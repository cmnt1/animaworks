from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unified housekeeping engine for periodic disk cleanup.

Runs as a single daily job from ProcessSupervisor's scheduler, cleaning up
all data types that lack their own rotation mechanisms.
"""

import asyncio
import errno
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from core.config.models import HousekeepingConfig, InboxConfig
from core.i18n import t
from core.platform.atomic_io import atomic_write_text
from core.platform.locks import acquire_file_lock, release_file_lock
from core.time_utils import now_local, today_local

logger = logging.getLogger("animaworks.housekeeping")
_PRESERVED_TMP_SUBDIRS = frozenset({"attachments", "skill_hub"})
_ANIMA_LOG_DATE_RE = re.compile(r"(20\d{6})")
_CODEX_LOG_DB_NAME = "logs_2.sqlite"
_PROTECTED_PREFIXES = ("current_session_", "streaming_journal")
_ARCHIVE_VERSION_RE = re.compile(r"^(?P<stem>.+)_v(?P<version>\d+)_(?P<ts>\d{8}_\d{6})(?P<suffix>\.[^.]+)$")


@dataclass(frozen=True, slots=True)
class _HousekeepingRule:
    """One declarative cleanup target and the policy that processes it."""

    result_key: str
    root: Literal["data", "animas"]
    path: str
    pattern: str
    method: str
    settings: tuple[str, ...] = ()
    config_section: Literal["housekeeping", "inbox"] = "housekeeping"
    error_message: str = "cleanup failed"
    count_target_file: bool = False
    age_mode: Literal["mtime", "filename", "archive"] | None = None
    filename_prefix: str = ""
    retention_cap_days: int | None = None
    files_only: bool = False
    error_label: str = "file"
    success_log: str = ""


def _rule(
    result_key: str,
    pattern: str,
    method: str,
    *settings: str,
    root: Literal["data", "animas"] = "animas",
    path: str = ".",
    **options: Any,
) -> _HousekeepingRule:
    options.setdefault("error_message", f"{result_key} cleanup failed")
    return _HousekeepingRule(result_key, root, path, pattern, method, tuple(settings), **options)


# fmt: off
# Ordered for stable result keys; glob is relative to root/path.
_HOUSEKEEPING_RULES = (
    _rule("prompt_logs", "*/prompt_logs/*.jsonl", "prompt_logs", "prompt_log_retention_days"),
    _rule("daemon_log", "server-daemon.log[.N]", "daemon_log", "daemon_log_max_size_mb", "daemon_log_keep_generations", root="data", path="logs/server-daemon.log"),
    _rule("anima_logs", "<anima>/*", "anima_logs", "anima_log_retention_days", "anima_log_total_max_size_mb", root="data", path="logs/animas"),
    _rule("frontend_logs", "dated backups", "frontend_logs", "frontend_log_backup_count", root="data", path="logs/frontend"),
    _rule("dm_archives", "*.archive.jsonl", "delete_old_files", "dm_log_archive_retention_days", root="data", path="shared/dm_logs", error_label="dm archive", success_log="DM archive cleanup: deleted %d files"),
    _rule("cron_logs", "*/state/cron_logs/*.jsonl", "delete_old_files", "cron_log_retention_days", age_mode="filename", retention_cap_days=14, error_label="cron log", success_log="Cron log cleanup: deleted %d files"),
    _rule("shortterm", "*/shortterm/{chat,heartbeat,cron,inbox,task}/**/*", "shortterm", "shortterm_retention_days", "shortterm_archive_retention_days", "shortterm_thread_gc_days"),
    _rule("facts_locks", "*/facts/*.lock", "facts_locks", "facts_lock_stale_hours"),
    _rule("curator_reports", "*/state/skill_curator/report-*.json", "delete_old_files", "curator_report_retention_days", age_mode="filename", filename_prefix="report-", error_label="curator report", success_log="Curator report cleanup: deleted %d files"),
    _rule("task_results", "*/state/task_results/*.md", "delete_old_files", "task_results_retention_days", error_label="task result", success_log="Task results cleanup: deleted %d files"),
    _rule("corrupt_vectordb_archives", "*/archive/{vectordb-corrupt,corrupt-vectordb}-*", "corrupt_vectordb_archives", "corrupt_vectordb_keep_generations"),
    _rule("runtime_tmp", "*", "runtime_tmp", "tmp_retention_days", root="data", path="tmp"),
    _rule("backup_dirs", "*/*_backup_*", "backup_dirs", "backup_retention_days"),
    _rule("codex_execution_logs", "*/.codex_home/logs_2.sqlite[-wal|-shm]", "codex_execution_logs", "codex_log_max_size_mb"),
    _rule("codex_tmp", "*/.codex_home/{.tmp,tmp}/*", "codex_tmp", "codex_tmp_retention_hours"),
    _rule("anima_runtime_artifacts", "*/tmp_gitdirs/* and */logs/**/*", "anima_runtime_artifacts", "anima_tmp_gitdirs_retention_days", "anima_local_log_retention_days"),
    _rule("taskboard_stale", "animas/*/state/{background_tasks,current_state.md}", "taskboard_stale", "pending_processing_stale_hours", "background_running_stale_hours", "current_state_stale_hours", root="data"),
    _rule("suppressed_messages", "**/suppressed_messages.jsonl[.N]", "suppressed_messages", "suppressed_messages_max_size_mb", "suppressed_messages_keep_generations", root="data"),
    _rule("sdk_bash_injection", "sdk_bash_injection.jsonl[.N]", "daemon_log", "sdk_bash_injection_max_size_mb", "suppressed_messages_keep_generations", root="data", path="logs/sdk_bash_injection.jsonl", count_target_file=True),
    _rule("archive_superseded", "*/archive/superseded/*", "delete_old_files", "archive_superseded_retention_days", age_mode="archive", files_only=True, error_label="archived file", success_log="Archive/superseded cleanup: deleted %d files"),
    _rule("archive_versions", "*/archive/versions/*", "archive_versions", "archive_versions_keep_per_file"),
    _rule("shared_inbox", "*/{pending,processed,expired,quarantine}/*", "shared_inbox", "ttl_hours", "expired_retention_days", "processed_retention_days", "quarantine_retention_days", root="data", path="shared/inbox", config_section="inbox"),
    _rule("skill_curator", "*/state/skill_curator/report-<today>.json", "skill_curator"),
)
# fmt: on


# ── Public API ──────────────────────────────────────────────────


async def run_housekeeping(
    data_dir: Path,
    *,
    housekeeping: HousekeepingConfig | None = None,
    inbox: InboxConfig | None = None,
) -> dict[str, Any]:
    """Run all housekeeping tasks. Returns summary of actions taken."""
    if housekeeping is None:
        housekeeping = HousekeepingConfig()
    if inbox is None:
        inbox = InboxConfig()
    loop = asyncio.get_running_loop()
    results: dict[str, Any] = {}

    for rule in _HOUSEKEEPING_RULES:
        try:
            result = await loop.run_in_executor(
                None,
                _execute_housekeeping_rule,
                rule,
                data_dir,
                housekeeping,
                inbox,
            )
            results[rule.result_key] = result
        except Exception:
            logger.exception("Housekeeping: %s", rule.error_message)
            results[rule.result_key] = {"error": True}

    return results


def _execute_housekeeping_rule(
    rule: _HousekeepingRule,
    data_dir: Path,
    housekeeping: HousekeepingConfig,
    inbox: InboxConfig,
) -> dict[str, Any]:
    root = data_dir if rule.root == "data" else data_dir / "animas"
    target = root / rule.path
    config = inbox if rule.config_section == "inbox" else housekeeping
    settings = tuple(getattr(config, key) for key in rule.settings)
    if rule.method == "delete_old_files":
        return _delete_old_files(
            target,
            rule.pattern,
            settings[0],
            age_mode=rule.age_mode or "mtime",
            filename_prefix=rule.filename_prefix,
            retention_cap_days=rule.retention_cap_days,
            files_only=rule.files_only,
            error_label=rule.error_label,
            success_log=rule.success_log,
        )

    result = _HOUSEKEEPING_HANDLERS[rule.method](target, *settings)
    if rule.count_target_file:
        result["files"] = int(target.is_file())
    return result


def _delete_old_files(
    directory: Path,
    pattern: str,
    retention_days: int,
    *,
    age_mode: Literal["mtime", "filename", "archive"] = "mtime",
    filename_prefix: str = "",
    retention_cap_days: int | None = None,
    files_only: bool = False,
    error_label: str = "file",
    success_log: str = "",
) -> dict[str, Any]:
    """Apply a table-driven age policy to matching files."""
    if not directory.exists():
        return {"skipped": True}

    days = min(retention_days, retention_cap_days) if retention_cap_days is not None else retention_days
    cutoff: float | str
    if age_mode == "filename":
        cutoff = (today_local() - timedelta(days=days)).isoformat()
    else:
        cutoff = (now_local() - timedelta(days=days)).timestamp()

    matches = directory.glob(pattern)
    if files_only:
        matches = (path for path in matches if path.is_file())

    deleted = 0
    for path in matches:
        try:
            if age_mode == "filename":
                age: float | str = path.stem[len(filename_prefix) :]
            else:
                stat = path.stat()
                age = max(stat.st_mtime, stat.st_ctime) if age_mode == "archive" else stat.st_mtime
            if age < cutoff:
                path.unlink()
                deleted += 1
        except OSError:
            logger.warning("Failed to delete %s: %s", error_label, path)

    if deleted and success_log:
        logger.info(success_log, deleted)
    return {"deleted_files": deleted}


# ── Sub-functions ───────────────────────────────────────────────


def _run_skill_curator_reports(animas_dir: Path) -> dict[str, Any]:
    """Generate daily deterministic Skill Curator reports for all Animas."""
    if not animas_dir.is_dir():
        return {"skipped": True}
    generated = 0
    for anima_dir in sorted(p for p in animas_dir.iterdir() if p.is_dir()):
        try:
            from core.paths import get_common_skills_dir
            from core.skills.curator import SkillCurator
            from core.skills.index import SkillIndex

            index = SkillIndex(
                anima_dir / "skills",
                get_common_skills_dir(),
                anima_dir / "procedures",
                anima_dir=anima_dir,
            )
            index.build_index()
            report = SkillCurator(anima_dir, common_skills_dir=get_common_skills_dir()).generate_report(
                index.search("", include_blocked=True)
            )
            report_dir = anima_dir / "state" / "skill_curator"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"report-{today_local().isoformat()}.json"
            import json

            atomic_write_text(
                report_path,
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
            )
            generated += 1
        except Exception:
            logger.debug("Skill Curator report failed for %s", anima_dir, exc_info=True)
    return {"generated_reports": generated}


def _rotate_prompt_logs_all(
    animas_dir: Path,
    retention_days: int,
) -> dict[str, Any]:
    """Rotate prompt logs for all Animas."""
    from core.agent.prompt_log import rotate_all_prompt_logs

    if not animas_dir.exists():
        return {"skipped": True}
    result = rotate_all_prompt_logs(animas_dir, retention_days=retention_days)
    total = sum(result.values())
    if total:
        logger.info("Prompt log rotation: deleted %d files across %d animas", total, len(result))
    return {"deleted_files": total, "per_anima": result}


def _rotate_daemon_log(
    log_path: Path,
    max_size_mb: int,
    keep_generations: int,
) -> dict[str, Any]:
    """Size-based rotation for daemon logs using copytruncate strategy.

    Copies current log to .1, shifts .1 → .2, etc., then truncates the
    original path so live processes keep writing through their open fd.
    """
    if not log_path.exists():
        return {"skipped": True, "reason": "file_not_found"}

    parent = log_path.parent
    stem = log_path.name
    deleted = _delete_daemon_log_generations(parent, stem, keep_generations)

    size_mb = log_path.stat().st_size / (1024 * 1024)
    if size_mb < max_size_mb:
        return {
            "skipped": True,
            "current_size_mb": round(size_mb, 1),
            "deleted_generations": deleted,
        }

    # Shift existing generations: .N → .N+1 (highest first)
    for gen in range(keep_generations, 0, -1):
        src = parent / f"{stem}.{gen}"
        dst = parent / f"{stem}.{gen + 1}"
        if src.exists():
            if gen >= keep_generations:
                src.unlink()
            else:
                src.rename(dst)

    # Current → .1, then truncate in place for live redirected stdout/stderr fds.
    gen1 = parent / f"{stem}.1"
    shutil.copyfile(log_path, gen1)
    os.truncate(log_path, 0)

    # Delete over-limit generations
    deleted += _delete_daemon_log_generations(parent, stem, keep_generations)

    logger.info(
        "Daemon log rotated: %.1f MB → %s (deleted %d old generations)",
        size_mb,
        gen1.name,
        deleted,
    )
    return {"rotated": True, "size_mb": round(size_mb, 1), "deleted_generations": deleted}


def _delete_daemon_log_generations(parent: Path, stem: str, keep_generations: int) -> int:
    deleted = 0
    for gen in range(keep_generations + 1, keep_generations + 20):
        old = parent / f"{stem}.{gen}"
        if old.exists():
            old.unlink()
            deleted += 1
    return deleted


def _rotate_suppressed_message_logs(
    data_dir: Path,
    max_size_mb: int,
    keep_generations: int,
) -> dict[str, Any]:
    """Rotate legacy ``suppressed_messages.jsonl`` files by size."""
    if not data_dir.exists():
        return {"skipped": True}

    files = sorted(path for path in data_dir.rglob("suppressed_messages.jsonl") if path.is_file())
    rotated = 0
    skipped = 0
    deleted_generations = 0
    for path in files:
        result = _rotate_daemon_log(path, max_size_mb=max_size_mb, keep_generations=keep_generations)
        if result.get("rotated"):
            rotated += 1
        if result.get("skipped"):
            skipped += 1
        deleted_generations += int(result.get("deleted_generations", 0) or 0)

    return {
        "files": len(files),
        "rotated": rotated,
        "skipped": skipped,
        "deleted_generations": deleted_generations,
    }


def _cleanup_anima_runtime_logs(
    animas_log_dir: Path,
    retention_days: int,
    max_total_size_mb: int,
) -> dict[str, Any]:
    """Delete old per-Anima runtime logs and cap each Anima log directory.

    The active ``current.log`` target and ``stderr.log`` are preserved. This
    complements ``TimedRotatingFileHandler`` because Anima workers use a
    date-stamped base filename on restart, which can leave old files outside
    the handler's backup cleanup.
    """
    if not animas_log_dir.exists():
        return {"skipped": True}

    cutoff_date = today_local() - timedelta(days=retention_days)
    cutoff_ts = (now_local() - timedelta(days=retention_days)).timestamp()
    max_total_bytes = max_total_size_mb * 1024 * 1024
    open_paths = _collect_open_paths(animas_log_dir)

    deleted_files = 0
    capped_files = 0
    freed_bytes = 0
    skipped_open = 0
    per_anima: dict[str, dict[str, int]] = {}

    for anima_log_dir in sorted(p for p in animas_log_dir.iterdir() if p.is_dir()):
        protected = _protected_anima_log_paths(anima_log_dir)
        anima_deleted = 0
        anima_capped = 0
        anima_freed = 0

        for log_file in _iter_anima_log_files(anima_log_dir):
            if _is_protected_path(log_file, protected):
                continue
            try:
                if not _is_old_anima_log(log_file, cutoff_date, cutoff_ts):
                    continue
                if _path_has_open_files(log_file, open_paths):
                    skipped_open += 1
                    continue
                size = log_file.stat().st_size
                log_file.unlink()
                deleted_files += 1
                anima_deleted += 1
                freed_bytes += size
                anima_freed += size
            except OSError:
                logger.warning("Failed to delete old Anima runtime log: %s", log_file, exc_info=True)

        if max_total_bytes > 0:
            total_size = 0
            candidates: list[Path] = []
            for log_file in _iter_anima_log_files(anima_log_dir):
                try:
                    size = log_file.stat().st_size
                except OSError:
                    continue
                total_size += size
                if not _is_protected_path(log_file, protected):
                    candidates.append(log_file)

            for log_file in sorted(candidates, key=_anima_log_delete_sort_key):
                if total_size <= max_total_bytes:
                    break
                try:
                    if _path_has_open_files(log_file, open_paths):
                        skipped_open += 1
                        continue
                    size = log_file.stat().st_size
                    log_file.unlink()
                    total_size -= size
                    deleted_files += 1
                    capped_files += 1
                    anima_deleted += 1
                    anima_capped += 1
                    freed_bytes += size
                    anima_freed += size
                except OSError:
                    logger.warning("Failed to delete capped Anima runtime log: %s", log_file, exc_info=True)

        if anima_deleted:
            per_anima[anima_log_dir.name] = {
                "deleted_files": anima_deleted,
                "capped_files": anima_capped,
                "freed_bytes": anima_freed,
            }

    if deleted_files:
        logger.info(
            "Anima runtime log cleanup: deleted=%d capped=%d freed=%d bytes",
            deleted_files,
            capped_files,
            freed_bytes,
        )
    return {
        "deleted_files": deleted_files,
        "capped_files": capped_files,
        "freed_bytes": freed_bytes,
        "skipped_open": skipped_open,
        "per_anima": per_anima,
    }


def _iter_anima_log_files(anima_log_dir: Path) -> list[Path]:
    return [
        p
        for p in anima_log_dir.iterdir()
        if p.is_file() and not p.is_symlink() and p.name not in {"current.log", "stderr.log"}
    ]


def _protected_anima_log_paths(anima_log_dir: Path) -> set[Path]:
    protected: set[Path] = set()
    current_link = anima_log_dir / "current.log"
    stderr_log = anima_log_dir / "stderr.log"
    if stderr_log.exists():
        protected.add(stderr_log)
    try:
        if current_link.is_symlink():
            protected.add((anima_log_dir / current_link.readlink()).resolve(strict=False))
        elif current_link.is_file():
            target_name = current_link.read_text(encoding="utf-8").strip()
            if target_name:
                protected.add((anima_log_dir / target_name).resolve(strict=False))
    except OSError:
        logger.debug("Failed to resolve current Anima log link: %s", current_link, exc_info=True)
    return {p.resolve(strict=False) for p in protected}


def _is_protected_path(path: Path, protected: set[Path]) -> bool:
    return path.resolve(strict=False) in protected


def _is_old_anima_log(log_file: Path, cutoff_date: date, cutoff_ts: float) -> bool:
    match = _ANIMA_LOG_DATE_RE.search(log_file.name)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d").date() < cutoff_date
        except ValueError:
            pass
    return log_file.stat().st_mtime < cutoff_ts


def _anima_log_delete_sort_key(path: Path) -> tuple[float, str]:
    try:
        return (path.stat().st_mtime, path.name)
    except OSError:
        return (0.0, path.name)


def _cleanup_frontend_logs(frontend_log_dir: Path, backup_count: int) -> dict[str, Any]:
    """Keep only the newest rotated frontend log files."""
    if not frontend_log_dir.exists():
        return {"skipped": True}

    backups = [
        p
        for p in frontend_log_dir.iterdir()
        if p.is_file() and not p.is_symlink() and p.name != "frontend.jsonl" and _frontend_log_sort_key(p)[0]
    ]
    backups.sort(key=_frontend_log_sort_key, reverse=True)

    deleted_files = 0
    freed_bytes = 0
    open_paths = _collect_open_file_paths(backups[max(backup_count, 0) :])
    skipped_open = 0

    for log_file in backups[max(backup_count, 0) :]:
        try:
            if _path_has_open_files(log_file, open_paths):
                skipped_open += 1
                continue
            size = log_file.stat().st_size
            log_file.unlink()
            deleted_files += 1
            freed_bytes += size
        except OSError:
            logger.warning("Failed to delete frontend log backup: %s", log_file, exc_info=True)

    if deleted_files:
        logger.info("Frontend log cleanup: deleted=%d freed=%d bytes", deleted_files, freed_bytes)
    return {"deleted_files": deleted_files, "freed_bytes": freed_bytes, "skipped_open": skipped_open}


def _frontend_log_sort_key(path: Path) -> tuple[str, str]:
    if path.name.startswith("frontend.jsonl."):
        stamp = path.name.rsplit(".", 1)[-1]
        if re.fullmatch(r"\d{8}", stamp):
            return (stamp, path.name)
    if path.name.endswith(".jsonl") and re.fullmatch(r"\d{8}", path.stem):
        return (path.stem, path.name)
    return ("", path.name)


def _cleanup_shared_inbox(
    inbox_root: Path,
    ttl_hours: float,
    expired_retention_days: int,
    processed_retention_days: int,
    quarantine_retention_days: int,
) -> dict[str, Any]:
    """Sweep stale files and rotate archives under shared/inbox/<anima>/."""
    if not inbox_root.exists():
        return {"skipped": True}

    from core.messaging.messenger import Messenger

    shared_dir = inbox_root.parent
    totals: dict[str, Any] = {
        "animas": 0,
        "expired": 0,
        "protected": 0,
        "quarantined": 0,
        "deleted_expired": 0,
        "deleted_processed": 0,
        "deleted_quarantine": 0,
        "errors": 0,
    }
    per_anima: dict[str, dict[str, int]] = {}

    for inbox_dir in sorted(inbox_root.iterdir()):
        if not inbox_dir.is_dir() or inbox_dir.name.startswith("."):
            continue
        messenger = Messenger(shared_dir, inbox_dir.name)
        result = messenger.sweep_expired(
            ttl_hours=ttl_hours,
            expired_retention_days=expired_retention_days,
            processed_retention_days=processed_retention_days,
            quarantine_retention_days=quarantine_retention_days,
        )
        totals["animas"] += 1
        for key, value in result.items():
            totals[key] = totals.get(key, 0) + value
        if any(result.values()):
            per_anima[inbox_dir.name] = result

    if per_anima:
        logger.info("Shared inbox cleanup: %s", per_anima)
    totals["per_anima"] = per_anima
    return totals


def _cleanup_dm_archives(dm_logs_dir: Path, retention_days: int) -> dict[str, Any]:
    """Delete DM log archive files older than *retention_days*."""
    return _delete_old_files(
        dm_logs_dir,
        "*.archive.jsonl",
        retention_days,
        error_label="dm archive",
        success_log="DM archive cleanup: deleted %d files",
    )


def _cleanup_cron_logs(animas_dir: Path, retention_days: int) -> dict[str, Any]:
    """Delete filename-dated cron logs, with the historical 14-day cap."""
    return _delete_old_files(
        animas_dir,
        "*/state/cron_logs/*.jsonl",
        retention_days,
        age_mode="filename",
        retention_cap_days=14,
        error_label="cron log",
        success_log="Cron log cleanup: deleted %d files",
    )


def _episodeify_abandoned_session(anima_dir: Path, json_path: Path) -> bool:
    """Persist an abandoned short-term session as an episode before deletion.

    An expired ``session_state.json`` represents a chat session that crossed
    the context-window threshold, externalized its state, but was never
    finalized into long-term memory. Rather than losing it at retention expiry,
    fold its accumulated content into ``episodes/`` so it stays searchable.

    Returns True when the state file may be deleted (episode saved, or the file
    holds no recoverable content), and False when the episode write failed and
    deletion should be retried on the next housekeeping run.
    """
    import json

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Truly corrupt state carries no recoverable memory.
        return True
    except OSError:
        # Transient I/O failure (e.g. FD exhaustion): the content may still be
        # recoverable, so keep the file and retry on the next run.
        logger.warning(
            "Failed to read abandoned shortterm session %s; deferring deletion",
            json_path,
            exc_info=True,
        )
        return False
    if not isinstance(data, dict):
        return True

    prompt = (data.get("original_prompt") or "").strip()
    response = (data.get("accumulated_response") or "").strip()
    notes = (data.get("notes") or "").strip()
    if not prompt and not response and not notes:
        return True

    body_parts: list[str] = []
    if prompt:
        body_parts.append(f"{t('shortterm.original_request')}\n{prompt}")
    if response:
        body_parts.append(f"{t('shortterm.work_so_far')}\n{response}")
    if notes:
        body_parts.append(f"{t('shortterm.notes_header')}\n{notes}")
    entry = f"## {t('shortterm.title')}\n\n" + "\n\n".join(body_parts) + "\n"

    try:
        from core.memory.manager import MemoryManager

        MemoryManager(anima_dir).append_episode(entry, origin="shortterm_recovery")
        return True
    except Exception:
        logger.warning(
            "Failed to episode-ify abandoned shortterm session %s; deferring deletion",
            json_path,
            exc_info=True,
        )
        return False


def _cleanup_shortterm(
    animas_dir: Path,
    retention_days: int,
    archive_retention_days: int = 30,
    thread_gc_days: int = 30,
) -> dict[str, Any]:
    """Delete old session files from shortterm/ directories.

    Recurses into per-thread subdirectories (``shortterm/chat/{thread_id}/``)
    as well as the supported lifecycle folders. Archive files use their own
    retention window. Before removing an expired ``session_state.json`` from a
    chat tree, its unfinalized content is saved as an episode; if that save
    fails, the file and its thread directory are kept for retry.

    Skips ``current_session_*.json`` and ``streaming_journal*.jsonl``
    during individual file cleanup. Stale chat thread directories are removed
    as a unit once every file in them is older than the thread GC window. The
    directory is rescanned immediately before deletion to reduce TOCTOU risk;
    a write after that final scan remains an accepted residual race.
    """
    if not animas_dir.exists():
        return {"skipped": True}

    retention_days = max(retention_days, 0)
    archive_cleanup_enabled = archive_retention_days > 0
    thread_gc_enabled = thread_gc_days > 0
    skipped_substeps: dict[str, str] = {}
    if not archive_cleanup_enabled:
        skipped_substeps["archive_cleanup"] = "archive_retention_days_must_be_positive"
    if not thread_gc_enabled:
        skipped_substeps["thread_gc"] = "thread_gc_days_must_be_positive"
    now = now_local()
    cutoff_ts = (now - timedelta(days=retention_days)).timestamp()
    archive_cutoff_ts = (now - timedelta(days=archive_retention_days)).timestamp() if archive_cleanup_enabled else None
    thread_gc_cutoff_ts = (now - timedelta(days=thread_gc_days)).timestamp() if thread_gc_enabled else None
    total_deleted = 0
    total_episodified = 0
    archive_deleted = 0
    thread_dirs_deleted = 0
    deleted_by_subdir = {sub: 0 for sub in ("chat", "heartbeat", "cron", "inbox", "task")}

    for anima_dir in sorted(animas_dir.iterdir()):
        if not anima_dir.is_dir():
            continue
        shortterm_dir = anima_dir / "shortterm"
        if not shortterm_dir.is_dir():
            continue
        gc_protected_thread_dirs: set[Path] = set()
        for sub in deleted_by_subdir:
            sub_dir = shortterm_dir / sub
            if not sub_dir.is_dir():
                continue
            for f in list(sub_dir.rglob("*")):
                if not f.is_file():
                    continue
                relative_parts = f.relative_to(sub_dir).parts
                is_archive = "archive" in relative_parts
                if is_archive and not archive_cleanup_enabled:
                    continue
                if any(f.name.startswith(p) for p in _PROTECTED_PREFIXES):
                    continue
                try:
                    file_cutoff_ts = archive_cutoff_ts if is_archive else cutoff_ts
                    if file_cutoff_ts is None:
                        continue
                    if f.stat().st_mtime >= file_cutoff_ts:
                        continue
                except OSError:
                    logger.warning("Failed to stat shortterm file: %s", f)
                    continue
                # Preserve abandoned chat sessions as episodes before deletion.
                episodified = False
                if sub == "chat" and f.name == "session_state.json":
                    if not _episodeify_abandoned_session(anima_dir, f):
                        if len(relative_parts) > 1 and relative_parts[0] != "archive":
                            gc_protected_thread_dirs.add(sub_dir / relative_parts[0])
                        continue  # keep the file; retry next run
                    episodified = True
                try:
                    f.unlink()
                    total_deleted += 1
                    deleted_by_subdir[sub] += 1
                    if is_archive:
                        archive_deleted += 1
                    if episodified:
                        total_episodified += 1
                except OSError:
                    if episodified:
                        # Already saved as an episode: rename so the next run
                        # does not episodify it again (duplicate episode). The
                        # renamed file keeps its expired mtime and is swept by
                        # the generic deletion above on a later run.
                        try:
                            f.rename(f.with_name(f.name + ".episodified.bak"))
                            total_episodified += 1
                            logger.warning(
                                "Failed to delete episodified shortterm state; renamed for later sweep: %s",
                                f,
                            )
                        except OSError:
                            logger.error(
                                "Failed to delete or rename episodified shortterm state %s; "
                                "a duplicate episode may result on the next run",
                                f,
                            )
                    else:
                        logger.warning("Failed to delete shortterm file: %s", f)

        chat_dir = shortterm_dir / "chat"
        if not thread_gc_enabled or thread_gc_cutoff_ts is None or not chat_dir.is_dir():
            continue
        for thread_dir in sorted(path for path in chat_dir.iterdir() if path.is_dir()):
            if thread_dir.name == "archive" or thread_dir in gc_protected_thread_dirs:
                continue
            snapshot = _scan_shortterm_thread_for_gc(thread_dir, thread_gc_cutoff_ts)
            if snapshot is None:
                continue
            files, max_mtime, recent_protected = snapshot
            if recent_protected:
                continue
            if max_mtime is not None and max_mtime >= thread_gc_cutoff_ts:
                continue

            # Recheck immediately before rmtree. A write after this scan is the
            # documented residual race.
            rechecked = _scan_shortterm_thread_for_gc(thread_dir, thread_gc_cutoff_ts)
            if rechecked is None:
                continue
            files, max_mtime, recent_protected = rechecked
            if recent_protected or (max_mtime is not None and max_mtime >= thread_gc_cutoff_ts):
                continue
            deleted_file_count = len(files)
            deleted_archive_count = sum("archive" in f.relative_to(thread_dir).parts for f in files)
            try:
                shutil.rmtree(thread_dir)
            except OSError:
                logger.warning("Failed to delete stale shortterm thread directory: %s", thread_dir)
                continue
            thread_dirs_deleted += 1
            total_deleted += deleted_file_count
            archive_deleted += deleted_archive_count
            deleted_by_subdir["chat"] += deleted_file_count

    if total_deleted or total_episodified or thread_dirs_deleted:
        logger.info(
            "Shortterm cleanup: deleted=%d archive_deleted=%d thread_dirs_deleted=%d episodified=%d by_subdir=%s",
            total_deleted,
            archive_deleted,
            thread_dirs_deleted,
            total_episodified,
            deleted_by_subdir,
        )
    return {
        "deleted_files": total_deleted,
        "archive_deleted": archive_deleted,
        "thread_dirs_deleted": thread_dirs_deleted,
        "deleted_by_subdir": deleted_by_subdir,
        "episodified_sessions": total_episodified,
        "skipped_substeps": skipped_substeps,
    }


def _scan_shortterm_thread_for_gc(
    thread_dir: Path,
    cutoff_ts: float,
) -> tuple[list[Path], float | None, bool] | None:
    """Return a conservative thread snapshot, or ``None`` on any stat failure."""
    try:
        files = [path for path in thread_dir.rglob("*") if path.is_file()]
    except OSError:
        logger.warning("Failed to scan shortterm thread directory: %s", thread_dir)
        return None
    max_mtime: float | None = None
    recent_protected = False
    for path in files:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            logger.warning("Failed to stat shortterm thread file: %s", path)
            return None
        max_mtime = mtime if max_mtime is None else max(max_mtime, mtime)
        if mtime >= cutoff_ts and any(path.name.startswith(prefix) for prefix in _PROTECTED_PREFIXES):
            recent_protected = True
    return files, max_mtime, recent_protected


def _cleanup_facts_locks(animas_dir: Path, stale_hours: int) -> dict[str, Any]:
    """Delete stale empty ``facts/*.lock`` files for every Anima."""
    if not animas_dir.exists():
        return {"skipped": True}
    if stale_hours <= 0:
        return {
            "skipped": True,
            "reason": "stale_hours_must_be_positive",
            "scanned_files": 0,
            "deleted_files": 0,
        }

    cutoff_ts = (now_local() - timedelta(hours=stale_hours)).timestamp()
    deleted_files = 0
    scanned_files = 0
    locked_files = 0
    lock_failures = 0

    for anima_dir in sorted(animas_dir.iterdir()):
        if not anima_dir.is_dir():
            continue
        facts_dir = anima_dir / "facts"
        if not facts_dir.is_dir():
            continue
        for lock_file in sorted(facts_dir.glob("*.lock")):
            if not lock_file.is_file():
                continue
            scanned_files += 1
            try:
                with lock_file.open("r+b") as lock_handle:
                    acquired = False
                    try:
                        try:
                            acquire_file_lock(lock_handle, exclusive=True, blocking=False)
                            acquired = True
                        except OSError as exc:
                            if exc.errno in (errno.EACCES, errno.EAGAIN):
                                locked_files += 1
                            else:
                                lock_failures += 1
                                logger.warning("Failed to acquire facts lock file: %s", lock_file)
                            continue

                        stat = os.fstat(lock_handle.fileno())
                        path_stat = lock_file.stat()
                        if (stat.st_dev, stat.st_ino) != (path_stat.st_dev, path_stat.st_ino):
                            lock_failures += 1
                            continue
                        if stat.st_size != 0 or stat.st_mtime >= cutoff_ts:
                            continue
                        lock_file.unlink()
                        deleted_files += 1
                    finally:
                        if acquired:
                            release_file_lock(lock_handle)
            except OSError:
                logger.warning("Failed to inspect or delete facts lock file: %s", lock_file)
                lock_failures += 1

    if deleted_files:
        logger.info(
            "Facts lock cleanup: scanned=%d deleted=%d stale_hours=%d",
            scanned_files,
            deleted_files,
            stale_hours,
        )
    return {
        "scanned_files": scanned_files,
        "deleted_files": deleted_files,
        "locked_files": locked_files,
        "lock_failures": lock_failures,
    }


def _cleanup_curator_reports(animas_dir: Path, retention_days: int) -> dict[str, Any]:
    """Delete reports whose ``report-YYYY-MM-DD.json`` date has expired."""
    return _delete_old_files(
        animas_dir,
        "*/state/skill_curator/report-*.json",
        retention_days,
        age_mode="filename",
        filename_prefix="report-",
        error_label="curator report",
        success_log="Curator report cleanup: deleted %d files",
    )


