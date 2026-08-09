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
import subprocess
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
DISCORD_PARENT_CHANNEL_ID = "1489903551030493296"
ANIMAWORKS_TOOL = Path(r"E:\OneDriveBiz\Tools\General\animaworks\.venv\Scripts\animaworks-tool.exe")
SCRAPE_STATUS_TABLE = "dbo.T_Suumo_Scrape_Status"
TARGET_CITY_ID = 1
SQM_UNIT_PRICE_CUTOFF = "2026-06-26"
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


def report_uses_sqm_unit_price(report_date: str) -> bool:
    return report_date >= SQM_UNIT_PRICE_CUTOFF


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


def validate_minimini_snapshot(data: dict) -> dict:
    """Return the advisory availability check for the minimini snapshot."""
    snapshot = data.get("minimini_url_snapshot")
    reasons: list[str] = []
    if not isinstance(snapshot, dict):
        snapshot = {}
        reasons.append("minimini_url_snapshot_missing")

    fetch_status = snapshot.get("fetch_status")
    if fetch_status != "success":
        reasons.append(f"fetch_status={fetch_status or 'missing'}")

    listing_count = snapshot.get("listing_count")
    if isinstance(listing_count, bool) or not isinstance(listing_count, int) or listing_count < 0:
        reasons.append("listing_count_missing_or_invalid")

    listings = snapshot.get("listings")
    room_count = None
    rooms_count = None
    detail_fetched = None
    detail_cached = None
    detail_failed = None
    detail_stale = None
    if not isinstance(listings, dict):
        reasons.append("listings_missing")
    else:
        room_count = listings.get("room_count")
        rooms = listings.get("rooms")
        rooms_count = len(rooms) if isinstance(rooms, list) else None
        if rooms_count is None:
            reasons.append("listings_rooms_missing")
        if isinstance(listing_count, int) and not isinstance(listing_count, bool):
            if room_count != listing_count:
                reasons.append(f"room_count_mismatch={room_count}/{listing_count}")
            if rooms_count != listing_count:
                reasons.append(f"rooms_length_mismatch={rooms_count}/{listing_count}")
        enriched = listings.get("parking_enriched")
        if not isinstance(enriched, dict):
            reasons.append("detail_enrichment_missing")
        else:
            detail_fetched = enriched.get("fetched", 0)
            detail_cached = enriched.get("cached", 0)
            detail_failed = enriched.get("failed", 0)
            detail_stale = enriched.get("stale", 0)
            detail_counts = (detail_fetched, detail_cached, detail_failed, detail_stale)
            detail_counts_valid = all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in detail_counts
            )
            if not detail_counts_valid:
                reasons.append("detail_enrichment_counts_invalid")
            else:
                if detail_failed != 0:
                    reasons.append(f"detail_fetch_failed={detail_failed}")
                if detail_stale != 0:
                    reasons.append(f"detail_cache_stale={detail_stale}")
                if isinstance(listing_count, int) and not isinstance(listing_count, bool):
                    if detail_fetched + detail_cached != listing_count:
                        reasons.append(f"detail_coverage_mismatch={detail_fetched}+{detail_cached}/{listing_count}")

    return {
        "ok": not reasons,
        "fetch_status": fetch_status,
        "listing_count": listing_count,
        "room_count": room_count,
        "rooms_count": rooms_count,
        "detail_fetched": detail_fetched,
        "detail_cached": detail_cached,
        "detail_failed": detail_failed,
        "detail_stale": detail_stale,
        "fetched_at": snapshot.get("fetched_at"),
        "url": snapshot.get("url"),
        "error": snapshot.get("error") or snapshot.get("listings_error"),
        "reasons": reasons,
    }


