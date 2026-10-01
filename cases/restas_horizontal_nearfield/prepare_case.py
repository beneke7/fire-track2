#!/usr/bin/env python3
"""Generate a horizontal four-slot OpenFOAM near-field case."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

IMAGE = "opencfd/openfoam-default:2512"

DOMAIN = {
    "x": (0.0, 2.4),
    "y": (-1.275, 1.275),
    "z": (-0.025, 2.025),
}
Y_BREAKS = (-1.275, -1.025, -0.025, 0.025, 1.025, 1.275)
Z_BREAKS = (-0.025, 0.825, 0.975, 1.025, 1.175, 2.025)
SLOT_PATCHES = {
    (1, 1): "slot_01",
    (3, 1): "slot_02",
    (1, 3): "slot_03",
    (3, 3): "slot_04",
}
WATER_SPEED_M_S = 20.0
AIR_SPEED_M_S = 2.0
WATER_RHO = 1000.0
SLOT_AREA_M2 = 1.0 * 0.15
TOTAL_SLOT_AREA_M2 = 4.0 * SLOT_AREA_M2
WATER_VOLUME_FLOW_M3_S = WATER_SPEED_M_S * TOTAL_SLOT_AREA_M2
WATER_MASS_FLOW_KG_S = WATER_RHO * WATER_VOLUME_FLOW_M3_S
SURFACE_TENSION_N_M = 0.072
GRAVITY_M_S2 = (0.0, 0.0, -9.81)
MAX_DELTA_T_S = 3.75e-5


def foam_header(
    object_name: str, foam_class: str = "dictionary", location: str | None = None
) -> str:
    location_line = f'    location    "{location}";\n' if location else ""
    return (
        "FoamFile\n{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {foam_class};\n"
        f"{location_line}"
        f"    object      {object_name};\n"
        "}\n\n"
    )


def _vertex_index(i: int, j: int, k: int) -> int:
    return k * 2 * len(Y_BREAKS) + j * 2 + i


def _face(vertices: tuple[int, int, int, int]) -> str:
    return "(" + " ".join(str(vertex) for vertex in vertices) + ")"


def _block_mesh_dict(spacing_m: float) -> tuple[str, int, tuple[int, int, int]]:
    if not math.isfinite(spacing_m) or spacing_m not in (0.05, 0.025):
        raise ValueError(
            "mesh spacing must be 0.05 m for the short preflight or 0.025 m for the main cases"
        )

    vertices = []
    for z in Z_BREAKS:
        for y in Y_BREAKS:
            for x in DOMAIN["x"]:
                vertices.append(f"    ({x:.8g} {y:.8g} {z:.8g})")

    x_count = round((DOMAIN["x"][1] - DOMAIN["x"][0]) / spacing_m)
    y_counts = [round((b - a) / spacing_m) for a, b in zip(Y_BREAKS, Y_BREAKS[1:])]
    z_counts = [round((b - a) / spacing_m) for a, b in zip(Z_BREAKS, Z_BREAKS[1:])]
    if any(
        not math.isclose(count * spacing_m, b - a, abs_tol=1e-9)
        for count, (a, b) in zip(y_counts, zip(Y_BREAKS, Y_BREAKS[1:]))
    ):
        raise ValueError("y-segment lengths do not align with requested mesh spacing")
    if any(
        not math.isclose(count * spacing_m, b - a, abs_tol=1e-9)
        for count, (a, b) in zip(z_counts, zip(Z_BREAKS, Z_BREAKS[1:]))
    ):
        raise ValueError("z-segment lengths do not align with requested mesh spacing")

    blocks = []
    source_faces: dict[str, list[str]] = {name: [] for name in SLOT_PATCHES.values()}
    source_faces["plate"] = []
    x_outlet_faces: list[str] = []
    y_inlet_faces: list[str] = []
    y_outlet_faces: list[str] = []
    z_min_faces: list[str] = []
    z_max_faces: list[str] = []

    for kz in range(len(Z_BREAKS) - 1):
        for jy in range(len(Y_BREAKS) - 1):
            ids = (
                _vertex_index(0, jy, kz),
                _vertex_index(1, jy, kz),
                _vertex_index(1, jy + 1, kz),
                _vertex_index(0, jy + 1, kz),
                _vertex_index(0, jy, kz + 1),
                _vertex_index(1, jy, kz + 1),
                _vertex_index(1, jy + 1, kz + 1),
                _vertex_index(0, jy + 1, kz + 1),
            )
            blocks.append(
                "    hex ("
                + " ".join(map(str, ids))
                + ") "
                + f"({x_count} {y_counts[jy]} {z_counts[kz]}) simpleGrading (1 1 1)"
            )

            face_xmin = _face((ids[0], ids[4], ids[7], ids[3]))
            source_faces[SLOT_PATCHES.get((jy, kz), "plate")].append(face_xmin)
            x_outlet_faces.append(_face((ids[1], ids[2], ids[6], ids[5])))
            if jy == 0:
                y_inlet_faces.append(_face((ids[0], ids[1], ids[5], ids[4])))
            if jy == len(Y_BREAKS) - 2:
                y_outlet_faces.append(_face((ids[3], ids[7], ids[6], ids[2])))
            if kz == 0:
                z_min_faces.append(_face((ids[0], ids[3], ids[2], ids[1])))
            if kz == len(Z_BREAKS) - 2:
                z_max_faces.append(_face((ids[4], ids[5], ids[6], ids[7])))

    patches: list[str] = []
    for name, faces in source_faces.items():
        patch_type = "patch" if name.startswith("slot_") else "wall"
        patches.append(
            f"    {name}\n    {{\n        type {patch_type};\n        faces\n        (\n"
            + "\n".join(f"            {face}" for face in faces)
            + "\n        );\n    }\n"
        )
    for name, patch_type, faces in (
        ("xOutlet", "patch", x_outlet_faces),
        ("airInlet", "patch", y_inlet_faces),
        ("airOutlet", "patch", y_outlet_faces),
        ("zMin", "symmetryPlane", z_min_faces),
        ("zMax", "symmetryPlane", z_max_faces),
    ):
        patches.append(
            f"    {name}\n    {{\n        type {patch_type};\n        faces\n        (\n"
            + "\n".join(f"            {face}" for face in faces)
            + "\n        );\n    }\n"
        )

    nx = x_count
    ny = sum(y_counts)
    nz = sum(z_counts)
    cells = nx * ny * nz
    contents = (
        foam_header("blockMeshDict")
        + "scale 1;\n\nvertices\n(\n"
        + "\n".join(vertices)
        + "\n);\n\nblocks\n(\n"
        + "\n".join(blocks)
        + "\n);\n\nedges ();\n\nboundary\n(\n"
        + "\n".join(patches)
        + ");\n\nmergePatchPairs ();\n"
    )
    return contents, cells, (nx, ny, nz)


def _field(
    object_name: str, field_class: str, dimensions: str, internal: str, patches: dict[str, str]
) -> str:
    body = "\n".join(
        f"    {name}\n    {{\n{contents}\n    }}" for name, contents in patches.items()
    )
    return (
        foam_header(object_name, field_class)
        + f"dimensions {dimensions};\n\ninternalField uniform {internal};\n\nboundaryField\n{{\n{body}\n}}\n"
    )


def _write_turbulence_field(
    path: Path,
    name: str,
    dimensions: str,
    internal: float,
    source_value: float,
    air_value: float,
    wall_function: str,
) -> None:
    def value(number: float) -> str:
        return f"{number:.9g}"

    patches = {
        "slot_01": f"        type fixedValue;\n        value uniform {value(source_value)};",
        "slot_02": f"        type fixedValue;\n        value uniform {value(source_value)};",
        "slot_03": f"        type fixedValue;\n        value uniform {value(source_value)};",
        "slot_04": f"        type fixedValue;\n        value uniform {value(source_value)};",
        "plate": f"        type {wall_function};\n        value uniform {value(air_value)};",
        "airInlet": f"        type fixedValue;\n        value uniform {value(air_value)};",
        "xOutlet": f"        type inletOutlet;\n        inletValue uniform {value(air_value)};\n        value uniform {value(air_value)};",
        "airOutlet": f"        type inletOutlet;\n        inletValue uniform {value(air_value)};\n        value uniform {value(air_value)};",
        "zMin": "        type symmetryPlane;",
        "zMax": "        type symmetryPlane;",
    }
    if name == "nut":
        patches.update(
            {
                patch: "        type calculated;\n        value uniform 0;"
                for patch in (
                    "slot_01",
                    "slot_02",
                    "slot_03",
                    "slot_04",
                    "airInlet",
                    "xOutlet",
                    "airOutlet",
                )
            }
        )
    path.write_text(
        _field(name, "volScalarField", dimensions, value(internal), patches), encoding="utf-8"
    )


def _turbulence_values(
    intensity: float, speed: float, length_scale: float
) -> tuple[float, float, float]:
    k = 1.5 * (intensity * speed) ** 2
    epsilon = 0.09**0.75 * k**1.5 / length_scale
    omega = epsilon / (0.09 * k) if k > 0 else 0.0
    return k, epsilon, omega


def _base_fields(case_dir: Path) -> None:
    initial = case_dir / "0"
    base_u = {
        "slot_01": f"        type fixedValue;\n        value uniform ({WATER_SPEED_M_S:g} 0 0);",
        "slot_02": f"        type fixedValue;\n        value uniform ({WATER_SPEED_M_S:g} 0 0);",
        "slot_03": f"        type fixedValue;\n        value uniform ({WATER_SPEED_M_S:g} 0 0);",
        "slot_04": f"        type fixedValue;\n        value uniform ({WATER_SPEED_M_S:g} 0 0);",
        "plate": "        type noSlip;",
        "xOutlet": "        type pressureInletOutletVelocity;\n        value uniform (0 0 0);",
        "airInlet": f"        type fixedValue;\n        value uniform (0 {AIR_SPEED_M_S:g} 0);",
        "airOutlet": "        type pressureInletOutletVelocity;\n        value uniform (0 0 0);",
        "zMin": "        type symmetryPlane;",
        "zMax": "        type symmetryPlane;",
    }
    alpha = {
        "slot_01": "        type fixedValue;\n        value uniform 1;",
        "slot_02": "        type fixedValue;\n        value uniform 1;",
        "slot_03": "        type fixedValue;\n        value uniform 1;",
        "slot_04": "        type fixedValue;\n        value uniform 1;",
        "plate": "        type zeroGradient;",
        "xOutlet": "        type inletOutlet;\n        inletValue uniform 0;\n        value uniform 0;",
        "airInlet": "        type fixedValue;\n        value uniform 0;",
        "airOutlet": "        type inletOutlet;\n        inletValue uniform 0;\n        value uniform 0;",
        "zMin": "        type symmetryPlane;",
        "zMax": "        type symmetryPlane;",
    }
    pressure = {
        **{
            patch: "        type fixedFluxPressure;\n        value uniform 0;"
            for patch in ("slot_01", "slot_02", "slot_03", "slot_04", "plate", "airInlet")
        },
        "xOutlet": "        type fixedValue;\n        value uniform 0;",
        "airOutlet": "        type fixedValue;\n        value uniform 0;",
        "zMin": "        type symmetryPlane;",
        "zMax": "        type symmetryPlane;",
    }
    (initial / "U").write_text(
        _field("U", "volVectorField", "[0 1 -1 0 0 0 0]", f"(0 {AIR_SPEED_M_S:g} 0)", base_u),
        encoding="utf-8",
    )
    (initial / "alpha.water").write_text(
        _field("alpha.water", "volScalarField", "[0 0 0 0 0 0 0]", "0", alpha),
        encoding="utf-8",
    )
    (initial / "p_rgh").write_text(
        _field("p_rgh", "volScalarField", "[1 -1 -2 0 0 0 0]", "0", pressure),
        encoding="utf-8",
    )


def _write_model(
    case_dir: Path, model: str, ranks: int, spacing_m: float, end_time_s: float
) -> dict[str, Any]:
    if model not in {"laminar", "standard-ke", "realizable-ke", "k-omega-sst"}:
        raise ValueError("model must be laminar, standard-ke, realizable-ke, or k-omega-sst")
    if not math.isfinite(end_time_s) or not 0 < end_time_s <= 0.08:
        raise ValueError("end time must be in (0, 0.08] seconds")
    if ranks < 1 or ranks > 20:
        raise ValueError("MPI rank count must be between 1 and 20 on this 20-CPU host")

    for subdir in ("0", "constant", "system"):
        (case_dir / subdir).mkdir(parents=True, exist_ok=True)
    mesh_text, cell_count, cell_shape = _block_mesh_dict(spacing_m)
    (case_dir / "system" / "blockMeshDict").write_text(mesh_text, encoding="utf-8")
    source_k, source_epsilon, source_omega = _turbulence_values(0.05, WATER_SPEED_M_S, 0.15)
    air_k, air_epsilon, air_omega = _turbulence_values(0.05, AIR_SPEED_M_S, 0.05)
    _base_fields(case_dir)
    (case_dir / "constant" / "g").write_text(
        foam_header("g", "uniformDimensionedVectorField", "constant")
        + "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 -9.81);\n",
        encoding="utf-8",
    )
    (case_dir / "constant" / "transportProperties").write_text(
        foam_header("transportProperties", location="constant")
        + "phases (water air);\n\n"
        + "water { transportModel Newtonian; nu 1.0e-6; rho 1000; }\n"
        + "air { transportModel Newtonian; nu 1.48e-5; rho 1.225; }\n\n"
        + f"sigma {SURFACE_TENSION_N_M:g};\n",
        encoding="utf-8",
    )
    if model == "laminar":
        (case_dir / "constant" / "turbulenceProperties").write_text(
            foam_header("turbulenceProperties", location="constant") + "simulationType laminar;\n",
            encoding="utf-8",
        )
    else:
        ras_model = {
            "standard-ke": "kEpsilon",
            "realizable-ke": "realizableKE",
            "k-omega-sst": "kOmegaSST",
        }[model]
        (case_dir / "constant" / "turbulenceProperties").write_text(
            foam_header("turbulenceProperties", location="constant")
            + "density variable;\nsimulationType RAS;\n\nRAS\n{\n"
            + f"    RASModel {ras_model};\n    turbulence on;\n    printCoeffs on;\n}}\n",
            encoding="utf-8",
        )
        _write_turbulence_field(
            case_dir / "0" / "k", "k", "[0 2 -2 0 0 0 0]", air_k, source_k, air_k, "kqRWallFunction"
        )
        _write_turbulence_field(
            case_dir / "0" / "nut", "nut", "[0 2 -1 0 0 0 0]", 0.0, 0.0, 0.0, "nutkWallFunction"
        )
        if model in {"standard-ke", "realizable-ke"}:
            _write_turbulence_field(
                case_dir / "0" / "epsilon",
                "epsilon",
                "[0 2 -3 0 0 0 0]",
                air_epsilon,
                source_epsilon,
                air_epsilon,
                "epsilonWallFunction",
            )
            turbulence_name = "epsilon"
        else:
            _write_turbulence_field(
                case_dir / "0" / "omega",
                "omega",
                "[0 0 -1 0 0 0 0]",
                air_omega,
                source_omega,
                air_omega,
                "omegaWallFunction",
            )
            turbulence_name = "omega"

    delta_t_s = min(MAX_DELTA_T_S, spacing_m * 0.3 / WATER_SPEED_M_S)
    functions = (
        "functions\n{\n"
        "    waterVolume\n    {\n        type volFieldValue;\n        libs (fieldFunctionObjects);\n"
        "        writeControl timeStep;\n        writeInterval 10;\n        operation volIntegrate;\n"
        "        writeFields false;\n        fields (alpha.water);\n    }\n"
        "    liquidInterface\n    {\n        type surfaces;\n        libs (geometricVoF sampling);\n"
        "        writeControl writeTime;\n        surfaceFormat vtp;\n        fields (alpha.water U);\n"
        "        interpolationScheme cell;\n        surfaces\n        {\n            freeSurface\n            {\n"
        "                type interface;\n                interpolate false;\n            }\n        }\n    }\n"
        "}\n"
    )
    (case_dir / "system" / "controlDict").write_text(
        foam_header("controlDict", location="system")
        + "application interIsoFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\n"
        + f"endTime {end_time_s:.9g};\ndeltaT {delta_t_s:.9g};\n"
        + f"writeControl adjustableRunTime;\nwriteInterval {min(0.01, end_time_s):.9g};\npurgeWrite 0;\n"
        + "writeFormat binary;\nwritePrecision 8;\nwriteCompression off;\n"
        + "timeFormat fixed;\ntimePrecision 6;\nrunTimeModifiable no;\n"
        + f"adjustTimeStep yes;\nmaxCo 0.3;\nmaxAlphaCo 0.15;\nmaxDeltaT {MAX_DELTA_T_S:.9g};\n\n"
        + functions,
        encoding="utf-8",
    )
    turbulence_div = ""
    turbulence_grad = ""
    turbulence_solvers = ""
    wall_distance = ""
    if model != "laminar":
        terms = ["k", turbulence_name]
        if turbulence_name != "k":
            turbulence_div = (
                "\n".join(f"    div(rhoPhi,{name}) Gauss limitedLinear 1;" for name in terms) + "\n"
            )
            turbulence_grad = " ".join(f"grad({name}) Gauss linear;" for name in terms)
        if model == "k-omega-sst":
            # The OpenFOAM 2512 SST closure requires an explicit wall-distance
            # method in fvSchemes; meshWave is also used by its shipped VOF tutorials.
            wall_distance = "wallDist { method meshWave; }\n"
        turbulence_solvers = (
            '    "(k|epsilon|omega)" { solver smoothSolver; smoother GaussSeidel; '
            "tolerance 1e-8; relTol 0.1; nSweeps 2; maxIter 100; }\n"
            '    "(k|epsilon|omega)Final" { solver smoothSolver; smoother GaussSeidel; '
            "tolerance 1e-8; relTol 0; nSweeps 2; maxIter 100; }\n"
        )
    (case_dir / "system" / "fvSchemes").write_text(
        foam_header("fvSchemes", location="system")
        + "ddtSchemes { default Euler; }\n"
        + f"gradSchemes {{ default Gauss linear; {turbulence_grad} }}\n"
        + "divSchemes\n{\n    div(rhoPhi,U) Gauss limitedLinearV 1;\n"
        + turbulence_div
        + "    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;\n}\n"
        + "laplacianSchemes { default Gauss linear corrected; }\n"
        + "interpolationSchemes { default linear; }\n"
        + "snGradSchemes { default corrected; }\n"
        + wall_distance
        + "fluxRequired { default no; p_rgh; pcorr; alpha.water; }\n",
        encoding="utf-8",
    )
    solver_dict = (
        '    "alpha.water.*"\n    {\n        isoFaceTol 1e-6;\n'
        "        surfCellTol 1e-6;\n        nAlphaBounds 3;\n        snapTol 1e-12;\n"
        "        clip true;\n        reconstructionScheme isoAlpha;\n        writeFields true;\n"
        "        nAlphaSubCycles 1;\n        cAlpha 1;\n    }\n"
        '    "pcorr.*" { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0; }\n'
        "    p_rgh { solver GAMG; smoother DICGaussSeidel; tolerance 1e-9; relTol 0.05; }\n"
        "    p_rghFinal { $p_rgh; tolerance 1e-9; relTol 0; }\n"
        "    U { solver PBiCGStab; preconditioner DILU; tolerance 1e-6; relTol 0; }\n"
        + turbulence_solvers
    )
    (case_dir / "system" / "fvSolution").write_text(
        foam_header("fvSolution", location="system")
        + "solvers\n{\n"
        + solver_dict
        + "}\nPIMPLE\n{\n    momentumPredictor no;\n    nCorrectors 3;\n"
        + "    nOuterCorrectors 1;\n    nNonOrthogonalCorrectors 0;\n"
        + "    pRefCell 0;\n    pRefValue 0;\n}\n",
        encoding="utf-8",
    )
    (case_dir / "system" / "decomposeParDict").write_text(
        foam_header("decomposeParDict", location="system")
        + f"numberOfSubdomains {ranks};\nmethod simple;\ncoeffs {{ n ({ranks} 1 1); }}\n",
        encoding="utf-8",
    )

    analytic_volume_m3 = WATER_VOLUME_FLOW_M3_S * end_time_s
    analytic_mass_kg = WATER_MASS_FLOW_KG_S * end_time_s
    manifest = {
        "case_id": "RESTAS_HORIZONTAL_NEARFIELD",
        "evidence_label": "exploratory CPU VOF; hypothetical provisional source; not device reproduction or validation",
        "solver": "interIsoFoam",
        "openfoam_image": IMAGE,
        "model": model,
        "coordinate_frame": {
            "x": (
                "downstream along the +x water-jet velocity; the computational inlet is "
                "the x=0 plane with outward patch normal -x"
            ),
            "y": "cross-track horizontal axis; imposed background air flows +y",
            "z": "vertical upward; gravity acts -z",
        },
        "domain_bounds_m": DOMAIN,
        "mesh_spacing_m": spacing_m,
        "mesh_shape": {"nx": cell_shape[0], "ny": cell_shape[1], "nz": cell_shape[2]},
        "mesh_cells_expected": cell_count,
        "slot_count": 4,
        "slot_plane": (
            "x=0 vertical plane representing four distinct source outlets; their +x water "
            "velocity enters the domain whose patch outward normal is -x"
        ),
        "slot_dimensions_m_each": {"cross_track_y": 1.0, "vertical_z": 0.15},
        "slot_array_centers_m": {
            "y": [-0.525, 0.525],
            "z": [0.9, 1.1],
        },
        "slot_gaps_m": {"cross_track": 0.05, "vertical": 0.05},
        "slot_geometry_evidence": "Approximate 1 m by 0.10-0.15 m dimensions and close 2x2 outlet layout from track2_aerial_drop_experiment_plan.md; provisional, not measured built geometry.",
        "source_velocity_m_s_each": [WATER_SPEED_M_S, 0.0, 0.0],
        "source_velocity_evidence": "No local Restas source history, outlet discharge, or device record found; 20 m/s is an explicitly assumed high-speed diagnostic input.",
        "source_duration_s": end_time_s,
        "source_profile": "constant prescribed velocity over the simulated horizon; no shutoff segment",
        "outlet_area_total_m2": TOTAL_SLOT_AREA_M2,
        "analytic_source_volume_flow_m3_s": WATER_VOLUME_FLOW_M3_S,
        "analytic_source_mass_flow_kg_s": WATER_MASS_FLOW_KG_S,
        "analytic_source_volume_over_horizon_m3": analytic_volume_m3,
        "analytic_source_mass_over_horizon_kg": analytic_mass_kg,
        "background_air_velocity_m_s": [0.0, AIR_SPEED_M_S, 0.0],
        "airflow_evidence": "Small transverse air speed of 2 m/s selected as an explicit provisional ambient boundary/initial condition; not an aircraft or measured wind case.",
        "water": {"density_kg_m3": WATER_RHO, "kinematic_viscosity_m2_s": 1.0e-6},
        "air": {"density_kg_m3": 1.225, "kinematic_viscosity_m2_s": 1.48e-5},
        "surface_tension_N_m": SURFACE_TENSION_N_M,
        "gravity_m_s2": list(GRAVITY_M_S2),
        "time": {
            "end_s": end_time_s,
            "initial_delta_t_s": delta_t_s,
            "max_delta_t_s": MAX_DELTA_T_S,
            "adaptive": True,
            "max_Co": 0.3,
            "max_alpha_Co": 0.15,
        },
        "turbulence_model": model,
        "turbulence_assumption": (
            "For RANS cases, 5% inlet turbulence intensity with 0.15 m water-source and 0.05 m air-flow length scales; provisional boundary values."
            if model != "laminar"
            else "No modeled turbulence closure; laminar baseline retained as a closure sensitivity endpoint."
        ),
        "rans_boundary_values": {
            "source_k_m2_s2": source_k,
            "source_epsilon_m2_s3": source_epsilon,
            "source_omega_s1": source_omega,
            "air_k_m2_s2": air_k,
            "air_epsilon_m2_s3": air_epsilon,
            "air_omega_s1": air_omega,
        },
        "scope_limitations": [
            "no aircraft, rotor/wake, pressurized tank, measured discharge history, foam, parcels, evaporation, ground impact, fire, or deposition",
            "uniform 25 mm grid has six cells across the 0.15 m short slot axis and forty across the 1 m long axis; no mesh convergence study",
            "short open-domain near-field characterization only; turbulence models and boundary conditions are provisional",
            "not E1-E6 validation, built-system reproduction, suppression performance, or a design-gain result",
        ],
    }
    return manifest


def prepare_case(
    case_dir: Path, model: str, ranks: int, spacing_m: float, end_time_s: float
) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    inputs = _write_model(case_dir, model, ranks, spacing_m, end_time_s)
    (case_dir.parent / "inputs.json").write_text(
        json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return inputs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument(
        "--model", choices=("laminar", "standard-ke", "realizable-ke", "k-omega-sst"), required=True
    )
    parser.add_argument("--ranks", type=int, default=8)
    parser.add_argument("--spacing", type=float, choices=(0.025, 0.05), default=0.025)
    parser.add_argument("--end-time", type=float, default=0.02)
    options = parser.parse_args()
    details = prepare_case(
        options.case_dir, options.model, options.ranks, options.spacing, options.end_time
    )
    print(
        json.dumps(
            {
                "mesh_cells_expected": details["mesh_cells_expected"],
                "mesh_shape": details["mesh_shape"],
                "model": details["model"],
            },
            sort_keys=True,
        )
    )
