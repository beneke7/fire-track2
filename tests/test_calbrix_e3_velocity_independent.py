"""Regression checks for the independent CL-415 Fig. 4 trace extraction."""

from __future__ import annotations

import csv
import math
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CURVE_PATH = ROOT / "data/derived/calbrix_cl415_fig4_velocities_independent.csv"
SCRIPT_PATH = ROOT / "scripts/digitize_calbrix_e3_fig4_independent.py"
PDF_PATH = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"
EXPECTED_COLUMNS = {
    "source_pdf_sha256",
    "pdf_page",
    "journal_page",
    "figure",
    "series_id",
    "exit_label",
    "figure_color",
    "time_s",
    "u_l_m_s",
    "sample_kind",
    "source_pixel_x",
    "source_pixel_y",
    "figure_read_bound_time_s",
    "figure_read_bound_u_l_m_s",
}


def _rows() -> list[dict[str, str]]:
    with CURVE_PATH.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert set(reader.fieldnames or ()) == EXPECTED_COLUMNS
        return list(reader)


def test_independent_cl415_fig4_traces_preserve_caption_mapping_and_visible_tails() -> None:
    rows = _rows()
    assert len(rows) == 42

    grouped = {
        series_id: [row for row in rows if row["series_id"] == series_id]
        for series_id in ("cl415_top_exit_red", "cl415_bottom_exit_green")
    }
    assert {key: len(value) for key, value in grouped.items()} == {
        "cl415_top_exit_red": 21,
        "cl415_bottom_exit_green": 21,
    }
    assert (
        grouped["cl415_top_exit_red"][0]["exit_label"],
        grouped["cl415_top_exit_red"][0]["figure_color"],
    ) == (
        "top_exit",
        "red",
    )
    assert (
        grouped["cl415_bottom_exit_green"][0]["exit_label"],
        grouped["cl415_bottom_exit_green"][0]["figure_color"],
    ) == ("bottom_exit", "green")

    for series_id, series_rows in grouped.items():
        times = [float(row["time_s"]) for row in series_rows]
        assert times == sorted(times)
        assert Counter(row["sample_kind"] for row in series_rows) == {
            "visible_start": 1,
            "uniform_0p1s": 19,
            "visible_end": 1,
        }
        for row in series_rows:
            assert row["source_pdf_sha256"] == EXPECTED_PDF_SHA256
            assert row["pdf_page"] == "5"
            assert row["journal_page"] == "1519"
            assert row["figure"] == "4"
            for field in (
                "time_s",
                "u_l_m_s",
                "source_pixel_x",
                "source_pixel_y",
                "figure_read_bound_time_s",
                "figure_read_bound_u_l_m_s",
            ):
                assert math.isfinite(float(row[field]))
            velocity = float(row["u_l_m_s"])
            assert 0.0 < velocity <= 6.1
            assert 0.0 < float(row["figure_read_bound_time_s"]) < 0.2
            assert 0.0 < float(row["figure_read_bound_u_l_m_s"]) < 0.25
            assert 282 <= float(row["source_pixel_x"]) <= 683
            assert 1143 <= float(row["source_pixel_y"]) <= 1830

        peak = max(series_rows, key=lambda row: float(row["u_l_m_s"]))
        assert 0.45 <= float(peak["time_s"]) <= 0.65
        assert 5.3 <= float(peak["u_l_m_s"]) <= 6.1

        end = next(row for row in series_rows if row["sample_kind"] == "visible_end")
        # These are visible raster centers, not fitted shutoff times. In
        # particular, retain the positive low tail without appending U_L=0.
        assert 1.9 < float(end["time_s"]) < 2.1
        assert 0.0 < float(end["u_l_m_s"]) < 0.1


def test_independent_digitizer_reproduces_the_retained_csv(tmp_path: Path) -> None:
    if shutil.which("pdftoppm") is None:
        pytest.skip("Poppler pdftoppm is required to reproduce these traces")
    if not PDF_PATH.is_file():
        pytest.skip("local Calbrix source PDF is unavailable")

    output_path = tmp_path / "reproduced.csv"
    environment = os.environ.copy()
    environment.update(
        {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    )
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--output", str(output_path)],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert output_path.read_bytes() == CURVE_PATH.read_bytes()
