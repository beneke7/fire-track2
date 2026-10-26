#!/usr/bin/env python3
"""Prepare a parameterized, pressure-driven I4F apparatus case for OpenFOAM v2512.

The case uses compressibleInterFoam with ideal-gas air, constant-density water,
a sealed horizontal tank and a spatially localized, time-varying scalar valve
loss. It does not prescribe a liquid inlet or resolve a butterfly disk/wake.
Each invocation writes a fresh results/runs/i4f-* directory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "experiments/i4f_baseline.json"
DEFAULT_PROFILE = ROOT / "experiments/openfoam/i4f/cold_start_transonic.json"
LEGACY_PROFILE = ROOT / "experiments/openfoam/i4f/legacy_nontransonic.json"
RUNS = (ROOT / "results/runs").resolve()
BASE_ANGLES = 256
TRANSITION_STATIONS = 31
BACKGROUND_PITCH_M = 0.1
BACKGROUND_MARGIN_M = 0.2


def load_profile(path: Path | None) -> dict[str, Any]:
    profile_path = (path or DEFAULT_PROFILE).resolve(strict=True)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("schema") != "openfoam-i4f-case-profile/v1":
        raise ValueError(f"unsupported I4F OpenFOAM profile schema in {profile_path}")
    solver = profile.get("solver", {})
    if solver.get("n_alpha_sub_cycles") != 1:
        raise ValueError("the native alphaPhi0.water volume ledger requires one alpha subcycle")
    if float(solver.get("max_delta_t_s", 0.0)) <= 0.0:
        raise ValueError("profile max_delta_t_s must be positive")
    if float(solver.get("max_co", 0.0)) <= 0.0 or float(solver.get("max_alpha_co", 0.0)) <= 0.0:
        raise ValueError("profile Courant limits must be positive")
    return profile


def validate_supported_orientation(config: dict[str, Any]) -> None:
    """Validate the two supported tank axes and the horizontal discharge direction."""
    tank = config["tank"]
    nozzle = config["nozzle"]
    axis = str(tank.get("axis", "")).lower()

    def require_vector(name: str, value: Any, expected_vector: tuple[float, float, float]) -> None:
        try:
            vector = tuple(float(component) for component in value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} must be the supported unit vector {list(expected_vector)}"
            ) from exc
        if len(vector) != 3 or any(
            not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-9)
            for actual, expected in zip(vector, expected_vector, strict=False)
        ):
            raise ValueError(f"supported geometry requires {name} = {list(expected_vector)}")

    if axis == "horizontal":
        require_vector("tank.axis_vector", tank.get("axis_vector"), (1.0, 0.0, 0.0))
    elif axis == "vertical":
        require_vector("tank.axis_vector", tank.get("axis_vector"), (0.0, 0.0, 1.0))
        try:
            center = tuple(float(component) for component in tank["center_xyz_m"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("vertical tank requires finite tank.center_xyz_m") from exc
        if len(center) != 3 or any(not math.isfinite(value) for value in center):
            raise ValueError("vertical tank.center_xyz_m must contain three finite coordinates")
        if not math.isclose(float(tank["center_z_m"]), center[2], rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("vertical tank.center_z_m must match tank.center_xyz_m[2]")
        try:
            mouth = tuple(
                float(component) for component in config["connection"]["centerline_mouth_xyz_m"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("vertical tank requires connection.centerline_mouth_xyz_m") from exc
        radius = float(tank["diameter_m"]) / 2
        expected_mouth = (center[0] + radius, center[1], float(config["connection"]["center_z_m"]))
        if len(mouth) != 3 or any(
            not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-9)
            for actual, expected in zip(mouth, expected_mouth, strict=False)
        ):
            raise ValueError(
                "vertical side-port mouth must be [tank center x + radius, tank center y, connection center z]"
            )
    else:
        raise ValueError("tank.axis must be 'horizontal' or 'vertical'")

    require_vector("nozzle.direction", nozzle.get("direction"), (1.0, 0.0, 0.0))


def gravity_magnitude(config: dict[str, Any]) -> float:
    value = float(config["gravity_m_s2"])
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("gravity_m_s2 must be a finite positive magnitude")
    return value


def validate_supported_lamellae(config: dict[str, Any]) -> None:
    """Reject a request to include internal lamellae until their geometry is defined."""
    lamellae = config.get("lamellae", {})
    if not isinstance(lamellae, dict):
        raise ValueError("lamellae must be an object containing descriptive hardware metadata")
    included = lamellae.get("included_in_reference", False)
    if not isinstance(included, bool):
        raise ValueError("lamellae.included_in_reference must be a boolean")
    if included:
        raise ValueError(
            "lamellae.included_in_reference=true is unsupported: the generated nozzle has no internal lamellae; "
            "keep reported_count and reported_start_transition_fraction as metadata until plate orientation, "
            "thickness, and outlet termination are specified"
        )


def validate_supported_physics_inputs(config: dict[str, Any]) -> None:
    """Fail when inputs request gas, valve, or wind physics this case omits."""
    gas_kind = str(config.get("gas", {}).get("kind", "")).lower()
    if gas_kind != "air":
        raise ValueError("current thermophysical setup supports gas.kind='air' only")

    opening_law = str(config.get("valve", {}).get("opening_law", "")).lower()
    if opening_law != "smoothstep":
        raise ValueError("current valve source supports valve.opening_law='smoothstep' only")

    try:
        wind = tuple(float(component) for component in config["external"]["wind_velocity_m_s"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "external.wind_velocity_m_s must be the supported still-air vector [0, 0, 0]"
        ) from exc
    if len(wind) != 3 or any(not math.isfinite(component) for component in wind):
        raise ValueError("external.wind_velocity_m_s must contain three finite components")
    if any(abs(component) > 1e-12 for component in wind):
        raise ValueError("current external-air boundary supports still air only")

    minimum_effective_opening(config)


def minimum_effective_opening(config: dict[str, Any]) -> float:
    """Return the finite valve-area floor needed by the scalar loss source."""
    try:
        value = float(config.get("valve", {}).get("minimum_effective_opening", 0.02))
    except (TypeError, ValueError) as exc:
        raise ValueError("valve.minimum_effective_opening must be finite and in (0, 1]") from exc
    if not math.isfinite(value) or not 0.0 < value <= 1.0:
        raise ValueError("valve.minimum_effective_opening must be finite and in (0, 1]")
    return value


def foam_header(obj: str, *, location: str, cls: str = "dictionary") -> str:
    return f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  v2512                                 |
|   \\  /    A nd           | Website:  www.openfoam.com                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    location    "{location}";
    object      {obj};
}}
// ************************************************************************* //
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def git_dirty() -> bool:
    try:
        return bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return True


def polygon_area(points: list[tuple[float, float]]) -> float:
    return 0.5 * abs(
        sum(
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
            for i in range(len(points))
        )
    )


def ray_to_rectangle(
    theta: float, ylo: float, yhi: float, zlo: float, zhi: float, zc: float = 0.65
) -> tuple[float, float]:
    c, s = math.cos(theta), math.sin(theta)
    lambdas: list[float] = []
    if c > 1e-14:
        lambdas.append(yhi / c)
    elif c < -1e-14:
        lambdas.append(ylo / c)
    if s > 1e-14:
        lambdas.append((zhi - zc) / s)
    elif s < -1e-14:
        lambdas.append((zlo - zc) / s)
    lam = min(value for value in lambdas if value > 0.0)
    return lam * c, zc + lam * s


def ray_to_centered_rectangle(
    theta: float, width: float, height: float, zc: float
) -> tuple[float, float]:
    """Sample a rectangle with the loft's normalized L-infinity angle map.

    The superellipse ring converges to this parameterization as its exponent
    tends to infinity, so using the same map at the endpoint avoids pinching
    between differently parameterized rings.
    """
    c, s = math.cos(theta), math.sin(theta)
    scale = max(abs(c), abs(s))
    return width * c / (2.0 * scale), zc + height * s / (2.0 * scale)


def flow_angles(
    width: float, height: float, bounds: tuple[float, float, float, float], zc: float
) -> list[float]:
    ylo, yhi, zlo, zhi = bounds
    vals = {2.0 * math.pi * i / BASE_ANGLES for i in range(BASE_ANGLES)}
    for y in (-width / 2, width / 2):
        for z in (-height / 2, height / 2):
            vals.add(math.atan2(z, y) % (2 * math.pi))
    for y in (ylo, yhi):
        for z in (zlo, zhi):
            vals.add(math.atan2(z - zc, y) % (2 * math.pi))
    return sorted(vals)


def ring_circle(radius: float, zc: float, angles: list[float]) -> list[tuple[float, float]]:
    return [(radius * math.cos(t), zc + radius * math.sin(t)) for t in angles]


def ring_rect(
    width: float, height: float, zc: float, angles: list[float]
) -> list[tuple[float, float]]:
    return [ray_to_centered_rectangle(t, width, height, zc) for t in angles]


def ring_outer(
    bounds: tuple[float, float, float, float], zc: float, angles: list[float]
) -> list[tuple[float, float]]:
    ylo, yhi, zlo, zhi = bounds
    return [ray_to_rectangle(t, ylo, yhi, zlo, zhi, zc) for t in angles]


def tank_port_to_wall_ring(
    radius: float, z_wall: float, port_radius: float, z_port: float, angles: list[float]
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Map port-centered rays to the nested circular tank end-wall boundary."""
    inner = [(port_radius * math.cos(t), z_port + port_radius * math.sin(t)) for t in angles]
    outer = []
    offset = z_port - z_wall
    for t in angles:
        c, s = math.cos(t), math.sin(t)
        projection = offset * s
        distance = -projection + math.sqrt(
            max(0.0, projection * projection + radius * radius - offset * offset)
        )
        outer.append((distance * c, z_port + distance * s))
    return outer, inner


def transition_sections(
    x0: float,
    length: float,
    pipe_radius: float,
    width: float,
    height: float,
    zc: float,
    angles: list[float],
) -> tuple[list[tuple[float, list[tuple[float, float]]]], list[dict[str, float]]]:
    circle = ring_circle(pipe_radius, zc, angles)
    rect = ring_rect(width, height, zc, angles)
    area0, area1 = polygon_area(circle), polygon_area(rect)
    sections, audit = [], []
    for i in range(TRANSITION_STATIONS):
        t = i / (TRANSITION_STATIONS - 1)
        x = x0 + t * length
        target_area = (1 - t) * area0 + t * area1
        half_height = (1 - t) * pipe_radius + t * height / 2
        if i == 0:
            points = circle
        elif i == TRANSITION_STATIONS - 1:
            points = rect
        else:
            exponent = 2.0 / (1.0 - t)
            area_factor = (
                4.0 * math.gamma(1.0 + 1.0 / exponent) ** 2 / math.gamma(1.0 + 2.0 / exponent)
            )
            half_width = target_area / (area_factor * half_height)
            raw = []
            for angle in angles:
                c, s = abs(math.cos(angle)), abs(math.sin(angle))
                radius = (c**exponent + s**exponent) ** (-1.0 / exponent)
                raw.append(
                    (
                        half_width * radius * math.cos(angle),
                        zc + half_height * radius * math.sin(angle),
                    )
                )
            # Correct the discrete polar polygon area horizontally, preserving
            # the prescribed monotonic vertical contraction.
            polygon_scale_y = target_area / polygon_area(raw)
            points = [(polygon_scale_y * y, z) for y, z in raw]
        turns = []
        for j in range(len(points)):
            a, b, c = points[j], points[(j + 1) % len(points)], points[(j + 2) % len(points)]
            turns.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
        if min(turns) < -1e-10:
            raise ValueError(f"transition contour is non-convex at s={t * length:g} m")
        sections.append((x, points))
        audit.append(
            {
                "x_m": x,
                "s_m": t * length,
                "area_mesh_m2": polygon_area(points),
                "area_linear_target_m2": target_area,
                "superellipse_n": (2.0 / (1.0 - t)) if i < TRANSITION_STATIONS - 1 else None,
                "width_m": max(p[0] for p in points) - min(p[0] for p in points),
                "height_m": max(p[1] for p in points) - min(p[1] for p in points),
                "convex_contour": True,
            }
        )
    heights = [row["height_m"] for row in audit]
    widths = [row["width_m"] for row in audit]
    if any(b > a + 1e-10 for a, b in zip(heights, heights[1:])):
        raise ValueError("transition loft violates monotonic vertical contraction")
    if any(b < a - 1e-10 for a, b in zip(widths, widths[1:])):
        raise ValueError("transition loft violates monotonic horizontal expansion")
    return sections, audit


def xyz(x: float, yz: tuple[float, float]) -> tuple[float, float, float]:
    return x, yz[0], yz[1]


def normal(
    a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]
) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    mag = math.sqrt(sum(q * q for q in n))
    return (0.0, 0.0, 0.0) if mag == 0 else tuple(q / mag for q in n)


