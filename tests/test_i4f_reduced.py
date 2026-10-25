"""Independent limiting and conservation checks for the I4F reduced model."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from aerial_drop.i4f_reduced import (
    ModelParameters,
    darcy_friction_factor,
    gas_state,
    inertial_flow_midpoint_step,
    line_static_pressure_diagnostics,
    opening_fraction,
    pipe_friction_pressure_drop_Pa,
    simulate,
    summarize,
    tank_level_z_m,
    tank_volume_at_level_m3,
    valve_command_fraction,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def baseline() -> dict:
    return json.loads((ROOT / "experiments/i4f_baseline.json").read_text())


def test_horizontal_and_vertical_tank_half_fill_symmetry(baseline: dict) -> None:
    horizontal = json.loads(json.dumps(baseline))
    horizontal["tank"]["fill_fraction"] = 0.5
    hp = ModelParameters.from_config(horizontal)
    assert tank_level_z_m(hp, 0.5 * hp.tank_volume_m3) == pytest.approx(
        hp.tank_center_z_m, abs=1e-13
    )
    assert tank_volume_at_level_m3(hp, hp.tank_center_z_m) == pytest.approx(
        0.5 * hp.tank_volume_m3, rel=2e-14
    )

    vertical = json.loads(json.dumps(baseline))
    vertical["tank"]["axis"] = "vertical"
    vertical["tank"]["fill_fraction"] = 0.5
    vp = ModelParameters.from_config(vertical)
    assert tank_level_z_m(vp, 0.5 * vp.tank_volume_m3) == pytest.approx(
        vp.tank_center_z_m, abs=1e-13
    )
    assert tank_volume_at_level_m3(vp, vp.tank_center_z_m) == pytest.approx(
        0.5 * vp.tank_volume_m3, rel=2e-14
    )


def test_laminar_pipe_loss_matches_hagen_poiseuille_limit(baseline: dict) -> None:
    p = ModelParameters.from_config(baseline)
    flow = 1.0e-5
    re = p.liquid_density_kg_m3 * (flow / p.pipe_area_m2) * p.pipe_diameter_m
    re /= p.liquid_viscosity_Pa_s
    assert re < 2300.0
    expected = 128.0 * p.liquid_viscosity_Pa_s * p.pipe_length_m * flow
    expected /= np.pi * p.pipe_diameter_m**4
    assert pipe_friction_pressure_drop_Pa(p, flow) == pytest.approx(expected, rel=1e-13)
    assert darcy_friction_factor(re, p.roughness_m / p.pipe_diameter_m) == pytest.approx(
        64.0 / re, rel=1e-15
    )


def test_constant_head_orifice_matches_analytic_inertial_startup() -> None:
    inertance = 2000.0
    pressure_drive = 20000.0
    quadratic_resistance = 1.0e6
    time_step = 1.0e-4
    end_time = 0.05
    steps = round(end_time / time_step)
    flow = 0.0
    discharged_volume = 0.0
    for _ in range(steps):
        midpoint_flow, flow = inertial_flow_midpoint_step(
            flow,
            time_step,
            inertance,
            pressure_drive,
            0.0,
            quadratic_resistance,
        )
        discharged_volume += midpoint_flow * time_step
    steady_flow = np.sqrt(pressure_drive / quadratic_resistance)
    time_scale = inertance / np.sqrt(pressure_drive * quadratic_resistance)
    exact_flow = steady_flow * np.tanh(end_time / time_scale)
    exact_volume = steady_flow * time_scale * np.log(np.cosh(end_time / time_scale))
    assert flow == pytest.approx(exact_flow, rel=2.5e-6)
    assert discharged_volume == pytest.approx(exact_volume, rel=2.5e-6)


def test_isothermal_sealed_gas_obeys_pv_inventory(baseline: dict) -> None:
    case = json.loads(json.dumps(baseline))
    case["gas"]["polytropic_n"] = 1.0
    p = ModelParameters.from_config(case)
    gas_initial = (1.0 - p.tank_fill_fraction) * p.tank_volume_m3
    pressure, temperature, mass = gas_state(p, gas_initial, 0.6 * gas_initial)
    assert pressure * (0.6 * gas_initial) == pytest.approx(
        p.initial_gas_pressure_Pa * gas_initial, rel=2e-15
    )
    assert temperature == pytest.approx(p.gas_temperature_K, rel=2e-15)
    assert mass == pytest.approx(
        p.initial_gas_pressure_Pa
        * gas_initial
        / (p.gas_specific_constant_J_kg_K * p.gas_temperature_K),
        rel=2e-15,
    )


def test_discharge_stops_at_gas_breakthrough_and_conserves_total_water(baseline: dict) -> None:
    result = simulate(baseline, time_step_s=2.0e-4)
    samples = result.samples
    p = result.parameters
    assert samples["flow_rate_m3_s"][0] == 0.0
    assert samples["water_level_z_m"][-1] == pytest.approx(p.connection_upper_edge_z_m, abs=2e-13)
    assert "upper edge" in result.stop_reason
    assert result.max_mass_balance_error_m3 < 1e-14
    total_initial = result.initial_tank_water_volume_m3 + result.initial_line_water_volume_m3
    total_each_time = (
        samples["total_internal_water_volume_m3"]
        + samples["cumulative_external_discharge_volume_m3"]
    )
    assert np.allclose(total_each_time, total_initial, rtol=0.0, atol=3e-15)
    invariant = samples["gas_pressure_abs_Pa"] * samples["gas_volume_m3"] ** p.polytropic_n
    assert np.max(np.abs(invariant / invariant[0] - 1.0)) < 2e-14
    nonzero = samples["flow_rate_m3_s"] > 0
    expected_momentum = (
        p.liquid_density_kg_m3
        * samples["flow_rate_m3_s"][nonzero]
        * (p.pipe_length_m + p.transition_length_m)
    )
    assert np.allclose(
        samples["pipe_transition_liquid_momentum_kg_m_s"][nonzero],
        expected_momentum,
        rtol=0.0,
        atol=1e-12,
    )


def test_maintained_pressure_is_distinct_from_sealed_blowdown(baseline: dict) -> None:
    case = json.loads(json.dumps(baseline))
    case["gas"]["mode"] = "maintained_pressure"
    result = simulate(case, time_step_s=5.0e-4)
    pressure = result.samples["gas_pressure_abs_Pa"]
    assert np.all(pressure == case["gas"]["initial_absolute_pressure_Pa"])
    assert result.stop_reason.startswith("gas-liquid interface reached")


def test_square_edge_entrance_loss_uses_pipe_velocity_reference(baseline: dict) -> None:
    result = simulate(baseline, time_step_s=5.0e-4)
    samples = result.samples
    p = result.parameters
    positive = samples["flow_rate_m3_s"] > 0.1
    expected = (
        0.5
        * p.liquid_density_kg_m3
        * p.entrance_loss_K
        * (samples["flow_rate_m3_s"][positive] / p.pipe_area_m2) ** 2
    )
    assert np.allclose(samples["pressure_pipe_entrance_Pa"][positive], expected, rtol=2e-15)

    legacy = json.loads(json.dumps(baseline))
    legacy["pipe"].pop("entrance_K")
    assert ModelParameters.from_config(legacy).entrance_loss_K == 0.0


def test_effective_opening_floor_defaults_to_zero_and_clamps_smoothstep(
    baseline: dict,
) -> None:
    no_floor_config = json.loads(json.dumps(baseline))
    no_floor_config["valve"].pop("minimum_effective_opening", None)
    default = ModelParameters.from_config(no_floor_config)
    assert default.valve_minimum_effective_opening == 0.0
    assert opening_fraction(default, 0.0) == 0.0

    configured = json.loads(json.dumps(baseline))
    configured["valve"]["minimum_effective_opening"] = 0.02
    parameters = ModelParameters.from_config(configured)
    assert parameters.valve_minimum_effective_opening == pytest.approx(0.02)
    assert valve_command_fraction(parameters, 0.0) == 0.0
    assert opening_fraction(parameters, 0.0) == pytest.approx(0.02)
    assert valve_command_fraction(parameters, 0.25) == pytest.approx(0.5)
    assert opening_fraction(parameters, 0.25) == pytest.approx(0.5)
    assert opening_fraction(parameters, 0.5) == pytest.approx(1.0)


def test_effective_opening_floor_override_is_in_samples_and_validated(baseline: dict) -> None:
    result = simulate(baseline, minimum_effective_opening=0.02, time_step_s=0.01, max_time_s=0.1)
    assert result.parameters.valve_minimum_effective_opening == pytest.approx(0.02)
    assert result.samples["opening_fraction"][0] == pytest.approx(0.02)
    assert result.samples["valve_command_fraction"][0] == pytest.approx(0.0)
    assert valve_command_fraction(result.parameters, 0.1) == pytest.approx(0.104)
    assert opening_fraction(result.parameters, 0.1) == pytest.approx(0.104)
    assert result.samples["opening_fraction"][-1] == pytest.approx(0.104)
    assert result.samples["valve_command_fraction"][1] > 0.0

    invalid = json.loads(json.dumps(baseline))
    invalid["valve"]["minimum_effective_opening"] = 1.01
    with pytest.raises(ValueError, match="minimum_effective_opening"):
        ModelParameters.from_config(invalid)


def test_static_pressure_screen_recovers_equal_area_steady_limit(baseline: dict) -> None:
    case = json.loads(json.dumps(baseline))
    provisional = ModelParameters.from_config(case)
    case["nozzle"]["width_m"] = provisional.pipe_area_m2 / case["nozzle"]["height_m"]
    case["pipe"]["transition_K"] = 0.0
    p = ModelParameters.from_config(case)

    result = line_static_pressure_diagnostics(p, flow_rate_m3_s=0.4, flow_acceleration_m3_s2=0.0)

    assert result["pressure_transition_entry_abs_Pa"] == pytest.approx(
        p.ambient_pressure_Pa, abs=1e-10
    )
    assert result["pressure_after_valve_abs_Pa"] == pytest.approx(
        p.ambient_pressure_Pa + pipe_friction_pressure_drop_Pa(p, 0.4), rel=2e-15
    )


def test_positive_acceleration_adds_upstream_static_pressure(baseline: dict) -> None:
    p = ModelParameters.from_config(baseline)
    flow = 0.4
    acceleration = 2.5
    steady = line_static_pressure_diagnostics(p, flow, 0.0)
    accelerating = line_static_pressure_diagnostics(p, flow, acceleration)

    assert accelerating["pressure_transition_entry_abs_Pa"] - steady[
        "pressure_transition_entry_abs_Pa"
    ] == pytest.approx(p.transition_inertance_kg_m4 * acceleration, rel=2e-15)
    assert accelerating["pressure_after_valve_abs_Pa"] - steady[
        "pressure_after_valve_abs_Pa"
    ] == pytest.approx(p.liquid_column_inertance_kg_m4 * acceleration, rel=2e-15)


def test_pressure_screen_precedes_and_does_not_replace_crown_stop(baseline: dict) -> None:
    result = simulate(
        baseline,
        polytropic_n=1.0,
        valve_opening_time_s=0.1,
        minimum_effective_opening=0.0,
        time_step_s=2.0e-4,
    )
    summary = summarize(result)
    screen = summary["pressure_screen"]
    events = screen["first_at_or_below_threshold_events"]
    transition_zero = events["pipe_side_transition_entry"]["zero_absolute"]
    transition_vapor = events["pipe_side_transition_entry"]["water_vapor_reference_20C_absolute"]

    assert screen["history_at_or_below_water_vapor_reference"]
    assert screen["history_at_or_below_zero_absolute"]
    assert transition_vapor is not None
    assert transition_zero is not None
    assert transition_zero["time_s"] < result.stop_time_s
    assert screen["crown_stop_reached"]
    assert screen["crown_stop_time_s"] == result.stop_time_s
    assert screen["integration_stop_time_s"] == result.stop_time_s
    assert result.samples["time_s"][-1] == result.stop_time_s
    assert "upper edge" in result.stop_reason
