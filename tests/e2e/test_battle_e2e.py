"""Real browser tests of battle rendering and Pixel's WebSocket transport.

APIs and WS frames use production payload shapes, with no real runtime access.
Run: uv run pytest tests/e2e/test_battle_e2e.py
"""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[2] / "server" / "static"


@pytest.fixture(scope="module")
def battle_server():
    app = FastAPI()

    @app.get("/battle")
    @app.get("/battle/")
    def index():
        return HTMLResponse(
            (ROOT / "battle/index.html").read_text().replace("__AW_BASE__", "").replace("__AW_VERSION__", "test")
        )

    app.mount("/_v/test", StaticFiles(directory=ROOT))
    app.mount("/", StaticFiles(directory=ROOT))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    sock.close()


@pytest.fixture
def page():
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.route("**/api/system/config", lambda route: route.fulfill(json={"locale": "ja"}))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
        browser.close()
        assert not errors


def test_demo_animation_pause_mobile_and_next_wave(page, battle_server, tmp_path):
    sockets = []
    page.route_web_socket("**/ws", lambda ws: sockets.append(ws))
    page.goto(battle_server + "/battle?demo=1")
    page.wait_for_function("document.querySelectorAll('.party-row').length === 4")
    page.wait_for_function("document.querySelector('#phaseLabel').textContent.includes('01')")
    assert page.locator(".command.selected").inner_text() == "しらべる"
    page.wait_for_function("document.querySelector('#phaseLabel').textContent.includes('02')")
    assert page.locator(".target-row.selected").count() == 1
    page.wait_for_function("document.querySelector('#phaseLabel').textContent.includes('03')")
    page.wait_for_function("document.querySelector('#phaseLabel').textContent.includes('04')")
    page.wait_for_function("document.querySelector('#phaseLabel').textContent.includes('05')")
    page.screenshot(path=str(tmp_path / "battle-impact.png"), full_page=True)
    assert "Mira" in page.locator("#journal").inner_text()
    page.locator("#pause").click()
    text = page.locator("#message").inner_text()
    pixels = page.locator("#battle").evaluate("(el) => el.toDataURL()")
    page.wait_for_timeout(350)
    assert page.locator("#message").inner_text() == text
    assert page.locator("#battle").evaluate("(el) => el.toDataURL()") == pixels
    for width in [390, 768]:
        page.set_viewport_size({"width": width, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(tmp_path / f"battle-{width}.png"), full_page=True)
    page.locator("#speed").select_option("4")
    page.locator("#pause").click()
    page.wait_for_function("document.querySelector('#clearCount').textContent === '3'", timeout=20000)
    page.wait_for_function("document.querySelector('#activeCount').textContent === '3'", timeout=10000)
    assert not sockets, "Demo must not subscribe to live activity"
    assert page.locator("#modeSwitch").get_attribute("href") == "/battle"


def test_live_tasks_tools_failure_completion_and_reconnect(page, battle_server):
    tasks = [
        {
            "anima_name": "a",
            "assignee": "a",
            "task_id": "build",
            "summary": "本物のタスク",
            "queue_status": "in_progress",
            "visibility": "active",
        }
    ]
    page.route(
        "**/api/animas",
        lambda route: route.fulfill(json=[{"name": n, "status": "idle"} for n in ["a", "b", "c", "d", "e"]]),
    )
    page.route("**/api/task-board", lambda route: route.fulfill(json={"tasks": tasks}))
    page.route("**/assets/battle_sheet_v1.png", lambda route: route.fulfill(status=404))
    sockets, received = [], []

    def connected(ws):
        sockets.append(ws)
        ws.on_message(lambda message: received.append(json.loads(message)))
        ws.send(json.dumps({"type": "ping"}))

    page.route_web_socket("**/ws", connected)
    page.goto(battle_server + "/battle/")
    page.wait_for_function("document.querySelector('#connection').dataset.state === 'online'")
    page.wait_for_function("document.querySelector('#activeCount').textContent === '1'")
    assert {"type": "pong"} in received
    assert page.locator("#modeSwitch").get_attribute("href") == "/battle?demo=1"
    page.locator("#partyPage").click()
    assert page.locator(".party-name").inner_text() == "e"
    page.locator("#speed").select_option("4")

    def send(kind, data):
        sockets[-1].send(json.dumps({"type": kind, "data": data}))

    send(
        "anima.tool_activity",
        {"name": "a", "type": "tool_result", "tool": "Read", "ctx": "task:build", "meta": {"tool_use_id": "read-1"}},
    )
    page.wait_for_function("document.querySelectorAll('#journal li[data-source=activity]').length === 1")
    assert page.locator("#journal li[data-source=activity]").first.get_attribute("data-skill") in [
        "flare",
        "frost",
        "thunder",
        "meteor",
    ]
    assert page.locator("#partyPage").inner_text() == "1/2 ›"
    send(
        "anima.tool_activity",
        {"name": "a", "event": "tool_end", "tool_name": "Bash", "tool_id": "bash-1", "is_error": True},
    )
    page.wait_for_function("document.querySelectorAll('#journal li[data-source=activity]').length === 2")
    assert "失敗" in page.locator("#journal li[data-source=activity]").first.inner_text()
    send("anima.status", {"name": "a", "status": "idle"})
    page.wait_for_timeout(500)
    assert page.locator("#clearCount").inner_text() == "0"
    tasks[0]["queue_status"] = "done"
    send("anima.tool_activity", {"name": "a", "type": "task_updated", "meta": {"task_id": "build", "status": "done"}})
    page.wait_for_function("document.querySelector('#clearCount').textContent === '1'")
    page.wait_for_function("document.querySelector('#activeCount').textContent === '0'")
    assert "タスク完了" in page.locator("#journal").inner_text()
    sockets[-1].close(code=1012, reason="test reconnect")
    page.wait_for_function("document.querySelector('#connection').dataset.state === 'offline'")
    assert "ライブ" in page.locator("#modeLabel").inner_text() or "LIVE" in page.locator("#modeLabel").inner_text()
    page.wait_for_function("document.querySelector('#connection').dataset.state === 'online'", timeout=7000)
    assert len(sockets) >= 2
    assert page.locator("#clearCount").inner_text() == "1"


def test_auth_failure_is_not_demo_and_text_is_safe(page, battle_server):
    page.route("**/api/animas", lambda route: route.fulfill(status=401, json={"error": "unauthorized"}))
    page.route("**/api/task-board", lambda route: route.fulfill(status=401, json={"error": "unauthorized"}))
    # Keep the socket available: API authorization errors must still be shown.
    # Closing inside Playwright's route callback can deadlock its sync bridge.
    page.route_web_socket("**/ws", lambda ws: None)
    page.goto(battle_server + "/battle")
    page.wait_for_function("document.querySelector('#message').textContent.includes('ログイン')")
    assert page.locator(".party-row").count() == 0
    assert page.locator(".target-row").count() == 0
    assert page.locator("#clearCount").inner_text() == "0"


def test_base_path_live_transport_and_untrusted_titles(page, battle_server):
    html = (ROOT / "battle/index.html").read_text().replace("__AW_BASE__", "/office").replace("__AW_VERSION__", "test")
    page.route("**/office/battle", lambda route: route.fulfill(content_type="text/html", body=html))
    page.route(
        "**/office/_v/test/**",
        lambda route: route.continue_(url=route.request.url.replace("/office/_v/test/", "/_v/test/")),
    )
    page.route(
        "**/office/i18n/**", lambda route: route.continue_(url=route.request.url.replace("/office/i18n/", "/i18n/"))
    )
    title = "<img src=x onerror=window.injected=true>"
    page.route("**/office/api/animas", lambda route: route.fulfill(json=[{"name": "a", "status": "idle"}]))
    page.route(
        "**/office/api/task-board",
        lambda route: route.fulfill(
            json={
                "tasks": [
                    {
                        "anima_name": "a",
                        "task_id": "x",
                        "queue_status": "in_progress",
                        "visibility": "active",
                        "summary": title,
                    }
                ]
            }
        ),
    )
    page.route("**/assets/battle_sheet_v1.png", lambda route: route.fulfill(status=404))
    sockets = []
    page.route_web_socket("**/office/ws", lambda ws: sockets.append(ws))
    page.goto(battle_server + "/office/battle")
    page.wait_for_function("document.querySelectorAll('.target-row').length === 1")
    assert sockets
    assert page.locator(".target-name").inner_text() != title
    page.locator(".target-name").click()
    assert page.locator("#taskTitle").inner_text() == title
    assert page.locator("#taskDialog").is_visible()
    assert page.locator("#taskDialog img").count() == 0
    page.locator("#taskClose").click()
    assert page.locator("#targets img").count() == 0
    assert page.evaluate("window.injected") is None
    assert page.locator("#modeSwitch").get_attribute("href") == "/office/battle?demo=1"


def test_enemies_act_without_events_and_repeated_tools_vary(page, battle_server):
    page.route("**/api/animas", lambda route: route.fulfill(json=[{"name": "hero", "status": "idle"}]))
    page.route(
        "**/api/task-board",
        lambda route: route.fulfill(
            json={
                "tasks": [
                    {
                        "anima_name": "hero",
                        "task_id": "job",
                        "summary": "/work/tests/test_job.py",
                        "assignee": "hero",
                        "queue_status": "in_progress",
                        "visibility": "active",
                    }
                ]
            }
        ),
    )
    page.route("**/assets/battle_sheet_v1.png", lambda route: route.fulfill(status=404))
    requests, sockets = [], []
    page.on("request", lambda request: requests.append(request))
    page.route_web_socket("**/ws", lambda ws: sockets.append(ws))
    page.goto(battle_server + "/battle")
    page.locator("#speed").select_option("4")
    page.wait_for_function("Number(document.querySelector('.party-row')?.dataset.hp) < 1200")
    assert "ダメージ" in page.locator("#journal li[data-side=enemy]").first.inner_text()
    page.wait_for_function(
        "[...document.querySelectorAll('#journal li[data-source=scene]')].some(el => el.textContent.includes('反撃'))"
    )
    assert page.locator("#clearCount").inner_text() == "0"
    assert page.locator("#activeCount").inner_text() == "1"
    assert ".py" not in page.locator(".target-name").inner_text()
    for index in range(3):
        sockets[-1].send(
            json.dumps(
                {
                    "type": "anima.tool_activity",
                    "data": {
                        "name": "hero",
                        "type": "tool_result",
                        "tool": "Read",
                        "ctx": "task:job",
                        "meta": {"tool_use_id": f"read-{index}"},
                    },
                }
            )
        )
    page.wait_for_function("document.querySelectorAll('#journal li[data-source=activity]').length === 3", timeout=20000)
    skills = page.locator("#journal li[data-source=activity]").evaluate_all("els => els.map(el => el.dataset.skill)")
    assert len(set(skills)) >= 2
    assert all(a != b for a, b in zip(skills, skills[1:], strict=False))
    assert not [r for r in requests if r.method not in {"GET", "HEAD"}]
    assert not [r for r in requests if r.url.endswith("pixel_sheet.png")]
