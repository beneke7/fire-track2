# Komondor Rouaix status

Updated 2026-10-28 13:45 UTC (14:45 CET). Analytical E0 remains the only
passed gate. All CFD runs here are exploratory.

## Current execution

Targeted diagnosis (28 October13:45 UTC): coarse PTOTAL0 air and water both
completed0.30 s with End/exit0 and verified endpoint archives. The matched
original static-pressure water control reached its200 m/s guard around0.17 s.
Only the four pressure patches differ; injected volume is matched. This is a
working pressure-BC fix on the299,520-cell diagnostic mesh, not an E1 gate.
Water reference:8 ranks,0.1 ms,3,000 steps,1018 solver seconds,peakU103.15 m/s,
alpha[0,1], bulk/interface Co0.262/0.168, phase residual-3.65e-10 kg.
A fixed0.3 ms water pilot also reached0.30 s in1,000 steps and274 solver seconds
(276 supervisor seconds),peak105.32 m/s,Co0.776/0.491,alpha[0,1]. The observed
wall ratio3.72 is not a controlled attribution: the reference overlapped another
8-rank case. Field-level timestep convergence remains untested. No local CFD
is active after the completed bounded cases.
[Matched results and provenance](../results/summaries/rouaix_backflow_local_20261028/README.md).

Native early-save14700220/v2 14700456 finished0.202 s without a signal ack;
source fixes exposed site step-query invisibility, then an owner-format parse
error. Actual public-helper probe14700561 now passed with exact owned-step
SIGUSR2 receipt and acknowledgement before waiting. The corrected helper retains
live-job/owner/task/rank-zero identity checks. V3 native early-save14700599 COMPLETED0:0 in3m35s, with a25 s solver step.
It acknowledged signal12, saved at0.2005 s after5 complete continuation steps,
verified all endpoint fields, End/exit0, incremental ledger and archive.
Auditor14700602 completed in46s. The recovered tested source used only the
helper/test/launcher patch;
the fine pressure candidate remains prepared but unsubmitted. Its actual native
changeDictionary boundary edit/field-hash preflight is still required.
[Cause and test map](ROUAIX_FAILURE_DIAGNOSIS.md). All150 affected tests pass;
Ruff/format pass. Full suite collection is blocked by missingmatplotlib locally.

**No Rouaix solver or follow-up job is running or pending at28 October11:17 UTC.**
V4 smoke14689395 COMPLETED0:0: ten fixed0.1 ms steps from0.20 to0.201 s,
peak111.97527 m/s, all81 configured linear solves converged. Its incremental
mass residual is-6.33e-10 kg, with terminal fields and verified archive. Whole
job wall was4m03s; the solver step used39s. This demonstrates native restart
execution and short continuation, not bitwise equivalence or physical validity.

Control14689396 obtained its full120 ranks across three nodes and FAILED1:0
at09:53:44 UTC after35m47s. It logged658 complete post-restart steps and began
Time0.2659 s, then pressure GAMG raised a floating-point exception on rank12.
Recorded speed grew to2.253e10 m/s. No clean End or verified final fields exist;
no new incremental ledger is available for this failed branch. The1000 m/s
guard requested signal12 but did not secure a terminal checkpoint before the
failure. Raw logs and verified archive are retained. Auditors14689397/14689398
both completed. First guard crossing was0.2625 s at the same reported boundary
point as the prior run (new1033.79 versus old1045.53 m/s). This is not proof of
identical cells or cause; the old final volume peak was a different point.
The posthoc audit finds11 linear-solve criterion failures in U/k/epsilon;
configured p_rgh criterion success does not make the overall run converged.
The historical v4 stop_requested_utc was written after a blocking stop call,
so it cannot establish signal-send timing relative to the FPE. The new early-save
source persists request initiation and successful Slurm acknowledgement before
waiting, and does not list an unacknowledged signal as sent.
The target0.30 s was not reached; this did not fix the prior instability near0.26 s.
No identical retry or pressure candidate has been submitted.
[Verified terminal logs, metrics and audits](../results/summaries/rouaix_restart_controls_20261027/terminal-v4/README.md).

V3 smoke14688328 passed native startup but failed before CFD on literal
checkpoint-time matching. Its saved value0.199999999999994293 differs from0.2
by5.7e-15 s; this is ordinary accumulated floating-point roundoff. V4 parses
the original raw scalar with1e-12 s absolute metadata tolerance, checks finite
values, saved name/index and unchanged deltaT/deltaT0, while retaining source
and field hashes. Control14688329 cancelled without allocation. Both audits
completed; v3 used120 allocated CPUs for2m23s, no solver steps. Compact failure,
raw native time file, accounting and hash-verified audit bundle are preserved.
V4 changes metadata checks/source paths only, with no physics/timestep changes.
The126 affected tests, Ruff, formatting and shell syntax pass; its native
parser accepts the actual saved checkpoint-time file and source hashes match.

