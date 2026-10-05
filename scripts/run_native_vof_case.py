#!/usr/bin/env python3
"""Run a frozen Dash-8 case on its existing static polyhedral mesh.

The lifecycle copies and hashes an already meshed case, checks it with the
pinned OpenFOAM 2512 image, decomposes it, and runs ``interIsoFoam``. It never
invokes ``blockMesh`` or ``snappyHexMesh``. Native conservation and topology
postprocessing are recorded separately from CFD completion; neither is a
paper-acceptance decision.

The solver runs in a CPU-limited Docker container. For an interactive launch,
run this script directly so its SIGTERM handler can stop and verify the Docker
container before exit. Do not wrap this long-running command in
``scripts/run_local.py``: that wrapper terminates its child process group after
one second. A systemd service should use ``KillMode=process`` and allow enough
time for Docker cleanup, for example::

    [Service]
    ExecStart=/home/v/proj/bene/fire-track2/.venv/bin/python /home/v/proj/bene/fire-track2/scripts/run_native_vof_case.py --case-dir /path/to/prepared/case --run-id dash8-native-example --ranks 20 --memory-gib 96 --timeout-s 14400
    KillMode=process
    TimeoutStopSec=300s

The runner measures current Docker CPU usage and active host OpenFOAM utility
processes before accepting the requested rank budget; paused and stopped
containers do not consume measured CPU capacity. Its common snapshots are
analysis checkpoints, not restart-ready OpenFOAM states.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "opencfd/openfoam-default:2512"
PINNED_IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
SOLVER_PROCESS_NAMES = {
    "interIsoFoam",
    "interFoam",
    "decomposePar",
    "checkMesh",
    "blockMesh",
    "snappyHexMesh",
}
CONTAINER_LABEL_RUN = "dash8.native_vof.run_id"
CONTAINER_LABEL_STAGE = "dash8.native_vof.stage"
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{4,80}$")
TIME_TOKEN = r"([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?)"


class RunnerError(RuntimeError):
    """A preflight or lifecycle error with its attempt preserved in a bundle."""


class RunnerTermination(Exception):
    """SIGTERM/SIGINT translated into an exception so owned work can be cleaned up."""

    def __init__(self, signum: int):
        super().__init__(f"received signal {signum}")
        self.signum = signum


def _termination_handler(signum: int, frame: object) -> None:
    del frame
    # Ignore repeated requests while the first one is stopping Docker and
    # reaping its client. systemd's later SIGKILL remains its final hard stop.
    signal.signal(signum, signal.SIG_IGN)
    raise RunnerTermination(signum)


@contextmanager
def termination_handlers() -> Iterator[None]:
    """Install cleanup-aware handlers for the main runner process."""
    previous = {
        signum: signal.signal(signum, _termination_handler)
        for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


@contextmanager
def _defer_termination_during_cleanup() -> Iterator[None]:
    """Let ownership checks and container stop complete before handling signals."""
    if not hasattr(signal, "pthread_sigmask"):
        yield
        return
    blocked = {signal.SIGTERM, signal.SIGINT}
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    """Hash every regular file in a prepared case; reject links and odd entries."""
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"prepared case contains a symbolic link: {path}")
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = sha256_file(path)
        elif not path.is_dir():
            raise ValueError(f"prepared case contains a non-regular entry: {path}")
    return hashes


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)


def _single_scalar(text: str, key: str, *, label: str) -> str:
    clean = _strip_comments(text)
    values: list[str] = []
    depth = 0
    for line in clean.splitlines():
        if depth == 0:
            match = re.match(rf"^\s*{re.escape(key)}\s+([^;]+);\s*$", line)
            if match:
                values.append(match.group(1).strip())
        depth += line.count("{") - line.count("}")
        if depth < 0:
            raise ValueError(f"{label} has unbalanced dictionary braces")
    if depth != 0:
        raise ValueError(f"{label} has unbalanced dictionary braces")
    if len(values) != 1:
        raise ValueError(f"{label} must contain one {key} entry; found {len(values)}")
    return values[0].strip()


def _parse_float(value: str, *, label: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{label} is not a literal number: {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def read_patch_face_counts(boundary_path: Path) -> dict[str, int]:
    """Read patch counts from the native polyMesh boundary dictionary."""
    text = _strip_comments(boundary_path.read_text(encoding="utf-8", errors="strict"))
    counts: dict[str, int] = {}
    for match in re.finditer(r"(?ms)^\s*([A-Za-z_][A-Za-z_0-9]*)\s*\{(.*?)^\s*\}", text):
        name, body = match.groups()
        faces = re.search(r"(?m)^\s*nFaces\s+(\d+)\s*;", body)
        if faces:
            counts[name] = int(faces.group(1))
    return counts


def _case_numeric_directories(case_dir: Path) -> list[tuple[float, Path]]:
    found: list[tuple[float, Path]] = []
    for path in case_dir.iterdir():
        if not path.is_dir():
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        if math.isfinite(value):
            found.append((value, path))
    return found


def validate_prepared_case(case_dir: Path, *, ranks: int) -> dict[str, Any]:
    """Check the frozen case contract before copying or invoking OpenFOAM."""
    case_dir = case_dir.resolve(strict=True)
    if not case_dir.is_dir():
        raise ValueError("--case-dir must be a directory")
    input_hashes = tree_hashes(case_dir)
    input_bytes = sum((case_dir / relative).stat().st_size for relative in input_hashes)
    metadata_path = case_dir / "case-inputs.json"
    if not metadata_path.is_file():
        raise ValueError("prepared static VOF case requires case-inputs.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("solver") != "interIsoFoam":
        raise ValueError("case-inputs.json must declare solver interIsoFoam")
    if int(metadata.get("ranks", -1)) != ranks:
        raise ValueError("requested ranks do not match case-inputs.json")
    if ranks < 1:
        raise ValueError("MPI ranks must be positive")
    horizon = _parse_float(str(metadata.get("horizon_s", "nan")), label="horizon_s")
    if horizon <= 0:
        raise ValueError("horizon_s must be positive")

    mesh_type = str(metadata.get("mesh_type", "")).lower()
    if "poly" not in mesh_type and "unstructured" not in mesh_type:
        raise ValueError("case-inputs.json must identify a static polyhedral/unstructured mesh")
    mesh_dir = case_dir / "constant" / "polyMesh"
    missing_mesh = [name for name in POLYMESH_FILES if not (mesh_dir / name).is_file()]
    if missing_mesh:
        raise ValueError(f"prebuilt constant/polyMesh is incomplete: {missing_mesh}")

    expected_cells = metadata.get("mesh_cells_expected")
    if not isinstance(expected_cells, int) or expected_cells <= 0:
        raise ValueError("case-inputs.json requires positive mesh_cells_expected")
    source_patches = metadata.get("source_patches")
    source_face_counts = metadata.get("source_patch_face_counts")
    if (
        not isinstance(source_patches, list)
        or not source_patches
        or not isinstance(source_face_counts, dict)
    ):
        raise ValueError("case-inputs.json requires source_patches and source_patch_face_counts")
    if any(
        not isinstance(patch, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", patch)
        for patch in source_patches
    ) or len(set(source_patches)) != len(source_patches):
        raise ValueError("source patch names must be unique OpenFOAM words")
    if set(source_patches) != set(source_face_counts):
        raise ValueError(
            "source patch list and source face-count metadata must name the same patches"
        )
    boundary_counts = read_patch_face_counts(mesh_dir / "boundary")
    source_inventory: dict[str, dict[str, int]] = {}
    for patch in source_patches:
        expected = source_face_counts.get(patch)
        actual = boundary_counts.get(patch)
        if not isinstance(expected, int) or expected <= 0:
            raise ValueError(f"source face count metadata is missing for {patch!r}")
        if actual != expected:
            raise ValueError(
                f"native boundary count for {patch!r} is {actual}; metadata declares {expected}"
            )
        source_inventory[patch] = {"expected_faces": expected, "native_boundary_faces": actual}

    if any(path.is_dir() for path in case_dir.glob("processor[0-9]*")):
        raise ValueError("prepared case must be undecomposed; processor* input directories found")
    if any(value > 1e-12 for value, _ in _case_numeric_directories(case_dir)):
        raise ValueError("prepared case must start from zero and contain no positive-time fields")

    control_path = case_dir / "system" / "controlDict"
    decompose_path = case_dir / "system" / "decomposeParDict"
    if not control_path.is_file() or not decompose_path.is_file():
        raise ValueError("system/controlDict and system/decomposeParDict are required")
    control = _strip_comments(control_path.read_text(encoding="utf-8"))
    application = _single_scalar(control, "application", label="controlDict")
    if application != "interIsoFoam":
        raise ValueError(f"controlDict application must be interIsoFoam, got {application!r}")
    end_time = _parse_float(
        _single_scalar(control, "endTime", label="controlDict"), label="endTime"
    )
    if not math.isclose(end_time, horizon, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(
            f"controlDict endTime {end_time:g} does not match metadata horizon {horizon:g}"
        )
    start = _parse_float(
        _single_scalar(control, "startTime", label="controlDict"), label="startTime"
    )
    if not math.isclose(start, 0.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("native mass-ledger runner requires startTime 0")
    write_control = _single_scalar(control, "writeControl", label="controlDict")
    if write_control not in {"adjustableRunTime", "runTime"}:
        raise ValueError("sparse snapshots require writeControl runTime/adjustableRunTime")
    write_interval = _parse_float(
        _single_scalar(control, "writeInterval", label="controlDict"), label="writeInterval"
    )
    if write_interval <= 0:
        raise ValueError("controlDict writeInterval must be positive")
    time_controls = metadata.get("time_controls", {})
    declared_intervals = [
        time_controls.get(name)
        for name in ("snapshot_interval_s", "requested_snapshot_interval_s", "write_interval_s")
        if time_controls.get(name) is not None
    ]
    if declared_intervals:
        declared = _parse_float(str(declared_intervals[0]), label="declared snapshot interval")
        if not math.isclose(write_interval, declared, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(
                f"controlDict writeInterval {write_interval:g} does not match declared snapshot interval {declared:g}"
            )
        if any(float(item) != declared for item in declared_intervals[1:]):
            raise ValueError("case-inputs.json has contradictory snapshot interval metadata")

    decompose = _strip_comments(decompose_path.read_text(encoding="utf-8"))
    subdomains = int(_single_scalar(decompose, "numberOfSubdomains", label="decomposeParDict"))
    if subdomains != ranks:
        raise ValueError(
            f"decomposeParDict numberOfSubdomains={subdomains}; requested ranks={ranks}"
        )
    return {
        "case_directory": str(case_dir),
        "case_inputs": metadata,
        "input_file_sha256": input_hashes,
        "input_tree_bytes": input_bytes,
        "horizon_s": horizon,
        "expected_mesh_cells": expected_cells,
        "mesh_type": mesh_type,
        "write_control": write_control,
        "write_interval_s": write_interval,
        "decomposition_subdomains": subdomains,
        "source_patch_inventory": source_inventory,
        "poly_mesh_sha256": {
            name: input_hashes[f"constant/polyMesh/{name}"] for name in POLYMESH_FILES
        },
    }


def _check_mesh_cells(log: str) -> int:
    matches = re.findall(r"(?m)^\s*cells:\s*([\d,]+)\s*$", log)
    if len(matches) != 1:
        raise ValueError(f"checkMesh log must report exactly one cell count; found {matches}")
    return int(matches[0].replace(",", ""))


def _failed_check_lines(log: str) -> list[str]:
    return [line.strip() for line in log.splitlines() if re.match(r"^\s*\*\*\*", line)]


def validate_planar_exception(
    evidence_path: Path, case_dir: Path, failed_lines: list[str], log: str
) -> dict[str, Any]:
    """Verify a narrowly scoped, mesh-hash-bound planar transition exception."""
    evidence_path = evidence_path.resolve(strict=True)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("schema") != "dash8-static-polyhedral-planar-exception-v1":
        raise ValueError("mesh exception evidence has an unsupported schema")
    expected_lines = evidence.get("expected_checkmesh_failure_lines")
    if not isinstance(expected_lines, list) or len(expected_lines) != 1:
        raise ValueError("planar exception must enumerate exactly one expected checker flag")
    exact_flag = re.compile(
        r"^\*\*\*Concave cells \(using face planes\) found, number of cells: \d+$"
    )
    if not all(isinstance(line, str) and exact_flag.fullmatch(line) for line in expected_lines):
        raise ValueError(
            "only the exact checkMesh planar-transition/concave-cells flag is eligible"
        )
    if failed_lines != expected_lines:
        raise ValueError(
            f"checkMesh failures {failed_lines!r} do not exactly match reviewed evidence {expected_lines!r}"
        )
    summaries = re.findall(r"(?m)^\s*Failed\s+(\d+)\s+mesh checks?\.\s*$", log)
    if summaries != ["1"]:
        raise ValueError(
            f"checkMesh failure summary must be exactly one failed check; got {summaries}"
        )

    proof_record = evidence.get("native_geometry_proof")
    if not isinstance(proof_record, dict) or not proof_record.get("path"):
        raise ValueError("mesh exception evidence must identify its native geometry proof")
    proof_path = Path(str(proof_record["path"]))
    if not proof_path.is_absolute():
        proof_path = evidence_path.parent / proof_path
    proof_path = proof_path.resolve(strict=True)
    proof_hash = sha256_file(proof_path)
    if proof_hash != proof_record.get("sha256"):
        raise ValueError("native geometry proof SHA256 does not match the supplied evidence")
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    plane = proof.get("supporting_plane_result", {})
    max_excursion = float(plane.get("max_outside_excursion_m", math.nan))
    if (
        plane.get("cells_with_two_sided_vertices") != 0
        or plane.get("faces_with_two_sided_vertices") != 0
        or not math.isfinite(max_excursion)
        or abs(max_excursion) > 1e-9
    ):
        raise ValueError(
            "native proof does not establish zero nonconvex supporting-plane violations"
        )
    flagged_count = int(re.search(r"number of cells: (\d+)$", expected_lines[0]).group(1))
    if int(proof.get("concave_cell_count", -1)) != flagged_count:
        raise ValueError("native geometry proof's checker-rule cell count differs from checkMesh")
    native_files = proof.get("native_graph_files")
    mesh_dir = case_dir / "constant" / "polyMesh"
    if not isinstance(native_files, dict):
        raise ValueError("native geometry proof lacks hashed native polyMesh inputs")
    current_hashes: dict[str, str] = {}
    for name in POLYMESH_FILES:
        record = native_files.get(name)
        if not isinstance(record, dict) or not record.get("sha256"):
            raise ValueError(f"native geometry proof lacks a hash for polyMesh/{name}")
        actual = sha256_file(mesh_dir / name)
        if actual != record["sha256"]:
            raise ValueError(f"native geometry proof does not match this mesh's {name}")
        current_hashes[name] = actual
    return {
        "status": "exploratory_planar_transition_exception_applied",
        "formal_quality_gate_pass": False,
        "expected_checkmesh_failure_lines": expected_lines,
        "native_geometry_proof": str(proof_path),
        "native_geometry_proof_sha256": proof_hash,
        "mesh_file_sha256": current_hashes,
        "supporting_plane_violations": 0,
        "concave_or_planar_transition_cells": flagged_count,
        "exception_evidence_sha256": sha256_file(evidence_path),
    }


def evaluate_checkmesh(
    *,
    return_code: int,
    log: str,
    case_dir: Path,
    expected_cells: int,
    exception_evidence: Path | None,
) -> dict[str, Any]:
    actual_cells = _check_mesh_cells(log)
    if actual_cells != expected_cells:
        raise ValueError(
            f"checkMesh reports {actual_cells} cells; metadata declares {expected_cells}"
        )
    flags = _failed_check_lines(log)
    failed_summary = re.findall(r"(?m)^\s*Failed\s+(\d+)\s+mesh checks?\.\s*$", log)
    fatal = bool(re.search(r"FOAM FATAL|FATAL(?:\s+IO)?\s+ERROR|Fatal error", log, re.I))
    if return_code == 0 and not fatal and not flags and not failed_summary and "Mesh OK." in log:
        return {
            "status": "strict_checkmesh_ok",
            "formal_quality_gate_pass": None,
            "cells": actual_cells,
            "failed_check_lines": [],
            "log_sha256": hashlib.sha256(log.encode()).hexdigest(),
        }
    if exception_evidence is None:
        raise ValueError(
            f"checkMesh did not pass strictly (exit={return_code}, fatal={fatal}); "
            f"failed check lines={flags}, summaries={failed_summary}"
        )
    if return_code not in {0, 1} or fatal:
        raise ValueError(f"checkMesh exception cannot cover exit={return_code} or fatal={fatal}")
    exception = validate_planar_exception(exception_evidence, case_dir, flags, log)
    exception.update(
        cells=actual_cells,
        checkmesh_exit_code=return_code,
        log_sha256=hashlib.sha256(log.encode()).hexdigest(),
    )
    return exception


def latest_common_analysis_checkpoint(
    case_dir: Path,
    ranks: int,
    fields: tuple[str, ...] = ("alpha.water", "U", "k", "epsilon", "nut"),
) -> dict[str, Any]:
    """Find common fields sufficient for analysis, not a restart-ready state."""
    rank_dirs: dict[int, Path] = {}
    for path in case_dir.glob("processor[0-9]*"):
        match = re.fullmatch(r"processor(\d+)", path.name)
        if match and path.is_dir():
            rank_dirs[int(match.group(1))] = path
    if sorted(rank_dirs) != list(range(ranks)):
        return {
            "status": "no_complete_common_analysis_checkpoint",
            "reason": f"expected ranks 0..{ranks - 1}; found {sorted(rank_dirs)}",
            "required_fields": list(fields),
            "checkpoint_classification": "analysis_only_not_restart_ready",
            "restart_ready": False,
        }
    by_rank: list[dict[float, Path]] = []
    for rank in range(ranks):
        candidates: dict[float, Path] = {}
        for path in rank_dirs[rank].iterdir():
            if not path.is_dir():
                continue
            try:
                value = float(path.name)
            except ValueError:
                continue
            if math.isfinite(value) and value >= 0:
                candidates[value] = path
        by_rank.append(candidates)
    shared = set(by_rank[0])
    for candidates in by_rank[1:]:
        shared.intersection_update(candidates)
    for value in sorted(shared, reverse=True):
        selected = [rank_times[value] for rank_times in by_rank]
        if len({directory.name for directory in selected}) != 1:
            continue
        if not all(
            all((directory / field).is_file() for field in fields) for directory in selected
        ):
            continue
        inventory = {
            (directory / field).relative_to(case_dir).as_posix(): sha256_file(directory / field)
            for directory in selected
            for field in fields
        }
        return {
            "status": "complete_common_all_rank_analysis_checkpoint",
            "checkpoint_classification": "analysis_only_not_restart_ready",
            "restart_ready": False,
            "time_s": value,
            "time_directory_names": [directory.name for directory in selected],
            "rank_count": ranks,
            "required_fields": list(fields),
            "analysis_field_file_count": len(inventory),
            "field_sha256": inventory,
        }
    return {
        "status": "no_complete_common_analysis_checkpoint",
        "reason": "no shared time contains all requested analysis fields on all ranks",
        "required_fields": list(fields),
        "checkpoint_classification": "analysis_only_not_restart_ready",
        "restart_ready": False,
    }


def solver_summary(log: str, horizon_s: float) -> dict[str, Any]:
    stages = {
        name: int(code)
        for name, code in re.findall(r"^NATIVE_VOF_STAGE_EXIT stage=(\w+) code=(\d+)$", log, re.M)
    }
    solver_start = 0
    decomp_marker = re.search(r"^NATIVE_VOF_STAGE_EXIT stage=decomposePar code=\d+$", log, re.M)
    if decomp_marker:
        solver_start = decomp_marker.end()
    solver_log = log[solver_start:]
    times = [
        _parse_float(token, label="solver time")
        for token in re.findall(r"^Time = " + TIME_TOKEN + r"$", solver_log, re.M)
    ]
    clocks = re.findall(r"ClockTime = ([0-9.eE+-]+) s", solver_log)
    last = times[-1] if times else None
    return {
        "stage_exit_codes": stages,
        "last_solver_time_s": last,
        "solver_step_count": len(times),
        "clock_time_s": _parse_float(clocks[-1], label="ClockTime") if clocks else None,
        "reached_requested_horizon": last is not None
        and math.isclose(last, horizon_s, rel_tol=0.0, abs_tol=1e-6),
        "fatal_error_observed": bool(
            re.search(
                r"FOAM FATAL|FATAL(?:\s+IO)?\s+ERROR|Floating point exception(?! trapping enabled)",
                log,
                re.I,
            )
        ),
    }


def mesh_check_command(run_dir: Path, case_dir: Path, image_id: str, memory_gib: int) -> list[str]:
    check_memory_gib = min(memory_gib, 16.0)
    shell = (
        "set +e +u; source /usr/lib/openfoam/openfoam2512/etc/bashrc; setup=$?; "
        "[ $setup -eq 0 ] || exit $setup; set -o pipefail; "
        "foamVersion > log.openfoam-version 2>&1 || exit $?; "
        "if checkMesh -allTopology -allGeometry > log.checkMesh 2>&1; then code=0; else code=$?; fi; cat log.checkMesh; "
        "printf 'NATIVE_VOF_STAGE_EXIT stage=checkMesh code=%s\\n' $code; exit $code"
    )
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        f"{run_dir.name}-checkmesh",
        "--cidfile",
        str(run_dir / "checkmesh.cid"),
        "--label",
        f"{CONTAINER_LABEL_RUN}={run_dir.name}",
        "--label",
        f"{CONTAINER_LABEL_STAGE}=checkMesh",
        "--cpus=1",
        f"--memory={check_memory_gib:g}g",
        f"--memory-swap={check_memory_gib:g}g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "OMP_NUM_THREADS=1",
        "--env",
        "OPENBLAS_NUM_THREADS=1",
        "--mount",
        f"type=bind,src={case_dir},dst=/case",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        image_id,
        "-lc",
        shell,
    ]


def solver_shell_script(ranks: int) -> str:
    return f"""set +e +u
