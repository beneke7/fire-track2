"""Analytical and ledger checks for the initially dry I4F branch model."""

from __future__ import annotations

import numpy as np
import pytest

from aerial_drop.i4f_filling_network import (
    FillingBranch,
    FillingNetworkParameters,
    _air_diagnostics,
    simulate_filling,
)
from aerial_drop.i4f_reduced import R_AIR_J_KG_K, tank_level_z_m, tank_volume_at_level_m3
from aerial_drop.i4f_reduced_network import (
    BranchParameters,
    GasProperties,
    HydraulicSection,
    LiquidProperties,
    NetworkParameters,
    TankProperties,
    simulate_parallel_branches,
)


def _make_branch(
    name: str,
    *,
    length_m: float = 0.5,
    area_m2: float = 0.01,
    initial_front_s_m: float = 0.1,
    valve_cd: float = 0.8,
    transition_loss_k: float = 0.0,
    entrance_loss_k: float = 0.0,
    opening_time_s: float = 0.0,
    elevation_m: float = 0.0,
    air_minor_loss_k: float | None = 0.0,
) -> tuple[BranchParameters, FillingBranch]:
    diameter = np.sqrt(4.0 * area_m2 / np.pi)
    section = HydraulicSection(
        "pipe",
        length_m,
        area_m2,
        area_m2,
        diameter,
        diameter,
        0.0,
    )
    base = BranchParameters(
        name=name,
        intake_center_z_m=elevation_m,
        intake_diameter_m=diameter,
        outlet_center_z_m=elevation_m,
        sections=(section,),
        valve_Cd=valve_cd,
        valve_opening_time_s=opening_time_s,
        valve_opening_law="linear",
        valve_minimum_effective_opening=1.0 if opening_time_s == 0 else 0.02,
        entrance_loss_K=entrance_loss_k,
        transition_loss_K=transition_loss_k,
    )
    filling = FillingBranch(
        base,
        (elevation_m, elevation_m),
        initial_front_s_m,
        transition_start_s_m=0.0 if transition_loss_k > 0 else None,
        transition_end_s_m=0.0 if transition_loss_k > 0 else None,
        air_minor_loss_K=air_minor_loss_k,
    )
    return base, filling


def _make_params(
    filling_branches: tuple[FillingBranch, ...],
    *,
    fill_fraction: float = 0.7,
    p0_pa: float = 300_000.0,
    ambient_pa: float = 100_000.0,
) -> FillingNetworkParameters:
    base_branches = tuple(item.branch for item in filling_branches)
    tank = TankProperties("vertical", 0.6, 1.0, 0.0, fill_fraction)
    gas = GasProperties("air", p0_pa, ambient_pa, 293.15, 1.0)
    liquid = LiquidProperties(998.2, 0.001002, 9.81)
    network = NetworkParameters(tank, gas, liquid, base_branches)
    return FillingNetworkParameters(network, filling_branches)


def test_euler_startup_acceleration_uses_nonzero_wet_column_and_front_head() -> None:
    base, filling = _make_branch("single", length_m=1.0, area_m2=0.01, initial_front_s_m=0.2)
    params = _make_params((filling,), p0_pa=300_000.0)
    dt = 1.0e-7
    result = simulate_filling(params, time_step_s=dt, max_time_s=dt)
    rho = params.liquid.density_kg_m3
    initial_water = result.initial_tank_water_volume_m3
    tank_level = tank_level_z_m(params.tank, initial_water)
    p_drive = (
        params.gas.initial_pressure_abs_Pa
        - params.gas.ambient_pressure_Pa
        + rho * params.liquid.gravity_m_s2 * (tank_level - filling.elevation_at_s(0.2))
    )
    inertance = rho * (0.2 / 0.01)
    expected_qdot = p_drive / inertance
    observed_qdot = result.samples["flow_single_m3_s"][1] / dt
    assert observed_qdot == pytest.approx(expected_qdot, rel=2e-6)
    assert filling.inertance_integral_to_s(0.2) > 0


