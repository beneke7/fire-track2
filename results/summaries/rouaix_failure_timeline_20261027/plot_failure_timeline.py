#!/usr/bin/env python3
"""Build a two-panel timeline from the hash-bound Rouaix 14650641 traces."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import lzma
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import ScalarFormatter


SCRIPT = Path(__file__).resolve()
SUMMARY_DIR = SCRIPT.parent
REPO_ROOT = SCRIPT.parents[3]
SOURCE_DIR = REPO_ROOT / "results/summaries/rouaix_long_stop_20261027"
TIMELINE_RUN_DIR = REPO_ROOT / "results/runs/rouaix-fast-local-20261027/timeline"
SOLVER_XZ = SOURCE_DIR / "solver.log.xz"
SPEED_XZ = SOURCE_DIR / "max-speed.csv.xz"
POSTMORTEM_PATH = SOURCE_DIR / "postmortem-analysis.json"
SOURCE_MANIFEST_PATH = SOURCE_DIR / "files.sha256.json"
METRICS_PATH = REPO_ROOT / "scripts/hpc_metrics.py"
PLOT_PATH = SUMMARY_DIR / "failure_timeline.png"
ANALYSIS_PATH = SUMMARY_DIR / "analysis.json"
OUTPUT_MANIFEST_PATH = SUMMARY_DIR / "files.sha256.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_close(actual: float, expected: float, tolerance: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise ValueError(f"{label}: got {actual:.14g}, expected {expected:.14g}")


def import_metrics_parser():
    spec = importlib.util.spec_from_file_location("hpc_metrics", METRICS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import metrics parser at {METRICS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_compressed_solver_log(
    source_path: Path, temporary_dir: Path
) -> tuple[Path, str]:
    digest = hashlib.sha256()
    fd, raw_name = tempfile.mkstemp(
        prefix="solver-log-", suffix=".log", dir=temporary_dir
    )
    temporary_path = Path(raw_name)
    try:
        with os.fdopen(fd, "wb") as output, lzma.open(source_path, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                output.write(chunk)
        return temporary_path, digest.hexdigest()
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def pair_courant_to_next_time(
    log_path: Path, metrics_parser: Any
) -> list[dict[str, float]]:
    """Keep the final pending bulk/interface values before each printed Time."""
    pending: dict[str, tuple[float, float]] = {}
    paired: list[dict[str, float]] = []
    with log_path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            courant = metrics_parser.COURANT_RE.match(line)
            if courant:
                kind = "interface" if courant.group(1) else "bulk"
                pending[kind] = (float(courant.group(2)), float(courant.group(3)))

            time_match = metrics_parser.TIME_RE.match(line)
            if time_match:
                if set(pending) != {"bulk", "interface"}:
                    raise ValueError(
                        f"missing bulk/interface Courant sample before Time={time_match.group(1)}"
                    )
                time_s = float(time_match.group(1))
                bulk_mean, bulk_max = pending["bulk"]
                interface_mean, interface_max = pending["interface"]
                paired.append(
                    {
                        "time_s": time_s,
                        "bulk_mean": bulk_mean,
                        "bulk_max": bulk_max,
                        "interface_mean": interface_mean,
                        "interface_max": interface_max,
                    }
                )
                pending.clear()
    if pending:
        raise ValueError("unpaired Courant record remains after final printed Time")
    return paired


def load_speed_series(source_path: Path) -> list[dict[str, float]]:
    with lzma.open(source_path, "rt", encoding="utf-8", newline="") as stream:
        rows = [
            {
                "time_s": float(row["time_s"]),
                "max_u_m_s": float(row["max_magnitude_U_m_s"]),
            }
            for row in csv.DictReader(stream)
        ]
    if not rows:
        raise ValueError("maximum-speed trace is empty")
    return rows


def row_at(rows: list[dict[str, float]], time_s: float) -> dict[str, float]:
    best = min(rows, key=lambda row: abs(row["time_s"] - time_s))
    if abs(best["time_s"] - time_s) > 1e-11:
        raise ValueError(f"no time-series row at requested event t={time_s}")
    return best


def main() -> None:
    TIMELINE_RUN_DIR.mkdir(parents=True, exist_ok=True)
    source_manifest = json.loads(SOURCE_MANIFEST_PATH.read_text())
    source_identities = source_manifest["files"]
    source_paths = {
        "solver_log_xz": SOLVER_XZ,
        "max_speed_csv_xz": SPEED_XZ,
        "postmortem_analysis": POSTMORTEM_PATH,
        "source_files_sha256_manifest": SOURCE_MANIFEST_PATH,
    }
    source_hashes: dict[str, dict[str, Any]] = {}
    for label, path in source_paths.items():
        actual_sha = file_sha256(path)
        expected = source_identities.get(path.name)
        if expected is not None:
            if actual_sha != expected["sha256"] or path.stat().st_size != expected["bytes"]:
                raise ValueError(f"source payload hash/size mismatch for {path}")
        source_hashes[label] = {
            "path": str(path.relative_to(REPO_ROOT)),
            "bytes": path.stat().st_size,
            "sha256": actual_sha,
        }
    source_hashes["hpc_metrics_parser"] = {
        "path": str(METRICS_PATH.relative_to(REPO_ROOT)),
        "bytes": METRICS_PATH.stat().st_size,
        "sha256": file_sha256(METRICS_PATH),
    }

    metrics_parser = import_metrics_parser()
    temporary_log, uncompressed_log_sha = load_compressed_solver_log(
        SOLVER_XZ, TIMELINE_RUN_DIR
    )
    try:
        parsed_log = metrics_parser.parse_openfoam_log(temporary_log)
        courant_rows = pair_courant_to_next_time(temporary_log, metrics_parser)
    finally:
        temporary_log.unlink(missing_ok=True)

    speed_rows = load_speed_series(SPEED_XZ)
    postmortem = json.loads(POSTMORTEM_PATH.read_text())
    onset = postmortem["onset_diagnostics"]
    guard = postmortem["outcome"]["guard"]
    terminal = postmortem["outcome"]["solver_terminal"]
    expected_courant = onset["courant_peaks"]

    if parsed_log["step_count"] != 2628 or len(speed_rows) != 2628:
        raise ValueError(
            f"expected 2628 steps and speed samples, got "
            f"{parsed_log['step_count']} and {len(speed_rows)}"
        )
    if len(courant_rows) != 2628:
        raise ValueError(f"expected 2628 aligned Courant samples, got {len(courant_rows)}")
    speed_times = np.asarray([row["time_s"] for row in speed_rows], dtype=float)
    speed_values = np.asarray([row["max_u_m_s"] for row in speed_rows], dtype=float)
    if not np.all(np.diff(speed_times) > 0):
        raise ValueError("maximum-speed times are not strictly increasing")
    if not np.all(np.diff([row["time_s"] for row in courant_rows]) > 0):
        raise ValueError("aligned Courant times are not strictly increasing")

    global_speed_index = int(np.argmax(speed_values))
    require_close(speed_values[global_speed_index], 1260.037732681, 1e-8, "max U")
    require_close(speed_times[global_speed_index], 0.2628, 1e-12, "max-U time")
    bulk_index = max(range(len(courant_rows)), key=lambda i: courant_rows[i]["bulk_max"])
    interface_index = max(
        range(len(courant_rows)), key=lambda i: courant_rows[i]["interface_max"]
    )
    bulk_peak = courant_rows[bulk_index]
    interface_peak = courant_rows[interface_index]
    require_close(bulk_peak["bulk_max"], expected_courant["bulk"]["max"], 1e-10, "bulk Co peak")
    require_close(
        bulk_peak["time_s"], expected_courant["bulk"]["time_s"], 1e-12, "bulk Co peak time"
    )
    require_close(
        interface_peak["interface_max"],
        expected_courant["interface"]["max"],
        1e-10,
        "interface Co peak",
    )
    require_close(
        interface_peak["time_s"],
        expected_courant["interface"]["time_s"],
        1e-12,
        "interface Co peak time",
    )
    require_close(
        parsed_log["courant_number"]["max"]["max"], expected_courant["bulk"]["max"], 1e-10,
        "hpc_metrics bulk Co summary",
    )
    require_close(
        parsed_log["interface_courant_number"]["max"]["max"],
        expected_courant["interface"]["max"],
        1e-10,
        "hpc_metrics interface Co summary",
    )

    isolated = onset["isolated_U_excursion"]
    ramp = onset["sustained_U_ramp"]
    trial_end_s = 0.05
    trial_end = row_at(speed_rows, trial_end_s)
    isolated_peak = row_at(speed_rows, isolated["time_s"])
    isolated_next = row_at(speed_rows, isolated["next_time_s"])
    ramp_start = row_at(speed_rows, ramp["start_marker_time_s"])
    guard_row = row_at(speed_rows, guard["guard_poll_trigger_time_s"])
    final_row = row_at(speed_rows, terminal["logged_time_s"])
    require_close(isolated_peak["max_u_m_s"], isolated["U_m_s"], 1e-8, "isolated U spike")
    require_close(isolated_next["max_u_m_s"], isolated["next_U_m_s"], 1e-8, "next U sample")
    require_close(ramp_start["max_u_m_s"], ramp["U_m_s"], 1e-8, "ramp start")
    require_close(guard_row["max_u_m_s"], guard["guard_poll_trigger_U_m_s"], 1e-8, "guard U")
    require_close(final_row["max_u_m_s"], terminal["logged_final_max_U_m_s"], 1e-8, "final U")
    first_trial_rows = [row for row in speed_rows if row["time_s"] <= trial_end_s + 1e-12]
    trial_peak = max(first_trial_rows, key=lambda row: row["max_u_m_s"])
    ramp_rows = [row for row in speed_rows if row["time_s"] >= ramp["start_marker_time_s"] - 1e-12]
    ramp_monotone = all(
        right["max_u_m_s"] >= left["max_u_m_s"] - 1e-10
        for left, right in zip(ramp_rows, ramp_rows[1:])
    )
    if not ramp_monotone or not ramp["monotone_from_0_2511_through_terminal"]:
        raise ValueError("sustained ramp rows do not reproduce the recorded monotone interval")

    event_specs = [
        (trial_end_s, "short trial end", "#718096", ":"),
        (isolated["time_s"], "isolated interior spike", "#805ad5", "--"),
        (ramp["start_marker_time_s"], "sustained corner growth", "#319795", "-."),
        (guard["guard_poll_trigger_time_s"], "guard trigger", "#dd6b20", "--"),
        (terminal["logged_time_s"], "final checkpoint", "#c53030", "-"),
    ]
    event_handles = [
        Line2D([0], [0], color=color, linestyle=style, linewidth=1.6,
               label=f"{time_s:.4f} s — {label}")
        for time_s, label, color, style in event_specs
    ]

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.facecolor": "white",
        }
    )
    fig, (ax_u, ax_co) = plt.subplots(
        2, 1, figsize=(12.2, 8.0), sharex=True, gridspec_kw={"height_ratios": [1.15, 1.0]}
    )
    colors = {label: color for _, label, color, _ in event_specs}
    for time_s, label, color, style in event_specs:
        for axis in (ax_u, ax_co):
            axis.axvline(time_s, color=color, linestyle=style, linewidth=0.9, alpha=0.72, zorder=1)

    ax_u.plot(
        speed_times, speed_values, color="#245a9b", linewidth=1.35,
        label="maximum |U| across cells", zorder=3,
    )
    ax_u.axhline(
        guard["threshold_max_abs_U_m_s"], color="#9b2c2c", linestyle="--",
        linewidth=1.1, label="configured operational guard: 1,000 m/s", zorder=2,
    )
    for row, event_time, key in (
        (trial_end, trial_end_s, "short trial end"),
        (isolated_peak, isolated["time_s"], "isolated interior spike"),
        (ramp_start, ramp["start_marker_time_s"], "sustained corner growth"),
        (guard_row, guard["guard_poll_trigger_time_s"], "guard trigger"),
        (final_row, terminal["logged_time_s"], "final checkpoint"),
    ):
        ax_u.scatter(
            [event_time], [row["max_u_m_s"]], s=28, color=colors[key],
            edgecolors="white", linewidths=0.6, zorder=5,
        )
    ax_u.set_yscale("log")
    ax_u.set_ylim(50, 1750)
    ax_u.set_yticks([50, 100, 200, 500, 1000, 1500])
    ax_u.yaxis.set_major_formatter(ScalarFormatter())
    ax_u.set_ylabel("Maximum speed |U| (m s⁻¹)")
    ax_u.set_title("Cellwise maximum speed", loc="left", pad=6)
    ax_u.grid(True, which="major", axis="both", color="#cbd5e0", linewidth=0.55, alpha=0.72)
    ax_u.grid(True, which="minor", axis="y", color="#e2e8f0", linewidth=0.35, alpha=0.55)
    ax_u.legend(loc="upper left", frameon=True, framealpha=0.94)
    ax_u.annotate(
        f"guard sample: {guard_row['max_u_m_s']:,.1f} m/s",
        xy=(guard_row["time_s"], guard_row["max_u_m_s"]),
        xycoords="data",
        xytext=(0.71, 0.72),
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "->", "color": "#dd6b20", "lw": 0.9},
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "#dd6b20", "alpha": 0.95},
        fontsize=8,
        zorder=7,
    )
    ax_u.annotate(
        f"final: {final_row['max_u_m_s']:,.1f} m/s",
        xy=(final_row["time_s"], final_row["max_u_m_s"]),
        xycoords="data",
        xytext=(0.72, 0.91),
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "->", "color": "#c53030", "lw": 0.9},
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "#c53030", "alpha": 0.95},
        fontsize=8,
        zorder=7,
    )

    courant_times = [row["time_s"] for row in courant_rows]
    bulk_max = [row["bulk_max"] for row in courant_rows]
    interface_max = [row["interface_max"] for row in courant_rows]
    ax_co.plot(courant_times, bulk_max, color="#2b6cb0", linewidth=1.05, label="bulk max Co", zorder=3)
    ax_co.plot(
        courant_times, interface_max, color="#2f855a", linewidth=1.05,
        label="interface max Co", zorder=3,
    )
    ax_co.axhline(
        1.0, color="#4a5568", linestyle="--", linewidth=1.0,
        label="Co = 1 reference (not a gate)", zorder=2,
    )
    ax_co.scatter(
        [bulk_peak["time_s"]], [bulk_peak["bulk_max"]], color="#2b6cb0",
        edgecolors="white", linewidths=0.6, s=34, zorder=5,
    )
    ax_co.scatter(
        [interface_peak["time_s"]], [interface_peak["interface_max"]], color="#2f855a",
        edgecolors="white", linewidths=0.6, s=34, zorder=5,
    )
    ax_co.set_ylim(0, 2.1)
    ax_co.set_ylabel("Maximum Courant number (dimensionless)")
    ax_co.set_xlabel("Simulation time (s)")
    ax_co.set_title("Bulk and interface Courant maxima", loc="left", pad=6)
    ax_co.grid(True, which="major", axis="both", color="#cbd5e0", linewidth=0.55, alpha=0.72)
    ax_co.legend(loc="upper left", ncol=1, frameon=True, framealpha=0.94)
    ax_co.annotate(
        f"interface peak {interface_peak['interface_max']:.3f} at {interface_peak['time_s']:.4f} s",
        xy=(interface_peak["time_s"], interface_peak["interface_max"]),
        xycoords="data",
        xytext=(0.34, 0.80),
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "->", "color": "#2f855a", "lw": 0.9},
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "#2f855a", "alpha": 0.95},
        fontsize=8,
        zorder=7,
    )
    ax_co.annotate(
        f"bulk peak {bulk_peak['bulk_max']:.3f} at {bulk_peak['time_s']:.4f} s",
        xy=(bulk_peak["time_s"], bulk_peak["bulk_max"]),
        xycoords="data",
        xytext=(0.73, 0.86),
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "->", "color": "#2b6cb0", "lw": 0.9},
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "#2b6cb0", "alpha": 0.95},
        fontsize=8,
        zorder=7,
    )

    ax_co.set_xlim(0, 0.268)
    fig.suptitle("Rouaix original 120-rank run: early-stop timeline", y=0.985, fontsize=13, weight="bold")
    fig.text(
        0.5, 0.952,
        "Partial exploratory run: reached 0.2628 s of a requested 5.0 s; vertical markers identify the recorded events.",
        ha="center", va="center", fontsize=9, color="#4a5568",
    )
    fig.legend(
        handles=event_handles, loc="upper center", bbox_to_anchor=(0.5, 0.918),
        ncol=3, frameon=False, fontsize=8, columnspacing=1.6, handlelength=2.4,
    )
    fig.text(
        0.5, 0.025,
        "U is the domain maximum, so its cell location may change over time. Courant samples are aligned to the next printed Time line.",
        ha="center", va="center", fontsize=8, color="#4a5568",
    )
    fig.subplots_adjust(left=0.105, right=0.975, top=0.82, bottom=0.105, hspace=0.2)
    fig.savefig(PLOT_PATH, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    analysis = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Bounded descriptive plot of the hash-bound 14650641 partial solver timeline.",
        "run": {
            "job_id": "14650641",
            "case_id": postmortem["case_id"],
            "status": postmortem["outcome"]["failure_classification"],
            "requested_horizon_s": postmortem["outcome"]["requested_horizon_s"],
            "reached_time_s": parsed_log["physical_time_reached_s"],
            "recorded_steps": parsed_log["step_count"],
            "plot_qualification": "Computed diagnostics from an exploratory partial run; no solver-validation gate or cause is inferred.",
        },
        "verified_series": {
            "maximum_speed": {
                "source": "max-speed.csv.xz",
                "rows": len(speed_rows),
                "units": "m/s",
                "maximum": float(speed_values[global_speed_index]),
                "maximum_time_s": float(speed_times[global_speed_index]),
                "maximum_through_0_05_s_m_s": float(trial_peak["max_u_m_s"]),
                "maximum_through_0_05_s_time_s": float(trial_peak["time_s"]),
                "isolated_spike": isolated_peak,
                "next_sample_after_spike": isolated_next,
                "sustained_ramp_start": ramp_start,
                "monotone_from_ramp_start": ramp_monotone,
                "guard_sample": guard_row,
                "final_sample": final_row,
                "operational_guard_threshold_m_s": float(guard["threshold_max_abs_U_m_s"]),
            },
            "courant": {
                "source": "solver.log.xz parsed with scripts/hpc_metrics.py",
                "alignment": "Bulk/interface values pair to the next printed Time line; repeated values before a timestamp resolve to the final pending record.",
                "rows_each_series": len(courant_rows),
                "units": "dimensionless",
                "bulk_max": {"time_s": bulk_peak["time_s"], "max": bulk_peak["bulk_max"]},
                "interface_max": {
                    "time_s": interface_peak["time_s"],
                    "max": interface_peak["interface_max"],
                },
                "reference_line": "Co = 1, shown for context only; not a gate.",
                "first_bulk_above_1": onset["bulk_courant_first_above_1"],
                "first_interface_above_1": onset["interface_courant_first_above_1"],
            },
        },
        "plot": {
            "path": str(PLOT_PATH.relative_to(REPO_ROOT)),
            "sha256": file_sha256(PLOT_PATH),
            "bytes": PLOT_PATH.stat().st_size,
            "format": "PNG",
            "dpi": 220,
            "matplotlib_version": matplotlib.__version__,
            "backend": matplotlib.get_backend(),
            "python_executable": sys.executable,
            "u_axis": "logarithmic",
            "event_markers_s": [
                {"time_s": trial_end_s, "label": "short trial end"},
                {"time_s": isolated["time_s"], "label": "isolated interior spike"},
                {"time_s": ramp["start_marker_time_s"], "label": "sustained corner growth"},
                {"time_s": guard["guard_poll_trigger_time_s"], "label": "operational U-guard trigger"},
                {"time_s": terminal["logged_time_s"], "label": "final checkpoint"},
            ],
        },
        "source_hashes": source_hashes,
        "temporary_input": {
            "compressed_solver_log_sha256": source_hashes["solver_log_xz"]["sha256"],
            "decompressed_solver_log_sha256": uncompressed_log_sha,
            "decompressed_copy": "Temporary file under ignored timeline run directory, removed after parsing.",
            "compressed_source_payloads_copied": False,
        },
    }
    ANALYSIS_PATH.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")

    output_names = ("README.md", SCRIPT.name, PLOT_PATH.name, ANALYSIS_PATH.name)
    output_manifest = {
        "schema_version": 1,
        "files": {
            name: {
                "bytes": (SUMMARY_DIR / name).stat().st_size,
                "sha256": file_sha256(SUMMARY_DIR / name),
            }
            for name in output_names
        },
        "source_hashes_revalidated": True,
        "time_series_checks": {
            "max_U_m_s": float(speed_values[global_speed_index]),
            "max_bulk_Co": float(bulk_peak["bulk_max"]),
            "max_interface_Co": float(interface_peak["interface_max"]),
        },
    }
    OUTPUT_MANIFEST_PATH.write_text(json.dumps(output_manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "plot": str(PLOT_PATH),
        "plot_sha256": analysis["plot"]["sha256"],
        "analysis": str(ANALYSIS_PATH),
        "max_U_m_s": analysis["verified_series"]["maximum_speed"]["maximum"],
        "bulk_Co_max": analysis["verified_series"]["courant"]["bulk_max"],
        "interface_Co_max": analysis["verified_series"]["courant"]["interface_max"],
        "parser_steps": parsed_log["step_count"],
        "paired_Co_rows": len(courant_rows),
        "matplotlib": matplotlib.__version__,
        "backend": matplotlib.get_backend(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
