#!/usr/bin/env python3
"""Render exploratory Rouaix VOF fields with CPU Mitsuba participating media.

The dilute alpha.water band is an inferred spray-equivalent optical proxy;
alpha.water is not a droplet-size or number-density measurement. The alpha=.5
surface is a separate display geometry for coherent bulk liquid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_interface_wave_flux import (  # noqa: E402
    EXPECTED_ALPHA_DIMENSIONS,
    read_volume_scalar_field,
)

WATER_CASE = ROOT / "results/runs/recovery-air-only-20261015T201744Z-water-C-gradlim/case"
MESH_CASE = ROOT / "results/runs/rouaix-c4-adaptive-1p5-20261006T1049Z/case"
DEFAULT_RUN = ROOT / "results/runs/rouaix-mitsuba-20261016"
DEFAULT_SUMMARY = ROOT / "results/summaries/rouaix_mitsuba_20261016"
CELL_COUNT = 2_733_120
RHO_WATER_KG_M3 = 997.6
ALPHA_SURFACE = 0.5
SPRAY_ALPHA_MAX = 0.1
Q_EXT = 2.0
SINGLE_SCATTER_ALBEDO = 0.999
ASYMMETRY_G = 0.85


@dataclass(frozen=True)
class StructuredCoordinates:
    x_m: np.ndarray
    y_m: np.ndarray
    z_by_y_m: np.ndarray
    ix: np.ndarray
    iy: np.ndarray
    iz: np.ndarray
    shape_yxz: tuple[int, int, int]


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def read_vector_internal(path: Path, expected_cells: int) -> np.ndarray:
    """Read an ASCII OpenFOAM volVectorField internalField in cell order."""
    text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    dimensions = re.search(r"\bdimensions\s*\[([^\]]+)\]\s*;", text)
    if dimensions is None:
        raise ValueError(f"{path}: missing dimensions")
    dim_tuple = tuple(int(token) for token in dimensions.group(1).split())
    if dim_tuple != (0, 1, 0, 0, 0, 0, 0):
        raise ValueError(f"{path}: expected length dimensions, got {dim_tuple}")
    pattern = r"\binternalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;"
    match = re.search(pattern, text, flags=re.DOTALL)
    if match is None:
        raise ValueError(f"{path}: expected a nonuniform vector internalField")
    count = int(match.group(1))
    values = np.fromstring(match.group(2).replace("(", " ").replace(")", " "), sep=" ")
    if count != expected_cells or values.size != 3 * count:
        raise ValueError(f"{path}: expected {expected_cells} vectors, found {count}")
    return values.reshape((count, 3))


def structured_coordinates(centres_xyz_m: np.ndarray) -> StructuredCoordinates:
    """Map cell-order coordinates to the native y,x,z structured lattice."""
    xyz = np.round(np.asarray(centres_xyz_m, dtype=np.float64), 8)
    x = np.unique(xyz[:, 0])
    y = np.unique(xyz[:, 1])
    if not x.size or not y.size or xyz.shape[0] % (x.size * y.size):
        raise ValueError("native cell centres are not a regular y,x,z lattice")
    nz = xyz.shape[0] // (x.size * y.size)
    ix = np.searchsorted(x, xyz[:, 0])
    iy = np.searchsorted(y, xyz[:, 1])
    z_by_y = np.empty((y.size, nz), dtype=np.float64)
    iz = np.empty(len(xyz), dtype=np.int64)
    for iy_row in range(y.size):
        rows = np.flatnonzero(iy == iy_row)
        levels = np.unique(xyz[rows, 2])
        if levels.size != nz or rows.size != x.size * nz:
            raise ValueError(f"y row {iy_row} does not contain a complete structured plane")
        z_by_y[iy_row] = levels
        iz[rows] = np.searchsorted(levels, xyz[rows, 2])
        if np.unique(ix[rows] * nz + iz[rows]).size != len(rows):
            raise ValueError(f"y row {iy_row} contains duplicate x,z locations")
    flat_index = (iy * x.size + ix) * nz + iz
    if np.unique(flat_index).size != len(xyz):
        raise ValueError("native coordinates do not map one-to-one to structured cells")
    return StructuredCoordinates(x, y, z_by_y, ix, iy, iz, (len(y), len(x), nz))


def structured_values(values: np.ndarray, coordinates: StructuredCoordinates) -> np.ndarray:
    """Return native cell values in [y,x,z] layout, without interpolation."""
    result = np.empty(coordinates.shape_yxz, dtype=np.float64)
    result[coordinates.iy, coordinates.ix, coordinates.iz] = np.asarray(values)
    return result


def _cell_center_support(axis: np.ndarray) -> tuple[float, float]:
    """Estimate outer face bounds from sorted cell centers and local end spacing."""
    if axis.size < 2:
        raise ValueError("at least two cell centers are needed to estimate outer faces")
    return (
        float(axis[0] - 0.5 * (axis[1] - axis[0])),
        float(axis[-1] + 0.5 * (axis[-1] - axis[-2])),
    )


def resample_to_uniform_box(
    values_yxz: np.ndarray,
    coordinates: StructuredCoordinates,
    bounds_xyz_m: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    dimensions_xyz: tuple[int, int, int],
) -> np.ndarray:
    """Linearly sample native cell-centred data onto a uniform [z,y,x] grid.

    Native z cell-centres vary by y. We interpolate x,z within each native y
    plane, then interpolate between adjacent y planes. Samples outside the
    native cell-centre support are set to zero. Resampling is display-only.
    """
    try:
        from scipy.interpolate import RegularGridInterpolator
    except ImportError as error:  # pragma: no cover - dependency has an extra
        raise RuntimeError("install the physical-rendering extra to resample fields") from error

    nx, ny, nz = dimensions_xyz
    (x0, x1), (y0, y1), (z0, z1) = bounds_xyz_m
    if min(nx, ny, nz) < 2 or not (x0 < x1 and y0 < y1 and z0 < z1):
        raise ValueError("invalid uniform volume bounds or dimensions")
    tx = np.linspace(x0, x1, nx, endpoint=False) + (x1 - x0) / (2 * nx)
    ty = np.linspace(y0, y1, ny, endpoint=False) + (y1 - y0) / (2 * ny)
    tz = np.linspace(z0, z1, nz, endpoint=False) + (z1 - z0) / (2 * nz)
    xx, zz = np.meshgrid(tx, tz, indexing="xy")
    sample_points = np.column_stack((xx.ravel(), zz.ravel()))

    plane_interpolators = [
        RegularGridInterpolator(
            (coordinates.x_m, coordinates.z_by_y_m[j]),
            values_yxz[j],
            method="linear",
            bounds_error=False,
            fill_value=0.0,
        )
        for j in range(len(coordinates.y_m))
    ]
    samples_zyx = np.zeros((nz, ny, nx), dtype=np.float32)
    for out_j, y_value in enumerate(ty):
        if y_value < coordinates.y_m[0] or y_value > coordinates.y_m[-1]:
            continue
        j1 = int(np.searchsorted(coordinates.y_m, y_value, side="right"))
        j0 = max(0, j1 - 1)
        j1 = min(j1, len(coordinates.y_m) - 1)
        if j0 == j1:
            weight = 0.0
        else:
            weight = (y_value - coordinates.y_m[j0]) / (coordinates.y_m[j1] - coordinates.y_m[j0])
        lower = plane_interpolators[j0](sample_points).reshape((nz, nx))
        if j0 == j1:
            plane = lower
        else:
            upper = plane_interpolators[j1](sample_points).reshape((nz, nx))
            plane = (1.0 - weight) * lower + weight * upper
        samples_zyx[:, out_j, :] = plane
    return samples_zyx


def liquid_volume_integral(alpha: np.ndarray, cell_volumes_m3: np.ndarray) -> float:
    return float(np.sum(np.asarray(alpha, dtype=np.float64) * cell_volumes_m3, dtype=np.float64))


def sigma_t_from_alpha(alpha: np.ndarray, d32_m: float, q_ext: float = Q_EXT) -> np.ndarray:
    """Independent-sphere dilute-droplet extinction coefficient in inverse metres."""
    if not math.isfinite(d32_m) or d32_m <= 0 or not math.isfinite(q_ext) or q_ext < 0:
        raise ValueError("D32 must be positive and Qext nonnegative")
    return (1.5 * q_ext / d32_m) * np.asarray(alpha, dtype=np.float64)


def _load_mitsuba(threads: int) -> tuple[Any, Any]:
    try:
        import drjit as dr
        import mitsuba as mi
    except ImportError as error:  # pragma: no cover - dependency has an extra
        raise RuntimeError("install the physical-rendering extra to use Mitsuba") from error
    dr.set_thread_count(threads)
    mi.set_variant("llvm_ad_rgb")
    return dr, mi


def _uniform_grid_volume(mi: Any, samples_zyx: np.ndarray, bounds_xyz_m: Any) -> Any:
    (x0, x1), (y0, y1), (z0, z1) = bounds_xyz_m
    transform = mi.ScalarTransform4f().translate([x0, y0, z0]).scale([x1 - x0, y1 - y0, z1 - z0])
    return mi.load_dict(
        {
            "type": "gridvolume",
            "grid": mi.VolumeGrid(np.ascontiguousarray(samples_zyx, dtype=np.float32)),
            "raw": True,
            "to_world": transform,
            "filter_type": "trilinear",
        }
    )


def _fit_camera(
    bounds_xyz_m: Any,
    width: int,
    height: int,
    fov_degrees: float = 34.0,
) -> dict[str, Any]:
    """Fit all eight crop corners in perspective using a fixed viewing direction."""
    (x0, x1), (y0, y1), (z0, z1) = bounds_xyz_m
    target = np.array([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2], dtype=np.float64)
    direction = np.array([0.38, 0.20, 1.0], dtype=np.float64)
    direction /= np.linalg.norm(direction)
    world_up = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    right = np.cross(world_up, direction)
    right /= np.linalg.norm(right)
    up = np.cross(direction, right)
    tan_x = math.tan(math.radians(fov_degrees) / 2)
    tan_y = tan_x * height / width
    corners = np.array(
        [[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)],
        dtype=np.float64,
    )
    relative = corners - target
    depth_from_target = relative @ direction
    horizontal = np.abs(relative @ right)
    vertical = np.abs(relative @ up)
    required = np.maximum(
        depth_from_target + horizontal / tan_x, depth_from_target + vertical / tan_y
    )
    distance = float(np.max(required) * 1.08 + 0.05)
    origin = target + distance * direction
    return {
        "origin_m": origin.tolist(),
        "target_m": target.tolist(),
        "direction_from_target": direction.tolist(),
        "distance_m": distance,
        "fov_degrees": fov_degrees,
        "aspect": width / height,
        "fit_margin_fraction": 0.08,
        "all_crop_corners_in_frustum": True,
    }


def voxel_center_world_coordinate(
    bounds_xyz_m: Any, dimensions_xyz: tuple[int, int, int], index_xyz: tuple[int, int, int]
) -> tuple[float, float, float]:
    """Return the world coordinate Mitsuba assigns to a grid voxel centre."""
    result = []
    for (lower, upper), count, index in zip(bounds_xyz_m, dimensions_xyz, index_xyz, strict=True):
        if not 0 <= index < count:
            raise IndexError(index)
        result.append(lower + (index + 0.5) * (upper - lower) / count)
    return tuple(result)


def _structured_surface_ply(
    alpha_zyx: np.ndarray,
    bounds_xyz_m: Any,
    out_path: Path,
    level: float = ALPHA_SURFACE,
) -> dict[str, Any]:
    try:
        import pyvista as pv
    except ImportError as error:  # pragma: no cover - dependency has an extra
        raise RuntimeError(
            "install the visualization extra to extract the alpha surface"
        ) from error
    nz, ny, nx = alpha_zyx.shape
    (x0, x1), (y0, y1), (z0, z1) = bounds_xyz_m
    spacing = ((x1 - x0) / nx, (y1 - y0) / ny, (z1 - z0) / nz)
    origin = (x0 + spacing[0] / 2, y0 + spacing[1] / 2, z0 + spacing[2] / 2)
    image = pv.ImageData(dimensions=(nx, ny, nz), spacing=spacing, origin=origin)
    # C-order flattening of [z,y,x] gives VTK's x-fast point order.
    image.point_data["alpha.water"] = np.ascontiguousarray(alpha_zyx).ravel(order="C")
    surface = image.contour([level], scalars="alpha.water")
    if surface.n_points == 0 or surface.n_cells == 0:
        raise ValueError(f"alpha={level} surface is empty in the selected crop")
    open_edges_before = surface.extract_feature_edges(
        feature_edges=False,
        boundary_edges=True,
        manifold_edges=False,
        non_manifold_edges=False,
    ).n_cells
    if open_edges_before:
        # The selected field touches the open inlet plane. Capping that boundary
        # closes the display-only dielectric solid so refraction has a valid
        # inside/outside surface. The cap is not part of the computed VOF field.
        surface = surface.fill_holes(10.0)
    open_edges_after = surface.extract_feature_edges(
        feature_edges=False,
        boundary_edges=True,
        manifold_edges=False,
        non_manifold_edges=False,
    ).n_cells
    if open_edges_after:
        raise ValueError(
            f"alpha surface remains open after source-plane cap ({open_edges_after} edges)"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    surface.save(out_path, binary=True)
    _sanitize_ply_header(out_path)
    return {
        "point_count": int(surface.n_points),
        "triangle_count": int(surface.n_cells),
        "boundary_edges_before_source_cap": int(open_edges_before),
        "boundary_edges_after_cap": int(open_edges_after),
        "crop_boundary_cap": "VTK fill_holes on alpha=.5 isosurface; display-only closure of inlet/crop openings",
        "bounds_m_xyz": [[float(v) for v in pair] for pair in bounds_xyz_m],
        "level": level,
        "point_location_convention": "uniform voxel centers; VTK points at first center plus integer spacing",
    }


def _sanitize_ply_header(path: Path) -> None:
    """Remove VTK's nonstandard obj_info line for Mitsuba's PLY parser."""
    content = path.read_bytes()
    marker = b"end_header"
    if marker not in content:
        raise ValueError(f"invalid PLY emitted by VTK: no end_header in {path}")
    header, payload = content.split(marker, maxsplit=1)
    lines = [line for line in header.splitlines() if not line.startswith(b"obj_info")]
    path.write_bytes(b"\n".join(lines) + b"\n" + marker + payload)


def _mitsuba_scene(
    mi: Any,
    volume: Any,
    surface_path: Path,
    bounds_xyz_m: Any,
    d32_m: float,
    width: int,
    height: int,
    spp: int,
    bulk_material: str = "dielectric",
) -> Any:
    (x0, x1), (y0, y1), (z0, z1) = bounds_xyz_m
    volume_shape = {
        "type": "cube",
        "to_world": mi.ScalarTransform4f()
        .translate([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
        .scale([(x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2]),
        "bsdf": {"type": "null"},
        "interior": {
            "type": "heterogeneous",
            "sigma_t": volume,
            "scale": 1.5 * Q_EXT / d32_m,
            "albedo": SINGLE_SCATTER_ALBEDO,
            "phase": {"type": "hg", "g": ASYMMETRY_G},
        },
    }
    if bulk_material == "dielectric":
        bulk_bsdf = {"type": "dielectric", "int_ior": 1.333, "ext_ior": 1.000277}
    elif bulk_material == "matte-blue":
        bulk_bsdf = {
            "type": "diffuse",
            "reflectance": {"type": "rgb", "value": [0.07, 0.28, 0.65]},
        }
    else:
        raise ValueError(f"unsupported bulk display material: {bulk_material}")
    surface_shape = {
        "type": "ply",
        "filename": str(surface_path),
        "bsdf": bulk_bsdf,
    }
    fit = _fit_camera(bounds_xyz_m, width, height)
    target = fit["target_m"]
    camera = fit["origin_m"]
    up = [0.0, 1.0, 0.0]  # gravity is -y in Rouaix coordinates
    sensor = {
        "type": "perspective",
        "fov": 34.0,
        "near_clip": 0.01,
        "far_clip": 100.0,
        "to_world": mi.ScalarTransform4f.look_at(origin=camera, target=target, up=up),
        "sampler": {"type": "independent", "sample_count": spp},
        "film": {
            "type": "hdrfilm",
            "width": width,
            "height": height,
            "rfilter": {"type": "tent"},
        },
    }
    key_origin = [target[0] - 2.0, target[1] + 3.0, target[2] + 1.5]
    key_transform = mi.ScalarTransform4f.look_at(
        origin=key_origin, target=target, up=[0.0, 1.0, 0.0]
    ).scale([2.0, 2.0, 1.0])
    return mi.load_dict(
        {
            "type": "scene",
            "integrator": {"type": "volpath", "max_depth": -1, "rr_depth": 8},
            "sensor": sensor,
            "environment": {
                "type": "constant",
                "radiance": {"type": "rgb", "value": [0.4, 0.5, 0.8]},
            },
            "broad-key-light": {
                "type": "rectangle",
                "to_world": key_transform,
                "emitter": {
                    "type": "area",
                    "radiance": {"type": "rgb", "value": [3.0, 3.0, 3.0]},
                },
            },
            "volume-boundary": volume_shape,
            "alpha-half-surface": surface_shape,
        }
    )


def _linear_to_srgb(values: np.ndarray) -> np.ndarray:
    values = np.maximum(values, 0.0)
    return np.where(values <= 0.0031308, 12.92 * values, 1.055 * values ** (1 / 2.4) - 0.055)


def _label_image(
    rgb_linear: np.ndarray,
    out_path: Path,
    time_text: str,
    d32_m: float,
    exposure: float,
    bulk_material: str = "dielectric",
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    mapped = 1.0 - np.exp(-np.maximum(rgb_linear, 0.0) * exposure)
    srgb = np.clip(_linear_to_srgb(mapped), 0.0, 1.0)
    image = Image.fromarray(np.asarray(np.round(srgb * 255), dtype=np.uint8), mode="RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    font = (
        ImageFont.truetype(str(font_path), max(10, min(18, image.width // 40)))
        if font_path.is_file()
        else ImageFont.load_default()
    )
    surface_label = (
        "alpha=.5 water dielectric; 0<alpha<.1 inferred spray proxy"
        if bulk_material == "dielectric"
        else "alpha=.5 matte-blue display; 0<alpha<.1 inferred spray proxy"
    )
    lines_in = [
        f"Rouaix volpath | t={time_text} s | D32={d32_m * 1000:g} mm",
        surface_label,
        "Near-field | exploratory attempt, not validated",
    ]
    pad = max(6, image.width // 100)
    max_width = image.width - 2 * pad
    lines: list[str] = []
    for line in lines_in:
        current = ""
        for word in line.split():
            candidate = f"{current} {word}".strip()
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    line_height = font.getbbox("Ag")[3] + 3
    block_height = pad * 2 + line_height * len(lines)
    draw.rectangle((0, 0, image.width, block_height), fill=(5, 12, 20, 190))
    for index, line in enumerate(lines):
        draw.text((pad, pad + index * line_height), line, font=font, fill=(243, 247, 250, 255))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, optimize=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mesh_field_order_comparison(field_case: Path, mesh_case: Path) -> dict[str, Any]:
    """Require identical native mesh/addressing before borrowing C and V fields."""
    names = ("points", "faces", "owner", "neighbour", "boundary")
    field_mesh = field_case / "constant" / "polyMesh"
    source_mesh = mesh_case / "constant" / "polyMesh"
    comparison = {
        name: {
            "field_case_sha256": _sha256(field_mesh / name),
            "coordinate_source_sha256": _sha256(source_mesh / name),
        }
        for name in names
    }
    mismatches = [
        name
        for name, hashes in comparison.items()
        if hashes["field_case_sha256"] != hashes["coordinate_source_sha256"]
    ]
    if mismatches:
        raise ValueError(f"fresh-start mesh does not match coordinate-source mesh: {mismatches}")
    return comparison


def _frame_manifest(
    field_path: Path,
    alpha_native: np.ndarray,
    native_centres_xyz_m: np.ndarray,
    volumes_m3: np.ndarray,
    alpha_uniform: np.ndarray,
    bounds_xyz_m: Any,
) -> dict[str, Any]:
    (x0, x1), (y0, y1), (z0, z1) = bounds_xyz_m
    inside = (
        np.isfinite(alpha_native)
        & (native_centres_xyz_m[:, 0] >= x0)
        & (native_centres_xyz_m[:, 0] <= x1)
        & (native_centres_xyz_m[:, 1] >= y0)
        & (native_centres_xyz_m[:, 1] <= y1)
        & (native_centres_xyz_m[:, 2] >= z0)
        & (native_centres_xyz_m[:, 2] <= z1)
    )
    crop_native = liquid_volume_integral(alpha_native[inside], volumes_m3[inside])
    voxel_volume = (
        ((x1 - x0) / alpha_uniform.shape[2])
        * ((y1 - y0) / alpha_uniform.shape[1])
        * ((z1 - z0) / alpha_uniform.shape[0])
    )
    crop_uniform = float(np.sum(alpha_uniform, dtype=np.float64) * voxel_volume)
    return {
        "field_path": str(field_path.relative_to(ROOT)),
        "field_sha256": _sha256(field_path),
        "native_cells_inside_crop": int(inside.sum()),
        "native_liquid_volume_inside_crop_m3": crop_native,
        "uniform_resampled_liquid_volume_inside_crop_m3": crop_uniform,
        "uniform_over_native_crop_integral": crop_uniform / crop_native if crop_native else None,
        "alpha_native_minmax": [float(np.min(alpha_native)), float(np.max(alpha_native))],
        "alpha_clipped_cell_count": int(np.count_nonzero((alpha_native < 0) | (alpha_native > 1))),
        "resampled_shape_zyx": list(alpha_uniform.shape),
    }


def _render_pregridded_npz(args: argparse.Namespace) -> dict[str, Any]:
    """Render a portable display grid without access to the original CFD case."""
    import shutil
    import time

    npz_path = args.grid_npz.resolve()
    metadata_path = (
        args.grid_metadata.resolve() if args.grid_metadata else npz_path.with_name("metadata.json")
    )
    if not npz_path.is_file():
        raise FileNotFoundError(npz_path)
    if not metadata_path.is_file():
        raise FileNotFoundError(f"source metadata sidecar not found: {metadata_path}")
    with np.load(npz_path) as archive:
        if not {"alpha_zyx", "bounds_m"}.issubset(archive.files):
            raise ValueError("pregridded NPZ must contain alpha_zyx and bounds_m")
        alpha = np.asarray(archive["alpha_zyx"], dtype=np.float32)
        bounds_values = np.asarray(archive["bounds_m"], dtype=np.float64)
    if alpha.ndim != 3 or min(alpha.shape) < 2 or not np.all(np.isfinite(alpha)):
        raise ValueError("alpha_zyx must be a finite three-dimensional grid")
    if np.min(alpha) < 0 or np.max(alpha) > 1:
        raise ValueError("pregridded alpha values must already be within [0,1]")
    if bounds_values.shape != (6,):
        raise ValueError("bounds_m must contain xmin,xmax,ymin,ymax,zmin,zmax")
    bounds = (
        (float(bounds_values[0]), float(bounds_values[1])),
        (float(bounds_values[2]), float(bounds_values[3])),
        (float(bounds_values[4]), float(bounds_values[5])),
    )
    sidecar = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = sidecar.get("source", {})
    if abs(float(source.get("time_s", args.time_s)) - float(args.time_s)) > 1e-6:
        raise ValueError("--time-s does not match the time recorded in the source sidecar")

    portable_npz = args.summary_dir / "rouaix-legacy-t1p5-alpha-zyx.npz"
    portable_sidecar = args.summary_dir / "rouaix-legacy-t1p5-source-metadata.json"
    hero = args.summary_dir / f"rouaix-{args.artifact_prefix}-t1p5.png"
    manifest_path = args.summary_dir / f"{args.artifact_prefix}-manifest.json"
    for source_path, destination in (
        (npz_path, portable_npz),
        (metadata_path, portable_sidecar),
    ):
        if (
            destination.exists()
            and destination.resolve() != source_path.resolve()
            and _sha256(destination) != _sha256(source_path)
        ):
            raise FileExistsError(
                f"refusing to replace different portable source asset: {destination}"
            )
    for destination in (hero, manifest_path):
        if destination.exists():
            raise FileExistsError(f"refusing to replace existing render output: {destination}")

    dr, mi = _load_mitsuba(args.threads)
    dilute = np.where((alpha > 0.0) & (alpha < SPRAY_ALPHA_MAX), alpha, 0.0).astype(np.float32)
    volume = _uniform_grid_volume(mi, dilute, bounds)
    surface_path = args.run_dir / "legacy-alpha-half-surface.ply"
    surface = _structured_surface_ply(alpha, bounds, surface_path)
    camera_fit = _fit_camera(bounds, args.width, args.height)
    started = time.perf_counter()
    scene = _mitsuba_scene(
        mi,
        volume,
        surface_path,
        bounds,
        args.d32_mm * 1e-3,
        args.width,
        args.height,
        args.spp,
        bulk_material=args.bulk_material,
    )
    rendered = np.asarray(mi.render(scene, spp=args.spp), dtype=np.float32)
    elapsed = time.perf_counter() - started
    np.save(args.run_dir / "legacy-linear-rgb.npy", rendered)
    rendered_path = args.run_dir / "legacy-multiple-scattering.png"
    _label_image(
        rendered,
        rendered_path,
        args.time_s,
        args.d32_mm * 1e-3,
        args.exposure,
        args.bulk_material,
    )

    if npz_path.resolve() != portable_npz.resolve():
        shutil.copy2(npz_path, portable_npz)
    if metadata_path.resolve() != portable_sidecar.resolve():
        shutil.copy2(metadata_path, portable_sidecar)
    shutil.copy2(rendered_path, hero)
    voxel_volume = float(
        np.prod([(bounds[i][1] - bounds[i][0]) / alpha.shape[2 - i] for i in range(3)])
    )
    uniform_volume = float(np.sum(alpha, dtype=np.float64) * voxel_volume)
    native_crop_volume = float(
        sidecar.get("liquid_volume_accounting", {}).get(
            "native_cell_center_in_crop_alpha_times_V_m3", 0.0
        )
    )
    record = {
        "time_s": float(args.time_s),
        "field_path": source.get("alpha_field_resolved"),
        "field_sha256": source.get("alpha_water_sha256"),
        "npz_sha256": _sha256(npz_path),
        "portable_npz": str(portable_npz.relative_to(ROOT)),
        "portable_npz_sha256": _sha256(portable_npz),
        "portable_source_metadata": str(portable_sidecar.relative_to(ROOT)),
        "portable_source_metadata_sha256": _sha256(portable_sidecar),
        "native_liquid_volume_inside_crop_m3": native_crop_volume,
        "uniform_resampled_liquid_volume_inside_crop_m3": uniform_volume,
        "uniform_over_native_crop_integral": uniform_volume / native_crop_volume
        if native_crop_volume
        else None,
        "alpha_minmax": [float(np.min(alpha)), float(np.max(alpha))],
        "alpha_clipped_cell_count": 0,
        "resampled_shape_zyx": list(alpha.shape),
        "bounds_xyz_m": [[float(v) for v in pair] for pair in bounds],
        "surface": surface,
        "render": {
            "variant": str(mi.variant()),
            "mitsuba_version": getattr(mi, "__version__", "unknown"),
            "drjit_version": getattr(dr, "__version__", "unknown"),
            "python_version": sys.version.split()[0],
            "integrator": "volpath; multiple scattering with Russian roulette after depth 8; no finite max depth",
            "resolution_px": [args.width, args.height],
            "spp": args.spp,
            "threads": args.threads,
            "wall_seconds": elapsed,
            "exposure": args.exposure,
            "bulk_surface_material": args.bulk_material,
            "tonemap": "linear HDR, exposure multiplier, exponential shoulder, then sRGB",
            "linear_rgb_finite_fraction": float(np.mean(np.isfinite(rendered))),
            "camera_fit": camera_fit,
        },
        "output_png": str(hero.relative_to(ROOT)),
        "output_png_sha256": _sha256(hero),
        "output_png_bytes": hero.stat().st_size,
    }
    manifest = {
        "schema_version": 1,
        "task": "Portable CPU Mitsuba legacy Rouaix near-field crop, exploratory optical interpretation",
        "source_metadata": str(portable_sidecar.relative_to(ROOT)),
        "optical_interpretation": {
            "coherent_bulk": (
                "alpha.water=0.5 isosurface rendered as a dielectric water/air interface; geometry is display-only"
                if args.bulk_material == "dielectric"
                else "alpha.water=0.5 isosurface rendered with a matte-blue diffuse display material; this is deliberately nonphysical and geometry is display-only"
            ),
            "dilute_medium": "only 0 < alpha.water < 0.1 is used as an inferred spray-equivalent optical proxy; not a measured droplet population",
            "extinction_equation": "sigma_t [m^-1] = 1.5 Qext alpha / D32",
            "D32_m": args.d32_mm * 1e-3,
            "Qext": Q_EXT,
            "Qsca_over_Qext": SINGLE_SCATTER_ALBEDO,
            "HG_g": ASYMMETRY_G,
            "assumption_status": "illustrative geometric-optics Qext≈2, albedo and g assumptions; alpha is not a droplet-size or number-density measurement",
            "alpha_mask": (
                "display inference: 0 < alpha < 0.1 dilute medium; alpha=0.5 dielectric isosurface"
                if args.bulk_material == "dielectric"
                else "display inference: 0 < alpha < 0.1 dilute medium; alpha=0.5 matte-blue nonphysical surface"
            ),
            "bulk_surface_material": args.bulk_material,
        },
        "render_settings": {
            "backend": "Mitsuba 3 llvm_ad_rgb CPU",
            "software_versions": {
                "mitsuba": getattr(mi, "__version__", "unknown"),
                "drjit": getattr(dr, "__version__", "unknown"),
                "python": sys.version.split()[0],
            },
            "environment": {
                "type": "constant",
                "radiance_rgb": [0.4, 0.5, 0.8],
                "interpretation": "illustrative environment boundary condition",
            },
            "broad_area_key": {
                "type": "rectangle emitter",
                "position_relative_to_crop_center_m": [-2.0, 3.0, 1.5],
                "dimensions_m": [4.0, 4.0],
                "radiance_rgb": [3.0, 3.0, 3.0],
                "orientation": "facing crop center, world up +y",
            },
            "camera": "perspective 34 degrees; fixed center-relative camera; up +y",
            "camera_fit": camera_fit,
            "bulk_surface_material": args.bulk_material,
            "axis_layout": "[z,y,x], x fastest",
            "sampling_convention": "input grid values at voxel centers; bounds_m are outer voxel boundaries",
            "threads": args.threads,
            "tone_mapping": "linear HDR * exposure then 1-exp(-x), then sRGB",
            "exposure": args.exposure,
            "resolution_px": [args.width, args.height],
            "spp": args.spp,
        },
        "snapshot": record,
        "scientific_limitations": [
            "The source is a failed exploratory numerical attempt, not a validated Rouaix reproduction.",
            "The image is a near-field crop: 36.70% of whole-field liquid volume lies outside the retained crop.",
            "The crop NPZ is resampled display data; its crop alpha-volume integral differs from native by the value recorded above, with no normalization.",
            "The spray-equivalent medium, dielectric interface, closure, illumination and tone mapping are rendering assumptions, not CFD variables.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"manifest": str(manifest_path), "hero": str(hero), "wall_seconds": elapsed}, indent=2
        )
    )
    return 0


def render_frame(
    *,
    mi: Any,
    field_path: Path,
    cell_count: int,
    native_centres_xyz_m: np.ndarray,
    coords: StructuredCoordinates,
    cell_volumes_m3: np.ndarray,
    bounds_xyz_m: Any,
    dimensions_xyz: tuple[int, int, int],
    run_dir: Path,
    summary_dir: Path,
    time_text: str,
    d32_m: float,
    width: int,
    height: int,
    spp: int,
    exposure: float,
    threads: int,
    bulk_material: str,
) -> dict[str, Any]:
    alpha_native = read_volume_scalar_field(
        field_path, cell_count, EXPECTED_ALPHA_DIMENSIONS
    ).internal
    alpha_yxz = structured_values(np.clip(alpha_native, 0.0, 1.0), coords)
    alpha_uniform = resample_to_uniform_box(alpha_yxz, coords, bounds_xyz_m, dimensions_xyz)
    frame_dir = run_dir / f"t-{time_text.replace('.', 'p')}"
    frame_dir.mkdir(parents=True, exist_ok=True)
    dilute_alpha = np.where(
        (alpha_uniform > 0.0) & (alpha_uniform < SPRAY_ALPHA_MAX), alpha_uniform, 0.0
    ).astype(np.float32)
    np.savez_compressed(
        frame_dir / "alpha-uniform-zyx.npz", alpha=alpha_uniform, dilute_alpha=dilute_alpha
    )
    volume_grid = _uniform_grid_volume(mi, dilute_alpha, bounds_xyz_m)
    surface_path = frame_dir / "alpha-half-surface.ply"
    surface_record = _structured_surface_ply(alpha_uniform, bounds_xyz_m, surface_path)
    camera_fit = _fit_camera(bounds_xyz_m, width, height)
    scene = _mitsuba_scene(
        mi,
        volume_grid,
        surface_path,
        bounds_xyz_m,
        d32_m,
        width,
        height,
        spp,
        bulk_material=bulk_material,
    )
    rendered = np.asarray(mi.render(scene, spp=spp), dtype=np.float32)
    np.save(frame_dir / "linear-rgb.npy", rendered)
    finite = np.isfinite(rendered)
    rendered_dir = run_dir / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)
    output_png = (
        rendered_dir / f"rouaix-startup-d32-{d32_m * 1000:g}mm-t-{time_text.replace('.', 'p')}.png"
    )
    _label_image(rendered, output_png, time_text, d32_m, exposure, bulk_material)
    return {
        **_frame_manifest(
            field_path,
            alpha_native,
            native_centres_xyz_m,
            cell_volumes_m3,
            alpha_uniform,
            bounds_xyz_m,
        ),
        "time_s": float(time_text),
        "output_png": str(output_png.relative_to(ROOT)),
        "output_png_sha256": _sha256(output_png),
        "output_png_bytes": output_png.stat().st_size,
        "linear_render_stats": {
            "finite_fraction": float(np.mean(finite)),
            "finite_min": float(np.min(rendered[finite])) if np.any(finite) else None,
            "finite_max": float(np.max(rendered[finite])) if np.any(finite) else None,
            "finite_mean": float(np.mean(rendered[finite])) if np.any(finite) else None,
        },
        "render": {
            "variant": str(mi.variant()),
            "integrator": "volpath; multiple scattering with Russian roulette after depth 8; no finite max depth",
            "resolution_px": [width, height],
            "spp": spp,
            "threads": threads,
            "bulk_surface_material": bulk_material,
            "surface": surface_record,
            "exposure": exposure,
            "tonemap": "linear HDR, exposure multiplier, exponential shoulder 1-exp(-x), then sRGB",
            "camera_up": "+y (opposite gravity), perspective 34 degrees; camera fitted to all crop corners and fixed for all frames",
            "camera_fit": camera_fit,
        },
        "cached_grid_path": str((frame_dir / "alpha-uniform-zyx.npz").relative_to(ROOT)),
        "mesh_path": str(surface_path.relative_to(ROOT)),
    }


def _parse_bounds(
    value: str,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    try:
        values = [float(part) for part in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("bounds must be six comma-separated metres") from error
    if len(values) != 6:
        raise argparse.ArgumentTypeError("bounds must be x0,x1,y0,y1,z0,z1")
    return ((values[0], values[1]), (values[2], values[3]), (values[4], values[5]))


def _make_video(
    summary_dir: Path,
    frame_paths: list[Path],
    times_s: list[float],
    playback_slowdown: float = 10.0,
    fps: int = 24,
) -> Path:
    ffmpeg = subprocess.run(
        ["which", "ffmpeg"], check=True, text=True, capture_output=True
    ).stdout.strip()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to encode the snapshot-hold clip")
    list_path = summary_dir / "snapshot-list.txt"
    lines = []
    if len(frame_paths) != len(times_s) or not frame_paths:
        raise ValueError("video frame paths and saved field times must be nonempty and match")
    deltas = np.diff(np.asarray(times_s, dtype=np.float64))
    if len(deltas) and np.any(deltas <= 0):
        raise ValueError("video saved times must be strictly increasing")
    endpoint_duration = float(deltas[-1] if len(deltas) else 0.025) * playback_slowdown
    for index, path in enumerate(frame_paths):
        hold = float(
            deltas[index] if index < len(deltas) else endpoint_duration / playback_slowdown
        )
        lines.extend((f"file '{path.resolve()}'", f"duration {hold * playback_slowdown:.8f}"))
    lines.append(f"file '{frame_paths[-1].resolve()}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    video = summary_dir / "rouaix-startup-multiple-scattering.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-safe",
            "0",
            "-f",
            "concat",
            "-i",
            str(list_path),
            "-vf",
            f"fps={fps},format=yuv420p",
            "-c:v",
            "libx264",
            "-crf",
            "22",
            "-movflags",
            "+faststart",
            str(video),
        ],
        check=True,
    )
    list_path.unlink()
    return video


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-root", type=Path, default=WATER_CASE)
    parser.add_argument("--mesh-case", type=Path, default=MESH_CASE)
    parser.add_argument(
        "--grid-npz", type=Path, help="pregridded alpha_zyx/bounds_m display artifact"
    )
    parser.add_argument(
        "--grid-metadata",
        type=Path,
        help="source sidecar for --grid-npz (defaults to sibling metadata.json)",
    )
    parser.add_argument(
        "--time-s", default="1.5000193048", help="display time label for --grid-npz"
    )
    parser.add_argument("--artifact-prefix", default="legacy-multiple-scattering")
    parser.add_argument(
        "--bulk-material",
        choices=("dielectric", "matte-blue"),
        default="dielectric",
        help="display material for the alpha=.5 surface; matte-blue is intentionally nonphysical",
    )
    parser.add_argument("--times", default="0.025,0.05,0.075,0.1,0.125,0.15")
    parser.add_argument(
        "--bounds-m", type=_parse_bounds, default=_parse_bounds("-0.8,1.5,-2.25,-0.001,-1.3,1.3")
    )
    parser.add_argument("--dims", default="96,96,96", help="uniform Nx,Ny,Nz grid")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--summary-dir", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--d32-mm", type=float, default=0.5)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=320)
    parser.add_argument("--spp", type=int, default=16)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--exposure", type=float, default=1.0)
    parser.add_argument("--no-video", action="store_true")
    args = parser.parse_args()

    dimensions = tuple(int(item) for item in args.dims.split(","))
    if len(dimensions) != 3:
        parser.error("--dims must be Nx,Ny,Nz")
    times = [item.strip() for item in args.times.split(",") if item.strip()]
    if not times:
        parser.error("at least one saved time is required")
    field_root = args.field_root.resolve()
    mesh_case = args.mesh_case.resolve()
    args.run_dir = args.run_dir.resolve()
    args.summary_dir = args.summary_dir.resolve()
    args.run_dir.mkdir(parents=True, exist_ok=False)
    args.summary_dir.mkdir(parents=True, exist_ok=True)

    if args.grid_npz is not None:
        _render_pregridded_npz(args)
        return 0

    mesh_hash_comparison = mesh_field_order_comparison(field_root, mesh_case)
    coords_native = read_vector_internal(mesh_case / "0.4" / "C", CELL_COUNT)
    coordinates = structured_coordinates(coords_native)
    native_volumes = read_volume_scalar_field(
        mesh_case / "0.4" / "V", CELL_COUNT, (0, 3, 0, 0, 0, 0, 0)
    ).internal
    if not np.all(np.isfinite(native_volumes)) or np.any(native_volumes <= 0):
        raise ValueError("native cell volumes must be finite and positive")

    # The physical domain is cropped to a fixed near-nozzle box. Uniform-grid
    # samples are at voxel centres; volume transforms map those centres to the
    # exact declared crop bounds without a half-cell offset.
    (x0, x1), (y0, y1), (z0, z1) = args.bounds_m
    x_support = _cell_center_support(coordinates.x_m)
    y_support = _cell_center_support(coordinates.y_m)
    z_edges_by_y = np.stack([_cell_center_support(z_row) for z_row in coordinates.z_by_y_m], axis=0)
    z_support = (float(np.min(z_edges_by_y[:, 0])), float(np.max(z_edges_by_y[:, 1])))
    if (
        x0 < x_support[0]
        or x1 > x_support[1]
        or y0 < y_support[0]
        or y1 > y_support[1]
        or z0 < z_support[0]
        or z1 > z_support[1]
    ):
        raise ValueError("crop bounds exceed estimated native outer cell faces")
    dr, mi = _load_mitsuba(args.threads)
    records = []
    output_frames = []
    for time_text in times:
        field_path = field_root / time_text / "alpha.water"
        if not field_path.is_file():
            raise FileNotFoundError(field_path)
        record = render_frame(
            mi=mi,
            field_path=field_path,
            cell_count=CELL_COUNT,
            native_centres_xyz_m=coords_native,
            coords=coordinates,
            cell_volumes_m3=native_volumes,
            bounds_xyz_m=args.bounds_m,
            dimensions_xyz=dimensions,
            run_dir=args.run_dir,
            summary_dir=args.summary_dir,
            time_text=time_text,
            d32_m=args.d32_mm * 1e-3,
            width=args.width,
            height=args.height,
            spp=args.spp,
            exposure=args.exposure,
            threads=args.threads,
            bulk_material=args.bulk_material,
        )
        records.append(record)
        output_frames.append(ROOT / record["output_png"])

    video = (
        None
        if args.no_video
        else _make_video(
            args.summary_dir,
            output_frames,
            [float(time_text) for time_text in times],
            playback_slowdown=10.0,
        )
    )
    import shutil

    poster = args.summary_dir / "rouaix-startup-multiple-scattering-poster.png"
    shutil.copy2(output_frames[-1], poster)
    manifest = {
        "schema_version": 1,
        "task": "CPU Mitsuba exploratory multiple-scattering visualization from saved Rouaix VOF alpha.water fields",
        "source": {
            "run": str(args.field_root.relative_to(ROOT))
            if args.field_root.is_relative_to(ROOT)
            else str(args.field_root),
            "mesh_case": str(mesh_case.relative_to(ROOT)),
            "mesh_C_path": str((mesh_case / "0.4/C").relative_to(ROOT)),
            "mesh_C_sha256": _sha256(mesh_case / "0.4/C"),
            "mesh_V_path": str((mesh_case / "0.4/V").relative_to(ROOT)),
            "mesh_V_sha256": _sha256(mesh_case / "0.4/V"),
            "fresh_start_mesh_field_order_sha256_match": mesh_hash_comparison,
            "solver_case": "fresh-start C gradient-limited U exploratory run; stopped at 0.17425 s after max|U| operational guard; not validated",
            "mesh_cells": CELL_COUNT,
            "native_structured_dimensions_yxz": list(coordinates.shape_yxz),
            "coordinate_frame": {
                "x": "streamwise",
                "y": "vertical; roof y=0, gravity -y",
                "z": "spanwise",
            },
            "native_cell_center_support_xyz_m": [
                [float(coordinates.x_m[0]), float(coordinates.x_m[-1])],
                [float(coordinates.y_m[0]), float(coordinates.y_m[-1])],
                [float(np.min(coordinates.z_by_y_m)), float(np.max(coordinates.z_by_y_m))],
            ],
            "estimated_outer_cell_face_bounds_xyz_m": [
                [float(v) for v in x_support],
                [float(v) for v in y_support],
                [float(v) for v in z_support],
            ],
        },
        "display_grid": {
            "bounds_xyz_m": [[float(v) for v in pair] for pair in args.bounds_m],
            "dimensions_xyz": list(dimensions),
            "axis_layout": "[z,y,x] contiguous NumPy array; x fastest; verified against Mitsuba VolumeGrid dimensions [x,y,z] and an asymmetric impulse",
            "sampling_convention": "uniform samples at voxel centers (i+0.5)/N mapped by the gridvolume affine transform to declared crop bounds; native field samples at OpenFOAM cell centers; no half-cell shift",
            "resampling": "display-only trilinear interpolation in x,z on each native y-plane then linear interpolation between y-planes; out-of-support samples zero",
            "crop_native_vs_uniform_integrals": [
                {
                    "time_s": row["time_s"],
                    "native_m3": row["native_liquid_volume_inside_crop_m3"],
                    "uniform_m3": row["uniform_resampled_liquid_volume_inside_crop_m3"],
                    "ratio": row["uniform_over_native_crop_integral"],
                }
                for row in records
            ],
        },
        "optical_interpretation": {
            "coherent_bulk": (
                "alpha.water=0.5 isosurface rendered as a dielectric water/air interface (int_ior=1.333, ext_ior=1.000277); this is display geometry extracted from cell-centered, resampled VOF data"
                if args.bulk_material == "dielectric"
                else "alpha.water=0.5 isosurface rendered with a matte-blue diffuse display material; this deliberately nonphysical material changes only appearance, not the VOF geometry or dilute-medium field"
            ),
            "dilute_medium": "only clipped alpha.water in 0 < alpha < 0.1 is used as an inferred dilute spray-equivalent volume-fraction proxy; this is a visual inference, not calibrated spray classifier or measured droplet field",
            "extinction_equation": "sigma_t [m^-1] = 1.5 Qext alpha / D32",
            "D32_m": args.d32_mm * 1e-3,
            "Qext": Q_EXT,
            "Qsca_over_Qext": SINGLE_SCATTER_ALBEDO,
            "HG_g": ASYMMETRY_G,
            "assumption_status": "illustrative geometric-optics Qext≈2, high single-scattering albedo and g are assumptions, not measured; alpha is a water fraction and does not encode droplet size or count",
            "coefficient_scale_m_inv_per_alpha": 1.5 * Q_EXT / (args.d32_mm * 1e-3),
            "surface_alpha_threshold": ALPHA_SURFACE,
            "alpha_clamp": "clip to [0,1] for VOF physical range; clamped native-cell count recorded per snapshot",
            "bulk_surface_material": args.bulk_material,
        },
        "render_settings": {
            "backend": "Mitsuba 3 llvm_ad_rgb CPU",
            "software_versions": {
                "mitsuba": getattr(mi, "__version__", "unknown"),
                "drjit": getattr(dr, "__version__", "unknown"),
                "python": sys.version.split()[0],
            },
            "integrator": "volpath, Russian roulette after depth 8, max_depth=-1",
            "environment": {
                "type": "constant",
                "radiance_rgb": [0.4, 0.5, 0.8],
                "interpretation": "illustrative environment boundary condition; sunsky trials returned zero radiance in smoke",
            },
            "broad_area_key": {
                "type": "rectangle emitter",
                "position_relative_to_crop_center_m": [-2.0, 3.0, 1.5],
                "dimensions_m": [4.0, 4.0],
                "radiance_rgb": [3.0, 3.0, 3.0],
                "orientation": "facing crop center, world up +y",
            },
            "camera": "perspective 34 degrees; fixed look-at at crop center from +x,+y,+z; up +y",
            "bulk_surface_material": args.bulk_material,
            "threads": args.threads,
            "tone_mapping": "linear HDR * exposure then 1-exp(-x), then sRGB; overlay records exploratory interpretation",
            "exposure": args.exposure,
            "time_handling": "only saved field times rendered; no temporal interpolation; MP4 holds each snapshot for its next saved-time interval multiplied by a declared 10x slow-motion factor, then repeats the endpoint for the final interval",
            "resolution_px": [args.width, args.height],
            "spp": args.spp,
        },
        "snapshots": records,
        "video": None
        if video is None
        else {
            "path": str(video.relative_to(ROOT)),
            "sha256": _sha256(video),
            "size_bytes": video.stat().st_size,
            "presentation": "held snapshots; displayed simulation times are labels, not interpolated motion",
        },
        "poster": {
            "path": str(poster.relative_to(ROOT)),
            "sha256": _sha256(poster),
            "size_bytes": poster.stat().st_size,
            "time_s": float(times[-1]),
        },
        "scientific_limitations": [
            "The source run is exploratory and failed a declared operational velocity guard at 0.17425 s; no solver-validation claim follows from these images.",
            "The dilute-band optical mapping depends strongly on assumed D32, Qext, albedo and HG g; none is measured by alpha.water.",
            "Alpha 0.1 is an explicit display mask only; the actual dispersed-droplet population and breakup are unresolved by this VOF export.",
            "All resampling, alpha=.5 mesh extraction, dielectric optical properties and environment illumination are rendering choices.",
        ],
    }
    manifest_path = args.summary_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "snapshots": len(records),
                "video": str(video) if video else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
