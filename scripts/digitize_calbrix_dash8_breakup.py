#!/usr/bin/env python3
"""Reproducible raster extraction of Calbrix Dash-8 breakup observables.

This writes figure-read artifacts only. It never reads a CFD result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PDF = (
    ROOT
    / "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
)
EXPECTED_PDF_SHA256 = "128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4"

FIG5_PAGE = 6
FIG11_PAGE = 10
DPI = 300
FIG5_REGIONS = {
    "0.1": (1180, 300, 2240, 600),
    "1.0": (1180, 690, 2240, 1260),
    "4.8": (1180, 1260, 2240, 1880),
}
TEAL_DELTA_THRESHOLDS = (16, 24, 32)
COMPONENT_AREA_CUTOFFS_PX = (4, 16, 64, 256)

# Full-page pixel coordinates from the 300 dpi render of PDF page 10.
# Axis terminal centers correspond to panel (c)'s labelled t=0..6 s and
# N=0..700 liquid-structure axes. Error allowances are recorded separately.
FIG11C_AXES = {
    "x_zero_px": 390.0,
    "x_six_px": 1177.0,
    "y_zero_px": 2651.0,
    "y_700_px": 2051.0,
}
FIG11C_X_MIN_PX = 390
FIG11C_X_MAX_PX = 1177
FIG11C_Y_TOP_PX = 2048
FIG11C_Y_BOTTOM_PX = 2656
FIG11C_LEGEND_EXCLUSION = (630, 2410, 935, 2550)  # x0,y0,x1,y1, page pixels
FIG11C_TIME_SAMPLE_STEP_S = 0.1
FIG11C_COUNT_READ_ALLOWANCE = 5
FIG11C_TIME_READ_ALLOWANCE_S = 0.01


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def render_page(page: int) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix=f"dash8-target-p{page}-") as temp_dir:
        prefix = Path(temp_dir) / f"page-{page}"
        subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(page),
                "-l",
                str(page),
                "-r",
                str(DPI),
                "-png",
                "-singlefile",
                str(PDF),
                str(prefix),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        image = np.asarray(Image.open(prefix.with_suffix(".png")).convert("RGB"))
    expected = (3249, 2481, 3)
    if image.shape != expected:
        raise ValueError(f"Page {page} render shape {image.shape}, expected {expected}")
    return image


def component_labels(mask: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Return 8-connected component labels and pixel sizes using a simple BFS."""
    height, width = mask.shape
    flat_mask = mask.ravel()
    unseen = np.zeros(flat_mask.size, dtype=bool)
    unseen[np.flatnonzero(flat_mask)] = True
    labels = np.zeros(flat_mask.size, dtype=np.int32)
    sizes: list[int] = []
    starts = np.flatnonzero(unseen)
    next_label = 0
    for start_value in starts:
        start = int(start_value)
        if not unseen[start]:
            continue
        next_label += 1
        unseen[start] = False
        labels[start] = next_label
        stack = [start]
        size = 0
        while stack:
            index = stack.pop()
            size += 1
            row, col = divmod(index, width)
            row_min = max(0, row - 1)
            row_max = min(height - 1, row + 1)
            col_min = max(0, col - 1)
            col_max = min(width - 1, col + 1)
            for neighbor_row in range(row_min, row_max + 1):
                offset = neighbor_row * width
                for neighbor_col in range(col_min, col_max + 1):
                    neighbor = offset + neighbor_col
                    if unseen[neighbor]:
                        unseen[neighbor] = False
                        labels[neighbor] = next_label
                        stack.append(neighbor)
        sizes.append(size)
    return labels.reshape(height, width), sizes


def teal_mask(rgb: np.ndarray, delta: int) -> np.ndarray:
    red = rgb[..., 0].astype(np.int16)
    green = rgb[..., 1].astype(np.int16)
    blue = rgb[..., 2].astype(np.int16)
    return (
        (green - red >= delta)
        & (blue - red >= delta)
        & (green > 115)
        & (blue > 115)
        & (np.abs(green - blue) <= 50)
    )


