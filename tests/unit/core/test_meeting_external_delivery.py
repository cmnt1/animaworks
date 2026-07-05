from __future__ import annotations

from types import SimpleNamespace

from core._anima_messaging import MessagingMixin


class _DummyMessaging(MessagingMixin):
    name = "kanna"


def test_meeting_source_does_not_resolve_external_delivery(monkeypatch, tmp_path):
    dummy = _DummyMessaging()
    resolved = SimpleNamespace(is_internal=False, channel="discord")

    monkeypatch.setattr(
        "core.config.models.load_config",
        lambda: SimpleNamespace(external_messaging={}),
    )
    monkeypatch.setattr("core.paths.get_animas_dir", lambda: tmp_path)
    monkeypatch.setattr("core.outbound.resolve_recipient", lambda *args, **kwargs: resolved)

    assert dummy._resolve_chat_external_recipient("cmnt", source="meeting") is None


def test_external_platform_source_does_not_re_resolve_delivery():
    dummy = _DummyMessaging()

    assert dummy._resolve_chat_external_recipient("cmnt", source="discord") is None
