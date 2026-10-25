#!/usr/bin/env python3
"""Stage a custom OpenFOAM solver overlay and its local-build provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PACKAGE_SCHEMA = 1
SOURCE_SUFFIXES = {".C", ".H"}
MAKE_INPUTS = {"files", "options"}
EVIDENCE_NAMES = (
    "build.log",
    "launch-record.json",
    "solver-source.diff",
    "runner-source.diff",
    "parent-input-hashes.json",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_source_input(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if path.suffix in SOURCE_SUFFIXES:
        return True
    return (
        len(relative.parts) >= 2 and relative.parts[-2] == "Make" and relative.name in MAKE_INPUTS
    )


def source_manifest_digest(paths: list[Path], root: Path) -> str:
    """Hash source paths and their content digests in a stable, portable order."""
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        file_digest = bytes.fromhex(sha256_file(path))
        digest.update(len(relative).to_bytes(4, byteorder="big"))
        digest.update(relative)
        digest.update(file_digest)
    return digest.hexdigest()


def _read_launch_record(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read launch record {path}: {error}") from error
    if not isinstance(record, dict):
        raise ValueError("launch-record.json must contain a JSON object")
    return record


def stage_bundle(
    *,
    source_root: Path,
    binary: Path,
    evidence_root: Path,
    output: Path,
    expected_source_sha256: str | None = None,
    local_image_id: str | None = None,
) -> dict[str, Any]:
    source_root = source_root.resolve(strict=True)
    binary = binary.resolve(strict=True)
    evidence_root = evidence_root.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise ValueError(f"refusing to overwrite existing staging directory: {output}")
    if not source_root.is_dir() or not evidence_root.is_dir():
        raise ValueError("source root and evidence root must be directories")

    required = (
        source_root / "interIsoFoam/Make/files",
        source_root / "interIsoFoam/Make/options",
        source_root / "interIsoFoam/interIsoFoam.C",
        source_root / "interIsoFoam/traceNormalHeadPressureFvPatchScalarField.C",
        source_root / "interIsoFoam/traceNormalHeadPressureFvPatchScalarField.H",
        binary,
        evidence_root / "launch-record.json",
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise ValueError(
            "missing required solver provenance inputs: " + ", ".join(map(str, missing))
        )
    if binary.stat().st_mode & 0o111 == 0:
        raise ValueError("reference binary must be executable")

    source_files = [
        path
        for path in source_root.rglob("*")
        if path.is_file() and _is_source_input(path, source_root)
    ]
    if len(source_files) < 5:
        raise ValueError(
            f"solver overlay unexpectedly contains only {len(source_files)} source inputs"
        )
    source_digest = source_manifest_digest(source_files, source_root)
    if expected_source_sha256 is not None and source_digest != expected_source_sha256.lower():
        raise ValueError(
            "source overlay digest differs from expected value: "
            f"{source_digest} != {expected_source_sha256.lower()}"
        )

    launch_record = _read_launch_record(evidence_root / "launch-record.json")
    recorded_binary = launch_record.get("binary_sha256")
    binary_digest = sha256_file(binary)
    if recorded_binary is not None and str(recorded_binary).lower() != binary_digest:
        raise ValueError("binary SHA-256 does not match launch-record.json")

    output.mkdir(parents=True)
    overlay_root = output / "solver-overlay"
    for source_path in source_files:
        destination = overlay_root / source_path.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)

    reference_binary = output / "reference-build/interIsoFoamTracePair"
    reference_binary.parent.mkdir(parents=True)
    shutil.copy2(binary, reference_binary)
    reference_binary.chmod(0o755)

    staged_evidence = output / "provenance"
    staged_evidence.mkdir()
    evidence_hashes: dict[str, str] = {}
    for name in EVIDENCE_NAMES:
        source = evidence_root / name
        if source.is_file():
            destination = staged_evidence / name
            shutil.copy2(source, destination)
            evidence_hashes[name] = sha256_file(destination)

    manifest = {
        "schema_version": PACKAGE_SCHEMA,
        "solver_name": "interIsoFoamTracePair",
        "solver_kind": "custom interIsoFoam-derived diagnostic; not stock interIsoFoam",
        "custom_boundary_condition": "traceNormalHeadPressure",
        "custom_boundary_condition_model": (
            "normal-only inlet dynamic-head pressure: pStatic=pExternal-0.5*rho*min(Un,0)^2; "
            "then p_rgh=pStatic-rho*(g dot Cf-ghRef); tangential U is not included"
        ),
        "source_overlay_file_count": len(source_files),
        "source_manifest_sha256": source_digest,
        "source_manifest_algorithm": (
            "sha256 over sorted relative POSIX paths as 4-byte big-endian byte-length plus path UTF-8 "
            "plus raw 32-byte per-file SHA-256 digest"
        ),
        "source_files": [
            {
                "path": source_path.relative_to(source_root).as_posix(),
                "sha256": sha256_file(source_path),
            }
            for source_path in sorted(
                source_files, key=lambda item: item.relative_to(source_root).as_posix()
            )
        ],
        "reference_binary_sha256": binary_digest,
        "reference_binary_role": "provenance only; not declared portable to cluster ABI/MPI",
        "local_build_environment": {
            "openfoam_version": launch_record.get("openfoam_version", "OpenCFD OpenFOAM v2512"),
            "container_image_id": local_image_id
            or launch_record.get("image_id", launch_record.get("image")),
            "launch_record_binary_sha256": recorded_binary,
        },
        "evidence_sha256": evidence_hashes,
        "cluster_build_policy": (
            "Build the staged source overlay against the site's confirmed OpenFOAM version, "
            "compiler, and MPI. Do not substitute stock interIsoFoam or copy the reference "
            "binary into a production run without a site-native smoke test."
        ),
    }
    (output / "staging-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "BUILD-ON-CLUSTER.md").write_text(_build_instructions(manifest), encoding="utf-8")
    return manifest


def _build_instructions(manifest: dict[str, Any]) -> str:
    return f"""# Build the staged custom solver on the cluster

