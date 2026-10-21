from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_store(db_path: Path):
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from swe.ci_autofix_intake import CIAutofixIntakeStore

    return CIAutofixIntakeStore(db_path)


def _strip_model_prefix(provider: str, model: str) -> str:
    model = str(model or "").strip()
    provider = str(provider or "").strip()
    if provider in {"codex", "openai"} and model.startswith("codex/"):
        return model.split("/", 1)[1]
    if provider in {"anthropic", "claude_code"} and model.startswith("anthropic/"):
        return model.split("/", 1)[1]
    return model


def _build_prompt(job, attempt: int) -> str:
    return f"""GitHub Actions auto-fix task for AnimaWorks.

Repository: {job.repo}
Branch: {job.branch}
Failing run: https://github.com/{job.repo}/actions/runs/{job.last_run_id}
Attempt: {attempt}/{job.max_attempts}

Goal:
1. Inspect the failing GitHub Actions run and failed logs.
2. Fix the root cause in this repository.
3. Run focused local verification.
4. Commit only the relevant changes.
5. Push ONCE using: git push origin HEAD:refs/heads/{job.branch}.
6. Immediately finish after this push. The controller watches CI and starts the next attempt if necessary.

Operational rules:
- Use rtk for shell commands.
- This is an isolated detached worktree prepared from origin/{job.branch}. Stay in this directory; do not switch branches or create another worktree.
- Do not revert unrelated user changes.
- Keep commits scoped.
- Never pip/uv install into the global Python (D:\\Program Files\\Python\\Python311) or any shared venv (E:\\OneDriveBiz\\Tools\\abconfig\\*, the running animaworks .venv). Other tools resolve CLIs from them; a stray notebooklm-py 0.3.4 there broke NotebookLM auth for the NBO pipeline. If dependencies are needed, create a throwaway venv inside this worktree (e.g. `uv venv .venv-autofix`) and install there.
- One attempt is ONE repair/push cycle. Do not watch, poll, rerun, or wait for CI after pushing. Do not start another repair cycle.
- If authentication, permissions or missing information block the fix, explain the blocker and finish.
- Final output should summarize the pushed commit SHA or the precise blocker.
"""


def _command_for_job(job, repo_root: Path, prompt_path: Path) -> list[str]:
    provider = str(job.llm_provider or "").strip()
    model = _strip_model_prefix(provider, str(job.llm_model or "").strip())

    if provider in {"anthropic", "claude_code"}:
        exe = shutil.which("claude.cmd") or shutil.which("claude") or "claude"
        cmd = [
            exe,
            "--print",
            "--permission-mode",
            "bypassPermissions",
            "--add-dir",
            str(repo_root),
        ]
        if model:
            cmd.extend(["--model", model])
        return cmd

    exe = shutil.which("codex.cmd") or shutil.which("codex") or "codex"
    cmd = [
        exe,
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        str(repo_root),
    ]
    if model:
        cmd.extend(["-m", model])
    cmd.extend(["--output-last-message", str(prompt_path.with_name("final.txt")), "-"])
    return cmd


def _failure_context(store, job) -> str:
    event = store.latest_event(job.id, ("CI failure evidence captured",))
    if not event or event.data.get("run_id") != job.last_run_id:
        return ""
    lines = ["\nConfirmed failed jobs (other CI jobs may still be running):"]
    for item in event.data.get("failed_jobs", []):
        path = Path(item["log_path"])
        lines.append(f"\nFailed job: {item['name']}\nComplete log: {path}")
        if path.is_file():
            lines.append(path.read_text(encoding="utf-8", errors="replace")[-12000:])
    lines.append("\nFix these confirmed failures now. Do not wait for other CI jobs or for run-level logs to become available.")
    return "\n".join(lines)


def _git_head(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _prepare_workspace(source: Path, destination: Path, branch: str) -> Path:
    for args in (["fetch", "--no-tags", "origin", branch],
                 ["worktree", "add", "--detach", str(destination), "FETCH_HEAD"]):
        result = subprocess.run(["git", *args], cwd=source, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout)[-2000:])
    return destination


def _pushed_commit(workspace: Path, branch: str, before: str) -> str:
    head = _git_head(workspace)
    if not head or head == before:
        return ""
    result = subprocess.run(
        ["git", "ls-remote", "origin", f"refs/heads/{branch}"], cwd=workspace,
        capture_output=True, text=True, timeout=30,
    )
    remote = result.stdout.split()[0] if result.returncode == 0 and result.stdout.strip() else ""
    return remote if remote.startswith(head) else ""


