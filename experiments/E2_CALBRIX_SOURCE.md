# E2 source record: Calbrix et al. Dash-8 water case

**Purpose:** transcribe the published Dash-8 nearfield numerical reference for
E2 and preserve figure-derived source history and timing ambiguities. This is
a source handoff, not an E2 run declaration, tolerance selection, or validation
decision.

## Source and page convention

Corentin Calbrix, Alexei Stoukov, Axelle Cadiere, Benoit Roig, and Dominique
Legendre (2023), “Numerical simulation of aerial liquid drops of Canadair
CL-415 and Dash-8 airtankers,” *International Journal of Wildland Fire*
32(11), 1515–1528. [DOI](https://doi.org/10.1071/WF22147). The supplied local
PDF is 14 pages. Page locators below give physical PDF page first and printed
journal page second (PDF p. 1 is journal p. 1515).
The source PDF's SHA-256 is
`128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4`.

## Dash-8 case inputs

The E2 nearfield comparison is the paper's first set of **water** simulations,
not the later Fire-Trol 931 retardant/field comparison.

| Input or result | Evidence class | Source location and value |
| --- | --- | --- |
| Liquid | **Reported** | PDF p. 4 / journal p. 1518, Domains and meshes: water `rho_L=1000 kg/m^3`, `mu_L=0.001 Pa s`. |
| Air speed and frame | **Reported** | PDF p. 4 / journal p. 1518, Domains and meshes: `U_G=50 m/s` for the first water-simulation set, for both CL-415 and Dash-8. It is stated to correspond approximately to the aircraft's operating ground speed in the absence of wind. The atomization calculations are in the aircraft-moving frame; `U_G` is imposed at the domain inlet. It is not the separate 65–70 m/s normal-air-speed background range for Dash-8 in the introduction (PDF p. 2 / journal p. 1516). |
| Dash-8 tank exit | **Reported, incompletely specified** | PDF p. 3 / journal p. 1517, Tank geometry: the discharge calculation uses “full load” mode, with the maximum exit section imposed throughout the drop. The mean exit velocity is defined as `U_L=Q_L/S`. PDF p. 5 / journal p. 1519, Fig. 3(b): one exit at the bottom of the Dash-8 tank is shown in red. Numeric exit area `S`, the exact open-patch shape, and a spatial profile table are not stated in the prose. |
| Exit-velocity history | **Reported and digitized** | PDF p. 5 / journal p. 1519, Fig. 4 and adjacent Results text: the legend identifies the blue Dash-8 curve and the text says its peak is approximately `4.8 m/s` at `0.5 s`, with complete tank discharge in approximately `4 s`. A primary centerline read and a separately implemented second raster read, using the same documented axis calibration, are in [`data/derived/calbrix_dash8_fig4_velocity.csv`](../data/derived/calbrix_dash8_fig4_velocity.csv) and [`data/derived/calbrix_dash8_fig4_velocity_independent.csv`](../data/derived/calbrix_dash8_fig4_velocity_independent.csv). The prose elsewhere incorrectly calls a CL-415 top-exit trace blue; use the Fig. 4 legend to select Dash-8. Both are approximate figure reads, not raw flow data. |
| Flow and payload | **Reported gap** | PDF p. 3 / journal p. 1517, Tank geometry: the Dash-8/CL-415 flow-rate measurements are confidential. The paper provides no exact `Q_L(t)`, total released mass, or measured payload for the E2 nearfield water case. The generic aircraft maximum tank capacity of 10,000 L (PDF p. 2 / journal p. 1516) is not the simulated E2 release mass. |
| Later drop-volume cross-check | **Reported for retardant; water linkage incomplete** | PDF p. 11 / journal p. 1525, Table 5: Dash-8 drop volume is `8.840 m³` for the Fire-Trol 931 field-drop conditions (`rho=1100 kg/m³`, `mu=0.056 Pa s`). The adjacent paragraph says those volumes were used in tank-discharge simulations to determine inlet conditions. This is relevant to the profile setup, but the article does not explicitly identify it as the first water set's initial payload or give a water fill depth. |
| Dimensionless case values | **Reported** | PDF p. 8 / journal p. 1522, Table 2: Dash-8 `We_G=23,643`, momentum ratio `q=7.90`, penetration prefactor `K_P=K q^alpha=3.0`, exponent `beta=1.36`. PDF p. 9 / journal p. 1523, Table 3: `We_G=23,643`, `q=7.90`, lateral-expansion prefactor `K_L=K' q^alpha'=0.07`, exponent `beta'=2.0`. Both tables describe the maximum ejection velocity at `t=0.5 s`. |
| Air properties, surface tension, gravity magnitude | **Not fully reported** | PDF p. 3 / journal p. 1517, Eqs. (1)–(3): air density `rho_G`, air viscosity `mu_G`, and gravity `g` occur symbolically. No numeric values for those properties or `sigma` are stated for this case in the methods/results. The authors omit the surface-tension term from Eq. (3), explaining that the resolution is larger than a capillary length of about 3 mm. Do not silently supply values from another paper or default conditions. |

The liquid-outlet velocity comes from a prior tank-discharge computation, then
is imposed at the red exit boundary in the external-air calculation (PDF p. 4 /
journal p. 1518, Domains and meshes). The source says a **velocity profile** is
transferred; it does not publish the pointwise outlet profile, exact flux
history, numerical boundary file, or a reconstruction rule. A constant uniform
`4.8 m/s` inlet is therefore a **project idealization** of the reported peak,
not the published time-dependent source and not an exact replication. A
time-dependent replay based on Fig. 4 must be labeled as digitized.

There is also a naming ambiguity: the Tank geometry subsection defines `U_L`
as the **mean** exit velocity `Q_L/S`, while Fig. 4's caption and Results text
call the plotted `U_L(t)` a **maximum** exit velocity. The paper does not
reconcile these labels. The digitized scalar trace must not be treated as a
fully specified pointwise inlet profile. The digitized values are `4.693 m/s`
at `0.4 s` and `4.677 m/s` at `0.5 s`; the latter differs from the text's
approximate `4.8 m/s` by slightly more than its listed `0.10 m/s` ordinate
read bound. Treat these as an approximate source-text discrepancy, not as
agreement within the listed digitization bound.

Under the provisional area-mean interpretation, the digitized 0–5 s history
integrates to 11.953 m. The inferred 1.332 m² aperture therefore releases
15.921396 m³, exceeding both the nominal 10 m³ capacity and the later
8.840 m³ drop-volume cross-check; the conditional 0.333 m² sensitivity
releases 3.980349 m³. Neither is a paper-specified water payload. This
unresolved consistency issue reinforces the need to distinguish prescribed
velocity, actual water flux and tank inventory; matching `q` alone does not
resolve the outlet area or mean-versus-maximum velocity interpretation.

## Geometry, coordinates, boundaries, and numerics

| Item | Evidence class | Source location and value |
| --- | --- | --- |
| Tank geometry | **Reported drawing dimensions; outlet interpretation incomplete** | PDF p. 4 / journal p. 1518, Fig. 2(b–c): Dash-8 tank front/side views label a 2 m overall front width, 1.7 m internal width, 1.5 m height, a 0.3 m lower opening-region dimension, and a 0.1 m bottom feature; side view labels 7.46 m overall length and 4.44 m lower-section length. The drawing does not state a numerical open exit area or explain in text how these labels define `S`; do not calculate `S` from them without resolving the drawing geometry. |
| Opening-axis alignment | **Figure-read support; exact aperture remains unknown** | PDF p. 5 / journal p. 1519, Fig. 3(b): the single red narrow exit follows the fuselage longitudinal axis and air-flow direction. PDF p. 4 / journal p. 1518, Fig. 2(b-c) places the 4.44 m lower-section span in side view and the 0.3 m bottom feature in front view; Figs. 6 and 8 confirm streamwise/transverse axes. An independent image review and root inspection support a streamwise long axis, without establishing numerical aperture edges or area. A 90-degree rotation would be a source-disfavored sensitivity. |
| Nearfield domain | **Reported drawing dimensions** | PDF p. 5 / journal p. 1519, Fig. 3(b): domain under the Dash-8 belly is labeled 26 m long, 20 m wide, and 31 m high. These are figure dimensions; the paper does not tabulate coordinate bounds or exact outlet-to-boundary distances. |
| Aircraft geometry and walls | **Body inclusion reported; wall condition unspecified** | PDF p. 4 / journal p. 1518, Domains and meshes, and PDF p. 5 / journal p. 1519, Fig. 3: the aircraft belly is meshed in the adapted external domain. Our flat slip roof omits that geometry. The paper's wall-cell sizes do not specify a slip/no-slip or wall-function treatment. |
| Frame and axes | **Reported/figure-read** | PDF p. 4 / journal p. 1518: calculation is in a frame moving with the aircraft. PDF p. 7 / journal p. 1521, Fig. 6, shows `y` along the streamwise/downstream direction and `z` vertically downward from the exit; the airflow arrow points along `+y`. PDF p. 9 / journal p. 1523, Fig. 8(a), is a front view with `x` transverse and `z` downward. Text on PDF p. 8 / journal p. 1522 describes velocity components `v_Z`, `v_Y`, `v_X` as vertical, streamwise, and transverse. A formal right-handed basis and signed gravity vector are not stated; the axis signs above are figure-based conventions, not a published vector specification. |
| Boundaries | **Reported in part; conditions missing** | PDF p. 4 / journal p. 1518, Domains and meshes: aircraft belly is meshed in an adapted external domain; the velocity profile from tank discharge is applied at the tank-exit inlet; relative air speed `U_G` is imposed at the domain inlet. The article does not specify outlet/top/side pressure or velocity conditions, wall-slip condition, initial field, or detailed inlet turbulence values. |
| VOF and equations | **Reported** | PDF p. 3 / journal p. 1517, Numerical method, Eqs. (1)–(3): unsteady 3D incompressible, immiscible Newtonian fluids; VOF fraction `alpha_L` obeys `d(alpha_L)/dt + div(alpha_L v)=0`; `div(v)=0`; one-fluid density `rho=alpha_L rho_L+(1-alpha_L)rho_G` and viscosity `mu=alpha_L mu_L+(1-alpha_L)mu_G`; momentum includes pressure, viscous stress, and gravity. Surface tension is omitted as noted above. STAR-CCM+ and standard `k-epsilon` RANS turbulence are reported. |
| Liquid observables | **Reported definitions** | PDF p. 6 / journal p. 1520: liquid core is `alpha_L >= 0.9`; cloud envelope is `alpha_L >= 0.001`. PDF p. 7 / journal p. 1521, Fig. 6: penetration `Z` is the front of the `alpha_L=0.001` surface as a function of streamwise `y`; plotted for Dash-8 and CL-415 at `t=0.5 s`. PDF p. 9 / journal p. 1523, Fig. 8: lateral expansion `L` is described as maximum width of the dispersed liquid. |
| Mesh and compute | **Reported; exact benchmark mesh mapping incomplete** | PDF p. 3 / journal p. 1517, Methods: at least two mesh resolutions were considered for each case, but the paper does not identify which exact mesh produced each comparison curve. PDF p. 5 / journal p. 1519, Fig. 3(b): the nearfield domain under the Dash-8 is labeled 26 m long, 20 m wide, and 31 m high; the adjacent results text reports a polyhedral mesh with cell sizes from `8e-2 m` in the center to `8e-6 m` at walls and about 8.7 million Dash-8 cells. PDF p. 11 / journal p. 1525, Concluding discussion, separately states that the “domain of study” extends up to 10 m under the airtanker with spatial resolution `0.04 m`. The article does not reconcile that conclusion statement with the Fig. 3 domain and nearfield mesh description or map it to a particular plotted comparison; do not conflate the two scales or claim the 40 mm resolution reproduces a specific figure. PDF p. 3 / journal p. 1517 also reports a separate Dash-8 tank-discharge mesh with about 1.9 million cells, sizes `2e-2 m` at the center to `5e-6 m` at walls. The Dash-8 parallel run used 720 processors and 28,800 CPU-hours. |
| Data availability | **Reported access route; source arrays absent locally** | PDF p. 14 / journal p. 1528 states that the data used to generate the paper results are available by contacting the corresponding author. The supplied PDF has no embedded files, and no supplementary files or originating arrays were found in the local project tree; the local Dash-8 CSV/JSON inputs are documented project figure digitizations. No author contact was made. |

The paper does not state a time step, CFL limit, temporal or spatial discretization
schemes, full turbulence boundary values, exact external boundary conditions,
or the mapping of the spatially varying tank-exit velocity onto the air-domain
inlet. Those gaps prevent a bit-for-bit reconstruction from the article alone.

## Correlations and figure timing

The paper defines the momentum ratio and characteristic length in PDF p. 7 /
journal p. 1521:

- `q = rho_L U_L^2 / (rho_G U_G^2)` compares liquid-exit and crossflow inertia.
- `L_c = sqrt(S)`, where `S` is the tank exit area (the numeric `S` is not
  reported).
- Penetration Eq. (4): `Z/L_c = K q^alpha (y/L_c)^beta`. For Dash-8 at
  maximum ejection velocity, Table 2 reports `K_P=K q^alpha=3.0` and
  `beta=1.36`; Fig. 7 compares the `t=0.5 s` simulated curve with this fit.
- Air Weber number Eq. (5): `We_G = rho_G U_G^2 L_c / sigma`.
- Lateral expansion Eq. (6), PDF p. 8 / journal p. 1522:
  `L/L_c = K' q^alpha' (z/L_c)^beta'`. At `t=0.5 s`, Table 3 reports
  `K_L=K' q^alpha'=0.07` and `beta'=2.0` for Dash-8.

A conditional area cross-check uses the reported `We_G=23,643` and
`S=(We_G sigma / (rho_G U_G^2))^2`. With **assumed reference properties**
`rho_G=1.15–1.25 kg/m³` and water `sigma=0.070–0.074 N/m`, and reported
`U_G=50 m/s`, this gives `S=0.28048–0.37033 m²`. The current inferred
`S=1.332 m²` instead gives `We_G=44,839–51,523` under those assumptions.
Root requested an independent check; both source extraction and scientific
review confirmed the equation and arithmetic in the local PDF. This is a
conditional consistency warning, **not a recovered numerical aperture**.
Surface tension supplies the dimensionless reference scale here even though
the authors omit its force from their momentum equation. The reported `q`
does not constrain area. A `2.22 × 0.15 m` opening (`S=0.333 m²`) preserves
the current candidate's aspect ratio and is a useful provisional sensitivity;
those individual dimensions are not drawing measurements. At unchanged
digitized mean speed, its flow and release mass are one quarter of baseline,
and its width spans only two baseline cells, requiring resolution sensitivity.

There is an explicit timing conflict for dimensional lateral expansion. Section
“Liquid lateral expansion” says **Fig. 8 is compared at `t=0.5 s`** (PDF p. 7 /
journal p. 1521, text). Fig. 8's own caption says both its Dash-8
`alpha_L=0.001` front view and the Dash-8/CL-415 comparison are at **`t=1 s`**
(PDF p. 9 / journal p. 1523). Fig. 9 is a separate normalized `L/L_c` vs
`z/L_c` time series showing Dash-8 curves at `t=0.5, 1.0, 1.5 s` (same PDF
page); the `t=1 s` Fig. 9 curve does not resolve the Fig. 8 conflict. Do not
choose one Fig. 8 time by inference. Record whichever source observable and
time is selected before a future comparison.

Fig. 9's caption also says its dashed lateral-expansion fit is “Eqn 5,” while
the lateral-expansion relation is defined as Eq. (6) in the body and Fig. 9
caption gives the Eq. (6) coefficients. This appears to be an internal equation
number inconsistency; preserve the source's wording in any audit rather than
quietly rewriting the citation.

Figure 5 (PDF p. 6 / journal p. 1520) provides qualitative Dash-8 water
snapshots at `t=0.1, 1, 4.8 s` with `alpha_L=0.001` cloud envelope and
`alpha_L=0.9` core. It is morphology context, not an outlet-history table.

## Dash-8 structure counts and velocity classes

Figure 11 (PDF p. 10 / journal p. 1524) assigns CL-415 to panels (a,b) and
**Dash-8 to panels (c,d)**. Panel (c) plots the count history for
`0.001 <= alpha_L <= 1` (red cloud) and `0.9 <= alpha_L <= 1` (blue core).
These are figure-read targets, not tabulated raw counts. The earlier project
statement that all Figure 11 counts were CL-415-only was incorrect; root and
an independent worker rechecked the local PDF caption on 2026-10-04.

The reproducible extraction is
[`scripts/digitize_calbrix_dash8_breakup.py`](../scripts/digitize_calbrix_dash8_breakup.py);
its count bins, native pixel trace and calibration metadata are linked in
[`E2_DASH8_BREAKUP_EXPLORATORY.json`](E2_DASH8_BREAKUP_EXPLORATORY.json).
An independent 600 dpi read checked the axes. The corrected 300 dpi zero-axis
stroke center is y=2651 px; the earlier top-edge read is preserved in its
original ignored bundle. At approximately 1 s, the cloud read is 266.583
structures and core read 14.000, with heuristic +/-5 count and +/-0.01 s
raster-read allowances. These are not author error bars. Near-zero unresolved
reads and gaps remain explicit; missing values are not fabricated.

Panel (d) reports Dash-8 velocity classes at `t=1 s`, detected with the dilute
cloud threshold, for equivalent diameters `0.04–0.1`, `0.1–1`, and `1–10 m`.
The printed component values, read from the labeled bars, are respectively:
`v_x = (0.07, -0.02, -0.16) m/s`,
`v_y = (25.95, 41.57, 18.7) m/s`, and
`v_z = (1.07, -2.26, -5.13) m/s`.
These use the paper's transverse x, streamwise y and vertical z components;
keep the established signed mesh-to-paper transform explicit when comparing.

The body (PDF p. 8 / journal p. 1522) describes MATLAB reconstruction of
three-dimensional liquid structures but leaves connectivity, filtering,
equivalent-diameter calculation and velocity averaging unspecified. Our
face-connected native-cell counts, alpha-volume equivalent diameter and
liquid-mass-weighted velocities therefore require detector sensitivity and
cannot be asserted equivalent to the paper merely because counts agree.

## Figure 4 history digitization

The first-pass digitized blue Dash-8 series is in
[`data/derived/calbrix_dash8_fig4_velocity.csv`](../data/derived/calbrix_dash8_fig4_velocity.csv).
Columns give `time_s`, `u_l_m_s`, and separate conservative
`figure_read_bound_*` bounds in time and velocity. Values are samples from the plotted line at 0.1 s increments; they are
not source-provided raw measurements, a probability distribution, or a source
error bar. The data preserve the visible short spike near 2.3 s and the
low-velocity tail rather than smoothing them.

Reproduction: the supplied local PDF is 14 pages. With Poppler `pdftocairo`
24.02.0, render its PDF page 5 as SVG using `pdftocairo -f 5 -l 5 -svg
<pdf> <temporary-prefix>`. This page contains an embedded JPEG image element
`source-5`, 1464 by 1157 pixels. Extract its `data:image/jpeg;base64` payload
to a temporary image; do not add the PDF or extracted image to the repository.
The time-series plot uses the blue Dash-8 curve identified by the figure
legend; the adjacent prose's color naming is inconsistent. A raster color mask
isolates the blue trace. The legend stroke overlaps the plotted series from
about `2.6–3.1 s`; there, select the lower continuous time-series branch by its
graph position rather than the legend sample. The isolated trace is sampled
at the nearest pixel column to each 0.1 s time coordinate, using the visible
centerline. The origin is set to the plotted axes intersection.

The axis calibration is `t=0..5 s` across image x approximately 9..1459 px and
`U_L=0..6 m/s` from image y approximately 1148..7 px (image y increases
downward). Conversion used `t=5(x-9)/(1459-9)` and
`U_L=6(1148-y)/(1148-7)`. Raster line thickness and axis-pixel placement bound
most ordinate reads to approximately `±0.10 m/s` and horizontal placement to
`±0.03 s`; the initial acceleration and sharp decline around `t=3.8–4.2 s`
are assigned wider `±0.15–0.20 m/s` ordinate-read bounds. These are separate,
correlated figure-read bounds, not independent statistical errors: on the
initial rise, a `±0.03 s` horizontal shift can change the ordinate by roughly
`0.7 m/s` using the local plotted slope. Quantitative time-history comparisons
must propagate the horizontal bound through the local slope or compare with
time uncertainty explicitly. The figure’s curve and the text’s
“approximately 4 s” full-discharge statement differ in the low-flow tail; keep
that source-level imprecision visible.

The separately implemented second raster read, using the same stated axis
calibration, is in
[`data/derived/calbrix_dash8_fig4_velocity_independent.csv`](../data/derived/calbrix_dash8_fig4_velocity_independent.csv),
generated by
[`scripts/digitize_calbrix_dash8_fig4_velocity_independent.py`](../scripts/digitize_calbrix_dash8_fig4_velocity_independent.py).
It renders the embedded 1464 by 1157 source JPEG through Poppler at native size,
applies a blue RGB-dominance mask, and samples the median blue-pixel center at
the nearest column every 0.1 s. In the 2.6–3.1 s legend overlap it selects the
lower continuous branch of the time series. At all 51 nominal times, the two
reads differ by mean signed `−0.000255 m/s`, mean absolute `0.00367 m/s`, and
maximum `0.032 m/s`; every same-time difference is inside the sum of the
declared ordinate-read allowances. This is an ordinate-only same-time check;
it does not propagate the correlated `±0.03 s` timing allowance, which can
change the initial-rise value by roughly `0.7 m/s`. It establishes trace-read
reproducibility only, not inlet-history accuracy or an E2 gate. The independent
CSV SHA-256 is
`fd4791bf79e39e2dbd3261af59c96b13d731b2a0a6ce4fe5450092aa2c1d7f0b`; the
generator SHA-256 is
`bdd7ba6294f495cf3345791d2ef1d339db169537da2d557257a8ba044c1ea6c6`.

## Evidence classes and limits

- **Reported:** water properties, relative air speed, dimensionless values,
  methods, and figure/table statements above.
- **Digitized:** primary and second reads of the Figure 4 blue velocity curve
  (sharing the stated axis calibration), and first and independent reads of the
  four `alpha_L=0.001`
  cloud-envelope curves recorded below; all are figure reads with stated
  bounds, not source-provided arrays. Figure 4's horizontal bound must be
  propagated through the local slope for time-history comparisons.
- **Inferred:** the coordinate directions read from Figs. 3, 6, and 8; they
  are figure-based because the article does not give a full signed basis.
- **Assumed for a controlled E2 run:** constant uniform `U_L=4.8 m/s` if the
  plan's fixed-source comparison is used. The reported peak is a measured-from-
  figure/model value, but constant speed over a chosen interval is not the
  paper's discharge history.

The article does not provide the Dash-8 `Q_L(t)` measurements, exit area `S`,
integrated payload for the plotted water case, exact time-varying inlet
profile, or full boundary/mesh/time-step files. Figure 8's time is conflicted.
This source record does not set E2 tolerances, pick a conflict resolution,
authorize CFD, or declare E2 ready. Nearfield agreement would be a numerical
benchmark comparison only; the paper itself says its resolved domain is not
the full path to ground deposition.

An independent source audit on 2026-09-25 approved the first-pass digitization
with revisions. The review checked representative pixel-center samples and
confirmed the blue trace against the figure legend. This record now identifies
the legend overlap, the approximate 4.8 m/s text-versus-digitization difference,
and the correlated horizontal/vertical figure-read bounds. It does not declare
the digitized history an exact inlet boundary condition or an E2 pass.

## Figures 6–9 cloud-envelope digitization

The primary raster centerline traces of the Dash-8 `alpha_L=0.001` envelope in
Figs. 6–9 are in
[`data/derived/calbrix_dash8_cloud_curves.csv`](../data/derived/calbrix_dash8_cloud_curves.csv),
generated by
[`scripts/digitize_calbrix_dash8_cloud_curves.py`](../scripts/digitize_calbrix_dash8_cloud_curves.py).
The input PDF is the exact local file named above, SHA-256
`128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4`; this
4,965-row CSV's SHA-256 is
`308c23d755828027acb54e9e9181f74142f831ad6649a1fc91f0a482023a5969`. The
current script hash is
`0442a2fdde1927156d5509a09ef8dc9ae4d9df50d5d4338f1fada622a1d2d0e6`. It
renders PDF pages 7–9 at 300 dpi with Poppler
`pdftoppm` 24.02.0 (page raster 2481 by 3249 pixels), uses a color mask to
isolate the plotted trace, and emits its pixel-center reads. The mask uses
fixed RGB-dominance thresholds from the script; qualifying pixels are grouped
with 8-connected components, then sampled scanline-by-scanline. Minimum
component area/traversal-span filters are 5000/500 pixels for Fig. 6, 1000/100
for Fig. 7, 5000/500 for Fig. 8, and 100/10 for each Fig. 9 colored series.
The global Fig. 9 filter excludes small origin marks, so a separate red/blue-
only gate retains components with at least 15 pixels and a 5-pixel vertical
span when the entire component lies within `z/L_c<=0.35, L/L_c<=0.4`. This
gate retains the source-colored marks reviewed in the page raster without
lowering the global threshold that excludes legend strokes. Reproduce with
`.venv/bin/python scripts/digitize_calbrix_dash8_cloud_curves.py`.

A second, independently calibrated raster read is in
[`data/derived/calbrix_dash8_cloud_curves_independent.csv`](../data/derived/calbrix_dash8_cloud_curves_independent.csv),
generated by
[`scripts/digitize_calbrix_dash8_cloud_curves_independent.py`](../scripts/digitize_calbrix_dash8_cloud_curves_independent.py).
It renders separate 500 dpi panel crops, measures its own tick centers, and
uses a color-distance mask with 4-pixel scan spacing and a continuity rule.
The 1,492-row output SHA-256 is
`2634389063a3d75a2e1e2c8523b3d27ae204ae31557d9e354de7fe4c2aceab4b`; the
script SHA-256 is
`7f64f33679f62031bb910d30b17237a62b4a2aa7f01b8a0497cc37c719c40b59`.
In a directed nearest-sample comparison, each primary sample was checked
against the nearest point on the corresponding independent series, using the
displayed horizontal/vertical axes. The second direction reverses the query.
For each nearest pair, read-bound overlap means both coordinate differences
fall within the sum of the two reads' per-axis bounds.

| Figure / series | Primary / independent samples | Primary-to-independent nearest distance, median / p95 / max | Read-bound overlap, primary / independent direction |
| --- | ---: | ---: | ---: |
| Fig. 6(b) | 1003 / 349 | 0.004 / 0.012 / 0.024 m | 1003/1003 / 349/349 |
| Fig. 7 | 931 / 292 | 0.005 / 0.015 / 0.040 (dimensionless) | 928/931 / 292/292 |
| Fig. 8(b) | 827 / 263 | 0.014 / 0.053 / 0.115 m | 820/827 / 263/263 |
| Fig. 9(a), red `0.5 s` | 299 / 85 | 0.026 / 0.114 / 0.207 (dimensionless) | 292/299 / 85/85 |
| Fig. 9(a), blue `1.0 s` | 917 / 243 | 0.027 / 0.095 / 0.286 (dimensionless) | 905/917 / 243/243 |
| Fig. 9(a), green `1.5 s` | 988 / 260 | 0.023 / 0.192 / 0.459 (dimensionless) | 932/988 / 260/260 |

The unequal sample densities, separate masks, and disconnected components make
the nearest-sample metrics directional; endpoint distance can reflect different
scan spacing or visible branch coverage. The overlap check supports
reproducibility of plotted reads only. It is not a solver comparison or
validation pass.

The plot coordinates are calibrated linearly from these raster axis centers
(pixel coordinates are page-image x/y, rounded to the nearest pixel, origin at
the top left):

| Figure and trace | PDF / journal page | Plotted axes; corner pixels |
| --- | --- | --- |
| Fig. 6(b), Dash-8, `t=0.5 s` | 7 / 1521 | horizontal `y=0..2 m`, vertical `Z=0..3 m`; `(x0,y0)=(1359,340)`, `(x1,y1)=(2208,1015)` |
| Fig. 7, Dash-8 simulation, `t=0.5 s` | 8 / 1522 | horizontal `y/L_c=0..2`, vertical `Z/L_c=0..2`; `(313,291)` to `(1160,935)` |
| Fig. 8(b), Dash-8, time conflicted | 9 / 1523 | horizontal `L=0..6 m`, vertical `z=0..3.5 m`; `(1238,445)` to `(2096,1113)` |
| Fig. 9(a), Dash-8, `t=0.5, 1.0, 1.5 s` | 9 / 1523 | horizontal `L/L_c=0..9`, vertical `z/L_c=0..8`; `(350,1591)` to `(1177,2242)` |

The high-resolution page raster confirms that Fig. 9(a)'s horizontal ticks are
labeled `0` through `9`: at 300 dpi their centers are approximately x=350, 443,
535, 626, 718, 810, 902, 994, 1085, and 1175 px. The labeled 9 tick is at the
right frame (approximately x=1177 px), so `dependent_max=9` is supported; this
is not an unlabeled-endpoint inference. Fig. 9(b)'s separate left frame is at
approximately x=1359 px. The Fig. 9(a) color mask is restricted to x=350..1177
px and therefore cannot include panel (b).

The original Fig. 9(a) first-pass vertical origin (`y=1653 px`) was close to
the printed 1 tick, not the zero axis; it also cropped off the upper part of
the curves. A separate 500-dpi page render places the 0 and 8 tick centers at
crop rows about 200 and 1287 (crop origin y=2450), equivalent to full-page
300-dpi rows about 1590.5 and 2241.5. The corrected first-pass script now uses
those measured axis centers and regenerates the CSV above. A regression test
cross-checks the primary tick calibration against the independent panel, whose
0–8 labels are also checked against PDF text boxes. A separate raster review
found small, disconnected red and blue source-colored marks near the origin:
two red fragments and three blue fragments lie within `z/L_c<=0.35,
L/L_c<=0.4`. They are retained as separate figure reads with widened local
pixel bounds and no interpolation to the larger curves. Their plotted positions
are consistent with curve starts, but continuity and an exact zero-origin
value are unresolved; the red fragment touching the plot edge is least certain.

Axes increase toward the right and down in these plots. Figure 6 samples the
Dash-8 blue trace. Figure 7 includes the solid blue simulation curve and filters
out the dashed Eq. (4) fit and legend marks using connected-component area and
span; its two separated visible components remain separate, with no points
interpolated across the gap. Figure 8 samples the blue Dash-8 `L(z)` trace. Its
body text identifies
`t=0.5 s` (PDF p. 7 / journal p. 1521), but its caption identifies `t=1 s`
(PDF p. 9 / journal p. 1523); `time_s` is therefore blank and the CSV retains
both candidates rather than choosing. Figure 9 preserves the red, blue, and
green Dash-8 traces for the captioned `t=0.5, 1.0, 1.5 s` and excludes the
black dashed fit. No core (`alpha_L>=0.9`) curve is digitized because the paper
does not publish a corresponding quantitative curve in these figures.

Each primary row has `read_bound_independent` and `read_bound_dependent`
half-width allowances in the corresponding plotted units. The
independent-coordinate allowance uses two rendered pixels; the dependent
allowance uses the measured half-stroke width plus two pixels. These are
conservative, correlated raster-read allowances, not statistical confidence
intervals. The independent CSV reports its own per-axis bounds. Neither pass
recovers the authors' raw arrays. The raster masks are restricted to the
calibrated plot rectangles; disconnected fragments use separate segment IDs,
and no data are inferred through visible gaps. The Fig. 9 origin fragments are
source-color-consistent but remain uncertain figure reads, particularly the
small red mark at the plot edge.

Figures 7 and 9 remain dimensionless because the paper does not report numeric
exit area `S` for converting `L_c=sqrt(S)` to meters. Figure 8 is not a unique
timed target until its caption/body conflict is resolved by a source decision.
The paired figure reads and bounds are source-preparation evidence, not raw
solver data, an exact boundary history, an acceptance target, or an E2 pass.
