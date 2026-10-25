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
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe, BRepOffsetAPI_ThruSections
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.collections import Array1_gp_Pnt, HSequence_TopoDS_Shape
from OCP.Geom import Geom_BezierCurve
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pln, gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.StlAPI import StlAPI_Writer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound

# Fixed topology and centerline stations retained from the reviewed
# two-tank/four-mouth reconstruction. The dimensions are assumptions unless
# stated as user-confirmed in the project hardware notes.
TANK_Y = (-0.550, 0.550)
TANK_Z = 1.250
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
):
    radius = pipe_diameter_m / 2
    y_pipe = y_tank + branch["pipe_lateral_offset_m"]
    z_out = branch["mouth_z_m"]
    port_offset = branch["port_y_offset_m"]
    tank_r = tank_diameter_m / 2
    z_port = TANK_Z - math.sqrt(tank_r**2 - port_offset**2)
    p0 = [0.250, y_tank + 0.30 * port_offset, TANK_Z - 0.100]
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
    spine.Add(
        BRepBuilderAPI_MakeEdge(
            gp_Pnt(*q3), gp_Pnt(stations.pipe_overlap_end_x_m, y_pipe, z_out)
        ).Edge()
    )
    if not spine.IsDone():
        raise RuntimeError("Could not form connected branch centerline")
    tangent = np.asarray(p1, dtype=float) - np.asarray(p0, dtype=float)
    tangent /= np.linalg.norm(tangent)
    profile = BRepBuilderAPI_MakeFace(make_circle_wire(p0, tangent.tolist(), radius)).Face()
    pipe = BRepOffsetAPI_MakePipe(spine.Wire(), profile)
    if not pipe.IsDone() or len(solids(pipe.Shape())) != 1:
        raise RuntimeError("Could not sweep a single connected branch pipe")
    return pipe.Shape(), y_pipe


