#!/usr/bin/env python3
"""Run the bounded native .2-to-.201 s Rouaix restart smoke on Komondor."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import sys
import tarfile
import time
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cases.e1_rouaix_hpc import run_pilot as pilot  # noqa: E402

PARENT_ARCHIVE = Path(
    "/project/nk_meshapplied/bene/fire-track2-hpc/"
    "rouaix-healthy-seed-source-v1-20261027/"
    "rouaix-e1-hpc-pilot-14669440/result.tar.gz"
)
PARENT_ARCHIVE_SHA256 = "31010755e705010771de7ed00fb5fb9990e7d2621237c3d881ee22b826cf25c9"
PARENT_LEDGER_SHA256 = "0baa380005d188edf6c94a0c175b790a5a8af5fa79773ff37ace5da5dda2f300"
PARENT_INVENTORY_M3 = 0.2508975771509
PARENT_LEDGER_M3_PATH = "attempt/ledger/summary.json"
PARENT_CASE_ROOT = "attempt/case"
PARENT_TIME_DIR = "processors120/0.200000000000"
PARENT_TIME_S = 0.2
DT_S = 0.0001
END_TIME_S = 0.201
WRITE_INTERVAL_S = 0.001
VARIANT_SETTINGS = {
    "original-smoke": {"end_time_s": 0.201, "write_interval_s": 0.001, "wall_budget_s": 1200},
    "original-control": {"end_time_s": 0.3, "write_interval_s": 0.1, "wall_budget_s": 5400},
}
CASE_IDS = {
    "original-smoke": "rouaix-restart-original-smoke-0201",
    "original-control": "rouaix-restart-original-control-0300",
}
EXPECTED_ARCHIVE_MEMBERS = 131
EXPECTED_RANKS = 120
EXPECTED_NODES = 3
TASKS_PER_NODE = 40
MEMORY_GIB_PER_NODE = 22
MIN_FREE_DISK_BYTES = 12 * 1024**3
PAUSE_FILE = Path("/project/nk_meshapplied/bene/fire-track2-hpc/PAUSE")
REQUIRED_CHECKPOINT_FIELDS = (
    "U",
    "alpha.water",
    "epsilon",
    "k",
    "nut",
    "p",
    "p_rgh",
    "phi",
    "uniform/cumulativeContErr",
    "uniform/functionObjects/functionObjectProperties",
    "uniform/time",
)
REQUIRED_ENDPOINT_FIELDS = ("U", "alpha.water", "p_rgh", "k", "epsilon", "nut", "p", "phi")
MESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
TIME_FIELD_LINE = re.compile(r"^\s*(value|name|index|deltaT|deltaT0)\s+([^;]+);\s*$", re.MULTILINE)


class RestartError(RuntimeError):
    """The immutable checkpoint or bounded restart contract did not verify."""


def validate_checkpoint_time(time_text: str) -> None:
    fields: dict[str, str] = {}
    for match in TIME_FIELD_LINE.finditer(time_text):
        key, value = match.groups()
        if key in fields:
            raise RestartError(f"checkpoint uniform/time contains duplicate {key}")
        fields[key] = value.strip()
    for key in ("value", "name", "index", "deltaT", "deltaT0"):
        if key not in fields:
            raise RestartError(f"checkpoint uniform/time lacks {key}")

    try:
        value_s = float(fields["value"])
        delta_t_s = float(fields["deltaT"])
        delta_t0_s = float(fields["deltaT0"])
        index = int(fields["index"])
    except ValueError as error:
        raise RestartError("checkpoint uniform/time has a nonnumeric scalar") from error
    if not all(math.isfinite(number) for number in (value_s, delta_t_s, delta_t0_s)):
        raise RestartError("checkpoint uniform/time has a nonfinite scalar")
    if fields["name"] != f'"{PARENT_TIME_DIR.rsplit("/", 1)[-1]}"':
        raise RestartError("checkpoint uniform/time name differs from the checkpoint directory")
    if index != round(PARENT_TIME_S / DT_S):
        raise RestartError("checkpoint uniform/time index does not match 0.2 s")
    if delta_t_s != DT_S or delta_t0_s != DT_S:
        raise RestartError("checkpoint uniform/time timestep does not equal 0.0001 s")
    if not math.isclose(value_s, PARENT_TIME_S, rel_tol=0.0, abs_tol=1e-12):
        raise RestartError("checkpoint uniform/time does not record exactly 0.2 s")


@dataclass(frozen=True)
class RestartConfig:
    variant: str = "original-smoke"
    start_time_s: float = PARENT_TIME_S
    end_time_s: float = END_TIME_S
    delta_t_s: float = DT_S
    write_interval_s: float = WRITE_INTERVAL_S
    ranks: int = EXPECTED_RANKS
    nodes: int = EXPECTED_NODES
    wall_budget_s: int = 1200
    memory_gib_per_node: int = MEMORY_GIB_PER_NODE

    def validate(self) -> RestartConfig:
        declared = VARIANT_SETTINGS.get(self.variant)
        if declared is None:
            raise RestartError(f"unsupported restart variant: {self.variant}")
        if self.start_time_s != 0.2 or self.delta_t_s != 0.0001:
            raise RestartError("restart must begin at 0.2 s with fixed deltaT 0.0001 s")
        if self.end_time_s != declared["end_time_s"]:
            raise RestartError("restart end time differs from the selected frozen variant")
        if self.write_interval_s != declared["write_interval_s"]:
            raise RestartError("field write interval differs from the selected frozen variant")
        if self.wall_budget_s != declared["wall_budget_s"]:
            raise RestartError("wall budget differs from the selected frozen variant")
        steps = (self.end_time_s - self.start_time_s) / self.delta_t_s
        expected_steps = round(steps)
        if not math.isclose(steps, expected_steps, rel_tol=0.0, abs_tol=1e-12):
            raise RestartError("restart target must contain an integer number of fixed steps")
        if self.variant == "original-smoke" and expected_steps != 10:
            raise RestartError("smoke must contain exactly ten continuation steps")
        if self.variant == "original-control" and expected_steps != 1000:
            raise RestartError("original control must contain exactly 1000 continuation steps")
        if (self.ranks, self.nodes, self.memory_gib_per_node) != (120, 3, 22):
            raise RestartError(
                "restart allocation must be three nodes, 40 ranks per node, 22 GiB/node"
            )
        return self


def config_for_variant(variant: str) -> RestartConfig:
    settings = VARIANT_SETTINGS.get(variant)
    if settings is None:
        raise RestartError(f"unsupported restart variant: {variant}")
    return RestartConfig(variant=variant, **settings).validate()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, path)


def safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RestartError(f"unsafe seed archive member {name!r}")
    return path


def select_seed_members(members: list[tarfile.TarInfo]) -> list[tarfile.TarInfo]:
    selected: list[tarfile.TarInfo] = []
    names: set[str] = set()
    for member in members:
        relative = safe_member_path(member.name)
        name = relative.as_posix()
        if name in names:
            raise RestartError(f"duplicate seed archive member {name}")
        names.add(name)
        if member.isdir():
            continue
        if not member.isfile():
            raise RestartError(f"seed archive contains a link or special file: {name}")
        if not name.startswith("attempt/"):
            continue
        case_member = name.removeprefix("attempt/")
        wanted = (
            name in {"attempt/manifest.json", PARENT_LEDGER_M3_PATH}
            or case_member == "case/case-inputs.json"
            or case_member.startswith("case/system/")
            or case_member.startswith("case/constant/")
            or case_member.startswith("case/processors120/constant/polyMesh/")
            or case_member.startswith(f"case/{PARENT_TIME_DIR}/")
        )
        if wanted:
            selected.append(member)
    selected_names = {safe_member_path(item.name).as_posix() for item in selected}
    required = {
        "attempt/manifest.json",
        PARENT_LEDGER_M3_PATH,
        f"{PARENT_CASE_ROOT}/case-inputs.json",
        *(
            f"{PARENT_CASE_ROOT}/system/{name}"
            for name in ("controlDict", "decomposeParDict", "fvSchemes", "fvSolution")
        ),
        *(f"{PARENT_CASE_ROOT}/constant/polyMesh/{name}" for name in MESH_FILES),
        *(f"{PARENT_CASE_ROOT}/processors120/constant/polyMesh/{name}" for name in MESH_FILES),
        *(f"{PARENT_CASE_ROOT}/{PARENT_TIME_DIR}/{name}" for name in REQUIRED_CHECKPOINT_FIELDS),
    }
    missing = sorted(required - selected_names)
    if missing:
        raise RestartError(f"seed archive lacks required restart members: {missing}")
    return selected


def extract_seed_archive(archive: Path, attempt: Path) -> dict[str, Any]:
    if archive.is_symlink() or not archive.is_file():
        raise RestartError("parent seed archive must be a regular file")
    actual_sha = sha256_file(archive)
    if actual_sha != PARENT_ARCHIVE_SHA256:
        raise RestartError(f"parent seed archive SHA-256 mismatch: {actual_sha}")
    with tarfile.open(archive, mode="r:gz") as tar:
        members = tar.getmembers()
        if len(members) != EXPECTED_ARCHIVE_MEMBERS:
            raise RestartError(f"parent archive has {len(members)} members, expected 131")
        selected = select_seed_members(members)
        selected_manifest: list[dict[str, Any]] = []
        for member in selected:
            relative = safe_member_path(member.name)
            target = attempt.joinpath(*relative.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise RestartError(f"could not read required parent member {member.name}")
            digest = hashlib.sha256()
            byte_count = 0
            with source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    byte_count += len(chunk)
            selected_manifest.append(
                {"path": member.name, "bytes": byte_count, "sha256": digest.hexdigest()}
            )
    parent_ledger = attempt / "ledger/summary.json"
    if sha256_file(parent_ledger) != PARENT_LEDGER_SHA256:
        raise RestartError("parent ledger summary hash differs from the independently audited seed")
    parent_manifest_path = attempt / "manifest.json"
    parent_manifest = json.loads(parent_manifest_path.read_text(encoding="utf-8"))
    if (
        parent_manifest.get("rank_count") != EXPECTED_RANKS
        or parent_manifest.get("horizon_s") != 0.2
    ):
        raise RestartError("parent run manifest does not prove the 120-rank .2 s checkpoint")
    case = attempt / "case"
    actual_original_hashes: dict[str, str] = {}
    declared_hashes = parent_manifest.get("prepared_case_sha256", {})
    for relative in (
        "case-inputs.json",
        "system/controlDict",
        "system/decomposeParDict",
        "system/fvSchemes",
        "system/fvSolution",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        *(f"constant/polyMesh/{name}" for name in MESH_FILES),
    ):
        path = case / relative
        declared = declared_hashes.get(relative)
        if not declared or sha256_file(path) != declared:
            raise RestartError(f"seed case input does not match parent manifest: {relative}")
        actual_original_hashes[relative] = declared
    decomposition = (case / "system/decomposeParDict").read_text(encoding="utf-8")
    if not re.search(r"\bnumberOfSubdomains\s+120\s*;", decomposition):
        raise RestartError("parent decomposition dictionary does not declare 120 subdomains")
    endpoint = case / PARENT_TIME_DIR
    checkpoint_hashes: dict[str, dict[str, Any]] = {}
    for relative in REQUIRED_CHECKPOINT_FIELDS:
        path = endpoint / relative
        if not path.is_file() or path.is_symlink():
            raise RestartError(f"missing regular checkpoint file: {relative}")
        checkpoint_hashes[relative] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    mesh_path = case / "processors120/constant/polyMesh"
    decomposed_mesh = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(mesh_path.iterdir())
        if path.is_file()
    }
    if not set(MESH_FILES).issubset(decomposed_mesh):
        raise RestartError("collated 120-rank decomposition mesh is incomplete")
    time_text = (endpoint / "uniform/time").read_text(encoding="ascii", errors="strict")
    validate_checkpoint_time(time_text)
    ledger = json.loads(parent_ledger.read_text(encoding="utf-8"))
    inventory = float(ledger["integration"]["final_inventory_m3"])
    if not math.isclose(inventory, PARENT_INVENTORY_M3, rel_tol=0.0, abs_tol=1e-13):
        raise RestartError("measured parent checkpoint inventory differs from audited value")
    receipt = {
        "archive_sha256": actual_sha,
        "checkpoint_time_s": PARENT_TIME_S,
        "inventory_m3": inventory,
        "archive_status": "verified_crc_hash_and_member_list",
        "selected_endpoint_member": f"{PARENT_CASE_ROOT}/{PARENT_TIME_DIR}/alpha.water",
    }
    write_json(case / "parent-checkpoint-receipt.json", receipt)
    verification = {
        "schema_version": 1,
        "source_archive_sha256": actual_sha,
        "archive_member_count": len(members),
        "archive_members_sha256": hashlib.sha256(
            (
                "\n".join(sorted(safe_member_path(item.name).as_posix() for item in members)) + "\n"
            ).encode()
        ).hexdigest(),
        "archive_status": "verified_crc_hash_and_member_list",
        "selected_files": selected_manifest,
        "parent_manifest_sha256": sha256_file(parent_manifest_path),
        "parent_ledger_sha256": PARENT_LEDGER_SHA256,
        "parent_inventory_m3": inventory,
        "parent_case_input_sha256": actual_original_hashes,
        "checkpoint_fields": checkpoint_hashes,
        "collated_decomposition_mesh": decomposed_mesh,
        "checkpoint_receipt_sha256": sha256_file(case / "parent-checkpoint-receipt.json"),
    }
    write_json(attempt / "seed-verification.json", verification)
    shutil.copy2(parent_ledger, attempt / "parent-ledger-summary.json")
    parent_ledger.unlink()
    shutil.copy2(parent_manifest_path, attempt / "parent-seed-manifest.json")
    parent_manifest_path.unlink()
    return verification


def rewrite_control_dict(path: Path, config: RestartConfig) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    end_token = f"{config.end_time_s:.12g}"
    write_token = f"{config.write_interval_s:.12g}"
    replacements = (
        (r"(?m)^startFrom\s+startTime\s*;", "startFrom latestTime;"),
        (r"(?m)^startTime\s+0\s*;", "startTime 0.2;"),
        (r"(?m)^endTime\s+0\.2\s*;", f"endTime {end_token};"),
        (r"(?m)^writeInterval\s+0\.2\s*;", f"writeInterval {write_token};"),
    )
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text)
        if count != 1:
            raise RestartError(
                f"expected one controlDict setting for {replacement!r}, found {count}"
            )
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_text(text, encoding="utf-8")
    if "deltaT 0.0001;" not in text or "adjustTimeStep no;" not in text:
        raise RestartError("restart changed the fixed time-step controls")
    return {"before_sha256": before, "after_sha256": sha256_file(path)}


class RestartOutputMonitor(pilot.OutputMonitor):
    """Reuse the frozen log parser but require continuation times after .2 s."""

    start_time_s = PARENT_TIME_S

    def _finish_current(self) -> None:
        if self.current_time_s is not None and self.current_time_s <= self.start_time_s + 1e-12:
            return
        super()._finish_current()

    def completion_fault(self) -> str | None:
        step_count = round((self.horizon_s - self.start_time_s) / self.delta_t_s)
        rows = [(t, u) for t, u in self.rows if t > self.start_time_s + 1e-12]
        expected = [self.start_time_s + i * self.delta_t_s for i in range(1, step_count + 1)]
        if len(rows) != step_count or any(
            abs(actual - target) > 1e-9
            for (actual, _speed), target in zip(rows, expected, strict=True)
        ):
            return (
                f"solver log does not prove all {step_count} fixed continuation steps after 0.2 s"
            )
        if not self.saw_end_marker:
            return "solver log lacks the native End completion marker"
        return None


def validate_allocation(config: RestartConfig, env: dict[str, str]) -> dict[str, Any]:
    config.validate()
    expected = {
        "SLURM_JOB_NAME": "ml-vof",
        "SLURM_JOB_ACCOUNT": "nk_meshapplied",
        "SLURM_JOB_PARTITION": "cpu-short",
        "SLURM_JOB_NUM_NODES": "3",
        "SLURM_NTASKS": "120",
        "SLURM_CPUS_PER_TASK": "1",
    }
    bad = {key: env.get(key) for key, value in expected.items() if env.get(key) != value}
    if bad:
        raise RestartError(f"Slurm allocation differs from the declared restart smoke: {bad}")
    tasks = pilot._tasks_per_node(env.get("SLURM_TASKS_PER_NODE", ""))
    if tasks != (40, 40, 40):
        raise RestartError(f"expected tasks_per_node=(40,40,40), got {tasks}")
    if int(env.get("SLURM_MEM_PER_NODE", "0")) < MEMORY_GIB_PER_NODE * 1024:
        raise RestartError(
            f"Slurm did not allocate at least {MEMORY_GIB_PER_NODE} GiB on each node"
        )
    if int(env.get("SLURM_CPUS_ON_NODE", "0")) < TASKS_PER_NODE:
        raise RestartError(f"Slurm allocated fewer than {TASKS_PER_NODE} CPUs on a node")
    return {
        "partition": env["SLURM_JOB_PARTITION"],
        "nodes": 3,
        "tasks_per_node": list(tasks),
        "ranks": 120,
        "cpus_per_task": 1,
        "memory_mb_per_node": int(env["SLURM_MEM_PER_NODE"]),
        "nodelist": env.get("SLURM_JOB_NODELIST", "unknown"),
        "gpu_request": None,
    }


def prepare_case(attempt: Path, config: RestartConfig) -> tuple[Path, dict[str, Any]]:
    case = attempt / "case"
    seed_receipt = extract_seed_archive(PARENT_ARCHIVE, attempt)
    case_inputs_path = case / "case-inputs.json"
    case_inputs = json.loads(case_inputs_path.read_text(encoding="utf-8"))
    case_inputs["restart"] = {
        "start_time_s": config.start_time_s,
        "end_time_s": config.end_time_s,
        "delta_t_s": config.delta_t_s,
        "parent_archive_sha256": PARENT_ARCHIVE_SHA256,
        "parent_checkpoint_time_s": PARENT_TIME_S,
        "parent_checkpoint_inventory_m3": PARENT_INVENTORY_M3,
        "variant": config.variant,
        "parent_smoke_job_id": os.environ.get("ROUAIX_PARENT_SMOKE_JOB_ID"),
        "fields_mapped_from_prior_run": True,
    }
    case_inputs["field_write_times_s"] = [config.end_time_s]
    case_inputs["file_handler"] = "collated"
    case_inputs["rank_count"] = EXPECTED_RANKS
    case_inputs["node_count"] = EXPECTED_NODES
    case_inputs["tasks_per_node"] = [TASKS_PER_NODE] * EXPECTED_NODES
    write_json(case_inputs_path, case_inputs)
    control_hashes = rewrite_control_dict(case / "system/controlDict", config)
    (case / "system/controlDict").chmod(0o444)
    manifest = {
        "schema_version": 1,
        "case_id": CASE_IDS[config.variant],
        "job_id": os.environ["SLURM_JOB_ID"],
        "rank_count": EXPECTED_RANKS,
        "node_count": EXPECTED_NODES,
        "tasks_per_node": [TASKS_PER_NODE] * EXPECTED_NODES,
        "memory_gib_per_node": MEMORY_GIB_PER_NODE,
        "wall_budget_s": config.wall_budget_s,
        "horizon_s": config.end_time_s,
        "start_time_s": config.start_time_s,
        "delta_t_s": config.delta_t_s,
        "requested_incremental_duration_s": config.end_time_s - config.start_time_s,
        "numerical_variant": "original",
        "momentum_convection": "limitedLinearV 1",
        "parent_archive_sha256": PARENT_ARCHIVE_SHA256,
        "parent_ledger_sha256": PARENT_LEDGER_SHA256,
        "parent_checkpoint_time_s": PARENT_TIME_S,
        "parent_checkpoint_inventory_m3": PARENT_INVENTORY_M3,
        "parent_smoke_job_id": os.environ.get("ROUAIX_PARENT_SMOKE_JOB_ID"),
        "parent_checkpoint_receipt_sha256": seed_receipt["checkpoint_receipt_sha256"],
        "controlDict_hashes": control_hashes,
        "file_handler": "collated",
        "formal_validation_decision": None,
    }
    write_json(attempt / "manifest.json", manifest)
    source_dir = attempt / "source"
    source_dir.mkdir()
    for source in (
        Path(__file__),
        Path(__file__).with_name(
            "restart_control.sbatch"
            if config.variant == "original-control"
            else "restart_smoke_v2.sbatch"
        ),
        ROOT / "cases/e1_rouaix_hpc/run_pilot.py",
        ROOT / "cases/e1_rouaix_hpc/collect_native_provenance.py",
        ROOT / "cases/e1_rouaix_hpc/prepare_case.py",
        ROOT / "cases/e1_rouaix_hpc/source-provenance.json",
        ROOT / "scripts/hpc_metrics.py",
        ROOT / "scripts/audit_iso_vof_ledger.py",
        ROOT / "scripts/continue_rouaix_case.py",
        ROOT / "scripts/audit_interface_wave_flux.py",
        ROOT / "cases/e1_rouaix_hpc_restart/audit_restart.py",
    ):
        if source.is_file():
            target = source_dir / source.name
            shutil.copy2(source, target)
    source_hashes = {path.name: sha256_file(path) for path in sorted(source_dir.iterdir())}
    write_json(attempt / "source-capsule-index.json", {"sha256": source_hashes})
    write_json(attempt / "seed-verification-copy.json", seed_receipt)
    return case, manifest


def verify_endpoint(case: Path, time_s: float) -> dict[str, Any]:
    time_name = f"{time_s:.12f}"
    endpoint = case / "processors120" / time_name
    missing = [name for name in REQUIRED_ENDPOINT_FIELDS if not (endpoint / name).is_file()]
    if missing:
        raise RestartError(f"collated endpoint {time_name} lacks required fields: {missing}")
    fields = {
        name: {"bytes": (endpoint / name).stat().st_size, "sha256": sha256_file(endpoint / name)}
        for name in REQUIRED_ENDPOINT_FIELDS
    }
    if not (endpoint / "uniform/time").is_file():
        raise RestartError(f"collated endpoint {time_name} lacks uniform/time")
    return {"time_s": time_s, "directory": str(endpoint), "fields": fields}


def build_terminal_status(
    *,
    return_code: int,
    end_marker: bool,
    actual_time_s: float | None,
    step_count: int,
    stop_detail: str | None,
    pause_observed: bool,
    stop_signals: list[str],
    endpoint_verified: bool,
    variant: str = "original-smoke",
    target_time_s: float = END_TIME_S,
    solver_log_sha256: str | None = None,
    max_speed_csv_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the exact receipt consumed by the restart-ledger audit."""
    reached = actual_time_s is not None and math.isclose(
        actual_time_s, target_time_s, rel_tol=0.0, abs_tol=1e-10
    )
    u_guard = bool(stop_detail and stop_detail.startswith("operational stop: max|U|="))
    requested = u_guard and "12" in stop_signals
    acknowledged = bool(requested and return_code == 0 and end_marker and endpoint_verified)
    if reached and return_code == 0 and end_marker and stop_detail is None and not pause_observed:
        state, stop_reason = "terminal", None
    elif (
        u_guard
        and not reached
        and return_code == 0
        and end_marker
        and not pause_observed
        and acknowledged
    ):
        state, stop_reason = "guarded_partial", "max_abs_U_exceeded_1000.0_m_s"
    else:
        state, stop_reason = "incomplete", stop_detail
    return {
        "schema_version": 1,
        "state": state,
        "solver_exit_code": return_code,
        "solver_end_marker": end_marker,
        "solver_time_s": actual_time_s,
        "target_time_s": target_time_s,
        "requested_start_time_s": PARENT_TIME_S,
        "solver_time_steps_recorded": step_count,
        "stop_reason": stop_reason,
        "stop_detail": stop_detail,
        "pause_observed": pause_observed,
        "write_and_stop_requested": requested,
        "write_and_stop_acknowledged": acknowledged,
        "variant": variant,
        "solver_log_sha256": solver_log_sha256,
        "max_speed_csv_sha256": max_speed_csv_sha256,
    }


