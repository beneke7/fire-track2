#!/usr/bin/env python3
"""Recompute frozen-pressure map vector metrics from rank-local binary dumps."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "case"
PROBE = CASE / "i4f_frozen_pressure_probe"
N_RANKS = 10


def l2w(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sqrt(np.dot(weights, values * values)))


def weighted_stats(values: np.ndarray, weights: np.ndarray) -> dict[str, float]:
    return {
        "max_abs": float(np.max(np.abs(values))),
        "volume_weighted_l2": l2w(values, weights),
        "volume_weighted_rms": float(np.sqrt(np.dot(weights, values * values) / weights.sum())),
    }


def read_global_volumes() -> np.ndarray:
    data = (CASE / "constant/V").read_bytes()
    marker = data.index(b"internalField")
    match = re.search(rb"(?m)^(\d+)\s*\n\s*\(", data[marker:])
    if match is None:
        raise ValueError("could not locate binary V internalField")
    count = int(match.group(1))
    offset = marker + match.end()
    values = np.frombuffer(data, dtype="<f8", count=count, offset=offset)
    if len(values) != count or not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("invalid global cell volumes")
    return values


def read_cell_addressing(rank: int, expected_count: int) -> np.ndarray:
    data = (CASE / "processors10/constant/polyMesh/cellProcAddressing").read_bytes()
    marker = f"// processor{rank}".encode()
    start = data.index(marker) + len(marker)
    next_marker = data.find(b"// processor", start)
    segment = data[start:] if next_marker < 0 else data[start:next_marker]
    matches = list(re.finditer(rb"(?m)^(\d+)\s*\n\s*\(", segment))
    # Each decomposedBlockData processor record has a global count followed by
    # a nested FoamFile header, then the local count/list. The second count is
    # the local cell addressing array.
    if len(matches) < 2:
        raise ValueError(f"rank {rank}: could not locate local cell list")
    local = matches[1]
    count = int(local.group(1))
    if count != expected_count:
        raise ValueError(f"rank {rank}: address count {count} != {expected_count}")
    labels = np.frombuffer(segment, dtype="<i4", count=count, offset=local.end())
    if len(labels) != count:
        raise ValueError(f"rank {rank}: truncated cellProcAddressing")
    return labels.astype(np.int64, copy=False)


def read_rank_vector(rank: int, field_name: str, expected_count: int) -> np.ndarray:
    index_path = PROBE / f"rank{rank}.sweeps-index.csv"
    bin_path = PROBE / f"rank{rank}.sweeps.bin"
    with index_path.open(newline="") as stream:
        rows = {row["name"]: row for row in csv.DictReader(stream)}
    row = rows[field_name]
    count = int(row["count"])
    if count != expected_count or int(row["value_bytes"]) != 8:
        raise ValueError(f"rank {rank} {field_name}: unexpected layout {row}")
    return np.fromfile(
        bin_path,
        dtype="<f8",
        count=count,
        offset=int(row["byte_offset"]),
    )


def read_state_vector(rank: int, field_name: str, expected_count: int) -> np.ndarray:
    index_path = PROBE / f"rank{rank}.state-index.csv"
    bin_path = PROBE / f"rank{rank}.state.bin"
    with index_path.open(newline="") as stream:
        rows = {row["name"]: row for row in csv.DictReader(stream)}
    row = rows[field_name]
    count = int(row["count"])
    if count != expected_count or int(row["value_bytes"]) != 8:
        raise ValueError(f"rank {rank} state {field_name}: unexpected layout {row}")
    return np.fromfile(
        bin_path,
        dtype="<f8",
        count=count,
        offset=int(row["byte_offset"]),
    )


def main() -> None:
    volumes = read_global_volumes()
    ranks: list[tuple[np.ndarray, np.ndarray]] = []
    for rank in range(N_RANKS):
        with (PROBE / f"rank{rank}.sweeps-index.csv").open(newline="") as stream:
            first = next(csv.DictReader(stream))
        nlocal = int(first["count"])
        labels = read_cell_addressing(rank, nlocal)
        if labels.min() < 0 or labels.max() >= len(volumes):
            raise ValueError(f"rank {rank}: cell label outside global V")
        ranks.append((labels, volumes[labels]))
    all_labels = np.concatenate([item[0] for item in ranks])
    if len(all_labels) != len(volumes) or len(np.unique(all_labels)) != len(volumes):
        raise ValueError("cellProcAddressing is not a one-to-one partition of global V")

    def collect(name: str) -> tuple[np.ndarray, np.ndarray]:
        vals = [read_rank_vector(rank, name, len(ranks[rank][0])) for rank in range(N_RANKS)]
        weights = [ranks[rank][1] for rank in range(N_RANKS)]
        return np.concatenate(vals), np.concatenate(weights)

    baseline: list[np.ndarray] = []
    w_all: np.ndarray | None = None
    for sweep in range(1, 9):
        v, weights = collect(f"baseline_iteration_amp0_sign0_sweep{sweep}_p_rgh")
        baseline.append(v)
        w_all = weights
    assert w_all is not None

    records: list[dict[str, object]] = []
    first_input, weights = collect("baseline_iteration_amp0_sign0_sweep1_input_p_rgh")
    records.append({"map": "baseline", "step": 1, "difference": weighted_stats(baseline[0] - first_input, weights)})
    for i in range(1, len(baseline)):
        records.append({
            "map": "baseline",
            "step": i + 1,
            "difference_from_previous_output": weighted_stats(baseline[i] - baseline[i - 1], w_all),
        })

    def collect_state(name: str) -> tuple[np.ndarray, np.ndarray]:
        vals = [read_state_vector(rank, name, len(ranks[rank][0])) for rank in range(N_RANKS)]
        weights = [ranks[rank][1] for rank in range(N_RANKS)]
        return np.concatenate(vals), np.concatenate(weights)

    response = {}
    for amp in (1, 10):
        plus, weights = collect(f"one_map_response_amp{amp}_sign1_sweep1_p_rgh")
        minus, _ = collect(f"one_map_response_amp{amp}_sign-1_sweep1_p_rgh")
        centered = (plus - minus) / (2 * amp)
        v, _ = collect_state("v_normalized_max1Pa")
        numerator = l2w(centered, weights)
        vnorm = l2w(v, weights)
        response[str(amp)] = {
            "gain_recomputed": numerator / vnorm,
            "alignment_recomputed": float(np.dot(weights * centered, v) / (numerator * vnorm)),
            "projection_recomputed": float(np.dot(weights * centered, v) / (vnorm * vnorm)),
            "centered_vector_weighted_rms_per_Pa": float(np.sqrt(np.dot(weights, centered**2) / weights.sum())),
        }
    c1, _ = collect("one_map_response_amp1_sign1_sweep1_p_rgh")
    c1m, _ = collect("one_map_response_amp1_sign-1_sweep1_p_rgh")
    c10, _ = collect("one_map_response_amp10_sign1_sweep1_p_rgh")
    c10m, _ = collect("one_map_response_amp10_sign-1_sweep1_p_rgh")
    centered1 = (c1 - c1m) / 2
    centered10 = (c10 - c10m) / 20
    response_shape_delta = l2w(centered1 - centered10, weights) / l2w(centered1, weights)

    result = {
        "source": {
            "bundle": ROOT.as_posix(),
            "cell_volume_file": "case/constant/V",
            "cell_addressing": "case/processors10/constant/polyMesh/cellProcAddressing",
            "rank_sweep_indices": [f"case/i4f_frozen_pressure_probe/rank{i}.sweeps-index.csv" for i in range(N_RANKS)],
            "rank_sweep_binary": [f"case/i4f_frozen_pressure_probe/rank{i}.sweeps.bin" for i in range(N_RANKS)],
            "global_cells": int(len(volumes)),
            "sum_cell_volumes_m3": float(volumes.sum()),
        },
        "baseline_sweeps": records,
        "centered_response": response,
        "relative_centered_response_1Pa_vs_10Pa_weighted_L2": response_shape_delta,
        "interpretation_limit": "one pressure-only direction at one frozen state; not global operator stability or a physical cause test",
    }
    out = ROOT / "analysis/tight-map-vector-summary.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