def _cleanup_task_results(animas_dir: Path, retention_days: int) -> dict[str, Any]:
    """Delete old task result files from state/task_results/."""
    return _delete_old_files(
        animas_dir,
        "*/state/task_results/*.md",
        retention_days,
        error_label="task result",
        success_log="Task results cleanup: deleted %d files",
    )


def _rotate_archive_superseded(animas_dir: Path, retention_days: int) -> dict[str, Any]:
    """Expire files by max(mtime, ctime), which approximates archive-entry time."""
    return _delete_old_files(
        animas_dir,
        "*/archive/superseded/*",
        retention_days,
        age_mode="archive",
        files_only=True,
        error_label="archived file",
        success_log="Archive/superseded cleanup: deleted %d files",
    )


def _prune_archive_versions(animas_dir: Path, keep_per_file: int) -> dict[str, Any]:
    """Keep only the newest archive versions for each source file and suffix."""
    if not animas_dir.is_dir():
        return {"skipped": True}

    found_versions_dir = False
    total_files = 0
    deleted_files = 0

    for anima_dir in sorted(animas_dir.iterdir()):
        if not anima_dir.is_dir():
            continue
        versions_dir = anima_dir / "archive" / "versions"
        if not versions_dir.is_dir():
            logger.debug("Archive versions directory not found: %s", versions_dir)
            continue

        found_versions_dir = True
        groups: dict[tuple[str, str], list[tuple[str, int, Path]]] = {}
        for path in versions_dir.iterdir():
            if not path.is_file():
                logger.debug("Ignoring non-file in archive versions: %s", path)
                continue
            match = _ARCHIVE_VERSION_RE.match(path.name)
            if match is None:
                logger.debug("Ignoring unrecognized archive version filename: %s", path)
                continue
            stem = match.group("stem")
            suffix = match.group("suffix")
            version = int(match.group("version"))
            timestamp = match.group("ts")
            groups.setdefault((stem, suffix), []).append((timestamp, version, path))

        for versions in groups.values():
            versions.sort(key=lambda item: (item[0], item[1]), reverse=True)
            total_files += len(versions)
            for _, _, path in versions[keep_per_file:]:
                try:
                    path.unlink()
                    deleted_files += 1
                except OSError:
                    logger.warning("Failed to prune archived version: %s", path, exc_info=True)

    if not found_versions_dir:
        return {"skipped": True}

    kept_files = total_files - deleted_files
    if deleted_files:
        logger.info("Archive/versions cleanup: deleted %d files, kept %d", deleted_files, kept_files)
    return {"deleted_files": deleted_files, "kept_files": kept_files}


