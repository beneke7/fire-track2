#!/usr/bin/env python3
"""Verify and stage the exact, empty dry_four diagnostic input triplet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Sequence

CASE_ID = "dry_four"
INPUTS = {
    "dns.in": "929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0",
    "source-boundary.in": "f14d5e44d14928e5c3db0b4158e9ff7122aec64ac591fc8ea2fea9ce5df154e0",
    "vof.in": "2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54",
}


def _read_exact_inputs(source: Path) -> tuple[dict[str, bytes], dict[str, list[list[str]]]]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("case source must be a real directory, not a symlink")
    entries = sorted(source.iterdir(), key=lambda path: path.name)
    if [path.name for path in entries] != sorted(INPUTS):
        raise ValueError("case directory must contain exactly the three allowlisted files")

    payloads: dict[str, bytes] = {}
    tokens: dict[str, list[list[str]]] = {}
    for name, expected_hash in INPUTS.items():
        path = source / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f"{name} must be a regular, singly linked file")
        data = path.read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"{name} SHA-256 mismatch: {actual_hash}")
        if not data.endswith(b"\n") or b"\r" in data or data.startswith(b"\xef\xbb\xbf"):
            raise ValueError(f"{name} must be ASCII with LF records and one final LF")
        try:
            lines = data.decode("ascii").splitlines()
        except UnicodeDecodeError as exc:
            raise ValueError(f"{name} is not ASCII") from exc
        if not lines or any(not line.strip() for line in lines):
            raise ValueError(f"{name} has a blank record")
        parsed = []
        for line in lines:
            record = line.split("!", 1)[0].strip()
            parsed.append(record.split())
        payloads[name] = data
        tokens[name] = parsed

    _check_dry_four_semantics(tokens)
    return payloads, tokens


def _at(records: list[list[str]], index: int, expected: Sequence[str], label: str) -> None:
    if index >= len(records) or records[index] != list(expected):
        raise ValueError(f"{label} does not match the frozen dry_four relation")


def _check_dry_four_semantics(tokens: dict[str, list[list[str]]]) -> None:
    dns = tokens["dns.in"]
    source = tokens["source-boundary.in"]
    vof = tokens["vof.in"]
    if len(dns) != 29 or len(source) != 9 or len(vof) != 8:
        raise ValueError("dry_four record counts differ from the frozen fixture")
    _at(dns, 0, ("160", "84", "40"), "DNS grid")
    _at(dns, 1, ("4.0", "2.1", "1.0"), "DNS domain")
    _at(dns, 3, ("0.2", "1.0e-4"), "DNS timestep")
    _at(dns, 4, ("T",), "constant-step flag")
    _at(dns, 10, ("14", "0.0014", "1.0"), "DNS horizon")
    _at(dns, 11, ("T", "F", "F"), "DNS stop type")
    _at(dns, 12, ("F", "1", "1", "T"), "no-restart setting")
    _at(dns, 23, ("0", "0", "0"), "DNS gravity")
    _at(dns, 24, ("0", "0", "0"), "DNS background velocity")

    _at(source, 0, ("0",), "zero-slot setting")
    _at(source, 1, ("160", "84", "40"), "source-grid agreement")
    _at(source, 2, ("0", "0"), "empty half-open schedule")
    _at(source, 3, ("1.0e-4",), "source timestep agreement")
    _at(source, 4, ("0", "0", "-4.8"), "unused source-velocity parameter")
    _at(source, 5, ("0", "0", "0"), "zero source background")
    _at(source, 6, ("0", "0", "0"), "zero source gravity")
    _at(source, 8, ("0.2",), "fixed-step factor")

    _at(vof, 0, ("1000.0", "1.0", "1.0e-3", "1.8e-5"), "water/air properties")
    _at(vof, 1, ("zer",), "empty initial VOF")
    _at(vof, 6, ("0.0",), "zero surface tension")
    _at(vof, 7, ("F", "0"), "no late initialization")


def stage(source: Path, destination: Path) -> dict[str, object]:
    payloads, _ = _read_exact_inputs(source)
    report_path = destination.parent / "input-preflight.json"
    if (
        destination.exists()
        or destination.is_symlink()
        or report_path.exists()
        or report_path.is_symlink()
    ):
        raise FileExistsError("staging directory or preflight report already exists")
    destination.mkdir(mode=0o700, parents=False)
    staged_hashes: dict[str, str] = {}
    for name, data in payloads.items():
        target = destination / name
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(target, flags, 0o444)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(target, 0o444)
        staged_hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    if staged_hashes != INPUTS:
        raise RuntimeError("staged file hashes changed during copy")
    os.chmod(destination, 0o555)
    report: dict[str, object] = {
        "schema_version": "dry-four-input-preflight-v1",
        "case_id": CASE_ID,
        "source_directory": str(source.resolve()),
        "staged_directory": str(destination.resolve()),
        "cell_count": 160 * 84 * 40,
        "interval_count": 14,
        "state_count": 15,
        "planned_physical_time_s": 0.0014,
        "source_slot_count": 0,
        "source_schedule_steps": [0, 0],
        "gravity_m_s2": [0.0, 0.0, 0.0],
        "background_velocity_m_s": [0.0, 0.0, 0.0],
        "initial_vof": "empty (inivof=zer)",
        "source_velocity_parameter_m_s": [0.0, 0.0, -4.8],
        "source_velocity_parameter_applies": False,
        "input_sha256": staged_hashes,
        "records": "exact byte allowlist plus frozen dry_four semantic relations; not a generalized Fortran parser",
    }
    encoded = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(report_path, flags, 0o444)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(report_path, 0o444)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="candidate5 allowlisted dry_four directory")
    parser.add_argument("destination", type=Path, help="new run-specific read-only input directory")
    args = parser.parse_args(argv)
    try:
        report = stage(args.source, args.destination)
    except (FileExistsError, OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"preflight failed: {exc}\n")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