class Surface:
    def __init__(self, name: str):
        self.name = name
        self.tris: list[tuple[tuple[float, float, float], ...]] = []

    def tri(
        self,
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        c: tuple[float, float, float],
    ) -> None:
        self.tris.append((a, b, c))

    def quad(
        self,
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        c: tuple[float, float, float],
        d: tuple[float, float, float],
    ) -> None:
        self.tri(a, b, c)
        self.tri(a, c, d)

    def write(self, path: Path) -> None:
        with path.open("w", encoding="ascii") as out:
            out.write(f"solid {self.name}\n")
            for tri in self.tris:
                out.write("  facet normal " + " ".join(f"{x:.12g}" for x in normal(*tri)) + "\n")
                out.write("    outer loop\n")
                for p in tri:
                    out.write("      vertex " + " ".join(f"{x:.12g}" for x in p) + "\n")
                out.write("    endloop\n  endfacet\n")
            out.write(f"endsolid {self.name}\n")


def add_cyl_side(surf: Surface, xs: list[float], ring: list[tuple[float, float]]) -> None:
    for x0, x1 in zip(xs[:-1], xs[1:], strict=True):
        for i, p in enumerate(ring):
            q = ring[(i + 1) % len(ring)]
            surf.quad(xyz(x0, p), xyz(x0, q), xyz(x1, q), xyz(x1, p))


def add_disk(
    surf: Surface, x: float, ring: list[tuple[float, float]], center: tuple[float, float], sign: int
) -> None:
    c = (x, center[0], center[1])
    for i, p in enumerate(ring):
        q = ring[(i + 1) % len(ring)]
        surf.tri(c, xyz(x, p), xyz(x, q)) if sign > 0 else surf.tri(c, xyz(x, q), xyz(x, p))


def add_annulus(
    surf: Surface,
    x: float,
    outer: list[tuple[float, float]],
    inner: list[tuple[float, float]],
    sign: int,
) -> None:
    for i in range(len(outer)):
        j = (i + 1) % len(outer)
        a, b, c, d = xyz(x, outer[i]), xyz(x, outer[j]), xyz(x, inner[j]), xyz(x, inner[i])
        surf.quad(a, b, c, d) if sign > 0 else surf.quad(d, c, b, a)


def add_loft_wall(surf: Surface, sections: list[tuple[float, list[tuple[float, float]]]]) -> None:
    for (x0, a), (x1, b) in zip(sections[:-1], sections[1:], strict=True):
        for i in range(len(a)):
            j = (i + 1) % len(a)
            surf.quad(xyz(x0, a[i]), xyz(x0, a[j]), xyz(x1, b[j]), xyz(x1, b[i]))


def surface_edge_audit(surfaces: list[Surface]) -> dict[str, int]:
    edges: dict[tuple[tuple[int, int, int], tuple[int, int, int]], int] = {}
    for surface in surfaces:
        for tri in surface.tris:
            ids = [tuple(round(c * 1e8) for c in point) for point in tri]
            for i in range(3):
                edge = tuple(sorted((ids[i], ids[(i + 1) % 3])))
                edges[edge] = edges.get(edge, 0) + 1
    return {
        "unique_edges": len(edges),
        "boundary_edges": sum(v == 1 for v in edges.values()),
        "nonmanifold_edges": sum(v != 2 for v in edges.values()),
    }


def _build_horizontal_geometry(config: dict[str, Any], tri_dir: Path) -> dict[str, Any]:
    tank, pipe, nozzle, ext = (config[k] for k in ("tank", "pipe", "nozzle", "external"))
    xt0 = float(tank["start_x_m"])
    xt1 = xt0 + float(tank["length_m"])
    xp1 = xt1 + float(pipe["length_m"])
    xe = xp1 + float(pipe["transition_length_m"])
    xe2 = xe + float(ext["length_m"])
    rt = float(tank["diameter_m"]) / 2
    rp = float(pipe["diameter_m"]) / 2
    ztank, zpipe = float(tank["center_z_m"]), float(nozzle["center_z_m"])
    width, height = float(nozzle["width_m"]), float(nozzle["height_m"])
    bounds = (
        -float(ext["half_width_m"]),
        float(ext["half_width_m"]),
        float(ext["bottom_z_m"]),
        float(ext["top_z_m"]),
    )
    angles = flow_angles(width, height, bounds, zpipe)
    pipe_ring_nominal = ring_circle(rp, zpipe, angles)
    # Compensate the finite polygon's inscribed-circle area so the mesh section
    # area matches the analytic circular area used by the reduced model.
    pipe_radius_mesh = rp * math.sqrt(math.pi * rp**2 / polygon_area(pipe_ring_nominal))
    tank_outer, tank_inner = tank_port_to_wall_ring(rt, ztank, pipe_radius_mesh, zpipe, angles)
    pipe_ring = ring_circle(pipe_radius_mesh, zpipe, angles)
    nozzle_ring = ring_rect(width, height, zpipe, angles)
    ext_ring = ring_outer(bounds, zpipe, angles)
    transition, area_audit = transition_sections(
        xp1, float(pipe["transition_length_m"]), pipe_radius_mesh, width, height, zpipe, angles
    )

    tank_s = Surface("tankWall")
    add_cyl_side(tank_s, [xt0 + (xt1 - xt0) * i / 24 for i in range(25)], tank_outer)
    add_disk(tank_s, xt0, tank_outer, (0.0, ztank), -1)
    add_annulus(tank_s, xt1, tank_outer, tank_inner, +1)

    pipe_s = Surface("pipeWall")
    add_cyl_side(pipe_s, [xt1 + (xp1 - xt1) * i / 20 for i in range(21)], pipe_ring)

    transition_s = Surface("transitionWall")
    add_loft_wall(transition_s, transition)

    ext_s = Surface("externalSides")
    ext_stations = [xe + (xe2 - xe) * i / 20 for i in range(21)]
    add_cyl_side(ext_s, ext_stations, ext_ring)

    ambient_s = Surface("ambientAnnulus")
    add_annulus(ambient_s, xe, ext_ring, nozzle_ring, -1)

    outlet_s = Surface("outlet")
    add_disk(outlet_s, xe2, ext_ring, (0.0, (bounds[2] + bounds[3]) / 2), +1)

    surfaces = [tank_s, pipe_s, transition_s, ext_s, ambient_s, outlet_s]
    for surf in surfaces:
        surf.write(tri_dir / f"{surf.name}.stl")
    closure = surface_edge_audit(surfaces)
    if closure["boundary_edges"] or closure["nonmanifold_edges"]:
        raise ValueError(f"fluid boundary is not closed/manifold: {closure}")
    background_bounds = {
        "minimum_xyz_m": [
            xt0 - BACKGROUND_MARGIN_M,
            -float(ext["half_width_m"]) - BACKGROUND_MARGIN_M,
            float(ext["bottom_z_m"]) - BACKGROUND_MARGIN_M,
        ],
        "maximum_xyz_m": [
            xe2 + BACKGROUND_MARGIN_M,
            float(ext["half_width_m"]) + BACKGROUND_MARGIN_M,
            float(ext["top_z_m"]) + BACKGROUND_MARGIN_M,
        ],
        "margin_m": BACKGROUND_MARGIN_M,
    }
    return {
        "surfaces": surfaces,
        "closure": closure,
        "angles": angles,
        "transition": transition,
        "area_audit": area_audit,
        "x_tank_start_m": xt0,
        "x_tank_end_m": xt1,
        "x_pipe_end_m": xp1,
        "x_exit_m": xe,
        "x_external_end_m": xe2,
        "background_bounds_m": background_bounds,
        "pipe_area_m2": polygon_area(pipe_ring),
        "pipe_radius_mesh_m": pipe_radius_mesh,
        "pipe_radius_polygon_correction_fraction": pipe_radius_mesh / rp - 1.0,
        "nozzle_area_m2": polygon_area(nozzle_ring),
        "triangle_counts": {s.name: len(s.tris) for s in surfaces},
    }


def _build_vertical_geometry(config: dict[str, Any], tri_dir: Path) -> dict[str, Any]:
    """Adapt the standalone curved-side-port builder to the common case API."""
    import sys

    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from prepare_i4f_vertical_geometry import build_geometry as build_vertical_stls

    metadata = build_vertical_stls(config, tri_dir)
    tank = metadata["tank"]
    port = metadata["port"]
    pipe = metadata["pipe"]
    transition = metadata["transition"]
    external = metadata["external"]
    bbox = metadata["geometry_bounds_xyz_m"]
    area_audit = transition["section_audit"]
    margin = BACKGROUND_MARGIN_M
    pipe_radius = float(pipe["diameter_m"]) / 2
    center = tank["center_xyz_m"]
    port_center = port["centerline_mouth_xyz_m"]
    ring_points = metadata["junction"]["port_ring_points_xyz_m"]
    background_lo = [
        float(value) - BACKGROUND_MARGIN_M for value in metadata["geometry_bounds_xyz_m"][0]
    ]
    background_hi = [
        float(value) + BACKGROUND_MARGIN_M for value in metadata["geometry_bounds_xyz_m"][1]
    ]
    background_cells = [
        round((background_hi[i] - background_lo[i]) / BACKGROUND_PITCH_M) for i in range(3)
    ]
    background_pitch = [
        (background_hi[i] - background_lo[i]) / background_cells[i] for i in range(3)
    ]
    seed_cell = [
        math.floor((float(center[i]) - background_lo[i]) / background_pitch[i]) for i in range(3)
    ]
    # Keep the seed in the center cell, but away from the Cartesian grid faces.
    # A seed at the cylinder center can land exactly on multiple blockMesh planes
    # (for example x=z=1.5 m on the current 0.1 m lattice), which snappyHexMesh
    # cannot assign uniquely to a cell.
    seed_fraction = (0.37, 0.43, 0.31)
    seed_point = [
        background_lo[i] + (seed_cell[i] + seed_fraction[i]) * background_pitch[i] for i in range(3)
    ]
    if math.hypot(seed_point[0] - float(center[0]), seed_point[1] - float(center[1])) >= float(
        tank["diameter_m"]
    ) / 2 or not float(tank["bottom_z_m"]) < seed_point[2] < float(tank["top_z_m"]):
        raise ValueError("could not place a non-grid-aligned snappy seed inside the vertical tank")
    return {
        "surfaces": [],
        "closure": metadata["surface_edge_audit"],
        "angles": metadata["section_angles_rad"],
        "transition": [],
        "area_audit": area_audit,
        "x_tank_start_m": float(tank["actual_bbox_xyz_m"][0][0]),
        "x_tank_end_m": float(tank["actual_bbox_xyz_m"][1][0]),
        "x_pipe_end_m": float(pipe["centerline_x_end_m"]),
        "x_exit_m": float(transition["end_x_m"]),
        "x_external_end_m": float(external["end_x_m"]),
        "background_bounds_m": {
            "minimum_xyz_m": [float(value) - margin for value in bbox[0]],
            "maximum_xyz_m": [float(value) + margin for value in bbox[1]],
            "margin_m": margin,
        },
        "pipe_area_m2": float(area_audit[0]["area_mesh_m2"]),
        "pipe_radius_mesh_m": pipe_radius,
        "pipe_radius_polygon_correction_fraction": 0.0,
        "nozzle_area_m2": float(area_audit[-1]["area_mesh_m2"]),
        "triangle_counts": metadata["surface_triangle_count"],
        "vertical_geometry": metadata,
        "tank_bounds_xyz_m": tank["actual_bbox_xyz_m"],
        "tank_center_xyz_m": center,
        "tank_bottom_z_m": float(tank["bottom_z_m"]),
        "tank_top_z_m": float(tank["top_z_m"]),
        "port_centerline_mouth_xyz_m": port_center,
        "port_stub_min_x_m": min(float(point[0]) for point in ring_points),
        "port_ring_mean_x_m": sum(float(point[0]) for point in ring_points) / len(ring_points),
        "line_zone_prefill_volume_m3": float(
            metadata["approximate_component_volume_m3"]["curved_start_pipe_extension_m3"]
            + metadata["approximate_component_volume_m3"]["transition_m3"]
        ),
        "port_stub_volume_m3": float(
            pipe["diameter_m"] ** 2
            * math.pi
            / 4
            * (
                port_center[0]
                - metadata["approximate_component_volume_m3"]["pipe_connection_mean_start_x_m"]
            )
        ),
        "seed_point_xyz_m": seed_point,
    }


def build_geometry(config: dict[str, Any], tri_dir: Path) -> dict[str, Any]:
    """Build supported horizontal or vertical apparatus geometry."""
    validate_supported_orientation(config)
    validate_supported_lamellae(config)
    if str(config["tank"]["axis"]).lower() == "vertical":
        return _build_vertical_geometry(config, tri_dir)
    return _build_horizontal_geometry(config, tri_dir)


