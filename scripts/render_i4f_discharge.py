#!/usr/bin/env python3
"""Render timestamped, saved OpenFOAM fields for the I4F hydraulic reference.

Every frame is read from an exact OpenFOAM time directory. The renderer does
not synthesize intermediate flow states or bubble particles. A single saved
time produces a static image; an MP4 requires at least two distinct saved
physical times.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_case(path: Path) -> Path:
    path = path.expanduser().resolve(strict=True)
    bundled_case = path / "case"
    if bundled_case.is_dir() and list(bundled_case.glob("*.foam")):
        path = bundled_case
    marker = path / "i4f.foam"
    if marker.is_file():
        return path
    markers = sorted(path.glob("*.foam"))
    if len(markers) == 1 and markers[0].is_file():
        return path
    if len(markers) > 1:
        raise ValueError(f"case has multiple .foam markers; specify a case with one marker: {path}")
    raise ValueError(f"case must contain an existing .foam marker: {path}")


def saved_times(case_dir: Path) -> list[float]:
    values: list[float] = []
    for entry in case_dir.iterdir():
        if not entry.is_dir():
            continue
        try:
            value = float(entry.name)
        except ValueError:
            continue
        if math.isfinite(value) and value >= 0.0:
            values.append(value)
    values.sort()
    if not values:
        processors = sorted(p.name for p in case_dir.glob("processors*"))
        detail = f" Processor-local directories found: {processors}." if processors else ""
        raise ValueError(
            "no reconstructed numeric time directories are present at the case root."
            f"{detail} Reconstruct the selected OpenFOAM times before rendering."
        )
    if any(right <= left for left, right in zip(values, values[1:])):
        raise ValueError("saved OpenFOAM times must be distinct")
    return values


def derive_render_geometry(
    case_dir: Path, case_inputs: dict[str, Any], mesh_bounds: tuple[float, ...]
) -> dict[str, Any]:
    """Read apparatus orientation and stations from case metadata and its mesh."""
    metadata = case_inputs.get("geometry", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    legacy_config_path = case_dir.parent / "analysis-config.json"
    legacy_config: dict[str, Any] = {}
    if legacy_config_path.is_file():
        try:
            loaded = json.loads(legacy_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            legacy_config = loaded
    legacy_tank = legacy_config.get("tank", {})
    legacy_tank = legacy_tank if isinstance(legacy_tank, dict) else {}
    axis_name = str(metadata.get("tank_axis", "")).lower()
    axis_vector = metadata.get("tank_axis_vector_xyz")
    if axis_name not in {"horizontal", "vertical"} and axis_vector is not None:
        vector = np.asarray(axis_vector, dtype=np.float64)
        if vector.shape == (3,) and np.all(np.isfinite(vector)):
            if np.allclose(vector, (1.0, 0.0, 0.0), atol=1e-8):
                axis_name = "horizontal"
            elif np.allclose(vector, (0.0, 0.0, 1.0), atol=1e-8):
                axis_name = "vertical"
    tank_surface_path = case_dir / "constant/triSurface/tankWall.stl"
    tank_bounds = metadata.get("tank_bbox_xyz_m")
    geometry_source = "case-inputs geometry"
    if tank_bounds is None and legacy_tank:
        legacy_axis = str(legacy_tank.get("axis", "")).lower()
        legacy_vector = legacy_tank.get("axis_vector")
        if legacy_axis in {"horizontal", "vertical"}:
            axis_name = legacy_axis
        if legacy_vector is not None:
            axis_vector = legacy_vector
        diameter = float(legacy_tank.get("diameter_m", 0.0))
        if diameter <= 0.0:
            raise ValueError("legacy analysis-config.json tank diameter must be positive")
        if axis_name == "horizontal":
            x_start = float(legacy_tank.get("start_x_m", metadata.get("x_tank_start_m", 0.0)))
            length = float(legacy_tank.get("length_m", 0.0))
            center_z = float(legacy_tank.get("center_z_m", 0.0))
            if length <= 0.0:
                raise ValueError(
                    "legacy analysis-config.json horizontal tank length must be positive"
                )
            for key, recovered in (
                ("x_tank_start_m", x_start),
                ("x_tank_end_m", x_start + length),
            ):
                recorded = metadata.get(key)
                if recorded is not None and not math.isclose(
                    float(recorded), recovered, rel_tol=0.0, abs_tol=1e-6
                ):
                    raise ValueError(
                        f"archived tank geometry disagrees with case-inputs {key}: "
                        f"{recovered:g} vs {float(recorded):g} m"
                    )
            tank_bounds = [
                [
                    x_start,
                    float(legacy_tank.get("center_y_m", 0.0)) - 0.5 * diameter,
                    center_z - 0.5 * diameter,
                ],
                [
                    x_start + length,
                    float(legacy_tank.get("center_y_m", 0.0)) + 0.5 * diameter,
                    center_z + 0.5 * diameter,
                ],
            ]
            geometry_source = "archived analysis-config.json tank dimensions"
        elif axis_name == "vertical":
            raise ValueError(
                "legacy vertical analysis-config.json requires explicit tank_center_xyz_m and length"
            )
    if tank_bounds is None and tank_surface_path.is_file():
        surface_bounds = pv.read(tank_surface_path).bounds
        candidate_bounds = [
            [float(surface_bounds[0]), float(surface_bounds[2]), float(surface_bounds[4])],
            [float(surface_bounds[1]), float(surface_bounds[3]), float(surface_bounds[5])],
        ]
        candidate_extents = np.asarray(candidate_bounds[1]) - np.asarray(candidate_bounds[0])
        expected_axial_extent = float(
            metadata.get("x_tank_end_m", candidate_bounds[1][0])
            - metadata.get("x_tank_start_m", candidate_bounds[0][0])
        )
        if axis_name == "vertical" or (
            expected_axial_extent > 0.0
            and math.isclose(
                candidate_extents[0], expected_axial_extent, rel_tol=0.02, abs_tol=1e-6
            )
        ):
            tank_bounds = candidate_bounds
            geometry_source = "tankWall.stl bounds"
    if tank_bounds is None:
        raise ValueError(
            "saved case does not provide tank bounds or recoverable tank dimensions; "
            "refusing to use whole-domain bounds as the tank"
        )
    tank_bounds_array = np.asarray(tank_bounds, dtype=np.float64)
    if tank_bounds_array.shape != (2, 3) or not np.all(np.isfinite(tank_bounds_array)):
        raise ValueError("case tank bounds must be two finite xyz corners")
    mesh_bounds_array = np.asarray(mesh_bounds, dtype=np.float64).reshape(3, 2).T
    if np.any(tank_bounds_array[0] < mesh_bounds_array[0] - 1e-6) or np.any(
        tank_bounds_array[1] > mesh_bounds_array[1] + 1e-6
    ):
        raise ValueError("derived tank bounds fall outside the saved OpenFOAM mesh")
    extents = tank_bounds_array[1] - tank_bounds_array[0]
    if axis_name not in {"horizontal", "vertical"}:
        axis_name = "vertical" if int(np.argmax(extents)) == 2 else "horizontal"
    if axis_name == "horizontal":
        axis_vector = [1.0, 0.0, 0.0]
        axial_index = 0
    else:
        axis_vector = [0.0, 0.0, 1.0]
        axial_index = 2
    center = metadata.get("tank_center_xyz_m")
    if center is None:
        if axis_name == "horizontal" and legacy_tank:
            center = [
                0.5 * (tank_bounds_array[0, 0] + tank_bounds_array[1, 0]),
                float(legacy_tank.get("center_y_m", 0.0)),
                float(
                    legacy_tank.get(
                        "center_z_m", 0.5 * (tank_bounds_array[0, 2] + tank_bounds_array[1, 2])
                    )
                ),
            ]
        else:
            center = (tank_bounds_array[0] + tank_bounds_array[1]) / 2.0
    center_array = np.asarray(center, dtype=np.float64)
    if center_array.shape != (3,) or not np.all(np.isfinite(center_array)):
        raise ValueError("case tank center must contain three finite coordinates")

    x_tank_start = float(metadata.get("x_tank_start_m", tank_bounds_array[0, 0]))
    if axis_name == "horizontal":
        x_tank_end_default = float(tank_bounds_array[1, 0])
    else:
        x_tank_end_default = float(
            metadata.get("port_centerline_mouth_xyz_m", [tank_bounds_array[1, 0], 0, 0])[0]
        )
    x_tank_end = float(metadata.get("x_tank_end_m", x_tank_end_default))
    x_pipe_end = float(metadata.get("x_pipe_end_m", x_tank_end + 1.0))
    x_nozzle_exit = float(metadata.get("x_nozzle_exit_m", x_pipe_end + 1.5))
    x_external_end = float(metadata.get("x_external_end_m", x_nozzle_exit + 2.0))

    event = case_inputs.get("event_rule", {})
    event = event if isinstance(event, dict) else {}
    planes = event.get("observer_planes", {})
    planes = planes if isinstance(planes, dict) else {}
    nozzle_plane = planes.get("nozzle", {})
    nozzle_plane = nozzle_plane if isinstance(nozzle_plane, dict) else {}
    port_plane = planes.get("port", {})
    port_plane = port_plane if isinstance(port_plane, dict) else {}
    mouth = metadata.get("port_centerline_mouth_xyz_m")
    if mouth is not None and len(mouth) == 3:
        nozzle_center_y = float(mouth[1])
        nozzle_center_z = float(mouth[2])
    else:
        port_probe = event.get("port_probe_m", [x_tank_end + 0.2, 0.0, 0.65])
        if isinstance(port_probe, (list, tuple)) and len(port_probe) == 3:
            nozzle_center_y = float(port_probe[1])
            nozzle_center_z = float(port_probe[2])
        else:
            nozzle_center_y = float(port_plane.get("y_m", 0.0))
            nozzle_center_z = float(port_plane.get("z_m", 0.65))
    if nozzle_plane:
        nozzle_center_y = float(nozzle_plane.get("y_m", nozzle_center_y))
        nozzle_center_z = float(nozzle_plane.get("z_m", nozzle_center_z))
    legacy_nozzle = legacy_config.get("nozzle", {})
    legacy_nozzle = legacy_nozzle if isinstance(legacy_nozzle, dict) else {}

    nozzle_width = metadata.get("nozzle_width_m", legacy_nozzle.get("width_m"))
    nozzle_height = metadata.get("nozzle_height_m", legacy_nozzle.get("height_m"))
    nozzle_geometry_source = (
        "case-inputs geometry"
        if metadata.get("nozzle_width_m") is not None
        and metadata.get("nozzle_height_m") is not None
        else "archived analysis-config.json"
        if nozzle_width is not None and nozzle_height is not None
        else None
    )
    transition_surface = case_dir / "constant/triSurface/transitionWall.stl"
    if transition_surface.is_file():
        points = np.asarray(pv.read(transition_surface).points, dtype=np.float64)
        terminal = points[np.isclose(points[:, 0], x_nozzle_exit, rtol=0.0, atol=1e-7)]
        if terminal.size:
            nozzle_width = float(np.ptp(terminal[:, 1]))
            nozzle_height = float(np.ptp(terminal[:, 2]))
            nozzle_center_y = float(0.5 * (terminal[:, 1].min() + terminal[:, 1].max()))
            nozzle_center_z = float(0.5 * (terminal[:, 2].min() + terminal[:, 2].max()))
            nozzle_geometry_source = "transitionWall.stl terminal ring"
    if nozzle_width is None or nozzle_height is None:
        raise ValueError("saved case has no nozzle dimensions or transitionWall.stl terminal ring")
    nozzle_width, nozzle_height = float(nozzle_width), float(nozzle_height)

    supplier = metadata.get("vertical_supplier_metadata", {})
    supplier = supplier if isinstance(supplier, dict) else {}
    supplier_port = supplier.get("port", {})
    supplier_port = supplier_port if isinstance(supplier_port, dict) else {}
    pipe_diameter = supplier_port.get("diameter_m")
    if pipe_diameter is not None:
        pipe_radius = 0.5 * float(pipe_diameter)
    else:
        pipe_area = float(
            metadata.get(
                "pipe_polygon_area_m2", metadata.get("pipe_analytic_area_m2", math.pi * 0.125**2)
            )
        )
        pipe_radius = math.sqrt(max(pipe_area, 0.0) / math.pi)

    return {
        "tank_axis": axis_name,
        "tank_geometry_source": geometry_source,
        "legacy_analysis_config_sha256": (
            sha256(legacy_config_path) if legacy_tank and legacy_config_path.is_file() else None
        ),
        "tank_axis_vector_xyz": [float(value) for value in axis_vector],
        "tank_center_xyz_m": [float(value) for value in center_array],
        "tank_bbox_xyz_m": tank_bounds_array.tolist(),
        "tank_length_m": float(extents[axial_index]),
        "tank_sample_x_m": (
            float(center_array[0])
            if axis_name == "vertical"
            else x_tank_start + 0.525 * float(extents[axial_index])
        ),
        "tank_axis_label": "vertical (z)" if axis_name == "vertical" else "horizontal (x)",
        "tank_start_x_m": x_tank_start,
        "tank_end_x_m": x_tank_end,
        "pipe_end_x_m": x_pipe_end,
        "nozzle_exit_x_m": x_nozzle_exit,
        "external_end_x_m": x_external_end,
        "valve_x_m": float(case_inputs.get("valve", {}).get("location_x_m", 2.4)),
        "nozzle_center_y_m": nozzle_center_y,
        "nozzle_center_z_m": nozzle_center_z,
        "nozzle_width_m": nozzle_width,
        "nozzle_height_m": nozzle_height,
        "nozzle_geometry_source": nozzle_geometry_source,
        "pipe_radius_m": pipe_radius,
        "mesh_bounds_xyz_m": [float(value) for value in mesh_bounds],
    }


def validated_view_bounds(
    supplied: tuple[float, ...] | None,
    derived: tuple[float, float, float, float],
    label: str,
) -> tuple[float, float, float, float]:
    bounds = derived if supplied is None else supplied
    if len(bounds) != 4 or not all(math.isfinite(value) for value in bounds):
        raise ValueError(f"{label} bounds must contain four finite coordinates")
    if bounds[1] <= bounds[0] or bounds[3] <= bounds[2]:
        raise ValueError(f"{label} bounds must be increasing")
    return tuple(float(value) for value in bounds)


def requested_times(raw: str | None, available: list[float]) -> list[float]:
    if raw is None:
        return available.copy()
    values: list[float] = []
    for item in raw.split(","):
        try:
            value = float(item.strip())
        except ValueError as error:
            raise ValueError(f"invalid physical time in --times: {item!r}") from error
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("requested physical times must be finite and nonnegative")
        match = next(
            (
                saved
                for saved in available
                if math.isclose(value, saved, rel_tol=1e-9, abs_tol=1e-12)
            ),
            None,
        )
        if match is None:
            raise ValueError(
                f"requested time {value:g} s is not saved. Available times: "
                + ", ".join(f"{time:g}" for time in available)
            )
        values.append(match)
    if not values:
        raise ValueError("--times must select at least one saved physical time")
    if any(right <= left for left, right in zip(values, values[1:])):
        raise ValueError("--times must be strictly increasing and contain no duplicates")
    return values


def limit_times(values: list[float], max_frames: int) -> list[float]:
    if max_frames <= 0:
        raise ValueError("--max-frames must be a positive integer")
    if len(values) <= max_frames:
        return values
    indices = np.rint(np.linspace(0, len(values) - 1, max_frames)).astype(int)
    return [values[index] for index in sorted(set(indices.tolist()))]


def active_mesh(reader: pv.OpenFOAMReader, time_s: float) -> pv.UnstructuredGrid:
    reader.set_active_time_value(time_s)
    data = reader.read()
    if not isinstance(data, pv.MultiBlock) or data.n_blocks == 0 or data[0] is None:
        raise ValueError(f"OpenFOAMReader returned no internal mesh at t={time_s:g} s")
    mesh = data[0]
    if not isinstance(mesh, pv.DataSet) or mesh.n_cells == 0:
        raise ValueError(f"OpenFOAM internal mesh is empty at t={time_s:g} s")
    if "alpha.water" not in mesh.cell_data:
        raise ValueError(f"alpha.water is unavailable at t={time_s:g} s")
    return mesh


def values_for_field(mesh: pv.DataSet, field: str) -> tuple[np.ndarray, str, str]:
    if field == "p":
        if "p" not in mesh.cell_data:
            raise ValueError("pressure field 'p' is unavailable in the selected time")
        return (
            np.asarray(mesh.cell_data["p"], dtype=np.float64),
            "pressure p (Pa absolute)",
            "magma",
        )
    if field == "speed":
        if "U" not in mesh.cell_data:
            raise ValueError("velocity field 'U' is unavailable in the selected time")
        velocity = np.asarray(mesh.cell_data["U"], dtype=np.float64)
        if velocity.ndim != 2 or velocity.shape[1] != 3:
            raise ValueError("U must contain three cell-centred velocity components")
        return np.linalg.norm(velocity, axis=1), "speed |U| (m s$^{-1}$)", "viridis"
    raise ValueError(f"unsupported field: {field}")


def scalar_range(
    reader: pv.OpenFOAMReader,
    times: Iterable[float],
    field: str,
    requested_min: float | None,
    requested_max: float | None,
) -> tuple[float, float]:
    actual_min, actual_max = math.inf, -math.inf
    for time_s in times:
        mesh = active_mesh(reader, time_s)
        values, _, _ = values_for_field(mesh, field)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            raise ValueError(f"field {field} has no finite values at t={time_s:g} s")
        actual_min = min(actual_min, float(finite.min()))
        actual_max = max(actual_max, float(finite.max()))
    vmin = actual_min if requested_min is None else requested_min
    vmax = actual_max if requested_max is None else requested_max
    if not math.isfinite(vmin) or not math.isfinite(vmax) or vmax <= vmin:
        if field == "speed" and math.isclose(vmin, vmax, abs_tol=1e-12):
            vmax = vmin + 1.0
        else:
            raise ValueError("field display scale must have finite increasing limits")
    return vmin, vmax


def triangles_as_polygons(
    data: pv.PolyData, axes: tuple[int, int], scalars: np.ndarray
) -> list[np.ndarray]:
    mesh = data.triangulate()
    points = np.asarray(mesh.points)
    faces = np.asarray(mesh.faces)
    if faces.size % 4:
        raise ValueError("triangulated cut contains an unexpected non-triangle cell")
    faces = faces.reshape((-1, 4))[:, 1:]
    scalar_values = np.asarray(scalars, dtype=np.float64)
    if scalar_values.size != faces.shape[0]:
        raise ValueError("cut geometry and cell field have different cell counts")
    return [points[face][:, axes] for face in faces]


def add_cell_cut(
    ax: Any,
    mesh: pv.DataSet,
    *,
    normal: tuple[float, float, float],
    origin: tuple[float, float, float],
    axes: tuple[int, int],
    field: str,
    cmap: str,
    limits: tuple[float, float],
) -> Any:
    cut = mesh.slice(normal=normal, origin=origin).triangulate()
    if cut.n_cells == 0:
        raise ValueError(f"empty mesh cut at origin={origin} normal={normal}")
    if field == "alpha.water":
        scalars = np.asarray(cut.cell_data[field], dtype=np.float64)
    else:
        source_values, _, _ = values_for_field(mesh, field)
        # PyVista's slicing interpolates cell data onto new cut cells. Compute
        # the same scalar with a temporary cell array to keep field selection
        # explicit and units attached to the original OpenFOAM field.
        working = mesh.copy(deep=True)
        working.cell_data["_i4f_display_scalar"] = source_values
        cut = working.slice(normal=normal, origin=origin).triangulate()
        scalars = np.asarray(cut.cell_data["_i4f_display_scalar"], dtype=np.float64)
    polygons = triangles_as_polygons(cut, axes, scalars)
    collection = PolyCollection(
        polygons,
        array=scalars,
        cmap=cmap,
        clim=limits,
        edgecolors="none",
        linewidths=0,
        antialiased=False,
        rasterized=True,
    )
    ax.add_collection(collection)
    ax.autoscale_view()
    return collection


def add_liquid_speed_inset(
    ax: Any,
    mesh: pv.DataSet,
    geometry: dict[str, Any],
    xz_bounds: tuple[float, float, float, float],
) -> None:
    """Show a second, liquid-only velocity scale beside the full speed field."""
    velocity = np.asarray(mesh.cell_data["U"], dtype=np.float64)
    speed = np.linalg.norm(velocity, axis=1)
    working = mesh.copy(deep=True)
    working.cell_data["_i4f_liquid_speed"] = speed
    cut_y = float(geometry["tank_center_xyz_m"][1])
    cut = working.slice(normal=(0, 1, 0), origin=(0, cut_y, 0)).triangulate()
    alpha = np.asarray(cut.cell_data["alpha.water"], dtype=np.float64)
    cut_speed = np.asarray(cut.cell_data["_i4f_liquid_speed"], dtype=np.float64)
    polygons = triangles_as_polygons(cut, (0, 2), cut_speed)
    liquid = np.isfinite(alpha) & np.isfinite(cut_speed) & (alpha >= 0.5)
    if not np.any(liquid):
        return

    inset = ax.inset_axes([0.02, 0.045, 0.58, 0.50], facecolor="white", zorder=5)
    collection = PolyCollection(
        [polygon for polygon, keep in zip(polygons, liquid, strict=True) if keep],
        array=cut_speed[liquid],
        cmap="viridis",
        clim=(0.0, 25.0),
        edgecolors="none",
        linewidths=0,
        antialiased=False,
        rasterized=True,
    )
    inset.add_collection(collection)
    inset.set_xlim(xz_bounds[0], xz_bounds[1])
    inset.set_ylim(xz_bounds[2], xz_bounds[3])
    inset.set_aspect("equal", adjustable="box")
    inset.set_title("Liquid speed (αwater ≥ 0.5), 0–25 m/s", fontsize=7, pad=2)
    inset.set_xlabel("x (m)", fontsize=6, labelpad=0)
    inset.set_ylabel("z (m)", fontsize=6, labelpad=0)
    inset.tick_params(labelsize=5, pad=1)
    inset.grid(False)
    inset.set_facecolor("white")
    inset.patch.set_alpha(0.96)
    inset.spines[:].set_color("#343a40")
    colorbar = inset.inset_axes([1.015, 0.08, 0.035, 0.84])
    inset.figure.colorbar(collection, cax=colorbar, ticks=(0.0, 25.0))
    colorbar.tick_params(labelsize=5, pad=1)


def alpha_contour(plane: pv.PolyData, level: float = 0.5) -> pv.PolyData | None:
    # The cell-to-point interpolation is used only to make a display contour.
    # The underlying saved alpha.water values and volume integrals are untouched.
    converted = plane.cell_data_to_point_data(pass_cell_data=True)
    if "alpha.water" not in converted.point_data:
        return None
    contour = converted.contour([level], scalars="alpha.water")
    return contour if contour.n_cells else None


ALPHA_CLASS_COLORS = ("#dce6ef", "#edb458", "#f28482", "#123b63")
ALPHA_CLASS_LABELS = (
    "gas core (αwater ≤ 0.01)",
    "gas-side mixed cells (0.01 < αwater < 0.50)",
    "liquid-side mixed cells (0.50 ≤ αwater < 0.99)",
    "water core (αwater ≥ 0.99)",
)


def add_alpha_class_cut(
    ax: Any,
    mesh: pv.DataSet,
    *,
    normal: tuple[float, float, float],
    origin: tuple[float, float, float],
    axes: tuple[int, int],
) -> pv.PolyData:
    """Draw cell-native alpha classes on a planar cut, without point smoothing."""
    cut = mesh.slice(normal=normal, origin=origin).triangulate()
    if cut.n_cells == 0:
        raise ValueError(f"empty alpha.class cut at origin={origin} normal={normal}")
    alpha = np.asarray(cut.cell_data["alpha.water"], dtype=np.float64)
    if not np.isfinite(alpha).all():
        raise ValueError("non-finite alpha.water values in a connection diagnostic cut")
    categories = np.select(
        [alpha <= 0.01, alpha < 0.5, alpha < 0.99],
        [0, 1, 2],
        default=3,
    ).astype(np.int8)
    polygons = triangles_as_polygons(cut, axes, alpha)
    collection = PolyCollection(
        polygons,
        facecolors=np.asarray(ALPHA_CLASS_COLORS)[categories],
        edgecolors="none",
        linewidths=0,
        antialiased=False,
        rasterized=True,
    )
    ax.add_collection(collection)
    ax.autoscale_view()
    return cut


def draw_alpha_contours(
    ax: Any,
    cut: pv.PolyData,
    *,
    axes: tuple[int, int],
    levels: tuple[float, ...],
) -> dict[str, bool]:
    styles = {
        0.01: ("#188977", (0, (4, 2))),
        0.5: ("#d62828", "-"),
        0.99: ("#6a4c93", (0, (2, 2))),
    }
    present: dict[str, bool] = {}
    for level in levels:
        color, linestyle = styles[level]
        contour = alpha_contour(cut, level)
        present[f"{level:g}"] = contour is not None
        if contour is None:
            continue
        for cell_index in range(contour.n_cells):
            points = np.asarray(contour.get_cell(cell_index).points)
            if points.shape[0] >= 2:
                ax.plot(
                    points[:, axes[0]],
                    points[:, axes[1]],
                    color=color,
                    linestyle=linestyle,
                    linewidth=0.9 if level == 0.5 else 0.7,
                    alpha=0.95,
                )
    return present


def parse_numeric_history(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        values: list[float] = []
        for token in stripped.replace("(", " ").replace(")", " ").split():
            try:
                values.append(float(token))
            except ValueError:
                continue
        if len(values) >= 2 and all(math.isfinite(v) for v in (values[0], values[-1])):
            rows.append((values[0], values[-1]))
    return rows


def parse_pressure_probes(
    path: Path,
) -> tuple[dict[int, tuple[float, float, float]], list[tuple[float, list[float]]]]:
    coordinates: dict[int, tuple[float, float, float]] = {}
    rows: list[tuple[float, list[float]]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# Probe "):
            parts = stripped.replace("(", " ").replace(")", " ").split()
            try:
                index = int(parts[2])
                coordinate = tuple(float(value) for value in parts[3:6])
            except (IndexError, ValueError):
                continue
            if len(coordinate) == 3:
                coordinates[index] = coordinate  # type: ignore[assignment]
            continue
        if stripped.startswith("#"):
            continue
        try:
            values = [float(token) for token in stripped.split()]
        except ValueError:
            continue
        if len(values) >= 2 and all(math.isfinite(value) for value in values):
            rows.append((values[0], values[1:]))
    return coordinates, rows


def probe_location_audit(
    point: tuple[float, float, float], geometry: dict[str, Any]
) -> dict[str, Any]:
    p = np.asarray(point, dtype=np.float64)
    bbox = np.asarray(geometry["tank_bbox_xyz_m"], dtype=np.float64)
    center = np.asarray(geometry["tank_center_xyz_m"], dtype=np.float64)
    radius = 0.5 * min(
        bbox[1, i] - bbox[0, i]
        for i in range(3)
        if i != (0 if geometry["tank_axis"] == "horizontal" else 2)
    )
    if geometry["tank_axis"] == "horizontal":
        in_tank = (
            bbox[0, 0] - 1e-6 <= p[0] <= bbox[1, 0] + 1e-6
            and math.hypot(p[1] - center[1], p[2] - center[2]) <= radius + 1e-6
        )
    else:
        in_tank = (
            bbox[0, 2] - 1e-6 <= p[2] <= bbox[1, 2] + 1e-6
            and math.hypot(p[0] - center[0], p[1] - center[1]) <= radius + 1e-6
        )
    if in_tank:
        return {
            "valid": True,
            "region": "tank interior",
            "reason": "point lies inside the tank cylinder from the saved geometry",
        }

    pipe_radius = float(geometry["pipe_radius_m"])
    near_centerline = (
        abs(p[1] - float(geometry["nozzle_center_y_m"])) <= pipe_radius
        and abs(p[2] - float(geometry["nozzle_center_z_m"])) <= pipe_radius
    )
    if (
        float(geometry["tank_end_x_m"]) - 0.03 <= p[0] <= float(geometry["nozzle_exit_x_m"]) + 1e-6
        and near_centerline
    ):
        return {
            "valid": True,
            "region": "port/pipe/transition",
            "reason": "point lies on the downstream apparatus centerline within its pipe radius",
        }

    mesh_bounds = np.asarray(geometry["mesh_bounds_xyz_m"], dtype=np.float64)
    within_domain = (
        mesh_bounds[0] <= p[0] <= mesh_bounds[1]
        and mesh_bounds[2] <= p[1] <= mesh_bounds[3]
        and mesh_bounds[4] <= p[2] <= mesh_bounds[5]
    )
    if p[0] > float(geometry["nozzle_exit_x_m"]) and within_domain:
        return {
            "valid": True,
            "region": "external air domain",
            "reason": "point lies downstream of the nozzle exit and inside the saved external mesh bounds",
        }
    return {
        "valid": False,
        "region": None,
        "reason": "point is outside the tank, downstream centerline, and external mesh bounds",
    }


def load_history(
    case_dir: Path, geometry: dict[str, Any]
) -> tuple[dict[str, list[tuple[float, float]]], dict[str, Any]]:
    post = case_dir / "postProcessing"
    result: dict[str, list[tuple[float, float]]] = {}
    probe_audit: dict[str, Any] = {
        "status": "no probe file found",
        "probe_files": [],
        "valid_probe_indices": [],
        "excluded_probe_indices": [],
        "probes": [],
    }
    if not post.is_dir():
        return result, probe_audit
    candidates: dict[str, list[Path]] = {
        "tank water volume": [],
    }
    for path in post.rglob("*.dat"):
        if "tankWaterVolume" in path.parts:
            candidates["tank water volume"].append(path)
    for label, files in candidates.items():
        rows: dict[float, float] = {}
        for path in sorted(files):
            for time_s, value in parse_numeric_history(path):
                rows[time_s] = value
        if rows:
            result[label] = sorted(rows.items())

    probe_files = sorted(
        path for path in post.rglob("p") if "probes" in path.parts and path.is_file()
    )
    probe_audit["probe_files"] = [str(path.relative_to(case_dir)) for path in probe_files]
    probe_coordinates: dict[int, tuple[float, float, float]] = {}
    pressure_rows: dict[float, list[float]] = {}
    for path in probe_files:
        coordinates, rows = parse_pressure_probes(path)
        probe_coordinates.update(coordinates)
        pressure_rows.update({time_s: values for time_s, values in rows})
    if probe_coordinates and pressure_rows:
        valid_indices: list[int] = []
        for index, coordinate in sorted(probe_coordinates.items()):
            audit = probe_location_audit(coordinate, geometry)
            probe_audit["probes"].append(
                {"index": index, "coordinates_m": list(coordinate), **audit}
            )
            if audit["valid"]:
                valid_indices.append(index)
        probe_audit["valid_probe_indices"] = valid_indices
        probe_audit["excluded_probe_indices"] = [
            entry["index"] for entry in probe_audit["probes"] if not entry["valid"]
        ]
        probe_audit["status"] = (
            "recorded probe coordinates checked against saved tank and downstream geometry"
        )
        preferred = [index for index in (0, 1, 6, 7) if index in valid_indices]
        if not preferred:
            preferred = valid_indices[:4]
        for index in preferred:
            x, y, z = probe_coordinates[index]
            label = f"pressure probe {index} at ({x:g}, {y:g}, {z:g}) m"
            rows = [
                (time_s, values[index])
                for time_s, values in sorted(pressure_rows.items())
                if index < len(values)
            ]
            if rows:
                result[label] = rows
    return result, probe_audit


def draw_history(ax: Any, history: dict[str, list[tuple[float, float]]], time_s: float) -> None:
    history = {
        label: [
            (sample_time, value) for sample_time, value in rows if sample_time <= time_s + 1e-12
        ]
        for label, rows in history.items()
    }
    history = {label: rows for label, rows in history.items() if rows}
    if not history:
        ax.text(
            0.5,
            0.5,
            "No verified history through this saved time was included.\n"
            "The plotted field is an exact saved snapshot.",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=10,
        )
        ax.set_title("History unavailable through this field time")
        ax.set_axis_off()
        return
    plotted = False
    pressure_labels = [label for label in history if label.startswith("pressure probe ")]
    tank_rows = history.get("tank water volume")
    pressure_axis = ax.twinx() if tank_rows and pressure_labels else ax if pressure_labels else None
    if tank_rows:
        volume_axis = ax
        values = np.asarray(tank_rows, dtype=np.float64)
        drawdown = values[0, 1] - values[:, 1]
        volume_axis.plot(
            values[:, 0],
            drawdown,
            lw=1.8,
            color="#1768ac",
            label="tank water drawdown from first sample (m$^3$)",
        )
        plotted = True
    if pressure_axis is not None:
        palette = ("#c44536", "#e07a2d", "#6f4e9c", "#159d85")
        for index, label in enumerate(pressure_labels):
            values = np.asarray(history[label], dtype=np.float64)
            pressure_axis.plot(
                values[:, 0],
                values[:, 1],
                lw=1.3,
                color=palette[index % len(palette)],
                label=label,
            )
            plotted = True
    if plotted:
        ax.axvline(time_s, color="#343a40", lw=1.0, ls="--", label=f"field t={time_s:g} s")
        ax.set_xlabel("physical time (s)")
        ax.set_ylabel("tank water volume drawdown (m$^3$)")
        if pressure_axis is not None:
            pressure_axis.set_ylabel("absolute pressure p (Pa)")
        elif not tank_rows:
            ax.set_ylabel("absolute pressure p (Pa)")
        h1, l1 = ax.get_legend_handles_labels()
        if pressure_axis is not None and pressure_axis is not ax:
            h2, l2 = pressure_axis.get_legend_handles_labels()
        else:
            h2, l2 = [], []
        ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="best", framealpha=0.9)
    if tank_rows and pressure_labels:
        ax.set_title("Tank drawdown and verified absolute-pressure probes")
    elif tank_rows:
        ax.set_title("Tank-water drawdown (no verified pressure probes)")
    elif pressure_labels:
        ax.set_ylabel("absolute pressure p (Pa)")
        ax.set_title("Verified absolute pressure probes; tank-water-volume history unavailable")
    else:
        ax.set_title("History unavailable")
    ax.grid(True, alpha=0.22)


def add_stage_annotations(ax: Any, case_inputs: dict[str, Any], geometry: dict[str, Any]) -> None:
    pipe_start = float(geometry["tank_end_x_m"])
    transition_start = float(geometry["pipe_end_x_m"])
    outlet_x = float(geometry["nozzle_exit_x_m"])
    limits = ax.get_xlim()
    zmin, zmax = ax.get_ylim()
    height = zmax - zmin
    for x in (pipe_start, transition_start, outlet_x):
        ax.axvline(x, color="#495057", lw=0.8, ls="--", alpha=0.85)
    ax.text(
        float(geometry["tank_center_xyz_m"][0]),
        zmax - 0.07 * height,
        f"{geometry['tank_axis']} tank",
        ha="center",
        va="top",
        fontsize=8,
        color="#343a40",
    )
    ax.text(
        0.5 * (pipe_start + transition_start),
        zmax - 0.07 * height,
        "pipe",
        ha="center",
        va="top",
        fontsize=8,
        color="#343a40",
    )
    ax.text(
        0.5 * (transition_start + outlet_x),
        zmax - 0.07 * height,
        "transition",
        ha="center",
        va="top",
        fontsize=8,
        color="#343a40",
    )
    ax.text(
        0.5 * (outlet_x + limits[1]),
        zmax - 0.07 * height,
        "nozzle exit / external air",
        ha="center",
        va="top",
        fontsize=8,
        color="#343a40",
    )
    valve_x = float(geometry["valve_x_m"])
    ax.axvspan(valve_x - 0.05, valve_x + 0.05, color="#e76f51", alpha=0.16, lw=0)
    ax.annotate(
        "x = 2.35–2.45 m: scalar valve-loss zone; no resolved disk",
        xy=(valve_x, float(geometry["nozzle_center_z_m"])),
        xytext=(min(valve_x + 0.32, limits[1] - 1.25), zmax - 0.22 * height),
        arrowprops={"arrowstyle": "->", "color": "#9c3d20", "lw": 0.8},
        fontsize=7,
        color="#7a2e18",
    )
    if case_inputs.get("lamellae", {}).get("included_in_reference") is False:
        start_fraction = float(
            case_inputs.get("lamellae", {}).get("reported_start_transition_fraction", 0.5)
        )
        x = transition_start + start_fraction * (outlet_x - transition_start)
        ax.axvline(x, color="#6c757d", lw=1.0, ls=":")
    ax.set_xlim(limits)


def draw_external_isosurface_image(
    mesh: pv.DataSet,
    outlet_x: float,
    time_s: float,
    geometry: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    # Keep the positive-x side of the nozzle exit plane: the opposite clip
    # would select tank/pipe contents and mislabel them as an external sheet.
    external = mesh.clip(normal=(1.0, 0.0, 0.0), origin=(outlet_x, 0.0, 0.0), invert=False)
    surface: pv.PolyData | None = None
    if external.n_cells:
        point_mesh = external.cell_data_to_point_data(pass_cell_data=True)
        if "alpha.water" in point_mesh.point_data:
            candidate = point_mesh.contour([0.5], scalars="alpha.water").triangulate()
            if candidate.n_cells:
                surface = candidate
    if surface is None:
        fig, ax = plt.subplots(figsize=(5.4, 3.6), constrained_layout=True)
        ax.text(
            0.5,
            0.56,
            "No resolved external $\\alpha_{water}=0.50$ interface\n"
            f"in saved field at $t={time_s:g}$ s",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=10,
        )
        ax.text(
            0.5,
            0.38,
            "No bubble particles or foam are synthesized.",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=8,
            color="#555",
        )
        ax.set_axis_off()
        fig.savefig(output_path, dpi=170, facecolor="white")
        plt.close(fig)
        return {"present": False, "triangle_count": 0, "image": str(output_path)}

    fig, ax = plt.subplots(figsize=(7.2, 4.5), constrained_layout=True)
    poly_faces = np.asarray(surface.faces).reshape((-1, 4))[:, 1:]
    points = np.asarray(surface.points)
    projected_polygons = [points[face][:, (1, 2)] for face in poly_faces]
    projected = PolyCollection(
        projected_polygons,
        facecolors="#168aad",
        edgecolors="none",
        linewidths=0,
        antialiased=False,
        rasterized=True,
    )
    ax.add_collection(projected)
    width = float(geometry["nozzle_width_m"])
    height = float(geometry["nozzle_height_m"])
    center_y = float(geometry["nozzle_center_y_m"])
    center_z = float(geometry["nozzle_center_z_m"])
    y_half = width / 2.0 + 0.08
    y_extent = min(
        y_half, max(abs(external.bounds[2] - center_y), abs(external.bounds[3] - center_y))
    )
    z_half = height / 2.0 + 0.10
    z_min = max(external.bounds[4], center_z - z_half)
    z_max = min(external.bounds[5], center_z + z_half)
    half_width, half_height = width / 2.0, height / 2.0
    corners = [
        (center_y - half_width, center_z - half_height),
        (center_y + half_width, center_z - half_height),
        (center_y + half_width, center_z + half_height),
        (center_y - half_width, center_z + half_height),
        (center_y - half_width, center_z - half_height),
    ]
    rectangle = np.asarray([point for point in corners])
    ax.plot(rectangle[:, 0], rectangle[:, 1], color="#343a40", lw=1.2, label="nominal exit opening")
    ax.set_xlim(center_y - y_extent, center_y + y_extent)
    ax.set_ylim(z_min, z_max)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("y horizontal span (m)")
    ax.set_ylabel("z upward (m)")
    ax.legend(loc="upper right", fontsize=7, framealpha=0.9)
    ext_x = np.asarray(surface.points)[:, 0]
    fig.suptitle(
        "Computed external $\\alpha_{water}=0.50$ isosurface, projected along x\n"
        f"t = {time_s:.8g} s; surface x extent "
        f"{surface.bounds[0]:.4f}–{surface.bounds[1]:.4f} m\n"
        f"Nominal nozzle {width:g} × {height:g} m",
        fontsize=10,
    )
    fig.savefig(output_path, dpi=170, facecolor="white")
    plt.close(fig)
    return {
        "present": True,
        "triangle_count": int(surface.n_cells),
        "representation": "alpha.water=0.50 contour after cell-to-point display interpolation, projected onto y-z",
        "surface_bounds_m": [float(v) for v in surface.bounds],
        "extends_beyond_nozzle_plane": bool(float(ext_x.max()) > outlet_x + 1e-6),
        "image": str(output_path),
    }


def draw_cross_sections(
    mesh: pv.DataSet,
    time_s: float,
    geometry: dict[str, Any],
    output_path: Path,
) -> None:
    tank_label = f"{geometry['tank_axis']} tank section"
    transition_start = float(geometry["pipe_end_x_m"])
    nozzle_exit = float(geometry["nozzle_exit_x_m"])
    ext_end = float(geometry["external_end_x_m"])
    valve_x = float(geometry["valve_x_m"])
    stations = [
        (float(geometry["tank_sample_x_m"]), tank_label),
        (valve_x + 0.13, "pipe near valve"),
        (0.5 * (transition_start + nozzle_exit), "transition midpoint"),
        (nozzle_exit - 0.02, "nozzle, 0.02 m upstream"),
        (nozzle_exit + 0.01, "external air entrance"),
        (0.5 * (nozzle_exit + ext_end), "external air region"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.2), constrained_layout=True)
    mappable = None
    for ax, (x, label) in zip(axes.flat, stations, strict=True):
        mappable = add_cell_cut(
            ax,
            mesh,
            normal=(1, 0, 0),
            origin=(x, float(geometry["tank_center_xyz_m"][1]), 0),
            axes=(1, 2),
            field="alpha.water",
            cmap="Blues",
            limits=(0.0, 1.0),
        )
        ax.set_title(f"x = {x:.2f} m • {label}", fontsize=9)
        ax.set_xlabel("y horizontal span (m)")
        ax.set_ylabel("z upward (m)")
        ax.set_aspect("equal", adjustable="box")
        cut = mesh.slice(
            normal=(1, 0, 0),
            origin=(x, float(geometry["tank_center_xyz_m"][1]), 0),
        )
        if cut.n_cells:
            y_min, y_max = float(cut.bounds[2]), float(cut.bounds[3])
            z_min, z_max = float(cut.bounds[4]), float(cut.bounds[5])
            y_pad = max(0.025, 0.06 * (y_max - y_min))
            z_pad = max(0.025, 0.06 * (z_max - z_min))
            ax.set_xlim(y_min - y_pad, y_max + y_pad)
            ax.set_ylim(z_min - z_pad, z_max + z_pad)
    if mappable is not None:
        fig.colorbar(mappable, ax=list(axes.flat), label="saved cell alpha.water", shrink=0.85)
    fig.suptitle(f"I4F connection and cross-section checks • saved field at t = {time_s:.8g} s")
    fig.savefig(output_path, dpi=170, facecolor="white")
    plt.close(fig)


def load_connection_reference(case_inputs: dict[str, Any]) -> dict[str, Any]:
    provenance = case_inputs.get("provenance", {})
    source = Path(provenance.get("baseline_config", "experiments/i4f_baseline.json"))
    candidates = [source, Path.cwd() / "experiments/i4f_baseline.json"]
    expected_hash = provenance.get("baseline_config_sha256")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        candidate = candidate.resolve()
        actual_hash = sha256(candidate)
        if expected_hash and actual_hash != expected_hash:
            continue
        config = json.loads(candidate.read_text(encoding="utf-8"))
        connection = config.get("connection", {})
        tank = config.get("tank", {})
        pipe = config.get("pipe", {})
        if all(key in connection for key in ("center_z_m", "lower_edge_z_m", "upper_edge_z_m")):
            return {
                "tank_end_x_m": float(tank.get("start_x_m", 0.0))
                + float(tank.get("length_m", 2.0)),
                "connection_center_z_m": float(connection["center_z_m"]),
                "connection_lower_z_m": float(connection["lower_edge_z_m"]),
                "connection_upper_z_m": float(connection["upper_edge_z_m"]),
                "pipe_radius_m": float(pipe.get("diameter_m", 0.25)) / 2.0,
                "source": str(candidate),
                "sha256": actual_hash,
            }
    raise ValueError(
        "connection diagnostic requires the baseline geometry file whose hash is "
        "recorded in case-inputs.json"
    )


def free_surface_at_x(mesh: pv.DataSet, x_m: float) -> float | None:
    cut = mesh.slice(normal=(0, 1, 0), origin=(0, 0, 0)).triangulate()
    contour = alpha_contour(cut, 0.5)
    if contour is None:
        return None
    points = np.asarray(contour.points)
    near = points[(np.abs(points[:, 0] - x_m) <= 0.10) & (points[:, 2] > 0.9)]
    return float(np.median(near[:, 2])) if near.size else None


def gas_core_connectivity(
    mesh: pv.DataSet,
    *,
    free_surface_z_m: float | None,
    connection: dict[str, Any],
) -> dict[str, Any]:
    """Check a thresholded 3D cell component from upper headspace to pipe mouth."""
    cell_centers = np.asarray(mesh.cell_centers().points)
    roi = (
        (cell_centers[:, 0] >= 1.2)
        & (cell_centers[:, 0] <= 2.4)
        & (cell_centers[:, 1] >= -0.50)
        & (cell_centers[:, 1] <= 0.50)
        & (cell_centers[:, 2] >= 0.45)
        & (cell_centers[:, 2] <= 1.25)
    )
    submesh = mesh.extract_cells(roi)
    if submesh.n_cells == 0:
        return {"available": False, "reason": "empty diagnostic ROI"}
    gas_core = submesh.threshold(value=0.01, scalars="alpha.water", invert=True, preference="cell")
    if gas_core.n_cells == 0:
        return {
            "available": True,
            "gas_core_cell_count": 0,
            "component_count": 0,
            "headspace_to_mouth_connected": False,
        }
    labeled = gas_core.connectivity(extraction_mode="all", label_regions=True)
    if "RegionId" not in labeled.cell_data:
        return {
            "available": False,
            "reason": "VTK connectivity filter did not produce cell RegionId",
        }
    region_ids = np.asarray(labeled.cell_data["RegionId"], dtype=np.int64)
    gas_centers = np.asarray(labeled.cell_centers().points)
    free_surface = free_surface_z_m if free_surface_z_m is not None else 1.15
    headspace_seed = (
        (gas_centers[:, 0] >= 1.30)
        & (gas_centers[:, 0] <= 1.75)
        & (gas_centers[:, 1] >= -0.30)
        & (gas_centers[:, 1] <= 0.30)
        & (gas_centers[:, 2] >= max(1.20, free_surface + 0.03))
    )
    pipe_radius = float(connection["pipe_radius_m"])
    mouth_seed = (
        (gas_centers[:, 0] >= float(connection["tank_end_x_m"]))
        & (gas_centers[:, 0] <= float(connection["tank_end_x_m"]) + 0.10)
        & (gas_centers[:, 1] >= -pipe_radius)
        & (gas_centers[:, 1] <= pipe_radius)
        & (gas_centers[:, 2] >= float(connection["connection_lower_z_m"]))
        & (gas_centers[:, 2] <= float(connection["connection_upper_z_m"]))
    )
    head_ids = set(region_ids[headspace_seed].tolist())
    mouth_ids = set(region_ids[mouth_seed].tolist())
    shared_ids = sorted(head_ids & mouth_ids)
    return {
        "available": True,
        "alpha_water_threshold": "cell alpha.water <= 0.01",
        "roi_bounds_m": {"x": [1.2, 2.4], "y": [-0.50, 0.50], "z": [0.45, 1.25]},
        "cell_connectivity_method": "VTK connectivity on the thresholded unstructured mesh; point-sharing connectivity is diagnostic only",
        "gas_core_cell_count": int(gas_core.n_cells),
        "component_count": int(np.unique(region_ids).size),
        "headspace_seed_cell_count": int(np.count_nonzero(headspace_seed)),
        "pipe_mouth_seed_cell_count": int(np.count_nonzero(mouth_seed)),
        "headspace_region_ids": sorted(head_ids),
        "pipe_mouth_region_ids": sorted(mouth_ids),
        "shared_region_ids": shared_ids,
        "headspace_to_mouth_connected": bool(shared_ids),
        "headspace_seed_definition": "1.30<=x<=1.75 m, |y|<=0.30 m, z>=max(1.20 m, measured alpha=0.50 level+0.03 m)",
        "pipe_mouth_seed_definition": "first 0.10 m of pipe, |y|<=pipe radius, within the nominal upper/lower port lip bounds",
    }


def current_gas_hotspot(
    mesh: pv.DataSet,
    *,
    x_bounds: tuple[float, float],
    z_bounds: tuple[float, float],
) -> dict[str, float] | None:
    """Find the fastest gas-core cell in the current saved field and ROI."""
    if "U" not in mesh.cell_data or "alpha.water" not in mesh.cell_data:
        return None
    centres = np.asarray(mesh.cell_centers().points, dtype=np.float64)
    velocity = np.asarray(mesh.cell_data["U"], dtype=np.float64)
    alpha = np.asarray(mesh.cell_data["alpha.water"], dtype=np.float64)
    speed = np.linalg.norm(velocity, axis=1)
    roi = (
        np.isfinite(alpha)
        & np.isfinite(speed)
        & (alpha <= 0.01)
        & (centres[:, 0] >= x_bounds[0])
        & (centres[:, 0] <= x_bounds[1])
        & (centres[:, 1] >= -0.50)
        & (centres[:, 1] <= 0.50)
        & (centres[:, 2] >= z_bounds[0])
        & (centres[:, 2] <= z_bounds[1])
    )
    candidates = np.flatnonzero(roi)
    if candidates.size == 0:
        return None
    index = int(candidates[np.argmax(speed[candidates])])
    if speed[index] <= 0.05:
        return None
    x, y, z = centres[index]
    return {
        "x_m": float(x),
        "y_m": float(y),
        "z_m": float(z),
        "alpha_water": float(alpha[index]),
        "speed_m_s": float(speed[index]),
    }


def draw_connection_gas_diagnostic(
    mesh: pv.DataSet,
    *,
    time_s: float,
    free_surface_z_m: float | None,
    connection: dict[str, Any],
    connectivity: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    x_bounds = (1.2, 2.4)
    z_bounds = (0.45, 1.25)
    tank_end = float(connection["tank_end_x_m"])
    lower_z = float(connection["connection_lower_z_m"])
    upper_z = float(connection["connection_upper_z_m"])
    free_z = free_surface_z_m

    fig = plt.figure(figsize=(16.5, 11.5), constrained_layout=True)
    grid = fig.add_gridspec(2, 1, height_ratios=(0.85, 1.25))
    roi_ax = fig.add_subplot(grid[0, 0])
    roi_cut = add_alpha_class_cut(
        roi_ax,
        mesh,
        normal=(0, 1, 0),
        origin=(0, 0, 0),
        axes=(0, 2),
    )
    contour_presence = draw_alpha_contours(roi_ax, roi_cut, axes=(0, 2), levels=(0.01, 0.5, 0.99))
    roi_ax.axvline(tank_end, color="#4a4e69", linestyle="--", linewidth=1.2)
    roi_ax.plot(
        [tank_end, tank_end],
        [lower_z, upper_z],
        color="#9d0208",
        linewidth=3,
        solid_capstyle="butt",
        label="nominal pipe port opening",
    )
    roi_ax.plot(
        [tank_end - 0.035, tank_end + 0.035],
        [lower_z, lower_z],
        color="#9d0208",
        linewidth=1.5,
    )
    roi_ax.plot(
        [tank_end - 0.035, tank_end + 0.035],
        [upper_z, upper_z],
        color="#9d0208",
        linewidth=1.5,
    )
    if free_z is not None:
        roi_ax.hlines(
            free_z,
            x_bounds[0],
            tank_end - 0.05,
            color="#0277bd",
            linestyle=(0, (6, 2)),
            linewidth=1.0,
        )
        roi_ax.annotate(
            f"tank alpha=0.50 level ≈ {free_z:.3f} m at x=1.5 m",
            xy=(1.52, free_z),
            xytext=(1.25, min(z_bounds[1] - 0.08, free_z + 0.11)),
            fontsize=8,
            color="#01579b",
            arrowprops={"arrowstyle": "->", "color": "#0277bd", "lw": 0.8},
        )
    hotspot = current_gas_hotspot(mesh, x_bounds=x_bounds, z_bounds=z_bounds)
    if hotspot is not None:
        projected = (hotspot["x_m"], hotspot["z_m"])
        roi_ax.scatter(
            [projected[0]],
            [projected[1]],
            marker="*",
            s=85,
            facecolor="#f77f00",
            edgecolor="black",
            linewidth=0.6,
            zorder=7,
            label=(f"current gas-core max-speed cell (projected from y={hotspot['y_m']:.3f} m)"),
        )
        roi_ax.annotate(
            f"current |U|={hotspot['speed_m_s']:.1f} m/s, "
            f"αwater={hotspot['alpha_water']:.3g}\n"
            f"(x={hotspot['x_m']:.3f}, y={hotspot['y_m']:.3f}, "
            f"z={hotspot['z_m']:.3f} m)",
            xy=projected,
            xytext=(min(x_bounds[1] - 0.25, projected[0] + 0.12), z_bounds[1] - 0.12),
            fontsize=8,
            color="#6a040f",
            arrowprops={"arrowstyle": "->", "color": "#6a040f", "lw": 0.8},
        )
    roi_ax.set_xlim(*x_bounds)
    roi_ax.set_ylim(*z_bounds)
    roi_ax.set_xlabel("x discharge direction (m)")
    roi_ax.set_ylabel("z upward (m)")
    roi_ax.set_aspect("equal", adjustable="box")
    roi_ax.set_title(
        "Connection detail: y = 0 m; polygons colored by saved cell alpha.water; dashed contours use display interpolation",
        fontsize=10,
    )

    stations = [
        (1.85, "tank before mouth"),
        (1.95, "tank at mouth"),
        (2.00, "tank/pipe interface"),
        (2.05, "pipe entrance"),
        (2.10, "pipe downstream"),
        (2.25, "pipe before valve"),
    ]
    section_axes = grid[1, 0].subgridspec(2, 3, wspace=0.13, hspace=0.30)
    section_presence: dict[str, bool] = {}
    for ax, (x_m, label) in zip(
        (fig.add_subplot(section_axes[row, col]) for row in range(2) for col in range(3)),
        stations,
        strict=True,
    ):
        cut = add_alpha_class_cut(
            ax,
            mesh,
            normal=(1, 0, 0),
            origin=(x_m, 0, 0),
            axes=(1, 2),
        )
        ax.axhline(upper_z, color="#9d0208", linestyle="--", linewidth=0.7)
        ax.axhline(lower_z, color="#9d0208", linestyle="--", linewidth=0.7)
        ax.set_title(f"x = {x_m:.3f} m • {label}", fontsize=8)
        ax.set_xlabel("y cross-stream (m)", fontsize=8)
        ax.set_ylabel("z upward (m)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_xlim(-0.52, 0.52)
        ax.set_ylim(0.45, 1.25)
        ax.set_aspect("equal", adjustable="box")
        section_presence[f"{x_m:.3f}"] = bool(cut.n_cells)

    phase_handles = [
        Patch(facecolor=color, edgecolor="none", label=label)
        for color, label in zip(ALPHA_CLASS_COLORS, ALPHA_CLASS_LABELS, strict=True)
    ]
    contour_handles = [
        Line2D(
            [0], [0], color="#188977", linestyle=(0, (4, 2)), lw=1, label="αwater=0.01 contour*"
        ),
        Line2D([0], [0], color="#d62828", linestyle="-", lw=1, label="αwater=0.50 contour*"),
        Line2D(
            [0], [0], color="#6a4c93", linestyle=(0, (2, 2)), lw=1, label="αwater=0.99 contour*"
        ),
    ]
    fig.legend(
        handles=phase_handles + contour_handles,
        loc="outside lower center",
        ncol=4,
        fontsize=8,
        frameon=True,
    )
    connected = connectivity.get("headspace_to_mouth_connected")
    connection_state = (
        "same αwater≤0.01 3D cell component reaches the headspace and port"
        if connected
        else "no shared αwater≤0.01 headspace-to-port cell component detected"
        if connected is False
        else "3D threshold connectivity unavailable"
    )
    fig.suptitle(
        f"I4F connection gas-ingress diagnostic • exact saved field at t = {time_s:.8g} s\n"
        f"{connection_state}; connectivity is a thresholded mesh diagnostic, not a robustness claim",
        fontsize=12,
    )
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)
    return {
        "image": str(output_path),
        "roi_x_bounds_m": list(x_bounds),
        "roi_z_bounds_m": list(z_bounds),
        "roi_cut_plane_y_m": 0.0,
        "section_x_stations_m": [float(x) for x, _ in stations],
        "section_planes_nonempty": section_presence,
        "cell_native_alpha_classification": ALPHA_CLASS_LABELS,
        "display_contour_levels": [0.01, 0.5, 0.99],
        "display_contour_presence": contour_presence,
        "display_contours_use_cell_to_point_interpolation": True,
        "tank_water_level_alpha_0p5_at_x1p5_m": free_z,
        "nominal_connection_reference": connection,
        "projected_current_gas_core_hot_cell": hotspot,
        "hotspot_selection": (
            "current exact saved field; maximum |U| among cells with alpha.water<=0.01 "
            "inside x=[1.2,2.4] m, y=[-0.5,0.5] m, z=[0.45,1.25] m; projected onto y=0"
        ),
        "gas_core_connectivity": connectivity,
        "interpretation": "visual diagnostic of a numerical pilot; no physical gas-breakthrough robustness is established",
    }


def draw_frame(
    mesh: pv.DataSet,
    *,
    time_s: float,
    field: str,
    field_range: tuple[float, float],
    field_title: str,
    field_cmap: str,
    case_inputs: dict[str, Any],
    geometry: dict[str, Any],
    xz_bounds: tuple[float, float, float, float],
    xy_bounds: tuple[float, float, float, float],
    history: dict[str, list[tuple[float, float]]],
    external_iso_image: Path,
    external_iso_record: dict[str, Any],
    run_label: str | None,
    additional_note: str | None,
    output_path: Path,
) -> dict[str, Any]:
    alpha_range = (0.0, 1.0)
    fig = plt.figure(figsize=(17, 10.2), constrained_layout=True)
    grid = fig.add_gridspec(3, 2, height_ratios=(1.55, 1.15, 1.18), width_ratios=(1.0, 1.0))
    side_ax = fig.add_subplot(grid[0, :])
    plan_ax = fig.add_subplot(grid[1, 0])
    field_ax = fig.add_subplot(grid[1, 1])
    bottom = grid[2, :].subgridspec(1, 2, width_ratios=(0.82, 1.18), wspace=0.08)
    iso_ax = fig.add_subplot(bottom[0, 0])
    history_ax = fig.add_subplot(bottom[0, 1])
    center_y = float(geometry["tank_center_xyz_m"][1])

    side_alpha = add_cell_cut(
        side_ax,
        mesh,
        normal=(0, 1, 0),
        origin=(0, center_y, 0),
        axes=(0, 2),
        field="alpha.water",
        cmap="Blues",
        limits=alpha_range,
    )
    side_cut = mesh.slice(normal=(0, 1, 0), origin=(0, center_y, 0)).triangulate()
    side_iso = alpha_contour(side_cut)
    if side_iso is not None:
        for i in range(side_iso.n_cells):
            cell = side_iso.get_cell(i)
            pts = np.asarray(cell.points)
            if pts.shape[0] >= 2:
                side_ax.plot(pts[:, 0], pts[:, 2], color="#e76f51", lw=0.65, alpha=0.9)
    side_ax.set_title(
        f"Longitudinal cut y = {center_y:g} m • {geometry['tank_axis_label']} • saved cell volume fraction"
        " and $\\alpha_{water}=0.50$ contour"
    )
    side_ax.set_xlabel("x discharge direction (m)")
    side_ax.set_ylabel("z upward (m)")
    side_ax.set_aspect("equal", adjustable="box")
    side_ax.set_xlim(xz_bounds[0], xz_bounds[1])
    side_ax.set_ylim(xz_bounds[2], xz_bounds[3])
    add_stage_annotations(side_ax, case_inputs, geometry)
    fig.colorbar(
        side_alpha,
        ax=side_ax,
        label="saved cell alpha.water (0 = air, 1 = water)",
        fraction=0.025,
        pad=0.012,
    )

    z_cut = float(geometry["nozzle_center_z_m"])
    plan_alpha = add_cell_cut(
        plan_ax,
        mesh,
        normal=(0, 0, 1),
        origin=(0, center_y, z_cut),
        axes=(0, 1),
        field="alpha.water",
        cmap="Blues",
        limits=alpha_range,
    )
    plan_cut = mesh.slice(normal=(0, 0, 1), origin=(0, center_y, z_cut)).triangulate()
    plan_iso = alpha_contour(plan_cut)
    if plan_iso is not None:
        for i in range(plan_iso.n_cells):
            cell = plan_iso.get_cell(i)
            pts = np.asarray(cell.points)
            if pts.shape[0] >= 2:
                plan_ax.plot(pts[:, 0], pts[:, 1], color="#e76f51", lw=0.7, alpha=0.9)
    plan_ax.set_title(f"Horizontal x-y cut at nozzle-center elevation z = {z_cut:g} m")
    plan_ax.set_xlabel("x discharge direction (m)")
    plan_ax.set_ylabel("y cross-stream direction (m)")
    plan_ax.set_aspect("equal", adjustable="box")
    plan_ax.set_xlim(xy_bounds[0], xy_bounds[1])
    plan_ax.set_ylim(xy_bounds[2], xy_bounds[3])
    fig.colorbar(plan_alpha, ax=plan_ax, label="alpha.water", fraction=0.046, pad=0.04)

    field_key = "p" if field == "p" else "speed"
    field_cut = add_cell_cut(
        field_ax,
        mesh,
        normal=(0, 1, 0),
        origin=(0, center_y, 0),
        axes=(0, 2),
        field=field_key,
        cmap=field_cmap,
        limits=field_range,
    )
    # Marking the water interface makes the scalar field interpretable relative
    # to the actual gas-liquid boundary without changing the field itself.
    if side_iso is not None:
        for i in range(side_iso.n_cells):
            cell = side_iso.get_cell(i)
            pts = np.asarray(cell.points)
            if pts.shape[0] >= 2:
                field_ax.plot(pts[:, 0], pts[:, 2], color="#23b6c7", lw=0.55, alpha=0.85)
    field_ax.set_title(
        f"Longitudinal cut y = {center_y:g} m • {field_title} (fixed across rendered times)"
    )
    field_ax.set_xlabel("x discharge direction (m)")
    field_ax.set_ylabel("z upward (m)")
    field_ax.set_aspect("equal", adjustable="box")
    field_ax.set_xlim(xz_bounds[0], xz_bounds[1])
    field_ax.set_ylim(xz_bounds[2], xz_bounds[3])
    fig.colorbar(field_cut, ax=field_ax, label=field_title, fraction=0.046, pad=0.04)
    if field == "speed":
        add_liquid_speed_inset(field_ax, mesh, geometry, xz_bounds)

    iso_ax.imshow(plt.imread(external_iso_image))
    iso_ax.set_axis_off()
    draw_history(history_ax, history, time_s)

    cell_count = int(mesh.n_cells)
    alpha = np.asarray(mesh.cell_data["alpha.water"], dtype=np.float64)
    mixed = int(np.count_nonzero((alpha > 1e-6) & (alpha < 1.0 - 1e-6)))
    time_qualifier = (
        "initialized field; the discharge has not advanced"
        if math.isclose(time_s, 0.0, abs_tol=1e-12)
        else "exact saved OpenFOAM field"
    )
    title = (
        f"I4F hydraulic reference • {geometry['tank_axis_label']} tank • "
        f"{run_label + ' • ' if run_label else ''}"
        f"{time_qualifier} at t = {time_s:.8g} s"
    )
    qualification = "Provisional water/ideal-air • scalar valve loss • no lamellae"
    fig.suptitle(
        f"{title}\n{qualification}",
        fontsize=12,
    )
    fig.savefig(output_path, dpi=170, facecolor="white")
    plt.close(fig)
    return {
        "time_s": float(time_s),
        "tank_axis": geometry["tank_axis"],
        "tank_center_xyz_m": geometry["tank_center_xyz_m"],
        "view_bounds_xz_m": list(xz_bounds),
        "view_bounds_xy_m": list(xy_bounds),
        "cell_count": cell_count,
        "mixed_alpha_cell_count": mixed,
        "external_alpha_0p5_surface": external_iso_record,
        "run_label": run_label,
        "additional_note": additional_note,
        "alpha_color_range": list(alpha_range),
        "field_color_range": [float(v) for v in field_range],
        "liquid_speed_inset": (
            {
                "included": True,
                "field": "speed |U|",
                "mask": "displayed cut cells with interpolated alpha.water >= 0.5",
                "color_range_m_s": [0.0, 25.0],
            }
            if field == "speed"
            else {"included": False}
        ),
    }


def history_sources(case_dir: Path, history: dict[str, list[tuple[float, float]]]) -> list[str]:
    if not history:
        return []
    post = case_dir / "postProcessing"
    found = []
    if post.exists():
        for path in post.rglob("*.dat"):
            if "tankWaterVolume" in path.parts:
                found.append(str(path.relative_to(case_dir)))
        for path in post.rglob("p"):
            if "probes" in path.parts and path.is_file():
                found.append(str(path.relative_to(case_dir)))
    return sorted(found)


def choose_output(path: Path | None) -> Path:
    if path is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = Path("results/runs") / f"i4f-visual-{stamp}"
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.parent.resolve() / path.name
    if path.exists():
        raise ValueError(f"refusing to overwrite existing output bundle: {path}")
    return path


def create_video(
    output_dir: Path,
    frame_paths: list[Path],
    times: list[float],
    *,
    fps: int,
    simulation_seconds_per_video_second: float,
    max_video_frames: int,
) -> tuple[Path, list[int]]:
    if len(set(times)) < 2:
        raise ValueError("MP4 creation requires at least two distinct saved physical times")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for MP4 creation")
    holds = [
        max(1, int(round((right - left) / simulation_seconds_per_video_second * fps)))
        for left, right in zip(times, times[1:])
    ]
    holds.append(1)
    total = sum(holds)
    if total > max_video_frames:
        raise ValueError(
            f"physical-time scaling requires {total} video frames, above --max-video-frames="
            f"{max_video_frames}; increase the limit or change --simulation-seconds-per-video-second"
        )
    sequence = output_dir / "video-frames"
    sequence.mkdir()
    index = 0
    for source, repeat in zip(frame_paths, holds, strict=True):
        for _ in range(repeat):
            destination = sequence / f"frame_{index:06d}.png"
            if index == 0:
                shutil.copyfile(source, destination)
            else:
                # Repeated hard-linking avoids making hundreds of identical PNG
                # copies while ffmpeg still sees a sequential image stream.
                try:
                    destination.hardlink_to(source)
                except OSError:
                    shutil.copyfile(source, destination)
            index += 1
    mp4 = output_dir / "i4f-discharge.mp4"
    pattern = str(sequence / "frame_%06d.png")
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            pattern,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(mp4),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")
    shutil.rmtree(sequence)
    return mp4, holds


def render(args: argparse.Namespace) -> Path:
    case_dir = resolve_case(args.case)
    available = saved_times(case_dir)
    selected = limit_times(requested_times(args.times, available), args.max_frames)
    if args.video == "yes" and len(set(selected)) < 2:
        raise ValueError("--video yes requires at least two distinct saved physical times")
    if args.fps <= 0 or args.max_video_frames <= 0:
        raise ValueError("--fps and --max-video-frames must be positive integers")
    if (
        not math.isfinite(args.simulation_seconds_per_video_second)
        or args.simulation_seconds_per_video_second <= 0
    ):
        raise ValueError("--simulation-seconds-per-video-second must be positive and finite")
    if (args.field_min is None) != (args.field_max is None):
        raise ValueError("provide both --field-min and --field-max, or neither")
    if args.field_min is not None and args.field_max <= args.field_min:
        raise ValueError("--field-max must be greater than --field-min")

    output = choose_output(args.output)
    output.mkdir(parents=True)
    marker = case_dir / "i4f.foam"
    if not marker.is_file():
        marker = next(case_dir.glob("*.foam"))
    reader = pv.OpenFOAMReader(str(marker))
    reader.skip_zero_time = False
    reader.cell_array_status = ["alpha.water", "p", "U"]
    input_path = case_dir.parent / "case-inputs.json"
    if not input_path.is_file():
        input_path = case_dir / "case-inputs.json"
    if input_path.is_file():
        case_inputs = json.loads(input_path.read_text(encoding="utf-8"))
        input_hash = sha256(input_path)
    else:
        case_inputs = {}
        input_hash = None
    first_mesh = active_mesh(reader, selected[0])
    geometry = derive_render_geometry(case_dir, case_inputs, tuple(first_mesh.bounds))
    xz_bounds = validated_view_bounds(
        args.xz_bounds,
        (
            float(first_mesh.bounds[0]),
            float(first_mesh.bounds[1]),
            float(first_mesh.bounds[4]),
            float(first_mesh.bounds[5]),
        ),
        "x-z view",
    )
    xy_bounds = validated_view_bounds(
        args.xy_bounds,
        (
            float(first_mesh.bounds[0]),
            float(first_mesh.bounds[1]),
            float(first_mesh.bounds[2]),
            float(first_mesh.bounds[3]),
        ),
        "x-y view",
    )
    field_range = scalar_range(reader, selected, args.field, args.field_min, args.field_max)
    _, field_title, field_cmap = values_for_field(active_mesh(reader, selected[0]), args.field)
    history, probe_audit = load_history(case_dir, geometry)
    frames_dir = output / "frames"
    frames_dir.mkdir()
    frame_paths: list[Path] = []
    frame_records: list[dict[str, Any]] = []
    connection_diagnostic_records: list[dict[str, Any]] = []
    if args.connection_diagnostic and geometry["tank_axis"] == "vertical":
        raise ValueError(
            "--connection-diagnostic currently uses a horizontal-tank ROI; it is withheld for vertical cases"
        )
    connection_reference = (
        load_connection_reference(case_inputs) if args.connection_diagnostic else None
    )
    for index, time_s in enumerate(selected):
        mesh = active_mesh(reader, time_s)
        frame_path = frames_dir / f"field-{index:05d}-t-{time_s:.9g}s.png"
        outlet_x = float(geometry["nozzle_exit_x_m"])
        iso_path = frames_dir / f"isosurface-{index:05d}-t-{time_s:.9g}s.png"
        iso_record = draw_external_isosurface_image(mesh, outlet_x, time_s, geometry, iso_path)
        iso_record["image"] = str(iso_path.relative_to(output))
        record = draw_frame(
            mesh,
            time_s=time_s,
            field=args.field,
            field_range=field_range,
            field_title=field_title,
            field_cmap=field_cmap,
            case_inputs=case_inputs,
            geometry=geometry,
            xz_bounds=xz_bounds,
            xy_bounds=xy_bounds,
            history=history,
            external_iso_image=iso_path,
            external_iso_record=iso_record,
            run_label=args.run_label,
            additional_note=args.note,
            output_path=frame_path,
        )
        frame_paths.append(frame_path)
        record["image"] = str(frame_path.relative_to(output))
        frame_records.append(record)
        if connection_reference is not None:
            free_surface_z = free_surface_at_x(mesh, 1.5)
            connectivity = gas_core_connectivity(
                mesh,
                free_surface_z_m=free_surface_z,
                connection=connection_reference,
            )
            diagnostic_path = frames_dir / f"connection-gas-ingress-{index:05d}-t-{time_s:.9g}s.png"
            diagnostic_record = draw_connection_gas_diagnostic(
                mesh,
                time_s=time_s,
                free_surface_z_m=free_surface_z,
                connection=connection_reference,
                connectivity=connectivity,
                output_path=diagnostic_path,
            )
            diagnostic_record["image"] = str(diagnostic_path.relative_to(output))
            connection_diagnostic_records.append(diagnostic_record)

    cross_sections = output / "connection-cross-sections.png"
    draw_cross_sections(first_mesh, selected[0], geometry, cross_sections)

    make_video = args.video == "yes" or (args.video == "auto" and len(set(selected)) >= 2)
    video_path: Path | None = None
    holds: list[int] | None = None
    if make_video:
        video_path, holds = create_video(
            output,
            frame_paths,
            selected,
            fps=args.fps,
            simulation_seconds_per_video_second=args.simulation_seconds_per_video_second,
            max_video_frames=args.max_video_frames,
        )

    script_path = Path(__file__).resolve()
    manifest: dict[str, Any] = {
        "schema": "i4f-field-visualization/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "case_directory": str(case_dir),
        "time_selection": "exact saved OpenFOAM times; no temporal interpolation or extrapolation",
        "available_saved_times_s": available,
        "rendered_times_s": selected,
        "video_created": video_path is not None,
        "video_file": str(video_path.relative_to(output)) if video_path else None,
        "video_fps": args.fps if video_path else None,
        "video_frame_holds": holds,
        "simulation_seconds_per_video_second": args.simulation_seconds_per_video_second
        if video_path
        else None,
        "max_field_frames": args.max_frames,
        "selected_field": args.field,
        "run_label": args.run_label,
        "additional_note": args.note,
        "selected_field_units": "Pa absolute" if args.field == "p" else "m s^-1",
        "tank_orientation": geometry["tank_axis_label"],
        "tank_geometry_source": geometry["tank_geometry_source"],
        "tank_axis_vector_xyz": geometry["tank_axis_vector_xyz"],
        "tank_center_xyz_m": geometry["tank_center_xyz_m"],
        "tank_bbox_xyz_m": geometry["tank_bbox_xyz_m"],
        "mesh_derived_bounds_xyz_m": geometry["mesh_bounds_xyz_m"],
        "view_bounds_xz_m": list(xz_bounds),
        "view_bounds_xy_m": list(xy_bounds),
        "nozzle_geometry_source": geometry["nozzle_geometry_source"],
        "nozzle_geometry": {
            "center_yz_m": [geometry["nozzle_center_y_m"], geometry["nozzle_center_z_m"]],
            "width_m": geometry["nozzle_width_m"],
            "height_m": geometry["nozzle_height_m"],
            "exit_x_m": geometry["nozzle_exit_x_m"],
        },
        "field_color_range": [float(v) for v in field_range],
        "field_range_method": "user-specified"
        if args.field_min is not None
        else "global finite extrema over the selected saved times",
        "alpha_water_display_range": [0.0, 1.0],
        "frame_records": frame_records,
        "connection_cross_sections_image": str(cross_sections.relative_to(output)),
        "connection_gas_ingress_diagnostics": connection_diagnostic_records,
        "history_sources": history_sources(case_dir, history),
        "history_data_available": bool(history),
        "history_series": sorted(history),
        "pressure_probe_location_audit": probe_audit,
        "history_plot_definition": {
            "tank_water_drawdown_m3": "first saved tankWaterVolume minus current saved tankWaterVolume",
            "pressure_Pa": "absolute pressure p from saved postProcessing/probes/p time series; only probes checked inside the tank, downstream centerline, or external domain are plotted",
            "far_domain_exit_flux": "not plotted as nozzle discharge; the OpenFOAM patch named outlet is the far external-domain exit near x=6.5 m",
        },
        "case_inputs_sha256": input_hash,
        "legacy_analysis_config_sha256": geometry["legacy_analysis_config_sha256"],
        "renderer_sha256": sha256(script_path),
        "qualifications": [
            "Water/ideal-air hydraulic reference only; no CO2 thermodynamics, dissolution, foam, or retardant rheology.",
            "All unconfirmed apparatus dimensions and material inputs are provisional.",
            "Valve is a scalar loss zone; it is not a resolved butterfly disk and cannot show a disk wake.",
            "Five reported lamellae are omitted because their orientation and geometry are unresolved.",
            "The alpha.water=0.50 display surface/contours use cell-to-point interpolation for display only.",
            "No bubble particles or foam structures are synthesized.",
            "Nozzle discharge flow is not inferred from the far external-domain outlet patch; history plots tank-zone volume drawdown and recorded absolute-pressure probes.",
            "Tank axis and position come from saved case geometry or the archived analysis configuration for legacy cases; probe histories are plotted only after coordinate checks against that geometry.",
        ],
    }
    if args.note:
        manifest["qualifications"].append(args.note)
    (output / "render-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    label_record = f"Run label: {args.run_label}.\n\n" if args.run_label else ""
    note_record = f"Run qualification: {args.note}\n\n" if args.note else ""
    (output / "README.md").write_text(
        "# I4F saved-field visualization\n\n"
        f"Rendered exact saved times: {', '.join(f'{t:g} s' for t in selected)}.\n\n"
        f"{label_record}{note_record}"
        "The visual uses the saved OpenFOAM `alpha.water` and pressure or velocity field. "
        "A computed external alpha=0.50 surface is shown when it exists; a static initialized "
        "field does not imply discharge. The red/teal alpha contours are display contours "
        "derived from the saved volume fraction. Valve restriction is scalar, and the five "
        "reported lamellae are not in this reference mesh. This is a water/ideal-air hydraulic "
        "reference, not an assessment of foam, CO2, or retardant behavior. The case patch named "
        "`outlet` is the far external-domain exit and is not interpreted as nozzle discharge.\n\n"
        "See `render-manifest.json` for exact time directories, field scale, hashes and limitations.\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        type=Path,
        required=True,
        help="OpenFOAM case directory or run bundle containing case/",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="new, nonexisting output bundle; default is timestamped results/runs/i4f-visual-*",
    )
    parser.add_argument(
        "--times",
        help="comma-separated exact saved physical times in seconds; default renders all available times",
    )
    parser.add_argument(
        "--field",
        choices=("p", "speed"),
        default="p",
        help="scalar cut field: absolute pressure Pa or speed m/s",
    )
    parser.add_argument(
        "--field-min",
        type=float,
        help="fixed lower color-scale bound in the selected field's SI units",
    )
    parser.add_argument(
        "--field-max",
        type=float,
        help="fixed upper color-scale bound in the selected field's SI units",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=24,
        help="maximum distinct saved-time snapshots rendered; selected times are evenly spaced",
    )
    parser.add_argument(
        "--xz-bounds",
        type=float,
        nargs=4,
        metavar=("XMIN", "XMAX", "ZMIN", "ZMAX"),
        help="fixed longitudinal x-z view bounds in metres, useful for a common orientation comparison",
    )
    parser.add_argument(
        "--xy-bounds",
        type=float,
        nargs=4,
        metavar=("XMIN", "XMAX", "YMIN", "YMAX"),
        help="fixed plan x-y view bounds in metres, useful for a common orientation comparison",
    )
    parser.add_argument(
        "--video",
        choices=("auto", "yes", "no"),
        default="auto",
        help="auto writes MP4 only with at least two saved times",
    )
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument(
        "--simulation-seconds-per-video-second",
        type=float,
        default=0.05,
        help="physical-time scale for holding saved frames; default 0.05 simulated seconds per video second",
    )
    parser.add_argument(
        "--max-video-frames",
        type=int,
        default=1800,
        help="hard limit on repeated frames used to represent physical time",
    )
    parser.add_argument("--run-label", help="short label added to each frame, e.g. NUMERICAL PILOT")
    parser.add_argument(
        "--note", help="explicit per-run qualification shown in each frame and manifest"
    )
    parser.add_argument(
        "--connection-diagnostic",
        action="store_true",
        help="add a close tank/pipe alpha.water and thresholded gas-connectivity diagnostic",
    )
    args = parser.parse_args()
    try:
        output = render(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"render_i4f_discharge: {error}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
