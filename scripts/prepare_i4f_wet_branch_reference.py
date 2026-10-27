#!/usr/bin/env python3
"""Prepare a bounded water-filled reference on one native I4F branch."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aerial_drop.i4f_native_face_reader import (
    _face_geometry,
    _parse_internal,
    _parse_patch_scalar_values,
    _read_global_boundary,
    _read_global_faces,
    _read_global_labels,
    _read_global_points,
)

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
SOURCE_CASE = RUNS / "i4f-cold-mesh-pair-20261027T050932Z/arms/baseline-1p0m-299214/case"
IMAGE = "opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319"
BRANCH_STL = "constant/triSurface/trainA_upperBranch.stl"
RHO = 998.2
MU = 0.001002
Q_TARGET = 0.599812435
P_AMBIENT = 100_000.0
GRAVITY = np.asarray([0.0, 0.0, -9.81])
XREF_XYZ = np.asarray([4.8, -0.55, 0.90])
X_INLET = 2.25
X_OUTLET = 4.8
OUTLET_FACE_CENTER_RANGE = (4.799, 4.807)
OUTSIDE_POINT = (6.20, -0.55, 0.90)
BRANCH_BOX = ((2.250001, -1.10, 0.30), (4.799999, 0.0, 1.35))
MAX_WALL_S = 1800
SAVE_WALL_S = 1500
OUTPUT_CAP = 400 * 1024 * 1024
K_INLET = 0.02
OMEGA_INLET = 10.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reduced_pressure(
    p_abs_pa: float | np.ndarray,
    p_ambient_pa: float,
    rho_kg_m3: float,
    gravity_xyz: np.ndarray | tuple[float, float, float],
    xyz_m: np.ndarray | tuple[float, float, float],
    xref_xyz_m: np.ndarray | tuple[float, float, float],
) -> float | np.ndarray:
    """pSolver=(pAbs-pAmbient)/rho - g dot (C-xref), in m2/s2."""
    if not math.isfinite(rho_kg_m3) or rho_kg_m3 <= 0:
        raise ValueError("density must be finite and positive")
    xyz = np.asarray(xyz_m, dtype=np.float64)
    gravity = np.asarray(gravity_xyz, dtype=np.float64)
    reference = np.asarray(xref_xyz_m, dtype=np.float64)
    if xyz.shape[-1] != 3 or gravity.shape != (3,) or reference.shape != (3,):
        raise ValueError("coordinates, gravity, and reference must be xyz vectors")
    value = (np.asarray(p_abs_pa) - p_ambient_pa) / rho_kg_m3
    value = value - np.sum(gravity * (xyz - reference), axis=-1)
    return float(value) if np.ndim(value) == 0 else value


def recover_absolute_pressure(
    p_solver_m2_s2: float | np.ndarray,
    p_ambient_pa: float,
    rho_kg_m3: float,
    gravity_xyz: np.ndarray | tuple[float, float, float],
    xyz_m: np.ndarray | tuple[float, float, float],
    xref_xyz_m: np.ndarray | tuple[float, float, float],
) -> float | np.ndarray:
    """pAbs=pAmbient+rho*(pSolver+g dot (C-xref))."""
    xyz = np.asarray(xyz_m, dtype=np.float64)
    gravity = np.asarray(gravity_xyz, dtype=np.float64)
    reference = np.asarray(xref_xyz_m, dtype=np.float64)
    if xyz.shape[-1] != 3 or gravity.shape != (3,) or reference.shape != (3,):
        raise ValueError("coordinates, gravity, and reference must be xyz vectors")
    value = p_ambient_pa + rho_kg_m3 * (
        np.asarray(p_solver_m2_s2) + np.sum(gravity * (xyz - reference), axis=-1)
    )
    return float(value) if np.ndim(value) == 0 else value


def outlet_pressure_values(
    centers_xyz_m: np.ndarray,
    gravity_xyz: np.ndarray | tuple[float, float, float],
    xref_xyz_m: np.ndarray | tuple[float, float, float],
) -> np.ndarray:
    centers = np.asarray(centers_xyz_m, dtype=np.float64)
    gravity = np.asarray(gravity_xyz, dtype=np.float64)
    reference = np.asarray(xref_xyz_m, dtype=np.float64)
    if centers.ndim != 2 or centers.shape[1] != 3:
        raise ValueError("face centers must have shape (n, 3)")
    return -np.sum(gravity * (centers - reference), axis=1)


def foam_header(location: str, cls: str, obj: str) -> str:
    return f"""FoamFile
{{
    version 2.0;
    format ascii;
    class {cls};
    location "{location}";
    object {obj};
}}
"""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def copy_independent(source: Path, destination: Path) -> dict[str, Any]:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"expected a regular source file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    digest = sha256_file(source)
    shutil.copy2(source, destination)
    after = destination.stat()
    if source.stat().st_ino != before.st_ino or source.stat().st_mtime_ns != before.st_mtime_ns:
        raise RuntimeError(f"source changed during copy: {source}")
    if (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino):
        raise RuntimeError(f"copied file is not independent: {source}")
    if after.st_size != before.st_size or sha256_file(destination) != digest:
        raise RuntimeError(f"copy hash/size mismatch: {source}")
    return {
        "source": str(source),
        "bytes": before.st_size,
        "sha256": digest,
        "source_device_inode": [before.st_dev, before.st_ino],
        "staged_device_inode": [after.st_dev, after.st_ino],
    }


def _mesh_dicts(case: Path) -> None:
    system = case / "system"
    write_text(
        system / "controlDict",
        foam_header("system", "dictionary", "controlDict")
        + "application simpleFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\nendTime 1;\ndeltaT 1;\nwriteControl timeStep;\nwriteInterval 1;\nwriteFormat binary;\nwritePrecision 17;\n",
    )
    write_text(
        system / "topoSetDict",
        foam_header("system", "dictionary", "topoSetDict")
        + f"""actions
(
    {{ name wetBranch; type cellSet; action new; source surfaceToCell;
      file "{BRANCH_STL}"; outsidePoints (({OUTSIDE_POINT[0]} {OUTSIDE_POINT[1]} {OUTSIDE_POINT[2]}));
      includeCut true; includeInside true; includeOutside false; nearDistance -1; curvature -100; }}
    {{ name wetBranch; type cellSet; action subset; source boxToCell;
      box ({BRANCH_BOX[0][0]} {BRANCH_BOX[0][1]} {BRANCH_BOX[0][2]})
          ({BRANCH_BOX[1][0]} {BRANCH_BOX[1][1]} {BRANCH_BOX[1][2]}); }}
);
""",
    )
    write_text(
        system / "endSectionsTopoSetDict",
        foam_header("system", "dictionary", "endSectionsTopoSetDict")
        + f"""actions
(
    {{ name inletFaces; type faceSet; action new; source patchToFace; sourceInfo {{ patch oldInternalFaces; }} }}
    {{ name inletFaces; type faceSet; action subset; source boxToFace;
      box ({X_INLET - 1e-5:.8f} -1.10 0.30) ({X_INLET + 1e-5:.8f} 0.0 1.35); }}
    {{ name outletFaces; type faceSet; action new; source patchToFace; sourceInfo {{ patch oldInternalFaces; }} }}
    {{ name outletFaces; type faceSet; action subset; source boxToFace;
      box ({OUTLET_FACE_CENTER_RANGE[0]:.8f} -1.10 0.30) ({OUTLET_FACE_CENTER_RANGE[1]:.8f} 0.0 1.35); }}
);
""",
    )
    write_text(
        system / "createPatchDict",
        foam_header("system", "dictionary", "createPatchDict")
        + """pointSync false;
patches
(
    { name wetInlet; patchInfo { type patch; inGroups (inlet); } constructFrom set; set inletFaces; }
    { name wetOutlet; patchInfo { type patch; inGroups (outlet); } constructFrom set; set outletFaces; }
);
""",
    )
    # Some mesh utilities instantiate finite-volume mesh objects and read the
    # case schemes even though no equation is solved during this stage.
    write_text(
        system / "fvSchemes",
        foam_header("system", "dictionary", "fvSchemes")
        + """ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default none; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
""",
    )
    write_text(
        system / "fvSolution",
        foam_header("system", "dictionary", "fvSolution")
        + "solvers { p { solver PCG; preconditioner DIC; tolerance 1e-8; relTol 0.05; } }\n",
    )


def mesh_pipeline_script() -> str:
    return """#!/usr/bin/env bash
