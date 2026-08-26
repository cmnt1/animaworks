"""Unit tests for emotion extraction in server/routes/chat.py."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json

import pytest

from server.routes.chat import extract_emotion, _handle_chunk


# ── extract_emotion ──────────────────────────────────────


class TestExtractEmotion:
    """Tests for the extract_emotion() function."""

    def test_extracts_valid_emotion(self):
        text = 'Hello!\n<!-- emotion: {"emotion": "smile"} -->'
        clean, emotion = extract_emotion(text)
        assert clean == "Hello!"
        assert emotion == "smile"

    def test_extracts_laugh(self):
        text = 'Ha ha that is funny!\n<!-- emotion: {"emotion": "laugh"} -->'
        clean, emotion = extract_emotion(text)
        assert clean == "Ha ha that is funny!"
        assert emotion == "laugh"

    def test_extracts_troubled(self):
        text = 'I am not sure...\n<!-- emotion: {"emotion": "troubled"} -->'
        clean, emotion = extract_emotion(text)
        assert clean == "I am not sure..."
        assert emotion == "troubled"

    def test_extracts_surprised(self):
        text = 'Oh really?!\n<!-- emotion: {"emotion": "surprised"} -->'
        clean, emotion = extract_emotion(text)
        assert clean == "Oh really?!"
        assert emotion == "surprised"

    def test_extracts_thinking(self):
        text = 'Let me consider...\n<!-- emotion: {"emotion": "thinking"} -->'
        clean, emotion = extract_emotion(text)
        assert clean == "Let me consider..."
        assert emotion == "thinking"

    def test_extracts_embarrassed(self):
        text = 'Oh, um...\n<!-- emotion: {"emotion": "embarrassed"} -->'
        clean, emotion = extract_emotion(text)
        assert clean == "Oh, um..."
        assert emotion == "embarrassed"

    def test_neutral_explicit(self):
        text = 'OK.\n<!-- emotion: {"emotion": "neutral"} -->'
        clean, emotion = extract_emotion(text)
        assert clean == "OK."
        assert emotion == "neutral"

    def test_no_metadata_returns_neutral(self):
        text = "Hello, how are you?"
        clean, emotion = extract_emotion(text)
        assert clean == "Hello, how are you?"
        assert emotion == "neutral"

    def test_empty_string(self):
        clean, emotion = extract_emotion("")
        assert clean == ""
        assert emotion == "neutral"

    def test_invalid_emotion_falls_back_to_neutral(self):
        text = 'Hello\n<!-- emotion: {"emotion": "angry"} -->'
        clean, emotion = extract_emotion(text)
        assert clean == "Hello"
        assert emotion == "neutral"

    def test_malformed_json_falls_back_to_neutral(self):
        text = "Hello\n<!-- emotion: {broken json} -->"
        clean, emotion = extract_emotion(text)
        assert clean == "Hello"
        assert emotion == "neutral"

    def test_missing_emotion_key_falls_back_to_neutral(self):
        text = 'Hello\n<!-- emotion: {"mood": "happy"} -->'
        clean, emotion = extract_emotion(text)
        assert clean == "Hello"
        assert emotion == "neutral"

    def test_metadata_in_middle_of_text(self):
        text = 'Before\n<!-- emotion: {"emotion": "smile"} -->\nAfter'
        clean, emotion = extract_emotion(text)
        assert "Before" in clean
        assert "After" in clean
        assert "emotion" not in clean
        assert emotion == "smile"

    def test_whitespace_around_tag(self):
        text = 'Hello\n<!--  emotion:  {"emotion": "smile"}  -->'
        clean, emotion = extract_emotion(text)
        assert clean == "Hello"
        assert emotion == "smile"

    def test_multiline_response_with_metadata(self):
        text = "Line 1\nLine 2\nLine 3\n<!-- emotion: {\"emotion\": \"laugh\"} -->"
        clean, emotion = extract_emotion(text)
        assert clean == "Line 1\nLine 2\nLine 3"
        assert emotion == "laugh"

    @pytest.mark.parametrize("emotion_name", [
        "neutral", "smile", "laugh", "troubled",
        "surprised", "thinking", "embarrassed",
    ])
    def test_all_valid_emotions(self, emotion_name):
        text = f'Test\n<!-- emotion: {{"emotion": "{emotion_name}"}} -->'
        clean, emotion = extract_emotion(text)
        assert emotion == emotion_name

    @pytest.mark.parametrize("invalid", [
        "happy", "angry", "sad", "normal", "working", "idle",
    ])
    def test_invalid_emotions_rejected(self, invalid):
        text = f'Test\n<!-- emotion: {{"emotion": "{invalid}"}} -->'
        clean, emotion = extract_emotion(text)
        assert emotion == "neutral"


# ── _handle_chunk with emotion ───────────────────────────


class TestHandleChunkEmotion:
    """Tests that _handle_chunk injects emotion into done events."""

    def test_cycle_done_extracts_emotion(self):
        chunk = {
            "type": "cycle_done",
            "cycle_result": {
                "summary": 'Hello!\n<!-- emotion: {"emotion": "smile"} -->',
            },
        }
        frame, response_text = _handle_chunk(chunk)
        assert frame is not None
        # Parse the SSE frame to check emotion field
        data_line = frame.split("data: ", 1)[1].split("\n")[0]
        data = json.loads(data_line)
        assert data["emotion"] == "smile"
        assert "<!-- emotion" not in data["summary"]
        assert response_text == "Hello!"

    def test_cycle_done_no_emotion(self):
        chunk = {
            "type": "cycle_done",
            "cycle_result": {"summary": "Simple response"},
        }
        frame, response_text = _handle_chunk(chunk)
        data_line = frame.split("data: ", 1)[1].split("\n")[0]
        data = json.loads(data_line)
        assert data["emotion"] == "neutral"
        assert response_text == "Simple response"

    def test_text_delta_unchanged(self):
        chunk = {"type": "text_delta", "text": "Hello"}
        frame, response_text = _handle_chunk(chunk)
        assert frame is not None
        assert "text_delta" in frame
        assert response_text == ""

    def test_tool_events_unchanged(self):
        chunk = {"type": "tool_start", "tool_name": "web", "tool_id": "t1"}
        frame, _ = _handle_chunk(chunk)
        assert "tool_start" in frame


# ── 3-route unification (expected same result across all paths) ────


class TestEmotionParsingUnified:
    """The shared parser must be used by all three former implementations so that
    the missing-close-tag, newline-JSON and normal cases agree across the
    chat-, messaging- and voice-paths."""

    def _all_emotions(self, text: str) -> list[str]:
        from core._anima_messaging import _extract_emotion_from_tag
        from core.voice.front import extract_emotion as voice_extract

        chat_emotion = extract_emotion(text)[1]  # server chat route
        msg_emotion = _extract_emotion_from_tag(text)[1]  # messaging route
        voice_emotion = voice_extract(text)  # voice front route
        return [chat_emotion, msg_emotion, voice_emotion]

    def test_normal_case_consistent(self):
        vals = self._all_emotions('Hey!\n<!-- emotion: {"emotion": "smile"} -->')
        assert vals == ["smile", "smile", "smile"]

    def test_missing_close_tag_consistent(self):
        # No closing '-->' — chat previously failed, voice previously matched.
        vals = self._all_emotions('Hey!\n<!-- emotion: {"emotion": "laugh"}')
        assert vals == ["laugh", "laugh", "laugh"]

    def test_newline_json_consistent(self):
        vals = self._all_emotions(
            "Hey!\n<!-- emotion: {\n  \"emotion\": \"surprised\"\n} -->"
        )
        assert vals == ["surprised", "surprised", "surprised"]

    def test_clean_text_consistent_across_full_parsers(self):
        from core._anima_messaging import _extract_emotion_from_tag

        text = "Body\n<!-- emotion: { \"emotion\": \"thinking\" } -->"
        chat_clean, chat_emo = extract_emotion(text)
        msg_clean, msg_emo = _extract_emotion_from_tag(text)
        assert chat_clean == msg_clean == "Body"
        assert chat_emo == msg_emo == "thinking"
