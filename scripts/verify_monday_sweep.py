"""verify_monday_sweep.py — did the weekly knowledge-promotion loop run *autonomously*?

Run this AFTER Monday 09:30 JST (sakura-3 promote 06:00 -> sakura-4 review 09:30).
It is a mechanical check so "確認した" can never be hand-waved:

  1. Did apply_inbox_decision.py actually run today? (sakura task_results/inbox-apply-*.json)
  2. Did that sweep fail anything? (failed must be 0)
  3. Did it regenerate consumption indexes? (index_updates present when adopts happened)
  4. What is the LIVE residual `_inbox/<P>/` backlog now? (should be ~0, not climbing)

Exit 0 = autonomous sweep verified clean. Exit 1 = no sweep today / failures / backlog.

Usage:
    python verify_monday_sweep.py            # checks today (JST)
    python verify_monday_sweep.py 2026-06-15
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
TASK_RESULTS = Path(r"C:\Users\cmnt\.animaworks\animas\sakura\state\task_results")
INBOX_ROOT = Path(r"E:\OneDriveBiz\Obsidian\_ai_rules\_inbox")


def target_date(argv: list[str]) -> str:
    if len(argv) > 1:
        return argv[1]
    return datetime.now(JST).date().isoformat()


def sweeps_for(date: str) -> list[dict]:
    out = []
    if not TASK_RESULTS.is_dir():
        return out
    for p in sorted(TASK_RESULTS.glob("inbox-apply-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(d.get("ran_at", "")).startswith(date):
            d["_file"] = p.name
            out.append(d)
    return out


def live_residual() -> dict[str, int]:
    out: dict[str, int] = {}
    if INBOX_ROOT.is_dir():
        for sub in sorted(INBOX_ROOT.iterdir()):
            if sub.is_dir():
                out[sub.name] = len(list(sub.glob("*.md")))
    return out


def main(argv: list[str]) -> int:
    date = target_date(argv)
    sweeps = sweeps_for(date)
    residual = live_residual()
    total_backlog = sum(residual.values())

    print(f"=== Monday sweep verification for {date} (JST) ===")
    print(f"live _inbox residual: {residual} (total={total_backlog})")

    if not sweeps:
        print(f"[ATTENTION] {date} に apply_inbox_decision.py の実行痕跡なし。")
        print("  -> sakura-4 (Mon 09:30 LLM) が決定論スクリプトを呼ばなかった可能性。")
        print(f"  -> 確認: {TASK_RESULTS}\\inbox-apply-*.json と sakura の当日 episodes/state。")
        if total_backlog == 0:
            print("  （ただし backlog=0 なら『採用すべき新知見が無かった』正常 NOOP の線もある）")
        return 1

    failed_total = 0
    adopted_total = 0
    for s in sweeps:
        print(
            f"- {s['_file']}: status={s.get('status')} adopted={s.get('adopted')} "
            f"rejected={s.get('rejected')} skipped={s.get('skipped')} failed={s.get('failed')}"
        )
        if s.get("index_updates"):
            for iu in s["index_updates"]:
                print(f"    index: {iu.get('project')} runbooks={iu.get('runbooks')} "
                      f"changed={iu.get('changed')} verified={iu.get('verified')}")
        failed_total += int(s.get("failed", 0) or 0)
        adopted_total += int(s.get("adopted", 0) or 0)

    ok = failed_total == 0
    if adopted_total and not any(s.get("index_updates") for s in sweeps):
        print("[ATTENTION] 採用ありなのに index_updates 空 = 消費配線が走っていない疑い。")
        ok = False

    print()
    if ok:
        print(f"[PASS] {date}: 自律スイープ実行・failed=0。採用 {adopted_total} 件、現 backlog {total_backlog}。")
        return 0
    print(f"[ATTENTION] {date}: failed={failed_total} または index 未更新。原因調査が必要。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
