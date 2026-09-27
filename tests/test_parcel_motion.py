"""Independent checks of the isolated-drop momentum implementation."""

from __future__ import annotations

import math

import numpy as np
import pytest

from aerial_drop.parcel_motion import (
    MotionProperties,
    drop_acceleration_m_s2,
    evaluate_drop_aerodynamics,
    integrate_isolated_drop,
)


def test_denner_aerodynamic_correlations_match_direct_equation_evaluation() -> None:
    radius = 5.0e-4
    air = np.array((3.0, 4.0, 0.0))
    drop = np.zeros(3)
    properties = MotionProperties()
    speed = 5.0
    reynolds = 2.0 * radius * properties.air_density_kg_m3 * speed
    reynolds /= properties.air_dynamic_viscosity_pa_s
    weber = 2.0 * radius * properties.air_density_kg_m3 * speed**2
    weber /= properties.surface_tension_n_m
    cd_sphere = (24.0 / reynolds) * (
        1.0 + 0.15 * reynolds**0.687 + 0.0175 * reynolds / (1.0 + 42500.0 * reynolds**-1.16)
    )
    max_radius = radius * (1.0 + 0.19 * math.sqrt(weber))
    cd = cd_sphere * (1.0 + 2.632 * (1.0 - (radius / max_radius) ** 2))
    bond = (
        properties.water_density_kg_m3
        * np.linalg.norm(properties.gravity_m_s2)
        * (2.0 * radius) ** 2
        / properties.surface_tension_n_m
    )
    critical_weber = (4.0 / (3.0 * cd)) * (
        4.0 * math.pi**2 * (radius / max_radius) ** 4 - bond * (radius / max_radius) ** 2
    )

    result = evaluate_drop_aerodynamics(radius, air, drop, properties)
    assert result.reynolds_number == pytest.approx(332.596685082873, rel=1e-12)
    assert result.weber_number == pytest.approx(0.418055555555556, rel=1e-12)
    assert result.drag_coefficient == pytest.approx(1.02708954038592, rel=1e-12)
    assert result.critical_weber_number == pytest.approx(32.1008855501431, rel=1e-12)
    assert result.reynolds_number == pytest.approx(reynolds, rel=1e-14)
    assert result.weber_number == pytest.approx(weber, rel=1e-14)
    assert result.drag_coefficient == pytest.approx(cd, rel=1e-14)
    assert result.critical_weber_number == pytest.approx(critical_weber, rel=1e-14)
    assert result.breakup_predicted == (weber > critical_weber)


def test_zero_relative_velocity_has_zero_drag_and_finite_gravity_acceleration() -> None:
    result = evaluate_drop_aerodynamics(2.0e-4, (7.0, 0.0, 0.0), (7.0, 0.0, 0.0))
    assert result.reynolds_number == 0.0
    assert result.weber_number == 0.0
    assert math.isinf(result.drag_coefficient)
    assert not result.breakup_predicted

    gravity = np.asarray(MotionProperties().gravity_m_s2)
    expected = gravity * (
        1.0 - MotionProperties().air_density_kg_m3 / MotionProperties().water_density_kg_m3
    )
    actual = drop_acceleration_m_s2(2.0e-4, (7.0, 0.0, 0.0), (7.0, 0.0, 0.0))
    assert actual == pytest.approx(expected, abs=1e-14)


def test_rk4_converges_to_the_independent_ballistic_solution_at_vanishing_air_density() -> None:
    properties = MotionProperties(air_density_kg_m3=1e-100, air_dynamic_viscosity_pa_s=1e-100)
    initial_position = np.array((0.0, 0.0, 40.0))
    initial_velocity = np.array((12.0, -3.0, 2.0))
    duration = 1.25
    gravity = np.asarray(properties.gravity_m_s2)
    expected_position = initial_position + initial_velocity * duration + 0.5 * gravity * duration**2
    expected_velocity = initial_velocity + gravity * duration

    coarse = integrate_isolated_drop(
        initial_position,
        initial_velocity,
        1.0e-4,
        duration_s=duration,
        step_s=0.25,
        properties=properties,
    )
    fine = integrate_isolated_drop(
        initial_position,
        initial_velocity,
        1.0e-4,
        duration_s=duration,
        step_s=0.125,
        properties=properties,
    )
    assert coarse.stop_reason == fine.stop_reason == "duration"
    assert coarse.time_s.ndim == 1
    assert coarse.position_m[-1] == pytest.approx(expected_position, abs=1e-10)
    assert fine.position_m[-1] == pytest.approx(expected_position, abs=1e-10)
    assert fine.velocity_m_s[-1] == pytest.approx(expected_velocity, abs=1e-10)
    assert not fine.time_s.flags.writeable
    assert not fine.position_m.flags.writeable
    assert not fine.velocity_m_s.flags.writeable