def block_mesh_dict(geom: dict[str, Any]) -> str:
    lo = tuple(geom["background_bounds_m"]["minimum_xyz_m"])
    hi = tuple(geom["background_bounds_m"]["maximum_xyz_m"])
    n = [round((hi[i] - lo[i]) / BACKGROUND_PITCH_M) for i in range(3)]
    return (
        foam_header("blockMeshDict", location="system")
        + f"""
convertToMeters 1;
vertices
(
    ({lo[0]} {lo[1]} {lo[2]}) ({hi[0]} {lo[1]} {lo[2]})
    ({hi[0]} {hi[1]} {lo[2]}) ({lo[0]} {hi[1]} {lo[2]})
    ({lo[0]} {lo[1]} {hi[2]}) ({hi[0]} {lo[1]} {hi[2]})
    ({hi[0]} {hi[1]} {hi[2]}) ({lo[0]} {hi[1]} {hi[2]})
);
blocks (hex (0 1 2 3 4 5 6 7) ({n[0]} {n[1]} {n[2]}) simpleGrading (1 1 1));
edges ();
boundary
(
    backgroundBoundary
    {{
        type patch;
        faces ((0 4 7 3) (1 2 6 5) (0 1 5 4)
               (3 7 6 2) (0 3 2 1) (4 5 6 7));
    }}
);
mergePatchPairs ();
"""
    )


def surface_feature_extract_dict() -> str:
    return (
        foam_header("surfaceFeatureExtractDict", location="system")
        + """
pipeWall.stl
{
    extractionMethod extractFromSurface;
    includedAngle 150;
    subsetFeatures { nonManifoldEdges yes; openEdges yes; }
    trimFeatures { minElem 0; minLen 0; }
    writeObj yes;
}
transitionWall.stl
{
    extractionMethod extractFromSurface;
    includedAngle 150;
    subsetFeatures { nonManifoldEdges yes; openEdges yes; }
    trimFeatures { minElem 0; minLen 0; }
    writeObj yes;
}
tankWall.stl
{
    extractionMethod extractFromSurface;
    includedAngle 150;
    subsetFeatures { nonManifoldEdges yes; openEdges yes; }
    trimFeatures { minElem 0; minLen 0; }
    writeObj yes;
}
"""
    )


def snappy_dict(config: dict[str, Any], geom: dict[str, Any]) -> str:
    if str(config["tank"].get("axis", "horizontal")).lower() == "vertical":
        return vertical_snappy_dict(config, geom)
    tank, pipe, nozzle = (config[k] for k in ("tank", "pipe", "nozzle"))
    x0, xt1, xp1, xe, xe2 = (
        geom["x_tank_start_m"],
        geom["x_tank_end_m"],
        geom["x_pipe_end_m"],
        geom["x_exit_m"],
        geom["x_external_end_m"],
    )
    rt = float(tank["diameter_m"]) / 2
    rp = float(pipe["diameter_m"]) / 2
    zt, zp = float(tank["center_z_m"]), float(nozzle["center_z_m"])
    W, H = float(nozzle["width_m"]), float(nozzle["height_m"])
    port_xlo, port_xhi = xt1 - 0.18, xt1 + 0.20
    port_yhalf, port_zhalf = rp + 0.055, 0.19
    lip_xlo, lip_xhi = xe - 0.16, xe + 0.02
    lip_yhalf, lip_zhalf = W / 2 + 0.03, H / 2 + 0.055
    return (
        foam_header("snappyHexMeshDict", location="system")
        + f"""
castellatedMesh true;
snap true;
addLayers false;
geometry
{{
    tankWall.stl {{ type triSurfaceMesh; name tankWall; }}
    pipeWall.stl {{ type triSurfaceMesh; name pipeWall; }}
    transitionWall.stl {{ type triSurfaceMesh; name transitionWall; }}
    externalSides.stl {{ type triSurfaceMesh; name externalSides; }}
    ambientAnnulus.stl {{ type triSurfaceMesh; name ambientAnnulus; }}
    outlet.stl {{ type triSurfaceMesh; name outlet; }}
    tankFine {{ type searchableBox; min ({x0} {-rt} {zt - rt}); max ({xt1} {rt} {zt + rt}); }}
    pipeFine {{ type searchableBox; min ({xt1} {-rp - 0.02} {zp - rp - 0.02}); max ({xp1} {rp + 0.02} {zp + rp + 0.02}); }}
    transitionFine {{ type searchableBox; min ({xp1} {-W / 2 - 0.02} {zp - H / 2 - 0.02}); max ({xe} {W / 2 + 0.02} {zp + H / 2 + 0.02}); }}
    jetFine {{ type searchableBox; min ({xe} {-0.65} {zp - 0.35}); max ({min(xe2, xe + 0.8)} {0.65} {zp + 0.35}); }}
    portFine {{ type searchableBox; min ({port_xlo} {-port_yhalf} {zp - port_zhalf}); max ({port_xhi} {port_yhalf} {zp + port_zhalf}); }}
    lipFine {{ type searchableBox; min ({lip_xlo} {-lip_yhalf} {zp - lip_zhalf}); max ({lip_xhi} {lip_yhalf} {zp + lip_zhalf}); }}
}}
castellatedMeshControls
{{
    maxLocalCells 600000;
    maxGlobalCells 1800000;
    minRefinementCells 0;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 2;
    features
    (
        {{ file "pipeWall.eMesh"; level 2; }}
        {{ file "transitionWall.eMesh"; level 2; }}
        {{ file "tankWall.eMesh"; level 2; }}
    );
    refinementSurfaces
    {{
        tankWall {{ level (1 1); patchInfo {{ type wall; }} }}
        pipeWall {{ level (2 2); patchInfo {{ type wall; }} }}
        transitionWall {{ level (2 2); patchInfo {{ type wall; }} }}
        externalSides {{ level (1 1); patchInfo {{ type patch; }} }}
        ambientAnnulus {{ level (1 1); patchInfo {{ type patch; }} }}
        outlet {{ level (1 1); patchInfo {{ type patch; }} }}
    }}
    resolveFeatureAngle 30;
    refinementRegions
    {{
        tankFine {{ mode inside; levels ((1e15 1)); }}
        pipeFine {{ mode inside; levels ((1e15 2)); }}
        transitionFine {{ mode inside; levels ((1e15 2)); }}
        jetFine {{ mode inside; levels ((1e15 2)); }}
        portFine {{ mode inside; levels ((1e15 3)); }}
        lipFine {{ mode inside; levels ((1e15 3)); }}
    }}
    // Keep the seed strictly inside a tank cell, away from the 0.1 m background lattice.
    locationInMesh (1.05 0.025 1.05);
    allowFreeStandingZoneFaces true;
}}
snapControls
{{
    nSmoothPatch 4;
    tolerance 2.0;
    nSolveIter 40;
    nRelaxIter 6;
    nFeatureSnapIter 20;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap true;
}}
addLayersControls
{{
    relativeSizes true;
    layers {{}}
    expansionRatio 1.0;
    finalLayerThickness 0.3;
    minThickness 0.1;
    nGrow 0;
    featureAngle 60;
    slipFeatureAngle 30;
    nRelaxIter 3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 0;
}}
meshQualityControls
{{
    #includeEtc "caseDicts/meshQualityDict"
    nSmoothScale 4;
    errorReduction 0.75;
}}
writeFlags (scalarLevels layerSets layerFields);
mergeTolerance 1e-6;
"""
    )


def vertical_snappy_dict(config: dict[str, Any], geom: dict[str, Any]) -> str:
    tank, pipe, nozzle = (config[k] for k in ("tank", "pipe", "nozzle"))
    meta = geom["vertical_geometry"]
    bounds = geom["tank_bounds_xyz_m"]
    pipe_meta = meta["pipe"]
    port = meta["port"]
    external = meta["external"]
    center_y = float(pipe_meta["center_y_m"])
    port_z = float(port["center_z_m"])
    mouth_x = float(port["centerline_mouth_xyz_m"][0])
    pipe_end_x = float(pipe_meta["centerline_x_end_m"])
    transition_end_x = float(meta["transition"]["end_x_m"])
    external_end_x = float(external["end_x_m"])
    rp = float(pipe["diameter_m"]) / 2
    width, height = float(nozzle["width_m"]), float(nozzle["height_m"])
    tank_lo, tank_hi = bounds
    port_xlo, port_xhi = mouth_x - 0.18, mouth_x + 0.20
    port_yhalf, port_zhalf = rp + 0.055, 0.19
    lip_xlo, lip_xhi = transition_end_x - 0.16, transition_end_x + 0.02
    lip_yhalf, lip_zhalf = width / 2 + 0.03, height / 2 + 0.055
    stub_lo = geom["port_stub_min_x_m"] - 0.02
    external_ylo, external_yhi = float(external["y_min_m"]), float(external["y_max_m"])
    seed = geom["seed_point_xyz_m"]
    return (
        foam_header("snappyHexMeshDict", location="system")
        + f"""
castellatedMesh true;
snap true;
addLayers false;
geometry
{{
    tankWall.stl {{ type triSurfaceMesh; name tankWall; }}
    pipeWall.stl {{ type triSurfaceMesh; name pipeWall; }}
    transitionWall.stl {{ type triSurfaceMesh; name transitionWall; }}
    externalSides.stl {{ type triSurfaceMesh; name externalSides; }}
    ambientAnnulus.stl {{ type triSurfaceMesh; name ambientAnnulus; }}
    outlet.stl {{ type triSurfaceMesh; name outlet; }}
    tankFine {{ type searchableBox; min ({tank_lo[0]} {tank_lo[1]} {tank_lo[2]}); max ({tank_hi[0]} {tank_hi[1]} {tank_hi[2]}); }}
    pipeFine {{ type searchableBox; min ({stub_lo} {center_y - rp - 0.02} {port_z - rp - 0.02}); max ({pipe_end_x} {center_y + rp + 0.02} {port_z + rp + 0.02}); }}
    transitionFine {{ type searchableBox; min ({pipe_end_x} {center_y - width / 2 - 0.02} {port_z - height / 2 - 0.02}); max ({transition_end_x} {center_y + width / 2 + 0.02} {port_z + height / 2 + 0.02}); }}
    jetFine {{ type searchableBox; min ({transition_end_x} {max(external_ylo, center_y - 0.65)} {port_z - 0.35}); max ({min(external_end_x, transition_end_x + 0.8)} {min(external_yhi, center_y + 0.65)} {port_z + 0.35}); }}
    portFine {{ type searchableBox; min ({port_xlo} {center_y - port_yhalf} {port_z - port_zhalf}); max ({port_xhi} {center_y + port_yhalf} {port_z + port_zhalf}); }}
    lipFine {{ type searchableBox; min ({lip_xlo} {center_y - lip_yhalf} {port_z - lip_zhalf}); max ({lip_xhi} {center_y + lip_yhalf} {port_z + lip_zhalf}); }}
}}
castellatedMeshControls
{{
    maxLocalCells 600000;
    maxGlobalCells 1800000;
    minRefinementCells 0;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 2;
    features
    (
        {{ file "pipeWall.eMesh"; level 2; }}
        {{ file "transitionWall.eMesh"; level 2; }}
        {{ file "tankWall.eMesh"; level 2; }}
    );
    refinementSurfaces
    {{
        tankWall {{ level (1 1); patchInfo {{ type wall; }} }}
        pipeWall {{ level (2 2); patchInfo {{ type wall; }} }}
        transitionWall {{ level (2 2); patchInfo {{ type wall; }} }}
        externalSides {{ level (1 1); patchInfo {{ type patch; }} }}
        ambientAnnulus {{ level (1 1); patchInfo {{ type patch; }} }}
        outlet {{ level (1 1); patchInfo {{ type patch; }} }}
    }}
    resolveFeatureAngle 30;
    refinementRegions
    {{
        tankFine {{ mode inside; levels ((1e15 1)); }}
        pipeFine {{ mode inside; levels ((1e15 2)); }}
        transitionFine {{ mode inside; levels ((1e15 2)); }}
        jetFine {{ mode inside; levels ((1e15 2)); }}
        portFine {{ mode inside; levels ((1e15 3)); }}
        lipFine {{ mode inside; levels ((1e15 3)); }}
    }}
    // Seed lies inside the vertical cylinder, clear of its tank/pipe intersection.
    locationInMesh ({seed[0]} {seed[1]} {seed[2]});
    allowFreeStandingZoneFaces true;
}}
snapControls
{{
    nSmoothPatch 4;
    tolerance 2.0;
    nSolveIter 40;
    nRelaxIter 6;
    nFeatureSnapIter 20;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap true;
}}
addLayersControls
{{
    relativeSizes true;
    layers {{}}
    expansionRatio 1.0;
    finalLayerThickness 0.3;
    minThickness 0.1;
    nGrow 0;
    featureAngle 60;
    slipFeatureAngle 30;
    nRelaxIter 3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 0;
}}
meshQualityControls
{{
    #includeEtc "caseDicts/meshQualityDict"
    nSmoothScale 4;
    errorReduction 0.75;
}}
writeFlags (scalarLevels layerSets layerFields);
mergeTolerance 1e-6;
"""
    )


