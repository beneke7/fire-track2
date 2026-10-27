"""Native water-phase flux through an apparatus/external FV control surface.

This module reads the saved ``alphaPhi0.water`` surface field on unique
apparatus/external internal faces. Unlike the audited secondary outlet reader,
which integrates an x-plane cut through four nominal windows, this extractor
selects the actual offset finite-volume interface from ``externalAirZone``
connectivity. The selected surfaces are control surfaces, not assumed to be
the physical outlet apertures. Their area, projection, normals and offsets are
reported separately from the branch STL mouth caps.

Only ten-rank collated OpenFOAM cases with the current named cell zone are
supported. Mesh and field inputs are read-only. Flux is reported as water-phase
volume flux in m3/s; no mass conversion is attempted because phase density is
not directly saved on these faces.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from aerial_drop.i4f_native_face_reader import (
    MOUTH_WINDOWS,
    TARGET_X_M,
    _ascii_list_body,
    _block_list_start,
    _collated_block,
    _field_chunks,
    _parse_internal,
    _parse_patch_scalar_values,
    _parse_uniform_time,
    _read_block_boundary,
    _read_block_labels,
    read_native_mouth_snapshot,
)


@dataclass(frozen=True)
class ControlSurfaceFluxSummary:
    mouth: str
    native_face_count: int
    fv_control_surface_mag_sf_m2: float
    absolute_first_vertex_fan_area_m2: float
    nominal_window_plane_area_m2: float
    stl_branch_cap_projected_area_m2: float | None
    sum_oriented_sf_x_m2: float
    sum_absolute_face_sf_x_m2: float
    projected_sf_x_to_nominal_window_area_ratio: float
    projected_sf_x_to_stl_cap_area_ratio: float | None
    mag_sf_to_stl_cap_area_ratio: float | None
    net_water_volume_flux_m3_s: float
    forward_water_volume_flux_m3_s: float
    reverse_water_volume_flux_m3_s: float
    sum_absolute_water_volume_flux_m3_s: float
    centroid_xyz_m: tuple[float, float, float]
    x_min_m: float
    x_max_m: float
    vertex_bounds_xyz_m: dict[str, tuple[float, float]]
    sum_oriented_sf_xyz_m2: tuple[float, float, float]
    area_weighted_mean_face_normal_xyz: tuple[float, float, float]
    resultant_outward_unit_normal_xyz: tuple[float, float, float] | None
    face_normal_component_bounds_xyz: dict[str, tuple[float, float]]
    projected_x_offset_integral_to_branch_cap_m3: float | None
    projected_x_offset_integral_to_ambient_plane_m3: float | None
    buffer_volume_between_fv_surface_and_branch_cap_m3: float | None
    buffer_volume_status: str
    perimeter_edge_count: int
    perimeter_edge_patch_coverage: dict[str, int]
    uncovered_perimeter_edge_count: int


@dataclass(frozen=True)
class NativeControlSurfaceFluxSnapshot:
    case_path: Path
    time_name: str
    time_value_s: float
    nprocs: int
    summaries: tuple[ControlSurfaceFluxSummary, ...]
    topology: dict[str, Any]
    physical_geometry_reference: dict[str, Any]
    plane_cut_comparison: dict[str, Any]
    input_hashes: dict[str, str]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


_STL_VERTEX_RE = re.compile(rb"\bvertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)")
_STL_BRANCH_BY_MOUTH = {
    "A_lower": "trainA_lowerBranch.stl",
    "A_upper": "trainA_upperBranch.stl",
    "B_lower": "trainB_lowerBranch.stl",
    "B_upper": "trainB_upperBranch.stl",
}


def _read_ascii_stl_triangles(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    vertices = np.asarray(
        [[float(value) for value in match.groups()] for match in _STL_VERTEX_RE.finditer(raw)],
        dtype=np.float64,
    )
    if vertices.size == 0 or vertices.size % 9:
        raise ValueError(f"ASCII STL has an invalid vertex count: {path}")
    triangles = vertices.reshape((-1, 3, 3))
    if not np.isfinite(triangles).all():
        raise ValueError(f"ASCII STL contains non-finite coordinates: {path}")
    return triangles


def _coordinate_surface_topology(triangles: np.ndarray) -> dict[str, Any]:
    """Return boundary loops for a triangle surface with repeated STL vertices."""
    point_ids: dict[tuple[float, float, float], int] = {}
    point_xyz: dict[int, np.ndarray] = {}
    faces: list[tuple[int, ...]] = []
    for triangle in np.asarray(triangles, dtype=np.float64):
        face: list[int] = []
        for point in triangle:
            key = tuple(float(value) for value in point)
            point_id = point_ids.setdefault(key, len(point_ids))
            point_xyz.setdefault(point_id, np.asarray(point, dtype=np.float64))
            face.append(point_id)
        faces.append(tuple(face))
    return _patch_boundary_topology(faces, point_xyz)


def _stl_cap_reference(case: Path) -> dict[str, Any]:
    """Measure each branch STL's planar max-x cap and ambient boundary plane."""
    tri_surface = case / "constant/triSurface"
    mouths: dict[str, Any] = {}
    for mouth, filename in _STL_BRANCH_BY_MOUTH.items():
        path = tri_surface / filename
        if not path.is_file():
            return {"status": "branch STL mouth caps unavailable", "mouths": {}}
        triangles = _read_ascii_stl_triangles(path)
        max_x = float(triangles[:, :, 0].max())
        mask = np.all(np.abs(triangles[:, :, 0] - max_x) <= 1e-8, axis=1)
        cap_triangles = triangles[mask]
        if not len(cap_triangles):
            raise ValueError(f"no planar max-x cap triangles found in {path}")
        area_vectors = 0.5 * np.cross(
            cap_triangles[:, 1] - cap_triangles[:, 0],
            cap_triangles[:, 2] - cap_triangles[:, 0],
        )
        areas = np.linalg.norm(area_vectors, axis=1)
        if np.any(areas <= 0.0):
            raise ValueError(f"degenerate branch STL mouth-cap triangle in {path}")
        vertices = cap_triangles.reshape((-1, 3))
        cap_topology = _coordinate_surface_topology(cap_triangles)
        cap_loops = cap_topology["loops"]
        mouths[mouth] = {
            "path": path.relative_to(case).as_posix(),
            "sha256": sha256(path),
            "plane_x_m": max_x,
            "triangle_count": int(len(cap_triangles)),
            "triangulated_surface_area_m2": float(areas.sum()),
            "projected_area_x_m2": float(np.abs(area_vectors[:, 0]).sum()),
            "boundary_loop_count": len(cap_loops),
            "boundary_edge_count": cap_topology["boundary_edge_count"],
            "boundary_loops": [_public_boundary_loop(loop) for loop in cap_loops],
            "vertex_bounds_yz_m": {
                "y": [float(vertices[:, 1].min()), float(vertices[:, 1].max())],
                "z": [float(vertices[:, 2].min()), float(vertices[:, 2].max())],
            },
        }

    reference: dict[str, Any] = {
        "status": "measured from saved ASCII STL triangles",
        "mouths": mouths,
    }
    ambient_path = tri_surface / "ambientAnnulus.stl"
    if ambient_path.is_file():
        triangles = _read_ascii_stl_triangles(ambient_path)
        ambient_topology = _coordinate_surface_topology(triangles)
        x_values = triangles[:, :, 0]
        if float(np.ptp(x_values)) <= 1e-8:
            area_vectors = 0.5 * np.cross(
                triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
            )
            reference["ambient_annulus_boundary_plane"] = {
                "path": ambient_path.relative_to(case).as_posix(),
                "sha256": sha256(ambient_path),
                "plane_x_m": float(x_values.mean()),
                "triangle_count": int(len(triangles)),
                "surface_area_m2": float(np.linalg.norm(area_vectors, axis=1).sum()),
                "projected_area_x_m2": float(np.abs(area_vectors[:, 0]).sum()),
                "boundary_edge_count": ambient_topology["boundary_edge_count"],
                "interior_edge_count": ambient_topology["interior_edge_count"],
                "boundary_loops": [
                    _public_boundary_loop(loop) for loop in ambient_topology["loops"]
                ],
            }
    wall_path = tri_surface / "apparatusWall.stl"
    if wall_path.is_file():
        triangles = _read_ascii_stl_triangles(wall_path)
        reference["apparatus_wall_extent"] = {
            "path": wall_path.relative_to(case).as_posix(),
            "sha256": sha256(wall_path),
            "max_x_m": float(triangles[:, :, 0].max()),
        }
    ambient_reference = reference.get("ambient_annulus_boundary_plane")
    if ambient_reference is not None:
        ambient_x = float(ambient_reference["plane_x_m"])
        reference["branch_cap_to_ambient_plane_offsets_m"] = {
            mouth: float(item["plane_x_m"] - ambient_x) for mouth, item in mouths.items()
        }
        wall_reference = reference.get("apparatus_wall_extent")
        if wall_reference is not None:
            reference["apparatus_wall_max_x_minus_ambient_plane_m"] = float(
                wall_reference["max_x_m"] - ambient_x
            )
    return reference


