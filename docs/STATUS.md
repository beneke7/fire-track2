# Live project status

Updated: 2026-10-25 12:36 UTC. Workstation priority: **I4F internal discharge**.
Aerial work continues separately on the server. User requested publication of
the reviewed code, summaries and video; HPC execution belongs to another agent.

## Current execution

- **Full-apparatus startup continuation completed on 20 MPI ranks.** Docker
  `0b6d29bb43bc`, StartedAt 2026-10-25 11:16:42 UTC, exact-ID guard verified by
  root. Normal End at actual .00502116666404 s, with a complete native20
  checkpoint and no floor/clipping/nonfinite/ledger failures. It started from
  .00004368 s with eight outer iterations. Five boundary samples have maximum
  incoming Mach .000234; native face mapping/flux checks pass. This remains an
  exploratory static-ambient control; no later hours-long stage is armed yet.
  Bundle: `results/runs/i4f-two-tank-four-mouth-fixed8-physical-continue-20261025T1110Z/`.
  Owner: Luna coupling worker.
- **Eight versus sixteen outer iterations:** both three-step cases ended
  normally with complete native20 states on the same partition. All four-mouth
  flow/pressure/inventory screens pass; full-volume field differences are small.
  This covers only 43.68 microseconds before gas ingestion. Standard residual
  control at 1e-8 still used all sixteen loops; its separate-partition attempt
  is preserved, not repeated for bookkeeping. Eight-loop cold wall time was
  longer; two post-startup step increments were about 20% cheaper, which is
  limited throughput evidence, not a demonstrated whole-run speedup.
  Profiles: `results/runs/i4f-fourmouth-observer-audit-20261025T102803Z/`.
- **Pressure-floor replay pair completed:** both arms reached .589617581493 s
  on the identical 555-step schedule, with complete native8 checkpoints.
  Endpoint tank pressure and outlet flow are nearly insensitive to 10/5 kPa
  floors, although intermediate iterations differ. This does not clear the
  old fields: nearby gas reaches about 1490 m/s and 652 K. The speed-limiting
  cell has Co about .5004; gas speed exceeds 1000 m/s before the first floor
  intervention. Root inspected the comparison and extreme-field plots.
  Bundle: `results/runs/i4f-pmin-replay-pair-20261025T095211Z/`.
- **Compressible reservoir boundary comparison completed** on the older
  one-tank/two-outlet reference. Both eight-rank arms ended normally at
  .588704120044 s with 373/373 matched steps, native checkpoints and no pressure
  floor contacts. At matched pre-contact time .588511510680, the static
  ambientAnnulus inflow reached Mach 2.57 with reconstructed mass-weighted
  stagnation pressure 150.1 kPa; the 100 kPa/293.15 K compressible-reservoir
  condition held it at 100 kPa with max inflow Mach .0122. Endpoint global
  maximum speed changed 1162→67 m/s and global maximum temperature 495.5→293.3 K
  (the latter maximum is gas in the static arm and liquid in the reservoir arm).
  Tank-zone pressure, sampled mouth flow and phase-ledger defects stayed close
  under the fixed original timestep schedule. The estimated 22.35× timestep
  headroom is a Courant-based bound, not measured runtime speedup or proof of
  global stability. This is boundary sensitivity evidence, not hardware
  validation; shared-mixture temperature and ambient coupling remain
  unresolved. Exact patch-only fragments for `ambientAnnulus`, `externalSides`
  and `farOutlet`, plus source/hash provenance, are in
  `experiments/openfoam/i4f/reservoir_bc_verification/tested-ambient-patches/`.
  Pair outputs: `results/summaries/i4f_20261025/ambient-reservoir-pair-r2-*`.
  The failed pre-GO schedule attempt remains preserved and released no solver
  ranks. No GPU solver port.
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