def _run_audit(case: Path, attempt: Path, config: RestartConfig) -> dict[str, Any]:
    helper_path = ROOT / "cases/e1_rouaix_hpc_restart/audit_restart.py"
    if not helper_path.is_file():
        raise RestartError("restart ledger helper is missing from the frozen source capsule")
    from cases.e1_rouaix_hpc_restart.audit_restart import audit_restart

    audit = audit_restart(
        run_dir=case,
        parent_ledger=attempt / "parent-ledger-summary.json",
        start_time_s=config.start_time_s,
        end_time_s=config.end_time_s,
        delta_t_s=config.delta_t_s,
    )
    ledger_dir = attempt / "ledger"
    ledger_dir.mkdir(exist_ok=True)
    shutil.copy2(case / "restart-audit.json", ledger_dir / "summary.json")
    shutil.copy2(case / "restart-ledger.csv", ledger_dir / "ledger.csv")
    return audit


def verify_stop_contract(attempt: Path, case: Path) -> dict[str, Any]:
    evidence = json.loads((attempt / "native-source-evidence.json").read_text())
    native = evidence["native_solver"]
    if (
        native["executable_sha256"]
        != "1907a33483b27dcca0bf17b36e8b8165983a2bbf39f7bde660860b7fe27e3549"
    ):
        raise RestartError("native solver executable differs from the verified donor")
    source = Path(native["wm_project_dir"]) / pilot.STOP_SIGNAL_SOURCE_RELATIVE
    if sha256_file(source.resolve(strict=True)) != pilot.STOP_SIGNAL_SOURCE_SHA256:
        raise RestartError("installed write-and-stop source differs from the pinned donor")
    if not re.search(r"\bstopAtWriteNowSignal\s+12\s*;", (case / "system/controlDict").read_text()):
        raise RestartError("restart does not configure native write-and-stop signal 12")
    return {
        "signal": 12,
        "source_sha256": pilot.STOP_SIGNAL_SOURCE_SHA256,
        "executable_sha256": native["executable_sha256"],
        "scope": "Installed source and case configuration; current runtime banner checked after solve.",
    }


