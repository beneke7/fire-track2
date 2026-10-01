#!/usr/bin/env python3
"""Continue a preserved, interrupted horizontal near-field CPU VOF run.

The parent run is never modified. Its decomposed 20 ms checkpoint is copied to
a new run directory, then OpenFOAM resumes from that exact saved time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cases/restas_amr_probe"))
import run_hnf_mesh_case as hnf  # noqa: E402

IMAGE = hnf.IMAGE
CHECKPOINT = "0.020000"
CHECKPOINT_S = 0.02
TARGET_S = 0.1
REQUIRED_FIELDS = ("alpha.water", "U", "p_rgh", "k", "nut")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_time(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def set_restart_time(control_path: Path) -> None:
    text = control_path.read_text(encoding="utf-8")
    replacements = (
        (r"(?m)^startFrom\s+[^;]+;", "startFrom startTime;"),
        (r"(?m)^startTime\s+[^;]+;", f"startTime {CHECKPOINT_S:g};"),
        (r"(?m)^stopAt\s+[^;]+;", "stopAt endTime;"),
        (r"(?m)^endTime\s+[^;]+;", f"endTime {TARGET_S:g};"),
    )
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"expected one controlDict entry matching {pattern!r}")
    control_path.write_text(text, encoding="utf-8")


def validate_parent(parent: Path) -> tuple[dict[str, Any], dict[str, Any], list[Path]]:
    manifest_path = parent / "manifest.json"
    inputs_path = parent / "inputs.json"
    case = parent / "case"
    if not manifest_path.is_file() or not inputs_path.is_file() or not case.is_dir():
        raise RuntimeError(f"parent run is missing manifest, inputs, or case: {parent}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    if manifest.get("exit_code") == 0 or manifest.get("finished_utc"):
        if manifest.get("exit_code") == 0:
            raise RuntimeError("refusing to resume a completed parent run")
    if manifest.get("solver_image") != IMAGE:
        raise RuntimeError("parent solver image differs from the continuation image")
    if inputs.get("time", {}).get("end_s") != TARGET_S:
        raise RuntimeError(f"expected original target horizon {TARGET_S:g} s")
    if inputs.get("variant") != "uniform":
        raise RuntimeError("this continuation path is restricted to uniform fixed meshes")
    processors = sorted(
        (path for path in case.glob("processor[0-9]*") if path.is_dir()),
        key=lambda path: int(path.name.removeprefix("processor")),
    )
    ranks = manifest.get("execution", {}).get("mpi_ranks")
    if not processors or len(processors) != ranks:
        raise RuntimeError(f"expected {ranks} processor directories, found {len(processors)}")
    checkpoint_files: list[Path] = []
    for proc in processors:
        checkpoint = proc / CHECKPOINT
        if not checkpoint.is_dir():
            raise RuntimeError(f"missing checkpoint directory: {checkpoint}")
        missing = [name for name in REQUIRED_FIELDS if not (checkpoint / name).is_file()]
        if inputs.get("model") == "standard-ke" and not (checkpoint / "epsilon").is_file():
            missing.append("epsilon")
        if inputs.get("model") == "realizable-ke" and not (checkpoint / "epsilon").is_file():
            missing.append("epsilon")
        if inputs.get("model") == "k-omega-sst" and not (checkpoint / "omega").is_file():
            missing.append("omega")
        if missing:
            raise RuntimeError(f"{proc.name} checkpoint missing fields: {', '.join(missing)}")
        checkpoint_files.extend(path for path in checkpoint.iterdir() if path.is_file())
    if len(processors) != 10:
        raise RuntimeError("the saved processor layout expects exactly 10 MPI ranks")
    if not (case / "system/controlDict").is_file():
        raise RuntimeError("parent case has no system/controlDict")
    return manifest, inputs, checkpoint_files


def file_hashes(paths: list[Path], base: Path) -> dict[str, dict[str, Any]]:
    return {
        str(path.relative_to(base)): {"bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(paths)
    }


def run_continuation(args: argparse.Namespace) -> int:
    parent = args.parent.resolve()
    run_dir = ROOT / "results/runs" / args.run_id
    if run_dir.exists():
        raise RuntimeError(f"run directory already exists; refusing to overwrite: {run_dir}")
    parent_manifest, inputs, parent_checkpoint_files = validate_parent(parent)
    parent_manifest_path = parent / "manifest.json"
    source_hashes = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in (
            Path(__file__).resolve(),
            Path(hnf.__file__).resolve(),
            ROOT / "scripts/run_local.py",
        )
    }
    image_id = subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    case = run_dir / "case"
    started_utc = datetime.now(UTC).isoformat()
    manifest: dict[str, Any] = {
        "run_id": args.run_id,
        "started_utc": started_utc,
        "finished_utc": None,
        "git_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "git_worktree_dirty": bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        ),
        "case_classification": "Exploratory continuation of a provisional horizontal four-slot near-field CPU VOF case; not validation.",
        "solver_image": IMAGE,
        "solver_image_id": image_id,
        "model": inputs.get("model"),
        "variant": "uniform",
        "stage": "pulse100ms-resumed-from-20ms",
        "resume_parent_run_id": parent.name,
        "resume_parent_manifest_sha256": sha256(parent_manifest_path),
        "resume_parent_exit_code": parent_manifest.get("exit_code"),
        "resume_parent_last_solver_time_s": parent_manifest.get("solver_log_summary", {}).get(
            "last_time_s"
        ),
        "restart_checkpoint_time_s": CHECKPOINT_S,
        "restart_checkpoint_sha256": file_hashes(parent_checkpoint_files, parent / "case"),
        "resume_reason": "Continue the user-stopped 100 ms turbulence comparison from the last complete 10-rank checkpoint; the parent attempt remains preserved.",
        "inputs_sha256": sha256(parent / "inputs.json"),
        "source_sha256": source_hashes,
        "execution": {
            "mpi_ranks": args.ranks,
            "docker_cpu_limit": args.docker_cpus,
            "docker_memory_limit_gib": args.memory_gib,
            "wall_timeout_s": args.timeout_s,
            "commands": [
                "copy preserved parent case into a new run directory",
                f"startFrom startTime; startTime {CHECKPOINT_S:g}; endTime {TARGET_S:g}",
                f"mpirun -np {args.ranks} interIsoFoam -parallel",
                "reconstructParMesh -constant",
                "reconstructPar -fields '(alpha.water)'",
            ],
        },
        "inputs": inputs,
        "parent_solver_summary": parent_manifest.get("solver_log_summary", {}),
    }
    run_dir.mkdir(parents=True)
    (run_dir / "inputs.json").write_bytes((parent / "inputs.json").read_bytes())
    shutil.copy2(parent_manifest_path, run_dir / "resume_parent_manifest.json")
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    try:
        shutil.copytree(parent / "case", case, copy_function=shutil.copy2)
        set_restart_time(case / "system/controlDict")
        # Hash the copied checkpoint too, confirming the clone matches its parent.
        cloned_checkpoint_files = [
            path
            for proc in sorted(case.glob("processor[0-9]*"))
            for path in (proc / CHECKPOINT).iterdir()
            if path.is_file()
        ]
        cloned_hashes = file_hashes(cloned_checkpoint_files, case)
        if cloned_hashes != manifest["restart_checkpoint_sha256"]:
            raise RuntimeError("cloned checkpoint hash does not match the preserved parent")
        manifest["copied_checkpoint_verified"] = True
        manifest["copied_controlDict_sha256"] = sha256(case / "system/controlDict")
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except Exception as error:
        manifest.update(
            {
                "finished_utc": datetime.now(UTC).isoformat(),
                "exit_code": 1,
                "setup_error": repr(error),
            }
        )
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        raise

    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "parent": parent.name,
                "model": inputs.get("model"),
                "checkpoint_s": CHECKPOINT_S,
                "target_s": TARGET_S,
                "case_copy_bytes": sum(p.stat().st_size for p in case.rglob("*") if p.is_file()),
                "run_dir": str(run_dir.relative_to(ROOT)),
                "state": "launching solver",
            }
        ),
        flush=True,
    )

    container_name = args.run_id[:63]
    docker_args = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        f"--cpus={args.docker_cpus}",
        f"--memory={args.memory_gib}g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={case.resolve()},dst=/case",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        IMAGE,
        "-lc",
    ]
    shell = f"""source /usr/lib/openfoam/openfoam2512/etc/bashrc
