#!/usr/bin/env python3
"""Generate a closed provisional vertical-tank I4F STL geometry preview.

This standalone prototype reuses the horizontal generator's surface and loft
helpers without modifying it. The tank side port is cut with the exact curved
intersection ring between the vertical cylinder and the +x pipe.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_i4f_case import (  # noqa: E402
    BASE_ANGLES,
    Surface,
    add_annulus,
    add_cyl_side,
    add_loft_wall,
    flow_angles,
    polygon_area,
    ring_circle,
    ring_outer,
    ring_rect,
    surface_edge_audit,
    transition_sections,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_sha256(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def default_vertical_config(center_z_m: float = 1.5) -> dict[str, Any]:
    """Return a private vertical arrangement based on the provisional baseline."""
    config = json.loads((ROOT / "experiments/i4f_baseline.json").read_text())
    tank = config["tank"]
    radius = float(tank["diameter_m"]) / 2.0
    center_xyz = [1.5, 0.0, float(center_z_m)]
    tank["axis"] = "vertical"
    tank["axis_vector"] = [0.0, 0.0, 1.0]
    tank["center_xyz_m"] = center_xyz
    tank["center_z_m"] = center_xyz[2]
    # Kept only as inherited horizontal metadata; build_geometry never uses it
    # to define the vertical tank bounds.
    connection = config["connection"]
    mouth = [center_xyz[0] + radius, center_xyz[1], float(connection["center_z_m"])]
    connection["centerline_mouth_xyz_m"] = mouth
    config["nozzle"]["center_z_m"] = mouth[2]
    return config


def validate_vertical_config(config: dict[str, Any]) -> dict[str, Any]:
    tank = config["tank"]
    connection = config["connection"]
    pipe = config["pipe"]
    nozzle = config["nozzle"]
    external = config["external"]
    if tank.get("axis") != "vertical":
        raise ValueError("vertical geometry requires tank.axis='vertical'")
    center = np.asarray(tank.get("center_xyz_m"), dtype=float)
    axis = np.asarray(tank.get("axis_vector"), dtype=float)
    if center.shape != (3,) or not np.isfinite(center).all():
        raise ValueError("tank.center_xyz_m must be a finite three-vector")
    if axis.shape != (3,) or not np.allclose(axis, (0.0, 0.0, 1.0), atol=1e-12, rtol=0.0):
        raise ValueError("vertical geometry requires tank.axis_vector=[0,0,1]")
    if not math.isclose(float(tank.get("center_z_m", math.nan)), float(center[2]), abs_tol=1e-12):
        raise ValueError("tank.center_z_m must agree with tank.center_xyz_m[2]")
    diameter = float(tank["diameter_m"])
    length = float(tank["length_m"])
    pipe_diameter = float(pipe["diameter_m"])
    if (
        min(
            diameter,
            length,
            pipe_diameter,
            float(pipe["length_m"]),
            float(pipe["transition_length_m"]),
            float(external["length_m"]),
        )
        <= 0
    ):
        raise ValueError("tank, pipe, transition and external dimensions must be positive")
    mouth = np.asarray(connection.get("centerline_mouth_xyz_m"), dtype=float)
    if mouth.shape != (3,) or not np.isfinite(mouth).all():
        raise ValueError("connection.centerline_mouth_xyz_m must be a finite three-vector")
    tank_radius = diameter / 2.0
    pipe_radius = pipe_diameter / 2.0
    if not math.isclose(float(mouth[0]), float(center[0] + tank_radius), abs_tol=1e-12):
        raise ValueError(
            "the +x side-port mouth must satisfy mouth_x = tank_center_x + tank_radius"
        )
    if not math.isclose(float(mouth[1]), float(center[1]), abs_tol=1e-12):
        raise ValueError("the +x side-port mouth y must equal tank.center_xyz_m[1]")
    if not math.isclose(float(mouth[2]), float(connection["center_z_m"]), abs_tol=1e-12):
        raise ValueError(
            "connection.centerline_mouth_xyz_m[2] must agree with connection.center_z_m"
        )
    for edge_name, expected_edge_z in (
        ("lower_edge_z_m", float(mouth[2]) - pipe_radius),
        ("upper_edge_z_m", float(mouth[2]) + pipe_radius),
    ):
        if edge_name in connection and not math.isclose(
            float(connection[edge_name]), expected_edge_z, abs_tol=1e-12
        ):
            raise ValueError(f"connection.{edge_name} must match the configured round port radius")
    nozzle_center_z = config.get("nozzle_center_z_m", nozzle.get("center_z_m"))
    if nozzle_center_z is None:
        raise ValueError("nozzle.center_z_m (or legacy nozzle_center_z_m) is required")
    if "center_z_m" in nozzle and not math.isclose(
        float(nozzle["center_z_m"]), float(nozzle_center_z), abs_tol=1e-12
    ):
        raise ValueError("nozzle.center_z_m and top-level nozzle_center_z_m disagree")
    if not math.isclose(float(mouth[2]), float(nozzle_center_z), abs_tol=1e-12):
        raise ValueError("connection and nozzle center z must match")
    bottom_z = float(center[2] - length / 2.0)
    top_z = float(center[2] + length / 2.0)
    if mouth[2] - pipe_radius < bottom_z or mouth[2] + pipe_radius > top_z:
        raise ValueError("the complete side-port opening must lie within the vertical tank caps")
    external_center_y = float(external.get("center_y_m", center[1]))
    if "y_min_m" in external and "y_max_m" in external:
        y_min, y_max = float(external["y_min_m"]), float(external["y_max_m"])
    else:
        half_width = float(external["half_width_m"])
        y_min, y_max = external_center_y - half_width, external_center_y + half_width
    if y_max <= y_min:
        raise ValueError("external y bounds must be increasing")
    bounds = (y_min, y_max, float(external["bottom_z_m"]), float(external["top_z_m"]))
    if bounds[3] <= bounds[2]:
        raise ValueError("external z bounds must be increasing")
    return {
        "tank_center_xyz_m": center.tolist(),
        "tank_axis_vector": axis.tolist(),
        "tank_diameter_m": diameter,
        "tank_length_m": length,
        "tank_bottom_z_m": bottom_z,
        "tank_top_z_m": top_z,
        "port_mouth_xyz_m": mouth.tolist(),
        "port_radius_m": pipe_radius,
        "pipe_end_x_m": float(mouth[0] + float(pipe["length_m"])),
        "transition_length_m": float(pipe["transition_length_m"]),
        "external_length_m": float(external["length_m"]),
        "external_bounds_yz_m": list(bounds),
        "nozzle_width_m": float(nozzle["width_m"]),
        "nozzle_height_m": float(nozzle["height_m"]),
        "nozzle_center_z_m": float(nozzle_center_z),
        "fill_fraction": float(tank["fill_fraction"]),
    }


def unique_sorted(values: list[float], digits: int = 7) -> list[float]:
    """Deduplicate chart knots below the edge audit's 1e-8 m precision.

    Corner-ray inversion can place a chart knot almost on an existing grid
    knot. Keeping both creates zero-length or duplicate STL edges after the
    shared surface auditor rounds vertices to 1e-8 m. The resulting angular
    perturbation is below 1e-7 rad (under 5e-8 m on the tank wall).
    """
    rounded = sorted({round(float(value), digits) for value in values})
    merged: list[float] = []
    for value in rounded:
        if not merged or value - merged[-1] >= 1e-6:
            merged.append(value)
    return merged


def unique_periodic_angles(values: list[float]) -> list[float]:
    """Deduplicate port-ring angles on [0, 2π), including the seam."""
    full_turn = 2.0 * math.pi
    normalized = [float(value) % full_turn for value in values]
    rounded = sorted({round(value, 7) for value in normalized})
    merged: list[float] = []
    for value in rounded:
        if value < 1e-6 or full_turn - value < 1e-6:
            value = 0.0
        if not merged or value - merged[-1] >= 1e-6:
            merged.append(value)
    if len(merged) > 1 and full_turn - merged[-1] + merged[0] < 1e-6:
        merged.pop()
    return merged


def canonical_theta_nodes(values: list[float]) -> list[float]:
    """Use exact periodic endpoints after deduplicating the chart grid."""
    nodes = unique_sorted(values)
    return sorted(
        -math.pi
        if abs(value + math.pi) < 1e-6
        else math.pi
        if abs(value - math.pi) < 1e-6
        else value
        for value in nodes
    )


def snap_to_nodes(value: float, nodes: list[float], tolerance: float = 1e-6) -> float:
    """Use the representative retained after near-coincident chart knots merge."""
    nearest = min(nodes, key=lambda node: abs(node - value))
    return nearest if abs(nearest - value) <= tolerance else value


def chart_to_xyz(
    theta: float, z: float, center_x: float, center_y: float, radius: float
) -> tuple[float, float, float]:
    return center_x + radius * math.cos(theta), center_y + radius * math.sin(theta), z


def rectangle_ray(theta: float, z: float, theta_half: float, z_half: float, zc: float):
    """Intersect the chart ray from the port center with a surrounding rectangle."""
    dtheta = theta
    dz = z - zc
    candidates = []
    if dtheta > 1e-15:
        candidates.append(theta_half / dtheta)
    elif dtheta < -1e-15:
        candidates.append(-theta_half / dtheta)
    if dz > 1e-15:
        candidates.append(z_half / dz)
    elif dz < -1e-15:
        candidates.append(-z_half / dz)
    scale = min(value for value in candidates if value > 0.0)
    outer_theta = scale * dtheta
    outer_z = zc + scale * dz
    if abs(abs(outer_theta) - theta_half) <= 1e-10:
        outer_theta = math.copysign(theta_half, outer_theta)
    if abs(abs(outer_z - zc) - z_half) <= 1e-10:
        outer_z = zc + math.copysign(z_half, outer_z - zc)
    return outer_theta, outer_z


def port_angles_through_chart_corners(
    angles: list[float],
    radius_tank: float,
    radius_port: float,
    zc: float,
    theta_half: float,
    z_half: float,
    boundary_theta_nodes: list[float],
    boundary_z_nodes: list[float] | None = None,
) -> list[float]:
    """Add exact ray directions for chart-panel corners and edge-grid knots."""
    alpha = math.atan2(z_half, theta_half)
    targets = {alpha, math.pi - alpha, math.pi + alpha, 2.0 * math.pi - alpha}
    for theta in boundary_theta_nodes:
        if abs(theta) <= theta_half + 1e-10:
            targets.add(math.atan2(z_half, theta) % (2.0 * math.pi))
            targets.add(math.atan2(-z_half, theta) % (2.0 * math.pi))
    for z in boundary_z_nodes or []:
        dz = z - zc
        targets.add(math.atan2(dz, theta_half) % (2.0 * math.pi))
        targets.add(math.atan2(dz, -theta_half) % (2.0 * math.pi))
    targets = sorted(targets)

    def chart_ray_angle(phi: float) -> float:
        theta = math.asin(radius_port * math.cos(phi) / radius_tank)
        dz = radius_port * math.sin(phi)
        value = math.atan2(dz, theta)
        return value + 2.0 * math.pi if value < 0.0 else value

    added = []
    for target in targets:
        if target < math.pi / 2.0:
            lo_start, hi_start = 0.0, math.pi / 2.0
        elif target < math.pi:
            lo_start, hi_start = math.pi / 2.0, math.pi
        elif target < 3.0 * math.pi / 2.0:
            lo_start, hi_start = math.pi, 3.0 * math.pi / 2.0
        else:
            lo_start, hi_start = 3.0 * math.pi / 2.0, 2.0 * math.pi
        lo, hi = lo_start, hi_start
        for _ in range(64):
            mid = 0.5 * (lo + hi)
            if chart_ray_angle(mid) < target:
                lo = mid
            else:
                hi = mid
        added.append(0.5 * (lo + hi))
    return unique_periodic_angles(angles + added)


def add_chart_grid(
    surface: Surface,
    theta_nodes: list[float],
    z_nodes: list[float],
    center_x: float,
    center_y: float,
    radius: float,
) -> None:
    for z0, z1 in zip(z_nodes[:-1], z_nodes[1:], strict=True):
        for theta0, theta1 in zip(theta_nodes[:-1], theta_nodes[1:], strict=True):
            if theta1 - theta0 <= 1e-13 or z1 - z0 <= 1e-13:
                continue
            p = chart_to_xyz(theta0, z0, center_x, center_y, radius)
            q = chart_to_xyz(theta1, z0, center_x, center_y, radius)
            r = chart_to_xyz(theta1, z1, center_x, center_y, radius)
            s = chart_to_xyz(theta0, z1, center_x, center_y, radius)
            surface.quad(p, q, r, s)


def vertical_tank_wall_with_port(
    *,
    center_x: float,
    center_y: float,
    radius: float,
    bottom_z: float,
    top_z: float,
    port_radius: float,
    port_center_z: float,
    angles: list[float],
) -> tuple[Surface, list[tuple[float, float, float]], dict[str, Any]]:
    """Make the cylinder side, subtracting a charted hole with an exact rim."""
    surface = Surface("tankWall")
    margin = 0.02
    theta_half = math.asin((port_radius + margin) / radius)
    z_half = port_radius + margin
    zlo, zhi = port_center_z - z_half, port_center_z + z_half
    inner_chart = []
    port_ring_xyz = []
    for angle in angles:
        y = center_y + port_radius * math.cos(angle)
        z = port_center_z + port_radius * math.sin(angle)
        theta = math.asin((y - center_y) / radius)
        inner_chart.append((theta, z))
        radial_y = y - center_y
        port_ring_xyz.append((center_x + math.sqrt(radius * radius - radial_y * radial_y), y, z))
    outer_chart = [
        tuple(
            round(value, 7) for value in rectangle_ray(theta, z, theta_half, z_half, port_center_z)
        )
        for theta, z in inner_chart
    ]

    theta_base = np.linspace(-math.pi, math.pi, BASE_ANGLES * 2 + 1).tolist()
    theta_nodes = canonical_theta_nodes(theta_base + [point[0] for point in outer_chart])
    outer_chart = [(snap_to_nodes(theta, theta_nodes), z) for theta, z in outer_chart]
    left_edge_z = unique_sorted(
        [zlo, zhi] + [z for theta, z in outer_chart if abs(theta + theta_half) <= 1e-6]
    )
    right_edge_z = unique_sorted(
        [zlo, zhi] + [z for theta, z in outer_chart if abs(theta - theta_half) <= 1e-6]
    )
    shared_periodic_edge_z = unique_sorted(left_edge_z + right_edge_z)
    left_edge_z = shared_periodic_edge_z
    right_edge_z = shared_periodic_edge_z
    outer_chart = [
        (
            theta,
            snap_to_nodes(
                z,
                shared_periodic_edge_z,
            )
            if abs(abs(theta) - theta_half) <= 1e-6
            else z,
        )
        for theta, z in outer_chart
    ]

    # Uncut strips above/below the panel share every outer-ring edge knot.
    add_chart_grid(surface, theta_nodes, [bottom_z, zlo], center_x, center_y, radius)
    add_chart_grid(surface, theta_nodes, [zhi, top_z], center_x, center_y, radius)
    # Side strips on either side of the panel preserve the periodic cylinder seam.
    left_theta = [value for value in theta_nodes if value <= -theta_half + 1e-6]
    right_theta = [value for value in theta_nodes if value >= theta_half - 1e-6]
    add_chart_grid(surface, left_theta, left_edge_z, center_x, center_y, radius)
    add_chart_grid(surface, right_theta, right_edge_z, center_x, center_y, radius)

    # Fill the panel between the exact curved port rim and its rectangular outer rim.
    for index in range(len(inner_chart)):
        nxt = (index + 1) % len(inner_chart)
        a = chart_to_xyz(*inner_chart[index], center_x, center_y, radius)
        b = chart_to_xyz(*outer_chart[index], center_x, center_y, radius)
        c = chart_to_xyz(*outer_chart[nxt], center_x, center_y, radius)
        d = chart_to_xyz(*inner_chart[nxt], center_x, center_y, radius)
        surface.quad(a, b, c, d)

    ring_errors = []
    for point, angle in zip(port_ring_xyz, angles, strict=True):
        y, z = (
            center_y + port_radius * math.cos(angle),
            port_center_z + port_radius * math.sin(angle),
        )
        expected_x = center_x + math.sqrt(radius * radius - (y - center_y) ** 2)
        ring_errors.append(abs(point[0] - expected_x))
    metadata = {
        "chart": "s=R*theta, z; cylinder point (x_c+R*cos(theta), R*sin(theta), z)",
        "port_ring_equation": "y=y_c+r_p*cos(phi), z=z_p+r_p*sin(phi), x=x_c+sqrt(R^2-(y-y_c)^2)",
        "port_ring_point_count": len(port_ring_xyz),
        "port_ring_x_min_m": min(point[0] for point in port_ring_xyz),
        "port_ring_x_max_m": max(point[0] for point in port_ring_xyz),
        "port_ring_max_equation_error_m": max(ring_errors, default=0.0),
        "panel_outer_chart_bounds": {
            "theta_min_rad": -theta_half,
            "theta_max_rad": theta_half,
            "z_min_m": zlo,
            "z_max_m": zhi,
        },
        "periodic_seam": "theta=-pi and theta=+pi have coincident STL coordinates and are audited as one closed edge",
    }
    return surface, port_ring_xyz, metadata


def add_vertical_tank_caps(
    surface: Surface,
    *,
    center_x: float,
    center_y: float,
    radius: float,
    z: float,
    theta_nodes: list[float],
    sign: int,
) -> None:
    center = (center_x, center_y, z)
    ring = [
        (center_x + radius * math.cos(theta), center_y + radius * math.sin(theta), z)
        for theta in theta_nodes[:-1]
    ]
    for index, point in enumerate(ring):
        nxt = ring[(index + 1) % len(ring)]
        if sign > 0:
            surface.tri(center, point, nxt)
        else:
            surface.tri(center, nxt, point)


def add_vertical_pipe_wall(
    surface: Surface,
    *,
    back_ring: list[tuple[float, float, float]],
    x_start: float,
    x_end: float,
    center_y: float,
    center_z: float,
    radius: float,
    angles: list[float],
    stations: int = 20,
) -> None:
    rings = [back_ring]
    for step in range(stations + 1):
        x = x_start + (x_end - x_start) * step / stations
        rings.append(
            [
                (x, center_y + radius * math.cos(angle), center_z + radius * math.sin(angle))
                for angle in angles
            ]
        )
    for ring_a, ring_b in zip(rings[:-1], rings[1:], strict=True):
        for index in range(len(angles)):
            nxt = (index + 1) % len(angles)
            a, b, c, d = ring_a[index], ring_a[nxt], ring_b[nxt], ring_b[index]
            # At the two tangent points y=0, the curved tank/pipe ring exactly
            # touches the circular x=x_start ring. The connector quad collapses
            # to one triangle there; omit only its zero-area second triangle.
            for triangle in ((a, b, c), (a, c, d)):
                quantized = {tuple(round(value, 10) for value in point) for point in triangle}
                if len(quantized) == 3:
                    surface.tri(*triangle)


def signed_volume(surfaces: list[Surface]) -> tuple[float, dict[str, float]]:
    contributions = {}
    for surface in surfaces:
        subtotal = 0.0
        for a, b, c in surface.tris:
            subtotal += (
                a[0] * (b[1] * c[2] - b[2] * c[1])
                + a[1] * (b[2] * c[0] - b[0] * c[2])
                + a[2] * (b[0] * c[1] - b[1] * c[0])
            ) / 6.0
        contributions[surface.name] = subtotal
    return sum(contributions.values()), contributions


def detailed_edge_audit(surfaces: list[Surface]) -> dict[str, Any]:
    edges: dict[tuple[tuple[int, int, int], tuple[int, int, int]], list[dict[str, Any]]] = {}
    for surface in surfaces:
        for triangle_index, triangle in enumerate(surface.tris):
            vertices = [tuple(round(value * 1e8) for value in point) for point in triangle]
            for index in range(3):
                a, b = vertices[index], vertices[(index + 1) % 3]
                key = tuple(sorted((a, b)))
                edges.setdefault(key, []).append(
                    {
                        "surface": surface.name,
                        "triangle": triangle_index,
                        "direction": 1 if a < b else -1,
                    }
                )
    boundary = [(key, owners) for key, owners in edges.items() if len(owners) == 1]
    nonmanifold = [(key, owners) for key, owners in edges.items() if len(owners) != 2]

    def point(key):
        return [value / 1e8 for value in key]

    return {
        "boundary_count": len(boundary),
        "nonmanifold_count": len(nonmanifold),
        "boundary_by_owner_surface": dict(Counter(owners[0]["surface"] for _, owners in boundary)),
        "nonmanifold_by_owner_surfaces": dict(
            Counter(
                "+".join(sorted({owner["surface"] for owner in owners}))
                for _, owners in nonmanifold
            )
        ),
        "boundary_samples": [
            {"edge_xyz_m": [point(edge[0]), point(edge[1])], "owner": owners[0]}
            for edge, owners in boundary
        ],
        "nonmanifold_samples": [
            {"edge_xyz_m": [point(edge[0]), point(edge[1])], "owners": owners}
            for edge, owners in nonmanifold
        ],
    }


def expected_fluid_volume(
    *,
    center_x: float,
    tank_radius: float,
    tank_height: float,
    port_radius: float,
    pipe_end_x: float,
    pipe_center_z: float,
    transition_areas: list[float],
    transition_x: list[float],
    external_length: float,
    external_area: float,
) -> dict[str, float]:
    tank_volume = math.pi * tank_radius**2 * tank_height
    pipe_area = math.pi * port_radius**2
    radial = (np.arange(256) + 0.5) / 256.0
    angles = 2 * math.pi * (np.arange(512) + 0.5) / 512.0
    rho, phi = np.meshgrid(radial, angles, indexing="ij")
    y = port_radius * rho * np.cos(phi)
    x_back = center_x + np.sqrt(tank_radius**2 - y**2)
    weights = rho
    mean_x_back = float(np.sum(x_back * weights) / np.sum(weights))
    pipe_extension = pipe_area * (pipe_end_x - mean_x_back)
    transition_volume = float(np.trapezoid(transition_areas, transition_x))
    external_volume = external_length * external_area
    total = tank_volume + pipe_extension + transition_volume + external_volume
    return {
        "tank_cylinder_m3": tank_volume,
        "curved_start_pipe_extension_m3": pipe_extension,
        "transition_m3": transition_volume,
        "external_domain_m3": external_volume,
        "total_approx_m3": total,
        "pipe_connection_mean_start_x_m": mean_x_back,
    }


def draw_geometry_preview(
    output: Path,
    surfaces: list[Surface],
    metadata: dict[str, Any],
    transition: list[tuple[float, list[tuple[float, float]]]],
) -> list[str]:
    output.mkdir(parents=True, exist_ok=True)
    colors = {
        "tankWall": "#3978a8",
        "pipeWall": "#42a66f",
        "transitionWall": "#cf8b28",
        "externalSides": "#8b6ab7",
        "ambientAnnulus": "#d05a75",
        "outlet": "#626a73",
    }

    # Axial centerline view, with the vertical vessel and horizontal discharge visible together.
    fig, ax = plt.subplots(figsize=(14, 7), constrained_layout=True)
    tank = metadata["tank"]
    cx, cy, _ = tank["center_xyz_m"]
    radius = tank["diameter_m"] / 2
    bottom, top = tank["bottom_z_m"], tank["top_z_m"]
    ax.plot([cx - radius, cx - radius], [bottom, top], color=colors["tankWall"], lw=2)
    ax.plot([cx + radius, cx + radius], [bottom, top], color=colors["tankWall"], lw=2)
    ax.plot([cx - radius, cx + radius], [bottom, bottom], color=colors["tankWall"], lw=2)
    ax.plot([cx - radius, cx + radius], [top, top], color=colors["tankWall"], lw=2)
    port_z = metadata["port"]["center_z_m"]
    pipe_r = metadata["pipe"]["diameter_m"] / 2
    xring = [point[0] for point in metadata["junction"]["port_ring_points_xyz_m"]]
    pipe_end_x = metadata["pipe"]["centerline_x_end_m"]
    ax.plot(
        [min(xring), pipe_end_x],
        [port_z + pipe_r, port_z + pipe_r],
        color=colors["pipeWall"],
        lw=1.6,
    )
    ax.plot(
        [min(xring), pipe_end_x],
        [port_z - pipe_r, port_z - pipe_r],
        color=colors["pipeWall"],
        lw=1.6,
    )
    for x, ring in transition:
        ax.plot(
            [x, x],
            [min(p[1] for p in ring), max(p[1] for p in ring)],
            color=colors["transitionWall"],
            lw=0.7,
            alpha=0.55,
        )
    transition_start = metadata["transition"]["start_x_m"]
    transition_end = metadata["transition"]["end_x_m"]
    for side in (-1, 1):
        ax.plot(
            [transition_start, transition_end],
            [port_z + side * pipe_r, port_z + side * metadata["nozzle"]["height_m"] / 2],
            color=colors["transitionWall"],
            lw=1.7,
        )
    external = metadata["external"]
    ax.plot(
        [transition_end, transition_end],
        [external["bottom_z_m"], external["top_z_m"]],
        color=colors["ambientAnnulus"],
        lw=1.5,
    )
    ax.plot(
        [transition_end, external["end_x_m"]],
        [external["bottom_z_m"], external["bottom_z_m"]],
        color=colors["externalSides"],
        lw=1.4,
    )
    ax.plot(
        [transition_end, external["end_x_m"]],
        [external["top_z_m"], external["top_z_m"]],
        color=colors["externalSides"],
        lw=1.4,
    )
    ax.plot(
        [external["end_x_m"], external["end_x_m"]],
        [external["bottom_z_m"], external["top_z_m"]],
        color=colors["outlet"],
        lw=1.5,
    )
    ax.axvline(cx, color="#333333", ls=":", lw=0.8)
    ax.axvline(metadata["port"]["centerline_mouth_xyz_m"][0], color="#333333", ls="--", lw=0.8)
    ax.axvline(pipe_end_x, color="#333333", ls="--", lw=0.8)
    ax.axvline(transition_end, color="#333333", ls="--", lw=0.8)
    ax.axvline(external["end_x_m"], color="#333333", ls="--", lw=0.8)
    ax.text(cx, top + 0.04, "vertical tank axis z", ha="center", fontsize=9)
    ax.text(
        metadata["port"]["centerline_mouth_xyz_m"][0],
        port_z + 0.19,
        "curved side port",
        ha="center",
        fontsize=9,
    )
    ax.text(
        transition_end,
        external["top_z_m"] - 0.05,
        "external starts",
        rotation=90,
        va="top",
        fontsize=8,
    )
    ax.text(
        external["end_x_m"],
        external["top_z_m"] - 0.05,
        "far outlet",
        rotation=90,
        va="top",
        fontsize=8,
    )
    ax.set(
        xlabel="x discharge direction (m)",
        ylabel="z upward (m)",
        title="Vertical tank, curved side port, preserved +x pipe / transition / external geometry",
    )
    ax.set_xlim(cx - radius - 0.2, external["end_x_m"] + 0.1)
    ax.set_ylim(min(external["bottom_z_m"], bottom) - 0.1, max(external["top_z_m"], top) + 0.2)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.2)
    overview = output / "geometry-mesh-overview.png"
    fig.savefig(overview, dpi=180)
    plt.close(fig)

    # Detailed projections of the curved wall/pipe junction and four downstream sections.
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    ax = axes[0, 0]
    theta = np.linspace(0.0, 2 * math.pi, 512)
    y = cy + pipe_r * np.cos(theta)
    x = cx + np.sqrt(radius * radius - (y - cy) ** 2)
    ax.plot(x, y, color=colors["tankWall"], lw=1.4, label="tank/pipe intersection ring")
    ax.fill(x, y, color=colors["pipeWall"], alpha=0.16)
    ax.set(title="Curved port ring, viewed in x-y at z=0.65 m", xlabel="x (m)", ylabel="y (m)")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.2)

    ax = axes[0, 1]
    yline = np.linspace(cy - radius, cy + radius, 512)
    xwall = cx + np.sqrt(np.maximum(0.0, radius * radius - (yline - cy) ** 2))
    ax.plot(xwall, yline, color=colors["tankWall"], lw=1.5, label="tank side")
    select = np.abs(yline) <= pipe_r
    ax.plot(xwall[select], yline[select], color="#cf2d2d", lw=3, label="ring at z=0.65 m")
    ax.plot([min(xring), pipe_end_x], [cy + pipe_r, cy + pipe_r], color=colors["pipeWall"], lw=1.5)
    ax.plot([min(xring), pipe_end_x], [cy - pipe_r, cy - pipe_r], color=colors["pipeWall"], lw=1.5)
    ax.set(title="Junction side view at z=0.65 m", xlabel="x (m)", ylabel="y (m)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.2)

    transition_mid_x = 0.5 * (transition_start + transition_end)
    sections = [
        (
            metadata["port"]["centerline_mouth_xyz_m"][0] + 0.53 * metadata["pipe"]["length_m"],
            "round pipe",
        ),
        (transition_mid_x, "transition midpoint"),
        (transition_end - 0.01, "nozzle lip"),
        (transition_end + 0.01, "external entrance"),
    ]
    angles = metadata["section_angles_rad"]
    ext = metadata["external"]
    for ax, (xsec, title) in zip(axes.flat[2:], sections, strict=True):
        if xsec < transition_start:
            ring = [(y + cy, z) for y, z in ring_circle(pipe_r, port_z, angles)]
            outline = np.asarray(ring + [ring[0]])
        elif xsec < transition_end - 1e-9:
            section = min(transition, key=lambda item: abs(item[0] - xsec))
            outline = np.asarray(section[1] + [section[1][0]])
        elif xsec < transition_end + 1e-9:
            nozzle_ring = [
                (y + cy, z)
                for y, z in ring_rect(
                    metadata["nozzle"]["width_m"], metadata["nozzle"]["height_m"], port_z, angles
                )
            ]
            outline = np.asarray(nozzle_ring + [nozzle_ring[0]])
        else:
            outline = np.asarray(
                ring_outer(
                    (ext["y_min_m"], ext["y_max_m"], ext["bottom_z_m"], ext["top_z_m"]),
                    port_z,
                    angles,
                )
                + [
                    ring_outer(
                        (ext["y_min_m"], ext["y_max_m"], ext["bottom_z_m"], ext["top_z_m"]),
                        port_z,
                        angles,
                    )[0]
                ]
            )
        ax.plot(
            outline[:, 0],
            outline[:, 1],
            color=colors["pipeWall"]
            if xsec < 3
            else colors["transitionWall"]
            if xsec < 4.5
            else colors["outlet"],
            lw=1.2,
        )
        ax.set(title=title, xlabel="y horizontal span (m)", ylabel="z upward (m)")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.2)
    crosssections = output / "geometry-mesh-crosssections.png"
    fig.savefig(crosssections, dpi=180)
    plt.close(fig)

    # Perspective mesh view of the exact sidewall ring and the first 30 cm of pipe.
    fig = plt.figure(figsize=(10, 8), constrained_layout=True)
    ax3 = fig.add_subplot(111, projection="3d")
    for surface in surfaces[:2]:
        upper_x = 2.03 if surface.name == "tankWall" else 2.08
        triangles = [
            triangle
            for triangle in surface.tris
            if all(1.82 <= point[0] <= upper_x for point in triangle)
        ]
        if triangles:
            collection = Poly3DCollection(
                triangles,
                facecolor=colors[surface.name],
                edgecolor=(0.1, 0.1, 0.1, 0.35),
                linewidth=0.18,
                alpha=0.62,
            )
            ax3.add_collection3d(collection)
    ring = np.asarray(metadata["junction"]["port_ring_points_xyz_m"])
    ax3.plot(
        ring[:, 0],
        ring[:, 1],
        ring[:, 2],
        color="#cf2d2d",
        lw=2,
        label="exact tank-side intersection",
    )
    ax3.set(
        xlabel="x (m)",
        ylabel="y (m)",
        zlabel="z (m)",
        title="Closed sidewall cut and pipe wall joined on the curved intersection",
    )
    mouth = metadata["port"]["centerline_mouth_xyz_m"]
    ax3.set_xlim(min(xring) - 0.05, mouth[0] + 0.34)
    ax3.set_ylim(cy - pipe_r - 0.065, cy + pipe_r + 0.065)
    ax3.set_zlim(port_z - pipe_r - 0.065, port_z + pipe_r + 0.065)
    ax3.set_box_aspect((0.49, 0.38, 0.38))
    ax3.view_init(elev=24, azim=-54)
    ax3.legend(fontsize=8)
    connection = output / "geometry-connection.png"
    fig.savefig(connection, dpi=180)
    plt.close(fig)
    return [str(overview), str(crosssections), str(connection)]


def _generate_geometry(
    config: dict[str, Any], tri_dir: Path
) -> tuple[dict[str, Any], list[Surface], list[tuple[float, list[tuple[float, float]]]]]:
    parameters = validate_vertical_config(config)
    tri_dir.mkdir(parents=True, exist_ok=True)
    tank_d = parameters["tank_diameter_m"]
    tank_radius = tank_d / 2
    tank_center = tuple(parameters["tank_center_xyz_m"])
    tank_bottom = parameters["tank_bottom_z_m"]
    tank_top = parameters["tank_top_z_m"]
    port_center = tuple(parameters["port_mouth_xyz_m"])
    pipe_radius = parameters["port_radius_m"]
    pipe_end_x = parameters["pipe_end_x_m"]
    transition_start_x = pipe_end_x
    transition_length = parameters["transition_length_m"]
    transition_end_x = transition_start_x + transition_length
    external_length = parameters["external_length_m"]
    external_end_x = transition_end_x + external_length
    bounds = tuple(parameters["external_bounds_yz_m"])
    nozzle = config["nozzle"]
    port_z = parameters["nozzle_center_z_m"]
    angles = flow_angles(float(nozzle["width_m"]), float(nozzle["height_m"]), bounds, port_z)
    theta_panel_half = math.asin((pipe_radius + 0.02) / tank_radius)
    theta_base = np.linspace(-math.pi, math.pi, BASE_ANGLES * 2 + 1).tolist()
    angles = port_angles_through_chart_corners(
        angles,
        tank_radius,
        pipe_radius,
        port_z,
        theta_panel_half,
        pipe_radius + 0.02,
        theta_base,
    )
    initial_panel_inner = [
        (
            math.asin((pipe_radius * math.cos(angle)) / tank_radius),
            port_z + pipe_radius * math.sin(angle),
        )
        for angle in angles
    ]
    initial_panel_outer = [
        rectangle_ray(t, z, theta_panel_half, pipe_radius + 0.02, port_z)
        for t, z in initial_panel_inner
    ]
    panel_edge_z = unique_sorted(
        [port_z - pipe_radius - 0.02, port_z + pipe_radius + 0.02]
        + [z for theta, z in initial_panel_outer if abs(abs(theta) - theta_panel_half) <= 1e-8]
    )
    angles = port_angles_through_chart_corners(
        angles,
        tank_radius,
        pipe_radius,
        port_z,
        theta_panel_half,
        pipe_radius + 0.02,
        [],
        panel_edge_z,
    )
    tank_wall, port_ring_xyz, junction_meta = vertical_tank_wall_with_port(
        center_x=tank_center[0],
        center_y=tank_center[1],
        radius=tank_radius,
        bottom_z=tank_bottom,
        top_z=tank_top,
        port_radius=pipe_radius,
        port_center_z=port_z,
        angles=angles,
    )

    theta_panel_half = math.asin((pipe_radius + 0.02) / tank_radius)
    theta_base = np.linspace(-math.pi, math.pi, BASE_ANGLES * 2 + 1).tolist()
    # Cap-ring knots must match the outer panel perimeter used by the tank wall.
    chart_inner = [
        (
            math.asin((pipe_radius * math.cos(angle)) / tank_radius),
            port_z + pipe_radius * math.sin(angle),
        )
        for angle in angles
    ]
    panel_outer = [
        rectangle_ray(t, z, theta_panel_half, pipe_radius + 0.02, port_z) for t, z in chart_inner
    ]
    panel_outer = [(round(t, 7), round(z, 7)) for t, z in panel_outer]
    theta_nodes = canonical_theta_nodes(theta_base + [t for t, _ in panel_outer])
    tank_top_cap = Surface("tankTop")
    tank_bottom_cap = Surface("tankBottom")
    add_vertical_tank_caps(
        tank_top_cap,
        center_x=tank_center[0],
        center_y=tank_center[1],
        radius=tank_radius,
        z=tank_top,
        theta_nodes=theta_nodes,
        sign=1,
    )
    add_vertical_tank_caps(
        tank_bottom_cap,
        center_x=tank_center[0],
        center_y=tank_center[1],
        radius=tank_radius,
        z=tank_bottom,
        theta_nodes=theta_nodes,
        sign=-1,
    )
    tank_wall.tris.extend(tank_top_cap.tris)
    tank_wall.tris.extend(tank_bottom_cap.tris)

    pipe_wall = Surface("pipeWall")
    add_vertical_pipe_wall(
        pipe_wall,
        back_ring=port_ring_xyz,
        x_start=port_center[0],
        x_end=pipe_end_x,
        center_y=port_center[1],
        center_z=port_z,
        radius=pipe_radius,
        angles=angles,
        stations=20,
    )
    transition, transition_audit = transition_sections(
        transition_start_x,
        transition_length,
        pipe_radius,
        float(nozzle["width_m"]),
        float(nozzle["height_m"]),
        port_z,
        angles,
    )
    transition = [(x, [(y + port_center[1], z) for y, z in ring]) for x, ring in transition]
    transition_wall = Surface("transitionWall")
    add_loft_wall(transition_wall, transition)
    outer_ring = ring_outer(bounds, port_z, angles)
    external_wall = Surface("externalSides")
    add_cyl_side(
        external_wall, [transition_end_x + external_length * i / 20 for i in range(21)], outer_ring
    )
    annulus = Surface("ambientAnnulus")
    nozzle_ring = [
        (y + port_center[1], z)
        for y, z in ring_rect(float(nozzle["width_m"]), float(nozzle["height_m"]), port_z, angles)
    ]
    add_annulus(annulus, transition_end_x, outer_ring, nozzle_ring, -1)
    outlet = Surface("outlet")
    for index, point in enumerate(outer_ring):
        next_point = outer_ring[(index + 1) % len(outer_ring)]
        center = (external_end_x, (bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2)
        p = (external_end_x, point[0], point[1])
        q = (external_end_x, next_point[0], next_point[1])
        c = (external_end_x, center[1], center[2])
        outlet.tri(c, p, q)

    surfaces = [tank_wall, pipe_wall, transition_wall, external_wall, annulus, outlet]
    audit = surface_edge_audit(surfaces)
    volume_m3, surface_volumes = signed_volume(surfaces)
    if audit["boundary_edges"] or audit["nonmanifold_edges"]:
        (tri_dir.parent / "edge-audit-failure.json").write_text(
            json.dumps(detailed_edge_audit(surfaces), indent=2) + "\n"
        )
        raise RuntimeError(f"vertical geometry is not closed/manifold: {audit}")
    if not math.isfinite(volume_m3) or volume_m3 <= 0.0:
        raise RuntimeError(f"vertical geometry signed volume must be positive, got {volume_m3}")

    outer_area = polygon_area(outer_ring)
    expected = expected_fluid_volume(
        center_x=tank_center[0],
        tank_radius=tank_radius,
        tank_height=tank_top - tank_bottom,
        port_radius=pipe_radius,
        pipe_end_x=pipe_end_x,
        pipe_center_z=port_z,
        transition_areas=[row["area_mesh_m2"] for row in transition_audit],
        transition_x=[row["x_m"] for row in transition_audit],
        external_length=external_length,
        external_area=outer_area,
    )
    relative_volume_error = (volume_m3 - expected["total_approx_m3"]) / expected["total_approx_m3"]
    if abs(relative_volume_error) > 0.02:
        raise RuntimeError(
            f"STL signed volume differs from component estimate by {relative_volume_error:.3%}"
        )
    for surface in surfaces:
        surface.write(tri_dir / f"{surface.name}.stl")

    metadata: dict[str, Any] = {
        "schema": "i4f-vertical-geometry/v2",
        "status": "provisional parameterized geometry; not verified CAD",
        "source_config": "caller-provided configuration dictionary",
        "source_config_sha256": config_sha256(config),
        "tank": {
            "diameter_m": tank_d,
            "length_m": tank_top - tank_bottom,
            "center_xyz_m": list(tank_center),
            "axis": "vertical",
            "axis_vector": list(parameters["tank_axis_vector"]),
            "bottom_z_m": tank_bottom,
            "top_z_m": tank_top,
            "actual_bbox_xyz_m": [
                [tank_center[0] - tank_radius, tank_center[1] - tank_radius, tank_bottom],
                [tank_center[0] + tank_radius, tank_center[1] + tank_radius, tank_top],
            ],
            "ignored_legacy_horizontal_start_x_m": config["tank"].get("start_x_m"),
            "fill_fraction_geometric": parameters["fill_fraction"],
        },
        "port": {
            "centerline_mouth_xyz_m": list(port_center),
            "pipe_axis": "+x",
            "junction": "curved intersection with the vertical cylinder side; exact ring used as the pipe-wall back boundary",
            "diameter_m": 2.0 * pipe_radius,
            "center_z_m": port_z,
            "clearance_from_port_lower_edge_to_tank_bottom_m": (port_z - pipe_radius) - tank_bottom,
        },
        "pipe": {
            "diameter_m": 2.0 * pipe_radius,
            "length_m": pipe_end_x - port_center[0],
            "centerline_x_start_m": port_center[0],
            "centerline_x_end_m": pipe_end_x,
            "centerline_length_m": pipe_end_x - port_center[0],
            "center_z_m": port_z,
            "center_y_m": port_center[1],
            "junction_back_boundary": "curved sidewall intersection ring, x varies with y",
        },
        "junction": {
            **junction_meta,
            "port_ring_points_xyz_m": [list(point) for point in port_ring_xyz],
        },
        "transition": {
            "start_x_m": transition_start_x,
            "end_x_m": transition_end_x,
            "length_m": transition_length,
            "section_audit": transition_audit,
        },
        "nozzle": {
            "width_m": float(nozzle["width_m"]),
            "height_m": float(nozzle["height_m"]),
            "center_z_m": port_z,
            "direction": [1.0, 0.0, 0.0],
            "center_y_m": port_center[1],
        },
        "external": {
            "start_x_m": transition_end_x,
            "end_x_m": external_end_x,
            "length_m": external_length,
            "y_min_m": bounds[0],
            "y_max_m": bounds[1],
            "bottom_z_m": bounds[2],
            "top_z_m": bounds[3],
        },
        "geometry_bounds_xyz_m": [
            [
                tank_center[0] - tank_radius,
                min(tank_center[1] - tank_radius, bounds[0]),
                min(tank_bottom, bounds[2]),
            ],
            [
                external_end_x,
                max(tank_center[1] + tank_radius, bounds[1]),
                max(tank_top, bounds[3]),
            ],
        ],
        "section_angles_rad": angles,
        "surface_names": [surface.name for surface in surfaces],
        "surface_triangle_count": {surface.name: len(surface.tris) for surface in surfaces},
        "stl_paths": [str(tri_dir / f"{surface.name}.stl") for surface in surfaces],
        "surface_edge_audit": audit,
        "signed_volume_m3": volume_m3,
        "signed_volume_by_surface_m3": surface_volumes,
        "approximate_component_volume_m3": expected,
        "relative_signed_volume_check_error": relative_volume_error,
        "notes": [
            "This is a water/air reference geometry prototype only. It does not include butterfly disk, five lamellae, CO2, foam or user CAD.",
            f"The vertical tank center is {list(tank_center)} m with actual bounding box {[[tank_center[0] - tank_radius, tank_center[1] - tank_radius, tank_bottom], [tank_center[0] + tank_radius, tank_center[1] + tank_radius, tank_top]]} m.",
            f"The +x pipe begins at configured centerline mouth {list(port_center)} m, uses the curved tank-wall intersection ring as its back boundary, and ends at x={pipe_end_x:g} m; the tank is not merely rotated from the horizontal case.",
            "Tank bounds are derived from diameter, length and center_xyz_m. Inherited horizontal tank.start_x_m does not define this vertical geometry.",
        ],
    }
    return metadata, surfaces, transition


def build_geometry(config: dict[str, Any], tri_dir: Path) -> dict[str, Any]:
    """Write six audited STLs and return geometry metadata without plotting."""
    metadata, _, _ = _generate_geometry(config, tri_dir.resolve())
    return metadata


def build(
    output: Path,
    config: dict[str, Any] | None = None,
    *,
    preview: bool = True,
) -> dict[str, Any]:
    if config is None:
        config = default_vertical_config()
    output.mkdir(parents=True, exist_ok=False)
    config_path = output / "vertical-geometry-config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    tri_dir = output / "geometry/constant/triSurface"
    metadata, surfaces, transition = _generate_geometry(config, tri_dir)
    metadata["source_config_path"] = str(config_path)
    metadata["preview_images"] = (
        draw_geometry_preview(output, surfaces, metadata, transition) if preview else []
    )
    (output / "vertical-geometry-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path, help="private vertical geometry configuration JSON")
    parser.add_argument("--no-preview", action="store_true", help="write geometry only; skip plots")
    args = parser.parse_args()
    output = (
        args.output
        or ROOT
        / "results/runs"
        / f"i4f-vertical-geometry-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}"
    )
    config = json.loads(args.config.read_text()) if args.config else None
    metadata = build(output.resolve(), config=config, preview=not args.no_preview)
    print(
        json.dumps(
            {
                "output": str(output.resolve()),
                "signed_volume_m3": metadata["signed_volume_m3"],
                "surface_edge_audit": metadata["surface_edge_audit"],
                "preview_images": metadata["preview_images"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