def test_water_ledger_closes_and_outlet_is_dry_before_front_arrives() -> None:
    _, filling = _make_branch("single", length_m=1.0, area_m2=0.01, initial_front_s_m=0.2)
    result = simulate_filling(_make_params((filling,)), time_step_s=1.0e-5, max_time_s=0.01)
    samples = result.samples
    assert np.max(np.abs(samples["water_volume_balance_residual_m3"])) < 2e-13
    assert np.all(samples["outlet_flow_single_m3_s"] == 0.0)
    assert np.all(samples["total_external_water_volume_m3"] == 0.0)
    assert np.all(samples["front_s_single_m"] < filling.length_m)


def test_identical_branches_remain_symmetric_with_shared_headspace() -> None:
    _, first = _make_branch("first", initial_front_s_m=0.1)
    _, second = _make_branch("second", initial_front_s_m=0.1)
    result = simulate_filling(_make_params((first, second)), time_step_s=1.0e-5, max_time_s=0.002)
    assert np.allclose(
        result.samples["flow_first_m3_s"],
        result.samples["flow_second_m3_s"],
        rtol=0.0,
        atol=2e-13,
    )
    assert np.max(np.abs(result.samples["water_volume_balance_residual_m3"])) < 2e-13


def test_centerline_elevation_profile_overrides_lumped_hydraulic_section() -> None:
    _, base = _make_branch("profiled", length_m=1.0, initial_front_s_m=0.5)
    profiled = FillingBranch(
        branch=base.branch,
        elevation_samples_m=base.elevation_samples_m,
        initial_front_s_m=base.initial_front_s_m,
        elevation_profile_s_m=(0.0, 0.25, 0.5, 1.0),
        elevation_profile_z_m=(0.0, 0.4, 0.4, 0.0),
    )
    profiled.validate()
    assert profiled.elevation_at_s(0.125) == pytest.approx(0.2)
    assert profiled.elevation_at_s(0.5) == pytest.approx(0.4)
    assert profiled.elevation_at_s(0.75) == pytest.approx(0.2)


def test_fully_wet_uniform_route_matches_existing_network_limit() -> None:
    base, filling = _make_branch(
        "single",
        length_m=0.5,
        area_m2=0.01,
        initial_front_s_m=0.5,
        valve_cd=0.8,
        entrance_loss_k=0.3,
    )
    old_params = NetworkParameters(
        _make_params((filling,)).tank,
        _make_params((filling,)).gas,
        _make_params((filling,)).liquid,
        (base,),
    )
    new = simulate_filling(_make_params((filling,)), time_step_s=1.0e-5, max_time_s=0.001)
    old = simulate_parallel_branches(old_params, time_step_s=1.0e-5, max_time_s=0.001)
    assert np.allclose(
        new.samples["flow_single_m3_s"],
        old.samples["flow_rate_single_m3_s"],
        rtol=1.5e-3,
        atol=1e-10,
    )
    assert np.allclose(
        new.samples["gas_pressure_abs_Pa"],
        old.samples["gas_pressure_abs_Pa"],
        rtol=1e-8,
        atol=1e-4,
    )


def test_mouth_arrival_is_step_refined_and_external_water_stays_conservative() -> None:
    _, filling = _make_branch(
        "short",
        length_m=0.08,
        area_m2=0.01,
        initial_front_s_m=0.02,
        valve_cd=1.0,
    )
    params = _make_params((filling,), p0_pa=300_000.0)
    coarse = simulate_filling(params, time_step_s=2.0e-5, max_time_s=0.01)
    fine = simulate_filling(params, time_step_s=1.0e-5, max_time_s=0.01)
    coarse_arrivals = np.flatnonzero(coarse.samples["external_water_volume_short_m3"] > 0)
    fine_arrivals = np.flatnonzero(fine.samples["external_water_volume_short_m3"] > 0)
    assert coarse_arrivals.size and fine_arrivals.size
    coarse_time = coarse.samples["time_s"][coarse_arrivals[0]]
    fine_time = fine.samples["time_s"][fine_arrivals[0]]
    assert abs(coarse_time - fine_time) <= 3.0e-5
    assert np.max(np.abs(coarse.samples["water_volume_balance_residual_m3"])) < 2e-13
    assert np.max(np.abs(fine.samples["water_volume_balance_residual_m3"])) < 2e-13
    assert coarse.samples["outlet_flow_short_m3_s"][coarse_arrivals[0]] > 0
    assert fine.samples["outlet_flow_short_m3_s"][fine_arrivals[0]] > 0


