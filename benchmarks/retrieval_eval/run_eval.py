from __future__ import annotations

import argparse
import copy
import json
import math
import signal
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.retrieval_eval.build_dataset import _default_data_dir

VARIANT_OVERRIDES: dict[str, dict[str, bool]] = {
    "baseline": {},
    "no_rerank": {"rerank_enabled": False},
    "no_entity_boost": {"entity_boost_enabled": False},
    "no_temporal_boost": {"temporal_boost_enabled": False},
    "no_access_boost": {"access_boost_enabled": False},
    "minimal": {
        "rerank_enabled": False,
        "entity_boost_enabled": False,
        "temporal_boost_enabled": False,
        "access_boost_enabled": False,
        "enable_spreading_activation": False,
        "entity_registry_enabled": False,
        "entity_aware_graph_enabled": False,
        "graph_cache_enabled": False,
        "graph_inverse_fan_enabled": False,
        "graph_recency_weight_enabled": False,
    },
}
# minimal pipeline with the cross-encoder rerank kept on
VARIANT_OVERRIDES["minimal_rerank"] = {**VARIANT_OVERRIDES["minimal"], "rerank_enabled": True}


def variant_settings(config: Any, variant: str) -> dict[str, Any]:
    """Return independent settings for a variant without mutating config."""
    if variant not in VARIANT_OVERRIDES:
        raise ValueError(f"Unknown retrieval variant: {variant}")
    if isinstance(config, dict):
        settings = copy.deepcopy(config)
    elif callable(getattr(config, "model_dump", None)):
        settings = copy.deepcopy(config.model_dump())
    else:
        raise TypeError("config must be a dict or a schema-backed config model")
    settings.update(VARIANT_OVERRIDES[variant])
    # The production search_memory tool uses the tool trigger policy's fixed pool.
    # Supplying copied settings to inject ablation flags must not change that pool.
    from core.memory.retrieval.unified_search import TRIGGER_POLICIES

    settings["rerank_candidate_pool"] = TRIGGER_POLICIES["tool"].pool_k
    return settings


def _normalize_path(value: Any, anima_dir: Path | None = None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = value.strip().replace("\\", "/").split("#", 1)[0]
    if anima_dir is not None:
        try:
            path = Path(path).resolve().relative_to(anima_dir.resolve()).as_posix()
        except (OSError, ValueError):
            pass
    path = path.lstrip("/")
    while path.startswith("./"):
        path = path[2:]
    return path or None


def _ranked_paths(results: list[dict[str, Any]], anima_dir: Path) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for item in results:
        path = _normalize_path(item.get("source_file") or item.get("doc_id") or item.get("path"), anima_dir)
        if path is not None and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def score_query(gold_paths: list[str], ranked_paths: list[str]) -> dict[str, float]:
    """Compute document-path metrics, counting a file at its first result rank."""
    gold = {_normalize_path(path) for path in gold_paths}
    gold.discard(None)
    ranked = [_normalize_path(path) for path in ranked_paths]
    ranked = [path for path in ranked if path is not None]
    if not gold:
        return {"recall@5": 0.0, "recall@10": 0.0, "mrr": 0.0, "hit@10": 0.0}
    relevant_ranks = [index for index, path in enumerate(ranked, start=1) if path in gold]
    return {
        "recall@5": len({path for path in ranked[:5] if path in gold}) / len(gold),
        "recall@10": len({path for path in ranked[:10] if path in gold}) / len(gold),
        "mrr": 1.0 / relevant_ranks[0] if relevant_ranks else 0.0,
        "hit@10": 1.0 if any(rank <= 10 for rank in relevant_ranks) else 0.0,
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    fraction = position - lower
    return round(ordered[lower] * (1 - fraction) + ordered[upper] * fraction, 3)


def aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in rows if not row["failed"]]
    latencies = [float(row["latency_ms"]) for row in rows]
    metrics: dict[str, Any] = {
        "queries": len(rows),
        "successful": len(successful),
        "failed": len(rows) - len(successful),
        "recall@5": 0.0,
        "recall@10": 0.0,
        "mrr": 0.0,
        "hit@10": 0.0,
        "latency_p50_ms": _percentile(latencies, 0.5),
        "latency_p90_ms": _percentile(latencies, 0.9),
    }
    if successful:
        for metric in ("recall@5", "recall@10", "mrr", "hit@10"):
            metrics[metric] = round(sum(float(row[metric]) for row in successful) / len(successful), 4)
    return metrics


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(item, dict)
                and isinstance(item.get("anima"), str)
                and isinstance(item.get("query"), str)
                and item["query"].strip()
                and isinstance(item.get("gold_paths"), list)
                and item["gold_paths"]
            ):
                records.append(item)
    return records