_CORRUPT_VECTORDB_RE = re.compile(r"^(?:vectordb-corrupt|corrupt-vectordb)[-_](?P<stamp>\d{8}[-_]?\d{6}|\d{14})")


def _corrupt_archive_sort_key(path: Path) -> tuple[str, str]:
    match = _CORRUPT_VECTORDB_RE.match(path.name)
    if match:
        return (match.group("stamp").replace("_", "").replace("-", ""), path.name)
    return ("", path.name)


def _path_size(path: Path) -> int:
    if path.is_symlink() or not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file() and not child.is_symlink())


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _cleanup_corrupt_vectordb_archives(
    animas_dir: Path,
    keep_generations: int,
) -> dict[str, Any]:
    """Keep only the newest corrupt vectordb archives per Anima."""
    if not animas_dir.exists():
        return {"skipped": True}

    deleted_dirs = 0
    freed_bytes = 0
    per_anima: dict[str, int] = {}

    for anima_dir in sorted(p for p in animas_dir.iterdir() if p.is_dir()):
        archive_dir = anima_dir / "archive"
        if not archive_dir.is_dir():
            continue
        archives = [
            p
            for p in archive_dir.iterdir()
            if p.is_dir() and (p.name.startswith("vectordb-corrupt-") or p.name.startswith("corrupt-vectordb-"))
        ]
        archives.sort(key=_corrupt_archive_sort_key, reverse=True)
        for archive in archives[max(keep_generations, 0) :]:
            try:
                size = _path_size(archive)
                _remove_path(archive)
                deleted_dirs += 1
                freed_bytes += size
                per_anima[anima_dir.name] = per_anima.get(anima_dir.name, 0) + 1
            except OSError:
                logger.warning("Failed to delete corrupt vectordb archive: %s", archive, exc_info=True)

    if deleted_dirs:
        logger.info("Corrupt vectordb archive cleanup: deleted=%d freed=%d bytes", deleted_dirs, freed_bytes)
    return {"deleted_dirs": deleted_dirs, "freed_bytes": freed_bytes, "per_anima": per_anima}


