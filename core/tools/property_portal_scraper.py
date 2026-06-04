# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""PROP-07 property sale portal monitor.

The tool is intentionally conservative: it fetches configured sale/investment
listing pages, records fetch/robots status, and extracts likely property
anchors into a small normalized report for Anima daily reporting.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx


EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "run": {"expected_seconds": 45, "background_eligible": True},
}


DEFAULT_USER_AGENT = "AnimaWorks-PROP07-PropertyMonitor/0.1"
DEFAULT_OUTPUT_DIR = Path("reports") / "property_portals"
DEFAULT_MIN_DELAY_SECONDS = 3.0


DEFAULT_PORTALS: tuple[dict[str, str], ...] = (
    {
        "name": "at_home_toushi_anjo",
        "label": "アットホーム投資",
        "url": "https://toushi-athome.jp/bklist?ITEM=ei&ART=42",
    },
    {
        "name": "rakumachi_anjo",
        "label": "楽待 安城",
        "url": (
            "https://www.rakumachi.jp/syuuekibukken/area/prefecture/dimAll/"
            "?area%5B%5D=23212&newly=&price_from=&price_to=&gross_from=&gross_to="
            "&dim%5B%5D=1001&dim%5B%5D=1002&year_from=&year_to=&b_area_from="
            "&b_area_to=&houses_ge=&houses_le=&min=&l_area_from=&l_area_to="
            "&keyword=%E5%AE%89%E5%9F%8E&ex_real_search="
        ),
    },
    {
        "name": "kenbiya_anjo",
        "label": "健美家 安城",
        "url": "https://www.kenbiya.com/pp2_3/t/kw=%E5%AE%89%E5%9F%8E/",
    },
    {
        "name": "sumadepa_anjo",
        "label": "住まいのデパート 安城",
        "url": "https://www.sumadepa.com/area3t1/city_cr23212/",
    },
    {
        "name": "stepon_anjo_section",
        "label": "住友不動産ステップ 安城 区分",
        "url": "https://www.stepon.co.jp/pro/area_23/list_23_212/cs_25_04/",
    },
    {
        "name": "rehouse_anjo_investment",
        "label": "三井のリハウス 安城 投資・事業用",
        "url": "https://www.rehouse.co.jp/buy/tohshi/prefecture/23/city/23212/",
    },
    {
        "name": "livable_anjo_yield4",
        "label": "東急リバブル 安城 利回り4%以上",
        "url": "https://www.livable.co.jp/fudosan-toushi/tatemono-aichi-select-area/a23212/conditions-yield%3D4/",
    },
    {
        "name": "nomu_pro_anjo",
        "label": "ノムコム・プロ 安城",
        "url": (
            "https://www.nomu.com/pro/search/?bukken_class=build&new_period=0"
            "&area_ids[]=2312&fw=%E5%AE%89%E5%9F%8E&rosen_tab_id=-1&order=0"
        ),
    },
)


PROPERTY_TYPE_KEYWORDS = (
    "一棟マンション",
    "一棟アパート",
    "一棟ビル",
    "一棟売りマンション",
    "一棟売りアパート",
    "マンション（一棟）",
    "アパート（一棟）",
    "ビル（一棟）",
    "区分マンション",
    "マンション区分",
    "マンション（区分）",
    "収益マンション",
    "収益アパート",
    "売りアパート",
    "売アパート",
    "投資用",
    "店舗・事務所",
    "戸建賃貸",
)

SKIP_LINK_KEYWORDS = (
    "ログイン",
    "お気に入り",
    "お問い合わせ",
    "会社概要",
    "利用規約",
    "プライバシー",
    "サイトマップ",
    "検索",
    "変更",
    "追加する",
    "ブログ",
    "トップページ",
)


@dataclass(frozen=True)
class PortalConfig:
    name: str
    label: str
    url: str


@dataclass
class RobotsStatus:
    allowed: bool
    status: str
    robots_url: str
    error: str = ""


@dataclass
class Listing:
    portal: str
    portal_label: str
    title: str
    url: str
    raw_text: str
    property_type: str = ""
    price_text: str = ""
    price_jpy: int | None = None
    gross_yield_percent: float | None = None
    area_sqm: float | None = None
    building_age_years: int | None = None
    station: str = ""
    location_hint: str = ""
    review_status: str = "needs_review"


@dataclass
class PortalRun:
    portal: str
    portal_label: str
    url: str
    fetched: bool
    http_status: int | None
    robots: RobotsStatus
    listing_count: int
    listings: list[Listing] = field(default_factory=list)
    error: str = ""


