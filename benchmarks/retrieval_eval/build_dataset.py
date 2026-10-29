from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import deque
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_since(value: str, *, now: datetime | None = None) -> datetime:
    text = value.strip().lower()
    current = now or datetime.now(UTC)
    duration = re.fullmatch(r"(\d+(?:\.\d+)?)([dh])", text)
    if duration:
        amount = float(duration.group(1))
        unit = duration.group(2)
        return current - timedelta(days=amount if unit == "d" else amount / 24)
    parsed = _parse_timestamp(value)
    if parsed is None:
        try:
            parsed_date = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("--since must be a duration such as 30d or an ISO date/timestamp") from exc
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=UTC)
    return parsed


def _tool_name(entry: dict[str, Any]) -> str:
    raw = entry.get("tool") or entry.get("name") or ""
    name = str(raw).strip().lower()
    for separator in ("__", ".", "/"):
        if separator in name:
            name = name.rsplit(separator, 1)[-1]
    return name


def _parse_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _tool_args(entry: dict[str, Any]) -> dict[str, Any]:
    meta = entry.get("meta")
    if isinstance(meta, dict):
        args = _parse_mapping(meta.get("args"))
        if args is not None:
            return args
    for key in ("args", "arguments", "input", "tool_input"):
        args = _parse_mapping(entry.get(key))
        if args is not None:
            return args
    for key in ("summary", "content"):
        args = _parse_mapping(entry.get(key))
        if args is not None:
            return args
    return {}


def _read_path(entry: dict[str, Any]) -> str | None:
    args = _tool_args(entry)
    raw_path = args.get("path")
    if not isinstance(raw_path, str):
        return None
    path = raw_path.strip().replace("\\", "/").split("#", 1)[0]
    while path.startswith("./"):
        path = path[2:]
    if not path or path.startswith("/") or ".." in path.split("/"):
        return None
    return path


