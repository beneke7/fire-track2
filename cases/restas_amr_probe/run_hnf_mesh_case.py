#!/usr/bin/env python3
"""Run an isolated horizontal RANS AMR/static/uniform mesh comparison case."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cases/restas_horizontal_nearfield"))
import prepare_case  # noqa: E402

IMAGE = "opencfd/openfoam-default:2512"
REFERENCE_25_KE = ROOT / "results/runs/restas-hnf-realizableke-20260928T151453Z-0c472f"
RANKS = 20
DOCKER_CPUS = 20
MEMORY_GIB = 96
TIMEOUT_S = 1800
SLOT_Y_INTERVALS = ((-1.025, -0.025), (0.025, 1.025))
SLOT_Z_INTERVALS = ((0.825, 0.975), (1.025, 1.175))
SOURCE_Z_MIN_M = min(lower for lower, _ in SLOT_Z_INTERVALS)
STATIC_Y_ROI = (-1.025, 1.025)
STATIC_Z_ROI = (0.575, 1.425)
STATIC_X_END_M = 0.9
PULSE_DURATION_S = 0.08
DEFAULT_PULSE_HORIZON_S = 0.1
DEFAULT_PULSE_DOMAIN_X_END_M = 4.0
DEFAULT_PULSE_DOMAIN_Z_MIN_M = -0.525
DEFAULT_PULSE_SNAPSHOT_INTERVAL_S = 0.01


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: float) -> str:
    return f"{value:.10g}"


def block_mesh_dict(
    *,
    spacing_m: float,
    coarse_spacing_m: float | None = None,
    mode: str,
    x_end_m: float = 2.4,
    y_bounds: tuple[float, float] = (-1.275, 1.275),
    z_bounds: tuple[float, float] = (-0.025, 2.025),
    roi_x_end_m: float = STATIC_X_END_M,
    roi_y: tuple[float, float] = STATIC_Y_ROI,
    roi_z: tuple[float, float] = STATIC_Z_ROI,
) -> tuple[str, dict[str, Any]]:
    """Create conformal Cartesian blocks with piecewise constant cell widths."""
    if mode not in {"uniform", "static_localized"}:
        raise ValueError(f"unsupported structured mesh mode: {mode}")
    if coarse_spacing_m is None:
        coarse_spacing_m = spacing_m

    x_breaks = [0.0, x_end_m]
    y_breaks = [y_bounds[0], y_bounds[1]]
    z_breaks = [z_bounds[0], z_bounds[1]]
    if math_is_in(y_bounds[0], -1.275, 1e-9):
        y_breaks.extend((-1.025, -0.025, 0.025, 1.025))
    else:
        y_breaks.extend(
            v
            for v in (-1.275, -1.025, -0.025, 0.025, 1.025, 1.275)
            if y_bounds[0] < v < y_bounds[1]
        )
    if math_is_in(z_bounds[0], -0.025, 1e-9):
        z_breaks.extend((-0.025, 0.575, 0.825, 0.975, 1.025, 1.175, 1.425, 2.025))
    else:
        z_breaks.extend(
            v
            for v in (-0.025, 0.575, 0.825, 0.975, 1.025, 1.175, 1.425, 2.025)
            if z_bounds[0] < v < z_bounds[1]
        )
    if mode == "static_localized" and 0.0 < roi_x_end_m < x_end_m:
        x_breaks.insert(1, roi_x_end_m)
    x_breaks = sorted(set(x_breaks))
    y_breaks = sorted(set(v for v in y_breaks if y_bounds[0] <= v <= y_bounds[1]))
    z_breaks = sorted(set(v for v in z_breaks if z_bounds[0] <= v <= z_bounds[1]))

    def axis_counts(breaks: list[float], axis: str) -> tuple[list[int], list[float]]:
        counts: list[int] = []
        widths: list[float] = []
        for lower, upper in zip(breaks, breaks[1:], strict=False):
            step = coarse_spacing_m
            if mode == "static_localized":
                inside = (
                    (axis == "x" and upper <= roi_x_end_m + 1e-9)
                    or (axis == "y" and lower >= roi_y[0] - 1e-9 and upper <= roi_y[1] + 1e-9)
                    or (axis == "z" and lower >= roi_z[0] - 1e-9 and upper <= roi_z[1] + 1e-9)
                )
                if inside:
                    step = spacing_m
            elif mode == "uniform":
                step = spacing_m
            cells = round((upper - lower) / step)
            if cells < 1 or abs(cells * step - (upper - lower)) > 1e-8:
                raise ValueError(
                    f"{axis} interval [{lower:g}, {upper:g}] does not align to {step:g} m"
                )
            counts.append(cells)
            widths.append((upper - lower) / cells)
        return counts, widths

    nx, dxs = axis_counts(x_breaks, "x")
    ny, dys = axis_counts(y_breaks, "y")
    nz, dzs = axis_counts(z_breaks, "z")
    x_len, y_len = len(x_breaks), len(y_breaks)

    def vertex_index(i: int, j: int, k: int) -> int:
        return k * x_len * y_len + j * x_len + i

    vertices = [
        f"    ({canonical(x)} {canonical(y)} {canonical(z)})"
        for z in z_breaks
        for y in y_breaks
        for x in x_breaks
    ]
    blocks: list[str] = []
    faces: dict[str, list[str]] = {
        "slot_01": [],
        "slot_02": [],
        "slot_03": [],
        "slot_04": [],
        "plate": [],
        "xOutlet": [],
        "airInlet": [],
        "airOutlet": [],
        "zMin": [],
        "zMax": [],
    }

    def face(ids: tuple[int, int, int, int]) -> str:
        return "(" + " ".join(map(str, ids)) + ")"

    def in_interval(lower: float, upper: float, interval: tuple[float, float]) -> bool:
        return lower >= interval[0] - 1e-9 and upper <= interval[1] + 1e-9

    for ix, nxi in enumerate(nx):
        for iy, nyi in enumerate(ny):
            for iz, nzi in enumerate(nz):
                ids = (
                    vertex_index(ix, iy, iz),
                    vertex_index(ix + 1, iy, iz),
                    vertex_index(ix + 1, iy + 1, iz),
                    vertex_index(ix, iy + 1, iz),
                    vertex_index(ix, iy, iz + 1),
                    vertex_index(ix + 1, iy, iz + 1),
                    vertex_index(ix + 1, iy + 1, iz + 1),
                    vertex_index(ix, iy + 1, iz + 1),
                )
                blocks.append(
                    "    hex ("
                    + " ".join(map(str, ids))
                    + f") ({nxi} {nyi} {nzi}) simpleGrading (1 1 1)"
                )
                if ix == 0:
                    slot_y = [
                        i
                        for i, interval in enumerate(SLOT_Y_INTERVALS)
                        if in_interval(y_breaks[iy], y_breaks[iy + 1], interval)
                    ]
                    slot_z = [
                        i
                        for i, interval in enumerate(SLOT_Z_INTERVALS)
                        if in_interval(z_breaks[iz], z_breaks[iz + 1], interval)
                    ]
                    if slot_y and slot_z:
                        faces[f"slot_{slot_z[0] * 2 + slot_y[0] + 1:02d}"].append(
                            face((ids[0], ids[4], ids[7], ids[3]))
                        )
                    else:
                        faces["plate"].append(face((ids[0], ids[4], ids[7], ids[3])))
                if ix == len(nx) - 1:
                    faces["xOutlet"].append(face((ids[1], ids[2], ids[6], ids[5])))
                if iy == 0:
                    faces["airInlet"].append(face((ids[0], ids[1], ids[5], ids[4])))
                if iy == len(ny) - 1:
                    faces["airOutlet"].append(face((ids[3], ids[7], ids[6], ids[2])))
                if iz == 0:
                    faces["zMin"].append(face((ids[0], ids[3], ids[2], ids[1])))
                if iz == len(nz) - 1:
                    faces["zMax"].append(face((ids[4], ids[5], ids[6], ids[7])))

    boundary = []
    for name, patch_faces in faces.items():
        patch_type = (
            "wall" if name == "plate" else "symmetryPlane" if name in {"zMin", "zMax"} else "patch"
        )
        boundary.append(
            f"    {name}\n    {{\n        type {patch_type};\n        faces\n        (\n"
            + "\n".join(f"            {item}" for item in patch_faces)
            + "\n        );\n    }\n"
        )
    text = (
        prepare_case.foam_header("blockMeshDict")
        + "scale 1;\n\nvertices\n(\n"
        + "\n".join(vertices)
        + "\n);\n\nblocks\n(\n"
        + "\n".join(blocks)
        + "\n);\n\nedges ();\n\nboundary\n(\n"
        + "\n".join(boundary)
        + ");\n\nmergePatchPairs ();\n"
    )
    metadata = {
        "mesh_mode": mode,
        "mesh_spacing_or_max_spacing_m": spacing_m,
        "x_breaks_m": x_breaks,
        "y_breaks_m": y_breaks,
        "z_breaks_m": z_breaks,
        "x_cells_by_segment": nx,
        "y_cells_by_segment": ny,
        "z_cells_by_segment": nz,
        "x_widths_by_segment_m": dxs,
        "y_widths_by_segment_m": dys,
        "z_widths_by_segment_m": dzs,
        "mesh_shape": [sum(nx), sum(ny), sum(nz)],
        "cell_count": sum(nx) * sum(ny) * sum(nz),
        "static_refinement_box_m": {
            "x": [0.0, roi_x_end_m],
            "y": list(roi_y),
            "z": list(roi_z),
        }
        if mode == "static_localized"
        else None,
        "domain_bounds_m": {"x": [0.0, x_end_m], "y": list(y_bounds), "z": list(z_bounds)},
    }
    return text, metadata


def math_is_in(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance


def add_flux_diagnostics(control_path: Path, *, every_step: bool) -> None:
    text = control_path.read_text(encoding="utf-8")
    if "functions\n{" not in text:
        raise RuntimeError("generated controlDict has no functions block")
    names = ("slot_01", "slot_02", "slot_03", "slot_04", "xOutlet", "airInlet", "airOutlet")
    interval = "timeStep" if every_step else "writeTime"
    flux_fos = "".join(
        f"    {name}Flux\n    {{\n        type surfaceFieldValue;\n        libs (fieldFunctionObjects);\n"
        f"        regionType patch;\n        name {name};\n        operation sum;\n"
        "        fields (phi alphaPhi_);\n        writeFields false;\n"
        "        executeControl timeStep;\n        executeInterval 1;\n"
        f"        writeControl {interval};\n        writeInterval 1;\n    }}\n"
        for name in names
    )
    start = text.index("functions\n{") + len("functions\n{")
    control_path.write_text(text[:start] + "\n" + flux_fos + text[start:], encoding="utf-8")


def install_pulsed_inlet(case: Path, *, pulse_end_s: float, end_s: float) -> None:
    field_path = case / "0/U"
    text = field_path.read_text(encoding="utf-8")
    boundary = (
        "        type uniformFixedValue;\n"
        "        uniformValue table\n        (\n"
        "            (0 (20 0 0))\n"
        f"            ({canonical(pulse_end_s)} (20 0 0))\n"
        f"            ({canonical(pulse_end_s + 1e-6)} (0 0 0))\n"
        f"            ({canonical(end_s)} (0 0 0))\n"
        "        );\n        value uniform (20 0 0);"
    )
    for patch in ("slot_01", "slot_02", "slot_03", "slot_04"):
        pattern = re.compile(rf"(?ms)^    {patch}\s*\{{.*?^    \}}")
        replacement = f"    {patch}\n    {{\n{boundary}\n    }}"
        text, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"could not install the provisional pulse on {patch}")
    field_path.write_text(text, encoding="utf-8")


def install_pulsed_source_turbulence(
    case: Path,
    *,
    model: str,
    pulse_end_s: float,
    end_s: float,
    k_value: float,
    epsilon_value: float,
) -> None:
    """Decay source turbulence after shutoff using the selected RANS variables."""
    if model in {"standard-ke", "realizable-ke"}:
        pulsed_fields = (("k", k_value), ("epsilon", epsilon_value))
    elif model == "k-omega-sst":
        # Keep omega positive while k decays; setting both to 1e-12 would make
        # k/omega order one and create a large eddy viscosity at the inlet.
        pulsed_fields = (("k", k_value),)
    else:
        raise ValueError(f"unsupported RANS source-turbulence pulse model: {model}")

    for field_name, initial in pulsed_fields:
        field_path = case / "0" / field_name
        text = field_path.read_text(encoding="utf-8")
        boundary = (
            "        type uniformFixedValue;\n"
            "        uniformValue table\n        (\n"
            f"            (0 {canonical(initial)})\n"
            f"            ({canonical(pulse_end_s)} {canonical(initial)})\n"
            f"            ({canonical(pulse_end_s + 1e-6)} 1e-12)\n"
            f"            ({canonical(end_s)} 1e-12)\n"
            f"        );\n        value uniform {canonical(initial)};"
        )
        for patch in ("slot_01", "slot_02", "slot_03", "slot_04"):
            pattern = re.compile(rf"(?ms)^    {patch}\s*\{{.*?^    \}}")
            replacement = f"    {patch}\n    {{\n{boundary}\n    }}"
            text, count = pattern.subn(replacement, text, count=1)
            if count != 1:
                raise RuntimeError(f"could not pulse {field_name} at {patch}")
        field_path.write_text(text, encoding="utf-8")


def configure_pulse100ms_case(case: Path, inputs: dict[str, Any], args: argparse.Namespace) -> None:
    """Apply pulse-stage horizon, domain, snapshot and fixed source-pulse metadata."""
    x_end_m = args.domain_x_end_m
    z_min_m = args.domain_z_min_m
    end_time_s = args.pulse_horizon_s
    snapshot_interval_s = args.snapshot_interval_s
    inputs["domain_bounds_m"] = {
        "x": [0.0, x_end_m],
        "y": [-2.525, 2.525],
        "z": [z_min_m, 2.025],
    }
    inputs["time"]["end_s"] = end_time_s
    inputs["time"]["snapshot_interval_s"] = snapshot_interval_s
    inputs["source_duration_s"] = PULSE_DURATION_S
    inputs["source_pulse_duration_s"] = PULSE_DURATION_S
    inputs["source_profile"] = (
        "constant prescribed 20 m/s through 80 ms, then abrupt shutoff with a 1 microsecond transition"
    )
    inputs["analytic_source_mass_flow_kg_s"] = prepare_case.WATER_MASS_FLOW_KG_S
    inputs["analytic_source_mass_over_horizon_kg"] = (
        prepare_case.WATER_MASS_FLOW_KG_S * PULSE_DURATION_S
    )
    inputs["domain_extension_assumption"] = (
        f"x extends to {x_end_m:g} m, y to ±2.525 m, and lower z to {z_min_m:g} m "
        f"for a {end_time_s:g} s post-pulse/outflow diagnostic; these bounds are provisional."
    )

    install_pulsed_inlet(case, pulse_end_s=PULSE_DURATION_S, end_s=end_time_s)
    install_pulsed_source_turbulence(
        case,
        model=args.model,
        pulse_end_s=PULSE_DURATION_S,
        end_s=end_time_s,
        k_value=float(inputs["rans_boundary_values"]["source_k_m2_s2"]),
        epsilon_value=float(inputs["rans_boundary_values"]["source_epsilon_m2_s3"]),
    )
    control = case / "system/controlDict"
    control_text = control.read_text(encoding="utf-8")
    control_text, end_count = re.subn(
        r"(?m)^endTime\s+[^;]+;", f"endTime {canonical(end_time_s)};", control_text, count=1
    )
    control_text, write_count = re.subn(
        r"(?m)^writeInterval\s+[^;]+;",
        f"writeInterval {canonical(snapshot_interval_s)};",
        control_text,
        count=1,
    )
    if end_count != 1 or write_count != 1:
        raise RuntimeError("could not apply pulse-stage endTime and snapshot interval")
    control.write_text(control_text, encoding="utf-8")
    inputs.setdefault("source", {})
    inputs["source"].update(
        {
            "pulse_end_s": PULSE_DURATION_S,
            "source_mass_expected_kg": inputs["analytic_source_mass_over_horizon_kg"],
            "pulse_shape": (
                "uniformFixedValue table: 20 m/s until 0.080 s, then zero after a 1 microsecond transition interval"
            ),
            "turbulence_pulse_shape": (
                "Source k and epsilon are table-ramped to residual 1e-12 after shutoff."
                if args.model in {"standard-ke", "realizable-ke"}
                else "Source k is table-ramped to residual 1e-12 after shutoff; positive omega stays at its provisional inlet value to avoid an artificial k/omega eddy-viscosity spike."
            ),
        }
    )


def pulse100ms_mesh_dict(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    """Build the selected pulse-stage base mesh with the requested bounds."""
    x_end_m = args.domain_x_end_m
    y_bounds = (-2.525, 2.525)
    z_bounds = (args.domain_z_min_m, 2.025)
    if args.variant == "dynamic":
        return block_mesh_dict(
            spacing_m=0.05,
            coarse_spacing_m=0.05,
            mode="uniform",
            x_end_m=x_end_m,
            y_bounds=y_bounds,
            z_bounds=z_bounds,
        )
    mesh_mode = "static_localized" if args.variant == "static" else "uniform"
    return block_mesh_dict(
        spacing_m=args.finest_spacing,
        coarse_spacing_m=0.05 if mesh_mode == "static_localized" else args.finest_spacing,
        mode=mesh_mode,
        x_end_m=x_end_m,
        y_bounds=y_bounds,
        z_bounds=z_bounds,
        roi_x_end_m=args.static_x_end_m,
    )


def apply_sensitivity_overrides(
    case: Path, inputs: dict[str, Any], args: argparse.Namespace
) -> None:
    """Apply only declared sigma and RANS inlet turbulence sensitivity values."""
    if args.surface_tension_n_m is not None:
        transport = case / "constant/transportProperties"
        text = transport.read_text(encoding="utf-8")
        text, count = re.subn(
            r"(?m)^sigma\s+[^;]+;",
            f"sigma {args.surface_tension_n_m:.9g};",
            text,
            count=1,
        )
        if count != 1:
            raise RuntimeError("could not override surface tension in transportProperties")
        transport.write_text(text, encoding="utf-8")
        inputs["surface_tension_N_m"] = args.surface_tension_n_m

    turbulence_overridden = any(
        value is not None
        for value in (
            args.turbulence_intensity,
            args.source_length_scale_m,
            args.air_length_scale_m,
        )
    )
    if not turbulence_overridden:
        return
    if args.model not in {"standard-ke", "realizable-ke"}:
        raise RuntimeError("inlet turbulence sensitivities require a k-epsilon RANS case")

    intensity = 0.05 if args.turbulence_intensity is None else args.turbulence_intensity
    source_length = 0.15 if args.source_length_scale_m is None else args.source_length_scale_m
    air_length = 0.05 if args.air_length_scale_m is None else args.air_length_scale_m
    source_k, source_epsilon, source_omega = prepare_case._turbulence_values(
        intensity, prepare_case.WATER_SPEED_M_S, source_length
    )
    air_k, air_epsilon, air_omega = prepare_case._turbulence_values(
        intensity, prepare_case.AIR_SPEED_M_S, air_length
    )
    prepare_case._write_turbulence_field(
        case / "0/k", "k", "[0 2 -2 0 0 0 0]", air_k, source_k, air_k, "kqRWallFunction"
    )
    prepare_case._write_turbulence_field(
        case / "0/epsilon",
        "epsilon",
        "[0 2 -3 0 0 0 0]",
        air_epsilon,
        source_epsilon,
        air_epsilon,
        "epsilonWallFunction",
    )
    inputs["rans_boundary_values"].update(
        {
            "source_k_m2_s2": source_k,
            "source_epsilon_m2_s3": source_epsilon,
            "source_omega_s1": source_omega,
            "air_k_m2_s2": air_k,
            "air_epsilon_m2_s3": air_epsilon,
            "air_omega_s1": air_omega,
        }
    )
    inputs["turbulence_assumption"] = (
        f"RANS inlet intensity {100 * intensity:g}% at source (L={source_length:g} m) and air (L={air_length:g} m); "
        "values are provisional sensitivity inputs."
    )
    inputs["turbulence_sensitivity"] = {
        "intensity_fraction": intensity,
        "source_length_scale_m": source_length,
        "air_length_scale_m": air_length,
    }


def parse_solver_log(log: str) -> dict[str, Any]:
    solver = log.rsplit("Exec   : interIsoFoam -parallel", 1)[-1]
    solver = re.split(r"\nExec\s+: (?:reconstructParMesh|reconstructPar)\b", solver, maxsplit=1)[0]
    times = [float(value) for value in re.findall(r"^Time =\s*([0-9.eE+-]+)", solver, re.M)]
    clocks = [
        (float(cpu), float(wall))
        for cpu, wall in re.findall(
            r"^ExecutionTime =\s*([0-9.eE+-]+) s\s+ClockTime =\s*([0-9.eE+-]+) s",
            solver,
            re.M,
        )
    ]
    pressure = [
        int(value)
        for value in re.findall(r"GAMG:\s+Solving for p_rgh,.*?No Iterations (\d+)", solver)
    ]
    events: list[dict[str, Any]] = []
    active_time = None
    for line in solver.splitlines():
        current = re.match(r"^Time =\s*([0-9.eE+-]+)", line)
        if current:
            active_time = float(current.group(1))
        refined = re.search(r"Refined from (\d+) to (\d+) cells\.", line)
        unrefined = re.search(r"Unrefined from (\d+) to (\d+) cells\.", line)
        match = refined or unrefined
        if match:
            events.append(
                {
                    "time_s": active_time,
                    "operation": "refine" if refined else "unrefine",
                    "cells_before": int(match.group(1)),
                    "cells_after": int(match.group(2)),
                }
            )
    return {
        "last_time_s": max(times, default=None),
        "time_rows": len(times),
        "solver_steps": len(clocks),
        "solver_clock_time_s": clocks[-1][1] if clocks else None,
        "solver_cpu_time_s": clocks[-1][0] if clocks else None,
        "mean_clock_time_per_step_s": clocks[-1][1] / len(clocks) if clocks else None,
        "pressure_solve_count": len(pressure),
        "pressure_iteration_total": sum(pressure),
        "mean_pressure_iterations_per_solve": sum(pressure) / len(pressure) if pressure else None,
        "max_courant_number": max(
            (
                float(value)
                for value in re.findall(
                    r"^Courant Number mean:.*? max: ([0-9.eE+-]+)", solver, re.M
                )
            ),
            default=None,
        ),
        "max_interface_courant_number": max(
            (
                float(value)
                for value in re.findall(
                    r"^Interface Courant Number mean:.*? max: ([0-9.eE+-]+)", solver, re.M
                )
            ),
            default=None,
        ),
        "refinement_events": events,
    }


def expected_end_time_s(args: argparse.Namespace) -> float:
    if args.stage == "pulse100ms":
        return args.pulse_horizon_s
    return 0.08 if args.stage == "stage80ms" else 0.02


def run_case(args: argparse.Namespace) -> Path:
    is_pulse = args.stage == "pulse100ms"
    is_80ms = args.stage == "stage80ms"
    end_time_s = expected_end_time_s(args)
    start_spacing_m = 0.05 if args.variant in {"dynamic", "static"} else args.finest_spacing
    prep_horizon_s = PULSE_DURATION_S if is_pulse else end_time_s
    prep_spacing = start_spacing_m if start_spacing_m in {0.05, 0.025} else 0.025
    generated_run_id = f"restas-hnf-{args.model.replace('-', '')}-{args.stage}-{args.variant}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    run_id = args.run_id or generated_run_id
    run_dir = ROOT / "results/runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    case = run_dir / "case"
    inputs = prepare_case.prepare_case(case, args.model, args.ranks, prep_spacing, prep_horizon_s)
    inputs.update(
        {
            "study_stage": args.stage,
            "variant": args.variant,
            "case_classification": "Exploratory horizontal near-field mesh comparison; not validation.",
            "mesh_method": args.variant,
            "starting_mesh_spacing_m": start_spacing_m,
            "target_finest_spacing_m": args.finest_spacing,
            "max_dynamic_refinement_levels": args.max_levels if args.variant == "dynamic" else 0,
            "source_pulse_duration_s": PULSE_DURATION_S if is_pulse else end_time_s,
            "source_history_assumption": "Constant prescribed 20 m/s through 80 ms, then step to zero using uniformFixedValue/table; provisional and not measured.",
            "mpi_ranks": args.ranks,
            "comparison_reference_run_id": args.reference_run_dir.name
            if args.reference_run_dir
            else None,
            "wall_budget_s": args.timeout_s,
        }
    )
    apply_sensitivity_overrides(case, inputs, args)
    if is_80ms:
        inputs["source_history_assumption"] = (
            "Constant prescribed 20 m/s through the full 80 ms simulation horizon; subsequent shutoff is not modeled."
        )
        inputs["source_profile"] = "constant prescribed velocity through 80 ms; no shutoff segment"
    if is_pulse:
        configure_pulse100ms_case(case, inputs, args)
    else:
        inputs["domain_bounds_m"] = {"x": [0.0, 2.4], "y": [-1.275, 1.275], "z": [-0.025, 2.025]}
    if args.variant == "dynamic":
        mesh_mode = "dynamic"
        if is_pulse:
            mesh_text, mesh_metadata = pulse100ms_mesh_dict(args)
            (case / "system/blockMeshDict").write_text(mesh_text, encoding="utf-8")
            inputs.update(mesh_metadata)
            inputs["mesh_cells_expected"] = mesh_metadata["cell_count"]
            inputs["mesh_shape"] = {
                "nx": mesh_metadata["mesh_shape"][0],
                "ny": mesh_metadata["mesh_shape"][1],
                "nz": mesh_metadata["mesh_shape"][2],
            }
        inputs["base_mesh_cells_expected"] = inputs["mesh_cells_expected"]
        inputs["dynamic_refinement"] = {
            "field": "alpha.water",
            "lower_refine_level": 0.001,
            "upper_refine_level": 0.999,
            "unrefine_level": 0.001,
            "max_refinement_levels": args.max_levels,
            "refine_interval_steps": 1,
            "buffer_layers": 1,
            "max_cells": args.max_cells,
            "base_spacing_m": 0.05,
            "finest_spacing_m": 0.05 / (2**args.max_levels),
        }
        max_cells = args.max_cells
    else:
        if is_pulse:
            mesh_text, mesh_metadata = pulse100ms_mesh_dict(args)
        else:
            mesh_mode = "static_localized" if args.variant == "static" else "uniform"
            mesh_text, mesh_metadata = block_mesh_dict(
                spacing_m=args.finest_spacing,
                coarse_spacing_m=0.05 if mesh_mode == "static_localized" else args.finest_spacing,
                mode=mesh_mode,
                x_end_m=2.4,
                y_bounds=(-1.275, 1.275),
                z_bounds=(-0.025, 2.025),
                roi_x_end_m=args.static_x_end_m,
            )
        (case / "system/blockMeshDict").write_text(mesh_text, encoding="utf-8")
        inputs.update(mesh_metadata)
        inputs["mesh_cells_expected"] = mesh_metadata["cell_count"]
        inputs["mesh_spacing_m"] = args.finest_spacing if args.variant == "uniform" else 0.05
        inputs["finest_interface_cell_spacing_m"] = [args.finest_spacing] * 3
        inputs["mesh_shape"] = {
            "nx": mesh_metadata["mesh_shape"][0],
            "ny": mesh_metadata["mesh_shape"][1],
            "nz": mesh_metadata["mesh_shape"][2],
        }
        max_cells = None
    if args.variant == "dynamic":
        if is_pulse:
            dynamic_domain = (0.0, args.domain_x_end_m)
            static_refine_end = args.static_x_end_m
        else:
            dynamic_domain = (0.0, 2.4)
            static_refine_end = args.static_x_end_m
        (case / "constant/dynamicMeshDict").write_text(
            prepare_case.foam_header("dynamicMeshDict", location="constant")
            + "dynamicFvMesh dynamicRefineFvMesh;\n\nrefineInterval 1;\nfield alpha.water;\n"
            + "lowerRefineLevel 0.001;\nupperRefineLevel 0.999;\nunrefineLevel 0.001;\n"
            + f"nBufferLayers 1;\nmaxRefinement {args.max_levels};\nmaxCells {args.max_cells};\n"
            + "correctFluxes ((phi none) (nHatf none) (rhoPhi none) (alphaPhi_ none) (ghf none) (phi0 none) (dVf_ none));\ndumpLevel true;\n",
            encoding="utf-8",
        )
        inputs["dynamic_refinement"]["max_cells"] = max_cells
        inputs["dynamic_refinement"]["downstream_domain_m"] = dynamic_domain[1]
        inputs["dynamic_refinement"]["static_comparison_refine_end_x_m"] = static_refine_end
    else:
        (case / "constant/dynamicMeshDict").write_text(
            prepare_case.foam_header("dynamicMeshDict", location="constant")
            + "dynamicFvMesh staticFvMesh;\n",
            encoding="utf-8",
        )
    add_flux_diagnostics(case / "system/controlDict", every_step=True)
    inputs_path = run_dir / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    reference = args.reference_run_dir.resolve() if args.reference_run_dir else None
    reference_manifest: dict[str, Any] = {}
    common_files = (
        "0/U",
        "0/alpha.water",
        "0/p_rgh",
        "0/k",
        "0/epsilon",
        "0/omega",
        "0/nut",
        "constant/g",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        "system/fvSchemes",
        "system/fvSolution",
    )
    hashes: dict[str, Any] = {}
    if reference and (reference / "case").is_dir():
        reference_manifest = json.loads((reference / "manifest.json").read_text(encoding="utf-8"))
        for relative in common_files:
            if not (reference / "case" / relative).is_file() or not (case / relative).is_file():
                continue
            hashes[relative] = {
                "reference_sha256": sha256(reference / "case" / relative),
                "candidate_sha256": sha256(case / relative),
                "bytewise_match": sha256(reference / "case" / relative) == sha256(case / relative),
            }
        if not is_pulse:
            allowed_mismatches = set()
            if args.model != reference_manifest.get("model"):
                # This is an intentional closure comparison against the existing
                # realizable-kE reference; all shared source/physics inputs must
                # still match bytewise apart from the selected RAS model.
                allowed_mismatches.update({"constant/turbulenceProperties", "0/epsilon"})
            if args.model == "k-omega-sst":
                # OpenFOAM 2512 requires the SST wall-distance method; the
                # RKE reference does not contain this closure-specific scheme.
                allowed_mismatches.add("system/fvSchemes")
            if args.surface_tension_n_m is not None:
                allowed_mismatches.add("constant/transportProperties")
            if any(
                value is not None
                for value in (
                    args.turbulence_intensity,
                    args.source_length_scale_m,
                    args.air_length_scale_m,
                )
            ):
                allowed_mismatches.update({"0/k", "0/epsilon"})
            unexpected = [
                relative
                for relative, record in hashes.items()
                if not record["bytewise_match"] and relative not in allowed_mismatches
            ]
            if unexpected:
                raise RuntimeError(
                    "candidate source/physics fields differ from the selected reference: "
                    + ", ".join(unexpected)
                )

    image_id = subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    source_files = (
        Path(__file__).resolve(),
        ROOT / "cases/restas_horizontal_nearfield/prepare_case.py",
        ROOT / "cases/restas_amr_probe/analyze_hnf_mesh_comparison.py",
        ROOT / "cases/restas_amr_probe/run_warden_followup_queue.sh",
        ROOT / "scripts/run_local.py",
        reference / "manifest.json" if reference else Path("/nonexistent"),
    )
    source_archive = run_dir / "source_snapshot"
    for source_path in source_files:
        if source_path.is_file() and source_path.is_relative_to(ROOT):
            archived_path = source_archive / source_path.relative_to(ROOT)
            archived_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, archived_path)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_utc": datetime.now(UTC).isoformat(),
        "git_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "git_worktree_dirty": bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        ),
        "case_classification": "Exploratory horizontal four-slot CPU mesh comparison; not validation.",
        "solver_image": IMAGE,
        "solver_image_id": image_id,
        "model": args.model,
        "variant": args.variant,
        "stage": args.stage,
        "reference_run_id": reference.name if reference else None,
        "reference_manifest_sha256": sha256(reference / "manifest.json") if reference else None,
        "reference_inputs_sha256": reference_manifest.get("inputs_sha256"),
        "common_physics_field_hashes": hashes,
        "inputs_sha256": sha256(inputs_path),
        "source_sha256": {
            str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path): sha256(path)
            for path in source_files
            if path and path.is_file()
        },
        "source_archive_relative_path": "source_snapshot",
        "prepared_case_file_sha256": {
            str(path.relative_to(case)): sha256(path)
            for path in sorted(case.rglob("*"))
            if path.is_file()
        },
        "execution": {
            "mpi_ranks": args.ranks,
            "docker_cpu_limit": args.docker_cpus,
            "docker_memory_limit_gib": args.memory_gib,
            "wall_timeout_s": args.timeout_s,
            "commands": [
                "blockMesh",
                "checkMesh -allTopology -allGeometry",
                "decomposePar -force",
                f"mpirun -np {args.ranks} interIsoFoam -parallel",
                "reconstructParMesh -constant",
                "reconstructPar -fields '(alpha.water [cellLevel for dynamic])'",
            ],
        },
        "scope": "Exploratory horizontal near-field pulse and post-pulse AMR/static/uniform method diagnostic; not E1-E6 validation or a device reproduction.",
        "inputs": inputs,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    container_name = run_id[:63]
    docker_args = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        f"--cpus={args.docker_cpus}",
        f"--memory={args.memory_gib}g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={case.resolve()},dst=/case",
        "--workdir",
        "/case",
        "--entrypoint",
        "/bin/bash",
        IMAGE,
        "-lc",
    ]
    fields = "(alpha.water cellLevel)" if args.variant == "dynamic" else "(alpha.water)"
    shell = f"""source /usr/lib/openfoam/openfoam2512/etc/bashrc
