from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cases.e1_rouaix_fast_diagnostics import build_cases  # noqa: E402


def test_all_air_pair_has_frozen_inputs_and_single_convection_change(tmp_path: Path) -> None:
    mesh = tmp_path / "mesh-input"
    mesh_record = build_cases.write_mesh_input(mesh)
    assert mesh_record["structured_base_mesh"]["cells"] == 299_520
    assert mesh_record["structured_base_mesh"]["x_cells_by_band"] == [4, 20, 18, 10, 13]
    assert mesh_record["structured_base_mesh"]["y_cells_by_band"] == [5, 7, 20]
    assert mesh_record["structured_base_mesh"]["spanwise_cells"] == 144
    assert mesh_record["local_refinement"]["nominal_near_nozzle_base_spacing_m"] == [
        0.05,
        0.05,
        7 / 144,
    ]
    mesh_control = (mesh / "system/controlDict").read_text()
    assert "application meshOnly;" in mesh_control
    assert mesh_record["template_sha256"]["mesh_control_dict"] == build_cases.sha256(
        build_cases.MESH_CONTROL_DICT
    )
    for name in ("fvSchemes", "fvSolution"):
        assert (mesh / f"system/{name}").read_bytes() == (
            build_cases.HPC_TEMPLATE / name
        ).read_bytes()
    assert "addLayersControls" in (mesh / "system/snappyHexMeshDict").read_text()
    block = (mesh / "system/blockMeshDict").read_text()
    assert "(-2.5 -10 -8)" in block and "(17.5 0 3.5)" in block
    assert "(17.5 0 -3.5)" in block and "(-2.5 -10 8)" in block
    assert "castellatedMesh false;" in (mesh / "system/snappyHexMeshDict").read_text()
    assert mesh_record["local_refinement"]["applied"] is False
    for patch in (
        "gasInlet",
        "downstreamOutlet",
        "bottomOutlet",
        "aircraftWall",
        "spanwiseMinus",
        "spanwisePlus",
    ):
        assert f"{patch} {{ type" in block
    topo = (mesh / "system/topoSetDict").read_text()
    assert "radius 0.2;" in topo
    assert "levels ((1e15 1))" in (mesh / "system/snappyHexMeshDict").read_text()

    original = tmp_path / "original"
    upwind = tmp_path / "upwind"
    original_meta = build_cases.write_case(original, "original")
    upwind_meta = build_cases.write_case(upwind, "upwind")
    assert original_meta["expected_steps"] == upwind_meta["expected_steps"] == 5000
    assert original_meta["reference_image_digest"] == build_cases.IMAGE_ID
    assert original_meta["runtime_guard"]["max_abs_U_m_s"] == 1000

    original_files = {
        p.relative_to(original).as_posix(): p for p in original.rglob("*") if p.is_file()
    }
    upwind_files = {p.relative_to(upwind).as_posix(): p for p in upwind.rglob("*") if p.is_file()}
    assert set(original_files) == set(upwind_files)
    differences = {
        name
        for name in original_files
        if name != "case-inputs.json"
        and original_files[name].read_bytes() != upwind_files[name].read_bytes()
    }
    assert differences == {"system/fvSchemes"}
    for case_dir, variant, expected in (
        (original, "original", "limitedLinearV 1"),
        (upwind, "upwind", "upwind"),
    ):
        schemes = (case_dir / "system/fvSchemes").read_text()
        assert f"div(rhoPhi,U) Gauss {expected};" in schemes
        assert "div(rhoPhi,k) Gauss upwind;" in schemes
        assert "div(rhoPhi,epsilon) Gauss upwind;" in schemes
        alpha = (case_dir / "0/alpha.water").read_text()
        assert "internalField   uniform 0;" in alpha
        assert (
            "nozzle\n    {\n        type            fixedValue;\n        value           uniform 0;"
            in alpha
        )
        velocity = (case_dir / "0/U").read_text()
        assert "value           uniform (0 -10 0);" in velocity
        assert "value           uniform (70 0 0);" in velocity
        control = (case_dir / "system/controlDict").read_text()
        for token in (
            "stopAtWriteNowSignal 12",
            "writeInterval 0.25",
            "fieldMinMax",
            "volFieldValue",
            "surfaceFieldValue",
            "fixedProbes",
            "executeInterval 1",
            "location true",
        ):
            assert token in control
        recorded = json.loads((case_dir / "case-inputs.json").read_text())
        assert "not gas-turbulence-matched" in recorded["source_turbulence_boundary_note"]
        assert "phi is mixture-volume flux" in recorded["flux_field_note"]
        actual = {
            p.relative_to(case_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in case_dir.rglob("*")
            if p.is_file() and p.name != "case-inputs.json"
        }
        assert recorded["case_files_sha256"] == actual
        assert recorded["momentum_convection"] == expected

    pilot = tmp_path / "air-a-pilot"
    pilot_meta = build_cases.write_case(pilot, "original", horizon_s=0.01)
    assert pilot_meta["expected_steps"] == 100
    assert pilot_meta["field_write_times_s"] == [0.0, 0.01]
    assert "writeInterval 0.01;" in (pilot / "system/controlDict").read_text()

    with pytest.raises(ValueError, match="horizon must be one of"):
        build_cases.write_case(tmp_path / "unsupported-horizon", "original", horizon_s=0.4)

    reprofile = tmp_path / "air-a-pilot-8rank"
    reprofile_meta = build_cases.write_case(reprofile, "original", horizon_s=0.01, ranks=8)
    assert reprofile_meta["mpi_ranks"] == 8
    assert "numberOfSubdomains 8;" in (reprofile / "system/decomposeParDict").read_text()
    assert "n (2 2 2);" in (reprofile / "system/decomposeParDict").read_text()

    original_030 = tmp_path / "original-030"
    upwind_030 = tmp_path / "upwind-030"
    original_030_meta = build_cases.write_case(original_030, "original", horizon_s=0.30, ranks=8)
    upwind_030_meta = build_cases.write_case(upwind_030, "upwind", horizon_s=0.30, ranks=8)
    assert upwind_030_meta["expected_steps"] == original_030_meta["expected_steps"]
    assert upwind_030_meta["field_write_times_s"] == original_030_meta["field_write_times_s"]
    assert upwind_030_meta["mpi_ranks"] == original_030_meta["mpi_ranks"]
    assert original_030_meta["expected_steps"] == 3000
    assert original_030_meta["field_write_times_s"] == [0.0, 0.3]
    assert original_030_meta["write_interval_s"] == 0.3
    assert original_030_meta["mpi_ranks"] == 8
    assert original_030_meta["case_id"].endswith("-08RANK")
    assert original_030_meta["runtime_guard"]["hard_wall_seconds"] == 1680
    assert original_030_meta["runtime_guard"]["grace_seconds"] == 120
    control_030 = (original_030 / "system/controlDict").read_text()
    assert "endTime 0.3;" in control_030
    assert "writeInterval 0.3;" in control_030
    original_hashes = {
        p.relative_to(original_030).as_posix(): p for p in original_030.rglob("*") if p.is_file()
    }
    upwind_hashes = {
        p.relative_to(upwind_030).as_posix(): p for p in upwind_030.rglob("*") if p.is_file()
    }
    assert set(original_hashes) == set(upwind_hashes)
    assert {
        name
        for name in original_hashes
        if name != "case-inputs.json"
        and original_hashes[name].read_bytes() != upwind_hashes[name].read_bytes()
    } == {"system/fvSchemes"}


def test_collated_snapshot_inventory_accepts_guard_time_not_future_field_time(
    tmp_path: Path,
) -> None:
    runner_path = (
        ROOT / "results/runs/rouaix-fast-local-20261027/cases-and-runs/attempt-003/run_remote.py"
    )
    spec = importlib.util.spec_from_file_location("rouaix_fast_local_runner", runner_path)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.RUN = tmp_path

    case = tmp_path / "case"
    case.mkdir()
    (case / "case-inputs.json").write_text(json.dumps({"field_write_times_s": [0.0, 0.3]}))
    output = tmp_path / "container-runs/air-original-030"
    time_root = output / "evidence/case/times/processors8"
    for time_value in ("0", "0.2628"):
        snapshot = time_root / time_value
        snapshot.mkdir(parents=True)
        for field in ("U", "alpha.water", "p_rgh"):
            (snapshot / field).write_text("field")
    (output / "terminal-status.json").write_text(json.dumps({"solver_time_s": "0.262800000000"}))

    inventory = runner._snapshot_inventory(output, "case")
    assert inventory["passed"] is True
    assert inventory["reached_declared_times_s"] == ["0"]
    assert inventory["unreached_declared_times_s"] == ["0.3"]
    assert inventory["expected_captured_times_s"] == ["0", "0.2628"]
