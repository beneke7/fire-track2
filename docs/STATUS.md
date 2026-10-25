# Live project status

Updated: 2026-10-25 18:08 UTC. Workstation priority: **I4F internal discharge**.
Aerial work continues separately on the server. User requested publication of
the reviewed code, summaries and video; HPC execution belongs to another agent.

## Current execution

- **Physical baseline revised: downstream passages initially contain air.**
  User confirmed this directly. The compact cold start completed .050021 s
  normally with all restart fields. Its same-physics ten-rank continuation is
  Docker `42b79f4695fa`, StartedAt 16:09:55 UTC, in
  `results/runs/i4f-short1-dryline-continue-20261025T160951Z/`, targeting 1.3 s.
  Root verified progress through .38884 s without pressure contacts or guard
  errors. Full states every .05 s; .8 s is an intermediate observation.
  An active exact-ID wall-budget controller allows only healthy wall-save
  continuations, with four-hour stages and a twelve-hour campaign bound.
  Tank load is 2.700 m3 plus .502166 m3 of wetted upstream feed; the assumed
  effective valve plane is x=2.25 m. All downstream gas starts at 100 kPa and
  293.15 K. The old fully
  wetted network is a conditional limit, not a line-filling model. Owner:
  Luna coupling worker. The half-timestep run ended normally at .04995696 s;
  dense scalar comparisons use common-time interpolation without extrapolation,
  while field pairs disclose their 64 microsecond offset. Maximum compared
  probe-pressure difference is 178 Pa; no water outflow is resolved through .05 s.
- **Wet-side valve-source diagnostic continues on the other ten ranks.**
  Pilot Docker `b34ec61f05d6` completed .050021 s normally with all 14 fields,
  no pressure contacts and phase-ledger errors below 3e-7 of initial inventory.
  Its ten-rank continuation `5a6bb983ac5a`, StartedAt 16:58:04 UTC, reached
  .19477 s without pressure contacts or diagnostic errors and targets .3 s
  with two-hour hard / 1 h 40 save bounds. It uses the same native initial
  state and partition. Only the source support moves into an initially wetted
  upstream band, preserving fully wet integrated resistance. The original
  .3 m source zone starts half-water/half-air; its wet coverage rises to .656
  by .05 s. This is a source-placement sensitivity, not a fitted valve curve.
  The exact-time .05 comparison reduces tank drawdown by 12.1% (6.547 to
  5.756 L), explaining part of the gap to the reduced model. Owner: coupling
  worker; `results/runs/i4f-short1-valve-wetside-continue-20261025T165800Z/`.
- **Valve pressure–flow error isolated in an analytical limit.** Four all-water,
  slip-wall duct cases ended normally. With the same integrated scalar loss,
  native flow exceeds the analytical result by 6.34% for a .30 m support on
  25 mm axial cells, versus 1.38% at 6.25 mm. A .10 m support gives 27.66%
  and 5.02%, respectively. Flux conservation still closes: source resolution,
  rather than missing water, is implicated. These errors are not apparatus
  correction factors. The one-CPU component follow-up checks other openings.
  One bounded Astra Warden pass selected a .30 m initially wetted support at
  x=1.95–2.25 m, retaining Cd/opening and normalizing discrete source weights.
  Two axial-refinement meshes (279,536 and 299,248 cells) pass all nine
  configured checks. All 14 zones and initial fields were repaired/verified
  through the refinement map. The actual user-systemd queue is active as
  `i4f-short1-valve-band-axial-dispatcher.service`, restarted at 17:59:40 UTC
  with a six-hour bound. It waits for the exact thin-source parent to finish
  and capture before sequential ten-rank .05 s cold starts. No child is
  launched yet. A post-pair comparison/conditional fine continuation is being
  prepared separately; do not count it as armed yet. Prospective 2% source-flow accuracy
  and apparatus mesh sensitivity are separate numerical targets, not hardware
  validation. Evidence: `results/runs/i4f-valve-resistance-duct-20261025T1721Z-attempt4/analysis/`
  and `results/runs/i4f-refineMesh-axial-feasibility-20261025T1731Z/`.