def send_minimini_unavailable_notification(
    *,
    code: str,
    report_date: str,
    report_path: Path,
    source_json: Path,
    gate: dict,
    task_results_dir: Path,
) -> dict:
    """Post one deterministic Discord warning per report date when minimini is unavailable."""
    marker = task_results_dir / f"anjo-1k-minimini-unavailable-{report_date.replace('-', '')}.json"
    if marker.exists():
        try:
            previous = json.loads(marker.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        if previous.get("status") in {"ok", "verified_existing"}:
            return {
                "status": "verified_existing",
                "marker_path": str(marker),
                "message_id": previous.get("message_id"),
            }

    message = (
        f"【minimini取得未完了 / 注記付き完了可】{code} 安城市1K賃貸 市場動向 日次レポート（{report_date}）は、"
        "minimini掲載一覧を取得できていません。"
        "miniminiは補助情報のため、主要データの検証が通れば注記付きで完了できます。\n\n"
        f"- fetch_status: {gate.get('fetch_status')}\n"
        f"- listing_count: {gate.get('listing_count')}\n"
        f"- error: {gate.get('error') or '-'}\n"
        f"- report: {report_path}\n"
        f"- source JSON: {source_json}\n"
        "minimini値は当日レポートには含めず、取得不可の根拠を証跡JSONに保存します。"
    )
    if not ANIMAWORKS_TOOL.exists():
        result = {
            "status": "blocked",
            "reason": f"animaworks-tool not found: {ANIMAWORKS_TOOL}",
            "message": message,
        }
    else:
        env = os.environ.copy()
        proc = subprocess.run(
            [
                str(ANIMAWORKS_TOOL),
                "discord",
                "send",
                DISCORD_PARENT_CHANNEL_ID,
                message,
                "--thread-id",
                DISCORD_THREAD_ID,
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=env,
            timeout=30,
        )
        result = {
            "status": "ok" if proc.returncode == 0 else "blocked",
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "channel_id": DISCORD_PARENT_CHANNEL_ID,
            "thread_id": DISCORD_THREAD_ID,
        }
        match = re.search(r"id:\s*(\d+)", proc.stdout)
        if match:
            result["message_id"] = match.group(1)

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker_payload = {
        **result,
        "reported_at": datetime.now(JST).replace(microsecond=0).isoformat(),
        "code": code,
        "report_date": report_date,
        "gate": gate,
        "marker_path": str(marker),
    }
    marker.write_text(json.dumps(marker_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return marker_payload


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


def pct(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        return f"{value:+.1f}%"
    return f"{value}"


def build_roof_tree_section(data: dict) -> tuple[str, str]:
    """Return (summary_line, section) for own-property (ROOF TREE) monitoring."""
    roof = data.get("roof_tree")
    if not roof:
        return "", ""
    count = roof.get("count") or 0
    listings = roof.get("listings") or []
    mref = roof.get("market_ref") or {}
    if count and listings:
        top = listings[0]
        summary_line = (
            f"\n- ROOF TREE該当: **{count}件**（予測比 差額 {signed(top.get('diff_vs_predicted'), '円')}・負=割安）"
        )
        rows = "\n".join(
            f"| {x.get('rank')} | {x.get('bname')} | {yen(x.get('base_rent'))}円 "
            f"| {yen(x.get('cmn_fee'))}円 | {yen(x.get('rent_total'))}円 | {yen(x.get('ocu_area'))}㎡ "
            f"| {yen(x.get('unit_price'))}円/㎡ | {yen(x.get('predicted_rent'))}円 "
            f"| {signed(x.get('diff_vs_predicted'), '円')} | {pct(x.get('dev_vs_mean_pct'))} "
            f"| {pct(x.get('dev_vs_median_pct'))} | {x.get('baddress') or '-'} "
            f"| {x.get('bage') or '-'} | {x.get('floor') or '-'} |"
            for x in listings
        )
        hm = roof.get("hedonic_model") or {}
        decomp_groups = hm.get("decomp_groups") or ["面積", "築年", "設備", "駅力", "徒歩分", "その他"]
        decomp_rows = "\n".join(
            f"| {x.get('bname')} | {yen((x.get('decomposition') or {}).get('基準'))}円 "
            + "".join(f"| {signed((x.get('decomposition') or {}).get(g), '円')} " for g in decomp_groups)
            + f"| {yen(x.get('predicted_rent'))}円 | {yen(x.get('rent_total'))}円 "
            f"| {signed(x.get('diff_vs_predicted'), '円')} |"
            for x in listings
        )
        section = f"""
## ROOF TREE 自社物件モニタリング

- 抽出条件: 物件名に「{roof.get("match_term")}」を含む（{roof.get("normalization")}）
- 該当件数: **{count}件**
- 賃料/割安度の定義: {roof.get("rent_basis")}
- 市場参照（最新日・賃料合計ベース）: 平均単価 {yen(mref.get("mean_unit_price"))}円/㎡ ・ 中央値単価 {yen(mref.get("median_unit_price"))}円/㎡

| 順位 | 物件名 | 家賃 | 管理費 | 賃料合計 | 専有面積 | 単価 | 予測賃料 | 差額(賃料合計−予測) | 対平均乖離 | 対中央値乖離 | 所在地 | 築年数 | 階 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
{rows}

### 予測賃料の成分分解（ヘドニックモデル）
- モデル: {hm.get("method") or "-"}（{hm.get("model_artifact") or "-"}）
- 学習精度: R²={hm.get("r2")} ／ 学習サンプル {yen(hm.get("n_samples"))}件 ／ 設備ダミー {hm.get("n_amenity_cols")}列
- 予測賃料を「基準（切片）＋面積・築年・設備・駅力・徒歩分・その他」の各成分の寄与額（円）に分解しています。各成分は最寄駅・徒歩分・専有面積・築年数・設備の各説明変数の係数寄与です。

| 物件名 | 基準 | 面積 | 築年 | 設備 | 駅力 | 徒歩分 | その他 | 予測賃料(推定) | 実賃料合計 | 差額 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{decomp_rows}

- {hm.get("note") or ""}
- 差額（賃料合計−予測）が負に大きいほどモデル比割安。魅力度順位は差額の昇順。
"""
    else:
        summary_line = "\n- ROOF TREE該当: **0件**（当日データに該当物件なし）"
        section = f"""
## ROOF TREE 自社物件モニタリング

- 抽出条件: 物件名に「{roof.get("match_term")}」を含む（{roof.get("normalization")}）
- 該当件数: **0件**（{data.get("latest_date")} 時点で安城市1Kに該当物件は掲載されていません）
"""
    return summary_line, section


def build_minimini_listing_section(minimini: dict) -> str:
    """Return a newest-first MINIMINI room listing table (own properties highlighted)."""
    listings = (minimini or {}).get("listings") or {}
    buildings = listings.get("buildings") or []
    rooms = listings.get("rooms") or []
    if not rooms:
        return ""

    def cell(value: object) -> str:
        if value is None or value == "":
            return "-"
        return str(value).replace("|", "\\|")

    built_by_order = {}
    for building in buildings:
        order = building.get("building_order") if building.get("building_order") is not None else building.get("order")
        if order is None:
            continue
        built_by_order[order] = re.sub(r"\s*/\s*$", "", cell(building.get("built")))

    rows = []
    for i, room in enumerate(rooms, 1):
        own = room.get("is_own")
        name = cell(room.get("bname"))
        name = f"**【自社】{name}**" if own else name
        built = built_by_order.get(room.get("building_order"), "-")
        detail = room.get("detail_url")
        detail_cell = f"[詳細]({detail})" if detail else "-"
        rows.append(
            f"| {i} | {name} | {cell(room.get('address'))} | {built} | {cell(room.get('station'))} "
            f"| {cell(room.get('floor'))} | {cell(room.get('rent'))} | {cell(room.get('mgmt_fee'))} "
            f"| {cell(room.get('deposit'))} | {cell(room.get('key_money'))} | {cell(room.get('layout'))} "
            f"| {cell(room.get('area'))} | {cell(room.get('parking'))} | {cell(room.get('move_in'))} | {detail_cell} |"
        )
    body = "\n".join(rows)
    enriched = listings.get("parking_enriched") or {}
    park_note = ""
    if enriched:
        park_note = (
            f"\n- 駐車場は各物件の詳細ページから取得"
            f"（取得 {enriched.get('fetched', 0)}件／失敗 {enriched.get('failed', 0)}件）。"
            f"「◯◯円」=敷地内月額、「近隣」=近隣斡旋、「無」=なし、空欄=未取得。"
        )
    return f"""

### minimini掲載一覧（{listings.get("sort", "新着順")}）
- 建物数: **{listings.get("building_count")}棟** ／ 部屋数: **{listings.get("room_count")}件**（うち自社 {listings.get("own_room_count", 0)}件）
- 並び順はページ既定の新着順（掲載順）。自社物件（{listings.get("own_term")}）は **【自社】** で強調。{park_note}

| 新着順 | 建物名 | 所在地 | 築年 | 最寄駅 | 階数 | 賃料 | 管理費 | 敷金 | 礼金 | 間取り | 専有面積 | 駐車場 | 入居可能時期 | 詳細 |
|---:|---|---|---|---|---|---:|---:|---|---|---|---:|---|---|---|
{body}
"""


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
    use_sqm_unit_price = report_uses_sqm_unit_price(d)
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
    minimini_gate = validate_minimini_snapshot(data)
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
{build_minimini_listing_section(minimini)}"""
    else:
        minimini_summary_line = "\n- minimini掲載一覧: **取得未完了（注記付き完了可）**"
        minimini_section = f"""
## minimini掲載状況

> [!warning] 取得未完了
> minimini掲載一覧は取得できていません。miniminiは補助情報のため、主要データの検証が通れば注記付きで完了できます。

| 項目 | 値 |
|---|---|
| 取得状態 | {minimini.get("fetch_status", "-")} |
| 取得日時 | {minimini.get("fetched_at", "-")} |
| 取得URL | {minimini.get("url", "-")} |
| HTTPステータス | {minimini.get("http_status", "-")} |
| エラー | {minimini.get("error") or minimini.get("listings_error") or "-"} |
"""

    # ROOF TREE (own-property) section
    roof_summary_line, roof_section = build_roof_tree_section(data)

    review_request = (
        f"Sakuraはこの下書きを確認し、主要データに問題がなければ frontmatter の `status` を `完了`、"
        f"`submitted` を `{d}` に更新したうえで、Discordスレッド `{DISCORD_THREAD_ID}` に完成報告してください。"
    )
    if not minimini_gate["ok"]:
        review_request += " miniminiは取得未完了の注記を残し、完了の必須条件にはしません。"

    markdown = f"""---
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
- 7日以上掲載比率: **{vac["pct_listings_7plus_days"]}%**{minimini_summary_line}{roof_summary_line}

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
{minimini_section}{roof_section}
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
{review_request}
"""

    if use_sqm_unit_price:
        markdown = (
            markdown.replace("平均坪単価", "平均平米単価")
            .replace("中央値坪単価", "中央値平米単価")
            .replace("坪単価", "平米単価")
            .replace("円/坪", "円/㎡")
        )
    return markdown


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
    try:
        source_data = json.loads(source_json.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        source_data = {}
    minimini_gate = validate_minimini_snapshot(source_data)
    blocking_checks = {
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
    advisory_checks = {
        "minimini_available": bool(minimini_gate.get("ok")),
    }
    checks = {**blocking_checks, **advisory_checks}
    from core.task_closure import build_task_closure

    closure = build_task_closure(
        latest_user_request=f"Generate and verify reproducible Products daily report for {TASK_NAME} {report_date}",
        changed_files=[str(out_md), str(copy_json), str(source_json), str(script_provenance.get("script_path") or "")],
        acceptance_checks=[
            {
                "name": name,
                "status": "passed" if ok else "failed",
                "evidence": "read_after_write_checks",
            }
            for name, ok in blocking_checks.items()
        ],
        remaining_blockers=[name for name, ok in blocking_checks.items() if not ok],
        notes=(
            "minimini is advisory; the report may complete with an explicit unavailability note."
            if not advisory_checks["minimini_available"]
            else ""
        ),
    )
    task_results_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = task_results_dir / f"anjo-1k-daily-products-draft-{report_date.replace('-', '')}.json"
    evidence = {
        "status": "done" if closure["can_submit"] else "blocked",
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
        "blocking_read_after_write_checks": blocking_checks,
        "advisory_checks": advisory_checks,
        "completion_policy": {
            "minimini_required": False,
            "minimini_unavailable_action": "complete_with_note",
        },
        "warnings": (
            [
                {
                    "code": "minimini_unavailable",
                    "message": "minimini掲載一覧は取得未完了ですが、補助情報のため注記付きで完了できます。",
                    "reasons": minimini_gate.get("reasons", []),
                }
            ]
            if not advisory_checks["minimini_available"]
            else []
        ),
        "minimini_completion_gate": minimini_gate,
        "discord_thread_id": DISCORD_THREAD_ID,
        "script_path": script_provenance.get("script_path"),
        "script_sha256": script_provenance.get("script_sha256"),
        "script_size_bytes": script_provenance.get("script_size_bytes"),
        "script_py_compile_ok": script_provenance.get("checks", {}).get("py_compile_ok"),
        "script_provenance": script_provenance,
        "task_closure": closure,
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
    if not evidence["minimini_completion_gate"]["ok"]:
        notification = send_minimini_unavailable_notification(
            code=code,
            report_date=report_date,
            report_path=out_md,
            source_json=source_json,
            gate=evidence["minimini_completion_gate"],
            task_results_dir=task_results_dir,
        )
        evidence["minimini_notification"] = notification
        Path(evidence["evidence_path"]).write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(evidence, ensure_ascii=False))
    return 0 if evidence["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
