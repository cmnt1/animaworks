"""Create the daily property sale portal Products draft for Sakura review."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import py_compile
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    import pandas as pd


def _is_missing(value: object) -> bool:
    """Return True for None or a float NaN (e.g. from pandas-read CSV blanks).

    Non-standard JSON/Markdown "nan" / "nan%" output was caused by treating
    pandas NaN floats as truthy values instead of missing values. Both None
    and NaN must normalize to "-" in Markdown and null in JSON.
    """
    if value is None:
        return True
    return isinstance(value, float) and math.isnan(value)


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively replace float NaN/Infinity with None so json.dumps produces
    strictly standard JSON (no NaN/Infinity/-Infinity literals)."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _load_pandas() -> Any:
    import pandas as pd

    return pd


def normalize_url_for_diff(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    split = urlsplit(text)
    return urlunsplit((split.scheme, split.netloc, split.path, split.query, ""))


def escape_md_cell(value: object) -> str:
    text = "-" if _is_missing(value) else str(value)
    return text.replace("\n", " ").replace("|", "｜")


def load_listing_csv(path: Path | None) -> pd.DataFrame | None:
    if path is None or not path.exists():
        return None
    pd = _load_pandas()
    return pd.read_csv(path)


def prepare_diff_frame(df: pd.DataFrame | None, *, source_label: str) -> pd.DataFrame:
    pd = _load_pandas()
    if df is None or df.empty:
        columns = [
            "source_label",
            "portal_label",
            "title",
            "url",
            "price_text",
            "price_jpy",
            "gross_yield_percent",
            "property_type",
            "review_status",
            "_url_norm",
            "_url_occurrence",
            "_match_key",
        ]
        return pd.DataFrame(columns=columns)

    out = df.copy()
    for col in ["portal_label", "title", "url", "price_text", "property_type", "review_status"]:
        if col not in out.columns:
            out[col] = ""
    if "price_jpy" not in out.columns:
        out["price_jpy"] = None
    if "gross_yield_percent" not in out.columns:
        out["gross_yield_percent"] = None

    out["source_label"] = source_label
    out["_url_norm"] = out["url"].map(normalize_url_for_diff)
    out = out[out["_url_norm"].astype(str).str.len() > 0].copy()
    out = out.reset_index(drop=True)
    out["_url_occurrence"] = out.groupby("_url_norm").cumcount() + 1
    out["_match_key"] = out["_url_norm"] + "||" + out["_url_occurrence"].astype(str)
    return out


def _observed_portals(csv_path: Path) -> set[str]:
    """Portals fetched that day according to the sibling scraper JSON (empty if unreadable)."""
    try:
        runs = json.loads(csv_path.with_suffix(".json").read_text(encoding="utf-8-sig")).get("portal_runs") or []
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()
    return {str(run.get("portal_label")) for run in runs if run.get("fetched")}


def sale_observation(date: str, csv_path: Path, fetched_portals: set[str] | None = None) -> Observation:
    """One day's listings keyed by match key; portals present in the CSV count as fetched."""
    frame = prepare_diff_frame(load_listing_csv(csv_path), source_label=date)
    items = {row["_match_key"]: (str(row["portal_label"]), row) for row in frame.to_dict("records")}
    observed = _observed_portals(csv_path) if fetched_portals is None else set(fetched_portals)
    return date, items, observed


