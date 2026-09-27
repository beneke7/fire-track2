"""Provenance and cross-checks for Rouaix Case 1 curve extractions."""

from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURVE_PATH = ROOT / "data" / "derived" / "rouaix_e1_case1_fig13.csv"
RASTER_CURVE_PATH = ROOT / "data" / "derived" / "rouaix_e1_case1_fig13_raster.csv"
EXPECTED_COLUMNS = {
    "observable",
    "x_over_dj",
    "value_over_dj",
    "sigma_value_over_dj",
    "sigma_x_over_dj",
}


def test_rouaix_case1_figure_13_csv_has_separate_monotone_curves_and_bounds() -> None:
    with CURVE_PATH.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert set(reader.fieldnames or ()) == EXPECTED_COLUMNS
        rows = list(reader)

    penetration = [row for row in rows if row["observable"] == "penetration_y"]
    width = [row for row in rows if row["observable"] == "width_z"]
    assert len(penetration) == 21
    assert len(width) == 11
    assert len(rows) == 32

    for series, value_sigma, x_sigma in (
        (penetration, 0.07, 0.02),
        (width, 0.04, 0.01),
    ):
        xs = [float(row["x_over_dj"]) for row in series]
        values = [float(row["value_over_dj"]) for row in series]
        for row in series:
            assert all(
                math.isfinite(float(row[column])) for column in EXPECTED_COLUMNS - {"observable"}
            )
            assert float(row["sigma_value_over_dj"]) == value_sigma
            assert float(row["sigma_x_over_dj"]) == x_sigma
        assert all(right > left for left, right in zip(xs, xs[1:], strict=False))
        assert all(right >= left for left, right in zip(values, values[1:], strict=False))
        assert all(value >= 0.0 for value in values)


def test_independent_raster_trace_agrees_with_vector_trace_within_recorded_bounds() -> None:
    with CURVE_PATH.open(encoding="utf-8", newline="") as stream:
        primary_rows = list(csv.DictReader(stream))
    with RASTER_CURVE_PATH.open(encoding="utf-8", newline="") as stream:
        raster_reader = csv.DictReader(stream)
        expected_raster_columns = {
            "observable",
            "x_over_dj",
            "value_over_dj_raster",
            "sigma_raster_bound",
            "source_value_over_dj",
            "source_sigma_value_bound",
            "source_sigma_x_bound",
            "local_abs_slope",
            "trace_window_px",
            "trace_columns",
            "trace_xpix_min",
            "trace_xpix_max",
        }
        assert set(raster_reader.fieldnames or ()) == expected_raster_columns
        raster_rows = list(raster_reader)

    def point_key(row: dict[str, str]) -> tuple[str, float]:
        return row["observable"], float(row["x_over_dj"])

    primary_by_point = {point_key(row): row for row in primary_rows}
    assert len(raster_rows) == len(primary_rows) == 32
    assert {point_key(row) for row in raster_rows} == set(primary_by_point)

    squared_errors: dict[str, list[float]] = {"penetration_y": [], "width_z": []}
    for raster_row in raster_rows:
        observable = raster_row["observable"]
        primary_row = primary_by_point[point_key(raster_row)]
        primary_value = float(primary_row["value_over_dj"])
        raster_value = float(raster_row["value_over_dj_raster"])
        raster_sigma = float(raster_row["sigma_raster_bound"])
        propagated_x_sigma = abs(float(raster_row["local_abs_slope"])) * float(
            primary_row["sigma_x_over_dj"]
        )
        combined_bound = (
            float(primary_row["sigma_value_over_dj"]) + propagated_x_sigma + raster_sigma
        )
        assert abs(raster_value - primary_value) <= combined_bound
        squared_errors[observable].append((raster_value - primary_value) ** 2)

    penetration_rmse = math.sqrt(sum(squared_errors["penetration_y"]) / 21)
    width_rmse = math.sqrt(sum(squared_errors["width_z"]) / 11)
    assert 0.018 < penetration_rmse < 0.020
    assert 0.027 < width_rmse < 0.029
