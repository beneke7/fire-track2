# Live project status

Updated: 2026-10-26 05:56 UTC. Priority: **I4F internal pressure-driven discharge**.
Aerial/HPC work belongs to the separate server agent. No complete trustworthy
current discharge, exterior sheet, hardware validation or scientific gate pass yet.

## Current execution

- **Standard phase-source update, 299,248 cells / ten MPI ranks:** Docker
  `7a4508c7f1fe`, StartedAt 2026-10-26T05:43:15.899063019Z. Latest native
  observation: 0.370422 s, zero raw contacts/errors. Target .46 s,
  then 1.3 s if healthy. It continues exact .341377415807 s from stage02.
  Current bundle: `results/runs/i4f-stock-cold-299248-stage03-20261026T054311Z/`.
  Authority: `results/runs/i4f-resource-save-recovery-v2-20261026T053959Z/stock-campaign-recovery-v2-status.json`;
  unit `i4f-stock-cold-299248-recovery-v2-campaign.service`.
  Original campaign deadline remains **2026-10-27 02:10:45 UTC**.
  The diagnostic binary uses the standard MULES corrector source update;
  its physical inputs and other numerical controls match the coarse reference.
- **Bend/outlet refinement, 881,431 cells / ten MPI ranks:** Docker
  `d1e8e2922f8e`, StartedAt 2026-10-26T05:42:41.284617235Z. Latest observation:
  0.266271 s, zero raw contacts/errors. Target .7 s; exact native
  parent .253271166664 s. Tanks stay coarse; the valve source retains 48 bands.
  Current bundle: `results/runs/i4f-881k-outlet-bend-diagnostic-20261025T2325Z-stage06-resource-save-recovery3/`.
  Authority: `results/runs/i4f-resource-save-recovery-v2-20261026T053959Z/881-campaign-recovery-v2-status.json`;
  unit `i4f-881k-outlet-bend-recovery-v2-campaign.service`.
  Original outer deadline remains **2026-10-27 16:25:42 UTC**.
- **Storage and recovery:** at 05:34 both preceding children saved normally,
  all fourteen fields, after a project archive helper's default Docker JSON
  logger recorded its binary export stream and crossed the unchanged 20 GiB
  guard. That helper/log was removed; the safe retry used verified logging
  disabled. Two inactive aerial volumes are now losslessly archived with all
  2,192 file hashes and metadata checked by worker and root before removal.
  The archives save about 3.9 GB net and have restore commands in the
  [index](../results/archives/index.json). Free space was about 26 GiB after
  relaunch. An earlier purported 04:49 disk sample was not corroborated.
  New controller admission is 25 GiB, based on measured incremental .46/.7 s
  storage of about 3.1 GB plus the later stock-stage budget; runtime save stays
  at 20 GiB. Original campaign clocks, numerical settings, binaries, meshes,
  partitioning and t=0 phase ledgers are preserved. Old controller statuses
  remain evidence and are not current runtime authorities.
- **Conditional tank-refinement continuation:** prepared 456,954-cell case,
  .399995 to .46 s, remains unlaunched. Gate
  `i4f-thermal-stock-fallback-attempt5-v2-waiter.service` follows the exact V2
  stock chain, waits for a captured numerical failure and released ranks,
  requires 25 GiB and shared project ranks <=20, and honors PAUSE.
  It never triggers on healthy resource saves. Deadline: **2026-10-26 14:33:56 UTC**.
  Authority: `results/runs/i4f-tank-interface-thermal-fallback-stockfailure-20261026T0332Z-attempt5-v2-20261026T055219Z/conditional-status.json`.
  Its scientific comparison is refined-tank frozen-source versus the original
  coarse frozen-source failure; stock failure is only the resource trigger.
- **Rendering:** attempt4 is active under
  `i4f-current-discharge-milestone-render-attempt4.service`, following the exact
  V2 fine-mesh chain. It waits for a healthy complete state >=.65 s with
  resolved water, fixed camera/scales, CPU/Mesa and actual-state holds.
  Deadline remains **2026-10-27 16:55:42 UTC**. No new discharge movie exists.
  Authority: `results/runs/i4f-current-discharge-milestone-render-20261025T233209Z/attempts/watcher-attempt4-20261026T0546Z/milestone/watch-status.json`.
- **Geometry preparation:** the opt-in flush pipe/transition junction has
  inspected four-branch sections and valid connected CAD solids. A worker is
  preparing its native mesh and cold initial state with the existing source
  refinement and standard phase-source treatment. This uses bounded one-CPU
  preparation and tmpfs staging alongside the twenty project MPI ranks;
  no corrected-geometry CFD run has launched. Unrelated workloads stay untouched.

## Current evidence and limits

- **Native-wall geometry audit:** a real ~18.5 mm roof shoulder at x=3.911 m
  lies about 4 cm downstream of the recorded mixed-cell pressure-cycle site.
  The pre-mesh surface and frozen generator show an exposed pipe/loft overlap,
  not a meshing artifact or confirmed hardware feature. The opt-in flush
  junction removes it at all four branches; CAD tank/feed geometry is unchanged,
  and summed downstream branch storage changes -1.012 L. Root inspected the
  matched sections, area plots and assembly. Its CFD effect is untested.
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
