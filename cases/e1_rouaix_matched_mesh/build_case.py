"""Build mesh-only OpenFOAM inputs for the exploratory Rouaix Case 1 mesh."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/derived/rouaix_e1_case1_fig13.csv"
DJ = 0.4
COUNTS = (179, 89, 90)
BASE_H = 0.112
FINE_RADIUS = 0.9
MEDIUM_RADIUS = 1.73
TAIL = (6.5, -6.0)
LAYER_COUNT = 5
LAYER_GROWTH = 1.1
LAYER_WIDTHS = tuple(LAYER_GROWTH**i for i in range(LAYER_COUNT))
LAYER_EDGE_FRACTIONS = tuple(
    sum(LAYER_WIDTHS[:n]) / sum(LAYER_WIDTHS[: n + 1]) for n in range(LAYER_COUNT - 1, 0, -1)
)


def lower_envelope() -> list[tuple[float, float]]:
    points = []
    with SOURCE.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["observable"] == "penetration_y":
                points.append((float(row["x_over_dj"]) * DJ, -float(row["value_over_dj"]) * DJ))
    if not points or points[-1][0] >= TAIL[0]:
        raise ValueError("Figure 13 penetration data cannot define the ROI guide")
    return [*points, TAIL]


def fine_guide(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    # This provisional upward buffer includes the jet body above the lower envelope.
    return [(x, y + 0.8 * min(1.0, x / 1.95)) for x, y in points]


def header(name: str) -> str:
    return (
        f"FoamFile\n{{\n version 2.0;\n format ascii;\n class dictionary;\n object {name};\n}}\n\n"
    )


def block_mesh_dict() -> str:
    nx, ny, nz = COUNTS
    return (
        header("blockMeshDict")
        + f"""convertToMeters 1;
vertices
(
    (-2.5 -10 -8) (17.5 -10 -8) (17.5 0 -3.5) (-2.5 0 -3.5)
    (-2.5 -10 8) (17.5 -10 8) (17.5 0 3.5) (-2.5 0 3.5)
);
blocks ( hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1) );
edges ();
boundary
(
    gasInlet {{ type patch; faces ((0 4 7 3)); }}
    downstreamOutlet {{ type patch; faces ((1 2 6 5)); }}
    aircraftWall {{ type wall; faces ((3 7 6 2)); }}
    bottomOutlet {{ type patch; faces ((0 1 5 4)); }}
    spanwiseMinus {{ type patch; faces ((0 3 2 1)); }}
    spanwisePlus {{ type patch; faces ((4 5 6 7)); }}
);
mergePatchPairs ();
"""
    )


def wall_owner_set_dict() -> str:
    """Select only hex cells owning aircraftWall faces and expose coverage set."""
    return (
        header("topoSetDict")
        + """actions
(
    { name wallFaces; type faceSet; action new; source patchToFace; patch aircraftWall; }
    { name wallOwnerCells; type cellSet; action new; source faceToCell;
      set wallFaces; option owner; }
    { name wallOwnerCells; type cellSet; action subset; source shapeToCell; shape hex; }
    { name hexWallFaces; type faceSet; action new; source cellToFace;
      set wallOwnerCells; option all; }
    { name hexWallFaces; type faceSet; action subset; source patchToFace; patch aircraftWall; }
);
"""
    )


def cylinder(name: str, a: tuple[float, float], b: tuple[float, float], radius: float) -> str:
    return (
        f"    {name}\n    {{ type searchableCylinder;\n"
        f"      point1 ({a[0]:.9g} {a[1]:.9g} 0);\n"
        f"      point2 ({b[0]:.9g} {b[1]:.9g} 0);\n"
        f"      radius {radius:.9g};\n    }}\n"
    )


def snappy_dict(stage: str) -> str:
    if stage not in {"pilot", "final"}:
        raise ValueError("stage must be pilot or final")
    lower = lower_envelope()
    guide = fine_guide(lower)
    fine_level, nozzle_level, max_cells, local_cells = (
        (2, 3, 6_000_000, 750_000) if stage == "pilot" else (3, 3, 22_000_000, 2_000_000)
    )
    geometries, regions = [], []
    for label, path, radius, level in (
        ("medium", lower, MEDIUM_RADIUS, 1),
        ("fine", guide, FINE_RADIUS, fine_level),
    ):
        for i, (a, b) in enumerate(zip(path, path[1:])):
            name = f"{label}{i:02d}"
            geometries.append(cylinder(name, a, b, radius))
            regions.append(f"        {name} {{ mode inside; levels ((1e15 {level})); }}")
    geometries.append("""    nozzleArea
    { type searchableCylinder; point1 (0 0 0); point2 (0 -0.16 0); radius 0.28; }
""")
    regions.append(f"        nozzleArea {{ mode inside; levels ((1e15 {nozzle_level})); }}")
    return (
        header("snappyHexMeshDict")
        + f"""castellatedMesh true;
