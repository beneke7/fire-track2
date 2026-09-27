#!/usr/bin/env python3
"""Independent raster read of the Dash-8 liquid-cloud curves in Calbrix Figs. 6–9.

This script traces page-rendered source panels directly, independently of the
first Dash-8 digitizer. It uses its own page crops, tick-center calibrations,
RGB-distance palettes, and scan-line continuity rule. It reads the plotted
alpha_L = 0.001 cloud/penetration curves, not raw solver output or a final
validation observable.

Source: ``Numerical simulation of aerial liquid drops of Canadair CL-415 and
Dash-8 airtankers.pdf`` (SHA-256 pinned below). Fig. 6(b) is PDF p. 7 / journal
p. 1521; Fig. 7 is PDF p. 8 / journal p. 1522; Figs. 8 and 9 are PDF p. 9 /
journal p. 1523. Each panel is rendered at 500 dpi with a separately measured
crop and tick calibration. Pixel-color distance to the plotted stroke palette
isolates the target line; scan-line centers are read at 4-pixel spacing. The
Fig. 7 solid Dash-8 simulation is represented by its two separate connected
segments, with the visible gap left empty. Fig. 8's caption says t=1 s while
the nearby prose says t=0.5 s; the CSV labels the curve by the caption time and
the conflict is preserved. Fig. 9's t=0.5, 1.0, and 1.5 s Dash-8 curves remain
separate series; no missing points are interpolated. The plotted lines have
approximate raster-read bounds recorded per panel in the CSV.

Calibration note for Fig. 9(a): its printed vertical tick sequence is 0 through
8. On PDF p. 9, ``pdftotext -bbox`` locates the ``0`` label at y=378.97–385.30
pt, ``1`` at 398.49–404.82 pt, and ``8`` at 535.10–541.43 pt. At 500 dpi, the
dark left-axis tick centers are about crop rows 200 (0) and 1287 (8); the zero
tick is the first tick, not the next tick at row about 333. A comparison with
the earlier trace found that it had used the printed 1 tick as zero; the
coordinate correction is reported only as a figure-read reproducibility check,
not independent validation evidence.
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
DEFAULT_OUTPUT = ROOT / "data/derived/calbrix_dash8_cloud_curves_independent.csv"
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"
RENDER_DPI = 500
SCAN_STEP_PX = 4
RGB_DISTANCE_LIMIT = 90.0


@dataclass(frozen=True)
class Panel:
    figure: str
    page: int
    crop_x: int
    crop_y: int
    crop_width: int
    crop_height: int
    x_zero_px: float
    x_max_px: float
    x_max_value: float
    x_variable: str
    x_unit: str
    y_zero_px: float
    y_max_px: float
    y_max_value: float
    y_variable: str
    y_unit: str
    read_bound_x: float
    read_bound_y: float


# These are independent 500-dpi page crops and tick centers, measured from the
# rendered axes (the crop origin is the PDF page pixel origin at 500 dpi).
PANELS = {
    "fig6": Panel(
        figure="Fig. 6(b)",
        page=7,
        crop_x=2050,
        crop_y=300,
        crop_width=1800,
        crop_height=1700,
        x_zero_px=215.5,
        x_max_px=1631.0,
        x_max_value=2.0,
        x_variable="streamwise_distance_y",
        x_unit="m",
        y_zero_px=271.5,
        y_max_px=1390.0,
        y_max_value=3.0,
        y_variable="vertical_penetration_Z",
        y_unit="m",
        read_bound_x=0.02,
        read_bound_y=0.03,
    ),
    "fig7": Panel(
        figure="Fig. 7",
        page=8,
        crop_x=420,
        crop_y=300,
        crop_width=1800,
        crop_height=1700,
        x_zero_px=104.5,
        x_max_px=1516.0,
        x_max_value=2.0,
        x_variable="normalized_streamwise_distance_y_over_Lc",
        x_unit="1",
        y_zero_px=188.5,
        y_max_px=1256.0,
        y_max_value=2.0,
        y_variable="normalized_vertical_penetration_Z_over_Lc",
        y_unit="1",
        read_bound_x=0.02,
        read_bound_y=0.02,
    ),
    "fig8": Panel(
        figure="Fig. 8(b)",
        page=9,
        crop_x=2000,
        crop_y=550,
        crop_width=1900,
        crop_height=1700,
        x_zero_px=65.5,
        x_max_px=1492.0,
        x_max_value=6.0,
        x_variable="lateral_expansion_L",
        x_unit="m",
        y_zero_px=201.0,
        y_max_px=1305.0,
        y_max_value=3.5,
        y_variable="vertical_distance_z",
        y_unit="m",
        read_bound_x=0.05,
        read_bound_y=0.04,
    ),
    "fig9": Panel(
        figure="Fig. 9(a)",
        page=9,
        crop_x=420,
        crop_y=2450,
        crop_width=1850,
        crop_height=1700,
        x_zero_px=167.5,
        x_max_px=1540.0,
        x_max_value=9.0,
        x_variable="normalized_lateral_expansion_L_over_Lc",
        x_unit="1",
        y_zero_px=200.0,
        y_max_px=1287.0,
        y_max_value=8.0,
        y_variable="normalized_vertical_distance_z_over_Lc",
        y_unit="1",
        read_bound_x=0.08,
        read_bound_y=0.07,
    ),
}

# Crops are 500-dpi page pixels, independent per panel: Fig. 6(b) uses page-7
# crop (2050, 300), Fig. 7 page-8 crop (420, 300), Fig. 8(b) page-9 crop
# (2000, 550), and Fig. 9(a) page-9 crop (420, 2450). In each panel the x/y
# zero and maximum pixel centers below were read from visible axis ticks. Their
# plotted extents are respectively 0–2 m by 0–3 m; 0–2 by 0–2; 0–6 m by
# 0–3.5 m; and 0–9 by 0–8. Fig. 9's tick labels and zero-origin mapping are
# additionally checked against the PDF text boxes in the focused test.

# RGB stroke cores read from the embedded figure colors, not inferred from the
# earlier extractor's masks. The figures use blue/red in Figs. 6–8 and RGB
# primary strokes for the three time curves in Fig. 9(a).
PALETTES = {
    "dash8_blue": (62, 76, 170),
    "fig9_t0p5_red": (250, 10, 27),
    "fig9_t1p0_blue": (0, 0, 252),
    "fig9_t1p5_green": (0, 252, 53),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_ppm(path: Path) -> np.ndarray:
    """Decode the binary P6 raster produced by pdftoppm."""
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
    if pixels.size != width * height * 3:
        raise ValueError("Unexpected PPM payload length")
    return pixels.reshape(height, width, 3)


def _render_panel(panel: Panel) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix="calbrix-dash8-e2-") as temporary:
        prefix = Path(temporary) / f"page-{panel.page}"
        subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(panel.page),
                "-l",
                str(panel.page),
                "-r",
                str(RENDER_DPI),
                "-x",
                str(panel.crop_x),
                "-y",
                str(panel.crop_y),
                "-W",
                str(panel.crop_width),
                "-H",
                str(panel.crop_height),
                "-singlefile",
                str(SOURCE_PDF),
                str(prefix),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        image = _read_ppm(prefix.with_suffix(".ppm"))
    if image.shape != (panel.crop_height, panel.crop_width, 3):
        raise ValueError(f"Unexpected {panel.figure} raster crop: {image.shape}")
    return image


def _frame_mask(mask: np.ndarray, panel: Panel) -> np.ndarray:
    bounded = np.zeros_like(mask, dtype=bool)
    x0 = math.floor(panel.x_zero_px)
    x1 = math.ceil(panel.x_max_px)
    y0 = math.floor(panel.y_zero_px)
    y1 = math.ceil(panel.y_max_px)
    bounded[y0 : y1 + 1, x0 : x1 + 1] = mask[y0 : y1 + 1, x0 : x1 + 1]
    return bounded


def _palette_mask(image: np.ndarray, panel: Panel, palette: str) -> np.ndarray:
    prototype = np.asarray(PALETTES[palette], dtype=np.float32)
    # Nearest-palette RGB distance is deliberately distinct from hue-ratio
    # thresholding. It keeps only saturated stroke cores and excludes labels.
    distance = np.linalg.norm(image.astype(np.float32) - prototype, axis=2)
    return _frame_mask(distance <= RGB_DISTANCE_LIMIT, panel)


def _components(mask: np.ndarray) -> list[list[tuple[int, int, int]]]:
    """Return 8-connected run components as (row, x_start, x_end) tuples."""
    parents: list[int] = []
    runs: list[tuple[int, int, int, int]] = []
    previous: list[tuple[int, int, int]] = []

    def find(label: int) -> int:
        while parents[label] != label:
            parents[label] = parents[parents[label]]
            label = parents[label]
        return label

    def union(first: int, second: int) -> None:
        root_first = find(first)
        root_second = find(second)
        if root_first != root_second:
            parents[root_second] = root_first

    for row_index, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.r_[False, row, False].astype(np.int8)) != 0)
        current: list[tuple[int, int, int]] = []
        for start, stop in zip(edges[::2], edges[1::2], strict=True):
            end = int(stop) - 1
            start = int(start)
            label = len(parents)
            parents.append(label)
            current.append((start, end, label))
            runs.append((row_index, start, end, label))
            for prior_start, prior_end, prior_label in previous:
                if prior_end + 1 < start:
                    continue
                if prior_start - 1 > end:
                    break
                union(label, prior_label)
        previous = current

    grouped: dict[int, list[tuple[int, int, int]]] = {}
    for row, start, end, label in runs:
        grouped.setdefault(find(label), []).append((row, start, end))
    return sorted(grouped.values(), key=lambda component: -sum(e - s + 1 for _, s, e in component))


def _component_mask(shape: tuple[int, int], component: list[tuple[int, int, int]]) -> np.ndarray:
    result = np.zeros(shape, dtype=bool)
    for row, start, end in component:
        result[row, start : end + 1] = True
    return result


def _clusters(indices: np.ndarray, max_pixel_gap: int = 2) -> list[tuple[float, int]]:
    if indices.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(indices) > max_pixel_gap + 1) + 1
    return [
        (float(np.median(group)), int(group.size))
        for group in np.split(indices, breaks)
        if group.size >= 2
    ]


def _make_row(
    panel: Panel,
    series: str,
    segment: int,
    pixel_x: float,
    pixel_y: float,
) -> dict[str, str | int]:
    x_value = (pixel_x - panel.x_zero_px) * panel.x_max_value / (panel.x_max_px - panel.x_zero_px)
    y_value = (pixel_y - panel.y_zero_px) * panel.y_max_value / (panel.y_max_px - panel.y_zero_px)
    return {
        "figure": panel.figure,
        "series": series,
        "segment": segment,
        "x_variable": panel.x_variable,
        "x_unit": panel.x_unit,
        "y_variable": panel.y_variable,
        "y_unit": panel.y_unit,
        "x_value": f"{x_value:.4f}",
        "y_value": f"{y_value:.4f}",
        "read_bound_x": f"{panel.read_bound_x:.3f}",
        "read_bound_y": f"{panel.read_bound_y:.3f}",
        "plot_x_px": f"{pixel_x:.2f}",
        "plot_y_px": f"{pixel_y:.2f}",
    }


def _trace_columns(
    panel: Panel, series: str, mask: np.ndarray, segment: int = 1
) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    x0 = math.ceil(panel.x_zero_px)
    x1 = math.floor(panel.x_max_px)
    y0 = math.floor(panel.y_zero_px)
    y1 = math.ceil(panel.y_max_px)
    for column in range(x0, x1 + 1, SCAN_STEP_PX):
        for center, _ in _clusters(np.flatnonzero(mask[y0 : y1 + 1, column]) + y0):
            rows.append(_make_row(panel, series, segment, float(column), center))
    return rows


def _trace_rows_nearest(
    panel: Panel,
    series: str,
    mask: np.ndarray,
    y_end: int | None = None,
    start_x: float | None = None,
    max_jump_px: float = 100.0,
) -> list[dict[str, str | int]]:
    """Track a colored curve through horizontal scanlines, leaving empty rows blank."""
    rows: list[dict[str, str | int]] = []
    x0 = math.ceil(panel.x_zero_px)
    x1 = math.floor(panel.x_max_px)
    y0 = math.floor(panel.y_zero_px)
    y1 = math.ceil(panel.y_max_px) if y_end is None else y_end
    prior_x = float(x0 + 5) if start_x is None else start_x
    segment = 1
    missing = False
    for row_index in range(y0, y1 + 1, SCAN_STEP_PX):
        candidates = _clusters(np.flatnonzero(mask[row_index, x0 : x1 + 1]) + x0)
        if not candidates:
            missing = True
            continue
        center_x, _ = min(candidates, key=lambda candidate: abs(candidate[0] - prior_x))
        if not missing and abs(center_x - prior_x) > max_jump_px:
            missing = True
            continue
        if missing and rows:
            # Resume at the nearest visible stroke after a raster occlusion or
            # a steep turn. The omitted scanlines remain omitted; no gap is
            # interpolated.
            segment += 1
        rows.append(_make_row(panel, series, segment, center_x, float(row_index)))
        prior_x = center_x
        missing = False
    return rows


def _figure6(image: np.ndarray) -> list[dict[str, str | int]]:
    panel = PANELS["fig6"]
    mask = _palette_mask(image, panel, "dash8_blue")
    main_component = _components(mask)[0]
    line_mask = _component_mask(mask.shape, main_component)
    return _trace_columns(panel, "dash8_alpha0p001", line_mask)


def _figure7(image: np.ndarray) -> list[dict[str, str | int]]:
    panel = PANELS["fig7"]
    mask = _palette_mask(image, panel, "dash8_blue")
    components = _components(mask)
    # The solid simulation is the two large connected blue pieces. Smaller
    # disconnected dashes are the Eq. 4 fit; the separated solid tail is kept.
    solid = [
        component
        for component in components
        if sum(end - start + 1 for _, start, end in component) >= 1500
    ]
    solid.sort(key=lambda component: min(start for _, start, _ in component))
    if len(solid) != 2:
        raise ValueError(f"Expected two separated solid Dash-8 Fig. 7 segments, got {len(solid)}")
    rows: list[dict[str, str | int]] = []
    for segment, component in enumerate(solid, start=1):
        line_mask = _component_mask(mask.shape, component)
        rows.extend(_trace_columns(panel, "dash8_simulation_alpha0p001", line_mask, segment))
    return rows


def _figure8(image: np.ndarray) -> list[dict[str, str | int]]:
    panel = PANELS["fig8"]
    mask = _palette_mask(image, panel, "dash8_blue")
    main_component = _components(mask)[0]
    line_mask = _component_mask(mask.shape, main_component)
    # The caption identifies this comparison at t=1 s; the adjacent prose says
    # t=0.5 s. Preserve the discrepancy in the series name and source note.
    return _trace_rows_nearest(
        panel,
        "dash8_alpha0p001_caption_t1s_prose_t0p5s",
        line_mask,
        max_jump_px=100.0,
    )


def _figure9(image: np.ndarray) -> list[dict[str, str | int]]:
    panel = PANELS["fig9"]
    time_curves = (
        ("fig9_t0p5_red", "fig9_dash8_alpha0p001_t0p5s", 3.3),
        ("fig9_t1p0_blue", "fig9_dash8_alpha0p001_t1p0s", 7.7),
        ("fig9_t1p5_green", "fig9_dash8_alpha0p001_t1p5s", 8.0),
    )
    rows: list[dict[str, str | int]] = []
    for palette, series, y_end_value in time_curves:
        mask = _palette_mask(image, panel, palette)
        end_px = (
            panel.y_zero_px + y_end_value * (panel.y_max_px - panel.y_zero_px) / panel.y_max_value
        )
        rows.extend(
            _trace_rows_nearest(
                panel,
                series,
                mask,
                y_end=math.ceil(end_px),
                max_jump_px=110.0,
            )
        )
    return rows


def digitize(source_pdf: Path, output_csv: Path) -> tuple[int, str]:
    source_hash = _sha256(source_pdf)
    if source_hash != EXPECTED_PDF_SHA256:
        raise ValueError(f"Unexpected Calbrix PDF SHA-256 {source_hash}")
    panel_images = {key: _render_panel(panel) for key, panel in PANELS.items()}
    rows = (
        _figure6(panel_images["fig6"])
        + _figure7(panel_images["fig7"])
        + _figure8(panel_images["fig8"])
        + _figure9(panel_images["fig9"])
    )
    fields = (
        "figure",
        "series",
        "segment",
        "x_variable",
        "x_unit",
        "y_variable",
        "y_unit",
        "x_value",
        "y_value",
        "read_bound_x",
        "read_bound_y",
        "plot_x_px",
        "plot_y_px",
    )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), source_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_PDF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    count, source_hash = digitize(args.source, args.output)
    print(f"Wrote {args.output}: rows={count}; source_sha256={source_hash}")


if __name__ == "__main__":
    main()
