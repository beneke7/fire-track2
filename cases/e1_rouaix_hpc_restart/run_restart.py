#!/usr/bin/env python3
"""Run the bounded native .2-to-.201 s Rouaix restart smoke on Komondor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
from cases.e1_rouaix_hpc_restart.audit_restart import (  # noqa: E402
    PARENT_CONTRACT_PROFILES as PARENT_CONTRACT_SPECS,
)

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
    "original-early-save": {
        "end_time_s": 0.202,
        "write_interval_s": 0.002,
        "wall_budget_s": 1200,
    },
    "original-control": {"end_time_s": 0.3, "write_interval_s": 0.1, "wall_budget_s": 5400},
    "pressure-total-p0-zero": {
        "end_time_s": 0.3,
        "write_interval_s": 0.05,
        "wall_budget_s": 5400,
    },
    "pressure-total-pcgdic": {
        "end_time_s": 0.255,
        "write_interval_s": 0.005,
        "wall_budget_s": 7200,
    },
    "pressure-total-continuation": {
        "start_time_s": 0.3,
        "end_time_s": 0.5,
        "write_interval_s": 0.05,
        "wall_budget_s": 7200,
    },
    "pressure-pcgdic-continuation": {
        "start_time_s": 0.255,
        "end_time_s": 0.3,
        "write_interval_s": 0.005,
        "wall_budget_s": 7200,
    },
}
CASE_IDS = {
    "original-smoke": "rouaix-restart-original-smoke-0201",
    "original-early-save": "rouaix-restart-original-early-save-0202",
    "original-control": "rouaix-restart-original-control-0300",
    "pressure-total-p0-zero": "rouaix-restart-pressure-total-p0-zero-0300",
    "pressure-total-pcgdic": "rouaix-restart-pressure-total-pcgdic-0255",
    "pressure-total-continuation": "rouaix-restart-pressure-total-continuation-0500",
    "pressure-pcgdic-continuation": "rouaix-restart-pressure-pcgdic-continuation-0300",
}
EARLY_SAVE_STOP_REASON = "diagnostic early-save requested after 3 completed continuation steps"
EARLY_SAVE_TERMINAL_REASON = "diagnostic_early_save_after_3_steps"
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
PRESSURE_TOTAL_PATCHES = ("downstreamOutlet", "bottomOutlet", "spanwiseMinus", "spanwisePlus")
MESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
TIME_FIELD_LINE = re.compile(r"^\s*(value|name|index|deltaT|deltaT0)\s+([^;]+);\s*$", re.MULTILINE)


class RestartError(RuntimeError):
    """The immutable checkpoint or bounded restart contract did not verify."""


def validate_checkpoint_time(time_text: str, checkpoint_time_s: float = PARENT_TIME_S) -> None:
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
    time_name = f"{checkpoint_time_s:.12f}"
    if fields["name"] != f'"{time_name}"':
        raise RestartError("checkpoint uniform/time name differs from the checkpoint directory")
    if index != round(checkpoint_time_s / DT_S):
        raise RestartError("checkpoint uniform/time index does not match its declared time")
    if delta_t_s != DT_S or delta_t0_s != DT_S:
        raise RestartError("checkpoint uniform/time timestep does not equal 0.0001 s")
    if not math.isclose(value_s, checkpoint_time_s, rel_tol=0.0, abs_tol=1e-12):
        expected = "exactly 0.2 s" if checkpoint_time_s == PARENT_TIME_S else "its declared time"
        raise RestartError(f"checkpoint uniform/time does not record {expected}")


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
        expected_start = declared.get("start_time_s", PARENT_TIME_S)
        if self.start_time_s != expected_start or self.delta_t_s != DT_S:
            raise RestartError(
                f"restart must begin at {expected_start:g} s with fixed deltaT {DT_S:g} s"
            )
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
        if self.variant == "pressure-total-p0-zero" and expected_steps != 1000:
            raise RestartError(
                "pressure-total sensitivity must contain exactly 1000 continuation steps"
            )
        if self.variant == "pressure-total-pcgdic" and expected_steps != 550:
            raise RestartError("pressure PCG/DIC sensitivity must contain exactly 550 steps")
        if self.variant == "original-early-save" and expected_steps < 3:
            raise RestartError("early-save horizon must allow at least three continuation steps")
        if self.variant == "pressure-total-continuation" and expected_steps != 2000:
            raise RestartError("pressure-total continuation must contain exactly 2000 steps")
        if self.variant == "pressure-pcgdic-continuation" and expected_steps != 450:
            raise RestartError("pressure PCG/DIC continuation must contain exactly 450 steps")
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


def _member_list_sha256(names: list[str]) -> str:
    if len(names) != len(set(names)):
        raise RestartError("parent archive member list contains duplicates")
    return hashlib.sha256(("\n".join(sorted(names)) + "\n").encode()).hexdigest()


def _is_subsequence(values: list[str], sequence: list[str]) -> bool:
    iterator = iter(sequence)
    return all(any(candidate == value for candidate in iterator) for value in values)


def validate_parent_contract(
    contract: dict[str, Any], *, expected_time_s: float | None = None
) -> dict[str, Any]:
    """Validate a hash-bound .3 total-pressure or .255 PCG/DIC checkpoint."""
    required = {
        "schema_version",
        "parent_job_id",
        "case_id",
        "variant",
        "parent_run_dir",
        "run_state_path",
        "run_state_sha256",
        "archive_path",
        "archive_sha256",
        "archive_member_count",
        "archive_members_sha256",
        "archive_members",
        "ledger_member",
        "ledger_sha256",
        "manifest_member",
        "manifest_sha256",
        "terminal_member",
        "terminal_sha256",
        "checkpoint_time_s",
        "checkpoint_time_dir",
        "delta_t_s",
        "step_count",
        "inventory_m3",
        "inventory_history_member",
        "inventory_history_sha256",
        "inventory_history_time_s",
        "inventory_history_m3",
        "density_kg_m3",
        "checkpoint_fields",
        "processor_mesh",
        "verified_utc",
    }
    missing = sorted(required - contract.keys())
    if missing:
        raise RestartError(f"parent checkpoint contract lacks {missing}")
    if contract["schema_version"] != 1:
        raise RestartError("unsupported parent checkpoint contract schema")
    parent_variant = contract["variant"]
    spec = PARENT_CONTRACT_SPECS.get(parent_variant)
    if (
        not str(contract["parent_job_id"]).isdigit()
        or spec is None
        or contract["case_id"] != spec["case_id"]
    ):
        raise RestartError("parent contract does not identify an explicitly supported clean run")
    checkpoint_time = float(contract["checkpoint_time_s"])
    if expected_time_s is not None and not math.isclose(
        checkpoint_time, expected_time_s, rel_tol=0.0, abs_tol=1e-12
    ):
        raise RestartError("parent contract checkpoint time differs from the continuation start")
    if (
        not math.isclose(checkpoint_time, spec["target_time_s"], rel_tol=0.0, abs_tol=1e-12)
        or contract["checkpoint_time_dir"] != f"processors120/{checkpoint_time:.12f}"
        or not math.isclose(float(contract["delta_t_s"]), DT_S, rel_tol=0.0, abs_tol=1e-15)
        or contract["step_count"] != spec["step_count"]
    ):
        raise RestartError(
            f"parent contract does not describe the exact {spec['target_time_s']:g} s, "
            f"{spec['step_count']}-step checkpoint"
        )
    for key, expected in (
        ("parent_start_time_s", spec["start_time_s"]),
        ("parent_target_time_s", spec["target_time_s"]),
    ):
        if key in contract and not math.isclose(
            float(contract[key]), expected, rel_tol=0.0, abs_tol=1e-12
        ):
            raise RestartError(f"parent contract {key} differs from the verified parent profile")
    if (
        not math.isfinite(float(contract["inventory_m3"]))
        or float(contract["inventory_m3"]) < 0
        or not math.isclose(
            float(contract["inventory_history_time_s"]), checkpoint_time, rel_tol=0.0, abs_tol=1e-12
        )
        or not math.isclose(
            float(contract["inventory_history_m3"]),
            float(contract["inventory_m3"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        or not math.isclose(float(contract["density_kg_m3"]), 997.6, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise RestartError("parent contract inventory or water density is invalid")
    for key in (
        "run_state_sha256",
        "archive_sha256",
        "archive_members_sha256",
        "ledger_sha256",
        "manifest_sha256",
        "terminal_sha256",
        "inventory_history_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(contract[key])):
            raise RestartError(f"parent contract {key} is not a lowercase SHA-256")
    archive_members = contract["archive_members"]
    if (
        not isinstance(archive_members, list)
        or contract["archive_member_count"] != len(archive_members)
        or _member_list_sha256(archive_members) != contract["archive_members_sha256"]
    ):
        raise RestartError("parent contract archive-member receipt is incomplete or inconsistent")
    expected_members = {
        "attempt/manifest.json",
        "attempt/ledger/summary.json",
        "attempt/case/terminal-status.json",
        contract["inventory_history_member"],
        *(
            f"attempt/case/{contract['checkpoint_time_dir']}/{name}"
            for name in REQUIRED_CHECKPOINT_FIELDS
        ),
        *(f"attempt/case/processors120/constant/polyMesh/{name}" for name in MESH_FILES),
    }
    if not expected_members.issubset(set(archive_members)):
        raise RestartError("parent contract archive list omits required checkpoint members")
    fields = contract["checkpoint_fields"]
    if set(fields) != set(REQUIRED_CHECKPOINT_FIELDS):
        raise RestartError("parent contract does not hash all required checkpoint fields")
    for name, receipt in fields.items():
        if (
            not isinstance(receipt, dict)
            or not isinstance(receipt.get("bytes"), int)
            or receipt["bytes"] < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("sha256", "")))
        ):
            raise RestartError(f"parent contract field hash is invalid for {name}")
    mesh = contract["processor_mesh"]
    if not isinstance(mesh, dict) or not set(MESH_FILES).issubset(mesh):
        raise RestartError("parent contract processor120 mesh receipt is incomplete")
    for name in MESH_FILES:
        receipt = mesh[name]
        if (
            not isinstance(receipt, dict)
            or not isinstance(receipt.get("bytes"), int)
            or receipt["bytes"] < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("sha256", "")))
        ):
            raise RestartError(f"parent contract mesh hash is invalid for {name}")
    if contract["ledger_member"] != "attempt/ledger/summary.json":
        raise RestartError("parent contract ledger member path is unexpected")
    if contract["manifest_member"] != "attempt/manifest.json":
        raise RestartError("parent contract manifest member path is unexpected")
    if contract["terminal_member"] != "attempt/case/terminal-status.json":
        raise RestartError("parent contract terminal member path is unexpected")
    if parent_variant == "pressure-total-pcgdic":
        if contract.get("fv_solution_member") != "attempt/case/system/fvSolution":
            raise RestartError("PCG/DIC parent contract solver-dictionary path is unexpected")
        if not re.fullmatch(r"[0-9a-f]{64}", str(contract.get("fv_solution_sha256", ""))):
            raise RestartError("PCG/DIC parent contract solver-dictionary SHA-256 is invalid")
        if contract["fv_solution_member"] not in archive_members:
            raise RestartError("PCG/DIC parent archive omits its bound solver dictionary")
    elif "fv_solution_sha256" in contract or "fv_solution_member" in contract:
        raise RestartError(
            "legacy total-pressure contract must not add a solver-dictionary override"
        )
    history_member = safe_member_path(str(contract["inventory_history_member"])).as_posix()
    if not history_member.startswith("attempt/case/postProcessing/waterInventory/"):
        raise RestartError("parent contract inventory-history member path is unexpected")
    for key in ("parent_run_dir", "run_state_path", "archive_path"):
        if not isinstance(contract[key], str) or not contract[key]:
            raise RestartError(f"parent contract {key} is invalid")
    return contract


def _parent_inventory_sample(raw: bytes, checkpoint_time_s: float) -> float:
    lines = raw.decode("ascii", errors="strict").splitlines()
    if not lines or "Time" not in lines[0] or "alpha.water" not in lines[0]:
        raise RestartError(
            "parent native inventory history header is not volIntegrate(alpha.water)"
        )
    samples: list[tuple[float, float]] = []
    for line in lines[1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        columns = line.split()
        if len(columns) != 2:
            raise RestartError("parent native inventory history row is malformed")
        try:
            time_s, inventory_m3 = map(float, columns)
        except ValueError as error:
            raise RestartError(
                "parent native inventory history contains nonnumeric values"
            ) from error
        if not math.isfinite(time_s) or not math.isfinite(inventory_m3) or inventory_m3 < 0:
            raise RestartError("parent native inventory history contains invalid values")
        samples.append((time_s, inventory_m3))
    endpoint = [
        inventory for time_s, inventory in samples if abs(time_s - checkpoint_time_s) <= 1e-10
    ]
    if len(endpoint) != 1 or not samples or abs(samples[-1][0] - checkpoint_time_s) > 1e-10:
        raise RestartError(
            "parent native inventory history lacks its unique exact checkpoint sample"
        )
    return endpoint[0]


class _HashingReader:
    """Hash compressed archive bytes while tarfile consumes one forward-only pass."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.digest = hashlib.sha256()

    def read(self, size: int = -1) -> bytes:
        data = self.stream.read(size)
        self.digest.update(data)
        return data


