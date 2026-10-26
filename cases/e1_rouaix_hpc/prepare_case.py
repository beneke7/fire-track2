#!/usr/bin/env python3
"""Prepare a small fixed-step Rouaix Case 1 bundle from a qualified global mesh."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "cases/e1_rouaix_case1_static/case"
PROVENANCE = Path(__file__).with_name("source-provenance.json")
POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
ROUAIX_PATCHES = {
    "nozzle": "patch",
    "gasInlet": "patch",
    "downstreamOutlet": "patch",
    "bottomOutlet": "patch",
    "aircraftWall": "wall",
    "spanwiseMinus": "patch",
    "spanwisePlus": "patch",
}
SOURCE_PATCH = "nozzle"
OPEN_PATCHES = ("gasInlet", "downstreamOutlet", "bottomOutlet", "spanwiseMinus", "spanwisePlus")
WALL_PATCH = "aircraftWall"
CONCAVE_EXCEPTION_STATUS = "qualified_with_exact_concave_set_exception"
CONCAVE_EXCEPTION_COUNT = 114_008
HORIZON_S = 0.05
DELTA_T_OPTIONS_S = (0.001, 0.0005, 0.0001)
HORIZON_OPTIONS_S = (0.01, HORIZON_S, 0.5, 5.0)
NUMERICAL_VARIANTS = ("original", "upwind", "u_gradient_limited")
MOMENTUM_CONVECTION_BY_VARIANT = {
    "original": "limitedLinearV 1",
    "upwind": "upwind",
    "u_gradient_limited": "limitedLinearV 1",
}
VELOCITY_GRADIENT_BY_VARIANT = {
    "original": "grad(U) Gauss linear;",
    "upwind": "grad(U) Gauss linear;",
    "u_gradient_limited": "grad(U) cellLimited Gauss linear 1;",
}
FVSCHEMES_OVERRIDE_BY_VARIANT = {
    "upwind": ("div(rhoPhi,U) Gauss limitedLinearV 1;", "div(rhoPhi,U) Gauss upwind;"),
    "u_gradient_limited": ("grad(U) Gauss linear;", "grad(U) cellLimited Gauss linear 1;"),
}
SUPPORTED_PLACEMENTS = {24: 1, 64: 1, 96: 1, 120: 1, 240: 2, 300: 3}
RHO_WATER = 997.6
RHO_AIR = 1.18
MU_WATER = 8.89e-4
MU_AIR = 1.86e-5
SURFACE_TENSION = 0.072
JET_DIAMETER = 0.4
JET_SPEED = 10.0
AIR_SPEED = 70.0
GRAVITY = [0.0, -9.81, 0.0]
PINNED_IMAGE = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _hash_inventory(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(POLYMESH_FILES):
        raise ValueError(f"{label} must hash exactly the five native polyMesh files")
    if any(
        not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in value.values()
    ):
        raise ValueError(f"{label} contains an invalid SHA-256")
    return {name: value[name] for name in POLYMESH_FILES}


def _bound_file(
    root: Path, record: Any, *, label: str, with_count: bool = False
) -> tuple[Path, str, int | None]:
    if not isinstance(record, dict):
        raise ValueError(f"qualification receipt {label} must be an object")
    expected_keys = {"path", "sha256", "count"} if with_count else {"path", "sha256"}
    if set(record) != expected_keys:
        raise ValueError(
            f"qualification receipt {label} must contain exactly {sorted(expected_keys)}"
        )
    relative_value = record.get("path")
    if not isinstance(relative_value, str) or not relative_value:
        raise ValueError(f"qualification receipt {label}.path must be nonempty")
    relative = Path(relative_value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"qualification receipt {label}.path must stay within its bundle")
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"qualification receipt {label} is missing or not a regular file")
    expected_sha = record.get("sha256")
    if not isinstance(expected_sha, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha) is None:
        raise ValueError(f"qualification receipt {label}.sha256 is invalid")
    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise ValueError(f"qualification receipt {label} SHA-256 mismatch")
    count = None
    if with_count:
        count_value = record.get("count")
        if isinstance(count_value, bool) or not isinstance(count_value, int) or count_value < 0:
            raise ValueError(f"qualification receipt {label}.count must be a nonnegative integer")
        count = count_value
    return path, expected_sha, count


def _read_sorted_id_file(path: Path, *, count: int, cell_count: int, label: str) -> list[int]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError(f"qualification {label} must be UTF-8 decimal labels") from error
    if len(lines) != count or any(re.fullmatch(r"0|[1-9][0-9]*", line) is None for line in lines):
        raise ValueError(f"qualification {label} must contain exactly {count} decimal labels")
    identifiers = [int(line) for line in lines]
    if identifiers != sorted(set(identifiers)):
        raise ValueError(f"qualification {label} labels must be sorted and unique")
    if any(identifier < 0 or identifier >= cell_count for identifier in identifiers):
        raise ValueError(f"qualification {label} contains a label outside the mesh cell range")
    return identifiers


def _read_openfoam_cell_set(path: Path, *, count: int, cell_count: int, label: str) -> list[int]:
    """Read the bounded ASCII or 32/64-bit binary OpenFOAM cellSet list."""
    raw = path.read_bytes()
    header_end = re.search(rb"\n\}\s*\n", raw)
    if header_end is None:
        raise ValueError(f"qualification {label} has no OpenFOAM FoamFile header")
    header = raw[: header_end.end()].decode("ascii", errors="replace")
    body = raw[header_end.end() :]
    body = re.sub(
        rb"(?s)\A\s*(?:(?://[^\n]*(?:\n|$))|(?:/\*.*?\*/\s*))*",
        b"",
        body,
    )
    body = re.sub(rb"\AnCells\s*:\s*\d+\s*;\s*", b"", body)
    list_header = re.match(rb"\s*(\d+)\s*\n\s*\(\s*", body)
    if list_header is None or int(list_header.group(1)) != count:
        raise ValueError(f"qualification {label} OpenFOAM list count does not match its receipt")
    payload_start = list_header.end()
    format_match = re.search(r"(?m)^\s*format\s+(ascii|binary)\s*;", header)
    if format_match is None:
        raise ValueError(f"qualification {label} header lacks an ASCII/binary format")
    closing = body.rfind(b")")
    trailing = re.sub(rb"(?m)^\s*//[^\n]*(?:\n|$)", b"", body[closing + 1 :])
    trailing = re.sub(rb"(?s)/\*.*?\*/", b"", trailing)
    if closing < payload_start or trailing.strip():
        raise ValueError(f"qualification {label} cellSet payload is malformed")
    payload = body[payload_start:closing]
    ascii_labels = re.fullmatch(rb"\s*(?:-?[0-9]+\s*)*", payload)
    if ascii_labels is not None:
        tokens = payload.decode("ascii").split()
        if len(tokens) != count:
            raise ValueError(f"qualification {label} ASCII cellSet has the wrong label count")
        identifiers = [int(token) for token in tokens]
    elif format_match.group(1) == "binary":
        arch = re.search(r'arch\s+"([^\"]+)"', header)
        if arch is None:
            raise ValueError(f"qualification {label} binary cellSet lacks an arch declaration")
        arch_fields = arch.group(1).split(";")
        endian = "<" if any(field.upper() == "LSB" for field in arch_fields) else ">"
        label_field = next((field for field in arch_fields if field.startswith("label=")), "")
        label_bits = int(label_field.partition("=")[2]) if label_field else 0
        if label_bits not in {32, 64}:
            raise ValueError(f"qualification {label} binary cellSet has unsupported label width")
        label_bytes = label_bits // 8
        payload_end = payload_start + count * label_bytes
        suffix = body[payload_end:]
        if payload_end > closing or suffix[: closing - payload_end].strip():
            raise ValueError(f"qualification {label} binary cellSet payload is malformed")
        code = "i" if label_bits == 32 else "q"
        identifiers = list(struct.unpack(f"{endian}{count}{code}", body[payload_start:payload_end]))
    else:
        raise ValueError(f"qualification {label} ASCII cellSet is malformed")
    if len(identifiers) != count or len(set(identifiers)) != count:
        raise ValueError(
            f"qualification {label} cellSet labels are not a unique list of the stated size"
        )
    if any(identifier < 0 or identifier >= cell_count for identifier in identifiers):
        raise ValueError(f"qualification {label} has a cell label outside the mesh cell range")
    return sorted(identifiers)


def _verify_concave_qualification_exception(
    *,
    mesh_dir: Path,
    manifest_path: Path,
    native_log_path: Path,
    native_log_sha: str,
    cell_count: int,
    mesh_hashes: dict[str, str],
    exception_ref: Any,
) -> dict[str, Any]:
    if not isinstance(exception_ref, dict) or set(exception_ref) != {"path", "sha256"}:
        raise ValueError("native_qa qualification_exception must contain exactly path and sha256")
    receipt_rel = Path(str(exception_ref.get("path", "")))
    if (
        not str(exception_ref.get("path", ""))
        or receipt_rel.is_absolute()
        or any(part in {"", ".", ".."} for part in receipt_rel.parts)
    ):
        raise ValueError("native_qa qualification_exception path must stay inside the mesh bundle")
    receipt_path = manifest_path.parent / receipt_rel
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("native qualification exception receipt is missing or not a regular file")
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    if receipt_sha != exception_ref.get("sha256"):
        raise ValueError("native qualification exception receipt SHA-256 mismatch")
    receipt = _read_json(receipt_path)
    expected_keys = {
        "schema_version",
        "status",
        "mesh_files_sha256",
        "native_log_sha256",
        "native_failure",
        "native_ids",
        "reference_ids",
        "native_set",
        "reference_set",
        "independent_audit",
        "review",
        "audit_tool",
        "audit_tool_helper",
        "decision_owner",
        "decision_date",
        "scope",
        "reason",
    }
    if set(receipt) != expected_keys or receipt.get("schema_version") != 1:
        raise ValueError("native qualification exception receipt has an unsupported schema")
    if receipt.get("status") != CONCAVE_EXCEPTION_STATUS:
        raise ValueError(
            "native qualification exception status is not approved for this exact case"
        )
    receipt_mesh_hashes = _hash_inventory(
        receipt.get("mesh_files_sha256"), label="qualification receipt"
    )
    if receipt_mesh_hashes != mesh_hashes:
        raise ValueError("qualification exception is not bound to these five polyMesh files")
    if (
        receipt.get("native_log_sha256") != native_log_sha
        or hashlib.sha256(native_log_path.read_bytes()).hexdigest() != native_log_sha
    ):
        raise ValueError("qualification exception is not bound to the native checkMesh log")
    if receipt.get("native_failure") != {
        "category": "concaveCells",
        "count": CONCAVE_EXCEPTION_COUNT,
        "failed_check_count": 1,
    }:
        raise ValueError(
            "qualification exception does not declare only the approved concaveCells failure"
        )

    log = native_log_path.read_text(encoding="utf-8", errors="replace")
    if "Mesh OK." in log:
        raise ValueError("a Mesh OK log must not carry a failed-check qualification exception")
    failed = re.findall(r"(?m)^\s*Failed\s+(\d+)\s+mesh checks?\.\s*$", log)
    marked = re.findall(r"(?m)^\s*\*\*\*(.+)$", log)
    expected_failure = re.compile(
        rf"^Concave cells \(using face planes\) found, number of cells:\s*{CONCAVE_EXCEPTION_COUNT}\s*$"
    )
    if failed != ["1"] or len(marked) != 1 or expected_failure.fullmatch(marked[0].strip()) is None:
        raise ValueError(
            "native checkMesh log has an extra, missing, or differently counted failure"
        )
    reported_cells = {int(value) for value in re.findall(r"(?m)^\s*cells:\s*(\d+)\s*$", log)}
    if reported_cells != {cell_count}:
        raise ValueError("native exception log cell count differs from the manifest")

    bundle_root = receipt_path.parent
    native_ids_path, native_ids_sha, native_ids_count = _bound_file(
        bundle_root, receipt.get("native_ids"), label="native_ids", with_count=True
    )
    reference_ids_path, reference_ids_sha, reference_ids_count = _bound_file(
        bundle_root, receipt.get("reference_ids"), label="reference_ids", with_count=True
    )
    native_set_path, native_set_sha, _ = _bound_file(
        bundle_root, receipt.get("native_set"), label="native_set"
    )
    reference_set_path, reference_set_sha, _ = _bound_file(
        bundle_root, receipt.get("reference_set"), label="reference_set"
    )
    audit_path, audit_sha, _ = _bound_file(
        bundle_root, receipt.get("independent_audit"), label="independent_audit"
    )
    review_path, review_sha, _ = _bound_file(bundle_root, receipt.get("review"), label="review")
    audit_tool_path, audit_tool_sha, _ = _bound_file(
        bundle_root, receipt.get("audit_tool"), label="audit_tool"
    )
    audit_tool_helper_path, audit_tool_helper_sha, _ = _bound_file(
        bundle_root, receipt.get("audit_tool_helper"), label="audit_tool_helper"
    )
    if not isinstance(receipt.get("decision_owner"), str) or not receipt["decision_owner"].strip():
        raise ValueError("qualification receipt decision_owner must be nonempty")
    if (
        not isinstance(receipt.get("decision_date"), str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", receipt["decision_date"]) is None
    ):
        raise ValueError("qualification receipt decision_date must be YYYY-MM-DD")
    if not isinstance(receipt.get("scope"), str) or "No E1" not in receipt["scope"]:
        raise ValueError("qualification receipt scope must limit the exception to exploratory work")
    if (
        not isinstance(receipt.get("reason"), str)
        or re.search(r"\bno\s+MeshOK\b", receipt["reason"]) is None
    ):
        raise ValueError("qualification receipt reason must preserve the raw no-MeshOK result")
    if (
        native_ids_count != CONCAVE_EXCEPTION_COUNT
        or reference_ids_count != CONCAVE_EXCEPTION_COUNT
    ):
        raise ValueError(
            "native/reference concave ID counts differ from the exact 114008-cell finding"
        )

    native_ids = _read_sorted_id_file(
        native_ids_path, count=CONCAVE_EXCEPTION_COUNT, cell_count=cell_count, label="native_ids"
    )
    reference_ids = _read_sorted_id_file(
        reference_ids_path,
        count=CONCAVE_EXCEPTION_COUNT,
        cell_count=cell_count,
        label="reference_ids",
    )
    if native_ids != _read_openfoam_cell_set(
        native_set_path,
        count=CONCAVE_EXCEPTION_COUNT,
        cell_count=cell_count,
        label="native_set",
    ):
        raise ValueError("native ID list does not decode from the hash-bound v2512 cellSet")
    if reference_ids != _read_openfoam_cell_set(
        reference_set_path,
        count=CONCAVE_EXCEPTION_COUNT,
        cell_count=cell_count,
        label="reference_set",
    ):
        raise ValueError("reference ID list does not decode from the hash-bound Foundation cellSet")
    if native_ids != reference_ids:
        raise ValueError("native and reference concave-cell ID sets differ")

    audit = _read_json(audit_path)
    provenance = audit.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("independent concavity audit lacks provenance")
    verified = provenance.get("input_sha256_verified")
    expected_verified = {
        name: mesh_hashes[name] for name in ("points", "faces", "owner", "neighbour")
    }
    expected_verified["sets/concaveCells"] = reference_set_sha
    if not isinstance(verified, dict) or verified != expected_verified:
        raise ValueError(
            "independent audit input hashes do not bind four mesh files and the Foundation set"
        )
    if provenance.get("native_concave_set_count") != CONCAVE_EXCEPTION_COUNT:
        raise ValueError("independent audit native concave set count differs")
    screen = audit.get("independent_vertex_plane_screen")
    if not isinstance(screen, dict):
        raise ValueError("independent audit lacks the vertex-plane screen")
    expected_counts = {
        "audited_cell_count": CONCAVE_EXCEPTION_COUNT,
        "native_flags_reproduced_by_recomputed_area_normal_face_centres": CONCAVE_EXCEPTION_COUNT,
        "native_flags_not_reproduced": 0,
        "cells_with_external_vertex_excursion_above_numeric_bound": 0,
        "cells_with_positive_cosine_witness_above_roundoff_band": 0,
    }
    if any(screen.get(key) != value for key, value in expected_counts.items()):
        raise ValueError(
            "independent vertex-plane screen has an unexpected count or nonzero finding"
        )
    expected_values = {
        "max_positive_external_vertex_plane_excursion_m": 6.223858637768553e-15,
        "max_face_warp_m": 2.664535034107249e-15,
        "numeric_error_bound_m": 1e-11,
    }
    for key, expected_value in expected_values.items():
        value = screen.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"independent screen {key} must be a finite number")
        if not math.isclose(value, expected_value, rel_tol=0.0, abs_tol=1e-27):
            raise ValueError(f"independent screen {key} differs from the reviewed evidence")
    return {
        "schema_version": 1,
        "status": CONCAVE_EXCEPTION_STATUS,
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": receipt_sha,
        "native_log_sha256": native_log_sha,
        "mesh_files_sha256": mesh_hashes,
        "native_failure": receipt["native_failure"],
        "native_ids_sha256": native_ids_sha,
        "reference_ids_sha256": reference_ids_sha,
        "native_set_sha256": native_set_sha,
        "reference_set_sha256": reference_set_sha,
        "independent_audit_sha256": audit_sha,
        "review_sha256": review_sha,
        "audit_tool_sha256": audit_tool_sha,
        "audit_tool_helper_sha256": audit_tool_helper_sha,
        "support_files": [
            str(path.resolve())
            for path in (
                native_ids_path,
                reference_ids_path,
                native_set_path,
                reference_set_path,
                audit_path,
                review_path,
                audit_tool_path,
                audit_tool_helper_path,
            )
        ],
    }


def _patch_inventory(boundary: Path) -> tuple[dict[str, int], dict[str, str]]:
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", boundary.read_text(encoding="utf-8"), flags=re.S)
    counts: dict[str, int] = {}
    types: dict[str, str] = {}
    for match in re.finditer(r"(?ms)^\s*([A-Za-z_][A-Za-z_0-9]*)\s*\{(.*?)^\s*\}", text):
        name, body = match.groups()
        faces = re.search(r"(?m)^\s*nFaces\s+(\d+)\s*;", body)
        patch_type = re.search(r"(?m)^\s*type\s+(\w+)\s*;", body)
        if faces and patch_type:
            counts[name] = int(faces.group(1))
            types[name] = patch_type.group(1)
    return counts, types


def verify_mesh_inputs(
    mesh_dir: Path, manifest_path: Path, nozzle_audit_path: Path
) -> dict[str, Any]:
    """Fail closed unless hashes, native checkMesh evidence and nozzle audit align."""
    if mesh_dir.is_symlink() or manifest_path.is_symlink() or nozzle_audit_path.is_symlink():
        raise ValueError("mesh, manifest and nozzle audit inputs must not be symlinks")
    mesh_dir = mesh_dir.resolve(strict=True)
    if not mesh_dir.is_dir() or mesh_dir.is_symlink():
        raise ValueError("--mesh-dir must be a regular polyMesh directory")
    manifest_path = manifest_path.resolve(strict=True)
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("mesh manifest schema_version must be 1")
    cells = manifest.get("cell_count")
    if isinstance(cells, bool) or not isinstance(cells, int) or cells <= 0:
        raise ValueError("mesh manifest cell_count must be a positive integer")
    expected = _hash_inventory(manifest.get("mesh_files_sha256"), label="mesh manifest")
    actual = {}
    for name in POLYMESH_FILES:
        path = mesh_dir / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"mesh file is missing or not regular: {path}")
        actual[name] = sha256(path)
    if actual != expected:
        raise ValueError("polyMesh SHA-256 values differ from the qualified mesh manifest")

    native = manifest.get("native_qa")
    if not isinstance(native, dict) or (native.get("version"), native.get("status")) != (
        "v2512",
        "qualified",
    ):
        raise ValueError("mesh requires native_qa version v2512 and status qualified")
    log_path = Path(str(native.get("log_path", "")))
    if not log_path.is_absolute():
        log_path = manifest_path.parent / log_path
    if log_path.is_symlink():
        raise ValueError("native checkMesh log must not be a symlink")
    log_path = log_path.resolve(strict=True)
    if log_path.is_symlink() or sha256(log_path) != native.get("log_sha256"):
        raise ValueError("native checkMesh log is missing or its hash differs from the manifest")
    log = log_path.read_text(encoding="utf-8", errors="replace")
    reported_cells = {int(value) for value in re.findall(r"(?m)^\s*cells:\s*(\d+)\s*$", log)}
    if reported_cells != {cells}:
        raise ValueError("native checkMesh log cell count differs from the mesh manifest")
    native_log_sha = sha256(log_path)
    if "Mesh OK." in log:
        if "qualification_exception" in native:
            raise ValueError(
                "ordinary Mesh OK evidence must not carry a failure qualification exception"
            )
        verified_exception = None
    else:
        if "qualification_exception" not in native:
            raise ValueError(
                "native checkMesh lacks Mesh OK and has no bound qualification exception"
            )
        verified_exception = _verify_concave_qualification_exception(
            mesh_dir=mesh_dir,
            manifest_path=manifest_path,
            native_log_path=log_path,
            native_log_sha=native_log_sha,
            cell_count=cells,
            mesh_hashes=actual,
            exception_ref=native.get("qualification_exception"),
        )

    nozzle = _read_json(nozzle_audit_path.resolve(strict=True))
    if nozzle.get("schema_version") != 1 or nozzle.get("patch") != SOURCE_PATCH:
        raise ValueError("nozzle audit must be schema_version 1 for patch 'nozzle'")
    if _hash_inventory(nozzle.get("mesh_files_sha256"), label="nozzle audit") != expected:
        raise ValueError("nozzle geometry audit is not bound to this polyMesh hash set")
    face_count = nozzle.get("face_count")
    area = nozzle.get("area_m2")
    vector = nozzle.get("area_vector_m2")
    if isinstance(face_count, bool) or not isinstance(face_count, int) or face_count <= 0:
        raise ValueError("nozzle audit face_count must be a positive integer")
    if (
        not isinstance(area, (int, float))
        or isinstance(area, bool)
        or not math.isfinite(area)
        or area <= 0
    ):
        raise ValueError("nozzle audit area_m2 must be finite and positive")
    if (
        not isinstance(vector, list)
        or len(vector) != 3
        or any(
            not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(item)
            for item in vector
        )
    ):
        raise ValueError("nozzle audit area_vector_m2 must contain three finite values")
    analytic_area = math.pi * (JET_DIAMETER / 2) ** 2
    if abs(area / analytic_area - 1.0) > 0.005:
        raise ValueError("measured nozzle area differs from the analytic circle by over 0.5%")
    if (
        abs(vector[0]) > area * 1e-6
        or abs(vector[2]) > area * 1e-6
        or abs(vector[1] - area) > area * 1e-6
    ):
        raise ValueError("measured nozzle area vector must point outward along +y")

    counts, types = _patch_inventory(mesh_dir / "boundary")
    if types != ROUAIX_PATCHES:
        raise ValueError(f"mesh boundary patches differ from the Rouaix template: {types}")
    if counts.get(SOURCE_PATCH) != face_count:
        raise ValueError("nozzle audit face_count differs from the imported boundary")
    return {
        "cell_count": cells,
        "mesh_files_sha256": actual,
        "mesh_manifest_sha256": sha256(manifest_path),
        "mesh_manifest_path": str(manifest_path),
        "native_qa": native,
        "native_qualification_exception": verified_exception,
        "nozzle_audit_sha256": sha256(nozzle_audit_path.resolve()),
        "nozzle_audit": nozzle,
        "patch_face_counts": counts,
    }


def _function_objects() -> str:
    flux = "\n".join(
        f"""    {patch}Flux
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name {patch};
        operation sum;
        fields (phi alphaPhi_);
        writeFields false;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}"""
        for patch in (SOURCE_PATCH, *OPEN_PATCHES, WALL_PATCH)
    )
    return f"""functions
{{
    waterVolume
    {{
        type volFieldValue;
        libs (fieldFunctionObjects);
        fields (alpha.water);
        operation volIntegrate;
        regionType all;
        writeFields false;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}
{flux}
    alphaExtrema
    {{
        type fieldMinMax;
        libs (fieldFunctionObjects);
        fields (alpha.water);
        location false;
        log true;
        writePrecision 12;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}
    speedExtrema
    {{
        type fieldMinMax;
        libs (fieldFunctionObjects);
        mode magnitude;
        fields (U);
        location false;
        log true;
        writePrecision 12;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}
    failureLocations
    {{
        type fieldMinMax;
        libs (fieldFunctionObjects);
        mode magnitude;
        fields (U p_rgh k epsilon nut);
        location true;
        log true;
        writePrecision 12;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}
}}"""


def _field_write_times(end_time_s: float, write_interval_s: float) -> list[float]:
    count = end_time_s / write_interval_s
    if not math.isfinite(count) or not math.isclose(count, round(count), rel_tol=0, abs_tol=1e-9):
        raise ValueError("field write interval must divide the declared horizon exactly")
    return [round(index * write_interval_s, 12) for index in range(round(count) + 1)]


def _control_dict(
    delta_t_s: float,
    end_time_s: float = HORIZON_S,
    write_interval_s: float | None = None,
    profiling: bool = False,
) -> str:
    if write_interval_s is None:
        write_interval_s = end_time_s
    purge_write = 2 if end_time_s == 5.0 and write_interval_s == 1.0 else 0
    control = f"""FoamFile
{{
    version 2.0;
    format ascii;
    class dictionary;
    object controlDict;
}}
application interIsoFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {end_time_s:.12g};
deltaT {delta_t_s:.12g};
adjustTimeStep no;
maxCo 5;
maxAlphaCo 5;
maxDeltaT {delta_t_s:.12g};
writeControl runTime;
writeInterval {write_interval_s:.12g};
purgeWrite {purge_write};
writeFormat binary;
writePrecision 12;
writeCompression off;
timeFormat fixed;
timePrecision 12;
runTimeModifiable false;
OptimisationSwitches
{{
    fileHandler collated;
    maxThreadFileBufferSize 0;
    writeNowSignal 10;
    stopAtWriteNowSignal 12;
}}
{_function_objects()}
"""
    if profiling:
        control += "\nprofiling\n{\n    active true;\n    cpuInfo false;\n    memInfo false;\n    sysInfo false;\n}\n"
    return control


def _decompose_dict(ranks: int) -> str:
    return f"""FoamFile
{{
    version 2.0;
    format ascii;
    class dictionary;
    object decomposeParDict;
}}
numberOfSubdomains {ranks};
method scotch;
distributed no;
roots ();
"""


def prepare_case(
    mesh_dir: Path,
    mesh_manifest: Path,
    nozzle_audit: Path,
    output_dir: Path,
    *,
    ranks: int,
    delta_t_s: float,
    nodes: int = 1,
    end_time_s: float = HORIZON_S,
    numerical_variant: str = "original",
    write_interval_s: float | None = None,
    memory_gib: int = 64,
    profiling: bool = False,
    timeout_s: float = 1200.0,
    set_expr_fields: str = "setExprFields",
) -> Path:
    if (
        isinstance(ranks, bool)
        or ranks not in SUPPORTED_PLACEMENTS
        or isinstance(nodes, bool)
        or nodes != SUPPORTED_PLACEMENTS[ranks]
    ):
        raise ValueError(
            "supported rank/node placements are 24/1, 64/1, 96/1, 120/1, 240/2, or 300/3"
        )
    if (
        isinstance(memory_gib, bool)
        or not isinstance(memory_gib, int)
        or not 32 <= memory_gib <= 64
    ):
        raise ValueError("memory_gib must be an integer from 32 through 64")
    if not isinstance(profiling, bool):
        raise ValueError("profiling must be a boolean")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be finite and positive")
    if isinstance(delta_t_s, bool) or delta_t_s not in DELTA_T_OPTIONS_S:
        raise ValueError(f"deltaT must be one of {DELTA_T_OPTIONS_S}")
    if isinstance(end_time_s, bool) or end_time_s not in HORIZON_OPTIONS_S:
        raise ValueError(
            "end_time_s must be one of the declared 0.01, 0.05, 0.5, or 5.0 s horizons"
        )
    if numerical_variant not in NUMERICAL_VARIANTS:
        raise ValueError(f"numerical_variant must be one of {NUMERICAL_VARIANTS}")
    if write_interval_s is None:
        write_interval_s = end_time_s
    if (
        isinstance(write_interval_s, bool)
        or not math.isfinite(write_interval_s)
        or write_interval_s <= 0
        or (write_interval_s != end_time_s and not (end_time_s == 5.0 and write_interval_s == 1.0))
    ):
        raise ValueError("write interval must equal the horizon, except 1 s checkpoints for 5 s")
    interval_steps = write_interval_s / delta_t_s
    if not math.isclose(interval_steps, round(interval_steps), rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("write interval must align with fixed time steps")
    field_write_times = _field_write_times(end_time_s, write_interval_s)
    steps = end_time_s / delta_t_s
    if not math.isfinite(steps) or not math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-9):
        raise ValueError("end_time_s must contain an integer number of fixed time steps")
    evidence = verify_mesh_inputs(mesh_dir, mesh_manifest, nozzle_audit)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite prepared case: {output_dir}")
    provenance = _read_json(PROVENANCE)
    for relative, record in provenance["dictionaries"].items():
        if sha256(Path(__file__).resolve().parent / "template" / relative) != record["sha256"]:
            raise ValueError(f"verified source dictionary changed: {relative}")
    for relative, expected_hash in provenance["field_and_local_template_source"][
        "files_sha256"
    ].items():
        if sha256(TEMPLATE / relative) != expected_hash:
            raise ValueError(f"verified Case 1 field/template changed: {relative}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True)
    for directory in ("0", "constant", "system"):
        (output_dir / directory).mkdir()
    for source in (TEMPLATE / "0").iterdir():
        if source.is_file():
            shutil.copy2(source, output_dir / "0" / source.name)
    for relative in (
        "constant/g",
        "constant/hRef",
        "constant/turbulenceProperties",
        "system/setExprFieldsDict",
    ):
        shutil.copy2(TEMPLATE / relative, output_dir / relative)
    template_dir = Path(__file__).resolve().parent / "template"
    shutil.copy2(
        template_dir / "constant/transportProperties", output_dir / "constant/transportProperties"
    )
    for relative in ("fvSchemes", "fvSolution"):
        shutil.copy2(template_dir / "system" / relative, output_dir / "system" / relative)
    fv_schemes_path = output_dir / "system/fvSchemes"
    parent_fv_schemes_sha256 = sha256(fv_schemes_path)
    scheme_override = FVSCHEMES_OVERRIDE_BY_VARIANT.get(numerical_variant)
    if scheme_override is not None:
        schemes = fv_schemes_path.read_text(encoding="utf-8")
        original_scheme, diagnostic_scheme = scheme_override
        if schemes.count(original_scheme) != 1:
            raise ValueError(
                f"{numerical_variant} diagnostic expects exactly one {original_scheme!r} entry"
            )
        fv_schemes_path.write_text(
            schemes.replace(original_scheme, diagnostic_scheme), encoding="utf-8"
        )
    post_override_fv_schemes_sha256 = sha256(fv_schemes_path)
    poly_mesh = output_dir / "constant/polyMesh"
    poly_mesh.mkdir()
    for name in POLYMESH_FILES:
        shutil.copy2(Path(mesh_dir) / name, poly_mesh / name)
    (output_dir / "system/controlDict").write_text(
        _control_dict(delta_t_s, end_time_s, write_interval_s, profiling), encoding="utf-8"
    )
    (output_dir / "system/decomposeParDict").write_text(_decompose_dict(ranks), encoding="utf-8")

    pressure_seed = (output_dir / "0/p_rgh").read_text(encoding="utf-8")
    if not re.search(r"\binternalField\s+uniform\s+0\s*;", pressure_seed):
        raise RuntimeError("case template p_rgh must start from the verified uniform zero seed")

    result = subprocess.run(
        [set_expr_fields, "-time", "0"],
        cwd=output_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    (output_dir / "setExprFields.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(
            f"setExprFields failed with exit code {result.returncode}; case preserved"
        )
    pressure_header = (output_dir / "0/p_rgh").read_bytes()[:8192].decode("ascii", errors="replace")
    if not re.search(
        rf"\binternalField\s+nonuniform\s+List<scalar>\s+{evidence['cell_count']}\s*\(",
        pressure_header,
    ):
        raise RuntimeError(
            "setExprFields did not write the declared transformed p_rgh value per mesh cell"
        )

    area = float(evidence["nozzle_audit"]["area_m2"])
    area_vector = evidence["nozzle_audit"]["area_vector_m2"]
    analytic_area = math.pi * (JET_DIAMETER / 2) ** 2
    source_flow = area * JET_SPEED
    source_mass_flow = RHO_WATER * source_flow
    source_momentum = [0.0, -RHO_WATER * area * JET_SPEED**2, 0.0]
    hashes = {
        relative: sha256(output_dir / relative)
        for relative in (
            "system/fvSchemes",
            "system/fvSolution",
            "constant/transportProperties",
        )
    }
    metadata = {
        "case_id": "rouaix-e1-case1-hpc-startup-pilot",
        "solver": "interIsoFoam",
        "execution_backend": "slurm-native",
        "solver_version": "v2512",
        "reference_image_digest": PINNED_IMAGE,
        "solver_runtime_provenance": "Native Komondor module and executable must be captured by the Slurm job and matched to verified-source-evidence; reference_image_digest is reference provenance only.",
        "mesh_type": "static polyhedral mesh imported from a native-v2512-qualified global mesh",
        "mesh_cells_expected": evidence["cell_count"],
        "mesh_source": evidence["mesh_manifest_path"],
        "mesh_files_sha256": evidence["mesh_files_sha256"],
        "mesh_manifest_sha256": evidence["mesh_manifest_sha256"],
        "native_qa": evidence["native_qa"],
        "native_qualification_exception": evidence["native_qualification_exception"],
        "nozzle_audit_sha256": evidence["nozzle_audit_sha256"],
        "source_patches": [SOURCE_PATCH],
        "source_patch_face_counts": {SOURCE_PATCH: evidence["patch_face_counts"][SOURCE_PATCH]},
        "open_patches": list(OPEN_PATCHES),
        "wall_patches": [WALL_PATCH],
        "source_patch_areas_m2": {SOURCE_PATCH: area},
        "source_patch_area_vector_m2": {SOURCE_PATCH: area_vector},
        "source_geometry_deviation_fraction": area / analytic_area - 1.0,
        "source_geometry": {
            "patch": SOURCE_PATCH,
            "measured_area_m2": area,
            "analytic_circle_area_m2": analytic_area,
            "relative_area_deviation_fraction": area / analytic_area - 1.0,
            "area_deviation_limit_fraction": 0.005,
            "measured_outward_area_vector_m2": area_vector,
            "velocity_m_s": [0.0, -JET_SPEED, 0.0],
            "velocity_renormalized": False,
            "volume_flow_from_measured_area_m3_s": source_flow,
            "mass_flow_from_measured_area_kg_s": source_mass_flow,
            "momentum_influx_from_measured_area_N": source_momentum,
        },
        "source_velocity_m_s": [0.0, -JET_SPEED, 0.0],
        "air_speed_m_s": AIR_SPEED,
        "coordinate_frame": {"x": "crossflow +", "y": "upward +", "z": "spanwise +"},
        "gravity_m_s2": GRAVITY,
        "fluid_properties": {
            "water": {"rho_kg_m3": RHO_WATER, "mu_pa_s": MU_WATER, "nu_m2_s": MU_WATER / RHO_WATER},
            "air": {"rho_kg_m3": RHO_AIR, "mu_pa_s": MU_AIR, "nu_m2_s": MU_AIR / RHO_AIR},
            "surface_tension_N_m": SURFACE_TENSION,
        },
        "source_flow_from_measured_area_m3_s": source_flow,
        "source_mass_flow_from_measured_area_kg_s": source_mass_flow,
        "source_momentum_influx_from_measured_area_N": source_momentum,
        "horizon_s": end_time_s,
        "node_count": nodes,
        "ranks": ranks,
        "profiling": profiling,
        "time_controls": {
            "delta_t_s": delta_t_s,
            "fixed_delta_t": True,
            "adjust_time_step": False,
            "max_delta_t_s": delta_t_s,
            "nAlphaSubCycles": 1,
            "snapshot_interval_s": write_interval_s,
            "full_field_write_times_s": field_write_times,
            "purge_write": 2 if end_time_s == 5.0 and write_interval_s == 1.0 else 0,
            "checkpoint_policy": {
                "scheduled_field_write_times_s": field_write_times,
                "retained_positive_checkpoint_limit": (
                    2 if end_time_s == 5.0 and write_interval_s == 1.0 else None
                ),
                "preserve_initial_global_t0": True,
                "retain_all_per_step_metrics": True,
            },
            "startup_steps": round(end_time_s / delta_t_s),
        },
        "initial_fields": {
            "alpha.water": "fresh air-filled internalField uniform 0; source boundary is prescribed",
            "p_rgh": "native v2512 setExprFields transform of uniform gauge-static p0, hRef=0 m",
            "fields_mapped_from_prior_run": False,
        },
        "turbulence_model": "realizable k-epsilon RANS",
        "numerical_variant": numerical_variant,
        "parent_fvSchemes_sha256": parent_fv_schemes_sha256,
        "post_override_fvSchemes_sha256": post_override_fv_schemes_sha256,
        "actual_momentum_convection": MOMENTUM_CONVECTION_BY_VARIANT[numerical_variant],
        "actual_velocity_gradient_scheme": VELOCITY_GRADIENT_BY_VARIANT[numerical_variant],
        "numerical_assumptions": {
            "source": "current fine-mesh dictionaries bound by parent and post-override SHA-256",
            "momentum_convection": MOMENTUM_CONVECTION_BY_VARIANT[numerical_variant],
            "velocity_gradient_scheme": VELOCITY_GRADIENT_BY_VARIANT[numerical_variant],
            "velocity_gradient_limiter_scope": (
                "cellLimited Gauss linear 1 on grad(U) only; grad(k) and grad(epsilon) unchanged"
                if numerical_variant == "u_gradient_limited"
                else "no velocity-gradient limiter override"
            ),
            "velocity_gradient_diagnostic_note": (
                "OpenFOAM cellLimited Gauss linear 1 is a bounded diagnostic choice, not the "
                "Rouaix paper's Venkatakrishnan or hybrid least-squares scheme"
                if numerical_variant == "u_gradient_limited"
                else None
            ),
            "numerical_variant": numerical_variant,
            "parent_fvSchemes_sha256": parent_fv_schemes_sha256,
            "post_override_fvSchemes_sha256": post_override_fv_schemes_sha256,
            "turbulence_convection": "upwind",
            "momentum_solver": "PBiCGStab/DILU",
            "kFinal_minIter": 1,
            "kFinal_history": "current fine-case fvSolution already has minIter 1; an older minIter 0 diagnostic printed zero kFinal iterations and is not this input",
            "interface_method": "OpenCFD v2512 interIsoFoam isoAdvector; not paper HRIC",
            "paper_numerics_difference": "Rouaix Table 1 uses HRIC and second-order-upwind convection; these inherited pilot choices are diagnostic assumptions, not an E1 match",
        },
        "diagnostics": {
            "file_handler": "collated",
            "max_thread_file_buffer_size": 0,
            "native_water_volume_and_alphaPhi_each_step": True,
            "flux_patches_including_wall_leak_check": [SOURCE_PATCH, *OPEN_PATCHES, WALL_PATCH],
            "alpha_and_speed_extrema_each_step": True,
            "failure_localization_fields_each_step": ["U", "p_rgh", "k", "epsilon", "nut"],
            "Courant_and_pressure_iteration_data": "native solver console log",
            "IO_and_clock_time": "native solver console log; separate IO fraction not instrumented",
            "resource_sampling": "Slurm accounting and native-launcher samples; periodic samples are not a true peak",
        },
        "resource_budget_provisional": {
            "memory_gib": memory_gib,
            "wall_time_s": timeout_s,
            "threads_per_rank": 1,
        },
        "solver_dictionary_sha256": hashes,
        "source_dictionary_provenance": provenance["dictionaries"],
        "formal_validation_decision": None,
    }
    (output_dir / "case-inputs.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mesh-dir", type=Path, required=True, help="qualified global constant/polyMesh"
    )
    parser.add_argument(
        "--mesh-manifest",
        type=Path,
        required=True,
        help="root-emitted hash/native-v2512 QA manifest",
    )
    parser.add_argument(
        "--nozzle-audit",
        type=Path,
        required=True,
        help="hash-bound native nozzle area/vector report",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="new prepared case directory"
    )
    parser.add_argument("--ranks", type=int, default=64)
    parser.add_argument("--nodes", type=int, default=1)
    parser.add_argument("--end-time-s", type=float, choices=HORIZON_OPTIONS_S, default=HORIZON_S)
    parser.add_argument("--write-interval-s", type=float)
    parser.add_argument("--numerical-variant", choices=NUMERICAL_VARIANTS, default="original")
    parser.add_argument("--memory-gib", type=int, default=64)
    parser.add_argument("--profiling", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=1200.0)
    parser.add_argument("--delta-t-s", type=float, choices=DELTA_T_OPTIONS_S, required=True)
    parser.add_argument(
        "--set-expr-fields", default="setExprFields", help="native OpenFOAM v2512 utility"
    )
    args = parser.parse_args()
    try:
        case = prepare_case(
            args.mesh_dir,
            args.mesh_manifest,
            args.nozzle_audit,
            args.output_dir,
            ranks=args.ranks,
            delta_t_s=args.delta_t_s,
            nodes=args.nodes,
            end_time_s=args.end_time_s,
            numerical_variant=args.numerical_variant,
            write_interval_s=args.write_interval_s,
            memory_gib=args.memory_gib,
            profiling=args.profiling,
            timeout_s=args.timeout_s,
            set_expr_fields=args.set_expr_fields,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Rouaix HPC case preparation failed: {error}", file=sys.stderr)
        return 2
    print(case.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