def _iter_entries(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(entry, dict):
                yield entry


def _within_lookahead(
    query_index: int,
    query_ts: datetime | None,
    current_index: int,
    current_ts: datetime | None,
    *,
    lookahead_lines: int,
    window_seconds: float,
) -> bool:
    if current_index - query_index <= lookahead_lines:
        return True
    if query_ts is None or current_ts is None:
        return False
    elapsed = (current_ts - query_ts).total_seconds()
    return 0 <= elapsed <= window_seconds


def extract_anima_queries(
    anima: str,
    activity_files: Iterable[Path],
    *,
    since: datetime,
    per_anima_limit: int = 40,
    lookahead_lines: int = 15,
    window_minutes: float = 10,
) -> list[dict[str, Any]]:
    """Extract implicit-feedback queries for one anima from streamed logs."""
    pending: list[dict[str, Any]] = []
    selected: deque[dict[str, Any]] = deque(maxlen=max(1, per_anima_limit))
    line_index = 0
    query_ordinal = 0
    window_seconds = window_minutes * 60

    for activity_file in sorted(activity_files):
        for entry in _iter_entries(activity_file):
            line_index += 1
            ts = _parse_timestamp(entry.get("ts"))
            active: list[dict[str, Any]] = []
            for item in pending:
                if _within_lookahead(
                    item["line_index"],
                    item["ts"],
                    line_index,
                    ts,
                    lookahead_lines=lookahead_lines,
                    window_seconds=window_seconds,
                ):
                    active.append(item)
                elif item["gold_paths"]:
                    selected.append(_serialize_query(item))
            pending = active

            event_type = str(entry.get("type", "")).lower()
            tool = _tool_name(entry)
            if event_type == "tool_use" and tool == "search_memory":
                if ts is None or ts < since:
                    continue
                args = _tool_args(entry)
                query = args.get("query")
                if not isinstance(query, str) or not query.strip():
                    continue
                query_ordinal += 1
                time_range = args.get("time_range")
                if not isinstance(time_range, dict):
                    time_range = None
                identity = f"{anima}\0{ts.isoformat()}\0{query_ordinal}\0{query}"
                pending.append(
                    {
                        "id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
                        "anima": anima,
                        "query": query.strip(),
                        "scope": str(args.get("scope") or "all"),
                        "time_range": time_range,
                        "ts": ts,
                        "line_index": line_index,
                        "gold_paths": set(),
                    }
                )
            elif event_type == "tool_use" and tool == "read_memory_file":
                path = _read_path(entry)
                if path is None:
                    continue
                for item in pending:
                    item["gold_paths"].add(path)

    for item in pending:
        if item["gold_paths"]:
            selected.append(_serialize_query(item))
    return sorted(selected, key=lambda item: (str(item.get("ts", "")), str(item["id"])))


def _serialize_query(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "anima": item["anima"],
        "query": item["query"],
        "scope": item["scope"],
        "time_range": item["time_range"],
        "gold_paths": sorted(item["gold_paths"]),
        "ts": item["ts"].isoformat(),
    }


def build_dataset(
    data_dir: Path,
    *,
    since: datetime,
    out: Path,
    per_anima_limit: int = 40,
    lookahead_lines: int = 15,
    window_minutes: float = 10,
) -> dict[str, list[dict[str, Any]]]:
    animas_dir = data_dir / "animas"
    result: dict[str, list[dict[str, Any]]] = {}
    for anima_dir in sorted(animas_dir.iterdir() if animas_dir.is_dir() else []):
        activity_dir = anima_dir / "activity_log"
        if not anima_dir.is_dir() or not activity_dir.is_dir():
            continue
        queries = extract_anima_queries(
            anima_dir.name,
            activity_dir.glob("*.jsonl"),
            since=since,
            per_anima_limit=per_anima_limit,
            lookahead_lines=lookahead_lines,
            window_minutes=window_minutes,
        )
        if queries:
            result[anima_dir.name] = queries

    output = out.resolve()
    repository_root = Path(__file__).resolve().parents[2]
    if output.is_relative_to(repository_root):
        raise ValueError("Private query datasets must not be written inside the repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for anima in sorted(result):
            for query in result[anima]:
                stream.write(json.dumps(query, ensure_ascii=False) + "\n")

    counts = {anima: len(queries) for anima, queries in sorted(result.items())}
    total = sum(counts.values())
    gold_count = sum(len(item["gold_paths"]) for queries in result.values() for item in queries)
    average_gold = gold_count / total if total else 0.0
    print(f"Extracted {total} queries across {len(counts)} animas")
    for anima, count in counts.items():
        print(f"  {anima}: {count}")
    print(f"Average gold paths per query: {average_gold:.2f}")
    print(f"Dataset written to {output}")
    return result


def _default_data_dir() -> Path:
    from core.paths import get_data_dir

    return Path(get_data_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a private retrieval-evaluation dataset from activity logs")
    parser.add_argument("--data-dir", type=Path, default=_default_data_dir())
    parser.add_argument("--since", default="30d", help="Lookback duration (e.g. 30d) or ISO date/timestamp")
    parser.add_argument(
        "--out", type=Path, help="Output JSONL (default: <data-dir>/benchmarks/retrieval_eval/queries.jsonl)"
    )
    parser.add_argument("--per-anima-limit", type=int, default=40)
    parser.add_argument("--lookahead-lines", type=int, default=15)
    parser.add_argument("--window-minutes", type=float, default=10)
    args = parser.parse_args(argv)
    if args.per_anima_limit < 1 or args.lookahead_lines < 0 or args.window_minutes < 0:
        parser.error("limits must be positive (lookahead lines and window may be zero)")
    data_dir = args.data_dir.expanduser().resolve()
    output = args.out.expanduser() if args.out else data_dir / "benchmarks" / "retrieval_eval" / "queries.jsonl"
    try:
        build_dataset(
            data_dir,
            since=_parse_since(args.since),
            out=output,
            per_anima_limit=args.per_anima_limit,
            lookahead_lines=args.lookahead_lines,
            window_minutes=args.window_minutes,
        )
    except (OSError, ValueError) as exc:
        print(f"Dataset generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
