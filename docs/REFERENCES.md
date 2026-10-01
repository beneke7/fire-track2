# Benchmark reference inventory

**Inventory basis:** the eight PDFs present beside `track2_aerial_drop_experiment_plan.md` on 24 September 2026 were extracted with `pdftotext -layout` to temporary text files and checked for title, DOI, page count, tables, and figure captions. Page numbers below are **PDF page numbers** (the number of physical pages in the supplied file); journal pagination is added where present. The source PDFs remain the evidence of record. Figure digitization is a secondary approximation and must carry its own calibration and uncertainty.

## Local PDFs

| Local PDF | Verified bibliographic identity | Relevant source locations and intended use | Limits / status |
| --- | --- | --- | --- |
| `Examining_the_Effectiveness_of_Aerial_Firefighting.pdf` | Á. Restás (2023), “Examining the Effectiveness of Aerial Firefighting with the Components of Firebreak Requirements and Footprint Geometry—Critics of the Present Practice,” *Fire* 6(9), 351. [doi:10.3390/fire6090351](https://doi.org/10.3390/fire6090351). 17 PDF pages. | PDF pp. 7–12: the threshold-width geometry and equations; Fig. 7 and the 550 m² example on pp. 9–11; Tables 1–2 on p. 12 summarize widths, effective ellipse, converted rectangle, and ratios. At a 9 m band, the text reports an approximately 50 m by 14 m qualifying ellipse converted to an approximately 61 m rectangle; Restás reports an effective qualifying ellipse length of 38.5 m; direct evaluation of the displayed rounded semiaxes and 9 m chord gives about 38.30 m. Using the paper's rounded 550 m² area, the rectangle is about 61.1 m, so both calculations support roughly 1.6× for that geometry-only illustration. | This is a simplified geometric conversion based on prior footprint data, not a fluid simulation, field test of the proposed outlet, or fourfold result. It motivates the strip score and $C_*=2.4\,\mathrm{kg/m^2}$; it cannot validate E6. |
| `WF09122.pdf` | J. H. Amorim (2011), “Numerical modelling of the aerial drop of firefighting agents by fixed-wing aircraft. Part I: model development,” *International Journal of Wildland Fire* 20, 384–393. [doi:10.1071/WF09122](https://doi.org/10.1071/WF09122). 10 PDF pages. | PDF pp. 2–7: ADM formulation, modules, assumptions, and input parameters; Fig. 2 and Table 2 are useful for understanding how that legacy model maps release and atmospheric inputs to deposition. | This describes another model and its assumptions. It is context for the ground-delivery problem, not a verification target for our VOF solver. |
| `WF09123.pdf` | J. H. Amorim (2011), “Numerical modelling of the aerial drop of firefighting agents by fixed-wing aircraft. Part II: model validation,” *International Journal of Wildland Fire* 20, 394–406. [doi:10.1071/WF09123](https://doi.org/10.1071/WF09123). 13 PDF pages. | PDF p. 3, Table 2: M134 water inputs (4.64 m³, 2.04 m³/s, 60.66 m height, 67.90 m/s drop speed, 2.68 m/s wind, 135° relative wind direction). PDF p. 6, Fig. 4: measured versus ADM Marana contour maps. PDF pp. 6–8, Tables 5–8 and Figs. 5–7: reported pattern-length/area statistics. PDF p. 11, Fig. 9: measured and modeled `Vx` profile versus along-track position; the paper defines `Vx` as a cross-track sum at each x, not a running cumulative sum along x. Its displayed x position is adjusted because the aircraft position is unknown. The reproducible vector-marker trace and source limits are recorded in [`E4_AMORIM_M134_SOURCE.md`](../experiments/E4_AMORIM_M134_SOURCE.md) and [`amorim_m134_fig9.csv`](../data/derived/amorim_m134_fig9.csv). | The paper has cup-grid field measurements and reports its model's overall comparison statistics, but the local PDF does not include raw M134 cup-by-cup data or all outlet traces needed to reproduce the field map exactly. The CSV is a plotted-figure digitization, not raw data; any reconstructed flow history is approximate. The paper's aggregate result (78% of computed line lengths within 10%) is not a result for this project or an automatic acceptance guarantee for one M134 case. |
| `WF13029.pdf` | D. Legendre, R. Becker, E. Alméras, and A. Chassagne (2014), “Air tanker drop patterns,” *International Journal of Wildland Fire* 23, 272–280. [doi:10.1071/WF13029](https://doi.org/10.1071/WF13029). 9 PDF pages. | PDF pp. 2–3, Tables 1–4: source drop-test parameters across aircraft and delivery systems. PDF pp. 4–8, Figs. 3–8 and equations: empirical pattern length, width, Gaussian ground coverage, and contour predictions. Useful for map-context and source-condition interpretation. | Aggregated field-pattern relationships across systems; not validation of the Restás four-slot source or a fourfold useful-strip outcome. Keep its ground/collected-fraction convention distinct from $f_{\rm useful}$. |
| `Study on the ground fraction of air tankers.pdf` | Y. Gu, R. Zhou, H. Xie, and L. Shi (2023), “Study on the ground fraction of air tankers,” *International Journal of Wildland Fire* 32(4), 576–592. [doi:10.1071/WF22055](https://doi.org/10.1071/WF22055). 17 PDF pages. | PDF pp. 3–8: method, field-pattern examples, and AG600 conditions; Table 4 on p. 8 lists six AG600 water drops. Table 5 on p. 9 gives measured ground fractions 42.20%, 43.22%, 41.35%, 42.52%, 44.31%, and 42.08%, alongside post-processing estimates 46.21%, 45.40%, 44.95%, 44.08%, 47.99%, and 45.07%. PDF pp. 9–13, Figs. 5–11: simplified contours and fitted ground-fraction relations. | The paper defines ground fraction as collected liquid divided by released liquid. Its method is fitted/reconstructed from field data, and its reported agreement is not a useful-strip score. Table summaries do not replace raw cup-level samples. It is a collection-convention check only if matching conditions can be reconstructed. |
| `Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf` | C. Calbrix, A. Stoukov, A. Cadière, B. Roig, and D. Legendre (2023), “Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers,” *International Journal of Wildland Fire* 32(11), 1515–1528. [doi:10.1071/WF22147](https://doi.org/10.1071/WF22147). 14 PDF pages. | PDF pp. 4–5: Figs. 1–4 show release geometry and outlet velocity histories. PDF pp. 5–10: Figs. 5–11 and Tables 1–4 show time-resolved plume, penetration, lateral expansion, and fragmentation observables; the Dash-8 maximum is about 4.8 m/s, and the reference relative airflow is 50 m/s. PDF pp. 11–12: Table 5 and Figs. 12–13 compare retardant footprint/expansion with drop-test information. | The published simulations use $v(t)$, geometry-specific outlet histories, and a time-dependent release. A constant 4.8 m/s source is a controlled comparison, not exact replication. Fig. 8's text and caption specify different times; record the chosen time before comparison. Nearfield plots do not validate ground deposition. |
| `Breakup Processes and Droplet Characteristics of Liquid Jets Injected into Low-Speed Air Crossflow.pdf` | L. Kong, T. Lan, J. Chen, K. Wang, and H. Sun (2020), “Breakup Processes and Droplet Characteristics of Liquid Jets Injected into Low-Speed Air Crossflow,” *Processes* 8(6), 676. [doi:10.3390/pr8060676](https://doi.org/10.3390/pr8060676). 16 PDF pages. | PDF pp. 4–5: 1 mm orifice geometry and experimental conditions (Table 1). PDF pp. 10–14: primary breakup regime map (Fig. 9), droplet size distributions (Figs. 10–13), and velocities (Fig. 14). Could inform a separate small-nozzle qualitative or experimental comparison. | This is an experiment on a 1 mm orifice in low-speed crossflow, not Rouaix et al.'s 0.2–0.6 m numerical VOF jet. It does not supply Rouaix's initial/boundary conditions or replace E1. Do not cite it as the planned E1 benchmark. |
| `Water droplet dynamics and evaporation in airtanker firefighting.pdf` | Fabian Denner (2026), “Water droplet dynamics and evaporation in airtanker firefighting,” arXiv:2603.11855v1, posted 12 March 2026. [arXiv:2603.11855](https://arxiv.org/abs/2603.11855). 13 PDF pages. The supplied file is the v1 preprint; no journal DOI is stated in that file. | PDF p. 3: isolated-drop momentum/drag and breakup equations (Eqs. 1–11), now equation-checked in [`REGION_C_DENNER_ISOLATED_DROP.md`](../experiments/REGION_C_DENNER_ISOLATED_DROP.md). PDF pp. 5–10: coupled heat/mass transfer; Figs. 2–8 and Table 2 discuss size, flight time, height, humidity and evaporation, and may support later sensitivity cases. | The paper explicitly isolates individual droplets and does not resolve collective spray, wake interaction, or turbulence. The current component omits heat/mass transfer and is not a plume, aircraft outlet, ground-pattern, or field validation source. Treat as preprint context, not E1–E6 validation. |

The Calbrix Dash-8 water-case extraction, Fig. 8 timing conflict, and first-pass
Fig. 4 velocity digitization are recorded in
[`experiments/E2_CALBRIX_SOURCE.md`](../experiments/E2_CALBRIX_SOURCE.md) and
[`data/derived/calbrix_dash8_fig4_velocity.csv`](../data/derived/calbrix_dash8_fig4_velocity.csv).
The curve is a digitized scalar peak-velocity trace, not the unavailable exact
discharge history or spatial outlet profile. Missing air properties, exit
area, and boundary details prevent exact reconstruction from the paper alone.

The corresponding CL-415/E3 source extraction is recorded in
[`experiments/E3_CALBRIX_CL415_SOURCE.md`](../experiments/E3_CALBRIX_CL415_SOURCE.md).
It records the reported four-exit layout, paired independent digitizations of
the plotted Fig. 4 scalar histories and Fig. 11(a) structure counts, nearfield
observables, and reconstruction gaps. The Fig. 4 top/bottom color labels
conflict between legend and prose; exact outlet coordinates, areas, spatial
flow histories, and patch mapping remain unpublished. The figure reads are
not original solver arrays or a quantitative reproduction of the unpublished
structure-detection method, so no E3 solver comparison or pass is claimed.

## External E1 source: Rouaix et al.

The plan's E1 citation is Clément Rouaix, Alexei Stoukov, Yannick Bury, David
Joubert, and Dominique Legendre (2023), “Liquid jet breakup in gaseous
crossflow injected through a large diameter nozzle,” *International Journal
of Multiphase Flow* 163, article 104419
([DOI](https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419),
[publisher record](https://www.sciencedirect.com/science/article/pii/S0301932223000423)).
A full 22-page author manuscript is available at
[HAL record hal-04098260](https://hal.science/hal-04098260v1) and its
[PDF](https://hal.science/hal-04098260v1/file/Rouaix_28516.pdf). It was not one
of the eight supplied local PDFs; the original local set remains unchanged.

The manuscript is the primary source for E1 conditions. PDF p. 5 (article p. 4),
Tables 2–3, lists round-jet diameters 0.2–0.6 m and gas speeds 50–90 m/s. Its
reference Case 1 is a **single** 0.4 m nozzle with liquid speed 10 m/s into a
70 m/s crossflow; the tables report $q=17.3$, $We_g=3.2\times10^4$,
$Re_j=4.9\times10^6$, and $Re_g=1.78\times10^6$. Other Case-1 inputs are
water density 997.6 kg/m³, air density 1.18 kg/m³, surface tension 0.072 N/m,
dynamic viscosities $8.89\times10^{-4}$ and $1.86\times10^{-5}$ Pa·s,
temperature 300 K, and pressure 101,325 Pa. The figure axes use liquid velocity
downward along $-e_y$ and air in $+e_x$ (PDF p. 4, article p. 3, Fig. 1). The
table gives a 16 mm Case-1 mesh size; the mesh study compares 70, 50, 30 and
16 mm. It uses inlet turbulence intensity 0.01 and a realizable $k$–$\epsilon$
RANS model.

PDF p. 7 (article p. 6), §3.2/Fig. 3, describes a curved no-slip aircraft
underside, an air inlet 2.5 m upstream of the nozzle center, a domain about
$25d_j$ high opening from $50d_j\times17.5d_j$ at the top to
$50d_j\times40d_j$ at the bottom, and outflow at atmospheric pressure.
The source is a steady uniform-velocity nozzle inlet; the approximately 5 s
shown on PDF p. 8 (article p. 7) is simulation duration, not a finite release
period. The paper discusses four 0.4 m outlets on the B747, but the numerical
benchmark models one isolated nozzle and provides no outlet spacing or
coordinates. For Case 1, $\rho \pi D^2v/4\approx1,254$ kg/s is a derived
single-nozzle flow rate, not a reported total payload.

The local Kong et al. 1 mm experimental paper remains a different study and
does not replace E1. Before an E1 gate decision, transcribe the chosen exact
case and boundary conditions and independently digitize the required
penetration, lateral-width and breakup-location curves with uncertainty. Do
not infer four-slot hardware data, a release duration, or ground delivery from
this isolated-nozzle benchmark.

The Case-1 Figure 13 vector-path and independently traced raster curves, with
their procedures and extraction bounds, are recorded in
[`experiments/E1_ROUAIX_CASE1_SOURCE.md`](../experiments/E1_ROUAIX_CASE1_SOURCE.md),
[`data/derived/rouaix_e1_case1_fig13.csv`](../data/derived/rouaix_e1_case1_fig13.csv),
and [`data/derived/rouaix_e1_case1_fig13_raster.csv`](../data/derived/rouaix_e1_case1_fig13_raster.csv).
The two methods agree within their extraction bounds. Section 4.3's equations
are cross-case empirical fits, separate from Case 1 Figure 13, and their fit
scatter is not reported. Residuals against the plotted curve are therefore a
secondary consistency check, not a demonstrated source contradiction. The
unstated figure sampling time, ambiguous width definition, source-aware
comparison limits, and solver/resource qualification remain open before an E1
benchmark run.

## Additional external source: Gu et al. (2026)

Yin Gu, Hui Lv, and Rui Zhou, “Fighting with wildfire: unsteady discharge
flow dynamics and drop pattern prediction for air tankers,” *Results in
Engineering* 30 (2026), 110410
([DOI and publisher record](https://doi.org/10.1016/j.rineng.2026.110410)).
The abstract describes a reduced-order unsteady tank-discharge model based on
non-constant Bernoulli flow and rigid-body rotation, coupled to a variable-flow
drop-pattern model. It reports validation against full-scale discharge/drop
data, including 8.17% average relative error in coverage-line lengths and
−6.51% error in cumulative deposition versus 23.55% for the earlier model.
This may help supply a time-varying outlet-flow history and an independent
whole-drop mass/deposition check when its system geometry and assumptions fit.
It is not a VOF method or a direct benchmark for the four horizontal Restás
outlets. This is an abstract-level review; the signed PDF link supplied in chat
expired before its equations and case data could be checked.

## Non-PDF implementation reference

The experiment plan lists [FluTAS](https://github.com/Multiphysics-Flow-Solvers/FluTAS) as a GPU-capable VOF implementation. No upstream FluTAS source is bundled with the papers. The [GPU feasibility record](GPU_FLUTAS_FEASIBILITY.md) pins the reviewed upstream revision; a native Blackwell build and upstream bubble check have passed. The first synthetic source/return candidate compiled and passed static/fixture checks but was withdrawn after review found state-timing and return-flow defects. A corrected candidate is in progress. No source CFD has run. Treat aircraft inlet, turbulence, and boundary behavior as unqualified until their specific gates pass.

## Data extraction and citation policy

- Preserve each source PDF version by DOI/URL and SHA-256, extracted text, and page/table/figure locator. Keep digitized points, image calibration, axis transforms, and independently produced extractions as versioned data files.
- Transcribe tabular values directly and record units exactly. For figure-derived values, report pixel/axis calibration and digitization uncertainty; do not present digitized curves as raw source data.
- Do not infer missing outlet traces, cup weights, or timing from a plotted contour without labelling the reconstruction. Seek raw trial/cup data and case metadata for E4 and E5.
- Keep author-reported model comparisons, field measurements, and our future simulation results in separate columns/files. Source-reported metrics are not our acceptance results.
