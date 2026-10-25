# I4F discharge: published results, 25 October 2026

[Watch the current air-filled compact startup, 10× slow](current-air-filled-cutaway-10x.mp4)
or its [outlet view](current-air-filled-outlet-10x.mp4). These show pipe filling
through **0.200021 s**, with downstream air still present and no resolved sheet
outside the mouths. Six saved states are held at their actual timing; the
3-second clip includes a 1-second endpoint hold and no field interpolation.
The [movie manifest](current-air-filled-movie-manifest.json) records the inputs.

![Current air-filled startup at 0.200021 s](current-air-filled-preview.png)

**Initial-state correction:** the user confirms that passages downstream of
the valves initially contain air. The older movies and liquid-full-line
comparisons here preserve the earlier primed-line assumption. They do not show
that confirmed startup. The new 269,680-cell air-filled compact baseline is
running. Its [native initial-state image](current-air-filled-initial-state.png)
shows 1.350 m3 in each tank, with another .25106/.25111 m3 in wetted upstream
feeds and air downstream of the assumed x=2.25 m valve planes. The image shows
initialization, not a discharge result. The rectangular mouths are at x=4.8 m.

The portable [moving-front model](air-filled-moving-front-model.json) and its
[timestep comparison](air-filled-moving-front-model-dt.json) predict first
mouth water near .612/.620 s, conditionally on a full-bore front. The
[thermal sensitivity](air-filled-model-thermal-sensitivity.json) advances those
times to .580/.587 s for isothermal gas and changes intake-crown timing by 14%.
These are one-tank/two-branch model results, not measured discharge or emptying.
The [native gas-state diagnostic](air-filled-gas-apparent-exponent.json) and
[data](air-filled-gas-apparent-exponent.csv) give an apparent expansion exponent
near 1.24 by .20 s, versus dry-air gamma near 1.40. This is an output diagnostic,
not a fitted input or a measured heat-transfer rate; energy closure remains open.
Run the model from the [frozen input packet](../../../experiments/i4f_filling_reference/inputs-manifest.json)
using `.venv/bin/python scripts/run_i4f_filling_network.py --max-time 1.3`.

The [CFD timestep comparison](air-filled-timestep-comparison.json) separates
common-time scalar interpolation from field snapshots at slightly different
times. The [initial-fill comparison](air-filled-initial-fill-comparison.json)
and [CSV](air-filled-initial-fill-comparison.csv) retain the different initial
water inventories. The [valve-source audit](air-filled-valve-zone-audit.json),
[plot](air-filled-valve-zone-audit.png) and
[inventory comparison](air-filled-valve-inventory-comparison.csv) identify an
early model/CFD mismatch: the distributed CFD resistance initially overlaps
water and air, while the reduced model applies a full liquid valve loss. A
separate source-placement trial is testing that mechanism without fitting Cd.
Its [first exact-time result](air-filled-valve-source-comparison.json) and
[CSV](air-filled-valve-source-comparison.csv) show 12.1% less tank drawdown at
.05 s with resistance wholly upstream of the initial front, preserving its
fully wet integral. This explains part of the model/CFD gap; later apparatus
sensitivity is still running. The [comparison through .200021 s](air-filled-source-history-comparison.json),
[data](air-filled-source-history-comparison.csv) and
[plot](air-filled-source-history-comparison.png) show a sign reversal:
thin-source tank-A withdrawal changes from .79 L less at .05 s to 3.08 L
more at .20 s. At .20 s its gas pressure is 11.85 kPa lower and its
alpha-water >= .5 front is about .15 m farther along the pipe. The original
source is already fully wetted by .15 s. Both fronts remain upstream of the
transition; this does not establish a corrected physical valve model.

The [direct resistance benchmark](valve-resistance-duct-results.json) and
[case table](valve-resistance-duct-cases.csv) isolate a numerical contribution:
for a .30 m scalar-resistance reach, reducing axial cell size from 25 to
6.25 mm lowers analytical steady-flow error from 6.34% to 1.38%. A .10 m
reach gives 27.66% and 5.02%, respectively. All four runs end normally with
native inlet/outlet flux closure; matching the integrated force alone does
not ensure the correct flow rate. This all-water, gravity-free slip duct tests
the scalar closure, not the real butterfly valve or apparatus. No fitted
discharge-coefficient correction is applied.

The [completed 12.5/6.25 mm apparatus comparison](air-filled-valve-band-axial-comparison.json)
and [native histories](air-filled-valve-band-axial-comparison.csv) retain a
strict **HOLD**: the first two timesteps exceed the 2% pointwise target.
Endpoint flow differs about 1.50%, and tank-A withdrawal is 4.66391 versus
4.59423 L, close to the reduced model's approximately 4.57 L. Both cases
ended normally at .050021 s without pressure-floor contacts. The longer
fine run is explicitly exploratory; this does not establish mesh independence
or hardware validation.

![Matched-time tank drawdown across source and axial-grid choices](air-filled-drawdown-source-grid.png)

