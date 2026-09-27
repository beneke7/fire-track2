"""Source-trace checks for the independent Calbrix Dash-8 figure read."""

from __future__ import annotations

import csv
import hashlib
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict

from scripts.digitize_calbrix_dash8_cloud_curves_independent import (
    DEFAULT_OUTPUT,
    EXPECTED_PDF_SHA256,
    PANELS,
    RENDER_DPI,
    SOURCE_PDF,
)


def _rows() -> list[dict[str, str]]:
    with DEFAULT_OUTPUT.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_source_pdf_matches_the_pinned_calbrix_paper() -> None:
    digest = hashlib.sha256(SOURCE_PDF.read_bytes()).hexdigest()
    assert digest == EXPECTED_PDF_SHA256


def test_fig7_keeps_the_visible_gap_between_solid_simulation_segments() -> None:
    rows = [row for row in _rows() if row["figure"] == "Fig. 7"]
    by_segment: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        by_segment[int(row["segment"])].append(float(row["x_value"]))

    assert set(by_segment) == {1, 2}
    gap = min(by_segment[2]) - max(by_segment[1])
    assert max(by_segment[1]) < 1.4
    assert min(by_segment[2]) > 1.6
    assert gap > 0.25


def test_fig8_keeps_the_caption_and_prose_time_conflict_visible() -> None:
    rows = [row for row in _rows() if row["figure"] == "Fig. 8(b)"]
    assert rows
    assert {row["series"] for row in rows} == {"dash8_alpha0p001_caption_t1s_prose_t0p5s"}


def test_fig9_zero_tick_is_not_mistaken_for_the_one_tick() -> None:
    panel = PANELS["fig9"]
    result = subprocess.run(
        [
            "pdftotext",
            "-bbox",
            "-f",
            str(panel.page),
            "-l",
            str(panel.page),
            str(SOURCE_PDF),
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    document = ET.fromstring(result.stdout)
    tick_centers_px: dict[int, float] = {}
    for word in document.iter():
        if not word.tag.endswith("word") or word.text not in {str(i) for i in range(9)}:
            continue
        x_min = float(word.attrib["xMin"])
        y_min = float(word.attrib["yMin"])
        if not 76.0 <= x_min <= 82.0 or not 375.0 <= y_min <= 540.0:
            continue
        number = int(word.text)
        y_center_pt = (float(word.attrib["yMin"]) + float(word.attrib["yMax"])) / 2
        tick_centers_px[number] = y_center_pt * RENDER_DPI / 72

    assert set(tick_centers_px) == set(range(9))
    for value, actual_center in tick_centers_px.items():
        expected_center = (
            panel.crop_y
            + panel.y_zero_px
            + value * (panel.y_max_px - panel.y_zero_px) / panel.y_max_value
        )
        # Text-box centers sit a few pixels below their tick marks in this PDF.
        assert abs(actual_center - expected_center) < 12
    assert tick_centers_px[1] - tick_centers_px[0] > 100


def test_fig9_time_curves_remain_separate_and_reach_distinct_envelopes() -> None:
    rows = [row for row in _rows() if row["figure"] == "Fig. 9(a)"]
    by_series: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_series[row["series"]].append(row)

    assert set(by_series) == {
        "fig9_dash8_alpha0p001_t0p5s",
        "fig9_dash8_alpha0p001_t1p0s",
        "fig9_dash8_alpha0p001_t1p5s",
    }
    expected_max_lateral = {
        "fig9_dash8_alpha0p001_t0p5s": (2.2, 2.6),
        "fig9_dash8_alpha0p001_t1p0s": (5.9, 6.4),
        "fig9_dash8_alpha0p001_t1p5s": (7.8, 8.3),
    }
    for series, series_rows in by_series.items():
        assert len({row["segment"] for row in series_rows}) > 1
        assert {(row["x_variable"], row["y_variable"]) for row in series_rows} == {
            (
                "normalized_lateral_expansion_L_over_Lc",
                "normalized_vertical_distance_z_over_Lc",
            )
        }
        max_lateral = max(float(row["x_value"]) for row in series_rows)
        low, high = expected_max_lateral[series]
        assert low <= max_lateral <= high
