from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import analyze_native_turbulence as turbulence  # noqa: E402


def foam_scalar_bytes(
    name: str,
    values: list[float],
    *,
    format_: str = "ascii",
    location: str = "1.000000",
    dimensions: str | None = None,
) -> bytes:
    dimensions = dimensions or turbulence.FIELD_DIMENSIONS[name]
    header = (
        "FoamFile\n{\n"
        "    version 2.0;\n"
        f"    format {format_};\n"
        + ('    arch "LSB;label=32;scalar=64";\n' if format_ == "binary" else "")
        + "    class volScalarField;\n"
        + f'    location "{location}";\n'
        + f"    object {name};\n"
        + "}\n"
        + f"dimensions [{dimensions}];\n\n"
        + f"internalField nonuniform List<scalar>\n{len(values)}\n("
    ).encode("ascii")
    if format_ == "binary":
        return header + np.asarray(values, dtype="<f8").tobytes() + b");\n"
    body = "\n".join(str(value) for value in values)
    return header + f"\n{body}\n);\n".encode("ascii")


class NativeScalarFieldReaderTests(unittest.TestCase):
    def test_reads_ascii_binary_and_uniform_without_reordering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for format_ in ("ascii", "binary"):
                path = root / f"k-{format_}"
                path.write_bytes(foam_scalar_bytes("k", [0.5, -2.0, 4.25], format_=format_))
                values = turbulence.read_foam_scalar_internal(
                    path,
                    expected_count=3,
                    expected_object="k",
                    expected_location="1.0",
                    expected_dimensions=turbulence.FIELD_DIMENSIONS["k"],
                )
                np.testing.assert_array_equal(values, np.array([0.5, -2.0, 4.25]))

            uniform = root / "uniform"
            uniform.write_text(
                "FoamFile { version 2.0; format ascii; class volScalarField; "
                'location "1.0"; object nut; }\n'
                "dimensions [0 2 -1 0 0 0 0];\ninternalField uniform -0.25;\n",
                encoding="ascii",
            )
            np.testing.assert_array_equal(
                turbulence.read_foam_scalar_internal(
                    uniform,
                    expected_count=4,
                    expected_object="nut",
                    expected_location="1.000000",
                    expected_dimensions=turbulence.FIELD_DIMENSIONS["nut"],
                ),
                np.full(4, -0.25),
            )

    def test_rejects_wrong_count_time_object_and_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "epsilon"
            path.write_bytes(foam_scalar_bytes("epsilon", [1.0, 2.0]))
            args = {
                "expected_object": "epsilon",
                "expected_location": "1.0",
                "expected_dimensions": turbulence.FIELD_DIMENSIONS["epsilon"],
            }
            with self.assertRaisesRegex(ValueError, "has 2 values; expected 3"):
                turbulence.read_foam_scalar_internal(path, expected_count=3, **args)
            with self.assertRaisesRegex(ValueError, "does not match '0.5'"):
                turbulence.read_foam_scalar_internal(
                    path, expected_count=2, **{**args, "expected_location": "0.5"}
                )
            with self.assertRaisesRegex(ValueError, "object name"):
                turbulence.read_foam_scalar_internal(
                    path, expected_count=2, **{**args, "expected_object": "k"}
                )
            with self.assertRaisesRegex(ValueError, "dimensions"):
                turbulence.read_foam_scalar_internal(
                    path, expected_count=2, **{**args, "expected_dimensions": "0 1 -1 0 0 0 0"}
                )

    def test_rank_metadata_rejects_rank_count_time_and_source_disagreement(self) -> None:
        metadata = {
            "rank": 1,
            "rank_count": 2,
            "local_cell_count": 3,
            "time_name": "1.000000",
            "time_value_s": 1.0,
            "source_patch": "opening",
            "parallel_global_id_source": "constant/polyMesh/cellProcAddressing",
            "label_bytes_input": 4,
            "scalar_bytes_input": 8,
            "export_integer_bytes": 8,
            "export_float_bytes": 8,
            "export_byte_order": "little-endian",
        }
        expected = {
            "expected_rank": 1,
            "expected_rank_count": 2,
            "expected_time_name": "1.000000",
            "expected_time_s": 1.0,
            "expected_source_patch": "opening",
        }
        self.assertEqual(turbulence._validate_rank_metadata(metadata, **expected), 3)
        for changes, message in (
            ({"rank": 0}, "rank-count mismatch"),
            ({"rank_count": 3}, "rank-count mismatch"),
            ({"time_name": "0.500000"}, "time mismatch"),
            ({"source_patch": "other"}, "source-patch mismatch"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                turbulence._validate_rank_metadata(metadata | changes, **expected)

    def test_aligns_rank_local_field_values_by_exported_global_ids(self) -> None:
        ids = [np.array([2, 0]), np.array([1])]
        fields = {
            "k": [np.array([20.0, 10.0]), np.array([15.0])],
            "epsilon": [np.array([200.0, 100.0]), np.array([150.0])],
        }
        aligned = turbulence.align_rank_fields(ids, fields, np.array([0, 1, 2]))
        np.testing.assert_array_equal(aligned["k"], [10.0, 15.0, 20.0])
        np.testing.assert_array_equal(aligned["epsilon"], [100.0, 150.0, 200.0])

    def test_alignment_rejects_duplicate_ids_wrong_global_inventory_and_count(self) -> None:
        field = {"k": [np.array([1.0, 2.0]), np.array([3.0])]}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            turbulence.align_rank_fields(
                [np.array([0, 1]), np.array([1])], field, np.array([0, 1, 2])
            )
        with self.assertRaisesRegex(ValueError, "do not match"):
            turbulence.align_rank_fields(
                [np.array([0, 2]), np.array([1])], field, np.array([0, 1, 3])
            )
        with self.assertRaisesRegex(ValueError, "do not match local cell-ID counts"):
            turbulence.align_rank_fields(
                [np.array([0, 2]), np.array([1])],
                {"k": [np.array([1.0]), np.array([3.0])]},
                np.array([0, 1, 2]),
            )

    def test_nonuniform_volume_weights_and_negative_fields_are_preserved(self) -> None:
        alpha = np.array([0.2, 0.8, 0.0])
        volume = np.array([1.0, 3.0, 2.0])
        original_alpha = alpha.copy()
        snapshot = {
            "alpha_water": alpha,
            "cell_volumes_m3": volume,
            "cell_global_ids": np.array([0, 1, 2]),
            "cell_centres_xyz_m": np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]),
        }
        values = {
            "k": np.array([-2.0, 4.0, 6.0]),
            "epsilon": np.array([1.0, 2.0, 3.0]),
            "nut": np.array([0.01, 0.02, 0.03]),
        }
        report = turbulence.summarize_turbulence(
            snapshot,
            values,
            {"x": (-1.0, 1.5), "y": (-1.0, 1.0), "z": (-1.0, 1.0)},
        )
        self.assertEqual(report["regions"]["whole_domain"]["cell_count"], 3)
        self.assertEqual(report["regions"]["source_refinement_box_cell_centres"]["cell_count"], 2)
        all_k = report["regions"]["whole_domain"]["phase_partition_masks"]["all_cells"][
            "turbulence_fields"
        ]["k"]
        water = all_k["phase_weights"]["water_volume_weighted"]
        air = all_k["phase_weights"]["air_volume_weighted"]
        self.assertAlmostEqual(water["weighted_mean"], 9.2 / 2.6)
        self.assertAlmostEqual(air["weighted_mean"], 12.8 / 3.4)
        self.assertEqual(all_k["negative_value_count"], 1)
        self.assertEqual(all_k["raw_finite_min_location"]["cell_global_id"], 0)
        self.assertEqual(all_k["raw_finite_min_location"]["alpha_water_raw"], 0.2)
        self.assertEqual(all_k["raw_finite_max_location"]["cell_global_id"], 2)
        self.assertEqual(water["minimum_on_positive_weight_support"]["value"], -2.0)
        self.assertEqual(water["minimum_on_positive_weight_support"]["cell_global_id"], 0)
        self.assertEqual(all_k["raw_values_clipped"], False)
        np.testing.assert_array_equal(alpha, original_alpha)

    def test_nonfinite_saved_values_are_reported_and_not_silently_dropped(self) -> None:
        snapshot = {
            "alpha_water": np.array([0.5, 0.5]),
            "cell_volumes_m3": np.array([1.0, 1.0]),
            "cell_global_ids": np.array([0, 1]),
            "cell_centres_xyz_m": np.zeros((2, 3)),
        }
        report = turbulence.summarize_turbulence(
            snapshot,
            {
                "k": np.array([1.0, np.nan]),
                "epsilon": np.array([2.0, 3.0]),
                "nut": np.array([0.1, 0.2]),
            },
            {"x": (-1.0, 1.0), "y": (-1.0, 1.0), "z": (-1.0, 1.0)},
        )
        record = report["regions"]["whole_domain"]["phase_partition_masks"]["all_cells"][
            "turbulence_fields"
        ]["k"]
        self.assertEqual(record["nonfinite_value_count"], 1)
        self.assertEqual(
            record["phase_weights"]["water_volume_weighted"][
                "positive_weight_nonfinite_value_count"
            ],
            1,
        )


