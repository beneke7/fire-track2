#!/usr/bin/env python3
"""Create a compact, read-only audit after one explicitly listed Slurm job ends.

Run from a bounded Slurm ``afterany`` job:

    python3 hpc_finished_audit.py --manifest jobs.json --job-id 14651185 --output AUDITROOT/14651185

The manifest contains ``jobs`` with ``job_id``, ``source_root``, optional
``run_dir`` and ``slurm_output_path``, plus expected ``case_id``, ``expected_ranks``,
``horizon_s`` and ``delta_t_s``. The auditor reads the parent run and local
Slurm accounting only. It never changes the run or submits/cancels a job.
"""

from __future__ import annotations

import csv
import fcntl
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import hpc_metrics  # noqa: E402

HOST_ROOTS = (
    "/project/nk_meshapplied/bene/fire-track2-hpc",
    "/scratch/nk_meshapplied/bene/fire-track2-hpc",
)
JOB_ID_RE = re.compile(r"^\d+$")
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TERMINAL_STATES = {
    "COMPLETED",
    "FAILED",
    "TIMEOUT",
    "OOM",
    "OUT_OF_MEMORY",
    "NODE_FAIL",
    "PREEMPTED",
    "BOOT_FAIL",
    "DEADLINE",
}
MAX_FILE_BYTES = 512 * 1024**2
MAX_SELECTED_BYTES = 1024**3
MAX_SELECTED_FILES = 64
MAX_ARCHIVE_MEMBERS = 100_000
MAX_CAPTURE_ATTEMPTS = 3
SACCT_TIMEOUT_S = 45
NATIVE_PROFILING_RE = re.compile(
    r"^attempt/case/(?:processors\d+/\d+(?:\.\d+)?/uniform|"
    r"postProcessing/profiling/\d+(?:\.\d+)?)/profiling(?:\.gz)?$"
)
EXACT_MEMBERS = {
    "attempt/solver.log",
    "attempt/solver-convergence.json",
    "attempt/manifest.json",
    "attempt/native-source-evidence.json",
    "attempt/max-speed.csv",
    "attempt/case/case-inputs.json",
    "attempt/case/system/controlDict",
    "attempt/case/system/fvSolution",
    "attempt/case/system/fvSchemes",
    "attempt/ledger/summary.json",
    "attempt/ledger/ledger.csv",
    "attempt/ledger-audit.log",
    "attempt/slurm-step-accounting.txt",
    "attempt/rank0-affinity.txt",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    jobs = raw.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("manifest jobs must be a nonempty list")
    seen: set[str] = set()
    checked: list[dict[str, Any]] = []
    for source in jobs:
        if not isinstance(source, dict):
            raise ValueError("each manifest job must be an object")
        job = dict(source)
        job_id = str(job.get("job_id", ""))
        if not JOB_ID_RE.fullmatch(job_id) or job_id in seen:
            raise ValueError("job IDs must be unique decimal strings")
        seen.add(job_id)
        source_root = job.get("source_root")
        if not isinstance(source_root, str) or not any(
            source_root == root or source_root.startswith(root + "/") for root in HOST_ROOTS
        ):
            raise ValueError(f"source_root must be below an approved project root: {source_root!r}")
        if not SAFE_PATH_RE.fullmatch(source_root) or ".." in PurePosixPath(source_root).parts:
            raise ValueError("source_root contains unsafe path characters")
        run_dir = job.get("run_dir", f"rouaix-e1-hpc-pilot-{job_id}")
        if not isinstance(run_dir, str) or not SAFE_PATH_RE.fullmatch(run_dir):
            raise ValueError("run_dir contains unsafe path characters")
        if ".." in PurePosixPath(run_dir).parts:
            raise ValueError("run_dir may not traverse parent directories")
        if not run_dir.startswith("/"):
            if "/" in run_dir:
                raise ValueError("relative run_dir must be one child of source_root")
            run_dir = f"{source_root}/{run_dir}"
        if not run_dir.startswith(source_root + "/"):
            raise ValueError("absolute run_dir must remain below source_root")
        job["job_id"] = job_id
        job["run_dir"] = run_dir
        for key in ("expected_ranks", "horizon_s", "delta_t_s", "case_id"):
            if key not in job:
                raise ValueError(f"job {job_id} is missing {key}")
        if (
            isinstance(job["expected_ranks"], bool)
            or not isinstance(job["expected_ranks"], int)
            or job["expected_ranks"] <= 0
        ):
            raise ValueError(f"job {job_id} expected_ranks must be a positive integer")
        for key in ("horizon_s", "delta_t_s"):
            value = job[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"job {job_id} {key} must be a finite positive number")
        if not isinstance(job["case_id"], str) or not job["case_id"]:
            raise ValueError(f"job {job_id} case_id must be nonempty")
        if "slurm_output_path" in job:
            path = job["slurm_output_path"]
            if not isinstance(path, str):
                raise ValueError("slurm_output_path must be a string")
            path = path.replace("{job_id}", job_id)
            if (
                not SAFE_PATH_RE.fullmatch(path)
                or ".." in PurePosixPath(path).parts
                or not any(path.startswith(root + "/") for root in HOST_ROOTS)
            ):
                raise ValueError("slurm_output_path must stay under an approved project root")
            job["slurm_output_path"] = path
        checked.append(job)
    raw["jobs"] = checked
    return raw


def is_terminal_state(state: str) -> bool:
    token = state.strip().split(maxsplit=1)[0].rstrip("+").upper() if state.strip() else ""
    return token.startswith("CANCELLED") or token in TERMINAL_STATES


def classify_result(
    slurm_state: str,
    solver_status: str,
    solver_exit_code: Any,
    horizon_reached: bool,
    convergence_ok: bool,
    inputs_match: bool,
) -> str:
    if not inputs_match:
        return "captured_attempt_inputs_differ_from_manifest"
    if slurm_state != "COMPLETED":
        return "slurm_" + re.sub(r"[^a-z0-9]+", "_", slurm_state.lower()).strip("_")
    if solver_status == "diverged":
        return "solver_diverged"
    if solver_status != "completed" or solver_exit_code != 0:
        return "solver_failed_or_missing_end_marker"
    if not horizon_reached:
        return "completed_but_requested_horizon_not_reached"
    if not convergence_ok:
        return "completed_horizon_but_convergence_not_verified"
    return "completed_horizon_converged_exploratory_only"


def parse_sacct(text: str, job_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {"steps": []}
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.rstrip("|").split("|")
        if len(fields) < 7:
            raise ValueError(f"malformed sacct row: {line[:240]}")
        row_id, state, exit_code, elapsed, total_cpu, allocated, max_rss = fields[:7]
        if row_id == job_id:
            result["parent"] = {
                "job_id": row_id,
                "state": state,
                "exit_code": exit_code,
                "elapsed_raw": elapsed,
                "total_cpu": total_cpu,
                "allocated_cpus": allocated,
                "max_rss": max_rss,
            }
        elif row_id.split(".", 1)[0] == job_id:
            result["steps"].append(
                {
                    "job_id": row_id,
                    "state": state,
                    "exit_code": exit_code,
                    "elapsed_raw": elapsed,
                    "total_cpu": total_cpu,
                    "allocated_cpus": allocated,
                    "max_rss": max_rss,
                }
            )
    return result


def local_sacct(job_id: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "sacct",
            f"--jobs={job_id}",
            "--parsable2",
            "--noheader",
            "--format=JobIDRaw,State,ExitCode,ElapsedRaw,TotalCPU,AllocCPUS,MaxRSS",
        ],
        capture_output=True,
        text=True,
        timeout=SACCT_TIMEOUT_S,
        env=dict(os.environ, TZ="UTC"),
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"sacct exit {result.returncode}: {result.stderr[-1000:]}")
    return parse_sacct(result.stdout, job_id)


def safe_member_name(name: str) -> str:
    raw = name.rstrip("/")
    if (
        not raw
        or raw.startswith("/")
        or "\\" in raw
        or any(part in {"", ".", ".."} for part in raw.split("/"))
    ):
        raise ValueError(f"unsafe archive path: {name!r}")
    return PurePosixPath(raw).as_posix()


def is_selected(name: str) -> bool:
    if name in EXACT_MEMBERS:
        return True
    if NATIVE_PROFILING_RE.fullmatch(name):
        return True
    return bool(
        re.search(
            r"(?:^|/)(?:raw[-_]?profil(?:e|ing)|profile[-_]?container|container[-_]?profile)(?:/|[-_.])",
            name,
            re.I,
        )
    )


def compact_archive(
    archive_path: Path, archive_hash: str, sidecar: str | None, output: Path
) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(archive_hash):
        raise ValueError("run-state result archive SHA-256 is missing or invalid")
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError("result archive is not a regular file")
    if sha256_file(archive_path) != archive_hash:
        raise ValueError("result archive SHA-256 differs from run-state")
    if sidecar is not None:
        match = re.fullmatch(r"([0-9a-f]{64})\s+result\.tar\.gz", sidecar.strip())
        if not match or match.group(1) != archive_hash:
            raise ValueError("result archive sidecar differs from run-state/archive")

    chosen: list[tarfile.TarInfo] = []
    seen: set[str] = set()
    total = 0
    with tarfile.open(archive_path, "r:gz") as source:
        members = source.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError("archive member count exceeds 100000")
        for member in members:
            name = safe_member_name(member.name)
            if name in seen:
                raise ValueError(f"duplicate archive member: {name}")
            seen.add(name)
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"archive contains a link or special member: {name}")
            if not member.isfile() or not is_selected(name):
                continue
            if member.size > MAX_FILE_BYTES:
                raise ValueError(f"selected file exceeds 512 MiB: {name}")
            total += member.size
            if total > MAX_SELECTED_BYTES:
                raise ValueError("selected payload exceeds 1 GiB")
            chosen.append(member)
            if len(chosen) > MAX_SELECTED_FILES:
                raise ValueError("selected file count exceeds 64")

        selected_files: list[dict[str, Any]] = []
        with tarfile.open(output / "compact.tar.gz", "w:gz", compresslevel=1) as compact:
            for member in chosen:
                source_file = source.extractfile(member)
                if source_file is None:
                    raise ValueError(f"cannot read selected member: {member.name}")
                digest = hashlib.sha256()

                class HashingReader:
                    count = 0

                    def read(self, size: int = -1) -> bytes:
                        block = source_file.read(size)
                        digest.update(block)
                        self.count += len(block)
                        return block

                reader = HashingReader()
                compact.addfile(member, reader)
                if reader.count != member.size:
                    raise ValueError(f"short read in selected member: {member.name}")
                selected_files.append(
                    {"path": member.name, "bytes": member.size, "sha256": digest.hexdigest()}
                )

    selection = {
        "schema_version": 1,
        "archive_sha256": archive_hash,
        "selected_bytes": total,
        "selected_files": selected_files,
    }
    atomic_json(output / "selection.json", selection)
    compact_hash = sha256_file(output / "compact.tar.gz")
    (output / "compact.tar.gz.sha256").write_text(
        f"{compact_hash}  compact.tar.gz\n", encoding="ascii"
    )
    return selection