def _cleanup_runtime_tmp(tmp_dir: Path, retention_days: int) -> dict[str, Any]:
    """Delete old top-level entries while retaining selected tmp roots."""
    if not tmp_dir.exists():
        return {"skipped": True}

    cutoff = (now_local() - timedelta(days=retention_days)).timestamp()
    result = _cleanup_tree_children(
        tmp_dir,
        cutoff,
        _collect_open_tmp_paths(tmp_dir),
        skip_hidden=True,
        count_skipped_symlinks=True,
        preserved_roots=_PRESERVED_TMP_SUBDIRS,
        open_warning="Runtime tmp entry is open; skipping: %s",
        error_label="runtime tmp entry",
    )
    if result["deleted_entries"]:
        logger.info(
            "Runtime tmp cleanup: deleted=%d freed=%d bytes",
            result["deleted_entries"],
            result["freed_bytes"],
        )
    return {key: result[key] for key in ("deleted_entries", "freed_bytes", "skipped_count", "errors")}


def _cleanup_tree_children(
    root: Path,
    cutoff_ts: float,
    open_paths: set[Path],
    *,
    skip_hidden: bool = False,
    count_skipped_symlinks: bool = False,
    preserved_roots: frozenset[str] = frozenset(),
    open_warning: str | None = None,
    error_label: str,
) -> dict[str, Any]:
    """Remove stale children using shared tree-age, open-file and size rules."""
    result: dict[str, Any] = {
        "deleted_entries": 0,
        "freed_bytes": 0,
        "skipped_count": 0,
        "skipped_open": 0,
        "errors": [],
    }
    for entry in sorted(root.iterdir()):
        if skip_hidden and entry.name.startswith("."):
            continue
        if entry.is_symlink():
            result["skipped_count"] += int(count_skipped_symlinks)
            continue
        if entry.name in preserved_roots and entry.is_dir():
            nested = _cleanup_tree_children(
                entry,
                cutoff_ts,
                open_paths,
                skip_hidden=skip_hidden,
                count_skipped_symlinks=count_skipped_symlinks,
                open_warning=open_warning,
                error_label=error_label,
            )
            for key in ("deleted_entries", "freed_bytes", "skipped_count", "skipped_open"):
                result[key] += nested[key]
            result["errors"].extend(nested["errors"])
            continue
        try:
            if not _path_tree_older_than(entry, cutoff_ts):
                continue
            if _path_has_open_files(entry, open_paths):
                result["skipped_count"] += 1
                result["skipped_open"] += 1
                if open_warning:
                    logger.warning(open_warning, entry)
                continue
            size = _path_size(entry)
            _remove_path(entry)
            result["deleted_entries"] += 1
            result["freed_bytes"] += size
        except OSError as exc:
            logger.warning("Failed to delete %s: %s", error_label, entry, exc_info=True)
            result["skipped_count"] += 1
            result["errors"].append(f"{entry}: {exc}")
    return result


