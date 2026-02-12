"""First-launch initialization: copy templates to runtime data directory."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from core.paths import TEMPLATES_DIR, get_data_dir

logger = logging.getLogger("animaworks.init")


def ensure_runtime_dir() -> Path:
    """Ensure the runtime data directory exists, seeding from templates if needed.

    Returns the runtime data directory path.
    """
    data_dir = get_data_dir()

    if data_dir.exists():
        _maybe_migrate_config(data_dir)
        logger.debug("Runtime directory already exists: %s", data_dir)
        return data_dir

    logger.info("First launch: initializing runtime directory at %s", data_dir)

    if not TEMPLATES_DIR.exists():
        raise FileNotFoundError(
            f"Templates directory not found: {TEMPLATES_DIR}. "
            "Is the project installed correctly?"
        )

    # Copy templates tree: templates/persons/ -> data_dir/persons/, etc.
    data_dir.mkdir(parents=True, exist_ok=True)
    for item in TEMPLATES_DIR.iterdir():
        target = data_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)

    # Create runtime-only directories that have no template
    (data_dir / "shared" / "inbox").mkdir(parents=True, exist_ok=True)
    (data_dir / "tmp" / "attachments").mkdir(parents=True, exist_ok=True)
    (data_dir / "common_skills").mkdir(parents=True, exist_ok=True)

    # Generate default config.json
    _create_default_config(data_dir)

    logger.info("Runtime directory initialized: %s", data_dir)
    return data_dir


def _create_default_config(data_dir: Path) -> None:
    """Generate a default config.json for a freshly initialized runtime."""
    from core.config import (
        AnimaWorksConfig,
        CredentialConfig,
        PersonModelConfig,
        save_config,
    )

    config = AnimaWorksConfig(
        credentials={"anthropic": CredentialConfig()},
    )

    # Auto-detect persons from the just-copied templates
    persons_dir = data_dir / "persons"
    if persons_dir.exists():
        for d in sorted(persons_dir.iterdir()):
            if d.is_dir() and (d / "identity.md").exists():
                config.persons[d.name] = PersonModelConfig()

    save_config(config, data_dir / "config.json")
    logger.info("Default config.json created at %s", data_dir / "config.json")


def _maybe_migrate_config(data_dir: Path) -> None:
    """Auto-migrate existing config.md setups to config.json if needed."""
    config_path = data_dir / "config.json"
    if config_path.exists():
        return

    persons_dir = data_dir / "persons"
    if not persons_dir.exists():
        return

    has_legacy = any(
        (d / "config.md").exists()
        for d in persons_dir.iterdir()
        if d.is_dir()
    )
    if not has_legacy:
        return

    logger.info("Migrating legacy config.md files to config.json")
    from core.config_migrate import migrate_to_config_json

    migrate_to_config_json(data_dir)
