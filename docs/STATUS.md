# Live project status

Updated: 2026-10-16 13:09 UTC. CPU-only work; use available capacity within a
shared 20-CPU budget and respect unrelated workloads. Analytical E0 is the
only passed gate. No E1, aircraft, ground or field reproduction is validated.

## Current work

- The clean-start water B diagnostic is running under the durable user service
  `fire-track2-air-only-resume-20261016.service` (MainPID 4054741, dispatcher
  4054742), independent of the tool session. Container
  `air-only-water-b_resume-20261015-flow` has 20 MPI ranks and is at t=0.13275 s.
  Root verified its actual Docker quota restored to 20 CPUs after rendering
  and checks. Its latest water-ledger relative residual is 2.44e-12; all 530
  k solves so far iterated. These checks do not establish physical accuracy.
- Air-only A stopped at t=0.421 s on its predeclared wall-budget stop; solver
  exit was zero and all 20 ranks received the write/stop request. It did not
  reach 0.5 s. All water inventory/flux remained zero. Its nozzle injected air
  downward at 10 m/s: phase replacement, not a sealed-nozzle baseline.
- The air-only flow is not qualified as healthy: recorded peaks include
  k=2,734.93 m2/s2, epsilon=906,154 m2/s3 and nut=494.97 m2/s, at different
  cells/times. Logs show negative epsilon before bounding, frequent zero k
  iterations and U component solves reaching maxIter=100. Thus a substantial
  numerical/turbulence anomaly occurs without a water interface; its cause
  is not yet established. A lacks the kFinal minIter=1 already used in B/C,
  so the air/water comparison also changes this solver setting. A matched
  air-only minIter pair is the next recommended isolated diagnostic before
  attributing differences to water or combining changes with refinement.
- Supervisor state is
  `results/runs/recovery-air-only-20261015T201744Z/resource-resume-live-state.json`.
  It runs A first, then prepares and launches B from clean t=0. C/D are
  excluded because C failed its velocity diagnostic. Each case retains its
  finite 0.5 s/3-hour declaration and the shared PAUSE behavior. Actual solver
  startup registers stopAtWriteNowSignal=12 from nested OptimisationSwitches.
- CPU Mitsuba rendering trial completed in
  `results/summaries/rouaix_mitsuba_20261016/`: a 64-spp matte-blue near-field
  still at 1.5000193048 s, dielectric alternative, and six-state 0.025–0.15 s
  startup movie at 10× slow motion. Root inspected the still; sampling grain
  remains. Optical D32=0.5 mm, Qext=2, albedo=0.999 and HG g=0.85 are assumed;
  only 0<alpha<0.1 supplies the inferred spray proxy. These are presentation
  trials from exploratory fields, not measured foam or a validated reproduction.
  A portable cropped grid and replay command accompany the still. No CFD
  physics or acceptance criteria changed. Two Luna workers implemented and
  checked this; `make check` passed (656 tests, one optional Docker skip).
  A pre-existing SIGTERM test race was corrected by waiting for both mock
  startup markers; the original failed check log remains preserved.
- The morning check found no active CFD: the main finite queue had finished
  at 22:10 UTC on 15 Oct, while the prior resource dispatcher disappeared
  after its 21:21 update and never launched follow-ups. Its failed attempt
  and stale state are preserved; a written queue or old PID is not proof
  of running work. This restart replaces tool-session-dependent supervision.
- The clean-start limited-grad(U) water case reached 0.17425 s and stopped
  when max |U| exceeded 1,000 m/s (logged 1,025.04 m/s at t=0.174 s).
  The peak was at (10.25,-0.017254,-3.48584) m, near the roof/spanwise edge
  in the downstream coarse region. All 696 k solves had positive iteration
  counts and the native water ledger passed; neither establishes a credible
  velocity field. The 3.2 s continuation correctly did not launch.
- C's uncontrolled signal exit was 140; a reconstructed 0.15 s checkpoint
  exists, but is preserved for diagnostics rather than blindly continued.
  A and B had stopped solely on the old 24 GiB reserve. A has a valid
  0.05 s checkpoint; B requires clean t=0. Future supervisors use nested
  OptimisationSwitches, verify actual startup signal registration, and use
  measured-headroom memory stops. Failed attempts remain intact.
- Two Luna workers completed read-only comparisons of the actual dictionaries
  with Rouaix and Shi/Yumeng. No competing compute was launched. Ordinary
  launch and recovery work does not require another Astra review.
