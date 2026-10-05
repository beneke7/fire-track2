#!/usr/bin/env python3
"""Prepare an assumed gravity-driven Dash-8 tank-discharge VOF pilot.

This generates dictionaries and a multi-block mesh description only.  It does
not run interIsoFoam or prescribe the Calbrix Figure 4 velocity history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RADIUS_M = 0.85
TANK_HEIGHT_M = 1.5
TANK_LENGTH_M = 4.44
HEAD_M = 1.0
DEFAULT_HORIZON_S = 0.6
WATER_RHO_KG_M3 = 1000.0
WATER_NU_M2_S = 1.0e-6
AIR_RHO_KG_M3 = 1.2
AIR_NU_M2_S = 1.5e-5
GRAVITY_M_S2 = 9.81
PINNED_IMAGE = "opencfd/openfoam-default:2512"
PINNED_IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
SOURCE_PDF = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
SOURCE_RECORD = ROOT / "experiments/E2_CALBRIX_SOURCE.md"
HISTORY_CSV = ROOT / "data/derived/calbrix_dash8_fig4_velocity.csv"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def foam_header(object_name: str, *, location: str | None = None, cls: str = "dictionary") -> str:
    location_line = f'    location    "{location}";\n' if location else ""
    return (
        "/*--------------------------------*- C++ -*----------------------------------*\\\n"
        "| =========                 |                                                 |\n"
        "| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n"
        "|  \\    /   O peration     | Version:  v2512                                 |\n"
        "|   \\  /    A nd           | Website:  www.openfoam.com                      |\n"
        "|    \\/     M anipulation  |                                                 |\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {cls};\n"
        f"{location_line}"
        f"    object      {object_name};\n"
        "}\n\n"
    )


def aperture_parameters(aperture: str) -> dict[str, float | str]:
    if aperture == "large":
        return {
            "label": "large_default",
            "length_m": 4.44,
            "width_m": 0.30,
            "area_m2": 1.332,
            "basis": "project's current assumed nearfield opening; not reported by the paper",
        }
    if aperture == "small":
        return {
            "label": "small_area_sensitivity",
            "length_m": 2.22,
            "width_m": 0.15,
            "area_m2": 0.333,
            "basis": "explicit conditional area sensitivity; individual dimensions are assumptions",
        }
    raise ValueError("aperture must be 'large' or 'small'")


def _fmt(value: float) -> str:
    return f"{value:.12g}"


def _foam_list(name: str, values: list[str]) -> str:
    return f"{name}\n(\n" + "\n".join(f"    {value}" for value in values) + "\n);\n"


def rounded_bottom_mesh(aperture: str) -> tuple[str, dict[str, Any]]:
    """Make a conformal tank-to-air opening with a circularly rounded tank floor."""
    outlet = aperture_parameters(aperture)
    half_width = float(outlet["width_m"]) / 2.0
    half_length = float(outlet["length_m"]) / 2.0
    curve_limit = 0.80
    x_breaks = [-RADIUS_M, -curve_limit, -half_width, 0.0, half_width, curve_limit, RADIUS_M]
    y_breaks = (
        [-TANK_LENGTH_M / 2.0, TANK_LENGTH_M / 2.0]
        if aperture == "large"
        else [-TANK_LENGTH_M / 2.0, -half_length, half_length, TANK_LENGTH_M / 2.0]
    )
    opening_y_index = 0 if aperture == "large" else 1
    opening_y = (y_breaks[opening_y_index], y_breaks[opening_y_index + 1])

    # A circle through the tank side-rim and slot lip points approximates the
    # drawn rounded belly.  Its lower arc is omitted across the outlet itself.
    circle_z = (2.0 * RADIUS_M**2 - half_width**2) / (2.0 * RADIUS_M)
    circle_radius = math.hypot(half_width, circle_z)

    def bottom_z(x: float) -> float:
        if abs(x) <= half_width + 1e-12:
            return 0.0
        curve_x = min(abs(x), curve_limit)
        return circle_z - math.sqrt(max(0.0, circle_radius**2 - curve_x**2))

    points: list[tuple[float, float, float]] = []
    point_lookup: dict[tuple[float, float, float], int] = {}

    def point(x: float, y: float, z: float) -> int:
        coord = (round(x, 12), round(y, 12), round(z, 12))
        if coord not in point_lookup:
            point_lookup[coord] = len(points)
            points.append(coord)
        return point_lookup[coord]

    blocks: list[dict[str, Any]] = []
    boundaries: dict[str, list[tuple[int, ...]]] = {
        "tankWalls": [],
        "vent": [],
        "ambient": [],
    }
    arcs: dict[tuple[int, int], tuple[float, float, float]] = {}

    def add_arc(p0: int, p1: int, x0: float, x1: float, y: float) -> None:
        theta0 = math.atan2(bottom_z(x0) - circle_z, x0)
        theta1 = math.atan2(bottom_z(x1) - circle_z, x1)
        if x0 < 0 and theta1 < theta0:
            theta1 += 2.0 * math.pi
        elif x0 >= 0 and theta1 < theta0:
            theta1 += 2.0 * math.pi
        theta = 0.5 * (theta0 + theta1)
        mid = (
            circle_radius * math.cos(theta),
            y,
            circle_z + circle_radius * math.sin(theta),
        )
        arcs[tuple(sorted((p0, p1)))] = mid

    x_counts: list[int] = []
    for index, (x0, x1) in enumerate(zip(x_breaks, x_breaks[1:])):
        width = x1 - x0
        x_counts.append(max(3, math.ceil(width / 0.025)))
    ny_counts = [max(1, round((y1 - y0) / 0.0444)) for y0, y1 in zip(y_breaks, y_breaks[1:])]
    nz_tank = 40

    def add_block(
        *,
        x0: float,
        x1: float,
        y0: float,
        y1: float,
        z0_x0: float,
        z0_x1: float,
        z1: float,
        nx: int,
        ny: int,
        nz: int,
        kind: str,
        x_segment: int | None = None,
        y_segment: int | None = None,
        is_opening: bool = False,
    ) -> None:
        ids = (
            point(x0, y0, z0_x0),
            point(x1, y0, z0_x1),
            point(x1, y1, z0_x1),
            point(x0, y1, z0_x0),
            point(x0, y0, z1),
            point(x1, y0, z1),
            point(x1, y1, z1),
            point(x0, y1, z1),
        )
        blocks.append(
            {
                "ids": ids,
                "cells": (nx, ny, nz),
                "kind": kind,
                "x_segment": x_segment,
                "y_segment": y_segment,
                "is_opening": is_opening,
            }
        )
        if kind == "tank":
            boundaries["vent"].append((ids[4], ids[5], ids[6], ids[7]))
            if x_segment == 0:
                boundaries["tankWalls"].append((ids[0], ids[4], ids[7], ids[3]))
            if x_segment == len(x_breaks) - 2:
                boundaries["tankWalls"].append((ids[1], ids[2], ids[6], ids[5]))
            if y_segment == 0:
                boundaries["tankWalls"].append((ids[0], ids[1], ids[5], ids[4]))
            if y_segment == len(y_breaks) - 2:
                boundaries["tankWalls"].append((ids[3], ids[7], ids[6], ids[2]))
            if not is_opening:
                boundaries["tankWalls"].append((ids[0], ids[3], ids[2], ids[1]))
            if x_segment in (1, len(x_breaks) - 3):
                # Circular bottom edges at the two curved belly blocks.
                y_front = y0
                y_back = y1
                add_arc(ids[0], ids[1], x0, x1, y_front)
                add_arc(ids[3], ids[2], x0, x1, y_back)
        elif kind == "throat":
            # Its top and bottom faces connect conformally to the tank and
            # plenum; the lateral faces remain open to ambient air.
            if x_segment == 2:
                boundaries["ambient"].append((ids[0], ids[4], ids[7], ids[3]))
            elif x_segment == 3:
                boundaries["ambient"].append((ids[1], ids[2], ids[6], ids[5]))
            boundaries["ambient"].extend(
                ((ids[0], ids[1], ids[5], ids[4]), (ids[3], ids[7], ids[6], ids[2]))
            )
        elif kind == "plenum":
            # The centre top tiles connect to the throat.  Remaining exterior
            # surfaces are open to the ambient pressure reservoir.
            boundaries["ambient"].append((ids[0], ids[3], ids[2], ids[1]))
            if x_segment == 0:
                boundaries["ambient"].append((ids[0], ids[4], ids[7], ids[3]))
            if x_segment == 3:
                boundaries["ambient"].append((ids[1], ids[2], ids[6], ids[5]))
            if y_segment == 0:
                boundaries["ambient"].append((ids[0], ids[1], ids[5], ids[4]))
            if y_segment == 2:
                boundaries["ambient"].append((ids[3], ids[7], ids[6], ids[2]))
            if not (x_segment in (1, 2) and y_segment == 1):
                boundaries["ambient"].append((ids[4], ids[5], ids[6], ids[7]))

    for yi, (y0, y1) in enumerate(zip(y_breaks, y_breaks[1:])):
        for xi, (x0, x1) in enumerate(zip(x_breaks, x_breaks[1:])):
            opening = xi in (2, 3) and yi == opening_y_index
            add_block(
                x0=x0,
                x1=x1,
                y0=y0,
                y1=y1,
                z0_x0=bottom_z(x0),
                z0_x1=bottom_z(x1),
                z1=TANK_HEIGHT_M,
                nx=x_counts[xi],
                ny=ny_counts[yi],
                nz=nz_tank,
                kind="tank",
                x_segment=xi,
                y_segment=yi,
                is_opening=opening,
            )

    # A conformal short throat joins the tank aperture to an expanded ambient
    # plenum. This permits jet contraction without prescribing a velocity
    # curve; all dimensions below are explicit modeling assumptions.
    throat_depth = 0.15
    plenum_depth = 1.35
    throat_nz = 6
    plenum_x = [-1.0, -half_width, 0.0, half_width, 1.0]
    plenum_y = [opening_y[0] - 0.5, opening_y[0], opening_y[1], opening_y[1] + 0.5]
    plenum_nx = [max(12, math.ceil((x1 - x0) / 0.05)) for x0, x1 in zip(plenum_x, plenum_x[1:])]
    plenum_nx[1] = x_counts[2]
    plenum_nx[2] = x_counts[3]
    plenum_ny = [max(6, math.ceil((y1 - y0) / 0.05)) for y0, y1 in zip(plenum_y, plenum_y[1:])]
    plenum_ny[1] = ny_counts[opening_y_index]

    for yi, (y0, y1) in enumerate(zip(y_breaks, y_breaks[1:])):
        if yi != opening_y_index:
            continue
        for xi in (2, 3):
            x0, x1 = x_breaks[xi], x_breaks[xi + 1]
            add_block(
                x0=x0,
                x1=x1,
                y0=y0,
                y1=y1,
                z0_x0=-throat_depth,
                z0_x1=-throat_depth,
                z1=0.0,
                nx=x_counts[xi],
                ny=ny_counts[yi],
                nz=throat_nz,
                kind="throat",
                x_segment=xi,
                y_segment=yi,
            )

    for yi, (y0, y1) in enumerate(zip(plenum_y, plenum_y[1:])):
        for xi, (x0, x1) in enumerate(zip(plenum_x, plenum_x[1:])):
            add_block(
                x0=x0,
                x1=x1,
                y0=y0,
                y1=y1,
                z0_x0=-(throat_depth + plenum_depth),
                z0_x1=-(throat_depth + plenum_depth),
                z1=-throat_depth,
                nx=plenum_nx[xi],
                ny=plenum_ny[yi],
                nz=30,
                kind="plenum",
                x_segment=xi,
                y_segment=yi,
            )

    block_lines = []
    for block in blocks:
        ids = " ".join(str(index) for index in block["ids"])
        nx, ny, nz = block["cells"]
        block_lines.append(f"    hex ({ids}) ({nx} {ny} {nz}) simpleGrading (1 1 1)")

    edge_lines = []
    for (p0, p1), midpoint in sorted(arcs.items()):
        edge_lines.append(
            f"    arc {p0} {p1} ({_fmt(midpoint[0])} {_fmt(midpoint[1])} {_fmt(midpoint[2])})"
        )

    patch_lines = []
    for name, patch_type in (("tankWalls", "wall"), ("vent", "patch"), ("ambient", "patch")):
        face_lines = ["        (" + " ".join(map(str, face)) + ")" for face in boundaries[name]]
        patch_lines.append(
            f"    {name}\n    {{\n        type {patch_type};\n        faces\n        (\n"
            + "\n".join(face_lines)
            + "\n        );\n    }"
        )

    point_lines = [f"    ({_fmt(x)} {_fmt(y)} {_fmt(z)})" for x, y, z in points]
    text = (
        foam_header("blockMeshDict", location="system")
        + "convertToMeters 1;\n\n"
        + _foam_list("vertices", point_lines)
        + "\nblocks\n(\n"
        + "\n".join(block_lines)
        + "\n);\n\nedges\n(\n"
        + "\n".join(edge_lines)
        + "\n);\n\nboundary\n(\n"
        + "\n\n".join(patch_lines)
        + "\n);\n\nmergePatchPairs ();\n"
    )
    estimated_cells = sum(math.prod(block["cells"]) for block in blocks)
    metadata = {
        "aperture": outlet,
        "tank_internal_width_m": 2.0 * RADIUS_M,
        "tank_lower_section_span_m": TANK_LENGTH_M,
        "tank_height_m": TANK_HEIGHT_M,
        "head_measured_from_sampling_plane_z_m": 0.0,
        "outlet_sampling_plane_z_m": 0.0,
        "curvature": {
            "circle_center_xz_m": [0.0, circle_z],
            "circle_radius_m": circle_radius,
            "description": "assumed circular rounded belly, truncated at |x|=0.80 m with a 50 mm flat rim shelf and flat slot lip",
        },
        "cell_counts_by_block": [list(block["cells"]) for block in blocks],
        "mesh_cells_expected": estimated_cells,
        "opening_faces_across_transverse_width_minimum": sum(x_counts[2:4]),
        "downstream_plenum_bounds_m": {
            "x": [plenum_x[0], plenum_x[-1]],
            "y": [plenum_y[0], plenum_y[-1]],
            "z": [-(throat_depth + plenum_depth), -throat_depth],
            "throat_depth_m": throat_depth,
        },
        "outlet_winding_expectation": "tank-to-downstream, approximately -z, by setsToFaceZone from the tank-side cellSet",
        "patch_face_polygons_in_blockmeshdict": {
            name: len(faces) for name, faces in boundaries.items()
        },
    }
    return text, metadata


def _toposet_dict(aperture: str) -> str:
    outlet = aperture_parameters(aperture)
    half_width = float(outlet["width_m"]) / 2.0
    half_length = float(outlet["length_m"]) / 2.0
    y_min, y_max = -half_length, half_length
    e = 1.0e-5
    return (
        foam_header("topoSetDict", location="system")
        + "actions\n(\n"
        + "    { name outletFaces; type faceSet; action new; source boxToFace;\n"
        + f"      box ({_fmt(-half_width - e)} {_fmt(y_min - e)} {_fmt(-e)}) ({_fmt(half_width + e)} {_fmt(y_max + e)} {_fmt(e)}); }}\n"
        + "    { name tankCells; type cellSet; action new; source boxToCell;\n"
        + f"      box ({_fmt(-RADIUS_M - e)} {_fmt(-TANK_LENGTH_M / 2 - e)} 0) ({_fmt(RADIUS_M + e)} {_fmt(TANK_LENGTH_M / 2 + e)} {_fmt(TANK_HEIGHT_M + e)}); }}\n"
        + "    { name outletPlane; type faceZoneSet; action new; source setsToFaceZone;\n"
        + "      faceSet outletFaces; cellSet tankCells; }\n"
        + ");\n"
    )


def _field(object_name: str, cls: str, dimensions: str, internal: str, patches: str) -> str:
    return (
        foam_header(object_name, cls=cls)
        + f"dimensions      {dimensions};\n\n"
        + f"internalField   uniform {internal};\n\n"
        + "boundaryField\n{\n"
        + patches
        + "}\n"
    )


def _field_boundaries() -> dict[str, dict[str, str]]:
    zero_vector = "value uniform (0 0 0);"
    tiny = "value uniform 1e-8;"
    return {
        "U": {
            "tankWalls": "type noSlip;",
            "vent": f"type pressureInletOutletVelocity; {zero_vector}",
            "ambient": f"type pressureInletOutletVelocity; {zero_vector}",
        },
        "alpha.water": {
            "tankWalls": "type zeroGradient;",
            "vent": "type inletOutlet; inletValue uniform 0; value uniform 0;",
            "ambient": "type inletOutlet; inletValue uniform 0; value uniform 0;",
        },
        "p_rgh": {
            "tankWalls": "type fixedFluxPressure; value uniform 0;",
            "vent": "type prghPressure; p uniform 0; rho rho; value uniform 0;",
            "ambient": "type prghPressure; p uniform 0; rho rho; value uniform 0;",
        },
        "k": {
            "tankWalls": f"type kqRWallFunction; {tiny}",
            "vent": "type inletOutlet; inletValue uniform 1e-8; value uniform 1e-8;",
            "ambient": "type inletOutlet; inletValue uniform 1e-8; value uniform 1e-8;",
        },
        "epsilon": {
            "tankWalls": f"type epsilonWallFunction; {tiny}",
            "vent": "type inletOutlet; inletValue uniform 1e-8; value uniform 1e-8;",
            "ambient": "type inletOutlet; inletValue uniform 1e-8; value uniform 1e-8;",
        },
        "nut": {
            "tankWalls": "type nutkWallFunction; value uniform 0;",
            "vent": "type calculated; value uniform 0;",
            "ambient": "type calculated; value uniform 0;",
        },
    }


def _write_fields(case: Path, *, head_m: float) -> None:
    fields = _field_boundaries()
    dims = {
        "U": ("volVectorField", "[0 1 -1 0 0 0 0]", "(0 0 0)"),
        "alpha.water": ("volScalarField", "[0 0 0 0 0 0 0]", "0"),
        "p_rgh": ("volScalarField", "[1 -1 -2 0 0 0 0]", "0"),
        "k": ("volScalarField", "[0 2 -2 0 0 0 0]", "1e-8"),
        "epsilon": ("volScalarField", "[0 2 -3 0 0 0 0]", "1e-8"),
        "nut": ("volScalarField", "[0 2 -1 0 0 0 0]", "0"),
    }
    for name, (cls, dimensions, internal) in dims.items():
        patch_text = "".join(
            f"    {patch}\n    {{\n        {condition}\n    }}\n"
            for patch, condition in fields[name].items()
        )
        (case / "0" / name).write_text(
            _field(name, cls, dimensions, internal, patch_text), encoding="utf-8"
        )

    alpha_expr = (
        foam_header("setExprFieldsDict", location="system")
        + "expressions\n(\n"
        + "    alphaInit\n    {\n        field alpha.water;\n"
        + "        dimensions [0 0 0 0 0 0 0];\n"
        + f"        fieldMask #{{ (pos().z() >= 0) && (pos().z() < {head_m:.12g}) #}};\n"
        + "        expression #{ 1 #};\n    }\n"
        + "    pRghWater\n    {\n        field p_rgh;\n"
        + "        dimensions [1 -1 -2 0 0 0 0];\n"
        + f"        fieldMask #{{ (pos().z() >= 0) && (pos().z() < {head_m:.12g}) #}};\n"
        + f"        expression #{{ {WATER_RHO_KG_M3:g}*{GRAVITY_M_S2:g}*{head_m:.12g} #}};\n    }}\n"
        + "    pRghAir\n    {\n        field p_rgh;\n"
        + "        dimensions [1 -1 -2 0 0 0 0];\n"
        + f"        fieldMask #{{ (pos().z() < 0) || (pos().z() >= {head_m:.12g}) #}};\n"
        + f"        expression #{{ {AIR_RHO_KG_M3:g}*{GRAVITY_M_S2:g}*pos().z() #}};\n    }}\n"
        + ");\n"
    )
    (case / "system" / "setExprFieldsDict").write_text(alpha_expr, encoding="utf-8")


def _write_dictionaries(case: Path, *, horizon_s: float, aperture: str) -> None:
    for directory in (case / "0", case / "constant", case / "system"):
        directory.mkdir(parents=True, exist_ok=True)
    (case / "constant" / "g").write_text(
        foam_header("g", location="constant", cls="uniformDimensionedVectorField")
        + "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 -9.81);\n",
        encoding="utf-8",
    )
    (case / "constant" / "transportProperties").write_text(
        foam_header("transportProperties", location="constant")
        + "phases (water air);\n"
        + f"water {{ transportModel Newtonian; nu {WATER_NU_M2_S:g}; rho {WATER_RHO_KG_M3:g}; }}\n"
        + f"air {{ transportModel Newtonian; nu {AIR_NU_M2_S:g}; rho {AIR_RHO_KG_M3:g}; }}\n"
        + "sigma 0;\n",
        encoding="utf-8",
    )
    (case / "constant" / "turbulenceProperties").write_text(
        foam_header("turbulenceProperties", location="constant")
        + "density variable;\nsimulationType RAS;\nRAS { RASModel kEpsilon; turbulence on; printCoeffs on; }\n",
        encoding="utf-8",
    )
    # Shared transient controls; profile function samples the internal aperture
    # faceZone, while the native swept water flux is logged independently.
    (case / "system" / "controlDict").write_text(
        foam_header("controlDict", location="system")
        + "application interIsoFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\n"
        + f"endTime {_fmt(horizon_s)};\ndeltaT 1e-5;\n"
        + "adjustTimeStep yes;\nmaxCo 0.25;\nmaxAlphaCo 0.10;\nmaxDeltaT 1e-3;\n"
        + "writeControl adjustableRunTime;\nwriteInterval 0.025;\npurgeWrite 0;\n"
        + "writeFormat binary;\nwritePrecision 8;\nwriteCompression off;\n"
        + "timeFormat fixed;\ntimePrecision 6;\nrunTimeModifiable no;\n"
        + "functions\n{\n"
        + "    waterInventory\n    {\n        type volFieldValue;\n        libs (fieldFunctionObjects);\n"
        + "        fields (alpha.water);\n        operation volIntegrate;\n        writeFields false;\n"
        + "        executeControl timeStep;\n        executeInterval 1;\n        writeControl timeStep;\n        writeInterval 1;\n    }\n"
        + "    ambientFlux\n    {\n        type surfaceFieldValue;\n        libs (fieldFunctionObjects);\n        regionType patch;\n        name ambient;\n"
        + "        operation sum;\n        fields (phi alphaPhi_);\n        writeFields false;\n"
        + "        executeControl timeStep;\n        executeInterval 1;\n        writeControl timeStep;\n        writeInterval 1;\n    }\n"
        + "    ventFlux\n    {\n        type surfaceFieldValue;\n        libs (fieldFunctionObjects);\n        regionType patch;\n        name vent;\n"
        + "        operation sum;\n        fields (phi alphaPhi_);\n        writeFields false;\n"
        + "        executeControl timeStep;\n        executeInterval 1;\n        writeControl timeStep;\n        writeInterval 1;\n    }\n"
        + "    apertureFlux\n    {\n        type surfaceFieldValue;\n        libs (fieldFunctionObjects);\n        regionType faceZone;\n        name outletPlane;\n"
        + "        operation sum;\n        fields (phi alphaPhi_);\n        writeFields false;\n"
        + "        executeControl timeStep;\n        executeInterval 1;\n        writeControl timeStep;\n        writeInterval 1;\n    }\n"
        + "    apertureProfile\n    {\n        type surfaceFieldValue;\n        libs (fieldFunctionObjects);\n        regionType faceZone;\n        name outletPlane;\n"
        + "        operation areaAverage;\n        fields (alpha.water U);\n        writeFields true;\n"
        + "        surfaceFormat vtk;\n"
        + "        executeControl adjustableRunTime;\n        executeInterval 0.025;\n"
        + "        writeControl adjustableRunTime;\n        writeInterval 0.025;\n    }\n"
        + "}\n",
        encoding="utf-8",
    )
    (case / "system" / "fvSchemes").write_text(
        foam_header("fvSchemes", location="system")
        + "ddtSchemes { default Euler; }\n"
        + "gradSchemes { default Gauss linear; grad(k) Gauss linear; grad(epsilon) Gauss linear; }\n"
        + "divSchemes\n{\n    div(rhoPhi,U) Gauss limitedLinearV 1;\n"
        + "    div(rhoPhi,k) Gauss limitedLinear 1;\n    div(rhoPhi,epsilon) Gauss limitedLinear 1;\n"
        + "    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;\n}\n"
        + "laplacianSchemes { default Gauss linear corrected; }\n"
        + "interpolationSchemes { default linear; }\nsnGradSchemes { default corrected; }\n"
        + "fluxRequired { default no; p_rgh; pcorr; alpha.water; }\n",
        encoding="utf-8",
    )
    (case / "system" / "fvSolution").write_text(
        foam_header("fvSolution", location="system")
        + 'solvers\n{\n    "alpha.water.*" { isoFaceTol 1e-6; surfCellTol 1e-6; nAlphaBounds 3; snapTol 1e-12; clip true; reconstructionScheme isoAlpha; writeFields true; nAlphaSubCycles 1; cAlpha 1; }\n'
        + '    "pcorr.*" { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0; }\n'
        + "    p_rgh { solver GAMG; smoother DICGaussSeidel; tolerance 1e-9; relTol 0.05; }\n"
        + "    p_rghFinal { $p_rgh; tolerance 1e-9; relTol 0; }\n"
        + "    U { solver PBiCGStab; preconditioner DILU; tolerance 1e-6; relTol 0; }\n"
        + '    "(k|epsilon)" { solver smoothSolver; smoother GaussSeidel; tolerance 1e-8; relTol 0.1; }\n'
        + '    "(k|epsilon)Final" { solver smoothSolver; smoother GaussSeidel; tolerance 1e-8; relTol 0; }\n'
        + "}\nPIMPLE { momentumPredictor no; nCorrectors 3; nOuterCorrectors 1; nNonOrthogonalCorrectors 0; pRefCell 0; pRefValue 0; }\n",
        encoding="utf-8",
    )
    (case / "system" / "decomposeParDict").write_text(
        foam_header("decomposeParDict", location="system")
        + "numberOfSubdomains 20;\nmethod scotch;\n",
        encoding="utf-8",
    )
    (case / "system" / "topoSetDict").write_text(_toposet_dict(aperture), encoding="utf-8")


def prepare_case(
    output_dir: Path,
    *,
    aperture: str = "large",
    head_m: float = HEAD_M,
    horizon_s: float = DEFAULT_HORIZON_S,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_dir}")
    if not math.isfinite(head_m) or not 0.05 <= head_m < TANK_HEIGHT_M:
        raise ValueError(f"head_m must be finite and in [0.05, {TANK_HEIGHT_M})")
    if not math.isfinite(horizon_s) or not 0.025 <= horizon_s <= 5.0:
        raise ValueError("horizon_s must be finite and in [0.025, 5.0]")
    outlet = aperture_parameters(aperture)
    mesh_text, mesh_data = rounded_bottom_mesh(aperture)
    output_dir.mkdir(parents=True)
    _write_dictionaries(output_dir, horizon_s=horizon_s, aperture=aperture)
    _write_fields(output_dir, head_m=head_m)
    (output_dir / "system" / "blockMeshDict").write_text(mesh_text, encoding="utf-8")

    # Analytic volume is only a planning estimate; authoritative initial water
    # inventory is the post-setExprFields volIntegrate(alpha.water) result.
    circle_z = float(mesh_data["curvature"]["circle_center_xz_m"][1])
    circle_r = float(mesh_data["curvature"]["circle_radius_m"])
    upper = min(head_m, TANK_HEIGHT_M)
    if upper <= circle_z:
        # Circular-segment area below the level, less the omitted outlet chord.
        q = max(-1.0, min(1.0, (circle_z - upper) / circle_r))
        segment_area = circle_r**2 * (math.acos(q) - q * math.sqrt(max(0.0, 1.0 - q * q)))
        water_area = segment_area
    else:
        semi_area = math.pi * circle_r**2 / 2.0
        water_area = semi_area + (upper - circle_z) * (2.0 * RADIUS_M)
    analytic_volume = water_area * TANK_LENGTH_M
    inventory = {
        "schema_version": 1,
        "case_kind": "gravity-fed upstream tank-discharge VOF pilot",
        "solver": "interIsoFoam",
        "openfoam_image": PINNED_IMAGE,
        "openfoam_image_id": PINNED_IMAGE_ID,
        "horizon_s": horizon_s,
        "intended_resources": {"ranks": 20, "memory_gib": 96, "wall_budget_minutes": 20},
        "coordinates": {
            "x": "transverse",
            "y": "streamwise",
            "z": "upward",
            "gravity_m_s2": [0, 0, -GRAVITY_M_S2],
        },
        "physics": {
            "water_rho_kg_m3": WATER_RHO_KG_M3,
            "water_nu_m2_s": WATER_NU_M2_S,
            "air_rho_kg_m3": AIR_RHO_KG_M3,
            "air_nu_m2_s": AIR_NU_M2_S,
            "sigma_n_m": 0.0,
            "sigma_status": "set to zero to match paper's omitted surface-tension term; applicability to tank startup is unvalidated",
            "turbulence": "standard k-epsilon RAS from paper; small positive initialization floors only, no imposed turbulent inlet",
            "initial_velocity_m_s": [0, 0, 0],
            "source_history": "none; Fig. 4 is only an external post-run comparison target",
        },
        "geometry": {
            **mesh_data,
            "radius_status": "inferred nominal radius 0.85 m from half of the Fig.2(b) 1.7 m internal width; circular arc is truncated at |x|=0.80 m to avoid a vertical-tangent mesh singularity",
            "length_status": "4.44 m lower-section span from Fig.2(c), used as assumed extrusion length; paper tank overall length is 7.46 m",
            "height_status": "1.5 m tank height from Fig.2(b)",
            "outlet_status": str(outlet["basis"]),
            "external_air": "ambient wedge below internal outlet plane; no aircraft belly and no 50 m/s crossflow in this source-generation pilot",
            "outlet_normal": "native faceZone is oriented from tank-side cells into the downstream air wedge; expected direction is -z",
        },
        "initial_condition": {
            "head_m": head_m,
            "head_status": "provisional assumption; no Dash-8 water-test fill depth/head is reported",
            "head_definition": "vertical distance from outlet sampling plane z=0 to initially horizontal free surface z=head_m",
            "vent": "tank top at z=1.5 m open to atmospheric pressure; this is an assumed vent path",
            "analytic_initial_water_volume_estimate_m3": analytic_volume,
            "actual_initial_water_volume_m3": None,
            "actual_initial_water_volume_method": "postProcess volFieldValue volIntegrate(alpha.water) after setExprFields on the built mesh; fill case metadata from that output",
            "initial_p_rgh": "setExprFields initializes hydrostatic water p_rgh below the sharp alpha-water free surface; air is initialized at constant physical atmospheric pressure p=0. The ambient/vent prghPressure boundaries hold that atmospheric reference, an explicit short-pilot approximation rather than a hydrostatic air column",
        },
        "diagnostics": {
            "native_flux": "surfaceFieldValue sum(phi,alphaPhi_) on internal outletPlane and signed sums on ambient/vent patches; aperture flux is tank-to-plenum transfer, patch sums use their outward boundary normals and separately measure escaped water",
            "outlet_flux_orientation": "setsToFaceZone oriented outletPlane away from tankCells; pinned-v2512 surfaceFieldValue maps faceZone flipMap for oriented surface fields, and the generated faceZone flipMap is all false, so owner-oriented flux is tank-outward; geometric plane outward is -z",
            "mass_closure": "compare actual initial/current alpha.water volume with time-integrated signed ambient+vent alphaPhi_ escape; do not add the cumulative outletPlane transfer to stored inventory",
            "velocity": "faceZone area averages of alpha.water and U plus VTK surfaceFieldValue owner/neighbour-interpolated cell values at outlet faces every 0.025 s; these are not native fluxes. Distinguish geometric Q/S, alpha-area mean, and max",
            "mass_ledger": "initial tank water = remaining tank water + downstream water + boundary escape; aperture alphaPhi_ is transfer, not stored mass",
            "times": "3-D fields every 0.025 s for the short 0.6 s pilot, including .025/.05/.075/.1 startup snapshots; all native signed fluxes every time step and face-resolved outlet alpha/U VTK plus area means every 0.025 s",
        },
        "source_provenance": {
            "citation": "Calbrix et al. 2023, International Journal of Wildland Fire 32(11), 1515-1528, DOI 10.1071/WF22147",
            "tank_dims": "local PDF p.4 / journal p.1518, Fig.2(b-c); drawing dimensions, not a full CAD specification",
            "opening_location": "local PDF p.5 / journal p.1519, Fig.3(b)",
            "figure4": "local PDF p.5 / journal p.1519, used only for post-run comparison; paper methods define mean U=Q/S but caption/results call Fig.4 maximum velocity",
            "parameter_classes_and_locations": {
                "water_rho_nu": "reported: PDF p.4 / journal p.1518, Domains and meshes",
                "tank_internal_width_height_lower_span": "reported drawing labels: PDF p.4 / journal p.1518, Fig.2(b-c); extrusion length and bowl radius are inferred/assumed",
                "outlet_dimensions_and_area": "not numerically reported: PDF p.3 / journal p.1517 tank geometry and PDF p.4-5 / journal p.1518-1519 Figs.2-3; 4.44x0.30 m / 1.332 m2 retained as the project's assumed nearfield opening",
                "head_and_initial_fill": "not reported: PDF p.3 / journal p.1517 tank geometry; 1.0 m head is provisional and referenced to z=0 outlet plane",
                "air_rho_nu_and_gravity_magnitude": "not numerically reported: PDF p.3 / journal p.1517 Eqs.(1)-(3); ambient air and g=9.81 m/s2 are assumptions",
                "surface_tension": "paper omits capillary term in PDF p.3 / journal p.1517 Eq.(3) due resolution relative to capillary length; sigma=0 follows that model statement",
                "turbulence": "standard k-epsilon RANS reported: PDF p.3 / journal p.1517 Numerical method; initialization floors and all boundary turbulence values are assumptions",
                "later_8p840_m3": "PDF p.11 / journal p.1525 Table 5 is Fire-Trol 931 field-drop volume and is not assigned as water-test inventory",
            },
            "source_pdf_sha256": sha256_file(SOURCE_PDF),
            "source_record_sha256": sha256_file(SOURCE_RECORD),
            "fig4_digitization_sha256": sha256_file(HISTORY_CSV),
        },
        "formal_gate": False,
    }
    (output_dir / "case-inputs.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return inventory


def record_mesh_verification(case_dir: Path) -> dict[str, Any]:
    """Record actual blockMesh/checkMesh/faceZone/alpha-volume readbacks."""
    case_dir = Path(case_dir)
    inputs_path = case_dir / "case-inputs.json"
    record = json.loads(inputs_path.read_text(encoding="utf-8"))
    required_logs = {
        name: case_dir / f"log.{name}"
        for name in ("blockMesh", "checkMesh", "topoSet", "postprocess-alpha")
    }
    missing = [str(path) for path in required_logs.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"mesh verification logs are missing: {missing}")
    log_texts = {
        name: path.read_text(encoding="utf-8", errors="replace")
        for name, path in required_logs.items()
    }

    cell_match = re.search(r"(?m)^\s*nCells:\s*(\d+)\s*$", log_texts["blockMesh"])
    if not cell_match:
        raise ValueError("blockMesh log does not report nCells")
    cells = int(cell_match.group(1))
    expected_cells = int(record["geometry"]["mesh_cells_expected"])
    if cells != expected_cells:
        raise ValueError(
            f"blockMesh has {cells} cells but generated metadata expected {expected_cells}"
        )

    checkmesh_ok = "Mesh OK." in log_texts["checkMesh"] and not re.search(
        r"(?m)^\s*Failed\s+\d+\s+mesh checks?\.", log_texts["checkMesh"]
    )
    if not checkmesh_ok:
        raise ValueError("strict checkMesh did not print Mesh OK. with no failed mesh checks")

    face_count_match = re.search(r"faceZoneSet outletPlane now size (\d+)", log_texts["topoSet"])
    face_area_matches = re.findall(
        r"total faces\s*=\s*(\d+).*?total area\s*=\s*([0-9.eE+-]+)",
        log_texts["postprocess-alpha"],
        re.S,
    )
    volume_dir = case_dir / "postProcessing/waterInventory/0.000000"
    volume_candidates = [
        volume_dir / "volFieldValue_0.000000.dat",
        volume_dir / "volFieldValue.dat",
    ]
    volume_path = next(
        (path for path in volume_candidates if path.is_file()), volume_candidates[-1]
    )
    volume_text = volume_path.read_text(encoding="utf-8") if volume_path.is_file() else ""
    volume_match = re.search(r"(?m)^0\.000000\s+([0-9.eE+-]+)\s*$", volume_text)
    stdout_volume_match = re.search(
        r"volIntegrate\(region0\) of alpha\.water = ([0-9.eE+-]+)",
        log_texts["postprocess-alpha"],
    )
    if not face_count_match or not face_area_matches or not volume_match or not stdout_volume_match:
        raise ValueError("postprocess logs lack outlet face/area or actual alpha-water volume")
    face_count = int(face_count_match.group(1))
    matching_areas = [
        float(area_text)
        for count_text, area_text in face_area_matches
        if int(count_text) == face_count
    ]
    if not matching_areas:
        raise ValueError("postProcess did not report the native outlet faceZone area")
    area = matching_areas[-1]
    water_volume = float(volume_match.group(1))
    if not math.isclose(water_volume, float(stdout_volume_match.group(1)), rel_tol=1e-8):
        raise ValueError("volFieldValue output file disagrees with postProcess stdout")
    if not math.isclose(area, float(record["geometry"]["aperture"]["area_m2"]), rel_tol=1e-8):
        raise ValueError("native outlet faceZone area does not match declared geometric aperture")

    record["geometry"]["mesh_cells_actual"] = cells
    record["geometry"]["outlet_face_count_actual"] = face_count
    record["geometry"]["outlet_facezone_area_actual_m2"] = area
    patch_matches = re.findall(
        r"patch\s+\d+\s+\(start:\s*\d+\s+size:\s*(\d+)\)\s+name:\s*([A-Za-z_][A-Za-z_0-9]*)",
        log_texts["blockMesh"],
    )
    if not patch_matches:
        raise ValueError("blockMesh log does not report actual mesh patch face counts")
    record["geometry"]["mesh_patch_face_counts"] = {
        name: int(count) for count, name in patch_matches
    }
    record["geometry"]["strict_checkmesh_status"] = "Mesh OK."
    record["initial_condition"]["actual_initial_water_volume_m3"] = water_volume
    record["initial_condition"]["actual_initial_water_volume_method"] = (
        "pinned v2512 postProcess volFieldValue volIntegrate(alpha.water) after setExprFields; "
        "recorded from the native mesh at time 0"
    )
    record["mesh_build_verification"] = {
        "cell_count_match": True,
        "strict_checkmesh_ok": True,
        "facezone_away_from_tank_cellset": True,
        "outlet_faces_match": True,
        "outlet_area_match": True,
        "actual_initial_water_volume_m3": water_volume,
        "logs_sha256": {name: sha256_file(path) for name, path in required_logs.items()},
        "initial_inventory_report_sha256": sha256_file(volume_path),
    }
    inputs_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--aperture", choices=("large", "small"), default="large")
    parser.add_argument("--head-m", type=float, default=HEAD_M)
    parser.add_argument("--horizon-s", type=float, default=DEFAULT_HORIZON_S)
    parser.add_argument(
        "--record-mesh-verification",
        action="store_true",
        help="update an existing generated case-inputs.json from completed pinned mesh/postProcess logs",
    )
    args = parser.parse_args()
    if args.record_mesh_verification:
        record = record_mesh_verification(args.output_dir)
    else:
        record = prepare_case(
            args.output_dir,
            aperture=args.aperture,
            head_m=args.head_m,
            horizon_s=args.horizon_s,
        )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "aperture_area_m2": record["geometry"]["aperture"]["area_m2"],
                "expected_mesh_cells": record["geometry"]["mesh_cells_expected"],
                "head_m": record["initial_condition"]["head_m"],
                "horizon_s": record["horizon_s"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