- **Source-placement effect reverses by .20 s.** Exact common native states
  show thin-source tank-A drawdown .79 L lower at .05 s, but 3.08 L higher
  at .20 s, with gas pressure 11.85 kPa lower and the liquid front about
  .15 m farther downstream. Original support is fully wetted by .15 s.
  Both fronts remain upstream of the transition. Native inventory/field
  mapping checks passed; the reduced model remains a consistency reference.
  Published: `air-filled-source-history-comparison.{json,csv,png}`.
- **Moving-front reduced model implemented and independently reviewed.**
  A portable frozen input packet supports execution without private history.
  Nineteen affected tests pass (eleven new, eight existing), plus Ruff checks.
  The one-tank/two-branch approximation predicts mouth-water arrival brackets
  near .612/.620 s and intake-crown exposure near 1.127 s. It assumes a
  full-bore front and ambient air pressure; incomplete air/transition screens,
  geometry mismatch and strong adiabatic cooling prevent a validation claim.
  Energy worker now verifies resistance in a small all-water plug-flow limit.
  A current air-filled cutaway movie through .200021 s is ready and inspected;
  no resolved exterior water appears in those sparse saved states. It is pipe
  filling, not a completed sheet-discharge movie.
- **User-directed compact geometry:** fresh CAD now defaults to zero straight
  after the upward bend and a 1.0 m transition/outlet train; 0.8 m is the
  alternative. The photo supplies proportions, not measured lengths. Geometry
  generation, roof/floor contacts and common-scale comparison passed. Compact
  mesh has 269,680 cells and passes all nine configured quality rows; optional
  geometry checks still report concave cells. Native initialization gives
  1.350 m3 water per tank and no unclassified/overlapping cells. The compact
  primed-line pilot finished normally at .050021 s: Docker `9d73e14fb678`,
  StartedAt 15:37:08 UTC, exited 0 at 15:49:28 UTC with all 14 restart fields
  and no raw pressure contacts. It remains a conditional initial-state
  sensitivity; no long primed continuation will launch. Owner: Luna coupling
  worker. Existing fields and
  movies retain the frozen 0.2 m straight plus 1.8 m legacy train.
- **Long-geometry primed continuation saved and stopped.** Docker
  `715ddc276b6e`, StartedAt 2026-10-25 13:23:49 UTC, exact identity independently
  verified. The 303,108-cell pilot completed .050021166664 s in 506 seconds
  with normal End, all 14 native restart fields, zero pressure-floor contacts
  and phase-ledger errors below 2e-7 of initial inventories. Continuation
  targets .8 s, with a three-hour hard bound and save ten minutes earlier;
  full fields every .05 s support rendering. This is explicitly quality-limited:
  two configured face-tet checks fail; the other eight rows pass. It is not a
  passed mesh gate or hardware validation. Owner: Luna coupling worker; bundle
  `results/runs/i4f-quality-limited-fourmouth-continue-20261025T131742Z/`.
  It stopped gracefully after the initial-fill correction at .516777453181 s,
  exit 0 at 15:48:24 UTC with all 14 fields plus uniform/time, zero pressure
  contacts and no diagnostic errors. The wall-limit dispatcher was stopped
  first and launched no child. This was a superseded-input stop, not numerical
  failure or a user pause of the project. Owner: Luna energy worker.
- **Fine 1,779,258-cell reservoir check completed normally on ten MPI ranks.** Docker
  `1b4d0094bba8`, StartedAt 2026-10-25 13:48:54 UTC, exact identity verified.
  It starts from the approved fine initial state with the tested ambient BCs,
  targeting .05 s under a four-hour bound. Source binary and nominal physics
  match the coarse run; native gas capacities differ by about 1% through mesh
  volume discretization. Normal End at .050021166664 s after 6,471 wall seconds
  and 212 steps, with all 14 native restart fields, zero raw pressure-floor
  contacts and no guardian diagnostics. Root verified terminal Docker state,
  actual End and checkpoint metadata. Matched startup analysis finds 403 Pa
  probe-pressure difference and -2.44% tank drawdown on the fine mesh. Native
  mixed-cell gas fraction is 19.94% coarse versus 12.69% fine, despite close
  pure-gas/probe temperatures; no independent gas-energy closure follows.
  Owner: Luna energy worker;
  `results/runs/i4f-fine-reservoir-coldstart-20261025T134345Z/`.
