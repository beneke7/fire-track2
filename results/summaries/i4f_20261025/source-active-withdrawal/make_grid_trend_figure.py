#!/usr/bin/env python3
"""Build the compact resolution trend table and figure from included summaries."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
SUMMARY_FILES = ("analysis-summary.json", "refinement-analysis-summary.json")


def main() -> None:
    rows: list[dict[str, object]] = []
    for filename in SUMMARY_FILES:
        data = json.loads((HERE / filename).read_text(encoding="utf-8"))
        for arm in data["arms"]:
            rows.append(
                {
                    "grid_cells_x": int(arm["grid_cells_x"]),
                    "mode": str(arm["mode"]),
                    "comparison_time_s": float(arm["endpoint_time_s"]),
                    "gas_pressure_error_pct_vs_adiabat_at_native_volume": float(
                        arm["final_pressure_error_pct"]
                    ),
                    "gas_temperature_error_pct_vs_adiabat_at_native_volume": float(
                        arm["final_temperature_error_pct"]
                    ),
                    "water_balance_residual_m3": float(arm["water_balance_residual_m3"]),
                    "initial_water_volume_m3": float(arm["initial_water_volume_m3"]),
                    "water_balance_residual_fraction_initial_water": abs(
                        float(arm["water_balance_residual_m3"])
                    )
                    / float(arm["initial_water_volume_m3"]),
                    "gas_mass_drift_pct": float(arm["gas_mass_drift_pct"]),
                }
            )
    rows.sort(key=lambda row: (int(row["grid_cells_x"]), str(row["mode"])))
    with (HERE / "grid-trend.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    colors = {"sp-only": "#2878b5", "full-source": "#d1495b"}
    markers = {"sp-only": "o", "full-source": "s"}
    labels = {
        "sp-only": r"Cached $S_p$",
        "full-source": r"Cached $S_p + \nabla\!\cdot U$",
    }
    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.35), constrained_layout=True)
    panels = (
        ("gas_pressure_error_pct_vs_adiabat_at_native_volume", "Gas pressure error [%]", False),
        (
            "gas_temperature_error_pct_vs_adiabat_at_native_volume",
            "Gas temperature error [%]",
            False,
        ),
        (
            "water_balance_residual_fraction_initial_water",
            r"$|V_w(t)-V_{w,0}+\int Q_w\,dt|/V_{w,0}$ [–]",
            True,
        ),
    )
    for axis, (key, ylabel, log_scale) in zip(axes, panels, strict=True):
        for mode in ("sp-only", "full-source"):
            selected = [row for row in rows if row["mode"] == mode]
            axis.plot(
                [row["grid_cells_x"] for row in selected],
                [abs(float(row[key])) for row in selected],
                marker=markers[mode],
                color=colors[mode],
                linewidth=1.8,
                markersize=5.5,
                label=labels[mode],
            )
        axis.set_xlabel(r"Axial cells in channel, $N_x$ [–]")
        axis.set_ylabel(ylabel)
        axis.set_xticks(sorted({int(row["grid_cells_x"]) for row in rows}))
        axis.grid(True, which="both", alpha=0.28)
        if log_scale:
            axis.set_yscale("log")
    axes[0].set_title("Pressure")
    axes[1].set_title("Temperature")
    axes[2].set_title("Water-volume balance")
    axes[0].legend(frameon=False, fontsize=8, loc="best")
    fig.suptitle(
        "Sealed-channel source comparison at 0.4 s\n"
        "80 mL water / 20 mL air; rhoConst water, laminar flow, Pr = 10⁹",
        fontsize=11,
    )
    fig.savefig(HERE / "grid-trend.png", dpi=190)
    plt.close(fig)


if __name__ == "__main__":
    main()
