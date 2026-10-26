from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path(__file__).resolve().parents[1]
CASE = BUNDLE / "case"
LOG = CASE / "log.cold-coupled"
EVENT_CSV = BUNDLE / "analysis/pressure-cycle-events.csv"
SUMMARY_JSON = BUNDLE / "analysis/pressure-cycle-diagnostic-summary.json"
PLOT = BUNDLE / "analysis/pressure-cycle-events.png"
CHECKPOINT_DIR: Path | None = None

KV_RE = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")
RECORD_RE = re.compile(r"^\[(\d+)\]\s+(I4F_PRESSURE_CYCLE_CELL|I4F_OUTER_DP_CELL)\s+(.*)$")
REQUIRED_FIELDS = (
    "T", "T.air", "T.water", "U", "alpha.water", "alphaPhi0.water", "alphat",
    "k", "nut", "omega", "p", "p_rgh", "phi", "rho",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(line: str) -> tuple[str, dict[str, str]] | None:
    match = RECORD_RE.match(line)
    if not match:
        return None
    values = dict(KV_RE.findall(match.group(3)))
    values["rank"] = match.group(1)
    c_match = re.search(r"\bC_m=\(([^)]*)\)", line)
    if c_match:
        coords = [float(x) for x in c_match.group(1).split()]
        if len(coords) == 3:
            values.update({"C_x_m": str(coords[0]), "C_y_m": str(coords[1]), "C_z_m": str(coords[2])})
    u_match = re.search(r"\bU_before_m_s=\(([^)]*)\)", line)
    if u_match:
        u = [float(x) for x in u_match.group(1).split()]
        if len(u) == 3:
            values.update({"U_before_x_m_s": str(u[0]), "U_before_y_m_s": str(u[1]), "U_before_z_m_s": str(u[2])})
    u_match = re.search(r"\bU_after_m_s=\(([^)]*)\)", line)
    if u_match:
        u = [float(x) for x in u_match.group(1).split()]
        if len(u) == 3:
            values.update({"U_after_x_m_s": str(u[0]), "U_after_y_m_s": str(u[1]), "U_after_z_m_s": str(u[2])})
    return match.group(2), values


def key(values: dict[str, str]) -> tuple[str, str, str, str]:
    return tuple(values[k] for k in ("time_s", "outer_iteration", "rank", "local_cell"))  # type: ignore[return-value]


def main() -> None:
    global CHECKPOINT_DIR
    launch = json.loads((BUNDLE / "launch-manifest.json").read_text())
    guardian = json.loads((BUNDLE / "guardian-status.json").read_text())
    branch = guardian["branches"]["fourmouth_coldstart"]
    assert guardian["status"] == "solver_terminal"
    assert branch["status"] == "normal_End_complete_native10_checkpoint"
    terminal = branch["latest_native10_checkpoint"]
    assert terminal["complete"]
    CHECKPOINT_DIR = Path(terminal["path"])

    dp_cells: dict[tuple[str, str, str, str], dict[str, str]] = {}
    observer: list[dict[str, str]] = []
    outer_count = 0
    with LOG.open(errors="replace") as stream:
        for line in stream:
            parsed = record(line)
            if parsed is None:
                continue
            kind, values = parsed
            if kind == "I4F_OUTER_DP_CELL":
                dp_cells[key(values)] = values
                outer_count += 1
            else:
                observer.append(values)
    observer.sort(key=lambda x: (float(x["time_s"]), int(x["outer_iteration"]), int(x["rank"]), int(x["local_cell"])))
    assert observer, "the observer window did not produce any selected-cell records"

    joined: list[dict[str, Any]] = []
    missing_coordinates = 0
    for event in observer:
        cell = dp_cells.get(key(event))
        if cell is None:
            missing_coordinates += 1
        row: dict[str, Any] = {
            "time_s": float(event["time_s"]),
            "time_index": int(event["time_index"]),
            "outer_iteration": int(event["outer_iteration"]),
            "rank": int(event["rank"]),
            "local_cell": int(event["local_cell"]),
            "stage": event.get("stage"),
            "abs_outer_dp_Pa": float(event["abs_outer_dp_Pa"]),
            "signed_outer_dp_Pa": float(event["signed_outer_dp_Pa"]),
            "p_before_Pa": float(event["p_before_Pa"]),
            "p_after_Pa": float(event["p_after_Pa"]),
            "alpha_before_outer": float(event["alpha_before_outer"]),
            "alpha_after_outer": float(event["alpha_after_outer"]),
            "alpha_before_predictor": float(event["alpha_before_predictor"]),
            "alpha_after_implicit_predictor": float(event["alpha_after_implicit_predictor"]),
            "alpha_before_MULES_corrector": float(event["alpha_before_MULES_corrector"]),
            "alpha_after_MULES_corrector": float(event["alpha_after_MULES_corrector"]),
            "signed_delta_alpha_predictor": float(event["signed_delta_alpha_predictor"]),
            "signed_delta_alpha_MULES": float(event["signed_delta_alpha_MULES"]),
            "predictor_Sp_per_s": float(event["predictor_Sp_per_s"]),
            "predictor_Su_per_s": float(event["predictor_Su_per_s"]),
            "corrector_Sp_recomputed_per_s": float(event["corrector_Sp_recomputed_per_s"]),
            "corrector_Su_recomputed_per_s": float(event["corrector_Su_recomputed_per_s"]),
            "corrector_Sp_used_by_MULES_per_s": float(event["corrector_Sp_used_by_MULES_per_s"]),
            "predictor_dgdt_per_s": float(event["predictor_dgdt_per_s"]),
            "predictor_divU_per_s": float(event["predictor_divU_per_s"]),
            "water_postEOS_phase_continuity_kg_m3_s": float(event["water_postEOS_phase_continuity_kg_m3_s"]),
            "gas_postEOS_phase_continuity_kg_m3_s": float(event["gas_postEOS_phase_continuity_kg_m3_s"]),
            "alpha_corrector_index": int(event.get("alpha_corrector_index", "-1")),
            "phase_class_by_alpha_before": (
                "gas_dominant" if float(event["alpha_before_outer"]) <= 0.01
                else "water_core" if float(event["alpha_before_outer"]) >= 0.99
                else "mixed"
            ),
            "observer_cell_zone_query": event.get("valve_cellZone"),
            "in_valve_source_band": int(event.get("in_valve_source_band", "-1")),
            "residual_definition": event.get("residual_definition"),
            "residual_scope": event.get("residual_scope"),
            "causality_claim": event.get("causality_claim"),
            "coordinate_frame": "native case Cartesian coordinates, metres",
            "pressure_stage": event.get("stage", "after_pressure_outer"),
            "pressure_unit": "Pa",
            "source_term_unit": "s^-1",
            "phase_continuity_residual_unit": "kg m^-3 s^-1",
            "raw_observer_line": " ".join(KV_RE.split("")) if False else None,
        }
        # Join exact same printed time/outer/rank/local-cell from the paired local pressure logger.
        if cell is not None:
            for out_name, key_name in (
                ("C_x_m", "C_x_m"), ("C_y_m", "C_y_m"), ("C_z_m", "C_z_m"),
                ("nativeV_m3", "nativeV_m3"), ("in_valve_source_band_dp", "in_valve_source_band"),
                ("T_before_K", "T_before_K"), ("T_after_K", "T_after_K"),
                ("rho_water_before_kg_m3", "rho1_before_kg_m3"), ("rho_water_after_kg_m3", "rho1_after_kg_m3"),
                ("rho_gas_before_kg_m3", "rho2_before_kg_m3"), ("rho_gas_after_kg_m3", "rho2_after_kg_m3"),
                ("U_before_x_m_s", "U_before_x_m_s"), ("U_before_y_m_s", "U_before_y_m_s"), ("U_before_z_m_s", "U_before_z_m_s"),
                ("U_after_x_m_s", "U_after_x_m_s"), ("U_after_y_m_s", "U_after_y_m_s"), ("U_after_z_m_s", "U_after_z_m_s"),
            ):
                value = cell.get(key_name)
                row[out_name] = float(value) if value is not None and out_name not in {"in_valve_source_band_dp"} else value
            row["dp_cell_signed_delta_Pa"] = float(cell["signed_delta_p_Pa"])
            row["dp_cell_signed_delta_alpha"] = float(cell["signed_delta_alpha"])
            row["observer_vs_DP_cell_signed_dp_difference_Pa"] = float(event["signed_outer_dp_Pa"]) - float(cell["signed_delta_p_Pa"])
        else:
            row.update({k: None for k in ("C_x_m", "C_y_m", "C_z_m", "nativeV_m3", "in_valve_source_band_dp", "T_before_K", "T_after_K", "rho_water_before_kg_m3", "rho_water_after_kg_m3", "rho_gas_before_kg_m3", "rho_gas_after_kg_m3", "dp_cell_signed_delta_Pa", "dp_cell_signed_delta_alpha", "observer_vs_DP_cell_signed_dp_difference_Pa")})
        joined.append(row)

    # Exact event identity join: each observer row must map to the same native selected cell.
    assert missing_coordinates == 0, f"selected observer rows missing paired local DP coordinates: {missing_coordinates}"
    assert max(abs(r["observer_vs_DP_cell_signed_dp_difference_Pa"]) for r in joined) < 0.03

    columns = list(joined[0])
    with EVENT_CSV.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(joined)

    by_cell: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    by_cell_time: dict[tuple[float, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in joined:
        by_cell[(row["rank"], row["local_cell"])].append(row)
        by_cell_time[(row["time_s"], row["rank"], row["local_cell"])].append(row)
    cell_summaries = []
    total_sign_reversals = 0
    for (rank, local_cell), rows in sorted(by_cell.items()):
        rows.sort(key=lambda r: (r["time_s"], r["outer_iteration"]))
        signs = [1 if r["signed_outer_dp_Pa"] > 0 else -1 if r["signed_outer_dp_Pa"] < 0 else 0 for r in rows]
        changes = sum(1 for a, b in zip(signs, signs[1:]) if a and b and a != b)
        total_sign_reversals += changes
        cell_summaries.append({
            "rank": rank,
            "local_cell": local_cell,
            "event_count": len(rows),
            "distinct_times": len({r["time_s"] for r in rows}),
            "first_time_s": rows[0]["time_s"],
            "last_time_s": rows[-1]["time_s"],
            "sign_reversals_in_recorded_events": changes,
            "signed_dp_min_Pa": min(r["signed_outer_dp_Pa"] for r in rows),
            "signed_dp_max_Pa": max(r["signed_outer_dp_Pa"] for r in rows),
            "alpha_before_min": min(r["alpha_before_outer"] for r in rows),
            "alpha_before_max": max(r["alpha_before_outer"] for r in rows),
            "coordinate_m": [rows[0][f"C_{axis}_m"] for axis in "xyz"],
            "in_valve_source_band": sorted({r["in_valve_source_band"] for r in rows}),
        })

    # Run the plot only after all exact record joins and checks passed.
    fig, ax = plt.subplots(figsize=(9.2, 5.0), dpi=160)
    scatter = ax.scatter(
        [r["time_s"] for r in joined],
        [r["signed_outer_dp_Pa"] / 1000.0 for r in joined],
        c=[r["alpha_before_outer"] for r in joined],
        cmap="viridis", vmin=0.0, vmax=1.0, s=18, alpha=0.85,
        linewidths=0,
    )
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.axhline(0.1, color="gray", linestyle="--", linewidth=0.8, label="+100 Pa trigger")
    ax.axhline(-0.1, color="gray", linestyle="--", linewidth=0.8, label="−100 Pa trigger")
    ax.axvline(0.478, color="tab:blue", linestyle=":", linewidth=1.0, label="observer window start")
    terminal_time = float(terminal["time_s"])
    ax.axvline(terminal_time, color="tab:red", linestyle="-.", linewidth=1.0, label="guard writeNow endpoint")
    ax.set_xlabel("Native simulation time (s)")
    ax.set_ylabel("Signed selected-cell outer pressure update (kPa)")
    ax.set_title("Pressure-cycle observer records during the full-window replay")
    ax.grid(True, alpha=0.22)
    ax.legend(loc="upper right", fontsize=8)
    cb = fig.colorbar(scatter, ax=ax)
    cb.set_label("alpha.water before pressure outer (dimensionless)")
    fig.text(0.01, 0.01, "Rows are selected per-pressure-outer updates with global |Δp|>100 Pa; not all cells or a global continuity measure.", fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(PLOT)
    plt.close(fig)

    signed = [r["signed_outer_dp_Pa"] for r in joined]
    alpha = [r["alpha_before_outer"] for r in joined]
    water_resid = [r["water_postEOS_phase_continuity_kg_m3_s"] for r in joined]
    gas_resid = [r["gas_postEOS_phase_continuity_kg_m3_s"] for r in joined]
    unique_times = sorted({r["time_s"] for r in joined})
    phase_counts = Counter(r["phase_class_by_alpha_before"] for r in joined)
    membership_counts = Counter(str(r["in_valve_source_band"]) for r in joined)
    health_rows = list(csv.DictReader((BUNDLE / "step_health.csv").open()))
    tail_health = health_rows[-6:]
    field_hashes = []
    for field in REQUIRED_FIELDS:
        p = CHECKPOINT_DIR / field
        field_hashes.append({"field": field, "size_bytes": p.stat().st_size, "sha256": sha(p)})
    time_path = CHECKPOINT_DIR / "uniform/time"
    field_hashes.append({"field": "uniform/time", "size_bytes": time_path.stat().st_size, "sha256": sha(time_path)})
    (BUNDLE / "provenance/terminal-native10.sha256").write_text("".join(f"{row['sha256']}  {CHECKPOINT_DIR.name}/{row['field']}\n" for row in field_hashes))

    summary = {
        "schema": "i4f-pressure-cycle-full-diagnostic-summary/v1",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Localized diagnostic of the pressure-update plateau after the active observer window; not validation and not a solver fix.",
        "launch": {
            "container_id": launch["container_id"],
            "container_started_at": launch["docker_started_at"],
            "container_finished_at": branch["docker_final_state"].get("FinishedAt"),
            "exit_code": branch["docker_final_state"].get("ExitCode"),
            "observer_binary_sha256": launch["binary_sha256"],
            "input_freeze_sha256": launch["input_freeze_sha256"],
            "case_static_tree_sha256": launch["static_case_tree_sha256"],
            "experiment_sha256": launch["experiment_record_sha256"],
            "guard_sha256": launch["guard_sha256"],
            "elapsed_wall_s": branch["wall_elapsed_s"],
            "completed_steps": branch["completed_steps"],
            "mpi_ranks": launch["ranks"],
            "cpu_quota_equivalent": 8,
            "pimple": launch["preflight"],
        },
        "termination": {
            "branch_status": branch["status"],
            "normal_End": branch["terminal_log"]["normal_End"],
            "solver_end_due_to_guard_writeNow": bool(branch.get("write_now_requested_utc")),
            "write_now_requested_utc": branch.get("write_now_requested_utc"),
            "write_now_reason": branch.get("write_now_reason"),
            "target_end_time_s": 0.483,
            "actual_complete_native_time_s": terminal_time,
            "observer_window_s": [0.478, 0.4835],
            "actual_observer_record_time_span_s": [min(unique_times), max(unique_times)],
            "raw_pressure_contact_count": branch["raw_pressure_contact_count"],
            "raw_clipped_liquid_mass_peak_kg": branch["maximum_clipped_liquid_mass_kg"],
            "persistent_final_floor_steps": branch["persistent_final_floor_steps"],
            "last_six_completed_step_health_rows": tail_health,
            "final_outer_delta": branch["final_outer_delta"],
            "penultimate_outer_delta": branch["penultimate_outer_delta"],
            "phase_ledger": {
                "cumulative_water_defect_kg": branch["cumulative_water_defect_kg"],
                "cumulative_gas_defect_kg": branch["cumulative_gas_defect_kg"],
                "water_inventory_kg": branch["previous_water_kg"],
                "gas_inventory_kg": branch["previous_gas_kg"],
                "note": "Cumulative campaign-ledger defects are carried forward; inventories are native monitored outputs.",
            },
            "complete_native10_checkpoint": terminal,
            "terminal_field_hashes": field_hashes,
            "controlDict_initial_sha256": branch["write_now_action"]["controlDict_before_sha256"],
            "controlDict_writeNow_sha256": branch["write_now_action"]["controlDict_after_sha256"],
        },
        "observer_events": {
            "record_count": len(joined),
            "outer_dp_cell_records_in_raw_log": outer_count,
            "all_observer_rows_joined_to_exact_same_time_outer_rank_cell_record": missing_coordinates == 0,
            "missing_coordinate_joins": missing_coordinates,
            "unique_rank_local_cells": len(by_cell),
            "unique_time_rank_local_cell_groups": len(by_cell_time),
            "unique_native_times": len(unique_times),
            "phase_class_counts_by_alpha_water_before_outer": dict(phase_counts),
            "in_valve_source_band_counts": dict(membership_counts),
            "all_selected_cells_outside_valve_source_band": all(r["in_valve_source_band"] == 0 for r in joined),
            "signed_dp_min_Pa": min(signed),
            "signed_dp_max_Pa": max(signed),
            "max_abs_dp_Pa": max(abs(x) for x in signed),
            "max_abs_dp_event": max(joined, key=lambda r: abs(r["signed_outer_dp_Pa"])),
            "alpha_before_outer_range": [min(alpha), max(alpha)],
            "predictor_Sp_per_s_range": [min(r["predictor_Sp_per_s"] for r in joined), max(r["predictor_Sp_per_s"] for r in joined)],
            "corrector_Sp_recomputed_per_s_range": [min(r["corrector_Sp_recomputed_per_s"] for r in joined), max(r["corrector_Sp_recomputed_per_s"] for r in joined)],
            "predictor_dgdt_per_s_range": [min(r["predictor_dgdt_per_s"] for r in joined), max(r["predictor_dgdt_per_s"] for r in joined)],
            "water_local_postEOS_phase_continuity_kg_m3_s_range": [min(water_resid), max(water_resid)],
            "gas_local_postEOS_phase_continuity_kg_m3_s_range": [min(gas_resid), max(gas_resid)],
            "within_cell_signed_dp_sign_reversals_across_recorded_events": total_sign_reversals,
            "most_observed_cells": sorted(cell_summaries, key=lambda x: x["event_count"], reverse=True)[:12],
            "unit_and_stage_notes": {
                "outer_dp": "Signed p_after - p_before across a PIMPLE pressure outer correction, Pa.",
                "alpha": "Dimensionless alpha.water sampled before/after implicit predictor and MULES corrector, with event cell selected by global outer pressure update.",
                "Sp_Su_dgdt_divU": "Local actual phase-equation coefficients/fields as emitted by the instrumented solver, per second; predictor and recomputed corrector labels are distinct.",
                "postEOS_residual": "Local discrete ddt(alpha*rho)+div(alphaPhi*interpolate(rho)) at the selected cell, kg m^-3 s^-1; not a global mass or continuity proof.",
                "location": "Native case Cartesian C coordinates, m; membership flag tests the actual valveSourceBand cellZone.",
                "selection": "Observer logs selected outer pressure-update cells when global max |Δp| > 100 Pa inside its configured window; this is not a full spatial field dump.",
                "causality": "Correlation only; no causal mechanism is proven by the selected-cell traces.",
            },
        },
        "reproducibility": {
            "raw_log_sha256": sha(LOG),
            "step_health_csv_sha256": sha(BUNDLE / "step_health.csv"),
            "events_csv_sha256": sha(EVENT_CSV),
            "plot_sha256": sha(PLOT),
            "binary_sha256": sha(BUNDLE / "bin/compressibleInterFoamFrozenAlphaSourceV2NoPout"),
            "launch_manifest_sha256": sha(BUNDLE / "launch-manifest.json"),
            "terminal_guard_status_sha256": sha(BUNDLE / "guardian-status.json"),
            "terminal_checkpoint_manifest_sha256": sha(BUNDLE / "provenance/terminal-native10.sha256"),
        },
        "limitations": [
            "Warm restart from 0.460047515286 s; not an uninterrupted cold-start trajectory.",
            "The replay ended at 0.48199621213 s after guard-requested writeNow, before the nominal 0.483 s target and before the observer window's configured 0.4835 s endpoint.",
            "Observer diagnostics are selected local cells and local reconstructed residuals, not global continuity/energy proof or causal attribution.",
            "No pressure-floor contacts occurred in this replay; the pressure-update guard still stopped it for the declared persistent update screen.",
            "This is a diagnostic replay only; it does not establish physical validity or a remedy for the underlying pressure-update cycle.",
        ],
        "output_files": {
            "events_csv": str(EVENT_CSV.relative_to(ROOT)),
            "diagnostic_plot": str(PLOT.relative_to(ROOT)),
            "terminal_native_manifest": str((BUNDLE / "provenance/terminal-native10.sha256").relative_to(ROOT)),
        },
    }
    SUMMARY_JSON.write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({
        "summary": str(SUMMARY_JSON.relative_to(ROOT)),
        "summary_sha256": sha(SUMMARY_JSON),
        "events_csv": str(EVENT_CSV.relative_to(ROOT)),
        "events_sha256": sha(EVENT_CSV),
        "event_count": len(joined),
        "unique_cells": len(by_cell),
        "unique_times": len(unique_times),
        "max_abs_dp_Pa": max(abs(x) for x in signed),
        "all_outside_valve_source_band": all(r["in_valve_source_band"] == 0 for r in joined),
        "plot": str(PLOT.relative_to(ROOT)),
        "plot_sha256": sha(PLOT),
    },indent=2))


if __name__ == "__main__":
    main()
