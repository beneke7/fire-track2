"""Source-trace checks for the digitized CL-415 Fig. 11(a) histories."""

from __future__ import annotations

import csv
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CURVE_PATH = ROOT / "data" / "derived" / "calbrix_cl415_fig11_structure_counts.csv"
SCRIPT_PATH = ROOT / "scripts" / "digitize_calbrix_e3_fig11.py"
PDF_PATH = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
EXPECTED_COLUMNS = {
    "series",
    "time_s",
    "count_digitized",
    "read_bound_count",
    "read_bound_time_s",
    "plot_x_px",
    "plot_y_px",
}


def test_cl415_fig11_structure_counts_preserve_the_two_threshold_traces() -> None:
    with CURVE_PATH.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert set(reader.fieldnames or ()) == EXPECTED_COLUMNS
        rows = list(reader)

    grouped = {
        series: [row for row in rows if row["series"] == series]
        for series in ("cloud_alpha_0p001_to_1", "core_alpha_0p9_to_1")
    }
    assert len(rows) == 60
    expected_times = [round(index / 10, 1) for index in range(1, 31)]
    for series_rows in grouped.values():
        times = [float(row["time_s"]) for row in series_rows]
        counts = [int(row["count_digitized"]) for row in series_rows]
        assert times == expected_times
        assert all(count >= 0 for count in counts)
        assert all(int(row["read_bound_count"]) == 5 for row in series_rows)
        assert all(float(row["read_bound_time_s"]) == 0.01 for row in series_rows)
        assert all(math.isfinite(float(row["plot_y_px"])) for row in series_rows)

    cloud = {
        float(row["time_s"]): int(row["count_digitized"])
        for row in grouped["cloud_alpha_0p001_to_1"]
    }
    core = {
        float(row["time_s"]): int(row["count_digitized"]) for row in grouped["core_alpha_0p9_to_1"]
    }

    # Fig. 11's lower-alpha detector includes many more fragmented structures.
    assert all(cloud[time_s] >= core[time_s] for time_s in expected_times)
    assert cloud[0.1] in range(30, 45)
    assert core[0.1] <= 8

    # The plotted cloud peak is above the 400-count tick near 1.1 s; the core
    # trace peaks later at a much smaller count, then both decay toward 3 s.
    cloud_peak_time = max(cloud, key=cloud.__getitem__)
    core_peak_time = max(core, key=core.__getitem__)
    assert 1.0 <= cloud_peak_time <= 1.2
    assert 410 <= cloud[cloud_peak_time] <= 430
    assert 1.2 <= core_peak_time <= 1.5
    assert 45 <= core[core_peak_time] <= 65
    assert cloud[2.6] < 30 and cloud[3.0] < 45
    assert core[2.8] < 20 and core[3.0] < 20


def test_fig11_digitizer_reproduces_the_retained_csv(tmp_path: Path) -> None:
    if shutil.which("pdftoppm") is None:
        pytest.skip("Poppler pdftoppm is required to reproduce this trace")
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
