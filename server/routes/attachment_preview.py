from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Structure-only previews for chat attachments.

Converts ``.xlsx`` / ``.docx`` / ``.pptx`` files into JSON-friendly structures
using only the standard library (``zipfile`` + ``xml.etree.ElementTree``).
The converters are deliberately conservative: malformed, encrypted or
suspiciously large archives are rejected instead of partially rendered.
"""

import datetime as dt
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_MEMBER_SIZE = 30 * 1024 * 1024
MAX_TOTAL_READ = 100 * 1024 * 1024
MAX_SHEETS = 20
MAX_SHEET_ROWS = 500
MAX_SHEET_COLUMNS = 50
MAX_DOC_BLOCKS = 2000
MAX_TABLE_ROWS = 200
MAX_SLIDES = 200

SUPPORTED_EXTENSIONS = frozenset({".xlsx", ".xlsm", ".docx", ".pptx"})

_UNSUPPORTED_KEY = "chat.attach.preview_unsupported"
_TOO_LARGE_KEY = "chat.attach.preview_too_large"
_UNREADABLE_KEY = "chat.attach.preview_unreadable"

_BUILTIN_DATE_FORMAT_IDS = frozenset({*range(14, 23), *range(45, 48)})
_OFFICE_NAMESPACE_PREFIX = "{"


class AttachmentPreviewError(Exception):
    """Raised when a preview cannot be produced.

    ``status_code`` is the HTTP status the route should return and
    ``message_key`` is the i18n key used for the error detail.
    """

    def __init__(self, status_code: int, message_key: str) -> None:
        self.status_code = status_code
        self.message_key = message_key
        super().__init__(message_key)


def _unreadable() -> AttachmentPreviewError:
    return AttachmentPreviewError(422, _UNREADABLE_KEY)


# ── XML / zip helpers ───────────────────────────────────────────────


def _local(name: str) -> str:
    """Return an XML tag or attribute name without its namespace."""
    if _OFFICE_NAMESPACE_PREFIX in name:
        return name.rsplit("}", 1)[-1]
    return name


def _attr(element: ET.Element | None, name: str) -> str | None:
    if element is None:
        return None
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return None


def _rel_id(element: ET.Element | None) -> str | None:
    """Return the namespaced relationship id (``r:id``)."""
    if element is None:
        return None
    for key, value in element.attrib.items():
        if _OFFICE_NAMESPACE_PREFIX in key and _local(key) == "id":
            return value
    return None


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _children(element: ET.Element | None, name: str) -> Iterator[ET.Element]:
    if element is None:
        return
    for child in element:
        if _local(child.tag) == name:
            yield child


def _find_first(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    for node in element.iter():
        if _local(node.tag) == name:
            return node
    return None


def _parse_xml(data: bytes) -> ET.Element:
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise _unreadable()
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise _unreadable() from exc


def _normalize_member(name: str) -> str:
    cleaned = name.replace("\\", "/")
    parts = [part for part in cleaned.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise _unreadable()
    return "/".join(parts)


def _resolve_relationship_target(base_dir: str, target: str) -> str:
    target = target.replace("\\", "/")
    joined = target.lstrip("/") if target.startswith("/") else posixpath.join(base_dir, target)
    normalized = posixpath.normpath(joined)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise _unreadable()
    return _normalize_member(normalized)


class _ZipReader:
    """Read zip members while enforcing size and path safety limits."""

    def __init__(self, archive: zipfile.ZipFile) -> None:
        self.archive = archive
        self.total_bytes = 0

    def _info(self, name: str) -> zipfile.ZipInfo | None:
        try:
            return self.archive.getinfo(_normalize_member(name))
        except KeyError:
            return None

    def optional(self, name: str) -> bytes | None:
        if self._info(name) is None:
            return None
        return self.read(name)

    def read(self, name: str) -> bytes:
        member = _normalize_member(name)
        try:
            info = self.archive.getinfo(member)
        except KeyError as exc:
            raise _unreadable() from exc
        if info.flag_bits & 0x1:
            raise _unreadable()
        if info.file_size > MAX_MEMBER_SIZE:
            raise _unreadable()
        if self.total_bytes + info.file_size > MAX_TOTAL_READ:
            raise _unreadable()
        try:
            data = self.archive.read(info)
        except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
            raise _unreadable() from exc
        self.total_bytes += len(data)
        return data


def _relationships(zr: _ZipReader, path: str) -> dict[str, tuple[str | None, str]]:
    data = zr.optional(path)
    if data is None:
        return {}
    root = _parse_xml(data)
    result: dict[str, tuple[str | None, str]] = {}
    for node in root.iter():
        if _local(node.tag) != "Relationship":
            continue
        rel_id = node.get("Id")
        target = node.get("Target")
        if rel_id and target is not None:
            result[rel_id] = (node.get("Type"), target)
    return result


def _rich_text(element: ET.Element | None) -> str:
    """Join plain text and rich-text runs while ignoring phonetic hints."""
    if element is None:
        return ""
    parts: list[str] = []
    for child in element:
        kind = _local(child.tag)
        if kind == "t":
            parts.append(child.text or "")
        elif kind == "r":
            for run_child in child:
                if _local(run_child.tag) == "t":
                    parts.append(run_child.text or "")
    return "".join(parts)


# ── Spreadsheet (.xlsx) ─────────────────────────────────────────────


def _shared_strings(zr: _ZipReader) -> list[str]:
    data = zr.optional("xl/sharedStrings.xml")
    if data is None:
        return []
    root = _parse_xml(data)
    return [_rich_text(si) for si in _children(root, "si")]


def _is_date_format(num_fmt_id: int, custom_formats: dict[int, str]) -> bool:
    if num_fmt_id in _BUILTIN_DATE_FORMAT_IDS:
        return True
    code = custom_formats.get(num_fmt_id)
    if code is None:
        return False
    # Drop colour/condition brackets and literal quoted sections before
    # looking for date/time placeholders.
    stripped = re.sub(r"\[[^\]]*\]", "", code)
    stripped = re.sub(r'"[^"]*"', "", stripped)
    return any(char in stripped.lower() for char in "ydhm")


def _date_formats(zr: _ZipReader) -> list[bool]:
    data = zr.optional("xl/styles.xml")
    if data is None:
        return []
    root = _parse_xml(data)
    custom_formats: dict[int, str] = {}
    for node in root.iter():
        if _local(node.tag) == "numFmt":
            try:
                fmt_id = int(_attr(node, "numFmtId") or "0")
            except ValueError:
                continue
            custom_formats[fmt_id] = _attr(node, "formatCode") or ""
    cell_xfs = _find_first(root, "cellXfs")
    formats: list[bool] = []
    for xf in _children(cell_xfs, "xf"):
        try:
            fmt_id = int(_attr(xf, "numFmtId") or "0")
        except ValueError:
            fmt_id = 0
        formats.append(_is_date_format(fmt_id, custom_formats))
    return formats


def _column_index(reference: str | None) -> int | None:
    if not reference:
        return None
    match = re.match(r"([A-Za-z]+)", reference)
    if match is None:
        return None
    index = 0
    for char in match.group(1).upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _number_text(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return repr(value)


def _date_text(value: float) -> str:
    if value < 0:
        return _number_text(value)
    days = int(value // 1)
    minutes = round((value - days) * 1440)
    if minutes >= 1440:
        days += 1
        minutes -= 1440
    hours, minutes = divmod(minutes, 60)
    if days == 0:
        return f"{hours:02d}:{minutes:02d}"
    moment = dt.datetime(1899, 12, 30) + dt.timedelta(days=days)
    rendered = moment.strftime("%Y-%m-%d")
    if minutes or hours:
        rendered += f" {hours:02d}:{minutes:02d}"
    return rendered


def _cell_text(
    cell: ET.Element,
    shared_strings: list[str],
    date_format_flags: list[bool],
) -> str:
    cell_type = _attr(cell, "t")
    value_node = _child(cell, "v")
    raw_value = value_node.text if value_node is not None else None

    if cell_type == "inlineStr":
        return _rich_text(_child(cell, "is"))
    if cell_type == "s":
        if raw_value is None or raw_value.strip() == "":
            return ""
        try:
            return shared_strings[int(raw_value)]
        except (ValueError, IndexError):
            return ""
    if cell_type == "str":
        return raw_value or ""
    if cell_type == "b":
        if raw_value is None:
            return ""
        return "TRUE" if raw_value.strip().lower() in {"1", "true"} else "FALSE"
    if cell_type == "e":
        return raw_value or ""
    if cell_type == "d":
        return raw_value or ""

    if raw_value is None or raw_value.strip() == "":
        return ""
    try:
        numeric = float(raw_value)
    except ValueError:
        return raw_value
    try:
        style_index = int(_attr(cell, "s") or "0")
    except ValueError:
        style_index = 0
    if 0 <= style_index < len(date_format_flags) and date_format_flags[style_index]:
        return _date_text(numeric)
    return _number_text(numeric)


def _sheet_rows(
    zr: _ZipReader,
    name: str,
    shared_strings: list[str],
    date_format_flags: list[bool],
) -> tuple[list[list[str]], bool]:
    root = _parse_xml(zr.read(name))
    sheet_data = _find_first(root, "sheetData")
    rows: list[list[str]] = []
    truncated = False
    for row_index, row in enumerate(_children(sheet_data, "row")):
        if row_index >= MAX_SHEET_ROWS:
            truncated = True
            break
        values: list[str] = []
        next_column = 0
        for cell in _children(row, "c"):
            column = _column_index(_attr(cell, "r"))
            if column is None:
                column = next_column
            if column >= MAX_SHEET_COLUMNS:
                truncated = True
                continue
            while len(values) < column:
                values.append("")
            text = _cell_text(cell, shared_strings, date_format_flags)
            if len(values) == column:
                values.append(text)
            else:
                values[column] = text
            next_column = column + 1
        while values and values[-1] == "":
            values.pop()
        rows.append(values)
    return rows, truncated


def _xlsx_preview(zr: _ZipReader) -> dict[str, Any]:
    workbook = _parse_xml(zr.read("xl/workbook.xml"))
    relationships = _relationships(zr, "xl/_rels/workbook.xml.rels")
    shared_strings = _shared_strings(zr)
    date_format_flags = _date_formats(zr)

    sheets: list[dict[str, Any]] = []
    truncated = False
    sheets_node = _find_first(workbook, "sheets")
    for index, sheet_node in enumerate(_children(sheets_node, "sheet")):
        if index >= MAX_SHEETS:
            truncated = True
            break
        rel_id = _rel_id(sheet_node)
        relationship = relationships.get(rel_id or "")
        if relationship is None:
            raise _unreadable()
        sheet_path = _resolve_relationship_target("xl", relationship[1])
        rows, sheet_truncated = _sheet_rows(zr, sheet_path, shared_strings, date_format_flags)
        truncated = truncated or sheet_truncated
        sheets.append(
            {
                "name": _attr(sheet_node, "name") or f"Sheet{index + 1}",
                "rows": rows,
                "truncated": sheet_truncated,
            }
        )
    return {"kind": "sheets", "truncated": truncated, "sheets": sheets}


# ── Word document (.docx) ───────────────────────────────────────────


def _docx_styles(zr: _ZipReader) -> dict[str, str]:
    data = zr.optional("word/styles.xml")
    if data is None:
        return {}
    root = _parse_xml(data)
    styles: dict[str, str] = {}
    for node in root.iter():
        if _local(node.tag) != "style":
            continue
        style_id = _attr(node, "styleId")
        if not style_id:
            continue
        styles[style_id] = _attr(_child(node, "name"), "val") or ""
    return styles


def _docx_numbering(zr: _ZipReader) -> dict[str, dict[int, str]]:
    data = zr.optional("word/numbering.xml")
    if data is None:
        return {}
    root = _parse_xml(data)
    abstract_levels: dict[str, dict[int, str]] = {}
    for node in root.iter():
        if _local(node.tag) != "abstractNum":
            continue
        abstract_id = _attr(node, "abstractNumId")
        if abstract_id is None:
            continue
        levels: dict[int, str] = {}
        for level_node in _children(node, "lvl"):
            try:
                level = int(_attr(level_node, "ilvl") or "0")
            except ValueError:
                level = 0
            levels[level] = _attr(_child(level_node, "numFmt"), "val") or "bullet"
        abstract_levels[abstract_id] = levels
    numbering: dict[str, dict[int, str]] = {}
    for node in root.iter():
        if _local(node.tag) != "num":
            continue
        num_id = _attr(node, "numId")
        abstract_id = _attr(_child(node, "abstractNumId"), "val")
        if num_id is None or abstract_id is None:
            continue
        numbering[num_id] = abstract_levels.get(abstract_id, {})
    return numbering


def _toggle_value(element: ET.Element | None) -> bool:
    if element is None:
        return False
    value = _attr(element, "val")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "none", "off"}


def _docx_run_text(run: ET.Element) -> str:
    parts: list[str] = []
    for node in run.iter():
        kind = _local(node.tag)
        if kind == "t":
            parts.append(node.text or "")
        elif kind == "br" or kind == "cr":
            parts.append("\n")
        elif kind == "tab":
            parts.append("\t")
    return "".join(parts)


def _docx_runs(paragraph: ET.Element) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for node in paragraph.iter():
        if _local(node.tag) != "r":
            continue
        run_properties = _child(node, "rPr")
        text = _docx_run_text(node)
        if not text:
            continue
        runs.append(
            {
                "text": text,
                "bold": _toggle_value(_child(run_properties, "b")),
                "italic": _toggle_value(_child(run_properties, "i")),
                "underline": _toggle_value(_child(run_properties, "u")),
            }
        )
    return runs


def _docx_paragraph_style(
    paragraph: ET.Element,
    styles: dict[str, str],
) -> str | None:
    paragraph_properties = _child(paragraph, "pPr")
    style_id = _attr(_child(paragraph_properties, "pStyle"), "val")
    if not style_id:
        return None
    candidates = [style_id.lower(), styles.get(style_id, "").strip().lower()]
    for candidate in candidates:
        if not candidate:
            continue
        match = re.match(r"heading\s*([1-6])$", candidate)
        if match is None:
            match = re.match(r"見出し\s*([1-6])$", candidate)
        if match is not None:
            return f"heading{match.group(1)}"
        if candidate in {"title", "タイトル"}:
            return "title"
    return None


def _docx_list(paragraph: ET.Element, numbering: dict[str, dict[int, str]]) -> dict[str, Any] | None:
    paragraph_properties = _child(paragraph, "pPr")
    number_properties = _child(paragraph_properties, "numPr")
    if number_properties is None:
        return None
    try:
        level = int(_attr(_child(number_properties, "ilvl"), "val") or "0")
    except ValueError:
        level = 0
    num_id = _attr(_child(number_properties, "numId"), "val")
    levels = numbering.get(num_id or "", {})
    ordered = levels.get(level, "bullet") != "bullet"
    return {"level": level, "ordered": ordered}


def _docx_paragraph(
    paragraph: ET.Element,
    styles: dict[str, str],
    numbering: dict[str, dict[int, str]],
) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "runs": _docx_runs(paragraph),
        "style": _docx_paragraph_style(paragraph, styles),
        "list": _docx_list(paragraph, numbering),
    }


def _docx_table(table: ET.Element) -> tuple[dict[str, Any], bool]:
    rows: list[list[str]] = []
    truncated = False
    for row_index, row in enumerate(_children(table, "tr")):
        if row_index >= MAX_TABLE_ROWS:
            truncated = True
            break
        cells: list[str] = []
        for cell in _children(row, "tc"):
            paragraphs = [
                "".join(run["text"] for run in _docx_runs(paragraph))
                for paragraph in cell.iter()
                if _local(paragraph.tag) == "p"
            ]
            cells.append("\n".join(paragraphs))
        rows.append(cells)
    return {"type": "table", "rows": rows}, truncated


def _docx_preview(zr: _ZipReader) -> dict[str, Any]:
    document = _parse_xml(zr.read("word/document.xml"))
    styles = _docx_styles(zr)
    numbering = _docx_numbering(zr)
    body = _find_first(document, "body")
    blocks: list[dict[str, Any]] = []
    truncated = False
    body_children = list(body) if body is not None else []
    for node in body_children:
        kind = _local(node.tag)
        if kind not in {"p", "tbl"}:
            continue
        if len(blocks) >= MAX_DOC_BLOCKS:
            truncated = True
            break
        if kind == "p":
            blocks.append(_docx_paragraph(node, styles, numbering))
        else:
            table, table_truncated = _docx_table(node)
            truncated = truncated or table_truncated
            blocks.append(table)
    return {"kind": "document", "truncated": truncated, "blocks": blocks}


# ── Presentation (.pptx) ────────────────────────────────────────────


def _shape_paragraphs(shape: ET.Element) -> list[str]:
    paragraphs: list[str] = []
    for paragraph in shape.iter():
        if _local(paragraph.tag) != "p":
            continue
        parts: list[str] = []
        for node in paragraph.iter():
            kind = _local(node.tag)
            if kind == "t":
                parts.append(node.text or "")
            elif kind == "br":
                parts.append("\n")
        text = "".join(parts)
        if text:
            paragraphs.append(text)
    return paragraphs


def _shape_text(shape: ET.Element) -> str:
    return "\n".join(_shape_paragraphs(shape))


def _shape_placeholder_type(shape: ET.Element) -> str | None:
    placeholder = _find_first(shape, "ph")
    if placeholder is None:
        return None
    return _attr(placeholder, "type")


def _slide_shape_texts(slide: ET.Element) -> list[tuple[str | None, str]]:
    return [(_shape_placeholder_type(shape), _shape_text(shape)) for shape in slide.iter() if _local(shape.tag) == "sp"]


def _slide_paragraph_texts(slide: ET.Element) -> list[str]:
    texts: list[str] = []
    for shape in slide.iter():
        if _local(shape.tag) == "sp":
            texts.extend(_shape_paragraphs(shape))
    return texts


def _notes_text(zr: _ZipReader, slide_path: str) -> str:
    slide_dir = posixpath.dirname(slide_path)
    slide_name = posixpath.basename(slide_path)
    rels_path = posixpath.join(slide_dir, "_rels", f"{slide_name}.rels")
    relationships = _relationships(zr, rels_path)
    notes_target = next(
        (target for rel_type, target in relationships.values() if (rel_type or "").lower().endswith("/notesslide")),
        None,
    )
    if notes_target is None:
        notes_target = next((target for _, target in relationships.values() if "notesslide" in target.lower()), None)
    if notes_target is None:
        return ""
    notes_path = _resolve_relationship_target(slide_dir, notes_target)
    data = zr.optional(notes_path)
    if data is None:
        return ""
    root = _parse_xml(data)
    parts: list[str] = []
    for placeholder_type, text in _slide_shape_texts(root):
        if placeholder_type in {"sldNum", "hdr", "ftr", "dt"}:
            continue
        if text:
            parts.append(text)
    return "\n".join(parts)


def _pptx_preview(zr: _ZipReader) -> dict[str, Any]:
    presentation = _parse_xml(zr.read("ppt/presentation.xml"))
    relationships = _relationships(zr, "ppt/_rels/presentation.xml.rels")
    slide_id_list = _find_first(presentation, "sldIdLst")

    slides: list[dict[str, Any]] = []
    truncated = False
    for index, slide_id in enumerate(_children(slide_id_list, "sldId")):
        if index >= MAX_SLIDES:
            truncated = True
            break
        relationship = relationships.get(_rel_id(slide_id) or "")
        if relationship is None:
            raise _unreadable()
        slide_path = _resolve_relationship_target("ppt", relationship[1])
        slide = _parse_xml(zr.read(slide_path))
        shape_texts = _slide_shape_texts(slide)
        texts = _slide_paragraph_texts(slide)
        title = next(
            (text for placeholder, text in shape_texts if placeholder in {"title", "ctrTitle"} and text),
            texts[0] if texts else "",
        )
        # The title is shown on its own; do not repeat it as the first body line.
        if texts and texts[0] == title:
            texts = texts[1:]
        slides.append(
            {
                "index": index + 1,
                "title": title,
                "texts": texts,
                "notes": _notes_text(zr, slide_path),
            }
        )
    return {"kind": "slides", "truncated": truncated, "slides": slides}


# ── Public API ──────────────────────────────────────────────────────


def _convert(path: Path, suffix: str) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            if any(info.flag_bits & 0x1 for info in archive.infolist()):
                raise _unreadable()
            reader = _ZipReader(archive)
            if suffix in {".xlsx", ".xlsm"}:
                payload = _xlsx_preview(reader)
            elif suffix == ".docx":
                payload = _docx_preview(reader)
            else:
                payload = _pptx_preview(reader)
    except zipfile.BadZipFile as exc:
        raise _unreadable() from exc
    except OSError as exc:
        raise _unreadable() from exc
    return {**payload, "name": path.name}


@lru_cache(maxsize=16)
def _convert_cached(path: str, mtime_ns: int, size: int) -> dict[str, Any]:
    del mtime_ns, size  # part of the cache key only
    resolved = Path(path)
    return _convert(resolved, resolved.suffix.lower())


def preview_attachment(path: Path) -> dict[str, Any]:
    """Return a structured preview for *path* or raise AttachmentPreviewError."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise AttachmentPreviewError(415, _UNSUPPORTED_KEY)
    try:
        stat = path.stat()
    except OSError as exc:
        raise _unreadable() from exc
    if stat.st_size > MAX_FILE_SIZE:
        raise AttachmentPreviewError(413, _TOO_LARGE_KEY)
    return _convert_cached(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