class NativeExportInputInventoryTests(unittest.TestCase):
    def _fixture(self, root: Path, *, settings: bool) -> tuple[Path, dict[str, str]]:
        case = root / "case"
        expected: dict[str, str] = {}
        files = [
            *(
                f"processor0/constant/polyMesh/{name}"
                for name in (
                    "boundary",
                    "cellProcAddressing",
                    "faces",
                    "neighbour",
                    "owner",
                    "points",
                )
            ),
            "processor0/1.000000/alpha.water",
            "processor0/1.000000/U",
        ]
        if settings:
            files.extend(("system/controlDict", "system/fvSchemes", "system/fvSolution"))
        for index, relative in enumerate(files):
            path = case / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = f"synthetic input {index}: {relative}\n".encode()
            path.write_bytes(payload)
            expected[relative] = hashlib.sha256(payload).hexdigest()
        return case, expected

    def test_accepts_legacy_mesh_and_flow_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case, inventory = self._fixture(Path(temp), settings=False)
            actual, settings = turbulence.verify_native_export_input_inventory(
                case, inventory, rank_count=1, time_name="1.000000"
            )
            self.assertEqual(actual, inventory)
            self.assertEqual(settings, ())

    def test_accepts_complete_new_system_dictionary_inventory_and_verifies_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case, inventory = self._fixture(Path(temp), settings=True)
            actual, settings = turbulence.verify_native_export_input_inventory(
                case, inventory, rank_count=1, time_name="1.000000"
            )
            self.assertEqual(actual, inventory)
            self.assertEqual(
                settings,
                ("system/controlDict", "system/fvSchemes", "system/fvSolution"),
            )

    def test_rejects_partial_known_system_dictionary_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case, inventory = self._fixture(Path(temp), settings=True)
            inventory.pop("system/fvSolution")
            with self.assertRaisesRegex(ValueError, "partial known system-dictionary"):
                turbulence.verify_native_export_input_inventory(
                    case, inventory, rank_count=1, time_name="1.000000"
                )

    def test_rejects_arbitrary_extra_or_missing_rank_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case, inventory = self._fixture(Path(temp), settings=False)
            inventory["system/unreviewedDictionary"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "unsupported files"):
                turbulence.verify_native_export_input_inventory(
                    case, inventory, rank_count=1, time_name="1.000000"
                )

            _, inventory = self._fixture(Path(temp) / "second", settings=False)
            inventory.pop("processor0/constant/polyMesh/owner")
            with self.assertRaisesRegex(ValueError, "does not cover every rank"):
                turbulence.verify_native_export_input_inventory(
                    Path(temp) / "second/case", inventory, rank_count=1, time_name="1.000000"
                )

    def test_rejects_tampered_known_system_dictionary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case, inventory = self._fixture(Path(temp), settings=True)
            (case / "system/fvSchemes").write_text("changed after native export\n")
            with self.assertRaisesRegex(ValueError, "case input changed since native export"):
                turbulence.verify_native_export_input_inventory(
                    case, inventory, rank_count=1, time_name="1.000000"
                )


if __name__ == "__main__":
    unittest.main()
