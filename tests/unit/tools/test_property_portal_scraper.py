# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import httpx

from core.tools.property_portal_scraper import (
    PortalConfig,
    extract_listings,
    parse_price_jpy,
    run_scan,
)


def test_parse_price_jpy_handles_oku_and_man() -> None:
    price_text, price_jpy = parse_price_jpy("1 億 5,300 万円")

    assert price_text == "1 億 5,300 万円"
    assert price_jpy == 153_000_000


def test_parse_price_jpy_handles_man_only() -> None:
    price_text, price_jpy = parse_price_jpy("価格相場 15300万円")

    assert price_text == "15300万円"
    assert price_jpy == 153_000_000


def test_parse_price_jpy_ignores_plain_yen_amounts() -> None:
    price_text, price_jpy = parse_price_jpy("年間収入／4,440,000円")

    assert price_text == ""
    assert price_jpy is None


def test_parse_price_jpy_prefers_amount_after_price_label() -> None:
    price_text, price_jpy = parse_price_jpy("年収入想定約1177万円 価格 1億1500万円")

    assert price_text == "1億1500万円"
    assert price_jpy == 115_000_000


def test_extract_listings_from_sumadepa_like_anchor() -> None:
    html = """
    <html><body>
      <a href="/bkn123/">
        一棟マンション 安城市 相生町 ☆ メトロヒルズ安城 ☆
        1 億 5,300 万円 利回り： - - / 665.66㎡ / 3DK /築31年 /4階建
        東海道本線 「 安城 」駅 徒歩7分
      </a>
      <a href="/privacy/">プライバシーポリシー</a>
    </body></html>
    """

    listings = extract_listings(
        html,
        base_url="https://www.sumadepa.com/area3t1/city_cr23212/",
        portal="sumadepa_anjo",
        portal_label="住まいのデパート 安城",
        max_listings=10,
        min_gross_yield_percent=None,
    )

    assert len(listings) == 1
    listing = listings[0]
    assert listing.property_type == "一棟マンション"
    assert listing.price_jpy == 153_000_000
    assert listing.area_sqm == 665.66
    assert listing.building_age_years == 31
    assert listing.url == "https://www.sumadepa.com/bkn123/"


def test_extract_listings_from_kenbiya_spaced_percent() -> None:
    html = """
    <a href="/pp3/t/aichi/anjo-shi/re_44553444in/">
      愛知県安城市 一棟マンション 愛知県安城市今本町3-6-13
      名鉄西尾線 新安城駅 歩10分 1 億 1,500 万円
      10 .23 ％ 建:507.37m² 土:208.33m²
    </a>
    """

    listings = extract_listings(
        html,
        base_url="https://www.kenbiya.com/pp2_3/t/kw=%E5%AE%89%E5%9F%8E/",
        portal="kenbiya_anjo",
        portal_label="健美家 安城",
        max_listings=10,
        min_gross_yield_percent=8.0,
    )

    assert len(listings) == 1
    assert listings[0].gross_yield_percent == 10.23
    assert listings[0].area_sqm == 507.37
    assert listings[0].review_status == "passes_min_gross_yield"


def test_extract_listings_from_plain_brokerage_result_text() -> None:
    html = """
    <html><body>
      ベリスタ安城 物件詳細 ■JR東海道本線「安城」駅まで徒歩3分
      画像枚数15枚 価格 3,050 万円 物件種別 マンション（区分）
      想定利回り ※ 5.5 % 所在地 愛知県安城市朝日町
      交通 東海道本線 「 安城 」駅 徒歩3分 間取り/専有面積 3LDK / 75.4 m²
      条件で絞り込む
    </body></html>
    """

    listings = extract_listings(
        html,
        base_url="https://www.stepon.co.jp/pro/area_23/list_23_212/cs_25_04/",
        portal="stepon_anjo_section",
        portal_label="住友不動産ステップ 安城 区分",
        max_listings=10,
        min_gross_yield_percent=8.0,
    )

    assert len(listings) == 1
    assert listings[0].property_type == "マンション（区分）"
    assert listings[0].price_jpy == 30_500_000
    assert listings[0].gross_yield_percent == 5.5
    assert listings[0].area_sqm == 75.4
    assert listings[0].review_status == "below_min_gross_yield"


class _FakeClient:
    def __init__(self, html: str, *, page_status: int = 200) -> None:
        self.html = html
        self.page_status = page_status
        self.closed = False

    def get(self, url: str, **_kwargs):
        request = httpx.Request("GET", url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *\nDisallow:\n", request=request)
        return httpx.Response(self.page_status, text=self.html, request=request)

    def close(self) -> None:
        self.closed = True


def test_run_scan_records_portal_status_without_live_http() -> None:
    html = """
    <a href="/detail/1">一棟アパート 安城市 桜町 4,800万円 利回り：8.2% / 180㎡ /築22年 安城駅 徒歩12分</a>
    """
    client = _FakeClient(html)

    result = run_scan(
        portals=[PortalConfig(name="test", label="テスト", url="https://example.test/list")],
        min_delay_seconds=0,
        min_gross_yield_percent=8.0,
        client=client,  # type: ignore[arg-type]
    )

    assert len(result.portal_runs) == 1
    run = result.portal_runs[0]
    assert run.fetched is True
    assert run.http_status == 200
    assert run.robots.status == "allowed"
    assert run.listing_count == 1
    assert run.listings[0].review_status == "passes_min_gross_yield"


def test_run_scan_reports_http_errors() -> None:
    result = run_scan(
        portals=[PortalConfig(name="test", label="テスト", url="https://example.test/list")],
        min_delay_seconds=0,
        client=_FakeClient("", page_status=403),  # type: ignore[arg-type]
    )

    run = result.portal_runs[0]
    assert run.fetched is False
    assert run.http_status == 403
    assert run.error == "http_403"
