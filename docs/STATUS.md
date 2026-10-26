# Live project status

Updated: 2026-10-26 02:14 UTC. Workstation priority: **I4F internal discharge**.
Aerial work continues separately on the server. User requested publication of
the reviewed code, summaries and video; HPC execution belongs to another agent.

## Current execution

- **Bend/outlet refinement completed its cold pilot and is continuing:**
  881,431 cells, ten MPI ranks. Pilot `b5d05f19814c` ended normally at
  .050021166664 s after 212 steps, with all 14 restart fields and no raw
  pressure contacts. Child `212925cc3be6`, StartedAt
  2026-10-26T00:54:50.781946359Z, is advancing from that checkpoint toward
  the .7 s filling/sheet interval; the latest check reached .128021 s with
  no raw pressure contacts or diagnostic errors.
  Source bands stay
  at 48 layers and tank resolution remains coarse; the refined region covers
  the bend/transition failure cells. All nine configured quality rows pass;
  optional concavity flags and approximately -.453% line-volume differences
  remain explicit. Bundle:
  `results/runs/i4f-881k-outlet-bend-diagnostic-20261025T2325Z/`.
  The campaign wrapper initially called its one-shot launcher twice after
  successful GO and recorded a false failure. That wrapper is repaired and
  the existing pilot is adopted under the active campaign service; Docker, GO
  and its original start are unchanged. Terminal capture is bounded to 300 s.
  The rate-derived campaign deadline is 2026-10-27 16:25:42 UTC. Future child
  runners record process-local MPI yielding; the live pilot was not changed.
  First child preparation also exposed an undefined Python name. Failed
  no-launch child attempts are preserved; stage04 passed undefined-name lint,
  actual checkpoint preparation, four checksum checks and exact-ID GO.
  The continuation is real, rather than a prepared but unstarted queue.
- **Tank/interface refinement completed:** 456,954 cells, ten MPI
  ranks, Docker `b31f9fc09916`, StartedAt 2026-10-25T23:59:36.593088248Z,
  reached .399995294759 s with original physics/numerics. It resumed the complete native
  .135021166664 s checkpoint, preserving time-zero mass ledgers. The preceding
  healthy branch was saved at root's resource-priority request to free a short
  diagnostic slot; this was neither user PAUSE nor numerical failure. Both
  short diagnostics then ended, so the saved thermal run resumed immediately.
  Docker ended normally at 02:10:27 UTC, all 14 restart fields are captured,
  and raw contacts/clipping and diagnostic errors remain zero. The final outer
  pressure update was 2.415 Pa; cumulative water/gas ledger defects are
  +.045687/+.000151 kg, respectively (.001429%/.000443% of initial mass).
  Failed no-solver preparation attempts and exact restart hashes are retained.
  Bundle: `results/runs/i4f-tank-interface-thermal-resolution-20261025T223913Z/continuation-attempt5/`.
  Read-only terminal analysis completed; root inspected the plot and independently
  checked EOS/work/reference arithmetic for 38 tank-states and all 15 terminal
  native-file hashes. No solver or controller change was made by this analysis.
  Analysis bundle: `results/runs/i4f-tank-refinement-terminal-comparison-20261026T014438Z/`.
- **Stock source treatment from the true cold state is running.**
  The dispatcher automatically launched the fresh 299,248-cell, 48-layer,
  initially air-filled case after thermal endpoint capture. Docker
  `ae3d81dc9d01`, StartedAt 2026-10-26T02:10:45.881380584Z, has completed
  28 steps through .004271 s with zero raw contacts or diagnostic errors.
  Only the phase-source update treatment changes; physical inputs, other solver
  controls, initial geometry/inventories and raw-pressure criteria stay fixed.
  A guarded .05 s pilot precedes the .46 s comparison and, if healthy, the
  useful discharge interval. The switched .4 s restart below cannot substitute
  for this independent trajectory. Actual Docker, exact-ID guard, GO and
  advancing native steps are verified; the campaign controller is active.
  Bundle: `results/runs/i4f-stock-from-cold-299248-20261026T002045Z-attempt2/`.
  The thermal waiter handed off successfully; the stock campaign's absolute
  deadline is 2026-10-27 02:10:45 UTC, 24 h from its own pilot start. A prospective
  half-terminal-step endpoint rule handles discrete solver End times without
  changing pressure, mass or other scientific criteria.
