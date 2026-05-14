# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Codex built-in GPT Image client for character portrait generation."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from core.platform.codex import default_home_dir, get_codex_executable
from core.tools._base import logger

OPENAI_IMAGE_MODELS = ("gpt-image-2",)
OPENAI_IMG2IMG_MODELS = frozenset(OPENAI_IMAGE_MODELS)
_MAX_CODEX_PROMPT_CHARS = 1800
_REFERENCE_UNSUPPORTED_MESSAGE = (
    "gpt-image-2 via Codex subscription auth cannot reliably use reference images in this environment. "
    "Choose a reference-capable backend such as Diffusers or NanoGPT, or set "
    "ANIMAWORKS_CODEX_IMAGE_ALLOW_REFERENCES=1 to force an experimental Codex reference attempt."
)

_TRANSIENT_CODEX_ERROR_MARKERS = (
    "stream disconnected",
    "reconnecting",
    "retrying sampling request",
    "you can retry your request",
    "temporarily unavailable",
)


class _TransientCodexImageError(RuntimeError):
    """A Codex image generation failure that is worth retrying from scratch."""


def _is_transient_codex_failure(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _TRANSIENT_CODEX_ERROR_MARKERS)


def _read_env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(0, value)


def _read_env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(0.0, value)


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _openai_size(width: int, height: int) -> str:
    """Map arbitrary dimensions to GPT Image friendly aspect-ratio sizes."""
    if height > width:
        return "1024x1536"
    if width > height:
        return "1536x1024"
    return "1024x1024"


def _compact_prompt(prompt: str) -> str:
    text = " ".join(prompt.split())
    if len(text) <= _MAX_CODEX_PROMPT_CHARS:
        return text
    return text[: _MAX_CODEX_PROMPT_CHARS - 3].rstrip() + "..."


