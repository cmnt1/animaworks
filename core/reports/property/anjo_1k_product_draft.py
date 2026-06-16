"""Create the Anjo 1K daily Products draft for Sakura review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import re
import runpy
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

PROJECT_DIR = Path(r"E:\OneDriveBiz\Tools\General\animaworks")
ABCONFIG_DIR = Path(r"E:\OneDriveBiz\Tools\abconfig")
for path in (PROJECT_DIR, ABCONFIG_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

EXTRACT_SCRIPT = Path(r"E:\OneDriveBiz\Tools\Property\py_mod\extract_anjo_1k_daily.py")
DATA_ROOT = Path(r"E:\OneDriveBiz\Obsidian\_data\Property\Suumo")
PRODUCT_DATA_ROOT = Path(r"E:\OneDriveBiz\Obsidian\_data\Property\Products")
PRODUCT_ROOT = Path(r"E:\OneDriveBiz\Obsidian\_products")
CATEGORY_DIR = PRODUCT_ROOT / "Property"
DEFAULT_TASK_RESULTS_DIR = Path(r"E:\OneDriveBiz\AnimaWorks\.animaworks\animas\hikaru\state\task_results")
TASK_RESULTS_DIR = Path(os.environ.get("ANIMAWORKS_REPORT_TASK_RESULTS_DIR", str(DEFAULT_TASK_RESULTS_DIR)))

TASK_CODE = "PTY-ANJO-1K-DAILY"
TASK_NAME = "安城市1K賃貸 市場動向 日次レポート"
SLUG_PREFIX = "anjo-1k"
DISCORD_THREAD_ID = "1491411026263146658"
SCRAPE_STATUS_TABLE = "dbo.T_Suumo_Scrape_Status"
TARGET_CITY_ID = 1
TRUSTED_MINIMINI_COUNT_PATTERNS = {
    "p.kensu strong count",
    "pagetitle_sub p.kensu strong count",
    "count text label",
    "count text range label",
}


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


def read_scrape_status() -> dict | None:
    from Cnct_Env import create_connection
    from sqlalchemy import text

    engine = create_connection("property_db")
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f"""
                SELECT TOP 1 Status, Row_Count, Finished_At, Updated_At
                FROM {SCRAPE_STATUS_TABLE}
                WHERE Date_Search = CAST(GETDATE() AS date)
                  AND IID_City = :city_id
                ORDER BY Updated_At DESC
                """
            ),
            {"city_id": TARGET_CITY_ID},
        ).fetchone()
    if row is None:
        return None
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return {
        "Status": row["Status"],
        "Row_Count": row["Row_Count"],
        "Finished_At": row["Finished_At"],
        "Updated_At": row["Updated_At"],
    }


def yen(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, float):
        return f"{value:,.1f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def signed(value: object, unit: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, float):
        return f"{value:+,.1f}{unit}"
    if isinstance(value, int):
        return f"{value:+,}{unit}"
    return f"{value}{unit}"


def read_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    values: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def frontmatter_value(text: str, key: str, default: str = "") -> str:
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", text, re.M)
    return m.group(1).strip() if m else default


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
        m = re.search(r"^id:\s*(\d+)\s*$", text, re.M)
        if m:
            ids.append(int(m.group(1)))
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
        if re.search(rf"^report_date:\s*{re.escape(report_date)}\s*$", text, re.M) and TASK_CODE in text:
            return path
    return None


def data_dir_for_ymd(root: Path, ymd: str) -> Path:
    return root / ymd[0:4] / ymd[4:6] / ymd[6:8]


def get_prev_minimini_count(prev_date: str) -> int | None:
    """Get a trusted minimini listing count from the previous day's product JSON."""
    prev_ymd = prev_date.replace("-", "")
    prev_dir = data_dir_for_ymd(PRODUCT_DATA_ROOT, prev_ymd)
    if not prev_dir.exists():
        return None
    for path in prev_dir.glob(f"P-*_{SLUG_PREFIX}-{prev_ymd}_data.json"):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            snapshot = d.get("minimini_url_snapshot", {})
            if snapshot.get("fetch_status") != "success":
                continue
            if snapshot.get("pattern_used") not in TRUSTED_MINIMINI_COUNT_PATTERNS:
                continue
            count = snapshot.get("listing_count")
            if count is not None:
                return int(count)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def build_comments(data: dict) -> list[str]:
    lc = data["listing_count"]
    rent = data["rent"]
    unit = data["unit_price"]
    vac = data["vacancy_proxy"]
    trend = data["trend_7d"]
    counts = [x["listing_count"] for x in trend]
    avg_unit_values = [x["avg_unit_price"] for x in trend if x["avg_unit_price"] is not None]
    avg_unit_7d = round(sum(avg_unit_values) / len(avg_unit_values), 1) if avg_unit_values else None

    comments = [
        f"募集件数は前日比{signed(lc['change'], '件')}の{lc['latest']}件です。直近7日の件数レンジは{min(counts)}-{max(counts)}件です。",
        f"平均賃料は{yen(rent['latest']['mean'])}円、中央値賃料は{yen(rent['latest']['median'])}円です。前日比は平均{signed(rent['change_mean'], '円')}、中央値{signed(rent['change_median'], '円')}です。",
        f"平均坪単価は{yen(unit['latest']['mean'])}円/坪で、前日比{signed(unit['change_mean'], '円/坪')}です。直近7日の平均坪単価平均は{yen(avg_unit_7d)}円/坪です。",
        f"掲載日数中央値は{vac['median_obs_days']}日、7日以上掲載比率は{vac['pct_listings_7plus_days']}%です。",
    ]
    if rent.get("change_mean") and rent["change_mean"] >= 1000:
        comments.append("平均賃料の上昇がやや目立つため、掲載物件の入れ替わりや高額帯の増加有無を次回も確認します。")
    else:
        comments.append("総合すると、件数・賃料・単価はいずれも日次変動の範囲で、安城市1K市場は安定推移です。")
    return comments


