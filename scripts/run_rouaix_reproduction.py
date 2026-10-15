#!/usr/bin/env python3
"""Prepare and supervise an exploratory Rouaix Case 4 CPU continuation.

The run starts from the exact 16-rank 1.750234439187 s checkpoint, preserves
the existing solver physics and mesh, and carries the audited native boundary
ledger exactly once. It is a reproduction attempt, not an E1 pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "runs"
SOURCE_ID = "rouaix-c4-continue-5s-20261007T153256Z-retry01"
SOURCE_RUN = RUNS / SOURCE_ID
SOURCE_CASE = SOURCE_RUN / "case"
SOURCE_DECLARATION = SOURCE_RUN / "case-declaration.json"
AUDITOR_SOURCE = ROOT / "scripts" / "rouaix_checkpoint_audit.py"
MONITOR_SOURCE = ROOT / "scripts" / "rouaix_checkpoint_monitor.py"
CHECKPOINT_NAME = "1.750234439187"
CHECKPOINT_TIME_S = float(CHECKPOINT_NAME)
PINNED_IMAGE = "opencfd/openfoam-default:2512"
PINNED_IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
OPENFOAM_BASHRC = "/usr/lib/openfoam/openfoam2512/etc/bashrc"
RHO_WATER_KG_M3 = 997.6
RANKS = 16
MEMORY_GIB = 48
WALL_BUDGET_S = 12 * 60 * 60
WRITE_INTERVAL_S = 0.5
FOOTPRINT_LIMIT_BYTES = 15 * 1024**3
MIN_FREE_DISK_BYTES = 60 * 1024**3
TIME_TOL_S = 1e-10
FIELDS = ("alpha.water", "U", "p_rgh", "k", "epsilon", "nut", "p", "phi")
PATCHES = (
    "gasInlet",
    "downstreamOutlet",
    "bottomOutlet",
    "aircraftWall",
    "spanwiseMinus",
    "spanwisePlus",
    "nozzle",
)
EXTERNAL_PATCHES = tuple(item for item in PATCHES if item != "nozzle")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,54}$")
NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])[+-]?(?:nan|inf(?:inity)?|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
NONFINITE_RE = re.compile(
    r"(?<![A-Za-z0-9_])[+-]?(?:nan|inf(?:inity)?)(?![A-Za-z0-9_])", re.IGNORECASE
)


class RunError(RuntimeError):
    """An input, restart, ledger, resource, or solver-stage failure."""


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
        child.relative_to(path).as_posix(): sha256(child)
        for child in sorted(path.rglob("*"))
        if child.is_file()
    }


def tree_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise RunError(f"expected JSON object in {path}")
    return result


def run_command(
    argv: list[str],
    *,
    cwd: Path = ROOT,
    timeout_s: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RunError(f"command did not complete: {argv!r}: {error}") from error
    if check and result.returncode:
        raise RunError(
            f"command exited {result.returncode}: {argv!r}\n{result.stdout}\n{result.stderr}"
        )
    return result


def git_state() -> dict[str, Any]:
    revision = run_command(["git", "rev-parse", "HEAD"], check=False)
    status = run_command(["git", "status", "--porcelain", "--untracked-files=all"], check=False)
    return {
        "revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "status_porcelain_at_prepare": status.stdout.splitlines() if status.returncode == 0 else [],
    }


def free_disk_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def parse_uniform_time(path: Path, directory_name: str) -> float:
    text = path.read_text(encoding="utf-8", errors="replace")
    value_match = re.search(r"\bvalue\s+([^;\s]+)\s*;", text)
    name_match = re.search(r'\bname\s+"([^"]+)"\s*;', text)
    if value_match is None or name_match is None:
        raise RunError(f"uniform/time lacks a numeric value or exact name: {path}")
    value = float(value_match.group(1))
    if not math.isfinite(value) or name_match.group(1) != directory_name:
        raise RunError(
            f"uniform/time name/value mismatch: {path}, {name_match.group(1)!r}, {value!r}"
        )
    if abs(value - float(directory_name)) > TIME_TOL_S:
        raise RunError(f"uniform/time does not identify checkpoint folder {directory_name}")
    return value


def local_cell_count(mesh: Path) -> int:
    text = (mesh / "cellProcAddressing").read_text(encoding="ascii", errors="replace")
    match = re.search(r"(?m)^\s*(\d+)\s*\(\s*$", text)
    if match is None:
        raise RunError(f"cannot read cellProcAddressing in {mesh}")
    return int(match.group(1))


def field_header(text: str) -> tuple[str, str]:
    head = text[: text.find("internalField")] if "internalField" in text else text
    field_class = re.search(r"\bclass\s+([^;\s]+)\s*;", head)
    object_name = re.search(r"\bobject\s+([^;\s]+)\s*;", head)
    if field_class is None or object_name is None:
        raise RunError("OpenFOAM field lacks a class or object header")
    return field_class.group(1), object_name.group(1)


def check_field(path: Path, cells: int, name: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        raise RunError(f"missing or empty checkpoint field: {path}")
    text = path.read_text(encoding="ascii", errors="replace")
    field_class, object_name = field_header(text)
    if object_name != name:
        raise RunError(f"{path}: OpenFOAM object name is {object_name!r}")
    if NONFINITE_RE.search(text):
        raise RunError(f"{path}: field contains NaN or infinity")
    tokens = sum(1 for _ in NUMBER_RE.finditer(text))
    if not tokens:
        raise RunError(f"{path}: field has no numeric data")
    result: dict[str, Any] = {
        "class": field_class,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "finite_numeric_tokens": tokens,
    }
    if name in {"alpha.water", "p_rgh", "k", "epsilon", "nut", "p"}:
        values_match = re.search(
            r"\binternalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;",
            text,
            flags=re.DOTALL,
        )
        uniform_match = re.search(
            r"\binternalField\s+uniform\s+"
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*;",
            text,
        )
        if values_match is not None:
            declared = int(values_match.group(1))
            values = [float(token.group(0)) for token in NUMBER_RE.finditer(values_match.group(2))]
            if declared != cells or len(values) != cells:
                raise RunError(f"{path}: scalar internalField count does not match {cells} cells")
        elif uniform_match is not None:
            values = [float(uniform_match.group(1))]
        else:
            raise RunError(f"{path}: unsupported scalar internalField")
        if not all(math.isfinite(value) for value in values):
            raise RunError(f"{path}: scalar values are non-finite")
        if name == "alpha.water":
            alpha_min, alpha_max = min(values), max(values)
            if alpha_min < -1e-12 or alpha_max > 1.0 + 1e-12:
                raise RunError(f"{path}: alpha outside [0,1]: {alpha_min}, {alpha_max}")
            result["alpha_min"] = alpha_min
            result["alpha_max"] = alpha_max
    elif name == "U":
        vector_match = re.search(
            r"\binternalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;",
            text,
            flags=re.DOTALL,
        )
        if vector_match is None:
            raise RunError(f"{path}: unsupported U internalField")
        count = int(vector_match.group(1))
        components = sum(1 for _ in NUMBER_RE.finditer(vector_match.group(2)))
        if count != cells or components != 3 * cells:
            raise RunError(f"{path}: velocity vector count does not match {cells} cells")
    return result


def validate_checkpoint(case: Path) -> dict[str, Any]:
    ranks = sorted(
        case.glob("processor[0-9]*"),
        key=lambda item: int(item.name.removeprefix("processor")),
    )
    expected_ranks = [f"processor{i}" for i in range(RANKS)]
    if [rank.name for rank in ranks] != expected_ranks:
        raise RunError(f"expected processor0..processor15, found {[p.name for p in ranks]}")
    local_cells: list[int] = []
    time_values: list[float] = []
    alpha_mins: list[float] = []
    alpha_maxes: list[float] = []
    checkpoint_field_hashes: dict[str, str] = {}
    processor_mesh_hashes: dict[str, dict[str, str]] = {}
    checkpoint_bytes = 0
    for rank in ranks:
        mesh = rank / "constant" / "polyMesh"
        folder = rank / CHECKPOINT_NAME
        if not mesh.is_dir():
            raise RunError(f"processor mesh missing: {mesh}")
        time_values.append(parse_uniform_time(folder / "uniform" / "time", CHECKPOINT_NAME))
        cells = local_cell_count(mesh)
        local_cells.append(cells)
        for field in FIELDS:
            path = folder / field
            info = check_field(path, cells, field)
            checkpoint_field_hashes[f"{rank.name}/{CHECKPOINT_NAME}/{field}"] = info["sha256"]
            checkpoint_bytes += path.stat().st_size
            if field == "alpha.water":
                alpha_mins.append(float(info["alpha_min"]))
                alpha_maxes.append(float(info["alpha_max"]))
        for name in ("time", "cumulativeContErr"):
            path = folder / "uniform" / name
            if not path.is_file() or path.stat().st_size == 0:
                raise RunError(f"checkpoint uniform state missing: {path}")
        processor_mesh_hashes[rank.name] = tree_hash(mesh)
    if len(set(local_cells)) != 1 or sum(local_cells) != 2_733_120:
        raise RunError(f"unexpected checkpoint partition sizes: {local_cells}")
    if max(time_values) - min(time_values) > TIME_TOL_S:
        raise RunError(f"processor uniform/time values differ: {time_values}")
    return {
        "rank_count": RANKS,
        "local_cells": local_cells,
        "global_cells": sum(local_cells),
        "checkpoint_name": CHECKPOINT_NAME,
        "uniform_time_values_s": time_values,
        "all_16_processor_checkpoints_complete": True,
        "all_required_fields_finite": True,
        "checkpoint_fields": list(FIELDS),
        "alpha_min": min(alpha_mins),
        "alpha_max": max(alpha_maxes),
        "checkpoint_field_bytes_all_ranks": checkpoint_bytes,
        "checkpoint_field_sha256": checkpoint_field_hashes,
        "processor_mesh_sha256": processor_mesh_hashes,
    }


def copy_tree(source: Path, target: Path) -> dict[str, str]:
    expected = tree_hash(source)
    shutil.copytree(source, target)
    if tree_hash(target) != expected:
        raise RunError(f"copy hash mismatch: {source} -> {target}")
    return expected


def copy_file(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    digest = sha256(source)
    if digest != sha256(target):
        raise RunError(f"copy hash mismatch: {source} -> {target}")
    return digest


def replace_top_level(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^({re.escape(key)}\s+)[^;]+;")
    updated, count = pattern.subn(rf"\g<1>{value};", text, count=1)
    if count != 1:
        raise RunError(f"expected one top-level controlDict entry {key}, found {count}")
    return updated


def patch_control_dict(source: Path, end_time_s: float) -> tuple[str, dict[str, Any]]:
    text = source.read_text(encoding="utf-8")
    source_digest = sha256(source)
    changes = {
        "startFrom": "latestTime",
        "endTime": f"{end_time_s:.13g}",
        "writeControl": "adjustableRunTime",
        "writeInterval": f"{WRITE_INTERVAL_S:.13g}",
        "timePrecision": "13",
    }
    for key, value in changes.items():
        text = replace_top_level(text, key, value)
    missing = [patch for patch in PATCHES if f"liquidFlux_{patch}" not in text]
    if missing:
        raise RunError(f"source controlDict lacks native flux writers: {missing}")
    return text, {
        "source_sha256": source_digest,
        "prepared_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "top_level_changes": changes,
    }


def container_name(run_dir: Path) -> str:
    return "rr-" + run_dir.name[:50]


def source_container_state() -> dict[str, Any]:
    source_manifest = read_json(SOURCE_RUN / "run-manifest.json")
    command = source_manifest.get("launch", {}).get("command", [])
    name = None
    for index, token in enumerate(command):
        if isinstance(token, str) and token.startswith("--name="):
            name = token.split("=", 1)[1]
            break
        if token == "--name" and index + 1 < len(command):
            name = str(command[index + 1])
            break
    if not name:
        raise RunError("source container name is missing from retained launch record")
    result = run_command(
        ["docker", "inspect", "--format", "{{json .State}}", name],
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no Docker error detail"
        raise RunError(f"cannot verify source CFD container state for {name}: {detail}")
    try:
        state = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RunError(f"Docker returned invalid state JSON for source container {name}") from error
    running = state.get("Running")
    if not isinstance(running, bool):
        raise RunError(f"Docker did not report a boolean running state for source container {name}")
    if running:
        raise RunError(f"source CFD container is still active: {name}")
    return {
        "name": name,
        "inspect_available": True,
        "running": running,
        "status": state.get("Status"),
        "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled"),
    }


def copy_auditor(destination: Path) -> str:
    if not AUDITOR_SOURCE.is_file():
        raise RunError(f"stable checkpoint auditor is missing: {AUDITOR_SOURCE}")
    shutil.copy2(AUDITOR_SOURCE, destination)
    copied_hash = sha256(destination)
    if copied_hash != sha256(AUDITOR_SOURCE):
        raise RunError("copied checkpoint auditor does not match its stable source")
    return copied_hash


def load_auditor(path: Path) -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("rouaix_checkpoint_audit", path)
    if spec is None or spec.loader is None:
        raise RunError(f"cannot load checkpoint auditor: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke_audit(
    auditor: Path,
    case: Path,
    declaration: Path,
    through_time_s: float,
    output: Path,
    timeout_s: int = 600,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    for key in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        env[key] = "1"
    command = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(auditor),
        "--case",
        str(case),
        "--declaration",
        str(declaration),
        "--through-time",
        f"{through_time_s:.13g}",
        "--output-dir",
        str(output),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RunError(f"native audit timed out in {output}") from error
    (output / "audit.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "audit.stderr.txt").write_text(result.stderr, encoding="utf-8")
    report_path = output / "ledger-report.json"
    if result.returncode or not report_path.is_file():
        raise RunError(f"native ledger audit exited {result.returncode}: {output}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    declared = read_json(declaration)
    if report.get("run_id") != declared.get("run_id"):
        raise RunError("ledger report run id differs from declaration")
    return report


def zero_increment_smoke(auditor: Any, declaration: dict[str, Any]) -> dict[str, Any]:
    metadata = auditor.checkpoint_metadata(declaration)
    closure = auditor.calculate_closure(
        metadata,
        incremental_source_m3=0.0,
        incremental_escape_m3=0.0,
        final_inventory_m3=metadata["initial_inventory_m3"],
    )
    incremental_residual = float(closure["incremental_residual_kg"])
    cumulative_fraction = float(closure["cumulative_residual_m3"]) / float(
        closure["cumulative_source_m3"]
    )
    result = {
        "status": "pass",
        "checkpoint_time_s": metadata["initial_time_s"],
        "initial_inventory_m3": metadata["initial_inventory_m3"],
        "carried_prior_release_m3": metadata["prior_release_m3"],
        "carried_prior_escape_m3": metadata["prior_escape_m3"],
        "carried_parent_residual_kg": metadata["parent_residual_kg"],
        "incremental_source_m3": 0.0,
        "incremental_escape_m3": 0.0,
        "incremental_residual_kg": incremental_residual,
        "incremental_residual_fraction": None,
        "zero_source_guard": "absolute residual <= 1e-12 kg; fraction is undefined",
        "incremental_guard_pass": abs(incremental_residual) <= 1e-12,
        "cumulative_residual_kg": closure["cumulative_residual_kg"],
        "cumulative_residual_fraction": cumulative_fraction,
        "cumulative_guard_pass": abs(cumulative_fraction) <= 0.001,
    }
    if not result["incremental_guard_pass"] or not result["cumulative_guard_pass"]:
        result["status"] = "fail"
        raise RunError(f"zero-increment checkpoint smoke failed: {result}")
    return result


def foam_dictionary_smoke(run_dir: Path) -> dict[str, Any]:
    case = run_dir / "case"
    command = [
        "docker",
        "run",
        "--rm",
        "--cpus=2",
        "--memory=8g",
        "--memory-swap",
        "8g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={case},dst=/case,readonly",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        PINNED_IMAGE,
        "-lc",
        (
            "source " + OPENFOAM_BASHRC + " >/dev/null 2>&1 && "
            "for key in startFrom endTime writeControl writeInterval timePrecision "
            "deltaT adjustTimeStep maxCo maxAlphaCo maxDeltaT; do "
            'printf \'%s=\' "$key"; foamDictionary system/controlDict -entry "$key" -value; '
            "done; printf 'numberOfSubdomains='; "
            "foamDictionary system/decomposeParDict -entry numberOfSubdomains -value"
        ),
    ]
    result = run_command(command, timeout_s=180)
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    expected = {
        "startFrom": "latestTime",
        "endTime": "5",
        "writeControl": "adjustableRunTime",
        "writeInterval": "0.5",
        "timePrecision": "13",
        "deltaT": "0.00025",
        "adjustTimeStep": "yes",
        "maxCo": "2",
        "maxAlphaCo": "1",
        "maxDeltaT": "0.0005",
        "numberOfSubdomains": str(RANKS),
    }
    if values != expected:
        raise RunError(f"foamDictionary parsed {values}; expected {expected}")
    record = {
        "status": "pass",
        "image": PINNED_IMAGE,
        "expected_image_id": PINNED_IMAGE_ID,
        "parsed_dictionary_values": values,
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    write_json(run_dir / "preflight" / "foam-dictionary-smoke.json", record)
    return record


def image_check() -> dict[str, str]:
    result = run_command(
        ["docker", "image", "inspect", PINNED_IMAGE, "--format", "{{.Id}}"],
        timeout_s=60,
    )
    image_id = result.stdout.strip()
    if image_id != PINNED_IMAGE_ID:
        raise RunError(f"solver image mismatch: {image_id!r}")
    return {"reference": PINNED_IMAGE, "resolved_image_id": image_id}


def prepare(run_id: str, end_time_s: float) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise RunError(f"invalid run id {run_id!r}")
    if not 4.5 <= end_time_s <= 5.0:
        raise RunError("end time must be between the paper-time observation at 4.5 s and 5.0 s")
    if free_disk_bytes(ROOT) < MIN_FREE_DISK_BYTES:
        raise RunError("disk free space is below the 60 GiB launch threshold")
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        run_dir / "prepare-state.json",
        {"status": "preparing", "started_utc": utc_now(), "run_id": run_id},
    )
    try:
        source_state = source_container_state()
        image = image_check()
        if not SOURCE_CASE.is_dir() or not SOURCE_DECLARATION.is_file():
            raise RunError("source case or declaration is missing")
        source_decl = read_json(SOURCE_DECLARATION)
        if source_decl.get("run_id") != SOURCE_ID:
            raise RunError("source declaration run_id mismatch")
        source_health = validate_checkpoint(SOURCE_CASE)

        auditor_path = run_dir / "audit_checkpoint.py"
        auditor_hash = copy_auditor(auditor_path)
        preflight_audit_dir = run_dir / "preflight" / "parent-checkpoint-audit"
        parent_report = invoke_audit(
            auditor_path,
            SOURCE_CASE,
            SOURCE_DECLARATION,
            CHECKPOINT_TIME_S,
            preflight_audit_dir,
        )
        if (
            abs(float(parent_report["actual_final_time_s"]) - CHECKPOINT_TIME_S) > TIME_TOL_S
            or not parent_report["continuation_guard_0p1_percent"]["incremental_pass"]
            or not parent_report["continuation_guard_0p1_percent"]["cumulative_pass"]
        ):
            raise RunError("exact current checkpoint native ledger audit did not pass")
        cumulative = parent_report["cumulative_ledger_from_t0"]
        offsets = {
            "checkpoint_inventory_volume_m3": float(cumulative["final_stored_volume_m3"]),
            "checkpoint_residual_expected_minus_observed_kg": float(
                cumulative["residual_expected_minus_observed_kg"]
            ),
            "offset_applied_once": True,
            "prior_escape_volume_m3": float(cumulative["total_escape_volume_m3"]),
            "prior_release_volume_m3": float(cumulative["total_source_volume_m3"]),
        }

        case = run_dir / "case"
        case.mkdir()
        copy_hashes: dict[str, Any] = {}
        copy_hashes["constant/polyMesh"] = copy_tree(
            SOURCE_CASE / "constant" / "polyMesh", case / "constant" / "polyMesh"
        )
        for name in ("g", "hRef", "transportProperties", "turbulenceProperties"):
            copy_hashes[f"constant/{name}"] = copy_file(
                SOURCE_CASE / "constant" / name, case / "constant" / name
            )
        copy_hashes["system"] = copy_tree(SOURCE_CASE / "system", case / "system")
        source_control = SOURCE_CASE / "system" / "controlDict"
        control_text, control_record = patch_control_dict(source_control, end_time_s)
        target_control = case / "system" / "controlDict"
        target_control.write_text(control_text, encoding="utf-8")
        copy_hashes["system/controlDict"] = control_record

        copied_rank_hashes: dict[str, Any] = {}
        for rank_index in range(RANKS):
            rank_name = f"processor{rank_index}"
            source_rank = SOURCE_CASE / rank_name
            target_rank = case / rank_name
            target_rank.mkdir()
            copied_rank_hashes[rank_name] = {
                "mesh": copy_tree(
                    source_rank / "constant" / "polyMesh",
                    target_rank / "constant" / "polyMesh",
                ),
                "checkpoint_fields": {},
            }
            source_time = source_rank / CHECKPOINT_NAME
            target_time = target_rank / CHECKPOINT_NAME
            target_time.mkdir()
            for field in FIELDS:
                copied_rank_hashes[rank_name]["checkpoint_fields"][field] = copy_file(
                    source_time / field, target_time / field
                )
            for field in ("time", "cumulativeContErr"):
                copied_rank_hashes[rank_name][f"uniform/{field}"] = copy_file(
                    source_time / "uniform" / field,
                    target_time / "uniform" / field,
                )
        copied_health = validate_checkpoint(case)
        if copied_health["checkpoint_field_sha256"] != source_health["checkpoint_field_sha256"]:
            raise RunError("copied checkpoint fields do not match all source ranks")
        if copied_health["processor_mesh_sha256"] != source_health["processor_mesh_sha256"]:
            raise RunError("copied per-rank mesh hashes differ from the source")

        interval_start = math.ceil(CHECKPOINT_TIME_S / WRITE_INTERVAL_S)
        interval_end = math.floor(end_time_s / WRITE_INTERVAL_S)
        expected_frame_targets = [
            float(f"{index * WRITE_INTERVAL_S:.12g}")
            for index in range(interval_start, interval_end + 1)
        ]
        declaration: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "purpose": (
                "Exploratory Rouaix Case 4 coarse 70 mm constant-jet continuation "
                "from the exact complete 1.750234439187 s checkpoint."
            ),
            "status": "declared_before_launch",
            "declared_utc": utc_now(),
            "solver": {
                "name": "interIsoFoam",
                "version": "OpenFOAM v2512",
                "container_image": PINNED_IMAGE,
                "resolved_image_id": image["resolved_image_id"],
                "water_air_vof": True,
                "turbulence_model": "realizable k-epsilon",
                "gravity_m_s2": [0.0, -9.81, 0.0],
                "surface_tension_N_m": 0.072,
                "water_outlet_velocity_m_s": [0.0, 10.0, 0.0],
                "air_velocity_m_s": [70.0, 0.0, 0.0],
                "mesh_measured_nozzle_area_m2": 0.1237069,
                "nominal_round_nozzle_area_m2": math.pi * 0.2**2,
                "water_density_kg_m3": RHO_WATER_KG_M3,
                "physics_and_mesh_unchanged": True,
            },
            "mesh": {
                "case": "Rouaix Table 3 Case 4 coarse 70 mm constant jet",
                "cell_count": 2_733_120,
                "rank_count": RANKS,
                "decomposition": "4 x 2 x 2",
                "nominal_source_cell_spacing_m": 0.07,
                "source_run_id": SOURCE_ID,
                "processor_mesh_hashes_identical": True,
                "assumptions": [
                    "structured hexahedral corridor instead of paper polyhedral/prism mesh",
                    "flat roof is provisional",
                ],
            },
            "checkpoint": {
                "time_s": CHECKPOINT_TIME_S,
                "directory_name": CHECKPOINT_NAME,
                "uniform_time_values_s": source_health["uniform_time_values_s"],
                "native_water_volume_m3": offsets["checkpoint_inventory_volume_m3"],
                "native_water_mass_kg": offsets["checkpoint_inventory_volume_m3"] * RHO_WATER_KG_M3,
                "native_inventory_source": "exact common native waterInventory history row",
                "rank_count": RANKS,
                "field_health": {
                    "fields": list(FIELDS),
                    "all_fields_finite": True,
                    "alpha_water_min": source_health["alpha_min"],
                    "alpha_water_max": source_health["alpha_max"],
                },
            },
            "parent_ledger_offsets": offsets,
            "continuation": {
                "from_time_s": CHECKPOINT_TIME_S,
                "end_time_s": end_time_s,
                "physical_time_advanced_s": end_time_s - CHECKPOINT_TIME_S,
                "startFrom": "latestTime",
                "checkpoint_time_precision": 13,
                "initial_delta_t_s": 0.00025,
                "adjustTimeStep": True,
                "max_delta_t_s": 0.0005,
                "maxCo": 2.0,
                "maxAlphaCo": 1.0,
                "writeControl": "adjustableRunTime",
                "writeInterval_s": WRITE_INTERVAL_S,
                "nominal_snapshot_targets_s": expected_frame_targets,
                "native_inventory_and_seven_boundary_fluxes_every_step": True,
                "parent_offsets_applied_once": True,
                "full_precheckpoint_history_copied": False,
                "wall_budget_s": WALL_BUDGET_S,
            },
            "resource_allocation": {
                "cpu_limit": RANKS,
                "mpi_ranks": RANKS,
                "memory_limit_gib": MEMORY_GIB,
                "threads_per_rank": 1,
                "gpu": False,
                "wall_budget_s": WALL_BUDGET_S,
                "free_disk_floor_bytes": MIN_FREE_DISK_BYTES,
                "new_bundle_footprint_cap_bytes": FOOTPRINT_LIMIT_BYTES,
            },
            "boundary_conditions": {
                "native_flux_patches": list(PATCHES),
                "source_patch": "nozzle",
                "exterior_open_patches": list(EXTERNAL_PATCHES),
                "outward_alphaPhi_positive": True,
            },
            "operational_guards_not_validation_gates": {
                "max_abs_incremental_and_cumulative_residual_fraction": 0.001,
                "meaning": "continuation health guard; not Rouaix E1 acceptance",
            },
            "diagnostics": {
                "native_waterInventory_each_solver_step": True,
                "native_alphaPhi_all_seven_patches_each_solver_step": True,
                "continuous_checkpoint_mass_closure": True,
                "full_processor_fields_every_0p5s": True,
                "explicit_paper_time_observables": [4.5, 5.0],
                "not_claimed": [
                    "E1 acceptance",
                    "field validation",
                    "paper-mesh reproduction",
                    "ground-delivery validity",
                ],
            },
            "source_run": {
                "run_id": SOURCE_ID,
                "directory": str(SOURCE_RUN),
                "container_state": source_state,
                "standalone_restart_dependency": (
                    "The exact restart fields, native source/escape history, and case dictionaries "
                    "must be restored from this retained results/runs bundle; a fresh checkout alone "
                    "does not contain this restart state."
                ),
                "run_manifest_sha256": sha256(SOURCE_RUN / "run-manifest.json"),
                "case_declaration_sha256": sha256(SOURCE_DECLARATION),
                "checkpoint_audit": str(
                    (preflight_audit_dir / "ledger-report.json").relative_to(ROOT)
                ),
                "source_bundle_preserved": True,
            },
            "input_hashes": {
                "copied_auditor_sha256": auditor_hash,
                "copied_auditor_source": str(AUDITOR_SOURCE.relative_to(ROOT)),
                "copied_auditor_source_sha256": sha256(AUDITOR_SOURCE),
                "copied_global_mesh_and_constants": copy_hashes,
                "copied_processor_mesh_checkpoint_hashes": copied_rank_hashes,
                "controlDict_changes": control_record,
            },
            "preflight": {
                "source_checkpoint": source_health,
                "copied_checkpoint": copied_health,
                "exact_native_checkpoint_audit": parent_report,
                "zero_increment_smoke": None,
                "positive_history_smoke": None,
                "foam_dictionary_smoke": None,
            },
            "git": git_state(),
        }
        declaration_path = run_dir / "case-declaration.json"
        write_json(declaration_path, declaration)
        write_json(run_dir / "case.json", declaration)

        auditor_module = load_auditor(auditor_path)
        zero_result = zero_increment_smoke(auditor_module, declaration)
        write_json(run_dir / "preflight" / "zero-increment-smoke.json", zero_result)
        declaration["preflight"]["zero_increment_smoke"] = zero_result

        positive_decl = json.loads(json.dumps(source_decl))
        positive_decl["run_id"] = run_id + "-positive-smoke"
        positive_decl_path = run_dir / "preflight" / "positive-smoke-declaration.json"
        write_json(positive_decl_path, positive_decl)
        positive_dir = run_dir / "preflight" / "positive-history-smoke"
        positive_report = invoke_audit(
            auditor_path,
            SOURCE_CASE,
            positive_decl_path,
            CHECKPOINT_TIME_S,
            positive_dir,
        )
        guards = positive_report["continuation_guard_0p1_percent"]
        if not (guards["incremental_pass"] and guards["cumulative_pass"]):
            raise RunError("positive actual-history audit smoke failed its ledger guards")
        declaration["preflight"]["positive_history_smoke"] = {
            "status": "pass",
            "new_nested_schema_used": True,
            "actual_checkpoint_time_s": positive_report["actual_final_time_s"],
            "incremental_residual_kg": positive_report["incremental_ledger_from_checkpoint"][
                "residual_expected_minus_observed_kg"
            ],
            "cumulative_residual_kg": positive_report["cumulative_ledger_from_t0"][
                "residual_expected_minus_observed_kg"
            ],
            "both_0p1_percent_guards_pass": True,
            "report": str((positive_dir / "ledger-report.json").relative_to(ROOT)),
        }
        declaration["preflight"]["foam_dictionary_smoke"] = foam_dictionary_smoke(run_dir)

        measured_snapshot = source_health["checkpoint_field_bytes_all_ranks"]
        copied_case_size = tree_size(case)
        write_count = len(expected_frame_targets)
        projected = int(math.ceil((copied_case_size + measured_snapshot * write_count) * 1.5))
        if projected >= FOOTPRINT_LIMIT_BYTES:
            raise RunError(f"projected run footprint {projected} bytes reaches 15 GiB cap")
        declaration["storage_estimate"] = {
            "measured_full_checkpoint_fields_bytes_all_16_ranks": measured_snapshot,
            "expected_full_snapshot_count": write_count,
            "prelaunch_case_bytes": copied_case_size,
            "projected_bundle_bytes_with_50_percent_margin": projected,
            "bundle_footprint_cap_bytes": FOOTPRINT_LIMIT_BYTES,
            "free_disk_bytes_at_prepare": free_disk_bytes(ROOT),
        }
        write_json(declaration_path, declaration)
        write_json(run_dir / "case.json", declaration)
        write_json(
            run_dir / "prepare-state.json",
            {
                "status": "prepared",
                "prepared_utc": utc_now(),
                "run_id": run_id,
                "case_declaration_sha256": sha256(declaration_path),
                "case_json_sha256": sha256(run_dir / "case.json"),
                "case_bytes": copied_case_size,
                "free_disk_bytes": free_disk_bytes(ROOT),
                "effective_cpu_count": 20,
                "mpi_ranks": RANKS,
            },
        )
        return run_dir
    except Exception as error:
        write_json(
            run_dir / "preparation-failure.json",
            {
                "status": "preparation_failed",
                "failed_utc": utc_now(),
                "error_type": type(error).__name__,
                "error": str(error),
                "partial_artifacts_preserved": True,
            },
        )
        raise


def docker_command(run_dir: Path) -> list[str]:
    name = container_name(run_dir)
    cidfile = run_dir / "flow.cid"
    case = run_dir / "case"
    if cidfile.exists():
        raise RunError(f"refusing to reuse container id file: {cidfile}")
    flow = (
        "set +e +u; source "
        + OPENFOAM_BASHRC
        + " >/dev/null 2>&1; setup=$?; set -euo pipefail; "
        + "printf 'ROUAIX_SETUP_EXIT code=%s\\n' \"$setup\"; "
        + 'if [ "$setup" -ne 0 ]; then exit "$setup"; fi; '
        + 'run_stage() { stage=$1; shift; set +e; "$@"; code=$?; set -e; '
        + 'printf \'ROUAIX_STAGE_EXIT stage=%s code=%s\\n\' "$stage" "$code"; '
        + 'if [ "$code" -ne 0 ]; then exit "$code"; fi; }; '
        + "run_stage dictionary-time-precision foamDictionary system/controlDict -entry timePrecision -value; "
        + "run_stage dictionary-ranks foamDictionary system/decomposeParDict -entry numberOfSubdomains -value; "
        + "run_stage solver timeout --signal=TERM --kill-after=60s "
        + str(WALL_BUDGET_S)
        + "s mpirun --bind-to none -np "
        + str(RANKS)
        + " interIsoFoam -parallel; "
        + "run_stage reconstruct reconstructPar -latestTime -fields '(alpha.water U p_rgh k epsilon nut)'"
    )
    command = [
        "docker",
        "run",
        f"--name={name}",
        f"--cidfile={cidfile}",
        f"--cpus={RANKS}",
        f"--memory={MEMORY_GIB}g",
        "--memory-swap",
        f"{MEMORY_GIB}g",
    ]
    for variable in (
        "OMP_NUM_THREADS=1",
        "OMP_THREAD_LIMIT=1",
        "OPENBLAS_NUM_THREADS=1",
        "MKL_NUM_THREADS=1",
        "BLIS_NUM_THREADS=1",
        "NUMEXPR_NUM_THREADS=1",
    ):
        command.extend(["--env", variable])
    command.extend(
        [
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--mount",
            f"type=bind,src={case},dst=/case",
            "--workdir",
            "/case",
            "--entrypoint",
            "/bin/bash",
            PINNED_IMAGE,
            "-c",
            flow,
        ]
    )
    return command


def launch(run_dir: Path) -> dict[str, Any]:
    state = read_json(run_dir / "prepare-state.json")
    if state.get("status") != "prepared":
        raise RunError(f"run is not prepared: {state.get('status')!r}")
    if sha256(run_dir / "case.json") != state["case_json_sha256"]:
        raise RunError("case.json changed after preflight")
    if free_disk_bytes(ROOT) < MIN_FREE_DISK_BYTES:
        raise RunError("free disk fell below 60 GiB before launch")
    if tree_size(run_dir) >= FOOTPRINT_LIMIT_BYTES:
        raise RunError("prepared run bundle reached the 15 GiB cap")
    if (run_dir / "launch.json").exists():
        raise RunError("run bundle already has a launch record")
    command = docker_command(run_dir)
    worker_command = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "scripts" / "run_local.py"),
        "--threads",
        "1",
        "--",
        str(ROOT / ".venv" / "bin" / "python"),
        str(Path(__file__).resolve()),
        "--worker",
        str(run_dir),
    ]
    launch_record = {
        "status": "launching",
        "run_id": run_dir.name,
        "started_utc": utc_now(),
        "detached": True,
        "host_cpu_limit": RANKS,
        "mpi_ranks": RANKS,
        "memory_limit_gib": MEMORY_GIB,
        "gpu": False,
        "restart_interval_s": [
            CHECKPOINT_TIME_S,
            read_json(run_dir / "case.json")["continuation"]["end_time_s"],
        ],
        "checkpoint_folder": CHECKPOINT_NAME,
        "full_field_write_interval_s": WRITE_INTERVAL_S,
        "wall_budget_s": WALL_BUDGET_S,
        "monitor": {
            "poll_interval_s": 30,
            "checkpoint_stability_s": 30,
            "resource_sample_interval_s": 600,
            "operational_ledger_guard": 0.001,
            "unreadable_audit_stop_after_attempts": 3,
            "minimum_free_disk_bytes": MIN_FREE_DISK_BYTES,
            "bundle_footprint_cap_bytes": FOOTPRINT_LIMIT_BYTES,
        },
        "docker_command": command,
        "worker_command": worker_command,
        "solver_log": "flow.log",
        "monitor_log": "checkpoint-monitor.stdout.log",
    }
    write_json(run_dir / "docker-command.json", launch_record)
    worker_log = (run_dir / "worker.log").open("ab", buffering=0)
    try:
        process = subprocess.Popen(
            worker_command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=worker_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        worker_log.close()
    launch_record.update(
        {
            "status": "launched_detached",
            "host_worker_pid": process.pid,
            "process_group": process.pid,
        }
    )
    write_json(run_dir / "launch.json", launch_record)
    write_json(
        run_dir / "worker-state.json",
        {"status": "launching", "host_worker_pid": process.pid, "started_utc": utc_now()},
    )
    return launch_record


def monitor_source_copy(run_dir: Path) -> Path:
    if not MONITOR_SOURCE.is_file():
        raise RunError(f"stable checkpoint monitor template is missing: {MONITOR_SOURCE}")
    text = MONITOR_SOURCE.read_text(encoding="utf-8")
    text = text.replace(
        'SOURCE_RUN = ROOT / "results/runs/rouaix-c4-continue-5s-20261007T153256Z-retry01"',
        "SOURCE_RUN = RUN",
        1,
    )
    text = text.replace(
        "NAME = SOURCE_RUN.name",
        f'NAME = "{container_name(run_dir)}"',
        1,
    )
    marker = 'INDEX = AUDIT_ROOT / "index.jsonl"'
    insertion = (
        marker + "\nMIN_FREE_DISK_BYTES = 60 * 1024**3\n" + "FOOTPRINT_LIMIT_BYTES = 15 * 1024**3\n"
    )
    if text.count(marker) != 1:
        raise RunError("checkpoint monitor insertion point changed")
    text = text.replace(marker, insertion, 1)
    loop_marker = "        state = container_running()"
    guard_code = (
        "        if time.monotonic() - last_disk_check >= 600.0:\n"
        "            free_bytes = shutil.disk_usage(ROOT).free\n"
        "            bundle_bytes = sum(p.stat().st_size for p in RUN.rglob('*') if p.is_file())\n"
        "            append_record({'utc': datetime.now(UTC).isoformat(), 'status': 'resource_guard_sample', 'free_disk_bytes': free_bytes, 'bundle_bytes': bundle_bytes})\n"
        "            last_disk_check = time.monotonic()\n"
        "            if free_bytes < MIN_FREE_DISK_BYTES:\n"
        "                stop_container(f'free disk below 60 GiB: {free_bytes} bytes')\n"
        "                return 4\n"
        "            if bundle_bytes >= FOOTPRINT_LIMIT_BYTES:\n"
        "                stop_container(f'run bundle reached 15 GiB: {bundle_bytes} bytes')\n"
        "                return 4\n"
    )
    if text.count(loop_marker) != 1:
        raise RunError("checkpoint monitor resource-guard insertion point changed")
    text = text.replace(loop_marker, guard_code + loop_marker, 1)
    before_loop = "    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)\n    while True:"
    if text.count(before_loop) != 1:
        raise RunError("checkpoint monitor loop initialization changed")
    text = text.replace(
        before_loop,
        "    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)\n"
        "    last_disk_check = 0.0\n"
        "    while True:",
        1,
    )
    destination = run_dir / "checkpoint_monitor.py"
    destination.write_text(text, encoding="utf-8")
    return destination


def docker_inspect(name: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["docker", "inspect", name],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
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
        "name": data.get("Name"),
        "image_id": data.get("Image"),
        "status": state.get("Status"),
        "running": state.get("Running"),
        "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "error": state.get("Error"),
    }


def solver_worker(run_dir: Path) -> int:
    state_path = run_dir / "worker-state.json"
    state = read_json(state_path)
    state.update({"status": "running", "worker_started_utc": utc_now()})
    write_json(state_path, state)
    command = docker_command(run_dir)
    name = container_name(run_dir)
    image = image_check()
    declaration = read_json(run_dir / "case-declaration.json")
    if image["resolved_image_id"] != declaration["solver"]["resolved_image_id"]:
        raise RunError("pinned solver image changed after preflight")
    if free_disk_bytes(ROOT) < MIN_FREE_DISK_BYTES:
        raise RunError("disk below the 60 GiB threshold when worker started")
    if tree_size(run_dir) >= FOOTPRINT_LIMIT_BYTES:
        raise RunError("run bundle already reaches 15 GiB cap")
    monitor_script = monitor_source_copy(run_dir)
    write_json(run_dir / "worker-command.json", {"command": command, "created_utc": utc_now()})
    flow = (run_dir / "flow.log").open("ab", buffering=0)
    try:
        solver = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=flow,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        flow.close()
    state.update({"status": "solver_starting", "docker_client_pid": solver.pid})
    write_json(state_path, state)

    cidfile = run_dir / "flow.cid"
    start_deadline = time.monotonic() + 180.0
    container_state = None
    while time.monotonic() < start_deadline:
        if cidfile.is_file():
            container_state = docker_inspect(name)
            if container_state and container_state["running"]:
                break
        if solver.poll() is not None:
            break
        time.sleep(2)
    if container_state is None or not container_state.get("running"):
        rc = solver.poll()
        if rc is None:
            subprocess.run(
                ["docker", "stop", "--time", "20", name],
                cwd=ROOT,
                capture_output=True,
                timeout=40,
                check=False,
            )
            rc = solver.wait(timeout=60)
        state.update(
            {
                "status": "failed_before_solver",
                "docker_client_exit_code": rc,
                "container_inspect": docker_inspect(name),
                "finished_utc": utc_now(),
            }
        )
        write_json(state_path, state)
        (run_dir / "worker.exit").write_text("1\n", encoding="ascii")
        return 1
    cid = cidfile.read_text(encoding="ascii").strip()
    live_started_utc = utc_now()
    write_json(
        run_dir / "live.json",
        {
            "status": "running",
            "container_id": cid,
            "container_name": name,
            "mpi_ranks": RANKS,
            "start_time_s": CHECKPOINT_TIME_S,
            "end_time_s": declaration["continuation"]["end_time_s"],
            "started_utc": live_started_utc,
            "disk_free_bytes": free_disk_bytes(ROOT),
            "run_bundle_bytes": tree_size(run_dir),
        },
    )

    monitor_log = (run_dir / "checkpoint-monitor.stdout.log").open("ab", buffering=0)
    try:
        monitor = subprocess.Popen(
            [str(ROOT / ".venv" / "bin" / "python"), str(monitor_script)],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=monitor_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        monitor_log.close()
    write_json(
        run_dir / "monitor-launch.json",
        {
            "pid": monitor.pid,
            "started_utc": utc_now(),
            "script": str(monitor_script),
            "source_template": str(MONITOR_SOURCE.relative_to(ROOT)),
            "source_template_sha256": sha256(MONITOR_SOURCE),
            "generated_monitor_sha256": sha256(monitor_script),
        },
    )
    state.update(
        {
            "status": "solver_running",
            "container_id": cid,
            "container_name": name,
            "mpi_ranks": RANKS,
            "monitor_pid": monitor.pid,
            "solver_started_utc": live_started_utc,
        }
    )
    write_json(state_path, state)

    start = time.monotonic()
    next_sample = start + 600.0
    pending_error = None
    while solver.poll() is None:
        now = time.monotonic()
        if now - start > WALL_BUDGET_S + 120:
            pending_error = "host supervisor exceeded the 12 h wall limit"
            subprocess.run(
                ["docker", "stop", "--time", "60", name],
                cwd=ROOT,
                capture_output=True,
                timeout=90,
                check=False,
            )
            break
        if now >= next_sample:
            stats = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", name],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            stats_json = None
            if stats.returncode == 0:
                try:
                    stats_json = json.loads(stats.stdout.strip().splitlines()[-1])
                except (json.JSONDecodeError, IndexError):
                    pass
            sample = {
                "utc": utc_now(),
                "docker_stats_exit_code": stats.returncode,
                "docker_stats": stats_json,
                "free_disk_bytes": free_disk_bytes(ROOT),
                "bundle_bytes": tree_size(run_dir),
            }
            with (run_dir / "resource-samples.jsonl").open("a", encoding="utf-8") as out:
                out.write(json.dumps(sample, sort_keys=True) + "\n")
            if sample["free_disk_bytes"] < MIN_FREE_DISK_BYTES:
                pending_error = "free disk fell below 60 GiB"
                subprocess.run(
                    ["docker", "stop", "--time", "60", name],
                    cwd=ROOT,
                    capture_output=True,
                    timeout=90,
                    check=False,
                )
                break
            if sample["bundle_bytes"] >= FOOTPRINT_LIMIT_BYTES:
                pending_error = "run bundle reached its 15 GiB footprint cap"
                subprocess.run(
                    ["docker", "stop", "--time", "60", name],
                    cwd=ROOT,
                    capture_output=True,
                    timeout=90,
                    check=False,
                )
                break
            next_sample = now + 600.0
        monitor_rc = monitor.poll()
        if monitor_rc not in (None, 0):
            pending_error = f"checkpoint monitor exited {monitor_rc}"
            subprocess.run(
                ["docker", "stop", "--time", "60", name],
                cwd=ROOT,
                capture_output=True,
                timeout=90,
                check=False,
            )
            break
        time.sleep(30)
    try:
        docker_client_rc = solver.wait(timeout=120)
    except subprocess.TimeoutExpired:
        solver.kill()
        docker_client_rc = solver.wait()
        pending_error = pending_error or "Docker client did not exit after container stop"
    if monitor.poll() is None:
        try:
            monitor_rc = monitor.wait(timeout=900)
        except subprocess.TimeoutExpired:
            monitor.terminate()
            try:
                monitor_rc = monitor.wait(timeout=15)
            except subprocess.TimeoutExpired:
                monitor.kill()
                monitor_rc = monitor.wait()
            pending_error = (
                pending_error or "checkpoint monitor did not finish after container exit"
            )
    else:
        monitor_rc = int(monitor.returncode or 0)
    inspect = docker_inspect(name)
    log_text = (run_dir / "flow.log").read_text(encoding="utf-8", errors="replace")
    last_times = re.findall(r"(?m)^Time\s*=\s*([0-9.eE+-]+)\s*$", log_text)
    stages = {
        match.group(1): int(match.group(2))
        for match in re.finditer(
            r"(?m)^ROUAIX_STAGE_EXIT stage=([A-Za-z0-9_-]+) code=(-?\d+)\s*$",
            log_text,
        )
    }
    expected_stages = {
        "dictionary-time-precision": 0,
        "dictionary-ranks": 0,
        "solver": 0,
        "reconstruct": 0,
    }
    solver_ok = (
        docker_client_rc == 0
        and inspect is not None
        and inspect.get("exit_code") == 0
        and stages == expected_stages
        and monitor_rc == 0
        and not (run_dir / "checkpoint-guard-failure.txt").exists()
        and pending_error is None
    )
    result = {
        "status": "completed_exploratory" if solver_ok else "failed_or_stopped",
        "finished_utc": utc_now(),
        "worker_wall_s": round(time.monotonic() - start, 3),
        "docker_client_exit_code": docker_client_rc,
        "container_inspect": inspect,
        "container_id": cid,
        "monitor_exit_code": monitor_rc,
        "stop_reason": pending_error,
        "stage_exit_codes": stages,
        "last_solver_time_s": float(last_times[-1]) if last_times else None,
        "log": "flow.log",
    }
    write_json(run_dir / "solver-result.json", result)
    state.update(result)
    write_json(state_path, state)
    (run_dir / "worker.exit").write_text("0\n" if solver_ok else "1\n", encoding="ascii")
    return 0 if solver_ok else 1


def make_run_id() -> str:
    return "rouaix-c4-reproduction-5s-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--launch-prepared", type=Path)
    mode.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--run-id")
    parser.add_argument("--end-time-s", type=float, default=5.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.prepare_only:
            run_id = args.run_id or make_run_id()
            run_dir = prepare(run_id, args.end_time_s)
            print(
                json.dumps(
                    {
                        "status": "prepared",
                        "run_dir": str(run_dir),
                        "case": str(run_dir / "case.json"),
                        "checkpoint": CHECKPOINT_NAME,
                        "free_disk_gib": free_disk_bytes(ROOT) / 1024**3,
                    },
                    indent=2,
                )
            )
            return 0
        if args.launch_prepared:
            record = launch(args.launch_prepared.resolve())
            print(json.dumps(record, indent=2, sort_keys=True))
            return 0
        assert args.worker is not None
        return solver_worker(args.worker.resolve())
    except (OSError, RunError, subprocess.SubprocessError, ValueError, KeyError) as error:
        print(f"Rouaix reproduction failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
