#!/usr/bin/env python3
"""Generate the provisional I4F two-tank/four-outlet BREP geometry.

This reconstructs a fluid-envelope preview and separate divider candidates.
It is not manufacturing CAD, a CFD mesh, or a statement of measured internal
dimensions. All lengths are SI metres.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from matplotlib.patches import Circle, Rectangle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Fuse, BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Transform,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe, BRepOffsetAPI_ThruSections
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
from OCP.collections import Array1_gp_Pnt, HSequence_TopoDS_Shape
from OCP.Geom import Geom_BezierCurve
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.STEPControl import (
    STEPControl_AsIs,
    STEPControl_Controller,
    STEPControl_Reader,
    STEPControl_Writer,
)
from OCP.StlAPI import StlAPI_Writer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound

# Fixed topology and centerline stations retained from the reviewed
# two-tank/four-mouth reconstruction. The dimensions are assumptions unless
# stated as user-confirmed in the project hardware notes.
TANK_Y = (-0.550, 0.550)
TANK_Z = 1.250
PIPE_START_X_M = 0.250
PIPE_ID_M = 0.300
VALVE_D_M = 0.300
PIPE_RUN_Z = 0.500
MOUTH_W_M = 1.000
MOUTH_H_M = 0.150
POST_RISE_STRAIGHT_DEFAULT_M = 0.000
TRANSITION_AND_MOUTH_DEFAULT_M = 1.000
REFERENCE_TRANSITION_AND_MOUTH_LENGTH_M = 1.800
LAMELLA_START_OFFSET_M = 0.750
TRANSITION_XMID_OFFSET_M = 0.800
TRANSITION_X1_OFFSET_M = 1.500
PIPE_OVERLAP_OFFSET_M = 0.200
PIPE_TRANSITION_JOIN_MODES = ("legacy-overlap", "flush-at-inlet")
BREP_UNION_VOLUME_REL_TOLERANCE = 1e-5
VALVE_X_M = (2.100, 2.400)
BRANCHES = (
    {
        "name": "lower",
        "port_y_offset_m": -0.270,
        "pipe_lateral_offset_m": -0.200,
        "mouth_z_m": 0.650,
    },
    {"name": "upper", "port_y_offset_m": 0.370, "pipe_lateral_offset_m": 0.200, "mouth_z_m": 0.900},
)
BEND_X_M = (2.600, 3.000, 3.400, 3.800)


@dataclass(frozen=True)
class DownstreamStations:
    """Stations after the fixed rise bend, without mutating module globals."""

    transition_inlet_x_m: float
    lamella_start_x_m: float
    transition_intermediate_x_m: float
    transition_end_x_m: float
    mouth_x_m: float
    pipe_overlap_end_x_m: float
    scale_from_default: float


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def solids(shape) -> list:
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    result = []
    while explorer.More():
        result.append(explorer.Current())
        explorer.Next()
    return result


def volume(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def surface_area(shape) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return float(props.Mass())


def bounds(shape) -> list[float]:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    return [
        float(value)
        for value in (
            box.GetXMin(),
            box.GetXMax(),
            box.GetYMin(),
            box.GetYMax(),
            box.GetZMin(),
            box.GetZMax(),
        )
    ]


def compound(shapes) -> TopoDS_Compound:
    from OCP.BRep import BRep_Builder

    result = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def require_common(a, b):
    operation = BRepAlgoAPI_Common(a, b)
    operation.Build()
    if not operation.IsDone():
        raise RuntimeError("OpenCascade BREP common operation failed")
    return operation.Shape()


def require_fuse(a, b):
    """Fuse touching/overlapping BREP solids and require one valid fluid solid."""
    operation = BRepAlgoAPI_Fuse(a, b)
    operation.Build()
    if not operation.IsDone():
        raise RuntimeError("OpenCascade BREP pipe/transition union failed")
    shape = operation.Shape()
    if len(solids(shape)) != 1 or not BRepCheck_Analyzer(shape).IsValid():
        raise RuntimeError(
            "Pipe/transition union is not one valid connected solid: "
            f"solids={len(solids(shape))}, valid={BRepCheck_Analyzer(shape).IsValid()}"
        )
    return shape


def downstream_stations(post_rise_straight_m: float, transition_and_mouth_length_m: float):
    """Scale every original downstream station from the fixed bend endpoint."""
    scale = transition_and_mouth_length_m / REFERENCE_TRANSITION_AND_MOUTH_LENGTH_M
    inlet = BEND_X_M[-1] + post_rise_straight_m
    return DownstreamStations(
        transition_inlet_x_m=inlet,
        lamella_start_x_m=inlet + LAMELLA_START_OFFSET_M * scale,
        transition_intermediate_x_m=inlet + TRANSITION_XMID_OFFSET_M * scale,
        transition_end_x_m=inlet + TRANSITION_X1_OFFSET_M * scale,
        mouth_x_m=inlet + REFERENCE_TRANSITION_AND_MOUTH_LENGTH_M * scale,
        pipe_overlap_end_x_m=inlet + PIPE_OVERLAP_OFFSET_M * scale,
        scale_from_default=scale,
    )


def make_circle_wire(center, normal, radius: float):
    circle = gp_Circ(gp_Ax2(gp_Pnt(*center), gp_Dir(*normal)), radius)
    return BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(circle).Edge()).Wire()


def make_rect_wire(x: float, y: float, z: float, width_y: float, height_z: float):
    points = [
        gp_Pnt(x, y - width_y / 2, z - height_z / 2),
        gp_Pnt(x, y + width_y / 2, z - height_z / 2),
        gp_Pnt(x, y + width_y / 2, z + height_z / 2),
        gp_Pnt(x, y - width_y / 2, z + height_z / 2),
    ]
    wire = BRepBuilderAPI_MakeWire()
    for first, second in zip(points, points[1:] + points[:1]):
        wire.Add(BRepBuilderAPI_MakeEdge(first, second).Edge())
    if not wire.IsDone():
        raise RuntimeError("Could not construct rectangular section wire")
    return wire.Wire()


def make_bezier_edge(points):
    poles = Array1_gp_Pnt(1, len(points))
    for index, xyz in enumerate(points, start=1):
        poles.SetValue(index, gp_Pnt(*map(float, xyz)))
    return BRepBuilderAPI_MakeEdge(Geom_BezierCurve(poles)).Edge()


def branch_pipe(
    y_tank: float,
    branch: dict,
    tank_diameter_m: float,
    pipe_diameter_m: float,
    stations: DownstreamStations,
    pipe_transition_join: str,
):
    radius = pipe_diameter_m / 2
    y_pipe = y_tank + branch["pipe_lateral_offset_m"]
    z_out = branch["mouth_z_m"]
    port_offset = branch["port_y_offset_m"]
    tank_r = tank_diameter_m / 2
    z_port = TANK_Z - math.sqrt(tank_r**2 - port_offset**2)
    p0 = [PIPE_START_X_M, y_tank + 0.30 * port_offset, TANK_Z - 0.100]
    p1 = [0.550, y_tank + port_offset, z_port]
    p2 = [0.800, y_pipe, PIPE_RUN_Z]
    p3 = [1.300, y_pipe, PIPE_RUN_Z]
    q0, q1, q2, q3 = [
        [BEND_X_M[0], y_pipe, PIPE_RUN_Z],
        [BEND_X_M[1], y_pipe, PIPE_RUN_Z],
        [BEND_X_M[2], y_pipe, z_out],
        [BEND_X_M[3], y_pipe, z_out],
    ]
    spine = BRepBuilderAPI_MakeWire()
    spine.Add(make_bezier_edge([p0, p1, p2, p3]))
    spine.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(*p3), gp_Pnt(*q0)).Edge())
    spine.Add(make_bezier_edge([q0, q1, q2, q3]))
    if pipe_transition_join == "legacy-overlap":
        pipe_end_x = stations.pipe_overlap_end_x_m
    elif pipe_transition_join == "flush-at-inlet":
        pipe_end_x = stations.transition_inlet_x_m
    else:
        raise ValueError(f"Unsupported pipe/transition join mode: {pipe_transition_join}")
    if pipe_end_x > q3[0] + 1e-12:
        spine.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(*q3), gp_Pnt(pipe_end_x, y_pipe, z_out)).Edge())
    elif pipe_end_x < q3[0] - 1e-12:
        raise ValueError("Pipe end must not lie upstream of the fixed rise-bend endpoint")
    if not spine.IsDone():
        raise RuntimeError("Could not form connected branch centerline")
    tangent = np.asarray(p1, dtype=float) - np.asarray(p0, dtype=float)
    tangent /= np.linalg.norm(tangent)
    profile = BRepBuilderAPI_MakeFace(make_circle_wire(p0, tangent.tolist(), radius)).Face()
    pipe = BRepOffsetAPI_MakePipe(spine.Wire(), profile)
    if not pipe.IsDone() or len(solids(pipe.Shape())) != 1:
        raise RuntimeError("Could not sweep a single connected branch pipe")
    return pipe.Shape(), y_pipe


def make_tank(y_tank: float, radius: float, length: float, tank_axis: str):
    """Build the same flat-ended vessel with an explicit provisional axis."""
    if tank_axis == "horizontal":
        base = gp_Pnt(0.0, y_tank, TANK_Z)
        direction = gp_Dir(1, 0, 0)
        axis_start = 0.0
        placement = "base at x=0; +X axis through (y_tank,TANK_Z)"
    elif tank_axis == "vertical":
        base = gp_Pnt(PIPE_START_X_M, y_tank, TANK_Z - radius)
        direction = gp_Dir(0, 0, 1)
        axis_start = TANK_Z - radius
        placement = (
            "bottom at TANK_Z - tank radius; +Z axis through the existing internal pipe-start "
            "x=0.250 m and tank center y"
        )
    else:
        raise ValueError(f"Unsupported tank axis: {tank_axis}")
    shape = BRepPrimAPI_MakeCylinder(gp_Ax2(base, direction), radius, length).Shape()
    axis_end = axis_start + length
    return shape, {
        "axis_direction_xyz": [1, 0, 0] if tank_axis == "horizontal" else [0, 0, 1],
        "axis_start_coordinate_m": axis_start,
        "axis_end_coordinate_m": axis_end,
        "base_center_xyz_m": [float(base.X()), float(base.Y()), float(base.Z())],
        "placement_convention": placement,
    }


def pipe_start_section_clearance(
    y_tank: float, branch: dict, tank_radius: float, tank_length: float, tank_axis: str
) -> dict:
    """Conservative check that the complete circular pipe start fits in its own tank."""
    p0 = np.asarray(
        [PIPE_START_X_M, y_tank + 0.30 * branch["port_y_offset_m"], TANK_Z - 0.100],
        dtype=float,
    )
    pipe_radius = PIPE_ID_M / 2
    if tank_axis == "horizontal":
        radial_center = math.hypot(p0[1] - y_tank, p0[2] - TANK_Z)
        axial_coordinate = p0[0]
        axis_min, axis_max = 0.0, tank_length
    else:
        bottom = TANK_Z - tank_radius
        radial_center = math.hypot(p0[0] - PIPE_START_X_M, p0[1] - y_tank)
        axial_coordinate = p0[2]
        axis_min, axis_max = bottom, bottom + tank_length
    side_clearance = float(tank_radius - radial_center - pipe_radius)
    negative_end_clearance = float(axial_coordinate - axis_min - pipe_radius)
    positive_end_clearance = float(axis_max - axial_coordinate - pipe_radius)
    minimum_clearance = float(min(side_clearance, negative_end_clearance, positive_end_clearance))
    return {
        "pipe_start_center_xyz_m": list(map(float, p0)),
        "pipe_start_radius_m": pipe_radius,
        "tank_radial_center_distance_m": radial_center,
        "tank_side_clearance_m": side_clearance,
        "negative_axis_end_clearance_m": negative_end_clearance,
        "positive_axis_end_clearance_m": positive_end_clearance,
        "minimum_conservative_full_start_clearance_m": minimum_clearance,
        "entire_start_section_inside_own_tank": bool(minimum_clearance >= -1e-10),
    }


def aligned_ruled_transition(
    y_pipe: float,
    y_mouth: float,
    z: float,
    intermediate_width_m: float,
    stations: DownstreamStations,
    pipe_diameter_m: float,
):
    """Four-arc ruled circle-to-rectangle loft used by the approved geometry."""
    circle = gp_Circ(
        gp_Ax2(
            gp_Pnt(stations.transition_inlet_x_m, y_pipe, z),
            gp_Dir(1, 0, 0),
            gp_Dir(0, 1, 0),
        ),
        pipe_diameter_m / 2,
    )
    round_wire = BRepBuilderAPI_MakeWire()
    angles = (-3 * math.pi / 4, -math.pi / 4, math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4)
    for a0, a1 in zip(angles, angles[1:]):
        round_wire.Add(BRepBuilderAPI_MakeEdge(circle, a0, a1).Edge())
    if not round_wire.IsDone():
        raise RuntimeError("Could not construct four-arc round transition profile")
    loft = BRepOffsetAPI_ThruSections(True, True, 1e-5)
    loft.AddWire(round_wire.Wire())
    loft.AddWire(
        make_rect_wire(
            stations.transition_intermediate_x_m, y_pipe, z, intermediate_width_m, MOUTH_H_M
        )
    )
    loft.AddWire(make_rect_wire(stations.transition_end_x_m, y_mouth, z, MOUTH_W_M, MOUTH_H_M))
    loft.AddWire(make_rect_wire(stations.mouth_x_m, y_mouth, z, MOUTH_W_M, MOUTH_H_M))
    loft.Build()
    if not loft.IsDone() or len(solids(loft.Shape())) != 1:
        raise RuntimeError("Aligned ruled transition did not form one solid")
    if not BRepCheck_Analyzer(loft.Shape()).IsValid():
        raise RuntimeError("Aligned ruled transition failed BREP validity")
    return loft.Shape()


def equal_gap_centers(width: float, count: int, thickness: float) -> list[float]:
    clear = (width - count * thickness) / (count + 1)
    if clear <= 0:
        raise ValueError("Divider thickness leaves no clear passages")
    return [-width / 2 + (index + 1) * clear + (index + 0.5) * thickness for index in range(count)]


def plate_wire(x: float, y: float, z: float, thickness: float, height: float):
    return make_rect_wire(x, y, z, thickness, height)


def make_tall_plate(rows, thickness: float):
    loft = BRepOffsetAPI_ThruSections(True, True, 1e-5)
    for x, y, z in rows:
        loft.AddWire(plate_wire(x, y, z, thickness, 0.300))
    loft.Build()
    if not loft.IsDone() or len(solids(loft.Shape())) != 1:
        raise RuntimeError("Divider trimming stock did not form one solid")
    if not BRepCheck_Analyzer(loft.Shape()).IsValid():
        raise RuntimeError("Divider trimming stock failed BREP validity")
    return loft.Shape()


def make_oriented_plate_wire(center, tangent_xy, thickness: float, height: float):
    """Return a vertical rectangular plate section normal to a horizontal tangent."""
    x, y, z = map(float, center)
    tx, ty = map(float, tangent_xy)
    norm = math.hypot(tx, ty)
    if norm <= 0:
        raise ValueError("Plate tangent must have positive length")
    tx, ty = tx / norm, ty / norm
    nx, ny = -ty, tx
    half_t = thickness / 2
    half_h = height / 2
    points = [
        gp_Pnt(x + nx * half_t, y + ny * half_t, z - half_h),
        gp_Pnt(x - nx * half_t, y - ny * half_t, z - half_h),
        gp_Pnt(x - nx * half_t, y - ny * half_t, z + half_h),
        gp_Pnt(x + nx * half_t, y + ny * half_t, z + half_h),
    ]
    wire = BRepBuilderAPI_MakeWire()
    for first, second in zip(points, points[1:] + points[:1]):
        wire.Add(BRepBuilderAPI_MakeEdge(first, second).Edge())
    if not wire.IsDone():
        raise RuntimeError("Could not construct oriented rounded-divider body section")
    return wire.Wire()


def make_semicircular_nose(center, tangent_xy, radius: float, height: float):
    """Build a closed half-cylinder cap, tangent to the rounded-divider body."""
    cx, cy, zc = map(float, center)
    tx, ty = map(float, tangent_xy)
    norm = math.hypot(tx, ty)
    if norm <= 0:
        raise ValueError("Rounded-divider nose tangent must have positive length")
    tx, ty = tx / norm, ty / norm
    normal = (-ty, tx)
    z0 = zc - height / 2
    axis = gp_Ax2(gp_Pnt(cx, cy, z0), gp_Dir(0, 0, 1), gp_Dir(tx, ty, 0))
    circle = gp_Circ(axis, radius)
    # The arc runs from the positive transverse side, around the upstream tip,
    # to the negative transverse side. Closing with the diameter makes a
    # genuinely closed semicircular prism, rather than a rounded display edge.
    arc = BRepBuilderAPI_MakeEdge(circle, math.pi / 2, 3 * math.pi / 2).Edge()
    side_plus = gp_Pnt(cx + radius * normal[0], cy + radius * normal[1], z0)
    side_minus = gp_Pnt(cx - radius * normal[0], cy - radius * normal[1], z0)
    diameter = BRepBuilderAPI_MakeEdge(side_minus, side_plus).Edge()
    wire = BRepBuilderAPI_MakeWire()
    wire.Add(arc)
    wire.Add(diameter)
    if not wire.IsDone():
        raise RuntimeError("Could not construct rounded-divider semicircle wire")
    face = BRepBuilderAPI_MakeFace(wire.Wire(), True)
    if not face.IsDone() or not BRepCheck_Analyzer(face.Face()).IsValid():
        raise RuntimeError("Rounded-divider nose profile is not a valid closed face")
    prism = BRepPrimAPI_MakePrism(face.Face(), gp_Vec(0, 0, height), True)
    if not prism.IsDone() or len(solids(prism.Shape())) != 1:
        raise RuntimeError("Rounded-divider nose did not form one closed solid")
    if not BRepCheck_Analyzer(prism.Shape()).IsValid():
        raise RuntimeError("Rounded-divider nose solid failed BREP validity")
    return prism.Shape()


def make_rounded_tall_plate(rows, thickness: float, nose_radius: float):
    """Build a finite-thickness plate with a semicircular leading nose.

    The rounded tip preserves the first centerline point: its circle center is
    moved one nose radius down the local first-segment tangent, and its upstream
    arc tip lands at the original start point. The downstream loft begins at
    the tangent plane through that circle center.
    """
    if len(rows) < 2:
        raise ValueError("A rounded divider needs at least two centerline stations")
    x0, y0, z0 = map(float, rows[0])
    x1, y1, _ = map(float, rows[1])
    dx, dy = x1 - x0, y1 - y0
    distance = math.hypot(dx, dy)
    if distance <= 0 or dx <= 0:
        raise ValueError("Rounded-divider leading tangent must advance downstream")
    segment_tangents = []
    for first, second in zip(rows, rows[1:]):
        sx, sy = float(second[0]) - float(first[0]), float(second[1]) - float(first[1])
        segment_length = math.hypot(sx, sy)
        if segment_length <= 0 or sx <= 0:
            raise ValueError("Rounded-divider body centerline must advance monotonically")
        segment_tangents.append((sx / segment_length, sy / segment_length))
    station_tangents = []
    for index in range(len(rows)):
        if index == 0:
            station_tangents.append(segment_tangents[0])
        elif index == len(rows) - 1:
            station_tangents.append(segment_tangents[-1])
        else:
            tx = segment_tangents[index - 1][0] + segment_tangents[index][0]
            ty = segment_tangents[index - 1][1] + segment_tangents[index][1]
            tangent_length = math.hypot(tx, ty)
            if tangent_length <= 0:
                raise ValueError("Rounded-divider local station tangent is undefined")
            station_tangents.append((tx / tangent_length, ty / tangent_length))
    tangent = station_tangents[0]
    center = (x0 + nose_radius * tangent[0], y0 + nose_radius * tangent[1], z0)
    body_centers = [center, *[tuple(map(float, row)) for row in rows[1:]]]

    loft = BRepOffsetAPI_ThruSections(True, True, 1e-5)
    for section_center, section_tangent in zip(body_centers, station_tangents):
        loft.AddWire(make_oriented_plate_wire(section_center, section_tangent, thickness, 0.300))
    loft.Build()
    if not loft.IsDone() or len(solids(loft.Shape())) != 1:
        raise RuntimeError("Rounded-divider body loft did not form one solid")
    body = loft.Shape()
    if not BRepCheck_Analyzer(body).IsValid():
        raise RuntimeError("Rounded-divider body loft failed BREP validity")
    nose = make_semicircular_nose(center, tangent, nose_radius, 0.300)
    rounded = require_fuse(body, nose)
    if len(solids(rounded)) != 1 or not BRepCheck_Analyzer(rounded).IsValid():
        raise RuntimeError("Fused rounded-divider body/nose is not one valid solid")
    return rounded, {
        "leading_tip_xyz_m": [x0, y0, z0],
        "semicircle_center_xyz_m": list(center),
        "tangent_xy_unit": list(tangent),
        "body_station_tangents_xy": [list(value) for value in station_tangents],
        "normal_section_thickness_m": [thickness] * len(rows),
        "radius_m": nose_radius,
    }


def make_midface(row0, row1, half_height: float):
    x0, y0, z0 = row0
    x1, y1, z1 = row1
    points = [
        gp_Pnt(x0, y0, z0 - half_height),
        gp_Pnt(x1, y1, z1 - half_height),
        gp_Pnt(x1, y1, z1 + half_height),
        gp_Pnt(x0, y0, z0 + half_height),
    ]
    wire = BRepBuilderAPI_MakeWire()
    for index in range(4):
        wire.Add(BRepBuilderAPI_MakeEdge(points[index], points[(index + 1) % 4]).Edge())
    face = BRepBuilderAPI_MakeFace(wire.Wire(), True)
    if not face.IsDone() or not BRepCheck_Analyzer(face.Face()).IsValid():
        raise RuntimeError("Divider mid-surface segment failed BREP validity")
    return face.Face()


def write_step(shape, path: Path):
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP export failed for {path}: {status}")


def write_step_with_units(shape, path: Path, coordinate_scale: float, length_unit: str = "MM"):
    """Write SI-coordinate geometry with explicit STEP units and coordinate scaling.

    Project geometry is represented in metres. Candidate STEP exports scale the
    coordinates to millimetres and declare millimetres, so a 4.8 m mouth reads
    as 4800 mm in CAD. The historical writer above remains unchanged.
    """
    if not math.isfinite(coordinate_scale) or coordinate_scale <= 0:
        raise ValueError("STEP coordinate scale must be finite and positive")
    STEPControl_Controller.Init_s()
    previous_unit = Interface_Static.CVal_s("write.step.unit")
    Interface_Static.SetCVal_s("write.step.unit", length_unit)
    try:
        if coordinate_scale == 1.0:
            exported_shape = shape
        else:
            transform = gp_Trsf()
            transform.SetScale(gp_Pnt(0, 0, 0), coordinate_scale)
            exported_shape = BRepBuilderAPI_Transform(shape, transform, True).Shape()
        writer = STEPControl_Writer()
        writer.Transfer(exported_shape, STEPControl_AsIs)
        status = writer.Write(str(path))
        if status != IFSelect_RetDone:
            raise RuntimeError(f"STEP export failed for {path}: {status}")
    finally:
        Interface_Static.SetCVal_s("write.step.unit", previous_unit)


def step_length_unit(path: Path) -> str | None:
    text = path.read_text(encoding="ascii", errors="replace")
    if "SI_UNIT(.MILLI.,.METRE.)" in text:
        return "mm"
    if "SI_UNIT($,.METRE.)" in text:
        return "m"
    return None


def step_imported_bounds(path: Path) -> list[float]:
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP bounds readback failed for {path}: {status}")
    reader.TransferRoots()
    return bounds(reader.OneShape())


def step_readback(path: Path) -> dict:
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP readback failed for {path}: {status}")
    reader.TransferRoots()
    shape = reader.OneShape()
    solid_shapes = solids(shape)
    validity = [bool(BRepCheck_Analyzer(item).IsValid()) for item in solid_shapes]
    return {
        "solid_count": len(solid_shapes),
        "validity": validity,
        "all_solids_valid": bool(solid_shapes) and all(validity),
    }


def write_stl(shape, path: Path, linear_deflection_m: float = 0.004):
    BRepMesh_IncrementalMesh(shape, linear_deflection_m, False, 0.15, True).Perform()
    writer = StlAPI_Writer()
    if not writer.Write(shape, str(path)):
        raise RuntimeError(f"STL export failed for {path}")


def stl_closedness(path: Path, expected_components: int) -> dict:
    """Check the exported triangle mesh is a collection of closed solid shells."""
    mesh = pv.read(str(path)).extract_surface().triangulate().clean(tolerance=1e-9)
    if mesh.n_cells == 0:
        raise RuntimeError(f"Exported STL is empty: {path}")
    boundary = mesh.extract_feature_edges(
        boundary_edges=True,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=False,
    )
    nonmanifold = mesh.extract_feature_edges(
        boundary_edges=False,
        feature_edges=False,
        manifold_edges=False,
        non_manifold_edges=True,
    )
    connected = mesh.connectivity(extraction_mode="all")
    regions = np.asarray(connected.cell_data.get("RegionId", []), dtype=np.int64)
    component_count = int(np.unique(regions).size) if len(regions) else 0
    result = {
        "path": path.name,
        "triangle_count": int(mesh.n_cells),
        "point_count_after_welding": int(mesh.n_points),
        "connected_component_count": component_count,
        "expected_component_count": expected_components,
        "boundary_edge_count": int(boundary.n_cells),
        "nonmanifold_edge_count": int(nonmanifold.n_cells),
        "watertight_components": bool(
            component_count == expected_components
            and boundary.n_cells == 0
            and nonmanifold.n_cells == 0
        ),
    }
    if not result["watertight_components"]:
        raise RuntimeError(f"Rounded divider STL is not a watertight solid mesh: {result}")
    return result


def section_area(
    shape, x: float, y_center: float, z_center: float, tangent: tuple[float, float, float]
) -> float:
    """Build exact planar section faces from BREP intersection edges."""
    normal = np.asarray(tangent, dtype=float)
    normal /= np.linalg.norm(normal)
    section = BRepAlgoAPI_Section(
        shape,
        gp_Pln(gp_Pnt(x, y_center, z_center), gp_Dir(*map(float, normal))),
        True,
    )
    if not section.IsDone():
        raise RuntimeError(f"BREP section failed at x={x:.9f} m")
    edges = HSequence_TopoDS_Shape()
    explorer = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
    while explorer.More():
        edges.Append(explorer.Current())
        explorer.Next()
    if edges.IsEmpty():
        return 0.0
    wires = ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(edges, 1e-7, True)
    total = 0.0
    for index in range(1, wires.Length() + 1):
        maker = BRepBuilderAPI_MakeFace(TopoDS.Wire(wires.Value(index)), True)
        if not maker.IsDone() or not BRepCheck_Analyzer(maker.Face()).IsValid():
            raise RuntimeError(f"Invalid closed BREP section at x={x:.9f} m")
        total += surface_area(maker.Face())
    return total


def read_stl_triangles(path: Path):
    mesh = pv.read(str(path)).extract_surface().triangulate().clean()
    cells = mesh.faces.reshape((-1, 4))[:, 1:]
    return np.asarray(mesh.points[cells], dtype=float)


def render_assembly(
    envelope_stl: Path,
    plates_stl: Path,
    output: Path,
    assembly_bounds: list[float],
    tank_axis: str,
    divider_count: int,
    divider_thickness_m: float,
    pipe_transition_join: str,
    divider_leading_edge: str = "square",
    nose_radius_m: float | None = None,
):
    fig = plt.figure(figsize=(13, 8), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    for stl, color, alpha, stride in (
        (envelope_stl, "#72849a", 0.14, 1),
        (plates_stl, "#e6a62e", 0.94, 1),
    ):
        triangles = read_stl_triangles(stl)
        stride = max(stride, len(triangles) // 24000)
        ax.add_collection3d(
            Poly3DCollection(
                triangles[::stride],
                facecolor=color,
                edgecolor="none",
                alpha=alpha,
                linewidth=0,
            )
        )
    xmin, xmax, ymin, ymax, zmin, zmax = assembly_bounds
    spans = (xmax - xmin, ymax - ymin, zmax - zmin)
    pads = tuple(max(0.04, span * 0.04) for span in spans)
    xmin, xmax = xmin - pads[0], xmax + pads[0]
    ymin, ymax = ymin - pads[1], ymax + pads[1]
    zmin, zmax = zmin - pads[2], zmax + pads[2]
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_zlim(zmin, zmax)
    ax.set_box_aspect((xmax - xmin, ymax - ymin, zmax - zmin))
    ax.view_init(elev=25 if tank_axis == "vertical" else 28, azim=-57)
    ax.set_xlabel("X · discharge (+X), m")
    ax.set_ylabel("Y · tank columns / mouth width, m")
    ax.set_zlabel("Z · vertical, m")
    if divider_leading_edge == "rounded":
        divider_label = (
            f"{divider_count} finite {1000 * divider_thickness_m:g} mm dividers per outlet · "
            f"rounded nose R{1000 * float(nose_radius_m):g} mm (geometry candidate)"
        )
    else:
        divider_label = (
            f"{divider_count} assumed {1000 * divider_thickness_m:g} mm fitted divider solids"
        )
    ax.set_title(
        f"Provisional {tank_axis}-axis two-tank / four-outlet envelope\n"
        f"Pipe/transition join: {pipe_transition_join}\n"
        f"Grey: fluid envelope · amber: {divider_label}"
    )
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(output, facecolor="white")
    plt.close(fig)


def render_branch_join_sections(
    envelope_stl: Path,
    output: Path,
    join_mode: str,
    post_rise_straight_m: float,
    transition_and_mouth_length_m: float,
):
    """Render true STL longitudinal sections through all four pipe/loft joins."""
    mesh = pv.read(str(envelope_stl)).extract_surface().triangulate().clean()
    stations = downstream_stations(post_rise_straight_m, transition_and_mouth_length_m)
    pipe_end = (
        stations.pipe_overlap_end_x_m
        if join_mode == "legacy-overlap"
        else stations.transition_inlet_x_m
    )
    x_min = stations.transition_inlet_x_m - 0.08
    x_max = max(pipe_end, stations.transition_inlet_x_m) + 0.10
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), dpi=160, sharex=True, sharey=True)
    axes = axes.ravel()
    all_mouth_z = [branch["mouth_z_m"] for branch in BRANCHES]
    section_z_limits = (min(all_mouth_z) - 0.18, max(all_mouth_z) + 0.18)
    for index, (y_tank, branch) in enumerate(
        ((y_tank, branch) for y_tank in TANK_Y for branch in BRANCHES)
    ):
        y_pipe = y_tank + branch["pipe_lateral_offset_m"]
        section = mesh.slice(normal=(0.0, 1.0, 0.0), origin=(0.0, y_pipe, 0.0))
        if section.n_cells == 0:
            raise RuntimeError(
                f"Empty longitudinal section for tank y={y_tank:g}, {branch['name']}"
            )
        points = np.asarray(section.points, dtype=float)
        ids = np.asarray(section.lines, dtype=np.int64)
        cursor = 0
        line_count = 0
        ax = axes[index]
        while cursor < len(ids):
            count = int(ids[cursor])
            point_ids = ids[cursor + 1 : cursor + 1 + count]
            if count >= 2:
                line = points[point_ids]
                keep = (line[:, 0] >= x_min - 1e-8) & (line[:, 0] <= x_max + 1e-8)
                if np.count_nonzero(keep) >= 2:
                    ax.plot(line[keep, 0], line[keep, 2], color="#2d526c", linewidth=1.15)
                    line_count += 1
            cursor += count + 1
        if line_count == 0:
            raise RuntimeError(
                f"No longitudinal outline in ROI for tank y={y_tank:g}, {branch['name']}"
            )
        ax.axvline(stations.transition_inlet_x_m, color="#2b8a3e", linestyle="--", linewidth=0.9)
        ax.axvline(pipe_end, color="#c92a2a", linestyle=":", linewidth=0.9)
        ax.set_xlim(x_min, x_max)
        ax.set_title(f"Tank {index // 2 + 1} · {branch['name']} · y={y_pipe:.3f} m")
        ax.set_xlabel("X, m")
        ax.set_ylabel("Z, m")
        ax.grid(True, alpha=0.2)
    for ax in axes:
        ax.set_ylim(*section_z_limits)
    fig.suptitle(
        f"Actual STL longitudinal sections at all four joins · {join_mode}\n"
        "Green: transition inlet · red: pipe end; section plane normal +Y"
    )
    fig.tight_layout()
    fig.savefig(output, facecolor="white")
    plt.close(fig)


def render_tank_connection_section(envelope_stl: Path, output: Path, tank_axis: str):
    """Render an actual STL slice through tank cross-sections and pipe starts."""
    fluid = pv.read(str(envelope_stl)).extract_surface().triangulate().clean()
    if tank_axis == "horizontal":
        origin = (PIPE_START_X_M, 0.0, 0.0)
        normal = (1.0, 0.0, 0.0)
        label = f"YZ section at x={PIPE_START_X_M:.3f} m (through pipe starts)"
        view = "yz"
        axis_labels = ("Y · tank columns, m", "Z · vertical, m")
    else:
        z_cut = TANK_Z - 0.100
        origin = (0.0, 0.0, z_cut)
        normal = (0.0, 0.0, 1.0)
        label = f"XY section at z={z_cut:.3f} m (through pipe starts)"
        view = "xy"
        axis_labels = ("X · discharge, m", "Y · tank columns, m")
    section = fluid.slice(normal=normal, origin=origin)
    if section.n_cells == 0:
        raise RuntimeError(f"Tank/connection STL section is empty for {tank_axis} axis")
    points = np.asarray(section.points, dtype=float)
    projected = points[:, [1, 2]] if view == "yz" else points[:, [0, 1]]
    fig, ax = plt.subplots(figsize=(8, 7), dpi=160)
    line_indices = np.asarray(section.lines, dtype=np.int64)
    cursor = 0
    segment_count = 0
    while cursor < len(line_indices):
        count = int(line_indices[cursor])
        ids = line_indices[cursor + 1 : cursor + 1 + count]
        if count >= 2:
            ax.plot(projected[ids, 0], projected[ids, 1], color="#33495e", linewidth=1.25)
            segment_count += 1
        cursor += count + 1
    if segment_count == 0:
        plt.close(fig)
        raise RuntimeError(
            f"Tank/connection section has no drawable line segments for {tank_axis} axis"
        )
    xmin, ymin = np.min(projected, axis=0)
    xmax, ymax = np.max(projected, axis=0)
    padx = max(0.04, (xmax - xmin) * 0.06)
    pady = max(0.04, (ymax - ymin) * 0.06)
    ax.set_xlim(xmin - padx, xmax + padx)
    ax.set_ylim(ymin - pady, ymax + pady)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(axis_labels[0])
    ax.set_ylabel(axis_labels[1])
    ax.set_title(f"{tank_axis.capitalize()} tank-axis connection section\n{label}")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(output, facecolor="white")
    plt.close(fig)


def render_sections(
    output: Path,
    intermediate_width_m: float,
    divider_count: int,
    divider_thickness_m: float,
    stations: DownstreamStations,
):
    section_stations = [
        (
            f"Pipe/transition inlet\nx={stations.transition_inlet_x_m:.3f} m",
            PIPE_ID_M,
            PIPE_ID_M,
            0,
        ),
        (
            f"Divider start\nx={stations.lamella_start_x_m:.3f} m",
            0.485,
            0.1535,
            1,
        ),
        (
            f"Intermediate\nx={stations.transition_intermediate_x_m:.3f} m",
            intermediate_width_m,
            MOUTH_H_M,
            1,
        ),
        (f"Mouth\nx={stations.mouth_x_m:.3f} m", MOUTH_W_M, MOUTH_H_M, 1),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(14, 5), dpi=150)
    for ax, (label, width, height, has_dividers) in zip(axes, section_stations):
        if "Pipe/transition inlet" in label:
            ax.add_patch(
                Circle((0, 0), width / 2, facecolor="#d9e8f0", edgecolor="#263746", linewidth=1.4)
            )
        else:
            ax.add_patch(
                Rectangle(
                    (-width / 2, -height / 2),
                    width,
                    height,
                    facecolor="#d9e8f0",
                    edgecolor="#263746",
                    linewidth=1.4,
                )
            )
            if has_dividers:
                for center in equal_gap_centers(width, divider_count, divider_thickness_m):
                    ax.add_patch(
                        Rectangle(
                            (center - divider_thickness_m / 2, -height / 2),
                            divider_thickness_m,
                            height,
                            facecolor="#e6a62e",
                            edgecolor="#946500",
                            linewidth=0.55,
                        )
                    )
        ax.set_title(label)
        ax.set_xlabel("Y (m)")
        ax.set_ylabel("Z (m)")
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(-0.58, 0.58)
        ax.set_ylim(-0.23, 0.23)
        ax.grid(True, alpha=0.18)
    fig.suptitle(
        f"Cross-sections · {divider_count} dividers; "
        f"{1000 * divider_thickness_m:g} mm assumed, not measured"
    )
    fig.tight_layout()
    fig.savefig(output, facecolor="white")
    plt.close(fig)


def render_single_outlet_plates(plates_stl: Path, output: Path, closeup: bool = False):
    """Render one outlet's four finite divider solids without a covering shell."""
    mesh = pv.read(str(plates_stl)).extract_surface().triangulate().clean()
    if mesh.n_cells == 0:
        raise RuntimeError("Single-outlet divider STL is empty")
    if closeup:
        xmin, xmax, ymin, ymax, zmin, zmax = mesh.bounds
        nose_end_x = min(xmax, xmin + 0.10)
        mesh = mesh.clip_box(
            bounds=(xmin - 0.002, nose_end_x, ymin - 0.01, ymax + 0.01, zmin - 0.01, zmax + 0.01),
            invert=False,
        )
        if mesh.n_cells == 0:
            raise RuntimeError("Rounded-divider nose close-up clip is empty")
    triangles = np.asarray(mesh.points[mesh.faces.reshape((-1, 4))[:, 1:]], dtype=float)
    fig = plt.figure(figsize=(10, 7), dpi=180)
    ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(
        Poly3DCollection(
            triangles,
            facecolor="#e6a62e",
            edgecolor="#76521a",
            linewidth=0.12,
            alpha=1.0,
        )
    )
    xmin, xmax, ymin, ymax, zmin, zmax = mesh.bounds
    spans = (xmax - xmin, ymax - ymin, zmax - zmin)
    centers = (0.5 * (xmin + xmax), 0.5 * (ymin + ymax), 0.5 * (zmin + zmax))
    span = max(spans)
    ax.set_xlim(centers[0] - span * 0.56, centers[0] + span * 0.56)
    ax.set_ylim(centers[1] - span * 0.56, centers[1] + span * 0.56)
    ax.set_zlim(centers[2] - span * 0.36, centers[2] + span * 0.36)
    ax.set_box_aspect((1.35, 1.0, 0.42))
    ax.view_init(elev=27, azim=-57)
    ax.set_xlabel("X · discharge (+X), m")
    ax.set_ylabel("Y · mouth width, m")
    ax.set_zlabel("Z · vertical, m")
    if closeup:
        ax.set_title(
            "Rounded leading-edge close-up · R = 7.5 mm · gauge = 15 mm\n"
            "Downstream portions clipped for display"
        )
    else:
        ax.set_title(
            "One outlet · four finite-thickness rounded dividers\nNose radius = thickness / 2"
        )
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(output, facecolor="white")
    plt.close(fig)


