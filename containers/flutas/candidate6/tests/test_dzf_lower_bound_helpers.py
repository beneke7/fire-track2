#!/usr/bin/env python3
"""Compile exact candidate6 helper bodies and check independent mesh integrals."""
from __future__ import annotations

import csv
import math
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


arguments = sys.argv[1:]
if not arguments or len(arguments) > 2:
    raise SystemExit("usage: test_dzf_lower_bound_helpers.py CANDIDATE6_DIR [EVIDENCE_DIR]")
ROOT = Path(arguments[0]).resolve()
EVIDENCE = Path(arguments[1]).resolve() if len(arguments) == 2 else None
sys.argv = sys.argv[:1]
PATCH = ROOT / "source-boundary.patch"
TESTS = ROOT / "tests"
NX, NY, NZ = 2, 2, 3
DL = (2.0, 3.0, 4.0)
DT = 0.125
DZF = (0.4, 1.1, 2.3, 3.7, 5.2)


def added_source() -> str:
    lines = []
    for line in PATCH.read_text(encoding="utf-8").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    return "\n".join(lines)


def production_subroutine(source: str, name: str) -> str:
    marker = f"  subroutine {name}("
    starts = [index for index in range(len(source)) if source.startswith(marker, index)]
    if len(starts) != 1:
        raise AssertionError(f"expected one added production subroutine {name}, found {len(starts)}")
    start = starts[0]
    end_marker = f"  end subroutine {name}"
    end = source.find(end_marker, start)
    if end < 0:
        raise AssertionError(f"missing end marker for {name}")
    end += len(end_marker)
    return source[start:end]


def generated_module(source: str) -> str:
    names = (
        "restas_source_accumulate_boundary_flux",
        "restas_source_add_boundary_volume",
        "restas_source_record_inventory",
        "restas_source_record_velocity_audit",
    )
    routines = "\n\n".join(production_subroutine(source, name) for name in names)
    return f"""module mod_param
  implicit none
  integer, parameter :: rp=selected_real_kind(15,300)
  real(rp), parameter :: rho1=1000._rp
end module mod_param

module candidate6_production_helpers
  use mod_param, only: rp
  implicit none
  logical :: restas_source_loaded=.false.,restas_source_log_open=.false.
  integer :: restas_boundary_unit=31,restas_mass_unit=32,restas_velocity_unit=33
  real(rp) :: restas_step_in_volume(6)=0._rp,restas_step_out_volume(6)=0._rp
  real(rp) :: restas_cumulative_in_mass=0._rp,restas_cumulative_out_mass=0._rp
  real(rp) :: restas_initial_mass=0._rp
contains
{routines}
end module candidate6_production_helpers
"""


def check_patch_contract(source: str) -> None:
    for name in (
        "restas_source_accumulate_boundary_flux",
        "restas_source_record_inventory",
        "restas_source_record_velocity_audit",
    ):
        body = production_subroutine(source, name)
        if body.count("dzf(0:)") != 1 or "dzf(:)" in body:
            raise AssertionError(f"{name} does not retain caller lower bound zero")
    # The audit keeps its inherited division arithmetic. Candidate5 v1.2's
    # timestep restriction remains a separate captured-inverse calculation.
    required = (
        "dtix=ux/dl(1)+vx/dl(2)+wx/dzf(k)",
        "dtiy=uy/dl(1)+vy/dl(2)+wy/dzf(k)",
        "dtiz=uz/dl(1)+vz/dl(2)+wz/dzf(k)",
        "dtix=ux*dli(1)+vx*dli(2)+wx*dzfi(k)",
        "dtiz=uz*dli(1)+vz*dli(2)+wz*dzci(k)",
    )
    for expression in required:
        if expression not in source:
            raise AssertionError(f"candidate6 lost a frozen Courant expression: {expression}")


def check_new_include_hunk_count() -> None:
    patch = PATCH.read_text(encoding="utf-8")
    match = re.search(r"(?m)^@@ -0,0 \+1,(\d+) @@$", patch)
    if match is None:
        raise AssertionError("candidate6 new source include hunk header is missing")
    body = patch[match.end():].split("\ndiff --git ", 1)[0].splitlines()
    added_lines = sum(line.startswith("+") and not line.startswith("+++") for line in body)
    if added_lines != int(match.group(1)):
        raise AssertionError(
            f"candidate6 source include hunk declares {match.group(1)} lines but adds {added_lines}"
        )


def flux(i: int, j: int, k: int) -> float:
    return 0.13 * i - 0.17 * j + 0.09 * k - 0.24


