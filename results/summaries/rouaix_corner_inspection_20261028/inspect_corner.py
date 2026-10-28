from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from aerial_drop.i4f_native_face_reader import (
    _face_geometry,
    _read_global_boundary,
    _read_global_faces,
    _read_global_labels,
    _read_global_points,
)


ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "results/runs/rouaix-fast-local-20261027/cases-and-runs/attempt-003/air-original-030"
MESH = CASE / "constant/polyMesh"
EVIDENCE = ROOT / "results/runs/rouaix-fast-local-20261027/cases-and-runs/attempt-003/container-runs"
TARGETS = {
    "original": {
        "xyz_m": [17.4230769231, -0.0250266998932, 3.48687825096],
        "processor": 7,
        "local_cell": 37439,
        "time_s": 0.1752,
    },
    "upwind": {
        "xyz_m": [17.4230769231, -0.0250266998932, 3.48687825096],
        "processor": 7,
        "local_cell": 37439,
        "time_s": 0.196,
    },
}
PATCH_NAMES = ("downstreamOutlet", "aircraftWall", "spanwisePlus")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cell_geometry(cell_id: int, points, offsets, labels, owner, neighbour):
    own_faces = np.flatnonzero(owner == cell_id)
    neighbour_faces = np.flatnonzero(neighbour == cell_id)
    face_ids = np.unique(np.concatenate((own_faces, neighbour_faces)))
    volume = 0.0
    first_moment = np.zeros(3)
    vertex_ids = []
    for face_id in face_ids:
        face_id = int(face_id)
        sf, cf, _ = _face_geometry(face_id, offsets, labels, points)
        sign = 1.0 if int(owner[face_id]) == cell_id else -1.0
        signed_tetra_volume = sign * float(np.dot(sf, cf)) / 3.0
        volume += signed_tetra_volume
        first_moment += signed_tetra_volume * (0.75 * cf)
        vertex_ids.extend(labels[int(offsets[face_id]) : int(offsets[face_id + 1])])
    if volume <= 0.0:
        raise ValueError(f"invalid reconstructed volume {volume} for cell {cell_id}")
    cell_points = points[np.unique(np.asarray(vertex_ids, dtype=np.int64))]
    return {
        "cell_id": cell_id,
        "center_m": (first_moment / volume).tolist(),
        "volume_m3": volume,
        "aabb_min_m": cell_points.min(axis=0).tolist(),
        "aabb_max_m": cell_points.max(axis=0).tolist(),
        "face_count": int(len(face_ids)),
        "face_ids": [int(face_id) for face_id in face_ids],
    }


def patch_fluxes(log_path: Path) -> dict[str, float]:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    result = {}
    for patch in (
        "gasInlet",
        "nozzle",
        "downstreamOutlet",
        "bottomOutlet",
        "spanwiseMinus",
        "spanwisePlus",
    ):
        matches = re.findall(
            rf"surfaceFieldValue {patch}Flux write:\s+sum\({patch}\) of phi = ([^\s]+)",
            text,
        )
        if matches:
            result[patch] = float(matches[-1])
    return result


