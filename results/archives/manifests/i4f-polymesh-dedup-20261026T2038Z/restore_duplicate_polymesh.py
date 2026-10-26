#!/usr/bin/env python3
"""Restore one duplicate mesh file by copying a retained canonical file."""

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
DEFAULT_PLAN = Path("results/archives/manifests/i4f-polymesh-dedup-20261026T2038Z/dedup-plan.json")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def checked_relative(raw: str) -> Path:
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe relative path in plan: {raw}")
    lexical = ROOT / relative
    resolved = lexical.resolve(strict=False)
    if resolved != ROOT and ROOT not in resolved.parents:
        raise ValueError(f"path escapes repository: {raw}")
    current = ROOT
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink component is not allowed in plan path: {raw}")
    return lexical


def restore(plan_path: Path, duplicate_path: str) -> dict[str, object]:
    plan = json.loads(plan_path.read_text())
    rows = [row for row in plan["planned_files"] if row["duplicate_path"] == duplicate_path]
    if len(rows) != 1:
        raise ValueError(f"expected exactly one row for {duplicate_path}, found {len(rows)}")
    row = rows[0]
    canonical = checked_relative(row["canonical_path"])
    target = checked_relative(row["duplicate_path"])
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing restore path: {target}")
    if canonical.is_symlink() or not canonical.is_file():
        raise FileNotFoundError(f"canonical source is not a regular file: {canonical}")
    if canonical.stat().st_size != row["bytes"] or sha256(canonical) != row["sha256"]:
        raise RuntimeError("canonical source does not match the plan SHA/size")

    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.restore-", dir=target.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as destination, canonical.open("rb") as source:
            shutil.copyfileobj(source, destination, length=4 * 1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        if temp.stat().st_size != row["bytes"] or sha256(temp) != row["sha256"]:
            raise RuntimeError("copied file failed SHA/size verification")
        os.chown(temp, row["uid"], row["gid"])
        os.chmod(temp, stat.S_IMODE(int(row["mode_octal"], 8)))
        os.utime(temp, ns=(row["atime_ns"], row["mtime_ns"]))
        fd = os.open(temp, os.O_RDONLY | getattr(os, "O_NOATIME", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        # Atomically fail if another process created target after the initial check.
        # This link is from the independent copied temp file, never from canonical.
        os.link(temp, target, follow_symlinks=False)
        temp.unlink()
        parent_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        final = target.stat()
        checks = {
            "size_bytes": final.st_size == row["bytes"],
            "uid": final.st_uid == row["uid"],
            "gid": final.st_gid == row["gid"],
            "mode": stat.S_IMODE(final.st_mode) == int(row["mode_octal"], 8),
            "atime_ns": final.st_atime_ns == row["atime_ns"],
            "mtime_ns": final.st_mtime_ns == row["mtime_ns"],
        }
        if not all(checks.values()):
            raise RuntimeError(f"restored metadata verification failed: {checks}")
        return {
            "status": "restored_verified",
            "duplicate_path": duplicate_path,
            "canonical_path": row["canonical_path"],
            "sha256": row["sha256"],
            "bytes": row["bytes"],
            "metadata_checks": checks,
            "install_method": "atomic no-clobber link from the independent copied temporary file, then temporary name removed",
            "ctime_ns_note": "ctime necessarily changes during copy/restore and is recorded for provenance, not restored",
        }
    finally:
        if temp.exists():
            temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "duplicate_path", help="repository-relative path recorded in the restore plan"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=DEFAULT_PLAN,
        help="plan JSON path relative to the repository root",
    )
    args = parser.parse_args()
    plan_path = checked_relative(str(args.plan))
    result = restore(plan_path, args.duplicate_path)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