The [figure data](air-filled-drawdown-source-grid.csv) and
[source record](air-filled-drawdown-source-grid.json) preserve actual endpoint
times and the bracket-interpolated model reference. The model's initial wet-feed
volume is .634% larger than the native CFD value.

The [opening follow-up](valve-resistance-opening-comparison.json) and
[table](valve-resistance-opening-comparison.csv) give analytical flow errors
of .645%, .0162% and .00414% at constant opening fractions .02, .5 and 1,
using 3.125 mm axial cells in a shorter duct. The minimum-opening transfer
changes both domain and resolution relative to the first benchmark. Smoothing
the coarse source lowers its error to 3.13%, missing the working 2% target.
The aggregate run hit its wall cap during the full-open arm; its saved fields
and native flux plateau support the reported comparison, not completion of
its original .25 s horizon. Declared versus executed output-interval differences
are preserved in the JSON.

The compact geometry generator now supports both
[horizontal](compact-horizontal-tank-geometry.png) and
[vertical](compact-vertical-tank-geometry.png) tank axes. Their
[horizontal connection section](compact-horizontal-tank-connections.png) and
[vertical connection section](compact-vertical-tank-connections.png) were
inspected. The records ([horizontal](compact-horizontal-tank-geometry.json),
[vertical](compact-vertical-tank-geometry.json)) state the provisional placement,
equal vessel capacities and branch-intersection checks. These are geometry
comparisons; no vertical-tank performance result is claimed.

[Watch the 3D tank cutaway video, 10× slower](tank-cutaway-10x.mp4).
[Alternate outlet-focused render, same computed sequence](outlet-reference-10x.mp4).

![Tank discharge preview](tank-cutaway-preview.png)

The video shows thirteen computed states through 0.560717 s of the older,
provisional **one-tank/two-outlet, 9 bar absolute water/air reference**. It is a
partial discharge, with a numerical-run seam disclosed in the image and
[movie manifest](cutaway-movie-manifest.json). It does not depict the new
two-tank apparatus or a complete emptying.

The updated apparatus has two tanks and four outlets. Its parameterized,
provisional reconstruction is shown below; original user CAD and photograph
remain unchanged under `docs/`.

![Updated two-tank apparatus](current-two-tank-geometry.png)

[Updated tank cutaway](current-tank-cutaway.png) ·
[User-reported hardware record](../../../experiments/i4f_hardware_notes_20261024.json)

An earlier 1,779,258-cell CFD case completed **0.005021 s of startup** with a saved
restart and no recorded pressure-floor contacts. This is not a useful discharge
interval or hardware validation. See [startup summary](current-startup-summary.json)
and [early model comparison](startup-model-comparison.png). Tank pressure
drawdown and inventory agree closely with the reduced model. The
[native control-volume audit](native-cv-endpoint-flux.json) independently recovers
about .08714 m3/s per tank from both water inventory loss and native face flux;
the sampled mouth plane reports about .068 m3/s. That distinct sampled-plane
gap remains unresolved and must not be hidden by adding downstream storage.
Both models use the same nominal valve-opening law and minimum
opening; the discrepancy is not evidence of a different prescribed aperture.

The later reservoir-boundary fine run completed **0.050021 s** normally, with
all native restart fields and no pressure clipping. The matched
[coarse/fine startup comparison](current-startup-grid-comparison.json),
[metrics](current-startup-grid-comparison.csv) and
[plot](current-startup-grid-comparison.png) show 403 Pa headspace-probe pressure
difference (0.034%) and 2.44% less tank drawdown on the fine mesh. Sampled
mouth-plane mean water fraction differs more: 0.944 fine versus 0.970 coarse.
Native headspace capacities differ by about 1%, and the coarse mesh retains two
quality failures; this is nominal-geometry startup sensitivity, not formal
convergence or evidence of later sheet accuracy.
The [native thermal comparison](current-startup-thermal-grid.json),
[metrics](current-startup-thermal-grid.csv) and
[plot](current-startup-thermal-grid.png) show that mixed cells carry 19.94% of
coarse tank-gas volume versus 12.69% fine at .05 s. Some difference is already
present in the initial interface representation (14.34% versus 11.37%).
Gas-mass-weighted shared temperatures differ by only .055 K, but probe
agreement alone does not establish the same interface partition or a separately
conservative gas-energy calculation.

