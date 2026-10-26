#!/usr/bin/env python3
"""Recompute the selected local Sp/residual comparison and pressure tail."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / "full-replay/pressure-cycle-events.csv"
REFERENCE = ROOT / "stage03-comparison/local-source-term-ratio.json"
OUTPUT = ROOT / "local-source-mismatch.json"
TAIL = ROOT / "same-cell-final-six-outer-tail.csv"
TAIL_COLUMNS = (
    "time_s",
    "time_index",
    "outer_iteration",
    "rank",
    "local_cell",
    "signed_outer_dp_Pa",
    "abs_outer_dp_Pa",
    "p_before_Pa",
    "p_after_Pa",
    "alpha_before_outer",
    "alpha_after_outer",
    "alpha_after_implicit_predictor",
    "alpha_after_MULES_corrector",
    "predictor_Sp_per_s",
    "corrector_Sp_recomputed_per_s",
    "water_postEOS_phase_continuity_kg_m3_s",
    "C_x_m",
    "C_y_m",
    "C_z_m",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_percentile(values: list[float], probability: float) -> float:
    """Match capture_compare.py's floor-index percentile convention."""
    ordered = sorted(values)
    return ordered[int(probability * (len(ordered) - 1))]


def number(row: dict[str, str], name: str) -> float:
    value = float(row[name])
    if not math.isfinite(value):
        raise ValueError(f"nonfinite {name} in selected event row")
    return value


def local_ratio(row: dict[str, str]) -> dict[str, float]:
    delta_sp = number(row, "corrector_Sp_recomputed_per_s") - number(
        row, "predictor_Sp_per_s"
    )
    delta_alpha = number(row, "alpha_after_MULES_corrector") - number(
        row, "alpha_after_implicit_predictor"
    )
    d_value = delta_sp * delta_alpha
    rho_d = number(row, "rho_water_after_kg_m3") * d_value
    continuity = number(row, "water_postEOS_phase_continuity_kg_m3_s")
    if continuity == 0:
        raise ZeroDivisionError("selected event has zero water continuity residual")
    return {
        "delta_Sp_per_s": delta_sp,
        "delta_alpha_F_minus_P": delta_alpha,
        "D_per_s": d_value,
        "rho_times_D_kg_m3_s": rho_d,
        "water_postEOS_phase_continuity_kg_m3_s": continuity,
        "signed_ratio_rhoD_over_residual": rho_d / continuity,
    }