set +e
. /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1
foam_rc=$?
set -Eeuo pipefail
if [[ $foam_rc -ne 0 || -z \"${WM_PROJECT_VERSION:-}\" ]]; then
    echo \"OpenFOAM environment init failed rc=$foam_rc\" >&2
    exit 70
fi
export FOAM_FILEHANDLER=collated
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
cd /case
reconstructParMesh -constant -case /case -fileHandler collated > /bundle/logs/01-reconstructParMesh.log 2>&1
topoSet -constant -case /case > /bundle/logs/02-topoSet-branch.log 2>&1
subsetMesh wetBranch -overwrite -patch oldInternalFaces -case /case > /bundle/logs/03-subsetMesh.log 2>&1
topoSet -constant -case /case -dict system/endSectionsTopoSetDict > /bundle/logs/04-topoSet-sections.log 2>&1
createPatch -overwrite -case /case -dict system/createPatchDict > /bundle/logs/05-createPatch.log 2>&1
checkMesh -constant -allTopology -allGeometry -writeAllFields -case /case > /bundle/logs/06-checkMesh.log 2>&1
postProcess -func writeCellCentres -constant -case /case > /bundle/logs/07-writeCellCentres.log 2>&1
"""


def solver_wrapper_script() -> str:
    return """#!/usr/bin/env bash
set +e
. /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1
foam_rc=$?
set -Eeuo pipefail
if [[ $foam_rc -ne 0 || -z "${WM_PROJECT_VERSION:-}" ]]; then
    echo "OpenFOAM environment init failed rc=$foam_rc" >&2
    exit 70
fi
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
cd /case
while [[ ! -f /bundle/GO ]]; do
    if [[ -f /global-runs/PAUSE || -f /bundle/PAUSE || -f /case/PAUSE ]]; then
        echo "PAUSE before GO" >&2
        exit 75
    fi
    sleep 1
done
echo "I4F_WET_BRANCH_GO $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exec nice -n 19 simpleFoam > /case/log.simpleFoam 2>&1
"""


def create_bundle(source_case: Path = SOURCE_CASE, runs_dir: Path = RUNS) -> Path:
    source_case = source_case.resolve(strict=True)
    source_mesh = source_case / "processors10/constant/polyMesh"
    source_stl = source_case / BRANCH_STL
    if not source_mesh.is_dir() or not source_stl.is_file():
        raise FileNotFoundError("frozen source mesh or selected branch STL is missing")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle = runs_dir.resolve() / f"i4f-wet-branch-reference-{stamp}"
    suffix = 1
    while bundle.exists():
        bundle = runs_dir.resolve() / f"i4f-wet-branch-reference-{stamp}-attempt{suffix:03d}"
        suffix += 1
    case = bundle / "case"
    (bundle / "logs").mkdir(parents=True)
    (bundle / "figures").mkdir()
    copied = []
    for source in sorted(path for path in source_mesh.rglob("*") if path.is_file()):
        copied.append(copy_independent(source, case / source.relative_to(source_case)))
    copied.append(copy_independent(source_stl, case / BRANCH_STL))
    copied.append(
        copy_independent(source_case / "system/decomposeParDict", case / "system/decomposeParDict")
    )
    # Read the actual inherited turbulence initialization values rather than inventing inlet values.
    inherited = {}
    for field, default in (("k", K_INLET), ("omega", OMEGA_INLET)):
        path = source_case / "0" / field
        raw = path.read_text(encoding="latin1")
        match = re.search(r"internalField\s+uniform\s+([-+0-9.eE]+)\s*;", raw)
        if not match:
            raise ValueError(
                f"source 0/{field} is not a uniform field; sample a native inlet instead"
            )
        inherited[field] = {"value": float(match.group(1)), "sha256": sha256_file(path)}
    global_poly = source_case / "constant/polyMesh/boundary"
    copied.append(copy_independent(global_poly, case / "constant/polyMesh/boundary"))
    _mesh_dicts(case)
    scripts = bundle / "scripts"
    write_text(scripts / "mesh_pipeline.sh", mesh_pipeline_script())
    (scripts / "mesh_pipeline.sh").chmod(0o755)
    write_text(scripts / "run_solver.sh", solver_wrapper_script())
    (scripts / "run_solver.sh").chmod(0o755)
    source_snapshot = bundle / "source/prepare_i4f_wet_branch_reference.py"
    source_snapshot.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve(), source_snapshot)
    metadata = {
        "schema": "i4f-wet-branch-reference-preparation/v1",
        "created_utc": utc_now(),
        "source_case": str(source_case),
        "repository_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "repository_dirty_status": subprocess.run(
            ["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines(),
        "preparation_script_sha256": sha256_file(Path(__file__).resolve()),
        "preparation_source_snapshot": {
            "path": str(source_snapshot.relative_to(bundle)),
            "sha256": sha256_file(source_snapshot),
        },
        "source_static_inputs": copied,
        "preparation_scripts": {
            "mesh_pipeline_sha256": sha256_file(scripts / "mesh_pipeline.sh"),
            "solver_wrapper_sha256": sha256_file(scripts / "run_solver.sh"),
        },
        "source_inherited_turbulence_fields": inherited,
        "openfoam_image": IMAGE,
        "branch": {
            "name": "A_upper",
            "stl": BRANCH_STL,
            "inlet_x_m": X_INLET,
            "outlet_control_x_m": X_OUTLET,
            "outlet_face_center_selection_range_x_m": list(OUTLET_FACE_CENTER_RANGE),
            "outlet_section_qualification": "near-mouth native cut; face centers follow the curved terminal section within this x window",
            "outside_point_xyz_m": OUTSIDE_POINT,
            "selection_box_xyz_m": [list(BRANCH_BOX[0]), list(BRANCH_BOX[1])],
            "retains_native_zero_thickness_divider": True,
            "historical_upper_a_pmin_xyz_m": [4.220088, -0.380816, 0.970915],
        },
        "physics": {
            "purpose": "fully-water-filled single-branch steady head reference",
            "solver": "stock OpenCFD v2512 simpleFoam, incompressible, RAS kOmegaSST",
            "phase_assumption": "single-phase water throughout the selected branch; no gas, interface, cavitation, or valve model",
            "upstream_boundary": "prescribed uniform velocity at the native valve-seat section; tank and valve losses are outside this reference",
            "downstream_boundary": "ambient absolute pressure recovered from a hydrostatic facewise reduced-pressure condition at the near-mouth native cut",
            "wall_model": "native apparatus walls and zero-thickness divider surfaces retained; no added divider thickness or smoothing",
            "water_density_kg_m3": RHO,
            "water_dynamic_viscosity_pa_s": MU,
            "water_kinematic_viscosity_m2_s": MU / RHO,
            "flow_target_m3_s": Q_TARGET,
            "flow_source": "derived from earlier CFD; not measured and not an outlet history",
            "gravity_xyz_m_s2": GRAVITY.tolist(),
            "ambient_pressure_pa_abs": P_AMBIENT,
            "pressure_transform": "pSolver=(pAbs-pAmbient)/rho - g dot (C-xref)",
            "outlet_boundary": "pSolver=-g dot (Cf-xref), facewise, so recovered pAbs=pAmbient",
            "pressure_recovery": "pAbs=pAmbient+rho*(pSolver+g dot (C-xref))",
            "cavitation": "not modeled; no cavitation claim",
        },
        "resource_budget": {
            "mesh_utility_cpu_quota": 0.75,
            "solver_cpu_quota": 0.75,
            "solver_process_count": 1,
            "solver_hard_wall_s": MAX_WALL_S,
            "graceful_save_wall_s": SAVE_WALL_S,
            "output_cap_bytes": OUTPUT_CAP,
        },
        "status": "staged_mesh_inputs",
    }
    atomic_json(bundle / "preparation.json", metadata)
    return bundle


def run_mesh_preparation(bundle: Path) -> None:
    bundle = bundle.resolve(strict=True)
    result_path = bundle / "mesh-preparation.json"
    if result_path.exists():
        index = 2
        while (bundle / f"mesh-preparation-attempt{index:03d}.json").exists():
            index += 1
        result_path = bundle / f"mesh-preparation-attempt{index:03d}.json"
    command = [
        sys.executable,
        str(ROOT / "scripts/run_local.py"),
        "--threads",
        "1",
        "--timeout",
        "900",
        "--",
        "nice",
        "-n",
        "19",
        "docker",
        "run",
        "--rm",
        "--cpus=0.75",
        "--memory=4g",
        "--log-driver=none",
        "-v",
        f"{bundle / 'case'}:/case",
        "-v",
        f"{bundle}:/bundle",
        "-w",
        "/case",
        IMAGE,
        "bash",
        "/bundle/scripts/mesh_pipeline.sh",
    ]
    started = utc_now()
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    result: dict[str, Any] = {
        "schema": "i4f-wet-branch-mesh-preparation/v1",
        "started_utc": started,
        "completed_utc": utc_now(),
        "command": command,
        "returncode": process.returncode,
        "stdout": process.stdout[-3000:],
        "stderr": process.stderr[-3000:],
        "status": "failed" if process.returncode else "mesh_tools_completed",
    }
    if process.returncode == 0:
        mesh = bundle / "case/constant/polyMesh"
        patches = measure_patches(mesh, ("wetInlet", "wetOutlet"))
        boundary = _read_global_boundary(mesh / "boundary")
        result["patches"] = patches
        result["boundary_patches"] = [
            {"name": name, "type": kind, "n_faces": count} for name, kind, count, _ in boundary
        ]
        result["connectivity_method"] = (
            "union-find over native owner/neighbour face adjacency; "
            "splitMeshRegions was skipped because source cellZones overlap"
        )
        source_records = json.loads((bundle / "preparation.json").read_text())[
            "source_static_inputs"
        ]
        result["source_inputs_unchanged"] = all(
            Path(item["source"]).is_file() and sha256_file(Path(item["source"])) == item["sha256"]
            for item in source_records
        )
        result["native_mesh_cell_count"] = _mesh_cell_count(mesh)
        result["connected_cell_regions"] = _connected_cell_regions(mesh)
        result["checkMesh_log_sha256"] = sha256_file(bundle / "logs/06-checkMesh.log")
        check_text = (bundle / "logs/06-checkMesh.log").read_text(errors="replace")
        total_volume_match = re.search(r"Total volume =\s*([-+0-9.eE]+)", check_text)
        max_nonorth = re.search(
            r"Mesh non-orthogonality Max:\s*([-+0-9.eE]+) average:\s*([-+0-9.eE]+)", check_text
        )
        max_skewness = re.search(r"Max skewness =\s*([-+0-9.eE]+)", check_text)
        concave_cells = re.search(
            r"Concave cells \(using face planes\) found, number of cells:\s*(\d+)", check_text
        )
        result["checkMesh_summary"] = {
            "normal_End": "End" in check_text.splitlines(),
            "failed_check_count": int(re.search(r"Failed (\d+) mesh checks\.", check_text).group(1))
            if re.search(r"Failed (\d+) mesh checks\.", check_text)
            else None,
            "max_nonorthogonality_deg": float(max_nonorth.group(1)) if max_nonorth else None,
            "mean_nonorthogonality_deg": float(max_nonorth.group(2)) if max_nonorth else None,
            "max_skewness": float(max_skewness.group(1)) if max_skewness else None,
            "concave_cell_count": int(concave_cells.group(1)) if concave_cells else 0,
            "total_volume_m3": float(total_volume_match.group(1)) if total_volume_match else None,
            "log_tail": check_text[-5000:],
        }
        if not result["source_inputs_unchanged"]:
            result["status"] = "failed_source_input_immutability"
        elif not (mesh / "C").is_file() or not (bundle / "case/constant/cellVolume").is_file():
            result["status"] = "failed_native_geometry_fields_missing"
        elif result["connected_cell_regions"] != 1:
            result["status"] = "failed_not_single_connected_branch"
        elif not all(patches[name]["face_count"] > 0 for name in ("wetInlet", "wetOutlet")):
            result["status"] = "failed_empty_section"
        else:
            configure_solver_case(bundle, patches)
            prep = json.loads((bundle / "preparation.json").read_text())
            prep["mesh_preparation_record"] = result_path.name
            prep["mesh_checkMesh_summary"] = result["checkMesh_summary"]
            prep["mesh_connectivity"] = {
                "connected_regions": result["connected_cell_regions"],
                "cells": result["native_mesh_cell_count"],
                "method": result["connectivity_method"],
            }
            atomic_json(bundle / "preparation.json", prep)
            result["status"] = "solver_case_ready"
    atomic_json(result_path, result)
    if result["status"] != "solver_case_ready":
        raise RuntimeError(f"mesh preparation failed: {result['status']}")


def _mesh_cell_count(mesh: Path) -> int:
    owners = _read_global_labels(mesh / "owner")
    neighbours = _read_global_labels(mesh / "neighbour")
    return int(max(owners.max(initial=0), neighbours.max(initial=0)) + 1)


def _connected_cell_regions(mesh: Path) -> int:
    owners = _read_global_labels(mesh / "owner")
    neighbours = _read_global_labels(mesh / "neighbour")
    return _count_connected_cells(owners, neighbours)


def _count_connected_cells(owners: np.ndarray, neighbours: np.ndarray) -> int:
    owners = np.asarray(owners, dtype=np.int64)
    neighbours = np.asarray(neighbours, dtype=np.int64)
    n_cells = int(max(owners.max(initial=0), neighbours.max(initial=0)) + 1)
    parent = np.arange(n_cells, dtype=np.int64)

    def find(cell: int) -> int:
        while parent[cell] != cell:
            parent[cell] = parent[parent[cell]]
            cell = int(parent[cell])
        return cell

    for own, nei in zip(owners[: len(neighbours)], neighbours, strict=True):
        root_own, root_nei = find(int(own)), find(int(nei))
        if root_own != root_nei:
            parent[root_nei] = root_own
    roots = np.fromiter((find(i) for i in range(n_cells)), dtype=np.int64, count=n_cells)
    return int(np.unique(roots).size)


def measure_patches(mesh: Path, names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    points = _read_global_points(mesh / "points")
    offsets, labels = _read_global_faces(mesh / "faces")
    boundary = _read_global_boundary(mesh / "boundary")
    result = {}
    for name, patch_type, count, start in boundary:
        if name not in names:
            continue
        area = 0.0
        area_vector = np.zeros(3)
        projected_x = 0.0
        centers = []
        for face_id in range(start, start + count):
            sf, center, face_area = _face_geometry(face_id, offsets, labels, points)
            area += face_area
            area_vector += sf
            projected_x += abs(float(sf[0]))
            centers.append(center)
        if count == 0 or area <= 0:
            raise ValueError(f"empty/zero-area native patch {name}")
        centers_array = np.asarray(centers)
        result[name] = {
            "patch_type": patch_type,
            "face_count": count,
            "native_area_m2": area,
            "projected_x_area_m2": projected_x,
            "area_vector_sum_m2": area_vector.tolist(),
            "mean_face_center_xyz_m": centers_array.mean(axis=0).tolist(),
            "face_centers_xyz_m": centers_array.tolist(),
            "center_bounds_xyz_m": {
                axis: [float(centers_array[:, i].min()), float(centers_array[:, i].max())]
                for i, axis in enumerate(("x", "y", "z"))
            },
        }
    missing = sorted(set(names) - set(result))
    if missing:
        raise ValueError(f"missing native sections: {missing}")
    return result


def configure_solver_case(bundle: Path, patches: dict[str, dict[str, Any]]) -> None:
    case = bundle / "case"
    if (case / "0").exists():
        raise FileExistsError("initial fields already exist")
    inlet = patches["wetInlet"]
    outlet = patches["wetOutlet"]
    area_in = float(inlet["projected_x_area_m2"])
    area_out = float(outlet["projected_x_area_m2"])
    x_in = float(inlet["mean_face_center_xyz_m"][0])
    x_out = float(outlet["mean_face_center_xyz_m"][0])
    if area_in <= 0 or area_out <= 0:
        raise ValueError("native section projected area must be positive")
    if (
        abs(x_in - X_INLET) > 5e-4
        or not OUTLET_FACE_CENTER_RANGE[0] <= x_out <= OUTLET_FACE_CENTER_RANGE[1]
    ):
        raise ValueError(
            f"native section coordinates outside declared control sections: inlet={x_in}, outlet={x_out}"
        )
    xref = np.asarray(outlet["mean_face_center_xyz_m"], dtype=np.float64)
    xref[0] = X_OUTLET
    p_out = outlet_pressure_values(np.asarray(outlet["face_centers_xyz_m"]), GRAVITY, xref)
    u_in = Q_TARGET / area_in
    boundary = _read_global_boundary(case / "constant/polyMesh/boundary")
    inlet_normal = np.asarray(inlet["area_vector_sum_m2"], dtype=np.float64)
    outlet_normal = np.asarray(outlet["area_vector_sum_m2"], dtype=np.float64)
    if inlet_normal[0] >= 0 or outlet_normal[0] <= 0:
        raise ValueError("native section area-vector orientation is not outward at inlet/outlet")
    if np.abs(inlet_normal[1:]).sum() > 0.02 * abs(inlet_normal[0]) or np.abs(
        outlet_normal[1:]
    ).sum() > 0.02 * abs(outlet_normal[0]):
        raise ValueError("native control sections are not sufficiently normal to x")
    fields = _boundary_conditions(boundary, p_out, u_in)
    (case / "0").mkdir()
    field_specs = (
        ("p", "volScalarField", "[0 2 -2 0 0 0 0]", "uniform 0"),
        ("U", "volVectorField", "[0 1 -1 0 0 0 0]", f"uniform ({u_in:.17g} 0 0)"),
        ("k", "volScalarField", "[0 2 -2 0 0 0 0]", f"uniform {K_INLET:.17g}"),
        ("omega", "volScalarField", "[0 0 -1 0 0 0 0]", f"uniform {OMEGA_INLET:.17g}"),
        ("nut", "volScalarField", "[0 2 -1 0 0 0 0]", "uniform 0"),
    )
    for name, field_class, dimensions, initial in field_specs:
        write_text(
            case / "0" / name,
            foam_header("0", field_class, name)
            + f"dimensions {dimensions};\ninternalField {initial};\nboundaryField\n{{\n{fields[name]}\n}}\n",
        )
    write_text(
        case / "constant/transportProperties",
        foam_header("constant", "dictionary", "transportProperties")
        + f"transportModel Newtonian;\nnu [0 2 -1 0 0 0 0] {MU / RHO:.17g};\n",
    )
    write_text(
        case / "constant/turbulenceProperties",
        foam_header("constant", "dictionary", "turbulenceProperties")
        + "simulationType RAS;\nRAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }\n",
    )
    _write_solver_dictionaries(case)
    metadata = json.loads((bundle / "preparation.json").read_text())
    metadata["status"] = "ready_for_simplefoam"
    metadata["flow_setup"] = {
        "target_Q_m3_s": Q_TARGET,
        "inlet_area_m2": area_in,
        "outlet_area_m2": area_out,
        "inlet_Ux_m_s": u_in,
        "pressure_reference_xyz_m": xref.tolist(),
        "outlet_pSolver_values_m2_s2": p_out.tolist(),
        "inlet_k_m2_s2": K_INLET,
        "inlet_omega_s_1": OMEGA_INLET,
        "inlet_turbulence_note": "source initialization values, not measured inlet turbulence",
        "near_mouth_section_actual_face_center_bounds_xyz_m": outlet["center_bounds_xyz_m"],
        "near_mouth_section_area_vector_m2": outlet["area_vector_sum_m2"],
    }
    atomic_json(bundle / "preparation.json", metadata)
    freeze_inputs(bundle)
    render_geometry(bundle)


def clone_upwind_trial(parent_bundle: Path, runs_dir: Path = RUNS) -> Path:
    """Clone the frozen single-phase branch case and change only U convection."""
    parent_bundle = parent_bundle.resolve(strict=True)
    parent_case = parent_bundle / "case"
    parent_freeze_path = parent_bundle / "input-freeze.json"
    if not parent_freeze_path.is_file():
        raise FileNotFoundError("parent input freeze is required")
    verify_freeze(parent_bundle)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle = runs_dir.resolve() / f"i4f-wet-branch-upwind-{stamp}"
    suffix = 1
    while bundle.exists():
        bundle = runs_dir.resolve() / f"i4f-wet-branch-upwind-{stamp}-attempt{suffix:03d}"
        suffix += 1
    (bundle / "case").mkdir(parents=True)
    (bundle / "logs").mkdir()
    (bundle / "figures").mkdir()
    (bundle / "scripts").mkdir()
    parent_freeze = json.loads(parent_freeze_path.read_text(encoding="utf-8"))
    copied = []
    for row in parent_freeze["files"]:
        copied.append(copy_independent(parent_case / row["path"], bundle / "case" / row["path"]))

    scheme_path = bundle / "case/system/fvSchemes"
    scheme_before = scheme_path.read_text(encoding="utf-8")
    old_scheme = "div(phi,U) bounded Gauss linearUpwind grad(U);"
    new_scheme = "div(phi,U) bounded Gauss upwind;"
    if scheme_before.count(old_scheme) != 1:
        raise ValueError("frozen parent does not contain exactly one expected U convection scheme")
    scheme_path.write_text(scheme_before.replace(old_scheme, new_scheme), encoding="utf-8")

    control_path = bundle / "case/system/controlDict"
    control_before = control_path.read_text(encoding="utf-8")
    if control_before.count("pressureExtrema") != 1 or "runawayLimits" in control_before:
        raise ValueError("parent runtime diagnostic layout is not the expected clean baseline")
    guard = """
    runawayLimits
    {
        type runTimeControl;
        libs ("libutilityFunctionObjects.so");
        nWriteStep 1;
        conditions
        {
            excessiveSpeed
            {
                type minMax;
                functionObject pressureExtrema;
                fields (max(mag(U)));
                value 200;
                mode maximum;
            }
            excessivePositiveKinematicPressure
            {
                type minMax;
                functionObject pressureExtrema;
                fields (max(p));
                value 100000;
                mode maximum;
            }
            excessiveNegativeKinematicPressure
            {
                type minMax;
                functionObject pressureExtrema;
                fields (min(p));
                value -100000;
                mode minimum;
            }
        }
        satisfiedAction end;
    }
"""
    closing = control_before.rstrip().rfind("}")
    if closing < 0:
        raise ValueError("cannot locate controlDict functions closing brace")
    control_path.write_text(
        control_before[:closing] + guard + control_before[closing:], encoding="utf-8"
    )

    source_snapshot = bundle / "source/prepare_i4f_wet_branch_reference.py"
    source_snapshot.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve(), source_snapshot)
    shutil.copy2(parent_bundle / "scripts/mesh_pipeline.sh", bundle / "scripts/mesh_pipeline.sh")
    write_text(bundle / "scripts/run_solver.sh", solver_wrapper_script())
    (bundle / "scripts/run_solver.sh").chmod(0o755)

    parent_prep = json.loads((parent_bundle / "preparation.json").read_text(encoding="utf-8"))
    metadata = {
        "schema": "i4f-wet-branch-upwind-trial/v1",
        "created_utc": utc_now(),
        "parent_bundle": str(parent_bundle),
        "parent_input_freeze_sha256": sha256_file(parent_freeze_path),
        "parent_case_input_files": len(parent_freeze["files"]),
        "parent_case_input_freeze_files": copied,
        "repository_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "repository_dirty_status": subprocess.run(
            ["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines(),
        "preparation_script_sha256": sha256_file(Path(__file__).resolve()),
        "preparation_source_snapshot": {
            "path": str(source_snapshot.relative_to(bundle)),
            "sha256": sha256_file(source_snapshot),
        },
        "physics_and_solver": parent_prep.get("physics"),
        "flow_setup": parent_prep.get("flow_setup"),
        "mesh_and_geometry": parent_prep.get("branch"),
        "declared_comparison": {
            "only_equation_input_change": {
                "path": "case/system/fvSchemes",
                "from": old_scheme,
                "to": new_scheme,
            },
            "control_only_guard_change": {
                "path": "case/system/controlDict",
                "purpose": "terminate and write on declared runaway extrema; no equation change",
                "thresholds": {
                    "max_magnitude_U_m_s": 200.0,
                    "abs_kinematic_p_m2_s2": 100000.0,
                    "approx_abs_pressure_threshold_pa": 100000000.0,
                },
            },
            "same_parent_mesh_initial_fields_flow_boundaries_turbulence_solver_schemes_and_linear_controls": True,
        },
        "parent_reference": {
            "case_input_sha256": {row["path"]: row["sha256"] for row in parent_freeze["files"]},
            "parent_preparation_sha256": sha256_file(parent_bundle / "preparation.json"),
        },
        "openfoam_image": IMAGE,
        "resource_budget": {
            "solver_cpu_quota": 0.75,
            "solver_process_count": 1,
            "solver_hard_wall_s": MAX_WALL_S,
            "graceful_save_wall_s": SAVE_WALL_S,
            "output_cap_bytes": OUTPUT_CAP,
        },
        "status": "prepared_for_upwind_guarded_trial",
    }
    atomic_json(bundle / "preparation.json", metadata)
    freeze_inputs(bundle)
    return bundle


def _boundary_conditions(
    boundary: list[tuple[str, str, int, int]], p_out: np.ndarray, u_in: float
) -> dict[str, str]:
    entries: dict[str, list[str]] = {name: [] for name in ("p", "U", "k", "omega", "nut")}
    for name, patch_type, count, _ in boundary:
        if count == 0:
            continue
        if name == "wetInlet":
            entries["p"].append(f"    {name} {{ type zeroGradient; }}")
            entries["U"].append(
                f"    {name} {{ type fixedValue; value uniform ({u_in:.17g} 0 0); }}"
            )
            entries["k"].append(f"    {name} {{ type fixedValue; value uniform {K_INLET:.17g}; }}")
            entries["omega"].append(
                f"    {name} {{ type fixedValue; value uniform {OMEGA_INLET:.17g}; }}"
            )
            entries["nut"].append(f"    {name} {{ type calculated; value uniform 0; }}")
        elif name == "wetOutlet":
            values = "\n".join(f"        {value:.17g}" for value in p_out)
            entries["p"].append(
                f"    {name} {{ type fixedValue; value nonuniform List<scalar> {count}\n    (\n{values}\n    ); }}"
            )
            entries["U"].append(
                f"    {name} {{ type pressureInletOutletVelocity; value uniform (0 0 0); }}"
            )
            entries["k"].append(f"    {name} {{ type zeroGradient; }}")
            entries["omega"].append(f"    {name} {{ type zeroGradient; }}")
            entries["nut"].append(f"    {name} {{ type calculated; value uniform 0; }}")
        elif patch_type in {"wall", "wallPolyPatch"}:
            entries["p"].append(f"    {name} {{ type zeroGradient; }}")
            entries["U"].append(f"    {name} {{ type noSlip; }}")
            entries["k"].append(
                f"    {name} {{ type kqRWallFunction; value uniform {K_INLET:.17g}; }}"
            )
            entries["omega"].append(
                f"    {name} {{ type omegaWallFunction; value uniform {OMEGA_INLET:.17g}; }}"
            )
            entries["nut"].append(f"    {name} {{ type nutkWallFunction; value uniform 0; }}")
        elif patch_type in {"symmetry", "symmetryPlane"}:
            for field in entries:
                entries[field].append(f"    {name} {{ type {patch_type}; }}")
        else:
            raise ValueError(f"unexpected non-wall boundary patch: {name} ({patch_type})")
    return {name: "\n".join(values) for name, values in entries.items()}


def _write_solver_dictionaries(case: Path) -> None:
    system = case / "system"
    write_text(
        system / "controlDict",
        foam_header("system", "dictionary", "controlDict")
        + """application simpleFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime 3000;
deltaT 1;
writeControl timeStep;
writeInterval 1;
purgeWrite 2;
writeFormat binary;
writePrecision 17;
writeCompression off;
timeFormat general;
timePrecision 12;
runTimeModifiable yes;
functions
{
    inletVolumeFlow
    {
        type surfaceFieldValue; libs (fieldFunctionObjects); log true;
        writeControl timeStep; writeInterval 1;
        regionType patch; name wetInlet; operation sum; fields (phi); writeFields false;
    }
    outletVolumeFlow
    {
        type surfaceFieldValue; libs (fieldFunctionObjects); log true;
        writeControl timeStep; writeInterval 1;
        regionType patch; name wetOutlet; operation sum; fields (phi); writeFields false;
    }
    pressureExtrema
    {
        type fieldMinMax; libs (fieldFunctionObjects); log true;
        writeControl timeStep; writeInterval 1; fields (p U k omega);
    }
}
""",
    )
    write_text(
        system / "fvSchemes",
        foam_header("system", "dictionary", "fvSchemes")
        + """ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; grad(U) cellLimited Gauss linear 1; }
divSchemes
{
    default none;
    div(phi,U) bounded Gauss linearUpwind grad(U);
    div(phi,k) bounded Gauss upwind;
    div(phi,omega) bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
""",
    )
    write_text(
        system / "fvSolution",
        foam_header("system", "dictionary", "fvSolution")
        + """solvers
{
    p { solver GAMG; tolerance 1e-8; relTol 0.05; smoother GaussSeidel; agglomerator faceAreaPair; mergeLevels 1; }
    pFinal { $p; relTol 0; }
    U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }
    UFinal { $U; relTol 0; }
    k { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }
    kFinal { $k; relTol 0; }
    omega { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }
    omegaFinal { $omega; relTol 0; }
}
SIMPLE
{
    nNonOrthogonalCorrectors 1;
    consistent yes;
    residualControl { p 1e-6; U 1e-5; k 1e-5; omega 1e-5; }
}
relaxationFactors
{
    fields { p 0.3; }
    equations { U 0.7; k 0.7; omega 0.7; }
}
""",
    )


def freeze_inputs(bundle: Path) -> dict[str, Any]:
    case = bundle / "case"
    records = []
    for path in sorted(case.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(case)
        is_output_time = False
        try:
            is_output_time = float(relative.parts[0]) > 0.0
        except ValueError:
            pass
        if is_output_time or path.name.startswith("log."):
            continue
        stat = path.stat()
        records.append(
            {
                "path": relative.as_posix(),
                "bytes": stat.st_size,
                "sha256": sha256_file(path),
                "device_inode": [stat.st_dev, stat.st_ino],
            }
        )
    data = {
        "schema": "i4f-wet-branch-input-freeze/v1",
        "case_root": str(case),
        "created_utc": utc_now(),
        "files": records,
    }
    atomic_json(bundle / "input-freeze.json", data)
    return data


def verify_freeze(bundle: Path) -> None:
    freeze = json.loads((bundle / "input-freeze.json").read_text())
    case = bundle / "case"
    changed = []
    for row in freeze["files"]:
        path = case / row["path"]
        if (
            not path.is_file()
            or path.stat().st_size != row["bytes"]
            or sha256_file(path) != row["sha256"]
        ):
            changed.append(row["path"])
    if changed:
        raise RuntimeError("frozen inputs changed: " + ", ".join(changed))


def _parse_patch_vector_values(raw: bytes, patch: str, count: int) -> np.ndarray:
    if count == 0:
        return np.empty((0, 3), dtype=np.float64)
    match = re.search(rb"(?m)^\s*" + re.escape(patch.encode()) + rb"\s*\{", raw)
    if match is None:
        raise ValueError(f"missing patch {patch}")
    tail = raw[match.end() :]
    value_kind = re.search(rb"value\s+(uniform|nonuniform)\b", tail)
    if value_kind is None:
        raise ValueError(f"missing vector patch value for {patch}")
    if value_kind.group(1) == b"uniform":
        vector = re.search(
            rb"value\s+uniform\s*\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)", tail
        )
        if vector is None:
            raise ValueError(f"invalid uniform vector value for {patch}")
        return np.tile(np.asarray([float(v) for v in vector.groups()]), (count, 1))
    values_match = re.search(rb"value\s+nonuniform\s+List<vector>\s+(\d+)\s*\(", tail)
    if values_match is None or int(values_match.group(1)) != count:
        raise ValueError(f"vector patch count mismatch for {patch}")
    start = match.end() + values_match.end()
    if b"format      ascii" in raw[: match.start()]:
        end = re.search(rb"\n\s*\)\s*;", raw[start:])
        if end is None:
            raise ValueError(f"cannot find vector patch list end for {patch}")
        values = np.fromstring(
            raw[start : start + end.start()].decode("ascii").replace("(", " ").replace(")", " "),
            sep=" ",
        )
        values = values.reshape((-1, 3))
    else:
        values = np.frombuffer(raw[start : start + 24 * count], dtype="<f8").copy().reshape((-1, 3))
    if values.shape != (count, 3) or not np.isfinite(values).all():
        raise ValueError(f"invalid vector patch values for {patch}")
    return values


def _parse_simplefoam_residuals(log_path: Path) -> dict[str, Any]:
    if not log_path.exists():
        return {"log_present": False, "iterations": 0, "last": {}}
    text = log_path.read_text(errors="replace")
    time_match = re.findall(r"(?m)^Time =\s*([-+0-9.eE]+)\s*$", text)
    residuals = re.findall(
        r"(?m)^\s*(?:[A-Za-z_]\w*:\s*)*Solving for "
        r"(p|Ux|Uy|Uz|k|omega), Initial residual = ([^,]+), "
        r"Final residual = ([^,]+), No Iterations (\d+)",
        text,
    )
    last: dict[str, dict[str, float | int]] = {}
    for field, initial, final, iterations in residuals:
        last[field] = {
            "initial_residual": float(initial),
            "final_residual": float(final),
            "linear_iterations": int(iterations),
        }
    return {
        "log_present": True,
        "log_sha256": sha256_file(log_path),
        "log_bytes": log_path.stat().st_size,
        "time_entries": len(time_match),
        "last_logged_iteration": int(float(time_match[-1])) if time_match else None,
        "linear_solve_records": len(residuals),
        "last_linear_solves": last,
        "normal_End": "End" in text.splitlines(),
        "tail": text[-5000:],
    }


def _parse_simplefoam_iteration_history(log_path: Path) -> list[dict[str, Any]]:
    """Extract one row per steady SIMPLE iteration from standard solver output."""
    if not log_path.is_file():
        return []
    text = log_path.read_text(errors="replace")
    starts = list(re.finditer(r"(?m)^Time =\s*([-+0-9.eE]+)\s*$", text))
    rows: list[dict[str, Any]] = []
    number = r"([-+0-9.eE]+)"
    location = r"\s+in cell\s+(\d+)\s+at location\s+\(([^()]*)\)"
    solve_re = re.compile(
        r"(?m)^\s*(?:[A-Za-z_]\w*:\s*)*Solving for "
        r"(p|Ux|Uy|Uz|k|omega), Initial residual = ([^,]+), "
        r"Final residual = ([^,]+), No Iterations (\d+)"
    )
    for index, start in enumerate(starts):
        stop = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[start.end() : stop]
        row: dict[str, Any] = {"steady_iteration": int(float(start.group(1)))}
        by_field: dict[str, list[tuple[float, float, int]]] = {}
        for field, initial, final, count in solve_re.findall(block):
            by_field.setdefault(field, []).append((float(initial), float(final), int(count)))
        for field, solves in by_field.items():
            row[f"{field}_solve_count"] = len(solves)
            row[f"{field}_initial_residual_first"] = solves[0][0]
            row[f"{field}_final_residual_last"] = solves[-1][1]
            row[f"{field}_linear_iterations_total"] = sum(item[2] for item in solves)
            if field == "p":
                row["p_initial_residual_max"] = max(item[0] for item in solves)
                row["p_final_residual_max"] = max(item[1] for item in solves)
        for output, pattern in (
            ("p_min", rf"min\(p\) =\s*{number}{location}"),
            ("p_max", rf"max\(p\) =\s*{number}{location}"),
            ("U_mag_max", rf"max\(mag\(U\)\) =\s*{number}{location}"),
            ("k_max", rf"max\(k\) =\s*{number}{location}"),
            ("omega_max", rf"max\(omega\) =\s*{number}{location}"),
        ):
            match = re.search(pattern, block)
            if match:
                row[f"{output}_value"] = float(match.group(1))
                row[f"{output}_cell"] = int(match.group(2))
                xyz = np.fromstring(match.group(3), sep=" ", dtype=np.float64)
                if xyz.shape != (3,):
                    raise ValueError(
                        f"invalid {output} location in iteration {row['steady_iteration']}"
                    )
                row[f"{output}_xyz_m"] = xyz.tolist()
        for patch in ("wetInlet", "wetOutlet"):
            match = re.search(rf"sum\({patch}\) of phi =\s*{number}", block)
            if match:
                row[f"{patch}_Q_m3_s"] = float(match.group(1))
        match = re.search(
            rf"time step continuity errors : sum local =\s*{number}, "
            rf"global =\s*{number}, cumulative =\s*{number}",
            block,
        )
        if match:
            row["continuity_sum_local"] = float(match.group(1))
            row["continuity_global"] = float(match.group(2))
            row["continuity_cumulative"] = float(match.group(3))
        if row.get("p_min_value") is not None and row.get("p_max_value") is not None:
            xref = np.asarray([X_OUTLET, -0.55, 0.90])
            p_abs_at_min = recover_absolute_pressure(
                row["p_min_value"], P_AMBIENT, RHO, GRAVITY, row["p_min_xyz_m"], xref
            )
            p_abs_at_max = recover_absolute_pressure(
                row["p_max_value"], P_AMBIENT, RHO, GRAVITY, row["p_max_xyz_m"], xref
            )
            row["p_abs_min_at_logged_pmin_pa"] = p_abs_at_min
            row["p_abs_max_at_logged_pmax_pa"] = p_abs_at_max
        rows.append(row)
    return rows


def _write_iteration_history_csv(bundle: Path, rows: list[dict[str, Any]]) -> Path:
    import csv

    output = bundle / "analysis/steady-iteration-history.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in rows for key in row})
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, separators=(",", ":"))
                    if isinstance(value, (list, dict))
                    else value
                    for key, value in row.items()
                }
            )
    return output


def analyze_endpoint(bundle: Path, output_name: str = "analysis.json") -> dict[str, Any]:
    bundle = bundle.resolve(strict=True)
    case = bundle / "case"
    times = _numeric_times(case)
    if not times:
        raise FileNotFoundError("no native simpleFoam output time directory")
    time_name = times[-1]
    time_dir = case / time_name
    mesh = case / "constant/polyMesh"
    boundary = _read_global_boundary(mesh / "boundary")
    patch_data = {name: (count, start) for name, _, count, start in boundary}
    required = {"wetInlet", "wetOutlet"}
    if not required.issubset(patch_data):
        raise ValueError(f"missing control patches: {required - set(patch_data)}")
    offsets, labels = _read_global_faces(mesh / "faces")
    points = _read_global_points(mesh / "points")
    centers = {}
    area_vectors = {}
    for name in required:
        count, start = patch_data[name]
        patch_centers, patch_sf = [], []
        for face_id in range(start, start + count):
            sf, center, _area = _face_geometry(face_id, offsets, labels, points)
            patch_sf.append(sf)
            patch_centers.append(center)
        centers[name] = np.asarray(patch_centers)
        area_vectors[name] = np.asarray(patch_sf)

    p_path, u_path, phi_path = time_dir / "p", time_dir / "U", time_dir / "phi"
    p_internal = _parse_internal(p_path.read_bytes(), "scalar")
    u_internal = _parse_internal(u_path.read_bytes(), "vector", components=3)
    owners = _read_global_labels(mesh / "owner")
    neighbours = _read_global_labels(mesh / "neighbour")
    inlet_count, inlet_start = patch_data["wetInlet"]
    p_patch = {
        "wetInlet": p_internal[owners[inlet_start : inlet_start + inlet_count]],
        "wetOutlet": _parse_patch_scalar_values(
            p_path.read_bytes(), "wetOutlet", patch_data["wetOutlet"][0]
        ),
    }
    u_patch = {
        name: _parse_patch_vector_values(u_path.read_bytes(), name, patch_data[name][0])
        for name in required
    }
    # Read actual terminal surfaceScalarField boundary values.  U dot Sf is
    # separately reported because some velocity boundary conditions do not
    # guarantee facewise equality with the pressure-corrected phi field.
    phi_raw = phi_path.read_bytes() if phi_path.is_file() else None
    phi_patch = (
        {name: _parse_patch_scalar_values(phi_raw, name, patch_data[name][0]) for name in required}
        if phi_raw is not None
        else None
    )
    c_path = case / "constant/C"
    v_path = case / "constant/cellVolume"
    if not c_path.is_file() or not v_path.is_file():
        raise FileNotFoundError("native constant/C and checkMesh constant/cellVolume are required")
    cell_centers = _parse_internal(c_path.read_bytes(), "vector", components=3)
    cell_volumes = _parse_internal(v_path.read_bytes(), "scalar")
    if not (len(p_internal) == len(u_internal) == len(cell_centers) == len(cell_volumes)):
        raise ValueError("native internal field/mesh lengths differ")

    xref = np.asarray(
        json.loads((bundle / "preparation.json").read_text())["flow_setup"][
            "pressure_reference_xyz_m"
        ]
    )
    p_abs_cells = recover_absolute_pressure(p_internal, P_AMBIENT, RHO, GRAVITY, cell_centers, xref)
    min_id = int(np.argmin(p_abs_cells))
    p_min_abs = float(p_abs_cells[min_id])
    p_min_gauge = p_min_abs - P_AMBIENT
    near_min = p_abs_cells <= p_min_abs + 1000.0
    near_min_ids = np.flatnonzero(near_min)
    min_xyz = cell_centers[min_id]
    historical_xyz = np.asarray([4.220088, -0.380816, 0.970915])
    concave_set = mesh / "sets/concaveCells"
    concave_ids = (
        _read_global_labels(concave_set) if concave_set.is_file() else np.empty(0, dtype=np.int64)
    )
    concave_mask = np.zeros(len(p_internal), dtype=bool)
    valid_concave = concave_ids[(concave_ids >= 0) & (concave_ids < len(p_internal))]
    concave_mask[valid_concave] = True
    owners = _read_global_labels(mesh / "owner")
    neighbours = _read_global_labels(mesh / "neighbour")
    neighbor_ids: set[int] = set()
    adjacency: dict[int, set[int]] = {}
    near_ids = set(int(i) for i in near_min_ids)
    for own, nei in zip(owners[: len(neighbours)], neighbours, strict=True):
        own_i, nei_i = int(own), int(nei)
        if own_i == min_id:
            neighbor_ids.add(nei_i)
        elif nei_i == min_id:
            neighbor_ids.add(own_i)
        if own_i in near_ids and nei_i in near_ids:
            adjacency.setdefault(own_i, set()).add(nei_i)
            adjacency.setdefault(nei_i, set()).add(own_i)
    connected_near_min = {min_id}
    stack = [min_id]
    while stack:
        cell = stack.pop()
        for other in adjacency.get(cell, ()):
            if other not in connected_near_min:
                connected_near_min.add(other)
                stack.append(other)
    local_neighbors = []
    for cell in sorted(
        neighbor_ids, key=lambda i: float(np.linalg.norm(cell_centers[i] - min_xyz))
    ):
        local_neighbors.append(
            {
                "cell": cell,
                "center_xyz_m": cell_centers[cell].tolist(),
                "p_abs_pa": float(p_abs_cells[cell]),
                "p_gauge_pa": float(p_abs_cells[cell] - P_AMBIENT),
                "U_xyz_m_s": u_internal[cell].tolist(),
                "speed_m_s": float(np.linalg.norm(u_internal[cell])),
                "concaveCells_member": bool(concave_mask[cell]),
            }
        )
    metrics: dict[str, Any] = {
        "latest_steady_iteration": int(float(time_name)),
        "time_label_interpretation": "steady SIMPLE iteration label, not physical seconds",
        "native_cells": int(len(p_internal)),
        "cell_volume_sum_m3": float(cell_volumes.sum()),
        "minimum_cell": min_id,
        "p_min_absolute_pa": p_min_abs,
        "p_min_gauge_pa": p_min_gauge,
        "p_min_xyz_m": min_xyz.tolist(),
        "distance_to_historical_upper_a_pmin_m": float(np.linalg.norm(min_xyz - historical_xyz)),
        "cells_within_1kpa_of_minimum": int(len(near_min_ids)),
        "volume_within_1kpa_of_minimum_m3": float(cell_volumes[near_min].sum()),
        "near_min_concave_cell_count": int(np.count_nonzero(near_min & concave_mask)),
        "near_min_face_connected_component_cells": len(connected_near_min),
        "p_min_cell_native_face_neighbors": local_neighbors,
        "minimum_cell_in_concaveCells_set": bool(concave_mask[min_id]),
        "concaveCells_interpretation": "spatial coincidence only; not an attribution of the pressure minimum",
        "bbox_within_1kpa_of_minimum_xyz_m": [
            cell_centers[near_min].min(axis=0).tolist(),
            cell_centers[near_min].max(axis=0).tolist(),
        ],
        "low_pressure_cell_counts": {
            "p_abs_below_ambient_pa": int(np.count_nonzero(p_abs_cells < P_AMBIENT)),
            "p_abs_below_95kpa": int(np.count_nonzero(p_abs_cells < 95_000.0)),
            "p_abs_below_50kpa": int(np.count_nonzero(p_abs_cells < 50_000.0)),
            "p_abs_nonpositive": int(np.count_nonzero(p_abs_cells <= 0.0)),
        },
        "cavitation_interpretation": "not modeled; pressure is a single-phase incompressible diagnostic, not a cavitation criterion",
    }
    sections = {}
    for name, sign in (("wetInlet", -1.0), ("wetOutlet", 1.0)):
        sf = area_vectors[name]
        u = u_patch[name]
        p_solver = p_patch[name]
        phi_from_u = np.einsum("ij,ij->i", u, sf)
        phi = phi_patch[name] if phi_patch is not None else phi_from_u
        q_signed = float(phi.sum())
        q_outward = sign * q_signed
        p_abs = recover_absolute_pressure(p_solver, P_AMBIENT, RHO, GRAVITY, centers[name], xref)
        weight = np.abs(phi)
        weight_sum = float(weight.sum())
        pressure_mean = (
            float(np.dot(weight, p_abs) / weight_sum) if weight_sum > 0 else float("nan")
        )
        speed2_mean = (
            float(np.dot(weight, np.einsum("ij,ij->i", u, u)) / weight_sum)
            if weight_sum > 0
            else float("nan")
        )
        sections[name] = {
            "face_count": int(len(phi)),
            "Q_outward_m3_s": q_outward,
            "Q_signed_global_outward_m3_s": q_signed,
            "flux_weighted_absolute_static_pressure_pa": pressure_mean,
            "flux_weighted_speed_squared_m2_s2": speed2_mean,
            "flux_weighted_total_pressure_pa": pressure_mean + 0.5 * RHO * speed2_mean,
            "native_phi_sum_m3_s": q_signed,
            "max_abs_native_phi_minus_UdotSf_m3_s": float(np.max(np.abs(phi - phi_from_u))),
            "sum_UdotSf_m3_s": float(phi_from_u.sum()),
            "native_phi_minus_UdotSf_sum_m3_s": float(phi.sum() - phi_from_u.sum()),
            "phi_source": "terminal native surfaceScalarField boundary values"
            if phi_patch is not None
            else "U boundary dot native face-area vector fallback",
            "UdotSf_interpretation": "independent boundary-velocity estimate; not required to equal pressure-corrected native phi facewise",
        }
    qin, qout = sections["wetInlet"]["Q_outward_m3_s"], sections["wetOutlet"]["Q_outward_m3_s"]
    head_pa = (
        sections["wetInlet"]["flux_weighted_total_pressure_pa"]
        - sections["wetOutlet"]["flux_weighted_total_pressure_pa"]
    )
    metrics["sections"] = sections
    metrics["conservation"] = {
        "Q_target_m3_s": Q_TARGET,
        "Q_in_m3_s": qin,
        "Q_out_m3_s": qout,
        "relative_Q_imbalance": abs(qin - qout) / max(abs(qin), abs(qout), 1e-30),
        "inlet_relative_to_target": (qin - Q_TARGET) / Q_TARGET,
    }
    metrics["required_head"] = {
        "inlet_minus_outlet_flux_weighted_total_pressure_pa": head_pa,
        "equivalent_water_head_m": head_pa / (RHO * 9.81),
        "interpretation": "single-phase steady hydraulic head at prescribed Q; not a valve/tank discharge prediction",
    }
    metrics["native_hashes"] = {
        str(path.relative_to(bundle)): sha256_file(path)
        for path in (
            p_path,
            u_path,
            *([phi_path] if phi_path.is_file() else []),
            c_path,
            v_path,
            mesh / "points",
            mesh / "faces",
            mesh / "owner",
            mesh / "neighbour",
            *([concave_set] if concave_set.is_file() else []),
        )
    }
    metrics["linear_convergence"] = _parse_simplefoam_residuals(case / "log.simpleFoam")
    metrics["function_object_fluxes"] = _parse_logged_surface_fluxes(case / "log.simpleFoam")
    metrics["endpoint_status"] = (
        json.loads((bundle / "terminal.json").read_text())
        if (bundle / "terminal.json").exists()
        else None
    )
    log_path = case / "log.simpleFoam"
    history = _parse_simplefoam_iteration_history(log_path)
    history_path = _write_iteration_history_csv(bundle, history)
    log_text = log_path.read_text(errors="replace") if log_path.is_file() else ""
    control_text = (case / "system/controlDict").read_text(encoding="utf-8")
    end_time_match = re.search(r"(?m)^endTime\s+([-+0-9.eE]+)\s*;", control_text)
    end_time = float(end_time_match.group(1)) if end_time_match else None
    history_record = {
        "rows": len(history),
        "csv": str(history_path.relative_to(bundle)),
        "csv_sha256": sha256_file(history_path),
        "first_runaway_threshold_crossing": _first_runaway_threshold_crossing(history),
        "steady_converged_message_present": bool(
            re.search(r"(?i)SIMPLE solution converged", log_text)
        ),
        "normal_End": "End" in log_text.splitlines(),
        "end_time_label": end_time,
        "reached_iteration_cap": bool(history)
        and end_time is not None
        and history[-1]["steady_iteration"] >= end_time,
        "interpretation": "steady SIMPLE pseudo-time labels are iteration counts, not physical seconds",
    }
    metrics["iteration_history"] = history_record
    first_crossing = history_record["first_runaway_threshold_crossing"]
    if first_crossing is not None:
        metrics["numerical_outcome"] = {
            "classification": "divergent_nonphysical_endpoint",
            "first_declared_runaway_threshold_crossing": first_crossing,
            "hydraulic_interpretation": "invalid; do not interpret raw p_abs extrema, total head, or outlet flow as a hydraulic result",
        }
    elif history_record["steady_converged_message_present"]:
        metrics["numerical_outcome"] = {
            "classification": "simplefoam_residual_control_converged",
            "first_declared_runaway_threshold_crossing": None,
            "hydraulic_interpretation": "numerical convergence only; physical model remains exploratory",
        }
    else:
        metrics["numerical_outcome"] = {
            "classification": "iteration_cap_or_external_stop_without_convergence_message",
            "first_declared_runaway_threshold_crossing": None,
            "hydraulic_interpretation": "unsettled; do not interpret raw pressure minimum or required head as converged hydraulic results",
        }
    metrics["raw_endpoint_metrics_qualification"] = (
        "Raw native-field values are retained for audit. They are not engineering estimates when the numerical outcome is divergent or unsettled."
    )
    if metrics["numerical_outcome"]["classification"] == "divergent_nonphysical_endpoint":
        figure_path, slice_metadata = render_divergent_endpoint_magnitudes(
            bundle, cell_centers, u_internal, p_abs_cells, min_id
        )
    else:
        figure_stem = Path(output_name).stem
        filename = (
            "endpoint-pressure-velocity.png"
            if output_name == "analysis.json"
            else f"endpoint-pressure-velocity-{figure_stem}.png"
        )
        figure_path, slice_metadata = render_endpoint_pressure_velocity(
            bundle, cell_centers, u_internal, p_abs_cells, min_id, concave_mask, filename
        )
    metrics["native_pressure_velocity_plot"] = str(figure_path.relative_to(bundle))
    metrics["native_pressure_velocity_slice"] = slice_metadata
    history_figure = render_steady_history(bundle, history)
    metrics["steady_iteration_history_plot"] = str(history_figure.relative_to(bundle))
    metrics["created_utc"] = utc_now()
    atomic_json(bundle / output_name, metrics)
    return metrics


def _first_runaway_threshold_crossing(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        speed = row.get("U_mag_max_value")
        p_min_abs = row.get("p_abs_min_at_logged_pmin_pa")
        p_max_abs = row.get("p_abs_max_at_logged_pmax_pa")
        if speed is not None and speed > 200.0:
            return {
                "steady_iteration": row["steady_iteration"],
                "criterion": "max_magnitude_U_m_s > 200",
                "observed": speed,
                "location_xyz_m": row.get("U_mag_max_xyz_m"),
            }
        if p_min_abs is not None and p_min_abs < -100_000_000.0:
            return {
                "steady_iteration": row["steady_iteration"],
                "criterion": "minimum_recovered_absolute_pressure_pa < -100000000",
                "observed": p_min_abs,
                "location_xyz_m": row.get("p_min_xyz_m"),
            }
        if p_max_abs is not None and p_max_abs > 100_000_000.0:
            return {
                "steady_iteration": row["steady_iteration"],
                "criterion": "maximum_recovered_absolute_pressure_pa > 100000000",
                "observed": p_max_abs,
                "location_xyz_m": row.get("p_max_xyz_m"),
            }
    return None


def render_steady_history(bundle: Path, rows: list[dict[str, Any]]) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not rows:
        raise ValueError("cannot render an empty steady iteration history")
    iterations = np.asarray([row["steady_iteration"] for row in rows], dtype=np.float64)
    max_u = np.asarray([row.get("U_mag_max_value", np.nan) for row in rows], dtype=np.float64)
    qout = np.asarray([row.get("wetOutlet_Q_m3_s", np.nan) for row in rows], dtype=np.float64)
    pmin = np.asarray([row.get("p_abs_min_at_logged_pmin_pa", np.nan) for row in rows])
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), constrained_layout=True, sharex=True)
    axes[0].semilogy(iterations, np.maximum(max_u, 1e-16), color="firebrick")
    axes[0].axhline(200, color="black", linestyle="--", linewidth=0.8, label="runaway limit")
    axes[0].set_ylabel("max |U| (m/s)")
    axes[0].legend(loc="best")
    axes[1].plot(iterations, qout, color="navy", label="outlet native phi")
    axes[1].axhline(Q_TARGET, color="black", linestyle="--", linewidth=0.8, label="fixed inlet Q")
    axes[1].set_ylabel("section Q (m³/s)")
    axes[1].legend(loc="best")
    axes[2].plot(iterations, pmin / 100_000.0, color="purple")
    axes[2].axhline(-1000, color="black", linestyle="--", linewidth=0.8, label="−100 MPa limit")
    axes[2].set_ylabel("min p_abs / 100 kPa")
    axes[2].set_xlabel("steady SIMPLE iteration (not physical time)")
    axes[2].legend(loc="best")
    for axis in axes:
        axis.grid(True, alpha=0.2)
    path = bundle / "figures/steady-divergence-history.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path


def _parse_logged_surface_fluxes(log_path: Path) -> dict[str, Any]:
    if not log_path.is_file():
        return {"log_present": False, "last_m3_s": {}}
    text = log_path.read_text(errors="replace")
    last: dict[str, float] = {}
    for patch in ("wetInlet", "wetOutlet"):
        rows = re.findall(rf"(?m)^\s*sum\({re.escape(patch)}\) of phi =\s*([-+0-9.eE]+)", text)
        if rows:
            last[patch] = float(rows[-1])
    return {
        "log_present": True,
        "source": "OpenFOAM surfaceFieldValue log records",
        "last_m3_s": last,
    }


def render_endpoint_pressure_velocity(
    bundle: Path,
    cell_centers: np.ndarray,
    velocity: np.ndarray,
    p_absolute: np.ndarray,
    min_cell: int,
    concave_mask: np.ndarray,
    filename: str = "endpoint-pressure-velocity.png",
) -> tuple[Path, dict[str, Any]]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    center_y = -0.55
    half_width = 0.06
    band = np.abs(cell_centers[:, 1] - center_y) <= half_width
    ids = np.flatnonzero(band)
    if len(ids) < 20:
        raise ValueError(f"native y-band contains too few cells for a slice plot: {len(ids)}")
    x, z = cell_centers[ids, 0], cell_centers[ids, 2]
    p_gauge_kpa = (p_absolute[ids] - P_AMBIENT) / 1000.0
    speed = np.linalg.norm(velocity[ids], axis=1)
    pmin_xyz = cell_centers[min_cell]

    # One representative native center per x-z display bin keeps vectors legible;
    # the background remains un-interpolated cell-center samples.
    bins: dict[tuple[int, int], int] = {}
    for cell in ids:
        key = (
            int(math.floor(cell_centers[cell, 0] / 0.08)),
            int(math.floor(cell_centers[cell, 2] / 0.06)),
        )
        prior = bins.get(key)
        if prior is None or np.linalg.norm(velocity[cell]) > np.linalg.norm(velocity[prior]):
            bins[key] = int(cell)
    vector_ids = np.asarray(sorted(bins.values()), dtype=np.int64)

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True, sharex=True)
    scatter = axes[0].scatter(x, z, c=p_gauge_kpa, s=7, cmap="coolwarm", linewidths=0)
    axes[0].scatter(
        [pmin_xyz[0]],
        [pmin_xyz[2]],
        marker="*",
        s=130,
        color="black",
        edgecolor="white",
        linewidth=0.7,
        label=f"native pmin cell {min_cell}"
        + (" (concaveCells)" if concave_mask[min_cell] else ""),
    )
    axes[0].set_ylabel("z (m)")
    axes[0].set_title(f"Native cell-center pressure, |y + 0.55| ≤ {half_width:g} m")
    axes[0].legend(loc="best", fontsize=8)
    fig.colorbar(scatter, ax=axes[0], label="recovered absolute-pressure gauge (kPa)")

    axes[1].scatter(x, z, c=speed, s=7, cmap="viridis", linewidths=0)
    axes[1].quiver(
        cell_centers[vector_ids, 0],
        cell_centers[vector_ids, 2],
        velocity[vector_ids, 0],
        velocity[vector_ids, 2],
        angles="xy",
        scale_units="xy",
        scale=160,
        width=0.002,
        color="black",
    )
    axes[1].scatter(
        [pmin_xyz[0]],
        [pmin_xyz[2]],
        marker="*",
        s=110,
        color="red",
        edgecolor="white",
        linewidth=0.7,
    )
    axes[1].set_xlabel("x (m)")
    axes[1].set_ylabel("z (m)")
    axes[1].set_title("Native speed samples and projected (Ux, Uz) vectors")
    fig.suptitle("Wet A_upper steady single-phase reference — native points, no interpolation")
    for ax in axes:
        ax.grid(True, alpha=0.18)
        ax.set_xlim(2.20, 4.85)
    out = bundle / "figures" / filename
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out, {
        "method": "native cell-center scatter, no spatial interpolation",
        "band_center_y_m": center_y,
        "band_half_width_m": half_width,
        "native_cells_in_band": int(len(ids)),
        "quiver_representative_bins": int(len(vector_ids)),
        "velocity_vectors": "Ux and Uz; plotted arrows scaled by a fixed display factor 160",
        "pressure_values": "recovered absolute pressure minus 100 kPa ambient, in kPa",
    }


def render_divergent_endpoint_magnitudes(
    bundle: Path,
    cell_centers: np.ndarray,
    velocity: np.ndarray,
    p_absolute: np.ndarray,
    min_cell: int,
) -> tuple[Path, dict[str, Any]]:
    """Render native points for diagnosis only when the endpoint is divergent."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    center_y, half_width = -0.55, 0.06
    mask = np.abs(cell_centers[:, 1] - center_y) <= half_width
    ids = np.flatnonzero(mask)
    xyz = cell_centers[ids]
    speed = np.linalg.norm(velocity[ids], axis=1)
    pressure_deviation = np.abs(p_absolute[ids] - P_AMBIENT)
    log_pressure = np.log10(np.maximum(pressure_deviation, 1e-12))
    log_speed = np.log10(np.maximum(speed, 1e-12))
    bins: dict[tuple[int, int], int] = {}
    for cell in ids:
        key = (
            int(math.floor(cell_centers[cell, 0] / 0.08)),
            int(math.floor(cell_centers[cell, 2] / 0.06)),
        )
        prior = bins.get(key)
        if prior is None or np.linalg.norm(velocity[cell]) > np.linalg.norm(velocity[prior]):
            bins[key] = int(cell)
    vector_ids = np.asarray(sorted(bins.values()), dtype=np.int64)
    directions = velocity[vector_ids].copy()
    norms = np.linalg.norm(directions, axis=1)
    nonzero = norms > 0
    directions[nonzero] /= norms[nonzero, None]
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True, sharex=True)
    p_scatter = axes[0].scatter(xyz[:, 0], xyz[:, 2], c=log_pressure, s=7, cmap="magma")
    axes[0].scatter(
        [cell_centers[min_cell, 0]],
        [cell_centers[min_cell, 2]],
        marker="*",
        s=130,
        color="cyan",
        edgecolor="black",
        linewidth=0.6,
        label=f"raw p_abs minimum cell {min_cell}",
    )
    axes[0].set_ylabel("z (m)")
    axes[0].set_title("DIVERGENT endpoint: log10 |p_abs − ambient| (Pa), native cell centers")
    axes[0].legend(loc="best", fontsize=8)
    fig.colorbar(p_scatter, ax=axes[0], label="log10 pressure deviation (Pa)")
    u_scatter = axes[1].scatter(xyz[:, 0], xyz[:, 2], c=log_speed, s=7, cmap="viridis")
    axes[1].quiver(
        cell_centers[vector_ids, 0],
        cell_centers[vector_ids, 2],
        directions[:, 0],
        directions[:, 2],
        angles="xy",
        scale_units="xy",
        scale=28,
        width=0.002,
        color="black",
    )
    axes[1].scatter(
        [cell_centers[min_cell, 0]],
        [cell_centers[min_cell, 2]],
        marker="*",
        s=110,
        color="red",
        edgecolor="white",
        linewidth=0.7,
    )
    axes[1].set(
        xlabel="x (m)", ylabel="z (m)", title="log10 speed (m/s) and normalized (Ux, Uz) direction"
    )
    fig.colorbar(u_scatter, ax=axes[1], label="log10 speed (m/s)")
    for ax in axes:
        ax.set_xlim(2.2, 4.85)
        ax.grid(True, alpha=0.18)
    path = bundle / "figures/divergent-endpoint-log-field-map.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path, {
        "method": "native cell-center scatter in y band; logarithmic absolute magnitudes; no interpolation",
        "band_center_y_m": center_y,
        "band_half_width_m": half_width,
        "native_cells_in_band": int(len(ids)),
        "vectors": "normalized directions at one representative native cell per x-z bin",
        "qualification": "visualization is only a map of a numerically divergent endpoint; colors are magnitude diagnostics, not physical pressure or speed ranges",
    }


