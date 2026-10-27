#!/usr/bin/env python3
"""Safely restore one deduplicated I4F static mesh file."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import stat
from pathlib import Path
from typing import Any

CHUNK = 4 * 1024 * 1024
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def checked_relative(root: Path, raw: str) -> Path:
    """Return a confined lexical path, refusing symlinks in existing components."""
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError(f"unsafe relative path: {raw}")
    root = root.resolve(strict=True)
    lexical = root / rel
    current = root
    for part in rel.parts:
        current = current / part
        try:
            current.lstat()
        except FileNotFoundError:
            continue
        if current.is_symlink():
            raise ValueError(f"symlink component is not allowed: {raw}")
    resolved = lexical.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path escapes restore root: {raw}")
    return lexical


def _open_dir_chain(root: Path, parts: tuple[str, ...], *, create: bool = False) -> int:
    """Open a directory chain from root without following symlink components."""
    flags = os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW
    fd = os.open(root, flags)
    try:
        for part in parts:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o755, dir_fd=fd)
                except FileExistsError:
                    pass
                next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_canonical(root: Path, relative: Path) -> tuple[int, int, os.stat_result]:
    parent_fd = _open_dir_chain(root, relative.parts[:-1])
    try:
        fd = os.open(relative.name, os.O_RDONLY | O_NOFOLLOW, dir_fd=parent_fd)
        before = os.fstat(fd)
        named = os.stat(relative.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or not stat.S_ISREG(named.st_mode):
            raise ValueError("retained canonical copy is not a regular file")
        if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
            raise RuntimeError("canonical path changed while it was opened")
        return parent_fd, fd, before
    except BaseException:
        os.close(parent_fd)
        raise


def _hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        block = os.read(fd, CHUNK)
        if not block:
            break
        digest.update(block)
    return digest.hexdigest()


def _canonical_record_checks(st: os.stat_result, row: dict[str, Any]) -> dict[str, bool]:
    return {
        "size": st.st_size == row["bytes"],
        "mode": stat.S_IMODE(st.st_mode) == row["canonical_mode"],
        "uid": st.st_uid == row["canonical_uid"],
        "gid": st.st_gid == row["canonical_gid"],
        "mtime_ns": st.st_mtime_ns == row["canonical_mtime_ns"],
    }


def _same_source_identity(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )


def restore(manifest_path: Path, root: Path, duplicate_path: str) -> dict[str, Any]:
    root = root.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "i4f-reversible-duplicate-polymesh-manifest/v1":
        raise ValueError("unexpected restore manifest schema")

    journal_path = checked_relative(root, manifest["journal_path"])
    unlinked_paths: set[str] = set()
    if journal_path.is_file():
        for line in journal_path.read_text().splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event") == "mesh_file_unlinked_after_exact_duplicate_verification":
                unlinked_paths.add(event.get("duplicate_path"))
    rows = [
        row
        for row in manifest.get("records", [])
        if row.get("duplicate_path") == duplicate_path and duplicate_path in unlinked_paths
    ]
    if len(rows) != 1:
        raise ValueError(f"expected one unlinked record for {duplicate_path}, found {len(rows)}")
    row = rows[0]
    source = checked_relative(root, row["canonical_path"])
    target = checked_relative(root, duplicate_path)

    source_parent_fd, source_fd, source_before = _open_canonical(root, source.relative_to(root))
    target_parent_fd: int | None = None
    temp_name: str | None = None
    temp_fd: int | None = None
    linked = False
    complete = False
    temp_stat: os.stat_result | None = None
    try:
        before_checks = _canonical_record_checks(source_before, row)
        if not all(before_checks.values()):
            raise RuntimeError(f"retained canonical metadata mismatch: {before_checks}")
        source_sha = _hash_fd(source_fd)
        if source_sha != row["sha256"]:
            raise RuntimeError("retained canonical copy does not match recorded SHA-256")

        target_parent_fd = _open_dir_chain(root, target.relative_to(root).parts[:-1], create=True)
        try:
            os.stat(target.name, dir_fd=target_parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(f"refusing to overwrite existing restore path: {target}")

        for _ in range(20):
            candidate = f".{target.name}.restore-{secrets.token_hex(8)}"
            try:
                temp_fd = os.open(
                    candidate,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | O_NOFOLLOW,
                    0o600,
                    dir_fd=target_parent_fd,
                )
                temp_name = candidate
                break
            except FileExistsError:
                continue
        if temp_fd is None or temp_name is None:
            raise FileExistsError("could not allocate a unique temporary restore file")

        os.lseek(source_fd, 0, os.SEEK_SET)
        with (
            os.fdopen(os.dup(source_fd), "rb") as input_stream,
            os.fdopen(os.dup(temp_fd), "wb") as output_stream,
        ):
            shutil.copyfileobj(input_stream, output_stream, length=CHUNK)
            output_stream.flush()
            os.fsync(output_stream.fileno())

        if os.fstat(temp_fd).st_size != row["bytes"] or _hash_fd(temp_fd) != row["sha256"]:
            raise RuntimeError("temporary restore copy failed SHA/size verification")

        source_after = os.fstat(source_fd)
        source_named_after = os.stat(source.name, dir_fd=source_parent_fd, follow_symlinks=False)
        after_checks = _canonical_record_checks(source_after, row)
        if (
            not all(after_checks.values())
            or not _same_source_identity(source_before, source_after)
            or (source_after.st_dev, source_after.st_ino)
            != (source_named_after.st_dev, source_named_after.st_ino)
            or _hash_fd(source_fd) != row["sha256"]
        ):
            raise RuntimeError("retained canonical changed during restore; source left untouched")

        os.fchown(temp_fd, row["uid"], row["gid"])
        os.fchmod(temp_fd, stat.S_IMODE(row["mode"]))
        os.utime(temp_fd, ns=(row["atime_ns"], row["mtime_ns"]))
        os.fsync(temp_fd)
        temp_stat = os.fstat(temp_fd)

        try:
            os.link(
                temp_name,
                target.name,
                src_dir_fd=target_parent_fd,
                dst_dir_fd=target_parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise FileExistsError(f"refusing to overwrite existing restore path: {target}") from exc
        linked = True
        os.unlink(temp_name, dir_fd=target_parent_fd)
        temp_name = None
        os.fsync(target_parent_fd)

        final = os.stat(target.name, dir_fd=target_parent_fd, follow_symlinks=False)
        checks = {
            "same_inode_as_verified_copy": (final.st_dev, final.st_ino)
            == (temp_stat.st_dev, temp_stat.st_ino),
            "regular_file": stat.S_ISREG(final.st_mode),
            "size_bytes": final.st_size == row["bytes"],
            "uid": final.st_uid == row["uid"],
            "gid": final.st_gid == row["gid"],
            "mode": stat.S_IMODE(final.st_mode) == stat.S_IMODE(row["mode"]),
            "atime_ns": final.st_atime_ns == row["atime_ns"],
            "mtime_ns": final.st_mtime_ns == row["mtime_ns"],
        }
        if not all(checks.values()):
            raise RuntimeError(f"restored target failed final metadata verification: {checks}")

        complete = True
        return {
            "status": "restored_verified",
            "duplicate_path": duplicate_path,
            "canonical_path": row["canonical_path"],
            "sha256": row["sha256"],
            "bytes": row["bytes"],
            "mode": stat.S_IMODE(row["mode"]),
            "uid": row["uid"],
            "gid": row["gid"],
            "mtime_ns": row["mtime_ns"],
            "canonical_device_note": "historical manifest device is retained as provenance and is not required to match this host",
            "canonical_atime_note": "canonical atime is OS-managed and is never changed by this helper",
            "destination": str(target),
        }
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        if temp_name is not None and target_parent_fd is not None:
            try:
                os.unlink(temp_name, dir_fd=target_parent_fd)
            except FileNotFoundError:
                pass
        if linked and not complete and target_parent_fd is not None and temp_stat is not None:
            try:
                target_stat = os.stat(target.name, dir_fd=target_parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (target_stat.st_dev, target_stat.st_ino) == (temp_stat.st_dev, temp_stat.st_ino):
                    os.unlink(target.name, dir_fd=target_parent_fd)
                    os.fsync(target_parent_fd)
        if target_parent_fd is not None:
            os.close(target_parent_fd)
        os.close(source_fd)
        os.close(source_parent_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--path", required=True, help="repository-relative original duplicate path")
    args = parser.parse_args()
    result = restore(args.manifest, args.root, args.path)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
