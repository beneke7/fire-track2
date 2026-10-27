#!/usr/bin/env python3
"""Reconstruct the published v3 source from the public physical-alpha base."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_entries(root: Path, entries: list[dict[str, object]], label: str) -> None:
    expected = {str(entry["path"]): entry for entry in entries}
    actual_paths = sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())
    if set(actual_paths) != set(expected):
        raise ValueError(
            f"{label} path mismatch: missing={sorted(set(expected) - set(actual_paths))}, "
            f"extra={sorted(set(actual_paths) - set(expected))}"
        )
    for relative, entry in expected.items():
        path = root / relative
        if path.stat().st_size != int(entry["bytes"]):
            raise ValueError(f"{label} byte count mismatch: {relative}")
        if sha256(path) != str(entry["sha256"]):
            raise ValueError(f"{label} SHA256 mismatch: {relative}")


def apply_patch(patch_file: Path, cwd: Path) -> None:
    result = subprocess.run(
        ["patch", "--batch", "--forward", "-p1", "-i", str(patch_file)],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"patch failed ({result.returncode}): {result.stdout}{result.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    packet = repo / "results/summaries/i4f_20261025/alpha-mass-budget-observer"
    source_manifest = json.loads((packet / "source-manifest.json").read_text())
    base = source_manifest["base"]
    parent = repo / str(base["parent_source_root"])
    parent_manifest_path = repo / str(base["parent_manifest"])
    parent_manifest = json.loads(parent_manifest_path.read_text())
    if sha256(parent_manifest_path) != base["parent_manifest_sha256"]:
        raise ValueError("Public parent manifest hash mismatch")
    if len(parent_manifest["files"]) != int(base["parent_file_count"]):
        raise ValueError("Public parent source count mismatch")
    check_entries(parent, parent_manifest["files"], "public parent")

    physical_patch = repo / str(base["physical_alpha_patch"])
    physical_manifest_path = repo / str(base["physical_alpha_manifest"])
    if sha256(physical_patch) != base["physical_alpha_patch_sha256"]:
        raise ValueError("Physical-alpha patch hash mismatch")
    if sha256(physical_manifest_path) != base["physical_alpha_manifest_sha256"]:
        raise ValueError("Physical-alpha source manifest hash mismatch")
    physical_manifest = json.loads(physical_manifest_path.read_text())
    physical_entries = physical_manifest["source_entries"]
    if len(physical_entries) != int(base["physical_alpha_selected_file_count"]):
        raise ValueError("Physical-alpha selected-file count mismatch")
    expected_physical = {
        entry["path"]: (entry["bytes"], entry["sha256"])
        for entry in base["physical_alpha_selected_files"]
    }
    actual_physical = {
        entry["path"]: (entry["bytes"], entry["sha256"]) for entry in physical_entries
    }
    if expected_physical != actual_physical:
        raise ValueError("Physical-alpha file manifest mismatch")

    direct = packet / str(source_manifest["direct_observer_v3_delta"]["patch"])
    if sha256(direct) != source_manifest["direct_observer_v3_delta"]["patch_sha256"]:
        raise ValueError("Direct v3 patch hash mismatch")
    target = source_manifest["target"]["target_files"]
    if len(target) != int(source_manifest["target"]["target_file_count"]):
        raise ValueError("Target file count mismatch")

    with tempfile.TemporaryDirectory(prefix="i4f-v3-source-verify-") as temporary:
        temp = Path(temporary)
        full = temp / "parent"
        shutil.copytree(parent, full, symlinks=True)
        apply_patch(physical_patch, full)
        selected = temp / "physical-alpha"
        selected.mkdir()
        for entry in physical_entries:
            src = full / entry["path"]
            dst = selected / entry["path"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        check_entries(selected, physical_entries, "physical-alpha source")
        apply_patch(direct, selected)
        check_entries(selected, target, "v3 source target")

    print(
        json.dumps(
            {
                "status": "verified",
                "public_parent_files": len(parent_manifest["files"]),
                "physical_alpha_files": len(physical_entries),
                "direct_v3_patch_sha256": sha256(direct),
                "v3_target_files": len(target),
                "temporary_tree_cleaned": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
