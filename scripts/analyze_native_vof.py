#!/usr/bin/env python3
"""Analyze native OpenFOAM face-connected VOF components.

This analysis uses saved internal alpha.water/U, finite-volume cell volumes,
native owner/neighbour faces and processor-face joins. It is an exploratory
geometric observer, not Calbrix et al.'s unpublished MATLAB detector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aerial_drop.structure_counts import label_liquid_structures, structure_statistics  # noqa: E402

EXPORT_FORMAT = "fire-track2-native-vof-v1"
ANALYSIS_FORMAT = "fire-track2-native-vof-analysis-v1"
WATER_DENSITY_KG_M3 = 1000.0
CALBRIX_SOURCE = {
    "title": "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers",
    "doi": "https://doi.org/10.1071/WF22147",
    "local_pdf": "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf",
}


def _read_raw(path: Path, dtype: str, count: int | None = None) -> NDArray[Any]:
    values = np.fromfile(path, dtype=np.dtype(dtype))
    if count is not None and values.size != count:
        raise ValueError(f"{path.name} has {values.size} values; expected {count}")
    return values


def _payload_from_rank_dir(rank_dir: Path) -> dict[str, Any]:
    metadata_path = rank_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("format") != EXPORT_FORMAT:
        raise ValueError(f"unsupported export format in {metadata_path}")
    if (
        metadata.get("export_integer_bytes") != 8
        or metadata.get("export_float_bytes") != 8
        or metadata.get("export_byte_order") != "little-endian"
    ):
        raise ValueError(f"unsupported binary width or byte order in {metadata_path}")
    if metadata.get("label_bytes_input") != 4 or metadata.get("scalar_bytes_input") != 8:
        raise ValueError(f"unsupported pinned OpenFOAM label/scalar widths in {metadata_path}")
    n_cells = int(metadata["local_cell_count"])
    if n_cells < 0:
        raise ValueError("local cell count must be nonnegative")
    return {
        "metadata": metadata,
        "cell_global_ids": _read_raw(rank_dir / "cell_global_ids.i64", "<i8", n_cells),
        "cell_volumes_m3": _read_raw(rank_dir / "cell_volumes_m3.f64", "<f8", n_cells),
        "alpha_water": _read_raw(rank_dir / "alpha_water.f64", "<f8", n_cells),
        "velocity_xyz_m_s": _read_raw(
            rank_dir / "velocity_xyz_m_s.f64", "<f8", 3 * n_cells
        ).reshape((n_cells, 3)),
        "cell_centres_xyz_m": _read_raw(
            rank_dir / "cell_centres_xyz_m.f64", "<f8", 3 * n_cells
        ).reshape((n_cells, 3)),
        "cell_bounds_minmax_xyz_m": _read_raw(
            rank_dir / "cell_bounds_minmax_xyz_m.f64", "<f8", 6 * n_cells
        ).reshape((n_cells, 6)),
        "internal_edges_global": _read_raw(rank_dir / "internal_edges_global.i64", "<i8").reshape(
            (-1, 2)
        ),
        "processor_edges_global": _read_raw(rank_dir / "processor_edges_global.i64", "<i8").reshape(
            (-1, 2)
        ),
        "source_owner_global": _read_raw(rank_dir / "source_owner_global.i64", "<i8"),
        "source_face_local_ids": _read_raw(rank_dir / "source_face_local_ids.i64", "<i8"),
        "source_face_centres_xyz_m": _read_raw(
            rank_dir / "source_face_centres_xyz_m.f64", "<f8"
        ).reshape((-1, 3)),
        "source_face_area_vectors_xyz_m2": _read_raw(
            rank_dir / "source_face_area_vectors_xyz_m2.f64", "<f8"
        ).reshape((-1, 3)),
    }


def assemble_rank_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge serial or decomposed native payloads by explicit global cell IDs.

    Processor-edge records are emitted on both sides of an MPI interface. They
    are sorted and deduplicated after mapping global IDs to canonical native
    indices. No VTK or guessed reconstructed-cell ordering is used.
    """
    if not payloads:
        raise ValueError("at least one rank payload is required")
    metadata = [payload["metadata"] for payload in payloads]
    rank_count_values = {int(row["rank_count"]) for row in metadata}
    if len(rank_count_values) != 1:
        raise ValueError("rank payloads disagree on rank_count")
    expected_ranks = rank_count_values.pop()
    rank_ids = sorted(int(row["rank"]) for row in metadata)
    if rank_ids != list(range(expected_ranks)) or len(payloads) != expected_ranks:
        raise ValueError("rank payloads must contain each rank exactly once")
    time_names = {row["time_name"] for row in metadata}
    time_values = {float(row["time_value_s"]) for row in metadata}
    patches = {row["source_patch"] for row in metadata}
    if len(time_names) != 1 or len(time_values) != 1 or len(patches) != 1:
        raise ValueError("rank payloads disagree on snapshot time or source patch")

    ids_list: list[NDArray[np.int64]] = []
    volume_list: list[NDArray[np.float64]] = []
    alpha_list: list[NDArray[np.float64]] = []
    velocity_list: list[NDArray[np.float64]] = []
    centres_list: list[NDArray[np.float64]] = []
    bounds_list: list[NDArray[np.float64]] = []
    edge_list: list[NDArray[np.int64]] = []
    source_list: list[NDArray[np.int64]] = []
    source_face_local_ids: list[NDArray[np.int64]] = []
    source_face_centres: list[NDArray[np.float64]] = []
    source_face_area_vectors: list[NDArray[np.float64]] = []
    source_face_ranks: list[NDArray[np.int32]] = []
    internal_face_occurrences = 0
    processor_face_occurrences = 0
    source_face_occurrences = 0
    for payload in payloads:
        row_metadata = payload["metadata"]
        ids = np.asarray(payload["cell_global_ids"], dtype=np.int64)
        volumes = np.asarray(payload["cell_volumes_m3"], dtype=np.float64)
        alpha = np.asarray(payload["alpha_water"], dtype=np.float64)
        velocity = np.asarray(payload["velocity_xyz_m_s"], dtype=np.float64)
        centres = np.asarray(
            payload.get("cell_centres_xyz_m", np.zeros((len(ids), 3))), dtype=np.float64
        )
        bounds = np.asarray(
            payload.get("cell_bounds_minmax_xyz_m", np.zeros((len(ids), 6))), dtype=np.float64
        )
        internal = np.asarray(payload["internal_edges_global"], dtype=np.int64).reshape((-1, 2))
        processor = np.asarray(payload["processor_edges_global"], dtype=np.int64).reshape((-1, 2))
        source = np.asarray(payload["source_owner_global"], dtype=np.int64)
        source_face_ids = np.asarray(
            payload.get("source_face_local_ids", np.empty(0)), dtype=np.int64
        )
        source_centres = np.asarray(
            payload.get("source_face_centres_xyz_m", np.empty((0, 3))), dtype=np.float64
        ).reshape((-1, 3))
        source_area_vectors = np.asarray(
            payload.get("source_face_area_vectors_xyz_m2", np.empty((0, 3))), dtype=np.float64
        ).reshape((-1, 3))
        if len(internal) != int(row_metadata["internal_face_count"]):
            raise ValueError("native internal edge count disagrees with rank metadata")
        if len(processor) != int(row_metadata["processor_edge_occurrences"]):
            raise ValueError("processor edge count disagrees with rank metadata")
        if len(source) != int(row_metadata["source_face_count_local"]):
            raise ValueError("source owner count disagrees with rank metadata")
        n_cells = len(ids)
        if volumes.shape != (n_cells,) or alpha.shape != (n_cells,):
            raise ValueError("per-cell scalar arrays do not match cell global IDs")
        if velocity.shape != (n_cells, 3):
            raise ValueError("velocity must have shape (local cells, 3)")
        if centres.shape != (n_cells, 3) or bounds.shape != (n_cells, 6):
            raise ValueError("native cell centres/bounds have incompatible shapes")
        if source_face_ids.shape != source.shape or source_centres.shape != (len(source), 3):
            raise ValueError("source face geometry does not match source owner IDs")
        if source_area_vectors.shape != (len(source), 3):
            raise ValueError("source area vectors do not match source owner IDs")
        if not np.all(np.isfinite(source_centres)) or not np.all(np.isfinite(source_area_vectors)):
            raise ValueError("source face geometry contains nonfinite values")
        if np.any(ids < 0) or not np.all(np.isfinite(volumes)) or np.any(volumes <= 0):
            raise ValueError("cell IDs and volumes are invalid")
        if not np.all(np.isfinite(alpha)) or np.any(alpha < -1e-12) or np.any(alpha > 1 + 1e-12):
            raise ValueError("alpha.water must be finite and in [0, 1]")
        if not np.all(np.isfinite(velocity)):
            raise ValueError("internal velocity contains nonfinite values")
        if not np.all(np.isfinite(centres)) or not np.all(np.isfinite(bounds)):
            raise ValueError("native cell geometry contains nonfinite values")
        if np.any(bounds[:, :3] > bounds[:, 3:]):
            raise ValueError("native cell bounds have inverted min/max coordinates")
        ids_list.append(ids)
        volume_list.append(volumes)
        alpha_list.append(alpha.copy())
        velocity_list.append(velocity)
        centres_list.append(centres)
        bounds_list.append(bounds)
        if internal.size:
            edge_list.append(internal)
        if processor.size:
            edge_list.append(processor)
        if source.size:
            source_list.append(source)
            source_face_local_ids.append(source_face_ids)
            source_face_centres.append(source_centres)
            source_face_area_vectors.append(source_area_vectors)
            source_face_ranks.append(
                np.full(len(source), int(payload["metadata"]["rank"]), dtype=np.int32)
            )
        internal_face_occurrences += int(payload["metadata"]["internal_face_count"])
        processor_face_occurrences += int(payload["metadata"]["processor_edge_occurrences"])
        source_face_occurrences += int(payload["metadata"]["source_face_count_local"])

    global_ids = np.concatenate(ids_list) if ids_list else np.empty(0, dtype=np.int64)
    if len(np.unique(global_ids)) != len(global_ids):
        raise ValueError("duplicate global cell IDs across rank payloads")
    sorted_ids = np.sort(global_ids)
    if len(sorted_ids) and not np.array_equal(
        sorted_ids, np.arange(len(sorted_ids), dtype=np.int64)
    ):
        raise ValueError("cellProcAddressing global IDs must cover dense [0, N) exactly")
    order = np.argsort(global_ids, kind="stable")
    volumes = np.concatenate(volume_list)[order]
    alpha = np.concatenate(alpha_list)[order]
    velocity = np.concatenate(velocity_list, axis=0)[order]
    centres = np.concatenate(centres_list, axis=0)[order]
    bounds = np.concatenate(bounds_list, axis=0)[order]

    raw_edges = np.concatenate(edge_list, axis=0) if edge_list else np.empty((0, 2), dtype=np.int64)
    if raw_edges.size:
        if np.any(raw_edges < 0) or np.any(raw_edges >= len(sorted_ids)):
            raise ValueError("native edge endpoint is outside the global cell range")
        edges = np.sort(raw_edges, axis=1)
        edges = np.unique(edges, axis=0)
        if np.any(edges[:, 0] == edges[:, 1]):
            raise ValueError("native topology contains a self-edge")
    else:
        edges = np.empty((0, 2), dtype=np.int64)

    all_processor_edges = [
        np.asarray(payload["processor_edges_global"], dtype=np.int64).reshape((-1, 2))
        for payload in payloads
    ]
    processor_edges = (
        np.concatenate(all_processor_edges, axis=0)
        if all_processor_edges
        else np.empty((0, 2), dtype=np.int64)
    )
    processor_edges_reciprocal_verified = True
    if processor_edges.size:
        if np.any(processor_edges < 0) or np.any(processor_edges >= len(sorted_ids)):
            raise ValueError("processor edge endpoint is outside the global cell range")
        if np.any(processor_edges[:, 0] == processor_edges[:, 1]):
            raise ValueError("processor topology contains a self-edge")
        directed = processor_edges[np.lexsort((processor_edges[:, 1], processor_edges[:, 0]))]
        reciprocal = processor_edges[:, ::-1]
        reciprocal = reciprocal[np.lexsort((reciprocal[:, 1], reciprocal[:, 0]))]
        if not np.array_equal(directed, reciprocal):
            raise ValueError("processor face edges are not reciprocal across rank boundaries")

    source_owners = np.concatenate(source_list) if source_list else np.empty(0, dtype=np.int64)
    if source_owners.size and (
        np.any(source_owners < 0) or np.any(source_owners >= len(sorted_ids))
    ):
        raise ValueError("source boundary owner is outside the global cell range")
    source_owners = np.unique(source_owners)
    source_face_ids_merged = (
        np.concatenate(source_face_local_ids) if source_face_local_ids else np.empty(0, np.int64)
    )
    source_centres_merged = (
        np.concatenate(source_face_centres, axis=0)
        if source_face_centres
        else np.empty((0, 3), np.float64)
    )
    source_area_vectors_merged = (
        np.concatenate(source_face_area_vectors, axis=0)
        if source_face_area_vectors
        else np.empty((0, 3), np.float64)
    )
    source_face_ranks_merged = (
        np.concatenate(source_face_ranks) if source_face_ranks else np.empty(0, np.int32)
    )
    return {
        "time_name": next(iter(time_names)),
        "time_value_s": next(iter(time_values)),
        "source_patch": next(iter(patches)),
        "cell_global_ids": sorted_ids,
        "cell_volumes_m3": volumes,
        "alpha_water": alpha,
        "velocity_xyz_m_s": velocity,
        "cell_centres_xyz_m": centres,
        "cell_bounds_minmax_xyz_m": bounds,
        "edges_native_global_ids": edges,
        "source_owner_global_ids": source_owners,
        "source_face_local_ids": source_face_ids_merged,
        "source_face_ranks": source_face_ranks_merged,
        "source_face_centres_xyz_m": source_centres_merged,
        "source_face_area_vectors_xyz_m2": source_area_vectors_merged,
        "topology": {
            "rank_count": expected_ranks,
            "native_cells": int(len(sorted_ids)),
            "internal_face_edge_occurrences": internal_face_occurrences,
            "processor_face_edge_occurrences_both_sides": processor_face_occurrences,
            "unique_face_edges": int(len(edges)),
            "source_boundary_face_count": source_face_occurrences,
            "unique_source_owner_cells": int(len(source_owners)),
            "source_face_order": "native patch order within each rank; rank and local face label included",
            "source_patch_area_m2": float(
                np.linalg.norm(source_area_vectors_merged, axis=1).sum(dtype=np.float64)
            ),
            "processor_edges_deduplicated": True,
            "processor_edges_reciprocal_verified": processor_edges_reciprocal_verified,
            "global_cell_order": "sorted original IDs from serial identity or cellProcAddressing",
        },
        "alpha_input_validation": {
            "native_minimum_raw": float(np.min(alpha)) if len(alpha) else None,
            "native_maximum_raw": float(np.max(alpha)) if len(alpha) else None,
            "values_outside_unit_interval_within_roundoff_tolerance": int(
                np.count_nonzero((alpha < 0.0) | (alpha > 1.0))
            ),
            "raw_values_clipped": False,
            "raw_alpha_mass_preserved": True,
        },
    }


