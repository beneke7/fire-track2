#!/usr/bin/env python3
"""Dispatch one PCG/DIC continuation after its exact .255 s parent verifies cleanly."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import shutil
import signal
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROJECT_ROOT = Path("/project/nk_meshapplied/bene/fire-track2-hpc")
EXPERIMENT_ROOT = PROJECT_ROOT / "rouaix-pressure-pcgdic-continuation-20261028"
PARENT_JOB_ID = "14705632"
PARENT_RUN = (
    PROJECT_ROOT
    / "rouaix-pressure-pcgdic-restart-20261028"
    / "rouaix-restart-pressure-total-pcgdic-14705632"
)
SOURCE_ROOT = PROJECT_ROOT / "rouaix-pressure-pcgdic-continuation-source-20261028/unpacked"
AUDITOR = PROJECT_ROOT / "hpc-finished-audit-source-v3-20261026/scripts/hpc_finished_audit.py"
AUDITOR_SHA256 = "e49893ce488afe17a0e4536ae6b16f4dc830984fd1b8bd482d8b781fcbdd3989"
DISK_RESERVE_BYTES = 16 * 1024**3
MIN_INCREMENTAL_OUTPUT_BYTES = 8 * 1024**3
PARENT_SOURCE_INDEX = "results/summaries/rouaix_pressure_pcgdic_20261028/source-capsule-index.json"
PARENT_SOURCE_CAPSULE = "rouaix-pressure-pcgdic-source-20261028.tar.gz"
CONTINUATION_SOURCE_SUMMARY = (
    "results/summaries/rouaix_pressure_pcgdic_20261028/continuation-source"
)
CONTINUATION_SOURCE_CAPSULE = "rouaix-pressure-pcgdic-continuation-source-20261028.tar.gz"
SOURCE_HASH_OVERRIDES = {
    "cases/e1_rouaix_hpc_restart/run_restart.py": "892f8034f3ce798f130fa6cde29a4dda54f6762bda5d5c24e21da7b76d259845",
    "cases/e1_rouaix_hpc_restart/audit_restart.py": "b620f91848e5a773e08c0960afc6b75ff01c1a70a59b87dcf0b3f83972c88899",
    "tests/test_rouaix_hpc_restart.py": "74f3e31fd17267db2d153ab2577b7a5a9d44c48091ff92a12d9fbb7d91bbd774",
    "tests/test_rouaix_hpc_restart_audit.py": "f0d487a0591e8850382b8c34816608b4accf6ca7408b4bb39ea749876155cd09",
}
EXTRA_SOURCE_PATHS = (
    "cases/e1_rouaix_hpc_restart/dispatch_pressure_continue.py",
    "cases/e1_rouaix_hpc_restart/dispatch_pressure_continue.sbatch",
    "cases/e1_rouaix_hpc_restart/restart_pressure_pcgdic_continue.sbatch",
    "tests/test_rouaix_hpc_restart_dispatch.py",
    "experiments/E1_ROUAIX_PRESSURE_PCGDIC_CONTINUATION_20261028.md",
)


class DispatchError(RuntimeError):
    """A dispatcher precondition or Slurm receipt did not verify."""


@dataclass(frozen=True)
class DispatchConfig:
    parent_job_id: str = PARENT_JOB_ID
    parent_run: Path = PARENT_RUN
    shared_root: Path = EXPERIMENT_ROOT
    solver_root: Path = EXPERIMENT_ROOT / "solver-runs"
    seed_source_root: Path = SOURCE_ROOT
    auditor: Path = AUDITOR
    disk_reserve_bytes: int = DISK_RESERVE_BYTES


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_auditor(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or sha256_file(path) != AUDITOR_SHA256:
        raise DispatchError("frozen after-any auditor source hash differs")
    return AUDITOR_SHA256


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _safe_relative(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts or "." in path.parts:
        raise DispatchError(f"unsafe source member path: {raw!r}")
    return path


def freeze_seed_source(repo_root: Path, destination: Path) -> dict[str, Any]:
    """Freeze a continuation capsule from the immutable PCG/DIC parent source."""
    index_path = repo_root / PARENT_SOURCE_INDEX
    parent_index = json.loads(index_path.read_text(encoding="utf-8"))
    parent_capsule_path = index_path.parent / PARENT_SOURCE_CAPSULE
    parent_capsule_hash_path = parent_capsule_path.with_suffix(
        parent_capsule_path.suffix + ".sha256"
    )
    parent_capsule_sha256 = parent_capsule_hash_path.read_text(encoding="ascii").split()[0]
    if sha256_file(parent_capsule_path) != parent_capsule_sha256:
        raise DispatchError("frozen parent source capsule differs from its recorded SHA-256")
    declared_archive_sha = parent_index.get("archive_sha256", parent_index.get("capsule_sha256"))
    if declared_archive_sha is not None and declared_archive_sha != parent_capsule_sha256:
        raise DispatchError("continuation source index differs from its parent capsule SHA-256")
    expected_hashes = {str(item["path"]): str(item["sha256"]) for item in parent_index["files"]}
    with tarfile.open(parent_capsule_path, "r:gz") as tar:
        members = tar.getmembers()
        if {member.name for member in members} != set(expected_hashes) or any(
            not member.isfile() for member in members
        ):
            raise DispatchError("frozen parent capsule does not match its source index member set")
        for member in members:
            source = tar.extractfile(member)
            if (
                source is None
                or hashlib.sha256(source.read()).hexdigest() != expected_hashes[member.name]
            ):
                raise DispatchError(f"frozen parent capsule member hash differs: {member.name}")
    paths = {str(item["path"]) for item in parent_index["files"]}
    paths.update(EXTRA_SOURCE_PATHS)
    summary_dir = repo_root / CONTINUATION_SOURCE_SUMMARY
    if destination.exists() or summary_dir.exists():
        raise DispatchError(
            f"refusing to overwrite source preparation: {destination} or {summary_dir}"
        )
    unpacked = destination / "unpacked"
    unpacked.mkdir(parents=True)
    files: list[dict[str, Any]] = []
    for relative in sorted(paths):
        member = _safe_relative(relative)
        source = repo_root.joinpath(*member.parts)
        if source.is_symlink() or not source.is_file():
            raise DispatchError(f"source file is missing or not regular: {relative}")
        expected_sha = SOURCE_HASH_OVERRIDES.get(relative, expected_hashes.get(relative))
        if expected_sha is not None and sha256_file(source) != expected_sha:
            raise DispatchError(f"source differs from the reviewed continuation index: {relative}")
        target = unpacked.joinpath(*member.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files.append(
            {"path": relative, "bytes": target.stat().st_size, "sha256": sha256_file(target)}
        )
    index = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "parent_source_capsule_sha256": parent_capsule_sha256,
        "parent_source_index_sha256": sha256_file(index_path),
        "revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "dirty_files": subprocess.run(
            ["git", "status", "--short"], cwd=repo_root, capture_output=True, text=True, check=True
        ).stdout.splitlines(),
        "files": files,
    }
    index["dirty"] = bool(index["dirty_files"])
    write_json(unpacked / "dispatch-source-index.json", index)
    index_member = {
        "path": "dispatch-source-index.json",
        "bytes": (unpacked / "dispatch-source-index.json").stat().st_size,
        "sha256": sha256_file(unpacked / "dispatch-source-index.json"),
    }
    archive_files = [*files, index_member]
    checksum_lines = [f"{item['sha256']}  {item['path']}" for item in archive_files]
    (unpacked / "source-files.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="ascii"
    )
    archive = destination / CONTINUATION_SOURCE_CAPSULE
    with tarfile.open(archive, "w:gz") as tar:
        for item in files:
            tar.add(unpacked / item["path"], arcname=item["path"], recursive=False)
        tar.add(unpacked / "dispatch-source-index.json", arcname="dispatch-source-index.json")
    archive_sha256 = sha256_file(archive)
    archive_hash_path = archive.with_suffix(archive.suffix + ".sha256")
    archive_hash_path.write_text(f"{archive_sha256}  {archive.name}\n", encoding="ascii")
    index.update(
        archive=CONTINUATION_SOURCE_CAPSULE,
        archive_sha256=archive_sha256,
        file_count=len(archive_files),
        files=archive_files,
    )
    summary_dir.mkdir(parents=True)
    shutil.copy2(archive, summary_dir / archive.name)
    shutil.copy2(archive_hash_path, summary_dir / f"{archive.name}.sha256")
    write_json(summary_dir / "source-capsule-index.json", index)
    return {
        "directory": str(destination),
        "archive": str(archive),
        "archive_sha256": archive_sha256,
        "summary_directory": str(summary_dir),
        "file_count": len(archive_files),
        "files": files,
    }


def verify_seed_source(source_root: Path) -> dict[str, Any]:
    index_path = source_root / "dispatch-source-index.json"
    if index_path.is_symlink() or not index_path.is_file():
        raise DispatchError("dispatch seed lacks its frozen source index")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("schema_version") != 1 or not isinstance(index.get("files"), list):
        raise DispatchError("dispatch source index schema is invalid")
    seen: set[str] = set()
    for item in index["files"]:
        relative = str(item.get("path", ""))
        member = _safe_relative(relative)
        path = source_root.joinpath(*member.parts)
        if relative in seen or path.is_symlink() or not path.is_file():
            raise DispatchError(f"dispatch source is duplicate or missing: {relative}")
        seen.add(relative)
        if path.stat().st_size != item.get("bytes") or sha256_file(path) != item.get("sha256"):
            raise DispatchError(f"dispatch source hash differs: {relative}")
    return index


def check_pause(config: DispatchConfig) -> list[str]:
    pause_paths = (
        PROJECT_ROOT / "PAUSE",
        config.shared_root / "PAUSE",
        config.solver_root / "PAUSE",
    )
    present = [str(path) for path in pause_paths if path.exists()]
    if present:
        raise DispatchError(f"user PAUSE marker blocks continuation dispatch: {present}")
    return [str(path) for path in pause_paths]


def parent_archive_uncompressed_bytes(contract: dict[str, Any]) -> int:
    archive = Path(str(contract.get("archive_path", "")))
    if archive.is_symlink() or not archive.is_file():
        raise DispatchError("verified parent archive is missing before disk admission")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
    total = sum(member.size for member in members if member.isfile())
    if total <= 0:
        raise DispatchError("verified parent archive has no regular-file payload")
    return total


def check_admission(config: DispatchConfig, output_allowance_bytes: int) -> dict[str, Any]:
    pause_paths = check_pause(config)
    paths = (PROJECT_ROOT, config.shared_root, config.solver_root)
    disk = {str(path): shutil.disk_usage(path).free for path in paths if path.exists()}
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise DispatchError(f"shared run roots are missing: {missing}")
    required = config.disk_reserve_bytes + output_allowance_bytes
    if any(free < required for free in disk.values()):
        raise DispatchError(
            f"free disk is below reserve plus output allowance {required} bytes: {disk}"
        )
    return {
        "pause_paths_absent": pause_paths,
        "free_bytes": disk,
        "reserve_bytes": config.disk_reserve_bytes,
        "incremental_output_allowance_bytes": output_allowance_bytes,
        "required_free_bytes": required,
    }


def parse_scontrol(text: str) -> dict[str, str]:
    return dict(re.findall(r"(?:^|\s)([A-Za-z][A-Za-z0-9_/:]*)=([^\s]+)", text.strip()))


def _memory_bytes(value: str) -> int:
    match = re.fullmatch(r"(\d+)([KMGTP]?)", value.upper())
    if match is None:
        raise DispatchError(f"unrecognized Slurm memory readback: {value!r}")
    scale = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5}[match.group(2)]
    return int(match.group(1)) * 1024**scale


def validate_job_readback(
    text: str,
    *,
    job_id: str,
    owner: str,
    name: str,
    nodes: int,
    tasks: int,
    tasks_per_node: int | None,
    cpus: int,
    memory_bytes: int,
    wall_time: str,
    dependency: str,
    work_dir: Path,
    command: Path,
    comment: str,
    held: bool,
) -> dict[str, str]:
    fields = parse_scontrol(text)
    actual_owner = fields.get("UserId", "").split("(", 1)[0]
    expected = {
        "JobId": job_id,
        "JobName": name,
        "Account": "nk_meshapplied",
        "Partition": "cpu-short",
        "QOS": "normal",
        "NumTasks": str(tasks),
        "NumCPUs": str(cpus),
        "CPUs/Task": "1",
        "TimeLimit": wall_time,
        "Dependency": dependency,
        "WorkDir": str(work_dir),
        "Command": str(command),
        "Comment": comment,
        "Requeue": "0",
    }
    if actual_owner != owner:
        raise DispatchError(f"Slurm job owner differs: {actual_owner!r} != {owner!r}")
    node_range = fields.get("NumNodes", "").split("-", 1)
    if len(node_range) == 1:
        node_range *= 2
    if node_range != [str(nodes), str(nodes)]:
        raise DispatchError(f"Slurm node count differs: {fields.get('NumNodes')!r} != {nodes}")
    mismatches = {
        key: (fields.get(key), value) for key, value in expected.items() if fields.get(key) != value
    }
    dependency_value = re.sub(r"\((?:unfulfilled|fulfilled)\)", "", fields.get("Dependency", ""))
    if dependency_value == dependency:
        mismatches.pop("Dependency", None)
    if tasks_per_node is not None and fields.get("NtasksPerN:B:S:C") != f"{tasks_per_node}:0:*:1":
        mismatches["NtasksPerN:B:S:C"] = (
            fields.get("NtasksPerN:B:S:C"),
            f"{tasks_per_node}:0:*:1",
        )
    if tasks_per_node is not None and fields.get("MinCPUsNode") != str(tasks_per_node):
        mismatches["MinCPUsNode"] = (fields.get("MinCPUsNode"), str(tasks_per_node))
    try:
        if _memory_bytes(fields["MinMemoryNode"]) != memory_bytes:
            mismatches["MinMemoryNode"] = (fields.get("MinMemoryNode"), str(memory_bytes))
    except (KeyError, DispatchError):
        mismatches["MinMemoryNode"] = (fields.get("MinMemoryNode"), str(memory_bytes))
    if fields.get("JobState") != "PENDING":
        mismatches["JobState"] = (fields.get("JobState"), "PENDING")
    if held and fields.get("Reason") != "JobHeldUser":
        mismatches["Reason"] = (fields.get("Reason"), "JobHeldUser")
    if not held and fields.get("Reason") == "JobHeldUser":
        mismatches["Reason"] = (fields.get("Reason"), "released")
    if mismatches:
        raise DispatchError(f"Slurm job {job_id} readback mismatch: {mismatches}")
    return fields


def _run(argv: list[str], *, timeout_s: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout_s)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DispatchError(f"command could not be verified: {argv[0]}: {error}") from error


def _job_id(result: subprocess.CompletedProcess[str]) -> str:
    if result.returncode != 0:
        raise DispatchError(f"sbatch failed: {result.stderr.strip()}")
    job_id = result.stdout.strip().split(";", 1)[0]
    if not job_id.isdigit():
        raise DispatchError(f"sbatch returned a malformed job ID: {result.stdout!r}")
    return job_id


def _show_job(job_id: str) -> str:
    result = _run(["scontrol", "show", "job", "--oneliner", job_id])
    if result.returncode != 0:
        raise DispatchError(f"scontrol show job {job_id} failed: {result.stderr.strip()}")
    return result.stdout


def _submit_held(
    script: Path,
    dependency: str,
    *,
    comment: str,
    source_root: Path | None = None,
) -> tuple[str, list[str], bool]:
    argv = [
        "sbatch",
        "--parsable",
        "--hold",
        f"--dependency={dependency}",
        "--kill-on-invalid-dep=yes",
        f"--comment={comment}",
    ]
    if source_root is not None:
        argv.append(f"--export=ALL,ROUAIX_SOURCE_ROOT={source_root}")
    argv.append(str(script))
    try:
        result = _run(argv, timeout_s=120)
        return _job_id(result), argv, False
    except DispatchError as submit_error:
        matches = _find_jobs_by_comment(comment)
        if len(matches) == 1:
            return matches[0], argv, True
        if len(matches) > 1:
            cleanup_errors = []
            for job_id in matches:
                result = _run(["scancel", job_id])
                if result.returncode != 0:
                    cleanup_errors.append(f"{job_id}: {result.stderr.strip()}")
            raise DispatchError(
                f"ambiguous submission created {matches}; cancelled tagged jobs; "
                f"cleanup errors={cleanup_errors}"
            ) from submit_error
        raise DispatchError(
            f"submission result unknown for unique comment {comment}: {submit_error}"
        ) from submit_error


def _find_jobs_by_comment(comment: str) -> list[str]:
    result = _run(
        ["squeue", "--noheader", "--user", pwd.getpwuid(os.getuid()).pw_name, "--format=%i"]
    )
    if result.returncode != 0:
        raise DispatchError(
            f"squeue lookup for ambiguous submission failed: {result.stderr.strip()}"
        )
    matches = []
    for job_id in result.stdout.splitlines():
        job_id = job_id.strip()
        if not job_id.isdigit():
            continue
        fields = parse_scontrol(_show_job(job_id))
        if fields.get("Comment") == comment and fields.get("JobState") == "PENDING":
            matches.append(job_id)
    return matches


def _cancel_ours(job_ids: list[str], receipt: dict[str, Any], receipt_path: Path) -> None:
    for job_id in reversed(job_ids):
        try:
            result = _run(["scancel", job_id])
            action = {
                "utc": utc_now(),
                "action": "cancel_own_partial_job",
                "job_id": job_id,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except DispatchError as error:
            action = {
                "utc": utc_now(),
                "action": "cancel_own_partial_job",
                "job_id": job_id,
                "error": str(error),
            }
        receipt["actions"].append(action)
        write_json(receipt_path, receipt)


def _audit_script(
    manifest: Path, job_id: str, output: Path, shared_root: Path, auditor: Path
) -> Path:
    path = shared_root / f"audit-afterany-{job_id}.sbatch"
    path.write_text(
        "#!/bin/bash -l\n"
        "#SBATCH --account=nk_meshapplied\n#SBATCH --partition=cpu-short\n"
        "#SBATCH --qos=normal\n#SBATCH --job-name=ml-aud\n#SBATCH --nodes=1\n"
        "#SBATCH --ntasks=1\n#SBATCH --cpus-per-task=1\n#SBATCH --mem=1800M\n"
        "#SBATCH --time=00:10:00\n#SBATCH --no-requeue\n"
        f"#SBATCH --chdir={shared_root}\n"
        f"#SBATCH --output={shared_root}/audit-slurm-%j.out\n"
        "set -euo pipefail\nexport TZ=UTC PYTHONDONTWRITEBYTECODE=1\n"
        "export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1\n"
        "module load cray-python/3.11.7\n"
        f"exec python3 {auditor} --manifest {manifest} --job-id {job_id} --output {output}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def audit_manifest(child_id: str, solver_root: Path) -> dict[str, Any]:
    run_dir = solver_root / f"rouaix-restart-pressure-pcgdic-continuation-{child_id}"
    return {
        "schema_version": 1,
        "jobs": [
            {
                "case_id": "rouaix-restart-pressure-pcgdic-continuation-0300",
                "job_id": child_id,
                "run_dir": str(run_dir),
                "source_root": str(solver_root),
                "slurm_output_path": str(solver_root / f"slurm-{child_id}.out"),
                "expected_ranks": 120,
                "horizon_s": 0.3,
                "delta_t_s": 0.0001,
            }
        ],
    }


def _write_child_capsule(
    source_root: Path, index: dict[str, Any], contract: dict[str, Any], output: Path, unpacked: Path
) -> dict[str, Any]:
    if output.exists() or unpacked.exists():
        raise DispatchError("continuation source output already exists; refusing duplicate capsule")
    contract_path = output.parent / "parent-contract.json"
    write_json(contract_path, contract)
    names = [str(item["path"]) for item in index["files"]]
    names += ["dispatch-source-index.json", "parent-contract.json"]
    with tarfile.open(output, "w:gz") as tar:
        for name in names:
            path = contract_path if name == "parent-contract.json" else source_root / name
            if path.is_symlink() or not path.is_file():
                raise DispatchError(f"source capsule member is missing or not regular: {name}")
            tar.add(path, arcname=name, recursive=False)
    output_sha = sha256_file(output)
    expected = {str(item["path"]): str(item["sha256"]) for item in index["files"]}
    expected.update(
        {
            "dispatch-source-index.json": sha256_file(source_root / "dispatch-source-index.json"),
            "parent-contract.json": sha256_file(contract_path),
        }
    )
    unpacked.mkdir(parents=True)
    with tarfile.open(output, "r:gz") as tar:
        members = tar.getmembers()
        if {member.name for member in members} != set(expected) or any(
            not member.isfile() for member in members
        ):
            raise DispatchError("continuation source capsule member set is invalid")
        for member in members:
            relative = _safe_relative(member.name)
            source = tar.extractfile(member)
            if source is None:
                raise DispatchError(f"cannot read source capsule member: {member.name}")
            data = source.read()
            if hashlib.sha256(data).hexdigest() != expected[member.name]:
                raise DispatchError(f"source capsule hash differs: {member.name}")
            target = unpacked.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return {
        "path": str(output),
        "sha256": output_sha,
        "member_count": len(expected),
        "parent_contract_sha256": expected["parent-contract.json"],
    }


def dispatch(config: DispatchConfig) -> dict[str, Any]:
    dispatcher_id = os.environ.get("SLURM_JOB_ID", "")
    if not dispatcher_id.isdigit() or not config.parent_job_id.isdigit():
        raise DispatchError("dispatcher and parent job IDs must be numeric")
    claim_root = config.shared_root / "dispatch"
    claim_root.mkdir(parents=True, exist_ok=True)
    dispatch_dir = claim_root / f"parent-{config.parent_job_id}-dispatcher-{dispatcher_id}"
    dispatch_dir.mkdir()
    receipt_path = dispatch_dir / "dispatch-receipt.json"
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "created_utc": utc_now(),
        "status": "started",
        "parent_job_id": config.parent_job_id,
        "dispatcher_job_id": dispatcher_id,
        "actions": [],
    }
    write_json(receipt_path, receipt)
    created_jobs: list[str] = []
    try:
        check_pause(config)
        index = verify_seed_source(config.seed_source_root)
        receipt["source_index_sha256"] = sha256_file(
            config.seed_source_root / "dispatch-source-index.json"
        )
        receipt["auditor_sha256"] = verify_auditor(config.auditor)
        from cases.e1_rouaix_hpc_restart import run_restart

        contract = run_restart.verify_completed_parent(config.parent_run, config.parent_job_id)
        run_restart.validate_parent_contract(contract, expected_time_s=0.255)
        if (
            contract.get("variant") != "pressure-total-pcgdic"
            or contract.get("case_id") != "rouaix-restart-pressure-total-pcgdic-0255"
            or contract.get("parent_start_time_s") != 0.2
            or contract.get("parent_target_time_s") != 0.255
            or contract.get("checkpoint_time_dir") != "processors120/0.255000000000"
            or contract.get("step_count") != 550
        ):
            raise DispatchError("parent contract is not the exact PCG/DIC .255 s endpoint")
        allowance = max(
            MIN_INCREMENTAL_OUTPUT_BYTES,
            4 * parent_archive_uncompressed_bytes(contract),
        )
        receipt["admission"] = check_admission(config, allowance)
        receipt["parent_contract_sha256"] = hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        receipt["status"] = "preflight_verified"
        write_json(receipt_path, receipt)

        claim = claim_root / f"parent-{config.parent_job_id}.claim"
        try:
            descriptor = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o440)
        except FileExistsError as error:
            raise DispatchError(
                f"a dispatcher already claimed parent {config.parent_job_id}"
            ) from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"dispatcher_job_id={dispatcher_id}\n")
            stream.flush()
            os.fsync(stream.fileno())

        child_source_dir = dispatch_dir / "child-source"
        capsule = _write_child_capsule(
            config.seed_source_root,
            index,
            contract,
            child_source_dir / "pressure-pcgdic-continuation.tar.gz",
            child_source_dir / "unpacked",
        )
        receipt["child_source_capsule"] = capsule
        write_json(receipt_path, receipt)

        child_script = (
            child_source_dir
            / "unpacked/cases/e1_rouaix_hpc_restart/restart_pressure_pcgdic_continue.sbatch"
        )
        child_comment = f"rouaix-pcgdic-{dispatcher_id}-child"
        child_id, child_argv, child_recovered = _submit_held(
            child_script,
            f"afterany:{dispatcher_id}",
            comment=child_comment,
            source_root=child_source_dir / "unpacked",
        )
        created_jobs.append(child_id)
        receipt["child_job_id"] = child_id
        receipt["actions"].append(
            {
                "utc": utc_now(),
                "action": "submit_child_held",
                "argv": child_argv,
                "recovered_by_unique_comment": child_recovered,
            }
        )
        write_json(receipt_path, receipt)
        child_text = _show_job(child_id)
        validate_job_readback(
            child_text,
            job_id=child_id,
            owner=pwd.getpwuid(os.getuid()).pw_name,
            name="ml-vof",
            nodes=3,
            tasks=120,
            tasks_per_node=40,
            cpus=120,
            memory_bytes=22 * 1024**3,
            wall_time="02:00:00",
            dependency=f"afterany:{dispatcher_id}",
            work_dir=config.solver_root,
            command=child_script,
            comment=child_comment,
            held=True,
        )
        (dispatch_dir / "slurm-readback-held-child.txt").write_text(child_text, encoding="utf-8")

        manifest_path = dispatch_dir / "audit-manifest.json"
        write_json(manifest_path, audit_manifest(child_id, config.solver_root))
        audit_output = config.shared_root / "audit-reports" / child_id
        audit_script = _audit_script(
            manifest_path, child_id, audit_output, config.shared_root, config.auditor
        )
        audit_comment = f"rouaix-pcgdic-{dispatcher_id}-audit"
        audit_id, audit_argv, audit_recovered = _submit_held(
            audit_script, f"afterany:{child_id}", comment=audit_comment
        )
        created_jobs.append(audit_id)
        receipt["audit_job_id"] = audit_id
        receipt["actions"].append(
            {
                "utc": utc_now(),
                "action": "submit_audit_held",
                "argv": audit_argv,
                "recovered_by_unique_comment": audit_recovered,
            }
        )
        write_json(receipt_path, receipt)
        audit_text = _show_job(audit_id)
        validate_job_readback(
            audit_text,
            job_id=audit_id,
            owner=pwd.getpwuid(os.getuid()).pw_name,
            name="ml-aud",
            nodes=1,
            tasks=1,
            tasks_per_node=None,
            cpus=1,
            memory_bytes=1800 * 1024**2,
            wall_time="00:10:00",
            dependency=f"afterany:{child_id}",
            work_dir=config.shared_root,
            command=audit_script,
            comment=audit_comment,
            held=True,
        )
        (dispatch_dir / "slurm-readback-held-audit.txt").write_text(audit_text, encoding="utf-8")
        receipt["status"] = "both_jobs_held_and_verified"
        write_json(receipt_path, receipt)

        for job_id in (audit_id, child_id):
            result = _run(["scontrol", "release", job_id])
            receipt["actions"].append(
                {
                    "utc": utc_now(),
                    "action": "release",
                    "job_id": job_id,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            write_json(receipt_path, receipt)
            if result.returncode != 0:
                raise DispatchError(f"scontrol release {job_id} failed: {result.stderr.strip()}")
            released_text = _show_job(job_id)
            expected_dependency = f"afterany:{child_id if job_id == audit_id else dispatcher_id}"
            validate_job_readback(
                released_text,
                job_id=job_id,
                owner=pwd.getpwuid(os.getuid()).pw_name,
                name="ml-aud" if job_id == audit_id else "ml-vof",
                nodes=1 if job_id == audit_id else 3,
                tasks=1 if job_id == audit_id else 120,
                tasks_per_node=None if job_id == audit_id else 40,
                cpus=1 if job_id == audit_id else 120,
                memory_bytes=1800 * 1024**2 if job_id == audit_id else 22 * 1024**3,
                wall_time="00:10:00" if job_id == audit_id else "02:00:00",
                dependency=expected_dependency,
                work_dir=config.shared_root if job_id == audit_id else config.solver_root,
                command=audit_script if job_id == audit_id else child_script,
                comment=audit_comment if job_id == audit_id else child_comment,
                held=False,
            )
            (dispatch_dir / f"slurm-readback-released-{job_id}.txt").write_text(
                released_text, encoding="utf-8"
            )
        receipt["status"] = "released_audit_then_child_verified"
        receipt["completed_utc"] = utc_now()
        write_json(receipt_path, receipt)
        return receipt
    except Exception as error:
        receipt["status"] = "failed_preserved"
        receipt["error"] = f"{type(error).__name__}: {error}"
        write_json(receipt_path, receipt)
        if created_jobs:
            _cancel_ours(created_jobs, receipt, receipt_path)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--shared-root", type=Path, default=EXPERIMENT_ROOT)
    parser.add_argument("--solver-root", type=Path, default=EXPERIMENT_ROOT / "solver-runs")
    parser.add_argument("--parent-job-id", default=PARENT_JOB_ID)
    args = parser.parse_args()

    def stop_on_term(_signum: int, _frame: Any) -> None:
        raise DispatchError("dispatcher received scheduler termination signal")

    signal.signal(signal.SIGTERM, stop_on_term)
    try:
        dispatch(
            DispatchConfig(
                parent_job_id=args.parent_job_id,
                shared_root=args.shared_root,
                solver_root=args.solver_root,
                seed_source_root=args.source_root,
            )
        )
    except Exception as error:
        print(
            f"continuation dispatcher failed closed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
