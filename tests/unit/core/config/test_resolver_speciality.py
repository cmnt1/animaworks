from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""status.json speciality reaches the resolved config (org chart labels)."""

import json

from core.config.models import AnimaWorksConfig
from core.config.resolver import resolve_anima_config


def test_speciality_is_read_from_status_json(tmp_path):
    anima_dir = tmp_path / "hina"
    anima_dir.mkdir()
    (anima_dir / "status.json").write_text(
        json.dumps({"supervisor": "sakura", "speciality": "営業リサーチ担当"}, ensure_ascii=False),
        encoding="utf-8",
    )

    resolved, _ = resolve_anima_config(AnimaWorksConfig(), "hina", anima_dir=anima_dir)

    assert resolved.speciality == "営業リサーチ担当"
