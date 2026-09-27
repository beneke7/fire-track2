"""Deterministically materialize the provisional static OpenFOAM case."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

try:
    from .static_preparation import (
        AIR_NU_M2_S,
        NOZZLE_DIAMETER_M,
        PACKAGE_DIR,
        RHO_AIR_KG_M3,
        RHO_WATER_KG_M3,
        SOURCE_PDF_SHA256,
        SURFACE_TENSION_N_M,
        WATER_NU_M2_S,
        static_input_checks,
    )
except ImportError:  # direct script invocation from this directory
    from static_preparation import (
        AIR_NU_M2_S,
        NOZZLE_DIAMETER_M,
        PACKAGE_DIR,
        RHO_AIR_KG_M3,
        RHO_WATER_KG_M3,
        SOURCE_PDF_SHA256,
        SURFACE_TENSION_N_M,
        WATER_NU_M2_S,
        static_input_checks,
    )

CASE = PACKAGE_DIR / "case"
GEOMETRY = PACKAGE_DIR / "geometry"
MANIFEST_NAME = "CASE_SHA256SUMS"
EXPECTED_GENERATED_FILES = (
    "case/0/U",
    "case/0/alpha.water",
    "case/0/epsilon",
    "case/0/k",
    "case/0/nut",
    "case/0/p_rgh",
    "case/constant/g",
    "case/constant/hRef",
    "case/constant/transportProperties",
    "case/constant/turbulenceProperties",
    "case/system/blockMeshDict",
    "case/system/controlDict",
    "case/system/createPatchDict",
    "case/system/fvSchemes",
    "case/system/fvSolution",
    "case/system/setExprFieldsDict",
    "case/system/snappyHexMeshDict",
    "case/system/topoSetDict",
    "geometry/domain.json",
    "geometry/top_wall_nodes.csv",
)
EXPECTED_GENERATED_DIRS = (
    "case",
    "case/0",
    "case/constant",
    "case/system",
    "geometry",
)
UTILITY_ORDER = ("blockMesh", "topoSet", "createPatch", "snappyHexMesh -overwrite")
DJ = NOZZLE_DIAMETER_M
X_NODES = (
    -2.5,
    -2.0,
    -1.5,
    -1.0,
    -0.5,
    -0.4,
    -0.3,
    -0.25,
    -0.2,
    -0.15,
    -0.1,
    -0.05,
    0.0,
    0.05,
    0.1,
    0.15,
    0.2,
    0.25,
    0.3,
    0.4,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    17.5,
)
Z_TOP_NODES = (
    -3.5,
    -2.0,
    -1.0,
    -0.5,
    -0.4,
    -0.3,
    -0.25,
    -0.2,
    -0.15,
    -0.1,
    -0.05,
    0.0,
    0.05,
    0.1,
    0.15,
    0.2,
    0.25,
    0.3,
    0.4,
    0.5,
    1.0,
    2.0,
    3.5,
)
TOP_HALF_SPAN_M = 3.5
BOTTOM_HALF_SPAN_M = 8.0
HEIGHT_M = 10.0
# The source schematic says the top wall is curved but does not dimension it.
# These are explicit, assumed visual-reconstruction parameters, not source data.
CURVE_AMPLITUDE_M = 0.2 * DJ
CURVE_LENGTH_X_M = 2.0 * DJ
CURVE_LENGTH_Z_M = 2.0 * DJ


def wall_y(x_m: float, z_m: float) -> float:
    radial = (x_m / CURVE_LENGTH_X_M) ** 2 + (z_m / CURVE_LENGTH_Z_M) ** 2
    return CURVE_AMPLITUDE_M * (1.0 - math.exp(-radial))


def vertex_index(i: int, j: int, top: bool) -> int:
    plane_size = len(X_NODES) * len(Z_TOP_NODES)
    return (plane_size if top else 0) + i * len(Z_TOP_NODES) + j


def _header(object_name: str, object_class: str = "dictionary") -> str:
    return f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2512                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {object_class};
    object      {object_name};
}}
"""


