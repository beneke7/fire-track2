#!/usr/bin/env python3
"""Plot the public local outlet-mitigation CSV without reading CFD bundles.

Rebuild command:
  .venv/bin/python results/summaries/i4f_20261025/local-outlet-mitigation/plot_comparison.py
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
from matplotlib.ticker import FuncFormatter

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CSV = Path(__file__).resolve().parent / "comparison.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "comparison.png"
LABELS = {
    "B_native_Cf_control": "B · corrected outlet profile (1–197)",
    "D_outlet_extension": "D · extended outlet (1–3000)",
    "E_D_continuation": "E · D continuation (3001–9000)",
}
COLORS = {
    "B_native_Cf_control": "#b33a3a",
    "D_outlet_extension": "#28669a",
    "E_D_continuation": "#2d7d46",
}


def read_series(path: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            grouped[row["series"]].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: int(row["steady_iteration"]))
    return grouped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = read_series(args.csv)

    fig, axes = plt.subplots(2, 1, figsize=(10.5, 8.2), sharex=True, constrained_layout=True)
    for series in LABELS:
        rows = data.get(series, [])
        if not rows:
            continue
        x = np.asarray([int(row["steady_iteration"]) for row in rows])
        color = COLORS[series]
        axes[0].plot(
            x,
            [float(row["max_speed_m_s"]) for row in rows],
            color=color,
            lw=1.2,
            label=LABELS[series],
        )
        axes[1].plot(
            x,
            [float(row["p_abs_at_logged_min_p_cell_pa"]) for row in rows],
            color=color,
            lw=1.2,
            label=LABELS[series],
        )

    axes[0].axhline(
        200.0, color="#555555", ls="--", lw=0.9, label="declared runaway screen (200 m/s)"
    )
    axes[0].set_ylabel("Maximum cell speed (m/s)")
    axes[0].set_ylim(bottom=0)
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="upper left", frameon=True, fontsize=8)

    axes[1].axhline(0.0, color="#555555", lw=0.8)
    axes[1].set_yscale("symlog", linthresh=1000.0, linscale=0.8)
    axes[1].set_yticks([-1e6, -1e5, -1e4, -1e3, 0, 1e3, 1e4, 1e5])
    axes[1].yaxis.set_major_formatter(
        FuncFormatter(
            lambda value, _position: (
                "0" if value == 0 else f"{'−' if value < 0 else ''}{abs(value):.0e}"
            )
        )
    )
    axes[1].set_ylabel("pAbs at logged min(p) cell (Pa)\n(per-iteration diagnostic)")
    axes[1].set_xlabel("Steady SIMPLE iteration index (not physical seconds)")
    axes[1].grid(True, which="both", alpha=0.25)
    axes[1].legend(loc="lower right", frameon=True, fontsize=8)

    fig.suptitle("Single-phase wet-branch outlet-placement diagnostic", fontsize=13)
    fig.text(
        0.5,
        -0.015,
        "Q = 0.599812435 m³/s is a prescribed value derived from earlier CFD, not a measurement.\n"
        "D/E remain unsettled; the added stub also adds no-slip walls/cells and moves the pressure boundary.",
        ha="center",
        va="top",
        fontsize=8.5,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