def test_simulation_stops_at_highest_tank_intake_crown() -> None:
    _, filling = _make_branch("single", length_m=0.5, area_m2=0.01, initial_front_s_m=0.1)
    params = _make_params((filling,), p0_pa=2_000_000.0)
    result = simulate_filling(params, time_step_s=2.0e-5, max_time_s=0.2)
    stop_level = max(branch.branch.intake_crown_z_m for branch in (filling,))
    stop_water = tank_volume_at_level_m3(params.tank, stop_level)
    assert result.stop_reason == "tank_intake_crown_reached"
    assert result.samples["tank_water_volume_m3"][-1] == pytest.approx(stop_water, abs=1e-12)
    assert result.max_volume_balance_error_m3 < 2e-13


def test_frictionless_constant_head_column_matches_lengthening_front_solution() -> None:
    diameter = 10.0
    area = np.pi * diameter**2 / 4.0
    initial_length = 0.2
    section = HydraulicSection(
        "constant_area",
        1.0,
        area,
        area,
        diameter,
        diameter,
        0.0,
    )
    base = BranchParameters(
        name="large_tank",
        intake_center_z_m=-10.0,
        intake_diameter_m=diameter,
        outlet_center_z_m=-10.0,
        sections=(section,),
        valve_Cd=1.0e9,
        valve_opening_time_s=0.0,
        valve_opening_law="linear",
        valve_minimum_effective_opening=1.0,
        entrance_loss_K=0.0,
        transition_loss_K=0.0,
        intake_upper_edge_z_m=-5.0,
    )
    filling = FillingBranch(base, (-10.0, -10.0), initial_length, air_minor_loss_K=0.0)
    tank = TankProperties("vertical", 100.0, 100.0, 0.0, 0.5)
    p0 = 300_000.0
    ambient = 100_000.0
    gas = GasProperties("air", p0, ambient, 293.15, 1.0)
    liquid = LiquidProperties(998.2, 1.0e-9, 1.0e-9)
    params = FillingNetworkParameters(NetworkParameters(tank, gas, liquid, (base,)), (filling,))
    result = simulate_filling(params, time_step_s=1.0e-5, max_time_s=0.02)
    front = result.samples["front_s_large_tank_m"]
    speed_sq = (result.samples["flow_large_tank_m3_s"] / area) ** 2
    valid = (front >= 0.28) & (front <= 0.5)
    analytic = 2.0 * (p0 - ambient) / liquid.density_kg_m3 * (1.0 - initial_length / front)
    relative_error = np.abs(speed_sq[valid] - analytic[valid]) / analytic[valid]
    assert np.count_nonzero(valid) >= 10
    assert np.max(relative_error) < 0.01


def test_constant_area_air_screen_matches_laminar_darcy_and_minor_loss() -> None:
    diameter = 0.1
    area = np.pi * diameter**2 / 4.0
    total_length = 2.0
    dry_start = 0.3
    minor_k = 4.0
    _, filling = _make_branch(
        "air_screen",
        length_m=total_length,
        area_m2=area,
        initial_front_s_m=dry_start,
        air_minor_loss_k=minor_k,
    )
    params = _make_params((filling,), p0_pa=300_000.0)
    flow = 1.0e-4
    rho_air = params.network.gas.ambient_pressure_Pa / (R_AIR_J_KG_K * params.air_temperature_K)
    sound = np.sqrt(params.air_gamma * R_AIR_J_KG_K * params.air_temperature_K)
    velocity = flow / area
    reynolds = rho_air * velocity * diameter / 1.81e-5
    assert reynolds < 2300.0
    darcy = 64.0 / reynolds
    expected_drop = (
        0.5 * rho_air * velocity**2 * (darcy * (total_length - dry_start) / diameter + minor_k)
    )

    mach, pressure_drop, screen_pass = _air_diagnostics(
        filling,
        flow,
        dry_start,
        parameters=params,
        liquid_drive_Pa=300_000.0,
    )

    assert mach == pytest.approx(velocity / sound, rel=1e-13)
    assert pressure_drop == pytest.approx(expected_drop, rel=2e-12, abs=1e-15)
    assert screen_pass