def main() -> None:
    with EVENTS.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("event CSV has no header")
        rows = list(reader)
    if len(rows) != 118:
        raise ValueError(f"expected 118 full-replay events, found {len(rows)}")

    ratios: list[float] = []
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    keyed_rows: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        derived = local_ratio(row)
        ratio = derived["signed_ratio_rhoD_over_residual"]
        ratios.append(ratio)
        groups[(row["rank"], row["local_cell"])].append(ratio)
        keyed_rows[(row["rank"], row["local_cell"], row["time_s"])].append(row)

    recurrent = [ratio for values in groups.values() if len(values) > 1 for ratio in values]
    recurrent_groups = [values for values in groups.values() if len(values) > 1]
    if len(recurrent) != 88 or len(recurrent_groups) != 21:
        raise ValueError(
            f"recurrent cohort mismatch: rows={len(recurrent)} cells={len(recurrent_groups)}"
        )

    highlight_matches = [
        row
        for row in rows
        if row["rank"] == "7"
        and row["local_cell"] == "1164"
        and row["time_s"] == "0.48199621213"
        and row["outer_iteration"] == "1535"
    ]
    if len(highlight_matches) != 1:
        raise ValueError(f"expected one highlighted same-cell row, found {len(highlight_matches)}")
    highlight = highlight_matches[0]
    arithmetic = local_ratio(highlight)
    existing = json.loads(REFERENCE.read_text(encoding="utf-8"))
    quoted = existing["quoted_cell_rows"]
    matching_quoted = [
        row
        for row in quoted
        if row.get("rank") == 7
        and row.get("local_cell") == 1164
        and row.get("time_s") == float(highlight["time_s"])
        and row.get("outer_iteration") == 1535
    ]
    if len(matching_quoted) != 1:
        raise ValueError("existing A-analysis highlighted row does not match event CSV")
    quoted_ratio = float(matching_quoted[0]["signed_ratio_rhoD_over_residual"])
    if abs(quoted_ratio - arithmetic["signed_ratio_rhoD_over_residual"]) > 1e-10:
        raise ValueError("recomputed highlighted ratio disagrees with existing A analysis")

    tail_key = ("7", "1164", "0.48199621213")
    tail = sorted(
        keyed_rows[tail_key], key=lambda row: int(row["outer_iteration"])
    )
    expected_iterations = [1531, 1532, 1533, 1534, 1535, 1536]
    actual_iterations = [int(row["outer_iteration"]) for row in tail]
    if actual_iterations != expected_iterations:
        raise ValueError(f"same-cell pressure tail mismatch: {actual_iterations}")
    with TAIL.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=TAIL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(tail)

    signed = [
        row["signed_outer_dp_Pa"]
        for row in tail
    ]
    abs_values = [abs(value) for value in recurrent]
    output: dict[str, Any] = {
        "schema": "i4f-pressure-cycle-local-sp-arithmetic/v1",
        "event_csv": {
            "path": "full-replay/pressure-cycle-events.csv",
            "sha256": sha(EVENTS),
            "event_rows": len(rows),
            "formula_source_path": "stage03-comparison/local-source-term-ratio.json",
            "formula_source_sha256": sha(REFERENCE),
        },
        "featured_row": {
            "time_s": float(highlight["time_s"]),
            "outer_iteration": int(highlight["outer_iteration"]),
            "rank": int(highlight["rank"]),
            "local_cell": int(highlight["local_cell"]),
            "coordinate_m": [
                float(highlight["C_x_m"]),
                float(highlight["C_y_m"]),
                float(highlight["C_z_m"]),
            ],
            "alpha_before_outer": float(highlight["alpha_before_outer"]),
            "predictor_Sp_per_s": float(highlight["predictor_Sp_per_s"]),
            "corrector_Sp_recomputed_per_s": float(
                highlight["corrector_Sp_recomputed_per_s"]
            ),
            "alpha_after_implicit_predictor": float(
                highlight["alpha_after_implicit_predictor"]
            ),
            "alpha_after_MULES_corrector": float(
                highlight["alpha_after_MULES_corrector"]
            ),
            "rho_water_after_kg_m3": float(highlight["rho_water_after_kg_m3"]),
            **arithmetic,
            "relative_difference_from_local_continuity_percent": 100
            * (arithmetic["signed_ratio_rhoD_over_residual"] - 1),
            "comparison_to_existing_A_analysis": "matches the quoted row within 1e-10 ratio",
        },
        "recurrent_row_distribution": {
            "all_valid_event_rows": len(ratios),
            "recurrent_cell_count": len(recurrent_groups),
            "recurrent_event_row_count": len(recurrent),
            "median_signed_ratio": sorted(recurrent)[len(recurrent) // 2]
            if len(recurrent) % 2
            else (sorted(recurrent)[len(recurrent)//2-1] + sorted(recurrent)[len(recurrent)//2]) / 2,
            "median_absolute_ratio": sorted(abs_values)[len(abs_values) // 2]
            if len(abs_values) % 2
            else (sorted(abs_values)[len(abs_values)//2-1] + sorted(abs_values)[len(abs_values)//2]) / 2,
            "p10_absolute_ratio": source_percentile(abs_values, 0.10),
            "p90_absolute_ratio": source_percentile(abs_values, 0.90),
            "min_signed_ratio": min(recurrent),
            "max_signed_ratio": max(recurrent),
            "negative_ratio_rows": sum(value < 0 for value in recurrent),
            "rows_with_ratio_0p9_to_1p1": sum(0.9 <= value <= 1.1 for value in recurrent),
            "existing_A_summary": existing["recurrent_row_ratio_summary"],
        },
        "same_cell_six_outer_tail": {
            "path": "same-cell-final-six-outer-tail.csv",
            "sha256": sha(TAIL),
            "time_s": float(tail[0]["time_s"]),
            "rank": 7,
            "local_cell": 1164,
            "outer_iterations": actual_iterations,
            "signed_pressure_updates_Pa": [float(value) for value in signed],
            "source_event_rows_match": True,
        },
        "qualification": (
            "D=(corrector Sp recomputed - predictor Sp)*(alpha after MULES - alpha after implicit predictor). "
            "rho_water*D and the same-row post-EOS local water continuity residual both have units kg m^-3 s^-1. "
            "The highlighted 0.3037% mismatch is one row only. Across all 88 recurrent event rows in 21 cells, "
            "ratios are widely distributed and often change sign; this is descriptive local arithmetic, not a "
            "global conservation result or a causal explanation of the pressure cycle."
        ),
    }
    OUTPUT.write_text(
        json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "featured_ratio": arithmetic["signed_ratio_rhoD_over_residual"],
        "relative_difference_percent": output["featured_row"]["relative_difference_from_local_continuity_percent"],
        "recurrent_rows": len(recurrent),
        "recurrent_cells": len(recurrent_groups),
        "median_abs_ratio": output["recurrent_row_distribution"]["median_absolute_ratio"],
        "p90_abs_ratio": output["recurrent_row_distribution"]["p90_absolute_ratio"],
        "negative_rows": output["recurrent_row_distribution"]["negative_ratio_rows"],
        "six_tail_rows": len(tail),
    }, indent=2))


if __name__ == "__main__":
    main()
