"""Source-trace checks for the CL-415 outlet-velocity reads in Fig. 4."""

from __future__ import annotations

import csv
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CURVE_PATH = ROOT / "data" / "derived" / "calbrix_cl415_fig4_velocities.csv"
SCRIPT_PATH = ROOT / "scripts" / "digitize_calbrix_e3_fig4.py"
PDF_PATH = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
EXPECTED_COLUMNS = {
    "series",
    "time_s",
    "max_exit_velocity_digitized_m_s",
    "read_bound_velocity_m_s",
    "read_bound_time_s",
    "plot_x_px",
    "plot_y_px",
}


def test_cl415_fig4_contains_two_bounded_legend_mapped_scalar_traces() -> None:
    with CURVE_PATH.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert set(reader.fieldnames or ()) == EXPECTED_COLUMNS
        rows = list(reader)

    grouped = {
        series: [row for row in rows if row["series"] == series]
        for series in ("cl415_top_exit_red", "cl415_bottom_exit_green")
    }
    assert len(rows) == 75
    assert [row["series"] for row in rows[:36]] == ["cl415_top_exit_red"] * 36
    assert [row["series"] for row in rows[36:]] == ["cl415_bottom_exit_green"] * 39

    for series, end_s in (("cl415_top_exit_red", 1.80), ("cl415_bottom_exit_green", 1.95)):
        series_rows = grouped[series]
        times = [float(row["time_s"]) for row in series_rows]
        velocities = [float(row["max_exit_velocity_digitized_m_s"]) for row in series_rows]
        assert times == [round(index / 20, 2) for index in range(1, round(end_s * 20) + 1)]
        assert all(math.isfinite(value) and value >= 0 for value in velocities)
        assert all(float(row["read_bound_velocity_m_s"]) == 0.05 for row in series_rows)
        assert all(float(row["read_bound_time_s"]) == 0.01 for row in series_rows)
        assert all(21 <= float(row["plot_x_px"]) <= 1473 for row in series_rows)
        assert all(53 <= float(row["plot_y_px"]) < 1198 for row in series_rows)
        # The last supported colored feature is a low positive figure read, not
        # a fabricated zero-valued shutoff endpoint.
        assert times[-1] == end_s < 2.0
        assert 0 < velocities[-1] < 0.25

    red = {
        float(row["time_s"]): float(row["max_exit_velocity_digitized_m_s"])
        for row in grouped["cl415_top_exit_red"]
    }
    green = {
        float(row["time_s"]): float(row["max_exit_velocity_digitized_m_s"])
        for row in grouped["cl415_bottom_exit_green"]
    }
    red_peak_time = max(red, key=red.__getitem__)
    green_peak_time = max(green, key=green.__getitem__)

    # Fig. 4 shows the green bottom-exit peak near 6 m/s above the red top-exit
    # peak, with both peaks around half a second; the blue Dash-8 trace is absent.
    assert 5.4 <= red[red_peak_time] <= 5.7
    assert 0.45 <= red_peak_time <= 0.55
    assert 5.8 <= green[green_peak_time] <= 6.1
    assert 0.50 <= green_peak_time <= 0.60
    assert green[1.0] > red[1.0]
    assert set(grouped) == {"cl415_top_exit_red", "cl415_bottom_exit_green"}


def test_cl415_fig4_digitizer_reproduces_the_retained_csv(tmp_path: Path) -> None:
    if shutil.which("pdftoppm") is None:
        pytest.skip("Poppler pdftoppm is required to reproduce these traces")
    if not PDF_PATH.is_file():
        pytest.skip("local Calbrix source PDF is unavailable")

    output_path = tmp_path / "reproduced.csv"
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--output", str(output_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert output_path.read_bytes() == CURVE_PATH.read_bytes()
