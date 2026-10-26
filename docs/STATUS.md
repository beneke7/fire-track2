# Live project status

Updated: 2026-10-26 04:36 UTC. Priority: **I4F internal pressure-driven discharge**.
Aerial/HPC work belongs to the separate server agent. No complete trustworthy
current discharge, exterior sheet, hardware validation or scientific gate pass yet.

## Current execution

- **Stock source treatment, 299,248 cells / ten MPI ranks:** Docker
  `4a5dd1dccbee`, StartedAt 2026-10-26T04:10:38.502224958Z, is advancing
  from the exact .170021166664 s checkpoint toward .46 s, then the useful
  discharge interval if healthy. Latest check: .216521 s, 185 completed steps,
  zero raw pressure contacts or diagnostic errors. Current bundle:
  `results/runs/i4f-stock-cold-299248-stage02-20261026T040738Z/`.
  Authority: its `stock-campaign-recovery-status.json` and service
  `i4f-stock-cold-299248-recovery-stage02-campaign.service`.
  Original campaign deadline remains **2026-10-27 02:10:45 UTC**.
  The diagnostic fork uses the standard MULES corrector source update;
  other physical inputs and numerical controls match the coarse reference.
- **Bend/outlet refinement, 881,431 cells / ten MPI ranks:** Docker
  `bc850309e648`, StartedAt 2026-10-26T04:10:55.78655512Z, is advancing
  from exact .189271166664 s toward .7 s. Latest check: .206771 s,
  69 completed steps, zero raw contacts or diagnostic errors. Current bundle:
  `results/runs/i4f-881k-outlet-bend-diagnostic-20261025T2325Z-stage05-resource-save-recovery3/`.
  Authority: its `campaign-recovery-status.json` and service
  `i4f-881k-outlet-bend-diagnostic-recovery-stage05-campaign.service`.
  Original outer deadline remains **2026-10-27 16:25:42 UTC**.
  Bend/transition/outlets are refined, while tanks remain coarse and the valve
  source retains 48 bands. All nine configured mesh-quality rows pass; optional
  concavity flags and about -.453% downstream line-volume difference remain.
- **Disk resource save and recovery:** both preceding children saved normally
  at 03:34 UTC when free space fell below 20 GiB. Stock saved .170021 s;
  bend refinement saved .189271 s. Both had all 14 fields, exact uniform/time,
  normal End, zero contacts/errors and no PAUSE. This was an automatic resource
  stop, not a numerical failure or user pause. New children preserve meshes,
  partitioning, physics/numerics, binaries and original t=0 phase ledgers.
  Original terminal statuses and failed preparation attempts remain preserved;
  they are **not the live campaign authorities**. Recovery proof:
  `results/runs/i4f-disk-save-recovery-prep-20261026T0340Z/recovery-plan.json`.
- **Conditional follow-up:** a 456,954-cell continuation from the completed
  refined-tank .399995 s checkpoint toward .46 s is prepared. It compares
  against the original coarse frozen-source failure; stock failure is only
  its resource trigger. Waiter `i4f-thermal-stock-fallback-attempt4-buffer25-waiter.service`
  is verified active, held on the actual running stock stage02; no fallback
  GO, launch manifest or container exists. Its absolute wait deadline is
  2026-10-26 14:33:56 UTC. It never triggers on disk/healthy wall saves or PAUSE.
  Fresh admission is 25 GiB, based on the measured-file/estimated <3 GiB I/O
  envelope; the original 20 GiB runtime guard is unchanged. Authority:
  `results/runs/i4f-tank-interface-thermal-fallback-stockfailure-20261026T0332Z-attempt4/conditional-status.json`.
- **Rendering:** watcher attempt2 exited at 03:35 after the resource save.
  Replacement `i4f-current-discharge-milestone-render-attempt3.service` is
  verified active, actual PID 1587947, following the exact live recovered 881
  identity and its current status. Its immutable deadline is
  **2026-10-27 16:55:42 UTC**; it must wait for a healthy native checkpoint
  >=.65 s with resolved water, using this 881 trajectory's own cold prefix,
  fixed camera/scales, CPU/Mesa and actual state holds. No new movie exists.
  Authority: `results/runs/i4f-current-discharge-milestone-render-20261025T233209Z/attempts/watcher-attempt3-20261026T0420Z/milestone/watch-status.json`.
  Native mouth preflight found 960 faces and .149999993 m2 per outlet.
- **Resources:** both current Docker identities, GO/input-freeze hashes,
  exact-ID guards and advancing steps are verified. Twenty project MPI ranks
  share the host with unrelated work. A bounded 02:54 UTC sample delivered
  6.64/6.48 CPU equivalents to stock/bend and about 6.56 to other processes,
  with no container quota throttling and negligible I/O wait. This is one
  sample, not a rank-scaling result. Unrelated workloads stay untouched.
  Future controller helpers passed second-generation preparation checks for
  wrapper idempotence, empty checksum lists and numeric dictionary display;
  failed no-solver preparations remain preserved.

