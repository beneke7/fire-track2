#!/usr/bin/env python3
"""Write a sealed-gas quasistatic pressure-budget reference for corrected I4F geometry."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aerial_drop.i4f_pressure_budget import (  # noqa: E402
    SealedGasBudgetCase,
    pressure_budget,
)

GEOMETRY_PATH = Path(
    "results/summaries/i4f_20261025/transition-length-comparison/analysis/geometry-comparison.json"
)
BAR_PA = 100_000.0
TANK_WATER_M3 = 1.35
HEADSPACE_RATIOS = (0.20, 0.225, 0.25)
INITIAL_PRESSURES_BAR_ABS = (12.0, 13.0)
BACK_PRESSURE_BAR_ABS = 1.0
POLYTROPIC_EXPONENTS = (1.0, 1.4)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    """Print root-relative paths when possible and absolute paths otherwise."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _snapshot_inputs(output_dir: Path, geometry_path: Path) -> tuple[Path, dict[str, Any]]:
    """Capture exact source and geometry inputs before calculations begin."""
    from datetime import datetime, timezone

    capture_started = datetime.now(timezone.utc).isoformat()
    snapshot_dir = output_dir / "provenance" / "source-snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    inputs = {
        "module": (
            ROOT / "src/aerial_drop/i4f_pressure_budget.py",
            "src/aerial_drop/i4f_pressure_budget.py",
        ),
        "script": (Path(__file__).resolve(), "scripts/analyze_i4f_pressure_budget.py"),
        "tests": (ROOT / "tests/test_i4f_pressure_budget.py", "tests/test_i4f_pressure_budget.py"),
        "geometry_packet": (geometry_path.resolve(), "geometry/geometry-comparison.json"),
        "geometry_generator": (
            ROOT / "scripts/i4f_four_outlet_geometry/generate.py",
            "scripts/i4f_four_outlet_geometry/generate.py",
        ),
    }
    entries: dict[str, dict[str, Any]] = {}
    for role, (source, relative_copy) in inputs.items():
        if not source.is_file():
            raise FileNotFoundError(f"required {role} input does not exist: {source}")
        before_hash = _sha256(source)
        copy_path = snapshot_dir / relative_copy
        copy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copy_path)
        copied_hash = _sha256(copy_path)
        after_hash = _sha256(source)
        if before_hash != copied_hash or before_hash != after_hash:
            raise RuntimeError(f"input changed while snapshotting {role}: {source}")
        entries[role] = {
            "source_path": _display_path(source),
            "snapshot_path": _display_path(copy_path),
            "sha256": copied_hash,
            "size_bytes": copy_path.stat().st_size,
        }
    manifest = {
        "schema": "i4f_pressure_budget_source_snapshot_v1",
        "capture_started_utc": capture_started,
        "capture_completed_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Inputs were copied and hash-verified before calculations. Timestamps are actual capture times.",
        "files": entries,
    }
    manifest_path = snapshot_dir / "snapshot-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return snapshot_dir / "geometry/geometry-comparison.json", manifest


def _git_info() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = git("status", "--short") or ""
    return {
        "revision": git("rev-parse", "HEAD"),
        "dirty": bool(status),
        "status_short": status.splitlines(),
    }


def _mean_close_pair(values: list[float], *, name: str) -> float:
    if len(values) != 2 or not math.isclose(values[0], values[1], rel_tol=0.0, abs_tol=1e-10):
        raise ValueError(f"expected two matching per-tank {name} values, got {values}")
    return 0.5 * (values[0] + values[1])


