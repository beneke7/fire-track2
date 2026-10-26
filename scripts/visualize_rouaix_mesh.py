#!/usr/bin/env pvpython
"""Extract and CPU-plot the central z=0 cell-edge slice of Rouaix meshes."""

from __future__ import annotations

import argparse
import gc
import json
import math
import re
from pathlib import Path

from paraview import servermanager
from paraview.simple import Delete, ExtractEdges, OpenFOAMReader, Slice
from PIL import Image, ImageDraw, ImageFont

Z_PLANE_M = 0.0
NOZZLE_DISTANCE_FROM_INLET_M = 2.5  # Rouaix PDF p. 7, section 3.2
PAPER_EXTENT_M = (20.0, 11.0)
VIEWS = {
    "overview": ((1800, 1000), (170, 90, 1730, 850)),
    "nozzle": ((1600, 1080), (170, 90, 1510, 930)),
    "wall": ((1600, 520), (150, 90, 1510, 350)),
    "wall-inset": ((1600, 520), (150, 90, 1510, 350)),
}
SPACING_WINDOWS = {
    "near_nozzle": (2.60, 2.80, -0.20, 0.00),
    "fine_tube_center": (4.35, 4.55, -1.99, -1.79),
    "medium_only": (4.35, 4.55, -4.10, -3.90),
}


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", required=True, help="finished OpenFOAM case directory or .foam marker"
    )
    parser.add_argument("--label", default="Mac Rouaix mesh")
    parser.add_argument(
        "--check-mesh-log", required=True, help="final native checkMesh log for this case"
    )
    parser.add_argument("--reference-case", help="optional prior mesh case, processed sequentially")
    parser.add_argument("--reference-check-mesh-log", help="optional checkMesh log for prior mesh")
    parser.add_argument("--outdir", required=True, help="new output directory")
    return parser.parse_args()


def marker(path: str) -> Path:
    source = Path(path).expanduser().resolve()
    if source.is_dir():
        files = sorted(source.glob("*.foam"))
        if len(files) == 1:
            return files[0]
        raise ValueError(f"Expected one .foam marker in {source}; found {len(files)}")
    if source.is_file() and source.suffix == ".foam":
        return source
    raise FileNotFoundError(source)


def font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def mapping(window, rect, inlet_x, wall_y):
    x0, x1, y0, y1 = window
    left, top, right, bottom = rect
    vals = (*window, *rect, inlet_x, wall_y)
    if (
        not all(math.isfinite(v) for v in vals)
        or x1 <= x0
        or y1 <= y0
        or right <= left
        or bottom <= top
    ):
        raise ValueError(f"Invalid physical or pixel bounds: {window}, {rect}")
    scale = min((right - left) / (x1 - x0), (bottom - top) / (y1 - y0))
    pw, ph = (x1 - x0) * scale, (y1 - y0) * scale
    px, py = left + (right - left - pw) / 2, top + (bottom - top - ph) / 2

    def project(point):
        return round(px + (point[0] - inlet_x - x0) * scale), round(
            py + (y1 - (point[1] - wall_y)) * scale
        )

    return project, (px, py, px + pw, py + ph), scale


def clip(a, b, box):
    """Liang-Barsky line crop in the same physical x/y frame as Figure 4."""
    x0, x1, y0, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    enter, leave = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0.0:
            if q < 0.0:
                return None
            continue
        t = q / p
        if p < 0.0:
            if t > leave:
                return None
            enter = max(enter, t)
        else:
            if t < enter:
                return None
            leave = min(leave, t)
    if enter > leave:
        return None
    return ((a[0] + enter * dx, a[1] + enter * dy), (a[0] + leave * dx, a[1] + leave * dy))


def coordinate_self_check():
    project, plot, _ = mapping((0, 2, -1, 0), (0, 0, 200, 100), 10, 5)
    assert project((10, 5, 0)) == (0, 0) and project((12, 4, 0)) == (200, 100)
    assert plot == (0, 0, 200, 100)
    assert clip((-1, -0.5), (3, -0.5), (0, 2, -1, 0)) == ((0, -0.5), (2, -0.5))
    assert clip((-2, -0.5), (-1, -0.5), (0, 2, -1, 0)) is None


