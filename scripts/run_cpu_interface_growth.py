#!/usr/bin/env python3
"""Run an exploratory periodic water-air shear-layer instability test on CPU."""

from __future__ import annotations

import argparse
import csv
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

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "opencfd/openfoam-default:2512"
LENGTHS = (0.12, 0.06, 0.12)
WATER_RHO = 1000.0
AIR_RHO = 1.2
WATER_NU = 1.0e-6
AIR_NU = 1.5e-5
WATER_BOTTOM = 0.03
WATER_TOP = 0.09
SHEAR_DELTA = 0.0075
SEED_AMPLITUDE = 0.00075
MODE_NUMBER = 1
FIT_WINDOW_S = (0.002, 0.008)
ADDED_NU = 0.01
WRITE_INTERVAL_PILOT_S = 0.00025
WRITE_INTERVAL_SWEEP_S = 0.0005

# V2 uses a separate, better resolved case family.  Keep the V1 constants and
# helpers above unchanged so old input records and run snapshots remain exact.
V2_LENGTHS = (0.12, 0.06, 0.12)
V2_WATER_BOTTOM = 0.03
V2_WATER_TOP = 0.09
V2_SHEAR_DELTA = 0.0075
V2_SEED_AMPLITUDE = 0.00015
V2_PROFILE_DT_S = 4.0e-6
V2_PROFILE_STEPS = 50
V2_PROFILE_WRITE_STEPS = 10
V2_FIT_WINDOW_S = (0.002, 0.008)


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def field_header(object_name: str, field_class: str, location: str = "0") -> str:
    return (
        "FoamFile\n{\n"
        "    version 2.0;\n"
        "    format ascii;\n"
        f"    class {field_class};\n"
        f'    location "{location}";\n'
        f"    object {object_name};\n"
        "}\n\n"
    )


def cyclic_boundary_field() -> str:
    return """boundaryField
{
    xMin { type cyclic; }
    xMax { type cyclic; }
    yMin { type cyclic; }
    yMax { type cyclic; }
    zMin { type cyclic; }
    zMax { type cyclic; }
}
"""


def block_mesh_dict(nx: int, ny: int, nz: int) -> str:
    lx, ly, lz = LENGTHS
    return f"""{field_header("blockMeshDict", "dictionary", "system")}convertToMeters 1;
vertices
(
    (0 0 0)
    ({lx:.16g} 0 0)
    ({lx:.16g} {ly:.16g} 0)
    (0 {ly:.16g} 0)
    (0 0 {lz:.16g})
    ({lx:.16g} 0 {lz:.16g})
    ({lx:.16g} {ly:.16g} {lz:.16g})
    (0 {ly:.16g} {lz:.16g})
);
blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);
edges ();
boundary
(
    xMin {{ type cyclic; neighbourPatch xMax; transform translational; separationVector ({lx:.16g} 0 0); faces ((0 4 7 3)); }}
    xMax {{ type cyclic; neighbourPatch xMin; transform translational; separationVector (-{lx:.16g} 0 0); faces ((1 2 6 5)); }}
    yMin {{ type cyclic; neighbourPatch yMax; transform translational; separationVector (0 {ly:.16g} 0); faces ((0 1 5 4)); }}
    yMax {{ type cyclic; neighbourPatch yMin; transform translational; separationVector (0 -{ly:.16g} 0); faces ((3 7 6 2)); }}
    zMin {{ type cyclic; neighbourPatch zMax; transform translational; separationVector (0 0 {lz:.16g}); faces ((0 3 2 1)); }}
    zMax {{ type cyclic; neighbourPatch zMin; transform translational; separationVector (0 0 -{lz:.16g}); faces ((4 5 6 7)); }}
);
mergePatchPairs ();
"""


def control_dict(horizon_s: float, write_interval_s: float) -> str:
    return f"""{field_header("controlDict", "dictionary", "system")}application interIsoFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {horizon_s:.16g};
deltaT 1e-6;
adjustTimeStep yes;
maxCo 0.25;
maxAlphaCo 0.15;
maxDeltaT 2e-5;
writeControl runTime;
writeInterval {write_interval_s:.16g};
purgeWrite 0;
writeFormat ascii;
writePrecision 12;
writeCompression off;
timeFormat general;
timePrecision 10;
runTimeModifiable false;
"""


def fv_schemes() -> str:
    return f"""{field_header("fvSchemes", "dictionary", "system")}ddtSchemes {{ default Euler; }}
gradSchemes {{ default Gauss linear; }}
divSchemes
{{
    default none;
    div(rhoPhi,U) Gauss linearUpwind grad(U);
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}}
laplacianSchemes {{ default Gauss linear corrected; }}
interpolationSchemes {{ default linear; }}
snGradSchemes {{ default corrected; }}
fluxRequired {{ default no; p_rgh; pcorr; alpha.water; }}
"""


def fv_solution() -> str:
    return f"""{field_header("fvSolution", "dictionary", "system")}solvers
{{
    "alpha.water.*"
    {{
        isoFaceTol 1e-10;
        surfCellTol 1e-10;
        nAlphaBounds 5;
        snapTol 0;
        clip true;
        cAlpha 1;
        nAlphaSubCycles 1;
        reconstructionScheme isoAlpha;
    }}
    "pcorr.*" {{ solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0; }}
    p_rgh {{ solver GAMG; smoother DICGaussSeidel; tolerance 1e-9; relTol 0.02; }}
    p_rghFinal {{ $p_rgh; tolerance 1e-9; relTol 0; }}
    U {{ solver PBiCGStab; preconditioner DILU; tolerance 1e-8; relTol 0; }}
    UFinal {{ $U; relTol 0; }}
}}
PIMPLE
{{
    momentumPredictor yes;
    nOuterCorrectors 1;
    nCorrectors 3;
    nNonOrthogonalCorrectors 0;
    pRefCell 0;
    pRefValue 0;
}}
"""


def alpha_seed(nx: int, ny: int, nz: int) -> np.ndarray:
    """Subcell-integrate a periodic sinusoidally displaced water slab."""
    lx, _, lz = LENGTHS
    dx = lx / nx
    dz = lz / nz
    nodes, weights = np.polynomial.legendre.leggauss(12)
    alpha = np.zeros((nz, ny, nx), dtype=np.float64)
    z_low = np.arange(nz, dtype=np.float64) * dz
    z_high = z_low + dz
    mode_k = 2.0 * math.pi * MODE_NUMBER / lx
    for i in range(nx):
        x_mid = (i + 0.5) * dx
        x_nodes = x_mid + 0.5 * dx * nodes
        displacement = SEED_AMPLITUDE * np.sin(mode_k * x_nodes)
        lower = WATER_BOTTOM + displacement
        upper = WATER_TOP + displacement
        overlap = (
            np.maximum(
                0.0,
                np.minimum(z_high[:, None], upper[None, :])
                - np.maximum(z_low[:, None], lower[None, :]),
            )
            / dz
        )
        alpha[:, :, i] = (overlap @ weights / 2.0)[:, None]
    return np.clip(alpha, 0.0, 1.0)


def initial_velocity(nx: int, ny: int, nz: int, variant: str) -> np.ndarray:
    """Create a divergence-free uniform-advection or finite tanh-shear field."""
    _, _, lz = LENGTHS
    dz = lz / nz
    zc = (np.arange(nz, dtype=np.float64) + 0.5) * dz
    if variant == "advection_control":
        ux = np.full(nz, 25.0)
    elif variant in {"molecular_shear", "added_viscosity_shear"}:
        ux = (
            50.0
            - 25.0 * np.tanh((zc - WATER_BOTTOM) / SHEAR_DELTA)
            + 25.0 * np.tanh((zc - WATER_TOP) / SHEAR_DELTA)
        )
    else:
        raise ValueError(f"unknown flow variant: {variant}")
    velocity = np.zeros((nz, ny, nx, 3), dtype=np.float64)
    velocity[..., 0] = ux[:, None, None]
    return velocity


def write_scalar_field(path: Path, name: str, values: np.ndarray, location: str = "0") -> None:
    flat = values.ravel(order="C")
    body = "\n".join(f"{v:.16g}" for v in flat)
    path.write_text(
        field_header(name, "volScalarField", location)
        + "dimensions [0 0 0 0 0 0 0];\n"
        + f"internalField nonuniform List<scalar>\n{flat.size}\n(\n{body}\n);\n"
        + cyclic_boundary_field()
    )


def write_vector_field(path: Path, name: str, values: np.ndarray, location: str = "0") -> None:
    flat = values.reshape((-1, 3), order="C")
    body = "\n".join(f"({u:.16g} {v:.16g} {w:.16g})" for u, v, w in flat)
    path.write_text(
        field_header(name, "volVectorField", location)
        + "dimensions [0 1 -1 0 0 0 0];\n"
        + f"internalField nonuniform List<vector>\n{flat.shape[0]}\n(\n{body}\n);\n"
        + cyclic_boundary_field()
    )


def transport_properties(nu_add: float) -> str:
    nu_water = WATER_NU + nu_add
    nu_air = AIR_NU + nu_add
    return f"""{field_header("transportProperties", "dictionary", "constant")}phases (water air);
water {{ transportModel Newtonian; nu {nu_water:.16g}; rho {WATER_RHO:.16g}; }}
air {{ transportModel Newtonian; nu {nu_air:.16g}; rho {AIR_RHO:.16g}; }}
sigma 0;
"""


def create_case(case_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    nx, ny, nz = case["mesh"]
    system = case_dir / "system"
    constant = case_dir / "constant"
    initial = case_dir / "0"
    for path in (system, constant, initial):
        path.mkdir(parents=True, exist_ok=True)
    (system / "blockMeshDict").write_text(block_mesh_dict(nx, ny, nz))
    (system / "controlDict").write_text(control_dict(case["horizon_s"], case["write_interval_s"]))
    (system / "fvSchemes").write_text(fv_schemes())
    (system / "fvSolution").write_text(fv_solution())
    (constant / "transportProperties").write_text(transport_properties(case["nu_add_m2_s"]))
    (constant / "turbulenceProperties").write_text(
        f"""{field_header("turbulenceProperties", "dictionary", "constant")}simulationType laminar;
"""
    )
    (constant / "g").write_text(
        f"""{field_header("g", "uniformDimensionedVectorField", "constant")}dimensions [0 1 -2 0 0 0 0];
value (0 0 0);
"""
    )
    alpha = alpha_seed(nx, ny, nz)
    velocity = initial_velocity(nx, ny, nz, case["variant"])
    write_scalar_field(initial / "alpha.water", "alpha.water", alpha)
    write_vector_field(initial / "U", "U", velocity)
    (initial / "p_rgh").write_text(
        f"""{field_header("p_rgh", "volScalarField")}dimensions [1 -1 -2 0 0 0 0];
internalField uniform 0;
{cyclic_boundary_field()}"""
    )
    lx, ly, lz = LENGTHS
    cell_count = nx * ny * nz
    expected_volume = lx * ly * (WATER_TOP - WATER_BOTTOM)
    initial_volume = float(alpha.sum() * (lx / nx) * (ly / ny) * (lz / nz))
    metadata = {
        **case,
        "cell_count": cell_count,
        "cell_size_m": [lx / nx, ly / ny, lz / nz],
        "interface_seed": "both water-film interfaces: eta=0.00075*sin(2*pi*x/0.12), in phase",
        "alpha_initialization": "12-point Gauss-Legendre subcell integration in x; exact z-overlap per quadrature point",
        "expected_water_volume_m3": expected_volume,
        "initial_water_volume_m3": initial_volume,
        "initial_water_volume_relative_error": (initial_volume - expected_volume) / expected_volume,
        "initial_alpha_min": float(alpha.min()),
        "initial_alpha_max": float(alpha.max()),
        "boundary_conditions": "periodic/cyclic in all three axes",
        "gravity_m_s2": [0.0, 0.0, 0.0],
        "surface_tension_N_m": 0.0,
        "phase_density_kg_m3": {"water": WATER_RHO, "air": AIR_RHO},
        "water_to_air_density_ratio": WATER_RHO / AIR_RHO,
        "molecular_kinematic_viscosity_m2_s": {
            "water": WATER_NU,
            "air": AIR_NU,
        },
        "added_kinematic_viscosity_m2_s_each_phase": case["nu_add_m2_s"],
        "effective_kinematic_viscosity_m2_s": {
            "water": WATER_NU + case["nu_add_m2_s"],
            "air": AIR_NU + case["nu_add_m2_s"],
        },
        "effective_dynamic_viscosity_Pa_s": {
            "water": WATER_RHO * (WATER_NU + case["nu_add_m2_s"]),
            "air": AIR_RHO * (AIR_NU + case["nu_add_m2_s"]),
        },
        "turbulence_model": "laminar; constant nu_add is a damping surrogate, not RANS",
        "fit_window_s": list(FIT_WINDOW_S),
    }
    write_json(case_dir / "case-inputs.json", metadata)
    return metadata


def input_hashes(case_dir: Path) -> dict[str, str]:
    return {
        str(path.relative_to(case_dir)): sha256(path)
        for path in sorted(case_dir.rglob("*"))
        if path.is_file()
    }


def run_shell(mpi_ranks: int | None = None) -> str:
    if mpi_ranks is not None:
        return f"""set +e +u
source /usr/lib/openfoam/openfoam2512/etc/bashrc
setup_code=$?
if [ "$setup_code" -ne 0 ]; then exit "$setup_code"; fi
set -euo pipefail
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
blockMesh > log.blockMesh 2>&1 || {{ cat log.blockMesh; exit 10; }}
checkMesh -allTopology -allGeometry > log.checkMesh 2>&1 || {{ cat log.checkMesh; exit 11; }}
grep -q 'Mesh OK.' log.checkMesh || {{ cat log.checkMesh; exit 12; }}
decomposePar -force > log.decomposePar 2>&1 || {{ tail -n 100 log.decomposePar; exit 14; }}
mpirun --oversubscribe -np {mpi_ranks} interIsoFoam -parallel > log.interIsoFoam 2>&1 || {{ tail -n 120 log.interIsoFoam; exit 13; }}
reconstructPar -fields '(alpha.water U p_rgh divPhi phi)' > log.reconstructPar 2>&1 || {{ tail -n 100 log.reconstructPar; exit 15; }}
tail -n 30 log.interIsoFoam
"""
    return """set +e +u
source /usr/lib/openfoam/openfoam2512/etc/bashrc
setup_code=$?
if [ "$setup_code" -ne 0 ]; then exit "$setup_code"; fi
set -euo pipefail
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
blockMesh > log.blockMesh 2>&1 || { cat log.blockMesh; exit 10; }
checkMesh -allTopology -allGeometry > log.checkMesh 2>&1 || { cat log.checkMesh; exit 11; }
grep -q 'Mesh OK.' log.checkMesh || { cat log.checkMesh; exit 12; }
interIsoFoam > log.interIsoFoam 2>&1 || { tail -n 120 log.interIsoFoam; exit 13; }
tail -n 30 log.interIsoFoam
"""


def docker_image_id() -> str:
    return subprocess.check_output(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], text=True
    ).strip()


