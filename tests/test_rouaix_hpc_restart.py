from __future__ import annotations

import json
import tarfile

import pytest

from cases.e1_rouaix_hpc import run_pilot as pilot
from cases.e1_rouaix_hpc_restart.run_restart import (
    DT_S,
    END_TIME_S,
    PARENT_TIME_S,
    RestartConfig,
    RestartError,
    RestartOutputMonitor,
    build_terminal_status,
    config_for_variant,
    rewrite_control_dict,
    select_seed_members,
    validate_allocation,
    validate_smoke_preflight,
)


def test_restart_configs_have_frozen_smoke_and_control_horizons() -> None:
    assert RestartConfig().validate().end_time_s == 0.201
    with pytest.raises(RestartError, match="selected frozen variant"):
        RestartConfig(end_time_s=0.202).validate()
    control = config_for_variant("original-control")
    assert control.end_time_s == 0.3
    assert control.write_interval_s == 0.1
    assert control.wall_budget_s == 5400
    assert round((control.end_time_s - control.start_time_s) / control.delta_t_s) == 1000
    with pytest.raises(RestartError, match="selected frozen variant"):
        RestartConfig(
            variant="original-control", end_time_s=0.301, write_interval_s=0.1, wall_budget_s=5400
        ).validate()


def test_control_dict_changes_only_restart_window(tmp_path) -> None:
    path = tmp_path / "controlDict"
    path.write_text(
        "application interIsoFoam;\n"
        "startFrom startTime;\nstartTime 0;\nstopAt endTime;\nendTime 0.2;\n"
        "deltaT 0.0001;\nadjustTimeStep no;\nwriteControl runTime;\nwriteInterval 0.2;\n"
        "div(rhoPhi,U) Gauss linearUpwind grad(U);\n",
        encoding="utf-8",
    )

    hashes = rewrite_control_dict(path, RestartConfig())
    updated = path.read_text(encoding="utf-8")

    assert "startFrom latestTime;" in updated
    assert "startTime 0.2;" in updated
    assert "endTime 0.201;" in updated
    assert "writeInterval 0.001;" in updated
    assert "deltaT 0.0001;" in updated
    assert "div(rhoPhi,U) Gauss linearUpwind grad(U);" in updated
    assert hashes["before_sha256"] != hashes["after_sha256"]

    control_path = tmp_path / "controlDict-control"
    control_path.write_text(
        "startFrom startTime;\nstartTime 0;\nendTime 0.2;\n"
        "deltaT 0.0001;\nadjustTimeStep no;\nwriteInterval 0.2;\n",
        encoding="utf-8",
    )
    rewrite_control_dict(control_path, config_for_variant("original-control"))
    control = control_path.read_text(encoding="utf-8")
    assert "endTime 0.3;" in control
    assert "writeInterval 0.1;" in control
    assert "deltaT 0.0001;" in control


def test_restart_monitor_counts_absolute_times_after_checkpoint() -> None:
    tracker = RestartOutputMonitor(
        last_progress_monotonic=0.0, horizon_s=END_TIME_S, delta_t_s=DT_S
    )
    now = 1.0
    tracker.feed("Time = 0.2", now)
    tracker.feed("min / max (mag(U)) = 0 100", now)
    for step in range(1, 11):
        now += 1.0
        current = PARENT_TIME_S + step * DT_S
        tracker.feed(f"Time = {current:.4f}", now)
        tracker.feed("min / max (mag(U)) = 0 101", now)
    tracker.feed("End", now)
    tracker.finish()

    assert len(tracker.rows) == 10
    assert tracker.rows[0][0] == pytest.approx(0.2001)
    assert tracker.rows[-1][0] == pytest.approx(0.201)
    assert tracker.completion_fault() is None


