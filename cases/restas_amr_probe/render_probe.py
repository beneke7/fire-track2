#!/usr/bin/env python3
"""Render a cropped, correctly labelled alpha.water frame for the AMR probe."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pyvista as pv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--time", type=float, default=0.02)
    parser.add_argument("--alpha-threshold", type=float, default=0.65)
    parser.add_argument(
        "--camera-bounds", type=float, nargs=6, default=(-0.5, 0.5, -1.2, 1.2, 3.7, 4.0)
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output-label", default="amr")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    case = run_dir / "case"
    inputs = json.loads((run_dir / "inputs.json").read_text())
    numeric_times = sorted(
        (p for p in case.iterdir() if p.is_dir() and p.name.replace(".", "", 1).isdigit()),
        key=lambda p: float(p.name),
    )
    selected_dir = next(
        (p for p in numeric_times if math.isclose(float(p.name), args.time, abs_tol=1e-9)), None
    )
    if selected_dir is None:
        raise RuntimeError(f"No reconstructed fields at t={args.time:g} s")

    with tempfile.TemporaryDirectory(prefix="restas-amr-render-") as temporary:
        view = Path(temporary)
        for source in [case / "constant", case / "system", *numeric_times]:
            os.symlink(source, view / source.name, target_is_directory=True)
        marker = view / "probe.foam"
        marker.touch()
        reader = pv.OpenFOAMReader(str(marker))
        reader.enable_cell_array("alpha.water")
        reader.set_active_time_value(args.time)
        block = reader.read()
        mesh = block["internalMesh"]
        alpha = np.asarray(mesh.cell_data["alpha.water"], dtype=float)
        surface = mesh.threshold(
            (args.alpha_threshold, 1.0), scalars="alpha.water", preference="cell"
        )
        surface = surface.extract_surface(algorithm="dataset_surface").triangulate()
        if surface.n_cells == 0:
            raise RuntimeError("No alpha.water cells pass the render threshold")
        bounds = tuple(args.camera_bounds)
        actual = surface.bounds
        if any(
            actual[i] < bounds[i] - 1e-6 or actual[i + 1] > bounds[i + 1] + 1e-6 for i in (0, 2, 4)
        ):
            raise RuntimeError("camera bounds do not contain the thresholded water surface")

        output_dir = args.output_dir.resolve() if args.output_dir else run_dir / "figures"
        output_dir.mkdir(exist_ok=True)
        output = (
            output_dir
            / f"water-vof-{args.output_label}-t-{args.time:.3f}s-alpha-{args.alpha_threshold:.2f}-nearfield.png"
        )
        if output.exists():
            raise FileExistsError(output)
        plotter = pv.Plotter(off_screen=True, window_size=(2000, 1400))
        plotter.set_background("#f7f9fc")
        plotter.add_mesh(
            surface, color="#3f79a5", smooth_shading=True, ambient=0.5, diffuse=0.75, specular=0.0
        )
        if "background_air_velocity_m_s" in inputs:
            air = inputs["background_air_velocity_m_s"]
            flow_caption = (
                f"Horizontal four-slot · water +x {inputs['source_velocity_m_s_each'][0]:g} m/s · "
                f"air +y {air[1]:g} m/s"
            )
        else:
            crossflow = inputs.get("crossflow_m_s", [0.0, 0.0, 0.0])
            flow_caption = (
                f"Downward-release four-slot · crossflow "
                f"({crossflow[0]:g}, {crossflow[1]:g}, {crossflow[2]:g}) m/s"
            )
        plotter.add_text(
            f"Water VOF · alpha.water ≥ {args.alpha_threshold:.2f} · t = {args.time:.3f} s\n"
            f"{flow_caption} · exploratory mesh",
            position="upper_left",
            font_size=19,
            color="#182338",
        )
        plotter.add_axes(xlabel="x", ylabel="y", zlabel="z")
        center = np.asarray(
            [
                [(bounds[0] + bounds[1]) / 2],
                [(bounds[2] + bounds[3]) / 2],
                [(bounds[4] + bounds[5]) / 2],
            ]
        ).reshape(3)
        direction = np.asarray((-1.0, -1.0, -1.0), dtype=float)
        direction /= np.linalg.norm(direction)
        camera = plotter.camera
        camera.focal_point = tuple(center)
        camera.position = tuple(center - direction * 4.0)
        camera.up = (0.0, 0.0, 1.0)
        camera.parallel_projection = True
        camera.parallel_scale = max((bounds[3] - bounds[2]) * 0.64, (bounds[1] - bounds[0]) * 0.85)
        plotter.reset_camera_clipping_range()
        plotter.screenshot(str(output), transparent_background=False)
        plotter.close()

    record: dict[str, Any] = {
        "image": output.name,
        "run_id": run_dir.name,
        "output_label": args.output_label,
        "time_s": args.time,
        "field": "alpha.water",
        "threshold": args.alpha_threshold,
        "camera_bounds_m": list(bounds),
        "surface_bounds_m": [float(x) for x in actual],
        "thresholded_cell_count": int(np.count_nonzero(alpha >= args.alpha_threshold)),
        "label": flow_caption,
        "method": "PyVista OpenFOAMReader rendering of reconstructed computed field",
    }
    metadata = output.with_suffix(".json")
    metadata.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(f"Rendered {output}\nRender record {metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
