#!/usr/bin/env python3
"""Create a second raster read of the Dash-8 velocity curve in Calbrix Fig. 4.

The retained first-pass CSV is a manual centerline read and remains unchanged.
This pass decodes the embedded plot JPEG with Poppler, selects the blue trace by
an explicit RGB mask, and samples its median pixel center at 0.1 s intervals.
It is a figure read, not raw outlet history or a complete inlet profile.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import math
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PDF = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
DEFAULT_OUTPUT = ROOT / "data/derived/calbrix_dash8_fig4_velocity_independent.csv"
PRIMARY_CSV = ROOT / "data/derived/calbrix_dash8_fig4_velocity.csv"
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"

PDF_PAGE = 5
JOURNAL_PAGE = 1519
FIGURE = 4
SOURCE_IMAGE_ID = "source-5"
SOURCE_IMAGE_WIDTH = 1464
SOURCE_IMAGE_HEIGHT = 1157

# Figure coordinates from the E2 source record (image origin is top-left).
TIME_MIN_S = 0.0
TIME_MAX_S = 5.0
X_AT_TIME_MIN_PX = 9.0
X_AT_TIME_MAX_PX = 1459.0
VELOCITY_MIN_M_S = 0.0
VELOCITY_MAX_M_S = 6.0
Y_AT_VELOCITY_MIN_PX = 1148.0
Y_AT_VELOCITY_MAX_PX = 7.0
SAMPLE_STEP_S = 0.1

# The blue legend stroke overlaps the data trace for about 2.6–3.1 s. In this
# image the data branch lies below y=500 px, while the legend is above it.
LEGEND_OVERLAP_START_S = 2.6
LEGEND_OVERLAP_END_S = 3.1
LOWER_DATA_BRANCH_MIN_Y_PX = 500

# Same explicit blue RGB-dominance mask used in the local Calbrix raster work.
BLUE_MIN_DELTA_RED = 40
BLUE_MIN_DELTA_GREEN = 30
BLUE_MIN = 90
BLUE_MAX_RED = 220

READ_BOUND_TIME_S = 0.03
INITIAL_READ_BOUND_M_S = 0.15
SHARP_DECLINE_READ_BOUND_M_S = 0.20
ORDINARY_READ_BOUND_M_S = 0.10

FIELDNAMES = (
    "time_s",
    "u_l_m_s",
    "figure_read_bound_time_s",
    "figure_read_bound_u_l_m_s",
    "source_pdf_sha256",
    "pdf_page",
    "journal_page",
    "figure",
    "series_id",
    "source_pixel_x",
    "source_pixel_y",
    "sample_kind",
    "read_method",
)

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _extract_embedded_jpeg(source_pdf: Path, directory: Path) -> bytes:
    """Render page 5 to SVG and extract the exact source-5 JPEG payload."""
    prefix = directory / "page5"
    subprocess.run(
        [
            "pdftocairo",
            "-f",
            str(PDF_PAGE),
            "-l",
            str(PDF_PAGE),
            "-svg",
            str(source_pdf),
            str(prefix),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    svg_path = prefix if prefix.is_file() else prefix.with_suffix(".svg")
    if not svg_path.is_file():
        raise FileNotFoundError(f"pdftocairo did not write the page SVG at {prefix}")

    root = ElementTree.parse(svg_path).getroot()
    image = next(
        (
            element
            for element in root.iter(f"{{{SVG_NS}}}image")
            if element.attrib.get("id") == SOURCE_IMAGE_ID
        ),
        None,
    )
    if image is None:
        raise ValueError(f"SVG page {PDF_PAGE} has no image element {SOURCE_IMAGE_ID!r}")
    width = int(float(image.attrib["width"]))
    height = int(float(image.attrib["height"]))
    if (width, height) != (SOURCE_IMAGE_WIDTH, SOURCE_IMAGE_HEIGHT):
        raise ValueError(f"unexpected embedded plot size {width}x{height}")

    data_url = image.attrib.get(f"{{{XLINK_NS}}}href", image.attrib.get("href", ""))
    header, separator, encoded = data_url.partition(",")
    if not separator or header != "data:image/jpeg;base64":
        raise ValueError("source-5 image is not a base64 JPEG")
    return base64.b64decode(encoded, validate=True)


def _wrap_jpeg_as_pdf(jpeg: bytes, output_pdf: Path) -> None:
    """Place the original JPEG at native size for Poppler's PPM decoder."""
    width, height = SOURCE_IMAGE_WIDTH, SOURCE_IMAGE_HEIGHT
    content = f"q {width} 0 0 {height} 0 0 cm /Im0 Do Q".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            "/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>"
        ).encode("ascii"),
        (
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpeg)} >>\nstream\n"
        ).encode("ascii")
        + jpeg
        + b"\nendstream",
        f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    output_pdf.write_bytes(pdf)


