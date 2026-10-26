#!/usr/bin/env python3
"""Validate a cluster resource plan and render Slurm scripts without submitting jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PROFILES = {"smoke", "scaling", "production"}
RUNTIME_STRATEGIES = {"site-wrapper", "native-mpi", "apptainer-hybrid", "apptainer-bind"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MEMORY_RE = re.compile(r"^[1-9][0-9]*[KMGTP]?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OMP_THREAD_LIMIT",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


@dataclass(frozen=True)
class JobPlan:
    name: str
    profile: str
    nodes: int
    tasks_per_node: int
    cpus_per_task: int
    ranks: int
    requested_cores: int
    walltime: str
    walltime_seconds: int
    signal_before_walltime_seconds: int
    memory_per_node: str
    partition: str
    account: str | None


def parse_walltime(value: str) -> int:
    """Convert Slurm HH:MM:SS or D-HH:MM:SS to seconds."""
    if not isinstance(value, str) or not value:
        raise ValueError("walltime must be HH:MM:SS or D-HH:MM:SS")
    if "-" in value:
        day_text, clock = value.split("-", 1)
        if not day_text.isdigit():
            raise ValueError(f"invalid walltime day field: {value!r}")
        days = int(day_text)
    else:
        days, clock = 0, value
    pieces = clock.split(":")
    if len(pieces) != 3 or not all(piece.isdigit() for piece in pieces):
        raise ValueError(f"invalid walltime: {value!r}")
    hours, minutes, seconds = map(int, pieces)
    if minutes >= 60 or seconds >= 60 or (days and hours >= 24):
        raise ValueError(f"invalid walltime range: {value!r}")
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError("walltime must be positive")
    return total


def _required_text(record: dict[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{context}.{key} must be a single line")
    return value.strip()


def _positive_int(record: dict[str, Any], key: str, context: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{context}.{key} must be a positive integer")
    return value


def validate_config(config: Any) -> tuple[dict[str, Any], list[JobPlan]]:
    """Validate site-supplied resources and return normalized plans."""
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")

    allocation = config.get("allocation")
    if not isinstance(allocation, dict):
        raise ValueError("allocation must be an object")
    allocation_cores = _positive_int(allocation, "cores", "allocation")
    budget_min = _positive_int(allocation, "cpu_hours_budget_min", "allocation")
    budget_max = _positive_int(allocation, "cpu_hours_budget_max", "allocation")
    if budget_min > budget_max:
        raise ValueError("allocation CPU-hour budget minimum exceeds maximum")

    solver = config.get("solver")
    if not isinstance(solver, dict):
        raise ValueError("solver must be an object")
    for key in ("name", "openfoam_version"):
        _required_text(solver, key, "solver")
    for key in ("binary_sha256", "source_manifest_sha256"):
        value = _required_text(solver, key, "solver").lower()
        if not SHA256_RE.fullmatch(value):
            raise ValueError(f"solver.{key} must be a 64-character SHA-256 hex digest")
    custom_components = solver.get("custom_components")
    if (
        not isinstance(custom_components, list)
        or not custom_components
        or any(not isinstance(item, str) or not item.strip() for item in custom_components)
    ):
        raise ValueError("solver.custom_components must be a non-empty list of names")
    strategy = _required_text(solver, "runtime_strategy", "solver")
    if strategy not in RUNTIME_STRATEGIES:
        raise ValueError(f"solver.runtime_strategy must be one of {sorted(RUNTIME_STRATEGIES)}")

    jobs_value = config.get("jobs")
    if not isinstance(jobs_value, list) or not jobs_value:
        raise ValueError("jobs must be a non-empty list")
    jobs: list[JobPlan] = []
    names: set[str] = set()
    total_core_hours = 0.0
    for index, record in enumerate(jobs_value):
        context = f"jobs[{index}]"
        if not isinstance(record, dict):
            raise ValueError(f"{context} must be an object")
        name = _required_text(record, "name", context)
        if not NAME_RE.fullmatch(name):
            raise ValueError(f"{context}.name contains unsupported Slurm job-name characters")
        if name in names:
            raise ValueError(f"duplicate job name {name!r}")
        names.add(name)
        profile = _required_text(record, "profile", context)
        if profile not in PROFILES:
            raise ValueError(f"{context}.profile must be one of {sorted(PROFILES)}")

        nodes = _positive_int(record, "nodes", context)
        tasks_per_node = _positive_int(record, "tasks_per_node", context)
        cpus_per_task = record.get("cpus_per_task")
        if cpus_per_task != 1 or isinstance(cpus_per_task, bool):
            raise ValueError(f"{context}.cpus_per_task must be 1 for the MPI-only thread policy")
        ranks = nodes * tasks_per_node
        requested_cores = ranks * cpus_per_task
        if requested_cores > allocation_cores:
            raise ValueError(
                f"{context} requests {requested_cores} CPU cores, above allocation limit "
                f"{allocation_cores}"
            )

        walltime = _required_text(record, "walltime", context)
        walltime_seconds = parse_walltime(walltime)
        signal_before_walltime = _positive_int(record, "signal_before_walltime_seconds", context)
        if signal_before_walltime >= walltime_seconds:
            raise ValueError(f"{context}.signal_before_walltime_seconds must be below the walltime")
        memory = _required_text(record, "memory_per_node", context)
        if not MEMORY_RE.fullmatch(memory):
            raise ValueError(
                f"{context}.memory_per_node must be a positive Slurm size such as 256G"
            )
        partition = _required_text(record, "partition", context)
        if not NAME_RE.fullmatch(partition):
            raise ValueError(f"{context}.partition contains unsupported Slurm characters")
        account_value = record.get("account")
        account: str | None = None
        if account_value is not None:
            if not isinstance(account_value, str) or not NAME_RE.fullmatch(account_value):
                raise ValueError(f"{context}.account must be null or a simple Slurm account name")
            account = account_value

        total_core_hours += requested_cores * walltime_seconds / 3600
        jobs.append(
            JobPlan(
                name=name,
                profile=profile,
                nodes=nodes,
                tasks_per_node=tasks_per_node,
                cpus_per_task=cpus_per_task,
                ranks=ranks,
                requested_cores=requested_cores,
                walltime=walltime,
                walltime_seconds=walltime_seconds,
                signal_before_walltime_seconds=signal_before_walltime,
                memory_per_node=memory,
                partition=partition,
                account=account,
            )
        )
    if total_core_hours > budget_min:
        raise ValueError(
            f"maximum requested job CPU-hours {total_core_hours:.1f} exceeds conservative "
            f"configured planning cap {budget_min}"
        )
    return config, jobs


def render_job(config: dict[str, Any], job: JobPlan) -> str:
    solver = config["solver"]
    lines = [
        "#!/usr/bin/env bash",
        "# Generated by slurm_scaffold.py; rendering does not submit this job.",
        f"#SBATCH --job-name={job.name}",
        f"#SBATCH --nodes={job.nodes}",
        f"#SBATCH --ntasks={job.ranks}",
        f"#SBATCH --ntasks-per-node={job.tasks_per_node}",
        f"#SBATCH --cpus-per-task={job.cpus_per_task}",
        f"#SBATCH --time={job.walltime}",
        f"#SBATCH --signal=B:USR1@{job.signal_before_walltime_seconds}",
        f"#SBATCH --mem={job.memory_per_node}",
        f"#SBATCH --partition={job.partition}",
    ]
    if job.account is not None:
        lines.append(f"#SBATCH --account={job.account}")
    lines.extend(["#SBATCH --output=%x-%j.out", "", "set -euo pipefail", "umask 077", ""])
    for name in THREAD_ENV:
        lines.append(f"export {name}=1")
    lines.extend(
        [
            "export OMP_DYNAMIC=FALSE",
            f"export FIRETRACK2_PROFILE={shlex.quote(job.profile)}",
            f"export FIRETRACK2_SOLVER_NAME={shlex.quote(solver['name'])}",
            f"export FIRETRACK2_OPENFOAM_VERSION={shlex.quote(solver['openfoam_version'])}",
            f"export FIRETRACK2_EXPECTED_BINARY_SHA256={shlex.quote(solver['binary_sha256'].lower())}",
            "export FIRETRACK2_EXPECTED_SOURCE_MANIFEST_SHA256="
            f"{shlex.quote(solver['source_manifest_sha256'].lower())}",
            f"export FIRETRACK2_RUNTIME_STRATEGY={shlex.quote(solver['runtime_strategy'])}",
            f"export FIRETRACK2_EXPECTED_TASKS={job.ranks}",
            "",
            ': "$SLURM_JOB_ID"',
            ': "$SLURM_NTASKS"',
            ': "$SLURM_CPUS_PER_TASK"',
            ': "$FIRETRACK2_CASE"',
            ': "$FIRETRACK2_CLUSTER_WRAPPER"',
            '[[ -d "$FIRETRACK2_CASE" ]] || { echo "FIRETRACK2_CASE is not a directory" >&2; exit 2; }',
            '[[ -x "$FIRETRACK2_CLUSTER_WRAPPER" ]] || { echo "cluster wrapper is not executable" >&2; exit 2; }',
            '[[ "$SLURM_NTASKS" -eq "$FIRETRACK2_EXPECTED_TASKS" ]] || { echo "Slurm rank count differs from rendered plan" >&2; exit 2; }',
            '[[ "$SLURM_CPUS_PER_TASK" -eq 1 ]] || { echo "MPI jobs require one CPU per task" >&2; exit 2; }',
            "",
            'printf "job_id=%s profile=%s ranks=%s case=%s\\n" '
            '"$SLURM_JOB_ID" "$FIRETRACK2_PROFILE" "$SLURM_NTASKS" "$FIRETRACK2_CASE"',
            'exec "$FIRETRACK2_CLUSTER_WRAPPER" '
            '--profile "$FIRETRACK2_PROFILE" '
            '--case "$FIRETRACK2_CASE" '
            '--ranks "$SLURM_NTASKS" '
            '--cpus-per-task "$SLURM_CPUS_PER_TASK" '
            '--job-id "$SLURM_JOB_ID" '
            '--solver-name "$FIRETRACK2_SOLVER_NAME" '
            '--openfoam-version "$FIRETRACK2_OPENFOAM_VERSION" '
            '--expected-binary-sha256 "$FIRETRACK2_EXPECTED_BINARY_SHA256" '
            '--expected-source-manifest-sha256 "$FIRETRACK2_EXPECTED_SOURCE_MANIFEST_SHA256" '
            '--runtime-strategy "$FIRETRACK2_RUNTIME_STRATEGY"',
            "",
        ]
    )
    return "\n".join(lines)


def config_summary(config: dict[str, Any], jobs: list[JobPlan]) -> dict[str, Any]:
    requested_core_hours = sum(job.requested_cores * job.walltime_seconds / 3600 for job in jobs)
    return {
        "schema_version": SCHEMA_VERSION,
        "submission_performed": False,
        "allocation_cores": config["allocation"]["cores"],
        "cpu_hours_budget_min": config["allocation"]["cpu_hours_budget_min"],
        "cpu_hours_budget_max": config["allocation"]["cpu_hours_budget_max"],
        "conservative_cpu_hours_guard": config["allocation"]["cpu_hours_budget_min"],
        "requested_max_cpu_hours": round(requested_core_hours, 3),
        "solver": config["solver"],
        "jobs": [asdict(job) for job in jobs],
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON config {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("config root must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate_parser = commands.add_parser(
        "validate", help="validate and report allocation arithmetic"
    )
    validate_parser.add_argument("--config", type=Path, required=True)
    render_parser = commands.add_parser("render", help="render scripts only; never submit them")
    render_parser.add_argument("--config", type=Path, required=True)
    render_parser.add_argument("--output-dir", type=Path, required=True)
    render_parser.add_argument(
        "--dry-run",
        action="store_true",
        required=True,
        help="required acknowledgement: this command only writes reviewable scripts",
    )
    args = parser.parse_args(argv)

    try:
        config, jobs = validate_config(_load_json(args.config))
        summary = config_summary(config, jobs)
        if args.command == "validate":
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0

        output_dir: Path = args.output_dir
        if output_dir.exists():
            raise ValueError(f"refusing to overwrite existing output directory: {output_dir}")
        output_dir.mkdir(parents=True)
        script_manifest: list[dict[str, str]] = []
        for job in jobs:
            content = render_job(config, job)
            target = output_dir / f"{job.name}.sbatch"
            target.write_text(content, encoding="utf-8", newline="\n")
            target.chmod(0o644)
            script_manifest.append(
                {
                    "path": target.name,
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                }
            )
        summary["generated_scripts"] = script_manifest
        summary_path = output_dir / "scaffold-manifest.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "rendered": [item["path"] for item in script_manifest],
                    "manifest": summary_path.as_posix(),
                    "submission_performed": False,
                },
                indent=2,
            )
        )
        return 0
    except (OSError, ValueError) as error:
        print(f"slurm_scaffold: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
