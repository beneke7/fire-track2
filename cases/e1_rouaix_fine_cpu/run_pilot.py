#!/usr/bin/env python3
"""Clean-start bounded resource pilot of Goblin's previously checked fine mesh."""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import math
import os
import re
import selectors
import shutil
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "results/runs/rouaix-static-mesh-quality-full-20261020T1949Z"
IMAGE = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
FOAMRC = "/usr/lib/openfoam/openfoam2512/etc/bashrc"
SOLVER_SHELL = (
    "interIsoFoam -help && mpirun --bind-to none -mca mpi_yield_when_idle 1 "
    "-np 20 interIsoFoam -parallel"
)
PATCHES = (
    "gasInlet",
    "downstreamOutlet",
    "bottomOutlet",
    "aircraftWall",
    "spanwiseMinus",
    "spanwisePlus",
    "nozzle",
)


def write_json(path: Path, value: object) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temp.replace(path)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_entry(text: str, key: str, value: str) -> str:
    result, count = re.subn(rf"(?m)^(\s*{key}\s+)\S+(\s*;)", rf"\g<1>{value}\2", text, count=1)
    if count != 1:
        raise ValueError(f"expected one top-level {key} entry")
    return result


def integrate_sample(current, previous, sample, injected, net_external):
    """Integrate complete native per-step fluxes; never bridge missing steps."""
    flux = sample.get("alpha_phi", {})
    if set(flux) != set(PATCHES) or "inventory_m3" not in sample:
        raise ValueError("incomplete native water ledger sample")
    dt = current - previous
    values = [current, previous, sample["inventory_m3"], *flux.values()]
    if dt <= 0 or not all(math.isfinite(value) for value in values):
        raise ValueError("nonfinite or nonadvancing native water ledger sample")
    injected += -flux["nozzle"] * dt
    net_external += sum(flux[p] for p in PATCHES if p != "nozzle") * dt
    sample.update(
        time_s=current,
        injected_m3=injected,
        residual_m3=sample["inventory_m3"] + net_external - injected,
    )
    return injected, net_external


def docker(case: Path, name: str, shell: str) -> list[str]:
    cmd = [
        "docker",
        "run",
        "--name",
        name,
        "--cpus=20",
        "--memory=88g",
        "--memory-swap=88g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
    ]
    for var in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        cmd += ["--env", f"{var}=1"]
    return cmd + [
        "--mount",
        f"type=bind,src={case},dst=/case",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        IMAGE,
        "-c",
        f"set +e +u; source {FOAMRC} >/dev/null 2>&1; setup=$?; "
        'set -euo pipefail; [ "$setup" -eq 0 ] || exit "$setup"; ' + shell,
    ]


