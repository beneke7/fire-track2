#!/usr/bin/env python3
"""Prepare and durably launch an exploratory CPU pilot for Rouaix Table 3 Case 4.

The case uses the published single-nozzle flow conditions with an explicitly
provisional structured mesh and flat roof. It is a mesh/runtime precursor, not
a reproduction of the paper's polyhedral/prism mesh or an E1 acceptance run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

try:
    from audit_interface_wave_flux import (
        EXPECTED_ALPHA_DIMENSIONS,
        read_volume_scalar_field,
        read_volume_vector_internal,
    )
except ModuleNotFoundError:
    from scripts.audit_interface_wave_flux import (
        EXPECTED_ALPHA_DIMENSIONS,
        read_volume_scalar_field,
        read_volume_vector_internal,
    )

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CASE = ROOT / "cases/e1_rouaix_case1_static/case"
SOURCE_RECORD = ROOT / "experiments/E1_ROUAIX_CASE1_SOURCE.md"
SOURCE_PDF = ROOT / "Rouaix_28516.pdf"
SOURCE_EXTRACTION = (
    ROOT / "results/runs/rouaix-paper-next-step-20261006T064225Z/paper-next-step.json"
)
RUNS_ROOT = ROOT / "results/runs"
IMAGE = "opencfd/openfoam-default:2512"
PINNED_IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
OPENFOAM_BASHRC = "/usr/lib/openfoam/openfoam2512/etc/bashrc"

X_NODES = (-2.5, -0.5, 0.5, 4.5, 17.5)
X_COUNTS = (8, 29, 58, 26)
Y_NODES = (-10.0, -4.0, -1.0, 0.0)
Y_COUNTS = (24, 43, 29)
Z_CELLS = 160
MPI_DECOMPOSITIONS = {4: (2, 2, 1), 16: (4, 2, 2), 20: (5, 2, 2)}
LAYOUT_PROFILES = {
    "starter_70mm_corridor": {
        "x_nodes": (-2.5, -0.5, 0.5, 4.5, 17.5),
        "x_counts": (8, 29, 58, 26),
        "y_nodes": (-10.0, -4.0, -1.0, 0.0),
        "y_counts": (24, 43, 29),
        "z_cells": 160,
        "target_x": (0.0, 4.0),
        "target_y": (-4.0, 0.0),
        "description": "starter local <=70mm corridor x=0..4m, y=-4..0m",
    },
    "breakup_70mm_corridor": {
        "x_nodes": (-2.5, -0.5, 0.5, 6.5, 17.5),
        "x_counts": (8, 29, 87, 22),
        "y_nodes": (-10.0, -6.0, -1.0, 0.0),
        "y_counts": (16, 72, 29),
        "z_cells": 160,
        "target_x": (0.0, 6.5),
        "target_y": (-6.0, 0.0),
        "description": "extended x/y corridor for breakup precursor; z=77.5mm at y=-6m, preserving 160-cell source/top resolution",
    },
}
ACTIVE_LAYOUT_PROFILE = "starter_70mm_corridor"
TOP_HALF_SPAN_M = 3.5
BOTTOM_HALF_SPAN_M = 8.0
DIAMETER_M = 0.4
RADIUS_M = DIAMETER_M / 2
WATER_SPEED_M_S = 10.0
AIR_SPEED_M_S = 70.0
RHO_WATER_KG_M3 = 997.6
DEFAULT_END_TIME_S = 0.03
DEFAULT_DT_S = 0.001
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{12,64}$")


class PilotError(RuntimeError):
    """An input, setup, mesh, or solver stage failed."""


def _activate_layout(profile: str) -> None:
    """Select one declared structured layout for this run process."""
    global ACTIVE_LAYOUT_PROFILE, X_NODES, X_COUNTS, Y_NODES, Y_COUNTS, Z_CELLS
    if profile not in LAYOUT_PROFILES:
        raise ValueError(f"unknown Rouaix pilot mesh profile {profile!r}")
    layout = LAYOUT_PROFILES[profile]
    ACTIVE_LAYOUT_PROFILE = profile
    X_NODES = layout["x_nodes"]
    X_COUNTS = layout["x_counts"]
    Y_NODES = layout["y_nodes"]
    Y_COUNTS = layout["y_counts"]
    Z_CELLS = layout["z_cells"]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _vertex_id(ix: int, iy: int, side: int) -> int:
    return (iy * 2 + side) * len(X_NODES) + ix


def _half_span(y_m: float) -> float:
    fraction = (y_m - Y_NODES[0]) / (Y_NODES[-1] - Y_NODES[0])
    return BOTTOM_HALF_SPAN_M + fraction * (TOP_HALF_SPAN_M - BOTTOM_HALF_SPAN_M)


def _foam_header(name: str, object_class: str = "dictionary") -> str:
    return f"""FoamFile
{{
    version 2.0;
    format ascii;
    class {object_class};
    object {name};
}}
"""


def _block_mesh_dict() -> str:
    lines = [_foam_header("blockMeshDict"), "convertToMeters 1;", "", "vertices", "("]
    for iy, y_m in enumerate(Y_NODES):
        span = _half_span(y_m)
        for side, z_m in enumerate((-span, span)):
            for x_m in X_NODES:
                lines.append(f"    ({x_m:.9g} {y_m:.9g} {z_m:.9g})")
    lines.extend([");", "", "blocks", "("])
    for iy in range(len(Y_NODES) - 1):
        for ix in range(len(X_NODES) - 1):
            v = (
                _vertex_id(ix, iy, 0),
                _vertex_id(ix + 1, iy, 0),
                _vertex_id(ix + 1, iy + 1, 0),
                _vertex_id(ix, iy + 1, 0),
                _vertex_id(ix, iy, 1),
                _vertex_id(ix + 1, iy, 1),
                _vertex_id(ix + 1, iy + 1, 1),
                _vertex_id(ix, iy + 1, 1),
            )
            lines.append(
                "    hex ({} ) ({} {} {}) simpleGrading (1 1 1)".format(
                    " ".join(map(str, v)), X_COUNTS[ix], Y_COUNTS[iy], Z_CELLS
                )
            )
    lines.extend([");", "", "edges", "(", ");", "", "boundary", "("])
    lines.extend(
        [
            "    gasInlet { type patch; faces (",
            *[
                f"        ({_vertex_id(0, j, 0)} {_vertex_id(0, j, 1)} {_vertex_id(0, j + 1, 1)} {_vertex_id(0, j + 1, 0)})"
                for j in range(len(Y_NODES) - 1)
            ],
            "    ); }",
            "    downstreamOutlet { type patch; faces (",
            *[
                f"        ({_vertex_id(len(X_NODES) - 1, j, 0)} {_vertex_id(len(X_NODES) - 1, j + 1, 0)} {_vertex_id(len(X_NODES) - 1, j + 1, 1)} {_vertex_id(len(X_NODES) - 1, j, 1)})"
                for j in range(len(Y_NODES) - 1)
            ],
            "    ); }",
            "    bottomOutlet { type patch; faces (",
            *[
                f"        ({_vertex_id(i, 0, 0)} {_vertex_id(i + 1, 0, 0)} {_vertex_id(i + 1, 0, 1)} {_vertex_id(i, 0, 1)})"
                for i in range(len(X_NODES) - 1)
            ],
            "    ); }",
            "    aircraftWall { type wall; faces (",
            *[
                f"        ({_vertex_id(i, len(Y_NODES) - 1, 0)} {_vertex_id(i, len(Y_NODES) - 1, 1)} {_vertex_id(i + 1, len(Y_NODES) - 1, 1)} {_vertex_id(i + 1, len(Y_NODES) - 1, 0)})"
                for i in range(len(X_NODES) - 1)
            ],
            "    ); }",
            "    spanwiseMinus { type patch; faces (",
        ]
    )
    lines.extend(
        f"        ({_vertex_id(i, j, 0)} {_vertex_id(i, j + 1, 0)} {_vertex_id(i + 1, j + 1, 0)} {_vertex_id(i + 1, j, 0)})"
        for i in range(len(X_NODES) - 1)
        for j in range(len(Y_NODES) - 1)
    )
    lines.extend(["    ); }", "    spanwisePlus { type patch; faces ("])
    lines.extend(
        f"        ({_vertex_id(i, j, 1)} {_vertex_id(i + 1, j, 1)} {_vertex_id(i + 1, j + 1, 1)} {_vertex_id(i, j + 1, 1)})"
        for i in range(len(X_NODES) - 1)
        for j in range(len(Y_NODES) - 1)
    )
    lines.extend(["    ); }", ");", "", "mergePatchPairs", "(", ");", ""])
    return "\n".join(lines)


def _control_dict(end_time_s: float, delta_t_s: float) -> str:
    write_interval = min(0.01 if end_time_s < 0.05 else 0.025, end_time_s)
    patch_fluxes = "\n".join(
        f"""    liquidFlux_{patch}
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name {patch};
        operation sum;
        fields (alphaPhi_);
        writeFields false;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}"""
        for patch in (
            "gasInlet",
            "downstreamOutlet",
            "bottomOutlet",
            "spanwiseMinus",
            "spanwisePlus",
        )
    )
    return (
        _foam_header("controlDict")
        + f"""
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
writeInterval {write_interval:.12g};
purgeWrite 0;
writeFormat ascii;
writePrecision 12;
writeCompression off;
timeFormat general;
timePrecision 8;
runTimeModifiable false;
functions
{{
    waterInventory
    {{
        type volFieldValue;
        libs (fieldFunctionObjects);
        fields (alpha.water);
        operation volIntegrate;
        writeFields false;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}
{patch_fluxes}
}}
"""
    )


def _pilot_fv_solution(source_text: str) -> str:
    """Add v2512 pressure-correction solvers missing from the static source copy."""
    marker = "solvers\n{"
    if marker not in source_text:
        raise ValueError("source fvSolution has no top-level solvers dictionary")
    entries = (
        "solvers\n{\n"
        "    pcorr { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0; }\n"
        "    pcorrFinal { $pcorr; relTol 0; }\n"
    )
    return source_text.replace(marker, entries, 1)


def _decompose_dict(cpus: int) -> str:
    if cpus not in MPI_DECOMPOSITIONS:
        raise ValueError(f"unsupported MPI rank count {cpus}; choose {tuple(MPI_DECOMPOSITIONS)}")
    nx, ny, nz = MPI_DECOMPOSITIONS[cpus]
    return (
        _foam_header("decomposeParDict")
        + f"""
numberOfSubdomains {cpus};
method hierarchical;
hierarchicalCoeffs
{{
    n ({nx} {ny} {nz});
    delta 0.001;
    order xyz;
}}
distributed no;
roots ();
"""
    )


def _mesh_spec() -> dict[str, Any]:
    profile = LAYOUT_PROFILES[ACTIVE_LAYOUT_PROFILE]
    x_min, x_max = profile["target_x"]
    y_min, y_max = profile["target_y"]
    target_x = [
        (x1 - x0) / X_COUNTS[index]
        for index, (x0, x1) in enumerate(zip(X_NODES, X_NODES[1:]))
        if x1 > x_min and x0 < x_max
    ]
    target_y = [
        (y1 - y0) / Y_COUNTS[index]
        for index, (y0, y1) in enumerate(zip(Y_NODES, Y_NODES[1:]))
        if y1 > y_min and y0 < y_max
    ]
    spacings = {
        "target_x_m": target_x,
        "target_y_m": target_y,
        "z_at_roof_m": [2.0 * _half_span(y_max) / Z_CELLS],
        "z_at_target_y_min_m": [2.0 * _half_span(y_min) / Z_CELLS],
        "z_at_bottom_m": [2.0 * BOTTOM_HALF_SPAN_M / Z_CELLS],
    }
    target = [*target_x, *target_y, *spacings["z_at_roof_m"], *spacings["z_at_target_y_min_m"]]
    return {
        "profile": ACTIVE_LAYOUT_PROFILE,
        "profile_description": profile["description"],
        "structured_hex_cells": sum(X_COUNTS) * sum(Y_COUNTS) * Z_CELLS,
        "cell_counts_by_piecewise_band": {"x": list(X_COUNTS), "y": list(Y_COUNTS), "z": Z_CELLS},
        "x_nodes_m": list(X_NODES),
        "y_nodes_m": list(Y_NODES),
        "target_region": f"{x_min:g}<=x<={x_max:g} m and {y_min:g}<=y<={y_max:g} m; all local span",
        "directional_spacings_m": spacings,
        "max_spacing_in_target_m": max(target),
        "z_half_span_taper_m": {"at_roof": TOP_HALF_SPAN_M, "at_bottom": BOTTOM_HALF_SPAN_M},
        "roof": "flat no-slip at y=0, authorized first-pilot simplification",
        "mesh_difference": "structured hex, nonuniform outer bands, no prism layers; not the paper polyhedral/prism mesh",
    }


def _source_hashes() -> dict[str, str]:
    paths = [SOURCE_RECORD, SOURCE_PDF, SOURCE_EXTRACTION]
    return {str(path.relative_to(ROOT)): _sha256(path) for path in paths if path.is_file()}


def _git_state() -> dict[str, Any]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "status_porcelain_at_prepare": status.stdout.splitlines() if status.returncode == 0 else [],
    }


def _prepare(
    run_id: str,
    cpus: int,
    memory_gib: int,
    end_time_s: float,
    delta_t_s: float,
    *,
    mesh_profile: str = "starter_70mm_corridor",
    continuation_from: str | None = None,
    reuse_mesh_from: str | None = None,
) -> Path:
    _activate_layout(mesh_profile)
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SOURCE_CASE, run_dir / "case")
    (run_dir / "source-snapshot").mkdir()
    for source in (SOURCE_RECORD, SOURCE_PDF, SOURCE_EXTRACTION):
        if source.is_file():
            target = run_dir / "source-snapshot" / source.name
            target.write_bytes(source.read_bytes())
    continuation_record: dict[str, Any] | None = None
    if continuation_from:
        parent_run = RUNS_ROOT / continuation_from
        guard_path = parent_run / "advance-guard.json"
        assessment_path = parent_run / "advance-assessment.json"
        if not guard_path.is_file() or not assessment_path.is_file():
            raise PilotError("continuation requires the prior run's guard and completed assessment")
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        if not assessment.get("eligible_for_0p4s_followon"):
            raise PilotError(
                "predeclared continuation guard did not pass; refusing follow-on launch"
            )
        continuation_record = {
            "from_run_id": continuation_from,
            "advance_guard_sha256": _sha256(guard_path),
            "advance_assessment_sha256": _sha256(assessment_path),
            "guard": json.loads(guard_path.read_text(encoding="utf-8")),
            "assessment": assessment,
            "mesh_adjustment_reason": "extend the <=70mm resolved corridor to x=6.5m and y=-6m to keep expected breakup from coinciding with the previous grid transition",
        }
        (run_dir / "source-snapshot" / guard_path.name).write_bytes(guard_path.read_bytes())
        (run_dir / "source-snapshot" / assessment_path.name).write_bytes(
            assessment_path.read_bytes()
        )
    case = run_dir / "case"
    (case / "system/blockMeshDict").write_text(_block_mesh_dict(), encoding="utf-8")
    (case / "system/controlDict").write_text(_control_dict(end_time_s, delta_t_s), encoding="utf-8")
    (case / "system/decomposeParDict").write_text(_decompose_dict(cpus), encoding="utf-8")
    fv_solution = case / "system/fvSolution"
    fv_solution.write_text(
        _pilot_fv_solution(fv_solution.read_text(encoding="utf-8")), encoding="utf-8"
    )
    mesh_reuse: dict[str, Any] | None = None
    if reuse_mesh_from:
        reference_dir = RUNS_ROOT / reuse_mesh_from
        reference_manifest = json.loads(
            (reference_dir / "manifest.json").read_text(encoding="utf-8")
        )
        reference_mesh = reference_dir / "case/constant/polyMesh"
        if reference_manifest.get("mesh", {}).get("profile") != mesh_profile:
            raise PilotError("reused mesh profile differs from requested mesh profile")
        if not reference_manifest.get("mesh_result", {}).get("mesh_ok_marker"):
            raise PilotError("reused mesh source has no passing checkMesh result")
        if (
            int(reference_manifest["mesh_result"].get("cell_count_from_checkMesh", -1))
            != _mesh_spec()["structured_hex_cells"]
        ):
            raise PilotError("reused mesh source cell count differs from requested mesh")
        if not reference_mesh.is_dir():
            raise PilotError(f"reusable polyMesh is missing: {reference_mesh}")
        copied_mesh = case / "constant/polyMesh"
        if copied_mesh.exists():
            shutil.rmtree(copied_mesh)
        shutil.copytree(reference_mesh, copied_mesh)
        mesh_hashes = {
            path.relative_to(copied_mesh).as_posix(): _sha256(path)
            for path in sorted(copied_mesh.rglob("*"))
            if path.is_file()
        }
        reference_hashes = {
            path.relative_to(reference_mesh).as_posix(): _sha256(path)
            for path in sorted(reference_mesh.rglob("*"))
            if path.is_file()
        }
        if mesh_hashes != reference_hashes:
            raise PilotError("copied native polyMesh hashes differ from immutable source mesh")
        mesh_reuse = {
            "source_run_id": reuse_mesh_from,
            "source_mesh_relative_path": f"results/runs/{reuse_mesh_from}/case/constant/polyMesh",
            "source_checkMesh_passed": True,
            "source_cell_count": int(
                reference_manifest["mesh_result"]["cell_count_from_checkMesh"]
            ),
            "source_measured_nozzle_area_m2": reference_manifest["mesh_result"][
                "actual_nozzle_area_m2"
            ],
            "native_polyMesh_file_sha256": mesh_hashes,
            "hash_identical_after_copy": True,
        }
    run_case_hashes = {
        path.relative_to(case).as_posix(): _sha256(path)
        for path in sorted(case.rglob("*"))
        if path.is_file()
    }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "prepared",
        "created_utc": _utc_now(),
        "experiment": "Exploratory Rouaix et al. (2023) Table 3 Case 4/Mesh 4 precursor",
        "continuation": continuation_record,
        "paper_conditions": {
            "source_location": "Rouaix et al. (2023), Table 3 PDF p.5/article p.4; Mesh 4 §3.3/Fig.4d PDF p.8/article p.7",
            "nozzle_diameter_m": DIAMETER_M,
            "nozzle_velocity_m_s": WATER_SPEED_M_S,
            "air_velocity_m_s": AIR_SPEED_M_S,
            "water_density_kg_m3": RHO_WATER_KG_M3,
            "liquid_turbulence_intensity": 0.01,
            "turbulence_model": "realizableKE",
            "surface_tension_n_m": 0.072,
            "nominal_mesh_size_m": 0.070,
            "nominal_ideal_nozzle_area_m2": math.pi * RADIUS_M**2,
            "derived_ideal_volume_flow_m3_s": math.pi * RADIUS_M**2 * WATER_SPEED_M_S,
            "derived_ideal_water_mass_flow_kg_s": math.pi
            * RADIUS_M**2
            * WATER_SPEED_M_S
            * RHO_WATER_KG_M3,
        },
        "assumptions_and_differences": [
            "Flat no-slip roof, accepted for this pilot based on paper's unreported preliminary comparison; curved roof is not represented.",
            "Structured hexahedral mesh with piecewise refinement, no prism layers; not the paper's polyhedral mesh.",
            "Full 20m streamwise footprint and 10m height; local span tapers from 7m to 16m over y, corresponding to about 24.2 degrees rather than source's rounded 25 degrees.",
            "Nozzle cells are selected by the inherited cylinderToFace rule; actual patch area and resulting flow are measured after mesh creation. Inlet speed is not rescaled.",
            f"Physical horizon {end_time_s:g} s; exploratory runtime pilot, far shorter than the paper's approximately 5 s stabilized calculation.",
            "Native phase-volume and open-boundary alphaPhi diagnostics are function-object outputs and do not change solver physics.",
            "Air turbulence intensity is provisionally set to 1%; the paper reports liquid intensity 1% but does not report air intensity or turbulence length scale.",
            "No prism layers; wall treatment on the local structured grid is not a wall-resolved reproduction.",
            "The run-owned fvSolution adds PCG/DIC pcorr and pcorrFinal entries required by pinned v2512 interIsoFoam; material model, schemes, and source BCs are inherited.",
        ],
        "mesh": _mesh_spec(),
        "allocation": {
            "cpus": cpus,
            "memory_gib": memory_gib,
            "mpi_ranks": cpus,
            "timeout_s": 10800 if end_time_s >= 0.4 else 7200,
        },
        "solver": {
            "image": IMAGE,
            "expected_image_id": PINNED_IMAGE_ID,
            "resolved_image_id": None,
            "application": "interIsoFoam",
            "end_time_s": end_time_s,
            "delta_t_s": delta_t_s,
            "adjust_time_step": False,
            "max_co": 5.0,
            "max_alpha_co": 5.0,
            "max_delta_t_s": delta_t_s,
        },
        "source_hashes": _source_hashes(),
        "source_case_file_hashes": {
            p.relative_to(SOURCE_CASE).as_posix(): _sha256(p)
            for p in sorted(SOURCE_CASE.rglob("*"))
            if p.is_file()
        },
        "run_case_input_sha256": run_case_hashes,
        "runner_sha256": _sha256(Path(__file__).resolve()),
        "write_interval_s": min(0.01 if end_time_s < 0.05 else 0.025, end_time_s),
        "mesh_reuse": mesh_reuse,
        "modified_inputs": [
            "case/system/blockMeshDict",
            "case/system/controlDict",
            "case/system/decomposeParDict",
            "case/system/fvSolution",
        ],
        "git": _git_state(),
        "stages": {},
        "nozzle_patch": {
            "measured_area_m2": None,
            "measured_volume_flow_m3_s": None,
            "measured_mass_flow_kg_s": None,
        },
        "solver_performance": {
            "wall_s": None,
            "execution_time_s": None,
            "clock_time_s": None,
            "linear_wall_estimate_0p4s_s": None,
            "linear_wall_estimate_5s_s": None,
        },
        "failure_or_stop_reason": None,
    }
    if mesh_reuse is not None:
        throughput_comparison = {
            "declared_utc": _utc_now(),
            "purpose": "Bounded MPI startup and same-mesh throughput comparison while the four-rank 0.4 s case completes.",
            "reference_run_id": reuse_mesh_from,
            "reference_ranks": int(
                json.loads(
                    (RUNS_ROOT / reuse_mesh_from / "manifest.json").read_text(encoding="utf-8")
                )["allocation"]["mpi_ranks"]
            ),
            "candidate_ranks": cpus,
            "candidate_horizon_s": end_time_s,
            "comparison_window_s": [0.025, min(0.05, end_time_s)],
            "mesh_reused_by_sha256": mesh_reuse["hash_identical_after_copy"],
            "same_mesh_profile_and_cell_count": True,
            "same_physics_inputs": True,
            "declared_configuration_differences": [
                "MPI rank count/decomposition changes from4 to16.",
                "The candidate ends at0.05 s and uses the same0.025 s snapshot interval as the reference case.",
            ],
            "measurement": "Compare cumulative ClockTime at the common0.025 and0.05 s writes; exclude mesh creation because the candidate reuses the byte-identical checked polyMesh.",
        }
        manifest["throughput_comparison"] = throughput_comparison
        _write_json(run_dir / "throughput-comparison.json", throughput_comparison)
    if continuation_record is not None:
        parent_manifest = json.loads(
            (RUNS_ROOT / continuation_from / "manifest.json").read_text(encoding="utf-8")
        )
        selected_mesh = _mesh_spec()
        followon_declaration = {
            "schema_version": 1,
            "declared_utc": _utc_now(),
            "status": "declared_before_detached_launch",
            "source_run_id": continuation_from,
            "advance_guard_sha256": continuation_record["advance_guard_sha256"],
            "advance_assessment_sha256": continuation_record["advance_assessment_sha256"],
            "reason": "Move the coarse-grid transition beyond the paper's approximate x=3.5 m/y=-4 m breakup region while preserving source/top resolution and Case 4 physics.",
            "mesh": {
                "profile": mesh_profile,
                "cell_count": selected_mesh["structured_hex_cells"],
                "x_nodes_m": list(X_NODES),
                "x_counts": list(X_COUNTS),
                "y_nodes_m": list(Y_NODES),
                "y_counts": list(Y_COUNTS),
                "z_cells": Z_CELLS,
                "max_x_spacing_in_corridor_m": max(
                    selected_mesh["directional_spacings_m"]["target_x_m"]
                ),
                "max_y_spacing_in_corridor_m": max(
                    selected_mesh["directional_spacings_m"]["target_y_m"]
                ),
                "spanwise_spacing_at_y_minus6_m": selected_mesh["directional_spacings_m"][
                    "z_at_target_y_min_m"
                ][0],
                "source_x_band_cells_for_minus0p5_to0p5_m": X_COUNTS[1],
                "source_top_y_band_cells_for_minus1_to0_m": Y_COUNTS[-1],
                "source_spanwise_cells": Z_CELLS,
                "parent_measured_nozzle_area_m2": parent_manifest.get("nozzle_patch", {}).get(
                    "measured_area_m2"
                ),
                "domain_and_flat_roof_unchanged": True,
            },
            "physics_changes": [],
            "mesh_changes": [
                "Extend the 68.97 mm streamwise band from x=4.5 m to x=6.5 m.",
                "Move the outer-to-refined vertical transition from y=-4 m to y=-6 m; use 69.44 mm vertical spacing from y=-6 to -1 m.",
                "Preserve nozzle x-band count29, upper y-band count29, and z count160 from the 0.03 s pilot; resulting spanwise spacing at y=-6 m is77.5 mm.",
            ],
            "additional_diagnostics": [
                "Integrate alpha.water with volFieldValue at each solver step.",
                "Record alphaPhi_ sums on each external patch at each solver step.",
            ],
            "followon_wall_budget_s": 10800,
            "stage_timeout_s": manifest["allocation"]["timeout_s"],
        }
        _write_json(run_dir / "follow-on-refinement.json", followon_declaration)
    _write_json(run_dir / "manifest.json", manifest)
    return run_dir


def _resolve_image(run_dir: Path) -> str:
    command = ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
    (run_dir / "image-inspect.log").write_text(
        f"$ {' '.join(command)}\nexit={result.returncode}\n{result.stdout}{result.stderr}",
        encoding="utf-8",
    )
    if result.returncode:
        raise PilotError(f"Docker image inspect failed: {result.stderr.strip()}")
    resolved = result.stdout.strip()
    if resolved != PINNED_IMAGE_ID:
        raise PilotError(
            f"pinned OpenFOAM image mismatch: expected {PINNED_IMAGE_ID}, got {resolved}"
        )
    return resolved


def _foam_setup() -> str:
    qbash = shlex.quote(OPENFOAM_BASHRC)
    return (
        "set +e +u; source_status=0; source " + qbash + " || source_status=$?; set +e +u; "
        "printf 'PILOT_SETUP_EXIT code=%s\\n' \"$source_status\"; "
        'if [ "$source_status" -ne 0 ]; then exit "$source_status"; fi; set -euo pipefail; '
        'run_stage() { local stage="$1"; shift; local code=0; "$@" || code=$?; '
        'printf \'PILOT_STAGE_EXIT stage=%s code=%s\\n\' "$stage" "$code"; return "$code"; }'
    )


def _mesh_shell() -> str:
    commands = [
        ("blockMesh", "blockMesh"),
        ("topoSet", "topoSet"),
        ("createPatch", "createPatch -overwrite"),
        ("checkMesh", "checkMesh -allTopology -allGeometry"),
        ("setExprFields", "setExprFields"),
    ]
    return (
        _foam_setup()
        + "; "
        + "; ".join(f"run_stage {name} {command}" for name, command in commands)
    )


def _flow_shell(cpus: int) -> str:
    return (
        _foam_setup()
        + "; run_stage decomposePar decomposePar -force; run_stage interIsoFoam mpirun --bind-to none -np "
        + str(cpus)
        + " interIsoFoam -parallel; run_stage reconstructPar reconstructPar -fields '(alpha.water U p_rgh k epsilon nut)'"
    )


def _container_command(
    run_dir: Path, stage: str, shell: str, cpus: int, memory_gib: int
) -> tuple[list[str], Path]:
    name = f"rouaix-c4-{run_dir.name}-{stage}"
    cidfile = run_dir / f"{stage}.cid"
    if cidfile.exists():
        raise FileExistsError(f"refusing to reuse existing cidfile {cidfile}")
    command = [
        "docker",
        "run",
        "--rm",
        f"--name={name}",
        f"--cidfile={cidfile}",
        f"--cpus={cpus}",
        f"--memory={memory_gib}g",
        "--memory-swap",
        f"{memory_gib}g",
        "--env",
        "OMP_NUM_THREADS=1",
        "--env",
        "OMP_THREAD_LIMIT=1",
        "--env",
        "OPENBLAS_NUM_THREADS=1",
        "--env",
        "MKL_NUM_THREADS=1",
        "--env",
        "NUMEXPR_NUM_THREADS=1",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={run_dir / 'case'},dst=/case",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        IMAGE,
        "-c",
        shell,
    ]
    return command, cidfile


def _container_id(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    return value if CONTAINER_ID_RE.fullmatch(value) else None


def _run_container(
    run_dir: Path, stage: str, shell: str, manifest: dict[str, Any]
) -> tuple[int, float, str]:
    cpus = int(manifest["allocation"]["cpus"])
    memory_gib = int(manifest["allocation"]["memory_gib"])
    command, cidfile = _container_command(run_dir, stage, shell, cpus, memory_gib)
    (run_dir / f"{stage}-command.json").write_text(
        json.dumps(command, indent=2) + "\n", encoding="utf-8"
    )
    start = time.monotonic()
    log = run_dir / f"{stage}.log"
    try:
        with log.open("wb") as stream:
            proc = subprocess.Popen(
                command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
            )
            try:
                timeout_s = float(manifest["allocation"].get("timeout_s", 7200))
                code = proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                name = command[3].split("=", 1)[1]
                subprocess.run(
                    ["docker", "stop", "--time", "10", name], capture_output=True, timeout=30
                )
                subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=30)
                code = 124
    except OSError as error:
        log.write_text(f"container launch failed: {error}\n", encoding="utf-8")
        code = 127
    wall = time.monotonic() - start
    cid = _container_id(cidfile)
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    manifest["stages"][stage] = {
        "exit_code": code,
        "wall_time_s": round(wall, 3),
        "container_id": cid,
        "log": log.name,
        "command": command,
    }
    _write_json(run_dir / "manifest.json", manifest)
    return code, wall, text


def _stage_codes(text: str) -> dict[str, int]:
    return {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"(?m)^PILOT_STAGE_EXIT stage=(\w+) code=(-?\d+)\s*$", text)
    }


def _parse_poly_mesh(
    path: Path,
) -> tuple[dict[int, tuple[float, float, float]], list[list[int]], dict[str, dict[str, int]]]:
    boundary_file = path / "boundary"
    boundary_text = boundary_file.read_text(encoding="utf-8", errors="replace")
    boundary_text = re.sub(r"/\*.*?\*/", "", boundary_text, flags=re.S)
    boundary_text = re.sub(r"//[^\n]*", "", boundary_text)
    patches: dict[str, dict[str, int]] = {}
    for match in re.finditer(r"(?m)^\s*([A-Za-z_]\w*)\s*\{", boundary_text):
        name = match.group(1)
        opening = boundary_text.find("{", match.start())
        depth = 0
        close = None
        for index in range(opening, len(boundary_text)):
            if boundary_text[index] == "{":
                depth += 1
            elif boundary_text[index] == "}":
                depth -= 1
                if depth == 0:
                    close = index
                    break
        if close is None:
            continue
        body = boundary_text[opening + 1 : close]
        start = re.search(r"\bstartFace\s+(\d+)\s*;", body)
        count = re.search(r"\bnFaces\s+(\d+)\s*;", body)
        if start and count:
            patches[name] = {"startFace": int(start.group(1)), "nFaces": int(count.group(1))}
    if "nozzle" not in patches:
        return {}, [], patches
    first = patches["nozzle"]["startFace"]
    stop = first + patches["nozzle"]["nFaces"]
    faces: list[list[int]] = []
    in_list = False
    with (path / "faces").open(encoding="utf-8", errors="replace") as stream:
        face_index = 0
        for line in stream:
            stripped = line.strip()
            if stripped == "(":
                in_list = True
                continue
            if in_list and stripped == ")":
                break
            if not in_list or face_index >= stop:
                continue
            if face_index >= first:
                match = re.match(r"\d+\s*\(([^()]*)\)", stripped)
                if match:
                    faces.append([int(value) for value in match.group(1).split()])
            face_index += 1
    needed = {point for face in faces for point in face}
    points: dict[int, tuple[float, float, float]] = {}
    coordinate_pattern = re.compile(r"\(\s*(%s)\s+(%s)\s+(%s)\s*\)" % (FLOAT, FLOAT, FLOAT))
    with (path / "points").open(encoding="utf-8", errors="replace") as stream:
        in_list = False
        point_index = 0
        for line in stream:
            stripped = line.strip()
            if stripped == "(":
                in_list = True
                continue
            if in_list and stripped == ")":
                break
            if not in_list:
                continue
            if point_index in needed:
                match = coordinate_pattern.search(stripped)
                if match:
                    points[point_index] = tuple(map(float, match.groups()))
            point_index += 1
            if len(points) == len(needed):
                break
    return points, faces, patches


def _area_of_face(face: list[int], points: dict[int, tuple[float, float, float]]) -> float:
    area_vec = np.zeros(3)
    xyz = [np.asarray(points[index], dtype=float) for index in face]
    for first, second in zip(xyz, xyz[1:] + xyz[:1], strict=True):
        area_vec += np.cross(first, second)
    return float(np.linalg.norm(area_vec) / 2.0)


def _actual_nozzle_area(case: Path) -> float:
    points, faces, patches = _parse_poly_mesh(case / "constant/polyMesh")
    if "nozzle" not in patches:
        raise PilotError("createPatch did not produce a nozzle boundary patch")
    selected = faces
    if not selected:
        raise PilotError("nozzle patch contains no faces")
    return sum(_area_of_face(face, points) for face in selected)


FLOAT = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def _mesh_summary(text: str, case: Path) -> dict[str, Any]:
    count = re.findall(r"(?mi)^\s*cells\s*:\s*(\d+)\b", text)
    mesh_ok = bool(re.search(r"(?mi)^\s*Mesh OK\.\s*$", text))
    failed = re.findall(r"(?mi)^\s*Failed\s+(\d+)\s+mesh checks?\s*\.", text)
    area = _actual_nozzle_area(case) if (case / "constant/polyMesh/boundary").exists() else None
    return {
        "cell_count_from_checkMesh": int(count[-1]) if count else None,
        "mesh_ok_marker": mesh_ok,
        "failed_mesh_checks": [int(x) for x in failed],
        "actual_nozzle_area_m2": area,
        "ideal_nozzle_area_m2": math.pi * RADIUS_M**2,
        "relative_nozzle_area_error": (area / (math.pi * RADIUS_M**2) - 1)
        if area is not None
        else None,
    }


def _execution_times(text: str) -> tuple[float | None, float | None]:
    matches = re.findall(
        r"ExecutionTime\s*=\s*(%s)\s*s\s+ClockTime\s*=\s*(%s)\s*s" % (FLOAT, FLOAT), text
    )
    return tuple(map(float, matches[-1])) if matches else (None, None)


def _numeric_time_directories(case: Path) -> list[tuple[float, Path]]:
    times = []
    for path in case.iterdir():
        if not path.is_dir():
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        if (path / "alpha.water").is_file():
            times.append((value, path))
    return sorted(times)


def _surface_flux_history(case: Path) -> tuple[np.ndarray, np.ndarray] | None:
    summed: dict[float, float] = {}
    objects_found = set()
    for data_path in case.glob("postProcessing/liquidFlux_*/**/*.dat"):
        object_name = data_path.parent.parent.name
        objects_found.add(object_name.removeprefix("liquidFlux_"))
        for line in data_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            values = np.fromstring(stripped, sep=" ", dtype=np.float64)
            if values.size >= 2 and np.isfinite(values[:2]).all():
                time_s, flux_m3_s = map(float, values[:2])
                summed[time_s] = summed.get(time_s, 0.0) + flux_m3_s
    required = {"gasInlet", "downstreamOutlet", "bottomOutlet", "spanwiseMinus", "spanwisePlus"}
    if not required.issubset(objects_found) or not summed:
        return None
    ordered = sorted(summed.items())
    times = np.asarray([row[0] for row in ordered], dtype=np.float64)
    fluxes = np.asarray([row[1] for row in ordered], dtype=np.float64)
    return times, fluxes


def _native_cell_volume_field(
    run_dir: Path, manifest: dict[str, Any], time_dir: Path
) -> np.ndarray:
    """Read OpenFOAM's own V field, generating it offline when absent."""
    volume_path = time_dir / "V"
    if not volume_path.is_file():
        # writeCellVolumes uses the mesh's native cell ordering. The previous
        # structured-block reconstruction assumed a block concatenation order
        # that OpenFOAM does not promise, so it cannot be paired safely with a
        # field's internalField array.
        time_value = float(time_dir.name)
        shell = (
            _foam_setup()
            + f"; run_stage writeCellVolumes postProcess -func writeCellVolumes -time {time_value:.12g}"
        )
        code, _, output = _run_container(run_dir, "native-volume-audit", shell, manifest)
        stage_codes = _stage_codes(output)
        if code != 0 or stage_codes.get("writeCellVolumes") != 0 or not volume_path.is_file():
            raise PilotError(
                "OpenFOAM native cell-volume postProcess failed: "
                f"container exit={code}; stages={stage_codes}"
            )
    volumes = read_volume_scalar_field(
        volume_path,
        int(manifest["mesh"]["structured_hex_cells"]),
        (0, 3, 0, 0, 0, 0, 0),
    ).internal
    if not np.isfinite(volumes).all() or np.any(volumes <= 0):
        raise PilotError("native V field contains non-finite or non-positive cell volumes")
    domain_volume = float(volumes.sum())
    if not math.isclose(domain_volume, 2300.0, rel_tol=0, abs_tol=1e-7):
        raise PilotError(f"native V field sums to {domain_volume} m^3, expected 2300 m^3")
    manifest["native_volume_audit"] = {
        "method": "OpenFOAM v2512 postProcess -func writeCellVolumes; native cell ordering",
        "field_path": str(volume_path.relative_to(run_dir)),
        "cell_count": int(volumes.size),
        "sum_cell_volumes_m3": domain_volume,
        "minimum_cell_volume_m3": float(np.min(volumes)),
        "maximum_cell_volume_m3": float(np.max(volumes)),
    }
    command_record = run_dir / "native-volume-audit/command.json"
    if command_record.is_file():
        manifest["native_volume_audit"]["command_record"] = str(command_record.relative_to(run_dir))
    _write_json(run_dir / "manifest.json", manifest)
    return volumes


def _run_diagnostics(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    _activate_layout(manifest.get("mesh", {}).get("profile", "starter_70mm_corridor"))
    case = run_dir / "case"
    mesh = _mesh_spec()
    time_dirs = _numeric_time_directories(case)
    if not time_dirs:
        raise PilotError("no reconstructed alpha.water snapshots were found")
    cell_volumes = _native_cell_volume_field(run_dir, manifest, time_dirs[-1][1])
    if cell_volumes.size != mesh["structured_hex_cells"]:
        raise PilotError("cell-volume count differs from declared structured mesh")
    mass_flow = float(manifest["nozzle_patch"]["measured_mass_flow_kg_s"])
    external_patches = (
        "gasInlet",
        "downstreamOutlet",
        "bottomOutlet",
        "spanwiseMinus",
        "spanwisePlus",
    )
    scalar_dimensions = {
        "k": (0, 2, -2, 0, 0, 0, 0),
        "epsilon": (0, 2, -3, 0, 0, 0, 0),
        "nut": (0, 2, -1, 0, 0, 0, 0),
    }
    time_rows: list[dict[str, Any]] = []
    global_alpha_min = math.inf
    global_alpha_max = -math.inf
    alpha_outside = 0
    external_boundary_max = 0.0
    all_required_fields_finite = True
    missing_required_fields: list[str] = []
    for time_s, time_dir in time_dirs:
        alpha_field = read_volume_scalar_field(
            time_dir / "alpha.water", cell_volumes.size, EXPECTED_ALPHA_DIMENSIONS
        )
        alpha = alpha_field.internal
        if not np.isfinite(alpha).all():
            all_required_fields_finite = False
        global_alpha_min = min(global_alpha_min, float(np.nanmin(alpha)))
        global_alpha_max = max(global_alpha_max, float(np.nanmax(alpha)))
        alpha_outside += int(np.count_nonzero((alpha < -1e-8) | (alpha > 1 + 1e-8)))
        for patch in external_patches:
            values = alpha_field.boundary.get(patch, np.array([], dtype=np.float64))
            if values.size:
                if not np.isfinite(values).all():
                    all_required_fields_finite = False
                external_boundary_max = max(external_boundary_max, float(np.max(np.abs(values))))
            else:
                missing_required_fields.append(f"{time_dir.name}/alpha.water:{patch}")
        water_volume = float(np.dot(alpha, cell_volumes))
        row: dict[str, Any] = {
            "time_s": time_s,
            "water_volume_m3_native_cell_volumes": water_volume,
            "water_mass_kg": water_volume * RHO_WATER_KG_M3,
            "released_mass_kg_from_measured_patch": mass_flow * time_s,
            "alpha_min": float(np.nanmin(alpha)),
            "alpha_max": float(np.nanmax(alpha)),
            "external_boundary_max_abs_alpha": max(
                (
                    float(np.max(np.abs(alpha_field.boundary[p])))
                    for p in external_patches
                    if alpha_field.boundary.get(p, np.array([], dtype=np.float64)).size
                ),
                default=0.0,
            ),
        }
        for field_name, dimensions in scalar_dimensions.items():
            field_path = time_dir / field_name
            if not field_path.is_file():
                all_required_fields_finite = False
                missing_required_fields.append(f"{time_dir.name}/{field_name}")
                continue
            field_values = read_volume_scalar_field(
                field_path, cell_volumes.size, dimensions
            ).internal
            finite = bool(np.isfinite(field_values).all())
            all_required_fields_finite &= finite
            row[f"{field_name}_finite"] = finite
            row[f"{field_name}_min"] = float(np.nanmin(field_values))
            row[f"{field_name}_max"] = float(np.nanmax(field_values))
        vector_path = time_dir / "U"
        if not vector_path.is_file():
            all_required_fields_finite = False
            missing_required_fields.append(f"{time_dir.name}/U")
        else:
            velocity = read_volume_vector_internal(vector_path, cell_volumes.size)
            finite = bool(np.isfinite(velocity).all())
            all_required_fields_finite &= finite
            row["U_finite"] = finite
            row["U_max_magnitude_m_s"] = float(np.max(np.linalg.norm(velocity, axis=1)))
        time_rows.append(row)
    if not time_rows:
        raise PilotError("no reconstructed alpha.water snapshots were found")
    flux_history = _surface_flux_history(case)
    has_flux = flux_history is not None
    escaped_volume_m3: float | None = None
    escape_method: str
    if flux_history is not None:
        flux_times, flux_values = flux_history
        if flux_times[0] > 0:
            flux_times = np.insert(flux_times, 0, 0.0)
            flux_values = np.insert(flux_values, 0, 0.0)
        escaped_volume_m3 = float(np.trapezoid(flux_values, flux_times))
        escape_method = "time-integrated net alphaPhi_ sum over all five open patches"
    elif (
        float(manifest.get("solver", {}).get("end_time_s", 0.0)) <= 0.05
        and external_boundary_max <= 1e-8
        and not missing_required_fields
    ):
        escaped_volume_m3 = 0.0
        escape_method = "external-patch alpha.water values were <=1e-8 at every saved time; no flux writer in this short pilot"
    else:
        escape_method = (
            "not measured; open-boundary liquid or missing patch data prevents assuming zero escape"
        )
    final = time_rows[-1]
    expected_mass = float(final["released_mass_kg_from_measured_patch"])
    accounted_mass = float(final["water_mass_kg"]) + (
        escaped_volume_m3 * RHO_WATER_KG_M3 if escaped_volume_m3 is not None else 0.0
    )
    ledger_residual = (
        (expected_mass - accounted_mass) / expected_mass
        if expected_mass > 0 and escaped_volume_m3 is not None
        else None
    )
    return {
        "analysis_method": "sum(alpha.water * OpenFOAM-native V field in field cell order), generated by v2512 postProcess writeCellVolumes; sum(V) cross-check 2300 m^3",
        "cell_count": int(cell_volumes.size),
        "domain_volume_m3": float(cell_volumes.sum()),
        "snapshot_count": len(time_rows),
        "snapshots": time_rows,
        "alpha_internal_global_min": global_alpha_min,
        "alpha_internal_global_max": global_alpha_max,
        "alpha_internal_out_of_declared_tolerance_count": alpha_outside,
        "required_U_k_epsilon_nut_all_finite": bool(all_required_fields_finite),
        "missing_required_fields_or_boundary_values": missing_required_fields,
        "max_abs_open_boundary_alpha": external_boundary_max,
        "open_boundary_liquid_flux_history_available": has_flux,
        "open_boundary_net_escaped_water_volume_m3": escaped_volume_m3,
        "open_boundary_escape_accounting_method": escape_method,
        "final_expected_released_water_mass_kg": expected_mass,
        "final_accounted_water_mass_kg": accounted_mass if escaped_volume_m3 is not None else None,
        "final_phase_ledger_residual_fraction": ledger_residual,
        "final_phase_ledger_pass_le_0p1_percent": ledger_residual is not None
        and abs(ledger_residual) <= 0.001,
    }


def _worker(run_dir: Path) -> int:
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _activate_layout(manifest["mesh"]["profile"])
    manifest["status"] = "running_mesh"
    manifest["worker_started_utc"] = _utc_now()
    _write_json(manifest_path, manifest)
    started = time.monotonic()
    try:
        manifest["solver"]["resolved_image_id"] = _resolve_image(run_dir)
        _write_json(manifest_path, manifest)
        if manifest.get("mesh_reuse"):
            mesh_shell = (
                _foam_setup()
                + "; run_stage checkMesh checkMesh -allTopology -allGeometry; run_stage setExprFields setExprFields"
            )
        else:
            mesh_shell = _mesh_shell()
        mesh_code, mesh_wall, mesh_text = _run_container(run_dir, "mesh", mesh_shell, manifest)
        mesh_summary = _mesh_summary(mesh_text, run_dir / "case")
        manifest["mesh_result"] = mesh_summary
        stage_codes = _stage_codes(mesh_text)
        manifest["mesh_stage_codes"] = stage_codes
        if (
            mesh_code != 0
            or not mesh_summary["mesh_ok_marker"]
            or any(code != 0 for code in stage_codes.values())
        ):
            raise PilotError(
                f"mesh stage failed or checkMesh did not pass: docker exit={mesh_code}; stages={stage_codes}; summary={mesh_summary}"
            )
        area = float(mesh_summary["actual_nozzle_area_m2"])
        flow = area * WATER_SPEED_M_S
        mass_flow = flow * RHO_WATER_KG_M3
        manifest["nozzle_patch"] = {
            "measured_area_m2": area,
            "measured_volume_flow_m3_s": flow,
            "measured_mass_flow_kg_s": mass_flow,
            "imposed_speed_m_s": WATER_SPEED_M_S,
            "relative_area_error_vs_ideal": mesh_summary["relative_nozzle_area_error"],
        }
        manifest["status"] = "running_short_flow"
        _write_json(manifest_path, manifest)
        flow_start = time.monotonic()
        ranks = int(manifest["allocation"]["mpi_ranks"])
        flow_code, flow_wall, flow_text = _run_container(
            run_dir, "flow", _flow_shell(ranks), manifest
        )
        execution, clock = _execution_times(flow_text)
        end_time = float(manifest["solver"]["end_time_s"])
        estimated_basis = clock if clock and clock > 0 else flow_wall
        manifest["solver_performance"] = {
            "wall_s": round(flow_wall, 3),
            "flow_stage_elapsed_s": round(time.monotonic() - flow_start, 3),
            "execution_time_s": execution,
            "clock_time_s": clock,
            "linear_wall_estimate_0p4s_s": round(estimated_basis * 0.4 / end_time, 1),
            "linear_wall_estimate_5s_s": round(estimated_basis * 5.0 / end_time, 1),
            "extrapolation_note": "rough linear scaling from this 0.03 s startup pilot; not a cost guarantee",
        }
        manifest["flow_stage_codes"] = _stage_codes(flow_text)
        if flow_code != 0 or any(code != 0 for code in manifest["flow_stage_codes"].values()):
            raise PilotError(
                f"flow stage failed: docker exit={flow_code}; stages={manifest['flow_stage_codes']}"
            )
        try:
            manifest["diagnostics"] = _run_diagnostics(run_dir)
        except (OSError, ValueError, KeyError, IndexError) as analysis_error:
            manifest["diagnostics_error"] = f"{type(analysis_error).__name__}: {analysis_error}"
        manifest["status"] = "completed_short_pilot"
        manifest["flow_final_time_s"] = end_time
        return_code = 0
    except (OSError, subprocess.SubprocessError, PilotError, ValueError, KeyError) as error:
        manifest["status"] = "failed"
        manifest["failure_or_stop_reason"] = f"{type(error).__name__}: {error}"
        return_code = 1
    finally:
        manifest["worker_wall_time_s"] = round(time.monotonic() - started, 3)
        manifest["completed_utc"] = _utc_now()
        _write_json(manifest_path, manifest)
        (run_dir / "worker.exit").write_text(f"{return_code}\n", encoding="ascii")
    return return_code


def _launch(run_dir: Path) -> dict[str, Any]:
    worker_command = [
        sys.executable,
        str(ROOT / "scripts/run_local.py"),
        "--threads",
        "1",
        "--",
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        str(run_dir),
    ]
    worker_log = run_dir / "pilot-worker.log"
    with worker_log.open("ab", buffering=0) as stream:
        process = subprocess.Popen(
            worker_command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    launch = {
        "started_utc": _utc_now(),
        "host_pid": process.pid,
        "process_group": process.pid,
        "command": worker_command,
        "detached_session": True,
        "stdin": "DEVNULL",
        "log": worker_log.name,
        "status": "launched",
    }
    _write_json(run_dir / "launch.json", launch)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "launched_detached"
    manifest["host_worker_pid"] = process.pid
    _write_json(manifest_path, manifest)
    return launch


def _analyze_existing(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    diagnostics = _run_diagnostics(run_dir)
    guard_path = run_dir / "advance-guard.json"
    guard = json.loads(guard_path.read_text(encoding="utf-8")) if guard_path.is_file() else {}
    worker_exit_path = run_dir / "worker.exit"
    worker_exit = (
        int(worker_exit_path.read_text(encoding="ascii").strip())
        if worker_exit_path.is_file()
        else None
    )
    stage_flow = manifest.get("stages", {}).get("flow", {})
    stage_mesh = manifest.get("stages", {}).get("mesh", {})
    horizon = float(manifest.get("solver", {}).get("end_time_s", 0.0))
    budget_s = float(
        guard.get("candidate_followon", {}).get("maximum_projected_wall_time_s", 10800)
    )
    allowance = 1.2
    mesh_wall = float(stage_mesh.get("wall_time_s") or 0.0)
    flow_wall = float(stage_flow.get("wall_time_s") or 0.0)
    source_cell_count = int(manifest["mesh"]["structured_hex_cells"])
    active_profile = ACTIVE_LAYOUT_PROFILE
    _activate_layout("breakup_70mm_corridor")
    followon_cell_count = int(_mesh_spec()["structured_hex_cells"])
    _activate_layout(active_profile)
    mesh_cell_scale = followon_cell_count / source_cell_count
    projection = (
        (mesh_wall + flow_wall * 0.4 / horizon) * mesh_cell_scale * allowance
        if horizon > 0
        else math.inf
    )
    checks = {
        "solver_exit_zero_at_declared_horizon": (
            manifest.get("status") == "completed_short_pilot"
            and worker_exit == 0
            and stage_flow.get("exit_code") == 0
            and float(manifest.get("flow_final_time_s", -1)) >= horizon - 1e-10
        ),
        "alpha_within_minus1e8_to_1plus1e8": diagnostics[
            "alpha_internal_out_of_declared_tolerance_count"
        ]
        == 0,
        "saved_U_k_epsilon_nut_finite": diagnostics["required_U_k_epsilon_nut_all_finite"],
        "phase_ledger_residual_le_0p1_percent": diagnostics[
            "final_phase_ledger_pass_le_0p1_percent"
        ],
        "measured_projected_0p4_wall_with_20percent_allowance_le_3h": projection <= budget_s,
    }
    assessment = {
        "schema_version": 1,
        "assessed_utc": _utc_now(),
        "scope": "Exploratory continuation guard only; not an E1 acceptance decision.",
        "predeclared_guard_sha256": _sha256(guard_path) if guard_path.is_file() else None,
        "checks": checks,
        "eligible_for_0p4s_followon": all(checks.values()),
        "observed": {
            "worker_exit_code": worker_exit,
            "flow_exit_code": stage_flow.get("exit_code"),
            "declared_horizon_s": horizon,
            "flow_final_time_s": manifest.get("flow_final_time_s"),
            "mesh_stage_wall_time_s": mesh_wall,
            "flow_stage_wall_time_s": flow_wall,
            "pilot_cell_count": source_cell_count,
            "followon_mesh_profile": "breakup_70mm_corridor",
            "followon_cell_count": followon_cell_count,
            "followon_to_pilot_cell_ratio": mesh_cell_scale,
            "projected_0p4_wall_time_with_20percent_allowance_s": projection,
            "projected_0p4_wall_time_h": projection / 3600.0,
            "budget_s": budget_s,
            "diagnostics": diagnostics,
        },
    }
    manifest["diagnostics"] = diagnostics
    manifest["continuation_assessment"] = assessment
    _write_json(run_dir / "diagnostics.json", diagnostics)
    _write_json(run_dir / "advance-assessment.json", assessment)
    _write_json(manifest_path, manifest)
    return assessment


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="unique run bundle ID; generated when omitted")
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--memory-gib", type=int, default=48)
    parser.add_argument("--end-time-s", type=float, default=DEFAULT_END_TIME_S)
    parser.add_argument("--delta-t-s", type=float, default=DEFAULT_DT_S)
    parser.add_argument(
        "--mesh-profile",
        choices=tuple(LAYOUT_PROFILES),
        default="starter_70mm_corridor",
        help="declared structured mesh layout",
    )
    parser.add_argument("--continuation-from", help="eligible prior pilot run ID")
    parser.add_argument(
        "--reuse-mesh-from", help="copy a hash-verified polyMesh from a passing run bundle"
    )
    parser.add_argument("--analyze-only", type=Path, help="audit an existing completed run bundle")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return args
    if args.cpus not in MPI_DECOMPOSITIONS:
        parser.error(f"--cpus must be one of {tuple(MPI_DECOMPOSITIONS)}")
    if args.memory_gib < 8 or not math.isfinite(args.end_time_s) or args.end_time_s <= 0:
        parser.error("memory must be >=8 GiB and end time must be positive")
    if not math.isfinite(args.delta_t_s) or args.delta_t_s <= 0 or args.delta_t_s > args.end_time_s:
        parser.error("delta-t must be positive and no longer than the pilot horizon")
    if not args.run_id:
        args.run_id = "rouaix-case4-pilot-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not RUN_ID_RE.fullmatch(args.run_id):
        parser.error("run ID may contain only letters, digits, dot, underscore and hyphen")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        return _worker(args.worker.resolve())
    if args.analyze_only:
        try:
            assessment = _analyze_existing(args.analyze_only.resolve())
        except (OSError, PilotError, ValueError, KeyError, IndexError) as error:
            print(
                f"pilot post-run analysis failed: {type(error).__name__}: {error}", file=sys.stderr
            )
            return 1
        print(json.dumps(assessment, indent=2, sort_keys=True))
        return 0
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        run_dir = _prepare(
            args.run_id,
            args.cpus,
            args.memory_gib,
            args.end_time_s,
            args.delta_t_s,
            mesh_profile=args.mesh_profile,
            continuation_from=args.continuation_from,
            reuse_mesh_from=args.reuse_mesh_from,
        )
    except (FileExistsError, OSError, ValueError) as error:
        print(f"pilot preparation failed: {error}", file=sys.stderr)
        return 2
    if args.prepare_only:
        print(run_dir)
        return 0
    try:
        launch = _launch(run_dir)
    except OSError as error:
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "launch_failed"
        manifest["failure_or_stop_reason"] = f"{type(error).__name__}: {error}"
        _write_json(manifest_path, manifest)
        print(f"could not detach pilot worker: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"run_dir": str(run_dir), **launch}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
