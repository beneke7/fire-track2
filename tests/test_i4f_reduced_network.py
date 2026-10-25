"""Small analytical and conservation checks for the two-branch I4F model."""

from __future__ import annotations

import numpy as np
import pytest

from aerial_drop.i4f_reduced import inertial_flow_midpoint_step
from aerial_drop.i4f_reduced import simulate as simulate_legacy
from aerial_drop.i4f_reduced_network import (
    BranchParameters,
    GasProperties,
    HydraulicSection,
    LiquidProperties,
    NetworkParameters,
    TankProperties,
    _solve_branch_midpoint,
    branch_inertial_midpoint_step,
    simulate_parallel_branches,
)


def _circular_section(name: str, length: float, diameter: float) -> HydraulicSection:
    area = np.pi * diameter**2 / 4.0
    return HydraulicSection(name, length, area, area, diameter, diameter)


def _gas(*, pressure: float = 300_000.0, ambient: float = 100_000.0) -> GasProperties:
    return GasProperties("air", pressure, ambient, 293.15, 1.25)


def _liquid() -> LiquidProperties:
    return LiquidProperties(998.2, 0.001002, 9.81)


def _simple_network(branches: tuple[BranchParameters, ...]) -> NetworkParameters:
    return NetworkParameters(
        tank=TankProperties("vertical", 0.6, 1.0, 1.0, 0.7),
        gas=_gas(),
        liquid=_liquid(),
        branches=branches,
    )


def test_single_branch_midpoint_matches_existing_inertial_kernel() -> None:
    section = _circular_section("pipe", 0.05, 0.08)
    branch = BranchParameters(
        "single",
        intake_center_z_m=0.75,
        intake_diameter_m=0.08,
        outlet_center_z_m=0.6,
        sections=(section,),
        valve_Cd=0.8,
        valve_opening_time_s=0.0,
        entrance_loss_K=0.3,
        transition_loss_K=0.2,
    )
    liquid = _liquid()
    q0, dt, drive = 0.0, 1.0e-5, 100.0
    inertance = branch.inertance_kg_m4(liquid)
    area = section.area_start_m2
    # This low-flow state is in the laminar pipe limit. The outlet and scalar
    # K terms are exactly quadratic in Q and use the same reference area.
    r1 = 128.0 * liquid.dynamic_viscosity_Pa_s * section.length_m / (np.pi * 0.08**4)
    valve_k = 1.0 / branch.valve_Cd**2
    r2 = (
        0.5
        * liquid.density_kg_m3
        * ((valve_k + branch.entrance_loss_K + branch.transition_loss_K + 1.0) / area**2)
    )
    expected_mid, expected_new = inertial_flow_midpoint_step(q0, dt, inertance, drive, r1, r2)
    actual_mid, actual_new = _solve_branch_midpoint(branch, liquid, q0, dt, inertance, drive, 1.0)
    assert actual_mid == pytest.approx(expected_mid, rel=2e-10, abs=1e-16)
    assert actual_new == pytest.approx(expected_new, rel=2e-10, abs=1e-16)