def test_control_monitor_requires_all_thousand_post_checkpoint_steps() -> None:
    control = config_for_variant("original-control")
    tracker = RestartOutputMonitor(
        last_progress_monotonic=0.0,
        horizon_s=control.end_time_s,
        delta_t_s=control.delta_t_s,
    )
    now = 1.0
    tracker.feed("Time = 0.2", now)
    tracker.feed("min / max (mag(U)) = 0 100", now)
    for step in range(1, 1001):
        now += 0.01
        current = control.start_time_s + step * control.delta_t_s
        tracker.feed(f"Time = {current:.4f}", now)
        tracker.feed("min / max (mag(U)) = 0 101", now)
    tracker.feed("End", now)
    tracker.finish()
    assert len(tracker.rows) == 1000
    assert tracker.rows[-1][0] == pytest.approx(0.3)
    assert tracker.completion_fault() is None


def test_allocation_matches_three_nodes_of_forty_ranks_and_22_gib() -> None:
    env = {
        "SLURM_JOB_NAME": "ml-vof",
        "SLURM_JOB_ACCOUNT": "nk_meshapplied",
        "SLURM_JOB_PARTITION": "cpu-short",
        "SLURM_JOB_NUM_NODES": "3",
        "SLURM_NTASKS": "120",
        "SLURM_CPUS_PER_TASK": "1",
        "SLURM_TASKS_PER_NODE": "40(x3)",
        "SLURM_MEM_PER_NODE": str(22 * 1024),
        "SLURM_CPUS_ON_NODE": "40",
        "SLURM_JOB_NODELIST": "n[01-03]",
    }
    receipt = validate_allocation(config_for_variant("original-control"), env)
    assert receipt["nodes"] == 3
    assert receipt["tasks_per_node"] == [40, 40, 40]
    assert receipt["memory_mb_per_node"] == 22 * 1024
    env["SLURM_MEM_PER_NODE"] = str(21 * 1024)
    with pytest.raises(RestartError, match="22 GiB"):
        validate_allocation(config_for_variant("original-control"), env)


def test_smoke_preflight_verifies_new_id_layout_ledger_and_archive(tmp_path) -> None:
    smoke_id = "987654321"
    run_root = tmp_path
    smoke_dir = run_root / f"rouaix-restart-original-smoke-{smoke_id}"
    attempt = smoke_dir / "attempt"
    ledger_dir = attempt / "ledger"
    case = attempt / "case"
    ledger_dir.mkdir(parents=True)
    case.mkdir(parents=True)
    (ledger_dir / "summary.json").write_text(
        json.dumps(
            {
                "coverage": {
                    "status": "requested_horizon_reached_exploratory_only",
                    "requested_target_reached": True,
                },
                "integration": {
                    "closure_residual_kg": 1e-6,
                    "max_abs_per_step_closure_residual_kg": 2e-6,
                    "max_abs_cumulative_closure_residual_kg": 3e-6,
                },
            }
        )
    )
    terminal = {
        "state": "terminal",
        "solver_end_marker": True,
        "solver_exit_code": 0,
        "pause_observed": False,
        "solver_time_steps_recorded": 10,
    }
    (case / "terminal-status.json").write_text(json.dumps(terminal))
    archive, archive_sha, member_count, _ = pilot.pack_attempt(attempt, smoke_dir)
    state = {
        "status": "solver_complete_exploratory",
        "job_id": smoke_id,
        "case_id": "rouaix-restart-original-smoke-0201",
        "variant": "original-smoke",
        "solver_exit_code": 0,
        "solver_end_marker": True,
        "solver_time_steps_recorded": 10,
        "start_time_s": 0.2,
        "target_time_s": 0.201,
        "delta_t_s": 0.0001,
        "solver_time_s": 0.201,
        "attempt_archive_status": "verified_crc_hash_and_member_list",
        "ledger_status": "written_from_hash_bound_parent_checkpoint",
        "solver_convergence": {"all_converged": True, "failed_record_count": 0},
        "result_archive": str(archive),
        "result_archive_sha256": archive_sha,
        "result_archive_members": member_count,
        "allocation": {
            "nodes": 3,
            "ranks": 120,
            "tasks_per_node": [40, 40, 40],
            "memory_mb_per_node": 22 * 1024,
        },
    }
    state_path = smoke_dir / "run-state.json"
    state_path.write_text(json.dumps(state))

    receipt = validate_smoke_preflight(run_root, smoke_id)
    assert receipt["status"] == "verified_clean_smoke_archive_ledger_and_convergence"

    state["allocation"]["nodes"] = 2
    state_path.write_text(json.dumps(state))
    with pytest.raises(RestartError, match="allocation receipt"):
        validate_smoke_preflight(run_root, smoke_id)

    state["allocation"]["nodes"] = 3
    state_path.write_text(json.dumps(state))
    with archive.open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(RestartError, match="SHA-256 changed"):
        validate_smoke_preflight(run_root, smoke_id)