set -euo pipefail
run_stage() {{ local stage="$1"; shift; set +e; "$@"; local status=$?; set -e; printf 'HNFM_STAGE_EXIT stage=%s code=%s\\n' "$stage" "$status"; return "$status"; }}
run_stage blockMesh blockMesh
run_stage checkMesh checkMesh -allTopology -allGeometry
run_stage decomposePar decomposePar -force
run_stage interIsoFoam mpirun -np {args.ranks} interIsoFoam -parallel
run_stage reconstructParMesh reconstructParMesh -constant
run_stage reconstructPar reconstructPar -fields '{fields}'
"""
    samples: list[dict[str, Any]] = []
    started = time.monotonic()
    log_path = run_dir / "openfoam-console.log"
    with log_path.open("wb") as log_stream:
        proc = subprocess.Popen([*docker_args, shell], stdout=log_stream, stderr=subprocess.STDOUT)
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
                timeout=10,
                check=False,
            )
            if stat.returncode == 0 and stat.stdout.strip():
                cpu, memory = stat.stdout.strip().split("|", 1)
                sample.update({"cpu_percent": cpu, "memory_usage_and_limit": memory})
            samples.append(sample)
            if time.monotonic() - started > args.timeout_s:
                subprocess.run(
                    ["docker", "stop", container_name], capture_output=True, timeout=30, check=False
                )
                break
            time.sleep(2)
        exit_code = proc.wait()
    wall = time.monotonic() - started
    log = log_path.read_text(encoding="utf-8", errors="replace")
    cpu = [float(sample.get("cpu_percent", "0%").rstrip("%")) for sample in samples]
    ram_gib = []
    for sample in samples:
        match = re.match(r"([0-9.]+)\s*(B|KiB|MiB|GiB)", sample.get("memory_usage_and_limit", ""))
        if match:
            scale = {"B": 2**-30, "KiB": 2**-20, "MiB": 2**-10, "GiB": 1.0}[match.group(2)]
            ram_gib.append(float(match.group(1)) * scale)
    manifest.update(
        {
            "finished_utc": datetime.now(UTC).isoformat(),
            "exit_code": exit_code,
            "wall_time_s": wall,
            "stage_exit_records": [
                {"stage": stage, "exit_code": int(code)}
                for stage, code in re.findall(
                    r"^HNFM_STAGE_EXIT stage=([A-Za-z0-9_]+) code=(\d+)$", log, re.M
                )
            ],
            "solver_log_summary": parse_solver_log(log),
            "docker_resource_samples": samples,
            "peak_sampled_cpu_percent": max(cpu, default=None),
            "peak_sampled_memory_gib": max(ram_gib, default=None),
            "resource_sample_note": "Docker stats sampled approximately every two seconds; sub-interval peaks may be higher.",
            "output_tree_bytes": sum(
                path.stat().st_size for path in run_dir.rglob("*") if path.is_file()
            ),
            "run_sha256": {
                str(path.relative_to(run_dir)): sha256(path)
                for path in sorted(run_dir.rglob("*"))
                if path.is_file() and path.name != "manifest.json"
            },
        }
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "variant": args.variant,
                "stage": args.stage,
                "exit_code": exit_code,
                "wall_time_s": wall,
                "solver": manifest["solver_log_summary"],
                "peak_ram_gib": max(ram_gib, default=None),
                "run_dir": str(run_dir.relative_to(ROOT)),
            },
            indent=2,
        ),
        flush=True,
    )
    return run_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("stage1_25mm", "stage2_12p5mm", "stage80ms", "pulse100ms"),
        required=True,
    )
    parser.add_argument("--variant", choices=("dynamic", "static", "uniform"), required=True)
    parser.add_argument(
        "--model",
        choices=("realizable-ke", "standard-ke", "k-omega-sst"),
        default="realizable-ke",
    )
    parser.add_argument("--reference-run-dir", type=Path, default=REFERENCE_25_KE)
    parser.add_argument("--finest-spacing", type=float, choices=(0.025, 0.0125), default=0.025)
    parser.add_argument("--max-levels", type=int, choices=(1, 2), default=1)
    parser.add_argument("--max-cells", type=int, default=2_000_000)
    parser.add_argument("--static-x-end-m", type=float, default=0.9)
    parser.add_argument("--pulse-horizon-s", type=float, default=DEFAULT_PULSE_HORIZON_S)
    parser.add_argument("--domain-x-end-m", type=float, default=DEFAULT_PULSE_DOMAIN_X_END_M)
    parser.add_argument("--domain-z-min-m", type=float, default=DEFAULT_PULSE_DOMAIN_Z_MIN_M)
    parser.add_argument(
        "--snapshot-interval-s", type=float, default=DEFAULT_PULSE_SNAPSHOT_INTERVAL_S
    )
    parser.add_argument("--ranks", type=int, default=RANKS)
    parser.add_argument("--docker-cpus", type=int, default=DOCKER_CPUS)
    parser.add_argument("--memory-gib", type=int, default=MEMORY_GIB)
    parser.add_argument("--timeout-s", type=int, default=TIMEOUT_S)
    parser.add_argument("--surface-tension-n-m", type=float)
    parser.add_argument("--turbulence-intensity", type=float)
    parser.add_argument("--source-length-scale-m", type=float)
    parser.add_argument("--air-length-scale-m", type=float)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    new_values = (
        ("pulse horizon", args.pulse_horizon_s),
        ("downstream domain end", args.domain_x_end_m),
        ("lower domain z bound", args.domain_z_min_m),
        ("snapshot interval", args.snapshot_interval_s),
    )
    for name, value in new_values:
        if not math.isfinite(value):
            parser.error(f"{name} must be finite")
    if args.pulse_horizon_s < DEFAULT_PULSE_HORIZON_S:
        parser.error("pulse horizon must be at least 0.1 s")
    if args.domain_x_end_m < DEFAULT_PULSE_DOMAIN_X_END_M:
        parser.error("downstream domain end must be at least 4 m")
    if args.domain_z_min_m > DEFAULT_PULSE_DOMAIN_Z_MIN_M or args.domain_z_min_m > SOURCE_Z_MIN_M:
        parser.error("lower domain z bound must be at or below -0.525 m and the source")
    if args.snapshot_interval_s <= 0 or args.snapshot_interval_s > args.pulse_horizon_s:
        parser.error("snapshot interval must be positive and no greater than the pulse horizon")
    pulse_overrides = (
        args.pulse_horizon_s != DEFAULT_PULSE_HORIZON_S
        or args.domain_x_end_m != DEFAULT_PULSE_DOMAIN_X_END_M
        or args.domain_z_min_m != DEFAULT_PULSE_DOMAIN_Z_MIN_M
        or args.snapshot_interval_s != DEFAULT_PULSE_SNAPSHOT_INTERVAL_S
    )
    if args.stage != "pulse100ms" and pulse_overrides:
        parser.error("pulse horizon, domain, and snapshot overrides apply only to pulse100ms")
    if args.stage == "pulse100ms":
        mesh_spacing_m = 0.05 if args.variant in {"dynamic", "static"} else args.finest_spacing
        for name, length in (
            ("downstream domain end", args.domain_x_end_m),
            ("lower domain z segment", -0.025 - args.domain_z_min_m),
        ):
            cells = round(length / mesh_spacing_m)
            if cells < 1 or not math.isclose(cells * mesh_spacing_m, length, abs_tol=1e-8):
                parser.error(
                    f"{name} must align to the selected mesh spacing ({mesh_spacing_m:g} m)"
                )
    if args.ranks < 1 or args.ranks > 20 or args.docker_cpus < args.ranks or args.docker_cpus > 20:
        parser.error("ranks must be 1..20 and the CPU cap must cover ranks without exceeding 20")
    if args.memory_gib < 4 or args.memory_gib > 112:
        parser.error("memory limit must be 4..112 GiB on this 125 GiB host")
    if args.surface_tension_n_m is not None and args.surface_tension_n_m < 0:
        parser.error("surface tension cannot be negative")
    if args.run_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{8,120}", args.run_id):
        parser.error("run ID must be 8–120 letters, digits, underscores, or hyphens")
    if args.turbulence_intensity is not None and not 0 < args.turbulence_intensity <= 0.5:
        parser.error("turbulence intensity must be in (0, 0.5]")
    for name, value in (
        ("source length scale", args.source_length_scale_m),
        ("air length scale", args.air_length_scale_m),
    ):
        if value is not None and value <= 0:
            parser.error(f"{name} must be positive")
    if args.variant == "dynamic":
        expected = 0.05 / (2**args.max_levels)
        if abs(expected - args.finest_spacing) > 1e-9:
            parser.error(
                "dynamic max-levels must produce the requested finest spacing from a 50 mm base"
            )
    return args


def main() -> int:
    args = parse_args()
    run_dir = run_case(args)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    failed = [stage for stage in manifest["stage_exit_records"] if stage["exit_code"]]
    end_time = expected_end_time_s(args)
    if (
        manifest["exit_code"]
        or failed
        or not manifest["solver_log_summary"]["last_time_s"]
        or manifest["solver_log_summary"]["last_time_s"] < end_time
    ):
        return int(manifest["exit_code"] or failed[0]["exit_code"] or 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