- User prioritizes fine resolution for correct breakup behavior. Luna completed
  the initial estimate in `results/runs/fine-mesh-preparation-20261016T111012Z/`:
  a provisional locally refined 16 mm arm is about 8.6-9.3M cells and 24-26 GiB
  RAM; no mesh was generated or run. Rouaix's 16 mm is local refinement, not
  uniform domain spacing. A copied pilot needs a larger snappy cell cap than
  the existing 3M cap. Refinement is not assumed to cure the air-only pathology.
  The tested limited-gradient case limits only grad(U); grad(k/epsilon) remain
  unrestricted, as do all three gradients in baseline A/B. No fully limited
  production treatment has been qualified. Rouaix reports liquid I=1%, but neither gas
  intensity nor inlet length scale. Current air I=1% and L=0.028 m are assumed.
- The completed one-step kFinal tolerance batch remains sensitivity evidence:
  1e-10 is identical to the 1e-8/minIter1 control; 1e-12 and 1e-14 use 6 and
  12 iterations, with relative k L2 changes 0.004100 and 0.004227. All exact
  one-step native audits pass operational guards, not a scientific gate.
- Current doctor: 20 effective CPUs, about 70.6 GiB available RAM and 797.5 GiB
  free disk. GPU compute/rendering remains disabled. Count actual running
  processes and utilization, never paused PIDs' historical CPU averages.

## Numerical findings

The baseline stalled at 3.0942804546046 s with deltaT about 1.86e-17 s and
six hours without printed time advancement before manual pause. Its extreme
velocity/pressure growth invalidates the earlier completion estimate. Mass
closure and bounded alpha alone do not establish a credible flow solution.

| Diagnostic | Result | Interpretation |
| --- | --- | --- |
| maxCo 2 -> 1 | Manually checkpointed/stopped at 3.0851454757947256 s; mass guards passed | Did not reach the failure point; no fix established |
| k/epsilon convection -> upwind, maxCo=2 | Timed out at about 3.093817 s after 90 min; deltaT about 1.21e-6 s | Still shrinking timestep; no demonstrated remedy |
| Direct extrema in scalar trial | max velocity about 46,053 m/s, pressure extrema about +134/-262 MPa near x=10 m | Numerically compromised, despite finite fields and mass closure |
| Momentum convection -> upwind only | Guarded stop at 3.0753866640745677 s after velocity exceeded 10,000 m/s; checkpoint and native mass audit saved | Does not repair the already compromised restart seed |
| Active kFinal minIter 0 -> 1, matched one-step pair | 0 -> 2 iterations; relative L2 change in k 4.467%; k-floor cells 22 -> 0 | Actual solver settings materially affect k; convergence and a physical remedy remain unproven |

The scalar trial's k solver took zero iterations in all 1,622 recorded solves;
the sampled baseline at 2.75 s also had zero k iterations. Changing its
convection scheme therefore did not demonstrate evolving k transport. The
review identified linear-solver normalization/stiffness as a diagnostic target.
The sole PIMPLE iteration actually selects kFinal: the first k-only minIter
change was inactive and is preserved as a failed attempt. The corrected pair
in `recovery-rouaix-c4-kfinal-miniter-pair-20261015T2016Z` used the exact same
parent and terminal time 3.07365229458967493 s. Active minIter=1 changed all
2,733,120 k cells, with relative L2 difference 0.04467394; both native mass
audits passed the operational guards. This is sensitivity evidence, not a
convergence result; no model constants or viscosity caps are fitted.

The paper uses limited gradient reconstruction (PDF p. 8 / article p. 7,
section 3.3); our velocity linearUpwind reconstruction uses unrestricted
Gauss-linear gradients. The extreme velocities occur in the coarsened region,
where streamwise cells are 0.5 m long, rather than the nominal 70 mm corridor.
The current mesh is nonuniform: nozzle-plane spacing is about 34.48 mm in x
and 43.75 mm in z (roughly 12 by 9 cells across the nominal diameter), not
six cells across in each direction. Its measured nozzle area is
0.1237068965517 m2, 1.56% below the ideal 0.4 m circular opening. These
local sizes and actual source flux must accompany the nominal corridor size.
This motivates the single-change momentum diagnostic; causation is unproven.
Native sampling at the recovered 3.09328474300641 s checkpoint identifies
the logged peak cell (processor 9/local 85,297) as air: alpha=7.04e-28,
U=(64.5,-9149.96,20771.87) m/s, p_rgh=-1.113 MPa. Its center is
(11.75,-0.18967,-3.56294) m. Exact polygon distances place it 0.02043 m from
spanwiseMinus and about 0.19984 m from aircraftWall. The earlier centroid
distance did not identify the nearest boundary. The later 46 km/s peak has no matching saved field time;
sampling its location earlier does not establish its later local alpha.
This local velocity peak has nut about 3.36e-5 m2/s, so it must not be
conflated with the global maximum nut of about 19 m2/s elsewhere. Source-code
inspection found isoAdvector-derived rhoPhi feeding the momentum equation,
with no obvious phi-versus-rhoPhi substitution defect.

## Checkpoints and monitoring