def _numeric_times(case: Path) -> list[str]:
    entries = []
    for path in case.iterdir():
        if not path.is_dir():
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        if math.isfinite(value):
            entries.append((value, path.name))
    return [name for _, name in sorted(entries)]


def render_geometry(bundle: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    stl = (bundle / "case" / BRANCH_STL).read_bytes()
    vertices = np.asarray(
        [
            [float(v) for v in match.groups()]
            for match in re.finditer(
                rb"\bvertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", stl
            )
        ]
    )
    if vertices.size == 0 or vertices.size % 9:
        raise ValueError("branch STL is not an ASCII triangle mesh")
    triangles = vertices.reshape((-1, 3, 3))
    triangles = triangles[np.mean(triangles[:, :, 0], axis=1) >= X_INLET - 0.05]
    mesh = bundle / "case/constant/polyMesh"
    points = _read_global_points(mesh / "points")
    offsets, labels = _read_global_faces(mesh / "faces")
    boundary = _read_global_boundary(mesh / "boundary")
    patch_lookup = {name: (n, start) for name, _, n, start in boundary}

    figure = plt.figure(figsize=(11, 5), constrained_layout=True)
    ax = figure.add_subplot(1, 2, 1, projection="3d")
    ax.add_collection3d(
        Poly3DCollection(
            triangles, facecolor="#59a6cf", edgecolor="#31566b", linewidth=0.08, alpha=0.42
        )
    )
    for x, color, label in (
        (X_INLET, "#dd7b1c", "seat section x=2.25 m"),
        (X_OUTLET, "#2c8b52", "mouth section x=4.8 m"),
    ):
        ax.plot([x, x], [-1.1, 0], [0.30, 1.35], color=color, linewidth=2, label=label)
    ax.scatter(
        [4.220088], [-0.380816], [0.970915], color="red", s=24, label="historical upper-A pmin"
    )
    ax.set(xlabel="x (m)", ylabel="y (m)", zlabel="z (m)", title="A_upper native branch shell")
    ax.set_xlim(X_INLET - 0.1, X_OUTLET + 0.1)
    ax.set_ylim(-1.1, 0.0)
    ax.set_zlim(0.3, 1.35)
    ax.legend(loc="upper left", fontsize=7)
    ax2 = figure.add_subplot(1, 2, 2)
    for name, color in (("wetInlet", "#dd7b1c"), ("wetOutlet", "#2c8b52")):
        count, start = patch_lookup[name]
        for face_id in range(start, start + count):
            polygon = points[labels[offsets[face_id] : offsets[face_id + 1]]]
            closed = np.vstack([polygon[:, 1:3], polygon[0, 1:3]])
            ax2.plot(closed[:, 0], closed[:, 1], color=color, linewidth=0.55)
    ax2.set_aspect("equal", adjustable="datalim")
    ax2.set(xlabel="y (m)", ylabel="z (m)", title="Native sections: inlet orange, outlet green")
    ax2.grid(True, alpha=0.2)
    output = bundle / "figures/wet-branch-geometry.png"
    figure.savefig(output, dpi=180)
    plt.close(figure)
    return output


def _docker_inspect(container_id: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "inspect", container_id], capture_output=True, text=True, check=True, timeout=30
    )
    return json.loads(result.stdout)[0]


