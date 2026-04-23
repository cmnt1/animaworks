#!/usr/bin/env python3
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Migrate Notion T_Products DB entries to Obsidian `_products/` Vault layout.

Usage:
    python scripts/migrate_notion_tproducts_to_obsidian.py [--dry-run] \
        [--database-id <uuid>] [--vault <path>]

Default database id: `b3319880-9617-40cb-b048-4a66d3def1a8` (URL slug hyphenated).
Default vault root:  `E:/OneDriveBiz/Obsidian/_products`.

Behaviour:
- Pulls every page in the T_Products DB (paginated).
- Converts each page to an Obsidian main markdown file under
  `_products/<Category>/P-<id:05d>_<slug>.md` with the frontmatter schema the
  `obsidian-product` skill uses.
- Downloads any `添付ファイル` files into the same category folder as
  `P-<id>_<slug>_<filename>` (frontmatter `type: product_asset`).
- Preserves the original Notion `userDefined:ID` as the Obsidian `id`, and keeps
  the Notion page id as `legacy_notion_id`.
- Idempotent: skips pages whose target file already exists.

This is a one-shot migration helper, not a long-lived tool.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure the animaworks package is importable when running this script standalone
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.tools._base import get_credential  # noqa: E402
from core.tools.notion import NotionClient  # noqa: E402


DEFAULT_DATABASE_ID = "b3319880-9617-40cb-b048-4a66d3def1a8"
DEFAULT_VAULT_ROOT = Path("E:/OneDriveBiz/Obsidian/_products")

CATEGORY_MAP = {
    "General": "General",
    "Finance": "Finance",
    "Affiliate": "Affiliate",
    "Property": "Property",
    "経営": "Business",
    "Business": "Business",
}

VALID_CATEGORIES = {"General", "Finance", "Affiliate", "Property", "Business"}


# ── helpers ───────────────────────────────────────────────────────────────


def _hyphenate_uuid(raw: str) -> str:
    """Accept a bare 32-char hex id or a hyphenated uuid and normalize to hyphenated."""
    s = raw.strip().replace("-", "")
    if len(s) != 32:
        return raw
    return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"


def _rich_text_plain(rich: list[dict[str, Any]] | None) -> str:
    if not rich:
        return ""
    return "".join(r.get("plain_text", "") for r in rich)


def _prop(page: dict, name: str) -> dict | None:
    return page.get("properties", {}).get(name)


def _prop_title(page: dict, name: str) -> str:
    p = _prop(page, name) or {}
    return _rich_text_plain(p.get("title"))


def _prop_text(page: dict, name: str) -> str:
    p = _prop(page, name) or {}
    return _rich_text_plain(p.get("rich_text"))


def _prop_select(page: dict, name: str) -> str:
    p = _prop(page, name) or {}
    sel = p.get("select") or p.get("status") or {}
    return (sel or {}).get("name", "") if isinstance(sel, dict) else ""


def _prop_date(page: dict, name: str) -> str:
    p = _prop(page, name) or {}
    d = p.get("date") or {}
    return (d or {}).get("start", "") if isinstance(d, dict) else ""


def _prop_checkbox(page: dict, name: str) -> bool:
    p = _prop(page, name) or {}
    return bool(p.get("checkbox", False))


def _prop_number(page: dict, name: str):
    p = _prop(page, name) or {}
    t = p.get("type")
    if t == "unique_id":
        uid = p.get("unique_id") or {}
        return uid.get("number")
    if t == "number":
        return p.get("number")
    return None


def _prop_files(page: dict, name: str) -> list[dict[str, str]]:
    p = _prop(page, name) or {}
    out: list[dict[str, str]] = []
    for f in p.get("files", []) or []:
        fname = f.get("name", "")
        url = ""
        if "file" in f and f["file"]:
            url = f["file"].get("url", "")
        elif "external" in f and f["external"]:
            url = f["external"].get("url", "")
        if fname and url:
            out.append({"name": fname, "url": url})
    return out


_SLUG_NONWORD = re.compile(r"[^a-z0-9]+")


