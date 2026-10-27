# Exploratory Rouaix fast stability diagnostics — 27 October 2026

## Question and scope

Use a full-domain coarse mesh to test whether the late high-speed behavior seen
in the original Rouaix run can occur in an all-air velocity-boundary control.
The pair differs only in `div(rhoPhi,U)`: `limitedLinearV 1` (original) versus
`upwind`. This is a diagnostic control, not an E1 reproduction, mesh study,
or validation result. The coarse coupon cannot establish the behavior of the
10.1-million-cell production mesh. An all-air result cannot exclude an
interface-driven corner instability.

The dry-air control preserves the prescribed velocity field at the nozzle,
`(0,-10,0) m/s`, while setting `alpha.water=0` in the volume and on the nozzle
boundary. This represents a gas-composition source with the nominal water-jet
velocity vector retained as a controlled numerical input; it does not represent
a physical water discharge.

The exact-mesh zero-simulation peak probe recorded `alpha.water=3.193498e-143`
at the prior final maximum-U cell (processor 10), with
`p_rgh=-89913.416 Pa`; this motivates prioritizing the air control but does not
establish the cause of the earlier surge. Its record is
`results/summaries/rouaix_peak_probe_20261027/`.

## Inputs and mesh

- Domain: x=[−2.5,17.5] m, y=[−10,0] m; the spanwise half-width tapers from
  8 m at the bottom to 3.5 m at the flat roof. Coordinate frame: x is
  crossflow-positive, y upward, z spanwise.
- Structured candidate: 299,520 cells from x bands 4/20/18/10/13, y bands
  5/7/20, and 144 spanwise cells. The 4.5–15.5 m x band uses ten cells after
  the first underdetermined-cell set localized there; the central nozzle block
  retains 20 cells over 1 m. The bottom y band uses five cells after the
  next-mesh trial left 50 determinant flags in the first y layer. The remote
  15.5–17.5 m band uses 13 cells to keep the candidate under the cell cap.
  A level-1 refinement was tried, but native `checkMesh` then found 776 cells
  below the determinant threshold and 364 concave cells. The pilot mesh therefore omits
  that refinement with the predeclared checks unchanged; its nominal near-nozzle
  spacing remains about 49–50 mm. The first vertical band was refined from 3
  to 4, then 5 cells after the underdetermined-cell set localized to the sloped
  spanwise boundary at y=−9 m. Spanwise count 144 gives about 48.6 mm spacing
  at the nozzle plane, to meet the unchanged 2% nozzle-area tolerance.
- Nozzle: one round 0.4 m diameter source patch, selected using the existing
  `cylinderToFace` radius 0.2 m construction. Native face area and +y normal
  are recorded; the area must be within 2% of π(0.2 m)² for this diagnostic.
- All seven patches are retained: nozzle, gasInlet, aircraftWall,
  downstreamOutlet, bottomOutlet, spanwiseMinus and spanwisePlus.
- The Case 1 v2512 template supplies density, viscosity, gravity, outlet
  conditions, wall functions and realizable k-epsilon RANS. OpenCFD v2512
  `interIsoFoam` runs from the cached image digest
  `sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`.
- This is a phase-composition-only numerical control, not gas-turbulence-
  matched: the source Case 1 inlet values remain nozzle `k=0.015 m²/s²`,
  `epsilon=0.0107810420 m²/s³` and gasInlet `k=0.735 m²/s²`,
  `epsilon=3.6978974178 m²/s³`. `phi` is mixture-volume flux; `alphaPhi_` is
  water-phase flux. They are reported separately, and `alphaPhi_` is zero in
  this all-air case.
- Fixed `deltaT=0.0001 s`; full-run horizon 0.5 s / 5,000 steps. Sparse field
  writes at 0, 0.25 and 0.5 s. Every-step passive outputs record U, alpha.water,
  p_rgh, k, epsilon and nut extrema with locations, fixed probes at the prior
  transient and downstream-corner points, water-volume integral, and
  alpha/phi flux sums over all seven patches. The observers do not call
  `oldTime()`.

## Run order and stop conditions

