from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from cases.e1_rouaix_hpc import run_pilot as pilot
from cases.e1_rouaix_hpc_restart import run_restart as restart
from cases.e1_rouaix_hpc_restart.run_restart import (
    DT_S,
    END_TIME_S,
    PARENT_TIME_S,
    PRESSURE_TOTAL_PATCHES,
    RestartConfig,
    RestartError,
    RestartOutputMonitor,
    build_terminal_status,
    config_for_variant,
    pressure_checkpoint_integrity,
    pressure_total_change_command,
    pressure_total_dictionary_text,
    rewrite_control_dict,
    select_seed_members,
    validate_allocation,
    validate_checkpoint_time,
    validate_smoke_preflight,
)


def test_restart_sbatch_openfoam_bootstrap_preserves_module_args_and_reports_failure(
    tmp_path: Path,
) -> None:
    scripts = [
        Path(__file__).resolve().parents[1] / "cases/e1_rouaix_hpc_restart/restart_smoke_v2.sbatch",
        Path(__file__).resolve().parents[1] / "cases/e1_rouaix_hpc_restart/restart_control.sbatch",
    ]
    source_blocks = []
    for script_path in scripts:
        text = script_path.read_text(encoding="utf-8")
        assert (
            "SOURCE_ROOT=/project/nk_meshapplied/bene/fire-track2-hpc/"
            "rouaix-restart-source-v4-20261028/unpacked"
        ) in text
        start = text.index('read -r -a foam_bash_args <<< "$FOAM_BASH"')
        end = text.index("\n[[ ${WM_PROJECT_VERSION:-} == v2512 ]]", start)
        source_blocks.append(text[start:end])
    assert source_blocks[0] == source_blocks[1]

    fake_bashrc = tmp_path / "bashrc"
    args_record = tmp_path / "source-args.txt"
    fake_bashrc.write_text(
        'printf "%s\\n" "$@" > "$FOAM_ARGS_RECORD"\n'
        "[[ $1 == WM_PROJECT_VERSION=v2512 ]] || return 11\n"
        "[[ $2 == WM_COMPILER=Gcc ]] || return 12\n"
        "[[ $3 == WM_MPLIB=CRAY-MPICH ]] || return 13\n"
        "[[ $4 == WM_COMPILE_OPTION=Opt ]] || return 14\n"
        "[[ $5 == WM_LABEL_SIZE=32 ]] || return 15\n"
        "[[ $6 == WM_PRECISION_OPTION=DP ]] || return 16\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        FOAM_BASH=(
            f"{fake_bashrc} WM_PROJECT_VERSION=v2512 WM_COMPILER=Gcc "
            "WM_MPLIB=CRAY-MPICH WM_COMPILE_OPTION=Opt WM_LABEL_SIZE=32 "
            "WM_PRECISION_OPTION=DP"
        ),
        FOAM_ARGS_RECORD=str(args_record),
        RUN_ROOT=str(tmp_path),
        SLURM_JOB_ID="test",
    )
    successful = subprocess.run(
        ["bash", "-c", source_blocks[0]], env=env, capture_output=True, text=True
    )
    assert successful.returncode == 0, successful.stderr
    assert args_record.read_text(encoding="utf-8").splitlines() == [
        "WM_PROJECT_VERSION=v2512",
        "WM_COMPILER=Gcc",
        "WM_MPLIB=CRAY-MPICH",
        "WM_COMPILE_OPTION=Opt",
        "WM_LABEL_SIZE=32",
        "WM_PRECISION_OPTION=DP",
    ]

    fake_bashrc.write_text("return 23\n", encoding="utf-8")
    failed = subprocess.run(
        ["bash", "-c", source_blocks[0]], env=env, capture_output=True, text=True
    )
    assert failed.returncode == 23
    assert "OpenFOAM environment setup failed" in failed.stderr
    assert "modules-test.log" in failed.stderr


def test_early_save_sbatch_uses_dedicated_capsule_and_run_root() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "cases/e1_rouaix_hpc_restart/restart_early_save.sbatch"
    ).read_text(encoding="utf-8")
    assert "rouaix-early-save-source-v2-20261028/unpacked" in script
    assert "rouaix-early-save-v2-20261028" in script
    assert "#SBATCH --ntasks=120" in script
    assert "#SBATCH --time=00:20:00" in script
    assert "--variant original-early-save" in script