def _slugify(title: str, max_len: int = 40) -> str:
    """ASCII-lowercase-hyphen slug. Empty if title has no ASCII letters."""
    if not title:
        return ""
    nfkd = unicodedata.normalize("NFKD", title)
    ascii_only = nfkd.encode("ascii", errors="ignore").decode("ascii").lower()
    slug = _SLUG_NONWORD.sub("-", ascii_only).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug


def _yaml_escape(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _write_if_absent(path: Path, content: str, dry_run: bool) -> bool:
    if path.exists():
        print(f"  SKIP (exists): {path}")
        return False
    if dry_run:
        print(f"  WOULD WRITE:  {path} ({len(content)} bytes)")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"  WROTE:        {path}")
    return True


def _download(url: str, dest: Path, dry_run: bool) -> bool:
    if dest.exists():
        print(f"  SKIP attach (exists): {dest}")
        return False
    if dry_run:
        print(f"  WOULD DOWNLOAD: {url} -> {dest}")
        return True
    try:
        import httpx
    except ImportError:
        print("  ERROR: httpx not installed; cannot download attachments", file=sys.stderr)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    print(f"  DOWNLOADED:   {dest}")
    return True


# ── core migration ────────────────────────────────────────────────────────


def _fetch_all_pages(client: NotionClient, database_id: str) -> list[dict]:
    pages: list[dict] = []
    cursor: str | None = None
    while True:
        data = client.query_database(database_id, page_size=100, start_cursor=cursor)
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return pages


def _build_main_md(page: dict, body_md: str, attachments: list[str]) -> tuple[int, str, str, str]:
    """Return (id, category, filename, full_markdown_content)."""
    title = _prop_title(page, "成果物名") or "(untitled)"
    uid = _prop_number(page, "userDefined:ID") or _prop_number(page, "ID")
    if uid is None:
        raise ValueError(f"page {page.get('id')} has no userDefined:ID")
    id_int = int(uid)
    code = f"P-{id_int:05d}"

    cat_raw = _prop_select(page, "カテゴリ") or "General"
    category = CATEGORY_MAP.get(cat_raw, "General")
    if category not in VALID_CATEGORIES:
        category = "General"

    status = _prop_select(page, "ステータス") or "未着手"
    product_type = _prop_select(page, "種別") or "その他"
    task_code = _prop_text(page, "タスクコード")
    assignee = _prop_text(page, "担当者")
    submitted = _prop_date(page, "提出日")
    remarks = _prop_text(page, "備考")
    requires_reply = _prop_checkbox(page, "要返信")
    confirmed = _prop_checkbox(page, "確認済")
    created_time = page.get("created_time", "")
    updated_time = page.get("last_edited_time", "")

    slug = _slugify(title)
    if slug:
        filename = f"{code}_{slug}.md"
    else:
        filename = f"{code}.md"

    fm_lines = [
        "---",
        "type: product",
        f"id: {id_int}",
        f"code: {_yaml_escape(code)}",
        f"title: {_yaml_escape(title)}",
        f"category: {category}",
        f"product_type: {_yaml_escape(product_type)}",
        f"status: {_yaml_escape(status)}",
        f"task_code: {_yaml_escape(task_code)}",
        f"assignee: {_yaml_escape(assignee)}",
    ]
    if submitted:
        fm_lines.append(f"submitted: {submitted}")
    else:
        fm_lines.append("submitted: ")
    fm_lines += [
        f"requires_reply: {str(requires_reply).lower()}",
        f"confirmed: {str(confirmed).lower()}",
        f"legacy_notion_id: {_yaml_escape(page.get('id', ''))}",
        f"created: {created_time}",
        f"updated: {updated_time}",
        "tags: [product]",
        "---",
        "",
        f"# {title}",
        "",
    ]

    body_section = body_md.strip()
    parts = ["\n".join(fm_lines)]
    if body_section:
        parts.append(body_section + "\n")
    if remarks.strip():
        parts.append("## 備考\n\n" + remarks.strip() + "\n")
    if attachments:
        parts.append("## 付随資料\n\n" + "\n".join(f"- [[{a}]]" for a in attachments) + "\n")

    return id_int, category, filename, "\n".join(parts).rstrip() + "\n"