- **All recent short numerical variants stopped before .46 s.** The original
  reference and restart controls develop a persistent kPa-scale pressure cycle
  near .443 s. Transonic-off, pressure-component relaxation .5 and one added
  non-orthogonal correction retain that cycle; the last saved at
  .443765279816 s with a 3.56 kPa final update and zero raw pressure contacts.
  Momentum relaxation .5 saved at .410704346663 s after three raw contacts
  reaching -127.21 kPa. Stock-source switching from the same .400087 s seed
  saved at .410533462436 s after one 6.380 kPa raw contact. The earlier
  half-Courant case also contacted its 10 kPa floor. Positive final saved
  pressures and normal End do not clear these intermediate events; no long
  continuation was selected from any of these failed variants.
- **Raw failure cells are now identified, without another simulation.** The
  parser had missed `[rank]` prefixes. Corrected analysis reconciles all
  affected-cell records, global minima and all ten rank summaries with no
  omitted cells. U-relaxation's worst event is rank 0/cell 7902 at
  (3.436916,.736759,.964727) m, alpha_water=.999706; the stock event is nearby
  cell 7966, alpha_water=.9999999986. These are intermediate solves in the
  rising bend, not demonstrated physical cavitation. Recorded liquid support
  is not water mass removed by clipping. See the
  [corrected raw data](../results/summaries/i4f_20261025/pressure-contact-review.json).
- **Tank mesh sensitivity now reaches the .4 s comparison.** Coarse/refined
  endpoint times differ by 91.4 microseconds, without interpolation. Tank-A
  gas-mass-weighted T is 261.207/254.920 K and pressure 654.125/642.040 kPa;
  native seat flow changes -1.04% and drawdown -1.107 L per tank (-.584%).
  Gas volume in mixed cells falls from 19.80% to 9.69%. Initial gas capacity
  is .883% larger on the refined mesh, while total feed water is 7.1 mL lower;
  this is sensitivity with a geometric confound, not convergence or identified
  heat transfer. See the [terminal comparison](../results/summaries/i4f_20261025/tank-interface-terminal-comparison.png).
- **Earlier focused evidence remains qualified.** Suppressed-diffusion sealed
  withdrawal mesh refinement reduces adiabatic pressure error 6.66 to 1.92%.
  The all-water valve-source benchmark reduces flow error 6.34 to 1.38% with
  source refinement; the separate strict 2% apparatus startup screen remains
  HOLD at its first two microsteps. Through .4 s, current CFD and the reduced
  model differ 7.67% in pressure and 2.480 L in tank-A water. None is hardware
  validation. Observer source-lag identities close to roundoff without proving
  the cause of the pressure cycle; no speculative equation patch was adopted.
- **Current gas storage/work proxy is computed.** For both baseline tanks
  through clean .400087 s, delta(U*)=-195.307 kJ and integral(pbar dV)=332.626 kJ,
  leaving +137.319 kJ. The new refined near-.4 s endpoint gives -235.708 kJ
  storage, +327.933 kJ work proxy, and +92.225 kJ remainder. Work coarsening
  changes .844/.763 kJ per tank, coarse/refined. These are uniform-headspace
  proxies, not measured heat or closed total-energy defects. Open-domain gas
  inventory loss is not conservation error. See the
  [terminal analysis](../results/summaries/i4f_20261025/tank-interface-terminal-comparison.json).

The bounded Astra hard-blocker review selected two actions: continue the actual
bend refinement and run stock source treatment from cold; both are running. Finite water
compressibility remains conditional: nearly pure-water pressure storage can
change substantially despite small bulk density change, but an earlier Tait
restart did not remove clipping. Physical pressure-margin interpretation needs
settled native acceleration/curvature evidence. No scientific gate passed.

The .65 s render watcher is active for the adopted 881k campaign. Native cell
ordering, processor mapping and four mouth cuts (960 faces and .149999993 m2
each) pass preflight. It uses this mesh's own cold states without a 299k prefix.
The fixed renderer deadline is 2026-10-27 16:55:42 UTC, 30 min after the revised
campaign bound; its resolved-water screen, CPU/Mesa backend and PAUSE policy
remain in force. No new movie exists yet. Current corrected-source movies end at .443669 s
before useful exterior liquid. A complete trustworthy discharge remains pending.
Aerial and historical primed-line queues stay stopped; HPC belongs to another
agent. Unrelated workloads are untouched. Two ten-rank jobs share the machine
with unrelated CPU work, so delivered capacity is lower than the MPI count.

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
