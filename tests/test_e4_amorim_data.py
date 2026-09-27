"""Independent source-level checks for the plotted M134 Fig. 9 digitization."""

from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = ROOT / "data" / "derived" / "amorim_m134_fig9.csv"
EXPECTED_COLUMNS = {
    "series",
    "marker_index",
    "x_page_pt",
    "y_page_pt",
    "x_m",
    "Vx_L",
}


def test_m134_fig9_trace_has_expected_markers_and_valid_plot_coordinates() -> None:
    with TRACE_PATH.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert set(reader.fieldnames or ()) == EXPECTED_COLUMNS
        rows = list(reader)

    measured = [row for row in rows if row["series"] == "measured"]
    adm = [row for row in rows if row["series"] == "adm"]
    assert len(measured) == 442
    assert len(adm) == 273

    for series_rows in (measured, adm):
        x_values = [float(row["x_m"]) for row in series_rows]
        vx_values = [float(row["Vx_L"]) for row in series_rows]
        assert all(math.isfinite(value) and 0.0 <= value <= 600.0 for value in x_values)
        assert all(math.isfinite(value) and 0.0 <= value <= 30.0 for value in vx_values)
        assert all(right > left for left, right in zip(x_values, x_values[1:]))
        assert [int(row["marker_index"]) for row in series_rows] == list(
            range(1, len(series_rows) + 1)
        )

    measured_peak_row = max(measured, key=lambda row: float(row["Vx_L"]))
    adm_peak_row = max(adm, key=lambda row: float(row["Vx_L"]))
    assert math.isclose(float(measured_peak_row["x_m"]), 284.100942, abs_tol=1e-6)
    assert math.isclose(float(measured_peak_row["Vx_L"]), 24.673916, abs_tol=1e-6)
    assert math.isclose(float(adm_peak_row["x_m"]), 362.814726, abs_tol=1e-6)
    assert math.isclose(float(adm_peak_row["Vx_L"]), 25.229113, abs_tol=1e-6)
