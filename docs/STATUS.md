# Live project status

Updated: 2026-10-15 10:17 UTC. Full shared budget remains 20 available CPUs, CPU-only. Failed long continuation is paused; maxCo=1 pilot checkpointed before the failure point, and the scalar-convection diagnostic is advancing. Code/results were pushed as `656850f`; user expects about 1,300 cluster cores tomorrow.
**Analytical E0 is the only passed gate.** No nearfield, ground, field, suppression or 80–90% reproduction claim is validated.
See [plan](../track2_aerial_drop_experiment_plan.md), [gates](VALIDATION.md) and [sources](REFERENCES.md).

**Numerical stall discovered at status check:** at 08:53 UTC the container was
still consuming about 19 CPU equivalents but had reached only 3.0942804546046 s.
Root's full log scan found no printed-time advancement for the last 6.06 wall
hours. Final completed-step deltaT is 1.8574e-17 s, below the floating-point
time resolution near 3 s, while reported max Courant number remains near 2.
The log contains geometric interface-cut warnings and significant intermediate
alpha defects; their causal role is not established. Earlier ETA is invalid.
Checkpoint-based monitoring did not catch or stop this failure; high utilization
was not useful physical progress. Root suspended only this run's identity-checked
host supervisors/watchers/launcher/client and Docker-paused its container,
preserving RAM state and the 6.4 GB failure log. Unrelated workloads are untouched.

**Latest durable state:** write-now capture completed on Oct 14 at
3.0735945651412 s: all 20 ranks' saved fields finite/bounded, 175,954,077-byte
archive SHA256 `23d32baf14266820a195b13c5a83d397b2704471c2d4ebe283fb2e49fad9de40`.
Exact 1,838-row native prefix passed both 0.1% operational guards; incremental
residual -0.00043527636 kg, cumulative -0.01207418851 kg. These results precede
the numerical failure and do not validate its later state.

**Recovery work:** Luna execution worker owns the failure timeline/diagnosis,
a stall/throughput guard that works between checkpoints, and a bounded restart
experiment crossing the failure time from the saved state. No unpause of the
failed container or blind long continuation. Luna observer worker owns actual
native profiles and a compact CPU plot from the good checkpoint. Initial shared
allocation while both compute: diagnostic CFD 19 CPU equivalents plus analysis
1, then CFD can use 20.
The pilot `rouaix-c4-stall-pilot-maxco1-20261015T090213Z` ran in container
`rr-rouaix-c4-stall-pilot-maxco1-20261015T090213Z` (`49bdf3722987`), with
20 MPI ranks. It restarts at 3.0735945651412 s, changes maxCo 2->1 only
(plus endTime 3.12), and has a 60-minute limit. At 09:11:48 UTC it reached
3.076562 s, dt 2.66e-5 s, epsilon bound about 9.08e4 and final alpha [0,1].
It did not cross the original failure time, so no fix is established. New
guards monitor wall time, timestep/ULP, stagnation, epsilon, alpha and resources
between snapshots. The frozen main guard misparsed `max:` and has null Co;
an independent corrected sidecar covers subsequent Courant spikes, with
its coverage start and original loaded source hash preserved. The CFD quota
was restored 19->20 after observer completion; root verified the running,
unpaused container's 20-CPU quota and no OOM. At 09:12:18 worker observed
3.076801 s and about 19.84 CPU equivalents in use.

At 10:04:39 UTC the worker sent verified SIGUSR2 to all 20 solver ranks to
write and stop before the one-hour limit. Exit was 0 at 3.0851454757947256 s;
dt had declined to 5.45485e-6 s and epsilon bound was 112,180, with final
alpha [0,1]. No guard fired. The exact 1,070-row ledger passed both 0.1%
guards (incremental residual +7.82e-11 kg, cumulative -0.0120741884 kg).
The finite/bounded 20-rank checkpoint is archived: 176,492,636 bytes, SHA256
`9c4d8f58af27f22208ea52bf3aaf21d27cc92fc34077ae3782b8fc29cd293415`.
This result does not establish that lower maxCo prevents the numerical runaway.

Next bounded branch: restart from the same 3.0735945651412 s parent, restore
baseline maxCo=2, and change only k/epsilon convection to first-order upwind.
Keep physical inputs, mesh, momentum and pressure controls fixed; add compact
field-extrema diagnostics. This is a transport-sensitivity experiment, not
adoption of a more diffusive paper model. This branch is now running as
`rouaix-c4-turbulence-upwind-pilot-20261015T101327Z`, container
`rr-rouaix-c4-turbulence-upwind-pilot-20261015T101327Z` (`05eb04aaf234`),
with 20 MPI ranks, hard 20-CPU quota, 48 GiB memory cap and a 90-minute limit.
Root verified running/no OOM and advancement to 3.074108 s; worker later
observed 3.074334 s. Field-extrema diagnostics registered. Reported max |U|
about 1,229 m/s and max nut about 19.55 m2/s are extreme relative to the
imposed source/freestream and raise concern that the pre-stall checkpoint is
already numerically compromised. Finite fields and mass closure establish
checkpoint integrity, not physical credibility. The worker is investigating
locations/earlier onset without capping or clipping fields. Courant/alpha/dt
and progress guards are active; epsilon's old bounding-line metric is null
when no bounding message occurs, so direct-extrema coverage needs explicit
verification. No numerical remedy or failure-time crossing is established.
The worker owns this ignored run only; no automatic extension of the prior
pilot is authorized. Initial budget is all available 20 CPUs.

**Publication and cluster readiness:** compact tracked evidence is selected in
`results/summaries/rouaix_20261015/`; raw fields, archives, bulk logs and runs
remain ignored. Full `make check` passed 649 tests, one skip and four subtests,
with Ruff lint/format clean. A subsequently fixed source-container inspection
guard has three additional passing regression tests and affected Ruff checks;
unknown Docker state now blocks copying rather than assuming stopped.
Legacy checkpoint monitoring alone does not detect between-checkpoint stalls;
the trial's run-scoped progress guards are a separate mechanism. Local full
disk runs still require their declared 60 GiB; current free disk is about 6 GiB,
so recent trials explicitly use RAM-backed storage with guarded durable captures.
Cluster scheduler is probably Slurm; OpenFOAM is not expected preinstalled.
Environment, MPI/container support and node layout are unverified. The short
handoff sequence is in `docs/COMPUTE.md`; no cluster launch or scaling result
is claimed. Published numerical results are exploratory, not a passed E1 gate.

Durable pre-failure log tails show epsilon bounds growing from O(1e5) to
O(1e10) and eventually above 1e25 as dt collapses. This is evidence of
numerical runaway; it does not establish whether turbulence, momentum/pressure
or interface transport initiates the instability.

**Previous 20-rank launch (now paused):** `make doctor` reported 20 effective CPUs, 92.6 GiB
available memory and 16.3 GiB free disk; a short vmstat sample confirms 97–99%
CPU idle. Unrelated research workers are paused and untouched. Luna execution
worker launched a fresh continuation from the audited, durable 2.750234 s
checkpoint toward 5 s with all available CPU capacity. The old paused
container's 24-hour wall deadline has expired; do not blindly unpause it.
Reconstruction and the 20-rank checkpoint validation passed; the physical mesh
is unchanged and all required fields are finite. The fresh run is
`results/runs/rouaix-c4-reproduction-5s-continue-20261014T114815Z`.
Container `rr-rouaix-c4-continue-5s-20261014T114815Z` (CID `f979d449279c`)
is running unpaused, with 20 MPI ranks, hard 20-CPU quota and 48 GiB memory cap.
Root independently verified advancing solver time beyond 2.754 s, no OOM and
1984% Docker CPU use (about 19.84 CPU equivalents), with about 7.2 GiB RAM.
Worker later observed 2.755917 s and verified all 20 actual solver identities
and signal handlers. The fresh 24-hour deadline, supervisor and durable ledger
capture are active. Physics/time controls remain unchanged; inherited metadata
was corrected for the downward source, immediate restart and available storage.
Small logged alpha undershoot (~-1.53e-10) remains recorded and unclipped;
no new completed-checkpoint mass-closure pass is claimed yet. Old paused runs
and their durable checkpoints remain untouched. Workers have handed off; the
detached solver and monitoring processes continue.
At 13:43 UTC root observed continued advancement to about 3.072 s, about
18.9 CPU equivalents and 7.38 GiB memory. Recent 10/30-minute throughput is
0.125/0.134 physical seconds per wall hour, suggesting about 14–15 hours
remaining if those rates persist; adaptive stepping makes this provisional.
Latest complete durable checkpoint remains 2.750234 s, with the child's next
scheduled field write at about 3.250234 s. Execution worker is requesting a
write-now checkpoint and exact native-ledger capture at the current time;
no new checkpoint or mass-guard result is claimed until that handoff verifies it.

