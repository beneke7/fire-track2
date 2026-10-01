from __future__ import annotations

import pytest

from scripts.render_vof_animation import frame_hold_schedule


def test_frame_hold_schedule_preserves_zero_and_nonuniform_intervals() -> None:
    schedule = frame_hold_schedule([0.0, 0.025, 0.1], slowdown=20.0, fps=10, endpoint_hold_s=0.5)

    assert [entry["simulation_time_s"] for entry in schedule] == [0.0, 0.025, 0.1]
    assert [entry["frame_count"] for entry in schedule] == [5, 15, 5]
    assert [entry["frame_start_inclusive"] for entry in schedule] == [0, 5, 20]
    assert [entry["endpoint_hold"] for entry in schedule] == [False, False, True]
    assert schedule[0]["simulation_interval_end_s"] == 0.025
    assert schedule[1]["simulation_interval_end_s"] == 0.1
    assert schedule[2]["represented_simulation_interval_s"] == 0.0
    assert sum(entry["playback_duration_s"] for entry in schedule) == pytest.approx(2.5)
    assert all("no temporal interpolation" in entry["sampling"] for entry in schedule)


@pytest.mark.parametrize(
    ("times", "slowdown", "fps", "endpoint_hold_s", "message"),
    [
        ([0.1, 0.2], 10.0, 30, 1.0, "first saved simulation time must be zero"),
        ([0.0, 0.2, 0.1], 10.0, 30, 1.0, "strictly increasing"),
        ([0.0, 0.01], 0.01, 1, 1.0, "at least one video frame"),
        ([0.0], 10.0, 30, 0.0, "endpoint hold"),
    ],
)
def test_frame_hold_schedule_rejects_unrepresentable_inputs(
    times: list[float],
    slowdown: float,
    fps: int,
    endpoint_hold_s: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        frame_hold_schedule(times, slowdown=slowdown, fps=fps, endpoint_hold_s=endpoint_hold_s)
