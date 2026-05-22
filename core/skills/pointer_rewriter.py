from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Exact skill pointer rewrites for migration-time reference repair."""

import json
import re
from typing import Any


def rewrite_skill_pointers_in_text(text: str, pointer_map: dict[str, str]) -> str:
    """Rewrite exact skill pointer strings without changing skill-name refs."""
    normalized = normalize_pointer_map(pointer_map)
    if not normalized:
        return text
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return _rewrite_pointer_yamlish_text(text, normalized)
        changed, rewritten = _rewrite_json_pointers(data, normalized)
        return json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n" if changed else text
    if _looks_jsonl(text):
        out: list[str] = []
        changed = False
        for line in text.splitlines():
            if not line.strip():
                out.append(line)
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                out.append(line)
                continue
            line_changed, rewritten = _rewrite_json_pointers(data, normalized)
            changed = changed or line_changed
            out.append(json.dumps(rewritten, ensure_ascii=False) if line_changed else line)
        return "\n".join(out) + ("\n" if text.endswith("\n") else "") if changed else text
    return _rewrite_pointer_yamlish_text(text, normalized)


def normalize_pointer_map(pointer_map: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for old, new in pointer_map.items():
        old_value = str(old).strip()
        new_value = str(new).strip()
        if old_value and new_value and old_value != new_value:
            normalized[old_value] = new_value
    return normalized


def _rewrite_json_pointers(value: Any, pointer_map: dict[str, str]) -> tuple[bool, Any]:
    if isinstance(value, dict):
        changed = False
        result: dict[str, Any] = {}
        for key, item in value.items():
            item_changed, new_item = _rewrite_json_pointers(item, pointer_map)
            changed = changed or item_changed
            result[key] = new_item
        return changed, result
    if isinstance(value, list):
        changed = False
        result = []
        for item in value:
            item_changed, new_item = _rewrite_json_pointers(item, pointer_map)
            changed = changed or item_changed
            result.append(new_item)
        return changed, result
    if isinstance(value, str):
        rewritten = pointer_map.get(value)
        if rewritten is not None:
            return True, rewritten
    return False, value


def _rewrite_pointer_yamlish_text(text: str, pointer_map: dict[str, str]) -> str:
    lines = text.splitlines()
    out: list[str] = []
    changed = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if _is_inline_skills_line(stripped):
            new_line = _rewrite_inline_pointer_line(line, pointer_map)
            changed = changed or new_line != line
            out.append(new_line)
            i += 1
            continue
        if _is_scalar_skills_line(stripped):
            new_line = _rewrite_scalar_pointers_line(line, pointer_map)
            changed = changed or new_line != line
            out.append(new_line)
            i += 1
            continue
        if re.match(r"^\s*skills:\s*$", line):
            block, next_i = _consume_skills_block(lines, i)
            new_block = _rewrite_pointer_block(block, pointer_map)
            changed = changed or new_block != block
            out.extend(new_block)
            i = next_i
            continue
        if _is_scalar_skill_line(stripped):
            new_line = _rewrite_scalar_pointer_line(line, pointer_map)
            changed = changed or new_line != line
            out.append(new_line)
            i += 1
            continue
        out.append(line)
        i += 1
    if not changed:
        return text
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + suffix


def _is_inline_skills_line(stripped: str) -> bool:
    return stripped.startswith("skills:") and "[" in stripped and "]" in stripped


def _is_scalar_skills_line(stripped: str) -> bool:
    return stripped.startswith("skills:") and "[" not in stripped and stripped != "skills:"


def _is_scalar_skill_line(stripped: str) -> bool:
    return stripped.startswith(("skill:", "skill_name:", "skill_pointer:"))


def _rewrite_inline_pointer_line(line: str, pointer_map: dict[str, str]) -> str:
    prefix, rest = line.split(":", 1)
    before, _, after_bracket = rest.partition("[")
    inner, _, suffix = after_bracket.partition("]")
    values = [_strip_quotes(v.strip()) for v in inner.split(",") if v.strip()]
    rewritten = _rewrite_pointer_list(values, pointer_map)
    if rewritten == values:
        return line
    quote = '"'
    joined = ", ".join(f"{quote}{v}{quote}" for v in rewritten)
    return f"{prefix}:{before}[{joined}]{suffix}"


def _consume_skills_block(lines: list[str], start: int) -> tuple[list[str], int]:
    block = [lines[start]]
    i = start + 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("- "):
            block.append(lines[i])
            i += 1
            continue
        if not stripped:
            block.append(lines[i])
            i += 1
            continue
        break
    return block, i


def _rewrite_pointer_block(block: list[str], pointer_map: dict[str, str]) -> list[str]:
    header = block[0]
    indent = re.match(r"^(\s*)", header).group(1)  # type: ignore[union-attr]
    result = [header]
    changed = False
    for line in block[1:]:
        stripped = line.strip()
        if not stripped.startswith("- "):
            result.append(line)
            continue
        value = _strip_quotes(stripped[2:].strip())
        rewritten = pointer_map.get(value)
        if rewritten is None:
            result.append(line)
            continue
        changed = True
        result.append(f"{indent}  - {rewritten}")
    if not changed:
        return block
    return result


def _rewrite_scalar_pointer_line(line: str, pointer_map: dict[str, str]) -> str:
    prefix, value = line.split(":", 1)
    current = _strip_quotes(value.strip())
    rewritten = pointer_map.get(current)
    if rewritten is None:
        return line
    return f"{prefix}: {rewritten}"


def _rewrite_scalar_pointers_line(line: str, pointer_map: dict[str, str]) -> str:
    prefix, value = line.split(":", 1)
    raw = value.strip()
    values = [_strip_quotes(v.strip()) for v in raw.split(",") if v.strip()] if "," in raw else [_strip_quotes(raw)]
    rewritten = _rewrite_pointer_list(values, pointer_map)
    if rewritten == values:
        return line
    return f"{prefix}: {', '.join(rewritten)}"


def _rewrite_pointer_list(values: list[str], pointer_map: dict[str, str]) -> list[str]:
    result: list[str] = []
    for value in values:
        rewritten = pointer_map.get(value, value)
        if rewritten not in result:
            result.append(rewritten)
    return result


def _looks_jsonl(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("{") and line.endswith("}") for line in lines)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