def _field_file(
    name: str,
    dimensions: str,
    internal: str,
    boundary: dict[str, tuple[str, str, str]],
    *,
    object_class: str = "volScalarField",
) -> str:
    blocks = []
    for patch, (patch_type, entries, value) in boundary.items():
        body = [f"        type            {patch_type};"]
        if entries:
            body.extend(f"        {entry}" for entry in entries.splitlines())
        if value:
            body.append(f"        value           {value};")
        blocks.append(f"    {patch}\n    {{\n" + "\n".join(body) + "\n    }")
    return (
        _header(name, object_class)
        + f"\ndimensions      {dimensions};\n\ninternalField   {internal};\n\nboundaryField\n{{\n"
        + "\n\n".join(blocks)
        + "\n}\n"
    )


def make_fields(case_dir: Path = CASE) -> None:
    patches = (
        "nozzle",
        "gasInlet",
        "aircraftWall",
        "downstreamOutlet",
        "bottomOutlet",
        "spanwiseMinus",
        "spanwisePlus",
    )
    opens = patches[3:]

    U = {
        "nozzle": ("fixedValue", "", "uniform (0 -10 0)"),
        "gasInlet": ("fixedValue", "", "uniform (70 0 0)"),
        "aircraftWall": ("noSlip", "", ""),
    }
    alpha = {
        "nozzle": ("fixedValue", "", "uniform 1"),
        "gasInlet": ("fixedValue", "", "uniform 0"),
        "aircraftWall": (
            "constantAlphaContactAngle",
            "theta0          90;\nlimit           gradient;",
            "uniform 0",
        ),
    }
    p_rgh = {
        "nozzle": ("fixedFluxPressure", "", "uniform 0"),
        "gasInlet": ("fixedFluxPressure", "", "uniform 0"),
        "aircraftWall": ("fixedFluxPressure", "", "uniform 0"),
    }
    k = {
        "nozzle": ("fixedValue", "", "uniform 0.015"),
        "gasInlet": ("fixedValue", "", "uniform 0.735"),
        "aircraftWall": ("kqRWallFunction", "", "uniform 0"),
    }
    epsilon = {
        "nozzle": ("fixedValue", "", "uniform 0.0107810420"),
        "gasInlet": ("fixedValue", "", "uniform 3.6978974178"),
        "aircraftWall": ("epsilonWallFunction", "", "uniform 0"),
    }
    # D-NUT-BC (provisional): calculated seeds on prescribed velocity inlets;
    # open boundaries use zero reverse-flow nut through inletOutlet.
    nut = {
        "nozzle": ("calculated", "", "uniform 0"),
        "gasInlet": ("calculated", "", "uniform 0"),
        "aircraftWall": ("nutkWallFunction", "", "uniform 0"),
    }
    for patch in opens:
        U[patch] = (
            "pressureInletOutletVelocity",
            "phi             phi;\ntangentialVelocity uniform (70 0 0);",
            "uniform (70 0 0)",
        )
        alpha[patch] = ("inletOutlet", "inletValue      uniform 0;", "uniform 0")
        p_rgh[patch] = (
            "prghPressure",
            "p               uniform 0;\nrho             rho;",
            "uniform 0",
        )
        k[patch] = ("inletOutlet", "inletValue      uniform 0.735;", "uniform 0")
        epsilon[patch] = (
            "inletOutlet",
            "inletValue      uniform 3.6978974178;",
            "uniform 0",
        )
        nut[patch] = ("inletOutlet", "inletValue      uniform 0;", "uniform 0")

    files = {
        "U": _field_file(
            "U", "[0 1 -1 0 0 0 0]", "uniform (70 0 0)", U, object_class="volVectorField"
        ),
        "alpha.water": _field_file("alpha.water", "[0 0 0 0 0 0 0]", "uniform 0", alpha),
        # This zero seed is overwritten by setExprFieldsDict after meshing and
        # before any solver run; it is not the accepted hydrostatic field.
        "p_rgh": _field_file("p_rgh", "[1 -1 -2 0 0 0 0]", "uniform 0", p_rgh),
        "k": _field_file("k", "[0 2 -2 0 0 0 0]", "uniform 0.735", k),
        "epsilon": _field_file("epsilon", "[0 2 -3 0 0 0 0]", "uniform 3.6978974178", epsilon),
        "nut": _field_file("nut", "[0 2 -1 0 0 0 0]", "uniform 0", nut),
    }
    for name, text in files.items():
        (case_dir / "0" / name).write_text(text, encoding="utf-8")