def main() -> None:
    points = _read_global_points(MESH / "points")
    offsets, labels = _read_global_faces(MESH / "faces")
    owner = _read_global_labels(MESH / "owner")
    neighbour = _read_global_labels(MESH / "neighbour")
    patches = _read_global_boundary(MESH / "boundary")
    patch_ranges = {
        name: (start, start + count)
        for name, _kind, count, start in patches
    }
    if len(owner) != len(offsets) - 1 or len(neighbour) > len(owner):
        raise ValueError("mesh face/owner/neighbour counts do not agree")

    face_geometry = {}
    face_owners = {}
    for patch in PATCH_NAMES:
        start, end = patch_ranges[patch]
        for face_id in range(start, end):
            sf, cf, area = _face_geometry(face_id, offsets, labels, points)
            face_geometry[face_id] = (sf, cf, area)
            face_owners[face_id] = int(owner[face_id])

    target_xyz = np.asarray(TARGETS["original"]["xyz_m"], dtype=np.float64)
    candidate_cells = set()
    closest_faces = {}
    for patch in PATCH_NAMES:
        start, end = patch_ranges[patch]
        patch_faces = []
        for face_id in range(start, end):
            sf, cf, area = face_geometry[face_id]
            distance = float(np.linalg.norm(cf - target_xyz))
            patch_faces.append(
                {
                    "face_id": face_id,
                    "owner_cell": face_owners[face_id],
                    "center_m": cf.tolist(),
                    "area_m2": area,
                    "area_vector_m2": sf.tolist(),
                    "distance_from_reported_peak_m": distance,
                }
            )
            if distance < 0.4:
                candidate_cells.add(face_owners[face_id])
        closest_faces[patch] = sorted(
            patch_faces, key=lambda item: item["distance_from_reported_peak_m"]
        )[:3]

    candidates = [cell_geometry(cid, points, offsets, labels, owner, neighbour) for cid in candidate_cells]
    target_cell = min(
        candidates,
        key=lambda item: float(np.linalg.norm(np.asarray(item["center_m"]) - target_xyz)),
    )
    target_cell_distance = float(np.linalg.norm(np.asarray(target_cell["center_m"]) - target_xyz))
    target_faces = set(target_cell["face_ids"])
    adjacent_patch_faces = []
    for patch in PATCH_NAMES:
        start, end = patch_ranges[patch]
        for face_id in range(start, end):
            if face_id not in target_faces:
                continue
            sf, cf, area = face_geometry[face_id]
            adjacent_patch_faces.append(
                {
                    "patch": patch,
                    "face_id": face_id,
                    "owner_cell": int(owner[face_id]),
                    "center_m": cf.tolist(),
                    "area_m2": area,
                    "unit_normal_outward": (sf / np.linalg.norm(sf)).tolist(),
                    "distance_cell_center_to_face_center_m": float(
                        np.linalg.norm(cf - np.asarray(target_cell["center_m"]))
                    ),
                }
            )

    terminal_patch_fluxes = {
        "original": patch_fluxes(EVIDENCE / "air-original-030/evidence/interIsoFoam.log"),
        "upwind": patch_fluxes(EVIDENCE / "air-upwind-030/evidence/interIsoFoam.log"),
    }
    result = {
        "schema_version": 1,
        "purpose": "Read-only geometric mapping of the coarse all-air guard maxima to the native mesh; no CFD or mesh modification.",
        "case_root": str(CASE.relative_to(ROOT)),
        "mesh_sha256": {
            path.name: sha256(path)
            for path in (MESH / "boundary", MESH / "faces", MESH / "owner", MESH / "neighbour", MESH / "points")
        },
        "reported_hotspot": TARGETS,
        "reconstructed_nearest_native_cell": {
            **{key: value for key, value in target_cell.items() if key != "face_ids"},
            "distance_to_reported_fieldMinMax_center_m": target_cell_distance,
            "aabb_lengths_m": (
                np.asarray(target_cell["aabb_max_m"]) - np.asarray(target_cell["aabb_min_m"])
            ).tolist(),
            "approximate_aabb_aspect_ratio": float(
                max(np.asarray(target_cell["aabb_max_m"]) - np.asarray(target_cell["aabb_min_m"]))
                / min(np.asarray(target_cell["aabb_max_m"]) - np.asarray(target_cell["aabb_min_m"]))
            ),
        },
        "adjacent_open_or_wall_patch_faces": adjacent_patch_faces,
        "nearby_boundary_face_candidates_by_patch": closest_faces,
        "guard_time_integrated_patch_phi_m3_s": {
            "by_patch": terminal_patch_fluxes,
            "global_signed_sum_m3_s": {
                case: float(sum(values.values()))
                for case, values in terminal_patch_fluxes.items()
            },
            "sum_scope": "Terminal signed patch sums from solver log; global closure is subject to printed decimal rounding.",
        },
        "facewise_phi_at_hotspot": {
            "available": False,
            "reason": "The retained collated guard snapshot includes phi, but the compact archive omits processors8/constant/polyMesh and cellProcAddressing/faceProcAddressing; local processor face ordering cannot be mapped to these global boundary faces without regenerating decomposition.",
        },
        "mesh_qa": {
            "cells": 299520,
            "native_checkMesh_ok": True,
            "concave_or_planar_cells": 0,
            "low_quality_tet_faces": 0,
            "global_min_cell_determinant": 0.001307024566559602,
            "global_min_face_interpolation_weight": 0.09090909090909001,
            "global_min_face_volume_ratio": 0.09999999999999672,
            "local_checkMesh_metrics": "not stored; no cell-local skewness/non-orthogonality metric was recovered",
        },
    }
    out = Path(__file__).with_name("corner-audit.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