def _read_block_points(path: Path, rank: int) -> np.ndarray:
    block = _collated_block(path, rank)
    count, start = _block_list_start(block, path)
    if b"format      ascii" in block[:512]:
        body = _ascii_list_body(block, start, path).decode("ascii")
        values = np.fromstring(body.replace("(", " ").replace(")", " "), sep=" ")
    else:
        values = np.frombuffer(block[start : start + 24 * count], dtype="<f8").copy()
    if values.size != 3 * count:
        raise ValueError(f"rank {rank} point count mismatch in {path}")
    points = values.reshape((-1, 3))
    if not np.isfinite(points).all():
        raise ValueError(f"rank {rank} points contain non-finite coordinates")
    return points


def _read_block_faces(path: Path, rank: int) -> tuple[np.ndarray, np.ndarray]:
    block = _collated_block(path, rank)
    n_offsets, start = _block_list_start(block, path)
    if b"format      ascii" not in block[:512]:
        offsets = np.frombuffer(block[start : start + 4 * n_offsets], dtype="<i4").astype(np.int64)
        label_start = start + 4 * n_offsets
        trailer = re.match(rb"\s*\)\s*(\d+)\s*\(", block[label_start:])
        if trailer is None:
            raise ValueError(f"cannot parse compact binary faces in {path}, rank {rank}")
        n_labels = int(trailer.group(1))
        labels_start = label_start + trailer.end()
        labels = np.frombuffer(
            block[labels_start : labels_start + 4 * n_labels], dtype="<i4"
        ).astype(np.int64)
        if len(offsets) != n_offsets or len(labels) != n_labels:
            raise ValueError(f"rank {rank} compact face-list count mismatch in {path}")
        if offsets[0] != 0 or offsets[-1] != n_labels or np.any(np.diff(offsets) < 0):
            raise ValueError(f"rank {rank} compact face offsets are invalid in {path}")
        return offsets, labels

    body = _ascii_list_body(block, start, path).decode("ascii")
    offsets_list = [0]
    labels_list: list[int] = []
    for match in re.finditer(r"(\d+)\s*\(([^()]*)\)", body):
        count = int(match.group(1))
        labels = np.fromstring(match.group(2), sep=" ", dtype=np.int64)
        if len(labels) != count:
            raise ValueError(f"rank {rank} ASCII face vertex count mismatch in {path}")
        labels_list.extend(int(label) for label in labels)
        offsets_list.append(len(labels_list))
    if len(offsets_list) != n_offsets + 1:
        raise ValueError(f"rank {rank} ASCII face count mismatch in {path}")
    offsets = np.asarray(offsets_list, dtype=np.int64)
    labels = np.asarray(labels_list, dtype=np.int64)
    if offsets[0] != 0 or offsets[-1] != len(labels) or np.any(np.diff(offsets) < 0):
        raise ValueError(f"rank {rank} ASCII face offsets are invalid in {path}")
    return offsets, labels


def _zone_labels(block: bytes, *, zone_name: str, zone_kind: str) -> np.ndarray:
    field = "cellLabels" if zone_kind == "cellZone" else "faceLabels"
    pattern = re.compile(
        rb"\b"
        + re.escape(zone_name.encode())
        + rb"\s*\{\s*type\s+"
        + zone_kind.encode()
        + rb";\s*"
        + field.encode()
        + rb"\s+List<label>\s+(\d+)\s*(;|\()",
        re.S,
    )
    match = pattern.search(block)
    if match is None:
        raise ValueError(f"missing {zone_kind} {zone_name}")
    count = int(match.group(1))
    if count == 0:
        return np.empty(0, dtype=np.int64)
    start = match.end()
    if b"format      ascii" in block[:512]:
        end = re.search(rb"\n\s*\)", block[start:])
        if end is None:
            raise ValueError(f"cannot find ASCII {zone_name} list terminator")
        values = np.fromstring(block[start : start + end.start()].decode("ascii"), sep=" ")
        labels = values.astype(np.int64)
    else:
        labels = np.frombuffer(block[start : start + 4 * count], dtype="<i4").astype(np.int64)
    if len(labels) != count or np.any(labels < 0):
        raise ValueError(f"{zone_name} label count/content is invalid")
    return labels


