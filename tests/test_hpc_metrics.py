from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hpc_metrics.py"
SPEC = importlib.util.spec_from_file_location("hpc_metrics", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
METRICS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(METRICS)


def _write_log(
    path: Path,
    *,
    clock_seconds: float,
    execution_seconds: float = 0.0,
    final_time: float = 1.0,
) -> Path:
    path.write_text(
        "\n".join(
            [
                "Time = 0",
                "deltaT = 0.1",
                "Courant Number mean: 0.2 max: 0.4",
                "Interface Courant Number mean: 0.1 max: 0.3",
                f"ExecutionTime = {execution_seconds / 2} s ClockTime = {clock_seconds / 2} s",
                f"Time = {final_time}",
                f"ExecutionTime = {execution_seconds} s ClockTime = {clock_seconds} s",
                "End",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_parse_log_extracts_time_solver_and_interface_diagnostics(tmp_path: Path) -> None:
    log = tmp_path / "interIsoFoam.log"
    log.write_text(
        """Time = 0
deltaT = 1e-3
Courant Number mean: 0.10 max: 0.25
Interface Courant Number mean: 0.03 max: 0.08
smoothSolver: Solving for p_rgh, Initial residual = 2e-2, Final residual = 1e-5, No Iterations 4
Min/max alpha.water = -1e-6 1.00001
water volume fraction = 0.125
ExecutionTime = 0.2 s ClockTime = 0.3 s
Time = 0.01
deltaT = 2e-3
Courant Number mean: 0.20 max: 0.50
Interface Courant Number mean: 0.05 max: 0.12
GAMG: Solving for p_rgh, Initial residual = 0.1, Final residual = 2e-6, No Iterations 6
smoothSolver: Solving for Ux, Initial residual = 0.4, Final residual = 0.02, No Iterations 2
Min/max alpha.water = 0 1
water volume fraction = 0.25
ExecutionTime = 0.5 s ClockTime = 0.7 s
End
""",
        encoding="utf-8",
    )

    result = METRICS.parse_openfoam_log(log)

    assert result["completion_status"] == "completed"
    assert result["step_count"] == 2
    assert result["physical_time_start_s"] == 0
    assert result["physical_time_reached_s"] == 0.01
    assert result["physical_time_advanced_s"] == 0.01
    assert result["delta_t_s"] == {"min": 0.001, "max": 0.002, "last": 0.002}
    assert result["courant_number"]["max"]["last"] == 0.5
    assert result["interface_courant_number"]["max"]["max"] == 0.12
    assert result["timing"]["clock_time_seconds"] == 0.7
    assert result["timing"]["last_step_clock_seconds"] == pytest.approx(0.4)
    assert result["throughput"]["steps_per_clock_second_interval"] == pytest.approx(1 / 0.4)
    assert result["throughput"]["physical_seconds_per_clock_second_interval"] == pytest.approx(
        0.01 / 0.4
    )
    assert result["step_metrics"][1]["steps_per_clock_second_step"] == pytest.approx(1 / 0.4)
    assert result["step_metrics"][1]["physical_seconds_per_clock_second_step"] == pytest.approx(
        0.01 / 0.4
    )
    assert result["residuals"]["p_rgh"]["solves"] == 2
    assert result["residuals"]["p_rgh"]["iterations_total"] == 10
    assert result["residuals"]["p_rgh"]["last_final"] == 2e-6
    assert result["residuals"]["Ux"]["iterations_total"] == 2
    assert result["pressure_solve_iterations"] == {"fields": {"p_rgh": 10}, "total": 10}
    assert result["alpha_min_max"]["alpha.water"]["min"]["min"] == -1e-6
    assert result["alpha_min_max"]["alpha.water"]["max"]["max"] == 1.00001
    assert result["volume_fraction"]["water"]["last"] == 0.25


def test_fatal_and_nonfinite_log_values_are_reported_without_nan_json(tmp_path: Path) -> None:
    log = tmp_path / "failed.log"
    log.write_text(
        "Time = 0\n"
        "smoothSolver: Solving for p_rgh, Initial residual = 0.1, Final residual = nan, No Iterations 2\n"
        "FOAM FATAL ERROR: solver stopped\n",
        encoding="utf-8",
    )

    result = METRICS.parse_openfoam_log(log)
    serialized = json.dumps(result, allow_nan=False)

    assert result["completion_status"] == "failed"
    assert result["divergence_detected"] is True
    assert result["fatal_errors"]
    assert result["residuals"] == {}
    assert "NaN" not in serialized


def test_floating_point_trap_enabled_is_normal_startup_not_a_failure(tmp_path: Path) -> None:
    log = tmp_path / "normal-startup.log"
    log.write_text(
        "trapFpe: Floating point exception trapping enabled (FOAM_SIGFPE).\nTime = 0.1\nEnd\n",
        encoding="utf-8",
    )

    result = METRICS.parse_openfoam_log(log)

    assert result["completion_status"] == "completed"
    assert result["fatal_errors"] == []
    assert result["divergence_detected"] is False


def test_parse_phase_volume_fraction_and_parenthesized_alpha_extrema(tmp_path: Path) -> None:
    log = tmp_path / "phase-summary.log"
    log.write_text(
        "Time = 0.1\n"
        "Phase-1 volume fraction = 0.1 Min(alpha.water) = -1e-16 Max(alpha.water) = 1\n"
        "End\n",
        encoding="utf-8",
    )

    result = METRICS.parse_openfoam_log(log)

    assert result["volume_fraction"]["Phase-1"]["last"] == 0.1
    assert result["alpha_min_max"]["alpha.water"]["min"]["last"] == -1e-16
    assert result["alpha_min_max"]["alpha.water"]["max"]["last"] == 1
    assert result["step_metrics"][0]["volume_fraction"] == 0.1


def test_sacct_parsable_parent_row_and_resource_accounting(tmp_path: Path) -> None:
    accounting = tmp_path / "job.sacct"
    accounting.write_text(
        "JobID|Elapsed|TotalCPU|AllocCPUS|MaxRSS|State|ExitCode\n"
        "123|00:01:10|00:02:20|4|1.5G|COMPLETED|0:0\n"
        "123.batch|00:01:10|00:00:01||12M|COMPLETED|0:0\n",
        encoding="utf-8",
    )
    parsed = METRICS.parse_sacct(accounting)

    assert parsed == {
        "job_id": "123",
        "elapsed_seconds": 70,
        "total_cpu_seconds": 140,
        "allocated_cpus": 4,
        "parent_max_rss_bytes": int(1.5 * 1024**3),
        "state": "COMPLETED",
        "exit_code": "0:0",
    }


def test_sacct_jobidraw_header_ignores_step_rows(tmp_path: Path) -> None:
    accounting = tmp_path / "job-raw.sacct"
    accounting.write_text(
        "JobIDRaw|Elapsed|TotalCPU|AllocCPUS|MaxRSS|State|ExitCode\n"
        "123|00:01:10|00:02:20|4|1.5G|COMPLETED|0:0\n"
        "123.batch|00:01:10|00:00:01||12M|COMPLETED|0:0\n",
        encoding="utf-8",
    )

    parsed = METRICS.parse_sacct(accounting)

    assert parsed["job_id"] == "123"
    assert parsed["elapsed_seconds"] == 70
    assert parsed["allocated_cpus"] == 4
    assert parsed["parent_max_rss_bytes"] == int(1.5 * 1024**3)


def test_strong_scaling_requires_matched_steps_and_horizon(tmp_path: Path) -> None:
    baseline = METRICS.summarize_run(
        "n100", _write_log(tmp_path / "100.log", clock_seconds=10, execution_seconds=9), 100
    )
    scaled = METRICS.summarize_run(
        "n500", _write_log(tmp_path / "500.log", clock_seconds=4, execution_seconds=3), 500
    )
    comparison = METRICS.compare_runs([baseline, scaled], "n100")

    assert comparison["eligible"] is True
    assert comparison["runs"]["n500"]["solver_speedup"] == 2.5
    assert comparison["runs"]["n500"]["solver_parallel_efficiency"] == 0.5
    assert comparison["runs"]["n500"]["solver_core_hours_estimate"] == pytest.approx(4 * 500 / 3600)
    assert comparison["end_to_end_eligible"] is False

    mismatch_log = tmp_path / "mismatch.log"
    mismatch_log.write_text(
        "Time = 0\nExecutionTime = 1 s ClockTime = 2 s\nTime = 0.5\nTime = 1\nEnd\n",
        encoding="utf-8",
    )
    mismatch = METRICS.summarize_run("n1000", mismatch_log, 1000)
    comparison = METRICS.compare_runs([baseline, mismatch], "n100")
    assert comparison["eligible"] is False
    assert comparison["reason"] == "logged step counts differ across runs"
    assert comparison["runs"]["n1000"]["solver_speedup"] is None

    horizon_mismatch = METRICS.summarize_run(
        "n500-short",
        _write_log(tmp_path / "short.log", clock_seconds=3, final_time=0.5),
        500,
    )
    comparison = METRICS.compare_runs([baseline, horizon_mismatch], "n100")
    assert comparison["eligible"] is False
    assert comparison["reason"] == "physical-time start or horizon differs across runs"


def test_sacct_backed_summary_keeps_logged_clock_and_accounting_distinct(tmp_path: Path) -> None:
    log = _write_log(tmp_path / "solver.log", clock_seconds=11, execution_seconds=10)
    accounting = tmp_path / "job.sacct"
    accounting.write_text(
        "JobID|Elapsed|TotalCPU|AllocCPUS|MaxRSS|State|ExitCode\n"
        "456|00:00:20|00:01:00|8|500M|COMPLETED|0:0\n",
        encoding="utf-8",
    )
    run = METRICS.summarize_run("n8", log, 8, accounting)

    assert run["timing"]["clock_time_seconds"] == 11
    assert run["resources"]["solver_clock_time_seconds"] == 11
    assert run["resources"]["sacct_elapsed_seconds"] == 20
    assert run["resources"]["solver_core_hours_estimate"] == pytest.approx(11 * 8 / 3600)
    assert run["resources"]["sacct_allocated_core_hours"] == pytest.approx(20 * 8 / 3600)
    assert run["resources"]["sacct_cpu_core_hours"] == pytest.approx(60 / 3600)
    assert run["resources"]["sacct_cpu_utilization"] == pytest.approx(60 / (20 * 8))
    assert run["resources"]["sacct_parent_max_rss_bytes"] == 500 * 1024**2


def test_launcher_wall_time_is_separate_and_used_for_solver_scaling(tmp_path: Path) -> None:
    baseline_log = _write_log(tmp_path / "base.log", clock_seconds=20, execution_seconds=18)
    scaled_log = _write_log(tmp_path / "scaled.log", clock_seconds=4, execution_seconds=3)
    baseline_launcher = tmp_path / "base-launcher.log"
    baseline_launcher.write_text("solver_exit_code=0\nsolver_wall_s=10.250001\n", encoding="utf-8")
    scaled_launcher = tmp_path / "scaled-launcher.log"
    scaled_launcher.write_text("solver_exit_code=0\nsolver_wall_s=5.125\n", encoding="utf-8")

    runs = [
        METRICS.summarize_run("n100", baseline_log, 100, launcher_path=baseline_launcher),
        METRICS.summarize_run("n500", scaled_log, 500, launcher_path=scaled_launcher),
    ]
    comparison = METRICS.compare_runs(runs, "n100")

    assert runs[0]["resources"]["solver_wall_time_seconds"] == 10.250001
    assert (
        runs[0]["resources"]["solver_wall_time_source"] == "launcher.solver_wall_s (srun envelope)"
    )
    assert runs[0]["resources"]["solver_clock_time_seconds"] == 20
    assert runs[1]["resources"]["solver_clock_time_seconds"] == 4
    assert comparison["solver_time_source"] == "launcher.solver_wall_s (srun envelope)"
    assert comparison["runs"]["n500"]["solver_speedup"] == pytest.approx(2.0)


def test_runner_state_json_supplies_launcher_wall_time(tmp_path: Path) -> None:
    state = tmp_path / "run-state.json"
    state.write_text(
        json.dumps({"solver_wall_s": 12.345678, "solver_exit_code": 0}), encoding="utf-8"
    )

    parsed = METRICS.parse_launcher_log(state)

    assert parsed == {"solver_wall_seconds": 12.345678, "solver_exit_code": 0}


def test_per_step_throughput_is_null_when_clock_time_is_quantized(tmp_path: Path) -> None:
    log = tmp_path / "quantized-clock.log"
    log.write_text(
        "Time = 0.001\nExecutionTime = 1 s ClockTime = 1 s\n"
        "Time = 0.002\nExecutionTime = 2 s ClockTime = 1 s\n"
        "Time = 0.003\nExecutionTime = 3 s ClockTime = 2 s\nEnd\n",
        encoding="utf-8",
    )

    result = METRICS.parse_openfoam_log(log)

    assert result["step_metrics"][1]["clock_time_step_seconds"] == 0
    assert result["step_metrics"][1]["steps_per_clock_second_step"] is None
    assert result["step_metrics"][1]["physical_seconds_per_clock_second_step"] is None
    assert result["step_metrics"][2]["steps_per_clock_second_step"] == 1
    assert result["step_metrics"][2]["physical_seconds_per_clock_second_step"] == pytest.approx(
        0.001
    )


def test_solver_comparison_rejects_mixed_launcher_and_clock_sources(tmp_path: Path) -> None:
    baseline_log = _write_log(tmp_path / "base.log", clock_seconds=20, execution_seconds=18)
    scaled_log = _write_log(tmp_path / "scaled.log", clock_seconds=4, execution_seconds=3)
    launcher = tmp_path / "base-launcher.log"
    launcher.write_text("solver_exit_code=0\nsolver_wall_s=10\n", encoding="utf-8")
    runs = [
        METRICS.summarize_run("n100", baseline_log, 100, launcher_path=launcher),
        METRICS.summarize_run("n500", scaled_log, 500),
    ]

    comparison = METRICS.compare_runs(runs, "n100")

    assert comparison["eligible"] is False
    assert comparison["reason"] == "solver wall-time sources differ across runs"
    assert comparison["runs"]["n500"]["solver_speedup"] is None


def test_sacct_failure_blocks_a_completed_openfoam_log(tmp_path: Path) -> None:
    log = _write_log(tmp_path / "solver.log", clock_seconds=11, execution_seconds=10)
    accounting = tmp_path / "failed.sacct"
    accounting.write_text(
        "JobID|Elapsed|TotalCPU|AllocCPUS|MaxRSS|State|ExitCode\n"
        "456|00:00:20|00:01:00|8|500M|FAILED|1:0\n",
        encoding="utf-8",
    )

    run = METRICS.summarize_run("n8", log, 8, accounting)

    assert run["completion_status"] == "failed"


def test_scaling_reports_solver_and_end_to_end_efficiency_separately(tmp_path: Path) -> None:
    baseline_log = _write_log(tmp_path / "base.log", clock_seconds=10, execution_seconds=9)
    scaled_log = _write_log(tmp_path / "scaled.log", clock_seconds=4, execution_seconds=3)
    baseline_sacct = tmp_path / "base.sacct"
    baseline_sacct.write_text(
        "JobID|Elapsed|TotalCPU|AllocCPUS|MaxRSS|State|ExitCode\n"
        "100|00:00:20|00:10:00|100|N/A|COMPLETED|0:0\n",
        encoding="utf-8",
    )
    scaled_sacct = tmp_path / "scaled.sacct"
    scaled_sacct.write_text(
        "JobID|Elapsed|TotalCPU|AllocCPUS|MaxRSS|State|ExitCode\n"
        "500|00:00:08|00:30:00|500|N/A|COMPLETED|0:0\n",
        encoding="utf-8",
    )

    runs = [
        METRICS.summarize_run("n100", baseline_log, 100, baseline_sacct),
        METRICS.summarize_run("n500", scaled_log, 500, scaled_sacct),
    ]
    comparison = METRICS.compare_runs(runs, "n100")

    assert comparison["eligible"] is True
    assert comparison["end_to_end_eligible"] is True
    assert comparison["runs"]["n500"]["solver_speedup"] == 2.5
    assert comparison["runs"]["n500"]["end_to_end_speedup"] == 2.5
    assert comparison["runs"]["n500"]["end_to_end_parallel_efficiency"] == 0.5


def test_headerless_sacct_uses_documented_field_order(tmp_path: Path) -> None:
    accounting = tmp_path / "no-header.sacct"
    accounting.write_text("789|1-00:00:00|2-00:00:00|16|2G|COMPLETED|0:0\n", encoding="utf-8")

    parsed = METRICS.parse_sacct(accounting)

    assert parsed["elapsed_seconds"] == 86400
    assert parsed["total_cpu_seconds"] == 172800
    assert parsed["allocated_cpus"] == 16
    assert parsed["parent_max_rss_bytes"] == 2 * 1024**3
    assert math.isfinite(parsed["elapsed_seconds"])


def test_sacct_does_not_treat_cpu_time_raw_or_step_rss_as_measured_totals(
    tmp_path: Path,
) -> None:
    accounting = tmp_path / "accounting.sacct"
    accounting.write_text(
        "JobID|Elapsed|CPUTimeRAW|AllocCPUS|MaxRSS|State|ExitCode\n"
        "789|00:00:30|240|8||COMPLETED|0:0\n"
        "789.batch|00:00:30|240|8|2G|COMPLETED|0:0\n",
        encoding="utf-8",
    )

    parsed = METRICS.parse_sacct(accounting)

    assert parsed["total_cpu_seconds"] is None
    assert parsed["parent_max_rss_bytes"] is None


def test_cli_emits_compact_json_offline_by_default(tmp_path: Path, monkeypatch, capsys) -> None:
    log = _write_log(tmp_path / "offline.log", clock_seconds=10, execution_seconds=9)
    monkeypatch.setattr(
        METRICS,
        "upload_wandb",
        lambda *args: pytest.fail("W&B upload must remain opt-in"),
    )

    assert METRICS.main(["--run", f"n100={log}", "--ranks", "n100=100"]) == 0

    output = capsys.readouterr().out
    assert output.count("\n") == 1
    assert ": " not in output
    assert json.loads(output)["runs"][0]["ranks"] == 100


def test_cli_writes_json_before_opt_in_upload(tmp_path: Path, monkeypatch) -> None:
    log = _write_log(tmp_path / "upload.log", clock_seconds=10, execution_seconds=9)
    output = tmp_path / "metrics.json"

    def check_before_upload(report, project, entity):
        assert project == "demo"
        assert entity is None
        assert json.loads(output.read_text(encoding="utf-8"))["runs"][0]["step_count"] == 2
        assert report["runs"][0]["step_metrics"]

    monkeypatch.setattr(METRICS, "upload_wandb", check_before_upload)
    assert (
        METRICS.main(
            [
                "--run",
                f"n100={log}",
                "--ranks",
                "n100=100",
                "--output",
                str(output),
                "--wandb-project",
                "demo",
            ]
        )
        == 0
    )