def make_block_mesh_dict() -> str:
    nx, nz = len(X_NODES), len(Z_TOP_NODES)
    out = [_header("blockMeshDict"), "convertToMeters 1;", "", "vertices", "("]
    for top in (False, True):
        for x in X_NODES:
            for z_top in Z_TOP_NODES:
                z = z_top if top else z_top * (BOTTOM_HALF_SPAN_M / TOP_HALF_SPAN_M)
                y = wall_y(x, z_top) if top else -HEIGHT_M
                out.append(f"    ({x:.9g} {y:.9g} {z:.9g})")
    out.extend([");", "", "blocks", "("])
    for i in range(nx - 1):
        for j in range(nz - 1):
            v0 = vertex_index(i, j, False)
            v1 = vertex_index(i + 1, j, False)
            v2 = vertex_index(i + 1, j, True)
            v3 = vertex_index(i, j, True)
            v4 = vertex_index(i, j + 1, False)
            v5 = vertex_index(i + 1, j + 1, False)
            v6 = vertex_index(i + 1, j + 1, True)
            v7 = vertex_index(i, j + 1, True)
            out.append(
                f"    hex ({v0} {v1} {v2} {v3} {v4} {v5} {v6} {v7}) (1 20 1) simpleGrading (1 1 1)"
            )
    out.extend([");", "", "edges", "(", ");", "", "boundary", "("])
    patch_faces: dict[str, list[str]] = {
        name: []
        for name in (
            "gasInlet",
            "aircraftWall",
            "downstreamOutlet",
            "bottomOutlet",
            "spanwiseMinus",
            "spanwisePlus",
        )
    }
    for j in range(nz - 1):
        patch_faces["gasInlet"].append(
            f"({vertex_index(0, j, False)} {vertex_index(0, j + 1, False)} {vertex_index(0, j + 1, True)} {vertex_index(0, j, True)})"
        )
        i = nx - 2
        patch_faces["downstreamOutlet"].append(
            f"({vertex_index(i + 1, j, False)} {vertex_index(i + 1, j, True)} {vertex_index(i + 1, j + 1, True)} {vertex_index(i + 1, j + 1, False)})"
        )
    for i in range(nx - 1):
        for j in range(nz - 1):
            patch_faces["bottomOutlet"].append(
                f"({vertex_index(i, j, False)} {vertex_index(i + 1, j, False)} {vertex_index(i + 1, j + 1, False)} {vertex_index(i, j + 1, False)})"
            )
            patch_faces["aircraftWall"].append(
                f"({vertex_index(i, j, True)} {vertex_index(i, j + 1, True)} {vertex_index(i + 1, j + 1, True)} {vertex_index(i + 1, j, True)})"
            )
    for i in range(nx - 1):
        patch_faces["spanwiseMinus"].append(
            f"({vertex_index(i, 0, False)} {vertex_index(i, 0, True)} {vertex_index(i + 1, 0, True)} {vertex_index(i + 1, 0, False)})"
        )
        j = nz - 2
        patch_faces["spanwisePlus"].append(
            f"({vertex_index(i, j + 1, False)} {vertex_index(i + 1, j + 1, False)} {vertex_index(i + 1, j + 1, True)} {vertex_index(i, j + 1, True)})"
        )
    for name, faces in patch_faces.items():
        patch_type = "wall" if name == "aircraftWall" else "patch"
        out.extend(
            [f"    {name}", "    {", f"        type {patch_type};", "        faces", "        ("]
        )
        out.extend(f"            {face}" for face in faces)
        out.extend(["        );", "    }"])
    out.extend([");", "", "mergePatchPairs", "(", ");", ""])
    return "\n".join(out)


