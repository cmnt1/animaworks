#!/usr/bin/env bash

# Claude Code Stop hook: append the final session context to a librarian archive.
# Every failure is intentionally fail-open so the hook never blocks session exit.

project=${1:-}
case "$project" in
  ''|*[!A-Za-z0-9_-]*) exit 0 ;;
esac

input=$(command cat 2>/dev/null) || input=
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

transcript_path=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null) || exit 0
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null) || exit 0
if [ -z "$cwd" ]; then
  cwd=$(pwd 2>/dev/null) || cwd=
fi

branch="unavailable"
commits="(none)"
if command -v git >/dev/null 2>&1 && [ -d "$cwd" ]; then
  branch=$(git -C "$cwd" branch --show-current 2>/dev/null) || branch="unavailable"
  [ -n "$branch" ] || branch="detached HEAD"
  found_commits=$(git -C "$cwd" log --oneline --since="2 hours ago" -n 20 2>/dev/null) || found_commits=
  [ -z "$found_commits" ] || commits=$found_commits
fi

assistant_text=""
if [ -f "$transcript_path" ]; then
  assistant_text=$(jq -rs '
    [.[]
      | select(.type == "assistant" or .role == "assistant" or .message?.role? == "assistant")
      | (.message?.content? // .content // "")
      | if type == "array" then [.[] | select(.type == "text") | .text] | join("\n")
        elif type == "string" then . else "" end
      | select(length > 0)]
    | (last // "")[0:2000]
  ' "$transcript_path" 2>/dev/null) || assistant_text=""
fi
[ -n "$assistant_text" ] || assistant_text="(assistant text unavailable)"

data_dir=${ANIMAWORKS_DATA_DIR:-${HOME}/.animaworks}
archive_dir="$data_dir/animas/librarian/episodes/projects/$project"
mkdir -p "$archive_dir" 2>/dev/null || exit 0
archive_file="$archive_dir/$(date +%F)_sessions.md"
timestamp=$(date +%H:%M)
marker="<!-- librarian-transcript: $transcript_path -->"
if [ -n "$transcript_path" ] && [ -f "$archive_file" ] && command -v grep >/dev/null 2>&1; then
  grep -Fqx -- "$marker" "$archive_file" 2>/dev/null && exit 0
fi

{
  printf '%s\n' "$marker"
  printf '\n## %s セッション記録\n\n' "$timestamp"
  printf -- '- cwd: `%s`\n' "$cwd"
  printf -- '- git branch: `%s`\n\n' "$branch"
  printf '### Commits (last 2 hours)\n\n```text\n%s\n```\n\n' "$commits"
  printf '### Final assistant message\n\n%s\n' "$assistant_text"
} >>"$archive_file" 2>/dev/null || true

# Mark the librarian BM25 long-term index dirty so the next search rebuilds it.
state_dir="$data_dir/animas/librarian/state"
if [ -d "$state_dir" ]; then
  printf '{"dirty_at": "%s", "reason": "librarian_stop_hook"}\n' "$(date -u +%FT%TZ)" \
    >"$state_dir/bm25_longterm_index.dirty" 2>/dev/null || true
fi

exit 0