**Rouaix observer prepared:** `scripts/analyze_rouaix_profiles.py` reports
native-center-binned x profiles using native cell bounds: full alpha>=0.1 cloud
and separately alpha>=0.9 core connected through native faces to source-owner
cells. Rouaix axes are x streamwise, -y downward and z spanwise; full width,
signed edges, source origin and actual field times are explicit. Five synthetic
tests and affected Ruff checks pass. Primary inspected implementation and tests.
The adapter now processed the actual 3.0735945651412 s native checkpoint.
Whole-field alpha-volume agrees with saved inventory within 6.1e-14 m3.
The queried full cloud reaches 9.5 m depth and 4.86375 m full width; the
source-connected core reaches 4.0556 m depth and 0.5523 m width. A selected
cloud cell outside the queried x range touches the domain bottom at y=-10 m.
Profiles differ substantially from digitized Fig. 13; detached-lobe selection,
coarse Case 4 versus fine Case 1, unspecified paper timing/detector and
full/half-width ambiguity remain explicit. This is not a paper match or pass.
Evidence/plot: `results/runs/rouaix-observer-actual-3p0735945651412-20261015/`.
Six focused tests plus affected Ruff checks pass; root inspected the actual plot.

**Previous user-requested pause (superseded by resume):** root suspended the identity-checked RAM-run
launcher, Docker client, supervisor, monitor and capture-watcher processes,
then paused the active Rouaix container. Both current Rouaix containers are
verified Docker-paused; the older MULES container was already paused. The
latest solver log records 2.8369603592316 s; the complete 16-rank
2.750234439187 s checkpoint is durably archived (173,285,849 bytes), with
1,293-row native audit/raw prefixes and both mass guards passing.
Later in-memory state and RAM fields remain preserved while the machine stays
up, but are not reboot durable. Existing wall-time deadlines must be checked
before resuming; do not blindly unpause after an expired timeout. The execution
worker completed read-only verification and recorded `pause-evidence.json`
in the RAM-resume run; no solver resume or new launch occurred.
Unrelated workloads were left untouched. The continuation plans below are active again.

**Overnight results and failure:** the isoAdvector baseline reached its declared
wall timeout (exit 124), retaining a complete, finite, bounded and exactly
audited 2.250234439187 s checkpoint. Both unchanged 0.1% native water-ledger
guards passed. The queued child from that checkpoint advanced only to about
2.252 s before its launcher stopped it (exit 137, not OOM). The startup detector
matched launcher command lines containing the solver name, counted 19 entries
and rejected the rank/handler check. This was a supervision bug, not evidence
of unsupported signals or a CFD mass failure; original logs and attempts remain.

**Live CPU continuation:** run
`results/runs/rouaix-c4-reproduction-5s-ramresume-20261013T081725Z`, container
`rr-rouaix-c4-ram-20261013T081725Z` (CID `b262ba663eb6`), advances from the
preserved 2.250234439187 s checkpoint toward 5 s. Root verified the hard 10-CPU
quota, shares 512, 48 GiB memory cap and advancing solver time beyond 2.279 s;
worker later reported 2.315561 s. The unchanged 2,733,120-cell mesh retains
16 MPI ranks with idle yielding enabled. Detection now uses exact actual solver
process identity and a bounded startup wait; all 16 signal handlers were checked.
Physics, turbulence and timestep controls remain unchanged.
At 09:20 UTC root verified the container remains running, without OOM, with
the 10-CPU quota. Live nozzle-owning ranks use (0,-10,0); gas is (70,0,0) and
gravity (0,-9.81,0). A positive liquid-velocity sign in the declaration is a
metadata error only, documented in the run's `metadata-erratum.json`; original
declaration and hashes remain intact.

**Next scientific comparison:** finish the existing 5 s continuation before
another heavy launch. Compare full alpha=0.1 cloud profiles and separately
source-connected alpha=0.9 core profiles at common streamwise stations, with
actual snapshot times and explicit full/half-width conventions. Existing output
cadence is restart-offset, so an exact 4.5 s frame is not guaranteed. Test late
window stability before treating profiles as established. Compare the paper's
coarse Case 4 separately from fine Case 1; cross-case curve fits and fragment
counts are secondary diagnostics. Next candidates are pilot-guided static
refinement through the fragmentation corridor and a longer matched transport
branch, keeping source geometry/flux and other physics fixed. Short restart
branches establish sensitivity, not independent grid convergence or a gate pass.

The SSD had only about 4 GiB available, so bulky case files, fields and logs
live in `/dev/shm/fire-track2-1000/` under a declared RAM-storage policy.
Scratch cap is 16 GiB, host available-memory floor 24 GiB and wall cap 24 h;
Docker log spool is bounded to 10 MiB x 2. Bulk RAM outputs do not survive
reboot unless separately captured. The original disk checkpoint remains intact.
Completed checkpoints can produce unique compressed field archives <=500 MiB
only if at least 2 GiB disk remains afterward. Exact audit JSON, declaration,
CSV and all eight closed native-history prefixes are captured within a 50 MiB
metadata budget and 1 GiB disk-write floor. CPU allocation drops temporarily
for audit/capture and restores the observed quota without overriding another
resource change. Native mass and alpha quality guards remain in force; the
old 60 GiB bulk-disk guard is replaced explicitly by RAM/durability guards for
this trial, rather than claimed satisfied. Five PID/handler fixtures and six
capture fixtures, Ruff and compilation passed. Root inspected the live container
and computed comparison image. The actual write-now integration check passed:
all 16 verified solver ranks received SIGUSR1 and wrote a common, finite and
bounded checkpoint at 2.3234980328013 s. Its 157-row exact native audit passed
both guards (incremental residual -1.664e-5 kg, cumulative -0.011518 kg).
A 173,321,542-byte field archive and the audit/report/declaration/CSV plus eight
original raw prefixes were durably saved. The capture quota changed 10->9->10
and the solver continued advancing. Evidence:
`write-now-outcome-20261013T0842Z.json` in the RAM-resume bundle. Thus 2.323 s
is now a durable checkpoint; later uncaptured RAM state remains ephemeral.

**Matched transport result:** the four-rank isoAdvector and MULES branches both
completed at 1.800234439187 s from byte-identical initial alpha fields and the
same mesh, source and physical inputs. Native source addition matched at
0.06185345 m3. MULES retained 47.79 kg more liquid and escaped correspondingly
less during the 0.05 s window; its incremental residual was +0.006132 kg
(0.00994% of added source), versus -5.85e-7 kg for isoAdvector. Both operational
mass guards passed, but MULES had small unclipped alpha excursions.
With the existing six-face/source-seeded observer at alpha>=0.1, iso/MULES
detached selected mass was 225.6/35.6 kg and connected penetration 4.715/5.201 m.
At alpha>=0.9, connected penetration was 4.299/3.813 m. These substantial
transport/observer differences are transient numerical sensitivity, not an HRIC
reproduction or settled paper match. Native fields, mesh hashes, metrics, width
profiles and a computed equal-scale image are recorded in
`results/runs/rouaix-transport-analysis-20261013/`.

**Storage:** authorized cleanup removed one verified 1.5 GB duplicate preparation
case, unused driver and aerial-drop-TDK environments, and 14 exact orphaned
driver-lock package-cache archives. The TDK environment is not a Fire-Track
dependency; both projects' source, results and locks remain. Shared cache
archives, original toneking and other projects' data were preserved. About
10.4 GB was recovered; free space rose to 14.83 GB but then fell to about 3 GiB
while Fire-Track usage and its Docker writable layer remained small. The cause
of external growth is unresolved. Record:
`results/runs/storage-cleanup-20261013T082855Z.json`.
Filesystem statistics also show about 200 GB free but unavailable to this user,
likely ext4 reserved space; no filesystem reserve was changed. Large visible
other-project datasets/backups are inventory findings, not deletion approvals.

