# Rouaix local backflow pressure sensitivity — 28 October 2026

Predeclared exploratory CPU diagnostic. This is not an E1 gate, a paper
boundary-condition correction, or a validation result.

## Question and evidence

Test whether the four open-boundary pressure patches contribute to the
coarse all-air corner-speed blow-up. The prior 299,520-cell all-air runs using
`prghPressure` stopped at the downstream/top/positive-span corner at 0.1752 s
(original momentum scheme) and 0.1960 s (upwind). Upwind alone did not remove
the failure. The source review in
`results/summaries/rouaix_restart_controls_20261027/outlet-control-review.md`
recommends this pressure-energy sensitivity.

The fresh candidate starts from the same all-air `t=0` inputs and mesh. Change
only `p_rgh` on downstreamOutlet, bottomOutlet, spanwiseMinus, and spanwisePlus
from `prghPressure` (`p uniform 0`) to gravity-aware `prghTotalPressure` with
`p0 uniform 0`, `rho rho`, `U U`, `phi phi`, `value uniform 0`. Keep all four
`pressureInletOutletVelocity` entries and their tangential velocity unchanged.
This preserves zero outflow gauge and subtracts reverse-flow dynamic head; at
air density 1.18 kg/m³ and speed 70 m/s the term is 2.891 kPa. It is a
deliberate backflow-energy sensitivity, not an ambient-total-pressure match.

## Conditional water-nozzle sibling

Prepare a second fresh `t=0` candidate with the same total-pressure treatment,
mesh, 8-rank decomposition, original momentum scheme, timestep and 0.3000 s
horizon. Its only field change from the all-air candidate is the existing
source-case `alpha.water` nozzle patch (`fixedValue uniform 1`); the bulk
initial field remains `uniform 0`, and all other patches remain identical.
This means an air-filled domain with the source liquid nozzle boundary, not a
fully water-filled domain. Keep it staged without GO until the all-air target
has reached `t >= 0.20 s` with finite diagnostics and a peak speed below its
200 m/s operational stop, and the archived matched baseline/source checks
pass. If the target stops earlier or any check fails, do not release the water
case. The 200 m/s operational signal may stop the water branch after its own
fresh start; do not clip or modify fields.

## Matched inputs and observable

- Solver: OpenCFD v2512 `interIsoFoam`, image
  `sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`.
- Mesh: previously native-QA'd coarse full-domain mesh, 299,520 cells; copied
  from the immutable `rouaix-fast-local-20261027/cases-and-runs/attempt-003`
  preparation. No remeshing or field interpolation.
- Fresh initial state: `alpha.water=0` in the domain and nozzle, retained
  source-case velocity and realizable k-epsilon fields. This is an all-air
  negative control, not a water discharge case.
- Original momentum convection `limitedLinearV 1`; all other schemes,
  material inputs, geometry, time step and boundaries match the prior
  `air-original-030` case. Fixed `deltaT=0.0001 s`, 8 MPI ranks, collated I/O.
- Target horizon: 0.3000 s (3,000 steps), subject to a 1,680 s solver wall
  bound plus 120 s graceful-signal window. The target's operational U guard is
  200 m/s. It requests OpenFOAM's configured write-and-stop signal; it does not
  clip or alter fields. The historical static-pressure baseline used a
  1,000 m/s guard, so compare raw traces only at shared times and report the
  differing operational stop thresholds.
- Before the target, run a separately labelled fresh `t=0` checkpoint smoke
  using the same backflow BCs, 8 ranks and mesh, 0.01 s declared horizon, but
  a 70 m/s operational guard. Require OpenFOAM `End`, exit 0, and captured
  `U`, `alpha.water`, and `p_rgh` at `t=0` and the guard-stop time. This tests
  the signal-save path without changing the target branch's 200 m/s guard.
- Record every-step speed/pressure/turbulence extrema with locations, water
  volume, seven signed patch fluxes, two probes, solver iterations and wall
  timing. Retain only initial, endpoint or guard-stop fields; no dense 3D
  history.

## Compute, stop and interpretation

Use Goblin CPU only, up to 8 ranks and 3 GiB container memory, with OMP/BLAS
threads fixed at one. No GPU, HPC queue, or I4F container. Admit only with the
project's 20 GiB floor plus the runner's 1 GiB archive cap and staging space;
current inspection found 96 GiB free, 119 GiB available RAM and 20 effective
CPUs, with no active solver. Profile the target's first 100 steps from its
live log but do not delay launch for another forecast. Stop on nonfinite
diagnostics, an operational U guard, a 600 s no-progress interval, PAUSE, or
the declared wall/disk limit; preserve raw fields and logs for any stop.

Primary comparison: maximum speed and location, pressure and flux traces, and
whether the fresh candidate reaches the same time as the prior original-scheme
baseline. A lower peak alone is not evidence of greater physical accuracy.
Keep the run exploratory; no fitted inputs or acceptance tolerance are used.

## Observed air-branch result