def render_mouth_channel_dimensions(output: Path, thickness: float, divider_count: int):
    """Render the nominal mouth cross-section with all five equal clear gaps."""
    width, height = MOUTH_W_M, MOUTH_H_M
    gap = (width - divider_count * thickness) / (divider_count + 1)
    if gap <= 0:
        raise RuntimeError("Rounded dividers leave no clear mouth channels")
    centers = equal_gap_centers(width, divider_count, thickness)
    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=180)
    ax.add_patch(
        Rectangle(
            (-width / 2, -height / 2),
            width,
            height,
            facecolor="#eaf1f6",
            edgecolor="#263746",
            linewidth=1.8,
        )
    )
    for center in centers:
        ax.add_patch(
            Rectangle(
                (center - thickness / 2, -height / 2),
                thickness,
                height,
                facecolor="#e6a62e",
                edgecolor="#76521a",
                linewidth=1.1,
            )
        )
    divider = centers[1] if divider_count > 1 else centers[0]
    left, right = divider - thickness / 2, divider + thickness / 2
    gap_left = right
    gap_right = centers[2] - thickness / 2 if divider_count > 2 else left + gap
    ydim = -0.090
    ax.annotate(
        "",
        xy=(gap_left, ydim),
        xytext=(gap_right, ydim),
        arrowprops={"arrowstyle": "<->", "color": "#176b3a", "lw": 1.4},
    )
    ax.text(
        0.5 * (gap_left + gap_right),
        ydim - height * 0.10,
        f"equal clear gap = {gap * 1000:.0f} mm",
        ha="center",
        va="top",
        color="#176b3a",
        fontsize=10,
    )
    ax.annotate(
        "",
        xy=(-width / 2, 0.102),
        xytext=(width / 2, 0.102),
        arrowprops={"arrowstyle": "<->", "color": "#33495e", "lw": 1.1},
    )
    ax.text(
        0.0,
        0.106,
        "1000 mm mouth",
        ha="center",
        va="bottom",
        color="#33495e",
        fontsize=10,
    )
    ax.set_xlim(-0.59, 0.59)
    ax.set_ylim(-0.14, 0.14)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Y · outlet width, m")
    ax.set_ylabel("Z · outlet height, m")
    ax.set_title(
        f"Nominal mouth · {divider_count} vertical plates · {thickness * 1000:g} mm gauge · "
        f"{divider_count + 1} equal channels"
    )
    ax.grid(True, alpha=0.18)
    fig.tight_layout()
    fig.savefig(output, facecolor="white")
    plt.close(fig)