def segment_height(radius: float, fraction: float) -> float:
    lo, hi = -1.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        upper = (math.acos(mid) - mid * math.sqrt(max(0.0, 1 - mid * mid))) / math.pi
        if 1 - upper < fraction:
            lo = mid
        else:
            hi = mid
    return radius * (lo + hi) / 2


def set_fields_dict(config: dict[str, Any], geom: dict[str, Any]) -> str:
    if str(config["tank"].get("axis", "horizontal")).lower() == "vertical":
        return vertical_set_fields_dict(config, geom)
    tank, pipe, nozzle = (config[k] for k in ("tank", "pipe", "nozzle"))
    x0, xt1, xe = geom["x_tank_start_m"], geom["x_tank_end_m"], geom["x_exit_m"]
    rt, rp = float(tank["diameter_m"]) / 2, float(pipe["diameter_m"]) / 2
    zt, zp = float(tank["center_z_m"]), float(nozzle["center_z_m"])
    fill = float(tank["fill_fraction"])
    surface_z = zt + segment_height(rt, fill)
    p0, pamb = (
        float(config["gas"]["initial_absolute_pressure_Pa"]),
        float(config["gas"]["ambient_pressure_Pa"]),
    )
    xvalve = float(config["valve"]["location_x_m"])
    va, vb = xvalve - 0.05, xvalve + 0.05
    temp = float(config["gas"]["temperature_K"])
    return (
        foam_header("setFieldsDict", location="system")
        + f"""
defaultFieldValues
(
    volScalarFieldValue alpha.water 0
    volScalarFieldValue p {pamb:.12g}
    volScalarFieldValue p_rgh {pamb:.12g}
    volScalarFieldValue T {temp:.12g}
    volVectorFieldValue U (0 0 0)
);
regions
(
    // Lower tank segment; the generated cylindrical wall clips this box.
    boxToCell
    {{
        box ({x0 - 0.01} {-rt - 0.01} {zt - rt - 0.01}) ({xt1 + 0.01} {rt + 0.01} {surface_z:.12g});
        fieldValues (volScalarFieldValue alpha.water 1);
    }}
    // Wet-start fill through pipe, transition and rectangular passage; stop at the outlet lip.
    boxToCell
    {{
        box ({xt1} {-float(nozzle["width_m"]) / 2 - 0.02} {zp - rp - 0.02})
            ({xe} {float(nozzle["width_m"]) / 2 + 0.02} {zp + rp + 0.02});
        fieldValues
        (
            volScalarFieldValue alpha.water 1
            volScalarFieldValue p {pamb:.12g}
            volScalarFieldValue p_rgh {pamb:.12g}
        );
    }}
    // Pressure fields here are seeds only; setExprFields replaces p and p_rgh after meshing.
    boxToCell
    {{
        box ({x0 - 0.01} {-rt - 0.02} {zt - rt - 0.02}) ({va} {rt + 0.02} {zt + rt + 0.02});
        fieldValues
        (
            volScalarFieldValue p {p0:.12g}
            volScalarFieldValue p_rgh {p0:.12g}
        );
    }}
    // A spatially monotonic pressure seed across the finite loss zone.
    boxToCell
    {{
        box ({va} {-rp - 0.02} {zp - rp - 0.02}) ({vb} {rp + 0.02} {zt + rt + 0.02});
        fieldValues
        (
            volScalarFieldValue p {(p0 + pamb) / 2:.12g}
            volScalarFieldValue p_rgh {(p0 + pamb) / 2:.12g}
        );
    }}
);
// Downstream pipe/transition/nozzle prefill is approximately 0.1984 m3.
// This wet-start is not in hydrostatic equilibrium with the pressurized tank;
// setExprFields initializes each side of the valve hydrostatically.
// Calculated 70%-fill free surface z={surface_z:.12g} m.
"""
    )


def vertical_set_fields_dict(config: dict[str, Any], geom: dict[str, Any]) -> str:
    tank, pipe, nozzle = (config[k] for k in ("tank", "pipe", "nozzle"))
    meta = geom["vertical_geometry"]
    tank_lo, tank_hi = geom["tank_bounds_xyz_m"]
    port = meta["port"]["centerline_mouth_xyz_m"]
    port_y, port_z = float(port[1]), float(port[2])
    rp = float(pipe["diameter_m"]) / 2
    width = float(nozzle["width_m"])
    surface_z = geom["tank_bottom_z_m"] + float(tank["fill_fraction"]) * float(tank["length_m"])
    p0 = float(config["gas"]["initial_absolute_pressure_Pa"])
    pamb = float(config["gas"]["ambient_pressure_Pa"])
    xvalve = float(config["valve"]["location_x_m"])
    va, vb = xvalve - 0.05, xvalve + 0.05
    temp = float(config["gas"]["temperature_K"])
    stub_x = geom["port_stub_min_x_m"] - 0.01
    xe = geom["x_exit_m"]
    return (
        foam_header("setFieldsDict", location="system")
        + f"""
defaultFieldValues
(
    volScalarFieldValue alpha.water 0
    volScalarFieldValue p {pamb:.12g}
    volScalarFieldValue p_rgh {pamb:.12g}
    volScalarFieldValue T {temp:.12g}
    volVectorFieldValue U (0 0 0)
);
regions
(
    // The generated vertical cylinder clips this lower-tank fill box.
    boxToCell
    {{
        box ({tank_lo[0] - 0.01} {tank_lo[1] - 0.01} {tank_lo[2] - 0.01})
            ({tank_hi[0] + 0.01} {tank_hi[1] + 0.01} {surface_z:.12g});
        fieldValues (volScalarFieldValue alpha.water 1);
    }}
    // Wet-start through the curved side port, pipe, transition and nozzle lip.
    boxToCell
    {{
        box ({stub_x} {port_y - width / 2 - 0.02} {port_z - rp - 0.02})
            ({xe} {port_y + width / 2 + 0.02} {port_z + rp + 0.02});
        fieldValues
        (
            volScalarFieldValue alpha.water 1
            volScalarFieldValue p {pamb:.12g}
            volScalarFieldValue p_rgh {pamb:.12g}
        );
    }}
    // Pressure seeds are replaced by the piecewise hydrostatic expressions below.
    boxToCell
    {{
        box ({tank_lo[0] - 0.01} {tank_lo[1] - 0.01} {tank_lo[2] - 0.01})
            ({tank_hi[0] + 0.01} {tank_hi[1] + 0.01} {tank_hi[2] + 0.01});
        fieldValues
        (
            volScalarFieldValue p {p0:.12g}
            volScalarFieldValue p_rgh {p0:.12g}
        );
    }}
    boxToCell
    {{
        box ({va} {port_y - rp - 0.02} {port_z - rp - 0.02})
            ({vb} {port_y + rp + 0.02} {port_z + rp + 0.02});
        fieldValues
        (
            volScalarFieldValue p {(p0 + pamb) / 2:.12g}
            volScalarFieldValue p_rgh {(p0 + pamb) / 2:.12g}
        );
    }}
);
// Vertical tank free surface: z={surface_z:.12g} m.
// Downstream line volume includes the curved-wall pipe extension.
// The wet start is not hydrostatically equilibrated across the finite valve loss.
"""
    )


def set_expr_fields_dict(config: dict[str, Any], geom: dict[str, Any]) -> str:
    """Initialize physical p and p_rgh consistently for the wet-start layout.

    Water columns on either side of the finite valve-loss zone are initialized
    hydrostatically. The sealed tank gas uses its ideal-gas density evaluated at
    the initial pressure; the short ambient region uses ambient ideal-gas density.
    """
    if str(config["tank"].get("axis", "horizontal")).lower() == "vertical":
        return vertical_set_expr_fields_dict(config, geom)
    tank, pipe, nozzle = (config[k] for k in ("tank", "pipe", "nozzle"))
    x0 = float(tank["start_x_m"])
    xt1 = geom["x_tank_end_m"]
    va = float(config["valve"]["location_x_m"]) - 0.05
    vb = float(config["valve"]["location_x_m"]) + 0.05
    xe = geom["x_exit_m"]
    zt, rt = float(tank["center_z_m"]), float(tank["diameter_m"]) / 2
    fill = float(tank["fill_fraction"])
    surface_z = zt + segment_height(rt, fill)
    zexit = float(nozzle["center_z_m"])
    p0 = float(config["gas"]["initial_absolute_pressure_Pa"])
    pamb = float(config["gas"]["ambient_pressure_Pa"])
    temp = float(config["gas"]["temperature_K"])
    rho_w = float(config["liquid"]["density_kg_m3"])
    molar_mass = 0.02896546
    gas_constant = 8.314462618
    rho_gas = p0 * molar_mass / (gas_constant * temp)
    rho_amb = pamb * molar_mass / (gas_constant * temp)
    gravity = gravity_magnitude(config)

    regions = [
        (
            "tankWater",
            f"(pos().x() >= {x0:.12g}) && (pos().x() < {xt1:.12g}) && (pos().z() < {surface_z:.12g})",
            f"{p0:.12g} + {rho_w:.12g}*{gravity:.12g}*({surface_z:.12g} - pos().z())",
            f"{p0 + rho_w * gravity * surface_z:.12g}",
        ),
        (
            "tankGas",
            f"(pos().x() >= {x0:.12g}) && (pos().x() < {xt1:.12g}) && (pos().z() >= {surface_z:.12g})",
            f"{p0:.12g} + {rho_gas:.12g}*{gravity:.12g}*({surface_z:.12g} - pos().z())",
            f"{p0 + rho_gas * gravity * surface_z:.12g}",
        ),
        (
            "upstreamWetLine",
            f"(pos().x() >= {xt1:.12g}) && (pos().x() < {va:.12g})",
            f"{p0:.12g} + {rho_w:.12g}*{gravity:.12g}*({surface_z:.12g} - pos().z())",
            f"{p0 + rho_w * gravity * surface_z:.12g}",
        ),
        (
            "valveZone",
            f"(pos().x() >= {va:.12g}) && (pos().x() <= {vb:.12g})",
            f"(1 - (pos().x() - {va:.12g})/{vb - va:.12g})*({p0:.12g} + {rho_w:.12g}*{gravity:.12g}*({surface_z:.12g} - pos().z())) + ((pos().x() - {va:.12g})/{vb - va:.12g})*({pamb:.12g} + {rho_w:.12g}*{gravity:.12g}*({zexit:.12g} - pos().z()))",
            f"(1 - (pos().x() - {va:.12g})/{vb - va:.12g})*({p0 + rho_w * gravity * surface_z:.12g}) + ((pos().x() - {va:.12g})/{vb - va:.12g})*({pamb + rho_w * gravity * zexit:.12g})",
        ),
        (
            "downstreamWetLine",
            f"(pos().x() > {vb:.12g}) && (pos().x() <= {xe:.12g})",
            f"{pamb:.12g} + {rho_w:.12g}*{gravity:.12g}*({zexit:.12g} - pos().z())",
            f"{pamb + rho_w * gravity * zexit:.12g}",
        ),
        (
            "externalAir",
            f"pos().x() > {xe:.12g}",
            f"{pamb:.12g} + {rho_amb:.12g}*{gravity:.12g}*({zexit:.12g} - pos().z())",
            f"{pamb + rho_amb * gravity * zexit:.12g}",
        ),
    ]
    expressions = []
    for name, mask, pressure, _ in regions:
        expressions.append(
            f"    {name}Pressure\n    {{\n"
            f"        field p;\n"
            f"        dimensions [1 -1 -2 0 0 0 0];\n"
            f"        fieldMask #{{ {mask} #}};\n"
            f"        expression #{{ {pressure} #}};\n"
            f"    }}\n"
        )
    for name, mask, _, p_rgh in regions:
        expressions.append(
            f"    {name}ReducedPressure\n    {{\n"
            f"        field p_rgh;\n"
            f"        dimensions [1 -1 -2 0 0 0 0];\n"
            f"        fieldMask #{{ {mask} #}};\n"
            f"        expression #{{ {p_rgh} #}};\n"
            f"    }}\n"
        )
    return foam_header("setExprFieldsDict", location="system") + (
        "expressions\n(\n" + "".join(expressions) + ");\n"
    )


