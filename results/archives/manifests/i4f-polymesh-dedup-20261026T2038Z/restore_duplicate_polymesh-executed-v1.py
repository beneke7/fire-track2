#!/usr/bin/env python3
"""Restore one deduplicated polyMesh file from its retained canonical copy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

ROOT = Path.cwd().resolve()
PLAN = ROOT / "results/runs/i4f-disk-recovery-audit-20261026T2038Z/polymesh-dedup-plan.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def checked_relative(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe relative path in plan: {raw}")
    resolved = (ROOT / path).resolve(strict=False)
    if resolved != ROOT and ROOT not in resolved.parents:
        raise ValueError(f"path escapes repository: {raw}")
    return resolved


def restore(duplicate_path: str) -> None:
    plan = json.loads(PLAN.read_text())
    rows = [row for row in plan["planned_files"] if row["duplicate_path"] == duplicate_path]
    if len(rows) != 1:
        raise ValueError(f"expected one matching plan row, found {len(rows)}")
    row = rows[0]
    canonical = checked_relative(row["canonical_path"])
    target = checked_relative(row["duplicate_path"])
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing restore path: {target}")
    if not canonical.is_file() or canonical.is_symlink():
        raise FileNotFoundError(f"retained canonical file is unavailable: {canonical}")
    if canonical.stat().st_size != row["bytes"] or sha256(canonical) != row["sha256"]:
        raise RuntimeError("retained canonical file does not match recorded SHA/size")

    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.restore-", dir=target.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as destination, canonical.open("rb") as source:
            shutil.copyfileobj(source, destination, length=4 * 1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        if temp.stat().st_size != row["bytes"] or sha256(temp) != row["sha256"]:
            raise RuntimeError("copied restore payload failed SHA/size verification")
        os.chown(temp, row["uid"], row["gid"])
        os.chmod(temp, stat.S_IMODE(int(row["mode_octal"], 8)))
        os.utime(temp, ns=(row["atime_ns"], row["mtime_ns"]))
        with temp.open("rb") as stream:
            os.fsync(stream.fileno())
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"refusing to overwrite existing restore path: {target}")
        os.rename(temp, target)
        parent_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        restored = target.stat()
        if (
            target.stat().st_size != row["bytes"]
            or sha256(target) != row["sha256"]
            or restored.st_uid != row["uid"]
            or restored.st_gid != row["gid"]
            or stat.S_IMODE(restored.st_mode) != int(row["mode_octal"], 8)
            or restored.st_mtime_ns != row["mtime_ns"]
        ):
            raise RuntimeError("restored file failed final byte or metadata verification")
        print(json.dumps({"status": "restored_verified", "duplicate_path": duplicate_path, "canonical_path": row["canonical_path"], "sha256": row["sha256"], "bytes": row["bytes"]}, sort_keys=True))
    finally:
        if temp.exists():
            temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("duplicate_path", help="repository-relative path recorded in polymesh-dedup-plan.json")
    args = parser.parse_args()
    restore(args.duplicate_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