def volume_partition(outward_volume: float) -> tuple[float, float]:
    return (max(0.0, -outward_volume), max(0.0, outward_volume))


def expected_boundary(vertical_spacing: tuple[float, ...] = DZF) -> tuple[list[float], list[float]]:
    incoming = [0.0] * 6
    outgoing = [0.0] * 6

    def add(face: int, outward: float) -> None:
        inside, outside = volume_partition(outward)
        incoming[face] += inside
        outgoing[face] += outside

    for k in range(1, NZ + 1):
        for j in range(1, NY + 1):
            area = DL[1] * vertical_spacing[k]
            add(0, -flux(0, j, k) * area)
            add(1, flux(NX, j, k) * area)
    for k in range(1, NZ + 1):
        for i in range(1, NX + 1):
            area = DL[0] * vertical_spacing[k]
            add(2, -flux(i, 0, k) * area)
            add(3, flux(i, NY, k) * area)
    for j in range(1, NY + 1):
        for i in range(1, NX + 1):
            area = DL[0] * DL[1]
            add(4, -flux(i, j, 0) * area)
            add(5, flux(i, j, NZ) * area)
    return incoming, outgoing


def alpha(i: int, j: int, k: int) -> float:
    return 0.11 + 0.025 * i + 0.015 * j + 0.02 * k


def inventory_mass(increment: float, vertical_spacing: tuple[float, ...] = DZF) -> float:
    return 1000.0 * sum(
        (alpha(i, j, k) + increment) * DL[0] * DL[1] * vertical_spacing[k]
        for k in range(1, NZ + 1)
        for j in range(1, NY + 1)
        for i in range(1, NX + 1)
    )


def velocity(component: str, i: int, j: int, k: int) -> float:
    if component == "u":
        return 0.01 * (0.25 * i - 0.10 * j + 0.05 * k)
    if component == "v":
        return 0.01 * (-0.15 * i + 0.20 * j - 0.04 * k)
    return 1.1 * k


