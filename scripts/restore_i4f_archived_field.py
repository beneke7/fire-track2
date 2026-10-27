#!/usr/bin/env python3
"""Restore one or more fields from an I4F aerial retention member manifest.

Each payload is checked against its compressed SHA256 and the original byte
SHA256 before an atomic no-clobber install. Existing files are never replaced.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CHUNK_BYTES = 4 * 1024 * 1024


def sha256_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    flags = os.O_RDONLY | getattr(os, "O_NOATIME", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def checked_relative(value: str, label: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe {label}: {value!r}")
    return Path(*path.parts)


def safe_target(root: Path, relative: str) -> Path:
    rel = checked_relative(relative, "source path")
    root = root.resolve(strict=True)
    target = root / rel
    cursor = root
    for part in rel.parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RuntimeError(f"symlink in destination path: {cursor}")
        if cursor.exists() and not cursor.is_dir():
            raise RuntimeError(f"destination parent is not a directory: {cursor}")
    if target.is_symlink():
        raise RuntimeError(f"symlink destination refused: {target}")
    try:
        target.parent.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise RuntimeError("destination escapes destination root") from exc
    return target


def safe_archive(repo_root: Path, relative: str) -> Path:
    rel = checked_relative(relative, "archive path")
    root = repo_root.resolve(strict=True)
    path = root / rel
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RuntimeError(f"symlink in archive path: {cursor}")
    try:
        path.resolve(strict=True).relative_to(root)
    except ValueError as exc:
        raise RuntimeError("archive path escapes repository root") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def read_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != "i4f-lossless-aerial-intermediate-fields-members/v1":
        raise ValueError(f"unsupported archive manifest schema: {manifest.get('schema')!r}")
    if not isinstance(manifest.get("members"), list):
        raise ValueError("manifest has no member list")
    return manifest


def restore_member(record: dict[str, Any], destination_root: Path, repo_root: Path) -> Path:
    archive = safe_archive(repo_root, record["archive_path"])
    archive_sha, archive_bytes = sha256_path(archive)
    if (archive_sha, archive_bytes) != (record["archive_sha256"], record["archive_bytes"]):
        raise RuntimeError(f"archive hash/size mismatch: {record['archive_path']}")

    target = safe_target(destination_root, record["source_path"])
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target = safe_target(destination_root, record["source_path"])
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")

    temporary = target.with_name(target.name + f".{os.getpid()}.restore-tmp")
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            result = subprocess.run(
                ["zstd", "-q", "-d", "-c", "--", str(archive)],
                stdout=stream,
                stderr=subprocess.PIPE,
                check=False,
            )
            stream.flush()
            os.fsync(stream.fileno())
        if result.returncode != 0:
            raise RuntimeError(f"zstd decode failed: {result.stderr.decode(errors='replace')}")
        content_sha, content_bytes = sha256_path(temporary)
        if (content_sha, content_bytes) != (record["source_sha256"], record["source_bytes"]):
            raise RuntimeError(f"restored content hash/size mismatch: {record['source_path']}")

        metadata = record["metadata"]
        if os.geteuid() == 0:
            os.chown(temporary, metadata["uid"], metadata["gid"])
        elif (os.getuid(), os.getgid()) != (metadata["uid"], metadata["gid"]):
            raise RuntimeError("cannot preserve archived owner/group without privilege")
        os.chmod(temporary, metadata["mode"])
        for name, value in metadata["xattrs_base64"].items():
            os.setxattr(temporary, name, base64.b64decode(value), follow_symlinks=False)
        os.utime(temporary, ns=(metadata["atime_ns"], metadata["mtime_ns"]))

        # Hard-link install is atomic and fails with EEXIST if a target appears
        # after the precheck. The archived payload is never linked to the target.
        os.link(temporary, target, follow_symlinks=False)
        temporary.unlink()
        directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

        restored = target.lstat()
        for key, actual in (
            ("size_bytes", restored.st_size),
            ("mode", stat.S_IMODE(restored.st_mode)),
            ("uid", restored.st_uid),
            ("gid", restored.st_gid),
            ("atime_ns", restored.st_atime_ns),
            ("mtime_ns", restored.st_mtime_ns),
        ):
            if actual != metadata[key]:
                target.unlink()
                raise RuntimeError(f"restored metadata mismatch for {key}")
        actual_xattrs = {}
        for name in sorted(os.listxattr(target, follow_symlinks=False)):
            actual_xattrs[name] = base64.b64encode(
                os.getxattr(target, name, follow_symlinks=False)
            ).decode("ascii")
        if actual_xattrs != metadata["xattrs_base64"]:
            target.unlink()
            raise RuntimeError("restored metadata mismatch for xattrs")
        return target
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--destination-root", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--source-path", help="restore exactly this archived repository-relative path"
    )
    selection.add_argument(
        "--all", action="store_true", help="restore every manifest member without overwriting"
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    manifest = read_manifest(args.manifest)
    members = manifest["members"]
    if args.source_path is not None:
        matches = [member for member in members if member["source_path"] == args.source_path]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one manifest member for {args.source_path!r}, found {len(matches)}"
            )
        selected = matches
    else:
        selected = members
    for record in selected:
        print(restore_member(record, args.destination_root, args.repo_root))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RESTORE_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