def aligned_ruled_transition(
    y_pipe: float,
    y_mouth: float,
    z: float,
    intermediate_width_m: float,
    stations: DownstreamStations,
):
    """Four-arc ruled circle-to-rectangle loft used by the approved geometry."""
    circle = gp_Circ(
        gp_Ax2(
            gp_Pnt(stations.transition_inlet_x_m, y_pipe, z),
            gp_Dir(1, 0, 0),
            gp_Dir(0, 1, 0),
        ),
        0.150,
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


def write_stl(shape, path: Path):
    BRepMesh_IncrementalMesh(shape, 0.004, False, 0.15, True).Perform()
    writer = StlAPI_Writer()
    if not writer.Write(shape, str(path)):
        raise RuntimeError(f"STL export failed for {path}")


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
    mouth_x_m: float,
    divider_count: int,
    divider_thickness_m: float,
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
    ax.set_xlim(0, mouth_x_m)
    ax.set_ylim(-1.15, 1.15)
    ax.set_zlim(0.25, 1.80)
    ax.set_box_aspect((mouth_x_m, 2.30, 1.55))
    ax.view_init(elev=28, azim=-57)
    ax.set_xlabel("X · discharge (+X), m")
    ax.set_ylabel("Y · tank columns / mouth width, m")
    ax.set_zlabel("Z · vertical, m")
    ax.set_title(
        "Reconstructed two-tank / four-outlet fluid envelope\n"
        f"Grey: envelope · amber: {divider_count} assumed "
        f"{1000 * divider_thickness_m:g} mm fitted divider solids"
    )
    ax.grid(False)
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


def generate(args) -> dict:
    stations = downstream_stations(args.post_rise_straight_m, args.transition_and_mouth_length_m)
    output = args.output_dir.resolve()
    geometry_dir = output / "geometry"
    divider_dir = geometry_dir / "mid_surfaces"
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
    transition_rows = []
    line_volume_records = []
    plate_solids = []
    mid_faces = []
    divider_records = []
    for tank_index, y_tank in enumerate(TANK_Y, start=1):
        tank = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(0.0, y_tank, TANK_Z), gp_Dir(1, 0, 0)),
            tank_r,
            tank_length,
        ).Shape()
        if not BRepCheck_Analyzer(tank).IsValid():
            raise RuntimeError(f"Tank {tank_index} failed BREP validity")
        envelope_components.append(tank)
        tank_records.append(
            {
                "tank_index": tank_index,
                "center_y_m": y_tank,
                "volume_m3": volume(tank),
                "length_m": tank_length,
                "bounds_m": bounds(tank),
            }
        )
        tank_line_volume = 0.0
        for branch in BRANCHES:
            branch_shape, y_pipe = branch_pipe(
                y_tank, branch, args.tank_diameter_m, PIPE_ID_M, stations
            )
            y_mouth = y_tank
            transition = aligned_ruled_transition(
                y_pipe, y_mouth, branch["mouth_z_m"], args.intermediate_width_m, stations
            )
            envelope_components.extend((branch_shape, transition))
            transition_rows.append((tank_index, branch, y_pipe, transition))

            pipe_transition_overlap = require_common(branch_shape, transition)
            pipe_inside_tank = require_common(branch_shape, tank)
            transition_inside_tank = require_common(transition, tank)
            overlap_inside_tank = require_common(pipe_transition_overlap, tank)
            pipe_volume = volume(branch_shape)
            transition_volume = volume(transition)
            overlap_volume = volume(pipe_transition_overlap)
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
                stock = make_tall_plate(rows, args.lamella_thickness_m)
                fitted_plate = require_common(stock, transition)
                if len(solids(fitted_plate)) != 1 or not BRepCheck_Analyzer(fitted_plate).IsValid():
                    raise RuntimeError(
                        f"Fitted divider failed: tank{tank_index}/{branch['name']}/{divider_index + 1}"
                    )
                plate_solids.append(fitted_plate)

                clipped_segments = []
                for row0, row1 in zip(rows, rows[1:]):
                    clipped = require_common(make_midface(row0, row1, MOUTH_H_M), transition)
                    if not BRepCheck_Analyzer(clipped).IsValid() or surface_area(clipped) <= 1e-10:
                        raise RuntimeError(
                            "Clipped divider mid-surface segment is invalid or empty"
                        )
                    clipped_segments.append(clipped)
                    mid_faces.append(clipped)
                label = f"tank{tank_index:02d}_{branch['name']}_divider{divider_index + 1:02d}"
                group_path = divider_dir / f"{label}.step"
                write_step(compound(clipped_segments), group_path)
                divider_records.append(
                    {
                        "label": label,
                        "candidate_face_zone": f"baffle_{label}",
                        "tank_index": tank_index,
                        "branch": branch["name"],
                        "divider_index": divider_index + 1,
                        "segment_count": len(clipped_segments),
                        "stations_x_m": list(xs),
                        "centerline_points_xyz_m": [list(row) for row in rows],
                        "step": group_path.relative_to(output).as_posix(),
                    }
                )
        tank_records[-1]["downstream_line_volume_m3"] = tank_line_volume

    envelope = compound(envelope_components)
    finite_dividers = compound(plate_solids)
    zero_thickness = compound(mid_faces)
    envelope_step = geometry_dir / "two_tank_four_outlet_aligned_ruled_envelope.step"
    finite_step = geometry_dir / "four_mouth_fitted_divider_solids.step"
    mid_step = geometry_dir / "four_mouth_zero_thickness_divider_surfaces.step"
    write_step(envelope, envelope_step)
    write_step(finite_dividers, finite_step)
    write_step(zero_thickness, mid_step)
    envelope_check = step_readback(envelope_step)
    finite_check = step_readback(finite_step)
    if envelope_check["solid_count"] != 10 or not envelope_check["all_solids_valid"]:
        raise RuntimeError(f"Envelope STEP round-trip failed: {envelope_check}")
    expected_plate_count = len(transition_rows) * args.lamella_count
    if finite_check["solid_count"] != expected_plate_count or not finite_check["all_solids_valid"]:
        raise RuntimeError(f"Divider STEP round-trip failed: {finite_check}")

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
    dividers_stl = stl_dir / "fitted_dividers.stl"
    write_stl(envelope, envelope_stl)
    write_stl(finite_dividers, dividers_stl)
    assembly_png = figures_dir / "two_tank_four_outlet_assembly.png"
    sections_png = figures_dir / "transition_cross_sections.png"
    render_assembly(
        envelope_stl,
        dividers_stl,
        assembly_png,
        stations.mouth_x_m,
        args.lamella_count,
        args.lamella_thickness_m,
    )
    render_sections(
        sections_png,
        args.intermediate_width_m,
        args.lamella_count,
        args.lamella_thickness_m,
        stations,
    )

    sections_path = output / "transition_sections.csv"
    with sections_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=sections[0].keys())
        writer.writeheader()
        writer.writerows(sections)
    mid_index = output / "divider_index.json"
    mid_index.write_text(
        json.dumps(
            {
                "status": "geometry-only zero-thickness divider candidates; no mesh faceZones created",
                "count": len(divider_records),
                "surface_segment_count": len(mid_faces),
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
        "status": "reproducible provisional geometry source smoke generation; no mesh or CFD",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "generator": generator_path.name,
        "generator_sha256": sha256(generator_path),
        "runtime": {"python": platform.python_version(), "packages": package_versions},
        "units": "SI metres; +X discharge; Y separates tanks and spans mouth width; +Z up",
        "assumptions": {
            "tank_axis": "+X horizontal, flat-ended cylinder",
            "tank_diameter_m": args.tank_diameter_m,
            "water_volume_m3_per_tank": args.water_volume_m3,
            "headspace_to_water_volume_ratio": args.headspace_ratio,
            "valve_and_pipe_id_m": VALVE_D_M,
            "pipe_id_basis": "assumed equal to reported valve diameter",
            "mouth_width_m": MOUTH_W_M,
            "mouth_height_m": MOUTH_H_M,
            "post_rise_straight_m_assumed": args.post_rise_straight_m,
            "transition_and_mouth_length_m_assumed": args.transition_and_mouth_length_m,
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
                "offsets from x=4.0 m scale by transition_and_mouth_length/1.8 m; pipe overlap "
                "offset 0.2 m scales by the same factor as an internal pipe/transition BREP overlap, "
                "not as an additional exposed straight length."
            ),
            "intermediate_width_m_assumed": args.intermediate_width_m,
            "divider_count_per_mouth": args.lamella_count,
            "divider_thickness_m_assumed_not_measured": args.lamella_thickness_m,
            "divider_start_x_m_assumed": stations.lamella_start_x_m,
            "divider_geometry": (
                f"{args.lamella_count} equally spaced plates fanned through the aligned ruled "
                f"transition; {args.lamella_thickness_m:g} m thickness is assumed. "
                "Zero-thickness candidates are separate from fitted display solids."
            ),
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
            "tank_count": len(TANK_Y),
            "mouth_count": len(transition_rows),
            "envelope_solid_count": envelope_check["solid_count"],
            "divider_solid_count": finite_check["solid_count"],
            "divider_count": len(divider_records),
            "zero_thickness_segment_count": len(mid_faces),
            "passages_per_mouth": args.lamella_count + 1,
        },
        "area_metrics": {
            "pipe_area_m2": pipe_area,
            "gross_mouth_area_m2_each": mouth_area,
            "nominal_divider_open_mouth_area_m2_each": mouth_open_area,
            "section_samples_one_transition_only_m2": sections,
            "endpoint_probe_to_pipe_area_ratio": pipe_opening_ratio,
            "continuous_minimum_area": "not proven; section values are discrete BREP slab samples",
        },
        "artifacts": {
            "envelope_step": envelope_step.relative_to(output).as_posix(),
            "fitted_dividers_step": finite_step.relative_to(output).as_posix(),
            "zero_thickness_surfaces_step": mid_step.relative_to(output).as_posix(),
            "divider_index": mid_index.relative_to(output).as_posix(),
            "assembly_png": assembly_png.relative_to(output).as_posix(),
            "section_png": sections_png.relative_to(output).as_posix(),
        },
        "roundtrip": {"envelope": envelope_check, "fitted_dividers": finite_check},
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
    args = parser.parse_args()
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
        if not (stations.transition_inlet_x_m < stations.pipe_overlap_end_x_m < stations.mouth_x_m):
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
