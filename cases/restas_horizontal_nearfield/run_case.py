#!/usr/bin/env python3
"""Prepare and run one exploratory horizontal Restas near-field VOF case."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CASE_DIR = Path(__file__).resolve().parent
ROOT = CASE_DIR.parents[1]
sys.path.insert(0, str(CASE_DIR))
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_case  # noqa: E402
import run_restas_pilot as pilot  # noqa: E402

IMAGE = "opencfd/openfoam-default:2512"
WALL_TIMEOUT_S = 900.0
SOURCE_INPUTS = (
    CASE_DIR / "README.md",
    CASE_DIR / "prepare_case.py",
    CASE_DIR / "run_case.py",
    ROOT / "track2_aerial_drop_experiment_plan.md",
    ROOT / "docs" / "REFERENCES.md",
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf",
    ROOT / "Examining_the_Effectiveness_of_Aerial_Firefighting.pdf",
    ROOT / "scripts" / "run_local.py",
    ROOT / "scripts" / "run_restas_pilot.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _solver_summary(log_text: str) -> dict[str, Any]:
    times = [
        float(match.group(1))
        for match in re.finditer(r"^Time =\s*([0-9.eE+-]+)\s*$", log_text, re.M)
    ]
    courant = [
        float(match.group(1))
        for match in re.finditer(
            r"^Courant Number mean:\s*[-+0-9.eE]+\s+max:\s*([-+0-9.eE]+)", log_text, re.M
        )
    ]
    alpha_courant = [
        float(match.group(1))
        for match in re.finditer(
            r"^Interface Courant Number mean:\s*[-+0-9.eE]+\s+max:\s*([-+0-9.eE]+)", log_text, re.M
        )
    ]
    phase_fraction = [
        float(match.group(1))
        for match in re.finditer(r"^Phase-1 volume fraction =\s*([-+0-9.eE]+)", log_text, re.M)
    ]
    execution = [
        (float(match.group(1)), float(match.group(2)))
        for match in re.finditer(
            r"^ExecutionTime =\s*([-+0-9.eE]+) s\s+ClockTime =\s*([-+0-9.eE]+) s", log_text, re.M
        )
    ]
    return {
        "positive_time_records": len({value for value in times if value > 0}),
        "last_solver_time_s": max(times) if times else None,
        "max_courant_number": max(courant) if courant else None,
        "max_interface_courant_number": max(alpha_courant) if alpha_courant else None,
        "last_phase1_volume_fraction": phase_fraction[-1] if phase_fraction else None,
        "final_execution_time_s": execution[-1][0] if execution else None,
        "final_reported_clock_time_s": execution[-1][1] if execution else None,
    }


def _resource_snapshot() -> dict[str, Any]:
    mem_available_gib = None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                mem_available_gib = int(line.split()[1]) * 1024 / 1024**3
                break
    except (OSError, ValueError):
        pass
    process_result = subprocess.run(
        ["ps", "-eo", "pid=,pcpu=,rss=,args="], capture_output=True, text=True, check=False
    )
    active_solver_processes = []
    if process_result.returncode == 0:
        for line in process_result.stdout.splitlines():
            if "interIsoFoam" not in line and "foamRun" not in line:
                continue
            columns = line.split(maxsplit=3)
            if len(columns) == 4:
                active_solver_processes.append(
                    {
                        "pid": int(columns[0]),
                        "cpu_percent": float(columns[1]),
                        "rss_kib": int(columns[2]),
                        "command": columns[3],
                    }
                )
    containers_result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=False
    )
    active_project_containers = (
        [name for name in containers_result.stdout.splitlines() if name.startswith("restas-")]
        if containers_result.returncode == 0
        else []
    )
    gpu_summary = None
    gpu_result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if gpu_result.returncode == 0:
        gpu_summary = gpu_result.stdout.strip()
    return {
        "effective_cpu_count": pilot.effective_cpu_count(),
        "available_memory_gib": mem_available_gib,
        "free_disk_gib": shutil.disk_usage(ROOT).free / 1024**3,
        "gpu_utilization_and_memory": gpu_summary,
        "active_solver_processes": active_solver_processes,
        "active_project_containers": active_project_containers,
        "snapshot_utc": datetime.now(UTC).isoformat(),
    }


def run_case(
    model: str,
    spacing_m: float,
    end_time_s: float,
    ranks: int,
    memory_gib: int,
) -> int:
    if not 1 <= ranks <= 18:
        raise ValueError("rank count must be from 1 through 18 on this 20-CPU host")
    if not 4 <= memory_gib <= 112:
        raise ValueError("memory limit must be from 4 through 112 GiB on this 125 GiB host")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"restas-hnf-{model.replace('-', '')}-{stamp}-{uuid.uuid4().hex[:6]}"
    run_dir = ROOT / "results" / "runs" / run_id
    case_path = run_dir / "case"
    run_dir.mkdir(parents=True, exist_ok=False)
    inputs = prepare_case.prepare_case(case_path, model, ranks, spacing_m, end_time_s)
    input_path = run_dir / "inputs.json"
    input_path.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    git_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=False, capture_output=True, text=True
    ).stdout
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_utc": datetime.now(UTC).isoformat(),
        "git_revision": pilot._git_revision(),
        "git_worktree_dirty": bool(git_status.strip()),
        "source_sha256": {str(path.relative_to(ROOT)): _sha256(path) for path in SOURCE_INPUTS},
        "inputs_sha256": _sha256(input_path),
        "prepared_case_file_sha256": {
            str(path.relative_to(case_path)): _sha256(path)
            for path in sorted(case_path.rglob("*"))
            if path.is_file()
        },
        "solver_image": IMAGE,
        "solver_image_id": pilot._docker_image_id(),
        "execution": {
            "mpi_ranks": ranks,
            "docker_cpu_limit": ranks + 2,
            "docker_memory_limit_gib": memory_gib,
            "wall_time_limit_s": WALL_TIMEOUT_S,
            "command": "blockMesh; checkMesh -allTopology -allGeometry; decomposePar -force; mpirun interIsoFoam -parallel; reconstructPar -latestTime",
            "launch_wrapper": f".venv/bin/python scripts/run_local.py --threads {ranks} -- .venv/bin/python cases/restas_horizontal_nearfield/run_case.py ...",
            "time_step_controls": {
                "adaptive": True,
                "initial_delta_t_s": inputs["time"]["initial_delta_t_s"],
                "max_delta_t_s": inputs["time"]["max_delta_t_s"],
                "max_Co": 0.3,
                "max_alpha_Co": 0.15,
            },
        },
        "resource_preflight": _resource_snapshot(),
        "scope": "exploratory horizontal-source near-field CPU VOF only; no validation claim",
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Run directory: {run_dir}", flush=True)
    print(
        f"Model: {model}; mesh: {inputs['mesh_cells_expected']:,} cells; horizon: {end_time_s:g} s; ranks: {ranks}",
        flush=True,
    )
    start = time.monotonic()
    return_code, samples, stop_reason, stop_confirmed, stop_error, monitor_errors = (
        pilot._run_container(
            case_path,
            run_dir,
            run_id,
            ranks,
            memory_gib,
            courant_limits=(0.3, 0.15),
            wall_timeout_s=WALL_TIMEOUT_S,
        )
    )
    finished = datetime.now(UTC).isoformat()
    log_path = run_dir / "openfoam-console.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    stage_records = pilot._case_stage_exit_records(log_path)
    manifest.update(
        {
            "finished_utc": finished,
            "wall_time_s": time.monotonic() - start,
            "exit_code": return_code,
            "case_stage_exit_records": stage_records,
            "stop_reason": stop_reason,
            "stop_confirmed": stop_confirmed,
            "stop_error": stop_error,
            "resource_monitor_errors": monitor_errors,
            "docker_resource_samples": samples,
            "resource_sample_note": "Docker stats sampled about every 2 seconds; brief peaks between samples can be higher.",
            "solver_log_summary": _solver_summary(log_text),
            "case_file_sha256_after_run": {
                str(path.relative_to(case_path)): _sha256(path)
                for path in sorted(case_path.rglob("*"))
                if path.is_file()
                and path.relative_to(case_path).parts[0] in {"0", "constant", "system"}
            },
            "output_tree_bytes": _tree_bytes(run_dir),
            "exit_scope": "The solver completion and numerical diagnostics describe this exploratory run only.",
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Run status: exit={return_code}; wall={manifest['wall_time_s']:.2f} s; output={_tree_bytes(run_dir) / 1024**2:.1f} MiB",
        flush=True,
    )
    print(f"Console log: {log_path}", flush=True)
    print(f"Manifest: {manifest_path}", flush=True)
    return return_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", choices=("laminar", "standard-ke", "realizable-ke", "k-omega-sst"), required=True
    )
    parser.add_argument("--spacing", type=float, choices=(0.025, 0.05), default=0.025)
    parser.add_argument("--end-time", type=float, default=0.02)
    parser.add_argument("--ranks", type=int, default=18)
    parser.add_argument("--memory-gib", type=int, default=96)
    options = parser.parse_args()
    try:
        return run_case(
            options.model, options.spacing, options.end_time, options.ranks, options.memory_gib
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
