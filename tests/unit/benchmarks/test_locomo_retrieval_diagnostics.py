from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import benchmarks.locomo.retrieval_diagnostics as retrieval_diagnostics
from benchmarks.locomo.retrieval_diagnostics import (
    _per_question_deltas,
    _temporary_entity_aware_graph,
    _temporary_entity_boost,
    _temporary_fact_index,
    _temporary_temporal_boost,
    answer_token_recall,
    parse_args,
    summarize_results,
    write_diagnostics_json,
)


class TestAnswerTokenRecall:
    def test_answer_token_recall_partial(self) -> None:
        recall, all_present = answer_token_recall(
            "Becoming Nicole",
            [{"content": "Caroline recommended Becoming to Melanie."}],
        )

        assert recall == 0.5
        assert all_present == 0.0

    def test_answer_token_recall_all_present(self) -> None:
        recall, all_present = answer_token_recall(
            "Becoming Nicole",
            [{"content": "The book was Becoming Nicole."}],
        )

        assert recall == 1.0
        assert all_present == 1.0

    def test_empty_answer_tokens_return_none(self) -> None:
        recall, all_present = answer_token_recall("", [{"content": "anything"}])

        assert recall is None
        assert all_present is None

    def test_empty_context_tokens_return_zero(self) -> None:
        recall, all_present = answer_token_recall("Becoming Nicole", [])

        assert recall == 0.0
        assert all_present == 0.0


class TestSummarizeResults:
    def test_category_5_excluded_from_aggregates(self) -> None:
        summary = summarize_results(
            [
                {
                    "category": 2,
                    "answer_token_recall_at_10": 0.5,
                    "answer_token_recall_at_50": 1.0,
                    "all_answer_tokens_present_at_10": 0.0,
                    "all_answer_tokens_present_at_50": 1.0,
                },
                {
                    "category": 5,
                    "answer_token_recall_at_10": None,
                    "answer_token_recall_at_50": None,
                    "all_answer_tokens_present_at_10": None,
                    "all_answer_tokens_present_at_50": None,
                },
            ],
        )

        assert summary["count"] == 1
        assert summary["excluded_adversarial"] == 1
        assert summary["answer_token_recall_at_10"] == 0.5
        assert summary["answer_token_recall_at_50"] == 1.0
        assert summary["by_category"]["temporal"]["count"] == 1
        assert "adversarial" not in summary["by_category"]

    def test_multi_hop_helper_metrics_are_summarized(self) -> None:
        summary = summarize_results(
            [
                {
                    "category": 1,
                    "context_count": 0,
                    "locomo_multihop_helpers": {"fact_fallback": 1},
                    "answer_token_recall_at_10": 0.0,
                    "answer_token_recall_at_50": 0.5,
                    "all_answer_tokens_present_at_10": 0.0,
                    "all_answer_tokens_present_at_50": 0.0,
                },
                {
                    "category": 1,
                    "context_count": 2,
                    "locomo_multihop_helpers": {"profile": 2, "alias": 1},
                    "answer_token_recall_at_10": 1.0,
                    "answer_token_recall_at_50": 1.0,
                    "all_answer_tokens_present_at_10": 1.0,
                    "all_answer_tokens_present_at_50": 1.0,
                },
            ],
        )

        assert summary["multi_hop_zero_context_count"] == 1
        assert summary["multi_hop_helper_hit_counts"] == {
            "alias": 1,
            "fact_fallback": 1,
            "profile": 2,
        }
        assert summary["multi_hop_feature_recall_at_10"] == 0.5


