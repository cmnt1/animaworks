from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
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
5. Push to origin {job.branch}.
6. If a new CI run starts, monitor it when practical and continue fixing until it passes or the cause is genuinely blocked.

Operational rules:
- Use rtk for shell commands.
- Work on branch {job.branch}; do not create a feature branch unless unavoidable.
- Do not revert unrelated user changes.
- Keep commits scoped.
- If the same failure repeats, use the new failure logs and continue the same incident rather than starting over.
- Final output should summarize commit SHA, pushed branch, and CI run status.
"""


def _command_for_job(job, repo_root: Path, prompt_path: Path) -> list[str]:
    provider = str(job.llm_provider or "").strip()
    model = _strip_model_prefix(provider, str(job.llm_model or "").strip())
    prompt_arg = prompt_path.read_text(encoding="utf-8")

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
        cmd.append(prompt_arg)
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
    cmd.append(prompt_arg)
    return cmd


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one CI autofix LLM attempt and record events.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--job-id", required=True, type=int)
    parser.add_argument("--repo-root", default=str(_repo_root()))
    args = parser.parse_args()

    db_path = Path(args.db)
    repo_root = Path(args.repo_root).resolve()
    store = _load_store(db_path)
    job = store.begin_attempt(args.job_id)
    attempt = job.attempt_count
    if job.dry_run:
        store.update_job_state(job.id, status="needs_attention", terminal_reason="dry-run job; auto agent not executed")
        store.add_event(job.id, "warn", "dry-run job; auto agent not executed", {"attempt": attempt})
        return 0

    run_dir = db_path.parent / "ci_autofix_runs" / f"job_{job.id}_attempt_{attempt}"
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = run_dir / "prompt.txt"
    log_path = run_dir / "agent.log"
    prompt_path.write_text(_build_prompt(job, attempt), encoding="utf-8")

    try:
        cmd = _command_for_job(job, repo_root, prompt_path)
    except Exception as exc:
        store.add_event(job.id, "error", "failed to build agent command", {"error": f"{type(exc).__name__}: {exc}"})
        store.update_job_state(job.id, status="needs_attention", terminal_reason=str(exc))
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
            "cwd": str(repo_root),
        },
    )

    env = os.environ.copy()
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        code = proc.wait()

    last_commit = _git_head(repo_root)
    if code == 0:
        store.update_job_state(job.id, status="waiting_ci", last_commit=last_commit, terminal_reason="")
        store.add_event(
            job.id,
            "info",
            "LLM agent attempt finished; waiting for next CI result",
            {"attempt": attempt, "exit_code": code, "last_commit": last_commit, "log_path": str(log_path)},
        )
        return 0

    status = "exhausted" if attempt >= job.max_attempts else "needs_attention"
    store.update_job_state(
        job.id,
        status=status,
        last_commit=last_commit,
        terminal_reason=f"agent exited with code {code}",
    )
    store.add_event(
        job.id,
        "error",
        "LLM agent attempt failed",
        {"attempt": attempt, "exit_code": code, "last_commit": last_commit, "log_path": str(log_path)},
    )
    return int(code or 1)


if __name__ == "__main__":
    raise SystemExit(main())