def _pause_path(bundle: Path) -> Path | None:
    for path in (RUNS / "PAUSE", bundle / "PAUSE", bundle / "case/PAUSE"):
        if path.exists():
            return path
    return None


def launch_guarded(bundle: Path) -> str:
    bundle = bundle.resolve(strict=True)
    verify_freeze(bundle)
    if _pause_path(bundle):
        raise RuntimeError(f"PAUSE present: {_pause_path(bundle)}")
    if shutil.disk_usage(ROOT).free < 16 * 1024**3 + OUTPUT_CAP:
        raise RuntimeError("free disk is below the declared 16 GiB reserve plus output cap")
    unit = "i4f-wet-" + bundle.name.rsplit("-", 1)[-1].lower()
    cmd = [
        "systemd-run",
        "--user",
        "--unit",
        unit,
        "--collect",
        "--no-block",
        sys.executable,
        str(ROOT / "scripts/run_local.py"),
        "--threads",
        "1",
        "--timeout",
        str(MAX_WALL_S + 120),
        "--",
        "nice",
        "-n",
        "19",
        str(ROOT / ".venv/bin/python"),
        str(Path(__file__).resolve()),
        "_supervise",
        "--bundle",
        str(bundle),
    ]
    process = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if process.returncode:
        raise RuntimeError(f"systemd-run failed: {process.stderr[-2000:]}")
    return unit


