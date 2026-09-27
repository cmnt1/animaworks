# Engineering-Specific Guidelines

## Coding Principles

- **Minimal Changes**: Keep changes to existing code to the minimum necessary. Large-scale refactoring only when explicitly instructed. Out-of-scope fixes should be recorded as separate tasks.
- **YAGNI**: Do not complicate code by anticipating future extensions. Abstract only after the same pattern appears three times (Rule of Three).
- **Security**: Input validation is mandatory, use parameter binding for SQL, never hardcode secrets, use `pathlib.Path` to prevent path traversal, and avoid `shell=True`.

## Code Quality

- Type hints in the `from __future__ import annotations` + `str | None` format are mandatory.
- Use `pathlib.Path` for path operations, Google-style docstrings, and `logging.getLogger(__name__)`.
- Define data using Pydantic Model / dataclass.
- Semantic commits: `feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:`.

## Testing and Error Handling

- After code changes, verify related tests. Add unit tests for new functions.
- Catch specific exceptions (bare `except:` is prohibited). Use exponential backoff for retries.
- Use `async/await` + `asyncio.Lock()`. For CPU-bound tasks, use `asyncio.to_thread()`.

Refer to the repository's `.cursorrules` / `CLAUDE.md` for project-specific conventions.