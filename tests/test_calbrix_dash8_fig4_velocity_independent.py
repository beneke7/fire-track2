"""Reproducibility and nominal-time read checks for the second Fig. 4 trace."""

from __future__ import annotations

import csv
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PDF = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
PRIMARY_CSV = ROOT / "data/derived/calbrix_dash8_fig4_velocity.csv"
INDEPENDENT_CSV = ROOT / "data/derived/calbrix_dash8_fig4_velocity_independent.csv"
GENERATOR = ROOT / "scripts/digitize_calbrix_dash8_fig4_velocity_independent.py"
EXPECTED_SOURCE_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"
EXPECTED_COLUMNS = {
    "time_s",
    "u_l_m_s",
    "figure_read_bound_time_s",
    "figure_read_bound_u_l_m_s",
    "source_pdf_sha256",
    "pdf_page",
    "journal_page",
    "figure",
    "series_id",
    "source_pixel_x",
    "source_pixel_y",
    "sample_kind",
    "read_method",
}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_independent_trace_has_source_and_nominal_read_provenance() -> None:
    rows = _read_rows(INDEPENDENT_CSV)
    assert len(rows) == 51
    assert set(rows[0]) == EXPECTED_COLUMNS
    assert {row["source_pdf_sha256"] for row in rows} == {EXPECTED_SOURCE_SHA256}
    assert {(row["pdf_page"], row["journal_page"], row["figure"]) for row in rows} == {
        ("5", "1519", "4")
    }
    assert {row["series_id"] for row in rows} == {"dash8_blue"}
    assert {row["read_method"] for row in rows} == {"blue_rgb_mask_column_median"}

    times = [float(row["time_s"]) for row in rows]
    speeds = [float(row["u_l_m_s"]) for row in rows]
    assert times[0] == 0.0 and times[-1] == 5.0
    assert all(math.isclose(b - a, 0.1, abs_tol=1e-12) for a, b in zip(times, times[1:]))
    assert all(math.isfinite(speed) and speed >= 0.0 for speed in speeds)
    assert speeds[0] == 0.0
    assert all(float(row["figure_read_bound_time_s"]) == 0.03 for row in rows)
    assert all(float(row["figure_read_bound_u_l_m_s"]) > 0.0 for row in rows)
    assert all(row["source_pixel_x"].isdigit() for row in rows)
    assert all(math.isfinite(float(row["source_pixel_y"])) for row in rows)

    primary = _read_rows(PRIMARY_CSV)
    assert len(primary) == len(rows)
    for old, new in zip(primary, rows, strict=True):
        assert old["time_s"] == new["time_s"]
        # This is only a same-time ordinate-read check. The time bounds are
        # correlated with ordinate error and must be propagated using the
        # local curve slope for any quantitative time-history comparison.
        difference = abs(float(new["u_l_m_s"]) - float(old["u_l_m_s"]))
        combined_ordinate_read = float(old["figure_read_bound_u_l_m_s"]) + float(
            new["figure_read_bound_u_l_m_s"]
        )
        assert difference <= combined_ordinate_read


def test_generator_reproduces_independent_trace_byte_for_byte(tmp_path: Path) -> None:
    if not SOURCE_PDF.is_file() or not shutil.which("pdftocairo") or not shutil.which("pdftoppm"):
        pytest.skip("source PDF and Poppler pdftocairo/pdftoppm are required")

    regenerated = tmp_path / "regenerated.csv"
    environment = os.environ.copy()
    environment.update(
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    subprocess.run(
        [sys.executable, str(GENERATOR), "--output", str(regenerated)],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert regenerated.read_bytes() == INDEPENDENT_CSV.read_bytes()
