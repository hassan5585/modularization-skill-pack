#!/usr/bin/env python3
"""Compatibility shim: delegates to scaffold-kotlin-feature.

New work should call the sibling skill directly. This wrapper keeps existing
command paths and tests working after the scaffolder ownership move.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> int:
    sibling = (
        Path(__file__).resolve().parents[2]
        / "scaffold-kotlin-feature"
        / "scripts"
        / "scaffold_feature.py"
    )
    if not sibling.is_file():
        print(
            "error: scaffold-kotlin-feature is not installed beside migrate-kotlin-feature; "
            f"expected {sibling}",
            file=sys.stderr,
        )
        return 2
    sys.argv[0] = str(sibling)
    try:
        runpy.run_path(str(sibling), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
