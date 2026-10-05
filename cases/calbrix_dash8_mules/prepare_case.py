#!/usr/bin/env python3
"""Prepare an unlaunched stock interFoam/MULES Dash-8 transport comparator.

This case keeps the corrected uniform Dash-8 source inputs and uses the same
OpenFOAM mesh and RANS/pressure inputs as the 670,480-cell interIsoFoam
reference.  It changes only the VOF transport algorithm, its required alpha
schemes/controls, solver name, and phase-flux diagnostic field.  The Calbrix
paper does not specify its VOF transport discretization, so this is a numerical
sensitivity case rather than a recovered paper method.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASE_GENERATOR = ROOT / "cases/calbrix_dash8/prepare_case.py"
REFERENCE_RUN_ID = "dash8-freestream-backflow-20261004T200945Z"
REFERENCE_RUN = ROOT / "results/runs" / REFERENCE_RUN_ID
REFERENCE_CASE = REFERENCE_RUN / "case"
REFERENCE_MANIFEST = REFERENCE_RUN / "manifest.json"
OPENFOAM_IMAGE = "opencfd/openfoam-default:2512"
OPENFOAM_IMAGE_SHA256 = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
HORIZON_S = 0.6
RANKS = 20
MEMORY_GIB = 96
EXPECTED_CELLS = 670_480
SOURCE_AREA_M2 = 4.44 * 0.30
WATER_FLUX_FIELD = "alphaPhi0.water"

MULES_ALPHA_BLOCK = """    "alpha.water.*"
    {
        nAlphaCorr      2;
        nAlphaSubCycles 1;
        cAlpha          1;
        MULESCorr       yes;
        nLimiterIter    3;
        alphaApplyPrevCorr no;
        icAlpha         0;
        scAlpha         0;

        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): _sha256(path)
        for path in sorted(path for path in directory.rglob("*") if path.is_file())
    }


def _input_file_hashes(case: Path) -> dict[str, str]:
    files = [
        path
        for top in ("0", "constant", "system", "source")
        for path in (case / top).rglob("*")
        if path.is_file()
    ]
    files.extend((case / "source_geometry.json",))
    return {
        path.relative_to(case).as_posix(): _sha256(path) for path in sorted(files) if path.exists()
    }


def _load_base_generator() -> Any:
    spec = importlib.util.spec_from_file_location("calbrix_dash8_base_generator", BASE_GENERATOR)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load base Dash-8 generator at {BASE_GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _reference_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    if not REFERENCE_CASE.is_dir() or not REFERENCE_MANIFEST.is_file():
        raise FileNotFoundError(f"corrected reference case is missing: {REFERENCE_CASE}")
    case_inputs = json.loads((REFERENCE_CASE / "case-inputs.json").read_text(encoding="utf-8"))
    manifest = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    _require(manifest.get("status") == "exploratory_completed", "reference run is not complete")
    _require(manifest.get("run_id") == REFERENCE_RUN_ID, "unexpected reference run id")
    _require(case_inputs.get("solver") == "interIsoFoam", "reference solver changed")
    _require(
        case_inputs.get("mesh_cells_expected") == EXPECTED_CELLS, "reference mesh size changed"
    )
    _require(
        abs(case_inputs.get("source_patch_areas_m2", {}).get("dash8Opening", -1) - SOURCE_AREA_M2)
        < 1e-12,
        "reference source area changed",
    )
    _require(case_inputs.get("air_speed_m_s") == 50.0, "reference crossflow changed")
    _require(case_inputs.get("gravity_m_s2") == [0.0, 0.0, -9.81], "reference gravity changed")
    _require(
        case_inputs.get("turbulence_model") == "standard k-epsilon RANS",
        "reference RANS model changed",
    )
    _require(
        case_inputs.get("fluid_properties", {}).get("surface_tension_N_m") == 0.0,
        "reference surface-tension setting changed",
    )
    _require(
        case_inputs.get("time_controls", {}).get("turbulence_linear_solver", {}).get("choice")
        == "pbicgstab",
        "reference turbulence linear solver changed",
    )
    _require(
        case_inputs.get("source_patch_face_counts", {}).get("dash8Opening") == 224,
        "reference source-face count changed",
    )
    _require(
        case_inputs.get("inlet_profile", {}).get("kind") == "uniform",
        "reference inlet is no longer the uniform-history case",
    )
    original_control = (REFERENCE_CASE / "system/controlDict").read_text(encoding="utf-8")
    original_solution = (REFERENCE_CASE / "system/fvSolution").read_text(encoding="utf-8")
    _require(
        "application interIsoFoam;" in original_control, "reference controlDict solver changed"
    )
    _require("nAlphaSubCycles 1;" in original_solution, "reference alpha subcycling changed")
    _require("nOuterCorrectors 1;" in original_solution, "reference outer corrector count changed")
    _require(
        "type uniformFixedValue;" in (REFERENCE_CASE / "0/U").read_text(encoding="utf-8"),
        "reference source boundary is not uniformFixedValue",
    )
    reference_velocity = (REFERENCE_CASE / "0/U").read_text(encoding="utf-8")
    _require(
        reference_velocity.count("tangentialVelocity uniform (50 0 0);") == 4,
        "reference does not retain corrected freestream tangential velocity on four open patches",
    )
    owner_header = (
        (REFERENCE_CASE / "constant/polyMesh/owner")
        .read_bytes()[:4096]
        .decode("ascii", errors="ignore")
    )
    cell_match = re.search(r"nCells:\s*(\d+)", owner_header)
    _require(
        cell_match is not None and int(cell_match.group(1)) == EXPECTED_CELLS,
        "reference native polyMesh cell count changed",
    )
    _require(
        manifest.get("solver_image") == "opencfd/openfoam-default:2512",
        "reference solver image tag changed",
    )
    return case_inputs, manifest


def _replace_braced_entry(text: str, key: str, replacement: str) -> str:
    pattern = re.compile(rf"(?m)^(?P<indent>[ \t]*){re.escape(key)}[ \t]*(?:\r?\n[ \t]*)?\{{")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"expected one dictionary entry {key!r}, found {len(matches)}")
    match = matches[0]
    open_brace = text.index("{", match.start())
    depth = 0
    close_brace = None
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                close_brace = index
                break
    if close_brace is None:
        raise ValueError(f"unclosed dictionary entry {key!r}")
    return text[: match.start()] + replacement + text[close_brace + 1 :]


