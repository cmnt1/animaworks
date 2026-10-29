from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from cli.parser import build_parser


def test_forgetting_dry_run_cli_uses_vector_access_and_reports_json(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    data_dir = tmp_path / "runtime-data"
    anima_dir = data_dir / "animas" / "alice"
    anima_dir.mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))

    class ReadOnlyStore:
        def __init__(self) -> None:
            self.writes = 0

        def get_all(self, _collection: str, *, limit: int = 100_000) -> list:  # noqa: ARG002
            return []

        def count(self, _collection: str) -> int:
            return 0

        def update_metadata(self, *_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            self.writes += 1

        def upsert(self, *_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
            self.writes += 1

    store = ReadOnlyStore()
    calls: list[tuple[str, Path, str]] = []

    @contextmanager
    def fake_open_vector_access(
        anima_name: str,
        path: Path,
        *,
        purpose: str,
    ) -> Iterator[SimpleNamespace]:
        calls.append((anima_name, path, purpose))
        yield SimpleNamespace(store=store)

    monkeypatch.setattr("core.memory.rag.cli_access.open_vector_access", fake_open_vector_access)

    args = build_parser().parse_args(["memory", "forgetting-dry-run", "--anima", "alice"])
    args.func(args)

    output = json.loads(capsys.readouterr().out)
    assert output["dry_run"] is True
    assert output["scanned"] == 0
    assert output["collections"]["alice_knowledge"]["complete_forgetting_targets"] == 0
    assert calls == [("alice", anima_dir, "forgetting-dry-run")]
    assert store.writes == 0
