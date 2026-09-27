# Engineer Specialty Guidelines

## Coding Principles

- **Minimal change**: Keep changes to existing code to the minimum. Large refactors only when explicitly instructed. Out-of-scope fixes go to separate tasks
- **YAGNI**: Do not complicate code for hypothetical future needs. Abstract only after 3 occurrences (Rule of Three)
- **Security**: Always validate input, use parameter binding for SQL, never hardcode secrets, use `pathlib.Path` to prevent path traversal, avoid `shell=True`

## Code Quality

- `from __future__ import annotations` + `str | None` type hints required
- `pathlib.Path` for paths, Google-style docstrings, `logging.getLogger(__name__)`
- Pydantic Model / dataclass for data structures
- Semantic commits: `feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:`

## Testing and Error Handling

- Verify related tests after changes. Add unit tests for new functions
- Catch specific exceptions (no bare `except:`). Use exponential backoff for retries
- `async/await` + `asyncio.Lock()`. CPU-bound work via `asyncio.to_thread()`

For project-specific conventions, refer to `.cursorrules` / `CLAUDE.md` in the repository
