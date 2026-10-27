#!/usr/bin/env python3
"""Restore selected I4F logs from a recent closed-log recovery manifest.

The default destination is a fresh temporary directory. The helper restores one
explicitly selected source path; restoring every record requires ``--all``.
It validates compressed and decompressed hashes and sizes, never replaces an
existing destination, and leaves archive payloads untouched. Only the recorded
file mode and modification time are restored; ownership, xattrs, and atime were
not recorded and are not reconstructed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "i4f-recent-closed-log-recovery/v1"
CHUNK_BYTES = 1 << 20


def absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def no_symlink_components(path: Path, *, allow_missing: bool = False) -> Path:
    """Return a lexical absolute path after rejecting symlinks in its parents."""
    path = absolute(path)
    cursor = Path(path.anchor)
    missing = False
    for part in path.parts[1:]:
        cursor = cursor / part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            if not allow_missing:
                raise
            missing = True
            continue
        if missing:
            raise RuntimeError(f"path reappeared below a missing component: {cursor}")
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"symlink path component refused: {cursor}")
    return path


def checked_relative(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"unsafe {label}: {value!r}")
    parts = value.split("/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe {label}: {value!r}")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or not parsed.parts:
        raise ValueError(f"unsafe {label}: {value!r}")
    return Path(*parsed.parts)


def open_readonly(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOATIME", 0)
    try:
        return os.open(path, flags)
    except PermissionError:
        # Some filesystems permit reading but not O_NOATIME for this caller.
        return os.open(path, flags & ~getattr(os, "O_NOATIME", 0))


def sha256_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    fd = open_readonly(path)
    with os.fdopen(fd, "rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def file_identity(path: Path) -> tuple[int, int, int, int, int]:
    info = path.lstat()
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        stat.S_IMODE(info.st_mode),
    )


def prepare_repo_root(path: Path) -> Path:
    root = no_symlink_components(path)
    if not root.is_dir():
        raise NotADirectoryError(root)
    return root


def prepare_destination_root(path: Path) -> Path:
    root = no_symlink_components(path, allow_missing=True)
    if root.exists():
        if not root.is_dir():
            raise NotADirectoryError(root)
        return no_symlink_components(root)
    parent = root.parent
    if not parent.is_dir():
        raise NotADirectoryError(parent)
    no_symlink_components(parent)
    root.mkdir(mode=0o755)
    return no_symlink_components(root)


def safe_archive(repo_root: Path, relative: str) -> Path:
    rel = checked_relative(relative, "archive path")
    path = repo_root / rel
    cursor = repo_root
    for index, part in enumerate(rel.parts):
        cursor = cursor / part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            raise FileNotFoundError(f"archive component does not exist: {cursor}") from None
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"symlink in archive path: {cursor}")
        if index < len(rel.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise NotADirectoryError(cursor)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise RuntimeError(f"archive payload is not a regular file: {path}")
    try:
        path.resolve(strict=True).relative_to(repo_root.resolve(strict=True))
    except ValueError as exc:
        raise RuntimeError("archive path escapes repository root") from exc
    return path


def safe_target(destination_root: Path, relative: str) -> Path:
    rel = checked_relative(relative, "source path")
    root = no_symlink_components(destination_root)
    target = root / rel
    try:
        target.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"refusing to overwrite existing destination: {target}")

    cursor = root
    for part in rel.parts[:-1]:
        cursor = cursor / part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            try:
                cursor.mkdir(mode=0o755)
            except FileExistsError:
                pass
            info = cursor.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"symlink in destination path: {cursor}")
        if not stat.S_ISDIR(info.st_mode):
            raise NotADirectoryError(cursor)

    try:
        target.parent.resolve(strict=True).relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise RuntimeError("destination escapes destination root") from exc
    return target


def read_manifest(path: Path) -> dict[str, Any]:
    manifest_path = no_symlink_components(path)
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"unsupported manifest schema: {manifest.get('schema')!r}")
    if not isinstance(manifest.get("bundle"), str):
        raise ValueError("manifest has no bundle path")
    checked_relative(manifest["bundle"], "bundle path")
    if not isinstance(manifest.get("records"), list) or not manifest["records"]:
        raise ValueError("manifest has no recovery records")
    seen: set[str] = set()
    for record in manifest["records"]:
        if not isinstance(record, dict):
            raise ValueError("manifest record is not an object")
        source = record.get("source_path")
        checked_relative(source, "source path")
        if source in seen:
            raise ValueError(f"duplicate source path in manifest: {source}")
        seen.add(source)
        checked_relative(record.get("archive_path"), "archive path")
        for key in ("source_sha256", "decompressed_sha256", "archive_sha256"):
            digest = record.get(key)
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError(f"invalid {key} for {source}")
            try:
                int(digest, 16)
            except ValueError as exc:
                raise ValueError(f"invalid {key} for {source}") from exc
        for key in (
            "source_bytes",
            "decompressed_bytes",
            "archive_bytes",
        ):
            if not isinstance(record.get(key), int) or record[key] < 0:
                raise ValueError(f"invalid {key} for {source}")
        metadata = record.get("source_metadata")
        if not isinstance(metadata, dict):
            raise ValueError(f"missing source metadata for {source}")
        if not isinstance(metadata.get("mode"), int) or not stat.S_ISREG(metadata["mode"]):
            raise ValueError(f"invalid recorded mode for {source}")
        if not isinstance(metadata.get("mtime_ns"), int):
            raise ValueError(f"invalid recorded mtime for {source}")
    return manifest


def validate_record(record: dict[str, Any]) -> None:
    source_bytes = record["source_bytes"]
    if record["decompressed_bytes"] != source_bytes:
        raise RuntimeError(f"manifest decompressed size disagrees with source: {record['source_path']}")
    if record["decompressed_sha256"] != record["source_sha256"]:
        raise RuntimeError(f"manifest decompressed hash disagrees with source: {record['source_path']}")
    if record["source_metadata"].get("size_bytes") != source_bytes:
        raise RuntimeError(f"manifest metadata size disagrees with source: {record['source_path']}")


def make_temporary(target: Path) -> tuple[Path, int]:
    for _ in range(10):
        temporary = target.with_name(
            f".{target.name}.{os.getpid()}.{secrets.token_hex(8)}.restore-tmp"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            return temporary, os.open(temporary, flags, 0o600)
        except FileExistsError:
            continue
    raise FileExistsError(f"could not allocate exclusive temporary beside {target}")


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def restore_record(record: dict[str, Any], manifest: dict[str, Any], repo_root: Path,
                   destination_root: Path) -> Path:
    validate_record(record)
    archive_rel = checked_relative(record["archive_path"], "archive path")
    bundle_rel = checked_relative(manifest["bundle"], "bundle path")
    archive = safe_archive(repo_root, (bundle_rel / archive_rel).as_posix())
    archive_before = file_identity(archive)
    archive_sha, archive_bytes = sha256_path(archive)
    if (archive_sha, archive_bytes) != (record["archive_sha256"], record["archive_bytes"]):
        raise RuntimeError(f"archive hash/size mismatch: {record['archive_path']}")

    target = safe_target(destination_root, record["source_path"])
    # Recheck every destination component after safe_target created parents.
    target = safe_target(destination_root, record["source_path"])
    temporary, fd = make_temporary(target)
    try:
        with os.fdopen(fd, "wb") as output:
            with os.fdopen(open_readonly(archive), "rb") as compressed:
                result = subprocess.run(
                    ["zstd", "-q", "-d", "-c", "-T1"],
                    stdin=compressed,
                    stdout=output,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=600,
                )
            output.flush()
            os.fsync(output.fileno())
        if result.returncode != 0:
            detail = result.stderr.decode(errors="replace")[-400:]
            raise RuntimeError(f"zstd decode failed: {detail}")

        content_sha, content_bytes = sha256_path(temporary)
        expected = (record["decompressed_sha256"], record["decompressed_bytes"])
        if (content_sha, content_bytes) != expected:
            raise RuntimeError(f"decompressed hash/size mismatch: {record['source_path']}")
        if (content_sha, content_bytes) != (record["source_sha256"], record["source_bytes"]):
            raise RuntimeError(f"source hash/size mismatch: {record['source_path']}")

        metadata = record["source_metadata"]
        os.chmod(temporary, stat.S_IMODE(metadata["mode"]), follow_symlinks=False)
        current_atime_ns = temporary.stat().st_atime_ns
        os.utime(
            temporary,
            ns=(current_atime_ns, metadata["mtime_ns"]),
            follow_symlinks=False,
        )
        metadata_fd = os.open(temporary, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(metadata_fd)
        finally:
            os.close(metadata_fd)

        temp_info = temporary.lstat()
        for key, actual in (
            ("size_bytes", temp_info.st_size),
            ("mode", stat.S_IMODE(temp_info.st_mode)),
            ("mtime_ns", temp_info.st_mtime_ns),
        ):
            expected_value = (
                stat.S_IMODE(metadata["mode"]) if key == "mode" else metadata[key]
            )
            if actual != expected_value:
                raise RuntimeError(f"restored metadata mismatch for {key}: {record['source_path']}")

        if file_identity(archive) != archive_before:
            raise RuntimeError(f"archive metadata changed during restore: {record['archive_path']}")
        # Hard-link installation is atomic and fails if another file appears.
        os.link(temporary, target, follow_symlinks=False)
        temporary.unlink()
        fsync_directory(target.parent)
        return target
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--destination-root",
        type=Path,
        help="restore root (default: a new temporary directory)",
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--source-path", help="restore exactly this manifest source path")
    selection.add_argument("--all", action="store_true", help="restore every manifest record")
    args = parser.parse_args()

    repo_root = prepare_repo_root(args.repo_root)
    manifest = read_manifest(args.manifest)
    if args.destination_root is None:
        destination_root = Path(tempfile.mkdtemp(prefix="i4f-recent-logs-restore-"))
        no_symlink_components(destination_root)
    else:
        destination_root = prepare_destination_root(args.destination_root)

    records = manifest["records"]
    if args.source_path is not None:
        checked_relative(args.source_path, "source path")
        selected = [record for record in records if record["source_path"] == args.source_path]
        if len(selected) != 1:
            raise ValueError(
                f"expected exactly one record for {args.source_path!r}, found {len(selected)}"
            )
    else:
        selected = records

    print(f"DESTINATION_ROOT={destination_root}")
    for record in selected:
        restored = restore_record(record, manifest, repo_root, destination_root)
        print(f"RESTORED={restored}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RESTORE_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
