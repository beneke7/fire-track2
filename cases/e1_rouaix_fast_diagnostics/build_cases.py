"""Build matched all-air Rouaix diagnostics on a coarse full-domain mesh.

Exploratory only: this is a source-control diagnostic, not an E1 reproduction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_CASE = ROOT / "cases/e1_rouaix_case1_static/case"
MESH_CONTROL_DICT = ROOT / "cases/e1_rouaix_matched_mesh/case/system/controlDict"
HPC_TEMPLATE = ROOT / "cases/e1_rouaix_hpc/template/system"
MESH_HELPER = ROOT / "scripts/run_rouaix_case4_pilot.py"
IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
PATCHES = (
    "nozzle",
    "gasInlet",
    "aircraftWall",
    "downstreamOutlet",
    "bottomOutlet",
    "spanwiseMinus",
    "spanwisePlus",
)
FLUX_PATCHES = (
    "nozzle",
    "gasInlet",
    "aircraftWall",
    "downstreamOutlet",
    "bottomOutlet",
    "spanwiseMinus",
    "spanwisePlus",
)
X_NODES = (-2.5, -0.5, 0.5, 4.5, 15.5, 17.5)
X_COUNTS = (4, 20, 18, 10, 13)
Y_NODES = (-10.0, -4.0, -1.0, 0.0)
Y_COUNTS = (5, 7, 20)
Z_CELLS = 144
BASE_CELLS = sum(X_COUNTS) * sum(Y_COUNTS) * Z_CELLS  # 299,520
MAX_CELLS = 300_000
DELTA_T_S = 0.0001
FULL_HORIZON_S = 0.5
PILOT_HORIZON_S = 0.01
MAX_U_M_S = 1000.0
PROBES_M = (
    (1.138268156425, -1.959313183228, 0.8945972226264),
    (17.44413407821, -0.05631406956444, 3.486170872067),
)
VARIANTS = {"original": "limitedLinearV 1", "upwind": "upwind"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hashes(root: Path, *, exclude: tuple[str, ...] = ()) -> dict[str, str]:
    excluded = set(exclude)
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).as_posix() not in excluded
    }


def _header(name: str) -> str:
    return (
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n"
        f"    class dictionary;\n    object {name};\n}}\n\n"
    )


def mesh_block_dict() -> str:
    """Reuse the project's piecewise trapezoid generator with frozen coarse counts."""
    sys.path.insert(0, str(ROOT))
    from scripts import run_rouaix_case4_pilot as helper

    saved = (helper.X_NODES, helper.X_COUNTS, helper.Y_NODES, helper.Y_COUNTS, helper.Z_CELLS)
    try:
        helper.X_NODES, helper.X_COUNTS = X_NODES, X_COUNTS
        helper.Y_NODES, helper.Y_COUNTS = Y_NODES, Y_COUNTS
        helper.Z_CELLS = Z_CELLS
        return helper._block_mesh_dict()
    finally:
        helper.X_NODES, helper.X_COUNTS, helper.Y_NODES, helper.Y_COUNTS, helper.Z_CELLS = saved


def snappy_dict() -> str:
    return (
        _header("snappyHexMeshDict")
        + f"""castellatedMesh false;
snap false;
addLayers false;
geometry
{{
    nozzleExitRegion
    {{
        type searchableCylinder;
        point1 (0 0 0);
        point2 (0 -0.35 0);
        radius 0.32;
    }}
}}
castellatedMeshControls
{{
    maxLocalCells 150000;
    maxGlobalCells {MAX_CELLS};
    minRefinementCells 0;
    maxLoadUnbalance 0.1;
    nCellsBetweenLevels 2;
    features ();
    refinementSurfaces {{}};
    resolveFeatureAngle 30;
    refinementRegions
    {{
        nozzleExitRegion {{ mode inside; levels ((1e15 1)); }}
    }}
    locationInMesh (1 -2 0.25);
    allowFreeStandingZoneFaces true;
}}
snapControls {{ nSmoothPatch 3; tolerance 2; nSolveIter 30; nRelaxIter 5; }}
addLayersControls
{{
    relativeSizes true;
    layers {{}};
    expansionRatio 1.0;
    finalLayerThickness 0.3;
    minThickness 0.1;
    nGrow 0;
    featureAngle 60;
    slipFeatureAngle 30;
    nRelaxIter 3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 0;
}}
meshQualityControls
{{
    maxNonOrtho 65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave 80;
    minVol 1e-13;
    minTetQuality 1e-15;
    minArea -1;
    minTwist 0.02;
    minDeterminant 0.001;
    minFaceWeight 0.05;
    minVolRatio 0.01;
    minTriangleTwist -1;
    nSmoothScale 4;
    errorReduction 0.75;
}}
debug 0;
writeFlags (scalarLevels);
mergeTolerance 1e-6;
"""
    )


