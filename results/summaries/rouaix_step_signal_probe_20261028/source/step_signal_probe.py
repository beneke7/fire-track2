#!/usr/bin/env python3
"""Exercise the public Slurm step signal helper against this job's live step."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RANKS = 1
SIGNAL_NUMBER = 12


def utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def worker(directory: Path) -> int:
    received = False

    def handle_signal(signum: int, _frame: Any) -> None:
        nonlocal received
        write_json(
            directory / "signal-received.json",
            {
                "utc": utc(),
                "signal_number": signum,
                "job_id": os.environ.get("SLURM_JOB_ID"),
                "step_id": os.environ.get("SLURM_STEP_ID"),
                "task_count": os.environ.get("SLURM_NTASKS"),
                "global_rank": os.environ.get("SLURM_PROCID"),
            },
        )
        received = True

    signal.signal(signal.SIGUSR2, handle_signal)
    identity = " ".join(
        (
            os.environ.get("SLURM_JOB_ID", ""),
            os.environ.get("SLURM_STEP_ID", ""),
            os.environ.get("SLURM_NTASKS", ""),
            os.environ.get("SLURM_PROCID", ""),
        )
    )
    (directory / "identity.txt.tmp").write_text(identity + "\n", encoding="ascii")
    os.replace(directory / "identity.txt.tmp", directory / "identity.txt")
    while not received:
        time.sleep(0.05)
    return 0


def capture(command: list[str]) -> dict[str, Any]:
    started = utc()
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=15
        )
        return {
            "command": command,
            "started_utc": started,
            "finished_utc": utc(),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except Exception as error:
        return {
            "command": command,
            "started_utc": started,
            "finished_utc": utc(),
            "error": f"{type(error).__name__}: {error}",
        }


def controller(directory: Path) -> int:
    from run_pilot import signal_owned_step

    directory.mkdir(parents=True, exist_ok=True)
    job_id = os.environ.get("SLURM_JOB_ID", "")
    if not job_id.isdigit():
        raise RuntimeError("missing numeric SLURM_JOB_ID")
    helper = Path(__file__).with_name("run_pilot.py")
    trace: dict[str, Any] = {
        "schema_version": 1,
        "job_id": job_id,
        "job_name": os.environ.get("SLURM_JOB_NAME"),
        "task_allocation": {"nodes": 1, "tasks": 1, "cpus_per_task": 1},
        "slurm_conf": os.environ.get("SLURM_CONF"),
        "slurm_conf_server": os.environ.get("SLURM_CONF_SERVER"),
        "scontrol_path": __import__("shutil").which("scontrol"),
        "scancel_path": __import__("shutil").which("scancel"),
        "helper_source_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        "started_utc": utc(),
    }
    write_json(directory / "controller-start.json", trace)

    stdout = (directory / "step.stdout.log").open("w")
    stderr = (directory / "step.stderr.log").open("w")
    command = [
        "srun",
        "--nodes=1",
        "--ntasks=1",
        "--ntasks-per-node=1",
        sys.executable,
        "-u",
        str(Path(__file__).resolve()),
        "--worker",
        str(directory),
    ]
    trace["srun_command"] = command
    trace["srun_started_utc"] = utc()
    process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
    identity_path = directory / "identity.txt"
    deadline = time.monotonic() + 25
    while not identity_path.is_file() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    if not identity_path.is_file():
        trace["error"] = "owned step did not write its identity before timeout"
        write_json(directory / "probe-error.json", trace)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        stdout.close()
        stderr.close()
        return 2

    identity = identity_path.read_text(encoding="ascii").split()
    trace["identity"] = identity
    request_utc = utc()
    helper_receipt: dict[str, Any] = {}
    try:
        acknowledged = signal_owned_step(
            job_id, identity_path, "12", expected_ranks=RANKS, receipt=helper_receipt
        )
        error = None
    except Exception as exception:
        acknowledged = False
        error = f"{type(exception).__name__}: {exception}"
    ack_utc = utc() if acknowledged else None
    write_json(
        directory / "request-ack.json",
        {
            "request_utc": request_utc,
            "acknowledged": acknowledged,
            "acknowledged_utc": ack_utc,
            "signal_number": SIGNAL_NUMBER,
            "identity": identity,
            "helper_receipt": helper_receipt,
            "error": error,
        },
    )
    trace["request_utc"] = request_utc
    trace["acknowledged"] = acknowledged
    trace["acknowledged_utc"] = ack_utc
    trace["helper_receipt"] = helper_receipt
    if error is not None:
        trace["helper_error"] = error

    if not acknowledged:
        trace["cleanup"] = capture(["scancel", "--signal=TERM", f"{job_id}.{identity[1]}"])
    try:
        trace["srun_returncode"] = process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        trace["cleanup_after_timeout"] = capture(
            ["scancel", "--signal=TERM", f"{job_id}.{identity[1]}"]
        )
        try:
            trace["srun_returncode"] = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            trace["cleanup_after_timeout_kill"] = capture(
                ["scancel", "--signal=KILL", f"{job_id}.{identity[1]}"]
            )
            process.wait(timeout=10)
            trace["srun_returncode"] = process.returncode
    stdout.close()
    stderr.close()
    receipt = directory / "signal-received.json"
    trace["signal_received"] = receipt.is_file()
    if receipt.is_file():
        trace["signal_receipt"] = json.loads(receipt.read_text(encoding="utf-8"))
    trace["finished_utc"] = utc()
    trace["status"] = (
        "passed"
        if acknowledged
        and trace["signal_received"]
        and trace["srun_returncode"] == 0
        else "failed"
    )
    write_json(directory / "controller-result.json", trace)
    return 0 if trace["status"] == "passed" else 1


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        return worker(Path(sys.argv[2]))
    if len(sys.argv) != 2:
        raise SystemExit("usage: step_signal_probe.py OUTPUT_DIR | --worker OUTPUT_DIR")
    return controller(Path(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