def read_geometry_inputs(path: Path) -> tuple[dict[str, float], dict[str, float], dict[str, Any]]:
    source = json.loads(path.read_text(encoding="utf-8"))
    variants = source["geometry"]
    long = variants["train_1p0m_reference"]
    short = variants["train_0p8m"]
    for item in (long, short):
        if not math.isclose(
            item["tank_water_volume_assumed_m3_each"], TANK_WATER_M3, abs_tol=1e-12
        ):
            raise ValueError(
                "geometry packet tank-water value changed from declared pressure-budget input"
            )
        if not math.isclose(
            item["tank_headspace_volume_assumed_m3_each"],
            TANK_WATER_M3 * 0.225,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("geometry packet nominal headspace does not match 22.5% assumption")
    feed_long = _mean_close_pair(
        long["feed_volume_outside_tank_to_assumed_valve_plane_x2p25_m3_each"], name="wetted feed"
    )
    feed_short = _mean_close_pair(
        short["feed_volume_outside_tank_to_assumed_valve_plane_x2p25_m3_each"], name="wetted feed"
    )
    dry_long = _mean_close_pair(
        long["post_valve_air_line_volume_m3_each_initial_assumption"], name="long dry line"
    )
    dry_short = _mean_close_pair(
        short["post_valve_air_line_volume_m3_each_initial_assumption"], name="short dry line"
    )
    if not math.isclose(feed_long, feed_short, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("corrected transition variants should retain the same wetted feed volume")
    observed_delta = dry_long - dry_short
    expected_delta = 0.04133506221194305
    if not math.isclose(observed_delta, expected_delta, rel_tol=0.0, abs_tol=2e-12):
        raise ValueError(
            "corrected transition dry-line difference changed from the declared geometry"
        )
    common = {
        "tank_water_volume_m3_each": TANK_WATER_M3,
        "wetted_feed_volume_m3_each": feed_long,
        "headspace_ratio_nominal": 0.225,
        "headspace_volume_nominal_m3_each": TANK_WATER_M3 * 0.225,
        "dry_line_volume_1p0m_m3_each": dry_long,
        "dry_line_volume_0p8m_m3_each": dry_short,
        "dry_line_difference_1p0m_minus_0p8m_m3_each": observed_delta,
    }
    geometry = {
        "train_1p0m_reference": {
            "variant": "1.0 m transition and mouth",
            "dry_volume_m3": dry_long,
        },
        "train_0p8m": {"variant": "0.8 m transition and mouth", "dry_volume_m3": dry_short},
    }
    return common, geometry, source


def build_rows(
    common: dict[str, float], geometry: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pressure_bar in INITIAL_PRESSURES_BAR_ABS:
        for ratio in HEADSPACE_RATIOS:
            for exponent in POLYTROPIC_EXPONENTS:
                for geometry_key, geom in geometry.items():
                    case = SealedGasBudgetCase(
                        initial_pressure_abs_Pa=pressure_bar * BAR_PA,
                        back_pressure_abs_Pa=BACK_PRESSURE_BAR_ABS * BAR_PA,
                        tank_water_volume_m3=common["tank_water_volume_m3_each"],
                        headspace_ratio_to_tank_water=ratio,
                        wetted_feed_volume_m3=common["wetted_feed_volume_m3_each"],
                        initially_dry_downstream_volume_m3=geom["dry_volume_m3"],
                        polytropic_exponent=exponent,
                    )
                    outputs = pressure_budget(case)
                    rows.append(
                        {
                            "geometry_key": geometry_key,
                            "geometry_variant": geom["variant"],
                            "initial_pressure_bar_abs": pressure_bar,
                            "back_pressure_bar_abs": BACK_PRESSURE_BAR_ABS,
                            "polytropic_exponent_n": exponent,
                            "headspace_ratio_to_tank_water": ratio,
                            "tank_water_volume_m3": case.tank_water_volume_m3,
                            "tank_internal_capacity_assumed_m3": (
                                case.tank_water_volume_m3 + outputs["initial_headspace_volume_m3"]
                            ),
                            "initial_headspace_volume_m3": outputs["initial_headspace_volume_m3"],
                            "wetted_feed_volume_m3": case.wetted_feed_volume_m3,
                            "initially_dry_downstream_volume_m3": case.initially_dry_downstream_volume_m3,
                            "initial_liquid_inventory_m3": outputs["initial_liquid_inventory_m3"],
                            "pressure_after_full_bore_priming_bar_abs": (
                                outputs["pressure_after_full_bore_priming_abs_Pa"] / BAR_PA
                            ),
                            "priming_margin_over_back_pressure_bar": (
                                outputs["priming_pressure_margin_over_back_pressure_Pa"] / BAR_PA
                            ),
                            "raw_pressure_equilibrium_gas_displacement_m3": outputs[
                                "raw_pressure_equilibrium_gas_displacement_m3"
                            ],
                            "raw_pressure_equilibrium_nozzle_volume_after_priming_m3": outputs[
                                "raw_pressure_equilibrium_nozzle_volume_after_priming_m3"
                            ],
                            "inventory_capped_pressure_equilibrium_nozzle_volume_m3": outputs[
                                "inventory_capped_pressure_equilibrium_nozzle_volume_m3"
                            ],
                            "equilibrium_nozzle_volume_was_inventory_capped": outputs[
                                "equilibrium_nozzle_volume_was_inventory_capped"
                            ],
                            "pressure_after_hypothetical_all_initial_water_expulsion_bar_abs": (
                                outputs[
                                    "pressure_after_hypothetical_expulsion_of_all_initial_water_abs_Pa"
                                ]
                                / BAR_PA
                            ),
                            "tank_only_critical_headspace_ratio": outputs[
                                "tank_only_critical_headspace_ratio"
                            ],
                        }
                    )
    return rows


def write_plot(
    output_path: Path,
    common: dict[str, float],
    geometry: dict[str, dict[str, Any]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    p0 = INITIAL_PRESSURES_BAR_ABS[0] * BAR_PA
    pback = BACK_PRESSURE_BAR_ABS * BAR_PA
    ratio = 0.225
    vg0 = common["tank_water_volume_m3_each"] * ratio
    available = common["tank_water_volume_m3_each"] + common["wetted_feed_volume_m3_each"]
    delivered = np.linspace(0.0, available, 400)
    colors = {"train_1p0m_reference": "#176B87", "train_0p8m": "#C44735"}
    names = {"train_1p0m_reference": "1.0 m train", "train_0p8m": "0.8 m train"}

    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.4), sharey=True)
    for axis, exponent in zip(axes, POLYTROPIC_EXPONENTS, strict=True):
        for key, geom in geometry.items():
            dry = geom["dry_volume_m3"]
            pressure_bar = p0 * (vg0 / (vg0 + dry + delivered)) ** exponent / BAR_PA
            case = SealedGasBudgetCase(
                p0,
                pback,
                common["tank_water_volume_m3_each"],
                ratio,
                common["wetted_feed_volume_m3_each"],
                dry,
                exponent,
            )
            budget = pressure_budget(case)
            equilibrium_volume = budget["raw_pressure_equilibrium_nozzle_volume_after_priming_m3"]
            label = f"{names[key]} (dry line {dry:.3f} m³)"
            if 0.0 < equilibrium_volume < available:
                supported = delivered <= equilibrium_volume
                axis.plot(
                    delivered[supported],
                    pressure_bar[supported],
                    linewidth=2.4,
                    color=colors[key],
                    label=label,
                )
                axis.plot(
                    delivered[~supported],
                    pressure_bar[~supported],
                    linewidth=2.4,
                    color=colors[key],
                    linestyle="--",
                )
                axis.fill_between(
                    delivered[~supported],
                    pressure_bar[~supported],
                    BACK_PRESSURE_BAR_ABS,
                    color=colors[key],
                    alpha=0.12,
                    label="formula below back pressure; not pressure-supported"
                    if key == "train_1p0m_reference"
                    else None,
                )
                axis.vlines(
                    equilibrium_volume,
                    0.0,
                    BACK_PRESSURE_BAR_ABS,
                    color=colors[key],
                    alpha=0.6,
                    linestyle=":",
                )
                axis.scatter(
                    [equilibrium_volume], [BACK_PRESSURE_BAR_ABS], color=colors[key], s=35, zorder=4
                )
                axis.annotate(
                    f"{equilibrium_volume:.2f} m³",
                    (equilibrium_volume, BACK_PRESSURE_BAR_ABS),
                    xytext=(4, 9 if key == "train_1p0m_reference" else 23),
                    textcoords="offset points",
                    fontsize=8,
                    color=colors[key],
                )
            else:
                axis.plot(delivered, pressure_bar, linewidth=2.4, color=colors[key], label=label)
                if equilibrium_volume >= available:
                    axis.scatter([available], [pressure_bar[-1]], color=colors[key], s=25, zorder=4)
        axis.axhline(BACK_PRESSURE_BAR_ABS, color="#4C566A", linewidth=1.2, linestyle="--")
        axis.set_title(
            f"n = {exponent:g} ({'isothermal limit' if exponent == 1.0 else 'adiabatic-air reference'})"
        )
        axis.set_xlabel("Nozzle-delivered volume after full-bore priming (m³ per tank)")
        axis.set_xlim(0, available)
        axis.set_ylim(0.0, 6.0)
        axis.grid(True, alpha=0.22)
        axis.legend(frameon=False, fontsize=8, loc="upper right")
        if exponent == 1.0:
            raw = pressure_budget(
                SealedGasBudgetCase(
                    p0,
                    pback,
                    common["tank_water_volume_m3_each"],
                    ratio,
                    common["wetted_feed_volume_m3_each"],
                    geometry["train_1p0m_reference"]["dry_volume_m3"],
                    exponent,
                )
            )["raw_pressure_equilibrium_nozzle_volume_after_priming_m3"]
            axis.text(
                0.03,
                0.04,
                f"Raw equalization for 1.0 m: {raw:.2f} m³, beyond listed inventory",
                transform=axis.transAxes,
                fontsize=8,
                color="#333333",
                bbox={
                    "boxstyle": "round,pad=0.3",
                    "facecolor": "white",
                    "alpha": 0.9,
                    "edgecolor": "#BBBBBB",
                },
            )
    axes[0].set_ylabel("Headspace pressure reference (bar absolute)")
    fig.suptitle(
        "Sealed-gas quasistatic pressure budget — per tank\n"
        "12 bar abs initial, 1 bar abs back pressure, 22.5% headspace; line priming precedes output",
        fontsize=12,
    )
    fig.text(
        0.5,
        0.015,
        "Dashed/shaded portions are below 1 bar, hence not pressure-supported. No heat-transfer rate is modeled; this is not a transient emptying prediction.",
        ha="center",
        fontsize=8.5,
        color="#444444",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.88))
    fig.savefig(output_path, dpi=220, facecolor="white")
    plt.close(fig)


def generate(output_dir: Path, geometry_path: Path = ROOT / GEOMETRY_PATH) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    geometry_path = geometry_path.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing result bundle: {output_dir}")
    output_dir.mkdir(parents=True)
    snapshot_geometry_path, snapshot_manifest = _snapshot_inputs(output_dir, geometry_path)
    common, geometry, geometry_source = read_geometry_inputs(snapshot_geometry_path)
    rows = build_rows(common, geometry)
    csv_path = output_dir / "pressure-budget.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    plot_path = output_dir / "pressure-budget.png"
    write_plot(plot_path, common, geometry)
    manifest = {
        "schema": "i4f-sealed-gas-quasistatic-pressure-budget/v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "analytical engineering reference; not CFD and not a transient prediction",
        "git": _git_info(),
        "source_hashes": {
            "module": snapshot_manifest["files"]["module"]["sha256"],
            "script": snapshot_manifest["files"]["script"]["sha256"],
            "tests": snapshot_manifest["files"]["tests"]["sha256"],
            "corrected_geometry_packet": snapshot_manifest["files"]["geometry_packet"]["sha256"],
            "geometry_generator": geometry_source["source"]["generator_sha256"],
        },
        "source_snapshot_manifest": "provenance/source-snapshot/snapshot-manifest.json",
        "geometry_packet": _display_path(geometry_path),
        "headspace_sensitivity_interpretation": (
            "The headspace ratio is varied at fixed 1.35 m3 water volume per tank; therefore total assumed internal tank capacity also varies from 1.620 to 1.6875 m3 (nominal 1.65375 m3 at ratio 0.225)."
        ),
        "headspace_sensitivity_capacity_m3_each": [
            {
                "headspace_ratio_to_water": ratio,
                "headspace_volume_m3": TANK_WATER_M3 * ratio,
                "tank_internal_capacity_m3": TANK_WATER_M3 * (1.0 + ratio),
            }
            for ratio in HEADSPACE_RATIOS
        ],
        "cfd_pressure_relation": (
            "The 12 and 13 bar absolute starting pressures are analytical assumptions/sensitivities; this reference does not identify either value with a native CFD probe or tank average."
        ),
        "provisional_per_tank_inputs": common,
        "geometry_variants": geometry,
        "swept_conditions": {
            "initial_pressure_bar_abs": list(INITIAL_PRESSURES_BAR_ABS),
            "back_pressure_bar_abs": BACK_PRESSURE_BAR_ABS,
            "polytropic_exponent_n": list(POLYTROPIC_EXPONENTS),
            "headspace_ratio_to_tank_water": list(HEADSPACE_RATIOS),
            "rows": len(rows),
        },
        "nominal_pressure_budget_cases": [
            row
            for row in rows
            if row["initial_pressure_bar_abs"] == 12.0
            and row["headspace_ratio_to_tank_water"] == 0.225
        ],
        "equation": "P_abs = P0_abs * (Vg0 / (Vg0 + deltaVg))**n",
        "volume_accounting": {
            "after_full_bore_priming": "deltaVg = Vdry; nozzle-delivered volume is zero",
            "after_priming": "deltaVg = Vdry + Vnozzle_delivered",
            "available_liquid_cap_m3_per_tank": common["tank_water_volume_m3_each"]
            + common["wetted_feed_volume_m3_each"],
            "feed_handling": "Wetted feed contributes to available inventory. It is not added to dry-line priming displacement or counted twice.",
            "all_initial_water_expulsion_scenario": "deltaVg = Vdry + (Vtank_water + Vwetted_feed); assumes all listed initial liquid is eventually expelled and charged gas occupies the line as needed.",
            "tank_only_critical_ratio": "Vg0/Vtank_water = 1/((P0/Pback)**(1/n)-1); this excludes feed and downstream line volumes.",
        },
        "assumptions_and_limits": [
            "All pressures are absolute. Reported 12 bar convention is unresolved: 12 bar abs is the nominal assumption; 13 bar abs is a sensitivity representing a 12 bar gauge interpretation.",
            "Tank water 1.35 m3 per tank and corrected BREP feed/dry-line volumes are provisional geometry/inventory values, not native CFD inventories or measured volumes.",
            "Headspace ratio is varied from 20% to 25% of tank water at fixed 1.35 m3 water; this sensitivity therefore changes assumed total tank capacity. The 22.5% nominal case reproduces the geometry packet's 0.30375 m3 headspace and 1.65375 m3 capacity.",
            "n=1 is an isothermal limit and n=1.4 an adiabatic-air reference; neither is fitted to CFD or test data.",
            "The reference omits liquid inertia, gravity, valve and pipe losses, downstream-air compressibility, gas venting, dissolution/CO2, and foam. It does not model heat-transfer rates; n=1 is an isothermal limiting case and n=1.4 is an adiabatic-air reference.",
            "Pressure equalization is pressure-supported/quasistatic accounting, not a rigorous upper bound on delivered volume. Inertia and elevation head can sustain flow after tank gas pressure reaches back pressure.",
            "No valve opening history, flow rate, discharge duration, or actual complete-emptying prediction is produced.",
        ],
        "outputs": {
            "csv": {"path": csv_path.name, "sha256": _sha256(csv_path), "rows": len(rows)},
            "plot": {"path": plot_path.name, "sha256": _sha256(plot_path)},
        },
        "cases": rows,
    }
    json_path = output_dir / "pressure-budget.json"
    json_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, default=ROOT / GEOMETRY_PATH)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = ROOT / "results/runs" / f"i4f-pressure-budget-{stamp}"
    else:
        output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    manifest = generate(
        output_dir, args.geometry if args.geometry.is_absolute() else ROOT / args.geometry
    )
    print(f"result: {_display_path(output_dir)}")
    print(f"cases: {len(manifest['cases'])}")
    print(f"csv: {manifest['outputs']['csv']['sha256']}")
    print(f"plot: {manifest['outputs']['plot']['sha256']}")
    print(f"json: {_sha256(output_dir / 'pressure-budget.json')}")


if __name__ == "__main__":
    main()