def vertical_set_expr_fields_dict(config: dict[str, Any], geom: dict[str, Any]) -> str:
    """Initialize a vertical tank, its curved side-port stub and +x discharge line."""
    tank, pipe, nozzle = (config[k] for k in ("tank", "pipe", "nozzle"))
    center_x, center_y, _ = (float(value) for value in geom["tank_center_xyz_m"])
    tank_radius = float(tank["diameter_m"]) / 2
    bottom, top = float(geom["tank_bottom_z_m"]), float(geom["tank_top_z_m"])
    surface_z = bottom + float(tank["fill_fraction"]) * float(tank["length_m"])
    port = geom["vertical_geometry"]["port"]
    mouth_x, port_y, port_z = (float(value) for value in port["centerline_mouth_xyz_m"])
    stub_x = float(geom["port_stub_min_x_m"])
    pipe_radius = float(pipe["diameter_m"]) / 2
    valve_x = float(config["valve"]["location_x_m"])
    va, vb = valve_x - 0.05, valve_x + 0.05
    exit_x = float(geom["x_exit_m"])
    width = float(nozzle["width_m"])
    p0 = float(config["gas"]["initial_absolute_pressure_Pa"])
    pamb = float(config["gas"]["ambient_pressure_Pa"])
    temperature = float(config["gas"]["temperature_K"])
    rho_water = float(config["liquid"]["density_kg_m3"])
    molar_mass_air = 0.02896546
    universal_gas_constant = 8.314462618
    rho_gas = p0 * molar_mass_air / (universal_gas_constant * temperature)
    rho_ambient = pamb * molar_mass_air / (universal_gas_constant * temperature)
    gravity = gravity_magnitude(config)

    tank_radial_squared = (
        f"((pos().x() - {center_x:.12g})*(pos().x() - {center_x:.12g}) + "
        f"(pos().y() - {center_y:.12g})*(pos().y() - {center_y:.12g}))"
    )
    port_radial_squared = (
        f"((pos().y() - {port_y:.12g})*(pos().y() - {port_y:.12g}) + "
        f"(pos().z() - {port_z:.12g})*(pos().z() - {port_z:.12g}))"
    )
    tank_cylinder = (
        f"({tank_radial_squared} <= {tank_radius**2:.12g}) && "
        f"(pos().z() >= {bottom:.12g}) && (pos().z() <= {top:.12g})"
    )
    pipe_section = f"({port_radial_squared} <= {pipe_radius**2:.12g})"
    regions = [
        (
            "tankWater",
            f"({tank_cylinder}) && (pos().z() < {surface_z:.12g})",
            f"{p0:.12g} + {rho_water:.12g}*{gravity:.12g}*({surface_z:.12g} - pos().z())",
            f"{p0 + rho_water * gravity * surface_z:.12g}",
        ),
        (
            "tankGas",
            f"({tank_cylinder}) && (pos().z() >= {surface_z:.12g})",
            f"{p0:.12g} + {rho_gas:.12g}*{gravity:.12g}*({surface_z:.12g} - pos().z())",
            f"{p0 + rho_gas * gravity * surface_z:.12g}",
        ),
        (
            "curvedPortStub",
            f"(pos().x() >= {stub_x:.12g}) && (pos().x() < {mouth_x:.12g}) && "
            f"{pipe_section} && ({tank_radial_squared} > {tank_radius**2:.12g})",
            f"{p0:.12g} + {rho_water:.12g}*{gravity:.12g}*({surface_z:.12g} - pos().z())",
            f"{p0 + rho_water * gravity * surface_z:.12g}",
        ),
        (
            "upstreamWetLine",
            f"(pos().x() >= {mouth_x:.12g}) && (pos().x() < {va:.12g}) && {pipe_section}",
            f"{p0:.12g} + {rho_water:.12g}*{gravity:.12g}*({surface_z:.12g} - pos().z())",
            f"{p0 + rho_water * gravity * surface_z:.12g}",
        ),
        (
            "valveZone",
            f"(pos().x() >= {va:.12g}) && (pos().x() <= {vb:.12g}) && {pipe_section}",
            f"(1 - (pos().x() - {va:.12g})/{vb - va:.12g})*({p0:.12g} + {rho_water:.12g}*{gravity:.12g}*({surface_z:.12g} - pos().z())) + ((pos().x() - {va:.12g})/{vb - va:.12g})*({pamb:.12g} + {rho_water:.12g}*{gravity:.12g}*({port_z:.12g} - pos().z()))",
            f"(1 - (pos().x() - {va:.12g})/{vb - va:.12g})*({p0 + rho_water * gravity * surface_z:.12g}) + ((pos().x() - {va:.12g})/{vb - va:.12g})*({pamb + rho_water * gravity * port_z:.12g})",
        ),
        (
            "downstreamWetLine",
            f"(pos().x() > {vb:.12g}) && (pos().x() <= {exit_x:.12g}) && "
            f"(pos().y() >= {port_y - width / 2 - 0.02:.12g}) && "
            f"(pos().y() <= {port_y + width / 2 + 0.02:.12g}) && "
            f"(pos().z() >= {port_z - pipe_radius - 0.02:.12g}) && "
            f"(pos().z() <= {port_z + pipe_radius + 0.02:.12g})",
            f"{pamb:.12g} + {rho_water:.12g}*{gravity:.12g}*({port_z:.12g} - pos().z())",
            f"{pamb + rho_water * gravity * port_z:.12g}",
        ),
        (
            "externalAir",
            f"pos().x() > {exit_x:.12g}",
            f"{pamb:.12g} + {rho_ambient:.12g}*{gravity:.12g}*({port_z:.12g} - pos().z())",
            f"{pamb + rho_ambient * gravity * port_z:.12g}",
        ),
    ]
    expressions = []
    for name, mask, pressure, _ in regions:
        expressions.append(
            f"    {name}Pressure\n    {{\n"
            f"        field p;\n"
            f"        dimensions [1 -1 -2 0 0 0 0];\n"
            f"        fieldMask #{{ {mask} #}};\n"
            f"        expression #{{ {pressure} #}};\n"
            f"    }}\n"
        )
    for name, mask, _, p_rgh in regions:
        expressions.append(
            f"    {name}ReducedPressure\n    {{\n"
            f"        field p_rgh;\n"
            f"        dimensions [1 -1 -2 0 0 0 0];\n"
            f"        fieldMask #{{ {mask} #}};\n"
            f"        expression #{{ {p_rgh} #}};\n"
            f"    }}\n"
        )
    return foam_header("setExprFieldsDict", location="system") + (
        "expressions\n(\n" + "".join(expressions) + ");\n"
    )


def field_header(name: str, cls: str, dimensions: str) -> str:
    return foam_header(name, location="0", cls=cls) + f"\ndimensions {dimensions};\n"


def initial_fields(config: dict[str, Any], case: Path) -> None:
    pamb, temp = float(config["gas"]["ambient_pressure_Pa"]), float(config["gas"]["temperature_K"])
    out = {}
    out["p"] = (
        field_header("p", "volScalarField", "[1 -1 -2 0 0 0 0]")
        + f"""internalField uniform {pamb};
boundaryField
{{
    tankWall {{ type calculated; value uniform {pamb}; }}
    pipeWall {{ type calculated; value uniform {pamb}; }}
    transitionWall {{ type calculated; value uniform {pamb}; }}
    ambientAnnulus {{ type calculated; value uniform {pamb}; }}
    externalSides {{ type calculated; value uniform {pamb}; }}
    outlet {{ type calculated; value uniform {pamb}; }}
}}
"""
    )
    out["p_rgh"] = (
        field_header("p_rgh", "volScalarField", "[1 -1 -2 0 0 0 0]")
        + f"""internalField uniform {pamb};
boundaryField
{{
    tankWall {{ type fixedFluxPressure; value uniform {pamb}; }}
    pipeWall {{ type fixedFluxPressure; value uniform {pamb}; }}
    transitionWall {{ type fixedFluxPressure; value uniform {pamb}; }}
    ambientAnnulus {{ type prghPressure; p uniform {pamb}; rho rho; value uniform {pamb}; }}
    externalSides {{ type prghPressure; p uniform {pamb}; rho rho; value uniform {pamb}; }}
    outlet {{ type prghPressure; p uniform {pamb}; rho rho; value uniform {pamb}; }}
}}
"""
    )
    out["alpha.water"] = (
        field_header("alpha.water", "volScalarField", "[0 0 0 0 0 0 0]")
        + """internalField uniform 0;
boundaryField
{
    tankWall { type zeroGradient; }
    pipeWall { type zeroGradient; }
    transitionWall { type zeroGradient; }
    ambientAnnulus { type inletOutlet; inletValue uniform 0; value uniform 0; }
    externalSides { type inletOutlet; inletValue uniform 0; value uniform 0; }
    outlet { type inletOutlet; inletValue uniform 0; value uniform 0; }
}
"""
    )
    out["U"] = (
        field_header("U", "volVectorField", "[0 1 -1 0 0 0 0]")
        + """internalField uniform (0 0 0);
boundaryField
{
    tankWall { type noSlip; }
    pipeWall { type noSlip; }
    transitionWall { type noSlip; }
    ambientAnnulus { type pressureInletOutletVelocity; value uniform (0 0 0); }
    externalSides { type pressureInletOutletVelocity; value uniform (0 0 0); }
    outlet { type pressureInletOutletVelocity; value uniform (0 0 0); }
}
"""
    )
    out["T"] = (
        field_header("T", "volScalarField", "[0 0 0 1 0 0 0]")
        + f"""internalField uniform {temp};
boundaryField
{{
    tankWall {{ type zeroGradient; }}
    pipeWall {{ type zeroGradient; }}
    transitionWall {{ type zeroGradient; }}
    ambientAnnulus {{ type inletOutlet; inletValue uniform {temp}; value uniform {temp}; }}
    externalSides {{ type inletOutlet; inletValue uniform {temp}; value uniform {temp}; }}
    outlet {{ type inletOutlet; inletValue uniform {temp}; value uniform {temp}; }}
}}
"""
    )
    out["k"] = (
        field_header("k", "volScalarField", "[0 2 -2 0 0 0 0]")
        + """internalField uniform 0.02;
boundaryField
{
    tankWall { type kqRWallFunction; value uniform 0.02; }
    pipeWall { type kqRWallFunction; value uniform 0.02; }
    transitionWall { type kqRWallFunction; value uniform 0.02; }
    ambientAnnulus { type inletOutlet; inletValue uniform 0.02; value uniform 0.02; }
    externalSides { type inletOutlet; inletValue uniform 0.02; value uniform 0.02; }
    outlet { type inletOutlet; inletValue uniform 0.02; value uniform 0.02; }
}
"""
    )
    out["omega"] = (
        field_header("omega", "volScalarField", "[0 0 -1 0 0 0 0]")
        + """internalField uniform 10;
boundaryField
{
    tankWall { type omegaWallFunction; value uniform 10; }
    pipeWall { type omegaWallFunction; value uniform 10; }
    transitionWall { type omegaWallFunction; value uniform 10; }
    ambientAnnulus { type inletOutlet; inletValue uniform 10; value uniform 10; }
    externalSides { type inletOutlet; inletValue uniform 10; value uniform 10; }
    outlet { type inletOutlet; inletValue uniform 10; value uniform 10; }
}
"""
    )
    out["nut"] = (
        field_header("nut", "volScalarField", "[0 2 -1 0 0 0 0]")
        + """internalField uniform 0;
boundaryField
{
    tankWall { type nutkWallFunction; value uniform 0; }
    pipeWall { type nutkWallFunction; value uniform 0; }
    transitionWall { type nutkWallFunction; value uniform 0; }
    ambientAnnulus { type calculated; value uniform 0; }
    externalSides { type calculated; value uniform 0; }
    outlet { type calculated; value uniform 0; }
}
"""
    )
    out["alphat"] = (
        field_header("alphat", "volScalarField", "[1 -1 -1 0 0 0 0]")
        + """internalField uniform 0;
boundaryField
{
    tankWall { type compressible::alphatWallFunction; value uniform 0; }
    pipeWall { type compressible::alphatWallFunction; value uniform 0; }
    transitionWall { type compressible::alphatWallFunction; value uniform 0; }
    ambientAnnulus { type calculated; value uniform 0; }
    externalSides { type calculated; value uniform 0; }
    outlet { type calculated; value uniform 0; }
}
"""
    )
    (case / "0").mkdir(parents=True, exist_ok=True)
    for name, text in out.items():
        (case / "0" / name).write_text(text, encoding="utf-8")


