"""Shared helpers for modularization skill-pack unit tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACK = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(
    script: Path,
    *args: str,
    cwd: Path | None = None,
    expected: int = 0,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [PYTHON, str(script), *map(str, args)],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != expected:
        raise AssertionError(
            f"expected exit {expected}, got {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def skill_script(skill: str, name: str) -> Path:
    return PACK / skill / "scripts" / name


class PackTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = Path(tempfile.mkdtemp(prefix="modularization-pack-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temporary, ignore_errors=True)

    def write(self, relative: str, text: str = "") -> Path:
        path = self.temporary / relative
        write(path, text)
        return path
