#!/usr/bin/env python3
"""Independent raster read of Calbrix et al. Fig. 11(a), CL-415 only.

This extracts colored polyline centers from a fresh full-page render. It does
not read or use the pixel coordinates in the first digitization. The result is
a descriptive read of the printed figure, not the authors' MATLAB output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import math
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PDF = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
DEFAULT_OUTPUT = ROOT / "data/derived/calbrix_cl415_fig11_structure_counts_independent.csv"
FIRST_TRACE = ROOT / "data/derived/calbrix_cl415_fig11_structure_counts.csv"
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"

PAGE_NUMBER = 10
RENDER_DPI = 300
SAMPLE_STEP_S = 0.1
READ_BOUND_COUNT = 5
READ_BOUND_TIME_S = 0.025
LOCAL_HALF_WIDTH_PX = 3

SERIES = {
    "cloud_alpha_0p001_to_1": "red",
    "core_alpha_0p9_to_1": "blue",
}

# These bounds were located on a fresh full-page 300-dpi render. The legend is
# inside the plot axes, so mask it explicitly before following either trace.
PLOT_Y_TOP_PX = 1200
PLOT_Y_BOTTOM_MARGIN_PX = 4
LEGEND_BOX_PAGE_PX = (635, 1615, 915, 1770)

CSV_FIELDS = [
    "series",
    "time_s",
    "count_digitized",
    "read_bound_count",
    "read_bound_time_s",
    "page_x_px",
    "page_y_px",
    "source_pdf_sha256",
    "render_dpi",
    "read_method",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def render_page(source_pdf: Path, directory: Path) -> tuple[np.ndarray, float, float, str]:
    """Render p.10 once and return RGB pixels plus pixel/point scale factors."""
    image_path = directory / "page10.ppm"
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(PAGE_NUMBER),
            "-l",
            str(PAGE_NUMBER),
            "-r",
            str(RENDER_DPI),
            "-singlefile",
            str(source_pdf),
            str(directory / "page10"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    image = _read_ppm(image_path)

    bbox_path = directory / "page10.html"
    subprocess.run(
        [
            "pdftotext",
            "-f",
            str(PAGE_NUMBER),
            "-l",
            str(PAGE_NUMBER),
            "-bbox-layout",
            str(source_pdf),
            str(bbox_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    html = bbox_path.read_text(encoding="utf-8")
    page_match = re.search(r'<page width="([0-9.]+)" height="([0-9.]+)">', html)
    if page_match is None:
        raise ValueError("Could not read the rendered page size from pdftotext bbox output")
    width_pt, height_pt = map(float, page_match.groups())
    sx = image.shape[1] / width_pt
    sy = image.shape[0] / height_pt
    return image, sx, sy, html


def _read_ppm(path: Path) -> np.ndarray:
    """Read an 8-bit P6 PPM render using only the locked NumPy dependency."""
    data = path.read_bytes()
    cursor = 0
    tokens: list[bytes] = []
    whitespace = b" \t\r\n\v\f"
    while len(tokens) < 4:
        while cursor < len(data) and data[cursor] in whitespace:
            cursor += 1
        if cursor < len(data) and data[cursor] == ord("#"):
            newline = data.find(b"\n", cursor)
            if newline < 0:
                raise ValueError("Unterminated PPM comment")
            cursor = newline + 1
            continue
        start = cursor
        while cursor < len(data) and data[cursor] not in whitespace + b"#":
            cursor += 1
        if start == cursor:
            raise ValueError("Incomplete PPM header")
        tokens.append(data[start:cursor])

    if tokens[0] != b"P6":
        raise ValueError(f"Expected a binary P6 PPM, found {tokens[0]!r}")
    width, height, maximum = map(int, tokens[1:])
    if maximum != 255:
        raise ValueError(f"Expected 8-bit PPM pixels, found max value {maximum}")
    if data[cursor : cursor + 2] == b"\r\n":
        cursor += 2
    else:
        cursor += 1
    pixels = np.frombuffer(data, dtype=np.uint8, offset=cursor)
    if pixels.size != width * height * 3:
        raise ValueError("Unexpected PPM payload length")
    return pixels.reshape(height, width, 3)


def _bbox_words(html: str) -> list[tuple[str, float, float, float, float]]:
    pattern = re.compile(
        r'<word xMin="([0-9.]+)" yMin="([0-9.]+)" '
        r'xMax="([0-9.]+)" yMax="([0-9.]+)">([^<]+)</word>'
    )
    words = []
    for x0, y0, x1, y1, raw_text in pattern.findall(html):
        words.append((raw_text.strip(), *(float(v) for v in (x0, y0, x1, y1))))
    return words


def axis_ticks_from_vector_labels(
    image: np.ndarray, html: str, sx: float, sy: float
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Find labeled ticks from text boxes, then refine y ticks on raster marks."""
    words = _bbox_words(html)
    x_values = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    x_text = ["0", "0.5", "1", "1.5", "2", "2.5", "3"]
    x_centers = []
    for value, label in zip(x_values, x_text, strict=True):
        matches = [
            (x0 + x1) / 2
            for text, x0, y0, x1, y1 in words
            if text == label and 455.0 <= y0 <= 468.0 and 90.0 <= x0 <= 300.0
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one x-axis text box for {label!r}, found {len(matches)}")
        x_centers.append(matches[0] * sx)

    y_values = [0, 50, 100, 150, 200, 250, 300, 350, 400]
    y_label_centers = []
    for value in y_values:
        label = str(value)
        matches = [
            (y0 + y1) / 2
            for text, x0, y0, x1, y1 in words
            if text == label and 75.0 <= x0 <= 95.0 and 300.0 <= y0 <= 458.0
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one y-axis text box for {label!r}, found {len(matches)}")
        y_label_centers.append(matches[0] * sy)

    # Text glyph boxes sit a few raster pixels below the horizontal tick
    # centers. Refine each count anchor against the short gray tick mark, just
    # to the right of the vertical y-axis. This region contains no trace line.
    gray = image.astype(np.float32).mean(axis=2)
    axis_x = int(round(x_centers[0]))
    x_tick_band = gray[:, axis_x + 2 : axis_x + 14]
    y_centers = []
    for predicted_y in y_label_centers:
        row0 = max(0, round(predicted_y) - 6)
        row1 = min(image.shape[0], round(predicted_y) + 7)
        row_scores = np.maximum(0.0, 255.0 - x_tick_band[row0:row1]).sum(axis=1)
        peak = int(np.argmax(row_scores))
        neighborhood = np.arange(max(0, peak - 2), min(len(row_scores), peak + 3))
        weight_sum = float(row_scores[neighborhood].sum())
        if weight_sum <= 0:
            raise ValueError(f"Could not find raster y tick near page y={predicted_y:.2f}")
        y_centers.append(row0 + float(np.dot(neighborhood, row_scores[neighborhood]) / weight_sum))

    x_fit = np.polyfit(np.asarray(x_values), np.asarray(x_centers), 1)
    y_fit = np.polyfit(np.asarray(y_values), np.asarray(y_centers), 1)
    x_residual = float(np.max(np.abs(np.polyval(x_fit, np.asarray(x_values)) - x_centers)))
    y_residual = float(np.max(np.abs(np.polyval(y_fit, np.asarray(y_values)) - y_centers)))
    return x_fit, y_fit, x_residual, y_residual


def _color_mask(rgb: np.ndarray, color: str) -> np.ndarray:
    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    if color == "red":
        return (r >= 145) & (r - g >= 55) & (r - b >= 45) & (r >= 1.25 * g)
    if color == "blue":
        return (b >= 105) & (b - r >= 45) & (b - g >= 35) & (b >= 1.25 * r)
    raise ValueError(f"Unknown line color: {color}")


def _local_theil_sen_center(
    mask: np.ndarray, x_target: float, y_floor: int, y_ceiling: int
) -> float:
    """Fit a robust local centerline to per-column medians around one sample."""
    x0 = max(0, math.floor(x_target) - LOCAL_HALF_WIDTH_PX)
    x1 = min(mask.shape[1], math.ceil(x_target) + LOCAL_HALF_WIDTH_PX + 1)
    columns: list[tuple[float, float]] = []
    for x in range(x0, x1):
        y_pixels = np.flatnonzero(mask[y_floor:y_ceiling, x]) + y_floor
        if y_pixels.size:
            columns.append((float(x), float(np.median(y_pixels))))
    if len(columns) < 3:
        raise ValueError(f"Insufficient colored pixels at page x={x_target:.2f}")

    slopes = [
        (y_b - y_a) / (x_b - x_a)
        for (x_a, y_a), (x_b, y_b) in itertools.combinations(columns, 2)
        if x_b != x_a
    ]
    slope = float(np.median(slopes))
    intercept = float(np.median([y - slope * x for x, y in columns]))
    return slope * x_target + intercept


def extract(source_pdf: Path) -> tuple[list[dict[str, str]], dict[str, float | int]]:
    source_hash = sha256(source_pdf)
    if source_hash != EXPECTED_PDF_SHA256:
        raise ValueError(f"Unexpected source PDF SHA-256: {source_hash}")

    with tempfile.TemporaryDirectory(prefix="calbrix-e3-independent-") as temporary:
        image, sx, sy, html = render_page(source_pdf, Path(temporary))
        x_fit, y_fit, x_residual, y_residual = axis_ticks_from_vector_labels(image, html, sx, sy)
        red_mask = _color_mask(image, "red")
        blue_mask = _color_mask(image, "blue")
        legend_x0, legend_y0, legend_x1, legend_y1 = LEGEND_BOX_PAGE_PX
        for mask in (red_mask, blue_mask):
            mask[legend_y0:legend_y1, legend_x0:legend_x1] = False

        x0_px, x_per_s = float(x_fit[1]), float(x_fit[0])
        y_per_count, y0_px = float(y_fit[0]), float(y_fit[1])
        if x_per_s <= 0 or y_per_count >= 0:
            raise ValueError("Axis calibration had unexpected direction")
        y_floor = max(PLOT_Y_TOP_PX, round(y0_px + y_per_count * 450 - 8))
        y_ceiling = min(image.shape[0], round(y0_px) - PLOT_Y_BOTTOM_MARGIN_PX)

        rows: list[dict[str, str]] = []
        for series, color in SERIES.items():
            mask = red_mask if color == "red" else blue_mask
            for index in range(1, round(3.0 / SAMPLE_STEP_S) + 1):
                time_s = round(index * SAMPLE_STEP_S, 10)
                x_page_px = x0_px + x_per_s * time_s
                y_page_px = _local_theil_sen_center(mask, x_page_px, y_floor, y_ceiling)
                count_float = (y0_px - y_page_px) / -y_per_count
                count = int(math.floor(count_float + 0.5))
                rows.append(
                    {
                        "series": series,
                        "time_s": f"{time_s:.1f}",
                        "count_digitized": str(count),
                        "read_bound_count": str(READ_BOUND_COUNT),
                        "read_bound_time_s": f"{READ_BOUND_TIME_S:.3f}",
                        "page_x_px": f"{x_page_px:.3f}",
                        "page_y_px": f"{y_page_px:.3f}",
                        "source_pdf_sha256": source_hash,
                        "render_dpi": str(RENDER_DPI),
                        "read_method": "local_theil_sen_center",
                    }
                )

        diagnostics = {
            "page_width_px": image.shape[1],
            "page_height_px": image.shape[0],
            "x_px_per_s": x_per_s,
            "y_px_per_count": y_per_count,
            "x_tick_residual_px": x_residual,
            "y_tick_residual_px": y_residual,
        }
        return rows, diagnostics


def write_csv(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compare_to_first(rows: list[dict[str, str]], path: Path) -> dict[str, dict[str, float | int]]:
    with path.open(newline="", encoding="utf-8") as stream:
        first_rows = list(csv.DictReader(stream))
    first = {
        (row["series"], float(row["time_s"])): int(row["count_digitized"]) for row in first_rows
    }
    by_series: dict[str, dict[str, float | int]] = {}
    for series in SERIES:
        differences = [
            int(row["count_digitized"]) - first[(series, float(row["time_s"]))]
            for row in rows
            if row["series"] == series
        ]
        if len(differences) != 30:
            raise ValueError(f"Expected 30 matched reads for {series}, got {len(differences)}")
        by_series[series] = {
            "n": len(differences),
            "mean_bias_count": float(np.mean(differences)),
            "mae_count": float(np.mean(np.abs(differences))),
            "rmse_count": float(np.sqrt(np.mean(np.square(differences)))),
            "max_abs_count": int(max(abs(value) for value in differences)),
            "within_both_count_bounds": int(
                sum(abs(value) <= 2 * READ_BOUND_COUNT for value in differences)
            ),
        }
    return by_series


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_PDF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--compare", type=Path, default=FIRST_TRACE)
    args = parser.parse_args()

    rows, diagnostics = extract(args.source)
    write_csv(rows, args.output)
    print(f"Wrote {args.output} ({len(rows)} rows); source_sha256={sha256(args.source)}")
    print(f"Calibration/read diagnostics: {diagnostics}")
    if args.compare.is_file():
        print(
            f"Difference from first trace (descriptive only): {compare_to_first(rows, args.compare)}"
        )


if __name__ == "__main__":
    main()
