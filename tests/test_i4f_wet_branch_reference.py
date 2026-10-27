from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts import prepare_i4f_wet_branch_reference as wet


def test_pressure_transform_round_trips_vector_points() -> None:
    points = np.asarray([[2.25, -0.4, 0.4], [4.8, -0.55, 1.2]])
    pressure = np.asarray([101_200.0, 97_500.0])
    reduced = wet.reduced_pressure(
        pressure, wet.P_AMBIENT, wet.RHO, wet.GRAVITY, points, wet.XREF_XYZ
    )
    recovered = wet.recover_absolute_pressure(
        reduced, wet.P_AMBIENT, wet.RHO, wet.GRAVITY, points, wet.XREF_XYZ
    )
    np.testing.assert_allclose(recovered, pressure, rtol=0, atol=2e-11)


def test_outlet_profile_recovers_uniform_ambient_at_varied_elevation() -> None:
    face_centers = np.asarray([[4.8, -0.5, 0.35], [4.8, -0.5, 0.8], [4.8, -0.5, 1.25]])
    xref = np.asarray([4.8, -0.5, 0.8])
    reduced = wet.outlet_pressure_values(face_centers, wet.GRAVITY, xref)
    recovered = wet.recover_absolute_pressure(
        reduced, wet.P_AMBIENT, wet.RHO, wet.GRAVITY, face_centers, xref
    )
    np.testing.assert_allclose(recovered, wet.P_AMBIENT, rtol=0, atol=1e-10)


def test_connected_cell_regions_counts_disconnected_components() -> None:
    owners = np.asarray([0, 1, 3])
    neighbours = np.asarray([1, 2, 4])
    assert wet._count_connected_cells(owners, neighbours) == 2


def test_vector_patch_parser_handles_ascii_nonuniform_values() -> None:
    field = b"""FoamFile
{
    format      ascii;
}
boundaryField
{
    wetOutlet
    {
        type fixedValue;
        value nonuniform List<vector> 2
        (
            (1 2 3)
            (4 5 6)
        );
    }
}
"""
    values = wet._parse_patch_vector_values(field, "wetOutlet", 2)
    np.testing.assert_array_equal(values, [[1, 2, 3], [4, 5, 6]])


def test_freeze_includes_initial_fields_but_excludes_written_times_and_logs(
    tmp_path: Path,
) -> None:
    case = tmp_path / "case"
    (case / "0").mkdir(parents=True)
    (case / "0/p").write_text("initial", encoding="utf-8")
    (case / "constant").mkdir()
    (case / "constant/transportProperties").write_text("nu", encoding="utf-8")
    (case / "0.01").mkdir()
    (case / "0.01/p").write_text("output", encoding="utf-8")
    (case / "log.simpleFoam").write_text("log", encoding="utf-8")
    freeze = wet.freeze_inputs(tmp_path)
    frozen_paths = {item["path"] for item in freeze["files"]}
    assert frozen_paths == {"0/p", "constant/transportProperties"}


def test_simplefoam_residual_parser_records_iteration_count(tmp_path: Path) -> None:
    log = tmp_path / "log.simpleFoam"
    log.write_text(
        "Time = 14\n"
        "Solving for Ux, Initial residual = 0.2, Final residual = 0.001, No Iterations 7\n"
        "Solving for p, Initial residual = 0.04, Final residual = 1e-7, No Iterations 19\n"
        "End\n",
        encoding="utf-8",
    )

    result = wet._parse_simplefoam_residuals(log)

    assert result["last_logged_iteration"] == 14
    assert result["last_linear_solves"]["p"]["linear_iterations"] == 19
    assert result["normal_End"]


def test_simplefoam_residual_parser_accepts_solver_prefixes(tmp_path: Path) -> None:
    log = tmp_path / "log.simpleFoam"
    log.write_text(
        "Time = 9\n"
        "smoothSolver:  Solving for Ux, Initial residual = 0.2, Final residual = 0.001, No Iterations 7\n"
        "GAMG:  Solving for p, Initial residual = 0.04, Final residual = 1e-7, No Iterations 19\n"
        "End\n",
        encoding="utf-8",
    )

    result = wet._parse_simplefoam_residuals(log)

    assert result["linear_solve_records"] == 2
    assert result["last_linear_solves"]["Ux"]["linear_iterations"] == 7
    assert result["last_linear_solves"]["p"]["linear_iterations"] == 19


def test_steady_iteration_history_reads_extrema_fluxes_and_pressure_units(tmp_path: Path) -> None:
    log = tmp_path / "log.simpleFoam"
    log.write_text(
        "Time = 1\n"
        "smoothSolver: Solving for Ux, Initial residual = 0.2, Final residual = 0.01, No Iterations 2\n"
        "GAMG: Solving for p, Initial residual = 0.3, Final residual = 0.02, No Iterations 3\n"
        "GAMG: Solving for p, Initial residual = 0.1, Final residual = 0.01, No Iterations 1\n"
        "time step continuity errors : sum local = 0.02, global = -0.01, cumulative = -0.01\n"
        "sum(wetInlet) of phi = -0.6\n"
        "sum(wetOutlet) of phi = 0.59\n"
        "max(mag(U)) = 21 in cell 4 at location (4.2 -0.5 0.9)\n"
        "min(p) = -200 in cell 4 at location (4.2 -0.5 0.9)\n"
        "max(p) = 10 in cell 3 at location (4.5 -0.5 0.9)\n"
        "max(k) = 0.1 in cell 4 at location (4.2 -0.5 0.9)\n"
        "max(omega) = 2 in cell 4 at location (4.2 -0.5 0.9)\n"
        "Time = 2\nEnd\n",
        encoding="utf-8",
    )

    rows = wet._parse_simplefoam_iteration_history(log)

    assert len(rows) == 2
    assert rows[0]["steady_iteration"] == 1
    assert rows[0]["p_solve_count"] == 2
    assert rows[0]["p_linear_iterations_total"] == 4
    assert rows[0]["wetOutlet_Q_m3_s"] == pytest.approx(0.59)
    assert rows[0]["U_mag_max_value"] == pytest.approx(21)
    assert rows[0]["p_abs_min_at_logged_pmin_pa"] < 0
    assert rows[1]["steady_iteration"] == 2


def test_surface_flux_parser_uses_last_logged_patch_values(tmp_path: Path) -> None:
    log = tmp_path / "log.simpleFoam"
    log.write_text(
        "sum(wetInlet) of phi = -0.6\n"
        "sum(wetOutlet) of phi = 0.59\n"
        "sum(wetInlet) of phi = -0.5998\n"
        "sum(wetOutlet) of phi = 0.5997\n",
        encoding="utf-8",
    )

    result = wet._parse_logged_surface_fluxes(log)

    assert result["last_m3_s"] == {"wetInlet": -0.5998, "wetOutlet": 0.5997}


def test_reduced_pressure_rejects_invalid_density() -> None:
    with pytest.raises(ValueError, match="density"):
        wet.reduced_pressure(100_000.0, 100_000.0, 0.0, wet.GRAVITY, [0, 0, 0], [0, 0, 0])