set -euo pipefail
printf 'HNFM_RESUME checkpoint={CHECKPOINT} target=0.100000 model={inputs.get("model")} ranks={args.ranks}\\n'
run_stage() {{ local stage="$1"; shift; set +e; "$@"; local status=$?; set -e; printf 'HNFM_STAGE_EXIT stage=%s code=%s\\n' "$stage" "$status"; return "$status"; }}
run_stage interIsoFoam mpirun -np {args.ranks} interIsoFoam -parallel
run_stage reconstructParMesh reconstructParMesh -constant
run_stage reconstructPar reconstructPar -fields '(alpha.water)'
"""
    samples: list[dict[str, Any]] = []
    started = time.monotonic()
    log_path = run_dir / "openfoam-console.log"
    timed_out = False
    with log_path.open("wb") as log_stream:
        proc = subprocess.Popen([*docker_args, shell], stdout=log_stream, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            sample: dict[str, Any] = {"elapsed_s": round(time.monotonic() - started, 3)}
            stat = subprocess.run(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.CPUPerc}}|{{.MemUsage}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if stat.returncode == 0 and stat.stdout.strip():
                cpu, memory = stat.stdout.strip().split("|", 1)
                sample.update({"cpu_percent": cpu, "memory_usage_and_limit": memory})
            samples.append(sample)
            if time.monotonic() - started > args.timeout_s:
                timed_out = True
                subprocess.run(
                    ["docker", "stop", container_name], capture_output=True, timeout=30, check=False
                )
                break
            time.sleep(2)
        exit_code = proc.wait()
    wall = time.monotonic() - started
    log = log_path.read_text(encoding="utf-8", errors="replace")
    cpu = [float(sample.get("cpu_percent", "0%").rstrip("%")) for sample in samples]
    ram_gib: list[float] = []
    for sample in samples:
        match = re.match(r"([0-9.]+)\s*(B|KiB|MiB|GiB)", sample.get("memory_usage_and_limit", ""))
        if match:
            scale = {"B": 2**-30, "KiB": 2**-20, "MiB": 2**-10, "GiB": 1.0}[match.group(2)]
            ram_gib.append(float(match.group(1)) * scale)
    stage_records = [
        {"stage": stage, "exit_code": int(code)}
        for stage, code in re.findall(
            r"^HNFM_STAGE_EXIT stage=([A-Za-z0-9_]+) code=(\d+)$", log, re.M
        )
    ]
    summary = hnf.parse_solver_log(log)
    success = (
        exit_code == 0
        and not timed_out
        and not any(record["exit_code"] for record in stage_records)
        and summary.get("last_time_s", 0.0) >= TARGET_S
    )
    manifest.update(
        {
            "finished_utc": datetime.now(UTC).isoformat(),
            "exit_code": 0 if success else (exit_code or 1),
            "timed_out": timed_out,
            "wall_time_s": wall,
            "stage_exit_records": stage_records,
            "solver_log_summary": summary,
            "docker_resource_samples": samples,
            "peak_sampled_cpu_percent": max(cpu, default=None),
            "peak_sampled_memory_gib": max(ram_gib, default=None),
            "resource_sample_note": "Docker stats sampled approximately every two seconds; sub-interval peaks may be higher.",
            "output_tree_bytes": sum(
                path.stat().st_size for path in run_dir.rglob("*") if path.is_file()
            ),
            "run_sha256": {
                str(path.relative_to(run_dir)): sha256(path)
                for path in sorted(run_dir.rglob("*"))
                if path.is_file() and path.name != "manifest.json"
            },
        }
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "model": inputs.get("model"),
                "exit_code": manifest["exit_code"],
                "timed_out": timed_out,
                "wall_time_s": wall,
                "solver": summary,
                "peak_ram_gib": max(ram_gib, default=None),
                "run_dir": str(run_dir.relative_to(ROOT)),
            },
            indent=2,
        ),
        flush=True,
    )
    return int(manifest["exit_code"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ranks", type=int, default=10)
    parser.add_argument("--docker-cpus", type=int, default=10)
    parser.add_argument("--memory-gib", type=int, default=32)
    parser.add_argument("--timeout-s", type=int, default=43_200)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,120}", args.run_id):
        parser.error("run ID must be 8–120 letters, digits, underscores, or hyphens")
    if args.ranks != 10 or args.docker_cpus < args.ranks or args.docker_cpus > 20:
        parser.error("this saved decomposition requires 10 ranks and a CPU cap from 10 to 20")
    if args.memory_gib < 4 or args.memory_gib > 112:
        parser.error("memory cap must be 4..112 GiB")
    if args.timeout_s <= 0:
        parser.error("timeout must be positive")
    return run_continuation(args)


if __name__ == "__main__":
    raise SystemExit(main())