def _stop_agent(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=30)
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    proc.wait(timeout=30)


def _run_one_cycle(proc, workspace: Path, branch: str, before: str, timeout: int) -> tuple[int, str, str]:
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                code = None
            pushed = _pushed_commit(workspace, branch, before)
            if pushed:
                # End this agent after its first confirmed push, even if it
                # ignores the prompt and starts polling CI or another repair.
                _stop_agent(proc)
                return 0, pushed, ""
            if code is not None:
                return code, "", "新しいコミットのpushを確認できません。エージェントの報告を確認してください。"
            if time.monotonic() >= deadline:
                return 124, "", f"修正処理が制限時間（{timeout // 60}分）に達したため停止しました。"
    finally:
        _stop_agent(proc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one CI autofix LLM attempt and record events.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--job-id", required=True, type=int)
    parser.add_argument("--repo-root", default=str(_repo_root()))
    parser.add_argument("--agent-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    db_path = Path(args.db)
    repo_root = Path(args.repo_root).resolve()
    store = _load_store(db_path)
    try:
        job = store.begin_attempt(args.job_id)
    except RuntimeError:
        # A duplicate launcher must not consume a second attempt.
        return 0
    attempt = job.attempt_count
    if job.dry_run:
        store.update_job_state(job.id, status="needs_attention", terminal_reason="dry-run job; auto agent not executed")
        store.add_event(job.id, "warn", "dry-run job; auto agent not executed", {"attempt": attempt})
        return 0

    run_dir = db_path.parent / "ci_autofix_runs" / f"job_{job.id}_attempt_{attempt}"
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = run_dir / "prompt.txt"
    log_path = run_dir / "agent.log"

    try:
        workspace = _prepare_workspace(repo_root, run_dir / "worktree", job.branch)
        prompt_path.write_text(_build_prompt(job, attempt) + _failure_context(store, job), encoding="utf-8")
        cmd = _command_for_job(job, workspace, prompt_path)
    except Exception as exc:
        store.add_event(job.id, "error", "failed to build agent command", {"error": f"{type(exc).__name__}: {exc}"})
        store.update_job_state(job.id, status="needs_attention", automation_enabled=False, terminal_reason=str(exc))
        return 2

    store.add_event(
        job.id,
        "info",
        "LLM agent command started",
        {
            "attempt": attempt,
            "provider": job.llm_provider,
            "model": job.llm_model,
            "log_path": str(log_path),
            "cwd": str(workspace),
        },
    )

    before_commit = _git_head(workspace)
    env = os.environ.copy()
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log_file, prompt_path.open("rb") as prompt_input:
            proc = subprocess.Popen(
                cmd, cwd=str(workspace), env=env, stdout=log_file,
                stdin=prompt_input, stderr=subprocess.STDOUT, text=True,
                start_new_session=os.name != "nt",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            store.add_event(job.id, "info", "repair agent process started",
                            {"attempt": attempt, "pid": proc.pid, "workspace": str(workspace), "before_commit": before_commit})
            code, last_commit, reason = _run_one_cycle(
                proc, workspace, job.branch, before_commit, max(60, args.agent_timeout_seconds),
            )
    except Exception as exc:
        code, last_commit, reason = 2, "", f"修正エージェントの実行に失敗しました: {exc}"

    if last_commit:
        store.update_job_state(job.id, status="waiting_ci", last_commit=last_commit, terminal_reason="")
        store.add_event(
            job.id,
            "info",
            "LLM agent attempt finished; waiting for next CI result",
            {"attempt": attempt, "exit_code": code, "last_commit": last_commit, "log_path": str(log_path)},
        )
        return 0

    report_path = prompt_path.with_name("final.txt")
    report = report_path.read_text(encoding="utf-8").strip()[:1200] if report_path.exists() else ""
    if report:
        reason = f"{reason}\nエージェントの報告: {report}"
    store.update_job_state(
        job.id,
        status="needs_attention", automation_enabled=False,
        terminal_reason=reason or f"agent exited with code {code}",
    )
    store.add_event(
        job.id,
        "error",
        "LLM agent attempt failed",
        {"attempt": attempt, "exit_code": code, "last_commit": last_commit, "log_path": str(log_path), "agent_report": report},
    )
    return int(code or 1)


if __name__ == "__main__":
    raise SystemExit(main())
