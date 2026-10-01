#!/usr/bin/env python3
"""Run one horizontal-source AMR diagnostic against the frozen HNF laminar case."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_ID = "restas-hnf-laminar-20260928T145501Z-4fe554"
REFERENCE_RUN = ROOT / "results/runs" / REFERENCE_ID
IMAGE = "opencfd/openfoam-default:2512"
RANKS = 18
DOCKER_CPUS = 20
MEMORY_GIB = 96
SPACING_M = 0.05
END_TIME_S = 0.02
MAX_CELLS = 400_000

sys.path.insert(0, str(ROOT / "cases/restas_horizontal_nearfield"))
import prepare_case  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_flux_diagnostics(control_path: Path) -> None:
    text = control_path.read_text(encoding="utf-8")
    pieces: list[str] = []
    for name in ("slot_01", "slot_02", "slot_03", "slot_04", "xOutlet", "airInlet", "airOutlet"):
        pieces.append(
            "    "
            + name
            + "Flux\n    {\n        type surfaceFieldValue;\n        libs (fieldFunctionObjects);\n"
            + "        regionType patch;\n        name "
            + name
            + ";\n        operation sum;\n        fields (phi alphaPhi_);\n"
            + "        writeFields false;\n        executeControl timeStep;\n        executeInterval 1;\n"
            + "        writeControl writeTime;\n        writeInterval 1;\n    }\n"
        )
    if "functions\n{" not in text:
        raise RuntimeError("generated horizontal controlDict has no function-object section")
    start = text.index("functions\n{") + len("functions\n{")
    control_path.write_text(text[:start] + "\n" + "".join(pieces) + text[start:], encoding="utf-8")


def stage_records(log: str) -> list[dict[str, Any]]:
    return [
        {"stage": stage, "exit_code": int(code)}
        for stage, code in re.findall(
            r"^HNFA_STAGE_EXIT stage=([A-Za-z0-9_]+) code=(\d+)$", log, re.M
        )
    ]


def solver_summary(log: str) -> dict[str, Any]:
    solver = log.rsplit("Exec   : interIsoFoam -parallel", 1)[-1]
    solver = solver.split("\nExec   : reconstructParMesh", 1)[0]
    times = [float(x) for x in re.findall(r"^Time =\s*([0-9.eE+-]+)\s*$", solver, re.M)]
    clocks = [
        (float(cpu), float(wall))
        for cpu, wall in re.findall(
            r"^ExecutionTime =\s*([0-9.eE+-]+) s\s+ClockTime =\s*([0-9.eE+-]+) s", solver, re.M
        )
    ]
    pressure_iterations = [
        int(x) for x in re.findall(r"GAMG:\s+Solving for p_rgh,.*?No Iterations (\d+)", solver)
    ]
    return {
        "last_time_s": max(times) if times else None,
        "solver_steps": len(clocks),
        "solver_execution_time_s": clocks[-1][0] if clocks else None,
        "solver_clock_time_s": clocks[-1][1] if clocks else None,
        "pressure_solve_count": len(pressure_iterations),
        "pressure_iteration_total": sum(pressure_iterations),
        "mean_pressure_iterations_per_solve": sum(pressure_iterations) / len(pressure_iterations)
        if pressure_iterations
        else None,
        "max_courant_number": max(
            (
                float(x)
                for x in re.findall(r"^Courant Number mean:.*? max: ([0-9.eE+-]+)", solver, re.M)
            ),
            default=None,
        ),
        "max_interface_courant_number": max(
            (
                float(x)
                for x in re.findall(
                    r"^Interface Courant Number mean:.*? max: ([0-9.eE+-]+)", solver, re.M
                )
            ),
            default=None,
        ),
    }


def run(baseline_run: Path) -> Path:
    baseline_run = baseline_run.resolve()
    if not (baseline_run / "manifest.json").is_file() or not (baseline_run / "case").is_dir():
        raise FileNotFoundError(f"horizontal reference run is missing: {baseline_run}")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"restas-hnf-amr-dynamic-{stamp}-{uuid.uuid4().hex[:6]}"
    run_dir = ROOT / "results/runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    case = run_dir / "case"
    inputs = prepare_case.prepare_case(case, "laminar", RANKS, SPACING_M, END_TIME_S)
    inputs.update(
        {
            "variant": "horizontal_dynamic_amr",
            "comparison_reference_run_id": baseline_run.name,
            "comparison_reference_mesh_spacing_m": 0.025,
            "comparison_reference_mesh_cells": 802_944,
            "comparison_case_classification": "corrected horizontal four-slot near-field; water exits +x, ambient air +y",
            "dynamic_refinement": {
                "field": "alpha.water",
                "lower_refine_level": 0.001,
                "upper_refine_level": 0.999,
                "unrefine_level": 0.001,
                "max_refinement_levels": 1,
                "refine_interval_steps": 1,
                "buffer_layers": 1,
                "max_cells": MAX_CELLS,
                "finest_spacing_m": 0.025,
            },
            "diagnostic_difference": "Dynamic run adds patch surfaceFieldValue water/total flux output at write times; this affects output/measurement cost only.",
        }
    )
    inputs_path = run_dir / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dynamic_mesh_dict = (
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n"
        '    location "constant";\n    object dynamicMeshDict;\n}\n\n'
        "dynamicFvMesh dynamicRefineFvMesh;\n\n"
        "refineInterval 1;\nfield alpha.water;\nlowerRefineLevel 0.001;\n"
        "upperRefineLevel 0.999;\nunrefineLevel 0.001;\nnBufferLayers 1;\n"
        f"maxRefinement 1;\nmaxCells {MAX_CELLS};\n"
        "correctFluxes ((phi none) (nHatf none) (rhoPhi none) (alphaPhi_ none) (ghf none) (phi0 none) (dVf_ none));\n"
        "dumpLevel true;\n"
    )
    (case / "constant/dynamicMeshDict").write_text(dynamic_mesh_dict, encoding="utf-8")
    write_flux_diagnostics(case / "system/controlDict")

    baseline_inputs = json.loads((baseline_run / "inputs.json").read_text(encoding="utf-8"))
    baseline_manifest = json.loads((baseline_run / "manifest.json").read_text(encoding="utf-8"))
    common_files = (
        "0/U",
        "0/alpha.water",
        "0/p_rgh",
        "constant/g",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        "system/fvSchemes",
        "system/fvSolution",
    )
    common_hashes = {
        relative: {
            "horizontal_reference_sha256": sha256(baseline_run / "case" / relative),
            "new_dynamic_sha256": sha256(case / relative),
            "bytewise_match": sha256(baseline_run / "case" / relative) == sha256(case / relative),
        }
        for relative in common_files
    }
    if not all(value["bytewise_match"] for value in common_hashes.values()):
        raise RuntimeError(
            "prepared coarse fields/physics differ from the frozen horizontal laminar reference"
        )

    image_id = subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    source_files = (
        Path(__file__),
        ROOT / "cases/restas_horizontal_nearfield/prepare_case.py",
        ROOT / "cases/restas_amr_probe/analyze_horizontal_amr.py",
        ROOT / "cases/restas_amr_probe/render_probe.py",
        ROOT / "scripts/run_local.py",
        baseline_run / "inputs.json",
        baseline_run / "manifest.json",
    )
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_utc": datetime.now(UTC).isoformat(),
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
        "case_classification": "Corrected horizontal four-slot exploratory near-field AMR diagnostic; not validation.",
        "comparison_reference": {
            "run_id": baseline_run.name,
            "inputs_sha256": baseline_manifest.get("inputs_sha256"),
            "manifest_sha256": sha256(baseline_run / "manifest.json"),
            "mesh_cells": baseline_inputs["mesh_cells_expected"],
            "spacing_m": baseline_inputs["mesh_spacing_m"],
            "solver_wall_time_s": baseline_manifest.get("solver_log_summary", {}).get(
                "final_reported_clock_time_s"
            ),
            "full_wall_time_s": baseline_manifest.get("wall_time_s"),
        },
        "common_physics_and_field_file_hashes": common_hashes,
        "source_sha256": {
            str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path): sha256(path)
            for path in source_files
            if path.is_file()
        },
        "inputs_sha256": sha256(inputs_path),
        "prepared_case_file_sha256": {
            str(path.relative_to(case)): sha256(path)
            for path in sorted(case.rglob("*"))
            if path.is_file()
        },
        "solver_image": IMAGE,
        "solver_image_id": image_id,
        "execution": {
            "mpi_ranks": RANKS,
            "docker_cpu_limit": DOCKER_CPUS,
            "docker_memory_limit_gib": MEMORY_GIB,
            "wall_timeout_s": 900,
            "command": "blockMesh; checkMesh; decomposePar; mpirun interIsoFoam -parallel; reconstructParMesh -constant; reconstructPar fields at 0.01 and 0.02 s",
            "time_controls_match_reference": True,
            "step_controls": {
                "adaptive": True,
                "max_delta_t_s": 3.75e-5,
                "max_Co": 0.3,
                "max_alpha_Co": 0.15,
            },
        },
        "scope": "Short exploratory horizontal-source AMR cost/morphology check; not E1-E6 validation or a device reproduction.",
        "baseline_inputs_snapshot": baseline_inputs,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    mount = f"type=bind,src={case.resolve()},dst=/case"
    container_name = run_id[:60]
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        f"--cpus={DOCKER_CPUS}",
        f"--memory={MEMORY_GIB}g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        mount,
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        IMAGE,
        "-lc",
    ]
    shell = """source /usr/lib/openfoam/openfoam2512/etc/bashrc