def _path_tree_older_than(path: Path, cutoff_ts: float) -> bool:
    try:
        if path.stat().st_mtime >= cutoff_ts:
            return False
    except FileNotFoundError:
        return False
    except OSError:
        return False
    if path.is_dir() and not path.is_symlink():
        for child in path.rglob("*"):
            try:
                if child.stat().st_mtime >= cutoff_ts:
                    return False
            except FileNotFoundError:
                continue
            except OSError:
                return False
    return True


def _collect_open_tmp_paths(root: Path) -> set[Path]:
    return _collect_open_paths(root)


def _collect_open_paths(root: Path) -> set[Path]:
    lsof = shutil.which("lsof")
    if not lsof:
        return set()
    return _run_lsof(
        [lsof, "-F", "n", "+D", str(root)],
        timeout=10,
        target=root,
        timeout_message="Runtime tmp lsof scan timed out; proceeding without open-file skips for %s",
        debug_message="Runtime tmp lsof scan exited with status %s for %s",
    )


def _collect_open_file_paths(paths_to_check: Iterable[Path]) -> set[Path]:
    paths = [path for path in paths_to_check if path.exists()]
    lsof = shutil.which("lsof")
    if not lsof or not paths:
        return set()
    return _run_lsof(
        [lsof, "-F", "n", "--", *(str(path) for path in paths)],
        timeout=5,
        target=paths,
        timeout_message="Open-file scan timed out; proceeding without open-file skips for %s",
    )


