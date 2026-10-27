#!/usr/bin/env python3
"""Plot saved I4F outlet-rim and FV-control-surface geometry only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D


def _closed_loop_from_segments(segments: list[list[list[float]]]) -> np.ndarray:
    adjacency: dict[tuple[float, ...], set[tuple[float, ...]]] = {}
    coordinates: dict[tuple[float, ...], np.ndarray] = {}
    for segment in segments:
        first = tuple(round(float(value), 12) for value in segment[0])
        second = tuple(round(float(value), 12) for value in segment[1])
        coordinates[first] = np.asarray(segment[0], dtype=np.float64)
        coordinates[second] = np.asarray(segment[1], dtype=np.float64)
        adjacency.setdefault(first, set()).add(second)
        adjacency.setdefault(second, set()).add(first)
    if not adjacency or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise ValueError("selected control-surface perimeter is not a single closed loop")

    start = min(adjacency)
    loop = [start]
    previous: tuple[float, ...] | None = None
    current = start
    for _ in range(len(adjacency)):
        following = next(point for point in adjacency[current] if point != previous)
        if following == start:
            break
        loop.append(following)
        previous, current = current, following
    if len(loop) != len(adjacency):
        raise ValueError("control-surface perimeter traversal did not use every point")
    return np.asarray([coordinates[point] for point in loop], dtype=np.float64)


def plot(evidence_path: Path, output_path: Path, mouth: str) -> None:
    data = json.loads(evidence_path.read_text(encoding="utf-8"))
    if data.get("schema") != "i4f-native-control-surface-geometry-packet/v1":
        raise ValueError("unsupported evidence schema")
    figure_data = data["figure_data"][mouth]
    cap_xyz = np.asarray(figure_data["branch_stl_cap_outline_xyz_m"], dtype=np.float64)
    hole_xyz = np.asarray(figure_data["ambient_annulus_hole_rim_xyz_m"], dtype=np.float64)
    fv_segments = np.asarray(
        figure_data["selected_fv_perimeter_edge_segments_xyz_m"], dtype=np.float64
    )
    fv_loop = _closed_loop_from_segments(figure_data["selected_fv_perimeter_edge_segments_xyz_m"])

    cap_closed = np.vstack((cap_xyz, cap_xyz[0]))
    hole_closed = np.vstack((hole_xyz, hole_xyz[0]))
    fv_closed = np.vstack((fv_loop, fv_loop[0]))
    cap_area = float(figure_data["branch_stl_cap_projected_area_x_m2"])
    fv_projected_area = abs(
        0.5 * np.sum(fv_closed[:-1, 1] * fv_closed[1:, 2] - fv_closed[1:, 1] * fv_closed[:-1, 2])
    )

    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.8))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.23, wspace=0.3)
    plan, side = axes
    plan.plot(hole_closed[:, 1], hole_closed[:, 2], color="#087f5b", linewidth=1.6)
    plan.plot(cap_closed[:, 1], cap_closed[:, 2], color="#222222", linestyle="--", linewidth=1.2)
    plan.add_collection(
        LineCollection(fv_segments[:, :, [1, 2]], color="#d97706", linewidth=0.85, alpha=0.9)
    )
    plan.set_xlim(
        float(fv_segments[:, :, 1].min()) - 0.035, float(fv_segments[:, :, 1].max()) + 0.035
    )
    plan.set_ylim(
        float(fv_segments[:, :, 2].min()) - 0.055, float(fv_segments[:, :, 2].max()) + 0.075
    )
    plan.set_aspect("equal", adjustable="box")
    plan.set_xlabel("y (m)")
    plan.set_ylabel("z (m)")
    plan.set_title(
        f"{mouth}: y–z projection\nSTL cap {cap_area:.3f} m²; FV perimeter {fv_projected_area:.3f} m²",
        fontsize=9,
    )

    side.add_collection(
        LineCollection(fv_segments[:, :, [0, 2]], color="#d97706", linewidth=0.85, alpha=0.9)
    )
    side.plot(hole_closed[:, 0], hole_closed[:, 2], color="#087f5b", linewidth=1.6)
    side.plot(
        [cap_xyz[:, 0].mean(), cap_xyz[:, 0].mean()],
        [cap_xyz[:, 2].min(), cap_xyz[:, 2].max()],
        color="#222222",
        linestyle="--",
        linewidth=1.2,
    )
    ambient_x = float(figure_data["ambient_annulus_plane_x_m"])
    cap_x = float(figure_data["branch_cap_plane_x_m"])
    side.axvline(ambient_x, color="#64748b", linestyle=":", linewidth=1.0)
    side.axvline(cap_x, color="#222222", linestyle="--", linewidth=0.8)
    side.set_xlim(
        min(float(hole_xyz[:, 0].min()), ambient_x) - 0.001,
        float(figure_data["selected_fv_surface_vertex_x_bounds_m"][1]) + 0.003,
    )
    side.set_ylim(float(cap_xyz[:, 2].min()) - 0.025, float(cap_xyz[:, 2].max()) + 0.06)
    side.set_xlabel("x (m)")
    side.set_ylabel("z (m)")
    side.set_title(f"{mouth}: x–z projection")
    dimension_z = float(cap_xyz[:, 2].max()) + 0.025
    side.annotate(
        "",
        xy=(float(figure_data["selected_fv_surface_vertex_x_bounds_m"][1]), dimension_z),
        xytext=(ambient_x, dimension_z),
        arrowprops={"arrowstyle": "<->", "color": "#d97706", "linewidth": 0.8},
    )
    side.text(
        0.5 * (ambient_x + float(figure_data["selected_fv_surface_vertex_x_bounds_m"][1])),
        dimension_z + 0.009,
        "FV face vertices reach x = {:.3f} m".format(
            figure_data["selected_fv_surface_vertex_x_bounds_m"][1]
        ),
        ha="center",
        fontsize=7.5,
        color="#8a4b00",
    )

    handles = [
        Line2D([0], [0], color="#222222", linestyle="--", label="branch STL cap outline"),
        Line2D([0], [0], color="#087f5b", label="ambientAnnulus true hole rim"),
        Line2D([0], [0], color="#d97706", label="selected FV control-surface perimeter"),
        Line2D([0], [0], color="#64748b", linestyle=":", label="ambientAnnulus plane x = 4.799 m"),
        Line2D([0], [0], color="#222222", linestyle="--", label="branch-cap plane x = 4.800 m"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.015),
        ncol=3,
        frameon=False,
        fontsize=8,
    )
    fig.suptitle(
        f"I4F saved geometry at t = {figure_data['time_s']:.12f} s; geometry only, no flow field",
        fontsize=10,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence", type=Path, required=True, help="saved native geometry evidence JSON"
    )
    parser.add_argument("--output", type=Path, required=True, help="new PNG output path")
    parser.add_argument(
        "--mouth", default="A_lower", choices=("A_lower", "A_upper", "B_lower", "B_upper")
    )
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing figure: {args.output}")
    plot(args.evidence, args.output, args.mouth)


if __name__ == "__main__":
    main()
