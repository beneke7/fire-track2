# E3 source record: Calbrix et al. Canadair CL-415

**Purpose:** transcribe the CL-415 conventional four-release nearfield case in
Calbrix et al. for E3. This is a source handoff, not a CFD case declaration,
tolerance selection, or validation decision.

## Source and page convention

Corentin Calbrix, Alexei Stoukov, Axelle Cadiere, Benoit Roig, and Dominique
Legendre (2023), “Numerical simulation of aerial liquid drops of Canadair
CL-415 and Dash-8 airtankers,” *International Journal of Wildland Fire*
32(11), 1515–1528. [DOI](https://doi.org/10.1071/WF22147). The supplied local
PDF has 14 pages. Locators below give physical PDF page first and printed
journal page second (PDF p. 1 is journal p. 1515).
Local source PDF SHA-256: `128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4`.
Independent source review on 2026-09-25 returned **approved with revisions**;
the omitted tank-sketch label, `L_c` definition, Fig. 4 legend/prose distinction,
and authors' surface-tension rationale are clarified below. This remains a
source handoff, not an E3 readiness decision.

## CL-415 geometry and four-release layout

| Item | Evidence class | Source location and value |
| --- | --- | --- |
| Aircraft/tank arrangement | **Reported** | PDF p. 2 / journal p. 1516, Introduction: CL-415 has two tanks incorporated in the fuselage and a stated maximum liquid capacity of 6000 L. It uses belly scoops to fill. The 6000 L is aircraft capacity, not the payload of the plotted nearfield case. |
| Tank doors | **Reported** | PDF p. 4 / journal p. 1518, Fig. 1 caption: photograph shows both open doors of the left tank of the two CL-415 tanks. The simulated tank drawing has a bottom surface inclined 30 degrees to horizontal. |
| Tank sketch dimensions | **Reported drawing labels; mapping to open area incomplete** | PDF p. 4 / journal p. 1518, Fig. 1(b) labels 2 m, 1.6 m, 0.83 m, 1.8 m, and 0.3 m, and shows the 30-degree bottom inclination. These are dimensions on the tank sketch. The article does not give an outlet-area value `S`, the exact open-patch polygon, or a coordinate table for the doors; do not treat the sketch dimensions alone as a complete nozzle specification. |
| Outlet count and positions | **Reported count; position detail missing** | PDF p. 5 / journal p. 1519, Fig. 3(a) caption identifies four exits in red in the CL-415 belly domain. PDF p. 5 / journal p. 1519, Domains and meshes, says two tanks are considered for the CL-415. Together with Fig. 1's two doors on one of two tanks, this supports four modeled exit patches (two per tank); the one-to-one patch mapping is an **inference** from the figures/text. Exact patch center coordinates, spacing, area, door angles, normals, and outlet-by-outlet histories are not reported. |
| External domain | **Reported drawing dimensions** | PDF p. 5 / journal p. 1519, Fig. 3(a): CL-415 domain is labeled 22 m long, 14 m wide, and 21 m high. Coordinate bounds and exact distances from each patch to each outer boundary are not tabulated. |

The source supports “four exit patches” as the intended CL-415 numerical
geometry, but it does not provide enough text/CAD detail to reconstruct their
exact placement or directions from the article alone. Do not substitute the
four outlets of a different aircraft or assume equal per-port area/flow without
labeling that choice as an assumption.

## Water source and flight-frame conditions

| Input/history | Evidence class | Source location and value |
| --- | --- | --- |
| Liquid properties | **Reported** | PDF p. 4 / journal p. 1518, Domains and meshes: first comparison set is water with `rho_L=1000 kg/m^3`, `mu_L=0.001 Pa s`. The later Fire-Trol 931 retardant cases (`rho_L=1100 kg/m^3`, `mu_L=0.056 Pa s`) are separate and are not the E3 water reference. |
| Crossflow | **Reported** | PDF p. 4 / journal p. 1518: first CL-415 and Dash-8 water cases both use relative air speed `U_G=50 m/s`. The article says this is approximately the aircraft operating ground speed in the absence of wind. It is a controlled comparison input, distinct from the introduction's normal CL-415 air speed of approximately 55–60 m/s (PDF p. 2 / journal p. 1516). |
| Reference frame/direction | **Reported/figure-read** | PDF p. 4 / journal p. 1518: simulations use the frame moving with the airplane and impose air velocity at the domain inlet. PDF p. 7 / journal p. 1521, Fig. 6, shows the streamwise coordinate `y` along the crossflow and `z` downward; PDF p. 9 / journal p. 1523, Fig. 8(a), shows transverse `x` and downward `z`. In the figure convention, crossflow points along `+y`. A complete signed vector basis, aircraft attitude, and outlet velocity vectors are not stated. |
| Outlet history | **Reported only as a plot** | PDF p. 5 / journal p. 1519, Fig. 4: plots CL-415 top/bottom exit `U_L(t)` curves. Adjacent Results text says maximum exit speed is approximately 6 m/s, reached after 0.5 s, and the tank takes approximately 1.5 s to discharge. It reports about a 0.2 s delay between the two CL-415 curves. No raw samples, `Q_L(t)`, exact cutoff/ramp, total water mass, or measured per-outlet history is published; flow-rate measurements are stated to be confidential (PDF p. 3 / journal p. 1517). |
| Figure 4 color identity | **Conflicting report** | The Fig. 4 legend/caption (PDF p. 5 / journal p. 1519) maps red to CL-415 top exit, green to CL-415 bottom exit, and blue to Dash-8. The adjacent paragraph instead calls the delayed top exit “blue” and the bottom exit “red,” which conflicts with the legend (blue is Dash-8). Preserve this prose/legend conflict; identify the plotted traces by the figure legend, and do not use the adjacent prose to remap colors. |
| `U_L` meaning | **Source terminology ambiguity** | PDF p. 3 / journal p. 1517, Tank geometry, defines mean exit velocity as `U_L=Q_L/S`. Fig. 4 caption and Results call the curve the maximum exit velocity `U_L(t)`. No explanation reconciles mean versus maximum. Treat the graph as the published scalar `U_L(t)` history, not as a complete pointwise velocity field. |
| Air/liquid dimensionless values | **Reported** | PDF p. 8 / journal p. 1522, Table 2 (penetration): CL-415 `We_G=85,020`, `q=10.52`, `K_P=K q^alpha=1.0`, `beta=1.35`. PDF p. 9 / journal p. 1523, Table 3 (lateral expansion): `We_G=85,020`, `q=10.52`, `K_L=K' q^alpha'=0.007`, `beta'=2.6`. Both tables identify the maximum ejection velocity condition at `t=0.5 s`. |
| `S`, air properties, surface tension and gravity | **Not fully reported** | PDF p. 3 / journal p. 1517 gives `rho_G`, `mu_G`, `sigma`, and `g` symbolically in Eqs. (1)–(5), but does not state numeric CL-415 values in the methods/results. The exit-area aggregation convention for `S` across four patches is also unspecified. PDF p. 7 / journal p. 1521 defines the characteristic length as `L_c = sqrt(S)` following Legendre et al. Table dimensionless groups are reported, but the missing dimensional inputs should not be reconstructed from assumed defaults. |

For tank discharge, the paper imposes the maximum exit section during the full
load drop and defines `U_L=Q_L/S` (PDF p. 3 / journal p. 1517, Tank
geometry). The computed exit velocity profile is then imposed at each red
external-domain exit boundary (PDF p. 4 / journal p. 1518). The profile and
per-patch fluxes are not published. The first water set therefore provides a
time-varying velocity reference, not a reproducible payload or exact four-port
mass-flow history. A constant uniform outlet speed would be an **assumption**
for a controlled run, not an exact reproduction.

## VOF observables and source figures

The governing setup is shared with the Dash-8 description: unsteady 3D
incompressible, immiscible Newtonian fluids with VOF liquid fraction `alpha_L`
(PDF p. 3 / journal p. 1517, Eqs. (1)–(3)); standard `k-epsilon` RANS is used.
The paper says the surface-tension term is omitted from momentum because its
resolution is larger than an approximately 3 mm capillary length (PDF p. 3 /
journal p. 1517). This is the authors' stated rationale; the mesh description
does not establish that resolution argument across the full interface region.
The liquid core is `alpha_L >= 0.9`, and the cloud envelope is
`alpha_L >= 0.001` (PDF p. 6 / journal p. 1520).

| Figure/table | Reported CL-415 observable and timing |
| --- | --- |
| Fig. 4, PDF p. 5 / journal p. 1519 | Plotted tank-exit `U_L(t)` source curves; prose gives approximately 6 m/s peak at 0.5 s, about 1.5 s full discharge, and about 0.2 s separation between top/bottom curves. Color identity conflicts as described above. |
| Fig. 5, PDF p. 6 / journal p. 1520 | Water morphology snapshots for CL-415 at `t=0.1, 1, 3 s`; blue `alpha_L=0.001` envelope and red `alpha_L=0.9` core. Dash-8 is shown at 0.1, 1, and 4.8 s on the other panel. These are render times, not discharge boundary tables. |
| Fig. 6, PDF p. 7 / journal p. 1521 | Vertical penetration front `Z` from the `alpha_L=0.001` liquid surface as a function of streamwise `y`. The CL-415/Dash-8 comparison is explicitly at `t=0.5 s`; panel (a) shows the Dash-8 front. |
| Fig. 7 and Table 2, PDF p. 8 / journal p. 1522 | Normalized penetration `Z/L_c` versus `y/L_c` at `t=0.5 s`; CL-415 simulation plus Eq. (4) fit with `K_P=1.0`, `beta=1.35`. Table 2 reports `We_G=85,020`, `q=10.52`. |
| Fig. 8, PDF p. 9 / journal p. 1523 | Dimensional lateral expansion `L` (maximum width of dispersed liquid) versus downward distance `z`. The body text on PDF p. 7 / journal p. 1521 says this comparison is at `t=0.5 s`, while the Fig. 8 caption says `t=1 s` for its CL-415/Dash-8 comparison. Do not resolve this conflict by selecting a time without a preregistered source decision. |
| Fig. 9 and Table 3, PDF p. 9 / journal p. 1523 | Normalized total expansion `L/L_c` versus `z/L_c` for CL-415 at `t=0.5, 1.0, 1.5 s`; lateral fit coefficients in Table 3 are `K_L=0.007`, `beta'=2.6` at the maximum-ejection (`t=0.5 s`) condition. Fig. 9 is a separate normalized series and does not resolve Fig. 8's time conflict. Its caption says “Eqn 5” for the fit while the lateral relation is Eq. (6) in the body/caption coefficient statement, an internal equation-number inconsistency. |
| Fig. 11, PDF p. 10 / journal p. 1524 | Paper reports CL-415 time evolution of detected liquid-structure count at `alpha_L>=0.9` and `alpha_L>=0.001`; structures are reconstructed with a Matlab post-processing code. This is a secondary fragmentation observable, not outlet-history data. The preceding description is on PDF p. 8 / journal p. 1522. |

The source's lateral expansion is a maximum plume width. The paper does not
provide raw field arrays or numeric curve data for penetration/width, and the
local source note does not digitize them. A later digitization should state
axis calibration, color/line selection, timing choice, and uncertainty; Figure
8's timing discrepancy must remain visible in any comparison record.

### Fig. 4 CL-415 plotted outlet-velocity traces

The first raster reads of the red and green CL-415 traces are in
[`data/derived/calbrix_cl415_fig4_velocities.csv`](../data/derived/calbrix_cl415_fig4_velocities.csv),
generated by
[`scripts/digitize_calbrix_e3_fig4.py`](../scripts/digitize_calbrix_e3_fig4.py).
The PDF p. 5 / journal p. 1519 figure is rendered at 500 dpi with `pdftoppm`;
the 1700 by 1400 pixel crop starts at PDF-image coordinate `(450,1850)`. In
crop coordinates, the time ticks `0,5 s` are at `x=21.5,1473.0`, and the
velocity ticks `0,6 m/s` are at `y=1199.5,53.0`. The conversion is
`t=5(x-21.5)/(1473.0-21.5)` and
`U_L=6(1199.5-y)/(1199.5-53.0)`. Red and green RGB masks are applied
separately; the script samples 0.05 s intervals with linear interpolation
between colored pixels. The figure's legend lies within the plot region at
later times, but these extracted CL-415 traces stop before the legend occupies
their sampled positions.

The CSV has 36 red/top samples through 1.80 s and 39 green/bottom samples
through 1.95 s. The plotted red maximum reads 5.528 m/s at 0.50 s; the green
maximum reads 5.955 m/s at 0.55 s. These are close to the paper's approximate
6 m/s peak near 0.5 s, but they are centerline reads of the figure's scalar
maximum-velocity curves, not raw solver output, measured outlet profiles,
discharge rates, or four individual port histories. The last low-velocity
samples remain positive: the trace does not establish an exact zero cutoff,
even though the prose says the tank takes about 1.5 s to discharge. Do not
extend either curve to zero or infer total release mass from this CSV.
The current CSV SHA-256 is
`92ecfe6b5293d098b103e2f0560f79e926e04db557a504c97098ca180c643104`; the
generator SHA-256 is
`115273e07c4991968687fd1f0e691c56ea42249f5315c7dedd7ae9ae47985eb1`.

An independent full-page trace is in
[`data/derived/calbrix_cl415_fig4_velocities_independent.csv`](../data/derived/calbrix_cl415_fig4_velocities_independent.csv),
generated by
[`scripts/digitize_calbrix_e3_fig4_independent.py`](../scripts/digitize_calbrix_e3_fig4_independent.py).
It renders PDF p. 5 at 300 dpi and independently calibrates the raster axes,
uses NumPy color masks, and thins the colored line center. At shared 0.1 s
reads, maximum first-to-second differences are 0.0536 m/s for red and
0.0919 m/s for green; both sets fall within combined raster and timing read
bounds after propagating timing through the local trace slope. The independent
raster shows positive visible tails at 2.003 s / 0.060 m/s (red) and 1.974 s /
0.051 m/s (green), while the first extraction stops earlier. These separate
visible endpoints do not settle the prose's approximate 1.5 s discharge time
or establish shutoff; neither CSV appends zero. This agreement supports figure
reading reproducibility only, not independent experimental evidence or a
four-port source history. The independent CSV SHA-256 is
`21a77aa2009ab1184acf1ae1ff14094964a03614810c49ff32e9fdb6b781d2c9` and the
script SHA-256 is
`0f916d22c89d9dadf97d4e6180cfd6c015bee9e1a3cb5643de574040bbc557aa`.

The assigned read allowances are approximately `±0.05 m/s` and `±0.01 s`.
They are heuristic raster-read allowances, not paper uncertainty or source
error bars, and time/velocity reads are correlated on the steep rise and
decay. Near-baseline points have especially high relative uncertainty. A
independent read above checks figure-read reproducibility; regardless of that
agreement, the prose/legend color conflict and the missing map from two plotted
curves to four exits remain. Use the
caption/legend mapping (red top, green bottom) as the primary trace identity,
while preserving the adjacent prose's inconsistent “blue top, red bottom”
wording in sensitivity notes.

### Fig. 11(a) plotted structure-count trace

The figure is on **PDF p. 10 / journal p. 1524**. The page locator in an
earlier version of this source record pointed to PDF p. 8 / journal p. 1522,
which contains the explanatory paragraph but not Fig. 11. The paragraph says
the authors used Matlab to reconstruct 3D liquid structures at each instant.
Panel (a) plots the number of identified structures for
`0.001 <= alpha_L <= 1` (red) and `0.9 <= alpha_L <= 1` (blue) over 0–3 s.
The lower threshold includes smaller-than-grid fragments in larger numbers.
These are **structure counts, not parcel counts**. The two curves are
thresholds applied to the same simulation and unpublished reconstruction code,
so they are not independent observations.

The first reproducible figure trace is in
[`data/derived/calbrix_cl415_fig11_structure_counts.csv`](../data/derived/calbrix_cl415_fig11_structure_counts.csv),
generated by [`scripts/digitize_calbrix_e3_fig11.py`](../scripts/digitize_calbrix_e3_fig11.py).
It contains 0.1 s reads from 0.1 to 3.0 s, rounded to the nearest count, with
rendered-crop pixel coordinates and `±5` count / `±0.01 s` figure-read bounds.
The crop is PDF p. 10 rendered at 500 dpi with `pdftoppm`; the linear axes use
`t=0..3 s` at crop pixels `x=55.5..1408.0` and `N=0..400` at `y=1127.5..121.5`.
Use `t = 3 (x - 55.5)/(1408.0 - 55.5)` and
`N = 400 (1127.5 - y)/(1127.5 - 121.5)`. The line centers are isolated with
red pixels satisfying `R>150`, `R>1.65G`, `R>1.4B`, and blue pixels satisfying
`B>130`, `B>1.6R`, `B>1.35G`; the red legend swatch at crop pixels
`x=450..580, y=730..770` and blue swatch at `x=450..580, y=815..860` are
excluded. Neither swatch overlaps its matching data curve. At each sample
time the script takes the median colored-line pixel center per column and
linearly interpolates the trace. Reproduce with:

```sh
.venv/bin/python scripts/digitize_calbrix_e3_fig11.py
```

The first-trace CSV SHA-256 is
`cb60d88ab7105725f23917f223b07999d8c0cd1e61bf13d5a49012ea14bc43de`; the
generator SHA-256 is
`06c0425759fca91fe6645b282f3556ed70df4bbd9ace4aefe9f33e0cf1c7655f`.

The red trace's plotted peak is slightly above the 400-count tick; the CSV read
of 421 at 1.1 s is therefore a linear-axis extrapolation above the highest
labeled y tick, not an interpolation between labeled values. The `±5` count and
`±0.01 s` bounds are heuristic figure-read allowances, not bounds reported by
the paper or derived from repeated traces. They are correlated: around the steep
rise, a `±0.01 s` horizontal shift corresponds to roughly 6–10 counts, so a
fixed vertical allowance alone does not cover the joint read interval. Propagate
time and ordinate read together if plotting an overlay, and do not treat them
as independent random errors or as source/simulation uncertainty. The PDF
contains a raster figure, no raw counts or Matlab code, and no published
digitization error. An independent second read is in
[`data/derived/calbrix_cl415_fig11_structure_counts_independent.csv`](../data/derived/calbrix_cl415_fig11_structure_counts_independent.csv),
generated by
[`scripts/digitize_calbrix_e3_fig11_independent.py`](../scripts/digitize_calbrix_e3_fig11_independent.py)
and audited in
[`E3_FIG11_INDEPENDENT_TRACE_AUDIT.md`](E3_FIG11_INDEPENDENT_TRACE_AUDIT.md).
At the 30 matched nominal times, its red/cloud trace differs from the first by
mean `+0.50`, RMSE `1.85`, and at most 4 counts; the blue/core trace differs by
mean `+0.27`, RMSE `0.73`, and at most 2 counts. Every pointwise difference is
inside the combined vertical read allowances. This supports reproducible
figure reading only. The 0.1 s sample grid is a digitizer choice, not a paper
sampling interval, and the authors' structure-detection method remains
unpublished. Matching traces therefore do not establish an equivalent
quantitative benchmark observable. Keep Fig. 11 descriptive unless that
method is recovered or equivalence is independently demonstrated.

Panel (b), at `t=1 s` and the `0.001 <= alpha_L <= 1` detection, prints these
velocity-component values by equivalent-diameter interval:

| Equivalent diameter (m) | `v_x` | `v_y` | `v_z` |
| --- | ---: | ---: | ---: |
| 0.04–0.1 | 1.42 | 20.87 | −1.01 |
| 0.1–1 | 0.68 | 42.58 | −3.22 |
| 1–10 | −0.15 | 26.94 | −4.87 |

The legend associates these with transverse (`v_x`), streamwise (`v_y`), and
vertical (`v_z`) components. The panel says “Velocity components” but gives no
unit or definition of the statistic represented by each bar. These numbers
are retained as printed annotations only; do not assign a weighting or use
them as a quantitative gate without recovering that definition.

## Mesh, numerics, and boundary-condition gaps

- **Tank discharge mesh — reported:** PDF p. 3 / journal p. 1517 says CL-415
  uses a trimmed-cell mesh; by symmetry, half of the front part of one tank
  is calculated. The half-tank mesh has about 810,000 cells, from about
  `1e-2 m` in the center to `5e-6 m` at walls.
- **External nearfield mesh — reported:** PDF p. 5 / journal p. 1519 says the
  complex belly-domain uses a polyhedral mesh with cell sizes from `8e-2 m` in
  the center to `8e-6 m` at walls and about 6.9 million cells for CL-415.
  The run used 180 processors and a reported 3240 CPU-hours. At least two
  resolutions were considered for each case, but the paper does not identify
  which exact grid produced each reported curve or give quantitative grid
  convergence uncertainty.
- **Solver/physics — reported:** STAR-CCM+, unsteady 3D VOF, two
  incompressible immiscible Newtonian fluids, standard `k-epsilon` RANS; the
  authors omit surface tension for their stated capillary-resolution reason,
  which the reported mesh information does not independently establish.
- **Not specified:** time step/CFL, temporal and convective discretization,
  exact inlet turbulence, spatial mapping of the tank-exit velocity, precise
  inlet/outflow/top/side conditions, aircraft-wall slip condition, starting
  fields, outlet patch coordinates/normals/areas, per-port mass flow, exact
  water payload, and a numerical `S` for the characteristic length.

The introductory CL-415 maximum tank capacity of 6000 L and the later
retardant field comparisons (PDF pp. 9–12 / journal pp. 1523–1526) are not
substitutes for the unspecified water source history or payload in this
nearfield numerical comparison.

## Evidence classes and claim limits

- **Reported:** four exits shown in Fig. 3, two tank arrangement, plotted
  source histories, 50 m/s crossflow, water properties, normalized
  dimensionless values, solver, mesh counts, and nearfield observables.
- **Digitized:** paired first and independent figure-read traces of the two
  plotted Fig. 4 scalar curves and two reads of the supplemental Fig. 11(a)
  structure counts are described above. The Fig. 4 reads do not define exact
  source shutoff, flow rate, or histories for all four exits; Fig. 11's count
  trace is a different, secondary observable.
- **Inferred:** four outlets likely correspond to two door exits on each of
  two tanks; figure-based coordinate directions; exact per-port mapping is
  unavailable.
- **Assumed:** any numeric per-outlet spacing/area, equal flow split,
  constant velocity, outlet vector, air/water missing properties, or chosen
  resolution/time step beyond the paper's reported mesh facts.

This is a numerical nearfield benchmark with a water source. It does not
validate retardant or foam, field deposition, the ground pattern, or a
fourfold useful-strip gain. This record does not run CFD, select E3 tolerances,
or declare E3 ready.
