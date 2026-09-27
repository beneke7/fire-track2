#!/usr/bin/env python3
"""Extract the two M134 Fig. 9 plotted series from the supplied vector PDF.

The extracted locations are figure digitizations, not the authors' raw cup
measurements or ADM output.  The script intentionally accepts only the exact
local PDF revision documented in E4_AMORIM_M134_SOURCE.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PDF = ROOT / "WF09123.pdf"
DEFAULT_OUTPUT = ROOT / "data/derived/amorim_m134_fig9.csv"
EXPECTED_PDF_SHA256 = "89e50599fec1bcb872cc99270113d2cc12dbd377a56c9415b3470a64236d15da"

# Coordinates are in the page coordinate system emitted by pdftocairo for PDF
# page 11. These are the 0/600 m and 0/30 L major-tick positions in the
# top-left (M134) panel, not the outer plot-frame corners.
AXIS_X0_PT = 92.995894
AXIS_X600_PT = 276.181097
AXIS_Y0_PT = 228.345248
AXIS_Y30_PT = 95.854389

# Fig. 9's printed legend has one sample symbol per series. These symbols are
# inside the axes and must be excluded from the data trace.
LEGEND_BOX_PT = (217.0, 101.8, 276.7, 123.6)
PLOT_BOX_PT = (93.0, 95.0, 283.0, 229.0)

MEASURED_STROKE = "rgb(56.864929%, 56.079102%, 56.274414%)"
ADM_STROKE = "rgb(13.729858%, 12.159729%, 12.548828%)"
PATH_TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?")
MATRIX = re.compile(r"matrix\(([^)]+)\)")


def _pdf_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _first_closed_subpath(data: str) -> list[tuple[float, float]]:
    """Flatten the first closed SVG path subpath for marker-centre recovery."""
    tokens = PATH_TOKEN.findall(data)
    points: list[tuple[float, float]] = []
    command: str | None = None
    current: tuple[float, float] | None = None
    start: tuple[float, float] | None = None
    index = 0

    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
            if command in {"Z", "z"}:
                if start is not None and points[-1] != start:
                    points.append(start)
                return points

        if command in {"M", "L"}:
            point = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            current = point
            if command == "M":
                start = point
                command = "L"
            points.append(point)
        elif command == "C":
            if current is None:
                raise ValueError("Cubic path has no starting point")
            x0, y0 = current
            x1, y1, x2, y2, x3, y3 = map(float, tokens[index : index + 6])
            index += 6
            for step in range(1, 33):
                t = step / 32
                one_minus_t = 1 - t
                points.append(
                    (
                        one_minus_t**3 * x0
                        + 3 * one_minus_t**2 * t * x1
                        + 3 * one_minus_t * t**2 * x2
                        + t**3 * x3,
                        one_minus_t**3 * y0
                        + 3 * one_minus_t**2 * t * y1
                        + 3 * one_minus_t * t**2 * y2
                        + t**3 * y3,
                    )
                )
            current = (x3, y3)
        else:
            raise ValueError(f"Unsupported marker path command: {command!r}")

    raise ValueError("Marker path has no closed subpath")


def _polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    twice_area = 0.0
    x_numerator = 0.0
    y_numerator = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        x_numerator += (x0 + x1) * cross
        y_numerator += (y0 + y1) * cross
    if math.isclose(twice_area, 0.0, abs_tol=1e-12):
        raise ValueError("Marker outline has zero area")
    return x_numerator / (3 * twice_area), y_numerator / (3 * twice_area)


def _matrix_values(element: ElementTree.Element) -> tuple[float, ...]:
    match = MATRIX.search(element.attrib.get("transform", ""))
    if match is None:
        raise ValueError("Marker is missing its PDF-to-page transform")
    values = tuple(float(value) for value in match.group(1).replace(",", " ").split())
    if len(values) != 6:
        raise ValueError("Expected a six-value SVG matrix")
    return values


def _marker_series(source_pdf: Path) -> list[tuple[str, float, float]]:
    with tempfile.TemporaryDirectory(prefix="amorim-fig9-") as temporary:
        svg_prefix = Path(temporary) / "page"
        subprocess.run(
            [
                "pdftocairo",
                "-f",
                "11",
                "-l",
                "11",
                "-svg",
                str(source_pdf),
                str(svg_prefix),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        svg_path = svg_prefix
        if not svg_path.exists():
            candidates = sorted(Path(temporary).glob("page*.svg"))
            if len(candidates) != 1:
                raise FileNotFoundError("pdftocairo did not create one page-11 SVG")
            svg_path = candidates[0]
        root = ElementTree.parse(svg_path).getroot()

    series: list[tuple[str, float, float]] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "path":
            continue
        stroke = element.attrib.get("stroke")
        if stroke == MEASURED_STROKE:
            label, marker_commands = "measured", "MLLZM"
        elif stroke == ADM_STROKE:
            label, marker_commands = "adm", "MCCCCZM"
        else:
            continue

        data = element.attrib.get("d", "")
        commands = "".join(re.findall(r"[A-Za-z]", data))
        if commands != marker_commands:
            continue

        matrix_a, matrix_b, matrix_c, matrix_d, matrix_e, matrix_f = _matrix_values(element)
        outline = _first_closed_subpath(data)
        page_outline = [
            (
                matrix_a * x + matrix_c * y + matrix_e,
                matrix_b * x + matrix_d * y + matrix_f,
            )
            for x, y in outline
        ]
        page_x = [point[0] for point in page_outline]
        page_y = [point[1] for point in page_outline]
        plot_x_min, plot_y_min, plot_x_max, plot_y_max = PLOT_BOX_PT
        if not (
            min(page_x) >= plot_x_min
            and max(page_x) <= plot_x_max
            and min(page_y) >= plot_y_min
            and max(page_y) <= plot_y_max
        ):
            continue

        local_center_x, local_center_y = _polygon_centroid(outline)
        center_x = matrix_a * local_center_x + matrix_c * local_center_y + matrix_e
        center_y = matrix_b * local_center_x + matrix_d * local_center_y + matrix_f
        legend_x_min, legend_y_min, legend_x_max, legend_y_max = LEGEND_BOX_PT
        if legend_x_min <= center_x <= legend_x_max and legend_y_min <= center_y <= legend_y_max:
            continue
        series.append((label, center_x, center_y))

    counts = {label: sum(row[0] == label for row in series) for label in ("measured", "adm")}
    if counts != {"measured": 442, "adm": 273}:
        raise ValueError(
            "Unexpected M134 Fig. 9 marker count; inspect the PDF/SVG extraction "
            f"before updating this digitization (found {counts})"
        )
    return series


def digitize(source_pdf: Path, output_csv: Path) -> tuple[int, int, str]:
    source_hash = _pdf_sha256(source_pdf)
    if source_hash != EXPECTED_PDF_SHA256:
        raise ValueError(f"Unexpected WF09123.pdf SHA-256 {source_hash}; see the E4 source record")

    points = _marker_series(source_pdf)
    x_scale = 600.0 / (AXIS_X600_PT - AXIS_X0_PT)
    y_scale = 30.0 / (AXIS_Y0_PT - AXIS_Y30_PT)
    rows = []
    for label in ("measured", "adm"):
        selected = sorted((x, y) for series, x, y in points if series == label)
        for marker_index, (page_x, page_y) in enumerate(selected, start=1):
            x_m = (page_x - AXIS_X0_PT) * x_scale
            vx_l = (AXIS_Y0_PT - page_y) * y_scale
            if not (0.0 <= x_m <= 600.0 and 0.0 <= vx_l <= 30.0):
                raise ValueError(f"Digitized point falls outside M134 plot axes: {x_m}, {vx_l}")
            rows.append(
                {
                    "series": label,
                    "marker_index": marker_index,
                    "x_page_pt": f"{page_x:.9f}",
                    "y_page_pt": f"{page_y:.9f}",
                    "x_m": f"{x_m:.6f}",
                    "Vx_L": f"{vx_l:.6f}",
                }
            )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("series", "marker_index", "x_page_pt", "y_page_pt", "x_m", "Vx_L"),
        )
        writer.writeheader()
        writer.writerows(rows)
    counts = {label: sum(row["series"] == label for row in rows) for label in ("measured", "adm")}
    return counts["measured"], counts["adm"], source_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_PDF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    measured_count, adm_count, source_hash = digitize(args.source, args.output)
    print(f"Wrote {measured_count} measured and {adm_count} ADM markers to {args.output}")
    print(f"Source SHA-256: {source_hash}")


if __name__ == "__main__":
    main()