def expected_velocity(vertical_spacing: tuple[float, ...] = DZF) -> list[float]:
    face_out = [0.0] * 6
    for k in range(1, NZ + 1):
        for j in range(1, NY + 1):
            face_out[0] -= velocity("u", 0, j, k) * DL[1] * vertical_spacing[k]
            face_out[1] += velocity("u", NX, j, k) * DL[1] * vertical_spacing[k]
    for k in range(1, NZ + 1):
        for i in range(1, NX + 1):
            face_out[2] -= velocity("v", i, 0, k) * DL[0] * vertical_spacing[k]
            face_out[3] += velocity("v", i, NY, k) * DL[0] * vertical_spacing[k]
    for j in range(1, NY + 1):
        for i in range(1, NX + 1):
            face_out[4] -= velocity("w", i, j, 0) * DL[0] * DL[1]
            face_out[5] += velocity("w", i, j, NZ) * DL[0] * DL[1]

    div_integral = 0.0
    div_l1 = 0.0
    div_max = 0.0
    global_courant = 0.0
    interface_courant = 0.0
    for k in range(1, NZ + 1):
        cell_volume = DL[0] * DL[1] * vertical_spacing[k]
        for j in range(1, NY + 1):
            for i in range(1, NX + 1):
                div = (
                    (velocity("u", i, j, k) - velocity("u", i - 1, j, k)) / DL[0]
                    + (velocity("v", i, j, k) - velocity("v", i, j - 1, k)) / DL[1]
                    + (velocity("w", i, j, k) - velocity("w", i, j, k - 1))
                    / vertical_spacing[k]
                )
                div_integral += div * cell_volume
                div_l1 += abs(div) * cell_volume
                div_max = max(div_max, abs(div))

                ux = abs(velocity("u", i, j, k))
                vx = 0.25 * abs(
                    velocity("v", i, j, k) + velocity("v", i, j - 1, k)
                    + velocity("v", i + 1, j, k) + velocity("v", i + 1, j - 1, k)
                )
                wx = 0.25 * abs(
                    velocity("w", i, j, k) + velocity("w", i, j, k - 1)
                    + velocity("w", i + 1, j, k) + velocity("w", i + 1, j, k - 1)
                )
                dtix = ux / DL[0] + vx / DL[1] + wx / vertical_spacing[k]
                uy = 0.25 * abs(
                    velocity("u", i, j, k) + velocity("u", i, j + 1, k)
                    + velocity("u", i - 1, j + 1, k) + velocity("u", i - 1, j, k)
                )
                vy = abs(velocity("v", i, j, k))
                wy = 0.25 * abs(
                    velocity("w", i, j, k) + velocity("w", i, j + 1, k)
                    + velocity("w", i, j + 1, k - 1) + velocity("w", i, j, k - 1)
                )
                dtiy = uy / DL[0] + vy / DL[1] + wy / vertical_spacing[k]
                uz = 0.25 * abs(
                    velocity("u", i, j, k) + velocity("u", i - 1, j, k)
                    + velocity("u", i - 1, j, k + 1) + velocity("u", i, j, k + 1)
                )
                vz = 0.25 * abs(
                    velocity("v", i, j, k) + velocity("v", i, j - 1, k)
                    + velocity("v", i, j - 1, k + 1) + velocity("v", i, j, k + 1)
                )
                wz = abs(velocity("w", i, j, k))
                dtiz = uz / DL[0] + vz / DL[1] + wz / vertical_spacing[k]
                cell_courant = DT * max(dtix, dtiy, dtiz)
                global_courant = max(global_courant, cell_courant)
                interface_courant = max(interface_courant, cell_courant)

    # Candidate5 v1.2's separate timestep path uses the captured dzfi(k) in
    # x/y and dzci(k) in z, with multiplication in source order.
    captured_courant = 0.0
    for k in range(1, NZ + 1):
        dzci = 1.0 / (0.5 * (vertical_spacing[k] + vertical_spacing[k + 1]))
        dzfi = 1.0 / vertical_spacing[k]
        for j in range(1, NY + 1):
            for i in range(1, NX + 1):
                ux = abs(velocity("u", i, j, k))
                vx = 0.25 * abs(
                    velocity("v", i, j, k) + velocity("v", i, j - 1, k)
                    + velocity("v", i + 1, j, k) + velocity("v", i + 1, j - 1, k)
                )
                wx = 0.25 * abs(
                    velocity("w", i, j, k) + velocity("w", i, j, k - 1)
                    + velocity("w", i + 1, j, k) + velocity("w", i + 1, j, k - 1)
                )
                dtix = ux * (1.0 / DL[0]) + vx * (1.0 / DL[1]) + wx * dzfi
                uy = 0.25 * abs(
                    velocity("u", i, j, k) + velocity("u", i, j + 1, k)
                    + velocity("u", i - 1, j + 1, k) + velocity("u", i - 1, j, k)
                )
                vy = abs(velocity("v", i, j, k))
                wy = 0.25 * abs(
                    velocity("w", i, j, k) + velocity("w", i, j + 1, k)
                    + velocity("w", i, j + 1, k - 1) + velocity("w", i, j, k - 1)
                )
                dtiy = uy * (1.0 / DL[0]) + vy * (1.0 / DL[1]) + wy * dzfi
                uz = 0.25 * abs(
                    velocity("u", i, j, k) + velocity("u", i - 1, j, k)
                    + velocity("u", i - 1, j, k + 1) + velocity("u", i, j, k + 1)
                )
                vz = 0.25 * abs(
                    velocity("v", i, j, k) + velocity("v", i, j - 1, k)
                    + velocity("v", i, j - 1, k + 1) + velocity("v", i, j, k + 1)
                )
                wz = abs(velocity("w", i, j, k))
                dtiz = uz * (1.0 / DL[0]) + vz * (1.0 / DL[1]) + wz * dzci
                captured_courant = max(captured_courant, DT * max(dtix, dtiy, dtiz))

    if math.isclose(global_courant, captured_courant, rel_tol=1.0e-7, abs_tol=1.0e-10):
        raise AssertionError("nonuniform fixture failed to distinguish the two Courant contracts")
    return [
        1.0,
        0.0,
        DT,
        DT,
        float(NX * NY * NZ),
        global_courant,
        float(NX * NY * NZ),
        1.0,
        interface_courant,
        max(0.0, -face_out[5]),
        max(0.0, face_out[4]),
        sum(face_out),
        div_integral,
        div_integral - sum(face_out),
        div_max,
        div_l1,
        *face_out,
    ]


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="ascii") as stream:
        return list(csv.reader(stream, strict=True))


def assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=2.0e-12, abs_tol=2.0e-12):
        raise AssertionError(f"{label}: observed {actual:.17g}, expected {expected:.17g}")


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit("usage: test_dzf_lower_bound_helpers.py CANDIDATE6_DIR")
    patch_source = added_source()
    check_new_include_hunk_count()
    check_patch_contract(patch_source)
    compiler = shutil.which("nvfortran") or shutil.which("gfortran")
    if compiler is None:
        raise SystemExit("no supported Fortran compiler found (nvfortran, gfortran, or flang)")
    with tempfile.TemporaryDirectory(prefix="candidate6-dzf-helper-") as directory:
        work = Path(directory)
        generated = work / "candidate6_production_helpers.f90"
        executable = work / "dzf_lower_bound_driver"
        generated.write_text(generated_module(patch_source), encoding="utf-8")
        driver = TESTS / "dzf_lower_bound_driver.f90"
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
        compile_result = subprocess.run(
            compile_command,
            cwd=work,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if compile_result.returncode:
            raise AssertionError(f"Fortran helper compile failed:\n{compile_result.stdout}")
        run_output = ""
        prefix = work / "actual"
        run_result = subprocess.run(
            [str(executable), str(prefix)],
            cwd=work,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if run_result.returncode:
            raise AssertionError(f"compiled helper test failed:\n{run_result.stdout}")
        run_output = run_result.stdout

        incoming, outgoing = expected_boundary()
        boundary_rows = read_csv_rows(work / "actual_boundary.csv")
        if len(boundary_rows) != 2:
            raise AssertionError(f"expected two boundary rows, got {len(boundary_rows)}")
        for row_index, row in enumerate(boundary_rows):
            values = [float(value) for value in row]
            expected = [float(row_index), *sum(([incoming[i], outgoing[i]] for i in range(6)), [])]
            if len(values) != len(expected):
                raise AssertionError(f"boundary row {row_index} has {len(values)} fields")
            for column, (actual, target) in enumerate(zip(values, expected, strict=True)):
                assert_close(actual, target, f"boundary row {row_index} field {column}")

        mass_rows = read_csv_rows(work / "actual_mass.csv")
        if len(mass_rows) != 2:
            raise AssertionError(f"expected two inventory rows, got {len(mass_rows)}")
        first = [float(value) for value in mass_rows[0]]
        second = [float(value) for value in mass_rows[1]]
        if len(first) != 20 or len(second) != 20:
            raise AssertionError("inventory helper emitted an unexpected field count")
        expected_in = 1000.0 * sum(incoming)
        expected_out = 1000.0 * sum(outgoing)
        checks = (
            (first[2], inventory_mass(0.0), "initial inventory"),
            (second[2], inventory_mass(0.03), "step inventory"),
            (second[3], inventory_mass(0.0), "stored initial inventory"),
            (second[4], expected_in, "cumulative incoming mass"),
            (second[5], expected_out, "cumulative outgoing mass"),
            (second[6], expected_in - expected_out - (inventory_mass(0.03) - inventory_mass(0.0)),
             "mass residual"),
            (second[7], sum(incoming) - sum(outgoing), "net boundary volume"),
        )
        for actual, expected, label in checks:
            assert_close(actual, expected, label)

        velocity_rows = read_csv_rows(work / "actual_velocity.csv")
        if len(velocity_rows) != 1 or len(velocity_rows[0]) != 22:
            raise AssertionError("velocity audit emitted an unexpected row shape")
        actual_velocity = [float(value) for value in velocity_rows[0]]
        expected_velocity_values = expected_velocity()
        for column, (actual, expected) in enumerate(
            zip(actual_velocity, expected_velocity_values, strict=True)
        ):
            assert_close(actual, expected, f"velocity audit field {column}")

        if EVIDENCE is not None:
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            if any(EVIDENCE.iterdir()):
                raise SystemExit(f"one-halo evidence directory is not empty: {EVIDENCE}")
            retained = [generated, driver, executable, *work.glob("*.mod"), *work.glob("actual_*.csv")]
            for path in retained:
                shutil.copy2(path, EVIDENCE / path.name)
            version = subprocess.run(
                [compiler, "--version"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            (EVIDENCE / "compiler.txt").write_text(version.stdout, encoding="utf-8")
            (EVIDENCE / "compile-command.txt").write_text(
                shlex.join(compile_command) + "\n", encoding="utf-8"
            )
            (EVIDENCE / "compile.log").write_text(compile_result.stdout, encoding="utf-8")
            (EVIDENCE / "driver.stdout").write_text(run_output, encoding="utf-8")

    print(f"PASS: compiled extracted candidate6 helpers with {Path(compiler).name}")
    print("PASS: 0:nz+1 one-halo mapping, nonconstant dzf face areas, inventory volumes, divergence and legacy Courant")
    print("PASS: captured dzfi/dzci v1.2 Courant remains a distinct expression and expected value")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
