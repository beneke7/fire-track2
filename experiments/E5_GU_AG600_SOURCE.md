# Gu et al. AG600 ground-fraction source extraction

**Scope:** source transcription and method notes for E5 preparation. This record
does not set a project tolerance, reconstruct a ground map, or report a project
simulation or validation result.

## Source and locations

The source is Y. Gu, R. Zhou, H. Xie, and L. Shi (2023), “Study on the ground
fraction of air tankers,” *International Journal of Wildland Fire* 32(4),
576–592, [doi:10.1071/WF22055](https://doi.org/10.1071/WF22055), from the local
17-page file [`Study on the ground fraction of air tankers.pdf`](../Study%20on%20the%20ground%20fraction%20of%20air%20tankers.pdf).
The extracted source PDF SHA-256 is
`db8ad912aa33ee402906100ffa5e040b67064b150308c69057a2e4eaa67bcf46`.

All table values in [`gu_ag600_table4_table5.csv`](../data/derived/gu_ag600_table4_table5.csv)
retain the source's printed decimal precision and all six groups:

| Source | Locator | Extracted fields |
| --- | --- | --- |
| Table 4, “Drop water test parameters of an AG600 amphibious firefighting aircraft” | PDF p. 8; journal p. 583 | Group, aircraft type, relative velocity `U` (m/s), height `H` (m), dropped volume `Q` (m³), average flow rate `q` (m³/s), liquid density `ρL` (kg/m³), liquid viscosity `μL` (cP), wind speed `W` (m/s), and wind direction `α` (°). |
| Table 5, comparison of measured and post-processing ground fraction | PDF p. 9; journal p. 584 | Measured ground fraction (%), post-processing estimate (%), reported bias (%), and reported relative bias (%). |

The paper's abstract defines ground fraction as liquid collected on the ground
divided by dropped liquid (PDF p. 1; journal p. 576). The paper defines
`U = Ug − W cos α`, the aircraft velocity relative to air, with `Ug` the
aircraft velocity relative to ground and `α` the wind direction relative to
flight direction (PDF p. 2; journal p. 577). Thus the CSV's `velocity_U_m_s`
preserves the source variable; it is not relabeled as ground speed.

## Six source rows

The CSV is the row-preserving transcription. Table 4 gives the six AG600 water
conditions; Table 5 gives two distinct ground-fraction columns for the same
groups. The first fraction is the paper's drop-test measurement. The second is
the paper's estimate calculated with its post-processing method. The Table 5
bias fields are retained as reported and are not substituted for either
fraction.

## Collection convention and calculation described by the paper

The source says the cup-and-grid method places cups along the flight direction,
weighs the collected liquid, and uses those data to draw a ground-contour
distribution (PDF p. 2; journal p. 577). It identifies the AG600 water test as
a gravity-system drop conducted in Jingmen, Hubei, on 12 April 2022. For this
test, it describes a grassy area of 300 × 100 m (length × width), with
“cup + stake” devices at 5 m intervals in both the along-flight and
cross-flight directions. It reports six effective non-uniform two-dimensional
data sets. A small amount landed outside the test site; the authors linearly
interpolated that portion of the pattern (PDF p. 3; journal p. 578; Figs. 2
and 4).

For the post-processing estimate, the paper divides the non-uniform ground
distribution into `N` along-track segments of selected length `Δx`, treating
each segment as approximately uniform in `x`. It fits a cross-track Gaussian
liquid distribution at each segment. With exactly three original points at a
segment, it says to solve for the peak, center, and standard deviation
directly; otherwise it fits those parameters and requires `R² > 0.8`. It
integrates the fitted profile over `y0 ± 3σ` (a total width of `6σ`), sums
segment volume contributions to estimate collected volume `V`, then computes
`φ = V/Q × 100%`, where `Q` is the dropped volume (PDF p. 7, journal p. 582,
Eqs. 3–5; the calculation and definition of `Q` continue on PDF p. 8, journal
p. 583). Table 4 reports `Q = 6 m³` and `q = 2.84 m³/s` for all six groups.
The accompanying text says the reported `q` is an average formed from advance
full-scale tank-drop experiments and then averaged across the experimental
groups; it is not a published time-resolved release trace (PDF p. 3, journal
p. 578).

## Independent arithmetic check and interpretation

Using the two Table 5 fraction columns as printed, `post-processing estimate −
measured fraction` gives `4.01, 2.18, 3.60, 1.56, 3.68, 2.99` percentage points.
Dividing each difference by that row's measured fraction and multiplying by
100 gives `9.50, 5.04, 8.71, 3.67, 8.31, 7.11%` after rounding to two decimal
places. All six relative-bias values agree with the source at its displayed
precision.

The source describes its computed values as being in good agreement, reports a
maximum bias of 4.01% and a relative bias of 9.50%, and cites a USDA Forest
Service 10% percentage-error quality requirement (PDF p. 8; journal p. 583;
Table 5 is on the following page). That is the paper's statement about its
method and data. It does not establish a project E5 tolerance or a project
pass/fail result. The project plan and validation contract keep this E5 source
comparison distinct from project `f_useful`.

In the project plan, `f_useful` credits only threshold-satisfying cells inside
the longest valid strip, caps credited dose at the required threshold, and
normalizes by released mass. Gu et al.'s collected ground fraction is an
aggregate fraction of liquid collected on the ground. It does not encode the
project's threshold, width, strip continuity, dose cap, or outside-map
accounting and must not be used as a substitute for `f_useful`.

## Limits and open inputs

- The supplied paper gives the Table 5 aggregates and figures, but not the raw
  cup-by-cup masses and coordinates needed to independently rebuild each
  measured distribution or recompute its measured ground fraction.
- The reported small out-of-site portion is completed by linear interpolation;
  its raw amount and boundary observations are not tabulated. This makes the
  reconstructed collection total dependent on the paper's interpolation.
- The paper does not provide the selected `Δx`, the segment-level fitted
  parameters, or the underlying precision used for Table 5. Its `R² > 0.8`
  fit condition and `6σ` integration support a method description, not a
  reproducible row-level reconstruction from the supplied file alone.
- Table 4 supplies summary conditions, including one average `q` for every
  group. The supplied source does not provide the exact release history or
  per-run metered release record needed to construct a matching transient
  source independently.
- The source's 300 × 100 m area, 5 m grid spacing, and outside-site treatment
  define its collection context. They do not by themselves define the
  project's ground-map domain, registration, or scoring strip.

Before any E5 reconstruction or decision, reviewers still need to determine
whether the project can match the reported release and collection conditions,
what source data or registration are available, and whether any comparison
limit is justified and accepted for this use. This extraction makes no such
choice.
