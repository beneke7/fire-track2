#!/usr/bin/env python3
"""Render one actual OpenFOAM P0 interface surface with a reproducible 3D view."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _time_label(mesh: Any, input_path: Path, requested: float | None) -> float:
    if requested is not None:
        return requested
    if "TimeValue" in mesh.field_data:
        return float(mesh.field_data["TimeValue"][0])
    match = re.fullmatch(r"\d+(?:\.\d+)?", input_path.parent.name)
    if match:
        return float(match.group(0))
    raise ValueError("Cannot infer simulation time; provide --time explicitly")


def _render(input_path: Path, output_path: Path, requested_time: float | None) -> dict[str, Any]:
    try:
        import numpy as np
        import pyvista as pv
    except ImportError as error:
        raise RuntimeError(
            "Rendering dependencies are optional; run `uv sync --frozen --extra visualization`"
        ) from error

    mesh = pv.read(input_path)
    if not isinstance(mesh, pv.PolyData) or mesh.n_points == 0 or mesh.n_cells == 0:
        raise ValueError(f"{input_path} is not a non-empty VTK PolyData surface")
    if "U" not in mesh.cell_data:
        raise ValueError(f"{input_path} does not contain cell-centered velocity U")
    velocity = np.asarray(mesh.cell_data["U"])
    if velocity.shape != (mesh.n_cells, 3):
        raise ValueError(f"Unexpected U array shape {velocity.shape}; expected ({mesh.n_cells}, 3)")
    speed = np.linalg.norm(velocity, axis=1)
    if not np.isfinite(speed).all():
        raise ValueError("Velocity magnitude contains non-finite values")
    mesh.cell_data["speed_m_s"] = speed
    time_s = _time_label(mesh, input_path, requested_time)
    lower = float(speed.min())
    upper = float(speed.max())
    if upper <= lower:
        upper = lower + 1e-12

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plotter = pv.Plotter(off_screen=True, window_size=(1600, 1100))
    plotter.set_background("#f7f9fc")
    plotter.add_mesh(
        mesh,
        scalars="speed_m_s",
        cmap="viridis",
        clim=(lower, upper),
        smooth_shading=True,
        ambient=0.25,
        diffuse=0.8,
        specular=0.2,
        scalar_bar_args={
            "title": "Cell |U| on VOF surface (m/s)",
            "title_font_size": 22,
            "label_font_size": 18,
            "n_labels": 5,
            "fmt": "%.1f",
            "color": "#182338",
            "vertical": True,
            "position_x": 0.84,
            "position_y": 0.22,
            "height": 0.58,
            "width": 0.12,
        },
    )
    plotter.add_text(
        f"Computed water-air VOF interface · t = {time_s:.3f} s\n"
        "OpenFOAM interIsoFoam · provisional four-slot source · frame-specific speed scale",
        position="upper_left",
        font_size=15,
        color="#182338",
    )
    plotter.add_text(
        "P0 characterization only · x along-track · y cross-track · z upward · lengths in metres",
        position="lower_left",
        font_size=13,
        color="#182338",
    )
    plotter.add_axes(
        xlabel="x",
        ylabel="y",
        zlabel="z",
        line_width=2,
        labels_off=False,
    )
    plotter.view_isometric()
    plotter.camera.parallel_projection = True
    plotter.camera.zoom(1.45)
    plotter.show(screenshot=str(output_path), auto_close=True)

    result = {
        "input_vtp": str(input_path.resolve()),
        "input_sha256": _sha256(input_path),
        "output_png": str(output_path.resolve()),
        "output_sha256": _sha256(output_path),
        "rendered_utc": datetime.now(UTC).isoformat(),
        "simulation_time_s": time_s,
        "cell_count": int(mesh.n_cells),
        "point_count": int(mesh.n_points),
        "surface_speed_m_s": {"min": lower, "max": float(speed.max())},
        "color_scale": "frame-specific min/max of cell-centered |U|; not held constant across frames",
        "geometry_bounds_m": [float(value) for value in mesh.bounds],
        "pyvista_version": pv.__version__,
        "vtk_version": pv.vtk_version_info,
        "claim_limit": "Computed geometric VOF interface only; provisional source; not a validated Restas plume, resolved droplet field, or field prediction.",
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--time", type=float, help="simulation time in seconds; infer from VTP when omitted"
    )
    args = parser.parse_args()
    run_dir = args.run_dir
    if not run_dir.is_dir():
        parser.error(f"Run directory does not exist: {run_dir}")
    if args.time is None:
        matches = sorted(
            (run_dir / "case" / "postProcessing" / "liquidInterface").glob("*/freeSurface.vtp"),
            key=lambda path: float(path.parent.name),
        )
        if not matches:
            parser.error(f"No freeSurface.vtp files found under {run_dir}")
        input_path = matches[-1]
    else:
        time_dir = f"{args.time:.6f}"
        input_path = (
            run_dir / "case" / "postProcessing" / "liquidInterface" / time_dir / "freeSurface.vtp"
        )
    if not input_path.is_file():
        parser.error(f"No interface VTP exists at {input_path}")
    output_dir = run_dir / "figures"
    output_path = output_dir / f"interface-{input_path.parent.name.replace('.', 'p')}s.png"
    try:
        record = _render(input_path, output_path, args.time)
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    record_path = output_path.with_suffix(".json")
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Rendered {output_path}")
    print(f"Render record {record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
