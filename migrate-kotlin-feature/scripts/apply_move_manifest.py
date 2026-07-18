#!/usr/bin/env python3
"""Preview or transactionally apply explicit source/resource moves.

Only exact package declaration lines are rewritten. Imports and external identity
must be updated deliberately after each reviewed batch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path


SCHEMA_VERSION = 1
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--require-hashes", action="store_true", help="Reject moves without expected_sha256 preconditions")
    parser.add_argument("--receipt-out", help="Repository-relative JSON receipt path, written only after a successful apply")
    return parser.parse_args()


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read manifest: {exc}") from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    if not isinstance(data.get("moves"), list) or not data["moves"]:
        raise ValueError("manifest moves must be a non-empty list")
    return data


def safe(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute():
        raise ValueError(f"manifest paths must be relative: {relative}")
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes root: {relative}")
    return target


def validate(root: Path, data: dict, require_hashes: bool = False) -> list[dict]:
    prepared = []
    sources: set[Path] = set()
    targets: set[Path] = set()
    for index, move in enumerate(data["moves"], 1):
        if not isinstance(move, dict) or not move.get("from") or not move.get("to"):
            raise ValueError(f"move {index} must contain from and to")
        source = safe(root, move["from"])
        target = safe(root, move["to"])
        if source == target:
            raise ValueError(f"move {index} source and target are identical")
        if source in sources or target in targets:
            raise ValueError(f"duplicate source or target in move {index}")
        sources.add(source)
        targets.add(target)
        if not source.is_file():
            raise ValueError(f"source is not a file: {move['from']}")
        if target.exists():
            raise ValueError(f"target already exists: {move['to']}")
        package_from = move.get("package_from")
        package_to = move.get("package_to")
        if bool(package_from) != bool(package_to):
            raise ValueError(f"move {index} must specify both package_from and package_to")
        original_bytes = source.read_bytes()
        original_sha256 = hashlib.sha256(original_bytes).hexdigest()
        expected_sha256 = move.get("expected_sha256")
        if require_hashes and not expected_sha256:
            raise ValueError(f"move {index} is missing expected_sha256")
        if expected_sha256:
            if not isinstance(expected_sha256, str) or not SHA256_RE.fullmatch(expected_sha256):
                raise ValueError(f"move {index} expected_sha256 must be 64 lowercase hexadecimal characters")
            if original_sha256 != expected_sha256:
                raise ValueError(f"source hash changed for {move['from']}: expected {expected_sha256}, found {original_sha256}")
        rewritten: bytes | None = None
        if package_from:
            if not PACKAGE_NAME_RE.match(package_from) or not PACKAGE_NAME_RE.match(package_to):
                raise ValueError(f"invalid package in move {index}")
            try:
                original_text = original_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"package rewrite requires UTF-8 text: {move['from']}") from exc
            pattern = re.compile(rf"(?m)^(\s*package\s+){re.escape(package_from)}(\s*(?:;)?\s*)$")
            rewritten_text, count = pattern.subn(rf"\g<1>{package_to}\g<2>", original_text, count=1)
            if count != 1:
                raise ValueError(f"exact package declaration not found in {move['from']}: {package_from}")
            rewritten = rewritten_text.encode("utf-8")
        prepared.append({
            "source": source,
            "target": target,
            "source_rel": move["from"],
            "target_rel": move["to"],
            "original": original_bytes,
            "original_sha256": original_sha256,
            "rewritten": rewritten,
            "package_from": package_from,
            "package_to": package_to,
        })
    return prepared


def receipt(data: dict, prepared: list[dict]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": data.get("batch_id"),
        "feature": data.get("feature"),
        "layer": data.get("layer"),
        "moves": [
            {
                "from": move["source_rel"],
                "to": move["target_rel"],
                "source_sha256": move["original_sha256"],
                "target_sha256": hashlib.sha256(move["rewritten"] if move["rewritten"] is not None else move["original"]).hexdigest(),
                "package_from": move["package_from"],
                "package_to": move["package_to"],
            }
            for move in prepared
        ],
    }


def apply(prepared: list[dict]) -> None:
    completed: list[dict] = []
    try:
        for move in prepared:
            move["target"].parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(move["source"]), str(move["target"]))
            completed.append(move)
            if move["rewritten"] is not None:
                move["target"].write_bytes(move["rewritten"])
    except Exception:
        for move in reversed(completed):
            try:
                move["target"].write_bytes(move["original"])
                move["source"].parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(move["target"]), str(move["source"]))
            except Exception as rollback_error:
                print(f"rollback warning for {move['target_rel']}: {rollback_error}", file=sys.stderr)
        raise


def rollback_applied(prepared: list[dict]) -> None:
    errors = []
    for move in reversed(prepared):
        if not move["target"].exists() or move["source"].exists():
            continue
        try:
            move["target"].write_bytes(move["original"])
            move["source"].parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(move["target"]), str(move["source"]))
        except Exception as exc:
            errors.append(f"{move['target_rel']}: {exc}")
    if errors:
        raise RuntimeError("rollback failed for " + "; ".join(errors))


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        data = load(options.manifest)
        prepared = validate(root, data, options.require_hashes)
        receipt_path = safe(root, options.receipt_out) if options.receipt_out else None
        if options.apply and receipt_path and receipt_path.exists():
            raise ValueError(f"refusing to overwrite receipt: {receipt_path.relative_to(root)}")
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{'Applying' if options.apply else 'Dry run:'} {len(prepared)} move(s)")
    for move in prepared:
        package = f"; package {move['package_from']} -> {move['package_to']}" if move["package_from"] else ""
        print(f"  - {move['source_rel']} -> {move['target_rel']}{package}; sha256 {move['original_sha256']}")
    if not options.apply:
        return 0
    receipt_temporary: str | None = None
    try:
        if receipt_path:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, receipt_temporary = tempfile.mkstemp(prefix=f".{receipt_path.name}.", dir=receipt_path.parent)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(receipt(data, prepared), indent=2, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
    except OSError as exc:
        if receipt_temporary and os.path.exists(receipt_temporary):
            os.unlink(receipt_temporary)
        print(f"error: cannot prepare move receipt: {exc}", file=sys.stderr)
        return 3
    try:
        apply(prepared)
        if receipt_path and receipt_temporary:
            os.replace(receipt_temporary, receipt_path)
            receipt_temporary = None
    except Exception as exc:
        if receipt_temporary and os.path.exists(receipt_temporary):
            os.unlink(receipt_temporary)
        try:
            rollback_applied(prepared)
        except Exception as rollback_error:
            print(f"rollback warning after receipt/apply failure: {rollback_error}", file=sys.stderr)
        print(f"error: move failed and rollback was attempted: {exc}", file=sys.stderr)
        return 3
    if receipt_path:
        print(f"Wrote move receipt: {receipt_path.relative_to(root)}")
    print("Moves applied. Update imports/registrations and run the narrowest compile before another batch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
