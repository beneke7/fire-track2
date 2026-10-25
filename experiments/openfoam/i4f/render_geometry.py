#!/usr/bin/env python3
"""Render CPU-only mesh cutaways and cross-sections from a prepared I4F case."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from matplotlib.collections import PolyCollection


def triangles_as_polygons(slice_data: pv.PolyData, axes: tuple[int, int]) -> tuple[list[np.ndarray], np.ndarray]:
    faces = slice_data.faces.reshape((-1, 4))[:, 1:]
    pts = np.asarray(slice_data.points)
    polys = [pts[face][:, axes] for face in faces]
    alpha = np.asarray(slice_data.cell_data.get("alpha.water", np.zeros(len(faces))))
    return polys, alpha


def add_slice(ax, slice_data: pv.PolyData, axes: tuple[int, int], *,
              cmap: str = "Blues", linewidth: float = 0.12):
    polys, alpha = triangles_as_polygons(slice_data, axes)
    coll = PolyCollection(
        polys, array=alpha, cmap=cmap, edgecolors=(0.15, 0.20, 0.25, 0.30),
        linewidths=linewidth, clim=(0.0, 1.0), rasterized=True,
    )
    ax.add_collection(coll)
    ax.autoscale_view()
    return coll


def make_marker(case: Path) -> Path:
    marker = case / "i4f.foam"
    marker.touch(exist_ok=True)
    return marker


def render(run_dir: Path) -> tuple[Path, Path]:
    case = run_dir / "case"
    marker = make_marker(case)
    reader = pv.OpenFOAMReader(str(marker))
    reader.skip_zero_time = False
    reader.set_active_time_value(0.0)
    data = reader.read()
    mesh = data[0]
    concave_file = case / "VTK-concave/concaveCells_1/internal.vtu"
    concave_centres = (
        pv.read(concave_file).cell_centers().points
        if concave_file.is_file() else np.empty((0, 3))
    )

    # Full axial cutaways through the tank and discharge axis, using actual
    # snappyHexMesh cells and the initialized alpha.water field.
    side = mesh.slice(normal=(0, 1, 0), origin=(0, 0, 0)).triangulate()
    plan = mesh.slice(normal=(0, 0, 1), origin=(0, 0, 0.65)).triangulate()
    fig, axes = plt.subplots(2, 1, figsize=(15, 8.5), constrained_layout=True)
    side_coll = add_slice(axes[0], side, (0, 2), linewidth=0.10)
    if len(concave_centres):
        axes[0].scatter(concave_centres[:, 0], concave_centres[:, 2],
                        s=14, c="red", marker="x", linewidths=0.7,
                        label=f"{len(concave_centres)} checkMesh concave cells")
        axes[0].legend(loc="upper left", fontsize=8)
    axes[0].set_title("I4F hydraulic reference, y=0 mesh cut; blue indicates initial water")
    axes[0].set_xlabel("x discharge direction (m)")
    axes[0].set_ylabel("z upward (m)")
    axes[0].set_xlim(-0.05, 6.55)
    axes[0].set_ylim(-0.55, 2.05)
    axes[0].set_aspect("equal", adjustable="box")
    for x, label in ((2, "tank / pipe"), (3, "pipe / transition"), (4.5, "nozzle exit"), (6.5, "outlet")):
        axes[0].axvline(x, color="black", lw=0.8, ls="--")
        axes[0].text(x + 0.025, 1.9, label, rotation=90, va="top", fontsize=8)
    fig.colorbar(side_coll, ax=axes[0], label="water volume fraction")

    plan_coll = add_slice(axes[1], plan, (0, 1), linewidth=0.10)
    if len(concave_centres):
        axes[1].scatter(concave_centres[:, 0], concave_centres[:, 1],
                        s=14, c="red", marker="x", linewidths=0.7)
    axes[1].set_title("I4F horizontal-span cut, z=0.65 m")
    axes[1].set_xlabel("x discharge direction (m)")
    axes[1].set_ylabel("y horizontal span (m)")
    axes[1].set_xlim(-0.05, 6.55)
    axes[1].set_ylim(-1.55, 1.55)
    axes[1].set_aspect("equal", adjustable="box")
    for x in (2, 3, 4.5, 6.5):
        axes[1].axvline(x, color="black", lw=0.7, ls="--")
    fig.colorbar(plan_coll, ax=axes[1], label="water volume fraction")
    overview = run_dir / "geometry-mesh-overview.png"
    fig.savefig(overview, dpi=180)
    plt.close(fig)

    stations = [
        (1.05, "tank cross-section"),
        (2.53, "pipe"),
        (3.73, "transition"),
        (4.48, "rectangular nozzle, 0.02 m upstream"),
        (4.51, "external-air entrance"),
        (5.51, "external-air region"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    mappable = None
    for ax, (x, title) in zip(axes.flat, stations, strict=True):
        section = mesh.slice(normal=(1, 0, 0), origin=(x, 0, 0)).triangulate()
        mappable = add_slice(ax, section, (1, 2), linewidth=0.18)
        ax.set_title(f"x={x:.2f} m: {title}")
        ax.set_xlabel("y horizontal span (m)")
        ax.set_ylabel("z upward (m)")
        ax.set_aspect("equal", adjustable="box")
        if x < 4.5:
            ax.set_xlim(-0.62, 0.62)
            ax.set_ylim(0.45, 1.52)
        else:
            ax.set_xlim(-1.55, 1.55)
            ax.set_ylim(-0.55, 2.05)
    fig.colorbar(mappable, ax=list(axes.flat), shrink=0.78, label="water volume fraction")
    crosssections = run_dir / "geometry-mesh-crosssections.png"
    fig.savefig(crosssections, dpi=180)
    plt.close(fig)
    return overview, crosssections


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    a, b = render(args.run_dir.resolve(strict=True))
    print(a)
    print(b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