def test_pressure_total_sbatch_and_configuration_are_declared_without_submission() -> None:
    script = (
        Path(__file__).resolve().parents[1] / "cases/e1_rouaix_hpc_restart/restart_pressure.sbatch"
    ).read_text(encoding="utf-8")
    assert "rouaix-pressure-total-restart-source-20261028/unpacked" in script
    assert "rouaix-pressure-total-restart-20261028" in script
    assert "#SBATCH --ntasks=120" in script
    assert "#SBATCH --nodes=3" in script
    assert "#SBATCH --mem=22G" in script
    assert "#SBATCH --time=01:30:00" in script
    assert "--variant pressure-total-p0-zero" in script

    config = config_for_variant("pressure-total-p0-zero")
    assert config.end_time_s == 0.3
    assert config.write_interval_s == 0.05
    assert config.wall_budget_s == 5400
    assert round((config.end_time_s - config.start_time_s) / config.delta_t_s) == 1000
    with pytest.raises(RestartError, match="selected frozen variant"):
        RestartConfig(
            variant="pressure-total-p0-zero",
            end_time_s=0.3,
            write_interval_s=0.1,
            wall_budget_s=5400,
        ).validate()


def test_pressure_pcgdic_variant_keeps_the_physics_and_declares_rolling_writes() -> None:
    config = config_for_variant("pressure-total-pcgdic")
    assert (config.start_time_s, config.end_time_s, config.delta_t_s) == (
        0.2,
        0.255,
        0.0001,
    )
    assert config.write_interval_s == 0.005
    assert config.wall_budget_s == 7200
    assert round((config.end_time_s - config.start_time_s) / config.delta_t_s) == 550

    script = (
        Path(__file__).resolve().parents[1]
        / "cases/e1_rouaix_hpc_restart/restart_pressure_pcgdic.sbatch"
    ).read_text(encoding="utf-8")
    assert "rouaix-pressure-pcgdic-restart-source-20261028/unpacked" in script
    assert "rouaix-pressure-pcgdic-restart-20261028" in script
    assert "#SBATCH --ntasks=120" in script
    assert "#SBATCH --nodes=3" in script
    assert "#SBATCH --mem=22G" in script
    assert "#SBATCH --time=02:00:00" in script
    assert "--variant pressure-total-pcgdic" in script


def test_pressure_pcgdic_rewrite_changes_only_pressure_solver_and_checkpoint_retention(
    tmp_path: Path,
) -> None:
    fv_solution = tmp_path / "fvSolution"
    fv_solution.write_text(
        "solvers\n{\n"
        "    p_rgh\n    {\n        solver GAMG;\n        tolerance 1e-8;\n"
        "        relTol 0.01;\n        smoother DICGaussSeidel;\n        maxIter 100;\n    }\n"
        "    p_rghFinal { $p_rgh; relTol 0; }\n"
        "    U { solver PBiCGStab; preconditioner DILU; tolerance 1e-8; relTol 0.1; }\n"
        "}\nPIMPLE { nCorrectors 3; }\n",
        encoding="ascii",
    )
    receipt = restart.rewrite_p_rgh_solver_to_pcg_dic(fv_solution)
    updated = fv_solution.read_text(encoding="ascii")
    assert receipt["solver"] == "PCG"
    assert receipt["preconditioner"] == "DIC"
    assert receipt["tolerance"] == "1e-8"
    assert receipt["relTol"] == "0.01"
    assert receipt["p_rgh_maxIter"] == 1000
    assert "solver PCG;" in updated and "preconditioner DIC;" in updated
    assert "smoother DICGaussSeidel;" not in updated
    assert "maxIter 1000;" in updated
    assert "p_rghFinal { $p_rgh; relTol 0; }" in updated
    assert "U { solver PBiCGStab; preconditioner DILU; tolerance 1e-8; relTol 0.1; }" in updated

    control = tmp_path / "controlDict"
    control.write_text(
        "writeInterval 0.005;\npurgeWrite 0;\nfunctions {\nwriteInterval 1;\n}\n",
        encoding="ascii",
    )
    retention = restart.set_rolling_checkpoint_retention(control, retain_count=2)
    assert retention["previous_purge_write"] == 0
    assert retention["retained_checkpoint_count"] == 2
    assert "purgeWrite 2;" in control.read_text(encoding="ascii")