def _patch_case_dictionaries(case: Path) -> None:
    velocity_path = case / "0/U"
    velocity = velocity_path.read_text(encoding="utf-8")
    backflow_pattern = "type pressureInletOutletVelocity;\n        value uniform (0 0 0);"
    corrected_backflow_pattern = (
        "type pressureInletOutletVelocity;\n"
        "        tangentialVelocity uniform (50 0 0);\n"
        "        value uniform (0 0 0);"
    )
    corrected_count = velocity.count(corrected_backflow_pattern)
    uncorrected_count = velocity.count(backflow_pattern)
    _require(
        velocity.count("type pressureInletOutletVelocity;") == 4,
        "generated velocity field no longer has four expected pressure inlet/outlet patches",
    )
    if corrected_count != 4:
        _require(
            uncorrected_count == 4,
            "generated velocity field no longer matches the corrected reference backflow patches",
        )
        velocity = velocity.replace(backflow_pattern, corrected_backflow_pattern)
    _require(
        velocity.count(corrected_backflow_pattern) == 4 and velocity.count(backflow_pattern) == 0,
        "candidate backflow velocity does not match the corrected reference",
    )
    velocity_path.write_text(velocity, encoding="utf-8")

    control_path = case / "system/controlDict"
    control = control_path.read_text(encoding="utf-8")
    _require(control.count("application interIsoFoam;") == 1, "unexpected source application entry")
    _require(control.count("alphaPhi_") == 6, "unexpected number of interIsoFoam flux references")
    control = control.replace("application interIsoFoam;", "application interFoam;")
    control = control.replace("alphaPhi_", WATER_FLUX_FIELD)
    _require("endTime 0.6;" in control, "candidate horizon is not 0.6 s")
    control_path.write_text(control, encoding="utf-8")

    schemes_path = case / "system/fvSchemes"
    schemes = schemes_path.read_text(encoding="utf-8")
    _require("div(phi,alpha)" not in schemes, "MULES alpha scheme already present")
    _require("div(phirb,alpha)" not in schemes, "MULES compression scheme already present")
    marker = "    div(rhoPhi,epsilon) Gauss limitedLinear 1;"
    _require(schemes.count(marker) == 1, "reference turbulence divergence entry changed")
    schemes = schemes.replace(
        marker,
        marker + "\n    div(phi,alpha) Gauss vanLeer;" + "\n    div(phirb,alpha) Gauss linear;",
    )
    schemes_path.write_text(schemes, encoding="utf-8")

    solution_path = case / "system/fvSolution"
    solution = solution_path.read_text(encoding="utf-8")
    solution = _replace_braced_entry(solution, '"alpha.water.*"', MULES_ALPHA_BLOCK)
    solution_path.write_text(solution, encoding="utf-8")


