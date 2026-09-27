#!/usr/bin/env python3
"""Read the red and green scalar exit-velocity traces in Calbrix Fig. 4.

These are figure reads of the simulated maximum velocity at a tank exit, not
raw solver histories, discharge flow rates, or measured outlet fields. The
Fig. 4 caption/legend assigns red to the CL-415 top exit and green to its
bottom exit; the nearby prose contradicts that mapping by calling the top
trace blue and the bottom red. This extraction follows the caption/legend and
excludes the blue Dash-8 curve.

Source: ``Numerical simulation of aerial liquid drops of Canadair CL-415 and
Dash-8 airtankers.pdf``, PDF page 5 / journal page 1519, Fig. 4. The source
SHA-256 is pinned below. The chart spans t=0..5 s and U_L=0..6 m/s. A 500 dpi
render crop (PDF pixel origin x=450, y=1850; 1700 by 1400 pixels) is calibrated
to the visible tick centers at x=0/5 s and y=0/6 m/s. The legend is inside the
plot area at later times; the retained red/green samples stop before it enters
their trace locations. Red and green masks are applied independently; the blue
Dash-8 mask is never read. Centers are sampled at 0.05 s spacing by linear
interpolation between detected colored pixels. Figure-read bounds are
approximately +/-0.05 m/s and +/-0.01 s; low-tail values have especially high
relative uncertainty. The supported red trace ends at 1.80 s and the green
trace at 1.95 s, where their last distinguishable colored features remain.
Neither end is a digitized zero or a claim of physical shutoff.
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
DEFAULT_OUTPUT = ROOT / "data/derived/calbrix_cl415_fig4_velocities.csv"
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"

# PDF page 5 at 500 dpi. The crop contains the Fig. 4 axes, traces, and legend.
PAGE_NUMBER = 5
RENDER_DPI = 500
CROP_X_PX = 450
CROP_Y_PX = 1850
CROP_WIDTH_PX = 1700
CROP_HEIGHT_PX = 1400

# Tick centers in crop coordinates: t=0/5 s and U_L=0/6 m/s.
X_ZERO_PX = 21.5
X_FIVE_PX = 1473.0
Y_ZERO_PX = 1199.5
Y_SIX_PX = 53.0

SAMPLE_INTERVAL_S = 0.05
READ_BOUND_VELOCITY_M_S = 0.05
READ_BOUND_TIME_S = 0.01
MAX_CENTER_GAP_PX = 30
SERIES_END_S = {
    "cl415_top_exit_red": 1.80,
    "cl415_bottom_exit_green": 1.95,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_ppm(path: Path) -> np.ndarray:
    """Read the binary P6 PPM crop emitted by pdftoppm."""
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
    cursor += 2 if data[cursor : cursor + 2] == b"\r\n" else 1
    pixels = np.frombuffer(data, dtype=np.uint8, offset=cursor)
    expected_size = width * height * 3
    if pixels.size != expected_size:
        raise ValueError(f"Unexpected PPM payload length: {pixels.size} != {expected_size}")
    return pixels.reshape(height, width, 3)


def _render_crop(source_pdf: Path) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix="calbrix-e3-fig4-") as temporary:
        prefix = Path(temporary) / "page5"
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
        image = _read_ppm(prefix.with_suffix(".ppm"))
    if image.shape != (CROP_HEIGHT_PX, CROP_WIDTH_PX, 3):
        raise ValueError(f"Unexpected Fig. 4 crop shape: {image.shape}")
    return image


def _trace_centers(image: np.ndarray, series: str) -> tuple[np.ndarray, np.ndarray]:
    red, green, blue = image.transpose(2, 0, 1)
    if series == "cl415_top_exit_red":
        mask = (red >= 100) & (red >= green * 1.30) & (red >= blue * 1.20)
    elif series == "cl415_bottom_exit_green":
        mask = (green >= 100) & (green >= red * 1.20) & (green >= blue * 1.10)
    else:
        raise ValueError(f"Unknown Fig. 4 series: {series}")

    # Ignore the colored anti-alias pixels merged into the dark horizontal axis.
    mask[int(Y_ZERO_PX - 2) :, :] = False
    columns: list[int] = []
    centers: list[float] = []
    x_start = math.floor(X_ZERO_PX)
    x_end = math.ceil(X_FIVE_PX)
    for column in range(x_start, x_end + 1):
        rows = np.flatnonzero(mask[45:1198, column]) + 45
        if rows.size >= 2:
            columns.append(column)
            centers.append(float(np.median(rows)))

    if not columns:
        raise ValueError(f"No pixels found for Fig. 4 {series} trace")
    return np.asarray(columns, dtype=float), np.asarray(centers, dtype=float)


def _sample_series(image: np.ndarray, series: str, end_s: float) -> list[dict[str, str]]:
    columns, centers = _trace_centers(image, series)
    times = np.round(np.arange(SAMPLE_INTERVAL_S, end_s + 1e-9, SAMPLE_INTERVAL_S), 2)
    sample_x = X_ZERO_PX + (X_FIVE_PX - X_ZERO_PX) * times / 5.0
    rows: list[dict[str, str]] = []
    for time_s, pixel_x in zip(times, sample_x, strict=True):
        right = int(np.searchsorted(columns, pixel_x, side="left"))
        if right == 0 or right == len(columns):
            raise ValueError(f"No bracketing pixels for {series} at t={time_s:.2f} s")
        left = right - 1
        if columns[right] - columns[left] > MAX_CENTER_GAP_PX:
            raise ValueError(f"Trace gap too large for {series} at t={time_s:.2f} s")
        pixel_y = float(np.interp(pixel_x, columns[left : right + 1], centers[left : right + 1]))
        velocity = max(
            0.0,
            (Y_ZERO_PX - pixel_y) * 6.0 / (Y_ZERO_PX - Y_SIX_PX),
        )
        rows.append(
            {
                "series": series,
                "time_s": f"{time_s:.2f}",
                "max_exit_velocity_digitized_m_s": f"{velocity:.3f}",
                "read_bound_velocity_m_s": f"{READ_BOUND_VELOCITY_M_S:.2f}",
                "read_bound_time_s": f"{READ_BOUND_TIME_S:.2f}",
                "plot_x_px": f"{pixel_x:.3f}",
                "plot_y_px": f"{pixel_y:.3f}",
            }
        )
    return rows


def digitize(source_pdf: Path, output_csv: Path) -> tuple[int, int, str]:
    source_hash = _sha256(source_pdf)
    if source_hash != EXPECTED_PDF_SHA256:
        raise ValueError(
            f"Unexpected Calbrix PDF SHA-256 {source_hash}; inspect the E3 source record"
        )

    image = _render_crop(source_pdf)
    rows: list[dict[str, str]] = []
    for series, end_s in SERIES_END_S.items():
        rows.extend(_sample_series(image, series, end_s))

    fields = (
        "series",
        "time_s",
        "max_exit_velocity_digitized_m_s",
        "read_bound_velocity_m_s",
        "read_bound_time_s",
        "plot_x_px",
        "plot_y_px",
    )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    counts = {series: sum(row["series"] == series for row in rows) for series in SERIES_END_S}
    return counts["cl415_top_exit_red"], counts["cl415_bottom_exit_green"], source_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_PDF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    red_count, green_count, source_hash = digitize(args.source, args.output)
    print(
        f"Wrote {args.output}: red_top={red_count}, green_bottom={green_count}; "
        f"source_sha256={source_hash}"
    )


if __name__ == "__main__":
    main()