def render_markdown(
    product_id: int,
    code: str,
    data: dict,
    source_json: Path,
    copy_json: Path,
    digest: str,
    created: str,
    updated: str,
    confirmed: str,
    task_results_dir: Path = TASK_RESULTS_DIR,
    prev_minimini_count: int | None = None,
) -> str:
    d = data["latest_date"]
    prev = data["prev_date"]
    meta = data["meta"]
    lc = data["listing_count"]
    rent = data["rent"]
    unit = data["unit_price"]
    vac = data["vacancy_proxy"]
    title = f"{TASK_NAME}（{d}）"
    trend_rows = "\n".join(
        f"| {x['date']} | {x['listing_count']}件 | {yen(x['avg_rent'])}円 | {yen(x['median_rent'])}円 | {yen(x['avg_unit_price'])}円/坪 |"
        for x in data["trend_7d"]
    )
    comments = "\n".join(f"- {comment}" for comment in build_comments(data))
    evidence_path = task_results_dir / f"anjo-1k-daily-products-draft-{d.replace('-', '')}.json"

    # minimini section
    minimini = data.get("minimini_url_snapshot") or {}
    minimini_count = minimini.get("listing_count")
    minimini_summary_line = ""
    minimini_section = ""
    if minimini_count is not None:
        if prev_minimini_count is not None:
            diff = int(minimini_count) - int(prev_minimini_count)
            diff_str = f"（前日比 {'+' if diff > 0 else ''}{diff}件）"
        else:
            diff_str = ""
        minimini_summary_line = f"\n- minimini掲載件数: **{minimini_count}件**{diff_str}"
        minimini_section = f"""
## minimini掲載状況

| 項目 | 値 |
|---|---|
| 掲載件数 | {minimini_count}件{diff_str} |
| 取得日時 | {minimini.get("fetched_at", "-")} |
| 取得方法 | {minimini.get("method", "-")} |
| 取得URL | {minimini.get("url", "-")} |
| HTTPステータス | {minimini.get("http_status", "-")} |
"""

    return f"""---
type: product
id: {product_id}
code: {code}
title: {title}
category: Property
product_type: 報告書
status: レビュー待ち
task_code: {TASK_CODE}
assignee: hikaru
reviewer: sakura
review_discord_thread_id: "{DISCORD_THREAD_ID}"
report_date: {d}
submitted:
requires_reply: false
confirmed: {confirmed}
created: {created}
updated: {updated}
source_json: {source_json}
source_json_copy: {copy_json}
source_json_sha256: {digest}
tags:
  - product
  - property
  - anjo
  - 1k
  - daily
formal_evidence_path: {evidence_path}
---

# {title}

## サマリー
- 対象データ最新日: **{d}**（前日: {prev}）
- 募集件数: **{lc["latest"]}件**（前日比 {signed(lc["change"], "件")}）
- 平均賃料: **{yen(rent["latest"]["mean"])}円**（前日比 {signed(rent["change_mean"], "円")}）
- 中央値賃料: **{yen(rent["latest"]["median"])}円**（前日比 {signed(rent["change_median"], "円")}）
- 平均坪単価: **{yen(unit["latest"]["mean"])}円/坪**（前日比 {signed(unit["change_mean"], "円/坪")}）
- 中央値坪単価: **{yen(unit["latest"]["median"])}円/坪**
- 掲載日数中央値: **{vac["median_obs_days"]}日**
- 7日以上掲載比率: **{vac["pct_listings_7plus_days"]}%**{minimini_summary_line}

## 主要指標（最新日 vs 前日）
| 指標 | 最新日（{d}） | 前日（{prev}） | 前日比 |
|---|---:|---:|---:|
| 募集件数 | {lc["latest"]}件 | {lc["prev"]}件 | {signed(lc["change"], "件")} |
| 平均賃料 | {yen(rent["latest"]["mean"])}円 | {yen(rent["prev"]["mean"])}円 | {signed(rent["change_mean"], "円")} |
| 中央値賃料 | {yen(rent["latest"]["median"])}円 | {yen(rent["prev"]["median"])}円 | {signed(rent["change_median"], "円")} |
| 平均坪単価 | {yen(unit["latest"]["mean"])}円/坪 | {yen(unit["prev"]["mean"])}円/坪 | {signed(unit["change_mean"], "円/坪")} |
| 中央値坪単価 | {yen(unit["latest"]["median"])}円/坪 | {yen(unit["prev"]["median"])}円/坪 | - |

## 直近7日トレンド
| 日付 | 募集件数 | 平均賃料 | 中央値賃料 | 平均坪単価 |
|---|---:|---:|---:|---:|
{trend_rows}

## コメント
{comments}
{minimini_section}
## データソース
- 参照JSON: `{source_json}`
- Obsidian格納JSON: `{copy_json}`
- JSON SHA-256: `{digest}`
- データ基準日: {d}（latest_date_in_db: {meta.get("latest_date_in_db")}）
- JSON抽出時刻: {meta.get("extraction_time")} JST
- 賃料カラム: {meta.get("rent_column_used")}
- 単価カラム: Base_Rent / Ocu_Area
- データ期間: {meta.get("data_range", {}).get("min_date")} - {meta.get("data_range", {}).get("max_date")}

## レビュー依頼
Sakuraはこの下書きを確認し、問題がなければ frontmatter の `status` を `完了`、`submitted` を `{d}` に更新したうえで、Discordスレッド `{DISCORD_THREAD_ID}` に完成報告してください。
"""