def verify_compact(path: Path, selection: dict[str, Any], archive_hash: str) -> None:
    entries = selection.get("selected_files")
    if selection.get("archive_sha256") != archive_hash or not isinstance(entries, list):
        raise ValueError("selection receipt does not match run-state archive SHA-256")
    if (
        len(entries) > MAX_SELECTED_FILES
        or selection.get("selected_bytes", MAX_SELECTED_BYTES + 1) > MAX_SELECTED_BYTES
    ):
        raise ValueError("selection receipt exceeds capture limits")
    expected = {item["path"]: item for item in entries}
    if len(expected) != len(entries):
        raise ValueError("selection receipt contains duplicate paths")
    actual: dict[str, dict[str, Any]] = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            name = safe_member_name(member.name)
            if not member.isfile() or member.size > MAX_FILE_BYTES:
                raise ValueError(f"invalid compact member: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"cannot read compact member: {name}")
            digest = hashlib.sha256()
            size = 0
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
            actual[name] = {"path": name, "bytes": size, "sha256": digest.hexdigest()}
    if actual != expected:
        raise ValueError("compact archive member hashes differ from selection receipt")
    if sum(row["bytes"] for row in actual.values()) > MAX_SELECTED_BYTES:
        raise ValueError("compact archive exceeds 1 GiB selected payload limit")


def read_state(job_id: str, run_dir: Path) -> tuple[dict[str, Any] | None, str | None, Path]:
    state_path = run_dir / "run-state.json"
    archive = run_dir / "result.tar.gz"
    sidecar_path = run_dir / "result.tar.gz.sha256"
    if state_path.is_symlink() or not state_path.is_file():
        return None, None, archive
    if state_path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("run-state exceeds 5 MiB")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or str(state.get("job_id", "")) != job_id:
        raise ValueError("run-state job ID differs from requested parent job")
    sidecar = None
    if sidecar_path.exists() or sidecar_path.is_symlink():
        if (
            sidecar_path.is_symlink()
            or not sidecar_path.is_file()
            or sidecar_path.stat().st_size > 4096
        ):
            raise ValueError("result archive sidecar is not a small regular file")
        sidecar = sidecar_path.read_text(encoding="ascii").strip()
    if state.get("result_archive") not in {None, str(archive)}:
        raise ValueError("run-state result archive path differs from expected job directory")
    return state, sidecar, archive


def bootstrap_diagnostics(job: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
    paths = [run_dir / name for name in ("bootstrap.log", "allocation.txt", "module-load.log")]
    if job.get("slurm_output_path"):
        paths.append(Path(job["slurm_output_path"]))
    diagnostics = []
    for path in paths:
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 5 * 1024 * 1024:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        diagnostics.append(
            {
                "path": str(path),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "tail": data.decode("utf-8", errors="replace").splitlines()[-80:],
            }
        )
    return diagnostics


def load_pilot() -> Any:
    path = ROOT / "cases/e1_rouaix_hpc/run_pilot.py"
    spec = importlib.util.spec_from_file_location("finished_audit_pilot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load existing Rouaix solver-convergence parser")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PILOT = load_pilot()


def parse_u_peak(path: Path | None) -> dict[str, float | None]:
    if path is None:
        return {"max_m_s": None, "last_m_s": None}
    values = []
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "max_magnitude_U_m_s" not in reader.fieldnames:
            return {"max_m_s": None, "last_m_s": None}
        for row in reader:
            try:
                value = float(row["max_magnitude_U_m_s"])
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.append(value)
    return {"max_m_s": max(values) if values else None, "last_m_s": values[-1] if values else None}


def diagnostic_gaps(
    files: dict[str, Path], ledger: dict[str, Any], sacct: dict[str, Any]
) -> dict[str, Any]:
    profiles = sorted(name for name in files if "profil" in name.casefold())
    summary_present = "attempt/ledger/summary.json" in files
    audit_log_present = "attempt/ledger-audit.log" in files
    parent = sacct.get("parent", {})
    step_memory = [
        {"job_id": row.get("job_id"), "max_rss": row.get("max_rss")}
        for row in sacct.get("steps", [])
        if row.get("max_rss")
    ]
    return {
        "ledger": {
            "status": "raw_summary_captured" if summary_present else "missing",
            "summary_present": summary_present,
            "audit_log_present": audit_log_present,
            "formal_validation_decision": ledger.get("formal_validation_decision")
            if summary_present and isinstance(ledger, dict)
            else None,
        },
        "aggregate_memory": {
            "status": "not_aggregated",
            "parent_max_rss": parent.get("max_rss"),
            "step_max_rss_rows": step_memory,
            "note": "Parent and step MaxRSS values are shown separately; no aggregate memory value is inferred.",
        },
        "tke_extrema": {
            "status": "not_exposed_by_current_parser",
            "value": None,
            "note": "k/epsilon residuals do not provide TKE extrema.",
        },
        "native_profiling_interpretation": {
            "status": "raw_artifacts_uninterpreted" if profiles else "not_captured",
            "raw_files": profiles,
            "interpretation_performed": False,
        },
    }


def summarize(
    job: dict[str, Any], files: dict[str, Path], state: dict[str, Any], sacct: dict[str, Any]
) -> dict[str, Any]:
    ledger = (
        json.loads(files["attempt/ledger/summary.json"].read_text(encoding="utf-8"))
        if "attempt/ledger/summary.json" in files
        else {}
    )
    gaps = diagnostic_gaps(files, ledger, sacct)
    log = files.get("attempt/solver.log")
    if log is None:
        return {
            "analysis_status": "partial_no_solver_log",
            "classification": "terminal_attempt_without_solver_log",
            "diagnostic_gaps": gaps,
        }
    sacct_text = io.StringIO()
    writer = csv.writer(sacct_text, delimiter="|")
    writer.writerow(
        ["JobIDRaw", "State", "ExitCode", "ElapsedRaw", "TotalCPU", "AllocCPUS", "MaxRSS"]
    )
    parent = sacct.get("parent", {})
    writer.writerow(
        [
            parent.get(key, "")
            for key in (
                "job_id",
                "state",
                "exit_code",
                "elapsed_raw",
                "total_cpu",
                "allocated_cpus",
                "max_rss",
            )
        ]
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as stream:
        stream.write(sacct_text.getvalue())
        sacct_path = Path(stream.name)
    try:
        parsed = hpc_metrics.summarize_run(job["case_id"], log, job["expected_ranks"], sacct_path)
    finally:
        sacct_path.unlink(missing_ok=True)

    fv_solution = files.get("attempt/case/system/fvSolution")
    convergence = (
        PILOT.inspect_solver_convergence(log, fv_solution)
        if fv_solution
        else json.loads(files["attempt/solver-convergence.json"].read_text(encoding="utf-8"))
        if "attempt/solver-convergence.json" in files
        else {}
    )
    attempt_manifest = (
        json.loads(files["attempt/manifest.json"].read_text(encoding="utf-8"))
        if "attempt/manifest.json" in files
        else {}
    )
    actual = {
        "job_id": attempt_manifest.get("job_id"),
        "case_id": attempt_manifest.get("case_id"),
        "ranks": attempt_manifest.get("rank_count", attempt_manifest.get("ranks")),
        "horizon_s": attempt_manifest.get("horizon_s"),
        "delta_t_s": attempt_manifest.get("delta_t_s"),
    }
    expected = {
        "job_id": job["job_id"],
        "case_id": job["case_id"],
        "ranks": job["expected_ranks"],
        "horizon_s": job["horizon_s"],
        "delta_t_s": job["delta_t_s"],
    }
    same = all(
        actual[key] == expected[key]
        if key in {"job_id", "case_id", "ranks"}
        else isinstance(actual[key], (float, int))
        and math.isclose(float(actual[key]), float(expected[key]), rel_tol=1e-12, abs_tol=1e-15)
        for key in expected
    )
    reached = parsed["physical_time_reached_s"]
    horizon_reached = reached is not None and float(reached) + max(
        1e-12, float(job["delta_t_s"]) * 1e-6
    ) >= float(job["horizon_s"])
    convergence_ok = (
        convergence.get("all_converged") is True and convergence.get("failed_record_count", 0) == 0
    )
    slurm_state = str(parent.get("state", "UNKNOWN")).split()[0].rstrip("+").upper()
    classification = classify_result(
        slurm_state,
        parsed["completion_status"],
        state.get("solver_exit_code"),
        horizon_reached,
        convergence_ok,
        same,
    )

    integration = ledger.get("integration", {}) if isinstance(ledger, dict) else {}
    return {
        "analysis_status": "complete",
        "classification": classification,
        "scientific_scope": "Exploratory per-run audit only; no E1 or field-validation gate decision.",
        "expected_inputs": expected,
        "attempt_manifest_inputs": actual,
        "expected_inputs_match": same,
        "slurm_state": slurm_state,
        "solver_log_status": parsed["completion_status"],
        "solver_exit_code": state.get("solver_exit_code"),
        "expected_horizon_s": job["horizon_s"],
        "reached_time_s": reached,
        "reached_horizon": horizon_reached,
        "expected_delta_t_s": job["delta_t_s"],
        "logged_step_count": parsed["step_count"],
        "alpha_min_max": parsed["alpha_min_max"],
        "courant_number": parsed["courant_number"],
        "interface_courant_number": parsed["interface_courant_number"],
        "pressure_solve_iterations": parsed["pressure_solve_iterations"],
        "linear_residuals": parsed["residuals"],
        "solver_convergence": convergence,
        "u_peak": parse_u_peak(files.get("attempt/max-speed.csv")),
        "solver_clock_time_s": parsed["timing"]["clock_time_seconds"],
        "solver_wall_time_s": state.get("solver_wall_s"),
        "fatal_errors": parsed["fatal_errors"],
        "divergence_detected": parsed["divergence_detected"],
        "conservation": {
            key: integration[key]
            for key in (
                "initial_inventory_kg",
                "injected_kg",
                "final_inventory_m3",
                "signed_net_escape_kg",
                "max_abs_per_step_closure_residual_kg",
                "max_abs_cumulative_closure_residual_kg",
                "closure_residual_kg",
            )
            if key in integration
        },
        "ledger_status": ledger.get("coverage", {}).get("status")
        if isinstance(ledger, dict)
        else None,
        "formal_validation_decision": ledger.get("formal_validation_decision")
        if isinstance(ledger, dict)
        else None,
        "cpu_accounting": {
            "parent": parent,
            "steps": sacct.get("steps", []),
            "note": "Parent and step CPU rows are separate; step CPU is not added to parent CPU.",
        },
        "diagnostic_gaps": gaps,
        "timing_scope": "OpenFOAM ClockTime and launcher wall time only; no full I/O timing is inferred.",
    }


def valid_capture(directory: Path, archive_hash: str) -> bool:
    try:
        report = json.loads((directory / "audit.json").read_text(encoding="utf-8"))
        sidecar = (directory / "audit-bundle.tar.gz.sha256").read_text(encoding="ascii").split()[0]
        bundle = directory / "audit-bundle.tar.gz"
    except (OSError, ValueError, IndexError, json.JSONDecodeError):
        return False
    return (
        report.get("archive_sha256") == archive_hash
        and report.get("capture_status") == "verified"
        and report.get("analysis_complete") is True
        and SHA256_RE.fullmatch(sidecar) is not None
        and bundle.is_file()
        and sha256_file(bundle) == sidecar
    )


class Output:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("output must be a real directory")
        self.directory = directory.resolve()
        for name in (".lock", "status.json", "events.jsonl"):
            if (self.directory / name).is_symlink():
                raise ValueError(f"output {name} must not be a symlink")
        self.lock = (self.directory / ".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.lock.close()
            raise RuntimeError("another auditor already holds this output directory") from error
        self.status_path = self.directory / "status.json"
        self.events_path = self.directory / "events.jsonl"
        self.status = (
            json.loads(self.status_path.read_text(encoding="utf-8"))
            if self.status_path.exists()
            else {"schema_version": 1, "jobs": {}}
        )

    def close(self) -> None:
        self.lock.close()

    def save(self, job_id: str, record: dict[str, Any], phase: str) -> None:
        jobs = self.status.get("jobs", {})
        jobs[job_id] = record
        self.status.update(
            {"schema_version": 1, "updated_utc": utc_now(), "phase": phase, "jobs": jobs}
        )
        atomic_json(self.status_path, self.status)
        event = {
            "utc": utc_now(),
            "job_id": job_id,
            "phase": phase,
            "classification": record.get("classification"),
        }
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def run_one(job_id: str, manifest: dict[str, Any], manifest_path: Path, output_path: Path) -> int:
    job = next((item for item in manifest["jobs"] if item["job_id"] == job_id), None)
    if job is None:
        raise ValueError(f"job {job_id} is not listed in --manifest")
    declared_root = Path(job["source_root"])
    declared_run = Path(job["run_dir"])
    if not declared_run.is_absolute():
        declared_run = declared_root / declared_run
    if not declared_run.is_relative_to(declared_root) or declared_run == declared_root:
        raise ValueError("manifest run_dir must be below source_root")
    root = declared_root.resolve(strict=True)
    run_dir = root / declared_run.relative_to(declared_root)
    if run_dir.is_symlink() or any(path.is_symlink() for path in run_dir.parents if path != root):
        raise ValueError("manifest run_dir contains a symlinked parent")
    output_resolved = output_path.resolve(strict=False)
    if output_resolved == run_dir or output_resolved.is_relative_to(run_dir):
        raise ValueError("--output must be outside the immutable HPC run directory")

    output = Output(output_path)
    record: dict[str, Any] = {"job_id": job_id, "mode": "slurm-afterany", "updated_utc": utc_now()}
    try:
        try:
            sacct = local_sacct(job_id)
        except Exception as error:
            record.update(
                {
                    "phase": "sacct_error",
                    "classification": "accounting_unavailable",
                    "reason": f"{type(error).__name__}: {error}"[:1000],
                }
            )
            output.save(job_id, record, "sacct_error")
            return 1
        record["sacct"] = sacct
        parent = sacct.get("parent")
        if not parent:
            record.update(
                {"phase": "missing_from_sacct", "classification": "sacct_parent_row_missing"}
            )
            output.save(job_id, record, "missing_from_sacct")
            return 1
        if not is_terminal_state(parent["state"]):
            record.update({"phase": "not_terminal", "classification": "parent_job_not_terminal"})
            output.save(job_id, record, "not_terminal")
            return 1
        state_error = None
        try:
            state, sidecar, archive_path = read_state(job_id, run_dir)
        except Exception as error:
            state, sidecar, archive_path = None, None, run_dir / "result.tar.gz"
            state_error = f"{type(error).__name__}: {error}"[:1000]
        record["run_state"] = state
        if state_error:
            record["run_state_error"] = state_error

        if state is None and archive_path.is_file():
            record.update(
                {
                    "phase": "capture_error",
                    "classification": "terminal_archive_without_run_state",
                    "reason": state_error or "archive exists but run-state.json is unavailable",
                    "diagnostic_gaps": diagnostic_gaps({}, {}, sacct),
                }
            )
            output.save(job_id, record, "capture_error")
            return 1
        if state is None or not archive_path.is_file():
            cpu_s = hpc_metrics._slurm_seconds(parent.get("total_cpu", ""))
            slurm_state = parent["state"].split()[0].rstrip("+").upper()
            if state and state.get("status") == "bootstrap_failed":
                classification = "bootstrap_failure_no_archive"
            elif slurm_state.startswith("CANCELLED") and cpu_s == 0:
                classification = "cancelled_zero_cpu_no_archive"
            elif cpu_s == 0:
                classification = "admission_or_bootstrap_failure_no_archive"
            elif state and str(state.get("attempt_archive_status", "")).startswith(
                "verification_or_pack_failed"
            ):
                classification = "archive_pack_failed_after_solver_run"
            elif state is None:
                classification = "artifact_not_visible_afterany_start"
            else:
                classification = "terminal_no_archive_afterany_start"
            record.update(
                {
                    "phase": "inspected_no_archive",
                    "classification": classification,
                    "parent_cpu_seconds": cpu_s,
                    "reason": state_error
                    or "No archive was visible at afterany start; artifact status is not a physical solver verdict.",
                    "bootstrap_diagnostics": bootstrap_diagnostics(job, run_dir),
                    "diagnostic_gaps": diagnostic_gaps({}, {}, sacct),
                }
            )
            output.save(job_id, record, "inspected_no_archive")
            return 0

        expected_archive = str(run_dir / "result.tar.gz")
        if state.get("result_archive") not in {None, expected_archive}:
            raise ValueError("run-state archive path differs from the declared job directory")
        archive_hash = state.get("result_archive_sha256")
        if not isinstance(archive_hash, str) or not SHA256_RE.fullmatch(archive_hash):
            record.update(
                {"phase": "capture_error", "classification": "invalid_archive_hash_in_run_state"}
            )
            output.save(job_id, record, "capture_error")
            return 1

        job_output = output.directory / "jobs" / job_id
        if job_output.is_symlink():
            raise ValueError("per-job output directory must not be a symlink")
        job_output.mkdir(parents=True, exist_ok=True)
        existing = job_output / archive_hash
        if valid_capture(existing, archive_hash):
            record.update(
                {
                    "phase": "captured",
                    "classification": "duplicate_capture_skipped",
                    "archive_sha256": archive_hash,
                    "audit_path": str(existing / "audit.json"),
                    "bundle_path": str(existing / "audit-bundle.tar.gz"),
                }
            )
            output.save(job_id, record, "captured")
            return 0
        prior_attempts = [
            path for path in job_output.glob(f"{archive_hash}-attempt-*") if path.is_dir()
        ]
        if len(prior_attempts) >= MAX_CAPTURE_ATTEMPTS:
            record.update(
                {
                    "phase": "capture_error",
                    "classification": "capture_retry_limit",
                    "archive_sha256": archive_hash,
                    "reason": f"already preserved {len(prior_attempts)} failed captures",
                }
            )
            output.save(job_id, record, "capture_error")
            return 1
        version = (
            existing
            if not existing.exists()
            else job_output / f"{archive_hash}-attempt-{len(prior_attempts) + 2}"
        )
        version.mkdir(mode=0o700)
        try:
            selection = compact_archive(archive_path, archive_hash, sidecar, version)
            verify_compact(version / "compact.tar.gz", selection, archive_hash)
            analysis_dir = version / "_analysis"
            analysis_dir.mkdir()
            files: dict[str, Path] = {}
            with tarfile.open(version / "compact.tar.gz", "r:gz") as compact:
                for member in compact.getmembers():
                    name = safe_member_name(member.name)
                    path = analysis_dir / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    source = compact.extractfile(member)
                    if source is None:
                        raise ValueError(f"cannot read selected member: {name}")
                    with path.open("xb") as stream:
                        shutil.copyfileobj(source, stream)
                    files[name] = path
            metrics = summarize(job, files, state, sacct)
            audit = {
                "schema_version": 1,
                "created_utc": utc_now(),
                "job_id": job_id,
                "case_id": job["case_id"],
                "expected_ranks": job["expected_ranks"],
                "expected_horizon_s": job["horizon_s"],
                "expected_delta_t_s": job["delta_t_s"],
                "manifest_sha256": sha256_file(manifest_path),
                "auditor_sha256": sha256_file(Path(__file__).resolve()),
                "run_dir": str(run_dir),
                "archive_sha256": archive_hash,
                "compact_archive_sha256": sha256_file(version / "compact.tar.gz"),
                "selected_files": selection["selected_files"],
                "run_state": state,
                "slurm": sacct,
                "capture_status": "verified",
                "analysis_status": metrics["analysis_status"],
                "analysis_complete": True,
                "metrics": metrics,
                "capture_limits": {
                    "max_file_bytes": MAX_FILE_BYTES,
                    "max_selected_bytes": MAX_SELECTED_BYTES,
                    "max_files": MAX_SELECTED_FILES,
                },
            }
            atomic_json(version / "audit.json", audit)
            bundle_path = version / "audit-bundle.tar.gz"
            with tarfile.open(bundle_path, "w:gz", compresslevel=1) as bundle:
                bundle.add(version / "compact.tar.gz", arcname="compact.tar.gz", recursive=False)
                bundle.add(version / "selection.json", arcname="selection.json", recursive=False)
                bundle.add(version / "audit.json", arcname="audit.json", recursive=False)
            bundle_hash = sha256_file(bundle_path)
            (version / "audit-bundle.tar.gz.sha256").write_text(
                f"{bundle_hash}  audit-bundle.tar.gz\n", encoding="ascii"
            )
            shutil.rmtree(analysis_dir)
            for name in ("compact.tar.gz", "compact.tar.gz.sha256", "selection.json"):
                (version / name).unlink()
            record.update(
                {
                    "phase": "captured",
                    "classification": metrics["classification"],
                    "archive_sha256": archive_hash,
                    "audit_path": str(version / "audit.json"),
                    "bundle_path": str(bundle_path),
                    "bundle_sha256": bundle_hash,
                }
            )
            output.save(job_id, record, "captured")
            return 0
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"[:1000]
            atomic_json(
                version / "capture-error.json",
                {
                    "utc": utc_now(),
                    "job_id": job_id,
                    "archive_sha256": archive_hash,
                    "error": reason,
                    "run_state": state,
                    "slurm": sacct,
                },
            )
            record.update(
                {
                    "phase": "capture_error",
                    "classification": "archive_or_analysis_error",
                    "archive_sha256": archive_hash,
                    "audit_attempt_path": str(version),
                    "reason": reason,
                }
            )
            output.save(job_id, record, "capture_error")
            return 1
    finally:
        output.close()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="one job's durable audit directory"
    )
    args = parser.parse_args()
    if not JOB_ID_RE.fullmatch(args.job_id):
        parser.error("--job-id must contain decimal digits only")
    try:
        manifest = validate_manifest(json.loads(args.manifest.read_text(encoding="utf-8")))
        return run_one(args.job_id, manifest, args.manifest.resolve(), args.output)
    except Exception as error:
        print(f"hpc_finished_audit: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
