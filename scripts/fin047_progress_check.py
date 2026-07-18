"""fin047_progress_check.py — FIN-047 の進捗を決定論的に照合して Discord へ日次報告する.

Why this exists
---------------
FIN-047 (VIXシナリオ別PL_Chg低減最適化) は 2026-07-18 に「会議 → 方針合意 → 調整
マイクロタスク全消化 → 全員 idle」という形で空転した。アニマの自己申告や
heartbeat の自発性に依存した進捗報告は減衰する (安城1K の教訓と同じ) ため、
このスクリプトが毎日:

1. OpenSpec change (tasks.md) のチェックボックス進捗
2. feature/fin047-8520-staging ブランチのコミット実績
3. 8519 / 8520 サーバーの死活
4. 担当アニマの task_queue 上のアクティブな FIN-047 タスク

を機械的に観測し、前回スナップショットと比較した「進捗あり / 停滞N日目」の
判定つきレポートを Discord #finance に投稿する。LLM は経由しない。

Usage:
    python scripts/fin047_progress_check.py [--dry-run]

cron (sakura/cron.md, type: command, trigger_heartbeat: false) から日次起動される。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ── FIN-047 configuration ──────────────────────────────────────────────

FINANCE_REPO = Path(r"E:\OneDriveBiz\Tools\Finance")
STAGING_WORKTREE = FINANCE_REPO / ".claude" / ".claude" / "worktrees" / "wt-8520-fin047-staging"
BRANCH = "feature/fin047-8520-staging"
OPENSPEC_TASKS_MD = FINANCE_REPO / "openspec" / "changes" / "fin-047-vix-scenario-pl-chg-optimization" / "tasks.md"
OPTIMIZER_8519_URL = "http://localhost:8519/"
STAGING_8520_URL = "http://localhost:8520/"
DISCORD_FINANCE_CHANNEL_ID = "1489903546517164052"
REPORTER_NAME = "FIN-047 Progress"
ASSIGNEES = ("ayane", "sakura", "airi", "momoka", "rika")

DATA_DIR = Path.home() / ".animaworks"
SNAPSHOT_PATH = DATA_DIR / "state" / "fin047_progress_snapshot.json"

_CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.*)$")


# ── Collectors (each fail-soft: return a dict with an "error" key) ─────


def collect_git() -> dict:
    try:
        proc = subprocess.run(
            ["git", "-C", str(FINANCE_REPO), "log", "--format=%h|%ad|%s", "--date=format:%m/%d %H:%M", BRANCH],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": f"git log failed: {e}"}
    if proc.returncode != 0:
        return {"error": f"branch {BRANCH} not found: {(proc.stderr or '').strip()[:120]}"}
    commits = [line for line in proc.stdout.splitlines() if line.strip()]

    # ブランチ専用コミット数 (base との差分)。merge-base が取れない場合は総数のみ。
    ahead = None
    try:
        base = subprocess.run(
            ["git", "-C", str(FINANCE_REPO), "rev-list", "--count", f"master..{BRANCH}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if base.returncode != 0:
            base = subprocess.run(
                ["git", "-C", str(FINANCE_REPO), "rev-list", "--count", f"main..{BRANCH}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        if base.returncode == 0:
            ahead = int(base.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass

    dirty = None
    if STAGING_WORKTREE.exists():
        try:
            st = subprocess.run(
                ["git", "-C", str(STAGING_WORKTREE), "status", "--short"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if st.returncode == 0:
                dirty = [line for line in st.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.TimeoutExpired):
            pass

    return {
        "branch_exists": True,
        "ahead": ahead,
        "latest": commits[0] if commits else None,
        "worktree_exists": STAGING_WORKTREE.exists(),
        "dirty_files": dirty,
    }


def collect_openspec() -> dict:
    if not OPENSPEC_TASKS_MD.is_file():
        return {"error": f"tasks.md not found: {OPENSPEC_TASKS_MD}"}
    checked = 0
    total = 0
    sections: dict[str, list[int]] = {}
    current = "(前文)"
    for line in OPENSPEC_TASKS_MD.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            current = line.lstrip("#").strip()
            continue
        m = _CHECKBOX_RE.match(line)
        if not m:
            continue
        total += 1
        done = m.group(1) != " "
        checked += int(done)
        sec = sections.setdefault(current, [0, 0])
        sec[0] += int(done)
        sec[1] += 1
    return {"checked": checked, "total": total, "sections": sections}


def _http_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            return 200 <= getattr(resp, "status", 200) < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


def collect_servers() -> dict:
    return {"8519": _http_up(OPTIMIZER_8519_URL), "8520": _http_up(STAGING_8520_URL)}


def collect_tasks() -> dict:
    """各担当アニマの task_queue から FIN-047 関連のアクティブタスクを読む (read-only)."""
    active_statuses = {"pending", "in_progress", "blocked", "delegated"}
    result: dict[str, list[str]] = {}
    for anima in ASSIGNEES:
        queue = DATA_DIR / "animas" / anima / "state" / "task_queue.jsonl"
        tasks: dict[str, dict] = {}
        if queue.is_file():
            for line in queue.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tid = ev.get("task_id")
                if not tid:
                    continue
                tasks.setdefault(tid, {}).update({k: v for k, v in ev.items() if v is not None})
        entries = []
        for t in tasks.values():
            text = f"{t.get('summary', '')} {t.get('original_instruction', '')} {json.dumps(t.get('meta') or {}, ensure_ascii=False)}"
            if "FIN-047" not in text and "fin047" not in text.lower():
                continue
            if t.get("status") in active_statuses:
                entries.append(f"[{t.get('status')}] {t.get('summary', '')[:60]}")
        result[anima] = entries
    return result


# ── Report ─────────────────────────────────────────────────────────────


def load_snapshot() -> dict:
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_snapshot(snapshot: dict) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")


def build_report(now: datetime) -> tuple[str, dict]:
    git = collect_git()
    spec = collect_openspec()
    servers = collect_servers()
    tasks = collect_tasks()

    prev = load_snapshot()
    ahead_now = git.get("ahead") if isinstance(git.get("ahead"), int) else -1
    checked_now = spec.get("checked", -1)
    progressed = (
        (isinstance(prev.get("ahead"), int) and ahead_now > prev["ahead"])
        or (isinstance(prev.get("checked"), int) and checked_now > prev["checked"])
    )
    stall_days = 0 if progressed or not prev else int(prev.get("stall_days", 0)) + 1

    lines = [f"**FIN-047 進捗照合** {now.strftime('%Y-%m-%d %H:%M')} (決定論チェック / LLM不使用)"]

    if progressed:
        lines.append("判定: ✅ **前回から進捗あり**")
    elif not prev:
        lines.append("判定: ℹ️ 初回計測 (基準スナップショット作成)")
    else:
        lines.append(f"判定: ⚠️ **停滞 {stall_days} 回連続** — 実装コミットもチェックリスト進捗もなし")

    if "error" in spec:
        lines.append(f"- OpenSpec: ❌ {spec['error']}")
    else:
        lines.append(f"- OpenSpec tasks.md: {spec['checked']}/{spec['total']} 完了")
        for sec, (c, t) in spec.get("sections", {}).items():
            lines.append(f"    - {sec}: {c}/{t}")

    if "error" in git:
        lines.append(f"- Git: ❌ {git['error']}")
    else:
        ahead_disp = git["ahead"] if git["ahead"] is not None else "?"
        lines.append(f"- ブランチ `{BRANCH}`: 実装コミット {ahead_disp} 件")
        if git.get("latest"):
            lines.append(f"    - 最新: `{git['latest']}`")
        if git.get("dirty_files") is not None:
            lines.append(f"    - worktree 未コミット変更: {len(git['dirty_files'])} 件")

    lines.append(
        f"- サーバー: 8519 {'🟢' if servers['8519'] else '🔴 停止'} / 8520(staging) {'🟢' if servers['8520'] else '🔴 停止'}"
    )

    any_active = False
    for anima, entries in tasks.items():
        if entries:
            any_active = True
            lines.append(f"- {anima}: " + " / ".join(entries[:3]))
    if not any_active:
        lines.append("- 担当アニマの task_queue: ⚠️ FIN-047 のアクティブタスクなし (全員 idle)")

    snapshot = {
        "ts": now.isoformat(),
        "ahead": ahead_now if ahead_now >= 0 else prev.get("ahead"),
        "checked": checked_now if checked_now >= 0 else prev.get("checked"),
        "stall_days": stall_days,
    }
    return "\n".join(lines), snapshot


def post_to_discord(text: str) -> str:
    from core.discord_webhooks import get_webhook_manager

    wm = get_webhook_manager()
    return wm.send_as_anima(DISCORD_FINANCE_CHANNEL_ID, REPORTER_NAME, text)


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN-047 deterministic progress check")
    parser.add_argument("--dry-run", action="store_true", help="collect and print only; no Discord post")
    args = parser.parse_args()

    now = datetime.now().astimezone()
    report, snapshot = build_report(now)
    print(report)

    if not args.dry_run:
        msg_id = post_to_discord(report)
        print(f"\n[posted to Discord #finance: message_id={msg_id}]")
        save_snapshot(snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
