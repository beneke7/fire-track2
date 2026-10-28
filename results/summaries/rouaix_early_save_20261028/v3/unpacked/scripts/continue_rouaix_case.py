#!/usr/bin/env python3
"""Continue a completed Rouaix Case 4 checkpoint without replaying time zero.

This driver copies only the verified 0.4 s checkpoint, its immutable mesh and
solver inputs. It is an exploratory continuation of the existing structured
Mesh 4 precursor, not a new mesh or an E1 validation run.
"""

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

try:
    from audit_interface_wave_flux import read_volume_scalar_field, read_volume_vector_internal
except ModuleNotFoundError:
    from scripts.audit_interface_wave_flux import (
        read_volume_scalar_field,
        read_volume_vector_internal,
    )

ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = ROOT / "results/runs"
PARENT_RUN_ID = "rouaix-c4-0p4-20261006T072500Z-retry01"
PARENT_RUN = RUNS_ROOT / PARENT_RUN_ID
IMAGE = "opencfd/openfoam-default:2512"
PINNED_IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
OPENFOAM_BASHRC = "/usr/lib/openfoam/openfoam2512/etc/bashrc"
START_TIME_S = 0.4
DELTA_T_S = 0.001
RHO_WATER_KG_M3 = 997.6
FLUX_PATCHES = (
    "gasInlet",
    "downstreamOutlet",
    "bottomOutlet",
    "spanwiseMinus",
    "spanwisePlus",
)
ALL_FLUX_PATCHES = (*FLUX_PATCHES, "aircraftWall", "nozzle")
CHECKPOINT_FIELDS = ("alpha.water", "U", "p_rgh", "k", "epsilon", "nut", "C", "Cx", "Cy", "Cz", "V")
SYSTEM_INPUTS = ("controlDict", "fvSchemes", "fvSolution")
CONSTANT_INPUTS = ("g", "hRef", "transportProperties", "turbulenceProperties")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,70}$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{12,64}$")
FLOAT_RE = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


class ContinuationError(RuntimeError):
    """Raised when a continuation input or solver stage is not trustworthy."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_tree(path: Path) -> dict[str, str]:
    return {
        child.relative_to(path).as_posix(): _sha256(child)
        for child in sorted(path.rglob("*"))
        if child.is_file()
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _git_state() -> dict[str, Any]:
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
    return {
        "revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "status_porcelain_at_prepare": status.stdout.splitlines() if status.returncode == 0 else [],
    }


def _parse_time_file(path: Path) -> float:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"\bvalue\s+([^;\s]+)\s*;", text)
    if match is None:
        raise ContinuationError(f"checkpoint time file has no value: {path}")
    return float(match.group(1))


def _read_parent() -> tuple[dict[str, Any], Path]:
    manifest_path = PARENT_RUN / "manifest.json"
    if not manifest_path.is_file():
        raise ContinuationError(f"parent manifest is missing: {manifest_path}")
    parent = json.loads(manifest_path.read_text(encoding="utf-8"))
    if parent.get("status") != "completed_short_pilot":
        raise ContinuationError(f"parent is not completed: {parent.get('status')!r}")
    flow = parent.get("stages", {}).get("flow", {})
    worker_exit = PARENT_RUN / "worker.exit"
    if (
        flow.get("exit_code") != 0
        or not worker_exit.is_file()
        or worker_exit.read_text().strip() != "0"
    ):
        raise ContinuationError("parent flow exit is not independently recorded as zero")
    if not math.isclose(float(parent["flow_final_time_s"]), START_TIME_S, abs_tol=1e-10):
        raise ContinuationError("parent final time differs from the requested 0.4 s checkpoint")
    image_id = parent.get("solver", {}).get("resolved_image_id")
    if image_id != PINNED_IMAGE_ID:
        raise ContinuationError(f"parent solver image differs from pinned v2512 image: {image_id}")
    diagnostics = parent.get("diagnostics", {})
    if not diagnostics.get("open_boundary_liquid_flux_history_available"):
        raise ContinuationError("parent has no measured open-boundary alphaPhi history")
    if diagnostics.get("final_phase_ledger_residual_fraction") is None:
        raise ContinuationError("parent phase-volume ledger has no residual")
    case = PARENT_RUN / "case"
    checkpoint = case / "0.4"
    required = [checkpoint / field for field in CHECKPOINT_FIELDS]
    required.extend(checkpoint / "uniform" / name for name in ("time", "cumulativeContErr"))
    missing = [path.relative_to(PARENT_RUN).as_posix() for path in required if not path.is_file()]
    if missing:
        raise ContinuationError(f"incomplete 0.4 checkpoint fields: {missing}")
    if not (case / "constant/polyMesh/boundary").is_file():
        raise ContinuationError("source polyMesh is missing")
    if not math.isclose(_parse_time_file(checkpoint / "uniform/time"), START_TIME_S, abs_tol=1e-10):
        raise ContinuationError("checkpoint uniform/time does not identify t=0.4 s")
    return parent, case


def _replace_dictionary_entry(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^(\s*{re.escape(key)}\s+)[^;]+;")
    changed, count = pattern.subn(rf"\g<1>{value};", text, count=1)
    if count != 1:
        raise ContinuationError(f"expected exactly one `{key}` entry in controlDict")
    return changed


def _control_dict(
    source: str,
    end_time_s: float,
    write_interval_s: float,
    *,
    delta_t_s: float = DELTA_T_S,
    extra_flux_patches: tuple[str, ...] = (),
) -> str:
    output = _replace_dictionary_entry(source, "startFrom", "latestTime")
    output = _replace_dictionary_entry(output, "endTime", f"{end_time_s:.12g}")
    output = _replace_dictionary_entry(output, "writeInterval", f"{write_interval_s:.12g}")
    output = _replace_dictionary_entry(output, "deltaT", f"{delta_t_s:.12g}")
    output = _replace_dictionary_entry(output, "maxDeltaT", f"{delta_t_s:.12g}")
    if extra_flux_patches:
        function_start = re.search(r"(?m)^\s*functions\s*\{", output)
        if function_start is None:
            raise ContinuationError("source controlDict has no functions dictionary")
        opening = output.find("{", function_start.start())
        depth = 0
        closing = None
        for index in range(opening, len(output)):
            if output[index] == "{":
                depth += 1
            elif output[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        if closing is None:
            raise ContinuationError("unterminated functions dictionary")
        additions = "\n".join(
            f"""    liquidFlux_{patch}
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name {patch};
        operation sum;
        fields (alphaPhi_);
        writeFields false;
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}"""
            for patch in extra_flux_patches
        )
        output = output[:closing] + additions + "\n" + output[closing:]
    return output


def _decompose_dict(cpus: int) -> str:
    decompositions = {4: (2, 2, 1), 16: (4, 2, 2), 20: (5, 2, 2)}
    if cpus not in decompositions:
        raise ContinuationError("MPI rank count must be 4, 16 or 20 for this mesh")
    nx, ny, nz = decompositions[cpus]
    return f"""FoamFile
{{
    version 2.0;
    format ascii;
    class dictionary;
    object decomposeParDict;
}}