def write_mesh_input(destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    system = destination / "system"
    system.mkdir()
    (destination / "constant").mkdir()
    shutil.copy2(MESH_CONTROL_DICT, system / "controlDict")
    (system / "blockMeshDict").write_text(mesh_block_dict(), encoding="utf-8")
    (system / "snappyHexMeshDict").write_text(snappy_dict(), encoding="utf-8")
    for name in ("fvSchemes", "fvSolution"):
        shutil.copy2(HPC_TEMPLATE / name, system / name)
    for name in ("topoSetDict", "createPatchDict"):
        shutil.copy2(SOURCE_CASE / "system" / name, system / name)
    metadata = {
        "schema_version": 1,
        "purpose": "Exploratory all-air negative control on a coarse full-domain trapezoidal mesh.",
        "coordinate_frame": {"x": "crossflow +", "y": "upward +", "z": "spanwise +"},
        "domain_m": {
            "x": [-2.5, 17.5],
            "y": [-10.0, 0.0],
            "spanwise_half_width_m": {"bottom": 8.0, "roof": 3.5},
        },
        "structured_base_mesh": {
            "x_nodes_m": list(X_NODES),
            "x_cells_by_band": list(X_COUNTS),
            "y_nodes_m": list(Y_NODES),
            "y_cells_by_band": list(Y_COUNTS),
            "spanwise_cells": Z_CELLS,
            "cells": BASE_CELLS,
        },
        "local_refinement": {
            "shape": "vertical cylinder centered on nozzle",
            "radius_m": 0.32,
            "depth_m": 0.35,
            "level": 1,
            "applied": False,
            "reason": "omitted from the pilot mesh after the level-1 mesh failed native determinant/concavity checks",
            "nominal_near_nozzle_base_spacing_m": [1.0 / 20.0, 0.05, 7.0 / 144.0],
            "nominal_refined_spacing_m": None,
            "maximum_cells": MAX_CELLS,
        },
        "nozzle_radius_m": 0.2,
        "patches_after_createPatch": list(PATCHES),
        "native_checks": [
            "checkMesh -allTopology -allGeometry",
            "patch inventory",
            "nozzle area and +y normal",
        ],
        "template_sha256": {
            "topoSetDict": sha256(SOURCE_CASE / "system/topoSetDict"),
            "createPatchDict": sha256(SOURCE_CASE / "system/createPatchDict"),
            "mesh_helper": sha256(MESH_HELPER),
            "mesh_control_dict": sha256(MESH_CONTROL_DICT),
            "hpc_fvSchemes": sha256(HPC_TEMPLATE / "fvSchemes"),
            "hpc_fvSolution": sha256(HPC_TEMPLATE / "fvSolution"),
        },
    }
    metadata["generated_files_sha256"] = tree_hashes(destination)
    (destination / "mesh-input.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def _control_dict(horizon_s: float) -> str:
    write_interval_s = min(0.25, horizon_s)
    if abs(round(horizon_s / write_interval_s) * write_interval_s - horizon_s) > 1e-10:
        write_interval_s = horizon_s
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
        for patch in FLUX_PATCHES
    )
    probes = "\n".join(f"            ({x:.12g} {y:.12g} {z:.12g})" for x, y, z in PROBES_M)
    return (
        _header("controlDict")
        + f"""application interIsoFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {horizon_s:.12g};
deltaT {DELTA_T_S:.12g};
adjustTimeStep no;
maxCo 5;
maxAlphaCo 5;
maxDeltaT {DELTA_T_S:.12g};
writeControl runTime;
writeInterval {write_interval_s:.12g};
purgeWrite 0;
writeFormat binary;
writePrecision 12;
writeCompression off;
timeFormat fixed;
timePrecision 12;
runTimeModifiable false;
OptimisationSwitches {{ writeNowSignal 10; stopAtWriteNowSignal 12; }}
functions
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
        location true;
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
        location true;
        log true;
        writePrecision 12;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}
    pressureAndTurbulenceExtrema
    {{
        type fieldMinMax;
        libs (fieldFunctionObjects);
        fields (p_rgh k epsilon nut);
        location true;
        log true;
        writePrecision 12;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}
    fixedProbes
    {{
        type probes;
        libs (sampling);
        fields (U alpha.water p_rgh k epsilon nut);
        probeLocations
        (
{probes}
        );
        interpolationScheme cellPoint;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}
}}
"""
    )


def _decompose_dict(ranks: int) -> str:
    if ranks not in (4, 8):
        raise ValueError("this diagnostic supports four or eight MPI ranks")
    decomposition = "2 2 1" if ranks == 4 else "2 2 2"
    return (
        _header("decomposeParDict")
        + f"""numberOfSubdomains {ranks};
method hierarchical;
hierarchicalCoeffs {{ n ({decomposition}); delta 0.001; order xyz; }}
distributed no;
roots ();
"""
    )


def _set_variant(path: Path, variant: str) -> None:
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    text = (HPC_TEMPLATE / "fvSchemes").read_text(encoding="utf-8")
    pattern = re.compile(r"(?m)^(\s*div\(rhoPhi,U\) Gauss )limitedLinearV 1;$")
    text, count = pattern.subn(rf"\g<1>{VARIANTS[variant]};", text)
    if count != 1:
        raise ValueError("HPC fvSchemes must contain one U convection entry")
    path.write_text(text, encoding="utf-8")


def _set_nozzle_air(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(?ms)(\bnozzle\s*\{\s*type\s+fixedValue;\s*value\s+uniform\s+)1(\s*;\s*\})"
    )
    text, count = pattern.subn(r"\g<1>0\g<2>", text)
    if count != 1:
        raise ValueError("expected one water-filled nozzle alpha boundary in source template")
    path.write_text(text, encoding="utf-8")


def write_case(
    destination: Path, variant: str, *, horizon_s: float = FULL_HORIZON_S, ranks: int = 4
) -> dict[str, Any]:
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    supported_horizons = (PILOT_HORIZON_S, 0.3, FULL_HORIZON_S)
    if not any(abs(horizon_s - supported) <= 1e-12 for supported in supported_horizons):
        raise ValueError(f"horizon must be one of {supported_horizons} s")
    if ranks not in (4, 8):
        raise ValueError("this diagnostic supports four or eight MPI ranks")
    write_interval_s = min(0.25, horizon_s)
    if abs(round(horizon_s / write_interval_s) * write_interval_s - horizon_s) > 1e-10:
        write_interval_s = horizon_s
    field_write_times_s = [0.0]
    full_intervals = int(horizon_s / write_interval_s)
    for i in range(1, full_intervals + 1):
        t = round(i * write_interval_s, 12)
        if t < horizon_s - 1e-10:
            field_write_times_s.append(t)
    if abs(field_write_times_s[-1] - horizon_s) > 1e-10:
        field_write_times_s.append(round(horizon_s, 12))
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SOURCE_CASE / "0", destination / "0")
    shutil.copytree(SOURCE_CASE / "constant", destination / "constant")
    system = destination / "system"
    system.mkdir()
    _set_variant(system / "fvSchemes", variant)
    shutil.copy2(HPC_TEMPLATE / "fvSolution", system / "fvSolution")
    _set_nozzle_air(destination / "0/alpha.water")
    (system / "controlDict").write_text(_control_dict(horizon_s), encoding="utf-8")
    (system / "decomposeParDict").write_text(_decompose_dict(ranks), encoding="utf-8")
    (destination / "case.foam").touch()
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "case_id": f"ROUAIX-AIR-{variant.upper()}-{round(horizon_s / DELTA_T_S):05d}"
        + (f"-{ranks:02d}RANK" if ranks != 4 else ""),
        "scope": "Exploratory all-air negative control; not an E1 reproduction or validation case.",
        "source_mode": "alpha.water=0 in all cells and at nozzle; the prescribed nozzle velocity (0,-10,0) m/s is retained while the source composition is declared gas.",
        "solver": "OpenCFD v2512 interIsoFoam",
        "reference_image_digest": IMAGE_ID,
        "momentum_convection": VARIANTS[variant],
        "other_scheme_entries": "Same v2512 Rouaix HPC template in both siblings.",
        "coordinate_frame": {"x": "crossflow +", "y": "upward +", "z": "spanwise +"},
        "nozzle_velocity_m_s": [0.0, -10.0, 0.0],
        "gas_inlet_velocity_m_s": [70.0, 0.0, 0.0],
        "delta_t_s": DELTA_T_S,
        "end_time_s": horizon_s,
        "expected_steps": round(horizon_s / DELTA_T_S),
        "mpi_ranks": ranks,
        "write_interval_s": write_interval_s,
        "field_write_times_s": field_write_times_s,
        "initial_condition": "all-air alpha.water=0",
        "turbulence": "realizable k-epsilon RANS from Case 1 source fields",
        "source_turbulence_boundary_note": (
            "Case 1 source fields retained: nozzle k=0.015 m2/s2 and epsilon=0.0107810420 m2/s3; "
            "gasInlet k=0.735 m2/s2 and epsilon=3.6978974178 m2/s3. With alpha.water=0, "
            "this is not gas-turbulence-matched."
        ),
        "flux_field_note": (
            "phi is mixture-volume flux; alphaPhi_ is water-phase flux. "
            "Both are recorded separately; alphaPhi_ is zero in the all-air state."
        ),
        "runtime_guard": {
            "max_abs_U_m_s": MAX_U_M_S,
            "write_and_stop_signal": 12,
            "hard_wall_seconds": 1680,
            "grace_seconds": 120,
        },
        "diagnostics": {
            "every_step_extrema_with_locations": [
                "mag(U)",
                "alpha.water",
                "p_rgh",
                "k",
                "epsilon",
                "nut",
            ],
            "fixed_probes_m": [list(point) for point in PROBES_M],
            "water_volume_every_step": True,
            "patch_fluxes_every_step": list(FLUX_PATCHES),
            "field_write_times_s": field_write_times_s,
            "observer_oldTime_calls": False,
        },
        "source_sha256": {
            "case1_template": tree_hashes(SOURCE_CASE),
            "hpc_fvSchemes": sha256(HPC_TEMPLATE / "fvSchemes"),
            "hpc_fvSolution": sha256(HPC_TEMPLATE / "fvSolution"),
            "case_generator": sha256(Path(__file__)),
        },
    }
    metadata["case_files_sha256"] = tree_hashes(destination)
    metadata["case_files_total_bytes"] = sum(
        p.stat().st_size for p in destination.rglob("*") if p.is_file()
    )
    (destination / "case-inputs.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def attach_mesh(case_dir: Path, mesh_dir: Path) -> dict[str, str]:
    """Attach a native-QA'd polyMesh to a fresh case, refusing existing mesh data."""
    target = case_dir / "constant/polyMesh"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    shutil.copytree(mesh_dir, target)
    hashes = tree_hashes(target)
    metadata_path = case_dir / "case-inputs.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["mesh_files_sha256"] = hashes
    metadata["mesh_file_count"] = len(hashes)
    metadata["case_files_sha256"] = tree_hashes(case_dir, exclude=("case-inputs.json",))
    metadata["case_files_total_bytes"] = sum(
        path.stat().st_size
        for path in case_dir.rglob("*")
        if path.is_file() and path.name != "case-inputs.json"
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return hashes


def prepare_pair(
    destination: Path, *, horizon_s: float = FULL_HORIZON_S, ranks: int = 4
) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    mesh = write_mesh_input(destination / "mesh-input")
    cases = {
        variant: write_case(destination / variant, variant, horizon_s=horizon_s, ranks=ranks)
        for variant in VARIANTS
    }
    return {"mesh": mesh, "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--horizon-s", type=float, default=FULL_HORIZON_S)
    parser.add_argument("--ranks", type=int, choices=(4, 8), default=4)
    args = parser.parse_args()
    record = prepare_pair(args.output, horizon_s=args.horizon_s, ranks=args.ranks)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "base_cells": BASE_CELLS,
                "variants": list(record["cases"]),
                "horizon_s": args.horizon_s,
                "ranks": args.ranks,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
