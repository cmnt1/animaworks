from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""GitHub source adapter for Skill Hub imports."""

import base64
import json
import shutil
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError

from core.skills.guard import MAX_FILES_PER_SKILL, MAX_SKILL_DIR_SIZE, MAX_SKILL_FILE_SIZE
from core.skills.sources.url import stage_url_source


def stage_github_source(source: str, staging_root: Path) -> tuple[Path, str | None]:
    """Stage ``github:owner/repo/path`` and return ``(skill_dir, commit)``."""
    owner, repo, repo_path = _parse_github_source(source)
    if shutil.which("gh"):
        return _stage_with_gh_api(owner, repo, repo_path, staging_root), _default_commit(owner, repo)

    if not repo_path.endswith("SKILL.md"):
        raise RuntimeError("gh CLI is required for GitHub directory bundle imports")
    candidates = _raw_url_candidates(owner, repo, repo_path)
    errors: list[str] = []
    for url in candidates:
        try:
            staged = stage_url_source(url, staging_root / "from-raw")
            return _rename_staged(staged, _stage_name(repo_path)), None
        except (HTTPError, URLError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("GitHub source could not be fetched without gh CLI: " + "; ".join(errors))


def _parse_github_source(source: str) -> tuple[str, str, str]:
    raw = source.removeprefix("github:").strip("/")
    parts = raw.split("/", 2)
    if len(parts) < 3 or not all(parts):
        raise ValueError("GitHub sources must use github:owner/repo/path/to/skill")
    owner, repo, repo_path = parts
    if ".." in Path(repo_path).parts or Path(repo_path).is_absolute():
        raise ValueError("GitHub source path must be relative and must not contain '..'")
    return owner, repo, repo_path


def _raw_url_candidates(owner: str, repo: str, repo_path: str) -> list[str]:
    suffix = repo_path if repo_path.endswith("SKILL.md") else f"{repo_path.rstrip('/')}/SKILL.md"
    return [
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/{suffix}",
        f"https://raw.githubusercontent.com/{owner}/{repo}/master/{suffix}",
    ]


def _stage_with_gh_api(owner: str, repo: str, repo_path: str, staging_root: Path) -> Path:
    root = staging_root / _stage_name(repo_path)
    entries = _collect_files(owner, repo, repo_path)
    root.mkdir(parents=True, exist_ok=False)
    for item in entries:
        rel = _relative_repo_path(item["path"], repo_path)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_fetch_file_bytes(owner, repo, item["path"], int(item.get("size") or 0)))
    if not (root / "SKILL.md").is_file():
        raise FileNotFoundError("GitHub skill bundle must contain SKILL.md at the requested path")
    return root


def _collect_files(owner: str, repo: str, repo_path: str) -> list[dict]:
    stack = [repo_path]
    files: list[dict] = []
    total_size = 0
    entries_seen = 0
    while stack:
        data = _gh_api(f"repos/{owner}/{repo}/contents/{stack.pop(0)}")
        entries = data if isinstance(data, list) else [data]
        entries_seen += len(entries)
        if entries_seen > MAX_FILES_PER_SKILL * 2:
            raise ValueError(f"GitHub skill bundle entry count exceeds limit ({MAX_FILES_PER_SKILL * 2})")
        for item in entries:
            item_type = item.get("type")
            if item_type == "dir":
                stack.append(item["path"])
                continue
            if item_type != "file":
                raise ValueError(f"Unsupported GitHub skill bundle entry type: {item_type}")
            size = int(item.get("size") or 0)
            if size > MAX_SKILL_FILE_SIZE:
                raise ValueError(f"GitHub skill bundle file exceeds limit ({MAX_SKILL_FILE_SIZE}): {item['path']}")
            total_size += size
            if total_size > MAX_SKILL_DIR_SIZE:
                raise ValueError(f"GitHub skill bundle total size exceeds limit ({MAX_SKILL_DIR_SIZE})")
            files.append(item)
            if len(files) > MAX_FILES_PER_SKILL:
                raise ValueError(f"GitHub skill bundle file count exceeds limit ({MAX_FILES_PER_SKILL})")
    return files


def _fetch_file_bytes(owner: str, repo: str, path: str, expected_size: int) -> bytes:
    data = _gh_api(f"repos/{owner}/{repo}/contents/{path}")
    content = str(data.get("content") or "")
    raw = base64.b64decode(content, validate=False)
    if len(raw) > MAX_SKILL_FILE_SIZE or len(raw) > expected_size:
        raise ValueError(f"GitHub skill bundle file exceeds declared size: {path}")
    return raw


def _gh_api(endpoint: str):
    result = subprocess.run(
        ["gh", "api", endpoint],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _default_commit(owner: str, repo: str) -> str | None:
    try:
        repo_info = _gh_api(f"repos/{owner}/{repo}")
        branch = repo_info.get("default_branch")
        commit = _gh_api(f"repos/{owner}/{repo}/commits/{branch}") if branch else {}
        return commit.get("sha")
    except (subprocess.CalledProcessError, json.JSONDecodeError, TypeError):
        return None


def _relative_repo_path(path: str, repo_path: str) -> Path:
    if repo_path.endswith("SKILL.md"):
        return Path("SKILL.md")
    rel = Path(path).relative_to(repo_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Unsafe GitHub skill bundle path: {path}")
    return rel


def _stage_name(repo_path: str) -> str:
    path = Path(repo_path)
    if path.name == "SKILL.md":
        return path.parent.name or "skill"
    return path.name or "skill"


def _rename_staged(staged: Path, name: str) -> Path:
    target = staged.parent / name
    if target == staged:
        return staged
    shutil.move(str(staged), str(target))
    return target
