# Rouaix native restart controls — 27 October 2026

Declared before submission. Exploratory diagnostics only; no E1 acceptance or
paper-fidelity claim. Static timesteps remain the reference. The immediate aim
is to test restart compatibility and cross the known instability window without
replaying the first 0.20 s.

## Evidence and question

The original 10,099,265-cell run stopped at 0.2628 s with a finite but
unphysical speed surge near the downstream/top/positive-span corner. The final
peak cell was nearly all air. Both 299,520-cell all-air controls subsequently
hit the velocity guard at the same corner: original at 0.1752 s, upwind at
0.1960 s. Upwind alone did not remove that coarse-control failure. This does
not prove a common fine-grid mechanism.

The original-scheme seed, Slurm 14669440, completed 0.20 s / 2000 steps on
120 ranks. Its archive and native afterany audit are recorded in
`results/summaries/rouaix_healthy_seed_20261027/terminal/`. The checkpoint is a
candidate donor, not presumed physically healthy: large RANS extrema and
transient alpha bounding remain qualified.

## Frozen donor and common inputs

- Archive: `/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-healthy-seed-source-v1-20261027/rouaix-e1-hpc-pilot-14669440/result.tar.gz`.
- SHA-256: `31010755e705010771de7ed00fb5fb9990e7d2621237c3d881ee22b826cf25c9`.
- Donor time exactly 0.20 s, collated `processors120`, unchanged decomposition
  and mesh. Preserve U, alpha.water, p_rgh, k, epsilon, nut, p, phi, time state,
  cumulative continuity state and addressing as present in the checkpoint.
- Parent ledger summary SHA-256:
  `0baa380005d188edf6c94a0c175b790a5a8af5fa79773ff37ace5da5dda2f300`.
  Its measured final water inventory is 0.2508975771509 m3 at rho=997.6 kg/m3.
- Native OpenCFD v2512, DP32, Cray MPICH, same installed solver identity and
  source provenance as the donor. No solver-source modification.
- Original `limitedLinearV 1` momentum advection, Gauss linear U gradient,
  realizable k-epsilon, original materials/geometry/velocity and alpha BCs,
  one outer corrector, three pressure correctors, one alpha subcycle.
- Fixed deltaT=0.0001 s. No velocity/pressure clipping or fitted source changes.
  Preserve the solver's existing isoAdvection alpha-bounding behavior and caveat.

For the v2 scheduling amendment, retain the original 120-way decomposition
on three nodes with 40 ranks/node and 22 GiB/node (66 GiB total). This changes hardware/placement from the donor's single node; record
CPU models, affinity and measured throughput. Do not claim bitwise continuation.
The restart control and candidate must use the same declared placement.

Scheduling amendment (27 October17:55 UTC): v1 smoke14675897 was submitted
on two nodes ×60 ranks,32 GiB/node and remained pending without CFD steps.
A new test-only forecast placed it at28 October07:19 UTC, versus today18:08
UTC for three nodes ×40 ranks. Prepare a new immutable v2 smoke and replace
the old pending parent/auditor only after the v2 submission readback is
verified. Preserve the zero-step cancellation and v1 source; do not run both.
The extra2 GiB memory does not increase total CPU ranks. These forecasts
are provisional and do not reserve capacity.

Startup correction (28 October): v2 smoke14676288 obtained its requested
allocation but failed in three seconds before Python/CFD. Its shell quoted
FOAM_BASH, whose module-provided value includes bashrc arguments, as one path.
The launcher also omitted `/unpacked` from its frozen source root. Control
14676290 cancelled with zero allocation. Preserve v2 and its audit receipts;
freeze a new v3 source with only launcher/path corrections and regression
checks. Repeat the same declared smoke/control once with no physics changes,
and retain the actual-smoke success gate and bounded afterany captures.

## Finite job sequence

1. **RSMOKE-ORIG:** 0.2000 to 0.2010 s, exactly ten fixed steps, unchanged
   physics. Three nodes, 120 MPI tasks, one CPU/task, 22 GiB/node (66 GiB total),
   `cpu-short`, normal QoS, short name `ml-vof`, 20-minute allocation.
   Require native clean End/exit 0, complete ten-step diagnostics, verified
   terminal checkpoint and incremental ledger before releasing long siblings.