def validate_smoke_preflight(run_root: Path, smoke_id: str) -> dict[str, Any]:
    """Require the exact smoke success/archive before allowing a .3 continuation."""
    if not smoke_id.isdigit():
        raise RestartError("original control requires the explicit v2 smoke Slurm job ID")
    smoke_dir = run_root / f"rouaix-restart-original-smoke-{smoke_id}"
    state_path = smoke_dir / "run-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    exact = {
        "status": "solver_complete_exploratory",
        "job_id": smoke_id,
        "case_id": CASE_IDS["original-smoke"],
        "variant": "original-smoke",
        "solver_exit_code": 0,
        "solver_end_marker": True,
        "solver_time_steps_recorded": 10,
        "start_time_s": 0.2,
        "target_time_s": 0.201,
        "delta_t_s": 0.0001,
        "attempt_archive_status": "verified_crc_hash_and_member_list",
        "ledger_status": "written_from_hash_bound_parent_checkpoint",
    }
    for key, expected in exact.items():
        if state.get(key) != expected:
            raise RestartError(
                f"original smoke preflight {key}={state.get(key)!r}, expected {expected!r}"
            )
    allocation = state.get("allocation", {})
    if (
        allocation.get("nodes") != 3
        or allocation.get("ranks") != 120
        or allocation.get("tasks_per_node") != [40, 40, 40]
        or allocation.get("memory_mb_per_node", 0) < MEMORY_GIB_PER_NODE * 1024
    ):
        raise RestartError(
            "original smoke allocation receipt differs from 3 nodes × 40 ranks × 22 GiB"
        )
    if not math.isclose(
        float(state.get("solver_time_s", math.nan)), 0.201, rel_tol=0.0, abs_tol=1e-10
    ):
        raise RestartError("original smoke did not reach its requested .201 s endpoint")
    convergence = state.get("solver_convergence", {})
    if convergence.get("all_converged") is not True or convergence.get("failed_record_count") != 0:
        raise RestartError("original smoke solver residual/convergence receipt did not pass")
    attempt = smoke_dir / "attempt"
    ledger_path = attempt / "ledger/summary.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("coverage", {}).get("status") != "requested_horizon_reached_exploratory_only":
        raise RestartError("original smoke incremental ledger did not reach the requested target")
    if ledger.get("coverage", {}).get("requested_target_reached") is not True:
        raise RestartError("original smoke ledger does not record requested-target completion")
    integration = ledger.get("integration", {})
    residual_names = (
        "closure_residual_kg",
        "max_abs_per_step_closure_residual_kg",
        "max_abs_cumulative_closure_residual_kg",
    )
    residuals = {name: float(integration.get(name, math.nan)) for name in residual_names}
    if not all(math.isfinite(value) for value in residuals.values()):
        raise RestartError("original smoke ledger lacks finite interval residual diagnostics")
    archive = Path(state.get("result_archive", ""))
    if archive != smoke_dir / "result.tar.gz" or archive.is_symlink() or not archive.is_file():
        raise RestartError("original smoke result archive path is missing or outside its run")
    actual_archive_sha = sha256_file(archive)
    if actual_archive_sha != state.get("result_archive_sha256"):
        raise RestartError("original smoke result archive SHA-256 changed after capture")
    expected_members = [name for _path, name in pilot._attempt_inventory(attempt)]
    if len(expected_members) != state.get("result_archive_members"):
        raise RestartError(
            "original smoke archive member count differs from current attempt inventory"
        )
    if pilot.verify_result_archive(archive, expected_members) != actual_archive_sha:
        raise RestartError("original smoke archive CRC/member-list verification failed")
    terminal_path = attempt / "case/terminal-status.json"
    if not terminal_path.is_file():
        raise RestartError("original smoke archive lacks its terminal-status receipt")
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    if (
        terminal.get("state") != "terminal"
        or terminal.get("solver_end_marker") is not True
        or terminal.get("solver_exit_code") != 0
        or terminal.get("pause_observed") is not False
        or terminal.get("solver_time_steps_recorded") != 10
    ):
        raise RestartError(
            "original smoke terminal receipt does not prove a clean ten-step endpoint"
        )
    return {
        "job_id": smoke_id,
        "run_state_sha256": sha256_file(state_path),
        "result_archive_sha256": actual_archive_sha,
        "result_archive_member_count": len(expected_members),
        "terminal_status_sha256": sha256_file(terminal_path),
        "ledger_sha256": sha256_file(ledger_path),
        "ledger_residuals_kg": residuals,
        "solver_convergence": convergence,
        "status": "verified_clean_smoke_archive_ledger_and_convergence",
        "conservation_tolerance_decision": "raw residuals retained; no acceptance threshold inferred",
    }