**Earlier user-requested pause:** both active Rouaix containers were suspended, verified
by root via Docker's `Paused` state and 0.00% CPU. Host workers/docker clients
are suspended and monitors terminated, preventing automatic follow-on work.
The latest log times retained in memory are 1.892427084412 s (16-rank baseline)
and 1.783232739017 s (4-rank MULES); both latest complete disk checkpoints remain
1.750234439187 s. Logs, native histories and all existing fields are preserved.
Immediate write-stop signals were disabled at startup and both cases have
`runTimeModifiable=false`; no new disk snapshot is claimed for paused memory.
Memory progress does not survive reboot/container removal. Embedded GNU timeout
deadlines can become pending during suspension, so do not blindly unpause after
their original deadlines; a fresh continuation from the retained disk checkpoint
is the fallback. Enable a supported checkpoint-stop mechanism before future
launches. The evening resume authorization supersedes the pause. Exact process,
checkpoint completeness, existing ledger audit, signal configuration and resume
caveats are recorded in each run's `pause-evidence.json`:
`results/runs/rouaix-c4-reproduction-5s-20261012T1000Z/pause-evidence.json` and
`results/runs/rouaix-c4-vof-transport-pair-20261012T0939Z/mules/pause-evidence.json`.

**Earlier CPU diagnostics:** The 16-rank, 2,733,120-cell Rouaix continuation
`results/runs/rouaix-c4-cont-1s-20261006T0909` completed 1.0 s at 10:00 UTC;
solver and reconstruction exited 0, alpha remained bounded and saved fields
were finite. Its declared 0.1% water-ledger guard failed: cumulative discrepancy
was −5.7925 kg (−0.4694% of prescribed release, using released minus stored
minus escaped). This ledger measures five exterior patches but assumes the
inlet discharge; it cannot yet identify transport error versus source or
accounting error. The failed attempt and analysis are retained.
Three CPU diagnostics completed from the same 0.600 s checkpoint. All seven
boundary phase-flux histories confirm the source flow, with negligible roof
flux. The four-rank dt=0.001 s repeat has a 1.609 kg maximum step discrepancy
and −1.984 kg cumulative residual over 0.600–0.620 s. The 16-rank dt=0.0005 s
repeat reduces these magnitudes to 2.71e-5/3.08e-5 kg. A 16-rank adaptive
maxCo=2/maxAlphaCo=1 trial closes to 8.77e-6 kg maximum step residual and
7.68e-6 kg cumulative residual, with 77 steps versus 40 for fixed half-dt.
It reaches 0.62006026 s, and accounting uses actual step durations. Adaptive
and fixed half-dt outflow differ (0.01088/0.00602 m³); good conservation alone
does not establish a converged trajectory. The fixed pair also differs in
MPI count; the original failed run was itself 16 ranks. Evidence points to
high-Courant time-sensitive transport rather than incorrect inlet flow, but
does not prove clipping alone is responsible. See
`results/runs/rouaix-c4-stepclosure-t604-mpi4-20261006T1010Z/matched-window-closure-audit.json`.
All three solver/reconstruction exits are 0; saved final alpha is bounded
and required fields are finite. Continuation lint/format and four targeted
tests passed; independent ignored audit scripts compiled and completed.

The adaptive continuation in
`results/runs/rouaix-c4-adaptive-1p5-20261006T1049Z` completed at
1.5000193048 s with all stages exiting 0 and solver ClockTime 10102 s
(2.81 h for the 0.4–1.5 s extension). Root inspected the terminal log.
Its cached runtime and ledger summaries are partial, ending near 0.760/0.711 s.
The refreshed raw-history audit covers all 2707 steps through the terminal time:
released 1851.173824 kg, escaped 1098.428699 kg, stored 752.756488 kg;
cumulative residual −0.011363 kg (−0.000614% of release), including the
parent's −0.011001 kg residual. New continuation residual is −0.000362 kg.
All saved required fields are finite and alpha is bounded. Fresh audits live
in `results/runs/rouaix-c4-continue-5s-20261007T153256Z/preflight`; original
partial reports and raw parent inputs remain unchanged. Large local speed
maxima (345 m/s near 0.6 s, 200 m/s at 1.5 s) need phase/location inspection;
finite fields and good closure do not prove those velocities physical.
The quarter-step morphology comparison
completed: fixed half/quarter steps give source-connected core depths
4.229/4.299 m at 0.620 s; detached cloud mass is 221.97/215.86 kg at alpha>=0.1.
This is a transient cell-threshold observer with rank and seed limitations,
not a paper breakup validation. Geometry evidence is in
`results/runs/rouaix-c4-event604-quarterdt-20261006T1046/geometry-comparison-retry01`.

**2026-10-12 inspection:** The five-second target was not completed. The retry
advanced to 1.76961990362 s before the checkpoint monitor stopped its container
on 2026-10-07 at 16:28 UTC (exit 137, OOMKilled=false). At the first 1.750234439187 s
checkpoint, the monitor copied the legacy preflight auditor against the new
continuation metadata; three attempts raised `KeyError: checkpoint_inventory`.
This was an audit implementation failure, not a measured mass-guard violation.
Original failures and raw output remain preserved. The complete 1.5 s run is
still the latest fully audited CFD result. Offline recovery now audits the
exact shared 1.750234439187 s checkpoint row: 660 rows included and 38 later
rows excluded. Incremental mass residual is −7.05134e-6 kg, cumulative residual
−0.0113701 kg (−0.0005264% of release); both unchanged 0.1% operational guards
pass. The copied schema-aware auditor/monitor replay and focused regression
passed in `results/runs/rouaix-checkpoint-audit-recovery-20261012T085240Z`.
This recovers accounting evidence, not a completed five-second run or E1 pass.

The completed analysis in `results/runs/rouaix-results-cpu-20261007T153625Z`
contains a computed still and 10x slowed saved-field video (`final02` versions).
At 1.5 s, the source-connected alpha>=0.1 cloud reaches 4.715 m depth and
contains 229.25 kg of detached threshold-selected water; these are cell-mask
observations. The transient penetration overlay differs substantially from
the published multi-case fit and is not a matched steady-state acceptance test.
The 199.78 m/s peak is almost pure air at (15.75, −0.259, 3.549) m;
alpha>=0.9 cells have maximum speed 27.86 m/s. Air-domain/boundary behavior
still needs inspection, but this peak is not bulk-liquid speed.

**Cleanup completed:** the authorized duplicate `/home/v/proj/toneking_` was
verified against the original (Git identity, source hashes, dirty inventory,
inactive paths) and deleted, freeing about 107 GiB. `/home/v/proj/toneking`
and its edits remain intact. Generated run storage fell from 321 to 256 GiB
before new run writes: 64.6 GiB removed, consisting of redundant GPU image
exports/layers and verified duplicate legacy processor fields. Rouaix bundles,
reconstructed wave fields, flux histories, key snapshots, failure evidence,
sources and root PDFs remain. Historical GPU replay now requires rebuilding
the removed image exports; source and digest evidence remain. No global Docker
prune was performed. Retention evidence is in
`results/runs/storage-cleanup-20261012T0937Z.json`; the 27 affected archive-tool
tests passed. Root measured 175 GiB available after new run writes.

**CPU experiments before the pause:** `rouaix_execution` launched the 16-rank,
2,733,120-cell baseline in
`results/runs/rouaix-c4-reproduction-5s-20261012T1000Z` at 09:37 UTC.
It restarts from the exact audited 1.750234439187 s checkpoint, targets 5 s
within a 12 h budget and writes full fields about every 0.5 s while retaining
inventory and all seven native boundary phase fluxes every step. Root inspected
solver progress at 1.88373563495 s and bounded alpha at 10:08 UTC. Completion
time remains throughput-dependent; the target is not yet achieved.