source /usr/lib/openfoam/openfoam2512/etc/bashrc
setup=$?
[ "$setup" -eq 0 ] || exit "$setup"
set -eo pipefail
foamVersion
run_stage() {{
  stage="$1"; shift
  if "$@" > "log.$stage" 2>&1; then
    code=0
  else
    code=$?
  fi
  cat "log.$stage"
  printf 'NATIVE_VOF_STAGE_EXIT stage=%s code=%s\\n' "$stage" "$code"
  return "$code"
}}
run_stage decomposePar decomposePar
run_stage interIsoFoam mpirun -np {ranks} interIsoFoam -parallel
"""


def solver_command(
    run_dir: Path, case_dir: Path, image_id: str, ranks: int, memory_gib: int
) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--cidfile",
        str(run_dir / "container.cid"),
        "--name",
        run_dir.name,
        "--label",
        f"{CONTAINER_LABEL_RUN}={run_dir.name}",
        "--label",
        f"{CONTAINER_LABEL_STAGE}=solver",
        f"--cpus={ranks}",
        f"--memory={memory_gib:g}g",
        f"--memory-swap={memory_gib:g}g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "OMP_NUM_THREADS=1",
        "--env",
        "OPENBLAS_NUM_THREADS=1",
        "--mount",
        f"type=bind,src={case_dir},dst=/case",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        image_id,
        "-lc",
        solver_shell_script(ranks),
    ]


def copy_case(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite run case: {destination}")
    shutil.copytree(source, destination, symlinks=False)


def archive_preexisting_runtime_outputs(case_dir: Path, run_dir: Path) -> list[dict[str, str]]:
    """Move stale run logs/diagnostics out of the new case, preserving their bytes."""
    candidates = [
        case_dir / name
        for name in (
            "log.checkMesh",
            "log.openfoam-version",
            "log.decomposePar",
            "log.interIsoFoam",
            "postProcessing",
        )
        if (case_dir / name).exists()
    ]
    if not candidates:
        return []
    archive = run_dir / "preexisting-runtime-outputs"
    archive.mkdir(exist_ok=False)
    inventory: list[dict[str, str]] = []
    for source in candidates:
        relative = source.relative_to(case_dir).as_posix()
        destination = archive / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            digest = hashlib.sha256(
                json.dumps(tree_hashes(source), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        else:
            digest = sha256_file(source)
        shutil.move(str(source), str(destination))
        inventory.append(
            {
                "original_case_path": relative,
                "preserved_path": str(destination.relative_to(run_dir)),
                "sha256_or_tree_sha256": digest,
            }
        )
    return inventory


def preserve_mesh_exception_evidence(source: Path, run_dir: Path) -> dict[str, Any]:
    """Bundle the supplied evidence and its geometry proof as frozen run inputs."""
    source = source.resolve(strict=True)
    evidence = json.loads(source.read_text(encoding="utf-8"))
    proof_record = evidence.get("native_geometry_proof")
    if not isinstance(proof_record, dict) or not proof_record.get("path"):
        raise ValueError("mesh exception evidence must identify a native geometry proof")
    proof_source = Path(str(proof_record["path"]))
    if not proof_source.is_absolute():
        proof_source = source.parent / proof_source
    proof_source = proof_source.resolve(strict=True)
    proof_source_hash = sha256_file(proof_source)
    if proof_source_hash != proof_record.get("sha256"):
        raise ValueError("native geometry proof SHA256 differs from supplied evidence")

    proof_bundle = run_dir / "native_geometry_proof.json"
    shutil.copy2(proof_source, proof_bundle)
    bundled_evidence = dict(evidence)
    bundled_proof = dict(proof_record)
    bundled_proof["path"] = proof_bundle.name
    bundled_evidence["native_geometry_proof"] = bundled_proof
    evidence_bundle = run_dir / "mesh-quality-exception-evidence.json"
    _atomic_json(evidence_bundle, bundled_evidence)
    return {
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "bundle_evidence_path": evidence_bundle.name,
        "bundle_evidence_sha256": sha256_file(evidence_bundle),
        "source_geometry_proof_path": str(proof_source),
        "geometry_proof_sha256": proof_source_hash,
        "bundle_geometry_proof_path": proof_bundle.name,
        "bundle_geometry_proof_sha256": sha256_file(proof_bundle),
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _doctor(run_dir: Path) -> dict[str, Any]:
    output = run_dir / "machine.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/doctor.py"), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not output.is_file():
        raise RunnerError(f"doctor failed ({result.returncode}): {result.stdout}{result.stderr}")
    return json.loads(output.read_text(encoding="utf-8"))


def _docker_activity_snapshot() -> dict[str, Any]:
    """Measure running Docker CPU use while identifying paused/stopped containers."""
    listing = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--no-trunc",
            "--format",
            "{{.ID}}|{{.Names}}|{{.Status}}",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    containers: list[dict[str, str]] = []
    for line in listing.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            raise RunnerError(f"could not parse docker ps row: {line!r}")
        container_id, name, status = parts
        containers.append({"id": container_id, "name": name, "status": status})

    running = [
        row
        for row in containers
        if row["status"].startswith("Up") and "(Paused)" not in row["status"]
    ]
    paused = [row for row in containers if "(Paused)" in row["status"]]
    stats_by_name: dict[str, dict[str, Any]] = {}
    if running:
        stats = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}",
                *[row["name"] for row in running],
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        for line in stats.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) != 3:
                raise RunnerError(f"could not parse docker stats row: {line!r}")
            name, cpu_text, memory_text = parts
            match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)%\s*", cpu_text)
            if match is None:
                raise RunnerError(f"could not parse Docker CPU sample {cpu_text!r} for {name}")
            stats_by_name[name] = {
                "cpu_percent": float(match.group(1)),
                "cpu_equivalents": float(match.group(1)) / 100.0,
                "memory_usage": memory_text,
            }
    missing_stats = sorted(row["name"] for row in running if row["name"] not in stats_by_name)
    if missing_stats:
        raise RunnerError(f"Docker CPU sample missing for running containers: {missing_stats}")
    return {
        "containers": containers,
        "running_containers": running,
        "paused_containers": paused,
        "container_status_by_id": {row["id"]: row["status"] for row in containers},
        "running_container_usage": [{**row, **stats_by_name[row["name"]]} for row in running],
        "running_container_cpu_equivalents": sum(
            value["cpu_equivalents"] for value in stats_by_name.values()
        ),
    }


def _pid_docker_container_id(pid: int) -> str | None:
    try:
        cgroup = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"(?:docker-|/docker/)([0-9a-f]{64})(?:\.scope)?", cgroup)
    return match.group(1) if match else None


def _current_solver_processes(
    docker_container_status: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return active non-Docker OpenFOAM processes with measured CPU use.

    Docker-contained processes are accounted through docker stats. T/t,
    zombie, and exited processes consume no measured CPU and are omitted.
    """
    container_status = docker_container_status or {}
    result = subprocess.run(
        ["ps", "-eo", "pid=,comm=,stat=,pcpu="],
        capture_output=True,
        text=True,
        check=True,
    )
    active: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 4 or not fields[0].isdigit() or fields[1] not in SOLVER_PROCESS_NAMES:
            continue
        pid, command, state, cpu_text = fields
        if state[0] in {"T", "t", "Z", "X"}:
            continue
        docker_id = _pid_docker_container_id(int(pid))
        if docker_id is not None and docker_id in container_status:
            # Running containers are represented by docker stats; paused and
            # stopped containers are deliberately excluded from measured use.
            continue
        try:
            cpu_percent = float(cpu_text)
        except ValueError as error:
            raise RunnerError(
                f"could not parse ps CPU sample {cpu_text!r} for PID {pid}"
            ) from error
        active.append(
            {
                "pid": int(pid),
                "command": command,
                "state": state,
                "cpu_percent": cpu_percent,
                "cpu_equivalents": cpu_percent / 100.0,
                "docker_container_id": docker_id,
            }
        )
    return active


