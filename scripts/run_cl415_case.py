#!/usr/bin/env python3
"""Preserve and execute a prepared, exploratory CL415 water-air case."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "opencfd/openfoam-default:2512"
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,59}")


def utc() -> str:
    return datetime.now(UTC).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def solver_summary(log: str, horizon_s: float) -> dict:
    values = re.findall(r"^Time = ([0-9.eE+-]+)$", log, re.M)
    times = [float(value) for value in values]
    clocks = re.findall(r"ClockTime = ([0-9.eE+-]+) s", log)
    stages = dict(re.findall(r"^CL415_STAGE_EXIT stage=(\w+) code=(\d+)$", log, re.M))
    last = times[-1] if times else None
    return {
        "last_time_s": last,
        "solver_steps": len(times),
        "solver_clock_time_s": float(clocks[-1]) if clocks else None,
        "stage_exit_codes": {name: int(code) for name, code in stages.items()},
        "mesh_ok": "Mesh OK." in log and "Failed " not in log,
        "reached_requested_horizon": last is not None and abs(last - horizon_s) <= 1e-6,
        "fatal_error_observed": bool(
            re.search(r"FOAM FATAL|Floating point exception(?! trapping enabled)", log)
        ),
    }


def shell_script(ranks: int) -> str:
    return f"""set +e +u
