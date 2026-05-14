"""E2E tests for shared inbox TTL hygiene."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from core.memory.housekeeping import run_housekeeping
from core.messenger import Messenger
from core.time_utils import now_local


def _rewrite_timestamp(path: Path, timestamp) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["timestamp"] = timestamp.isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.asyncio
async def test_housekeeping_expires_low_priority_inbox_but_preserves_human(tmp_path: Path):
    """Real Messenger files are swept by real housekeeping with protection rules."""
    shared_dir = tmp_path / "shared"
    bob = Messenger(shared_dir, "bob")
    alice = Messenger(shared_dir, "alice")

    low_priority = bob.send("alice", "old internal status", intent="report")
    human_msg = alice.receive_external(
        content="old but directed human request",
        source="human",
        external_user_id="human-1",
        intent="question",
    )
    assert human_msg is not None

    old = now_local() - timedelta(hours=30)
    alice_inbox = shared_dir / "inbox" / "alice"
    _rewrite_timestamp(alice_inbox / f"{low_priority.id}.json", old)
    _rewrite_timestamp(alice_inbox / f"{human_msg.id}.json", old)

    result = await run_housekeeping(tmp_path, inbox_ttl_hours=24)

    shared = result["shared_inbox"]
    assert shared["expired"] == 1
    assert shared["protected"] == 1
    assert (alice_inbox / "expired" / f"{low_priority.id}.json").exists()
    assert (alice_inbox / f"{human_msg.id}.json").exists()
    assert len(alice.receive_with_paths()) == 1
    assert alice.receive_with_paths()[0].msg.content == "old but directed human request"