This bundle contains the captured solver source overlay and a reference binary
for provenance. The reference executable SHA-256 is
`{manifest["reference_binary_sha256"]}`; it was built locally with
`{manifest["local_build_environment"]["openfoam_version"]}`. It is **not**
assumed compatible with the cluster ABI, MPI, compiler, or interconnect.

The code is a custom `interIsoFoamTracePair` executable, not stock
`interIsoFoam`. It registers the `traceNormalHeadPressure` patch field. Do not
replace it with stock `prghTotalPressure`: that has different pressure
semantics and includes tangential velocity in its total-head treatment.

1. Load the site's documented OpenFOAM and MPI environment. Record the exact
   `foamVersion`, compiler, MPI implementation/version, and launch mechanism.
   This bundle does not guess module names or container paths.
2. Confirm the site OpenFOAM source/API version is compatible with the captured
   source. Build from `solver-overlay/interIsoFoam` using the site's `wmake`.
   Preserve build output and resulting executable hash. If the site version is
   not the captured v2512 API, stop and review the source differences; do not
   silently change solver or boundary-condition behavior.
3. Run a one-rank dry startup and a small multi-rank smoke using the site's
   documented native MPI/runtime integration. Verify the custom BC is loaded,
   solver identity/version and source hashes match the staged manifest, output
   writes/checkpoints work, and decomposition/reconstruction preserve the
   native fields and ledger. Only then prepare a science case.

The exact source input digest is `{manifest["source_manifest_sha256"]}`.
See `staging-manifest.json` and `provenance/` for the hash inventory and
captured local launch evidence. No run is submitted or started by the packager.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-source-sha256")
    parser.add_argument(
        "--local-image-id", help="optional image identifier used for the local build"
    )
    args = parser.parse_args(argv)
    try:
        manifest = stage_bundle(
            source_root=args.source_root,
            binary=args.binary,
            evidence_root=args.evidence_root,
            output=args.output,
            expected_source_sha256=args.expect_source_sha256,
            local_image_id=args.local_image_id,
        )
    except (OSError, ValueError) as error:
        print(f"package_solver: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "output": args.output.as_posix(),
                "source_manifest_sha256": manifest["source_manifest_sha256"],
                "reference_binary_sha256": manifest["reference_binary_sha256"],
                "source_overlay_file_count": manifest["source_overlay_file_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