The paired four-rank isoAdvector control completed at 1.800234439187 s with
solver/reconstruction exit 0 and exact seven-boundary audit passing both
unchanged 0.1% operational mass guards. Incremental residual is −5.85e−7 kg,
cumulative residual −0.01137066 kg. Stock interFoam/MULES ran from its
own copy of the same initial checkpoint, with identical mesh, physical inputs,
realizable k–epsilon and adaptive controls. Root inspected native
`alphaPhi0.water` fluxes and progress at 1.767731188862 s. Small alpha excursions
(reported minimum about −2.96e−4, maximum about 1.00011) remain quality flags;
the predeclared gross-stop bounds are −1e−3/1.001, and no clipping is applied.
Paired records and durable supervision live in
`results/runs/rouaix-c4-vof-transport-pair-20261012T0939Z`.
Shared allocation is 16+4 MPI ranks against 20 effective cores. Docker measured
about 17.2 cores in use and 11.7 GiB combined RAM at the inspection instant.
Cleanup, mismatch-review and execution workers finished their handoffs.
Solver processes have independent supervision.

The monitor now audits only the exact closed history prefix through a saved
checkpoint, so incomplete future writer tails cannot falsely stop a healthy
run. Missing or mismatched rows within that prefix still fail. Stable audit
and monitor templates are versioned in `scripts/`; original historical recovery
code was restored to its manifest hash, and active fixes retain provenance.
Focused audit/continuation tests passed 9/9, with lint, formatting, compilation,
CLI and helper-copy smoke checks. Restart fields still depend on retained local
ignored inputs, explicitly recorded rather than implied available in a fresh
checkout. The combined post-change `make check` passed lint, formatting of 120
files, 643 tests and four subtests; one opt-in Docker cgroup smoke was skipped.
Root inspected `results/runs/rouaix-final-make-check-20261012T100824Z/make-check.log`.

**Matching priorities:** root verified the paper's 4.5 s captions for Figs. 5
and 8 and approximately 5 s stabilization statement (PDF pp. 8–10); Fig. 13
time remains unspecified. The current 1.5 s penetration overlay is not a
matched settled comparison. The paper uses STAR-CCM+ HRIC interface transport;
neither isoAdvector nor stock MULES implements that exact scheme. The pair
tests transport sensitivity without changing the physical inputs, and is not
an HRIC reproduction. Next compare penetration, width and breakup with explicit
time/threshold/observer definitions, then refine the fragmentation corridor if
the mismatch persists. Near-wall mesh/body shape and incompletely specified
inlet turbulence remain further uncertainties. Research evidence is in
`results/runs/rouaix-mismatch-review-20261012/mismatch-review.json`.
Good conservation is numerical evidence, not an E1 or paper-match pass.
GPU work stays disabled.

**Exploratory CPU diagnostics completed 2026-10-05.** Six periodic finite-shear cases reached 0.012 s on 55,296- and 186,624-cell meshes. Advection controls retained 0.998/0.999 mode amplitudes, molecular-shear cases ended at 0.252/0.0473, and added ν=0.01 m²/s cases grew to 4.37/4.40. Alpha stayed bounded and water-volume drift was <1.53e-12. These are not plume evidence: displaced interfaces plus flat-z tanh U and zero normal velocity do not seed an unstable eigenmode; 3/4.5 cells per shear thickness leave fitted slopes transient-prone and unresolved. See the [six-case summary](../results/runs/cpu-interface-growth-20261005T203214Z/summary.json).

Stock MULES `interFoam` reached 0.6 s on 670,480 cells (16 ranks) against matched `interIsoFoam` at 20 ranks; physical inputs and mesh match, rank count differs. At α≥0.001, MULES/iso had 7/1 face components and 2.285/1.729 m maximum width; at α≥0.9 they had 1/25 components and 0.776/1.412 m width. Ledger: 2,934.318 kg source flux vs 2,935.262 kg prescribed, 2,934.211 kg final inventory, −0.1071 kg closure residual. Saved MULES alpha minimum was −8.49e-6 in 71,285 cells (0.000115 kg negative-equivalent mass). See [ledger](../results/runs/dash8-focused-cpu-transport-mules-20261005T201626Z/mules-ledger/summary.json), [paired metrics](../results/runs/dash8-focused-cpu-transport-mules-20261005T201626Z/transport-comparison-v1/paired-metrics.csv) and [figure](../results/runs/dash8-focused-cpu-transport-mules-20261005T201626Z/transport-comparison-v1/dash8-iso-vs-mules-t0p6-central-strip.png).

The saved-field observer corrected x-origin by +2.22 m and analyzed t=0.1–0.4 and 1.0 s fields. At 1 s, coarse/refined water volumes were 5.1715/5.1972 m³. Figure 6/7 digitizations support Lc≈1.155 m, consistent with √1.332 m²=1.154 m; this is inferred, not measured. Retain provisional source area 1.332 m². See the [corrected analysis](../results/runs/dash8-interface-growth-analysis-20261005t205338z/analysis.json).

**Current operations:** The user authorized the next step: a checked initial
instability mode and better-resolved CPU wave runs. Three reused Luna Max
workers completed the variable-density linear reference, MPI-capable wave runner
and independent native face-flux/amplitude audit; one worker now owns the
Rouaix pilot and follow-on. Three 1,048,576-cell CPU
profiling cases completed 50 steps to 0.0002 s with 4/8/16 MPI ranks:
solver wall times 86/55.5/46.7 s, with peak recorded memory below 2.5 GiB.
Native phi/divPhi fields were saved and reconstructed; root inspected the
8-rank terminal log. Independent 4-rank face-flux reconstruction agrees with
saved divPhi within 1.22e-7 s⁻¹, consistent with ASCII flux precision; water
volume varies by 6.6e-19 m³ across writes. These mixed-seed profiles measure
performance, not instability growth. The matched 0.05 mm, 1,048,576-cell
uniform-advection control completed on 4 ranks to approximately 0.002 s in
`results/runs/cpu-interface-growth-v2-advection-control-20261006T0835Z`.
Retained Docker inspect shows exit 0; post-removal Docker wait did not capture
the control exit. Measured mode retention was 99.9974%, relative
volume drift 2.64e-15 and phase-speed error about 0.012%. Root inspected the
summary and computed-field image. A draft cell-centre contour observer's
42% under-read was fixed by cell-to-vertex reconstruction; the independent
profile observers now agree within 0.03%.
The corrected even-mode run completed 0.012 s on 16 ranks, with reconstructed
fields, analysis and Docker exit 0 evidence in
`results/runs/cpu-interface-growth-v2-eigen-main-20261006T064154Z`, using the
copied, hashed reference from
`results/runs/interface-stability-reference-20261006T063400Z`. Independent
ODE, interface-jump, phase and coordinate checks support this exploratory
seed; its inviscid growth is 313.732 s⁻¹, not a viscous CFD acceptance target.
Root inspected actual solver progress and boundedness/continuity. At the
complete 1.99996 ms snapshot, mode amplitude grew by 1.86796 versus the
inviscid prediction 1.87283; water-volume drift was 6.90e-10 and alpha was
bounded. This is a two-point early transient comparison, not a fitted growth
rate or validation pass. Its exploratory 6–8 ms growth fit is 312.357 s⁻¹
versus reference 313.732 (−0.44%); phase rate −273.973 versus −305.732 rad/s
shows a larger discrepancy. Final amplitude is 2.062 mm and outside the
initial small-disturbance regime. Measured utilization while main and control ran was
about 15+4 cores and 5.5 GiB combined.
Interactive wrappers exited 143 while solvers continued; detached supervisors
recovered control completion, captured Docker exit evidence and retained the
original main deadline. All three durable follow-ons completed with exit 0:
spanwise-collapse comparison, 12-cells-per-shear-thickness x/z refinement,
and a declared added-viscosity sensitivity. Fine/surrogate growth fits were
315.009/308.824 s⁻¹; the constant viscosity surrogate is not RANS. The reduced span
applies only to a y-invariant diagnostic; equivalence is not assumed.
Reference, runner and independent audit checks passed 6+16+12 tests, lint and
formatting. GPU use is disabled. The fine reference and older broad queue
remain held.

