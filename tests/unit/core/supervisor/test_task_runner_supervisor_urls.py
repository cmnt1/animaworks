"""Task runners require the complete root-owned RAG endpoint set."""

from __future__ import annotations

import pytest

from core.runtime.task_runner_supervisor import TaskRunnerError, TaskRunnerSupervisor

_URLS = {
    "ANIMAWORKS_EMBED_URL": "http://rag.test/api/internal/embed",
    "ANIMAWORKS_VECTOR_URL": "http://rag.test/api/internal/vector",
    "ANIMAWORKS_RERANK_URL": "http://rag.test/api/internal/rerank",
}


def _clear_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _URLS:
        monkeypatch.delenv(name, raising=False)


def test_required_url_environment_accepts_all_three(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_urls(monkeypatch)
    for name, value in _URLS.items():
        monkeypatch.setenv(name, value)

    values = TaskRunnerSupervisor._required_url_environment()

    assert {name: values[name] for name in _URLS} == _URLS


@pytest.mark.parametrize("missing", ["ANIMAWORKS_VECTOR_URL", "ANIMAWORKS_RERANK_URL"])
def test_required_url_environment_rejects_missing_non_embed_url(
    missing: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_urls(monkeypatch)
    for name, value in _URLS.items():
        if name != missing:
            monkeypatch.setenv(name, value)

    with pytest.raises(TaskRunnerError, match=missing):
        TaskRunnerSupervisor._required_url_environment()


def test_required_url_environment_keeps_missing_embed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_urls(monkeypatch)
    monkeypatch.setenv("ANIMAWORKS_VECTOR_URL", _URLS["ANIMAWORKS_VECTOR_URL"])
    monkeypatch.setenv("ANIMAWORKS_RERANK_URL", _URLS["ANIMAWORKS_RERANK_URL"])

    with pytest.raises(TaskRunnerError, match="ANIMAWORKS_EMBED_URL"):
        TaskRunnerSupervisor._required_url_environment()
