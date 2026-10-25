# Live project status

Updated: 2026-10-25 14:24 UTC. Workstation priority: **I4F internal discharge**.
Aerial work continues separately on the server. User requested publication of
the reviewed code, summaries and video; HPC execution belongs to another agent.

## Current execution

- **Updated-apparatus continuation is running on ten MPI ranks.** Docker
  `715ddc276b6e`, StartedAt 2026-10-25 13:23:49 UTC, exact identity independently
  verified. The 303,108-cell pilot completed .050021166664 s in 506 seconds
  with normal End, all 14 native restart fields, zero pressure-floor contacts
  and phase-ledger errors below 2e-7 of initial inventories. Continuation
  targets .8 s, with a three-hour hard bound and save ten minutes earlier;
  full fields every .05 s support rendering. This is explicitly quality-limited:
  two configured face-tet checks fail; the other eight rows pass. It is not a
  passed mesh gate or hardware validation. Owner: Luna coupling worker; bundle
  `results/runs/i4f-quality-limited-fourmouth-continue-20261025T131742Z/`.
  A .2 s native checkpoint is available; root verified progress through .31471 s
  with zero raw pressure-floor contacts.
- **Fine 1,779,258-cell reservoir check is running on ten MPI ranks.** Docker
  `1b4d0094bba8`, StartedAt 2026-10-25 13:48:54 UTC, exact identity verified.
  It starts from the approved fine initial state with the tested ambient BCs,
  targeting .05 s under a four-hour bound. Source binary and nominal physics
  match the coarse run; native gas capacities differ by about 1% through mesh
  volume discretization. The first complete .005 s checkpoint has zero raw
  pressure-floor contacts; recent steps cost about 40 seconds on ten ranks.
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
pipe ID remain inferred/assumed. Initial downstream fill is still a pending
question; fully primed old lines hold approximately .88 m3 extra per tank.

Root inspected the corrected four-arc ruled envelope and fitted divider
sections. Earlier CAD plate gaps and a .05904 m2 accidental throat are fixed in
`integrity-audit-aligned-ruled-v4`; its sampled minimum is the pipe inlet within
about 1 ppm. This is not a proof of the continuous minimum or measured geometry.
The [standalone generator](../scripts/i4f_four_outlet_geometry/README.md) now
reproduces its geometry with an isolated locked CAD environment; default BREP
metrics and images were checked. It supports the current horizontal layout;
the revised four-outlet vertical layout is not implemented. A same-grid
no-divider preparation adds 308 faces above the configured nonorthogonality
limit, so it remains held rather than a clean engineering comparison.
Select the first physical comparison from the completed baseline. If line fill
remains unknown, its extra ~1.75 m3 across the apparatus takes priority over a
divider optimization. A primed/air-filled comparison would be an initial-state
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
