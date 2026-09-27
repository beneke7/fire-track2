#!/usr/bin/env python3
"""Digitize the plotted CL-415 structure-count traces in Calbrix Fig. 11(a).

The output is a bounded figure read, not the authors' raw Matlab count history.
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
DEFAULT_OUTPUT = ROOT / "data/derived/calbrix_cl415_fig11_structure_counts.csv"
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"

# PDF page 10, rendered at 500 dpi. This crop contains Fig. 11(a)'s axes and
# traces; the two legend swatches are removed before locating the line centers.
PAGE_NUMBER = 10
RENDER_DPI = 500
CROP_X_PX = 600
CROP_Y_PX = 2040
CROP_WIDTH_PX = 1450
CROP_HEIGHT_PX = 1200

# Tick centers measured in the rendered crop. Fig. 11(a) labels t=0..3 s and
# N=0..400; the cloud trace rises slightly above the highest labelled tick.
X_ZERO_PX = 55.5
X_THREE_PX = 1408.0
Y_ZERO_PX = 1127.5
Y_FOUR_HUNDRED_PX = 121.5
SAMPLE_INTERVAL_S = 0.1
READ_BOUND_COUNT = 5
READ_BOUND_TIME_S = 0.01


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_ppm(path: Path) -> np.ndarray:
    """Read the P6 PPM crop emitted by pdftoppm without an image dependency."""
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
    expected_size = width * height * 3
    if pixels.size != expected_size:
        raise ValueError(f"Unexpected PPM payload length: {pixels.size} != {expected_size}")
    return pixels.reshape(height, width, 3)


def _render_plot_crop(source_pdf: Path) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix="calbrix-e3-fig11-") as temporary:
        prefix = Path(temporary) / "page10"
        subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(PAGE_NUMBER),
                "-l",
                str(PAGE_NUMBER),
                "-r",
                str(RENDER_DPI),
                "-x",
                str(CROP_X_PX),
                "-y",
                str(CROP_Y_PX),
                "-W",
                str(CROP_WIDTH_PX),
                "-H",
                str(CROP_HEIGHT_PX),
                "-singlefile",
                str(source_pdf),
                str(prefix),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        ppm_path = prefix.with_suffix(".ppm")
        image = _read_ppm(ppm_path)
    if image.shape != (CROP_HEIGHT_PX, CROP_WIDTH_PX, 3):
        raise ValueError(f"Unexpected Fig. 11(a) crop shape: {image.shape}")
    return image


def _trace_centers(image: np.ndarray, series: str) -> tuple[np.ndarray, np.ndarray]:
    red, green, blue = image.transpose(2, 0, 1)
    if series == "cloud_alpha_0p001_to_1":
        mask = (red > 150) & (red > green * 1.65) & (red > blue * 1.4)
        # Fig. 11(a)'s red legend swatch is below the cloud line in this x range.
        mask[730:770, 450:580] = False
    elif series == "core_alpha_0p9_to_1":
        mask = (blue > 130) & (blue > red * 1.6) & (blue > green * 1.35)
        # The blue legend swatch is above the core line in this x range.
        mask[815:860, 450:580] = False
    else:
        raise ValueError(f"Unknown Fig. 11(a) series: {series}")

    columns: list[int] = []
    centers: list[float] = []
    x_start = math.floor(X_ZERO_PX)
    x_end = math.ceil(X_THREE_PX)
    for column in range(x_start, x_end + 1):
        rows = np.flatnonzero(mask[45:1135, column]) + 45
        if rows.size >= 3:
            columns.append(column)
            centers.append(float(np.median(rows)))

    if not columns:
        raise ValueError(f"No pixels found for Fig. 11(a) {series} trace")
    first_sample_x = X_ZERO_PX + (X_THREE_PX - X_ZERO_PX) * SAMPLE_INTERVAL_S / 3.0
    if columns[0] > first_sample_x + 3.0 or columns[-1] < X_THREE_PX - 2.0:
        raise ValueError(
            f"Incomplete Fig. 11(a) {series} trace span: {columns[0]}..{columns[-1]} px"
        )
    return np.asarray(columns, dtype=float), np.asarray(centers, dtype=float)


def digitize(source_pdf: Path, output_csv: Path) -> tuple[int, int, str]:
    source_hash = _sha256(source_pdf)
    if source_hash != EXPECTED_PDF_SHA256:
        raise ValueError(
            f"Unexpected Calbrix PDF SHA-256 {source_hash}; inspect the E3 source record"
        )

    image = _render_plot_crop(source_pdf)
    times = np.round(np.arange(SAMPLE_INTERVAL_S, 3.0 + 1e-9, SAMPLE_INTERVAL_S), 1)
    rows: list[dict[str, str | int]] = []
    for series in ("cloud_alpha_0p001_to_1", "core_alpha_0p9_to_1"):
        columns, centers = _trace_centers(image, series)
        sample_x = X_ZERO_PX + (X_THREE_PX - X_ZERO_PX) * times / 3.0
        sample_y = np.interp(sample_x, columns, centers)
        counts = (Y_ZERO_PX - sample_y) * 400.0 / (Y_ZERO_PX - Y_FOUR_HUNDRED_PX)
        for time_s, pixel_x, pixel_y, count in zip(times, sample_x, sample_y, counts, strict=True):
            rows.append(
                {
                    "series": series,
                    "time_s": f"{time_s:.1f}",
                    "count_digitized": math.floor(float(count) + 0.5),
                    "read_bound_count": READ_BOUND_COUNT,
                    "read_bound_time_s": f"{READ_BOUND_TIME_S:.2f}",
                    "plot_x_px": f"{pixel_x:.3f}",
                    "plot_y_px": f"{pixel_y:.3f}",
                }
            )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "series",
        "time_s",
        "count_digitized",
        "read_bound_count",
        "read_bound_time_s",
        "plot_x_px",
        "plot_y_px",
    )
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    counts = {
        series: sum(row["series"] == series for row in rows)
        for series in (
            "cloud_alpha_0p001_to_1",
            "core_alpha_0p9_to_1",
        )
    }
    return counts["cloud_alpha_0p001_to_1"], counts["core_alpha_0p9_to_1"], source_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_PDF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    cloud_count, core_count, source_hash = digitize(args.source, args.output)
    print(
        f"Wrote {args.output}: cloud={cloud_count}, core={core_count}; source_sha256={source_hash}"
    )


if __name__ == "__main__":
    main()
