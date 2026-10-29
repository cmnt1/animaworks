"""JSON manifest persistence and generated-document header helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
_TRANSLATION_HEADER_RE = re.compile(
    r"\A<!-- 自動翻訳ファイル・編集禁止 \(AUTO-TRANSLATED, DO NOT EDIT\)\. 正本: [^\n]+ -->\n"
    r"<!-- i18n: source-sha256=([0-9a-f]{64}) generated=[^ ]+ engine=[^ ]+ model=[^ ]+ translator=[^ ]+ -->\n(?:\n)?"
)


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": MANIFEST_VERSION, "files": {}}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read translation manifest: {path}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise ValueError(f"Invalid translation manifest structure: {path}")
    manifest.setdefault("version", MANIFEST_VERSION)
    return manifest


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def strip_translation_header(text: str) -> tuple[str, str | None]:
    match = _TRANSLATION_HEADER_RE.match(text)
    if not match:
        return text, None
    return text[match.end() :], match.group(1)


def translation_header(
    *, source_path: str, source_sha256: str, generated: str, engine: str, model: str, translator: str
) -> str:
    return (
        f"<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: {source_path} -->\n"
        f"<!-- i18n: source-sha256={source_sha256} generated={generated} engine={engine} "
        f"model={model} translator={translator} -->\n\n"
    )
