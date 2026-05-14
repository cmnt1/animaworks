"""CLI commands for Neo4j community maintenance."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def cmd_anima_detect_communities(args: argparse.Namespace) -> None:
    """Run batch community detection for Neo4j-backed animas."""
    from core.paths import get_animas_dir

    animas_dir = get_animas_dir()

    if args.detect_all:
        names = [d.name for d in animas_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    elif args.anima:
        names = [args.anima]
    else:
        print("Error: specify anima name or --all")
        sys.exit(1)

    asyncio.run(_run_detect_communities(names, animas_dir))


async def _run_detect_communities(names: list[str], animas_dir: Path) -> None:
    """Async runner for community detection."""
    from core.memory.backend.registry import get_backend, resolve_backend_type

    for name in names:
        anima_dir = animas_dir / name
        if not anima_dir.is_dir():
            print(f"  {name}: not found, skipping")
            continue

        backend_type = resolve_backend_type(anima_dir)
        if backend_type != "neo4j":
            print(f"  {name}: not using Neo4j (backend={backend_type}), skipping")
            continue

        print(f"  {name}: detecting communities...")
        backend = None
        try:
            backend = get_backend(backend_type, anima_dir)
            driver = await backend._ensure_driver()

            from core.memory.graph.community import CommunityDetector

            detector = CommunityDetector(
                driver,
                backend._group_id,
                model=backend._resolve_background_model(),
                locale=backend._resolve_locale(),
            )
            communities = await detector.detect_and_store()
            stats = await detector.get_community_stats()
            print(
                f"  {name}: {len(communities)} communities detected "
                f"(stored={stats['communities']}, memberships={stats['memberships']})"
            )
        except Exception as e:
            print(f"  {name}: ERROR - {e}")
        finally:
            if backend is not None:
                try:
                    await backend.close()
                except Exception as e:
                    logger.debug("Failed to close Neo4j backend after community detection: %s", e, exc_info=True)
