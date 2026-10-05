from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.digitize_calbrix_dash8_breakup import (
    FIG11C_AXES,
    count_fields,
    nearest_trace_sample,
    page_px_to_count,
    page_px_to_time,
    parse_args,
    run_extraction,
)


def test_fig11_axis_calibration_maps_endpoints_and_intermediate_pixels() -> None:
    axes = FIG11C_AXES
    times = page_px_to_time(
        np.array([axes["x_zero_px"], (axes["x_zero_px"] + axes["x_six_px"]) / 2, axes["x_six_px"]])
    )
    counts = page_px_to_count(
        np.array([axes["y_zero_px"], (axes["y_zero_px"] + axes["y_700_px"]) / 2, axes["y_700_px"]])
    )

    np.testing.assert_allclose(times, [0.0, 3.0, 6.0], atol=1e-12)
    np.testing.assert_allclose(counts, [0.0, 350.0, 700.0], atol=1e-12)


def test_read_allowance_preserves_raw_pixel_read_but_bounds_physical_target() -> None:
    just_below_zero = count_fields(-2.4)
    above_plotted_axis = count_fields(704.0)

    assert just_below_zero["count"] == ""
    assert just_below_zero["raw_count"] == "-2.400"
    assert just_below_zero["count_target_min"] == "0.000"
    assert just_below_zero["count_target_max"] == "2.600"
    assert just_below_zero["count_read_status"] == "near_zero_unresolved_within_read_allowance"
    assert above_plotted_axis["count"] == 700
    assert above_plotted_axis["count_target_min"] == "699.000"
    assert above_plotted_axis["count_target_max"] == "700.000"
    assert float(just_below_zero["count_target_min"]) >= 0.0
    assert float(above_plotted_axis["count_target_max"]) <= 700.0


def test_sampling_uses_a_nearby_native_column_and_leaves_trace_gaps_missing() -> None:
    axes = FIG11C_AXES

    def x_at(time_s: float) -> float:
        return axes["x_zero_px"] + (axes["x_six_px"] - axes["x_zero_px"]) * time_s / 6.0

    y_at = axes["y_zero_px"] - 220.0 * (axes["y_zero_px"] - axes["y_700_px"]) / 700.0
    sampled = nearest_trace_sample(np.array([x_at(1.004)]), np.array([y_at]), 1.0)
    assert sampled is not None
    sampled_time, sampled_count = sampled
    assert sampled_time == pytest.approx(1.004, abs=0.002)
    assert sampled_count == pytest.approx(220.0, abs=0.2)

    # A gap wider than the time-read allowance remains missing even when
    # visible pixels bracket the requested time; the code does not interpolate.
    gap_read = nearest_trace_sample(
        np.array([x_at(0.2), x_at(0.6)]),
        np.array([y_at, y_at]),
        0.4,
    )
    assert gap_read is None
    assert nearest_trace_sample(np.array([x_at(0.2)]), np.array([y_at]), -0.01) is None
    assert nearest_trace_sample(np.array([x_at(5.8)]), np.array([y_at]), 6.01) is None


def test_output_directory_is_required_and_existing_directories_are_preserved(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit):
        parse_args([])

    existing = tmp_path / "previous-run"
    existing.mkdir()
    sentinel = existing / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        run_extraction(existing)
    assert sentinel.read_text(encoding="utf-8") == "preserve"