def windows(domain):
    x0, x1, y0, y1 = domain
    n = NOZZLE_DISTANCE_FROM_INLET_M
    return {
        "overview": (x0, x1, y0, y1),
        "nozzle": (n - 0.85, n + 0.85, max(y0, -1.3), min(y1, 0.15)),
        "wall": (n + 0.6, n + 2.6, max(y0, -0.25), min(y1, 0.05)),
        "wall-inset": (n + 0.6, n + 0.8, max(y0, -0.03), min(y1, 0.02)),
    }


def draw_axes(context, plane_z):
    draw, image = context["draw"], context["image"]
    x0, x1, y0, y1 = context["window"]
    px0, py0, px1, py1 = context["plot"]
    axis = (74, 82, 88)
    draw.rectangle((px0, py0, px1, py1), outline=axis, width=2)
    xspan, yspan = x1 - x0, y1 - y0
    xstep = 5 if xspan > 10 else (0.5 if xspan > 1 else 0.05)
    ystep = 5 if yspan > 8 else (0.5 if yspan > 0.5 else (0.1 if yspan > 0.08 else 0.01))
    tick = font(17)
    for value in _ticks(x0, x1, xstep):
        x = context["project"]((value + context["inlet_x"], context["wall_y"], plane_z))[0]
        draw.line((x, py1, x, py1 + 8), fill=axis, width=2)
        draw.text((x - 12, py1 + 12), f"{value:g}", fill=axis, font=tick)
    for value in _ticks(y0, y1, ystep):
        y = context["project"]((context["inlet_x"], value + context["wall_y"], plane_z))[1]
        draw.line((px0 - 8, y, px0, y), fill=axis, width=2)
        draw.text((context["rect"][0] - 58, y - 10), f"{value:g}", fill=axis, font=tick)
    draw.text(
        ((px0 + px1) / 2 - 86, context["rect"][3] + 36),
        "x from inlet (m)",
        fill=axis,
        font=font(20),
    )
    draw.text(
        (context["rect"][0] - 112, context["rect"][1] - 24),
        "y - wall (m)",
        fill=axis,
        font=font(20),
    )
    draw.text(
        (38, image.height - 32),
        f"Computed cell edges · z={plane_z:g} m · equal x/y scale",
        fill=axis,
        font=font(16),
    )


def _ticks(start, end, step):
    first = math.ceil(start / step) * step
    n = max(0, int(math.floor((end - first) / step + 1e-9)) + 1)
    return (first + i * step for i in range(n))


def quantile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def slug(value):
    return "-".join(value.lower().replace(".", " ").split())


def polydata_blocks(obj):
    if obj.IsA("vtkPolyData"):
        yield obj
    elif hasattr(obj, "NewIterator"):
        iterator = obj.NewIterator()
        iterator.SkipEmptyNodesOn()
        iterator.InitTraversal()
        while not iterator.IsDoneWithTraversal():
            yield from polydata_blocks(iterator.GetCurrentDataObject())
            iterator.GoToNextItem()
    else:
        raise TypeError(f"Expected PolyData or composite edge output, got {obj.GetClassName()}")


def native_cell_count(log_path):
    text = Path(log_path).expanduser().resolve().read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"^\s*cells:\s*(\d+)\s*$", text, flags=re.MULTILINE)
    if not matches:
        raise ValueError(f"No native cells count found in checkMesh log {log_path}")
    return int(matches[-1])