class TestWriteDiagnosticsJson:
    def test_write_json_uses_required_config_shape(self, tmp_path: Path) -> None:
        out = write_diagnostics_json(
            tmp_path,
            mode="scope_all",
            conversations=1,
            top_k=10,
            ceiling_top_k=50,
            temporal_boost=False,
            entity_boost=False,
            summary={"answer_token_recall_at_10": 0.5},
            results=[],
            errors=0,
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["config"] == {
            "mode": "scope_all",
            "conversations": 1,
            "top_k": 10,
            "ceiling_top_k": 50,
            "temporal_boost": False,
            "entity_boost": False,
            "entity_aware_graph": False,
            "fact_index": False,
        }
        assert payload["summary"]["answer_token_recall_at_10"] == 0.5

    def test_write_json_can_include_fact_ablation(self, tmp_path: Path) -> None:
        out = write_diagnostics_json(
            tmp_path,
            mode="scope_all",
            conversations=1,
            top_k=10,
            ceiling_top_k=10,
            temporal_boost=False,
            entity_boost=False,
            fact_index=False,
            summary={},
            results=[],
            errors=0,
            fact_ablation={
                "config": {"fact_index": True},
                "summary": {"answer_token_recall_at_10": 0.6},
                "results": [],
                "errors": 0,
                "deltas": {"answer_token_recall_at_10": 0.1},
            },
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["fact_ablation"]["config"] == {"fact_index": True}
        assert payload["fact_ablation"]["deltas"]["answer_token_recall_at_10"] == 0.1

    def test_write_json_can_include_entity_aware_graph_ablation(self, tmp_path: Path) -> None:
        out = write_diagnostics_json(
            tmp_path,
            mode="vector_graph",
            conversations=1,
            top_k=10,
            ceiling_top_k=10,
            temporal_boost=False,
            entity_boost=False,
            summary={},
            results=[],
            errors=0,
            entity_aware_graph_ablation={
                "config": {"entity_aware_graph": True},
                "summary": {"answer_token_recall_at_10": 0.7},
                "results": [],
                "errors": 0,
                "deltas": {"answer_token_recall_at_10": 0.2},
            },
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["entity_aware_graph_ablation"]["config"] == {"entity_aware_graph": True}
        assert payload["entity_aware_graph_ablation"]["deltas"]["answer_token_recall_at_10"] == 0.2

    def test_write_json_can_include_feature_on_ablation(self, tmp_path: Path) -> None:
        out = write_diagnostics_json(
            tmp_path,
            mode="scope_all",
            conversations=1,
            top_k=10,
            ceiling_top_k=10,
            temporal_boost=False,
            entity_boost=False,
            summary={},
            results=[],
            errors=0,
            feature_on_ablation={
                "config": {"fact_index": True, "entity_boost": True, "entity_aware_graph": True},
                "summary": {"answer_token_recall_at_10": 0.8},
                "results": [],
                "errors": 0,
                "deltas": {"answer_token_recall_at_10": 0.3},
                "per_question_deltas": [],
            },
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["feature_on_ablation"]["config"]["fact_index"] is True
        assert payload["feature_on_ablation"]["deltas"]["answer_token_recall_at_10"] == 0.3

    def test_write_json_path_can_include_temporal_and_entity_ablation(self, tmp_path: Path) -> None:
        out = write_diagnostics_json(
            tmp_path / "diagnostics.json",
            mode="scope_all",
            conversations=1,
            top_k=10,
            ceiling_top_k=10,
            temporal_boost=False,
            entity_boost=False,
            summary={},
            results=[],
            errors=0,
            temporal_ablation={"config": {"temporal_boost": True}},
            entity_ablation={"config": {"entity_boost": True}},
        )

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert out.name == "diagnostics.json"
        assert payload["temporal_ablation"]["config"]["temporal_boost"] is True
        assert payload["entity_ablation"]["config"]["entity_boost"] is True


class TestRetrievalHelpers:
    def test_retrieve_at_k_restores_adapter_top_k(self) -> None:
        class FakeAdapter:
            def __init__(self) -> None:
                self._top_k = 3

            def retrieve(self, question: str, *, category: int):
                return [{"content": question, "score": float(self._top_k), "category": category}]

        adapter = FakeAdapter()

        rows = retrieval_diagnostics._retrieve_at_k(adapter, "Q", category=1, top_k=7)

        assert rows[0]["score"] == 7.0
        assert adapter._top_k == 3
        assert retrieval_diagnostics._top_score(rows) == 7.0
        assert retrieval_diagnostics._top_score([]) is None

    def test_temporary_fact_index_none_preserves_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOCOMO_FACT_INDEX", "1")

        with _temporary_fact_index(None):
            assert os.environ["LOCOMO_FACT_INDEX"] == "1"

        assert os.environ["LOCOMO_FACT_INDEX"] == "1"


class TestTemporalAblationCli:
    def test_parse_temporal_ablation_flag(self) -> None:
        args = parse_args(["--temporal-ablation"])

        assert args.temporal_ablation is True

    def test_temporary_temporal_boost_sets_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOCOMO_TEMPORAL_BOOST", raising=False)

        with _temporary_temporal_boost(True):
            assert os.environ["LOCOMO_TEMPORAL_BOOST"] == "1"

        assert "LOCOMO_TEMPORAL_BOOST" not in os.environ


class TestEntityAblationCli:
    def test_parse_entity_ablation_flag(self) -> None:
        args = parse_args(["--entity-ablation"])

        assert args.entity_ablation is True

    def test_temporary_entity_boost_sets_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOCOMO_ENTITY_BOOST", raising=False)

        with _temporary_entity_boost(True):
            assert os.environ["LOCOMO_ENTITY_BOOST"] == "1"

        assert "LOCOMO_ENTITY_BOOST" not in os.environ


class TestEntityAwareGraphAblationCli:
    def test_parse_entity_aware_graph_ablation_flag(self) -> None:
        args = parse_args(["--entity-aware-graph-ablation"])

        assert args.entity_aware_graph_ablation is True

    def test_temporary_entity_aware_graph_sets_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOCOMO_ENTITY_AWARE_GRAPH", raising=False)

        with _temporary_entity_aware_graph(True):
            assert os.environ["LOCOMO_ENTITY_AWARE_GRAPH"] == "1"

        assert "LOCOMO_ENTITY_AWARE_GRAPH" not in os.environ

    def test_entity_aware_graph_ablation_runs_baseline_then_boosted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[bool] = []
        captured_write: dict[str, object] = {}

        monkeypatch.setattr(retrieval_diagnostics, "load_dataset", lambda _path: [{"qa": []}])
        monkeypatch.setattr(retrieval_diagnostics, "summarize_results", lambda _results: {})
        monkeypatch.setattr(retrieval_diagnostics, "_ablation_delta", lambda _base, _boosted: {})

        def fake_run_retrieval_diagnostics(**kwargs):
            calls.append(kwargs["entity_aware_graph"])
            return [], 0

        def fake_write_diagnostics_json(_output: Path, **kwargs):
            captured_write.update(kwargs)
            return tmp_path / "out.json"

        monkeypatch.setattr(retrieval_diagnostics, "run_retrieval_diagnostics", fake_run_retrieval_diagnostics)
        monkeypatch.setattr(retrieval_diagnostics, "write_diagnostics_json", fake_write_diagnostics_json)

        assert retrieval_diagnostics.main(["--entity-aware-graph-ablation", "--output", str(tmp_path)]) == 0
        assert calls == [False, True]
        assert captured_write["entity_aware_graph_ablation"] is not None


class TestFactAblationCli:
    def test_parse_fact_ablation_flag(self) -> None:
        args = parse_args(["--fact-ablation"])

        assert args.fact_ablation is True

    def test_temporary_fact_index_sets_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOCOMO_FACT_INDEX", raising=False)

        with _temporary_fact_index(True):
            assert os.environ["LOCOMO_FACT_INDEX"] == "1"

        assert "LOCOMO_FACT_INDEX" not in os.environ

    def test_main_respects_fact_index_env_without_ablation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, bool] = {}

        monkeypatch.setenv("LOCOMO_FACT_INDEX", "1")
        monkeypatch.setattr(retrieval_diagnostics, "load_dataset", lambda _path: [{"qa": []}])
        monkeypatch.setattr(retrieval_diagnostics, "summarize_results", lambda _results: {})

        def fake_run_retrieval_diagnostics(**kwargs):
            captured["run_fact_index"] = kwargs["fact_index"]
            return [], 0

        def fake_write_diagnostics_json(_output: Path, **kwargs):
            captured["write_fact_index"] = kwargs["fact_index"]
            return tmp_path / "out.json"

        monkeypatch.setattr(retrieval_diagnostics, "run_retrieval_diagnostics", fake_run_retrieval_diagnostics)
        monkeypatch.setattr(retrieval_diagnostics, "write_diagnostics_json", fake_write_diagnostics_json)

        assert retrieval_diagnostics.main(["--output", str(tmp_path)]) == 0
        assert captured == {"run_fact_index": True, "write_fact_index": True}

    def test_fact_ablation_forces_baseline_false_then_boosted_true(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[bool] = []

        monkeypatch.setenv("LOCOMO_FACT_INDEX", "1")
        monkeypatch.setattr(retrieval_diagnostics, "load_dataset", lambda _path: [{"qa": []}])
        monkeypatch.setattr(retrieval_diagnostics, "summarize_results", lambda _results: {})
        monkeypatch.setattr(retrieval_diagnostics, "_ablation_delta", lambda _base, _boosted: {})

        def fake_run_retrieval_diagnostics(**kwargs):
            calls.append(kwargs["fact_index"])
            return [], 0

        monkeypatch.setattr(retrieval_diagnostics, "run_retrieval_diagnostics", fake_run_retrieval_diagnostics)
        monkeypatch.setattr(
            retrieval_diagnostics,
            "write_diagnostics_json",
            lambda _output, **_kwargs: tmp_path / "out.json",
        )

        assert retrieval_diagnostics.main(["--fact-ablation", "--output", str(tmp_path)]) == 0
        assert calls == [False, True]

    def test_temporal_ablation_preserves_env_fact_index(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[bool] = []

        monkeypatch.setenv("LOCOMO_FACT_INDEX", "1")
        monkeypatch.setattr(retrieval_diagnostics, "load_dataset", lambda _path: [{"qa": []}])
        monkeypatch.setattr(retrieval_diagnostics, "summarize_results", lambda _results: {})
        monkeypatch.setattr(retrieval_diagnostics, "_ablation_delta", lambda _base, _boosted: {})

        def fake_run_retrieval_diagnostics(**kwargs):
            calls.append(kwargs["fact_index"])
            return [], 0

        monkeypatch.setattr(retrieval_diagnostics, "run_retrieval_diagnostics", fake_run_retrieval_diagnostics)
        monkeypatch.setattr(
            retrieval_diagnostics,
            "write_diagnostics_json",
            lambda _output, **_kwargs: tmp_path / "out.json",
        )

        assert retrieval_diagnostics.main(["--temporal-ablation", "--output", str(tmp_path)]) == 0
        assert calls == [True, True]


class TestFeatureOnAblationCli:
    def test_parse_feature_on_ablation_flag(self) -> None:
        args = parse_args(["--feature-on-ablation"])

        assert args.feature_on_ablation is True

    def test_feature_on_ablation_runs_baseline_then_combined(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[tuple[bool, bool, bool]] = []
        captured_write: dict[str, object] = {}

        monkeypatch.setenv("LOCOMO_FACT_INDEX", "1")
        monkeypatch.setattr(retrieval_diagnostics, "load_dataset", lambda _path: [{"qa": []}])
        monkeypatch.setattr(retrieval_diagnostics, "summarize_results", lambda _results: {})
        monkeypatch.setattr(retrieval_diagnostics, "_ablation_delta", lambda _base, _boosted: {})

        def fake_run_retrieval_diagnostics(**kwargs):
            calls.append((kwargs["fact_index"], kwargs["entity_boost"], kwargs["entity_aware_graph"]))
            return [], 0

        def fake_write_diagnostics_json(_output: Path, **kwargs):
            captured_write.update(kwargs)
            return tmp_path / "out.json"

        monkeypatch.setattr(retrieval_diagnostics, "run_retrieval_diagnostics", fake_run_retrieval_diagnostics)
        monkeypatch.setattr(retrieval_diagnostics, "write_diagnostics_json", fake_write_diagnostics_json)

        assert retrieval_diagnostics.main(["--feature-on-ablation", "--output", str(tmp_path)]) == 0
        assert calls == [(False, False, False), (True, True, True)]
        assert captured_write["feature_on_ablation"] is not None
        assert captured_write["fact_index"] is False


class TestPerQuestionDeltas:
    def test_per_question_deltas_skip_cat5_and_report_memory_type_changes(self) -> None:
        rows = _per_question_deltas(
            [
                {
                    "sample_id": "conv-1",
                    "question_index": 0,
                    "category": 1,
                    "question": "Q",
                    "reference": "A",
                    "answer_token_recall_at_10": 0.0,
                    "answer_token_recall_at_50": 0.5,
                    "top_memory_type": "episodes",
                },
                {
                    "sample_id": "conv-1",
                    "question_index": 1,
                    "category": 5,
                    "question": "Adv",
                    "answer_token_recall_at_10": None,
                },
            ],
            [
                {
                    "sample_id": "conv-1",
                    "question_index": 0,
                    "category": 1,
                    "question": "Q",
                    "reference": "A",
                    "answer_token_recall_at_10": 1.0,
                    "answer_token_recall_at_50": 1.0,
                    "top_memory_type": "facts",
                },
                {
                    "sample_id": "conv-1",
                    "question_index": 1,
                    "category": 5,
                    "question": "Adv",
                    "answer_token_recall_at_10": None,
                },
            ],
        )

        assert len(rows) == 1
        assert rows[0]["answer_token_recall_at_10_delta"] == 1.0
        assert rows[0]["base_top_memory_type"] == "episodes"
        assert rows[0]["boosted_top_memory_type"] == "facts"