def station_sets() -> dict[str, list[float]]:
    return {
        "penetration_y": [round(0.25 * i, 3) for i in range(1, 20)] + [4.875],
        "width_z": [round(0.25 * i, 3) for i in range(1, 11)],
    }


def make_functions() -> str:
    entries = []
    for family, stations in station_sets().items():
        for station in stations:
            x = station * DJ
            suffix = f"{station:.3f}".replace(".", "p")
            entries.append(
                f"""        {family}_X_{suffix}
        {{
            type            plane;
            point           ({x:.9g} 0 0);
            normal          (1 0 0);
            interpolate     true;
            triangulate     true;
        }}"""
            )
    return "\n".join(
        [
            "    rouaixStations",
            "    {",
            "        type                surfaces;",
            "        libs                (sampling);",
            "        writeControl        writeTime;",
            "        timeStart           4.50;",
            "        interpolationScheme cellPoint; // OpenFOAM interpolationCellPoint",
            "        surfaceFormat       vtk;",
            "        fields              (alpha.water);",
            "        surfaces",
            "        (",
            *entries,
            "        );",
            "    }",
        ]
    )


def _assert_output_tree_is_known(case_dir: Path, geometry_dir: Path, package_dir: Path) -> None:
    """Refuse unknown paths before regeneration; never delete or overwrite them."""
    for directory in (package_dir, case_dir, geometry_dir):
        if directory.is_symlink():
            raise ValueError(f"refusing to regenerate through symlink directory: {directory}")
    expected_files = {package_dir / relative for relative in EXPECTED_GENERATED_FILES}
    expected_dirs = {package_dir / relative for relative in EXPECTED_GENERATED_DIRS}
    expected_dirs.add(package_dir)
    manifest_path = package_dir / MANIFEST_NAME
    expected_files.add(manifest_path)
    for root in (case_dir, geometry_dir):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"refusing to regenerate through symlink: {path}")
            if path.is_dir():
                if path not in expected_dirs:
                    raise ValueError(f"unexpected generated directory: {path}")
            elif path.is_file():
                if path not in expected_files:
                    raise ValueError(f"refusing to overwrite unknown file: {path}")
                if path.stat().st_nlink > 1:
                    raise ValueError(f"refusing to overwrite multiply-linked output file: {path}")
            else:
                raise ValueError(f"unexpected non-file output path: {path}")
    if manifest_path.is_symlink():
        raise ValueError(f"refusing to overwrite symlink manifest path: {manifest_path}")
    if manifest_path.exists() and not manifest_path.is_file():
        raise ValueError(f"refusing to overwrite non-file manifest path: {manifest_path}")
    if manifest_path.is_file() and manifest_path.stat().st_nlink > 1:
        raise ValueError(f"refusing to overwrite multiply-linked manifest: {manifest_path}")