V2 smoke14676288 FAILED1:0 in three seconds at27 October18:15:24 UTC,
before Python or CFD. Its launcher quoted the module's argument-bearing
FOAM_BASH as one filename; inspection also found a missing unpacked source-path
component. Control14676290 cancelled without allocation. Both auditors completed.
These are launcher defects, not CFD results. V3 corrects startup/path only;
physics, timestep and resources are unchanged. Actual Komondor module startup,
frozen source hashes and runner --help pass, alongside119 affected tests,
Ruff and shell syntax. V1/v2 source and failure evidence remain preserved.
[Declaration](../experiments/E1_ROUAIX_RESTART_CONTROLS_20261027.md) and
[source/submission evidence](../results/summaries/rouaix_restart_controls_20261027/README.md).
The pressure/backflow-energy candidate remains unsubmitted.

**14669440 (`ml-vof`) COMPLETED 0:0** on one CPU node with 120 ranks.
It reached all **2000 fixed 0.1 ms steps through 0.20 s** on the unchanged
10,099,265-cell mesh. Peak recorded speed was **116.92652 m/s**, with no guard
stop. All **16,001 recorded linear solves** met their configured criteria.
Whole-job wall was **1:55:13**, ending at 13:30:22 UTC; the solver step was
1:51:44. The positive-time checkpoint at exactly 0.20 s is retained, including
collated fields, flux, time state and mesh addressing in the verified archive.

Native afterany auditor **14669459 COMPLETED 0:0** in 46 s. Its recorded
archive SHA is `31010755e705010771de7ed00fb5fb9990e7d2621237c3d881ee22b826cf25c9`,
classified `completed_horizon_converged_exploratory_only`. Login-node sacct
independently confirms both donor terminal states. The donor is complete;
the new restart sequence above is terminal. Other jobs on the shared login are unrelated.
The run stops before the prior 0.2281/0.2341/0.2511 s events, so it does not
establish survival through the failure window or validate the water physics.
The terminal audit records 250.328864 kg injected and a +1.67e-6 kg ledger
closure residual, bulk/interface Co maxima 1.30161/0.96384, and retained
pre-bound alpha and large RANS extrema. These qualify the checkpoint as an
exploratory candidate; no restart equivalence or physical-health claim is made.
[Terminal metrics and receipts](../results/summaries/rouaix_healthy_seed_20261027/terminal/README.md).
[Declaration](../experiments/E1_ROUAIX_HEALTHY_SEED_20261027.md) and
[checkpoint record](../results/summaries/rouaix_healthy_seed_20261027/README.md).

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
about 75 minutes, exceeding its declared 30-minute cap. That original
four-rank 0.5 s pair was not launched. Its compact metrics and raw log are verified; an output
selector omitted the pilot's final 3D snapshot. That gap is recorded and the
selector is corrected for follow-ups.
[Local pilot](../results/summaries/rouaix_fast_local_20261027/README.md).
The finite local dispatcher (PID 60998) advanced after capacity became
available. Its **eight-rank 100-step reprofile completed** with final fields
captured; measured warm solver-clock slope was 0.35122 s/step, projecting
1053.66 s for 3000 steps. That passed the declared affordability gate.

The **all-air original-scheme branch hit the U guard**, ending cleanly at
**0.1752 s**, final speed **1364.74 m/s**. The requested 0.30 s was not reached;
its terminal checkpoint inventory passed and the verified archive was captured.
This shows that high-speed growth can occur without water in this coarse
setup, not that it shares the fine-grid failure mechanism. The matched
**upwind all-air branch also hit the U guard**, ending with a captured
checkpoint at **0.1960 s**, final speed **1221.68 m/s**. Neither air branch
reached 0.30 s. The finite queue is now complete, not waiting or retrying.
Upwind alone did not cure this coarse all-air failure; common boundary,
pressure-coupling, turbulence and mesh effects remain hypotheses for targeted
controls. This is not proof of the fine-grid cause.
[Matched terminal air comparison](../results/summaries/rouaix_fast_local_20261027/terminal-local/README.md).
No GPU work or changes to I4F jobs were made.

The finite sequence retains the shared six-hour capacity-wait budget,
1680 s branch cap plus 120 s grace, all three project PAUSE checks, no retries,
collated field capture and retention of remote failure evidence after failed
transfers. A verified speed-guard terminal permits its independent sibling.

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