def fig5_targets(page: np.ndarray) -> tuple[list[dict[str, object]], dict[str, object]]:
    metrics: list[dict[str, object]] = []
    crops: dict[str, object] = {}
    for time_s, box in FIG5_REGIONS.items():
        x0, y0, x1, y1 = box
        crop = page[y0:y1, x0:x1]
        crops[time_s] = {"box": box, "rgb": crop}
        for delta in TEAL_DELTA_THRESHOLDS:
            mask = teal_mask(crop, delta)
            labels, sizes = component_labels(mask)
            ys, xs = np.where(mask)
            record: dict[str, object] = {
                "time_s": float(time_s),
                "pdf_page": FIG5_PAGE,
                "journal_page": 1520,
                "figure_panel": "Fig. 5(b), Dash-8",
                "evidence_class": "digitized_image_only_proxy",
                "rgb_delta_threshold": delta,
                "teal_pixel_count": int(mask.sum()),
                "roi_pixel_count": int(mask.size),
                "bbox_page_pixels": [
                    int(xs.min() + x0),
                    int(ys.min() + y0),
                    int(xs.max() + x0),
                    int(ys.max() + y0),
                ]
                if mask.any()
                else None,
                "bbox_width_pixels": int(xs.max() - xs.min() + 1) if mask.any() else 0,
                "bbox_height_pixels": int(ys.max() - ys.min() + 1) if mask.any() else 0,
                "connected_components_8_neighbour": len(sizes),
                "component_area_cutoffs_px": {
                    str(cutoff): {
                        "count": int(sum(size >= cutoff for size in sizes)),
                        "included_pixel_area": int(sum(size for size in sizes if size >= cutoff)),
                    }
                    for cutoff in COMPONENT_AREA_CUTOFFS_PX
                },
                "largest_component_area_px": int(max(sizes, default=0)),
                "limits": [
                    "2D raster connected components only; not 3D liquid structures or parcels",
                    "component counts vary with RGB threshold and display-pixel area cutoff",
                    "airframe is excluded by the cyan chromatic class; overlapping or occluded water cannot be recovered",
                    "panel has no physical axes or camera calibration; no physical length or volume is inferred",
                    "4.8 s cloud is visibly clipped by the paper's displayed domain/view",
                ],
            }
            metrics.append(record)
            if delta == 24:
                crops[time_s]["mask"] = mask
                crops[time_s]["labels"] = labels
                crops[time_s]["sizes"] = sizes
    return metrics, crops


def trace_centers(page: np.ndarray, series: str) -> tuple[np.ndarray, np.ndarray]:
    red, green, blue = page.transpose(2, 0, 1)
    if series == "alpha_0p001_to_1":
        mask = (red > 150) & (red > green * 1.65) & (red > blue * 1.4)
    elif series == "alpha_0p9_to_1":
        mask = (blue > 130) & (blue > red * 1.6) & (blue > green * 1.35)
    else:
        raise ValueError(series)
    x0, y0, x1, y1 = FIG11C_LEGEND_EXCLUSION
    mask[y0:y1, x0:x1] = False
    mask[:FIG11C_Y_TOP_PX, :] = False
    mask[FIG11C_Y_BOTTOM_PX + 1 :, :] = False
    mask[:, :FIG11C_X_MIN_PX] = False
    mask[:, FIG11C_X_MAX_PX + 1 :] = False
    cols: list[int] = []
    centers: list[float] = []
    for x in range(FIG11C_X_MIN_PX, FIG11C_X_MAX_PX + 1):
        rows = np.flatnonzero(mask[FIG11C_Y_TOP_PX : FIG11C_Y_BOTTOM_PX + 1, x])
        if rows.size >= 2:
            cols.append(x)
            centers.append(float(np.median(rows + FIG11C_Y_TOP_PX)))
    if not cols:
        raise ValueError(f"No Fig. 11(c) {series} trace pixels found")
    return np.asarray(cols, dtype=float), np.asarray(centers, dtype=float)


def page_px_to_time(x_px: np.ndarray | float) -> np.ndarray | float:
    a = FIG11C_AXES
    return 6.0 * (np.asarray(x_px) - a["x_zero_px"]) / (a["x_six_px"] - a["x_zero_px"])


def page_px_to_count(y_px: np.ndarray | float) -> np.ndarray | float:
    a = FIG11C_AXES
    return 700.0 * (a["y_zero_px"] - np.asarray(y_px)) / (a["y_zero_px"] - a["y_700_px"])


def count_fields(raw_count: float) -> dict[str, object]:
    lower = min(700.0, max(0.0, raw_count - FIG11C_COUNT_READ_ALLOWANCE))
    upper = min(700.0, max(0.0, raw_count + FIG11C_COUNT_READ_ALLOWANCE))
    near_zero = raw_count - FIG11C_COUNT_READ_ALLOWANCE <= 0.0
    return {
        # Preserve the measured pixel ordinate separately. A negative raw read
        # near the horizontal zero axis is not a negative structure count. The
        # displayed target interval remains within the plotted physical range.
        "count": "" if near_zero else min(700, max(0, int(math.floor(raw_count + 0.5)))),
        "raw_count": f"{raw_count:.3f}",
        "count_target_min": f"{lower:.3f}",
        "count_target_max": f"{upper:.3f}",
        "count_read_status": "near_zero_unresolved_within_read_allowance"
        if near_zero
        else "resolved_positive_count_read",
    }