def load_export(export_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    rank_dirs = sorted(export_dir.glob("rank-[0-9][0-9][0-9][0-9]"))
    if not rank_dirs:
        raise FileNotFoundError(f"no rank-0000 export directory under {export_dir}")
    payloads = [_payload_from_rank_dir(rank_dir) for rank_dir in rank_dirs]
    inputs = {
        str(path.relative_to(export_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(export_dir.rglob("*"))
        if path.is_file()
    }
    return assemble_rank_payloads(payloads), inputs


def analyze_snapshot(
    snapshot: dict[str, Any],
    *,
    thresholds: tuple[float, ...] = (0.001, 0.9),
    density_kg_m3: float = WATER_DENSITY_KG_M3,
    refinement_box_m: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    alpha = np.asarray(snapshot["alpha_water"], dtype=np.float64)
    volumes = np.asarray(snapshot["cell_volumes_m3"], dtype=np.float64)
    velocity = np.asarray(snapshot["velocity_xyz_m_s"], dtype=np.float64)
    edges = np.asarray(snapshot["edges_native_global_ids"], dtype=np.int64)
    source_owners = np.asarray(snapshot["source_owner_global_ids"], dtype=np.int64)
    cell_centres = np.asarray(snapshot["cell_centres_xyz_m"], dtype=np.float64)
    cell_bounds = np.asarray(snapshot["cell_bounds_minmax_xyz_m"], dtype=np.float64)
    total_water_mass = float(np.sum(alpha * volumes, dtype=np.float64) * density_kg_m3)
    result: dict[str, Any] = {
        "schema": ANALYSIS_FORMAT,
        "observer": "native OpenFOAM face-connected cell components",
        "unpublished_paper_detector_equivalence": False,
        "time_name": snapshot["time_name"],
        "time_value_s": snapshot["time_value_s"],
        "source_patch": snapshot["source_patch"],
        "coordinate_frame": "OpenFOAM simulation axes; velocity components are signed x/y/z",
        "density_kg_m3": density_kg_m3,
        "mass_convention": "alpha.water * native cell volume * constant 1000 kg/m3",
        "component_observer_sensitivities": {
            "diameters": {
                "equivalent_diameter_m": {
                    "status": "existing primary descriptor; unchanged",
                    "volume_m3": "sum(alpha.water * native cell volume) within component",
                },
                "selected_cell_geometric_volume_equivalent_diameter_m": {
                    "status": "additive observer sensitivity; not a paper-method claim",
                    "volume_m3": "sum(full native cell volume) for selected component cells, without alpha weighting",
                    "not_mass": True,
                    "paper_context": {
                        "source": CALBRIX_SOURCE,
                        "location": "PDF p. 10 / journal p. 1524, Fig. 11(d)",
                        "reported_bins_m": [[0.04, 0.1], [0.1, 1.0], [1.0, 10.0]],
                        "extraction": "bin edges transcribed from experiments/E2_CALBRIX_SOURCE.md; author equivalent-diameter operator remains unspecified",
                    },
                },
            },
            "component_velocity_m_s": {
                "mass_weighted_velocity_m_s": "existing primary component statistic; alpha * cell volume * constant density weights; unchanged",
                "geometric_volume_weighted_velocity_m_s": "sum(native cell volume * internal U) / sum(native cell volume) within selected component cells",
                "cell_number_mean_velocity_m_s": "arithmetic mean of internal U over selected component cells",
                "class_aggregation": "when summarized by diameter bin, report both arithmetic component mean and component-mass-weighted mean; Calbrix Fig. 11(d) does not specify its velocity averaging operator",
            },
        },
        "alpha_integrity": snapshot["alpha_input_validation"],
        "input_provenance": {
            "cloud_threshold": {
                "value": 0.001,
                "classification": "reported paper threshold",
                "source": CALBRIX_SOURCE,
                "location": "PDF p. 6 / journal p. 1520; liquid cloud-envelope definition; Fig. 11 count history on PDF p. 10 / journal p. 1524",
                "extraction": "transcribed from experiments/E2_CALBRIX_SOURCE.md; not digitized from a graph",
            },
            "core_threshold": {
                "value": 0.9,
                "classification": "reported paper threshold",
                "source": CALBRIX_SOURCE,
                "location": "PDF p. 6 / journal p. 1520; liquid-core definition; Fig. 11 count history on PDF p. 10 / journal p. 1524",
                "extraction": "transcribed from experiments/E2_CALBRIX_SOURCE.md; not digitized from a graph",
            },
            "water_density": {
                "value_kg_m3": density_kg_m3,
                "classification": "reported source value used as constant mass conversion",
                "source": CALBRIX_SOURCE,
                "location": "PDF p. 4 / journal p. 1518, Domains and meshes: rho_L=1000 kg/m3",
                "extraction": "transcribed from experiments/E2_CALBRIX_SOURCE.md",
            },
            "cell_volume": {
                "classification": "computed from native OpenFOAM polyMesh geometry",
                "method": "OpenFOAM fvMesh::V() in original native local cell order",
            },
            "velocity": {
                "classification": "computed case field",
                "method": "saved internal U field; signed OpenFOAM x/y/z components; boundary values not used",
            },
            "connectivity": {
                "classification": "analysis assumption",
                "method": "native internal face owner/neighbour plus processor-face joins; no point-touch links",
            },
            "source_attachment": {
                "classification": "analysis assumption",
                "method": "component includes at least one threshold-selected owner cell of a face on the declared source boundary patch",
            },
            "unresolved_paper_method": "Calbrix does not provide the MATLAB connectivity, singleton filtering, mass aggregation, or velocity weighting details; these results are observer sensitivities and not detector equivalence.",
        },
        "total_domain_water_mass_kg": total_water_mass,
        "thresholds": {},
        "topology": snapshot["topology"],
    }
    refinement_mask: NDArray[np.bool_] | None = None
    if refinement_box_m is not None:
        required_axes = ("x", "y", "z")
        if set(refinement_box_m) != set(required_axes):
            raise ValueError("refinement box requires exactly x, y, and z bounds")
        box_values = np.asarray([refinement_box_m[axis] for axis in required_axes], dtype=float)
        if (
            box_values.shape != (3, 2)
            or not np.all(np.isfinite(box_values))
            or np.any(box_values[:, 0] >= box_values[:, 1])
        ):
            raise ValueError("refinement box bounds must be finite increasing [min,max] pairs")
        refinement_mask = np.ones(len(alpha), dtype=bool)
        for axis in range(3):
            refinement_mask &= (cell_centres[:, axis] >= box_values[axis, 0]) & (
                cell_centres[:, axis] <= box_values[axis, 1]
            )
        result["refinement_band_diagnostic"] = {
            "bounds_m": {axis: list(refinement_box_m[axis]) for axis in required_axes},
            "cell_classification": "cell volume centroid lies within the closed box",
            "component_bounds": "axis-aligned union of native mesh-point min/max bounds of member cells",
            "outside_water_mass_classification": "alpha.water * full native cell volume for cells whose volume centroid is outside; no clipped-cell volume reconstruction",
        }
    for threshold in thresholds:
        if not math.isfinite(threshold) or not 0 < threshold <= 1:
            raise ValueError("thresholds must be finite and in (0, 1]")
        threshold_record: dict[str, Any] = {}
        for min_cells in (1, 2):
            labels = label_liquid_structures(
                alpha, edges[:, 0], edges[:, 1], threshold, min_cells=min_cells
            )
            components = structure_statistics(
                alpha, volumes, labels, velocity, density_kg_m3=density_kg_m3
            )
            for component in components:
                member_mask = labels == int(component["label"])
                member_volumes = volumes[member_mask]
                member_velocity = velocity[member_mask]
                geometric_volume = float(np.sum(member_volumes, dtype=np.float64))
                component["selected_cell_geometric_volume_m3"] = geometric_volume
                component["selected_cell_geometric_volume_equivalent_diameter_m"] = float(
                    np.cbrt(6.0 * geometric_volume / np.pi)
                )
                component["geometric_volume_weighted_velocity_m_s"] = tuple(
                    float(value)
                    for value in np.sum(
                        member_velocity * member_volumes[:, None], axis=0, dtype=np.float64
                    )
                    / geometric_volume
                )
                component["cell_number_mean_velocity_m_s"] = tuple(
                    float(value) for value in np.mean(member_velocity, axis=0, dtype=np.float64)
                )
            attached_source_labels = set(
                int(label) for label in labels[source_owners] if label >= 0
            )
            for component in components:
                component["source_attached"] = int(component["label"]) in attached_source_labels
            attached = [row for row in components if row["source_attached"]]
            detached = [row for row in components if not row["source_attached"]]
            selected_mask = alpha >= threshold
            selected_mass = float(
                np.sum(alpha[selected_mask] * volumes[selected_mask], dtype=np.float64)
                * density_kg_m3
            )
            threshold_record[f"min_cells_{min_cells}"] = {
                "selected_cell_count_before_filter": int(np.count_nonzero(selected_mask)),
                "component_count": len(components),
                "attached_component_count": len(attached),
                "detached_component_count": len(detached),
                "reported_component_mass_kg": float(
                    sum(float(row["mass_kg"]) for row in components)
                ),
                "attached_component_mass_kg": float(sum(float(row["mass_kg"]) for row in attached)),
                "detached_component_mass_kg": float(sum(float(row["mass_kg"]) for row in detached)),
                "all_threshold_selected_cell_mass_kg": selected_mass,
                "retained_component_mass_fraction_of_threshold_selected": (
                    float(sum(float(row["mass_kg"]) for row in components) / selected_mass)
                    if selected_mass > 0
                    else None
                ),
                "attached_components": attached,
                "detached_components": detached,
            }
            component_bounds_rows: list[dict[str, Any]] = []
            if len(components):
                max_label = max(int(row["label"]) for row in components)
                min_bounds = np.full((max_label + 1, 3), np.inf, dtype=np.float64)
                max_bounds = np.full((max_label + 1, 3), -np.inf, dtype=np.float64)
                labelled = labels >= 0
                component_ids = labels[labelled]
                for axis in range(3):
                    np.minimum.at(min_bounds[:, axis], component_ids, cell_bounds[labelled, axis])
                    np.maximum.at(
                        max_bounds[:, axis], component_ids, cell_bounds[labelled, axis + 3]
                    )
                for row in components:
                    label = int(row["label"])
                    component_bounds_rows.append(
                        {
                            "label": label,
                            "bounds_m": {
                                "min": min_bounds[label].tolist(),
                                "max": max_bounds[label].tolist(),
                            },
                        }
                    )
            threshold_record[f"min_cells_{min_cells}"]["component_native_bounds"] = (
                component_bounds_rows
            )
            if refinement_mask is not None:
                selected_outside = selected_mask & ~refinement_mask
                threshold_record[f"min_cells_{min_cells}"]["cells_outside_refinement_band"] = int(
                    np.count_nonzero(selected_outside)
                )
                threshold_record[f"min_cells_{min_cells}"][
                    "selected_water_mass_outside_refinement_band_kg"
                ] = float(
                    np.sum(alpha[selected_outside] * volumes[selected_outside], dtype=np.float64)
                    * density_kg_m3
                )
                threshold_record[f"min_cells_{min_cells}"][
                    "components_extending_outside_refinement_band"
                ] = sum(
                    any(
                        bounds_row["bounds_m"]["min"][axis] < box_values[axis, 0]
                        or bounds_row["bounds_m"]["max"][axis] > box_values[axis, 1]
                        for axis in range(3)
                    )
                    for bounds_row in component_bounds_rows
                )
        result["thresholds"][format(threshold, ".6g")] = threshold_record
    return result


def all_cells_graph_component_count(snapshot: dict[str, Any]) -> int:
    """Geometry-only graph audit, deliberately independent of the VOF field."""
    n_cells = len(snapshot["cell_global_ids"])
    labels = label_liquid_structures(
        np.ones(n_cells, dtype=np.float64),
        snapshot["edges_native_global_ids"][:, 0],
        snapshot["edges_native_global_ids"][:, 1],
        0.5,
    )
    return int(np.unique(labels).size) if n_cells else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="new analysis directory")
    parser.add_argument("--all-cells-graph-check", action="store_true")
    parser.add_argument(
        "--refinement-box-m",
        type=float,
        nargs=6,
        metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"),
        help="optional declared box for out-of-refinement inventory",
    )
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error(f"output directory already exists: {args.output_dir}")
    try:
        snapshot, input_hashes = load_export(args.export_dir)
        refinement_box = None
        if args.refinement_box_m is not None:
            values = args.refinement_box_m
            refinement_box = {
                "x": (values[0], values[1]),
                "y": (values[2], values[3]),
                "z": (values[4], values[5]),
            }
        report = analyze_snapshot(snapshot, refinement_box_m=refinement_box)
        if args.all_cells_graph_check:
            report["geometry_only_all_cells_graph_component_count"] = (
                all_cells_graph_component_count(snapshot)
            )
            report["geometry_only_graph_warning"] = (
                "all cells were assigned synthetic alpha=1 solely to verify mesh connectivity; "
                "this is not a liquid or breakup result"
            )
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "analysis.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (args.output_dir / "raw_export_sha256.json").write_text(
            json.dumps(input_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"native VOF analysis failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "analysis": str(args.output_dir / "analysis.json"),
                "cells": report["topology"]["native_cells"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
