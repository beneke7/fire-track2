#!/usr/bin/env python3
"""Verify the checksummed restart-history evidence packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

PACKET = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify() -> int:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    expected = {row["path"]: row for row in manifest["files"]}
    actual = {
        path.relative_to(PACKET).as_posix(): path
        for path in PACKET.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if set(actual) != set(expected):
        raise RuntimeError(
            f"packet file set mismatch: missing={sorted(set(expected) - set(actual))}, "
            f"unmanifested={sorted(set(actual) - set(expected))}"
        )
    for relative, path in actual.items():
        row = expected[relative]
        if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise RuntimeError(f"packet file checksum mismatch: {relative}")

    source_checks = 0
    for variant in ("v7", "v8"):
        file_manifest = json.loads(
            (PACKET / "solver-source" / f"{variant}-source-files.json").read_text()
        )
        source_root = PACKET / "solver-source" / variant
        rows = file_manifest["files"]
        if len(rows) != file_manifest["file_count"]:
            raise RuntimeError(f"source manifest count mismatch: {variant}")
        for row in rows:
            path = source_root / row["path"]
            if (
                not path.is_file()
                or path.stat().st_size != row["bytes"]
                or sha256(path) != row["sha256"]
            ):
                raise RuntimeError(f"source file mismatch: {variant}/{row['path']}")
            source_checks += 1

    case_checks = 0
    for letter in ("A", "C", "D"):
        case_root = PACKET / "cases" / letter / "case"
        freeze = json.loads(
            (PACKET / "cases" / letter / "provenance" / "case-freeze.json").read_text()
        )
        if len(freeze["files"]) != freeze["static_file_count"]:
            raise RuntimeError(f"case static file count mismatch: {letter}")
        for row in freeze["files"]:
            path = case_root / row["path"]
            if (
                not path.is_file()
                or path.stat().st_size != row["bytes"]
                or sha256(path) != row["sha256"]
            ):
                raise RuntimeError(f"case static input mismatch: {letter}/{row['path']}")
            case_checks += 1

    source_inputs = json.loads((PACKET / "evidence/provenance/source-case-inputs.json").read_text())
    source_input_manifest = PACKET / "evidence/provenance/source-case-input-manifest.json"
    if sha256(source_input_manifest) != source_inputs["source_case_input_manifest_sha256"]:
        raise RuntimeError("copied source case input manifest hash mismatch")

    split = json.loads((PACKET / "evidence/provenance/split-checkpoint.json").read_text())
    for letter, branch in (("A", None), ("C", "arm-c-saved-dgdt"), ("D", None)):
        rows = split["branches"][branch]["checkpoint_files"] if branch else split["A_split_files"]
        time_root = PACKET / "cases" / letter / "case" / "0.10000000000000007"
        for row in rows:
            path = time_root / row["path"]
            if (
                not path.is_file()
                or path.stat().st_size != row["bytes"]
                or sha256(path) != row["sha256"]
            ):
                raise RuntimeError(f"split checkpoint mismatch: {letter}/{row['path']}")
            case_checks += 1

    for letter in ("A", "C", "D"):
        arm_root = PACKET / "cases" / letter
        status = json.loads((arm_root / "provenance/run-status.json").read_text())
        if status["exit_code"] != 0 or status["normal_End"] is not True:
            raise RuntimeError(f"captured run is not a normal End: {letter}")
        endpoint = arm_root / "case" / status["terminal_native_time_directory"]
        for field, expected_hash in status["endpoint_field_sha256"].items():
            path = endpoint / field
            if not path.is_file() or sha256(path) != expected_hash:
                raise RuntimeError(f"endpoint field mismatch: {letter}/{field}")
            case_checks += 1

    print(
        json.dumps(
            {
                "status": "verified",
                "packet_files": len(actual),
                "source_files": source_checks,
                "case_input_and_seed_files": case_checks,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(verify())