def make_case_files(*, package_dir: Path | None = None) -> None:
    package_dir = PACKAGE_DIR if package_dir is None else package_dir
    case_dir = package_dir / "case"
    geometry_dir = package_dir / "geometry"
    _assert_output_tree_is_known(case_dir, geometry_dir, package_dir)
    for path in (case_dir / "0", case_dir / "constant", case_dir / "system", geometry_dir):
        path.mkdir(parents=True, exist_ok=True)
    make_fields(case_dir)
    (case_dir / "constant" / "g").write_text(
        _header("g", "uniformDimensionedVectorField")
        + "\ndimensions [0 1 -2 0 0 0 0];\nvalue (0 -9.81 0);\n",
        encoding="utf-8",
    )
    (case_dir / "constant" / "hRef").write_text(
        _header("hRef", "uniformDimensionedScalarField")
        + "\ndimensions [0 1 0 0 0 0 0];\nvalue 0; // nozzle reference height (m)\n",
        encoding="utf-8",
    )
    (case_dir / "constant" / "transportProperties").write_text(
        _header("transportProperties")
        + f"""
phases (water air);
water
{{
    transportModel Newtonian;
    nu {WATER_NU_M2_S:.15g};
    rho {RHO_WATER_KG_M3:.9g};
}}
air
{{
    transportModel Newtonian;
    nu {AIR_NU_M2_S:.15g};
    rho {RHO_AIR_KG_M3:.9g};
}}
sigma {SURFACE_TENSION_N_M:.9g};
""",
        encoding="utf-8",
    )
    (case_dir / "constant" / "turbulenceProperties").write_text(
        _header("turbulenceProperties")
        + """
// Provisional variable-density selection pairs with rhoPhi turbulence schemes.
// The pinned v2512 selector otherwise defaults to uniform density and phi.
density variable;
simulationType RAS;
RAS
{
    RASModel realizableKE;
    turbulence on;
    printCoeffs on;
}
""",
        encoding="utf-8",
    )
    (case_dir / "system" / "blockMeshDict").write_text(make_block_mesh_dict(), encoding="utf-8")
    (case_dir / "system" / "topoSetDict").write_text(
        _header("topoSetDict")
        + """
actions
(
    {
        name nozzleFaces;
        type faceSet;
        action new;
        source patchToFace;
        patch aircraftWall;
    }
    {
        name nozzleFaces;
        type faceSet;
        action subset;
        source cylinderToFace;
        point1 (0 -0.1 0);
        point2 (0 0.1 0);
        radius 0.2;
    }
);
""",
        encoding="utf-8",
    )
    (case_dir / "system" / "createPatchDict").write_text(
        _header("createPatchDict")
        + """
pointSync false;
patches
(
    {
        name nozzle;
        patchInfo { type patch; inGroups (inlet); }
        constructFrom set;
        set nozzleFaces;
    }
);
""",
        encoding="utf-8",
    )
    (case_dir / "system" / "snappyHexMeshDict").write_text(
        _header("snappyHexMeshDict")
        + """
castellatedMesh true;
snap false;
addLayers true;
geometry
{
    nearNozzle
    {
        type searchableBox;
        min (-1 -3 -1);
        max (3 0.5 1);
    }
}
castellatedMeshControls
{
    maxLocalCells 1000000;
    maxGlobalCells 3000000;
    minRefinementCells 0;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 2;
    features ();
    refinementSurfaces {};
    resolveFeatureAngle 30;
    refinementRegions
    {
        nearNozzle { mode inside; levels ((1e15 2)); }
    }
    locationInMesh (0.05 -1 0.05);
    allowFreeStandingZoneFaces true;
}
snapControls
{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 5;
}
addLayersControls
{
    relativeSizes true;
    layers { aircraftWall { nSurfaceLayers 5; } }
    expansionRatio 1.1;
    finalLayerThickness 0.30;
    minThickness 0.05;
    nGrow 0;
    featureAngle 60;
    slipFeatureAngle 30;
    nRelaxIter 3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
}
meshQualityControls
{
    maxNonOrtho 65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave 80;
    minVol 1e-13;
    minTetQuality 1e-15;
    minArea -1;
    minTwist 0.02;
    minDeterminant 0.001;
    minFaceWeight 0.02;
    minVolRatio 0.01;
    minTriangleTwist -1;
    nSmoothScale 4;
    errorReduction 0.75;
}
debug 0;
mergeTolerance 1e-6;
""",
        encoding="utf-8",
    )
    (case_dir / "system" / "setExprFieldsDict").write_text(
        _header("setExprFieldsDict")
        + """
expressions
(
    hydrostaticAirPressure
    {
        field p_rgh;
        dimensions [1 -1 -2 0 0 0 0];
        expression #{ 1.18*9.81*pos().y() #};
    }
);
""",
        encoding="utf-8",
    )
    (case_dir / "system" / "fvSchemes").write_text(
        _header("fvSchemes")
        + """
ddtSchemes { default Euler; }
gradSchemes
{
    default Gauss linear;
    grad(U) Gauss linear;
    grad(k) Gauss linear;
    grad(epsilon) Gauss linear;
}
divSchemes
{
    default none;
    div(rhoPhi,U) Gauss linearUpwind grad(U);
    div(rhoPhi,k) Gauss linearUpwind grad(k);
    div(rhoPhi,epsilon) Gauss linearUpwind grad(epsilon);
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
""",
        encoding="utf-8",
    )
    (case_dir / "system" / "fvSolution").write_text(
        _header("fvSolution")
        + """
solvers
{
    p_rgh { solver GAMG; tolerance 1e-8; relTol 0.01; smoother DICGaussSeidel; maxIter 100; }
    p_rghFinal { $p_rgh; relTol 0; }
    "(U|k|epsilon)"
    {
        solver smoothSolver;
        smoother GaussSeidel;
        tolerance 1e-8;
        relTol 0.1;
        nSweeps 2;
        maxIter 100;
    }
    "(U|k|epsilon)Final"
    {
        solver smoothSolver;
        smoother GaussSeidel;
        tolerance 1e-8;
        relTol 0;
        nSweeps 2;
        maxIter 100;
    }
    "alpha.*"
    {
        isoFaceTol 1e-10;
        surfCellTol 1e-10;
        nAlphaBounds 5;
        snapTol 0;
        clip true;
        cAlpha 1;
        nAlphaSubCycles 1;
        reconstructionScheme isoAlpha;
    }
}
PIMPLE
{
    momentumPredictor yes;
    nOuterCorrectors 1;
    nCorrectors 3;
    nNonOrthogonalCorrectors 0;
    pRefCell 0;
    pRefValue 0;
}
""",
        encoding="utf-8",
    )
    (case_dir / "system" / "controlDict").write_text(
        _header("controlDict")
        + """
application interIsoFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime 5;
deltaT 0.001;
writeControl runTime;
writeInterval 0.01;
purgeWrite 0;
writeFormat ascii;
writePrecision 12;
writeCompression off;
timeFormat general;
timePrecision 8;
runTimeModifiable false;
functions
{
"""
        + make_functions()
        + "\n}\n",
        encoding="utf-8",
    )

    domain = {
        "case": "Rouaix et al. 2023 E1 Reference Case 1; static preparation only",
        "source": {
            "doi": "10.1016/j.ijmultiphaseflow.2023.104419",
            "pdf_url": "https://hal.science/hal-04098260v1/file/Rouaix_28516.pdf",
            "pdf_sha256": SOURCE_PDF_SHA256,
            "locations": [
                "PDF p. 4 / article p. 3, Fig. 1",
                "PDF p. 5 / article p. 4, Table 3",
                "PDF p. 7 / article p. 6, Fig. 3 and section 3.2",
            ],
        },
        "coordinate_frame": {"x": "crossflow +", "y": "upward +", "z": "spanwise +"},
        "nozzle_origin_m": [0.0, 0.0, 0.0],
        "domain": {
            "x_min_m": -2.5,
            "x_max_m": 17.5,
            "streamwise_length_m": 20.0,
            "top_span_m": 7.0,
            "bottom_span_m": 16.0,
            "vertical_height_m": 10.0,
            "nominal_opening_angle_deg": 25.0,
            "gas_inlet_to_nozzle_m": 2.5,
            "nominal_trapezoid_volume_m3": 2300.0,
        },
        "curved_aircraft_wall": {
            "classification": "assumed analytic wall; not source-derived geometry",
            "citation": "Rouaix PDF p. 7 / article p. 6, Fig. 3 and section 3.2",
            "figure3_trace_status": "not_quantitatively_defensible_from_source_schematic",
            "figure3_source_pdf_sha256": SOURCE_PDF_SHA256,
            "figure3_rendered_page_sha256": "12cd10ef2d1cb06b397dcc2fa81e83067a83bf8f7be5eca64a2d302fa2291726",
            "profile": "y=A*(1-exp(-((x/Lx)^2+(z/Lz)^2))) with nozzle center y=0",
            "amplitude_m": CURVE_AMPLITUDE_M,
            "length_x_m": CURVE_LENGTH_X_M,
            "length_z_m": CURVE_LENGTH_Z_M,
            "parameter_classification": "assumed SI reconstruction parameters; not dimensioned by the paper",
            "mesh_representation": "piecewise bilinear top faces through top_wall_nodes.csv; no aircraft CAD is claimed",
        },
        "patch_map": {
            "gasInlet": "x=-2.5 m; prescribed +x air",
            "nozzle": "aircraftWall boundary faces intersected with the cylinderToFace face-centre selection of radius 0.2 m; actual mesh area remains to be measured",
            "aircraftWall": "curved top boundary; no-slip",
            "downstreamOutlet": "x=17.5 m; atmospheric pressure outlet",
            "bottomOutlet": "y=-10 m; atmospheric pressure outlet",
            "spanwiseMinus": "negative span side; atmospheric pressure outlet",
            "spanwisePlus": "positive span side; atmospheric pressure outlet",
        },
        "mesh": {
            "utility_order": list(UTILITY_ORDER),
            "background_cells": "1x20x1 cells per structured block; not meshed or checked",
            "near_nozzle_refinement_level": 2,
            "layer_candidate": {
                "count": 5,
                "expansion_ratio": 1.1,
                "thickness_parameters": "assumed; not paper-recovered",
            },
            "family": "blockMesh plus snappyHexMesh hex-dominant refinement; source uses unstructured polyhedra",
        },
    }
    (geometry_dir / "domain.json").write_text(
        json.dumps(domain, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (geometry_dir / "top_wall_nodes.csv").open("w", encoding="utf-8") as handle:
        handle.write("x_m,z_m,y_m,classification\n")
        for x in X_NODES:
            for z in Z_TOP_NODES:
                handle.write(f"{x:.9g},{z:.9g},{wall_y(x, z):.9g},inferred_assumed\n")

    records = []
    for relative_name in EXPECTED_GENERATED_FILES:
        path = package_dir / relative_name
        if not path.is_file():
            raise ValueError(f"generator did not produce expected file: {path}")
        records.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative_name}")
    (package_dir / MANIFEST_NAME).write_text("\n".join(records) + "\n", encoding="utf-8")


def check_generated_fields() -> list[str]:
    failures = [check.detail for check in static_input_checks() if not check.passed]
    required = (
        CASE / "system" / "blockMeshDict",
        CASE / "system" / "topoSetDict",
        CASE / "system" / "createPatchDict",
        CASE / "system" / "snappyHexMeshDict",
        CASE / "system" / "controlDict",
        CASE / "system" / "setExprFieldsDict",
    )
    failures.extend(f"missing {path}" for path in required if not path.is_file())
    actual_files = {
        path.relative_to(PACKAGE_DIR).as_posix()
        for root in (CASE, GEOMETRY)
        for path in root.rglob("*")
        if path.is_file()
    }
    expected_files = set(EXPECTED_GENERATED_FILES)
    if actual_files != expected_files:
        failures.append(
            "generated file set mismatch: "
            f"missing={sorted(expected_files - actual_files)}; extra={sorted(actual_files - expected_files)}"
        )
    manifest_path = PACKAGE_DIR / MANIFEST_NAME
    if manifest_path.is_file():
        manifest_lines = manifest_path.read_text(encoding="utf-8").splitlines()
        expected_manifest = [
            f"{hashlib.sha256((PACKAGE_DIR / relative).read_bytes()).hexdigest()}  {relative}"
            for relative in EXPECTED_GENERATED_FILES
        ]
        if manifest_lines != expected_manifest:
            failures.append("CASE_SHA256SUMS does not match the exact generated file set and bytes")
    else:
        failures.append(f"missing {manifest_path}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help="write deterministic provisional input files"
    )
    args = parser.parse_args()
    if args.write:
        make_case_files()
    failures = check_generated_fields()
    print("static case inputs structurally consistent" if not failures else "\n".join(failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
