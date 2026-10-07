#!/usr/bin/env python3
"""Generate deterministic fictional JSONL data for enclave demonstrations."""

from __future__ import annotations

import argparse
import json
import logging
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_SEED = 20261006
_CUSTOMER_COUNT = 100
_TICKET_COUNT = 300

_SURNAMES = [
    ("青葉", "あおば"),
    ("水野", "みずの"),
    ("風間", "かざま"),
    ("星野", "ほしの"),
    ("月岡", "つきおか"),
    ("森川", "もりかわ"),
    ("白石", "しらいし"),
    ("夏目", "なつめ"),
    ("朝倉", "あさくら"),
    ("若葉", "わかば"),
    ("高原", "たかはら"),
    ("小春", "こはる"),
    ("桐谷", "きりたに"),
    ("花村", "はなむら"),
    ("新井", "あらい"),
    ("海野", "うみの"),
    ("橘", "たちばな"),
    ("秋月", "あきづき"),
    ("長谷", "はせ"),
    ("深町", "ふかまち"),
]
_GIVEN_NAMES = [
    ("葵", "あおい"),
    ("凛", "りん"),
    ("陽菜", "ひな"),
    ("悠", "ゆう"),
    ("結衣", "ゆい"),
    ("蓮", "れん"),
    ("紬", "つむぎ"),
    ("湊", "みなと"),
    ("咲", "さき"),
    ("律", "りつ"),
    ("澪", "みお"),
    ("奏", "かなで"),
    ("千尋", "ちひろ"),
    ("光", "ひかる"),
    ("楓", "かえで"),
    ("海", "かい"),
    ("花", "はな"),
    ("遥", "はるか"),
    ("翼", "つばさ"),
    ("千夏", "ちなつ"),
]
_PREFECTURES = ["北陽県", "青葉県", "水明県", "風見県", "若葉県", "星川県"]
_CITIES = ["桜川市", "朝凪市", "緑町", "月見野市", "白砂町", "森丘市"]
_PLANS = ["ベーシック", "スタンダード", "プレミアム"]
_CATEGORIES = ["アカウント", "ログイン", "契約", "請求", "操作方法"]
_TICKET_BODIES = [
    "設定方法を確認したいです。",
    "画面の表示について案内をお願いします。",
    "手続きの進み方を教えてください。",
    "登録内容を確認する方法を知りたいです。",
]


def _write_jsonl(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")


def generate_mock_dataset(output_dir: Path, *, seed: int = _DEFAULT_SEED) -> tuple[Path, Path]:
    """Write fixed-count customer and ticket datasets and return their paths."""
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    name_pairs = [
        (surname, surname_kana, given, given_kana)
        for surname, surname_kana in _SURNAMES
        for given, given_kana in _GIVEN_NAMES
    ]
    selected_names = rng.sample(name_pairs, _CUSTOMER_COUNT)
    customers: list[dict[str, str]] = []

    for index, (surname, surname_kana, given, given_kana) in enumerate(selected_names, start=1):
        customers.append(
            {
                "customer_id": f"C{index:06d}",
                "name": f"{surname} {given}",
                "kana": f"{surname_kana} {given_kana}",
                "address": (
                    f"{rng.choice(_PREFECTURES)}{rng.choice(_CITIES)}"
                    f"{rng.randint(1, 8)}丁目{rng.randint(1, 20)}-{rng.randint(1, 99)}"
                ),
                "phone": f"000-0000-{index:04d}",
                "email": f"customer{index:03d}@example.invalid",
                "plan": rng.choice(_PLANS),
            }
        )

    base_time = datetime(2026, 10, 1, tzinfo=UTC)
    tickets: list[dict[str, str]] = []
    for index in range(1, _TICKET_COUNT + 1):
        customer = rng.choice(customers)
        body_kind = index % 4
        if body_kind == 0:
            body = f"{customer['name']}です。登録電話番号 {customer['phone']} で問い合わせます。{rng.choice(_TICKET_BODIES)}"
        elif body_kind == 1:
            body = f"{customer['name']}です。{rng.choice(_TICKET_BODIES)}"
        else:
            body = rng.choice(_TICKET_BODIES)

        tickets.append(
            {
                "ticket_id": f"TK{index:06d}",
                "customer_id": customer["customer_id"],
                "created_at": (base_time + timedelta(minutes=rng.randrange(60 * 24 * 45))).isoformat(),
                "category": rng.choice(_CATEGORIES),
                "body": body,
            }
        )

    customers_path = output_dir / "customers.jsonl"
    tickets_path = output_dir / "tickets.jsonl"
    _write_jsonl(customers_path, customers)
    _write_jsonl(tickets_path, tickets)
    return customers_path, tickets_path


def main(argv: list[str] | None = None) -> None:
    """Generate mock JSONL files under the required ``--out`` directory."""
    parser = argparse.ArgumentParser(description="Generate deterministic enclave mock datasets")
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    args = parser.parse_args(argv)

    customers_path, tickets_path = generate_mock_dataset(args.out)
    logger.info(
        "Wrote %d customers to %s and %d tickets to %s",
        _CUSTOMER_COUNT,
        customers_path,
        _TICKET_COUNT,
        tickets_path,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