def stop(name: str, hard: bool = False) -> None:
    if hard:
        subprocess.run(
            ["docker", "stop", "-t", "30", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(
            ["docker", "exec", name, "bash", "-c", "pkill -USR2 -x interIsoFoam"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--resume-prepared", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"rouaix-fine-[A-Za-z0-9._-]{1,50}", args.run_id):
        parser.error("run ID must begin rouaix-fine- and use simple filename characters")
    run = ROOT / "results/runs" / args.run_id
    case = run / "case"
    name = args.run_id
    atexit.register(stop, name, hard=True)
    atexit.register(stop, name + "-decompose", hard=True)

    def terminate(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    if args.resume_prepared:
        state = json.loads((run / "run-state.json").read_text())
        with (run / "supervisor-transitions.jsonl").open("a") as transitions:
            transitions.write(json.dumps(state) + "\n")
        result = subprocess.run(
            [
                "docker",
                "inspect",
                name + "-decompose",
                "--format",
                "{{.State.ExitCode}} {{.State.Running}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip() != "0 false":
            raise RuntimeError("decomposition did not complete successfully")
        for rank in range(20):
            if not (case / f"processor{rank}/constant/polyMesh/boundary").is_file():
                raise RuntimeError(f"missing decomposed mesh on rank {rank}")
        state.setdefault("resumed_prepared_utc", datetime.now(UTC).isoformat())
    else:
        run.mkdir()  # Never overwrite an attempt.
        state = {
            "started_utc": datetime.now(UTC).isoformat(),
            "status": "preparing",
            "run_id": args.run_id,
            "ranks": 20,
            "container_memory_limit_gib": 88,
            "horizon_s": 0.002,
            "dt_s": 0.0001,
            "stop_reason": None,
        }
        write_json(run / "run-state.json", state)
        validation = json.loads((SOURCE / "mesh-validation.json").read_text())
        if validation["status"] != "static_mesh_passed_checks_no_cfd_launched":
            raise ValueError("source mesh lacks its successful all-topology/all-geometry record")
        if validation["expected_cells"] != 35_190_080:
            raise ValueError("source mesh is not the declared 35.19M arm")
        if shutil.disk_usage(run).free < 70 * 1024**3:
            raise RuntimeError("less than 70 GiB disk before preparation")
        case = run / "case"
        for directory in ("0", "constant", "system"):
            shutil.copytree(SOURCE / "candidate/case" / directory, case / directory)
        for filename in ("mesh-validation.json", "prepared-inputs.json", "source-nozzle.json"):
            shutil.copy2(SOURCE / filename, run / ("source-" + filename))
        shutil.copy2(Path(__file__), run / "run_pilot.py")
        shutil.copy2(ROOT / "experiments/E1_ROUAIX_FINE_CPU.md", run / "experiment.md")
        control = case / "system/controlDict"
        text = control.read_text()
        for key, value in (
            ("application", "interIsoFoam"),
            ("startFrom", "startTime"),
            ("startTime", "0"),
            ("endTime", "0.002"),
            ("deltaT", "0.0001"),
            ("maxDeltaT", "0.0001"),
            ("writeInterval", "0.001"),
            ("writeFormat", "binary"),
            ("writeCompression", "off"),
            ("timePrecision", "12"),
        ):
            text = replace_entry(text, key, value)
        control.write_text(text)
        decompose = case / "system/decomposeParDict"
        decompose.write_text(replace_entry(decompose.read_text(), "numberOfSubdomains", "20"))
        hashes = {
            str(p.relative_to(case)): sha(p)
            for directory in ("0", "system", "constant")
            for p in sorted((case / directory).rglob("*"))
            if p.is_file() and "polyMesh" not in p.parts
        }
        hashes["constant/polyMesh/boundary"] = sha(case / "constant/polyMesh/boundary")
        hashes["constant/polyMesh/points"] = sha(case / "constant/polyMesh/points")
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        write_json(
            run / "input-manifest.json",
            {
                "revision": revision,
                "dirty": bool(dirty),
                "status_porcelain": dirty.splitlines(),
                "input_sha256": hashes,
                "pinned_image": IMAGE,
                "source_mesh": str(SOURCE.relative_to(ROOT)),
            },
        )
        name = args.run_id
        state.update(status="decomposing", container=name + "-decompose")
        write_json(run / "run-state.json", state)
        with (run / "decompose.log").open("wb") as log:
            result = subprocess.run(
                docker(case, name + "-decompose", "decomposePar -force"),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=1200,
            )
        if result.returncode:
            state.update(status="failed_decomposition", exit_code=result.returncode)
            write_json(run / "run-state.json", state)
            return result.returncode
    # A running unrelated CFD container retains its CPU allocation even during
    # short quiet intervals; do not infer capacity from a single idle sample.
    wait_start = datetime.fromisoformat(
        state.get("resumed_prepared_utc", datetime.now(UTC).isoformat())
    )
    deadline = wait_start.timestamp() + 1200
    state.update(status="waiting_for_full_cpu_capacity")
    write_json(run / "run-state.json", state)
    while True:
        active = []
        ids = subprocess.check_output(["docker", "ps", "-q"], text=True).split()
        if ids:
            rows = json.loads(subprocess.check_output(["docker", "inspect", *ids], text=True))
            active = [r["Name"] for r in rows if r["State"]["Running"] and not r["State"]["Paused"]]
        before = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
        time.sleep(2)
        after = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
        delta = [b - a for a, b in zip(before, after, strict=True)]
        busy = 20 * (1 - (delta[3] + delta[4]) / sum(delta))
        state.update(unrelated_running_containers=active, sampled_busy_cpu_equivalents=busy)
        write_json(run / "run-state.json", state)
        if (run / "PAUSE").exists() or (ROOT / "results/runs/PAUSE").exists():
            state.update(status="prepared_paused", stop_reason="user pause marker")
            write_json(run / "run-state.json", state)
            return 0
        if time.time() >= deadline:
            state.update(
                status="prepared_capacity_deferred", stop_reason="20-minute capacity wait expired"
            )
            write_json(run / "run-state.json", state)
            return 0
        if not active and busy < 1:
            break
        time.sleep(8)
    cmd = docker(case, name, SOLVER_SHELL)
    state.update(status="running", container=name, solver_command=cmd)
    start = time.monotonic()
    last_progress = start
    requested_stop = None
    current = None
    previous = 0.0
    injected = 0.0
    net_external = 0.0
    max_u = 0.0
    sample = {}
    samples = 0
    last_state_write = start
    selector = selectors.DefaultSelector()
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    assert process.stdout is not None
    selector.register(process.stdout, selectors.EVENT_READ)
    write_json(run / "run-state.json", state)
    with (run / "flow.log").open("w") as log, (run / "observations.jsonl").open("w") as obs:
        while process.poll() is None or selector.get_map():
            now = time.monotonic()
            reason = None
            if (run / "PAUSE").exists() or (ROOT / "results/runs/PAUSE").exists():
                reason = "user pause marker"
            elif now - start > 2400:
                reason = "40-minute solver wall budget; reserve 5 minutes for checkpoint"
            elif now - last_progress > 600:
                reason = "no printed time progress for 600 s"
            elif shutil.disk_usage(run).free < 30 * 1024**3:
                reason = "free disk below 30 GiB"
            if reason and requested_stop is None:
                state["stop_reason"] = reason
                requested_stop = now
                stop(name)
            if requested_stop is not None and now - requested_stop > 300:
                stop(name, hard=True)
            if now - last_state_write > 30:
                state.update(elapsed_s=now - start, time_s=current, max_u_seen_m_s=max_u)
                write_json(run / "run-state.json", state)
                last_state_write = now
            events = selector.select(timeout=1)
            for key, _ in events:
                line = key.fileobj.readline()
                if not line:
                    selector.unregister(key.fileobj)
                    continue
                log.write(line)
                log.flush()
                m = re.match(r"^Time = (\S+)", line)
                if m:
                    if current is not None:
                        injected, net_external = integrate_sample(
                            current, previous, sample, injected, net_external
                        )
                        previous = current
                        obs.write(json.dumps(sample) + "\n")
                        obs.flush()
                        samples += 1
                    current = float(m.group(1))
                    last_progress = now
                    sample = {"alpha_phi": {}}
                    state.update(
                        time_s=current, elapsed_s=now - start, samples=samples, max_u_seen_m_s=max_u
                    )
                    write_json(run / "run-state.json", state)
                m = re.search(r"max\(mag\(U\)\)\s*=\s*(\S+)", line)
                if m:
                    value = float(m.group(1))
                    max_u = max(max_u, value)
                    if (not math.isfinite(value) or value > 1000) and requested_stop is None:
                        state["stop_reason"] = f"velocity guard {value} m/s"
                        requested_stop = now
                        stop(name)
                m = re.search(r"sum\((\w+)\) of alphaPhi_ = (\S+)", line)
                if m:
                    sample["alpha_phi"][m.group(1)] = float(m.group(2))
                m = re.search(r"volIntegrate\(region0\) of alpha.water = (\S+)", line)
                if m:
                    sample["inventory_m3"] = float(m.group(1))
    if current is not None and current > previous:
        injected, net_external = integrate_sample(current, previous, sample, injected, net_external)
        with (run / "observations.jsonl").open("a") as obs:
            obs.write(json.dumps(sample) + "\n")
        samples += 1
        state.update(water_ledger=sample, mass_residual_kg=sample["residual_m3"] * 997.6)
    state.update(
        status="stopped"
        if requested_stop
        else "completed"
        if process.returncode == 0
        else "failed_solver",
        exit_code=process.wait(),
        elapsed_s=time.monotonic() - start,
        latest_printed_time_s=current,
        samples=samples,
        max_u_seen_m_s=max_u,
        finished_utc=datetime.now(UTC).isoformat(),
    )
    write_json(run / "run-state.json", state)
    return int(state["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
