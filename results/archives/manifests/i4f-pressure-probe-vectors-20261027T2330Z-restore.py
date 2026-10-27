#!/usr/bin/env python3
"""Restore one archived pressure-probe vector without overwriting a path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

CHUNK = 1 << 20


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def checked_rel(root: Path, raw: str) -> Path:
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError(f"unsafe relative path: {raw}")
    target = (root / rel).resolve(strict=False)
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes root: {raw}")
    return target


def restore(manifest_path: Path, archive_root: Path, destination_root: Path, source_path: str) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "i4f-pressure-probe-vector-restore-manifest/v1":
        raise ValueError("unexpected manifest schema")
    rows = [row for row in manifest.get("records", []) if row.get("source_path") == source_path and row.get("source_unlinked")]
    if len(rows) != 1:
        raise ValueError(f"expected one archived record for {source_path}, found {len(rows)}")
    row = rows[0]
    destination_root = destination_root.resolve(strict=True)
    target = checked_rel(destination_root, source_path)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing restore target: {target}")
    archive_root = archive_root.resolve(strict=True)
    archive = checked_rel(archive_root, row["archive_path"])
    if archive.is_symlink() or not archive.is_file():
        raise FileNotFoundError(f"archive is unavailable: {archive}")
    if archive.stat().st_size != row["archive_bytes"] or sha256(archive) != row["archive_sha256"]:
        raise RuntimeError("archive SHA/size mismatch")
    checked = subprocess.run(["zstd", "-q", "-t", str(archive)], capture_output=True, text=True, timeout=120)
    if checked.returncode:
        raise RuntimeError(f"zstd frame verification failed: {checked.stderr[-1000:]}")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Resolve after directory creation so a symlink introduced in a parent is rejected.
    target = checked_rel(destination_root, source_path)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing restore target: {target}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.restore-", dir=target.parent)
    temp = Path(temp_name)
    h = hashlib.sha256()
    size = 0
    try:
        proc = subprocess.Popen(["zstd", "-q", "-dc", str(archive)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdout is not None
        with os.fdopen(fd, "wb") as destination:
            for block in iter(lambda: proc.stdout.read(CHUNK), b""):
                destination.write(block)
                h.update(block)
                size += len(block)
            destination.flush()
            os.fsync(destination.fileno())
        stderr = proc.stderr.read() if proc.stderr else b""
        if proc.wait() != 0:
            raise RuntimeError(f"zstd decompression failed: {stderr[-1000:]!r}")
        if (h.hexdigest(), size) != (row["source_sha256"], row["source_bytes"]):
            raise RuntimeError("decompressed bytes do not match source SHA/size")
        os.chown(temp, row["uid"], row["gid"])
        os.chmod(temp, stat.S_IMODE(row["mode"]))
        os.utime(temp, ns=(row["atime_ns"], row["mtime_ns"]))
        # A hard-link publish is atomic and fails if another process created target.
        os.link(temp, target)
        temp.unlink()
        parent_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        st = target.stat()
        if (
            target.stat().st_size != row["source_bytes"]
            or sha256(target) != row["source_sha256"]
            or st.st_uid != row["uid"]
            or st.st_gid != row["gid"]
            or stat.S_IMODE(st.st_mode) != row["mode"]
            or st.st_mtime_ns != row["mtime_ns"]
        ):
            target.unlink()
            raise RuntimeError("restored file failed final byte or metadata verification")
        return {"status": "restored_verified", "source_path": source_path, "archive_path": row["archive_path"], "sha256": row["source_sha256"], "bytes": row["source_bytes"], "mode": row["mode"], "uid": row["uid"], "gid": row["gid"], "mtime_ns": row["mtime_ns"], "destination": str(target)}
    finally:
        if temp.exists():
            temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--destination-root", required=True, type=Path)
    parser.add_argument("--path", required=True, help="repository-relative source path recorded in the manifest")
    args = parser.parse_args()
    result = restore(args.manifest, args.archive_root, args.destination_root, args.path)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
