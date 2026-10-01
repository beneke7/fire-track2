#!/usr/bin/env python3
"""Run the provisional Rouaix E1 Case 1 mesh utilities only.

This is an exploratory mesh-preparation probe. It does not run interIsoFoam,
score the paper curves, or make a formal E1 gate decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_REL = Path("cases/e1_rouaix_case1_static")
PACKAGE = ROOT / PACKAGE_REL
EXPERIMENT_REL = Path("experiments/E1_ROUAIX_CASE1_STATIC_PREPARATION.md")
RUNS_ROOT = ROOT / "results" / "runs"
IMAGE = "opencfd/openfoam-default:2512"
OPENFOAM_BASHRC = "/usr/lib/openfoam/openfoam2512/etc/bashrc"

sys.path.insert(0, str(ROOT / "cases"))
from e1_rouaix_case1_static.static_preparation import IMAGE_ID as PINNED_IMAGE_ID  # noqa: E402

STAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("blockMesh", ("blockMesh",)),
    ("topoSet", ("topoSet",)),
    ("createPatch", ("createPatch", "-overwrite")),
    ("snappyHexMesh", ("snappyHexMesh", "-overwrite")),
    ("checkMesh", ("checkMesh", "-allTopology", "-allGeometry")),
)
STAGE_MARKER = re.compile(r"^ROUAIX_STAGE_EXIT stage=([A-Za-z][A-Za-z0-9]*) code=(-?\d+)\s*$", re.M)
SETUP_MARKER = re.compile(r"^ROUAIX_OPENFOAM_SETUP_EXIT code=(-?\d+)\s*$", re.M)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{12,64}$")

SOURCE_FILES = (
    "CASE_SHA256SUMS",
    "ALPHA_CAPTURE_MAP.md",
    "__init__.py",
    "prepare_case.py",
    "static_preparation.py",
)


class TerminationRequested(Exception):
    def __init__(self, signum: int):
        self.signum = signum


def _termination_handler(signum: int, _frame: object) -> None:
    raise TerminationRequested(signum)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _positive_seconds(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive number of seconds") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number of seconds")
    return parsed


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="new, unique run bundle name")
    parser.add_argument("--cpus", type=_positive_int, default=20, help="Docker CPU quota")
    parser.add_argument("--memory-gib", type=_positive_int, default=48, help="Docker memory limit")
    parser.add_argument("--timeout-s", type=_positive_seconds, default=1800.0)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="snapshot and clone inputs without inspecting or launching Docker",
    )
    args = parser.parse_args(argv)
    if not RUN_ID_RE.fullmatch(args.run_id) or args.run_id in {".", ".."}:
        parser.error(
            "--run-id must contain only letters, digits, '.', '_' or '-' and start alphanumeric"
        )
    return args


def _source_paths() -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for directory in (PACKAGE / "case", PACKAGE / "geometry"):
        if not directory.is_dir():
            raise FileNotFoundError(f"required source directory is missing: {directory}")
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"source tree contains a symlink: {path}")
            if path.is_file():
                sources[path.relative_to(ROOT).as_posix()] = path
    for filename in SOURCE_FILES:
        path = PACKAGE / filename
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"required source file is missing or not regular: {path}")
        sources[path.relative_to(ROOT).as_posix()] = path
    experiment = ROOT / EXPERIMENT_REL
    if not experiment.is_file() or experiment.is_symlink():
        raise FileNotFoundError(
            f"required experiment record is missing or not regular: {experiment}"
        )
    sources[experiment.relative_to(ROOT).as_posix()] = experiment
    return sources


def _verify_case_manifest(sources: dict[str, Path]) -> None:
    manifest_path = PACKAGE / "CASE_SHA256SUMS"
    expected: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{64}", fields[0]):
            raise ValueError(f"malformed case checksum row: {line!r}")
        relative = (PACKAGE_REL / fields[1].removeprefix("./")).as_posix()
        if relative in expected:
            raise ValueError(f"duplicate case checksum entry: {relative}")
        expected[relative] = fields[0]
    actual_paths = {
        name
        for name in sources
        if name.startswith(
            (f"{PACKAGE_REL.as_posix()}/case/", f"{PACKAGE_REL.as_posix()}/geometry/")
        )
    }
    if set(expected) != actual_paths:
        missing = sorted(set(expected) - actual_paths)
        extra = sorted(actual_paths - set(expected))
        raise ValueError(f"case checksum file set differs; missing={missing}, extra={extra}")
    for relative, expected_hash in expected.items():
        actual_hash = _sha256(sources[relative])
        if actual_hash != expected_hash:
            raise ValueError(
                f"case checksum mismatch for {relative}: {actual_hash} != {expected_hash}"
            )


def _git_metadata() -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "revision": None,
        "dirty": None,
        "status_porcelain": [],
        "error": None,
    }
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if revision.returncode == 0:
            metadata["revision"] = revision.stdout.strip()
        if status.returncode == 0:
            lines = [line for line in status.stdout.splitlines() if line]
            metadata["status_porcelain"] = lines
            metadata["dirty"] = bool(lines)
        else:
            metadata["error"] = status.stderr.strip() or f"git status exited {status.returncode}"
    except OSError as error:
        metadata["error"] = str(error)
    return metadata


def _initial_manifest(args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": args.run_id,
        "status": "preparing",
        "created_utc": _utc_now(),
        "experiment": "Exploratory Rouaix et al. (2023) E1 Case 1 static mesh preparation",
        "scope": {
            "mesh_only": True,
            "solver_run": False,
            "paper_curve_scoring": False,
            "formal_e1_gate_decision": False,
            "geometry_classification": None,
        },
        "allocation": {
            "cpus": args.cpus,
            "memory_gib": args.memory_gib,
            "timeout_s": args.timeout_s,
            "prepare_only": args.prepare_only,
        },
        "openfoam_image": {
            "reference": IMAGE,
            "expected_image_id": PINNED_IMAGE_ID,
            "resolved_image_id": None,
        },
        "git": _git_metadata(),
        "paths": {
            "working_case": "case",
            "geometry": "geometry",
            "source_snapshot": "source-snapshot",
            "manifest": "manifest.json",
        },
        "source_inputs_sha256": {},
        "runner_sha256": _sha256(Path(__file__).resolve()),
        "stages": {name: {"command": list(command), "exit_code": None} for name, command in STAGES},
        "mesh": {
            "counts": {},
            "cell_count": None,
            "boundary_patches": {},
            "final_check_result": "not_run",
        },
        "setup_failure": None,
        "timeout": False,
        "container": {"name": f"rouaix-mesh-{args.run_id}", "id": None, "cleanup": "not_needed"},
        "wall_time_s": None,
        "mesh_container_wall_time_s": None,
        "exit_code": None,
        "completed_utc": None,
        "evidence": {
            "setup_log": "setup.log",
            "openfoam_log": "openfoam-console.log",
            "cleanup_log": "container-cleanup.log",
        },
    }


def _write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    destination = run_dir / "manifest.json"
    temporary = run_dir / ".manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)


def _prepare_inputs(run_dir: Path, manifest: dict[str, Any]) -> None:
    sources = _source_paths()
    _verify_case_manifest(sources)
    for relative, source in sources.items():
        snapshot = run_dir / "source-snapshot" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(source.read_bytes())
    for directory in ("case", "geometry"):
        source = PACKAGE / directory
        destination = run_dir / directory
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"source tree contains a symlink: {path}")
        shutil.copytree(source, destination)
    hashes = {relative: _sha256(path) for relative, path in sorted(sources.items())}
    for relative, expected_hash in hashes.items():
        snapshot = run_dir / "source-snapshot" / relative
        if _sha256(snapshot) != expected_hash:
            raise ValueError(f"source snapshot hash mismatch for {relative}")
        prefix = f"{PACKAGE_REL.as_posix()}/"
        if relative.startswith(prefix) and relative[len(prefix) :].startswith(
            ("case/", "geometry/")
        ):
            working_copy = run_dir / relative[len(prefix) :]
            if _sha256(working_copy) != expected_hash:
                raise ValueError(f"working copy hash mismatch for {relative}")
    manifest["source_inputs_sha256"] = hashes
    domain = json.loads((run_dir / "geometry" / "domain.json").read_text(encoding="utf-8"))
    geometry = domain.get("curved_aircraft_wall", {})
    manifest["scope"]["geometry_classification"] = geometry.get(
        "classification", "unclassified geometry"
    )
    manifest["mesh"]["declared_background_cells"] = domain.get("mesh", {}).get(
        "background_cells", "not declared"
    )


def _resolve_image_id(run_dir: Path) -> tuple[str, str]:
    command = ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20)
        transcript = (
            f"$ {' '.join(command)}\nreturn_code={result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    except subprocess.TimeoutExpired as error:
        transcript = f"$ {' '.join(command)}\nerror={error}\n"
        (run_dir / "setup.log").write_text(transcript, encoding="utf-8")
        raise
    except OSError as error:
        transcript = f"$ {' '.join(command)}\nerror={error}\n"
        (run_dir / "setup.log").write_text(transcript, encoding="utf-8")
        raise RuntimeError(f"could not inspect Docker image {IMAGE}: {error}") from error
    (run_dir / "setup.log").write_text(transcript, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(
            f"Docker image {IMAGE!r} is not available locally (exit {result.returncode})"
        )
    resolved = result.stdout.strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", resolved):
        raise RuntimeError(f"Docker returned an invalid image ID: {resolved!r}")
    if resolved != PINNED_IMAGE_ID:
        raise RuntimeError(
            f"Docker image ID mismatch: expected {PINNED_IMAGE_ID}, found {resolved}"
        )
    return resolved, transcript


def _openfoam_setup_script(bashrc_path: str = OPENFOAM_BASHRC) -> str:
    return "; ".join(
        (
            "set +e +u",
            "source_status=0",
            f"source {shlex.quote(bashrc_path)} || source_status=$?",
            "set +e +u",
            "printf 'ROUAIX_OPENFOAM_SETUP_EXIT code=%s\\n' \"$source_status\"",
            'if [ "$source_status" -ne 0 ]; then exit "$source_status"; fi',
            "set -euo pipefail",
        )
    )


def _shell_script() -> str:
    lines = [
        _openfoam_setup_script(),
        'run_stage() { local stage="$1"; shift; local code=0; "$@" || code=$?; printf \'ROUAIX_STAGE_EXIT stage=%s code=%s\\n\' "$stage" "$code"; return "$code"; }',
    ]
    lines.extend(f"run_stage {name} {' '.join(command)}" for name, command in STAGES)
    return "; ".join(lines)


def _docker_command(run_dir: Path, args: argparse.Namespace) -> list[str]:
    cidfile = run_dir / "container.cid"
    if cidfile.exists():
        raise FileExistsError(f"refusing to reuse Docker cidfile: {cidfile}")
    command = [
        "docker",
        "run",
        "--rm",
        f"--name=rouaix-mesh-{args.run_id}",
        f"--cidfile={cidfile}",
        f"--cpus={args.cpus}",
        f"--memory={args.memory_gib}g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={run_dir / 'case'},dst=/case",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        IMAGE,
        "-c",
        _shell_script(),
    ]
    return command


def _container_id(cidfile: Path) -> str | None:
    try:
        container_id = cidfile.read_text(encoding="ascii").strip()
    except OSError:
        return None
    return container_id if CONTAINER_ID_RE.fullmatch(container_id) else None


def _remove_own_container(run_dir: Path) -> tuple[str, str]:
    container_id = _container_id(run_dir / "container.cid")
    if container_id is None:
        return (
            "cidfile_missing_or_invalid",
            "No verified container ID was written; no container was removed.\n",
        )
    command = ["docker", "rm", "--force", container_id]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20)
        transcript = (
            f"$ {' '.join(command)}\nreturn_code={result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        if result.returncode == 0:
            return "removed", transcript
        if "no such container" in (result.stdout + result.stderr).lower():
            return "already_removed", transcript
        return "remove_failed", transcript
    except (OSError, subprocess.TimeoutExpired) as error:
        return "remove_failed", f"$ {' '.join(command)}\nerror={error}\n"


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_docker(
    run_dir: Path, args: argparse.Namespace, manifest: dict[str, Any]
) -> tuple[int, bool, bool]:
    command = _docker_command(run_dir, args)
    manifest["container"]["command"] = command
    manifest["container"]["name"] = f"rouaix-mesh-{args.run_id}"
    started = time.monotonic()
    timed_out = False
    interrupted = False
    return_code: int
    log_path = run_dir / "openfoam-console.log"
    try:
        with log_path.open("wb") as log_stream:
            process = subprocess.Popen(command, stdout=log_stream, stderr=subprocess.STDOUT)
            try:
                return_code = process.wait(timeout=args.timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                _stop_process(process)
                return_code = 124
            except TerminationRequested as error:
                interrupted = True
                _stop_process(process)
                return_code = 128 + error.signum
    except TerminationRequested as error:
        interrupted = True
        return_code = 128 + error.signum
    except OSError as error:
        log_path.write_text(f"Could not start Docker: {error}\n", encoding="utf-8")
        return_code = 127
    finally:
        state, transcript = _remove_own_container(run_dir)
        (run_dir / "container-cleanup.log").write_text(transcript, encoding="utf-8")
        manifest["container"]["id"] = _container_id(run_dir / "container.cid")
        manifest["container"]["cleanup"] = state
    manifest["mesh_container_wall_time_s"] = round(time.monotonic() - started, 6)
    manifest["timeout"] = timed_out
    return return_code, timed_out, interrupted


def _parse_stage_results(text: str) -> tuple[dict[str, int | None], int | None]:
    codes: dict[str, int | None] = {name: None for name, _ in STAGES}
    for match in STAGE_MARKER.finditer(text):
        if match.group(1) in codes:
            codes[match.group(1)] = int(match.group(2))
    setup = SETUP_MARKER.search(text)
    return codes, int(setup.group(1)) if setup else None


def _parse_mesh_counts(text: str) -> dict[str, int]:
    patterns = {
        "points": r"(?mi)^\s*points\s*:\s*(\d+)\b",
        "faces": r"(?mi)^\s*faces\s*:\s*(\d+)\b",
        "internal_faces": r"(?mi)^\s*internal faces\s*:\s*(\d+)\b",
        "cells": r"(?mi)^\s*cells\s*:\s*(\d+)\b",
    }
    counts: dict[str, int] = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if matches:
            counts[name] = int(matches[-1])
    if "cells" not in counts:
        matches = re.findall(r"(?mi)^\s*nCells\s*[:=]\s*(\d+)\b", text)
        if matches:
            counts["cells"] = int(matches[-1])
    return counts


def _parse_boundary_patches(boundary_path: Path) -> dict[str, dict[str, Any]]:
    if not boundary_path.is_file():
        return {}
    text = boundary_path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    patches: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\{", text):
        name = match.group(1)
        opening = text.find("{", match.start())
        depth = 0
        closing = None
        for index in range(opening, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        if closing is None:
            continue
        body = text[opening + 1 : closing]
        faces = re.search(r"(?m)^\s*nFaces\s+(\d+)\s*;", body)
        patch_type = re.search(r"(?m)^\s*type\s+([^;]+);", body)
        if faces:
            patches[name] = {
                "n_faces": int(faces.group(1)),
                "type": patch_type.group(1).strip() if patch_type else None,
            }
    return patches


def _record_mesh_results(run_dir: Path, manifest: dict[str, Any], return_code: int) -> None:
    log_path = run_dir / "openfoam-console.log"
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    codes, setup_code = _parse_stage_results(text)
    for stage, code in codes.items():
        manifest["stages"][stage]["exit_code"] = code
    manifest["openfoam_setup_exit_code"] = setup_code
    counts = _parse_mesh_counts(text)
    manifest["mesh"]["counts"] = counts
    manifest["mesh"]["cell_count"] = counts.get("cells")
    manifest["mesh"]["boundary_patches"] = _parse_boundary_patches(
        run_dir / "case" / "constant" / "polyMesh" / "boundary"
    )
    check_code = codes.get("checkMesh")
    failed_checks = re.search(r"(?mi)^\s*Failed\s+(\d+)\s+mesh checks?\s*\.", text)
    mesh_ok = re.search(r"(?mi)^\s*Mesh OK\.\s*$", text)
    if check_code is None:
        result = "not_run"
    elif check_code != 0 or (failed_checks and int(failed_checks.group(1)) > 0):
        result = "failed"
    elif mesh_ok:
        result = "passed"
    else:
        result = "indeterminate_missing_checkMesh_summary"
    manifest["mesh"]["final_check_result"] = result
    manifest["container"]["exit_code"] = return_code


def _run(args: argparse.Namespace, *, runs_root: Path | None = None) -> int:
    runs_root = RUNS_ROOT if runs_root is None else runs_root
    run_dir = runs_root / args.run_id
    runs_root.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir(exist_ok=False)
    except FileExistsError:
        print(f"Refusing to overwrite existing run bundle: {run_dir}", file=sys.stderr)
        return 2
    started = time.monotonic()
    manifest = _initial_manifest(args, run_dir)
    _write_manifest(run_dir, manifest)
    exit_code = 1
    try:
        _prepare_inputs(run_dir, manifest)
        _write_manifest(run_dir, manifest)
        if args.prepare_only:
            manifest["status"] = "prepared_only"
            exit_code = 0
        else:
            manifest["status"] = "setting_up"
            _write_manifest(run_dir, manifest)
            try:
                image_id, _transcript = _resolve_image_id(run_dir)
                manifest["openfoam_image"]["resolved_image_id"] = image_id
            except subprocess.TimeoutExpired as error:
                manifest["status"] = "setup_timeout"
                manifest["setup_failure"] = f"Docker image inspection timed out: {error}"
                manifest["timeout"] = True
                exit_code = 124
            except (OSError, RuntimeError) as error:
                manifest["status"] = "setup_failed"
                manifest["setup_failure"] = str(error)
                exit_code = 2
            else:
                manifest["status"] = "running_mesh_utilities"
                _write_manifest(run_dir, manifest)
                old_handlers = {
                    signum: signal.signal(signum, _termination_handler)
                    for signum in (signal.SIGTERM, signal.SIGINT)
                }
                try:
                    code, timed_out, interrupted = _run_docker(run_dir, args, manifest)
                finally:
                    for signum, handler in old_handlers.items():
                        signal.signal(signum, handler)
                _record_mesh_results(run_dir, manifest, code)
                if timed_out:
                    manifest["status"] = "timeout"
                    exit_code = 124
                elif interrupted:
                    manifest["status"] = "interrupted"
                    exit_code = code
                elif manifest["openfoam_setup_exit_code"] not in (None, 0):
                    manifest["status"] = "setup_failed"
                    manifest["setup_failure"] = (
                        "OpenFOAM environment setup failed inside the pinned image; "
                        f"exit={manifest['openfoam_setup_exit_code']}"
                    )
                    exit_code = code if code != 0 else 2
                elif manifest["openfoam_setup_exit_code"] is None and code != 0:
                    manifest["status"] = "setup_failed"
                    manifest["setup_failure"] = (
                        "Docker command ended before the OpenFOAM setup marker; "
                        "inspect setup.log and openfoam-console.log"
                    )
                    exit_code = code
                elif code == 0 and manifest["mesh"]["final_check_result"] == "passed":
                    manifest["status"] = "mesh_check_passed_exploratory_only"
                    exit_code = 0
                else:
                    manifest["status"] = "mesh_probe_failed_or_incomplete"
                    exit_code = code if code != 0 else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        manifest["status"] = "setup_failed"
        manifest["setup_failure"] = str(error)
        exit_code = 2
    finally:
        manifest["exit_code"] = exit_code
        manifest["completed_utc"] = _utc_now()
        manifest["wall_time_s"] = round(time.monotonic() - started, 6)
        _write_manifest(run_dir, manifest)
    print(f"Run bundle: {run_dir}")
    print(f"Status: {manifest['status']}; exit={exit_code}")
    if manifest["mesh"].get("cell_count") is not None:
        print(f"Generated cells: {manifest['mesh']['cell_count']}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    return _run(_arguments(argv))


if __name__ == "__main__":
    raise SystemExit(main())
