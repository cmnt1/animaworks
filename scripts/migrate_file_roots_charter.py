#!/usr/bin/env python3
"""Charter migration: strip data_dir paths from every anima's file_roots.

docs/specs/write-access-charter.ja.md — file_roots must not contain paths
under the runtime data dir. Company shared is granted unconditionally by
the sandbox, so those entries are redundant; everything else data_dir-side
is forbidden. Run once at deploy time, before restarting the server.
"""

import json
import sys
from pathlib import Path

DATA_DIR = Path("~/.animaworks").expanduser().resolve()

apply = "--apply" in sys.argv
for perms_path in sorted(DATA_DIR.glob("animas/*/permissions.json")):
    anima = perms_path.parent.name
    perms = json.loads(perms_path.read_text())
    roots = perms.get("file_roots", [])
    keep, drop = [], []
    for root in roots:
        resolved = Path(root).expanduser().resolve()
        # "/" is the legacy full-trust root (librarian); not a data_dir entry.
        if resolved != Path("/") and resolved.is_relative_to(DATA_DIR):
            drop.append(root)
        else:
            keep.append(root)
    if not drop:
        continue
    print(f"{anima}: drop {drop} -> keep {keep}")
    if apply:
        backup = perms_path.with_suffix(".json.bak-charter")
        backup.write_text(perms_path.read_text())
        perms["file_roots"] = keep
        perms_path.write_text(json.dumps(perms, indent=2, ensure_ascii=False) + "\n")

if not apply:
    print("(dry-run; pass --apply to write)")
