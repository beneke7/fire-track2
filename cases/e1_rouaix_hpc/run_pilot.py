#!/usr/bin/env python3
"""Run one fail-closed, native Slurm Rouaix Case 1 startup pilot."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_PROJECT_ROOT = Path("/scratch/nk_meshapplied/bene/fire-track2-hpc")
DEFAULT_SHARED_PAUSE = Path("/project/nk_meshapplied/bene/fire-track2-hpc/PAUSE")
MODULE_NAME = "OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH"
JOB_NAME = "ml-vof"
RANKS = 64
MEMORY_GIB = 64
WALL_TIME_S = 1200
HORIZON_S = 0.05
DELTA_T_S = 0.001
SUPPORTED_DELTA_T_S = (0.001, 0.0005, 0.0001)
SUPPORTED_HORIZONS_S = (0.01, HORIZON_S, 0.5, 5.0)
NUMERICAL_VARIANTS = ("original", "upwind", "u_gradient_limited")
MOMENTUM_CONVECTION_BY_VARIANT = {
    "original": "limitedLinearV 1",
    "upwind": "upwind",
    "u_gradient_limited": "limitedLinearV 1",
}
VELOCITY_GRADIENT_BY_VARIANT = {
    "original": "grad(U) Gauss linear;",
    "upwind": "grad(U) Gauss linear;",
    "u_gradient_limited": "grad(U) cellLimited Gauss linear 1;",
}
FVSCHEMES_OVERRIDE_BY_VARIANT = {
    "upwind": ("div(rhoPhi,U) Gauss limitedLinearV 1;", "div(rhoPhi,U) Gauss upwind;"),
    "u_gradient_limited": ("grad(U) Gauss linear;", "grad(U) cellLimited Gauss linear 1;"),
}
SUPPORTED_PLACEMENTS = {
    64: (1, (64,)),
    96: (1, (96,)),
    120: (1, (120,)),
    240: (2, (120, 120)),
    300: (3, (100, 100, 100)),
}
STOP_SIGNAL_SOURCE_RELATIVE = Path("src/OSspecific/POSIX/signals/sigStopAtWriteNow.cxx")
STOP_SIGNAL_SOURCE_SHA256 = "5571278a48efd49507546d9ac4aa419519010d5a2de822992d53e287761a7a03"
MAX_SPEED_M_S = 1000.0
NO_PROGRESS_S = 600.0
MIN_FREE_DISK_BYTES = 12 * 1024**3
DEADLINE_GRACE_S = 180.0
CHECKPOINT_GRACE_S = 120.0
TERM_GRACE_S = 20.0
KILL_GRACE_S = 30.0
STATE_INTERVAL_S = 30.0
POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
REQUIRED_INPUTS = {
    "mesh-input/mesh-manifest.json",
    "mesh-input/nozzle-audit.json",
    "mesh-input/raw-nozzle-audit.json",
    "mesh-input/checkMesh.log",
    *(f"mesh-input/constant/polyMesh/{name}" for name in POLYMESH_FILES),
}
TIME_LINE = re.compile(r"^\s*Time\s*=\s*(\S+)")
MAX_U_LINE = re.compile(r"max\s*\(\s*mag\s*\(\s*U\s*\)\s*\)\s*=\s*(\S+)")
MIN_MAX_U_LINE = re.compile(r"min\s*/\s*max\s*\(\s*mag\s*\(\s*U\s*\)\s*\)\s*=\s*(\S+)\s+(\S+)")
MIN_MAX_U_PREFIX = re.compile(r"min\s*/\s*max\s*\(\s*mag\s*\(\s*U\s*\)\s*\)\s*=")
CLOCK_TIME_LINE = re.compile(r"\bClockTime\s*=\s*(\S+)\s+s\b")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXTERNAL_SIGNAL: int | None = None


class PilotError(RuntimeError):
    """A preparation, provenance, or monitor condition stopped this attempt."""


class PilotStopped(PilotError):
    def __init__(self, reason: str, *, paused: bool = False) -> None:
        super().__init__(reason)
        self.paused = paused


@dataclass(frozen=True)
class PilotConfig:
    ranks: int = RANKS
    nodes: int = 1
    wall_budget_s: int = WALL_TIME_S
    horizon_s: float = HORIZON_S
    delta_t_s: float = DELTA_T_S
    numerical_variant: str = "original"
    write_interval_s: float | None = None
    retention_mode: str = "full"
    minimum_free_disk_gib: int = 12

    def validate(self) -> PilotConfig:
        placement = SUPPORTED_PLACEMENTS.get(self.ranks)
        if placement is None or self.nodes != placement[0]:
            raise PilotError(
                "supported rank/node placements are 64/1, 96/1, 120/1, 240/2, or 300/3"
            )
        if self.delta_t_s not in SUPPORTED_DELTA_T_S:
            raise PilotError("fixed deltaT must be one of 0.001, 0.0005, or 0.0001 s")
        if self.horizon_s not in SUPPORTED_HORIZONS_S:
            raise PilotError(
                "end time must be one of the declared 0.01, 0.05, 0.5, or 5.0 s horizons"
            )
        if self.numerical_variant not in NUMERICAL_VARIANTS:
            raise PilotError(f"numerical variant must be one of {NUMERICAL_VARIANTS}")
        if self.retention_mode not in {"full", "diagnostic"}:
            raise PilotError("retention mode must be full or diagnostic")
        if (
            isinstance(self.minimum_free_disk_gib, bool)
            or not isinstance(self.minimum_free_disk_gib, int)
            or not 4 <= self.minimum_free_disk_gib <= 64
        ):
            raise PilotError("minimum free disk must be an integer from 4 through 64 GiB")
        write_interval = (
            self.write_interval_s if self.write_interval_s is not None else self.horizon_s
        )
        if (
            isinstance(write_interval, bool)
            or not math.isfinite(write_interval)
            or write_interval <= 0
            or (
                write_interval != self.horizon_s
                and not (self.horizon_s == 5.0 and write_interval == 1.0)
            )
        ):
            raise PilotError("write interval must equal the horizon, except 1 s for the 5 s case")
        write_count = self.horizon_s / write_interval
        if not math.isclose(write_count, round(write_count), rel_tol=0.0, abs_tol=1e-9):
            raise PilotError("write interval must divide the horizon exactly")
        interval_steps = write_interval / self.delta_t_s
        if not math.isclose(interval_steps, round(interval_steps), rel_tol=0.0, abs_tol=1e-9):
            raise PilotError("write interval must align with fixed time steps")
        steps = self.horizon_s / self.delta_t_s
        if not math.isfinite(steps) or not math.isclose(
            steps, round(steps), rel_tol=0, abs_tol=1e-9
        ):
            raise PilotError("end time must contain an integer number of fixed time steps")
        minimum_wall = DEADLINE_GRACE_S + CHECKPOINT_GRACE_S + TERM_GRACE_S + KILL_GRACE_S + 30
        if isinstance(self.wall_budget_s, bool) or self.wall_budget_s <= minimum_wall:
            raise PilotError(
                f"wall budget must exceed the {minimum_wall} s stop-and-checkpoint allowance"
            )
        return self


def _tasks_per_node(value: str) -> tuple[int, ...]:
    result: list[int] = []
    for item in value.split(","):
        match = re.fullmatch(r"(\d+)(?:\(x(\d+)\))?", item.strip())
        if match is None:
            raise PilotError(f"cannot parse SLURM_TASKS_PER_NODE={value!r}")
        tasks, repetitions = int(match.group(1)), int(match.group(2) or 1)
        if tasks <= 0 or repetitions <= 0:
            raise PilotError("SLURM_TASKS_PER_NODE must contain positive counts")
        result.extend([tasks] * repetitions)
    return tuple(result)


def _validate_allocation(config: PilotConfig, env: dict[str, str]) -> dict[str, Any]:
    config.validate()
    nodes, expected_layout = SUPPORTED_PLACEMENTS[config.ranks]
    if env.get("SLURM_JOB_NAME") != JOB_NAME or env.get("SLURM_JOB_ACCOUNT") != "nk_meshapplied":
        raise PilotError("Slurm job name/account do not match the declared Rouaix pilot")
    if env.get("SLURM_JOB_NUM_NODES") != str(nodes) or env.get("SLURM_NTASKS") != str(config.ranks):
        raise PilotError("allocated Slurm node/rank counts differ from explicit case parameters")
    if env.get("SLURM_CPUS_PER_TASK") != "1":
        raise PilotError("the pilot requires one CPU per MPI task")
    try:
        actual_layout = _tasks_per_node(env["SLURM_TASKS_PER_NODE"])
        cpus_on_node = int(env["SLURM_CPUS_ON_NODE"])
        memory_mb_per_node = int(env["SLURM_MEM_PER_NODE"])
    except (KeyError, ValueError) as error:
        raise PilotError("Slurm allocation must report tasks per node, CPUs, and memory") from error
    if actual_layout != expected_layout:
        raise PilotError(
            f"Slurm tasks per node {actual_layout} differ from declared layout {expected_layout}"
        )
    if cpus_on_node < max(expected_layout):
        raise PilotError("allocated CPUs on node are fewer than the requested MPI tasks per node")
    if memory_mb_per_node < MEMORY_GIB * 1024:
        raise PilotError("allocated memory is below the 64 GiB per-node starting floor")
    if sum(actual_layout) != config.ranks:
        raise PilotError("Slurm task distribution does not sum to the declared MPI rank count")
    return {
        "nodes": nodes,
        "ranks": config.ranks,
        "tasks_per_node": list(actual_layout),
        "cpus_per_task": 1,
        "cpus_on_node": cpus_on_node,
        "memory_mb_per_node": memory_mb_per_node,
        "memory_gib_per_node": math.ceil(memory_mb_per_node / 1024),
        "memory_gib_total": math.ceil(memory_mb_per_node / 1024) * nodes,
        "node_list": env.get("SLURM_JOB_NODELIST", "unknown"),
        "wall_budget_s_declared": config.wall_budget_s,
        "slurm_job_start_time": env.get("SLURM_JOB_START_TIME"),
        "slurm_job_end_time": env.get("SLURM_JOB_END_TIME"),
    }


def _record_external_signal(signum: int, _frame: Any) -> None:
    global _EXTERNAL_SIGNAL
    _EXTERNAL_SIGNAL = signum


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PilotError(f"expected a JSON object in {path}")
    return value


def _safe_archive_name(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise PilotError(f"unsafe archive member name: {name!r}")
    normalized = name.rstrip("/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise PilotError(f"unsafe archive member path: {name!r}")
    return path


def validate_input_archive(archive: Path) -> list[tarfile.TarInfo]:
    """Check the compact input bundle before extracting any member."""
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
    if not members or len(members) >= 100:
        raise PilotError("input archive must contain 1–99 members")
    names: set[str] = set()
    for member in members:
        member_path = _safe_archive_name(member.name)
        name = member_path.as_posix()
        if name in names:
            raise PilotError(f"duplicate input archive member: {name}")
        names.add(name)
        if not (member.isdir() or member.isfile()):
            raise PilotError(f"input archive contains a link or special file: {name}")
        if name != "mesh-input" and not name.startswith("mesh-input/"):
            raise PilotError(f"unexpected input archive root: {name}")
    if not REQUIRED_INPUTS.issubset(names):
        missing = sorted(REQUIRED_INPUTS - names)
        raise PilotError(f"input archive is missing required files: {missing}")
    return members


def extract_input_archive(
    archive: Path, destination: Path, members: list[tarfile.TarInfo] | None = None
) -> None:
    members = validate_input_archive(archive) if members is None else members
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as tar:
        for member in members:
            relative = _safe_archive_name(member.name)
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise PilotError(f"cannot read input member {member.name}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1 << 20)
    for relative in REQUIRED_INPUTS:
        path = destination / relative
        if path.is_symlink() or not path.is_file():
            raise PilotError(f"required input did not extract as a regular file: {relative}")


def validate_raw_nozzle_binding(mesh_input: Path) -> dict[str, Any]:
    receipt_path = mesh_input / "nozzle-audit.json"
    receipt = read_json_object(receipt_path)
    if receipt.get("raw_audit_path") != "raw-nozzle-audit.json":
        raise PilotError("nozzle adapter must bind the preserved raw-nozzle-audit.json")
    raw_path = mesh_input / "raw-nozzle-audit.json"
    expected = receipt.get("raw_audit_sha256")
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        raise PilotError("nozzle adapter raw_audit_sha256 is invalid")
    if sha256_file(raw_path) != expected:
        raise PilotError("preserved raw nozzle audit does not match the adapter receipt")
    return receipt


def _receipt_relative_path(root: Path, relative_value: Any, *, label: str) -> Path:
    if not isinstance(relative_value, str) or not relative_value:
        raise PilotError(f"{label} path must be a nonempty relative path")
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise PilotError(f"{label} path escapes the mesh-input archive")
    candidate = root.joinpath(*relative.parts)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise PilotError(f"{label} path escapes the mesh-input archive") from error
    return candidate


def expected_input_files(mesh_input: Path) -> set[str]:
    expected = set(REQUIRED_INPUTS)
    manifest = read_json_object(mesh_input / "mesh-manifest.json")
    native = manifest.get("native_qa")
    if not isinstance(native, dict):
        raise PilotError("mesh manifest native_qa is missing or malformed")
    exception_ref = native.get("qualification_exception")
    if exception_ref is None:
        return expected
    if not isinstance(exception_ref, dict) or set(exception_ref) != {"path", "sha256"}:
        raise PilotError("mesh manifest qualification_exception must contain path and sha256")
    receipt_path = _receipt_relative_path(
        mesh_input, exception_ref.get("path"), label="qualification exception receipt"
    )
    expected.add(f"mesh-input/{receipt_path.relative_to(mesh_input).as_posix()}")
    receipt = read_json_object(receipt_path)
    for record_name in (
        "native_ids",
        "reference_ids",
        "native_set",
        "reference_set",
        "independent_audit",
        "review",
        "audit_tool",
        "audit_tool_helper",
    ):
        reference = receipt.get(record_name)
        if not isinstance(reference, dict):
            raise PilotError(f"qualification exception is missing {record_name}")
        support_path = _receipt_relative_path(
            receipt_path.parent, reference.get("path"), label=f"qualification {record_name}"
        )
        try:
            expected.add(f"mesh-input/{support_path.relative_to(mesh_input).as_posix()}")
        except ValueError as error:
            raise PilotError(f"qualification {record_name} is outside mesh-input") from error
    return expected


def validate_extracted_input_inventory(
    mesh_input: Path, archive_members: list[tarfile.TarInfo]
) -> set[str]:
    expected = expected_input_files(mesh_input)
    actual = {
        path.relative_to(mesh_input.parent).as_posix()
        for path in mesh_input.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise PilotError(
            f"extracted input files differ from the explicit receipt inventory; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    archive_files = {
        _safe_archive_name(member.name).as_posix() for member in archive_members if member.isfile()
    }
    if archive_files != expected:
        raise PilotError(
            f"input archive file members differ from the receipt inventory; "
            f"missing={sorted(expected - archive_files)}, extra={sorted(archive_files - expected)}"
        )
    return expected


def copy_input_evidence(
    mesh_input: Path,
    attempt: Path,
    archive_sha256: str,
    member_count: int,
    file_inventory: set[str],
) -> None:
    evidence = attempt / "input-evidence"
    evidence.mkdir(parents=True)
    for member in sorted(file_inventory):
        if "/constant/polyMesh/" in member:
            continue
        relative = PurePosixPath(member).relative_to("mesh-input")
        target = evidence / Path(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mesh_input / Path(*relative.parts), target)
    write_json(
        evidence / "input-archive.json",
        {
            "sha256": archive_sha256,
            "member_count": member_count,
            "layout": sorted(file_inventory),
        },
    )


def _filesystem_details(path: Path) -> tuple[str, str]:
    result = subprocess.run(
        ["findmnt", "-T", str(path), "-n", "-o", "FSTYPE,SOURCE"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if result.returncode != 0:
        return "unknown", "unknown"
    fields = result.stdout.split()
    return (fields[0], fields[1]) if len(fields) >= 2 else ("unknown", "unknown")


def select_node_local_workspace(
    env: dict[str, str], *, min_free_bytes: int = MIN_FREE_DISK_BYTES
) -> tuple[Path, dict[str, Any]]:
    """Select only job-local block storage with enough measured free space."""
    home = Path(env["HOME"]).resolve() if env.get("HOME") else None
    for value in (env.get("SLURM_TMPDIR"), env.get("TMPDIR"), "/tmp"):
        if not value:
            continue
        candidate = Path(value)
        if not candidate.is_dir() or not os.access(candidate, os.W_OK):
            continue
        real = candidate.resolve(strict=True)
        if any(
            str(real) == root or str(real).startswith(f"{root}/")
            for root in ("/project", "/scratch", "/home")
        ):
            continue
        if home is not None and (real == home or home in real.parents):
            continue
        fs_type, source = _filesystem_details(real)
        free = shutil.disk_usage(real).free
        if fs_type not in {"ext4", "xfs", "btrfs"} or not source.startswith("/dev/"):
            continue
        if free < min_free_bytes:
            continue
        return real, {
            "path": str(real),
            "filesystem_type": fs_type,
            "filesystem_source": source,
            "free_bytes_at_selection": free,
            "storage_class": "node-local-block",
        }
    gib = min_free_bytes / 1024**3
    raise PilotError(f"no qualifying node-local block filesystem has at least {gib:g} GiB free")


def create_workspace(
    env: dict[str, str],
    job_id: str,
    *,
    nodes: int = 1,
    min_free_bytes: int = MIN_FREE_DISK_BYTES,
) -> tuple[Path, dict[str, Any]]:
    shared_choice = env.get("ROUAIX_REQUIRE_SHARED_WORKSPACE")
    if shared_choice not in {None, "0", "1"}:
        raise PilotError("ROUAIX_REQUIRE_SHARED_WORKSPACE must be 0 or 1")
    if nodes == 1 and shared_choice != "1":
        try:
            base, record = select_node_local_workspace(env, min_free_bytes=min_free_bytes)
        except PilotError:
            base = Path(env.get("ROUAIX_PROJECT_ROOT", str(DEFAULT_PROJECT_ROOT))).resolve(
                strict=True
            )
            free = shutil.disk_usage(base).free
            if free < min_free_bytes:
                raise PilotError(
                    "node-local storage is unavailable and project scratch is below the declared free-space floor"
                )
            fs_type, source = _filesystem_details(base)
            record = {
                "path": str(base),
                "filesystem_type": fs_type,
                "filesystem_source": source,
                "free_bytes_at_selection": free,
                "storage_class": "shared-scratch-fallback-packed-after-run",
            }
    else:
        base = Path(env.get("ROUAIX_PROJECT_ROOT", str(DEFAULT_PROJECT_ROOT))).resolve(strict=True)
        free = shutil.disk_usage(base).free
        if free < min_free_bytes:
            label = "multi-node" if nodes > 1 else "required shared"
            raise PilotError(
                f"{label} workspace is below the declared free-space floor on shared project scratch"
            )
        fs_type, source = _filesystem_details(base)
        record = {
            "path": str(base),
            "filesystem_type": fs_type,
            "filesystem_source": source,
            "free_bytes_at_selection": free,
            "storage_class": (
                "shared-project-scratch-required-for-multinode"
                if nodes > 1
                else "shared-project-scratch-required"
            ),
        }
    workspace = Path(tempfile.mkdtemp(prefix=f"rouaix-e1hpc-{job_id}.", dir=base))
    record["workspace"] = str(workspace.resolve())
    return workspace, record


def _record_disk_space(state: dict[str, Any], local_path: Path, shared_path: Path) -> int:
    snapshot = {
        "workspace_free_bytes": shutil.disk_usage(local_path).free,
        "shared_run_free_bytes": shutil.disk_usage(shared_path).free,
    }
    minimum = min(snapshot.values())
    state["free_disk_bytes_last"] = snapshot
    state["free_disk_bytes_min_observed"] = min(
        minimum, state.get("free_disk_bytes_min_observed", minimum)
    )
    return minimum


def case_file_hashes(case: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(case.rglob("*")):
        if path.is_symlink():
            raise PilotError(f"prepared case contains a symbolic link: {path}")
        if path.is_file():
            hashes[path.relative_to(case).as_posix()] = sha256_file(path)
    if not hashes:
        raise PilotError("prepared case has no regular input files")
    return hashes


def verify_checkpoint_retention(
    case: Path, prepared_hashes: dict[str, str], *, horizon_s: float
) -> dict[str, Any]:
    for relative, expected in prepared_hashes.items():
        if relative.startswith("0/"):
            path = case / relative
            if path.is_symlink() or not path.is_file() or sha256_file(path) != expected:
                raise PilotError(
                    f"solver or purgeWrite changed the immutable initial field {relative}"
                )
    positive_times: set[str] = set()
    for processor in case.iterdir():
        if processor.is_symlink():
            raise PilotError(f"unexpected symlink in prepared case after solve: {processor}")
        if processor.is_dir() and re.fullmatch(r"processors\d+", processor.name):
            for time_dir in processor.iterdir():
                if time_dir.is_symlink():
                    raise PilotError(
                        f"unexpected symlink in checkpoint tree after solve: {time_dir}"
                    )
                if time_dir.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", time_dir.name):
                    if float(time_dir.name) > 0:
                        positive_times.add(time_dir.name)
    if horizon_s == 5.0 and len(positive_times) > 2:
        raise PilotError("purgeWrite retained more than two positive-time checkpoints")
    return {
        "initial_global_t0_preserved": True,
        "positive_checkpoint_times_s": sorted(float(value) for value in positive_times),
        "retained_positive_checkpoint_count": len(positive_times),
        "retained_positive_checkpoint_limit": 2 if horizon_s == 5.0 else None,
    }


def validate_prepared_case(
    case: Path, config: PilotConfig | None = None
) -> tuple[dict[str, Any], dict[str, str]]:
    config = (config or PilotConfig()).validate()
    inputs = read_json_object(case / "case-inputs.json")
    if (
        inputs.get("execution_backend") != "slurm-native"
        or inputs.get("solver_version") != "v2512"
        or inputs.get("ranks") != config.ranks
        or inputs.get("node_count") != config.nodes
        or inputs.get("horizon_s") != config.horizon_s
        or inputs.get("numerical_variant") != config.numerical_variant
    ):
        raise PilotError(
            "prepared case differs from the declared native Slurm placement/horizon/numerics"
        )
    write_interval = (
        config.write_interval_s if config.write_interval_s is not None else config.horizon_s
    )
    controls = inputs.get("time_controls", {})
    expected_purge_write = 2 if config.horizon_s == 5.0 and write_interval == 1.0 else 0
    checkpoint_policy = controls.get("checkpoint_policy", {}) if isinstance(controls, dict) else {}
    if (
        not isinstance(controls, dict)
        or controls.get("delta_t_s") != config.delta_t_s
        or controls.get("fixed_delta_t") is not True
        or controls.get("adjust_time_step") is not False
        or controls.get("nAlphaSubCycles") != 1
        or controls.get("snapshot_interval_s") != write_interval
        or controls.get("purge_write") != expected_purge_write
        or not isinstance(checkpoint_policy, dict)
        or checkpoint_policy.get("scheduled_field_write_times_s")
        != controls.get("full_field_write_times_s")
        or checkpoint_policy.get("retained_positive_checkpoint_limit")
        != (2 if expected_purge_write == 2 else None)
        or checkpoint_policy.get("preserve_initial_global_t0") is not True
        or checkpoint_policy.get("retain_all_per_step_metrics") is not True
    ):
        raise PilotError("prepared case is not the declared fixed-step, no-subcycle pilot")
    source_dictionaries = inputs.get("source_dictionary_provenance")
    source_schemes = (
        source_dictionaries.get("system/fvSchemes")
        if isinstance(source_dictionaries, dict)
        else None
    )
    parent_hash = source_schemes.get("sha256") if isinstance(source_schemes, dict) else None
    actual_scheme_hash = sha256_file(case / "system/fvSchemes")
    dictionary_hashes = inputs.get("solver_dictionary_sha256")
    expected_scheme_hash = (
        dictionary_hashes.get("system/fvSchemes") if isinstance(dictionary_hashes, dict) else None
    )
    schemes_text = (case / "system/fvSchemes").read_text(encoding="utf-8")
    template_schemes_path = ROOT / "cases/e1_rouaix_hpc/template/system/fvSchemes"
    try:
        parent_schemes_text = template_schemes_path.read_text(encoding="utf-8")
        trusted_parent_hash = sha256_file(template_schemes_path)
    except OSError as error:
        raise PilotError("trusted parent fvSchemes dictionary is unavailable") from error
    expected_schemes_text = parent_schemes_text
    scheme_override = FVSCHEMES_OVERRIDE_BY_VARIANT.get(config.numerical_variant)
    if scheme_override is not None:
        original_scheme, diagnostic_scheme = scheme_override
        if parent_schemes_text.count(original_scheme) != 1:
            raise PilotError(
                "trusted parent fvSchemes does not contain one declared override entry"
            )
        expected_schemes_text = parent_schemes_text.replace(original_scheme, diagnostic_scheme, 1)
    assumptions = inputs.get("numerical_assumptions")
    expected_momentum = MOMENTUM_CONVECTION_BY_VARIANT[config.numerical_variant]
    expected_gradient = VELOCITY_GRADIENT_BY_VARIANT[config.numerical_variant]
    expected_limiter_scope = (
        "cellLimited Gauss linear 1 on grad(U) only; grad(k) and grad(epsilon) unchanged"
        if config.numerical_variant == "u_gradient_limited"
        else "no velocity-gradient limiter override"
    )
    expected_limiter_note = (
        "OpenFOAM cellLimited Gauss linear 1 is a bounded diagnostic choice, not the "
        "Rouaix paper's Venkatakrishnan or hybrid least-squares scheme"
        if config.numerical_variant == "u_gradient_limited"
        else None
    )
    if (
        not isinstance(parent_hash, str)
        or parent_hash != trusted_parent_hash
        or inputs.get("parent_fvSchemes_sha256") != parent_hash
        or inputs.get("post_override_fvSchemes_sha256") != actual_scheme_hash
        or expected_scheme_hash != actual_scheme_hash
        or schemes_text != expected_schemes_text
        or schemes_text.count(expected_gradient) != 1
        or inputs.get("actual_momentum_convection") != expected_momentum
        or inputs.get("actual_velocity_gradient_scheme") != expected_gradient
        or not isinstance(assumptions, dict)
        or assumptions.get("numerical_variant") != config.numerical_variant
        or assumptions.get("momentum_convection") != expected_momentum
        or assumptions.get("velocity_gradient_scheme") != expected_gradient
        or assumptions.get("velocity_gradient_limiter_scope") != expected_limiter_scope
        or assumptions.get("velocity_gradient_diagnostic_note") != expected_limiter_note
        or assumptions.get("parent_fvSchemes_sha256") != parent_hash
        or assumptions.get("post_override_fvSchemes_sha256") != actual_scheme_hash
    ):
        raise PilotError("prepared fvSchemes does not match its declared variant and hash chain")
    control_text = (case / "system/controlDict").read_text(encoding="utf-8")
    required = (
        "stopAt endTime;",
        f"endTime {config.horizon_s:.12g};",
        f"deltaT {config.delta_t_s:.12g};",
        "adjustTimeStep no;",
        "runTimeModifiable false;",
        "fileHandler collated;",
        "maxThreadFileBufferSize 0;",
        "writeNowSignal 10;",
        "stopAtWriteNowSignal 12;",
        f"writeInterval {write_interval:.12g};",
        f"purgeWrite {expected_purge_write};",
        "speedExtrema",
        "fieldMinMax",
        "mode magnitude;",
    )
    if any(token not in control_text for token in required):
        raise PilotError(
            "prepared controlDict is missing fixed controls, per-step U extrema, or stop signal"
        )
    if control_text.count("stopAtWriteNowSignal") != 1:
        raise PilotError("controlDict must configure exactly one write-and-stop signal")
    return inputs, case_file_hashes(case)


def verify_stop_signal_source(attempt: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = read_json_object(manifest_path)
    evidence_path = Path(str(manifest.get("native_source_evidence_path", "")))
    evidence = read_json_object(evidence_path)
    native_solver = evidence.get("native_solver")
    if not isinstance(native_solver, dict):
        raise PilotError("native source evidence lacks native_solver identity")
    project_root = Path(str(native_solver.get("wm_project_dir", ""))).resolve(strict=True)
    source_link = project_root / STOP_SIGNAL_SOURCE_RELATIVE
    try:
        source = source_link.resolve(strict=True)
    except OSError as error:
        raise PilotError("installed native write-and-stop source is missing") from error
    if not source.is_file() or not source.is_relative_to(project_root):
        raise PilotError("installed native write-and-stop source is missing")
    source_text = source.read_text(encoding="utf-8", errors="replace")
    source_sha256 = sha256_file(source)
    if source_sha256 != STOP_SIGNAL_SOURCE_SHA256:
        raise PilotError("installed write-and-stop source differs from the pinned v2512 source")
    if "stopAtWriteNowSignal" not in source_text or "Time::saWriteNow" not in source_text:
        raise PilotError(
            "installed signal source does not document stopAtWriteNowSignal/write-and-stop"
        )
    banner_path = attempt / "input-evidence/checkMesh.log"
    banner = banner_path.read_text(encoding="utf-8", errors="replace")
    if not re.search(
        r"sigStopAtWriteNow\s*:\s*Enabling writing and stopping upon signal 12\b", banner
    ):
        raise PilotError("native solver banner did not confirm write-and-stop signal 12")
    record = {
        "requested_path": str(source_link),
        "path": str(source),
        "resolved_symlink": source_link.is_symlink(),
        "sha256": source_sha256,
        "required_source_tokens": ["stopAtWriteNowSignal", "Time::saWriteNow"],
        "signal_number": 12,
        "native_checkMesh_banner_path": str(banner_path.resolve()),
        "runtime_banner_sha256": sha256_file(banner_path),
        "interpretation": "Native source exposes write-and-stop; loaded solver banner confirms signal 12.",
    }
    manifest["write_and_stop_signal"] = record
    write_json(manifest_path, manifest)
    return record


@dataclass
class OutputMonitor:
    last_progress_monotonic: float
    current_time_s: float | None = 0.0
    horizon_s: float = HORIZON_S
    delta_t_s: float = DELTA_T_S
    current_max_u_m_s: float | None = None
    maximum_u_m_s: float = 0.0
    sample_count: int = 0
    pending_fault: str | None = None
    saw_end_marker: bool = False
    rows: list[tuple[float, float]] = field(default_factory=list)
    clock_samples: list[tuple[float, float]] = field(default_factory=list)

    def feed(self, line: str, now: float) -> str | None:
        if line.strip() == "End":
            self.saw_end_marker = True
        if re.search(r"(?i)(?<![a-z])[-+]?(?:nan|inf(?:inity)?)(?![a-z])", line):
            return f"nonfinite solver diagnostic: {line.strip()}"
        time_match = TIME_LINE.match(line)
        if time_match:
            try:
                value = float(time_match.group(1))
            except ValueError:
                return "solver printed a nonnumeric time"
            if not math.isfinite(value):
                return "solver printed a nonfinite time"
            if self.current_time_s is not None and value < self.current_time_s - 1e-12:
                return "solver time moved backwards"
            if self.current_time_s is None:
                self.last_progress_monotonic = now
                self.current_time_s = value
                self.current_max_u_m_s = None
            elif value > self.current_time_s + 1e-12:
                self._finish_current()
                if self.pending_fault:
                    return self.pending_fault
                self.last_progress_monotonic = now
                self.current_time_s = value
                self.current_max_u_m_s = None
            return None

        clock_match = CLOCK_TIME_LINE.search(line)
        if clock_match:
            if self.current_time_s is None:
                return "ClockTime appeared before a solver time line"
            try:
                clock_time = float(clock_match.group(1))
            except ValueError:
                return "solver printed a nonnumeric ClockTime"
            if not math.isfinite(clock_time) or clock_time < 0:
                return "solver printed an invalid ClockTime"
            self.clock_samples.append((self.current_time_s, clock_time))
            return None

        pair_match = MIN_MAX_U_LINE.search(line)
        pair_prefix = MIN_MAX_U_PREFIX.search(line)
        if pair_prefix and pair_match is None:
            return "fieldMinMax U min/max diagnostic is malformed"
        speed_match = MAX_U_LINE.search(line) if pair_match is None else None
        if pair_match or speed_match:
            if self.current_time_s is None:
                return "fieldMinMax U magnitude appeared before a solver time line"
            if pair_match:
                minimum_token, token = (value.rstrip(",;") for value in pair_match.groups())
                try:
                    minimum = float(minimum_token)
                except ValueError:
                    return f"fieldMinMax U minimum is not numeric: {minimum_token}"
                if not math.isfinite(minimum) or minimum < 0:
                    return f"fieldMinMax U minimum is invalid: {minimum_token}"
            else:
                token = speed_match.group(1).rstrip(",;")
            try:
                speed = float(token)
            except ValueError:
                return f"fieldMinMax U magnitude is not numeric: {token}"
            if not math.isfinite(speed):
                return f"nonfinite fieldMinMax max|U|: {token}"
            if speed < 0:
                return f"fieldMinMax magnitude is negative: {speed}"
            if pair_match and minimum > speed:
                return "fieldMinMax U minimum exceeds its maximum"
            self.current_max_u_m_s = speed
            self.maximum_u_m_s = max(self.maximum_u_m_s, speed)
            if speed > MAX_SPEED_M_S:
                return f"operational stop: max|U|={speed:g} m/s exceeds {MAX_SPEED_M_S:g} m/s"
        return None

    def _finish_current(self) -> None:
        if self.current_time_s is None or self.current_time_s <= 0:
            return
        if self.current_max_u_m_s is None:
            self.pending_fault = (
                f"missing per-step fieldMinMax max|U| at t={self.current_time_s:g} s"
            )
            return
        if self.rows and self.rows[-1][0] == self.current_time_s:
            self.rows[-1] = (self.current_time_s, self.current_max_u_m_s)
        else:
            self.rows.append((self.current_time_s, self.current_max_u_m_s))

    def finish(self) -> str | None:
        self._finish_current()
        return self.pending_fault

    def completion_fault(self) -> str | None:
        step_count = round(self.horizon_s / self.delta_t_s)
        expected = [index * self.delta_t_s for index in range(1, step_count + 1)]
        if len(self.rows) != len(expected) or any(
            abs(actual - target) > 1e-9
            for (actual, _speed), target in zip(self.rows, expected, strict=True)
        ):
            return (
                f"solver log does not prove all {step_count} fixed {self.delta_t_s:g} s steps "
                f"through {self.horizon_s:g} s"
            )
        if not self.saw_end_marker:
            return "solver log lacks the native End completion marker"
        return None


def solver_clock_window(
    samples: list[tuple[float, float]], start_s: float, end_s: float
) -> dict[str, Any]:
    start = next((clock for time_s, clock in samples if abs(time_s - start_s) <= 1e-9), None)
    end = next((clock for time_s, clock in samples if abs(time_s - end_s) <= 1e-9), None)
    if start is None or end is None or end < start:
        return {
            "start_s": start_s,
            "end_s": end_s,
            "status": "unavailable_exact_clock_samples",
        }
    physical = end_s - start_s
    wall = end - start
    return {
        "start_s": start_s,
        "end_s": end_s,
        "status": "measured",
        "physical_seconds": physical,
        "solver_clock_seconds": wall,
        "physical_seconds_per_solver_clock_second": physical / wall if wall > 0 else None,
    }


def summarize_solver_clock_windows(
    samples: list[tuple[float, float]], horizon_s: float
) -> dict[str, Any]:
    windows = [(0.010, 0.049)]
    if horizon_s >= 0.5:
        windows.extend(((0.05, 0.10), (0.10, 0.25), (0.25, 0.49)))
    if horizon_s >= 5.0:
        windows.extend(((0.05, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 3.2), (3.2, 5.0)))
    return {
        f"{start:.3f}..{end:.3f}s": solver_clock_window(samples, start, end)
        for start, end in windows
        if end <= horizon_s + 1e-12
    }


def monitor_stop_reason(
    *,
    now: float,
    deadline: float,
    last_progress: float,
    paused: bool,
    free_disk_bytes: int,
    parse_fault: str | None = None,
    external_signal: int | None = None,
    minimum_free_disk_bytes: int = MIN_FREE_DISK_BYTES,
) -> tuple[str, bool] | None:
    if parse_fault:
        return parse_fault, False
    if paused:
        return "user PAUSE marker", True
    if external_signal is not None:
        return f"Slurm requested termination with signal {external_signal}", False
    if free_disk_bytes < minimum_free_disk_bytes:
        return f"free disk fell below {minimum_free_disk_bytes / 1024**3:g} GiB", False
    if now >= deadline:
        return "allocation deadline checkpoint margin reached", False
    if now - last_progress > NO_PROGRESS_S:
        return "no printed solver-time progress for 600 s", False
    return None


def pause_present(run_dir: Path, shared_pause: Path, project_root: Path) -> bool:
    return any(path.exists() for path in (run_dir / "PAUSE", shared_pause, project_root / "PAUSE"))


def _step_identity(path: Path, job_id: str, expected_ranks: int = RANKS) -> tuple[str, int]:
    if not path.is_file() or path.is_symlink():
        raise PilotError("solver Slurm step has not recorded its identity")
    fields = path.read_text(encoding="ascii").split()
    if len(fields) != 4 or fields[0] != job_id or not fields[1].isdigit():
        raise PilotError("solver step identity does not match this Slurm job")
    if fields[2] != str(expected_ranks) or fields[3] != "0":
        raise PilotError(
            f"solver Slurm step identity has an unexpected rank count or writer; "
            f"expected {expected_ranks} rank-0 writer"
        )
    step_id = fields[1]
    if step_id != "0":
        raise PilotError(f"expected the sole solver step to be {job_id}.0, got {job_id}.{step_id}")
    return step_id, int(fields[2])


def _verify_slurm_step(job_id: str, step_id: str, ranks: int) -> bool:
    result = subprocess.run(
        ["scontrol", "show", "step", "-o", f"{job_id}.{step_id}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        return False
    lines = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise PilotError("scontrol did not return exactly one Slurm step record")
    fields: dict[str, str] = {}
    for token in lines[0]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key in fields:
            raise PilotError(f"scontrol returned duplicate {key} fields")
        fields[key] = value
    if fields.get("StepId") != f"{job_id}.{step_id}" or fields.get("Tasks") != str(ranks):
        raise PilotError(
            "scontrol step identity conflicts with this job, step, or 64-task allocation"
        )
    return True


def signal_owned_step(
    job_id: str, step_path: Path, signal_name: str, expected_ranks: int = RANKS
) -> bool:
    step_id, ranks = _step_identity(step_path, job_id, expected_ranks)
    if not _verify_slurm_step(job_id, step_id, ranks):
        return False
    result = subprocess.run(
        ["scancel", f"--signal={signal_name}", f"{job_id}.{step_id}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        raise PilotError(
            f"scancel --signal={signal_name} failed for owned step {job_id}.{step_id}: "
            f"{result.stderr.strip()}"
        )
    return True


def _wait_step_exit(process: subprocess.Popen[str], wait_s: float) -> bool:
    deadline = time.monotonic() + wait_s
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    return process.poll() is not None


def stop_solver_step(
    process: subprocess.Popen[str],
    job_id: str,
    step_path: Path,
    grace_s: float,
    expected_ranks: int = RANKS,
) -> list[str]:
    """Request write-and-stop, then escalate only against the verified own step."""
    signals: list[str] = []
    signal_owned_step(job_id, step_path, "12", expected_ranks)
    signals.append("12")
    if _wait_step_exit(process, grace_s):
        return signals
    if signal_owned_step(job_id, step_path, "TERM", expected_ranks):
        signals.append("TERM")
    if _wait_step_exit(process, TERM_GRACE_S):
        return signals
    if signal_owned_step(job_id, step_path, "KILL", expected_ranks):
        signals.append("KILL")
    try:
        process.wait(timeout=KILL_GRACE_S)
    except subprocess.TimeoutExpired:
        # This handle names only this runner's srun client; the Slurm step has
        # already received KILL through its verified job.step identity.
        process.kill()
        process.wait(timeout=10)
        signals.append("srun-client-KILL")
    return signals


def _terminate_srun_client(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except ProcessLookupError:
                pass
    process.wait()


def supervise_solver(
    *,
    case: Path,
    attempt: Path,
    run_dir: Path,
    shared_pause: Path,
    project_root: Path,
    job_id: str,
    config: PilotConfig,
    deadline: float,
    state: dict[str, Any],
    write_state: Any,
) -> tuple[int, OutputMonitor, str | None, bool]:
    identity_path = attempt / "solver-step-identity.txt"
    launcher = attempt / "solver-step.sh"
    launcher.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ ${SLURM_PROCID:-} == 0 ]]; then
  printf '%s %s %s %s\\n' "${SLURM_JOB_ID:-}" "${SLURM_STEP_ID:-}" "${SLURM_NTASKS:-}" "${SLURM_PROCID:-}" > "${ROUAIX_STEP_IDENTITY}.tmp"
  mv -- "${ROUAIX_STEP_IDENTITY}.tmp" "$ROUAIX_STEP_IDENTITY"
fi
exec interIsoFoam -parallel
""",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    environment = dict(os.environ)
    environment["ROUAIX_STEP_IDENTITY"] = str(identity_path)
    command = [
        "srun",
        "--kill-on-bad-exit=1",
        f"--nodes={config.nodes}",
        f"--ntasks={config.ranks}",
        f"--ntasks-per-node={config.ranks // config.nodes}",
        "--cpus-per-task=1",
        "--cpu-bind=cores",
        "--mem-bind=local",
        "--export=ALL,ROUAIX_STEP_IDENTITY=" + str(identity_path),
        str(launcher),
    ]
    log_path = attempt / "solver.log"
    observations_path = attempt / "max-speed.csv"
    tracker = OutputMonitor(
        last_progress_monotonic=time.monotonic(),
        horizon_s=config.horizon_s,
        delta_t_s=config.delta_t_s,
    )
    process: subprocess.Popen[str] | None = None
    stop_reason: str | None = None
    paused_stop = False
    requested = False
    signals: list[str] = []
    last_state_write = time.monotonic()
    last_space_check = 0.0
    free_disk = _record_disk_space(state, attempt, run_dir)

    with (
        log_path.open("w", encoding="utf-8", buffering=1) as log,
        log_path.open("r", encoding="utf-8", buffering=1) as monitor_stream,
        observations_path.open("w", encoding="utf-8", newline="") as observations,
    ):
        writer = csv.writer(observations)
        writer.writerow(["time_s", "max_magnitude_U_m_s"])
        process = subprocess.Popen(
            command,
            cwd=case,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            while True:
                now = time.monotonic()
                line = monitor_stream.readline()
                parse_fault = None
                if line:
                    parse_fault = tracker.feed(line, now)
                    while tracker.sample_count < len(tracker.rows):
                        time_s, max_u = tracker.rows[tracker.sample_count]
                        writer.writerow([f"{time_s:.12g}", f"{max_u:.12g}"])
                        observations.flush()
                        tracker.sample_count += 1
                    if parse_fault and not requested:
                        stop_reason = parse_fault
                if now - last_space_check >= 10.0:
                    free_disk = _record_disk_space(state, attempt, run_dir)
                    last_space_check = now
                should_stop = monitor_stop_reason(
                    now=now,
                    deadline=deadline,
                    last_progress=tracker.last_progress_monotonic,
                    paused=pause_present(run_dir, shared_pause, project_root),
                    free_disk_bytes=free_disk,
                    parse_fault=stop_reason,
                    external_signal=_EXTERNAL_SIGNAL,
                    minimum_free_disk_bytes=config.minimum_free_disk_gib * 1024**3,
                )
                if should_stop and not requested:
                    stop_reason, paused_stop = should_stop
                    state.update(status="checkpoint_requested", stop_reason=stop_reason)
                    write_state(state)
                    try:
                        signals = stop_solver_step(
                            process,
                            job_id,
                            identity_path,
                            CHECKPOINT_GRACE_S,
                            config.ranks,
                        )
                    except PilotError:
                        # Never guess a step if rank zero has not recorded it.
                        _terminate_srun_client(process)
                        raise
                    requested = True
                    state["stop_signals"] = signals
                    state["stop_requested_utc"] = datetime.now(UTC).isoformat()
                    write_state(state)
                if now - last_state_write >= STATE_INTERVAL_S:
                    state.update(
                        status="running",
                        solver_time_s=tracker.current_time_s,
                        max_u_seen_m_s=tracker.maximum_u_m_s,
                        solver_elapsed_s=now - state["solver_started_monotonic"],
                        free_disk_bytes=free_disk,
                    )
                    write_state(state)
                    last_state_write = now
                if process.poll() is not None and not line:
                    break
                if not line:
                    time.sleep(0.25)
            final_fault = tracker.finish()
            if final_fault and stop_reason is None:
                stop_reason = final_fault
            if final_fault:
                state["monitor_fault_after_exit"] = final_fault
            return_code = process.wait()
            for time_s, max_u in tracker.rows[tracker.sample_count :]:
                writer.writerow([f"{time_s:.12g}", f"{max_u:.12g}"])
            observations.flush()
        finally:
            if process.poll() is None:
                try:
                    cleanup_signals = stop_solver_step(
                        process,
                        job_id,
                        identity_path,
                        CHECKPOINT_GRACE_S,
                        config.ranks,
                    )
                    state["cleanup_stop_signals"] = cleanup_signals
                except Exception:
                    # The step identity could be missing or Slurm unavailable;
                    # terminate only this runner's srun client, then reap it.
                    _terminate_srun_client(process)
            process.wait()
    if requested and not stop_reason:
        stop_reason = "monitor requested stop"
    if return_code == 0 and stop_reason is None:
        stop_reason = tracker.completion_fault()
    state.update(
        solver_exit_code=return_code,
        solver_time_s=tracker.current_time_s,
        solver_max_u_m_s=tracker.maximum_u_m_s,
        max_u_seen_m_s=tracker.maximum_u_m_s,
        solver_time_steps_recorded=len(tracker.rows),
        solver_wall_s=time.monotonic() - state["solver_started_monotonic"],
        solver_end_marker=tracker.saw_end_marker,
        solver_log_sha256=sha256_file(log_path),
        max_speed_csv_sha256=sha256_file(observations_path),
        stop_reason=stop_reason,
        stop_signals=signals,
    )
    return return_code, tracker, stop_reason, paused_stop


def run_setup_command(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    deadline: float,
    run_dir: Path,
    shared_pause: Path,
    project_root: Path,
    state: dict[str, Any],
    write_state: Any,
    minimum_free_disk_bytes: int = MIN_FREE_DISK_BYTES,
) -> None:
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        def terminate_owned_setup() -> None:
            if process.poll() is not None:
                process.wait()
                return
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()

        try:
            while process.poll() is None:
                now = time.monotonic()
                if pause_present(run_dir, shared_pause, project_root):
                    terminate_owned_setup()
                    raise PilotStopped("user PAUSE marker during serial setup", paused=True)
                if now >= deadline:
                    terminate_owned_setup()
                    raise PilotStopped("allocation deadline checkpoint margin reached during setup")
                if _EXTERNAL_SIGNAL is not None:
                    terminate_owned_setup()
                    raise PilotStopped(
                        f"Slurm requested termination with signal {_EXTERNAL_SIGNAL}"
                    )
                disk_free = _record_disk_space(state, cwd, run_dir)
                state.update(status="setup", setup_command=command[0])
                write_state(state)
                if disk_free < minimum_free_disk_bytes:
                    terminate_owned_setup()
                    raise PilotStopped(
                        f"free disk fell below {minimum_free_disk_bytes / 1024**3:g} GiB during setup"
                    )
                time.sleep(1)
            result = process.wait()
        finally:
            terminate_owned_setup()
    if result != 0:
        raise PilotError(f"setup command failed ({result}): {' '.join(command)}; log={log_path}")


def _write_step_accounting(attempt: Path, job_id: str) -> None:
    with (attempt / "slurm-step-accounting.txt").open("w", encoding="utf-8") as stream:
        for command in (
            ["sstat", "-j", f"{job_id}.0", "--format=JobID,AveCPU,MaxRSS,AveRSS"],
            ["sacct", "-j", job_id, "--format=JobID,Elapsed,TotalCPU,MaxRSS,State", "--noheader"],
        ):
            result = subprocess.run(
                command, capture_output=True, text=True, check=False, timeout=30
            )
            stream.write(f"$ {' '.join(command)}\n")
            stream.write(result.stdout or result.stderr)
            stream.write("\n")


def _foam_named_block(text: str, name: str) -> str | None:
    cleaned = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*\{{", cleaned)
    if match is None:
        return None
    opening = cleaned.find("{", match.start(), match.end())
    depth = 1
    for index in range(opening + 1, len(cleaned)):
        if cleaned[index] == "{":
            depth += 1
        elif cleaned[index] == "}":
            depth -= 1
            if depth == 0:
                return cleaned[opening + 1 : index]
    raise PilotError(f"unterminated OpenFOAM dictionary block {name}")


def _foam_child_blocks(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    key_re = re.compile(r'(?m)^\s*("[^"\n]+"|[A-Za-z0-9_.*()|]+)\s*\{')
    for match in key_re.finditer(text):
        key = match.group(1).strip('"')
        opening = text.find("{", match.start(), match.end())
        depth = 1
        for index in range(opening + 1, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    result[key] = text[opening + 1 : index]
                    break
        else:
            raise PilotError(f"unterminated OpenFOAM solver entry {key}")
    return result


def _solver_dictionary_controls(fv_solution: Path) -> tuple[dict[str, str], dict[str, int]]:
    text = fv_solution.read_text(encoding="utf-8")
    solvers_block = _foam_named_block(text, "solvers")
    pimple_block = _foam_named_block(text, "PIMPLE")
    if solvers_block is None or pimple_block is None:
        raise PilotError("fvSolution lacks solvers or PIMPLE dictionary")
    solver_entries = _foam_child_blocks(solvers_block)
    pimple_values: dict[str, int] = {}
    for key in ("nOuterCorrectors", "nCorrectors", "nNonOrthogonalCorrectors"):
        match = re.search(rf"\b{key}\s+(\d+)\s*;", pimple_block)
        if match is None:
            raise PilotError(f"fvSolution PIMPLE block lacks {key}")
        pimple_values[key] = int(match.group(1))
    return solver_entries, pimple_values


def _resolve_solver_controls(
    entries: dict[str, str], field_name: str, *, final: bool
) -> dict[str, float | int]:
    base = (
        field_name
        if field_name in {"p_rgh", "pcorr"}
        else "U"
        if field_name
        in {
            "Ux",
            "Uy",
            "Uz",
        }
        else field_name
    )
    target = f"{base}Final" if final else base
    selected = target if target in entries else None
    if selected is None:
        for key in entries:
            try:
                if re.fullmatch(key, target):
                    selected = key
                    break
            except re.error as error:
                raise PilotError(f"invalid solver-key expression in fvSolution: {key}") from error
    if selected is None and final:
        return _resolve_solver_controls(entries, field_name, final=False)
    if selected is None:
        raise PilotError(f"fvSolution has no solver controls matching field {target}")
    body = entries[selected]
    controls: dict[str, float | int] = {}
    parent = re.search(r"\$(\w+)\s*;", body)
    if parent is not None:
        if parent.group(1) == selected or parent.group(1) not in entries:
            raise PilotError(f"invalid solver dictionary inheritance for {selected}")
        controls.update(_resolve_controls_body(entries, parent.group(1), set()))
    controls.update(_parse_control_values(body))
    for required in ("tolerance", "relTol"):
        if required not in controls:
            raise PilotError(f"fvSolution solver entry {selected} lacks {required}")
    return controls


def _parse_control_values(body: str) -> dict[str, float | int]:
    values: dict[str, float | int] = {}
    for key in ("tolerance", "relTol"):
        match = re.search(rf"\b{key}\s+([^;\s]+)\s*;", body)
        if match is not None:
            try:
                values[key] = float(match.group(1))
            except ValueError as error:
                raise PilotError(f"fvSolution {key} is not numeric") from error
    for key in ("maxIter", "minIter"):
        match = re.search(rf"\b{key}\s+(\d+)\s*;", body)
        if match is not None:
            values[key] = int(match.group(1))
    return values


def _resolve_controls_body(
    entries: dict[str, str], key: str, visited: set[str]
) -> dict[str, float | int]:
    if key in visited:
        raise PilotError(f"recursive fvSolution solver inheritance at {key}")
    visited.add(key)
    body = entries[key]
    values: dict[str, float | int] = {}
    parent = re.search(r"\$(\w+)\s*;", body)
    if parent is not None:
        if parent.group(1) not in entries:
            raise PilotError(f"unknown fvSolution solver parent {parent.group(1)}")
        values.update(_resolve_controls_body(entries, parent.group(1), visited))
    values.update(_parse_control_values(body))
    return values


_SOLVER_RESIDUAL_LINE = re.compile(
    r"Solving for\s+(?P<field>[A-Za-z0-9_.]+),\s*"
    r"Initial residual\s*=\s*(?P<initial>\S+),\s*"
    r"Final residual\s*=\s*(?P<final>\S+),\s*"
    r"No Iterations\s+(?P<iterations>\d+)"
)


def inspect_solver_convergence(log_path: Path, fv_solution: Path) -> dict[str, Any]:
    """Audit every printed linear solve against the active fvSolution criterion."""
    entries, pimple = _solver_dictionary_controls(fv_solution)
    outer_limit = pimple["nOuterCorrectors"]
    p_limit = pimple["nCorrectors"] * (pimple["nNonOrthogonalCorrectors"] + 1)
    outer_iter = 0
    pressure_solves = 0
    records = 0
    failed_records = 0
    failures: list[dict[str, Any]] = []
    by_field: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(
        log_path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        if TIME_LINE.match(line):
            pressure_solves = 0
        outer_match = re.search(r"PIMPLE:\s*iteration\s+(\d+)", line)
        if outer_match is not None:
            outer_iter = int(outer_match.group(1))
            pressure_solves = 0
        if "Solving for" not in line:
            continue
        match = _SOLVER_RESIDUAL_LINE.search(line)
        if match is None:
            failed_records += 1
            if len(failures) < 32:
                failures.append({"line": line_number, "reason": "malformed_solver_residual_line"})
            continue
        field_name = match.group("field")
        pressure_solves += field_name == "p_rgh"
        final = (field_name == "p_rgh" and pressure_solves % p_limit == 0) or (
            field_name != "p_rgh" and outer_iter > 0 and outer_iter >= outer_limit
        )
        try:
            initial = float(match.group("initial"))
            final_residual = float(match.group("final"))
            iterations = int(match.group("iterations"))
            controls = _resolve_solver_controls(entries, field_name, final=final)
        except (ValueError, PilotError) as error:
            failed_records += 1
            if len(failures) < 32:
                failures.append({"line": line_number, "field": field_name, "reason": str(error)})
            continue
        tolerance = float(controls["tolerance"])
        relative_tolerance = float(controls["relTol"])
        max_iterations = int(controls.get("maxIter", 2**31 - 1))
        min_iterations = int(controls.get("minIter", 0))
        finite = all(
            math.isfinite(value)
            for value in (initial, final_residual, tolerance, relative_tolerance)
        )
        met_tolerance = finite and (
            final_residual <= tolerance
            or (relative_tolerance > 0 and final_residual <= initial * relative_tolerance)
        )
        reason = None
        if not finite:
            reason = "nonfinite_residual_or_tolerance"
        elif iterations > max_iterations or iterations < min_iterations:
            reason = "iteration_count_outside_fvSolution_bounds"
        elif not met_tolerance:
            reason = "absolute_or_relative_residual_criterion_not_met"
        records += 1
        summary = by_field.setdefault(
            field_name,
            {"solve_count": 0, "max_iterations": 0, "max_final_residual": 0.0, "failed_count": 0},
        )
        summary["solve_count"] += 1
        summary["max_iterations"] = max(summary["max_iterations"], iterations)
        if finite:
            summary["max_final_residual"] = max(summary["max_final_residual"], final_residual)
        if reason:
            failed_records += 1
            summary["failed_count"] += 1
            if len(failures) < 32:
                base_field = "U" if field_name in {"Ux", "Uy", "Uz"} else field_name
                failures.append(
                    {
                        "line": line_number,
                        "field": field_name,
                        "initial_residual": initial,
                        "final_residual": final_residual,
                        "iterations": iterations,
                        "active_solver_entry": f"{base_field}{'Final' if final else ''}",
                        "tolerance": tolerance,
                        "relTol": relative_tolerance,
                        "maxIter": controls.get("maxIter"),
                        "minIter": min_iterations,
                        "reason": reason,
                    }
                )
    if records == 0:
        failures.append({"reason": "no_linear_solver_records"})
    return {
        "schema_version": 1,
        "fvSolution_sha256": sha256_file(fv_solution),
        "solver_record_count": records,
        "failed_record_count": failed_records,
        "all_converged": records > 0 and not failures,
        "pimple": pimple,
        "by_field": by_field,
        "failure_examples": failures[:32],
        "criteria": "final residual <= tolerance or <= initial residual * relTol; final PIMPLE controls and maxIter/minIter applied",
    }


def _attempt_inventory(attempt: Path) -> list[tuple[Path, str]]:
    inventory: list[tuple[Path, str]] = []
    for path in sorted(attempt.rglob("*")):
        if path.is_symlink():
            raise PilotError(f"refusing to archive symlink from attempt: {path}")
        arcname = PurePosixPath("attempt", path.relative_to(attempt).as_posix()).as_posix()
        _safe_archive_name(arcname)
        inventory.append((path, arcname))
    return inventory


def apply_diagnostic_retention(attempt: Path, *, audit_exit_code: int) -> dict[str, Any]:
    """Omit large 3D state only after a successful compact-ledger audit."""
    if audit_exit_code != 0:
        raise PilotError("diagnostic retention requires a successful compact-ledger audit")
    case = attempt / "case"
    if not case.is_dir() or case.is_symlink():
        raise PilotError("diagnostic retention requires the prepared case directory")
    targets: list[tuple[Path, str]] = []
    for path in case.iterdir():
        if path.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", path.name):
            targets.append((path, "time_fields"))
        elif path.is_dir() and re.fullmatch(r"processors?\d+", path.name):
            targets.append((path, "decomposed_mesh_and_fields"))
        elif path.is_symlink():
            raise PilotError(f"refusing diagnostic retention with case symlink: {path}")
    polymesh = case / "constant/polyMesh"
    if polymesh.exists():
        if polymesh.is_symlink() or not polymesh.is_dir():
            raise PilotError("constant/polyMesh is not a regular directory")
        targets.append((polymesh, "global_mesh"))

    omitted: list[dict[str, Any]] = []
    for path, kind in sorted(targets, key=lambda item: item[0].as_posix()):
        file_count = 0
        byte_count = 0
        for child in path.rglob("*"):
            if child.is_symlink():
                raise PilotError(f"refusing to omit symlink from diagnostic archive: {child}")
            if child.is_file():
                file_count += 1
                byte_count += child.stat().st_size
        omitted.append(
            {
                "path": path.relative_to(attempt).as_posix(),
                "kind": kind,
                "file_count": file_count,
                "bytes": byte_count,
            }
        )
    total_bytes = sum(item["bytes"] for item in omitted)
    result: dict[str, Any] = {
        "schema_version": 1,
        "mode": "diagnostic",
        "status": "complete",
        "compact_ledger_audit_exit_code": audit_exit_code,
        "omitted_paths": omitted,
        "omitted_file_count": sum(item["file_count"] for item in omitted),
        "omitted_bytes": total_bytes,
        "offline_mesh_or_field_reaudit_supported": False,
        "note": "Restore the hash-bound mesh and fields before any offline mesh or field re-audit.",
    }
    for path, _kind in targets:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    write_json(attempt / "retention-manifest.json", result)
    return result


def verify_result_archive(archive: Path, expected_members: list[str]) -> str:
    with gzip.open(archive, "rb") as stream:
        while stream.read(1 << 20):
            pass
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
    actual_names = [member.name.rstrip("/") for member in members]
    if actual_names != expected_members:
        raise PilotError("result archive member list differs from the pre-pack attempt inventory")
    if any(
        member.issym() or member.islnk() or not (member.isfile() or member.isdir())
        for member in members
    ):
        raise PilotError("result archive contains a link or special file")
    for name in actual_names:
        _safe_archive_name(name)
    return sha256_file(archive)


def pack_attempt(attempt: Path, run_dir: Path) -> tuple[Path, str, int, list[dict[str, Any]]]:
    final = run_dir / "result.tar.gz"
    partial = run_dir / "result.tar.gz.partial"
    if final.exists() or partial.exists() or final.is_symlink() or partial.is_symlink():
        raise PilotError("result archive path already exists; refusing to overwrite an attempt")
    inventory = _attempt_inventory(attempt)
    expected = [name for _path, name in inventory]
    member_sizes: list[dict[str, Any]] = []
    if not inventory:
        raise PilotError("attempt has no files to preserve")
    with tarfile.open(partial, "w:gz", compresslevel=1) as tar:
        for path, arcname in inventory:
            info = tar.gettarinfo(str(path), arcname=arcname)
            tar.add(path, arcname=arcname, recursive=False)
            if info.isfile():
                member_sizes.append({"path": info.name, "bytes": info.size})
    digest = verify_result_archive(partial, expected)
    os.replace(partial, final)
    if sha256_file(final) != digest:
        raise PilotError("result archive SHA-256 changed after final rename")
    sidecar = run_dir / "result.tar.gz.sha256"
    sidecar.write_text(f"{digest}  result.tar.gz\n", encoding="ascii")
    members = run_dir / "result-members.txt"
    members.write_text("\n".join(expected) + "\n", encoding="utf-8")
    return final, digest, len(expected), member_sizes


def clean_owned_workspace(workspace: Path, base: Path, job_id: str) -> None:
    resolved = workspace.resolve(strict=True)
    base_resolved = base.resolve(strict=True)
    expected_prefix = f"rouaix-e1hpc-{job_id}."
    if resolved.parent != base_resolved or not resolved.name.startswith(expected_prefix):
        raise PilotError(f"refusing to remove workspace outside the job-owned path: {resolved}")
    shutil.rmtree(resolved)


def _git_record() -> dict[str, Any]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return {
        "revision": revision.stdout.strip() if revision.returncode == 0 else "unknown",
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "status_porcelain": status.stdout.splitlines() if status.returncode == 0 else [],
    }


def effective_stop_deadline(
    monotonic_start: float,
    wall_budget_s: int,
    hard_deadline_utc: str | None,
    *,
    utc_now: datetime | None = None,
) -> float:
    """Return the earlier wall-budget or absolute-UTC checkpoint deadline."""
    deadline = monotonic_start + wall_budget_s - DEADLINE_GRACE_S
    if hard_deadline_utc is None or not hard_deadline_utc.strip():
        return deadline
    raw = hard_deadline_utc.strip()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as error:
        raise PilotError(
            "hard deadline must be ISO-8601 UTC, such as 2026-10-26T05:30:00Z"
        ) from error
    offset = parsed.utcoffset() if parsed.tzinfo is not None else None
    if offset is None or offset.total_seconds() != 0:
        raise PilotError("hard deadline must include a zero-offset UTC timezone")
    now_utc = utc_now or datetime.now(UTC)
    global_deadline = monotonic_start + (parsed.astimezone(UTC) - now_utc).total_seconds()
    global_deadline -= CHECKPOINT_GRACE_S
    return min(deadline, global_deadline)


def run_pilot(
    *,
    run_dir: Path,
    input_archive: Path,
    input_sha256: str,
    shared_pause: Path,
    config: PilotConfig | None = None,
) -> int:
    config = (config or PilotConfig()).validate()
    write_interval = (
        config.write_interval_s if config.write_interval_s is not None else config.horizon_s
    )
    env = dict(os.environ)
    global _EXTERNAL_SIGNAL
    _EXTERNAL_SIGNAL = None
    signal.signal(signal.SIGTERM, _record_external_signal)
    signal.signal(signal.SIGINT, _record_external_signal)
    job_id = env.get("SLURM_JOB_ID", "")
    if not job_id.isdigit():
        raise PilotError("SLURM_JOB_ID must be numeric")
    case_id = env.get("ROUAIX_CASE_ID", "manual")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", case_id):
        raise PilotError("ROUAIX_CASE_ID must be a short safe identifier")
    allocation = _validate_allocation(config, env)
    project_root = Path(os.environ.get("ROUAIX_PROJECT_ROOT", DEFAULT_PROJECT_ROOT)).resolve()
    run_dir = run_dir.resolve(strict=True)
    if run_dir.parent != project_root or not run_dir.name.endswith(job_id):
        raise PilotError("run directory must be a new job-specific directory under project scratch")
    if not SHA256.fullmatch(input_sha256):
        raise PilotError("input archive SHA-256 must be lowercase hex")
    if input_archive.is_symlink() or not input_archive.is_file():
        raise PilotError("input archive must be a regular file")
    input_archive = input_archive.resolve(strict=True)
    if not input_archive.is_relative_to(project_root):
        raise PilotError("input archive must be stored below the approved project scratch root")
    if sha256_file(input_archive) != input_sha256:
        raise PilotError("input archive SHA-256 differs from the submitted value")
    if any(
        (run_dir / name).exists()
        for name in ("run-state.json", "result.tar.gz", "result.tar.gz.partial")
    ):
        raise PilotError("refusing to reuse an existing run directory")

    start = time.monotonic()
    hard_deadline_utc = env.get("ROUAIX_HARD_DEADLINE_UTC")
    stop_deadline = effective_stop_deadline(start, config.wall_budget_s, hard_deadline_utc)
    state: dict[str, Any] = {
        **_git_record(),
        "schema_version": 1,
        "run_id": run_dir.name,
        "job_id": job_id,
        "case_id": case_id,
        "job_name": JOB_NAME,
        "execution_backend": "slurm-native",
        "solver_version": "v2512",
        "input_archive_path": str(input_archive),
        "input_archive_sha256": input_sha256,
        "status": "starting",
        "started_utc": datetime.now(UTC).isoformat(),
        "ranks": config.ranks,
        "nodes": config.nodes,
        "tasks_per_node": allocation["tasks_per_node"],
        "memory_gib_per_node": allocation["memory_gib_per_node"],
        "memory_mb_per_node": allocation["memory_mb_per_node"],
        "memory_gib_total": allocation["memory_gib_total"],
        "allocation": allocation,
        "wall_time_s": config.wall_budget_s,
        "hard_deadline_utc": hard_deadline_utc,
        "horizon_s": config.horizon_s,
        "delta_t_s": config.delta_t_s,
        "numerical_variant": config.numerical_variant,
        "write_interval_s": write_interval,
        "purge_write": 2 if config.horizon_s == 5.0 and write_interval == 1.0 else 0,
        "retention_mode": config.retention_mode,
        "minimum_free_disk_gib": config.minimum_free_disk_gib,
        "minimum_free_disk_bytes": config.minimum_free_disk_gib * 1024**3,
        "stop_signal": 12,
        "pause_paths": [str(run_dir / "PAUSE"), str(shared_pause), str(project_root / "PAUSE")],
    }
    state_path = run_dir / "run-state.json"

    def write_state(value: dict[str, Any]) -> None:
        value["updated_utc"] = datetime.now(UTC).isoformat()
        write_json(state_path, value)

    write_state(state)
    workspace: Path | None = None
    workspace_base: Path | None = None
    attempt: Path | None = None
    try:
        if time.monotonic() >= stop_deadline:
            raise PilotStopped("hard cutoff leaves no time for checkpointing")
        minimum_free_disk_bytes = config.minimum_free_disk_gib * 1024**3
        workspace, storage_record = create_workspace(
            env,
            job_id,
            nodes=config.nodes,
            min_free_bytes=minimum_free_disk_bytes,
        )
        workspace_base = workspace.parent
        attempt = workspace / "attempt"
        attempt.mkdir()
        state["workspace_storage"] = {**storage_record, "workspace": str(workspace.resolve())}
        startup_free = _record_disk_space(state, attempt, run_dir)
        state["free_disk_bytes_at_workspace_start"] = state["free_disk_bytes_last"]
        if startup_free < minimum_free_disk_bytes:
            raise PilotStopped(
                f"free disk fell below {config.minimum_free_disk_gib} GiB at workspace start"
            )
        state["status"] = "input_validation"
        write_state(state)
        extract_root = workspace / "extract"
        archive_members = validate_input_archive(input_archive)
        extract_input_archive(input_archive, extract_root, archive_members)
        mesh_input = extract_root / "mesh-input"
        input_files = validate_extracted_input_inventory(mesh_input, archive_members)
        nozzle_receipt = validate_raw_nozzle_binding(mesh_input)
        member_count = len(archive_members)
        copy_input_evidence(mesh_input, attempt, input_sha256, member_count, input_files)
        (attempt / "experiment.md").write_bytes(
            (ROOT / "experiments/E1_ROUAIX_HPC_PILOT.md").read_bytes()
        )
        progression = ROOT / "experiments/E1_ROUAIX_HPC_PROGRESSION.md"
        progression_copy = attempt / "experiment-progression.md"
        shutil.copy2(progression, progression_copy)
        state["primary_experiment_declaration"] = {
            "path": progression_copy.name,
            "sha256": sha256_file(progression_copy),
        }
        source_copy = attempt / "source"
        source_copy.mkdir()
        for source in (
            Path(__file__),
            Path(__file__).with_name("prepare_case.py"),
            Path(__file__).with_name("collect_native_provenance.py"),
        ):
            shutil.copy2(source, source_copy / source.name)
        state["status"] = "preparing"
        write_state(state)
        if pause_present(run_dir, shared_pause, project_root):
            raise PilotStopped("user PAUSE marker before case preparation", paused=True)
        case_dir = attempt / "case"
        run_setup_command(
            [
                sys.executable,
                str(ROOT / "cases/e1_rouaix_hpc/prepare_case.py"),
                "--mesh-dir",
                str(mesh_input / "constant/polyMesh"),
                "--mesh-manifest",
                str(mesh_input / "mesh-manifest.json"),
                "--nozzle-audit",
                str(mesh_input / "nozzle-audit.json"),
                "--output-dir",
                str(case_dir),
                "--ranks",
                str(config.ranks),
                "--nodes",
                str(config.nodes),
                "--end-time-s",
                str(config.horizon_s),
                "--write-interval-s",
                str(write_interval),
                "--numerical-variant",
                config.numerical_variant,
                "--memory-gib",
                str(allocation["memory_gib_per_node"]),
                "--timeout-s",
                str(config.wall_budget_s),
                "--delta-t-s",
                str(config.delta_t_s),
            ],
            cwd=mesh_input,
            log_path=attempt / "prepare-case.log",
            deadline=stop_deadline,
            run_dir=run_dir,
            shared_pause=shared_pause,
            project_root=project_root,
            state=state,
            write_state=write_state,
            minimum_free_disk_bytes=minimum_free_disk_bytes,
        )
        if pause_present(run_dir, shared_pause, project_root):
            raise PilotStopped("user PAUSE marker after case preparation", paused=True)
        if _EXTERNAL_SIGNAL is not None:
            raise PilotStopped(f"Slurm requested termination with signal {_EXTERNAL_SIGNAL}")
        if time.monotonic() >= stop_deadline:
            raise PilotStopped("allocation deadline checkpoint margin reached during preparation")
        inputs, hashes = validate_prepared_case(case_dir, config)
        manifest = {
            **_git_record(),
            "schema_version": 1,
            "run_id": run_dir.name,
            "job_id": job_id,
            "case_id": case_id,
            "execution_backend": "slurm-native",
            "solver_version": "v2512",
            "reference_image_digest": inputs.get("reference_image_digest"),
            "input_archive_sha256": input_sha256,
            "mesh_manifest_sha256": inputs.get("mesh_manifest_sha256"),
            "mesh_files_sha256": inputs.get("mesh_files_sha256"),
            "nozzle_audit_adapter_sha256": inputs.get("nozzle_audit_sha256"),
            "nozzle_raw_audit_sha256": nozzle_receipt.get("raw_audit_sha256"),
            "prepared_case_sha256": hashes,
            "prepared_case_files_count": len(hashes),
            "rank_count": config.ranks,
            "node_count": config.nodes,
            "tasks_per_node": allocation["tasks_per_node"],
            "memory_mb_per_node": allocation["memory_mb_per_node"],
            "wall_budget_s": config.wall_budget_s,
            "hard_deadline_utc": hard_deadline_utc,
            "horizon_s": config.horizon_s,
            "delta_t_s": config.delta_t_s,
            "numerical_variant": config.numerical_variant,
            "retention_mode": config.retention_mode,
            "minimum_free_disk_gib": config.minimum_free_disk_gib,
            "parent_fvSchemes_sha256": inputs.get("parent_fvSchemes_sha256"),
            "post_override_fvSchemes_sha256": inputs.get("post_override_fvSchemes_sha256"),
            "momentum_convection": inputs.get("actual_momentum_convection"),
            "velocity_gradient_scheme": inputs.get("actual_velocity_gradient_scheme"),
            "fixed_delta_t": True,
            "alpha_subcycles": 1,
            "field_write_times_s": list(inputs["time_controls"]["full_field_write_times_s"]),
            "purge_write": inputs["time_controls"]["purge_write"],
            "checkpoint_policy": inputs["time_controls"]["checkpoint_policy"],
            "formal_validation_decision": None,
        }
        manifest_path = attempt / "manifest.json"
        write_json(manifest_path, manifest)
        module_list = run_dir / "modules.log"
        state["status"] = "native_provenance"
        write_state(state)
        from cases.e1_rouaix_hpc import collect_native_provenance as native_provenance

        native_provenance.collect_native_provenance(
            module_name=MODULE_NAME,
            module_list_path=module_list,
            output_path=attempt / "native-source-evidence.json",
            run_manifest_path=manifest_path,
        )
        verify_stop_signal_source(attempt, manifest_path)
        if pause_present(run_dir, shared_pause, project_root):
            raise PilotStopped("user PAUSE marker before decomposition", paused=True)
        if _EXTERNAL_SIGNAL is not None:
            raise PilotStopped(f"Slurm requested termination with signal {_EXTERNAL_SIGNAL}")
        state["status"] = "decomposing"
        write_state(state)
        run_setup_command(
            ["decomposePar", "-force"],
            cwd=case_dir,
            log_path=attempt / "decompose.log",
            deadline=stop_deadline,
            run_dir=run_dir,
            shared_pause=shared_pause,
            project_root=project_root,
            state=state,
            write_state=write_state,
            minimum_free_disk_bytes=minimum_free_disk_bytes,
        )
        if pause_present(run_dir, shared_pause, project_root):
            raise PilotStopped("user PAUSE marker before solver start", paused=True)
        if time.monotonic() >= stop_deadline:
            raise PilotStopped("allocation deadline checkpoint margin reached before solver")

        state["status"] = "running"
        state["solver_started_utc"] = datetime.now(UTC).isoformat()
        state["solver_started_monotonic"] = time.monotonic()
        write_state(state)
        return_code, tracker, stop_reason, paused_stop = supervise_solver(
            case=case_dir,
            attempt=attempt,
            run_dir=run_dir,
            shared_pause=shared_pause,
            project_root=project_root,
            job_id=job_id,
            config=config,
            deadline=stop_deadline,
            state=state,
            write_state=write_state,
        )
        state["checkpoint_retention"] = verify_checkpoint_retention(
            case_dir, hashes, horizon_s=config.horizon_s
        )
        state["solver_clock_samples_count"] = len(tracker.clock_samples)
        state["solver_clock_windows"] = summarize_solver_clock_windows(
            tracker.clock_samples, config.horizon_s
        )
        convergence_path = attempt / "solver-convergence.json"
        try:
            solver_convergence = inspect_solver_convergence(
                attempt / "solver.log", case_dir / "system/fvSolution"
            )
        except (OSError, PilotError) as convergence_error:
            solver_convergence = {
                "schema_version": 1,
                "all_converged": False,
                "solver_record_count": 0,
                "failed_record_count": 0,
                "error": f"{type(convergence_error).__name__}: {convergence_error}",
            }
        write_json(convergence_path, solver_convergence)
        state["solver_convergence"] = solver_convergence
        _write_step_accounting(attempt, job_id)
        audit_log = attempt / "ledger-audit.log"
        audit_output = attempt / "ledger"
        command = [
            sys.executable,
            str(ROOT / "scripts/audit_iso_vof_ledger.py"),
            "--run-dir",
            str(attempt),
            "--solver-log",
            str(attempt / "solver.log"),
            "--output-dir",
            str(audit_output),
            "--verified-source-evidence",
            str(attempt / "native-source-evidence.json"),
        ]
        with audit_log.open("wb") as log:
            audit_result = subprocess.run(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=120
            )
        state["ledger_audit_exit_code"] = audit_result.returncode
        state["ledger_audit_command"] = command
        if audit_result.returncode != 0:
            state["ledger_audit_status"] = "failed_partial_or_unavailable"
        else:
            state["ledger_audit_status"] = "raw_exploratory_ledger_written"
            if (
                config.retention_mode == "diagnostic"
                and return_code == 0
                and stop_reason is None
                and solver_convergence.get("all_converged") is True
            ):
                state["retention"] = apply_diagnostic_retention(
                    attempt, audit_exit_code=audit_result.returncode
                )
            elif config.retention_mode == "diagnostic":
                state["retention"] = {
                    "mode": "diagnostic",
                    "status": "skipped_full_evidence_retained",
                    "reason": "requires completed solver, passed residual gate, and successful ledger audit",
                }
        if return_code != 0 or stop_reason is not None:
            state["status"] = "paused" if paused_stop else "stopped_with_preserved_evidence"
        elif audit_result.returncode != 0:
            state["status"] = "solver_complete_ledger_failed"
        elif solver_convergence.get("all_converged") is not True:
            state["status"] = "solver_complete_solver_criteria_failed"
        else:
            state["status"] = "solver_complete_exploratory"
    except PilotStopped as error:
        state["status"] = "paused" if error.paused else "stopped_with_preserved_evidence"
        state["stop_reason"] = str(error)
        state["error"] = str(error)
    except Exception as error:  # preserve unexpected failures as first-class attempts
        state["status"] = "failed_preserved"
        state["error"] = f"{type(error).__name__}: {error}"
        state["traceback"] = __import__("traceback").format_exc()
    finally:
        if attempt is not None and attempt.exists():
            try:
                state["attempt_archive_status"] = "packing"
                write_state(state)
                archive, digest, members, member_sizes = pack_attempt(attempt, run_dir)
                state["result_archive"] = str(archive)
                state["result_archive_sha256"] = digest
                state["result_archive_members"] = members
                state["result_archive_member_sizes"] = member_sizes
                state["attempt_archive_status"] = "verified_crc_hash_and_member_list"
                write_state(state)
                if workspace is not None and workspace_base is not None:
                    clean_owned_workspace(workspace, workspace_base, job_id)
                    state["node_local_workspace_removed_after_verified_archive"] = True
            except Exception as archive_error:
                state["attempt_archive_status"] = "verification_or_pack_failed_workspace_retained"
                state["archive_error"] = f"{type(archive_error).__name__}: {archive_error}"
            write_state(state)
        else:
            write_state(state)
    archive_ok = state.get("attempt_archive_status") == "verified_crc_hash_and_member_list"
    return (
        0 if archive_ok and state.get("status") in {"paused", "solver_complete_exploratory"} else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--input-archive", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--shared-pause", type=Path, default=DEFAULT_SHARED_PAUSE)
    parser.add_argument("--ranks", type=int, default=RANKS)
    parser.add_argument("--nodes", type=int, default=1)
    parser.add_argument("--wall-budget-s", type=int, default=WALL_TIME_S)
    parser.add_argument("--end-time-s", type=float, choices=SUPPORTED_HORIZONS_S, default=HORIZON_S)
    parser.add_argument("--delta-t-s", type=float, choices=SUPPORTED_DELTA_T_S, default=DELTA_T_S)
    parser.add_argument("--numerical-variant", choices=NUMERICAL_VARIANTS, default="original")
    parser.add_argument("--write-interval-s", type=float)
    parser.add_argument("--retention-mode", choices=("full", "diagnostic"), default="full")
    parser.add_argument("--minimum-free-disk-gib", type=int, default=12)
    args = parser.parse_args()
    try:
        return run_pilot(
            run_dir=args.run_dir,
            input_archive=args.input_archive,
            input_sha256=args.input_sha256,
            shared_pause=args.shared_pause,
            config=PilotConfig(
                ranks=args.ranks,
                nodes=args.nodes,
                wall_budget_s=args.wall_budget_s,
                horizon_s=args.end_time_s,
                delta_t_s=args.delta_t_s,
                numerical_variant=args.numerical_variant,
                write_interval_s=args.write_interval_s,
                retention_mode=args.retention_mode,
                minimum_free_disk_gib=args.minimum_free_disk_gib,
            ),
        )
    except (
        OSError,
        subprocess.SubprocessError,
        PilotError,
        tarfile.TarError,
        json.JSONDecodeError,
    ) as error:
        print(f"Rouaix native HPC pilot failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