**Rouaix next larger case:** Fast-forward pull to `90b99a1` added
`Rouaix_28516.pdf`; its hash matches the earlier extraction exactly. A Luna
worker completed the source review, and another prepared an executable
CPU pilot using the existing static physics dictionaries. Table 3 Case 4 supplies
the same single-nozzle physics as Case 1 at 70 mm, a useful paper-defined coarse
precursor to 16 mm: 0.4 m round nozzle, 10 m/s downward water, 70 m/s air,
realizable k–epsilon, gravity and surface tension. A 1,858,560-cell pilot
completed 0.03 s on four ranks with solver/mesh checks passing; solver time
was 291 s. Native cell-volume integration gives 37.023 kg stored and released
water, relative residual 1.97e-11, bounded alpha and finite saved fields.
The source raster area is 1.56% below the ideal circle, measured rather than
corrected by changing velocity. An earlier offline volume-ordering error and
four setup failures are preserved; they are not physical mass-loss evidence.
The structured mesh and flat no-slip roof remain provisional differences
from the paper's polyhedral/prism mesh and curved roof.

A new 0.4 s run was launched at 07:26 UTC in
`results/runs/rouaix-c4-0p4-20261006T072500Z-retry01`; it completed 0.4 s
with mesh/solver/reconstruction exit 0. It extends
the fine corridor to x=6.5 m and depth 6 m, preserving the source resolution,
with 2,733,120 cells. Source patch area and flow match the pilot exactly.
Native phase inventory and all five exterior water-flux writers execute.
Solver ClockTime was 3215 s. Released mass is 493.640 kg; stored plus net
escaped mass is 493.651 kg, a 0.00223% ledger discrepancy with recorded
flux quadrature. Alpha is bounded and saved U/k/epsilon/nut are finite.
It retained the four-rank allocation originally shared with the wave case;
wave work is now complete. A bounded 16-rank, 0.05 s matched scaling trial
was launched in `results/runs/rouaix-c4-mpi16-scale-20261006T081700Z`.
The hash-identical copied mesh passes checkMesh, its source area is unchanged,
and the 16-rank run completed 0.05 s with exit 0, ClockTime 297 s, bounded
alpha, finite fields and ledger residual 4.87e-10 fraction. At the shared
0.025–0.05 s interval, four/16-rank clocks were 276/95 s (2.91x throughput);
0–0.05 s clocks were 468/297 s (1.58x including startup). These are actual
overlapping-workload measurements, not isolated scaling or a cluster
guarantee. Root previously measured 1460% + 399% CPU during overlap.
The runner now supports 4/16/20 ranks with
matching decomposition and manifest-derived MPI launch; lint, compilation
and decomposition smoke checks passed. Subsequent jet allocation can use
up to 20 ranks after measured scaling and active-workload checks. Avoid an
expensive restart of the nearly complete four-rank run solely to increase
its rank count. A 20-rank, 0.05 s comparison is now starting in
`results/runs/rouaix-c4-mpi20-scale-20261006T0858Z`, with hash-identical mesh
and unchanged source/physics; its solver and reconstruction completed with
exit 0. It measured about 19 cores and 7.3 GiB. The common 0.025–0.05 s
interval took 133 s, versus 95 s for 16 ranks and 276 s for four ranks;
20 ranks did not improve this measured interval. Prefer 16 ranks for the
next continuation, pending further evidence. The separate checkpoint driver
passed its 0.4–0.405 s restart check and three regression checks. It preserves
parent inventory/outflow and absolute time; right-endpoint native flux
integration matches the solver steps. The subsequent 1 s continuation and
its failed ledger guard are recorded above. Old fine solver PIDs were
confirmed frozen with unchanged CPU ticks and their job remains paused.
The completed 0.4 s run's separate prelaunch refinement record links
the unchanged pilot guard; physics and source resolution are retained, while
the corridor mesh changes explicitly. The first 0.4 s attempt was stopped
after its first startup step to correct an inherited two-hour stage timeout;
logs and exit 137 are preserved. The retry uses the declared three-hour
budget. Native per-step boundary liquid flux is configured for its ledger;
missing output will leave the longer ledger incomplete rather than assume
zero escape. Air turbulence intensity 1% is assumed; the paper's 1% value
belongs to the liquid inlet. The 0.4 s test addresses early breakup and width, not the
paper's roughly 5 s stabilized statistics. The CPU still at 0.4 s is in
`render/rouaix-case4-alpha-t0p4-center-and-span-mean.png`; root inspected it.
Its central cut has a bent connected column and detached fragments; these
are early morphology observations, not three-dimensional breakup locations.
Global threshold extents include outliers and do not define main-column
width. The central-layer source-connected masks end at depths 4.229 m
(alpha>=0.1) and 4.160 m (alpha>=0.9), explicitly two-dimensional observations.
The full-span mean has maximum alpha 0.0735 and is displayed with its own
0–0.08 scale; it is not a paper cloud contour. The earlier renderer failure was an incorrect
dimension expectation for the valid cell-center field C; the failed attempt
is retained. Runner lint/format/compilation passed. No new formal gate passed;
no GPU jobs were launched.

**New source:** Fast-forward pull to `d23b73d` added the user's
`yumeng.et.al.pdf`, preserving local work. Shi et al. (2026), DOI
10.1063/5.0311627, describes hybrid VOF–DPM, AMR and a small jet-in-crossflow
comparison using SST k–omega and surface tension (PDF pp. 7–8). A reused
Luna worker completed extraction of transfer criteria and numerical/source
gaps in `results/runs/yumeng-paper-next-step-20261006a/yumeng-paper-evidence.json`.
The reported micro-jet cost is roughly two weeks on 12 cores for 0.1 s;
smaller dimensions alone do not imply an inexpensive benchmark. Printed
timestep and height-sweep conflicts remain unresolved. No paper-derived
physics or transfer thresholds have been adopted yet.

**Retained pause history:** Fine and pair/fine supervisors remain held; watchdog budgets were not reset. See [pause actions](../results/runs/user-discussion-pause-20261005T143009Z/pause-actions.json). Detailed compute/queue sections below retain earlier snapshots; this opening records current state.

## Compute and queue

Local uniform completed at 10:42:19 UTC: exact 1 s checkpoint, solver End
and exit 0. Three-component variant launched at 10:42:31 UTC, advanced to
0.827767 s at 14:11 UTC after resuming from the instrumented tank trial. At
14:13:28 it was temporarily paused for the first authorized head trial, which
uses twenty MPI ranks; the fine baseline remains paused. Its epsilon solve
used two iterations but reported negative pre-bounding values and a high
maximum; this is recorded separately from finite saved fields, not a failure
declaration. Uniform terminal native analysis and GPU still renders are
complete; the computed-field slowed video is now complete and root inspected
its t=0 and t=1 frames. Initial internal alpha is zero and the first frame has
no liquid contour. The 09:10 resource sample
measured 19.8 core equivalents and 5.54 GiB; these are observations, not an ETA.
Actual machine capacity: 20 effective CPU cores; OpenFOAM v2512 pinned image;
RTX 5090 used for rendering. No GPU CFD implementation is qualified.

| Run | State and allocation |
| --- | --- |
| Water-length 5 mm | Complete: 670,480 cells, 1 s, 20 MPI ranks; native analysis/ledger/render ready |
| Fixed-region viscosity cap, c=1000 | Complete: same coarse mesh, 1 s; exploratory modified turbulence |
| Ambient-air intensity 1% | Complete: same coarse mesh, 1 s; assumed input sensitivity |
| Local uniform inlet | Complete: 1,857,796 cells, 1 s, 20 ranks; exact 0.5 and 1 s native analyses and matched still renders complete |
| Local three-component inlet | Complete: t=1 s/End/exit 0; same mesh/history/numerics, altered U/k/epsilon; terminal diagnostics pending |
| Fine baseline | Paused at logged t=0.113840 s, exact 0.1 s saved; 6,205,440 cells, 1.5 s target |
| Wider refined plume | Queued after pair and fine terminal evidence: 4,962,992 cells, 1.5 s, 20 ranks |
| Source80 / Source40 / small-area composite | Held downstream of wider run's verified cleanup/release sentinel |
| Gravity-driven tank discharge | First attempt failed at 0.249255 s; upwind-only k/epsilon transport retry completed 0.6 s, exit 0; 452,800 cells, 20 ranks |
| Instrumented gravity tank | Solver complete at 0.6 s/End/exit 0; 452,800 cells, 20 ranks; exact baseline resumed; separate retained-input recovery and full native-flux archive complete |
| Gravity-head sensitivity | All three depths completed 0.6 s/End/exit 0, owned cleanup and exact C3 resume; 452,800 cells, 20 ranks; h125/h150 detailed analyses held |