def docker_stats(container_id: str) -> str | None:
    try:
        completed = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", container_id],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def docker_memory_usage_bytes(memory_usage: str) -> int | None:
    match = re.match(r"\s*([0-9.]+)\s*(B|kB|KB|KiB|MB|MiB|GB|GiB)\b", memory_usage)
    if not match:
        return None
    unit_scale = {
        "B": 1,
        "kB": 1000,
        "KB": 1024,
        "KiB": 1024,
        "MB": 1000**2,
        "MiB": 1024**2,
        "GB": 1000**3,
        "GiB": 1024**3,
    }
    return int(float(match.group(1)) * unit_scale[match.group(2)])


def summarize_docker_resources(resources_path: Path) -> dict[str, Any]:
    cpu_percent: list[float] = []
    memory_bytes: list[int] = []
    sample_count = 0
    if resources_path.is_file():
        for line in resources_path.read_text(errors="replace").splitlines():
            try:
                record = json.loads(line)
                stats = json.loads(record["docker_stats"])
                cpu_percent.append(float(stats["CPUPerc"].rstrip("%")))
                parsed_memory = docker_memory_usage_bytes(stats["MemUsage"])
                if parsed_memory is not None:
                    memory_bytes.append(parsed_memory)
                sample_count += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
    peak_memory = max(memory_bytes, default=None)
    return {
        "sample_count": sample_count,
        "cpu_percent_mean_of_samples": float(np.mean(cpu_percent)) if cpu_percent else None,
        "cpu_percent_peak": max(cpu_percent, default=None),
        "memory_usage_peak_bytes": peak_memory,
        "memory_usage_peak_MiB": peak_memory / (1024**2) if peak_memory is not None else None,
    }


def run_case(
    case_dir: Path,
    case: dict[str, Any],
    image_id: str,
    cpu_count: int,
    memory_gib: int,
    timeout_s: float,
    mpi_ranks: int | None = None,
) -> dict[str, Any]:
    cidfile = case_dir / "container.cid"
    console_log = case_dir / "docker-console.log"
    name = re.sub(
        r"[^a-zA-Z0-9_.-]",
        "-",
        f"cpuig-{case_dir.parent.parent.name}-{case['case_id']}",
    )[:60]
    create_command = [
        "docker",
        "create",
        "--cidfile",
        str(cidfile),
        "--name",
        name,
        f"--cpus={cpu_count}",
        f"--memory={memory_gib}g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "OMP_NUM_THREADS=1",
        "--env",
        "OPENBLAS_NUM_THREADS=1",
        "--mount",
        f"type=bind,src={case_dir.resolve()},dst=/case",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        image_id,
        "-lc",
        run_shell(mpi_ranks),
    ]
    create = subprocess.run(create_command, capture_output=True, text=True, check=True)
    cid = cidfile.read_text().strip() if cidfile.exists() else create.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{64}", cid):
        raise RuntimeError(f"docker create did not return a full container id: {cid!r}")
    start_command = ["docker", "start", "--attach", cid]
    write_json(
        case_dir / "launch.json",
        {
            "create_command": create_command,
            "start_command": start_command,
            "solver_image": IMAGE,
            "solver_image_id": image_id,
            "cpu_count": cpu_count,
            "mpi_ranks": mpi_ranks,
            "memory_limit_gib": memory_gib,
            "timeout_s": timeout_s,
            "input_sha256": input_hashes(case_dir),
            "gpu_requested": False,
        },
    )
    started = time.monotonic()
    timed_out = False
    samples_path = case_dir / "resources.jsonl"
    with console_log.open("wb") as log_stream, samples_path.open("w") as samples:
        process = subprocess.Popen(start_command, stdout=log_stream, stderr=subprocess.STDOUT)
        print(
            f"LAUNCH case={case['case_id']} cells={case['cell_count']} horizon_s={case['horizon_s']:.6g} "
            f"host_pid={process.pid} container_id={cid} artifact={case_dir}",
            flush=True,
        )
        docker_top = ""
        time.sleep(0.1)
        try:
            top = subprocess.run(
                ["docker", "top", cid, "-eo", "pid,ppid,comm,args"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            docker_top = top.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        print(
            f"RUNNING case={case['case_id']} host_pid={process.pid} container_id={cid} "
            f"artifact={case_dir}",
            flush=True,
        )
        manifest = {
            "case_id": case["case_id"],
            "host_docker_pid": process.pid,
            "container_id": cid,
            "docker_top_at_launch": docker_top,
            "started_utc": datetime.now(UTC).isoformat(),
            "status": "running",
        }
        write_json(case_dir / "execution.json", manifest)
        next_sample = time.monotonic()
        while process.poll() is None:
            now = time.monotonic()
            if now - started >= timeout_s:
                timed_out = True
                subprocess.run(
                    ["docker", "stop", "-t", "10", cid],
                    capture_output=True,
                    check=False,
                    timeout=20,
                )
                break
            if now >= next_sample:
                sample = docker_stats(cid)
                if sample:
                    samples.write(
                        json.dumps({"elapsed_s": now - started, "docker_stats": sample}) + "\n"
                    )
                    samples.flush()
                next_sample = now + 1.0
            time.sleep(0.2)
        exit_code = process.wait()
    subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False, timeout=30)
    completed = time.monotonic()
    result = {
        **manifest,
        "status": "timeout" if timed_out else ("completed" if exit_code == 0 else "failed"),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed_wall_s": completed - started,
        "finished_utc": datetime.now(UTC).isoformat(),
        "console_log": str(console_log),
        "solver_log": str(case_dir / "log.interIsoFoam"),
        "container_cid_file": str(cidfile),
    }
    write_json(case_dir / "execution.json", result)
    print(
        f"FINISH case={case['case_id']} status={result['status']} exit={exit_code} "
        f"elapsed_s={result['elapsed_wall_s']:.3f} host_pid={process.pid} container_id={cid}",
        flush=True,
    )
    return result


def parse_scalar_field(path: Path) -> np.ndarray:
    text = path.read_text(errors="replace")
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;",
        text,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"could not parse scalar list in {path}")
    count = int(match.group(1))
    values = np.fromstring(match.group(2), sep=" ", dtype=np.float64)
    if values.size != count:
        raise ValueError(f"expected {count} scalar values in {path}, parsed {values.size}")
    return values


def parse_vector_field(path: Path) -> np.ndarray:
    text = path.read_text(errors="replace")
    match = re.search(
        r"internalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;",
        text,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"could not parse vector list in {path}")
    count = int(match.group(1))
    values = np.fromstring(match.group(2).replace("(", " ").replace(")", " "), sep=" ")
    if values.size != 3 * count:
        raise ValueError(f"expected {3 * count} vector components in {path}, parsed {values.size}")
    return values.reshape((count, 3))


def interface_mode_components(alpha: np.ndarray, nx: int, ny: int, nz: int) -> dict[str, Any]:
    """Recover both interface modes and their symmetric/antisymmetric parts."""
    lx, ly, lz = LENGTHS
    dz = lz / nz
    z_low = np.arange(nz, dtype=np.float64) * dz
    z_high = z_low + dz
    zc = (z_low + z_high) / 2.0
    alpha_xz = alpha.reshape((nz, ny, nx)).mean(axis=1)
    lower_ref = np.clip((z_high - WATER_BOTTOM) / dz, 0.0, 1.0)[:, None]
    upper_ref = np.clip((WATER_TOP - z_low) / dz, 0.0, 1.0)[:, None]
    lower_mask = np.abs(zc - WATER_BOTTOM) <= 0.018
    upper_mask = np.abs(zc - WATER_TOP) <= 0.018
    lower_eta = -dz * np.sum(alpha_xz[lower_mask] - lower_ref[lower_mask], axis=0)
    upper_eta = dz * np.sum(alpha_xz[upper_mask] - upper_ref[upper_mask], axis=0)
    lower_eta -= float(lower_eta.mean())
    upper_eta -= float(upper_eta.mean())
    symmetric_eta = 0.5 * (lower_eta + upper_eta)
    antisymmetric_eta = 0.5 * (lower_eta - upper_eta)

    displacements = {
        "lower": lower_eta,
        "upper": upper_eta,
        "symmetric": symmetric_eta,
        "antisymmetric": antisymmetric_eta,
    }
    modes: dict[str, complex] = {}
    spectra: dict[str, np.ndarray] = {}
    for name, eta in displacements.items():
        modes[name] = complex(2.0 * np.fft.rfft(eta)[MODE_NUMBER] / nx)
        spectra[name] = 2.0 * np.abs(np.fft.rfft(eta)) / nx
    return {
        "displacements": displacements,
        "modes": modes,
        "spectra": spectra,
        "amplitudes": {name: abs(mode) for name, mode in modes.items()},
        "phases_rad": {name: float(np.angle(mode)) for name, mode in modes.items()},
        "relative_interface_phase_rad": float(
            np.angle(modes["lower"] * np.conjugate(modes["upper"]))
        ),
    }