def _validate_capacity(doctor: dict[str, Any], *, ranks: int, memory_gib: int) -> dict[str, Any]:
    resources = doctor.get("resources", {})
    cpu = resources.get("cpu", {})
    memory = resources.get("memory", {})
    effective = float(cpu.get("effective", 0))
    total_bytes = int(memory.get("total_bytes") or 0)
    if effective < ranks:
        raise RunnerError(f"requested {ranks} ranks exceed effective CPU capacity {effective}")
    if total_bytes and memory_gib * 1024**3 > total_bytes:
        raise RunnerError("requested container memory limit exceeds host physical memory")
    activity = _docker_activity_snapshot()
    active = _current_solver_processes(activity["container_status_by_id"])
    docker_cpu = float(activity["running_container_cpu_equivalents"])
    host_solver_cpu = sum(float(row["cpu_equivalents"]) for row in active)
    measured_competing_cpu = docker_cpu + host_solver_cpu
    available = max(0.0, effective - measured_competing_cpu)
    if ranks > available + 1e-6:
        raise RunnerError(
            f"requested {ranks} CPU equivalents exceed measured shared capacity "
            f"{available:.3f} of {effective:g}; current Docker use={docker_cpu:.3f}, "
            f"host OpenFOAM utility use={host_solver_cpu:.3f} CPU equivalents"
        )
    return {
        "effective_cpu_count": effective,
        "host_memory_total_bytes": total_bytes or None,
        "host_memory_available_bytes": memory.get("effective_available_bytes"),
        "requested_cpu_equivalents": ranks,
        "measured_competing_cpu_equivalents": measured_competing_cpu,
        "estimated_shared_cpu_capacity_available": available,
        "active_docker_cpu_equivalents": docker_cpu,
        "running_container_usage": activity["running_container_usage"],
        "paused_containers_excluded_from_cpu_load": activity["paused_containers"],
        "active_uncontainerized_solver_or_mesh_processes": active,
        "capacity_method": "effective CPU count minus one-shot docker stats and active host OpenFOAM ps CPU samples",
        "requested_ranks": ranks,
        "requested_memory_limit_gib": memory_gib,
    }