def test_pressure_dictionary_and_native_change_command_touch_only_declared_patches(
    tmp_path: Path,
) -> None:
    text = pressure_total_dictionary_text()
    assert text.startswith("FoamFile\n{")
    assert "class dictionary;" in text
    assert "object changeDictionaryDict;" in text
    assert "\np_rgh\n{" in text
    assert "internalField" not in text
    assert "p\n{" not in text
    assert text.count("type prghTotalPressure;") == 4
    assert all(f"{patch}\n        {{" in text for patch in PRESSURE_TOTAL_PATCHES)
    assert "p0 uniform 0;" in text
    assert "rho rho;" in text and "U U;" in text and "phi phi;" in text
    assert "value uniform 0;" in text

    case = tmp_path / "private-case"
    command = pressure_total_change_command(case)
    assert command == [
        "srun",
        "--nodes=3",
        "--ntasks=120",
        "--ntasks-per-node=40",
        "changeDictionary",
        "-parallel",
        "-fileHandler",
        "collated",
        "-case",
        str(case),
        "-time",
        "0.2",
        "-dict",
        "system/changeDictionaryDict",
    ]


def _write_synthetic_collated_pressure(path: Path, patch_type: str) -> None:
    entries = (
        "        p0 uniform 0;\n        rho rho;\n"
        "        U U;\n        phi phi;\n        value uniform 0;\n"
        if patch_type == "prghTotalPressure"
        else "        p uniform 0;\n        rho rho;\n        value uniform 0;\n"
    )
    patches = "\n".join(
        f"    {patch}\n    {{\n        type {patch_type};\n{entries}    }}"
        for patch in PRESSURE_TOTAL_PATCHES
    )
    with path.open("wb") as stream:
        for rank in range(120):
            text = (
                f"// processor{rank}\n1\n(\n"
                "FoamFile\n{\n    format      ascii;\n}\n"
                "dimensions [0 2 -2 0 0 0 0];\n"
                "internalField nonuniform List<scalar>\n2\n(\n1.25\n-2.5\n);\n"
                "boundaryField\n{\n"
                f"{patches}\n"
                "}\n)\n"
            )
            stream.write(text.encode("ascii"))


def test_pressure_checkpoint_integrity_uses_existing_native_reader(tmp_path: Path) -> None:
    case = tmp_path / "case"
    endpoint = case / "processors120/0.200000000000"
    endpoint.mkdir(parents=True)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    reader_path = Path(__file__).resolve().parents[1] / "src/aerial_drop/i4f_native_face_reader.py"
    (source_dir / "i4f_native_face_reader.py").write_bytes(reader_path.read_bytes())
    for relative in restart.REQUIRED_CHECKPOINT_FIELDS:
        if relative != "p_rgh":
            target = endpoint / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f"unchanged:{relative}\n".encode())
    pressure_path = endpoint / "p_rgh"
    _write_synthetic_collated_pressure(pressure_path, "prghPressure")
    before = pressure_checkpoint_integrity(case, source_dir)
    _write_synthetic_collated_pressure(pressure_path, "prghTotalPressure")
    after = pressure_checkpoint_integrity(case, source_dir)

    assert before["p_rgh_file_sha256"] != after["p_rgh_file_sha256"]
    assert before["unchanged_checkpoint_field_sha256"] == after["unchanged_checkpoint_field_sha256"]
    assert before["p_rgh_internal_sha256"] == after["p_rgh_internal_sha256"]
    assert before["p_rgh_internal_rank_sha256"] == after["p_rgh_internal_rank_sha256"]
    assert before["p_rgh_internal_value_count"] == 240
    restart.verify_pressure_total_patches(case, source_dir)


NATIVE_PARENT_TIME = (
    "value 0.199999999999994293;\n"
    'name "0.200000000000";\n'
    "index 2000;\n"
    "deltaT 0.0001;\n"
    "deltaT0 0.0001;\n"
)


def test_checkpoint_time_accepts_native_roundoff_and_equivalent_notation() -> None:
    validate_checkpoint_time(NATIVE_PARENT_TIME)
    equivalent = (
        NATIVE_PARENT_TIME.replace("0.199999999999994293", "2e-1")
        .replace("deltaT 0.0001", "deltaT 1e-4")
        .replace("deltaT0 0.0001", "deltaT0 1E-4")
    )
    validate_checkpoint_time(equivalent)