def load_sale_history(before_date: str, root: Path | None = None) -> list[Observation]:
    """Observations for each saved day before `before_date` (first CSV per day)."""
    root = root or DATA_ROOT
    before_ymd = before_date.replace("-", "")
    by_day: dict[str, Path] = {}
    for path in sorted(root.glob(f"*/*/*/P-*_{SLUG_PREFIX}-*.csv")):
        ymd = path.stem.rsplit("-", 1)[-1]
        if len(ymd) == 8 and ymd.isdigit() and ymd < before_ymd:
            by_day.setdefault(ymd, path)
    history = []
    for ymd, path in sorted(by_day.items()):
        try:
            history.append(sale_observation(f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}", path))
        except Exception:  # noqa: BLE001 - one unreadable day must not break the report
            continue
    return history


def _listing_start(row: dict) -> str:
    return escape_md_cell(row.get("listing_start"))


_DAY_COLUMNS = {
    "listed": (
        ("掲載開始", "---", _listing_start),
        ("掲載日目", "---:", lambda r: days_cell(r.get("listing_day"), bool(r.get("start_uncertain")), "日目")),
    ),
    "withdrawn": (
        ("掲載開始", "---", _listing_start),
        ("最終確認", "---", lambda r: escape_md_cell(r.get("last_seen"))),
        ("掲載日数", "---:", lambda r: days_cell(r.get("listing_days"), bool(r.get("start_uncertain")), "日")),
    ),
}


def diff_rows_to_markdown(rows: list[dict], *, days: str, empty_message: str = "該当なし") -> str:
    """days: "listed" (掲載開始/掲載日目) or "withdrawn" (掲載開始/最終確認/掲載日数)."""
    columns = _DAY_COLUMNS[days]
    header = "| 媒体名 | タイトル/物件名 | URL | 価格 | 表面利回り | 種別 | " + " | ".join(c[0] for c in columns) + " |"
    separator = "|---|---|---|---:|---:|---|" + "|".join(c[1] for c in columns) + "|"
    if not rows:
        return "\n".join([header, separator, f"| {empty_message} | - | - | - | - | - |" + " - |" * len(columns)])

    lines = [header, separator]
    for row in rows:
        portal = escape_md_cell(row.get("portal_label"))
        title = escape_md_cell(row.get("title"))
        url = escape_md_cell(row.get("url"))
        price_text = row.get("price_text")
        price_text = None if _is_missing(price_text) else price_text
        price = escape_md_cell(price_text or yen(row.get("price_jpy")))
        yield_ = escape_md_cell(pct(row.get("gross_yield_percent")))
        property_type = row.get("property_type")
        property_type = None if _is_missing(property_type) else property_type
        property_type = escape_md_cell(property_type or "-")
        url_cell = f"[{url}]({url})" if url and url != "-" else "-"
        day_cells = " | ".join(cell(row) for _, _, cell in columns)
        lines.append(f"| {portal} | {title} | {url_cell} | {price} | {yield_} | {property_type} | {day_cells} |")
    return "\n".join(lines)


def build_url_diff_report(
    current_csv: Path,
    report_date: str,
    *,
    history: list[Observation],
    fetched_portals: set[str] | None = None,
) -> dict[str, object]:
    """Classify today's listings against every earlier observation of their portal."""
    today = sale_observation(report_date, current_csv, fetched_portals)
    base = {
        "current_csv": str(current_csv),
        "current_count": len(today[1]),
        "comparison_key": "URL（fragment除去・空白除去）",
    }
    if not history:
        return {**base, "comparison_available": False, "message": "過去データなしのため比較不可"}
    rows = classify_listings(history, today)
    counts = {name.replace("_rows", "_count"): len(value) for name, value in rows.items()}
    return {**base, "comparison_available": True, "previous_date": history[-1][0], **counts, **rows}


JST = timezone(timedelta(hours=9))

PROJECT_DIR = Path(r"E:\OneDriveBiz\Tools\General\animaworks")
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core.reports.property._listing_runs import MAX_OBSERVATION_GAP_DAYS, Observation, classify_listings, days_cell
from core.tools.property_portal_scraper import result_to_dict, run_scan, write_outputs

PRODUCT_ROOT = Path(r"E:\OneDriveBiz\Obsidian\_products")
CATEGORY_DIR = PRODUCT_ROOT / "Property"
DATA_ROOT = Path(r"E:\OneDriveBiz\Obsidian\_data\Property\SalePortals")
REPORT_OUTPUT_DIR = PROJECT_DIR / "reports" / "property_portals"
DEFAULT_TASK_RESULTS_DIR = Path(r"E:\OneDriveBiz\AnimaWorks\.animaworks\animas\hikaru\state\task_results")
TASK_RESULTS_DIR = Path(os.environ.get("ANIMAWORKS_REPORT_TASK_RESULTS_DIR", str(DEFAULT_TASK_RESULTS_DIR)))

TASK_CODE = "PROP-07"
TASK_NAME = "デイリー売買情報レポート"
SLUG_PREFIX = "daily-sale-info"
DISCORD_THREAD_ID = "1491411026263146658"
MIN_GROSS_YIELD = 8.0


def source_file_path() -> Path:
    return Path(__file__).resolve()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_matches(path: Path, expected: str) -> bool:
    return path.exists() and sha256_file(path) == expected


def script_preflight(path: Path | None = None) -> dict:
    source_path = (path or source_file_path()).resolve()
    checks = {
        "source_exists": source_path.exists(),
        "source_nonempty": source_path.exists() and source_path.stat().st_size > 0,
        "py_compile_ok": False,
    }
    compile_error = None
    try:
        py_compile.compile(str(source_path), doraise=True)
        checks["py_compile_ok"] = True
    except py_compile.PyCompileError as exc:
        compile_error = str(exc)

    payload = {
        "script_path": str(source_path),
        "script_size_bytes": source_path.stat().st_size if source_path.exists() else 0,
        "script_sha256": sha256_file(source_path) if source_path.exists() else None,
        "checks": checks,
        "ok": all(checks.values()),
    }
    if compile_error:
        payload["py_compile_error"] = compile_error
    return payload


def read_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    values: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line or line.startswith((" ", "\t", "- ")):
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def max_product_id() -> int:
    ids: list[int] = []
    for path in PRODUCT_ROOT.rglob("P-*.md"):
        match = re.match(r"P-(\d{5})", path.name)
        if match:
            ids.append(int(match.group(1)))
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        id_match = re.search(r"^id:\s*(\d+)\s*$", text, re.M)
        if id_match:
            ids.append(int(id_match.group(1)))
    return max(ids) if ids else 0


def find_existing(report_date: str) -> Path | None:
    ymd = report_date.replace("-", "")
    for path in CATEGORY_DIR.glob(f"P-*_{SLUG_PREFIX}-{ymd}.md"):
        return path
    for path in CATEGORY_DIR.glob("P-*.md"):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        if re.search(rf"^task_code:\s*{re.escape(TASK_CODE)}\s*$", text, re.M) and re.search(
            rf"^report_date:\s*{re.escape(report_date)}\s*$", text, re.M
        ):
            return path
    return None


def data_dir_for_date(root: Path, report_date: str) -> Path:
    ymd = report_date.replace("-", "")
    return root / ymd[0:4] / ymd[4:6] / ymd[6:8]


def yen(value: int | None) -> str:
    return "-" if _is_missing(value) else f"{value:,}円"


def pct(value: float | None) -> str:
    return "-" if _is_missing(value) else f"{value:g}%"


def build_candidate_rows(listings: list[dict]) -> str:
    if not listings:
        return "| - | - | - | - | - | - |\n"
    rows: list[str] = []
    for item in listings:
        price_text = item.get("price_text")
        price_text = None if _is_missing(price_text) else price_text
        property_type = item.get("property_type")
        property_type = None if _is_missing(property_type) else property_type
        rows.append(
            "| {portal} | [{title}]({url}) | {price} | {yield_} | {type_} | {review} |".format(
                portal=item.get("portal_label", "-"),
                title=str(item.get("title") or "-").replace("|", " "),
                url=item.get("url", ""),
                price=price_text or yen(item.get("price_jpy")),
                yield_=pct(item.get("gross_yield_percent")),
                type_=property_type or "-",
                review=item.get("review_status") or "-",
            )
        )
    return "\n".join(rows) + "\n"


def render_product(
    *,
    product_id: int,
    code: str,
    report_date: str,
    scraper_md: Path,
    scraper_json: Path,
    scraper_csv: Path,
    data_json_copy: Path,
    data_md_copy: Path,
    data_csv_copy: Path,
    digest: str,
    result: dict,
    comparison: dict | None,
    created: str,
    updated: str,
    confirmed: str,
) -> str:
    portal_runs = result["portal_runs"]
    listings = [item for run in portal_runs for item in run.get("listings", [])]
    passed = [item for item in listings if item.get("review_status") == "passes_min_gross_yield"]
    needs_review = [item for item in listings if item.get("review_status") == "needs_review"]
    blocked = [run for run in portal_runs if not run.get("fetched")]
    portal_lines = "\n".join(
        "- {label}: HTTP={http}, robots={robots}, 取得={fetched}, 候補={count}件{error}".format(
            label=run["portal_label"],
            http=run.get("http_status"),
            robots=run.get("robots", {}).get("status"),
            fetched="yes" if run.get("fetched") else "no",
            count=run.get("listing_count"),
            error=f", error={run.get('error')}" if run.get("error") else "",
        )
        for run in portal_runs
    )

    def _blocked_line(run: dict) -> str:
        url = run.get("url")
        url_text = f"[{url}]({url})" if url else "-"
        return f"- {run['portal_label']}: {run.get('error') or '未取得'} ({url_text})"

    blocked_lines = "\n".join(_blocked_line(run) for run in blocked) or "- なし"
    diff_section: list[str] = []
    if comparison and comparison.get("comparison_available"):
        unconfirmed = list(comparison.get("unconfirmed_rows", []))
        diff_section.extend(
            [
                "## 前回差分（URL単位）",
                "",
                "- 比較キー: " + str(comparison.get("comparison_key") or "-"),
                "- 現在CSV: `" + str(comparison.get("current_csv") or "-") + "`",
                "- 比較対象: 各媒体の前回取得日（前回データ: " + str(comparison.get("previous_date")) + "）",
                "- 新規で見つかった物件: **" + str(comparison.get("new_count")) + "件**",
                "- 前回から継続して載っている物件: **" + str(comparison.get("continued_count")) + "件**",
                "- 前回から消えた物件: **" + str(comparison.get("deleted_count")) + "件**",
            ]
        )
        if unconfirmed:
            diff_section.append(
                f"- 当日取得に失敗した媒体のため判定保留: **{len(unconfirmed)}件**（取り下げとはみなさない）"
            )
        diff_section.extend(
            [
                "- 掲載日目＝初めて確認した日を1日目とした暦日数。掲載日数＝初回確認〜最終確認の暦日数"
                "（取り下げはその翌日〜当日の間）。媒体の取得失敗日は飛ばして数える。",
                "- 「以上」＝データ開始前、または媒体の取得が"
                f"{MAX_OBSERVATION_GAP_DAYS}日を超えて空いた間に掲載が始まったため、実際はそれより長い。",
                "",
                "### 新規で見つかった物件",
                "",
                diff_rows_to_markdown(list(comparison.get("new_rows", [])), days="listed"),
                "",
                "### 前回から継続して載っている物件",
                "",
                diff_rows_to_markdown(list(comparison.get("continued_rows", [])), days="listed"),
                "",
                "### 前回から消えた物件",
                "",
                diff_rows_to_markdown(list(comparison.get("deleted_rows", [])), days="withdrawn"),
                "",
            ]
        )
        if unconfirmed:
            diff_section.extend(
                [
                    "### 判定保留（当日取得に失敗した媒体）",
                    "",
                    diff_rows_to_markdown(unconfirmed, days="listed"),
                    "",
                ]
            )
    else:
        diff_section.extend(
            [
                "## 前回差分（URL単位）",
                "",
                "- " + str(comparison.get("message") if comparison else "過去データなしのため比較不可"),
                "",
            ]
        )
    diff_section_text = "\n".join(diff_section)
    title = f"{TASK_NAME}（{report_date}）"
    evidence_path = TASK_RESULTS_DIR / f"daily-sale-report-draft-{report_date.replace('-', '')}.json"

    return f"""---
type: product
id: {product_id}
code: {code}
title: {title}
category: Property
product_type: 報告書
status: レビュー待ち
task_code: {TASK_CODE}
task_name: {TASK_NAME}
assignee: hikaru
reviewer: sakura
review_discord_thread_id: "{DISCORD_THREAD_ID}"
report_date: {report_date}
submitted:
requires_reply: false
confirmed: {confirmed}
created: {created}
updated: {updated}
source_json: {scraper_json}
source_json_copy: {data_json_copy}
source_markdown: {scraper_md}
source_markdown_copy: {data_md_copy}
source_csv: {scraper_csv}
source_csv_copy: {data_csv_copy}
source_json_sha256: {digest}
min_gross_yield_percent: {MIN_GROSS_YIELD}
tags:
  - product
  - property
  - sale
  - anjo
  - daily
formal_evidence_path: {evidence_path}
---

# {title}

## サマリー
- 巡回対象: 投資用不動産・収益物件の売買情報（安城市中心）
- 巡回ポータル: {len(portal_runs)}件
- 抽出候補: {len(listings)}件
- 一次通過（表面利回り {MIN_GROSS_YIELD:g}% 以上）: {len(passed)}件
- 要確認（利回り未取得など）: {len(needs_review)}件
- 未取得ポータル: {len(blocked)}件

## ポータル別取得状況
{portal_lines}

## 一次通過候補
| ポータル | 物件 | 価格 | 表面利回り | 種別 | 判定 |
|---|---|---:|---:|---|---|
{build_candidate_rows(passed)}
## 要確認候補
| ポータル | 物件 | 価格 | 表面利回り | 種別 | 判定 |
|---|---|---:|---:|---|---|
{build_candidate_rows(needs_review)}
## 未取得・改善対象
{blocked_lines}

{diff_section_text}

## データソース
- 最新Markdown: `{scraper_md}`
- 最新JSON: `{scraper_json}`
- 最新CSV: `{scraper_csv}`
- Obsidian格納JSON: `{data_json_copy}`
- Obsidian格納Markdown: `{data_md_copy}`
- Obsidian格納CSV: `{data_csv_copy}`
- JSON SHA-256: `{digest}`

## Sakuraレビュー依頼
Sakuraはこの下書きと証跡JSONを確認し、問題がなければ frontmatter の `status` を `完了`、`submitted` を `{report_date}` に更新し、Discordスレッド `{DISCORD_THREAD_ID}` に完成報告してください。
"""


def write_evidence(
    *,
    code: str,
    report_date: str,
    report_path: Path,
    data_json_copy: Path,
    data_md_copy: Path,
    data_csv_copy: Path,
    scraper_json: Path,
    scraper_md: Path,
    scraper_csv: Path,
    digest: str,
    result: dict,
    comparison: dict | None,
    task_results_dir: Path = TASK_RESULTS_DIR,
    script_provenance: dict | None = None,
) -> dict:
    script_provenance = script_provenance or script_preflight()
    fm = read_frontmatter(report_path)
    checks = {
        "report_exists": report_path.exists(),
        "json_copy_exists": data_json_copy.exists(),
        "markdown_copy_exists": data_md_copy.exists(),
        "csv_copy_exists": data_csv_copy.exists(),
        "source_json_exists": scraper_json.exists(),
        "source_markdown_exists": scraper_md.exists(),
        "source_csv_exists": scraper_csv.exists(),
        "code_matches": fm.get("code") == code,
        "type_product": fm.get("type") == "product",
        "category_property": fm.get("category") == "Property",
        "status_acceptable": fm.get("status") in {"レビュー待ち", "完了"},
        "task_code_matches": fm.get("task_code") == TASK_CODE,
        "report_date_matches": fm.get("report_date") == report_date,
        "source_sha_matches": fm.get("source_json_sha256") == digest,
        "copy_sha_matches_source": sha256_matches(data_json_copy, digest),
        "assignee_hikaru": fm.get("assignee") == "hikaru",
        "reviewer_sakura": fm.get("reviewer") == "sakura",
        "script_preflight_ok": bool(script_provenance.get("ok")),
    }
    task_results_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = task_results_dir / f"daily-sale-report-draft-{report_date.replace('-', '')}.json"
    payload = {
        "status": "done" if all(checks.values()) else "blocked",
        "generated_at": datetime.now(JST).replace(microsecond=0).isoformat(),
        "task_code": TASK_CODE,
        "task_name": TASK_NAME,
        "code": code,
        "report_date": report_date,
        "report_path": str(report_path),
        "data_json_copy_path": str(data_json_copy),
        "data_markdown_copy_path": str(data_md_copy),
        "data_csv_copy_path": str(data_csv_copy),
        "source_json_path": str(scraper_json),
        "source_markdown_path": str(scraper_md),
        "source_csv_path": str(scraper_csv),
        "source_json_sha256": digest,
        "read_after_write_checks": checks,
        "summary": {
            "portal_count": len(result["portal_runs"]),
            "listing_count": sum(run["listing_count"] for run in result["portal_runs"]),
            "passed_min_gross_yield_count": sum(
                1
                for run in result["portal_runs"]
                for item in run.get("listings", [])
                if item.get("review_status") == "passes_min_gross_yield"
            ),
        },
        "comparison": comparison,
        "discord_thread_id": DISCORD_THREAD_ID,
        "script_path": script_provenance.get("script_path"),
        "script_sha256": script_provenance.get("script_sha256"),
        "script_size_bytes": script_provenance.get("script_size_bytes"),
        "script_py_compile_ok": script_provenance.get("checks", {}).get("py_compile_ok"),
        "script_provenance": script_provenance,
    }
    # Sanitize before serializing: pandas-derived NaN floats in comparison
    # rows must become JSON null, never the non-standard "NaN" literal that
    # Python's json module emits by default (allow_nan=True).
    sanitized_payload = _sanitize_for_json(payload)
    evidence_path.write_text(
        json.dumps(sanitized_payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    sanitized_payload["evidence_path"] = str(evidence_path)
    return sanitized_payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=TASK_NAME)
    parser.add_argument(
        "--report-date",
        default=datetime.now(JST).strftime("%Y-%m-%d"),
        help="Report date in YYYY-MM-DD. Defaults to today in JST.",
    )
    parser.add_argument(
        "--task-results-dir",
        type=Path,
        default=TASK_RESULTS_DIR,
        help="Directory for formal evidence JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report_date = args.report_date
    task_results_dir = args.task_results_dir
    script_provenance = script_preflight()
    if not script_provenance["ok"]:
        print(json.dumps({"status": "blocked", "script_provenance": script_provenance}, ensure_ascii=False))
        return 1

    CATEGORY_DIR.mkdir(parents=True, exist_ok=True)
    task_results_dir.mkdir(parents=True, exist_ok=True)
    REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    existing = find_existing(report_date)
    if existing:
        fm = read_frontmatter(existing)
        if fm.get("status") in {"レビュー待ち", "完了"}:
            print(f"NOOP_ALREADY_CREATED: {existing} status={fm.get('status')}")
            return 0

    scan = run_scan(min_gross_yield_percent=MIN_GROSS_YIELD)
    outputs = write_outputs(scan, REPORT_OUTPUT_DIR)
    result = result_to_dict(scan)

    scraper_json = Path(outputs["json"]).resolve()
    scraper_md = Path(outputs["markdown"]).resolve()
    scraper_csv = Path(outputs["csv"]).resolve()
    data_dir = data_dir_for_date(DATA_ROOT, report_date)
    data_dir.mkdir(parents=True, exist_ok=True)

    product_id = max_product_id() + 1
    code = f"P-{product_id:05d}"
    out_md = CATEGORY_DIR / f"{code}_{SLUG_PREFIX}-{report_date.replace('-', '')}.md"
    data_json_copy = data_dir / f"{code}_{SLUG_PREFIX}-{report_date.replace('-', '')}.json"
    data_md_copy = data_dir / f"{code}_{SLUG_PREFIX}-{report_date.replace('-', '')}.md"
    data_csv_copy = data_dir / f"{code}_{SLUG_PREFIX}-{report_date.replace('-', '')}.csv"

    shutil.copyfile(scraper_json, data_json_copy)
    shutil.copyfile(scraper_md, data_md_copy)
    shutil.copyfile(scraper_csv, data_csv_copy)
    digest = sha256_file(scraper_json)
    if sha256_file(data_json_copy) != digest:
        raise RuntimeError("Copied scraper JSON SHA-256 mismatch")

    comparison = build_url_diff_report(
        data_csv_copy,
        report_date,
        history=load_sale_history(report_date),
        fetched_portals={str(run["portal_label"]) for run in result["portal_runs"] if run.get("fetched")},
    )
    now = datetime.now(JST).replace(microsecond=0).isoformat()
    out_md.write_text(
        render_product(
            product_id=product_id,
            code=code,
            report_date=report_date,
            scraper_md=scraper_md,
            scraper_json=scraper_json,
            scraper_csv=scraper_csv,
            data_json_copy=data_json_copy,
            data_md_copy=data_md_copy,
            data_csv_copy=data_csv_copy,
            digest=digest,
            result=result,
            comparison=comparison,
            created=now,
            updated=now,
            confirmed="false",
        ),
        encoding="utf-8",
        newline="\n",
    )
    evidence = write_evidence(
        code=code,
        report_date=report_date,
        report_path=out_md,
        data_json_copy=data_json_copy,
        data_md_copy=data_md_copy,
        data_csv_copy=data_csv_copy,
        scraper_json=scraper_json,
        scraper_md=scraper_md,
        scraper_csv=scraper_csv,
        digest=digest,
        result=result,
        comparison=comparison,
        task_results_dir=task_results_dir,
        script_provenance=script_provenance,
    )
    print(json.dumps(evidence, ensure_ascii=False))
    return 0 if evidence["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
