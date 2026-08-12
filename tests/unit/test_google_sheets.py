from __future__ import annotations

import json
from pathlib import Path

from core.tools.google_sheets import _credentials_dir


def test_credentials_dir_prefers_running_animas_company(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "animas" / "sakura"
    anima_dir.mkdir(parents=True)
    (anima_dir / "status.json").write_text(json.dumps({"company": "fs"}), encoding="utf-8")
    credentials_dir = tmp_path / "companies" / "fs" / "credentials" / "fs" / "google_sheets"
    credentials_dir.mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))

    assert _credentials_dir() == credentials_dir