@dataclass
class ScanResult:
    generated_at: str
    target: str
    min_gross_yield_percent: float | None
    portal_runs: list[PortalRun]

    @property
    def listings(self) -> list[Listing]:
        return [listing for run in self.portal_runs for listing in run.listings]


class _AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.page_chunks: list[str] = []
        self._href_stack: list[str | None] = []
        self._anchor_chunks: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if tag == "a":
            href = dict(attrs).get("href")
            self._href_stack.append(href)
            self._anchor_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag == "a" and self._href_stack:
            href = self._href_stack.pop()
            text = _normalize_text(" ".join(self._anchor_chunks))
            if href and text:
                self.links.append((href, text))
            self._anchor_chunks = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if data.strip():
            self.page_chunks.append(data)
        if self._href_stack and data.strip():
            self._anchor_chunks.append(data)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _compact_money_text(text: str) -> str:
    return re.sub(r"\s+", "", text).replace(",", "")


def parse_price_jpy(text: str) -> tuple[str, int | None]:
    price_pattern = r"(?:(\d+(?:\.\d+)?)\s*億\s*)?(?:(\d[\d,]*)\s*万)円|(\d+(?:\.\d+)?)\s*億円"
    match = None
    if "価格" in text:
        match = re.search(price_pattern, text[text.find("価格") :])
    if match is None:
        match = re.search(price_pattern, text)
    if not match:
        return "", None
    raw = match.group(0)
    compact = _compact_money_text(raw)
    oku_match = re.search(r"(\d+(?:\.\d+)?)億", compact)
    man_match = re.search(r"(\d+)万", compact)
    total = 0
    if oku_match:
        total += int(float(oku_match.group(1)) * 100_000_000)
    if man_match:
        total += int(man_match.group(1)) * 10_000
    if total == 0:
        return raw, None
    return raw, total


def _extract_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _extract_int(pattern: str, text: str) -> int | None:
    value = _extract_float(pattern, text)
    return int(value) if value is not None else None


def _extract_gross_yield(text: str, price_text: str = "") -> float | None:
    labeled = re.search(r"(?:想定)?利回り\s*[:：]?\s*(?:※)?\s*(\d+(?:\.\d+)?)\s*[%％]", text)
    if labeled:
        return float(labeled.group(1))
    search_text = text
    if price_text and price_text in text:
        search_text = text.split(price_text, 1)[1]
    spaced = re.search(r"(\d+)\s*\.\s*(\d+)\s*[%％]", search_text)
    if spaced:
        return float(f"{spaced.group(1)}.{spaced.group(2)}")
    compact = re.search(r"(\d+(?:\.\d+)?)\s*[%％]", search_text)
    return float(compact.group(1)) if compact else None


def _extract_property_type(text: str) -> str:
    for keyword in PROPERTY_TYPE_KEYWORDS:
        if keyword in text:
            return keyword
    return ""


def _extract_station(text: str) -> str:
    match = re.search(r"([^\s「」]+駅\s*(?:歩|徒歩)\s*\d+分|(?:歩|徒歩)\s*\d+分)", text)
    return _normalize_text(match.group(1)) if match else ""


def _extract_location_hint(text: str) -> str:
    match = re.search(r"(安城市\s*[^\s☆★]*|愛知県\s*安城市\s*[^\s☆★]*)", text)
    return _normalize_text(match.group(1)) if match else ("安城" if "安城" in text else "")


def _is_probable_listing(text: str) -> bool:
    if len(text) < 12:
        return False
    if "安城" not in text:
        return False
    if any(keyword in text for keyword in SKIP_LINK_KEYWORDS):
        return False
    signals = 0
    if _extract_property_type(text):
        signals += 2
    if "安城" in text:
        signals += 1
    if parse_price_jpy(text)[1] is not None:
        signals += 2
    if _extract_gross_yield(text) is not None or re.search(r"利回り\s*[:：]?\s*-", text):
        signals += 1
    if "㎡" in text or "築" in text or "駅" in text:
        signals += 1
    return signals >= 3


def _is_probable_listing_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path
    if "propPrClick" in url or path.startswith("/ar/"):
        return False
    return any(part in path for part in ("/show.html", "/pp2/", "/pp3/", "/bkn", "/detail", "/re_"))


def _listing_title(text: str) -> str:
    price_text, _ = parse_price_jpy(text)
    if price_text:
        before_price = text.split(price_text, 1)[0]
        if before_price.strip():
            return before_price.strip(" -/　")
    return text[:100]


