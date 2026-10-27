#!/usr/bin/env python3
"""Verify the published v3 source plus the one-parameter denominator-floor patch."""

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
    expected = {str(item["path"]): item for item in entries}
    actual = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
    if actual != set(expected):
        raise ValueError(
            f"{label} paths differ: missing={sorted(set(expected) - actual)}, "
            f"extra={sorted(actual - set(expected))}"
        )
    for relative, item in expected.items():
        path = root / relative
        if path.stat().st_size != int(item["bytes"]):
            raise ValueError(f"{label} byte count mismatch: {relative}")
        if sha256(path) != str(item["sha256"]):
            raise ValueError(f"{label} SHA256 mismatch: {relative}")


def apply_patch(patch_path: Path, cwd: Path) -> None:
    result = subprocess.run(
        ["patch", "--batch", "--forward", "-p1", "-i", str(patch_path)],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"patch failed ({result.returncode}): {result.stdout}{result.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional new JSON report path; existing paths are never overwritten",
    )
    args = parser.parse_args()
    packet = Path(__file__).resolve().parent
    repo = packet.parents[3]
    closure = json.loads((packet / "source-closure.json").read_text())
    controlled_entries = [
        entry
        for entry in closure["target_files"]
        if entry["path"] in {row["path"] for row in closure["controlled_files"]}
    ]
    check_entries(
        packet / closure["controlled_target_file_snapshot_root"],
        controlled_entries,
        "published controlled source snapshots",
    )
    v3_packet = repo / closure["published_v3_packet"]
    v3_manifest_path = v3_packet / "source-manifest.json"
    v3_manifest = json.loads(v3_manifest_path.read_text())
    if sha256(v3_manifest_path) != closure["published_v3_manifest_sha256"]:
        raise ValueError("published v3 source manifest hash mismatch")

    base = v3_manifest["base"]
    parent = repo / base["parent_source_root"]
    parent_manifest_path = repo / base["parent_manifest"]
    parent_manifest = json.loads(parent_manifest_path.read_text())
    if sha256(parent_manifest_path) != base["parent_manifest_sha256"]:
        raise ValueError("published immediate-parent manifest hash mismatch")
    check_entries(parent, parent_manifest["files"], "public immediate parent")

    physical_patch = repo / base["physical_alpha_patch"]
    physical_manifest_path = repo / base["physical_alpha_manifest"]
    if sha256(physical_patch) != base["physical_alpha_patch_sha256"]:
        raise ValueError("physical-alpha patch hash mismatch")
    if sha256(physical_manifest_path) != base["physical_alpha_manifest_sha256"]:
        raise ValueError("physical-alpha manifest hash mismatch")
    physical_manifest = json.loads(physical_manifest_path.read_text())
    selected_files = physical_manifest["source_entries"]
    if len(selected_files) != int(base["physical_alpha_selected_file_count"]):
        raise ValueError("physical-alpha selected source file count mismatch")

    v3_patch = v3_packet / v3_manifest["direct_observer_v3_delta"]["patch"]
    floor_patch = packet / closure["floor_patch"]
    if sha256(v3_patch) != v3_manifest["direct_observer_v3_delta"]["patch_sha256"]:
        raise ValueError("published v3 patch hash mismatch")
    if sha256(floor_patch) != closure["floor_patch_sha256"]:
        raise ValueError("floor patch hash mismatch")

    with tempfile.TemporaryDirectory(prefix="i4f-source-cutoff-verify-") as temp_name:
        temp = Path(temp_name)
        full = temp / "full-parent"
        shutil.copytree(parent, full, symlinks=True)
        apply_patch(physical_patch, full)

        selected = temp / "published-v3"
        selected.mkdir()
        for item in selected_files:
            src = full / str(item["path"])
            dst = selected / str(item["path"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        check_entries(selected, selected_files, "physical-alpha source")
        apply_patch(v3_patch, selected)
        v3_entries = v3_manifest["target"]["target_files"]
        check_entries(selected, v3_entries, "published v3 source")

        apply_patch(floor_patch, selected)
        target_entries = closure["target_files"]
        check_entries(selected, target_entries, "floor-patched source")

    report = {
        "schema": "i4f-source-cutoff-source-reconstruction/v1",
        "status": "verified",
        "public_parent_file_count": len(parent_manifest["files"]),
        "physical_alpha_file_count": len(selected_files),
        "published_v3_file_count": len(v3_entries),
        "floor_patched_file_count": len(target_entries),
        "published_v3_tree_digest_sha256": v3_manifest["target"]["target_tree_digest_sha256"],
        "floor_patch_sha256": sha256(floor_patch),
        "temporary_trees_removed": True,
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