source /usr/lib/openfoam/openfoam2512/etc/bashrc
setup_code=$?
if [ "$setup_code" -ne 0 ]; then exit "$setup_code"; fi
set -euo pipefail
run_stage() {{
    local stage="$1"; shift
    set +e
    "$@" > "log.$stage" 2>&1
    local code=$?
    set -e
    cat "log.$stage"
    printf 'CL415_STAGE_EXIT stage=%s code=%s\\n' "$stage" "$code"
    return "$code"
}}
run_stage blockMesh blockMesh
run_stage checkMesh checkMesh -allTopology -allGeometry
grep -q 'Mesh OK.' log.checkMesh
if grep -q 'Failed .*mesh checks' log.checkMesh; then exit 2; fi
run_stage decomposePar decomposePar -force
run_stage interIsoFoam mpirun -np {ranks} interIsoFoam -parallel
run_stage reconstructPar reconstructPar -fields '(alpha.water U k epsilon)'
"""


def pilot_mass_error(after: Path, dependency: dict) -> float:
    if dependency.get("status") != "exploratory_completed":
        raise RuntimeError("required pilot did not complete with diagnostics")
    report = json.loads((after / "analytics/report.json").read_text())
    last = report["times"][-1]
    residual = last.get("sampled_mass_residual_kg")
    injected = last.get("sampled_injected_water_kg", 0)
    if (
        residual is None
        or not math.isfinite(residual)
        or not math.isfinite(injected)
        or injected <= 0
        or abs(residual) > 0.01 * injected
    ):
        raise RuntimeError("pilot sampled mass diagnostic missing or exceeds 1%")
    return abs(residual) / injected


def wait_for_capacity(
    manifest: dict,
    path: Path,
    after: Path | None,
    deadline: float,
    *,
    require_success: bool = False,
) -> None:
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError("dependency/capacity wait deadline exceeded")
        dependency_ready = after is None
        if after is not None:
            source = after / "manifest.json"
            if source.exists():
                dependency = json.loads(source.read_text())
                dependency_ready = bool(dependency.get("finished_utc"))
                if dependency_ready:
                    manifest["dependency_exit_code"] = dependency.get("exit_code")
                    if require_success:
                        manifest["dependency_sampled_mass_error_fraction"] = pilot_mass_error(
                            after, dependency
                        )
        process = subprocess.run(
            ["ps", "-eo", "comm"], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        busy = any(
            name.strip() in {"interIsoFoam", "interFoam", "snappyHexMesh", "blockMesh"}
            for name in process
        )
        if dependency_ready and not busy:
            return
        manifest.update(status="waiting_for_capacity", updated_utc=utc())
        save(path, manifest)
        time.sleep(60)


def run(args: argparse.Namespace) -> int:
    run_dir = ROOT / "results" / "runs" / args.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    manifest = {
        "run_id": args.run_id,
        "started_utc": utc(),
        "status": "preparing",
        "classification": "Exploratory simplified CL415; no E3 acceptance decision",
        "allocation": {"ranks": args.ranks, "memory_gib": args.memory_gib},
        "solver_image": IMAGE,
        "after_run_dir": str(args.after_run_dir) if args.after_run_dir else None,
        "require_successful_pilot": args.require_after_success,
        "pilot_stop_rule": "When required, missing diagnostics or sampled mass residual above 1% prevents the longer exploratory run; this is not E3 acceptance",
        "runner_sha256": sha256(Path(__file__)),
    }
    save(manifest_path, manifest)
    container_id: str | None = None
    process: subprocess.Popen | None = None
    started = None
    exit_code = 1
    try:
        if any(path.is_symlink() for path in args.case_dir.rglob("*")):
            raise ValueError("prepared case must not contain symlinks")
        case = run_dir / "case"
        shutil.copytree(args.case_dir, case)
        inputs = json.loads((case / "case-inputs.json").read_text())
        if int(inputs["ranks"]) != args.ranks:
            raise ValueError("runner ranks must match the frozen prepared decomposition")
        manifest["inputs"] = inputs
        shutil.copy2(Path(__file__), run_dir / "runner-snapshot.py")
        analyzer = ROOT / "scripts/analyze_cl415_case.py"
        shutil.copy2(analyzer, run_dir / "analyzer-snapshot.py")
        manifest["analyzer_sha256"] = sha256(analyzer)
        analysis_package = run_dir / "analysis_modules/aerial_drop"
        analysis_package.mkdir(parents=True)
        (analysis_package / "__init__.py").write_text("")
        structure_module = ROOT / "src/aerial_drop/structure_counts.py"
        shutil.copy2(structure_module, analysis_package / "structure_counts.py")
        manifest["structure_counter_sha256"] = sha256(structure_module)
        manifest["prepared_case_sha256"] = {
            str(path.relative_to(case)): sha256(path)
            for path in sorted(case.rglob("*"))
            if path.is_file()
        }
        manifest["git_revision"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        manifest["git_dirty"] = bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        )
        save(manifest_path, manifest)
        if args.prepare_only:
            manifest["status"] = "prepared_only"
            exit_code = 0
            return exit_code
        wait_for_capacity(
            manifest,
            manifest_path,
            args.after_run_dir,
            time.monotonic() + args.wait_timeout_s,
            require_success=args.require_after_success,
        )
        if shutil.disk_usage(run_dir).free < 40 * 1024**3:
            raise RuntimeError("less than 40 GiB disk free at launch")
        subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                str(ROOT / "scripts/doctor.py"),
                "--output",
                str(run_dir / "machine.json"),
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        image_id = subprocess.check_output(
            ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], text=True
        ).strip()
        manifest["solver_image_id"] = image_id
        cidfile = run_dir / "container.cid"
        command = [
            "docker",
            "run",
            "--rm",
            "--cidfile",
            str(cidfile),
            "--name",
            args.run_id,
            f"--cpus={args.ranks}",
            f"--memory={args.memory_gib}g",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--env",
            "OMP_NUM_THREADS=1",
            "--env",
            "OPENBLAS_NUM_THREADS=1",
            "--mount",
            f"type=bind,src={case},dst=/case",
            "--workdir",
            "/case",
            "--entrypoint",
            "/bin/bash",
            image_id,
            "-c",
            shell_script(args.ranks),
        ]
        manifest.update(status="running", solver_started_utc=utc())
        save(manifest_path, manifest)
        started = time.monotonic()
        with (run_dir / "openfoam-console.log").open("wb") as stream:
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
            with (run_dir / "resources.jsonl").open("w") as resources:
                while process.poll() is None:
                    remaining = args.timeout_s - (time.monotonic() - started)
                    if remaining <= 0:
                        manifest["timeout"] = True
                        raise TimeoutError("solver wall time exceeded")
                    try:
                        process.wait(timeout=min(60, remaining))
                    except subprocess.TimeoutExpired:
                        sample = subprocess.run(
                            [
                                "docker",
                                "stats",
                                "--no-stream",
                                "--format",
                                "{{json .}}",
                                args.run_id,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=15,
                            check=False,
                        )
                        resources.write(
                            json.dumps(
                                {
                                    "utc": utc(),
                                    "elapsed_s": time.monotonic() - started,
                                    "docker_stats": sample.stdout.strip(),
                                }
                            )
                            + "\n"
                        )
                        resources.flush()
                exit_code = process.returncode
        summary = solver_summary(
            (run_dir / "openfoam-console.log").read_text(errors="replace"), inputs["horizon_s"]
        )
        manifest["solver_summary"] = summary
        accepted = (
            exit_code == 0
            and summary["mesh_ok"]
            and summary["reached_requested_horizon"]
            and not summary["fatal_error_observed"]
        )
        manifest["status"] = "exploratory_completed" if accepted else "failed_or_incomplete"
        exit_code = 0 if accepted else 1
        if accepted:
            analysis_environment = os.environ.copy()
            analysis_environment["PYTHONPATH"] = str(run_dir / "analysis_modules")
            analysis = subprocess.run(
                [
                    str(ROOT / ".venv/bin/python"),
                    str(run_dir / "analyzer-snapshot.py"),
                    "--run-dir",
                    str(run_dir),
                    "--output-dir",
                    str(run_dir / "analytics"),
                ],
                cwd=ROOT,
                env=analysis_environment,
                capture_output=True,
                text=True,
                check=False,
            )
            (run_dir / "analysis.log").write_text(analysis.stdout + analysis.stderr)
            manifest["analysis_exit_code"] = analysis.returncode
            if analysis.returncode:
                manifest["status"] = "flow_completed_analysis_failed"
        return exit_code
    except (Exception, KeyboardInterrupt) as error:
        exit_code = 1
        manifest.update(status="failed_or_interrupted", error=f"{type(error).__name__}: {error}")
        return 1
    finally:
        cidfile = run_dir / "container.cid"
        if process is not None and process.poll() is None:
            try:
                if cidfile.exists():
                    container_id = cidfile.read_text().strip()
                    if re.fullmatch(r"[0-9a-f]{64}", container_id):
                        subprocess.run(
                            ["docker", "stop", "-t", "10", container_id],
                            capture_output=True,
                            check=False,
                            timeout=30,
                        )
                process.wait(timeout=30)
            except (OSError, subprocess.TimeoutExpired) as error:
                manifest["cleanup_error"] = str(error)
                process.kill()
                process.wait()
        manifest.update(finished_utc=utc(), exit_code=exit_code)
        if started is not None:
            manifest["wall_time_s"] = time.monotonic() - started
        save(manifest_path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ranks", type=int, default=20)
    parser.add_argument("--memory-gib", type=int, default=48)
    parser.add_argument("--timeout-s", type=float, default=14400)
    parser.add_argument("--wait-timeout-s", type=float, default=86400)
    parser.add_argument("--after-run-dir", type=Path)
    parser.add_argument("--require-after-success", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if not RUN_ID.fullmatch(args.run_id) or not 1 <= args.ranks <= 20:
        parser.error("invalid run id or ranks (1..20)")
    if args.memory_gib <= 0 or not 0 < args.timeout_s < float("inf"):
        parser.error("positive finite timeout and memory required")
    if not 0 < args.wait_timeout_s < float("inf"):
        parser.error("positive finite wait timeout required")
    if args.require_after_success and args.after_run_dir is None:
        parser.error("--require-after-success needs --after-run-dir")
    args.case_dir = args.case_dir.resolve()
    if args.after_run_dir:
        args.after_run_dir = args.after_run_dir.resolve()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
