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

Small JSON/CSV results accompany the figures. [Publication manifest](publication-manifest.json)
records source paths and byte hashes. Raw native fields, full logs and restart
bundles remain local under ignored `results/runs/`; these files are selected
outputs, not a complete transferable CFD case.