def _codex_generated_image_roots(codex_home: Path | None) -> list[Path]:
    roots: list[Path] = []
    if codex_home:
        roots.append(codex_home)
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        roots.append(Path(env_home).expanduser())
    roots.append(Path(default_home_dir()) / ".codex")

    seen: set[Path] = set()
    result: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            resolved = root
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def _find_latest_codex_generated_image(since_ts: float, codex_home: Path | None) -> Path | None:
    candidates: list[tuple[float, Path]] = []
    for root in _codex_generated_image_roots(codex_home):
        gen_root = root / "generated_images"
        if not gen_root.is_dir():
            continue
        for path in gen_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime >= since_ts - 5:
                candidates.append((mtime, path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _terminate_process_tree(pid: int) -> None:
    """Best-effort termination for a Codex CLI wrapper and its children."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        logger.debug("Failed to terminate Codex process group pid=%s", pid, exc_info=True)


def _write_reference_png(image_bytes: bytes, path: Path, label: str) -> None:
    """Decode a user/reference image and write a small, valid PNG for Codex."""
    try:
        from PIL import Image, ImageOps
    except Exception as exc:
        raise RuntimeError("Pillow is required to prepare reference images for gpt-image-2") from exc

    max_side = _read_env_int("ANIMAWORKS_CODEX_REFERENCE_MAX_SIDE", 256) or 256
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            if max(img.size) > max_side:
                img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            if img.mode not in {"RGB", "RGBA"}:
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            img.save(path, format="PNG", optimize=True)
    except Exception as exc:
        raise RuntimeError(f"{label} reference image could not be decoded as an image") from exc

    logger.info(
        "Prepared %s reference image for Codex: %s (%d bytes)",
        label,
        path.name,
        path.stat().st_size,
    )


class OpenAIImageClient:
    """Generate images through Codex built-in image_gen using subscription auth.

    The Remake Assets selector uses the ``openai:`` provider label for user-facing
    clarity, but the actual auth path follows the Usage Governor's Codex
    subscription credentials and invokes ``codex exec``. This matches the
    reference implementation from session 019e23ee-b31c-7801-a4e6-bfba696cf13b.
    """

    def __init__(self, model: str = "gpt-image-2") -> None:
        self._model = model

    @staticmethod
    def _codex_home() -> Path:
        from server.routes.usage_routes import get_openai_subscription_codex_home

        return get_openai_subscription_codex_home(refresh=False)

    def _run_codex_image_gen(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        size: str,
        references: list[Path],
        output_path: Path,
    ) -> None:
        codex = get_codex_executable()
        if not codex:
            raise RuntimeError("Codex CLI not found; complete Codex login before using gpt-image-2")

        codex_home = self._codex_home()
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)

        if references:
            references_text = "\n".join(f"- {path.name}: {path}" for path in references)
        else:
            references_text = "- None"

        avoid_text = negative_prompt.strip() or "text, watermark, logo, extra limbs, duplicate body, cropped body"
        compact_prompt = _compact_prompt(prompt)
        instruction = (
            "Use the built-in image generation tool with gpt-image-2 to create one PNG.\n"
            "Generate a single human bust-up, head-and-shoulders character portrait.\n"
            "If face_reference.png is provided, use it as the face and identity reference. "
            "If style_reference.png is provided, use it only for style, palette, outfit, or composition.\n"
            f"Prompt:\n{compact_prompt}\n\n"
            f"Reference images:\n{references_text}\n\n"
            f"Canvas size: {size}\n"
            f"Avoid: {avoid_text}\n"
            f"Save or copy the final generated image to this exact path:\n{output_path}\n\n"
            "When finished, print only the absolute output path."
        )

        logger.info(
            "Codex image request model=%s size=%s references=%d prompt_chars=%d prompt=%.500s",
            self._model,
            size,
            len(references),
            len(prompt),
            _compact_prompt(prompt),
        )

        since_ts = time.time()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()

        cmd = [
            codex,
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--ephemeral",
            "--ignore-rules",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--cd",
            str(output_path.parent),
        ]
        agent_model = os.environ.get("ANIMAWORKS_CODEX_IMAGE_AGENT_MODEL", "").strip()
        if agent_model:
            cmd.extend(["--model", agent_model])
        for reference in references:
            cmd.extend(["--image", str(reference)])
        cmd.append("-")
        timeout_sec = int(os.environ.get("ANIMAWORKS_CODEX_IMAGE_TIMEOUT_SEC", "600"))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if os.name == "nt":
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            env=env,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        try:
            stdout, stderr = proc.communicate(input=instruction, timeout=timeout_sec)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_tree(proc.pid)
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except Exception:
                stdout, stderr = "", ""
            tail = ((stderr or "") + "\n" + (stdout or ""))[-1200:]
            raise RuntimeError(f"Codex image_gen timed out after {timeout_sec}s: {tail}") from exc

        logger.info(
            "Codex image_gen finished rc=%s model=%s codex_home=%s",
            proc.returncode,
            self._model,
            codex_home,
        )
        if proc.returncode != 0:
            tail = ((stderr or "") + "\n" + (stdout or ""))[-1200:]
            if _is_transient_codex_failure(tail):
                raise _TransientCodexImageError(f"Codex image_gen transient failure rc={proc.returncode}: {tail}")
            raise RuntimeError(f"Codex image_gen failed rc={proc.returncode}: {tail}")

        if output_path.exists() and output_path.stat().st_size > 0:
            return

        latest = _find_latest_codex_generated_image(since_ts, codex_home)
        if latest and latest.exists() and latest.stat().st_size > 0:
            shutil.copyfile(latest, output_path)
            return

        tail = ((stdout or "") + "\n" + (stderr or ""))[-1200:]
        raise RuntimeError(f"Codex image_gen finished but image file was not found: {tail}")

    def generate_fullbody(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1536,
        seed: int | None = None,
        steps: int = 28,
        scale: float = 5.0,
        sampler: str = "k_euler_ancestral",
        vibe_image: bytes | None = None,
        vibe_strength: float = 0.6,
        vibe_info_extracted: float = 0.8,
        face_reference_image: bytes | None = None,
        step_callback: Callable[[int, int], None] | None = None,
    ) -> bytes:
        """Generate a character portrait via Codex built-in image_gen."""
        del seed, steps, scale, sampler, vibe_strength, vibe_info_extracted, step_callback

        has_reference = vibe_image is not None or face_reference_image is not None
        if has_reference and not _env_enabled("ANIMAWORKS_CODEX_IMAGE_ALLOW_REFERENCES"):
            raise RuntimeError(_REFERENCE_UNSUPPORTED_MESSAGE)

        size = _openai_size(width, height)

        def _call() -> bytes:
            with tempfile.TemporaryDirectory(prefix="animaworks-codex-image-") as tmp:
                tmp_dir = Path(tmp)
                references: list[Path] = []
                if vibe_image is not None:
                    path = tmp_dir / "style_reference.png"
                    _write_reference_png(vibe_image, path, "style")
                    references.append(path)
                if face_reference_image is not None:
                    path = tmp_dir / "face_reference.png"
                    _write_reference_png(face_reference_image, path, "face")
                    references.append(path)

                output_path = tmp_dir / "generated.png"
                self._run_codex_image_gen(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    size=size,
                    references=references,
                    output_path=output_path,
                )
                return output_path.read_bytes()

        max_retries = _read_env_int("ANIMAWORKS_CODEX_IMAGE_RETRIES", 2)
        retry_delay = _read_env_float("ANIMAWORKS_CODEX_IMAGE_RETRY_DELAY_SEC", 15.0)
        for attempt in range(max_retries + 1):
            try:
                image = _call()
                break
            except _TransientCodexImageError as exc:
                if attempt >= max_retries:
                    raise RuntimeError(
                        f"Codex image_gen failed after {attempt + 1} attempts due to transient stream errors: {exc}"
                    ) from exc
                wait = retry_delay * (attempt + 1)
                logger.warning(
                    "Codex image_gen transient failure; retrying attempt %d/%d in %.1fs",
                    attempt + 2,
                    max_retries + 1,
                    wait,
                )
                time.sleep(wait)
        logger.info("Codex image generated (model=%s)", self._model)
        return image
