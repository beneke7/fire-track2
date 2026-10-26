"""Small ASCII polyMesh audit for the nozzle patch and refinement log."""

from __future__ import annotations

import json
import math
import mmap
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np

FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def list_section(path: Path) -> tuple[str, int, int]:
    text = path.read_text(encoding="ascii")
    match = re.search(r"(?m)^(\d+)\s*\n\s*\(", text)
    if not match:
        raise ValueError(f"ASCII OpenFOAM list not found in {path}")
    return text, int(match.group(1)), match.end()


def list_header(path: Path) -> tuple[int, int]:
    """Read an ASCII OpenFOAM list count and return its body byte offset."""
    with path.open(encoding="ascii") as stream:
        while line := stream.readline():
            match = re.fullmatch(r"\s*(\d+)\s*\n?", line)
            if not match:
                continue
            body_offset = stream.tell()
            opening = stream.readline()
            if opening.strip() == "(":
                return int(match.group(1)), stream.tell()
            stream.seek(body_offset)
    raise ValueError(f"ASCII OpenFOAM list not found in {path}")


def iter_ascii_faces(path: Path) -> Iterator[list[int]]:
    """Stream OpenFOAM ASCII face records, including records split across lines."""
    face_count, start = list_header(path)
    token_re = re.compile(r"\d+|[()]")
    with path.open(encoding="ascii") as stream:
        stream.seek(start)
        tokens = (token for line in stream for token in token_re.findall(line))
        for face_id in range(face_count):
            try:
                declared = int(next(tokens))
                opening = next(tokens)
                ids = [int(next(tokens)) for _ in range(declared)]
                closing = next(tokens)
            except (StopIteration, ValueError) as error:
                raise ValueError(f"incomplete face record {face_id} in {path}") from error
            if declared < 3 or opening != "(" or closing != ")":
                raise ValueError(f"invalid face record {face_id} in {path}")
            yield ids


def boundary_ranges(path: Path) -> dict[str, tuple[int, int]]:
    text, _count, start = list_section(path)
    ranges = {}
    pattern = re.compile(r"(?m)^\s*([A-Za-z0-9_.-]+)\s*\{([^{}]*)\}")
    for match in pattern.finditer(text, start):
        body = match.group(2)
        n = re.search(r"\bnFaces\s+(\d+)\s*;", body)
        first = re.search(r"\bstartFace\s+(\d+)\s*;", body)
        if n and first:
            ranges[match.group(1)] = (int(first.group(1)), int(n.group(1)))
    return ranges


def _binary_list_header(path: Path) -> tuple[int, int]:
    """Return a binary OpenFOAM list count and its first payload byte offset."""
    with path.open("rb") as stream:
        head = stream.read(8192)
    header_end = head.find(b"\n}\n")
    if header_end < 0:
        raise ValueError(f"OpenFOAM file header not found in {path}")
    match = re.search(rb"(?m)^(\d+)\n\(", head[header_end + 3 :])
    if not match:
        raise ValueError(f"binary OpenFOAM list not found in {path}")
    return int(match.group(1)), header_end + 3 + match.end()


