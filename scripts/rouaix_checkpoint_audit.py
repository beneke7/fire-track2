#!/usr/bin/env python3
"""Audit one exact checkpoint row from the Rouaix native seven-boundary history."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

RHO_WATER_KG_M3 = 997.6
TIME_TOL_S = 1e-10
# The checkpoint volume is recorded to 13 significant digits (0.5e-13 m^3
# half-unit); at rho=997.6 kg/m^3 this is 5.0e-11 kg. A 1e-8 kg bound gives
# roughly 200x margin for serialized decimal and binary floating-point rounding.
METADATA_RECONCILIATION_TOL_KG = 1e-8
PATCHES = (
    "gasInlet",
    "downstreamOutlet",
    "bottomOutlet",
    "aircraftWall",
    "spanwiseMinus",
    "spanwisePlus",
    "nozzle",
)
EXTERNAL_PATCHES = tuple(patch for patch in PATCHES if patch != "nozzle")


def checkpoint_metadata(declaration: dict[str, Any]) -> dict[str, float]:
    """Read either the legacy flat declaration or the current nested schema."""
    if "checkpoint" in declaration:
        checkpoint = declaration["checkpoint"]
        initial_inventory = float(checkpoint["native_water_volume_m3"])
        initial_time = float(checkpoint["time_s"])
    elif "checkpoint_inventory" in declaration:
        checkpoint = declaration["checkpoint_inventory"]
        initial_inventory = float(checkpoint["native_water_volume_m3"])
        initial_time = float(declaration["checkpoint_time_s"])
    else:
        raise ValueError("declaration has neither checkpoint nor checkpoint_inventory metadata")

    offsets = declaration["parent_ledger_offsets"]
    expected_inventory = float(offsets["checkpoint_inventory_volume_m3"])
    if not math.isclose(initial_inventory, expected_inventory, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("checkpoint inventory disagrees with parent_ledger_offsets")
    if offsets.get("offset_applied_once", True) is not True:
        raise ValueError("declaration does not mark parent offsets as applied once")

    prior_release = float(offsets["prior_release_volume_m3"])
    prior_escape = float(offsets["prior_escape_volume_m3"])
    parent_residual_kg = float(offsets["checkpoint_residual_expected_minus_observed_kg"])
    derived_parent_residual_kg = (
        prior_release - prior_escape - initial_inventory
    ) * RHO_WATER_KG_M3
    if abs(derived_parent_residual_kg - parent_residual_kg) > METADATA_RECONCILIATION_TOL_KG:
        raise ValueError("checkpoint inventory and carried parent ledger residual do not reconcile")
    if not all(
        math.isfinite(value)
        for value in (initial_inventory, initial_time, prior_release, prior_escape)
    ):
        raise ValueError("checkpoint metadata contains a non-finite value")
    if initial_inventory < 0.0 or prior_release < 0.0 or prior_escape < 0.0:
        raise ValueError("checkpoint volumes must be non-negative")

    return {
        "initial_inventory_m3": initial_inventory,
        "initial_time_s": initial_time,
        "prior_release_m3": prior_release,
        "prior_escape_m3": prior_escape,
        "parent_residual_kg": parent_residual_kg,
    }


def read_history(path: Path, *, through_time_s: float | None = None) -> list[tuple[float, float]]:
    """Read a full history or the closed prefix ending at one exact time.

    Live function objects append independently. Stop at the matched cutoff so
    writers' later, unequal or partial tails cannot invalidate a closed prefix.
    """
    rows: list[tuple[float, float]] = []
    found_cutoff = False
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            try:
                line = raw_line.decode("ascii")
            except UnicodeDecodeError as exc:
                raise ValueError(f"non-ASCII history row {line_number} in {path}") from exc
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = stripped.split()
            if len(fields) < 2:
                raise ValueError(f"malformed history row {line_number} in {path}")
            try:
                time_s, value = float(fields[0]), float(fields[1])
            except ValueError as exc:
                raise ValueError(f"non-numeric history row {line_number} in {path}") from exc
            if not math.isfinite(time_s) or not math.isfinite(value):
                raise ValueError(f"non-finite history row {line_number} in {path}")
            if rows and time_s <= rows[-1][0]:
                raise ValueError(f"history times are not strictly increasing in {path}")
            if through_time_s is not None and time_s > through_time_s + TIME_TOL_S:
                raise ValueError(
                    f"requested checkpoint time {through_time_s:.12g} is missing from {path}"
                )
            rows.append((time_s, value))
            if through_time_s is not None and abs(time_s - through_time_s) <= TIME_TOL_S:
                found_cutoff = True
                break
    if through_time_s is not None and not found_cutoff:
        raise ValueError(f"requested checkpoint time {through_time_s:.12g} is missing from {path}")
    return rows


def history_file(case: Path, object_name: str, filename: str) -> Path:
    candidates = sorted((case / "postProcessing" / object_name).glob(f"*/{filename}"))
    if len(candidates) != 1:
        raise ValueError(f"expected one {object_name}/{filename}, found {len(candidates)}")
    return candidates[0]


def select_exact_shared_checkpoint(
    histories: dict[str, list[tuple[float, float]]], through_time_s: float
) -> tuple[list[float], dict[str, list[float]], int]:
    """Require aligned histories and an exact requested row; never choose a nearby row."""
    if "waterInventory" not in histories:
        raise ValueError("waterInventory history is required")
    inventory_rows = histories["waterInventory"]
    if not inventory_rows:
        raise ValueError("waterInventory history is empty")
    canonical_times = [time_s for time_s, _ in inventory_rows]
    for name, rows in histories.items():
        if len(rows) != len(canonical_times):
            raise ValueError(
                f"row count differs for {name}: {len(rows)} vs {len(canonical_times)} inventory rows"
            )
        for index, ((time_s, _), expected_time_s) in enumerate(
            zip(rows, canonical_times, strict=True)
        ):
            if abs(time_s - expected_time_s) > TIME_TOL_S:
                raise ValueError(
                    f"time mismatch for {name} row {index}: {time_s:.12g} != {expected_time_s:.12g}"
                )
    matches = [
        index
        for index, time_s in enumerate(canonical_times)
        if abs(time_s - through_time_s) <= TIME_TOL_S
    ]
    if len(matches) != 1:
        raise ValueError(
            f"requested checkpoint time {through_time_s:.12g} is not an exact shared history row; "
            "no nearest-row clamping is performed"
        )
    last_index = matches[0]
    selected_times = canonical_times[: last_index + 1]
    selected_values = {
        name: [value for _, value in rows[: last_index + 1]] for name, rows in histories.items()
    }
    return selected_times, selected_values, len(canonical_times) - len(selected_times)


def calculate_closure(
    metadata: dict[str, float],
    incremental_source_m3: float,
    incremental_escape_m3: float,
    final_inventory_m3: float,
) -> dict[str, float]:
    initial_inventory = metadata["initial_inventory_m3"]
    prior_release = metadata["prior_release_m3"]
    prior_escape = metadata["prior_escape_m3"]
    incremental_residual_m3 = (
        incremental_source_m3 - incremental_escape_m3 - (final_inventory_m3 - initial_inventory)
    )
    cumulative_source_m3 = prior_release + incremental_source_m3
    cumulative_escape_m3 = prior_escape + incremental_escape_m3
    cumulative_residual_m3 = cumulative_source_m3 - cumulative_escape_m3 - final_inventory_m3
    incremental_residual_kg = incremental_residual_m3 * RHO_WATER_KG_M3
    cumulative_residual_kg = cumulative_residual_m3 * RHO_WATER_KG_M3
    identity_error_kg = (
        cumulative_residual_kg - metadata["parent_residual_kg"] - incremental_residual_kg
    )
    if abs(identity_error_kg) > 0.05:
        raise ValueError(
            "cumulative closure does not equal carried parent plus incremental closure"
        )
    return {
        "incremental_source_m3": incremental_source_m3,
        "incremental_escape_m3": incremental_escape_m3,
        "incremental_stored_change_m3": final_inventory_m3 - initial_inventory,
        "incremental_residual_m3": incremental_residual_m3,
        "incremental_residual_kg": incremental_residual_kg,
        "cumulative_source_m3": cumulative_source_m3,
        "cumulative_escape_m3": cumulative_escape_m3,
        "final_inventory_m3": final_inventory_m3,
        "cumulative_residual_m3": cumulative_residual_m3,
        "cumulative_residual_kg": cumulative_residual_kg,
        "cumulative_identity_error_kg": identity_error_kg,
    }


def audit(
    case: Path, declaration_path: Path, through_time_s: float, output_dir: Path
) -> dict[str, Any]:
    declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    metadata = checkpoint_metadata(declaration)
    if through_time_s <= metadata["initial_time_s"]:
        raise ValueError("requested checkpoint must be later than the declared restart checkpoint")

    inventory_path = history_file(case, "waterInventory", "volFieldValue.dat")
    histories = {"waterInventory": read_history(inventory_path, through_time_s=through_time_s)}
    flux_paths: dict[str, Path] = {}
    for patch in PATCHES:
        path = history_file(case, f"liquidFlux_{patch}", "surfaceFieldValue.dat")
        flux_paths[patch] = path
        histories[patch] = read_history(path, through_time_s=through_time_s)

    times, values, excluded_rows = select_exact_shared_checkpoint(histories, through_time_s)
    if not times or times[0] <= metadata["initial_time_s"]:
        raise ValueError("native history does not start strictly after the declared checkpoint")

    rows_out: list[dict[str, float]] = []
    patch_integrals = {patch: 0.0 for patch in PATCHES}
    step_residuals_kg: list[float] = []
    previous_time_s = metadata["initial_time_s"]
    previous_inventory_m3 = metadata["initial_inventory_m3"]
    for index, (time_s, inventory_m3) in enumerate(
        zip(times, values["waterInventory"], strict=True)
    ):
        dt_s = time_s - previous_time_s
        flux = {patch: values[patch][index] for patch in PATCHES}
        for patch in PATCHES:
            patch_integrals[patch] += flux[patch] * dt_s
        source_m3 = -flux["nozzle"] * dt_s
        escape_m3 = sum(flux[patch] for patch in EXTERNAL_PATCHES) * dt_s
        expected_change_m3 = source_m3 - escape_m3
        observed_change_m3 = inventory_m3 - previous_inventory_m3
        residual_kg = (expected_change_m3 - observed_change_m3) * RHO_WATER_KG_M3
        step_residuals_kg.append(residual_kg)
        rows_out.append(
            {
                "time_s": time_s,
                "dt_from_previous_s": dt_s,
                "native_water_volume_m3": inventory_m3,
                "incremental_source_m3": source_m3,
                "incremental_external_escape_m3": escape_m3,
                "incremental_expected_volume_change_m3": expected_change_m3,
                "observed_volume_change_m3": observed_change_m3,
                "step_residual_expected_minus_observed_kg": residual_kg,
                **{f"alphaPhi_{patch}_m3_s": flux[patch] for patch in PATCHES},
            }
        )
        previous_time_s, previous_inventory_m3 = time_s, inventory_m3

    final_inventory_m3 = values["waterInventory"][-1]
    incremental_source_m3 = -patch_integrals["nozzle"]
    incremental_escape_m3 = sum(patch_integrals[patch] for patch in EXTERNAL_PATCHES)
    closure = calculate_closure(
        metadata, incremental_source_m3, incremental_escape_m3, final_inventory_m3
    )
    incremental_fraction = (
        closure["incremental_residual_m3"] / incremental_source_m3
        if incremental_source_m3
        else None
    )
    cumulative_fraction = (
        closure["cumulative_residual_m3"] / closure["cumulative_source_m3"]
        if closure["cumulative_source_m3"]
        else None
    )
    max_abs_step_kg = max(abs(value) for value in step_residuals_kg)
    rms_step_kg = math.sqrt(
        sum(value * value for value in step_residuals_kg) / len(step_residuals_kg)
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    per_step_path = output_dir / "ledger-per-step.csv"
    with per_step_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows_out[0]))
        writer.writeheader()
        writer.writerows(rows_out)

    report: dict[str, Any] = {
        "schema_version": 1,
        "scope": "Exploratory native phase ledger; 0.1% checks are continuation guards, not E1 acceptance.",
        "run_id": declaration.get("run_id", "unknown"),
        "restart_checkpoint_time_s": metadata["initial_time_s"],
        "requested_checkpoint_time_s": through_time_s,
        "actual_final_time_s": times[-1],
        "rows": len(rows_out),
        "source_history_rows": len(histories["waterInventory"]),
        "post_checkpoint_rows_excluded": excluded_rows,
        "step_dt_s": {
            "min": min(row["dt_from_previous_s"] for row in rows_out),
            "max": max(row["dt_from_previous_s"] for row in rows_out),
            "mean": sum(row["dt_from_previous_s"] for row in rows_out) / len(rows_out),
        },
        "checkpoint": {
            "initial_native_water_volume_m3": metadata["initial_inventory_m3"],
            "initial_native_water_mass_kg": metadata["initial_inventory_m3"] * RHO_WATER_KG_M3,
            "carried_prior_release_volume_m3": metadata["prior_release_m3"],
            "carried_prior_escape_volume_m3": metadata["prior_escape_m3"],
            "carried_parent_residual_kg": metadata["parent_residual_kg"],
            "parent_residual_record_precision_tolerance_kg": METADATA_RECONCILIATION_TOL_KG,
            "parent_offsets_applied_once": True,
        },
        "incremental_ledger_from_checkpoint": {
            "initial_stored_volume_m3": metadata["initial_inventory_m3"],
            "final_stored_volume_m3": closure["final_inventory_m3"],
            "source_volume_m3": closure["incremental_source_m3"],
            "net_external_escape_volume_m3": closure["incremental_escape_m3"],
            "stored_change_volume_m3": closure["incremental_stored_change_m3"],
            "residual_expected_minus_observed_kg": closure["incremental_residual_kg"],
            "residual_fraction_of_incremental_source": incremental_fraction,
        },
        "cumulative_ledger_from_t0": {
            "prior_source_volume_m3": metadata["prior_release_m3"],
            "new_source_volume_m3": closure["incremental_source_m3"],
            "total_source_volume_m3": closure["cumulative_source_m3"],
            "total_source_mass_kg": closure["cumulative_source_m3"] * RHO_WATER_KG_M3,
            "prior_escape_volume_m3": metadata["prior_escape_m3"],
            "new_escape_volume_m3": closure["incremental_escape_m3"],
            "total_escape_volume_m3": closure["cumulative_escape_m3"],
            "total_escape_mass_kg": closure["cumulative_escape_m3"] * RHO_WATER_KG_M3,
            "final_stored_volume_m3": closure["final_inventory_m3"],
            "final_stored_mass_kg": closure["final_inventory_m3"] * RHO_WATER_KG_M3,
            "residual_expected_minus_observed_kg": closure["cumulative_residual_kg"],
            "residual_fraction_of_total_source": cumulative_fraction,
            "parent_plus_incremental_identity_error_kg": closure["cumulative_identity_error_kg"],
            "max_abs_per_step_residual_kg": max_abs_step_kg,
            "rms_per_step_residual_kg": rms_step_kg,
            "time_of_max_abs_per_step_residual_s": rows_out[
                max(range(len(rows_out)), key=lambda idx: abs(step_residuals_kg[idx]))
            ]["time_s"],
        },
        "boundary_fluxes": {
            "all_seven_native_alphaPhi_integrated_each_solver_step": list(PATCHES),
            "integrated_signed_flux_volume_m3": patch_integrals,
            "nozzle_split_as_source": True,
            "other_six_signed_sum_as_net_escape": list(EXTERNAL_PATCHES),
        },
        "continuation_guard_0p1_percent": {
            "incremental_pass": incremental_fraction is not None
            and abs(incremental_fraction) <= 0.001,
            "cumulative_pass": cumulative_fraction is not None
            and abs(cumulative_fraction) <= 0.001,
        },
        "artifacts": {
            "native_inventory_history": str(inventory_path),
            "native_flux_histories": {patch: str(path) for patch, path in flux_paths.items()},
            "per_step_csv": str(per_step_path),
        },
    }
    report_path = output_dir / "ledger-report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--declaration", required=True, type=Path)
    parser.add_argument("--through-time", required=True, type=float)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.case, args.declaration, args.through_time, args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
