# Live project status

I4F snapshot: 2026-10-26 09:01 UTC. Workstation priority: **I4F internal pressure-driven discharge**.
Aerial/HPC work belongs to the separate server agent. No complete trustworthy
current discharge, exterior sheet, hardware validation or scientific gate pass yet.

## HPC Rouaix work and GitHub evidence publication

HPC readback **2026-10-26 12:36:16 UTC (13:36:16 CET)**: job **14650641**
(one node, 120 ranks, fixed 0.1 ms toward 5 s, 72 h cap) and **14648472**
(300 ranks, three nodes, short 0.1 ms trial) were PENDING/Priority with no
allocation or start estimate. This timestamp is a snapshot, not live status.
No unrelated account jobs were changed. W&B remains offline pending a destination.

Short one-node T1 job **14649329** completed all 500 steps through 0.05 s;
all 4,001 linear-solver records met their configured criteria. Peak speed
103.29355 m/s, bulk/interface Co 1.12154/0.56017, mass residual 1.05e-11 kg.
G1 gradient-limiter trial **14648417** failed its speed guard after a
6,975.25 m/s peak and ended at 0.0455 s; it did not complete its target.
The 64/120/240/300-rank original-scheme timing samples do not establish
healthy long-time behavior or a universal optimum.

ParaView CLI displays the 10,099,265-cell result using the requested
cell alpha.water >= 0.01 threshold at 0.05 s. The early cloud comparison
uses alpha >= 0.1; its time, detector and unresolved paper-width convention
prevent a developed Rouaix agreement claim. Only analytical E0 has passed.

The [published compact evidence bundle](../results/summaries/rouaix_hpc_20261026/README.md)
contains selected measurements, hashes, preview, diagnostic source and check
results. The [preserved HPC status snapshot](../results/summaries/rouaix_hpc_20261026/hpc-status-snapshot.md)
retains the full prior history. Raw CFD archives/mesh remain in verified
local/HPC storage, outside Git; this is a summary release, not a standalone
raw-data reproduction package. Frozen queued-job source is unchanged by Git
integration or the later local max-U metadata and accounting-parser fixes.

Publication checks on the integrated tree: 201 affected tests and Ruff passed;
all seven fresh E0 analytical checks passed. Full make check is not green:
collection needs matplotlib; the pre-merge diagnostic excluding that module gave 775 passed,
19 failed and 6 skipped, involving platform support, missing dependencies,
missing ignored fixtures and a retained digitization mismatch. The compact
check report preserves exact commands and outcomes.

## Current execution

- **Corrected-junction cold start, 299,214 cells / ten MPI ranks:** the pilot
  ended normally at exact .050021166664 s with all fourteen fields and zero
  raw contacts/errors. The first actual continuation is advancing at
  0.370794 s toward .46 s, then 1.3 s if healthy, with zero raw contacts/errors. Docker
  `23c2bb49e6e4`, StartedAt 2026-10-26T06:44:49.045490597Z; bundle
  `results/runs/i4f-flush-stock-cold-stage01-20261026T064444Z/`.
  Its four input manifests, exact GO/guard and completed steps are verified.
  The same standard phase-source update, water/ideal-air physics, SST, scalar
  valve and numerical settings match the old coarse standard-source case;
  the pipe/transition join and native mesh differ. Cold input begins with dry
  downstream passages; no failed fields are inherited. Authority:
  `results/runs/i4f-flush-stock-cold-campaign-20261026T060440Z/stock-campaign-status.json`;
  unit `i4f-flush-stock-cold-campaign-20261026t060440z-campaign.service`.
  Original new-campaign clock ends **2026-10-27 06:23:53 UTC**.
  Stage01 hard/save limits are 4 h / 3 h 40, measured from its actual StartedAt.