def _ppm_token(data: bytes, offset: int) -> tuple[bytes, int]:
    while offset < len(data):
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
    while offset < len(data) and data[offset] not in b" \t\r\n\v\f#":
        offset += 1
    if start == offset:
        raise ValueError("incomplete PPM header")
    return data[start:offset], offset


def _read_ppm(path: Path) -> np.ndarray:
    data = path.read_bytes()
    offset = 0
    magic, offset = _ppm_token(data, offset)
    width_token, offset = _ppm_token(data, offset)
    height_token, offset = _ppm_token(data, offset)
    maximum_token, offset = _ppm_token(data, offset)
    if magic != b"P6" or int(maximum_token) != 255:
        raise ValueError(f"expected 8-bit binary RGB PPM, got {magic!r}/{maximum_token!r}")
    width, height = int(width_token), int(height_token)
    if data[offset : offset + 2] == b"\r\n":
        offset += 2
    elif offset < len(data) and data[offset] in b" \t\r\n\v\f":
        offset += 1
    pixels = np.frombuffer(data, dtype=np.uint8, offset=offset)
    if pixels.size != width * height * 3:
        raise ValueError("PPM pixel count does not match its header")
    image = pixels.reshape(height, width, 3)
    if image.shape != (SOURCE_IMAGE_HEIGHT, SOURCE_IMAGE_WIDTH, 3):
        raise ValueError(f"unexpected native-size raster {image.shape[1]}x{image.shape[0]}")
    return image


def _decode_jpeg_with_poppler(jpeg: bytes, directory: Path) -> np.ndarray:
    wrapper_pdf = directory / "source5.pdf"
    prefix = directory / "source5_native"
    _wrap_jpeg_as_pdf(jpeg, wrapper_pdf)
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "1",
            "-r",
            "72",
            "-singlefile",
            str(wrapper_pdf),
            str(prefix),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return _read_ppm(prefix.with_suffix(".ppm"))


def _blue_mask(image: np.ndarray) -> np.ndarray:
    red = image[:, :, 0].astype(np.int16)
    green = image[:, :, 1].astype(np.int16)
    blue = image[:, :, 2].astype(np.int16)
    return (
        (blue - red > BLUE_MIN_DELTA_RED)
        & (blue - green > BLUE_MIN_DELTA_GREEN)
        & (blue > BLUE_MIN)
        & (red < BLUE_MAX_RED)
    )


def _read_bound_velocity(time_s: float) -> float:
    if time_s <= 0.2:
        return INITIAL_READ_BOUND_M_S
    if 3.8 <= time_s <= 4.2:
        return SHARP_DECLINE_READ_BOUND_M_S
    return ORDINARY_READ_BOUND_M_S


def _velocity_from_pixel_y(pixel_y: float) -> float:
    return (
        VELOCITY_MAX_M_S
        * (Y_AT_VELOCITY_MIN_PX - pixel_y)
        / (Y_AT_VELOCITY_MIN_PX - Y_AT_VELOCITY_MAX_PX)
    )