- **Halved-timestep startup comparison completed normally.** Both ten-rank
  cases reached .05 s without pressure-floor contacts. At matched time, probe
  pressure differs by 103 Pa, sampled flow about .2%, and maximum speed about
  4.1%; wall cost increased 2.07x. This is startup sensitivity, not full-release
  convergence. `results/runs/i4f-fouroutlet-dt-half-20261025T131044Z/analysis/matched-time-sensitivity-v1/`.
- **Older adaptive reference saved and stopped at .636303119113 s.** Docker
  `0d0195e6e362` exited normally after 410 steps/956 s. First raw floor contact
  was 9993.8 Pa at .636086754533 s; its exact pre-floor cell was not logged.
  The saved clipped cell and its neighborhood are liquid; ambient incoming
  Mach stayed below .021. This differs from the former ambient runaway.
  Actual throughput was .179 physical seconds per wall hour; no 22x measured
  speedup is claimed. Audit:
  `results/runs/i4f-ambient-reservoir-adaptive-20261025T124200Z/pair-r3/adaptive-reservoir/endpoint-audit/`.
- **Outlet observer audit:** native flux matches inventory loss. Sampled-plane
  flow is 29.8% lower at 5 ms and 11.37% lower at 50 ms; v3 corrects a stale
  profile join and rejects time mismatches. The gas fraction at this plane is
  not proof of headspace delivery. No remote or GPU jobs are launched.
- **Full-apparatus startup continuation completed on 20 MPI ranks.** Docker
  `0b6d29bb43bc`, StartedAt 2026-10-25 11:16:42 UTC, exact-ID guard verified by
  root. Normal End at actual .00502116666404 s, with a complete native20
  checkpoint and no floor/clipping/nonfinite/ledger failures. It started from
  .00004368 s with eight outer iterations. Five boundary samples have maximum
  incoming Mach .000234; native face mapping/flux checks pass. This remains an
  exploratory static-ambient control; its later reservoir check is separate.
  Bundle: `results/runs/i4f-two-tank-four-mouth-fixed8-physical-continue-20261025T1110Z/`.
  Owner: Luna coupling worker.
- **Eight versus sixteen outer iterations:** both three-step cases ended
  normally with complete native20 states on the same partition. All four-mouth
  flow/pressure/inventory screens pass; full-volume field differences are small.
  This covers only 43.68 microseconds. Eight-loop post-startup step increments
  were about 20% cheaper; cold wall time was longer, so no whole-run speedup is
  established. Residual-control and separate-partition attempts are preserved.
  Profiles: `results/runs/i4f-fourmouth-observer-audit-20261025T102803Z/`.
- **Pressure-floor replay pair completed:** both arms reached .589617581493 s
  on the same 555-step schedule. Bulk outputs are nearly insensitive to 10/5 kPa
  floors, but old gas extrema reach 1490 m/s and 652 K before floor intervention.
  Bundle: `results/runs/i4f-pmin-replay-pair-20261025T095211Z/`.
- **Compressible reservoir boundary comparison completed** on the older
  one-tank/two-outlet reference. Both eight-rank arms ended normally at
  .588704120044 s with 373 matched steps and no pressure-floor contacts. Endpoint
  maximum speed changed 1162→67 m/s and global maximum temperature 495.5→293.3 K
  (gas versus liquid temperature maxima respectively). Bulk outputs stayed
  close. The 22.35x Courant-based timestep estimate is not measured speedup or
  proof of stability. Exact patch-only fragments and provenance are in
  `experiments/openfoam/i4f/reservoir_bc_verification/tested-ambient-patches/`.
  Pair outputs: `results/summaries/i4f_20261025/ambient-reservoir-pair-r2-*`.
  Failed pre-GO attempts remain preserved. No GPU solver port.
