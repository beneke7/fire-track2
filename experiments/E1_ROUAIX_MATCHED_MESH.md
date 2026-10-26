# Exploratory Rouaix Case 1 matched mesh

**Purpose:** produce and inspect a source-shaped, mesh-only hex-dominant
candidate on the Mac. This is not a CFD run, E1 comparison, solver
verification, or gate decision.

## Source and geometry

Rouaix et al. (2023), DOI
[10.1016/j.ijmultiphaseflow.2023.104419](https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419).
The source record is E1_ROUAIX_CASE1_SOURCE.md.
Use the single round Case 1 nozzle (D=0.4 m), U_j=(0,-10,0) m/s,
U_g=(70,0,0) m/s; x is crossflow-positive, y upward, and z spanwise.
Domain: x=[-2.5,17.5] m, y=[-10,0] m; spanwise half-width grows from
3.5 m at the top to 8 m at the bottom. The roof is flat at y=0, which the
paper says gave no significant jet-evolution change in preliminary unreported
tests. It is not aircraft CAD.

Figure 4 (printed p.6 / PDF p.7) shows a near-jet fine region and a broader
surrounding region; §3.3 (printed p.7 / PDF p.8) describes separate 70, 50,
30, and 16 mm mesh candidates, five prism layers, and 1.1 growth. The mesh
sizes and ROI outlines are not recovered as exact coordinates. The provisional
fine guide uses the digitized Figure 13 lower-cloud envelope (printed p.12 /
PDF p.13), shifted upward by 0 to 0.8 m by x=1.95 m, then continued to the
low-confidence Figure 4 visual bound (x,s)=(6.5,6.0) m. This is an
engineering refinement guide, **not a measured jet centerline**. The
spanwise extrusion is also assumed: a 0.9 m fine radius treats the largest
digitized Figure 13 ordinate z/D=4.328 (1.73 m at x/D=2.5) as full width;
a 1.73 m surrounding radius retains the alternate one-sided interpretation.
Figure 4 gives no 3-D ROI.

## Mesh and declared checks

blockMesh makes one trapezoidal-prism hex block with 179×89×90 =
1,433,790 background cells. Directional sizes vary: approximately 111.7 mm
in x, 123.2 mm along the sheared vertical edge (112.4 mm vertical
projection), and 77.8–177.8 mm spanwise. snappyHexMesh uses dyadic
refinement: level 1 is 56 mm; level 2 is 28 mm; level 3 is 14 mm; level 4 is
7 mm. The selected Mac candidate uses level 3 in the fine guide and nozzle
region, and level 1 in the surrounding guide. Its source-inspired nominal
sizes are 14/56 mm, compared with the paper's 16/50 mm labels. The nozzle
remains at level 3 because the measured circular-patch area meets the
predeclared 0.5% area target; no level-4 nozzle refinement is present in the
final mesh.

The paper reports five wall layers with 1.1 expansion but no first-layer
height. The selected Mac mesh contains **zero explicit prism/wall layers**;
that source feature is not reproduced. Experimental layer implementations
are documented below and remain rejected. The cast-only mesh has a no-layer
wall gap that matters for later near-wall physics and time-step planning.

The unrestricted `refineWallLayer '(aircraftWall)'` trial also selected
point-neighbour cells at the nozzle rim: it selected 21,256 cells per pass
for 21,120 wall faces and grew the nozzle patch from 924 to 1,468 faces.
Nozzle area and +y normal stayed unchanged to roundoff, but 160 low-quality
volume-decomposition tetrahedra appeared at the nozzle rim, plus 31,282
Foundation 13 “concave or planar” cell flags. This unrestricted candidate is
**rejected**. An owner-only selection fixture retained its nozzle and has
only exact planar checker flags, but the 2.77M-cell owner-only pilot has
unresolved warped geometry and is **not accepted**. No wall-layer method has
been applied to the 10.1M final cast-only mesh. Actual nozzle-adjacent cell
scales must be measured before using them for time-step planning.

The analytical circular nozzle area is pi*(0.2 m)^2 = 0.1256637061 m2. The
final cast-only patch area and oriented area vector are recorded in the
hash-bound nozzle audit under `results/runs/rouaix-matched-mesh-mac-20261025/`.
Face-area agreement alone does not establish unchanged adjacent cell scale.
These are mesh checks, not E1 acceptance criteria.

The mesh pipeline refines cells with layers disabled, reconstructs the
castellated mesh, selects nozzle faces and creates that patch in serial, then
runs global `checkMesh`. Foundation 13's parallel `topoSet -constant` stalled
in an MPI read at pilot size; the failed attempt and stack evidence are
preserved. In this Foundation 13 build `reconstructParMesh` is a successful
no-op; use `reconstructPar -constant -noFields -noSets` and assert the global
cell count after each mesh transition.

Run the pilot first at 28 mm in the fine guide, 56 mm around it, and 14 mm
at the nozzle. Record peak RSS, wall time, cell count, and checkMesh
topology/geometry before using its measured scaling to decide whether the
14/56 mm candidate fits the VM. blockMesh is serial;
snappyHexMesh is intended for 10 OpenMPI ranks. Stop refinement at the
predeclared cell cap (22 million) or if measured memory headroom is
insufficient; a capped mesh is an incomplete candidate and must not be called
16 mm. Do not launch any solver.

