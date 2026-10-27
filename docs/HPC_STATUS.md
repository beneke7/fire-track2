# Komondor Rouaix status

Updated 2026-10-27 12:05 UTC (13:05 CET). Analytical E0 remains the only
passed gate. All CFD runs here are exploratory.

## Current execution

SSH access is restored. **14669440 (`ml-vof`) is RUNNING on one node,
120 CPU ranks**, x1000c1s1b0n1, since 11:35:09 UTC. It targets a fresh
original-scheme checkpoint at **0.20 s**, fixed 0.1 ms, on the unchanged
10,099,265-cell mesh. At 12:05:10 UTC its guard readback was 0.0523 s,
max recorded speed 103.29355 m/s, with no guard stop. This equals the prior
original short-trial peak; full-field equivalence has not been checked.
The two-hour allocation ends at 13:35:09 UTC; completion within that cap is
not guaranteed. Native auditor **14669459** waits on `afterany:14669440`.
A captured checkpoint is a candidate donor until its terminal audit passes.
[Declaration](../experiments/E1_ROUAIX_HEALTHY_SEED_20261027.md) and
[submission proof](../results/summaries/rouaix_healthy_seed_20261027/README.md).

The prepared eight-hour upwind extension is **unsubmitted**. No old failed
CFD run was resumed. This 120-CPU allocation was accepted in `cpu`; no
`cpu-short` eligibility claim is made. Slurm start estimates are forecasts,
not reservations. Times above are UTC, with CET one hour later.

## What finished overnight

- **Original 5 s target, 14650641: FAILED, 1:0.** The U guard observed
  1045.53 m/s at 0.2625 s; final write-stop reached **0.2628 s**, with
  peak speed **1260.04 m/s**. The solver reached `End`, but the requested
  five seconds did not complete. All **21,025 linear solve records** met
  their configured convergence criteria. Whole-job wall was 9380 s and
  TotalCPU 303.344 core-hours. Ledger closure was +1.20e-5 kg after
  328.932 kg injected; this does not establish momentum closure or stability.
  [Hash-bound postmortem](../results/summaries/rouaix_long_stop_20261027/README.md).
- **Upwind 120 ranks, 14651178: COMPLETED, 0:0.** It reached all 500
  fixed steps through **0.05 s**, with all 4001 linear solve records
  converged. Peak speed was **96.385 m/s**, versus 103.294 m/s in the matched
  original scheme. Whole-job wall was 1896 s versus 1839 s; different
  CPU128 hosts prevent a controlled speed comparison. The only numerical
  dictionary difference is momentum convection. Both endpoints precede the
  later failure; this does not show that upwind fixes it.
  [Matched comparison](../results/summaries/rouaix_upwind_20261027/README.md).

Native dependent audits 14656218/19 completed in 45 seconds each. Their
verified compact evidence and separate login-node accounting are preserved.
Compute-node sacct remains unavailable; missing accounting is explicit rather
than represented as zero CPU use. Full result archives remain on Komondor.

## Failure localization and cheap diagnostics

The failure has two distinct events: a brief interior spike at 0.2341 s,
then a sustained ramp from about 0.2511 s at the downstream/top/positive-span
junction. The span boundary is **z = 3.5 - 0.45y**, not a rectangular z=8
wall. The final maximum-U and minimum-p_rgh occur in the same recorded cell.
A zero-simulation extraction of six collated processor blocks subsequently
found **alpha.water=3.19e-143** there, with p_rgh=-89.9 kPa. This is a
near-pure-air final cell; p_rgh is reduced pressure, not absolute pressure.
It does not establish phase at the earlier spike or identify the cause.
[Cell probe](../results/summaries/rouaix_peak_probe_20261027/README.md) and
[computed timeline](../results/summaries/rouaix_failure_timeline_20261027/README.md).

The Mac produced the timeline using installed ParaView Python/Matplotlib,
one CPU, in 3.7 s. Its existing OpenFOAM VM started but guest commands failed
with `No route to host`; it was returned to its prior stopped state. No guest
solver version or compute availability is inferred from VM startup.

Goblin's cached native v2512 solver completed a **100-step all-air pilot** on a 299,520-cell full trapezoidal domain with native
`Mesh OK`, all seven patches and nozzle area within 0.577%. Fixed 0.1 ms,
four MPI ranks, no GPU: 0.01 s reached, maximum speed 75.642 m/s, bulk Co
0.1743, alpha and water volume zero. This is a composition negative control,
not a water reproduction or a paper-resolution mesh.

Measured warm cost was 0.9125 wall seconds/step: a 0.5 s branch projects to
about 75 minutes, exceeding its declared 30-minute cap. The full comparison
has not launched. Its compact metrics and raw log are verified; an output
selector omitted the pilot's final 3D snapshot. That gap is recorded and the
selector is corrected for follow-ups.
[Local pilot](../results/summaries/rouaix_fast_local_20261027/README.md).
The finite local dispatcher is **armed and waiting**, launchd label
`com.firetrack.rouaix-fast-q20261027`, PID 60998. At 12:02:13 UTC its live
sample measured 18.249 busy CPU equivalents on Goblin; no Rouaix solver was
active. It has a shared six-hour capacity-wait budget and requires two samples
at or below 11 busy CPUs plus a final recheck before each eight-rank launch.
All three project PAUSE paths are checked; unavailable checks defer launch.

Its finite sequence is an eight-rank 100-step reprofile, then fresh matched
original/upwind air branches to **0.30 s** only if measured 3000-step solver
wall projects within 1680 s. Each branch has a 1680 s cap and 120 s stop grace,
with no automatic retries. A clean, captured speed-guard terminal permits the
independent sibling; pause, timeout, nonfinite or archive failures stop the
sequence. Fields are collated, terminal snapshots inventoried, and remote
failure data retained if transfer fails. The queued sources are frozen in the
compact local summary. No GPU work or changes to I4F jobs were made.

Independent read-only review found no blocker for these declared cases.
The 94 affected case/runner/local-generator tests, Ruff and formatting checks
passed. Frozen queue scripts also passed syntax and self-checks; the live
resource gate was exercised without launching compute. Full repository checks
were not rerun; unrelated known failures are outside this change.

## Interpretation and earlier performance

No velocity or pressure clamping was added. Native isoAdvection's existing
alpha bounding is retained and explicitly qualified. The transient conservative
alpha minimum (-0.00134 at 0.2281 s) and a smaller solver-log versus
fieldMinMax alpha discrepancy remain diagnostic questions. Stable coarse air
controls cannot rule out fine-mesh or interface-driven instability.

Observed original-scheme short-run whole-job walls were 1839 s at 120 ranks,
2339 s at 96, and 3681 s at 64. Allocated core-hours were 61.30, 62.37 and
65.44 respectively. All reached 0.05 s; host differences limit scaling claims.
[120-rank audit](../results/summaries/rouaix_s1_120_20261026/README.md),
[96-rank audit](../results/summaries/rouaix_s1_96_20261026/README.md),
[64-rank audit](../results/summaries/rouaix_s1_64_20261026/README.md).
The mesh retains its documented exact concavity-set exception and lacks the
paper's five prism layers. Neither appearance, linear convergence nor mass
closure establishes Rouaix agreement. The immediate sequence is cheap local
controls, audited pre-instability checkpoint, then matched full-grid restart
control/candidate comparisons before committing another long horizon.