def test_terminal_receipt_requires_verified_u_guard_stop() -> None:
    partial = build_terminal_status(
        return_code=0,
        end_marker=True,
        actual_time_s=0.2001,
        step_count=1,
        stop_detail="operational stop: max|U|=1000.2 m/s exceeds 1000 m/s",
        pause_observed=False,
        stop_signals=["12"],
        endpoint_verified=True,
    )
    assert partial["state"] == "guarded_partial"
    assert partial["stop_reason"] == "max_abs_U_exceeded_1000.0_m_s"
    assert partial["write_and_stop_requested"] is True
    assert partial["write_and_stop_acknowledged"] is True

    unacknowledged = build_terminal_status(
        return_code=1,
        end_marker=False,
        actual_time_s=0.2001,
        step_count=1,
        stop_detail="operational stop: max|U|=1000.2 m/s exceeds 1000 m/s",
        pause_observed=False,
        stop_signals=[],
        endpoint_verified=False,
    )
    assert unacknowledged["state"] == "incomplete"
    assert unacknowledged["write_and_stop_acknowledged"] is False

    clean_control = build_terminal_status(
        return_code=0,
        end_marker=True,
        actual_time_s=0.3,
        step_count=1000,
        stop_detail=None,
        pause_observed=False,
        stop_signals=[],
        endpoint_verified=True,
        variant="original-control",
        target_time_s=0.3,
    )
    assert clean_control["state"] == "terminal"
    assert clean_control["target_time_s"] == 0.3


def test_seed_selection_requires_checkpoint_and_rejects_links() -> None:
    required = {
        "attempt/manifest.json",
        "attempt/ledger/summary.json",
        "attempt/case/case-inputs.json",
        *(
            f"attempt/case/system/{name}"
            for name in ("controlDict", "decomposeParDict", "fvSchemes", "fvSolution")
        ),
        *(
            f"attempt/case/constant/polyMesh/{name}"
            for name in ("points", "faces", "owner", "neighbour", "boundary")
        ),
        *(
            f"attempt/case/processors120/constant/polyMesh/{name}"
            for name in ("points", "faces", "owner", "neighbour", "boundary")
        ),
        *(
            f"attempt/case/processors120/0.200000000000/{name}"
            for name in (
                "U",
                "alpha.water",
                "epsilon",
                "k",
                "nut",
                "p",
                "p_rgh",
                "phi",
                "uniform/cumulativeContErr",
                "uniform/functionObjects/functionObjectProperties",
                "uniform/time",
            )
        ),
    }
    members = []
    for name in sorted(required):
        info = tarfile.TarInfo(name)
        info.size = 0
        members.append(info)
    assert len(select_seed_members(members)) == len(members)

    link = tarfile.TarInfo("attempt/case/processors120/0.200000000000/foreign")
    link.type = tarfile.SYMTYPE
    with pytest.raises(RestartError, match="link or special file"):
        select_seed_members([*members, link])
