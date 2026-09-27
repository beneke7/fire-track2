#!/usr/bin/env python3
"""Compile the exact helpers against explicit and deliberately shifted halo calls."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import math
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(sys.argv[1]).resolve()
EVIDENCE = Path(sys.argv[2]).resolve()
TESTS = ROOT / "tests"
REFERENCE_PATH = TESTS / "test_dzf_lower_bound_helpers.py"
DRIVER_PATH = TESTS / "dzf_two_halo_driver.f90"
ONE_HALO_DRIVER_PATH = TESTS / "dzf_lower_bound_driver.f90"
SHIFTED_DZF = (9.9, 0.4, 1.1, 2.3, 3.7)

saved_argv = sys.argv[:]
sys.argv = [str(REFERENCE_PATH), str(ROOT)]
spec = importlib.util.spec_from_file_location("candidate6_one_halo_reference", REFERENCE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("could not load the independent one-halo reference helpers")
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference
spec.loader.exec_module(reference)
sys.argv = saved_argv


def rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="ascii") as stream:
        return list(csv.reader(stream, strict=True))


def compare_case(prefix: Path, spacing: tuple[float, ...], label: str) -> dict[str, float]:
    area_rows = rows(prefix.with_name(prefix.name + "_area.csv"))
    if len(area_rows) != 6 or any(len(row) != 3 for row in area_rows):
        raise AssertionError(f"{label}: geometric face-area output has an unexpected shape")
    summed_spacing = sum(spacing[1 : reference.NZ + 1])
    expected_areas = (
        reference.NY * reference.DL[1] * summed_spacing,
        reference.NY * reference.DL[1] * summed_spacing,
        reference.NX * reference.DL[0] * summed_spacing,
        reference.NX * reference.DL[0] * summed_spacing,
        reference.NX * reference.NY * reference.DL[0] * reference.DL[1],
        reference.NX * reference.NY * reference.DL[0] * reference.DL[1],
    )
    for face_index, (row, geometric_area) in enumerate(
        zip(area_rows, expected_areas, strict=True), start=1
    ):
        face, incoming_area, outgoing_area = (float(value) for value in row)
        expected_in = geometric_area if face_index % 2 == 1 else 0.0
        expected_out = 0.0 if face_index % 2 == 1 else geometric_area
        reference.assert_close(face, float(face_index), f"{label}: area face index")
        reference.assert_close(incoming_area, expected_in, f"{label}: face {face_index} inward area")
        reference.assert_close(outgoing_area, expected_out, f"{label}: face {face_index} outward area")

    incoming, outgoing = reference.expected_boundary(spacing)
    boundary_rows = rows(prefix.with_name(prefix.name + "_boundary.csv"))
    if len(boundary_rows) != 2:
        raise AssertionError(f"{label}: expected two boundary rows")
    for row_index, row in enumerate(boundary_rows):
        actual = [float(value) for value in row]
        expected = [
            float(row_index),
            *sum(([incoming[index], outgoing[index]] for index in range(6)), []),
        ]
        if len(actual) != len(expected):
            raise AssertionError(f"{label}: boundary field count changed")
        for column, (observed, target) in enumerate(zip(actual, expected, strict=True)):
            reference.assert_close(observed, target, f"{label}: boundary row {row_index} field {column}")

    mass_rows = rows(prefix.with_name(prefix.name + "_mass.csv"))
    if len(mass_rows) != 2 or any(len(row) != 20 for row in mass_rows):
        raise AssertionError(f"{label}: inventory output has an unexpected shape")
    first = [float(value) for value in mass_rows[0]]
    second = [float(value) for value in mass_rows[1]]
    expected_in = 1000.0 * sum(incoming)
    expected_out = 1000.0 * sum(outgoing)
    mass_checks = (
        (first[2], reference.inventory_mass(0.0, spacing), "initial inventory"),
        (second[2], reference.inventory_mass(0.03, spacing), "updated inventory"),
        (second[3], reference.inventory_mass(0.0, spacing), "stored initial inventory"),
        (second[4], expected_in, "cumulative input mass"),
        (second[5], expected_out, "cumulative output mass"),
        (
            second[6],
            expected_in - expected_out
            - (reference.inventory_mass(0.03, spacing) - reference.inventory_mass(0.0, spacing)),
            "mass residual",
        ),
        (second[7], sum(incoming) - sum(outgoing), "net boundary volume"),
    )
    for observed, target, name in mass_checks:
        reference.assert_close(observed, target, f"{label}: {name}")

    velocity_rows = rows(prefix.with_name(prefix.name + "_velocity.csv"))
    if len(velocity_rows) != 1 or len(velocity_rows[0]) != 22:
        raise AssertionError(f"{label}: velocity audit output has an unexpected shape")
    velocity_values = [float(value) for value in velocity_rows[0]]
    for column, (observed, target) in enumerate(
        zip(velocity_values, reference.expected_velocity(spacing), strict=True)
    ):
        reference.assert_close(observed, target, f"{label}: velocity field {column}")

    return {
        "xlow_geometric_area": float(area_rows[0][1]),
        "ylow_geometric_area": float(area_rows[2][1]),
        "initial_inventory_kg": first[2],
        "updated_inventory_kg": second[2],
        "ylow_inward_volume_m3": float(boundary_rows[0][5]),
        "max_abs_divergence_s_inv": velocity_values[14],
        "global_legacy_courant": velocity_values[5],
        "divergence_integral_m3_s": velocity_values[12],
    }


def hash_files(paths: list[Path], output: Path, *, relative_to: Path) -> None:
    lines = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(relative_to)}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_dzf_two_halo_helpers.py CANDIDATE6_DIR EVIDENCE_DIR")
    preexisting = {path.name for path in EVIDENCE.iterdir()} if EVIDENCE.exists() else set()
    if preexisting - {"command.txt", "metadata.txt", "test.log"}:
        raise SystemExit(f"evidence directory already contains generated artifacts: {EVIDENCE}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    patch_source = reference.added_source()
    reference.check_new_include_hunk_count()
    reference.check_patch_contract(patch_source)
    compiler = shutil.which("nvfortran") or shutil.which("gfortran")
    if compiler is None:
        raise SystemExit("no supported Fortran compiler found (nvfortran or gfortran)")

    generated = EVIDENCE / "candidate6_production_helpers.f90"
    driver = EVIDENCE / "dzf_two_halo_driver.f90"
    one_halo_driver = EVIDENCE / "dzf_one_halo_driver.f90"
    executable = EVIDENCE / "dzf_two_halo_driver"
    generated.write_text(reference.generated_module(patch_source), encoding="utf-8")
    shutil.copy2(DRIVER_PATH, driver)
    shutil.copy2(ONE_HALO_DRIVER_PATH, one_halo_driver)
    compiler_version = subprocess.run(
        [compiler, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (EVIDENCE / "compiler.txt").write_text(compiler_version.stdout, encoding="utf-8")
    if Path(compiler).name == "nvfortran":
        compile_command = [
            compiler, "-O0", "-g", "-Mbounds", "-Mextend", "-o", str(executable),
            str(generated), str(driver),
        ]
    else:
        compile_command = [
            compiler, "-std=f2008", "-O0", "-g", "-fcheck=all", "-fbacktrace",
            "-ffree-line-length-none", "-o", str(executable), str(generated), str(driver),
        ]
    (EVIDENCE / "compile-command.txt").write_text(
        shlex.join(compile_command) + "\n", encoding="utf-8"
    )
    compiled = subprocess.run(
        compile_command,
        cwd=EVIDENCE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (EVIDENCE / "compile.log").write_text(compiled.stdout, encoding="utf-8")
    if compiled.returncode:
        raise AssertionError(f"two-halo helper compile failed:\n{compiled.stdout}")

    prefixes: dict[str, Path] = {}
    for mode, stem in (
        ("explicit-slice", "two-halo-explicit-slice"),
        ("whole-array-negative", "two-halo-whole-array-negative"),
    ):
        prefix = EVIDENCE / stem
        result = subprocess.run(
            [str(executable), mode, str(prefix)],
            cwd=EVIDENCE,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        (EVIDENCE / f"{stem}.stdout").write_text(result.stdout, encoding="utf-8")
        if result.returncode:
            raise AssertionError(f"{mode} driver failed:\n{result.stdout}")
        prefixes[mode] = prefix

    correct = compare_case(prefixes["explicit-slice"], reference.DZF, "explicit physical slice")
    shifted = compare_case(prefixes["whole-array-negative"], SHIFTED_DZF, "shifted whole-array control")
    controls = (
        "initial_inventory_kg",
        "updated_inventory_kg",
        "ylow_inward_volume_m3",
        "max_abs_divergence_s_inv",
        "global_legacy_courant",
    )
    for name in controls:
        if math.isclose(correct[name], shifted[name], rel_tol=2.0e-12, abs_tol=2.0e-12):
            raise AssertionError(f"whole-array negative control did not shift {name}")

    (EVIDENCE / "comparison.txt").write_text(
        "Two-halo caller storage: dzf(-1:nz+2) = "
        "(9.9, 0.4, 1.1, 2.3, 3.7, 5.2, 8.8)\n"
        "Correct call operands: dzf(0:) for boundary flux, inventory and velocity audit.\n"
        "Negative control operands: whole dzf array; helper dummy 0 maps to caller -1.\n"
        "Both compiled paths matched independent geometric face-area, flux-volume, "
        "inventory, divergence and Courant expectations.\n"
        "The whole-array path mismatched the physical-spacing results for inventory, "
        "x/y-low face area, boundary flux volume, divergence maximum and Courant.\n"
        f"Physical slice: {correct}\nShifted negative: {shifted}\n",
        encoding="utf-8",
    )
    pinned_inputs = [
        ROOT / "source-boundary.patch",
        ROOT / "source-pin.txt",
        REFERENCE_PATH,
        Path(__file__).resolve(),
        ONE_HALO_DRIVER_PATH,
        DRIVER_PATH,
    ]
    hash_files(pinned_inputs, EVIDENCE / "inputs.sha256", relative_to=ROOT)
    print(f"PASS: two-halo physical slice matched independent face, inventory, divergence and Courant expectations")
    print(f"PASS: whole-array negative control produced the expected shifted-index mismatch: {shifted}")
    print(f"Evidence artifacts retained in {EVIDENCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