- **Geometry/init evidence:** the 1,779,258-cell divider mesh passes configured
  quality (max nonorthogonality 58.020 degrees); the no-wall variant remains
  held. Native initialization has exactly 1.350 m3 water and .301493 m3 gas per
  tank, plus .87597/.87602 m3 assumed primed-line water. Every cell is classified
  once. Earlier missing-alphat startup and four-rank deadline-without-checkpoint
  failures are preserved; neither is a complete discharge result. Older aerial
  queues and old one-tank discharge continuations remain stopped.

## Current inputs and scientific direction

The [hardware record](../experiments/i4f_hardware_notes_20261024.json) contains
confirmed .900 m tank diameter, .300 m valve diameter, 1.350 m3 liquid per tank,
and gas headspace .20–.25 times liquid volume, with two tanks/two outlets each.
The next reference uses 12 bar absolute and 13 bar sensitivity. About five
seconds is discharge duration, not opening time. Four dividers starting halfway
through each transition are the first-pass layout; orientation/thickness and
pipe ID remain inferred/assumed. Downstream passages initially contain air,
confirmed by the user; tank-to-valve water is accounted separately. Fully
primed old lines are a superseded initial-state assumption.

Root inspected the corrected four-arc ruled envelope and fitted divider
sections. Earlier CAD plate gaps and a .05904 m2 accidental throat are fixed in
`integrity-audit-aligned-ruled-v4`; its sampled minimum is the pipe inlet within
about 1 ppm. This is not a proof of the continuous minimum or measured geometry.
The [standalone generator](../scripts/i4f_four_outlet_geometry/README.md) uses
an isolated locked CAD environment; the explicit legacy layout and new compact
default were both checked. It now supports horizontal and vertical tank axes,
with both assemblies and connection sections generated and inspected. The
vertical arrangement preserves tank capacity and fixed branch spines under an
explicit provisional placement convention; no discharge benefit is established.
A same-grid
no-divider preparation adds 308 faces above the configured nonorthogonality
limit, so it remains held rather than a clean engineering comparison.
Select the first physical comparison from the completed baseline. A
primed/air-filled comparison is an initial-state
sensitivity with different total water inventories, not a matched design gain.
The same-envelope divider/no-divider comparison remains a candidate; its
no-wall mesh is currently held. The old 1/5 s opening pair remains hypothetical
and unlaunched.

Six revised-inventory reduced scenarios plus a timestep refinement are complete;
root inspected the plot. They predict the mean-level intake event, not emptying
or a five-second release. Early coarse/fine CFD histories are compared through
.20 s with native inventory/geometry caveats. The gas-energy remainder remains
unresolved. Results and interpretation are in
[the working scientific note](I4F_SCIENTIFIC_NOTE.md).

The [new 3D cutaway movie](../results/summaries/i4f_20261025/tank-cutaway-10x.mp4)
uses thirteen saved states through .560717 s, with the combined-run seam labeled.
It is the older 9-bar, one-tank/two-outlet case. The 10x slow H.264 video is
1280x720, 24 fps and 6.875 s. Root inspected first/middle/last images, ffprobe,
and a decoded final video frame. No complete emptying or new geometry is shown.
**A complete verified discharge and hardware validation remain unachieved.**

The [published results index](../results/summaries/i4f_20261025/README.md) contains
selected figures, JSON/CSV summaries and video. Executed solver source and the
small four-outlet case dictionaries are included for the shared-repo handoff;
native meshes/restarts remain separate. `make check`: 721 passed, one optional
Docker test skipped, four subtests passed.

The overnight outage came from account `v` requesting reboot at 00:03 UTC;
Tailscale/Docker stopped normally. NVIDIA modeset errors continued until
07:32 UTC before the successful boot at 07:33. No driver/network settings were
changed. New unrelated GPU-model workloads are left alone; current tasks use CPU.

## Earlier evidence

The scientific note links the retained numerical failures, reduced-model results
and prior comparisons. Historical status prose is preserved verbatim in
[`previous-STATUS.md`](../results/runs/i4f-status-consolidation-20261025T103658Z/previous-STATUS.md); it is not a live queue. Actual run directories and Docker state remain authoritative.
