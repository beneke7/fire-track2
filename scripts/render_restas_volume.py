#!/usr/bin/env python3
"""Render a matte, alpha-thresholded water volume from a reconstructed OpenFOAM time."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _numeric_time_dirs(case_dir: Path) -> list[Path]:
    found: list[Path] = []
    for path in case_dir.iterdir():
        if not path.is_dir():
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        if math.isfinite(value) and value >= 0.0:
            found.append(path)
    return sorted(found, key=lambda path: float(path.name))


def render(run_dir: Path, time_s: float | None, alpha_threshold: float) -> dict[str, Any]:
    try:
        import numpy as np
        import pyvista as pv
        from PIL import Image, ImageFilter
    except ImportError as error:
        raise RuntimeError(
            "Rendering dependencies are optional; run `uv sync --frozen --extra visualization`"
        ) from error

    run_dir = run_dir.resolve()
    case_dir = run_dir / "case"
    time_dirs = _numeric_time_dirs(case_dir)
    if not time_dirs:
        raise ValueError(f"No reconstructed OpenFOAM time directories found in {case_dir}")
    selected_time = float(time_dirs[-1].name) if time_s is None else time_s
    time_dir = next(
        (path for path in time_dirs if math.isclose(float(path.name), selected_time, abs_tol=1e-9)),
        None,
    )
    if time_dir is None:
        available = ", ".join(path.name for path in time_dirs)
        raise ValueError(f"Time {selected_time:g} is not reconstructed; available: {available}")
    alpha_path = time_dir / "alpha.water"
    if not alpha_path.is_file():
        raise ValueError(f"Missing reconstructed water fraction field: {alpha_path}")
    for required in (
        case_dir / "constant" / "polyMesh" / "points",
        case_dir / "system" / "controlDict",
    ):
        if not required.is_file():
            raise ValueError(f"Missing OpenFOAM case input: {required}")

    # VTK's OpenFOAM reader expects a .foam case marker. Keep that marker and
    # the reader's case view in a temporary directory so the run bundle remains
    # unchanged; its contents are symlinks to the saved case files.
    with tempfile.TemporaryDirectory(prefix="restas-volume-render-") as temporary:
        reader_case = Path(temporary)
        for source in [case_dir / "constant", case_dir / "system", *time_dirs]:
            os.symlink(source, reader_case / source.name, target_is_directory=True)
        marker = reader_case / "render.foam"
        marker.touch()
        reader = pv.OpenFOAMReader(str(marker))
        if not any(
            math.isclose(value, selected_time, abs_tol=1e-9) for value in reader.time_values
        ):
            raise ValueError(f"VTK did not expose reconstructed time {selected_time:g} s")
        reader.set_active_time_value(selected_time)
        reader.enable_cell_array("alpha.water")
        data = reader.read()
        try:
            volume_mesh = data["internalMesh"]
        except (KeyError, TypeError) as error:
            raise ValueError("OpenFOAM reader did not return the internal volume mesh") from error

        if "alpha.water" not in volume_mesh.cell_data:
            raise ValueError("Reconstructed volume mesh has no cell-centered alpha.water field")
        alpha = np.asarray(volume_mesh.cell_data["alpha.water"], dtype=np.float64)
        if alpha.shape != (volume_mesh.n_cells,) or not np.isfinite(alpha).all():
            raise ValueError("alpha.water is not one finite value per volume cell")
        if float(alpha.min()) < -1e-5 or float(alpha.max()) > 1.0 + 1e-5:
            raise ValueError("alpha.water lies outside [0, 1] beyond solver roundoff")

        volumes = np.asarray(
            volume_mesh.compute_cell_sizes(length=False, area=False, volume=True)["Volume"],
            dtype=np.float64,
        )
        water_volume = float(alpha @ volumes)
        threshold_mask = alpha >= alpha_threshold
        selected_volume = float(volumes[threshold_mask].sum())
        selected_mesh = volume_mesh.threshold(
            value=(alpha_threshold, 1.0), scalars="alpha.water", preference="cell"
        )
        surface = selected_mesh.extract_surface(algorithm="dataset_surface").triangulate()
        if surface.n_points == 0 or surface.n_cells == 0:
            raise ValueError(f"No water cells remain above alpha threshold {alpha_threshold:g}")
        geometry_bounds = [float(value) for value in surface.bounds]
        selected_cell_count = int(np.count_nonzero(threshold_mask))

        output_dir = run_dir / "figures"
        output_dir.mkdir(parents=True, exist_ok=True)
        time_label = time_dir.name.replace(".", "p")
        threshold_label = f"{alpha_threshold:.2f}".replace(".", "p")
        output_path = output_dir / f"water-volume-alpha-{threshold_label}-t-{time_label}s.png"
        if output_path.exists():
            raise FileExistsError(f"Refusing to overwrite existing render: {output_path}")

        hi_res_path = Path(temporary) / "supersampled.png"
        plotter = pv.Plotter(off_screen=True, window_size=(2400, 1650))
        plotter.set_background("#f7f9fc")
        plotter.add_mesh(
            surface,
            color="#3f79a5",
            smooth_shading=True,
            ambient=0.5,
            diffuse=0.75,
            specular=0.0,
            show_edges=False,
        )
        plotter.add_text(
            f"Water VOF · alpha.water ≥ {alpha_threshold:.2f} · t = {selected_time:.3f} s\n"
            "Still-air OpenFOAM case · exploratory mesh",
            position="upper_left",
            font_size=18,
            color="#182338",
        )
        plotter.add_axes(xlabel="x", ylabel="y", zlabel="z")
        plotter.view_isometric()
        plotter.camera.parallel_projection = True
        plotter.camera.zoom(1.4)
        plotter.show(screenshot=str(hi_res_path), auto_close=True)

        image = Image.open(hi_res_path).convert("RGB")
        image = image.resize((1600, 1100), Image.Resampling.LANCZOS)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.45))
        image.save(output_path)

    return {
        "run_id": json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")).get("run_id"),
        "simulation_time_s": selected_time,
        "alpha_threshold": alpha_threshold,
        "source_alpha_field": str(alpha_path),
        "source_alpha_field_sha256": _sha256(alpha_path),
        "mesh_points_sha256": _sha256(case_dir / "constant" / "polyMesh" / "points"),
        "rendered_utc": datetime.now(UTC).isoformat(),
        "volume_cell_count": int(volume_mesh.n_cells),
        "water_inventory_m3": water_volume,
        "thresholded_cell_count": selected_cell_count,
        "thresholded_cell_geometric_volume_m3": selected_volume,
        "surface_triangle_count": int(surface.n_cells),
        "surface_bounds_m": geometry_bounds,
        "output_png": str(output_path.resolve()),
        "output_sha256": _sha256(output_path),
        "render": {
            "color": "#3f79a5",
            "style": "matte blue cell-thresholded volume surface",
            "supersampled_window_px": [2400, 1650],
            "output_window_px": [1600, 1100],
            "downsampling": "Lanczos",
            "gaussian_blur_radius_px": 0.45,
        },
        "claim_limit": (
            "Exploratory VOF water-volume rendering from saved OpenFOAM cell fractions; "
            "not a validated breakup, droplet-size, deposition, or field-prediction result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--time", type=float, help="reconstructed simulation time in seconds")
    parser.add_argument("--alpha-threshold", type=float, default=0.65)
    args = parser.parse_args()
    if not 0.5 <= args.alpha_threshold <= 0.8:
        parser.error("--alpha-threshold must be between 0.5 and 0.8")
    try:
        record = render(args.run_dir, args.time, args.alpha_threshold)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    record_path = Path(record["output_png"]).with_suffix(".json")
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Rendered {record['output_png']}")
    print(f"Render record {record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
