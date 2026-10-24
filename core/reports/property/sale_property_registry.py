"""Persistent physical-property numbers, independent of portal and asking price."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalized(value: object) -> str:
    if value is None or str(value).lower() == "nan":
        return ""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value)))


def listing_url(value: object) -> str:
    parts = urlsplit(str(value or "").strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.startswith("utm_")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def physical_features(row: dict) -> dict:
    raw = normalized(row.get("raw_text"))

    def capture(pattern: str) -> str:
        match = re.search(pattern, raw)
        return match.group(1) if match else ""

    building = capture(r"(?:建物|建[:：])([\d,.]+)(?:㎡|m[2²])")
    land = capture(r"(?:土地|土[:：])([\d,.]+)(?:㎡|m[2²])")
    built = capture(r"((?:19|20)\d{2}年\d{1,2}月)")
    if built:
        year, month = re.findall(r"\d+", built)
        built = f"{year}-{int(month):02d}"
    units = capture(r"総戸数[:：]?(\d+)戸") or capture(r"[/／](\d+)戸")
    address = capture(r"愛知県(.*?)(?:交通|名鉄|JR|地下鉄|近鉄)")
    if not address:
        address = normalized(row.get("location_hint"))
    address = re.sub(r"(丁目|番地|番|号)", "-", address).removeprefix("愛知県").removesuffix("他").rstrip("-")
    city = re.search(r"(.+?[市区町村])", address)
    town = re.sub(r"\d.*$", "", address)
    return {
        "building": str(float(building.replace(",", ""))) if building else "",
        "land": str(float(land.replace(",", ""))) if land else "",
        "built": built, "units": units, "city": city.group(1) if city else "", "town": town, "address": address,
    }


def same_physical_property(left: dict, right: dict) -> bool:
    required = ("building", "land", "built", "units", "city")
    if not all(left.get(k) and left[k] == right.get(k) for k in required):
        return False
    # Partial addresses are common; remove the shared city before comparing town suffixes.
    lt = left["town"].removeprefix(left["city"])
    rt = right["town"].removeprefix(right["city"])
    ln = re.search(r"\d.*$", left.get("address", ""))
    rn = re.search(r"\d.*$", right.get("address", ""))
    if ln and rn:
        a, b = ln.group(), rn.group()
        if not (a == b or a.startswith(b + "-") or b.startswith(a + "-")):
            return False
    return bool(lt and rt and (lt.endswith(rt) or rt.endswith(lt)))


class PropertyRegistry:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, timeout=30)
        self.conn.execute("CREATE TABLE IF NOT EXISTS properties (id INTEGER PRIMARY KEY AUTOINCREMENT, features TEXT NOT NULL)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id))")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def assign(self, rows: list[dict]) -> list[dict]:
        """One transaction prevents competing cron runs from issuing different IDs."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            output = [self._assign(row) for row in rows]
            self.conn.commit()
            return output
        except Exception:
            self.conn.rollback()
            raise

    def _assign(self, row: dict) -> dict:
        features = physical_features(row)
        url = listing_url(row.get("url"))
        if not url:
            raise ValueError("Property numbering requires a listing URL")
        # Listing/search pages may contain multiple properties. Do not treat their URL as a property ID.
        path = urlsplit(url).path
        detail = bool(path.strip("/")) and not re.search(r"/(?:area_|list|search|cs_)", path)
        alias = url if detail else url + "|" + json.dumps(features, ensure_ascii=False, sort_keys=True) + "|" + normalized(row.get("title"))
        existing = self.conn.execute("SELECT property_id FROM aliases WHERE alias=?", (alias,)).fetchone()
        method = "url_alias"
        if existing:
            number = existing[0]
            old = json.loads(self.conn.execute("SELECT features FROM properties WHERE id=?", (number,)).fetchone()[0])
            enriched = {k: old.get(k) or v for k, v in features.items()}
            if len(features.get("address", "")) > len(old.get("address", "")):
                enriched["address"] = features["address"]
            if enriched != old:
                self.conn.execute("UPDATE properties SET features=? WHERE id=?", (json.dumps(enriched, ensure_ascii=False), number))
        else:
            candidates = [number for number, data in self.conn.execute("SELECT id, features FROM properties")
                          if same_physical_property(features, json.loads(data))]
            method = "physical_features" if len(candidates) == 1 else "new_property"
            if len(candidates) == 1:
                number = candidates[0]
            else:
                cursor = self.conn.execute("INSERT INTO properties(features) VALUES (?)", (json.dumps(features, ensure_ascii=False),))
                number = cursor.lastrowid
                if len(candidates) > 1:
                    method = "ambiguous_separate"
            self.conn.execute("INSERT INTO aliases(alias,property_id) VALUES (?,?)", (alias, number))
        return {**row, "property_id": f"PROP-{number:06d}", "property_match_method": method}


def number_report(result: dict, comparison: dict | None, registry_path: Path, history_root: Path) -> dict:
    """Enrich working data; leave the original scraper JSON/CSV and their hashes intact."""
    first_run = not registry_path.exists()
    registry = PropertyRegistry(registry_path)
    try:
        if first_run:
            for path in sorted(history_root.glob("*/*/*/P-*_daily-sale-info-*.json")):
                saved = json.loads(path.read_text(encoding="utf-8-sig"))
                registry.assign([r for run in saved.get("portal_runs", []) for r in run.get("listings", [])])
        for run in result.get("portal_runs", []):
            run["listings"] = registry.assign(run.get("listings", []))
        for key in ("new_rows", "continued_rows", "deleted_rows", "unconfirmed_rows"):
            if comparison and key in comparison:
                comparison[key] = registry.assign(comparison[key])
        rows = [r for run in result.get("portal_runs", []) for r in run.get("listings", [])]
        return {"registry_path": str(registry_path), "listing_count": len(rows),
                "property_count": len({r["property_id"] for r in rows}),
                "listings": rows, "version": 1}
    finally:
        registry.close()
