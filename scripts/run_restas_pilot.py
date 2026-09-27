#!/usr/bin/env python3
"""Prepare and run the declared four-slot OpenFOAM CPU characterization pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from analyze_restas_pilot import build_report
from doctor import effective_cpu_count

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "opencfd/openfoam-default:2512"
DOMAIN = {"x": (-7.975, 7.975), "y": (-3.025, 3.025), "z": (0.0, 4.0)}
X_BREAKS = (-7.975, -0.175, -0.025, 0.025, 0.175, 7.975)
Y_BREAKS = (-3.025, -1.025, -0.025, 0.025, 1.025, 3.025)
NX = (104, 3, 1, 3, 104)
NY = (40, 20, 1, 20, 40)
NZ = 80
SLOT_X_SEGMENTS = (1, 3)
SLOT_Y_SEGMENTS = (1, 3)
SLOT_NAMES = {
    (1, 1): "slot_01",
    (3, 1): "slot_02",
    (1, 3): "slot_03",
    (3, 3): "slot_04",
}
LEDGER_PATCHES = (*SLOT_NAMES.values(), "airInlet", "airOutlet", "lowerOutlet")
IMAGE_PROBE = (
    "source /usr/lib/openfoam/openfoam2512/etc/bashrc && interIsoFoam -help >/dev/null 2>&1"
)
CASE_COMMAND = (
    "source /usr/lib/openfoam/openfoam2512/etc/bashrc; "
    "set -euo pipefail; "
    'run_stage() {{ local stage="$1"; shift; set +e; "$@"; '
    'local status=$?; set -e; printf \'P1_STAGE_EXIT stage=%s code=%s\\n\' "$stage" "$status"; '
    'return "$status"; }}; '
    "run_stage blockMesh blockMesh; "
    "run_stage checkMesh checkMesh -allTopology -allGeometry; "
    "run_stage decomposePar decomposePar -force; "
    "run_stage interIsoFoam mpirun -np {ranks} interIsoFoam -parallel; "
    "run_stage reconstructPar reconstructPar -latestTime"
)

CASE_STAGE_ORDER = ("blockMesh", "checkMesh", "decomposePar", "interIsoFoam", "reconstructPar")
CASE_STAGE_EXIT_PATTERN = re.compile(
    r"^P1_STAGE_EXIT stage=([A-Za-z][A-Za-z0-9]*) code=(-?\d+)\s*$"
)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_p1_execution_contract(
    contract: dict[str, object], *, ranks: int, memory_gib: int
) -> float:
    """Check approval state and caller limits against the frozen P1 contract."""
    review = contract.get("independent_review")
    if not isinstance(review, dict):
        raise ValueError("independent_review is missing from the P1 execution contract")
    if contract.get("execution_status") != "ready":
        raise ValueError("P1 execution_status is not ready")
    if review.get("decision") != "approved_with_revisions":
        raise ValueError("P1 scientific review is not approved")
    if review.get("amendment_1_review_decision") != "approved_with_revisions":
        raise ValueError("P1 sampling-convention amendment is not independently approved")
    if (
        not isinstance(review.get("amendment_1_reviewer"), str)
        or not review["amendment_1_reviewer"].strip()
    ):
        raise ValueError("P1 amendment reviewer identity is missing")
    if (
        not isinstance(review.get("amendment_1_reviewed_utc"), str)
        or not review["amendment_1_reviewed_utc"].strip()
    ):
        raise ValueError("P1 amendment review timestamp is missing")
    if review.get("execution_code_review") != "approved":
        raise ValueError("P1 execution code review is not approved")
    if (
        not isinstance(review.get("execution_code_reviewer"), str)
        or not review["execution_code_reviewer"].strip()
    ):
        raise ValueError("P1 execution code reviewer identity is missing")
    if (
        not isinstance(review.get("execution_code_reviewed_utc"), str)
        or not review["execution_code_reviewed_utc"].strip()
    ):
        raise ValueError("P1 execution code review timestamp is missing")
    reviewed_code_sha256 = contract.get("reviewed_code_sha256")
    required_reviewed_paths = {
        "Makefile",
        "scripts/analyze_restas_pilot.py",
        "scripts/run_restas_pilot.py",
        "scripts/analyze_restas_ledger.py",
        "scripts/doctor.py",
        "scripts/run_local.py",
    }
    if not isinstance(reviewed_code_sha256, dict) or set(reviewed_code_sha256) != (
        required_reviewed_paths
    ):
        raise ValueError("P1 code review must freeze every file in the local execution path")
    for relative_path in sorted(required_reviewed_paths):
        expected_hash = reviewed_code_sha256[relative_path]
        if (
            not isinstance(expected_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
        ):
            raise ValueError(f"P1 reviewed code hash is invalid for {relative_path}")
        actual_hash = _hash(ROOT / relative_path)
        if actual_hash != expected_hash:
            raise ValueError(f"P1 reviewed code hash no longer matches {relative_path}")

    amendment_path = ROOT / "experiments" / "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1.md"
    expected_amendment_sha256 = contract.get("protocol_document_sha256")
    if (
        not isinstance(expected_amendment_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_amendment_sha256) is None
        or _hash(amendment_path) != expected_amendment_sha256
    ):
        raise ValueError("P1 amendment document hash does not match its reviewed value")

    declared_protocol = {
        "experiment_id": "P1_SOURCE_EVENT_LEDGER",
        "protocol_revision": 2,
        "protocol_amendment_id": "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1",
        "source_profile_m_s": [[0.0, -4.8], [0.0795, -4.8], [0.0805, 0.0], [0.12, 0.0]],
        "continuous_expected_release_kg": 230.4,
        "alpha_phi_sampling_convention": "left_endpoint_of_completed_interval",
        "alpha_phi_left_sampled_expected_release_kg": 230.544,
        "alpha_phi_left_sampled_expected_release_per_slot_kg": 57.636,
        "phi_right_sampled_expected_release_kg": 230.256,
        "phi_right_sampled_expected_release_per_slot_kg": 57.564,
        "source_dose_tolerance_fraction": 0.001,
        "mass_ledger_tolerance_fraction_of_cumulative_source": 0.001,
        "fixed_delta_t_s": 1e-4,
        "expected_time_steps": 1200,
        "n_alpha_sub_cycles": 1,
        "max_courant": 0.5,
        "max_alpha_courant": 0.25,
        "hard_stop_on_courant_breach": True,
    }
    for name, expected in declared_protocol.items():
        if contract.get(name) != expected:
            raise ValueError(f"P1 {name} does not match the implemented, reviewed protocol")

    try:
        rank_limit = int(contract["mpi_ranks"])
        memory_limit = int(contract["max_memory_gib"])
        wall_timeout_s = float(contract["max_wall_time_s"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"P1 resource limits are missing or invalid: {error}") from error
    if rank_limit < 1 or rank_limit > 16:
        raise ValueError("P1 contract MPI ceiling must be between 1 and the reviewed 16 ranks")
    if memory_limit < 4 or memory_limit > 48:
        raise ValueError("P1 contract memory ceiling must be between 4 and the reviewed 48 GiB")
    if wall_timeout_s > 3600:
        raise ValueError("P1 contract wall-time ceiling cannot exceed the reviewed 3,600 s")
    if ranks > rank_limit:
        raise ValueError(f"P1 permits at most {rank_limit} MPI ranks")
    if memory_gib > memory_limit:
        raise ValueError(f"P1 permits at most {memory_limit} GiB of container memory")
    if not math.isfinite(wall_timeout_s) or wall_timeout_s <= 0:
        raise ValueError("P1 max_wall_time_s must be positive")
    return wall_timeout_s


def _analyze_p1_run(
    run_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    case_command_exit_code: int,
    case_stage_exit_records: list[dict[str, int | str]],
    report_builder: Callable[[Path], dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    """Persist stage and command statuses before the ledger analyzer reads the run."""
    stage_codes = {
        record["stage"]: record["exit_code"]
        for record in case_stage_exit_records
        if isinstance(record.get("stage"), str) and isinstance(record.get("exit_code"), int)
    }
    manifest["case_stage_exit_records"] = case_stage_exit_records
    manifest["case_command_exit_code"] = case_command_exit_code
    manifest["interisofoam_exit_code"] = stage_codes.get("interIsoFoam")
    manifest["reconstruction_exit_code"] = stage_codes.get("reconstructPar")
    manifest.pop("solver_exit_code", None)
    manifest["exit_code"] = case_command_exit_code
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = report_builder(run_dir)
    runner_exit_code = case_command_exit_code
    gate_decision = report.get("gate_decision")
    if case_command_exit_code == 0 and (
        manifest.get("interisofoam_exit_code") != 0
        or manifest.get("reconstruction_exit_code") != 0
        or not isinstance(gate_decision, dict)
        or not gate_decision.get("p1_ledger_passed")
    ):
        runner_exit_code = 1
    report_manifest = report.get("manifest")
    if isinstance(report_manifest, dict):
        report_manifest["runner_exit_code"] = runner_exit_code
    manifest["exit_code"] = runner_exit_code
    return report, runner_exit_code


def _case_stage_exit_records(log_path: Path) -> list[dict[str, int | str]]:
    """Read raw stage statuses embedded in the container log."""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        match = CASE_STAGE_EXIT_PATTERN.fullmatch(line.strip())
        if match is not None:
            records.append({"stage": match.group(1), "exit_code": int(match.group(2))})
    return records


def _execution_stop_reason(
    line: str,
    *,
    elapsed_s: float,
    courant_limits: tuple[float, float] | None,
    wall_timeout_s: float | None,
) -> str | None:
    """Return the declared hard-stop reason for one log line or elapsed time."""
    if wall_timeout_s is not None and elapsed_s >= wall_timeout_s:
        return f"wall-time limit of {wall_timeout_s:g} s reached"
    if courant_limits is None:
        return None
    global_match = re.search(r"^Courant Number mean:\s*[-+\deE.]+\s+max:\s*([-+\deE.]+)", line)
    alpha_match = re.search(
        r"^Interface Courant Number mean:\s*[-+\deE.]+\s+max:\s*([-+\deE.]+)", line
    )
    if global_match and float(global_match.group(1)) > courant_limits[0]:
        return f"global Co {float(global_match.group(1)):.8g} exceeded {courant_limits[0]:g}"
    if alpha_match and float(alpha_match.group(1)) > courant_limits[1]:
        return f"interface Co {float(alpha_match.group(1)):.8g} exceeded {courant_limits[1]:g}"
    return None


def _foam_header(
    object_name: str, foam_class: str = "dictionary", location: str | None = None
) -> str:
    location_line = f'    location    "{location}";\n' if location else ""
    return (
        "FoamFile\n{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {foam_class};\n"
        f"{location_line}"
        f"    object      {object_name};\n"
        "}\n\n"
    )


def _vertex_index(i: int, j: int, k: int) -> int:
    return k * len(X_BREAKS) * len(Y_BREAKS) + j * len(X_BREAKS) + i


def _face(vertices: tuple[int, int, int, int]) -> str:
    return "(" + " ".join(str(vertex) for vertex in vertices) + ")"


def _block_mesh_dict() -> str:
    vertices = []
    for z in DOMAIN["z"]:
        for y in Y_BREAKS:
            for x in X_BREAKS:
                vertices.append(f"    ({x:.8g} {y:.8g} {z:.8g})")

    blocks = []
    for j in range(len(Y_BREAKS) - 1):
        for i in range(len(X_BREAKS) - 1):
            ids = (
                _vertex_index(i, j, 0),
                _vertex_index(i + 1, j, 0),
                _vertex_index(i + 1, j + 1, 0),
                _vertex_index(i, j + 1, 0),
                _vertex_index(i, j, 1),
                _vertex_index(i + 1, j, 1),
                _vertex_index(i + 1, j + 1, 1),
                _vertex_index(i, j + 1, 1),
            )
            cell_count = f"({NX[i]} {NY[j]} {NZ})"
            blocks.append(
                "    hex (" + " ".join(map(str, ids)) + f") {cell_count} simpleGrading (1 1 1)"
            )

    top_faces: dict[str, list[str]] = {name: [] for name in SLOT_NAMES.values()}
    top_faces["airPlate"] = []
    inlet_faces: list[str] = []
    outlet_faces: list[str] = []
    side_min_faces: list[str] = []
    side_max_faces: list[str] = []
    lower_faces: list[str] = []

    for j in range(len(Y_BREAKS) - 1):
        for i in range(len(X_BREAKS) - 1):
            top = _face(
                (
                    _vertex_index(i, j, 1),
                    _vertex_index(i + 1, j, 1),
                    _vertex_index(i + 1, j + 1, 1),
                    _vertex_index(i, j + 1, 1),
                )
            )
            patch = SLOT_NAMES.get((i, j), "airPlate")
            top_faces[patch].append(top)
            lower_faces.append(
                _face(
                    (
                        _vertex_index(i, j, 0),
                        _vertex_index(i, j + 1, 0),
                        _vertex_index(i + 1, j + 1, 0),
                        _vertex_index(i + 1, j, 0),
                    )
                )
            )
            if i == 0:
                outlet_faces.append(
                    _face(
                        (
                            _vertex_index(i, j, 0),
                            _vertex_index(i, j, 1),
                            _vertex_index(i, j + 1, 1),
                            _vertex_index(i, j + 1, 0),
                        )
                    )
                )
            if i == len(X_BREAKS) - 2:
                inlet_faces.append(
                    _face(
                        (
                            _vertex_index(i + 1, j, 0),
                            _vertex_index(i + 1, j + 1, 0),
                            _vertex_index(i + 1, j + 1, 1),
                            _vertex_index(i + 1, j, 1),
                        )
                    )
                )
            if j == 0:
                side_min_faces.append(
                    _face(
                        (
                            _vertex_index(i, j, 0),
                            _vertex_index(i + 1, j, 0),
                            _vertex_index(i + 1, j, 1),
                            _vertex_index(i, j, 1),
                        )
                    )
                )
            if j == len(Y_BREAKS) - 2:
                side_max_faces.append(
                    _face(
                        (
                            _vertex_index(i, j + 1, 0),
                            _vertex_index(i, j + 1, 1),
                            _vertex_index(i + 1, j + 1, 1),
                            _vertex_index(i + 1, j + 1, 0),
                        )
                    )
                )

    patches = []
    for name, faces in top_faces.items():
        patch_type = "wall" if name == "airPlate" else "patch"
        patches.append(
            f"    {name}\n    {{\n        type {patch_type};\n        faces\n        (\n"
            + "\n".join(f"            {face}" for face in faces)
            + "\n        );\n    }\n"
        )
    boundary_data = (
        ("airInlet", "patch", inlet_faces),
        ("airOutlet", "patch", outlet_faces),
        ("sideMin", "symmetryPlane", side_min_faces),
        ("sideMax", "symmetryPlane", side_max_faces),
        ("lowerOutlet", "patch", lower_faces),
    )
    for name, patch_type, faces in boundary_data:
        patches.append(
            f"    {name}\n    {{\n        type {patch_type};\n        faces\n        (\n"
            + "\n".join(f"            {face}" for face in faces)
            + "\n        );\n    }\n"
        )

    return (
        _foam_header("blockMeshDict")
        + f"scale 1;\n\nvertices\n(\n{chr(10).join(vertices)}\n);\n\n"
        + f"blocks\n(\n{chr(10).join(blocks)}\n);\n\nedges ();\n\nboundary\n(\n"
        + "\n".join(patches)
        + ");\n\nmergePatchPairs ();\n"
    )


def _boundary_field(
    header: str, field_class: str, dimensions: str, internal: str, patches: dict[str, str]
) -> str:
    body = "\n".join(
        f"    {name}\n    {{\n{contents}\n    }}" for name, contents in patches.items()
    )
    return (
        _foam_header(header, field_class)
        + f"dimensions {dimensions};\n\ninternalField uniform {internal};\n\nboundaryField\n{{\n{body}\n}}\n"
    )


def _surface_flux_function_object(name: str, patch: str) -> str:
    return (
        f"    {name}\n    {{\n"
        "        type surfaceFieldValue;\n"
        "        libs (fieldFunctionObjects);\n"
        "        regionType patch;\n"
        f"        name {patch};\n"
        "        operation sum;\n"
        "        fields (phi alphaPhi_);\n"
        "        writeFields false;\n"
        "        executeControl timeStep;\n"
        "        executeInterval 1;\n"
        "        writeControl timeStep;\n"
        "        writeInterval 1;\n"
        "    }\n"
    )


def _write_case(
    case_dir: Path, ranks: int, *, source_event_ledger: bool = False
) -> dict[str, object]:
    system = case_dir / "system"
    constant = case_dir / "constant"
    initial = case_dir / "0"
    for directory in (system, constant, initial):
        directory.mkdir(parents=True, exist_ok=True)

    source_table = (
        "((0 (0 0 -4.8)) (0.0795 (0 0 -4.8)) (0.0805 (0 0 0)) (0.12 (0 0 0)))"
        if source_event_ledger
        else "((0 (0 0 -4.8)) (0.08 (0 0 -4.8)) (0.0800001 (0 0 0)) (0.12 (0 0 0)))"
    )
    source_patch_u = (
        "        type uniformFixedValue;\n"
        f"        uniformValue table {source_table};\n"
        "        value uniform (0 0 -4.8);"
    )
    patches_u = {
        "slot_01": source_patch_u,
        "slot_02": source_patch_u,
        "slot_03": source_patch_u,
        "slot_04": source_patch_u,
        "airPlate": "        type noSlip;",
        "airInlet": "        type fixedValue;\n        value uniform (-50 0 0);",
        "airOutlet": "        type pressureInletOutletVelocity;\n        value uniform (-50 0 0);",
        "sideMin": "        type symmetryPlane;",
        "sideMax": "        type symmetryPlane;",
        "lowerOutlet": "        type pressureInletOutletVelocity;\n        value uniform (0 0 -4.8);",
    }
    patches_alpha = {
        "slot_01": "        type fixedValue;\n        value uniform 1;",
        "slot_02": "        type fixedValue;\n        value uniform 1;",
        "slot_03": "        type fixedValue;\n        value uniform 1;",
        "slot_04": "        type fixedValue;\n        value uniform 1;",
        "airPlate": "        type zeroGradient;",
        "airInlet": "        type fixedValue;\n        value uniform 0;",
        "airOutlet": "        type inletOutlet;\n        inletValue uniform 0;\n        value uniform 0;",
        "sideMin": "        type symmetryPlane;",
        "sideMax": "        type symmetryPlane;",
        "lowerOutlet": "        type inletOutlet;\n        inletValue uniform 0;\n        value uniform 0;",
    }
    patches_p = {
        name: "        type fixedFluxPressure;\n        value uniform 0;"
        for name in ("slot_01", "slot_02", "slot_03", "slot_04", "airPlate", "airInlet")
    }
    patches_p.update(
        {
            "airOutlet": "        type fixedValue;\n        value uniform 0;",
            "sideMin": "        type symmetryPlane;",
            "sideMax": "        type symmetryPlane;",
            "lowerOutlet": "        type fixedValue;\n        value uniform 0;",
        }
    )
    (system / "blockMeshDict").write_text(_block_mesh_dict(), encoding="utf-8")
    (initial / "U").write_text(
        _boundary_field("U", "volVectorField", "[0 1 -1 0 0 0 0]", "(-50 0 0)", patches_u),
        encoding="utf-8",
    )
    (initial / "alpha.water").write_text(
        _boundary_field("alpha.water", "volScalarField", "[0 0 0 0 0 0 0]", "0", patches_alpha),
        encoding="utf-8",
    )
    (initial / "p_rgh").write_text(
        _boundary_field("p_rgh", "volScalarField", "[1 -1 -2 0 0 0 0]", "0", patches_p),
        encoding="utf-8",
    )
    (constant / "g").write_text(
        _foam_header("g", "uniformDimensionedVectorField", "constant")
        + "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 -9.81);\n",
        encoding="utf-8",
    )
    (constant / "transportProperties").write_text(
        _foam_header("transportProperties", location="constant")
        + "phases (water air);\n\n"
        + "water { transportModel Newtonian; nu 1.0e-6; rho 1000; }\n"
        + "air { transportModel Newtonian; nu 1.48e-5; rho 1.225; }\n\n"
        + "sigma 0.072;\n",
        encoding="utf-8",
    )
    (constant / "turbulenceProperties").write_text(
        _foam_header("turbulenceProperties", location="constant") + "simulationType laminar;\n",
        encoding="utf-8",
    )
    (system / "controlDict").write_text(
        _foam_header("controlDict", location="system")
        + "application interIsoFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\n"
        + "endTime 0.12;\ndeltaT 1e-4;\nwriteControl adjustableRunTime;\nwriteInterval 0.02;\n"
        + "purgeWrite 0;\nwriteFormat binary;\nwritePrecision 8;\nwriteCompression off;\n"
        + "timeFormat fixed;\ntimePrecision 6;\nrunTimeModifiable no;\n"
        + f"adjustTimeStep {'no' if source_event_ledger else 'yes'};\n"
        + "maxCo 0.5;\nmaxAlphaCo 0.25;\nmaxDeltaT 5e-4;\n\n"
        + "functions\n{\n"
        + "    liquidInterface\n    {\n        type surfaces;\n        libs (geometricVoF sampling);\n"
        + "        writeControl writeTime;\n        surfaceFormat vtp;\n        fields (alpha.water U);\n"
        + "        interpolationScheme cell;\n        surfaces\n        {\n            freeSurface\n            {\n"
        + "                type interface;\n                interpolate false;\n            }\n        }\n    }\n"
        + "    waterVolume\n    {\n        type volFieldValue;\n        libs (fieldFunctionObjects);\n"
        + "        writeControl timeStep;\n"
        + f"        writeInterval {1 if source_event_ledger else 10};\n"
        + "        operation volIntegrate;\n"
        + "        writeFields false;\n"
        + "        fields (alpha.water);\n    }\n"
        + (
            "".join(
                _surface_flux_function_object(f"{patch}Flux", patch) for patch in LEDGER_PATCHES
            )
            if source_event_ledger
            else ""
        )
        + "}\n",
        encoding="utf-8",
    )
    (system / "fvSchemes").write_text(
        _foam_header("fvSchemes", location="system")
        + "ddtSchemes { default Euler; }\n"
        + "gradSchemes { default Gauss linear; }\n"
        + "divSchemes\n{\n    div(rhoPhi,U) Gauss limitedLinearV 1;\n"
        + "    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;\n}\n"
        + "laplacianSchemes { default Gauss linear corrected; }\n"
        + "interpolationSchemes { default linear; }\n"
        + "snGradSchemes { default corrected; }\n"
        + "fluxRequired { default no; p_rgh; pcorr; alpha.water; }\n",
        encoding="utf-8",
    )
    (system / "fvSolution").write_text(
        _foam_header("fvSolution", location="system")
        + 'solvers\n{\n    "alpha.water.*"\n    {\n'
        + "        isoFaceTol 1e-6;\n        surfCellTol 1e-6;\n        nAlphaBounds 3;\n"
        + "        snapTol 1e-12;\n        clip true;\n        reconstructionScheme isoAlpha;\n"
        + "        writeFields true;\n        nAlphaSubCycles 1;\n        cAlpha 1;\n    }\n"
        + '    "pcorr.*" { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0; }\n'
        + "    p_rgh { solver GAMG; smoother DICGaussSeidel; tolerance 1e-9; relTol 0.05; }\n"
        + "    p_rghFinal { $p_rgh; tolerance 1e-9; relTol 0; }\n"
        + "    U { solver PBiCGStab; preconditioner DILU; tolerance 1e-6; relTol 0; }\n}\n"
        + "PIMPLE\n{\n    momentumPredictor no;\n    nCorrectors 3;\n    nOuterCorrectors 1;\n"
        + "    nNonOrthogonalCorrectors 0;\n    pRefCell 0;\n    pRefValue 0;\n}\n",
        encoding="utf-8",
    )
    (system / "decomposeParDict").write_text(
        _foam_header("decomposeParDict", location="system")
        + f"numberOfSubdomains {ranks};\nmethod simple;\ncoeffs {{ n ({ranks} 1 1); }}\n",
        encoding="utf-8",
    )
    expected_flux = 1000.0 * 4.0 * 1.0 * 0.15 * 4.8
    released_mass = expected_flux * 0.08
    details: dict[str, object] = {
        "solver": "interIsoFoam",
        "openfoam_image": IMAGE,
        "geometry_class": "four distinct rectangular slot patches in a flat plate",
        "evidence_label": "provisional characterization pilot; not a Restas measurement or validation",
        "coordinate_frame": {
            "x": "along-track; aircraft-frame crossflow is negative",
            "y": "cross-track",
            "z": "upward",
        },
        "domain_bounds_m": DOMAIN,
        "mesh_cells_expected": sum(NX) * sum(NY) * NZ,
        "slot_count": 4,
        "slot_dimensions_m": {"short_axis_x": 0.15, "long_axis_y": 1.0},
        "slot_edge_gap_m": {"x": 0.05, "y": 0.05},
        "mesh_cell_width_m": {"slot_region": 0.05, "outer_x_region": 0.075, "y": 0.05, "z": 0.05},
        "cells_across_slot_short_axis": 3,
        "source_velocity_m_s": [0.0, 0.0, -4.8],
        "source_window_s": [0.0, 0.08],
        "source_shutoff_s": 0.08,
        "crossflow_m_s": [-50.0, 0.0, 0.0],
        "crossflow_evidence": "Calbrix et al. (2023), local PDF, reference relative airflow; this is an idealized aircraft-frame condition",
        "source_speed_evidence": "Calbrix et al. (2023), local PDF, Dash-8 peak; borrowed as a provisional constant Restas-source speed",
        "outlet_area_m2": 4.0 * 0.15,
        "expected_source_mass_flow_kg_s": expected_flux,
        "expected_released_mass_kg": released_mass,
        "water": {"density_kg_m3": 1000.0, "kinematic_viscosity_m2_s": 1.0e-6},
        "air": {"density_kg_m3": 1.225, "kinematic_viscosity_m2_s": 1.48e-5},
        "surface_tension_N_m": 0.072,
        "gravity_m_s2": [0.0, 0.0, -9.81],
        "turbulence_model": "laminar; deliberately characterization-only at these high Reynolds numbers",
        "end_time_s": 0.12,
        "max_courant": 0.5,
        "max_alpha_courant": 0.25,
        "snapshot_interval_s": 0.02,
        "scope_limitations": [
            "no aircraft body or wake",
            "no descent through flight altitude or ground impact",
            "no turbulence closure, parcels, foam, evaporation, fire, or post-impact dynamics",
            "not a GPU pilot, paper benchmark, field validation, or built-system prediction",
        ],
    }
    if source_event_ledger:
        details.update(
            {
                "experiment_id": "P1_SOURCE_EVENT_LEDGER",
                "protocol_revision": 2,
                "protocol_amendment_id": "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1",
                "evidence_label": "provisional source-event and conservative ledger diagnostic",
                "source_profile_m_s": [
                    [0.0, -4.8],
                    [0.0795, -4.8],
                    [0.0805, 0.0],
                    [0.12, 0.0],
                ],
                "source_constant_velocity_interval_s": [0.0, 0.0795],
                "source_window_s": [0.0, 0.0805],
                "source_shutoff_s": 0.0805,
                "source_shutoff_ramp_s": [0.0795, 0.0805],
                "alpha_phi_sampling_convention": "left_endpoint_of_completed_interval",
                "alpha_phi_left_sampled_expected_release_kg": 230.544,
                "alpha_phi_left_sampled_expected_release_per_slot_kg": 57.636,
                "phi_right_sampled_expected_release_kg": 230.256,
                "phi_right_sampled_expected_release_per_slot_kg": 57.564,
                "time_step_mode": "fixed",
                "fixed_delta_t_s": 1.0e-4,
                "adjust_time_step": False,
                "expected_time_steps": 1200,
                "n_alpha_sub_cycles": 1,
                "source_dose_tolerance_fraction": 0.001,
                "mass_ledger_tolerance_fraction": 0.001,
                "flux_field": "alphaPhi_",
                "flux_patch_names": list(LEDGER_PATCHES),
                "flux_sample_interval_steps": 1,
                "volume_sample_interval_steps": 1,
                "hard_stop_on_courant_breach": True,
                "scope_limitations": [
                    *details["scope_limitations"],
                    "source event and mass ledger diagnostic only; not a validation gate",
                    "no mesh or time-step convergence claim",
                ],
            }
        )
    return details


def _docker_image_id() -> str:
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode:
        raise RuntimeError(
            f"Required Docker image {IMAGE!r} is not available locally; see docs/COMPUTE.md"
        )
    return result.stdout.strip()


def _git_revision() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=False, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _run_container(
    case_dir: Path,
    run_dir: Path,
    run_id: str,
    ranks: int,
    memory_gib: int,
    *,
    courant_limits: tuple[float, float] | None = None,
    wall_timeout_s: float | None = None,
    monitor_interval_s: float = 2.0,
) -> tuple[int, list[dict[str, str]], str | None, bool | None, str | None, list[str]]:
    docker_command = [
        "docker",
        "run",
        "--rm",
        "--name",
        run_id,
        f"--cpus={ranks + 2}",
        f"--memory={memory_gib}g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={case_dir},dst=/case",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        IMAGE,
        "-c",
        CASE_COMMAND.format(ranks=ranks),
    ]
    log_path = run_dir / "openfoam-console.log"
    samples: list[dict[str, str]] = []
    stop_sampling = threading.Event()
    stop_reason: list[str | None] = [None]
    stop_confirmed: list[bool | None] = [None]
    stop_error: list[str | None] = [None]
    monitor_errors: list[str] = []
    process_ref: list[subprocess.Popen[str] | None] = [None]
    stop_lock = threading.Lock()

    def stop_container(reason: str) -> None:
        with stop_lock:
            if stop_reason[0] is not None:
                return
            stop_reason[0] = reason
            stop_confirmed[0] = False
        print(f"[run_restas_pilot] stopping container: {reason}", file=sys.stderr, flush=True)
        stop_command_error = None
        try:
            stopped = subprocess.run(
                ["docker", "stop", "--time", "2", run_id],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as error:
            stopped = None
            stop_command_error = f"docker stop failed: {type(error).__name__}: {error}"
        if stopped is not None and stopped.returncode == 0:
            stop_confirmed[0] = True
            return

        if stopped is not None:
            stop_command_error = (
                f"docker stop returned {stopped.returncode}: {stopped.stderr.strip()}"
            )
        try:
            killed = subprocess.run(
                ["docker", "kill", run_id],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as error:
            killed = None
            kill_command_error = f"docker kill failed: {type(error).__name__}: {error}"
        else:
            kill_command_error = (
                None
                if killed.returncode == 0
                else f"docker kill returned {killed.returncode}: {killed.stderr.strip()}"
            )
        if killed is not None and killed.returncode == 0:
            stop_confirmed[0] = True
            return

        stop_error[0] = "; ".join(
            message for message in (stop_command_error, kill_command_error) if message
        )
        process = process_ref[0]
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError as error:
                stop_error[0] += f"; could not terminate docker client: {error}"

    def sample_resources() -> None:
        while not stop_sampling.wait(monitor_interval_s):
            if stop_reason[0] is not None:
                return
            reason = _execution_stop_reason(
                "",
                elapsed_s=time.monotonic() - started,
                courant_limits=None,
                wall_timeout_s=wall_timeout_s,
            )
            if reason is not None:
                stop_container(reason)
                return
            try:
                sample = subprocess.run(
                    [
                        "docker",
                        "stats",
                        "--no-stream",
                        "--format",
                        "{{.MemUsage}}|{{.CPUPerc}}|{{.MemPerc}}",
                        run_id,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError) as error:
                monitor_errors.append(f"docker stats failed: {type(error).__name__}: {error}")
                continue
            if sample.returncode == 0 and sample.stdout.strip():
                samples.append(
                    {
                        "elapsed_s": f"{time.monotonic() - started:.3f}",
                        "memory_usage_and_limit": sample.stdout.strip().split("|")[0],
                        "cpu_percent": sample.stdout.strip().split("|")[1],
                        "memory_percent": sample.stdout.strip().split("|")[2],
                    }
                )

    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            docker_command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        process_ref[0] = process
        assert process.stdout is not None
        monitor = threading.Thread(target=sample_resources, daemon=True)
        monitor.start()
        try:
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log_file.write(line)
                log_file.flush()
                reason = _execution_stop_reason(
                    line,
                    elapsed_s=time.monotonic() - started,
                    courant_limits=courant_limits,
                    wall_timeout_s=wall_timeout_s,
                )
                if reason is not None:
                    stop_container(reason)
            return_code = process.wait()
        finally:
            stop_sampling.set()
            monitor.join(timeout=6)
    post_run_wall_reason = _execution_stop_reason(
        "",
        elapsed_s=time.monotonic() - started,
        courant_limits=None,
        wall_timeout_s=wall_timeout_s,
    )
    if post_run_wall_reason is not None and stop_reason[0] is None:
        stop_reason[0] = f"{post_run_wall_reason} before solver completion was observed"
        stop_confirmed[0] = False
    if return_code < 0:
        return_code = 128 - return_code
    if return_code == 0 and stop_reason[0] is not None:
        return_code = 124 if stop_reason[0].startswith("wall-time limit") else 1
    if stop_error[0] is not None and return_code == 0:
        return_code = 127
    return (
        return_code,
        samples,
        stop_reason[0],
        stop_confirmed[0],
        stop_error[0],
        monitor_errors,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=min(16, effective_cpu_count()))
    parser.add_argument("--memory-gib", type=int, default=48)
    parser.add_argument(
        "--source-event-ledger",
        action="store_true",
        help="prepare or run the reviewed P1 source-event and liquid-ledger diagnostic",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="write the case and manifest without running OpenFOAM",
    )
    args = parser.parse_args(argv)
    experiment_path = ROOT / "experiments" / "P1_SOURCE_EVENT_LEDGER.md"
    amendment_path = ROOT / "experiments" / "P1_SOURCE_EVENT_LEDGER_AMENDMENT_1.md"
    execution_contract_path = ROOT / "experiments" / "P1_SOURCE_EVENT_LEDGER.execution.json"
    ledger_analyzer_path = ROOT / "scripts" / "analyze_restas_ledger.py"
    ledger_report_builder = None
    wall_timeout_s = None
    if args.source_event_ledger and not experiment_path.is_file():
        parser.error(f"P1 experiment record is missing: {experiment_path}")
    if args.source_event_ledger and not amendment_path.is_file():
        parser.error(f"P1 protocol amendment is missing: {amendment_path}")
    if args.source_event_ledger and not ledger_analyzer_path.is_file():
        parser.error(f"P1 ledger analyzer is missing: {ledger_analyzer_path}")
    if args.source_event_ledger:
        try:
            from analyze_restas_ledger import build_ledger_report
        except (ImportError, SyntaxError) as error:
            parser.error(f"P1 ledger analyzer cannot be imported: {error}")
        if not callable(build_ledger_report):
            parser.error("P1 ledger analyzer does not expose build_ledger_report")
        ledger_report_builder = build_ledger_report
        try:
            execution_contract = json.loads(execution_contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            parser.error(f"cannot read the P1 execution contract: {error}")
        try:
            wall_timeout_s = float(execution_contract["max_wall_time_s"])
        except (KeyError, TypeError, ValueError) as error:
            parser.error(f"P1 max_wall_time_s is missing or invalid: {error}")
        if not math.isfinite(wall_timeout_s) or wall_timeout_s <= 0:
            parser.error("P1 max_wall_time_s must be a positive finite value")
        if not args.prepare_only:
            try:
                wall_timeout_s = _validate_p1_execution_contract(
                    execution_contract, ranks=args.threads, memory_gib=args.memory_gib
                )
            except ValueError as error:
                parser.error(f"P1 execution is blocked: {error}")
    available = effective_cpu_count()
    if args.threads < 1 or args.threads > max(1, available - 2):
        parser.error(f"--threads must be 1..{max(1, available - 2)} to keep two CPUs available")
    if args.memory_gib < 4:
        parser.error("--memory-gib must be at least 4")
    if not args.prepare_only:
        try:
            image_id = _docker_image_id()
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as error:
            parser.error(str(error))
        probe = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "/bin/bash", IMAGE, "-c", IMAGE_PROBE],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if probe.returncode:
            parser.error(f"OpenFOAM solver probe failed inside {IMAGE}: {probe.stderr.strip()}")
    else:
        image_id = "not-probed"

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    prefix = "restas-source-ledger" if args.source_event_ledger else "restas-cpu-vof"
    run_id = f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"
    run_dir = ROOT / "results" / "runs" / run_id
    case_dir = run_dir / "case"
    case_dir.mkdir(parents=True, exist_ok=False)
    inputs = _write_case(case_dir, args.threads, source_event_ledger=args.source_event_ledger)
    inputs_path = run_dir / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_paths = [
        Path(__file__),
        ROOT / "cases" / "restas_four_slot" / "README.md",
        ROOT / "scripts" / "run_local.py",
        ROOT / "scripts" / "doctor.py",
        ROOT / "scripts" / "analyze_restas_pilot.py",
        ROOT / "track2_aerial_drop_experiment_plan.md",
        ROOT
        / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf",
    ]
    if args.source_event_ledger:
        source_paths.extend(
            [
                experiment_path,
                amendment_path,
                execution_contract_path,
                ledger_analyzer_path,
            ]
        )
    git_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=False, capture_output=True, text=True
    ).stdout
    manifest = {
        "run_id": run_id,
        "started_utc": datetime.now(UTC).isoformat(),
        "git_revision": _git_revision(),
        "git_worktree_dirty": bool(git_status.strip()),
        "source_sha256": {str(path.relative_to(ROOT)): _hash(path) for path in source_paths},
        "inputs_sha256": _hash(inputs_path),
        "prepared_case_file_hashes": {
            str(path.relative_to(case_dir)): _hash(path)
            for path in sorted(case_dir.rglob("*"))
            if path.is_file() and path.relative_to(case_dir).parts[0] in {"0", "constant", "system"}
        },
        "solver_image": IMAGE,
        "solver_image_id": image_id,
        "execution": {
            "mpi_ranks": args.threads,
            "docker_cpu_limit": args.threads + 2,
            "docker_memory_limit_gib": args.memory_gib,
            "wall_time_limit_s": wall_timeout_s,
            "hard_stop_courant_limits": (
                {
                    "global": inputs["max_courant"],
                    "interface": inputs["max_alpha_courant"],
                }
                if args.source_event_ledger
                else None
            ),
        },
        "scope": (
            "P1 provisional source-event and conservative ledger diagnostic only; no E1-E6 or design claim"
            if args.source_event_ledger
            else "CPU characterization pilot only; no E1-E6 or design claim"
        ),
    }
    if args.source_event_ledger:
        independent_review = execution_contract["independent_review"]
        manifest["independent_review"] = {
            "execution_status": execution_contract.get("execution_status"),
            "protocol_revision": execution_contract.get("protocol_revision"),
            "protocol_amendment_id": execution_contract.get("protocol_amendment_id"),
            "protocol_decision": independent_review.get("decision"),
            "protocol_reviewer": independent_review.get("reviewer"),
            "amendment_1_review_decision": independent_review.get("amendment_1_review_decision"),
            "amendment_1_reviewer": independent_review.get("amendment_1_reviewer"),
            "amendment_1_reviewed_utc": independent_review.get("amendment_1_reviewed_utc"),
            "execution_code_review": independent_review.get("execution_code_review"),
            "execution_code_reviewer": independent_review.get("execution_code_reviewer"),
            "execution_code_reviewed_utc": independent_review.get("execution_code_reviewed_utc"),
        }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Run directory: {run_dir.relative_to(ROOT)}", flush=True)
    print(f"Expected mesh cells: {inputs['mesh_cells_expected']:,}", flush=True)
    print(
        f"Continuous analytic water dose: {inputs['expected_released_mass_kg']:.3f} kg", flush=True
    )
    if args.source_event_ledger:
        print(
            "alphaPhi_ left-step dose target: 230.544 kg (57.636 kg per slot); "
            "continuous target: 230.400 kg",
            flush=True,
        )
    print(f"Provisional input manifest: {inputs_path.relative_to(ROOT)}", flush=True)
    if args.prepare_only:
        return 0

    started = time.monotonic()
    try:
        return_code, resource_samples, stop_reason, stop_confirmed, stop_error, monitor_errors = (
            _run_container(
                case_dir,
                run_dir,
                run_id,
                args.threads,
                args.memory_gib,
                courant_limits=(inputs["max_courant"], inputs["max_alpha_courant"])
                if args.source_event_ledger
                else None,
                wall_timeout_s=wall_timeout_s,
            )
        )
    except (OSError, subprocess.SubprocessError) as error:
        return_code = 127
        resource_samples = []
        stop_reason = None
        stop_confirmed = None
        stop_error = f"{type(error).__name__}: {error}"
        monitor_errors = []
        (run_dir / "launcher-error.txt").write_text(f"{stop_error}\n", encoding="utf-8")
    elapsed = time.monotonic() - started
    manifest["finished_utc"] = datetime.now(UTC).isoformat()
    manifest["wall_time_s"] = elapsed
    manifest["exit_code"] = return_code
    stage_exit_records = _case_stage_exit_records(run_dir / "openfoam-console.log")
    stage_codes = {record["stage"]: record["exit_code"] for record in stage_exit_records}
    manifest["case_command_exit_code"] = return_code
    manifest["case_stage_exit_records"] = stage_exit_records
    manifest["interisofoam_exit_code"] = stage_codes.get("interIsoFoam")
    manifest["reconstruction_exit_code"] = stage_codes.get("reconstructPar")
    manifest["stop_reason"] = stop_reason
    manifest["stop_confirmed"] = stop_confirmed
    manifest["stop_error"] = stop_error
    manifest["resource_monitor_errors"] = monitor_errors
    manifest["docker_resource_samples"] = resource_samples
    manifest["resource_sample_note"] = (
        "docker stats snapshots at approximately 2 s intervals; peak between samples may be higher"
    )
    manifest["case_file_hashes"] = {
        str(path.relative_to(case_dir)): _hash(path)
        for path in sorted(case_dir.rglob("*"))
        if path.is_file() and path.relative_to(case_dir).parts[0] in {"0", "constant", "system"}
    }
    manifest["surface_artifact_hashes"] = {
        str(path.relative_to(run_dir)): _hash(path)
        for path in sorted((case_dir / "postProcessing").rglob("*.vtp"))
        if path.is_file()
    }
    if args.source_event_ledger:
        assert ledger_report_builder is not None
        ledger_report, return_code = _analyze_p1_run(
            run_dir,
            manifest_path,
            manifest,
            return_code,
            stage_exit_records,
            ledger_report_builder,
        )
        (run_dir / "ledger-report.json").write_text(
            json.dumps(ledger_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    else:
        manifest["exit_code"] = return_code
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (run_dir / "pilot-report.json").write_text(
            json.dumps(build_report(run_dir), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    manifest["diagnostic_artifact_hashes"] = {
        str(path.relative_to(run_dir)): _hash(path)
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
        and (
            path.name == "openfoam-console.log"
            or path.name in {"ledger-report.json", "pilot-report.json"}
            or ("postProcessing" in path.parts and path.suffix == ".dat")
        )
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
