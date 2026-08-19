#!/usr/bin/env python3
"""Fail if unresolved merge-conflict markers are present in runtime source.

The live runtime imports core/ cli/ server/ directly from the checkout, so a
conflict marker left in any of them makes every newly spawned task runner exit
with SyntaxError while the resident processes keep running (issue #279).

Used by CI and by the pre-commit hook (scripts/hooks/pre-commit).
"""

import re
import sys
from pathlib import Path

ROOTS = ("core", "cli", "server")
MARKER_RE = re.compile(rb"^(<{7}|={7}|>{7})(?: |$)", re.MULTILINE)


def main() -> int:
    hits: list[str] = []
    for root in ROOTS:
        for path in Path(root).rglob("*.py"):
            match = MARKER_RE.search(path.read_bytes())
            if match:
                line = path.read_bytes()[: match.start()].count(b"\n") + 1
                hits.append(f"{path}:{line}: {match.group(1).decode()}")
    for hit in hits:
        print(f"conflict marker: {hit}", file=sys.stderr)
    if hits:
        print(f"\n{len(hits)} file(s) contain unresolved merge-conflict markers.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
