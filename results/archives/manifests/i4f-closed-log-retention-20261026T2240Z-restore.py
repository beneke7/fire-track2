#!/usr/bin/env python3
"""Restore one archived I4F solver log without overwriting an existing path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

CHUNK = 1 << 20


def digest(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    count = 0
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
            count += len(block)
    return h.hexdigest(), count


def safe_relative(value: str) -> PurePosixPath:
    rel = PurePosixPath(value)
    if rel.is_absolute() or not rel.parts or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError(f"unsafe relative path: {value!r}")
    return rel


def contained_path(root: Path, value: str) -> Path:
    rel = safe_relative(value)
    root = root.resolve(strict=True)
    target = root.joinpath(*rel.parts)
    # Keep the lexical target for no-symlink checks; resolve only to validate
    # that existing parent components cannot escape the selected root.
    resolved_parent = target.parent.resolve(strict=False)
    if resolved_parent != root and root not in resolved_parent.parents:
        raise ValueError(f"destination escapes root: {target}")
    cursor = root
    for part in rel.parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"refusing symlink parent: {cursor}")
    if target.is_symlink():
        raise ValueError(f"refusing symlink target: {target}")
    return target


def restore(manifest_path: Path, archive_root: Path, destination_root: Path, source_path: str) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "i4f-closed-solver-log-restore-manifest/v1":
        raise ValueError("unsupported restore manifest schema")
    matches = [row for row in manifest.get("records", []) if row.get("source_path") == source_path]
    if len(matches) != 1:
        raise ValueError(f"expected one manifest entry for {source_path!r}, found {len(matches)}")
    row: dict[str, Any] = matches[0]
    archive = contained_path(archive_root, row["archive_path"])
    destination = contained_path(destination_root, source_path)
    if not archive.is_file():
        raise FileNotFoundError(archive)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to overwrite {destination}")
    actual_archive_hash, _ = digest(archive)
    if actual_archive_hash != row["archive_sha256"]:
        raise ValueError(f"archive SHA256 mismatch: {actual_archive_hash}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Revalidate newly created parents and use an exclusive temporary file.
    destination = contained_path(destination_root, source_path)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{destination.name}.restore-", dir=destination.parent)
    tmp = Path(tmp_name)
    try:
        h = hashlib.sha256()
        count = 0
        with os.fdopen(fd, "wb") as out:
            proc = subprocess.Popen(["zstd", "-q", "-dc", str(archive)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert proc.stdout is not None
            for block in iter(lambda: proc.stdout.read(CHUNK), b""):
                h.update(block)
                out.write(block)
                count += len(block)
            stderr = proc.stderr.read() if proc.stderr else b""
            if proc.wait() != 0:
                raise RuntimeError(f"zstd restore failed: {stderr.decode(errors='replace')[-1000:]}")
            out.flush()
            os.fsync(out.fileno())
        if h.hexdigest() != row["source_sha256"] or count != row["size_bytes"]:
            raise ValueError(f"restored bytes do not match manifest: sha={h.hexdigest()} size={count}")
        if os.geteuid() == 0:
            os.chown(tmp, int(row["uid"]), int(row["gid"]))
        os.chmod(tmp, int(row["mode"]))
        os.utime(tmp, ns=(int(row["mtime_ns"]), int(row["mtime_ns"])))
        st = tmp.stat()
        if st.st_uid != int(row["uid"]) or st.st_gid != int(row["gid"]):
            raise PermissionError(f"cannot reproduce owner/group: {(st.st_uid, st.st_gid)} != {(row['uid'], row['gid'])}")
        # link(2) is an atomic no-replace install; unlike rename it cannot
        # replace a path that appeared after the earlier existence check.
        os.link(tmp, destination)
        tmp.unlink()
        dirfd = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        return destination
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True, help="root against which manifest archive_path values are resolved")
    parser.add_argument("--destination-root", type=Path, required=True, help="restore beneath this root; existing files are never overwritten")
    parser.add_argument("--path", required=True, help="exact original source_path from the manifest")
    args = parser.parse_args()
    restored = restore(args.manifest, args.archive_root, args.destination_root, args.path)
    print(restored)


if __name__ == "__main__":
    main()