@pytest.mark.parametrize(
    ("bad_text", "message"),
    [
        (NATIVE_PARENT_TIME.replace("0.199999999999994293", "0.20000000001"), "exactly 0.2"),
        (NATIVE_PARENT_TIME.replace("deltaT 0.0001", "deltaT 0.0002"), "timestep"),
        (NATIVE_PARENT_TIME.replace("value 0.199999999999994293", "value nan"), "nonfinite"),
        (NATIVE_PARENT_TIME + "value 0.2;\n", "duplicate value"),
        (NATIVE_PARENT_TIME.replace("index 2000", "index 1999"), "index"),
        (NATIVE_PARENT_TIME.replace('name "0.200000000000"', 'name "0.199900000000"'), "name"),
    ],
)
def test_checkpoint_time_rejects_invalid_native_fields(bad_text: str, message: str) -> None:
    with pytest.raises(RestartError, match=message):
        validate_checkpoint_time(bad_text)


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
    early_save = config_for_variant("original-early-save")
    assert early_save.end_time_s == 0.202
    assert early_save.write_interval_s == 0.002
    assert early_save.wall_budget_s == 1200
    assert round((early_save.end_time_s - early_save.start_time_s) / early_save.delta_t_s) == 20


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

    equivalent_path = tmp_path / "controlDict-equivalent-dt"
    equivalent_path.write_text(
        "startFrom startTime;\nstartTime 0;\nendTime 0.2;\n"
        "deltaT 1e-4;\nadjustTimeStep no;\nwriteInterval 0.2;\n",
        encoding="utf-8",
    )
    rewrite_control_dict(equivalent_path, config_for_variant("pressure-total-continuation"))
    assert "deltaT 1e-4;" in equivalent_path.read_text(encoding="utf-8")


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


def test_terminal_receipt_keeps_diagnostic_early_save_separate_from_u_guard() -> None:
    early = build_terminal_status(
        return_code=0,
        end_marker=True,
        actual_time_s=0.2004,
        step_count=4,
        stop_detail=restart.EARLY_SAVE_STOP_REASON,
        pause_observed=False,
        stop_signals=["12"],
        endpoint_verified=True,
        variant="original-early-save",
        target_time_s=0.202,
        stop_signal_request_utc="2026-10-28T12:00:00+00:00",
        stop_signal_acknowledged_utc="2026-10-28T12:00:01+00:00",
        stop_signal_job_id="14700000",
        stop_signal_job_step="14700000.0",
        stop_signal_task_count=120,
        stop_signal_request_solver_time_s=0.2003,
        early_save_trigger_after_steps=3,
    )

    assert early["state"] == "diagnostic_early_saved"
    assert early["stop_reason"] == "diagnostic_early_save_after_3_steps"
    assert early["write_and_stop_acknowledged"] is True
    assert early["stop_signals"] == ["12"]

    unacknowledged = build_terminal_status(
        return_code=1,
        end_marker=False,
        actual_time_s=0.2004,
        step_count=4,
        stop_detail=restart.EARLY_SAVE_STOP_REASON,
        pause_observed=False,
        stop_signals=[],
        endpoint_verified=False,
        variant="original-early-save",
        target_time_s=0.202,
    )
    assert unacknowledged["state"] == "incomplete"
    assert unacknowledged["write_and_stop_requested"] is False
    assert unacknowledged["write_and_stop_acknowledged"] is False


