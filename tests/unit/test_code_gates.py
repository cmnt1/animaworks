"""Ratchet tests for JSON-file writes and direct status.json references.

Run ``python -m tests.unit.test_code_gates --update`` from the repository root
to regenerate the reviewed file/count baselines after intentional cleanup.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("core", "cli", "server")
BASELINE_PATH = Path(__file__).with_name("code_gates_baseline.json")


def _python_files() -> list[Path]:
    return sorted(
        path for package in SCAN_ROOTS for path in (ROOT / package).rglob("*.py") if "__pycache__" not in path.parts
    )


def _is_json_dumps_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "dumps"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "json"
    )


@lru_cache(maxsize=1)
def _parsed_python_files() -> tuple[tuple[Path, ast.Module], ...]:
    return tuple((path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))) for path in _python_files())


@lru_cache(maxsize=1)
def _collect_code_gate_data() -> tuple[dict[str, int], list[str]]:
    """Collect both gates in one AST pass to keep the checks fast."""
    counts: Counter[str] = Counter()
    status_files = []
    for path, tree in _parsed_python_files():
        relative_path = path.relative_to(ROOT).as_posix()
        has_status_literal = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "status.json":
                has_status_literal = True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "write_text"
                and node.args
                and _is_json_dumps_call(node.args[0])
            ):
                counts[relative_path] += 1
        if has_status_literal:
            status_files.append(relative_path)
    return dict(sorted(counts.items())), status_files


def collect_write_text_json_dumps() -> dict[str, int]:
    """Count calls whose first write_text argument is json.dumps(...)."""
    return _collect_code_gate_data()[0]


def collect_status_json_literal_files() -> list[str]:
    """Return files containing an actual string literal equal to status.json."""
    return _collect_code_gate_data()[1]


def _activity_alog_calls() -> list[ast.Call]:
    """Parse anima source once and return activity logger calls with literal event types."""
    calls: list[ast.Call] = []
    for path in sorted((ROOT / "core" / "anima").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "alog":
                continue
            receiver = node.func.value
            if not isinstance(receiver, ast.Attribute) or receiver.attr not in {"_activity", "activity"}:
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                calls.append(node)
    return calls


def _call_keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def _expression(source: str) -> ast.expr:
    return ast.parse(source, mode="eval").body


def test_anima_activity_summaries_match_the_event_contract() -> None:
    """Check activity event payloads structurally instead of matching source text."""
    calls = _activity_alog_calls()
    heartbeat = [
        call
        for call in calls
        if call.args[0].value == "heartbeat_start"
        and ast.dump(_call_keyword(call, "summary"), include_attributes=False)
        == ast.dump(_expression("t('anima.heartbeat_start')"), include_attributes=False)
    ]
    assert heartbeat

    message_received = [call for call in calls if call.args[0].value == "message_received"]
    content_summary = [
        call
        for call in message_received
        if ast.dump(_call_keyword(call, "content"), include_attributes=False)
        == ast.dump(_expression("content"), include_attributes=False)
        and ast.dump(_call_keyword(call, "summary"), include_attributes=False)
        == ast.dump(_expression("content[:100]"), include_attributes=False)
    ]
    assert len(content_summary) == 2

    anima_content_summary = [
        call
        for call in message_received
        if ast.dump(_call_keyword(call, "content"), include_attributes=False)
        == ast.dump(_expression("_m.content"), include_attributes=False)
        and ast.dump(_call_keyword(call, "summary"), include_attributes=False)
        == ast.dump(_expression("_m.content[:200]"), include_attributes=False)
    ]
    assert anima_content_summary


def _class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    return next(
        node
        for node in owner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name
    )


def _is_activity_logger_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ActivityLogger"


def _is_activity_method_call(node: ast.AST, method_name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method_name
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_activity"
    )


def _assignment_to_self_attr(node: ast.AST, name: str) -> bool:
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    return any(
        isinstance(target, ast.Attribute)
        and target.attr == name
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
        for target in targets
    )


def test_activity_logger_consolidation_contract_is_explicit() -> None:
    """AST gate for shared logger ownership and guarded read paths."""
    anima_path = ROOT / "core/anima/digital_anima.py"
    handler_path = ROOT / "core/tooling/handler.py"
    anima_tree = ast.parse(anima_path.read_text(encoding="utf-8"), filename=str(anima_path))
    handler_tree = ast.parse(handler_path.read_text(encoding="utf-8"), filename=str(handler_path))
    anima_init = _class_method(anima_tree, "DigitalAnima", "__init__")
    handler_init = _class_method(handler_tree, "ToolHandler", "__init__")

    def has_logger_assignment(method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        return any(
            _assignment_to_self_attr(node, "_activity")
            and any(_is_activity_logger_call(child) for child in ast.walk(node))
            for node in ast.walk(method)
        )

    assert has_logger_assignment(anima_init)
    assert has_logger_assignment(handler_init)

    for tree, allowed_method in ((anima_tree, "__init__"), (handler_tree, "__init__")):
        for node in ast.walk(tree):
            if not _is_activity_logger_call(node):
                continue
            method = next(
                (
                    parent
                    for parent in ast.walk(tree)
                    if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)) and node in ast.walk(parent)
                ),
                None,
            )
            assert method is not None and method.name == allowed_method

    anima_modules = [
        ROOT / "core/anima" / f"{name}.py" for name in ("digital_anima", "lifecycle", "messaging", "inbox", "heartbeat")
    ]
    anima_calls = [
        node
        for path in anima_modules
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if _is_activity_method_call(node, "alog") or _is_activity_method_call(node, "recent")
    ]
    handler_calls = [node for node in ast.walk(handler_tree) if _is_activity_method_call(node, "log")]
    assert anima_calls
    assert handler_calls

    messaging_path = ROOT / "core/anima/messaging.py"
    messaging_tree = ast.parse(messaging_path.read_text(encoding="utf-8"), filename=str(messaging_path))
    stream_method = _class_method(messaging_tree, "MessagingMixin", "process_message_stream")
    receive_calls = [
        node
        for node in ast.walk(stream_method)
        if _is_activity_method_call(node, "alog")
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "message_received"
    ]
    assert receive_calls
    parents = {child: parent for parent in ast.walk(stream_method) for child in ast.iter_child_nodes(parent)}
    for call in receive_calls:
        parent = parents.get(call)
        while parent is not None:
            assert not (isinstance(parent, ast.Try) and parent.handlers), (
                "message_received activity writes must not be swallowed by a local except handler"
            )
            parent = parents.get(parent)

    heartbeat_path = ROOT / "core/anima/heartbeat.py"
    heartbeat_tree = ast.parse(heartbeat_path.read_text(encoding="utf-8"), filename=str(heartbeat_path))
    for method_name in ("_load_heartbeat_history", "_load_recent_reflections"):
        method = _class_method(heartbeat_tree, "HeartbeatMixin", method_name)
        fallbacks = [
            handler
            for try_node in ast.walk(method)
            if isinstance(try_node, ast.Try)
            for handler in try_node.handlers
            if isinstance(handler.type, ast.Name)
            and handler.type.id == "Exception"
            and any(
                isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and node.value.value == ""
                for node in ast.walk(handler)
            )
        ]
        assert fallbacks, f"{method_name} must retain an empty-string recovery fallback"


def test_activity_logger_live_tool_policy_is_structural() -> None:
    """Check the live-event and tool visibility contract without source substrings."""
    path = ROOT / "core/activity/logger.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assignments = {
        target.id: node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    live_types = assignments["_LIVE_EVENT_TYPES"]
    live_strings = {
        node.value for node in ast.walk(live_types) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "tool_use" not in live_strings

    visible_tools = assignments["_VISIBLE_TOOL_NAMES"]
    assert isinstance(visible_tools, ast.Call)
    assert isinstance(visible_tools.func, ast.Name) and visible_tools.func.id == "frozenset"
    tool_names = {
        node.value for node in ast.walk(visible_tools) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert {
        "delegate_task",
        "update_task",
        "backlog_task",
        "submit_tasks",
        "call_human",
        "post_channel",
        "send_message",
    } <= tool_names

    log_method = _class_method(tree, "ActivityLogger", "log")
    tool_branch = any(
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "event_type"
        and any(
            isinstance(comparator, ast.Tuple)
            and {element.value for element in comparator.elts if isinstance(element, ast.Constant)}
            == {"tool_use", "tool_result"}
            for comparator in node.comparators
        )
        for node in ast.walk(log_method)
    )
    assert tool_branch
    assert any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "allow"
        for node in ast.walk(log_method)
    )
    assert any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_emit_live_event"
        for node in ast.walk(log_method)
    )


def test_anima_message_received_from_anima_has_destination() -> None:
    """Anima-originated receive events retain sender metadata and their destination."""
    matching = []
    for call in _activity_alog_calls():
        if not call.args or not isinstance(call.args[0], ast.Constant) or call.args[0].value != "message_received":
            continue
        meta = _call_keyword(call, "meta")
        to_person = _call_keyword(call, "to_person")
        if not isinstance(meta, ast.Dict) or to_person is None:
            continue
        metadata_keys = {key.value for key in meta.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}
        if "from_type" in metadata_keys and ast.unparse(to_person) in {"self.name", "anima_mixin.name"}:
            matching.append(call)
    assert matching


def test_streaming_documentation_is_kept_in_python_ast() -> None:
    """Keep the documented streaming-mode and executor ownership contracts."""
    agent_path = ROOT / "core" / "agent" / "agent_core.py"
    executor_path = ROOT / "core" / "execution" / "engines" / "litellm" / "executor.py"
    agent_tree = ast.parse(agent_path.read_text(encoding="utf-8"), filename=str(agent_path))
    executor_tree = ast.parse(executor_path.read_text(encoding="utf-8"), filename=str(executor_path))

    agent_docstrings = [
        node.value for node in ast.walk(agent_tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert any("S / A / all modes" in text for text in agent_docstrings)

    executor_method = next(
        node
        for node in ast.walk(executor_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "execute_streaming"
    )
    executor_docstring = ast.get_docstring(executor_method) or ""
    assert "Session chaining is handled by AgentCore" in executor_docstring
    assert "NOT handled" not in executor_docstring


def _current_baseline() -> dict[str, object]:
    return {
        "write_text_json_dumps": collect_write_text_json_dumps(),
        "status_json_literal_files": collect_status_json_literal_files(),
    }


def _read_baseline() -> dict[str, object]:
    if not BASELINE_PATH.exists():
        raise AssertionError(
            f"Missing code gate baseline: {BASELINE_PATH}; run python -m tests.unit.test_code_gates --update"
        )
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def update_baseline() -> None:
    """Rewrite baselines from current code; review the diff before accepting it."""
    BASELINE_PATH.write_text(json.dumps(_current_baseline(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote code gate baseline to {BASELINE_PATH}")


def test_write_text_json_dumps_matches_baseline() -> None:
    expected = _read_baseline()["write_text_json_dumps"]
    actual = collect_write_text_json_dumps()
    assert actual == expected, (
        "write_text(json.dumps(...)) file/count baseline changed; update "
        "tests/unit/code_gates_baseline.json after reviewing the change.\n"
        f"Expected: {expected}\nActual: {actual}"
    )


def test_status_json_literal_files_match_baseline() -> None:
    expected = _read_baseline()["status_json_literal_files"]
    actual = collect_status_json_literal_files()
    assert actual == expected, (
        'Files containing the "status.json" string literal changed; update '
        "tests/unit/code_gates_baseline.json after reviewing the change.\n"
        f"Expected: {expected}\nActual: {actual}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="regenerate the reviewed code-gate baseline")
    args = parser.parse_args()
    if args.update:
        update_baseline()
    else:
        parser.error("Use --update to regenerate the baseline, or run this module with pytest")


if __name__ == "__main__":
    main()
