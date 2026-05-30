from __future__ import annotations

from core.task_granularity import assess_task_granularity, estimate_phase_count


def test_estimate_phase_count_detects_operational_chain() -> None:
    text = "Repair DB records -> sync -> deploy -> verify public URL -> report status"

    assert estimate_phase_count(text) >= 5


def test_medium_qwen_coder_rejects_broad_operational_task() -> None:
    decision = assess_task_granularity(
        model_name="qwen3-coder-30b",
        title="108501 image recovery",
        description="Repair DB records -> sync -> deploy -> verify public URL -> report status",
    )

    assert decision.allowed is False
    assert decision.capability == "medium"
    assert decision.reason == "task_too_broad_for_model"
    assert "Split it into single-purpose tasks" in decision.guidance


def test_high_model_allows_broad_operational_task() -> None:
    decision = assess_task_granularity(
        model_name="openai/gpt-5.4",
        title="108501 image recovery",
        description="Repair DB records -> sync -> deploy -> verify public URL -> report status",
    )

    assert decision.allowed is True


def test_allow_multistage_overrides_guardrail() -> None:
    decision = assess_task_granularity(
        model_name="qwen3-coder-30b",
        description="Repair DB records -> sync -> deploy -> verify public URL -> report status",
        allow_multistage=True,
    )

    assert decision.allowed is True
