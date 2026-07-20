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

さらに、オーナー (室町/cmnt) が Discord #finance に書いた FIN-047 への方向修正指示を
検知し、ayane に「計画反映タスク」(completion_criteria 付き) を自動投入する。
反映タスクは tasks.md の変更履歴に `反映済み: <指示ID>` を記録・コミットしない限り
done にできないため、指示が会話で流れて消えることを構造的に防ぐ。

Usage:
    python scripts/fin047_progress_check.py [--dry-run]          # 日次フルレポート
    python scripts/fin047_progress_check.py --directives-only    # 毎時: 指示検知のみ

cron (sakura/cron.md, type: command, trigger_heartbeat: false) から起動される。
"""

from __future__ import annotations

import argparse
import hashlib
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

from core.memory.task_verification import iter_channel_posts, iter_checkboxes  # noqa: E402
from core.paths import get_animas_dir, get_data_dir, get_shared_dir  # noqa: E402
from core.time_utils import now_local  # noqa: E402

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

OPENSPEC_CHANGE_DIR = OPENSPEC_TASKS_MD.parent
OPENSPEC_ARCHIVE_DIR = FINANCE_REPO / "openspec" / "changes" / "archive"
OBSIDIAN_PROJECTS_DIR = Path(r"E:\OneDriveBiz\Obsidian") / "_notes" / "Projects"
PROJECT_NOTE = OBSIDIAN_PROJECTS_DIR / "VIXシナリオ別PL_Chg低減最適化.md"
DELIVERABLES_START = "<!-- FIN047-DELIVERABLES:START"
DELIVERABLES_END = "<!-- FIN047-DELIVERABLES:END -->"

SNAPSHOT_PATH = get_data_dir() / "state" / "fin047_progress_snapshot.json"
FINANCE_CHANNEL_JSONL = get_shared_dir() / "channels" / "finance.jsonl"
OWNER_NAMES = {"室町", "cmnt"}
DIRECTIVE_ASSIGNEE = "ayane"

# 日次報告の締切時刻 (2026-07-19 以降 16:00。cron: 15:00 seed / 16:00 report)
REPORT_HOUR = 16
REPORT_MINUTE = 0
REPORT_DEADLINE_STR = f"{REPORT_HOUR:02d}:{REPORT_MINUTE:02d}"

# FIN-047 言及判定 (seed する channel_post criteria の pattern と同一に保つこと)
FIN047_PATTERN = r"(?i)fin-?047"
FIN047_RE = re.compile(FIN047_PATTERN)


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


_MOJIBAKE_RE = re.compile(r"[縺繝繧蜷蝣ｱ]|・ｽ")


def collect_openspec() -> dict:
    if not OPENSPEC_TASKS_MD.is_file():
        return {"error": f"tasks.md not found: {OPENSPEC_TASKS_MD}"}
    checked = 0
    total = 0
    sections: dict[str, list[int]] = {}
    current = "(前文)"
    text = OPENSPEC_TASKS_MD.read_text(encoding="utf-8", errors="replace")
    mojibake = bool(_MOJIBAKE_RE.search(text))
    for line in text.splitlines():
        if line.startswith("#"):
            current = line.lstrip("#").strip()
            continue
        for done, _label in iter_checkboxes(line):
            total += 1
            checked += int(done)
            sec = sections.setdefault(current, [0, 0])
            sec[0] += int(done)
            sec[1] += 1
    result = {"checked": checked, "total": total, "sections": sections}
    if mojibake:
        # cp932 往復破損の検知 (2026-07-19 に実際に発生)。放置すると正典が読めなくなる
        result["mojibake"] = True
    return result


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
    from core.memory.task_queue import TaskQueueManager

    result: dict[str, list[str]] = {}
    for anima in ASSIGNEES:
        entries = []
        anima_dir = get_animas_dir() / anima
        if anima_dir.is_dir():
            for task in TaskQueueManager(anima_dir).load_active_tasks().values():
                text = f"{task.summary} {task.original_instruction} {json.dumps(task.meta or {}, ensure_ascii=False)}"
                if FIN047_RE.search(text):
                    entries.append(f"[{task.status}] {task.summary[:60]}")
        result[anima] = entries
    return result


# ── Project note deliverables sync ─────────────────────────────────────


def _file_uri(path: Path) -> str:
    from urllib.request import pathname2url

    return "file:" + pathname2url(str(path))


def sync_project_note() -> str:
    """fin047 コミットの成果物リンクを Obsidian プロジェクトノートへ自動同期する.

    「◯◯にまとめました」報告だけでは成果物へ辿れない問題への決定論対策。
    ノート内の管理ブロック (DELIVERABLES markers) を、ブランチ上の fin047
    コミット一覧 + 変更ファイルへの file リンク (worktree 実体) で毎回再生成する。
    Returns a short status string for the report.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(FINANCE_REPO), "log", "--format=%h|%ad|%s", "--date=format:%Y-%m-%d %H:%M", BRANCH],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"note sync failed: git log: {e}"
    if proc.returncode != 0:
        return "note sync skipped: branch not found"

    lines: list[str] = []
    for raw in proc.stdout.splitlines():
        parts = raw.split("|", 2)
        if len(parts) != 3 or not FIN047_RE.search(parts[2]):
            continue
        commit, cdate, subject = parts
        try:
            files_proc = subprocess.run(
                ["git", "-C", str(FINANCE_REPO), "show", "--name-only", "--format=", commit],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            files = [f for f in files_proc.stdout.splitlines() if f.strip()]
        except (OSError, subprocess.TimeoutExpired):
            files = []
        links = []
        for f in files:
            target = STAGING_WORKTREE / f
            label = f.split("/")[-1]
            if target.exists():
                links.append(f"[{label}]({_file_uri(target)})")
            else:
                links.append(f"`{f}`")
        lines.append(f"- {cdate} `{commit}` {subject}" + (" — " + " / ".join(links) if links else ""))

    if not lines:
        lines = ["- (fin047 コミットなし)"]

    try:
        note_text = PROJECT_NOTE.read_text(encoding="utf-8")
    except OSError as e:
        return f"note sync failed: {e}"
    start = note_text.find(DELIVERABLES_START)
    end = note_text.find(DELIVERABLES_END)
    if start == -1 or end == -1 or end < start:
        return "note sync skipped: markers not found"
    marker_line_end = note_text.index("\n", start)
    new_text = note_text[: marker_line_end + 1] + "\n".join(lines) + "\n" + note_text[end:]
    if new_text != note_text:
        PROJECT_NOTE.write_text(new_text, encoding="utf-8")
        return f"note synced: {len(lines)} 成果物エントリ"
    return f"note up-to-date: {len(lines)} 成果物エントリ"


# ── Completion (loop termination) ──────────────────────────────────────


def completion_status() -> dict:
    """終了条件の充足状況を返す。両方 True になるまで日次ループは続く.

    1. OpenSpec Archive: change dir が active から消え、archive/ 配下に移動済み
    2. Projects DB 完了: Obsidian _notes/Projects の FIN-047 ノート frontmatter が ステータス: 完了
    """
    openspec_archived = (not OPENSPEC_CHANGE_DIR.exists()) and any(
        OPENSPEC_ARCHIVE_DIR.glob("*fin-047-vix-scenario-pl-chg-optimization*")
    )

    projects_done = False
    try:
        for note in OBSIDIAN_PROJECTS_DIR.glob("*.md"):
            head = note.read_text(encoding="utf-8", errors="replace")[:2000]
            if re.search(r"^タスクコード:\s*FIN-047\s*$", head, flags=re.MULTILINE):
                projects_done = bool(re.search(r"^ステータス:\s*完了\s*$", head, flags=re.MULTILINE))
                break
    except OSError:
        pass

    return {
        "openspec_archived": openspec_archived,
        "projects_done": projects_done,
        "complete": openspec_archived and projects_done,
    }


# ── Owner directives ───────────────────────────────────────────────────


def _directive_id(ts: str, text: str) -> str:
    return hashlib.sha1(f"{ts}|{text}".encode()).hexdigest()[:8]


def collect_owner_directives(seen_ids: set[str]) -> list[dict]:
    """内部 #finance チャンネルから FIN-047 に言及するオーナー発言を検知する.

    オーナーの Discord 投稿は inbound ミラーで finance.jsonl に記録されるため、
    ここを読むだけで Discord 側の指示を拾える (read-only)。
    """
    directives = []
    for msg in iter_channel_posts(FINANCE_CHANNEL_JSONL):
        if msg["sender"] not in OWNER_NAMES or not FIN047_RE.search(msg["text"]):
            continue
        did = _directive_id(msg["ts"], msg["text"])
        if did in seen_ids:
            continue
        directives.append({"id": did, "ts": msg["ts"], "text": msg["text"]})
    return directives


def reflection_marker(directive_id: str) -> str:
    return f"反映済み: {directive_id}"


def seed_reflection_task(directive: dict) -> str | None:
    """オーナー指示ごとに ayane へ計画反映タスクを冪等投入する."""
    from core.memory.task_queue import TaskQueueManager

    anima_dir = get_animas_dir() / DIRECTIVE_ASSIGNEE
    if not anima_dir.is_dir():
        return None
    marker = reflection_marker(directive["id"])
    summary = f"[FIN-047] オーナー指示を計画へ反映する ({directive['id']})"
    excerpt = directive["text"][:800]
    instruction = f"""オーナー (室町) が Discord #finance で FIN-047 について以下の指示を出した ({directive['ts']}):

---
{excerpt}
---

この指示を FIN-047 の正式計画へ反映してください。完了条件 (機械検証されます):

1. OpenSpec {OPENSPEC_TASKS_MD} を指示に沿って更新する
   (タスクの追加・修正・削除、担当変更、優先順位変更など)。
2. tasks.md 末尾の「## 変更履歴」に次の1行を追記する (これが機械検証マーカー):
   `- {directive['ts'][:10]} {marker} — <反映内容の要旨>`
3. 変更を Finance リポジトリにコミットする (メッセージに fin047 を含める)。
4. 関係アニマの task_queue のマイルストーンタスクに影響がある場合は調整し、
   反映内容を #finance の FIN-047 スレッドへ返信する (オーナーが確認できるように)。

指示の解釈に迷う場合は勝手に進めず、#finance で確認質問をした上で
このタスクを blocked にすること。"""
    entry = TaskQueueManager(anima_dir).add_task_if_absent(
        lambda t, s=summary: t.summary == s,
        source="human",
        original_instruction=instruction,
        assignee=DIRECTIVE_ASSIGNEE,
        summary=summary,
        deadline="1d",
        meta={
            "project": "FIN-047",
            "directive_id": directive["id"],
            "completion_criteria": [
                {"type": "file_contains", "path": str(OPENSPEC_TASKS_MD), "pattern": re.escape(marker)},
            ],
        },
    )
    return entry.task_id if entry is not None else None


def unreflected_directives(all_seen: list[dict]) -> list[dict]:
    """記録済み指示のうち tasks.md にまだ反映マーカーが無いものを返す."""
    try:
        text = Path(OPENSPEC_TASKS_MD).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return [d for d in all_seen if reflection_marker(d["id"]) not in text]


# ── Report ─────────────────────────────────────────────────────────────


def load_snapshot() -> dict:
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_snapshot(snapshot: dict) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")


def process_directives(snapshot: dict, *, dry_run: bool) -> tuple[list[dict], list[dict]]:
    """新規オーナー指示の検知・反映タスク投入と、未反映一覧の算出."""
    bootstrap = "directives_seen" not in snapshot
    seen: list[dict] = snapshot.get("directives_seen") or []
    seen_ids = {d["id"] for d in seen}
    fresh = collect_owner_directives(seen_ids)
    if bootstrap:
        # 初回: 既存のオーナー発言 (会議・計画に反映済みの過去分) は既読扱いにして
        # 反映タスクを積まない。以後の新規発言だけが検知対象になる。
        for d in fresh:
            d["bootstrap"] = True
        snapshot["directives_seen"] = fresh[-100:]
        return [], []
    for d in fresh:
        if not dry_run:
            task_id = seed_reflection_task(d)
            d["reflection_task_id"] = task_id
        seen.append(d)
    snapshot["directives_seen"] = seen[-100:]
    return fresh, unreflected_directives([d for d in seen if not d.get("bootstrap")])


# ── Daily per-assignee reports ─────────────────────────────────────────


def _daily_report_summary(anima: str, date_str: str) -> str:
    return f"[FIN-047] 日次報告 {date_str} を #finance スレッドへ投稿する ({anima})"


def seed_daily_report_tasks(now: datetime, *, dry_run: bool) -> list[str]:
    """各担当アニマに「本日の FIN-047 日次報告」タスクを冪等投入する.

    完了条件は channel_post 機械検証 (投入時刻以降に #finance へ FIN-047 言及の
    投稿があること)。前日以前の未消化日次報告タスクは自動キャンセルして堆積を防ぐ。
    """
    from core.memory.task_queue import TaskQueueManager

    date_str = now.strftime("%Y-%m-%d")
    deadline = now.replace(hour=REPORT_HOUR, minute=REPORT_MINUTE, second=0, microsecond=0)
    since_ts = now.isoformat()
    seeded: list[str] = []
    for anima in ASSIGNEES:
        anima_dir = get_animas_dir() / anima
        if not anima_dir.is_dir():
            continue
        tqm = TaskQueueManager(anima_dir)
        summary = _daily_report_summary(anima, date_str)

        # 前日以前の日次報告タスクが残っていれば失効キャンセル
        if not dry_run:
            for task in tqm.load_active_tasks().values():
                if (
                    task.summary.startswith("[FIN-047] 日次報告 ")
                    and task.summary != summary
                    and (task.meta or {}).get("fin047_daily_report")
                ):
                    tqm.update_status(task.task_id, "cancelled", note="日次報告期限超過のため失効 (未報告として記録済み)")

        instruction = f"""FIN-047 の本日分 ({date_str}) の状況を、{REPORT_DEADLINE_STR} までに #finance チャンネルへ報告してください
(投稿は自動で FIN-047 専用 Discord スレッドにルーティングされます)。

報告ルール:
- **進捗や問題が発生したら、{REPORT_DEADLINE_STR} を待たずその都度 #finance に報告してよい** (推奨)。
- {REPORT_DEADLINE_STR} の日次報告は**進捗ゼロでも必須**。その場合は「進捗なし」とその理由 (何にブロックされているか) を明記する。

報告書式 (オーナー指示 2026-07-19、以下3点は必須):
1. **担当スコープ**: 正典 tasks.md のどの番号を担当しているか (例: Phase1 の 1.2-1.3)
2. **進捗状態**: 未着手/実装中/検証中/完了 + 今日進んだ内容と残作業
3. **成果物の所在**: コミットハッシュ、またはファイルの絶対パス。
   git 管理外の成果物 (分析メモ・検証結果等) はプロジェクトノート
   E:\\OneDriveBiz\\Obsidian\\_notes\\Projects\\VIXシナリオ別PL_Chg低減最適化.md の
   「成果物 (手動追記)」セクションに `- 日付 担当: [説明](file:///絶対パス)` 形式で追記する。
「◯◯のファイルにまとめました」だけの報告は不可 — オーナーがリンクで成果物に辿れること。
(ブランチへの fin047 コミットは自動でノートにリンクされるので追記不要)

このタスクは、{since_ts} 以降に #finance へ FIN-047 に言及する投稿を行うと done にできます (機械検証)。"""

        if dry_run:
            seeded.append(f"{anima} (dry-run)")
            continue
        entry = tqm.add_task_if_absent(
            lambda t, s=summary: t.summary == s,
            source="human",
            original_instruction=instruction,
            assignee=anima,
            summary=summary,
            deadline=deadline.isoformat(),
            meta={
                "project": "FIN-047",
                "fin047_daily_report": date_str,
                "completion_criteria": [
                    {
                        "type": "channel_post",
                        "channel": "finance",
                        "sender": anima,
                        "pattern": FIN047_PATTERN,
                        "since_ts": since_ts,
                    }
                ],
            },
        )
        if entry is not None:
            seeded.append(f"{anima}: {entry.task_id}")
            # task_queue だけだと heartbeat 任せで気づかれない (2026-07-18 に全員スルーの実績)。
            # inbox にも通知を落とし、intent filter 経由の即時処理を促す。
            try:
                from core.messenger import Messenger

                Messenger(get_shared_dir(), "cmnt").send(
                    to=anima,
                    content=(
                        f"[FIN-047] 本日の日次報告タスク ({entry.task_id}) を投入しました。"
                        f"{REPORT_DEADLINE_STR} までに #finance へ日次報告を投稿してください"
                        f" (進捗ゼロでも理由付きで必須。投稿すればタスクは done にできます)。"
                    ),
                    msg_type="message",
                    intent="report",
                    source="human",
                )
            except Exception as e:
                print(f"WARN: inbox notify failed for {anima}: {e}", file=sys.stderr)
    return seeded


def _daily_report_cutoff(now: datetime) -> datetime:
    """各自報告のカウント開始時刻 (締切の1.5h前)."""
    minutes = REPORT_HOUR * 60 + REPORT_MINUTE - 90
    return now.replace(hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0)


def collect_daily_report_status(now: datetime) -> dict[str, bool]:
    """締切 1.5h 前以降に #finance へ FIN-047 言及投稿をしたかを担当別に返す."""
    cutoff = _daily_report_cutoff(now).isoformat()
    status = {anima: False for anima in ASSIGNEES}
    for msg in iter_channel_posts(FINANCE_CHANNEL_JSONL):
        if msg["sender"] in status and msg["ts"] >= cutoff and FIN047_RE.search(msg["text"]):
            status[msg["sender"]] = True
    return status


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
        if spec.get("mojibake"):
            lines.append("- ⚠️ **tasks.md にエンコーディング破損 (文字化け) を検知** — cp932 編集の疑い。即時修復が必要")
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

    reports = collect_daily_report_status(now)
    parts = [f"{a} {'✅' if ok else '❌未報告'}" for a, ok in reports.items()]
    lines.append(f"- 本日の各自報告 ({_daily_report_cutoff(now).strftime('%H:%M')}以降): " + " / ".join(parts))

    comp = completion_status()
    lines.append(
        "- 終了条件: OpenSpec Archive "
        f"{'✅' if comp['openspec_archived'] else '❌'} / Projects DB 完了 "
        f"{'✅' if comp['projects_done'] else '❌'}"
        " — 両方 ✅ になるまで本監視は毎日続く"
    )

    snapshot = {
        "ts": now.isoformat(),
        "ahead": ahead_now if ahead_now >= 0 else prev.get("ahead"),
        "checked": checked_now if checked_now >= 0 else prev.get("checked"),
        "stall_days": stall_days,
    }
    if "directives_seen" in prev:
        snapshot["directives_seen"] = prev["directives_seen"]
    return "\n".join(lines), snapshot


def directive_lines(fresh: list[dict], pending: list[dict]) -> list[str]:
    lines = []
    for d in fresh:
        lines.append(
            f"- 📥 オーナー指示を検知 ({d['ts'][:16]}): 「{d['text'][:80]}…」"
            f" → {DIRECTIVE_ASSIGNEE} に反映タスク投入 (id: {d['id']})"
        )
    if pending:
        ids = ", ".join(d["id"] for d in pending)
        lines.append(f"- ⚠️ **計画未反映のオーナー指示 {len(pending)} 件** (id: {ids}) — tasks.md 変更履歴に反映マーカーなし")
    return lines


def post_to_discord(text: str) -> str:
    from core.discord_webhooks import get_webhook_manager

    # 専用スレッドが登録されていればそこへ、なければ #finance トップへ
    channel_id, thread_id = DISCORD_FINANCE_CHANNEL_ID, None
    try:
        from core.project_threads import resolve_thread_for_code

        resolved = resolve_thread_for_code("FIN-047")
        if resolved:
            channel_id, thread_id = resolved
    except Exception:
        pass

    wm = get_webhook_manager()
    return wm.send_as_anima(channel_id, REPORTER_NAME, text, thread_id=thread_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN-047 deterministic progress check")
    parser.add_argument("--dry-run", action="store_true", help="collect and print only; no Discord post")
    parser.add_argument(
        "--directives-only",
        action="store_true",
        help="毎時実行用: オーナー指示の検知・反映タスク投入のみ (新規指示が無ければ NOOP)",
    )
    parser.add_argument(
        "--seed-daily-reports",
        action="store_true",
        help="17:30実行用: 各担当に本日分の日次報告タスクを投入する (Discord 投稿なし)",
    )
    args = parser.parse_args()

    # now_local(): チャンネルログの ts (now_iso 由来) と同一タイムゾーンで揃え、
    # since_ts / cutoff の辞書式比較が TZ ずれで壊れないようにする
    now = now_local()

    # 終了条件 (OpenSpec Archive + Projects DB 完了) 充足後は全モード NOOP。
    # 完了検知の初回だけ最終報告を投稿してループを閉じる。
    comp = completion_status()
    if comp["complete"]:
        snapshot = load_snapshot()
        if snapshot.get("completion_announced"):
            print("NOOP_PROJECT_COMPLETE: FIN-047 is complete; monitoring closed")
            return 0
        final = (
            f"**FIN-047 完了を確認** {now.strftime('%Y-%m-%d %H:%M')}\n"
            "- OpenSpec: Archive 済み ✅\n"
            "- Projects DB: ステータス 完了 ✅\n"
            "日次進捗監視・日次報告義務・指示検知を終了します。お疲れさまでした。"
        )
        print(final)
        if not args.dry_run:
            msg_id = post_to_discord(final)
            print(f"\n[posted to Discord #finance: message_id={msg_id}]")
            snapshot["completion_announced"] = now.isoformat()
            save_snapshot(snapshot)
        return 0

    if args.seed_daily_reports:
        seeded = seed_daily_report_tasks(now, dry_run=args.dry_run)
        if seeded:
            print("seeded daily report tasks: " + ", ".join(seeded))
        else:
            print("NOOP_ALREADY_SEEDED: daily report tasks already exist for today")
        return 0

    if args.directives_only:
        snapshot = load_snapshot()
        fresh, pending = process_directives(snapshot, dry_run=args.dry_run)
        if not fresh:
            print("NOOP_NO_NEW_DIRECTIVES: no new owner directives in #finance")
            return 0
        ack = "\n".join(
            [f"**FIN-047 指示受理** {now.strftime('%m/%d %H:%M')}"] + directive_lines(fresh, pending)
        )
        print(ack)
        if not args.dry_run:
            msg_id = post_to_discord(ack)
            print(f"\n[posted to Discord #finance: message_id={msg_id}]")
            save_snapshot(snapshot)
        return 0

    note_status = sync_project_note() if not args.dry_run else "(dry-run: note sync skipped)"
    report, snapshot = build_report(now)
    report += f"\n- 成果物リンク: プロジェクトノート「進捗と成果物」に自動同期済み ({note_status})"
    fresh, pending = process_directives(snapshot, dry_run=args.dry_run)
    dlines = directive_lines(fresh, pending)
    if dlines:
        report = report + "\n" + "\n".join(dlines)
    print(report)

    if not args.dry_run:
        msg_id = post_to_discord(report)
        print(f"\n[posted to Discord #finance: message_id={msg_id}]")
        save_snapshot(snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