def _history_member_from_ledger(
    parent_run_dir: Path, ledger: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    try:
        source = ledger["input_sources"]["native_histories"]["water_inventory"]
        source_path = Path(source["path"])
        source_sha = str(source["sha256"])
    except (KeyError, TypeError) as error:
        raise RestartError(
            "parent ledger lacks its hash-bound native water-inventory history"
        ) from error
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        raise RestartError("parent native water-inventory history SHA-256 is invalid")
    case_root = parent_run_dir / "attempt/case"
    try:
        raw_path = source_path if source_path.is_absolute() else case_root / source_path
        if raw_path.is_symlink():
            raise RestartError("parent native inventory history must not be a symbolic link")
        resolved = raw_path.resolve(strict=True)
        relative = resolved.relative_to(case_root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise RestartError(
            "parent native inventory history is outside the captured case"
        ) from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise RestartError("parent native inventory history member path is unsafe")
    member = f"attempt/case/{relative.as_posix()}"
    if not resolved.is_file() or resolved.is_symlink() or sha256_file(resolved) != source_sha:
        raise RestartError("parent native inventory history changed after its ledger audit")
    return member, {"path": str(resolved), "sha256": source_sha}


def verify_parent_contract_archive(contract: dict[str, Any]) -> dict[str, Any]:
    """Recheck the frozen parent archive, ledger, and restart checkpoint binding."""
    validate_parent_contract(contract)
    spec = PARENT_CONTRACT_SPECS[contract["variant"]]
    target_time_s = float(spec["target_time_s"])
    start_time_s = float(spec["start_time_s"])
    step_count = int(spec["step_count"])
    archive = Path(contract["archive_path"])
    state_path = Path(contract["run_state_path"])
    parent_run_dir = Path(contract["parent_run_dir"])
    if any(path.is_symlink() for path in (parent_run_dir, archive, state_path)) or not all(
        path.is_file() for path in (archive, state_path)
    ):
        raise RestartError("hash-bound parent archive or run-state changed after dispatch")
    try:
        state_raw = state_path.read_bytes()
        state = json.loads(state_raw)
    except (OSError, json.JSONDecodeError) as error:
        raise RestartError("parent run-state is unreadable") from error
    if hashlib.sha256(state_raw).hexdigest() != contract["run_state_sha256"]:
        raise RestartError("hash-bound parent run-state changed after dispatch")
    if (
        state_path.resolve() != (parent_run_dir / "run-state.json").resolve()
        or archive.resolve() != (parent_run_dir / "result.tar.gz").resolve()
    ):
        raise RestartError("parent run-state or archive path differs from its bound run directory")
    state_expected = {
        "status": "solver_complete_exploratory",
        "job_id": str(contract["parent_job_id"]),
        "case_id": spec["case_id"],
        "variant": contract["variant"],
        "solver_exit_code": 0,
        "solver_end_marker": True,
        "solver_time_steps_recorded": step_count,
        "stop_reason": None,
        "pause_observed": False,
        "ledger_status": "written_from_hash_bound_parent_checkpoint",
        "attempt_archive_status": "verified_crc_hash_and_member_list",
        "result_archive": str(archive),
        "result_archive_sha256": contract["archive_sha256"],
        "result_archive_members": contract["archive_member_count"],
    }
    if any(state.get(key) != value for key, value in state_expected.items()):
        raise RestartError(
            "hash-bound parent run-state does not identify the verified clean parent run"
        )
    if (
        contract["variant"] == "pressure-total-pcgdic"
        and state.get("solver_convergence", {}).get("all_converged") is not True
    ):
        raise RestartError("hash-bound PCG/DIC parent run-state lacks converged pressure solves")
    for key, expected in (
        ("start_time_s", start_time_s),
        ("target_time_s", target_time_s),
        ("solver_time_s", target_time_s),
        ("delta_t_s", DT_S),
    ):
        try:
            actual = float(state[key])
        except (KeyError, TypeError, ValueError) as error:
            raise RestartError(f"parent run-state {key} is invalid") from error
        if not math.isfinite(actual) or not math.isclose(
            actual, expected, rel_tol=0.0, abs_tol=1e-12
        ):
            raise RestartError(f"parent run-state {key} differs from the clean parent contract")
    try:
        max_u = float(state["solver_max_u_m_s"])
    except (KeyError, TypeError, ValueError) as error:
        raise RestartError("parent run-state max|U| is missing or invalid") from error
    if not math.isfinite(max_u) or max_u >= 1000.0:
        raise RestartError("parent run-state reached the existing max|U| guard")

    size_receipt = state.get("result_archive_member_sizes")
    if (
        not isinstance(size_receipt, list)
        or any(
            not isinstance(item, dict) or not isinstance(item.get("path"), str)
            for item in size_receipt
        )
        or not _is_subsequence([item["path"] for item in size_receipt], contract["archive_members"])
    ):
        raise RestartError("parent run-state archive member receipt differs from the contract")

    expected_hashes = {
        contract["manifest_member"]: contract["manifest_sha256"],
        contract["ledger_member"]: contract["ledger_sha256"],
        contract["terminal_member"]: contract["terminal_sha256"],
        contract["inventory_history_member"]: contract["inventory_history_sha256"],
    }
    expected_hashes.update(
        {
            f"attempt/case/{contract['checkpoint_time_dir']}/{name}": value["sha256"]
            for name, value in contract["checkpoint_fields"].items()
        }
    )
    expected_hashes.update(
        {
            f"attempt/case/processors120/constant/polyMesh/{name}": value["sha256"]
            for name, value in contract["processor_mesh"].items()
        }
    )
    if contract["variant"] == "pressure-total-pcgdic":
        expected_hashes[contract["fv_solution_member"]] = contract["fv_solution_sha256"]
    small_members = {
        contract["manifest_member"],
        contract["ledger_member"],
        contract["terminal_member"],
        contract["inventory_history_member"],
        f"attempt/case/{contract['checkpoint_time_dir']}/uniform/time",
    }
    if contract["variant"] == "pressure-total-pcgdic":
        small_members.add(contract["fv_solution_member"])
    actual_names: list[str] = []
    actual_file_sizes: list[dict[str, Any]] = []
    extracted: dict[str, bytes] = {}
    found_hashes: set[str] = set()
    archive_reader: _HashingReader
    with archive.open("rb") as raw_archive:
        archive_reader = _HashingReader(raw_archive)
        with tarfile.open(fileobj=archive_reader, mode="r|gz") as tar:
            for member in tar:
                name = safe_member_path(member.name).as_posix()
                if name in actual_names:
                    raise RestartError(f"parent archive contains duplicate member {name}")
                actual_names.append(name)
                if not (member.isfile() or member.isdir()):
                    raise RestartError(f"parent archive contains a link or special member {name}")
                if member.isdir():
                    continue
                actual_file_sizes.append({"path": name, "bytes": member.size})
                if name not in expected_hashes:
                    continue
                source = tar.extractfile(member)
                if source is None:
                    raise RestartError(f"cannot read parent archive member {name}")
                digest = hashlib.sha256()
                small = bytearray() if name in small_members else None
                with source:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        if small is not None:
                            small.extend(chunk)
                if digest.hexdigest() != expected_hashes[name]:
                    raise RestartError(f"parent archive member hash differs from contract: {name}")
                found_hashes.add(name)
                if small is not None:
                    extracted[name] = bytes(small)
            # Drain gzip through its trailer so its CRC is checked and the raw-byte
            # digest covers the full compressed archive, including tar padding.
            while tar.fileobj.read(1024 * 1024):
                pass

    if archive_reader.digest.hexdigest() != contract["archive_sha256"]:
        raise RestartError("parent archive SHA-256 differs from its hash-bound contract")
    if (
        actual_names != contract["archive_members"]
        or len(actual_names) != contract["archive_member_count"]
        or _member_list_sha256(actual_names) != contract["archive_members_sha256"]
        or actual_file_sizes != size_receipt
    ):
        raise RestartError("parent archive members or sizes differ from the verified contract")
    if found_hashes != set(expected_hashes):
        raise RestartError("parent archive omits one or more hash-bound checkpoint members")

    manifest = json.loads(extracted[contract["manifest_member"]])
    terminal = json.loads(extracted[contract["terminal_member"]])
    ledger = json.loads(extracted[contract["ledger_member"]])
    if (
        manifest.get("case_id") != spec["case_id"]
        or manifest.get("rank_count") != EXPECTED_RANKS
        or not math.isclose(
            float(manifest.get("start_time_s", math.nan)), start_time_s, abs_tol=1e-12
        )
        or not math.isclose(
            float(manifest.get("horizon_s", math.nan)), target_time_s, abs_tol=1e-12
        )
        or not math.isclose(float(manifest.get("delta_t_s", math.nan)), DT_S, abs_tol=1e-15)
    ):
        raise RestartError("parent archive manifest does not describe the verified run interval")
    if manifest.get("pressure_total_p0_zero_sensitivity", {}).get("p0_gauge_pa") != 0.0:
        raise RestartError(
            "parent archive manifest does not preserve its p0=0 boundary intervention"
        )
    expected_terminal = {
        "state": "terminal",
        "solver_exit_code": 0,
        "solver_end_marker": True,
        "pause_observed": False,
        "stop_reason": None,
        "solver_time_steps_recorded": step_count,
    }
    if any(terminal.get(key) != value for key, value in expected_terminal.items()):
        raise RestartError("parent archive terminal receipt is incomplete or guarded")
    for key, value in (
        ("solver_time_s", target_time_s),
        ("target_time_s", target_time_s),
        ("requested_start_time_s", start_time_s),
    ):
        if not math.isclose(float(terminal.get(key, math.nan)), value, rel_tol=0.0, abs_tol=1e-10):
            raise RestartError(
                f"parent terminal receipt {key} differs from the checkpoint endpoint"
            )
    coverage = ledger.get("coverage", {})
    interval = ledger.get("interval", {})
    integration = ledger.get("integration", {})
    if (
        coverage.get("status") != "requested_horizon_reached_exploratory_only"
        or coverage.get("requested_target_reached") is not True
        or not math.isclose(
            float(coverage.get("actual_end_time_s", math.nan)), target_time_s, abs_tol=1e-10
        )
        or interval.get("step_count") != step_count
        or not math.isclose(float(integration.get("density_kg_m3", math.nan)), 997.6, abs_tol=1e-12)
        or not math.isclose(
            float(integration.get("final_inventory_m3", math.nan)),
            float(contract["inventory_m3"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    ):
        raise RestartError("parent ledger does not verify the requested time and inventory")
    history_member, history_source = _history_member_from_ledger(parent_run_dir, ledger)
    if (
        history_member != contract["inventory_history_member"]
        or history_source["sha256"] != contract["inventory_history_sha256"]
        or not math.isclose(
            _parent_inventory_sample(
                extracted[contract["inventory_history_member"]],
                float(contract["checkpoint_time_s"]),
            ),
            float(contract["inventory_m3"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    ):
        raise RestartError("parent native inventory history differs from its ledger or contract")
    validate_checkpoint_time(
        extracted[f"attempt/case/{contract['checkpoint_time_dir']}/uniform/time"].decode("ascii"),
        checkpoint_time_s=float(contract["checkpoint_time_s"]),
    )
    if contract["variant"] == "pressure-total-pcgdic":
        solver_settings = validate_pcg_dic_solver_text(
            extracted[contract["fv_solution_member"]].decode("ascii")
        )
        declared_settings = manifest.get("pressure_linear_solver_sensitivity", {})
        if (
            declared_settings.get("solver") != solver_settings["solver"]
            or declared_settings.get("preconditioner") != solver_settings["preconditioner"]
            or declared_settings.get("p_rgh_maxIter") != solver_settings["p_rgh_maxIter"]
            or not math.isclose(
                float(declared_settings.get("tolerance", math.nan)),
                solver_settings["tolerance"],
                rel_tol=0.0,
                abs_tol=1e-15,
            )
            or not math.isclose(
                float(declared_settings.get("relTol", math.nan)),
                solver_settings["relTol"],
                rel_tol=0.0,
                abs_tol=1e-15,
            )
            or declared_settings.get("p_rghFinal") != "inherits PCG/DIC with relTol 0"
        ):
            raise RestartError("parent manifest PCG/DIC settings differ from fvSolution")
    return {"manifest": manifest, "terminal": terminal, "ledger": ledger, "run_state": state}


def verify_completed_parent(run_dir: Path, job_id: str) -> dict[str, Any]:
    """Build a contract for one exact clean total-pressure parent result."""
    if not job_id.isdigit():
        raise RestartError("parent job ID must be numeric")
    run_dir = run_dir.resolve(strict=True)
    state_path = run_dir / "run-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    spec = PARENT_CONTRACT_SPECS.get(str(state.get("variant", "")))
    if spec is None:
        raise RestartError("parent run variant is not an explicitly supported continuation parent")
    parent_variant = str(state["variant"])
    target_time_s = float(spec["target_time_s"])
    start_time_s = float(spec["start_time_s"])
    step_count = int(spec["step_count"])
    exact_state = {
        "status": "solver_complete_exploratory",
        "job_id": job_id,
        "case_id": spec["case_id"],
        "variant": parent_variant,
        "solver_exit_code": 0,
        "solver_end_marker": True,
        "solver_time_steps_recorded": step_count,
        "start_time_s": start_time_s,
        "target_time_s": target_time_s,
        "delta_t_s": DT_S,
        "solver_time_s": target_time_s,
        "stop_reason": None,
        "pause_observed": False,
        "ledger_status": "written_from_hash_bound_parent_checkpoint",
        "attempt_archive_status": "verified_crc_hash_and_member_list",
    }
    for key, value in exact_state.items():
        if state.get(key) != value:
            raise RestartError(f"completed parent {key}={state.get(key)!r}, expected {value!r}")
    if (
        not math.isfinite(float(state.get("solver_max_u_m_s", math.nan)))
        or state["solver_max_u_m_s"] >= 1000.0
    ):
        raise RestartError("parent run reached the existing max|U| guard")
    if (
        parent_variant == "pressure-total-pcgdic"
        and state.get("solver_convergence", {}).get("all_converged") is not True
    ):
        raise RestartError("PCG/DIC parent solver convergence receipt is incomplete or failed")

    attempt = run_dir / "attempt"
    archive = run_dir / "result.tar.gz"
    members_path = run_dir / "result-members.txt"
    manifest_path = attempt / "manifest.json"
    ledger_path = attempt / "ledger/summary.json"
    terminal_path = attempt / "case/terminal-status.json"
    if state.get("result_archive") != str(archive) or not all(
        path.is_file() and not path.is_symlink()
        for path in (archive, members_path, manifest_path, ledger_path, terminal_path)
    ):
        raise RestartError("completed parent is missing its captured archive or audit receipts")
    member_names = members_path.read_text(encoding="utf-8").splitlines()
    member_sizes = state.get("result_archive_member_sizes")
    if (
        len(member_names) != state.get("result_archive_members")
        or not isinstance(member_sizes, list)
        or any(not isinstance(item, dict) for item in member_sizes)
        or not _is_subsequence([item.get("path") for item in member_sizes], member_names)
    ):
        raise RestartError("parent archive member list differs from its pack receipt")
    _member_list_sha256(member_names)
    if not re.fullmatch(r"[0-9a-f]{64}", str(state.get("result_archive_sha256", ""))):
        raise RestartError("parent run-state lacks a valid result archive SHA-256")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    coverage = ledger.get("coverage", {})
    integration = ledger.get("integration", {})
    interval = ledger.get("interval", {})
    inventory = float(integration.get("final_inventory_m3", math.nan))
    if (
        coverage.get("status") != "requested_horizon_reached_exploratory_only"
        or coverage.get("requested_target_reached") is not True
        or not math.isclose(
            float(coverage.get("actual_end_time_s", math.nan)), target_time_s, abs_tol=1e-10
        )
        or interval.get("step_count") != step_count
        or not math.isfinite(inventory)
        or inventory < 0
    ):
        raise RestartError("parent incremental ledger does not cover its exact requested horizon")
    history_member, history_source = _history_member_from_ledger(run_dir, ledger)
    if history_member not in member_names:
        raise RestartError(
            "parent archive member list omits the audited native water-inventory history"
        )
    history_path = Path(history_source["path"])
    history_bytes = history_path.read_bytes()
    history_inventory = _parent_inventory_sample(history_bytes, target_time_s)
    if not math.isclose(history_inventory, inventory, rel_tol=0.0, abs_tol=1e-12):
        raise RestartError("parent native endpoint inventory differs from the audited ledger")

    checkpoint_time_dir = f"processors120/{target_time_s:.12f}"
    endpoint = attempt / "case" / checkpoint_time_dir
    checkpoint_fields: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_CHECKPOINT_FIELDS:
        path = endpoint / name
        if path.is_symlink() or not path.is_file():
            raise RestartError(f"completed parent checkpoint lacks regular field {name}")
        checkpoint_fields[name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    validate_checkpoint_time(
        (endpoint / "uniform/time").read_text(encoding="ascii"), checkpoint_time_s=target_time_s
    )
    processor_mesh = attempt / "case/processors120/constant/polyMesh"
    mesh_hashes = {
        name: {
            "bytes": (processor_mesh / name).stat().st_size,
            "sha256": sha256_file(processor_mesh / name),
        }
        for name in MESH_FILES
        if (processor_mesh / name).is_file() and not (processor_mesh / name).is_symlink()
    }
    if set(mesh_hashes) != set(MESH_FILES):
        raise RestartError("completed parent processor120 mesh is incomplete")
    if manifest.get("pressure_total_p0_zero_sensitivity", {}).get("p0_gauge_pa") != 0.0:
        raise RestartError("parent manifest does not preserve the declared total-pressure p0=0 BC")
    verify_pressure_total_patches(
        endpoint.parent.parent, ROOT / "src/aerial_drop", checkpoint_time_dir=checkpoint_time_dir
    )
    fv_solution_receipt = None
    if parent_variant == "pressure-total-pcgdic":
        fv_solution_path = attempt / "case/system/fvSolution"
        fv_solution_settings = validate_pcg_dic_solver_text(
            fv_solution_path.read_text(encoding="ascii")
        )
        declared_settings = manifest.get("pressure_linear_solver_sensitivity", {})
        if (
            any(
                declared_settings.get(key) != value
                for key, value in (
                    ("solver", fv_solution_settings["solver"]),
                    ("preconditioner", fv_solution_settings["preconditioner"]),
                    ("p_rgh_maxIter", fv_solution_settings["p_rgh_maxIter"]),
                    ("p_rghFinal", fv_solution_settings["p_rghFinal"]),
                )
            )
            or not math.isclose(
                float(declared_settings.get("tolerance", math.nan)),
                fv_solution_settings["tolerance"],
                rel_tol=0.0,
                abs_tol=1e-15,
            )
            or not math.isclose(
                float(declared_settings.get("relTol", math.nan)),
                fv_solution_settings["relTol"],
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        ):
            raise RestartError("PCG/DIC parent manifest does not match its solver dictionary")
        fv_solution_receipt = {
            "member": "attempt/case/system/fvSolution",
            "sha256": sha256_file(fv_solution_path),
        }

    contract = {
        "schema_version": 1,
        "parent_job_id": job_id,
        "case_id": spec["case_id"],
        "variant": parent_variant,
        "parent_start_time_s": start_time_s,
        "parent_target_time_s": target_time_s,
        "parent_run_dir": str(run_dir),
        "run_state_path": str(state_path),
        "run_state_sha256": sha256_file(state_path),
        "archive_path": str(archive),
        "archive_sha256": state["result_archive_sha256"],
        "archive_member_count": len(member_names),
        "archive_members_sha256": _member_list_sha256(member_names),
        "archive_members": member_names,
        "ledger_member": "attempt/ledger/summary.json",
        "ledger_sha256": sha256_file(ledger_path),
        "manifest_member": "attempt/manifest.json",
        "manifest_sha256": sha256_file(manifest_path),
        "terminal_member": "attempt/case/terminal-status.json",
        "terminal_sha256": sha256_file(terminal_path),
        "checkpoint_time_s": target_time_s,
        "checkpoint_time_dir": checkpoint_time_dir,
        "delta_t_s": DT_S,
        "step_count": step_count,
        "inventory_m3": inventory,
        "inventory_history_member": history_member,
        "inventory_history_sha256": history_source["sha256"],
        "inventory_history_time_s": target_time_s,
        "inventory_history_m3": history_inventory,
        "density_kg_m3": float(integration.get("density_kg_m3", math.nan)),
        "checkpoint_fields": checkpoint_fields,
        "processor_mesh": mesh_hashes,
        "verified_utc": datetime.now(UTC).isoformat(),
    }
    if fv_solution_receipt is not None:
        contract["fv_solution_member"] = fv_solution_receipt["member"]
        contract["fv_solution_sha256"] = fv_solution_receipt["sha256"]
    validate_parent_contract(contract, expected_time_s=target_time_s)
    verify_parent_contract_archive(contract)
    return contract


def pressure_total_dictionary_text() -> str:
    patches = "\n".join(
        f"        {patch}\n"
        "        {\n"
        "            type prghTotalPressure;\n"
        "            p0 uniform 0;\n"
        "            rho rho;\n"
        "            U U;\n"
        "            phi phi;\n"
        "            value uniform 0;\n"
        "        }"
        for patch in PRESSURE_TOTAL_PATCHES
    )
    return (
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n"
        "    class dictionary;\n    object changeDictionaryDict;\n}\n\n"
        "p_rgh\n{\n    boundaryField\n    {\n" + patches + "\n    }\n}\n"
    )


def pressure_total_change_command(case: Path) -> list[str]:
    return [
        "srun",
        "--nodes=3",
        "--ntasks=120",
        "--ntasks-per-node=40",
        "changeDictionary",
        "-parallel",
        "-fileHandler",
        "collated",
        "-case",
        str(case),
        "-time",
        "0.2",
        "-dict",
        "system/changeDictionaryDict",
    ]


def _native_field_reader(source_dir: Path) -> Any:
    reader_path = source_dir / "i4f_native_face_reader.py"
    spec = importlib.util.spec_from_file_location("rouaix_native_face_reader", reader_path)
    if spec is None or spec.loader is None:
        raise RestartError("could not load the existing collated native-field reader")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def pressure_checkpoint_integrity(case: Path, source_dir: Path) -> dict[str, Any]:
    endpoint = case / PARENT_TIME_DIR
    reader = _native_field_reader(source_dir)
    chunks = reader._field_chunks(endpoint / "p_rgh", EXPECTED_RANKS)
    rank_hashes: dict[str, str] = {}
    internal_digest = hashlib.sha256()
    internal_count = 0
    for rank, chunk in sorted(chunks.items()):
        values = reader._parse_internal(chunk, "scalar")
        canonical = values.astype("<f8", copy=False).tobytes()
        rank_hash = hashlib.sha256(canonical).hexdigest()
        rank_hashes[str(rank)] = rank_hash
        internal_digest.update(rank.to_bytes(4, "little"))
        internal_digest.update(len(values).to_bytes(8, "little"))
        internal_digest.update(canonical)
        internal_count += len(values)
    unchanged_fields = {
        relative: sha256_file(endpoint / relative)
        for relative in REQUIRED_CHECKPOINT_FIELDS
        if relative != "p_rgh"
    }
    return {
        "unchanged_checkpoint_field_sha256": unchanged_fields,
        "p_rgh_file_sha256": sha256_file(endpoint / "p_rgh"),
        "p_rgh_internal_sha256": internal_digest.hexdigest(),
        "p_rgh_internal_rank_sha256": rank_hashes,
        "p_rgh_internal_value_count": internal_count,
    }


def verify_pressure_total_patches(
    case: Path, source_dir: Path, checkpoint_time_dir: str = PARENT_TIME_DIR
) -> None:
    reader = _native_field_reader(source_dir)
    chunks = reader._field_chunks(case / checkpoint_time_dir / "p_rgh", EXPECTED_RANKS)
    for rank, chunk in sorted(chunks.items()):
        text = chunk.decode("latin1")
        for patch in PRESSURE_TOTAL_PATCHES:
            match = re.search(rf"(?ms)^\s*{re.escape(patch)}\s*\{{(.*?)^\s*\}}", text)
            if match is None:
                raise RestartError(f"p_rgh is missing {patch} on rank {rank}")
            entries = dict(re.findall(r"(?m)^\s*(\w+)\s+([^;]+);", match.group(1)))
            expected = {
                "type": "prghTotalPressure",
                "p0": "uniform 0",
                "rho": "rho",
                "U": "U",
                "phi": "phi",
                "value": "uniform 0",
            }
            if any(entries.get(key) != value for key, value in expected.items()):
                raise RestartError(f"p_rgh total-pressure entries differ on {patch}, rank {rank}")


def apply_pressure_total_restart(
    case: Path,
    attempt: Path,
    run_dir: Path,
    run_root: Path,
    deadline: float,
    state: dict[str, Any],
    write_state: Any,
) -> dict[str, Any]:
    source_dir = attempt / "source"
    dictionary = case / "system/changeDictionaryDict"
    expected_dictionary = pressure_total_dictionary_text()
    if not dictionary.is_file() or dictionary.read_text(encoding="ascii") != expected_dictionary:
        raise RestartError("prepared native pressure change dictionary is missing or changed")
    before = pressure_checkpoint_integrity(case, source_dir)
    pilot.run_setup_command(
        pressure_total_change_command(case),
        cwd=case,
        log_path=attempt / "pressure-total-change.log",
        deadline=deadline,
        run_dir=run_dir,
        shared_pause=PAUSE_FILE,
        project_root=run_root,
        state=state,
        write_state=write_state,
        minimum_free_disk_bytes=MIN_FREE_DISK_BYTES,
    )
    after = pressure_checkpoint_integrity(case, source_dir)
    if before["unchanged_checkpoint_field_sha256"] != after["unchanged_checkpoint_field_sha256"]:
        raise RestartError("native pressure change modified a non-p_rgh checkpoint field")
    if (
        before["p_rgh_internal_sha256"] != after["p_rgh_internal_sha256"]
        or before["p_rgh_internal_rank_sha256"] != after["p_rgh_internal_rank_sha256"]
    ):
        raise RestartError("native pressure change modified the p_rgh internal array")
    if before["p_rgh_file_sha256"] == after["p_rgh_file_sha256"]:
        raise RestartError("native pressure change did not rewrite the p_rgh boundary data")
    verify_pressure_total_patches(case, source_dir)
    receipt = {
        "utility": "changeDictionary -parallel -fileHandler collated -time 0.2",
        "command": pressure_total_change_command(case),
        "dictionary_sha256": sha256_file(dictionary),
        "patches": list(PRESSURE_TOTAL_PATCHES),
        "p0_gauge_pa": 0.0,
        "before": before,
        "after": after,
        "status": "native_boundary_change_verified_internal_arrays_and_other_fields_unchanged",
    }
    write_json(attempt / "pressure-total-change-receipt.json", receipt)
    return receipt


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


def select_seed_members(
    members: list[tarfile.TarInfo],
    checkpoint_time_dir: str = PARENT_TIME_DIR,
    *,
    include_terminal: bool = False,
) -> list[tarfile.TarInfo]:
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
            or (include_terminal and name == "attempt/case/terminal-status.json")
            or case_member == "case/case-inputs.json"
            or case_member.startswith("case/system/")
            or case_member.startswith("case/constant/")
            or case_member.startswith("case/processors120/constant/polyMesh/")
            or case_member.startswith(f"case/{checkpoint_time_dir}/")
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
        *(
            f"{PARENT_CASE_ROOT}/{checkpoint_time_dir}/{name}"
            for name in REQUIRED_CHECKPOINT_FIELDS
        ),
    }
    if include_terminal:
        required.add("attempt/case/terminal-status.json")
    missing = sorted(required - selected_names)
    if missing:
        raise RestartError(f"seed archive lacks required restart members: {missing}")
    return selected


def extract_seed_archive(
    archive: Path, attempt: Path, parent_contract: dict[str, Any] | None = None
) -> dict[str, Any]:
    if archive.is_symlink() or not archive.is_file():
        raise RestartError("parent seed archive must be a regular file")
    if parent_contract is not None:
        verify_parent_contract_archive(parent_contract)
        expected_archive_sha = parent_contract["archive_sha256"]
        checkpoint_time_s = float(parent_contract["checkpoint_time_s"])
        checkpoint_time_dir = str(parent_contract["checkpoint_time_dir"])
        expected_member_count = parent_contract["archive_member_count"]
        expected_member_sha = parent_contract["archive_members_sha256"]
        expected_inventory = float(parent_contract["inventory_m3"])
    else:
        expected_archive_sha = PARENT_ARCHIVE_SHA256
        checkpoint_time_s = PARENT_TIME_S
        checkpoint_time_dir = PARENT_TIME_DIR
        expected_member_count = EXPECTED_ARCHIVE_MEMBERS
        expected_member_sha = None
        expected_inventory = PARENT_INVENTORY_M3
    actual_sha = sha256_file(archive)
    if actual_sha != expected_archive_sha:
        raise RestartError(f"parent seed archive SHA-256 mismatch: {actual_sha}")
    with tarfile.open(archive, mode="r:gz") as tar:
        members = tar.getmembers()
        if len(members) != expected_member_count:
            raise RestartError(
                f"parent archive has {len(members)} members, expected {expected_member_count}"
            )
        actual_names = [safe_member_path(member.name).as_posix() for member in members]
        if (
            expected_member_sha is not None
            and _member_list_sha256(actual_names) != expected_member_sha
        ):
            raise RestartError("parent archive member list differs from the hash-bound contract")
        selected = select_seed_members(
            members,
            checkpoint_time_dir,
            include_terminal=parent_contract is not None,
        )
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
    expected_ledger_sha = (
        parent_contract["ledger_sha256"] if parent_contract is not None else PARENT_LEDGER_SHA256
    )
    if sha256_file(parent_ledger) != expected_ledger_sha:
        raise RestartError("parent ledger summary hash differs from the hash-bound parent receipt")
    parent_manifest_path = attempt / "manifest.json"
    parent_manifest = json.loads(parent_manifest_path.read_text(encoding="utf-8"))
    if parent_contract is None:
        if (
            parent_manifest.get("rank_count") != EXPECTED_RANKS
            or parent_manifest.get("horizon_s") != 0.2
        ):
            raise RestartError("parent run manifest does not prove the 120-rank .2 s checkpoint")
    elif sha256_file(parent_manifest_path) != parent_contract["manifest_sha256"]:
        raise RestartError("parent run manifest hash differs from the hash-bound contract")
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
        if parent_contract is None and (not declared or sha256_file(path) != declared):
            raise RestartError(f"seed case input does not match parent manifest: {relative}")
        actual_original_hashes[relative] = sha256_file(path)
    decomposition = (case / "system/decomposeParDict").read_text(encoding="utf-8")
    if not re.search(r"\bnumberOfSubdomains\s+120\s*;", decomposition):
        raise RestartError("parent decomposition dictionary does not declare 120 subdomains")
    endpoint = case / checkpoint_time_dir
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
    validate_checkpoint_time(time_text, checkpoint_time_s=checkpoint_time_s)
    ledger = json.loads(parent_ledger.read_text(encoding="utf-8"))
    inventory = float(ledger["integration"]["final_inventory_m3"])
    if not math.isclose(inventory, expected_inventory, rel_tol=0.0, abs_tol=1e-12):
        raise RestartError(
            "measured parent checkpoint inventory differs from its hash-bound receipt"
        )
    if parent_contract is not None:
        for name, receipt in parent_contract["checkpoint_fields"].items():
            if checkpoint_hashes.get(name) != receipt:
                raise RestartError(f"extracted checkpoint field differs from contract: {name}")
        for name, receipt in parent_contract["processor_mesh"].items():
            if decomposed_mesh.get(name) != receipt:
                raise RestartError(f"extracted processor120 mesh differs from contract: {name}")
        if sha256_file(attempt / "case/terminal-status.json") != parent_contract["terminal_sha256"]:
            raise RestartError("parent terminal status differs from hash-bound contract")
        if parent_manifest.get("case_id") != parent_contract["case_id"]:
            raise RestartError("parent manifest case ID differs from the hash-bound contract")
        if (
            "fv_solution_sha256" in parent_contract
            and sha256_file(case / "system/fvSolution") != parent_contract["fv_solution_sha256"]
        ):
            raise RestartError("parent solver dictionary differs from the hash-bound contract")
        verify_pressure_total_patches(
            case, ROOT / "src/aerial_drop", checkpoint_time_dir=checkpoint_time_dir
        )
    receipt = {
        "archive_sha256": actual_sha,
        "checkpoint_time_s": checkpoint_time_s,
        "inventory_m3": inventory,
        "archive_status": "verified_crc_hash_and_member_list",
        "selected_endpoint_member": f"{PARENT_CASE_ROOT}/{checkpoint_time_dir}/alpha.water",
        "ledger_sha256": expected_ledger_sha,
    }
    if parent_contract is not None:
        receipt.update(
            parent_job_id=parent_contract["parent_job_id"],
            manifest_sha256=parent_contract["manifest_sha256"],
            terminal_sha256=parent_contract["terminal_sha256"],
        )
        if "fv_solution_sha256" in parent_contract:
            receipt["fv_solution_sha256"] = parent_contract["fv_solution_sha256"]
    write_json(case / "parent-checkpoint-receipt.json", receipt)
    verification = {
        "schema_version": 1,
        "source_archive_sha256": actual_sha,
        "archive_member_count": len(members),
        "archive_members_sha256": hashlib.sha256(
            ("\n".join(sorted(actual_names)) + "\n").encode()
        ).hexdigest(),
        "archive_status": "verified_crc_hash_and_member_list",
        "selected_files": selected_manifest,
        "parent_manifest_sha256": sha256_file(parent_manifest_path),
        "parent_ledger_sha256": expected_ledger_sha,
        "parent_inventory_m3": inventory,
        "parent_case_input_sha256": actual_original_hashes,
        "checkpoint_fields": checkpoint_hashes,
        "collated_decomposition_mesh": decomposed_mesh,
        "checkpoint_receipt_sha256": sha256_file(case / "parent-checkpoint-receipt.json"),
    }
    write_json(attempt / "seed-verification.json", verification)
    if parent_contract is not None:
        terminal_path = attempt / "case/terminal-status.json"
        shutil.copy2(terminal_path, attempt / "parent-terminal-status.json")
        terminal_path.unlink()
    shutil.copy2(parent_ledger, attempt / "parent-ledger-summary.json")
    parent_ledger.unlink()
    shutil.copy2(parent_manifest_path, attempt / "parent-seed-manifest.json")
    parent_manifest_path.unlink()
    return verification


def rewrite_control_dict(
    path: Path,
    config: RestartConfig,
    previous_control: dict[str, float] | None = None,
) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    previous = previous_control or {
        "start_time_s": 0.0,
        "end_time_s": PARENT_TIME_S,
        "write_interval_s": PARENT_TIME_S,
    }
    start_from, count = re.subn(
        r"(?m)^startFrom\s+(?:startTime|latestTime)\s*;", "startFrom latestTime;", text
    )
    if count != 1:
        raise RestartError(f"expected one startFrom setting, found {count}")
    text = start_from
    for name, old_value, new_value in (
        ("startTime", float(previous["start_time_s"]), config.start_time_s),
        ("endTime", float(previous["end_time_s"]), config.end_time_s),
        ("writeInterval", float(previous["write_interval_s"]), config.write_interval_s),
    ):
        pattern = rf"(?m)^{name}\s+([^;\s]+)\s*;"
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise RestartError(f"expected one {name} setting in parent controlDict")
        try:
            actual = float(matches[0].group(1))
        except ValueError as error:
            raise RestartError(f"parent controlDict {name} is not numeric") from error
        if not math.isclose(actual, old_value, rel_tol=0.0, abs_tol=1e-12):
            raise RestartError(
                f"parent controlDict {name}={actual:g} differs from verified parent manifest"
            )
        replacement = f"{name} {new_value:.12g};"
        text = re.sub(pattern, replacement, text)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_text(text, encoding="utf-8")
    delta_matches = list(re.finditer(r"(?m)^[ \t]*deltaT[ \t]+([^;\s]+)[ \t]*;", text))
    adaptive_matches = list(re.finditer(r"(?m)^[ \t]*adjustTimeStep[ \t]+([^;\s]+)[ \t]*;", text))
    if len(delta_matches) != 1 or len(adaptive_matches) != 1:
        raise RestartError("restart changed the fixed time-step controls")
    try:
        actual_delta_t = float(delta_matches[0].group(1))
    except ValueError as error:
        raise RestartError("restart deltaT is not a numeric value") from error
    if (
        not math.isclose(actual_delta_t, DT_S, rel_tol=0.0, abs_tol=1e-15)
        or adaptive_matches[0].group(1).casefold() != "no"
    ):
        raise RestartError("restart changed the fixed time-step controls")
    return {"before_sha256": before, "after_sha256": sha256_file(path)}


def set_rolling_checkpoint_retention(path: Path, retain_count: int = 2) -> dict[str, Any]:
    """Set only controlDict purgeWrite for the rolling-checkpoint diagnostic."""
    if retain_count != 2:
        raise RestartError("this diagnostic retains exactly the last two field checkpoints")
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^[ \t]*purgeWrite[ \t]+([^;\s]+)[ \t]*;", text))
    if len(matches) != 1:
        raise RestartError(f"expected one top-level purgeWrite setting, found {len(matches)}")
    try:
        previous = int(matches[0].group(1))
    except ValueError as error:
        raise RestartError("parent controlDict purgeWrite is not an integer") from error
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    text = re.sub(
        r"(?m)^([ \t]*purgeWrite[ \t]+)[^;\s]+([ \t]*;)",
        rf"\g<1>{retain_count}\g<2>",
        text,
        count=1,
    )
    path.write_text(text, encoding="utf-8")
    after_matches = list(re.finditer(r"(?m)^[ \t]*purgeWrite[ \t]+([^;\s]+)[ \t]*;", text))
    if len(after_matches) != 1 or after_matches[0].group(1) != "2":
        raise RestartError("failed to configure the two-checkpoint rolling retention")
    return {
        "before_sha256": before,
        "after_sha256": sha256_file(path),
        "previous_purge_write": previous,
        "retained_checkpoint_count": retain_count,
    }


def validate_pcg_dic_solver_text(text: str) -> dict[str, Any]:
    """Return the exact inherited PCG/DIC solver controls for a child parent."""
    block_pattern = re.compile(r"(?ms)^[ \t]*p_rgh[ \t]*(?:\n[ \t]*)?\{(?P<body>[^{}]*)\}")
    blocks = list(block_pattern.finditer(text))
    final_blocks = list(re.finditer(r"(?ms)^[ \t]*p_rghFinal[ \t]*\{(?P<body>[^{}]*)\}", text))
    if len(blocks) != 1 or len(final_blocks) != 1:
        raise RestartError("PCG/DIC parent fvSolution lacks unique flat p_rgh solver blocks")

    def one_value(body: str, key: str) -> str:
        matches = list(re.finditer(rf"\b{re.escape(key)}[ \t]+([^;\s]+)[ \t]*;", body))
        if len(matches) != 1:
            raise RestartError(f"PCG/DIC parent p_rgh block must have one {key} entry")
        return matches[0].group(1)

    body = blocks[0].group("body")
    final_body = final_blocks[0].group("body")
    try:
        tolerance = float(one_value(body, "tolerance"))
        rel_tol = float(one_value(body, "relTol"))
        max_iter = int(one_value(body, "maxIter"))
        final_rel_tol = float(one_value(final_body, "relTol"))
    except ValueError as error:
        raise RestartError("PCG/DIC parent fvSolution has nonnumeric solver controls") from error
    solver = one_value(body, "solver")
    preconditioner = one_value(body, "preconditioner")
    if (
        solver != "PCG"
        or preconditioner != "DIC"
        or max_iter != 1000
        or not math.isclose(tolerance, 1e-8, rel_tol=0.0, abs_tol=1e-20)
        or not math.isclose(rel_tol, 0.01, rel_tol=0.0, abs_tol=1e-12)
        or not re.search(r"\$p_rgh\s*;", final_body)
        or not math.isclose(final_rel_tol, 0.0, rel_tol=0.0, abs_tol=1e-15)
    ):
        raise RestartError("PCG/DIC parent fvSolution differs from the frozen solver policy")
    return {
        "solver": solver,
        "preconditioner": preconditioner,
        "p_rgh_maxIter": max_iter,
        "tolerance": tolerance,
        "relTol": rel_tol,
        "p_rghFinal": "inherits PCG/DIC with relTol 0",
    }


def rewrite_p_rgh_solver_to_pcg_dic(path: Path) -> dict[str, Any]:
    """Change only p_rgh to PCG/DIC, preserving pressure tolerance and relTol."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(?ms)^(?P<prefix>[ \t]*p_rgh[ \t]*(?:\n[ \t]*)?\{)(?P<body>[^{}]*)(?P<suffix>\})"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RestartError(f"expected one flat p_rgh fvSolution block, found {len(matches)}")
    body = matches[0].group("body")

    def one_value(source: str, key: str) -> str:
        entries = list(re.finditer(rf"\b{re.escape(key)}[ \t]+([^;\s]+)[ \t]*;", source))
        if len(entries) != 1:
            raise RestartError(f"expected one {key} entry in p_rgh solver block")
        return entries[0].group(1)

    if one_value(body, "solver") != "GAMG":
        raise RestartError("pressure PCG/DIC variant requires the original GAMG parent solver")
    tolerance = one_value(body, "tolerance")
    rel_tol = one_value(body, "relTol")
    if one_value(body, "maxIter") != "100":
        raise RestartError("pressure PCG/DIC variant expects parent p_rgh maxIter 100")
    updated, solver_count = re.subn(r"\bsolver[ \t]+GAMG[ \t]*;", "solver PCG;", body, count=1)
    updated, smoother_count = re.subn(
        r"\bsmoother[ \t]+DICGaussSeidel[ \t]*;", "preconditioner DIC;", updated, count=1
    )
    updated, iteration_count = re.subn(
        r"\bmaxIter[ \t]+100[ \t]*;", "maxIter 1000;", updated, count=1
    )
    if (solver_count, smoother_count, iteration_count) != (1, 1, 1):
        raise RestartError(
            "parent p_rgh solver block differs from the declared GAMG/DICGaussSeidel baseline"
        )
    replacement = f"{matches[0].group('prefix')}{updated}{matches[0].group('suffix')}"
    changed_text = text[: matches[0].start()] + replacement + text[matches[0].end() :]
    final_matches = list(
        re.finditer(r"(?ms)^[ \t]*p_rghFinal[ \t]*\{(?P<body>[^{}]*)\}", changed_text)
    )
    if len(final_matches) != 1:
        raise RestartError("expected one p_rghFinal block inheriting p_rgh")
    final_body = final_matches[0].group("body")
    if not re.search(r"\$p_rgh\s*;", final_body) or one_value(final_body, "relTol") != "0":
        raise RestartError("p_rghFinal must inherit PCG/DIC with its existing relTol 0")
    changed_body = pattern.search(changed_text)
    if changed_body is None:
        raise RestartError("rewritten p_rgh solver block disappeared")
    if (
        one_value(changed_body.group("body"), "solver") != "PCG"
        or one_value(changed_body.group("body"), "preconditioner") != "DIC"
        or one_value(changed_body.group("body"), "tolerance") != tolerance
        or one_value(changed_body.group("body"), "relTol") != rel_tol
        or one_value(changed_body.group("body"), "maxIter") != "1000"
    ):
        raise RestartError("rewritten p_rgh solver settings did not preserve the declared controls")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_text(changed_text, encoding="utf-8")
    path.chmod(path.stat().st_mode & 0o777)
    return {
        "before_sha256": before,
        "after_sha256": sha256_file(path),
        "parent_solver": "GAMG",
        "solver": "PCG",
        "preconditioner": "DIC",
        "tolerance": tolerance,
        "relTol": rel_tol,
        "p_rgh_maxIter": 1000,
        "p_rghFinal": "inherits PCG/DIC with relTol 0",
    }


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
                f"solver log does not prove all {step_count} fixed continuation steps "
                f"after {self.start_time_s:g} s"
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


def prepare_case(
    attempt: Path,
    config: RestartConfig,
    parent_contract: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    case = attempt / "case"
    parent_archive = (
        Path(parent_contract["archive_path"]) if parent_contract is not None else PARENT_ARCHIVE
    )
    parent_archive_sha = (
        parent_contract["archive_sha256"] if parent_contract is not None else PARENT_ARCHIVE_SHA256
    )
    parent_ledger_sha = (
        parent_contract["ledger_sha256"] if parent_contract is not None else PARENT_LEDGER_SHA256
    )
    parent_time_s = (
        float(parent_contract["checkpoint_time_s"])
        if parent_contract is not None
        else PARENT_TIME_S
    )
    parent_time_dir = (
        str(parent_contract["checkpoint_time_dir"])
        if parent_contract is not None
        else PARENT_TIME_DIR
    )
    parent_inventory = (
        float(parent_contract["inventory_m3"])
        if parent_contract is not None
        else PARENT_INVENTORY_M3
    )
    seed_receipt = extract_seed_archive(parent_archive, attempt, parent_contract)
    parent_manifest = json.loads(
        (attempt / "parent-seed-manifest.json").read_text(encoding="utf-8")
    )
    case_inputs_path = case / "case-inputs.json"
    case_inputs = json.loads(case_inputs_path.read_text(encoding="utf-8"))
    case_inputs["restart"] = {
        "start_time_s": config.start_time_s,
        "end_time_s": config.end_time_s,
        "delta_t_s": config.delta_t_s,
        "write_interval_s": config.write_interval_s,
        "parent_archive_sha256": parent_archive_sha,
        "parent_ledger_sha256": parent_ledger_sha,
        "parent_checkpoint_time_s": parent_time_s,
        "parent_checkpoint_inventory_m3": parent_inventory,
        "variant": config.variant,
        "parent_job_id": (
            parent_contract["parent_job_id"] if parent_contract is not None else None
        ),
        "parent_smoke_job_id": os.environ.get("ROUAIX_PARENT_SMOKE_JOB_ID"),
        "fields_mapped_from_prior_run": True,
    }
    write_count = round((config.end_time_s - config.start_time_s) / config.write_interval_s)
    write_times = [
        round(config.start_time_s + index * config.write_interval_s, 12)
        for index in range(1, write_count + 1)
    ]
    case_inputs["field_write_times_s"] = write_times
    case_inputs["file_handler"] = "collated"
    case_inputs["rank_count"] = EXPECTED_RANKS
    case_inputs["node_count"] = EXPECTED_NODES
    case_inputs["tasks_per_node"] = [TASKS_PER_NODE] * EXPECTED_NODES
    write_json(case_inputs_path, case_inputs)
    previous_control = None
    if parent_contract is not None:
        previous_control = {
            "start_time_s": float(parent_manifest["start_time_s"]),
            "end_time_s": float(parent_manifest["horizon_s"]),
            "write_interval_s": float(parent_manifest["write_interval_s"]),
        }
    control_hashes = rewrite_control_dict(
        case / "system/controlDict", config, previous_control=previous_control
    )
    pressure_solver_receipt = None
    if config.variant == "pressure-total-pcgdic":
        control_hashes["rolling_checkpoint_retention"] = set_rolling_checkpoint_retention(
            case / "system/controlDict", retain_count=2
        )
        pressure_solver_receipt = rewrite_p_rgh_solver_to_pcg_dic(case / "system/fvSolution")
        (case / "system/fvSolution").chmod(0o444)
    pressure_dictionary_sha = None
    if config.variant in {"pressure-total-p0-zero", "pressure-total-pcgdic"}:
        dictionary_path = case / "system/changeDictionaryDict"
        dictionary_path.write_text(pressure_total_dictionary_text(), encoding="ascii")
        dictionary_path.chmod(0o444)
        pressure_dictionary_sha = sha256_file(dictionary_path)
        case_inputs["restart"]["pressure_total_p0_zero_sensitivity"] = {
            "type": "prghTotalPressure",
            "p0_gauge_pa": 0.0,
            "patches": list(PRESSURE_TOTAL_PATCHES),
            "dictionary_sha256": pressure_dictionary_sha,
            "scope": "four p_rgh open boundaries only; no paper boundary-condition correction",
        }
        if pressure_solver_receipt is not None:
            case_inputs["restart"]["pressure_linear_solver_sensitivity"] = pressure_solver_receipt
        write_json(case_inputs_path, case_inputs)
    elif config.variant in {"pressure-total-continuation", "pressure-pcgdic-continuation"}:
        verify_pressure_total_patches(
            case, ROOT / "src/aerial_drop", checkpoint_time_dir=parent_time_dir
        )
        if config.variant == "pressure-pcgdic-continuation":
            if parent_contract["variant"] != "pressure-total-pcgdic":
                raise RestartError("PCG/DIC continuation requires the verified PCG/DIC parent")
            fv_solution = case / "system/fvSolution"
            if sha256_file(fv_solution) != parent_contract["fv_solution_sha256"]:
                raise RestartError("PCG/DIC continuation changed the inherited solver dictionary")
            fv_solution.chmod(0o444)
            control_hashes["rolling_checkpoint_retention"] = set_rolling_checkpoint_retention(
                case / "system/controlDict", retain_count=2
            )
        case_inputs["restart"]["pressure_total_p0_zero_sensitivity"] = {
            "type": "prghTotalPressure",
            "p0_gauge_pa": 0.0,
            "patches": list(PRESSURE_TOTAL_PATCHES),
            "inherited_from_parent": parent_contract["archive_sha256"],
            "scope": "conditional exploratory continuation; no outlet BC change",
        }
        if config.variant == "pressure-pcgdic-continuation":
            case_inputs["restart"]["pressure_linear_solver_inherited"] = {
                "solver": "PCG",
                "preconditioner": "DIC",
                "p_rgh_maxIter": 1000,
                "tolerance": 1e-8,
                "relTol": 0.01,
                "p_rghFinal": "inherits PCG/DIC with relTol 0",
                "fv_solution_sha256": parent_contract["fv_solution_sha256"],
                "scope": "inherited unchanged from the verified .255 PCG/DIC checkpoint",
            }
        write_json(case_inputs_path, case_inputs)
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
        "numerical_variant": (
            "inherited-pcg-dic" if config.variant == "pressure-pcgdic-continuation" else "original"
        ),
        "momentum_convection": "limitedLinearV 1",
        "parent_archive_sha256": parent_archive_sha,
        "parent_ledger_sha256": parent_ledger_sha,
        "parent_checkpoint_time_s": parent_time_s,
        "parent_checkpoint_inventory_m3": parent_inventory,
        "write_interval_s": config.write_interval_s,
        "field_write_times_s": write_times,
        "parent_smoke_job_id": os.environ.get("ROUAIX_PARENT_SMOKE_JOB_ID"),
        "parent_checkpoint_receipt_sha256": seed_receipt["checkpoint_receipt_sha256"],
        "controlDict_hashes": control_hashes,
        "file_handler": "collated",
        "formal_validation_decision": None,
    }
    if pressure_dictionary_sha is not None:
        manifest["pressure_total_p0_zero_sensitivity"] = {
            "type": "prghTotalPressure",
            "p0_gauge_pa": 0.0,
            "patches": list(PRESSURE_TOTAL_PATCHES),
            "dictionary_sha256": pressure_dictionary_sha,
            "scope": "four p_rgh open boundaries only; no paper boundary-condition correction",
        }
    if pressure_solver_receipt is not None:
        manifest["pressure_linear_solver_sensitivity"] = {
            **pressure_solver_receipt,
            "input": "same original .2 donor and p0=0 total-pressure patch treatment as job 14702499",
            "checkpoint_policy": "writeInterval 0.005 s and purgeWrite 2; last two field checkpoints retained",
            "scope": "only p_rgh linear solver changed; exploratory numerical sensitivity, not a physics correction",
        }
    elif config.variant == "pressure-total-continuation":
        manifest["pressure_total_p0_zero_sensitivity"] = {
            "type": "prghTotalPressure",
            "p0_gauge_pa": 0.0,
            "patches": list(PRESSURE_TOTAL_PATCHES),
            "inherited_from_parent_archive_sha256": parent_archive_sha,
            "scope": "conditional exploratory continuation; no outlet BC change",
        }
    elif config.variant == "pressure-pcgdic-continuation":
        manifest["pressure_total_p0_zero_sensitivity"] = {
            "type": "prghTotalPressure",
            "p0_gauge_pa": 0.0,
            "patches": list(PRESSURE_TOTAL_PATCHES),
            "inherited_from_parent_archive_sha256": parent_archive_sha,
            "scope": "conditional exploratory continuation; no outlet BC change",
        }
        manifest["pressure_linear_solver_inherited"] = case_inputs["restart"][
            "pressure_linear_solver_inherited"
        ]
    write_json(attempt / "manifest.json", manifest)
    source_dir = attempt / "source"
    source_dir.mkdir()
    sbatch_path = {
        "original-control": "restart_control.sbatch",
        "original-early-save": "restart_early_save.sbatch",
        "pressure-total-p0-zero": "restart_pressure.sbatch",
        "pressure-total-pcgdic": "restart_pressure_pcgdic.sbatch",
        "pressure-total-continuation": "restart_pressure_continue.sbatch",
        "pressure-pcgdic-continuation": "restart_pressure_pcgdic_continue.sbatch",
    }.get(config.variant, "restart_smoke_v2.sbatch")
    source_files = (
        Path(__file__),
        Path(__file__).with_name(sbatch_path),
        ROOT / "cases/e1_rouaix_hpc/run_pilot.py",
        ROOT / "cases/e1_rouaix_hpc/collect_native_provenance.py",
        ROOT / "cases/e1_rouaix_hpc/prepare_case.py",
        ROOT / "cases/e1_rouaix_hpc/source-provenance.json",
        ROOT / "scripts/hpc_metrics.py",
        ROOT / "scripts/audit_iso_vof_ledger.py",
        ROOT / "scripts/continue_rouaix_case.py",
        ROOT / "scripts/audit_interface_wave_flux.py",
        ROOT / "cases/e1_rouaix_hpc_restart/audit_restart.py",
    )
    if config.variant in {
        "pressure-total-p0-zero",
        "pressure-total-pcgdic",
        "pressure-total-continuation",
        "pressure-pcgdic-continuation",
    }:
        source_files += (ROOT / "src/aerial_drop/i4f_native_face_reader.py",)
    for source in source_files:
        if source.is_file():
            target = source_dir / source.name
            shutil.copy2(source, target)
    source_hashes = {path.name: sha256_file(path) for path in sorted(source_dir.iterdir())}
    if parent_contract is not None:
        write_json(source_dir / "parent-contract.json", parent_contract)
        source_hashes["parent-contract.json"] = sha256_file(source_dir / "parent-contract.json")
    write_json(attempt / "source-capsule-index.json", {"sha256": source_hashes})
    write_json(attempt / "seed-verification-copy.json", seed_receipt)
    return case, manifest


def verify_endpoint(case: Path, time_s: float) -> dict[str, Any]:
    time_name = f"{time_s:.12f}"
    endpoint = case / "processors120" / time_name
    missing = [name for name in REQUIRED_CHECKPOINT_FIELDS if not (endpoint / name).is_file()]
    if missing:
        raise RestartError(f"collated endpoint {time_name} lacks required fields: {missing}")
    fields = {
        name: {"bytes": (endpoint / name).stat().st_size, "sha256": sha256_file(endpoint / name)}
        for name in REQUIRED_CHECKPOINT_FIELDS
    }
    validate_checkpoint_time(
        (endpoint / "uniform/time").read_text(encoding="ascii"), checkpoint_time_s=time_s
    )
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
    requested_start_time_s: float = PARENT_TIME_S,
    solver_log_sha256: str | None = None,
    max_speed_csv_sha256: str | None = None,
    stop_signal_request_utc: str | None = None,
    stop_signal_acknowledged_utc: str | None = None,
    stop_signal_job_id: str | None = None,
    stop_signal_job_step: str | None = None,
    stop_signal_task_count: int | None = None,
    stop_signal_request_solver_time_s: float | None = None,
    early_save_trigger_after_steps: int | None = None,
) -> dict[str, Any]:
    """Build the exact receipt consumed by the restart-ledger audit."""
    reached = actual_time_s is not None and math.isclose(
        actual_time_s, target_time_s, rel_tol=0.0, abs_tol=1e-10
    )
    u_guard = bool(stop_detail and stop_detail.startswith("operational stop: max|U|="))
    diagnostic_early_save = stop_detail == EARLY_SAVE_STOP_REASON
    requested = (u_guard or diagnostic_early_save) and "12" in stop_signals
    acknowledged = bool(requested and return_code == 0 and end_marker and endpoint_verified)
    if reached and return_code == 0 and end_marker and stop_detail is None and not pause_observed:
        state, stop_reason = "terminal", None
    elif (
        diagnostic_early_save
        and not reached
        and step_count >= 3
        and return_code == 0
        and end_marker
        and not pause_observed
        and acknowledged
        and stop_signal_request_utc
        and stop_signal_acknowledged_utc
        and stop_signal_job_id
        and stop_signal_job_step
        and stop_signal_task_count == EXPECTED_RANKS
        and early_save_trigger_after_steps == 3
        and stop_signal_request_solver_time_s is not None
    ):
        state, stop_reason = "diagnostic_early_saved", EARLY_SAVE_TERMINAL_REASON
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
        "requested_start_time_s": requested_start_time_s,
        "solver_time_steps_recorded": step_count,
        "stop_reason": stop_reason,
        "stop_detail": stop_detail,
        "pause_observed": pause_observed,
        "write_and_stop_requested": requested,
        "write_and_stop_acknowledged": acknowledged,
        "stop_signals": list(stop_signals),
        "stop_signal_request_utc": stop_signal_request_utc,
        "stop_signal_acknowledged_utc": stop_signal_acknowledged_utc,
        "stop_signal_job_id": stop_signal_job_id,
        "stop_signal_job_step": stop_signal_job_step,
        "stop_signal_task_count": stop_signal_task_count,
        "stop_signal_request_solver_time_s": stop_signal_request_solver_time_s,
        "early_save_trigger_after_steps": early_save_trigger_after_steps,
        "variant": variant,
        "solver_log_sha256": solver_log_sha256,
        "max_speed_csv_sha256": max_speed_csv_sha256,
    }


def _run_audit(
    case: Path,
    attempt: Path,
    config: RestartConfig,
    parent_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        parent_contract=parent_contract,
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


def run(
    run_root: Path,
    config: RestartConfig,
    parent_contract_path: Path | None = None,
) -> int:
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
        parent_contract = None
        if config.variant in {"pressure-total-continuation", "pressure-pcgdic-continuation"}:
            if (
                parent_contract_path is None
                or parent_contract_path.is_symlink()
                or not parent_contract_path.is_file()
            ):
                raise RestartError(
                    "pressure-total continuation requires its frozen parent contract"
                )
            parent_contract = json.loads(parent_contract_path.read_text(encoding="utf-8"))
            validate_parent_contract(parent_contract, expected_time_s=config.start_time_s)
            expected_parent_variant = (
                "pressure-total-p0-zero"
                if config.variant == "pressure-total-continuation"
                else "pressure-total-pcgdic"
            )
            if parent_contract["variant"] != expected_parent_variant:
                raise RestartError(
                    f"{config.variant} requires parent variant {expected_parent_variant}"
                )
            state.update(
                parent_archive_sha256=parent_contract["archive_sha256"],
                parent_ledger_sha256=parent_contract["ledger_sha256"],
                parent_checkpoint_time_s=parent_contract["checkpoint_time_s"],
                parent_checkpoint_inventory_m3=parent_contract["inventory_m3"],
                parent_job_id=parent_contract["parent_job_id"],
                parent_variant=parent_contract["variant"],
                parent_contract_sha256=sha256_file(parent_contract_path),
            )
            write_state()
        elif parent_contract_path is not None:
            raise RestartError("parent contracts are only accepted by pressure continuations")
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
        if parent_contract is None:
            case, manifest = prepare_case(attempt, config)
        else:
            case, manifest = prepare_case(attempt, config, parent_contract)
        state["seed_verification"] = json.loads((attempt / "seed-verification.json").read_text())
        state["manifest_sha256"] = sha256_file(attempt / "manifest.json")
        write_state()
        if config.variant in {"pressure-total-p0-zero", "pressure-total-pcgdic"}:
            state["status"] = "native_pressure_boundary_preparation"
            write_state()
            state["pressure_total_change_receipt"] = apply_pressure_total_restart(
                case,
                attempt,
                run_dir,
                run_root,
                solver_deadline,
                state,
                write_state,
            )
            if config.variant == "pressure-total-pcgdic":
                state["pressure_linear_solver_sensitivity"] = manifest[
                    "pressure_linear_solver_sensitivity"
                ]
            write_state()
        elif config.variant in {"pressure-total-continuation", "pressure-pcgdic-continuation"}:
            state["pressure_total_inherited"] = {
                "parent_archive_sha256": parent_contract["archive_sha256"],
                "parent_checkpoint_time_s": parent_contract["checkpoint_time_s"],
                "bc": "prghTotalPressure p0=0 on the same four open patches",
                "change_dictionary_applied": False,
            }
            if config.variant == "pressure-pcgdic-continuation":
                state["pressure_linear_solver_inherited"] = manifest[
                    "pressure_linear_solver_inherited"
                ]
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
        monitor_type = type(
            f"RestartOutputMonitor_{config.start_time_s:g}",
            (RestartOutputMonitor,),
            {"start_time_s": config.start_time_s},
        )
        pilot.OutputMonitor = monitor_type
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
                start_time_s=config.start_time_s,
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
                stop_after_steps=3 if config.variant == "original-early-save" else None,
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
                [time_s for time_s, _ in tracker.rows if time_s > config.start_time_s + 1e-12]
            ),
            solver_max_u_m_s=tracker.maximum_u_m_s,
            stop_reason=stop_reason,
            pause_observed=paused or PAUSE_FILE.exists() or (run_dir / "PAUSE").exists(),
        )
        if return_code == 0 and stop_reason is None and tracker.saw_end_marker:
            terminal_state = "terminal"
        elif (
            config.variant == "original-early-save"
            and stop_reason == EARLY_SAVE_STOP_REASON
            and return_code == 0
            and tracker.saw_end_marker
            and state.get("stop_signal_acknowledged_utc")
        ):
            terminal_state = "diagnostic_early_saved"
        elif stop_reason and stop_reason.startswith("operational stop: max|U|="):
            terminal_state = "guarded_partial"
        else:
            terminal_state = "incomplete"
        endpoint = None
        if (
            terminal_state in {"terminal", "guarded_partial", "diagnostic_early_saved"}
            and not state["pause_observed"]
        ):
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
            requested_start_time_s=config.start_time_s,
            solver_log_sha256=state.get("solver_log_sha256"),
            max_speed_csv_sha256=state.get("max_speed_csv_sha256"),
            stop_signal_request_utc=state.get("stop_requested_utc"),
            stop_signal_acknowledged_utc=state.get("stop_signal_acknowledged_utc"),
            stop_signal_job_id=state.get("job_id"),
            stop_signal_job_step=state.get("stop_signal_job_step"),
            stop_signal_task_count=state.get("stop_signal_task_count"),
            stop_signal_request_solver_time_s=state.get("stop_signal_request_solver_time_s"),
            early_save_trigger_after_steps=state.get("early_save_trigger_after_steps"),
        )
        terminal_state = terminal["state"]
        write_json(case / "terminal-status.json", terminal)
        state["terminal_status_sha256"] = sha256_file(case / "terminal-status.json")
        if (
            terminal_state in {"terminal", "guarded_partial", "diagnostic_early_saved"}
            and not state["pause_observed"]
        ):
            try:
                if parent_contract is None:
                    state["restart_ledger"] = _run_audit(case, attempt, config)
                else:
                    state["restart_ledger"] = _run_audit(case, attempt, config, parent_contract)
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
            terminal_state == "diagnostic_early_saved"
            and state.get("ledger_status") == "written_from_hash_bound_parent_checkpoint"
            and state.get("solver_convergence", {}).get("all_converged") is True
        ):
            state["status"] = "diagnostic_early_save_complete"
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
        if state.get("status") in {"solver_complete_exploratory", "diagnostic_early_save_complete"}
        and state.get("attempt_archive_status") == "verified_crc_hash_and_member_list"
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--variant", choices=tuple(VARIANT_SETTINGS), default="original-smoke")
    parser.add_argument("--parent-contract", type=Path)
    args = parser.parse_args()
    return run(args.run_root, config_for_variant(args.variant), args.parent_contract)


if __name__ == "__main__":
    raise SystemExit(main())
