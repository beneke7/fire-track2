#!/usr/bin/env python3
"""Run the project VOF renderer with gravity aligned down-screen (-y)."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "track2_render_vof_animation", ROOT / "scripts" / "render_vof_animation.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load the repository VOF animation renderer")
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


def fixed_isometric_camera_y_up(
    plotter: Any,
    bounds: tuple[float, float, float, float, float, float],
    window_size: tuple[int, int],
) -> dict[str, Any]:
    """Use a fixed parallel camera whose projected up direction is world +y."""
    limits = np.asarray(bounds, dtype=np.float64).reshape(3, 2)
    if not np.isfinite(limits).all() or np.any(limits[:, 1] <= limits[:, 0]):
        raise ValueError("camera bounds must contain finite increasing limits")
    center = limits.mean(axis=1)
    corners = np.asarray(
        [(x, y, z) for x in limits[0] for y in limits[1] for z in limits[2]],
        dtype=np.float64,
    )
    direction = np.asarray((-1.0, -1.0, -1.0), dtype=np.float64) / math.sqrt(3.0)
    view_up = np.asarray((0.0, 1.0, 0.0), dtype=np.float64)
    right = np.cross(direction, view_up)
    right /= np.linalg.norm(right)
    screen_up = np.cross(right, direction)
    relative = corners - center
    half_height = float(np.max(np.abs(relative @ screen_up)))
    half_width = float(np.max(np.abs(relative @ right)))
    aspect = window_size[0] / window_size[1]
    parallel_scale = 1.06 * max(half_height, half_width / aspect)
    distance = 2.0 * float(np.max(limits[:, 1] - limits[:, 0]))

    camera = plotter.camera
    camera.focal_point = tuple(center)
    camera.position = tuple(center - direction * distance)
    camera.up = tuple(view_up)
    camera.parallel_projection = True
    camera.parallel_scale = parallel_scale
    plotter.reset_camera_clipping_range()
    return {
        "mode": "fixed-isometric-parallel-y-up",
        "physical_bounds_m": [float(value) for value in bounds],
        "focal_point_m": [float(value) for value in center],
        "view_direction": [float(value) for value in direction],
        "world_screen_up": [0.0, 1.0, 0.0],
        "parallel_scale_m": parallel_scale,
    }


RENDERER._fixed_isometric_camera = fixed_isometric_camera_y_up

if __name__ == "__main__":
    raise SystemExit(RENDERER.main())