The older [pressure-floor comparison](pressure-floor-comparison.png) found
nearly identical endpoint bulk outputs at 10/5 kPa floors, but the
[gas-field audit](older-case-gas-extrema.png) revealed approximately 1490 m/s
gas speed and a separate 652 K gas-temperature maximum near the ambient opening.
A matched pre-contact pair on that same older one-tank/two-outlet reference
compared its static ambient treatment with a 100 kPa absolute, 293.15 K
compressible reservoir on the three external patches. At the matched endpoint,
global maximum speed changed from 1162 to 67 m/s and global maximum temperature
from 495.5 to 293.3 K; the latter maximum is gas in the static arm and liquid in
the reservoir arm. Tank-zone pressure, sampled mouth flow and phase ledgers
remained close under the fixed original time-step schedule. A simple Courant
estimate suggests 22.35× time-step headroom for the reservoir condition, but
this is not measured runtime speedup. These are boundary-sensitivity results,
not validation of ambient coupling or the updated four-outlet hardware. See the
[pair evidence](ambient-reservoir-pair-r2-evidence.json),
[plot](ambient-reservoir-pair-r2.png), and matched
[boundary](ambient-reservoir-pair-r2-matched-boundary-history.csv) and
[bulk](ambient-reservoir-pair-r2-matched-bulk-history.csv) histories. Exact
tested patch-only dictionaries and provenance are in the
[reservoir BC verification folder](../../../experiments/openfoam/i4f/reservoir_bc_verification/tested-ambient-patches/manifest.json).

[Reduced-model scenarios](reduced-model-scenarios.png) cover declared headspace,
pressure and polytropic sensitivities. Their stop is a mean-level intake event,
not a five-second discharge or measured gas breakthrough.

An ongoing 303,108-cell four-outlet continuation has a saved native checkpoint
at 0.200021 s on its way toward 0.8 s; the mesh retains two configured
face-decomposition tetrahedron-quality failures, so results remain exploratory.
The [matched timestep comparison](current-timestep-comparison.json)
and [metrics](current-timestep-comparison.csv) cover only the first
0.05 s (0.25 versus 0.125 ms), not full convergence. The
[CFD/reduced-network plot](current-reduced-network-comparison.png),
[CSV](current-reduced-network-comparison.csv), and
[JSON](current-reduced-network-comparison.json) use complete mouth
profiles through 0.100021 s; native scalar histories continue to 0.167021 s.
All four mouths exceeded 5% gas area for three
samples from 0.060021 to 0.070021 s, but sampled signed gas flow was negative;
this does not identify gas delivered from the headspaces.

At 0.200021 s, the [native headspace EOS summary](current-headspace-state.json)
reports per tank about 1.03844 MPa volume-weighted gas pressure and 284.905 K
mass-weighted temperature; the local probe reads 1.038412 MPa and 281.357 K.
Pure-gas and mixed-cell temperatures average 282.475 K and 291.847 K,
respectively, showing the effect of spatial and phase weighting. The reported
pV/(gamma−1) change is storage only, not a global energy balance. See the
[headspace table](current-headspace-state.csv) and
[geometry comparison](current-geometry-validation.json). The portable
geometry generator and its fixed horizontal +X layout are documented in the
[geometry source README](../../../scripts/i4f_four_outlet_geometry/README.md).

The [shortened outlet layout comparison](shortened-outlet-layouts.png),
[geometry table](shortened-outlet-layouts.csv), and
[comparison metadata](shortened-outlet-layouts.json) show the provisional CAD
layout now generated by default: no added post-rise straight and a 1.0 m
transition-and-mouth train. The 0.8 m train is a shorter sensitivity; the older
0.2 m straight plus 1.8 m train remains the explicit reference. These are
geometry-only alternatives. All simulated fields and movies above still use
the older layout, and no CFD has been run for either shortened layout. The exact
BREP downstream line volume is 0.88054/0.68645/0.64498 m³ per tank (two
branches) for the reference/1.0 m/0.8 m layouts. If all four branches are
primed, the 1.0 m layout reduces potential line-water inventory by 388.19 L
total across both tanks versus the reference. Full priming remains unconfirmed;
line inventory is separate from tank water.

The native 0.200021 s [true-grid diagnostic cutaway](current-fourmouth-cutaway.png)
and [outlet detail](current-fourmouth-outlet-detail.png) show whole-cell
alpha.water ≥ 0.5 bulk with an interpolated alpha.water = 0.5 display contour;
the visible blockiness reflects the mesh cells. The external native-water
cell-centre extent reaches x ≈ 5.96 m, inside the 7.8 m domain end. These are
diagnostic snapshots; [render metadata](current-fourmouth-render-metadata.json)
records their field mapping and display thresholds.

The current long-geometry prefix is also available as a [10× full cutaway
video](current-fourmouth-cutaway-10x.mp4) and [10× outlet-focused
video](current-fourmouth-outlet-10x.mp4). Both use the long-outlet reference
geometry from the native CFD case, with an ordinary same-model restart; they
do not use the newer short-outlet candidate. The sparse saved states span
0–0.349936 s, followed by a 1 s endpoint hold at 24 fps. This is a
quality-limited partial-discharge prefix, not a completed discharge or
validation result. The rendering adds no foam or synthetic droplets and does
not interpolate fields between saved physical times. See the [movie manifest](current-fourmouth-movie-manifest.json)
for source hashes and display details.

Small JSON/CSV results accompany the figures. [Publication manifest](publication-manifest.json)
records source paths and byte hashes. Raw native fields, full logs and restart
bundles remain local under ignored `results/runs/`; these files are selected
outputs, not a complete transferable CFD case.