- 3.0735945651412 s: durable 175,954,077-byte archive; exact 1,838-row native
  audit passed both 0.1% operational guards. Finite/bounded, but nearby fields
  already show about 1,229 m/s velocity; this is a recovery-comparison seed,
  not a physically verified initial state.
- 3.0851454757947256 s: maxCo=1 checkpoint archived (176,492,636 bytes), with
  1,070-row native audit passing both guards.
- 3.09328474300641 s: recovered manually from the scalar-upwind RAM case.
  Exact 1,304-row audit passed; incremental residual -6.007469e-6 kg,
  cumulative -0.012080196 kg. Its numerical velocity failure remains.

The scalar trial's automatic audit/capture watchers exited before Docker
created the container: they mistook a missing startup container for completed
work. Thus prior claims that these watchers remained active were incorrect.
The saved candidate was recovered to disk in
`results/runs/recovery-rouaix-c4-upwind-pilot-20261015T1948Z/`.
Startup ordering was corrected in the momentum trial; its direct velocity
guard requested a successful write/stop and checkpoint capture. The fresh
air run embeds its guards in the active dispatcher rather than assuming an
unverified watcher remains alive.
Native ledgers include all seven boundaries, exact closed time prefixes and
parent offsets applied once. Operational guards are not E1 acceptance tests.
Failed logs, snapshots and attempts remain preserved.

## Paper comparison and publication

The ten supplied PDFs were reviewed across two Luna reading tasks and primary
source inspection for the user's comparative report. Visually checked the
original Calbrix p.7 equation Lc=sqrt(S) and Shi p.5 Eq.16 transfer criteria
deq<=dthr and xi<=xi_c; extracted text loses these symbols. Calbrix does not
disclose its interface scheme, and Shi does not identify its solver package:
neither HRIC nor Fluent may be inferred from generic terminology. HRIC is
absent from the pinned local source tree; the isoAdvector authors' repository
contains uncompiled legacy HRIC/mHRIC/CICSAM implementations (reviewed tree
b2671915c5f777fc92e9910496f5ca3a1af90f23). Porting is feasible in principle,
but no HRIC implementation was installed or tested and no method was adopted.

Previously published code and compact evidence: `656850f` and `40ac757` on
main. This publication adds CPU recovery findings and selected attempt videos.
`results/summaries/rouaix_20261015/` contains the comparison figure, SI profiles,
nominal-D=0.4 m normalized profiles, hashes and explicitly scoped pilot evidence.
Raw CFD fields, large logs, archives and environments remain ignored.

- [Longer water attempt, 10x playback](../results/summaries/rouaix_20261016_videos/rouaix-long-attempt-10x.mp4):
  saved 2D center-layer and maximum-over-span projections, t=0.4-1.5 s;
  alpha=0.1/0.9 contours. Re-rendered with roof at top and gravity down.
- [Clean-start water diagnostic, 10x playback](../results/summaries/rouaix_20261016_videos/rouaix-startup-diagnostic-10x.mp4):
  seven saved fields from t=0 to 0.15 s, interpolated alpha=0.5 3D display
  surface with two display-only smoothing iterations and +y screen-up.
  This run later stopped at 0.17425 s on velocity runaway; no later motion
  is depicted. Both clips hold saved snapshots without temporal interpolation
  and are exploratory attempts, not validated reproductions. Root inspected
  both final poster images; raw fields and intermediate renders stay ignored.

At 3.0736 s, queried full alpha>=0.1 cloud depth reaches 9.5 m and width
4.86375 m; source-connected alpha>=0.9 core reaches 4.0556 m depth and
0.5523 m width. One selected cloud cell touches the domain bottom. The large
paper mismatch is not a validated physical conclusion: numerical corruption,
detached-cell selection, 70 mm versus 16 mm mesh, unspecified paper sampling
and full/half-width conventions all require resolution. The native whole-field
water-volume integral agrees with the saved inventory within 6.1e-14 m3.

Last full make check: 649 passed, one optional skip and four subtests; Ruff
passed. Three subsequently added source-container inspection regressions also
passed. No shared numerical acceptance criterion was changed.

## Cluster handoff

The user expects about 1,300 cores on 16 October; scheduler probably Slurm,
OpenFOAM not expected preinstalled. Actual access, node layout, MPI and allowed
container/build route remain unverified. No cluster job has been submitted.
Follow `docs/COMPUTE.md`: establish the pinned v2512 environment, run bounded
stability and measured MPI scaling, then choose ranks and independent refined
cases. More available cores do not establish that this unstable case is ready
for a production reproduction. Earlier 2.75 s fields are not automatically a
clean production seed; corrected production cases require verified evolution
from clean initialization.

Plan: `track2_aerial_drop_experiment_plan.md`. Gates: `docs/VALIDATION.md`.
Sources: `docs/REFERENCES.md`. Detailed earlier status is retained in Git history
at `40ac757`; original run evidence has not been removed.