def _run_lsof(
    command: list[str],
    *,
    timeout: int,
    target: Path | list[Path],
    timeout_message: str,
    debug_message: str = "",
) -> set[Path]:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning(timeout_message, target)
        return set()
    if debug_message and result.returncode not in (0, 1):
        logger.debug(debug_message, result.returncode, target)
    return {
        Path(raw_path).resolve(strict=False)
        for line in result.stdout.splitlines()
        if line.startswith("n") and (raw_path := line[1:].split(" (", 1)[0])
    }


def _path_has_open_files(path: Path, open_paths: set[Path]) -> bool:
    if not open_paths:
        return False
    resolved = path.resolve(strict=False)
    if resolved in open_paths:
        return True
    if path.is_dir():
        return any(open_path.is_relative_to(resolved) for open_path in open_paths)
    return False


def _cleanup_backup_dirs(animas_dir: Path, retention_days: int) -> dict[str, Any]:
    """Delete old explicit backup directories such as assets_backup_*."""
    if not animas_dir.exists():
        return {"skipped": True}

    cutoff_ts = (now_local() - timedelta(days=retention_days)).timestamp()
    deleted_dirs = 0
    freed_bytes = 0

    for anima_dir in sorted(p for p in animas_dir.iterdir() if p.is_dir()):
        for backup_dir in sorted(p for p in anima_dir.iterdir() if p.is_dir() and not p.is_symlink()):
            if "_backup_" not in backup_dir.name:
                continue
            try:
                if backup_dir.stat().st_mtime >= cutoff_ts:
                    continue
                size = _path_size(backup_dir)
                _remove_path(backup_dir)
                deleted_dirs += 1
                freed_bytes += size
            except OSError:
                logger.warning("Failed to delete backup dir: %s", backup_dir, exc_info=True)

    if deleted_dirs:
        logger.info("Backup dir cleanup: deleted=%d freed=%d bytes", deleted_dirs, freed_bytes)
    return {"deleted_dirs": deleted_dirs, "freed_bytes": freed_bytes}