The separate guard-save smoke crossed 70 m/s at 0.0001 s, wrote at 0.0003 s,
and exited with `End`, code 0, and the required `U`, `alpha.water`, and `p_rgh`
snapshots. The fresh all-air target then ran all 3,000 steps to 0.3000 s.
Container `rouaix-backflow-air-backflow-030-20261028-q20261028` started at
2026-10-28 12:43:40.620 UTC and completed at 13:01:00.586 UTC. It exited 0
with `End`, reached the declared endpoint, and did not trigger its 200 m/s
operational guard. The 29.76 MB archive hash and local copy agree; the snapshot
inventory passed for `U`, `alpha.water`, and `p_rgh` at `t=0` and `t=0.3`.

Every-step records show a peak speed of 85.0362 m/s at 0.0366 s and terminal
speed of 75.7689 m/s. `alpha.water` and its domain integral stayed exactly zero,
as expected for this all-air negative control. With `p_rgh` dimensions
`[1 -1 -2 0 0 0 0]` (Pa), the recorded run extrema were -3007.95 Pa at 0.0078 s
and +14373.64 Pa at 0.0001 s; terminal cumulative continuity error was
1.9548e-5. These are solver diagnostics, not an accuracy measure.

The matched raw traces are saved in
`results/summaries/rouaix_backflow_local_20261028/matched-time-comparison.json`.
At 0.1700 s, before the historical run approached its guard, the old static
`prghPressure` baseline had maximum speed 144.526 m/s versus 76.209 m/s in the
total-pressure candidate. The baseline then triggered its 1000 m/s stop at
0.1751 s (recorded trigger speed 1091.294 m/s) and ended at 0.1752 s with
1364.743 m/s; the candidate at those same raw `Time` records remained near
76 m/s. Its pressure extrema also diverged sharply. This supports a strong
boundary-energy sensitivity in this setup; it does not establish that the
candidate matches a paper boundary condition or is more physically accurate.

The conditional water-nozzle sibling passed its pre-release checks and was
released after the air case reached 0.2009 s with finite diagnostics and
maximum speed below 200 m/s. It started from bulk-air `t=0` with the source
nozzle alpha patch set to one. Its first 100 steps took 50 s of solver
`ClockTime`; the warm `ExecutionTime` slope was about 0.4801 s/step while the
air run was concurrent. It then completed all 3,000 steps at 0.3000 s, with
`End`, exit 0, and no 200 m/s stop. The run started at 12:53:10.447 UTC and
completed at 13:10:18.320 UTC; the guard's recorded elapsed wall time was
1019 s. Its archived endpoint passed snapshot checks and its 33.42 MB archive
matched the remote SHA-256.

The water-case global speed peak was 103.1456 m/s at 0.0957 s; terminal speed
was 100.2184 m/s. Every-step alpha extrema stayed within `[0,1]`. The bulk and
interface Courant maxima were 0.26165 at 0.0901 s and 0.16761 at 0.1775 s.
Water volume reached 0.379166666663 m³ at 0.3000 s. Integrating the 3,000
signed `alphaPhi_` samples at the fixed 0.0001 s step gives 0.379166666667 m³
in through the nozzle, 3.534e-12 m³ net outward through all other patches,
and -3.661e-13 m³ volume-balance residual. At the declared water density
997.6 kg/m³, the corresponding raw mass residual is -3.65e-10 kg. This is an
exploratory flux-integral check, not a declared conservation gate. Detailed
records are in
`results/summaries/rouaix_backflow_local_20261028/water-total-pressure-diagnostics.json`.

## Matched static-pressure water control (addendum before release)

To separate pressure-boundary effects from the newly active water-nozzle
condition, prepare and run a fresh bulk-air case with the existing source
nozzle alpha patch at one, paired against `air-backflow-water-030`. Copy the
already prepared total-pressure water case, then replace only the four open
`p_rgh` blocks with the corresponding original static `prghPressure` blocks
from the immutable coarse all-air baseline. Require every case file other than
`0/p_rgh` and `case-inputs.json` to remain byte-identical to the total-pressure
water case, and require all content outside those four blocks in `0/p_rgh` to
remain identical before GO.

Keep the same 299,520-cell mesh, fresh t=0/bulk-air alpha, source water nozzle,
velocity and turbulence fields, original momentum scheme, fixed 0.0001 s step,
0.3000 s horizon, 8 MPI ranks, collated output, 200 m/s non-clipping stop,
1680 s solver wall bound and 120 s save grace. Launch concurrently only after
measured capacity supports another eight ranks; if the total-pressure branch
finishes during preparation, launch as soon as its archive and capacity checks
pass. Do not pause or restart the total-pressure water run. Compare
speed/pressure histories, water volume, signed fluxes, continuity, and reached
time over shared records. This is an exploratory matched control and does not
validate either boundary treatment.

