from __future__ import annotations

import math

import numpy as np

from scripts.continue_rouaix_case import (
    _decompose_dict,
    _parse_event_stability_log,
    _right_endpoint_step_integral,
    continuation_ledger,
)


def test_continuation_ledger_carries_nonzero_checkpoint_inventory_once() -> None:
    result = continuation_ledger(
        initial_inventory_kg=8.0,
        final_inventory_kg=8.75,
        prior_released_kg=10.0,
        prior_escaped_kg=2.0,
        incremental_source_kg=1.0,
        incremental_escaped_kg=0.25,
    )

    assert math.isclose(result["parent_checkpoint_residual_kg"], 0.0, abs_tol=1e-14)
    assert math.isclose(result["incremental_residual_kg"], 0.0, abs_tol=1e-14)
    assert math.isclose(result["cumulative_residual_kg"], 0.0, abs_tol=1e-14)
    assert math.isclose(result["total_released_kg"], 11.0, abs_tol=1e-14)
    assert math.isclose(result["total_escaped_kg"], 2.25, abs_tol=1e-14)


def test_nonzero_checkpoint_inventory_closes_against_new_release() -> None:
    result = continuation_ledger(
        initial_inventory_kg=8.0,
        final_inventory_kg=9.0,
        prior_released_kg=10.0,
        prior_escaped_kg=2.0,
        incremental_source_kg=1.0,
        incremental_escaped_kg=0.0,
    )

    assert math.isclose(result["initial_inventory_kg"], 8.0, abs_tol=1e-14)
    assert math.isclose(result["incremental_residual_kg"], 0.0, abs_tol=1e-14)
    assert math.isclose(result["cumulative_residual_kg"], 0.0, abs_tol=1e-14)


def test_alpha_phi_step_integral_uses_solver_interval_values() -> None:
    volume = _right_endpoint_step_integral(
        0.4,
        np.array([0.401, 0.402, 0.403]),
        np.array([0.02, 0.03, 0.01]),
        0.001,
    )

    assert math.isclose(volume, 0.00006, rel_tol=0, abs_tol=1e-16)


def test_event_stability_parser_keeps_courant_and_preclip_alpha_bounds(tmp_path) -> None:
    log = tmp_path / "flow.log"
    log.write_text(
        """Courant Number mean: 0.31 max: 7.70
Interface Courant Number mean: 0.001 max: 4.15
Time = 0.604
isoAdvection: After conservative bounding: min(alpha) = -4.63e-09, max(alpha) = 1 + 6.5e-13
Phase-1 volume fraction = 0.000312 Min(alpha.water) = -1e-15 Max(alpha.water) = 1
""",
        encoding="utf-8",
    )

    rows = _parse_event_stability_log(log, 0.6, 0.62)

    assert rows == [
        {
            "time_s": 0.604,
            "courant_mean": 0.31,
            "courant_max": 7.7,
            "interface_courant_mean": 0.001,
            "interface_courant_max": 4.15,
            "conservative_bounding_min_alpha": -4.63e-9,
            "conservative_bounding_max_alpha_expression": "1 + 6.5e-13",
            "phase1_volume_fraction": 0.000312,
        }
    ]


def test_event_stability_parser_ignores_reconstruction_time_without_solver_metrics(
    tmp_path,
) -> None:
    log = tmp_path / "flow.log"
    log.write_text(
        """Courant Number mean: 0.31 max: 7.70
Interface Courant Number mean: 0.001 max: 4.15
Time = 0.604
isoAdvection: After conservative bounding: min(alpha) = -4.63e-09, max(alpha) = 1 + 6.5e-13
Phase-1 volume fraction = 0.000312 Min(alpha.water) = -1e-15 Max(alpha.water) = 1

Time = 0.604
Reconstructing FV fields
""",
        encoding="utf-8",
    )

    rows = _parse_event_stability_log(log, 0.6, 0.62)

    assert len(rows) == 1
    assert rows[0]["time_s"] == 0.604
    assert rows[0]["conservative_bounding_min_alpha"] == -4.63e-9


def test_four_rank_decomposition_dictionary_is_explicit_and_valid() -> None:
    text = _decompose_dict(4)

    assert "numberOfSubdomains 4;" in text
    assert "n (2 2 1);" in text
    assert _decompose_dict(16).count("numberOfSubdomains 16;") == 1
