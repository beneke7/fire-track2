#!/usr/bin/env python3
"""Run the declared I4F reduced discharge baseline and its small sensitivity set."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aerial_drop.i4f_reduced import SimulationResult, simulate, summarize

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "experiments/i4f_baseline.json"
DEFAULT_OUTPUT_ROOT = ROOT / "results/runs"
N_VALUES = (1.0, 1.25, 1.4)
OPENING_TIMES_S = (0.1, 0.5, 1.0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_info() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=ROOT,
                capture_output=True,
                check=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = git("status", "--short") or ""
    return {
        "revision": git("rev-parse", "HEAD"),
        "dirty": bool(status),
        "status_short": status.splitlines(),
    }


def unique_run_dir(output_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("i4f-reduced-%Y%m%dT%H%M%S.%fZ")
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / stamp
    run_dir.mkdir(exist_ok=False)
    return run_dir


def case_id(n: float, opening_time_s: float, minimum_opening: float = 0.0) -> str:
    base = f"n_{n:.2f}_valve_{opening_time_s:.1f}s".replace(".", "p")
    if minimum_opening == 0.0:
        return base
    return f"{base}_minopen_{minimum_opening:.3f}".replace(".", "p")


def write_csv(path: Path, result: SimulationResult) -> None:
    names = list(result.samples)
    row_count = len(result.samples[names[0]])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        for index in range(row_count):
            writer.writerow({name: result.samples[name][index] for name in names})


def make_plots(
    run_dir: Path,
    baseline: SimulationResult,
    summaries: list[dict[str, Any]],
) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []

    generated: list[str] = []
    sample = baseline.samples
    time = sample["time_s"]
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 8.0), constrained_layout=True)
    axes = axes.ravel()
    axes[0].plot(time, sample["gas_pressure_abs_Pa"] / 1e6, label="Headspace absolute")
    axes[0].axhline(
        baseline.parameters.ambient_pressure_Pa / 1e6,
        color="0.35",
        linestyle="--",
        label="Ambient absolute",
    )
    axes[0].set_ylabel("Pressure (MPa abs)")
    axes[0].legend(loc="best")
    axes[0].grid(True, alpha=0.25)

    axes[1].plot(time, sample["tank_water_volume_m3"], label="Tank liquid")
    axes[1].plot(time, sample["gas_volume_m3"], label="Gas headspace")
    axes[1].axhline(
        baseline.stop_tank_water_volume_m3,
        color="0.35",
        linestyle="--",
        label="Gas-breakthrough stop inventory",
    )
    axes[1].set_ylabel("Tank inventory (m³)")
    axes[1].legend(loc="best")
    axes[1].grid(True, alpha=0.25)

    axes[2].plot(time, sample["flow_rate_m3_s"], color="tab:blue", label="Volume flow")
    axes[2].set_ylabel("Flow rate (m³/s)")
    axes[2].set_xlabel("Time from valve command (s)")
    axes[2].grid(True, alpha=0.25)
    mass_axis = axes[2].twinx()
    mass_axis.plot(
        time,
        sample["flow_rate_kg_s"],
        color="tab:orange",
        alpha=0.8,
        label="Mass flow",
    )
    mass_axis.set_ylabel("Mass flow (kg/s)")
    axes[2].legend(loc="upper left")
    mass_axis.legend(loc="upper right")

    axes[3].plot(
        time,
        sample["outlet_momentum_flux_N"] / 1000.0,
        color="tab:green",
        label="Outlet momentum flux",
    )
    axes[3].set_ylabel("Momentum flux (kN)")
    axes[3].set_xlabel("Time from valve command (s)")
    axes[3].grid(True, alpha=0.25)
    speed_axis = axes[3].twinx()
    speed_axis.plot(
        time,
        sample["nozzle_velocity_m_s"],
        color="tab:red",
        alpha=0.75,
        label="Nozzle mean speed",
    )
    speed_axis.set_ylabel("Nozzle mean speed (m/s)")
    axes[3].legend(loc="upper left")
    speed_axis.legend(loc="upper right")
    fig.suptitle("I4F reduced-model baseline — sealed air, n=1.25, 0.5 s opening")
    path = run_dir / "baseline_history.png"
    fig.savefig(path, dpi=170)
    plt.close(fig)
    generated.append(path.name)

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.0), constrained_layout=True)
    metric_specs = (
        ("discharge_duration_s", "Gas-breakthrough time (s)"),
        ("peak_flow_rate_m3_s", "Peak flow rate (m³/s)"),
        ("final_gas_pressure_abs_Pa", "Final absolute gas pressure (Pa)"),
        ("outlet_momentum_impulse_N_s", "Outlet momentum impulse (N·s)"),
    )
    for ax, (metric, label) in zip(axes.ravel(), metric_specs, strict=True):
        for opening in OPENING_TIMES_S:
            group = sorted(
                (
                    item
                    for item in summaries
                    if item["valve_opening_time_s"] == opening
                    and item["minimum_effective_opening"]
                    == baseline.parameters.valve_minimum_effective_opening
                ),
                key=lambda item: item["polytropic_n"],
            )
            ax.plot(
                [item["polytropic_n"] for item in group],
                [item[metric] for item in group],
                marker="o",
                label=f"opening {opening:g} s",
            )
        ax.set_xlabel("Polytropic exponent n (assumed)")
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.25)
    axes[0, 0].legend(loc="best")
    fig.suptitle("Small input sensitivity — provisional valve and gas assumptions")
    path = run_dir / "sensitivity.png"
    fig.savefig(path, dpi=170)
    plt.close(fig)
    generated.append(path.name)
    return generated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--time-step", type=float, default=1.0e-4, help="model time step in seconds"
    )
    parser.add_argument("--max-time", type=float, default=10.0, help="stop time in seconds")
    parser.add_argument(
        "--skip-refinement",
        action="store_true",
        help="skip the baseline half-time-step check",
    )
    opening = parser.add_mutually_exclusive_group()
    opening.add_argument(
        "--minimum-effective-opening",
        type=float,
        help="override the valve effective-area floor for this campaign (default from config, or 0)",
    )
    opening.add_argument(
        "--compare-minimum-openings",
        action="store_true",
        help="run matched campaigns at minimum effective opening 0 and 0.02",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wall_start = time.perf_counter()
    config_path = args.config.resolve()
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    if args.compare_minimum_openings:
        minimum_opening_values = (0.0, 0.02)
    else:
        minimum_opening_values = (
            float(
                config["valve"].get("minimum_effective_opening", 0.0)
                if args.minimum_effective_opening is None
                else args.minimum_effective_opening
            ),
        )
    run_dir = unique_run_dir(args.output_root.resolve())
    (run_dir / "config_source.raw.json").write_bytes(config_bytes)
    (run_dir / "config_source.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source_snapshot_hashes: dict[str, str] = {}
    for relative_path in (
        "src/aerial_drop/i4f_reduced.py",
        "scripts/run_i4f_reduced.py",
    ):
        source_bytes = (ROOT / relative_path).read_bytes()
        source_snapshot_hashes[relative_path] = sha256_bytes(source_bytes)
        snapshot_path = run_dir / "source_snapshot" / relative_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(source_bytes)

    summaries: list[dict[str, Any]] = []
    results: dict[str, SimulationResult] = {}
    for minimum_opening in minimum_opening_values:
        for n in N_VALUES:
            for opening in OPENING_TIMES_S:
                key = case_id(n, opening, minimum_opening)
                result = simulate(
                    config,
                    polytropic_n=n,
                    valve_opening_time_s=opening,
                    minimum_effective_opening=minimum_opening,
                    time_step_s=args.time_step,
                    max_time_s=args.max_time,
                )
                results[key] = result
                write_csv(run_dir / f"{key}.csv", result)
                summaries.append(
                    {
                        "case_id": key,
                        "polytropic_n": n,
                        "valve_opening_time_s": opening,
                        "minimum_effective_opening": minimum_opening,
                        "time_step_s": args.time_step,
                        **summarize(result),
                    }
                )

    baseline_floor = 0.0 if args.compare_minimum_openings else minimum_opening_values[0]
    baseline_key = case_id(1.25, 0.5, baseline_floor)
    baseline = results[baseline_key]
    refinement: dict[str, Any] | None = None
    if not args.skip_refinement:
        fine = simulate(
            config,
            polytropic_n=1.25,
            valve_opening_time_s=0.5,
            minimum_effective_opening=baseline_floor,
            time_step_s=args.time_step / 2.0,
            max_time_s=args.max_time,
        )
        coarse_summary = summarize(baseline)
        fine_summary = summarize(fine)
        keys = (
            "discharge_duration_s",
            "peak_flow_rate_m3_s",
            "final_gas_pressure_abs_Pa",
            "outlet_momentum_impulse_N_s",
        )
        refinement = {
            "coarse_time_step_s": args.time_step,
            "fine_time_step_s": args.time_step / 2.0,
            "coarse": coarse_summary,
            "fine": fine_summary,
            "relative_fine_minus_coarse": {
                key: (float(fine_summary[key]) - float(coarse_summary[key]))
                / max(abs(float(fine_summary[key])), 1e-30)
                for key in keys
            },
        }

    try:
        import matplotlib

        matplotlib_version: str | None = matplotlib.__version__
    except ImportError:
        matplotlib_version = None
    try:
        import h5py

        h5py_version: str | None = h5py.__version__
    except ImportError:
        h5py_version = None
    plots = make_plots(run_dir, baseline, summaries)
    metadata = {
        "experiment": config.get("experiment", "I4F reduced discharge"),
        "status": "exploratory reduced-model result; not CFD or hardware validation",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_config": str(config_path),
        "source_config_sha256": sha256_bytes(config_bytes),
        "source_config_canonical_sha256": sha256_bytes(
            (json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        ),
        "code_sha256": source_snapshot_hashes,
        "source_snapshot_directory": "source_snapshot",
        "git": git_info(),
        "python_command": [
            str(Path(sys.executable).resolve()),
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
        "launcher_command": [
            str(Path(sys.executable).resolve()),
            "scripts/run_local.py",
            "--threads",
            str(int(os.environ.get("OMP_NUM_THREADS", "1"))),
            "--",
        ],
        "solver": "NumPy-only implicit midpoint liquid-column model",
        "solver_version": "aerial_drop.i4f_reduced in repository revision recorded above",
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "matplotlib_version": matplotlib_version,
        "h5py_version": h5py_version,
        "hdf5_output_written": False,
        "cpu_threads_requested": int(os.environ.get("OMP_NUM_THREADS", "1")),
        "elapsed_wall_s": time.perf_counter() - wall_start,
        "gpu_used": False,
        "random_seed": "not applicable; deterministic calculation",
        "time_step_s": args.time_step,
        "maximum_model_time_s": args.max_time,
        "stop_condition": "first liquid-interface contact with upper edge of tank connection",
        "sensitivity": {
            "polytropic_exponents": list(N_VALUES),
            "valve_opening_times_s": list(OPENING_TIMES_S),
            "minimum_effective_opening_fractions": list(minimum_opening_values),
        },
        "baseline_case_id": baseline_key,
        "time_step_refinement": refinement,
        "plots": plots,
        "cases": summaries,
        "limitations": [
            "valve uses the assigned provisional Cd=0.7 effective-orifice surrogate, not a resolved butterfly or a sourced K(theta) curve",
            "minimum effective opening is an explicit area-fraction floor; an omitted config value falls back to zero, the shared baseline currently sets 0.02, and the optional 0 vs 0.02 comparison does not resolve or validate a butterfly disk",
            "pipe entrance K=0.5 is a square-edged culvert analogy, not measured I4F data; the 0.3-0.7 range is approximate and not run as a sweep",
            "transition local loss K=0.2 is provisional; transition area is a linear-area polar loft",
            "sealed air uses an ideal-gas polytropic pressure law and no gas-water mixing or heat-transfer field",
            "liquid uses water properties only; the actual retardant and gas arrangement remain uncertain, and the user currently recalls mostly liquid before charging with possible oxygen above it then later CO2 pressurization",
            "line is initialized fully water-filled; its prefill is inventory and is not added a second time to discharged mass",
            "single-liquid equations stop at gas breakthrough and do not predict outlet-sheet spatial quality or external air interaction",
            "reported pipe-side transition-entry and lumped post-valve static pressures are unsteady one-dimensional diagnostics; the IAPWS 20 C vapor-pressure value is a screen only and does not model or establish cavitation",
            "a below-vapor or nonpositive single-liquid static-pressure history is reported separately from the tank-crown gas-breakthrough stop; integration is not truncated or presented as physically valid two-phase behavior after that screen",
        ],
    }
    (run_dir / "summary.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    lines = [
        "I4F reduced-model exploratory run",
        f"UTC: {metadata['created_utc']}",
        f"Config SHA-256: {metadata['source_config_sha256']}",
        f"Git revision: {metadata['git']['revision']} (dirty={metadata['git']['dirty']})",
        f"Time step: {args.time_step:g} s; minimum effective opening(s): {list(minimum_opening_values)}; single CPU thread; no GPU",
        "",
        "case_id | stop_s | discharged_kg | peak_Q_m3_s | final_p_abs_Pa",
    ]
    for item in summaries:
        lines.append(
            f"{item['case_id']} | {item['discharge_duration_s']:.9g} | "
            f"{item['external_discharged_mass_kg']:.9g} | "
            f"{item['peak_flow_rate_m3_s']:.9g} | {item['final_gas_pressure_abs_Pa']:.9g}"
        )
    lines.extend(
        [
            "",
            "Plots: " + (", ".join(plots) if plots else "not available (matplotlib absent)"),
            "HDF5: not written (h5py absent or not requested for these small histories).",
        ]
    )
    (run_dir / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote I4F reduced-model bundle: {run_dir}")
    print("case_id | stop_s | discharged_kg | peak_Q_m3_s | final_p_abs_Pa")
    for item in summaries:
        print(
            f"{item['case_id']} | {item['discharge_duration_s']:.9g} | "
            f"{item['external_discharged_mass_kg']:.9g} | "
            f"{item['peak_flow_rate_m3_s']:.9g} | {item['final_gas_pressure_abs_Pa']:.9g}"
        )
    print(
        f"Maximum baseline liquid mass-balance error: {baseline.max_mass_balance_error_m3:.3g} m^3"
    )
    print(f"Artifacts: {', '.join(plots) if plots else 'CSV and JSON only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