def test_single_branch_trajectory_matches_legacy_constant_area_limit() -> None:
    diameter = 0.10
    area = np.pi * diameter**2 / 4.0
    nozzle_height = area / diameter
    config = {
        "tank": {
            "axis": "horizontal",
            "diameter_m": 10.0,
            "length_m": 20.0,
            "center_z_m": 0.0,
            "fill_fraction": 0.7,
        },
        "connection": {"center_z_m": 0.0, "upper_edge_z_m": -1.95},
        "pipe": {
            "diameter_m": diameter,
            "length_m": 1.0,
            "transition_length_m": 1.0e-8,
            "roughness_m": 1.0e-5,
            "entrance_K": 0.5,
            "transition_K": 0.2,
        },
        "nozzle": {"width_m": diameter, "height_m": nozzle_height, "center_z_m": 0.0},
        "gas": {
            "mode": "sealed",
            "kind": "air",
            "initial_absolute_pressure_Pa": 300_000.0,
            "ambient_pressure_Pa": 100_000.0,
            "temperature_K": 293.15,
            "polytropic_n": 1.25,
        },
        "liquid": {"density_kg_m3": 998.2, "dynamic_viscosity_Pa_s": 0.001002},
        "gravity_m_s2": 9.81,
        "valve": {
            "opening_time_s": 0.5,
            "Cd": 0.7,
            "opening_law": "smoothstep",
            "minimum_effective_opening": 0.02,
        },
    }
    branch = BranchParameters(
        "one",
        intake_center_z_m=-2.0,
        intake_diameter_m=diameter,
        outlet_center_z_m=0.0,
        sections=(
            _circular_section("pipe", 1.0, diameter),
            _circular_section("transition", 1.0e-8, diameter),
        ),
        valve_Cd=0.7,
        valve_opening_time_s=0.5,
        valve_minimum_effective_opening=0.02,
        entrance_loss_K=0.5,
        transition_loss_K=0.2,
    )
    network = NetworkParameters(
        TankProperties("horizontal", 10.0, 20.0, 0.0, 0.7),
        _gas(pressure=300_000.0),
        _liquid(),
        (branch,),
    )
    dt = 1.0e-4
    new_result = simulate_parallel_branches(network, time_step_s=dt, max_time_s=0.005)
    old_result = simulate_legacy(config, time_step_s=dt, max_time_s=0.005)
    new_q = new_result.samples["total_flow_rate_m3_s"]
    old_q = old_result.samples["flow_rate_m3_s"]
    assert np.array_equal(new_result.samples["time_s"], old_result.samples["time_s"])
    assert np.allclose(new_q, old_q, rtol=5e-4, atol=1e-10)
    assert np.allclose(
        new_result.samples["gas_pressure_abs_Pa"],
        old_result.samples["gas_pressure_abs_Pa"],
        rtol=1e-10,
        atol=1e-5,
    )


def test_inviscid_fixed_head_midpoint_matches_analytic_acceleration() -> None:
    q0 = 0.0
    dt = 0.02
    inertance = 2400.0
    drive = 12_000.0
    q_mid, q_new = branch_inertial_midpoint_step(q0, dt, inertance, drive, 0.0, 0.0)
    assert q_new == pytest.approx(drive * dt / inertance, rel=1e-14)
    assert q_mid == pytest.approx(0.5 * drive * dt / inertance, rel=1e-14)


def test_identical_parallel_branches_share_tank_and_have_equal_flow() -> None:
    branch_a = BranchParameters(
        "a",
        0.8,
        0.08,
        0.55,
        (_circular_section("pipe", 0.5, 0.08),),
        0.8,
        0.02,
        valve_minimum_effective_opening=0.02,
        entrance_loss_K=0.2,
        transition_loss_K=0.1,
    )
    branch_b = BranchParameters(
        "b",
        0.8,
        0.08,
        0.55,
        (_circular_section("pipe", 0.5, 0.08),),
        0.8,
        0.02,
        valve_minimum_effective_opening=0.02,
        entrance_loss_K=0.2,
        transition_loss_K=0.1,
    )
    result = simulate_parallel_branches(
        _simple_network((branch_a, branch_b)), time_step_s=5.0e-4, max_time_s=0.1
    )
    samples = result.samples
    assert np.allclose(
        samples["flow_rate_a_m3_s"], samples["flow_rate_b_m3_s"], rtol=0.0, atol=2e-12
    )
    assert np.allclose(
        samples["total_flow_rate_m3_s"],
        samples["flow_rate_a_m3_s"] + samples["flow_rate_b_m3_s"],
        rtol=0.0,
        atol=2e-12,
    )
    assert np.max(np.abs(samples["total_water_balance_residual_m3"])) < 2e-14
    assert np.max(np.abs(samples["last_step_midpoint_momentum_residual_a_Pa"][1:])) < 2e-7
    assert np.max(np.abs(samples["last_step_midpoint_momentum_residual_b_Pa"][1:])) < 2e-7
    for name in ("a", "b"):
        inertia_key = f"last_step_midpoint_inertance_pressure_{name}_Pa"
        valve_key = f"last_step_midpoint_pressure_valve_Pa_{name}"
        assert np.isnan(samples[inertia_key][0])
        assert np.all(np.isfinite(samples[inertia_key][1:]))
        assert np.isnan(samples[valve_key][0])
        assert np.all(np.isfinite(samples[valve_key][1:]))
    assert result.initial_line_water_volume_m3 == pytest.approx(
        branch_a.initial_line_water_volume_m3 + branch_b.initial_line_water_volume_m3
    )