def thermo_files(config: dict[str, Any], case: Path) -> None:
    liquid = config["liquid"]
    gravity = gravity_magnitude(config)
    h = foam_header("thermophysicalProperties", location="constant")
    (case / "constant/thermophysicalProperties").write_text(
        h
        + f"phases (water air);\npMin 10000;\nsigma {float(liquid['surface_tension_N_m']):.12g};\n",
        encoding="utf-8",
    )
    (case / "constant/thermophysicalProperties.water").write_text(
        h
        + f"""
thermoType
{{
    type heRhoThermo;
    mixture pureMixture;
    transport const;
    thermo hConst;
    equationOfState rhoConst;
    specie specie;
    energy sensibleInternalEnergy;
}}
mixture
{{
    specie {{ molWeight 18.01528; }}
    equationOfState {{ rho {float(liquid["density_kg_m3"]):.12g}; }}
    thermodynamics {{ Cp 4182; Hf 0; }}
    transport {{ mu {float(liquid["dynamic_viscosity_Pa_s"]):.12g}; Pr 7.0; }}
}}
""",
        encoding="utf-8",
    )
    (case / "constant/thermophysicalProperties.air").write_text(
        h
        + """
thermoType
{
    type heRhoThermo;
    mixture pureMixture;
    transport const;
    thermo hConst;
    equationOfState perfectGas;
    specie specie;
    energy sensibleInternalEnergy;
}
mixture
{
    specie { molWeight 28.96546; }
    thermodynamics { Cp 1005; Hf 0; }
    transport { mu 1.81e-5; Pr 0.71; }
}
""",
        encoding="utf-8",
    )
    (case / "constant/g").write_text(
        foam_header("g", location="constant", cls="uniformDimensionedVectorField")
        + f"dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 {-gravity:.12g});\n",
        encoding="utf-8",
    )
    (case / "constant/turbulenceProperties").write_text(
        foam_header("turbulenceProperties", location="constant")
        + """
simulationType RAS;
RAS
{
    RASModel kOmegaSST;
    turbulence on;
    printCoeffs on;
}
""",
        encoding="utf-8",
    )


def topo_set_dict(config: dict[str, Any], geom: dict[str, Any]) -> str:
    if str(config["tank"].get("axis", "horizontal")).lower() == "vertical":
        return vertical_topo_set_dict(config, geom)
    tank, pipe, nozzle = (config[k] for k in ("tank", "pipe", "nozzle"))
    xt0, xt1, xe = geom["x_tank_start_m"], geom["x_tank_end_m"], geom["x_exit_m"]
    rt, rp = float(tank["diameter_m"]) / 2, float(pipe["diameter_m"]) / 2
    zt, zp = float(tank["center_z_m"]), float(nozzle["center_z_m"])
    xvalve = float(config["valve"]["location_x_m"])
    return (
        foam_header("topoSetDict", location="system")
        + f"""
actions
(
    {{ name tankCells; type cellSet; action new; source boxToCell;
       box ({xt0} {-rt} {zt - rt}) ({xt1} {rt} {zt + rt}); }}
    {{ name tankZone; type cellZoneSet; action new; source setToCellZone; set tankCells; }}
    {{ name lineCells; type cellSet; action new; source boxToCell;
       box ({xt1} {-float(nozzle["width_m"]) / 2 - 0.01} {zp - rp - 0.01})
           ({xe} {float(nozzle["width_m"]) / 2 + 0.01} {zp + rp + 0.01}); }}
    {{ name lineZone; type cellZoneSet; action new; source setToCellZone; set lineCells; }}
    {{ name valveCells; type cellSet; action new; source boxToCell;
       box ({xvalve - 0.05} {-rp} {zp - rp}) ({xvalve + 0.05} {rp} {zp + rp}); }}
    {{ name valveZone; type cellZoneSet; action new; source setToCellZone; set valveCells; }}
);
"""
    )


def vertical_topo_set_dict(config: dict[str, Any], geom: dict[str, Any]) -> str:
    tank, pipe, nozzle = (config[k] for k in ("tank", "pipe", "nozzle"))
    meta = geom["vertical_geometry"]
    center_x, center_y, _ = geom["tank_center_xyz_m"]
    bottom, top = geom["tank_bottom_z_m"], geom["tank_top_z_m"]
    mouth = meta["port"]["centerline_mouth_xyz_m"]
    mouth_x, port_y, port_z = (float(value) for value in mouth)
    stub_x = float(geom["port_stub_min_x_m"])
    radius = float(tank["diameter_m"]) / 2
    pipe_radius = float(pipe["diameter_m"]) / 2
    x_exit = float(geom["x_exit_m"])
    valve_x = float(config["valve"]["location_x_m"])
    width = float(nozzle["width_m"])
    return (
        foam_header("topoSetDict", location="system")
        + f"""
actions
(
    // Native tank inventory is the vertical cylinder.
    {{ name tankCells; type cellSet; action new; source cylinderToCell;
       p1 ({center_x} {center_y} {bottom}); p2 ({center_x} {center_y} {top}); radius {radius}; }}
    {{ name tankZone; type cellZoneSet; action new; source setToCellZone; set tankCells; }}
    // Curved pipe stub starts at the most upstream tank/pipe intersection; the
    // cylinder mask removes tank cells so the two native inventory zones are disjoint.
    {{ name lineCells; type cellSet; action new; source cylinderToCell;
       p1 ({stub_x} {port_y} {port_z}); p2 ({mouth_x} {port_y} {port_z}); radius {pipe_radius}; }}
    {{ name lineCells; type cellSet; action add; source boxToCell;
       box ({mouth_x} {port_y - width / 2 - 0.01} {port_z - pipe_radius - 0.01})
           ({x_exit} {port_y + width / 2 + 0.01} {port_z + pipe_radius + 0.01}); }}
    {{ name lineCells; type cellSet; action subtract; source zoneToCell; zone tankZone; }}
    {{ name lineZone; type cellZoneSet; action new; source setToCellZone; set lineCells; }}
    {{ name valveCells; type cellSet; action new; source boxToCell;
       box ({valve_x - 0.05} {port_y - pipe_radius} {port_z - pipe_radius})
           ({valve_x + 0.05} {port_y + pipe_radius} {port_z + pipe_radius}); }}
    {{ name valveZone; type cellZoneSet; action new; source setToCellZone; set valveCells; }}
);
"""
    )


def fv_options(config: dict[str, Any]) -> str:
    open_time, cd = (float(config["valve"][k]) for k in ("opening_time_s", "Cd"))
    min_open_fraction = minimum_effective_opening(config)
    return (
        foam_header("fvOptions", location="constant")
        + f"""
valveLoss
{{
    type vectorCodedSource;
    active true;
    name i4fTimeVaryingScalarValveLoss;
    vectorCodedSourceCoeffs
    {{
        selectionMode cellZone;
        cellZone valveZone;
        fields (U);
        codeCorrect
        #{{
        #}};
        codeConstrain
        #{{
        #}};
        codeAddSup
        #{{
        #}};
        codeAddSupRho
        #{{
            const scalar time = mesh_.time().value();
            const scalar openingTime = {open_time:.12g};
            const scalar Cd = {cd:.12g};
            const scalar valveLength = 0.10;
            const scalar minOpenFraction = {min_open_fraction:.12g};
            const scalar s = min(max(time/openingTime, scalar(0)), scalar(1));
            const scalar opening = max(sqr(s)*(3.0 - 2.0*s), minOpenFraction);
            const scalar K = 1.0/sqr(Cd*opening);
            const scalar lossPerLength = K/valveLength;
            const scalar uRegularization = 0.10;
            const vectorField& U = mesh_.lookupObject<volVectorField>("U").primitiveField();
            const scalarField& rhoCells = rho.primitiveField();
            const scalarField& V = mesh_.V();
            scalarField& diag = eqn.diag();
            forAll(cells_, i)
            {{
                const label celli = cells_[i];
                const scalar speed = max(mag(U[celli]), uRegularization);
                // fvOptions contributes on the RHS of UEqn; subtract positive drag
                // from that source so the term opposes U, matching DarcyForchheimer.
                // Linearized drop: dp = 0.5*rho*K*U|U| (regularized near zero speed).
                diag[celli] -= 0.5*rhoCells[celli]*lossPerLength*speed*V[celli];
            }}
        #}};
    }}
}}
// At t=0 the configured minimum effective area is a finite bleed, not a sealed valve.
// K matches the reduced model: K=1/(Cd*a)^2. No butterfly disk or wake is resolved.
"""
    )


def observer_plane_coordinates(
    config: dict[str, Any], profile: dict[str, Any]
) -> dict[str, dict[str, float]]:
    tank, pipe, nozzle = (config[name] for name in ("tank", "pipe", "nozzle"))
    observer = profile["observer"]
    if str(tank.get("axis", "horizontal")).lower() == "vertical":
        mouth = config["connection"]["centerline_mouth_xyz_m"]
        mouth_x, mouth_y, mouth_z = (float(value) for value in mouth)
        exit_x = mouth_x + float(pipe["length_m"]) + float(pipe["transition_length_m"])
        y = float(observer.get("center_y_m", mouth_y))
        return {
            "port": {
                "x_m": mouth_x + float(observer["port_offset_from_tank_end_m"]),
                "y_m": y,
                "z_m": mouth_z,
            },
            "nozzle": {
                "x_m": exit_x - float(observer["nozzle_offset_upstream_m"]),
                "y_m": y,
                "z_m": float(nozzle["center_z_m"]),
            },
        }
    tank_end = float(tank["start_x_m"]) + float(tank["length_m"])
    exit_x = tank_end + float(pipe["length_m"]) + float(pipe["transition_length_m"])
    y = float(observer.get("center_y_m", 0.0))
    return {
        "port": {
            "x_m": tank_end + float(observer["port_offset_from_tank_end_m"]),
            "y_m": y,
            "z_m": float(config["connection"]["center_z_m"]),
        },
        "nozzle": {
            "x_m": exit_x - float(observer["nozzle_offset_upstream_m"]),
            "y_m": y,
            "z_m": float(nozzle["center_z_m"]),
        },
    }


def observer_function(
    name: str,
    plane_name: str,
    point: dict[str, float],
    normal: list[float],
    operation: str,
    fields: str,
    write_interval: int,
    weight_field: str | None = None,
) -> str:
    weight_line = f"        weightField     {weight_field};\n" if weight_field else ""
    normal_values = " ".join(f"{value:.9g}" for value in normal)
    return f"""    {name}
    {{
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        regionType      sampledSurface;
        name            {plane_name};
        sampledSurfaceDict
        {{
            type        plane;
            point       ({point["x_m"]:.9g} {point["y_m"]:.9g} {point["z_m"]:.9g});
            normal      ({normal_values});
            triangulate true;
        }}
        writeControl    timeStep;
        writeInterval   {write_interval};
        writeFields     false;
        log             true;
        writeArea       true;
        operation       {operation};
{weight_line}        fields          ({fields});
    }}
"""


def sampled_observer_functions(config: dict[str, Any], profile: dict[str, Any]) -> str:
    coords = observer_plane_coordinates(config, profile)
    observer = profile["observer"]
    normal = [float(value) for value in observer.get("normal_xyz", [1.0, 0.0, 0.0])]
    if len(normal) != 3 or not math.isclose(math.sqrt(sum(x * x for x in normal)), 1.0):
        raise ValueError("observer normal_xyz must be a unit vector with three components")
    interval = int(observer.get("write_interval_steps", 1))
    if interval < 1:
        raise ValueError("observer write_interval_steps must be positive")
    entries = []
    for plane, plane_name in (("nozzle", "nozzlePlane"), ("port", "portPlane")):
        entries.extend(
            [
                observer_function(
                    f"{plane}WaterVectorFlux",
                    plane_name,
                    coords[plane],
                    normal,
                    "weightedAreaIntegrate",
                    "U",
                    interval,
                    weight_field="alpha.water",
                ),
                observer_function(
                    f"{plane}MixtureNormalFlux",
                    plane_name,
                    coords[plane],
                    normal,
                    "areaNormalIntegrate",
                    "U",
                    interval,
                ),
                observer_function(
                    f"{plane}WaterAreaMean",
                    plane_name,
                    coords[plane],
                    normal,
                    "areaAverage",
                    "alpha.water",
                    interval,
                ),
            ]
        )
    return "".join(entries)


