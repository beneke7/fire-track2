#!/usr/bin/env python3
"""Build a bounded generic downward-release OpenFOAM AMR cost comparison."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "opencfd/openfoam-default:2512"
RANKS = 8
MEMORY_GIB = 32
END_TIME = 0.02
DELTA_T = 0.0001
SNAPSHOT_INTERVAL_STEPS = 50
DOMAIN = {"x": (-7.975, 7.975), "y": (-3.025, 3.025), "z": (0.0, 4.0)}
X_BREAKS = (-7.975, -3.0, -0.175, -0.025, 0.025, 0.175, 0.5, 7.975)
Y_BREAKS = (-3.025, -2.5, -1.025, -0.025, 0.025, 1.025, 2.5, 3.025)
NX = (25, 57, 3, 1, 3, 7, 37)
NY = (3, 30, 20, 1, 20, 30, 3)
NZ = 32
SLOT_NAMES = {(2, 2): "slot_01", (4, 2): "slot_02", (2, 4): "slot_03", (4, 4): "slot_04"}
PATCHES = ("slot_01", "slot_02", "slot_03", "slot_04", "airInlet", "airOutlet", "lowerOutlet")
REFINE_BOX = ((-3.0, -1.5, 2.5), (0.5, 1.5, 4.0))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def foam_header(name: str, cls: str = "dictionary", location: str | None = None) -> str:
    where = f'    location    "{location}";\n' if location else ""
    return (
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n"
        f"    class {cls};\n{where}    object {name};\n}}\n\n"
    )


def block_mesh_dict(variant: str) -> str:
    if variant == "static_localized":
        x_breaks = X_BREAKS
        x_cells = (25, 114, 6, 2, 6, 14, 37)
        y_breaks = (-3.025, -2.5, -1.5, -1.025, -0.025, 0.025, 1.025, 1.5, 2.5, 3.025)
        y_cells = (3, 20, 19, 40, 2, 40, 19, 20, 3)
        z_breaks = (0.0, 2.5, 4.0)
        z_cells = (20, 24)
        slot_names = {(2, 3): "slot_01", (4, 3): "slot_02", (2, 5): "slot_03", (4, 5): "slot_04"}
    else:
        x_breaks, x_cells = X_BREAKS, NX
        y_breaks, y_cells = Y_BREAKS, NY
        z_breaks, z_cells = DOMAIN["z"], (NZ,)
        slot_names = SLOT_NAMES

    def local_face(points: tuple[tuple[int, int, int], ...]) -> str:
        nx, ny = len(x_breaks), len(y_breaks)
        return "(" + " ".join(str(k * nx * ny + j * nx + i) for i, j, k in points) + ")"

    vertices = [
        f"    ({x:.8g} {y:.8g} {z:.8g})" for z in z_breaks for y in y_breaks for x in x_breaks
    ]
    blocks: list[str] = []
    patches: dict[str, list[str]] = {name: [] for name in slot_names.values()}
    patches["airPlate"] = []
    inlet: list[str] = []
    outlet: list[str] = []
    side_min: list[str] = []
    side_max: list[str] = []
    lower: list[str] = []
    for k in range(len(z_breaks) - 1):
        for j in range(len(y_breaks) - 1):
            for i in range(len(x_breaks) - 1):
                vertices_for_block = (
                    (i, j, k),
                    (i + 1, j, k),
                    (i + 1, j + 1, k),
                    (i, j + 1, k),
                    (i, j, k + 1),
                    (i + 1, j, k + 1),
                    (i + 1, j + 1, k + 1),
                    (i, j + 1, k + 1),
                )
                nx, ny = len(x_breaks), len(y_breaks)
                points = " ".join(
                    str(kk * nx * ny + jj * nx + ii) for ii, jj, kk in vertices_for_block
                )
                blocks.append(
                    f"    hex ({points}) ({x_cells[i]} {y_cells[j]} {z_cells[k]}) simpleGrading (1 1 1)"
                )
                if k == len(z_breaks) - 2:
                    top_name = slot_names.get((i, j), "airPlate")
                    patches[top_name].append(
                        local_face(
                            (
                                (i, j, k + 1),
                                (i + 1, j, k + 1),
                                (i + 1, j + 1, k + 1),
                                (i, j + 1, k + 1),
                            )
                        )
                    )
                if k == 0:
                    lower.append(
                        local_face(((i, j, k), (i, j + 1, k), (i + 1, j + 1, k), (i + 1, j, k)))
                    )
                if i == 0:
                    outlet.append(
                        local_face(((i, j, k), (i, j, k + 1), (i, j + 1, k + 1), (i, j + 1, k)))
                    )
                if i == len(x_breaks) - 2:
                    inlet.append(
                        local_face(
                            (
                                (i + 1, j, k),
                                (i + 1, j + 1, k),
                                (i + 1, j + 1, k + 1),
                                (i + 1, j, k + 1),
                            )
                        )
                    )
                if j == 0:
                    side_min.append(
                        local_face(((i, j, k), (i + 1, j, k), (i + 1, j, k + 1), (i, j, k + 1)))
                    )
                if j == len(y_breaks) - 2:
                    side_max.append(
                        local_face(
                            (
                                (i, j + 1, k),
                                (i, j + 1, k + 1),
                                (i + 1, j + 1, k + 1),
                                (i + 1, j + 1, k),
                            )
                        )
                    )

    boundary: list[str] = []
    for name, faces in patches.items():
        kind = "wall" if name == "airPlate" else "patch"
        boundary.append(
            f"    {name}\n    {{\n        type {kind};\n        faces\n        (\n"
            + "\n".join(f"            {item}" for item in faces)
            + "\n        );\n    }"
        )
    for name, kind, faces in (
        ("airInlet", "patch", inlet),
        ("airOutlet", "patch", outlet),
        ("sideMin", "symmetryPlane", side_min),
        ("sideMax", "symmetryPlane", side_max),
        ("lowerOutlet", "patch", lower),
    ):
        boundary.append(
            f"    {name}\n    {{\n        type {kind};\n        faces\n        (\n"
            + "\n".join(f"            {item}" for item in faces)
            + "\n        );\n    }"
        )
    return (
        foam_header("blockMeshDict")
        + "scale 1;\n\nvertices\n(\n"
        + "\n".join(vertices)
        + "\n);\n\nblocks\n(\n"
        + "\n".join(blocks)
        + "\n);\n\nedges ();\n\nboundary\n(\n"
        + "\n".join(boundary)
        + "\n);\n\nmergePatchPairs ();\n"
    )


def boundary_field(
    name: str, cls: str, dimensions: str, internal: str, patches: dict[str, str]
) -> str:
    entries = "\n".join(
        f"    {patch}\n    {{\n{contents}\n    }}" for patch, contents in patches.items()
    )
    return (
        foam_header(name, cls)
        + f"dimensions {dimensions};\n\ninternalField uniform {internal};\n\nboundaryField\n{{\n{entries}\n}}\n"
    )


def make_case(case: Path, variant: str) -> dict[str, Any]:
    for relative in ("0", "constant", "system"):
        (case / relative).mkdir(parents=True, exist_ok=True)
    source_u = (
        "        type uniformFixedValue;\n"
        f"        uniformValue table ((0 (0 0 -4.8)) ({END_TIME:g} (0 0 -4.8)));\n"
        "        value uniform (0 0 -4.8);"
    )
    u_patches = {name: source_u for name in SLOT_NAMES.values()}
    u_patches.update(
        {
            "airPlate": "        type noSlip;",
            "airInlet": "        type fixedValue;\n        value uniform (-50 0 0);",
            "airOutlet": "        type pressureInletOutletVelocity;\n        value uniform (-50 0 0);",
            "sideMin": "        type symmetryPlane;",
            "sideMax": "        type symmetryPlane;",
            "lowerOutlet": "        type pressureInletOutletVelocity;\n        value uniform (0 0 -4.8);",
        }
    )
    alpha_patches = {
        name: "        type fixedValue;\n        value uniform 1;" for name in SLOT_NAMES.values()
    }
    alpha_patches.update(
        {
            "airPlate": "        type zeroGradient;",
            "airInlet": "        type fixedValue;\n        value uniform 0;",
            "airOutlet": "        type inletOutlet;\n        inletValue uniform 0;\n        value uniform 0;",
            "sideMin": "        type symmetryPlane;",
            "sideMax": "        type symmetryPlane;",
            "lowerOutlet": "        type inletOutlet;\n        inletValue uniform 0;\n        value uniform 0;",
        }
    )
    p_patches = {
        name: "        type fixedFluxPressure;\n        value uniform 0;"
        for name in (*SLOT_NAMES.values(), "airPlate", "airInlet")
    }
    p_patches.update(
        {
            "airOutlet": "        type fixedValue;\n        value uniform 0;",
            "sideMin": "        type symmetryPlane;",
            "sideMax": "        type symmetryPlane;",
            "lowerOutlet": "        type fixedValue;\n        value uniform 0;",
        }
    )
    (case / "0" / "U").write_text(
        boundary_field("U", "volVectorField", "[0 1 -1 0 0 0 0]", "(-50 0 0)", u_patches)
    )
    (case / "0" / "alpha.water").write_text(
        boundary_field("alpha.water", "volScalarField", "[0 0 0 0 0 0 0]", "0", alpha_patches)
    )
    (case / "0" / "p_rgh").write_text(
        boundary_field("p_rgh", "volScalarField", "[1 -1 -2 0 0 0 0]", "0", p_patches)
    )
    (case / "constant" / "g").write_text(
        foam_header("g", "uniformDimensionedVectorField", "constant")
        + "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 -9.81);\n"
    )
    (case / "constant" / "transportProperties").write_text(
        foam_header("transportProperties", location="constant")
        + "phases (water air);\nwater { transportModel Newtonian; nu 1e-6; rho 1000; }\n"
        + "air { transportModel Newtonian; nu 1.48e-5; rho 1.225; }\nsigma 0.072;\n"
    )
    (case / "constant" / "turbulenceProperties").write_text(
        foam_header("turbulenceProperties", location="constant") + "simulationType laminar;\n"
    )
    (case / "constant" / "dynamicMeshDict").write_text(
        foam_header("dynamicMeshDict", location="constant")
        + (
            "dynamicFvMesh dynamicRefineFvMesh;\n\nrefineInterval 1;\nfield alpha.water;\n"
            "lowerRefineLevel 0.001;\nupperRefineLevel 0.999;\nunrefineLevel 0.001;\n"
            "nBufferLayers 1;\nmaxRefinement 1;\nmaxCells 1100000;\n"
            "correctFluxes ((phi none) (nHatf none) (rhoPhi none) (alphaPhi_ none) (ghf none) (phi0 none) (dVf_ none));\n"
            "dumpLevel true;\n"
            if variant == "dynamic_amr"
            else "dynamicFvMesh staticFvMesh;\n"
        )
    )
    (case / "system" / "controlDict").write_text(
        foam_header("controlDict", location="system")
        + "application interIsoFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\n"
        + f"endTime {END_TIME:g};\ndeltaT {DELTA_T:g};\nwriteControl timeStep;\nwriteInterval {SNAPSHOT_INTERVAL_STEPS};\n"
        + "purgeWrite 0;\nwriteFormat binary;\nwritePrecision 8;\nwriteCompression off;\ntimeFormat fixed;\ntimePrecision 6;\nrunTimeModifiable no;\n"
        + "adjustTimeStep no;\nmaxCo 0.5;\nmaxAlphaCo 0.25;\n\nfunctions\n{\n"
        + "    liquidInterface\n    {\n        type surfaces;\n        libs (geometricVoF sampling);\n        writeControl writeTime;\n"
        + "        surfaceFormat vtp;\n        fields (alpha.water U);\n        interpolationScheme cell;\n        surfaces\n        {\n            freeSurface\n            {\n                type interface;\n                interpolate false;\n            }\n        }\n    }\n"
        + "    waterVolume\n    {\n        type volFieldValue;\n        libs (fieldFunctionObjects);\n        writeControl timeStep;\n        writeInterval 1;\n        operation volIntegrate;\n        writeFields false;\n        fields (alpha.water);\n    }\n"
        + "".join(
            f"    {name}Flux\n    {{\n        type surfaceFieldValue;\n        libs (fieldFunctionObjects);\n        regionType patch;\n        name {name};\n        operation sum;\n        fields (phi alphaPhi_);\n        writeFields false;\n        executeControl timeStep;\n        executeInterval 1;\n        writeControl timeStep;\n        writeInterval 1;\n    }}\n"
            for name in PATCHES
        )
        + "}\n"
    )
    (case / "system" / "fvSchemes").write_text(
        foam_header("fvSchemes", location="system")
        + "ddtSchemes { default Euler; }\ngradSchemes { default Gauss linear; }\n"
        + "divSchemes { div(rhoPhi,U) Gauss limitedLinearV 1; div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear; }\n"
        + "laplacianSchemes { default Gauss linear corrected; }\ninterpolationSchemes { default linear; }\n"
        + "snGradSchemes { default corrected; }\nfluxRequired { default no; p_rgh; pcorr; alpha.water; }\n"
    )
    (case / "system" / "fvSolution").write_text(
        foam_header("fvSolution", location="system")
        + 'solvers { "alpha.water.*" { isoFaceTol 1e-6; surfCellTol 1e-6; nAlphaBounds 3; snapTol 1e-12; clip true; reconstructionScheme isoAlpha; writeFields true; nAlphaSubCycles 1; cAlpha 1; }\n'
        + '"pcorr.*" { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0; }\n'
        + "p_rgh { solver GAMG; smoother DICGaussSeidel; tolerance 1e-9; relTol 0.05; }\n"
        + "p_rghFinal { $p_rgh; tolerance 1e-9; relTol 0; }\nU { solver PBiCGStab; preconditioner DILU; tolerance 1e-6; relTol 0; } }\n"
        + "PIMPLE { momentumPredictor no; nCorrectors 3; nOuterCorrectors 1; nNonOrthogonalCorrectors 0; pRefCell 0; pRefValue 0; }\n"
    )
    (case / "system" / "decomposeParDict").write_text(
        foam_header("decomposeParDict", location="system")
        + f"numberOfSubdomains {RANKS};\nmethod simple;\ncoeffs {{ n ({RANKS} 1 1); }}\n"
    )
    (case / "system" / "blockMeshDict").write_text(block_mesh_dict(variant))
    mesh_cells = sum(NX) * sum(NY) * NZ
    final_cells = (204 * 166 * 44) if variant == "static_localized" else mesh_cells
    return {
        "variant": variant,
        "evidence_label": "exploratory CPU mesh-cost comparison; not validated plume physics",
        "solver": "OpenCFD OpenFOAM v2512 interIsoFoam (isoAdvector)",
        "domain_bounds_m": DOMAIN,
        "base_mesh_cells_expected": mesh_cells,
        "mesh_cells_expected": final_cells,
        "base_mesh_cells_by_axis": {"x": sum(NX), "y": sum(NY), "z": NZ},
        "static_refinement_box_m": REFINE_BOX if variant == "static_localized" else None,
        "amr_field": "alpha.water" if variant == "dynamic_amr" else None,
        "amr_max_refinement_levels": 1 if variant == "dynamic_amr" else 0,
        "amr_max_cells": 1100000 if variant == "dynamic_amr" else None,
        "finest_interface_cell_spacing_m": [0.025, 0.025, 0.0625],
        "four_slots": {
            "count": 4,
            "dimensions_each_m": [0.15, 1.0],
            "edge_gaps_m": [0.05, 0.05],
            "assumption": "project plan provisional dimensions; not measured Restas hardware",
        },
        "source": {
            "velocity_m_s": [0, 0, -4.8],
            "duration_s": END_TIME,
            "mass_flow_kg_s": 2880.0,
            "expected_mass_kg": 57.6,
            "assumption": "Calbrix Dash-8 peak velocity reused provisionally; not measured Restas discharge",
        },
        "crossflow_m_s": [-50, 0, 0],
        "fluids": {
            "water_rho_kg_m3": 1000,
            "water_nu_m2_s": 1e-6,
            "air_rho_kg_m3": 1.225,
            "air_nu_m2_s": 1.48e-5,
            "sigma_N_m": 0.072,
        },
        "gravity_m_s2": [0, 0, -9.81],
        "turbulence_model": "laminar, intentionally held fixed to isolate mesh-cost differences; not physically qualified at this Reynolds number",
        "time": {
            "start_s": 0,
            "end_s": END_TIME,
            "fixed_delta_t_s": DELTA_T,
            "steps": round(END_TIME / DELTA_T),
            "write_every_steps": SNAPSHOT_INTERVAL_STEPS,
        },
        "refinement_zone_assumption": "fixed box covers expected coherent nearfield drift for 20 ms; dynamic case follows alpha.water over the full domain",
        "resource_cap": {"mpi_ranks": RANKS, "docker_cpu_limit": RANKS, "memory_gib": MEMORY_GIB},
    }


def run_one(run_dir: Path, variant: str, image_id: str) -> dict[str, Any]:
    case = run_dir / "case"
    case.mkdir(parents=True, exist_ok=False)
    inputs = make_case(case, variant)
    inputs_path = run_dir / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n")
    source_paths = [
        Path(__file__),
        ROOT / "cases/restas_amr_probe/README.md",
        ROOT / "track2_aerial_drop_experiment_plan.md",
        ROOT / "cases/restas_four_slot/README.md",
        ROOT / "experiments/P0_RESTAS_CPU_VOF.md",
        ROOT / "docs/REFERENCES.md",
        ROOT / "scripts/run_local.py",
    ]
    manifest = {
        "run_id": run_dir.name,
        "started_utc": datetime.now(UTC).isoformat(),
        "git_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "git_worktree_dirty": bool(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
            ).stdout.strip()
        ),
        "source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in source_paths if p.is_file()},
        "inputs_sha256": sha256(inputs_path),
        "solver_image": IMAGE,
        "solver_image_id": image_id,
        "execution": {
            "mpi_ranks": RANKS,
            "docker_cpu_limit": RANKS,
            "docker_memory_limit_gib": MEMORY_GIB,
            "wall_timeout_s": 1800,
        },
        "scope": "short provisional nearfield AMR cost probe; no E0-E6 scientific gate or validation claim",
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    case_hashes = {
        str(p.relative_to(case)): sha256(p) for p in sorted(case.rglob("*")) if p.is_file()
    }
    manifest["case_input_sha256"] = case_hashes
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    mount = f"type=bind,src={case.resolve()},dst=/case"
    container_name = run_dir.name[:60]
    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        f"--cpus={RANKS}",
        f"--memory={MEMORY_GIB}g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        mount,
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        IMAGE,
        "-lc",
    ]
    steps = ["blockMesh", "checkMesh -allTopology -allGeometry"]
    steps += ["decomposePar -force", f"mpirun -np {RANKS} interIsoFoam -parallel", "reconstructPar"]
    shell = "source /usr/lib/openfoam/openfoam2512/etc/bashrc; set -euo pipefail; " + "; ".join(
        steps
    )
    log = run_dir / "openfoam-console.log"
    stats: list[dict[str, Any]] = []
    started = time.monotonic()
    proc: subprocess.Popen[bytes]
    with log.open("wb") as stream:
        proc = subprocess.Popen([*cmd, shell], stdout=stream, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            sample: dict[str, Any] = {"elapsed_s": round(time.monotonic() - started, 3)}
            stat = subprocess.run(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.CPUPerc}}|{{.MemUsage}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if stat.returncode == 0 and stat.stdout.strip():
                cpu, memory = stat.stdout.strip().split("|", 1)
                sample.update({"cpu_percent": cpu, "memory_usage_and_limit": memory})
            stats.append(sample)
            if time.monotonic() - started > 1800:
                subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=20)
                break
            time.sleep(2)
        exit_code = proc.wait()
    wall = time.monotonic() - started
    manifest.update(
        {
            "finished_utc": datetime.now(UTC).isoformat(),
            "wall_time_s": wall,
            "exit_code": exit_code,
            "docker_resource_samples": stats,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    report = summarize(run_dir, inputs, manifest)
    report_path = run_dir / "probe-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (run_dir / "run-sha256.json").write_text(
        json.dumps(
            {
                str(p.relative_to(run_dir)): sha256(p)
                for p in sorted(run_dir.rglob("*"))
                if p.is_file() and p.name != "run-sha256.json"
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(
        f"{variant}: exit={exit_code}, wall={wall:.1f}s, cells={report['mesh']['initial_cells']} -> {report['mesh']['final_cells']}, report={report_path.relative_to(ROOT)}",
        flush=True,
    )
    return report


def parse_flux(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            rows.append((float(parts[0]), float(parts[2])))
        except ValueError:
            continue
    return rows


def summarize(run_dir: Path, inputs: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    log = (
        (run_dir / "openfoam-console.log").read_text(errors="replace")
        if (run_dir / "openfoam-console.log").exists()
        else ""
    )
    times = [float(x) for x in re.findall(r"^Time = ([0-9.eE+-]+)\s*$", log, re.M)]
    exec_times = [float(x) for x in re.findall(r"^ExecutionTime = ([0-9.eE+-]+)\s*s", log, re.M)]
    pressure = [
        int(x) for x in re.findall(r"GAMG:\s+Solving for p_rgh,.*?No Iterations (\d+)", log)
    ]
    cell_rows = []
    current = None
    for line in log.splitlines():
        match = re.match(r"Time = ([0-9.eE+-]+)", line)
        if match:
            current = float(match.group(1))
        cell_match = re.search(r"Refined from \d+ to (\d+) cells\.", line)
        if cell_match:
            cell_rows.append(
                {"time_s": current, "global_cells_after_refine": int(cell_match.group(1))}
            )
    mesh_ok = "Mesh OK." in log
    inventory_rows = []
    for path in sorted((run_dir / "case/postProcessing/waterVolume").glob("*/volFieldValue.dat")):
        for line in path.read_text(errors="replace").splitlines():
            vals = line.split()
            if len(vals) >= 2:
                try:
                    inventory_rows.append((float(vals[0]), float(vals[1])))
                except ValueError:
                    pass
    inventory_rows.sort()
    fluxes = {
        patch: parse_flux(
            next(
                iter(
                    (run_dir / f"case/postProcessing/{patch}Flux").glob("*/surfaceFieldValue.dat")
                ),
                Path(""),
            )
        )
        for patch in PATCHES
    }
    source_rows = [row for patch in PATCHES[:4] for row in fluxes[patch]]
    dt = DELTA_T
    source_volume = -sum(value for _, value in source_rows) * dt
    outward_volume = (
        sum(max(0.0, value) for patch in PATCHES[4:] for _, value in fluxes[patch]) * dt
    )
    inward_open_volume = (
        sum(max(0.0, -value) for patch in PATCHES[4:] for _, value in fluxes[patch]) * dt
    )
    observed_volume = inventory_rows[-1][1] if inventory_rows else None
    residual = source_volume + inward_open_volume - outward_volume - (observed_volume or 0.0)
    sample_stats = manifest.get("docker_resource_samples", [])
    memory_gib: list[float] = []
    cpu_percent: list[float] = []
    for sample in sample_stats:
        try:
            cpu_percent.append(float(sample.get("cpu_percent", "0%").rstrip("%")))
            match = re.match(
                r"([0-9.]+)\s*(B|KiB|MiB|GiB)", sample.get("memory_usage_and_limit", "")
            )
            if match:
                factor = {"B": 2**-30, "KiB": 2**-20, "MiB": 2**-10, "GiB": 1}[match.group(2)]
                memory_gib.append(float(match.group(1)) * factor)
        except (ValueError, AttributeError):
            pass
    sizes = [p.stat().st_size for p in run_dir.rglob("*") if p.is_file()]
    initial_cells = None
    check_match = re.search(r"^    cells:\s*(\d+)\s*$", log, re.M)
    if check_match:
        initial_cells = int(check_match.group(1))
    final_cells = cell_rows[-1]["global_cells_after_refine"] if cell_rows else initial_cells
    return {
        "run_id": run_dir.name,
        "variant": inputs["variant"],
        "solver_exit_code": manifest.get("exit_code"),
        "mesh": {
            "check_mesh_passed": mesh_ok,
            "initial_cells": initial_cells,
            "final_cells": final_cells,
            "dynamic_cells_by_time": cell_rows,
            "refinement_level_histogram_from_saved_fields": "pending post-processing",
        },
        "time": {
            "last_solver_time_s": max(times, default=None),
            "solver_time_rows": len(times),
            "fixed_delta_t_s": dt,
            "latest_execution_time_s": exec_times[-1] if exec_times else None,
            "mean_pressure_iterations_per_solve": sum(pressure) / len(pressure)
            if pressure
            else None,
            "pressure_solve_count": len(pressure),
            "pressure_iteration_total": sum(pressure),
            "pressure_time_share_measured": False,
        },
        "resources": {
            "wall_time_s": manifest.get("wall_time_s"),
            "peak_sampled_memory_gib": max(memory_gib, default=None),
            "peak_sampled_cpu_percent": max(cpu_percent, default=None),
            "output_bytes_before_render": sum(sizes),
            "resource_sample_count": len(sample_stats),
        },
        "liquid_ledger": {
            "expected_source_kg": inputs["source"]["expected_mass_kg"],
            "observed_alphaPhi_source_kg": source_volume * 1000,
            "source_dose_delta_kg": source_volume * 1000 - inputs["source"]["expected_mass_kg"],
            "domain_inventory_kg": observed_volume * 1000 if observed_volume is not None else None,
            "open_boundary_outflow_kg": outward_volume * 1000,
            "open_boundary_inflow_kg": inward_open_volume * 1000,
            "source_minus_boundary_and_inventory_residual_kg": residual * 1000,
            "ledger_relative_to_source": residual / source_volume if source_volume else None,
            "interpretation": "sampled alphaPhi_ ledger diagnostic; no frozen acceptance tolerance; not a conservation gate",
        },
        "plume": {
            "scope": "shape and penetration pending alpha.water post-processing; not a validated breakup prediction"
        },
        "scope": "Exploratory CPU mesh-cost comparison only; no E0-E6 gate or scientific validation pass.",
    }


def main() -> int:
    image_id = subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    summary_dir = ROOT / "results/runs" / f"restas-amr-comparison-{stamp}-{uuid.uuid4().hex[:8]}"
    summary_dir.mkdir(parents=True, exist_ok=False)
    reports = []
    prior_coarse = [
        path
        for path in (ROOT / "results/runs").glob("restas-amr-coarse_uniform-*")
        if (path / "probe-report.json").is_file()
    ]
    prior_coarse.sort(key=lambda path: path.stat().st_mtime)
    if prior_coarse:
        coarse_report = json.loads((prior_coarse[-1] / "probe-report.json").read_text())
        if coarse_report.get("solver_exit_code") == 0:
            reports.append(coarse_report)
    if not reports:
        variants = ("coarse_uniform", "static_localized", "dynamic_amr")
    else:
        variants = ("static_localized", "dynamic_amr")
    for variant in variants:
        run_dir = ROOT / "results/runs" / f"restas-amr-{variant}-{stamp}-{uuid.uuid4().hex[:6]}"
        run_dir.mkdir(parents=True, exist_ok=False)
        report = run_one(run_dir, variant, image_id)
        reports.append(report)
        if report["solver_exit_code"] != 0:
            print(
                f"Stopping comparison at {variant}; preserving this failure for handoff.",
                file=sys.stderr,
            )
            break
    (summary_dir / "comparison.json").write_text(
        json.dumps({"runs": reports, "scope": "exploratory only"}, indent=2, sort_keys=True) + "\n"
    )
    print(f"comparison summary: {summary_dir.relative_to(ROOT)}", flush=True)
    return (
        0 if len(reports) == 3 and all(report["solver_exit_code"] == 0 for report in reports) else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