The first tank diagnostic failed at 0.249255 s after about 173 s wall.
Changing only k/epsilon convection from limitedLinear to upwind completed
0.6 s in 378 s (10:29:34–10:35:52 UTC), with solver End and exit 0.
The owned pilot container was removed and the exact uniform container resumed;
the paused fine container and queue stayed intact. Both attempts are preserved
([successful retry and cleanup](../results/runs/dash8-gravity-discharge-upwind-retry-20261005T102609459314088Z/pilot-20261005T102934595442Z/launch.json)).
The queue is now three-component → larger-opening priority sensitivity
(temporary exact fine pause/resume) → fine continuation → wider plume → older
source queue. A native per-face-flux tank trial temporarily paused/resumed the
exact three-component run. That short trial completed
0.6 s with End/exit 0; the coded writer compiled and output covers 1,200 owning
faces. Root verified the pilot CID absent and the exact baseline CID running
unpaused. Its original manifest reports a postrun metadata error because a
whole-case hash traversal rejects legitimate runtime dynamicCode symlinks;
the worker recovered a retained-input-only audit separately, preserving
that original error. Recovery now verifies all 26 original input hashes; root
independently rehashed them and the trace, producer, trace builder, aggregate and
audit CSV. This is not another physical solver failure.
The full 1,374-step, 1,200-face native trace reconciles every step with the
aggregate within 4.9975e-9 m³/s (declared printed-rate tolerance 5.1e-9).
Integrated volume is 2.015733411766675 m³, differing from the printed aggregate
by -1.47e-11 m³. Native water-flux-equivalent normal-speed spatial CV at 0.5 s is 8.8009%, mean
2.73458 m/s and range 2.19155–3.15516 m/s. This is modest computed unevenness,
not measured turbulence or the prior 60% synthetic forcing.
[Frozen trace and sidecar](../results/runs/dash8-native-face-alphaPhi-preparation-20261005T112300Z/postprocess-attempt-01/native-tank-alphaPhi-step-series.json).
Successful transport stabilization does not establish a
physical breakup cause or numerical convergence.
Native geometry totals exactly 1.332 m² at z=0 with all oriented normals -z;
decomposed faceZone flipMap contains both signs and must be applied per face.

Fine's original 24 h watchdog deadline is **2026-10-06 04:17:37 UTC**, including
pauses. Its last throughput sample implied 35.77 h for 1.5 s at a constant
rate: budget exposure, not a settled ETA. Prepared continuation has 18 offline
tests; actual solver restart equivalence remains untested.

Exact operational handles and contracts:

- Completed uniform CID: `796b968903199f2e2bfe13dd35f50b8d087e471bbf93d43e90b08356c3c9d496`;
  [flow log](../results/runs/dash8-local-mesh-uniform-exit1-retry-20261005t0648z/case/log.interIsoFoam).
- Fine CID: `93e8ad234f6b2dc2e4715b45d31221f00f47c8290e5a9b00ebe569bb59f3051a`.
- [Pair scheduler and activation](../results/runs/dash8-local-mesh-pair-exit1-retry-20261005T064542Z/retry-activation.json);
  terminal native/GPU observer waits for successful sealed pair outputs.
- [Wider queue](../results/runs/dash8-wider-plume-queue-20261005T075838Z/service-handoff.json);
  actual flow-log horizon and owned cleanup are required for release.
- [Paper-count observer](../results/runs/dash8-native-paper-count-pair-observer-20261005T071428Z/);
  waits for native pair and render completion, with no CFD retry.
- [Width-profile replacement observer](../results/runs/dash8-native-cloud-pair-observer-loaded-source-20261005T094430Z/replacement-attempt-02.json);
  PID 1171527, waiting for native pair completion. Analyzer records import-time
  and on-disk source hashes separately. Old waiting-service evidence and failed
  replacement attempt are preserved; no CFD or upstream scheduler changed.

## Evidence that determines the next experiments

Native components use face connectivity and thresholds alpha>=0.001 (cloud)
and alpha>=0.9 (core); counts include source-attached regions and single cells.
The paper's MATLAB detector/filter/velocity weighting is unpublished.
Native counts and interpolated-isosurface counts are different observers.

| Completed coarse case, t=1 s | Cloud / core count | Detached cloud mass |
| --- | ---: | ---: |
| Corrected uniform reference | 41 / 123 | 400.05 kg |
| Normal-only uneven source | 45 / 104 | Mixed response; mean discharge retained |
| Water length 5 mm | 49 / 116 | 412.18 kg |
| Fixed-region viscosity cap | 74 / 103 | 391.51 kg |
| Ambient-air intensity 1% | 52 / 120 | 482.59 kg |

The paper's Fig. 11 raster read is about 267 cloud / 14 core regions at 1 s.
No completed sensitivity closes this gap or establishes improved physical
breakup. A larger count alone is insufficient: the cap increases cloud count
while reducing detached water mass. See [uneven](../results/runs/dash8-uneven-terminal-comparison-20261005T005540Z/summary.json),
[water length](../results/runs/dash8-water-length-terminal-comparison-20261005T020801Z/comparison.json),
[cap](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/comparisons/cap-t1/t1p000000/comparison.json)
and [air](../results/runs/dash8-matched-comparison-automation-20261005T022652Z/comparisons/air-i001-t1-fixed-20261005T042700Z/t1p000000/comparison.json).

Terminal local-uniform t=1 native analysis is now available: cloud count
79 (73 with two-cell minimum), core count 321 (155 with two-cell minimum),
detached cloud mass 304.428 kg and total domain water 5197.193 kg. Reference
is 41/123 with 400.05 kg detached cloud water. Increased counts do not alone
establish improved breakup; core counts are strongly single-cell-sensitive.
[Exact local t=1 native analysis](../results/runs/dash8-native-t1-local-vs-baseline-20261005T104846Z/analysis/local_uniform_1p86M/analysis.json).
Canonical turbulence analysis now accepts and verifies the complete original
export inventory (legacy or all three known system dictionaries); 12 tests
pass, and both actual snapshots analyze without editing export metadata.
The matched interpolated-surface observer gives cloud 27→64, core 3→10.
These are separate from native counts, with no fitted component filter.
Local max width falls 5.267→4.860 m and center-registered downward front
8.362→7.206 m. Refinement changes morphology but does not close the paper gap.
[Full comparison](../results/runs/dash8-native-t1-local-vs-baseline-20261005T104846Z/comparison.json)
and [matched full-plume GPU render](../results/runs/dash8-native-t1-local-vs-baseline-20261005T104846Z/render-full-plume-retry01/matched-full-plume-native-polyhedral-pair.png)
were inspected by root; all contour bounds fit the shared frame and source
fields remain unchanged. [New slowed refined-run video](../results/runs/dash8-refined-uniform-full-plume-animation-retry02-20261005T113418Z/refined-uniform-alpha001-vs-alpha05-full-plume-10x.mp4)
shows alpha=0.001 and 0.5 at exact saved times 0–1 s, 0.1 s apart, with the
same camera and Ux scale. Playback is 10x slowed using held snapshots, with
no temporal interpolation or surface smoothing. RTX 5090 rendering and all
440 source alpha/U field hashes are verified; the 330-frame video decodes.
Additive diameter/velocity observers preserve all
previous primary results (1,455 reference and 3,801 local metrics checked).
For detached clouds in the 0.1–1 m bin, using full selected-cell geometric
volume instead of liquid volume changes membership 34→37 reference and
62→72 local. Number-mean simulation-x velocity of the existing component
mass-weighted velocities changes 19.79→20.26 and 15.16→16.00 m/s respectively.
The paper's operators and axis convention remain unresolved; these are
measurement sensitivities, not a physical correction or equivalence claim.
[Observer comparison](../results/runs/dash8-equivalent-diameter-observer-20261005T111630Z/diameter_class_statistics.json).