2. **RCTRL-ORIG:** fresh branch from the same donor, 0.20 to 0.30 s, at most
   1000 steps; same original setup. Same placement/memory, 90-minute cap.
   Its purpose is to check whether the restart reproduces the known surge.
3. **RCTRL-PTOTAL0:** independent fresh branch from the same donor, same target,
   timestep, resources and numerical settings. Change only the pressure BC on
   downstreamOutlet, bottomOutlet, spanwiseMinus and spanwisePlus to the
   gravity-aware `prghTotalPressure`, with p0=0 Pa gauge. All U BCs stay unchanged.
   If needed, run a separately declared ten-step candidate smoke before release.

The long branches can be submitted held while the smoke is pending. Release
must be gated by actual smoke evidence, not merely an auditor's successful
capture or the absence of a Slurm error. No automatic retry. A valid captured
U-guard stop in the original branch does not invalidate the independent
candidate; infrastructure, pause, missing source or failed capture does.

## Pressure treatment and interpretation

Candidate dictionary on each of the four open pressure patches:

```foam
    type  prghTotalPressure;
    p0    uniform 0;
    rho   rho;
    U     U;
    phi   phi;
    value uniform 0;
```

Installed v2512 source gives
`p_rgh = p0 - 0.5*rho*neg(phi)*magSqr(U) - rho*(g.Cf-ghRef)`.
The existing `prghPressure` prescribes static pressure before hydrostatic
reduction. Thus the treatment retains zero static gauge on outward flow and
subtracts dynamic head on reverse flow. At declared air rho=1.18 kg/m3 and
speed70 m/s, that subtraction is 2891 Pa. This is a deliberate backflow-energy
sensitivity, not a neutral replacement or a paper-matched boundary claim.
No scalar p0 preserves the original static-pressure prescription for both
flow signs. Do not interpret a lower speed as greater physical accuracy.

Primary source: OpenCFD v2512
[prghTotalPressure implementation](https://api.openfoam.com/2512/prghTotalPressureFvPatchScalarField_8C_source.html),
[prghPressure implementation](https://api.openfoam.com/2512/prghPressureFvPatchScalarField_8C_source.html), and
[pressureInletOutletVelocity implementation](https://api.openfoam.com/2512/pressureInletOutletVelocityFvPatchVectorField_8C_source.html).
Installed-source paths, line ranges and hashes are preserved with the source
capsule/review receipt. This treatment must be edited with a verified native
parallel utility; raw string replacement inside collated binary blocks is
not acceptable. Verify unchanged internal p_rgh and other checkpoint values.

## Diagnostics, budget and stop conditions

Preserve every-step extrema/locations, bulk/interface Courant numbers, all
linear solver records and iterations, all seven signed alphaPhi_ patch flux
sums, water volume, time/ClockTime and sparse checkpoint fields. Record actual
elapsed setup/solver/archive time and Slurm CPU/RSS scopes; do not sum parent
and child CPU accounting or infer aggregate memory from task MaxRSS.

The incremental mass ledger starts at the measured donor inventory. Integrate
only new completed intervals with outward-positive patch flux and the right
endpoint rule. Do not reuse the fresh-case zero-water assumption or double
count prior source/escape. Bind donor/archive/ledger hashes and actual stop
time; preserve residuals for guard-stopped partial runs. These are raw
observables, not a conservation gate. Keep the native post-flux alpha-bounding
qualification.

Keep the shared PAUSE sentinel, nonfinite diagnostics, max|U|>1000 m/s,
600-second no-progress, free-disk floor, allocation deadline/checkpoint margin,
and verified-own-step signal escalation. Stop and capture before allocation
expiry. Use only allocated CPUs, OMP/BLAS threads1, no GPU or requeue. Preserve
failed attempts and durable logs if transfer fails. Pack collated outputs into
one archive and compact audit records; do not transfer full fields to the Mac.

Measured continuation cost from the donor suggests roughly 56 solver minutes
for 1000 more steps on the old node. Three-node performance is unknown until the
smoke. A 90-minute allocation is a cap, not a promise of reaching 0.30 s;
release can be withheld if measured throughput makes it unaffordable. Keep
source/index hashes, revision/dirty state and exact submitted command. Slurm
start forecasts are not reservations.
