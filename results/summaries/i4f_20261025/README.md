# I4F discharge: published results, 25 October 2026

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

The new 1,779,258-cell CFD case completed **0.005021 s of startup** with a saved
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
