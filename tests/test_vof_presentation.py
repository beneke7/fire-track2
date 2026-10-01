from __future__ import annotations

import numpy as np
import pytest

from scripts.render_vof_presentation import (
    _secondary_whitewater_samples,
    _wendland_c2_kernel,
)


def test_secondary_samples_are_seeded_and_preserve_alpha_inventory() -> None:
    alpha = np.asarray([0.0, 0.01, 0.10, 0.35, 0.55, 0.90, 0.99, 1.0])
    centers = np.arange(alpha.size * 3, dtype=np.float64).reshape(-1, 3) / 10.0
    cell_volumes = np.linspace(0.1, 0.8, alpha.size)
    alpha_before = alpha.copy()
    inventory_before = float(alpha @ cell_volumes)

    samples_a, record_a = _secondary_whitewater_samples(
        alpha, centers, seed=8, sample_count=3, cell_spacing_m=0.1
    )
    samples_b, record_b = _secondary_whitewater_samples(
        alpha, centers, seed=8, sample_count=3, cell_spacing_m=0.1
    )

    assert np.array_equal(samples_a, samples_b)
    assert record_a["selected_cell_indices_sha256"] == record_b["selected_cell_indices_sha256"]
    assert record_a["sample_positions_sha256"] == record_b["sample_positions_sha256"]
    assert np.array_equal(alpha, alpha_before)
    assert float(alpha @ cell_volumes) == inventory_before
    assert record_a["changes_alpha_or_mass"] is False
    assert record_a["secondary_sample_count"] == 3


def test_wendland_c2_kernel_has_unit_three_dimensional_integral() -> None:
    smoothing_length = 0.0625
    radius = np.linspace(0.0, 2.0 * smoothing_length, 20_001)
    kernel = _wendland_c2_kernel(radius, smoothing_length)
    integral = np.trapezoid(4.0 * np.pi * radius**2 * kernel, radius)

    assert integral == pytest.approx(1.0, rel=1e-7)
    assert kernel[0] == pytest.approx(21.0 / (16.0 * np.pi * smoothing_length**3))
    assert kernel[-1] == 0.0


def test_sample_generator_uses_replacement_only_when_needed_and_rejects_bad_bounds() -> None:
    alpha = np.asarray([0.0, 0.2, 0.6, 1.0])
    centers = np.asarray([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [0.2, 0.0, 0.0], [0.3, 0, 0]])

    samples, record = _secondary_whitewater_samples(
        alpha, centers, seed=11, sample_count=20, cell_spacing_m=0.1
    )

    assert samples.shape == (20, 3)
    assert record["candidate_mixed_alpha_cell_count"] == 2
    assert "with replacement" in record["selection"]
    with pytest.raises(ValueError, match="ordered within \\[0, 1\\]"):
        _secondary_whitewater_samples(
            alpha,
            centers,
            seed=11,
            sample_count=1,
            cell_spacing_m=0.1,
            alpha_min=0.9,
            alpha_max=0.1,
        )
