"""Pure-Python static checks and diagnostics for the provisional E1 case.

This module has no OpenFOAM, mesh, or solver dependency.  It checks the inputs
and synthetic fixtures only; it does not read or create CFD results.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

CASE_DIR = Path(__file__).resolve().parent / "case"
PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parents[1]
NOZZLE_DIAMETER_M = 0.4
RHO_WATER_KG_M3 = 997.6
RHO_AIR_KG_M3 = 1.18
WATER_NU_M2_S = 8.91138772955092e-7
AIR_NU_M2_S = 1.576271186440678e-5
SURFACE_TENSION_N_M = 0.072
GRAVITY_M_S2 = (0.0, -9.81, 0.0)
IMAGE_ID = "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
SOURCE_PDF_SHA256 = "624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446"
ALPHA_BOUND_CANDIDATE = (-1.0e-6, 1.0 + 1.0e-6)
WALL_NODE_SERIALIZATION_SIGNIFICANT_DIGITS = 9


def wall_y_serialization_allowance(amplitude_m: float) -> float:
    """Return the largest 9-significant-digit rounding half-step below A.

    The generated wall-node CSV uses ``.9g``.  For positive ``A``, the
    coarsest decimal step at any value in ``[0, A]`` is
    ``10**(floor(log10(A)) - 8)``; half of that step bounds its rounding
    error.  For the declared ``A=0.08 m`` this conservative allowance is
    ``5e-11 m``.
    """
    if not math.isfinite(amplitude_m) or amplitude_m <= 0.0:
        raise ValueError("wall amplitude must be finite and positive")
    decimal_exponent = math.floor(math.log10(amplitude_m))
    return 0.5 * 10.0 ** (decimal_exponent - (WALL_NODE_SERIALIZATION_SIGNIFICANT_DIGITS - 1))


PATCHES = (
    "nozzle",
    "gasInlet",
    "aircraftWall",
    "downstreamOutlet",
    "bottomOutlet",
    "spanwiseMinus",
    "spanwisePlus",
)

EXPECTED_DIMENSIONS = {
    "U": "[0 1 -1 0 0 0 0]",
    "alpha.water": "[0 0 0 0 0 0 0]",
    "p_rgh": "[1 -1 -2 0 0 0 0]",
    "k": "[0 2 -2 0 0 0 0]",
    "epsilon": "[0 2 -3 0 0 0 0]",
    "nut": "[0 2 -1 0 0 0 0]",
}

EXPECTED_PATCH_TYPES = {
    "U": {
        "nozzle": "fixedValue",
        "gasInlet": "fixedValue",
        "aircraftWall": "noSlip",
        **{name: "pressureInletOutletVelocity" for name in PATCHES[3:]},
    },
    "alpha.water": {
        "nozzle": "fixedValue",
        "gasInlet": "fixedValue",
        "aircraftWall": "constantAlphaContactAngle",
        **{name: "inletOutlet" for name in PATCHES[3:]},
    },
    "p_rgh": {
        "nozzle": "fixedFluxPressure",
        "gasInlet": "fixedFluxPressure",
        "aircraftWall": "fixedFluxPressure",
        **{name: "prghPressure" for name in PATCHES[3:]},
    },
    "k": {
        "nozzle": "fixedValue",
        "gasInlet": "fixedValue",
        "aircraftWall": "kqRWallFunction",
        **{name: "inletOutlet" for name in PATCHES[3:]},
    },
    "epsilon": {
        "nozzle": "fixedValue",
        "gasInlet": "fixedValue",
        "aircraftWall": "epsilonWallFunction",
        **{name: "inletOutlet" for name in PATCHES[3:]},
    },
    "nut": {
        "nozzle": "calculated",
        "gasInlet": "calculated",
        "aircraftWall": "nutkWallFunction",
        **{name: "inletOutlet" for name in PATCHES[3:]},
    },
}


@dataclass(frozen=True)
class StaticCheck:
    name: str
    passed: bool
    detail: str


def _without_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def _named_block(text: str, name: str) -> str:
    clean = _without_comments(text)
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*\{{", clean)
    if not match:
        raise ValueError(f"missing dictionary block {name!r}")
    opening = clean.find("{", match.start())
    depth = 0
    for index in range(opening, len(clean)):
        if clean[index] == "{":
            depth += 1
        elif clean[index] == "}":
            depth -= 1
            if depth == 0:
                return clean[opening + 1 : index]
    raise ValueError(f"unterminated dictionary block {name!r}")


def _direct_subblocks(text: str) -> dict[str, str]:
    clean = _without_comments(text)
    result: dict[str, str] = {}
    index = 0
    while index < len(clean):
        match = re.search(r"([A-Za-z_][A-Za-z0-9_.-]*)\s*\{", clean[index:])
        if not match:
            break
        name = match.group(1)
        start = index + match.end() - 1
        prefix = clean[index : index + match.start()]
        if prefix.count("{") != prefix.count("}"):
            index += match.end()
            continue
        depth = 0
        end = None
        for cursor in range(start, len(clean)):
            if clean[cursor] == "{":
                depth += 1
            elif clean[cursor] == "}":
                depth -= 1
                if depth == 0:
                    end = cursor
                    break
        if end is None:
            raise ValueError(f"unterminated subdictionary {name!r}")
        result[name] = clean[start + 1 : end]
        index = end + 1
    return result


def field_dimensions_and_patch_types(path: Path) -> tuple[str, dict[str, str], str]:
    text = _without_comments(path.read_text(encoding="utf-8"))
    dimensions = re.search(r"\bdimensions\s+(\[[^]]+\])\s*;", text)
    if not dimensions:
        raise ValueError(f"{path}: missing dimensions")
    boundary = _direct_subblocks(_named_block(text, "boundaryField"))
    types: dict[str, str] = {}
    for patch, body in boundary.items():
        match = re.search(r"\btype\s+(\S+)\s*;", body)
        if match:
            types[patch] = match.group(1)
    return dimensions.group(1), types, text


def check_case_fields(case_dir: Path = CASE_DIR) -> list[StaticCheck]:
    checks: list[StaticCheck] = []
    for field, expected_dimension in EXPECTED_DIMENSIONS.items():
        path = case_dir / "0" / field
        if not path.is_file():
            checks.append(StaticCheck(f"field_exists:{field}", False, str(path)))
            continue
        try:
            dimensions, actual_types, raw_text = field_dimensions_and_patch_types(path)
        except ValueError as error:
            checks.append(StaticCheck(f"field_parse:{field}", False, str(error)))
            continue
        checks.append(
            StaticCheck(
                f"dimensions:{field}",
                dimensions == expected_dimension,
                f"actual={dimensions}; expected={expected_dimension}",
            )
        )
        expected_types = EXPECTED_PATCH_TYPES[field]
        checks.append(
            StaticCheck(
                f"patch_set:{field}",
                set(actual_types) == set(PATCHES),
                f"actual={sorted(actual_types)}; expected={sorted(PATCHES)}",
            )
        )
        for patch in PATCHES:
            actual = actual_types.get(patch)
            expected = expected_types[patch]
            checks.append(
                StaticCheck(
                    f"patch_type:{field}:{patch}",
                    actual == expected,
                    f"actual={actual}; expected={expected}",
                )
            )
        if field == "alpha.water":
            try:
                wall = _named_block(_named_block(raw_text, "boundaryField"), "aircraftWall")
            except ValueError:
                wall = ""
            has_wall_angle = all(
                re.search(pattern, wall) is not None
                for pattern in (
                    r"\btype\s+constantAlphaContactAngle\s*;",
                    r"\btheta0\s+90\s*;",
                    r"\blimit\s+gradient\s*;",
                    r"\bvalue\s+uniform\s+0\s*;",
                )
            ) and not any(re.search(rf"\b{key}\b", wall) for key in ("thetaA", "thetaR", "uTheta"))
            checks.append(
                StaticCheck(
                    "provisional_contact_angle_dictionary",
                    has_wall_angle,
                    "wall block uses constantAlphaContactAngle; theta0=90 deg; required limit=gradient",
                )
            )
        if field == "nut":
            required = (
                re.compile(r"\binletValue\s+uniform\s+0\s*;"),
                re.compile(r"\bvalue\s+uniform\s+0\s*;"),
            )
            open_bodies = _direct_subblocks(_named_block(raw_text, "boundaryField"))
            open_values = all(
                all(pattern.search(open_bodies[patch]) is not None for pattern in required)
                for patch in PATCHES[3:]
            )
            seed_values = all(
                re.search(r"\bvalue\s+uniform\s+0\s*;", open_bodies[patch]) is not None
                for patch in PATCHES[:2]
            )
            checks.append(
                StaticCheck(
                    "D-NUT-BC_open_reverse_seed",
                    open_values,
                    "open patches use inletOutlet with zero reverse-flow nut and explicit seed",
                )
            )
            checks.append(
                StaticCheck(
                    "D-NUT-BC_inlet_calculated_seed",
                    seed_values,
                    "inlets use calculated with zero initialization seed",
                )
            )
    return checks


def _list_entry_blocks(text: str, name: str) -> list[str]:
    """Return the simple brace-delimited entries in a named parenthesized list."""
    clean = _without_comments(text)
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*\(", clean)
    if not match:
        raise ValueError(f"missing parenthesized dictionary list {name!r}")
    opening = clean.find("(", match.start())
    depth = 0
    closing = None
    for index in range(opening, len(clean)):
        if clean[index] == "(":
            depth += 1
        elif clean[index] == ")":
            depth -= 1
            if depth == 0:
                closing = index
                break
    if closing is None:
        raise ValueError(f"unterminated parenthesized dictionary list {name!r}")
    return re.findall(r"\{([^{}]*)\}", clean[opening + 1 : closing], flags=re.DOTALL)


def check_case_dictionaries(case_dir: Path = CASE_DIR) -> list[StaticCheck]:
    """Check the pinned provisional transport, alpha solver, sampler, and nozzle contract."""
    checks: list[StaticCheck] = []
    try:
        turbulence = _without_comments(
            (case_dir / "constant" / "turbulenceProperties").read_text(encoding="utf-8")
        )
        # density must be a top-level entry after FoamFile and before RAS.
        density_variable = (
            re.search(r"(?s)\}\s*density\s+variable\s*;\s*simulationType\s+RAS\s*;", turbulence)
            is not None
        )
        checks.append(
            StaticCheck(
                "provisional_variable_density_top_level",
                density_variable,
                "top-level density variable selects the pinned v2512 rhoPhi turbulence path",
            )
        )
    except OSError as error:
        checks.append(StaticCheck("provisional_variable_density_top_level", False, str(error)))

    try:
        schemes = _without_comments((case_dir / "system" / "fvSchemes").read_text(encoding="utf-8"))
        div_schemes = _named_block(schemes, "divSchemes")
        required_divergence_entries = (
            "div(rhoPhi,U) Gauss linearUpwind grad(U);",
            "div(rhoPhi,k) Gauss linearUpwind grad(k);",
            "div(rhoPhi,epsilon) Gauss linearUpwind grad(epsilon);",
            "div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;",
        )
        normalized_div = " ".join(div_schemes.split())
        for entry in required_divergence_entries:
            passed = entry in normalized_div
            checks.append(
                StaticCheck(
                    f"fvSchemes:{entry.split()[0]}",
                    passed,
                    f"required exact v2512 provisional entry: {entry}",
                )
            )
    except (OSError, ValueError) as error:
        checks.append(StaticCheck("fvSchemes_parse", False, str(error)))

    try:
        solution = _without_comments(
            (case_dir / "system" / "fvSolution").read_text(encoding="utf-8")
        )
    except OSError as error:
        solution = ""
        checks.append(StaticCheck("fvSolution_parse", False, str(error)))
    try:
        solvers = _named_block(solution, "solvers")
    except ValueError as error:
        solvers = ""
        checks.append(StaticCheck("fvSolution_parse", False, str(error)))
    try:
        pressure = _named_block(solvers, "p_rgh")
    except ValueError:
        pressure = ""
    gamg_valid = all(
        re.search(pattern, pressure) is not None
        for pattern in (r"\bsolver\s+GAMG\s*;", r"\bsmoother\s+DICGaussSeidel\s*;")
    )
    checks.append(
        StaticCheck(
            "fvSolution_GAMG_smoother",
            gamg_valid,
            "p_rgh nominates GAMG with DICGaussSeidel smoother",
        )
    )
    try:
        alpha_controls = _named_block(solvers, '"alpha.*"')
    except ValueError:
        alpha_controls = ""
    alpha_valid = all(
        re.search(pattern, alpha_controls) is not None
        for pattern in (
            r"\bclip\s+true\s*;",
            r"\bsnapTol\s+0\s*;",
            r"\bnAlphaSubCycles\s+1\s*;",
            r"\breconstructionScheme\s+isoAlpha\s*;",
        )
    )
    alpha_valid &= len(re.findall(r"\breconstructionScheme\b", solution)) == 1
    checks.append(
        StaticCheck(
            "fvSolution_alpha_controls_nested_isoAlpha",
            alpha_valid,
            "alpha controls are inside solvers with clip=true, snapTol=0, one subcycle, isoAlpha",
        )
    )

    try:
        control = _without_comments(
            (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
        )
        functions = _named_block(control, "functions")
        sampler = _named_block(functions, "rouaixStations")
        entries = {
            f"{observable}_X_{station:.3f}".replace(".", "p"): station
            for observable, stations in figure13_reference_stations().items()
            for station in stations
        }
        plane_checks = []
        for entry_name, station in entries.items():
            body = _named_block(sampler, entry_name)
            point = _vector_entry(body, "point")
            normal = _vector_entry(body, "normal")
            plane_checks.append(
                re.search(r"\binterpolate\s+true\s*;", body) is not None
                and re.search(r"\btriangulate\s+true\s*;", body) is not None
                and math.isclose(point[0], station * NOZZLE_DIAMETER_M, rel_tol=0.0, abs_tol=1e-12)
                and point[1:] == (0.0, 0.0)
                and normal == (1.0, 0.0, 0.0)
            )
        checks.append(
            StaticCheck(
                "sampler_each_plane_interpolates_and_matches_station",
                len(entries) == 30 and all(plane_checks),
                f"{sum(plane_checks)}/{len(entries)} expected planes have interpolate=true and frozen plane geometry",
            )
        )
    except (OSError, ValueError) as error:
        checks.append(StaticCheck("sampler_plane_contract", False, str(error)))

    try:
        topo = _without_comments((case_dir / "system" / "topoSetDict").read_text(encoding="utf-8"))
        actions = _list_entry_blocks(topo, "actions")
        action_values = [
            {name: value for name, value in re.findall(r"(?m)^\s*(\w+)\s+([^;]+);", body)}
            for body in actions
        ]
        ordered_boundary_intersection = (
            len(action_values) == 2
            and action_values[0].get("name") == "nozzleFaces"
            and action_values[0].get("type") == "faceSet"
            and action_values[0].get("action") == "new"
            and action_values[0].get("source") == "patchToFace"
            and action_values[0].get("patch") == "aircraftWall"
            and action_values[1].get("name") == "nozzleFaces"
            and action_values[1].get("type") == "faceSet"
            and action_values[1].get("action") == "subset"
            and action_values[1].get("source") == "cylinderToFace"
            and action_values[1].get("point1") == "(0 -0.1 0)"
            and action_values[1].get("point2") == "(0 0.1 0)"
            and action_values[1].get("radius") == "0.2"
        )
        create_patch = _without_comments(
            (case_dir / "system" / "createPatchDict").read_text(encoding="utf-8")
        )
        normalized_create_patch = " ".join(create_patch.split())
        patch_consumes_selected_set = (
            all(
                re.search(pattern, normalized_create_patch) is not None
                for pattern in (
                    r"\bname\s+nozzle\s*;",
                    r"\bconstructFrom\s+set\s*;",
                    r"\bset\s+nozzleFaces\s*;",
                    r"\bpatchInfo\s*\{\s*type\s+patch\s*;",
                )
            )
            and normalized_create_patch.count("name nozzle;") == 1
        )
        checks.extend(
            [
                StaticCheck(
                    "nozzle_selection_boundary_then_cylinder_subset",
                    ordered_boundary_intersection,
                    "topoSet first selects aircraftWall patch faces, then subsets the cylinder face-centre selection",
                ),
                StaticCheck(
                    "createPatch_consumes_boundary_intersection",
                    patch_consumes_selected_set,
                    "createPatch creates nozzle from the boundary-constrained nozzleFaces set",
                ),
            ]
        )
    except (OSError, ValueError) as error:
        checks.append(StaticCheck("nozzle_boundary_selection_parse", False, str(error)))
    return checks


def nozzle_geometry() -> dict[str, float | list[float] | str]:
    diameter = NOZZLE_DIAMETER_M
    radius = diameter / 2.0
    area = math.pi * radius**2
    speed = 10.0
    volume_flow = area * speed
    mass_flow = RHO_WATER_KG_M3 * volume_flow
    momentum = (0.0, -RHO_WATER_KG_M3 * area * speed**2, 0.0)
    return {
        "classification": "derived_from_reported_case1_inputs",
        "diameter_m": diameter,
        "area_m2": area,
        "normal_outward_nozzle": [0.0, 1.0, 0.0],
        "velocity_m_s": [0.0, -speed, 0.0],
        "volume_flow_m3_s": volume_flow,
        "water_mass_flow_kg_s": mass_flow,
        "momentum_influx_N": list(momentum),
    }


def pressure_reconstruct(
    p_rgh_pa: float,
    rho_kg_m3: float,
    position_m: Sequence[float],
    *,
    p_gauge_reference_pa: float = 0.0,
    gravity_m_s2: Sequence[float] = GRAVITY_M_S2,
    reference_point_m: Sequence[float] = (0.0, 0.0, 0.0),
) -> float:
    """Return static gauge pressure using v2512 p_rgh = p - rho*(g·(x-xRef))."""
    _validate_finite_scalar_values(
        p_rgh_pa, rho_kg_m3, p_gauge_reference_pa, label="pressure and density"
    )
    _validate_finite_vector(position_m, label="position")
    _validate_finite_vector(reference_point_m, label="reference point")
    _validate_finite_vector(gravity_m_s2, label="gravity")
    if rho_kg_m3 <= 0.0:
        raise ValueError("density must be positive")
    gh = sum(gravity_m_s2[i] * (position_m[i] - reference_point_m[i]) for i in range(3))
    result = p_rgh_pa + rho_kg_m3 * gh + p_gauge_reference_pa
    if not math.isfinite(result):
        raise ValueError("reconstructed pressure must be finite")
    return result


def prgh_from_static(
    p_gauge_pa: float,
    rho_kg_m3: float,
    position_m: Sequence[float],
    *,
    gravity_m_s2: Sequence[float] = GRAVITY_M_S2,
    reference_point_m: Sequence[float] = (0.0, 0.0, 0.0),
) -> float:
    _validate_finite_scalar_values(p_gauge_pa, rho_kg_m3, label="pressure and density")
    _validate_finite_vector(position_m, label="position")
    _validate_finite_vector(reference_point_m, label="reference point")
    _validate_finite_vector(gravity_m_s2, label="gravity")
    if rho_kg_m3 <= 0.0:
        raise ValueError("density must be positive")
    gh = sum(gravity_m_s2[i] * (position_m[i] - reference_point_m[i]) for i in range(3))
    result = p_gauge_pa - rho_kg_m3 * gh
    if not math.isfinite(result):
        raise ValueError("reconstructed p_rgh must be finite")
    return result


def _validate_finite_scalar_values(*values: float, label: str) -> None:
    if any(not math.isfinite(value) for value in values):
        raise ValueError(f"{label} must be finite")


def _validate_finite_vector(values: Sequence[float], *, label: str) -> None:
    if len(values) != 3 or any(not math.isfinite(value) for value in values):
        raise ValueError(f"{label} must contain three finite values")


def zero_safe_ratio(numerator: float, reference: float) -> dict[str, float | str | None]:
    if not math.isfinite(numerator) or not math.isfinite(reference):
        return {"status": "invalid_nonfinite", "ratio": None}
    if reference == 0.0:
        return {
            "status": "not_applicable_zero_reference",
            "ratio": None,
            "absolute_numerator": numerator,
            "absolute_reference": reference,
        }
    ratio = numerator / reference
    if not math.isfinite(ratio):
        return {"status": "invalid_nonfinite", "ratio": None}
    return {"status": "computed", "ratio": ratio}


def absent_phase_leakage(
    leakage_vector: Sequence[float],
    present_reference_vector: Sequence[float] | None,
) -> dict[str, object]:
    if present_reference_vector is None:
        return {"status": "invalid_present_reference", "ratio": None}
    if len(present_reference_vector) != 3 or len(leakage_vector) != 3:
        raise ValueError("phase momentum vectors must have three components")
    if any(
        not math.isfinite(component) for component in (*present_reference_vector, *leakage_vector)
    ):
        raise ValueError("phase momentum vectors must be finite")
    reference_norm = math.hypot(*present_reference_vector)
    leakage_norm = math.hypot(*leakage_vector)
    if not math.isfinite(reference_norm) or reference_norm <= 0.0:
        return {
            "status": "invalid_present_reference",
            "ratio": None,
            "reference_norm_N": reference_norm,
        }
    ratio = leakage_norm / reference_norm
    if not math.isfinite(ratio):
        raise ValueError("absent-phase momentum ratio must be finite")
    return {
        "status": "absent_reference",
        "ratio": ratio,
        "reference_norm_N": reference_norm,
        "leakage_vector_N": list(leakage_vector),
        "expected_vector_N": [0.0, 0.0, 0.0],
    }


def alpha_stage_summary(
    alpha: Sequence[float],
    cell_volumes_m3: Sequence[float],
    *,
    bounds: tuple[float, float] = ALPHA_BOUND_CANDIDATE,
) -> dict[str, float | int | bool]:
    if not alpha or len(alpha) != len(cell_volumes_m3):
        raise ValueError("alpha and positive cell-volume arrays must be nonempty and aligned")
    if (
        len(bounds) != 2
        or any(not math.isfinite(value) for value in bounds)
        or bounds[0] > bounds[1]
    ):
        raise ValueError("alpha bounds must be finite and ordered")
    if any((not math.isfinite(v) or v <= 0.0) for v in cell_volumes_m3):
        raise ValueError("cell volumes must be finite and positive")
    invalid = [i for i, value in enumerate(alpha) if not math.isfinite(value)]
    if invalid:
        raise ValueError("alpha contains non-finite values")
    outside = [i for i, value in enumerate(alpha) if value < bounds[0] or value > bounds[1]]
    out_of_range_volume = sum(cell_volumes_m3[i] for i in outside)
    if not math.isfinite(out_of_range_volume):
        raise ValueError("out-of-range cell volume sum must be finite")
    return {
        "minimum": min(alpha),
        "maximum": max(alpha),
        "out_of_range_cells": len(outside),
        "out_of_range_volume_m3": out_of_range_volume,
        "valid_at_this_stage": not outside,
    }


def alpha_correction_volumes(
    alpha_preclip: Sequence[float],
    alpha_postclip: Sequence[float],
    alpha_solver_final: Sequence[float],
    cell_volumes_m3: Sequence[float],
) -> dict[str, float]:
    arrays = (alpha_preclip, alpha_postclip, alpha_solver_final, cell_volumes_m3)
    if not arrays[0] or any(len(values) != len(arrays[0]) for values in arrays):
        raise ValueError("all alpha stages and cell volumes must have the same nonzero size")
    if any(not math.isfinite(value) for values in arrays for value in values):
        raise ValueError("all alpha values and cell volumes must be finite")
    if any(volume <= 0.0 for volume in cell_volumes_m3):
        raise ValueError("cell volumes must be positive")
    result = {
        "DeltaV_clip_m3": sum(
            volume * (post - pre)
            for pre, post, volume in zip(alpha_preclip, alpha_postclip, cell_volumes_m3)
        ),
        "DeltaV_later_m3": sum(
            volume * (final - post)
            for post, final, volume in zip(alpha_postclip, alpha_solver_final, cell_volumes_m3)
        ),
    }
    if any(not math.isfinite(value) for value in result.values()):
        raise ValueError("alpha correction volumes must remain finite")
    return result


def edge_level_crossings(
    points_yz_m: Sequence[Sequence[float]],
    alpha_values: Sequence[float],
    *,
    threshold: float = 0.1,
) -> list[tuple[float, float]]:
    """Find linear alpha crossings on polygon edges, preserving all components."""
    if len(points_yz_m) != len(alpha_values) or len(points_yz_m) < 2:
        raise ValueError(
            "polygon points and alpha values must align and contain at least two points"
        )
    if not math.isfinite(threshold):
        raise ValueError("contour threshold must be finite")
    if any(
        len(point) != 2 or any(not math.isfinite(float(coordinate)) for coordinate in point)
        for point in points_yz_m
    ):
        raise ValueError("polygon points must contain two finite coordinates")
    if any(not math.isfinite(value) for value in alpha_values):
        raise ValueError("contour alpha values must be finite")
    points = [(float(point[0]), float(point[1])) for point in points_yz_m]
    values = [float(value) for value in alpha_values]
    crossings: list[tuple[float, float]] = []
    count = len(points_yz_m)
    for i in range(count):
        j = (i + 1) % count
        p0 = points[i]
        p1 = points[j]
        a0 = values[i]
        a1 = values[j]
        if a0 == threshold and a1 == threshold:
            crossings.extend(((float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1]))))
        elif a0 == threshold:
            crossings.append((float(p0[0]), float(p0[1])))
        elif a1 == threshold:
            crossings.append((float(p1[0]), float(p1[1])))
        elif (a0 < threshold < a1) or (a1 < threshold < a0):
            fraction = (threshold - a0) / (a1 - a0)
            crossings.append(
                (
                    float(p0[0] + fraction * (p1[0] - p0[0])),
                    float(p0[1] + fraction * (p1[1] - p0[1])),
                )
            )
    return crossings


def contour_observable(
    crossings_yz_m: Iterable[Sequence[float]],
    *,
    station_x_over_dj: float,
    nozzle_y_m: float = 0.0,
    nozzle_diameter_m: float = NOZZLE_DIAMETER_M,
) -> dict[str, float | str]:
    if not all(math.isfinite(value) for value in (station_x_over_dj, nozzle_y_m)):
        raise ValueError("station and nozzle height must be finite")
    if not math.isfinite(nozzle_diameter_m) or nozzle_diameter_m <= 0.0:
        raise ValueError("nozzle diameter must be finite and positive")
    crossings = []
    for point in crossings_yz_m:
        if len(point) != 2 or any(not math.isfinite(float(value)) for value in point):
            raise ValueError("contour crossings must contain two finite coordinates")
        crossings.append((float(point[0]), float(point[1])))
    if not crossings:
        return {"status": "missing_station", "X": station_x_over_dj}
    y_min = min(y for y, _ in crossings)
    z_min = min(z for _, z in crossings)
    z_max = max(z for _, z in crossings)
    result = {
        "status": "sampled",
        "X": station_x_over_dj,
        "Y": (nozzle_y_m - y_min) / nozzle_diameter_m,
        "Z": (z_max - z_min) / nozzle_diameter_m,
        "crossing_count": len(crossings),
    }
    if any(not math.isfinite(value) for key, value in result.items() if key != "status"):
        raise ValueError("contour observables must be finite")
    return result


def _reference_rows() -> dict[str, list[dict[str, float]]]:
    path = ROOT_DIR / "data" / "derived" / "rouaix_e1_case1_fig13.csv"
    result: dict[str, list[dict[str, float]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            x = float(row["x_over_dj"])
            if x == 0.0:  # digitizer/calibration anchor, not scored evidence
                continue
            result.setdefault(row["observable"], []).append(
                {
                    "x": x,
                    "value": float(row["value_over_dj"]),
                    "sigma_value": float(row["sigma_value_over_dj"]),
                    "sigma_x": float(row["sigma_x_over_dj"]),
                }
            )
    return result


def figure13_reference_stations() -> dict[str, list[float]]:
    rows = _reference_rows()
    return {name: [row["x"] for row in values] for name, values in rows.items()}


def _source_bound_deltas(rows: Sequence[Mapping[str, float]]) -> list[float]:
    deltas: list[float] = []
    xs = [row["x"] for row in rows]
    ys = [row["value"] for row in rows]
    if len(rows) < 2 or any(
        not math.isfinite(value)
        for row in rows
        for value in (row["x"], row["value"], row["sigma_value"], row["sigma_x"])
    ):
        raise ValueError("reference rows must have at least two finite points")
    if any(right <= left for left, right in zip(xs, xs[1:])):
        raise ValueError("reference stations must be strictly increasing")
    if any(row["sigma_value"] < 0.0 or row["sigma_x"] < 0.0 for row in rows):
        raise ValueError("reference uncertainty bounds must be nonnegative")
    for index, row in enumerate(rows):
        slopes: list[float] = []
        if index > 0:
            slopes.append((ys[index] - ys[index - 1]) / (xs[index] - xs[index - 1]))
        if index + 1 < len(rows):
            slopes.append((ys[index + 1] - ys[index]) / (xs[index + 1] - xs[index]))
        slope = max(abs(value) for value in slopes)
        deltas.append(row["sigma_value"] + slope * row["sigma_x"])
    return deltas


def score_reference_curve(
    observable: str,
    simulation_by_x: Mapping[float, float],
) -> dict[str, float | str | int]:
    if observable not in {"penetration_y", "width_z"}:
        raise ValueError(f"unknown reference observable {observable!r}")
    if any(not math.isfinite(float(x)) for x in simulation_by_x):
        raise ValueError("simulation station keys must be finite")
    if any(not math.isfinite(float(value)) for value in simulation_by_x.values()):
        raise ValueError("simulation values must be finite")
    rows = _reference_rows()[observable]
    missing = [row["x"] for row in rows if row["x"] not in simulation_by_x]
    if missing:
        return {"status": "missing_station", "missing_x_over_dj": missing}
    expected = [row["value"] for row in rows]
    simulated = [simulation_by_x[row["x"]] for row in rows]
    deltas = _source_bound_deltas(rows)
    lower = [
        max(0.0, abs(sim - ref) - delta) for sim, ref, delta in zip(simulated, expected, deltas)
    ]
    upper = [abs(sim - ref) + delta for sim, ref, delta in zip(simulated, expected, deltas)]
    norm = 5.225 if observable == "penetration_y" else 3.257
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("score normalization must be finite and positive")
    nrmse_lower = math.sqrt(sum(value**2 for value in lower) / len(lower)) / norm
    nrmse_upper = math.sqrt(sum(value**2 for value in upper) / len(upper)) / norm
    if not math.isfinite(nrmse_lower) or not math.isfinite(nrmse_upper):
        raise ValueError("score result must be finite")
    return {
        "status": "scored_static_fixture",
        "station_count": len(rows),
        "normalization_range": norm,
        "NRMSE_lower": nrmse_lower,
        "NRMSE_upper": nrmse_upper,
    }


def _scalar_entry(text: str, name: str) -> float:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s+(?:uniform\s+)?([-+0-9.eE]+)\s*;", text)
    if not match:
        raise ValueError(f"missing scalar entry {name!r}")
    value = float(match.group(1))
    if not math.isfinite(value):
        raise ValueError(f"entry {name!r} must be finite")
    return value


def _vector_entry(text: str, name: str) -> tuple[float, float, float]:
    match = re.search(
        rf"(?m)^\s*{re.escape(name)}\s+(?:uniform\s+)?\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)\s*;",
        text,
    )
    if not match:
        raise ValueError(f"missing vector entry {name!r}")
    values = tuple(float(match.group(i)) for i in range(1, 4))
    if any(not math.isfinite(value) for value in values):
        raise ValueError(f"entry {name!r} must be finite")
    return values


def check_static_material_and_geometry(case_dir: Path = CASE_DIR) -> list[StaticCheck]:
    """Check candidate material, initial fields, inlet data, and mesh extents."""
    checks: list[StaticCheck] = []
    transport_path = case_dir / "constant" / "transportProperties"
    try:
        transport = _without_comments(transport_path.read_text(encoding="utf-8"))
        water = _named_block(transport, "water")
        air = _named_block(transport, "air")
        sigma = _scalar_entry(transport, "sigma")
        checks.extend(
            [
                StaticCheck(
                    "water_density_consistent_kg_m3",
                    math.isclose(_scalar_entry(water, "rho"), RHO_WATER_KG_M3, rel_tol=1e-12),
                    f"expected={RHO_WATER_KG_M3}",
                ),
                StaticCheck(
                    "water_nu_consistent_m2_s",
                    math.isclose(_scalar_entry(water, "nu"), WATER_NU_M2_S, rel_tol=1e-12),
                    f"expected={WATER_NU_M2_S}",
                ),
                StaticCheck(
                    "air_density_consistent_kg_m3",
                    math.isclose(_scalar_entry(air, "rho"), RHO_AIR_KG_M3, rel_tol=1e-12),
                    f"expected={RHO_AIR_KG_M3}",
                ),
                StaticCheck(
                    "air_nu_consistent_m2_s",
                    math.isclose(_scalar_entry(air, "nu"), AIR_NU_M2_S, rel_tol=1e-12),
                    f"expected={AIR_NU_M2_S}",
                ),
                StaticCheck(
                    "surface_tension_consistent_N_m",
                    math.isclose(sigma, SURFACE_TENSION_N_M, rel_tol=1e-12),
                    f"expected={SURFACE_TENSION_N_M}",
                ),
            ]
        )
    except (OSError, ValueError) as error:
        checks.append(StaticCheck("transport_properties_parse", False, str(error)))

    try:
        gravity = case_dir.joinpath("constant", "g").read_text(encoding="utf-8")
        checks.append(
            StaticCheck(
                "gravity_vector_and_dimensions",
                _vector_entry(gravity, "value") == GRAVITY_M_S2
                and "dimensions [0 1 -2 0 0 0 0]" in _without_comments(gravity),
                f"expected g={GRAVITY_M_S2} m/s^2",
            )
        )
        h_ref = case_dir.joinpath("constant", "hRef").read_text(encoding="utf-8")
        checks.append(
            StaticCheck(
                "pressure_reference_height_zero",
                re.search(r"(?m)^\s*value\s+0\s*;", _without_comments(h_ref)) is not None,
                "nozzle origin y=0 m",
            )
        )
    except (OSError, ValueError) as error:
        checks.append(StaticCheck("gravity_reference_parse", False, str(error)))

    try:
        _, _, velocity = field_dimensions_and_patch_types(case_dir / "0" / "U")
        _, _, alpha = field_dimensions_and_patch_types(case_dir / "0" / "alpha.water")
        nozzle_u = _named_block(_named_block(velocity, "boundaryField"), "nozzle")
        inlet_u = _named_block(_named_block(velocity, "boundaryField"), "gasInlet")
        nozzle_alpha = _named_block(_named_block(alpha, "boundaryField"), "nozzle")
        inlet_alpha = _named_block(_named_block(alpha, "boundaryField"), "gasInlet")
        checks.extend(
            [
                StaticCheck(
                    "water_inlet_velocity_m_s",
                    _vector_entry(nozzle_u, "value") == (0.0, -10.0, 0.0),
                    "reported Case 1 water vector (0,-10,0) m/s",
                ),
                StaticCheck(
                    "air_inlet_velocity_m_s",
                    _vector_entry(inlet_u, "value") == (70.0, 0.0, 0.0),
                    "reported Case 1 air vector (70,0,0) m/s",
                ),
                StaticCheck(
                    "water_inlet_phase_fraction",
                    _scalar_entry(nozzle_alpha, "value") == 1.0,
                    "alpha.water=1 at nozzle",
                ),
                StaticCheck(
                    "air_inlet_phase_fraction",
                    _scalar_entry(inlet_alpha, "value") == 0.0,
                    "alpha.water=0 at gas inlet",
                ),
            ]
        )
        alpha_internal = re.search(r"(?m)^\s*internalField\s+uniform\s+([-+0-9.eE]+)\s*;", alpha)
        checks.append(
            StaticCheck(
                "zero_initial_liquid_inventory_field",
                alpha_internal is not None and float(alpha_internal.group(1)) == 0.0,
                "uniform air-only seed; nozzle boundary is a source, not initial inventory",
            )
        )
    except (OSError, ValueError) as error:
        checks.append(StaticCheck("inlet_field_parse", False, str(error)))

    try:
        p_rgh = (case_dir / "0" / "p_rgh").read_text(encoding="utf-8")
        boundary = _direct_subblocks(_named_block(p_rgh, "boundaryField"))
        open_pressure = all(
            re.search(r"\btype\s+prghPressure\s*;", boundary[patch])
            and re.search(r"\bp\s+uniform\s+0\s*;", boundary[patch])
            and re.search(r"\brho\s+rho\s*;", boundary[patch])
            for patch in PATCHES[3:]
        )
        inlet_pressure = all(
            re.search(r"\btype\s+fixedFluxPressure\s*;", boundary[patch]) for patch in PATCHES[:3]
        )
        expression = _without_comments(
            (case_dir / "system" / "setExprFieldsDict").read_text(encoding="utf-8")
        )
        air_hydrostatic = (
            re.search(r"1\.18\s*\*\s*9\.81\s*\*\s*pos\(\)\.y\(\)", expression) is not None
        )
        checks.extend(
            [
                StaticCheck(
                    "open_pressure_static_reference_and_density",
                    open_pressure,
                    "prghPressure reconstructs p_gauge=0 using mixture rho",
                ),
                StaticCheck(
                    "velocity_inlet_wall_pressure_types",
                    inlet_pressure,
                    "fixedFluxPressure on velocity boundaries",
                ),
                StaticCheck(
                    "hydrostatic_air_initialization_available",
                    air_hydrostatic,
                    "setExprFields after mesh; zero p_rgh seed must be replaced before solver",
                ),
            ]
        )
    except (OSError, KeyError, ValueError) as error:
        checks.append(StaticCheck("pressure_field_parse", False, str(error)))

    try:
        geometry_dir = case_dir.parent / "geometry"
        domain = json.loads((geometry_dir / "domain.json").read_text(encoding="utf-8"))
        wall = domain["curved_aircraft_wall"]
        source_pdf_hash = domain.get("source", {}).get("pdf_sha256")
        figure_pdf_hash = wall.get("figure3_source_pdf_sha256")
        source_identity_valid = (
            source_pdf_hash == SOURCE_PDF_SHA256
            and figure_pdf_hash == SOURCE_PDF_SHA256
            and source_pdf_hash == figure_pdf_hash
        )
        checks.append(
            StaticCheck(
                "geometry_source_pdf_identity",
                source_identity_valid,
                "both generated source identities match the single pinned PDF hash",
            )
        )
        mesh_text = _without_comments(
            (case_dir / "system" / "blockMeshDict").read_text(encoding="utf-8")
        )
        dimensions = domain["domain"]
        bounds_match = (
            dimensions["x_min_m"] == -2.5
            and dimensions["x_max_m"] == 17.5
            and dimensions["vertical_height_m"] == 10.0
            and dimensions["top_span_m"] == 7.0
            and dimensions["bottom_span_m"] == 16.0
        )
        expected_blocks = (26 - 1) * (23 - 1)
        actual_blocks = len(re.findall(r"(?m)^\s*hex\s+\(", mesh_text))
        checks.append(
            StaticCheck(
                "blockmesh_domain_parameters_match_geometry",
                bounds_match,
                "x=[-2.5,17.5], height=10, top/bottom span=7/16 m",
            )
        )
        checks.append(
            StaticCheck(
                "blockmesh_structured_block_count",
                actual_blocks == expected_blocks,
                f"actual={actual_blocks}; expected={expected_blocks}",
            )
        )
        checks.append(
            StaticCheck(
                "mesh_utility_order_boundary_selection_before_refinement",
                domain["mesh"].get("utility_order")
                == ["blockMesh", "topoSet", "createPatch", "snappyHexMesh -overwrite"],
                f"actual={domain['mesh'].get('utility_order')}",
            )
        )
        with (geometry_dir / "top_wall_nodes.csv").open(newline="", encoding="utf-8") as handle:
            nodes = list(csv.DictReader(handle))
        node_classes_valid = bool(nodes) and all(
            row["classification"] == "inferred_assumed" for row in nodes
        )
        try:
            coordinates = [
                (float(row["x_m"]), float(row["z_m"]), float(row["y_m"])) for row in nodes
            ]
        except (KeyError, TypeError, ValueError):
            coordinates = []
        coordinates_finite = (
            bool(nodes)
            and len(coordinates) == len(nodes)
            and all(math.isfinite(value) for coordinate in coordinates for value in coordinate)
        )
        try:
            wall_amplitude = float(wall["amplitude_m"])
            y_allowance = wall_y_serialization_allowance(wall_amplitude)
        except (KeyError, TypeError, ValueError, OverflowError):
            wall_amplitude = math.nan
            y_allowance = math.nan
        node_bounds_valid = (
            coordinates_finite
            and math.isfinite(wall_amplitude)
            and all(
                -2.5 <= x_m <= 17.5
                and -3.5 <= z_m <= 3.5
                and 0.0 <= y_m <= wall_amplitude + y_allowance
                for x_m, z_m, y_m in coordinates
            )
        )
        checks.extend(
            [
                StaticCheck(
                    "top_wall_nodes_provenance",
                    node_classes_valid,
                    f"{len(nodes)} nodes are explicitly inferred/assumed",
                ),
                StaticCheck(
                    "top_wall_nodes_finite",
                    coordinates_finite,
                    "all x/z/y coordinates parse as finite values",
                ),
                StaticCheck(
                    "top_wall_nodes_within_top_footprint",
                    node_bounds_valid,
                    "x/z stay in the footprint; 0 <= y <= A with the documented 9g rounding allowance "
                    f"({y_allowance:.3g} m)",
                ),
            ]
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        checks.append(StaticCheck("mesh_geometry_static_parse", False, str(error)))
    return checks


def static_input_checks(case_dir: Path = CASE_DIR) -> list[StaticCheck]:
    checks = (
        check_case_fields(case_dir)
        + check_case_dictionaries(case_dir)
        + check_static_material_and_geometry(case_dir)
    )
    domain_path = case_dir.parent / "geometry" / "domain.json"
    try:
        domain = json.loads(domain_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return checks + [StaticCheck("domain_json", False, str(error))]
    top_width = float(domain["domain"]["top_span_m"])
    bottom_width = float(domain["domain"]["bottom_span_m"])
    height = float(domain["domain"]["vertical_height_m"])
    length = float(domain["domain"]["streamwise_length_m"])
    volume = length * height * (top_width + bottom_width) / 2.0
    angle = math.degrees(math.atan((bottom_width - top_width) / (2.0 * height)))
    checks.extend(
        [
            StaticCheck(
                "domain_volume_m3", math.isclose(volume, 2300.0, abs_tol=1e-9), f"{volume:.12g}"
            ),
            StaticCheck(
                "domain_opening_angle_deg",
                abs(angle - 25.0) < 1.0,
                f"derived={angle:.6f}; source nominal=25",
            ),
            StaticCheck(
                "source_frame",
                domain["coordinate_frame"]
                == {"x": "crossflow +", "y": "upward +", "z": "spanwise +"},
                json.dumps(domain["coordinate_frame"], sort_keys=True),
            ),
        ]
    )
    physics = nozzle_geometry()
    checks.append(
        StaticCheck(
            "nozzle_area_m2",
            math.isclose(float(physics["area_m2"]), 0.12566370614359174, rel_tol=1e-12),
            f"{physics['area_m2']:.12g}",
        )
    )
    checks.append(
        StaticCheck(
            "nozzle_flow_m3_s",
            math.isclose(float(physics["volume_flow_m3_s"]), 1.2566370614359172, rel_tol=1e-12),
            f"{physics['volume_flow_m3_s']:.12g}",
        )
    )
    expected_momentum_y = -RHO_WATER_KG_M3 * float(physics["area_m2"]) * 10.0**2
    checks.append(
        StaticCheck(
            "nozzle_momentum_N",
            math.isclose(
                float(physics["momentum_influx_N"][1]), expected_momentum_y, rel_tol=1e-14
            ),
            f"actual={physics['momentum_influx_N']}; derived={expected_momentum_y:.12g}",
        )
    )
    try:
        alpha_map = (PACKAGE_DIR / "ALPHA_CAPTURE_MAP.md").read_text(encoding="utf-8")
    except OSError as error:
        checks.append(StaticCheck("alpha_stage_source_names", False, str(error)))
    else:
        checks.append(
            StaticCheck(
                "alpha_stage_source_names",
                all(
                    name in alpha_map
                    for name in ("alpha_preclip", "alpha_postclip", "alpha_solver_final")
                ),
                "preclip/postclip/final source-order map is recorded",
            )
        )
    checks.append(
        StaticCheck(
            "station_list_excludes_zero_anchor",
            all(0.0 not in values for values in figure13_reference_stations().values()),
            "calibration anchor excluded; rows retained in source CSV",
        )
    )
    stations = figure13_reference_stations()
    checks.append(
        StaticCheck(
            "station_observable_names",
            set(stations) == {"penetration_y", "width_z"},
            f"observables={sorted(stations)}",
        )
    )
    try:
        control = _without_comments(
            (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
        )
        sampler = _named_block(_named_block(control, "functions"), "rouaixStations")
        sampler_shape_valid = all(
            re.search(pattern, sampler) is not None
            for pattern in (
                r"\btype\s+surfaces\s*;",
                r"\blibs\s*\(\s*sampling\s*\)\s*;",
                r"\binterpolationScheme\s+cellPoint\s*;",
                r"\bsurfaceFormat\s+vtk\s*;",
                r"\bfields\s*\(\s*alpha\.water\s*\)\s*;",
                r"\btimeStart\s+4\.50\s*;",
            )
        )
        checks.append(
            StaticCheck(
                "sampler_function_configuration",
                sampler_shape_valid,
                "surface sampler, cellPoint alpha.water, candidate timeStart=4.50 s",
            )
        )
        entries = {
            f"{observable}_X_{station:.3f}".replace(".", "p"): station
            for observable, values in stations.items()
            for station in values
        }
        entry_names = set(re.findall(r"(?m)^\s*([A-Za-z0-9_]+)\s*\{", sampler))
        checks.append(
            StaticCheck(
                "sampler_station_set",
                set(entries) <= entry_names and len(entries) == 30,
                f"entries={len(entry_names)}; expected={len(entries)}",
            )
        )
        plane_geometry_valid = True
        for entry_name, station in entries.items():
            body = _named_block(sampler, entry_name)
            point = _vector_entry(body, "point")
            normal = _vector_entry(body, "normal")
            triangulated = re.search(r"\btriangulate\s+true\s*;", body) is not None
            plane_geometry_valid &= (
                math.isclose(point[0], station * NOZZLE_DIAMETER_M, rel_tol=0.0, abs_tol=1e-12)
                and point[1:] == (0.0, 0.0)
                and normal == (1.0, 0.0, 0.0)
                and triangulated
            )
        checks.append(
            StaticCheck(
                "sampler_plane_positions_and_normals",
                plane_geometry_valid,
                "all reference stations are x-normal planes at X*d_j",
            )
        )
    except (OSError, ValueError) as error:
        checks.append(StaticCheck("sampler_static_parse", False, str(error)))
    return checks


def main() -> int:
    checks = static_input_checks()
    report = {
        "status": "static_preparation_only",
        "solver_or_mesh_executed": False,
        "image_id": IMAGE_ID,
        "source_pdf_sha256": SOURCE_PDF_SHA256,
        "checks": [check.__dict__ for check in checks],
        "all_pass": all(check.passed for check in checks),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
