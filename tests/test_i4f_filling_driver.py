from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_i4f_filling_network", ROOT / "scripts/run_i4f_filling_network.py"
)
assert SPEC is not None and SPEC.loader is not None
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def _parameters(packet: Path):
    return driver._build_parameters(
        valve_cd=0.7,
        valve_opening_time_s=1.0,
        air_minor_loss_k=None,
        input_packet_dir=packet,
    )


def test_flush_packet_matches_native_tank_and_keeps_direct_compact_coordinates() -> None:
    packet = ROOT / "experiments/i4f_flush_filling_reference"
    manifest, inputs = driver._read_input_packet(packet)
    params, geometry = _parameters(packet)
    native = json.loads(inputs["native-initialization-dryline.json"].read_text())

    tank_volume = native["native_partition"]["groups"]["tankA"]["volume_m3"]
    tank_water = native["native_tank_water_integrals_m3"]["tankA"]
    native_feed = native["additional_wetted_feed_water_m3"]["tankA_feed"]
    assert manifest["schema"] == "i4f-flush-filling-reference-input-packet/v1"
    assert params.tank.tank_volume_m3 == pytest.approx(tank_volume, abs=1e-12)
    assert params.tank.tank_volume_m3 * params.tank.fill_fraction == pytest.approx(
        tank_water, abs=1e-12
    )
    assert params.gas.initial_pressure_abs_Pa == pytest.approx(1.2e6)
    assert geometry["coordinate_map"]["coordinate_map_mode"] == "identity_compact"
    assert geometry["native_initialization_input_comparison"]["all_direct_state_assertions_pass"]
    line_partition = geometry["line_zone_water_partition"]
    assert line_partition["native_downstream_train_group_water_m3"] == pytest.approx(native_feed)
    assert "includes wetted feed" in line_partition["native_downstream_train_group_scope"]
    assert line_partition["inferred_downstream_water_m3"] == pytest.approx(0.0, abs=1e-15)

    modeled_feed = sum(branch.initial_wet_volume_m3 for branch in params.branches)
    assert modeled_feed == pytest.approx(0.2526483216, abs=2e-10)
    assert modeled_feed != pytest.approx(native_feed, rel=1e-4)
    assert geometry["initial_wet_feed_comparison"]["model_minus_native_m3"] == pytest.approx(
        modeled_feed - native_feed, abs=1e-12
    )
    assert geometry["equivalent_minus_native_full_line_zone_percent"] == pytest.approx(
        2.08, abs=0.06
    )
    for branch in params.branches:
        assert any(
            branch.branch.outlet_center_z_m == pytest.approx(value) for value in (0.65, 0.90)
        )
        assert branch.length_m == pytest.approx(4.4, abs=0.08)
        assert geometry["branches"][branch.branch.name]["mouth_x_m"] == pytest.approx(4.8)
        terminal = branch.branch.sections[-1]
        assert terminal.hydraulic_diameter_start_m == pytest.approx(0.2608695652173913)
        assert terminal.hydraulic_diameter_end_m == pytest.approx(0.2608695652173913)


def test_legacy_packet_remains_default_x_remapped_reference() -> None:
    params, geometry = _parameters(driver.INPUT_PACKET_DIR)
    assert geometry["coordinate_map"]["coordinate_map_mode"] == "legacy_x_only"
    assert geometry[
        "source_centerline_is_legacy_preview_x_only_remapped_to_compact_current_candidate"
    ]
    assert geometry["branches"]["lower"]["mouth_x_m"] == pytest.approx(4.8)
    line_partition = geometry["line_zone_water_partition"]
    assert line_partition["native_downstream_train_group_water_m3"] == pytest.approx(0.0)
    assert (
        "upstream feed is a separate native group"
        in line_partition["native_downstream_train_group_scope"]
    )
    assert line_partition["inferred_downstream_water_m3"] == pytest.approx(0.0, abs=1e-15)
    comparison = geometry["native_initialization_input_comparison"]
    assert comparison["all_direct_state_assertions_pass"]
    assert comparison["assertions"]["downstream_initial_water_m3"]["pass"]
    mouth_width_m = 1.0
    mouth_height_m = 0.15
    derived_rectangular_diameter = (
        2.0 * mouth_width_m * mouth_height_m / (mouth_width_m + mouth_height_m)
    )
    for branch in params.branches:
        terminal = branch.branch.sections[-1]
        assert terminal.hydraulic_diameter_start_m == pytest.approx(derived_rectangular_diameter)
        assert terminal.hydraulic_diameter_end_m == pytest.approx(derived_rectangular_diameter)


def test_packet_producer_hashes_are_provenance_not_runtime_dependencies(tmp_path: Path) -> None:
    packet = ROOT / "experiments/i4f_flush_filling_reference"
    manifest = json.loads((packet / "inputs-manifest.json").read_text())
    for entry in manifest["files"]:
        source = packet / entry["path"]
        destination = tmp_path / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    declared_sources = manifest["source_hashes"]
    source_path = next(iter(declared_sources))
    declared_sources[source_path] = "0" * 64
    (tmp_path / "inputs-manifest.json").write_text(json.dumps(manifest))

    loaded_manifest, loaded_files = driver._read_input_packet(tmp_path)
    assert loaded_manifest["source_hashes"][source_path] == "0" * 64
    assert "branch-centerline-sections.csv" in loaded_files