def nearest_trace_sample(
    xs: np.ndarray,
    ys: np.ndarray,
    time_s: float,
) -> tuple[float, float] | None:
    a = FIG11C_AXES
    if not 0.0 <= time_s <= 6.0:
        return None
    x = a["x_zero_px"] + (a["x_six_px"] - a["x_zero_px"]) * time_s / 6.0
    nearest = int(np.argmin(np.abs(xs - x)))
    if abs(xs[nearest] - x) > (a["x_six_px"] - a["x_zero_px"]) * FIG11C_TIME_READ_ALLOWANCE_S / 6.0:
        return None
    actual_time = float(page_px_to_time(xs[nearest]))
    count = float(page_px_to_count(ys[nearest]))
    return actual_time, count


def fig11c_targets(
    page: np.ndarray,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    series_names = ("alpha_0p001_to_1", "alpha_0p9_to_1")
    native_rows: list[dict[str, object]] = []
    sampled_rows: list[dict[str, object]] = []
    plot_data: dict[str, object] = {"crop": page[1990:2690, 340:1230]}
    times = np.round(np.arange(0.1, 6.0 + 1e-9, FIG11C_TIME_SAMPLE_STEP_S), 1)
    for series in series_names:
        xs, ys = trace_centers(page, series)
        counts = np.asarray(page_px_to_count(ys), dtype=float)
        tvals = np.asarray(page_px_to_time(xs), dtype=float)
        plot_data[series] = {"x_px": xs, "y_px": ys, "t": tvals, "counts": counts}
        for x_px, y_px, time_value, count in zip(xs, ys, tvals, counts, strict=True):
            number_fields = count_fields(float(count))
            native_rows.append(
                {
                    "time_s": f"{time_value:.6f}",
                    **number_fields,
                    "alpha_threshold": "0.001 <= alpha_L <= 1"
                    if series == "alpha_0p001_to_1"
                    else "0.9 <= alpha_L <= 1",
                    "read_bound_time_s": FIG11C_TIME_READ_ALLOWANCE_S,
                    "read_bound_count": FIG11C_COUNT_READ_ALLOWANCE,
                    "source_figure": "11c",
                    "panel": "c",
                    "aircraft": "Dash-8",
                    "pdf_page": FIG11_PAGE,
                    "journal_page": 1524,
                    "page_x_px": int(x_px),
                    "page_y_px": f"{y_px:.2f}",
                    "method": "300 dpi raster RGB trace mask; per-column pixel median; fixed axis endpoints; no smoothing",
                    "source_pdf_sha256": sha256(PDF),
                }
            )
        for nominal_time in times:
            value = nearest_trace_sample(xs, ys, float(nominal_time))
            if value is None:
                actual_time = raw_count = None
                number_fields = {
                    "count": "",
                    "raw_count": "",
                    "count_target_min": "",
                    "count_target_max": "",
                    "count_read_status": "no_visible_trace_read",
                }
                status = "not_digitized_no_visible_trace_within_time_read_bound"
            else:
                actual_time, raw_count = value
                number_fields = count_fields(raw_count)
                status = "nearest_visible_native_pixel_column; no interpolation"
            sampled_rows.append(
                {
                    "time_s": "" if actual_time is None else f"{actual_time:.6f}",
                    **number_fields,
                    "alpha_threshold": "0.001 <= alpha_L <= 1"
                    if series == "alpha_0p001_to_1"
                    else "0.9 <= alpha_L <= 1",
                    "read_bound_time_s": FIG11C_TIME_READ_ALLOWANCE_S,
                    "read_bound_count": FIG11C_COUNT_READ_ALLOWANCE,
                    "source_figure": "11c",
                    "panel": "c",
                    "aircraft": "Dash-8",
                    "pdf_page": FIG11_PAGE,
                    "journal_page": 1524,
                    "nominal_time_s": f"{nominal_time:.1f}",
                    "nearest_read_offset_s": ""
                    if actual_time is None
                    else f"{actual_time - nominal_time:+.6f}",
                    "status": status,
                    "method": "nearest native raster-column read within +/-0.01 s; no interpolation or extrapolation",
                    "source_pdf_sha256": sha256(PDF),
                }
            )
    return native_rows, sampled_rows, plot_data


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"No rows to write for {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_fig5_plot(
    crops: dict[str, object], metrics: list[dict[str, object]], output_dir: Path
) -> None:
    fig, axes = plt.subplots(3, 2, figsize=(12, 12), constrained_layout=True)
    for row, time_s in enumerate(("0.1", "1.0", "4.8")):
        item = crops[time_s]
        crop = item["rgb"]
        mask = item["mask"]
        labels = item["labels"]
        sizes = item["sizes"]
        axes[row, 0].imshow(crop)
        axes[row, 0].set_title(f"Paper Fig. 5(b), t = {time_s} s")
        axes[row, 1].imshow(crop)
        overlay = np.zeros((*mask.shape, 4), dtype=float)
        overlay[mask] = (0.1, 0.75, 0.78, 0.68)
        keep = np.zeros(mask.shape, dtype=bool)
        for label_id, size in enumerate(sizes, start=1):
            if size >= 16:
                keep |= labels == label_id
        overlay[keep] = (1.0, 0.25, 0.05, 0.78)
        axes[row, 1].imshow(overlay)
        row_records = [m for m in metrics if m["time_s"] == float(time_s)]
        base = next(m for m in row_records if m["rgb_delta_threshold"] == 24)
        axes[row, 1].set_title(
            "Cyan-class proxy; orange marks components ≥16 px\n"
            f"dRGB≥24; pixels={base['teal_pixel_count']}; "
            f"8-connected comps≥16 px={base['component_area_cutoffs_px']['16']['count']}"
        )
        for ax in axes[row]:
            ax.set_axis_off()
    fig.suptitle(
        "Dash-8 paper image proxies only — 300 dpi crop, PDF p. 6 / journal p. 1520",
        fontsize=14,
    )
    fig.savefig(output_dir / "fig5_projection_proxy.png", dpi=160)
    plt.close(fig)


