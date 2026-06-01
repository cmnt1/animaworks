from __future__ import annotations

import json

from core.execution._antigravity_llm import _sse_event_to_chunk


def test_sse_function_call_chunk_uses_openai_compatible_function_shape() -> None:
    chunk, delta_text, finish_reason, usage = _sse_event_to_chunk(
        {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "write_activity_log",
                                        "args": {"summary": "started"},
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    )

    tool_use = chunk["tool_use"]
    assert tool_use is not None
    assert tool_use["type"] == "function"
    assert tool_use["name"] == "write_activity_log"
    assert tool_use["arguments"] == json.dumps({"summary": "started"}, ensure_ascii=False)
    assert tool_use["function"] == {
        "name": "write_activity_log",
        "arguments": json.dumps({"summary": "started"}, ensure_ascii=False),
    }
    assert tool_use["index"] == 0
    assert delta_text == ""
    assert finish_reason is None
    assert usage is None