def _cleanup_codex_execution_logs(animas_dir: Path, max_size_mb: int) -> dict[str, Any]:
    """Delete oversized Codex execution log databases, preserving state/session DBs."""
    if not animas_dir.exists():
        return {"skipped": True}

    max_bytes = max_size_mb * 1024 * 1024
    deleted_databases = 0
    deleted_files = 0
    freed_bytes = 0
    skipped_open = 0

    for db in sorted(animas_dir.glob(f"*/.codex_home/{_CODEX_LOG_DB_NAME}")):
        try:
            if db.stat().st_size <= max_bytes:
                continue
            bundle = [
                p
                for p in (db, db.with_name(f"{_CODEX_LOG_DB_NAME}-wal"), db.with_name(f"{_CODEX_LOG_DB_NAME}-shm"))
                if p.exists()
            ]
            open_paths = _collect_open_file_paths(bundle)
            if any(_path_has_open_files(p, open_paths) for p in bundle):
                skipped_open += 1
                logger.warning("Codex execution log DB is open; skipping: %s", db)
                continue
            bundle_size = sum(_path_size(p) for p in bundle)
            for path in bundle:
                path.unlink(missing_ok=True)
                deleted_files += 1
            deleted_databases += 1
            freed_bytes += bundle_size
        except OSError:
            logger.warning("Failed to delete Codex execution log DB: %s", db, exc_info=True)

    if deleted_databases:
        logger.info(
            "Codex execution log cleanup: databases=%d files=%d freed=%d bytes",
            deleted_databases,
            deleted_files,
            freed_bytes,
        )
    return {
        "deleted_databases": deleted_databases,
        "deleted_files": deleted_files,
        "freed_bytes": freed_bytes,
        "skipped_open": skipped_open,
    }