def _atomic_go(bundle: Path, identity: dict[str, Any]) -> None:
    atomic_json(bundle / "GO", identity)


def _supervise(bundle: Path) -> None:
    bundle = bundle.resolve(strict=True)
    verify_freeze(bundle)
    if (bundle / "GO").exists():
        raise FileExistsError("GO already exists")
    if _pause_path(bundle):
        raise RuntimeError(f"PAUSE present before create: {_pause_path(bundle)}")
    case = bundle / "case"
    name = bundle.name.lower()
    create = [
        "docker",
        "create",
        "--name",
        name,
        "--cpus=0.75",
        "--memory=4g",
        "--log-driver=none",
        "-v",
        f"{case}:/case",
        "-v",
        f"{bundle}:/bundle",
        "-v",
        f"{RUNS}:/global-runs:ro",
        "-w",
        "/case",
        IMAGE,
        "bash",
        "/bundle/scripts/run_solver.sh",
    ]
    created = subprocess.run(create, capture_output=True, text=True, check=True, timeout=60)
    cid = created.stdout.strip()
    subprocess.run(["docker", "start", cid], capture_output=True, text=True, check=True, timeout=60)
    inspected = _docker_inspect(cid)
    started_at = inspected["State"]["StartedAt"]
    config = inspected["HostConfig"]
    image_data = subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True, text=True, check=True
    )
    image_id = json.loads(image_data.stdout)[0]["Id"]
    if (
        not inspected["State"]["Running"]
        or config["NanoCpus"] != 750_000_000
        or config["LogConfig"]["Type"] != "none"
        or inspected["Image"] != image_id
    ):
        stopped = subprocess.run(
            ["docker", "stop", "--time", "1", cid], capture_output=True, text=True, check=False
        )
        _event(
            bundle,
            {
                "event": "pre_go_identity_failure",
                "utc": utc_now(),
                "container_id": cid,
                "started_at": started_at,
                "stop_returncode": stopped.returncode,
            },
        )
        raise RuntimeError("Docker identity/quota/log-driver/image preflight failed")
    manifest = {
        "schema": "i4f-wet-branch-launch/v1",
        "container_id": cid,
        "container_name": name,
        "started_at": started_at,
        "image_reference": IMAGE,
        "image_id": image_id,
        "docker_nano_cpus": config["NanoCpus"],
        "docker_memory_bytes": config["Memory"],
        "docker_log_driver": config["LogConfig"]["Type"],
        "solver": "stock serial simpleFoam",
        "input_freeze_sha256": sha256_file(bundle / "input-freeze.json"),
        "created_utc": utc_now(),
        "controller_source_sha256": sha256_file(Path(__file__).resolve()),
        "solver_wrapper_sha256": sha256_file(bundle / "scripts/run_solver.sh"),
        "hard_wall_seconds": MAX_WALL_S,
        "graceful_write_seconds": SAVE_WALL_S,
    }
    atomic_json(bundle / "launch-manifest.json", manifest)
    if _pause_path(bundle):
        stopped = subprocess.run(
            ["docker", "stop", "--time", "1", cid], capture_output=True, text=True, check=False
        )
        _event(
            bundle,
            {
                "event": "pause_before_go",
                "utc": utc_now(),
                "container_id": cid,
                "started_at": started_at,
                "pause_path": str(_pause_path(bundle)),
                "stop_returncode": stopped.returncode,
            },
        )
        raise RuntimeError(f"PAUSE appeared after create and before GO: {_pause_path(bundle)}")
    _atomic_go(
        bundle,
        {
            "container_id": cid,
            "started_at": started_at,
            "launch_manifest_sha256": sha256_file(bundle / "launch-manifest.json"),
            "released_utc": utc_now(),
        },
    )
    _event(bundle, {"event": "GO", "container_id": cid, "started_at": started_at, "utc": utc_now()})
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
    requested_save = False
    final = None
    while time.time() - started < MAX_WALL_S:
        state = _docker_inspect(cid)
        if state["Id"] != cid or state["State"]["StartedAt"] != started_at:
            raise RuntimeError("Docker ID/StartedAt changed under guard")
        if not state["State"]["Running"]:
            final = state
            break
        elapsed = time.time() - started
        pause = _pause_path(bundle)
        output_bytes = sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file())
        low_disk = shutil.disk_usage(ROOT).free < 16 * 1024**3
        if (
            elapsed >= SAVE_WALL_S or pause is not None or low_disk or output_bytes >= OUTPUT_CAP
        ) and not requested_save:
            command = [
                "docker",
                "exec",
                cid,
                "bash",
                "--noprofile",
                "--norc",
                "-c",
                ". /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1; cd /case; foamDictionary system/controlDict -entry stopAt -set writeNow",
            ]
            save = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
            _event(
                bundle,
                {
                    "event": "writeNow_request",
                    "utc": utc_now(),
                    "elapsed_s": elapsed,
                    "pause_path": str(pause) if pause else None,
                    "low_disk": low_disk,
                    "output_bytes": output_bytes,
                    "returncode": save.returncode,
                    "stderr": save.stderr[-1000:],
                },
            )
            requested_save = save.returncode == 0
        atomic_json(
            bundle / "controller-status.json",
            {
                "status": "running",
                "container_id": cid,
                "started_at": started_at,
                "elapsed_wall_s": time.time() - started,
                "latest_native_times": _numeric_times(case),
                "writeNow_requested": requested_save,
                "updated_utc": utc_now(),
            },
        )
        time.sleep(5)
    if final is None:
        stopped = subprocess.run(
            ["docker", "stop", "--time", "30", cid],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        _event(
            bundle,
            {"event": "hard_deadline_stop", "utc": utc_now(), "returncode": stopped.returncode},
        )
        final = _docker_inspect(cid)
    log = case / "log.simpleFoam"
    log_text = log.read_text(errors="replace") if log.exists() else ""
    record = {
        "schema": "i4f-wet-branch-terminal/v1",
        "captured_utc": utc_now(),
        "container_id": cid,
        "started_at": started_at,
        "docker_state": final["State"],
        "exit_code": final["State"].get("ExitCode"),
        "normal_solver_End": "End" in log_text.splitlines(),
        "solver_log_bytes": log.stat().st_size if log.exists() else None,
        "solver_log_sha256": sha256_file(log) if log.exists() else None,
        "latest_native_times": _numeric_times(case),
        "bundle_bytes": sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file()),
    }
    atomic_json(bundle / "terminal.json", record)
    _event(bundle, {"event": "terminal", **record})