def binary_patch_area_normal(
    mesh_dir: Path,
    patch: str,
    *,
    endian: str = "<",
    label_bytes: int = 4,
    scalar_bytes: int = 8,
) -> dict[str, object]:
    """Audit a patch from binary Foundation polyMesh lists without loading full lists.

    This reader targets standard binary `vectorField`, `faceCompactList`, and
    32-bit `labelList` data. The endian and scalar width are explicit because
    Foundation 13 did not include an `arch` line in these file headers.
    """
    if endian not in {"<", ">"} or label_bytes not in {4, 8} or scalar_bytes not in {4, 8}:
        raise ValueError("unsupported binary OpenFOAM ABI")
    ranges = boundary_ranges(mesh_dir / "boundary")
    if patch not in ranges:
        raise KeyError(f"patch is absent: {patch}")
    first_face, face_count = ranges[patch]
    if face_count <= 0:
        raise ValueError(f"patch has no faces: {patch}")

    points_path = mesh_dir / "points"
    point_count, point_start = _binary_list_header(points_path)
    faces_path = mesh_dir / "faces"
    offset_count, offset_start = _binary_list_header(faces_path)
    if offset_count < 2 or first_face + face_count >= offset_count:
        raise ValueError(f"patch face range is outside binary face offsets: {patch}")
    label_dtype = np.dtype(f"{endian}i{label_bytes}")
    scalar_dtype = np.dtype(f"{endian}f{scalar_bytes}")

    with points_path.open("rb") as point_stream, faces_path.open("rb") as face_stream:
        point_map = mmap.mmap(point_stream.fileno(), 0, access=mmap.ACCESS_READ)
        face_map = mmap.mmap(face_stream.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            point_end = point_start + point_count * 3 * scalar_bytes
            if point_end > len(point_map):
                raise ValueError("binary points payload is truncated")
            points = np.frombuffer(
                point_map, dtype=scalar_dtype, count=point_count * 3, offset=point_start
            ).reshape(point_count, 3)

            offset_end = offset_start + offset_count * label_bytes
            if offset_end + 2 > len(face_map) or face_map[offset_end : offset_end + 2] != b")\n":
                raise ValueError("binary face offset list is malformed or truncated")
            elem_match = re.match(rb"(\d+)\n\(", face_map[offset_end + 2 : offset_end + 64])
            if not elem_match:
                raise ValueError("binary compact-face element list is missing")
            element_count = int(elem_match.group(1))
            element_start = offset_end + 2 + elem_match.end()
            element_end = element_start + element_count * label_bytes
            if element_end > len(face_map):
                raise ValueError("binary compact-face element payload is truncated")

            offsets = np.frombuffer(
                face_map, dtype=label_dtype, count=offset_count, offset=offset_start
            )
            face_offsets = offsets[first_face : first_face + face_count + 1].copy()
            if (
                face_offsets.size != face_count + 1
                or int(face_offsets[0]) < 0
                or np.any(face_offsets[1:] < face_offsets[:-1])
                or int(face_offsets[-1]) > element_count
            ):
                raise ValueError("binary face offsets are invalid for the requested patch")
            elements = np.frombuffer(
                face_map, dtype=label_dtype, count=element_count, offset=element_start
            )
            selected_ids = elements[int(face_offsets[0]) : int(face_offsets[-1])].copy()
            if selected_ids.size < face_count * 3:
                raise ValueError("binary patch contains fewer than three vertices per face")

            area_vector = np.zeros(3, dtype=np.float64)
            total_area = 0.0
            min_area = math.inf
            max_area = 0.0
            for face_index in range(face_count):
                begin = int(face_offsets[face_index]) - int(face_offsets[0])
                end = int(face_offsets[face_index + 1]) - int(face_offsets[0])
                ids = selected_ids[begin:end]
                if ids.size < 3 or int(ids.min()) < 0 or int(ids.max()) >= point_count:
                    raise ValueError(f"invalid binary face record at patch index {face_index}")
                polygon = points[ids]
                vector = np.zeros(3)
                for i in range(ids.size):
                    vector += np.cross(polygon[i], polygon[(i + 1) % ids.size])
                vector *= 0.5
                area = float(np.linalg.norm(vector))
                if not math.isfinite(area) or area <= 0.0 or not np.isfinite(vector).all():
                    raise ValueError(
                        f"invalid or zero-area binary face at patch index {face_index}"
                    )
                total_area += area
                area_vector += vector
                min_area = min(min_area, area)
                max_area = max(max_area, area)

            vector_magnitude = float(np.linalg.norm(area_vector))
            if not math.isfinite(vector_magnitude) or vector_magnitude <= 0.0:
                raise ValueError(f"binary patch has an invalid or cancelled area normal: {patch}")
            result = {
                "patch": patch,
                "faces": face_count,
                "area_m2": total_area,
                "area_vector_m2": [float(v) for v in area_vector],
                "area_vector_magnitude_m2": vector_magnitude,
                "normal": [float(v) for v in area_vector / vector_magnitude],
                "min_face_area_m2": min_area,
                "max_face_area_m2": max_area,
                "point_count": point_count,
                "binary_abi": {
                    "endian": "little" if endian == "<" else "big",
                    "label_bits": label_bytes * 8,
                    "scalar_bits": scalar_bytes * 8,
                },
            }
            del points, offsets, elements, selected_ids, face_offsets
        finally:
            face_map.close()
            point_map.close()
    return result


def patch_face_geometry(
    mesh_dir: Path, patch: str
) -> tuple[list[float], list[tuple[tuple[float, ...], ...]]]:
    """Return patch-order polygon areas and orientation-independent coordinate keys."""
    ranges = boundary_ranges(mesh_dir / "boundary")
    if patch not in ranges:
        raise KeyError(f"patch is absent: {patch}")
    first_face, face_count = ranges[patch]
    if face_count <= 0:
        raise ValueError(f"patch has no faces: {patch}")
    points = point_coordinates(mesh_dir / "points")
    total_faces, _start = list_header(mesh_dir / "faces")
    if first_face + face_count > total_faces:
        raise ValueError(f"patch face range is outside the faces list: {patch}")
    areas: list[float] = []
    keys: list[tuple[tuple[float, ...], ...]] = []
    for face_id, ids in enumerate(iter_ascii_faces(mesh_dir / "faces")):
        if face_id < first_face:
            continue
        if face_id >= first_face + face_count:
            break
        vertex_ids = np.asarray(ids, dtype=np.int64)
        if vertex_ids.min() < 0 or vertex_ids.max() >= points.shape[0]:
            raise ValueError(f"point index outside points list for face {face_id}")
        polygon = points[vertex_ids]
        origin = polygon[0]
        area_vector = np.zeros(3)
        for i in range(1, len(ids) - 1):
            area_vector += np.cross(polygon[i] - origin, polygon[i + 1] - origin)
        area_vector *= 0.5
        area = float(np.linalg.norm(area_vector))
        if not math.isfinite(area) or area <= 0.0:
            raise ValueError(f"invalid or zero-area face {face_id}")
        areas.append(area)
        keys.append(tuple(sorted(tuple(float(value) for value in point) for point in polygon)))
    if len(areas) != face_count:
        raise ValueError(f"patch face count mismatch: expected {face_count}, got {len(areas)}")
    return areas, keys


def face_set_labels(path: Path) -> np.ndarray:
    count, start = list_header(path)
    with path.open(encoding="ascii") as stream:
        stream.seek(start)
        body = stream.read()
    body = body.split(")", 1)[0]
    labels = np.fromstring(body, sep=" ", dtype=np.int64)
    if labels.size != count or np.unique(labels).size != count:
        raise ValueError(f"faceSet count/uniqueness mismatch in {path}")
    return labels


def wall_layer_coverage(
    prelayer_mesh: Path, postlayer_mesh: Path, selection_dir: Path, patch: str = "aircraftWall"
) -> dict[str, object]:
    """Area-weight cut selections on stable wall-face geometry across four passes."""
    areas, source_keys = patch_face_geometry(prelayer_mesh, patch)
    final_areas, final_keys = patch_face_geometry(postlayer_mesh, patch)
    if len(final_areas) != len(areas) or final_keys != source_keys:
        raise ValueError("wall patch face count/order/geometry changed across layer cuts")
    total_area = float(sum(areas))
    if not math.isfinite(total_area) or total_area <= 0.0:
        raise ValueError("wall patch has invalid total area")

    cut_counts = np.zeros(len(areas), dtype=np.int8)
    pass_rows = []
    for pass_index in range(1, 5):
        labels_path = selection_dir / f"pass-{pass_index}-hexWallFaces"
        start_path = selection_dir / f"pass-{pass_index}-startFace"
        if not labels_path.is_file() or not start_path.is_file():
            raise ValueError(f"selection snapshot missing for pass {pass_index}")
        start_face = int(start_path.read_text(encoding="ascii").strip())
        local_ids = face_set_labels(labels_path) - start_face
        if local_ids.size and (local_ids.min() < 0 or local_ids.max() >= len(areas)):
            raise ValueError(f"selected face outside {patch} range in pass {pass_index}")
        selected = np.zeros(len(areas), dtype=bool)
        selected[local_ids] = True
        cut_counts += selected
        selected_area = float(np.asarray(areas)[selected].sum())
        pass_rows.append(
            {
                "pass": pass_index,
                "selected_wall_faces": int(selected.sum()),
                "selected_area_m2": selected_area,
                "selected_area_fraction": selected_area / total_area,
                "source_start_face": start_face,
            }
        )

    area_by_cuts = {
        str(cuts): float(np.asarray(areas)[cut_counts == cuts].sum()) for cuts in range(5)
    }
    area_fraction_by_layer_bands = {
        str(int(cuts) + 1): area / total_area for cuts, area in area_by_cuts.items()
    }
    return {
        "patch": patch,
        "total_wall_faces": len(areas),
        "total_wall_area_m2": total_area,
        "pass_selections": pass_rows,
        "area_m2_by_completed_cuts": area_by_cuts,
        "area_fraction_by_achieved_bands": area_fraction_by_layer_bands,
        "area_fraction_with_five_bands": area_fraction_by_layer_bands["5"],
        "assumption": "Wall boundary polygon coordinates and patch-local ordering must remain unchanged; exact order and coordinates were compared before and after cuts.",
    }


def point_coordinates(path: Path) -> np.ndarray:
    text, point_count, start = list_section(path)
    numbers = np.fromiter((float(m.group()) for m in re.finditer(FLOAT, text[start:])), dtype=float)
    if numbers.size != point_count * 3 or not np.isfinite(numbers).all():
        raise ValueError(f"point count mismatch or nonfinite coordinate data in {path}")
    return numbers.reshape(point_count, 3)


def point_prefix_preservation(before_path: Path, after_path: Path) -> dict[str, object]:
    before = point_coordinates(before_path)
    after = point_coordinates(after_path)
    if after.shape[0] < before.shape[0] or not np.array_equal(after[: before.shape[0]], before):
        raise ValueError("original point coordinates changed or labels were reordered")
    return {
        "original_points": int(before.shape[0]),
        "final_points": int(after.shape[0]),
        "unchanged_prefix": True,
    }


def patch_area_normal(mesh_dir: Path, patch: str) -> dict[str, object]:
    ranges = boundary_ranges(mesh_dir / "boundary")
    if patch not in ranges:
        raise KeyError(f"patch is absent: {patch}")
    first_face, face_count = ranges[patch]
    if face_count <= 0:
        raise ValueError(f"patch has no faces: {patch}")

    text, point_count, start = list_section(mesh_dir / "points")
    point_body = text[start:]
    numbers = np.fromiter((float(m.group()) for m in re.finditer(FLOAT, point_body)), dtype=float)
    if numbers.size != point_count * 3:
        raise ValueError(f"point count mismatch: expected {point_count}, got {numbers.size // 3}")
    points = numbers.reshape(point_count, 3)

    selected: list[list[int]] = []
    for index, ids in enumerate(iter_ascii_faces(mesh_dir / "faces")):
        if index < first_face:
            continue
        selected.append(ids)
        if len(selected) == face_count:
            break
    if len(selected) != face_count:
        raise ValueError(
            f"face count mismatch for {patch}: expected {face_count}, got {len(selected)}"
        )

    total_area = 0.0
    area_vector = np.zeros(3)
    min_area = math.inf
    max_area = 0.0
    for ids in selected:
        polygon = points[ids]
        vector = (
            sum(
                (np.cross(polygon[i], polygon[(i + 1) % len(ids)]) for i in range(len(ids))),
                np.zeros(3),
            )
            / 2
        )
        area = float(np.linalg.norm(vector))
        if not math.isfinite(area) or area <= 0.0 or not np.all(np.isfinite(vector)):
            raise ValueError(f"patch contains invalid or zero-area face: {patch}")
        total_area += area
        area_vector += vector
        min_area = min(min_area, area)
        max_area = max(max_area, area)
    vector_magnitude = float(np.linalg.norm(area_vector))
    if (
        not np.isfinite(area_vector).all()
        or not math.isfinite(vector_magnitude)
        or vector_magnitude <= 0.0
    ):
        raise ValueError(f"patch has an invalid or cancelled area normal: {patch}")
    normal = area_vector / vector_magnitude
    return {
        "faces": face_count,
        "area_m2": total_area,
        "area_vector_m2": [float(v) for v in area_vector],
        "area_vector_magnitude_m2": vector_magnitude,
        "normal": [float(v) for v in normal],
        "min_face_area_m2": min_area,
        "max_face_area_m2": max_area,
    }


def nozzle_owner_spacing(mesh_dir: Path, patch: str = "nozzle") -> dict[str, object]:
    """Measure V/A for cells owning faces on a boundary patch.

    Cell volumes are reconstructed from oriented face triangles about each
    selected cell's vertex centroid.  The ratio is a geometric normal-scale
    estimate for boundary-adjacent cells, not a solver time-step limit.
    """
    ranges = boundary_ranges(mesh_dir / "boundary")
    if patch not in ranges:
        raise KeyError(f"patch is absent: {patch}")
    first_face, face_count = ranges[patch]
    if face_count <= 0:
        raise ValueError(f"patch has no faces: {patch}")

    owner_text, owner_count, owner_start = list_section(mesh_dir / "owner")
    owner = np.fromstring(owner_text[owner_start:], sep=" ", dtype=np.int64, count=owner_count)
    if owner.size != owner_count:
        raise ValueError(f"owner count mismatch in {mesh_dir / 'owner'}")
    neighbour_text, neighbour_count, neighbour_start = list_section(mesh_dir / "neighbour")
    neighbour = np.fromstring(
        neighbour_text[neighbour_start:], sep=" ", dtype=np.int64, count=neighbour_count
    )
    if neighbour.size != neighbour_count or neighbour_count > owner_count:
        raise ValueError(f"neighbour count mismatch in {mesh_dir / 'neighbour'}")
    if first_face + face_count > owner_count or first_face < neighbour_count:
        raise ValueError(f"invalid boundary range for patch {patch}")

    nozzle_owners = owner[first_face : first_face + face_count]
    selected_cells = np.unique(nozzle_owners)
    selected = set(int(cell) for cell in selected_cells)
    owner_face_mask = np.isin(owner, selected_cells)
    neighbour_face_mask = np.isin(neighbour, selected_cells)
    incident_face_ids = np.union1d(
        np.flatnonzero(owner_face_mask), np.flatnonzero(neighbour_face_mask)
    )
    incident = set(int(face_id) for face_id in incident_face_ids)

    points = point_coordinates(mesh_dir / "points")
    cell_faces: dict[int, list[tuple[int, int]]] = {cell: [] for cell in selected}
    cell_vertices: dict[int, set[int]] = {cell: set() for cell in selected}
    nozzle_area_by_cell = {cell: 0.0 for cell in selected}
    patch_area_vector = np.zeros(3)
    patch_area = 0.0
    face_vertices: dict[int, np.ndarray] = {}
    face_count_total, _face_start = list_header(mesh_dir / "faces")
    if face_count_total != owner_count:
        raise ValueError("faces and owner list lengths differ")
    wanted_end = int(incident_face_ids[-1]) if incident_face_ids.size else -1
    for face_id, face_ids in enumerate(iter_ascii_faces(mesh_dir / "faces")):
        if face_id > wanted_end:
            break
        if face_id not in incident:
            continue
        vertex_ids = np.asarray(face_ids, dtype=np.int64)
        declared = len(face_ids)
        if declared <= 0 or vertex_ids.size != declared:
            raise ValueError(f"invalid vertex count for face {face_id}")
        if vertex_ids.min() < 0 or vertex_ids.max() >= points.shape[0]:
            raise ValueError(f"point index outside points list for face {face_id}")
        face_vertices[face_id] = vertex_ids
        face_points = points[vertex_ids]
        origin = face_points[0]
        area_vector = np.zeros(3)
        for i in range(1, declared - 1):
            area_vector += np.cross(face_points[i] - origin, face_points[i + 1] - origin)
        area_vector *= 0.5
        area = float(np.linalg.norm(area_vector))
        if not math.isfinite(area) or area <= 0.0:
            raise ValueError(f"invalid or zero-area face {face_id}")
        owner_cell = int(owner[face_id])
        if owner_cell in selected:
            cell_faces[owner_cell].append((face_id, 1))
            cell_vertices[owner_cell].update(int(v) for v in vertex_ids)
        if face_id < neighbour_count:
            neighbour_cell = int(neighbour[face_id])
            if neighbour_cell in selected:
                cell_faces[neighbour_cell].append((face_id, -1))
                cell_vertices[neighbour_cell].update(int(v) for v in vertex_ids)
        if first_face <= face_id < first_face + face_count:
            if owner_cell not in selected:
                raise ValueError(f"nozzle owner missing from selected cells at face {face_id}")
            nozzle_area_by_cell[owner_cell] += area
            patch_area += area
            patch_area_vector += area_vector

    if len(face_vertices) != incident_face_ids.size:
        raise ValueError("not all faces incident to nozzle-owner cells were parsed")
    normal_magnitude = float(np.linalg.norm(patch_area_vector))
    if not np.isfinite(patch_area_vector).all() or normal_magnitude <= 0.0:
        raise ValueError("patch has invalid or cancelled area normal")
    normal = patch_area_vector / normal_magnitude

    cell_volumes = []
    thicknesses = []
    owner_face_counts = []
    for cell in sorted(selected):
        vertex_ids = np.fromiter(cell_vertices[cell], dtype=np.int64)
        if vertex_ids.size < 4:
            raise ValueError(f"nozzle-owner cell {cell} has fewer than four vertices")
        reference = points[vertex_ids].mean(axis=0)
        signed_volume = 0.0
        for face_id, orientation in cell_faces[cell]:
            face_points = points[face_vertices[face_id]]
            p0 = face_points[0]
            for i in range(1, face_points.shape[0] - 1):
                signed_volume += (
                    orientation
                    * float(
                        np.dot(
                            p0 - reference,
                            np.cross(face_points[i] - reference, face_points[i + 1] - reference),
                        )
                    )
                    / 6.0
                )
        volume = abs(signed_volume)
        area = nozzle_area_by_cell[cell]
        if not math.isfinite(volume) or volume <= 0.0 or area <= 0.0:
            raise ValueError(f"invalid cell volume or nozzle patch area for cell {cell}")
        cell_volumes.append(volume)
        thicknesses.append(volume / area)
        owner_face_counts.append(sum(owner == cell for owner in nozzle_owners))

    def summary(values: list[float]) -> dict[str, float]:
        array = np.asarray(values, dtype=float)
        return {
            "min": float(array.min()),
            "p05": float(np.quantile(array, 0.05)),
            "median": float(np.quantile(array, 0.5)),
            "p95": float(np.quantile(array, 0.95)),
            "max": float(array.max()),
        }

    return {
        "patch": patch,
        "patch_faces": face_count,
        "unique_owner_cells": int(selected_cells.size),
        "patch_area_m2": patch_area,
        "normal": [float(value) for value in normal],
        "owner_faces_per_cell": {
            "min": int(min(owner_face_counts)),
            "max": int(max(owner_face_counts)),
        },
        "owner_cell_volume_m3": summary(cell_volumes),
        "nozzle_area_per_owner_cell_m2": summary(
            [nozzle_area_by_cell[cell] for cell in sorted(selected)]
        ),
        "volume_over_nozzle_area_m": summary(thicknesses),
    }


def refinement_counts(log: str) -> dict[int, int]:
    matches = re.findall(r"Cells per refinement level:\s*((?:\n\s*\d+\s+\d+)+)", log)
    if not matches:
        return {}
    return {
        int(level): int(cells) for level, cells in re.findall(r"(?m)^\s*(\d+)\s+(\d+)", matches[-1])
    }


def check_mesh_summary(log: str) -> dict[str, object]:
    """Extract native checkMesh evidence without treating exit status as a pass."""
    cells = re.findall(r"(?m)^\s*cells:\s*(\d+)\s*$", log)
    tet_errors = re.findall(
        r"Error in face tets: (\d+) faces with low quality or negative volume decomposition tets",
        log,
    )
    concave = re.findall(r"Concave cells \(using face planes\) found, number of cells: (\d+)", log)
    failed = re.findall(r"Failed (\d+) mesh checks?\.", log)
    determinants = re.findall(r"Cell determinant \(wellposedness\) : minimum: ([^ ]+)", log)
    weights = re.findall(r"Face interpolation weight : minimum: ([^ ]+)", log)
    volume_ratios = re.findall(r"Face volume ratio : minimum: ([^ ]+)", log)
    return {
        "cells": int(cells[-1]) if cells else None,
        "mesh_ok_banner": "Mesh OK." in log,
        "failed_checkmesh_categories": int(failed[-1]) if failed else None,
        "low_quality_tet_faces": int(tet_errors[-1]) if tet_errors else 0,
        "concave_or_planar_cells": int(concave[-1]) if concave else 0,
        "minimum_cell_determinant": float(determinants[-1]) if determinants else None,
        "minimum_face_interpolation_weight": float(weights[-1]) if weights else None,
        "minimum_face_volume_ratio": float(volume_ratios[-1]) if volume_ratios else None,
    }


def vtk_point_bounds(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="ascii")
    match = re.search(r"(?m)^POINTS\s+(\d+)\s+\S+\s*$", text)
    if not match:
        raise ValueError(f"VTK POINTS section not found: {path}")
    count = int(match.group(1))
    end = re.search(r"(?m)^(?:POLYGONS|CELLS)\s+", text[match.end() :])
    if not end:
        raise ValueError(f"VTK cell section not found: {path}")
    body = text[match.end() : match.end() + end.start()]
    points = np.fromstring(body, sep=" ", dtype=float)
    if count <= 0 or points.size != count * 3 or not np.isfinite(points).all():
        raise ValueError(f"VTK point data is empty or invalid: {path}")
    points = points.reshape(count, 3)
    lower = points.min(axis=0)
    upper = points.max(axis=0)
    return {
        "points": count,
        "bounds_m": {
            axis: [float(lower[i]), float(upper[i])] for i, axis in enumerate(("x", "y", "z"))
        },
    }


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "vtk":
        print(json.dumps(vtk_point_bounds(Path(sys.argv[2])), indent=2))
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "binary-patch":
        print(json.dumps(binary_patch_area_normal(Path(sys.argv[2]), sys.argv[3]), indent=2))
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "nozzle-spacing":
        print(
            json.dumps(
                nozzle_owner_spacing(Path(sys.argv[2]) / "constant/polyMesh", sys.argv[3]), indent=2
            )
        )
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "checkmesh":
        print(
            json.dumps(check_mesh_summary(Path(sys.argv[2]).read_text(encoding="utf-8")), indent=2)
        )
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "point-prefix":
        print(json.dumps(point_prefix_preservation(Path(sys.argv[2]), Path(sys.argv[3])), indent=2))
        return 0
    if len(sys.argv) == 5 and sys.argv[1] == "wall-layer-coverage":
        print(
            json.dumps(
                wall_layer_coverage(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])),
                indent=2,
            )
        )
        return 0
    case = Path(sys.argv[1])
    print(json.dumps(patch_area_normal(case / "constant/polyMesh", "nozzle"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