At 0.5 s, local refinement leaves one attached dilute-cloud component, like
the coarse reference. Dense-core count rises 13→19, but detached dense-core
mass falls 14.166→12.211 kg. Both fixed-camera renders retain a similar sheet.
[Native comparison](../results/runs/dash8-local-uniform-live-t0p5-retry-20261005T084810Z/comparison.json).

The exact **0.1 s native comparison** now covers coarse, local uniform,
6.21M fine and local three-component checkpoints. All four have one source-
attached cloud and core, zero detached components at both thresholds, and
the same result with a two-cell minimum. Stored water is 151.987–152.256 kg;
local 3C core mass is 128.417 vs uniform 132.076 kg. This does not exclude
roughness/holes within a connected cloud or establish agreement with Fig. 5.
Coarse/fine metadata falsely describes seeded cosine forcing although frozen
0/U is uniformFixedValue; actual dictionaries are authoritative. Original
records remain frozen. Future-generator metadata now correctly labels inactive
perturbation settings and absence of coded uniform-boundary logs; 41 focused
tests pass, including pre-change physical-dictionary hash checks for uniform
and perturbed cases. Root reviewed the combined diff and downstream key use.
[Early native comparison](../results/runs/dash8-early-breakup-native-comparison-20261005T113841Z/comparison.json).

At exact **0.4 s**, local uniform and three-component cases still have one
attached component and zero detached components at both thresholds. Cloud
selected mass is 1695.0529 vs 1695.0554 kg; core selected mass is 1411.4745 vs
1386.7262 kg (1.75% lower). Native dilute-cloud bounds are identical: transverse
width 1.0125 m and downward front 1.39706 m. Root inspected the matched GPU
display: uneven forcing roughens the sheet, without demonstrated detached
breakup. This is an intermediate result, not the pending 1 s comparison.
[Native 0.4 s analysis](../results/runs/dash8-local-pair-t0p4-comparison-20261005T130240Z/analysis/three_component-attempt-01/analysis.json).

**Expansion remains too narrow**, conditional on provisional Lc=sqrt(1.332 m²).
At 0.5 s, refined L/Lc is 0.882, 1.248 and 0.929 at depths z/Lc=0.75, 1.25
and 1.5, versus digitized paper widths 1.742, 2.187 and 2.261: 43–59% narrower.
Coarse widths there are 0.816, 0.984 and 0.810. At 1 s, the completed coarse
run is about 39–41% narrower at z/Lc=1.5–3 and 12–20% narrower at 4–6.
Refined 0.5 s maximum penetration is about 1.99 m versus 2.44 m digitized.
Full-cell envelope slopes are grid-sensitive; dL/dz is not dL/dt.
[Expansion evidence](../results/runs/dash8-expansion-rate-audit-20261005T091303Z/comparison-attempt-02/comparison.json).

**Rendering thresholds explain part of the apparent transport difference.**
The sealed uniform t=1 snapshot reaches x=22.406 m at alpha>=0.001, but the
leading native cell contains only 0.0343 kg and is one 0.594 m coarse cell from
the outlet. At alpha>=0.5 the front is x=3.226 m and selected water is 81.4%
of domain water; at alpha>=0.9 the front is x=2.607 m. Most water remains near
the source. Fig. 10 uses alpha=0.001 but has no calibrated position scale, so
it cannot establish a numeric travel-distance error. Snapshot U is not a trajectory.
[Transport audit](../results/runs/dash8-advection-distance-audit-20261005T092100Z/native-t1-attempt-08/advection_distance_audit.json)
and [GPU threshold views](../results/runs/dash8-alpha-threshold-view-20261005T095433Z/render-output-attempt-04/alpha-thresholds-whole_plume-t1.png).
Contours use explicitly labelled cell-to-point interpolation for display;
numeric extents use native cell values and vertex bounds.

The native k/epsilon/nut diagnostic reproduces water-weighted reference means
1.41519 m²/s², 28.1337 m²/s³ and 0.00872631 m²/s. Saved fields are finite and
nonnegative, but these are shared-fluid snapshot statistics, not a closed
phase-specific turbulence budget or proof of a breakup cause.
[Diagnostic evidence](../results/runs/dash8-native-turbulence-audit-20261005T085142Z/evidence.json).
Water-length changes do not persistently lower water-weighted viscosity.
Stock multiphaseStabilizedTurbulence is incompatible with the current variable-
density path; the tested fixed-region cap does not follow the interface.
No further turbulence variant is selected without useful evidence.

## Source and mesh limits

Dash-8 uses one downward belly opening; Restás uses four horizontal outlets.
The paper uses standard k-epsilon, 50 m/s relative air and omitted capillarity.
Current source is assumed 4.44×0.30 m, not recovered aperture geometry.
Fig. 4 is digitized and provisionally interpreted as mean speed Q/S; caption
and results call it maximum speed. The applied 0–5 s history would release
15.921 m³ at this assumed area; neither nominal 10 m³ capacity nor later
8.840 m³ retardant volume identifies the nearfield water payload. q is area-
independent; area changes total flow and momentum. Do not fit area to appearance.

Paper aircraft belly, tank-generated spatial profile, inlet turbulence,
initial external fields and source-clock registration are incompletely
specified. Current exterior is a flat slip roof. Fig. 5's 0.1 s cloud fringe
is visibly rougher than ours, though much water is still attached.
[Early comparison](../results/runs/dash8-early-breakup-investigation-20261005T091031Z/early_breakup_review.json).

Completed normal-only uneven forcing uses 24 continuous space-time cosine
modes, maximum 60% deviation, periods 0.0582–2.529 s; it preserves area mean
and adds no whole-opening pulses. Queued three-component forcing uses different
assumed wavelengths 0.265–0.373 m and a nominal half resolved/half modeled
energy split. It is not measured turbulence, LES, or a same-spectrum direction test.

The local and wider polyhedral meshes have preserved checkMesh failures on
planar transitions. Independent vertex supporting-plane checks found zero
nonconvex cells; exploratory exact-failure allowances do not pass a formal
mesh-quality gate. Wider refinement covers fast downstream fragments through
x=23 m; local refinement ends at x=8 m. Static refinement is not dynamic AMR.
[Local mesh](../results/runs/dash8-local-refinement-efficiency-20261005T045530Z/preparation.json)
and [wider mesh](../results/runs/dash8-wider-plume-mesh-preparation-20261005T061516Z/mesh_comparison.json).

## Active ownership and checks

