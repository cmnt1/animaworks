from __future__ import annotations

from core.outbound_auto import prepare_auto_response_text


def test_prepare_auto_response_text_suppresses_repeated_operational_loop() -> None:
    text = (
        "まずは全体像を見ますね。必要な確認だけしてから最終回答テキストとして返します。"
        "まずは全体像を見直しますね。Discord送信ツールは使わず、最終回答テキストだけで返します。"
        "まずは全体像を再確認しますね。中断前の送信は繰り返さず、必要な確認だけ行います。"
        "まずは全体像を見ますね。外部DMやチャンネル投稿は使わず、この最終回答としてまとめます。"
    )

    assert prepare_auto_response_text(text) == ""


def test_prepare_auto_response_text_keeps_normal_report() -> None:
    text = (
        "安城市は三河安城駅周辺の商業集積と住宅需要を軸に、既存の高浜市レポートと同じ粒度で見ると、"
        "交通利便性、製造業集積、生活利便施設の三点が主要な評価軸になります。\n\n"
        "刈谷市は雇用集積が強く、岡崎市は広域商圏、知立市は交通結節点として比較します。"
    )

    assert prepare_auto_response_text(text) == text