## Current evidence and limits

- **Tank refinement finished near .4 s.** Coarse/refined native endpoints differ
  by 91.4 microseconds; no interpolation is used. Tank-A gas temperature is
  261.207/254.920 K, pressure 654.125/642.040 kPa, native seat flow changes
  -1.04%, and withdrawal changes -1.107 L (-.584%). Initial headspace differs
  +.883% and feed water about -7.1 mL. Mixed-cell gas-volume share falls
  19.80% to 9.69%. This is mesh sensitivity, not convergence or identified
  heat transfer. [Comparison](../results/summaries/i4f_20261025/tank-interface-terminal-comparison.png).
  The refined endpoint had final outer dp=2.415 Pa and water/gas ledger
  defects +.045687/+.000151 kg. Root checked 38 tank-state EOS/work/reference
  identities, CSV/output hashes and all 15 terminal native-file hashes.
- **Gas energy remains qualified.** Near .4 s, the two-tank uniform-headspace
  delta(U*)+integral(pbar dV) proxy is +137.319 kJ coarse and +92.225 kJ refined.
  This is not measured heat or a closed total-energy defect. Open-domain gas
  inventory loss is distinct from a boundary-flux-balanced conservation residual.
  [Analysis](../results/summaries/i4f_20261025/tank-interface-terminal-comparison.json).
- **Pressure instability is unresolved.** The reference/restart cases develop
  persistent kPa-scale outer updates near .443 s. Transonic-off, pressure-component
  relaxation .5 and nonOrth1 did not remove it; U relaxation .5 and half-Courant
  produced raw floor contacts earlier. Switching the source treatment only at
  .4 s also failed; it does not replace the current true-cold trajectory.
  Corrected rank-prefixed logs locate raw contacts in nearly pure water in the
  rising bend; these intermediate solves do not demonstrate physical cavitation.
  [Raw review](../results/summaries/i4f_20261025/pressure-contact-review.json).
  The executed solver never calls p_rgh.relax(), so a fields.p_rgh dictionary
  factor alone is not a whole-pressure damping trial. No production equation
  change is adopted; finite water compressibility remains conditional.
- **Source-control startup is nearly coincident.** At exact .050021 s,
  stock/frozen tank observables and seat fluxes match closely, while local
  interface differences remain. Initial fields/mesh/checked physics match;
  binaries differ in diagnostic source/object code, so executable identity is
  not claimed. Checked .05 restart phase-temperature files are regenerated
  from common T: internal differences <=5.68e-14 K, boundary resets <=.001758 K.
  Original checkpoints and pre-GO hashes remain recoverable. Evidence:
  `results/runs/i4f-stock-vs-frozen-cold-pilot-20261026T023644Z/analysis/comparison.json`.
- **Outlet diagnostics:** automatic native analysis covers signed water flux,
  five-channel flows, full-mouth projected-area flux CV and reconstructed
  momentum. The new tested `outlet_secondary_metrics` helper supplies direction
  distributions, sign/undefined-flow accounting, raw gas-area proxy and separate
  momentum resultants; its native adapter still needs integration on wet data.
  Sheet thickness, recirculation and gas-quality history remain incomplete.
  Saved phi-alphaPhi0.water is an endpoint complement across pressure stages,
  not automatically the solver's same-stage gas-volume or gas-mass flux.
  [Source audit](../results/runs/i4f-outlet-flux-semantics-audit-20261026T032902Z/source-semantics.json).
- **Storage recovered without discarding native evidence.** Verified regenerable
  exports freed 3.865 GB, obsolete project Flutas build caches were evicted with
  binaries/metadata retained, and lossless native archives reclaimed 15.031 GB
  net. All four archive/manifest hashes match; every member was streamed and
  checked before deleting only its duplicated uncompressed intermediate file.
  Initial/restart-seed and latest complete checkpoints remain in place.
  [Archive index and restore commands](../results/archives/index.json); payloads
  are local/ignored, while per-file manifests are retained. Free space reached
  40.37 GiB before recovery copies; the original 20 GiB runtime guard is unchanged.
- **Software checks:** make check passed 740 tests and four subtests; one optional
  real-Docker test was skipped. These checks do not validate the apparatus.
  The earlier strict 2% source-flow startup screen remains HOLD; no nearfield
  appearance or analytical consistency check supplies hardware validation.

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
native meshes/restarts remain separate. Current software-check results are recorded above.

The overnight outage came from account `v` requesting reboot at 00:03 UTC;
Tailscale/Docker stopped normally. NVIDIA modeset errors continued until
07:32 UTC before the successful boot at 07:33. No driver/network settings were
changed. New unrelated GPU-model workloads are left alone; current tasks use CPU.

## Earlier evidence

The scientific note links the retained numerical failures, reduced-model results
and prior comparisons. Historical status prose is preserved verbatim in
[`previous-STATUS.md`](../results/runs/i4f-status-consolidation-20261025T103658Z/previous-STATUS.md); it is not a live queue. Actual run directories and Docker state remain authoritative.