def test_early_save_run_path_verifies_endpoint_and_records_partial_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in {
        "SLURM_JOB_ID": "14700001",
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
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(restart.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(restart, "PAUSE_FILE", tmp_path / "shared-PAUSE")
    monkeypatch.setattr(
        restart.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=20 * 1024**3),
    )
    monkeypatch.setattr(pilot, "_EXTERNAL_SIGNAL", None)

    def prepare_case(attempt: Path, _config: RestartConfig):
        case = attempt / "case"
        case.mkdir()
        (attempt / "seed-verification.json").write_text("{}\n", encoding="utf-8")
        (attempt / "manifest.json").write_text("{}\n", encoding="utf-8")
        endpoint = case / "processors120/0.200400000000"
        for field in restart.REQUIRED_CHECKPOINT_FIELDS:
            path = endpoint / field
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("native field\n", encoding="ascii")
        (endpoint / "uniform/time").write_text(
            'value 0.2004;\nname "0.200400000000";\nindex 2004;\ndeltaT 0.0001;\ndeltaT0 0.0001;\n',
            encoding="ascii",
        )
        return case, {}

    def fake_supervise(**kwargs):
        state = kwargs["state"]
        assert kwargs["stop_after_steps"] == 3
        times = [0.2001, 0.2002, 0.2003, 0.2004]
        log = (
            "sigStopAtWriteNow : Enabling writing and stopping upon signal 12\n"
            + "".join(f"Time = {instant:.12f}\n" for instant in times)
            + "sigStopAtWriteNow : setting up write and stop at end of the next iteration\n"
            + "End\n"
        )
        (kwargs["attempt"] / "solver.log").write_text(log, encoding="utf-8")
        (kwargs["attempt"] / "max-speed.csv").write_text(
            "time_s,max_magnitude_U_m_s\n0.2003,110\n", encoding="ascii"
        )
        monitor = restart.RestartOutputMonitor(
            last_progress_monotonic=0.0, horizon_s=0.202, delta_t_s=DT_S
        )
        monitor.feed("Time = 0.2", 1.0)
        for instant in times:
            monitor.feed(f"Time = {instant:.12f}", instant)
            monitor.feed("min / max (mag(U)) = 0 110", instant)
        monitor.feed(
            "sigStopAtWriteNow : setting up write and stop at end of the next iteration",
            2.0,
        )
        monitor.feed("End", 2.0)
        monitor.finish()
        state.update(
            solver_log_sha256=restart.sha256_file(kwargs["attempt"] / "solver.log"),
            max_speed_csv_sha256=restart.sha256_file(kwargs["attempt"] / "max-speed.csv"),
            stop_requested_utc="2026-10-28T12:00:00+00:00",
            stop_signal_acknowledged_utc="2026-10-28T12:00:01+00:00",
            stop_signal_job_step="14700001.0",
            stop_signal_task_count=120,
            stop_signal_request_solver_time_s=0.2003,
            early_save_trigger_after_steps=3,
            stop_signals=["12"],
        )
        return 0, monitor, restart.EARLY_SAVE_STOP_REASON, False

    def fake_pack(_attempt: Path, run_dir: Path):
        archive = run_dir / "result.tar.gz"
        archive.write_bytes(b"synthetic verified attempt")
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest(), 1, []

    monkeypatch.setattr(restart, "prepare_case", prepare_case)
    monkeypatch.setattr(restart, "verify_stop_contract", lambda *_args: {"signal": 12})
    monkeypatch.setattr(pilot, "supervise_solver", fake_supervise)
    monkeypatch.setattr(pilot, "inspect_solver_convergence", lambda *_args: {"all_converged": True})
    monkeypatch.setattr(pilot, "_write_step_accounting", lambda *_args: {})
    monkeypatch.setattr(pilot, "pack_attempt", fake_pack)
    monkeypatch.setattr(
        restart,
        "_run_audit",
        lambda case, _attempt, _config: {
            "status": "diagnostic_early_save_partial_exploratory_only",
            "step_count": 4,
            "case": str(case),
        },
    )
    from cases.e1_rouaix_hpc import collect_native_provenance

    monkeypatch.setattr(
        collect_native_provenance,
        "collect_native_provenance",
        lambda **kwargs: kwargs["output_path"].write_text("{}\n", encoding="utf-8"),
    )

    run_root = tmp_path / "results/runs/rouaix-early-save-v2-20261028"
    result = restart.run(run_root, config_for_variant("original-early-save"))

    run_dir = run_root / "rouaix-restart-original-early-save-14700001"
    state = json.loads((run_dir / "run-state.json").read_text(encoding="utf-8"))
    terminal = json.loads(
        (run_dir / "attempt/case/terminal-status.json").read_text(encoding="utf-8")
    )
    assert result == 0
    assert state["status"] == "diagnostic_early_save_complete"
    assert state["ledger_status"] == "written_from_hash_bound_parent_checkpoint"
    assert terminal["state"] == "diagnostic_early_saved"
    assert terminal["solver_time_steps_recorded"] == 4
    assert terminal["stop_signal_request_solver_time_s"] == 0.2003


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


def _completed_pressure_parent(
    tmp_path: Path, variant: str = "pressure-total-p0-zero"
) -> tuple[Path, str]:
    spec = restart.PARENT_CONTRACT_SPECS[variant]
    start_time_s = spec["start_time_s"]
    target_time_s = spec["target_time_s"]
    step_count = spec["step_count"]
    inventory_m3 = 0.379166666663 if variant == "pressure-total-p0-zero" else 0.36123456789
    write_interval_s = 0.05 if variant == "pressure-total-p0-zero" else 0.005
    job_id = "14709991" if variant == "pressure-total-p0-zero" else "14709993"
    run_dir = tmp_path / f"rouaix-restart-{variant}-{job_id}"
    attempt = run_dir / "attempt"
    case = attempt / "case"
    checkpoint_time_dir = f"processors120/{target_time_s:.12f}"
    endpoint = case / checkpoint_time_dir
    for relative in (
        "case-inputs.json",
        "system/controlDict",
        "system/decomposeParDict",
        "system/fvSchemes",
        "system/fvSolution",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        *(f"constant/polyMesh/{name}" for name in restart.MESH_FILES),
        *(f"processors120/constant/polyMesh/{name}" for name in restart.MESH_FILES),
    ):
        path = case / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            '{"rank_count":120}\n'
            if relative == "case-inputs.json"
            else f"startFrom latestTime;\nstartTime {start_time_s};\n"
            f"endTime {target_time_s};\ndeltaT 0.0001;\nadjustTimeStep no;\n"
            f"writeInterval {write_interval_s};\npurgeWrite 2;\n"
            if relative == "system/controlDict"
            else "numberOfSubdomains 120;\n"
            if relative == "system/decomposeParDict"
            else (
                "solvers\n{\n"
                "    p_rgh { solver PCG; preconditioner DIC; tolerance 1e-8; "
                "relTol 0.01; maxIter 1000; }\n"
                "    p_rghFinal { $p_rgh; relTol 0; }\n}\n"
                if relative == "system/fvSolution" and variant == "pressure-total-pcgdic"
                else "fixture\n"
            )
        )
        path.write_text(content, encoding="ascii")
    for field in restart.REQUIRED_CHECKPOINT_FIELDS:
        path = endpoint / field
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture field\n", encoding="ascii")
    (endpoint / "uniform/time").write_text(
        f'value {target_time_s};\nname "{target_time_s:.12f}";\n'
        f"index {round(target_time_s / 0.0001)};\ndeltaT 0.0001;\ndeltaT0 0.0001;\n",
        encoding="ascii",
    )
    patch_text = "\n".join(
        f"{patch}\n{{\ntype prghTotalPressure;\np0 uniform 0;\nrho rho;\n"
        "U U;\nphi phi;\nvalue uniform 0;\n}"
        for patch in restart.PRESSURE_TOTAL_PATCHES
    )
    (endpoint / "p_rgh").write_text(
        "".join(
            f"// processor{rank}\n1\n(\nboundaryField\n{{\n{patch_text}\n}}\n)\n"
            for rank in range(restart.EXPECTED_RANKS)
        ),
        encoding="ascii",
    )
    manifest = {
        "case_id": spec["case_id"],
        "rank_count": 120,
        "start_time_s": start_time_s,
        "horizon_s": target_time_s,
        "delta_t_s": 0.0001,
        "write_interval_s": write_interval_s,
        "pressure_total_p0_zero_sensitivity": {"p0_gauge_pa": 0.0},
    }
    if variant == "pressure-total-pcgdic":
        manifest["pressure_linear_solver_sensitivity"] = {
            "solver": "PCG",
            "preconditioner": "DIC",
            "p_rgh_maxIter": 1000,
            "tolerance": 1e-8,
            "relTol": 0.01,
            "p_rghFinal": "inherits PCG/DIC with relTol 0",
        }
    restart.write_json(attempt / "manifest.json", manifest)
    terminal = {
        "state": "terminal",
        "solver_exit_code": 0,
        "solver_end_marker": True,
        "pause_observed": False,
        "stop_reason": None,
        "solver_time_s": target_time_s,
        "target_time_s": target_time_s,
        "requested_start_time_s": start_time_s,
        "solver_time_steps_recorded": step_count,
    }
    restart.write_json(case / "terminal-status.json", terminal)
    history_path = case / "postProcessing/waterInventory/0/volFieldValue.dat"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        f"# Time volIntegrate(alpha.water)\n{start_time_s} 0.2508975771509\n"
        f"{target_time_s} {inventory_m3}\n",
        encoding="ascii",
    )
    ledger = {
        "coverage": {
            "status": "requested_horizon_reached_exploratory_only",
            "requested_target_reached": True,
            "actual_end_time_s": target_time_s,
        },
        "interval": {"step_count": step_count},
        "integration": {"density_kg_m3": 997.6, "final_inventory_m3": inventory_m3},
        "input_sources": {
            "native_histories": {
                "water_inventory": {
                    "path": str(history_path),
                    "sha256": restart.sha256_file(history_path),
                    "header": "Time volIntegrate(alpha.water)",
                }
            }
        },
    }
    restart.write_json(attempt / "ledger/summary.json", ledger)
    archive, archive_sha, member_count, member_sizes = pilot.pack_attempt(attempt, run_dir)
    state = {
        "status": "solver_complete_exploratory",
        "job_id": job_id,
        "case_id": spec["case_id"],
        "variant": variant,
        "solver_exit_code": 0,
        "solver_end_marker": True,
        "solver_time_steps_recorded": step_count,
        "start_time_s": start_time_s,
        "target_time_s": target_time_s,
        "delta_t_s": 0.0001,
        "solver_time_s": target_time_s,
        "stop_reason": None,
        "pause_observed": False,
        "solver_max_u_m_s": 114.2,
        "ledger_status": "written_from_hash_bound_parent_checkpoint",
        "attempt_archive_status": "verified_crc_hash_and_member_list",
        "result_archive": str(archive),
        "result_archive_sha256": archive_sha,
        "result_archive_members": member_count,
        "result_archive_member_sizes": member_sizes,
    }
    if variant == "pressure-total-pcgdic":
        state["solver_convergence"] = {"all_converged": True}
    restart.write_json(run_dir / "run-state.json", state)
    return run_dir, job_id