def _extract_text_blocks(full_text: str) -> list[str]:
    type_pattern = "|".join(re.escape(keyword) for keyword in PROPERTY_TYPE_KEYWORDS)
    pattern = re.compile(
        rf"((?:{type_pattern})\s+安城市\b.*?)(?=(?:{type_pattern})\s+安城市\b|安城市の掲載物件|物件種別|該当物件|$)"
    )
    blocks = [_normalize_text(match.group(1)) for match in pattern.finditer(full_text)]

    detail_pattern = re.compile(
        r"((?:[^\s]{2,80}\s+)?物件詳細\s+.{0,260}?価格\s+"
        r"(?:(?:\d+(?:\.\d+)?)\s*億\s*)?(?:\d[\d,]*)\s*万円"
        r".{0,260}?(?:想定)?利回り.{0,80}?[%％].{0,260}?愛知県安城市"
        r".{0,260}?(?:間取り|専有面積|建物面積|土地面積).{0,160}?)"
        r"(?=所在階|築年月|構造|条件で絞り込む|物件種別\s+マンション|物件種別\s+アパート|物件種別\s+ビル|$)"
    )
    blocks.extend(_normalize_text(match.group(1)) for match in detail_pattern.finditer(full_text))
    loose_detail_pattern = re.compile(r"(.{0,120}物件詳細.{0,700}?愛知県安城市.{0,240}?)(?=条件で絞り込む|$)")
    blocks.extend(_normalize_text(match.group(1)) for match in loose_detail_pattern.finditer(full_text))
    return blocks


def _build_listing(
    *,
    text: str,
    href: str,
    base_url: str,
    portal: str,
    portal_label: str,
    min_gross_yield_percent: float | None,
) -> Listing:
    price_text, price_jpy = parse_price_jpy(text)
    gross_yield = _extract_gross_yield(text, price_text)
    review_status = "needs_review"
    if min_gross_yield_percent is not None and gross_yield is not None:
        review_status = "passes_min_gross_yield" if gross_yield >= min_gross_yield_percent else "below_min_gross_yield"

    return Listing(
        portal=portal,
        portal_label=portal_label,
        title=_listing_title(text),
        url=urljoin(base_url, href),
        raw_text=text,
        property_type=_extract_property_type(text),
        price_text=_normalize_text(price_text),
        price_jpy=price_jpy,
        gross_yield_percent=gross_yield,
        area_sqm=_extract_float(r"(\d+(?:\.\d+)?)\s*(?:㎡|m²)", text),
        building_age_years=_extract_int(r"築\s*(\d+)\s*年", text),
        station=_extract_station(text),
        location_hint=_extract_location_hint(text),
        review_status=review_status,
    )


def extract_listings(
    html_text: str,
    *,
    base_url: str,
    portal: str,
    portal_label: str,
    max_listings: int,
    min_gross_yield_percent: float | None,
) -> list[Listing]:
    parser = _AnchorExtractor()
    parser.feed(html_text)
    listings: list[Listing] = []
    seen: set[tuple[str, str]] = set()
    seen_titles: set[str] = set()

    for href, anchor_text in parser.links:
        text = _normalize_text(anchor_text)
        if not _is_probable_listing(text):
            continue
        full_url = urljoin(base_url, href)
        if not _is_probable_listing_url(full_url):
            continue
        key = (full_url.split("#", 1)[0], _listing_title(text))
        title_key = _listing_title(text)
        if key in seen or title_key in seen_titles:
            continue
        seen.add(key)
        seen_titles.add(title_key)
        listings.append(
            _build_listing(
                text=text,
                href=href,
                base_url=base_url,
                portal=portal,
                portal_label=portal_label,
                min_gross_yield_percent=min_gross_yield_percent,
            )
        )
        if len(listings) >= max_listings:
            break

    full_text = _normalize_text(" ".join(parser.page_chunks))
    for text in _extract_text_blocks(full_text):
        if len(listings) >= max_listings:
            break
        if not _is_probable_listing(text):
            continue
        key = (base_url, _listing_title(text))
        title_key = _listing_title(text)
        if key in seen or title_key in seen_titles:
            continue
        seen.add(key)
        seen_titles.add(title_key)
        listings.append(
            _build_listing(
                text=text,
                href=base_url,
                base_url=base_url,
                portal=portal,
                portal_label=portal_label,
                min_gross_yield_percent=min_gross_yield_percent,
            )
        )
    return listings


