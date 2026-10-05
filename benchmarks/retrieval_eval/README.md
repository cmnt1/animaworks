# Retrieval evaluation

This package builds an implicit-feedback query set from activity logs and compares retrieval configurations using the normal `RAGMemorySearch.search_memory_text` retrieval entry point.

## Data location and privacy

The default data directory is the configured AnimaWorks data directory (normally `~/.animaworks`). Private data is written only below:

```text
~/.animaworks/benchmarks/retrieval_eval/
├── queries.jsonl
└── results/<timestamp>/
    ├── metrics.json
    └── report.md
```

`queries.jsonl` contains private search text and must not be committed, copied into a repository, or shared without authorization. The builder rejects an output path inside the source repository. Repository tests use fabricated activity logs only.

The evaluator opens vector data through `core.memory.rag.cli_access.open_vector_access`; it does not open Chroma directly. It disables automatic cold indexing and calls retrieval with `read_only=True`, which suppresses `AccessBatch` flushes so retrieval/access metadata is not written back to memory. Evaluation only writes its dataset and reports under the benchmark output directory.

## Usage

From the repository root, with its project virtualenv:

```bash
.venv/bin/python -m benchmarks.retrieval_eval.build_dataset \
  --data-dir ~/.animaworks \
  --since 30d

.venv/bin/python -m benchmarks.retrieval_eval.run_eval \
  --limit 20 \
  --variants baseline,minimal
```

To generate a smaller dataset, use `--per-anima-limit 40` (the default). `build_dataset.py` also accepts `--out`, `--lookahead-lines` (default 15), and `--window-minutes` (default 10). A read is associated with a prior search if it occurs within either the line lookahead or the time window. Only searches with at least one subsequent read are retained; the most recent queries are kept up to the per-anima limit.

The evaluation runner supports:

- `baseline`: configured production retrieval settings
- `no_rerank`
- `minimal`: rerank, spreading activation, entity registry, entity-aware graph, and graph cache/weight options disabled

Other runner options are `--dataset`, `--variants` (comma-separated), `--limit`, `--anima`, `--out`, and `--timeout` (per-query seconds; default 60). Ranking metrics are calculated for successful queries; failed/timed-out queries are counted separately. Latency percentiles include all attempts. Results contain aggregate metrics and anima names, but not query or memory text.

## Metrics

- **Recall@5 / Recall@10**: fraction of gold file paths present in the first 5 / 10 distinct returned source paths.
- **MRR**: reciprocal rank of the first returned gold file path, averaged across queries.
- **Hit@10**: whether at least one gold file path appears in the first 10 distinct returned paths.
- **p50 / p90**: median and 90th-percentile retrieval latency in milliseconds.

The gold labels are implicit feedback: a file read soon after a search is treated as relevant. They are not manually judged. This creates selection bias (for example, reads may be influenced by other context or by a result not returned by the search), and the evaluation should be interpreted as a comparative diagnostic rather than an absolute relevance benchmark.