def _face_polygon(
    local_face: int,
    offsets: np.ndarray,
    labels: np.ndarray,
    local_points: np.ndarray,
    point_map: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    local_ids = labels[int(offsets[local_face]) : int(offsets[local_face + 1])]
    if len(local_ids) < 3:
        raise ValueError(f"face {local_face} has fewer than three vertices")
    return point_map[local_ids], local_points[local_ids]


def _polygon_measure(
    vertices_xyz: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Return v2512-compatible face areaNormal/centre and a fan diagnostic.

    ``face::areaNormal`` sums edge-to-mean-point triangle area normals.
    ``face::centre`` uses the magnitudes of those triangle area vectors as
    weights, including for concave and warped polygons. The pinned OpenCFD
    v2512 implementation is recorded in the geometry evidence packet. The
    final result is the absolute area from the separate first-vertex fan.
    """
    if len(vertices_xyz) < 3 or not np.isfinite(vertices_xyz).all():
        raise ValueError("face polygon is degenerate or non-finite")
    if len(vertices_xyz) == 3:
        area_vector = 0.5 * np.cross(
            vertices_xyz[1] - vertices_xyz[0], vertices_xyz[2] - vertices_xyz[0]
        )
        mag_sf = float(np.linalg.norm(area_vector))
        if mag_sf <= 0.0:
            raise ValueError("triangular face has zero area")
        fan_area = mag_sf
        return area_vector, vertices_xyz.mean(axis=0), mag_sf, fan_area

    p_avg = vertices_xyz.mean(axis=0)
    triangle_vectors = []
    area_vector = np.zeros(3, dtype=np.float64)
    for index in range(len(vertices_xyz)):
        point = vertices_xyz[index]
        next_point = vertices_xyz[(index + 1) % len(vertices_xyz)]
        triangle_vector = 0.5 * np.cross(next_point - point, p_avg - point)
        triangle_vectors.append(triangle_vector)
        area_vector += triangle_vector
    mag_sf = float(np.linalg.norm(area_vector))
    if mag_sf <= 0.0 or not math.isfinite(mag_sf):
        raise ValueError("face polygon has zero or invalid OpenFOAM areaNormal magnitude")
    central_triangle_areas = np.asarray(
        [float(np.linalg.norm(vector)) for vector in triangle_vectors], dtype=np.float64
    )
    centroid_terms = []
    for index in range(len(vertices_xyz)):
        point = vertices_xyz[index]
        next_point = vertices_xyz[(index + 1) % len(vertices_xyz)]
        centroid_terms.append(central_triangle_areas[index] * (point + next_point + p_avg))
    central_area_sum = float(central_triangle_areas.sum())
    center = (
        np.sum(centroid_terms, axis=0) / (3.0 * central_area_sum)
        if central_area_sum > 1e-300
        else p_avg
    )

    p0 = vertices_xyz[0]
    fan_area = 0.0
    for index in range(1, len(vertices_xyz) - 1):
        triangle_vector = 0.5 * np.cross(vertices_xyz[index] - p0, vertices_xyz[index + 1] - p0)
        fan_area += float(np.linalg.norm(triangle_vector))
    return area_vector, center, mag_sf, fan_area


def _cell_zone_mask(case: Path, nprocs: int) -> tuple[np.ndarray, list[np.ndarray]]:
    mesh = case / f"processors{nprocs}/constant/polyMesh"
    zone_path = mesh / "cellZones"
    cell_maps: list[np.ndarray] = []
    zone_local: list[np.ndarray] = []
    max_cell = -1
    for rank in range(nprocs):
        cell_map = _read_block_labels(mesh / "cellProcAddressing", rank)
        zone = _zone_labels(
            _collated_block(zone_path, rank), zone_name="externalAirZone", zone_kind="cellZone"
        )
        if np.any(cell_map < 0) or np.any(zone >= len(cell_map)):
            raise ValueError(f"rank {rank} externalAirZone labels are out of range")
        cell_maps.append(cell_map)
        zone_local.append(zone)
        max_cell = max(max_cell, int(cell_map.max()))
    is_external = np.zeros(max_cell + 1, dtype=bool)
    cell_seen = np.zeros(max_cell + 1, dtype=bool)
    for cell_map, local_zone in zip(cell_maps, zone_local, strict=True):
        if cell_seen[cell_map].any():
            raise ValueError("cellProcAddressing repeats a global cell")
        cell_seen[cell_map] = True
        is_external[cell_map[local_zone]] = True
    if not cell_seen.all():
        raise ValueError(f"cellProcAddressing misses {int(np.count_nonzero(~cell_seen))} cells")
    return is_external, cell_maps


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _polygon_edges(point_ids: np.ndarray) -> tuple[tuple[int, int], ...]:
    return tuple(
        _edge_key(int(point_ids[index]), int(point_ids[(index + 1) % len(point_ids)]))
        for index in range(len(point_ids))
    )


def _point_in_projected_polygon(point_yz: np.ndarray, polygon_yz: np.ndarray) -> bool:
    """Ray-crossing containment test in the apparatus y/z plane."""
    y, z = map(float, point_yz)
    inside = False
    for first, second in zip(polygon_yz, np.roll(polygon_yz, -1, axis=0), strict=True):
        y0, z0 = map(float, first)
        y1, z1 = map(float, second)
        if (z0 > z) != (z1 > z):
            crossing_y = y0 + (z - z0) * (y1 - y0) / (z1 - z0)
            if y < crossing_y:
                inside = not inside
    return inside


def _patch_boundary_topology(
    face_point_ids: list[tuple[int, ...]],
    point_xyz: dict[int, np.ndarray],
    *,
    extract_loops: bool = True,
) -> dict[str, Any]:
    """Find incidence-one boundary loops of unique oriented polygon faces.

    Face winding is retained for signed projected loop areas. Edges shared by
    two faces are interior patch edges and cannot count as patch perimeter.
    """
    edge_faces: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for point_ids in face_point_ids:
        if len(point_ids) < 3:
            raise ValueError("physical patch face has fewer than three vertices")
        for first, second in zip(point_ids, (*point_ids[1:], point_ids[0]), strict=True):
            edge_faces[_edge_key(first, second)].append((first, second))

    if any(len(incidence) > 2 for incidence in edge_faces.values()):
        raise ValueError("physical patch has non-manifold edge incidence")
    boundary_oriented = [incidence[0] for incidence in edge_faces.values() if len(incidence) == 1]
    boundary_edges = frozenset(_edge_key(a, b) for a, b in boundary_oriented)
    interior_edges = frozenset(
        edge for edge, incidence in edge_faces.items() if len(incidence) == 2
    )
    if not extract_loops:
        return {
            "unique_face_count": len(face_point_ids),
            "unique_edge_count": len(edge_faces),
            "boundary_edge_count": len(boundary_oriented),
            "interior_edge_count": len(interior_edges),
            "loops": [],
            "boundary_edges": boundary_edges,
            "interior_edges": interior_edges,
            "nonmanifold_edge_count": 0,
        }
    outgoing: dict[int, list[int]] = defaultdict(list)
    incoming: dict[int, list[int]] = defaultdict(list)
    for first, second in boundary_oriented:
        outgoing[first].append(second)
        incoming[second].append(first)
    vertices = set(outgoing) | set(incoming)
    if any(len(outgoing[point]) != 1 or len(incoming[point]) != 1 for point in vertices):
        raise ValueError("physical patch boundary is not a union of consistently oriented loops")

    edge_direction = set(boundary_oriented)
    loops: list[dict[str, Any]] = []
    while edge_direction:
        first_edge = min(edge_direction)
        start = first_edge[0]
        current = start
        point_ids: list[int] = []
        while True:
            next_points = outgoing[current]
            if len(next_points) != 1:
                raise ValueError("physical patch boundary loop has an ambiguous continuation")
            following = next_points[0]
            edge = (current, following)
            if edge not in edge_direction:
                if following == start:
                    break
                raise ValueError("physical patch boundary loop repeats an edge before closing")
            edge_direction.remove(edge)
            point_ids.append(current)
            current = following
            if current == start:
                break
            if len(point_ids) > len(boundary_oriented):
                raise ValueError("physical patch boundary loop did not close")
        if len(point_ids) < 3:
            raise ValueError("physical patch boundary loop has fewer than three vertices")
        xyz = np.asarray([point_xyz[point_id] for point_id in point_ids], dtype=np.float64)
        area_vector, _center, surface_area, _fan_area = _polygon_measure(xyz)
        loops.append(
            {
                "point_ids": tuple(point_ids),
                "edges": frozenset(
                    _edge_key(a, b)
                    for a, b in zip(point_ids, (*point_ids[1:], point_ids[0]), strict=True)
                ),
                "signed_projected_area_x_m2": float(area_vector[0]),
                "projected_area_abs_x_m2": float(abs(area_vector[0])),
                "area_vector_xyz_m2": tuple(float(value) for value in area_vector),
                "surface_area_m2": float(surface_area),
                "vertex_count": len(point_ids),
                "vertices_xyz_m": tuple(tuple(float(value) for value in row) for row in xyz),
                "vertex_bounds_xyz_m": {
                    axis: (
                        float(xyz[:, index].min()),
                        float(xyz[:, index].max()),
                    )
                    for index, axis in enumerate(("x", "y", "z"))
                },
            }
        )

    # Identify outer boundaries by containment. This uses location/topology,
    # never a nominal opening area or a name-to-area lookup.
    for loop in loops:
        representative = point_xyz[loop["point_ids"][0]][1:]
        containers = [
            other_index
            for other_index, other in enumerate(loops)
            if other is not loop
            and _point_in_projected_polygon(
                representative,
                np.asarray([point_xyz[pid][1:] for pid in other["point_ids"]]),
            )
        ]
        loop["containing_loop_ids"] = tuple(containers)
        loop["classification"] = "outlet_hole" if containers else "outer_or_disconnected"

    outer_candidates = [loop for loop in loops if not loop["containing_loop_ids"]]
    if len(outer_candidates) == 1:
        outer = outer_candidates[0]
        if all(
            loop is outer or loop["containing_loop_ids"] == (loops.index(outer),) for loop in loops
        ):
            outer["classification"] = "outer_boundary"
    for index, loop in enumerate(loops):
        loop["loop_id"] = index

    return {
        "unique_face_count": len(face_point_ids),
        "unique_edge_count": len(edge_faces),
        "boundary_edge_count": len(boundary_oriented),
        "interior_edge_count": sum(len(incidence) == 2 for incidence in edge_faces.values()),
        "loops": loops,
        "boundary_edges": boundary_edges,
        "interior_edges": interior_edges,
        "nonmanifold_edge_count": 0,
    }


def _public_boundary_loop(loop: dict[str, Any]) -> dict[str, Any]:
    """Exclude private point/edge ids from compact geometry evidence."""
    return {key: value for key, value in loop.items() if key not in {"point_ids", "edges"}}


def _segment_on_projected_side(
    edge: tuple[int, int],
    point_xyz: dict[int, np.ndarray],
    side_start_yz: np.ndarray,
    side_end_yz: np.ndarray,
    *,
    tolerance_m: float,
) -> tuple[bool, float, float]:
    """Check whether an edge lies on a finite y/z cap-outline side."""
    start = np.asarray(side_start_yz, dtype=np.float64)
    end = np.asarray(side_end_yz, dtype=np.float64)
    vector = end - start
    length = float(np.linalg.norm(vector))
    if length == 0.0:
        raise ValueError("STL cap boundary contains a zero-length edge")
    unit = vector / length
    coordinates = [point_xyz[int(point_id)][1:] for point_id in edge]
    parameters = []
    max_deviation = 0.0
    for coordinate in coordinates:
        delta = np.asarray(coordinate, dtype=np.float64) - start
        parameter_m = float(np.dot(delta, unit))
        perpendicular = delta - parameter_m * unit
        max_deviation = max(max_deviation, float(np.linalg.norm(perpendicular)))
        parameters.append(parameter_m)
    is_on_side = (
        max_deviation <= tolerance_m
        and min(parameters) >= -tolerance_m
        and max(parameters) <= length + tolerance_m
    )
    projected_length = abs(parameters[1] - parameters[0]) if is_on_side else 0.0
    return is_on_side, projected_length, max_deviation


def _compare_ambient_hole_rims_to_caps(
    ambient_patch: dict[str, Any],
    point_xyz: dict[int, np.ndarray],
    physical_geometry_reference: dict[str, Any],
    *,
    tolerance_m: float = 2e-7,
) -> dict[str, Any]:
    """Match actual ambientAnnulus hole loops to STL cap outlines by location."""
    hole_loops = [
        loop for loop in ambient_patch["loops"] if loop["classification"] == "outlet_hole"
    ]
    available_holes = list(hole_loops)
    matched: dict[str, Any] = {}
    for mouth, cap in sorted(physical_geometry_reference.get("mouths", {}).items()):
        cap_loops = cap.get("boundary_loops", [])
        if len(cap_loops) != 1:
            matched[mouth] = {"status": "branch cap does not have one boundary loop"}
            continue
        cap_loop = cap_loops[0]
        cap_vertices = np.asarray(cap_loop["vertices_xyz_m"], dtype=np.float64)
        cap_yz_center = np.mean(cap_vertices[:, 1:], axis=0)
        if not available_holes:
            matched[mouth] = {"status": "no unmatched ambientAnnulus hole loop"}
            continue
        center_distance = [
            float(
                np.linalg.norm(
                    np.mean(np.asarray(loop["vertices_xyz_m"], dtype=np.float64)[:, 1:], axis=0)
                    - cap_yz_center
                )
            )
            for loop in available_holes
        ]
        selected = int(np.argmin(center_distance))
        hole = available_holes.pop(selected)
        next_distance = min(
            (distance for index, distance in enumerate(center_distance) if index != selected),
            default=None,
        )
        cap_bounds = cap_loop["vertex_bounds_xyz_m"]
        hole_bounds = hole["vertex_bounds_xyz_m"]
        bounds_delta = {
            axis: max(
                abs(cap_bounds[axis][0] - hole_bounds[axis][0]),
                abs(cap_bounds[axis][1] - hole_bounds[axis][1]),
            )
            for axis in ("y", "z")
        }

        cap_sides = []
        assigned_hole_edges: set[tuple[int, int]] = set()
        for index, start in enumerate(cap_vertices):
            end = cap_vertices[(index + 1) % len(cap_vertices)]
            start_yz, end_yz = start[1:], end[1:]
            length = float(np.linalg.norm(end_yz - start_yz))
            rim_edge_lengths = []
            max_deviation = 0.0
            for edge in hole["edges"]:
                on_side, projected_length, deviation = _segment_on_projected_side(
                    edge,
                    point_xyz,
                    start_yz,
                    end_yz,
                    tolerance_m=tolerance_m,
                )
                if on_side:
                    assigned_hole_edges.add(edge)
                    rim_edge_lengths.append(projected_length)
                    max_deviation = max(max_deviation, deviation)
            interior_edge_lengths = []
            for edge in ambient_patch["interior_edges"]:
                on_side, projected_length, _deviation = _segment_on_projected_side(
                    edge,
                    point_xyz,
                    start_yz,
                    end_yz,
                    tolerance_m=tolerance_m,
                )
                if on_side:
                    interior_edge_lengths.append(projected_length)
            covered_length = float(sum(rim_edge_lengths))
            cap_sides.append(
                {
                    "side_index": index,
                    "cap_side_length_m": length,
                    "true_hole_rim_mesh_edge_count": len(rim_edge_lengths),
                    "true_hole_rim_projected_length_m": covered_length,
                    "true_hole_rim_projected_length_ratio_to_cap_side": covered_length / length,
                    "interior_annulus_edge_count_on_cap_side": len(interior_edge_lengths),
                    "interior_annulus_projected_length_m": float(sum(interior_edge_lengths)),
                    "max_true_rim_edge_deviation_from_cap_side_m": max_deviation,
                }
            )

        mouth_reference = physical_geometry_reference.get("mouths", {}).get(mouth, {})
        cap_area = float(mouth_reference.get("projected_area_x_m2", 0.0))
        hole_area = float(hole["projected_area_abs_x_m2"])
        cap_x = float(mouth_reference.get("plane_x_m", 0.0))
        hole_x_bounds = hole_bounds["x"]
        matched[mouth] = {
            "status": "matched by y/z location to ambientAnnulus boundary loop",
            "ambientAnnulus_loop_id": int(hole["loop_id"]),
            "center_distance_to_selected_loop_m": center_distance[selected],
            "center_distance_to_next_candidate_loop_m": next_distance,
            "ambientAnnulus_loop_classification": hole["classification"],
            "ambientAnnulus_loop_edge_count": len(hole["edges"]),
            "ambientAnnulus_loop_signed_projected_area_x_m2": float(
                hole["signed_projected_area_x_m2"]
            ),
            "branch_cap_projected_area_x_m2": cap_area,
            "absolute_projected_area_difference_m2": abs(hole_area - cap_area),
            "yz_bounds_max_abs_difference_m": bounds_delta,
            "cap_plane_x_m": cap_x,
            "ambient_hole_loop_x_bounds_m": hole_x_bounds,
            "cap_plane_minus_hole_loop_max_x_m": cap_x - hole_x_bounds[1],
            "cap_outline_side_count": len(cap_sides),
            "cap_outline_sides_covered_by_true_hole_rim": sum(
                side["true_hole_rim_projected_length_ratio_to_cap_side"] >= 1.0 - 1e-6
                and side["interior_annulus_edge_count_on_cap_side"] == 0
                for side in cap_sides
            ),
            "cap_outline_sides_with_interior_annulus_edges": sum(
                side["interior_annulus_edge_count_on_cap_side"] > 0 for side in cap_sides
            ),
            "all_hole_loop_edges_follow_cap_outline": assigned_hole_edges == hole["edges"],
            "cap_outline_sides": cap_sides,
        }
    return {
        "matching_method": "nearest unmatched hole-loop centroid in y/z, followed by cap-boundary side coverage",
        "outline_tolerance_m": tolerance_m,
        "ambient_hole_loop_count": len(hole_loops),
        "by_mouth": matched,
        "unmatched_hole_loop_ids": [int(loop["loop_id"]) for loop in available_holes],
    }


def _surface_components(faces: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    parent = list(range(len(faces)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        root_first = find(first)
        root_second = find(second)
        if root_first != root_second:
            parent[root_second] = root_first

    edge_owner: dict[tuple[int, int], int] = {}
    for index, face in enumerate(faces):
        for edge in face["edges"]:
            prior = edge_owner.setdefault(edge, index)
            union(index, prior)
    components: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, face in enumerate(faces):
        components[find(index)].append(face)
    return list(components.values())


def _validate_control_surface(
    faces: list[dict[str, Any]],
    *,
    boundary_edges_by_patch: dict[str, set[tuple[int, int]]],
    wall_face_ids: set[int],
    interior_edges_by_patch: dict[str, set[tuple[int, int]]] | None = None,
    boundary_loops_by_patch: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    face_ids = [int(face["global_face_id"]) for face in faces]
    if len(face_ids) != len(set(face_ids)):
        raise ValueError(
            "selected apparatus/external control surface contains duplicate global faces"
        )
    wall_intersections = len(set(face_ids).intersection(wall_face_ids))
    if wall_intersections:
        raise ValueError(
            f"internal mouth control surface intersects {wall_intersections} wall faces"
        )
    interior_edges_by_patch = interior_edges_by_patch or {}
    boundary_loops_by_patch = boundary_loops_by_patch or {}
    component_results = []
    for component in _surface_components(faces):
        edge_counts = Counter(edge for face in component for edge in face["edges"])
        if any(count > 2 for count in edge_counts.values()):
            raise ValueError("mouth control surface contains non-manifold edges")
        perimeter = {edge for edge, count in edge_counts.items() if count == 1}
        covered: set[tuple[int, int]] = set()
        patch_coverage = {}
        for patch, edges in boundary_edges_by_patch.items():
            overlap = perimeter.intersection(edges)
            if overlap:
                patch_coverage[patch] = len(overlap)
                covered.update(overlap)
        uncovered = len(perimeter - covered)
        ambient_hole_matches = [
            int(loop["loop_id"])
            for loop in boundary_loops_by_patch.get("ambientAnnulus", [])
            if loop.get("classification") == "outlet_hole" and loop.get("edges") == perimeter
        ]
        ambient_true_rim_edges = perimeter.intersection(
            boundary_edges_by_patch.get("ambientAnnulus", set())
        )
        ambient_interior_edges = perimeter.intersection(
            interior_edges_by_patch.get("ambientAnnulus", set())
        )
        component_point_xyz: dict[int, np.ndarray] = {}
        for face in component:
            point_ids = np.asarray(face["point_ids"], dtype=np.int64)
            coordinates = np.asarray(face["vertices_xyz_m"], dtype=np.float64)
            if len(point_ids) != len(coordinates):
                raise ValueError("control-surface face point/coordinate counts differ")
            for point_id, coordinate in zip(point_ids, coordinates, strict=True):
                prior = component_point_xyz.setdefault(int(point_id), coordinate.copy())
                if not np.allclose(prior, coordinate, rtol=0.0, atol=2e-12):
                    raise ValueError("control-surface global point coordinates disagree")
        perimeter_segments = [
            [[float(value) for value in component_point_xyz[point_id]] for point_id in edge]
            for edge in sorted(perimeter)
        ]
        other_true_patch_edges = perimeter.intersection(
            set().union(
                *(
                    edges
                    for patch, edges in boundary_edges_by_patch.items()
                    if patch != "ambientAnnulus"
                )
            )
            if any(patch != "ambientAnnulus" for patch in boundary_edges_by_patch)
            else set()
        )
        other_interior_patch_edges = perimeter.intersection(
            set().union(
                *(
                    edges
                    for patch, edges in interior_edges_by_patch.items()
                    if patch != "ambientAnnulus"
                )
            )
            if any(patch != "ambientAnnulus" for patch in interior_edges_by_patch)
            else set()
        )
        component_results.append(
            {
                "face_count": len(component),
                "perimeter_edge_count": len(perimeter),
                "perimeter_edge_segments_xyz_m": perimeter_segments,
                "perimeter_edge_patch_coverage": patch_coverage,
                "uncovered_perimeter_edge_count": uncovered,
                "ambient_annulus_true_hole_rim_edge_count": len(ambient_true_rim_edges),
                "ambient_annulus_interior_patch_edge_count": len(ambient_interior_edges),
                "other_true_physical_patch_edge_count": len(other_true_patch_edges),
                "other_interior_physical_patch_edge_count": len(other_interior_patch_edges),
                "exact_ambient_annulus_hole_loop_match_count": len(ambient_hole_matches),
                "matched_ambient_annulus_hole_loop_ids": ambient_hole_matches,
                "perimeter_edges_not_on_any_true_physical_patch_boundary": uncovered,
                "perimeter_edges_not_on_any_known_physical_patch_edge": len(
                    perimeter - covered - ambient_interior_edges - other_interior_patch_edges
                ),
            }
        )
    return {
        "unique_face_count": len(face_ids),
        "selected_wall_face_intersections": wall_intersections,
        "all_perimeter_edges_covered_by_true_physical_patch_boundary": all(
            component["perimeter_edges_not_on_any_true_physical_patch_boundary"] == 0
            for component in component_results
        ),
        "all_components_exactly_match_ambient_annulus_hole_loops": all(
            component["exact_ambient_annulus_hole_loop_match_count"] == 1
            for component in component_results
        )
        if boundary_loops_by_patch.get("ambientAnnulus")
        else None,
        "components": component_results,
    }


def _assign_mouths(
    components: list[list[dict[str, Any]]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    if len(components) != 4:
        raise ValueError(
            f"expected four disconnected apparatus mouth surfaces, found {len(components)}"
        )
    centers: dict[str, tuple[float, float]] = {}
    for name, window in MOUTH_WINDOWS.items():
        centers[name] = (
            0.5 * (window["y_min"] + window["y_max"]),
            0.5 * (window["z_min"] + window["z_max"]),
        )
    component_centers = []
    for component in components:
        area = np.asarray([face["area_m2"] for face in component], dtype=np.float64)
        yz = np.asarray([face["centroid_xyz_m"][1:] for face in component], dtype=np.float64)
        component_centers.append(np.average(yz, axis=0, weights=area))
    names = tuple(centers)
    choices = []
    for assignment in itertools.permutations(names):
        cost = sum(
            float(np.sum((component_centers[i] - np.asarray(centers[name])) ** 2))
            for i, name in enumerate(assignment)
        )
        choices.append((cost, assignment))
    choices.sort(key=lambda item: item[0])
    if len(choices) > 1 and math.isclose(
        choices[0][0], choices[1][0], rel_tol=1e-12, abs_tol=1e-14
    ):
        raise ValueError("mouth component assignment to nominal labels is ambiguous")
    return [(name, components[i]) for i, name in enumerate(choices[0][1])]


def _summarize_components(
    faces: list[dict[str, Any]],
    *,
    boundary_edges_by_patch: dict[str, set[tuple[int, int]]],
    physical_geometry_reference: dict[str, Any],
) -> tuple[ControlSurfaceFluxSummary, ...]:
    components = _surface_components(faces)
    assigned = _assign_mouths(components)
    summaries: list[ControlSurfaceFluxSummary] = []
    for mouth, component in sorted(assigned, key=lambda item: item[0]):
        q = np.asarray([face["water_volume_flux_m3_s"] for face in component], dtype=np.float64)
        areas = np.asarray([face["area_m2"] for face in component], dtype=np.float64)
        fan_areas = np.asarray(
            [face["first_vertex_fan_area_m2"] for face in component], dtype=np.float64
        )
        centers = np.asarray([face["centroid_xyz_m"] for face in component], dtype=np.float64)
        area_vectors = np.asarray(
            [face["outward_area_vector_xyz_m2"] for face in component], dtype=np.float64
        )
        vertex_arrays = [face["vertices_xyz_m"] for face in component]
        all_vertices = np.concatenate(vertex_arrays, axis=0)
        bounds = {
            axis: (float(all_vertices[:, i].min()), float(all_vertices[:, i].max()))
            for i, axis in enumerate(("x", "y", "z"))
        }
        centroid = np.average(centers, axis=0, weights=areas)
        net_area_vector = np.sum(area_vectors, axis=0)
        area_vector_norm = float(np.linalg.norm(net_area_vector))
        unit_normal = (
            tuple(float(value) for value in net_area_vector / area_vector_norm)
            if area_vector_norm > 0.0
            else None
        )
        edge_counts = Counter(edge for face in component for edge in face["edges"])
        perimeter = {edge for edge, count in edge_counts.items() if count == 1}
        if any(count > 2 for count in edge_counts.values()):
            raise ValueError(f"mouth {mouth} interface has non-manifold surface edges")
        patch_coverage = {
            patch: sum(edge in edges for edge in perimeter)
            for patch, edges in boundary_edges_by_patch.items()
            if any(edge in edges for edge in perimeter)
        }
        covered = set()
        for patch, edges in boundary_edges_by_patch.items():
            covered.update(perimeter.intersection(edges))
        nominal = MOUTH_WINDOWS[mouth]
        nominal_area = (nominal["y_max"] - nominal["y_min"]) * (nominal["z_max"] - nominal["z_min"])
        cap = physical_geometry_reference.get("mouths", {}).get(mouth)
        cap_area = float(cap["projected_area_x_m2"]) if cap is not None else None
        sf_x = float(np.sum(area_vectors[:, 0]))
        sf_x_abs = float(np.abs(area_vectors[:, 0]).sum())
        face_normals = area_vectors / areas[:, np.newaxis]
        normal_bounds = {
            axis: (float(face_normals[:, index].min()), float(face_normals[:, index].max()))
            for index, axis in enumerate(("x", "y", "z"))
        }
        cap_plane_x = float(cap["plane_x_m"]) if cap is not None else None
        ambient_plane = physical_geometry_reference.get("ambient_annulus_boundary_plane")
        ambient_plane_x = float(ambient_plane["plane_x_m"]) if ambient_plane else None
        projected_offset_to_cap = (
            float(np.sum((centers[:, 0] - cap_plane_x) * area_vectors[:, 0]))
            if cap_plane_x is not None
            else None
        )
        projected_offset_to_ambient = (
            float(np.sum((centers[:, 0] - ambient_plane_x) * area_vectors[:, 0]))
            if ambient_plane_x is not None
            else None
        )
        if cap_area is None:
            buffer_status = "not determined: no branch STL cap reference was found"
        else:
            buffer_status = (
                "not determined: the FV surface projection differs from the branch-cap projection; "
                "the x-offset integral is reported as a projected geometric diagnostic, not as an enclosed buffer volume"
            )
        summaries.append(
            ControlSurfaceFluxSummary(
                mouth=mouth,
                native_face_count=len(component),
                fv_control_surface_mag_sf_m2=float(areas.sum()),
                absolute_first_vertex_fan_area_m2=float(fan_areas.sum()),
                nominal_window_plane_area_m2=float(nominal_area),
                stl_branch_cap_projected_area_m2=cap_area,
                sum_oriented_sf_x_m2=sf_x,
                sum_absolute_face_sf_x_m2=sf_x_abs,
                projected_sf_x_to_nominal_window_area_ratio=float(sf_x / nominal_area),
                projected_sf_x_to_stl_cap_area_ratio=(
                    sf_x / cap_area if cap_area is not None and cap_area > 0.0 else None
                ),
                mag_sf_to_stl_cap_area_ratio=(
                    float(areas.sum() / cap_area)
                    if cap_area is not None and cap_area > 0.0
                    else None
                ),
                net_water_volume_flux_m3_s=float(q.sum()),
                forward_water_volume_flux_m3_s=float(np.maximum(q, 0.0).sum()),
                reverse_water_volume_flux_m3_s=float(np.maximum(-q, 0.0).sum()),
                sum_absolute_water_volume_flux_m3_s=float(np.abs(q).sum()),
                centroid_xyz_m=tuple(float(value) for value in centroid),
                x_min_m=float(all_vertices[:, 0].min()),
                x_max_m=float(all_vertices[:, 0].max()),
                vertex_bounds_xyz_m=bounds,
                sum_oriented_sf_xyz_m2=tuple(float(value) for value in net_area_vector),
                area_weighted_mean_face_normal_xyz=tuple(
                    float(value) for value in net_area_vector / float(areas.sum())
                ),
                resultant_outward_unit_normal_xyz=unit_normal,
                face_normal_component_bounds_xyz=normal_bounds,
                projected_x_offset_integral_to_branch_cap_m3=projected_offset_to_cap,
                projected_x_offset_integral_to_ambient_plane_m3=projected_offset_to_ambient,
                buffer_volume_between_fv_surface_and_branch_cap_m3=None,
                buffer_volume_status=buffer_status,
                perimeter_edge_count=len(perimeter),
                perimeter_edge_patch_coverage=patch_coverage,
                uncovered_perimeter_edge_count=len(perimeter - covered),
            )
        )
    return tuple(summaries)


def _compare_with_existing_xplane_cut(
    case: Path,
    time_name: str,
    nprocs: int,
    summaries: tuple[ControlSurfaceFluxSummary, ...],
) -> dict[str, Any]:
    """Compare the offset FV surface with a separately read nominal-window x-plane cut."""
    if not case.is_dir():
        raise FileNotFoundError(f"case directory does not exist: {case}")
    required_legacy_inputs = (
        case / "constant/polyMesh/points",
        case / "constant/polyMesh/faces",
        case / "constant/polyMesh/owner",
        case / "constant/polyMesh/neighbour",
        case / "constant/C",
    )
    missing_inputs = [
        path.relative_to(case).as_posix() for path in required_legacy_inputs if not path.is_file()
    ]
    if missing_inputs:
        control_by_mouth = {summary.mouth: summary for summary in summaries}
        return {
            "comparison_source": "existing audited read_native_mouth_snapshot x-plane cut; no changes to that reader",
            "status": "unavailable_missing_legacy_geometry",
            "unavailable_required_inputs": missing_inputs,
            "requested_target_x_m": TARGET_X_M,
            "geometry_interpretation_note": "The x-plane cut selects faces in fixed nominal y/z mouth windows. Its projected area is not independent evidence of the physical hole outline; use the incidence-one ambientAnnulus loops compared with the branch STL cap boundaries for that geometry check.",
            "xplane_selection_metadata": None,
            "processor_pair_check": None,
            "by_mouth": [
                {
                    "mouth": mouth,
                    "xplane_cut_x_m": None,
                    "xplane_face_count": None,
                    "xplane_projected_area_m2": None,
                    "xplane_native_water_Q_m3_s": None,
                    "fv_control_surface_water_Q_m3_s": control_by_mouth[
                        mouth
                    ].net_water_volume_flux_m3_s,
                    "control_minus_xplane_Q_m3_s": None,
                    "relative_difference_when_resolved": None,
                    "comparison_state": "unavailable_missing_legacy_geometry",
                }
                for mouth in MOUTH_WINDOWS
            ],
        }
    snapshot = read_native_mouth_snapshot(case, time_name, nprocs=nprocs)
    control_by_mouth = {summary.mouth: summary for summary in summaries}
    comparisons = []
    for mouth, faces in snapshot.mouth_faces.items():
        xplane_q = float(sum(face.native_alpha_phi_water_m3_s for face in faces))
        control_q = control_by_mouth[mouth].net_water_volume_flux_m3_s
        max_q = max(abs(xplane_q), abs(control_q))
        comparisons.append(
            {
                "mouth": mouth,
                "xplane_cut_x_m": snapshot.selection_metadata["target_x_cell_center_m"],
                "xplane_face_count": len(faces),
                "xplane_projected_area_m2": float(
                    sum(face.outward_projected_area_m2 for face in faces)
                ),
                "xplane_native_water_Q_m3_s": xplane_q,
                "fv_control_surface_water_Q_m3_s": control_q,
                "control_minus_xplane_Q_m3_s": control_q - xplane_q,
                "relative_difference_when_resolved": (
                    (control_q - xplane_q) / max_q if max_q > 1e-18 else None
                ),
                "comparison_state": "near_zero_traces_relative_difference_withheld"
                if max_q <= 1e-18
                else "resolved_flux_comparison",
            }
        )
    return {
        "comparison_source": "existing audited read_native_mouth_snapshot x-plane cut; no changes to that reader",
        "geometry_interpretation_note": "The x-plane cut selects faces in fixed nominal y/z mouth windows. Its projected area is not independent evidence of the physical hole outline; use the incidence-one ambientAnnulus loops compared with the branch STL cap boundaries for that geometry check.",
        "xplane_selection_metadata": snapshot.selection_metadata,
        "processor_pair_check": snapshot.processor_pair_summary,
        "by_mouth": comparisons,
    }


def _processor_pair_outward_flux(
    *,
    first_flux_owner_outward: float,
    first_face_map_sign: int,
    first_owner_is_apparatus: bool,
    second_flux_owner_outward: float,
    second_face_map_sign: int,
    second_owner_is_apparatus: bool,
    relative_tolerance: float = 1e-8,
    absolute_tolerance: float = 1e-14,
) -> tuple[float, dict[str, float]]:
    """Check a mirrored processor face and return one apparatus-outward flux."""
    if first_face_map_sign not in (-1, 1) or second_face_map_sign not in (-1, 1):
        raise ValueError("processor face maps must use signed one-based orientations")
    if first_face_map_sign != -second_face_map_sign:
        raise ValueError("paired processor faceProcAddressing signs must be opposite")
    if first_owner_is_apparatus == second_owner_is_apparatus:
        raise ValueError("processor pair must contain one apparatus and one external owner")
    first_global = first_flux_owner_outward * first_face_map_sign
    second_global = second_flux_owner_outward * second_face_map_sign
    absolute_error = abs(first_global - second_global)
    relative_error = absolute_error / max(abs(first_global), abs(second_global), 1e-300)
    if absolute_error > absolute_tolerance and relative_error > relative_tolerance:
        raise ValueError(
            "mirrored processor alphaPhi0.water values disagree after signed face mapping"
        )
    apparatus_local = (
        first_flux_owner_outward if first_owner_is_apparatus else second_flux_owner_outward
    )
    return float(apparatus_local), {
        "absolute_error_m3_s": float(absolute_error),
        "relative_error": float(relative_error),
    }


def read_native_apparatus_control_surface_flux(
    case_path: Path, time_name: str, *, nprocs: int = 10
) -> NativeControlSurfaceFluxSnapshot:
    """Extract unique actual apparatus/external interface water fluxes."""
    case = case_path.resolve()
    processor_mesh = case / f"processors{nprocs}/constant/polyMesh"
    time_dir = case / f"processors{nprocs}/{time_name}"
    if not processor_mesh.is_dir() or not time_dir.is_dir():
        raise FileNotFoundError(f"missing collated mesh/checkpoint for {case} at {time_name}")
    physical_geometry_reference = _stl_cap_reference(case)
    time_value, time_label = _parse_uniform_time(time_dir / "uniform/time")
    if time_label != time_name or not math.isclose(
        time_value, float(time_name), abs_tol=1e-9, rel_tol=0.0
    ):
        raise ValueError("uniform/time does not match requested checkpoint directory")

    external, cell_maps = _cell_zone_mask(case, nprocs)
    processor_face_records: dict[int, list[dict[str, Any]]] = defaultdict(list)
    internal_records: dict[int, dict[str, Any]] = {}
    boundary_patch_faces: dict[str, dict[int, tuple[int, ...]]] = defaultdict(dict)
    boundary_face_ids: dict[str, set[int]] = defaultdict(set)
    point_seen: dict[int, np.ndarray] = {}
    rank_mesh: list[dict[str, Any]] = []

    for rank in range(nprocs):
        mesh = processor_mesh
        cell_map = cell_maps[rank]
        point_map = _read_block_labels(mesh / "pointProcAddressing", rank)
        local_points = _read_block_points(mesh / "points", rank)
        if len(point_map) != len(local_points):
            raise ValueError(f"rank {rank} pointProcAddressing length mismatch")
        for global_point, xyz in zip(point_map, local_points, strict=True):
            prior = point_seen.setdefault(int(global_point), xyz.copy())
            if not np.allclose(prior, xyz, rtol=0.0, atol=2e-12):
                raise ValueError(
                    f"global point {global_point} has inconsistent processor coordinates"
                )
        offsets, vertex_labels = _read_block_faces(mesh / "faces", rank)
        local_owner = _read_block_labels(mesh / "owner", rank)
        local_neighbour = _read_block_labels(mesh / "neighbour", rank)
        face_map = _read_block_labels(mesh / "faceProcAddressing", rank)
        boundary = _read_block_boundary(mesh / "boundary", rank)
        if len(offsets) != len(face_map) + 1 or len(local_owner) != len(face_map):
            raise ValueError(f"rank {rank} face/owner/addressing count mismatch")
        if len(local_neighbour) > len(local_owner):
            raise ValueError(f"rank {rank} has more local neighbours than faces")
        if np.any(face_map == 0):
            raise ValueError(f"rank {rank} faceProcAddressing contains an invalid zero label")
        if (
            np.any(local_owner < 0)
            or np.any(local_owner >= len(cell_map))
            or np.any(local_neighbour < 0)
            or np.any(local_neighbour >= len(cell_map))
            or np.any(vertex_labels < 0)
            or np.any(vertex_labels >= len(local_points))
        ):
            raise ValueError(f"rank {rank} mesh labels are outside their local arrays")
        rank_mesh.append(
            {
                "point_map": point_map,
                "points": local_points,
                "offsets": offsets,
                "vertices": vertex_labels,
                "owner": local_owner,
                "neighbour": local_neighbour,
                "face_map": face_map,
                "boundary": boundary,
            }
        )
        for local_face in range(len(local_neighbour)):
            gid = abs(int(face_map[local_face])) - 1
            sign = 1 if face_map[local_face] > 0 else -1
            local_owner_global = int(cell_map[local_owner[local_face]])
            local_neighbour_global = int(cell_map[local_neighbour[local_face]])
            if sign > 0:
                global_owner, global_neighbour = local_owner_global, local_neighbour_global
            else:
                global_owner, global_neighbour = local_neighbour_global, local_owner_global
            if external[global_owner] == external[global_neighbour]:
                continue
            if gid in internal_records:
                raise ValueError(f"internal global face {gid} is represented more than once")
            point_ids, xyz = _face_polygon(
                local_face, offsets, vertex_labels, local_points, point_map
            )
            sf_local, centroid, area, fan_area = _polygon_measure(xyz)
            sf_global = sf_local * sign
            owner_is_apparatus = not bool(external[global_owner])
            outward_sf = sf_global if owner_is_apparatus else -sf_global
            internal_records[gid] = {
                "global_face_id": gid,
                "rank": rank,
                "local_face": local_face,
                "face_map_sign": sign,
                "global_owner_is_apparatus": owner_is_apparatus,
                "local_owner_is_apparatus": not bool(external[local_owner_global]),
                "point_ids": point_ids,
                "vertices_xyz_m": xyz,
                "centroid_xyz_m": centroid,
                "area_m2": area,
                "first_vertex_fan_area_m2": fan_area,
                "outward_area_vector_xyz_m2": outward_sf,
                "edges": _polygon_edges(point_ids),
                "global_owner": global_owner,
                "global_neighbour": global_neighbour,
            }

        for patch_name, patch_type, patch_count, start_face in boundary:
            for offset in range(patch_count):
                local_face = start_face + offset
                gid = abs(int(face_map[local_face])) - 1
                sign = 1 if face_map[local_face] > 0 else -1
                owner_global = int(cell_map[local_owner[local_face]])
                if patch_type == "processor":
                    processor_face_records[gid].append(
                        {
                            "global_face_id": gid,
                            "rank": rank,
                            "local_face": local_face,
                            "patch": patch_name,
                            "patch_offset": offset,
                            "face_map_sign": sign,
                            "owner_global": owner_global,
                        }
                    )
                else:
                    boundary_face_ids[patch_name].add(gid)
                    point_ids, _xyz = _face_polygon(
                        local_face, offsets, vertex_labels, local_points, point_map
                    )
                    if sign < 0:
                        point_ids = point_ids[::-1]
                    if gid in boundary_patch_faces[patch_name]:
                        raise ValueError(f"physical patch {patch_name} repeats global face {gid}")
                    boundary_patch_faces[patch_name][gid] = tuple(map(int, point_ids))

    if len(point_seen) == 0:
        raise ValueError("processor mesh has no mapped points")
    if len(point_seen) != max(point_seen) + 1:
        raise ValueError("pointProcAddressing does not cover a contiguous global point range")
    patch_topology_internal: dict[str, dict[str, Any]] = {}
    boundary_edges: dict[str, set[tuple[int, int]]] = {}
    interior_edges: dict[str, set[tuple[int, int]]] = {}
    for patch_name, patch_faces in boundary_patch_faces.items():
        patch_topology_internal[patch_name] = _patch_boundary_topology(
            list(patch_faces.values()),
            point_seen,
            extract_loops=(patch_name == "ambientAnnulus"),
        )
        boundary_edges[patch_name] = set(patch_topology_internal[patch_name]["boundary_edges"])
        interior_edges[patch_name] = set(patch_topology_internal[patch_name]["interior_edges"])
    ambient_patch = patch_topology_internal.get("ambientAnnulus")
    ambient_geometry_check: dict[str, Any] | None = None
    if ambient_patch is not None:
        ambient_face_area_vectors = []
        ambient_face_areas = []
        ambient_face_sf_x_abs = []
        for point_ids in boundary_patch_faces["ambientAnnulus"].values():
            xyz = np.asarray([point_seen[point_id] for point_id in point_ids], dtype=np.float64)
            area_vector, _center, area, _fan_area = _polygon_measure(xyz)
            ambient_face_area_vectors.append(area_vector)
            ambient_face_areas.append(area)
            ambient_face_sf_x_abs.append(abs(float(area_vector[0])))
        ambient_patch_area_vector = np.sum(ambient_face_area_vectors, axis=0)
        ambient_loop_signed_area_x = sum(
            float(loop["signed_projected_area_x_m2"]) for loop in ambient_patch["loops"]
        )
        stl_ambient = physical_geometry_reference.get("ambient_annulus_boundary_plane", {})
        ambient_geometry_check = {
            "face_count": ambient_patch["unique_face_count"],
            "unique_edge_count": ambient_patch["unique_edge_count"],
            "true_boundary_edge_count": ambient_patch["boundary_edge_count"],
            "interior_patch_edge_count": ambient_patch["interior_edge_count"],
            "sum_oriented_area_vector_xyz_m2": tuple(
                float(value) for value in ambient_patch_area_vector
            ),
            "boundary_loop_signed_projected_area_x_sum_m2": ambient_loop_signed_area_x,
            "boundary_loop_to_face_area_vector_x_closure_error_m2": float(
                ambient_loop_signed_area_x - ambient_patch_area_vector[0]
            ),
            "sum_absolute_face_sf_x_m2": float(sum(ambient_face_sf_x_abs)),
            "sum_face_mag_sf_m2": float(sum(ambient_face_areas)),
            "boundary_loop_count": len(ambient_patch["loops"]),
            "boundary_loops": [_public_boundary_loop(loop) for loop in ambient_patch["loops"]],
            "stl_hole_rim_comparison": _compare_ambient_hole_rims_to_caps(
                ambient_patch, point_seen, physical_geometry_reference
            ),
            "stl_annulus_projected_area_x_m2": stl_ambient.get("projected_area_x_m2"),
            "stl_annulus_surface_area_m2": stl_ambient.get("surface_area_m2"),
        }
    face_zone_path = processor_mesh / "faceZones"
    excluded_zone_ids: set[int] = set()
    for rank in range(nprocs):
        local_lamella_faces = _zone_labels(
            _collated_block(face_zone_path, rank), zone_name="lamellae", zone_kind="faceZone"
        )
        rank_face_map = rank_mesh[rank]["face_map"]
        if np.any(local_lamella_faces >= len(rank_face_map)):
            raise ValueError(f"rank {rank} lamellae face-zone labels are out of range")
        excluded_zone_ids.update(
            abs(int(rank_face_map[int(local_face)])) - 1 for local_face in local_lamella_faces
        )
    excluded_internal = set(internal_records).intersection(excluded_zone_ids)
    interface: list[dict[str, Any]] = []
    processor_candidates: dict[int, list[dict[str, Any]]] = {}
    processor_cross_candidates = 0
    excluded_processor_cross = 0
    max_pair_absolute = 0.0
    max_pair_relative = 0.0
    for gid, pair in processor_face_records.items():
        if len(pair) != 2:
            raise ValueError(f"processor face {gid} has {len(pair)} copies, expected exactly two")
        if pair[0]["face_map_sign"] != -pair[1]["face_map_sign"]:
            raise ValueError(f"processor face {gid} signed faceProcAddressing values do not mirror")
        if external[pair[0]["owner_global"]] == external[pair[1]["owner_global"]]:
            continue
        processor_cross_candidates += 1
        if gid in excluded_zone_ids:
            excluded_processor_cross += 1
            continue
        processor_candidates[gid] = pair
    if set(internal_records).intersection(processor_face_records):
        raise ValueError(
            "a global face is represented as both local internal and processor boundary"
        )

    time_field = time_dir / "alphaPhi0.water"
    field_chunks = _field_chunks(time_field, nprocs)
    alpha_internal: list[np.ndarray] = []
    alpha_processor_patches: list[dict[str, np.ndarray]] = []
    for rank in range(nprocs):
        chunk = field_chunks[rank]
        internal = _parse_internal(chunk, "scalar")
        if len(internal) != len(rank_mesh[rank]["neighbour"]):
            raise ValueError(f"rank {rank} alphaPhi0.water internal count differs from mesh")
        alpha_internal.append(internal)
        needed_patches = {
            item["patch"]
            for pair in processor_candidates.values()
            for item in pair
            if item["rank"] == rank
        }
        patch_values: dict[str, np.ndarray] = {}
        patch_lookup = {item[0]: item for item in rank_mesh[rank]["boundary"]}
        for patch in needed_patches:
            patch_values[patch] = _parse_patch_scalar_values(chunk, patch, patch_lookup[patch][2])
        alpha_processor_patches.append(patch_values)

    for gid, record in internal_records.items():
        if gid in excluded_zone_ids:
            continue
        q_local = float(alpha_internal[record["rank"]][record["local_face"]])
        q_global = q_local * record["face_map_sign"]
        q_out = q_global if record["global_owner_is_apparatus"] else -q_global
        record["water_volume_flux_m3_s"] = float(q_out)
        interface.append(record)

    pair_errors: list[dict[str, float]] = []
    for gid, pair in processor_candidates.items():
        owner_app = [not bool(external[item["owner_global"]]) for item in pair]
        if owner_app.count(True) != 1:
            raise ValueError(
                f"processor interface face {gid} does not bridge apparatus and external"
            )
        qvalues = [
            float(alpha_processor_patches[item["rank"]][item["patch"]][item["patch_offset"]])
            for item in pair
        ]
        q_out, pair_error = _processor_pair_outward_flux(
            first_flux_owner_outward=qvalues[0],
            first_face_map_sign=pair[0]["face_map_sign"],
            first_owner_is_apparatus=owner_app[0],
            second_flux_owner_outward=qvalues[1],
            second_face_map_sign=pair[1]["face_map_sign"],
            second_owner_is_apparatus=owner_app[1],
        )
        pair_errors.append(pair_error)
        app_side = pair[owner_app.index(True)]
        rank = app_side["rank"]
        local_face = app_side["local_face"]
        point_ids, xyz = _face_polygon(
            local_face,
            rank_mesh[rank]["offsets"],
            rank_mesh[rank]["vertices"],
            rank_mesh[rank]["points"],
            rank_mesh[rank]["point_map"],
        )
        sf_local, centroid, area, fan_area = _polygon_measure(xyz)
        global_owner_is_apparatus = (
            pair[0]["face_map_sign"] > 0
            and owner_app[0]
            or (pair[1]["face_map_sign"] > 0 and owner_app[1])
        )
        sf_global = sf_local * app_side["face_map_sign"]
        # Convert the global owner-to-neighbour vector to apparatus-outward.
        # The selected local polygon is from the apparatus-side rank.
        outward_sf = sf_local if owner_app[owner_app.index(True)] else -sf_local
        if not global_owner_is_apparatus:
            expected_outward = -sf_global
        else:
            expected_outward = sf_global
        if not np.allclose(outward_sf, expected_outward, rtol=1e-10, atol=1e-12):
            raise ValueError(
                f"processor face {gid} signed face map disagrees with apparatus orientation"
            )
        other = pair[1 - owner_app.index(True)]
        other_ids, other_xyz = _face_polygon(
            other["local_face"],
            rank_mesh[other["rank"]]["offsets"],
            rank_mesh[other["rank"]]["vertices"],
            rank_mesh[other["rank"]]["points"],
            rank_mesh[other["rank"]]["point_map"],
        )
        if set(map(int, point_ids)) != set(map(int, other_ids)) or not np.allclose(
            np.sort(xyz, axis=0), np.sort(other_xyz, axis=0), rtol=0.0, atol=2e-12
        ):
            raise ValueError(f"processor face {gid} duplicated geometry does not match")
        interface.append(
            {
                "global_face_id": gid,
                "point_ids": point_ids,
                "vertices_xyz_m": xyz,
                "centroid_xyz_m": centroid,
                "area_m2": area,
                "first_vertex_fan_area_m2": fan_area,
                "outward_area_vector_xyz_m2": outward_sf,
                "edges": _polygon_edges(point_ids),
                "water_volume_flux_m3_s": q_out,
                "record_kind": "paired_processor_face_once",
            }
        )
        max_pair_absolute = max(max_pair_absolute, pair_error["absolute_error_m3_s"])
        max_pair_relative = max(max_pair_relative, pair_error["relative_error"])

    wall_patches = {
        patch_name
        for patch_name, _kind, _count, _start in _read_block_boundary(
            processor_mesh / "boundary", 0
        )
        if _kind == "wall"
    }
    wall_ids = set().union(*(boundary_face_ids.get(name, set()) for name in wall_patches))
    if len(interface) == 0:
        raise ValueError(
            "no apparatus/external interface faces remain after wall/lamella filtering"
        )

    control_surface = _validate_control_surface(
        interface,
        boundary_edges_by_patch=boundary_edges,
        wall_face_ids=wall_ids,
        interior_edges_by_patch=interior_edges,
        boundary_loops_by_patch=(
            {"ambientAnnulus": ambient_patch["loops"]} if ambient_patch is not None else {}
        ),
    )
    summaries = _summarize_components(
        interface,
        boundary_edges_by_patch=boundary_edges,
        physical_geometry_reference=physical_geometry_reference,
    )
    plane_cut_comparison = _compare_with_existing_xplane_cut(case, time_name, nprocs, summaries)
    hashes = {
        "processor_cellProcAddressing": sha256(processor_mesh / "cellProcAddressing"),
        "processor_faceProcAddressing": sha256(processor_mesh / "faceProcAddressing"),
        "processor_pointProcAddressing": sha256(processor_mesh / "pointProcAddressing"),
        "processor_cellZones": sha256(processor_mesh / "cellZones"),
        "processor_faces": sha256(processor_mesh / "faces"),
        "processor_points": sha256(processor_mesh / "points"),
        "processor_owner": sha256(processor_mesh / "owner"),
        "processor_neighbour": sha256(processor_mesh / "neighbour"),
        "processor_boundary": sha256(processor_mesh / "boundary"),
        "processor_faceZones": sha256(face_zone_path),
        "alphaPhi0.water": sha256(time_field),
        "uniform_time": sha256(time_dir / "uniform/time"),
    }
    for mouth, reference in physical_geometry_reference.get("mouths", {}).items():
        hashes[f"stl_{mouth}"] = reference["sha256"]
    for key, path_name in (
        ("stl_ambientAnnulus", "ambient_annulus_boundary_plane"),
        ("stl_apparatusWall", "apparatus_wall_extent"),
    ):
        reference = physical_geometry_reference.get(path_name)
        if reference is not None:
            hashes[key] = reference["sha256"]
    topology = {
        "selection": "unique offset FV internal faces whose adjacent global cells differ in externalAirZone membership",
        "surface_interpretation": "apparatus/external finite-volume control surface; not assumed to coincide with branch STL end-cap aperture",
        "apparatus_side": "cell not in externalAirZone",
        "external_side": "cell in externalAirZone",
        "candidate_faces_before_lamella_exclusion": len(internal_records)
        + processor_cross_candidates,
        "excluded_lamella_face_intersections": len(excluded_internal) + excluded_processor_cross,
        "selected_unique_internal_faces": len(interface),
        "selected_local_internal_face_count": len(internal_records) - len(excluded_internal),
        "selected_paired_processor_face_count": len(processor_candidates),
        "component_count": len(summaries),
        "global_cell_count": len(external),
        "external_air_zone_cell_count": int(external.sum()),
        "apparatus_side_cell_count": int((~external).sum()),
        "global_point_count_seen": len(point_seen),
        "processor_pair_max_absolute_flux_error_m3_s": max_pair_absolute,
        "processor_pair_max_relative_flux_error": max_pair_relative,
        "physical_wall_patches": sorted(wall_patches),
        "selected_wall_face_intersections": control_surface["selected_wall_face_intersections"],
        "control_surface_validation": control_surface,
        "physical_patch_edge_topology": {
            patch_name: {
                "unique_face_count": data["unique_face_count"],
                "unique_edge_count": data["unique_edge_count"],
                "true_boundary_edge_count": data["boundary_edge_count"],
                "interior_edge_count": data["interior_edge_count"],
            }
            for patch_name, data in sorted(patch_topology_internal.items())
        },
        "ambient_annulus_boundary_geometry": ambient_geometry_check,
        "interface_perimeter_edges_covered_by_true_boundary_edges_of_physical_patch": control_surface[
            "all_perimeter_edges_covered_by_true_physical_patch_boundary"
        ],
        "mouth_surface_is_open_at_boundary": True,
        "mouth_surface_closure_note": "Each selected internal FV control surface has a perimeter. The topology reports whether those edges lie on incidence-one physical-patch boundaries, inside a physical-patch triangulation, or elsewhere. AmbientAnnulus outlet-hole loops and STL cap outlines are checked separately. The control surface is not reported as a mathematically closed standalone surface or as the branch STL outlet aperture.",
        "patch_perimeter_coverage": {
            summary.mouth: summary.perimeter_edge_patch_coverage for summary in summaries
        },
    }
    return NativeControlSurfaceFluxSnapshot(
        case_path=case,
        time_name=time_name,
        time_value_s=time_value,
        nprocs=nprocs,
        summaries=summaries,
        topology=topology,
        physical_geometry_reference=physical_geometry_reference,
        plane_cut_comparison=plane_cut_comparison,
        input_hashes=hashes,
    )


def snapshot_to_dict(snapshot: NativeControlSurfaceFluxSnapshot) -> dict[str, Any]:
    return {
        "schema": "i4f-native-apparatus-control-surface-flux/v3",
        "case": str(snapshot.case_path),
        "selected_time_directory": snapshot.time_name,
        "time_s": snapshot.time_value_s,
        "processor_count": snapshot.nprocs,
        "quantity": {
            "field": "alphaPhi0.water",
            "units": "m3/s",
            "sign": "positive from apparatus cell zone into externalAirZone",
            "phase_mass_conversion": "not provided; phase density is not saved directly on selected faces",
            "mass_storage_note": "instantaneous inter-zone throughput is not stored or escaped mass",
            "surface_scope": "offset apparatus/external finite-volume control surface; does not by itself represent physical branch-cap discharge",
            "face_area_definition": "per-face magnitude of OpenFOAM-compatible face::areaNormal; absolute first-vertex fan area is a separate diagnostic",
            "projected_offset_integral_note": "sum((OpenFOAM face-centre x - reference-plane x) * outward Sf_x); diagnostic only and not claimed as enclosed buffer volume when surface projections differ",
        },
        "topology": snapshot.topology,
        "physical_geometry_reference": snapshot.physical_geometry_reference,
        "existing_xplane_cut_comparison": snapshot.plane_cut_comparison,
        "control_surface_fluxes": [summary.__dict__ for summary in snapshot.summaries],
        "input_sha256": snapshot.input_hashes,
    }