def test_model_stops_at_highest_intake_crown_and_closes_water_ledger() -> None:
    branch = BranchParameters(
        "one",
        intake_center_z_m=0.60,
        intake_diameter_m=0.10,
        outlet_center_z_m=0.35,
        sections=(_circular_section("pipe", 0.05, 0.40),),
        valve_Cd=0.9,
        valve_opening_time_s=0.0,
        entrance_loss_K=0.0,
        transition_loss_K=0.0,
    )
    tank = TankProperties("vertical", 0.6, 1.0, 1.0, 0.7)
    gas = _gas(pressure=1_000_000.0)
    params = NetworkParameters(tank, gas, _liquid(), (branch,))
    result = simulate_parallel_branches(params, time_step_s=1e-3, max_time_s=0.5)
    assert "highest submerged-intake crown" in result.stop_reason
    assert result.samples["tank_free_surface_level_z_m"][-1] == pytest.approx(
        branch.intake_crown_z_m, abs=2e-11
    )
    assert result.max_mass_balance_error_m3 < 2e-14
    assert np.all(np.diff(result.samples["cumulative_discharge_volume_m3"]) >= 0)
    assert result.samples["gas_pressure_abs_Pa"][-1] < result.samples["gas_pressure_abs_Pa"][0]


def test_timestep_refinement_stabilizes_crown_event_time() -> None:
    branch = BranchParameters(
        "one",
        intake_center_z_m=0.60,
        intake_diameter_m=0.10,
        outlet_center_z_m=0.35,
        sections=(_circular_section("pipe", 0.05, 0.40),),
        valve_Cd=0.9,
        valve_opening_time_s=0.0,
        entrance_loss_K=0.0,
        transition_loss_K=0.0,
    )
    params = NetworkParameters(
        TankProperties("vertical", 0.6, 1.0, 1.0, 0.7),
        _gas(pressure=500_000.0),
        _liquid(),
        (branch,),
    )
    coarse = simulate_parallel_branches(params, time_step_s=2e-3, max_time_s=2.0)
    fine = simulate_parallel_branches(params, time_step_s=1e-3, max_time_s=2.0)
    assert "highest submerged-intake crown" in coarse.stop_reason
    assert "highest submerged-intake crown" in fine.stop_reason
    assert coarse.stop_time_s == pytest.approx(fine.stop_time_s, rel=2e-3)
    assert coarse.samples["total_flow_rate_m3_s"][-1] == pytest.approx(
        fine.samples["total_flow_rate_m3_s"][-1], rel=3e-2
    )


def test_reverse_flow_is_an_explicit_stop_not_a_clamped_discharge() -> None:
    branch = BranchParameters(
        "reverse",
        intake_center_z_m=0.7,
        intake_diameter_m=0.1,
        outlet_center_z_m=2.0,
        sections=(_circular_section("pipe", 0.2, 0.1),),
        valve_Cd=0.8,
        valve_opening_time_s=0.0,
        valve_minimum_effective_opening=1.0,
    )
    params = NetworkParameters(
        TankProperties("vertical", 0.6, 1.0, 1.0, 0.7),
        _gas(pressure=100_000.0),
        _liquid(),
        (branch,),
    )
    result = simulate_parallel_branches(params, time_step_s=1e-3, max_time_s=0.2)
    assert "stopped before predicted reverse flow" in result.stop_reason
    assert result.stop_time_s == 0.0
    assert result.samples["flow_rate_reverse_m3_s"][-1] == 0.0
    assert result.samples["cumulative_discharge_volume_m3"][-1] == 0.0


def test_initially_exposed_high_intake_is_rejected() -> None:
    upper = BranchParameters(
        "upper",
        intake_center_z_m=0.9938750305,
        intake_diameter_m=0.30,
        outlet_center_z_m=0.90,
        sections=(_circular_section("pipe", 0.5, 0.30),),
        valve_Cd=0.7,
        valve_opening_time_s=0.5,
        valve_minimum_effective_opening=0.02,
    )
    # This generic high-crown case checks startup validation. It is not the
    # exact generated-preview wall aperture or a claim about measured hardware.
    tank = TankProperties("horizontal", 0.9, 3.1, 1.25, 0.3422686948)
    with pytest.raises(ValueError, match="already at/below the highest intake crown"):
        simulate_parallel_branches(
            NetworkParameters(tank, _gas(), _liquid(), (upper,)),
            time_step_s=1e-3,
            max_time_s=1.0,
        )
