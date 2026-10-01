#!/usr/bin/env python3
"""Render a paired raw VOF diagnostic and interpolated alpha isosurface.

An optional, explicitly inferred whitewater-style density volume is generated
from deterministic samples with a normalized compact-support kernel. It is a
presentation layer, not a simulated phase or a contribution to water mass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WHITEWATER_COLORS = ["#b9d9e8", "#d7edf5", "#f5fbff", "#ffffff"]
WHITEWATER_OPACITIES = [0.0, 0.015, 0.08, 0.25, 0.55]


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


def _wendland_c2_kernel(radius_m: Any, smoothing_length_m: float) -> Any:
    """3-D Wendland C2 kernel with unit integral and support radius 2h."""
    import numpy as np

    if not math.isfinite(smoothing_length_m) or smoothing_length_m <= 0.0:
        raise ValueError("kernel smoothing length must be finite and positive")
    radius = np.asarray(radius_m, dtype=np.float64)
    if not np.isfinite(radius).all() or np.any(radius < 0.0):
        raise ValueError("kernel radii must be finite and nonnegative")
    q = radius / smoothing_length_m
    result = np.zeros_like(q)
    inside = q < 2.0
    result[inside] = (
        21.0
        / (16.0 * math.pi * smoothing_length_m**3)
        * (1.0 - 0.5 * q[inside]) ** 4
        * (1.0 + 2.0 * q[inside])
    )
    return result


def _secondary_whitewater_samples(
    alpha: Any,
    cell_centers_m: Any,
    *,
    seed: int,
    sample_count: int,
    cell_spacing_m: float,
    alpha_min: float = 0.05,
    alpha_max: float = 0.95,
) -> tuple[Any, dict[str, Any]]:
    """Seed a repeatable inferred detail cloud near mixed-alpha VOF cells."""
    import numpy as np

    values = np.asarray(alpha, dtype=np.float64)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("alpha must be a finite one-dimensional cell array")
    centers = np.asarray(cell_centers_m, dtype=np.float64)
    if centers.shape != (values.size, 3) or not np.isfinite(centers).all():
        raise ValueError("cell centers must be three finite coordinates per alpha value")
    if not 0.0 <= alpha_min < alpha_max <= 1.0:
        raise ValueError("overlay alpha bounds must be ordered within [0, 1]")
    if sample_count <= 0:
        raise ValueError("secondary sample count must be positive")
    if not math.isfinite(cell_spacing_m) or cell_spacing_m <= 0.0:
        raise ValueError("cell spacing must be finite and positive")
    candidates = np.flatnonzero((values >= alpha_min) & (values <= alpha_max))
    if candidates.size == 0:
        raise ValueError("no mixed-alpha cells are available for the optional detail volume")
    selected_count = int(sample_count)
    candidate_weights = values[candidates] * (1.0 - values[candidates])
    candidate_weights /= candidate_weights.sum()
    rng = np.random.default_rng(seed)
    samples_with_replacement = selected_count > candidates.size
    chosen = rng.choice(
        candidates,
        size=selected_count,
        replace=samples_with_replacement,
        p=candidate_weights,
    )
    jitter = rng.uniform(
        low=-0.5 * cell_spacing_m,
        high=0.5 * cell_spacing_m,
        size=(selected_count, 3),
    )
    samples = centers[chosen] + jitter
    record = {
        "enabled": True,
        "status": "inferred decorative detail; no bubble, foam, or droplet phase is modeled",
        "seed": int(seed),
        "secondary_sample_count": selected_count,
        "candidate_mixed_alpha_cell_count": int(candidates.size),
        "alpha_window": [float(alpha_min), float(alpha_max)],
        "selection": "weighted by alpha.water*(1-alpha.water), with replacement only when sample_count exceeds candidate cells",
        "position_jitter": "uniform within each selected cell using declared uniform mesh spacing",
        "cell_spacing_m": float(cell_spacing_m),
        "changes_alpha_or_mass": False,
    }
    record["selected_cell_indices_sha256"] = hashlib.sha256(
        chosen.astype("<i8").tobytes()
    ).hexdigest()
    record["sample_positions_sha256"] = hashlib.sha256(samples.astype("<f8").tobytes()).hexdigest()
    return samples, record


def _wendland_density_volume(
    samples_m: Any,
    bounds_m: tuple[float, float, float, float, float, float],
    *,
    smoothing_length_m: float,
    grid_spacing_m: float,
    pyvista_module: Any,
) -> tuple[Any, dict[str, Any]]:
    """Evaluate a sum of normalized Wendland kernels on a regular display grid."""
    import numpy as np

    samples = np.asarray(samples_m, dtype=np.float64)
    if samples.ndim != 2 or samples.shape[1] != 3 or not np.isfinite(samples).all():
        raise ValueError("samples must be a finite N by 3 coordinate array")
    if samples.shape[0] == 0:
        raise ValueError("density volume needs at least one secondary sample")
    if not math.isfinite(grid_spacing_m) or grid_spacing_m <= 0.0:
        raise ValueError("density grid spacing must be finite and positive")
    if not math.isfinite(smoothing_length_m) or smoothing_length_m <= 0.0:
        raise ValueError("kernel smoothing length must be finite and positive")

    limits = np.asarray(bounds_m, dtype=np.float64).reshape(3, 2)
    if not np.isfinite(limits).all() or np.any(limits[:, 1] <= limits[:, 0]):
        raise ValueError("density bounds must be finite increasing limits")
    origin = limits[:, 0]
    dimensions = np.ceil((limits[:, 1] - origin) / grid_spacing_m).astype(np.int64) + 1
    grid_shape = tuple(int(value) for value in dimensions)
    flat_density = np.zeros(int(np.prod(dimensions)), dtype=np.float32)

    reach = int(math.ceil(2.0 * smoothing_length_m / grid_spacing_m)) + 1
    axis = np.arange(-reach, reach + 1, dtype=np.int32)
    offsets = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1).reshape(-1, 3)
    nx, ny, _ = grid_shape
    flat_indices_per_axis = np.asarray((1, nx, nx * ny), dtype=np.int64)
    chunk_size = 256
    for start in range(0, samples.shape[0], chunk_size):
        chunk = samples[start : start + chunk_size]
        bases = np.floor((chunk - origin) / grid_spacing_m).astype(np.int32)
        indices = bases[:, None, :] + offsets[None, :, :]
        in_bounds = np.all((indices >= 0) & (indices < dimensions[None, None, :]), axis=2)
        coordinates = origin + indices * grid_spacing_m
        radii = np.linalg.norm(coordinates - chunk[:, None, :], axis=2)
        weights = _wendland_c2_kernel(radii, smoothing_length_m).astype(np.float32)
        keep = in_bounds & (weights > 0.0)
        linear_indices = np.sum(indices * flat_indices_per_axis, axis=2)
        np.add.at(flat_density, linear_indices[keep], weights[keep])

    positive_density = flat_density[flat_density > 0.0]
    if positive_density.size == 0:
        raise ValueError("kernel samples produced an empty whitewater density grid")
    display_reference = float(np.percentile(positive_density, 99.5))
    display_density = np.minimum(flat_density / display_reference, 1.0).astype(np.float32)
    grid = pyvista_module.ImageData(
        dimensions=grid_shape,
        spacing=(grid_spacing_m,) * 3,
        origin=tuple(float(value) for value in origin),
    )
    grid.point_data["whitewater_density_m-3"] = flat_density
    grid.point_data["whitewater_display_density"] = display_density
    record = {
        "representation": "regular-grid density volume from secondary samples",
        "kernel": "3-D Wendland C2: W(r,h)=21/(16*pi*h^3)*(1-r/(2h))^4*(1+2r/h), 0<=r<2h; zero otherwise",
        "kernel_normalization": "analytical 3-D integral equals one per unit-weight sample",
        "smoothing_length_h_m": float(smoothing_length_m),
        "kernel_support_radius_m": float(2.0 * smoothing_length_m),
        "grid_spacing_m": float(grid_spacing_m),
        "grid_dimensions_points": list(grid_shape),
        "grid_scalar_units": "m^-3 for unit-weight display samples; not a physical bubble number density",
        "display_normalization": "clip density divided by the positive-grid 99.5th percentile to [0,1]",
        "display_density_reference_m-3": display_reference,
        "peak_density_m-3": float(flat_density.max()),
        "changes_alpha_or_mass": False,
    }
    return grid, record


def _fixed_isometric_camera(
    plotter: Any,
    bounds: tuple[float, float, float, float, float, float],
    window_size: tuple[int, int],
) -> dict[str, Any]:
    import numpy as np

    limits = np.asarray(bounds, dtype=np.float64).reshape(3, 2)
    if not np.isfinite(limits).all() or np.any(limits[:, 1] <= limits[:, 0]):
        raise ValueError("camera bounds must be six finite, increasing physical limits")
    center = limits.mean(axis=1)
    corners = np.asarray(
        [(x, y, z) for x in limits[0] for y in limits[1] for z in limits[2]],
        dtype=np.float64,
    )
    direction = np.asarray((-1.0, -1.0, -1.0), dtype=np.float64) / math.sqrt(3.0)
    view_up = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    right = np.cross(direction, view_up)
    right /= np.linalg.norm(right)
    screen_up = np.cross(right, direction)
    relative = corners - center
    half_height = float(np.max(np.abs(relative @ screen_up)))
    half_width = float(np.max(np.abs(relative @ right)))
    aspect = window_size[0] / window_size[1]
    parallel_scale = 1.08 * max(half_height, half_width / aspect)
    distance = 2.0 * float(np.max(limits[:, 1] - limits[:, 0]))

    camera = plotter.camera
    camera.focal_point = tuple(center)
    camera.position = tuple(center - direction * distance)
    camera.up = tuple(view_up)
    camera.parallel_projection = True
    camera.parallel_scale = parallel_scale
    plotter.reset_camera_clipping_range()
    return {
        "mode": "fixed-isometric-parallel",
        "bounds_m": [float(value) for value in bounds],
        "focal_point_m": [float(value) for value in center],
        "view_direction": [float(value) for value in direction],
        "parallel_scale_m": parallel_scale,
    }


def _git_record(repository: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(repository), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}
    return {"revision": revision, "dirty": dirty}


def render(
    run_dir: Path,
    output_dir: Path,
    label: str,
    time_s: float | None = None,
    alpha_threshold: float = 0.65,
    isosurface_alpha: float = 0.50,
    whitewater: bool = False,
    whitewater_count: int = 20000,
    seed: int = 417,
    whitewater_smoothing_length_m: float | None = None,
    whitewater_grid_spacing_m: float | None = None,
) -> dict[str, Any]:
    """Render one paired still and a reproducibility record."""
    try:
        import numpy as np
        import pyvista as pv
    except ImportError as error:
        raise RuntimeError(
            "Rendering dependencies are optional; use the environment with the visualization extra"
        ) from error

    if not re.fullmatch(r"[A-Za-z0-9_-]+", label):
        raise ValueError("label may contain only letters, numbers, underscores, and hyphens")
    if not 0.5 <= alpha_threshold <= 0.8:
        raise ValueError("alpha threshold must be between 0.5 and 0.8")
    if not 0.0 < isosurface_alpha < 1.0:
        raise ValueError("isosurface alpha must be strictly between zero and one")
    if whitewater_count <= 0:
        raise ValueError("whitewater count must be positive")
    if seed < 0:
        raise ValueError("seed must be nonnegative")

    run_dir = run_dir.resolve()
    output_dir = output_dir.resolve()
    case_dir = run_dir / "case"
    time_dirs = _numeric_time_dirs(case_dir)
    if not time_dirs:
        raise ValueError(f"No reconstructed OpenFOAM time directories found in {case_dir}")
    selected_time = float(time_dirs[-1].name) if time_s is None else float(time_s)
    time_dir = next(
        (path for path in time_dirs if math.isclose(float(path.name), selected_time, abs_tol=1e-9)),
        None,
    )
    if time_dir is None:
        available = ", ".join(path.name for path in time_dirs)
        raise ValueError(f"Time {selected_time:g} is not reconstructed; available: {available}")
    alpha_path = time_dir / "alpha.water"
    mesh_points_path = case_dir / "constant" / "polyMesh" / "points"
    if not alpha_path.is_file():
        raise ValueError(f"Missing reconstructed water fraction field: {alpha_path}")
    for required in (mesh_points_path, case_dir / "system" / "controlDict"):
        if not required.is_file():
            raise ValueError(f"Missing OpenFOAM case input: {required}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"vof-presentation-{label}-t-{time_dir.name.replace('.', 'p')}s.png"
    if output_path.exists() or output_path.with_suffix(".json").exists():
        raise FileExistsError(f"Refusing to overwrite existing presentation render: {output_path}")

    # Limit VTK's CPU work for this lightweight postprocess while sharing the
    # workstation with active solver jobs.
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    try:
        import vtk

        vtk.vtkMultiThreader.SetGlobalMaximumNumberOfThreads(1)
    except (ImportError, AttributeError):
        pass

    with tempfile.TemporaryDirectory(prefix="vof-presentation-") as temporary:
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
        bounds = tuple(float(value) for value in volume_mesh.bounds)
        raw_mesh = volume_mesh.threshold(
            value=(alpha_threshold, 1.0), scalars="alpha.water", preference="cell"
        )
        raw_surface = raw_mesh.extract_surface(algorithm="dataset_surface").triangulate()
        if raw_surface.n_points == 0 or raw_surface.n_cells == 0:
            raise ValueError(f"No water cells remain above alpha threshold {alpha_threshold:g}")

        # This is a display-only interpolation. The original cell-centered
        # alpha array above remains the unmodified source for all diagnostics.
        point_mesh = volume_mesh.cell_data_to_point_data(pass_cell_data=True)
        point_alpha = np.asarray(point_mesh.point_data["alpha.water"], dtype=np.float64)
        iso_surface = point_mesh.contour(
            isosurfaces=[isosurface_alpha], scalars="alpha.water", method="contour"
        ).triangulate()
        if iso_surface.n_points == 0 or iso_surface.n_cells == 0:
            raise ValueError(f"No interpolated alpha.water={isosurface_alpha:g} isosurface found")

        inputs_path = run_dir / "inputs.json"
        inputs_record = (
            json.loads(inputs_path.read_text(encoding="utf-8")) if inputs_path.is_file() else {}
        )
        input_mesh_spacing = inputs_record.get("mesh_spacing_m")
        if input_mesh_spacing is None:
            raise ValueError("inputs.json must declare mesh_spacing_m for display sampling")
        input_mesh_spacing = float(input_mesh_spacing)
        if not math.isfinite(input_mesh_spacing) or input_mesh_spacing <= 0.0:
            raise ValueError("mesh_spacing_m must be finite and positive")
        kernel_h = (
            2.5 * input_mesh_spacing
            if whitewater_smoothing_length_m is None
            else float(whitewater_smoothing_length_m)
        )
        density_spacing = (
            2.0 * input_mesh_spacing
            if whitewater_grid_spacing_m is None
            else float(whitewater_grid_spacing_m)
        )
        whitewater_record: dict[str, Any] = {
            "enabled": False,
            "status": "disabled; only the computed interpolated alpha isosurface is shown",
            "changes_alpha_or_mass": False,
        }
        density_record: dict[str, Any] = {"enabled": False}
        density_grid = None
        if whitewater:
            cell_centers = np.asarray(volume_mesh.cell_centers().points, dtype=np.float64)
            samples, whitewater_record = _secondary_whitewater_samples(
                alpha,
                cell_centers,
                seed=seed,
                sample_count=whitewater_count,
                cell_spacing_m=input_mesh_spacing,
            )
            density_grid, density_record = _wendland_density_volume(
                samples,
                bounds,
                smoothing_length_m=kernel_h,
                grid_spacing_m=density_spacing,
                pyvista_module=pv,
            )
        camera_record = None
        window_size = (2200, 1200)
        plotter = pv.Plotter(off_screen=True, shape=(1, 2), window_size=window_size)
        try:
            plotter.set_background("#f7f9fc")
            plotter.subplot(0, 0)
            plotter.add_mesh(
                raw_surface,
                color="#287ca9",
                smooth_shading=True,
                ambient=0.38,
                diffuse=0.72,
                specular=0.20,
                specular_power=26,
                show_edges=False,
            )
            plotter.add_text(
                f"RAW CELL-THRESHOLD DIAGNOSTIC\nalpha.water ≥ {alpha_threshold:.2f} · t = {selected_time:.3f} s",
                position="upper_left",
                font_size=17,
                color="#152238",
            )
            plotter.add_axes(xlabel="x [m]", ylabel="y [m]", zlabel="z [m]")
            camera_record = _fixed_isometric_camera(plotter, bounds, window_size)

            plotter.subplot(0, 1)
            if density_grid is not None:
                plotter.add_volume(
                    density_grid,
                    scalars="whitewater_display_density",
                    cmap=WHITEWATER_COLORS,
                    opacity=WHITEWATER_OPACITIES,
                    opacity_unit_distance=density_spacing,
                    shade=False,
                    mapper="smart",
                    show_scalar_bar=False,
                )
            plotter.add_mesh(
                iso_surface,
                color="#287ca9",
                smooth_shading=True,
                ambient=0.38,
                diffuse=0.72,
                specular=0.30,
                specular_power=30,
                show_edges=False,
            )
            right_label = (
                f"CELL-TO-POINT alpha.water = {isosurface_alpha:.2f} ISOSURFACE\n"
                "Interpolated display geometry · computed VOF field"
            )
            if whitewater:
                right_label += (
                    f"\nInferred whitewater-style density · Wendland C2 h={kernel_h:.4f} m"
                    "\nUncalibrated detail · not a modeled foam/bubble phase"
                )
            else:
                right_label += "\nWater-only computed field · no subgrid detail"
            plotter.add_text(
                right_label,
                position="upper_left",
                font_size=16,
                color="#152238",
            )
            plotter.add_axes(xlabel="x [m]", ylabel="y [m]", zlabel="z [m]")
            _fixed_isometric_camera(plotter, bounds, window_size)
            plotter.show(screenshot=str(output_path), auto_close=True)
        finally:
            if getattr(plotter, "_closed", False) is False:
                plotter.close()

    manifest_path = run_dir / "manifest.json"
    manifest_record = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    )
    return {
        "schema": "vof-presentation-trial/v1",
        "run_id": manifest_record.get("run_id", run_dir.name),
        "case_id": inputs_record.get("case_id"),
        "simulation_time_s": selected_time,
        "presentation_seed": int(seed),
        "whitewater_requested": bool(whitewater),
        "coordinate_frame": inputs_record.get("coordinate_frame"),
        "domain_bounds_m": inputs_record.get("domain_bounds_m"),
        "mesh_shape": inputs_record.get("mesh_shape"),
        "mesh_spacing_m": inputs_record.get("mesh_spacing_m"),
        "solver": inputs_record.get("solver"),
        "turbulence_model": inputs_record.get("model"),
        "source_velocity_m_s_each": inputs_record.get("source_velocity_m_s_each"),
        "source_velocity_evidence": inputs_record.get("source_velocity_evidence"),
        "source_duration_s": inputs_record.get("source_duration_s"),
        "source_input_limit": inputs_record.get("evidence_label"),
        "source_alpha_field": str(alpha_path),
        "source_alpha_field_sha256": _sha256(alpha_path),
        "mesh_points_sha256": _sha256(mesh_points_path),
        "volume_cell_count": int(volume_mesh.n_cells),
        "water_inventory_m3_from_alpha_times_cell_volume": water_volume,
        "raw_alpha_threshold": alpha_threshold,
        "raw_thresholded_cell_count": int(raw_mesh.n_cells),
        "raw_thresholded_surface_triangle_count": int(raw_surface.n_cells),
        "isosurface_alpha": isosurface_alpha,
        "isosurface_point_count": int(iso_surface.n_points),
        "isosurface_triangle_count": int(iso_surface.n_cells),
        "point_alpha_value_range": [float(point_alpha.min()), float(point_alpha.max())],
        "display_geometry_processing": {
            "source": "saved cell-centered alpha.water",
            "operations": ["cell_data_to_point_data", "linear alpha isosurface", "triangulate"],
            "interpolation": "VTK cell-to-point interpolation over adjacent cells",
            "display_only": True,
            "original_alpha_cell_data_modified": False,
        },
        "volume_bounds_m": list(bounds),
        "whitewater_detail": {
            **whitewater_record,
            "density_volume": density_record,
            "display_mapping": {
                "color_controls_evenly_spaced_over_normalized_density_0_to_1": (
                    WHITEWATER_COLORS if whitewater else None
                ),
                "opacity_controls_evenly_spaced_over_normalized_density_0_to_1": (
                    WHITEWATER_OPACITIES if whitewater else None
                ),
                "opacity_unit_distance_m": density_spacing if whitewater else None,
                "status": "illustrative color/opacity, not calibrated optical constants",
            },
        },
        "render": {
            "output_png": str(output_path),
            "output_sha256": _sha256(output_path),
            "window_px": list(window_size),
            "comparison_camera": camera_record,
            "raw_panel": "cell-thresholded diagnostic from saved alpha.water",
            "surface_panel": "cell-to-point-interpolated alpha isosurface",
            "optional_density_volume": "secondary Wendland-kernel volume; display-only and inferred",
            "multiple_scattering": "not implemented",
            "optical_constants": "not supplied or calibrated",
            "vtk_version": ".".join(str(value) for value in pv.vtk_version_info),
            "pyvista_version": pv.__version__,
        },
        "foam_or_bubble_physics": "not modeled; alpha.water is not a bubble/foam classifier",
        "alpha_or_mass_modified_by_renderer": False,
        "claim_limit": (
            "Exploratory rendering of a horizontal, water-only VOF nearfield case. The right panel uses an "
            "interpolated alpha isosurface for display. Optional whitewater-style density is an inferred "
            "kernel volume from deterministic secondary samples, not physical foam, bubbles, spray, breakup, "
            "optical transfer, multiple scattering, deposition, or field performance."
        ),
        "code": {
            "script_sha256": _sha256(Path(__file__).resolve()),
            "git": _git_record(Path(__file__).resolve().parents[1]),
        },
        "rendered_utc": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--label", required=True, help="output label, such as water-only")
    parser.add_argument("--time", type=float, help="reconstructed simulation time in seconds")
    parser.add_argument("--alpha-threshold", type=float, default=0.65)
    parser.add_argument("--isosurface-alpha", type=float, default=0.50)
    parser.add_argument(
        "--whitewater",
        action="store_true",
        help="add an opt-in inferred Wendland density volume to the isosurface panel",
    )
    parser.add_argument("--whitewater-count", type=int, default=20000)
    parser.add_argument(
        "--whitewater-smoothing-length-m",
        type=float,
        help="illustrative Wendland h in metres (default: 2.5 times mesh spacing)",
    )
    parser.add_argument(
        "--whitewater-grid-spacing-m",
        type=float,
        help="density-volume spacing in metres (default: 2 times mesh spacing)",
    )
    parser.add_argument("--seed", type=int, default=417)
    args = parser.parse_args()
    try:
        record = render(
            run_dir=args.run_dir,
            output_dir=args.output_dir,
            label=args.label,
            time_s=args.time,
            alpha_threshold=args.alpha_threshold,
            isosurface_alpha=args.isosurface_alpha,
            whitewater=args.whitewater,
            whitewater_count=args.whitewater_count,
            seed=args.seed,
            whitewater_smoothing_length_m=args.whitewater_smoothing_length_m,
            whitewater_grid_spacing_m=args.whitewater_grid_spacing_m,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    record_path = Path(record["render"]["output_png"]).with_suffix(".json")
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Rendered {record['render']['output_png']}")
    print(f"Render record {record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
