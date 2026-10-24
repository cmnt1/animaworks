"""Evidence-linked preliminary investment reports for newly observed sale listings."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime
from pathlib import Path

from core.reports.property.sale_property_registry import normalized, physical_features

SALE_DISCORD_THREAD_ID = "1563692914620637246"


def positive_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def property_name(row: dict) -> str:
    name = str(row.get("property_name") or "").strip()
    if not name:
        explicit = re.search(r"物件名[:：]\s*([^／/・\n]+)", str(row.get("raw_text") or ""))
        if explicit:
            name = explicit.group(1).strip()
    if not name:
        title = str(row.get("title") or "")
        known = re.match(r"([^/／]+?)(?:[/／]安城市|\s+物件詳細)", title)
        if known and not known.group(1).endswith("市"):
            name = known.group(1).strip()
    return name


def analysis_note_name(row: dict) -> str:
    """Use a real property name, or a concise physical description for the Base name column."""
    name = property_name(row)
    if not name:
        features = physical_features(row)
        town = features["town"].removeprefix(features["city"]) or "所在地不明"
        raw = normalized(row.get("raw_text"))
        match = re.search(r"SRC造|鉄骨鉄筋コンクリート造|RC造|鉄筋コンクリート造|鉄骨造|木造|軽量鉄骨造", raw)
        structure = match.group() if match else "構造不明"
        structure = {"RC造": "RC", "鉄筋コンクリート造": "RC", "SRC造": "SRC", "鉄骨鉄筋コンクリート造": "SRC"}.get(structure, structure)
        year = features["built"][:4] + "年" if features["built"] else "築年不明"
        price = positive_number(row.get("price_jpy"))
        price_text = f"{price / 10000:g}万円" if price else "価格不明"
        name = "・".join([town, structure, year, price_text])
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "＿", name).rstrip(" .")[:180]


def note_frontmatter(row: dict, report_date: str, *, trial: bool = False) -> str:
    import json

    name = property_name(row)
    identity = str(row.get("property_id") or row.get("_match_key") or row.get("url"))
    return "\n".join([
        "---", f"日付: {report_date}", f'作成日時: "{datetime.now().strftime("%Y-%m-%d %H:%M")}"',
        f"物件: {json.dumps(name, ensure_ascii=False) if name else ''}", f"物件番号: {row.get('property_id') or '未採番'}",
        f'review_discord_thread_id: "{SALE_DISCORD_THREAD_ID}"',
        '書類名: "投資可否分析' + (' 試行' if trial else '') + '"',
        "タグ:", "  - 新規", "ファイル: []", "auto_generated_sale_analysis: true",
        f"analysis_identity: {hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]}", "---", "",
    ])


def render_analysis(row: dict, report_date: str, source_json: Path, source_sha: str, *, trial: bool = False) -> str:
    price = positive_number(row.get("price_jpy"))
    yield_ = positive_number(row.get("gross_yield_percent"))
    title = str(row.get("title") or "名称未取得").replace("\n", " ")
    decision = "判断保留（価格・利回りまたは詳細資料が不足）"
    if price and yield_:
        decision = (
            "追加調査候補・投資判断は保留（表面利回り8%以上）"
            if yield_ >= 8 else "現行の一次基準では見送り（表面利回り8%未満）"
        )
    lines = [
        f"# {'投資可否分析（試行）' if trial else '新規物件の投資可否分析'}：{title}", "",
        f"- 物件番号: {row.get('property_id') or '未採番'}",
        f"- 分析日: {report_date}", f"- 掲載元: {row.get('portal_label') or '-'}",
        f"- 物件URL: {row.get('url') or '-'}",
        f"- 種別: {row.get('property_type') or '-'}",
        f"- 所在地（掲載値）: {row.get('location_hint') or '未取得'}",
        f"- 最寄駅（掲載値）: {row.get('station') or '未取得'}",
        f"- 築年数（掲載値）: {positive_number(row.get('building_age_years')) or '未取得'}",
        f"- 面積㎡（掲載値・対象面積は原文参照）: {positive_number(row.get('area_sqm')) or '未取得'}",
        f"- 掲載価格: {price:,.0f}円" if price else "- 掲載価格: 未取得",
        f"- 掲載表面利回り: {yield_:g}%" if yield_ else "- 掲載表面利回り: 未取得",
        "", "## 投資可否（一次評価）", "", f"**{decision}**", "",
        "掲載情報を入力にした一次評価。購入可能の確定判断には、現況収支・物件調査・融資条件の確認が必要。",
        "既存掲載から選んだ試行分析で、新規物件ではない。" if trial else "新規は当日の掲載差分を意味する。物件番号は保存台帳の名寄せに基づく。",
        "", "## 収支・融資の感応度試算", "",
    ]
    if price and yield_:
        annual = price * yield_ / 100
        lines += [
            f"掲載価格×表面利回りから逆算した年間収入: {annual:,.0f}円。実収入・満室想定の別は未確認。",
            "以下は比較用の仮定。空室損は上記収入に、運営費は空室控除後収入に適用する。",
            "取得諸費用は価格の8%、借入は価格の80%、元利均等・25年、金利は下表の仮定。",
            "運営費率には税・管理・通常修繕等を仮置き。大型修繕・売却損益・所得税は別途精査。", "",
            "| シナリオ | 空室損 | 運営費率 | 金利 | 年間NOI | 年間返済 | 税引前年間CF | DSCR | 総取得費ベースNOI利回り |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for name, vacancy, expense, rate in [("基本", .10, .25, .03), ("悪化", .20, .35, .05)]:
            noi = annual * (1 - vacancy) * (1 - expense)
            monthly_rate = rate / 12
            repayment = price * .8 * monthly_rate / (1 - (1 + monthly_rate) ** -300) * 12
            lines.append(
                f"| {name} | {vacancy:.0%} | {expense:.0%} | {rate:.0%} | {noi:,.0f}円 | "
                f"{repayment:,.0f}円 | {noi - repayment:,.0f}円 | {noi / repayment:.2f} | {noi / (price * 1.08):.2%} |"
            )
        lines += ["", f"上記仮定の必要自己資金: {price * .28:,.0f}円（頭金20%＋取得諸費用8%、予備費別）。",
                  "CFが負、またはDSCRが1未満のケースでは、試算上の賃貸収益で返済を賄えない。"]
    else:
        lines += ["価格または利回りが未取得・非正数のため、収入・NOI・返済余力は算定不可。数値を補完して再評価する。"]
    lines += [
        "", "## リスクと投資判断に必要な確認", "",
        "- レントロール、実入金、空室期間、周辺成約賃料を取得し、想定収入の妥当性を確認。",
        "- 固定資産税、管理費、修繕履歴・見積り、保険料から実際のNOIを算定。",
        "- 所在地、築年、構造、面積、耐震性、再建築・接道、権利関係、ハザードを確認。",
        "- 金融機関の金利・期間・融資割合を取得し、空室増・金利上昇時のCFを再計算。",
        "- 近隣売買成約・出口価格・売却費用を確認し、保有中と売却時の回収額を検証。",
        "- 上記資料と投資家の目標利回り・予算が揃ってから、購入可否と指値条件を確定。",
        "", "## 根拠", "",
        f"- 保存元JSON: `{source_json}`", f"- 保存元SHA-256: `{source_sha}`", "",
        "事実は掲載価格・掲載利回り等の取得値、試算は明示した仮定。未取得の詳細情報は推定事実として扱わない。", "",
    ]
    age = positive_number(row.get("building_age_years"))
    if age and age >= 30:
        lines += [f"築{age:g}年の掲載値から、修繕費・残存耐用年数・融資期間を重点確認する。", ""]
    if row.get("raw_text"):
        lines += ["## 保存した掲載原文", "", str(row["raw_text"]), ""]
    return "\n".join(lines)


def create_bundle(comparison: dict | None, report_date: str, data_dir: Path,
                  source_json: Path, source_sha: str, *, note_root: Path | None = None) -> dict:
    if not comparison or not comparison.get("comparison_available"):
        return {"status": "comparison_unavailable", "count": 0, "reports": []}
    rows = comparison.get("new_rows") or []
    if not rows:
        return {"status": "no_new_listings", "count": 0, "reports": []}
    folder = note_root if note_root is not None else data_dir / "investment-analysis"
    folder.mkdir(parents=True, exist_ok=True)
    reports = []
    seen = set()
    for row in rows:
        key = str(row.get("property_id") or row.get("_match_key") or row.get("url"))
        if key in seen:
            continue
        seen.add(key)
        token = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        path = folder / f"{analysis_note_name(row)}.md"
        if path.exists():
            header = path.read_text(encoding="utf-8-sig").split("---", 2)
            metadata = header[1] if len(header) > 2 else ""
            same_generated_report = (
                "auto_generated_sale_analysis: true" in metadata
                and f"日付: {report_date}\n" in metadata
                and f"analysis_identity: {token}\n" in metadata
            )
            if not same_generated_report:
                path = folder / f"{analysis_note_name(row)}・{report_date}・{token}.md"
        text = note_frontmatter(row, report_date) + render_analysis(row, report_date, source_json, source_sha)
        duplicates = [r for r in rows if str(r.get("property_id") or r.get("_match_key") or r.get("url")) == key]
        if len(duplicates) > 1:
            text += "\n## 同じ物件番号の重複掲載\n\n試算は先頭掲載の価格・利回りを入力とする。掲載値に差がある場合は売主資料で確認する。\n\n"
            for other in duplicates:
                text += f"- {other.get('portal_label') or '-'}: {other.get('url')} / 価格={other.get('price_jpy')}円 / 表面利回り={other.get('gross_yield_percent')}%\n"
        path.write_text(text, encoding="utf-8")
        reports.append({"path": str(path), "sha256": digest(path), "url": row.get("url"), "title": row.get("title"), "property_id": row.get("property_id")})
    index = folder / f"sale-investment-{report_date}-index.md"
    index.write_text(note_frontmatter({"title": "新規売買物件の投資分析一覧"}, report_date) + "\n".join([
        f"# 新規物件の投資可否分析（{report_date}）", "", f"対象: {len(reports)}物件（{len(rows)}掲載）。個別分析は以下。", "",
        *[f"- {r.get('property_id') or '-'} [{str(r['title'] or '名称未取得').replace('[', '［').replace(']', '］')}]({Path(r['path']).name})" for r in reports], "",
    ]), encoding="utf-8")
    return {"status": "created", "count": len(reports), "listing_count": len(rows), "index_path": str(index),
            "index_sha256": digest(index), "reports": reports}


def validate_bundle(bundle: dict) -> bool:
    if bundle.get("status") in {"comparison_unavailable", "no_new_listings"}:
        return bundle.get("count") == 0 and bundle.get("reports") == []
    reports = bundle.get("reports") or []
    if bundle.get("status") != "created" or not reports or len(reports) != bundle.get("count"):
        return False
    entries = [*reports, {"path": bundle.get("index_path"), "sha256": bundle.get("index_sha256")}]
    return all(entry.get("path") and Path(entry["path"]).is_file()
               and digest(Path(entry["path"])) == entry.get("sha256") for entry in entries)


def validate_evidence_analysis(evidence: dict) -> dict:
    """Allow old evidence; verify every attached report for new-format evidence."""
    bundle = evidence.get("investment_analysis")
    if bundle is None:
        return {}
    comparison = evidence.get("comparison") or {}
    rows = comparison.get("new_rows") or []
    expected = len({r.get("property_id") or r.get("_match_key") or r.get("url") or str(i)
                    for i, r in enumerate(rows)}) if comparison.get("comparison_available") else 0
    if not validate_bundle(bundle) or bundle.get("count") != expected:
        raise RuntimeError("Investment analysis missing, incomplete or SHA-256 mismatch")
    return bundle


def notification_text(bundle: dict) -> str:
    if bundle.get("index_path"):
        return f"\n- 新規物件の投資可否分析: {bundle['count']}物件\n- 別レポート一覧: `{bundle['index_path']}`"
    return ""
