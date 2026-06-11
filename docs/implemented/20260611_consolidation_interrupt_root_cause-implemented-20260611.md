---
issue: 222
title: Daily consolidation interrupt root cause
date: 2026-06-11
---

# Daily Consolidation Interrupt Root Cause

The observed "[Session interrupted by user]" failures at roughly 30-37 minutes were caused by the supervisor scheduler, not by the consolidation agent deciding to stop.

`core/supervisor/_mgr_scheduler.py` sent `run_consolidation` IPC requests with a fixed `timeout=1800.0`. On timeout it logged `consolidation_timeout` and immediately sent an `interrupt` request to the child Anima. The child then surfaced that interrupt as a user-style session interruption during Phase B.

Mitigation implemented:

- daily IPC timeout is now sized from the actual workload gate counts: activity entries, recent episodes, and pending Phase B carryover;
- weekly IPC timeout is separately configurable;
- Phase B max-turns completion is returned as a normal `truncated` consolidation result with an explicit marker;
- Phase B carryover remains durable after timeout or truncation so the next daily trigger resumes the unprocessed source bundle instead of starting from scratch.

The 7-day completion-rate acceptance item still requires live runtime observation after deployment.