def run(run_root: Path, config: RestartConfig) -> int:
    config.validate()
    env = dict(os.environ)
    allocation = validate_allocation(config, env)
    job_id = env.get("SLURM_JOB_ID", "")
    if not job_id.isdigit():
        raise RestartError("SLURM_JOB_ID must be numeric")
    run_root.mkdir(parents=True, exist_ok=True)
    run_dir = run_root / f"rouaix-restart-{config.variant}-{job_id}"
    run_dir.mkdir(mode=0o750)
    attempt = run_dir / "attempt"
    attempt.mkdir()
    started = time.monotonic()
    solver_deadline = started + config.wall_budget_s - (180 + 120 + 20 + 30 + 30)
    if env.get("SLURM_JOB_END_TIME", "").isdigit():
        solver_deadline = min(
            solver_deadline, started + int(env["SLURM_JOB_END_TIME"]) - time.time() - 380
        )
    pilot._EXTERNAL_SIGNAL = None
    signal.signal(signal.SIGTERM, pilot._record_external_signal)
    signal.signal(signal.SIGINT, pilot._record_external_signal)
    state: dict[str, Any] = {
        "schema_version": 1,
        "job_id": job_id,
        "job_name": "ml-vof",
        "case_id": CASE_IDS[config.variant],
        "status": "starting",
        "started_utc": datetime.now(UTC).isoformat(),
        "execution_backend": "native-slurm-openfoam",
        "solver_version": "v2512",
        "variant": config.variant,
        "allocation": allocation,
        "wall_budget_s": config.wall_budget_s,
        "start_time_s": config.start_time_s,
        "target_time_s": config.end_time_s,
        "delta_t_s": config.delta_t_s,
        "parent_archive_sha256": PARENT_ARCHIVE_SHA256,
        "parent_checkpoint_time_s": PARENT_TIME_S,
        "parent_smoke_job_id": env.get("ROUAIX_PARENT_SMOKE_JOB_ID"),
        "pause_paths": [str(PAUSE_FILE), str(run_dir / "PAUSE"), str(run_root / "PAUSE")],
    }

    def write_state(_state: dict[str, Any] | None = None) -> None:
        state["updated_utc"] = datetime.now(UTC).isoformat()
        write_json(run_dir / "run-state.json", state)

    try:
        if PAUSE_FILE.exists() or (run_root / "PAUSE").exists():
            raise RestartError("user PAUSE marker is present before restart preparation")
        if config.variant == "original-control":
            state["smoke_preflight"] = validate_smoke_preflight(
                run_root, env.get("ROUAIX_PARENT_SMOKE_JOB_ID", "")
            )
            write_state()
        if shutil.disk_usage(run_root).free < MIN_FREE_DISK_BYTES:
            raise RestartError("available project disk is below the 12 GiB restart floor")
        state["status"] = "seed_validation_and_extraction"
        write_state()
        case, manifest = prepare_case(attempt, config)
        state["seed_verification"] = json.loads((attempt / "seed-verification.json").read_text())
        state["manifest_sha256"] = sha256_file(attempt / "manifest.json")
        write_state()
        from cases.e1_rouaix_hpc import collect_native_provenance

        collect_native_provenance.collect_native_provenance(
            module_name="OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH",
            module_list_path=run_root / f"module-list-{job_id}.log",
            output_path=attempt / "native-source-evidence.json",
            run_manifest_path=attempt / "manifest.json",
        )
        state["write_and_stop_contract"] = verify_stop_contract(attempt, case)
        state["status"] = "preflight_verified"
        write_state()
        if PAUSE_FILE.exists() or (run_dir / "PAUSE").exists() or (run_root / "PAUSE").exists():
            raise RestartError("user PAUSE marker appeared before solver launch")
        if time.monotonic() >= solver_deadline:
            raise RestartError("preparation consumed the declared checkpoint and cleanup margin")
        if pilot._EXTERNAL_SIGNAL is not None:
            raise RestartError("Slurm requested termination during restart preparation")
        tracker_class = pilot.OutputMonitor
        pilot.OutputMonitor = RestartOutputMonitor
        try:
            state["status"] = "running"
            state["solver_started_utc"] = datetime.now(UTC).isoformat()
            state["solver_started_monotonic"] = time.monotonic()
            write_state()
            config_for_pilot = SimpleNamespace(
                ranks=config.ranks,
                nodes=config.nodes,
                horizon_s=config.end_time_s,
                delta_t_s=config.delta_t_s,
                minimum_free_disk_gib=12,
            )
            return_code, tracker, stop_reason, paused = pilot.supervise_solver(
                case=case,
                attempt=attempt,
                run_dir=run_dir,
                shared_pause=PAUSE_FILE,
                project_root=run_root,
                job_id=job_id,
                config=config_for_pilot,
                deadline=solver_deadline,
                state=state,
                write_state=write_state,
            )
        finally:
            pilot.OutputMonitor = tracker_class
        if not re.search(
            r"sigStopAtWriteNow\s*:\s*Enabling writing and stopping upon signal 12\b",
            (attempt / "solver.log").read_text(errors="replace"),
        ):
            raise RestartError("current solver banner does not confirm write-and-stop signal 12")
        state["current_solver_stop_signal_banner_confirmed"] = True
        state.update(
            solver_exit_code=return_code,
            solver_end_marker=tracker.saw_end_marker,
            solver_time_s=tracker.current_time_s,
            solver_time_steps_recorded=len(
                [time_s for time_s, _ in tracker.rows if time_s > PARENT_TIME_S + 1e-12]
            ),
            solver_max_u_m_s=tracker.maximum_u_m_s,
            stop_reason=stop_reason,
            pause_observed=paused or PAUSE_FILE.exists() or (run_dir / "PAUSE").exists(),
        )
        if return_code == 0 and stop_reason is None and tracker.saw_end_marker:
            terminal_state = "terminal"
        elif stop_reason and stop_reason.startswith("operational stop: max|U|="):
            terminal_state = "guarded_partial"
        else:
            terminal_state = "incomplete"
        endpoint = None
        if terminal_state in {"terminal", "guarded_partial"} and not state["pause_observed"]:
            endpoint = verify_endpoint(case, float(tracker.current_time_s or 0.0))
            state["terminal_snapshot"] = endpoint
        terminal = build_terminal_status(
            return_code=return_code,
            end_marker=tracker.saw_end_marker,
            actual_time_s=tracker.current_time_s,
            step_count=state["solver_time_steps_recorded"],
            stop_detail=stop_reason,
            pause_observed=state["pause_observed"],
            stop_signals=state.get("stop_signals", []),
            endpoint_verified=endpoint is not None,
            variant=config.variant,
            target_time_s=config.end_time_s,
            solver_log_sha256=state.get("solver_log_sha256"),
            max_speed_csv_sha256=state.get("max_speed_csv_sha256"),
        )
        terminal_state = terminal["state"]
        write_json(case / "terminal-status.json", terminal)
        state["terminal_status_sha256"] = sha256_file(case / "terminal-status.json")
        if terminal_state in {"terminal", "guarded_partial"} and not state["pause_observed"]:
            try:
                state["restart_ledger"] = _run_audit(case, attempt, config)
                state["ledger_status"] = "written_from_hash_bound_parent_checkpoint"
            except Exception as error:
                state["ledger_status"] = "failed_preserved"
                state["ledger_error"] = f"{type(error).__name__}: {error}"
        else:
            state["ledger_status"] = "not_run_incomplete_or_paused"
        try:
            state["solver_convergence"] = pilot.inspect_solver_convergence(
                attempt / "solver.log", case / "system/fvSolution"
            )
        except Exception as error:
            state["solver_convergence"] = {
                "all_converged": False,
                "error": f"{type(error).__name__}: {error}",
            }
        state["step_accounting"] = pilot._write_step_accounting(attempt, job_id)
        if (
            terminal_state == "terminal"
            and state.get("ledger_status") == "written_from_hash_bound_parent_checkpoint"
            and state.get("solver_convergence", {}).get("all_converged") is True
        ):
            state["status"] = "solver_complete_exploratory"
        elif (
            terminal_state == "guarded_partial"
            and state.get("ledger_status") == "written_from_hash_bound_parent_checkpoint"
        ):
            state["status"] = "u_guard_partial_preserved"
        else:
            state["status"] = "stopped_with_preserved_evidence"
    except Exception as error:
        state["status"] = "failed_preserved"
        state["error"] = f"{type(error).__name__}: {error}"
        state["traceback"] = traceback.format_exc()
    finally:
        state["run_wall_s"] = time.monotonic() - started
        try:
            if attempt.exists():
                archive, archive_sha, member_count, member_sizes = pilot.pack_attempt(
                    attempt, run_dir
                )
                state["result_archive"] = str(archive)
                state["result_archive_sha256"] = archive_sha
                state["result_archive_members"] = member_count
                state["result_archive_member_sizes"] = member_sizes
                state["attempt_archive_status"] = "verified_crc_hash_and_member_list"
            else:
                state["attempt_archive_status"] = "no_attempt_directory"
        except Exception as error:
            state["attempt_archive_status"] = "verification_or_pack_failed_preserved"
            state["archive_error"] = f"{type(error).__name__}: {error}"
        write_state()
    return (
        0
        if state.get("status") == "solver_complete_exploratory"
        and state.get("attempt_archive_status") == "verified_crc_hash_and_member_list"
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--variant", choices=tuple(VARIANT_SETTINGS), default="original-smoke")
    args = parser.parse_args()
    return run(args.run_root, config_for_variant(args.variant))


if __name__ == "__main__":
    raise SystemExit(main())