def _time_bounds(time_range: Any) -> tuple[str | None, str | None]:
    if not isinstance(time_range, dict):
        return None, None
    after = time_range.get("after")
    before = time_range.get("before")
    return (str(after) if after is not None else None, str(before) if before is not None else None)


def _search_query(rag_search: Any, item: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    time_start, time_end = _time_bounds(item.get("time_range"))
    return rag_search.search_memory_text(
        item["query"],
        scope=str(item.get("scope") or "all"),
        time_start=time_start,
        time_end=time_end,
        knowledge_dir=rag_search._anima_dir / "knowledge",
        episodes_dir=rag_search._anima_dir / "episodes",
        procedures_dir=rag_search._anima_dir / "procedures",
        common_knowledge_dir=rag_search._common_knowledge_dir,
        pipeline_settings=settings,
        read_only=True,
    )


@contextmanager
def _query_timeout(seconds: float) -> Iterator[None]:
    """Interrupt a slow synchronous query on the main POSIX thread."""
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def timeout_handler(_signum, _frame):
        raise TimeoutError(f"retrieval query exceeded {seconds:g}s")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def _new_rag_search(data_dir: Path, anima: str, vector_store: Any):
    from core.memory.rag.indexer import MemoryIndexer
    from core.memory.retrieval.rag_search import RAGMemorySearch

    anima_dir = data_dir / "animas" / anima
    rag_search = RAGMemorySearch(
        anima_dir,
        data_dir / "common_knowledge",
        data_dir / "common_skills",
    )
    # Evaluation must never trigger cold indexing or index metadata updates.
    rag_search._auto_index_on_access = False
    rag_search._indexer = MemoryIndexer(vector_store, anima, anima_dir)
    rag_search._indexer_initialized = True
    return rag_search


def _run_anima_queries(
    data_dir: Path,
    anima: str,
    queries: list[dict[str, Any]],
    variants: list[str],
    *,
    timeout_seconds: float,
) -> dict[str, list[dict[str, Any]]]:
    from core.memory.rag.cli_access import open_vector_access

    output: dict[str, list[dict[str, Any]]] = {variant: [] for variant in variants}
    anima_dir = (data_dir / "animas" / anima).resolve()
    if not anima_dir.is_relative_to((data_dir / "animas").resolve()) or not anima_dir.is_dir():
        for variant in variants:
            output[variant] = [
                {"anima": anima, "failed": True, "latency_ms": 0.0, "error_type": "AnimaNotFound"} for _ in queries
            ]
        return output

    try:
        access_context = open_vector_access(anima, anima_dir, purpose="retrieval-eval")
        with access_context as access:
            rag_search = _new_rag_search(data_dir, anima, access.store)
            base_settings = rag_search._load_rag_pipeline_settings()
            variant_configs = {variant: variant_settings(base_settings, variant) for variant in variants}
            for variant in variants:
                for item in queries:
                    started = time.perf_counter()
                    try:
                        with _query_timeout(timeout_seconds):
                            results = _search_query(rag_search, item, variant_configs[variant])
                        paths = _ranked_paths(results if isinstance(results, list) else [], anima_dir)
                        scored = score_query(item["gold_paths"], paths)
                        output[variant].append(
                            {
                                "anima": anima,
                                "failed": False,
                                "latency_ms": (time.perf_counter() - started) * 1000,
                                **scored,
                            }
                        )
                    except Exception as exc:
                        output[variant].append(
                            {
                                "anima": anima,
                                "failed": True,
                                "latency_ms": (time.perf_counter() - started) * 1000,
                                "error_type": type(exc).__name__,
                            }
                        )
    except Exception as exc:
        error_type = type(exc).__name__
        for variant in variants:
            output[variant] = [
                {
                    "anima": anima,
                    "failed": True,
                    "latency_ms": 0.0,
                    "error_type": error_type,
                }
                for _ in queries
            ]
    return output


def evaluate(
    dataset: list[dict[str, Any]],
    data_dir: Path,
    variants: list[str],
    *,
    limit: int | None = None,
    anima: str | None = None,
    timeout_seconds: float = 60,
) -> dict[str, Any]:
    selected = [item for item in dataset if anima is None or item.get("anima") == anima]
    if limit is not None:
        selected = selected[: max(0, limit)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in selected:
        grouped[str(item["anima"])].append(item)

    variant_rows: dict[str, list[dict[str, Any]]] = {variant: [] for variant in variants}
    for anima_name, queries in sorted(grouped.items()):
        anima_rows = _run_anima_queries(
            data_dir,
            anima_name,
            queries,
            variants,
            timeout_seconds=timeout_seconds,
        )
        for variant in variants:
            variant_rows[variant].extend(anima_rows[variant])

    result: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_queries": len(selected),
        "variants": {},
    }
    for variant in variants:
        rows = variant_rows[variant]
        per_anima: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            per_anima[row["anima"]].append(row)
        result["variants"][variant] = {
            "overall": aggregate_metrics(rows),
            "by_anima": {name: aggregate_metrics(items) for name, items in sorted(per_anima.items())},
            "failure_types": dict(sorted(Counter(row["error_type"] for row in rows if row["failed"]).items())),
        }
    return result


def _format_number(value: Any, *, digits: int = 3) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"


def render_report(metrics: dict[str, Any]) -> str:
    variants = metrics["variants"]
    lines = [
        "# Retrieval evaluation report",
        "",
        f"Generated: {metrics['generated_at']}",
        f"Dataset queries: {metrics['dataset_queries']}",
        "",
        "## Overall comparison",
        "",
        "| Variant | Success / failed | Recall@5 | Recall@10 | MRR | Hit@10 | p50 ms | p90 ms | Δ Recall@10 vs baseline |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    baseline = variants.get("baseline", {}).get("overall", {})
    baseline_recall = baseline.get("recall@10")
    for variant, payload in variants.items():
        overall = payload["overall"]
        delta = None if baseline_recall is None else overall["recall@10"] - baseline_recall
        delta_text = "—" if delta is None else f"{delta:+.4f}"
        lines.append(
            "| {variant} | {successful} / {failed} | {r5} | {r10} | {mrr} | {hit} | {p50} | {p90} | {delta} |".format(
                variant=variant,
                successful=overall["successful"],
                failed=overall["failed"],
                r5=_format_number(overall["recall@5"], digits=4),
                r10=_format_number(overall["recall@10"], digits=4),
                mrr=_format_number(overall["mrr"], digits=4),
                hit=_format_number(overall["hit@10"], digits=4),
                p50=_format_number(overall["latency_p50_ms"], digits=1),
                p90=_format_number(overall["latency_p90_ms"], digits=1),
                delta=delta_text,
            )
        )
    lines.extend(
        [
            "",
            "## Per-anima comparison",
            "",
            "| Variant | Anima | Success / failed | Recall@5 | Recall@10 | MRR | Hit@10 | p50 ms | p90 ms |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for variant, payload in variants.items():
        for anima, values in payload["by_anima"].items():
            lines.append(
                f"| {variant} | {anima} | {values['successful']} / {values['failed']} | "
                f"{_format_number(values['recall@5'], digits=4)} | {_format_number(values['recall@10'], digits=4)} | "
                f"{_format_number(values['mrr'], digits=4)} | {_format_number(values['hit@10'], digits=4)} | "
                f"{_format_number(values['latency_p50_ms'], digits=1)} | {_format_number(values['latency_p90_ms'], digits=1)} |"
            )
    lines.extend(
        [
            "",
            "Latency percentiles include both successful and failed attempts. Ranking metrics are averaged over successful queries only.",
            "Gold labels are implicit feedback from subsequent memory-file reads; they are not manually judged and may be biased.",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_variants(value: str) -> list[str]:
    variants = [part.strip() for part in value.split(",") if part.strip()]
    unknown = sorted(set(variants) - set(VARIANT_OVERRIDES))
    if unknown:
        raise ValueError(f"Unknown variants: {', '.join(unknown)}")
    if not variants:
        raise ValueError("At least one variant is required")
    return list(dict.fromkeys(variants))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate memory retrieval variants without writing memory metadata")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--variants", default=",".join(VARIANT_OVERRIDES))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--anima")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--timeout", type=float, default=60, help="Per-query timeout in seconds")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        variants = _parse_variants(args.variants)
    except ValueError as exc:
        parser.error(str(exc))

    data_dir = _default_data_dir().expanduser().resolve()
    dataset_path = (
        args.dataset.expanduser() if args.dataset else data_dir / "benchmarks" / "retrieval_eval" / "queries.jsonl"
    )
    output_root = args.out.expanduser() if args.out else data_dir / "benchmarks" / "retrieval_eval"
    repository_root = Path(__file__).resolve().parents[2]
    if output_root.resolve().is_relative_to(repository_root):
        parser.error("Evaluation output must stay outside the repository")
    try:
        dataset = _load_dataset(dataset_path)
        metrics = evaluate(
            dataset,
            data_dir,
            variants,
            limit=args.limit,
            anima=args.anima,
            timeout_seconds=args.timeout,
        )
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        results_dir = output_root / "results" / timestamp
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report = render_report(metrics)
        (results_dir / "report.md").write_text(report, encoding="utf-8")
    except Exception as exc:
        print(f"Evaluation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Evaluated {metrics['dataset_queries']} queries; results: {results_dir}")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
