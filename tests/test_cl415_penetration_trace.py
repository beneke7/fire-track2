"""Checks for the digitized CL-415 Fig. 6(b) penetration trace."""

from __future__ import annotations

import csv
import math
import shutil
from pathlib import Path

import pytest

from scripts.digitize_cl415_penetration import (
    DEFAULT_OUTPUT,
    EXPECTED_PDF_SHA256,
    PANEL,
    SOURCE_PDF,
    digitize,
)


def _rows(path: Path = DEFAULT_OUTPUT) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_checked_in_trace_has_source_axes_and_red_cl415_identity() -> None:
    rows = _rows()
    assert 300 <= len(rows) <= 370
    assert {row["source_pdf_sha256"] for row in rows} == {EXPECTED_PDF_SHA256}
    assert {
        (row["pdf_page"], row["journal_page"], row["figure"], row["panel"]) for row in rows
    } == {("7", "1521", "Fig. 6(b)", "b")}
    assert {row["aircraft"] for row in rows} == {"CL-415"}
    assert {row["alpha_l_threshold"] for row in rows} == {"0.001"}
    assert {row["series_id"] for row in rows} == {"cl415_alpha0p001_t0.5s"}
    assert {row["time_s"] for row in rows} == {"0.5"}
    assert {row["legend_color"] for row in rows} == {"red"}
    assert {row["sample_step_px"] for row in rows} == {"4"}
    assert [int(row["point_index"]) for row in rows] == list(range(len(rows)))
    assert {row["axis_x_variable"] for row in rows} == {"streamwise_distance_y"}
    assert {row["axis_y_variable"] for row in rows} == {"vertical_penetration_Z"}
    assert {row["axis_x_unit"] for row in rows} == {"m"}
    assert {row["axis_y_unit"] for row in rows} == {"m"}
    assert {row["read_bound_streamwise_y_m"] for row in rows} == {"0.020"}
    assert {row["read_bound_vertical_Z_m"] for row in rows} == {"0.030"}

    x_values = [float(row["x_value"]) for row in rows]
    z_values = [float(row["y_value"]) for row in rows]
    assert x_values == sorted(x_values)
    assert 0.04 < x_values[0] < 0.07
    assert 1.93 < x_values[-1] < 1.98
    # The red CL-415 curve ends near Z=2.25 m; the blue Dash-8 trace bends
    # upward at the right edge and has a deeper maximum near 2.45 m.
    assert 2.15 < max(z_values) < 2.35

    for row in (rows[0], rows[len(rows) // 2], rows[-1]):
        pixel_x = float(row["plot_x_px"])
        pixel_z = float(row["plot_y_px"])
        expected_y = (
            (pixel_x - PANEL.x_zero_px) * PANEL.x_max_value / (PANEL.x_max_px - PANEL.x_zero_px)
        )
        expected_penetration = (
            (pixel_z - PANEL.y_zero_px) * PANEL.y_max_value / (PANEL.y_max_px - PANEL.y_zero_px)
        )
        assert math.isclose(float(row["x_value"]), expected_y, abs_tol=1e-5)
        assert math.isclose(float(row["y_value"]), expected_penetration, abs_tol=1e-5)
        assert float(row["page_x_px"]) == float(row["crop_x_px"]) + pixel_x
        assert float(row["page_y_px"]) == float(row["crop_y_px"]) + pixel_z


def test_one_page_pdf_rerender_reproduces_the_stored_curve(tmp_path: Path) -> None:
    if shutil.which("pdftoppm") is None:
        pytest.skip("Poppler pdftoppm is required to digitize the source panel")
    if not SOURCE_PDF.is_file():
        pytest.skip("local Calbrix source PDF is unavailable")

    regenerated = tmp_path / "cl415-fig6.csv"
    preview = tmp_path / "cl415-fig6-preview.png"
    count, source_hash = digitize(SOURCE_PDF, regenerated, preview)
    generated_rows = _rows(regenerated)
    stored_rows = _rows()

    assert source_hash == EXPECTED_PDF_SHA256
    assert count == len(generated_rows) == len(stored_rows)
    assert generated_rows == stored_rows
    assert preview.is_file() and preview.stat().st_size > 10_000