def generate(args) -> dict:
    stations = downstream_stations(args.post_rise_straight_m, args.transition_and_mouth_length_m)
    output = args.output_dir.resolve()
    rounded_candidate = args.lamella_leading_edge == "rounded"
    step_coordinate_scale = 1000.0 if rounded_candidate else 1.0

    def export_step(shape, path):
        if rounded_candidate:
            write_step_with_units(shape, path, step_coordinate_scale, "MM")
        else:
            write_step(shape, path)

    geometry_dir = output / "geometry"
    divider_dir = geometry_dir / (
        "rounded_dividers" if args.lamella_leading_edge == "rounded" else "mid_surfaces"
    )
    figures_dir = output / "figures"
    stl_dir = output / "stl"
    for directory in (geometry_dir, divider_dir, figures_dir, stl_dir):
        directory.mkdir(parents=True, exist_ok=True)

    tank_r = args.tank_diameter_m / 2
    tank_area = math.pi * tank_r**2
    gas_volume = args.water_volume_m3 * args.headspace_ratio
    capacity = args.water_volume_m3 + gas_volume
    tank_length = capacity / tank_area
    if tank_length <= 0 or args.lamella_count < 1:
        raise ValueError("Tank capacity and divider count must be positive")
    pipe_area = math.pi * (PIPE_ID_M / 2) ** 2
    mouth_area = MOUTH_W_M * MOUTH_H_M

    envelope_components = []
    tank_records = []
    tank_shapes = []
    tank_placements = []
    transition_rows = []
    joined_branch_shapes = []
    branch_join_records = []
    line_volume_records = []
    connection_records = []
    plate_solids = []
    mid_faces = []
    divider_records = []
    for y_tank in TANK_Y:
        tank, placement = make_tank(y_tank, tank_r, tank_length, args.tank_axis)
        if not BRepCheck_Analyzer(tank).IsValid():
            raise RuntimeError(f"Tank at y={y_tank:g} m failed BREP validity")
        tank_shapes.append(tank)
        tank_placements.append(placement)
    for tank_index, y_tank in enumerate(TANK_Y, start=1):
        tank = tank_shapes[tank_index - 1]
        placement = tank_placements[tank_index - 1]
        envelope_components.append(tank)
        tank_records.append(
            {
                "tank_index": tank_index,
                "center_y_m": y_tank,
                "axis": args.tank_axis,
                "volume_m3": volume(tank),
                "length_m": tank_length,
                "bounds_m": bounds(tank),
                **placement,
            }
        )
        tank_line_volume = 0.0
        other_tank = tank_shapes[1 - (tank_index - 1)]
        for branch in BRANCHES:
            start_check = pipe_start_section_clearance(
                y_tank, branch, tank_r, tank_length, args.tank_axis
            )
            if not start_check["entire_start_section_inside_own_tank"]:
                raise RuntimeError(
                    f"Pipe start is not fully inside own tank: tank{tank_index}/{branch['name']} "
                    f"clearance={start_check['minimum_conservative_full_start_clearance_m']:.9g} m"
                )
            branch_shape, y_pipe = branch_pipe(
                y_tank,
                branch,
                args.tank_diameter_m,
                PIPE_ID_M,
                stations,
                args.pipe_transition_join,
            )
            y_mouth = y_tank
            transition = aligned_ruled_transition(
                y_pipe,
                y_mouth,
                branch["mouth_z_m"],
                args.intermediate_width_m,
                stations,
                PIPE_ID_M,
            )
            envelope_components.extend((branch_shape, transition))
            transition_rows.append((tank_index, branch, y_pipe, transition))

            pipe_transition_overlap = require_common(branch_shape, transition)
            joined_branch = require_fuse(branch_shape, transition)
            joined_branch_shapes.append(joined_branch)
            pipe_inside_tank = require_common(branch_shape, tank)
            transition_inside_tank = require_common(transition, tank)
            overlap_inside_tank = require_common(pipe_transition_overlap, tank)
            pipe_inside_other_tank = require_common(branch_shape, other_tank)
            transition_inside_other_tank = require_common(transition, other_tank)
            pipe_volume = volume(branch_shape)
            transition_volume = volume(transition)
            overlap_volume = volume(pipe_transition_overlap)
            overlap_common_area = surface_area(pipe_transition_overlap)
            own_tank_overlap_volume = volume(pipe_inside_tank)
            other_tank_overlap_volume = volume(pipe_inside_other_tank) + volume(
                transition_inside_other_tank
            )
            if own_tank_overlap_volume <= 1e-10:
                raise RuntimeError(
                    f"Branch has no positive overlap with own tank: tank{tank_index}/{branch['name']}"
                )
            if other_tank_overlap_volume > 1e-8:
                raise RuntimeError(
                    f"Branch connects the other tank: tank{tank_index}/{branch['name']} "
                    f"overlap={other_tank_overlap_volume:.9g} m^3"
                )
            pipe_interface_area = None
            transition_interface_area = None
            if args.pipe_transition_join == "legacy-overlap":
                if overlap_volume <= 1e-10:
                    raise RuntimeError(
                        f"Pipe and transition do not overlap through to the mouth: "
                        f"tank{tank_index}/{branch['name']}"
                    )
            elif args.pipe_transition_join == "flush-at-inlet":
                expected_joint_area = math.pi * (PIPE_ID_M / 2) ** 2
                pipe_interface_area = section_area(
                    branch_shape,
                    stations.transition_inlet_x_m,
                    y_pipe,
                    branch["mouth_z_m"],
                    (1, 0, 0),
                )
                transition_interface_area = section_area(
                    transition,
                    stations.transition_inlet_x_m,
                    y_pipe,
                    branch["mouth_z_m"],
                    (1, 0, 0),
                )
                if (
                    overlap_volume > 1e-9
                    or abs(pipe_interface_area - expected_joint_area) > 2e-5
                    or abs(transition_interface_area - expected_joint_area) > 2e-5
                ):
                    raise RuntimeError(
                        f"Flush pipe/transition interface is not a single circular joint for "
                        f"tank{tank_index}/{branch['name']}: common volume={overlap_volume:.9g} "
                        f"m^3, BREP common area={overlap_common_area:.9g} m^2, "
                        f"pipe-plane area={pipe_interface_area:.9g} m^2, "
                        f"transition-plane area={transition_interface_area:.9g} m^2, "
                        f"expected each={expected_joint_area:.9g} m^2"
                    )
            joined_volume_error = abs(
                volume(joined_branch) - (pipe_volume + transition_volume - overlap_volume)
            )
            joined_volume_relative_error = joined_volume_error / max(volume(joined_branch), 1e-12)
            if joined_volume_relative_error > BREP_UNION_VOLUME_REL_TOLERANCE:
                raise RuntimeError(
                    f"Union volume does not match BREP inclusion-exclusion for "
                    f"tank{tank_index}/{branch['name']}: union={volume(joined_branch):.12g} m^3, "
                    f"pipe={pipe_volume:.12g} m^3, transition={transition_volume:.12g} m^3, "
                    f"common={overlap_volume:.12g} m^3, error={joined_volume_error:.12g} m^3 "
                    f"({joined_volume_relative_error:.6g} relative)"
                )
            pipe_end_x = (
                stations.pipe_overlap_end_x_m
                if args.pipe_transition_join == "legacy-overlap"
                else stations.transition_inlet_x_m
            )
            section_offsets = tuple(np.round(np.arange(-0.020, 0.241, 0.010), 9)) + (
                -0.010,
                -0.001,
                0.001,
                0.010,
                0.050,
                pipe_end_x - stations.transition_inlet_x_m - 0.001,
                pipe_end_x - stations.transition_inlet_x_m + 0.001,
            )
            section_samples = []
            for offset in dict.fromkeys(section_offsets):
                sample_x = stations.transition_inlet_x_m + offset
                if sample_x <= stations.mouth_x_m:
                    section_samples.append(
                        {
                            "x_m": sample_x,
                            "offset_from_transition_inlet_m": offset,
                            "area_m2": section_area(
                                joined_branch, sample_x, y_pipe, branch["mouth_z_m"], (1, 0, 0)
                            ),
                        }
                    )
            branch_join_records.append(
                {
                    "tank_index": tank_index,
                    "branch": branch["name"],
                    "join_mode": args.pipe_transition_join,
                    "pipe_end_x_m": pipe_end_x,
                    "transition_inlet_x_m": stations.transition_inlet_x_m,
                    "interface_common_volume_m3": overlap_volume,
                    "interface_common_surface_area_m2": overlap_common_area,
                    "expected_circular_interface_area_m2": math.pi * (PIPE_ID_M / 2) ** 2,
                    "pipe_interface_plane_section_area_m2": pipe_interface_area,
                    "transition_interface_plane_section_area_m2": transition_interface_area,
                    "joined_brep_valid": BRepCheck_Analyzer(joined_branch).IsValid(),
                    "joined_brep_solid_count": len(solids(joined_branch)),
                    "joined_volume_m3": volume(joined_branch),
                    "inclusion_exclusion_volume_error_m3": joined_volume_error,
                    "inclusion_exclusion_volume_relative_error": joined_volume_relative_error,
                    "inclusion_exclusion_volume_relative_tolerance": BREP_UNION_VOLUME_REL_TOLERANCE,
                    "x_normal_section_samples": section_samples,
                }
            )
            train_volume = pipe_volume + transition_volume - overlap_volume
            inside_tank_volume = (
                volume(pipe_inside_tank)
                + volume(transition_inside_tank)
                - volume(overlap_inside_tank)
            )
            outside_tank_volume = train_volume - inside_tank_volume
            if train_volume <= 0 or inside_tank_volume < 0 or outside_tank_volume <= 0:
                raise RuntimeError(
                    f"No positive downstream line volume: tank{tank_index}/{branch['name']}"
                )
            tank_line_volume += outside_tank_volume
            connection_records.append(
                {
                    "tank_index": tank_index,
                    "branch": branch["name"],
                    "start_section_check": start_check,
                    "pipe_overlap_own_tank_m3": own_tank_overlap_volume,
                    "pipe_and_transition_overlap_m3": overlap_volume,
                    "pipe_and_transition_overlap_other_tank_m3": other_tank_overlap_volume,
                    "transition_connected_to_own_mouth_x_m": stations.mouth_x_m,
                    "start_inside_own_tank": True,
                    "positive_own_tank_overlap": True,
                    "does_not_connect_other_tank": True,
                    "connected_through_to_own_horizontal_mouth": True,
                }
            )
            line_volume_records.append(
                {
                    "tank_index": tank_index,
                    "branch": branch["name"],
                    "branch_pipe_transition_union_volume_m3": train_volume,
                    "branch_pipe_shape_volume_m3": pipe_volume,
                    "transition_shape_volume_m3": transition_volume,
                    "pipe_transition_overlap_volume_m3": overlap_volume,
                    "union_volume_inside_tank_m3": inside_tank_volume,
                    "line_volume_outside_tank_m3": outside_tank_volume,
                }
            )

            widths = (0.485, args.intermediate_width_m, MOUTH_W_M, MOUTH_W_M)
            xs = (
                stations.lamella_start_x_m,
                stations.transition_intermediate_x_m,
                stations.transition_end_x_m,
                stations.mouth_x_m,
            )
            centerline_start = y_pipe - 0.0703 * (y_mouth - y_pipe)
            centers_by_station = []
            for width in widths:
                centers = equal_gap_centers(width, args.lamella_count, args.lamella_thickness_m)
                centers_by_station.append(centers)
            for divider_index in range(args.lamella_count):
                rows = []
                for station, (x, centers) in enumerate(zip(xs, centers_by_station)):
                    local_center = (
                        centerline_start if station == 0 else y_pipe if station == 1 else y_mouth
                    )
                    rows.append((x, local_center + centers[divider_index], branch["mouth_z_m"]))
                nose_record = None
                if args.lamella_leading_edge == "rounded":
                    stock, nose_record = make_rounded_tall_plate(
                        rows,
                        args.lamella_thickness_m,
                        args.effective_lamella_nose_radius_m,
                    )
                else:
                    stock = make_tall_plate(rows, args.lamella_thickness_m)
                fitted_plate = require_common(stock, transition)
                if len(solids(fitted_plate)) != 1 or not BRepCheck_Analyzer(fitted_plate).IsValid():
                    raise RuntimeError(
                        f"Fitted divider failed: tank{tank_index}/{branch['name']}/{divider_index + 1}"
                    )
                plate_solids.append(fitted_plate)

                clipped_segments = []
                label = f"tank{tank_index:02d}_{branch['name']}_divider{divider_index + 1:02d}"
                group_path = divider_dir / f"{label}.step"
                if args.lamella_leading_edge == "rounded":
                    export_step(fitted_plate, group_path)
                else:
                    for row0, row1 in zip(rows, rows[1:]):
                        clipped = require_common(make_midface(row0, row1, MOUTH_H_M), transition)
                        if (
                            not BRepCheck_Analyzer(clipped).IsValid()
                            or surface_area(clipped) <= 1e-10
                        ):
                            raise RuntimeError(
                                "Clipped divider mid-surface segment is invalid or empty"
                            )
                        clipped_segments.append(clipped)
                        mid_faces.append(clipped)
                    export_step(compound(clipped_segments), group_path)
                divider_records.append(
                    {
                        "label": label,
                        "tank_index": tank_index,
                        "branch": branch["name"],
                        "divider_index": divider_index + 1,
                        "geometry_kind": (
                            "finite-thickness rounded solid"
                            if args.lamella_leading_edge == "rounded"
                            else "zero-thickness clipped surface segments"
                        ),
                        "candidate_face_zone": (
                            None if args.lamella_leading_edge == "rounded" else f"baffle_{label}"
                        ),
                        "surface_segment_count": len(clipped_segments),
                        "stations_x_m": list(xs),
                        "centerline_points_xyz_m": [list(row) for row in rows],
                        "rounded_nose": nose_record,
                        "fitted_solid_bounds_m": bounds(fitted_plate),
                        "fitted_solid_volume_m3": volume(fitted_plate),
                        "step": group_path.relative_to(output).as_posix(),
                    }
                )
        tank_records[-1]["downstream_line_volume_m3"] = tank_line_volume

    envelope = compound(envelope_components)
    joined_branches = compound(joined_branch_shapes)
    finite_dividers = compound(plate_solids)
    envelope_step = geometry_dir / "two_tank_four_outlet_aligned_ruled_envelope.step"
    joined_branches_step = geometry_dir / "four_pipe_transition_joined_branches.step"
    if args.lamella_leading_edge == "rounded":
        finite_step = geometry_dir / "four_mouth_rounded_finite_divider_solids.step"
        single_outlet_step = geometry_dir / "single_outlet_rounded_divider_solids.step"
        full_assembly_step = geometry_dir / "two_tank_four_outlet_rounded_divider_assembly.step"
        mid_step = None
        full_assembly_shape = compound([envelope, finite_dividers])
        single_outlet_shape = compound(plate_solids[: args.lamella_count])
    else:
        finite_step = geometry_dir / "four_mouth_fitted_divider_solids.step"
        single_outlet_step = None
        full_assembly_step = None
        full_assembly_shape = None
        single_outlet_shape = None
        mid_step = geometry_dir / "four_mouth_zero_thickness_divider_surfaces.step"
    zero_thickness = compound(mid_faces) if mid_faces else None
    export_step(envelope, envelope_step)
    export_step(joined_branches, joined_branches_step)
    export_step(finite_dividers, finite_step)
    if zero_thickness is not None and mid_step is not None:
        export_step(zero_thickness, mid_step)
    if full_assembly_step is not None:
        export_step(full_assembly_shape, full_assembly_step)
        export_step(single_outlet_shape, single_outlet_step)
    envelope_check = step_readback(envelope_step)
    joined_branches_check = step_readback(joined_branches_step)
    finite_check = step_readback(finite_step)
    if envelope_check["solid_count"] != 10 or not envelope_check["all_solids_valid"]:
        raise RuntimeError(f"Envelope STEP round-trip failed: {envelope_check}")
    if joined_branches_check["solid_count"] != 4 or not joined_branches_check["all_solids_valid"]:
        raise RuntimeError(f"Joined branch STEP round-trip failed: {joined_branches_check}")
    expected_plate_count = len(transition_rows) * args.lamella_count
    if finite_check["solid_count"] != expected_plate_count or not finite_check["all_solids_valid"]:
        raise RuntimeError(f"Divider STEP round-trip failed: {finite_check}")
    if full_assembly_step is not None:
        full_assembly_check = step_readback(full_assembly_step)
        single_outlet_check = step_readback(single_outlet_step)
        if (
            full_assembly_check["solid_count"]
            != envelope_check["solid_count"] + expected_plate_count
            or not full_assembly_check["all_solids_valid"]
        ):
            raise RuntimeError(f"Full assembly STEP round-trip failed: {full_assembly_check}")
        if (
            single_outlet_check["solid_count"] != args.lamella_count
            or not single_outlet_check["all_solids_valid"]
        ):
            raise RuntimeError(f"Single-outlet STEP round-trip failed: {single_outlet_check}")
        step_units_validation = {
            "declared_length_unit": step_length_unit(full_assembly_step),
            "coordinate_scale_to_mm": step_coordinate_scale,
            "full_assembly_imported_bounds_mm": step_imported_bounds(full_assembly_step),
            "single_outlet_imported_bounds_mm": step_imported_bounds(single_outlet_step),
        }
        if step_units_validation["declared_length_unit"] != "mm":
            raise RuntimeError(
                f"Rounded candidate STEP does not declare millimetres: {step_units_validation}"
            )
        if abs(step_units_validation["full_assembly_imported_bounds_mm"][1] - 4800.0) > 0.1:
            raise RuntimeError(
                f"Rounded candidate STEP scale check failed: {step_units_validation}"
            )
        if (
            abs(step_units_validation["single_outlet_imported_bounds_mm"][1] - 4800.0) > 0.1
            or step_units_validation["single_outlet_imported_bounds_mm"][0] < 4210.0
        ):
            raise RuntimeError(
                f"Single-outlet STEP scale/start check failed: {step_units_validation}"
            )
    else:
        full_assembly_check = None
        single_outlet_check = None
        step_units_validation = None

    sections = []
    representative = transition_rows[0][3]
    y_pipe = transition_rows[0][2]
    y_mouth = TANK_Y[0]
    z_section = transition_rows[0][1]["mouth_z_m"]
    centerline_slope = (y_mouth - y_pipe) / (
        stations.transition_end_x_m - stations.transition_intermediate_x_m
    )
    section_epsilon = min(
        1e-4 * stations.scale_from_default, 1e-3 * args.transition_and_mouth_length_m
    )
    sample_xs = (
        stations.transition_inlet_x_m + section_epsilon,
        stations.transition_inlet_x_m + section_epsilon * 0.01,
        stations.transition_intermediate_x_m + section_epsilon * 0.1,
        stations.transition_end_x_m + section_epsilon * 0.1,
        stations.mouth_x_m - section_epsilon,
    )
    for x in sample_xs:
        if x <= stations.transition_intermediate_x_m:
            y_center, tangent = y_pipe, (1.0, 0.0, 0.0)
        elif x < stations.transition_end_x_m:
            y_center = y_pipe + centerline_slope * (x - stations.transition_intermediate_x_m)
            tangent = (1.0, centerline_slope, 0.0)
        else:
            y_center, tangent = y_mouth, (1.0, 0.0, 0.0)
        gross = section_area(representative, x, y_center, z_section, tangent)
        blocked = 0.0
        if x >= stations.lamella_start_x_m:
            blocked = sum(
                section_area(plate, x, y_center, z_section, tangent)
                for plate in plate_solids[: args.lamella_count]
            )
        sections.append(
            {
                "x_m": x,
                "centerline_y_m": y_center,
                "section_normal_xyz": list(tangent),
                "gross_envelope_area_m2": gross,
                "divider_blockage_area_m2": blocked,
                "open_area_after_dividers_m2": max(0.0, gross - blocked),
            }
        )
    # The start transition is circular and the mouth is rectangular. These
    # analytic values are independently reported beside the BREP slices.
    mouth_open_area = mouth_area - args.lamella_count * args.lamella_thickness_m * MOUTH_H_M
    pipe_opening_ratio = sections[1]["gross_envelope_area_m2"] / pipe_area

    envelope_stl = stl_dir / "envelope.stl"
    joined_branches_stl = stl_dir / "four_pipe_transition_joined_branches.stl"
    if rounded_candidate:
        dividers_stl = stl_dir / "rounded_finite_dividers.stl"
        full_assembly_stl = stl_dir / "fullassembly.stl"
        single_outlet_stl = stl_dir / "single_outlet_plates.stl"
    else:
        dividers_stl = stl_dir / "fitted_dividers.stl"
        full_assembly_stl = None
        single_outlet_stl = None
    if rounded_candidate:
        # Mesh the overview assembly before any high-resolution outlet export;
        # the BREP compounds share faces, and the later local nose refinement
        # would otherwise propagate into this deliberately compact STL.
        write_stl(full_assembly_shape, full_assembly_stl, linear_deflection_m=0.006)
        write_stl(envelope, envelope_stl)
        write_stl(joined_branches, joined_branches_stl, linear_deflection_m=0.00075)
        write_stl(finite_dividers, dividers_stl, linear_deflection_m=0.00020)
        write_stl(single_outlet_shape, single_outlet_stl, linear_deflection_m=0.00012)
        divider_stl_check = stl_closedness(dividers_stl, expected_plate_count)
        single_outlet_stl_check = stl_closedness(single_outlet_stl, args.lamella_count)
    else:
        write_stl(envelope, envelope_stl)
        write_stl(joined_branches, joined_branches_stl, linear_deflection_m=0.00075)
        write_stl(finite_dividers, dividers_stl)
        divider_stl_check = None
        single_outlet_stl_check = None
    assembly_png = figures_dir / "two_tank_four_outlet_assembly.png"
    sections_png = figures_dir / "transition_cross_sections.png"
    tank_connection_png = figures_dir / f"tank_connection_section_{args.tank_axis}.png"
    branch_join_png = (
        figures_dir / f"four_pipe_transition_join_sections_{args.pipe_transition_join}.png"
    )
    render_assembly(
        envelope_stl,
        dividers_stl,
        assembly_png,
        bounds(envelope),
        args.tank_axis,
        args.lamella_count,
        args.lamella_thickness_m,
        args.pipe_transition_join,
        args.lamella_leading_edge,
        args.effective_lamella_nose_radius_m,
    )
    render_tank_connection_section(envelope_stl, tank_connection_png, args.tank_axis)
    render_branch_join_sections(
        joined_branches_stl,
        branch_join_png,
        args.pipe_transition_join,
        args.post_rise_straight_m,
        args.transition_and_mouth_length_m,
    )
    render_sections(
        sections_png,
        args.intermediate_width_m,
        args.lamella_count,
        args.lamella_thickness_m,
        stations,
    )
    if rounded_candidate:
        plates_overview_png = figures_dir / "single_outlet_plates.png"
        nose_detail_png = figures_dir / "rounded_nose_closeup.png"
        mouth_dimensions_png = figures_dir / "rounded_mouth_channel_dimensions.png"
        render_single_outlet_plates(single_outlet_stl, plates_overview_png)
        render_single_outlet_plates(single_outlet_stl, nose_detail_png, closeup=True)
        render_mouth_channel_dimensions(
            mouth_dimensions_png, args.lamella_thickness_m, args.lamella_count
        )
    else:
        plates_overview_png = None
        nose_detail_png = None
        mouth_dimensions_png = None

    sections_path = output / "transition_sections.csv"
    with sections_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=sections[0].keys())
        writer.writeheader()
        writer.writerows(sections)
    mid_index = output / "divider_index.json"
    mid_index.write_text(
        json.dumps(
            {
                "status": (
                    "finite-thickness rounded divider solids; no zero-thickness surfaces exported; "
                    "CFD fluid mesh must be regenerated with the solids excluded"
                    if rounded_candidate
                    else "geometry-only zero-thickness divider candidates; no mesh faceZones created"
                ),
                "count": len(divider_records),
                "surface_segment_count": len(mid_faces),
                "solid_count": len(plate_solids),
                "leading_edge_mode": args.lamella_leading_edge,
                "nose_radius_m": args.effective_lamella_nose_radius_m,
                "dividers": divider_records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    generator_path = Path(__file__).resolve()
    package_versions = {}
    for package in ("cadquery-ocp", "numpy", "matplotlib", "pyvista", "vtk"):
        try:
            package_versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            package_versions[package] = "not installed"
    summary = {
        "status": (
            "rounded finite-thickness divider geometry candidate; no fluid mesh or CFD"
            if rounded_candidate
            else "reproducible provisional geometry source smoke generation; no mesh or CFD"
        ),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "generator": generator_path.name,
        "generator_sha256": sha256(generator_path),
        "runtime": {"python": platform.python_version(), "packages": package_versions},
        "units": "SI metres; +X discharge; Y separates tanks and spans mouth width; +Z up",
        "assumptions": {
            "tank_axis": args.tank_axis,
            "tank_axis_direction_xyz": [1, 0, 0] if args.tank_axis == "horizontal" else [0, 0, 1],
            "tank_placement_convention": (
                "Horizontal: flat-ended cylinder base at x=0, axis through (y_tank,TANK_Z)."
                if args.tank_axis == "horizontal"
                else "Vertical: flat-ended cylinder bottom at TANK_Z - tank radius; its +Z axis "
                "passes through the existing internal pipe-start x=0.250 m and each tank-center y. "
                "This is a provisional placement convention, not a measured rotated installation. "
                "Branch spines, valves, and outlets remain fixed, so wall intersections change."
            ),
            "tank_diameter_m": args.tank_diameter_m,
            "water_volume_m3_per_tank": args.water_volume_m3,
            "headspace_to_water_volume_ratio": args.headspace_ratio,
            "valve_and_pipe_id_m": VALVE_D_M,
            "pipe_id_basis": "assumed equal to reported valve diameter",
            "mouth_width_m": MOUTH_W_M,
            "mouth_height_m": MOUTH_H_M,
            "post_rise_straight_m_assumed": args.post_rise_straight_m,
            "transition_and_mouth_length_m_assumed": args.transition_and_mouth_length_m,
            "pipe_transition_join_mode": args.pipe_transition_join,
            "pipe_transition_join_interpretation": (
                "Legacy reproducibility mode: pipe extends 0.2 m (scaled with train length) "
                "past the transition inlet, then its lateral overlap with the loft is Boolean-"
                "unioned by downstream mesh preparation. This creates an exposed shoulder where "
                "the pipe ends if the loft has already narrowed."
                if args.pipe_transition_join == "legacy-overlap"
                else "Opt-in flush mode: constant-bore pipe terminates at the transition inlet "
                "plane; the circular pipe end and transition inlet share one nominal disk, with "
                "no added exposed straight or volumetric overlap. The two solids must fuse to "
                "one valid solid with a circular shared interface."
            ),
            "downstream_stations_x_m": {
                "rise_bend_end": BEND_X_M[-1],
                "transition_inlet": stations.transition_inlet_x_m,
                "divider_start": stations.lamella_start_x_m,
                "transition_intermediate": stations.transition_intermediate_x_m,
                "transition_end": stations.transition_end_x_m,
                "mouth": stations.mouth_x_m,
                "pipe_overlap_end": stations.pipe_overlap_end_x_m,
            },
            "station_mapping": (
                "Transition inlet = fixed rise-bend end + post-rise straight. All original downstream "
                "offsets from x=4.0 m scale by transition_and_mouth_length/1.8 m. The legacy overlap "
                "station at 0.2 m after the inlet scales by the same factor and is used only in "
                "legacy-overlap mode; flush-at-inlet terminates the pipe at the inlet."
            ),
            "intermediate_width_m_assumed": args.intermediate_width_m,
            "divider_count_per_mouth": args.lamella_count,
            "divider_thickness_m_assumed_not_measured": args.lamella_thickness_m,
            "divider_thickness_basis": (
                "User reported 10-20 mm thickness; 15 mm is the selected nominal for this geometry candidate."
                if rounded_candidate
                else "Historical geometry-generator default or command-line assumption; not measured."
            ),
            "divider_start_x_m_assumed": stations.lamella_start_x_m,
            "divider_geometry": (
                (
                    f"{args.lamella_count} vertical finite-thickness plates per outlet, equally "
                    f"spaced through the aligned ruled transition; {args.lamella_thickness_m:g} m "
                    "nominal gauge. Each leading edge is a semicircle of radius thickness/2, "
                    "oriented tangent to the first divider-centerline segment and clipped to the "
                    "transition envelope. These are closed geometry solids, not an existing CFD mesh."
                )
                if rounded_candidate
                else (
                    f"{args.lamella_count} equally spaced plates fanned through the aligned ruled "
                    f"transition; {args.lamella_thickness_m:g} m thickness is assumed. "
                    "Zero-thickness candidates are separate from fitted display solids."
                )
            ),
            "divider_leading_edge_mode": args.lamella_leading_edge,
            "divider_nose_radius_m": args.effective_lamella_nose_radius_m,
            "tank_length": "capacity divided by circular cross-sectional area; ideal flat-ended length, no end-cap correction",
        },
        "tank_metrics": {
            "capacity_m3_each": capacity,
            "derived_flat_cylinder_length_m": tank_length,
            "records": tank_records,
            "downstream_line_volume_m3_each": [
                item["downstream_line_volume_m3"] for item in tank_records
            ],
            "downstream_line_volume_total_m3": sum(
                item["downstream_line_volume_m3"] for item in tank_records
            ),
            "branch_line_volume_records": line_volume_records,
            "line_volume_definition": (
                "For each branch, exact BREP inclusion-exclusion computes pipe plus transition minus "
                "their overlap; the common part inside the tank is subtracted with the same inclusion-"
                "exclusion rule. Branch line volumes are summed per tank; this is a geometry inventory "
                "estimate, not a CFD zone-volume measurement."
            ),
        },
        "topology": {
            "tank_axis": args.tank_axis,
            "tank_count": len(TANK_Y),
            "mouth_count": len(transition_rows),
            "envelope_solid_count": envelope_check["solid_count"],
            "joined_pipe_transition_solid_count": joined_branches_check["solid_count"],
            "divider_solid_count": finite_check["solid_count"],
            "divider_count": len(divider_records),
            "zero_thickness_segment_count": len(mid_faces),
            "passages_per_mouth": args.lamella_count + 1,
            "rounded_nose_count": len(plate_solids) if rounded_candidate else 0,
        },
        "tank_connection_checks": {
            "method": (
                "The pipe-start disk is conservatively bounded by a radius-r ball inside the own-tank "
                "radial wall and flat ends; exact BREP common volumes verify positive own-tank overlap, "
                "zero other-tank intersection, and a valid single-solid pipe/transition union through "
                "the mouth. Join-specific shared volume/area is recorded separately."
            ),
            "records": connection_records,
            "all_starts_inside_own_tanks": all(
                item["start_inside_own_tank"] for item in connection_records
            ),
            "all_have_positive_own_tank_overlap": all(
                item["positive_own_tank_overlap"] for item in connection_records
            ),
            "none_connects_other_tank": all(
                item["does_not_connect_other_tank"] for item in connection_records
            ),
            "all_connect_through_own_mouth": all(
                item["connected_through_to_own_horizontal_mouth"] for item in connection_records
            ),
        },
        "pipe_transition_join_checks": {
            "mode": args.pipe_transition_join,
            "records": branch_join_records,
            "all_four_joined_solids_valid": all(
                item["joined_brep_valid"] and item["joined_brep_solid_count"] == 1
                for item in branch_join_records
            ),
            "shared_disk_area_expected_m2": math.pi * (PIPE_ID_M / 2) ** 2,
            "station_section_values_are_discrete": True,
        },
        "area_metrics": {
            "pipe_area_m2": pipe_area,
            "gross_mouth_area_m2_each": mouth_area,
            "nominal_divider_open_mouth_area_m2_each": mouth_open_area,
            "nominal_equal_clear_mouth_gap_m": (
                MOUTH_W_M - args.lamella_count * args.lamella_thickness_m
            )
            / (args.lamella_count + 1),
            "section_samples_one_transition_only_m2": sections,
            "endpoint_probe_to_pipe_area_ratio": pipe_opening_ratio,
            "continuous_minimum_area": "not proven; section values are discrete BREP slab samples",
        },
        "artifacts": {
            "envelope_step": envelope_step.relative_to(output).as_posix(),
            "joined_pipe_transition_step": joined_branches_step.relative_to(output).as_posix(),
            "fitted_dividers_step": finite_step.relative_to(output).as_posix(),
            "zero_thickness_surfaces_step": (
                mid_step.relative_to(output).as_posix() if mid_step is not None else None
            ),
            "single_outlet_dividers_step": (
                single_outlet_step.relative_to(output).as_posix()
                if single_outlet_step is not None
                else None
            ),
            "full_assembly_step": (
                full_assembly_step.relative_to(output).as_posix()
                if full_assembly_step is not None
                else None
            ),
            "full_assembly_stl": (
                full_assembly_stl.relative_to(output).as_posix()
                if full_assembly_stl is not None
                else None
            ),
            "single_outlet_dividers_stl": (
                single_outlet_stl.relative_to(output).as_posix()
                if single_outlet_stl is not None
                else None
            ),
            "divider_stl": dividers_stl.relative_to(output).as_posix(),
            "divider_index": mid_index.relative_to(output).as_posix(),
            "assembly_png": assembly_png.relative_to(output).as_posix(),
            "section_png": sections_png.relative_to(output).as_posix(),
            "tank_connection_section_png": tank_connection_png.relative_to(output).as_posix(),
            "four_join_longitudinal_section_png": branch_join_png.relative_to(output).as_posix(),
            "single_outlet_plates_png": (
                plates_overview_png.relative_to(output).as_posix() if plates_overview_png else None
            ),
            "single_outlet_rounded_noses_png": (
                nose_detail_png.relative_to(output).as_posix() if nose_detail_png else None
            ),
            "rounded_mouth_channel_dimensions_png": (
                mouth_dimensions_png.relative_to(output).as_posix()
                if mouth_dimensions_png
                else None
            ),
        },
        "roundtrip": {
            "envelope": envelope_check,
            "joined_pipe_transitions": joined_branches_check,
            "fitted_dividers": finite_check,
            "full_assembly": full_assembly_check,
            "single_outlet_dividers": single_outlet_check,
            "step_units_validation": step_units_validation,
            "divider_stl_closedness": divider_stl_check,
            "single_outlet_stl_closedness": single_outlet_stl_check,
        },
    }
    (output / "geometry_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="new output directory (never overwritten by this CLI)",
    )
    parser.add_argument("--tank-diameter-m", type=float, default=0.900)
    parser.add_argument(
        "--tank-axis",
        choices=("horizontal", "vertical"),
        default="horizontal",
        help="vessel axis; vertical placement is provisional and documented in the geometry record",
    )
    parser.add_argument("--water-volume-m3", type=float, default=1.350)
    parser.add_argument(
        "--headspace-ratio",
        type=float,
        default=0.225,
        help="headspace volume / liquid volume per tank",
    )
    parser.add_argument("--intermediate-width-m", type=float, default=0.500)
    parser.add_argument("--lamella-count", type=int, default=4)
    parser.add_argument("--lamella-thickness-m", type=float, default=0.004)
    parser.add_argument(
        "--lamella-leading-edge",
        choices=("square", "rounded"),
        default="square",
        help="square preserves historical divider output; rounded builds finite capped solids",
    )
    parser.add_argument(
        "--lamella-nose-radius-m",
        type=float,
        default=None,
        help="rounded leading semicircle radius; defaults to half the divider thickness",
    )
    parser.add_argument(
        "--post-rise-straight-m",
        type=float,
        default=POST_RISE_STRAIGHT_DEFAULT_M,
        help="straight distance after the fixed rise-bend end at x=3.8 m",
    )
    parser.add_argument(
        "--transition-and-mouth-length-m",
        type=float,
        default=TRANSITION_AND_MOUTH_DEFAULT_M,
        help="distance from transition inlet to mouth; scales all downstream stations",
    )
    parser.add_argument(
        "--pipe-transition-join",
        choices=PIPE_TRANSITION_JOIN_MODES,
        default="legacy-overlap",
        help=(
            "legacy-overlap preserves the historical pipe tail; flush-at-inlet makes the pipe "
            "terminate at the circular transition inlet"
        ),
    )
    args = parser.parse_args()
    args.effective_lamella_nose_radius_m = (
        args.lamella_nose_radius_m
        if args.lamella_nose_radius_m is not None
        else args.lamella_thickness_m / 2
        if args.lamella_leading_edge == "rounded"
        else None
    )
    errors = validate_inputs(args)
    if errors:
        parser.error("; ".join(errors))
    return args


def validate_inputs(args) -> list[str]:
    """Reject invalid numeric geometry inputs before creating output files."""
    positive = (
        ("--tank-diameter-m", args.tank_diameter_m),
        ("--water-volume-m3", args.water_volume_m3),
        ("--headspace-ratio", args.headspace_ratio),
        ("--intermediate-width-m", args.intermediate_width_m),
        ("--lamella-thickness-m", args.lamella_thickness_m),
        ("--transition-and-mouth-length-m", args.transition_and_mouth_length_m),
    )
    errors = [
        f"{name} must be finite and greater than zero"
        for name, value in positive
        if not math.isfinite(value) or value <= 0
    ]
    if args.lamella_count < 1:
        errors.append("--lamella-count must be at least 1")
    if args.lamella_leading_edge == "rounded":
        radius = args.effective_lamella_nose_radius_m
        if not math.isfinite(radius) or radius <= 0:
            errors.append("rounded divider nose radius must be finite and greater than zero")
        elif not math.isclose(2 * radius, args.lamella_thickness_m, rel_tol=0, abs_tol=1e-9):
            errors.append(
                "a semicircular leading nose requires --lamella-nose-radius-m = thickness / 2"
            )
    elif args.lamella_nose_radius_m is not None:
        errors.append("--lamella-nose-radius-m requires --lamella-leading-edge rounded")
    if not math.isfinite(args.post_rise_straight_m) or args.post_rise_straight_m < 0:
        errors.append("--post-rise-straight-m must be finite and nonnegative")
    if (
        math.isfinite(args.post_rise_straight_m)
        and args.post_rise_straight_m >= 0
        and math.isfinite(args.transition_and_mouth_length_m)
        and args.transition_and_mouth_length_m > 0
    ):
        stations = downstream_stations(
            args.post_rise_straight_m, args.transition_and_mouth_length_m
        )
        ordered_x = (
            stations.transition_inlet_x_m,
            stations.lamella_start_x_m,
            stations.transition_intermediate_x_m,
            stations.transition_end_x_m,
            stations.mouth_x_m,
        )
        if any(right <= left for left, right in zip(ordered_x, ordered_x[1:])):
            errors.append("downstream stations must be finite and strictly increasing")
        if stations.transition_inlet_x_m < BEND_X_M[-1]:
            errors.append("transition inlet must not be upstream of the fixed rise-bend end")
        if args.pipe_transition_join == "legacy-overlap" and not (
            stations.transition_inlet_x_m < stations.pipe_overlap_end_x_m < stations.mouth_x_m
        ):
            errors.append("mapped pipe/transition overlap must lie between the inlet and mouth")
    if math.isfinite(args.tank_diameter_m) and args.tank_diameter_m > 0:
        if args.tank_diameter_m / 2 <= max(abs(branch["port_y_offset_m"]) for branch in BRANCHES):
            errors.append("--tank-diameter-m / 2 must exceed the fixed branch port offset 0.37 m")
    if args.lamella_count >= 1 and math.isfinite(args.lamella_thickness_m):
        for station, width in (
            ("divider-start", 0.485),
            ("intermediate", args.intermediate_width_m),
            ("mouth", MOUTH_W_M),
        ):
            if math.isfinite(width) and width > 0:
                clear = (width - args.lamella_count * args.lamella_thickness_m) / (
                    args.lamella_count + 1
                )
                if clear <= 0:
                    errors.append(
                        f"divider thickness/count leave no clear passage at the {station} station"
                    )
    return errors


def main():
    args = parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit(f"Refusing to overwrite nonempty output directory: {args.output_dir}")
    summary = generate(args)
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "tank_capacity_each_m3": summary["tank_metrics"]["capacity_m3_each"],
                "tank_axis": summary["assumptions"]["tank_axis"],
                "tank_length_m": summary["tank_metrics"]["derived_flat_cylinder_length_m"],
                "post_rise_straight_m": summary["assumptions"]["post_rise_straight_m_assumed"],
                "transition_and_mouth_length_m": summary["assumptions"][
                    "transition_and_mouth_length_m_assumed"
                ],
                "mouth_x_m": summary["assumptions"]["downstream_stations_x_m"]["mouth"],
                "mouths": summary["topology"]["mouth_count"],
                "dividers": summary["topology"]["divider_count"],
                "section_samples": summary["area_metrics"][
                    "section_samples_one_transition_only_m2"
                ],
                "images": summary["artifacts"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