def control_dict(config: dict[str, Any], profile: dict[str, Any]) -> str:
    end = float(config.get("exploratory_horizon_s", 1.5))
    solver = profile["solver"]
    observer_blocks = sampled_observer_functions(config, profile)
    if str(config["tank"].get("axis", "horizontal")).lower() == "vertical":
        tank = config["tank"]
        pipe = config["pipe"]
        mouth = config["connection"]["centerline_mouth_xyz_m"]
        cx, cy, _ = (float(value) for value in tank["center_xyz_m"])
        mouth_x, mouth_y, port_z = (float(value) for value in mouth)
        surface_z = (
            float(tank["center_z_m"])
            - float(tank["length_m"]) / 2
            + float(tank["fill_fraction"]) * float(tank["length_m"])
        )
        pipe_end_x = mouth_x + float(pipe["length_m"])
        exit_x = pipe_end_x + float(pipe["transition_length_m"])
        external_x = exit_x + float(config["external"]["length_m"]) / 2
        mid_transition_x = pipe_end_x + float(pipe["transition_length_m"]) / 2
        probe_points = [
            (
                cx,
                cy,
                min(surface_z + 0.2, float(tank["center_z_m"]) + float(tank["length_m"]) / 2 - 0.1),
            ),
            (cx, cy, surface_z - 0.2),
            (mouth_x + 0.1, mouth_y, port_z),
            (float(config["valve"]["location_x_m"]), mouth_y, port_z),
            (pipe_end_x - 0.1, mouth_y, port_z),
            (mid_transition_x, mouth_y, port_z),
            (exit_x - 0.01, mouth_y, port_z),
            (external_x, mouth_y, port_z),
        ]
        probe_locations = "\n".join(
            f"            ({x:.12g} {y:.12g} {z:.12g})" for x, y, z in probe_points
        )
    else:
        probe_locations = """            (1.0 0.0 1.30)
            (1.0 0.0 0.70)
            (2.20 0.0 0.65)
            (2.60 0.0 0.65)
            (2.90 0.0 0.65)
            (3.75 0.0 0.65)
            (4.49 0.0 0.65)
            (5.50 0.0 0.65)"""
    return (
        foam_header("controlDict", location="system")
        + f"""
application compressibleInterFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {end:.8g};
deltaT 1e-5;
writeControl adjustable;
writeInterval 0.05;
purgeWrite 0;
writeFormat binary;
writePrecision 8;
writeCompression off;
fileHandler collated;
timeFormat general;
timePrecision 8;
runTimeModifiable yes;
adjustTimeStep yes;
maxCo {float(solver["max_co"]):.8g};
maxAlphaCo {float(solver["max_alpha_co"]):.8g};
maxDeltaT {float(solver["max_delta_t_s"]):.8g};

functions
{{
    outletWaterPhaseVolumeFlux
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name outlet;
        operation sum;
        fields (alphaPhi0.water);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    ambientAnnulusWaterPhaseVolumeFlux
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name ambientAnnulus;
        operation sum;
        fields (alphaPhi0.water);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    outletMixtureMassFlux
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name outlet;
        operation sum;
        fields (rhoPhi);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    ambientAnnulusMixtureMassFlux
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name ambientAnnulus;
        operation sum;
        fields (rhoPhi);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    externalSidesWaterPhaseVolumeFlux
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name externalSides;
        operation sum;
        fields (alphaPhi0.water);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    externalSidesMixtureMassFlux
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name externalSides;
        operation sum;
        fields (rhoPhi);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
{observer_blocks}
    outletLiquidVolumeFlux
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name outlet;
        operation weightedSum;
        weightField phi;
        fields (alpha.water);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    outletMixtureFlux
    {{
        type surfaceFieldValue;
        libs (fieldFunctionObjects);
        regionType patch;
        name outlet;
        operation sum;
        fields (phi);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    tankWaterVolume
    {{
        type volFieldValue;
        libs (fieldFunctionObjects);
        regionType cellZone;
        name tankZone;
        operation volIntegrate;
        fields (alpha.water);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    tankMixtureMass
    {{
        type volFieldValue;
        libs (fieldFunctionObjects);
        regionType cellZone;
        name tankZone;
        operation volIntegrate;
        fields (rho);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    lineWaterVolume
    {{
        type volFieldValue;
        libs (fieldFunctionObjects);
        regionType cellZone;
        name lineZone;
        operation volIntegrate;
        fields (alpha.water);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    lineMixtureMass
    {{
        type volFieldValue;
        libs (fieldFunctionObjects);
        regionType cellZone;
        name lineZone;
        operation volIntegrate;
        fields (rho);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    totalWaterVolume
    {{
        type volFieldValue;
        libs (fieldFunctionObjects);
        regionType all;
        operation volIntegrate;
        fields (alpha.water);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    totalMixtureMass
    {{
        type volFieldValue;
        libs (fieldFunctionObjects);
        regionType all;
        operation volIntegrate;
        fields (rho);
        writeControl timeStep;
        writeInterval 1;
        writeFields false;
        log true;
    }}
    probes
    {{
        type probes;
        libs (sampling);
        fields (p alpha.water U T);
        probeLocations
        (
{probe_locations}
        );
        writeControl timeStep;
        writeInterval 10;
    }}
}}
"""
    )


def fv_schemes(profile: dict[str, Any]) -> str:
    transonic_schemes = ""
    if profile["solver"].get("transonic", False):
        transonic_schemes = (
            "    div(phid1,p_rgh) Gauss upwind;\n    div(phid2,p_rgh) Gauss upwind;\n"
        )
    template = """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes
{
    div(phi,alpha) Gauss vanLeer;
    div(phirb,alpha) Gauss linear;
    div(rhoPhi,U) Gauss linearUpwind grad(U);
    div(rhoPhi,T) Gauss upwind;
    div(rhoPhi,K) Gauss upwind;
    div(phi,p) Gauss upwind;
    div(rhoPhi,k) Gauss upwind;
    div(rhoPhi,omega) Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
__TRANSONIC_SCHEMES__
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
"""
    return foam_header("fvSchemes", location="system") + template.replace(
        "__TRANSONIC_SCHEMES__", transonic_schemes.rstrip()
    )


