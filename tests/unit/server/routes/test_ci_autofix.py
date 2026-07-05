from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routes.ci_autofix import create_ci_autofix_api_router, create_ci_autofix_page_router
from swe.ci_autofix_intake import CIAutofixIntakeStore


def _client(tmp_path) -> TestClient:
    app = FastAPI()
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    app.include_router(create_ci_autofix_api_router(lambda: store), prefix="/api")
    app.include_router(create_ci_autofix_page_router())
    return TestClient(app)


def test_ci_autofix_page_renders(tmp_path) -> None:
    client = _client(tmp_path)

    res = client.get("/runner/ci-autofix")

    assert res.status_code == 200
    assert "CI Autofix Intake" in res.text


def test_create_candidate_and_list_events(tmp_path) -> None:
    client = _client(tmp_path)

    created = client.post(
        "/api/ci-autofix/jobs/candidate",
        json={"run_id": "123", "llm_provider": "codex", "llm_model": "codex/gpt-5.5"},
    ).json()
    jobs = client.get("/api/ci-autofix/jobs").json()
    summary = client.get("/api/ci-autofix/summary").json()
    events = client.get(f"/api/ci-autofix/jobs/{created['job']['id']}/events").json()

    assert created["ok"] is True
    assert jobs["jobs"][0]["run_id"] == "123"
    assert jobs["jobs"][0]["llm_provider"] == "codex"
    assert jobs["jobs"][0]["llm_model"] == "codex/gpt-5.5"
    assert summary["active_count"] == 1
    assert [event["message"] for event in events["events"]] == [
        "candidate created",
        "manual candidate registered",
    ]


def test_missing_job_returns_404(tmp_path) -> None:
    client = _client(tmp_path)

    res = client.get("/api/ci-autofix/jobs/999/events")

    assert res.status_code == 404
