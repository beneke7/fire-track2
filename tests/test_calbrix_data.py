"""Schema and figure-coordinate checks for the digitized Calbrix history."""

from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURVE_PATH = ROOT / "data" / "derived" / "calbrix_dash8_fig4_velocity.csv"
EXPECTED_COLUMNS = {
    "time_s",
    "u_l_m_s",
    "figure_read_bound_time_s",
    "figure_read_bound_u_l_m_s",
}


def test_calbrix_dash8_figure_4_history_is_ordered_and_carries_bounds() -> None:
    with CURVE_PATH.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert set(reader.fieldnames or ()) == EXPECTED_COLUMNS
        rows = list(reader)

    assert len(rows) == 51
    times = [float(row["time_s"]) for row in rows]
    speeds = [float(row["u_l_m_s"]) for row in rows]
    assert times[0] == 0.0
    assert times[-1] == 5.0
    assert all(
        math.isclose(right - left, 0.1, abs_tol=1e-12) for left, right in zip(times, times[1:])
    )
    assert all(math.isfinite(value) and value >= 0 for value in speeds)
    assert all(float(row["figure_read_bound_time_s"]) > 0 for row in rows)
    assert all(float(row["figure_read_bound_u_l_m_s"]) > 0 for row in rows)

    peak_index = max(range(len(speeds)), key=speeds.__getitem__)
    assert times[peak_index] == 0.4
    assert math.isclose(speeds[peak_index], 4.693, abs_tol=1e-9)