def _build_attachment_md(parent_code: str, title: str, created: str, updated: str) -> str:
    lines = [
        "---",
        "type: product_asset",
        f"parent_code: {_yaml_escape(parent_code)}",
        f"title: {_yaml_escape(title)}",
        f"created: {created}",
        f"updated: {updated}",
        "tags: [product-asset]",
        "---",
        "",
        f"# {title}",
        "",
        "(attachment originally stored on Notion; downloaded by migration script)",
        "",
    ]
    return "\n".join(lines)


def migrate(database_id: str, vault_root: Path, dry_run: bool) -> None:
    token = get_credential("notion", "notion", env_var="NOTION_API_TOKEN")
    client = NotionClient(token)

    print(f"Fetching pages from database {database_id}…")
    pages = _fetch_all_pages(client, database_id)
    print(f"Found {len(pages)} pages.")

    for page in pages:
        page_id = page.get("id", "")
        print(f"\nPage {page_id}")

        # Attachment file list (filenames only; we'll download + wikilink)
        att_files = _prop_files(page, "添付ファイル")

        # Fetch body
        try:
            content = client.get_page_content(page_id)
            body_md = content.get("markdown", "")
        except Exception as e:  # noqa: BLE001
            print(f"  WARN: body fetch failed: {e}")
            body_md = ""

        # Preliminary frontmatter to know id/category/filename
        try:
            # first pass without attachment links to derive code/category/filename
            id_int, category, main_filename, _ = _build_main_md(page, body_md, attachments=[])
        except ValueError as e:
            print(f"  WARN: {e}; skipping")
            continue

        code = f"P-{id_int:05d}"
        main_stem = main_filename[:-3]  # strip .md
        dest_dir = vault_root / category
        main_path = dest_dir / main_filename

        # Downloaded attachment stems (wikilink targets)
        attachment_stems: list[str] = []

        for af in att_files:
            asset_raw = af["name"]
            asset_slug = _slugify(Path(asset_raw).stem) or "attachment"
            ext = Path(asset_raw).suffix
            attach_filename = f"{main_stem}_{asset_slug}{ext}"
            attach_path = dest_dir / attach_filename
            if ext.lower() == ".md":
                # Write wrapper md directly (content unknown; record pointer)
                mdwrap_path = dest_dir / attach_filename
                if _download(af["url"], mdwrap_path, dry_run):
                    attachment_stems.append(mdwrap_path.stem)
            else:
                # Binary: download as-is; make a sidecar .md that wikilinks the binary
                if _download(af["url"], attach_path, dry_run):
                    sidecar_stem = f"{main_stem}_{asset_slug}"
                    sidecar_path = dest_dir / f"{sidecar_stem}.md"
                    sidecar_md = _build_attachment_md(
                        parent_code=code,
                        title=asset_raw,
                        created=page.get("created_time", ""),
                        updated=page.get("last_edited_time", ""),
                    )
                    sidecar_md += f"\n[Original file]({attach_filename})\n"
                    _write_if_absent(sidecar_path, sidecar_md, dry_run)
                    attachment_stems.append(sidecar_stem)

        # Rebuild main md with attachment wikilinks and write
        _id2, _cat2, _fn2, main_md = _build_main_md(page, body_md, attachment_stems)
        _write_if_absent(main_path, main_md, dry_run)


# ── CLI ───────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not write files")
    parser.add_argument(
        "--database-id",
        default=DEFAULT_DATABASE_ID,
        help=f"Notion T_Products database id (default: {DEFAULT_DATABASE_ID})",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT_ROOT,
        help=f"Obsidian _products folder (default: {DEFAULT_VAULT_ROOT})",
    )
    args = parser.parse_args(argv)

    db_id = _hyphenate_uuid(args.database_id)
    vault_root: Path = args.vault
    if not vault_root.exists() and not args.dry_run:
        print(f"ERROR: vault root not found: {vault_root}", file=sys.stderr)
        return 2

    started = datetime.now()
    migrate(db_id, vault_root, args.dry_run)
    print(f"\nDone in {(datetime.now() - started).total_seconds():.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
