#!/usr/bin/env python3
"""Exact-ID, GO-gated, bounded controller for this small reference case."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IMAGE = "opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319"
SOLVER = "compressibleInterFoamFrozenAlphaSourceV2NoPout"
FIELDS = (
    "alpha.water",
    "alphaPhi0.water",
    "alphat",
    "k",
    "nut",
    "omega",
    "p",
    "p_rgh",
    "phi",
    "rho",
    "T",
    "T.air",
    "T.water",
    "U",
)
TARGET_S = 0.1
DT_S = 1e-4
SAVE_REQUEST_S = 510.0
HARD_WALL_S = 650.0
POLL_S = 2.0
EXECUTION_CLOSURE_FILES = (
    "cases/i4f_pressure_equilibrium_reference/Allrun",
    "cases/i4f_pressure_equilibrium_reference/case_controller.py",
    "cases/i4f_pressure_equilibrium_reference/run_in_container.sh",
    "cases/i4f_pressure_equilibrium_reference/verify_native_checkpoint.py",
    "cases/i4f_pressure_equilibrium_reference/input-manifest.json",
    "scripts/run_local.py",
    "scripts/doctor.py",
    "pyproject.toml",
    "uv.lock",
    "scripts/prepare_i4f_dcec_source.py",
    "scripts/analyze_dash8_interface_growth.py",
    "scripts/analyze_native_turbulence.py",
    "scripts/analyze_native_vof.py",
    "src/aerial_drop/__init__.py",
    "src/aerial_drop/structure_counts.py",
    "solvers/i4f_frozen_sp/source-manifest.json",
    "solvers/i4f_frozen_sp/variants/dcec/variant-manifest.json",
    "solvers/i4f_frozen_sp/variants/dcec/overrides/applications/solvers/multiphase/compressibleInterFoam/compressibleInterFoam.C",
    "solvers/i4f_frozen_sp/variants/dcec/overrides/applications/solvers/multiphase/compressibleInterFoam/pEqn.H",
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def command(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def inspect(identity: str) -> dict[str, Any] | None:
    result = command(["docker", "inspect", "--format", "{{json .}}", identity])
    if result.returncode:
        if "no such" in result.stderr.casefold():
            return None
        raise RuntimeError(f"docker inspect failed: {result.stderr.strip()}")
    raw = json.loads(result.stdout)
    return {
        "id": raw.get("Id"),
        "name": raw.get("Name", "").lstrip("/"),
        "state": raw.get("State", {}),
        "image": raw.get("Config", {}).get("Image"),
        "host_config": raw.get("HostConfig", {}),
    }


def pause_paths(repo: Path, output: Path, case: Path) -> list[str]:
    paths = (repo / "results/runs/PAUSE", output / "PAUSE", case / "PAUSE")
    return [str(path) for path in paths if path.exists()]


def verify_case_input_tree(output: Path) -> dict[str, Any]:
    manifest_path = output / "input-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    bad: list[str] = []
    for item in manifest["case_files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            bad.append(item["path"])
            continue
        path = (output / relative).resolve(strict=False)
        if (
            output.resolve() not in path.parents
            or not path.is_file()
            or sha(path) != item["sha256"]
        ):
            bad.append(item["path"])
    if bad:
        raise RuntimeError(f"frozen case input mismatch: {bad}")
    return {
        "file_count": len(manifest["case_files"]),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "source_freeze": manifest["source_freeze"],
    }


def git_worktree_state(repo: Path) -> dict[str, Any]:
    revision = command(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if revision.returncode:
        raise RuntimeError(f"cannot capture Git revision: {revision.stderr.strip()}")
    status = command(["git", "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=all"])
    if status.returncode:
        raise RuntimeError(f"cannot capture Git dirty state: {status.stderr.strip()}")
    status_text = status.stdout
    dirty_paths = [line[3:] for line in status_text.splitlines() if len(line) >= 4]
    return {
        "revision_head": revision.stdout.strip(),
        "worktree_dirty": bool(status_text),
        "dirty_path_count": len(dirty_paths),
        "dirty_paths": dirty_paths,
        "porcelain_status_sha256": hashlib.sha256(status_text.encode()).hexdigest(),
    }


def snapshot_execution_closure(repo: Path, output: Path) -> dict[str, Any]:
    """Copy the launch-time host/container execution closure before GO."""
    snapshot_root = output / "provenance/execution-closure"
    record_path = output / "provenance/execution-source-snapshot.json"
    if snapshot_root.exists() or record_path.exists():
        raise FileExistsError("execution-source snapshot already exists in this output directory")
    git_state = git_worktree_state(repo)
    captured_at = utc()
    files: list[dict[str, Any]] = []
    snapshot_root.mkdir(parents=True)
    for relative_text in EXECUTION_CLOSURE_FILES:
        relative = Path(relative_text)
        source = (repo / relative).resolve(strict=True)
        if repo.resolve() not in source.parents or not source.is_file():
            raise RuntimeError(f"execution-closure source is missing or escapes repo: {relative}")
        source_sha = sha(source)
        destination = snapshot_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied_sha = sha(destination)
        if copied_sha != source_sha:
            raise RuntimeError(f"execution-closure snapshot copy mismatch: {relative}")
        files.append(
            {
                "repo_relative_path": relative.as_posix(),
                "snapshot_relative_path": destination.relative_to(output).as_posix(),
                "size_bytes": destination.stat().st_size,
                "sha256": copied_sha,
            }
        )
    record = {
        "schema": "i4f-pressure-equilibrium-execution-source-snapshot/v1",
        "captured_utc": captured_at,
        **git_state,
        "file_count": len(files),
        "files": files,
    }
    write_json(record_path, record)
    return {
        "record_path": record_path.relative_to(output).as_posix(),
        "record_sha256": sha(record_path),
        **record,
    }


def verify_execution_closure_snapshot(repo: Path, output: Path, snapshot: dict[str, Any]) -> None:
    """Require both the saved bytes and live sources to match immediately before GO."""
    record_path = output / snapshot["record_path"]
    if not record_path.is_file() or sha(record_path) != snapshot["record_sha256"]:
        raise RuntimeError("execution-source snapshot record changed after preparation")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("files") != snapshot.get("files"):
        raise RuntimeError("execution-source snapshot file list differs from host preparation")
    for item in record["files"]:
        source = (repo / item["repo_relative_path"]).resolve(strict=True)
        copied = (output / item["snapshot_relative_path"]).resolve(strict=True)
        if repo.resolve() not in source.parents or output.resolve() not in copied.parents:
            raise RuntimeError("execution-source snapshot path escaped its root")
        expected = item["sha256"]
        if sha(source) != expected or sha(copied) != expected:
            raise RuntimeError(
                f"execution-source bytes changed before GO: {item['repo_relative_path']}"
            )


def prepare_host_inputs(repo: Path, output: Path, freeze: dict[str, Any]) -> dict[str, Any]:
    """Prepare Python-dependent source and checksum metadata on the host.

    The pinned OpenFOAM image intentionally has no Python interpreter, so the
    container runner only performs shell/OpenFOAM work after this frozen step.
    """
    source_output = output / "build/dcec-source"
    source_record = output / "logs/source-prepare.json"
    checksum_list = output / "input-files.sha256"
    if (
        source_output.exists()
        or source_record.exists()
        or checksum_list.exists()
        or (output / "provenance/execution-closure").exists()
        or (output / "provenance/execution-source-snapshot.json").exists()
    ):
        raise FileExistsError("host-prepared inputs already exist; use a fresh output directory")
    source_record.parent.mkdir(parents=True, exist_ok=True)
    execution_snapshot = snapshot_execution_closure(repo, output)
    manifest = json.loads((output / "input-manifest.json").read_text(encoding="utf-8"))
    checksum_lines: list[str] = []
    for item in manifest["case_files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe manifest path: {relative}")
        checksum_lines.append(f"{item['sha256']}  {relative.as_posix()}\n")
    checksum_list.write_text("".join(checksum_lines), encoding="utf-8")
    result = command(
        [
            sys.executable,
            str(repo / "scripts/prepare_i4f_dcec_source.py"),
            "--repo-root",
            str(repo),
            "--output-dir",
            str(source_output),
        ],
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError(
            f"host DCEC source preparation failed: {result.stderr[-2000:]} {result.stdout[-1000:]}"
        )
    source_tree = json.loads(result.stdout)
    source_record.write_text(
        json.dumps(source_tree, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if source_tree.get("file_count") != 68 or source_tree.get("status") != (
        "source_tree_prepared_and_hash_verified"
    ):
        raise RuntimeError("host DCEC source preparation did not verify the 68-file variant")
    return {
        "input_manifest_sha256": freeze["manifest_sha256"],
        "input_checksums_sha256": sha(checksum_list),
        "source_prepare_sha256": sha(source_record),
        "source_tree": source_tree,
        "execution_source_snapshot": execution_snapshot,
    }


def write_preparation_record(
    repo: Path,
    case: Path,
    freeze: dict[str, Any],
    host_preparation: dict[str, Any],
) -> dict[str, Any]:
    marker = case / "logs/preparation-ready.env"
    if not marker.is_file():
        raise RuntimeError("container preparation marker is missing")
    marker_values: dict[str, str] = {}
    for line in marker.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            raise RuntimeError(f"malformed preparation marker line: {line!r}")
        key, value = line.split("=", 1)
        if key in marker_values:
            raise RuntimeError(f"duplicate preparation marker key: {key}")
        marker_values[key] = value
    expected = {
        "schema": "i4f-pressure-equilibrium-case-preparation/v1",
        "status": "prepared_mesh_ok_waiting_for_GO",
        "input_manifest_sha256": freeze["manifest_sha256"],
        "input_checksums_sha256": host_preparation["input_checksums_sha256"],
        "source_prepare_sha256": host_preparation["source_prepare_sha256"],
        "mesh_check": "Mesh_OK",
    }
    if any(marker_values.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"container preparation marker mismatch: {marker_values}")
    binary = case / "bin/compressibleInterFoamFrozenAlphaSourceV2NoPout"
    if not binary.is_file() or sha(binary) != marker_values.get("solver_binary_sha256"):
        raise RuntimeError("host and container disagree on the built solver binary hash")
    source_record = json.loads((case / "logs/source-prepare.json").read_text(encoding="utf-8"))
    required_fields = (
        "alpha.water",
        "alphat",
        "k",
        "nut",
        "omega",
        "p",
        "p_rgh",
        "T",
        "U",
    )
    payload = {
        "schema": "i4f-pressure-equilibrium-case-preparation/v1",
        "status": "prepared_mesh_ok_waiting_for_GO",
        "image": IMAGE,
        "input_manifest_sha256": freeze["manifest_sha256"],
        "prescribed_input_file_count": freeze["file_count"],
        "dcec_source_builder_sha256": sha(repo / "scripts/prepare_i4f_dcec_source.py"),
        "dcec_source_tree": source_record,
        "execution_source_snapshot": host_preparation["execution_source_snapshot"],
        "solver_binary": "bin/compressibleInterFoamFrozenAlphaSourceV2NoPout",
        "solver_binary_sha256": marker_values["solver_binary_sha256"],
        "post_setFields_time0_field_sha256": {
            field: sha(case / "0" / field) for field in required_fields
        },
        "input_checksums_sha256": host_preparation["input_checksums_sha256"],
        "preparation_marker_sha256": sha(marker),
        "mesh_check": "Mesh OK",
        "blockMesh_command": "blockMesh",
        "setFields_command": "setFields",
        "checkMesh_command": "checkMesh -allTopology -allGeometry",
    }
    write_json(case / "logs/preparation-ready.json", payload)
    return payload


def latest_checkpoint(case: Path) -> dict[str, Any] | None:
    candidates: list[tuple[float, Path]] = []
    for path in case.iterdir():
        if not path.is_dir():
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        if value > 0.0:
            candidates.append((value, path))
    if not candidates:
        return None
    value, path = max(candidates, key=lambda item: item[0])
    present = [name for name in FIELDS if (path / name).is_file() and (path / name).stat().st_size]
    time_path = path / "uniform/time"
    time_value: float | None = None
    if time_path.is_file():
        text = time_path.read_text(errors="replace")
        match = re.search(r"(?m)^\s*value\s+([-+0-9.eE]+)\s*;", text)
        if match:
            try:
                time_value = float(match.group(1))
            except ValueError:
                time_value = None
    return {
        "time_s": value,
        "uniform_time_value_s": time_value,
        "path": str(path),
        "fields_present": present,
        "all_14_fields_present": len(present) == len(FIELDS),
        "uniform_time_present": time_path.is_file() and time_path.stat().st_size > 0,
        "uniform_time_sha256": sha(time_path) if time_path.is_file() else None,
    }


class LogProgress:
    """Read only appended solver log bytes; do not rescan a growing file."""

    def __init__(self) -> None:
        self.offset = 0
        self.partial = b""
        self.latest_time_s: float | None = None
        self.normal_end = False
        self.fatal_lines: list[str] = []
        self.last_execution_time_s: float | None = None

    def update(self, path: Path) -> None:
        if not path.is_file():
            return
        size = path.stat().st_size
        if size < self.offset:
            self.offset = 0
            self.partial = b""
        with path.open("rb") as stream:
            stream.seek(self.offset)
            data = stream.read()
            self.offset = stream.tell()
        lines = (self.partial + data).split(b"\n")
        self.partial = lines.pop() if lines else b""
        for raw in lines:
            line = raw.decode("utf-8", errors="replace").strip()
            match = re.fullmatch(r"Time\s*=\s*([-+0-9.eE]+)", line)
            if match:
                try:
                    self.latest_time_s = float(match.group(1))
                except ValueError:
                    pass
            if line == "End":
                self.normal_end = True
            if line.startswith(("FOAM FATAL ERROR:", "FOAM FATAL IO ERROR:")):
                self.fatal_lines.append(line[:500])
            exec_match = re.search(r"ExecutionTime\s*=\s*([-+0-9.eE]+)\s*s", line)
            if exec_match:
                try:
                    self.last_execution_time_s = float(exec_match.group(1))
                except ValueError:
                    pass


def request_write_now(case: Path, output: Path, reason: str) -> None:
    control = case / "system/controlDict"
    before = control.read_text(encoding="utf-8")
    if re.search(r"(?m)^\s*stopAt\s+writeNow\s*;", before):
        return
    updated, count = re.subn(r"(?m)^(\s*stopAt\s+)endTime(\s*;)", r"\1writeNow\2", before, count=1)
    if count != 1:
        raise RuntimeError("cannot request a graceful save: stopAt is not endTime")
    control.write_text(updated, encoding="utf-8")
    diff = "--- system/controlDict before GO/runtime save\n+++ runtime\n-stopAt endTime;\n+stopAt writeNow;\n"
    (output / "logs/controlDict-resource-stop.diff").write_text(diff, encoding="utf-8")
    write_json(
        output / "logs/stop-request.json",
        {
            "time_utc": utc(),
            "reason": reason,
            "requested_stopAt": "writeNow",
            "controlDict_before_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "controlDict_after_sha256": sha(control),
        },
    )


def run_native_check(
    repo: Path, case: Path, checkpoint: dict[str, Any], output: Path
) -> dict[str, Any]:
    destination = output / "analysis/native-terminal-review.json"
    script = repo / "cases/i4f_pressure_equilibrium_reference/verify_native_checkpoint.py"
    result = command(
        [
            sys.executable,
            str(script),
            "--case",
            str(case),
            "--time-dir",
            str(checkpoint["path"]),
            "--output",
            str(destination),
        ],
        timeout=90,
    )
    if result.returncode:
        raise RuntimeError(
            f"native checkpoint verifier failed: {result.stderr[-2000:]} {result.stdout[-1000:]}"
        )
    return json.loads(destination.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--prepare-host-inputs",
        action="store_true",
        help="freeze the source tree/checksum list for a non-solver preparation run",
    )
    args = parser.parse_args()
    repo = args.repo_root.resolve(strict=True)
    output = args.output_dir.resolve(strict=True)
    case = output
    if args.prepare_host_inputs:
        freeze = verify_case_input_tree(output)
        prepared = prepare_host_inputs(repo, output, freeze)
        print(json.dumps(prepared, indent=2, sort_keys=True, allow_nan=False))
        return 0
    manifest_path = output / "launch-manifest.json"
    status_path = output / "run-status.json"
    go_path = output / "GO"
    name = ""
    container_id: str | None = None
    started_at: str | None = None
    try:
        if manifest_path.exists() or go_path.exists():
            raise RuntimeError(
                "refusing to relaunch an output directory containing launch identity/GO"
            )
        if pause_paths(repo, output, case):
            raise RuntimeError(
                f"PAUSE sentinel present before launch: {pause_paths(repo, output, case)}"
            )
        freeze = verify_case_input_tree(case)
        host_preparation = prepare_host_inputs(repo, case, freeze)
        disk = shutil.disk_usage(output)
        if disk.free < 1 * 1024**3:
            raise RuntimeError(f"less than 1 GiB free before run: {disk.free} bytes")
        image_check = command(
            ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", IMAGE]
        )
        if image_check.returncode:
            raise RuntimeError(f"pinned OpenFOAM image unavailable: {image_check.stderr.strip()}")
        collision = command(
            ["docker", "ps", "-a", "--filter", "name=^/i4f-pe-", "--format", "{{.Names}}"]
        )
        if collision.returncode:
            raise RuntimeError(f"cannot check container names: {collision.stderr.strip()}")

        safe_slug = re.sub(r"[^a-z0-9-]+", "-", output.name.lower()).strip("-")[:36] or "case"
        name = f"i4f-pe-{safe_slug}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        create = command(
            [
                "docker",
                "create",
                "--name",
                name,
                "--log-driver=none",
                "--cpus=1",
                "--cpu-shares=2",
                "--memory=4g",
                "--network",
                "none",
                "--label",
                "i4f.experiment=pressure-equilibrium-reference",
                "--mount",
                f"type=bind,src={output},dst=/case",
                "--mount",
                f"type=bind,src={repo},dst=/repo,readonly",
                "--workdir",
                "/repo",
                IMAGE,
                "bash",
                "/repo/cases/i4f_pressure_equilibrium_reference/run_in_container.sh",
                "/case",
                "run",
            ],
            timeout=60,
        )
        if create.returncode:
            raise RuntimeError(f"docker create failed: {create.stderr.strip()}")
        container_id = create.stdout.strip().splitlines()[-1]
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise RuntimeError(f"docker create returned an invalid container ID: {container_id!r}")
        start = command(["docker", "start", container_id], timeout=60)
        if start.returncode:
            raise RuntimeError(f"docker start failed: {start.stderr.strip()}")
        identity = inspect(container_id)
        if not identity or identity["id"] != container_id or not identity["state"].get("Running"):
            raise RuntimeError(f"exact container did not enter preparation state: {identity}")
        started_at = identity["state"].get("StartedAt")
        if not started_at:
            raise RuntimeError("Docker did not return StartedAt")
        container_started_clock = time.monotonic()
        write_json(
            status_path,
            {
                "schema": "i4f-pressure-equilibrium-case-run/v1",
                "status": "container_preparing_before_GO",
                "container_id": container_id,
                "container_name": name,
                "started_at": started_at,
                "input_manifest": freeze,
                "image": IMAGE,
                "updated_utc": utc(),
            },
        )

        preparation_path = case / "logs/preparation-ready.json"
        preparation_marker = case / "logs/preparation-ready.env"
        prepare_deadline = time.monotonic() + 240.0
        while time.monotonic() < prepare_deadline:
            if pause_paths(repo, output, case):
                stop = command(["docker", "stop", "--time", "10", container_id], timeout=20)
                write_json(
                    status_path,
                    {
                        "schema": "i4f-pressure-equilibrium-case-run/v1",
                        "status": "held_by_pause_before_GO",
                        "container_id": container_id,
                        "container_name": name,
                        "started_at": started_at,
                        "pause_paths": pause_paths(repo, output, case),
                        "docker_stop_exit": stop.returncode,
                        "updated_utc": utc(),
                    },
                )
                return 1
            current = inspect(container_id)
            if (
                not current
                or current["id"] != container_id
                or current["state"].get("StartedAt") != started_at
            ):
                raise RuntimeError("container identity/StartedAt changed during preparation")
            if preparation_marker.is_file():
                break
            if not current["state"].get("Running"):
                raise RuntimeError(
                    f"container exited before pre-GO readiness (exit={current['state'].get('ExitCode')})"
                )
            time.sleep(1.0)
        else:
            raise TimeoutError("pre-GO source build/mesh preparation exceeded 240 seconds")

        write_preparation_record(repo, case, freeze, host_preparation)
        preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
        if preparation.get("status") != "prepared_mesh_ok_waiting_for_GO":
            raise RuntimeError(f"unexpected pre-GO readiness status: {preparation.get('status')!r}")
        if preparation.get("input_manifest_sha256") != freeze["manifest_sha256"]:
            raise RuntimeError(
                "preparation input-manifest hash differs from the host-verified copy"
            )
        if preparation.get("prescribed_input_file_count") != 20:
            raise RuntimeError("preparation did not verify all 20 frozen case files")
        if preparation.get("mesh_check") != "Mesh OK":
            raise RuntimeError("mesh preparation is not verified")
        if preparation.get("dcec_source_tree", {}).get("file_count") != 68:
            raise RuntimeError("DCEC source builder did not verify all 68 variant files")
        verify_execution_closure_snapshot(
            repo, output, host_preparation["execution_source_snapshot"]
        )

        manifest = {
            "schema": "i4f-pressure-equilibrium-case-launch/v1",
            "status": "exact_container_verified_waiting_for_GO",
            "output_dir": str(output.relative_to(repo))
            if output.is_relative_to(repo)
            else str(output),
            "container_id": container_id,
            "container_name": name,
            "started_at": started_at,
            "image": IMAGE,
            "solver": SOLVER,
            "solver_binary_sha256": preparation["solver_binary_sha256"],
            "input_manifest_sha256": freeze["manifest_sha256"],
            "preparation_ready_sha256": sha(preparation_path),
            "case_controller_sha256": sha(Path(__file__).resolve()),
            "run_in_container_sha256": sha(
                repo / "cases/i4f_pressure_equilibrium_reference/run_in_container.sh"
            ),
            "dcec_source_builder_sha256": preparation["dcec_source_builder_sha256"],
            "dcec_source_manifest_sha256": preparation["dcec_source_tree"][
                "source_manifest_sha256"
            ],
            "dcec_variant_manifest_sha256": preparation["dcec_source_tree"][
                "variant_manifest_sha256"
            ],
            "execution_source_snapshot": host_preparation["execution_source_snapshot"],
            "target_s": TARGET_S,
            "deltaT_s": DT_S,
            "requested_utc": utc(),
            "resource_limits": {
                "cpu_equivalents": 1.0,
                "cpu_shares": 2,
                "memory_bytes": 4 * 1024**3,
                "solver_timeout_s": 650,
                "guard_hard_wall_s": HARD_WALL_S,
                "graceful_save_request_after_s": SAVE_REQUEST_S,
            },
            "input_freeze": freeze,
            "preparation": preparation,
        }
        write_json(manifest_path, manifest)
        manifest_digest = sha(manifest_path)
        identity_text = (
            f"container_id={container_id}\n"
            f"started_at={started_at}\n"
            f"launch_manifest_sha256={manifest_digest}\n"
        )
        (case / "launch-identity.txt").write_text(identity_text, encoding="utf-8")
        go_tmp = go_path.with_suffix(".tmp")
        go_tmp.write_text(identity_text, encoding="utf-8")
        os.replace(go_tmp, go_path)
        write_json(
            status_path,
            {
                **manifest,
                "status": "running",
                "launch_manifest_sha256": manifest_digest,
                "go_sha256": sha(go_path),
                "elapsed_wall_s": 0.0,
                "updated_utc": utc(),
            },
        )

        next_status = 0.0
        save_requested = False
        save_reason: str | None = None
        progress = LogProgress()
        log_path = case / "log.cold-coupled"
        while time.monotonic() - container_started_clock < HARD_WALL_S:
            elapsed = time.monotonic() - container_started_clock
            current = inspect(container_id)
            if (
                not current
                or current["id"] != container_id
                or current["state"].get("StartedAt") != started_at
            ):
                raise RuntimeError("container identity/StartedAt changed while solver was running")
            progress.update(log_path)
            requested_reason = None
            flags = pause_paths(repo, output, case)
            if flags:
                requested_reason = "pause_sentinel_observed"
            elif elapsed >= SAVE_REQUEST_S:
                requested_reason = "bounded_wall_save"
            if requested_reason and not save_requested and current["state"].get("Running"):
                request_write_now(case, output, requested_reason)
                save_requested = True
                save_reason = requested_reason
            if elapsed >= next_status:
                write_json(
                    status_path,
                    {
                        **manifest,
                        "status": "running"
                        if current["state"].get("Running")
                        else "container_terminal_waiting_capture_check",
                        "launch_manifest_sha256": manifest_digest,
                        "go_sha256": sha(go_path),
                        "elapsed_wall_s": round(elapsed, 3),
                        "latest_log_time_s": progress.latest_time_s,
                        "stop_request_made": save_requested,
                        "stop_reason": save_reason,
                        "fatal_log_lines": progress.fatal_lines[-4:],
                        "docker_state": current["state"],
                        "updated_utc": utc(),
                    },
                )
                next_status = elapsed + 5.0
            if not current["state"].get("Running"):
                code = current["state"].get("ExitCode")
                if code is None:
                    time.sleep(POLL_S)
                    continue
                progress.update(log_path)
                checkpoint = latest_checkpoint(case)
                field_check: dict[str, Any] | None = None
                if (
                    checkpoint
                    and checkpoint["all_14_fields_present"]
                    and checkpoint["uniform_time_present"]
                ):
                    field_check = run_native_check(repo, case, checkpoint, output)
                target_reached = bool(
                    checkpoint
                    and checkpoint["time_s"] >= TARGET_S - DT_S / 2
                    and checkpoint["uniform_time_value_s"] is not None
                    and abs(checkpoint["uniform_time_value_s"] - checkpoint["time_s"]) <= DT_S / 2
                )
                complete = bool(
                    checkpoint
                    and checkpoint["all_14_fields_present"]
                    and checkpoint["uniform_time_present"]
                )
                field_ok = bool(field_check and field_check.get("status") == "native_fields_valid")
                normal = int(code) == 0 and progress.normal_end
                healthy = (
                    normal and complete and target_reached and field_ok and not progress.fatal_lines
                )
                status = (
                    "healthy_normal_end"
                    if healthy
                    else "normal_end_before_target"
                    if normal and complete and field_ok
                    else "solver_failure_or_incomplete_capture"
                )
                write_json(
                    status_path,
                    {
                        **manifest,
                        "status": status,
                        "launch_manifest_sha256": manifest_digest,
                        "go_sha256": sha(go_path),
                        "terminal": {
                            "docker_exit_code": int(code),
                            "normal_openfoam_end_marker": progress.normal_end,
                            "latest_log_time_s": progress.latest_time_s,
                            "execution_time_s": progress.last_execution_time_s,
                            "latest_native_checkpoint": checkpoint,
                            "complete_14_field_checkpoint": complete,
                            "target_reached_within_half_step": target_reached,
                            "native_field_check": field_check,
                            "fatal_log_lines": progress.fatal_lines,
                        },
                        "stop_request_made": save_requested,
                        "stop_reason": save_reason,
                        "container_retained_for_audit": True,
                        "updated_utc": utc(),
                    },
                )
                return 0 if healthy else 1
            time.sleep(POLL_S)

        # Hardwall: ask the running solver to write a complete state, then enforce
        # a short bounded stop and record whatever native checkpoint exists.
        current = inspect(container_id)
        if current and current["id"] == container_id and current["state"].get("Running"):
            if not save_requested:
                request_write_now(case, output, "controller_hard_wall")
                save_requested = True
                save_reason = "controller_hard_wall"
            grace_deadline = time.monotonic() + 45.0
            while time.monotonic() < grace_deadline:
                current = inspect(container_id)
                if not current or not current["state"].get("Running"):
                    break
                time.sleep(1.0)
            current = inspect(container_id)
            if current and current["state"].get("Running"):
                command(["docker", "stop", "--time", "10", container_id], timeout=20)
        current = inspect(container_id)
        progress.update(log_path)
        checkpoint = latest_checkpoint(case)
        code = current["state"].get("ExitCode") if current else None
        complete = bool(
            checkpoint
            and checkpoint["all_14_fields_present"]
            and checkpoint["uniform_time_present"]
        )
        field_check = (
            run_native_check(repo, case, checkpoint, output) if complete and checkpoint else None
        )
        write_json(
            status_path,
            {
                **manifest,
                "status": "bounded_wall_save_before_target"
                if complete
                else "solver_failure_or_incomplete_capture",
                "launch_manifest_sha256": manifest_digest,
                "go_sha256": sha(go_path),
                "terminal": {
                    "docker_exit_code": code,
                    "normal_openfoam_end_marker": progress.normal_end,
                    "latest_log_time_s": progress.latest_time_s,
                    "latest_native_checkpoint": checkpoint,
                    "complete_14_field_checkpoint": complete,
                    "target_reached_within_half_step": bool(
                        checkpoint and checkpoint["time_s"] >= TARGET_S - DT_S / 2
                    ),
                    "native_field_check": field_check,
                },
                "stop_request_made": save_requested,
                "stop_reason": save_reason,
                "container_retained_for_audit": True,
                "updated_utc": utc(),
            },
        )
        return 1
    except Exception as error:  # Preserve an operational failure status beside any created ID.
        if container_id:
            try:
                current = inspect(container_id)
                if current and current["id"] == container_id and current["state"].get("Running"):
                    if go_path.is_file():
                        request_write_now(case, output, "controller_exception")
                        grace_end = time.monotonic() + 25.0
                        while time.monotonic() < grace_end:
                            current = inspect(container_id)
                            if not current or not current["state"].get("Running"):
                                break
                            time.sleep(1.0)
                    current = inspect(container_id)
                    if (
                        current
                        and current["id"] == container_id
                        and current["state"].get("Running")
                    ):
                        command(["docker", "stop", "--time", "10", container_id], timeout=20)
            except Exception:
                pass
        existing = {}
        if status_path.is_file():
            try:
                existing = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = {}
        write_json(
            status_path,
            {
                **existing,
                "schema": "i4f-pressure-equilibrium-case-run/v1",
                "status": "controller_error",
                "error": str(error),
                "container_id": container_id or existing.get("container_id"),
                "container_name": name or existing.get("container_name"),
                "started_at": started_at or existing.get("started_at"),
                "updated_utc": utc(),
            },
        )
        print(f"controller error: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
