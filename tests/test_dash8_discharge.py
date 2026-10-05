from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "cases/calbrix_dash8_discharge/prepare_case.py"
SPEC = importlib.util.spec_from_file_location("dash8_discharge_prepare_case", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def test_default_is_assumed_1m_head_gravity_source_without_imposed_history(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    record = prepare.prepare_case(case_dir)

    assert record["initial_condition"]["head_m"] == 1.0
    assert record["initial_condition"]["head_definition"].startswith(
        "vertical distance from outlet sampling plane z=0"
    )
    assert record["physics"]["initial_velocity_m_s"] == [0, 0, 0]
    assert (
        record["physics"]["source_history"]
        == "none; Fig. 4 is only an external post-run comparison target"
    )
    assert "value uniform (0 0 0)" in (case_dir / "0/U").read_text()
    assert "fixedValue" not in (case_dir / "0/U").read_text()
    assert "value (0 0 -9.81)" in (case_dir / "constant/g").read_text()
    pressure = (case_dir / "0/p_rgh").read_text()
    assert "type prghPressure; p uniform 0; rho rho;" in pressure
    assert "totalPressure" not in pressure
    assert record["geometry"]["aperture"]["area_m2"] == pytest.approx(1.332)
    assert record["openfoam_image_id"] == prepare.PINNED_IMAGE_ID
    assert len(prepare.PINNED_IMAGE_ID.removeprefix("sha256:")) == 64
    assert record["formal_gate"] is False


def test_aperture_sensitivity_is_explicit_and_resolution_spans_width(tmp_path: Path) -> None:
    _, large = prepare.rounded_bottom_mesh("large")
    _, small = prepare.rounded_bottom_mesh("small")

    assert large["aperture"]["area_m2"] == pytest.approx(1.332)
    assert small["aperture"]["area_m2"] == pytest.approx(0.333)
    assert large["opening_faces_across_transverse_width_minimum"] >= 6
    assert small["opening_faces_across_transverse_width_minimum"] >= 6
    assert "assumed circular rounded belly" in large["curvature"]["description"]
    assert large["downstream_plenum_bounds_m"]["throat_depth_m"] == pytest.approx(0.15)


def test_case_refuses_to_overwrite_existing_directory(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    sentinel = case_dir / "keep.txt"
    sentinel.write_text("immutable")

    with pytest.raises(FileExistsError):
        prepare.prepare_case(case_dir)

    assert sentinel.read_text() == "immutable"


def test_case_record_labels_fig4_as_comparison_only(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    prepare.prepare_case(case_dir, head_m=0.75, horizon_s=0.3)
    record = json.loads((case_dir / "case-inputs.json").read_text())

    assert record["horizon_s"] == 0.3
    assert record["initial_condition"]["head_m"] == 0.75
    assert "external post-run comparison target" in record["physics"]["source_history"]
    assert record["initial_condition"]["actual_initial_water_volume_m3"] is None


def test_runtime_fluxes_include_outlet_and_both_escape_patches(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    record = prepare.prepare_case(case_dir)
    control = (case_dir / "system/controlDict").read_text()

    assert "maxCo 0.25;" in control
    assert "maxAlphaCo 0.10;" in control
    assert "maxDeltaT 1e-3;" in control
    for name, patch in (("ambientFlux", "ambient"), ("ventFlux", "vent")):
        section = control.split(f"    {name}\n", 1)[1].split("    }", 1)[0]
        assert f"name {patch};" in section
        assert "fields (phi alphaPhi_);" in section
        assert "operation sum;" in section
    assert "name outletPlane;" in control
    assert "fields (phi alphaPhi_);" in control
    assert "owner/neighbour-interpolated" in record["diagnostics"]["velocity"]
    assert "constant physical atmospheric pressure" in record["initial_condition"]["initial_p_rgh"]


def test_mesh_verification_records_native_inventory_and_area(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    record = prepare.prepare_case(case_dir)
    (case_dir / "log.blockMesh").write_text(
        f"nCells: {record['geometry']['mesh_cells_expected']}\n"
        "patch 0 (start: 100 size: 10) name: tankWalls\n"
    )
    (case_dir / "log.checkMesh").write_text("Boundary definition OK.\nMesh OK.\nEnd\n")
    (case_dir / "log.topoSet").write_text("faceZoneSet outletPlane now size 1200\n")
    (case_dir / "log.postprocess-alpha").write_text(
        "total faces   = 1200\ntotal area    = 1.332\n"
        "volIntegrate(region0) of alpha.water = 6.32045682\n"
    )
    inventory_file = case_dir / "postProcessing/waterInventory/0.000000/volFieldValue_0.000000.dat"
    inventory_file.parent.mkdir(parents=True)
    inventory_file.write_text("# Time\tvolIntegrate(alpha.water)\n0.000000\t6.32045682\n")

    updated = prepare.record_mesh_verification(case_dir)

    assert updated["geometry"]["mesh_cells_actual"] == record["geometry"]["mesh_cells_expected"]
    assert updated["geometry"]["outlet_face_count_actual"] == 1200
    assert updated["geometry"]["outlet_facezone_area_actual_m2"] == pytest.approx(1.332)
    assert updated["initial_condition"]["actual_initial_water_volume_m3"] == pytest.approx(
        6.32045682
    )
    assert updated["mesh_build_verification"]["strict_checkmesh_ok"] is True
