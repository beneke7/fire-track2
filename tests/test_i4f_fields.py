"""Independent analytic checks for reconstructed-field diagnostics."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_i4f_fields import (
    OPEN_PATCHES,
    annotate_gas_mass_normalization,
    annotate_native_mixture_gas_storage,
    annotate_native_volume_comparison,
    annotate_native_water_ledger_normalizations,
    connection_mouth_xyz_m,
    exact_function_value,
    find_function_table,
    gas_thermo_properties,
    inventory_metrics,
    line_cell_mask,
    matched_checkpoint_normalizations,
    native_flux_ledger,
    native_gas_mass_ledger,
    nominal_section_area_m2,
    outlet_face_metrics,
    parse_scalar_table,
    section_profile_metrics,
    section_stations_for_config,
    solver_step_table,
    solver_time_controls,
    tank_cell_mask,
    weighted_quantile,
)


def test_tank_cylinder_mask_horizontal_and_vertical() -> None:
    points = np.asarray(
        [
            [1.0, 0.0, 0.65],
            [1.0, 0.0, 1.16],
            [1.0, 0.6, 0.65],
            [0.0, 0.0, 1.0],
        ]
    )
    horizontal = {
        "axis_vector": [1, 0, 0],
        "start_x_m": 0,
        "length_m": 2,
        "center_z_m": 0.65,
        "diameter_m": 1,
    }
    np.testing.assert_array_equal(tank_cell_mask(points[:3], horizontal), [True, False, False])

    vertical = {
        "axis_vector": [0, 0, 1],
        "length_m": 2,
        "center_z_m": 1,
        "diameter_m": 1,
    }
    np.testing.assert_array_equal(tank_cell_mask(points[3:], vertical), [True])


def test_tank_cylinder_mask_uses_explicit_vertical_center() -> None:
    tank = {
        "axis_vector": [0, 0, 1],
        "center_xyz_m": [1.5, 0.0, 1.5],
        "center_z_m": 1.5,
        "length_m": 2.0,
        "diameter_m": 1.0,
    }
    points = np.asarray(
        [
            [1.5, 0.0, 1.5],
            [1.5, 0.0, 2.501],
            [2.01, 0.0, 1.5],
            [1.5, 0.51, 1.5],
            [1.5, 0.0, 0.65],
        ]
    )
    np.testing.assert_array_equal(tank_cell_mask(points, tank), [True, False, False, False, True])


def test_vertical_line_mask_includes_curved_port_stub_disjoint_from_tank() -> None:
    config = {
        "tank": {
            "axis_vector": [0, 0, 1],
            "center_xyz_m": [1.5, 0.0, 1.5],
            "center_z_m": 1.5,
            "length_m": 2.0,
            "diameter_m": 1.0,
        },
        "connection": {
            "centerline_mouth_xyz_m": [2.0, 0.0, 0.65],
            "center_z_m": 0.65,
        },
        "pipe": {"diameter_m": 0.25, "length_m": 1.0, "transition_length_m": 1.5},
        "nozzle": {"width_m": 1.0, "height_m": 0.15, "center_z_m": 0.65},
    }
    points = np.asarray(
        [
            [1.995, 0.12, 0.65],  # outside cylinder, inside the curved pipe stub
            [1.995, 0.0, 0.65],  # same x, but still an actual tank cell
            [1.95, 0.12, 0.65],  # upstream of the curved port ring
            [2.2, 0.0, 0.65],  # downstream pipe
            [4.49, 0.5, 0.65],  # transition/nozzle envelope
            [4.6, 0.0, 0.65],  # beyond the line region
        ]
    )
    tank = tank_cell_mask(points, config["tank"])
    line = line_cell_mask(points, config)
    np.testing.assert_array_equal(tank, [False, True, True, False, False, False])
    np.testing.assert_array_equal(line, [True, False, False, True, True, False])
    assert not np.any(tank & line)
    assert connection_mouth_xyz_m(config).tolist() == [2.0, 0.0, 0.65]
    stations = dict(section_stations_for_config(config))
    assert stations == {
        "pipe_upstream": pytest.approx(2.2),
        "post_valve": pytest.approx(2.6),
        "pipe_end": pytest.approx(2.9),
        "transition_mid": pytest.approx(3.75),
        "nozzle_lip": pytest.approx(4.49),
        "external_mid": pytest.approx(5.5),
    }
    assert nominal_section_area_m2(3.0, config) == pytest.approx(np.pi * 0.25**2 / 4.0)
    changed_geometry = {
        **config,
        "pipe": {"diameter_m": 0.25, "length_m": 1.2, "transition_length_m": 2.0},
        "valve": {"location_x_m": 2.7},
        "analysis": {"pressure_tap_offset_m": 0.15},
        "connection": {
            **config["connection"],
            "centerline_mouth_xyz_m": [2.1, 0.0, 0.65],
        },
    }
    changed_stations = dict(section_stations_for_config(changed_geometry))
    assert changed_stations == {
        "pipe_upstream": pytest.approx(2.55),
        "post_valve": pytest.approx(2.85),
        "pipe_end": pytest.approx(3.2),
        "transition_mid": pytest.approx(4.3),
        "nozzle_lip": pytest.approx(5.29),
        "external_mid": pytest.approx(6.3),
    }
    assert nominal_section_area_m2(3.3, changed_geometry) == pytest.approx(np.pi * 0.25**2 / 4.0)
    invalid_station = {
        **changed_geometry,
        "analysis": {"section_station_overrides_x_m": {"pipe_upstream": 2.0}},
    }
    with pytest.raises(ValueError, match="pipe_upstream station"):
        section_stations_for_config(invalid_station)


def test_geometric_tank_and_line_masks_compare_only_exact_native_zone_times() -> None:
    rows = [
        {
            "time_s": 0.2,
            "total_water_volume_vtk_m3": 10.0,
            "tank_water_volume_vtk_m3": 4.0,
            "line_water_volume_vtk_raw_alpha_m3": 3.0,
        },
        {
            "time_s": 0.21,
            "total_water_volume_vtk_m3": 9.0,
            "tank_water_volume_vtk_m3": 3.5,
            "line_water_volume_vtk_raw_alpha_m3": 2.5,
        },
    ]
    tables = {
        "total": (np.asarray([0.2]), np.asarray([9.8])),
        "tank": (np.asarray([0.2]), np.asarray([3.8])),
        "line": (np.asarray([0.2]), np.asarray([2.7])),
    }
    annotate_native_volume_comparison(rows, tables)
    assert rows[0]["tank_geometric_cylinder_mask_minus_native_zone_m3"] == pytest.approx(0.2)
    assert rows[0]["line_geometric_mask_minus_native_zone_m3"] == pytest.approx(0.3)
    assert rows[1]["native_tank_zone_water_volume_m3"] is None
    assert rows[1]["native_line_zone_water_volume_m3"] is None


def test_inventory_uses_alpha_volume_and_phase_weighted_gas_statistics() -> None:
    result = inventory_metrics(
        alpha_water=np.asarray([1.0, 0.5, 0.0, 0.25]),
        cell_volumes_m3=np.asarray([1.0, 2.0, 3.0, 4.0]),
        pressure_abs_Pa=np.asarray([100_000.0, 200_000.0, 300_000.0, 400_000.0]),
        temperature_K=np.asarray([280.0, 290.0, 300.0, 310.0]),
        centres_xyz_m=np.zeros((4, 3)),
        tank_mask=np.asarray([True, True, False, True]),
        water_density_kg_m3=1000.0,
    )
    assert result["total_water_volume_vtk_m3"] == pytest.approx(3.0)
    assert result["total_water_mass_vtk_kg"] == pytest.approx(3000.0)
    assert result["tank_water_volume_vtk_m3"] == pytest.approx(3.0)
    assert result["headspace_gas_volume_vtk_m3"] == pytest.approx(4.0)
    assert result["headspace_air_fraction_mean_volume_weighted"] == pytest.approx(4.0 / 7.0)
    assert result["headspace_pressure_gas_phase_weighted_bounded_alpha_Pa"] == pytest.approx(
        350_000.0
    )
    assert result["headspace_temperature_gas_phase_weighted_bounded_alpha_K"] == pytest.approx(
        305.0
    )


def test_inventory_reports_raw_alpha_overshoots_and_separate_bounded_inventory() -> None:
    result = inventory_metrics(
        alpha_water=np.asarray([1.2, 0.5]),
        cell_volumes_m3=np.asarray([2.0, 4.0]),
        pressure_abs_Pa=np.full(2, 100_000.0),
        temperature_K=np.full(2, 300.0),
        centres_xyz_m=np.zeros((2, 3)),
        tank_mask=np.asarray([True, True]),
        water_density_kg_m3=1000.0,
    )
    assert result["total_water_volume_vtk_m3"] == pytest.approx(4.4)
    assert result["total_water_volume_vtk_bounded_alpha_m3"] == pytest.approx(4.0)
    assert result["total_water_inventory_bounding_delta_m3"] == pytest.approx(-0.4)
    assert result["alpha_water_raw_max"] == pytest.approx(1.2)
    assert result["alpha_water_above_one_cell_count"] == 1


def test_inventory_computes_ideal_air_mass_and_cv_energy_from_all_gas_fractions() -> None:
    result = inventory_metrics(
        alpha_water=np.asarray([1.0, 0.5]),
        cell_volumes_m3=np.asarray([1.0, 2.0]),
        pressure_abs_Pa=np.asarray([100_000.0, 200_000.0]),
        temperature_K=np.asarray([300.0, 300.0]),
        centres_xyz_m=np.zeros((2, 3)),
        tank_mask=np.asarray([True, True]),
        water_density_kg_m3=1000.0,
        gas_constant_J_kg_K=200.0,
        gas_cv_J_kg_K=500.0,
    )
    expected_mass = 200_000.0 / (200.0 * 300.0)
    assert result["headspace_air_mass_ideal_gas_bounded_alpha_kg"] == pytest.approx(expected_mass)
    assert result[
        "headspace_air_sensible_internal_energy_ideal_gas_bounded_alpha_J"
    ] == pytest.approx(expected_mass * 500.0 * 300.0)
    assert result["headspace_air_temperature_ideal_mass_weighted_bounded_alpha_K"] == pytest.approx(
        300.0
    )


def test_inventory_reports_whole_domain_raw_and_bounded_gas_eos_mass() -> None:
    result = inventory_metrics(
        alpha_water=np.asarray([1.2, 0.5]),
        cell_volumes_m3=np.asarray([2.0, 4.0]),
        pressure_abs_Pa=np.asarray([100_000.0, 200_000.0]),
        temperature_K=np.asarray([300.0, 300.0]),
        centres_xyz_m=np.zeros((2, 3)),
        tank_mask=np.asarray([True, False]),
        water_density_kg_m3=1000.0,
        gas_constant_J_kg_K=200.0,
        gas_cv_J_kg_K=500.0,
    )
    # All domain cells contribute: the second cell is deliberately outside the
    # tank mask and represents line/external gas inventory.
    assert result["domain_gas_mass_ideal_gas_raw_alpha_kg"] == pytest.approx(6.0)
    assert result["domain_gas_mass_ideal_gas_bounded_alpha_kg"] == pytest.approx(20.0 / 3.0)
    assert result["domain_gas_mass_bounding_delta_kg"] == pytest.approx(2.0 / 3.0)
    assert result["domain_gas_sensible_internal_energy_ideal_gas_bounded_alpha_J"] == pytest.approx(
        (20.0 / 3.0) * 500.0 * 300.0
    )


def _analytic_gas_flux_tables(times: np.ndarray, rho_water: float = 1000.0):
    """Three signed patch fluxes whose net outward air flux is 1.3 kg/s."""
    return (
        {
            "ambientAnnulus": (times, np.ones(len(times))),
            "externalSides": (times, np.full(len(times), -0.2)),
            "outlet": (times, np.full(len(times), 0.5 + rho_water * 0.001)),
        },
        {
            "ambientAnnulus": (times, np.zeros(len(times))),
            "externalSides": (times, np.zeros(len(times))),
            "outlet": (times, np.full(len(times), 0.001)),
        },
    )


def test_native_gas_mass_ledger_closes_analytic_open_control_volume_after_late_logger_start() -> (
    None
):
    rho_water = 1000.0
    solver_times = np.asarray([0.25, 0.5, 0.75, 1.0])
    solver_dts = np.full(4, 0.25)
    # Logging starts at t=0.75, after the selected saved inventory at t=0.5.
    logged_times = solver_times[2:]
    total_mass, _ = _analytic_gas_flux_tables(logged_times, rho_water)
    _, water_volume = _analytic_gas_flux_tables(solver_times, rho_water)
    ledger = native_gas_mass_ledger(
        inventory_times_s=np.asarray([0.0, 0.5, 1.0]),
        stored_gas_mass_raw_kg=np.asarray([10.0, 9.35, 8.75]),
        stored_gas_mass_bounded_kg=np.asarray([10.0, 9.35, 8.75]),
        stored_headspace_gas_mass_bounded_kg=np.asarray([2.0, 1.9, 1.8]),
        total_mass_flux_tables=total_mass,
        water_volume_flux_tables=water_volume,
        solver_step_times_s=solver_times,
        solver_delta_t_s=solver_dts,
        water_density_kg_m3=rho_water,
        n_alpha_sub_cycles=1,
        ddt_scheme="Euler",
    )
    assert ledger["available"] is True
    assert ledger["reference_time_s"] == pytest.approx(0.5)
    assert ledger["flux_table_matching"]["outlet"]["rhoPhi_logged_row_count"] == 2
    assert ledger["flux_table_matching"]["outlet"]["alphaPhi0_water_logged_row_count"] == 4
    assert ledger["flux_table_matching"]["outlet"]["unmatched_alphaPhi0_water_row_count"] == 2
    assert ledger["unledgered_pre_reference_duration_s"] == pytest.approx(0.5)
    assert ledger["unledgered_pre_reference_gas_mass_change_kg_bounded_alpha"] == pytest.approx(
        -0.65
    )
    np.testing.assert_allclose(ledger["time_s"], [0.5, 1.0])
    np.testing.assert_allclose(
        ledger["stored_tank_headspace_gas_mass_bounded_alpha_kg"], [1.9, 1.8]
    )
    np.testing.assert_allclose(ledger["total_outward_gas_mass_flux_kg_s"], [1.3, 1.3])
    np.testing.assert_allclose(ledger["cumulative_outward_gas_mass_kg"], [0.0, 0.65])
    np.testing.assert_allclose(
        ledger["gas_mass_balance_residual_bounded_alpha_kg"], [0.0, 0.05], atol=1e-15
    )
    assert ledger["initial_domain_gas_mass_bounded_alpha_kg"] == pytest.approx(10.0)
    assert ledger["initial_tank_headspace_gas_mass_bounded_alpha_kg"] == pytest.approx(2.0)
    assert ledger["reference_tank_headspace_gas_mass_bounded_alpha_kg"] == pytest.approx(1.9)
    assert ledger["gas_mass_balance_residual_bounded_alpha_percent_reference_domain_gas_mass"][
        -1
    ] == pytest.approx(100.0 * 0.05 / 9.35)
    assert ledger["gas_mass_balance_residual_bounded_alpha_percent_initial_domain_gas_mass"][
        -1
    ] == pytest.approx(0.5)
    assert ledger[
        "gas_mass_balance_residual_bounded_alpha_percent_initial_tank_headspace_gas_mass"
    ][-1] == pytest.approx(2.5)
    assert ledger["cumulative_outward_gas_mass_by_patch_kg"]["ambientAnnulus"] == pytest.approx(
        [0.0, 0.5]
    )
    assert ledger["cumulative_outward_gas_mass_by_patch_kg"]["externalSides"] == pytest.approx(
        [0.0, -0.1]
    )
    assert ledger["cumulative_outward_gas_mass_by_patch_kg"]["outlet"] == pytest.approx([0.0, 0.25])


def test_native_gas_mass_ledger_refuses_subcycled_non_euler_and_missing_coverage() -> None:
    times = np.asarray([0.5, 1.0])
    total_mass, water_volume = _analytic_gas_flux_tables(times)
    common = {
        "inventory_times_s": times,
        "stored_gas_mass_raw_kg": np.asarray([9.35, 8.7]),
        "stored_gas_mass_bounded_kg": np.asarray([9.35, 8.7]),
        "total_mass_flux_tables": total_mass,
        "water_volume_flux_tables": water_volume,
        "solver_step_times_s": times,
        "solver_delta_t_s": np.asarray([0.5, 0.5]),
        "water_density_kg_m3": 1000.0,
    }
    subcycled = native_gas_mass_ledger(**common, n_alpha_sub_cycles=2, ddt_scheme="Euler")
    assert subcycled["available"] is False
    assert "last subcycle" in subcycled["reason"]
    non_euler = native_gas_mass_ledger(**common, n_alpha_sub_cycles=1, ddt_scheme="backward")
    assert non_euler["available"] is False
    assert "Euler" in non_euler["reason"]

    incomplete_times = np.asarray([0.25, 0.75])
    incomplete_mass, incomplete_water = _analytic_gas_flux_tables(incomplete_times)
    incomplete = native_gas_mass_ledger(
        inventory_times_s=np.asarray([0.0, 0.5, 1.0]),
        stored_gas_mass_raw_kg=np.asarray([10.0, 9.35, 8.7]),
        stored_gas_mass_bounded_kg=np.asarray([10.0, 9.35, 8.7]),
        total_mass_flux_tables=incomplete_mass,
        water_volume_flux_tables=incomplete_water,
        solver_step_times_s=np.asarray([0.25, 0.5, 0.75, 1.0]),
        solver_delta_t_s=np.full(4, 0.25),
        water_density_kg_m3=1000.0,
        n_alpha_sub_cycles=1,
        ddt_scheme="Euler",
    )
    assert incomplete["available"] is False
    assert "coverage" in incomplete["reason"]


def test_solver_step_table_pairs_logged_delta_t_with_time(tmp_path) -> None:
    log = tmp_path / "log.compressibleInterFoam.test"
    log.write_text(
        "deltaT = 1e-4\nTime = 0.0001\nsolve\ndeltaT = 2e-4\nTime = 0.0003\n",
        encoding="utf-8",
    )
    system = tmp_path / "system"
    system.mkdir()
    (system / "controlDict").write_text("timeFormat general;\ntimePrecision 8;\n", encoding="utf-8")
    parsed = solver_step_table(tmp_path)
    assert parsed["available"] is True
    np.testing.assert_allclose(parsed["time_s"], [0.0001, 0.0003])
    np.testing.assert_allclose(parsed["deltaT_s"], [0.0001, 0.0002])
    assert parsed["time_format"] == "general"
    assert parsed["time_precision"] == 8


def test_outlet_metrics_separate_forward_reverse_water_and_momentum() -> None:
    summary, profile = outlet_face_metrics(
        centres_xyz_m=np.zeros((3, 3)),
        face_areas_m2=np.asarray([1.0, 1.0, 2.0]),
        alpha_water=np.asarray([1.0, 1.0, 0.5]),
        velocity_xyz_m_s=np.asarray([[2.0, 0.0, 0.0], [-1.0, 2.0, 0.0], [3.0, 0.0, 4.0]]),
        pressure_abs_Pa=np.full(3, 100_000.0),
        temperature_K=np.full(3, 300.0),
        normal_xyz=np.asarray([2.0, 0.0, 0.0]),
        water_density_kg_m3=1000.0,
    )
    assert summary["outlet_area_m2"] == pytest.approx(4.0)
    assert summary["outlet_area_weighted_water_fraction"] == pytest.approx(0.75)
    assert summary["outlet_forward_water_volume_flux_profile_approx_m3_s"] == pytest.approx(5.0)
    assert summary["outlet_reverse_water_volume_flux_profile_approx_m3_s"] == pytest.approx(1.0)
    assert summary["outlet_reverse_face_area_fraction"] == pytest.approx(0.25)
    assert summary["outlet_mean_normal_velocity_wet_area_m_s"] == pytest.approx(1.75)
    assert summary["outlet_water_momentum_flux_x_profile_approx_N"] == pytest.approx(14_000.0)
    assert summary["outlet_water_momentum_flux_y_profile_approx_N"] == pytest.approx(-2000.0)
    assert summary["outlet_water_momentum_flux_z_profile_approx_N"] == pytest.approx(12_000.0)
    assert summary["outlet_signed_water_momentum_flux_normal_profile_approx_N"] == pytest.approx(
        14_000.0
    )
    assert summary["outlet_net_forward_water_momentum_angle_deg"] == pytest.approx(
        np.degrees(np.arctan2(12_000.0, 13_000.0))
    )
    assert profile["normal_velocity_m_s"].tolist() == [2.0, -1.0, 3.0]
    assert summary["outlet_water_flux_weighted_angle_deg"] == pytest.approx(
        (3.0 * np.degrees(np.arctan2(4.0, 3.0))) / 5.0
    )


def test_net_water_momentum_angle_cancels_opposite_lateral_faces() -> None:
    summary, profile = outlet_face_metrics(
        centres_xyz_m=np.zeros((2, 3)),
        face_areas_m2=np.ones(2),
        alpha_water=np.ones(2),
        velocity_xyz_m_s=np.asarray([[1.0, 1.0, 0.0], [1.0, -1.0, 0.0]]),
        pressure_abs_Pa=np.full(2, 100_000.0),
        temperature_K=np.full(2, 300.0),
        normal_xyz=np.asarray([1.0, 0.0, 0.0]),
        water_density_kg_m3=1000.0,
    )
    assert summary["outlet_water_flux_weighted_angle_deg"] == pytest.approx(45.0)
    assert summary["outlet_net_forward_water_momentum_angle_deg"] == pytest.approx(0.0)
    assert summary["outlet_forward_water_momentum_flux_y_profile_approx_N"] == pytest.approx(0.0)
    for axis in "xyz":
        per_face = profile[f"forward_water_momentum_flux_{axis}_approx_N_per_face"]
        total = summary[f"outlet_forward_water_momentum_flux_{axis}_profile_approx_N"]
        assert np.sum(per_face) == pytest.approx(total)


def test_net_forward_momentum_angle_is_undefined_for_all_reverse_flow() -> None:
    summary, _ = outlet_face_metrics(
        centres_xyz_m=np.zeros((2, 3)),
        face_areas_m2=np.ones(2),
        alpha_water=np.ones(2),
        velocity_xyz_m_s=np.asarray([[-1.0, 1.0, 0.0], [-1.0, -1.0, 0.0]]),
        pressure_abs_Pa=np.full(2, 100_000.0),
        temperature_K=np.full(2, 300.0),
        normal_xyz=np.asarray([1.0, 0.0, 0.0]),
        water_density_kg_m3=1000.0,
    )
    assert summary["outlet_water_flux_weighted_angle_deg"] is None
    assert summary["outlet_net_forward_water_momentum_angle_deg"] is None
    assert summary["outlet_water_momentum_flux_x_profile_approx_N"] == pytest.approx(2000.0)


def test_plane_metric_prefix_and_alpha_area_weighted_velocity_cv() -> None:
    summary, _ = outlet_face_metrics(
        centres_xyz_m=np.zeros((2, 3)),
        face_areas_m2=np.ones(2),
        alpha_water=np.asarray([1.0, 0.5]),
        velocity_xyz_m_s=np.asarray([[1.0, 0.0, 0.0], [3.0, 0.0, 0.0]]),
        pressure_abs_Pa=np.full(2, 100_000.0),
        temperature_K=np.full(2, 300.0),
        metric_prefix="nozzle_internal",
    )
    assert summary["nozzle_internal_area_m2"] == pytest.approx(2.0)
    assert summary["nozzle_internal_mean_normal_velocity_alpha_area_m_s"] == pytest.approx(5 / 3)
    assert summary["nozzle_internal_cv_normal_velocity_alpha_area"] == pytest.approx(
        np.sqrt(8.0 / 9.0) / (5.0 / 3.0)
    )
    assert summary["nozzle_internal_cv_normal_velocity_wet_area"] == pytest.approx(0.5)


def test_section_profile_flux_is_area_integral_and_keeps_reverse_sign() -> None:
    result = section_profile_metrics(
        x_m=3.0,
        cell_areas_m2=np.asarray([0.2, 0.3]),
        alpha_water=np.asarray([1.0, 0.5]),
        pressure_abs_Pa=np.asarray([200_000.0, 100_000.0]),
        temperature_K=np.asarray([290.0, 300.0]),
        velocity_xyz_m_s=np.asarray([[2.0, 0.0, 0.0], [-4.0, 0.0, 0.0]]),
    )
    assert result["water_volume_flux_approx_m3_s"] == pytest.approx(0.4 - 0.6)
    assert result["reverse_water_volume_flux_approx_m3_s"] == pytest.approx(-0.6)
    assert result["wet_area_fraction_alpha_ge_0p5"] == pytest.approx(1.0)


def test_nominal_section_area_checks_pipe_and_linear_transition_geometry() -> None:
    config = {
        "tank": {"start_x_m": 0.0, "length_m": 2.0},
        "pipe": {"diameter_m": 0.25, "length_m": 1.0, "transition_length_m": 1.5},
        "nozzle": {"width_m": 1.0, "height_m": 0.15},
    }
    pipe_area = np.pi * 0.25**2 / 4.0
    assert nominal_section_area_m2(2.6, config) == pytest.approx(pipe_area)
    assert nominal_section_area_m2(3.75, config) == pytest.approx((pipe_area + 0.15) / 2.0)
    assert nominal_section_area_m2(4.49, config) == pytest.approx(
        pipe_area + (1.49 / 1.5) * (0.15 - pipe_area)
    )
    assert nominal_section_area_m2(5.5, config) is None


def test_native_flux_ledger_requires_every_open_boundary_and_closes_analytic_history() -> None:
    times = np.asarray([0.0, 1.0, 2.0])
    fluxes = {
        patch: (times, np.asarray([1.0, 1.0, 1.0]) if patch == "outlet" else np.zeros(3))
        for patch in OPEN_PATCHES
    }
    ledger = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=np.asarray([10.0, 9.0, 8.0]),
        flux_tables=fluxes,
        solver_step_times_s=times[1:],
        solver_delta_t_s=np.diff(times),
    )
    assert ledger["available"] is True
    assert ledger["cumulative_net_outward_water_volume_m3"] == pytest.approx(2.0)
    assert ledger["max_absolute_water_volume_balance_residual_m3"] == pytest.approx(0.0)

    missing = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=np.asarray([10.0, 9.0, 8.0]),
        flux_tables={"outlet": fluxes["outlet"]},
        solver_step_times_s=times[1:],
        solver_delta_t_s=np.diff(times),
    )
    assert missing["available"] is False
    assert set(missing["missing_open_patches"]) == set(OPEN_PATCHES) - {"outlet"}


def test_native_flux_ledger_uses_euler_right_endpoint_without_startup_inference() -> None:
    times = np.asarray([1.0, 2.0, 3.0])
    fluxes = {
        patch: (
            times,
            np.asarray([99.0, 2.0, 3.0]) if patch == "outlet" else np.zeros(3),
        )
        for patch in OPEN_PATCHES
    }
    ledger = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=np.asarray([10.0, 8.0, 5.0]),
        flux_tables=fluxes,
        solver_step_times_s=times[1:],
        solver_delta_t_s=np.diff(times),
    )
    assert ledger["available"] is True
    assert ledger["cumulative_outward_water_volume_m3"] == pytest.approx([0.0, 2.0, 5.0])
    assert ledger["water_volume_balance_residual_m3"] == pytest.approx([0.0, 0.0, 0.0])
    assert ledger["startup_interval_before_first_logged_flux_integrated"] is False


def test_native_flux_ledger_weights_nonuniform_steps_by_logged_delta_t() -> None:
    inventory_times = np.asarray([0.0, 0.4, 1.0])
    flux_times = np.asarray([0.0, 0.1, 0.2, 0.4, 0.7, 1.0])
    solver_times = flux_times[1:]
    solver_dt = np.asarray([0.1, 0.1, 0.2, 0.3, 0.3])
    fluxes = {
        patch: (
            flux_times,
            np.ones(len(flux_times)) if patch == "outlet" else np.zeros(len(flux_times)),
        )
        for patch in OPEN_PATCHES
    }
    ledger = native_flux_ledger(
        volume_times_s=inventory_times,
        stored_water_volume_m3=np.asarray([10.0, 9.6, 9.0]),
        flux_tables=fluxes,
        solver_step_times_s=solver_times,
        solver_delta_t_s=solver_dt,
    )
    assert ledger["available"] is True
    np.testing.assert_allclose(ledger["native_flux_step_deltaT_s"], solver_dt)
    np.testing.assert_allclose(ledger["cumulative_outward_water_volume_m3"], [0.0, 0.4, 1.0])
    np.testing.assert_allclose(
        ledger["water_volume_balance_residual_m3"], [0.0, 0.0, 0.0], atol=1e-14
    )


def test_time_precision_rounding_is_allowed_without_hiding_missing_endpoints() -> None:
    # OpenFOAM general/8 output rounds each of these printed Time endpoints to
    # 1e-8 s. The adjacent-time error can therefore reach 1e-8 s even while the
    # solver deltaT and every native flux row are valid.
    times = np.asarray([0.38682272, 0.38684178, 0.38686083])
    solver_dt = np.asarray([1.9069877e-5, 1.9042279e-5])
    first_printed_interval = times[1] - times[0]
    first_error = abs(first_printed_interval - solver_dt[0])
    existing_tolerance = max(2e-9, 5e-4 * max(first_printed_interval, solver_dt[0]))
    assert first_error > existing_tolerance
    assert first_error <= 1e-8

    fluxes = {
        patch: (
            times,
            np.asarray([0.0, 1.0, 1.0]) if patch == "outlet" else np.zeros(3),
        )
        for patch in OPEN_PATCHES
    }
    stored_water = np.asarray([10.0, 10.0 - solver_dt[0], 10.0 - np.sum(solver_dt)])
    water = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=stored_water,
        flux_tables=fluxes,
        solver_step_times_s=times[1:],
        solver_delta_t_s=solver_dt,
        solver_time_format="general",
        solver_time_precision=8,
    )
    assert water["available"] is True
    assert water["solver_step_endpoint_coverage_complete"] is True
    assert water["water_volume_balance_residual_m3"][-1] == pytest.approx(0.0, abs=1e-14)

    # Missing the first logged native endpoint remains unavailable even though
    # the later endpoint itself is inside the formatting tolerance.
    missing_fluxes = {
        patch: (times[[0, 2]], values[[0, 2]]) for patch, (_, values) in fluxes.items()
    }
    missing = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=stored_water,
        flux_tables=missing_fluxes,
        solver_step_times_s=times[1:],
        solver_delta_t_s=solver_dt,
        solver_time_format="general",
        solver_time_precision=8,
    )
    assert missing["available"] is False

    mass_fluxes = {
        patch: (
            times,
            np.asarray([0.0, 1.0, 1.0]) if patch == "outlet" else np.zeros(3),
        )
        for patch in OPEN_PATCHES
    }
    gas = native_gas_mass_ledger(
        inventory_times_s=times,
        stored_gas_mass_raw_kg=stored_water,
        stored_gas_mass_bounded_kg=stored_water,
        total_mass_flux_tables=mass_fluxes,
        water_volume_flux_tables={patch: (times, np.zeros(3)) for patch in OPEN_PATCHES},
        solver_step_times_s=times[1:],
        solver_delta_t_s=solver_dt,
        water_density_kg_m3=998.2,
        solver_time_format="general",
        solver_time_precision=8,
    )
    assert gas["available"] is True
    assert gas["flux_interval_coverage_complete_from_reference_time"] is True
    assert gas["gas_mass_balance_residual_bounded_alpha_kg"][-1] == pytest.approx(0.0, abs=1e-14)


def test_native_flux_ledger_rejects_missing_internal_solver_endpoint() -> None:
    sparse_times = np.asarray([0.0, 2.0])
    sparse_fluxes = {patch: (sparse_times, np.zeros(2)) for patch in OPEN_PATCHES}
    ledger = native_flux_ledger(
        volume_times_s=sparse_times,
        stored_water_volume_m3=np.asarray([10.0, 10.0]),
        flux_tables=sparse_fluxes,
        solver_step_times_s=np.asarray([1.0, 2.0]),
        solver_delta_t_s=np.asarray([1.0, 1.0]),
    )
    assert ledger["available"] is False
    assert ledger["conservative_ledger_available"] is False
    assert "every solver right-endpoint" in ledger["reason"]


def test_scalar_log_parser_retains_nonfinite_value_and_water_ledger_refuses_it(tmp_path) -> None:
    log = tmp_path / "outlet.dat"
    log.write_text("# Time sum\n0 0\n1 nan\n2 0\n", encoding="utf-8")
    times, values = parse_scalar_table(log)
    np.testing.assert_allclose(times, [0.0, 1.0, 2.0])
    assert np.isnan(values[1])
    fluxes = {
        patch: (times, values if patch == "outlet" else np.zeros(len(times)))
        for patch in OPEN_PATCHES
    }
    ledger = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=np.asarray([10.0, 10.0, 10.0]),
        flux_tables=fluxes,
        solver_step_times_s=times[1:],
        solver_delta_t_s=np.diff(times),
    )
    assert ledger["available"] is False
    assert "finite" in ledger["reason"]


def test_scalar_log_parser_keeps_nonfinite_duplicate_time_for_rejection(tmp_path) -> None:
    log = tmp_path / "outlet.dat"
    log.write_text("# Time sum\n0 0\n1 1\n1 nan\n2 0\n", encoding="utf-8")
    times, values = parse_scalar_table(log)
    np.testing.assert_allclose(times, [0.0, 1.0, 1.0, 2.0])
    assert np.isnan(values[2])


def test_matched_checkpoint_normalizations_use_initial_inventory_and_tank_drawdown() -> None:
    times = np.asarray([0.0, 1.0, 2.0])
    fluxes = {
        patch: (
            times,
            np.asarray([0.0, 0.55, 0.5]) if patch == "outlet" else np.zeros(3),
        )
        for patch in OPEN_PATCHES
    }
    ledger = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=np.asarray([10.0, 9.5, 9.0]),
        flux_tables=fluxes,
        solver_step_times_s=times[1:],
        solver_delta_t_s=np.diff(times),
    )
    tank_table = (times, np.asarray([5.0, 4.5, 4.0]))
    annotate_native_water_ledger_normalizations(ledger, tank_table)
    rows = [
        {
            "time_s": 0.0,
            "native_total_region_water_volume_m3": 10.0,
            "headspace_air_mass_ideal_gas_bounded_alpha_kg": 4.0,
        },
        {
            "time_s": 2.0,
            "native_total_region_water_volume_m3": 9.0,
            "headspace_air_mass_ideal_gas_bounded_alpha_kg": 3.96,
        },
    ]
    annotate_gas_mass_normalization(rows)
    checkpoint = matched_checkpoint_normalizations(rows, ledger)
    assert ledger["balance_residual_fraction_initial_total_water_percent"] == pytest.approx(
        [0.0, 0.5, 0.5]
    )
    assert ledger["balance_residual_fraction_tank_drawdown_percent"][0] is None
    np.testing.assert_allclose(
        ledger["balance_residual_fraction_tank_drawdown_percent"][1:], [10.0, 5.0]
    )
    assert [row["time_s"] for row in checkpoint] == [0.0, 2.0]
    assert checkpoint[0]["residual_percent_of_tank_drawdown"] is None
    assert checkpoint[1]["tank_drawdown_from_first_ledger_time_m3"] == pytest.approx(1.0)
    assert checkpoint[1]["native_ledger_balance_residual_m3"] == pytest.approx(0.05)
    assert checkpoint[1]["residual_percent_of_initial_total_water"] == pytest.approx(0.5)
    assert checkpoint[1]["residual_percent_of_tank_drawdown"] == pytest.approx(5.0)
    assert checkpoint[1]["ideal_air_mass_kg"] == pytest.approx(3.96)
    assert checkpoint[1]["ideal_air_mass_change_from_first_saved_percent"] == pytest.approx(-1.0)


def test_native_flux_ledger_is_limited_to_last_saved_field_time() -> None:
    times = np.asarray([0.0, 1.0, 2.0, 3.0])
    fluxes = {
        patch: (times, np.asarray([0.0, 1.0, 2.0, 3.0]) if patch == "outlet" else np.zeros(4))
        for patch in OPEN_PATCHES
    }
    ledger = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=np.asarray([10.0, 9.0, 7.0, 4.0]),
        flux_tables=fluxes,
        solver_step_times_s=times[1:],
        solver_delta_t_s=np.diff(times),
        end_time_limit_s=2.0,
    )
    assert ledger["available"] is True
    assert ledger["time_s"] == pytest.approx([0.0, 1.0, 2.0])
    assert ledger["analysis_end_time_limit_s"] == 2.0
    assert ledger["cumulative_outward_water_volume_m3"] == pytest.approx([0.0, 1.0, 3.0])


def test_native_flux_ledger_refuses_last_subcycle_as_full_step_flux() -> None:
    times = np.asarray([0.0, 1.0, 2.0])
    fluxes = {
        patch: (times, np.ones(3) if patch == "outlet" else np.zeros(3)) for patch in OPEN_PATCHES
    }
    result = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=np.asarray([10.0, 9.0, 8.0]),
        flux_tables=fluxes,
        n_alpha_sub_cycles=2,
        ddt_scheme="Euler",
    )
    assert result["available"] is False
    assert result["diagnostic_available"] is True
    assert result["conservative_ledger_available"] is False
    assert "last alpha subcycle" in result["reason"]


def test_native_flux_ledger_refuses_unaligned_inventory_or_non_euler_time_scheme() -> None:
    times = np.asarray([0.0, 1.0, 2.0])
    fluxes = {
        patch: (times, np.ones(3) if patch == "outlet" else np.zeros(3)) for patch in OPEN_PATCHES
    }
    unaligned = native_flux_ledger(
        volume_times_s=np.asarray([0.0, 1.1, 2.0]),
        stored_water_volume_m3=np.asarray([10.0, 9.0, 8.0]),
        flux_tables=fluxes,
        solver_step_times_s=times[1:],
        solver_delta_t_s=np.diff(times),
    )
    assert unaligned["available"] is False
    assert unaligned["conservative_ledger_available"] is False
    assert "no exact native flux endpoint" in unaligned["reason"]

    non_euler = native_flux_ledger(
        volume_times_s=times,
        stored_water_volume_m3=np.asarray([10.0, 9.0, 8.0]),
        flux_tables=fluxes,
        ddt_scheme="backward",
    )
    assert non_euler["available"] is False
    assert non_euler["conservative_ledger_available"] is False


def test_solver_time_controls_detect_subcycles_and_euler(tmp_path) -> None:
    system = tmp_path / "system"
    system.mkdir()
    (system / "fvSolution").write_text("alpha { nAlphaSubCycles 2; }\n", encoding="utf-8")
    (system / "fvSchemes").write_text("ddtSchemes { default Euler; }\n", encoding="utf-8")
    controls = solver_time_controls(tmp_path)
    assert controls["n_alpha_sub_cycles"] == 2
    assert controls["n_alpha_sub_cycles_source"] == "system/fvSolution"
    assert controls["ddt_scheme"] == "Euler"


def test_line_box_mask_and_openfoam_gas_cv_reader(tmp_path) -> None:
    config = {
        "tank": {"start_x_m": 0.0, "length_m": 2.0},
        "connection": {"center_z_m": 0.65},
        "pipe": {"diameter_m": 0.25, "length_m": 1.0, "transition_length_m": 1.5},
        "nozzle": {"width_m": 1.0, "height_m": 0.15, "center_z_m": 0.65},
    }
    points = np.asarray([[2.2, 0.0, 0.65], [4.49, 0.50, 0.65], [4.6, 0.0, 0.65]])
    np.testing.assert_array_equal(line_cell_mask(points, config), [True, True, False])

    (tmp_path / "constant").mkdir()
    thermo = tmp_path / "constant/thermophysicalProperties.air"
    thermo.write_text("thermodynamics { Cp 1005; }\n", encoding="utf-8")
    r_gas, cv, source = gas_thermo_properties(tmp_path, "air")
    assert r_gas == pytest.approx(287.05)
    assert cv == pytest.approx(717.95)
    assert source == str(thermo)


def test_exact_function_value_requires_timestamp_match() -> None:
    table = (np.asarray([0.1, 0.2]), np.asarray([3.0, 4.0]))
    assert exact_function_value(table, 0.2) == pytest.approx((4.0, 0.0))
    assert exact_function_value(table, 0.205)[0] is None


def test_native_mixture_mass_minus_water_crosschecks_eos_gas_storage() -> None:
    rows = [
        {"time_s": 0.1, "domain_gas_mass_ideal_gas_bounded_alpha_kg": 500.0},
        {"time_s": 0.2, "domain_gas_mass_ideal_gas_bounded_alpha_kg": 690.0},
        {"time_s": 0.3, "domain_gas_mass_ideal_gas_bounded_alpha_kg": 900.0},
    ]
    mixture_mass = (np.asarray([0.1, 0.2]), np.asarray([10_000.0, 10_100.0]))
    water_volume = (np.asarray([0.1, 0.2]), np.asarray([9.5, 9.4]))
    summary = annotate_native_mixture_gas_storage(rows, mixture_mass, water_volume, 1000.0)
    assert summary["available"] is True
    assert summary["matched_field_time_count"] == 2
    assert summary["max_absolute_eos_minus_native_mixture_gas_mass_kg"] == pytest.approx(10.0)
    assert rows[0]["native_gas_mass_from_mixture_minus_water_kg"] == pytest.approx(500.0)
    assert rows[0]["eos_minus_native_mixture_gas_mass_kg"] == pytest.approx(0.0)
    assert rows[1]["eos_minus_native_mixture_gas_mass_kg"] == pytest.approx(-10.0)
    assert rows[2]["native_gas_mass_from_mixture_minus_water_kg"] is None


def test_find_function_table_accepts_v2512_mixture_mass_flux_alias(tmp_path) -> None:
    table = tmp_path / "postProcessing/outletMixtureMassFlux/0/surfaceFieldValue.dat"
    table.parent.mkdir(parents=True)
    table.write_text("# Time sum\n0.1 2.0\n", encoding="utf-8")
    assert (
        find_function_table(
            tmp_path,
            ("outletTotalMassFlux", "outletMixtureMassFlux"),
            "surfaceFieldValue.dat",
        )
        == table
    )


def test_weighted_quantile_and_scalar_function_log_parser(tmp_path) -> None:
    assert weighted_quantile(np.asarray([1, 4, 2]), np.asarray([1, 2, 1]), 0.5) == 2.0
    assert weighted_quantile(np.asarray([1, 4]), np.asarray([0, 0]), 0.5) is None

    log = tmp_path / "values.dat"
    log.write_text("# Time value\n0 10\n1 9\n1 8\n2 7\n", encoding="utf-8")
    times, values = parse_scalar_table(log)
    np.testing.assert_allclose(times, [0, 1, 2])
    np.testing.assert_allclose(values, [10, 9, 7])
