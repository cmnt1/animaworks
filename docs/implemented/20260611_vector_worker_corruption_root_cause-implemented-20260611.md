# Vector Worker Corruption Root Cause

Date: 2026-06-11

Related issue: GitHub #221

## Root Cause

The observed `disk I/O error (code 522)` and follow-on `no such table` errors were concentrated in the shared Chroma collections (`shared_common_knowledge`, `shared_common_skills`). Those collections are the only high-fan-out indexes rebuilt from shared markdown and read by all Animas, so a failed write left the shared collection database in a bad state while the indexer kept retrying immediately.

The retry storm had two concrete causes:

1. Failed shared-collection writes did not trip a per-collection circuit breaker. The same failing upsert could be attempted again on the next indexing pass.
2. The index metadata hash is only advanced after successful indexing, so a corrupt shared collection looked permanently dirty and was retried indefinitely.

The likely corruption trigger is concurrent or interrupted Chroma/SQLite access on the shared collections. The mitigation is to keep native Chroma access isolated in the vector worker, serialize native operations through the worker executor, and stop shared-collection retry storms as soon as repeated write failures are detected.

## Mitigation

- Vector worker write endpoints now record consecutive failures per owner/collection/operation.
- After the configured failure threshold, the worker opens a per-collection circuit breaker and returns HTTP 429 with `Retry-After` instead of issuing more native writes.
- `/status` exposes open circuit breakers so server status can alert on a shared-search outage.
- Housekeeping keeps only the two newest `vectordb-corrupt-*` quarantine archives per Anima.
- `server-daemon.log`, `vector-worker.log`, and legacy `suppressed_messages.jsonl` files now rotate by size.

## Operational Recovery

To recover a shared collection after the breaker opens:

1. Stop the server or otherwise stop new indexing writes.
2. Move the corrupt vector database directory to a `vectordb-corrupt-*` quarantine path.
3. Restart the vector worker/server.
4. Run a full RAG repair or indexing rebuild from source markdown for shared collections.
5. Confirm `/status` has no open circuit breaker and shared-collection queries return results.

Live steady-state validation still requires observing the deployed vector worker logs and Vector API 500 rate after the rebuilt database is in service.
