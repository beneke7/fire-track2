#!/usr/bin/env python3
"""Independently trace Rouaix et al. Fig. 13 Case 1 from a 600 dpi raster.

The script renders PDF page 13 to temporary raw PPM with Poppler, then samples
pixels using only the Python standard library. It does not inspect PDF/SVG
vector paths. The temporary PDF and raster are not copied into the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import mmap
import statistics
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CSV = ROOT / "data" / "derived" / "rouaix_e1_case1_fig13.csv"
DEFAULT_OUTPUT = ROOT / "data" / "derived" / "rouaix_e1_case1_fig13_raster.csv"
PDF_PAGE = 13
RENDER_DPI = 600
EXPECTED_RASTER_SIZE = (4961, 6615)
EXPECTED_PDF_SHA256 = "624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446"

# Tick centers measured on the 600 dpi raster. Values are the printed major
# ticks from Figure 13; raster y coordinates increase down the page.
PANELS = {
    "penetration_y": {
        "xpix": [866.5, 1231.0, 1595.5, 1959.5, 2324.5],
        "xval": [0, 2, 4, 6, 8],
        "ypix": [1666.5, 1430.5, 1194.5, 958.5, 723.0, 487.0],
        "yval": [0, 2, 4, 6, 8, 10],
        "bbox": (850, 2350, 475, 1680),
    },
    "width_z": {
        "xpix": [2780.5, 3072.0, 3363.5, 3655.0, 3946.5, 4238.5],
        "xval": [0, 0.5, 1, 1.5, 2, 2.5],
        "ypix": [1666.5, 1431.5, 1196.0, 960.5, 725.0, 489.5],
        "yval": [0, 1, 2, 3, 4, 5],
        "bbox": (2765, 4255, 480, 1680),
    },
}
OUTPUT_FIELDS = [
    "observable",
    "x_over_dj",
    "value_over_dj_raster",
    "sigma_raster_bound",
    "source_value_over_dj",
    "source_sigma_value_bound",
    "source_sigma_x_bound",
    "local_abs_slope",
    "trace_window_px",
    "trace_columns",
    "trace_xpix_min",
    "trace_xpix_max",
]


def ppm_token(stream: object) -> bytes:
    """Read one PPM header token, including comments and whitespace."""
    whitespace = b" \t\r\n\v\f"
    while True:
        char = stream.read(1)  # type: ignore[attr-defined]
        if not char:
            raise ValueError("truncated PPM header")
        if char in whitespace:
            continue
        if char == b"#":
            stream.readline()  # type: ignore[attr-defined]
            continue
        token = bytearray(char)
        break

    while True:
        char = stream.read(1)  # type: ignore[attr-defined]
        if not char:
            break
        if char in whitespace:
            if char == b"\r":
                next_char = stream.read(1)  # type: ignore[attr-defined]
                if next_char != b"\n":
                    stream.seek(-1, 1)  # type: ignore[attr-defined]
            break
        if char == b"#":
            stream.readline()  # type: ignore[attr-defined]
            break
        token.extend(char)
    return bytes(token)


class PPMRaster:
    """Memory-mapped reader for Poppler's 8-bit, raw RGB PPM output."""

    def __init__(self, path: Path) -> None:
        self._stream = path.open("rb")
        if ppm_token(self._stream) != b"P6":
            self._stream.close()
            raise ValueError("expected raw RGB PPM (P6)")
        self.width = int(ppm_token(self._stream))
        self.height = int(ppm_token(self._stream))
        max_value = int(ppm_token(self._stream))
        if max_value != 255:
            self._stream.close()
            raise ValueError(f"expected 8-bit PPM values, got max value {max_value}")
        self.data_offset = self._stream.tell()
        expected_length = self.data_offset + self.width * self.height * 3
        if path.stat().st_size != expected_length:
            self._stream.close()
            raise ValueError("PPM pixel data length does not match its header")
        self._data = mmap.mmap(self._stream.fileno(), 0, access=mmap.ACCESS_READ)

    def green_rows(self, x: int, y_min: int, y_max: int) -> list[int]:
        """Return rows whose pixels are within RGB distance 100 of bright green."""
        rows = []
        for y in range(y_min, y_max + 1):
            offset = self.data_offset + (y * self.width + x) * 3
            red, green, blue = self._data[offset : offset + 3]
            distance_squared = red * red + (green - 255) ** 2 + blue * blue
            if distance_squared < 100**2:
                rows.append(y)
        return rows

    def close(self) -> None:
        self._data.close()
        self._stream.close()


def linear_fit(x_values: list[float], y_values: list[float]) -> tuple[float, float]:
    """Ordinary least-squares slope and intercept, matching the raster calibration."""
    x_mean = statistics.fmean(x_values)
    y_mean = statistics.fmean(y_values)
    denominator = sum((value - x_mean) ** 2 for value in x_values)
    slope = (
        sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values, strict=True))
        / denominator
    )
    return slope, y_mean - slope * x_mean


def calibrations() -> dict[str, tuple[float, float, float, float]]:
    result = {}
    for observable, panel in PANELS.items():
        x_slope, x_intercept = linear_fit(panel["xpix"], panel["xval"])
        y_slope, y_intercept = linear_fit(panel["ypix"], panel["yval"])
        result[observable] = (x_slope, x_intercept, y_slope, y_intercept)
    return result


