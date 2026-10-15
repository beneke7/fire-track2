#!/usr/bin/env python3
"""Keep the resumed Rouaix branch within 10 CPUs and continue from a safe checkpoint.

This private supervisor is intentionally run-local. It first keeps the baseline
at six CPUs while the four-CPU MULES comparison is active, raises the baseline
to ten CPUs after that container exits, then prepares a fresh sparse
continuation if the original 12-hour timeout ends before t=5 s.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
PAIR = ROOT / "results/runs/rouaix-c4-vof-transport-pair-20261012T1920Z/mules"
BASE_NAME = "rr-rouaix-c4-reproduction-5s-20261012T1000Z"
PAIR_NAME = "rr-rouaix-c4-paired-stock-mules-restart-4mpi-to-1p800234-20261012T1920Z"
IMAGE = "opencfd/openfoam-default:2512"
IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
OPENFOAM_BASHRC = "/usr/lib/openfoam/openfoam2512/etc/bashrc"
MIN_FREE = 60 * 1024**3
PREPARE_HEADROOM = 4 * 1024**3
BASE_CAP = 15 * 1024**3
NEW_WALL_S = 24 * 60 * 60
FIELDS = ("alpha.water", "U", "p_rgh", "k", "epsilon", "nut")
PATCHES = (
    "gasInlet",
    "downstreamOutlet",
    "bottomOutlet",
    "aircraftWall",
    "spanwiseMinus",
    "spanwisePlus",
    "nozzle",
)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,54}$")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): sha256(item)
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def tree_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def record(event: dict[str, Any]) -> None:
    event = {"utc": utc_now(), **event}
    path = BASE / "resume-chain" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")
    write_json(BASE / "resume-chain" / "state.json", event)


def inspect_container(name: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["docker", "inspect", name], text=True, capture_output=True, timeout=30, check=False
    )
    if result.returncode:
        return None
    try:
        data = json.loads(result.stdout)[0]
    except (json.JSONDecodeError, IndexError):
        return None
    state = data.get("State", {})
    return {
        "id": data.get("Id"),
        "name": name,
        "running": bool(state.get("Running")),
        "paused": bool(state.get("Paused")),
        "status": state.get("Status"),
        "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled"),
        "nano_cpus": data.get("HostConfig", {}).get("NanoCpus"),
        "cpu_shares": data.get("HostConfig", {}).get("CpuShares"),
        "memory_bytes": data.get("HostConfig", {}).get("Memory"),
    }


def set_cpu_quota(name: str, cpu_count: int) -> dict[str, Any]:
    state = inspect_container(name)
    if state is None or not state["running"]:
        return {"name": name, "running": False, "requested_cpu_count": cpu_count}
    result = subprocess.run(
        ["docker", "update", f"--cpus={cpu_count}", "--cpu-shares=512", name],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"docker update failed for {name}: {result.stderr.strip()}")
    updated = inspect_container(name)
    expected = cpu_count * 1_000_000_000
    if updated is None or updated["nano_cpus"] != expected or updated["cpu_shares"] != 512:
        raise RuntimeError(f"quota verification failed for {name}: {updated}")
    return {**updated, "requested_cpu_count": cpu_count}


def process_alive(pid: Any) -> bool:
    try:
        status = Path(f"/proc/{int(pid)}/stat").read_text(encoding="ascii").split()
    except (OSError, TypeError, ValueError):
        return False
    return len(status) > 2 and status[2] != "Z"


def pair_still_supervised(container: dict[str, Any] | None) -> bool:
    if container and container["running"] and not container["paused"]:
        return True
    try:
        state = read_json(PAIR / "worker-state.json")
    except (OSError, ValueError):
        return False
    if state.get("status") != "solver_running":
        return False
    return process_alive(state.get("host_worker_pid")) or process_alive(state.get("monitor_pid"))


def stop_owned(reason: str) -> None:
    record({"status": "resource_guard_stop", "reason": reason})
    for name in (PAIR_NAME, BASE_NAME):
        state = inspect_container(name)
        if state and state["running"]:
            subprocess.run(
                ["docker", "stop", "--time", "60", name],
                text=True,
                capture_output=True,
                timeout=90,
                check=False,
            )


def numeric_dirs(rank: Path) -> set[str]:
    return {
        child.name
        for child in rank.iterdir()
        if child.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", child.name)
    }


def latest_complete_checkpoint(case: Path) -> tuple[str, dict[str, Any]]:
    ranks = sorted(case.glob("processor[0-9]*"), key=lambda p: int(p.name.removeprefix("processor")))
    expected_names = [f"processor{i}" for i in range(16)]
    if [rank.name for rank in ranks] != expected_names:
        raise RuntimeError(f"expected sixteen decomposed ranks, found {[p.name for p in ranks]}")
    common = set.intersection(*(numeric_dirs(rank) for rank in ranks))
    candidates = sorted(common, key=float, reverse=True)
    if not candidates:
        raise RuntimeError("no shared numeric field-time directory exists")
    for name in candidates:
        okay = True
        for rank in ranks:
            folder = rank / name
            uniform_time = folder / "uniform/time"
            try:
                uniform = uniform_time.read_text(encoding="ascii", errors="replace")
            except OSError:
                okay = False
                break
            exact_name = re.search(r'\bname\s+"([^"]+)"\s*;', uniform)
            exact_value = re.search(r"\bvalue\s+([^;\s]+)\s*;", uniform)
            if (
                exact_name is None
                or exact_value is None
                or exact_name.group(1) != name
                or abs(float(exact_value.group(1)) - float(name)) > 1e-10
            ):
                okay = False
                break
            if any(not (folder / field).is_file() or (folder / field).stat().st_size == 0 for field in FIELDS):
                okay = False
                break
            if not (folder / "uniform/cumulativeContErr").is_file():
                okay = False
                break
        if okay:
            import importlib.util

            runner_path = ROOT / "scripts/run_rouaix_reproduction.py"
            spec = importlib.util.spec_from_file_location("rouaix_restart_field_check", runner_path)
            if spec is None or spec.loader is None:
                raise RuntimeError("cannot load the existing checkpoint-field validator")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.CHECKPOINT_NAME = name
            module.FIELDS = FIELDS
            try:
                field_health = module.validate_checkpoint(case)
            except (OSError, ValueError, RuntimeError) as error:
                record({"status": "checkpoint_candidate_rejected", "checkpoint_time_s": float(name), "reason": str(error)})
                continue
            return name, field_health
    raise RuntimeError("no common checkpoint has all six fields and matching uniform/time records")


def audit_parent(case: Path, declaration: Path, time_name: str, out: Path) -> dict[str, Any]:
    command = [
        str(ROOT / ".venv/bin/python"),
        str(ROOT / "scripts/rouaix_checkpoint_audit.py"),
        "--case",
        str(case),
        "--declaration",
        str(declaration),
        "--through-time",
        time_name,
        "--output-dir",
        str(out),
    ]
    env = os.environ.copy()
    for key in ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=900, check=False)
    (out / "audit.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (out / "audit.stderr.txt").write_text(result.stderr, encoding="utf-8")
    report_path = out / "ledger-report.json"
    if result.returncode or not report_path.is_file():
        raise RuntimeError(f"terminal native ledger audit exited {result.returncode}; see {out}")
    report = read_json(report_path)
    guard = report["continuation_guard_0p1_percent"]
    if not guard["incremental_pass"] or not guard["cumulative_pass"]:
        raise RuntimeError(f"latest checkpoint failed the existing 0.1% operational ledger guard: {guard}")
    if abs(float(report["actual_final_time_s"]) - float(time_name)) > 1e-10:
        raise RuntimeError("terminal audit did not end at the exact selected field time")
    return report


def audit_pair_terminal() -> dict[str, Any]:
    """Capture the MULES branch's final native ledger row, even without a field write."""
    import importlib.util

    auditor_path = PAIR / "audit_checkpoint.py"
    spec = importlib.util.spec_from_file_location("rouaix_mules_terminal_audit", auditor_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the private MULES restart auditor")
    auditor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auditor)
    case = PAIR / "case"
    declaration_path = PAIR / "case-declaration.json"
    inventory_path = auditor.history_file(case, "waterInventory", "volFieldValue.dat")
    histories: dict[str, list[tuple[float, float]]] = {
        "waterInventory": auditor.read_history(inventory_path)
    }
    for patch in PATCHES:
        path = auditor.history_file(case, f"liquidFlux_{patch}", "surfaceFieldValue.dat")
        histories[patch] = auditor.read_history(path)
    inventory_rows = histories["waterInventory"]
    if not inventory_rows:
        raise RuntimeError("MULES branch wrote no native waterInventory rows")
    final_time = inventory_rows[-1][0]
    times, _, excluded = auditor.select_exact_shared_checkpoint(histories, final_time)
    if not times or abs(times[-1] - final_time) > 1e-10 or excluded:
        raise RuntimeError("MULES terminal history rows do not align at one exact final time")
    attempt = 1
    output = PAIR / f"terminal-ledger-audit-attempt{attempt}"
    while output.exists():
        attempt += 1
        output = PAIR / f"terminal-ledger-audit-attempt{attempt}"
    output.mkdir(parents=True, exist_ok=False)
    command = [
        str(ROOT / ".venv/bin/python"), str(auditor_path), "--case", str(case),
        "--declaration", str(declaration_path), "--through-time", f"{final_time:.13g}",
        "--output-dir", str(output),
    ]
    env = os.environ.copy()
    for key in ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=900, check=False)
    (output / "audit.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "audit.stderr.txt").write_text(result.stderr, encoding="utf-8")
    report_path = output / "ledger-report.json"
    if result.returncode or not report_path.is_file():
        raise RuntimeError(f"MULES terminal native ledger audit exited {result.returncode}: {result.stderr[-1000:]}")
    report = read_json(report_path)
    guard = report["continuation_guard_0p1_percent"]
    summary = {
        "status": "captured",
        "run_id": report.get("run_id"),
        "declared_end_time_s": read_json(declaration_path)["continuation"]["end_time_s"],
        "actual_terminal_history_time_s": report["actual_final_time_s"],
        "rows": report["rows"],
        "incremental_residual_kg": report["incremental_ledger_from_checkpoint"]["residual_expected_minus_observed_kg"],
        "incremental_residual_fraction": report["incremental_ledger_from_checkpoint"]["residual_fraction_of_incremental_source"],
        "cumulative_residual_kg": report["cumulative_ledger_from_t0"]["residual_expected_minus_observed_kg"],
        "cumulative_residual_fraction": report["cumulative_ledger_from_t0"]["residual_fraction_of_total_source"],
        "incremental_guard_pass": bool(guard["incremental_pass"]),
        "cumulative_guard_pass": bool(guard["cumulative_pass"]),
        "actual_terminal_time_matches_declared_target": abs(float(report["actual_final_time_s"]) - float(read_json(declaration_path)["continuation"]["end_time_s"])) <= 1e-8,
        "ledger_report": str(report_path.relative_to(ROOT)),
        "active_native_histories": report["artifacts"],
    }
    write_json(PAIR / "terminal-ledger-summary.json", summary)
    record({"status": "mules_terminal_ledger_captured", **summary})
    return summary


def copy_file(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    source_hash, target_hash = sha256(source), sha256(target)
    if source_hash != target_hash:
        raise RuntimeError(f"copy hash mismatch: {source}")
    return target_hash


def copy_tree(source: Path, target: Path) -> dict[str, str]:
    shutil.copytree(source, target)
    expected = tree_hash(source)
    if tree_hash(target) != expected:
        raise RuntimeError(f"tree hash mismatch: {source}")
    return expected


def set_top_level(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^({re.escape(key)}\s+)[^;]+;")
    result, count = pattern.subn(rf"\g<1>{value};", text, count=1)
    if count != 1:
        raise RuntimeError(f"expected exactly one controlDict entry {key}")
    return result


def create_continuation(time_name: str, report: dict[str, Any], audit_report_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"rouaix-c4-reproduction-5s-resume-{stamp}"
    if not RUN_ID_RE.fullmatch(run_id):
        raise RuntimeError(f"generated run id is invalid: {run_id}")
    run_dir = ROOT / "results/runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    case = run_dir / "case"
    case.mkdir()
    parent_case = BASE / "case"
    source_decl_path = BASE / "case-declaration.json"
    source_decl = read_json(source_decl_path)
    source_hashes: dict[str, Any] = {"root": {}, "processor_meshes": {}, "checkpoint_fields": {}}

    source_hashes["root/constant"] = copy_tree(parent_case / "constant", case / "constant")
    source_hashes["root/system"] = copy_tree(parent_case / "system", case / "system")
    system_dir = case / "system"
    control = system_dir / "controlDict"
    control_text = control.read_text(encoding="utf-8")
    source_control_hash = sha256(control)
    for key, value in (("application", "interIsoFoam"), ("startFrom", "latestTime"), ("endTime", "5"), ("writeControl", "adjustableRunTime"), ("writeInterval", "0.5"), ("timePrecision", "13")):
        control_text = set_top_level(control_text, key, value)
    if "OptimisationSwitches" in control_text:
        raise RuntimeError("source already contains OptimisationSwitches; refusing implicit edit")
    control_text += "\nOptimisationSwitches\n{\n    writeNowSignal 10;\n    stopAtWriteNowSignal 12;\n}\n"
    control.write_text(control_text, encoding="utf-8")
    source_hashes["system/controlDict"] = {
        "source_sha256": source_control_hash,
        "prepared_sha256": sha256(control),
        "changes": {
            "startFrom": "latestTime",
            "endTime": "5",
            "writeControl": "adjustableRunTime",
            "writeInterval": "0.5",
            "timePrecision": "13",
            "run_local_writeNowSignal": 10,
            "run_local_stopAtWriteNowSignal": 12,
        },
    }

    source_ranks = sorted(parent_case.glob("processor[0-9]*"), key=lambda p: int(p.name.removeprefix("processor")))
    target_time_s = float(time_name)
    for rank in source_ranks:
        target_rank = case / rank.name
        source_hashes["processor_meshes"][rank.name] = copy_tree(
            rank / "constant/polyMesh", target_rank / "constant/polyMesh"
        )
        source_hashes["checkpoint_fields"][rank.name] = {}
        old_time = rank / time_name
        new_time = target_rank / time_name
        new_time.mkdir(parents=True)
        for field in FIELDS:
            digest = copy_file(old_time / field, new_time / field)
            source_hashes["checkpoint_fields"][rank.name][field] = digest
        for field in ("time", "cumulativeContErr"):
            digest = copy_file(old_time / "uniform" / field, new_time / "uniform" / field)
            source_hashes["checkpoint_fields"][rank.name][f"uniform/{field}"] = digest

    parent = report["cumulative_ledger_from_t0"]
    checkpoint_volume = float(parent["final_stored_volume_m3"])
    offsets = {
        "checkpoint_inventory_volume_m3": checkpoint_volume,
        "checkpoint_residual_expected_minus_observed_kg": float(parent["residual_expected_minus_observed_kg"]),
        "offset_applied_once": True,
        "prior_escape_volume_m3": float(parent["total_escape_volume_m3"]),
        "prior_release_volume_m3": float(parent["total_source_volume_m3"]),
    }
    declaration = json.loads(json.dumps(source_decl))
    declaration.update(
        {
            "run_id": run_id,
            "status": "declared_before_launch",
            "declared_utc": utc_now(),
            "purpose": "Exploratory continuation of the Rouaix Case 4 coarse 70 mm constant-jet baseline from the latest exact, complete, native-ledger-audited checkpoint.",
            "checkpoint": {
                "time_s": target_time_s,
                "directory_name": time_name,
                "native_water_volume_m3": checkpoint_volume,
                "native_water_mass_kg": checkpoint_volume * 997.6,
                "native_inventory_source": "exact common native waterInventory row audited at the selected complete checkpoint",
                "rank_count": 16,
                "field_health": {
                    "fields": list(FIELDS),
                    "all_fields_finite": True,
                    "validated_checkpoint_directory": True,
                },
            },
            "parent_ledger_offsets": offsets,
        }
    )
    declaration["continuation"].update(
        {
            "from_time_s": target_time_s,
            "end_time_s": 5.0,
            "physical_time_advanced_s": 5.0 - target_time_s,
            "checkpoint_time_precision": 13,
            "writeInterval_s": 0.5,
            "wall_budget_s": NEW_WALL_S,
            "parent_offsets_applied_once": True,
            "predecessor_postProcessing_copied": False,
            "predecessor_logs_or_fields_overwritten": False,
            "fresh_native_histories_begin_after_this_checkpoint": True,
        }
    )
    declaration["resource_allocation"].update(
        {
            "cpu_limit": 10,
            "mpi_ranks": 16,
            "memory_limit_gib": 48,
            "threads_per_rank": 1,
            "gpu": False,
            "wall_budget_s": NEW_WALL_S,
            "free_disk_floor_bytes": MIN_FREE,
            "new_bundle_footprint_cap_bytes": BASE_CAP,
            "cpu_policy": "16 MPI ranks under a hard 10 CPU-equivalent container quota; retained partition, no repartitioning",
            "cpu_shares": 512,
            "openmpi_mpi_yield_when_idle": 1,
            "openmpi_mca_source": "pinned-container ompi_info read-only check; default is false, option description recommends 1 when oversubscribing",
        }
    )
    declaration["continuation"]["mpi_idle_wait_policy"] = "mpirun -mca mpi_yield_when_idle 1; scheduler-only setting, no change to solver physics"
    declaration["source_run"] = {
        "run_id": BASE.name,
        "directory": str(BASE.relative_to(ROOT)),
        "checkpoint_time_s": target_time_s,
        "checkpoint_audit_report": str(audit_report_path.relative_to(ROOT)),
        "case_declaration_sha256": sha256(source_decl_path),
        "source_control_dict_sha256": source_control_hash,
        "parent_native_histories_copied": False,
        "prior_release_escape_and_inventory_offsets_carried_once": True,
    }
    declaration.setdefault("restart_chain", {})
    declaration["restart_chain"].update(
        {
            "parent_run": BASE.name,
            "selected_complete_checkpoint_s": target_time_s,
            "parent_ledger_guard_passed": True,
            "copied_fields": list(FIELDS),
            "copied_processor_mesh_hashes": source_hashes["processor_meshes"],
            "copied_checkpoint_hashes": source_hashes["checkpoint_fields"],
            "excluded_from_child_case": ["postProcessing", "logs", "predecessor time directories", "old monitor/audit output"],
            "continuation_method": "fresh interIsoFoam process at latestTime; original physics and mesh retained",
        }
    )
    declaration["input_hashes"]["restart_chain_copy"] = source_hashes
    declaration["input_hashes"]["audit_helper"] = {
        "source": str((PAIR / "audit_checkpoint.py").relative_to(ROOT)),
        "sha256": sha256(PAIR / "audit_checkpoint.py"),
        "note": "restart-segment selector uses this child attempt's native output file and does not blend predecessor rows",
    }
    declaration["preflight"]["parent_checkpoint_audit"] = {
        "status": "pass",
        "actual_final_time_s": report["actual_final_time_s"],
        "rows": report["rows"],
        "incremental_guard": report["continuation_guard_0p1_percent"]["incremental_pass"],
        "cumulative_guard": report["continuation_guard_0p1_percent"]["cumulative_pass"],
    }

    shutil.copy2(PAIR / "audit_checkpoint.py", run_dir / "audit_checkpoint.py")
    monitor = (BASE / "checkpoint_monitor.py").read_text(encoding="utf-8")
    old_name_line = f'NAME = "{BASE_NAME}"'
    if monitor.count(old_name_line) != 1:
        raise RuntimeError("baseline checkpoint monitor name template changed")
    new_name = "rr-" + run_id[:50]
    monitor = monitor.replace(old_name_line, f'NAME = "{new_name}"', 1)
    (run_dir / "checkpoint_monitor.py").write_text(monitor, encoding="utf-8")
    write_json(run_dir / "case-declaration.json", declaration)
    write_json(run_dir / "case.json", declaration)
    measured_bytes = sum((case / f"processor{i}" / time_name / field).stat().st_size for i in range(16) for field in FIELDS)
    write_json(
        run_dir / "prepare-state.json",
        {
            "status": "prepared",
            "prepared_utc": utc_now(),
            "run_id": run_id,
            "checkpoint_time_s": target_time_s,
            "end_time_s": 5.0,
            "checkpoint_bytes_all_ranks": measured_bytes,
            "case_bytes": tree_size(case),
            "disk_free_bytes": shutil.disk_usage(ROOT).free,
            "fresh_postProcessing": True,
            "restart_signal_overrides": {"writeNowSignal": 10, "stopAtWriteNowSignal": 12},
            "hash_manifest": source_hashes,
        },
    )
    if shutil.disk_usage(ROOT).free < MIN_FREE:
        raise RuntimeError("disk crossed the 60 GiB floor during restart-case preparation")
    if tree_size(run_dir) >= BASE_CAP:
        raise RuntimeError("prepared continuation reached the 15 GiB bundle guard")
    return run_dir


def docker_command(run_dir: Path) -> list[str]:
    run_id = run_dir.name
    name = "rr-" + run_id[:50]
    case = run_dir / "case"
    flow = (
        "set +e +u; source " + OPENFOAM_BASHRC + " >/dev/null 2>&1; setup=$?; "
        "set -euo pipefail; printf 'ROUAIX_SETUP_EXIT code=%s\\n' \"$setup\"; "
        "if [ \"$setup\" -ne 0 ]; then exit \"$setup\"; fi; "
        "run_stage() { stage=$1; shift; set +e; \"$@\"; code=$?; set -e; "
        "printf 'ROUAIX_STAGE_EXIT stage=%s code=%s\\n' \"$stage\" \"$code\"; "
        "if [ \"$code\" -ne 0 ]; then exit \"$code\"; fi; }; "
        "run_stage dictionary-time-precision foamDictionary system/controlDict -entry timePrecision -value; "
        "run_stage dictionary-ranks foamDictionary system/decomposeParDict -entry numberOfSubdomains -value; "
        "run_stage solver timeout --signal=TERM --kill-after=60s 86400s mpirun --bind-to none -mca mpi_yield_when_idle 1 -np 16 interIsoFoam -parallel; "
        "run_stage reconstruct reconstructPar -latestTime -fields '(alpha.water U p_rgh k epsilon nut)'"
    )
    command = [
        "docker", "run", f"--name={name}", f"--cidfile={run_dir / 'flow.cid'}",
        "--cpus=10", "--cpu-shares=512", "--memory=48g", "--memory-swap", "48g",
    ]
    for env_value in (
        "OMP_NUM_THREADS=1", "OMP_THREAD_LIMIT=1", "OPENBLAS_NUM_THREADS=1",
        "MKL_NUM_THREADS=1", "BLIS_NUM_THREADS=1", "NUMEXPR_NUM_THREADS=1",
    ):
        command.extend(["--env", env_value])
    command.extend([
        "--user", f"{os.getuid()}:{os.getgid()}", "--mount",
        f"type=bind,src={case},dst=/case", "--workdir", "/case", "--entrypoint", "/bin/bash",
        IMAGE, "-c", flow,
    ])
    return command


def parse_docker_top_pids(output: str) -> list[int]:
    """Parse only PID columns; command text is never used to identify ranks."""
    pids: list[int] = []
    for line in output.splitlines():
        match = re.match(r"\s*(\d+)(?:\s|$)", line)
        if match:
            pids.append(int(match.group(1)))
    return sorted(set(pids))


def process_identity(pid: int, proc_root: Path = Path("/proc")) -> dict[str, Any] | None:
    process_dir = proc_root / str(pid)
    try:
        comm = (process_dir / "comm").read_text(encoding="ascii").strip()
        status = (process_dir / "status").read_text(encoding="ascii")
        raw_cmdline = (process_dir / "cmdline").read_bytes()
        exe_path = os.readlink(process_dir / "exe")
    except OSError:
        return None
    state_match = re.search(r"(?m)^State:\s+(\S+)", status)
    argv = [value.decode("utf-8", errors="replace") for value in raw_cmdline.split(b"\0") if value]
    argv0 = argv[0] if argv else ""
    return {
        "pid": pid,
        "comm": comm,
        "state": state_match.group(1) if state_match else "?",
        "argv0": argv0,
        "exe_path": exe_path,
    }


def is_actual_solver_process(identity: dict[str, Any], solver_name: str) -> bool:
    """Require the process identity to be the solver executable, not a wrapper argv."""
    exe_name = Path(str(identity.get("exe_path", ""))).name.removesuffix(" (deleted)")
    argv0_name = Path(str(identity.get("argv0", ""))).name
    return (
        identity.get("state") != "Z"
        and identity.get("comm") == solver_name
        and (exe_name == solver_name or argv0_name == solver_name)
    )


def container_process_identities(name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    result = subprocess.run(
        ["docker", "top", name, "-eo", "pid"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        return [], [], False
    ranks: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for pid in parse_docker_top_pids(result.stdout):
        identity = process_identity(pid)
        if identity is None:
            excluded.append({"pid": pid, "reason": "process exited before /proc inspection"})
        elif is_actual_solver_process(identity, "interIsoFoam"):
            ranks.append(identity)
        else:
            excluded.append(identity)
    return ranks, excluded, True


def handler_evidence(name: str) -> dict[str, Any]:
    container = inspect_container(name)
    ranks, excluded, top_succeeded = container_process_identities(name)
    expected = {10: 1 << 9, 12: 1 << 11}
    observed: list[dict[str, Any]] = []
    for identity in ranks:
        pid = int(identity["pid"])
        try:
            status = Path(f"/proc/{pid}/status").read_text(encoding="ascii")
        except OSError:
            continue
        match = re.search(r"(?m)^SigCgt:\s*([0-9a-fA-F]+)\s*$", status)
        mask = int(match.group(1), 16) if match else 0
        observed.append(
            {
                **identity,
                "SigCgt": match.group(1) if match else None,
                "required_mask": 0xA00,
                "write_signal10_caught": (mask & expected[10]) == expected[10],
                "stop_signal12_caught": (mask & expected[12]) == expected[12],
            }
        )
    return {
        "verified_utc": utc_now(),
        "container_running": bool(container and container["running"] and not container["paused"]),
        "docker_top_succeeded": top_succeeded,
        "expected_ranks": 20,
        "solver_process_count": len(observed),
        "solver_ranks": observed,
        "excluded_container_processes": excluded,
        "all_rank_handlers_verified": len(observed) == 20
        and all(rank["write_signal10_caught"] and rank["stop_signal12_caught"] for rank in observed),
    }


class HandlerStartupError(RuntimeError):
    def __init__(self, message: str, evidence: dict[str, Any]):
        super().__init__(message)
        self.evidence = evidence


def wait_for_signal_handlers(
    evidence_provider: Any,
    *,
    timeout_s: float = 180.0,
    poll_s: float = 2.0,
    clock: Any = time.monotonic,
    sleeper: Any = time.sleep,
) -> dict[str, Any]:
    """Wait a bounded startup window for exactly sixteen real solver ranks."""
    started = clock()
    polls = 0
    last: dict[str, Any] = {}
    while True:
        last = evidence_provider()
        polls += 1
        if not last.get("container_running", True):
            raise HandlerStartupError("container exited before all solver signal handlers were ready", last)
        if last.get("all_rank_handlers_verified"):
            return {
                **last,
                "startup_wait_s": round(clock() - started, 3),
                "startup_poll_count": polls,
                "startup_wait_status": "passed",
            }
        elapsed = clock() - started
        if elapsed >= timeout_s:
            raise HandlerStartupError(
                f"signal-handler startup timed out after {elapsed:.1f}s with {last.get('solver_process_count')} exact solver processes",
                {
                    **last,
                    "startup_wait_s": round(elapsed, 3),
                    "startup_poll_count": polls,
                    "startup_wait_status": "timed_out",
                },
            )
        sleeper(min(poll_s, timeout_s - elapsed))


def solver_pids(name: str) -> list[int]:
    ranks, _, _ = container_process_identities(name)
    return sorted(int(rank["pid"]) for rank in ranks)


def launch_worker(run_dir: Path) -> int:
    state_path = run_dir / "worker-state.json"
    state: dict[str, Any] = {"status": "launching", "run_id": run_dir.name, "started_utc": utc_now(), "mpi_ranks": 16, "cpu_quota": 10, "memory_gib": 48}
    write_json(state_path, state)
    if shutil.disk_usage(ROOT).free < MIN_FREE or tree_size(run_dir) >= BASE_CAP:
        raise RuntimeError("resource guard failed before continuation launch")
    command = docker_command(run_dir)
    write_json(run_dir / "docker-command.json", {"command": command, "created_utc": utc_now(), "cpu_quota": 10, "cpu_shares": 512, "wall_cap_s": NEW_WALL_S})
    flow = (run_dir / "flow.log").open("ab", buffering=0)
    try:
        solver = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=flow, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    finally:
        flow.close()
    name = "rr-" + run_dir.name[:50]
    cidfile = run_dir / "flow.cid"
    deadline = time.monotonic() + 180
    state_obj = None
    while time.monotonic() < deadline:
        state_obj = inspect_container(name)
        if state_obj and state_obj["running"] and cidfile.is_file():
            break
        if solver.poll() is not None:
            break
        time.sleep(2)
    if not state_obj or not state_obj["running"]:
        code = solver.poll()
        if code is None:
            subprocess.run(["docker", "stop", "--time", "20", name], cwd=ROOT, capture_output=True, timeout=30, check=False)
            code = solver.wait(timeout=60)
        state.update({"status": "failed_before_solver", "docker_client_exit_code": code, "container": inspect_container(name), "finished_utc": utc_now()})
        write_json(state_path, state)
        return int(code or 1)
    cid = cidfile.read_text(encoding="ascii").strip()
    try:
        handlers = wait_for_signal_handlers(lambda: handler_evidence(name), timeout_s=180.0, poll_s=2.0)
    except HandlerStartupError as error:
        handlers = error.evidence
        write_json(run_dir / "signal-handler-verification.json", handlers)
        failure_reason = f"signal-handler startup check failed: {error}"
        (run_dir / "startup-guard-failure.txt").write_text(failure_reason + "\n", encoding="utf-8")
        current = inspect_container(name)
        if current and current["running"]:
            subprocess.run(["docker", "stop", "--time", "30", name], cwd=ROOT, capture_output=True, timeout=45, check=False)
        try:
            docker_code = solver.wait(timeout=60)
        except subprocess.TimeoutExpired:
            solver.kill()
            docker_code = solver.wait()
        state.update(
            {
                "status": "signal_handler_startup_failed",
                "container_id": cid,
                "container_name": name,
                "docker_client_pid": solver.pid,
                "docker_client_exit_code": docker_code,
                "container": inspect_container(name),
                "startup_failure": failure_reason,
                "finished_utc": utc_now(),
            }
        )
        write_json(state_path, state)
        (run_dir / "worker.exit").write_text(f"{int(docker_code or 1)}\n", encoding="ascii")
        return int(docker_code or 1)
    write_json(run_dir / "signal-handler-verification.json", handlers)
    monitor_log = (run_dir / "checkpoint-monitor.stdout.log").open("ab", buffering=0)
    try:
        monitor = subprocess.Popen([str(ROOT / ".venv/bin/python"), str(run_dir / "checkpoint_monitor.py")], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=monitor_log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    finally:
        monitor_log.close()
    write_json(run_dir / "monitor-launch.json", {"pid": monitor.pid, "started_utc": utc_now(), "sha256": sha256(run_dir / "checkpoint_monitor.py")})
    started = time.monotonic()
    target_stop_at = started + NEW_WALL_S - 300
    next_sample = started + 600
    state.update({"status": "solver_running", "container_id": cid, "container_name": name, "docker_client_pid": solver.pid, "monitor_pid": monitor.pid, "solver_started_utc": utc_now(), "wall_cap_s": NEW_WALL_S})
    write_json(state_path, state)
    write_json(run_dir / "live.json", {"status": "running", "container_id": cid, "container_name": name, "start_time_s": read_json(run_dir / "case-declaration.json")["checkpoint"]["time_s"], "end_time_s": 5.0, "mpi_ranks": 16, "cpu_quota": 10, "disk_free_bytes": shutil.disk_usage(ROOT).free, "run_bundle_bytes": tree_size(run_dir), "started_utc": utc_now()})
    while solver.poll() is None:
        now = time.monotonic()
        if now >= target_stop_at:
            pids = solver_pids(name)
            signaled: list[int] = []
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGUSR2)
                    signaled.append(pid)
                except ProcessLookupError:
                    pass
            record({"status": "wall_budget_safe_stop_signal", "run_id": run_dir.name, "signal": 12, "solver_pids": pids, "signaled_pids": signaled, "margin_before_internal_timeout_s": 300})
            break
        if now >= next_sample:
            free = shutil.disk_usage(ROOT).free
            size = tree_size(run_dir)
            with (run_dir / "resource-samples.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"utc": utc_now(), "free_disk_bytes": free, "run_bundle_bytes": size, "container": inspect_container(name)}, sort_keys=True) + "\n")
            if free < MIN_FREE or size >= BASE_CAP:
                reason = f"disk/bundle guard: free_bytes={free}, bundle_bytes={size}"
                (run_dir / "checkpoint-guard-failure.txt").write_text(reason + "\n", encoding="utf-8")
                subprocess.run(["docker", "stop", "--time", "60", name], cwd=ROOT, capture_output=True, timeout=90, check=False)
                break
            next_sample = now + 600
        if monitor.poll() not in (None, 0):
            (run_dir / "checkpoint-guard-failure.txt").write_text(f"checkpoint monitor exited {monitor.returncode}\n", encoding="utf-8")
            subprocess.run(["docker", "stop", "--time", "60", name], cwd=ROOT, capture_output=True, timeout=90, check=False)
            break
        time.sleep(30)
    try:
        docker_code = solver.wait(timeout=120)
    except subprocess.TimeoutExpired:
        solver.kill()
        docker_code = solver.wait()
    if monitor.poll() is None:
        try:
            monitor_code = monitor.wait(timeout=900)
        except subprocess.TimeoutExpired:
            monitor.terminate()
            monitor_code = monitor.wait(timeout=15)
    else:
        monitor_code = int(monitor.returncode or 0)
    result = {"status": "finished", "finished_utc": utc_now(), "docker_client_exit_code": docker_code, "container": inspect_container(name), "monitor_exit_code": monitor_code, "wall_elapsed_s": round(time.monotonic() - started, 3), "last_solver_time_s": last_time(run_dir / "flow.log"), "stop_reason": (run_dir / "checkpoint-guard-failure.txt").read_text(encoding="utf-8").strip() if (run_dir / "checkpoint-guard-failure.txt").exists() else None}
    write_json(run_dir / "solver-result.json", result)
    state.update(result)
    write_json(state_path, state)
    return 0 if docker_code == 0 and monitor_code == 0 and result["stop_reason"] is None else 1


def last_time(log: Path) -> float | None:
    text = log.read_text(encoding="utf-8", errors="replace")
    times = re.findall(r"(?m)^Time\s*=\s*([0-9.eE+-]+)\s*$", text)
    return float(times[-1]) if times else None


def foam_dictionary_smoke(run_dir: Path) -> None:
    case = run_dir / "case"
    command = [
        "docker", "run", "--rm", "--cpus=0.25", "--memory=2g", "--memory-swap", "2g",
        "--user", f"{os.getuid()}:{os.getgid()}", "--mount", f"type=bind,src={case},dst=/case,readonly",
        "--workdir", "/case", "--entrypoint", "/bin/bash", IMAGE, "-lc",
        "source " + OPENFOAM_BASHRC + " >/dev/null 2>&1 && "
        "foamDictionary system/controlDict -entry timePrecision -value && "
        "foamDictionary system/controlDict -entry OptimisationSwitches/writeNowSignal -value && "
        "foamDictionary system/controlDict -entry OptimisationSwitches/stopAtWriteNowSignal -value && "
        "foamDictionary system/decomposeParDict -entry numberOfSubdomains -value",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=180, check=False)
    values = result.stdout.splitlines()
    if result.returncode or values != ["13", "10", "12", "16"]:
        raise RuntimeError(f"OpenFOAM dictionary smoke failed: rc={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}")
    write_json(run_dir / "preflight" / "foam-dictionary-signal-smoke.json", {"status": "pass", "values": values, "command": command})


def run_supervisor() -> int:
    if not PAIR.exists() or not BASE.exists():
        raise RuntimeError("expected resumed baseline and paired MULES bundle are missing")
    start = time.monotonic()
    last_sample = 0.0
    last_cpu_policy: str | None = None
    record({"status": "supervisor_started", "script_sha256": sha256(Path(__file__)), "baseline_container": BASE_NAME, "mules_container": PAIR_NAME, "shared_cpu_limit": 10, "baseline_starting_quota": 6, "pair_quota": 4, "disk_floor_bytes": MIN_FREE, "next_baseline_wall_deadline_utc": "2026-10-12T21:37:25Z"})
    while True:
        base = inspect_container(BASE_NAME)
        pair = inspect_container(PAIR_NAME)
        pair_active = pair_still_supervised(pair)
        base_active = bool(base and base["running"] and not base["paused"])
        if pair and not pair["running"] and not (PAIR / "terminal-ledger-summary.json").exists():
            try:
                audit_pair_terminal()
            except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
                failure = {"status": "mules_terminal_ledger_capture_failed", "error_type": type(error).__name__, "error": str(error)}
                write_json(PAIR / "terminal-ledger-summary.json", failure)
                record(failure)
        if pair_active and base_active:
            quota = base if base.get("nano_cpus") == 6_000_000_000 and base.get("cpu_shares") == 512 else set_cpu_quota(BASE_NAME, 6)
            if last_cpu_policy != "baseline6+mules4":
                record({"status": "cpu_policy_active", "baseline_quota": quota, "mules_quota": pair.get("nano_cpus", 0) / 1e9, "shared_quota": 10})
            last_cpu_policy = "baseline6+mules4"
        elif base_active:
            quota = base if base.get("nano_cpus") == 10_000_000_000 and base.get("cpu_shares") == 512 else set_cpu_quota(BASE_NAME, 10)
            if last_cpu_policy != "baseline10":
                record({"status": "mules_exited_baseline_quota_raised", "baseline_quota": quota, "mules_container": pair})
            last_cpu_policy = "baseline10"
        if time.monotonic() - last_sample >= 300:
            free = shutil.disk_usage(ROOT).free
            base_size = tree_size(BASE)
            pair_size = tree_size(PAIR)
            record({"status": "resource_sample", "free_disk_bytes": free, "baseline_bundle_bytes": base_size, "mules_bundle_bytes": pair_size, "baseline_container": base, "mules_container": pair})
            last_sample = time.monotonic()
            if free < MIN_FREE:
                stop_owned(f"disk floor crossed: {free} bytes available")
                return 4
            if base_size >= BASE_CAP or pair_size >= 3 * 1024**3:
                stop_owned(f"run bundle cap crossed: baseline={base_size}, mules={pair_size}")
                return 4
        if base and not base_active and not pair_active:
            break
        time.sleep(30)
    base = inspect_container(BASE_NAME)
    pair = inspect_container(PAIR_NAME)
    record({"status": "both_original_containers_exited", "baseline": base, "mules": pair, "elapsed_s": round(time.monotonic() - start, 1)})
    return continue_after_originals(base or {}, pair or {})


def continue_after_originals(base: dict[str, Any], pair: dict[str, Any]) -> int:
    if base.get("exit_code") == 0 and last_time(BASE / "flow.log") >= 4.999:
        record({"status": "target_reached_by_original_baseline", "baseline": base, "last_solver_time_s": last_time(BASE / "flow.log")})
        return 0
    if base.get("oom_killed") or (BASE / "checkpoint-guard-failure.txt").exists():
        raise RuntimeError("original baseline ended from OOM or checkpoint/resource guard; refusing automatic continuation")
    log_text = (BASE / "flow.log").read_text(encoding="utf-8", errors="replace")
    solver_stage = re.findall(r"(?m)^ROUAIX_STAGE_EXIT stage=solver code=(-?\d+)\s*$", log_text)
    expected_timeout = base.get("exit_code") == 124 or (solver_stage and int(solver_stage[-1]) == 124)
    if not expected_timeout:
        raise RuntimeError(f"original baseline did not end at target or declared 12 h wall timeout: {base}, solver_stage={solver_stage[-1:]}")
    required_free = MIN_FREE + PREPARE_HEADROOM
    waiting_started = utc_now()
    while True:
        free = shutil.disk_usage(ROOT).free
        if free >= required_free:
            record({"status": "disk_headroom_available_for_restart", "free_disk_bytes": free, "required_free_disk_bytes": required_free, "wait_started_utc": waiting_started})
            break
        record({"status": "waiting_for_reviewed_storage_headroom", "free_disk_bytes": free, "minimum_floor_bytes": MIN_FREE, "required_prepare_headroom_bytes": PREPARE_HEADROOM, "required_free_disk_bytes": required_free, "no_case_copy_or_CFD_launch": True})
        time.sleep(300)
    time_name, field_validation = latest_complete_checkpoint(BASE / "case")
    declared_start = float(read_json(BASE / "case-declaration.json")["checkpoint"]["time_s"])
    if float(time_name) <= declared_start + 1e-10:
        audit_report_path = BASE / "preflight/parent-checkpoint-audit/ledger-report.json"
        report = read_json(audit_report_path)
        guard = report["continuation_guard_0p1_percent"]
        if abs(float(report["actual_final_time_s"]) - declared_start) > 1e-10 or not guard["incremental_pass"] or not guard["cumulative_pass"]:
            raise RuntimeError("preserved initial checkpoint audit is absent, mismatched, or failed")
        record({"status": "terminal_checkpoint_fallback_to_preserved_initial", "checkpoint_time_s": declared_start, "audit_report": str(audit_report_path.relative_to(ROOT)), "reason": "no newer complete checkpoint was written before the old wall timeout"})
    else:
        audit_out = BASE / "resume-chain" / f"terminal-audit-{time_name}"
        audit_report_path = audit_out / "ledger-report.json"
        if audit_report_path.is_file():
            report = read_json(audit_report_path)
            guard = report["continuation_guard_0p1_percent"]
            if abs(float(report["actual_final_time_s"]) - float(time_name)) > 1e-10 or not guard["incremental_pass"] or not guard["cumulative_pass"]:
                raise RuntimeError("preserved terminal checkpoint audit is mismatched or failed")
            record({"status": "terminal_checkpoint_audit_reused", "checkpoint_time_s": float(time_name), "ledger_report": str(audit_report_path.relative_to(ROOT))})
        else:
            audit_out.mkdir(parents=True, exist_ok=False)
            report = audit_parent(BASE / "case", BASE / "case-declaration.json", time_name, audit_out)
    record({"status": "terminal_checkpoint_audit_pass", "checkpoint_time_s": float(time_name), "ledger_report": str(audit_report_path.relative_to(ROOT)), "field_validation": field_validation, "incremental_guard": report["continuation_guard_0p1_percent"]["incremental_pass"], "cumulative_guard": report["continuation_guard_0p1_percent"]["cumulative_pass"]})
    run_dir = create_continuation(time_name, report, audit_report_path)
    foam_dictionary_smoke(run_dir)
    record({"status": "continuation_prepared", "run_dir": str(run_dir.relative_to(ROOT)), "checkpoint_time_s": float(time_name), "target_s": 5.0, "ranks": 16, "cpu_quota": 10, "memory_gib": 48, "wall_budget_s": NEW_WALL_S, "bundle_bytes": tree_size(run_dir), "disk_free_bytes": shutil.disk_usage(ROOT).free})
    worker_command = [
        str(ROOT / ".venv/bin/python"),
        str(ROOT / "scripts/run_local.py"),
        "--threads",
        "1",
        "--",
        str(ROOT / ".venv/bin/python"),
        str(Path(__file__).resolve()),
        "--worker",
        str(run_dir),
    ]
    worker = subprocess.Popen(
        worker_command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=(run_dir / "worker.log").open("ab", buffering=0),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    record({"status": "continuation_worker_detached", "run_dir": str(run_dir.relative_to(ROOT)), "pid": worker.pid, "worker_command": worker_command, "worker_thread_limit": 1, "container_cpu_quota": 10, "shared_job_count": 1})
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--supervise":
        return run_supervisor()
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        return launch_worker(Path(sys.argv[2]).resolve())
    print(f"usage: {Path(sys.argv[0]).name} --supervise | --worker RUN_DIRECTORY", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        record({"status": "supervisor_failure", "error_type": type(error).__name__, "error": str(error)})
        raise
