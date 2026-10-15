from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import analyze_dash8_interface_growth as growth  # noqa: E402


def foam_vector_bytes(
    name: str,
    values: list[tuple[float, float, float]],
    *,
    format_: str = "ascii",
    location: str = "0.100000",
    dimensions: str = "0 1 -1 0 0 0 0",
) -> bytes:
    header = (
        "FoamFile\n{\n"
        "    version 2.0;\n"
        f"    format {format_};\n"
        + ('    arch "LSB;label=32;scalar=64";\n' if format_ == "binary" else "")
        + "    class volVectorField;\n"
        + f'    location "{location}";\n'
        + f"    object {name};\n"
        + "}\n"
        + f"dimensions [{dimensions}];\n\n"
        + f"internalField nonuniform List<vector>\n{len(values)}\n("
    ).encode("ascii")
    if format_ == "binary":
        return header + np.asarray(values, dtype="<f8").tobytes() + b");\n"
    body = "\n".join(f"({x} {y} {z})" for x, y, z in values)
    return header + f"\n{body}\n);\n".encode("ascii")


class Dash8VectorFieldReaderTests(unittest.TestCase):
    def test_reads_ascii_binary_and_uniform_vectors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            expected = np.array([[1.0, -2.0, 3.5], [0.0, 4.0, -1.0]])
            for format_ in ("ascii", "binary"):
                path = root / f"U-{format_}"
                path.write_bytes(
                    foam_vector_bytes("U", [tuple(row) for row in expected], format_=format_)
                )
                actual = growth.read_foam_vector_internal(
                    path,
                    expected_count=2,
                    expected_object="U",
                    expected_location="0.1",
                    expected_dimensions=growth.VECTOR_DIMENSIONS["U"],
                )
                np.testing.assert_array_equal(actual, expected)

            uniform = root / "uniform"
            uniform.write_text(
                "FoamFile { version 2.0; format ascii; class volVectorField; "
                'location "0.1"; object U; }\n'
                "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (2 0 -4);\n",
                encoding="ascii",
            )
            np.testing.assert_array_equal(
                growth.read_foam_vector_internal(
                    uniform,
                    expected_count=3,
                    expected_object="U",
                    expected_location="0.100000",
                    expected_dimensions=growth.VECTOR_DIMENSIONS["U"],
                ),
                np.tile([2.0, 0.0, -4.0], (3, 1)),
            )