- **Older bend/outlet refinement, 881,431 cells / ten MPI ranks:** Docker
  `d1e8e2922f8e`, StartedAt 2026-10-26T05:42:41.284617235Z, remains running
  at 0.377900 s with zero raw contacts/errors, target .7 s.
  It retains the old overlapping-pipe geometry and frozen-source update.
  No priority save was needed: the failed standard-source case released the
  slot for the corrected cold run. Its current bundle is
  `results/runs/i4f-881k-outlet-bend-diagnostic-20261025T2325Z-stage06-resource-save-recovery3/`.
  Authority: `results/runs/i4f-resource-save-recovery-v2-20261026T053959Z/881-campaign-recovery-v2-status.json`;
  unit `i4f-881k-outlet-bend-recovery-v2-campaign.service`.
  Original outer deadline remains **2026-10-27 16:25:42 UTC**; the controller
  also retains an earlier inner deadline of **2026-10-26 12:25:55 UTC**.
  Reaching .7 s before that earlier deadline is not established.
- **Old standard-source cold trajectory failed numerically:** stage03 ended
  normally at .410269089521 s, but two intermediate pressure solves at
  .41005436428 s reached -9.095 and -80.959 kPa. All fourteen fields are saved;
  its .46 s target was not reached. The 0.08947 kg figure is liquid support
  associated with below-floor cells, not removed mass. The terminal saved
  minimum is positive and does not erase the raw events. No automatic restart.
  [Pressure/contact evidence](../results/summaries/i4f_20261025/stock-cold-pressure-contact-review.json).
- **Storage:** a temporary binary-export Docker log caused the earlier 05:34
  healthy resource saves; that helper/log was removed and subsequent exports
  disabled logging. Two old native volumes and selected Rouaix intermediates
  are losslessly archived. Verified duplicate snapshot copies were removed
  with explicit restore-prefix mappings; a symlink alias was preserved and
  counted once. Latest free space is about 34 GiB. See the
  [archive index](../results/archives/index.json). The runtime save trigger stays
  20 GiB; current inputs, checkpoints and phase ledgers remain recoverable.
- **Conditional tank refinement:** the prepared 456,954-cell .399995-to-.46 s
  trial is unlaunched behind both priority campaigns. A durable attempt7 waiter
  is active under `i4f-tank-interface-thermal-fallback-attempt7-v2-20261026t085430z.service`.
  Each whole campaign reserves ten ranks through healthy restart gaps; launch
  requires one reservation released by a verified terminal campaign and captured
  checkpoint, actual spare capacity, disk >=25 GiB, and no PAUSE. Low desktop
  noise is distinguished from sustained competing compute. The original old-stock
  numerical stop is the trigger, not the physical comparison: this trial compares
  tank-refined frozen-source fields with the older coarse frozen-source case.
  Admission deadline remains **2026-10-26 14:33:56 UTC**. Attempts5/6 are stopped
  and preserved. Authority:
  `results/runs/i4f-tank-interface-thermal-fallback-stockfailure-20261026T0332Z-attempt7-20261026T085430Z/conditional-status.json`.
- **Rendering:** the old 881 attempt4 watcher remains tied to that trajectory.
  Corrected-case attempt4 is separately active under
  `i4f-flush-stock-native-render-20261026t0646z.service`, following the exact
  corrected stage01 identity and its own cold prefix. It waits for a healthy
  complete state >=.65 s with resolved outlet/exterior water; CPU/Mesa, fixed
  camera/scales and actual-state 10x holds. No new discharge movie exists.
  Deadline: **2026-10-27 06:53:53 UTC**. Authority:
  `results/runs/i4f-flush-stock-native-milestone-render-20261026T0646Z-attempt4/milestone/watch-status.json`.
- **Compute:** twenty project MPI ranks are active alongside unrelated work.
  Routine archive/analysis work uses bounded one-CPU jobs. No GPU solver or
  GPU rendering was launched; unrelated workloads remain untouched.

## Current evidence and limits

