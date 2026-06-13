"""notebooklm_ask.py — thin, measured wrapper around `notebooklm ask` (GEN-019 Phase 1).

Why this exists
---------------
NotebookLM Memory NB is written to nightly but `notebooklm-py` keeps NO native ask
history (GEN-019 Phase 0: `~/.notebooklm/` has config/last_sync/profiles only — no
query log). So "is the archive actually consumed?" is unmeasurable unless we log it
ourselves. This wrapper is the single measurement point: every successful ask appends
one `event:"ask"` row to the shared consumption ledger, which the daily-ops dashboard
renders next to TaskDiary generated/adopted.

It also fixes the Claude-Code-Bash streaming bug (notebooklm ask dies with exit 255 in
Claude Code's Bash subprocess, notebooklm_usage.md) by always shelling out through
PowerShell, so the deterministic weekly cron step never hits that trap.

Usage
-----
  python notebooklm_ask.py --query "..." --project Finance [--out <md>] [--no-log]
  python notebooklm_ask.py --batch <questions.json>   # [{"project","query"}...]

Exit 0 if at least one ask succeeded; 1 if all asks failed (rate limit / auth / API).
Failures are NOT logged to the ledger — only answered asks count as consumption, so a
zero-streak on the dashboard means real consumption stopped, not that the API blipped.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# same-dir helper (scripts/ is on sys.path when run as a script or via -m)
try:
    from consumption_metrics import EVENT_ASK, SOURCE_NOTEBOOKLM
    from consumption_metrics import log_event as log_consumption_event
    from consumption_metrics import read_rows as read_ledger_rows
except ImportError:  # pragma: no cover - logging is best-effort
    log_consumption_event = None  # type: ignore[assignment]
    read_ledger_rows = None  # type: ignore[assignment]

JST = timezone(timedelta(hours=9))
MEMORY_NB = "19d12bde-9c01-47f6-bcf9-d0838104b20c"

# Answers land here by default so a human / the weekly review LLM can read what the
# deterministic ask surfaced. One dated file per run, project sections appended.
DEFAULT_OUT_DIR = Path(
    r"E:\OneDriveBiz\Obsidian\_ai_rules\_inbox\_notebooklm"
)

RATE_LIMIT_MARKERS = ("rate limited", "rate-limited", "429", "quota")


def _ps_quote(s: str) -> str:
    """Quote a string as a PowerShell single-quoted literal ('' escapes ')."""
    return "'" + s.replace("'", "''") + "'"


def ask_once(query: str, notebook: str, timeout: int) -> tuple[bool, str]:
    """Run one `notebooklm ask` through PowerShell. Returns (ok, text)."""
    # Build the command line PowerShell will execute. notebooklm resolves to the npm
    # shim on PATH; single-quote the query so spaces/JP text survive intact.
    inner = f"notebooklm ask {_ps_quote(query)} -n {_ps_quote(notebook)}"
    cmd = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        inner,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Error: timed out after {timeout}s"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    text = out or err
    # The CLI prints "Error: ..." and/or a non-zero exit on failure.
    ok = proc.returncode == 0 and bool(out) and not out.lower().startswith("error:")
    if not ok and not text:
        text = f"Error: notebooklm exited {proc.returncode} with empty output"
    return ok, text


def ask_with_retry(
    query: str, notebook: str, timeout: int, retries: int
) -> tuple[bool, str]:
    """Ask with linear backoff on rate-limit responses."""
    last = ""
    for attempt in range(1, retries + 1):
        ok, text = ask_once(query, notebook, timeout)
        if ok:
            return True, text
        last = text
        if attempt < retries and any(m in text.lower() for m in RATE_LIMIT_MARKERS):
            time.sleep(15 * attempt)  # 15s, 30s, ...
            continue
        break
    return False, last


def asks_done_today(required: int) -> bool:
    """True if today's ledger already has >= `required` successful notebooklm asks.

    Lets the time-windowed Monday cron (`*/20 5-9 * * 1`) retry across rate limits:
    every tick re-runs, but once the batch has fully succeeded for the day this
    returns True so later ticks NOOP instead of re-asking.
    """
    if read_ledger_rows is None:
        return False
    today = datetime.now(JST).date().isoformat()
    try:
        n = sum(
            1
            for r in read_ledger_rows()
            if r.get("date") == today
            and r.get("source") == SOURCE_NOTEBOOKLM
            and r.get("event") == EVENT_ASK
        )
    except Exception:
        return False
    return n >= required


def append_answer(out_path: Path, project: str, query: str, answer: str) -> None:
    """Append one project section to the dated digest (best-effort, dedup by query)."""
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Dedup: on a catch-up retry tick, don't re-append a question already answered today.
        if out_path.exists() and query in out_path.read_text(encoding="utf-8"):
            return
        now = datetime.now(JST)
        block = (
            f"\n## {project} — {now.strftime('%H:%M')}\n\n"
            f"**Q:** {query}\n\n{answer}\n"
        )
        header = ""
        if not out_path.exists():
            header = (
                "---\n"
                "ai-first: true\n"
                "confidence: stated\n"
                "source_kind: notebooklm_ask\n"
                f"date: {now.date().isoformat()}\n"
                "---\n\n"
                "# NotebookLM 週次 ask ダイジェスト\n\n"
                "> 決定論 cron が Memory NB に引いた『runbook 未蒸留の生の経緯』。"
                "週次レビュー(sakura-4)の判定入力。採用に値する手順は decisions JSON 経由で runbook 化する。\n"
            )
        with out_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(header + block)
    except Exception:
        pass


def run_one(
    *,
    project: str,
    query: str,
    notebook: str,
    out_path: Path | None,
    do_log: bool,
    timeout: int,
    retries: int,
) -> bool:
    ok, text = ask_with_retry(query, notebook, timeout, retries)
    stamp = datetime.now(JST).isoformat(timespec="seconds")
    if ok:
        print(f"[OK] {project}: ask answered ({len(text)} chars) @ {stamp}")
        print(text)
        if out_path is not None:
            append_answer(out_path, project, query, text)
        if do_log and log_consumption_event is not None:
            log_consumption_event(
                source=SOURCE_NOTEBOOKLM,
                event=EVENT_ASK,
                project=project,
                count=1,
                extra={"chars": len(text)},
            )
    else:
        # Not logged to the ledger: a failed ask is not consumption.
        print(f"[FAIL] {project}: {text[:200]}", file=sys.stderr)
    return ok


def load_batch(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[dict[str, str]] = []
    for entry in data:
        q = (entry.get("query") or "").strip()
        if not q:
            continue
        items.append({"project": (entry.get("project") or "General").strip(), "query": q})
    return items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measured notebooklm ask wrapper (GEN-019).")
    ap.add_argument("--query", "-q", help="single query string")
    ap.add_argument("--project", "-p", default="General", help="ledger project label")
    ap.add_argument("--batch", help="path to JSON [{project, query}, ...]")
    ap.add_argument("--notebook", "-n", default=MEMORY_NB, help="notebook id")
    ap.add_argument("--out", help="digest md path (default: dated file under _inbox/_notebooklm)")
    ap.add_argument("--no-out", action="store_true", help="do not write a digest file")
    ap.add_argument("--no-log", action="store_true", help="do not append to the consumption ledger")
    ap.add_argument("--timeout", type=int, default=180, help="per-ask timeout seconds")
    ap.add_argument("--retries", type=int, default=3, help="attempts per query (backoff on rate limit)")
    ap.add_argument(
        "--skip-if-done",
        action="store_true",
        help="NOOP if today's ledger already has >= len(batch) successful asks "
        "(for the time-windowed Monday cron to stop re-asking once done)",
    )
    args = ap.parse_args(argv)

    if args.batch:
        items = load_batch(Path(args.batch))
    elif args.query:
        items = [{"project": args.project, "query": args.query}]
    else:
        ap.error("either --query or --batch is required")
        return 2  # unreachable

    if not items:
        print("[NOOP] no queries to ask")
        return 0

    if args.skip_if_done and asks_done_today(len(items)):
        print(f"NOOP_ALREADY_ASKED: {len(items)} ask(s) already logged today")
        return 0

    out_path: Path | None
    if args.no_out:
        out_path = None
    elif args.out:
        out_path = Path(args.out)
    else:
        day = datetime.now(JST).date().isoformat()
        out_path = DEFAULT_OUT_DIR / f"{day}-notebooklm-ask.md"

    any_ok = False
    for it in items:
        ok = run_one(
            project=it["project"],
            query=it["query"],
            notebook=args.notebook,
            out_path=out_path,
            do_log=not args.no_log,
            timeout=args.timeout,
            retries=args.retries,
        )
        any_ok = any_ok or ok

    return 0 if any_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
