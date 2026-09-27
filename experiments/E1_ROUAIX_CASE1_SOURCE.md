# E1 source record: Rouaix et al. Reference Case 1

**Purpose:** source transcription and two-method Figure 13 digitization for the
single round-jet numerical benchmark. This is a provenance handoff, not an E1
run declaration, tolerance selection, validation result, or readiness decision.

## Source and page references

Clément Rouaix, Alexei Stoukov, Yannick Bury, David Joubert, and Dominique
Legendre (2023), “Liquid jet breakup in gaseous crossflow injected through a
large diameter nozzle,” *International Journal of Multiphase Flow* 163,
104419. [DOI](https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419),
[HAL author-manuscript record](https://hal.science/hal-04098260v1),
[HAL PDF](https://hal.science/hal-04098260v1/file/Rouaix_28516.pdf).
The external author manuscript has 22 PDF pages. The PDF cover is an additional
page: references below give PDF page first and printed article page second.
The manuscript was inspected externally and is not included in this repository.
The exact PDF used for the recorded digitizations has SHA-256
`624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446`; the raster
script checks this hash before tracing so a changed source file cannot silently
reuse the recorded calibration.

| Input or observable | Source location | Extracted information |
| --- | --- | --- |
| Coordinate frame and setup sketch | PDF p. 4 / article p. 3, Fig. 1 | One downward liquid jet, velocity in `-e_y`; uniform air crossflow in `+e_x`; `e_z` is spanwise. Gravity is in `-e_y`. Fig. 1 labels a Case 1 morphology at 4.5 s; that label does not set the sampling time of Fig. 13. |
| Fluid properties and study ranges | PDF p. 5 / article p. 4, Table 2 | Water: `rho_j=997.6 kg/m^3`, `mu_j=8.89e-4 Pa s`; air: `rho_g=1.18 kg/m^3`, `mu_g=1.86e-5 Pa s`; `sigma=0.072 N/m`, `g=9.81 m/s^2`, `p_g=101325 Pa`, `T=300 K`. Study ranges: `d_j=0.2–0.6 m`, `v_j=5–15 m/s`, `u_g=50–90 m/s`; `q=4.3–39`, `We_g=(1.6–5.29)e4`, `We_j=(1.39–12.5)e5`, `Re_g=(0.89–2.66)e6`, `Re_j=(2.24–6.73)e6`, `Oh_j=(1.35–2.34)e-4`, `Bo_j=(0.54–4.89)e4`, density ratio 846, viscosity ratio 48, and inlet liquid turbulence intensity `I_j=0.01–0.2`. |
| Exact reference row | PDF p. 5 / article p. 4, Table 3 | Case 1, legend `+` (green plus), mesh `Delta x=16 mm`, `I_j=0.01`, realizable `k-epsilon`, `d_j=40 cm`, `v_j=10 m/s`, `u_g=70 m/s`, `q=17.3`, `Re_j=4.9e6`, `Re_g=1.78e6`, `We_g=3.2e4`, `We_j=5.54e5`. These are the single-nozzle conditions. |
| Solver and interface definitions | PDF p. 6 / article p. 5, Section 3.1 | Unsteady, incompressible, three-dimensional finite-volume STAR-CCM+ calculation; VOF liquid volume fraction `chi`, continuum surface force surface tension, realizable `k-epsilon` RANS with two-layer wall treatment (the paper also tested SST `k-omega`). HRIC second-order interface scheme, second-order-upwind convection, first-order implicit time integration, `Delta t=1e-3 s`; reported CFL is 3.2–5.7. The paper uses `chi=0.9` for the liquid core, `chi=0.1` for the lower cloud envelope, and `chi=0.5` for the interface. |
| Geometry and boundary conditions | PDF p. 7 / article p. 6, Section 3.2 and Fig. 3 | Curved aircraft underside is a no-slip top wall. Top footprint is `50 d_j` streamwise by `17.5 d_j` spanwise; vertical height is about `25 d_j`, with a trapezoidal opening angle of 25 degrees; bottom footprint is `50 d_j` by `40 d_j`. Uniform crossflow enters `l=2.5 m` upstream of the nozzle center. A uniform liquid velocity is imposed at the nozzle exit. Other boundaries are outflow at atmospheric pressure. The paper says preliminary, unreported tests found no significant difference between the curved and a flat wall for jet evolution. |
| Mesh and run duration | PDF p. 8 / article p. 7, Section 3.3 | Unstructured polyhedral mesh with five prism layers and 1.1 growth ratio. Mesh sizes studied: 70, 50, 30, and 16 mm; Case 1 uses the 16 mm fine mesh. The calculation runs for about 5 s to reach stabilized penetration and transverse width. This is simulated time, not a stated finite release duration or payload. |
| Penetration and transverse width curves | PDF p. 13 / article p. 12, Fig. 13; definitions/fits at PDF p. 15 / article p. 14, Section 4.3, Eqs. (10)–(11) | Case 1 is the green `+` series; Case 12 is the darker-green right-point triangle. Axes are normalized by `d_j`: streamwise `x/d_j`, vertical penetration `y/d_j`, and transverse expansion `z/d_j`. The paper defines the cloud surface with `chi=0.1`. The accompanying fits are `y/d_j = 1.15 q^0.379 (x/d_j)^0.54` and `z/d_j = 2.1 q^0.171 (x/d_j)^0.49` for `z >= 0.25 d_j`; near the nozzle, Eq. (11) uses approximately `z=d_j` for `x/d_j<0.25`. These are reported multi-case fit relations, separate from the digitized points. |
| Breakup location | PDF p. 14 / article p. 13, Fig. 16; definitions/fits at PDF p. 15 / article p. 14, Section 4.4, Eqs. (12)–(13) | The breakup locations are time means of the streamwise and vertical positions of the `chi=0.9` liquid-core breakup. Fig. 16 plots generic `x_BU/d_j` circles and `y_BU/d_j` squares against `q`; it does not label a Case 1-specific marker or a time window. A vector-plot read near `q=17.3` is approximately `x_BU/d_j=8.91` and `y_BU/d_j=10.04`, each with about `0.25` normalized ordinate uncertainty from marker/trace width. This is only a `q`-level marker: Cases 1, 8, and 9 share `q=17.3`, so it cannot be uniquely attributed to Case 1 geometry. The separate paper fits are `x_BU/d_j=3.6 q^0.3` and `y_BU/d_j=3.4 q^0.4`; they are not substituted for the plotted marker. |

Table 2 gives a `v_j` study range through 15 m/s, while the Section 2.2 prose
describes a selected range through 10 m/s. Table 3 includes a Case 12 at 15
m/s. This transcription follows the tables for the ranges and Case 1, while
retaining the prose/table discrepancy rather than silently reconciling it.

## Source model versus aircraft context

Case 1 is a **single circular nozzle** with `d_j=0.4 m`, constant uniform
`v_j=10 m/s`, and `u_g=70 m/s`. Under the reported water density, the implied
area is `0.125664 m^2`, volumetric flow is `1.25664 m^3/s`, and mass flow is
about `1.254e3 kg/s`; these are calculated from the table values, not reported
payload measurements. The downward vector momentum-flux magnitude is about
`12.54 kN`, also derived. No finite release duration, total payload, valve
history, or transient outlet ramp for Case 1 is specified. A finite mass would
therefore require an independently declared duration and must not be described
as a paper input.

The paper separately discusses a B747 system with four nominal 0.4 m exits
(PDF p. 4 / article p. 3, Section 2.2). Its later B747 comparison (PDF p. 16 /
article p. 15, Section 4.5 and Fig. 17) mentions up to 70 m^3, delivery
pressure 7 bar, four holes in line, approximately 14 m/s exit speed, and
approximately 70 m/s aircraft speed relative to air; a certification drop is
described as 10 s with a pattern about 1 km long by 70 m wide. These are
separate aircraft-comparison statements, not the Case 1 boundary condition.
The outlet coordinates and spacing, per-port histories, and a resolved
four-outlet simulation are not supplied. Four nozzles or a four-slot source
must not be represented as Rouaix Case 1.

## Figure 13 digitizations, cross-check, and uncertainty

The primary vector-path digitization is in
[`data/derived/rouaix_e1_case1_fig13.csv`](../data/derived/rouaix_e1_case1_fig13.csv).
An independent raster centerline trace is in
[`data/derived/rouaix_e1_case1_fig13_raster.csv`](../data/derived/rouaix_e1_case1_fig13_raster.csv),
generated by [`scripts/digitize_rouaix_fig13_raster.py`](../scripts/digitize_rouaix_fig13_raster.py).
Both files are long-form: each row is one observable at its own `x/d_j`;
penetration and width samples are **not** asserted to be matched at identical
streamwise positions. Values are normalized by the reported Case 1 nozzle
diameter. The raster output retains the plotted `z/d_j` convention and makes
no half-width/full-width conversion.

Reproduce the independent raster trace by placing the cited HAL PDF in a
temporary location and running
`python scripts/digitize_rouaix_fig13_raster.py /tmp/Rouaix_28516.pdf`.
The script uses Poppler `pdftoppm` to render PDF page 13 at 600 dpi as a
temporary raw RGB PPM, then uses only the Python standard library to trace
pixels. It does not inspect PDF or SVG vector paths, and neither the PDF nor
the rendered image is written into the repository. The tested Poppler version
was 24.02.0; the expected page raster is 4961 by 6615 pixels. The independent
source is the cited 22-page HAL author manuscript (DOI
[10.1016/j.ijmultiphaseflow.2023.104419](https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419));
Fig. 13 is PDF p. 13 / article p. 12. Its caption labels panel (a) as
`y/d_j`, panel (b) as `z/d_j`, and both abscissae as `x/d_j`. The legend maps
the bright-green plus (`+`) to Case 1, `q=17.3`; Case 12 at `q=39` is the
darker-green right-point triangle. The raster method uses a bright-green RGB
distance mask (distance below 100 from `(0,255,0)`), which excludes the darker
Case 12 trace (about `(77,179,26)`).

The primary vector-path digitization uses Poppler `pdftocairo` and SVG paths.
Its inspected page has a 595.276 by 793.701 point SVG viewport. The digitizing
transformation accounts for the plotted path transforms (scale approximately
`+/-0.998785`). Its normalized axis calibration was:

- Penetration panel: SVG x ticks from `103.91062` to `278.638109` pt map to
  `x/d_j=0..8`; SVG y ticks from `200.121777` to `58.769696` pt map to
  `y/d_j=0..10` (SVG vertical coordinates increase downward).
- Width panel: SVG x ticks from `333.311613` to `508.019126` pt map to
  `x/d_j=0..2.5`; SVG y ticks from `200.177709` to `59.074325` pt map to
  `z/d_j=0..5`.

The independent raster axis calibration uses major tick centers measured in
the 600 dpi page raster:

- Penetration x pixels `866.5, 1231, 1595.5, 1959.5, 2324.5` map to
  `x/d_j=0, 2, 4, 6, 8`; y pixels `1666.5, 1430.5, 1194.5, 958.5, 723,
  487` map to `y/d_j=0, 2, 4, 6, 8, 10`.
- Width x pixels `2780.5, 3072, 3363.5, 3655, 3946.5, 4238.5` map to
  `x/d_j=0, 0.5, 1, 1.5, 2, 2.5`; y pixels `1666.5, 1431.5, 1196, 960.5,
  725, 489.5` map to `z/d_j=0, 1, 2, 3, 4, 5`.

For each primary-CSV x coordinate, the raster script takes local per-column
green-pixel medians and a Theil–Sen centerline estimate to reduce the effect
of plus-marker strokes. At the shared nozzle origin it records the axis origin,
because plotted symbols overlap there. At width `x/d_j=0.25`, overlapping
traces occlude part of the Case 1 pixels; the script uses a one-sided local
extrapolation and expands the raster bound to `0.082`. Raster samples are
rounded to 0.0001. This is a second extraction method at the primary CSV's
sampled x coordinates, not an independently selected x grid.

The primary CSV `sigma_*` fields are conservative **digitization bounds**, not
standard deviations, source error bars, or CFD acceptance tolerances. They
are `0.07` for penetration and `0.04` for width in normalized ordinate, and
`0.02` for penetration and `0.01` for width in normalized x. The raster CSV's
`sigma_raster_bound` is a separate heuristic extraction bound based on local
centerline residuals and, where needed, one-sided extrapolation; it is not a
statistical confidence interval. Compared at common x values, the raster and
primary curves have RMSE `0.019` for penetration and `0.028` for width. Their
maximum absolute differences are `0.051` at penetration `x/d_j=0.5` and
`0.088` at width `x/d_j=0.25` (the partly occluded point). No point falls
outside the sum of the primary ordinate bound, the local-slope-propagated
primary x bound, and the raster bound. The plotted curves provide no
statistical model uncertainty.

Section 4.3's equations are on PDF p. 15 / article p. 14, not PDF p. 14 /
article p. 13. At `q=17.3`, they predict `y/d_j = 3.388 (x/d_j)^0.54` and
`z/d_j = 3.419 (x/d_j)^0.49` using the printed rounded coefficients. These
are reported multi-case empirical fits, not pointwise acceptance criteria for
Case 1. Against the primary digitized nonzero points, the penetration-fit
residual RMSE is `0.552` (mean absolute residual `0.386`); the largest residual
is `-1.244` at `x/d_j=4.875` (digitized `6.725`, fit `7.969`). The transverse
fit residual RMSE is `0.693` (mean absolute residual `0.644`); at
`x/d_j=0.5`, the digitized value is `2.143` versus fit `2.435`; at `1.0`,
`3.092` versus `3.419`; and at `2.5`, `4.328` versus `5.357`, a difference
of `-1.029`. Those residuals exceed the point-digitization bounds downstream,
but those bounds describe trace extraction only. The equations are empirical
fits across cases, and the paper does not report their residual scatter or
coefficient uncertainty here. The residual is therefore a secondary
consistency check, not evidence of a source contradiction and not a
pointwise E1 acceptance target. The independent raster trace agrees with the
primary curve within the extraction bounds and shows the same slower
downstream rise relative to Eq. (11); this confirms the trace, not the expected
scatter of the fit.

The plot and Section 4.3 call the observable transverse expansion `z` and
plot `z/d_j`; the paper does not explicitly define it as a half-width or a
full width. It notes `z approximately d_j` for `x/d_j<0.25`. Preserve the
reported ordinate without a factor-of-two conversion. Fig. 13's caption does
not give a sample time or averaging interval. Section 3.3's roughly 5 s is
the run duration and Fig. 1's 4.5 s is a separate morphology illustration;
neither establishes Fig. 13's sampling time.

## Claim limits and next use

These data support a provisional source transcription and an approximate
curve comparison from two extraction methods only. The breakup plot provides
a `q=17.3` marker, not a Case-1-unique breakup location. The numerical case
uses RANS/VOF and the paper's specified single-nozzle geometry; it is not
measured full-scale aircraft performance. It says nothing by itself about
the four-outlet I4F
geometry, finite payload, ground deposition, useful-strip score, or field
validity. This record does not set CFD tolerances, prescribe a run budget, or
mark E1 ready. Freeze those only through the project review process after
source review and acceptance-criterion review.