def _robots_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def check_robots(
    client: httpx.Client,
    url: str,
    *,
    user_agent: str,
    timeout: float,
    respect_robots: bool,
) -> RobotsStatus:
    robots_url = _robots_url(url)
    if not respect_robots:
        return RobotsStatus(allowed=True, status="skipped", robots_url=robots_url)

    try:
        response = client.get(robots_url, timeout=timeout)
    except Exception as exc:
        return RobotsStatus(allowed=True, status="unavailable", robots_url=robots_url, error=str(exc))
    if response.status_code >= 400:
        return RobotsStatus(
            allowed=True,
            status=f"unavailable_http_{response.status_code}",
            robots_url=robots_url,
        )

    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    allowed = parser.can_fetch(user_agent, url)
    return RobotsStatus(allowed=allowed, status="allowed" if allowed else "disallowed", robots_url=robots_url)


def _sleep_for_host(url: str, last_request_by_host: dict[str, float], min_delay_seconds: float) -> None:
    if min_delay_seconds <= 0:
        return
    host = urlparse(url).netloc
    last = last_request_by_host.get(host)
    if last is not None:
        wait = min_delay_seconds - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    last_request_by_host[host] = time.monotonic()


def load_portals(config_path: str | Path | None = None) -> list[PortalConfig]:
    if config_path is None:
        return [PortalConfig(**item) for item in DEFAULT_PORTALS]
    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    items = payload.get("portals", payload) if isinstance(payload, dict) else payload
    return [PortalConfig(**item) for item in items]


def run_scan(
    *,
    portals: list[PortalConfig] | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    min_delay_seconds: float = DEFAULT_MIN_DELAY_SECONDS,
    timeout: float = 30.0,
    respect_robots: bool = True,
    max_listings_per_portal: int = 50,
    min_gross_yield_percent: float | None = None,
    client: httpx.Client | None = None,
) -> ScanResult:
    selected_portals = portals or load_portals()
    own_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=True,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en;q=0.8",
        },
    )
    last_request_by_host: dict[str, float] = {}
    portal_runs: list[PortalRun] = []

    try:
        for portal in selected_portals:
            robots = check_robots(
                http_client,
                portal.url,
                user_agent=user_agent,
                timeout=timeout,
                respect_robots=respect_robots,
            )
            if not robots.allowed:
                portal_runs.append(
                    PortalRun(
                        portal=portal.name,
                        portal_label=portal.label,
                        url=portal.url,
                        fetched=False,
                        http_status=None,
                        robots=robots,
                        listing_count=0,
                        error="blocked_by_robots",
                    )
                )
                continue

            try:
                _sleep_for_host(portal.url, last_request_by_host, min_delay_seconds)
                response = http_client.get(portal.url, timeout=timeout)
                listings: list[Listing] = []
                error = ""
                if response.status_code < 400:
                    listings = extract_listings(
                        response.text,
                        base_url=portal.url,
                        portal=portal.name,
                        portal_label=portal.label,
                        max_listings=max_listings_per_portal,
                        min_gross_yield_percent=min_gross_yield_percent,
                    )
                else:
                    error = f"http_{response.status_code}"
                portal_runs.append(
                    PortalRun(
                        portal=portal.name,
                        portal_label=portal.label,
                        url=portal.url,
                        fetched=response.status_code < 400,
                        http_status=response.status_code,
                        robots=robots,
                        listing_count=len(listings),
                        listings=listings,
                        error=error,
                    )
                )
            except Exception as exc:
                portal_runs.append(
                    PortalRun(
                        portal=portal.name,
                        portal_label=portal.label,
                        url=portal.url,
                        fetched=False,
                        http_status=None,
                        robots=robots,
                        listing_count=0,
                        error=str(exc),
                    )
                )
    finally:
        if own_client:
            http_client.close()

    return ScanResult(
        generated_at=datetime.now(timezone.utc).isoformat(),
        target="投資用不動産・収益物件の売買情報（安城市中心）",
        min_gross_yield_percent=min_gross_yield_percent,
        portal_runs=portal_runs,
    )


def result_to_dict(result: ScanResult) -> dict[str, Any]:
    return asdict(result)