## Runtime and provenance

The Mac's existing Multipass Ubuntu 22 VM is configured for 10 vCPU and
16 GiB after the 2.77M-cell pilot check peaked at 3.72 GiB. The final
10.10M-cell castellation was produced in that VM; monitor host memory pressure
before serial global QA. It provides OpenFOAM Foundation 13, OpenMPI 4.1.2,
ARM64, DP Int32. The pilot
mesh is ASCII; the final candidate is binary to limit disk use, with its
OpenFOAM architecture header recorded in the run manifest. `writePrecision 16`
is set for reproducible geometry export and audit.
Both use standard polyMesh files for later native-v2512 checkMesh/HPC reading;
do not transfer VM libraries or MPI binaries.

Use unique results/runs/rouaix-matched-mesh-* directories. Keep the input
dictionary and ROI metadata with each stage; preserve failed attempts and
logs. Record Git revision/dirty state, SHA-256 input hashes, executable
versions, rank count, elapsed time, peak RSS, final checks, nozzle area and
normal, cell-type counts, refinement-level coverage, and layer coverage.

## Pilot checkpoints and wall-layer evidence

The immutable `pilot-checkpoint` is a 2,773,793-cell global castellation
before layer extrusion. Its 924-face nozzle patch has measured area
0.12546554934822965 m2 (−0.157688% from the circular target) and normal
(0,1,0), so level 3 is retained in the final input. The serial prelayer check
reports topology OK, minimum determinant 0.7310 and interpolation weight
0.3322, plus 29,914 cells in OpenFOAM 13's “Concave cells (using face planes)”
category. The installed checker labels this “Concave OR PLANAR face”; an
independent signed-plane audit found all 29,914 prelayer flags were planar
subdivisions without positive vertex-plane excursion above 1e−11 m.

Two snappyHexMesh wall-layer attempts are rejected. The fixed-height pilot
failed determinant and interpolation-weight checks. A relative-height trial
added 102,610 of 105,600 requested layer cells and averaged 4.86 of 5 layers,
but a signed-plane audit found 24,334 positive aggregate-plane excursions,
with a maximum of 26.6 mm and face warp up to 18.8 mm. These are rejected
warped geometries, not a certified count of purely concave cells. Do not use it.

The alternate four-cut wall split has 2,858,817 cells; all 2,900,159 original
points remained an exact coordinate prefix. It passes topology, determinant
(minimum 0.07656), interpolation-weight (minimum 0.05795), volume-ratio
(minimum 0.01016), skewness, and non-orthogonality checks. It fails the 160
low-quality tetra-decomposition and 31,282 concave-or-planar checks; the
tetra flags are at the nozzle rim. Logs, quality sets, and a full global mesh
copy are preserved under
`results/runs/rouaix-matched-mesh-mac-20261025/pilot-wall-split/`. No layered
pilot mesh is accepted.

The owner-only four-cut pilot selects exactly 21,120 unique aircraft-wall face
owners in each of four passes and adds 84,480 cells, for 2,858,273 total.
`checkMesh` passes topology, connected-region and patch-topology checks; it
reports `Face tets OK`, maximum aspect ratio 8.528, minimum volume
3.1273e−7 m³, maximum non-orthogonality 47.58° (average 9.47°), maximum
skewness 1.310, minimum determinant 0.08072, minimum interpolation weight
0.19297, and minimum volume ratio 0.05694. It also reports 31,182
“concave or planar” cells. The independent signed-plane screen finds 125
positive vertex-plane screens (maximum 8.441 mm, 5.65% of local cell diagonal)
and 31,057 planar/roundoff-only flags. All 125 positive cases have offending
face warp at least as large as the plane excursion, so they are unresolved
warped geometry, not a certified count of truly concave cells. Their total bounds are
x=[−0.936,1.746] m, z=[−1.736,1.730] m, and y=[−0.112,−0.005] m; none is a
current aircraft-wall or nozzle face owner. This owner-only trial is
**rejected** pending a demonstrated correction. Full logs and per-cell
localization are under `results/runs/rouaix-matched-mesh-mac-20261025/pilot-owner-wall-split/`.

The coarse wall split leaves the nozzle patch exactly unchanged: 924 faces,
area 0.12546554934822962 m², +y normal. The nozzle-owner volume/area median
remains 14.0862 mm before and after. `aircraftWall` has 21,120 faces and
21,120 unique owner cells. Measured first-band volume/area thickness is
2.303 mm minimum, 4.608 mm at p05, and 18.426 mm at the median/p95/maximum.
All 2,900,159 original point coordinates are an exact prefix of the 2,900,159
final points. `refineWallLayer` does not update the old AMR labels: `cellLevel`
still declares 2,773,793 entries and `pointLevel` 2,900,159, while the split
mesh has 2,858,273 cells and 2,986,731 points. A future static transfer bundle
must exclude these stale files or replace them with valid metadata; the full
diagnostic copy is preserved unchanged.

