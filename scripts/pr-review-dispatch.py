#!/usr/bin/env python3
"""Fallback PR review dispatcher for a 15-minute cron schedule.

The GitHub webhook gateway is the primary detector.  This poller retains the
existing recovery path and shares its state and flock with the gateway so a
delivery made by either process is not repeated by the other.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Deployment-specific values come from the environment so no site-specific
# repos, accounts, or paths are baked into the public source tree.
SHARED_DIR = Path(os.environ.get("ANIMAWORKS_SHARED_DIR", "~/.animaworks/shared")).expanduser()
STATE_FILE = SHARED_DIR / "pr-review-dispatch-state.json"
STATE_LOCK = STATE_FILE.with_suffix(".lock")
LOG_FILE = SHARED_DIR / "pr-review-dispatch.log"
GH_CONFIG_DIR = os.environ.get("GH_CONFIG_DIR", str(SHARED_DIR / "gh-bot"))

# Comma-separated "owner/repo" list; the poller refuses to run without it.
REPOS = [r.strip() for r in os.environ.get("PR_DISPATCH_REPOS", "").split(",") if r.strip()]
QUIET_SECONDS = float(os.environ.get("PR_DISPATCH_QUIET_SECONDS", "180"))
# Bot account whose own comments are ignored; empty disables the exclusion.
BOT_LOGIN = os.environ.get("PR_DISPATCH_BOT_LOGIN", "")
# Dedicated review-bot login (e.g. animaworks-reviewer); treated like BOT_LOGIN.
REVIEWER_LOGIN = os.environ.get("PR_DISPATCH_REVIEWER_LOGIN", "")
REVIEWER = os.environ.get("PR_DISPATCH_REVIEWER", "sumire")
DISPATCHER = os.environ.get("PR_DISPATCH_DISPATCHER", "rin")
FIXER = os.environ.get("PR_DISPATCH_FIXER", "natsume")
ESCALATION_TARGET = os.environ.get("PR_DISPATCH_ESCALATION", "sakura")
ALERT_EVERY = 5

# Stale unaddressed-review warning thresholds (hours).
# 2026-07-27 taka指示: 15分警告 → 以後15分毎に再警告(30/45分) → 60分でsakuraエスカレーション
STALE_WARN_HOURS = float(os.environ.get("PR_STALE_WARN_HOURS", "0.25"))
STALE_REWARN_HOURS = float(os.environ.get("PR_STALE_REWARN_HOURS", "0.25"))
STALE_ESCALATE_HOURS = float(os.environ.get("PR_STALE_ESCALATE_HOURS", "1"))

# When set (1/true/yes), send() logs instead of delivering DMs.
DRY_RUN = os.environ.get("PR_DISPATCH_DRY_RUN", "").strip().lower() in ("1", "true", "yes")

# Non-bot issue/review comments matching this are treated as fix requests.
FIX_REQUEST_PATTERN = re.compile(
    r"修正|直して|対応して|お願いします|fix|please|change|address|required",
    re.IGNORECASE,
)

sys.path.insert(
    0,
    os.environ.get("ANIMAWORKS_REPO_ROOT", str(Path(__file__).resolve().parents[1])),
)

from core.tasks_dispatch import dispatch_direct_task


def is_our_bot(login: str) -> bool:
    """True when *login* is BOT_LOGIN or REVIEWER_LOGIN (our bot accounts)."""
    if not login:
        return False
    return (bool(BOT_LOGIN) and login == BOT_LOGIN) or (
        bool(REVIEWER_LOGIN) and login == REVIEWER_LOGIN
    )


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"[{iso(now_utc())}] {msg}\n")


def gh(args: list[str]) -> str:
    env = dict(os.environ, GH_CONFIG_DIR=GH_CONFIG_DIR)
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}... failed: {proc.stderr.strip()[:500]}")
    return proc.stdout


def send(to: str, content: str) -> None:
    if DRY_RUN:
        log(f"DRY_RUN send -> {to}: {content[:300]}")
        return
    from core.messenger import Messenger

    Messenger(SHARED_DIR, "pr-review-dispatch").send(
        to=to,
        content=content,
        intent="report",
        skip_logging=True,
        meta={"source": "pr-review-dispatch.py"},
        source="system",
    )


def dispatch_task(**kwargs: Any) -> bool:
    """Dispatch unless this poller is running in dry-run mode."""
    if DRY_RUN:
        log(f"DRY_RUN task -> {kwargs['target']}: {kwargs['task_id']} {kwargs['summary']}")
        return False
    return dispatch_direct_task(**kwargs)


def default_state() -> dict:
    return {
        "prs": {},
        "last_comment_check": iso(now_utc()),
        "seen_comments": {},
        "ci_notified": {},
        "conflict_notified": {},
        "stale_watch": {},
        "consecutive_failures": 0,
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                state.setdefault("prs", {})
                state.setdefault("seen_comments", {})
                state.setdefault("ci_notified", {})
                state.setdefault("conflict_notified", {})
                state.setdefault("stale_watch", {})
                return state
        except (json.JSONDecodeError, OSError):
            log("state file unreadable; starting fresh")
    return default_state()


def parse_gh_time(value: str | None) -> datetime | None:
    """Parse GitHub ISO timestamps into timezone-aware UTC datetimes."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def is_addressed(
    *,
    pr_closed: bool,
    thread_resolved: bool = False,
    item_created_at: datetime | None = None,
    bot_commit_at: datetime | None = None,
    bot_comment_at: datetime | None = None,
    kind: str = "comment",
    review_dismissed: bool = False,
    review_decision: str | None = None,
    ci_still_failing: bool = True,
    head_sha_changed: bool = False,
) -> bool:
    """Return True when the fix request no longer needs tracking.

    kind:
      - review: CHANGES_REQUESTED stays open until PR close, dismiss, or
        reviewDecision leaves CHANGES_REQUESTED. Bot commits/comments do NOT clear it.
      - thread / comment: resolve, subsequent bot commit, or bot reply clears it.
      - ci: cleared when PR closes, CI no longer failing on the item SHA, or
        head SHA moved on (new failing SHA becomes a fresh item).
    """
    if pr_closed:
        return True
    if kind == "review":
        if review_dismissed:
            return True
        decision = (review_decision or "").upper()
        return bool(decision and decision != "CHANGES_REQUESTED")
    if kind == "ci":
        # Old SHA items are retired when head moves; a failing new SHA is a new item_id.
        if head_sha_changed:
            return True
        return not ci_still_failing
    # thread / comment (default)
    if thread_resolved:
        return True
    if item_created_at is None:
        return False
    if bot_commit_at is not None and bot_commit_at > item_created_at:
        return True
    return bot_comment_at is not None and bot_comment_at > item_created_at