def centerline_at(
    raster: PPMRaster,
    calibration: tuple[float, float, float, float],
    observable: str,
    x_value: float,
) -> tuple[float, float, float, int, int, tuple[float, float]] | None:
    panel = PANELS[observable]
    if abs(x_value) < 1e-12:
        # All curves meet at the nozzle origin; plotted markers overlap there.
        return 0.0, 0.020, 0.0, 0, 0, (0.0, 0.0)

    x_slope, x_intercept, y_slope, y_intercept = calibration
    x_pixel = (x_value - x_intercept) / x_slope
    x_min, x_max, y_min, y_max = panel["bbox"]
    for radius in (7, 12, 20, 30, 42):
        first_x = max(x_min, int(x_pixel - radius))
        last_x = min(x_max, int(x_pixel + radius + 0.999999))
        points = []
        for x_pixel_column in range(first_x, last_x + 1):
            rows = raster.green_rows(x_pixel_column, y_min, y_max)
            if rows:
                points.append((float(x_pixel_column), float(statistics.median(rows))))
        if len(points) >= 5:
            break
    if len(points) < 2:
        return None

    x_pixels = [point[0] for point in points]
    y_pixels = [point[1] for point in points]
    slopes = [
        (y_pixels[j] - y_pixels[i]) / (x_pixels[j] - x_pixels[i])
        for i, j in itertools.combinations(range(len(x_pixels)), 2)
        if x_pixels[j] != x_pixels[i]
    ]
    local_slope = statistics.median(slopes) if slopes else 0.0
    center_y = statistics.median(y - local_slope * (x - x_pixel) for x, y in points)
    residuals = [(y - center_y - local_slope * (x - x_pixel)) * y_slope for x, y in points]
    residual_mad = statistics.median(
        abs(value - statistics.median(residuals)) for value in residuals
    )
    sigma = max(0.025, 2.0 * 1.4826 * residual_mad + 0.015)
    sides_visible = (any(x < x_pixel for x in x_pixels), any(x > x_pixel for x in x_pixels))
    if not all(sides_visible):
        nearest_distance = min(abs(x - x_pixel) for x in x_pixels)
        sigma += min(0.15, abs(local_slope * y_slope) * nearest_distance)

    ordinate = center_y * y_slope + y_intercept
    normalized_slope = abs(local_slope * y_slope / x_slope)
    return (
        ordinate,
        sigma,
        normalized_slope,
        radius,
        len(points),
        (min(x_pixels), max(x_pixels)),
    )


def render_pdf_page(pdf_path: Path, output_prefix: Path) -> Path:
    command = [
        "pdftoppm",
        "-f",
        str(PDF_PAGE),
        "-l",
        str(PDF_PAGE),
        "-r",
        str(RENDER_DPI),
        "-singlefile",
        str(pdf_path),
        str(output_prefix),
    ]
    subprocess.run(command, check=True)
    ppm_path = output_prefix.with_suffix(".ppm")
    if not ppm_path.is_file():
        raise RuntimeError(f"Poppler did not produce the expected raster: {ppm_path}")
    return ppm_path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="temporary copy of the cited HAL manuscript PDF")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.is_file():
        parser.error(f"PDF does not exist: {pdf_path}")
    if sha256(pdf_path) != EXPECTED_PDF_SHA256:
        parser.error(
            "PDF SHA-256 differs from the version used for the recorded digitizations: "
            f"expected {EXPECTED_PDF_SHA256}"
        )
    if not SOURCE_CSV.is_file():
        parser.error(f"primary digitization does not exist: {SOURCE_CSV}")

    with tempfile.TemporaryDirectory(prefix="rouaix-fig13-raster-") as temporary_dir:
        ppm_path = render_pdf_page(pdf_path, Path(temporary_dir) / "figure13")
        raster = PPMRaster(ppm_path)
        try:
            actual_size = (raster.width, raster.height)
            if actual_size != EXPECTED_RASTER_SIZE:
                raise ValueError(
                    "unexpected page raster dimensions "
                    f"{actual_size}; expected {EXPECTED_RASTER_SIZE} at {RENDER_DPI} dpi"
                )
            axis_calibrations = calibrations()
            with SOURCE_CSV.open(encoding="utf-8", newline="") as source_stream:
                source_rows = list(csv.DictReader(source_stream))

            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w", encoding="utf-8", newline="") as output_stream:
                writer = csv.DictWriter(
                    output_stream, fieldnames=OUTPUT_FIELDS, lineterminator="\n"
                )
                writer.writeheader()
                for row in source_rows:
                    observable = row["observable"]
                    x_value = float(row["x_over_dj"])
                    result = centerline_at(
                        raster,
                        axis_calibrations[observable],
                        observable,
                        x_value,
                    )
                    if result is None:
                        ordinate, sigma, slope, radius, columns, x_extent = (
                            0.0,
                            0.05,
                            0.0,
                            0,
                            0,
                            (0.0, 0.0),
                        )
                    else:
                        ordinate, sigma, slope, radius, columns, x_extent = result
                    writer.writerow(
                        {
                            "observable": observable,
                            "x_over_dj": f"{x_value:.3f}",
                            "value_over_dj_raster": f"{ordinate:.4f}",
                            "sigma_raster_bound": f"{sigma:.4f}",
                            "source_value_over_dj": f"{float(row['value_over_dj']):.4f}",
                            "source_sigma_value_bound": f"{float(row['sigma_value_over_dj']):.4f}",
                            "source_sigma_x_bound": f"{float(row['sigma_x_over_dj']):.4f}",
                            "local_abs_slope": f"{slope:.4f}",
                            "trace_window_px": radius,
                            "trace_columns": columns,
                            "trace_xpix_min": f"{x_extent[0]:.1f}",
                            "trace_xpix_max": f"{x_extent[1]:.1f}",
                        }
                    )
        finally:
            raster.close()


if __name__ == "__main__":
    main()