def _event(bundle: Path, value: dict[str, Any]) -> None:
    with (bundle / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--mesh", action="store_true")
    mesh = commands.add_parser("mesh")
    mesh.add_argument("--bundle", type=Path, required=True)
    launch = commands.add_parser("launch")
    launch.add_argument("--bundle", type=Path, required=True)
    supervise = commands.add_parser("_supervise")
    supervise.add_argument("--bundle", type=Path, required=True)
    status = commands.add_parser("status")
    status.add_argument("--bundle", type=Path, required=True)
    analyze = commands.add_parser("analyze")
    analyze.add_argument("--bundle", type=Path, required=True)
    analyze.add_argument("--output", default="analysis.json")
    clone = commands.add_parser("clone-upwind")
    clone.add_argument("--parent-bundle", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        bundle = create_bundle()
        print(bundle)
        if args.mesh:
            run_mesh_preparation(bundle)
    elif args.command == "mesh":
        run_mesh_preparation(args.bundle)
    elif args.command == "launch":
        print(launch_guarded(args.bundle))
    elif args.command == "_supervise":
        _supervise(args.bundle)
    elif args.command == "status":
        for name in (
            "preparation.json",
            "mesh-preparation.json",
            "input-freeze.json",
            "launch-manifest.json",
            "controller-status.json",
            "terminal.json",
        ):
            path = args.bundle / name
            if path.exists():
                print(f"## {name}\n{path.read_text(encoding='utf-8')}")
    elif args.command == "analyze":
        print(json.dumps(analyze_endpoint(args.bundle, args.output), indent=2, sort_keys=True))
    elif args.command == "clone-upwind":
        print(clone_upwind_trial(args.parent_bundle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