def ci_stale_item_id(repo: str, number: int, sha: str) -> str:
    """Stable stale-watch key for a CI failure on a specific PR head SHA."""
    return f"ci:{repo}#{number}:{sha}"


# 2026-07-27 taka指示: CANCELLED(60分timeout等)/TIMED_OUTも「CI NG」として扱う。
# #3854のFeature Tests CANCELLEDがFAILURE限定判定のため警告ゼロで放置された。
FAILING_CI_CONCLUSIONS = frozenset({"FAILURE", "CANCELLED", "TIMED_OUT", "STARTUP_FAILURE"})


def failed_check_names(status_check_rollup: list[dict[str, Any]] | None) -> list[str]:
    """Return names of checks whose conclusion counts as failing (see FAILING_CI_CONCLUSIONS)."""
    return [
        str(check.get("name") or "?")
        for check in (status_check_rollup or [])
        if str(check.get("conclusion") or "").upper() in FAILING_CI_CONCLUSIONS
    ]


def determine_warning_stage(
    *,
    item_created_at: datetime,
    now: datetime,
    last_warned: datetime | None,
    escalated_at: datetime | None,
    warn_hours: float = 0.25,
    rewarn_hours: float = 0.25,
    escalate_hours: float = 1.0,
) -> str:
    """Return warning stage: none | warn | rewarn | escalate.

    When both dispatcher rewarn and escalate are due, returns escalate
    (caller still notifies the dispatcher when its interval has elapsed).
    """
    age = now - item_created_at
    if age < timedelta(hours=warn_hours):
        return "none"

    escalate_due = age >= timedelta(hours=escalate_hours) and (
        escalated_at is None or (now - escalated_at) >= timedelta(hours=escalate_hours)
    )
    if last_warned is None:
        dispatcher_stage = "warn"
    elif (now - last_warned) >= timedelta(hours=rewarn_hours):
        dispatcher_stage = "rewarn"
    else:
        dispatcher_stage = "none"

    if escalate_due:
        return "escalate"
    return dispatcher_stage


