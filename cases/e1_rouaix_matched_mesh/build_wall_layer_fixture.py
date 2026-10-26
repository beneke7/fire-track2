"""Build a small aperture-and-wall case for testing owner-only layer cuts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_case import header, wall_owner_set_dict

COUNTS = (8, 2, 8)
NOZZLE_RADIUS = 1.6


def block_mesh_dict() -> str:
    nx, ny, nz = COUNTS
    return (
        header("blockMeshDict")
        + f"""convertToMeters 1;
vertices
(
    (-4 -2 -4) (4 -2 -4) (4 0 -4) (-4 0 -4)
    (-4 -2 4) (4 -2 4) (4 0 4) (-4 0 4)
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


def write_case(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    system = destination / "system"
    system.mkdir()
    (destination / "constant").mkdir()
    (system / "blockMeshDict").write_text(block_mesh_dict(), encoding="utf-8")
    (system / "topoSetDict").write_text(
        header("topoSetDict")
        + f"""actions
(
    {{ name nozzleFaces; type faceSet; action new; source patchToFace; patch aircraftWall; }}
    {{ name nozzleFaces; type faceSet; action subset; source cylinderToFace;
      point1 (0 -0.1 0); point2 (0 0.1 0); radius {NOZZLE_RADIUS}; }}
);
""",
        encoding="utf-8",
    )
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
    (system / "wallOwnerSetDict").write_text(wall_owner_set_dict(), encoding="utf-8")
    (system / "controlDict").write_text(
        header("controlDict")
        + """application meshOnly;
startFrom startTime; startTime 0; stopAt endTime; endTime 0; deltaT 1;
writeControl timeStep; writeInterval 1; writeFormat ascii; writeCompression off;
writePrecision 16;
runTimeModifiable false;
""",
        encoding="utf-8",
    )
    (destination / "case.foam").touch()
    (destination / "fixture-input.json").write_text(
        json.dumps(
            {
                "purpose": "Prove hex-owner-restricted aircraftWall cuts leave a multi-face nozzle aperture unchanged.",
                "counts": list(COUNTS),
                "domain_m": {"x": [-4, 4], "y": [-2, 0], "z": [-4, 4]},
                "base_cell_count": COUNTS[0] * COUNTS[1] * COUNTS[2],
                "expected_nozzle_faces": "more than one, checked from the created patch",
                "nozzle_cylinder_radius_m": NOZZLE_RADIUS,
                "owner_selection": "faceToCell set wallFaces option owner, subset shapeToCell type hex; regenerate before every cut",
                "layers": 5,
                "growth": 1.1,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    write_case(args.out)
    print(args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