def fv_solution(profile: dict[str, Any]) -> str:
    solver = profile["solver"]
    transonic_entry = "    transonic yes;\n" if solver.get("transonic", False) else ""
    template = """
solvers
{
    "alpha.water.*"
    {
        nAlphaCorr 1;
        nAlphaSubCycles __N_ALPHA_SUBCYCLES__;
        cAlpha 1;
        MULESCorr yes;
        nLimiterIter 3;
        solver smoothSolver;
        smoother symGaussSeidel;
        tolerance 1e-8;
        relTol 0;
    }
    ".*(rho|rhoFinal)"
    {
        solver diagonal;
    }
    p_rgh
    {
        solver __PRESSURE_SOLVER__;
        tolerance __PRESSURE_TOLERANCE__;
        relTol __PRESSURE_RELATIVE_TOLERANCE__;
        smoother __PRESSURE_SMOOTHER__;
    }
    p_rghFinal
    {
        $p_rgh;
        relTol 0;
    }
    U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-7; relTol 0; maxIter 200; }
    T { solver PBiCGStab; preconditioner DILU; tolerance 1e-8; relTol 0.01; maxIter 200; }
    k { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.01; maxIter 200; }
    omega { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.01; maxIter 200; }
    UFinal { $U; relTol 0; }
    TFinal { $T; relTol 0.01; }
    kFinal { $k; relTol 0; }
    omegaFinal { $omega; relTol 0; }
}
PIMPLE
{
    momentumPredictor yes;
__TRANSONIC_ENTRY__
    nOuterCorrectors __N_OUTER_CORRECTORS__;
    nCorrectors __N_CORRECTORS__;
    nNonOrthogonalCorrectors 0;
}
"""
    replacements = {
        "__N_ALPHA_SUBCYCLES__": str(int(solver["n_alpha_sub_cycles"])),
        "__PRESSURE_SOLVER__": str(solver["pressure_solver"]),
        "__PRESSURE_TOLERANCE__": f"{float(solver['pressure_tolerance']):.8g}",
        "__PRESSURE_RELATIVE_TOLERANCE__": f"{float(solver['pressure_relative_tolerance']):.8g}",
        "__PRESSURE_SMOOTHER__": str(solver["pressure_smoother"]),
        "__TRANSONIC_ENTRY__": transonic_entry.rstrip("\n"),
        "__N_OUTER_CORRECTORS__": str(int(solver["n_outer_correctors"])),
        "__N_CORRECTORS__": str(int(solver["n_correctors"])),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return foam_header("fvSolution", location="system") + template


def prepare(
    config_path: Path,
    output: Path,
    config: dict[str, Any],
    ranks: int,
    profile: dict[str, Any],
    profile_path: Path,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    validate_supported_lamellae(config)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {output}")
    case = output / "case"
    tri_dir, system = case / "constant/triSurface", case / "system"
    tri_dir.mkdir(parents=True)
    system.mkdir(parents=True)
    geom = build_geometry(config, tri_dir)
    (system / "blockMeshDict").write_text(block_mesh_dict(geom), encoding="utf-8")
    (system / "surfaceFeatureExtractDict").write_text(
        surface_feature_extract_dict(), encoding="utf-8"
    )
    (system / "snappyHexMeshDict").write_text(snappy_dict(config, geom), encoding="utf-8")
    (system / "setFieldsDict").write_text(set_fields_dict(config, geom), encoding="utf-8")
    (system / "setExprFieldsDict").write_text(set_expr_fields_dict(config, geom), encoding="utf-8")
    (system / "topoSetDict").write_text(topo_set_dict(config, geom), encoding="utf-8")
    (system / "controlDict").write_text(control_dict(config, profile), encoding="utf-8")
    (system / "fvSchemes").write_text(fv_schemes(profile), encoding="utf-8")
    (system / "fvSolution").write_text(fv_solution(profile), encoding="utf-8")
    (system / "decomposeParDict").write_text(
        foam_header("decomposeParDict", location="system")
        + f"numberOfSubdomains {ranks};\nmethod scotch;\ndistributed no;\nroots ();\n",
        encoding="utf-8",
    )
    initial_fields(config, case)
    thermo_files(config, case)
    (case / "constant/fvOptions").write_text(fv_options(config), encoding="utf-8")
    (case / "i4f.foam").touch()
    output.mkdir(parents=True, exist_ok=True)
    initial_volume = (
        math.pi
        * (float(config["tank"]["diameter_m"]) / 2) ** 2
        * float(config["tank"]["length_m"])
        * float(config["tank"]["fill_fraction"])
    )
    downstream_prefill_volume = float(geom.get("line_zone_prefill_volume_m3", 0.19840292))
    axis_vector = [float(value) for value in config["tank"]["axis_vector"]]
    nozzle_direction = [float(value) for value in config["nozzle"]["direction"]]
    vertical_orientation = str(config["tank"].get("axis", "horizontal")).lower() == "vertical"
    orientation_support = (
        "vertical +z tank with +x side port and +x downstream passage; arbitrary rotations unsupported"
        if vertical_orientation
        else "fixed tank axis +x, nozzle direction +x, vertical +z; arbitrary rotations are unsupported"
    )
    transition_area_rule = (
        "linear from measured pipe polygon area to rectangular endpoint; vertical supplier angle sampling retained"
        if vertical_orientation
        else "linear from analytic circular pipe area to exact rectangular area; pipe STL radius corrected by sub-0.01% to preserve exact circular polygon area; horizontal y scaling only"
    )
    pressure_initialization = (
        "setExprFields initializes the vertical tank by its cylindrical radial mask and z fill plane, applies hydrostatic pressure through the curved side-port stub and upstream line, and initializes the downstream wet line/external air"
        if vertical_orientation
        else "setExprFields initializes tank gas/water and both wet line segments with piecewise hydrostatic p and matching p_rgh; linear interpolation across valve zone"
    )
    result = {
        "experiment": config["experiment"],
        "status": "exploratory CPU case prepared; not yet executed",
        "coordinate_frame": "stationary apparatus; x along discharge, y horizontal cross-stream, z upward",
        "gravity": {
            "magnitude_m_s2": gravity_magnitude(config),
            "vector_xyz_m_s2": [0.0, 0.0, -gravity_magnitude(config)],
        },
        "solver": "OpenCFD compressibleInterFoam v2512",
        "solver_image": "opencfd/openfoam-default:2512",
        "solver_image_id": "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b",
        "mesh": {
            "method": "blockMesh plus surfaceFeatureExtract and feature-snapped snappyHexMesh of the closed STL fluid volume",
            "background_pitch_m": BACKGROUND_PITCH_M,
            "background_bounds_m": geom["background_bounds_m"],
            "target_cells": "100k-500k exploratory; actual checkMesh count to be recorded",
            "wall_layers": "none",
            "feature_mesh_settings": {
                "surface_features": ["pipeWall", "transitionWall", "tankWall"],
                "feature_snap": "explicitFeatureSnap and multiRegionFeatureSnap enabled; 20 iterations",
                "local_level_3_regions": ["portFine", "lipFine"],
            },
            "output_format": "collated OpenFOAM file handler for parallel fields; dictionaries set fileHandler collated",
            "checkpoint_interval_s": 0.05,
            "compact_flux_and_inventory_sample": "every solver timestep, time-stamped",
        },
        "horizon_s": float(config.get("exploratory_horizon_s", 1.5)),
        "solver_profile": {
            "name": profile.get("name", "unnamed"),
            "source_file": str(profile_path),
            "source_sha256": sha256(profile_path),
            "settings": profile,
        },
        "runtime_overrides": overrides,
        "mpi_ranks": ranks,
        "turbulence": "RAS kOmegaSST, wall functions; first closure and y+ unverified",
        "vof_numerics": {
            "nAlphaSubCycles": 1,
            "maxAlphaCo": float(profile["solver"]["max_alpha_co"]),
            "maxCo": float(profile["solver"]["max_co"]),
            "maxDeltaT_s": float(profile["solver"]["max_delta_t_s"]),
            "native_water_flux_field": "alphaPhi0.water; with one alpha subcycle this is the full-step MULES water volume flux",
            "flux_integration": "right-endpoint Euler sum over solver timesteps",
        },
        "event_rule": {
            "horizon_s": float(config.get("exploratory_horizon_s", 1.5)),
            "label": profile["event"].get(
                "marker_label",
                "NET SAMPLED OPERATIONAL MARKER; not a universal physical break threshold",
            ),
            "observer_planes": observer_plane_coordinates(config, profile),
            "observer_normal_xyz": profile["observer"].get("normal_xyz", [1.0, 0.0, 0.0]),
            "observer_sampling_stride_steps": int(profile["observer"]["write_interval_steps"]),
            "observer_quantities": {
                "water_vector_flux": "x component of weightedAreaIntegrate(U, weight=alpha.water); sampled/interpolated plane estimate",
                "mixture_normal_flux": "areaNormalIntegrate(U); sampled/interpolated plane estimate",
                "water_area_mean": "areaAverage(alpha.water); sampled/interpolated plane estimate",
                "gas_net_flux_estimate": "Qmixture - Qwater_x",
                "net_gas_flux_fraction": "(Qmixture - Qwater_x)/Qmixture, evaluated only when Qmixture > 0",
            },
            "port_arming": (
                "require the configured number of consecutive port rows with positive mixture flux "
                "and net sampled gas flux fraction >= threshold; this gates out startup ambient-air discharge"
            ),
            "nozzle_liquid_requalification": (
                "after port arming, require the configured number of consecutive nozzle rows with "
                "positive mixture flux and net gas fraction < threshold"
            ),
            "nozzle_marker": (
                "after liquid requalification, require the configured number of consecutive nozzle "
                "rows with positive mixture flux and net gas fraction >= threshold"
            ),
            "threshold_net_gas_fraction": float(profile["event"]["threshold_net_gas_fraction"]),
            "port_arming_consecutive_samples": int(
                profile["event"]["port_arming_consecutive_samples"]
            ),
            "nozzle_liquid_confirmation_consecutive_samples": int(
                profile["event"]["nozzle_liquid_confirmation_consecutive_samples"]
            ),
            "nozzle_event_consecutive_samples": int(
                profile["event"]["nozzle_event_consecutive_samples"]
            ),
            "stop_after_persistence_confirmation": f"write controlDict stopAt {profile['event']['stop_at']} and preserve that written checkpoint",
            "execution": "an external watcher must evaluate these logged rows and request the stop; the OpenFOAM case itself is bounded by endTime",
            "qualification": "sampled/interpolated plane metrics; not a conservative face flux or a universal physical breakthrough time",
        },
        "thermophysics": {
            "air": "ideal gas, non-isothermal; sealed headspace",
            "water": "rhoConst; pressure-compressibility omitted",
            "walls": "adiabatic; conjugate heat transfer omitted",
        },
        "external_air": {
            "wind_velocity_m_s": [
                float(component) for component in config["external"]["wind_velocity_m_s"]
            ],
            "wind_support": "still air only; nonzero wind is rejected",
        },
        "valve": {
            "law": str(config["valve"]["opening_law"]),
            "minimum_effective_opening_fraction": minimum_effective_opening(config),
            "loss": "K(t)=1/[Cd*a(t)]^2, pipe reference area; 0.10 m implicit Darcy-Forchheimer zone",
            "fvOptions_implementation": "OpenCFD v2512 vectorCodedSource with codeAddSupRho, selected on valveZone",
            "source_sign": "negative implicit diagonal on the fvOptions right-hand-side source; drag opposes velocity",
            "location_x_m": float(config["valve"]["location_x_m"]),
            "disk_or_wake_resolved": False,
            "initial_minimum_effective_area_fraction": minimum_effective_opening(config),
            "initial_leakage": "finite bleed approximation at t=0; not a sealed closed valve; magnitude to be measured in pilot",
            "reduced_model_match": "same K(t)=1/[Cd*a(t)]^2 law; no subtract-one offset",
        },
        "initial_state": {
            "tank_pressure_absolute_Pa": float(config["gas"]["initial_absolute_pressure_Pa"]),
            "ambient_pressure_absolute_Pa": float(config["gas"]["ambient_pressure_Pa"]),
            "gas": "sealed ideal air at 293.15 K",
            "downstream_line": "water-filled wet start at ambient pressure",
            "pressure_initialization": pressure_initialization,
            "downstream_line_hydrostatic_equilibrium": "water-filled downstream line is initialized hydrostatically at ambient reference pressure; the upstream/downstream apparatus is not in equilibrium across the finite valve restriction",
            "tank_water_volume_expected_m3": initial_volume,
            "downstream_prefill_volume_expected_m3": downstream_prefill_volume,
            "preopening_exit_flux_separate": True,
        },
        "lamellae": {
            "included_in_reference": False,
            "geometry_emitted": False,
            "reported_count": config.get("lamellae", {}).get("reported_count"),
            "reported_start_transition_fraction": config.get("lamellae", {}).get(
                "reported_start_transition_fraction"
            ),
            "orientation": config.get("lamellae", {}).get("orientation", "unspecified"),
            "reach_exit": config.get("lamellae", {}).get("reach_exit", "unspecified"),
            "thickness_m": config.get("lamellae", {}).get("thickness_m"),
            "qualification": "reported hardware description only; no internal nozzle plates are generated or simulated",
        },
        "geometry": {
            "orientation_support": orientation_support,
            "tank_axis_vector_xyz": axis_vector,
            "nozzle_direction_xyz": nozzle_direction,
            "closed_surface_edge_audit": geom["closure"],
            "triangle_counts": geom["triangle_counts"],
            "flow_angle_count": len(geom["angles"]),
            "pipe_polygon_area_m2": geom["pipe_area_m2"],
            "pipe_analytic_area_m2": math.pi * (float(config["pipe"]["diameter_m"]) / 2) ** 2,
            "pipe_radius_polygon_correction_fraction": geom[
                "pipe_radius_polygon_correction_fraction"
            ],
            "nozzle_polygon_area_m2": geom["nozzle_area_m2"],
            "nominal_nozzle_area_m2": float(config["nozzle"]["width_m"])
            * float(config["nozzle"]["height_m"]),
            "transition_area_rule": transition_area_rule,
            "transition_cross_section_shape": "convex superellipse, n=2/(1-s), circular inlet to rectangular endpoint; vertical half-height contracts linearly and horizontal half-width is solved to maintain the linear area law",
            "transition_section_audit": geom["area_audit"],
            "x_tank_start_m": geom["x_tank_start_m"],
            "x_tank_end_m": geom["x_tank_end_m"],
            "x_pipe_end_m": geom["x_pipe_end_m"],
            "x_nozzle_exit_m": geom["x_exit_m"],
            "x_external_end_m": geom["x_external_end_m"],
            "external_length_m": float(config["external"]["length_m"]),
            **(
                {
                    "tank_axis": "vertical",
                    "tank_center_xyz_m": geom["tank_center_xyz_m"],
                    "tank_bbox_xyz_m": geom["tank_bounds_xyz_m"],
                    "tank_bottom_z_m": geom["tank_bottom_z_m"],
                    "tank_top_z_m": geom["tank_top_z_m"],
                    "port_centerline_mouth_xyz_m": geom["port_centerline_mouth_xyz_m"],
                    "port_stub_min_x_m": geom["port_stub_min_x_m"],
                    "port_stub_volume_m3": geom["port_stub_volume_m3"],
                    "pipe_area_relative_to_analytic": geom["pipe_area_m2"]
                    / (math.pi * (float(config["pipe"]["diameter_m"]) / 2) ** 2)
                    - 1.0,
                    "vertical_supplier_metadata": geom["vertical_geometry"],
                }
                if vertical_orientation
                else {}
            ),
        },
        "provenance": {
            "created_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "repository_revision": git_revision(),
            "working_tree_dirty": git_dirty(),
            "baseline_config": str(config_path),
            "baseline_config_sha256": sha256(config_path),
            "generator_sha256": sha256(Path(__file__)),
        },
        "input_qualification": config["provenance"],
        "limitations": [
            "tank-axis configurations are limited to +x horizontal or +z vertical with a +x discharge; arbitrary tilt and other azimuths are rejected",
            "air baseline does not represent already gas-dispersed liquid or confirmed CO2 charging",
            "CO2 dissolution, bubble transport and foam rheology are omitted",
            "no cavitation model or real-gas equation of state",
            "scalar valve loss cannot predict butterfly wake/asymmetry",
            "five reported internal nozzle lamellae are omitted from this no-vane hydraulic reference; their orientation and thickness are unresolved",
            "external air is initialized at rest; nonzero wind inputs are rejected",
            "wet-start downstream inventory contributes to early outlet flux",
            "no mesh/time-step sensitivity evidence yet",
        ],
    }
    (output / "case-inputs.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output / "case-profile.json").write_text(
        json.dumps(profile, indent=2) + "\n", encoding="utf-8"
    )
    (output / "geometry-section-audit.csv").write_text(
        "x_m,s_m,superellipse_n,area_mesh_m2,area_linear_target_m2,width_m,height_m,convex_contour\n"
        + "".join(
            f"{r['x_m']:.9g},{r['s_m']:.9g},{'' if r['superellipse_n'] is None else format(r['superellipse_n'], '.9g')},"
            f"{r['area_mesh_m2']:.12g},{r['area_linear_target_m2']:.12g},"
            f"{r['width_m']:.12g},{r['height_m']:.12g},{str(r['convex_contour']).lower()}\n"
            for r in geom["area_audit"]
        ),
        encoding="utf-8",
    )
    if vertical_orientation:
        orientation_readme = (
            "This provisional arrangement has a +z vertical tank, a curved side-wall junction, "
            "and a +x pipe, transition, nozzle and external region. Arbitrary tank rotations are rejected. "
        )
    else:
        orientation_readme = (
            "The current mesh generator supports only a tank axis and nozzle direction along +x, with +z upward; "
            "it rejects other configured orientations. "
        )
    (case / "README.md").write_text(
        "# I4F exploratory case\n\n"
        "Generated by scripts/prepare_i4f_case.py. Run blockMesh, surfaceFeatureExtract, "
        "snappyHexMesh -overwrite, "
        "checkMesh -allTopology -allGeometry, topoSet, setFields, then setExprFields in order. "
        "The sibling case-inputs.json, case-profile.json and geometry-section-audit.csv record the assumptions. "
        + orientation_readme
        + "Gravity magnitude is taken from gravity_m_s2. "
        "The current thermophysics accepts air only, the valve source accepts the smoothstep law only, "
        "and the external region accepts still air only. The valve area floor is a finite configured fraction. "
        "The sampled observer is interpolated and supports the origin-gated operational marker; "
        "it is not a conservative phase-flux measurement.\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            f"{__doc__}\nDefault profile: {DEFAULT_PROFILE.relative_to(ROOT)}. "
            "The prior non-transonic profile is preserved at "
            f"{LEGACY_PROFILE.relative_to(ROOT)}. Generated cases are exploratory and are not validated predictions."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ranks", type=int, default=8)
    parser.add_argument(
        "--profile",
        type=Path,
        help=(
            "OpenFOAM profile JSON (solver controls and observer/event contract); "
            f"default: {DEFAULT_PROFILE.relative_to(ROOT)}. Profiles are exploratory, not validated."
        ),
    )
    parser.add_argument(
        "--external-length-m",
        type=float,
        help="override only the downstream external-air region length in metres",
    )
    args = parser.parse_args()
    if args.ranks < 1:
        parser.error("--ranks must be positive")
    config_path = args.config.resolve(strict=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile_path = (args.profile or DEFAULT_PROFILE).resolve(strict=True)
    profile = load_profile(profile_path)
    overrides: dict[str, Any] = {}
    if args.external_length_m is not None:
        if not math.isfinite(args.external_length_m) or args.external_length_m <= 0:
            parser.error("--external-length-m must be positive and finite")
        config["external"]["length_m"] = float(args.external_length_m)
        overrides["external.length_m"] = float(args.external_length_m)
    if config.get("gas", {}).get("mode") != "sealed":
        raise ValueError("the first case supports the declared sealed blowdown")
    validate_supported_orientation(config)
    validate_supported_lamellae(config)
    validate_supported_physics_inputs(config)
    gravity_magnitude(config)
    if float(config["nozzle"]["width_m"]) != 1.0 or float(config["nozzle"]["height_m"]) != 0.15:
        raise ValueError("baseline nozzle must remain 1.0 m x 0.15 m")
    run_id = dt.datetime.now(dt.UTC).strftime("i4f-apparatus-%Y%m%dT%H%M%SZ")
    output = (args.output or (RUNS / run_id)).resolve()
    output.relative_to(RUNS)
    meta = prepare(
        config_path,
        output,
        config,
        args.ranks,
        profile,
        profile_path,
        overrides,
    )
    print(
        json.dumps(
            {
                "run_dir": str(output),
                "solver": meta["solver"],
                "surface_closure": meta["geometry"]["closed_surface_edge_audit"],
                "pipe_area_m2": meta["geometry"]["pipe_polygon_area_m2"],
                "nozzle_area_m2": meta["geometry"]["nozzle_polygon_area_m2"],
                "transition_end_area_m2": meta["geometry"]["transition_section_audit"][-1][
                    "area_mesh_m2"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
