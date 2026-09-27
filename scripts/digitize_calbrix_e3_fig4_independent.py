#!/usr/bin/env python3
"""Independently digitize Calbrix et al. CL-415 Fig. 4 red/green traces.

This pass renders PDF page 5 / journal page 1519 to a 300-dpi PPM, calibrates
from the visible Fig. 4 ticks, isolates red and green strokes in HSV, and thins
them with Zhang-Suen morphology. Pixel tick centers are recorded below for
reproducibility. The figure caption/legend maps red to the CL-415 top exit and
green to the bottom exit. Nearby prose conflicts, calling the top exit blue and
the bottom red; this trace follows the caption/legend and excludes blue.

Fig. 4 plots maximum exit velocity U_L(t), not a measured flow rate or the
authors' raw outlet history. Nearby prose estimates full CL-415 discharge at
about 1.5 s, while the raster retains small positive colored marks later. The
visible-end reads below retain that ambiguity: read bounds can overlap the
zero axis, no exact physical shutoff is established, and no zero is appended.
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

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PDF = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
DEFAULT_OUTPUT = ROOT / "data/derived/calbrix_cl415_fig4_velocities_independent.csv"
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"
PDF_PAGE = 5
JOURNAL_PAGE = 1519
RENDER_DPI = 300
PPM_WIDTH = 2481
PPM_HEIGHT = 3249

# Figure 4 tick centers independently read from the page-5 300-dpi render.
# Values are full-page-image pixels, with image origin at the upper left. The x
# ticks are t=0..5 s; descending y ticks are U_L=0..6 m/s. Each axis is fit by
# least squares to all six/seven tick centers rather than only its endpoints.
TIME_TICK_PX = (282.5, 456.5, 630.5, 804.5, 978.5, 1152.5)
SPEED_TICK_PX = (1830.0, 1715.5, 1600.5, 1486.5, 1372.5, 1258.0, 1143.0)
TIME_TICK_VALUES_S = tuple(float(i) for i in range(6))
SPEED_TICK_VALUES_M_S = tuple(float(i) for i in range(7))

# Process the plotted axes through 2.3 s. This excludes the in-plot legend at
# approximately 2.6–3.1 s; the red and green traces have visible low tails to
# roughly 2 s. The blue Dash-8 trace is excluded by hue selection.
TIME_MASK_MAX_S = 2.3
REGULAR_SAMPLE_STEP_S = 0.1
HUE_RED_DEGREES = 25.0
HUE_GREEN_MIN_DEGREES = 60.0
HUE_GREEN_MAX_DEGREES = 165.0
MIN_SATURATION = 0.30
MIN_VALUE = 0.35

FIELDNAMES = (
    "source_pdf_sha256",
    "pdf_page",
    "journal_page",
    "figure",
    "series_id",
    "exit_label",
    "figure_color",
    "time_s",
    "u_l_m_s",
    "sample_kind",
    "source_pixel_x",
    "source_pixel_y",
    "figure_read_bound_time_s",
    "figure_read_bound_u_l_m_s",
)

SERIES = (
    ("cl415_top_exit_red", "top_exit", "red"),
    ("cl415_bottom_exit_green", "bottom_exit", "green"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_ppm(path: Path) -> np.ndarray:
    """Read the P6 image emitted by Poppler using only the standard library."""
    data = path.read_bytes()
    offset = 0

    def token() -> bytes:
        nonlocal offset
        while offset < len(data):
            if data[offset] in b" \t\r\n\v\f":
                offset += 1
            elif data[offset] == ord("#"):
                newline = data.find(b"\n", offset)
                if newline < 0:
                    raise ValueError("unterminated PPM comment")
                offset = newline + 1
            else:
                break
        start = offset
        while offset < len(data) and data[offset] not in b" \t\r\n\v\f#":
            offset += 1
        if start == offset:
            raise ValueError("incomplete PPM header")
        return data[start:offset]

    magic = token()
    width = int(token())
    height = int(token())
    maximum = int(token())
    if magic != b"P6" or maximum != 255:
        raise ValueError(f"expected an 8-bit P6 PPM, got {magic!r}/{maximum}")
    if data[offset : offset + 2] == b"\r\n":
        offset += 2
    elif offset < len(data) and data[offset] in b" \t\r\n\v\f":
        offset += 1
    pixels = np.frombuffer(data, dtype=np.uint8, offset=offset)
    if pixels.size != width * height * 3:
        raise ValueError("PPM pixel count does not match the header")
    return pixels.reshape(height, width, 3)


def _render_source_page(pdf_path: Path, directory: Path) -> np.ndarray:
    prefix = directory / "calbrix_page5"
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(PDF_PAGE),
            "-l",
            str(PDF_PAGE),
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
            f"page 5 rendered as {image.shape[1]}x{image.shape[0]}, "
            f"expected {PPM_WIDTH}x{PPM_HEIGHT} at {RENDER_DPI} dpi"
        )
    return image


def _fit_axis(
    tick_pixels: tuple[float, ...], tick_values: tuple[float, ...]
) -> tuple[float, float]:
    """Return slope/intercept for value = slope*pixel + intercept."""
    if len(tick_pixels) != len(tick_values):
        raise ValueError("pixel and value tick counts differ")
    slope, intercept = np.polyfit(
        np.asarray(tick_pixels, dtype=np.float64),
        np.asarray(tick_values, dtype=np.float64),
        1,
    )
    return float(slope), float(intercept)


TIME_SLOPE, TIME_INTERCEPT = _fit_axis(TIME_TICK_PX, TIME_TICK_VALUES_S)
SPEED_SLOPE, SPEED_INTERCEPT = _fit_axis(SPEED_TICK_PX, SPEED_TICK_VALUES_M_S)
AXIS_X_MIN_PX = int(round(min(TIME_TICK_PX)))
AXIS_Y_MIN_PX = int(round(min(SPEED_TICK_PX)))
AXIS_Y_MAX_PX = int(round(max(SPEED_TICK_PX)))
TIME_MASK_X_MAX_PX = int(round((TIME_MASK_MAX_S - TIME_INTERCEPT) / TIME_SLOPE))


def _hsv_mask(page: np.ndarray, series_color: str) -> np.ndarray:
    """Build hue-based trace mask, distinct from the first RGB-dominance pass."""
    rgb = page.astype(np.float32) / 255.0
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    maximum = np.maximum(np.maximum(red, green), blue)
    minimum = np.minimum(np.minimum(red, green), blue)
    chroma = maximum - minimum
    hue = np.zeros(maximum.shape, dtype=np.float32)
    nonzero = chroma > 1e-7
    is_red_max = nonzero & (maximum == red)
    is_green_max = nonzero & (maximum == green)
    is_blue_max = nonzero & (maximum == blue)
    hue[is_red_max] = 60.0 * ((green[is_red_max] - blue[is_red_max]) / chroma[is_red_max])
    hue[is_red_max & (hue < 0.0)] += 360.0
    hue[is_green_max] = (
        60.0 * ((blue[is_green_max] - red[is_green_max]) / chroma[is_green_max]) + 120.0
    )
    hue[is_blue_max] = (
        60.0 * ((red[is_blue_max] - green[is_blue_max]) / chroma[is_blue_max]) + 240.0
    )
    saturation = np.divide(
        chroma,
        maximum,
        out=np.zeros_like(chroma),
        where=maximum > 1e-7,
    )
    vivid = (saturation >= MIN_SATURATION) & (maximum >= MIN_VALUE)
    if series_color == "red":
        color = (hue <= HUE_RED_DEGREES) | (hue >= 360.0 - HUE_RED_DEGREES)
    elif series_color == "green":
        color = (hue >= HUE_GREEN_MIN_DEGREES) & (hue <= HUE_GREEN_MAX_DEGREES)
    else:
        raise ValueError(f"unsupported trace color: {series_color}")

    return vivid & color


def _thin_zhang_suen(mask: np.ndarray) -> np.ndarray:
    """Reduce each colored stroke to its medial 1-pixel skeleton."""
    skeleton = mask.astype(np.uint8).copy()
    while True:
        changed = False
        for phase in (0, 1):
            padded = np.pad(skeleton, 1)
            p2 = padded[:-2, 1:-1]
            p3 = padded[:-2, 2:]
            p4 = padded[1:-1, 2:]
            p5 = padded[2:, 2:]
            p6 = padded[2:, 1:-1]
            p7 = padded[2:, :-2]
            p8 = padded[1:-1, :-2]
            p9 = padded[:-2, :-2]
            neighbors = (p2, p3, p4, p5, p6, p7, p8, p9)
            neighbor_count = sum(neighbors)
            transitions = np.zeros_like(skeleton)
            for index in range(8):
                transitions += (neighbors[index] == 0) & (neighbors[(index + 1) % 8] == 1)
            remove = (
                (skeleton == 1) & (neighbor_count >= 2) & (neighbor_count <= 6) & (transitions == 1)
            )
            if phase == 0:
                remove &= ~((p2 & p4 & p6).astype(bool)) & ~((p4 & p6 & p8).astype(bool))
            else:
                remove &= ~((p2 & p4 & p8).astype(bool)) & ~((p2 & p6 & p8).astype(bool))
            if np.any(remove):
                skeleton[remove] = 0
                changed = True
        if not changed:
            return skeleton.astype(bool)


def _column_center(skeleton: np.ndarray, x: int) -> tuple[float, float] | None:
    """Read a thinned trace at one x, using a 3-column local window if needed."""
    width = skeleton.shape[1]
    for radius in (0, 1):
        x0 = max(0, x - radius)
        x1 = min(width, x + radius + 1)
        ys, xs = np.nonzero(skeleton[:, x0:x1])
        if ys.size:
            # Use the nearest column(s); median y suppresses small skeleton
            # spurs while retaining the visible path center.
            x_global = xs + x0
            closest = np.min(np.abs(x_global - x))
            local_y = ys[np.abs(x_global - x) == closest]
            center_x = float(np.median(x_global[np.abs(x_global - x) == closest]))
            return center_x, float(np.median(local_y))
    return None


def _stroke_halfwidth(mask: np.ndarray, x: int, y: float) -> tuple[float, float]:
    """Return horizontal/vertical half-widths for the HSV blob near a skeleton read."""
    x_int = min(max(int(round(x)), 0), mask.shape[1] - 1)
    y_int = min(max(int(round(y)), 0), mask.shape[0] - 1)
    vertical_pixels = np.flatnonzero(mask[:, x_int])
    if vertical_pixels.size:
        vertical_center = int(vertical_pixels[np.argmin(np.abs(vertical_pixels - y_int))])
        lo = hi = vertical_center
        while lo > 0 and mask[lo - 1, x_int]:
            lo -= 1
        while hi + 1 < mask.shape[0] and mask[hi + 1, x_int]:
            hi += 1
        vertical_half = (hi - lo + 1) / 2.0
    else:
        vertical_half = 3.0

    horizontal_pixels = np.flatnonzero(mask[y_int, :])
    if horizontal_pixels.size:
        horizontal_center = int(horizontal_pixels[np.argmin(np.abs(horizontal_pixels - x_int))])
        lo = hi = horizontal_center
        while lo > 0 and mask[y_int, lo - 1]:
            lo -= 1
        while hi + 1 < mask.shape[1] and mask[y_int, hi + 1]:
            hi += 1
        horizontal_half = (hi - lo + 1) / 2.0
    else:
        horizontal_half = 3.0
    return horizontal_half, vertical_half


def _sample_row(
    series_id: str,
    exit_label: str,
    color: str,
    time_value: float,
    source_x: float,
    source_y: float,
    time_slope: float,
    speed_slope: float,
    speed_intercept: float,
    mask: np.ndarray,
    sample_kind: str,
) -> dict[str, object]:
    # The source x/y are in page-render coordinates. Mask coordinates are
    # relative to the independently calibrated plot/time window.
    x_local = int(round(source_x - AXIS_X_MIN_PX))
    y_local = int(round(source_y - AXIS_Y_MIN_PX))
    horizontal_half, vertical_half = _stroke_halfwidth(mask, x_local, y_local)
    time_bound = (horizontal_half + 2.0) * abs(time_slope)
    speed_bound = (vertical_half + 2.0) * abs(speed_slope)
    value = speed_slope * source_y + speed_intercept
    return {
        "source_pdf_sha256": EXPECTED_PDF_SHA256,
        "pdf_page": PDF_PAGE,
        "journal_page": JOURNAL_PAGE,
        "figure": 4,
        "series_id": series_id,
        "exit_label": exit_label,
        "figure_color": color,
        # A microsecond decimal is far finer than the raster calibration and
        # avoids binary-artifact timestamps such as 0.30000000000000004.
        "time_s": round(time_value, 6),
        "u_l_m_s": value,
        "sample_kind": sample_kind,
        "source_pixel_x": source_x,
        "source_pixel_y": source_y,
        "figure_read_bound_time_s": time_bound,
        "figure_read_bound_u_l_m_s": speed_bound,
    }


def _curve_rows(
    page: np.ndarray,
    series_id: str,
    exit_label: str,
    color: str,
    time_slope: float,
    time_intercept: float,
    speed_slope: float,
    speed_intercept: float,
) -> list[dict[str, object]]:
    crop = page[AXIS_Y_MIN_PX : AXIS_Y_MAX_PX + 1, AXIS_X_MIN_PX : TIME_MASK_X_MAX_PX + 1]
    mask = _hsv_mask(crop, color)
    skeleton = _thin_zhang_suen(mask)
    relative_y, relative_x = np.nonzero(skeleton)
    if relative_x.size < 100:
        raise ValueError(f"not enough skeleton pixels for {series_id}")

    # Return to full-page pixel coordinates for this trace's visible endpoints.
    xs = relative_x.astype(np.float64) + AXIS_X_MIN_PX
    ys = relative_y.astype(np.float64) + AXIS_Y_MIN_PX
    left = float(xs.min())
    right = float(xs.max())

    samples: list[tuple[float, float, float, str]] = []
    for endpoint_x, label in ((left, "visible_start"), (right, "visible_end")):
        y_values = ys[xs == endpoint_x]
        center_y = float(np.median(y_values))
        samples.append((time_slope * endpoint_x + time_intercept, endpoint_x, center_y, label))

    start_time = time_slope * left + time_intercept
    end_time = time_slope * right + time_intercept
    first_grid = math.ceil((start_time + 1e-9) / REGULAR_SAMPLE_STEP_S) * REGULAR_SAMPLE_STEP_S
    last_grid = math.floor((end_time - 1e-9) / REGULAR_SAMPLE_STEP_S) * REGULAR_SAMPLE_STEP_S
    if abs(first_grid - start_time) < 0.025:
        first_grid += REGULAR_SAMPLE_STEP_S
    if abs(last_grid - end_time) < 0.025:
        last_grid -= REGULAR_SAMPLE_STEP_S
    grid_count = max(0, int(round((last_grid - first_grid) / REGULAR_SAMPLE_STEP_S)) + 1)

    for index in range(grid_count):
        sample_time = first_grid + index * REGULAR_SAMPLE_STEP_S
        page_x = int(round((sample_time - time_intercept) / time_slope))
        center = _column_center(skeleton, page_x - AXIS_X_MIN_PX)
        if center is None:
            continue
        local_x, local_y = center
        actual_x = AXIS_X_MIN_PX + local_x
        actual_y = AXIS_Y_MIN_PX + local_y
        if actual_x < left - 1 or actual_x > right + 1:
            continue
        samples.append((sample_time, actual_x, actual_y, "uniform_0p1s"))

    rows = [
        _sample_row(
            series_id,
            exit_label,
            color,
            sample_time,
            source_x,
            source_y,
            time_slope,
            speed_slope,
            speed_intercept,
            mask,
            sample_kind,
        )
        for sample_time, source_x, source_y, sample_kind in samples
    ]
    rows.sort(key=lambda row: float(row["time_s"]))
    return rows


def digitize(pdf_path: Path = SOURCE_PDF) -> list[dict[str, object]]:
    if _sha256(pdf_path) != EXPECTED_PDF_SHA256:
        raise ValueError(f"unexpected source PDF revision: {pdf_path}")
    with tempfile.TemporaryDirectory(prefix="calbrix-e3-fig4-independent-") as temporary:
        page = _render_source_page(pdf_path, Path(temporary))
    rows: list[dict[str, object]] = []
    for series_id, exit_label, color in SERIES:
        rows.extend(
            _curve_rows(
                page,
                series_id,
                exit_label,
                color,
                TIME_SLOPE,
                TIME_INTERCEPT,
                SPEED_SLOPE,
                SPEED_INTERCEPT,
            )
        )
    return rows


def write_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=SOURCE_PDF, help="exact local source PDF")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV output path")
    args = parser.parse_args()
    rows = digitize(args.pdf)
    write_csv(rows, args.output)
    print(f"wrote {len(rows)} independent figure-read points to {args.output}")


if __name__ == "__main__":
    main()