def test_dynamic_parent_contract_accepts_verified_030_checkpoint_and_rejects_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SLURM_JOB_ID", "14709992")
    run_dir, job_id = _completed_pressure_parent(tmp_path)
    contract = restart.verify_completed_parent(run_dir, job_id)

    assert restart.validate_parent_contract(contract, expected_time_s=0.3) is contract
    assert set(contract["checkpoint_fields"]) == set(restart.REQUIRED_CHECKPOINT_FIELDS)
    assert set(restart.MESH_FILES).issubset(contract["processor_mesh"])
    assert (
        restart.verify_parent_contract_archive(contract)["ledger"]["coverage"][
            "requested_target_reached"
        ]
        is True
    )

    attempt = tmp_path / "child-attempt"
    _case, child_manifest = restart.prepare_case(
        attempt, config_for_variant("pressure-total-continuation"), contract
    )
    assert child_manifest["parent_checkpoint_inventory_m3"] == pytest.approx(0.379166666663)
    assert child_manifest["parent_checkpoint_inventory_m3"] != restart.PARENT_INVENTORY_M3

    incomplete = dict(contract)
    incomplete.pop("ledger_sha256")
    with pytest.raises(RestartError, match="lacks"):
        restart.validate_parent_contract(incomplete)

    wrong_time = dict(contract, checkpoint_time_s=0.3001)
    with pytest.raises(RestartError, match="exact 0.3 s"):
        restart.validate_parent_contract(wrong_time)

    wrong_hash = dict(contract, archive_sha256="f" * 64)
    with pytest.raises(RestartError, match="run-state"):
        restart.verify_parent_contract_archive(wrong_hash)

    wrong_job = dict(contract, parent_job_id="14709992")
    with pytest.raises(RestartError, match="run-state"):
        restart.verify_parent_contract_archive(wrong_job)

    wrong_history = dict(contract, inventory_history_sha256="f" * 64)
    with pytest.raises(RestartError, match="hash-bound parent run-state|member hash"):
        restart.verify_parent_contract_archive(wrong_history)

    wrong_inventory = dict(contract, inventory_m3=contract["inventory_m3"] + 0.01)
    with pytest.raises(RestartError, match="inventory"):
        restart.verify_parent_contract_archive(wrong_inventory)