def extract_case(case_marker, label, outdir, checkmesh_cells):
    reader = OpenFOAMReader(registrationName=slug(label), FileName=str(case_marker))
    reader.SkipZeroTime = 0
    reader.MeshRegions = ["internalMesh"]
    reader_decomposes_polyhedra = hasattr(reader, "Decomposepolyhedra")
    if reader_decomposes_polyhedra:
        reader.Decomposepolyhedra = 0
    if hasattr(reader, "CellArrays"):
        reader.CellArrays = []
    reader.UpdatePipeline()
    info = reader.GetDataInformation()
    bounds = tuple(float(v) for v in info.GetBounds())
    if not all(math.isfinite(v) for v in bounds):
        raise ValueError(f"{label}: non-finite mesh bounds {bounds}")
    reader_cells = int(info.GetNumberOfCells())
    if reader_cells <= 0:
        raise ValueError(f"{label}: reader returned no mesh cells")
    inlet_x, wall_y = bounds[0], bounds[3]
    domain = (0.0, bounds[1] - inlet_x, bounds[2] - wall_y, 0.0)

    cut = Slice(registrationName=f"{slug(label)}_z0", Input=reader)
    cut.SliceType = "Plane"
    cut.SliceType.Origin = [0.0, 0.0, Z_PLANE_M]
    cut.SliceType.Normal = [0.0, 0.0, 1.0]
    if not hasattr(cut, "Triangulatetheslice"):
        raise RuntimeError(
            "ParaView Slice lacks Triangulatetheslice; refusing to treat triangulated cuts as native edges"
        )
    cut.Triangulatetheslice = 0
    cut.UpdatePipeline()
    slice_cells = int(cut.GetDataInformation().GetNumberOfCells())
    edges = ExtractEdges(registrationName=f"{slug(label)}_edges", Input=cut)
    edges.UpdatePipeline()
    edge_cells = int(edges.GetDataInformation().GetNumberOfCells())
    if edge_cells <= 0:
        raise ValueError(f"{label}: central-plane cut produced no edges")

    fetched = servermanager.Fetch(edges)
    blocks = list(polydata_blocks(fetched))
    if not blocks:
        raise ValueError(f"{label}: fetched edge output contains no PolyData blocks")

    contexts = {}
    for name, window in windows(domain).items():
        size, rect = VIEWS[name]
        image = Image.new("RGB", size, (250, 249, 246))
        draw = ImageDraw.Draw(image)
        title = f"{label} - {name.replace('-', ' ')} - z=0 m"
        draw.text((38, 24), title, fill=(28, 35, 42), font=font(28))
        project, plot, scale = mapping(window, rect, inlet_x, wall_y)
        contexts[name] = {
            "image": image,
            "draw": draw,
            "project": project,
            "plot": plot,
            "rect": rect,
            "window": window,
            "scale": scale,
            "inlet_x": inlet_x,
            "wall_y": wall_y,
            "segments": 0,
        }
    spacing = {name: {"x": [], "y": []} for name in SPACING_WINDOWS}

    # Traverse all central-plane edges once; crop each segment before pixel mapping.
    for poly in blocks:
        for i in range(poly.GetNumberOfCells()):
            ids = poly.GetCell(i).GetPointIds()
            for j in range(ids.GetNumberOfIds() - 1):
                a0 = poly.GetPoint(ids.GetId(j))
                b0 = poly.GetPoint(ids.GetId(j + 1))
                a = (a0[0] - inlet_x, a0[1] - wall_y)
                b = (b0[0] - inlet_x, b0[1] - wall_y)
                dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
                length = math.hypot(dx, dy)
                midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                tolerance = max(1e-8, length * 0.01)
                for name, (sx0, sx1, sy0, sy1) in SPACING_WINDOWS.items():
                    if sx0 <= midpoint[0] <= sx1 and sy0 <= midpoint[1] <= sy1:
                        if dy <= tolerance:
                            spacing[name]["x"].append(dx)
                        elif dx <= tolerance:
                            spacing[name]["y"].append(dy)
                for context in contexts.values():
                    cropped = clip(a, b, context["window"])
                    if cropped is None:
                        continue
                    p0, p1 = cropped
                    pixel0 = context["project"]((p0[0] + inlet_x, p0[1] + wall_y, Z_PLANE_M))
                    pixel1 = context["project"]((p1[0] + inlet_x, p1[1] + wall_y, Z_PLANE_M))
                    context["draw"].line((pixel0, pixel1), fill=(45, 52, 58), width=1)
                    context["segments"] += 1

    plots = {}
    for name, context in contexts.items():
        draw_axes(context, Z_PLANE_M)
        image_path = outdir / f"{slug(label)}-{name}.png"
        if image_path.exists():
            raise FileExistsError(image_path)
        context["image"].save(image_path, format="PNG", optimize=True)
        plots[name] = {
            "path": str(image_path),
            "x_from_inlet_m": context["window"][:2],
            "y_from_wall_m": context["window"][2:],
            "line_segments_drawn": context["segments"],
        }
    spacing_summary = {
        name: {
            "sample_box_x_from_inlet_y_from_wall_m": box,
            "method": "central z=0 slice edge lengths; midpoint inside box; axis-aligned within 1% of segment length",
            "x_edge_count": len(spacing[name]["x"]),
            "x_median_m": quantile(spacing[name]["x"], 0.5),
            "x_p10_m": quantile(spacing[name]["x"], 0.1),
            "x_p90_m": quantile(spacing[name]["x"], 0.9),
            "y_edge_count": len(spacing[name]["y"]),
            "y_median_m": quantile(spacing[name]["y"], 0.5),
            "y_p10_m": quantile(spacing[name]["y"], 0.1),
            "y_p90_m": quantile(spacing[name]["y"], 0.9),
        }
        for name, box in SPACING_WINDOWS.items()
    }

    result = {
        "label": label,
        "case_marker": str(case_marker),
        "native_checkMesh_cells": checkmesh_cells,
        "paraview_reader_cells": reader_cells,
        "reader_count_matches_checkMesh": reader_cells == checkmesh_cells,
        "reader_decompose_polyhedra": 0 if reader_decomposes_polyhedra else "property unavailable",
        "cell_count_note": "checkMesh is authoritative; ParaView count is diagnostic and may differ if polyhedra are decomposed.",
        "bounds_global_m": bounds,
        "domain_x_from_inlet_y_from_wall_m": domain,
        "slice_z_m": Z_PLANE_M,
        "slice_triangulated": False,
        "slice_cells": slice_cells,
        "slice_edge_cells": edge_cells,
        "plots": plots,
        "directional_spacing_samples": spacing_summary,
    }
    Delete(edges)
    Delete(cut)
    Delete(reader)
    del blocks, fetched
    gc.collect()
    return result


