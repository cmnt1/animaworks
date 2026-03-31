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

# ── ArcFace embedding extraction via onnxruntime ──────────

_ARCFACE_SESSION: Any | None = None
_SCRFD_SESSION: Any | None = None


def _resolve_onnx_path(repo_id: str, filename: str) -> str | None:
    """Resolve path to an ONNX model in the HuggingFace cache."""
    cache_dir = _HF_CACHE_ROOT / ("models--" + repo_id.replace("/", "--"))
    snapshots_dir = cache_dir / "snapshots"
    if not snapshots_dir.is_dir():
        return None
    for snap in sorted(snapshots_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        candidate = snap / filename
        if candidate.is_file():
            return str(candidate)
    return None


def _get_scrfd_session() -> Any | None:
    """Lazy-load SCRFD face detection ONNX session."""
    global _SCRFD_SESSION  # noqa: PLW0603
    if _SCRFD_SESSION is not None:
        return _SCRFD_SESSION
    try:
        import onnxruntime as ort
    except ImportError:
        logger.debug("onnxruntime not available — face detection disabled")
        return None
    path = _resolve_onnx_path("DIAMONIK7777/antelopev2", "scrfd_10g_bnkps.onnx")
    if path is None:
        logger.warning("SCRFD model not found in HF cache — face detection disabled")
        return None
    _SCRFD_SESSION = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    logger.info("SCRFD face detection model loaded: %s", path)
    return _SCRFD_SESSION


def _get_arcface_session() -> Any | None:
    """Lazy-load ArcFace recognition ONNX session."""
    global _ARCFACE_SESSION  # noqa: PLW0603
    if _ARCFACE_SESSION is not None:
        return _ARCFACE_SESSION
    try:
        import onnxruntime as ort
    except ImportError:
        logger.debug("onnxruntime not available — ArcFace disabled")
        return None
    path = _resolve_onnx_path("DIAMONIK7777/antelopev2", "glintr100.onnx")
    if path is None:
        logger.warning("ArcFace model not found in HF cache — face ID disabled")
        return None
    _ARCFACE_SESSION = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    logger.info("ArcFace recognition model loaded: %s", path)
    return _ARCFACE_SESSION


def _scrfd_detect(image_bgr: Any, session: Any) -> list[tuple[int, int, int, int, list[tuple[float, float]]]]:
    """Run SCRFD face detection. Returns list of (x1, y1, x2, y2, landmarks).

    The SCRFD model expects 640x640 input.  We letterbox the image and
    rescale detections back to original coordinates.
    """
    import numpy as np

    h0, w0 = image_bgr.shape[:2]
    target = 640
    scale = min(target / h0, target / w0)
    nw, nh = int(w0 * scale), int(h0 * scale)

    import cv2

    resized = cv2.resize(image_bgr, (nw, nh))
    padded = np.zeros((target, target, 3), dtype=np.uint8)
    padded[:nh, :nw] = resized

    blob = (padded.astype(np.float32) - 127.5) / 128.0
    blob = blob.transpose(2, 0, 1)[np.newaxis]

    outputs = session.run(None, {session.get_inputs()[0].name: blob})

    # SCRFD outputs: [scores_8, bboxes_8, kps_8, scores_16, bboxes_16, kps_16, scores_32, bboxes_32, kps_32]
    results: list[tuple[int, int, int, int, list[tuple[float, float]]]] = []
    strides = [8, 16, 32]
    threshold = 0.5

    for idx, stride in enumerate(strides):
        scores = outputs[idx * 3]
        bboxes = outputs[idx * 3 + 1]
        kps_raw = outputs[idx * 3 + 2]

        feat_h = target // stride
        feat_w = target // stride

        for i in range(scores.shape[1]):
            if scores[0, i, 0] < threshold:
                continue
            # bboxes are in distance format (left, top, right, bottom from anchor)
            anchor_y = (i // feat_w) * stride
            anchor_x = (i % feat_w) * stride

            x1 = (anchor_x - bboxes[0, i, 0] * stride) / scale
            y1 = (anchor_y - bboxes[0, i, 1] * stride) / scale
            x2 = (anchor_x + bboxes[0, i, 2] * stride) / scale
            y2 = (anchor_y + bboxes[0, i, 3] * stride) / scale

            # 5-point landmarks
            landmarks: list[tuple[float, float]] = []
            for j in range(5):
                lx = (anchor_x + kps_raw[0, i, j * 2] * stride) / scale
                ly = (anchor_y + kps_raw[0, i, j * 2 + 1] * stride) / scale
                landmarks.append((lx, ly))

            results.append((int(x1), int(y1), int(x2), int(y2), landmarks))

    # NMS
    if len(results) > 1:
        boxes = np.array([[r[0], r[1], r[2], r[3]] for r in results], dtype=np.float32)
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        order = areas.argsort()[::-1]
        keep: list[int] = []
        suppressed = set()
        for oi in order:
            if oi in suppressed:
                continue
            keep.append(oi)
            for oj in order:
                if oj in suppressed or oj == oi:
                    continue
                xx1 = max(boxes[oi, 0], boxes[oj, 0])
                yy1 = max(boxes[oi, 1], boxes[oj, 1])
                xx2 = min(boxes[oi, 2], boxes[oj, 2])
                yy2 = min(boxes[oi, 3], boxes[oj, 3])
                inter = max(0, xx2 - xx1) * max(0, yy2 - yy1)
                iou = inter / (areas[oi] + areas[oj] - inter + 1e-6)
                if iou > 0.4:
                    suppressed.add(oj)
        results = [results[i] for i in keep]

    return results


def _align_face_arcface(image_bgr: Any, landmarks: list[tuple[float, float]]) -> Any:
    """Align face to ArcFace standard 112x112 using 5-point landmarks.

    Uses the standard ArcFace alignment template (same as insightface).
    """
    import cv2
    import numpy as np

    # Standard ArcFace 112x112 destination landmarks
    dst = np.array([
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ], dtype=np.float32)

    src = np.array(landmarks, dtype=np.float32)
    M = cv2.estimateAffinePartial2D(src, dst)[0]
    if M is None:
        # Fallback: simple resize
        return cv2.resize(image_bgr, (112, 112))
    aligned = cv2.warpAffine(image_bgr, M, (112, 112), borderValue=0)
    return aligned


def _extract_arcface_embedding(image_pil: Any) -> Any | None:
    """Extract 512-dim ArcFace face embedding from a PIL image.

    Uses SCRFD for detection and glintr100 for recognition, both via
    onnxruntime — no insightface package required.

    Returns a numpy array of shape (512,) or None if no face detected.
    """
    import numpy as np

    try:
        import cv2
    except ImportError:
        logger.warning("OpenCV not available — ArcFace embedding extraction disabled")
        return None

    scrfd = _get_scrfd_session()
    arcface = _get_arcface_session()
    if scrfd is None or arcface is None:
        return None

    arr = np.array(image_pil)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    faces = _scrfd_detect(bgr, scrfd)
    if not faces:
        logger.info("No face detected by SCRFD — cannot extract embedding")
        return None

    # Pick largest face
    best = max(faces, key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
    x1, y1, x2, y2, landmarks = best
    logger.info("SCRFD detected face at (%d,%d)-(%d,%d)", x1, y1, x2, y2)

    # Align face for ArcFace
    aligned = _align_face_arcface(bgr, landmarks)

    # Preprocess for ArcFace: BGR float32, normalize
    blob = cv2.dnn.blobFromImage(
        aligned, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=False,
    )

    embedding = arcface.run(None, {arcface.get_inputs()[0].name: blob})[0][0]
    # Normalize
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    logger.info("ArcFace embedding extracted: dim=%d, norm=%.4f", len(embedding), np.linalg.norm(embedding))
    return embedding


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

    # VRAM thresholds for full-GPU mode.
    # RealVisXL_V5.0 (SDXL) memory budget in float16:
    #   UNet ~4.8 GB + VAE ~0.2 GB + CLIP ~1.3 GB = ~6.3 GB base
    #   Inference activations: ~0.7 GB with xFormers, ~3 GB without
    #   → need ≥7 GB free to run full-GPU with xFormers safely
    #   → need ≥10 GB free to run full-GPU without xFormers
    _VRAM_THRESHOLD_WITH_XFORMERS: int = 7 * 1024 ** 3
    _VRAM_THRESHOLD_NO_XFORMERS: int = 10 * 1024 ** 3

    @staticmethod
    def _xformers_available() -> bool:
        try:
            import xformers  # noqa: F401
            return True
        except ImportError:
            return False

    def _vram_offload_threshold(self) -> int:
        if self._xformers_available():
            return self._VRAM_THRESHOLD_WITH_XFORMERS
        return self._VRAM_THRESHOLD_NO_XFORMERS

    def _should_use_cpu_offload(self) -> bool:
        """Return True if free VRAM is below the threshold for full-VRAM mode."""
        if self._device != "cuda":
            return False
        try:
            torch = _import_torch()
            free, _ = torch.cuda.mem_get_info()
            threshold = self._vram_offload_threshold()
            needs_offload = free < threshold
            if needs_offload:
                logger.info(
                    "Free VRAM %.1fGB < %.0fGB threshold — enabling CPU offload for Diffusers",
                    free / 1024 ** 3,
                    threshold / 1024 ** 3,
                )
            return needs_offload
        except Exception:
            return False

    def _apply_memory_optimizations(self, pipe: Any, cpu_offload: bool) -> Any:
        """Apply VRAM-saving optimizations and optionally move to device.

        NOTE: xFormers and model_cpu_offload are mutually exclusive —
        do not enable xFormers when using CPU offload.
        """
        if cpu_offload:
            # CPU offload path: minimal VRAM usage, xFormers NOT compatible
            # VAE slicing still reduces peak decode VRAM
            try:
                pipe.vae.enable_slicing()
            except Exception:
                pass
            try:
                pipe.enable_model_cpu_offload()
                logger.info("Model CPU offload enabled (low-VRAM mode)")
                return pipe  # do NOT call .to(device) after cpu_offload
            except Exception:
                logger.warning("enable_model_cpu_offload failed, falling back to .to(device)", exc_info=True)
            return pipe.to(self._device)

        # Full-GPU path: use xFormers + slicing for maximum VRAM efficiency
        pipe = pipe.to(self._device)

        if self._xformers_available():
            try:
                pipe.enable_xformers_memory_efficient_attention()
                logger.info("xFormers memory-efficient attention enabled")
            except Exception:
                logger.debug("xFormers not applicable for this pipeline", exc_info=True)

        try:
            pipe.vae.enable_slicing()
            logger.debug("VAE slicing enabled")
        except Exception:
            pass

        try:
            pipe.enable_attention_slicing()
            logger.debug("Attention slicing enabled")
        except Exception:
            pass

        return pipe

    def _load_text2img_pipeline(self) -> Any:
        cache_key = ("text2img", self._text2img_source, self._device, self._dtype_name)
        cached = _PIPELINE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        auto_text2img, _ = _import_diffusers()
        pipe = auto_text2img.from_pretrained(self._text2img_source, **self._pipeline_kwargs())
        cpu_offload = self._should_use_cpu_offload()
        pipe = self._apply_memory_optimizations(pipe, cpu_offload)
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
            # Retire IP-Adapter before deriving img2img so bustup/expression
            # generation is not polluted by face-reference weights.
            text2img_key = ("text2img", self._text2img_source, self._device, self._dtype_name)
            self._retire_ip_adapter(text2img_key)
            pipe = auto_img2img.from_pipe(base_pipe)
        else:
            pipe = auto_img2img.from_pretrained(self._img2img_source, **self._pipeline_kwargs())
            cpu_offload = self._should_use_cpu_offload()
            pipe = self._apply_memory_optimizations(pipe, cpu_offload)
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
    def _pad_to_size(image: Any, width: int, height: int) -> Any:
        """Resize image to fit within width x height, then pad to exact size.

        Preserves aspect ratio by fitting image within the target dimensions
        and centering it on a neutral background.
        """
        image_cls, _ = _import_pil()
        img = image.copy()
        img.thumbnail((width, height), image_cls.LANCZOS)
        # Center on neutral background
        bg = image_cls.new("RGB", (width, height), (128, 128, 128))
        offset_x = (width - img.width) // 2
        offset_y = (height - img.height) // 2
        bg.paste(img, (offset_x, offset_y))
        return bg

    @staticmethod
    def _crop_to_face(image: Any) -> Any:
        """Detect face via OpenCV Haar cascade and crop tightly around it.

        Returns the cropped face region (with margin) or the original image
        if detection fails.  This prevents background/clothing from leaking
        into IP-Adapter embeddings.
        """
        try:
            import cv2
            import numpy as np

            arr = np.array(image)
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml",
            )
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30),
            )
            if len(faces) == 0:
                logger.info("No face detected in reference — using full image")
                return image

            # Pick the largest face
            x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
            # Expand by 50% for forehead/chin/cheek margin
            margin = int(max(w, h) * 0.5)
            ih, iw = arr.shape[:2]
            x1, y1 = max(0, x - margin), max(0, y - margin)
            x2, y2 = min(iw, x + w + margin), min(ih, y + h + margin)
            # Make square (IP-Adapter expects square input)
            side = max(x2 - x1, y2 - y1)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            x1 = max(0, cx - side // 2)
            y1 = max(0, cy - side // 2)
            x2 = min(iw, x1 + side)
            y2 = min(ih, y1 + side)
            # Adjust if clamped
            if x2 - x1 < side:
                x1 = max(0, x2 - side)
            if y2 - y1 < side:
                y1 = max(0, y2 - side)

            cropped = image.crop((x1, y1, x2, y2))
            logger.info(
                "Face detected: crop (%d,%d)-(%d,%d) from %dx%d",
                x1, y1, x2, y2, iw, ih,
            )
            return cropped
        except ImportError:
            logger.debug("OpenCV not available — skipping face crop")
            return image
        except Exception:
            logger.warning("Face detection failed — using full image", exc_info=True)
            return image

    @staticmethod
    def _make_generator(seed: int | None) -> Any:
        if seed is None:
            return None
        torch = _import_torch()
        return torch.Generator().manual_seed(seed)

    def _ensure_ip_adapter(self, pipe: Any, cache_key: tuple) -> None:
        """Load IP-Adapter FaceID weights onto a pipeline (lazy, once per pipeline).

        Uses IP-Adapter FaceID which accepts ArcFace embeddings (512-dim)
        instead of CLIP image embeddings.  This produces much better face
        similarity than the standard IP-Adapter Plus Face approach.

        Call :meth:`_retire_ip_adapter` when switching away from face mode.

        IMPORTANT: ``enable_model_cpu_offload`` must be (re-)applied **after**
        IP-Adapter weights are loaded.  The offload hooks wrap the UNet forward
        and can prevent ``added_cond_kwargs`` from being passed through when the
        adapter is loaded onto an already-offloaded pipeline.  After a
        successful load we therefore strip existing offload hooks and re-apply
        ``enable_model_cpu_offload`` so the new ``encoder_hid_proj`` layer is
        properly registered in the hook chain.
        """
        if cache_key in _IP_ADAPTER_LOADED:
            return

        ip_model = "h94/IP-Adapter-FaceID"

        if self._is_sdxl(self._text2img_source):
            ip_weight = "ip-adapter-faceid_sdxl.bin"
        else:
            ip_weight = "ip-adapter-faceid_sd15.bin"

        logger.info(
            "Loading IP-Adapter FaceID: %s (weight=%s, model=%s)",
            ip_model, ip_weight, self._text2img_source,
        )

        # Detect whether CPU-offload hooks are active on this pipeline so we
        # can re-apply them after the IP-Adapter load.
        had_cpu_offload = getattr(pipe, "_hf_hook", None) is not None or any(
            getattr(m, "_hf_hook", None) is not None
            for m in pipe.components.values() if m is not None
        )

        # Try local cache first, then auto-download if not found.
        for attempt, local_only in enumerate((self._local_files_only, False)):
            try:
                # Reset attention processors to default before loading IP-Adapter
                # to avoid SlicedAttnProcessor compatibility issues with diffusers.
                try:
                    pipe.unet.set_default_attn_processor()
                except Exception:
                    pass
                pipe.load_ip_adapter(
                    ip_model,
                    subfolder=None,
                    weight_name=ip_weight,
                    image_encoder_folder=None,
                    local_files_only=local_only,
                )

                # Re-apply CPU-offload hooks so the newly added
                # encoder_hid_proj (MultiIPAdapterImageProjection) is
                # included in the offload chain and added_cond_kwargs are
                # forwarded correctly through the UNet forward hooks.
                #
                # IMPORTANT: move all components to CPU *before* removing
                # hooks, otherwise remove_all_hooks() can cause the full
                # model to materialise on GPU and OOM on low-VRAM cards.
                if had_cpu_offload:
                    try:
                        pipe.to("cpu")
                        pipe.remove_all_hooks()
                        pipe.enable_model_cpu_offload()
                        logger.info(
                            "Re-applied model CPU offload after IP-Adapter load"
                        )
                    except Exception:
                        logger.warning(
                            "Failed to re-apply CPU offload after IP-Adapter load",
                            exc_info=True,
                        )

                _IP_ADAPTER_LOADED.add(cache_key)
                if attempt > 0:
                    logger.info("IP-Adapter FaceID downloaded and loaded successfully")
                else:
                    logger.info("IP-Adapter FaceID loaded from local cache")
                return
            except Exception:
                if attempt == 0 and self._local_files_only:
                    logger.info("IP-Adapter FaceID not in local cache — attempting download …")
                    continue
                logger.exception(
                    "Failed to load IP-Adapter FaceID (%s) — face reference will use img2img fallback",
                    ip_weight,
                )

    def _retire_ip_adapter(self, text2img_key: tuple) -> None:
        """Unload IP-Adapter from the cached text2img pipeline if present.

        Called once when switching away from face-reference mode (e.g. to
        plain text2img or img2img for bustup), NOT after every generation.
        """
        if text2img_key not in _IP_ADAPTER_LOADED:
            return
        pipe = _PIPELINE_CACHE.get(text2img_key)
        if pipe is None:
            _IP_ADAPTER_LOADED.discard(text2img_key)
            return
        try:
            pipe.unload_ip_adapter()
            logger.info("IP-Adapter retired (switching away from face reference mode)")
        except Exception:
            logger.warning("Failed to unload IP-Adapter", exc_info=True)
        _IP_ADAPTER_LOADED.discard(text2img_key)
        # Invalidate derived img2img cache so it is rebuilt cleanly.
        img2img_key = ("img2img", self._img2img_source, self._device, self._dtype_name)
        _PIPELINE_CACHE.pop(img2img_key, None)

    def _image2image_strength(self, requested: float | None = None) -> float:
        strength = requested
        if strength is None:
            strength = getattr(self._config, "diffusers_img2img_strength", 0.55)
        return max(0.15, min(0.85, float(strength)))

    def generate_fullbody(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 512,
        height: int = 768,
        seed: int | None = None,
        steps: int = 20,
        scale: float = 7.5,
        sampler: str = "k_euler_ancestral",
        vibe_image: bytes | None = None,
        vibe_strength: float = 0.6,
        vibe_info_extracted: float = 0.8,
        face_reference_image: bytes | None = None,
        step_callback: "Callable[[int, int], None] | None" = None,
    ) -> bytes:
        """Generate a full-body character image locally.

        If *face_reference_image* is provided, IP-Adapter FaceID is used
        to inject facial identity from the reference via ArcFace embeddings.
        This takes priority over *vibe_image* when both are supplied.

        *step_callback(current_step, total_steps)* is called after each
        denoising step so callers can emit progress events.
        """
        del sampler, vibe_info_extracted

        # In CPU-offload mode, further reduce to keep generation under ~5 min.
        cpu_offload = self._should_use_cpu_offload()
        if cpu_offload:
            steps = min(steps, 10)             # cap at 10 steps
            width = min(width, 512)            # max 512×512
            height = min(height, 512)
            logger.info(
                "Low-VRAM CPU-offload mode: reduced to %d steps at %dx%d",
                steps, width, height,
            )

        width, height = self._snap_size(width, height)
        total_steps = max(1, steps)
        generator = self._make_generator(seed)

        # Build Diffusers callback for progress reporting
        _done_steps = [0]

        def _diffusers_callback(pipe_self: Any, step: int, timestep: Any, callback_kwargs: dict) -> dict:  # noqa: ARG001
            _done_steps[0] = step + 1
            if step_callback is not None:
                try:
                    step_callback(_done_steps[0], total_steps)
                except Exception:
                    pass
            return callback_kwargs

        common_kwargs: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt or None,
            "guidance_scale": scale,
            "num_inference_steps": total_steps,
            "generator": generator,
            "callback_on_step_end": _diffusers_callback,
        }

        text2img_key = ("text2img", self._text2img_source, self._device, self._dtype_name)

        if face_reference_image is not None:
            # IP-Adapter FaceID: extract ArcFace embedding and use it for
            # identity-preserving generation.  Falls back to img2img if
            # embedding extraction or FaceID weights are unavailable.
            face_img = self._read_image(face_reference_image)
            face_embedding = _extract_arcface_embedding(face_img)

            pipe = self._load_text2img_pipeline()
            self._ensure_ip_adapter(pipe, text2img_key)

            if text2img_key in _IP_ADAPTER_LOADED and face_embedding is not None:
                torch = _import_torch()

                ip_scale = vibe_strength if vibe_strength is not None else float(
                    getattr(self._config, "ip_adapter_scale", 0.6),
                )
                pipe.set_ip_adapter_scale(ip_scale)

                # Build FaceID embedding tensors for classifier-free guidance:
                # [negative_embed, positive_embed] concatenated along batch dim.
                embed_t = torch.from_numpy(face_embedding).unsqueeze(0).unsqueeze(0)  # (1, 1, 512)
                neg_embed_t = torch.zeros_like(embed_t)
                id_embeds = torch.cat([neg_embed_t, embed_t]).to(
                    dtype=self._resolve_torch_dtype(),
                    device=self._device if not cpu_offload else "cpu",
                )

                common_kwargs["ip_adapter_image_embeds"] = [id_embeds]
                logger.info(
                    "Generating with IP-Adapter FaceID (scale=%.2f, embed shape=%s)",
                    ip_scale, list(id_embeds.shape),
                )

                result = pipe(**common_kwargs, width=width, height=height)

                # Invalidate img2img cache so bustup/expressions get fresh pipeline
                img2img_key = ("img2img", self._img2img_source, self._device, self._dtype_name)
                _PIPELINE_CACHE.pop(img2img_key, None)
            else:
                # FaceID unavailable — fall back to img2img with face crop.
                if face_embedding is None:
                    logger.warning("ArcFace embedding extraction failed — falling back to img2img")
                else:
                    logger.warning("IP-Adapter FaceID not loaded — falling back to img2img")

                face_strength = 1.0 - (vibe_strength if vibe_strength is not None else 0.6)
                face_strength = max(0.15, min(0.85, face_strength))
                logger.info(
                    "img2img fallback (strength=%.2f, %.0f%% face preserved)",
                    face_strength, (1 - face_strength) * 100,
                )
                pipe = self._load_img2img_pipeline()
                face_crop = self._crop_to_face(face_img)
                reference = self._pad_to_size(face_crop, width, height)
                result = pipe(
                    **common_kwargs,
                    image=reference,
                    strength=face_strength,
                )

        elif vibe_image is not None:
            # Switching away from face reference — retire IP-Adapter if loaded
            self._retire_ip_adapter(text2img_key)
            pipe = self._load_img2img_pipeline()
            reference = self._read_image(vibe_image).resize((width, height))
            result = pipe(
                **common_kwargs,
                image=reference,
                strength=self._image2image_strength(vibe_strength),
            )

        else:
            # Pure text2img — retire IP-Adapter if loaded
            self._retire_ip_adapter(text2img_key)
            pipe = self._load_text2img_pipeline()
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
