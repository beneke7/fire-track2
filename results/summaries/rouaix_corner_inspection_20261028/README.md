# Rouaix coarse all-air corner inspection — 28 October 2026

Read-only analysis of the closed attempt-003 `air-original-030` and
`air-upwind-030` archives. No solver was launched, and no case inputs or mesh
files were modified. The one-CPU parser reads the retained native mesh and
compact guard-time fields.

## Finding

Both `fieldMinMax` logs locate their guard-time peak in processor 7, local cell
37439, at `(17.4230769231, -0.0250266999, 3.4868782510) m`. Reconstructing
cell geometry from native `points/faces/owner/neighbour` gives global cell
299519 with center matching the logged coordinate within `2.4e-11 m`. It is
an **internal volume-cell center**, not a boundary-face location. That six-face
cell owns three boundary faces:

- `downstreamOutlet`, global face 891727, outward normal +x;
- `aircraftWall`, face 910395, outward normal +y;
- `spanwisePlus`, face 914555, outward normal approximately
  `(0, 0.4104, 0.9119)`.

This is the outermost cell at the intersection of the downstream outlet, the
top wall, and the positive-spanwise boundary. The cell volume is
`3.75134e-4 m3`; its axis-aligned dimensions are approximately
`0.15385 x 0.05000 x 0.07111 m` (aspect ratio about 3.08). The coarse mesh is
conformal structured blockMesh: no partial/cut cells are present at this
corner. Its top wall is flat at `y=0`; this coarse mesh has no snapping or local
refinement. Do not carry this exact corner geometry over to the separate
10.1-million-cell case without checking that mesh.

The coarse mesh's global native checks passed: 299,520 cells, zero
concave/planar cells, zero low-quality tet faces, minimum cell determinant
`0.001307`, minimum face interpolation weight `0.0909`, and minimum face-volume
ratio `0.1`. These are global QA values; local skewness/non-orthogonality
metrics for cell 299519 were not retained.

## Flux evidence and limit

The archived guard snapshots include `phi`, but not the `processors8` mesh or
`cellProcAddressing`/`faceProcAddressing`. Therefore exact facewise `phi` on the
three hotspot faces cannot be mapped from the compact archive without
regenerating decomposition. The final solver-log integrated patch sums show
net spanwise inflow at both sides: original `spanwisePlus=-290.044` and
`spanwiseMinus=-289.948 m3/s`; upwind `spanwisePlus=-262.243` and
`spanwiseMinus=-262.226 m3/s`. The global signed patch-flux sums close to
`-1.82e-5` and `-3.58e-6 m3/s`, respectively, within the printed-decimal
rounding of much larger patch totals. Net inflow on a patch does not establish
the flux sign at the hotspot face.

Because `pressureInletOutletVelocity` prescribes a 70 m/s tangent on inflow,
the spanwise face is adjacent to a no-slip wall and a pressure-controlled
downstream face. This combination makes an unresolved corner gradient a
plausible mechanism, not a demonstrated cause. A fixed `(70 0 0) m/s` vector
on the whole open spanwise patch would additionally constrain normal velocity
and is not a like-for-like open-boundary control.

## Reproduction

From the repository root:

```sh
.venv/bin/python scripts/run_local.py --threads 1 --timeout 120 -- \
  .venv/bin/python results/runs/rouaix-corner-inspection-20261028/inspect_corner.py
```

`corner-audit.json` records exact face geometry, cell dimensions/volume, mesh
hashes, patch totals, archive limitation and global checkMesh summary. Inputs
are the closed guard snapshots and mesh under
`results/runs/rouaix-fast-local-20261027/cases-and-runs/attempt-003/`.
