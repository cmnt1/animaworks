from __future__ import annotations

import json
from pathlib import Path

from benchmarks.locomo.fact_index import (
    extract_locomo_fact_records,
    fact_bm25_documents,
    write_fact_records,
)


def test_extract_locomo_fact_records_are_deterministic_and_session_grounded() -> None:
    conversation = {
        "speaker_a": "Caroline",
        "speaker_b": "Melanie",
        "session_1_date_time": "7 May 2023, 10:00 AM",
        "session_1": [
            {
                "speaker": "Caroline",
                "text": "I recommended Becoming Nicole. We talked about an LGBTQ support group.",
            },
            {"speaker": "Melanie", "text": "That book sounds helpful."},
        ],
    }

    first = extract_locomo_fact_records("conv-26", conversation, source_episode="episodes/conv-26.md")
    second = extract_locomo_fact_records("conv-26", conversation, source_episode="episodes/conv-26.md")

    assert [record.fact_id for record in first] == [record.fact_id for record in second]
    assert len(first) == 3
    assert first[0].text == "Caroline: I recommended Becoming Nicole."
    assert first[0].source_episode == "episodes/conv-26.md"
    assert first[0].session_index == 1
    assert first[0].turn_index == 0
    assert first[0].sentence_index == 0
    assert first[0].event_time_iso.startswith("2023-05-07T10:00:00")
    assert "becoming nicole" in first[0].entities


def test_extract_locomo_fact_records_uses_image_caption_when_text_is_empty() -> None:
    conversation = {
        "session_2_date_time": "8 May 2023",
        "session_2": [
            {
                "speaker": "Caroline",
                "text": "",
                "blip_caption": "a bookstore display for Becoming Nicole",
            },
        ],
    }

    records = extract_locomo_fact_records("conv-26", conversation, source_episode="episodes/conv-26.md")

    assert len(records) == 1
    assert records[0].text == "Caroline: Image caption: a bookstore display for Becoming Nicole"


def test_write_fact_records_creates_markdown_and_skips_existing(tmp_path: Path) -> None:
    conversation = {
        "session_1_date_time": "7 May 2023, 10:00 AM",
        "session_1": [{"speaker": "Caroline", "text": "I recommended Becoming Nicole."}],
    }
    records = extract_locomo_fact_records("conv-26", conversation, source_episode="episodes/conv-26.md")

    assert write_fact_records(tmp_path, records) == 1
    assert write_fact_records(tmp_path, records) == 0

    fact_file = tmp_path / f"fact_{records[0].fact_id}.md"
    text = fact_file.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "source_episode: \"episodes/conv-26.md\"" in text
    assert "Caroline: I recommended Becoming Nicole." in text
    jsonl = tmp_path / "locomo_facts.jsonl"
    payload = json.loads(jsonl.read_text(encoding="utf-8").strip())
    assert payload["fact_id"] == records[0].fact_id
    assert payload["text"] == "Caroline: I recommended Becoming Nicole."
    assert payload["source_entity"] == "Caroline"
    assert payload["source_episode"] == "episodes/conv-26.md"


def test_fact_bm25_documents_use_fact_memory_type_and_numeric_valid_at() -> None:
    conversation = {
        "session_1_date_time": "7 May 2023, 10:00 AM",
        "session_1": [{"speaker": "Caroline", "text": "I recommended Becoming Nicole."}],
    }
    records = extract_locomo_fact_records("conv-26", conversation, source_episode="episodes/conv-26.md")

    documents = fact_bm25_documents(records)

    assert documents[0][0] == "Caroline: I recommended Becoming Nicole."
    assert documents[0][1]["memory_type"] == "facts"
    assert documents[0][1]["source_file"] == f"facts/fact_{records[0].fact_id}.md"
    assert isinstance(documents[0][1]["valid_at"], float)