1. The native coarse mesh passed `checkMesh -allTopology -allGeometry`, the
   unchanged patch inventory, and the predeclared nozzle area/normal checks.
   It has 299,520 cells; the 25 mm refinement was omitted because native QA
   failed with it. This is a solver diagnostic mesh, not a qualified grid.
2. A fresh 4-rank 100-step pilot reached t=0.0100 s with 91.26 s
   `ExecutionTime` and 93 s `ClockTime`. The measured solver-clock projection
   rejects the proposed .5 s pair at that allocation; no 4-rank continuation
   is planned.
3. The active bounded queue first runs a fresh 8-rank, same-physics 100-step
   reprofile. It launches the matched original/upwind pair to .300 s only when
   the measured warm-window `ClockTime` projects no more than 1,680 s for
   3,000 steps. The .300 s horizon crosses the original .2628 s stop. Each
   branch has a 1,680 s hard deadline plus 120 s grace. OMP/BLAS remain at one
   thread; the container limit is 8 CPUs, 3 GiB RAM, 2 GiB workspace tmpfs,
   no network and no GPU. `FOAM_FILEHANDLER=collated` is used for both
   decomposition and solver writes; required U, alpha.water and p_rgh snapshots
   are checked at every declared and terminal time before the pair may advance.
4. Stop gracefully on max|U| > 1,000 m/s using the v2512 write-and-stop
   signal 12. At the hard deadline, request the same write-and-stop; preserve a
   timeout failure if `End` is not reached after the bounded grace interval.
   A user `PAUSE` during a solver run requests that same write-and-stop and
   prevents the queue from advancing. Do not count a graceful partial stop as
   reaching the declared .300 s horizon.
5. Transfer compact logs, postProcessing metrics, run manifests, and only the
   sparse saved fields to the workstation before releasing the container's
   tmpfs. Verify transferred hashes before cleanup.

## Bounded continuation after the 4-rank pilot

The 4-rank 100-step run reached 0.0100 s with 91.26 s OpenFOAM `ExecutionTime`
and 93 s `ClockTime`. A linear fit of the solver clock over steps 20–100
projects about 75 minutes for the original 0.5 s / 5,000-step request, so that
pair is not launched on the 4-rank allocation.

The next sequence is predeclared as a fresh 8-rank 100-step same-physics
reprofile, followed only if its measured solver-clock projection is at most
1,680 s for 3,000 steps by a matched original/upwind pair to 0.300 s. This
horizon crosses the prior original-case stop at 0.2628 s. Both pair members
use the same mesh, all-air state, fixed 0.0001 s step, and eight-rank
decomposition; only `div(rhoPhi,U)` differs. Their endpoint field output is at
0.300 s, and any signal-triggered checkpoint is also retained. Each solver
branch has a 1,680 s hard wall plus 120 s graceful-stop window, for at most 30
minutes from solver-stage start. A forecast above 1,680 s rejects both pair
members before either starts.

The queue waits for system-wide `/proc/stat` busy usage at or below 11 CPU
equivalents in two consecutive samples 30 s apart before each 8-rank launch.
It checks the local, Goblin and Komondor `PAUSE` sentinels before each launch;
an unavailable host or pause check defers rather than being treated as clear.
The wait budget is six hours total. No solver is active while waiting. Cases
and solver output are staged under the owned durable Goblin results path; the
output archive is capped at 1 GiB per case and a 20 GiB filesystem free-space
floor is enforced. The queue uses no GPU and preserves exact frozen source and
input hashes. These are exploratory runs, not E1 validation.

## Interpretation

Compare reached physical time, per-step ClockTime, U guard, maximum-U locations,
Courant history, alpha extrema, probes, patch fluxes and water-volume integral.
A lower maximum U on the coarse mesh is not evidence of greater accuracy. A
corner surge is evidence to inspect the boundary and mesh; local phase and cause
must be read from recorded outputs, not inferred. No VOF siblings are included
in this record; they require the root agent's follow-up decision after the
all-air pilot and must use the existing source-case preparer unchanged.

Rouaix et al. source: `experiments/E1_ROUAIX_CASE1_SOURCE.md`, DOI
[10.1016/j.ijmultiphaseflow.2023.104419](https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419).
The literature comparator remains the published Case 1 conditions and mesh,
not this coarse all-air sensitivity.
