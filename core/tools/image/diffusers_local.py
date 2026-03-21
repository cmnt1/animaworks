"""Local Diffusers-backed image generation helpers."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.tools._base import logger

if TYPE_CHECKING:
    from core.config.models import ImageGenConfig

_HF_CACHE_ROOT = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
_AUTO_MODEL_REPOS = (
    "stable-diffusion-v1-5/stable-diffusion-v1-5",
    "runwayml/stable-diffusion-v1-5",
)
_ASPECT_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (896, 896),
    "3:4": (768, 1024),
    "4:3": (1024, 768),
}
_PIPELINE_CACHE: dict[tuple[str, str, str, str], Any] = {}
_IP_ADAPTER_LOADED: set[tuple[str, str, str, str]] = set()


def _import_torch() -> Any:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("torch is required for local Diffusers image generation.") from exc
    return torch


def _import_diffusers() -> tuple[Any, Any]:
    try:
        from diffusers import AutoPipelineForImage2Image, AutoPipelineForText2Image
    except ImportError as exc:
        raise RuntimeError("diffusers is required for local image generation. Install animaworks with Diffusers support.") from exc
    return AutoPipelineForText2Image, AutoPipelineForImage2Image


def _import_pil() -> tuple[Any, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for local Diffusers image generation.") from exc
    return Image, io.BytesIO


def _cache_dir_for_repo(repo_id: str) -> Path:
    return _HF_CACHE_ROOT / ("models--" + repo_id.replace("/", "--"))


def _resolve_snapshot_path(repo_id: str) -> str | None:
    cache_dir = _cache_dir_for_repo(repo_id)
    snapshots_dir = cache_dir / "snapshots"
    if not snapshots_dir.is_dir():
        return None

    main_ref = cache_dir / "refs" / "main"
    if main_ref.is_file():
        revision = main_ref.read_text(encoding="utf-8").strip()
        snapshot_dir = snapshots_dir / revision
        if snapshot_dir.is_dir():
            return str(snapshot_dir)

    snapshots = sorted((p for p in snapshots_dir.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    if snapshots:
        return str(snapshots[0])
    return None


def _resolve_model_source(value: str | None) -> str:
    if value and value not in {"", "auto"}:
        return value

    env_model = os.getenv("ANIMAWORKS_DIFFUSERS_MODEL")
    if env_model:
        return env_model

    for repo_id in _AUTO_MODEL_REPOS:
        snapshot = _resolve_snapshot_path(repo_id)
        if snapshot:
            logger.info("Using cached Diffusers model snapshot: %s", snapshot)
            return snapshot

    return _AUTO_MODEL_REPOS[0]


class LocalDiffusersClient:
    """Local text/image generation using Hugging Face Diffusers."""

    def __init__(self, config: ImageGenConfig | None = None) -> None:
        from core.config.models import ImageGenConfig

        self._config = config or ImageGenConfig()
        self._device = self._resolve_device(getattr(self._config, "diffusers_device", "auto"))
        self._dtype_name = getattr(self._config, "diffusers_torch_dtype", "auto")
        self._local_files_only = bool(getattr(self._config, "diffusers_local_files_only", True))

        # Resolve text2img model: style-specific override > generic > auto
        image_style = getattr(self._config, "image_style", "realistic")
        style_model = ""
        if image_style == "realistic":
            style_model = getattr(self._config, "diffusers_text2img_model_realistic", "") or ""
        elif image_style == "anime":
            style_model = getattr(self._config, "diffusers_text2img_model_anime", "") or ""
        base_model = style_model or getattr(self._config, "diffusers_text2img_model", "auto")
        self._text2img_source = _resolve_model_source(base_model)

        img2img_value = getattr(self._config, "diffusers_img2img_model", "auto")
        if not img2img_value or img2img_value == "auto":
            img2img_value = self._text2img_source
        self._img2img_source = _resolve_model_source(img2img_value)
        logger.info("Diffusers model resolved: style=%s, text2img=%s", image_style, self._text2img_source)

    @staticmethod
    def _resolve_device(value: str) -> str:
        if value != "auto":
            return value
        torch = _import_torch()
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _resolve_torch_dtype(self) -> Any:
        torch = _import_torch()
        if self._device == "cpu":
            return torch.float32
        if self._dtype_name == "float32":
            return torch.float32
        if self._dtype_name == "bfloat16":
            return torch.bfloat16
        return torch.float16

    @staticmethod
    def _snap_size(width: int, height: int) -> tuple[int, int]:
        snapped_width = max(64, (width // 8) * 8)
        snapped_height = max(64, (height // 8) * 8)
        return snapped_width, snapped_height

    @staticmethod
    def _is_sdxl(model_source: str) -> bool:
        """Detect whether the model source points to an SDXL-class model."""
        lower = model_source.lower()
        sdxl_markers = ("stable-diffusion-xl", "sdxl", "realvis", "animagine")
        return any(m in lower for m in sdxl_markers)

    def _pipeline_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "torch_dtype": self._resolve_torch_dtype(),
            "local_files_only": self._local_files_only,
        }
        # safety_checker is only used by SD 1.x pipelines; SDXL ignores it
        if not self._is_sdxl(self._text2img_source):
            kwargs["safety_checker"] = None
            kwargs["requires_safety_checker"] = False
        return kwargs

    @staticmethod
    def _apply_scheduler(pipe: Any, model_source: str) -> None:
        """Replace the default scheduler with DPM++ 2M Karras for better quality."""
        try:
            from diffusers import DPMSolverMultistepScheduler
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                pipe.scheduler.config,
                algorithm_type="dpmsolver++",
                use_karras_sigmas=True,
            )
            logger.info("Scheduler set to DPM++ 2M Karras for %s", model_source)
        except Exception:
            logger.debug("Failed to set DPM++ scheduler, keeping default", exc_info=True)

    def _load_text2img_pipeline(self) -> Any:
        cache_key = ("text2img", self._text2img_source, self._device, self._dtype_name)
        cached = _PIPELINE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        auto_text2img, _ = _import_diffusers()
        pipe = auto_text2img.from_pretrained(self._text2img_source, **self._pipeline_kwargs())
        pipe = pipe.to(self._device)
        self._apply_scheduler(pipe, self._text2img_source)
        _PIPELINE_CACHE[cache_key] = pipe
        return pipe

    def _load_img2img_pipeline(self) -> Any:
        cache_key = ("img2img", self._img2img_source, self._device, self._dtype_name)
        cached = _PIPELINE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        _, auto_img2img = _import_diffusers()
        if self._img2img_source == self._text2img_source:
            base_pipe = self._load_text2img_pipeline()
            pipe = auto_img2img.from_pipe(base_pipe)
        else:
            pipe = auto_img2img.from_pretrained(self._img2img_source, **self._pipeline_kwargs())
            pipe = pipe.to(self._device)
            self._apply_scheduler(pipe, self._img2img_source)
        _PIPELINE_CACHE[cache_key] = pipe
        return pipe

    @staticmethod
    def _to_png_bytes(image: Any) -> bytes:
        _, bytes_io_cls = _import_pil()
        buffer = bytes_io_cls()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    @staticmethod
    def _read_image(image_bytes: bytes) -> Any:
        image_cls, bytes_io_cls = _import_pil()
        image = image_cls.open(bytes_io_cls(image_bytes))
        return image.convert("RGB")

    @staticmethod
    def _make_generator(seed: int | None) -> Any:
        if seed is None:
            return None
        torch = _import_torch()
        return torch.Generator().manual_seed(seed)

    def _ensure_ip_adapter(self, pipe: Any, cache_key: tuple) -> None:
        """Load IP-Adapter face weights onto a pipeline (lazy, once per pipeline)."""
        if cache_key in _IP_ADAPTER_LOADED:
            return

        if not self._is_sdxl(self._text2img_source):
            logger.warning("IP-Adapter face reference is only supported for SDXL models")
            return

        ip_model = getattr(self._config, "ip_adapter_model", "h94/IP-Adapter")
        ip_weight = "ip-adapter-plus-face_sdxl_vit-h.safetensors"

        logger.info("Loading IP-Adapter: %s (subfolder=sdxl_models, weight=%s)", ip_model, ip_weight)
        try:
            pipe.load_ip_adapter(
                ip_model,
                subfolder="sdxl_models",
                weight_name=ip_weight,
                image_encoder_folder="models/image_encoder",
                local_files_only=self._local_files_only,
            )
            _IP_ADAPTER_LOADED.add(cache_key)
            logger.info("IP-Adapter loaded successfully")
        except Exception:
            logger.exception("Failed to load IP-Adapter — generating without face reference")

    def _image2image_strength(self, requested: float | None = None) -> float:
        strength = requested
        if strength is None:
            strength = getattr(self._config, "diffusers_img2img_strength", 0.55)
        return max(0.15, min(0.85, float(strength)))

    def generate_fullbody(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 768,
        height: int = 1152,
        seed: int | None = None,
        steps: int = 40,
        scale: float = 7.5,
        sampler: str = "k_euler_ancestral",
        vibe_image: bytes | None = None,
        vibe_strength: float = 0.6,
        vibe_info_extracted: float = 0.8,
        face_reference_image: bytes | None = None,
    ) -> bytes:
        """Generate a full-body character image locally.

        If *face_reference_image* is provided, IP-Adapter (Plus Face) is used
        to inject the facial features from the reference into the generation.
        This takes priority over *vibe_image* when both are supplied.
        """
        del sampler, vibe_info_extracted

        width, height = self._snap_size(width, height)
        generator = self._make_generator(seed)
        common_kwargs: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt or None,
            "guidance_scale": scale,
            "num_inference_steps": max(1, steps),
            "generator": generator,
        }

        text2img_key = ("text2img", self._text2img_source, self._device, self._dtype_name)

        if face_reference_image is not None:
            # IP-Adapter face reference → text2img + adapter
            pipe = self._load_text2img_pipeline()
            self._ensure_ip_adapter(pipe, text2img_key)

            if text2img_key in _IP_ADAPTER_LOADED:
                ip_scale = float(getattr(self._config, "ip_adapter_scale", 0.6))
                pipe.set_ip_adapter_scale(ip_scale)
                face_img = self._read_image(face_reference_image)
                common_kwargs["ip_adapter_image"] = face_img
                logger.info("Generating with IP-Adapter face reference (scale=%.2f)", ip_scale)

            result = pipe(**common_kwargs, width=width, height=height)

        elif vibe_image is not None:
            pipe = self._load_img2img_pipeline()
            # Disable IP-Adapter if it was previously loaded on the text2img pipe
            if text2img_key in _IP_ADAPTER_LOADED:
                t2i_pipe = _PIPELINE_CACHE.get(text2img_key)
                if t2i_pipe is not None:
                    t2i_pipe.set_ip_adapter_scale(0.0)
            reference = self._read_image(vibe_image).resize((width, height))
            result = pipe(
                **common_kwargs,
                image=reference,
                strength=self._image2image_strength(vibe_strength),
            )

        else:
            pipe = self._load_text2img_pipeline()
            # Disable IP-Adapter if loaded but no face reference this time
            if text2img_key in _IP_ADAPTER_LOADED:
                pipe.set_ip_adapter_scale(0.0)
            result = pipe(**common_kwargs, width=width, height=height)

        return self._to_png_bytes(result.images[0])

    def _run_img2img_pipeline(
        self,
        pipe: Any,
        prompt: str,
        negative_prompt: str,
        image: Any,
        guidance_scale: float,
        strength: float,
        generator: Any,
        steps: int,
    ) -> Any:
        """Run img2img with step fallback in case scheduler limits are hit."""
        max_attempts = 3
        attempt_steps = max(1, steps)
        kwargs = {
            "image": image,
            "guidance_scale": guidance_scale,
            "strength": strength,
            "generator": generator,
        }
        for attempt in range(max_attempts):
            pipe.scheduler.set_timesteps(attempt_steps)
            try:
                return pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt or None,
                    num_inference_steps=attempt_steps,
                    **kwargs,
                )
            except IndexError:
                if attempt == max_attempts - 1 or attempt_steps <= 5:
                    raise
                attempt_steps = max(5, attempt_steps - 2)


    def generate_from_reference(
        self,
        reference_image: bytes,
        prompt: str,
        aspect_ratio: str = "3:4",
        output_format: str = "png",
        guidance_scale: float = 5.5,
        seed: int | None = None,
        negative_prompt: str = "",
        strength: float | None = None,
    ) -> bytes:
        """Generate a derivative image from a reference image locally."""
        del output_format

        width, height = _ASPECT_SIZES.get(aspect_ratio, _ASPECT_SIZES["3:4"])
        generator = self._make_generator(seed)
        reference = self._read_image(reference_image).resize((width, height))
        pipe = self._load_img2img_pipeline()
        result = self._run_img2img_pipeline(
            pipe=pipe,
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=reference,
            guidance_scale=guidance_scale,
            strength=self._image2image_strength(strength),
            generator=generator,
            steps=max(1, int(getattr(self._config, "diffusers_num_inference_steps", 28))),
        )
        return self._to_png_bytes(result.images[0])


__all__ = [
    "LocalDiffusersClient",
]
