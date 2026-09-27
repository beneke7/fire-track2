"""Regression checks for the independent Calbrix CL-415 Fig. 11(a) trace."""

from __future__ import annotations

import csv
import math
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/derived/calbrix_cl415_fig11_structure_counts_independent.csv"
FIRST_CSV_PATH = ROOT / "data/derived/calbrix_cl415_fig11_structure_counts.csv"
SCRIPT_PATH = ROOT / "scripts/digitize_calbrix_e3_fig11_independent.py"
PDF_PATH = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
SOURCE_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_independent_fig11_trace_is_a_bounded_raster_read() -> None:
    rows = _read(CSV_PATH)
    assert len(rows) == 60
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["series"]].append(row)
        assert row["source_pdf_sha256"] == SOURCE_SHA256
        assert int(row["render_dpi"]) == 300
        assert row["read_method"] == "local_theil_sen_center"
        assert int(row["read_bound_count"]) == 5
        assert float(row["read_bound_time_s"]) == 0.025
        assert all(
            math.isfinite(float(row[field]))
            for field in ("time_s", "count_digitized", "page_x_px", "page_y_px")
        )

    assert set(grouped) == {"cloud_alpha_0p001_to_1", "core_alpha_0p9_to_1"}
    times = [round(index / 10, 1) for index in range(1, 31)]
    for series_rows in grouped.values():
        assert [float(row["time_s"]) for row in series_rows] == times

    cloud = {
        float(row["time_s"]): int(row["count_digitized"])
        for row in grouped["cloud_alpha_0p001_to_1"]
    }
    core = {
        float(row["time_s"]): int(row["count_digitized"]) for row in grouped["core_alpha_0p9_to_1"]
    }
    assert all(cloud[t] >= core[t] >= 0 for t in times)
    assert 415 <= cloud[1.1] <= 425  # Above the highest labeled count tick.
    assert max(core.values()) in range(45, 65)

    first_by_key = {
        (row["series"], float(row["time_s"])): int(row["count_digitized"])
        for row in _read(FIRST_CSV_PATH)
    }
    independent_by_key = {
        (row["series"], float(row["time_s"])): int(row["count_digitized"]) for row in rows
    }
    differences = {
        series: [
            independent_by_key[(series, time_s)] - first_by_key[(series, time_s)]
            for time_s in times
        ]
        for series in grouped
    }
    assert max(abs(value) for value in differences["cloud_alpha_0p001_to_1"]) <= 4
    assert max(abs(value) for value in differences["core_alpha_0p9_to_1"]) <= 2


def test_independent_fig11_script_reproduces_csv(tmp_path: Path) -> None:
    if shutil.which("pdftoppm") is None or shutil.which("pdftotext") is None:
        pytest.skip("Poppler pdftoppm and pdftotext are required to reproduce this trace")
    if not PDF_PATH.is_file():
        pytest.skip("local Calbrix source PDF is unavailable")

    output_path = tmp_path / "reproduced.csv"
    env = {
        **os.environ,
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    }
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--output", str(output_path)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert output_path.read_bytes() == CSV_PATH.read_bytes()
