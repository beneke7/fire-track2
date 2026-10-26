#!/usr/bin/env python3
"""Reconstruct the captured DCEC source tree from the frozen public snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BASE_RELATIVE = Path("solvers/i4f_frozen_sp")
VARIANT_RELATIVE = BASE_RELATIVE / "variants/dcec"
SCHEMA = "i4f-executed-dcec-source-variant/v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative_path(value: str) -> PurePosixPath:
    """Parse a portable relative source path without traversal components."""
    if not value or "\\" in value:
        raise ValueError(f"invalid portable relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"path must be relative and contain no traversal: {value!r}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def canonical_file_manifest_sha256(files: list[dict[str, str]]) -> str:
    ordered = sorted(files, key=lambda item: item["path"])
    payload = json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def prepare_source_tree(output_dir: Path, repo_root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Copy and verify the exact variant without modifying the base snapshot."""
    repo_root = repo_root.resolve(strict=True)
    base_root = (repo_root / BASE_RELATIVE).resolve(strict=True)
    variant_root = (repo_root / VARIANT_RELATIVE).resolve(strict=True)
    base_manifest_path = base_root / "source-manifest.json"
    variant_manifest_path = variant_root / "variant-manifest.json"
    if not base_manifest_path.is_file() or not variant_manifest_path.is_file():
        raise ValueError("base or DCEC variant manifest is missing")

    base_manifest_bytes = base_manifest_path.read_bytes()
    variant_manifest = _read_json(variant_manifest_path)
    if variant_manifest.get("schema") != SCHEMA:
        raise ValueError("unsupported DCEC variant manifest schema")
    expected_base_manifest_sha = variant_manifest.get("base_snapshot", {}).get("manifest_sha256")
    if sha256_file(base_manifest_path) != expected_base_manifest_sha:
        raise ValueError("public base source manifest hash does not match the frozen variant")

    base_manifest = json.loads(base_manifest_bytes)
    base_records = base_manifest.get("files")
    target_records = variant_manifest.get("files")
    if not isinstance(base_records, list) or not isinstance(target_records, list):
        raise ValueError("base and variant manifests must contain file lists")

    base_by_path: dict[str, str] = {}
    for item in base_records:
        rel = safe_relative_path(item["path"]).as_posix()
        if rel in base_by_path:
            raise ValueError(f"duplicate base manifest path: {rel}")
        base_by_path[rel] = item["sha256"]

    target_by_path: dict[str, str] = {}
    for item in target_records:
        rel = safe_relative_path(item["path"]).as_posix()
        if rel in target_by_path:
            raise ValueError(f"duplicate variant manifest path: {rel}")
        target_by_path[rel] = item["sha256"]
    if set(base_by_path) != set(target_by_path):
        raise ValueError("variant file list must exactly match the base source manifest")

    overrides: dict[str, tuple[Path, str]] = {}
    for item in variant_manifest.get("overrides", []):
        rel = safe_relative_path(item["path"]).as_posix()
        override_rel = safe_relative_path(item["override_file"])
        if rel not in base_by_path or rel in overrides:
            raise ValueError(f"invalid or duplicate override target: {rel}")
        override_path = (variant_root / Path(*override_rel.parts)).resolve(strict=True)
        if not _inside(override_path, variant_root) or not override_path.is_file():
            raise ValueError(f"override escapes variant directory or is not a file: {rel}")
        if item.get("base_sha256") != base_by_path[rel]:
            raise ValueError(f"override base hash disagrees with base manifest: {rel}")
        override_sha = sha256_file(override_path)
        if override_sha != item.get("target_sha256") or override_sha != target_by_path[rel]:
            raise ValueError(f"override hash does not match target manifest: {rel}")
        overrides[rel] = (override_path, override_sha)

    if canonical_file_manifest_sha256(target_records) != variant_manifest.get(
        "canonical_file_manifest_sha256"
    ):
        raise ValueError("canonical variant file-manifest hash mismatch")

    for rel, base_sha in base_by_path.items():
        source_path = (base_root / Path(*safe_relative_path(rel).parts)).resolve(strict=True)
        if not _inside(source_path, base_root) or not source_path.is_file():
            raise ValueError(f"base source path escapes snapshot or is not a file: {rel}")
        source_sha = sha256_file(source_path)
        expected = overrides[rel][1] if rel in overrides else base_sha
        if source_sha != base_sha:
            raise ValueError(f"public base source hash mismatch: {rel}")
        if target_by_path[rel] != expected:
            raise ValueError(f"unexpected variant change outside declared override: {rel}")

    destination = output_dir.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing output path: {destination}")
    if (
        destination == repo_root
        or _inside(destination, base_root)
        or _inside(base_root, destination)
    ):
        raise ValueError("output path must not overlap the frozen public solver snapshot")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()

    try:
        for rel, target_sha in target_by_path.items():
            relative = Path(*safe_relative_path(rel).parts)
            source_path = overrides[rel][0] if rel in overrides else base_root / relative
            target_path = destination / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            if sha256_file(target_path) != target_sha:
                raise ValueError(f"copied source hash mismatch: {rel}")
    except Exception:
        # Do not leave a partial tree that might be mistaken for a valid build input.
        shutil.rmtree(destination)
        raise

    actual_files = sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    )
    if actual_files != sorted(target_by_path):
        shutil.rmtree(destination)
        raise ValueError("prepared output contains missing or extra files")

    return {
        "schema": "i4f-dcec-source-preparation-result/v1",
        "status": "source_tree_prepared_and_hash_verified",
        "output_dir": str(destination),
        "file_count": len(actual_files),
        "override_count": len(overrides),
        "canonical_file_manifest_sha256": variant_manifest["canonical_file_manifest_sha256"],
        "variant_manifest_sha256": sha256_file(variant_manifest_path),
        "source_manifest_sha256": expected_base_manifest_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="new directory for the verified source tree (must not already exist)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository root containing solvers/i4f_frozen_sp (default: script's repository)",
    )
    args = parser.parse_args()
    result = prepare_source_tree(args.output_dir, args.repo_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