def _inspect_pinned_image() -> str:
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE],
        capture_output=True,
        text=True,
        check=True,
    )
    image_id = result.stdout.strip()
    if image_id != PINNED_IMAGE_ID:
        raise RunnerError(
            f"pinned OpenFOAM image ID mismatch: expected {PINNED_IMAGE_ID}, got {image_id}"
        )
    return image_id


def _code_provenance() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    scripts = (
        "scripts/run_native_vof_case.py",
        "scripts/audit_iso_vof_ledger.py",
        "scripts/export_native_vof.py",
        "scripts/analyze_native_vof.py",
        "scripts/run_local.py",
    )
    return {
        "git_revision": revision,
        "git_dirty": dirty,
        "script_sha256": {
            relative: sha256_file(ROOT / relative)
            for relative in scripts
            if (ROOT / relative).is_file()
        },
    }


def _inspect_container(container_id: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{json .}}", container_id],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        absent = "no such object" in result.stderr.lower()
        return {
            "exists": False if absent else None,
            "inspection_error": result.stderr.strip(),
            "return_code": result.returncode,
        }
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return {"exists": None, "inspection_error": f"invalid docker inspect JSON: {error}"}
    return {
        "exists": True,
        "id": str(raw.get("Id", "")),
        "name": str(raw.get("Name", "")).lstrip("/"),
        "image_id": raw.get("Image"),
        "configured_image": raw.get("Config", {}).get("Image"),
        "labels": raw.get("Config", {}).get("Labels") or {},
        "mounts": raw.get("Mounts") or [],
        "state": raw.get("State") or {},
    }