def write_fig11c_plot(plot_data: dict[str, object], output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 6), constrained_layout=True)
    styles = {
        "alpha_0p001_to_1": ("#dc3028", "0.001 ≤ αL ≤ 1, cloud structures"),
        "alpha_0p9_to_1": ("#1245d8", "0.9 ≤ αL ≤ 1, core structures"),
    }
    for name, (color, label_text) in styles.items():
        item = plot_data[name]
        ax.fill_between(
            item["t"],
            item["counts"] - FIG11C_COUNT_READ_ALLOWANCE,
            item["counts"] + FIG11C_COUNT_READ_ALLOWANCE,
            color=color,
            alpha=0.14,
            linewidth=0,
        )
        ax.plot(item["t"], item["counts"], color=color, linewidth=1.15, label=label_text)
    ax.set_xlim(0, 6)
    ax.set_ylim(-10, 700)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("Number of identified liquid structures")
    ax.set_title("Calbrix Fig. 11(c) — Dash-8 trace read; ±5-count raster allowance")
    ax.grid(alpha=0.18)
    ax.legend(loc="upper right", framealpha=0.88)
    fig.savefig(output_dir / "fig11c_dash8_structure_counts.png", dpi=180)
    plt.close(fig)


def write_fig11d_csv(output_dir: Path) -> None:
    rows = [
        ("0.04–0.1", "v_x", 0.07),
        ("0.04–0.1", "v_y", 25.95),
        ("0.04–0.1", "v_z", 1.07),
        ("0.1–1", "v_x", -0.02),
        ("0.1–1", "v_y", 41.57),
        ("0.1–1", "v_z", -2.26),
        ("1–10", "v_x", -0.16),
        ("1–10", "v_y", 18.7),
        ("1–10", "v_z", -5.13),
    ]
    records = []
    for size_range, component, value in rows:
        records.append(
            {
                "panel": "Fig. 11(d)",
                "aircraft": "Dash-8",
                "time_s": 1.0,
                "alpha_interval": "0.001 <= alpha_L <= 1",
                "equivalent_diameter_class_m": size_range,
                "velocity_component_label": component,
                "velocity_value_m_s": f"{value:g}",
                "evidence_class": "reported_numerical_result_directly_labelled_in_source_figure",
                "pdf_page": 10,
                "journal_page": 1524,
                "source": "Calbrix et al. (2023), Fig. 11(d), exact bar-top label transcription",
                "source_pdf_sha256": sha256(PDF),
                "uncertainty": "none printed; no error bar or class sample count shown",
            }
        )
    write_csv(output_dir / "fig11d_dash8_size_velocity_labels.csv", records)