set -euo pipefail
run_stage() { local stage="$1"; shift; set +e; "$@"; local status=$?; set -e; printf 'HNFA_STAGE_EXIT stage=%s code=%s\\n' "$stage" "$status"; return "$status"; }
run_stage blockMesh blockMesh
run_stage checkMesh checkMesh -allTopology -allGeometry
run_stage decomposePar decomposePar -force
run_stage interIsoFoam mpirun -np __MPI_RANKS__ interIsoFoam -parallel
run_stage reconstructParMesh reconstructParMesh -constant
run_stage reconstructPar reconstructPar -time '0:0.02' -fields '(alpha.water U p_rgh cellLevel)'
"""
    shell = shell.replace("__MPI_RANKS__", str(RANKS))
    log_path = run_dir / "openfoam-console.log"
    samples: list[dict[str, Any]] = []
    started = time.monotonic()
    proc: subprocess.Popen[bytes]
    with log_path.open("wb") as stream:
        proc = subprocess.Popen([*command, shell], stdout=stream, stderr=subprocess.STDOUT)
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
                timeout=8,
                check=False,
            )
            if stat.returncode == 0 and stat.stdout.strip():
                cpu, memory = stat.stdout.strip().split("|", 1)
                sample.update({"cpu_percent": cpu, "memory_usage_and_limit": memory})
            samples.append(sample)
            if time.monotonic() - started > 900:
                subprocess.run(
                    ["docker", "stop", container_name], capture_output=True, timeout=20, check=False
                )
                break
            time.sleep(2)
        exit_code = proc.wait()
    wall = time.monotonic() - started
    log = log_path.read_text(encoding="utf-8", errors="replace")
    summary = solver_summary(log)
    cpu = [float(s.get("cpu_percent", "0%").rstrip("%")) for s in samples if "cpu_percent" in s]
    mem: list[float] = []
    for sample in samples:
        match = re.match(r"([0-9.]+)\s*(B|KiB|MiB|GiB)", sample.get("memory_usage_and_limit", ""))
        if match:
            factor = {"B": 2**-30, "KiB": 2**-20, "MiB": 2**-10, "GiB": 1}[match.group(2)]
            mem.append(float(match.group(1)) * factor)
    manifest.update(
        {
            "finished_utc": datetime.now(UTC).isoformat(),
            "wall_time_s": wall,
            "exit_code": exit_code,
            "stage_exit_records": stage_records(log),
            "solver_log_summary": summary,
            "docker_resource_samples": samples,
            "peak_sampled_cpu_percent": max(cpu, default=None),
            "peak_sampled_memory_gib": max(mem, default=None),
            "resource_sample_note": "Docker stats sampled about every two seconds; brief peaks can be higher.",
            "output_tree_bytes": sum(p.stat().st_size for p in run_dir.rglob("*") if p.is_file()),
            "run_sha256": {
                str(path.relative_to(run_dir)): sha256(path)
                for path in sorted(run_dir.rglob("*"))
                if path.is_file() and path.name not in {"run-sha256.json", "manifest.json"}
            },
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "exit_code": exit_code,
                "wall_time_s": wall,
                "solver": summary,
                "peak_ram_gib": max(mem, default=None),
                "run_dir": str(run_dir.relative_to(ROOT)),
            },
            indent=2,
        ),
        flush=True,
    )
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run-dir", type=Path, default=REFERENCE_RUN)
    args = parser.parse_args()
    run_dir = run(args.baseline_run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    failed_stages = [record for record in manifest["stage_exit_records"] if record["exit_code"]]
    summary = manifest["solver_log_summary"]
    if (
        manifest["exit_code"]
        or failed_stages
        or not summary["last_time_s"]
        or summary["last_time_s"] < END_TIME_S
    ):
        return int(manifest["exit_code"] or failed_stages[0]["exit_code"] or 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