def prepare_case(output: Path) -> dict[str, Any]:
    """Generate the frozen-physics 0.6 s MULES comparator at ``output``."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"output already exists; preserving it: {output}")
    _reference_contract()
    base = _load_base_generator()
    metadata = base.prepare_case(
        output,
        horizon_s=HORIZON_S,
        ranks=RANKS,
        snapshot_interval_s=0.1,
        spacing_m=0.08,
        coarse_spacing_m=0.6,
        source_length_m=4.44,
        source_width_m=0.30,
        source_profile="uniform",
        turbulence_linear_solver="pbicgstab",
        air_turbulence_intensity=0.05,
        water_turbulence_intensity=0.05,
        air_length_scale_m=0.05,
        water_length_scale_m=0.05,
    )
    generated_mesh = _sha256(output / "system/blockMeshDict")
    reference_mesh = _sha256(REFERENCE_CASE / "system/blockMeshDict")
    _require(generated_mesh == reference_mesh, "generated mesh dictionary differs from reference")

    mesh_destination = output / "constant/polyMesh"
    shutil.copytree(REFERENCE_CASE / "constant/polyMesh", mesh_destination)
    owner_header = mesh_destination / "owner"
    header_text = owner_header.read_bytes()[:4096].decode("ascii", errors="ignore")
    cell_match = re.search(r"nCells:\s*(\d+)", header_text)
    _require(
        cell_match is not None and int(cell_match.group(1)) == EXPECTED_CELLS,
        "copied mesh does not contain the expected number of cells",
    )

    _patch_case_dictionaries(output)
    metadata["solver"] = "interFoam"
    metadata["horizon_s"] = HORIZON_S
    metadata["ranks"] = RANKS
    metadata["resources"] = {
        "mpi_ranks": RANKS,
        "memory_gib": MEMORY_GIB,
        "status": "prepared only; no solver launched",
    }
    metadata["time_controls"]["end_s"] = HORIZON_S
    metadata["numerical_method_comparison"] = {
        "classification": "exploratory VOF-method sensitivity; not a recovered Calbrix method or validation",
        "paper_transport_method_reported": False,
        "method": "OpenCFD v2512 stock interFoam MULES with bounded interface compression",
        "alpha_convection_scheme": "div(phi,alpha) Gauss vanLeer",
        "compression_convection_scheme": "div(phirb,alpha) Gauss linear",
        "alpha_controls": {
            "nAlphaCorr": 2,
            "nAlphaSubCycles": 1,
            "cAlpha": 1,
            "MULESCorr": True,
            "nLimiterIter": 3,
            "alphaApplyPrevCorr": False,
            "icAlpha": 0,
            "scAlpha": 0,
            "alpha_predictor_solver": "smoothSolver / symGaussSeidel, tolerance 1e-8, relTol 0",
        },
        "phase_volume_flux": {
            "field_name": WATER_FLUX_FIELD,
            "units": "m^3/s",
            "meaning": "registered AUTO_WRITE MULES-corrected phase-1 volume flux used to assemble rhoPhi",
            "main_step_contract": "nAlphaSubCycles=1 leaves one alpha update over the full main time step; pair each logged flux with its solver deltaT",
            "subcycle_limit": "interFoam alphaEqnSubCycle time-averages rhoPhi, not alphaPhi0.water; do not increase nAlphaSubCycles without a separate phase-flux aggregation check",
        },
        "source_evidence": {
            "image": OPENFOAM_IMAGE,
            "image_sha256": OPENFOAM_IMAGE_SHA256,
            "registered_field_definition": "applications/solvers/multiphase/VoF/createAlphaFluxes.H",
            "mules_flux_update_and_rhoPhi_use": "applications/solvers/multiphase/VoF/alphaEqn.H",
            "subcycle_averaging": "applications/solvers/multiphase/VoF/alphaEqnSubCycle.H",
            "control_lookup": "src/finiteVolume/cfdTools/general/include/alphaControls.H",
        },
        "required_runtime_verification": [
            "confirm interFoam starts with these exact fvSolution/fvSchemes hashes",
            "confirm post-step registry/output contains alphaPhi0.water and every flux row has paired native deltaT",
            "close water ledger against stored alpha.water and summed boundary alphaPhi0.water; this preparation is not a ledger pass",
        ],
    }
    metadata["reference_clone"] = {
        "run_id": REFERENCE_RUN_ID,
        "manifest_sha256": _sha256(REFERENCE_MANIFEST),
        "case_inputs_sha256": _sha256(REFERENCE_CASE / "case-inputs.json"),
        "base_solver": "interIsoFoam",
        "mesh_cells": EXPECTED_CELLS,
        "mesh_blockMeshDict_sha256": reference_mesh,
        "copied_polyMesh_sha256": _tree_digest(mesh_destination),
        "copied_polyMesh_file_hashes": _tree_hashes(mesh_destination),
        "source_area_m2": SOURCE_AREA_M2,
        "statement": "initial fields, physical dictionaries, source history through 0.6 s, mesh recipe and polyMesh are matched; alpha transport method and its alpha-specific schemes/controls/flux observer differ",
        "corrected_freestream_backflow": "The four open pressureInletOutletVelocity patches retain the frozen reference tangentialVelocity uniform (50 0 0); the history tables in 0/U, 0/k, and 0/epsilon are horizon-truncated to 0.6 s with values through 0.6 s unchanged.",
    }
    metadata["prepared_input_hashes_sha256"] = _input_file_hashes(output)
    metadata["provenance"]["mules_preparation_script_sha256"] = _sha256(Path(__file__))
    metadata_path = output / "case-inputs.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def _tree_digest(directory: Path) -> str:
    records = "".join(
        f"{relative} {digest}\n" for relative, digest in _tree_hashes(directory).items()
    )
    return hashlib.sha256(records.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new candidate case directory")
    args = parser.parse_args(argv)
    metadata = prepare_case(args.output)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "solver": metadata["solver"],
                "horizon_s": metadata["horizon_s"],
                "ranks": metadata["ranks"],
                "mesh_cells_expected": metadata["mesh_cells_expected"],
                "phase_volume_flux": metadata["numerical_method_comparison"]["phase_volume_flux"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
