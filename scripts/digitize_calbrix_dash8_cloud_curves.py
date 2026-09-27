#!/usr/bin/env python3
"""Digitize Calbrix Dash-8 alpha_L=0.001 curves from the supplied paper PDF.

This extracts colored plotted curves from page rasters. It does not recover
the authors' simulation arrays or provide a solver boundary condition.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PDF = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
DEFAULT_OUTPUT = ROOT / "data/derived/calbrix_dash8_cloud_curves.csv"
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"
RENDER_DPI = 300
PPM_WIDTH = 2481
PPM_HEIGHT = 3249

FIELDNAMES = (
    "figure",
    "pdf_page",
    "journal_page",
    "panel",
    "aircraft",
    "alpha_l_threshold",
    "series_id",
    "time_s",
    "time_candidates_s",
    "time_status",
    "independent_variable",
    "independent_value",
    "independent_unit",
    "dependent_variable",
    "dependent_value",
    "dependent_unit",
    "segment_id",
    "branch_id",
    "point_index",
    "read_bound_independent",
    "read_bound_dependent",
)


@dataclass(frozen=True)
class CurveSpec:
    figure: int
    pdf_page: int
    journal_page: int
    panel: str
    series_id: str
    time_s: float | None
    time_candidates_s: str
    time_status: str
    independent_variable: str
    independent_unit: str
    independent_min: float
    independent_max: float
    dependent_variable: str
    dependent_unit: str
    dependent_min: float
    dependent_max: float
    color: str
    traversal: str
    x0_px: float
    x1_px: float
    y0_px: float
    y1_px: float
    min_component_area: int
    min_traversal_span_px: int


SPECS = (
    CurveSpec(
        figure=6,
        pdf_page=7,
        journal_page=1521,
        panel="b",
        series_id="dash8_t0.5s",
        time_s=0.5,
        time_candidates_s="0.5",
        time_status="reported",
        independent_variable="y",
        independent_unit="m",
        independent_min=0.0,
        independent_max=2.0,
        dependent_variable="Z",
        dependent_unit="m",
        dependent_min=0.0,
        dependent_max=3.0,
        color="blue",
        traversal="x",
        x0_px=1359.0,
        x1_px=2208.0,
        y0_px=340.0,
        y1_px=1015.0,
        min_component_area=5000,
        min_traversal_span_px=500,
    ),
    CurveSpec(
        figure=7,
        pdf_page=8,
        journal_page=1522,
        panel="single",
        series_id="dash8_simulation_t0.5s",
        time_s=0.5,
        time_candidates_s="0.5",
        time_status="reported",
        independent_variable="y_over_Lc",
        independent_unit="1",
        independent_min=0.0,
        independent_max=2.0,
        dependent_variable="Z_over_Lc",
        dependent_unit="1",
        dependent_min=0.0,
        dependent_max=2.0,
        color="blue",
        traversal="x",
        x0_px=313.0,
        x1_px=1160.0,
        y0_px=291.0,
        y1_px=935.0,
        min_component_area=1000,
        min_traversal_span_px=100,
    ),
    CurveSpec(
        figure=8,
        pdf_page=9,
        journal_page=1523,
        panel="b",
        series_id="dash8_time_conflict",
        time_s=None,
        time_candidates_s="body=0.5;caption=1.0",
        time_status="conflict",
        independent_variable="z",
        independent_unit="m",
        independent_min=0.0,
        independent_max=3.5,
        dependent_variable="L",
        dependent_unit="m",
        dependent_min=0.0,
        dependent_max=6.0,
        color="blue",
        traversal="y",
        x0_px=1238.0,
        x1_px=2096.0,
        y0_px=445.0,
        y1_px=1113.0,
        min_component_area=5000,
        min_traversal_span_px=500,
    ),
)

FIG9_TIMES = (
    ("red", "dash8_t0.5s", 0.5),
    ("blue", "dash8_t1.0s", 1.0),
    ("green", "dash8_t1.5s", 1.5),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ppm_token(data: bytes, offset: int) -> tuple[bytes, int]:
    length = len(data)
    while offset < length:
        if data[offset] in b" \t\r\n\v\f":
            offset += 1
        elif data[offset] == ord("#"):
            newline = data.find(b"\n", offset)
            if newline < 0:
                raise ValueError("unterminated comment in PPM header")
            offset = newline + 1
        else:
            break
    start = offset
    while offset < length and data[offset] not in b" \t\r\n\v\f":
        offset += 1
    if start == offset:
        raise ValueError("unexpected end of PPM header")
    return data[start:offset], offset


def _read_ppm(path: Path) -> np.ndarray:
    data = path.read_bytes()
    offset = 0
    magic, offset = _ppm_token(data, offset)
    width_token, offset = _ppm_token(data, offset)
    height_token, offset = _ppm_token(data, offset)
    max_token, offset = _ppm_token(data, offset)
    if magic != b"P6" or int(max_token) != 255:
        raise ValueError(f"expected 8-bit binary RGB PPM, got {magic!r}/{max_token!r}")
    width, height = int(width_token), int(height_token)
    # Consume the single header delimiter (or CRLF) without mistaking a pixel
    # whose byte equals whitespace for additional header whitespace.
    if data[offset : offset + 2] == b"\r\n":
        offset += 2
    elif offset < len(data) and data[offset] in b" \t\r\n\v\f":
        offset += 1
    pixels = np.frombuffer(data, dtype=np.uint8, offset=offset)
    if pixels.size != width * height * 3:
        raise ValueError("PPM pixel count does not match its header")
    return pixels.reshape(height, width, 3)


def _render_page(pdf_path: Path, page: int, directory: Path) -> np.ndarray:
    prefix = directory / f"calbrix_page_{page}"
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page),
            "-l",
            str(page),
            "-r",
            str(RENDER_DPI),
            "-singlefile",
            str(pdf_path),
            str(prefix),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    image = _read_ppm(prefix.with_suffix(".ppm"))
    if image.shape != (PPM_HEIGHT, PPM_WIDTH, 3):
        raise ValueError(
            f"page {page} rendered as {image.shape[1]}x{image.shape[0]}; "
            f"expected {PPM_WIDTH}x{PPM_HEIGHT} at {RENDER_DPI} dpi"
        )
    return image


def _color_mask(image: np.ndarray, color: str) -> np.ndarray:
    red = image[..., 0].astype(np.int16)
    green = image[..., 1].astype(np.int16)
    blue = image[..., 2].astype(np.int16)
    if color == "blue":
        return (blue - red > 40) & (blue - green > 30) & (blue > 90) & (red < 220)
    if color == "red":
        return (red - green > 50) & (red - blue > 50) & (red > 120) & (green < 210)
    if color == "green":
        return (green - red > 50) & (green - blue > 25) & (green > 100) & (red < 210)
    raise ValueError(f"unsupported trace color: {color}")


def _components(mask: np.ndarray) -> list[tuple[np.ndarray, int, int, int, int, int]]:
    """Return 8-connected components and their area/bounds in local pixels."""
    y_values, x_values = np.nonzero(mask)
    remaining = set(zip(y_values.tolist(), x_values.tolist(), strict=True))
    result = []
    while remaining:
        start = remaining.pop()
        stack = [start]
        ys = [start[0]]
        xs = [start[1]]
        while stack:
            y, x = stack.pop()
            for neighbor_y in range(y - 1, y + 2):
                for neighbor_x in range(x - 1, x + 2):
                    neighbor = (neighbor_y, neighbor_x)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        stack.append(neighbor)
                        ys.append(neighbor_y)
                        xs.append(neighbor_x)
        component = np.zeros(mask.shape, dtype=bool)
        component[np.asarray(ys), np.asarray(xs)] = True
        result.append((component, len(xs), min(xs), max(xs), min(ys), max(ys)))
    return result


def _runs(values: np.ndarray) -> list[tuple[int, int]]:
    if values.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(values) > 1)
    starts = np.concatenate(([0], breaks + 1))
    ends = np.concatenate((breaks, [values.size - 1]))
    return [(int(values[start]), int(values[end])) for start, end in zip(starts, ends, strict=True)]


def _choose_components(spec: CurveSpec, page_image: np.ndarray) -> list[np.ndarray]:
    # Keep the mask inside the calibrated plot rectangle. Pixels outside it can
    # otherwise turn a curve that touches an axis into an out-of-range read.
    x0 = max(0, math.floor(spec.x0_px))
    x1 = min(page_image.shape[1], math.ceil(spec.x1_px) + 1)
    y0 = max(0, math.floor(spec.y0_px))
    y1 = min(page_image.shape[0], math.ceil(spec.y1_px) + 1)
    roi = page_image[y0:y1, x0:x1]
    candidates = []
    for component, area, left, right, top, bottom in _components(_color_mask(roi, spec.color)):
        span = right - left + 1 if spec.traversal == "x" else bottom - top + 1
        near_origin_fig9_fragment = False
        if spec.figure == 9 and spec.color in {"red", "blue"} and area >= 15 and span >= 5:
            z_min = spec.independent_min + (
                (y0 + top - spec.y0_px)
                * (spec.independent_max - spec.independent_min)
                / (spec.y1_px - spec.y0_px)
            )
            z_max = spec.independent_min + (
                (y0 + bottom - spec.y0_px)
                * (spec.independent_max - spec.independent_min)
                / (spec.y1_px - spec.y0_px)
            )
            lateral_min = spec.dependent_min + (
                (x0 + left - spec.x0_px)
                * (spec.dependent_max - spec.dependent_min)
                / (spec.x1_px - spec.x0_px)
            )
            lateral_max = spec.dependent_min + (
                (x0 + right - spec.x0_px)
                * (spec.dependent_max - spec.dependent_min)
                / (spec.x1_px - spec.x0_px)
            )
            near_origin_fig9_fragment = (
                0.0 <= z_min <= z_max <= 0.35 and 0.0 <= lateral_min <= lateral_max <= 0.4
            )
        if (area >= spec.min_component_area and span >= spec.min_traversal_span_px) or (
            near_origin_fig9_fragment
        ):
            candidates.append((component, area, left, right, top, bottom))
    if not candidates:
        raise ValueError(f"no qualifying {spec.color} component for Figure {spec.figure}")
    candidates.sort(
        key=lambda item: (item[2] if spec.traversal == "x" else item[4], item[3], item[5])
    )
    return [item[0] for item in candidates]


def _line_half_width_px(component: np.ndarray, traversal: str) -> int:
    widths = []
    if traversal == "x":
        for x in range(component.shape[1]):
            values = np.flatnonzero(component[:, x])
            for lower, upper in _runs(values):
                width = upper - lower + 1
                if width <= 20:
                    widths.append(width)
    else:
        for y in range(component.shape[0]):
            values = np.flatnonzero(component[y, :])
            for lower, upper in _runs(values):
                width = upper - lower + 1
                if width <= 20:
                    widths.append(width)
    if not widths:
        return 3
    return max(2, int(math.ceil(float(np.median(widths)) / 2)))


def _trace_component(
    spec: CurveSpec,
    component: np.ndarray,
    segment_id: int,
) -> list[dict[str, object]]:
    offsets = np.argwhere(component)
    top, left = offsets.min(axis=0)
    bottom, right = offsets.max(axis=0)
    half_width_px = _line_half_width_px(component, spec.traversal)
    independent_pixel_scale = (
        (spec.independent_max - spec.independent_min) / (spec.x1_px - spec.x0_px)
        if spec.traversal == "x"
        else (spec.independent_max - spec.independent_min) / (spec.y1_px - spec.y0_px)
    )
    dependent_pixel_scale = (
        (spec.dependent_max - spec.dependent_min) / (spec.y1_px - spec.y0_px)
        if spec.traversal == "x"
        else (spec.dependent_max - spec.dependent_min) / (spec.x1_px - spec.x0_px)
    )
    rows = []
    point_index = 0
    if spec.traversal == "x":
        traversals = range(left, right + 1)
        for x in traversals:
            intervals = _runs(np.flatnonzero(component[:, x]))
            for branch_id, (lower, upper) in enumerate(intervals):
                span = upper - lower + 1
                if span > max(16, 2 * half_width_px + 2):
                    cross_centers = (lower + half_width_px, upper - half_width_px)
                else:
                    cross_centers = ((lower + upper) / 2.0,)
                for cross_center in cross_centers:
                    page_x = x + math.floor(spec.x0_px)
                    page_y = cross_center + math.floor(spec.y0_px)
                    independent = spec.independent_min + (
                        (page_x - spec.x0_px)
                        * (spec.independent_max - spec.independent_min)
                        / (spec.x1_px - spec.x0_px)
                    )
                    dependent = spec.dependent_min + (
                        (page_y - spec.y0_px)
                        * (spec.dependent_max - spec.dependent_min)
                        / (spec.y1_px - spec.y0_px)
                    )
                    rows.append(
                        _row(
                            spec,
                            segment_id,
                            branch_id,
                            point_index,
                            independent,
                            dependent,
                            2 * independent_pixel_scale,
                            (half_width_px + 2) * dependent_pixel_scale,
                        )
                    )
                    point_index += 1
    else:
        traversals = range(top, bottom + 1)
        for y in traversals:
            intervals = _runs(np.flatnonzero(component[y, :]))
            for branch_id, (lower, upper) in enumerate(intervals):
                span = upper - lower + 1
                if span > max(16, 2 * half_width_px + 2):
                    cross_centers = (lower + half_width_px, upper - half_width_px)
                else:
                    cross_centers = ((lower + upper) / 2.0,)
                for cross_center in cross_centers:
                    page_x = cross_center + math.floor(spec.x0_px)
                    page_y = y + math.floor(spec.y0_px)
                    independent = spec.independent_min + (
                        (page_y - spec.y0_px)
                        * (spec.independent_max - spec.independent_min)
                        / (spec.y1_px - spec.y0_px)
                    )
                    dependent = spec.dependent_min + (
                        (page_x - spec.x0_px)
                        * (spec.dependent_max - spec.dependent_min)
                        / (spec.x1_px - spec.x0_px)
                    )
                    independent_bound = 2 * independent_pixel_scale
                    dependent_bound = (half_width_px + 2) * dependent_pixel_scale
                    if (
                        spec.figure == 9
                        and spec.color in {"red", "blue"}
                        and independent <= 0.35
                        and dependent <= 0.4
                    ):
                        # The near-origin marks are short and disconnected;
                        # widen their raster-read bounds and do not imply
                        # continuity with the larger curve components.
                        independent_bound = max(independent_bound, 0.07)
                        dependent_bound = max(dependent_bound, 0.08)
                    rows.append(
                        _row(
                            spec,
                            segment_id,
                            branch_id,
                            point_index,
                            independent,
                            dependent,
                            independent_bound,
                            dependent_bound,
                        )
                    )
                    point_index += 1
    return rows


def _row(
    spec: CurveSpec,
    segment_id: int,
    branch_id: int,
    point_index: int,
    independent: float,
    dependent: float,
    independent_bound: float,
    dependent_bound: float,
) -> dict[str, object]:
    return {
        "figure": spec.figure,
        "pdf_page": spec.pdf_page,
        "journal_page": spec.journal_page,
        "panel": spec.panel,
        "aircraft": "Dash-8",
        "alpha_l_threshold": 0.001,
        "series_id": spec.series_id,
        "time_s": "" if spec.time_s is None else spec.time_s,
        "time_candidates_s": spec.time_candidates_s,
        "time_status": spec.time_status,
        "independent_variable": spec.independent_variable,
        "independent_value": independent,
        "independent_unit": spec.independent_unit,
        "dependent_variable": spec.dependent_variable,
        "dependent_value": dependent,
        "dependent_unit": spec.dependent_unit,
        "segment_id": segment_id,
        "branch_id": branch_id,
        "point_index": point_index,
        "read_bound_independent": independent_bound,
        "read_bound_dependent": dependent_bound,
    }


def _fig9_specs(color: str, series_id: str, time_s: float) -> CurveSpec:
    return CurveSpec(
        figure=9,
        pdf_page=9,
        journal_page=1523,
        panel="a",
        series_id=series_id,
        time_s=time_s,
        time_candidates_s=str(time_s),
        time_status="reported",
        independent_variable="z_over_Lc",
        independent_unit="1",
        independent_min=0.0,
        independent_max=8.0,
        dependent_variable="L_over_Lc",
        dependent_unit="1",
        dependent_min=0.0,
        dependent_max=9.0,
        color=color,
        traversal="y",
        x0_px=350.0,
        x1_px=1177.0,
        # Page raster at 300 dpi; dark-axis tick centers put z/Lc=0 at
        # y≈1590.5 and z/Lc=8 at y≈2241.5. The old y0=1653 was close to the
        # printed 1 tick and cropped the top of each curve.
        y0_px=1590.5,
        y1_px=2241.5,
        # Keep the general component filter strict enough to reject legend
        # strokes. _choose_components separately retains reviewed red/blue
        # components in the near-origin ROI as isolated start fragments.
        min_component_area=100,
        min_traversal_span_px=10,
    )


def digitize(pdf_path: Path = SOURCE_PDF) -> list[dict[str, object]]:
    """Return deterministic raster-centerline points and conservative bounds."""
    if _sha256(pdf_path) != EXPECTED_PDF_SHA256:
        raise ValueError(f"unexpected Calbrix source PDF revision: {pdf_path}")

    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="calbrix-curves-") as temp:
        workdir = Path(temp)
        rendered: dict[int, np.ndarray] = {}
        for page in sorted({spec.pdf_page for spec in SPECS} | {9}):
            rendered[page] = _render_page(pdf_path, page, workdir)

        for spec in SPECS:
            for segment_id, component in enumerate(
                _choose_components(spec, rendered[spec.pdf_page]), start=1
            ):
                rows.extend(_trace_component(spec, component, segment_id))

        for color, series_id, time_s in FIG9_TIMES:
            spec = _fig9_specs(color, series_id, time_s)
            for segment_id, component in enumerate(_choose_components(spec, rendered[9]), start=1):
                rows.extend(_trace_component(spec, component, segment_id))

    return rows


def write_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=SOURCE_PDF, help="exact local Calbrix PDF")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV output path")
    args = parser.parse_args()
    rows = digitize(args.pdf)
    write_csv(rows, args.output)
    print(f"wrote {len(rows)} figure-read points to {args.output}")


if __name__ == "__main__":
    main()
