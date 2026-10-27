"""Synthetic checks for the runtime alpha-source denominator floor."""

from __future__ import annotations

import math
import unittest
from pathlib import Path

DEFAULT_FLOOR = 1.0e-4
TRIAL_FLOOR = 1.0e-5


def resolve_floor(value: float | None) -> float:
    floor = DEFAULT_FLOOR if value is None else float(value)
    if not math.isfinite(floor) or floor <= 0.0:
        raise ValueError("alpha-source denominator floor must be finite and positive")
    return floor


def assemble_susp(gamma: float, alpha_source: float, floor: float) -> tuple[float, float]:
    """Return the solver's (Su, Sp) split for its positive/negative branches."""
    if gamma > 0.0:
        denominator = max(1.0 - alpha_source, floor)
        return gamma / denominator, -gamma / denominator
    if gamma < 0.0:
        denominator = max(alpha_source, floor)
        return 0.0, gamma / denominator
    return 0.0, 0.0


def floor_active(gamma: float, alpha_source: float, floor: float) -> bool:
    if gamma > 0.0:
        return 1.0 - alpha_source < floor
    if gamma < 0.0:
        return alpha_source < floor
    return False


class AlphaSourceFloorTests(unittest.TestCase):
    def test_missing_value_keeps_exact_v3_default(self) -> None:
        self.assertEqual(resolve_floor(None), 1e-4)
        self.assertEqual(resolve_floor(DEFAULT_FLOOR), 1e-4)

    def test_positive_and_negative_pure_phase_branches_are_finite(self) -> None:
        floor = resolve_floor(None)
        positive = assemble_susp(2.5, 1.0, floor)
        self.assertEqual(positive, (2.5 / floor, -2.5 / floor))
        self.assertTrue(floor_active(2.5, 1.0, floor))

        negative = assemble_susp(-3.0, 0.0, floor)
        self.assertEqual(negative, (0.0, -3.0 / floor))
        self.assertTrue(floor_active(-3.0, 0.0, floor))

    def test_explicit_trial_floor_is_shared_by_coefficients_and_diagnostic(self) -> None:
        floor = resolve_floor(TRIAL_FLOOR)
        self.assertEqual(floor, 1e-5)
        positive = assemble_susp(1.0, 1.0 - 0.5 * floor, floor)
        negative = assemble_susp(-1.0, 0.5 * floor, floor)
        self.assertEqual(positive, (1.0 / floor, -1.0 / floor))
        self.assertEqual(negative, (0.0, -1.0 / floor))
        self.assertTrue(floor_active(1.0, 1.0 - 0.5 * floor, floor))
        self.assertTrue(floor_active(-1.0, 0.5 * floor, floor))

    def test_interior_coefficients_are_unchanged(self) -> None:
        alpha = 0.37
        for floor in (DEFAULT_FLOOR, TRIAL_FLOOR):
            positive = assemble_susp(2.0, alpha, floor)
            negative = assemble_susp(-3.0, alpha, floor)
            self.assertEqual(positive, (2.0 / (1.0 - alpha), -2.0 / (1.0 - alpha)))
            self.assertEqual(negative, (0.0, -3.0 / alpha))
            self.assertFalse(floor_active(2.0, alpha, floor))
            self.assertFalse(floor_active(-3.0, alpha, floor))

    def test_invalid_floor_values_are_rejected(self) -> None:
        for value in (0.0, -1e-4, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_floor(value)

    def test_variant_routes_all_source_denominator_diagnostics_through_one_value(self) -> None:
        root = Path(__file__).resolve().parent / "source/target-files"
        paths = (
            "applications/solvers/multiphase/compressibleInterFoam/alphaSuSp.H",
            "applications/solvers/multiphase/compressibleInterFoam/i4fPhysicalAlphaFluxRelaxApply.H",
            "applications/solvers/multiphase/compressibleInterFoam/i4fAlphaMassBudgetAlphaObserve.H",
            "applications/solvers/multiphase/compressibleInterFoam/i4fAlphaMassBudgetEosObserve.H",
            "applications/solvers/multiphase/VoF/alphaEqn.H",
        )
        for relative in paths:
            text = (root / relative).read_text()
            self.assertIn("i4fAlphaSourceDenominatorFloor", text, relative)
            self.assertNotIn("1e-4", text, relative)
        main = (
            root / "applications/solvers/multiphase/compressibleInterFoam/compressibleInterFoam.C"
        ).read_text()
        self.assertIn('"i4fAlphaSourceDenominatorFloor"', main)
        self.assertIn("scalar(1e-4)", main)
        self.assertIn("i4fAlphaSourceDenominatorFloor < GREAT", main)


if __name__ == "__main__":
    unittest.main()
