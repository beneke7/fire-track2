from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MULES_GENERATOR_PATH = ROOT / "cases/calbrix_dash8_mules/prepare_case.py"
BASE_GENERATOR_PATH = ROOT / "cases/calbrix_dash8/prepare_case.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mules = _load_module("test_dash8_mules_prepare_case", MULES_GENERATOR_PATH)
base = _load_module("test_dash8_base_prepare_case_for_mules", BASE_GENERATOR_PATH)


def _add_frozen_backflow_velocity(case: Path) -> None:
    path = case / "0/U"
    velocity = path.read_text(encoding="utf-8")
    uncorrected = "type pressureInletOutletVelocity;\n        value uniform (0 0 0);"
    corrected = (
        "type pressureInletOutletVelocity;\n"
        "        tangentialVelocity uniform (50 0 0);\n"
        "        value uniform (0 0 0);"
    )
    if velocity.count(corrected) != 4:
        assert velocity.count(uncorrected) == 4
        velocity = velocity.replace(uncorrected, corrected)
    path.write_text(velocity, encoding="utf-8")


@pytest.fixture(scope="module")
def candidate_case(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("dash8-mules")
    reference = root / "synthetic-reference"
    base.prepare_case(
        reference,
        horizon_s=1.5,
        ranks=20,
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
    _add_frozen_backflow_velocity(reference)
    owner = reference / "constant/polyMesh/owner"
    owner.parent.mkdir(parents=True, exist_ok=True)
    owner.write_text(
        "FoamFile { class labelList; }\nnCells: 670480;\n670480\n(\n);\n", encoding="ascii"
    )
    mules.REFERENCE_CASE = reference
    mules.REFERENCE_MANIFEST = root / "manifest.json"
    mules.REFERENCE_MANIFEST.write_text(
        json.dumps(
            {
                "status": "exploratory_completed",
                "run_id": mules.REFERENCE_RUN_ID,
                "solver_image": mules.OPENFOAM_IMAGE,
            }
        ),
        encoding="utf-8",
    )

    case = root / "case"
    mules.prepare_case(case)
    return case


def _baseline_case(case: Path) -> Path:
    base.prepare_case(
        case,
        horizon_s=0.6,
        ranks=20,
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
    return case


def test_candidate_matches_physics_inputs_and_only_changes_vof_settings(
    candidate_case: Path, tmp_path: Path
) -> None:
    baseline = _baseline_case(tmp_path / "interiso-baseline")
    _add_frozen_backflow_velocity(baseline)
    excluded = {
        "case-inputs.json",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
    }
    baseline_paths = sorted(
        path.relative_to(baseline).as_posix()
        for top in ("0", "constant", "system", "source")
        for path in (baseline / top).rglob("*")
        if path.is_file()
    )
    for relative in baseline_paths:
        if relative in excluded:
            continue
        assert (candidate_case / relative).read_bytes() == (baseline / relative).read_bytes(), (
            relative
        )

    baseline_control = (baseline / "system/controlDict").read_text(encoding="utf-8")
    expected_control = baseline_control.replace(
        "application interIsoFoam;", "application interFoam;"
    )
    expected_control = expected_control.replace("alphaPhi_", "alphaPhi0.water")
    assert (candidate_case / "system/controlDict").read_text(encoding="utf-8") == expected_control

    baseline_schemes = (baseline / "system/fvSchemes").read_text(encoding="utf-8")
    marker = "    div(rhoPhi,epsilon) Gauss limitedLinear 1;"
    expected_schemes = baseline_schemes.replace(
        marker,
        marker + "\n    div(phi,alpha) Gauss vanLeer;" + "\n    div(phirb,alpha) Gauss linear;",
    )
    assert (candidate_case / "system/fvSchemes").read_text(encoding="utf-8") == expected_schemes

    baseline_solution = (baseline / "system/fvSolution").read_text(encoding="utf-8")
    expected_solution = mules._replace_braced_entry(
        baseline_solution, '"alpha.water.*"', mules.MULES_ALPHA_BLOCK
    )
    assert (candidate_case / "system/fvSolution").read_text(encoding="utf-8") == expected_solution

    metadata = json.loads((candidate_case / "case-inputs.json").read_text(encoding="utf-8"))
    assert metadata["solver"] == "interFoam"
    assert metadata["horizon_s"] == pytest.approx(0.6)
    assert metadata["ranks"] == 20
    # These unit tests use a synthetic owner-file header; the frozen native
    # mesh count/hash is independently recorded in the ignored prep evidence.
    assert metadata["mesh_cells_expected"] == 670_480
    assert metadata["source_patch_areas_m2"]["dash8Opening"] == pytest.approx(1.332)
    assert metadata["source_patch_face_counts"]["dash8Opening"] == 224
    candidate_u = (candidate_case / "0/U").read_text(encoding="utf-8")
    assert candidate_u.count("tangentialVelocity uniform (50 0 0);") == 4
    assert metadata["turbulence_model"] == "standard k-epsilon RANS"
    assert metadata["numerical_method_comparison"]["paper_transport_method_reported"] is False
    assert metadata["reference_clone"]["run_id"] == mules.REFERENCE_RUN_ID
    assert metadata["reference_clone"]["copied_polyMesh_sha256"]
    assert metadata["resources"]["memory_gib"] == 96


def test_registered_mules_water_flux_and_step_controls_are_explicit(candidate_case: Path) -> None:
    control = (candidate_case / "system/controlDict").read_text(encoding="utf-8")
    assert "application interFoam;" in control
    assert control.count("fields (phi alphaPhi0.water);") == 6
    assert "alphaPhi_" not in control

    schemes = (candidate_case / "system/fvSchemes").read_text(encoding="utf-8")
    assert "div(phi,alpha) Gauss vanLeer;" in schemes
    assert "div(phirb,alpha) Gauss linear;" in schemes

    solution = (candidate_case / "system/fvSolution").read_text(encoding="utf-8")
    alpha_block = solution.split('"alpha.water.*"', maxsplit=1)[1].split("\n    }", maxsplit=1)[0]
    for expected in (
        "nAlphaCorr      2;",
        "nAlphaSubCycles 1;",
        "cAlpha          1;",
        "MULESCorr       yes;",
        "nLimiterIter    3;",
        "alphaApplyPrevCorr no;",
        "icAlpha         0;",
        "scAlpha         0;",
        "solver          smoothSolver;",
        "smoother        symGaussSeidel;",
    ):
        assert expected in alpha_block
    for linear_solver in (
        "U { solver PBiCGStab; preconditioner DILU;",
        "p_rgh { solver GAMG;",
        '"(k|epsilon)" { solver PBiCGStab; preconditioner DILU;',
    ):
        assert linear_solver in solution

    flux = json.loads((candidate_case / "case-inputs.json").read_text(encoding="utf-8"))[
        "numerical_method_comparison"
    ]["phase_volume_flux"]
    assert flux["field_name"] == "alphaPhi0.water"
    assert flux["main_step_contract"].startswith("nAlphaSubCycles=1")
    assert "time-averages rhoPhi, not alphaPhi0.water" in flux["subcycle_limit"]


def test_pinned_foam_dictionary_parses_prepared_controls(candidate_case: Path) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker is unavailable; pinned OpenFOAM dictionary parse was not run")
    image = subprocess.run(
        [docker, "image", "inspect", "--format", "{{.Id}}", mules.OPENFOAM_IMAGE],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if image.returncode != 0:
        pytest.skip("pinned OpenFOAM image is not present locally")
    assert image.stdout.strip() == mules.OPENFOAM_IMAGE_SHA256

    shell = (
        "source /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1; set -e; "
        "foamDictionary system/controlDict -entry application -value; "
        "foamDictionary system/controlDict -entry functions.dash8OpeningFlux.fields -value; "
        "foamDictionary system/fvSchemes -entry divSchemes; "
        "foamDictionary system/fvSolution -entry solvers"
    )
    result = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
            "--cpus",
            "1",
            "--memory",
            "2g",
            "--volume",
            f"{candidate_case.resolve()}:/case:ro",
            "--workdir",
            "/case",
            "--entrypoint",
            "/bin/bash",
            mules.OPENFOAM_IMAGE,
            "-lc",
            shell,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "interFoam" in result.stdout
    assert "alphaPhi0.water" in result.stdout
    assert "MULESCorr" in result.stdout
