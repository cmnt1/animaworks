from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Backup and restore memory data for migration safety."""

import hashlib
import json
import logging
import shutil
import tarfile
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ── BackupManager ──────────────────────────────────────────────


class BackupManager:
    """Create and restore memory backups."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._backup_dir = data_dir / "backup"

    def create(self, *, label: str = "") -> Path:
        """Create a backup snapshot of all memory data.

        Returns:
            Path to the created backup directory.
        """
        ts = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        name = f"memory-{ts}" + (f"-{label}" if label else "")
        backup_path = self._backup_dir / name
        backup_path.mkdir(parents=True, exist_ok=True)

        targets = [
            "animas",
            "vectordb",
            "common_knowledge",
            "common_skills",
            "shared",
        ]

        config_src = self._data_dir / "config.json"
        if config_src.exists():
            shutil.copy2(config_src, backup_path / "config.json")

        for target in targets:
            src = self._data_dir / target
            if not src.exists():
                continue
            tar_path = backup_path / f"{target}.tar.gz"
            try:
                with tarfile.open(tar_path, "w:gz") as tar:
                    tar.add(src, arcname=target)
                logger.info("Backed up %s -> %s", src, tar_path)
            except Exception:
                logger.warning("Failed to backup %s", target, exc_info=True)

        manifest: dict[str, str] = {}
        for f in sorted(backup_path.iterdir()):
            if f.is_file():
                manifest[f.name] = self._sha256(f)
        (backup_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        logger.info("Backup created: %s", backup_path)
        return backup_path

    def restore(self, backup_name: str) -> None:
        """Restore from a named backup.

        Args:
            backup_name: Name of backup directory
                (e.g. ``"memory-20260422-153000"``).

        Raises:
            FileNotFoundError: If backup doesn't exist.
            ValueError: If manifest verification fails.
        """
        backup_path = self._backup_dir / backup_name
        if not backup_path.is_dir():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        self._verify_manifest(backup_path)

        config_bak = backup_path / "config.json"
        if config_bak.exists():
            shutil.copy2(config_bak, self._data_dir / "config.json")

        for tar_path in sorted(backup_path.glob("*.tar.gz")):
            target_name = tar_path.stem.replace(".tar", "")
            target_dir = self._data_dir / target_name
            try:
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                with tarfile.open(tar_path, "r:gz") as tar:
                    tar.extractall(self._data_dir)  # noqa: S202
                logger.info("Restored %s from %s", target_name, tar_path)
            except Exception:
                logger.warning("Failed to restore %s", target_name, exc_info=True)
                raise

        logger.info("Restore complete from %s", backup_name)

    def list_backups(self) -> list[dict[str, str]]:
        """List available backups."""
        if not self._backup_dir.exists():
            return []
        result: list[dict[str, str]] = []
        for d in sorted(self._backup_dir.iterdir()):
            if d.is_dir() and d.name.startswith("memory-"):
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                result.append(
                    {
                        "name": d.name,
                        "path": str(d),
                        "size_mb": str(round(size / 1024 / 1024, 1)),
                    }
                )
        return result

    # ── Internal ───────────────────────────────────────────────

    def _verify_manifest(self, backup_path: Path) -> None:
        manifest_path = backup_path / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("No manifest.json found in backup")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for fname, expected_hash in manifest.items():
            if fname == "manifest.json":
                continue
            fpath = backup_path / fname
            if not fpath.exists():
                raise ValueError(f"Missing file in backup: {fname}")
            actual_hash = self._sha256(fpath)
            if actual_hash != expected_hash:
                raise ValueError(f"SHA256 mismatch for {fname}")

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
