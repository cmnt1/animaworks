"""Structural and language validation for generated translation sections."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import yaml


class ValidationError(ValueError):
    """Raised when a translated section violates a preservation rule."""


_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+", re.MULTILINE)
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\n]*(?:\n|$).*?^ {0,3}(`{3,}|~{3,})[ \t]*$", re.MULTILINE | re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_.]*)\}(?!\})")
_URL_RE = re.compile(r"https?://[^\s<>()]+")
_LINK_DEST_RE = re.compile(r"\]\(([^\s)]+)")
_JAPANESE_RE = re.compile(r"[ぁ-んァ-ン一-龯々〆ヵヶ]")
_KANA_RE = re.compile(r"[ぁ-んァ-ン]")
_HANGUL_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
_ALLOWED_FRONTMATTER_KEYS = {"description", "title", "summary"}


def _code_blocks(text: str) -> list[str]:
    return [match.group(0) for match in _FENCE_RE.finditer(text)]


def _frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") in {"---", "..."}), None)
    if end is None:
        raise ValidationError("Frontmatter closing delimiter is missing")
    raw = "".join(lines[1:end])
    try:
        parsed = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValidationError("Frontmatter is not valid YAML") from exc
    if not isinstance(parsed, dict):
        raise ValidationError("Frontmatter must be a YAML mapping")
    return parsed, raw


def _table_shapes(text: str) -> list[tuple[int, int]]:
    shapes: list[tuple[int, int]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = stripped.strip("|").split("|")
        shapes.append((len(cells), len(cells)))
    return shapes


def _visible(text: str) -> str:
    text = re.sub(r"⟦P\d+⟧", " ", text)
    text = re.sub(r"```.*?```|~~~.*?~~~", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return text


def _check_language(source_visible: str, translated_visible: str, lang: str) -> None:
    if not _JAPANESE_RE.search(source_visible):
        return
    letters = [char for char in translated_visible if char.isalpha()]
    if not letters:
        raise ValidationError(f"Translation to {lang} contains no readable text")
    japanese_ratio = sum(bool(_JAPANESE_RE.fullmatch(char)) for char in letters) / len(letters)
    if lang == "en" and japanese_ratio >= 0.02:
        raise ValidationError(f"English output contains too much Japanese text ({japanese_ratio:.1%})")
    if lang == "ko":
        kana_ratio = sum(bool(_KANA_RE.fullmatch(char)) for char in letters) / len(letters)
        hangul_ratio = sum(bool(_HANGUL_RE.fullmatch(char)) for char in letters) / len(letters)
        if kana_ratio >= 0.02:
            raise ValidationError(f"Korean output contains too much kana ({kana_ratio:.1%})")
        if hangul_ratio < 0.05:
            raise ValidationError(f"Korean output contains too little Hangul ({hangul_ratio:.1%})")


def validate_translation(
    source: str,
    translated: str,
    lang: str,
    *,
    source_visible: str | None = None,
    translated_visible: str | None = None,
    frontmatter: bool = False,
) -> None:
    """Raise :class:`ValidationError` if structure, identifiers, or locale changed."""
    errors: list[str] = []
    if _PLACEHOLDER_RE.findall(source) != _PLACEHOLDER_RE.findall(translated):
        if Counter(_PLACEHOLDER_RE.findall(source)) != Counter(_PLACEHOLDER_RE.findall(translated)):
            errors.append("placeholder set changed")
    if _code_blocks(source) != _code_blocks(translated):
        errors.append("fenced code blocks changed")
    if [len(match.group(1)) for match in _HEADING_RE.finditer(source)] != [
        len(match.group(1)) for match in _HEADING_RE.finditer(translated)
    ]:
        errors.append("heading count or levels changed")
    if Counter(_URL_RE.findall(source)) != Counter(_URL_RE.findall(translated)):
        errors.append("URL set changed")
    if Counter(_LINK_DEST_RE.findall(source)) != Counter(_LINK_DEST_RE.findall(translated)):
        errors.append("Markdown link destinations changed")
    if _table_shapes(source) != _table_shapes(translated):
        errors.append("table row/column structure changed")

    if frontmatter:
        try:
            source_data = _frontmatter(source)
            translated_data = _frontmatter(translated)
            if source_data is None or translated_data is None:
                errors.append("frontmatter delimiters changed")
            else:
                source_mapping, _ = source_data
                translated_mapping, _ = translated_data
                if set(source_mapping) != set(translated_mapping):
                    errors.append("frontmatter keys changed")
                for key in set(source_mapping) - _ALLOWED_FRONTMATTER_KEYS:
                    if source_mapping.get(key) != translated_mapping.get(key):
                        errors.append(f"frontmatter value changed for {key}")
        except ValidationError as exc:
            errors.append(str(exc))

    if errors:
        raise ValidationError("; ".join(errors))

    _check_language(
        source_visible if source_visible is not None else _visible(source),
        translated_visible if translated_visible is not None else _visible(translated),
        lang,
    )