def test_air_screen_rejects_high_mach_at_expanding_dry_front_endpoint() -> None:
    area_start = 0.005
    area_end = 0.020
    diameter_start = np.sqrt(4.0 * area_start / np.pi)
    diameter_end = np.sqrt(4.0 * area_end / np.pi)
    section = HydraulicSection(
        "expanding_dry_pipe",
        2.0,
        area_start,
        area_end,
        diameter_start,
        diameter_end,
        0.0,
    )
    branch = BranchParameters(
        name="expanding_air_screen",
        intake_center_z_m=0.0,
        intake_diameter_m=diameter_start,
        outlet_center_z_m=0.0,
        sections=(section,),
        valve_Cd=1.0,
        valve_opening_time_s=0.0,
        valve_opening_law="linear",
        valve_minimum_effective_opening=1.0,
        entrance_loss_K=0.0,
        transition_loss_K=0.0,
    )
    filling = FillingBranch(branch, (0.0, 0.0), initial_front_s_m=0.0, air_minor_loss_K=0.0)
    params = _make_params((filling,), p0_pa=300_000.0)
    sound = np.sqrt(params.air_gamma * R_AIR_J_KG_K * params.air_temperature_K)
    flow = 0.12 * sound * area_start
    gauss = np.polynomial.legendre.leggauss(4)[0]
    gauss_mach = []
    for xi in gauss:
        s = 1.0 + float(xi)  # four-point nodes over the full 2 m dry section
        area = area_start + (area_end - area_start) * s / 2.0
        gauss_mach.append(flow / area / sound)
    assert max(gauss_mach) < params.max_screened_air_mach

    mach, pressure_drop, screen_pass = _air_diagnostics(
        filling,
        flow,
        0.0,
        parameters=params,
        liquid_drive_Pa=1.0e9,
    )

    assert mach == pytest.approx(0.12, rel=1e-13)
    assert pressure_drop / 1.0e9 < params.max_screened_air_loss_fraction
    assert not screen_pass


def test_staggered_mouth_crossings_keep_branch_local_external_ledgers() -> None:
    _, first = _make_branch(
        "early",
        length_m=0.08,
        initial_front_s_m=0.07998,
        valve_cd=1.0e9,
    )
    _, second = _make_branch(
        "late",
        length_m=0.081,
        initial_front_s_m=0.08092,
        valve_cd=1.0e9,
    )
    params = _make_params((first, second), p0_pa=2_000_000.0)
    result = simulate_filling(params, time_step_s=1.0e-4, max_time_s=1.0e-4)
    samples = result.samples
    assert samples["external_water_volume_early_m3"][-1] > 0.0
    assert samples["external_water_volume_late_m3"][-1] > 0.0
    assert samples["external_water_volume_early_m3"][-1] != pytest.approx(
        samples["external_water_volume_late_m3"][-1], rel=1e-3, abs=1e-15
    )
    for name in ("early", "late"):
        assert np.max(np.abs(samples[f"branch_volume_balance_residual_{name}_m3"])) < 2e-13
        assert samples[f"integrated_branch_inflow_{name}_m3"][-1] == pytest.approx(
            samples[f"wet_line_volume_{name}_m3"][-1]
            - params.branches[("early", "late").index(name)].initial_wet_volume_m3
            + samples[f"external_water_volume_{name}_m3"][-1],
            abs=2e-13,
        )
