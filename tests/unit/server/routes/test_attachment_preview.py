"""Unit tests for attachment preview (xlsx/docx/pptx) and preview API."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

_XMLNS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_RELNS = "http://schemas.openxmlformats.org/package/2006/relationships"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _make_app(animas_dir: Path):
    from fastapi import FastAPI

    from server.routes.assets import create_assets_router

    app = FastAPI()
    app.state.animas_dir = animas_dir
    app.state.ws_manager = MagicMock()
    app.state.ws_manager.broadcast = AsyncMock()
    app.include_router(create_assets_router(), prefix="/api")
    return app


def _write_zip(path: Path, members: dict[str, bytes | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def _attachment_dir(animas_dir: Path, anima: str = "alice") -> Path:
    directory = animas_dir / anima / "attachments"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def _get_preview(animas_dir: Path, filename: str):
    transport = ASGITransport(app=_make_app(animas_dir))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(f"/api/animas/alice/attachments/{filename}/preview")


def _xlsx_members(
    *,
    sheets: list[tuple[str, str]] | None = None,
    shared_strings: str | None = None,
    styles: str | None = None,
) -> dict[str, str]:
    sheets = sheets or [("First", _sheet_first()), ("Second", _sheet_second())]
    workbook_sheets = "".join(
        f'<sheet name="{name}" sheetId="{index + 1}" r:id="rId{index + 1}"/>' for index, (name, _) in enumerate(sheets)
    )
    relationships = "".join(
        f'<Relationship Id="rId{index + 1}" Type="{_RELNS}/worksheet" Target="worksheets/sheet{index + 1}.xml"/>'
        for index in range(len(sheets))
    )
    members = {
        "xl/workbook.xml": (
            f'<?xml version="1.0"?><workbook xmlns="{_XMLNS}" xmlns:r="{_RELNS}">'
            f"<sheets>{workbook_sheets}</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<?xml version="1.0"?><Relationships xmlns="{_PKG_RELNS}">{relationships}</Relationships>'
        ),
    }
    for index, (_, sheet_xml) in enumerate(sheets):
        members[f"xl/worksheets/sheet{index + 1}.xml"] = sheet_xml
    if shared_strings is not None:
        members["xl/sharedStrings.xml"] = shared_strings
    if styles is not None:
        members["xl/styles.xml"] = styles
    return members


def _sheet_first() -> str:
    return (
        f'<?xml version="1.0"?><worksheet xmlns="{_XMLNS}"><sheetData>'
        '<row r="1">'
        '<c r="A1" t="s"><v>0</v></c>'
        '<c r="B1" t="inlineStr"><is><t>Inline</t></is></c>'
        '<c r="C1"><v>42</v></c>'
        '<c r="D1" t="b"><v>1</v></c>'
        '<c r="E1"><f>1+1</f><v>2</v></c>'
        "</row>"
        '<row r="2">'
        '<c r="A2" s="1"><v>45000</v></c>'
        '<c r="B2" s="2"><v>45000.5</v></c>'
        "</row>"
        '<row r="3">'
        '<c r="C3" t="inlineStr"><is><t>c</t></is></c>'
        "</row>"
        '<row r="4">'
        '<c r="A4" t="inlineStr"><is><t>a</t></is></c>'
        '<c r="C4" t="inlineStr"><is><t></t></is></c>'
        "</row>"
        '<row r="5">'
        '<c r="A5" t="e"><v>#DIV/0!</v></c>'
        '<c r="B5" t="b"><v>0</v></c>'
        '<c r="C5"><v>3.5</v></c>'
        '<c r="D5" t="str"><f>A1</f><v>cached</v></c>'
        "</row>"
        '<row r="6">'
        '<c r="A6"><v>2.50</v></c>'
        "</row>"
        "</sheetData></worksheet>"
    )


def _sheet_second() -> str:
    return (
        f'<?xml version="1.0"?><worksheet xmlns="{_XMLNS}"><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Second</t></is></c></row>'
        "</sheetData></worksheet>"
    )


def _shared_strings() -> str:
    return (
        f'<?xml version="1.0"?><sst xmlns="{_XMLNS}">'
        "<si><t>Hello</t></si>"
        "<si><r><t>Rich</t></r><r><t> Text</t></r></si>"
        "</sst>"
    )


def _styles() -> str:
    return (
        f'<?xml version="1.0"?><styleSheet xmlns="{_XMLNS}">'
        '<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy/mm/dd hh:mm"/></numFmts>'
        '<cellXfs count="3">'
        '<xf numFmtId="0"/>'
        '<xf numFmtId="14"/>'
        '<xf numFmtId="164"/>'
        "</cellXfs></styleSheet>"
    )


def _docx_document(body: str) -> str:
    return f'<?xml version="1.0"?><w:document xmlns:w="{_W_NS}" xmlns:r="{_RELNS}"><w:body>{body}</w:body></w:document>'


def _docx_members(body: str) -> dict[str, str]:
    styles = (
        f'<?xml version="1.0"?><w:styles xmlns:w="{_W_NS}">'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>'
        "</w:styles>"
    )
    numbering = (
        f'<?xml version="1.0"?><w:numbering xmlns:w="{_W_NS}">'
        '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>'
        '<w:abstractNum w:abstractNumId="1">'
        '<w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>'
        '<w:lvl w:ilvl="1"><w:numFmt w:val="lowerLetter"/></w:lvl>'
        "</w:abstractNum>"
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
        "</w:numbering>"
    )
    return {
        "word/document.xml": _docx_document(body),
        "word/styles.xml": styles,
        "word/numbering.xml": numbering,
    }


def _paragraph(text: str, properties: str = "") -> str:
    return f"<w:p><w:pPr>{properties}</w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>"


def _pptx_members(slide_count: int = 2, notes: bool = True) -> dict[str, str]:
    slide_ids = "".join(f'<p:sldId id="{255 + index}" r:id="rId{index}"/>' for index in range(1, slide_count + 1))
    presentation_rels = "".join(
        f'<Relationship Id="rId{index}" Type="{_RELNS}/slide" Target="slides/slide{index}.xml"/>'
        for index in range(1, slide_count + 1)
    )
    members = {
        "ppt/presentation.xml": (
            f'<?xml version="1.0"?><p:presentation xmlns:p="{_P_NS}" xmlns:r="{_RELNS}">'
            f"<p:sldIdLst>{slide_ids}</p:sldIdLst></p:presentation>"
        ),
        "ppt/_rels/presentation.xml.rels": (
            f'<?xml version="1.0"?><Relationships xmlns="{_PKG_RELNS}">{presentation_rels}</Relationships>'
        ),
    }
    for index in range(1, slide_count + 1):
        title = f"Title {index}"
        body = f"Body {index}"
        members[f"ppt/slides/slide{index}.xml"] = (
            f'<?xml version="1.0"?><p:sld xmlns:p="{_P_NS}" xmlns:a="{_A_NS}"><p:cSld><p:spTree>'
            '<p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
            f"<p:txBody><a:p><a:r><a:t>{title}</a:t></a:r></a:p></p:txBody></p:sp>"
            "<p:sp><p:nvSpPr><p:nvPr/></p:nvSpPr>"
            f"<p:txBody><a:p><a:r><a:t>{body}</a:t></a:r></a:p></p:txBody></p:sp>"
            "</p:spTree></p:cSld></p:sld>"
        )
    if notes:
        members["ppt/slides/_rels/slide1.xml.rels"] = (
            f'<?xml version="1.0"?><Relationships xmlns="{_PKG_RELNS}">'
            f'<Relationship Id="rId1" Type="{_RELNS}/notesSlide" Target="../notesSlides/notesSlide1.xml"/>'
            "</Relationships>"
        )
        members["ppt/notesSlides/notesSlide1.xml"] = (
            f'<?xml version="1.0"?><p:notes xmlns:p="{_P_NS}" xmlns:a="{_A_NS}"><p:cSld><p:spTree>'
            '<p:sp><p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr>'
            "<p:txBody><a:p><a:r><a:t>Speaker notes</a:t></a:r></a:p></p:txBody></p:sp>"
            '<p:sp><p:nvSpPr><p:nvPr><p:ph type="sldNum"/></p:nvPr></p:nvSpPr>'
            "<p:txBody><a:p><a:r><a:t>1</a:t></a:r></a:p></p:txBody></p:sp>"
            "</p:spTree></p:cSld></p:notes>"
        )
    return members


class TestXlsxPreview:
    async def test_cells_dates_and_sheet_order(self, tmp_path):
        animas_dir = tmp_path / "animas"
        _write_zip(
            _attachment_dir(animas_dir) / "book.xlsx",
            _xlsx_members(shared_strings=_shared_strings(), styles=_styles()),
        )

        response = await _get_preview(animas_dir, "book.xlsx")

        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "sheets"
        assert data["name"] == "book.xlsx"
        assert data["truncated"] is False
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "no-store"
        assert [sheet["name"] for sheet in data["sheets"]] == ["First", "Second"]

        rows = data["sheets"][0]["rows"]
        assert rows[0] == ["Hello", "Inline", "42", "TRUE", "2"]
        assert rows[1] == ["2023-03-15", "2023-03-15 12:00"]
        assert rows[2] == ["", "", "c"]
        assert rows[3] == ["a"]
        assert rows[4] == ["#DIV/0!", "FALSE", "3.5", "cached"]
        assert rows[5] == ["2.5"]
        assert data["sheets"][0]["truncated"] is False
        assert data["sheets"][1]["rows"] == [["Second"]]

    async def test_rich_shared_strings(self, tmp_path):
        animas_dir = tmp_path / "animas"
        members = _xlsx_members(shared_strings=_shared_strings(), styles=_styles())
        members["xl/worksheets/sheet1.xml"] = (
            f'<?xml version="1.0"?><worksheet xmlns="{_XMLNS}"><sheetData>'
            '<row r="1"><c r="A1" t="s"><v>1</v></c></row>'
            "</sheetData></worksheet>"
        )
        _write_zip(_attachment_dir(animas_dir) / "rich.xlsx", members)

        response = await _get_preview(animas_dir, "rich.xlsx")

        assert response.json()["sheets"][0]["rows"] == [["Rich Text"]]

    async def test_row_limit_truncates(self, tmp_path):
        rows = "".join(f'<row r="{index + 1}"><c r="A{index + 1}"><v>{index}</v></c></row>' for index in range(501))
        sheet = f'<?xml version="1.0"?><worksheet xmlns="{_XMLNS}"><sheetData>{rows}</sheetData></worksheet>'
        animas_dir = tmp_path / "animas"
        _write_zip(
            _attachment_dir(animas_dir) / "long.xlsx",
            _xlsx_members(sheets=[("Long", sheet)], shared_strings=_shared_strings(), styles=_styles()),
        )

        response = await _get_preview(animas_dir, "long.xlsx")

        assert response.status_code == 200
        data = response.json()
        assert data["truncated"] is True
        assert data["sheets"][0]["truncated"] is True
        assert len(data["sheets"][0]["rows"]) == 500


class TestDocxPreview:
    async def test_paragraphs_lists_table_and_hyperlinks(self, tmp_path):
        body = (
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            "<w:r><w:rPr><w:b/></w:rPr><w:t>Header</w:t></w:r></w:p>"
            '<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>Doc title</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:pStyle w:val="heading2"/></w:pPr><w:r><w:t>Sub</w:t></w:r></w:p>'
            '<w:p><w:r><w:rPr><w:i/><w:u w:val="single"/></w:rPr><w:t>Italic</w:t></w:r>'
            '<w:r><w:t xml:space="preserve"> plain</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
            "<w:r><w:t>Bullet</w:t></w:r></w:p>"
            '<w:p><w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="2"/></w:numPr></w:pPr>'
            "<w:r><w:t>Numbered</w:t></w:r></w:p>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell1</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Cell1b</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>Cell2</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
            "<w:p><w:r><w:t>line1</w:t><w:br/><w:t>line2</w:t><w:tab/><w:t>tab</w:t></w:r></w:p>"
            '<w:p><w:hyperlink r:id="rId1"><w:r><w:t>Linked</w:t></w:r></w:hyperlink></w:p>'
        )
        animas_dir = tmp_path / "animas"
        _write_zip(_attachment_dir(animas_dir) / "doc.docx", _docx_members(body))

        response = await _get_preview(animas_dir, "doc.docx")

        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "document"
        assert data["name"] == "doc.docx"
        assert data["truncated"] is False
        blocks = data["blocks"]

        assert blocks[0]["style"] == "heading1"
        assert blocks[0]["runs"] == [{"text": "Header", "bold": True, "italic": False, "underline": False}]
        assert blocks[1]["style"] == "title"
        assert blocks[2]["style"] == "heading2"
        assert blocks[3]["style"] is None
        assert blocks[3]["runs"][0] == {
            "text": "Italic",
            "bold": False,
            "italic": True,
            "underline": True,
        }
        assert blocks[3]["runs"][1]["text"] == " plain"
        assert blocks[4]["list"] == {"level": 0, "ordered": False}
        assert blocks[5]["list"] == {"level": 1, "ordered": True}
        assert blocks[6] == {"type": "table", "rows": [["Cell1\nCell1b", "Cell2"]]}
        assert blocks[7]["runs"][0]["text"] == "line1\nline2\ttab"
        assert blocks[8]["runs"][0]["text"] == "Linked"

    async def test_block_limit_truncates(self, tmp_path):
        body = "".join(_paragraph(f"p{index}") for index in range(2001))
        animas_dir = tmp_path / "animas"
        _write_zip(_attachment_dir(animas_dir) / "many.docx", _docx_members(body))

        response = await _get_preview(animas_dir, "many.docx")

        data = response.json()
        assert data["truncated"] is True
        assert len(data["blocks"]) == 2000

    async def test_table_row_limit_truncates(self, tmp_path):
        rows = "".join("<w:tr><w:tc><w:p><w:r><w:t>x</w:t></w:r></w:p></w:tc></w:tr>" for _ in range(201))
        body = f"<w:tbl>{rows}</w:tbl>"
        animas_dir = tmp_path / "animas"
        _write_zip(_attachment_dir(animas_dir) / "table.docx", _docx_members(body))

        response = await _get_preview(animas_dir, "table.docx")

        data = response.json()
        assert data["truncated"] is True
        assert len(data["blocks"][0]["rows"]) == 200


class TestPptxPreview:
    async def test_slide_order_title_texts_and_notes(self, tmp_path):
        animas_dir = tmp_path / "animas"
        _write_zip(_attachment_dir(animas_dir) / "deck.pptx", _pptx_members())

        response = await _get_preview(animas_dir, "deck.pptx")

        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "slides"
        assert data["name"] == "deck.pptx"
        assert data["truncated"] is False
        assert [slide["index"] for slide in data["slides"]] == [1, 2]
        assert data["slides"][0]["title"] == "Title 1"
        assert data["slides"][0]["texts"] == ["Body 1"]
        assert data["slides"][0]["notes"] == "Speaker notes"
        assert data["slides"][1]["title"] == "Title 2"
        assert data["slides"][1]["notes"] == ""

    async def test_slide_limit_truncates(self, tmp_path):
        animas_dir = tmp_path / "animas"
        _write_zip(
            _attachment_dir(animas_dir) / "long.pptx",
            _pptx_members(slide_count=201, notes=False),
        )

        response = await _get_preview(animas_dir, "long.pptx")

        data = response.json()
        assert data["truncated"] is True
        assert len(data["slides"]) == 200


class TestPreviewErrors:
    async def test_unsupported_extension_returns_415(self, tmp_path):
        animas_dir = tmp_path / "animas"
        (_attachment_dir(animas_dir) / "notes.txt").write_text("hello", encoding="utf-8")

        response = await _get_preview(animas_dir, "notes.txt")

        assert response.status_code == 415
        assert response.json()["detail"]

    async def test_invalid_filename_returns_400(self, tmp_path):
        animas_dir = tmp_path / "animas"
        _attachment_dir(animas_dir)

        response = await _get_preview(animas_dir, "bad%5Cname.xlsx")

        assert response.status_code == 400

    async def test_missing_file_returns_404(self, tmp_path):
        animas_dir = tmp_path / "animas"
        _attachment_dir(animas_dir)

        response = await _get_preview(animas_dir, "missing.xlsx")

        assert response.status_code == 404
        assert response.json()["detail"] == "Attachment not found"

    async def test_missing_anima_returns_404(self, tmp_path):
        animas_dir = tmp_path / "animas"

        response = await _get_preview(animas_dir, "missing.xlsx")

        assert response.status_code == 404
        assert response.json()["detail"] == "Anima not found: alice"

    async def test_broken_zip_returns_422(self, tmp_path):
        animas_dir = tmp_path / "animas"
        (_attachment_dir(animas_dir) / "broken.xlsx").write_bytes(b"not a zip")

        response = await _get_preview(animas_dir, "broken.xlsx")

        assert response.status_code == 422

    async def test_encrypted_zip_returns_422(self, tmp_path):
        path = _attachment_dir(tmp_path / "animas") / "encrypted.xlsx"
        _write_zip(path, _xlsx_members(shared_strings=_shared_strings(), styles=_styles()))
        data = path.read_bytes()
        central = data.rfind(b"PK\x01\x02")
        flags = int.from_bytes(data[central + 8 : central + 10], "little") | 0x1
        path.write_bytes(data[: central + 8] + flags.to_bytes(2, "little") + data[central + 10 :])

        response = await _get_preview(tmp_path / "animas", "encrypted.xlsx")

        assert response.status_code == 422

    async def test_doctype_xml_returns_422(self, tmp_path):
        animas_dir = tmp_path / "animas"
        members = _xlsx_members(shared_strings=_shared_strings(), styles=_styles())
        members["xl/workbook.xml"] = (
            '<?xml version="1.0"?><!DOCTYPE workbook><workbook xmlns='
            f'"{_XMLNS}" xmlns:r="{_RELNS}"><sheets></sheets></workbook>'
        )
        _write_zip(_attachment_dir(animas_dir) / "doctype.xlsx", members)

        response = await _get_preview(animas_dir, "doctype.xlsx")

        assert response.status_code == 422

    async def test_broken_xml_returns_422(self, tmp_path):
        animas_dir = tmp_path / "animas"
        members = _xlsx_members(shared_strings=_shared_strings(), styles=_styles())
        members["xl/workbook.xml"] = "<workbook><sheets>"
        _write_zip(_attachment_dir(animas_dir) / "badxml.xlsx", members)

        response = await _get_preview(animas_dir, "badxml.xlsx")

        assert response.status_code == 422

    async def test_oversized_member_returns_422(self, tmp_path):
        path = _attachment_dir(tmp_path / "animas") / "huge.xlsx"
        _write_zip(path, {"xl/workbook.xml": "<workbook/>"})
        data = path.read_bytes()
        central = data.find(b"PK\x01\x02")
        fake_size = (30 * 1024 * 1024 + 1).to_bytes(4, "little")
        path.write_bytes(data[: central + 24] + fake_size + data[central + 28 :])

        response = await _get_preview(tmp_path / "animas", "huge.xlsx")

        assert response.status_code == 422

    async def test_file_too_large_returns_413(self, tmp_path):
        animas_dir = tmp_path / "animas"
        path = _attachment_dir(animas_dir) / "big.xlsx"
        with path.open("wb") as handle:
            handle.truncate(50 * 1024 * 1024 + 1)

        response = await _get_preview(animas_dir, "big.xlsx")

        assert response.status_code == 413