class Dash8InterfaceDiagnosticsTests(unittest.TestCase):
    def test_aperture_origin_shift_preserves_solver_coordinates(self) -> None:
        centres = np.array([[-2.22, 0.0, 0.0], [2.22, 0.0, -1.0]])
        bounds = np.array(
            [[-2.25, -0.15, -0.04, -2.19, 0.15, 0.0], [2.19, -0.15, -1.04, 2.25, 0.15, -0.98]]
        )
        shifted_centres, shifted_bounds = growth.shift_x_to_opening_leading_edge(
            centres, bounds, 2.22
        )
        np.testing.assert_array_equal(centres[:, 0], [-2.22, 2.22])
        np.testing.assert_array_equal(shifted_centres[:, 0], [0.0, 4.44])
        np.testing.assert_allclose(
            shifted_bounds[:, (0, 3)], [[-0.03, 0.03], [4.41, 4.47]], atol=1e-12, rtol=0.0
        )

    def test_source_connected_core_uses_face_edges_and_threshold(self) -> None:
        alpha = np.array([1.0, 0.8, 0.2, 0.9, 0.9])
        edges = np.array([[0, 1], [1, 2], [3, 4]], dtype=np.int64)
        connected = growth.source_connected_core(
            alpha, edges, np.array([0], dtype=np.int64), threshold=0.5
        )
        np.testing.assert_array_equal(connected, [True, True, False, False, False])

    def test_native_neighbour_gradient_recovers_linear_shear(self) -> None:
        coordinates = np.array(
            [[x, y, z] for z in range(3) for y in range(3) for x in range(3)],
            dtype=np.float64,
        )
        edges = []

        def index(x: int, y: int, z: int) -> int:
            return z * 9 + y * 3 + x

        for z in range(3):
            for y in range(3):
                for x in range(3):
                    for neighbor in ((x + 1, y, z), (x, y + 1, z), (x, y, z + 1)):
                        nx, ny, nz = neighbor
                        if nx < 3 and ny < 3 and nz < 3:
                            edges.append([index(x, y, z), index(nx, ny, nz)])
        velocity = np.column_stack(
            (2.0 * coordinates[:, 2], coordinates[:, 0], np.zeros(len(coordinates)))
        )
        target = np.zeros(len(coordinates), dtype=bool)
        target[index(1, 1, 1)] = True
        shear, valid = growth.least_squares_shear(
            coordinates, velocity, np.asarray(edges, dtype=np.int64), target
        )
        self.assertTrue(valid[index(1, 1, 1)])
        self.assertAlmostEqual(shear[index(1, 1, 1)], np.sqrt(5.0), places=12)

    def test_section_thickness_uses_raw_alpha_volume_and_reports_gaps(self) -> None:
        x_edges = np.array([0.0, 0.15, 0.30, 0.45])
        centres = np.array([[x, 0.0, -0.15] for x in (0.075, 0.225, 0.375)])
        bounds = np.array(
            [[x - 0.075, -0.15, -0.1875, x + 0.075, 0.15, -0.1125] for x in (0.075, 0.225, 0.375)]
        )
        volumes = np.full(3, 0.15 * 0.30 * 0.075)
        alpha = np.array([0.5, 0.0, 0.5])
        record = growth.section_profile(
            centres,
            bounds,
            volumes,
            alpha,
            z_m=-0.15,
            x_edges_m=x_edges,
            dz_m=0.075,
            y_limits_m=(-0.15, 0.15),
        )
        self.assertEqual(record["dense_alpha05_bin_count"], 2)
        self.assertEqual(record["total_x_bin_count"], 3)
        self.assertAlmostEqual(
            record["water_equivalent_thickness_m"]["p50_across_dense_bins"], 0.15
        )
        self.assertEqual(record["spatial_displacement_spectrum"]["status"], "missing")
        self.assertIn("no gaps are filled", record["spatial_displacement_spectrum"]["reason"])

    def test_spatial_spectrum_requires_cell_resolution_and_two_cycles(self) -> None:
        spacing = 0.15
        x = np.arange(16, dtype=np.float64) * spacing
        displacement = np.sin(2.0 * np.pi * x / 0.8)
        valid = np.ones(len(x), dtype=bool)
        spectrum = growth.spectrum_from_profile(
            x,
            displacement,
            valid,
            sample_spacing_m=spacing,
            local_cell_dx_m=np.full(len(x), 0.03),
        )
        self.assertEqual(spectrum["status"], "computed")
        self.assertGreaterEqual(spectrum["resolution_floor_wavelength_m"], 4.0 * spacing)
        self.assertTrue(
            all(
                row["wavelength_m"] <= spectrum["segment_length_m"] / 2.0
                for row in spectrum["resolved_modes"]
            )
        )

        no_resolved_mode = growth.spectrum_from_profile(
            x,
            displacement,
            valid,
            sample_spacing_m=spacing,
            local_cell_dx_m=np.full(len(x), 0.4),
        )
        self.assertEqual(no_resolved_mode["status"], "missing")
        self.assertIn("both", no_resolved_mode["reason"])

    def test_mesh_transition_brackets_sparse_coarse_cell_centres(self) -> None:
        centres = np.array(
            [[x, y, -0.3] for x in (0.075, 0.675) for y in (-0.02, 0.0, 0.02)],
            dtype=np.float64,
        )
        bounds = []
        for x in (0.075, 0.675):
            dx = 0.1 if x < 0.5 else 0.6
            for y in (-0.02, 0.0, 0.02):
                bounds.append([x - dx / 2, y - 0.05, -0.35, x + dx / 2, y + 0.05, -0.25])
        profile = growth.mesh_transition_profile(
            centres,
            np.asarray(bounds, dtype=np.float64),
            z_m=-0.3,
            x_edges_m=np.arange(0.0, 1.2 + 0.075, 0.15),
            declared_refinement_region_x_analysis_m=(-0.28, 6.22),
        )
        self.assertEqual(len(profile["transition_flags"]), 1)
        transition = profile["transition_flags"][0]
        self.assertEqual(transition["x_bracket_m"], [0.075, 0.675])
        self.assertAlmostEqual(transition["x_midpoint_m"], 0.375)
        self.assertAlmostEqual(transition["bracket_width_m"], 0.6)
        self.assertEqual(profile["declared_refinement_region_x_analysis_m"], [-0.28, 6.22])

    def test_independent_fig6_fig7_reads_disfavor_corrected_alternative_area(self) -> None:
        result = growth.paper_scale_check()
        reader = result["readers"][1]
        compatible = reader["candidates"]["1p155_m"][
            "main_segment_same_x_normalized_vertical_rms_m"
        ]
        alternative = reader["candidates"]["0p566_from_alternative_area_0p32_m2_m"][
            "main_segment_same_x_normalized_vertical_rms_m"
        ]
        self.assertLess(compatible, 0.01)
        self.assertGreater(alternative, 0.15)


if __name__ == "__main__":
    unittest.main()
