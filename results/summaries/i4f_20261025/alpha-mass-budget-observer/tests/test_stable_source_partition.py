"""Synthetic checks for finite Su/Sp source attribution at phase endpoints."""

from __future__ import annotations

import math
import unittest

ALPHA_FLOOR = 1e-4


def phase_source_coefficients(gamma: float, alpha_source: float) -> tuple[float, float]:
    """Reproduce the configured alphaSuSp denominator-floor branches."""
    if gamma > 0.0:
        denominator = max(1.0 - alpha_source, ALPHA_FLOOR)
        return gamma / denominator, -gamma / denominator
    if gamma < 0.0:
        denominator = max(alpha_source, ALPHA_FLOOR)
        return 0.0, gamma / denominator
    return 0.0, 0.0


def partition(
    gamma: float, su: float, sp: float, alpha_source: float, alpha_eval: float
) -> dict[str, float]:
    gamma_at_assembly = su + sp * alpha_source
    gamma_cut_at_assembly = gamma_at_assembly - gamma
    source_state_delta = sp * (alpha_eval - alpha_source)
    gamma_direct = su + sp * alpha_eval
    reconstruction = gamma + gamma_cut_at_assembly + source_state_delta
    return {
        "gamma_at_assembly": gamma_at_assembly,
        "gamma_cut_at_assembly": gamma_cut_at_assembly,
        "source_state_delta": source_state_delta,
        "gamma_direct": gamma_direct,
        "reconstruction": reconstruction,
        "split_error": gamma_direct - reconstruction,
    }


class StableSourcePartitionTests(unittest.TestCase):
    def assert_finite_identity(
        self, gamma: float, alpha_source: float, alpha_eval: float
    ) -> dict[str, float]:
        su, sp = phase_source_coefficients(gamma, alpha_source)
        values = partition(gamma, su, sp, alpha_source, alpha_eval)
        self.assertTrue(all(math.isfinite(value) for value in values.values()), values)
        self.assertAlmostEqual(
            values["gamma_direct"],
            values["reconstruction"],
            delta=1e-12 * max(1.0, abs(values["gamma_direct"])),
        )
        return values

    def test_pure_phase_source_floor_branches(self) -> None:
        positive = self.assert_finite_identity(4.0, 1.0, 1.0)
        self.assertEqual(positive["gamma_at_assembly"], 0.0)
        self.assertEqual(positive["gamma_cut_at_assembly"], -4.0)
        self.assertEqual(positive["source_state_delta"], 0.0)

        negative = self.assert_finite_identity(-3.0, 0.0, 0.0)
        self.assertEqual(negative["gamma_at_assembly"], 0.0)
        self.assertEqual(negative["gamma_cut_at_assembly"], 3.0)
        self.assertEqual(negative["source_state_delta"], 0.0)

    def test_subnormal_phase_fraction_does_not_create_a_ratio(self) -> None:
        alpha_source = math.nextafter(0.0, 1.0)
        values = self.assert_finite_identity(-8.3, alpha_source, 2.0e-320)
        self.assertTrue(math.isfinite(values["gamma_cut_at_assembly"]))
        self.assertTrue(math.isfinite(values["source_state_delta"]))

    def test_predictor_coefficients_are_not_replaced_by_corrector_coefficients(self) -> None:
        gamma_predictor = 0.7
        alpha_source = 0.2
        alpha_eval = 0.35
        su_predictor, sp_predictor = phase_source_coefficients(gamma_predictor, alpha_source)
        predictor = partition(gamma_predictor, su_predictor, sp_predictor, alpha_source, alpha_eval)

        gamma_corrector = -1.1
        su_corrector, sp_corrector = phase_source_coefficients(gamma_corrector, 0.8)
        wrong_current_coefficients = partition(
            gamma_predictor, su_corrector, sp_corrector, alpha_source, alpha_eval
        )

        self.assertAlmostEqual(predictor["gamma_direct"], predictor["reconstruction"], delta=1e-12)
        self.assertGreater(
            abs(predictor["gamma_direct"] - wrong_current_coefficients["reconstruction"]),
            1e-3,
        )

    def test_changed_state_is_separate_from_assembly_partition(self) -> None:
        gamma, alpha_source, alpha_eval = 2.0, 0.99995, 0.6
        values = self.assert_finite_identity(gamma, alpha_source, alpha_eval)
        su, sp = phase_source_coefficients(gamma, alpha_source)
        self.assertAlmostEqual(values["source_state_delta"], sp * (alpha_eval - alpha_source))
        self.assertAlmostEqual(
            values["gamma_at_assembly"] + values["source_state_delta"],
            values["gamma_direct"],
            delta=1e-12,
        )
        self.assertNotEqual(values["gamma_at_assembly"], values["gamma_direct"])


if __name__ == "__main__":
    unittest.main()
