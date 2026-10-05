#!/usr/bin/env python3
"""Export OpenFOAM native-cell VOF fields and face topology with pinned v2512.

The exporter reads only internal alpha.water/U and mesh topology. It never
corrects patch fields, advances a solver, or writes to the read-only case.
Each output directory must be new; failed attempts are preserved there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PINNED_IMAGE = "opencfd/openfoam-default:2512"
PINNED_IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
MESH_INPUTS = ("owner", "neighbour", "faces", "points", "boundary")
FIELD_INPUTS = ("alpha.water", "U")
SYSTEM_INPUTS = ("controlDict", "fvSchemes", "fvSolution")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _time_directory(root: Path, time_name: str) -> Path:
    time_value = float(time_name)
    matches = []
    for candidate in root.iterdir():
        if candidate.is_dir():
            try:
                value = float(candidate.name)
            except ValueError:
                continue
            if math.isclose(value, time_value, rel_tol=0.0, abs_tol=5e-10) and all(
                (candidate / field).is_file() for field in FIELD_INPUTS
            ):
                matches.append(candidate)
    exact = root / time_name
    if exact in matches:
        return exact
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected one saved time {time_value:g} with alpha.water/U under {root}; "
            f"found {[p.name for p in matches]}"
        )
    return matches[0]


def input_inventory(case_dir: Path, time_name: str, mpi_ranks: int) -> tuple[dict[str, str], str]:
    """Hash topology and selected fields before and after a read-only export."""
    paths: list[Path] = []
    paths.extend(case_dir / "system" / name for name in SYSTEM_INPUTS)
    selected_names: set[str] = set()
    if mpi_ranks > 1:
        processor_dirs = sorted(
            (path for path in case_dir.glob("processor[0-9]*") if path.is_dir()),
            key=lambda path: int(re.fullmatch(r"processor(\d+)", path.name).group(1)),
        )
        if len(processor_dirs) != mpi_ranks:
            raise ValueError(
                f"requested {mpi_ranks} MPI ranks but found {len(processor_dirs)} processor dirs"
            )
        for proc_dir in processor_dirs:
            mesh_dir = proc_dir / "constant" / "polyMesh"
            selected_time = _time_directory(proc_dir, time_name)
            selected_names.add(selected_time.name)
            paths.extend(mesh_dir / name for name in MESH_INPUTS)
            paths.append(mesh_dir / "cellProcAddressing")
            paths.extend(selected_time / name for name in FIELD_INPUTS)
    else:
        mesh_dir = case_dir / "constant" / "polyMesh"
        selected_time = _time_directory(case_dir, time_name)
        selected_names.add(selected_time.name)
        paths.extend(mesh_dir / name for name in MESH_INPUTS)
        paths.extend(selected_time / name for name in FIELD_INPUTS)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing required OpenFOAM inputs: {missing[:10]}")
    if len(selected_names) != 1:
        raise ValueError(
            f"ranks do not share one selected time directory: {sorted(selected_names)}"
        )
    return (
        {str(path.relative_to(case_dir)): sha256_file(path) for path in paths},
        next(iter(selected_names)),
    )


def _container_command(
    *,
    case_dir: Path,
    output_dir: Path,
    source_dir: Path,
    time_name: str,
    source_patch: str,
    mpi_ranks: int,
) -> list[str]:
    build = (
        "source /usr/lib/openfoam/openfoam2512/etc/bashrc; "
        "set -eo pipefail; "
        "mkdir -p /out/buildsrc /out/build-bin /out/raw; "
        "cp -a /src/. /out/buildsrc/; "
        "export FOAM_USER_APPBIN=/out/build-bin; "
        "cd /out/buildsrc; wmake; "
    )
    utility = [
        "/out/build-bin/exportNativeVof",
        "-case",
        "/case",
        "-snapshotName",
        time_name,
        "-sourcePatch",
        source_patch,
        "-outputDir",
        "/out/raw",
    ]
    if mpi_ranks > 1:
        utility = [
            "mpirun",
            "--allow-run-as-root",
            "--oversubscribe",
            "-np",
            str(mpi_ranks),
            *utility,
            "-parallel",
        ]
    shell = build + " ".join(shlex_quote(arg) for arg in utility)
    user = f"{os.getuid()}:{os.getgid()}"
    return [
        "docker",
        "run",
        "--rm",
        "--cpus=1",
        "--memory=12g",
        "--user",
        user,
        "-e",
        "HOME=/tmp",
        "-e",
        "OMPI_ALLOW_RUN_AS_ROOT=1",
        "-e",
        "OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1",
        "-v",
        f"{case_dir}:/case:ro",
        "-v",
        f"{source_dir}:/src:ro",
        "-v",
        f"{output_dir}:/out:rw",
        PINNED_IMAGE,
        "bash",
        "-lc",
        shell,
    ]


def shlex_quote(value: str) -> str:
    """Small strict shell quoting helper for the controlled generated argv."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def export_case(
    case_dir: Path,
    time_name: str,
    output_dir: Path,
    source_patch: str,
    mpi_ranks: int = 1,
) -> dict[str, Any]:
    case_dir = case_dir.resolve(strict=True)
    if not case_dir.is_dir():
        raise ValueError("--case-dir must be an OpenFOAM case directory")
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", source_patch):
        raise ValueError("source patch must be a simple OpenFOAM word")
    try:
        time_value = float(time_name)
    except ValueError as exc:
        raise ValueError("--time must be a numeric OpenFOAM time") from exc
    if not math.isfinite(time_value) or mpi_ranks < 1:
        raise ValueError("time must be finite and MPI rank count positive")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    source_dir = Path(__file__).resolve().parents[1] / "src" / "openfoam" / "exportNativeVof"
    before, selected_time_directory = input_inventory(case_dir, time_name, mpi_ranks)
    image_id = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", PINNED_IMAGE],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if image_id != PINNED_IMAGE_ID:
        raise RuntimeError(f"pinned OpenFOAM image ID mismatch: {image_id}")

    argv = _container_command(
        case_dir=case_dir,
        output_dir=output_dir,
        source_dir=source_dir,
        time_name=selected_time_directory,
        source_patch=source_patch,
        mpi_ranks=mpi_ranks,
    )
    started = datetime.now(UTC).isoformat()
    log_path = output_dir / "export.log"
    return_code = 1
    error: str | None = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=False)
        return_code = result.returncode
        if return_code != 0:
            error = f"container exporter exited {return_code}"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        return_code = 1
    finally:
        after, selected_after_directory = input_inventory(case_dir, time_name, mpi_ranks)
        status: dict[str, Any] = {
            "schema": "dash8-native-vof-export-attempt-v1",
            "status": "complete" if return_code == 0 else "failed",
            "started_utc": started,
            "finished_utc": datetime.now(UTC).isoformat(),
            "case_directory": str(case_dir),
            "selected_time_requested": time_name,
            "selected_time_directory": selected_time_directory,
            "source_patch": source_patch,
            "mpi_ranks": mpi_ranks,
            "solver_or_utility": "read-only OpenFOAM utility; no solver launched",
            "image": PINNED_IMAGE,
            "image_id": image_id,
            "cpu_limit": 1,
            "memory_limit": "12g",
            "container_argv": argv,
            "input_sha256_before": before,
            "input_sha256_after": after,
            "input_hashes_unchanged": before == after,
            "selected_time_directory_unchanged": selected_time_directory
            == selected_after_directory,
            "return_code": return_code,
            "error": error,
            "log": str(log_path),
            "raw_directory": str(output_dir / "raw"),
        }
        (output_dir / "export_attempt.json").write_text(
            json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if return_code != 0:
        raise RuntimeError(f"native exporter failed; see {log_path}")
    if before != after:
        raise RuntimeError(f"input case changed during export; hashes in {output_dir}")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time", required=True, help="numeric saved OpenFOAM time")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="new immutable export bundle"
    )
    parser.add_argument("--source-patch", default="dash8Opening")
    parser.add_argument(
        "--mpi-ranks",
        type=int,
        default=1,
        help="1 for serial; >1 reads processor* with cellProcAddressing",
    )
    args = parser.parse_args(argv)
    try:
        result = export_case(
            args.case_dir, args.time, args.output_dir, args.source_patch, args.mpi_ranks
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"native VOF export failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "status",
                    "case_directory",
                    "selected_time_requested",
                    "mpi_ranks",
                    "raw_directory",
                    "input_hashes_unchanged",
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
