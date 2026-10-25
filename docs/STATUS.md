# Live project status

Updated: 2026-10-25 23:10 UTC. Workstation priority: **I4F internal discharge**.
Aerial work continues separately on the server. User requested publication of
the reviewed code, summaries and video; HPC execution belongs to another agent.

## Current execution

- **Live pressure-coupling diagnostic:** ten MPI ranks in Docker
  `dc9e1ff553ed`, StartedAt 2026-10-25T23:07:03.122833725Z, advance from the
  clean .400086712911 s checkpoint. It reached .402370906292 s in its first
  16 completed steps without raw pressure contacts. The only numerical change
  is one non-orthogonal pressure correction instead of zero; all pressure and
  momentum relaxation entries are absent. The bounded serial dispatcher tests
  momentum relaxation only if this arm fails before a healthy .46 s endpoint.
  No guard threshold is relaxed. Bundle:
  `results/runs/i4f-pressure-nonorth1-20261025T2304Z/`.
- **Finer-tank cold start completed cleanly:** the 456,954-cell mesh reached
  .050021166664 s in 212 steps, normal End at 23:04:47 UTC, with all 14 restart
  fields, zero pressure-floor contacts and cumulative water/gas mass defects
  below 2e-7 of their initial inventories. The last outer pressure update was
  .00126 Pa. Local tank/interface spacing is about 25 mm rather than 50 mm;
  the 48-layer valve bands are preserved. Native gas capacity differs by
  approximately .88%, so comparisons must normalize by each mesh's own initial
  gas volume. The conditional continuation to .4 s failed during preflight,
  before a solver step; the fine worker is repairing that setup failure using
  the saved pilot, not rerunning the cold start. Bundle:
  `results/runs/i4f-tank-interface-thermal-resolution-20261025T223913Z/`.
- **The principal blocker remains a repeated pressure-coupling cycle near
  .44 s.** The original 299,248-cell run saved at .443669498426 s after sustained
  3.29 kPa final outer updates. A clean restart control and the 279,536-cell
  source comparison reproduced the stop. Disabling the transonic pressure
  Jacobian stopped at .443765288530 s, and pressure-component relaxation .5
  stopped at .443684998512 s. Both retained alternating kPa-scale updates in
  mixed transition cells without raw pressure clipping; neither is a fix.
  The half-Courant trial instead encountered a raw intermediate pressure of
  2698 Pa at .410317423204 s and saved at .410421862107 s. This is a numerical
  diagnostic, not evidence of physical cavitation. All attempts and checkpoints
  are preserved. A normal solver End after a guard save is not convergence.
- **Localized source observers now execute correctly on MPI.** Two initial
  attempts stalled because a coupled matrix residual was evaluated on only one
  rank. They were stopped and preserved; diagnostics now evaluate coupled
  operations on every rank and restrict only extraction/printing. The clean
  observer completed .426970166588 s and the separate underconverged-state
  probe saved at .445999359584 s. The source-lag balance identity closes to
  roundoff, but finite lag is not established as the cause of the pressure
  cycle. No unproven source-equation correction has been adopted.
- **Controlled thermal mesh sensitivity is executed and published.** Four
  water–air withdrawal cases with 3/6/12/24 initial gas-layer cells completed
  .4 s. Pressure errors against adiabatic expansion at native gas volume are
  6.66/4.45/2.92/1.92%; temperature follows the same trend, despite gas-mass
  drift near .01%. Both phases are refined, turbulence is disabled and
  thermal diffusion suppressed. This isolates a numerical contribution in
  that limit, not the apparatus error or its correction. See the
  [figure and data](../results/summaries/i4f_20261025/README.md).
- **Current model comparison reaches .400087 s.** Tank-A pressure is
  654.125 kPa versus the forward adiabatic model's 607.529 kPa; native water
  inventory is 2.480 L lower. Temperature audits localize cooling to tank gas,
  while water-rich cells remain above 292.799 K at .4 s. Turbulent thermal
  diffusivity and mixed-interface resolution are material hypotheses;
  coefficient/time-scale estimates do not measure interphase heat flux or
  close total energy.
- **Valve-source accuracy improved, without a full mesh pass.** A wetted
  .30 m source at x=1.95–2.25 m replaces the old partly dry support. The
  all-water analytical duct error drops from 6.34% on 25 mm axial cells to
  1.38% on 6.25 mm cells. In the apparatus, 24/48-layer endpoint fluxes differ
  about 1.50%, but the unchanged strict 2% pointwise startup screen remains
  HOLD because of its first two microsteps. Later exploratory runs do not
  relabel that result.
- **No complete current sheet discharge yet.** The reduced full-bore-front
  model predicts mouth arrival near .612/.620 s and intake-crown exposure
  near 1.127 s; these are consistency predictions, not hardware validation.
  Current corrected-source movies stop at .443669 s before useful exterior
  liquid is resolved. The 881,431-cell downstream mesh is prepared but its
  conditional pilot remains held; it is not an executed refinement result.
  Legacy primed-line, one-tank and aerial runs are not resumed.

A bounded Astra review found no obvious pressure-operator sign error and
recommended controlled numerical/source and interface-resolution diagnostics.
Source tracing, the failed pressure-component trial and the live tank refinement
implement those directions; no repeated routine review is required. Current
runs use CPU only and leave unrelated GPU workloads untouched. Full logs and
restart fields remain in ignored run bundles. The prior detailed status is
preserved in `results/runs/i4f-status-consolidation-20261025T231009Z/previous-STATUS.md`; those historical jobs are not live.

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