def _elapsed_label(created_at: datetime, now: datetime) -> str:
    minutes = max(0, int((now - created_at).total_seconds() // 60))
    return f"{minutes // 60}h{minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


def _format_stale_line(
    *,
    repo: str,
    number: int,
    author: str,
    body: str,
    url: str,
    created_at: datetime,
    now: datetime,
    kind: str = "comment",
    sha: str = "",
    failed_checks: list[str] | None = None,
) -> str:
    elapsed = _elapsed_label(created_at, now)
    if kind == "review":
        return (
            f"- PR #{number} が CHANGES_REQUESTED のまま未解除です"
            f"（@{author}/経過{elapsed}）\n  {url}"
        )
    if kind == "ci":
        checks = ", ".join((failed_checks or [])[:6]) or "?"
        sha8 = (sha or "")[:8] or "?"
        return (
            f"- PR #{number} のCI失敗が未修正のまま放置されています"
            f"（{sha8}・{checks}・経過{elapsed}）\n  {url}"
        )
    snippet = (body or "").replace("\n", " ").strip()[:140]
    return f"- {repo}#{number} (経過{elapsed}) @{author}: {snippet}\n  {url}"


def _stale_message(lines: list[str], *, kind: str = "comment") -> str:
    detail = "\n".join(lines[:20])
    more = f"\n…他{len(lines) - 20}件" if len(lines) > 20 else ""
    if kind == "review":
        return (
            "【警告】PR が CHANGES_REQUESTED のまま未解除です\n\n"
            f"{detail}{more}\n\n"
            "修正を積んだ場合は reviewer に再レビューを依頼するか、"
            "対応方針をPRコメントで明示してください"
        )
    if kind == "ci":
        return (
            "【警告】PR のCI失敗が未修正のまま放置されています\n\n"
            f"{detail}{more}\n\n"
            "修正commitをpushするか、対応不能ならその理由をPRコメントに残してください"
        )
    return (
        "【警告】PR修正依頼が未対応です\n\n"
        f"{detail}{more}\n\n"
        "修正commit・返信・resolveのいずれかで対応するか、"
        "対応しない理由をスレッドへ返信してください"
    )


def _latest_bot_activity(
    *,
    commits: list[dict[str, Any]],
    comments: list[dict[str, Any]],
) -> tuple[datetime | None, datetime | None]:
    """Return (latest bot commit time, latest bot comment time) on a PR."""
    bot_commit_at: datetime | None = None
    bot_comment_at: datetime | None = None
    if BOT_LOGIN or REVIEWER_LOGIN:
        for commit in commits:
            author = (commit.get("author") or {}).get("login") or ""
            committer = (commit.get("committer") or {}).get("login") or ""
            if not is_our_bot(author) and not is_our_bot(committer):
                continue
            committed = parse_gh_time(
                ((commit.get("commit") or {}).get("committer") or {}).get("date")
            ) or parse_gh_time(((commit.get("commit") or {}).get("author") or {}).get("date"))
            if committed is not None and (bot_commit_at is None or committed > bot_commit_at):
                bot_commit_at = committed
    for comment in comments:
        author = (comment.get("user") or {}).get("login") or (comment.get("author") or {}).get(
            "login", ""
        )
        if not is_our_bot(author):
            continue
        created = parse_gh_time(comment.get("created_at") or comment.get("createdAt") or comment.get("submitted_at"))
        if created is not None and (bot_comment_at is None or created > bot_comment_at):
            bot_comment_at = created
    return bot_commit_at, bot_comment_at


def _collect_pr_stale_items(
    repo: str,
    number: int,
    *,
    pr_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Collect unaddressed fix-request / CI-failure candidates for one open PR.

    pr_meta may include headRefOid, statusCheckRollup, reviewDecision, url from
    a single `gh pr list --json` call to avoid extra API round-trips.
    """
    owner, _, name = repo.partition("/")
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    meta = pr_meta or {}
    review_decision = str(meta.get("reviewDecision") or "")
    head_sha = str(meta.get("headRefOid") or "")
    pr_url = str(meta.get("url") or f"https://github.com/{repo}/pull/{number}")

    reviews = json.loads(gh(["api", f"repos/{repo}/pulls/{number}/reviews", "--paginate"]))
    issue_comments = json.loads(gh(["api", f"repos/{repo}/issues/{number}/comments?per_page=100"]))
    review_comments = json.loads(gh(["api", f"repos/{repo}/pulls/{number}/comments?per_page=100"]))
    commits = json.loads(gh(["api", f"repos/{repo}/pulls/{number}/commits", "--paginate"]))

    thread_query = (
        "query($owner:String!,$name:String!,$number:Int!){"
        "repository(owner:$owner,name:$name){"
        "pullRequest(number:$number){"
        "reviewThreads(first:100){nodes{id isResolved "
        "comments(last:1){nodes{author{login} body createdAt url}}}}}}}"
    )
    graphql = json.loads(
        gh(
            [
                "api",
                "graphql",
                "-f",
                f"query={thread_query}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"number={number}",
            ]
        )
    )
    threads = (
        (((graphql.get("data") or {}).get("repository") or {}).get("pullRequest") or {})
        .get("reviewThreads")
        or {}
    ).get("nodes") or []

    all_comment_like: list[dict[str, Any]] = list(issue_comments) + list(review_comments)
    for review in reviews:
        if review.get("body"):
            all_comment_like.append(
                {
                    "user": review.get("user"),
                    "created_at": review.get("submitted_at"),
                    "body": review.get("body"),
                }
            )
    bot_commit_at, bot_comment_at = _latest_bot_activity(commits=commits, comments=all_comment_like)

    for review in reviews:
        state_upper = str(review.get("state", "")).upper()
        if state_upper == "DISMISSED":
            continue
        if state_upper != "CHANGES_REQUESTED":
            continue
        author = (review.get("user") or {}).get("login", "")
        if is_our_bot(author):
            continue
        created = parse_gh_time(review.get("submitted_at"))
        if created is None:
            continue
        item_id = f"review:{review.get('id')}"
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        items.append(
            {
                "item_id": item_id,
                "kind": "review",
                "repo": repo,
                "number": number,
                "author": author,
                "body": review.get("body") or "(CHANGES_REQUESTED)",
                "url": review.get("html_url") or pr_url,
                "created_at": created,
                "thread_resolved": False,
                "bot_commit_at": bot_commit_at,
                "bot_comment_at": bot_comment_at,
                "review_dismissed": False,
                "review_decision": review_decision,
            }
        )

    for thread in threads:
        if thread.get("isResolved"):
            continue
        last_comments = ((thread.get("comments") or {}).get("nodes")) or []
        if not last_comments:
            continue
        last = last_comments[-1]
        author = (last.get("author") or {}).get("login", "")
        if is_our_bot(author):
            continue
        created = parse_gh_time(last.get("createdAt"))
        if created is None:
            continue
        item_id = f"thread:{thread.get('id')}"
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        items.append(
            {
                "item_id": item_id,
                "kind": "thread",
                "repo": repo,
                "number": number,
                "author": author,
                "body": last.get("body") or "",
                "url": last.get("url") or pr_url,
                "created_at": created,
                "thread_resolved": False,
                "bot_commit_at": bot_commit_at,
                "bot_comment_at": bot_comment_at,
            }
        )

    for comment in list(issue_comments) + list(review_comments):
        author = (comment.get("user") or {}).get("login", "")
        if is_our_bot(author):
            continue
        body = comment.get("body") or ""
        if not FIX_REQUEST_PATTERN.search(body):
            continue
        created = parse_gh_time(comment.get("created_at"))
        if created is None:
            continue
        item_id = f"comment:{comment.get('id')}"
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        items.append(
            {
                "item_id": item_id,
                "kind": "comment",
                "repo": repo,
                "number": number,
                "author": author,
                "body": body,
                "url": comment.get("html_url") or pr_url,
                "created_at": created,
                "thread_resolved": False,
                "bot_commit_at": bot_commit_at,
                "bot_comment_at": bot_comment_at,
            }
        )

    # CI failure on current head SHA (persistent rewarn path; check_ci handles first-shot).
    failed = failed_check_names(meta.get("statusCheckRollup"))
    if head_sha and failed:
        item_id = ci_stale_item_id(repo, number, head_sha)
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            items.append(
                {
                    "item_id": item_id,
                    "kind": "ci",
                    "repo": repo,
                    "number": number,
                    "author": "ci",
                    "body": ", ".join(failed[:6]),
                    "url": pr_url,
                    "created_at": None,  # age uses watch first_seen
                    "sha": head_sha,
                    "failed_checks": failed,
                    "ci_still_failing": True,
                    "head_sha_changed": False,
                    "thread_resolved": False,
                    "bot_commit_at": None,
                    "bot_comment_at": None,
                }
            )

    return items


def check_unaddressed(state: dict) -> None:
    """Warn on unaddressed external fix requests / CI failures; escalate long-running ones."""
    watch = state.setdefault("stale_watch", {})
    ci_notified = state.setdefault("ci_notified", {})
    now = now_utc()
    active_ids: set[str] = set()
    # kind -> lines for dispatcher / escalate (separate message templates)
    dispatcher_by_kind: dict[str, list[str]] = {"review": [], "ci": [], "comment": []}
    escalate_by_kind: dict[str, list[str]] = {"review": [], "ci": [], "comment": []}
    open_pr_count = 0

    for repo in REPOS:
        prs = json.loads(
            gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--json",
                    "number,headRefOid,statusCheckRollup,reviewDecision,url",
                    "--limit",
                    "100",
                ]
            )
        )
        open_pr_count += len(prs)
        for pr in prs:
            number = pr["number"]
            for item in _collect_pr_stale_items(repo, number, pr_meta=pr):
                kind = str(item.get("kind") or "comment")
                if is_addressed(
                    pr_closed=False,
                    thread_resolved=bool(item.get("thread_resolved")),
                    item_created_at=item.get("created_at"),
                    bot_commit_at=item.get("bot_commit_at"),
                    bot_comment_at=item.get("bot_comment_at"),
                    kind=kind,
                    review_dismissed=bool(item.get("review_dismissed")),
                    review_decision=item.get("review_decision"),
                    ci_still_failing=bool(item.get("ci_still_failing", True)),
                    head_sha_changed=bool(item.get("head_sha_changed")),
                ):
                    continue
                item_id = item["item_id"]
                active_ids.add(item_id)
                entry = watch.get(item_id)
                if entry is None:
                    # CI: if check_ci already notified this SHA, treat that as first warn
                    # so stale side starts rewarn after REWARN interval (no duplicate immediate alert).
                    already_ci_notified = False
                    if kind == "ci":
                        sha = str(item.get("sha") or "")
                        ci_key = f"{repo}#{number}_{sha[:8]}"
                        already_ci_notified = ci_key in ci_notified
                    entry = {
                        "first_seen": iso(now),
                        "last_warned": iso(now) if already_ci_notified else None,
                        "escalated_at": None,
                        "kind": kind,
                    }
                    watch[item_id] = entry
                last_warned = parse_gh_time(entry.get("last_warned"))
                escalated_at = parse_gh_time(entry.get("escalated_at"))
                # CI age is measured from first_seen (no event timestamp on the check rollup).
                if kind == "ci":
                    item_created_at = parse_gh_time(entry.get("first_seen")) or now
                    warn_hours = 0.0  # first warn immediate (unless already_ci_notified set last_warned)
                else:
                    item_created_at = item["created_at"]
                    warn_hours = STALE_WARN_HOURS
                stage = determine_warning_stage(
                    item_created_at=item_created_at,
                    now=now,
                    last_warned=last_warned,
                    escalated_at=escalated_at,
                    warn_hours=warn_hours,
                    rewarn_hours=STALE_REWARN_HOURS,
                    escalate_hours=STALE_ESCALATE_HOURS,
                )
                if stage == "none":
                    continue
                line = _format_stale_line(
                    repo=item["repo"],
                    number=item["number"],
                    author=item.get("author") or "",
                    body=item.get("body") or "",
                    url=item.get("url") or "",
                    created_at=item_created_at,
                    now=now,
                    kind=kind,
                    sha=str(item.get("sha") or ""),
                    failed_checks=item.get("failed_checks"),
                )
                dispatcher_due = stage in ("warn", "rewarn") or (
                    stage == "escalate"
                    and (
                        last_warned is None
                        or (now - last_warned) >= timedelta(hours=STALE_REWARN_HOURS)
                    )
                )
                # thread/comment share the generic message template
                msg_kind = kind if kind in ("review", "ci") else "comment"
                if dispatcher_due:
                    dispatcher_by_kind[msg_kind].append(line)
                    entry["last_warned"] = iso(now)
                if stage == "escalate":
                    escalate_by_kind[msg_kind].append(line)
                    entry["escalated_at"] = iso(now)

    if open_pr_count == 0 and not watch:
        return

    # Drop resolved / closed-PR items and 14-day leftovers only after a full scan.
    cutoff = iso(now - timedelta(days=14))
    state["stale_watch"] = {
        key: value
        for key, value in watch.items()
        if key in active_ids and (value.get("first_seen") or iso(now)) >= cutoff
    }

    for msg_kind, lines in dispatcher_by_kind.items():
        if lines:
            send(DISPATCHER, _stale_message(lines, kind=msg_kind))
            log(f"stale warn ({msg_kind}) -> {DISPATCHER}: {len(lines)} item(s)")
    for msg_kind, lines in escalate_by_kind.items():
        if lines:
            send(ESCALATION_TARGET, _stale_message(lines, kind=msg_kind))
            log(f"stale escalate ({msg_kind}) -> {ESCALATION_TARGET}: {len(lines)} item(s)")


def save_state(state: dict) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=STATE_FILE.parent,
            prefix=f".{STATE_FILE.name}.",
            delete=False,
        ) as handle:
            json.dump(state, handle, indent=1, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        temp_path.replace(STATE_FILE)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


@contextmanager
def locked_state() -> Iterator[dict]:
    """Lock the shared state across the complete read/modify/write cycle."""
    from core.platform.locks import acquire_file_lock, release_file_lock

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_LOCK.open("a+", encoding="utf-8") as lock_handle:
        acquire_file_lock(lock_handle, exclusive=True)
        try:
            state = load_state()
            yield state
            save_state(state)
        finally:
            release_file_lock(lock_handle)


def check_commits(state: dict) -> None:
    """Detect a stable PR head and dispatch it once to the reviewer."""
    now = now_utc()
    ready: list[str] = []
    open_keys: set[str] = set()

    for repo in REPOS:
        prs = json.loads(
            gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--json",
                    "number,title,headRefOid,isDraft",
                    "--limit",
                    "100",
                ]
            )
        )
        for pr in prs:
            if pr.get("isDraft"):
                continue
            key = f"{repo}#{pr['number']}"
            open_keys.add(key)
            sha = pr["headRefOid"]
            entry = state["prs"].get(key)
            if entry is None or entry.get("sha") != sha:
                state["prs"][key] = {
                    "sha": sha,
                    "sha_seen_at": iso(now),
                    "notified_sha": (entry or {}).get("notified_sha", ""),
                    "title": pr["title"][:120],
                }
                continue
            if entry.get("notified_sha") == sha:
                continue
            seen_at = datetime.strptime(entry["sha_seen_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if now - seen_at >= timedelta(seconds=QUIET_SECONDS):
                ready.append(f"- {key} {sha[:8]}: {entry.get('title', '')}")
                entry["notified_sha"] = sha

    state["prs"] = {key: value for key, value in state["prs"].items() if key in open_keys}
    if ready:
        send(
            REVIEWER,
            "【PR新規コミット検出（push静穏確認済み）】\n\n"
            + "\n".join(ready)
            + "\n\n"
            + f"最終pushから{QUIET_SECONDS // 60}分以上静穏を確認済みです。"
            "上記PRの current HEAD に対する差分レビュー/FRCを直ちに実施してください。"
            "過去HEADへのレビューは新push時点で無効です。"
            "2回目以降のレビューは収束ルール（heartbeat.md記載・2026-07-15 taka指示）に従い、"
            "前回blocking findingsの解消確認と新push差分に限定してください。"
            "full PRの再レビューをやり直さないこと。"
            "同一PRのHOLDが通算3回に達している場合は自動レビューを停止し、rinへエスカレーションしてください。"
            "複数件ある場合はbackgroundタスクとして並列に処理して構いません。",
        )
        log(f"review dispatch -> {REVIEWER}: {len(ready)} PR(s)")


def check_comments(state: dict) -> None:
    """Dispatch new non-bot review and issue comments once."""
    since = state.get("last_comment_check") or iso(now_utc() - timedelta(hours=1))
    now = now_utc()
    seen = state.setdefault("seen_comments", {})
    lines: list[str] = []

    for repo in REPOS:
        for endpoint, kind in (
            (f"repos/{repo}/pulls/comments", "review-comment"),
            (f"repos/{repo}/issues/comments", "issue-comment"),
        ):
            comments = json.loads(gh(["api", f"{endpoint}?since={since}&per_page=100"]))
            for comment in comments:
                author = (comment.get("user") or {}).get("login", "")
                if is_our_bot(author):
                    continue
                dedupe_key = f"{kind}:{comment.get('id')}"
                if dedupe_key in seen:
                    continue
                raw_body = str(comment.get("body") or "")
                if BOT_LOGIN and f"@{BOT_LOGIN}".casefold() in raw_body.casefold():
                    resource_url = str(
                        comment.get("pull_request_url" if kind == "review-comment" else "issue_url") or ""
                    )
                    try:
                        number = int(resource_url.rstrip("/").rsplit("/", 1)[-1])
                    except ValueError:
                        number = 0
                    url = str(comment.get("html_url") or "")
                    instruction = (
                        f"GitHub の {repo}#{number} に次のコメントが投稿された。\n\n"
                        f"{raw_body}\n\nURL: {url}\n\n"
                        "上記コメントの指示に従って対応せよ。コンフリクト解消の場合は "
                        "procedures/pr-conflict-resolution.md の手順（worktreeでorigin/baseをmerge・"
                        "テスト通過確認・通常push・force-push禁止）に従う。"
                    )
                    dispatch_task(
                        target=FIXER,
                        task_id=f"gh-cmd-{comment.get('id')}",
                        summary=f"GitHubコメント対応 {repo}#{number}",
                        instruction=instruction,
                        meta={"repo": repo, "number": number, "url": url, "kind": kind},
                    )
                    seen[dedupe_key] = iso(now)
                    continue
                seen[dedupe_key] = iso(now)
                body = raw_body.replace("\n", " ")[:140]
                lines.append(f"- [{kind}] {author}: {body}\n  {comment.get('html_url', '')}")

    state["last_comment_check"] = iso(now)
    cutoff = iso(now - timedelta(days=14))
    state["seen_comments"] = {key: value for key, value in seen.items() if value >= cutoff}
    if lines:
        detail = "\n".join(lines[:20])
        more = f"\n…他{len(lines) - 20}件" if len(lines) > 20 else ""
        send(
            DISPATCHER,
            "【外部レビューコメント検知】\n\n"
            f"{detail}{more}\n\n"
            "bot以外による新規コメントです。ACTION_REQUIRED判定と"
            f"{FIXER}への修正ディスパッチを procedures/pr-event-detection-patrol.md "
            "に従って実施してください。",
        )
        log(f"comment dispatch -> {DISPATCHER}: {len(lines)} comment(s)")


def check_ci(state: dict) -> None:
    """Dispatch CI failures once per PR and head SHA."""
    for repo in REPOS:
        prs = json.loads(
            gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--json",
                    "number,headRefOid,statusCheckRollup",
                    "--limit",
                    "100",
                ]
            )
        )
        for pr in prs:
            failed = failed_check_names(pr.get("statusCheckRollup"))
            if not failed:
                continue
            key = f"{repo}#{pr['number']}_{pr['headRefOid'][:8]}"
            if key in state["ci_notified"]:
                continue
            workflow_url = next(
                (
                    str(check.get("detailsUrl") or "")
                    for check in (pr.get("statusCheckRollup") or [])
                    if str(check.get("conclusion") or "").upper() in FAILING_CI_CONCLUSIONS
                ),
                "",
            )
            number = pr["number"]
            sha = pr["headRefOid"]
            pr_url = f"https://github.com/{repo}/pull/{number}"
            workflow_name = ", ".join(failed[:6])
            dispatch_task(
                target=FIXER,
                task_id=f"gh-ci-{repo.replace('/', '-')}#{number}-{sha[:8]}",
                summary=f"CI失敗修正 {repo}#{number}",
                instruction=(
                    f"PR #{number} ({pr_url}) の CI ({workflow_name}) が head {sha} で失敗。"
                    f"原因を調査し修正をpushせよ。\nworkflow URL: {workflow_url}"
                ),
                meta={"repo": repo, "number": number, "sha": sha, "workflow_url": workflow_url},
            )
            state["ci_notified"][key] = iso(now_utc())

    cutoff = iso(now_utc() - timedelta(days=30))
    state["ci_notified"] = {key: value for key, value in state["ci_notified"].items() if value >= cutoff}


def check_conflicts(state: dict) -> None:
    """Dispatch merge conflicts once per PR head; renotify after re-conflict."""
    notified = state.setdefault("conflict_notified", {})
    open_keys: set[str] = set()
    dispatched = 0
    for repo in REPOS:
        prs = json.loads(
            gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--json",
                    "number,title,headRefName,baseRefName,headRefOid,mergeable,isDraft,url",
                    "--limit",
                    "100",
                ]
            )
        )
        for pr in prs:
            if pr.get("isDraft"):
                continue
            key = f"{repo}#{pr['number']}"
            open_keys.add(key)
            mergeable = str(pr.get("mergeable", "")).upper()
            if mergeable == "MERGEABLE":
                # 解消済み: 同一headのまま再コンフリクトしても再通知できるよう記録を消す
                notified.pop(key, None)
                continue
            if mergeable != "CONFLICTING":
                # UNKNOWN はGitHub側の算出待ち。次回巡回で確定値を見る。
                continue
            sha = pr["headRefOid"][:8]
            if notified.get(key) == sha:
                continue
            notified[key] = sha
            url = str(pr.get("url") or f"https://github.com/{repo}/pull/{pr['number']}")
            dispatch_task(
                target=FIXER,
                task_id=f"gh-conflict-{repo.replace('/', '-')}#{pr['number']}-{sha}",
                summary=f"コンフリクト解消 {repo}#{pr['number']}",
                instruction=(
                    f"PR #{pr['number']}「{pr.get('title', '')}」"
                    f"（{pr.get('headRefName', '')} -> {pr.get('baseRefName', '')}）\nURL: {url}\n\n"
                    "baseブランチとのコンフリクトを解消せよ。手順は "
                    "procedures/pr-conflict-resolution.md に従う（該当ブランチのworktreeで "
                    "origin/base をmergeして解消・テスト通過確認・通常push・force-push禁止）。"
                    "解消pushの後は既存の静穏検知で差分レビューが自動起動する。"
                ),
                meta={"repo": repo, "number": pr["number"], "sha": pr["headRefOid"], "url": url},
            )
            dispatched += 1

    state["conflict_notified"] = {key: value for key, value in notified.items() if key in open_keys}
    if dispatched:
        log(f"conflict task dispatch -> {FIXER}: {dispatched} PR(s)")


def main() -> int:
    if not REPOS:
        sys.stderr.write("PR_DISPATCH_REPOS is not set (comma-separated owner/repo list); refusing to run.\n")
        return 2
    with locked_state() as state:
        try:
            check_commits(state)
            check_comments(state)
            check_ci(state)
            check_conflicts(state)
            check_unaddressed(state)
        except Exception as exc:
            state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
            count = state["consecutive_failures"]
            log(f"FAILURE #{count}: {exc}")
            if count % ALERT_EVERY == 0:
                try:
                    send(
                        DISPATCHER,
                        f"【pr-review-dispatch異常】gh連続失敗 {count}回。"
                        f"PRレビュー自動起動が止まっています。エラー: {str(exc)[:300]}\n"
                        f"ログ: {LOG_FILE}",
                    )
                except Exception as alert_exc:
                    log(f"alert send failed: {alert_exc}")
            return 1
        state["consecutive_failures"] = 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
