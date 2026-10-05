#!/usr/bin/env python3
"""Prepare a source-limited exploratory CL-415 belly-release OpenFOAM case.

The generator records its provisional geometry and properties in
``case-inputs.json``. It does not infer a payload from aircraft capacity and it
does not turn the digitized Fig. 4 scalar curves into measured port profiles.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "opencfd/openfoam-default:2512"
PRIMARY_HISTORY_CSV = ROOT / "data/derived/calbrix_cl415_fig4_velocities.csv"
INDEPENDENT_HISTORY_CSV = ROOT / "data/derived/calbrix_cl415_fig4_velocities_independent.csv"
SOURCE_RECORD = ROOT / "experiments/E3_CALBRIX_CL415_SOURCE.md"

PILOT_DOMAIN = {"x": (-2.0, 6.0), "y": (-3.0, 3.0), "z": (-4.0, 0.0)}
FULL_DOMAIN = {"x": (-2.0, 20.0), "y": (-7.0, 7.0), "z": (-21.0, 0.0)}
REFINEMENT_REGION = {"x": (-1.0, 2.0), "y": (-1.5, 1.5), "z": (-2.0, 0.0)}
WATER_RHO_KG_M3 = 1000.0
WATER_MU_PA_S = 1.0e-3
AIR_RHO_KG_M3 = 1.2
AIR_MU_PA_S = 1.8e-5
SURFACE_TENSION_N_M = 0.0
GRAVITY_M_S2 = (0.0, 0.0, -9.81)
AIR_SPEED_M_S = 50.0
TURBULENCE_INTENSITY = 0.05
AIR_LENGTH_SCALE_M = 0.05
WATER_LENGTH_SCALE_M = 0.05
MAX_CO = 0.30
MAX_ALPHA_CO = 0.15
MAX_DELTA_T_S = 5.0e-4
SNAPSHOT_INTERVAL_S = 0.05
VALID_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(number: float) -> str:
    if number == 0.0:
        return "0"
    return f"{number:.10g}"


def foam_header(
    object_name: str, field_class: str = "dictionary", location: str | None = None
) -> str:
    location_line = f'    location    "{location}";\n' if location else ""
    return (
        "FoamFile\n{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {field_class};\n"
        f"{location_line}"
        f"    object      {object_name};\n"
        "}\n\n"
    )


def _default_geometry() -> dict[str, Any]:
    """Return a deliberately assumed, cell-aligned four-door geometry."""
    sources: list[dict[str, Any]] = []
    for index, (x, history) in enumerate(
        ((-0.4, "top"), (-0.4, "top"), (0.4, "bottom"), (0.4, "bottom")), 1
    ):
        y = -0.55 if index % 2 else 0.55
        sources.append(
            {
                "name": f"source_{index:02d}",
                "center_x_m": x,
                "center_y_m": y,
                "length_x_m": 0.80,
                "width_y_m": 0.30,
                "discharge_direction_unit": [0.0, 0.0, -1.0],
                "history": history,
            }
        )
    return {
        "schema_version": 1,
        "source_origin_m": [0.0, 0.0, 0.0],
        "source_plane_z_m": 0.0,
        "geometry_evidence": "assumed; Fig. 3 reports four exits but not their polygons, centers, or normals",
        "sources": sources,
    }


def _validate_geometry(value: Any, domain: dict[str, tuple[float, float]]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("source geometry JSON must be an object with schema_version 1")
    origin = value.get("source_origin_m", [0.0, 0.0, 0.0])
    if (
        not isinstance(origin, list)
        or len(origin) != 3
        or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in origin)
    ):
        raise ValueError("source_origin_m must contain three finite numbers")
    plane_z = value.get("source_plane_z_m", 0.0)
    if not isinstance(plane_z, (int, float)) or not math.isfinite(plane_z):
        raise ValueError("source_plane_z_m must be finite")
    if not math.isclose(float(plane_z), domain["z"][1], abs_tol=1e-10):
        raise ValueError("the four assumed outlets must lie on the domain top plane")
    raw_sources = value.get("sources")
    if not isinstance(raw_sources, list) or len(raw_sources) != 4:
        raise ValueError("exactly four disjoint outlet rectangles are required")

    sources: list[dict[str, Any]] = []
    names: set[str] = set()
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise ValueError("each source must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not VALID_NAME.fullmatch(name) or name in names:
            raise ValueError("source names must be unique OpenFOAM identifiers")
        names.add(name)
        numbers: dict[str, float] = {}
        for key in ("center_x_m", "center_y_m", "length_x_m", "width_y_m"):
            number = raw.get(key)
            if not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ValueError(f"{name}.{key} must be finite")
            numbers[key] = float(number)
        if numbers["length_x_m"] <= 0 or numbers["width_y_m"] <= 0:
            raise ValueError(f"{name} rectangle dimensions must be positive")
        direction = raw.get("discharge_direction_unit", [0.0, 0.0, -1.0])
        if (
            not isinstance(direction, list)
            or len(direction) != 3
            or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in direction)
        ):
            raise ValueError(f"{name}.discharge_direction_unit must have three finite numbers")
        magnitude = math.sqrt(sum(float(v) ** 2 for v in direction))
        if not math.isclose(magnitude, 1.0, rel_tol=0.0, abs_tol=1e-8):
            raise ValueError(f"{name}.discharge_direction_unit must be a unit vector")
        if float(direction[2]) >= 0.0:
            raise ValueError(f"{name} must have a downward discharge direction into the domain")
        history = raw.get("history")
        if history not in {"top", "bottom"}:
            raise ValueError(f"{name}.history must be 'top' or 'bottom' per the Fig. 4 legend")

        source = {
            "name": name,
            **numbers,
            "area_m2": numbers["length_x_m"] * numbers["width_y_m"],
            "direction_unit": [float(v) for v in direction],
            "history": history,
            "plane_z_m": float(plane_z),
        }
        xmin = numbers["center_x_m"] - numbers["length_x_m"] / 2
        xmax = numbers["center_x_m"] + numbers["length_x_m"] / 2
        ymin = numbers["center_y_m"] - numbers["width_y_m"] / 2
        ymax = numbers["center_y_m"] + numbers["width_y_m"] / 2
        if xmin < domain["x"][0] or xmax > domain["x"][1]:
            raise ValueError(f"{name} lies outside the x domain")
        if ymin < domain["y"][0] or ymax > domain["y"][1]:
            raise ValueError(f"{name} lies outside the y domain")
        source["bounds_m"] = {"x": [xmin, xmax], "y": [ymin, ymax]}
        sources.append(source)

    if sum(source["history"] == "top" for source in sources) != 2:
        raise ValueError("exactly two exits must use the top/red Fig. 4 trace")
    if sum(source["history"] == "bottom" for source in sources) != 2:
        raise ValueError("exactly two exits must use the bottom/green Fig. 4 trace")
    for index, first in enumerate(sources):
        ax0, ax1 = first["bounds_m"]["x"]
        ay0, ay1 = first["bounds_m"]["y"]
        for second in sources[index + 1 :]:
            bx0, bx1 = second["bounds_m"]["x"]
            by0, by1 = second["bounds_m"]["y"]
            overlap_x = min(ax1, bx1) - max(ax0, bx0)
            overlap_y = min(ay1, by1) - max(ay0, by0)
            if overlap_x > 1e-12 and overlap_y > 1e-12:
                raise ValueError(f"source rectangles {first['name']} and {second['name']} overlap")
    return {
        "schema_version": 1,
        "source_origin_m": [float(v) for v in origin],
        "source_plane_z_m": float(plane_z),
        "geometry_evidence": str(value.get("geometry_evidence", "user-supplied geometry")),
        "sources": sources,
    }


def _read_histories() -> dict[str, list[tuple[float, float]]]:
    series = {"cl415_top_exit_red": "top", "cl415_bottom_exit_green": "bottom"}
    output: dict[str, list[tuple[float, float]]] = {"top": [], "bottom": []}
    with PRIMARY_HISTORY_CSV.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            label = series.get(row["series"])
            if label is None:
                continue
            time_s = float(row["time_s"])
            speed_m_s = float(row["max_exit_velocity_digitized_m_s"])
            if (
                not math.isfinite(time_s)
                or not math.isfinite(speed_m_s)
                or time_s <= 0
                or speed_m_s < 0
            ):
                raise ValueError(
                    "Fig. 4 CSV contains a non-finite, non-positive time, or negative speed"
                )
            output[label].append((time_s, speed_m_s))
    for label, samples in output.items():
        if not samples or any(a[0] >= b[0] for a, b in zip(samples, samples[1:])):
            raise ValueError(f"Fig. 4 source series {label!r} is empty or not strictly increasing")
        samples.insert(0, (0.0, 0.0))
    return output


def _interpolate(samples: list[tuple[float, float]], time_s: float) -> float:
    if time_s <= samples[0][0]:
        return samples[0][1]
    for (t0, v0), (t1, v1) in zip(samples, samples[1:]):
        if time_s <= t1:
            return v0 + (v1 - v0) * ((time_s - t0) / (t1 - t0))
    if math.isclose(time_s, samples[-1][0], abs_tol=1e-12):
        return samples[-1][1]
    raise ValueError(f"time {time_s:g} s exceeds digitized source support")


def history_to_horizon(
    samples: list[tuple[float, float]], horizon_s: float
) -> list[tuple[float, float]]:
    if not math.isfinite(horizon_s) or horizon_s <= 0:
        raise ValueError("horizon_s must be finite and positive")
    if horizon_s > samples[-1][0] + 1e-12:
        raise ValueError(
            f"horizon {horizon_s:g} s exceeds digitized support ending at {samples[-1][0]:g} s"
        )
    selected = [(t, v) for t, v in samples if 0.0 < t < horizon_s]
    selected.append((horizon_s, _interpolate(samples, horizon_s)))
    return [(0.0, 0.0), *selected]


def integrate_history(samples: list[tuple[float, float]], horizon_s: float) -> float:
    bounded = history_to_horizon(samples, horizon_s)
    return sum((t1 - t0) * (v0 + v1) / 2 for (t0, v0), (t1, v1) in zip(bounded, bounded[1:]))


def _axis_breaks(
    axis: str,
    bounds: tuple[float, float],
    sources: list[dict[str, Any]],
    refinement_bounds: tuple[float, float],
    local_spacing_m: float,
    coarse_spacing_m: float,
    inner_refinement_bounds: tuple[float, float] | None = None,
    inner_spacing_m: float | None = None,
) -> tuple[list[float], list[int], list[float]]:
    lower, upper = bounds
    points = {lower, upper}
    for source in sources:
        if axis in source["bounds_m"]:
            points.update(source["bounds_m"][axis])
    region_lo, region_hi = refinement_bounds
    if lower < region_lo < upper:
        points.add(region_lo)
    if lower < region_hi < upper:
        points.add(region_hi)
    if inner_refinement_bounds is not None:
        inner_lo, inner_hi = inner_refinement_bounds
        if lower < inner_lo < upper:
            points.add(inner_lo)
        if lower < inner_hi < upper:
            points.add(inner_hi)
    ordered = sorted(points)
    counts: list[int] = []
    widths: list[float] = []
    for start, end in zip(ordered, ordered[1:]):
        middle = (start + end) / 2
        in_refinement = region_lo - 1e-10 <= middle <= region_hi + 1e-10
        in_inner_refinement = (
            inner_refinement_bounds is not None
            and inner_refinement_bounds[0] - 1e-10 <= middle <= inner_refinement_bounds[1] + 1e-10
        )
        if in_inner_refinement:
            assert inner_spacing_m is not None
            target_width = inner_spacing_m
        else:
            target_width = local_spacing_m if in_refinement else coarse_spacing_m
        count = max(1, math.ceil((end - start) / target_width - 1e-12))
        actual_width = (end - start) / count
        counts.append(count)
        widths.append(actual_width)
    return ordered, counts, widths


def _validate_refinement_region(
    refinement_region: dict[str, tuple[float, float]] | None,
    domain: dict[str, tuple[float, float]],
    sources: list[dict[str, Any]],
) -> dict[str, tuple[float, float]]:
    value = REFINEMENT_REGION if refinement_region is None else refinement_region
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        raise ValueError("refinement region must provide exactly x, y, and z bounds")
    normalized: dict[str, tuple[float, float]] = {}
    for axis in ("x", "y", "z"):
        bounds = value[axis]
        if (
            not isinstance(bounds, (tuple, list))
            or len(bounds) != 2
            or any(
                not isinstance(number, (int, float)) or not math.isfinite(number)
                for number in bounds
            )
        ):
            raise ValueError(f"refinement region {axis} bounds must be two finite numbers")
        lower, upper = float(bounds[0]), float(bounds[1])
        if lower >= upper:
            raise ValueError(f"refinement region {axis} lower bound must be less than upper bound")
        if lower < domain[axis][0] - 1e-12 or upper > domain[axis][1] + 1e-12:
            raise ValueError(f"refinement region {axis} bounds must lie inside the selected domain")
        normalized[axis] = (lower, upper)

    for source in sources:
        for axis in ("x", "y"):
            source_lower, source_upper = source["bounds_m"][axis]
            region_lower, region_upper = normalized[axis]
            if source_lower < region_lower - 1e-12 or source_upper > region_upper + 1e-12:
                raise ValueError(
                    f"refinement region must cover outlet {source['name']} in {axis}; "
                    "moving refinement away from a source requires an explicit model change"
                )
        if not normalized["z"][0] <= source["plane_z_m"] <= normalized["z"][1]:
            raise ValueError(
                f"refinement region must include outlet {source['name']} source plane in z"
            )
    return normalized


def _validate_inner_refinement(
    *,
    inner_refinement_region: dict[str, tuple[float, float]] | None,
    inner_spacing_m: float | None,
    domain: dict[str, tuple[float, float]],
    sources: list[dict[str, Any]],
    refinement: dict[str, tuple[float, float]],
    spacing_m: float,
) -> tuple[dict[str, tuple[float, float]] | None, float | None]:
    if (inner_refinement_region is None) != (inner_spacing_m is None):
        raise ValueError("inner_refinement_region and inner_spacing_m must be provided together")
    if inner_refinement_region is None:
        return None, None

    if not isinstance(inner_refinement_region, dict) or set(inner_refinement_region) != {
        "x",
        "y",
        "z",
    }:
        raise ValueError("refinement region must provide exactly x, y, and z bounds")
    for axis in ("x", "y", "z"):
        axis_bounds = inner_refinement_region[axis]
        if not isinstance(axis_bounds, (tuple, list)) or len(axis_bounds) != 2:
            raise ValueError(f"refinement region {axis} bounds must be two finite numbers")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in axis_bounds
        ):
            raise ValueError(f"refinement region {axis} bounds must be two finite numbers")

    if (
        isinstance(spacing_m, bool)
        or not isinstance(spacing_m, (int, float))
        or not math.isfinite(spacing_m)
        or spacing_m <= 0.0
    ):
        raise ValueError("spacing_m must be finite and positive when inner refinement is enabled")
    if (
        isinstance(inner_spacing_m, bool)
        or not isinstance(inner_spacing_m, (int, float))
        or not math.isfinite(inner_spacing_m)
        or inner_spacing_m <= 0.0
    ):
        raise ValueError("inner_spacing_m must be finite and positive")
    inner_spacing = float(inner_spacing_m)
    if inner_spacing > spacing_m:
        raise ValueError("inner_spacing_m must be no larger than spacing_m")

    inner = _validate_refinement_region(inner_refinement_region, domain, sources)
    for axis in ("x", "y", "z"):
        if (
            inner[axis][0] < refinement[axis][0] - 1e-12
            or inner[axis][1] > refinement[axis][1] + 1e-12
        ):
            raise ValueError(
                f"inner refinement region {axis} bounds must lie inside the base refinement region"
            )
    return inner, inner_spacing


def _face(vertices: tuple[int, int, int, int]) -> str:
    return "(" + " ".join(str(vertex) for vertex in vertices) + ")"


def _mesh_index(ix: int, iy: int, iz: int, nx: int, ny: int) -> int:
    return iz * (nx + 1) * (ny + 1) + iy * (nx + 1) + ix


def block_mesh_dict(
    *,
    domain: dict[str, tuple[float, float]],
    sources: list[dict[str, Any]],
    spacing_m: float,
    coarse_spacing_m: float,
    refinement_region: dict[str, tuple[float, float]] | None = None,
    inner_refinement_region: dict[str, tuple[float, float]] | None = None,
    inner_spacing_m: float | None = None,
) -> tuple[str, dict[str, Any]]:
    refinement = _validate_refinement_region(refinement_region, domain, sources)
    inner_refinement, inner_spacing = _validate_inner_refinement(
        inner_refinement_region=inner_refinement_region,
        inner_spacing_m=inner_spacing_m,
        domain=domain,
        sources=sources,
        refinement=refinement,
        spacing_m=spacing_m,
    )
    axes = {
        axis: _axis_breaks(
            axis,
            domain[axis],
            sources,
            refinement[axis],
            spacing_m,
            coarse_spacing_m,
            inner_refinement[axis] if inner_refinement is not None else None,
            inner_spacing,
        )
        for axis in ("x", "y", "z")
    }
    breaks = {axis: axes[axis][0] for axis in axes}
    counts = {axis: axes[axis][1] for axis in axes}
    widths = {axis: axes[axis][2] for axis in axes}
    nx_breaks, ny_breaks, nz_breaks = (breaks[a] for a in ("x", "y", "z"))
    nxi, nyi, nzi = (len(nx_breaks) - 1, len(ny_breaks) - 1, len(nz_breaks) - 1)

    vertices = [
        f"    ({canonical(x)} {canonical(y)} {canonical(z)})"
        for z in nz_breaks
        for y in ny_breaks
        for x in nx_breaks
    ]
    source_faces: dict[str, list[str]] = {source["name"]: [] for source in sources}
    source_face_areas: dict[str, float] = {source["name"]: 0.0 for source in sources}
    boundary_faces: dict[str, list[str]] = {
        "plate": [],
        "airInlet": [],
        "xOutlet": [],
        "yMin": [],
        "yMax": [],
        "zMin": [],
    }
    blocks: list[str] = []

    def source_for_block(ix: int, iy: int) -> str | None:
        x0, x1 = nx_breaks[ix : ix + 2]
        y0, y1 = ny_breaks[iy : iy + 2]
        for source in sources:
            sx0, sx1 = source["bounds_m"]["x"]
            sy0, sy1 = source["bounds_m"]["y"]
            if x0 >= sx0 - 1e-10 and x1 <= sx1 + 1e-10 and y0 >= sy0 - 1e-10 and y1 <= sy1 + 1e-10:
                return source["name"]
        return None

    for ix in range(nxi):
        for iy in range(nyi):
            for iz in range(nzi):
                p000 = _mesh_index(ix, iy, iz, nxi, nyi)
                p100 = _mesh_index(ix + 1, iy, iz, nxi, nyi)
                p110 = _mesh_index(ix + 1, iy + 1, iz, nxi, nyi)
                p010 = _mesh_index(ix, iy + 1, iz, nxi, nyi)
                p001 = _mesh_index(ix, iy, iz + 1, nxi, nyi)
                p101 = _mesh_index(ix + 1, iy, iz + 1, nxi, nyi)
                p111 = _mesh_index(ix + 1, iy + 1, iz + 1, nxi, nyi)
                p011 = _mesh_index(ix, iy + 1, iz + 1, nxi, nyi)
                blocks.append(
                    f"    hex ({p000} {p100} {p110} {p010} {p001} {p101} {p111} {p011}) "
                    f"({counts['x'][ix]} {counts['y'][iy]} {counts['z'][iz]}) simpleGrading (1 1 1)"
                )
                if iz == nzi - 1:
                    source_name = source_for_block(ix, iy)
                    face = _face((p001, p101, p111, p011))
                    if source_name:
                        source_faces[source_name].append(face)
                        source_face_areas[source_name] += (nx_breaks[ix + 1] - nx_breaks[ix]) * (
                            ny_breaks[iy + 1] - ny_breaks[iy]
                        )
                    else:
                        boundary_faces["plate"].append(face)
                if ix == 0:
                    boundary_faces["airInlet"].append(_face((p000, p001, p011, p010)))
                if ix == nxi - 1:
                    boundary_faces["xOutlet"].append(_face((p100, p110, p111, p101)))
                if iy == 0:
                    boundary_faces["yMin"].append(_face((p000, p100, p101, p001)))
                if iy == nyi - 1:
                    boundary_faces["yMax"].append(_face((p010, p011, p111, p110)))
                if iz == 0:
                    boundary_faces["zMin"].append(_face((p000, p010, p110, p100)))

    patch_text: list[str] = []
    for source in sources:
        faces = source_faces[source["name"]]
        if not faces:
            raise ValueError(f"no blockMesh faces were assigned to outlet {source['name']}")
        patch_text.append(_patch(source["name"], "patch", faces))
    for name, patch_type in (
        ("plate", "wall"),
        ("airInlet", "patch"),
        ("xOutlet", "patch"),
        ("yMin", "patch"),
        ("yMax", "patch"),
        ("zMin", "patch"),
    ):
        patch_text.append(_patch(name, patch_type, boundary_faces[name]))

    mesh = (
        foam_header("blockMeshDict")
        + "scale 1;\n\nvertices\n(\n"
        + "\n".join(vertices)
        + "\n);\n\nblocks\n(\n"
        + "\n".join(blocks)
        + "\n);\n\nedges ();\n\nboundary\n(\n"
        + "\n".join(patch_text)
        + ");\n\nmergePatchPairs ();\n"
    )
    cell_shape = {axis: sum(counts[axis]) for axis in counts}
    details = {
        "mesh_breaks_m": breaks,
        "mesh_cells_per_segment": counts,
        "mesh_widths_by_segment_m": widths,
        "mesh_shape": cell_shape,
        "mesh_cells_expected": math.prod(cell_shape.values()),
        "refinement_region_m": {axis: list(refinement[axis]) for axis in refinement},
        "refinement_covers_all_source_faces": True,
        "source_patch_macro_face_counts": {
            name: len(faces) for name, faces in source_faces.items()
        },
        "source_patch_face_counts": {
            source["name"]: math.prod(
                sum(
                    count
                    for start, end, count in zip(
                        breaks[axis][:-1], breaks[axis][1:], counts[axis], strict=True
                    )
                    if start >= source["bounds_m"][axis][0] - 1e-10
                    and end <= source["bounds_m"][axis][1] + 1e-10
                )
                for axis in ("x", "y")
            )
            for source in sources
        },
        "source_patch_areas_m2": source_face_areas,
    }
    if inner_refinement is not None:
        details.update(
            {
                "inner_refinement_region_m": {
                    axis: list(inner_refinement[axis]) for axis in inner_refinement
                },
                "inner_spacing_m": inner_spacing,
                "mesh_refinement_interpretation": (
                    "conforming Cartesian tensor-product axis bands extending across the box; "
                    "not true local three-dimensional AMR"
                ),
            }
        )
    return mesh, details


def _patch(name: str, patch_type: str, faces: list[str]) -> str:
    return (
        f"    {name}\n    {{\n        type {patch_type};\n        faces\n        (\n"
        + "\n".join(f"            {face}" for face in faces)
        + "\n        );\n    }\n"
    )


def _field(
    name: str,
    field_class: str,
    dimensions: str,
    internal_value: str,
    patch_values: dict[str, str],
) -> str:
    boundaries = "\n".join(
        f"    {patch}\n    {{\n{value}\n    }}" for patch, value in patch_values.items()
    )
    return (
        foam_header(name, field_class)
        + f"dimensions {dimensions};\n\ninternalField uniform {internal_value};\n\nboundaryField\n{{\n"
        + boundaries
        + "\n}\n"
    )


def _turbulence_values(
    speed_m_s: float,
    length_scale_m: float,
    turbulence_intensity: float = TURBULENCE_INTENSITY,
) -> tuple[float, float]:
    k = 1.5 * (turbulence_intensity * speed_m_s) ** 2
    epsilon = 0.09**0.75 * k**1.5 / length_scale_m
    return k, epsilon


def _source_turbulence_history(
    samples: list[tuple[float, float]],
    length_scale_m: float,
    turbulence_intensity: float = TURBULENCE_INTENSITY,
) -> list[tuple[float, float, float]]:
    values = []
    for time_s, speed_m_s in samples:
        k_value, epsilon_value = _turbulence_values(speed_m_s, length_scale_m, turbulence_intensity)
        values.append((time_s, max(k_value, 1.0e-12), max(epsilon_value, 1.0e-12)))
    return values


def _history_boundary(source: dict[str, Any], values: list[tuple[float, float]]) -> str:
    vector = source["direction_unit"]
    table = "\n".join(
        f"            ({canonical(time_s)} ({canonical(speed * vector[0])} "
        f"{canonical(speed * vector[1])} {canonical(speed * vector[2])}))"
        for time_s, speed in values
    )
    first = values[0][1]
    initial_vector = tuple(first * component for component in vector)
    return (
        "        type uniformFixedValue;\n        uniformValue table\n        (\n"
        + table
        + "\n        );\n        value uniform ("
        + " ".join(canonical(number) for number in initial_vector)
        + ");"
    )


def _scalar_table_boundary(samples: list[tuple[float, float]]) -> str:
    table = "\n".join(
        f"            ({canonical(time_s)} {canonical(value)})" for time_s, value in samples
    )
    return (
        "        type uniformFixedValue;\n        uniformValue table\n        (\n"
        + table
        + f"\n        );\n        value uniform {canonical(samples[0][1])};"
    )


def _write_fields(
    case_dir: Path,
    sources: list[dict[str, Any]],
    histories: dict[str, list[tuple[float, float]]],
    *,
    air_turbulence_intensity: float = TURBULENCE_INTENSITY,
    water_turbulence_intensity: float = TURBULENCE_INTENSITY,
    air_length_scale_m: float = AIR_LENGTH_SCALE_M,
    water_length_scale_m: float = WATER_LENGTH_SCALE_M,
) -> dict[str, Any]:
    source_names = [source["name"] for source in sources]
    roof = ["plate"]
    open_patches = ["xOutlet", "yMin", "yMax", "zMin"]
    velocity: dict[str, str] = {
        source["name"]: _history_boundary(source, histories[source["history"]])
        for source in sources
    }
    velocity.update(
        {
            "plate": "        type slip;",
            "airInlet": f"        type fixedValue;\n        value uniform ({AIR_SPEED_M_S:g} 0 0);",
            **{
                name: "        type pressureInletOutletVelocity;\n        value uniform (0 0 0);"
                for name in open_patches
            },
        }
    )
    alpha: dict[str, str] = {
        source["name"]: "        type fixedValue;\n        value uniform 1;" for source in sources
    }
    alpha.update(
        {
            "plate": "        type zeroGradient;",
            "airInlet": "        type fixedValue;\n        value uniform 0;",
            **{
                name: "        type inletOutlet;\n        inletValue uniform 0;\n        value uniform 0;"
                for name in open_patches
            },
        }
    )
    pressure: dict[str, str] = {
        name: "        type fixedFluxPressure;\n        value uniform 0;"
        for name in [*source_names, *roof, "airInlet"]
    }
    pressure.update(
        {name: "        type fixedValue;\n        value uniform 0;" for name in open_patches}
    )

    order = [*source_names, "plate", "airInlet", *open_patches]
    (case_dir / "0" / "U").write_text(
        _field(
            "U", "volVectorField", "[0 1 -1 0 0 0 0]", "(50 0 0)", {k: velocity[k] for k in order}
        ),
        encoding="utf-8",
    )
    (case_dir / "0" / "alpha.water").write_text(
        _field(
            "alpha.water", "volScalarField", "[0 0 0 0 0 0 0]", "0", {k: alpha[k] for k in order}
        ),
        encoding="utf-8",
    )
    (case_dir / "0" / "p_rgh").write_text(
        _field(
            "p_rgh", "volScalarField", "[1 -1 -2 0 0 0 0]", "0", {k: pressure[k] for k in order}
        ),
        encoding="utf-8",
    )

    air_k, air_epsilon = _turbulence_values(
        AIR_SPEED_M_S, air_length_scale_m, air_turbulence_intensity
    )
    source_k, source_epsilon = _turbulence_values(
        6.0, water_length_scale_m, water_turbulence_intensity
    )
    k_bc = {
        source["name"]: _scalar_table_boundary(
            [
                (t, k)
                for t, k, _ in _source_turbulence_history(
                    histories[source["history"]],
                    water_length_scale_m,
                    water_turbulence_intensity,
                )
            ]
        )
        for source in sources
    }
    epsilon_bc = {
        source["name"]: _scalar_table_boundary(
            [
                (t, epsilon)
                for t, _, epsilon in _source_turbulence_history(
                    histories[source["history"]],
                    water_length_scale_m,
                    water_turbulence_intensity,
                )
            ]
        )
        for source in sources
    }
    k_bc.update(
        {
            "plate": "        type zeroGradient;",
            "airInlet": f"        type fixedValue;\n        value uniform {canonical(air_k)};",
            **{
                name: f"        type inletOutlet;\n        inletValue uniform {canonical(air_k)};\n        value uniform {canonical(air_k)};"
                for name in open_patches
            },
        }
    )
    epsilon_bc.update(
        {
            "plate": "        type zeroGradient;",
            "airInlet": f"        type fixedValue;\n        value uniform {canonical(air_epsilon)};",
            **{
                name: f"        type inletOutlet;\n        inletValue uniform {canonical(air_epsilon)};\n        value uniform {canonical(air_epsilon)};"
                for name in open_patches
            },
        }
    )
    nut_bc = {
        name: "        type calculated;\n        value uniform 0;"
        for name in [*source_names, "airInlet", *open_patches]
    }
    nut_bc["plate"] = "        type calculated;\n        value uniform 0;"
    field_order = [*source_names, "plate", "airInlet", *open_patches]
    (case_dir / "0" / "k").write_text(
        _field(
            "k",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            canonical(air_k),
            {k: k_bc[k] for k in field_order},
        ),
        encoding="utf-8",
    )
    (case_dir / "0" / "epsilon").write_text(
        _field(
            "epsilon",
            "volScalarField",
            "[0 2 -3 0 0 0 0]",
            canonical(air_epsilon),
            {k: epsilon_bc[k] for k in field_order},
        ),
        encoding="utf-8",
    )
    (case_dir / "0" / "nut").write_text(
        _field(
            "nut", "volScalarField", "[0 2 -1 0 0 0 0]", "0", {k: nut_bc[k] for k in field_order}
        ),
        encoding="utf-8",
    )
    return {
        "air_turbulence_k_m2_s2": air_k,
        "air_turbulence_epsilon_m2_s3": air_epsilon,
        "source_turbulence_k_m2_s2": source_k,
        "source_turbulence_epsilon_m2_s3": source_epsilon,
    }


def _functions_dict(patches: list[str]) -> str:
    flux_objects = "".join(
        f"    {name}Flux\n    {{\n        type surfaceFieldValue;\n"
        "        libs (fieldFunctionObjects);\n        regionType patch;\n"
        f"        name {name};\n        operation sum;\n        fields (phi alphaPhi_);\n"
        "        writeFields false;\n        executeControl timeStep;\n        executeInterval 1;\n"
        "        writeControl timeStep;\n        writeInterval 1;\n    }\n"
        for name in patches
    )
    return (
        "functions\n{\n"
        "    waterVolume\n    {\n        type volFieldValue;\n        libs (fieldFunctionObjects);\n"
        "        executeControl timeStep;\n        executeInterval 1;\n"
        "        writeControl timeStep;\n        writeInterval 1;\n        operation volIntegrate;\n"
        "        writeFields false;\n        fields (alpha.water);\n    }\n" + flux_objects + "}\n"
    )


def _write_dictionaries(
    case_dir: Path,
    *,
    horizon_s: float,
    mesh_details: dict[str, Any],
    ranks: int,
    patches: list[str],
    snapshot_interval_s: float = SNAPSHOT_INTERVAL_S,
) -> float:
    if not math.isfinite(snapshot_interval_s) or snapshot_interval_s <= 0:
        raise ValueError("snapshot_interval_s must be finite and positive")
    (case_dir / "constant" / "g").write_text(
        foam_header("g", "uniformDimensionedVectorField", "constant")
        + "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 -9.81);\n",
        encoding="utf-8",
    )
    (case_dir / "constant" / "transportProperties").write_text(
        foam_header("transportProperties", location="constant")
        + "phases (water air);\n\n"
        + "water { transportModel Newtonian; nu 1e-6; rho 1000; }\n"
        + "air { transportModel Newtonian; nu 1.5e-5; rho 1.2; }\n\n"
        + "sigma 0;\n",
        encoding="utf-8",
    )
    (case_dir / "constant" / "turbulenceProperties").write_text(
        foam_header("turbulenceProperties", location="constant")
        + "density variable;\nsimulationType RAS;\n\nRAS\n{\n"
        "    RASModel kEpsilon;\n    turbulence on;\n    printCoeffs on;\n}\n",
        encoding="utf-8",
    )
    min_width = min(
        width
        for axis in ("x", "y", "z")
        for width in mesh_details["mesh_widths_by_segment_m"][axis]
    )
    delta_t_s = min(1.0e-4, 0.25 * min_width / AIR_SPEED_M_S)
    maximum_delta_t_s = min(MAX_DELTA_T_S, 0.25 * min_width / AIR_SPEED_M_S)
    write_interval = min(snapshot_interval_s, horizon_s)
    (case_dir / "system" / "controlDict").write_text(
        foam_header("controlDict", location="system")
        + "application interIsoFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\n"
        + f"endTime {canonical(horizon_s)};\ndeltaT {canonical(delta_t_s)};\n"
        + "writeControl adjustableRunTime;\n"
        + f"writeInterval {canonical(write_interval)};\npurgeWrite 0;\n"
        + "writeFormat binary;\nwritePrecision 8;\nwriteCompression off;\n"
        "timeFormat fixed;\ntimePrecision 6;\nrunTimeModifiable no;\n"
        + f"adjustTimeStep yes;\nmaxCo {MAX_CO:g};\nmaxAlphaCo {MAX_ALPHA_CO:g};\n"
        + f"maxDeltaT {canonical(maximum_delta_t_s)};\n\n"
        + _functions_dict(patches),
        encoding="utf-8",
    )
    (case_dir / "system" / "fvSchemes").write_text(
        foam_header("fvSchemes", location="system") + "ddtSchemes { default Euler; }\n"
        "gradSchemes { default Gauss linear; grad(k) Gauss linear; grad(epsilon) Gauss linear; }\n"
        "divSchemes\n{\n    div(rhoPhi,U) Gauss limitedLinearV 1;\n"
        "    div(rhoPhi,k) Gauss limitedLinear 1;\n"
        "    div(rhoPhi,epsilon) Gauss limitedLinear 1;\n"
        "    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;\n}\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes { default corrected; }\n"
        "fluxRequired { default no; p_rgh; pcorr; alpha.water; }\n",
        encoding="utf-8",
    )
    (case_dir / "system" / "fvSolution").write_text(
        foam_header("fvSolution", location="system") + "solvers\n{\n"
        '    "alpha.water.*"\n    {\n        isoFaceTol 1e-6;\n        surfCellTol 1e-6;\n'
        "        nAlphaBounds 3;\n        snapTol 1e-12;\n        clip true;\n"
        "        reconstructionScheme isoAlpha;\n        writeFields true;\n"
        "        nAlphaSubCycles 1;\n        cAlpha 1;\n    }\n"
        '    "pcorr.*" { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0; }\n'
        "    p_rgh { solver GAMG; smoother DICGaussSeidel; tolerance 1e-9; relTol 0.05; }\n"
        "    p_rghFinal { $p_rgh; tolerance 1e-9; relTol 0; }\n"
        "    U { solver PBiCGStab; preconditioner DILU; tolerance 1e-6; relTol 0; }\n"
        '    "(k|epsilon)" { solver smoothSolver; smoother GaussSeidel; tolerance 1e-8; relTol 0.1; }\n'
        '    "(k|epsilon)Final" { solver smoothSolver; smoother GaussSeidel; tolerance 1e-8; relTol 0; }\n'
        "}\nPIMPLE\n{\n    momentumPredictor no;\n    nCorrectors 3;\n"
        "    nOuterCorrectors 1;\n    nNonOrthogonalCorrectors 0;\n"
        "    pRefCell 0;\n    pRefValue 0;\n}\n",
        encoding="utf-8",
    )
    n_x_cells = int(mesh_details["mesh_shape"]["x"])
    if ranks > n_x_cells:
        raise ValueError(f"ranks ({ranks}) must not exceed x-direction cell count ({n_x_cells})")
    (case_dir / "system" / "decomposeParDict").write_text(
        foam_header("decomposeParDict", location="system")
        + f"numberOfSubdomains {ranks};\nmethod simple;\ncoeffs {{ n ({ranks} 1 1); }}\n",
        encoding="utf-8",
    )
    return delta_t_s


def _git_provenance() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}
    return {"revision": revision, "dirty": bool(status)}


def prepare_case(
    output: Path,
    horizon_s: float = 0.1,
    spacing_m: float = 0.1,
    ranks: int = 20,
    *,
    full_domain: bool = False,
    source_geometry: Path | None = None,
    coarse_spacing_m: float | None = None,
    refinement_region: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Create a new case directory and return the exact input manifest."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"output directory already exists; preserving it: {output}")
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("spacing_m must be finite and positive")
    if coarse_spacing_m is None:
        coarse_spacing_m = spacing_m
    if not math.isfinite(coarse_spacing_m) or coarse_spacing_m < spacing_m:
        raise ValueError("coarse_spacing_m must be finite and no smaller than spacing_m")
    if isinstance(ranks, bool) or not isinstance(ranks, int) or ranks < 1:
        raise ValueError("ranks must be a positive integer")
    if not math.isfinite(horizon_s) or horizon_s <= 0:
        raise ValueError("horizon_s must be finite and positive")
    domain = FULL_DOMAIN if full_domain else PILOT_DOMAIN

    if source_geometry is None:
        geometry_raw = _default_geometry()
        geometry_source_text = json.dumps(geometry_raw, indent=2, sort_keys=True) + "\n"
        geometry_evidence = "default assumed geometry generated by prepare_case.py"
    else:
        geometry_raw = json.loads(Path(source_geometry).read_text(encoding="utf-8"))
        geometry_source_text = Path(source_geometry).read_text(encoding="utf-8")
        geometry_evidence = "user-supplied geometry; still provisional unless externally sourced"
    geometry = _validate_geometry(geometry_raw, domain)
    geometry["geometry_evidence"] = geometry_evidence
    refinement = _validate_refinement_region(refinement_region, domain, geometry["sources"])
    histories = _read_histories()
    upper_source_time = min(samples[-1][0] for samples in histories.values())
    if horizon_s > upper_source_time + 1e-12:
        raise ValueError(
            f"horizon_s ({horizon_s:g}) exceeds the shorter digitized history support ({upper_source_time:g} s); "
            "do not extrapolate a tail or invent a shutoff"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    for directory in ("0", "constant", "system"):
        (output / directory).mkdir()
    domain_details = {axis: [float(v) for v in domain[axis]] for axis in domain}
    mesh_text, mesh_details = block_mesh_dict(
        domain=domain,
        sources=geometry["sources"],
        spacing_m=spacing_m,
        coarse_spacing_m=coarse_spacing_m,
        refinement_region=refinement,
    )
    (output / "system" / "blockMeshDict").write_text(mesh_text, encoding="utf-8")

    bounded_histories = {
        name: history_to_horizon(samples, horizon_s) for name, samples in histories.items()
    }
    turbulence_values = _write_fields(output, geometry["sources"], bounded_histories)
    patch_names = [source["name"] for source in geometry["sources"]] + [
        "airInlet",
        "xOutlet",
        "yMin",
        "yMax",
        "zMin",
    ]
    delta_t_s = _write_dictionaries(
        output,
        horizon_s=horizon_s,
        mesh_details=mesh_details,
        ranks=ranks,
        patches=patch_names,
    )

    geometry_path = output / "source_geometry.json"
    if source_geometry is None:
        geometry_path.write_text(geometry_source_text, encoding="utf-8")
    else:
        geometry_path.write_text(geometry_source_text, encoding="utf-8")

    source_artifacts_dir = output / "source"
    source_artifacts_dir.mkdir()
    source_artifacts = {
        "fig4_primary_csv": PRIMARY_HISTORY_CSV,
        "fig4_independent_csv": INDEPENDENT_HISTORY_CSV,
        "e3_source_record": SOURCE_RECORD,
    }
    for source_path in source_artifacts.values():
        (source_artifacts_dir / source_path.name).write_bytes(source_path.read_bytes())

    per_source: dict[str, dict[str, float]] = {}
    for source in geometry["sources"]:
        volume_m3 = source["area_m2"] * integrate_history(histories[source["history"]], horizon_s)
        per_source[source["name"]] = {
            "analytic_volume_m3": volume_m3,
            "analytic_mass_kg": WATER_RHO_KG_M3 * volume_m3,
        }
    total_volume_m3 = sum(entry["analytic_volume_m3"] for entry in per_source.values())
    total_mass_kg = WATER_RHO_KG_M3 * total_volume_m3
    source_csvs = {
        "fig4_primary_csv_sha256": sha256(PRIMARY_HISTORY_CSV),
        "fig4_independent_csv_sha256": sha256(INDEPENDENT_HISTORY_CSV),
        "e3_source_record_sha256": sha256(SOURCE_RECORD),
        "source_geometry_sha256": sha256(geometry_path),
        "prepare_case_sha256": sha256(Path(__file__)),
    }
    mesh_details.update(
        {
            "domain_bounds_m": domain_details,
            "coarse_spacing_m": coarse_spacing_m,
            "local_spacing_m": spacing_m,
            "refinement_region_m": mesh_details["refinement_region_m"],
            "mesh_widths_by_segment_m": mesh_details["mesh_widths_by_segment_m"],
        }
    )
    metadata: dict[str, Any] = {
        "case_id": "E3_CALBRIX_CL415_EXPLORATORY_NEARFIELD",
        "evidence_label": "exploratory source-limited approximation; not E3 validation",
        "solver": "interIsoFoam",
        "openfoam_image": IMAGE,
        "horizon_s": horizon_s,
        "ranks": ranks,
        "source_origin_m": geometry["source_origin_m"],
        "source_patches": [source["name"] for source in geometry["sources"]],
        "open_patches": ["airInlet", "xOutlet", "yMin", "yMax", "zMin"],
        "coordinate_frame": {
            "mesh": {
                "x": "aircraft-frame streamwise axis; relative air flows in +x",
                "y": "cross-track horizontal axis",
                "z": "vertical upward; outlet flow and gravity act in -z",
            },
            "source_origin_m": geometry["source_origin_m"],
            "source_plane_z_m": geometry["source_plane_z_m"],
            "paper_plot_transform": {
                "paper_streamwise_y_m": "mesh_x_m - source_origin_m[0]",
                "paper_cross_track_x_m": "mesh_y_m - source_origin_m[1]",
                "paper_downward_z_m": "source_plane_z_m - mesh_z_m",
            },
        },
        **mesh_details,
        "full_domain_requested": full_domain,
        "domain_placement_assumption": (
            "The 22 x 14 x 21 m reported domain is placed at x[-2,20], y[-7,7], z[-21,0] with the outlet plane at z=0; "
            "the 2 m upstream x offset and all outlet-to-boundary distances are assumed."
            if full_domain
            else "The short pilot subset x[-2,6], y[-3,3], z[-4,0] is a provisional outlet-centered crop."
        ),
        "source_geometry": geometry,
        "default_port_area_assumption": (
            "0.8 m x 0.3 m per outlet, loosely guided by separate Fig. 1 tank-sketch labels 0.83 m and 0.3 m; "
            "the paper does not map those labels to outlet polygons or establish an open area"
            if source_geometry is None
            else "custom supplied rectangle areas; they remain provisional unless independently sourced"
        ),
        "source_histories": {
            "top": {
                "series_id": "cl415_top_exit_red",
                "figure_legend": "top exit, red trace",
                "curve_quantity": "digitized scalar U_L(t); paper does not reconcile mean U_L=Q_L/S with figure's maximum-velocity label",
                "mapping": "uniform scalar speed on two assumed outlet patches",
                "samples_used_m_s": [[t, v] for t, v in bounded_histories["top"]],
                "zero_at_t0": "inferred linear ramp from zero because first digitized sample is at 0.05 s",
                "integration_method": "exact trapezoidal integral of the piecewise-linear digitized samples",
            },
            "bottom": {
                "series_id": "cl415_bottom_exit_green",
                "figure_legend": "bottom exit, green trace",
                "curve_quantity": "digitized scalar U_L(t); paper does not reconcile mean U_L=Q_L/S with figure's maximum-velocity label",
                "mapping": "uniform scalar speed on two assumed outlet patches",
                "samples_used_m_s": [[t, v] for t, v in bounded_histories["bottom"]],
                "zero_at_t0": "inferred linear ramp from zero because first digitized sample is at 0.05 s",
                "integration_method": "exact trapezoidal integral of the piecewise-linear digitized samples",
            },
            "figure_color_note": "Fig. 4 legend maps red=top and green=bottom; adjacent prose conflicts and is not used to remap the curves.",
            "tail_policy": "horizon must not exceed the shortest primary digitized series; no extrapolated tail or shutoff is added",
            "horizon_s": horizon_s,
            "analytic_expected_by_source": per_source,
            "analytic_expected_volume_m3": total_volume_m3,
            "analytic_expected_mass_kg": total_mass_kg,
            "not_a_payload": "integrated provisional source mass for this area/history approximation; not inferred from 6000 L aircraft capacity",
            "source_patch_areas_m2": mesh_details["source_patch_areas_m2"],
            "initial_water_volume_anchor_m3": 0.0,
            "figure_read_allowances": {
                "velocity_m_s": 0.05,
                "time_s": 0.01,
                "status": "heuristic raster read allowances from the E3 source record; not paper uncertainty and correlated near steep curve regions",
            },
            "source_artifacts_relative_paths": {
                key: f"source/{path.name}" for key, path in source_artifacts.items()
            },
        },
        "fluid_properties": {
            "water": {
                "rho_kg_m3": WATER_RHO_KG_M3,
                "mu_Pa_s": WATER_MU_PA_S,
                "evidence": "reported, E3 source record PDF p. 4 / journal p. 1518",
            },
            "air": {
                "rho_kg_m3": AIR_RHO_KG_M3,
                "mu_Pa_s": AIR_MU_PA_S,
                "evidence": "assumed; numeric CL-415 air properties absent from the source record",
            },
            "surface_tension_N_m": SURFACE_TENSION_N_M,
            "surface_tension_evidence": "zero to match paper's omitted momentum term; paper rationale is not independently established on this mesh",
        },
        "gravity_m_s2": list(GRAVITY_M_S2),
        "boundary_conditions": {
            "airInlet": "x-min plane; fixed 50 m/s +x relative air flow",
            "open_boundaries": ["xOutlet", "yMin", "yMax", "zMin"],
            "top_belly": "free-slip wall patch without aircraft geometry; k and epsilon use zeroGradient, and nut is calculated at zero",
            "source_flow_sign": "patch outward normal is +z; prescribed velocity has negative z component and enters the domain",
        },
        "turbulence_model": "standard k-epsilon RANS",
        "turbulence_assumptions": {
            "intensity": TURBULENCE_INTENSITY,
            "air_length_scale_m": AIR_LENGTH_SCALE_M,
            "water_length_scale_m": WATER_LENGTH_SCALE_M,
            **turbulence_values,
            "source_boundary_scaling": "source k and epsilon follow each digitized U_L(t) table using the stated intensity and water length scale, with positive 1e-12 floors at t=0",
            "status": "assumed; exact inlet turbulence values are absent from the paper",
        },
        "time_controls": {
            "end_s": horizon_s,
            "initial_delta_t_s": delta_t_s,
            "max_delta_t_s": min(
                MAX_DELTA_T_S,
                0.25
                * min(min(v) for v in mesh_details["mesh_widths_by_segment_m"].values())
                / AIR_SPEED_M_S,
            ),
            "adaptive": True,
            "max_Co": MAX_CO,
            "max_alpha_Co": MAX_ALPHA_CO,
            "snapshot_interval_s": min(SNAPSHOT_INTERVAL_S, horizon_s),
        },
        "resources": {"mpi_ranks": ranks, "starting_allocation_only": True},
        "intended_diagnostic": "nearfield VOF smoke/profiling and alpha>=0.001 / alpha>=0.9 cloud snapshots; no ground deposition",
        "scope_limitations": [
            "no aircraft or tank mesh; belly is a slip wall",
            "four top-plane rectangle positions, dimensions, and mapping of red/green histories to two outlets each are assumed",
            "Fig. 4 provides two scalar traces, not pointwise or independently measured four-port velocity profiles; U_L mean/maximum meaning is unresolved",
            "default 0.8 m by 0.3 m ports and their positions are assumed; the tank-sketch labels are not exact outlet geometry, and source area controls the integrated provisional mass",
            "no exact payload, 6000 L capacity is not used as a source mass",
            "no measured source cutoff, no extrapolated history beyond the chosen horizon, and no fitted tail",
            "no rotor/wake, foam, parcels, evaporation, ground impact, fire, or deposition",
            "air properties, gravity, turbulence boundary values, open boundaries, and local-resolution policy are provisional where not reported",
            "the case cannot establish E3 validation, field performance, suppression, or design gain",
        ],
        "provenance": {**_git_provenance(), **source_csvs},
    }
    manifest_path = output / "case-inputs.json"
    manifest_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="new, non-existing case directory"
    )
    parser.add_argument("--horizon-s", type=float, default=0.1)
    parser.add_argument("--spacing-m", type=float, default=0.1, help="finest local cell width")
    parser.add_argument(
        "--coarse-spacing-m",
        type=float,
        help="optional coarser width outside the near-source region",
    )
    parser.add_argument("--ranks", type=int, default=20)
    parser.add_argument(
        "--full-domain", action="store_true", help="use the approximate 22 x 14 x 21 m paper domain"
    )
    parser.add_argument("--source-geometry-json", type=Path)
    parser.add_argument(
        "--refinement-region-json",
        type=Path,
        help="JSON object with x, y, and z bounds in metres",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        refinement_region = None
        if args.refinement_region_json is not None:
            raw_region = json.loads(args.refinement_region_json.read_text(encoding="utf-8"))
            if isinstance(raw_region, dict):
                refinement_region = {
                    axis: tuple(bounds) if isinstance(bounds, list) else bounds
                    for axis, bounds in raw_region.items()
                }
            else:
                refinement_region = raw_region
        metadata = prepare_case(
            args.output,
            horizon_s=args.horizon_s,
            spacing_m=args.spacing_m,
            ranks=args.ranks,
            full_domain=args.full_domain,
            source_geometry=args.source_geometry_json,
            coarse_spacing_m=args.coarse_spacing_m,
            refinement_region=refinement_region,
        )
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"prepare_case: {error}") from error
    print(
        json.dumps(
            {
                "output": str(args.output),
                "case_id": metadata["case_id"],
                "mesh_cells_expected": metadata["mesh_cells_expected"],
                "mesh_shape": metadata["mesh_shape"],
                "analytic_expected_mass_kg": metadata["source_histories"][
                    "analytic_expected_mass_kg"
                ],
                "horizon_s": metadata["source_histories"]["horizon_s"],
                "evidence_label": metadata["evidence_label"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