def test_pcgdic_parent_contract_prepares_only_the_255_to_300_inherited_policy_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SLURM_JOB_ID", "14709994")
    run_dir, job_id = _completed_pressure_parent(tmp_path, "pressure-total-pcgdic")
    contract = restart.verify_completed_parent(run_dir, job_id)

    assert contract["schema_version"] == 1
    assert contract["variant"] == "pressure-total-pcgdic"
    assert contract["parent_start_time_s"] == pytest.approx(0.2)
    assert contract["parent_target_time_s"] == pytest.approx(0.255)
    assert contract["checkpoint_time_s"] == pytest.approx(0.255)
    assert contract["inventory_history_time_s"] == pytest.approx(0.255)
    assert contract["step_count"] == 550
    assert contract["fv_solution_member"] == "attempt/case/system/fvSolution"
    assert contract["fv_solution_sha256"] == restart.sha256_file(
        run_dir / "attempt/case/system/fvSolution"
    )
    assert restart.validate_parent_contract(contract, expected_time_s=0.255) is contract
    verified = restart.verify_parent_contract_archive(contract)
    assert verified["terminal"]["solver_time_s"] == pytest.approx(0.255)

    attempt = tmp_path / "pcgdic-child-attempt"
    case, manifest = restart.prepare_case(
        attempt, config_for_variant("pressure-pcgdic-continuation"), contract
    )
    assert manifest["start_time_s"] == pytest.approx(0.255)
    assert manifest["horizon_s"] == pytest.approx(0.3)
    assert manifest["parent_checkpoint_inventory_m3"] == pytest.approx(0.36123456789)
    assert manifest["parent_checkpoint_inventory_m3"] != restart.PARENT_INVENTORY_M3
    assert manifest["numerical_variant"] == "inherited-pcg-dic"
    assert (
        manifest["pressure_linear_solver_inherited"]["fv_solution_sha256"]
        == contract["fv_solution_sha256"]
    )
    fv_solution = case / "system/fvSolution"
    assert restart.sha256_file(fv_solution) == contract["fv_solution_sha256"]
    assert fv_solution.stat().st_mode & 0o222 == 0
    control = (case / "system/controlDict").read_text(encoding="ascii")
    assert "startTime 0.255;" in control
    assert "endTime 0.3;" in control
    assert "writeInterval 0.005;" in control
    assert "purgeWrite 2;" in control
    assert not (case / "system/changeDictionaryDict").exists()

    altered_inventory_time = dict(contract, inventory_history_time_s=0.3)
    with pytest.raises(RestartError, match="inventory or water density"):
        restart.validate_parent_contract(altered_inventory_time)
    altered_solver = dict(contract, fv_solution_sha256="f" * 64)
    with pytest.raises(RestartError, match="member hash|solver dictionary"):
        restart.verify_parent_contract_archive(altered_solver)

    state_path = Path(contract["run_state_path"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["solver_convergence"] = {"all_converged": False}
    restart.write_json(state_path, state)
    wrong_convergence = dict(contract, run_state_sha256=restart.sha256_file(state_path))
    with pytest.raises(RestartError, match="lacks converged pressure solves"):
        restart.verify_parent_contract_archive(wrong_convergence)


def test_legacy_seed_contract_keeps_the_original_hash_gate(tmp_path: Path) -> None:
    archive = tmp_path / "wrong-parent.tar.gz"
    archive.write_bytes(b"not the frozen .2 parent")
    with pytest.raises(RestartError, match="SHA-256 mismatch"):
        restart.extract_seed_archive(archive, tmp_path / "attempt")


def test_pressure_total_continuation_config_is_frozen_at_030_to_050() -> None:
    config = config_for_variant("pressure-total-continuation")
    assert (config.start_time_s, config.end_time_s, config.delta_t_s) == (0.3, 0.5, 0.0001)
    assert config.write_interval_s == 0.05
    assert config.wall_budget_s == 7200
    assert round((config.end_time_s - config.start_time_s) / config.delta_t_s) == 2000

    pcgdic = config_for_variant("pressure-pcgdic-continuation")
    assert (pcgdic.start_time_s, pcgdic.end_time_s, pcgdic.delta_t_s) == (
        0.255,
        0.3,
        0.0001,
    )
    assert pcgdic.write_interval_s == 0.005
    assert pcgdic.wall_budget_s == 7200
    assert round((pcgdic.end_time_s - pcgdic.start_time_s) / pcgdic.delta_t_s) == 450