def test_nonzero_drag_vector_and_terminal_speed_match_independent_force_balance() -> None:
    radius = 5.0e-4
    relative_wind = (3.0, 4.0, 0.0)
    acceleration = drop_acceleration_m_s2(radius, relative_wind, (0.0, 0.0, 0.0))
    assert acceleration == pytest.approx(
        (13.95378919, 18.60505226, -9.79815322), rel=1e-8, abs=1e-8
    )

    terminal_speed = 3.158494072
    terminal_acceleration = drop_acceleration_m_s2(
        radius, (0.0, 0.0, 0.0), (0.0, 0.0, -terminal_speed)
    )
    assert terminal_acceleration[2] == pytest.approx(0.0, abs=3e-8)
    trajectory = integrate_isolated_drop(
        (0.0, 0.0, 100.0),
        (0.0, 0.0, 0.0),
        radius,
        duration_s=20.0,
        step_s=0.01,
    )
    assert trajectory.stop_reason == "duration"
    assert trajectory.velocity_m_s[-1, 2] == pytest.approx(-terminal_speed, abs=1e-7)


def test_ground_event_terminates_at_plane_and_reports_ground_frame_impact() -> None:
    properties = MotionProperties(
        air_density_kg_m3=1e-100,
        air_dynamic_viscosity_pa_s=1e-100,
        gravity_m_s2=(0.0, 0.0, -10.0),
    )
    height = 10.0
    initial_vertical_velocity = 2.0
    exact_time = (
        initial_vertical_velocity + math.sqrt(initial_vertical_velocity**2 + 200.0)
    ) / 10.0
    trajectory = integrate_isolated_drop(
        (1.0, -2.0, height),
        (4.0, 3.0, initial_vertical_velocity),
        1.0e-4,
        duration_s=5.0,
        step_s=0.7,
        ground_z_m=0.0,
        properties=properties,
    )
    assert trajectory.stop_reason == "ground"
    assert trajectory.flight_time_s == pytest.approx(exact_time, abs=1e-10)
    assert trajectory.impact_position_m is not None
    assert trajectory.impact_position_m[2] == 0.0
    assert np.all(trajectory.position_m[:, 2] >= 0.0)


def test_stationary_drop_at_ground_stops_at_zero_time_when_gravity_points_into_plane() -> None:
    trajectory = integrate_isolated_drop(
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        1.0e-4,
        duration_s=0.1,
        step_s=0.01,
        ground_z_m=0.0,
    )
    assert trajectory.stop_reason == "ground"
    assert trajectory.flight_time_s == 0.0
    assert trajectory.position_m[-1, 2] == 0.0


def test_coarse_step_still_catches_ground_crossing_before_upward_turnaround() -> None:
    trajectory = integrate_isolated_drop(
        (0.0, 0.0, 0.001),
        (0.0, 0.0, -10.0),
        1.0e-4,
        (0.0, 0.0, 20.0),
        duration_s=0.005,
        step_s=0.005,
        ground_z_m=0.0,
    )
    assert trajectory.stop_reason == "ground"
    assert trajectory.flight_time_s == pytest.approx(1.02834835e-4, abs=1e-11)
    assert trajectory.position_m[-1, 2] == 0.0
    assert trajectory.velocity_m_s[-1, 2] < 0.0


def test_initial_breakup_criterion_stops_without_extending_a_fixed_radius_path() -> None:
    trajectory = integrate_isolated_drop(
        (0.0, 0.0, 50.0),
        (0.0, 0.0, 0.0),
        2.0e-3,
        (0.0, 0.0, 100.0),
        duration_s=2.0,
        step_s=0.01,
    )
    assert trajectory.stop_reason == "breakup"
    assert trajectory.breakup_bracket_s == (0.0, 0.0)
    assert len(trajectory.time_s) == 1
    assert trajectory.within_nominal_source_size_range


def test_source_range_is_reported_without_rejecting_an_explicit_sensitivity_size() -> None:
    trajectory = integrate_isolated_drop(
        (0.0, 0.0, 10.0),
        (0.0, 0.0, 0.0),
        3.0e-3,
        duration_s=0.001,
        step_s=0.001,
    )
    assert not trajectory.within_nominal_source_size_range


def test_in_step_breakup_event_converges_under_step_refinement_outside_source_range() -> None:
    trajectories = [
        integrate_isolated_drop(
            (0.0, 0.0, 100.0),
            (0.0, 0.0, 0.0),
            4.0e-3,
            duration_s=2.0,
            step_s=step,
        )
        for step in (0.01, 0.005)
    ]
    for trajectory in trajectories:
        assert trajectory.stop_reason == "breakup"
        assert trajectory.breakup_bracket_s is not None
        assert not trajectory.within_nominal_source_size_range
    assert trajectories[0].flight_time_s == pytest.approx(0.85424286, abs=5e-8)
    assert trajectories[1].flight_time_s == pytest.approx(trajectories[0].flight_time_s, abs=5e-8)


def test_invalid_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="finite length-3"):
        integrate_isolated_drop((0.0, 0.0), (0.0, 0.0, 0.0), 1e-4, duration_s=1, step_s=0.1)
    with pytest.raises(ValueError, match="positive"):
        integrate_isolated_drop((0.0, 0.0, 1.0), (0.0, 0.0, 0.0), 1e-4, duration_s=1, step_s=0)
    with pytest.raises(ValueError, match="on or above"):
        integrate_isolated_drop(
            (0.0, 0.0, -1.0),
            (0.0, 0.0, 0.0),
            1e-4,
            duration_s=1,
            step_s=0.1,
            ground_z_m=0.0,
        )