def write_evidence(
    code: str,
    report_date: str,
    out_md: Path,
    copy_json: Path,
    source_json: Path,
    digest: str,
    *,
    task_results_dir: Path = TASK_RESULTS_DIR,
    script_provenance: dict | None = None,
) -> dict:
    script_provenance = script_provenance or script_preflight()
    fm = read_frontmatter(out_md)
    copied_digest = sha256_file(copy_json) if copy_json.exists() else ""
    checks = {
        "report_exists": out_md.exists(),
        "data_copy_exists": copy_json.exists(),
        "source_json_exists": source_json.exists(),
        "code_matches": fm.get("code") == code,
        "type_product": fm.get("type") == "product",
        "category_property": fm.get("category") == "Property",
        "status_acceptable": fm.get("status") in {"レビュー待ち", "完了"},
        "task_code_matches": fm.get("task_code") == TASK_CODE,
        "report_date_matches": fm.get("report_date") == report_date,
        "source_sha_matches": fm.get("source_json_sha256") == digest,
        "copy_sha_matches_source": copied_digest == digest,
        "assignee_hikaru": fm.get("assignee") == "hikaru",
        "reviewer_sakura": fm.get("reviewer") == "sakura",
        "script_preflight_ok": bool(script_provenance.get("ok")),
    }
    task_results_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = task_results_dir / f"anjo-1k-daily-products-draft-{report_date.replace('-', '')}.json"
    evidence = {
        "status": "done" if all(checks.values()) else "blocked",
        "generated_at": datetime.now(JST).replace(microsecond=0).isoformat(),
        "task_code": TASK_CODE,
        "task_name": TASK_NAME,
        "code": code,
        "report_date": report_date,
        "report_path": str(out_md),
        "data_copy_path": str(copy_json),
        "source_json_path": str(source_json),
        "source_json_sha256": digest,
        "data_copy_sha256": copied_digest,
        "frontmatter": {
            key: fm.get(key)
            for key in (
                "type",
                "code",
                "status",
                "task_code",
                "assignee",
                "reviewer",
                "report_date",
                "submitted",
                "confirmed",
            )
        },
        "read_after_write_checks": checks,
        "discord_thread_id": DISCORD_THREAD_ID,
        "script_path": script_provenance.get("script_path"),
        "script_sha256": script_provenance.get("script_sha256"),
        "script_size_bytes": script_provenance.get("script_size_bytes"),
        "script_py_compile_ok": script_provenance.get("checks", {}).get("py_compile_ok"),
        "script_provenance": script_provenance,
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence["evidence_path"] = str(evidence_path)
    return evidence


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
    task_results_dir = args.task_results_dir
    script_provenance = script_preflight()
    if not script_provenance["ok"]:
        print(json.dumps({"status": "blocked", "script_provenance": script_provenance}, ensure_ascii=False))
        return 1

    CATEGORY_DIR.mkdir(parents=True, exist_ok=True)
    task_results_dir.mkdir(parents=True, exist_ok=True)

    today = args.report_date.replace("-", "")
    today_iso = args.report_date
    existing_today = find_existing(today_iso)
    if existing_today:
        old_fm = read_frontmatter(existing_today)
        if old_fm.get("status") in {"レビュー待ち", "完了"}:
            print(f"NOOP_ALREADY_CREATED: {existing_today} status={old_fm.get('status')}")
            return 0

    scrape_status = read_scrape_status()
    if scrape_status is None:
        print(f"NOT_READY: scrape marker missing for report_date={today_iso}, IID_City={TARGET_CITY_ID}")
        return 0
    status = str(scrape_status.get("Status") or "")
    if status in {"running", "queued", "pending", "no_data", ""}:
        print(
            "NOT_READY: "
            f"scrape status={status or 'unknown'}, "
            f"row_count={scrape_status.get('Row_Count')}, "
            f"updated_at={scrape_status.get('Updated_At')}"
        )
        return 0
    if status != "completed":
        raise RuntimeError(
            "Scrape is not completed: "
            f"status={status}, row_count={scrape_status.get('Row_Count')}, "
            f"finished_at={scrape_status.get('Finished_At')}"
        )

    runpy.run_path(str(EXTRACT_SCRIPT), run_name="__main__")
    source_json = data_dir_for_ymd(DATA_ROOT, today) / f"anjo_1k_market_metrics_{today}.json"
    if not source_json.exists():
        raise FileNotFoundError(source_json)

    data = json.loads(source_json.read_text(encoding="utf-8-sig"))
    report_date = data["latest_date"]
    ymd = report_date.replace("-", "")
    existing = find_existing(report_date)

    if existing:
        m = re.match(r"P-(\d{5})", existing.name)
        if not m:
            raise ValueError(f"Cannot parse product code from {existing}")
        product_id = int(m.group(1))
        code = f"P-{product_id:05d}"
        out_md = existing
        old_text = existing.read_text(encoding="utf-8-sig", errors="ignore")
        old_fm = read_frontmatter(existing)
        if old_fm.get("status") == "完了":
            copy_json = Path(
                old_fm.get("source_json_copy")
                or data_dir_for_ymd(PRODUCT_DATA_ROOT, ymd) / f"{code}_{SLUG_PREFIX}-{ymd}_data.json"
            )
            source_for_evidence = Path(old_fm.get("source_json") or source_json)
            digest_for_evidence = old_fm.get("source_json_sha256") or sha256_file(source_for_evidence)
            evidence = write_evidence(
                code,
                report_date,
                out_md,
                copy_json,
                source_for_evidence,
                digest_for_evidence,
                task_results_dir=task_results_dir,
                script_provenance=script_provenance,
            )
            print(json.dumps(evidence, ensure_ascii=False))
            return 0 if evidence["status"] == "done" else 1
        created = frontmatter_value(old_text, "created", datetime.now(JST).replace(microsecond=0).isoformat())
        # Never propagate confirmed:true from an existing file. Only a human reviewer (sakura) can
        # set confirmed:true after promotion to status:完了. Anima generation always emits false.
        confirmed = "false"
    else:
        product_id = max_product_id() + 1
        code = f"P-{product_id:05d}"
        out_md = CATEGORY_DIR / f"{code}_{SLUG_PREFIX}-{ymd}.md"
        created = datetime.now(JST).replace(microsecond=0).isoformat()
        confirmed = "false"

    copy_dir = data_dir_for_ymd(PRODUCT_DATA_ROOT, ymd)
    copy_dir.mkdir(parents=True, exist_ok=True)
    copy_json = copy_dir / f"{code}_{SLUG_PREFIX}-{ymd}_data.json"
    shutil.copyfile(source_json, copy_json)
    digest = sha256_file(source_json)
    if not sha256_matches(copy_json, digest):
        raise RuntimeError("Copied JSON SHA-256 mismatch")

    prev_minimini_count = get_prev_minimini_count(data.get("prev_date", ""))
    updated = datetime.now(JST).replace(microsecond=0).isoformat()
    out_md.write_text(
        render_markdown(
            product_id,
            code,
            data,
            source_json,
            copy_json,
            digest,
            created,
            updated,
            confirmed,
            task_results_dir=task_results_dir,
            prev_minimini_count=prev_minimini_count,
        ),
        encoding="utf-8",
        newline="\n",
    )
    evidence = write_evidence(
        code,
        report_date,
        out_md,
        copy_json,
        source_json,
        digest,
        task_results_dir=task_results_dir,
        script_provenance=script_provenance,
    )
    print(json.dumps(evidence, ensure_ascii=False))
    return 0 if evidence["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