- **Reduced model aligned to corrected geometry:** a new immutable input packet
  uses direct compact centerlines and native tank/headspace values. With no
  fitting, adiabatic/isothermal gas laws predict first mouth water around
  .617–.625/.585–.591 s and mean-level intake-crown endpoints 1.127/.970 s.
  Crown crossing is not emptying or validated gas breakthrough. Halving the
  adiabatic timestep changes arrival by 25 microseconds. Wet-feed/full-line
  volumes differ +.634/+2.081% from native Tank-A zones, explicitly retained.
  [Results and limits](../results/summaries/i4f_20261025/flush-filling-model-comparison.json),
  [thermal sensitivity](../results/summaries/i4f_20261025/flush-filling-model-thermo-sensitivity.png).
  The legacy input packet remains unchanged. Driver input integrity and both
  packets' downstream-water semantics are tested; `make check`: 746 passed,
  one optional Docker test skipped, four subtests passed. The
  [early CFD comparison](../results/summaries/i4f_20261025/flush-early-cfd-model-comparison.png)
  now covers complete .10–.25 s checkpoints. At .250021 s, mean tank withdrawal
  is 62.581 L versus 62.210 L (+.597%); native two-seat flow per tank is
  .608803 versus .604200 m3/s (+.762%). Local CFD gas-probe pressure is
  946.934 kPa versus adiabatic-model bulk 920.654 kPa; the differing pressure
  observables and thermal/geometry assumptions preclude a validation claim.
- **Native-wall geometry audit:** a real ~18.5 mm roof shoulder at x=3.911 m
  lies about 4 cm downstream of the recorded mixed-cell pressure-cycle site.
  The pre-mesh surface and frozen generator show an exposed pipe/loft overlap,
  not a meshing artifact or confirmed hardware feature. The opt-in flush
  junction removes it at all four branches; CAD tank/feed geometry is unchanged,
  and summed downstream branch storage changes -1.012 L. Root inspected the
  matched sections, area plots and assembly. The corrected native mesh has
  299,214 cells, valid four-branch sections,
  and all nine configured quality rows pass; the optional all-geometry check
  reports 6,345 concave cells. Its effect on pressure stability is untested.
  [Geometry proof](../results/summaries/i4f_20261025/pipe-transition-join-summary.json).
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
  .4 s also failed. The separate true-cold old-geometry control now reaches raw
  contacts near .410 s; the corrected-junction cold trajectory is running.
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
- **Outlet diagnostics:** the new in-repository native reader/CLI handles the
  compact four-mouth, ten-rank collated mesh without ignored-code dependencies.
  It combines native signed alphaPhi0.water with reconstructed U/raw alpha for
  secondary direction and momentum. Root found reversed interpolation weights
  inherited from the older v2 secondary reconstruction; the corrected owner
  weighting and signed face addressing have independent technical review and
  asymmetric-grid checks. Old outputs are preserved and superseded for these
  secondary quantities. Wet native Q matches v2 within 6.94e-18 m3/s; two dry
  snapshots retain numerical trace and withhold interpreted direction/momentum.
  Final evidence: `results/runs/i4f-native-outlet-secondary-ownerweight-final-20261026T055120Z/`.
  Existing native five-channel flux/CV analysis remains available. Gas-area
  proxy is not gas flux or breakthrough; sheet thickness, recirculation and
  gas-quality history remain incomplete. Saved phi-alphaPhi0.water crosses
  pressure stages, so it is not automatically same-stage gas flux.
- **Storage recovered without discarding native evidence.** Verified regenerable
  exports freed 3.865 GB, obsolete project Flutas build caches were evicted with
  binaries/metadata retained, and lossless native archives reclaimed 15.031 GB
  net. All four archive/manifest hashes match; every member was streamed and
  checked before deleting only its duplicated uncompressed intermediate file.
  Initial/restart-seed and latest complete checkpoints remain in place.
  [Archive index and restore commands](../results/archives/index.json); payloads
  are local/ignored, while per-file manifests are retained. Free space reached
  40.37 GiB before recovery copies; the original 20 GiB runtime guard is unchanged.
- **Software checks:** make check passed 743 tests and four subtests; one optional
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