def alpha05_interface_modes(
    alpha: np.ndarray,
    nx: int,
    ny: int,
    nz: int,
    mode_number: int = 1,
    half_window_m: float = 0.0225,
) -> dict[str, Any]:
    """Track the fixed lower/upper alpha=.5 branches with linear subcell interpolation."""
    lx, _, lz = V2_LENGTHS
    dz = lz / nz
    z_vertices = np.arange(nz, dtype=np.float64) * dz
    a = np.asarray(alpha, dtype=np.float64).reshape((nz, ny, nx))
    # Reconstruct point values by averaging the eight adjacent cell averages,
    # matching the regular-mesh cell-to-point interpolation used before an
    # alpha=.5 contour. Interpolate the crossing within the selected edge.
    point_alpha = np.zeros_like(a)
    for z_shift in (0, 1):
        for y_shift in (0, 1):
            for x_shift in (0, 1):
                point_alpha += np.roll(a, (z_shift, y_shift, x_shift), axis=(0, 1, 2)) / 8.0
    crossings = {
        "lower": (point_alpha[:-1] < 0.5) & (point_alpha[1:] >= 0.5),
        "upper": (point_alpha[:-1] >= 0.5) & (point_alpha[1:] < 0.5),
    }
    surfaces: dict[str, np.ndarray] = {}
    coverage: dict[str, float] = {}
    for name, z_ref in (("lower", V2_WATER_BOTTOM), ("upper", V2_WATER_TOP)):
        band = np.abs(0.5 * (z_vertices[:-1] + z_vertices[1:]) - z_ref) <= half_window_m
        candidates = crossings[name] & band[:, None, None]
        distances = np.where(
            candidates,
            np.abs(0.5 * (z_vertices[:-1] + z_vertices[1:]) - z_ref)[:, None, None],
            np.inf,
        )
        index = np.argmin(distances, axis=0)
        valid = np.isfinite(np.min(distances, axis=0))
        a0 = np.take_along_axis(point_alpha[:-1], index[None, ...], axis=0)[0]
        a1 = np.take_along_axis(point_alpha[1:], index[None, ...], axis=0)[0]
        z0 = z_vertices[index]
        z_cross = z0 + ((0.5 - a0) / np.where(np.abs(a1 - a0) > 1e-15, a1 - a0, 1.0)) * dz
        eta_yx = np.where(valid, z_cross - z_ref, np.nan)
        counts = np.isfinite(eta_yx).sum(axis=0)
        eta_x = np.nansum(eta_yx, axis=0) / np.maximum(counts, 1)
        surfaces[name] = eta_x
        coverage[name] = float(np.mean(valid))

    x = np.arange(nx, dtype=np.float64) * lx / nx
    k = 2.0 * math.pi * mode_number / lx
    modes: dict[str, complex] = {}
    for name, eta in surfaces.items():
        valid = np.isfinite(eta)
        if int(valid.sum()) < max(3, nx // 2):
            modes[name] = complex(float("nan"), float("nan"))
            continue
        centered = eta[valid] - float(np.mean(eta[valid]))
        modes[name] = complex(2.0 * np.mean(centered * np.exp(-1j * k * x[valid])))
    if all(np.isfinite([modes[n].real, modes[n].imag]).all() for n in ("lower", "upper")):
        modes["symmetric"] = 0.5 * (modes["lower"] + modes["upper"])
    else:
        modes["symmetric"] = complex(float("nan"), float("nan"))
    return {
        "modes": modes,
        "amplitudes_m": {name: abs(mode) for name, mode in modes.items()},
        "coverage_fraction": coverage,
        "relative_lower_upper_phase_rad": float(
            np.angle(modes["lower"] * np.conjugate(modes["upper"]))
        ),
    }


def interface_mode_amplitude(
    alpha: np.ndarray, nx: int, ny: int, nz: int
) -> tuple[float, np.ndarray]:
    """Backward-compatible symmetric interface-mode amplitude and shape."""
    components = interface_mode_components(alpha, nx, ny, nz)
    eta = components["displacements"]["symmetric"]
    return float(components["amplitudes"]["symmetric"]), eta


def fit_log_slope(times: np.ndarray, amplitudes: np.ndarray, mask: np.ndarray) -> float | None:
    valid = mask & np.isfinite(amplitudes) & (amplitudes > max(SEED_AMPLITUDE * 1e-4, 1e-12))
    if int(valid.sum()) < 3:
        return None
    return float(np.polyfit(times[valid], np.log(amplitudes[valid]), 1)[0])


def periodic_divergence_max(velocity: np.ndarray, nx: int, ny: int, nz: int) -> tuple[float, float]:
    lx, ly, lz = LENGTHS
    dx, dy, dz = lx / nx, ly / ny, lz / nz
    u = velocity.reshape((nz, ny, nx, 3))
    div = (
        (np.roll(u[..., 0], -1, axis=2) - np.roll(u[..., 0], 1, axis=2)) / (2.0 * dx)
        + (np.roll(u[..., 1], -1, axis=1) - np.roll(u[..., 1], 1, axis=1)) / (2.0 * dy)
        + (np.roll(u[..., 2], -1, axis=0) - np.roll(u[..., 2], 1, axis=0)) / (2.0 * dz)
    )
    return float(np.max(np.abs(div))), float(np.sqrt(np.mean(div**2)))


def plane_averaged_shear_metrics(
    velocity: np.ndarray, nx: int, ny: int, nz: int
) -> dict[str, dict[str, float | None]]:
    """Estimate each mean velocity jump and plane-mean tanh-profile delta."""
    _, _, lz = LENGTHS
    dz = lz / nz
    zc = (np.arange(nz, dtype=np.float64) + 0.5) * dz
    ux_profile = velocity.reshape((nz, ny, nx, 3))[..., 0].mean(axis=(1, 2))
    dudz = np.gradient(ux_profile, dz)
    result: dict[str, dict[str, float | None]] = {}
    for name, z_interface in (("lower", WATER_BOTTOM), ("upper", WATER_TOP)):
        window = np.abs(zc - z_interface) <= 3.0 * SHEAR_DELTA
        below_velocity = float(np.interp(z_interface - 3.0 * SHEAR_DELTA, zc, ux_profile))
        above_velocity = float(np.interp(z_interface + 3.0 * SHEAR_DELTA, zc, ux_profile))
        velocity_jump = abs(above_velocity - below_velocity)
        maximum_gradient = float(np.max(np.abs(dudz[window])))
        tanh_delta = (
            velocity_jump / (2.0 * maximum_gradient)
            if maximum_gradient > 1e-12 and velocity_jump > 1e-9
            else None
        )
        result[name] = {
            "mean_velocity_jump_m_s": velocity_jump,
            "max_mean_du_dz_s_inv": maximum_gradient,
            "plane_averaged_tanh_parameter_delta_m": tanh_delta,
        }
    return result


def vortex_sheet_growth_rate(case: dict[str, Any]) -> float:
    if case["variant"] == "advection_control":
        return 0.0
    k = 2.0 * math.pi * MODE_NUMBER / LENGTHS[0]
    delta_u = 50.0
    return k * delta_u * math.sqrt(WATER_RHO * AIR_RHO) / (WATER_RHO + AIR_RHO)


def continuity_residuals(log_path: Path) -> list[dict[str, float | None]]:
    if not log_path.exists():
        return []
    time_match = re.compile(r"^Time = ([^\s]+)")
    continuity_match = re.compile(
        r"sum local\s*=\s*([-+0-9.eE]+),\s*global\s*=\s*([-+0-9.eE]+),\s*cumulative\s*=\s*([-+0-9.eE]+)"
    )
    current_time: float | None = None
    rows: list[dict[str, float | None]] = []
    for line in log_path.read_text(errors="replace").splitlines():
        found_time = time_match.search(line)
        if found_time:
            try:
                current_time = float(found_time.group(1))
            except ValueError:
                current_time = None
        found_error = continuity_match.search(line)
        if found_error:
            values = [float(found_error.group(i)) for i in range(1, 4)]
            rows.append(
                {
                    "time_s": current_time,
                    "sum_local": values[0],
                    "global": values[1],
                    "cumulative": values[2],
                }
            )
    return rows


def write_alpha_snapshot_frame(
    case_dir: Path,
    snapshots: list[tuple[float, np.ndarray, Path | None]],
    nx: int,
    ny: int,
    nz: int,
) -> str | None:
    if len(snapshots) < 2:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lx, _, lz = LENGTHS
    fig = plt.figure(figsize=(9.0, 3.8))
    grid = fig.add_gridspec(1, 3, width_ratios=(1.0, 1.0, 0.045), wspace=0.12)
    axes = [fig.add_subplot(grid[0, 0])]
    axes.append(fig.add_subplot(grid[0, 1], sharex=axes[0], sharey=axes[0]))
    colorbar_axis = fig.add_subplot(grid[0, 2])
    image = None
    for axis, (time_s, alpha, _) in zip(axes, (snapshots[0], snapshots[-1]), strict=True):
        alpha_xz = alpha.reshape((nz, ny, nx)).mean(axis=1)
        image = axis.imshow(
            alpha_xz,
            origin="lower",
            extent=(0.0, lx, 0.0, lz),
            aspect="equal",
            interpolation="nearest",
            cmap="viridis",
            vmin=0.0,
            vmax=1.0,
        )
        axis.contour(
            np.linspace(0.5 * lx / nx, lx - 0.5 * lx / nx, nx),
            np.linspace(0.5 * lz / nz, lz - 0.5 * lz / nz, nz),
            alpha_xz,
            levels=[0.5],
            colors="white",
            linewidths=0.7,
        )
        axis.set_title(f"$\\alpha_w$, t={time_s:.5f} s")
        axis.set_xlabel("streamwise x [m]")
    axes[0].set_ylabel("shear-normal z [m]")
    if image is not None:
        fig.colorbar(image, cax=colorbar_axis, label="water volume fraction")
    fig.suptitle(f"{case_dir.name}: spanwise-averaged VOF field")
    fig.subplots_adjust(left=0.095, right=0.90, bottom=0.14, top=0.83)
    target = case_dir / "alpha_initial_final_xz.png"
    fig.savefig(target, dpi=150)
    plt.close(fig)
    return str(target)


def analyze_case(case_dir: Path, case: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    nx, ny, nz = case["mesh"]
    lx, ly, lz = LENGTHS
    cell_volume = lx * ly * lz / (nx * ny * nz)
    alpha_initial = parse_scalar_field(case_dir / "0" / "alpha.water")
    snapshots: list[tuple[float, np.ndarray, Path | None]] = [(0.0, alpha_initial, None)]
    for path in case_dir.iterdir():
        if not path.is_dir() or path.name in {"0", "constant", "system"}:
            continue
        try:
            time_value = float(path.name)
        except ValueError:
            continue
        alpha_path = path / "alpha.water"
        if alpha_path.exists():
            snapshots.append((time_value, parse_scalar_field(alpha_path), path))
    snapshots.sort(key=lambda item: item[0])
    water_volume_0 = float(alpha_initial.sum() * cell_volume)
    diagnostic_rows: list[dict[str, Any]] = []
    component_names = ("lower", "upper", "symmetric", "antisymmetric")
    amplitudes: dict[str, list[float]] = {name: [] for name in component_names}
    spectra: dict[str, list[np.ndarray]] = {name: [] for name in component_names}
    alpha_mins: list[float] = []
    alpha_maxs: list[float] = []
    water_volumes: list[float] = []
    divergence_maxs: list[float] = []
    divergence_rms: list[float] = []
    for time_value, alpha_flat, path in snapshots:
        components = interface_mode_components(alpha_flat, nx, ny, nz)
        volume = float(alpha_flat.sum() * cell_volume)
        if path is None:
            velocity = parse_vector_field(case_dir / "0" / "U")
        else:
            velocity_file = path / "U"
            velocity = (
                parse_vector_field(velocity_file)
                if velocity_file.exists()
                else np.zeros((nx * ny * nz, 3))
            )
        div_max, div_rms = periodic_divergence_max(velocity, nx, ny, nz)
        shear_metrics = plane_averaged_shear_metrics(velocity, nx, ny, nz)
        row = {
            "time_s": time_value,
            # Retain the historical field names for the symmetric mode.
            "mode_amplitude_m": components["amplitudes"]["symmetric"],
            "mode_growth_ratio": components["amplitudes"]["symmetric"] / max(SEED_AMPLITUDE, 1e-30),
            "lower_mode_amplitude_m": components["amplitudes"]["lower"],
            "upper_mode_amplitude_m": components["amplitudes"]["upper"],
            "symmetric_mode_amplitude_m": components["amplitudes"]["symmetric"],
            "antisymmetric_mode_amplitude_m": components["amplitudes"]["antisymmetric"],
            "lower_mode_phase_rad": components["phases_rad"]["lower"],
            "upper_mode_phase_rad": components["phases_rad"]["upper"],
            "relative_interface_phase_rad": components["relative_interface_phase_rad"],
            "water_volume_m3": volume,
            "water_volume_relative_drift": (volume - water_volume_0) / water_volume_0,
            "alpha_min": float(alpha_flat.min()),
            "alpha_max": float(alpha_flat.max()),
            "max_abs_central_divergence_s_inv": div_max,
            "rms_central_divergence_s_inv": div_rms,
            "plane_averaged_shear_profile": shear_metrics,
        }
        diagnostic_rows.append(row)
        for name in component_names:
            amplitudes[name].append(float(components["amplitudes"][name]))
            spectra[name].append(components["spectra"][name])
        alpha_mins.append(row["alpha_min"])
        alpha_maxs.append(row["alpha_max"])
        water_volumes.append(volume)
        divergence_maxs.append(div_max)
        divergence_rms.append(div_rms)
    times = np.asarray([row["time_s"] for row in diagnostic_rows], dtype=np.float64)
    amplitude_arrays = {
        name: np.asarray(values, dtype=np.float64) for name, values in amplitudes.items()
    }
    fit_mask = (times >= FIT_WINDOW_S[0]) & (times <= FIT_WINDOW_S[1])
    transient_mask = times <= FIT_WINDOW_S[0]
    fit_rates = {
        name: fit_log_slope(times, values, fit_mask) for name, values in amplitude_arrays.items()
    }
    transient_rates = {
        name: fit_log_slope(times, values, transient_mask)
        for name, values in amplitude_arrays.items()
    }
    symmetric_values = amplitude_arrays["symmetric"]
    symmetric_fit_mask = fit_mask & (symmetric_values > max(SEED_AMPLITUDE * 1e-4, 1e-12))
    fit_intercept = (
        float(
            np.polyfit(times[symmetric_fit_mask], np.log(symmetric_values[symmetric_fit_mask]), 1)[
                1
            ]
        )
        if int(symmetric_fit_mask.sum()) >= 3
        else None
    )
    continuity = continuity_residuals(case_dir / "log.interIsoFoam")
    solver_log = (
        (case_dir / "log.interIsoFoam").read_text(errors="replace")
        if (case_dir / "log.interIsoFoam").exists()
        else ""
    )
    build_match = re.search(r"^Build\s+:\s+(.+)$", solver_log, re.MULTILINE)
    finite_dt = [float(x) for x in re.findall(r"\bdeltaT\s*=\s*([-+0-9.eE]+)", solver_log)]
    cell_dx = lx / nx
    measured_horizon = float(times[-1]) if times.size else 0.0
    component_fit_amplitude_floor = max(SEED_AMPLITUDE * 1e-4, 1e-12)
    metrics = {
        "case_id": case["case_id"],
        "variant": case["variant"],
        "mesh": list(case["mesh"]),
        "cell_count": int(nx * ny * nz),
        "cell_size_m": [lx / nx, ly / ny, lz / nz],
        "resolved_cells_per_seed_wavelength": float(LENGTHS[0] / cell_dx),
        "seeded_streamwise_mode_number": MODE_NUMBER,
        "seeded_wavelength_m": LENGTHS[0] / MODE_NUMBER,
        "resolved_cells_per_shear_thickness_z": float(SHEAR_DELTA / (lz / nz)),
        "finite_shear_k_delta": float(2.0 * math.pi / LENGTHS[0] * SHEAR_DELTA),
        "seed_amplitude_declared_m": SEED_AMPLITUDE,
        "phase_density_kg_m3": {"water": WATER_RHO, "air": AIR_RHO},
        "water_to_air_density_ratio": WATER_RHO / AIR_RHO,
        "molecular_kinematic_viscosity_m2_s": {
            "water": WATER_NU,
            "air": AIR_NU,
        },
        "added_kinematic_viscosity_m2_s_each_phase": case["nu_add_m2_s"],
        "effective_kinematic_viscosity_m2_s": {
            "water": WATER_NU + case["nu_add_m2_s"],
            "air": AIR_NU + case["nu_add_m2_s"],
        },
        "effective_dynamic_viscosity_Pa_s": {
            "water": WATER_RHO * (WATER_NU + case["nu_add_m2_s"]),
            "air": AIR_RHO * (AIR_NU + case["nu_add_m2_s"]),
        },
        "initial_mode_amplitude_measured_m": (
            float(symmetric_values[0]) if symmetric_values.size else None
        ),
        "final_mode_amplitude_m": (float(symmetric_values[-1]) if symmetric_values.size else None),
        "final_mode_growth_ratio": (
            float(symmetric_values[-1] / max(symmetric_values[0], 1e-30))
            if symmetric_values.size
            else None
        ),
        "initial_component_amplitudes_m": {
            name: float(values[0]) if values.size else None
            for name, values in amplitude_arrays.items()
        },
        "final_component_amplitudes_m": {
            name: float(values[-1]) if values.size else None
            for name, values in amplitude_arrays.items()
        },
        "final_component_growth_ratios": {
            name: (
                float(values[-1] / values[0])
                if values.size and values[0] > component_fit_amplitude_floor
                else None
            )
            for name, values in amplitude_arrays.items()
        },
        "transient_log_amplitude_slope_s_inv": transient_rates["symmetric"],
        "transient_component_log_amplitude_slopes_s_inv": transient_rates,
        "fit_window_s": list(FIT_WINDOW_S),
        "component_fit_amplitude_floor_m": component_fit_amplitude_floor,
        "fit_log_amplitude_slope_s_inv": fit_rates["symmetric"],
        "fit_component_log_amplitude_slopes_s_inv": fit_rates,
        "fit_log_amplitude_intercept": fit_intercept,
        "initial_relative_interface_phase_rad": (
            diagnostic_rows[0]["relative_interface_phase_rad"] if diagnostic_rows else None
        ),
        "final_relative_interface_phase_rad": (
            diagnostic_rows[-1]["relative_interface_phase_rad"] if diagnostic_rows else None
        ),
        "initial_plane_averaged_shear_profile": (
            diagnostic_rows[0]["plane_averaged_shear_profile"] if diagnostic_rows else None
        ),
        "final_plane_averaged_shear_profile": (
            diagnostic_rows[-1]["plane_averaged_shear_profile"] if diagnostic_rows else None
        ),
        "vortex_sheet_growth_rate_reference_s_inv_diagnostic_only": vortex_sheet_growth_rate(case),
        "finite_thickness_eigenvalue_available": False,
        "measured_horizon_s": measured_horizon,
        "requested_horizon_s": case["horizon_s"],
        "openfoam_build_line": build_match.group(1) if build_match else None,
        "solver_status": execution["status"],
        "solver_exit_code": execution["exit_code"],
        "solver_elapsed_wall_s": execution["elapsed_wall_s"],
        "container_resource_summary": summarize_docker_resources(case_dir / "resources.jsonl"),
        "gpu_requested": False,
        "alpha_initial_volume_m3": water_volume_0,
        "water_volume_relative_drift_final": diagnostic_rows[-1]["water_volume_relative_drift"]
        if diagnostic_rows
        else None,
        "water_volume_relative_drift_max_abs": max(
            (abs(r["water_volume_relative_drift"]) for r in diagnostic_rows), default=None
        ),
        "alpha_min_over_snapshots": min(alpha_mins, default=None),
        "alpha_max_over_snapshots": max(alpha_maxs, default=None),
        "alpha_bounded_all_snapshots": bool(
            alpha_mins and min(alpha_mins) >= -1e-10 and max(alpha_maxs) <= 1.0 + 1e-10
        ),
        "max_abs_periodic_central_divergence_s_inv": max(divergence_maxs, default=None),
        "max_rms_periodic_central_divergence_s_inv": max(divergence_rms, default=None),
        "max_abs_openfoam_continuity_global": max(
            (abs(r["global"]) for r in continuity), default=None
        ),
        "max_abs_openfoam_continuity_local_sum": max(
            (abs(r["sum_local"]) for r in continuity), default=None
        ),
        "dt_min_s": min(finite_dt, default=None),
        "dt_max_s": max(finite_dt, default=None),
        "snapshots": diagnostic_rows,
        "alpha_initial_final_spanwise_average_frame": write_alpha_snapshot_frame(
            case_dir, snapshots, nx, ny, nz
        ),
        "continuity_residuals": continuity,
        "classification": "exploratory CPU finite-shear interface diagnostic; no Dash-8 reproduction or acceptance decision",
        "interpretation_limits": [
            "The interface is deliberately seeded; lower/upper complex Fourier modes and their symmetric/antisymmetric combinations are tracked separately to expose phase beating.",
            "The prescribed disturbance is invariant in the spanwise direction, so this three-dimensional mesh does not test spanwise breakup or secondary instabilities.",
            "The finite-thickness tanh velocity profile is not an exact finite-thickness eigenmode.",
            "The vortex-sheet rate is only an approximate reference; initial transient and finite-time fitted slope are reported separately.",
            "The added constant kinematic viscosity is a damping surrogate, not k-epsilon RANS or LES.",
            "The flow is periodic in all axes, has zero gravity and sigma=0, and is not the aircraft geometry or source history.",
        ],
    }
    write_json(case_dir / "diagnostics.json", metrics)
    if diagnostic_rows:
        with (case_dir / "final_mode_spectrum.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "streamwise_mode",
                    "wavenumber_rad_m",
                    *(f"{name}_amplitude_m" for name in component_names),
                ]
            )
            for mode in range(len(spectra["symmetric"][-1])):
                writer.writerow(
                    [
                        mode,
                        2.0 * math.pi * mode / LENGTHS[0],
                        *(float(spectra[name][-1][mode]) for name in component_names),
                    ]
                )
    with (case_dir / "amplitude_time.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(diagnostic_rows[0]) if diagnostic_rows else []
        )
        if diagnostic_rows:
            writer.writeheader()
            writer.writerows(diagnostic_rows)
    return metrics


def case_definitions(pilot: bool) -> list[dict[str, Any]]:
    if pilot:
        return [
            {
                "case_id": "pilot32-shear-molecular",
                "variant": "molecular_shear",
                "mesh_name": "pilot32x16x32",
                "mesh": [32, 16, 32],
                "nu_add_m2_s": 0.0,
                "horizon_s": 0.002,
                "write_interval_s": WRITE_INTERVAL_PILOT_S,
            }
        ]
    cases: list[dict[str, Any]] = []
    variants = (
        ("advection_control", 0.0),
        ("molecular_shear", 0.0),
        ("added_viscosity_shear", ADDED_NU),
    )
    for mesh_name, mesh in (("coarse", [48, 24, 48]), ("fine", [72, 36, 72])):
        for variant, nu_add in variants:
            cases.append(
                {
                    "case_id": f"{mesh_name}-{variant}",
                    "variant": variant,
                    "mesh_name": mesh_name,
                    "mesh": mesh,
                    "nu_add_m2_s": nu_add,
                    "horizon_s": 0.012,
                    "write_interval_s": WRITE_INTERVAL_SWEEP_S,
                }
            )
    return cases


def alpha_seed_v2(nx: int, ny: int, nz: int, amplitude_m: float = V2_SEED_AMPLITUDE) -> np.ndarray:
    """Subcell integrate the smaller V2 sinusoidal displacement on both surfaces."""
    return v2_alpha_from_eta((nx, ny, nz), V2_LENGTHS, -1j * amplitude_m, -1j * amplitude_m, 1)


def v2_alpha_from_eta(
    mesh: tuple[int, int, int],
    lengths: tuple[float, float, float],
    eta_lower: complex,
    eta_upper: complex,
    mode_number: int,
) -> np.ndarray:
    nx, ny, nz = mesh
    lx, _, lz = lengths
    dx, dz = lx / nx, lz / nz
    nodes, weights = np.polynomial.legendre.leggauss(12)
    alpha = np.zeros((nz, ny, nx), dtype=np.float64)
    z_low = np.arange(nz, dtype=np.float64) * dz
    z_high = z_low + dz
    k = 2.0 * math.pi * mode_number / lx
    for ix in range(nx):
        x_nodes = (ix + 0.5) * dx + 0.5 * dx * nodes
        phase = np.exp(1j * k * x_nodes)
        lower = V2_WATER_BOTTOM + np.real(eta_lower * phase)
        upper = V2_WATER_TOP + np.real(eta_upper * phase)
        overlap = (
            np.maximum(
                0.0,
                np.minimum(z_high[:, None], upper[None, :])
                - np.maximum(z_low[:, None], lower[None, :]),
            )
            / dz
        )
        alpha[:, :, ix] = (overlap @ weights / 2.0)[:, None]
    return np.clip(alpha, 0.0, 1.0)


def v2_fv_schemes() -> str:
    """fvSchemes including the native surface-flux divergence scheme."""
    return fv_schemes().replace(
        "    div(rhoPhi,U) Gauss linearUpwind grad(U);",
        "    div(phi) Gauss linear;\n    div(rhoPhi,U) Gauss linearUpwind grad(U);",
    )


def _eigen_value(eigenpair: Any, name: str) -> Any:
    return eigenpair[name] if isinstance(eigenpair, dict) else getattr(eigenpair, name)


def _linear_complex_extrapolate(
    source_z: np.ndarray, values: np.ndarray, target_z: np.ndarray
) -> np.ndarray:
    result = np.interp(target_z, source_z, values.real) + 1j * np.interp(
        target_z, source_z, values.imag
    )
    below = target_z < source_z[0]
    above = target_z > source_z[-1]
    if np.any(below):
        result[below] = values[0] + (target_z[below] - source_z[0]) * (values[1] - values[0]) / (
            source_z[1] - source_z[0]
        )
    if np.any(above):
        result[above] = values[-1] + (target_z[above] - source_z[-1]) * (
            values[-1] - values[-2]
        ) / (source_z[-1] - source_z[-2])
    return result


def _phasewise_tangential_mode(
    target_z: np.ndarray,
    source_z: np.ndarray,
    source_u: np.ndarray,
    lower_z: float,
    upper_z: float,
) -> np.ndarray:
    """Avoid smearing the eigenmode's tangential velocity jump across interfaces."""
    regions = (
        (target_z < lower_z, source_z < lower_z),
        (
            (target_z >= lower_z) & (target_z < upper_z),
            (source_z >= lower_z) & (source_z < upper_z),
        ),
        (target_z >= upper_z, source_z >= upper_z),
    )
    result = np.empty(target_z.shape, dtype=np.complex128)
    for target_mask, source_mask in regions:
        z_values = source_z[source_mask]
        u_values = source_u[source_mask]
        if z_values.size < 2:
            raise ValueError("eigenpair needs at least two samples in each density region")
        result[target_mask] = _linear_complex_extrapolate(z_values, u_values, target_z[target_mask])
    return result


def v2_initial_fields(
    case: dict[str, Any], eigenpair: Any | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray, complex, complex]:
    """Make finite-shear VOF and velocity seed, scaled from a reference eigenpair."""
    nx, ny, nz = case["mesh"]
    lengths = tuple(case.get("domain_m", V2_LENGTHS))
    lx, _, lz = lengths
    dz, dx = lz / nz, lx / nx
    zc = (np.arange(nz, dtype=np.float64) + 0.5) * dz
    z_reference = zc - 0.5 * lz
    xcenters = (np.arange(nx, dtype=np.float64) + 0.5) * dx
    mode_number = int(case.get("mode_number", 1))
    k = float(case.get("wavenumber_rad_m", 2.0 * math.pi * mode_number / lx))
    seed_amp = float(case.get("seed_amplitude_m", 5.0e-5))
    eta_lower = -1j * seed_amp
    eta_upper = -1j * seed_amp
    from aerial_drop.interface_stability import BaseState

    base_state = BaseState(
        Lz=lz,
        z_lower=V2_WATER_BOTTOM - 0.5 * lz,
        z_upper=V2_WATER_TOP - 0.5 * lz,
        delta=V2_SHEAR_DELTA,
        rho_water=WATER_RHO,
        rho_air=AIR_RHO,
        U_air=50.0,
        U_water=0.0,
    )
    base_ux = np.asarray(base_state.velocity(z_reference)[0], dtype=np.float64)
    if case["variant"] == "advection_control":
        base_ux = np.full(nz, 25.0)
    u_mode = np.zeros(nz, dtype=np.complex128)
    w_mode = np.zeros(nz, dtype=np.complex128)
    p_mode = np.zeros(nz, dtype=np.complex128)
    reference_metadata = None
    if eigenpair is not None:
        zref = np.asarray(_eigen_value(eigenpair, "z"), dtype=np.float64)
        eta_l_ref = complex(_eigen_value(eigenpair, "eta_lower"))
        eta_u_ref = complex(_eigen_value(eigenpair, "eta_upper"))
        # Rotate the entire eigenvector so its lower interface starts as the
        # same positive sine used by the zero-shear transport control.  The
        # modal u/w/p fields receive this identical complex scale below.
        scale = (-1j * seed_amp) / (eta_l_ref if abs(eta_l_ref) > 1e-30 else 1.0)
        eta_lower, eta_upper = eta_l_ref * scale, eta_u_ref * scale

        base_reference = np.asarray(_eigen_value(eigenpair, "U"), dtype=np.float64)
        base_mismatch = float(np.max(np.abs(base_reference - base_state.velocity(zref)[0])))
        if base_mismatch > 5e-8:
            raise ValueError(
                f"eigenpair base does not match periodic-image CFD profile ({base_mismatch:.3g} m/s)"
            )
        if case["variant"] != "advection_control":
            u_reference = np.asarray(_eigen_value(eigenpair, "u"), dtype=np.complex128)
            u_mode = (
                _phasewise_tangential_mode(
                    z_reference,
                    zref,
                    u_reference,
                    V2_WATER_BOTTOM - 0.5 * lz,
                    V2_WATER_TOP - 0.5 * lz,
                )
                * scale
            )
            w_reference = np.asarray(_eigen_value(eigenpair, "w"), dtype=np.complex128)
            w_mode = _linear_complex_extrapolate(zref, w_reference, z_reference) * scale
            try:
                p_reference = np.asarray(_eigen_value(eigenpair, "p"), dtype=np.complex128)
                p_mode = _linear_complex_extrapolate(zref, p_reference, z_reference) * scale
            except (AttributeError, KeyError):
                pass
        try:
            reference_metadata = _eigen_value(eigenpair, "metadata")
        except (AttributeError, KeyError):
            reference_metadata = None

    alpha = v2_alpha_from_eta((nx, ny, nz), lengths, eta_lower, eta_upper, mode_number)
    phase = np.exp(1j * k * xcenters)
    ux = base_ux[:, None] + np.real(u_mode[:, None] * phase[None, :])
    wz = np.real(w_mode[:, None] * phase[None, :])
    p = np.real(p_mode[:, None] * phase[None, :])
    velocity = np.zeros((nz, ny, nx, 3), dtype=np.float64)
    velocity[..., 0] = ux[:, None, :]
    velocity[..., 2] = wz[:, None, :]
    pressure = np.broadcast_to(p[:, None, :], (nz, ny, nx)).copy()
    case["eigenpair_metadata"] = reference_metadata
    if eigenpair is not None:
        case["eigenpair_applied_scale_complex"] = [float(scale.real), float(scale.imag)]
    return alpha, velocity, pressure, eta_lower, eta_upper


def v2_decompose_par_dict(ranks: int) -> str:
    factors = {1: (1, 1, 1), 2: (2, 1, 1), 4: (2, 1, 2), 8: (2, 2, 2), 16: (4, 2, 2)}
    decomposition = factors.get(ranks, (ranks, 1, 1))
    return (
        field_header("decomposeParDict", "dictionary", "system")
        + f"numberOfSubdomains {ranks};\nmethod simple;\nsimpleCoeffs\n{{\n"
        + f"    n ({decomposition[0]} {decomposition[1]} {decomposition[2]});\n"
        + "    delta 0.001;\n    order xyz;\n}\ndistributed no;\nroots ();\n"
    )


def create_v2_growth_case(
    case_dir: Path, case: dict[str, Any], eigenpair: Any | None = None
) -> dict[str, Any]:
    """Create the seeded-eigenmode growth case for a declared mesh/variant."""
    nx, ny, nz = case["mesh"]
    lengths = tuple(case.get("domain_m", V2_LENGTHS))
    if tuple(lengths) != V2_LENGTHS:
        raise ValueError("current V2 block mesh is declared for domain 0.12 x 0.06 x 0.12 m")
    system, constant, initial = (case_dir / name for name in ("system", "constant", "0"))
    for path in (system, constant, initial):
        path.mkdir(parents=True, exist_ok=True)
    (system / "blockMeshDict").write_text(block_mesh_dict(nx, ny, nz))
    (system / "decomposeParDict").write_text(v2_decompose_par_dict(int(case["mpi_ranks"])))
    control = control_dict(float(case["horizon_s"]), float(case["write_interval_s"]))
    # Native face-flux auditing is sensitive to ASCII roundoff; retain enough
    # significant digits for an independent per-cell div(phi) reconstruction.
    control = control.replace("writePrecision 12;", "writePrecision 17;")
    control += """
functions
{
    nativeDivPhi
    {
        type div;
        libs (fieldFunctionObjects);
        field phi;
        result divPhi;
        executeControl writeTime;
        writeControl writeTime;
    }
    savePhi
    {
        type writeObjects;
        libs (utilityFunctionObjects);
        objects (phi);
        writeOption anyWrite;
        executeControl writeTime;
        writeControl writeTime;
    }
}
"""
    (system / "controlDict").write_text(control)
    (system / "fvSchemes").write_text(v2_fv_schemes())
    (system / "fvSolution").write_text(fv_solution())
    nu_add = float(case.get("nu_add_m2_s", 0.0))
    (constant / "transportProperties").write_text(transport_properties(nu_add))
    (constant / "turbulenceProperties").write_text(
        f"""{field_header("turbulenceProperties", "dictionary", "constant")}simulationType laminar;
"""
    )
    (constant / "g").write_text(
        f"""{field_header("g", "uniformDimensionedVectorField", "constant")}dimensions [0 1 -2 0 0 0 0];
value (0 0 0);
"""
    )
    alpha, velocity, pressure, eta_lower, eta_upper = v2_initial_fields(case, eigenpair)
    write_scalar_field(initial / "alpha.water", "alpha.water", alpha)
    write_vector_field(initial / "U", "U", velocity)
    write_scalar_field(initial / "p_rgh", "p_rgh", pressure)
    p_path = initial / "p_rgh"
    p_path.write_text(
        p_path.read_text().replace("dimensions [0 0 0 0 0 0 0];", "dimensions [1 -1 -2 0 0 0 0];")
    )
    cell_volume = float(np.prod(lengths) / (nx * ny * nz))
    expected_volume = lengths[0] * lengths[1] * (V2_WATER_TOP - V2_WATER_BOTTOM)
    metadata = {
        **case,
        "solver": "OpenCFD OpenFOAM v2512 interIsoFoam",
        "cell_count": nx * ny * nz,
        "cell_size_m": [lengths[0] / nx, lengths[1] / ny, lengths[2] / nz],
        "cells_per_finite_shear_thickness": V2_SHEAR_DELTA / (lengths[2] / nz),
        "water_volume_expected_m3": expected_volume,
        "water_volume_initial_m3": float(alpha.sum() * cell_volume),
        "water_volume_initial_relative_error": float(
            (alpha.sum() * cell_volume - expected_volume) / expected_volume
        ),
        "initial_alpha_min": float(alpha.min()),
        "initial_alpha_max": float(alpha.max()),
        "seeded_mode": {
            "mode_number": int(case.get("mode_number", 1)),
            "wavelength_m": lengths[0] / int(case.get("mode_number", 1)),
            "wavenumber_rad_m": float(case.get("wavenumber_rad_m", 2.0 * math.pi / lengths[0])),
            "amplitude_scale_m": float(case.get("seed_amplitude_m", 5e-5)),
            "eta_lower_complex_m": [eta_lower.real, eta_lower.imag],
            "eta_upper_complex_m": [eta_upper.real, eta_upper.imag],
            "eigenpair_applied_scale_complex": case.get("eigenpair_applied_scale_complex"),
            "phase_convention": "eta(x)=Re(eta_hat*exp(i*k*x)); temporal eigen convention exp(i*k*x+sigma*t)",
            "velocity_mode_from_eigenpair": eigenpair is not None
            and case["variant"] != "advection_control",
        },
        "boundary_conditions": "cyclic in x,y,z; no open/physical boundary patches",
        "coupled_periodic_patches_excluded_from_physical_boundary_flux": [
            "xMin",
            "xMax",
            "yMin",
            "yMax",
            "zMin",
            "zMax",
        ],
        "gravity_m_s2": [0.0, 0.0, 0.0],
        "surface_tension_N_m": 0.0,
        "phase_density_kg_m3": {"water": WATER_RHO, "air": AIR_RHO},
        "water_to_air_density_ratio": WATER_RHO / AIR_RHO,
        "molecular_kinematic_viscosity_m2_s": {"water": WATER_NU, "air": AIR_NU},
        "added_kinematic_viscosity_m2_s_each_phase": nu_add,
        "effective_dynamic_viscosity_Pa_s": {
            "water": WATER_RHO * (WATER_NU + nu_add),
            "air": AIR_RHO * (AIR_NU + nu_add),
        },
        "turbulence_model": "laminar; constant added nu is a damping surrogate, not RANS/LES",
        "native_flux_divergence": {
            "function_object": "v2512 fieldFunctionObjects div",
            "operand": "phi",
            "result": "divPhi",
            "scheme": "div(phi) Gauss linear",
        },
        "finite_thickness_eigenpair_reference": (
            _eigen_value(eigenpair, "metadata")
            if eigenpair is not None
            and (
                isinstance(eigenpair, dict)
                and "metadata" in eigenpair
                or hasattr(eigenpair, "metadata")
            )
            else None
        ),
        "surface_tension_zero_baseline": "deliberate sigma=0 isolated mechanism baseline",
    }
    write_json(case_dir / "case-inputs.json", metadata)
    return metadata


def create_v2_profile_case(case_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    """Create the high-resolution 50-step MPI profiling/control case."""
    nx, ny, nz = case["mesh"]
    system, constant, initial = (case_dir / name for name in ("system", "constant", "0"))
    for path in (system, constant, initial):
        path.mkdir(parents=True, exist_ok=True)
    (system / "blockMeshDict").write_text(block_mesh_dict(nx, ny, nz))
    (system / "decomposeParDict").write_text(v2_decompose_par_dict(int(case.get("mpi_ranks", 1))))
    profile_dt = float(case["profile_dt_s"])
    write_steps = int(case["profile_write_steps"])
    control = control_dict(profile_dt * int(case["profile_steps"]), profile_dt * write_steps)
    control = control.replace("deltaT 1e-6;", f"deltaT {profile_dt:.16g};")
    control = control.replace("adjustTimeStep yes;", "adjustTimeStep no;")
    control = control.replace("writeControl runTime;", "writeControl timeStep;")
    control = control.replace(
        f"writeInterval {profile_dt * write_steps:.16g};",
        f"writeInterval {write_steps};",
    )
    control += """
functions
{
    nativeDivPhi
    {
        type div;
        libs (fieldFunctionObjects);
        field phi;
        result divPhi;
        executeControl writeTime;
        writeControl writeTime;
    }
    savePhi
    {
        type writeObjects;
        libs (utilityFunctionObjects);
        objects (phi);
        writeOption anyWrite;
        executeControl writeTime;
        writeControl writeTime;
    }
}
"""
    (system / "controlDict").write_text(control)
    (system / "fvSchemes").write_text(v2_fv_schemes())
    (system / "fvSolution").write_text(fv_solution())
    (constant / "transportProperties").write_text(transport_properties(0.0))
    (constant / "turbulenceProperties").write_text(
        f"""{field_header("turbulenceProperties", "dictionary", "constant")}simulationType laminar;
"""
    )
    (constant / "g").write_text(
        f"""{field_header("g", "uniformDimensionedVectorField", "constant")}dimensions [0 1 -2 0 0 0 0];
value (0 0 0);
"""
    )
    alpha = alpha_seed_v2(nx, ny, nz)
    velocity = initial_velocity(nx, ny, nz, case["variant"])
    write_scalar_field(initial / "alpha.water", "alpha.water", alpha)
    write_vector_field(initial / "U", "U", velocity)
    (initial / "p_rgh").write_text(
        f"""{field_header("p_rgh", "volScalarField")}dimensions [1 -1 -2 0 0 0 0];
internalField uniform 0;
{cyclic_boundary_field()}"""
    )
    nx, ny, nz = case["mesh"]
    cell_volume = np.prod(LENGTHS) / (nx * ny * nz)
    expected_volume = LENGTHS[0] * LENGTHS[1] * (V2_WATER_TOP - V2_WATER_BOTTOM)
    metadata = {
        **case,
        "horizon_s": float(case["profile_steps"]) * float(case["profile_dt_s"]),
        "cell_count": nx * ny * nz,
        "cell_size_m": [LENGTHS[0] / nx, LENGTHS[1] / ny, LENGTHS[2] / nz],
        "cells_per_shear_thickness": V2_SHEAR_DELTA / (LENGTHS[2] / nz),
        "seed_amplitude_m": V2_SEED_AMPLITUDE,
        "seed_wavelength_m": LENGTHS[0],
        "water_volume_expected_m3": expected_volume,
        "water_volume_initial_m3": float(alpha.sum() * cell_volume),
        "water_volume_initial_relative_error": float(
            (alpha.sum() * cell_volume - expected_volume) / expected_volume
        ),
        "initial_alpha_min": float(alpha.min()),
        "initial_alpha_max": float(alpha.max()),
        "boundary_conditions": "cyclic on all axes; no open boundaries",
        "gravity_m_s2": [0.0, 0.0, 0.0],
        "surface_tension_N_m": 0.0,
        "phase_density_kg_m3": {"water": WATER_RHO, "air": AIR_RHO},
        "water_to_air_density_ratio": WATER_RHO / AIR_RHO,
        "molecular_kinematic_viscosity_m2_s": {"water": WATER_NU, "air": AIR_NU},
        "added_kinematic_viscosity_m2_s_each_phase": 0.0,
        "turbulence_model": "laminar molecular viscosity; no RANS/LES",
        "native_flux_divergence": {
            "field_object": "OpenFOAM v2512 fieldFunctionObjects div",
            "operand": "surfaceScalarField phi",
            "result": "volScalarField divPhi",
            "scheme": "div(phi) Gauss linear",
            "phi_saved_at_write_times": True,
        },
        "finite_thickness_eigenmode": False,
        "purpose": "50-step MPI/resource and native flux-field writer check only; not a growth-rate measurement",
    }
    write_json(case_dir / "case-inputs.json", metadata)
    return metadata


def run_v2_mpi_profile(args: argparse.Namespace) -> int:
    run_id = args.run_id or f"cpu-interface-growth-v2-profile-{utc_stamp()}"
    run_dir = ROOT / "results" / "runs" / run_id
    if run_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {run_dir}")
    run_dir.mkdir(parents=True)
    shutil.copy2(Path(__file__), run_dir / "runner-snapshot.py")
    image_id = docker_image_id()
    git_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    is_smoke = bool(getattr(args, "v2_smoke", False))
    profile_mesh = [32, 16, 32] if is_smoke else [128, 64, 128]
    profile_steps = 4 if is_smoke else V2_PROFILE_STEPS
    profile_dt_s = 1.0e-5 if is_smoke else V2_PROFILE_DT_S
    profile_write_steps = 2 if is_smoke else V2_PROFILE_WRITE_STEPS
    case = {
        "case_id": f"{'writer-smoke32' if is_smoke else 'profile128'}-mpi{args.cpus}",
        "variant": "molecular_shear",
        "mesh_name": "writer-smoke32x16x32" if is_smoke else "profile128x64x128",
        "mesh": profile_mesh,
        "profile_steps": profile_steps,
        "profile_dt_s": profile_dt_s,
        "profile_write_steps": profile_write_steps,
        "nu_add_m2_s": 0.0,
        "mpi_ranks": args.cpus,
    }
    case_dir = run_dir / "cases" / case["case_id"]
    metadata = create_v2_profile_case(case_dir, case)
    metadata.update(
        {
            "solver": "OpenCFD OpenFOAM v2512 interIsoFoam",
            "solver_image": IMAGE,
            "solver_image_id": image_id,
            "mpi_ranks": args.cpus,
            "classification": "exploratory CPU finite-shear, short MPI profiling case",
            "no_growth_claim": True,
        }
    )
    write_json(case_dir / "case-inputs.json", metadata)
    write_json(
        run_dir / "run.json",
        {
            "run_id": run_id,
            "created_utc": datetime.now(UTC).isoformat(),
            "status": "running",
            "classification": "CPU-only OpenFOAM MPI profile, finite-shear water-air VOF",
            "git_revision": git_revision,
            "git_dirty_before_run": bool(
                subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
            ),
            "solver_image": IMAGE,
            "solver_image_id": image_id,
            "gpu_requested": False,
            "cpu_count_per_case": args.cpus,
            "memory_limit_gib_per_case": args.memory_gib,
            "case_ids": [case["case_id"]],
            "intended_diagnostic": "writer dictionary smoke test; no growth-rate inference"
            if is_smoke
            else "50-step wall-time/MPI/native-phi-divPhi viability check; no growth-rate inference",
        },
    )
    print(
        f"PROFILE_SETUP cells={metadata['cell_count']} mesh={case['mesh']} steps={case['profile_steps']} "
        f"horizon_s={case['profile_steps'] * case['profile_dt_s']:.6g} ranks={args.cpus} artifact={case_dir}",
        flush=True,
    )
    execution = run_case(
        case_dir,
        metadata,
        image_id,
        args.cpus,
        args.memory_gib,
        args.timeout_s,
        mpi_ranks=None if is_smoke else args.cpus,
    )
    result = {
        "case_id": case["case_id"],
        "mesh": case["mesh"],
        "cell_count": metadata["cell_count"],
        "cells_per_shear_thickness": metadata["cells_per_shear_thickness"],
        "requested_steps": profile_steps,
        "requested_horizon_s": profile_steps * profile_dt_s,
        "mpi_ranks": args.cpus,
        "execution": execution,
        "native_phi_expected": str(case_dir / "<time>" / "phi"),
        "native_divPhi_expected": str(case_dir / "<time>" / "divPhi"),
        "case_inputs_sha256": sha256(case_dir / "case-inputs.json"),
    }
    if execution["status"] == "completed":
        time_dirs = []
        for child in case_dir.iterdir():
            if child.is_dir():
                try:
                    t = float(child.name)
                except ValueError:
                    continue
                if (child / "alpha.water").exists():
                    time_dirs.append((t, child))
        time_dirs.sort(key=lambda item: item[0])
        cell_volume = float(np.prod(LENGTHS) / metadata["cell_count"])
        diagnostics = []
        for time_value, time_dir in time_dirs:
            alpha = parse_scalar_field(time_dir / "alpha.water")
            div_path = time_dir / "divPhi"
            div_phi = parse_scalar_field(div_path) if div_path.exists() else None
            alpha_volume_modes = interface_mode_components(alpha, *metadata["mesh"])
            alpha05_modes = alpha05_interface_modes(alpha, *metadata["mesh"])
            row = {
                "time_s": time_value,
                "water_volume_m3": float(alpha.sum() * cell_volume),
                "alpha_min": float(alpha.min()),
                "alpha_max": float(alpha.max()),
                "alpha_mode_amplitude_m": alpha_volume_modes["amplitudes"]["symmetric"],
                "alpha05_mode_amplitude_m": alpha05_modes["amplitudes_m"]["symmetric"],
                "alpha05_branch_coverage": alpha05_modes["coverage_fraction"],
                "divPhi_written": div_phi is not None,
                "max_abs_divPhi_s_inv": float(np.max(np.abs(div_phi)))
                if div_phi is not None
                else None,
                "sum_V_divPhi_m3_s": float(div_phi.sum() * cell_volume)
                if div_phi is not None
                else None,
                "sum_V_abs_divPhi_m3_s": float(np.abs(div_phi).sum() * cell_volume)
                if div_phi is not None
                else None,
                "sum_V_alpha_divPhi_m3_s": float(np.dot(alpha, div_phi) * cell_volume)
                if div_phi is not None
                else None,
            }
            diagnostics.append(row)
        result["snapshot_diagnostics"] = diagnostics
        result["native_phi_and_divPhi_present_all_snapshots"] = bool(
            any(row["divPhi_written"] for row in diagnostics)
            and all(
                row["divPhi_written"] and (p / "phi").exists()
                for (_, p), row in zip(time_dirs, diagnostics, strict=True)
                if row["time_s"] > 0.0
            )
        )
        with (case_dir / "flux_divergence.csv").open("w", newline="") as stream:
            fields = [
                "time_s",
                "sum_V_div_phi_m3_s",
                "sum_V_abs_div_phi_m3_s",
                "max_abs_div_phi_s_inv",
                "sum_V_alpha_div_phi_m3_s",
                "water_volume_m3",
                "alpha_mode_amplitude_m",
                "alpha05_mode_amplitude_m",
                "cell_count",
                "cell_volume_m3",
                "physical_boundary_phi_m3_s",
                "excluded_coupled_patch_names",
            ]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in diagnostics:
                if not row["divPhi_written"]:
                    continue
                writer.writerow(
                    {
                        "time_s": row["time_s"],
                        "sum_V_div_phi_m3_s": row["sum_V_divPhi_m3_s"],
                        "sum_V_abs_div_phi_m3_s": row["sum_V_abs_divPhi_m3_s"],
                        "max_abs_div_phi_s_inv": row["max_abs_divPhi_s_inv"],
                        "sum_V_alpha_div_phi_m3_s": row["sum_V_alpha_divPhi_m3_s"],
                        "water_volume_m3": row["water_volume_m3"],
                        "alpha_mode_amplitude_m": row["alpha_mode_amplitude_m"],
                        "alpha05_mode_amplitude_m": row["alpha05_mode_amplitude_m"],
                        "cell_count": metadata["cell_count"],
                        "cell_volume_m3": cell_volume,
                        "physical_boundary_phi_m3_s": 0.0,
                        "excluded_coupled_patch_names": "xMin;xMax;yMin;yMax;zMin;zMax",
                    }
                )
        write_json(case_dir / "profile-diagnostics.json", result)
    write_json(run_dir / "summary.json", {"cases": [result]})
    run_manifest = json.loads((run_dir / "run.json").read_text())
    run_manifest.update(finished_utc=datetime.now(UTC).isoformat(), status=execution["status"])
    write_json(run_dir / "run.json", run_manifest)
    print(f"PROFILE_ARTIFACT run={run_dir} status={execution['status']}", flush=True)
    return 0 if execution["status"] == "completed" else 1


def load_v2_eigenpair(npz_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Load the immutable sampled eigenmode arrays and their JSON metadata."""
    manifest = json.loads(manifest_path.read_text())
    with np.load(npz_path, allow_pickle=False) as archive:
        result = {name: archive[name].copy() for name in archive.files}
    result["metadata"] = manifest["eigenpair"]["metadata"]
    return result


def _fit_complex_mode(
    times: np.ndarray, modes: list[complex], mask: np.ndarray
) -> dict[str, float | int | None]:
    values = np.asarray(modes, dtype=np.complex128)
    valid = mask & np.isfinite(values.real) & np.isfinite(values.imag) & (np.abs(values) > 1e-12)
    if int(valid.sum()) < 3:
        return {"growth_s_inv": None, "phase_rate_rad_s": None, "sample_count": int(valid.sum())}
    selected_times = times[valid]
    growth = np.polyfit(selected_times, np.log(np.abs(values[valid])), 1)[0]
    phase = np.polyfit(selected_times, np.unwrap(np.angle(values[valid])), 1)[0]
    return {
        "growth_s_inv": float(growth),
        "phase_rate_rad_s": float(phase),
        "sample_count": int(valid.sum()),
    }


def analyze_v2_case_outputs(
    case_dir: Path,
    case: dict[str, Any],
    metadata: dict[str, Any],
    execution: dict[str, Any],
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write shared two-observer, native-flux, and conservation diagnostics."""
    nx, ny, nz = case["mesh"]
    lengths = tuple(case.get("domain_m", V2_LENGTHS))
    cell_volume = float(np.prod(lengths) / metadata["cell_count"])
    alpha_initial = parse_scalar_field(case_dir / "0" / "alpha.water")
    snapshots: list[tuple[float, np.ndarray, Path | None]] = [(0.0, alpha_initial, None)]
    time_dirs: list[tuple[float, Path]] = []
    for child in case_dir.iterdir():
        if not child.is_dir() or child.name in {"0", "constant", "system"}:
            continue
        try:
            time_value = float(child.name)
        except ValueError:
            continue
        if time_value > 0 and (child / "alpha.water").is_file():
            time_dirs.append((time_value, child))
    for time_value, time_dir in sorted(time_dirs):
        snapshots.append((time_value, parse_scalar_field(time_dir / "alpha.water"), time_dir))

    water_volume_0 = float(alpha_initial.sum() * cell_volume)
    diagnostic_rows: list[dict[str, Any]] = []
    flux_rows: list[dict[str, Any]] = []
    mode_history: dict[str, list[complex]] = {
        key: []
        for key in (
            "alpha_volume_lower",
            "alpha_volume_upper",
            "alpha_volume_symmetric",
            "alpha_volume_antisymmetric",
            "alpha05_lower",
            "alpha05_upper",
            "alpha05_symmetric",
            "alpha05_antisymmetric",
        )
    }
    final_spectra: dict[str, np.ndarray] | None = None
    divergence_maxs: list[float] = []
    divergence_rms: list[float] = []
    for time_value, alpha, time_dir in snapshots:
        volume_modes = interface_mode_components(alpha, nx, ny, nz)
        contour_modes = alpha05_interface_modes(alpha, nx, ny, nz)
        contour = dict(contour_modes["modes"])
        if all(name in contour for name in ("lower", "upper")):
            contour["antisymmetric"] = 0.5 * (contour["lower"] - contour["upper"])
        velocity_path = case_dir / "0" / "U" if time_dir is None else time_dir / "U"
        if velocity_path.is_file():
            velocity = parse_vector_field(velocity_path)
            div_max, div_rms = periodic_divergence_max(velocity, nx, ny, nz)
        else:
            div_max, div_rms = float("nan"), float("nan")
        divergence_maxs.append(div_max)
        divergence_rms.append(div_rms)
        volume = float(alpha.sum() * cell_volume)
        row: dict[str, Any] = {
            "time_s": time_value,
            "water_volume_m3": volume,
            "water_volume_relative_drift": (volume - water_volume_0) / water_volume_0,
            "alpha_min": float(alpha.min()),
            "alpha_max": float(alpha.max()),
            "max_abs_central_divergence_s_inv": div_max,
            "rms_central_divergence_s_inv": div_rms,
            "alpha05_branch_coverage": contour_modes["coverage_fraction"],
            "relative_interface_phase_rad": contour_modes["relative_lower_upper_phase_rad"],
            "phi_written": bool(time_dir is not None and (time_dir / "phi").is_file()),
            "divPhi_written": bool(time_dir is not None and (time_dir / "divPhi").is_file()),
        }
        for component in ("lower", "upper", "symmetric", "antisymmetric"):
            mode = volume_modes["modes"][component]
            row[f"alpha_volume_{component}_amplitude_m"] = float(abs(mode))
            row[f"alpha_volume_{component}_phase_rad"] = float(np.angle(mode))
            mode_history[f"alpha_volume_{component}"].append(mode)
            if component in contour:
                contour_mode = complex(contour[component])
                row[f"alpha05_{component}_amplitude_m"] = float(abs(contour_mode))
                row[f"alpha05_{component}_phase_rad"] = float(np.angle(contour_mode))
                mode_history[f"alpha05_{component}"].append(contour_mode)
        row["alpha_volume_mode_amplitude_m"] = row["alpha_volume_symmetric_amplitude_m"]
        row["alpha05_mode_amplitude_m"] = row["alpha05_symmetric_amplitude_m"]
        row["symmetric_mode_amplitude_m"] = row["alpha_volume_symmetric_amplitude_m"]
        diagnostic_rows.append(row)
        final_spectra = volume_modes["spectra"]

        if time_dir is not None and (time_dir / "divPhi").is_file():
            div_phi = parse_scalar_field(time_dir / "divPhi")
            flux_rows.append(
                {
                    "time_s": time_value,
                    "sum_V_div_phi_m3_s": float(div_phi.sum() * cell_volume),
                    "sum_V_abs_div_phi_m3_s": float(np.abs(div_phi).sum() * cell_volume),
                    "max_abs_div_phi_s_inv": float(np.max(np.abs(div_phi))),
                    "sum_V_alpha_div_phi_m3_s": float(np.dot(alpha, div_phi) * cell_volume),
                    "water_volume_m3": volume,
                    "alpha_mode_amplitude_m": row["alpha_volume_mode_amplitude_m"],
                    "alpha05_mode_amplitude_m": row["alpha05_mode_amplitude_m"],
                    "cell_count": metadata["cell_count"],
                    "cell_volume_m3": cell_volume,
                    "physical_boundary_phi_m3_s": 0.0,
                    "excluded_coupled_patch_names": "xMin;xMax;yMin;yMax;zMin;zMax",
                }
            )

    with (case_dir / "amplitude_time.csv").open("w", newline="") as stream:
        if diagnostic_rows:
            writer = csv.DictWriter(stream, fieldnames=list(diagnostic_rows[0]))
            writer.writeheader()
            writer.writerows(diagnostic_rows)
    flux_fields = [
        "time_s",
        "sum_V_div_phi_m3_s",
        "sum_V_abs_div_phi_m3_s",
        "max_abs_div_phi_s_inv",
        "sum_V_alpha_div_phi_m3_s",
        "water_volume_m3",
        "alpha_mode_amplitude_m",
        "alpha05_mode_amplitude_m",
        "cell_count",
        "cell_volume_m3",
        "physical_boundary_phi_m3_s",
        "excluded_coupled_patch_names",
    ]
    with (case_dir / "flux_divergence.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=flux_fields)
        writer.writeheader()
        writer.writerows(flux_rows)
    if final_spectra is not None:
        with (case_dir / "final_mode_spectrum.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            components = ("lower", "upper", "symmetric", "antisymmetric")
            writer.writerow(
                ["streamwise_mode", "wavenumber_rad_m"]
                + [f"alpha_volume_{name}_amplitude_m" for name in components]
            )
            for mode in range(len(final_spectra["symmetric"])):
                writer.writerow(
                    [mode, 2.0 * math.pi * mode / lengths[0]]
                    + [float(final_spectra[name][mode]) for name in components]
                )

    times = np.asarray([row["time_s"] for row in diagnostic_rows], dtype=np.float64)
    fit_start, fit_end = case.get("fit_window_s", V2_FIT_WINDOW_S)
    fit_mask = (times >= fit_start) & (times <= fit_end)
    transient_end = min(float(fit_start), 0.002)
    transient_mask = times <= transient_end
    fits = {
        "transient_through_s": transient_end,
        "transient": {
            observer: _fit_complex_mode(times, values, transient_mask)
            for observer, values in (
                ("alpha_volume", mode_history["alpha_volume_symmetric"]),
                ("alpha05", mode_history["alpha05_symmetric"]),
            )
        },
        "declared_window_s": [float(fit_start), float(fit_end)],
        "declared_window": {
            observer: _fit_complex_mode(times, values, fit_mask)
            for observer, values in (
                ("alpha_volume", mode_history["alpha_volume_symmetric"]),
                ("alpha05", mode_history["alpha05_symmetric"]),
            )
        },
    }
    sigma = complex(_eigen_value(reference, "sigma")) if reference is not None else None
    expected = (
        {"growth_s_inv": float(sigma.real), "phase_rate_rad_s": float(sigma.imag)}
        if sigma is not None
        else None
    )
    continuity = continuity_residuals(case_dir / "log.interIsoFoam")
    solver_log = (
        (case_dir / "log.interIsoFoam").read_text(errors="replace")
        if (case_dir / "log.interIsoFoam").exists()
        else ""
    )
    finite_dt = [float(value) for value in re.findall(r"\bdeltaT\s*=\s*([-+0-9.eE]+)", solver_log)]
    summary = {
        "case_id": case["case_id"],
        "classification": metadata["classification"],
        "solver_status": execution["status"],
        "solver_exit_code": execution.get("exit_code"),
        "solver_elapsed_wall_s": execution.get("elapsed_wall_s"),
        "cell_count": metadata["cell_count"],
        "mesh": case["mesh"],
        "cells_per_finite_shear_thickness": metadata["cells_per_finite_shear_thickness"],
        "mpi_ranks": case["mpi_ranks"],
        "measured_horizon_s": diagnostic_rows[-1]["time_s"] if diagnostic_rows else 0.0,
        "requested_horizon_s": case["horizon_s"],
        "expected_water_volume_m3": metadata["water_volume_expected_m3"],
        "alpha_initial_volume_m3": water_volume_0,
        "max_abs_water_volume_drift_relative": max(
            (abs(row["water_volume_relative_drift"]) for row in diagnostic_rows), default=None
        ),
        "alpha_bounds": [
            min((row["alpha_min"] for row in diagnostic_rows), default=None),
            max((row["alpha_max"] for row in diagnostic_rows), default=None),
        ],
        "alpha_bounded_all_snapshots": bool(
            diagnostic_rows
            and min(row["alpha_min"] for row in diagnostic_rows) >= -1e-10
            and max(row["alpha_max"] for row in diagnostic_rows) <= 1.0 + 1e-10
        ),
        "initial_mode_amplitudes_m": {
            "alpha_volume": diagnostic_rows[0]["alpha_volume_symmetric_amplitude_m"]
            if diagnostic_rows
            else None,
            "alpha05": diagnostic_rows[0]["alpha05_symmetric_amplitude_m"]
            if diagnostic_rows
            else None,
        },
        "final_mode_amplitudes_m": {
            "alpha_volume": diagnostic_rows[-1]["alpha_volume_symmetric_amplitude_m"]
            if diagnostic_rows
            else None,
            "alpha05": diagnostic_rows[-1]["alpha05_symmetric_amplitude_m"]
            if diagnostic_rows
            else None,
        },
        "max_abs_central_divergence_s_inv": max(divergence_maxs, default=None),
        "max_rms_central_divergence_s_inv": max(divergence_rms, default=None),
        "max_abs_openfoam_continuity_global": max(
            (abs(row["global"]) for row in continuity), default=None
        ),
        "max_abs_openfoam_continuity_local_sum": max(
            (abs(row["sum_local"]) for row in continuity), default=None
        ),
        "dt_min_s": min(finite_dt, default=None),
        "dt_max_s": max(finite_dt, default=None),
        "native_flux_snapshot_count": len(flux_rows),
        "all_nonzero_snapshots_have_phi_and_divPhi": bool(
            time_dirs
            and all(
                (time_dir / "phi").is_file() and (time_dir / "divPhi").is_file()
                for _, time_dir in time_dirs
            )
        ),
        "native_flux_rows": flux_rows,
        "container_resources": summarize_docker_resources(case_dir / "resources.jsonl"),
        "initial_final_frame": write_alpha_snapshot_frame(case_dir, snapshots, nx, ny, nz),
        "mode_fits": fits,
        "finite_thickness_inviscid_eigenvalue_s_inv": expected,
        "finite_thickness_eigenpair_metadata": (
            _eigen_value(reference, "metadata") if reference is not None else None
        ),
        "snapshots": diagnostic_rows,
        "gpu_requested": False,
        "interpretation_limits": [
            "Finite-thickness eigenvalue is inviscid and assumes sharp density jumps, sigma=0, zero gravity, and a 2-D periodic mode.",
            "OpenFOAM run has molecular viscosity; fit differences from the inviscid reference are diagnostic, not an acceptance gate.",
            "The added constant kinematic viscosity is a damping surrogate, not RANS or LES.",
            "This is an isolated periodic shear mechanism test, not a Dash-8 aircraft or source reproduction.",
        ],
    }
    write_json(case_dir / "diagnostics.json", summary)
    return summary


def run_v2_advection_control(args: argparse.Namespace) -> int:
    """Run a matched zero-shear/advection control while the eigenmode is prepared."""
    run_id = args.run_id or f"cpu-interface-growth-v2-advection-control-{utc_stamp()}"
    run_dir = ROOT / "results" / "runs" / run_id
    if run_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {run_dir}")
    run_dir.mkdir(parents=True)
    shutil.copy2(Path(__file__), run_dir / "runner-snapshot.py")
    image_id = docker_image_id()
    case = {
        "case_id": "advection-control128",
        "variant": "advection_control",
        "mesh_name": "coarse128x64x128",
        "mesh": [128, 64, 128],
        "domain_m": list(V2_LENGTHS),
        "mode_number": 1,
        "seed_amplitude_m": 5.0e-5,
        "nu_add_m2_s": 0.0,
        "horizon_s": 0.002,
        "write_interval_s": 0.00025,
        "mpi_ranks": args.cpus,
        "control": "uniform 25 m/s advection, no shear, no eigenmode velocity perturbation",
    }
    case_dir = run_dir / "cases" / case["case_id"]
    metadata = create_v2_growth_case(case_dir, case, eigenpair=None)
    metadata.update(
        solver_image=IMAGE,
        solver_image_id=image_id,
        classification="exploratory matched seed advection control; not an instability growth case",
        gpu_requested=False,
    )
    write_json(case_dir / "case-inputs.json", metadata)
    manifest = {
        "run_id": run_id,
        "created_utc": datetime.now(UTC).isoformat(),
        "status": "running",
        "classification": "CPU-only finite-thickness alpha reconstruction/advection control",
        "git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_dirty_before_run": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        ),
        "solver_image": IMAGE,
        "solver_image_id": image_id,
        "cpu_count_per_case": args.cpus,
        "memory_limit_gib_per_case": args.memory_gib,
        "gpu_requested": False,
        "case_ids": [case["case_id"]],
        "intended_diagnostic": "zero-shear uniform-advection control for the same 0.05 mm sine displacement; quantify reconstruction drift",
    }
    write_json(run_dir / "run.json", manifest)
    execution = run_case(
        case_dir,
        metadata,
        image_id,
        args.cpus,
        args.memory_gib,
        args.timeout_s,
        mpi_ranks=args.cpus,
    )
    metrics = analyze_v2_case_outputs(case_dir, case, metadata, execution)
    write_json(run_dir / "summary.json", {"cases": [metrics]})
    manifest.update(finished_utc=datetime.now(UTC).isoformat(), status=execution["status"])
    write_json(run_dir / "run.json", manifest)
    print(f"V2_CONTROL_ARTIFACT run={run_dir} status={execution['status']}", flush=True)
    return 0 if execution["status"] == "completed" else 1


def reanalyze_run(run_id: str) -> int:
    if not re.fullmatch(r"cpu-interface-growth-[A-Za-z0-9_.-]{1,60}", run_id):
        raise ValueError("--reanalyze-run must name an existing cpu-interface-growth-* bundle")
    run_dir = ROOT / "results" / "runs" / run_id
    manifest_path = run_dir / "run.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no run manifest at {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    results: list[dict[str, Any]] = []
    for case_dir in sorted((run_dir / "cases").glob("*")):
        input_path = case_dir / "case-inputs.json"
        execution_path = case_dir / "execution.json"
        if not input_path.is_file() or not execution_path.is_file():
            continue
        case = json.loads(input_path.read_text())
        execution = json.loads(execution_path.read_text())
        if "exit_code" not in execution or not (case_dir / "0/alpha.water").is_file():
            continue
        metrics = analyze_case(case_dir, case, execution)
        results.append(metrics)
    if not results:
        raise RuntimeError(f"no executed cases could be reanalyzed under {run_dir}")
    write_json(run_dir / "summary.json", {"cases": results})
    write_run_plot(run_dir, results)
    original_record_path = run_dir / "experiment-record.json"
    current_record_path = ROOT / "cases/cpu_interface_growth/experiment.json"
    runner_snapshot_path = run_dir / "runner-snapshot.py"
    if original_record_path.is_file() and current_record_path.is_file() and results:
        original_record = json.loads(original_record_path.read_text())
        current_record = json.loads(current_record_path.read_text())
        original_seed = original_record.get("seeded_mode", {}).get(
            "interface_displacement_amplitude_m"
        )
        current_seed = current_record.get("seeded_mode", {}).get(
            "interface_displacement_amplitude_m"
        )
        runner_text = (
            runner_snapshot_path.read_text(errors="replace")
            if runner_snapshot_path.is_file()
            else ""
        )
        runner_seed_match = re.search(
            r"^SEED_AMPLITUDE\s*=\s*([-+0-9.eE]+)", runner_text, re.MULTILINE
        )
        runner_seed = float(runner_seed_match.group(1)) if runner_seed_match else None
        if (
            original_seed is not None
            and runner_seed is not None
            and not math.isclose(float(original_seed), runner_seed, rel_tol=1e-12)
        ):
            write_json(
                run_dir / "record-correction.json",
                {
                    "classification": "input-record discrepancy audit; solver inputs and preserved records were not rewritten",
                    "original_copied_record_seed_amplitude_m": original_seed,
                    "runner_snapshot_seed_amplitude_m": runner_seed,
                    "current_source_record_seed_amplitude_m": current_seed,
                    "measured_initial_mode_amplitude_m_by_case": {
                        item["case_id"]: item.get("initial_mode_amplitude_measured_m")
                        for item in results
                    },
                    "runner_snapshot_sha256": sha256(runner_snapshot_path),
                    "original_record_sha256": sha256(original_record_path),
                    "current_source_record_sha256": sha256(current_record_path),
                    "note": "The saved original record is retained for provenance. The executable runner snapshot and measured initial mode indicate the amplitude actually used; the owned source experiment record has been corrected for future cases.",
                },
            )
    manifest.update(
        analysis_refreshed_utc=datetime.now(UTC).isoformat(),
        result_count=len(results),
        completed_case_count=sum(item.get("solver_status") == "completed" for item in results),
        runner_snapshot_sha256=(
            sha256(run_dir / "runner-snapshot.py")
            if (run_dir / "runner-snapshot.py").is_file()
            else None
        ),
        experiment_record_sha256=(
            sha256(run_dir / "experiment-record.json")
            if (run_dir / "experiment-record.json").is_file()
            else None
        ),
        analysis_source_path=str(Path(__file__).resolve().relative_to(ROOT)),
        analysis_source_sha256=sha256(Path(__file__).resolve()),
    )
    if all(item.get("solver_status") == "completed" for item in results):
        manifest["status"] = "completed_exploratory"
    write_json(manifest_path, manifest)
    print(f"REANALYZED run={run_dir} case_count={len(results)}", flush=True)
    return 0


def write_run_plot(run_dir: Path, all_metrics: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (axis, phase_axis) = plt.subplots(2, 1, figsize=(8.2, 6.2), sharex=True)
    for metrics in all_metrics:
        rows = metrics.get("snapshots", [])
        if not rows:
            continue
        time_s = [row["time_s"] for row in rows]
        amplitude = [max(row["symmetric_mode_amplitude_m"], 1e-12) for row in rows]
        line = axis.plot(time_s, amplitude, marker="o", markersize=2.0, label=metrics["case_id"])[0]
        phase_axis.plot(
            time_s,
            [row["relative_interface_phase_rad"] for row in rows],
            color=line.get_color(),
        )
    axis.set_yscale("log")
    axis.set_ylabel("symmetric mode amplitude [m]")
    axis.set_title("Seeded interface mode and relative surface phase — exploratory CPU diagnostic")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend(fontsize=7, loc="best")
    phase_axis.axhline(0.0, color="black", linewidth=0.7, alpha=0.5)
    phase_axis.set_xlabel("time [s]")
    phase_axis.set_ylabel("lower/upper phase difference [rad]")
    phase_axis.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(run_dir / "amplitude_vs_time.png", dpi=160)
    plt.close(fig)


def run(args: argparse.Namespace) -> int:
    cases = case_definitions(not args.sweep)
    run_id = args.run_id or f"cpu-interface-growth-{utc_stamp()}"
    run_dir = ROOT / "results" / "runs" / run_id
    if run_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {run_dir}")
    run_dir.mkdir(parents=True)
    shutil.copy2(Path(__file__), run_dir / "runner-snapshot.py")
    image_id = docker_image_id()
    git_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    git_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    case_template = ROOT / "cases/cpu_interface_growth/experiment.json"
    case_template_hash = sha256(case_template)
    run_manifest: dict[str, Any] = {
        "run_id": run_id,
        "created_utc": datetime.now(UTC).isoformat(),
        "classification": "exploratory CPU finite-shear water-air interface-instability diagnostic",
        "git_revision": git_revision,
        "git_dirty_before_run": git_dirty,
        "case_template_sha256": case_template_hash,
        "solver_image": IMAGE,
        "solver_image_id": image_id,
        "gpu_requested": False,
        "cpu_count_per_case": args.cpus,
        "memory_limit_gib_per_case": args.memory_gib,
        "mode": "sweep" if args.sweep else "pilot",
        "status": "prepared_only" if args.prepare_only else "running",
        "case_ids": [case["case_id"] for case in cases],
    }
    write_json(run_dir / "run.json", run_manifest)
    results: list[dict[str, Any]] = []
    for case in cases:
        case_dir = run_dir / "cases" / case["case_id"]
        metadata = create_case(case_dir, case)
        if args.prepare_only:
            results.append({"case_id": case["case_id"], "status": "prepared_only", **metadata})
            continue
        execution = run_case(
            case_dir, metadata, image_id, args.cpus, args.memory_gib, args.timeout_s
        )
        try:
            metrics = analyze_case(case_dir, metadata, execution)
        except (OSError, ValueError, IndexError) as error:
            metrics = {
                "case_id": case["case_id"],
                "solver_status": execution["status"],
                "analysis_error": f"{type(error).__name__}: {error}",
                "diagnostics_path": str(case_dir),
            }
            write_json(case_dir / "diagnostics.json", metrics)
        results.append(metrics)
        write_json(run_dir / "summary.json", {"cases": results})
        if execution["status"] != "completed":
            run_manifest.update(status="failed", failed_case=case["case_id"])
            write_json(run_dir / "run.json", run_manifest)
            break
    successful = len(results) == len(cases) and all(
        r.get("solver_status", r.get("status")) in {"completed", "prepared_only"} for r in results
    )
    if not args.prepare_only and results:
        write_run_plot(run_dir, results)
    run_manifest.update(
        status=(
            "prepared_only"
            if args.prepare_only
            else ("completed_exploratory" if successful else "failed")
        ),
        finished_utc=datetime.now(UTC).isoformat(),
        completed_case_count=sum(r.get("solver_status") == "completed" for r in results),
        result_count=len(results),
        diagnostics="per-case diagnostics.json, amplitude_time.csv, final_mode_spectrum.csv",
    )
    write_json(run_dir / "summary.json", {"cases": results})
    write_json(run_dir / "run.json", run_manifest)
    print(f"ARTIFACT run={run_dir} status={run_manifest['status']}", flush=True)
    return 0 if args.prepare_only or successful else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--pilot",
        action="store_true",
        help="run the small 32x16x32 molecular-shear trial (default)",
    )
    mode.add_argument(
        "--sweep",
        action="store_true",
        help="run advection, molecular-shear, and added-viscosity variants on both meshes",
    )
    mode.add_argument(
        "--reanalyze-run",
        help="recompute diagnostics/plot from a preserved run without launching a solver",
    )
    mode.add_argument(
        "--v2-smoke",
        action="store_true",
        help="run a tiny MPI native-div(phi) output smoke before the V2 profile",
    )
    mode.add_argument(
        "--v2-mpi-profile",
        action="store_true",
        help="run a 50-step 128x64x128 MPI throughput/native-field profile",
    )
    mode.add_argument(
        "--v2-advection-control",
        action="store_true",
        help="run the 128x64x128 no-shear same-seed CPU control for 2 ms",
    )
    parser.add_argument(
        "--run-id",
        help="new results/runs/ directory name; existing directories are never overwritten",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="write cases and manifest without launching OpenFOAM",
    )
    parser.add_argument(
        "--cpus",
        type=int,
        default=1,
        help="CPU cores/MPI ranks allocated to each sequential solver case",
    )
    parser.add_argument(
        "--memory-gib", type=int, default=8, help="container memory limit for each case"
    )
    parser.add_argument(
        "--timeout-s", type=float, default=1800.0, help="wall-clock stop for each case"
    )
    args = parser.parse_args(argv)
    if (
        args.memory_gib < 1
        or not math.isfinite(args.timeout_s)
        or args.timeout_s <= 0
        or args.cpus < 1
        or args.cpus > 20
    ):
        parser.error("memory and timeout must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.reanalyze_run:
            return reanalyze_run(args.reanalyze_run)
        if args.v2_smoke or args.v2_mpi_profile:
            if args.v2_smoke and args.cpus != 1:
                raise ValueError("--v2-smoke uses one MPI rank")
            return run_v2_mpi_profile(args)
        if args.v2_advection_control:
            return run_v2_advection_control(args)
        return run(args)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(
            f"cpu interface-growth runner failed: {type(error).__name__}: {error}", file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
