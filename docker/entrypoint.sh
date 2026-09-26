#!/usr/bin/env bash
# AnimaWorks container entrypoint.
set -euo pipefail
# git identity for commits made by animas (override via env)
git config --global user.name  "${GIT_AUTHOR_NAME:-animaworks}"  >/dev/null 2>&1 || true
git config --global user.email "${GIT_AUTHOR_EMAIL:-animaworks@localhost}" >/dev/null 2>&1 || true
git config --global init.defaultBranch main >/dev/null 2>&1 || true
# Plain git does not use gh's token; wire the credential helper when a token is present.
if [ -n "${GH_TOKEN:-}" ] && command -v gh >/dev/null 2>&1; then
  gh auth setup-git >/dev/null 2>&1 || echo "[entrypoint] warning: gh auth setup-git failed" >&2
fi
exec python /app/main.py "$@"
