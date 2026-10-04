#!/usr/bin/env python3
"""Prepare a provisional single-opening Dash-8 OpenFOAM nearfield case.

The generator reuses the CL-415 case's Cartesian mesh and OpenFOAM dictionary
helpers. The one 4.44 m by 0.30 m source is a figure-derived geometry
candidate, not a reported aperture measurement. The five-second digitized
history ends at a nonzero velocity, so each case ends at its requested horizon
without adding a shutoff or an extrapolated tail.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PRIMARY_HISTORY_CSV = ROOT / "data/derived/calbrix_dash8_fig4_velocity.csv"
INDEPENDENT_HISTORY_CSV = ROOT / "data/derived/calbrix_dash8_fig4_velocity_independent.csv"
SOURCE_RECORD = ROOT / "experiments/E2_CALBRIX_SOURCE.md"
CL415_HELPERS_PATH = ROOT / "cases/calbrix_cl415/prepare_case.py"

CASE_ID = "E2_CALBRIX_DASH8_EXPLORATORY_NEARFIELD_SINGLE_OPENING"
SOURCE_NAME = "dash8Opening"
HISTORY_NAME = "dash8"
MAX_HISTORY_HORIZON_S = 5.0
WATER_RHO_KG_M3 = 1000.0
AIR_SPEED_M_S = 50.0
GRAVITY_M_S2 = (0.0, 0.0, -9.81)
DEFAULT_SOURCE_LENGTH_M = 4.44
DEFAULT_SOURCE_WIDTH_M = 0.30
DEFAULT_DOMAIN_BOUNDS_M = {
    "x": (-3.0, 23.0),
    "y": (-10.0, 10.0),
    "z": (-31.0, 0.0),
}
DEFAULT_REFINEMENT_REGION_M = {
    "x": (-2.5, 4.0),
    "y": (-1.5, 1.5),
    "z": (-3.0, 0.0),
}
OPEN_PATCHES = ["airInlet", "xOutlet", "yMin", "yMax", "zMin"]


def _load_cl415_helpers() -> Any:
    """Load CL-415 helpers under a unique name without importing its CLI module."""
    module_name = "track2_dash8_cl415_mesh_field_dictionary_helpers"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, CL415_HELPERS_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load CL-415 helpers from {CL415_HELPERS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


CL_HELPERS = _load_cl415_helpers()


def _finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{name} must be {qualifier}")
    return number


def _normalize_bounds(
    value: dict[str, Any] | None,
    *,
    default: dict[str, tuple[float, float]],
    name: str,
) -> dict[str, tuple[float, float]]:
    if value is None:
        value = default
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        raise ValueError(f"{name} must provide exactly x, y, and z bounds")
    normalized: dict[str, tuple[float, float]] = {}
    for axis in ("x", "y", "z"):
        pair = value[axis]
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(f"{name} {axis} bounds must contain two finite numbers")
        lower = _finite_number(pair[0], f"{name} {axis} lower bound")
        upper = _finite_number(pair[1], f"{name} {axis} upper bound")
        if lower >= upper:
            raise ValueError(f"{name} {axis} lower bound must be less than upper bound")
        normalized[axis] = (lower, upper)
    return normalized


def validate_history(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Validate a digitized scalar history in seconds and metres per second."""
    if not isinstance(samples, list) or not samples:
        raise ValueError("Dash-8 source history must be a non-empty list")
    normalized: list[tuple[float, float]] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, (tuple, list)) or len(sample) != 2:
            raise ValueError("each source-history sample must be a (time, speed) pair")
        time_s = _finite_number(sample[0], f"history sample {index} time")
        speed_m_s = _finite_number(sample[1], f"history sample {index} speed")
        if time_s < 0.0 or speed_m_s < 0.0:
            raise ValueError("source-history times and speeds must be nonnegative")
        normalized.append((time_s, speed_m_s))
    if not math.isclose(normalized[0][0], 0.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("Dash-8 history must include its digitized t=0 sample")
    if not math.isclose(normalized[0][1], 0.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("Dash-8 digitized t=0 source speed must be zero")
    if any(left[0] >= right[0] for left, right in zip(normalized, normalized[1:])):
        raise ValueError("source-history times must be strictly increasing")
    return normalized


def read_primary_history(path: Path = PRIMARY_HISTORY_CSV) -> list[tuple[float, float]]:
    """Read the first Dash-8 blue-curve digitization without fitting or filtering."""
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not {"time_s", "u_l_m_s"}.issubset(reader.fieldnames):
            raise ValueError("primary Dash-8 history CSV lacks time_s or u_l_m_s")
        samples = [(float(row["time_s"]), float(row["u_l_m_s"])) for row in reader]
    return validate_history(samples)


def _interpolate_history(samples: list[tuple[float, float]], time_s: float) -> float:
    if time_s < samples[0][0] or time_s > samples[-1][0] + 1e-12:
        raise ValueError("requested time lies outside digitized source-history support")
    for (t0, v0), (t1, v1) in zip(samples, samples[1:]):
        if time_s <= t1:
            fraction = (time_s - t0) / (t1 - t0)
            return v0 + (v1 - v0) * fraction
    return samples[-1][1]


def history_to_horizon(
    samples: list[tuple[float, float]], horizon_s: float
) -> list[tuple[float, float]]:
    """Clip a piecewise-linear history to a supported horizon; never invent a tail."""
    checked = validate_history(samples)
    horizon = _finite_number(horizon_s, "horizon_s", positive=True)
    if horizon > checked[-1][0] + 1e-12:
        raise ValueError(
            f"horizon_s ({horizon:g}) exceeds digitized history support ({checked[-1][0]:g} s); "
            "do not extrapolate a tail or invent a shutoff"
        )
    bounded = [(time_s, speed) for time_s, speed in checked if time_s < horizon]
    bounded.append((horizon, _interpolate_history(checked, horizon)))
    return bounded


def integrate_history(samples: list[tuple[float, float]], horizon_s: float) -> float:
    """Integrate speed exactly for the piecewise-linear curve (distance in metres)."""
    bounded = history_to_horizon(samples, horizon_s)
    return math.fsum(
        (t1 - t0) * (v0 + v1) / 2.0 for (t0, v0), (t1, v1) in zip(bounded, bounded[1:])
    )


def integrate_squared_history(samples: list[tuple[float, float]], horizon_s: float) -> float:
    """Integrate squared speed for the uniform-source momentum impulse diagnostic."""
    bounded = history_to_horizon(samples, horizon_s)
    return math.fsum(
        (t1 - t0) * (v0 * v0 + v0 * v1 + v1 * v1) / 3.0
        for (t0, v0), (t1, v1) in zip(bounded, bounded[1:])
    )


def _make_source(
    *, length_m: float, width_m: float, plane_z_m: float, domain: dict[str, tuple[float, float]]
) -> dict[str, Any]:
    x_bounds = (-length_m / 2.0, length_m / 2.0)
    y_bounds = (-width_m / 2.0, width_m / 2.0)
    if x_bounds[0] < domain["x"][0] or x_bounds[1] > domain["x"][1]:
        raise ValueError("the single Dash-8 outlet lies outside the x domain")
    if y_bounds[0] < domain["y"][0] or y_bounds[1] > domain["y"][1]:
        raise ValueError("the single Dash-8 outlet lies outside the y domain")
    if not math.isclose(plane_z_m, domain["z"][1], rel_tol=0.0, abs_tol=1e-10):
        raise ValueError("the single opening must lie on the flat top source plane")
    return {
        "name": SOURCE_NAME,
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "length_x_m": length_m,
        "width_y_m": width_m,
        "area_m2": length_m * width_m,
        "direction_unit": [0.0, 0.0, -1.0],
        "history": HISTORY_NAME,
        "plane_z_m": plane_z_m,
        "bounds_m": {"x": list(x_bounds), "y": list(y_bounds)},
    }


def _git_provenance() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip()
        dirty_lines = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}
    return {"revision": revision, "dirty": bool(dirty_lines)}


def prepare_case(
    output: Path,
    *,
    horizon_s: float = 5.0,
    ranks: int = 20,
    snapshot_interval_s: float = 0.1,
    spacing_m: float = 0.1,
    coarse_spacing_m: float = 0.4,
    source_length_m: float = DEFAULT_SOURCE_LENGTH_M,
    source_width_m: float = DEFAULT_SOURCE_WIDTH_M,
    domain_bounds_m: dict[str, tuple[float, float]] | None = None,
    refinement_region: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Create a new case after validating source, history, domain, mesh and ranks."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"output directory already exists; preserving it: {output}")

    horizon = _finite_number(horizon_s, "horizon_s", positive=True)
    if horizon > MAX_HISTORY_HORIZON_S + 1e-12:
        raise ValueError(
            f"horizon_s ({horizon:g}) exceeds primary and independent CSV support "
            f"({MAX_HISTORY_HORIZON_S:g} s); do not invent a tail"
        )
    if isinstance(ranks, bool) or not isinstance(ranks, int) or ranks < 1:
        raise ValueError("ranks must be a positive integer")
    spacing = _finite_number(spacing_m, "spacing_m", positive=True)
    coarse_spacing = _finite_number(coarse_spacing_m, "coarse_spacing_m", positive=True)
    if coarse_spacing < spacing:
        raise ValueError("coarse_spacing_m must be no smaller than spacing_m")
    snapshot = _finite_number(snapshot_interval_s, "snapshot_interval_s", positive=True)
    source_length = _finite_number(source_length_m, "source_length_m", positive=True)
    source_width = _finite_number(source_width_m, "source_width_m", positive=True)
    domain = _normalize_bounds(
        domain_bounds_m,
        default=DEFAULT_DOMAIN_BOUNDS_M,
        name="domain_bounds_m",
    )
    refinement = _normalize_bounds(
        refinement_region,
        default=DEFAULT_REFINEMENT_REGION_M,
        name="refinement_region",
    )
    if not domain["x"][0] <= 0.0 <= domain["x"][1]:
        raise ValueError("the source-centered coordinate origin must lie in the x domain")
    if not domain["y"][0] <= 0.0 <= domain["y"][1]:
        raise ValueError("the source-centered coordinate origin must lie in the y domain")

    history = read_primary_history()
    if not math.isclose(history[-1][0], MAX_HISTORY_HORIZON_S, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("primary Dash-8 history support changed from the declared 5.0 s")
    bounded_history = history_to_horizon(history, horizon)
    plane_z = domain["z"][1]
    source = _make_source(
        length_m=source_length,
        width_m=source_width,
        plane_z_m=plane_z,
        domain=domain,
    )
    sources = [source]

    # Generate and validate the complete mesh before creating any output path.
    mesh_text, mesh_details = CL_HELPERS.block_mesh_dict(
        domain=domain,
        sources=sources,
        spacing_m=spacing,
        coarse_spacing_m=coarse_spacing,
        refinement_region=refinement,
    )
    expected_area = source_length * source_width
    patch_area = mesh_details["source_patch_areas_m2"][SOURCE_NAME]
    if not math.isclose(patch_area, expected_area, rel_tol=0.0, abs_tol=1e-10):
        raise ValueError(
            f"generated opening faces cover {patch_area:g} m^2, expected {expected_area:g} m^2"
        )
    if ranks > int(mesh_details["mesh_shape"]["x"]):
        raise ValueError(
            f"ranks ({ranks}) must not exceed x-direction cell count "
            f"({mesh_details['mesh_shape']['x']})"
        )

    source_origin = [0.0, 0.0, plane_z]
    domain_json = {axis: list(domain[axis]) for axis in ("x", "y", "z")}
    refinement_json = {axis: list(refinement[axis]) for axis in ("x", "y", "z")}
    mesh_details.update(
        {
            "domain_bounds_m": domain_json,
            "local_spacing_m": spacing,
            "coarse_spacing_m": coarse_spacing,
            "refinement_region_m": refinement_json,
        }
    )

    # All value validation is complete; preserve partial writes as evidence if I/O fails.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    for directory in ("0", "constant", "system"):
        (output / directory).mkdir()
    (output / "system" / "blockMeshDict").write_text(mesh_text, encoding="utf-8")

    histories = {HISTORY_NAME: bounded_history}
    turbulence_values = CL_HELPERS._write_fields(output, sources, histories)
    patch_names = [SOURCE_NAME, *OPEN_PATCHES]
    delta_t_s = CL_HELPERS._write_dictionaries(
        output,
        horizon_s=horizon,
        mesh_details=mesh_details,
        ranks=ranks,
        patches=patch_names,
        snapshot_interval_s=snapshot,
    )

    geometry = {
        "schema_version": 1,
        "source_origin_m": source_origin,
        "source_plane_z_m": plane_z,
        "geometry_evidence": (
            "provisional figure-derived candidate inference: Fig. 2 labels 4.44 m for the "
            "narrow lower section and 0.30 m for a bottom projection; the article does not "
            "identify these labels as aperture dimensions or report exit area"
        ),
        "unused_figure_dimension_note": (
            "Fig. 2 also shows a 0.10 m bottom feature; it is not interpreted as an aperture gap"
        ),
        "sources": [
            {
                key: value
                for key, value in source.items()
                if key not in {"direction_unit", "history"}
            }
            | {
                "discharge_direction_unit": source["direction_unit"],
                "history": source["history"],
            }
        ],
    }
    geometry_path = output / "source_geometry.json"
    geometry_path.write_text(
        json.dumps(geometry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    source_dir = output / "source"
    source_dir.mkdir()
    source_paths = {
        "fig4_primary_csv": PRIMARY_HISTORY_CSV,
        "fig4_independent_csv": INDEPENDENT_HISTORY_CSV,
        "e2_source_record": SOURCE_RECORD,
    }
    for source_path in source_paths.values():
        (source_dir / source_path.name).write_bytes(source_path.read_bytes())

    integrated_speed_m = integrate_history(history, horizon)
    integrated_speed_squared_m2_s = integrate_squared_history(history, horizon)
    analytic_volume_m3 = expected_area * integrated_speed_m
    analytic_mass_kg = WATER_RHO_KG_M3 * analytic_volume_m3
    analytic_momentum_impulse_n_s = WATER_RHO_KG_M3 * expected_area * integrated_speed_squared_m2_s
    per_source = {
        SOURCE_NAME: {
            "source_area_m2": expected_area,
            "integral_speed_m": integrated_speed_m,
            "integral_speed_squared_m2_s": integrated_speed_squared_m2_s,
            "analytic_expected_volume_m3": analytic_volume_m3,
            "analytic_expected_mass_kg": analytic_mass_kg,
            "analytic_expected_momentum_impulse_N_s": [
                0.0,
                0.0,
                -analytic_momentum_impulse_n_s,
            ],
        }
    }
    input_hashes = {
        "fig4_primary_csv_sha256": CL_HELPERS.sha256(PRIMARY_HISTORY_CSV),
        "fig4_independent_csv_sha256": CL_HELPERS.sha256(INDEPENDENT_HISTORY_CSV),
        "e2_source_record_sha256": CL_HELPERS.sha256(SOURCE_RECORD),
        "cl415_helper_module_sha256": CL_HELPERS.sha256(CL415_HELPERS_PATH),
        "prepare_case_sha256": CL_HELPERS.sha256(Path(__file__)),
        "source_geometry_sha256": CL_HELPERS.sha256(geometry_path),
    }
    effective_snapshot_interval = min(snapshot, horizon)
    metadata: dict[str, Any] = {
        "case_id": CASE_ID,
        "aircraft": "Dash-8",
        "evidence_label": "exploratory source-limited approximation; not E2 validation",
        "solver": "interIsoFoam",
        "openfoam_image": CL_HELPERS.IMAGE,
        "horizon_s": horizon,
        "ranks": ranks,
        "source_origin_m": source_origin,
        "source_patches": [SOURCE_NAME],
        "open_patches": OPEN_PATCHES,
        "coordinate_frame": {
            "mesh": {
                "x": "aircraft-frame streamwise axis; relative air flows in +x",
                "y": "cross-track horizontal axis",
                "z": "vertical upward; outlet flow and gravity act in -z",
            },
            "source_origin_m": source_origin,
            "source_plane_z_m": plane_z,
            "streamwise_origin_note": (
                "The coordinate origin is placed at the center of the assumed opening by convention; "
                "the paper does not identify the source rectangle's streamwise leading edge or origin."
            ),
            "paper_plot_transform": {
                "paper_streamwise_y_m": "mesh_x_m - source_origin_m[0]",
                "paper_cross_track_x_m": "mesh_y_m - source_origin_m[1]",
                "paper_downward_z_m": "source_plane_z_m - mesh_z_m",
            },
            "paper_frame_note": (
                "The published component directions are figure-read; a formal right-handed basis "
                "and signed gravity vector are not stated in the paper."
            ),
        },
        **mesh_details,
        "domain_placement_assumption": (
            f"Selected computational bounds are {domain_json} m; the top source plane "
            f"is at z={plane_z:g} m. The reported nearfield dimensions are 26 x 20 x 31 m. "
            "The outlet-to-boundary distances and source placement are assumed."
        ),
        "source_geometry": geometry,
        "source_geometry_assumption": {
            "opening_count": 1,
            "shape": "single longitudinal rectangle",
            "length_x_m": source_length,
            "width_y_m": source_width,
            "area_m2": expected_area,
            "evidence_class": "provisional figure-derived candidate inference, not a reported aperture",
            "evidence_location": "Calbrix et al. (2023), Fig. 2(b-c), PDF p. 4 / journal p. 1518",
            "mapping": (
                "4.44 m narrow lower-section label and 0.30 m bottom-projection width label "
                "are provisionally mapped to one opening; the source does not establish that mapping"
            ),
            "0_10_m_dimension": "pictured bottom feature; not used as aperture height or gap",
            "source_center_m": [0.0, 0.0, plane_z],
            "direction_unit": [0.0, 0.0, -1.0],
            "direction_evidence": "assumed vertical downward discharge from belly into domain",
            "source_profile": "uniform over the rectangle; no spatially varying profile is published",
        },
        "source_histories": {
            HISTORY_NAME: {
                "series_id": "dash8_blue",
                "figure_legend": "blue Dash-8 curve",
                "curve_quantity": (
                    "digitized scalar U_L(t); paper defines U_L=Q_L/S as mean but Fig. 4 "
                    "caption/results call the plotted quantity maximum velocity"
                ),
                "mapping": "one uniform scalar speed on one assumed outlet rectangle",
                "spatial_profile_assumption": "uniform profile; pointwise velocity profile is unavailable",
                "samples_used_m_s": [[time_s, speed] for time_s, speed in bounded_history],
                "interpolation": "piecewise linear between primary digitized samples",
                "zero_at_t0": "t=0, U_L=0 is explicitly present in the primary digitization",
                "integration_method": "exact trapezoidal integral of the piecewise-linear speed history",
                "history_support_s": [history[0][0], history[-1][0]],
                "digitized_endpoint_speed_m_s": history[-1][1],
                "source_endpoint_policy": (
                    "no forced shutoff at the horizon; the primary curve is still 0.074 m/s at 5.0 s"
                ),
                "horizon_s": horizon,
                "analytic_expected_by_source": per_source,
                "analytic_expected_volume_m3": analytic_volume_m3,
                "analytic_expected_mass_kg": analytic_mass_kg,
                "analytic_expected_momentum_impulse_N_s": [
                    0.0,
                    0.0,
                    -analytic_momentum_impulse_n_s,
                ],
                "source_patch_areas_m2": mesh_details["source_patch_areas_m2"],
                "figure_read_allowances": {
                    "time_s": "copied unchanged from the CSV; about 0.03 s",
                    "velocity_m_s": "copied unchanged from the CSV; varies from about 0.10 to 0.20 m/s",
                    "status": "heuristic raster-read allowances, not paper uncertainty",
                },
                "independent_read": {
                    "source_artifact": f"source/{INDEPENDENT_HISTORY_CSV.name}",
                    "status": "second raster implementation copied as provenance; not blended into primary history",
                },
                "source_artifact": f"source/{PRIMARY_HISTORY_CSV.name}",
            }
        },
        "analytic_expected_mass_kg": analytic_mass_kg,
        "analytic_expected_mass_by_source_kg": {
            SOURCE_NAME: analytic_mass_kg,
        },
        "analytic_expected_momentum_impulse_by_source_N_s": {
            SOURCE_NAME: [0.0, 0.0, -analytic_momentum_impulse_n_s],
        },
        "fluid_properties": {
            "water": {
                "rho_kg_m3": WATER_RHO_KG_M3,
                "mu_Pa_s": 1.0e-3,
                "evidence": "reported, E2 source record PDF p. 4 / journal p. 1518",
            },
            "air": {
                "rho_kg_m3": 1.2,
                "mu_Pa_s": 1.8e-5,
                "evidence": "assumed; numeric E2 air properties are absent from the paper",
            },
            "surface_tension_N_m": 0.0,
            "surface_tension_evidence": (
                "set to zero to match the paper's omitted momentum term; applicability on this mesh is unverified"
            ),
        },
        "air_speed_m_s": AIR_SPEED_M_S,
        "gravity_m_s2": list(GRAVITY_M_S2),
        "boundary_conditions": {
            "airInlet": "x-min plane; fixed 50 m/s +x aircraft-relative air flow",
            "open_boundaries": OPEN_PATCHES,
            "top_belly": (
                "flat slip wall over the top plane except for the single source rectangle; "
                "no aircraft or tank CAD geometry"
            ),
            "source_flow_sign": "top patch outward normal is +z; prescribed velocity is -z and enters the domain",
        },
        "turbulence_model": "standard k-epsilon RANS",
        "turbulence_assumptions": {
            "intensity": CL_HELPERS.TURBULENCE_INTENSITY,
            "air_length_scale_m": CL_HELPERS.AIR_LENGTH_SCALE_M,
            "water_length_scale_m": CL_HELPERS.WATER_LENGTH_SCALE_M,
            **turbulence_values,
            "status": "assumed; E2 inlet turbulence values are not fully reported",
        },
        "time_controls": {
            "end_s": horizon,
            "initial_delta_t_s": delta_t_s,
            "max_delta_t_s": min(
                CL_HELPERS.MAX_DELTA_T_S,
                0.25
                * min(min(widths) for widths in mesh_details["mesh_widths_by_segment_m"].values())
                / AIR_SPEED_M_S,
            ),
            "adaptive": True,
            "max_Co": CL_HELPERS.MAX_CO,
            "max_alpha_Co": CL_HELPERS.MAX_ALPHA_CO,
            "requested_snapshot_interval_s": snapshot,
            "snapshot_interval_s": effective_snapshot_interval,
        },
        "resources": {"mpi_ranks": ranks, "starting_allocation_only": True},
        "intended_diagnostic": (
            "exploratory E2 nearfield VOF run; compare alpha>=0.001 cloud and alpha>=0.9 core "
            "morphology at available paper times; no ground deposition"
        ),
        "scope_limitations": [
            f"single {source_length:g} m by {source_width:g} m rectangle is provisional; the default candidate uses Fig. 2 labels, but the paper gives no numerical exit area",
            "the pictured 0.10 m bottom feature is not treated as an aperture gap",
            "the digitized U_L(t) may be maximum velocity while the paper also defines U_L=Q_L/S as mean; this discrepancy is unresolved",
            "one uniform scalar speed is assigned over the assumed patch because pointwise exit profiles are unavailable",
            "the t=5 s digitized endpoint remains nonzero; this case does not append a shutoff, an extrapolated tail, or a claimed completed discharge",
            "no tank or aircraft geometry, rotor wake, foam, parcels, evaporation, ground impact, fire, or deposition",
            "air properties, gravity, turbulence boundary values, surface-tension omission, wall slip, and open boundaries are assumptions where not numerically specified",
            "the case is exploratory and cannot establish E2 validation, field performance, suppression, or design gain",
        ],
        "input_hashes": input_hashes,
        "provenance": {
            **_git_provenance(),
            **input_hashes,
            "source_artifacts_relative_paths": {
                key: f"source/{path.name}" for key, path in source_paths.items()
            },
        },
    }
    (output / "case-inputs.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def _read_json_bounds(path: Path | None) -> dict[str, tuple[float, float]] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"bounds JSON must contain an object: {path}")
    return {
        axis: tuple(bounds) if isinstance(bounds, list) else bounds
        for axis, bounds in value.items()
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="new, non-existing case directory"
    )
    parser.add_argument("--horizon-s", type=float, default=5.0)
    parser.add_argument("--ranks", type=int, default=20)
    parser.add_argument("--snapshot-interval-s", type=float, default=0.1)
    parser.add_argument("--spacing-m", type=float, default=0.1, help="finest local cell width")
    parser.add_argument("--coarse-spacing-m", type=float, default=0.4)
    parser.add_argument("--source-length-m", type=float, default=DEFAULT_SOURCE_LENGTH_M)
    parser.add_argument("--source-width-m", type=float, default=DEFAULT_SOURCE_WIDTH_M)
    parser.add_argument("--domain-bounds-json", type=Path)
    parser.add_argument("--refinement-region-json", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        metadata = prepare_case(
            args.output,
            horizon_s=args.horizon_s,
            ranks=args.ranks,
            snapshot_interval_s=args.snapshot_interval_s,
            spacing_m=args.spacing_m,
            coarse_spacing_m=args.coarse_spacing_m,
            source_length_m=args.source_length_m,
            source_width_m=args.source_width_m,
            domain_bounds_m=_read_json_bounds(args.domain_bounds_json),
            refinement_region=_read_json_bounds(args.refinement_region_json),
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
                "analytic_expected_mass_kg": metadata["analytic_expected_mass_kg"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
