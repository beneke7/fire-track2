"""Independent algebraic checks for the sealed-gas pressure-budget reference."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from aerial_drop.i4f_pressure_budget import (
    SealedGasBudgetCase,
    pressure_after_gas_displacement_abs_Pa,
    pressure_budget,
    pressure_during_post_priming_delivery_abs_Pa,
    tank_only_critical_headspace_ratio,
)


def _case(*, dry_m3: float = 0.4320037386471729, n: float = 1.4) -> SealedGasBudgetCase:
    return SealedGasBudgetCase(
        initial_pressure_abs_Pa=1_200_000.0,
        back_pressure_abs_Pa=100_000.0,
        tank_water_volume_m3=1.35,
        headspace_ratio_to_tank_water=0.225,
        wetted_feed_volume_m3=0.2539360223582692,
        initially_dry_downstream_volume_m3=dry_m3,
        polytropic_exponent=n,
    )


def test_pressure_budget_primes_before_nozzle_delivery_without_double_counting_feed() -> None:
    case = _case()
    result = pressure_budget(case)
    expected = 1_200_000.0 * (0.30375 / (0.30375 + 0.4320037386471729)) ** 1.4
    assert result["pressure_after_full_bore_priming_abs_Pa"] == pytest.approx(expected)
    assert result["initial_liquid_inventory_m3"] == pytest.approx(1.35 + 0.2539360223582692)
    # The wetted feed affects the inventory cap, not the gas displacement needed to prime.
    no_feed = SealedGasBudgetCase(**{**case.__dict__, "wetted_feed_volume_m3": 0.0})
    assert pressure_budget(no_feed)["pressure_after_full_bore_priming_abs_Pa"] == pytest.approx(
        result["pressure_after_full_bore_priming_abs_Pa"]
    )
    assert (
        result["initial_liquid_inventory_m3"]
        - pressure_budget(no_feed)["initial_liquid_inventory_m3"]
    ) == pytest.approx(case.wetted_feed_volume_m3)


def test_primed_zero_dry_volume_limit_matches_closed_form_equalization() -> None:
    case = _case(dry_m3=0.0)
    result = pressure_budget(case)
    expected_displacement = case.initial_headspace_volume_m3 * (
        (case.initial_pressure_abs_Pa / case.back_pressure_abs_Pa)
        ** (1.0 / case.polytropic_exponent)
        - 1.0
    )
    assert result["raw_pressure_equilibrium_gas_displacement_m3"] == pytest.approx(
        expected_displacement
    )
    assert result["raw_pressure_equilibrium_nozzle_volume_after_priming_m3"] == pytest.approx(
        expected_displacement
    )
    assert pressure_during_post_priming_delivery_abs_Pa(
        case, expected_displacement
    ) == pytest.approx(case.back_pressure_abs_Pa)


def test_pressure_is_positive_monotone_and_inverse_equilibrium_is_exact() -> None:
    case = _case()
    points = [
        pressure_during_post_priming_delivery_abs_Pa(case, volume) for volume in (0, 0.2, 0.7, 1.2)
    ]
    assert all(value > 0 for value in points)
    assert all(right < left for left, right in zip(points, points[1:]))
    result = pressure_budget(case)
    assert (
        result["raw_pressure_equilibrium_nozzle_volume_after_priming_m3"]
        < case.initial_liquid_inventory_m3
    )
    assert pressure_during_post_priming_delivery_abs_Pa(
        case, result["raw_pressure_equilibrium_nozzle_volume_after_priming_m3"]
    ) == pytest.approx(case.back_pressure_abs_Pa)
    assert not result["equilibrium_nozzle_volume_was_inventory_capped"]


def test_shorter_train_increases_equilibrium_nozzle_volume_by_dryline_difference() -> None:
    long_dry = 0.4320037386471729
    short_dry = 0.39066867643522984
    long = pressure_budget(_case(dry_m3=long_dry, n=1.4))
    short = pressure_budget(_case(dry_m3=short_dry, n=1.4))
    assert not long["equilibrium_nozzle_volume_was_inventory_capped"]
    assert not short["equilibrium_nozzle_volume_was_inventory_capped"]
    assert (
        short["raw_pressure_equilibrium_nozzle_volume_after_priming_m3"]
        - long["raw_pressure_equilibrium_nozzle_volume_after_priming_m3"]
    ) == pytest.approx(long_dry - short_dry, abs=1e-12)


def test_headspace_critical_ratio_is_tank_only_and_inventory_cap_is_reported() -> None:
    ratio = tank_only_critical_headspace_ratio(1_200_000.0, 100_000.0, 1.0)
    assert ratio == pytest.approx(1.0 / 11.0)
    large_headspace = SealedGasBudgetCase(
        initial_pressure_abs_Pa=1_200_000.0,
        back_pressure_abs_Pa=100_000.0,
        tank_water_volume_m3=1.35,
        headspace_ratio_to_tank_water=0.225,
        wetted_feed_volume_m3=0.2539360223582692,
        initially_dry_downstream_volume_m3=0.4320037386471729,
        polytropic_exponent=1.0,
    )
    result = pressure_budget(large_headspace)
    assert result["equilibrium_nozzle_volume_was_inventory_capped"]
    assert result["inventory_capped_pressure_equilibrium_nozzle_volume_m3"] == pytest.approx(
        large_headspace.initial_liquid_inventory_m3
    )
    assert result["raw_pressure_equilibrium_gas_displacement_m3"] > (
        large_headspace.initially_dry_downstream_volume_m3
        + large_headspace.initial_liquid_inventory_m3
    )
    # At full hypothetical expulsion, the formula can remain above back pressure.
    assert result["pressure_after_hypothetical_expulsion_of_all_initial_water_abs_Pa"] > 100_000


@pytest.mark.parametrize(
    "updates",
    [
        {"initial_pressure_abs_Pa": 0.0},
        {"back_pressure_abs_Pa": -1.0},
        {"headspace_ratio_to_tank_water": 0.0},
        {"initially_dry_downstream_volume_m3": -1.0},
        {"polytropic_exponent": 0.0},
    ],
)
def test_invalid_budget_inputs_are_rejected(updates: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        pressure_budget(SealedGasBudgetCase(**{**_case().__dict__, **updates}))


def test_gas_pressure_function_rejects_nonpositive_expanded_volume() -> None:
    with pytest.raises(ValueError):
        pressure_after_gas_displacement_abs_Pa(100_000.0, 0.1, -0.1, 1.0)
    assert math.isfinite(pressure_after_gas_displacement_abs_Pa(100_000, 0.1, 0, 1.0))


def test_headspace_sweep_changes_total_capacity_at_fixed_water_volume() -> None:
    from scripts.analyze_i4f_pressure_budget import build_rows, read_geometry_inputs

    root = Path(__file__).resolve().parents[1]
    geometry = (
        root
        / "results/summaries/i4f_20261025/transition-length-comparison/analysis/geometry-comparison.json"
    )
    common, variants, _ = read_geometry_inputs(geometry)
    rows = build_rows(common, variants)
    capacities = {
        row["headspace_ratio_to_tank_water"]: row["tank_internal_capacity_assumed_m3"]
        for row in rows
        if row["initial_pressure_bar_abs"] == 12.0
        and row["geometry_key"] == "train_1p0m_reference"
        and row["polytropic_exponent_n"] == 1.0
    }
    assert capacities == pytest.approx({0.20: 1.62, 0.225: 1.65375, 0.25: 1.6875})


def test_cli_snapshots_inputs_and_accepts_external_output_without_overwrite(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts/analyze_i4f_pressure_budget.py"
    geometry = (
        root
        / "results/summaries/i4f_20261025/transition-length-comparison/analysis/geometry-comparison.json"
    )
    output = tmp_path / "external" / "pressure-budget"
    command = [
        sys.executable,
        str(script),
        "--geometry",
        str(geometry),
        "--output-dir",
        str(output),
    ]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    assert f"result: {output.resolve()}" in first.stdout
    manifest = json.loads((output / "pressure-budget.json").read_text())
    snapshot = output / manifest["source_snapshot_manifest"]
    snapshot_manifest = json.loads(snapshot.read_text())
    assert snapshot_manifest["capture_started_utc"] < snapshot_manifest["capture_completed_utc"]
    for key, expected in manifest["source_hashes"].items():
        if key in {"module", "script", "tests", "corrected_geometry_packet"}:
            role = {
                "corrected_geometry_packet": "geometry_packet",
            }.get(key, key)
            assert snapshot_manifest["files"][role]["sha256"] == expected
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode != 0
    assert "refusing to overwrite" in second.stderr
