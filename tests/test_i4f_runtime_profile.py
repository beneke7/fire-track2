import pytest

from scripts.profile_i4f_runtime import parse_lines, profile_logs


def test_parse_time_steps_solver_iterations_and_trapfpe_banner() -> None:
    steps, metadata = parse_lines(
        [
            "Create mesh for time = 0.0\n",
            "trapFpe: Floating point exception trapping enabled (FOAM_SIGFPE).\n",
            "Exec   : /pair/bin/compressibleInterFoamFrozenAlphaSourceV2NoPout\n",
            "[0] Time = 0.1\n",
            "[0] PIMPLE: iteration 1\n",
            "[2] smoothSolver:  Solving for Ux, Initial residual = 1, Final residual = 0, No Iterations 2\n",
            "[0] GAMG:  Solving for p_rgh, Initial residual = 1, Final residual = 0, No Iterations 7\n",
            "[0] ExecutionTime = 1.0 s  ClockTime = 2 s\n",
            "Time = 0.2\n",
            "PIMPLE: iteration 1\n",
            "GAMG:  Solving for p_rgh, Initial residual = 1, Final residual = 0, No Iterations 4\n",
            "ExecutionTime = 2.5 s  ClockTime = 5 s\n",
            "End\n",
        ]
    )

    assert len(steps) == 2
    assert steps[0].delta_t_s == 0.1
    assert steps[0].execution_interval_s is None
    assert steps[0].clock_interval_s is None
    assert steps[0].first_timer_in_segment is True
    assert steps[0].iterations_by_field["Ux"] == 2
    assert steps[0].iterations_by_field["p_rgh"] == 7
    assert steps[1].delta_t_s == 0.1
    assert steps[1].execution_interval_s == 1.5
    assert steps[1].clock_interval_s == 3.0
    assert steps[1].solves_by_field["p_rgh"] == 1
    counters = metadata["counters"]
    assert counters["trapfpe_banner_lines"] == 1
    assert counters["foam_fatal_lines"] == 0
    assert counters["pout_records"] == 0
    assert counters["end_markers"] == 1


def test_restart_boundaries_reset_timer_baseline_and_normalize_pout_prefix() -> None:
    steps, metadata = parse_lines(
        [
            "Create mesh for time = 0.0\n",
            "Time = 0.1\n",
            "ExecutionTime = 3 s  ClockTime = 4 s\n",
            "Time = 0.2\n",
            "ExecutionTime = 4 s  ClockTime = 6 s\n",
            "Create mesh for time = 0.2\n",
            "[2] I4F_POUT time_s=0.3 rank=2 value=1\n",
            "[0] Time = 0.3\n",
            "[0] ExecutionTime = 0.5 s  ClockTime = 1 s\n",
            "[0] Time = 0.4\n",
            "[0] ExecutionTime = 1 s  ClockTime = 2.5 s\n",
            "Time = 0.5\n",
            "ExecutionTime = 0.2 s  ClockTime = 0.5 s\n",
            "Time = 0.6\n",
            "ExecutionTime = 0.8 s  ClockTime = 1.7 s\n",
        ]
    )

    assert len(steps) == 6
    assert [step.segment for step in steps] == [1, 1, 2, 2, 3, 3]
    assert steps[2].first_timer_in_segment is True
    assert steps[2].execution_interval_s is None
    assert steps[3].execution_interval_s == 0.5
    assert steps[3].clock_interval_s == 1.5
    assert steps[4].timer_reset is True
    assert steps[4].execution_interval_s is None
    assert abs(steps[5].execution_interval_s - 0.6) < 1e-12
    assert metadata["counters"]["restart_or_create_mesh_boundaries"] == 2
    assert metadata["counters"]["timer_reset_boundaries"] == 1
    assert metadata["counters"]["pout_records"] == 1


def test_profile_output_refuses_to_overwrite_existing_results(tmp_path) -> None:
    (tmp_path / "prior-result.json").write_text("preserve\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        profile_logs([], tmp_path)
