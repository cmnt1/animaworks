from __future__ import annotations

from unittest.mock import patch

from core.platform.env import (
    ANIMA_DIR_ENV,
    DATA_DIR_ENV,
    DEFAULT_SERVER_URL,
    SERVER_URL_ENV,
    anima_dir_env,
    data_dir_env,
    server_url,
    set_server_url,
)


def test_named_env_accessors_read_current_environment(monkeypatch) -> None:
    monkeypatch.setenv(ANIMA_DIR_ENV, "/runtime/animas/mei")
    monkeypatch.setenv(DATA_DIR_ENV, "/runtime/data")
    assert anima_dir_env() == "/runtime/animas/mei"
    assert data_dir_env() == "/runtime/data"

    monkeypatch.setenv(ANIMA_DIR_ENV, "/runtime/animas/renamed")
    monkeypatch.setenv(DATA_DIR_ENV, "/runtime/other-data")
    assert anima_dir_env() == "/runtime/animas/renamed"
    assert data_dir_env() == "/runtime/other-data"


def test_server_url_reads_env_each_time_and_normalizes(monkeypatch) -> None:
    monkeypatch.setenv(SERVER_URL_ENV, " https://server.example:18501/// ")
    assert server_url() == "https://server.example:18501"

    monkeypatch.setenv(SERVER_URL_ENV, "http://server.example:18502/")
    assert server_url() == "http://server.example:18502"


def test_server_url_falls_back_without_loading_config(monkeypatch) -> None:
    monkeypatch.delenv(SERVER_URL_ENV, raising=False)
    with patch("core.config.load_config") as load_config:
        assert server_url() == DEFAULT_SERVER_URL
    load_config.assert_not_called()


def test_server_url_can_preserve_an_empty_override(monkeypatch) -> None:
    monkeypatch.delenv(SERVER_URL_ENV, raising=False)
    with patch("core.config.load_config") as load_config:
        assert server_url(default="") == ""
    load_config.assert_not_called()


def test_set_server_url_normalizes_value(monkeypatch) -> None:
    monkeypatch.setenv(SERVER_URL_ENV, "http://original.example")
    set_server_url(" http://localhost:18601/// ")
    assert server_url() == "http://localhost:18601"