def run_extraction(output_dir: Path) -> dict[str, object]:
    """Create all extraction artifacts in a new directory and return a run summary."""
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output_dir}")
    source_hash = sha256(PDF)
    if source_hash != EXPECTED_PDF_SHA256:
        raise ValueError(f"Unexpected source PDF SHA-256 {source_hash}")
    output_dir.mkdir(parents=True, exist_ok=False)
    fig5_page = render_page(FIG5_PAGE)
    fig11_page = render_page(FIG11_PAGE)
    fig5_metrics, fig5_crops = fig5_targets(fig5_page)
    write_csv(output_dir / "fig5_projection_proxy_metrics.csv", fig5_metrics)
    (output_dir / "fig5_projection_proxy_metrics.json").write_text(
        json.dumps(
            {
                "source_pdf": PDF.name,
                "source_pdf_sha256": source_hash,
                "source_locator": "PDF p. 6 / journal p. 1520, Fig. 5(b), Dash-8",
                "render_dpi": DPI,
                "render_tool": subprocess.run(
                    ["pdftoppm", "-v"], capture_output=True, text=True
                ).stderr.splitlines()[0],
                "roi_page_pixel_coordinates": {k: list(v) for k, v in FIG5_REGIONS.items()},
                "segmentation": {
                    "formula": "(G-R>=d) AND (B-R>=d) AND G>115 AND B>115 AND abs(G-B)<=50",
                    "d_values": list(TEAL_DELTA_THRESHOLDS),
                    "connectivity": "8-neighbour",
                    "component_area_cutoffs_px": list(COMPONENT_AREA_CUTOFFS_PX),
                    "physical_alpha_interpretation": "none; this is a rendered-color mask, not reconstructed alpha data",
                },
                "metrics": fig5_metrics,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_fig5_plot(fig5_crops, fig5_metrics, output_dir)

    native_rows, sampled_rows, plot_data = fig11c_targets(fig11_page)
    write_csv(output_dir / "fig11c_dash8_native_pixel_trace.csv", native_rows)
    write_csv(output_dir / "fig11c_dash8_0p1s_target_bins.csv", sampled_rows)
    Image.fromarray(fig11_page[2051:2656, 390:1178]).save(output_dir / "fig11c_source_panel_c.png")
    write_fig11c_plot(plot_data, output_dir)
    write_fig11d_csv(output_dir)
    metadata = {
        "source_pdf": PDF.name,
        "source_pdf_sha256": source_hash,
        "source_locator": "PDF p. 10 / journal p. 1524, Fig. 11(c,d); Dash-8, not CL-415 panel (a,b)",
        "render_dpi": DPI,
        "fig11c_axes_page_pixels": FIG11C_AXES,
        "fig11c_axis_calibration": {
            "time_s": "6*(x_px-x_zero_px)/(x_six_px-x_zero_px)",
            "structure_count": "700*(y_zero_px-y_px)/(y_zero_px-y_700_px)",
        },
        "fig11c_trace_masks": {
            "red": "R>150 AND R>1.65G AND R>1.4B",
            "blue": "B>130 AND B>1.6R AND B>1.35G",
            "legend_exclusion_page_px": list(FIG11C_LEGEND_EXCLUSION),
        },
        "digitization_allowances": {
            "count_plus_minus": FIG11C_COUNT_READ_ALLOWANCE,
            "time_plus_minus_s": FIG11C_TIME_READ_ALLOWANCE_S,
            "status": "heuristic raster-read allowances, not source uncertainty, confidence intervals, or author error bars",
        },
        "sampling": {
            "native_trace": "one pixel-column median where at least two qualifying color pixels are visible",
            "report_bins_s": FIG11C_TIME_SAMPLE_STEP_S,
            "selected_report_points": "nearest native pixel-column read within the +/-0.01 s time-read allowance; no interpolation or extrapolation",
            "target_count_interval": (
                "digitized count +/-5 clipped to the plotted 0..700 physical axis; time and count "
                "read allowances are retained as separate bounds"
            ),
            "source_solver_output_cadence": "not stated in paper",
        },
        "figure11d_values": "direct transcription of numeric bar labels; no error bars or class sample counts",
        "limits": [
            "the article's MATLAB 3D structure identification algorithm is not published",
            "counts are identified liquid structures, not parcels and not direct experimental measurements",
            "a different connected-component detector is not automatically equivalent",
        ],
    }
    (output_dir / "fig11_targets_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "source_pdf_sha256": source_hash,
        "fig5_records": len(fig5_metrics),
        "fig11c_native_pixel_samples": len(native_rows),
        "fig11c_0p1s_bins": len(sampled_rows),
        "outputs": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="new directory for extracted figure-read artifacts (must not already exist)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(run_extraction(args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