snap false;
addLayers false;
geometry
{{
{"".join(geometries)}}}
castellatedMeshControls
{{
    maxLocalCells {local_cells};
    maxGlobalCells {max_cells};
    minRefinementCells 0;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 3;
    features ();
    refinementSurfaces {{}};
    resolveFeatureAngle 30;
    refinementRegions
    {{
{chr(10).join(regions)}
    }}
    locationInMesh (0.05 -1 0.05);
    allowFreeStandingZoneFaces true;
}}
snapControls {{ nSmoothPatch 3; tolerance 2; nSolveIter 30; nRelaxIter 5; }}
meshQualityControls
{{
    maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80;
    minVol 1e-13; minTetQuality 1e-15; minArea -1; minTwist 0.02;
    minDeterminant 0.001; minFaceWeight 0.05; minVolRatio 0.01;
    minTriangleTwist -1; nSmoothScale 4; errorReduction 0.75;
}}
debug 0;
writeFlags (scalarLevels);
mergeTolerance 1e-6;
"""
    )


def write_case(destination: Path, stage: str, experimental_wall_sets: bool = False) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    system = destination / "system"
    system.mkdir()
    (destination / "constant").mkdir()
    (system / "blockMeshDict").write_text(block_mesh_dict(), encoding="utf-8")
    (system / "snappyHexMeshDict").write_text(snappy_dict(stage), encoding="utf-8")
    (system / "topoSetDict").write_text(
        header("topoSetDict")
        + """actions
(
    { name nozzleFaces; type faceSet; action new; source patchToFace; patch aircraftWall; }
    { name nozzleFaces; type faceSet; action subset; source cylinderToFace;
      point1 (0 -0.1 0); point2 (0 0.1 0); radius 0.2; }
);
""",
        encoding="utf-8",
    )
    if experimental_wall_sets:
        (system / "wallOwnerSetDict").write_text(wall_owner_set_dict(), encoding="utf-8")
    (system / "createPatchDict").write_text(
        header("createPatchDict")
        + """pointSync false;
patches
(
    { name nozzle; patchInfo { type patch; inGroups (inlet); }
      constructFrom set; set nozzleFaces; }
);
""",
        encoding="utf-8",
    )
    (system / "decomposeParDict").write_text(
        header("decomposeParDict")
        + """numberOfSubdomains 10;
method simple;
simpleCoeffs { n (2 5 1); delta 0.001; }
distributed no;
roots ();
""",
        encoding="utf-8",
    )
    write_format = "binary" if stage == "final" else "ascii"
    (system / "controlDict").write_text(
        header("controlDict")
        + f"""application meshOnly;
startFrom startTime; startTime 0; stopAt endTime; endTime 0; deltaT 1;
writeControl timeStep; writeInterval 1; writeFormat {write_format}; writeCompression off;
writePrecision 16;
runTimeModifiable false;
""",
        encoding="utf-8",
    )
    (destination / "case.foam").touch()
    lower = lower_envelope()
    length = sum(math.dist(a, b) for a, b in zip(lower, lower[1:]))
    meta = {
        "stage": stage,
        "coordinate_frame": {"x": "crossflow +", "y": "upward +", "z": "spanwise +"},
        "domain_m": {"x": [-2.5, 17.5], "y": [-10, 0], "z_top": [-3.5, 3.5], "z_bottom": [-8, 8]},
        "base_counts": list(COUNTS),
        "base_spacing_m": [20 / COUNTS[0], 10 / COUNTS[1], 7 / COUNTS[2]],
        "levels": {
            "medium": 1,
            "fine": 2 if stage == "pilot" else 3,
            "nozzle_audit": 3,
        },
        "roi": {
            "source": "Fig4 center-plane visual bounds; Fig13 lower cloud envelope with inferred upward offset and tail",
            "fine_radius_m": FINE_RADIUS,
            "medium_radius_m": MEDIUM_RADIUS,
            "path_length_m": length,
            "tail_m": list(TAIL),
        },
        "nozzle": {
            "diameter_m": DJ,
            "area_target_m2": math.pi * (DJ / 2) ** 2,
            "normal_target": [0, 1, 0],
        },
        "wall_layers": {
            "paper_reported_count": 5,
            "paper_reported_growth": 1.1,
            "reproduced_count": 0,
            "status": "not_reproduced",
            "note": "The generated and selected Mac mesh is cast-only. Experimental layer trials are archived separately and rejected; no layer method is part of this case's default pipeline.",
        },
        "polyMesh_write_format": write_format,
        "paper": {
            "doi": "10.1016/j.ijmultiphaseflow.2023.104419",
            "source_pdf_sha256": "624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446",
        },
        "fig13_csv_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    }
    (destination / "mesh-input.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("pilot", "final"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--experimental-wall-sets",
        action="store_true",
        help="write the experimental wall-owner topoSet dictionary; not used by the default cast-only mesh",
    )
    args = parser.parse_args()
    write_case(args.out, args.stage, experimental_wall_sets=args.experimental_wall_sets)
    print(args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