Root integrates and makes scientific decisions. Exact saved 0.4 s comparison/GPU
views (root inspected) and finer inlet replay geometry/mapping analysis are
complete. The larger-opening waiting service now uses the reviewed immutable
wrapper, Type=exec, MainPID 1285124 and invocation
3a9c31ced8d84f5f9dd331b23f9c91db. It waits for the active pair and verified fine
resume; candidate physics is unchanged. Its 17 focused tests passed. Root
activated the numerical batch waiting service after 15 tests and an actual
verify-only run with zero launches. It is active with MainPID 1287563 and
invocation 52ba19697b9d4e1989ffb388f6775260, waiting for exact predecessors;
zero solver stages and no fine pause attempt are recorded.
Root review repaired own-process contention false positives, legitimate cleared
terminal systemd InvocationID handling and cleanup/resume recovery defects.
These are launcher defects, not physical solver failures. A second worker has
prepared three gravity-head cases (1.0/1.25/1.5 m in a common assumed 2.0 m tank),
all strict mesh checks passed at 452,800 cells. Root reviewed the corrected v4
launch helper, the v6 cleanup extraction and focused checks; all three serial
0.6 s/20-rank trials are authorized. The first started at 14:13:28 UTC, CID
b2b7f2523e4fcc582812a581454acec9cd7b80444cc9e437543d74fe08cca3d4,
and completed at 14:20:50 UTC with End/exit 0, 26/26 original inputs unchanged,
owned container removed and exact C3 resumed. The 1.25 m trial then started at
14:21:13 UTC, CID d9c634294ca83983559b2f07218f059d0900410cea658b07775d4fddb1db0d4f.
Each borrows CPU from only the exact live three-component container and
resumes that same container after owned-pilot inactivity is proven; fine is
untouched. Another Luna worker prepares native-flux/mean-versus-maximum comparisons, with disjoint output
ownership and no CFD launch authority.
The completed 1.0 m control native trace reconciles 1,612 steps/1,200 faces
with aggregate flux (maximum rate difference 4.9933e-9 m³/s). At 0.5 s its Q/S
is 2.750739 m/s versus old-tank 2.734581 and Fig.4 scalar 4.677; sampled U
maximum is 3.068 m/s. The tank extension/grid change does not materially close
the speed gap. Spatial flux-equivalent CV increases from 8.80% to 10.13%.
[Executed head comparison](../results/runs/dash8-gravity-head-comparison-20261005T140908Z/h100-comparison-v3/comparison.json).
Its frozen 670,480-cell candidate preserves the corrected reference
physics and extends only U/k/epsilon histories and horizon/output times. Root
reviewed that physical diff; waiting-service activation is authorized. Its 5 s
expected release is 15,921.396 kg under the provisional mean-speed reading.
The x=23 m and z=-31 m open boundaries remove older structures, so this is a
long-horizon nearfield-throughflow diagnostic, not a complete retained-drop or
late whole-cloud count reproduction. The curve remains nonzero at 5 s; no
unreported shutoff/tail is added.
[Frozen batch candidates](../results/runs/dash8-numerical-long-horizon-preparation-20261005T125937Z/preparation.json).
Existing queued controllers remain unchanged. Pinned stock
interFoam uses registered water flux alphaPhi0.water; with Euler and one alpha
subcycle this is the main-step phase-volume flux. The existing iso-only ledger
must not silently be reused. Early comparison and metadata correction are
handed off. Root found and the worker repaired a replay boundary dictionary-scope
bug before launch; replay checks now pass 16 tests, including patch preservation
and producer-checksum/reconciliation checks. The frozen coarse replay pair is
prepared and parsed. In a disposable actual-case copy, pinned v2512 postProcess
read and compiled U/k/epsilon coded boundaries, exit 0/End, three verified shared
libraries. No transient replay has run. Two preceding harness-only failures
(copied image-digest typo; bashrc under set-u/auto-removed container cleanup)
are preserved. Exact baseline quota was restored to 20 and it stayed unpaused.
Mapping from 1,200 native faces to 224 coarse inlet faces reduces the 0.5 s
flux-equivalent velocity CV from 8.8009% to 2.8322%; total Q is conserved but
~89% of the integrated extra normal impulse from spatial variance is lost.
This limits the coarse pair's test of natural source unevenness.
The verified local mesh supplies 960 native rectangular faces on a 120×8
grid. Its prepared 0.6 s replay pair conserves total Q to 2.1e-14 m³/s and
retains 61.75% of native time-integrated spatial variance (coarse: 11.07%).
At 0.5 s, mapped CV is 6.91% versus 8.80% native. Extra normal impulse is
23.236 N·s, only 0.431% above the uniform replay; no fitted amplification is
applied. Root reviewed the geometry adapter and matched physical inputs;
18 affected tests pass. Both resolutions remain unlaunched.
[Finer replay evidence](../results/runs/dash8-flux-replay-fine-mapping-20261005T125547Z/fine-pair-verification.json).
Root reran replay, source metadata and native face-writer checks: 63 tests pass.
Neither new comparator has launched CFD or changed the live queue. The pair will
use the same recorded total water history, liquid-only alpha=1 and zero
tangential inlet speed; it is not a coupled two-fluid/momentum handoff or a
Figure-4 reproduction. No replay CFD is launched or queued yet. Old proxy NPZs
are excluded; only the new actual per-step native trace is an allowed input.
GPU still rendering is complete. No routine Astra/Warden pass is pending.

The unlaunched MULES comparator's corrected case-02 matches the reference's
physical dictionaries and source history through 0.6 s; its first candidate
is preserved as superseded because it omitted the four freestream-backflow
entries. Shared future CL-415/Dash-8 generators now emit those entries using
the configured air speed and record them in metadata. Old cases are untouched.
Shared runner dispatch cross-checks the frozen solver against controlDict and
launches/parses the selected interIsoFoam or interFoam binary. A separate MULES
ledger verifies pinned source, Euler/one subcycle/one outer corrector, all
boundary phase fluxes and zero initial water. It reports prescribed flow and
transported flow separately; configuration-only preflight passes, with no
physical closure result yet.
[MULES candidate/source evidence](../results/runs/dash8-mules-preparation-20261005T122955Z/preparation.json).

The gravity pilot assumes a rounded internal tank bottom, 1 m head from the
aperture plane, atmospheric openings and water initially at rest. It imposes
no Fig. 4 velocity. Repaired 452,800-cell mesh has strict checkMesh Mesh OK,
1,200 internal aperture faces, 1.332 m² area and 6.32045682 m³ initialized water.
Native internal-transfer and ambient/vent escape fluxes were logged separately.
The first attempt preserved profiles through 0.225 s. The numerical-scheme
retry now supplies the full 0.6 s profile history. Pressure PCG/GAMG reported the final floating-point exception;
k/epsilon solves had already hit 1,000 iterations and large nonphysical growth,
followed by a Courant jump above 4. This is evidence of numerical instability
in the new tank pilot, not a cause established for the stable old nearfield
sheet. Analysis distinguishes geometric Q/S, wet-area mean and maximum
velocity; VTP polygon winding is not used as the physical outlet normal.
No aircraft wake or 50 m/s external airflow is included in this source pilot.
The first attempt's native Q/S at 0.1 s was 2.269 m/s versus digitized 2.29 m/s;
at 0.225 s it was 2.873 versus about 3.857 m/s. The early agreement does not
establish discharge-history agreement. Mapping its 0.1 s saved alpha/U profile
preserves the 2.802 m³/s geometric flux proxy, but native alphaPhi is 3.023 m³/s:
a 7.31% mismatch that must remain explicit before boundary replay. Coarsening
also changes reconstructed momentum and kinetic-energy flux.
Completed upwind retry confirms native Q/S=2.735 m/s at 0.5 s and 2.644 at
0.6 s, versus digitized 4.677 and 4.567 m/s. Interpolated face maxima are
3.089 and 2.984 m/s. The provisional tank does not reproduce the later source
history under either mean or maximum interpretation. Its 0.6 s internal
transfer is 2015.738 kg, signed ambient/vent escape 989.496 kg and stored water
5330.96049 kg; internal transfer is excluded from global stored inventory.
[Successful tank analysis](../results/runs/dash8-gravity-discharge-upwind-analysis-20261005T104528Z/analysis-attempt-01/).
A doubled-opening 0.5 s diagnostic has a frozen corrected-airflow candidate:
4.44×0.60 m, 2.664 m², expected 670,480 cells/448 source faces, unchanged
Figure 4 mean-speed history and matched PBiCGStab/DILU scalar solvers.
Expected release 4639.223 kg at 0.5 s; mass/total momentum double and q stays
area-independent. Older uncorrected-air candidate is preserved and not used.
A replacement priority wrapper has completed root review and 17 focused tests.
Its Type=exec service is activated and waiting for both 1 s pair members and their
scheduler cleanup. It temporarily pauses/resumes the exact fine reference;
the candidate CFD has not launched and supplies no completed result.
[Waiting-controller state](../results/runs/dash8-width-controller-replacement-20261005T133025Z/controller/activation-state.json).
This changes payload and momentum.

Latest full `make check`: **587 tests and four subtests passed**, one optional
Docker smoke skipped; Ruff lint and formatting passed, 105 files checked
(13:02 UTC). Case-generator focused lint/format checks also pass. Runtime
native-writer reconciliation and replay-library compilation are recorded above;
transient replay and MULES solver results remain absent. Failures and retries
remain preserved; exploratory evidence is not a gate pass.

User-requested publication is pushed as `61b5e6e`, with selected previews
and raw runs ignored. New discharge/profile work remains local.

The [20-hour actual-run inventory](../results/runs/dash8-cfd-run-inventory-20261005T103100Z/solver_runs.json) records nine fresh completed coarse cases separately from
restart, mesh-only and analysis attempts. It preserves the 913 s overlap of
two 20-rank jobs on 20 effective cores and an aborted-run summary/log mismatch.
Neither resource caps nor overlapping elapsed time establish measured CPU-hours.
