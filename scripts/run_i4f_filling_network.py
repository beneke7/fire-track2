#!/usr/bin/env python3
"""Run an exploratory initially dry downstream I4F moving-front network case."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aerial_drop.i4f_filling_network import (  # noqa: E402
    FillingBranch,
    FillingNetworkParameters,
    _air_diagnostics,
    simulate_filling,
)
from aerial_drop.i4f_reduced import tank_volume_at_level_m3  # noqa: E402
from aerial_drop.i4f_reduced_network import (  # noqa: E402
    BranchParameters,
    GasProperties,
    HydraulicSection,
    LiquidProperties,
    NetworkParameters,
    TankProperties,
)

INPUT_PACKET_DIR = ROOT / "experiments/i4f_filling_reference"
INPUTS_DIR = INPUT_PACKET_DIR / "inputs"
INPUT_MANIFEST = INPUT_PACKET_DIR / "inputs-manifest.json"
GEOMETRY_JSON = INPUTS_DIR / "branch-hydraulic-geometry.json"
GEOMETRY_CSV = INPUTS_DIR / "branch-centerline-sections.csv"
PREVIEW_JSON = INPUTS_DIR / "preview-geometry.json"
NATIVE_INIT_JSON = INPUTS_DIR / "native-initialization-dryline.json"
COMPACT_GEOMETRY_JSON = INPUTS_DIR / "geometry_summary.json"
COMPACT_ADAPTER_JSON = INPUTS_DIR / "geometry-adapter-short1.json"
AIR_THERMO = INPUTS_DIR / "thermophysicalProperties.air"
WATER_THERMO = INPUTS_DIR / "thermophysicalProperties.water"
COMPACT_MOUTH_X_M = 4.8
LEGACY_TRANSITION_START_X_M = 4.0
COMPACT_TRANSITION_START_X_M = 3.8
LEGACY_MOUTH_X_M = 5.8
X_COMPRESSION_LENGTH_M = 1.8
VALVE_PLANE_X_M = 2.25
TANK_DIAMETER_M = 0.9  # user-confirmed value, asserted against current compact CAD input
PIPE_ROUGHNESS_M = 1.0e-5


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_info() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = git("status", "--short") or ""
    return {
        "revision": git("rev-parse", "HEAD"),
        "dirty": bool(status),
        "status_short": status.splitlines(),
    }


def _read_geometry_rows(branch_name: str) -> list[dict[str, float]]:
    with GEOMETRY_CSV.open(newline="", encoding="utf-8") as stream:
        return [
            {
                "source_s": float(row["centerline_s_from_tank_wall_m"]),
                "x": float(row["centerline_x_m"]),
                "y": float(row["centerline_y_m"]),
                "z": float(row["centerline_z_m"]),
                "area": float(row["section_area_m2"]),
            }
            for row in csv.DictReader(stream)
            if row["branch"] == branch_name
        ]


def _map_x_to_compact(x_m: float) -> float:
    if x_m <= COMPACT_TRANSITION_START_X_M + 1e-9:
        return x_m
    if x_m < LEGACY_TRANSITION_START_X_M - 1e-9:
        raise ValueError("the removed exposed 0.2 m straight has no mapped centerline station")
    return (
        COMPACT_TRANSITION_START_X_M + (x_m - LEGACY_TRANSITION_START_X_M) / X_COMPRESSION_LENGTH_M
    )


def _mapped_centerline(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    """Apply the frozen x-only compact map, trim its exposed 0.2 m straight, and recompute s."""
    raw_x = np.asarray([row["x"] for row in rows], dtype=float)
    if np.any(np.diff(raw_x) <= 0):
        raise ValueError("the source centerline x coordinate must increase strictly")
    mapped: list[dict[str, float]] = []
    for row in rows:
        old_x = row["x"]
        if COMPACT_TRANSITION_START_X_M < old_x < LEGACY_TRANSITION_START_X_M:
            continue
        point = {
            "source_x": old_x,
            "x": _map_x_to_compact(old_x),
            "y": row["y"],
            "z": row["z"],
            "area": row["area"],
        }
        if mapped and abs(point["x"] - mapped[-1]["x"]) < 1e-12:
            if not np.allclose(
                [point["y"], point["z"]],
                [mapped[-1]["y"], mapped[-1]["z"]],
                rtol=0.0,
                atol=1e-10,
            ):
                raise ValueError("compact x map creates a discontinuity at the transition inlet")
            mapped[-1] = point
            continue
        mapped.append(point)
    if abs(mapped[0]["source_x"] - rows[0]["x"]) > 1e-9:
        raise ValueError("mapped route no longer starts at the source tank-wall station")
    if abs(mapped[-1]["x"] - COMPACT_MOUTH_X_M) > 1e-9:
        raise ValueError("mapped route does not end at the current compact x=4.8 m mouth")
    cumulative = 0.0
    mapped[0]["s"] = 0.0
    for previous, current in zip(mapped[:-1], mapped[1:], strict=True):
        segment = math.dist(
            (previous["x"], previous["y"], previous["z"]),
            (current["x"], current["y"], current["z"]),
        )
        if segment <= 0:
            raise ValueError("mapped centerline contains a zero-length segment")
        cumulative += segment
        current["s"] = cumulative
    return mapped


def _station_at_source_x(
    source_rows: list[dict[str, float]], mapped_rows: list[dict[str, float]], x_m: float
) -> dict[str, float]:
    raw_x = np.asarray([row["x"] for row in source_rows], dtype=float)
    if x_m < raw_x[0] - 1e-9 or x_m > raw_x[-1] + 1e-9:
        raise ValueError(f"requested centerline station x={x_m} lies outside the source route")
    point = {
        key: float(np.interp(x_m, raw_x, [row[key] for row in source_rows]))
        for key in ("y", "z", "area")
    }
    compact_x = _map_x_to_compact(x_m)
    mapped_x = np.asarray([row["x"] for row in mapped_rows], dtype=float)
    point["x"] = compact_x
    point["source_x"] = x_m
    point["s"] = float(np.interp(compact_x, mapped_x, [row["s"] for row in mapped_rows]))
    return point


def _hydraulic_diameter(x_m: float) -> float:
    pipe_d = 0.30
    mid_d = 2.0 * 0.45 * 0.15 / (0.45 + 0.15)
    mouth_d = 2.0 * 1.0 * 0.15 / (1.0 + 0.15)
    if x_m <= 4.8:
        fraction = (x_m - 4.0) / 0.8
        return pipe_d + fraction * (mid_d - pipe_d)
    fraction = (x_m - 4.8) / 0.7
    return mid_d + fraction * (mouth_d - mid_d)


def _build_branch(
    name: str,
    meta: dict[str, Any],
    *,
    valve_cd: float,
    valve_opening_time_s: float,
    air_minor_loss_k: float | None,
) -> FillingBranch:
    source_rows = _read_geometry_rows(name)
    if not source_rows:
        raise ValueError(f"no centerline rows for branch {name}")
    mapped_rows = _mapped_centerline(source_rows)
    station_xs = [4.0 + 0.1 * index for index in range(16)]
    transition = [_station_at_source_x(source_rows, mapped_rows, x) for x in station_xs]
    mouth = _station_at_source_x(source_rows, mapped_rows, LEGACY_MOUTH_X_M)
    seat = _station_at_source_x(source_rows, mapped_rows, VALVE_PLANE_X_M)
    wall = _station_at_source_x(source_rows, mapped_rows, source_rows[0]["x"])
    if abs(wall["s"]) > 1e-12:
        raise ValueError("the compact centerline must begin at s=0 at the tank wall")

    sections: list[HydraulicSection] = []
    elevations: list[float] = [wall["z"]]
    start = transition[0]
    sections.append(
        HydraulicSection(
            name="round_feed_to_transition",
            length_m=start["s"],
            area_start_m2=wall["area"],
            area_end_m2=start["area"],
            hydraulic_diameter_start_m=0.30,
            hydraulic_diameter_end_m=0.30,
            roughness_m=PIPE_ROUGHNESS_M,
        )
    )
    elevations.append(start["z"])
    for index, (left, right) in enumerate(zip(transition[:-1], transition[1:], strict=True)):
        x_left = station_xs[index]
        x_right = station_xs[index + 1]
        sections.append(
            HydraulicSection(
                name=f"transition_{index:02d}",
                length_m=right["s"] - left["s"],
                area_start_m2=left["area"],
                area_end_m2=right["area"],
                hydraulic_diameter_start_m=_hydraulic_diameter(x_left),
                hydraulic_diameter_end_m=_hydraulic_diameter(x_right),
                roughness_m=PIPE_ROUGHNESS_M,
            )
        )
        elevations.append(right["z"])
    exit_station = transition[-1]
    sections.append(
        HydraulicSection(
            name="rectangular_mouth_channel",
            length_m=mouth["s"] - exit_station["s"],
            area_start_m2=exit_station["area"],
            area_end_m2=mouth["area"],
            hydraulic_diameter_start_m=_hydraulic_diameter(5.5),
            hydraulic_diameter_end_m=_hydraulic_diameter(5.5),
            roughness_m=PIPE_ROUGHNESS_M,
        )
    )
    elevations.append(mouth["z"])
    profile_rows = mapped_rows

    base = BranchParameters(
        name=name,
        intake_center_z_m=wall["z"],
        intake_diameter_m=0.30,
        outlet_center_z_m=mouth["z"],
        sections=tuple(sections),
        valve_Cd=valve_cd,
        valve_opening_time_s=valve_opening_time_s,
        valve_opening_law="smoothstep",
        valve_minimum_effective_opening=0.02,
        entrance_loss_K=0.5,
        transition_loss_K=0.2,
        intake_upper_edge_z_m=float(
            meta["exact_tank_wall_aperture_section"]["sampled_curve_crown_z_m"]
        ),
    )
    return FillingBranch(
        branch=base,
        elevation_samples_m=tuple(elevations),
        initial_front_s_m=seat["s"],
        transition_start_s_m=transition[0]["s"],
        transition_end_s_m=transition[-1]["s"],
        air_minor_loss_K=air_minor_loss_k,
        elevation_profile_s_m=tuple(row["s"] for row in profile_rows),
        elevation_profile_z_m=tuple(row["z"] for row in profile_rows),
    )


def _build_parameters(
    *, valve_cd: float, valve_opening_time_s: float, air_minor_loss_k: float | None
) -> tuple[FillingNetworkParameters, dict[str, Any]]:
    geometry = json.loads(GEOMETRY_JSON.read_text(encoding="utf-8"))
    preview = json.loads(PREVIEW_JSON.read_text(encoding="utf-8"))
    native = json.loads(NATIVE_INIT_JSON.read_text(encoding="utf-8"))
    compact_cad = json.loads(COMPACT_GEOMETRY_JSON.read_text(encoding="utf-8"))
    compact_adapter = json.loads(COMPACT_ADAPTER_JSON.read_text(encoding="utf-8"))
    thermo_text = AIR_THERMO.read_text(encoding="utf-8")
    water_thermo_text = WATER_THERMO.read_text(encoding="utf-8")
    cp_match = re.search(r"\bCp\s+([0-9.eE+-]+)\s*;", thermo_text)
    mol_weight_match = re.search(r"\bmolWeight\s+([0-9.eE+-]+)\s*;", thermo_text)
    water_density_match = re.search(r"\brho\s+([0-9.eE+-]+)\s*;", water_thermo_text)
    water_mu_match = re.search(r"\bmu\s+([0-9.eE+-]+)\s*;", water_thermo_text)
    if (
        cp_match is None
        or mol_weight_match is None
        or water_density_match is None
        or water_mu_match is None
    ):
        raise ValueError("could not read required current CFD thermophysical properties")
    air_cp_j_kg_k = float(cp_match.group(1))
    air_mol_weight_g_mol = float(mol_weight_match.group(1))
    air_specific_gas_constant = 8314.46261815324 / air_mol_weight_g_mol
    air_gamma = air_cp_j_kg_k / (air_cp_j_kg_k - air_specific_gas_constant)
    tank_volume_m3 = float(native["native_partition"]["groups"]["tankA"]["volume_m3"])
    tank_water_m3 = float(native["native_tank_water_integrals_m3"]["tankA"])
    tank_fill_fraction = tank_water_m3 / tank_volume_m3
    tank_diameter_m = float(compact_cad["assumptions"]["tank_diameter_m"])
    if abs(tank_diameter_m - TANK_DIAMETER_M) > 1e-12:
        raise ValueError("current compact CAD tank diameter differs from user-confirmed 0.9 m")
    tank_effective_length_m = tank_volume_m3 / (math.pi * (tank_diameter_m**2) / 4.0)
    tank_center_bounds = compact_cad["tank_metrics"]["records"][0]["bounds_m"][4:6]
    tank_center_z_m = 0.5 * sum(float(value) for value in tank_center_bounds)
    initial_pressure_abs_pa = float(native["assumptions"]["tank_pressure_absolute_Pa_assumed"])
    gas_temperature_k = float(native["assumptions"]["temperature_K"])
    ambient_pressure_pa = float(native["assumptions"]["downstream_pressure_absolute_Pa"])
    water_density_kg_m3 = float(water_density_match.group(1))
    water_viscosity_pa_s = float(water_mu_match.group(1))
    if abs(water_density_kg_m3 - float(native["assumptions"]["water_density_kg_m3"])) > 1e-9:
        raise ValueError("native dry-line water density differs from current CFD thermo")
    by_name = {item["branch"]: item for item in geometry["branches"]}
    branches = tuple(
        _build_branch(
            name,
            by_name[name],
            valve_cd=valve_cd,
            valve_opening_time_s=valve_opening_time_s,
            air_minor_loss_k=air_minor_loss_k,
        )
        for name in ("upper", "lower")
    )
    tank = TankProperties(
        "horizontal", tank_diameter_m, tank_effective_length_m, tank_center_z_m, tank_fill_fraction
    )
    gas = GasProperties(
        "air",
        initial_pressure_abs_pa,
        ambient_pressure_pa,
        gas_temperature_k,
        air_gamma,
    )
    liquid = LiquidProperties(water_density_kg_m3, water_viscosity_pa_s, 9.81)
    network = NetworkParameters(tank, gas, liquid, tuple(item.branch for item in branches))
    parameters = FillingNetworkParameters(
        network,
        branches,
        air_temperature_K=gas_temperature_k,
        air_gamma=air_gamma,
    )
    parameters.validate()
    compact_mouth_z = sorted(
        {round(float(point[1]), 9) for point in compact_adapter["topology"]["mouth_centres_yz_m"]}
    )
    if len(compact_mouth_z) != 2:
        raise ValueError("current compact geometry must report two branch-mouth elevations")
    expected_mouth_z = {"lower": compact_mouth_z[0], "upper": compact_mouth_z[1]}
    preview_mouth_z = {
        item["level"]: float(item["nozzle_center_z_m"])
        for item in preview["preview_config"]["branch_definitions"]
    }
    for branch in branches:
        if abs(branch.branch.outlet_center_z_m - expected_mouth_z[branch.branch.name]) > 1e-9:
            raise ValueError(
                f"mapped {branch.branch.name} route endpoint misses compact CAD mouth z"
            )
        if abs(branch.branch.outlet_center_z_m - preview_mouth_z[branch.branch.name]) > 1e-9:
            raise ValueError(
                f"mapped {branch.branch.name} route endpoint misses source preview mouth z"
            )
    native_upstream_feed = float(native["additional_wetted_feed_water_m3"]["tankA_feed"])
    model_upstream_feed = sum(item.initial_wet_volume_m3 for item in branches)
    native_downstream_water = float(
        native["native_partition"]["groups"]["downstreamTrainA"]["water_volume_m3"]
    )
    model_downstream_water = 0.0
    tank_water_initial = tank.tank_volume_m3 * tank.fill_fraction
    model_headspace_m3 = tank.tank_volume_m3 - tank_water_m3
    native_headspace_m3 = float(native["actual_tank_headspace_m3"]["tankA"])
    input_comparison = {
        "tank_capacity_m3": {
            "native": tank_volume_m3,
            "model": tank.tank_volume_m3,
            "absolute_difference": abs(tank_volume_m3 - tank.tank_volume_m3),
            "tolerance": 1e-12,
            "pass": abs(tank_volume_m3 - tank.tank_volume_m3) <= 1e-12,
        },
        "tank_payload_water_m3": {
            "native": tank_water_m3,
            "model": tank_water_initial,
            "absolute_difference": abs(tank_water_m3 - tank_water_initial),
            "tolerance": 1e-12,
            "pass": abs(tank_water_m3 - tank_water_initial) <= 1e-12,
        },
        "headspace_m3": {
            "native": native_headspace_m3,
            "model": model_headspace_m3,
            "absolute_difference": abs(native_headspace_m3 - model_headspace_m3),
            "tolerance": 1e-12,
            "pass": abs(native_headspace_m3 - model_headspace_m3) <= 1e-12,
        },
        "initial_tank_pressure_absolute_Pa": {
            "native": initial_pressure_abs_pa,
            "model": gas.initial_pressure_abs_Pa,
            "absolute_difference": abs(initial_pressure_abs_pa - gas.initial_pressure_abs_Pa),
            "tolerance": 1e-9,
            "pass": abs(initial_pressure_abs_pa - gas.initial_pressure_abs_Pa) <= 1e-9,
        },
        "initial_temperature_K": {
            "native": gas_temperature_k,
            "model": gas.initial_temperature_K,
            "absolute_difference": abs(gas_temperature_k - gas.initial_temperature_K),
            "tolerance": 1e-12,
            "pass": abs(gas_temperature_k - gas.initial_temperature_K) <= 1e-12,
        },
        "downstream_initial_gas_pressure_absolute_Pa": {
            "native": ambient_pressure_pa,
            "model_front_boundary": gas.ambient_pressure_Pa,
            "absolute_difference": abs(ambient_pressure_pa - gas.ambient_pressure_Pa),
            "tolerance": 1e-9,
            "pass": abs(ambient_pressure_pa - gas.ambient_pressure_Pa) <= 1e-9,
        },
        "downstream_initial_air_temperature_K": {
            "native": gas_temperature_k,
            "model_air_screen": parameters.air_temperature_K,
            "absolute_difference": abs(gas_temperature_k - parameters.air_temperature_K),
            "tolerance": 1e-12,
            "pass": abs(gas_temperature_k - parameters.air_temperature_K) <= 1e-12,
        },
        "downstream_initial_water_m3": {
            "native": native_downstream_water,
            "model": model_downstream_water,
            "absolute_difference": abs(native_downstream_water - model_downstream_water),
            "tolerance": 1e-15,
            "pass": abs(native_downstream_water - model_downstream_water) <= 1e-15,
        },
        "initial_wet_tank_to_valve_feed_m3": {
            "native": native_upstream_feed,
            "model": model_upstream_feed,
            "absolute_difference": abs(native_upstream_feed - model_upstream_feed),
            "relative_difference": abs(model_upstream_feed / native_upstream_feed - 1.0),
            "assertion": "reported as grid/centerline volume difference, not required to match exactly",
        },
    }
    input_assertions_pass = all(
        row["pass"] for row in input_comparison.values() if isinstance(row, dict) and "pass" in row
    )
    cad_line_volume_per_tank = float(
        compact_cad["tank_metrics"]["downstream_line_volume_m3_each"][0]
    )
    native_full_line_zone_volume = float(native["native_partition"]["lineA_native_zone_volume_m3"])
    geometry_summary = {
        "source_bundle": str(INPUT_PACKET_DIR.relative_to(ROOT)),
        "model_scope": "current compact 1-tank / 2-branch equivalent line, downstream air, wetted feed through assumed valve plane",
        "source_centerline_is_legacy_preview_x_only_remapped_to_compact_current_candidate": True,
        "coordinate_map": {
            "remove_exposed_round_straight_x3p8_to_4p0_m": True,
            "legacy_x_at_or_below_3p8_unchanged": True,
            "legacy_x_at_or_above_4p0_m": "x_compact=3.8+(x_legacy-4.0)/1.8",
            "y_z_mapping": "retain legacy preview y,z; recompute 3D polyline arclength after x map",
            "compact_mouth_x_m": COMPACT_MOUTH_X_M,
        },
        "seat_x_m_assumed": VALVE_PLANE_X_M,
        "tank_state_from_current_dryline_native_initialization": {
            "tank_identity": "tankA representative; tankB differs by sub-microlitre capacity",
            "tank_capacity_m3": tank_volume_m3,
            "tank_water_m3": tank_water_m3,
            "initial_headspace_m3": tank_volume_m3 - tank_water_m3,
            "initial_pressure_abs_Pa": initial_pressure_abs_pa,
            "initial_temperature_K": gas_temperature_k,
            "air_Cp_J_kg_K": air_cp_j_kg_k,
            "air_molecular_weight_g_mol": air_mol_weight_g_mol,
            "air_R_J_kg_K": air_specific_gas_constant,
            "air_gamma_and_selected_polytropic_n": air_gamma,
            "water_density_kg_m3": water_density_kg_m3,
            "water_dynamic_viscosity_Pa_s": water_viscosity_pa_s,
            "tank_diameter_m": tank_diameter_m,
            "tank_center_z_m": tank_center_z_m,
            "current_compact_mouth_center_z_m_by_branch": expected_mouth_z,
        },
        "initial_wet_feed_comparison": {
            "model_two_branch_area_integral_m3": model_upstream_feed,
            "native_tankA_feed_zone_m3": native_upstream_feed,
            "model_minus_native_m3": model_upstream_feed - native_upstream_feed,
            "model_minus_native_percent": 100.0
            * (model_upstream_feed / native_upstream_feed - 1.0),
            "interpretation": "provisional 1-D centerline integral vs cell-zone volume, not normalized",
        },
        "native_initialization_input_comparison": {
            "source": str(NATIVE_INIT_JSON.relative_to(ROOT)),
            "all_direct_state_assertions_pass": input_assertions_pass,
            "assertions": input_comparison,
        },
        "current_compact_cad_line_volume_outside_tank_m3_per_tank": cad_line_volume_per_tank,
        "current_native_full_line_zone_including_mouth_slabs_m3_per_tank": native_full_line_zone_volume,
        "equivalent_minus_native_full_line_zone_m3_per_tank": (
            sum(item.full_wet_volume_m3 for item in branches) - native_full_line_zone_volume
        ),
        "equivalent_minus_native_full_line_zone_percent": 100.0
        * (sum(item.full_wet_volume_m3 for item in branches) / native_full_line_zone_volume - 1.0),
        "actual_compact_geometry_adapter": str(COMPACT_ADAPTER_JSON.relative_to(ROOT)),
        "branches": {
            item.branch.name: {
                "initial_front_s_m": item.initial_front_s_m,
                "initial_front_z_m": item.elevation_at_s(item.initial_front_s_m),
                "initial_wet_volume_m3": item.initial_wet_volume_m3,
                "full_wet_volume_m3": item.full_wet_volume_m3,
                "mouth_x_m": COMPACT_MOUTH_X_M,
                "mouth_z_m": item.branch.outlet_center_z_m,
                "branch_full_inertance_integral_m_minus1": item.full_inertance_integral_m,
                "initial_wet_inertance_kg_m4": (
                    water_density_kg_m3 * item.inertance_integral_to_s(item.initial_front_s_m)
                ),
                "transition_start_s_m": item.transition_start_s_m,
                "transition_end_s_m": item.transition_end_s_m,
                "mouth_s_m": item.length_m,
            }
            for item in branches
        },
        "compact_equivalent_line_total_m3_per_tank": sum(
            item.full_wet_volume_m3 for item in branches
        ),
        "equivalent_minus_compact_cad_m3_per_tank": (
            sum(item.full_wet_volume_m3 for item in branches) - cad_line_volume_per_tank
        ),
        "equivalent_minus_compact_cad_percent": 100.0
        * (sum(item.full_wet_volume_m3 for item in branches) / cad_line_volume_per_tank - 1.0),
        "native_initialization_path": str(NATIVE_INIT_JSON.relative_to(ROOT)),
        "compact_geometry_summary_path": str(COMPACT_GEOMETRY_JSON.relative_to(ROOT)),
    }
    return parameters, geometry_summary


def _write_csv(path: Path, samples: dict[str, np.ndarray]) -> None:
    columns = list(samples)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row_index in range(len(samples[columns[0]])):
            writer.writerow({column: samples[column][row_index] for column in columns})


def _air_k_sensitivity(
    parameters: FillingNetworkParameters,
    samples: dict[str, np.ndarray],
    time_s: float,
) -> list[dict[str, Any]]:
    """Evaluate diagnostic dry-path K scenarios on the same saved liquid state."""
    time_index = int(np.argmin(np.abs(samples["time_s"] - time_s)))
    rows: list[dict[str, Any]] = []
    for branch in parameters.branches:
        name = branch.branch.name
        flow = float(samples[f"flow_{name}_m3_s"][time_index])
        front = float(samples[f"front_s_{name}_m"][time_index])
        drive = float(samples[f"liquid_drive_{name}_Pa"][time_index])
        friction_only = replace(branch, air_minor_loss_K=0.0)
        _, friction_drop, _ = _air_diagnostics(
            friction_only,
            flow,
            front,
            parameters=parameters,
            liquid_drive_Pa=drive,
        )
        for k_value in (0.0, 10.0, 100.0):
            trial = replace(branch, air_minor_loss_K=k_value)
            mach, total_drop, screen_pass = _air_diagnostics(
                trial,
                flow,
                front,
                parameters=parameters,
                liquid_drive_Pa=drive,
            )
            rows.append(
                {
                    "diagnostic_time_s": float(samples["time_s"][time_index]),
                    "branch": name,
                    "assumed_air_minor_loss_K": k_value,
                    "air_mach_estimate": mach,
                    "friction_only_pressure_drop_Pa": friction_drop,
                    "total_pressure_drop_estimate_Pa": total_drop,
                    "liquid_driving_pressure_Pa": drive,
                    "pressure_loss_to_drive_ratio": total_drop / abs(drive) if drive else None,
                    "screen_pass": screen_pass,
                    "sensitivity_changes_only_diagnostic_not_front_pressure_or_flow": True,
                }
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Frozen input files and provenance are in "
            "experiments/i4f_filling_reference/inputs/ and inputs-manifest.json. "
            "Those inputs remain provisional; see the manifest for model limits."
        ),
    )
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/runs")
    parser.add_argument("--time-step", type=float, default=5.0e-5)
    parser.add_argument("--max-time", type=float, default=0.05)
    parser.add_argument("--valve-cd", type=float, default=0.7)
    parser.add_argument("--valve-opening-time", type=float, default=1.0)
    parser.add_argument(
        "--air-minor-loss-k",
        type=float,
        default=None,
        help="declared lumped dry-path minor-loss K; omit to mark the vent screen incomplete",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    parameters, geometry_summary = _build_parameters(
        valve_cd=args.valve_cd,
        valve_opening_time_s=args.valve_opening_time,
        air_minor_loss_k=args.air_minor_loss_k,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = args.output_root.resolve() / f"i4f-filling-network-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "inputs").mkdir()
    (run_dir / "source_snapshot").mkdir()
    input_paths = (
        INPUT_MANIFEST,
        GEOMETRY_JSON,
        GEOMETRY_CSV,
        PREVIEW_JSON,
        NATIVE_INIT_JSON,
        COMPACT_GEOMETRY_JSON,
        COMPACT_ADAPTER_JSON,
        AIR_THERMO,
        WATER_THERMO,
    )
    for path in input_paths:
        (run_dir / "inputs" / path.name).write_bytes(path.read_bytes())

    source_paths = (
        ROOT / "src/aerial_drop/i4f_filling_network.py",
        ROOT / "src/aerial_drop/i4f_reduced_network.py",
        ROOT / "src/aerial_drop/i4f_reduced.py",
        Path(__file__).resolve(),
        INPUT_MANIFEST,
        GEOMETRY_JSON,
        GEOMETRY_CSV,
        PREVIEW_JSON,
        NATIVE_INIT_JSON,
        COMPACT_GEOMETRY_JSON,
        COMPACT_ADAPTER_JSON,
        AIR_THERMO,
        WATER_THERMO,
    )
    source_hashes = {
        str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path): _sha256(path)
        for path in source_paths
    }
    for path in source_paths:
        if path.is_relative_to(ROOT):
            snapshot = run_dir / "source_snapshot" / path.relative_to(ROOT)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, snapshot)
    simulation_started_at = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    result = simulate_filling(
        parameters,
        time_step_s=args.time_step,
        max_time_s=args.max_time,
    )
    elapsed = time.perf_counter() - start
    _write_csv(run_dir / "history.csv", result.samples)
    arrivals = {}
    for branch in parameters.branches:
        column = f"external_water_volume_{branch.branch.name}_m3"
        hits = np.flatnonzero(result.samples[column] > 0)
        arrivals[branch.branch.name] = (
            float(result.samples["time_s"][hits[0]]) if hits.size else None
        )
    air_screen_time = min(0.05, result.stop_time_s)
    air_k_sensitivity = _air_k_sensitivity(parameters, result.samples, air_screen_time)
    froude_index = int(np.argmin(np.abs(result.samples["time_s"] - air_screen_time)))
    front_froude_at_screen_time = {
        branch.branch.name: float(
            result.samples[f"front_froude_{branch.branch.name}"][froude_index]
        )
        for branch in parameters.branches
    }
    summary = {
        "schema": "i4f-moving-front-fill-run-v2",
        "purpose": "exploratory 1-D filling of initially air-filled downstream branch paths",
        "utc_bundle_created_at": stamp,
        "utc_simulation_started_at": simulation_started_at,
        "git": _git_info(),
        "source_sha256": source_hashes,
        "input_assumptions": {
            "initial_wet_upstream_line_water_m3": result.initial_wet_line_water_volume_m3,
            "case_scope": "current compact one-tank / two-branch candidate, 4.8 m mouth",
            "tank_capacity_m3": parameters.tank.tank_volume_m3,
            "tank_water_initial_m3": result.initial_tank_water_volume_m3,
            "headspace_initial_m3": parameters.tank.tank_volume_m3
            - result.initial_tank_water_volume_m3,
            "gas_initial_pressure_absolute_Pa": parameters.gas.initial_pressure_abs_Pa,
            "gas_initial_temperature_K": parameters.gas.initial_temperature_K,
            "gas_polytropic_n_assumed": parameters.gas.polytropic_n,
            "air_gamma_from_current_thermophysicalProperties": parameters.gas.polytropic_n,
            "ambient_pressure_Pa": parameters.gas.ambient_pressure_Pa,
            "downstream_air_temperature_K": parameters.air_temperature_K,
            "front_pressure_model": "ambient static pressure; declared vented approximation",
            "air_volume_flow_screen": "assumes dry-path air volume flow equals front displacement rate",
            "vent_screen_thresholds_are_engineering_choices": {
                "maximum_air_mach": parameters.max_screened_air_mach,
                "maximum_air_pressure_loss_fraction_of_liquid_drive": (
                    parameters.max_screened_air_loss_fraction
                ),
            },
            "air_minor_loss_K": args.air_minor_loss_k,
            "ambient_front_validity_caveat": (
                "screen is incomplete when air_minor_loss_K is omitted; dry-path local losses "
                "(including bends/transition) and detailed gas compressibility are not modeled"
            ),
            "valve_Cd_assumed": args.valve_cd,
            "valve_opening_time_s_assumed": args.valve_opening_time,
            "valve_opening_law": "smoothstep",
            "valve_minimum_effective_opening_assumed": 0.02,
            "valve_seat_x_m_assumed": VALVE_PLANE_X_M,
            "tank_intake_crown_stop": {
                "highest_crown_z_m": max(
                    branch.branch.intake_crown_z_m for branch in parameters.branches
                ),
                "tank_water_volume_at_crown_m3": tank_volume_at_level_m3(
                    parameters.tank,
                    max(branch.branch.intake_crown_z_m for branch in parameters.branches),
                ),
            },
            "route_geometry": geometry_summary,
            "dimensions_and_centerlines_are_provisional_preview_not_measurements": True,
            "native_initialization_source": str(NATIVE_INIT_JSON.relative_to(ROOT)),
            "actual_initial_wet_feed_reference_m3": geometry_summary["initial_wet_feed_comparison"][
                "native_tankA_feed_zone_m3"
            ],
            "model_initial_wet_feed_minus_native_m3": geometry_summary[
                "initial_wet_feed_comparison"
            ]["model_minus_native_m3"],
        },
        "integration": {
            "method": "explicit midpoint RK2",
            "time_step_s": args.time_step,
            "requested_max_time_s": args.max_time,
            "stop_reason": result.stop_reason,
            "actual_stop_time_s": result.stop_time_s,
            "wall_seconds": elapsed,
            "first_outlet_water_arrival_s_by_branch": arrivals,
            "air_minor_loss_K_sensitivity": {
                "assumed_values_are_scenarios_not_measurements_or_rigorous_bounds": [
                    0,
                    10,
                    100,
                ],
                "diagnostic_time_target_s": air_screen_time,
                "rows": air_k_sensitivity,
            },
            "full_bore_front_froude_at_screen_time": {
                "time_s": float(result.samples["time_s"][froude_index]),
                "by_branch": front_froude_at_screen_time,
                "interpretation": "diagnostic only; no universal cutoff is applied",
            },
            "max_abs_volume_balance_residual_m3": result.max_volume_balance_error_m3,
            "max_abs_branch_volume_balance_residual_m3": max(
                float(
                    np.max(
                        np.abs(
                            result.samples[
                                f"branch_volume_balance_residual_{branch.branch.name}_m3"
                            ]
                        )
                    )
                )
                for branch in parameters.branches
            ),
            "total_external_water_volume_m3": result.total_external_water_volume_m3,
        },
        "caveats": [
            "legacy branch preview coordinates are transformed to the current 4.8 m compact candidate by the frozen x-only map; y/z are retained and 3D arclength is recomputed",
            "current dry-line native initialization supplies tank capacity, water, pressure, temperature, air thermo and wetted upstream-feed reference; Tank A is modeled as representative",
            "compact line areas and transition losses remain an equivalent-line approximation; the network line volume is compared against current compact CAD and native zones",
            "single full-bore water front per branch; no stratification, slugs, or trapped pockets",
            "front Froude number is reported as a diagnostic and does not validate piston-front kinematics",
            "front pressure is held at ambient only as a declared approximation and has an air-loss screen",
            "unknown valve seat, Cd, opening history, bend loss, and actual branch geometry remain provisional",
            "tank-to-line water entering the branch is stored until the front reaches the open mouth",
        ],
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"run_dir": str(run_dir), **summary["integration"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
