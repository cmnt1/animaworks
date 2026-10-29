"""Tests for LoCoMo benchmark answer prompt improvements (Issue #174)."""

from __future__ import annotations


class TestAnswerPromptConstants:
    """Verify answer prompt templates contain required elements."""

    def test_answer_prompt_has_system(self) -> None:
        from benchmarks.locomo.answer_prompt import ANSWER_SYSTEM

        assert "expert assistant" in ANSWER_SYSTEM
        assert "past conversations" in ANSWER_SYSTEM

    def test_answer_prompt_has_template(self) -> None:
        from benchmarks.locomo.answer_prompt import ANSWER_TEMPLATE

        assert "{context}" in ANSWER_TEMPLATE
        assert "{question}" in ANSWER_TEMPLATE
        assert "event_time" in ANSWER_TEMPLATE
        assert "7 May 2023" in ANSWER_TEMPLATE

    def test_legacy_adapter_has_answer_system(self) -> None:
        from benchmarks.locomo.answer_prompt import ANSWER_SYSTEM

        assert "expert assistant" in ANSWER_SYSTEM

    def test_legacy_adapter_has_answer_template(self) -> None:
        from benchmarks.locomo.answer_prompt import ANSWER_TEMPLATE

        assert "{context}" in ANSWER_TEMPLATE
        assert "{question}" in ANSWER_TEMPLATE
        assert "event_time" in ANSWER_TEMPLATE

    def test_templates_are_consistent(self) -> None:
        from benchmarks.locomo.answer_prompt import ANSWER_TEMPLATE

        assert "never abstain when context exists" not in ANSWER_TEMPLATE
        assert "No information available." in ANSWER_TEMPLATE

    def test_template_format_works(self) -> None:
        from benchmarks.locomo.answer_prompt import build_answer_user_content

        result = build_answer_user_content(
            "When did I go to the vet?",
            "[1] (event_time: 2023-05-08T13:56:00) Went to the vet",
            category=2,
        )
        assert "When did I go to the vet?" in result
        assert "event_time: 2023-05-08T13:56:00" in result


class TestRunnerDefaults:
    """Verify runner CLI default values."""

    def test_runner_default_top_k(self) -> None:
        from benchmarks.locomo.runner import _build_arg_parser

        parser = _build_arg_parser()
        args = parser.parse_args([])
        assert args.top_k == 10

    def test_runner_exclude_cat5_default_off(self) -> None:
        from benchmarks.locomo.runner import _build_arg_parser

        parser = _build_arg_parser()
        args = parser.parse_args([])
        assert args.exclude_cat5 is False

    def test_runner_exclude_cat5_flag(self) -> None:
        from benchmarks.locomo.runner import _build_arg_parser

        parser = _build_arg_parser()
        args = parser.parse_args(["--exclude-cat5"])
        assert args.exclude_cat5 is True