numberOfSubdomains {cpus};
method hierarchical;
hierarchicalCoeffs
{{
    n ({nx} {ny} {nz});
    delta 0.001;
    order xyz;
}}
distributed no;
roots ();
"""


def _parse_flux_history(case: Path) -> tuple[np.ndarray, np.ndarray]:
    summed: dict[float, float] = {}
    seen: set[str] = set()
    for data_path in case.glob("postProcessing/liquidFlux_*/**/*.dat"):
        object_name = data_path.parent.parent.name.removeprefix("liquidFlux_")
        seen.add(object_name)
        for line in data_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            values = np.fromstring(stripped, sep=" ", dtype=np.float64)
            if values.size >= 2 and np.isfinite(values[:2]).all():
                instant, flux = map(float, values[:2])
                summed[instant] = summed.get(instant, 0.0) + flux
    if not set(FLUX_PATCHES).issubset(seen):
        raise ContinuationError(f"continuation lacks one or more alphaPhi patch histories: {seen}")
    ordered = sorted(summed.items())
    if len(ordered) < 2:
        raise ContinuationError("continuation has too few boundary-flux samples")
    return (
        np.asarray([row[0] for row in ordered], dtype=np.float64),
        np.asarray([row[1] for row in ordered], dtype=np.float64),
    )


def _parent_flux_history(case: Path) -> tuple[np.ndarray, np.ndarray]:
    values: dict[float, float] = {}
    seen: set[str] = set()
    for data_path in case.glob("postProcessing/liquidFlux_*/**/*.dat"):
        object_name = data_path.parent.parent.name.removeprefix("liquidFlux_")
        seen.add(object_name)
        for line in data_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            row = np.fromstring(stripped, sep=" ", dtype=np.float64)
            if row.size >= 2 and np.isfinite(row[:2]).all():
                instant, flux = map(float, row[:2])
                values[instant] = values.get(instant, 0.0) + flux
    if not set(FLUX_PATCHES).issubset(seen) or not values:
        raise ContinuationError("parent flux history is incomplete")
    ordered = sorted(values.items())
    if ordered[0][0] > 0:
        ordered.insert(0, (0.0, 0.0))
    return (
        np.asarray([row[0] for row in ordered], dtype=np.float64),
        np.asarray([row[1] for row in ordered], dtype=np.float64),
    )


def _trapezoid(values: np.ndarray, times: np.ndarray) -> float:
    if values.size != times.size or values.size < 2 or np.any(np.diff(times) <= 0):
        raise ContinuationError("invalid or non-monotonic flux samples for integration")
    return float(np.sum(0.5 * (values[1:] + values[:-1]) * np.diff(times)))


def _right_endpoint_step_integral(
    start_time_s: float, times: np.ndarray, fluxes: np.ndarray, delta_t_s: float
) -> float:
    """Integrate OpenFOAM alphaPhi_ step fluxes over the preceding fixed steps."""
    if times.size != fluxes.size or times.size == 0:
        raise ContinuationError("invalid continuation flux arrays")
    intervals = np.diff(np.concatenate(([start_time_s], times)))
    if np.any(intervals <= 0) or not np.allclose(intervals, delta_t_s, rtol=0, atol=1e-9):
        raise ContinuationError(
            "new alphaPhi_ samples do not align with the fixed solver time step"
        )
    return float(np.dot(fluxes, intervals))


def _parse_inventory_history(case: Path) -> tuple[np.ndarray, np.ndarray]:
    histories: dict[float, float] = {}
    for data_path in case.glob("postProcessing/waterInventory/**/*.dat"):
        for line in data_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            row = np.fromstring(stripped, sep=" ", dtype=np.float64)
            if row.size >= 2 and np.isfinite(row[:2]).all():
                instant, inventory = map(float, row[:2])
                histories[instant] = inventory
    ordered = sorted(histories.items())
    if not ordered:
        raise ContinuationError("continuation has no native waterInventory time history")
    return (
        np.asarray([row[0] for row in ordered], dtype=np.float64),
        np.asarray([row[1] for row in ordered], dtype=np.float64),
    )


def _parse_patch_flux_histories(
    case: Path, patches: tuple[str, ...]
) -> dict[str, dict[float, float]]:
    histories: dict[str, dict[float, float]] = {}
    for patch in patches:
        data_paths = list((case / "postProcessing" / f"liquidFlux_{patch}").glob("**/*.dat"))
        if not data_paths:
            raise ContinuationError(f"missing alphaPhi_ history for boundary patch {patch}")
        values: dict[float, float] = {}
        for data_path in data_paths:
            for line in data_path.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                row = np.fromstring(stripped, sep=" ", dtype=np.float64)
                if row.size >= 2 and np.isfinite(row[:2]).all():
                    instant, flux = map(float, row[:2])
                    values[instant] = flux
        histories[patch] = values
    return histories


def _parse_event_stability_log(
    path: Path, start_time_s: float, end_time_s: float
) -> list[dict[str, float | str | None]]:
    """Extract per-step Courant and alpha-bounding records around an event."""
    records: dict[float, dict[str, float | str | None]] = {}
    pending: dict[str, float | None] = {
        "courant_mean": None,
        "courant_max": None,
        "interface_courant_mean": None,
        "interface_courant_max": None,
    }
    current: dict[str, float | str | None] | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        courant = re.search(rf"^\s*Courant Number mean:\s*({FLOAT_RE})\s+max:\s*({FLOAT_RE})", line)
        if courant is not None:
            pending["courant_mean"] = float(courant.group(1))
            pending["courant_max"] = float(courant.group(2))
        interface_courant = re.search(
            rf"Interface Courant Number mean:\s*({FLOAT_RE})\s+max:\s*({FLOAT_RE})",
            line,
        )
        if interface_courant is not None:
            pending["interface_courant_mean"] = float(interface_courant.group(1))
            pending["interface_courant_max"] = float(interface_courant.group(2))
        instant = re.match(rf"\s*Time\s*=\s*({FLOAT_RE})\s*$", line)
        if instant is not None:
            time_s = float(instant.group(1))
            current = None
            has_courant_sample = any(value is not None for value in pending.values())
            if start_time_s < time_s <= end_time_s and has_courant_sample:
                current = {"time_s": time_s, **pending}
                records[time_s] = current
            pending = {
                "courant_mean": None,
                "courant_max": None,
                "interface_courant_mean": None,
                "interface_courant_max": None,
            }
            continue
        if current is None:
            continue
        bounding = re.search(
            rf"After conservative bounding:\s*min\(alpha\)\s*=\s*({FLOAT_RE}),\s*max\(alpha\)\s*=\s*(.+)$",
            line,
        )
        if bounding is not None:
            current["conservative_bounding_min_alpha"] = float(bounding.group(1))
            # Keep the original expression: OpenFOAM may print `1 + tiny`.
            current["conservative_bounding_max_alpha_expression"] = bounding.group(2).strip()
        phase_volume = re.search(rf"Phase-1 volume fraction\s*=\s*({FLOAT_RE})", line)
        if phase_volume is not None:
            current["phase1_volume_fraction"] = float(phase_volume.group(1))
    return [records[time_s] for time_s in sorted(records)]


def _analyze_boundary_diagnostic(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    continuation = manifest["continuation"]
    start_time = float(continuation["from_time_s"])
    end_time = float(continuation["end_time_s"])
    delta_t = float(continuation["delta_t_s"])
    expected_cells = int(manifest["mesh"]["cell_count"])
    case = run_dir / "case"
    histories = _parse_patch_flux_histories(case, ALL_FLUX_PATCHES)
    common_times = set.intersection(*(set(values) for values in histories.values()))
    times = np.asarray(sorted(t for t in common_times if t > start_time + 1e-10), dtype=np.float64)
    expected_steps = round((end_time - start_time) / delta_t)
    intervals = np.diff(np.concatenate(([start_time], times)))
    if times.size != expected_steps or not np.allclose(intervals, delta_t, rtol=0, atol=1e-9):
        raise ContinuationError(
            f"boundary flux history has {times.size} steps; expected {expected_steps} at dt={delta_t:g} s"
        )
    inventory_times, inventory_values = _parse_inventory_history(case)
    inventory_map = dict(zip(inventory_times.tolist(), inventory_values.tolist(), strict=True))
    if not all(float(t) in inventory_map for t in times):
        raise ContinuationError("waterInventory does not match every boundary-flux timestep")

    initial_mass, initial_quality = _native_inventory(case, start_time, expected_cells)
    final_mass, final_quality = _native_inventory(case, end_time, expected_cells)
    final_fields = _field_finiteness(case, end_time, expected_cells)
    source_flow = float(manifest["source_flow_m3_s_nominal"])
    previous_inventory_m3 = initial_mass / RHO_WATER_KG_M3
    previous_time = start_time
    row_records: list[dict[str, float]] = []
    residual_kg: list[float] = []
    signed_source_m3 = 0.0
    external_net_m3 = 0.0
    wall_m3 = 0.0
    net_boundary_m3 = 0.0
    patch_integrals = {patch: 0.0 for patch in ALL_FLUX_PATCHES}
    for instant in times:
        step_s = float(instant - previous_time)
        q = {patch: float(histories[patch][float(instant)]) for patch in ALL_FLUX_PATCHES}
        inventory_m3 = float(inventory_map[float(instant)])
        total_outward_m3_s = sum(q.values())
        delta_inventory_m3 = inventory_m3 - previous_inventory_m3
        residual = (delta_inventory_m3 + total_outward_m3_s * step_s) * RHO_WATER_KG_M3
        residual_kg.append(residual)
        signed_source_m3 += -q["nozzle"] * step_s
        external_net_m3 += sum(q[patch] for patch in FLUX_PATCHES) * step_s
        wall_m3 += q["aircraftWall"] * step_s
        net_boundary_m3 += total_outward_m3_s * step_s
        for patch in ALL_FLUX_PATCHES:
            patch_integrals[patch] += q[patch] * step_s
        row_records.append(
            {
                "time_s": float(instant),
                "inventory_m3": inventory_m3,
                "delta_inventory_m3": delta_inventory_m3,
                "alphaPhi_nozzle_outward_m3_s": q["nozzle"],
                "alphaPhi_aircraftWall_outward_m3_s": q["aircraftWall"],
                "alphaPhi_external_other_outward_m3_s": sum(q[p] for p in FLUX_PATCHES),
                "alphaPhi_all_boundaries_outward_m3_s": total_outward_m3_s,
                "step_balance_residual_kg": residual,
            }
        )
        previous_inventory_m3 = inventory_m3
        previous_time = float(instant)
    residual_sum_kg = float(sum(residual_kg))
    source_mismatch_m3 = signed_source_m3 - source_flow * (end_time - start_time)
    checks = {
        "all_boundary_fluxes_sampled_at_each_fixed_step": times.size == expected_steps,
        "alpha_bounded": final_fields["alpha_bounded"],
        "required_flow_fields_finite": final_fields["U_finite"]
        and all(bool(row["finite"]) for row in final_fields["scalars"].values()),
        "nozzle_flow_is_inward_by_openfoam_sign": all(
            histories["nozzle"][float(t)] < 0 for t in times
        ),
        "summed_boundary_balance_within_0p1_percent_of_actual_source": (
            abs(residual_sum_kg) / (abs(signed_source_m3) * RHO_WATER_KG_M3) <= 0.001
            if signed_source_m3 != 0
            else False
        ),
    }
    columns = list(row_records[0])
    with (run_dir / "event-step-balance.csv").open("w", encoding="utf-8") as stream:
        stream.write(",".join(columns) + "\n")
        for row in row_records:
            stream.write(",".join(f"{row[column]:.12g}" for column in columns) + "\n")
    stability = _parse_event_stability_log(run_dir / "flow.log", start_time, end_time)
    if stability:
        stability_columns = list(stability[0])
        with (run_dir / "event-stability.csv").open("w", encoding="utf-8") as stream:
            stream.write(",".join(stability_columns) + "\n")
            for row in stability:
                stream.write(
                    ",".join(
                        "" if row[column] is None else str(row[column])
                        for column in stability_columns
                    )
                    + "\n"
                )
    return {
        "schema_version": 1,
        "scope": "Exploratory fixed-deltaT event diagnostic; signed FV phase balance from all physical boundary alphaPhi_ sums.",
        "source_run_id": manifest["source_run_id"],
        "checkpoint_time_s": start_time,
        "end_time_s": end_time,
        "delta_t_s": delta_t,
        "step_count": int(times.size),
        "initial_inventory_kg": initial_mass,
        "final_inventory_kg": final_mass,
        "initial_field_quality": initial_quality,
        "final_field_quality": final_quality,
        "final_field_checks": final_fields,
        "flux_orientation": "OpenFOAM alphaPhi_ is outward-positive on each patch; nozzle inward flow is negative. Per-step residual = (Vwater[n]-Vwater[n-1] + dt*sum(alphaPhi_all_boundary[n]))*rho_water; positive means inventory grew more than signed boundary flux predicts.",
        "source_flow_nominal_m3_s_for_comparison_only": source_flow,
        "measured_nozzle_inflow_volume_m3_from_alphaPhi": signed_source_m3,
        "nominal_nozzle_volume_m3": source_flow * (end_time - start_time),
        "measured_minus_nominal_source_volume_m3": source_mismatch_m3,
        "measured_nozzle_source_mismatch_fraction": source_mismatch_m3
        / (source_flow * (end_time - start_time)),
        "net_other_open_boundary_outward_volume_m3": external_net_m3,
        "aircraft_wall_alphaPhi_integral_m3": wall_m3,
        "net_all_boundary_alphaPhi_integral_m3": net_boundary_m3,
        "per_patch_outward_flux_integrals_m3": patch_integrals,
        "signed_fv_balance_residual_kg": residual_sum_kg,
        "max_abs_per_step_signed_fv_balance_residual_kg": max(map(abs, residual_kg)),
        "rms_per_step_signed_fv_balance_residual_kg": float(
            np.sqrt(np.mean(np.square(residual_kg)))
        ),
        "event_stability_sample_count": len(stability),
        "event_stability_max_courant": max(
            (float(row["courant_max"]) for row in stability if row["courant_max"] is not None),
            default=None,
        ),
        "event_stability_max_interface_courant": max(
            (
                float(row["interface_courant_max"])
                for row in stability
                if row["interface_courant_max"] is not None
            ),
            default=None,
        ),
        "event_stability_min_conservative_bounding_alpha": min(
            (
                float(row["conservative_bounding_min_alpha"])
                for row in stability
                if row.get("conservative_bounding_min_alpha") is not None
            ),
            default=None,
        ),
        "event_stability_csv": "event-stability.csv" if stability else None,
        "checks": checks,
        "diagnostic_ledger_pass": all(checks.values()),
        "per_step_csv": "event-step-balance.csv",
    }


def continuation_ledger(
    *,
    initial_inventory_kg: float,
    final_inventory_kg: float,
    prior_released_kg: float,
    prior_escaped_kg: float,
    incremental_source_kg: float,
    incremental_escaped_kg: float,
) -> dict[str, float]:
    """Return separate continuation and cumulative balances including t0 inventory."""
    incremental_residual = (
        initial_inventory_kg + incremental_source_kg - incremental_escaped_kg - final_inventory_kg
    )
    total_released = prior_released_kg + incremental_source_kg
    total_escaped = prior_escaped_kg + incremental_escaped_kg
    cumulative_residual = total_released - total_escaped - final_inventory_kg
    parent_residual = prior_released_kg - prior_escaped_kg - initial_inventory_kg
    return {
        "initial_inventory_kg": initial_inventory_kg,
        "final_inventory_kg": final_inventory_kg,
        "prior_released_kg": prior_released_kg,
        "prior_escaped_kg": prior_escaped_kg,
        "incremental_source_kg": incremental_source_kg,
        "incremental_escaped_kg": incremental_escaped_kg,
        "total_released_kg": total_released,
        "total_escaped_kg": total_escaped,
        "parent_checkpoint_residual_kg": parent_residual,
        "incremental_residual_kg": incremental_residual,
        "incremental_residual_fraction": incremental_residual / incremental_source_kg
        if incremental_source_kg > 0
        else math.nan,
        "cumulative_residual_kg": cumulative_residual,
        "cumulative_residual_fraction": cumulative_residual / total_released
        if total_released > 0
        else math.nan,
    }


def _native_inventory(
    case: Path, time_s: float, expected_cells: int
) -> tuple[float, dict[str, Any]]:
    time_dir = case / f"{time_s:g}"
    alpha_path = time_dir / "alpha.water"
    volume_path = time_dir / "V"
    if not volume_path.is_file():
        eligible_volume_paths = []
        for candidate in case.iterdir():
            if not candidate.is_dir() or not (candidate / "V").is_file():
                continue
            try:
                candidate_time = float(candidate.name)
            except ValueError:
                continue
            if candidate_time <= time_s:
                eligible_volume_paths.append((candidate_time, candidate / "V"))
        if eligible_volume_paths:
            volume_path = max(eligible_volume_paths, key=lambda item: item[0])[1]
    if not alpha_path.is_file() or not volume_path.is_file():
        raise ContinuationError(f"native alpha.water or V is missing at t={time_s:g} s")
    alpha = read_volume_scalar_field(alpha_path, expected_cells, (0, 0, 0, 0, 0, 0, 0)).internal
    volumes = read_volume_scalar_field(volume_path, expected_cells, (0, 3, 0, 0, 0, 0, 0)).internal
    if not np.isfinite(alpha).all() or not np.isfinite(volumes).all() or np.any(volumes <= 0):
        raise ContinuationError(f"non-finite alpha or invalid cell volume at t={time_s:g} s")
    return float(np.dot(alpha, volumes) * RHO_WATER_KG_M3), {
        "alpha_min": float(np.min(alpha)),
        "alpha_max": float(np.max(alpha)),
        "alpha_out_of_bounds_count": int(np.count_nonzero((alpha < -1e-8) | (alpha > 1.0 + 1e-8))),
        "finite_alpha": True,
        "cell_count": int(alpha.size),
        "volume_sum_m3": float(np.sum(volumes)),
    }


def _field_finiteness(case: Path, time_s: float, expected_cells: int) -> dict[str, Any]:
    directory = case / f"{time_s:g}"
    alpha = read_volume_scalar_field(
        directory / "alpha.water", expected_cells, (0, 0, 0, 0, 0, 0, 0)
    ).internal
    velocity = read_volume_vector_internal(directory / "U", expected_cells)
    scalars: dict[str, dict[str, float | bool]] = {}
    for name, dimensions in {
        "k": (0, 2, -2, 0, 0, 0, 0),
        "epsilon": (0, 2, -3, 0, 0, 0, 0),
        "nut": (0, 2, -1, 0, 0, 0, 0),
    }.items():
        values = read_volume_scalar_field(directory / name, expected_cells, dimensions).internal
        scalars[name] = {
            "finite": bool(np.isfinite(values).all()),
            "minimum": float(np.nanmin(values)),
            "maximum": float(np.nanmax(values)),
        }
    return {
        "time_s": time_s,
        "alpha_min": float(np.min(alpha)),
        "alpha_max": float(np.max(alpha)),
        "alpha_bounded": bool(np.all((alpha >= -1e-8) & (alpha <= 1.0 + 1e-8))),
        "U_finite": bool(np.isfinite(velocity).all()),
        "U_max_magnitude_m_s": float(np.max(np.linalg.norm(velocity, axis=1))),
        "scalars": scalars,
    }


def _analyze(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    case = run_dir / "case"
    parent, parent_case = _read_parent()
    end_time = float(manifest["solver"]["end_time_s"])
    expected_cells = int(parent["diagnostics"]["cell_count"])
    initial_mass, initial_quality = _native_inventory(parent_case, START_TIME_S, expected_cells)
    final_mass, final_quality = _native_inventory(case, end_time, expected_cells)
    finiteness = _field_finiteness(case, end_time, expected_cells)

    parent_times, parent_flux = _parent_flux_history(parent_case)
    parent_escape_m3 = _trapezoid(parent_flux, parent_times)
    declared_parent_escape = float(
        parent["diagnostics"]["open_boundary_net_escaped_water_volume_m3"]
    )
    if not math.isclose(parent_escape_m3, declared_parent_escape, rel_tol=0, abs_tol=2e-10):
        raise ContinuationError(
            f"recomputed prior escape {parent_escape_m3:.12g} m3 differs from parent ledger {declared_parent_escape:.12g} m3"
        )

    continuation_times, continuation_flux = _parse_flux_history(case)
    keep = continuation_times > START_TIME_S + 1e-10
    if not np.any(keep):
        raise ContinuationError("new continuation has no post-checkpoint boundary-flux samples")
    t_new = continuation_times[keep]
    q_new = continuation_flux[keep]
    incremental_escape_m3 = _right_endpoint_step_integral(START_TIME_S, t_new, q_new, DELTA_T_S)
    inventory_times, inventory_values = _parse_inventory_history(case)
    inventory_keep = inventory_times > START_TIME_S + 1e-10
    if not np.array_equal(inventory_times[inventory_keep], t_new):
        raise ContinuationError("waterInventory and alphaPhi_ samples differ in time")
    previous_inventory_m3 = initial_mass / RHO_WATER_KG_M3
    stepwise_residuals_kg: list[float] = []
    previous_time = START_TIME_S
    for instant, inventory_m3, external_flux_m3_s in zip(
        inventory_times[inventory_keep], inventory_values[inventory_keep], q_new, strict=True
    ):
        step_s = float(instant - previous_time)
        if not math.isclose(step_s, DELTA_T_S, rel_tol=0, abs_tol=1e-9):
            raise ContinuationError("inventory samples do not align with fixed deltaT")
        expected_in_m3 = float(parent["nozzle_patch"]["measured_volume_flow_m3_s"]) * step_s
        residual_m3 = (
            expected_in_m3 - external_flux_m3_s * step_s - (inventory_m3 - previous_inventory_m3)
        )
        stepwise_residuals_kg.append(residual_m3 * RHO_WATER_KG_M3)
        previous_inventory_m3 = float(inventory_m3)
        previous_time = float(instant)
    q_source_m3_s = float(parent["nozzle_patch"]["measured_volume_flow_m3_s"])
    prior_source_kg = q_source_m3_s * START_TIME_S * RHO_WATER_KG_M3
    prior_escape_kg = parent_escape_m3 * RHO_WATER_KG_M3
    incremental_source_kg = q_source_m3_s * (end_time - START_TIME_S) * RHO_WATER_KG_M3
    incremental_escape_kg = incremental_escape_m3 * RHO_WATER_KG_M3
    ledger = continuation_ledger(
        initial_inventory_kg=initial_mass,
        final_inventory_kg=final_mass,
        prior_released_kg=prior_source_kg,
        prior_escaped_kg=prior_escape_kg,
        incremental_source_kg=incremental_source_kg,
        incremental_escaped_kg=incremental_escape_kg,
    )
    time_rows = [float(value) for value in continuation_times if value > START_TIME_S + 1e-10]
    observed_end = max(time_rows, default=math.nan)
    delta_steps = round((end_time - START_TIME_S) / DELTA_T_S)
    checks = {
        "reconstructed_end_time_matches_declaration": math.isclose(
            observed_end, end_time, abs_tol=1e-9
        ),
        "one_flux_sample_per_fixed_delta_t_step": int(np.count_nonzero(keep)) == delta_steps,
        "alpha_bounded": finiteness["alpha_bounded"],
        "flow_fields_finite": finiteness["U_finite"]
        and all(bool(value["finite"]) for value in finiteness["scalars"].values()),
        "cumulative_phase_ledger_within_0p1_percent": abs(ledger["cumulative_residual_fraction"])
        <= 0.001,
    }
    return {
        "schema_version": 1,
        "scope": "Exploratory restart and finite-horizon continuation check; not an E1 acceptance decision.",
        "parent_run_id": PARENT_RUN_ID,
        "start_time_s": START_TIME_S,
        "declared_end_time_s": end_time,
        "observed_last_flux_time_s": observed_end,
        "new_flux_sample_count": int(np.count_nonzero(keep)),
        "expected_fixed_dt_steps": int(delta_steps),
        "initial_inventory_check_at_parent_checkpoint": initial_quality,
        "final_inventory_check": final_quality,
        "final_field_checks": finiteness,
        "source_flow_m3_s": q_source_m3_s,
        "prior_source_volume_m3": q_source_m3_s * START_TIME_S,
        "prior_escape_volume_m3_recomputed_from_parent_flux": parent_escape_m3,
        "incremental_source_volume_m3": q_source_m3_s * (end_time - START_TIME_S),
        "incremental_escape_volume_m3": incremental_escape_m3,
        "incremental_escape_integration": "sum(native alphaPhi_ external-boundary flux at each solver time multiplied by the preceding fixed deltaT; checked against per-step waterInventory changes",
        "max_abs_per_step_mass_balance_residual_kg": max(map(abs, stepwise_residuals_kg)),
        "rms_per_step_mass_balance_residual_kg": float(
            np.sqrt(np.mean(np.square(stepwise_residuals_kg)))
        ),
        "water_ledger": ledger,
        "checks": checks,
        "exploratory_checks_pass": all(checks.values()),
    }


def _control_shell(cpus: int, checkpoint_time_s: float = START_TIME_S) -> str:
    return (
        "set +e +u; source_status=0; source "
        + shlex_quote(OPENFOAM_BASHRC)
        + ' || source_status=$?; set +e +u; printf "CONTINUATION_SETUP_EXIT code=%s\\n" "$source_status"; '
        + 'if [ "$source_status" -ne 0 ]; then exit "$source_status"; fi; '
        + "set -euo pipefail; "
        + 'run_stage() { local stage="$1"; shift; local code=0; "$@" || code=$?; '
        + 'printf "CONTINUATION_STAGE_EXIT stage=%s code=%s\\n" "$stage" "$code"; '
        + '[ "$code" -eq 0 ] || exit "$code"; }; '
        + "run_stage decomposePar decomposePar -force -time "
        + f"{checkpoint_time_s:.12g}; "
        + "run_stage interIsoFoam mpirun --bind-to none -np "
        + str(cpus)
        + " interIsoFoam -parallel; "
        + "run_stage reconstructPar reconstructPar -latestTime -fields '(alpha.water U p_rgh k epsilon nut)'"
    )


def shlex_quote(value: str) -> str:
    """Quote the fixed OpenFOAM shell setup path without importing shell state."""
    return "'" + value.replace("'", "'\\''") + "'"


def _container_command(run_dir: Path, manifest: dict[str, Any]) -> list[str]:
    cpus = int(manifest["allocation"]["mpi_ranks"])
    memory_gib = int(manifest["allocation"]["memory_gib"])
    name = f"rouaix-c4-cont-{run_dir.name}"
    cidfile = run_dir / "flow.cid"
    if cidfile.exists():
        raise ContinuationError(f"refusing to reuse container ID file {cidfile}")
    return [
        "docker",
        "run",
        f"--name={name}",
        f"--cidfile={cidfile}",
        f"--cpus={cpus}",
        f"--memory={memory_gib}g",
        "--memory-swap",
        f"{memory_gib}g",
        "--env",
        "OMP_NUM_THREADS=1",
        "--env",
        "OMP_THREAD_LIMIT=1",
        "--env",
        "OPENBLAS_NUM_THREADS=1",
        "--env",
        "MKL_NUM_THREADS=1",
        "--env",
        "BLIS_NUM_THREADS=1",
        "--env",
        "NUMEXPR_NUM_THREADS=1",
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
        _control_shell(cpus, float(manifest["continuation"]["from_time_s"])),
    ]


def _container_id(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    return value if CONTAINER_ID_RE.fullmatch(value) else None


def _inspect_container(cid: str) -> dict[str, Any] | None:
    result = subprocess.run(["docker", "inspect", cid], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        raw = json.loads(result.stdout)[0]
    except (json.JSONDecodeError, IndexError):
        return None
    state = raw.get("State", {})
    return {
        "id": raw.get("Id"),
        "name": raw.get("Name"),
        "image_id": raw.get("Image"),
        "status": state.get("Status"),
        "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "error": state.get("Error"),
    }


def _worker(run_dir: Path) -> int:
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest["worker_started_utc"] = _utc_now()
    _write_json(manifest_path, manifest)
    start = time.monotonic()
    result_code = 1
    try:
        resolved = subprocess.run(
            ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        image_id = resolved.stdout.strip()
        manifest["solver"]["resolved_image_id"] = image_id
        _write_json(manifest_path, manifest)
        if resolved.returncode != 0 or image_id != PINNED_IMAGE_ID:
            raise ContinuationError(
                f"pinned image check failed: status={resolved.returncode}, id={image_id!r}"
            )
        command = _container_command(run_dir, manifest)
        (run_dir / "flow-command.json").write_text(
            json.dumps(command, indent=2) + "\n", encoding="utf-8"
        )
        log_path = run_dir / "flow.log"
        wall_start = time.monotonic()
        with log_path.open("ab", buffering=0) as log:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
            try:
                docker_exit = process.wait(timeout=float(manifest["allocation"]["timeout_s"]))
            except subprocess.TimeoutExpired:
                container_name = command[2].split("=", 1)[1]
                subprocess.run(
                    ["docker", "stop", "--time", "20", container_name],
                    capture_output=True,
                    timeout=40,
                    check=False,
                )
                try:
                    docker_exit = process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    process.kill()
                    docker_exit = process.wait()
                manifest["timed_out"] = True
                manifest["timeout_wall_s"] = float(manifest["allocation"]["timeout_s"])
        wall_s = time.monotonic() - wall_start
        cid = _container_id(run_dir / "flow.cid")
        inspect = _inspect_container(cid) if cid else None
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        stage_codes = {
            match.group(1): int(match.group(2))
            for match in re.finditer(
                r"(?m)^CONTINUATION_STAGE_EXIT stage=(\w+) code=(-?\d+)\s*$", log_text
            )
        }
        solver_times = [
            float(match.group(1))
            for match in re.finditer(rf"(?m)^Time\s*=\s*({FLOAT_RE})\s*$", log_text)
        ]
        manifest["stages"]["flow"] = {
            "docker_client_exit_code": docker_exit,
            "container_inspect": inspect,
            "container_id": cid,
            "wall_time_s": round(wall_s, 3),
            "log": log_path.name,
            "stage_codes": stage_codes,
            "solver_time_samples": len(solver_times),
            "last_solver_time_s": solver_times[-1] if solver_times else None,
        }
        _write_json(manifest_path, manifest)
        if docker_exit != 0 or (inspect is not None and inspect.get("exit_code") != 0):
            raise ContinuationError(
                f"flow did not exit zero: docker={docker_exit}, inspect={inspect}"
            )
        if stage_codes != {"decomposePar": 0, "interIsoFoam": 0, "reconstructPar": 0}:
            raise ContinuationError(f"one or more flow stages failed: {stage_codes}")
        event_diagnostic = manifest.get("analysis_mode", "").startswith("all_boundary_")
        analysis = _analyze_boundary_diagnostic(run_dir) if event_diagnostic else _analyze(run_dir)
        _write_json(run_dir / "continuation-analysis.json", analysis)
        manifest["analysis"] = analysis
        if event_diagnostic:
            manifest["status"] = "completed_boundary_diagnostic"
        else:
            if not analysis["exploratory_checks_pass"]:
                raise ContinuationError(f"continuation checks failed: {analysis['checks']}")
            manifest["status"] = "completed_exploratory_continuation"
        result_code = 0
    except (OSError, subprocess.SubprocessError, ContinuationError, ValueError, KeyError) as error:
        manifest["status"] = "failed"
        manifest["failure_or_stop_reason"] = f"{type(error).__name__}: {error}"
        result_code = 1
    finally:
        manifest["completed_utc"] = _utc_now()
        manifest["worker_wall_time_s"] = round(time.monotonic() - start, 3)
        _write_json(manifest_path, manifest)
        (run_dir / "worker.exit").write_text(f"{result_code}\n", encoding="ascii")
    return result_code


def _source_inventory(parent: dict[str, Any], case: Path) -> tuple[float, dict[str, Any]]:
    return _native_inventory(case, START_TIME_S, int(parent["diagnostics"]["cell_count"]))


def _prepare(run_id: str, cpus: int, memory_gib: int, end_time_s: float, timeout_s: int) -> Path:
    if cpus not in (16, 20):
        raise ContinuationError("rank count must be 16 or 20")
    if memory_gib < 16 or memory_gib > 96:
        raise ContinuationError("memory allocation must be between 16 and 96 GiB")
    steps = (end_time_s - START_TIME_S) / DELTA_T_S
    if end_time_s <= START_TIME_S or not math.isclose(steps, round(steps), abs_tol=1e-8):
        raise ContinuationError("end time must exceed 0.4 s by an integer number of 0.001 s steps")
    if timeout_s <= 0 or timeout_s > 10800:
        raise ContinuationError("continuation timeout must be in (0, 10800] seconds")
    parent, parent_case = _read_parent()
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    case = run_dir / "case"
    case.mkdir()
    try:
        source_hashes: dict[str, str] = {}
        copy_hashes: dict[str, str] = {}

        def copy_file(source: Path, relative: str) -> None:
            target = case / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            source_hashes[relative] = _sha256(source)
            copy_hashes[relative] = _sha256(target)
            if source_hashes[relative] != copy_hashes[relative]:
                raise ContinuationError(f"copied input hash mismatch: {relative}")

        source_mesh = parent_case / "constant/polyMesh"
        target_mesh = case / "constant/polyMesh"
        target_mesh.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["cp", "-a", str(source_mesh), str(target_mesh)],
            check=True,
            capture_output=True,
            text=True,
        )
        source_hashes.update(
            {f"constant/polyMesh/{k}": v for k, v in _hash_tree(source_mesh).items()}
        )
        copy_hashes.update(
            {f"constant/polyMesh/{k}": v for k, v in _hash_tree(target_mesh).items()}
        )
        if source_hashes != copy_hashes:
            raise ContinuationError("polyMesh changed while copying")

        for name in CONSTANT_INPUTS:
            copy_file(parent_case / "constant" / name, f"constant/{name}")
        checkpoint = parent_case / "0.4"
        checkpoint_copy = case / "0.4"
        checkpoint_copy.mkdir()
        for source in sorted(checkpoint.iterdir()):
            if source.is_file():
                copy_file(source, f"0.4/{source.name}")
            elif source.name == "uniform":
                for nested in sorted(source.rglob("*")):
                    if nested.is_file():
                        copy_file(nested, f"0.4/uniform/{nested.relative_to(source).as_posix()}")

        (case / "system").mkdir()
        source_control = parent_case / "system/controlDict"
        write_interval = 0.005 if math.isclose(end_time_s, 0.405, abs_tol=1e-10) else 0.025
        control_text = _control_dict(
            source_control.read_text(encoding="utf-8"), end_time_s, write_interval
        )
        target_control = case / "system/controlDict"
        target_control.write_text(control_text, encoding="utf-8")
        source_hashes["system/controlDict"] = _sha256(source_control)
        copy_hashes["system/controlDict"] = _sha256(target_control)
        for name in ("fvSchemes", "fvSolution"):
            copy_file(parent_case / "system" / name, f"system/{name}")
        decompose_text = _decompose_dict(cpus)
        decompose_path = case / "system/decomposeParDict"
        decompose_path.write_text(decompose_text, encoding="utf-8")

        input_hashes = _hash_tree(case)
        initial_inventory_kg, quality = _source_inventory(parent, parent_case)
        recorded_inventory = float(parent["diagnostics"]["snapshots"][-1]["water_mass_kg"])
        if not math.isclose(initial_inventory_kg, recorded_inventory, rel_tol=0, abs_tol=2e-7):
            raise ContinuationError(
                f"checkpoint inventory {initial_inventory_kg:.12g} kg differs from prior diagnostics {recorded_inventory:.12g} kg"
            )
        allocation = {
            "mpi_ranks": cpus,
            "memory_gib": memory_gib,
            "timeout_s": timeout_s,
            "host_threads_for_supervisor": 1,
            "thread_env_in_container": 1,
        }
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "prepared",
            "created_utc": _utc_now(),
            "experiment": "Exploratory Rouaix Case 4 / Mesh 4 CPU checkpoint continuation",
            "parent_run_id": PARENT_RUN_ID,
            "parent_manifest_sha256": _sha256(PARENT_RUN / "manifest.json"),
            "parent_status": parent["status"],
            "continuation": {
                "from_time_s": START_TIME_S,
                "end_time_s": end_time_s,
                "physical_time_advanced_s": end_time_s - START_TIME_S,
                "fixed_delta_t_s": DELTA_T_S,
                "expected_steps": int(round(steps)),
                "startFrom": "latestTime",
                "checkpoint_relative_path": "case/0.4",
                "copied_time_directories": ["0.4"],
                "prior_full_source_history_not_copied": True,
                "prior_source_and_escape_retained_as_ledger_offsets": True,
            },
            "mesh": {
                "source_profile": parent["mesh"]["profile"],
                "cell_count": int(parent["diagnostics"]["cell_count"]),
                "mesh_source_run": PARENT_RUN_ID,
                "polyMesh_hashes_identical": True,
            },
            "solver": {
                "application": "interIsoFoam",
                "image": IMAGE,
                "expected_image_id": PINNED_IMAGE_ID,
                "resolved_image_id": None,
                "delta_t_s": DELTA_T_S,
                "end_time_s": end_time_s,
                "write_interval_s": write_interval,
                "adjust_time_step": False,
                "physics_and_field_schemes": "byte-identical to parent except control start/end/write times; same constant properties and checkpoint fields",
            },
            "initial_checkpoint_inventory_kg": initial_inventory_kg,
            "initial_checkpoint_inventory_check": quality,
            "source_flow_m3_s": float(parent["nozzle_patch"]["measured_volume_flow_m3_s"]),
            "prior_ledger_offsets": {
                "released_water_kg": float(
                    parent["diagnostics"]["final_expected_released_water_mass_kg"]
                ),
                "net_open_boundary_escape_m3": float(
                    parent["diagnostics"]["open_boundary_net_escaped_water_volume_m3"]
                ),
                "parent_ledger_residual_fraction": float(
                    parent["diagnostics"]["final_phase_ledger_residual_fraction"]
                ),
            },
            "allocation": allocation,
            "source_input_sha256": source_hashes,
            "copied_input_sha256": copy_hashes,
            "prepared_case_input_sha256": input_hashes,
            "runner_sha256": _sha256(Path(__file__).resolve()),
            "git": _git_state(),
            "stages": {},
            "failure_or_stop_reason": None,
        }
        _write_json(run_dir / "manifest.json", manifest)
        _write_json(
            run_dir / "continuation-declaration.json",
            {
                "declared_utc": manifest["created_utc"],
                "status": "declared_before_launch",
                "objective": "Verify restart from the completed native 0.4 s state, then measure incremental and cumulative phase-volume closure.",
                "parent_run_id": PARENT_RUN_ID,
                "from_time_s": START_TIME_S,
                "to_time_s": end_time_s,
                "cell_count": int(parent["diagnostics"]["cell_count"]),
                "mpi_ranks": cpus,
                "wall_budget_s": timeout_s,
                "checkpoints_and_outputs": [
                    "flow.log",
                    "case/<new-time>/alpha.water",
                    "continuation-analysis.json",
                ],
                "stop_conditions": [
                    "nonzero Docker or stage exit",
                    "missing exact end-time reconstruction",
                    "unbounded alpha",
                    "non-finite required fields",
                    "cumulative phase ledger residual above 0.1%",
                ],
                "not_claimed": [
                    "paper-mesh reproduction",
                    "one-second statistical stationarity",
                    "E1 acceptance",
                ],
            },
        )
        (run_dir / "source-parent-manifest.json").write_bytes(
            (PARENT_RUN / "manifest.json").read_bytes()
        )
        return run_dir
    except Exception:
        (run_dir / "preparation-failure.txt").write_text(
            "Continuation preparation failed; partial artifacts retained.\n", encoding="utf-8"
        )
        raise


def _prepare_event_checkpoint(
    run_id: str,
    source_run_id: str,
    checkpoint_time_s: float,
    end_time_s: float,
    delta_t_s: float,
    cpus: int,
    memory_gib: int,
    timeout_s: int,
) -> Path:
    """Extract one retained processor checkpoint for a fixed-timestep event audit."""
    if cpus not in (4, 16):
        raise ContinuationError("event comparison supports the declared 4- or 16-rank cases")
    if memory_gib < 16 or memory_gib > 96 or timeout_s <= 0 or timeout_s > 7200:
        raise ContinuationError("event diagnostic resources exceed the 2 h / 96 GiB bounds")
    steps = (end_time_s - checkpoint_time_s) / delta_t_s
    if end_time_s <= checkpoint_time_s or not math.isclose(steps, round(steps), abs_tol=1e-8):
        raise ContinuationError("event horizon must be an integer number of fixed deltaT steps")
    if not any(
        math.isclose(delta_t_s, value, rel_tol=0, abs_tol=1e-12) for value in (0.00025, 0.0005)
    ):
        raise ContinuationError("event comparison deltaT must be 0.00025 or 0.0005 s")
    source_run = RUNS_ROOT / source_run_id
    source_manifest_path = source_run / "manifest.json"
    if not source_manifest_path.is_file():
        raise ContinuationError(
            f"event checkpoint source manifest is missing: {source_manifest_path}"
        )
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_flow = source_manifest.get("stages", {}).get("flow", {})
    if (
        source_flow.get("docker_client_exit_code") != 0
        or source_flow.get("last_solver_time_s") != 1.0
    ):
        raise ContinuationError("event checkpoint source must be the completed 1.0 s run")
    if source_manifest.get("solver", {}).get("resolved_image_id") != PINNED_IMAGE_ID:
        raise ContinuationError("event checkpoint source used an unexpected OpenFOAM image")
    source_ranks = int(source_manifest["allocation"]["mpi_ranks"])
    if source_ranks != 16:
        raise ContinuationError(
            "source checkpoint must retain all 16 original processor partitions"
        )
    source_case = source_run / "case"
    source_processor_checkpoint = f"{checkpoint_time_s:g}"
    required_fields = ("alpha.water", "U", "p_rgh", "k", "epsilon", "nut", "p", "phi")
    for rank in range(source_ranks):
        processor = source_case / f"processor{rank}"
        missing = [
            name
            for name in required_fields
            if not (processor / source_processor_checkpoint / name).is_file()
        ]
        if missing or not (processor / "constant/polyMesh/boundary").is_file():
            raise ContinuationError(f"processor{rank} checkpoint is incomplete: {missing}")

    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    case = run_dir / "case"
    case.mkdir()
    try:
        hashes: dict[str, str] = {}

        def copytree_hashed(source: Path, target: Path, relative: str) -> None:
            shutil.copytree(source, target)
            hashes.update(
                {f"{relative}/{name}": value for name, value in _hash_tree(source).items()}
            )
            target_hashes = {
                f"{relative}/{name}": value for name, value in _hash_tree(target).items()
            }
            expected = {
                key: value for key, value in hashes.items() if key.startswith(f"{relative}/")
            }
            if expected != target_hashes:
                raise ContinuationError(f"copied input hashes differ under {relative}")

        copytree_hashed(
            source_case / "constant/polyMesh", case / "constant/polyMesh", "constant/polyMesh"
        )
        for name in CONSTANT_INPUTS:
            source = source_case / "constant" / name
            target = case / "constant" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            hashes[f"constant/{name}"] = _sha256(source)
            if _sha256(target) != hashes[f"constant/{name}"]:
                raise ContinuationError(f"copied constant input hash differs: {name}")
        (case / "system").mkdir()
        source_control = source_case / "system/controlDict"
        control = _control_dict(
            source_control.read_text(encoding="utf-8"),
            end_time_s,
            0.005,
            delta_t_s=delta_t_s,
            extra_flux_patches=("aircraftWall", "nozzle"),
        )
        (case / "system/controlDict").write_text(control, encoding="utf-8")
        hashes["system/controlDict.source"] = _sha256(source_control)
        hashes["system/controlDict.prepared"] = _sha256(case / "system/controlDict")
        for name in ("fvSchemes", "fvSolution"):
            source = source_case / "system" / name
            target = case / "system" / name
            shutil.copy2(source, target)
            hashes[f"system/{name}"] = _sha256(source)
            if _sha256(target) != hashes[f"system/{name}"]:
                raise ContinuationError(f"copied system input hash differs: {name}")
        source_decompose = source_case / "system/decomposeParDict"
        (case / "system/decomposeParDict").write_text(_decompose_dict(cpus), encoding="utf-8")
        hashes["system/decomposeParDict.source"] = _sha256(source_decompose)
        hashes["system/decomposeParDict.prepared"] = _sha256(case / "system/decomposeParDict")
        for rank in range(source_ranks):
            source_proc = source_case / f"processor{rank}"
            target_proc = case / f"processor{rank}"
            (target_proc / "constant").mkdir(parents=True)
            copytree_hashed(
                source_proc / "constant/polyMesh",
                target_proc / "constant/polyMesh",
                f"processor{rank}/constant/polyMesh",
            )
            target_time = target_proc / source_processor_checkpoint
            target_time.mkdir()
            for name in required_fields:
                source = source_proc / source_processor_checkpoint / name
                shutil.copy2(source, target_time / name)
                rel = f"processor{rank}/{source_processor_checkpoint}/{name}"
                hashes[rel] = _sha256(source)
            for name in ("time", "cumulativeContErr"):
                source = source_proc / source_processor_checkpoint / "uniform" / name
                if source.is_file():
                    destination = target_time / "uniform" / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    rel = f"processor{rank}/{source_processor_checkpoint}/uniform/{name}"
                    hashes[rel] = _sha256(source)

        # Reconstruct only this checkpoint in the new bundle; the failed source remains untouched.
        name = f"rouaix-extract-{run_id}"
        cidfile = run_dir / "checkpoint-reconstruct.cid"
        command = [
            "docker",
            "run",
            f"--name={name}",
            f"--cidfile={cidfile}",
            "--cpus=2",
            "--memory=24g",
            "--memory-swap",
            "24g",
            "--env",
            "OMP_NUM_THREADS=1",
            "--env",
            "OPENBLAS_NUM_THREADS=1",
            "--env",
            "MKL_NUM_THREADS=1",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--mount",
            f"type=bind,src={case},dst=/case",
            "--workdir",
            "/case",
            "--entrypoint",
            "/bin/bash",
            IMAGE,
            "-c",
            "set +e +u; source_status=0; source "
            + shlex_quote(OPENFOAM_BASHRC)
            + ' || source_status=$?; set +e +u; if [ "$source_status" -ne 0 ]; then exit "$source_status"; fi; '
            + "set -euo pipefail; reconstructPar -time "
            + f"{checkpoint_time_s:.12g} -fields '(alpha.water U p_rgh k epsilon nut)'",
        ]
        (run_dir / "checkpoint-reconstruct-command.json").write_text(
            json.dumps(command, indent=2) + "\n", encoding="utf-8"
        )
        with (run_dir / "checkpoint-reconstruct.log").open("wb") as log:
            extract_process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            extract_exit = extract_process.wait(timeout=1800)
        cid = _container_id(cidfile)
        extract_inspect = _inspect_container(cid) if cid else None
        if extract_exit != 0 or not (case / source_processor_checkpoint / "alpha.water").is_file():
            raise ContinuationError(
                f"checkpoint reconstruction failed: docker exit={extract_exit}; inspect={extract_inspect}"
            )
        volume_source = source_case / "0.4/V"
        if not volume_source.is_file():
            raise ContinuationError("global native cell-volume field V is missing from source")
        shutil.copy2(volume_source, case / source_processor_checkpoint / "V")
        hashes[f"{source_processor_checkpoint}/V copied from t0.4"] = _sha256(volume_source)

        prior_release_m3 = float(source_manifest["source_flow_m3_s"]) * checkpoint_time_s
        old_parent, old_parent_case = _read_parent()
        parent_times, parent_flux = _parent_flux_history(old_parent_case)
        prior_escape_m3 = _trapezoid(parent_flux, parent_times)
        full_times, full_flux = _parse_flux_history(source_case)
        interval = (full_times > START_TIME_S + 1e-10) & (full_times <= checkpoint_time_s + 1e-10)
        if not np.any(interval):
            raise ContinuationError(
                "source run has no boundary flux history up to the event checkpoint"
            )
        prior_escape_m3 += _right_endpoint_step_integral(
            START_TIME_S, full_times[interval], full_flux[interval], DELTA_T_S
        )
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "prepared",
            "created_utc": _utc_now(),
            "experiment": "Exploratory Rouaix event-focused fixed-deltaT all-boundary phase-flux diagnostic",
            "analysis_mode": "all_boundary_fixed_dt",
            "source_run_id": source_run_id,
            "source_run_manifest_sha256": _sha256(source_manifest_path),
            "source_run_solver_status": source_manifest.get("status"),
            "source_run_water_ledger_failure_preserved": source_manifest.get(
                "failure_or_stop_reason"
            ),
            "source_run_snapshot_time_s": checkpoint_time_s,
            "source_run_snapshot_kind": "processor-local checkpoint extracted from the already completed 16-rank run",
            "continuation": {
                "from_time_s": checkpoint_time_s,
                "end_time_s": end_time_s,
                "delta_t_s": delta_t_s,
                "expected_steps": int(round(steps)),
                "startFrom": "latestTime",
                "decomposePar_checkpoint_time_s": checkpoint_time_s,
                "write_interval_s": 0.005,
                "event_of_interest_s": 0.604,
                "predeclared_shared_comparison": (
                    "4 ranks at dt=0.00025 versus the existing 16-rank dt=0.0005 case "
                    "from the same 0.600 s checkpoint through 0.620 s"
                ),
            },
            "mesh": {
                "cell_count": int(source_manifest["mesh"]["cell_count"]),
                "source_mesh_run": source_run_id,
                "source_checkpoint_ranks": source_ranks,
                "decomposition_ranks": cpus,
                "processor_decomposition": " x ".join(
                    map(str, {4: (2, 2, 1), 16: (4, 2, 2)}[cpus])
                ),
                "copied_source_hashes": hashes,
            },
            "solver": {
                "application": "interIsoFoam",
                "image": IMAGE,
                "expected_image_id": PINNED_IMAGE_ID,
                "resolved_image_id": None,
                "delta_t_s": delta_t_s,
                "end_time_s": end_time_s,
                "adjust_time_step": False,
                "added_flux_writers": ["aircraftWall", "nozzle"],
                "all_boundary_flux_writers": list(ALL_FLUX_PATCHES),
                "physics_inputs": "same mesh, constant properties, fvSchemes and fvSolution as source; only dt, end/write time and diagnostic function objects changed",
            },
            "source_flow_m3_s_nominal": float(source_manifest["source_flow_m3_s"]),
            "prior_ledger_offsets": {
                "prior_released_nominal_volume_m3": prior_release_m3,
                "prior_external_net_escape_volume_m3": prior_escape_m3,
                "prior_release_caveat": "The original run did not record nozzle alphaPhi_ before t=0.6; this offset uses its measured constant nozzle flow, while this event window records actual nozzle alphaPhi_ every step.",
            },
            "allocation": {
                "mpi_ranks": cpus,
                "memory_gib": memory_gib,
                "timeout_s": timeout_s,
                "host_threads_for_supervisor": 1,
                "thread_env_in_container": 1,
            },
            "checkpoint_reconstruction": {
                "container_id": cid,
                "container_inspect": extract_inspect,
                "docker_exit_code": extract_exit,
                "log": "checkpoint-reconstruct.log",
            },
            "source_checkpoint_file_sha256": hashes,
            "runner_sha256": _sha256(Path(__file__).resolve()),
            "stages": {},
        }
        _write_json(run_dir / "manifest.json", manifest)
        _write_json(
            run_dir / "continuation-declaration.json",
            {
                "declared_utc": manifest["created_utc"],
                "status": "declared_before_solver_launch",
                "objective": "Compare the .600-.620 s fixed-time-step phase ledger and outlet observables using measured all-boundary alphaPhi_.",
                "source_run_id": source_run_id,
                "checkpoint_time_s": checkpoint_time_s,
                "end_time_s": end_time_s,
                "delta_t_s": delta_t_s,
                "cell_count": manifest["mesh"]["cell_count"],
                "mpi_ranks": cpus,
                "timeout_s": timeout_s,
                "sign_convention": "outward alphaPhi_ positive; inward nozzle flow negative; balance residual=(delta inventory+dt*sum all outward boundary alphaPhi_)*rho_water",
                "not_claimed": [
                    "Rouaix paper-mesh reproduction",
                    "E1 acceptance",
                    "validation of the one-second run",
                ],
            },
        )
        shutil.copy2(source_manifest_path, run_dir / "source-run-manifest.json")
        return run_dir
    except Exception:
        (run_dir / "preparation-failure.txt").write_text(
            "Event diagnostic preparation failed; partial files and logs are preserved.\n",
            encoding="utf-8",
        )
        raise


def _launch(run_dir: Path) -> dict[str, Any]:
    worker_command = [
        sys.executable,
        str(ROOT / "scripts/run_local.py"),
        "--threads",
        "1",
        "--",
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        str(run_dir),
    ]
    log_path = run_dir / "continuation-worker.log"
    with log_path.open("ab", buffering=0) as log:
        process = subprocess.Popen(
            worker_command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    launch = {
        "started_utc": _utc_now(),
        "host_pid": process.pid,
        "process_group": process.pid,
        "command": worker_command,
        "detached_session": True,
        "stdin": "DEVNULL",
        "log": log_path.name,
    }
    _write_json(run_dir / "launch.json", launch)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["status"] = "launched_detached"
    manifest["host_worker_pid"] = process.pid
    _write_json(run_dir / "manifest.json", manifest)
    return launch


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--end-time-s", type=float)
    parser.add_argument(
        "--event-source-run", help="use a completed run's processor-local event checkpoint"
    )
    parser.add_argument("--checkpoint-time-s", type=float, default=0.6)
    parser.add_argument("--delta-t-s", type=float, default=0.0005)
    parser.add_argument("--cpus", type=int, default=16)
    parser.add_argument("--memory-gib", type=int, default=48)
    parser.add_argument("--timeout-s", type=int, default=10800)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--launch-prepared", type=Path)
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return args
    if not args.launch_prepared and (not args.run_id or args.end_time_s is None):
        parser.error("--run-id and --end-time-s are required when preparing a continuation")
    if args.run_id is not None and not RUN_ID_RE.fullmatch(args.run_id):
        parser.error("run ID may contain only letters, digits, dot, underscore and hyphen")
    if args.launch_prepared and args.prepare_only:
        parser.error("choose either --prepare-only or --launch-prepared")
    if args.end_time_s is not None and not math.isfinite(args.end_time_s):
        parser.error("end time must be finite")
    if args.event_source_run and not math.isfinite(args.checkpoint_time_s):
        parser.error("checkpoint time must be finite")
    if args.event_source_run and not math.isfinite(args.delta_t_s):
        parser.error("deltaT must be finite")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        return _worker(args.worker.resolve())
    if args.launch_prepared:
        run_dir = args.launch_prepared.resolve()
        if not (run_dir / "manifest.json").is_file():
            print(f"prepared run is missing manifest: {run_dir}", file=sys.stderr)
            return 2
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") != "prepared":
            print(f"refusing to launch status={manifest.get('status')!r}", file=sys.stderr)
            return 2
    else:
        try:
            if args.event_source_run:
                run_dir = _prepare_event_checkpoint(
                    args.run_id,
                    args.event_source_run,
                    args.checkpoint_time_s,
                    args.end_time_s,
                    args.delta_t_s,
                    args.cpus,
                    args.memory_gib,
                    args.timeout_s,
                )
            else:
                run_dir = _prepare(
                    args.run_id,
                    args.cpus,
                    args.memory_gib,
                    args.end_time_s,
                    args.timeout_s,
                )
        except (OSError, subprocess.SubprocessError, ContinuationError, ValueError) as error:
            print(
                f"continuation preparation failed: {type(error).__name__}: {error}", file=sys.stderr
            )
            return 2
        if args.prepare_only:
            print(run_dir)
            return 0
    try:
        launch = _launch(run_dir)
    except OSError as error:
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "launch_failed"
        manifest["failure_or_stop_reason"] = f"{type(error).__name__}: {error}"
        _write_json(manifest_path, manifest)
        print(f"continuation launch failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"run_dir": str(run_dir), **launch}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