def format_markdown(result: ScanResult) -> str:
    lines = [
        "# PROP-07 投資物件ポータル巡回レポート",
        "",
        f"- 生成時刻(UTC): {result.generated_at}",
        f"- 対象: {result.target}",
        f"- 抽出候補: {len(result.listings)} 件",
    ]
    if result.min_gross_yield_percent is not None:
        lines.append(f"- 一次判定利回り: {result.min_gross_yield_percent:g}% 以上")
    lines.append("")
    lines.append("## ポータル別状況")
    for run in result.portal_runs:
        status = "取得" if run.fetched else "未取得"
        error = f" / {run.error}" if run.error else ""
        lines.append(
            f"- {run.portal_label}: {status}, HTTP={run.http_status}, robots={run.robots.status}, "
            f"候補={run.listing_count}件{error}"
        )
    lines.append("")
    lines.append("## 候補物件")
    if not result.listings:
        lines.append("- 候補物件は抽出されませんでした。HTTP状態・robots状態・ページ構造変更を確認してください。")
        return "\n".join(lines) + "\n"

    for index, listing in enumerate(result.listings, 1):
        yield_text = "-" if listing.gross_yield_percent is None else f"{listing.gross_yield_percent:g}%"
        price = listing.price_text or "-"
        lines.extend(
            [
                f"### {index}. {listing.title}",
                f"- ポータル: {listing.portal_label}",
                f"- 種別: {listing.property_type or '-'}",
                f"- 価格: {price}",
                f"- 表面利回り: {yield_text}",
                f"- 面積/築年: {listing.area_sqm or '-'}㎡ / {listing.building_age_years or '-'}年",
                f"- 立地: {listing.location_hint or '-'} {listing.station or ''}".rstrip(),
                f"- 判定: {listing.review_status}",
                f"- URL: {listing.url}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(result: ScanResult, output_dir: str | Path, *, prefix: str = "prop07") -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = out_dir / f"{prefix}_{stamp}"

    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    csv_path = base.with_suffix(".csv")
    json_path.write_text(json.dumps(result_to_dict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown(result), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "portal_label",
                "title",
                "property_type",
                "price_text",
                "price_jpy",
                "gross_yield_percent",
                "area_sqm",
                "building_age_years",
                "location_hint",
                "station",
                "review_status",
                "url",
                "raw_text",
            ],
        )
        writer.writeheader()
        for listing in result.listings:
            row = asdict(listing)
            writer.writerow({field: row.get(field, "") for field in writer.fieldnames})

    return {"json": str(json_path), "markdown": str(md_path), "csv": str(csv_path)}


def dispatch(name: str, args: dict[str, Any]) -> Any:
    if name != "property_portal_scraper":
        raise ValueError(f"Unknown tool: {name}")
    args.pop("anima_dir", None)
    config_path = args.pop("config_path", None)
    output_dir = args.pop("output_dir", None)
    result = run_scan(portals=load_portals(config_path), **args)
    payload = result_to_dict(result)
    if output_dir:
        payload["outputs"] = write_outputs(result, output_dir)
    return payload


def get_tool_schemas() -> list[dict]:
    return []


def cli_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="animaworks-tool property_portal_scraper")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="Fetch configured property sale portals and report likely listings")
    run_parser.add_argument("--config", help="JSON config path. Defaults to PROP-07 built-in portal list.")
    run_parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for JSON/Markdown/CSV outputs.")
    run_parser.add_argument("--no-write", action="store_true", help="Print only; do not write output files.")
    run_parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    run_parser.add_argument("--min-gross-yield", type=float, help="Optional PROP-01 minimum gross yield threshold.")
    run_parser.add_argument("--delay", type=float, default=DEFAULT_MIN_DELAY_SECONDS, help="Minimum delay per host.")
    run_parser.add_argument("--timeout", type=float, default=30.0)
    run_parser.add_argument("--max-listings-per-portal", type=int, default=50)
    run_parser.add_argument("--ignore-robots", action="store_true", help="Fetch pages without robots.txt checks.")
    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_scan(
            portals=load_portals(args.config),
            min_delay_seconds=args.delay,
            timeout=args.timeout,
            respect_robots=not args.ignore_robots,
            max_listings_per_portal=args.max_listings_per_portal,
            min_gross_yield_percent=args.min_gross_yield,
        )
        if not args.no_write:
            outputs = write_outputs(result, args.output_dir)
        else:
            outputs = {}
        if args.json:
            payload = result_to_dict(result)
            if outputs:
                payload["outputs"] = outputs
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(format_markdown(result))
            if outputs:
                sys.stdout.write("\n## 出力ファイル\n")
                for kind, path in outputs.items():
                    sys.stdout.write(f"- {kind}: {path}\n")


if __name__ == "__main__":
    cli_main(sys.argv[1:])