def _read_trace(image: np.ndarray) -> list[dict[str, str]]:
    blue = _blue_mask(image)
    rows = []
    for sample_index in range(round((TIME_MAX_S - TIME_MIN_S) / SAMPLE_STEP_S) + 1):
        time_s = round(TIME_MIN_S + sample_index * SAMPLE_STEP_S, 10)
        pixel_x = int(
            round(
                X_AT_TIME_MIN_PX
                + (time_s - TIME_MIN_S)
                * (X_AT_TIME_MAX_PX - X_AT_TIME_MIN_PX)
                / (TIME_MAX_S - TIME_MIN_S)
            )
        )
        if time_s == TIME_MIN_S:
            # The digitized curve starts at the visible axes intersection.
            pixel_y = Y_AT_VELOCITY_MIN_PX
            velocity = 0.0
            sample_kind = "axes_origin"
        else:
            y_pixels = np.flatnonzero(blue[:, pixel_x])
            if LEGEND_OVERLAP_START_S <= time_s <= LEGEND_OVERLAP_END_S:
                y_pixels = y_pixels[y_pixels >= LOWER_DATA_BRANCH_MIN_Y_PX]
            if y_pixels.size == 0:
                raise ValueError(f"no blue curve pixels at t={time_s:.1f} s, x={pixel_x}")
            pixel_y = float(np.median(y_pixels))
            velocity = _velocity_from_pixel_y(pixel_y)
            sample_kind = (
                "lower_data_branch" if time_s >= 2.6 and time_s <= 3.1 else "column_median"
            )

        if not math.isfinite(velocity) or velocity < 0:
            raise ValueError(f"invalid velocity {velocity} at t={time_s}")
        rows.append(
            {
                "time_s": f"{time_s:.1f}",
                "u_l_m_s": f"{velocity:.3f}",
                "figure_read_bound_time_s": f"{READ_BOUND_TIME_S:.2f}",
                "figure_read_bound_u_l_m_s": f"{_read_bound_velocity(time_s):.2f}",
                "source_pdf_sha256": EXPECTED_PDF_SHA256,
                "pdf_page": str(PDF_PAGE),
                "journal_page": str(JOURNAL_PAGE),
                "figure": str(FIGURE),
                "series_id": "dash8_blue",
                "source_pixel_x": str(pixel_x),
                "source_pixel_y": f"{pixel_y:.3f}",
                "sample_kind": sample_kind,
                "read_method": "blue_rgb_mask_column_median",
            }
        )
    return rows


def digitize(source_pdf: Path, output_csv: Path) -> tuple[list[dict[str, str]], str]:
    source_hash = sha256(source_pdf)
    if source_hash != EXPECTED_PDF_SHA256:
        raise ValueError(f"Unexpected Calbrix PDF SHA-256 {source_hash}")
    with tempfile.TemporaryDirectory(prefix="calbrix-dash8-fig4-") as temporary:
        workdir = Path(temporary)
        jpeg = _extract_embedded_jpeg(source_pdf, workdir)
        image = _decode_jpeg_with_poppler(jpeg, workdir)
    rows = _read_trace(image)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows, source_hash


def compare_primary(rows: list[dict[str, str]], primary_csv: Path) -> dict[str, float | int]:
    with primary_csv.open(newline="", encoding="utf-8") as stream:
        primary_rows = list(csv.DictReader(stream))
    if len(primary_rows) != len(rows):
        raise ValueError("primary and independent traces have different sample counts")
    deltas = []
    for first, second in zip(primary_rows, rows, strict=True):
        if float(first["time_s"]) != float(second["time_s"]):
            raise ValueError("primary and independent traces have different sample times")
        deltas.append(float(second["u_l_m_s"]) - float(first["u_l_m_s"]))
    absolute = np.abs(np.asarray(deltas))
    return {
        "n": len(deltas),
        "mean_signed_difference_m_s": float(np.mean(deltas)),
        "mean_absolute_difference_m_s": float(np.mean(absolute)),
        "rmse_m_s": float(np.sqrt(np.mean(np.square(deltas)))),
        "maximum_absolute_difference_m_s": float(np.max(absolute)),
        "within_combined_nominal_ordinate_bounds": sum(
            abs(delta)
            <= float(first["figure_read_bound_u_l_m_s"])
            + float(second["figure_read_bound_u_l_m_s"])
            for first, second, delta in zip(primary_rows, rows, deltas, strict=True)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_PDF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--compare", type=Path, default=PRIMARY_CSV)
    args = parser.parse_args()

    rows, source_hash = digitize(args.source, args.output)
    print(f"Wrote {args.output} ({len(rows)} samples); source_sha256={source_hash}")
    if args.compare.is_file():
        print(
            "Nominal-time difference from primary trace (not a gate): "
            f"{compare_primary(rows, args.compare)}"
        )


if __name__ == "__main__":
    main()