The final 14/56 mm cast-only mesh and clean five-file transfer bundle are
preserved under `results/runs/rouaix-matched-mesh-mac-20261025/final-cast-only/`
and `results/runs/rouaix-matched-mesh-mac-20261025/final-cast-only-transfer-core/`.
The mesh has 10,099,265 cells
(9,936,263 hexes and 163,002 polyhedra), one region, a 924-face nozzle patch,
and no prisms. The actual scalar refinement histogram is L0=1,373,193,
L1=332,846, L2=190,042, and L3=8,203,184; there is no L4. Full serial
`checkMesh -allTopology -allGeometry` uses 13.23 GiB peak RSS in 7m13s and
passes every listed quality category except 114,008 native “concave or planar”
flags. Independent signed-plane review classifies all 114,008 as planar
subdivisions with maximum absolute plane excursion 6.224e−15 m; no positive
out-of-plane vertex excursion was found. The audit verifies every native
flagged cell and the binary list counts; its report is
`results/runs/rouaix-mesh-convexity-20261025/finecast-binary-review.md`, with
machine-readable audit SHA-256
`b8194ee0f417483c54a284d29efc40d33e272fd64c04db179ead20bb712b1ca1`.
This interpretation covers the native flagged cells, not every unflagged
cell. Preserve the native warning and independent interpretation together.
The immutable binary polyMesh, per-file manifest, native check log, stage
timings, input hashes, transfer manifest, and final nozzle audit are preserved
with the run. The transfer `SHA256SUMS` manifest
hash is `86cada8ce1f7e2822a3252d873aba3004210f548ec624562c2cc5b465628c76e`;
the nozzle audit binds to that hash and records 924 faces, area 0.1254655493
m², and area vector (0, 0.1254655493, 0) m². No CFD or HPC job is included.

### True-hex wall-owner trial

Foundation 13 `topoSet` confirmed that `shapeToCell` with `shape hex` selects
the cell-model hexes and that a `SUBSET` action intersects that selection with
fresh `aircraftWall` face owners. A coverage face set is made with
`cellToFace option all`, then intersected with the wall patch. The 8×2×8
multi-face aperture fixture selected all 52 hex wall owners on each cut,
retained all 12 nozzle faces, and completed four cuts with 100% area-weighted
five-band coverage. Its eight native concave-or-planar flags match the earlier
fixture's core polyMesh hashes; an independent plane screen found no positive
vertex excursion in those planar flags. This verifies selection syntax and
aperture handling only.

A fresh coarse pilot started from the immutable 2,773,793-cell castellation
under
`results/runs/rouaix-matched-mesh-mac-20261025/pilot-owner-hex-wall-split-retry1/`.
The command was
`.venv/bin/python scripts/run_local.py --threads 1 --timeout 7200 -- ssh -oBatchMode=yes ubuntu@192.168.252.2 'cd /home/ubuntu/rouaix-matched-mesh-mac-20261025/pilot-owner-hex-wall-split-retry1 && exec timeout -k 30 6500 bash ./run_mesh.sh ./case owner-wall-split'`.
All four serial cuts completed. Each pass selected 20,364 hex owners from
21,120 wall faces and added exactly 20,364 cells; the total grew by 81,456 to
2,855,249. Face-selection sets were mapped to original wall polygons after
checking that the patch-local polygon order and exact coordinates remained
unchanged. The selected faces cover 136.4821 of 139.8745 m² (97.5746%). Thus
97.5746% of wall area receives five bands and the remaining 3.39246 m²
(2.4254%, 756 faces) remains unlayered. The selected area stayed constant
through all four cuts; no wall area received an intermediate number of bands.

The candidate retains one connected region and singly connected patches, but
is **rejected**: native `checkMesh -allTopology -allGeometry` reports 263
low-quality face-tet decompositions and 30,186 “concave or planar” cells.
The former is a new native geometry failure relative to the prior owner-only
trial, which had no face-tet errors. Other reported checks pass: minimum cell
determinant 0.08072, minimum interpolation weight 0.19297, minimum face-volume
ratio 0.02036, maximum non-orthogonality 51.21° (average 9.48°), maximum
skewness 1.467, and face-flatness minimum approximately 1. The independent
all-flag triangulated audit was not run because the native face-tet failure
already rejects this candidate.

The 924-face nozzle patch is unchanged at 0.12546554934823 m² with +y normal;
nozzle-owner V/A remains 14.0862 mm at the median. All 2,900,159 original
point coordinates remain an exact prefix of the 2,985,227-point trial mesh.
The run took 52.21 s for global checkMesh (3.83 GiB peak RSS, no swap); each
`refineWallLayer` pass took 13.22–14.45 s, and each set-selection pass took
6.20–6.51 s. The stopped host SSH wrapper emitted no final stage banner after
the remote checkMesh had reached `End`; the completed mesh, per-stage logs,
point snapshot, and output hashes are preserved. As for the earlier split
trial, refinement-level files are stale after these topological cuts and are
not suitable for a transfer bundle. No layer method is accepted for the final
14/56 mm mesh.