def _cleanup_codex_tmp_dirs(animas_dir: Path, retention_hours: int) -> dict[str, Any]:
    """Delete stale temporary entries under per-Anima CODEX_HOME directories."""
    if not animas_dir.exists():
        return {"skipped": True}

    cutoff = (now_local() - timedelta(hours=retention_hours)).timestamp()
    totals = {"deleted_entries": 0, "freed_bytes": 0, "skipped_open": 0}
    for codex_home in sorted(animas_dir.glob("*/.codex_home")):
        for name in (".tmp", "tmp"):
            tmp_root = codex_home / name
            if not tmp_root.is_dir():
                continue
            result = _cleanup_tree_children(
                tmp_root,
                cutoff,
                _collect_open_paths(tmp_root),
                open_warning="Codex tmp entry is open; skipping: %s",
                error_label="Codex tmp entry",
            )
            for key in totals:
                totals[key] += result[key]

    if totals["deleted_entries"]:
        logger.info("Codex tmp cleanup: deleted=%d freed=%d bytes", totals["deleted_entries"], totals["freed_bytes"])
    return totals


def _cleanup_anima_runtime_artifacts(
    animas_dir: Path,
    tmp_gitdirs_retention_days: int,
    local_log_retention_days: int,
) -> dict[str, Any]:
    """Delete old per-Anima temporary git dirs and local runtime log files."""
    if not animas_dir.exists():
        return {"skipped": True}

    tmp_cutoff_ts = (now_local() - timedelta(days=tmp_gitdirs_retention_days)).timestamp()
    log_cutoff_ts = (now_local() - timedelta(days=local_log_retention_days)).timestamp()
    tmp_gitdirs_deleted = 0
    local_logs_deleted = 0
    freed_bytes = 0
    skipped_open = 0

    for anima_dir in sorted(p for p in animas_dir.iterdir() if p.is_dir()):
        tmp_gitdirs = anima_dir / "tmp_gitdirs"
        if tmp_gitdirs.is_dir():
            result = _cleanup_tree_children(
                tmp_gitdirs,
                tmp_cutoff_ts,
                _collect_open_paths(tmp_gitdirs),
                error_label="tmp gitdir artifact",
            )
            tmp_gitdirs_deleted += result["deleted_entries"]
            freed_bytes += result["freed_bytes"]
            skipped_open += result["skipped_open"]

        local_logs = anima_dir / "logs"
        if local_logs.is_dir():
            open_paths = _collect_open_paths(local_logs)
            for log_file in sorted(p for p in local_logs.rglob("*") if p.is_file() and not p.is_symlink()):
                try:
                    if log_file.stat().st_mtime >= log_cutoff_ts:
                        continue
                    if _path_has_open_files(log_file, open_paths):
                        skipped_open += 1
                        continue
                    size = log_file.stat().st_size
                    log_file.unlink()
                    local_logs_deleted += 1
                    freed_bytes += size
                except OSError:
                    logger.warning("Failed to delete local Anima runtime log: %s", log_file, exc_info=True)

    if tmp_gitdirs_deleted or local_logs_deleted:
        logger.info(
            "Anima runtime artifact cleanup: tmp_gitdirs=%d local_logs=%d freed=%d bytes",
            tmp_gitdirs_deleted,
            local_logs_deleted,
            freed_bytes,
        )
    return {
        "tmp_gitdirs_deleted": tmp_gitdirs_deleted,
        "local_logs_deleted": local_logs_deleted,
        "freed_bytes": freed_bytes,
        "skipped_open": skipped_open,
    }


def _cleanup_taskboard_stale(
    data_dir: Path,
    pending_processing_stale_hours: int,
    background_running_stale_hours: int,
    current_state_stale_hours: int,
) -> dict[str, Any]:
    from core.tasks.board.housekeeping import cleanup_taskboard_stale_artifacts

    return cleanup_taskboard_stale_artifacts(
        data_dir,
        pending_processing_stale_hours,
        background_running_stale_hours,
        current_state_stale_hours,
    )


_HOUSEKEEPING_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "prompt_logs": _rotate_prompt_logs_all,
    "daemon_log": _rotate_daemon_log,
    "anima_logs": _cleanup_anima_runtime_logs,
    "frontend_logs": _cleanup_frontend_logs,
    "shortterm": _cleanup_shortterm,
    "facts_locks": _cleanup_facts_locks,
    "corrupt_vectordb_archives": _cleanup_corrupt_vectordb_archives,
    "runtime_tmp": _cleanup_runtime_tmp,
    "backup_dirs": _cleanup_backup_dirs,
    "codex_execution_logs": _cleanup_codex_execution_logs,
    "codex_tmp": _cleanup_codex_tmp_dirs,
    "anima_runtime_artifacts": _cleanup_anima_runtime_artifacts,
    "taskboard_stale": _cleanup_taskboard_stale,
    "suppressed_messages": _rotate_suppressed_message_logs,
    "archive_versions": _prune_archive_versions,
    "shared_inbox": _cleanup_shared_inbox,
    "skill_curator": _run_skill_curator_reports,
}
