"""Regression checks for raster traces from Calbrix et al. Figs. 6–9."""

from __future__ import annotations

import csv
import math
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest

from scripts.digitize_calbrix_dash8_cloud_curves import _fig9_specs
from scripts.digitize_calbrix_dash8_cloud_curves_independent import (
    PANELS as INDEPENDENT_PANELS,
)
from scripts.digitize_calbrix_dash8_cloud_curves_independent import (
    RENDER_DPI,
)

ROOT = Path(__file__).resolve().parents[1]
CURVE_PATH = ROOT / "data/derived/calbrix_dash8_cloud_curves.csv"
SCRIPT_PATH = ROOT / "scripts/digitize_calbrix_dash8_cloud_curves.py"
PDF_PATH = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
EXPECTED_COLUMNS = {
    "figure",
    "pdf_page",
    "journal_page",
    "panel",
    "aircraft",
    "alpha_l_threshold",
    "series_id",
    "time_s",
    "time_candidates_s",
    "time_status",
    "independent_variable",
    "independent_value",
    "independent_unit",
    "dependent_variable",
    "dependent_value",
    "dependent_unit",
    "segment_id",
    "branch_id",
    "point_index",
    "read_bound_independent",
    "read_bound_dependent",
}
AXIS_LIMITS = {
    6: (0.0, 2.0, 0.0, 3.0),
    7: (0.0, 2.0, 0.0, 2.0),
    8: (0.0, 3.5, 0.0, 6.0),
    9: (0.0, 8.0, 0.0, 9.0),
}
SOURCE_PAGES = {6: (7, 1521), 7: (8, 1522), 8: (9, 1523), 9: (9, 1523)}


def _read_rows() -> list[dict[str, str]]:
    with CURVE_PATH.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert set(reader.fieldnames or ()) == EXPECTED_COLUMNS
        return list(reader)


def test_figures_6_to_9_cloud_traces_have_valid_units_ranges_and_bounds() -> None:
    rows = _read_rows()
    assert len(rows) >= 4_500
    assert {int(row["figure"]) for row in rows} == set(AXIS_LIMITS)
    assert {row["alpha_l_threshold"] for row in rows} == {"0.001"}
    assert {row["aircraft"] for row in rows} == {"Dash-8"}
    for row in rows:
        figure = int(row["figure"])
        assert (int(row["pdf_page"]), int(row["journal_page"])) == SOURCE_PAGES[figure]
        if figure == 9:
            assert row["panel"] == "a"

    grouped: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        figure = int(row["figure"])
        independent = float(row["independent_value"])
        dependent = float(row["dependent_value"])
        independent_bound = float(row["read_bound_independent"])
        dependent_bound = float(row["read_bound_dependent"])
        assert all(
            math.isfinite(value)
            for value in (independent, dependent, independent_bound, dependent_bound)
        )
        assert independent_bound > 0 and dependent_bound > 0
        x_min, x_max, y_min, y_max = AXIS_LIMITS[figure]
        assert x_min <= independent <= x_max
        assert y_min <= dependent <= y_max
        grouped[(figure, row["series_id"])].append(row)

    expected_series = {
        (6, "dash8_t0.5s"),
        (7, "dash8_simulation_t0.5s"),
        (8, "dash8_time_conflict"),
        (9, "dash8_t0.5s"),
        (9, "dash8_t1.0s"),
        (9, "dash8_t1.5s"),
    }
    assert set(grouped) == expected_series

    # The first plotted pixel in each series is a broad anchor, not a fitted
    # value. Its tolerance is intentionally wider than the stored raster bound.
    anchors = {
        (6, "dash8_t0.5s"): (0.0283, 0.02),
        (7, "dash8_simulation_t0.5s"): (0.0283, 0.0109),
        (8, "dash8_time_conflict"): (0.0, 0.049),
        # The first retained mark is the small red fragment near the plot
        # origin; it is not evidence of exact continuity to the larger curve.
        (9, "dash8_t0.5s"): (0.006, 0.0),
    }
    for key, (expected_independent, expected_dependent) in anchors.items():
        first = min(grouped[key], key=lambda row: int(row["point_index"]))
        assert math.isclose(float(first["independent_value"]), expected_independent, abs_tol=0.04)
        assert math.isclose(float(first["dependent_value"]), expected_dependent, abs_tol=0.12)

    # The normalized axes stay dimensionless, and the reported Fig. 8 time
    # contradiction remains explicit rather than being resolved in the data.
    assert {
        (r["independent_unit"], r["dependent_unit"]) for r in grouped[(7, "dash8_simulation_t0.5s")]
    } == {("1", "1")}
    assert {(r["independent_unit"], r["dependent_unit"]) for r in grouped[(9, "dash8_t1.0s")]} == {
        ("1", "1")
    }
    fig8 = grouped[(8, "dash8_time_conflict")]
    assert {row["time_s"] for row in fig8} == {""}
    assert {row["time_candidates_s"] for row in fig8} == {"body=0.5;caption=1.0"}
    assert {row["time_status"] for row in fig8} == {"conflict"}

    # Figure 7's visible gap is represented as two separately indexed traces;
    # it is not silently bridged with interpolated points.
    fig7 = grouped[(7, "dash8_simulation_t0.5s")]
    segments: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in fig7:
        segments[int(row["segment_id"])].append(row)
    assert set(segments) == {1, 2}
    first_end = max(float(row["independent_value"]) for row in segments[1])
    second_start = min(float(row["independent_value"]) for row in segments[2])
    assert second_start - first_end > 0.3


def test_primary_fig9_vertical_ticks_match_independent_source_calibration() -> None:
    primary = _fig9_specs("red", "test", 0.5)
    second = INDEPENDENT_PANELS["fig9"]
    to_primary_dpi = 300 / RENDER_DPI
    expected_zero = (second.crop_y + second.y_zero_px) * to_primary_dpi
    expected_eight = (second.crop_y + second.y_max_px) * to_primary_dpi
    assert math.isclose(primary.y0_px, expected_zero, abs_tol=1)
    assert math.isclose(primary.y1_px, expected_eight, abs_tol=1)


def test_fig9_near_origin_red_blue_fragments_are_separate_and_bounded() -> None:
    rows = [row for row in _read_rows() if int(row["figure"]) == 9]
    for series, expected_fragments in (("dash8_t0.5s", 2), ("dash8_t1.0s", 3)):
        series_rows = [row for row in rows if row["series_id"] == series]
        near_origin = [
            row
            for row in series_rows
            if float(row["independent_value"]) <= 0.35 and float(row["dependent_value"]) <= 0.4
        ]
        segments = {int(row["segment_id"]) for row in near_origin}
        assert len(segments) >= expected_fragments
        assert all(float(row["read_bound_independent"]) >= 0.07 for row in near_origin)
        assert all(float(row["read_bound_dependent"]) >= 0.08 for row in near_origin)
        assert min(float(row["independent_value"]) for row in near_origin) > 0


def test_digitization_regenerates_deterministically(tmp_path: Path) -> None:
    if shutil.which("pdftoppm") is None:
        pytest.skip("Poppler pdftoppm is required to regenerate raster traces")
    if not PDF_PATH.is_file():
        pytest.skip("local Calbrix source PDF is unavailable")

    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    for output_path in (first_path, second_path):
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--output", str(output_path)],
            check=True,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert first_path.read_bytes() == second_path.read_bytes()

    renderer = subprocess.run(["pdftoppm", "-v"], check=False, capture_output=True, text=True)
    if "version 24.02.0" in (renderer.stdout + renderer.stderr):
        assert first_path.read_bytes() == CURVE_PATH.read_bytes()
