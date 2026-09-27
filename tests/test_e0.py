"""Independent analytic checks for the E0 foundation."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from aerial_drop.e0 import (
    GroundMap,
    MassLedger,
    aircraft_to_ground_position,
    ballistic_impact,
    check_momentum_conservation,
    deposit_impacts,
    ellipse_rectangle_check,
    improvement_gain,
    release_mass,
    score_ground_map,
)


def test_release_mass_uses_only_velocity_normal_to_the_outlet() -> None:
    first = release_mass(1000.0, 0.12, (5.0, 0.0, 0.0), (1.0, 0.0, 0.0), 2.0)
    second = release_mass(1000.0, 0.12, (5.0, -12.0, 3.0), (1.0, 0.0, 0.0), 2.0)
    assert first == pytest.approx(1200.0, rel=0.0, abs=1e-12)
    assert second == pytest.approx(first, rel=0.0, abs=1e-12)


def test_aircraft_mapping_and_ballistic_impact_use_absolute_release_time() -> None:
    mapped = aircraft_to_ground_position((2.0, 3.0, 4.0), 5.0, (1.0, 2.0, 10.0), (3.0, 4.0, 0.0))
    assert mapped == pytest.approx((18.0, 25.0, 14.0), rel=1e-12, abs=1e-12)

    flight = math.sqrt(20.0)
    impact = ballistic_impact(
        release_position_aircraft_m=(0.0, 0.0, 0.0),
        release_velocity_aircraft_m_s=(2.0, -1.0, 0.0),
        release_time_s=4.0,
        aircraft_position_at_zero_m=(0.0, 0.0, 100.0),
        aircraft_velocity_m_s=(10.0, 2.0, 0.0),
        gravity_m_s2=(0.0, 0.0, -10.0),
    )
    assert impact.flight_time_s == pytest.approx(flight, rel=1e-12, abs=1e-12)
    assert impact.impact_time_s == pytest.approx(4.0 + flight, rel=1e-12, abs=1e-12)
    assert impact.position_m == pytest.approx(
        (40.0 + 12.0 * flight, 8.0 + flight, 0.0), rel=1e-12, abs=1e-12
    )


def test_ballistic_solver_handles_surface_launch_and_strong_downward_velocity() -> None:
    surface_launch = ballistic_impact(
        release_position_aircraft_m=(0.0, 0.0, 0.0),
        release_velocity_aircraft_m_s=(0.0, 0.0, 5.0),
        release_time_s=0.0,
        aircraft_position_at_zero_m=(0.0, 0.0, 0.0),
        aircraft_velocity_m_s=(0.0, 0.0, 0.0),
        gravity_m_s2=(0.0, 0.0, -10.0),
    )
    assert surface_launch.flight_time_s == pytest.approx(1.0, rel=1e-12, abs=1e-12)
    assert surface_launch.position_m[2] == pytest.approx(0.0, rel=0.0, abs=1e-12)

    fast_fall = ballistic_impact(
        release_position_aircraft_m=(0.0, 0.0, 100.0),
        release_velocity_aircraft_m_s=(0.0, 0.0, -1e12),
        release_time_s=0.0,
        aircraft_position_at_zero_m=(0.0, 0.0, 0.0),
        aircraft_velocity_m_s=(0.0, 0.0, 0.0),
        gravity_m_s2=(0.0, 0.0, -9.81),
    )
    assert fast_fall.flight_time_s == pytest.approx(1e-10, rel=1e-12, abs=0.0)


def test_weighted_finite_volume_deposition_preserves_boundary_convention_and_mass() -> None:
    result = deposit_impacts(
        x_edges_m=(0.0, 1.0, 3.0),
        y_edges_m=(-1.0, 0.0, 3.0),
        impact_xy_m=((0.5, -0.5), (1.0, 0.0), (3.0, 3.0), (-0.1, 1.0)),
        impact_mass_kg=(2.0, 3.0, 4.0, 5.0),
    )
    # Interior edges are assigned to the bin above/right; the last outer edge
    # remains inside the final bin. Axes are indexed [x_cell, y_cell].
    assert result.ground_map.concentration_kg_m2 == pytest.approx(
        np.array([[2.0, 0.0], [0.0, 0.5 + 4.0 / 6.0]]), rel=1e-12, abs=1e-12
    )
    assert result.in_map_mass_kg == pytest.approx(9.0, rel=1e-12, abs=1e-12)
    assert result.outside_map_mass_kg == pytest.approx(5.0, rel=1e-12, abs=1e-12)
    assert result.deposited_mass_kg == pytest.approx(14.0, rel=1e-12, abs=1e-12)
    assert result.impact_locations_xy_m.tolist() == [
        [0.5, -0.5],
        [1.0, 0.0],
        [3.0, 3.0],
        [-0.1, 1.0],
    ]
    assert not result.ground_map.concentration_kg_m2.flags.writeable
    assert not result.impact_masses_kg.flags.writeable

    ledger = MassLedger(14.0, result.deposited_mass_kg, 0.0, 0.0, 0.0, 0.0)
    assert ledger.residual_kg == pytest.approx(0.0, rel=0.0, abs=1e-12)
    split_airborne_ledger = MassLedger(18.0, 14.0, 2.0, 1.0, 0.5, 0.5)
    assert split_airborne_ledger.airborne_kg == pytest.approx(3.0, rel=1e-12, abs=1e-12)
    assert split_airborne_ledger.residual_kg == pytest.approx(0.0, rel=0.0, abs=1e-12)
    with pytest.raises(ValueError, match="released mass"):
        MassLedger(14.0, result.in_map_mass_kg, 0.0, 0.0, 0.0, 0.0)


def _scoring_fixture() -> GroundMap:
    x_edges = np.array([0.0, 2.0, 5.0, 7.0, 10.0, 12.0])
    y_edges = np.array([-2.0, -1.375, -1.125, -0.8, 0.8, 1.125, 1.375, 2.0])
    concentration = np.zeros((5, 7))
    for i in (0, 1, 3, 4):
        concentration[i, 2:6] = 3.0
        concentration[i, (0, 6)] = 10.0  # high dose outside the centered target
    return GroundMap(x_edges, y_edges, concentration)


def test_l95_uses_partial_y_area_caps_excess_and_breaks_ties_earliest() -> None:
    result = score_ground_map(_scoring_fixture(), 250.0, 2.5, 2.4)
    # The five qualifying y cells overlap the centered width by 2.375 m,
    # exactly 95% of 2.5 m; the outermost 0.125 m cell fails the threshold.
    assert result.l95_m == pytest.approx(5.0, rel=1e-12, abs=1e-12)
    assert (result.strip_start_index, result.strip_stop_index) == (0, 2)
    assert (result.strip_x_start_m, result.strip_x_stop_m) == (0.0, 5.0)
    assert result.useful_credit_mass_kg == pytest.approx(2.4 * 2.375 * 5.0, rel=1e-12, abs=1e-12)
    assert result.actual_mass_inside_strip_kg == pytest.approx(
        3.0 * 2.375 * 5.0, rel=1e-12, abs=1e-12
    )
    assert result.useful_fraction == pytest.approx(28.5 / 250.0, rel=1e-12, abs=1e-12)
    assert result.mass_elsewhere_on_ground_kg == pytest.approx(200.0 - 35.625, rel=1e-12, abs=1e-12)

    including_outside_map = score_ground_map(
        _scoring_fixture(), 255.0, 2.5, 2.4, outside_map_mass_kg=5.0
    )
    assert including_outside_map.mass_elsewhere_on_ground_kg == pytest.approx(
        result.mass_elsewhere_on_ground_kg + 5.0, rel=1e-12, abs=1e-12
    )


def test_no_valid_strip_returns_zero_and_excess_map_mass_is_rejected() -> None:
    ground_map = GroundMap((0.0, 2.0), (-2.0, 2.0), np.zeros((1, 1)))
    result = score_ground_map(ground_map, 1.0, 2.0, 2.4)
    assert result.l95_m == 0.0
    assert result.strip_x_start_m is None
    assert result.strip_x_stop_m is None
    assert result.useful_fraction == 0.0
    assert result.useful_credit_mass_kg == 0.0

    overdrawn = GroundMap((0.0, 1.0), (-1.0, 1.0), np.array([[2.0]]))
    with pytest.raises(ValueError, match="cannot exceed"):
        score_ground_map(overdrawn, 1.0, 2.0, 1.0)


def test_longest_strip_uses_physical_length_instead_of_cell_count() -> None:
    # Three narrow sections span 3 m, then a dry gap, then one 6 m section.
    ground_map = GroundMap(
        (0.0, 1.0, 2.0, 3.0, 4.0, 10.0),
        (-0.5, 0.5),
        np.array([[1.0], [1.0], [1.0], [0.0], [1.0]]),
    )
    result = score_ground_map(ground_map, 9.0, 1.0, 1.0)
    assert (result.strip_x_start_m, result.strip_x_stop_m) == (4.0, 10.0)
    assert result.l95_m == 6.0
    assert result.useful_fraction == pytest.approx(2.0 / 3.0, rel=1e-12, abs=1e-12)


def test_threshold_equality_and_excess_dose_have_distinct_useful_credit() -> None:
    at_threshold = GroundMap((0.0, 2.0), (-0.5, 0.5), np.array([[2.4]]))
    excess_dose = GroundMap((0.0, 2.0), (-0.5, 0.5), np.array([[4.8]]))
    exact = score_ground_map(at_threshold, 4.8, 1.0, 2.4)
    excess = score_ground_map(excess_dose, 9.6, 1.0, 2.4)
    assert exact.l95_m == excess.l95_m == 2.0
    assert exact.useful_fraction == pytest.approx(1.0, rel=1e-12, abs=1e-12)
    assert excess.useful_fraction == pytest.approx(0.5, rel=1e-12, abs=1e-12)


def test_gain_is_undefined_for_zero_control_length() -> None:
    assert improvement_gain(10.0, 0.0) is None
    assert improvement_gain(12.0, 6.0) == pytest.approx(2.0, rel=1e-12, abs=1e-12)


def test_ellipse_rectangle_arithmetic_is_full_width_not_l95() -> None:
    result = ellipse_rectangle_check(25.0, 7.0, 9.0)
    assert result.ellipse_area_m2 == pytest.approx(math.pi * 25.0 * 7.0, rel=1e-12, abs=1e-12)
    assert result.full_width_ellipse_length_m == pytest.approx(
        38.29930462415574, rel=1e-12, abs=1e-12
    )
    assert result.same_area_rectangle_length_m == pytest.approx(
        61.08652381980154, rel=1e-12, abs=1e-12
    )
    assert result.rectangle_to_ellipse_length_ratio == pytest.approx(
        1.5949773610582394, rel=1e-12, abs=1e-12
    )
    assert "not the map-based 95% L95" in ellipse_rectangle_check.__doc__


def test_handoff_momentum_check_is_vector_sum_only() -> None:
    balanced = check_momentum_conservation((1.0, 2.0, 3.0), (0.25, 0.5, 0.75), (0.75, 1.5, 2.25))
    unbalanced = check_momentum_conservation((1.0, 0.0, 0.0), (0.5, 0.0, 0.0), (0.4, 0.0, 0.0))
    assert balanced.conserved
    assert balanced.residual_norm_kg_m_s == pytest.approx(0.0, rel=0.0, abs=1e-12)
    assert not unbalanced.conserved


def test_e0_cli_writes_reproducible_bundle_and_refuses_overwrite(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(repository_root / "src"), existing_pythonpath) if part
    )
    outputs = [tmp_path / "run-a", tmp_path / "run-b"]
    reports = []
    maps = []
    for output in outputs:
        completed = subprocess.run(
            [sys.executable, "-m", "aerial_drop.e0", "--output", str(output)],
            cwd=repository_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        assert completed.stdout.strip() == str(output)
        reports.append(json.loads((output / "e0-report.json").read_text(encoding="utf-8")))
        with np.load(output / "ground-map.npz") as archive:
            maps.append({name: archive[name].copy() for name in archive.files})

    assert reports[0]["checks"] == reports[1]["checks"]
    assert reports[0]["seed"] == 0
    provenance = reports[0]["provenance"]
    assert provenance["revision"] is None or len(provenance["revision"]) >= 7
    assert provenance["dirty"] is True or provenance["dirty"] is False
    assert provenance["code_sha256"]["src/aerial_drop/e0.py"]
    assert set(maps[0]) == set(maps[1])
    for name in maps[0]:
        assert np.array_equal(maps[0][name], maps[1][name])

    original_report = (outputs[0] / "e0-report.json").read_bytes()
    refused = subprocess.run(
        [sys.executable, "-m", "aerial_drop.e0", "--output", str(outputs[0])],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert (outputs[0] / "e0-report.json").read_bytes() == original_report
