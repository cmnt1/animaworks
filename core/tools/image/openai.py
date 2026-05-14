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
from pathlib import Path

from core.platform.codex import default_home_dir, get_codex_executable
from core.tools._base import logger

from .utils import _retry

OPENAI_IMAGE_MODELS = ("gpt-image-2",)
OPENAI_IMG2IMG_MODELS = frozenset(OPENAI_IMAGE_MODELS)


def _openai_size(width: int, height: int) -> str:
    """Map arbitrary dimensions to GPT Image friendly aspect-ratio sizes."""
    if height > width:
        return "1024x1536"
    if width > height:
        return "1536x1024"
    return "1024x1024"


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

        reference_guidance = ""
        if references:
            references_text = "\n".join(f"- {path}" for path in references)
            reference_guidance = (
                "The reference image files are mandatory visual inputs. "
                "Inspect the local reference image files before generating and translate their visible traits into the image request. "
                "If face_reference.png is listed, use it as the primary face and identity reference: "
                "match facial proportions, age, hairstyle, glasses, expression style, and overall person identity as closely as possible. "
                "Use style_reference.png only for outfit, pose, palette, and composition guidance.\n"
            )
        else:
            references_text = "- None"

        avoid_text = negative_prompt.strip() or "text, watermark, logo, extra limbs, duplicate body, cropped body"
        instruction = (
            "Use Codex's built-in image generation tool with gpt-image-2 to create exactly one PNG image.\n"
            "Do not use the OpenAI API directly, do not use an API key, and do not write a script that calls an image API.\n"
            "This pipeline slot is named fullbody, but for this OpenAI backend generate a bust-up head-and-shoulders human character portrait. "
            "Prioritize face identity and upper-torso character design over full-body composition. "
            "If the result is not clearly a single human person, retry before finishing.\n"
            "Use the listed reference images as visual references when present, especially for face/identity and style.\n"
            f"{reference_guidance}\n"
            f"Prompt:\n{prompt.strip()}\n\n"
            f"Reference images:\n{references_text}\n\n"
            f"Canvas size: {size}\n"
            f"Avoid: {avoid_text}\n"
            f"Save or copy the final generated image to this exact path:\n{output_path}\n\n"
            "When finished, print only the absolute output path."
        )

        logger.info(
            "Codex image request model=%s size=%s references=%d prompt=%.500s",
            self._model,
            size,
            len(references),
            prompt.strip().replace("\n", " "),
        )

        since_ts = time.time()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()

        cmd = [
            codex,
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--cd",
            str(Path.cwd()),
        ]
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

        size = _openai_size(width, height)

        def _call() -> bytes:
            with tempfile.TemporaryDirectory(prefix="animaworks-codex-image-") as tmp:
                tmp_dir = Path(tmp)
                references: list[Path] = []
                if vibe_image is not None:
                    path = tmp_dir / "style_reference.png"
                    path.write_bytes(vibe_image)
                    references.append(path)
                if face_reference_image is not None:
                    path = tmp_dir / "face_reference.png"
                    path.write_bytes(face_reference_image)
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

        image = _retry(_call)
        logger.info("Codex image generated (model=%s)", self._model)
        return image