The total-pressure water arm finished while the static control was being
prepared. After verifying its full-horizon archive, the static control started
at 13:11:42.569 UTC with a 19.592/20 CPU-equivalent availability sample. Its
pre-GO check confirmed that only the four open `p_rgh` blocks and metadata
differ from the total-pressure water input. Its first-100 profile reached
0.010 s in 23 s `ClockTime`; the warm `ExecutionTime` slope was 0.2332 s/step.
The static case then triggered its 200 m/s guard and stopped at 0.1703 s with
maximum speed 210.058 m/s, `End`, and exit 0. The supervisor records the guard
trigger at 0.1702 s and 200.697 m/s, while the raw function-object maximum with
that value is labelled `Time=0.1701`; retain both timestamps because the guard
status trails the raw field record by one fixed step. The initial and guard
snapshots passed inventory checks, and its 31.92 MB archive hash matched.

Against the full-horizon total-pressure water case, the static control had
maximum speed 196.368 m/s at raw 0.1700 s versus 98.103 m/s for total pressure;
at raw 0.1701 s the values were 200.697 versus 98.135 m/s. Both had the same
water volume, 0.215240277778 m³, at 0.1703 s. Its `alphaPhi_` phase-volume
balance residual was 3.30e-15 m³ up to its guard stop. The selected shared-time
records are in
`results/summaries/rouaix_backflow_local_20261028/water-pressure-matched-comparison.json`;
static diagnostics and source checks are in
`results/summaries/rouaix_backflow_local_20261028/water-static-control-diagnostics.json`
and `results/runs/rouaix-backflow-local-20261028/static-water-pre-go-checks.json`.
This matched coarse comparison supports a strong pressure-boundary sensitivity
for the water-nozzle startup. It does not establish which treatment matches
the apparatus or validate the run.

## Fixed-step cost/robustness diagnostic (addendum before release)

Run one fresh copy of the successful total-pressure water-nozzle case with the
same 299,520-cell mesh, initial fields, source nozzle alpha patch, pressure and
velocity boundaries, schemes, 8 ranks, and 0.3000 s endpoint, but fixed
`deltaT=0.0003 s` (1,000 steps). Do not enable time-step adaptation, clip any
field, or change physics. Require the copied case to be byte-identical to the
0.0001 s reference except `system/controlDict` and `case-inputs.json`, with
only `deltaT` changed in the control dictionary and metadata matching the
declared 1,000 steps.

Keep the same 200 m/s non-clipping guard and 120 s save grace. Set the solver
wall cap to 900 s, based on the 1,019 s successful reference runtime at 3,000
steps (about 340 s projected for 1,000 steps). The reference maxima were bulk
Co=0.26165 and interface Co=0.16761; their threefold estimates, 0.78495 and
0.50283, are admission context only, not guarantees or acceptance limits.
Record endpoint time, peak/terminal speed, alpha range, interface/bulk Co,
water volume and signed phase-flux balance, and solver wall cost. Preserve the
0.0001 s reference unchanged; interpret this as a coarse timestep cost and
stability diagnostic, not a resolution study or E1 result.

### Fixed-step diagnostic result

The case passed pre-GO checks showing the reference inputs and sources were
unchanged and only `system/controlDict`/metadata differed. The bounded
LaunchAgent released Docker container
`c19d371edb4560a7a434e7ee57a46f2d845fe6ee182b635ab0d97fde73dfa467` at
2026-10-28 13:27:28 UTC. It completed at 13:32:12 UTC: `End`, exit 0,
`t=0.3000 s`, 1,000 steps, no guard trigger. Solver `ClockTime` was 274 s
(supervisor elapsed 276 s), below the 900 s wall cap. The 31,797,802-byte
archive SHA-256 is
`a7d0963990430d277a59bd2f32fe9ae63c50831f7ba82ea8826c4a09304d16b8`; remote
and local hashes matched and initial/terminal `U`, `alpha.water`, and `p_rgh`
snapshots passed inventory.

The run used 3.72 times less wall time for the same horizon than the
0.0001 s reference (274 versus 1,018 s); per-step wall time was 0.274 versus
0.339 s. Peak speed was 105.319 m/s at 0.0555 s; terminal speed was
99.850 m/s. Alpha stayed in [0,1]. Bulk Co peaked at 0.77629 at 0.0891 s and
interface Co at 0.49124 at 0.2271 s (2.97 and 2.93 times the reference
maxima). At `t=0.3000 s`, water volume was 0.379166476170 m³; integrated
nozzle inflow was 0.379166666667 m³ and net outward phase flux was
1.9049484e-7 m³. The volume residual was -2.1571e-12 m³, or -2.1519e-9 kg
at 997.6 kg/m³. The full compact metrics, integrity receipts, and provenance
are in
`results/summaries/rouaix_backflow_local_20261028/water-dt0003-diagnostics.json`.

This run remained finite and completed under the declared non-clipping guard,
with larger Courant maxima and small changes in speed/phase flux relative to
the reference. It establishes only that this coarse case reached the target
under the larger fixed timestep; it does not establish timestep convergence,
physical correctness, or an E1 pass.
