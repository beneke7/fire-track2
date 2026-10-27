#!/usr/bin/env python3
"""Plot captured per-outer pressure, velocity and water-mass residuals."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def records(path: Path, prefix: str) -> list[dict[str, str]]:
    parsed = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith(prefix + " "):
            continue
        parsed.append(dict(re.findall(r"([A-Za-z0-9_]+)=([^\s]+)", line)))
    return parsed


def per_outer_eos(path: Path) -> list[dict[str, str]]:
    by_outer: dict[int, dict[str, str]] = {}
    for row in records(path, "I4F_ALPHA_MASS_BUDGET_EOS_V3"):
        outer = int(row["source_outer_iteration"])
        pressure_pass = int(row["pressure_pass"])
        if outer not in by_outer or pressure_pass > int(by_outer[outer]["pressure_pass"]):
            by_outer[outer] = row
    return [by_outer[key] for key in sorted(by_outer)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--default-log", type=Path, required=True)
    parser.add_argument("--trial-log", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional new PNG path; omit to write PNG bytes to stdout",
    )
    args = parser.parse_args()
    floors = (
        ("default 1e-4", args.default_log),
        ("trial 1e-5", args.trial_log),
    )
    outer_data = [records(path, "I4F_OUTER_STATE_DELTA") for _, path in floors]
    eos_data = [per_outer_eos(path) for _, path in floors]
    if any(len(rows) != 16 for rows in outer_data + eos_data):
        raise ValueError("expected 16 outer-iteration rows in each log")
    if any(
        [int(row["outer_iteration"]) for row in rows] != list(range(1, 17)) for rows in outer_data
    ):
        raise ValueError("outer iteration sequence is incomplete")

    fig, axes = plt.subplots(3, 1, figsize=(9.5, 8), sharex=True, constrained_layout=True)
    colors = ("#245b8f", "#c35b32")
    x = list(range(1, 17))
    series = (
        (axes[0], outer_data, "max_abs_dp_Pa", "max |Δp| (Pa)"),
        (axes[1], outer_data, "max_abs_dU_m_s", "max |ΔU| (m/s)"),
        (
            axes[2],
            eos_data,
            "Rmass_signed_kg_s",
            "signed whole-domain water mass residual (kg/s)",
        ),
    )
    for axis, data, key, ylabel in series:
        for (label, _), rows, color in zip(floors, data, colors, strict=True):
            y = [float(row[key]) for row in rows]
            axis.plot(x, y, marker="o", markersize=3.2, linewidth=1.4, label=label, color=color)
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.3)
        axis.legend(loc="best", frameon=False)
    axes[-1].set_xlabel("PIMPLE outer iteration")
    fig.suptitle(
        "One native timestep: alpha-source denominator-floor sensitivity\n"
        "same seed and controls; exploratory, not a trajectory or causal test",
        fontsize=11,
    )
    if args.output is None:
        fig.savefig(sys.stdout.buffer, format="png", dpi=150)
    else:
        with args.output.open("xb") as stream:
            fig.savefig(stream, format="png", dpi=150)
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
