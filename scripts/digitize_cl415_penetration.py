#!/usr/bin/env python3
"""Digitize the CL-415 liquid penetration curve from Calbrix et al. Fig. 6(b).

The source is the supplied Calbrix PDF, PDF p. 7 / journal p. 1521. This reads
the red CL-415 alpha_L=0.001 curve at the reported t=0.5 s from the page raster;
it does not recover the authors' raw simulation output or fit the curve.

The 500-dpi Fig. 6(b) crop starts at full-page pixel (2050, 300). In crop
coordinates the x-axis tick centers are x=215.5 px at y=0 m and x=1631.0 px at
y=2 m; the vertical axis tick centers are y=271.5 px at Z=0 m and y=1390.0 px
at Z=3 m. Pixel y increases downward, matching the plotted positive Z. Values
are mapped linearly between these tick centers. The red line is selected by
RGB distance from (250, 10, 27), restricted to the plotted axes, then the
largest connected stroke component is read at 4-pixel x intervals using the
median stroke pixel in each column. Red text labels are separate components.

The stored +/-0.02 m streamwise and +/-0.03 m penetration bounds are heuristic
raster-read allowances, not uncertainty bars reported by the paper. They do
not include source-model, geometry, or calibration uncertainty.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from scripts.digitize_calbrix_dash8_cloud_curves_independent import (
    PANELS as DASH8_PANELS,
)
from scripts.digitize_calbrix_dash8_cloud_curves_independent import (
    _component_mask,
    _components,
    _read_ppm,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PDF = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
DEFAULT_OUTPUT = ROOT / "data/derived/calbrix_cl415_fig6_penetration.csv"
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"

# Reuse the independently measured Fig. 6(b) crop and tick centers. Coordinates
# are local to this 500-dpi crop; page pixel positions add crop_x_px/crop_y_px.
PANEL = DASH8_PANELS["fig6"]
CROP_X_PX = PANEL.crop_x
CROP_Y_PX = PANEL.crop_y
RENDER_DPI = 500
SCAN_STEP_PX = 4
RED_RGB = (250, 10, 27)
RGB_DISTANCE_LIMIT = 90.0
MIN_COMPONENT_PIXELS = 1_000
MIN_COMPONENT_X_SPAN_PX = 500
READ_BOUND_STREAMWISE_M = 0.02
READ_BOUND_PENETRATION_M = 0.03

FIELDNAMES = (
    "source_pdf_sha256",
    "source_pdf_filename",
    "pdf_page",
    "journal_page",
    "figure",
    "panel",
    "aircraft",
    "alpha_l_threshold",
    "series_id",
    "time_s",
    "time_status",
    "legend_color",
    "stroke_rgb_center",
    "stroke_rgb_distance_limit",
    "render_dpi",
    "sample_step_px",
    "crop_x_px",
    "crop_y_px",
    "crop_width_px",
    "crop_height_px",
    "axis_x_variable",
    "axis_x_unit",
    "axis_x_zero_px",
    "axis_x_zero_value",
    "axis_x_max_px",
    "axis_x_max_value",
    "axis_y_variable",
    "axis_y_unit",
    "axis_y_zero_px",
    "axis_y_zero_value",
    "axis_y_max_px",
    "axis_y_max_value",
    "axis_y_pixels_increase_downward",
    "plot_x_px",
    "plot_y_px",
    "point_index",
    "page_x_px",
    "page_y_px",
    "x_value",
    "y_value",
    "read_bound_streamwise_y_m",
    "read_bound_vertical_Z_m",
    "read_method",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _render_page_crop(source_pdf: Path) -> np.ndarray:
    """Render only the Fig. 6(b) crop, avoiding a full-page raster."""
    with tempfile.TemporaryDirectory(prefix="calbrix-cl415-fig6-") as temporary:
        prefix = Path(temporary) / "fig6b"
        subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(PANEL.page),
                "-l",
                str(PANEL.page),
                "-r",
                str(RENDER_DPI),
                "-x",
                str(CROP_X_PX),
                "-y",
                str(CROP_Y_PX),
                "-W",
                str(PANEL.crop_width),
                "-H",
                str(PANEL.crop_height),
                "-singlefile",
                str(source_pdf),
                str(prefix),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        image = _read_ppm(prefix.with_suffix(".ppm"))
    expected_shape = (PANEL.crop_height, PANEL.crop_width, 3)
    if image.shape != expected_shape:
        raise ValueError(f"Unexpected Fig. 6(b) raster crop: {image.shape}")
    return image


def _plot_frame(mask: np.ndarray) -> np.ndarray:
    bounded = np.zeros_like(mask, dtype=bool)
    x0 = math.floor(PANEL.x_zero_px)
    x1 = math.ceil(PANEL.x_max_px)
    z0 = math.floor(PANEL.y_zero_px)
    z1 = math.ceil(PANEL.y_max_px)
    bounded[z0 : z1 + 1, x0 : x1 + 1] = mask[z0 : z1 + 1, x0 : x1 + 1]
    return bounded


def _red_stroke_mask(image: np.ndarray) -> np.ndarray:
    prototype = np.asarray(RED_RGB, dtype=np.float32)
    distance = np.linalg.norm(image.astype(np.float32) - prototype, axis=2)
    return _plot_frame(distance <= RGB_DISTANCE_LIMIT)


def _select_curve_component(mask: np.ndarray) -> np.ndarray:
    eligible = []
    for component in _components(mask):
        area = sum(end - start + 1 for _, start, end in component)
        x_span = max(end for _, _, end in component) - min(start for _, start, _ in component)
        if area >= MIN_COMPONENT_PIXELS and x_span >= MIN_COMPONENT_X_SPAN_PX:
            eligible.append((area, component))
    if len(eligible) != 1:
        raise ValueError(
            f"Expected one long red CL-415 curve component in Fig. 6(b), found {len(eligible)}"
        )
    return _component_mask(mask.shape, eligible[0][1])


def _extract_trace(
    image: np.ndarray, source_hash: str, source_filename: str
) -> list[dict[str, str | int]]:
    line_mask = _select_curve_component(_red_stroke_mask(image))
    x0 = math.ceil(PANEL.x_zero_px)
    x1 = math.floor(PANEL.x_max_px)
    z0 = math.floor(PANEL.y_zero_px)
    z1 = math.ceil(PANEL.y_max_px)
    visible_columns = np.flatnonzero(line_mask[z0 : z1 + 1, :].any(axis=0))
    trace_start_x = int(visible_columns[0])
    trace_end_x = int(visible_columns[-1])
    plot_columns = sorted(set(range(x0, x1 + 1, SCAN_STEP_PX)) | {trace_start_x, trace_end_x})
    rows: list[dict[str, str | int]] = []

    for plot_x in plot_columns:
        stroke_z = np.flatnonzero(line_mask[z0 : z1 + 1, plot_x]) + z0
        if stroke_z.size == 0:
            continue
        plot_z = float(np.median(stroke_z))
        streamwise_y_m = (
            (plot_x - PANEL.x_zero_px) * PANEL.x_max_value / (PANEL.x_max_px - PANEL.x_zero_px)
        )
        penetration_z_m = (
            (plot_z - PANEL.y_zero_px) * PANEL.y_max_value / (PANEL.y_max_px - PANEL.y_zero_px)
        )
        point_index = len(rows)
        rows.append(
            {
                "source_pdf_sha256": source_hash,
                "source_pdf_filename": source_filename,
                "pdf_page": PANEL.page,
                "journal_page": 1521,
                "figure": "Fig. 6(b)",
                "panel": "b",
                "aircraft": "CL-415",
                "alpha_l_threshold": "0.001",
                "series_id": "cl415_alpha0p001_t0.5s",
                "time_s": "0.5",
                "time_status": "reported",
                "legend_color": "red",
                "stroke_rgb_center": ",".join(str(v) for v in RED_RGB),
                "stroke_rgb_distance_limit": f"{RGB_DISTANCE_LIMIT:.1f}",
                "render_dpi": RENDER_DPI,
                "sample_step_px": SCAN_STEP_PX,
                "crop_x_px": CROP_X_PX,
                "crop_y_px": CROP_Y_PX,
                "crop_width_px": PANEL.crop_width,
                "crop_height_px": PANEL.crop_height,
                "axis_x_variable": "streamwise_distance_y",
                "axis_x_unit": "m",
                "axis_x_zero_px": f"{PANEL.x_zero_px:.1f}",
                "axis_x_zero_value": "0.0",
                "axis_x_max_px": f"{PANEL.x_max_px:.1f}",
                "axis_x_max_value": f"{PANEL.x_max_value:.1f}",
                "axis_y_variable": "vertical_penetration_Z",
                "axis_y_unit": "m",
                "axis_y_zero_px": f"{PANEL.y_zero_px:.1f}",
                "axis_y_zero_value": "0.0",
                "axis_y_max_px": f"{PANEL.y_max_px:.1f}",
                "axis_y_max_value": f"{PANEL.y_max_value:.1f}",
                "axis_y_pixels_increase_downward": "true",
                "plot_x_px": f"{plot_x:.2f}",
                "plot_y_px": f"{plot_z:.2f}",
                "point_index": point_index,
                "page_x_px": f"{CROP_X_PX + plot_x:.2f}",
                "page_y_px": f"{CROP_Y_PX + plot_z:.2f}",
                "x_value": f"{streamwise_y_m:.5f}",
                "y_value": f"{penetration_z_m:.5f}",
                "read_bound_streamwise_y_m": f"{READ_BOUND_STREAMWISE_M:.3f}",
                "read_bound_vertical_Z_m": f"{READ_BOUND_PENETRATION_M:.3f}",
                "read_method": (
                    "500dpi page-7 raster; red connected stroke; median pixel "
                    "center per 4px plot-x column plus visible endpoints; "
                    "no curve fitting or bridging"
                ),
            }
        )
    return rows


def _write_preview(image: np.ndarray, rows: list[dict[str, str | int]], path: Path) -> None:
    """Write a source crop preview with extracted samples highlighted."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - optional preview feature
        raise RuntimeError("Pillow is required only when --preview is requested") from exc

    preview = Image.fromarray(image.copy())
    draw = ImageDraw.Draw(preview)
    for row in rows:
        x = round(float(row["plot_x_px"]))
        z = round(float(row["plot_y_px"]))
        draw.ellipse((x - 3, z - 3, x + 3, z + 3), fill=(0, 230, 80))
    path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(path)


def digitize(
    source_pdf: Path,
    output_csv: Path,
    preview_path: Path | None = None,
) -> tuple[int, str]:
    source_hash = _sha256(source_pdf)
    if source_hash != EXPECTED_PDF_SHA256:
        raise ValueError(f"Unexpected Calbrix PDF SHA-256 {source_hash}")
    image = _render_page_crop(source_pdf)
    rows = _extract_trace(image, source_hash, source_pdf.name)
    if len(rows) < 100:
        raise ValueError(f"Fig. 6(b) CL-415 trace is unexpectedly short: {len(rows)}")

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if preview_path is not None:
        _write_preview(image, rows, preview_path)
    return len(rows), source_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_PDF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    count, source_hash = digitize(args.source, args.output, args.preview)
    print(f"Wrote {args.output}: rows={count}; source_sha256={source_hash}")
    if args.preview is not None:
        print(f"Wrote preview: {args.preview}")


if __name__ == "__main__":
    main()