def main():
    coordinate_self_check()
    options = args()
    outdir = Path(options.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = outdir / "mesh-visualization-metrics.json"
    if manifest.exists():
        raise FileExistsError(manifest)
    cases = [
        extract_case(
            marker(options.case),
            options.label,
            outdir,
            native_cell_count(options.check_mesh_log),
        )
    ]
    if options.reference_case:
        reference_cells = (
            native_cell_count(options.reference_check_mesh_log)
            if options.reference_check_mesh_log
            else None
        )
        cases.append(
            extract_case(
                marker(options.reference_case), "35.19M-cell baseline", outdir, reference_cells
            )
        )
    data = {
        "cases": cases,
        "plot_coordinate_self_check": "PASS: finite bounds, equal metre scale, known corners, crossing/outside clipping",
        "paper_reference": {
            "source": "Rouaix et al., Fig. 4, PDF p. 7 / printed p. 6",
            "paper_extent_m": {"x": PAPER_EXTENT_M[0], "y": PAPER_EXTENT_M[1]},
            "paper_mesh1_callouts_m": {"fine": 0.016, "surrounding": 0.05},
            "comparison_note": "Keep the measured case height; do not stretch it to Figure 4's 11 m label.",
        },
        "method": "OpenFOAMReader geometry only -> ParaView Slice(z=0) -> ExtractEdges -> CPU Pillow raster; x/y spacing is sampled from axis-aligned central-slice segments at explicitly recorded boxes; no RenderView, OpenGL, or solver fields.",
    }
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