def _owned_container_matches(
    inspection: dict[str, Any],
    *,
    container_id: str,
    run_id: str,
    stage: str,
    case_dir: Path,
    image_id: str,
) -> tuple[bool, dict[str, Any]]:
    mounts = inspection.get("mounts", [])
    case_mounts = [
        row
        for row in mounts
        if row.get("Destination") == "/case"
        and Path(str(row.get("Source", ""))).resolve() == case_dir.resolve()
    ]
    checks = {
        "full_id_matches_cidfile": inspection.get("id") == container_id,
        "run_label_matches": inspection.get("labels", {}).get(CONTAINER_LABEL_RUN) == run_id,
        "stage_label_matches": inspection.get("labels", {}).get(CONTAINER_LABEL_STAGE) == stage,
        "image_id_matches": inspection.get("image_id") == image_id,
        "case_mount_matches": bool(case_mounts),
    }
    return all(checks.values()), checks


def _ensure_owned_container_stopped_impl(
    run_dir: Path, *, stage: str, case_dir: Path, image_id: str
) -> dict[str, Any]:
    """Stop only a full CID whose image, labels, and case mount match this run."""
    cid_filename = "checkmesh.cid" if stage == "checkMesh" else "container.cid"
    cid_path = run_dir / cid_filename
    lifecycle_path = run_dir / f"container-lifecycle-{stage}.json"
    attempts: list[dict[str, Any]] = []
    record: dict[str, Any] = {
        "schema": "dash8-owned-container-lifecycle-v1",
        "run_id": run_dir.name,
        "stage": stage,
        "cidfile": cid_filename,
        "attempts": attempts,
    }
    if not cid_path.is_file():
        record.update(
            status="no_cidfile_no_container_claimed",
            ownership_verified=False,
            cleanup_attempted=False,
            stopped_verified=None,
        )
        _atomic_json(lifecycle_path, record)
        return record

    container_id = cid_path.read_text(encoding="ascii", errors="strict").strip().lower()
    record["cidfile_sha256"] = sha256_file(cid_path)
    if not re.fullmatch(r"[0-9a-f]{64}", container_id):
        record.update(
            status="invalid_cidfile",
            ownership_verified=False,
            cleanup_attempted=False,
            stopped_verified=None,
        )
        _atomic_json(lifecycle_path, record)
        return record
    record["container_id"] = container_id

    def inspect_and_check() -> tuple[dict[str, Any], bool, dict[str, Any]]:
        inspection = _inspect_container(container_id)
        if inspection.get("exists") is False:
            return inspection, True, {"cidfile_identifies_container": True}
        if inspection.get("exists") is not True:
            return inspection, False, {"inspect_succeeded": False}
        matched, checks = _owned_container_matches(
            inspection,
            container_id=container_id,
            run_id=run_dir.name,
            stage=stage,
            case_dir=case_dir,
            image_id=image_id,
        )
        return inspection, matched, checks

    try:
        inspection, owned, identity_checks = inspect_and_check()
        record["initial_inspection"] = inspection
        record["identity_checks"] = identity_checks
        if not owned:
            record.update(
                status="ownership_unverified_no_stop_attempted",
                ownership_verified=False,
                cleanup_attempted=False,
                stopped_verified=False,
            )
        elif inspection.get("exists") is False:
            record.update(
                status="container_already_absent_by_owned_cid",
                ownership_verified=True,
                cleanup_attempted=False,
                stopped_verified=True,
            )
        elif not bool(inspection.get("state", {}).get("Running")):
            record.update(
                status="owned_container_already_stopped",
                ownership_verified=True,
                cleanup_attempted=False,
                stopped_verified=True,
            )
        else:
            record["ownership_verified"] = True
            for action in ("stop", "kill"):
                try:
                    command = (
                        ["docker", "stop", "--time", "30", container_id]
                        if action == "stop"
                        else ["docker", "kill", container_id]
                    )
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=45 if action == "stop" else 15,
                        check=False,
                    )
                    attempts.append(
                        {
                            "action": action,
                            "return_code": result.returncode,
                            "stdout": result.stdout.strip(),
                            "stderr": result.stderr.strip(),
                            "target_full_id": container_id,
                        }
                    )
                except Exception as error:
                    attempts.append(
                        {
                            "action": action,
                            "target_full_id": container_id,
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
                final_inspection, still_owned, final_checks = inspect_and_check()
                record["latest_inspection"] = final_inspection
                record["latest_identity_checks"] = final_checks
                if final_inspection.get("exists") is False:
                    record.update(
                        status="owned_container_removed_after_stop",
                        cleanup_attempted=True,
                        stopped_verified=True,
                    )
                    break
                if still_owned and not bool(final_inspection.get("state", {}).get("Running")):
                    record.update(
                        status="owned_container_stopped_and_verified",
                        cleanup_attempted=True,
                        stopped_verified=True,
                    )
                    break
                if not still_owned:
                    record.update(
                        status="ownership_lost_during_cleanup_no_further_stop",
                        cleanup_attempted=True,
                        stopped_verified=False,
                    )
                    break
            else:
                record.update(
                    status="owned_container_still_running_after_cleanup_attempts",
                    cleanup_attempted=True,
                    stopped_verified=False,
                )
    except RunnerTermination:
        raise
    except Exception as error:
        record.update(
            status="container_cleanup_error",
            cleanup_error=f"{type(error).__name__}: {error}",
            stopped_verified=False,
        )
    _atomic_json(lifecycle_path, record)
    return record


def _ensure_owned_container_stopped(
    run_dir: Path, *, stage: str, case_dir: Path, image_id: str
) -> dict[str, Any]:
    with _defer_termination_during_cleanup():
        return _ensure_owned_container_stopped_impl(
            run_dir, stage=stage, case_dir=case_dir, image_id=image_id
        )


def _reap_docker_client(process: subprocess.Popen[bytes] | None) -> dict[str, Any]:
    if process is None:
        return {"status": "not_started", "return_code": None, "forced_kill": False}
    if process.poll() is not None:
        return {
            "status": "exited",
            "return_code": process.returncode,
            "forced_kill": False,
        }
    try:
        return_code = process.wait(timeout=60)
        return {"status": "reaped_after_cleanup", "return_code": return_code, "forced_kill": False}
    except subprocess.TimeoutExpired:
        process.kill()
        return_code = process.wait()
        return {
            "status": "killed_after_cleanup_timeout",
            "return_code": return_code,
            "forced_kill": True,
        }


def run_checkmesh(
    command: list[str],
    *,
    run_dir: Path,
    case_dir: Path,
    image_id: str,
    timeout_s: float = 1200.0,
) -> dict[str, Any]:
    started = time.monotonic()
    timeout = False
    interrupted = False
    stop_attempt: dict[str, Any] | None = None
    termination_signal: int | None = None
    console_path = case_dir.parent / "checkmesh-container.log"
    process: subprocess.Popen[bytes] | None = None
    result_code = 1
    try:
        with console_path.open("wb") as console:
            process = subprocess.Popen(command, stdout=console, stderr=subprocess.STDOUT)
            try:
                result_code = process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timeout = True
                stop_attempt = _ensure_owned_container_stopped(
                    run_dir, stage="checkMesh", case_dir=case_dir, image_id=image_id
                )
                try:
                    result_code = process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    process.kill()
                    result_code = process.wait()
            except RunnerTermination as error:
                interrupted = True
                termination_signal = error.signum
                stop_attempt = _ensure_owned_container_stopped(
                    run_dir, stage="checkMesh", case_dir=case_dir, image_id=image_id
                )
                try:
                    process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            except KeyboardInterrupt:
                interrupted = True
                stop_attempt = _ensure_owned_container_stopped(
                    run_dir, stage="checkMesh", case_dir=case_dir, image_id=image_id
                )
                try:
                    process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    except RunnerTermination as error:
        interrupted = True
        termination_signal = error.signum
        stop_attempt = _ensure_owned_container_stopped(
            run_dir, stage="checkMesh", case_dir=case_dir, image_id=image_id
        )
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    except KeyboardInterrupt:
        interrupted = True
        stop_attempt = _ensure_owned_container_stopped(
            run_dir, stage="checkMesh", case_dir=case_dir, image_id=image_id
        )
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    finally:
        try:
            cleanup = _ensure_owned_container_stopped(
                run_dir, stage="checkMesh", case_dir=case_dir, image_id=image_id
            )
        finally:
            client_reap = _reap_docker_client(process)
            cleanup = _ensure_owned_container_stopped(
                run_dir, stage="checkMesh", case_dir=case_dir, image_id=image_id
            )
    if timeout:
        result_code = 124
    elif interrupted:
        result_code = 128 + termination_signal if termination_signal else 130
    elif process is None or process.returncode is None:
        result_code = 1
    elif process.returncode != 0:
        result_code = int(process.returncode)
    if cleanup.get("stopped_verified") is not True and result_code == 0:
        result_code = 1
    log_path = case_dir / "log.checkMesh"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    version_path = case_dir / "log.openfoam-version"
    return {
        "return_code": result_code,
        "timed_out": timeout,
        "interrupted": interrupted,
        "termination_signal": termination_signal,
        "container_stop_attempt": stop_attempt,
        "container_cleanup": cleanup,
        "container_cleanup_verified": cleanup.get("stopped_verified") is True,
        "docker_client_process": client_reap,
        "elapsed_s": time.monotonic() - started,
        "log": log,
        "console_log": str(console_path),
        "version": version_path.read_text(encoding="utf-8", errors="replace").strip()
        if version_path.is_file()
        else None,
    }


def run_solver(
    command: list[str],
    *,
    run_dir: Path,
    case_dir: Path,
    image_id: str,
    timeout_s: float,
) -> dict[str, Any]:
    console_path = run_dir / "openfoam-console.log"
    started = time.monotonic()
    timed_out = False
    interrupted = False
    termination_signal: int | None = None
    stop_attempt: dict[str, Any] | None = None
    process: subprocess.Popen[bytes] | None = None
    launcher_error: str | None = None
    try:
        with console_path.open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            with (run_dir / "resources.jsonl").open("w", encoding="utf-8") as resources:
                while process.poll() is None:
                    remaining = timeout_s - (time.monotonic() - started)
                    if remaining <= 0:
                        timed_out = True
                        stop_attempt = _ensure_owned_container_stopped(
                            run_dir, stage="solver", case_dir=case_dir, image_id=image_id
                        )
                        try:
                            process.wait(timeout=60)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        break
                    try:
                        process.wait(timeout=min(30.0, remaining))
                    except subprocess.TimeoutExpired:
                        elapsed = time.monotonic() - started
                        sample_record: dict[str, Any]
                        try:
                            sample = subprocess.run(
                                [
                                    "docker",
                                    "stats",
                                    "--no-stream",
                                    "--format",
                                    "{{json .}}",
                                    run_dir.name,
                                ],
                                capture_output=True,
                                text=True,
                                timeout=20,
                                check=False,
                            )
                            sample_record = {"docker_stats": sample.stdout.strip()}
                        except RunnerTermination as error:
                            interrupted = True
                            termination_signal = error.signum
                            stop_attempt = _ensure_owned_container_stopped(
                                run_dir, stage="solver", case_dir=case_dir, image_id=image_id
                            )
                            try:
                                process.wait(timeout=60)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                            break
                        except KeyboardInterrupt:
                            interrupted = True
                            stop_attempt = _ensure_owned_container_stopped(
                                run_dir, stage="solver", case_dir=case_dir, image_id=image_id
                            )
                            try:
                                process.wait(timeout=60)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                            break
                        except Exception as error:
                            sample_record = {
                                "docker_stats_error": f"{type(error).__name__}: {error}"
                            }
                        resources.write(
                            json.dumps(
                                {
                                    "utc": utc_now(),
                                    "elapsed_s": elapsed,
                                    **sample_record,
                                }
                            )
                            + "\n"
                        )
                        resources.flush()
                    except RunnerTermination as error:
                        interrupted = True
                        termination_signal = error.signum
                        stop_attempt = _ensure_owned_container_stopped(
                            run_dir, stage="solver", case_dir=case_dir, image_id=image_id
                        )
                        try:
                            process.wait(timeout=60)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        break
                    except KeyboardInterrupt:
                        interrupted = True
                        stop_attempt = _ensure_owned_container_stopped(
                            run_dir, stage="solver", case_dir=case_dir, image_id=image_id
                        )
                        try:
                            process.wait(timeout=60)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        break
    except RunnerTermination as error:
        interrupted = True
        termination_signal = error.signum
        stop_attempt = _ensure_owned_container_stopped(
            run_dir, stage="solver", case_dir=case_dir, image_id=image_id
        )
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    except KeyboardInterrupt:
        interrupted = True
        stop_attempt = _ensure_owned_container_stopped(
            run_dir, stage="solver", case_dir=case_dir, image_id=image_id
        )
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    except Exception as error:
        launcher_error = f"{type(error).__name__}: {error}"
    finally:
        try:
            cleanup = _ensure_owned_container_stopped(
                run_dir, stage="solver", case_dir=case_dir, image_id=image_id
            )
        finally:
            client_reap = _reap_docker_client(process)
            cleanup = _ensure_owned_container_stopped(
                run_dir, stage="solver", case_dir=case_dir, image_id=image_id
            )
    if timed_out:
        code = 124
    elif interrupted:
        code = 128 + termination_signal if termination_signal else 130
    elif process is None:
        code = 1
    else:
        code = int(process.returncode or 0)
    if cleanup.get("stopped_verified") is not True and code == 0:
        code = 1
    if launcher_error is not None:
        code = 1
    cid_path = run_dir / "container.cid"
    return {
        "return_code": code,
        "timed_out": timed_out,
        "interrupted": interrupted,
        "termination_signal": termination_signal,
        "launcher_error": launcher_error,
        "container_stop_attempt": stop_attempt,
        "container_cleanup": cleanup,
        "container_cleanup_verified": cleanup.get("stopped_verified") is True,
        "docker_client_process": client_reap,
        "elapsed_s": time.monotonic() - started,
        "container_id": cid_path.read_text().strip() if cid_path.is_file() else None,
        "console_log": str(console_path),
        "console": console_path.read_text(encoding="utf-8", errors="replace"),
    }


def run_postprocessors(
    run_dir: Path, *, ranks: int, horizon_s: float, source_patch: str
) -> dict[str, Any]:
    """Run ledger and native-topology observers without changing solver status."""
    case_dir = run_dir / "case"
    post_dir = run_dir / "analytics"
    post_dir.mkdir(exist_ok=False)
    report: dict[str, Any] = {"status": "running", "observers": {}}
    commands = {
        "water_ledger": [
            sys.executable,
            str(ROOT / "scripts/audit_iso_vof_ledger.py"),
            "--run-dir",
            str(run_dir),
            "--output-dir",
            str(post_dir / "water-ledger"),
            "--end-time-s",
            f"{horizon_s:.12g}",
        ],
    }
    time_record = latest_common_analysis_checkpoint(case_dir, ranks, fields=("alpha.water", "U"))
    if time_record.get("status") == "complete_common_all_rank_analysis_checkpoint" and math.isclose(
        float(time_record["time_s"]), horizon_s, rel_tol=0.0, abs_tol=1e-6
    ):
        snapshot_time = time_record["time_directory_names"][0]
        export_dir = post_dir / "native-export"
        analysis_dir = post_dir / "native-analysis"
        commands["native_export"] = [
            sys.executable,
            str(ROOT / "scripts/export_native_vof.py"),
            "--case-dir",
            str(case_dir),
            "--time",
            snapshot_time,
            "--output-dir",
            str(export_dir),
            "--source-patch",
            source_patch,
            "--mpi-ranks",
            str(ranks),
        ]
        commands["native_analysis"] = [
            sys.executable,
            str(ROOT / "scripts/analyze_native_vof.py"),
            "--export-dir",
            str(export_dir / "raw"),
            "--output-dir",
            str(analysis_dir),
        ]
        report["native_analysis_checkpoint"] = time_record
    else:
        report["native_analysis_checkpoint"] = time_record
        report["observers"]["native_export"] = {
            "status": "not_attempted_missing_terminal_checkpoint",
            "reason": "exact requested-horizon analysis fields alpha.water/U are not present on every rank",
        }
        report["observers"]["native_analysis"] = {
            "status": "not_attempted_export_unavailable",
            "reason": "native export did not run without the exact terminal checkpoint",
        }

    for name, command in commands.items():
        if (
            name == "native_analysis"
            and report["observers"].get("native_export", {}).get("status") != "completed"
        ):
            report["observers"][name] = {
                "status": "not_attempted_export_unavailable",
                "reason": "native export did not complete",
            }
            continue
        log_path = post_dir / f"{name}.log"
        wrapped = [
            sys.executable,
            str(ROOT / "scripts/run_local.py"),
            "--threads",
            "1",
            "--",
            *command,
        ]
        try:
            result = subprocess.run(wrapped, cwd=ROOT, capture_output=True, text=True, check=False)
            log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
            report["observers"][name] = {
                "status": "completed" if result.returncode == 0 else "failed",
                "exit_code": result.returncode,
                "command": wrapped,
                "log": str(log_path),
            }
        except RunnerTermination as error:
            log_path.write_text(f"RunnerTermination: {error}\n", encoding="utf-8")
            report["observers"][name] = {
                "status": "interrupted",
                "error": str(error),
                "command": wrapped,
                "log": str(log_path),
            }
            report["status"] = "interrupted"
            report["solver_status_unchanged_by_observers"] = True
            report["finished_utc"] = utc_now()
            _atomic_json(post_dir / "postprocess.json", report)
            raise
        except Exception as error:  # preserve an observer failure without changing CFD result
            log_path.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
            report["observers"][name] = {
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
                "command": wrapped,
                "log": str(log_path),
            }
    states = [row["status"] for row in report["observers"].values()]
    report["status"] = (
        "completed"
        if states and all(state == "completed" for state in states)
        else "failed_or_incomplete"
    )
    report["solver_status_unchanged_by_observers"] = True
    report["finished_utc"] = utc_now()
    _atomic_json(post_dir / "postprocess.json", report)
    return report


def _save_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_utc"] = utc_now()
    _atomic_json(run_dir / "manifest.json", manifest)


def run_case(
    *,
    case_dir: Path,
    run_id: str,
    ranks: int,
    memory_gib: int,
    timeout_s: float,
    mesh_quality_exception_evidence: Path | None = None,
    postprocess: bool = True,
) -> tuple[int, Path]:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run-id must use lowercase letters, digits and hyphens")
    if not isinstance(ranks, int) or ranks < 1:
        raise ValueError("ranks must be a positive integer")
    if not isinstance(memory_gib, int) or isinstance(memory_gib, bool) or memory_gib < 4:
        raise ValueError("memory-gib must be finite and at least 4 for the pinned mesh utility")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout-s must be positive and finite")

    prepared = validate_prepared_case(case_dir, ranks=ranks)
    source_dir = Path(prepared["case_directory"])
    run_dir = ROOT / "results" / "runs" / run_id
    if run_dir.exists():
        raise FileExistsError(f"run directory already exists: {run_dir}")
    if source_dir == run_dir or run_dir in source_dir.parents:
        raise ValueError("run directory must be outside the prepared source case")
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "schema": "dash8-native-vof-run-v1",
        "run_id": run_id,
        "created_utc": utc_now(),
        "updated_utc": utc_now(),
        "classification": "exploratory static-polyhedral interIsoFoam trial; no E2/E0 gate decision",
        "solver_status": "preparing",
        "postprocess_status": "not_attempted",
        "prepared_case": prepared,
        "prepared_source_input_sha256": prepared["input_file_sha256"],
        "prepared_source_input_bytes": prepared["input_tree_bytes"],
        "code_provenance": _code_provenance(),
        "solver_image": IMAGE,
        "solver_image_id": None,
        "openfoam_version": None,
        "allocation": {
            "mpi_ranks": ranks,
            "docker_cpus": ranks,
            "memory_gib_max": memory_gib,
            "solver_timeout_s": timeout_s,
        },
        "mesh_quality_exception": None,
        "stages": [],
        "mesh_generators_invoked": {"blockMesh": False, "snappyHexMesh": False},
        "solver_commands": [
            "checkMesh -allTopology -allGeometry",
            "decomposePar",
            "mpirun -np N interIsoFoam -parallel",
        ],
        "postprocessing": "separate from solver_status; native waterVolume/alphaPhi ledger and native-topology export/analyzer are attempted after a completed solver run",
        "resource_sampling": {
            "docker_stats_interval_s": 30,
            "note": "Container statistics are periodic samples; peaks between samples may be higher.",
        },
    }
    manifest_path = run_dir / "manifest.json"
    _save_manifest(run_dir, manifest)

    try:
        machine = _doctor(run_dir)
        manifest["machine_report"] = str(run_dir / "machine.json")
        manifest["capacity_preflight"] = _validate_capacity(
            machine, ranks=ranks, memory_gib=memory_gib
        )
        disk_free = machine.get("resources", {}).get("disk", {}).get("free_bytes")
        required_free = max(16 * 1024**3, int(prepared["input_tree_bytes"]) * 2)
        if disk_free is not None and int(disk_free) < required_free:
            raise RunnerError(
                f"available disk {int(disk_free)} bytes is below the preflight floor {required_free} bytes"
            )
        manifest["capacity_preflight"]["disk_free_bytes"] = disk_free
        manifest["capacity_preflight"]["minimum_free_disk_floor_bytes"] = required_free
        manifest["solver_image_id"] = _inspect_pinned_image()
        _save_manifest(run_dir, manifest)

        copy_case(source_dir, run_dir / "case")
        run_case_dir = run_dir / "case"
        copied_hashes = tree_hashes(run_case_dir)
        if copied_hashes != manifest["prepared_source_input_sha256"]:
            raise RunnerError("copied input tree does not match the frozen prepared source")
        manifest["run_case_initial_sha256"] = copied_hashes
        _atomic_json(run_dir / "case-input-sha256.json", copied_hashes)
        manifest["preexisting_runtime_outputs_archived"] = archive_preexisting_runtime_outputs(
            run_case_dir, run_dir
        )
        if mesh_quality_exception_evidence is not None:
            manifest["mesh_quality_exception_evidence"] = preserve_mesh_exception_evidence(
                mesh_quality_exception_evidence, run_dir
            )
        _save_manifest(run_dir, manifest)

        check_timeout = min(1200.0, timeout_s)
        check_result = run_checkmesh(
            mesh_check_command(run_dir, run_case_dir, manifest["solver_image_id"], memory_gib),
            run_dir=run_dir,
            case_dir=run_case_dir,
            image_id=manifest["solver_image_id"],
            timeout_s=check_timeout,
        )
        manifest["openfoam_version"] = check_result.get("version")
        manifest["mesh_check_attempt"] = {
            "return_code": int(check_result["return_code"]),
            "timed_out": bool(check_result.get("timed_out", False)),
            "interrupted": bool(check_result.get("interrupted", False)),
            "elapsed_s": check_result.get("elapsed_s"),
            "log_path": str(run_case_dir / "log.checkMesh"),
            "log_sha256": hashlib.sha256(str(check_result["log"]).encode()).hexdigest(),
            "failed_check_lines": _failed_check_lines(str(check_result["log"])),
            "console_log": check_result.get("console_log"),
            "container_stop_attempt": check_result.get("container_stop_attempt"),
            "container_cleanup": check_result.get("container_cleanup"),
            "container_cleanup_verified": check_result.get("container_cleanup_verified"),
            "termination_signal": check_result.get("termination_signal"),
        }
        _save_manifest(run_dir, manifest)
        if check_result.get("container_cleanup_verified") is not True:
            raise RunnerError(
                "checkMesh container stopped state could not be verified; solver not started"
            )
        if check_result.get("timed_out") or check_result.get("interrupted"):
            raise RunnerError(
                "checkMesh was interrupted or timed out; preserved its attempt and did not start solver"
            )
        check_record = evaluate_checkmesh(
            return_code=int(check_result["return_code"]),
            log=str(check_result["log"]),
            case_dir=run_case_dir,
            expected_cells=int(prepared["expected_mesh_cells"]),
            exception_evidence=(
                run_dir / "mesh-quality-exception-evidence.json"
                if mesh_quality_exception_evidence is not None
                else None
            ),
        )
        manifest["mesh_check"] = check_record
        if check_record.get("status") == "exploratory_planar_transition_exception_applied":
            manifest["mesh_quality_exception"] = check_record
        manifest["stages"].append({"stage": "checkMesh", "utc": utc_now(), **check_record})
        manifest["solver_status"] = "decomposing"
        _save_manifest(run_dir, manifest)

        manifest["solver_status"] = "running"
        manifest["solver_started_utc"] = utc_now()
        _save_manifest(run_dir, manifest)
        solver_result = run_solver(
            solver_command(run_dir, run_case_dir, manifest["solver_image_id"], ranks, memory_gib),
            run_dir=run_dir,
            case_dir=run_case_dir,
            image_id=manifest["solver_image_id"],
            timeout_s=timeout_s,
        )
        summary = solver_summary(solver_result["console"], prepared["horizon_s"])
        manifest["container_id"] = solver_result.get("container_id")
        manifest["solver_exit_code"] = int(solver_result["return_code"])
        manifest["solver_timed_out"] = bool(solver_result["timed_out"])
        manifest["solver_interrupted"] = bool(solver_result.get("interrupted", False))
        manifest["solver_termination_signal"] = solver_result.get("termination_signal")
        manifest["solver_container_stop_attempt"] = solver_result.get("container_stop_attempt")
        manifest["solver_container_cleanup"] = solver_result.get("container_cleanup")
        manifest["solver_container_cleanup_verified"] = solver_result.get(
            "container_cleanup_verified"
        )
        if solver_result.get("launcher_error"):
            manifest["solver_launcher_error"] = solver_result["launcher_error"]
        manifest["solver_elapsed_s"] = solver_result["elapsed_s"]
        manifest["solver_log"] = solver_result["console_log"]
        manifest["solver_summary"] = summary
        manifest["latest_common_analysis_checkpoint"] = latest_common_analysis_checkpoint(
            run_case_dir, ranks
        )
        if not solver_result.get("container_cleanup_verified"):
            manifest["solver_status"] = "container_cleanup_unverified_checkpoint_preserved"
        elif solver_result["timed_out"]:
            manifest["solver_status"] = "wall_timeout_checkpoint_preserved"
        elif solver_result.get("interrupted"):
            manifest["solver_status"] = "interrupted_checkpoint_preserved"
        elif (
            solver_result["return_code"] == 0
            and summary["stage_exit_codes"].get("decomposePar") == 0
            and summary["stage_exit_codes"].get("interIsoFoam") == 0
            and summary["reached_requested_horizon"]
            and not summary["fatal_error_observed"]
        ):
            manifest["solver_status"] = "completed_at_requested_horizon"
        else:
            manifest["solver_status"] = "failed_or_incomplete_checkpoint_preserved"
        source_after = tree_hashes(source_dir)
        manifest["prepared_source_input_unchanged"] = (
            source_after == manifest["prepared_source_input_sha256"]
        )
        if not manifest["prepared_source_input_unchanged"]:
            manifest["prepared_source_input_sha256_after"] = source_after
        _save_manifest(run_dir, manifest)

        if postprocess and manifest["solver_status"] == "completed_at_requested_horizon":
            try:
                post_report = run_postprocessors(
                    run_dir,
                    ranks=ranks,
                    horizon_s=prepared["horizon_s"],
                    source_patch=str(prepared["case_inputs"]["source_patches"][0]),
                )
                manifest["postprocess_status"] = post_report["status"]
                manifest["postprocess_report"] = str(run_dir / "analytics/postprocess.json")
            except RunnerTermination:
                raise
            except Exception as error:  # observer failures cannot rewrite solver status
                manifest["postprocess_status"] = "failed"
                manifest["postprocess_error"] = f"{type(error).__name__}: {error}"
            _save_manifest(run_dir, manifest)
        elif manifest["solver_status"] != "completed_at_requested_horizon":
            manifest["postprocess_status"] = "not_attempted_solver_incomplete"
            _save_manifest(run_dir, manifest)
        elif not postprocess:
            manifest["postprocess_status"] = "skipped_by_cli"
            _save_manifest(run_dir, manifest)
        if solver_result.get("termination_signal") is not None:
            return 128 + int(solver_result["termination_signal"]), run_dir
        return 0 if manifest["solver_status"] == "completed_at_requested_horizon" else 1, run_dir
    except RunnerTermination as error:
        manifest["termination_signal"] = error.signum
        if manifest.get("solver_status") == "completed_at_requested_horizon":
            manifest["postprocess_status"] = "interrupted_after_solver_completion"
        else:
            manifest["solver_status"] = "interrupted_attempt_or_checkpoint_preserved"
            manifest["postprocess_status"] = "not_attempted_runner_interrupted"
        manifest["error"] = str(error)
        lifecycle_records = sorted(run_dir.glob("container-lifecycle-*.json"))
        if lifecycle_records:
            manifest["container_lifecycle_records"] = {
                path.stem.removeprefix("container-lifecycle-"): json.loads(
                    path.read_text(encoding="utf-8")
                )
                for path in lifecycle_records
            }
        manifest["finished_utc"] = utc_now()
        try:
            manifest["prepared_source_input_unchanged"] = (
                tree_hashes(source_dir) == manifest["prepared_source_input_sha256"]
            )
            _save_manifest(run_dir, manifest)
        except Exception as final_error:
            manifest["manifest_finalization_error"] = f"{type(final_error).__name__}: {final_error}"
            _atomic_json(manifest_path, manifest)
        return 128 + error.signum, run_dir
    except Exception as error:
        manifest["solver_status"] = "preflight_or_stage_failed_attempt_preserved"
        manifest["postprocess_status"] = "not_attempted_solver_not_completed"
        manifest["error"] = f"{type(error).__name__}: {error}"
        lifecycle_records = sorted(run_dir.glob("container-lifecycle-*.json"))
        if lifecycle_records:
            manifest["container_lifecycle_records"] = {
                path.stem.removeprefix("container-lifecycle-"): json.loads(
                    path.read_text(encoding="utf-8")
                )
                for path in lifecycle_records
            }
        manifest["finished_utc"] = utc_now()
        try:
            if source_dir.exists():
                source_after = tree_hashes(source_dir)
                manifest["prepared_source_input_unchanged"] = (
                    source_after == manifest["prepared_source_input_sha256"]
                )
            _save_manifest(run_dir, manifest)
        except Exception as final_error:
            manifest["manifest_finalization_error"] = f"{type(final_error).__name__}: {final_error}"
            _atomic_json(manifest_path, manifest)
        return 1, run_dir
    finally:
        manifest.setdefault("finished_utc", utc_now())
        if source_dir.exists() and "prepared_source_input_sha256" in manifest:
            try:
                final_source_hashes = tree_hashes(source_dir)
                manifest["prepared_source_input_unchanged"] = (
                    final_source_hashes == manifest["prepared_source_input_sha256"]
                )
                if not manifest["prepared_source_input_unchanged"]:
                    manifest["prepared_source_input_sha256_after"] = final_source_hashes
                _save_manifest(run_dir, manifest)
            except Exception as final_error:
                manifest["source_integrity_finalization_error"] = (
                    f"{type(final_error).__name__}: {final_error}"
                )
                _atomic_json(manifest_path, manifest)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-dir", type=Path, required=True, help="prepared static polyhedral OpenFOAM case"
    )
    parser.add_argument("--run-id", required=True, help="unique lowercase run ID")
    parser.add_argument(
        "--ranks",
        type=int,
        required=True,
        help="MPI rank count matching both metadata and decomposeParDict",
    )
    parser.add_argument("--memory-gib", type=int, required=True, help="Docker memory ceiling")
    parser.add_argument("--timeout-s", type=float, required=True, help="solver wall timeout")
    parser.add_argument(
        "--mesh-quality-exception-evidence",
        type=Path,
        help="optional hash-matched native support-plane evidence for one exact planar-transition checkMesh flag",
    )
    parser.add_argument(
        "--no-postprocess",
        action="store_true",
        help="skip observers after a full solver completion",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with termination_handlers():
            code, run_dir = run_case(
                case_dir=args.case_dir,
                run_id=args.run_id,
                ranks=args.ranks,
                memory_gib=args.memory_gib,
                timeout_s=args.timeout_s,
                mesh_quality_exception_evidence=args.mesh_quality_exception_evidence,
                postprocess=not args.no_postprocess,
            )
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        print(f"native VOF runner rejected invocation: {error}", file=sys.stderr)
        return 2
    except RunnerTermination as error:
        print(
            f"native VOF runner interrupted before launching managed work: {error}", file=sys.stderr
        )
        return 128 + error.signum
    print(json.dumps({"run_directory": str(run_dir), "exit_code": code}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
