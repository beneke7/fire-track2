# Shi et al. (Yumeng) VOF reference audit

**Prepared:** 28 October 2026

**Source:** Yumeng Shi, Qiuzu Yang, Xinzhe Chang, Jiyuan Ye, and Fei Xu,
“A volume of fluid-enhanced-discrete phase model algorithm for water dropping
simulation of firefighting aircraft,” *Physics of Fluids* 38, 043308 (2026),
[DOI 10.1063/5.0311627](https://doi.org/10.1063/5.0311627). The preserved local
source is [`yumeng.et.al.pdf`](../yumeng.et.al.pdf), SHA-256
`e27a73fc252fe1e5350aeb54c144668a050b4eec2918bc9abfb9b4ba24741149`.

## Assessment

This paper is useful as a **hybrid VOF-to-particle method and scale-cost
reference**, and as a source for candidate interface, breakup, and handoff
sensitivity checks. It is not a fully reproducible solver benchmark and does
not establish conservation of the proposed handoff for this project. The
article's only detailed VOF jet case is a 0.8 mm jet at small scale. The
firefighting-aircraft cases use enhanced-DPM for the ground-distribution
calculations; they do not run the AG600 plume as VOF or validate a full
VOF-to-particle descent.

For this repository, Shi et al. can inform a **separate auxiliary hybrid
method study**. It should not replace Rouaix Case 1 as the quantitative
large-diameter nearfield reference, and it cannot explain the current
OpenFOAM pressure-corrector behavior: Shi et al. do not state the solver
software/version, pressure-velocity coupling, pressure discretization, linear
solver, or comparable convergence controls. The paper reports an
incompressible VOF formulation, not a compressible gas model.

The reported data, the paper's numerical outputs, any arithmetic derived from
its tables, and unreported assumptions are kept separate below. I read the
complete 17-page PDF and rendered all pages; figures/tables/equations cited
here refer to the PDF page and printed article page separately. Read-only
extraction and page images are retained under
[`results/runs/yumeng-vof-audit-20261028/`](../results/runs/yumeng-vof-audit-20261028/).
No curves or maps were digitized for this audit. An independent read-only scientific review cross-checked the equations, setup and validation claims; primary integration corrected page anchors and distinguished under-specification from actual contradictions.

## Source model and implementation inputs

| Item | Source statement | Classification and provenance |
|---|---|---|
| Phase representation | Liquid volume fraction `alpha = Vl/V`, Eq. (1); `alpha=0` air, `alpha=1` liquid, intermediate values interface. The fraction equation is `d alpha/dt + div(alpha u)=0`, Eq. (2). | **Reported model equation**, PDF p. 4 / printed p. 3, Eqs. (1)–(2). No compression term, boundedness correction, subcycling count, or exact implemented alpha-flux equation is given. |
| Momentum, density, viscosity | The paper says it solves **incompressible** Navier–Stokes, Eq. (3), with a single air–water mixture velocity and volume-weighted `rho` and `mu`, Eq. (5). Gravity and a continuum-surface-force term are included. | **Reported model equation**, PDF p. 4 / printed p. 3, Eqs. (3)–(5). It does not specify gas compressibility, an equation of state, or gravity vector/magnitude. |
| Surface tension and interface | CSF force is printed as `F_sigma = sigma*kappa*grad(F)`, Eq. (4). The interface is reconstructed using geometric PLIC. | **Reported method**, PDF p. 4 / printed p. 3, Eq. (4) and paragraph following Eq. (5). The indicator `F` is not separately defined there; do not silently substitute a project field name. |
| Turbulence | SST `k–omega` is described with transport equations (6)–(7); constants are referred to generically. | **Reported method**, PDF p. 4 / printed p. 3, Eqs. (6)–(7). Inlet turbulence, wall treatment, wall `y+`, limiter values, and turbulence boundary conditions are not reported for the VOF case. |
| Material properties | Table I reports air `rho=1.18 kg/m3`, `mu=1.86e-6 Pa s`; water `rho=997 kg/m3`, `mu=8.94e-4 Pa s`; `sigma=0.0708`, with the printed unit `N/s`. | **Reported numerical inputs**, PDF p. 7 / printed p. 6, Table I. Preserve the air-viscosity exponent as printed (possible exponent typo) and the surface-tension unit (not the expected force-per-length unit) until checked against the cited original/source authors. No correction is assumed here. |
| Software and numerics | Table II lists transient, VOF-to-DPM, explicit geometric reconstruction, second-order-upwind momentum, SST `k–omega`, no-slip, CSF, and `dt=1e-7 s`. | **Reported settings**, PDF p. 8 / printed p. 7, Table II. Software name/version, pressure equation, pressure-velocity coupling, gradient/Laplacian schemes, linear solvers, residual definitions, nonlinear iteration counts, and exact stopping rules are missing. Do not infer that the solver was Fluent or OpenFOAM from table terminology. |
| Initial and boundary state | Crossflow boundary is described as velocity inlet at `x=0`; a `y=50` plane is no-slip; remaining boundaries are “free outflow.” Liquid inlet is at `(2,10,10)`, diameter `0.8 mm`. | **Reported setup**, PDF p. 7 / printed p. 6, Section III B and Fig. 8. Coordinate units, inlet velocity profile, inlet turbulence, pressure/outflow treatment, initial air/liquid field, contact angle, and exact face orientation are not specified. The axis-to-dimension mapping is ambiguous; see discrepancy register. |

The printed property table also labels density as `P (kg/m3)` and dynamic
viscosity as `M (Pa s)`. The notation does not create a new measured quantity.
The paper gives no independent material-property uncertainty or temperature
range (PDF p. 7 / printed p. 6, Table I).

## VOF crossflow case: reported inputs and numerical results

The case is presented as a reproduced benchmark from Li and Soteriou (2016),
not as an independent raw-experiment dataset. Figure 12 explicitly reproduces
their published velocity-map results, and the article calls this a
“benchmark transverse-jet case” (PDF pp. 7–9 / printed pp. 6–8, Section III B
and Fig. 12). The underlying Li and Soteriou article is cited as *Physics of
Fluids* 28, 082101 (2016), DOI [10.1063/1.4959290](https://doi.org/10.1063/1.4959290).
The Yumeng article does not provide raw reference arrays or a supplementary
dataset; its data-availability statement says data are available from the
corresponding author on reasonable request (PDF p. 17 / printed p. 16).

| Quantity | Value or statement | Classification and provenance |
|---|---|---|
| Nozzle and domain | Inlet diameter `0.8 mm`; domain `30 x 20 x 50 mm3`, described as length, width, height; inlet coordinates `(2,10,10)`. | **Reported geometry**, PDF p. 7 / printed p. 6, Section III B and Fig. 8. The coordinate unit and which dimension maps to which plotted axis are not explicit. |
| Water and air speeds | Water `17.7 m/s`; crossflow `54.8 m/s`. | **Reported operating inputs**, PDF p. 7 / printed p. 6, Section III B. Inlet profiles and velocity fluctuations are not stated. |
| Dimensionless conditions | Momentum ratio `88.2`; `We=40`. | **Reported inputs**, same location. The paper does not give its momentum-ratio or benchmark-Weber-number definition in this section; use the original cited benchmark definition before reproducing. |
| Cross-check of dimensionless values | With Table I values and reported speeds/diameter, `J = rho_l U_l^2/(rho_g U_g^2) = 88.2`. Using crossflow speed in `We_g = rho_g U_g^2 D/sigma` gives `40.0` if `sigma=0.0708` is numerically interpreted as N/m. Using Eq. (10)'s relative speed for initially perpendicular jet/crossflow velocities, `sqrt(U_g^2+U_l^2)=57.59 m/s`, gives a droplet-Weber value of about `44.2`. | **Calculated arithmetic**, not additional measurements, from PDF pp. 4, 7 / printed pp. 3, 6, Eqs. (4), (10), Table I and Section III B. The 40 and 44.2 values may represent distinct gas-crossflow and local droplet-relative Weber conventions; the paper does not define its benchmark `We` alongside Eq. (10). This arithmetic does not resolve the Table I `N/s` unit or prove the source's `J` definition. |
| Approximate full-penetration time | `~2 ms`. | **Reported numerical characterization**, PDF p. 8 / printed p. 7, text before Table II. It is not defined as a stopping time or tied to a stated boundary observable; the same section later reports a `0.1 s` simulation. |
| AMR levels | Two, three, and four refinement levels were compared. The three-level mesh had minimum cell size `38 um`; the text calls this comparable to, and slightly finer than, a `39 um` literature value. | **Reported mesh study**, PDF p. 8 / printed p. 7, Fig. 9 and its text. Cell counts, base spacing, refinement variable/thresholds, buffer layers, and domain-wide versus local minimum-cell distribution are not given. “Boundary changes are stable” is a visual conclusion, not a reported numerical error norm. |
| Physical duration and run cost | The VOF case is said to run to `0.1 s`, taking approximately two weeks on a 12-core/24-thread Intel Xeon Platinum 8352Y at 2.8 GHz with 64 GB RAM. Table III separately reports the VOF baseline at about `500 h` for `0.1 s`. | **Reported performance estimates**, PDF pp. 8, 10 / printed pp. 7, 9, paragraph after Table II and Table III. Both are approximate source estimates; they are not independently benchmarked or normalized to this workstation. |
| Figures used for comparison | Fig. 12 shows VOF and hybrid velocity contours in the `y=10 mm` midplane against a reproduced Li–Soteriou image. Fig. 13 plots “Uniform Grid” and “AMR (3 Level)” boundaries and marks `Maximum error: 4.5%`. | **Published figure output**, PDF p. 9 / printed p. 8, Figs. 12–13. The article prose calls 4.5% the maximum error after extracting a boundary from literature, but the plotted arrow is between the two labelled numerical curves; a third gray curve/data cloud is unlabeled. The 4.5% cannot be assigned to experimental/literature agreement without clarification. No digitization was done for this audit. |
| Time-step controls | Narrative: `1e-8` to `1e-5 s` until residuals fall below `1e-3`. Table II: `1e-7 s`. | **Under-specified reported schedule**, PDF p. 8 / printed p. 7, Table II and surrounding text. The table value lies inside the stated range, so these statements are not inherently contradictory. It is not clear whether the range is adaptive stepping or a sweep, which values were used in this case, or how residual stopping interacts with time stepping. This is not a time-step convergence study. |

Table III (PDF p. 10 / printed p. 9) also claims enhanced DPM takes about
0.10 h (six minutes), standard DPM about 0.05 h (three minutes), and hybrid
about 20% of the full-VOF runtime, depending on its transition. Its normalized
runtime and boundary-error definitions are not reproducibly specified. The
table claims hybrid boundary error below 15% relative to VOF and standard-DPM
error above 40%; these are author-reported numerical comparisons, not an
experimental uncertainty bound or an L95 result. They support profiling a
conservative hybrid architecture, but cannot forecast our runtime or justify
accepting its transfer without mass/momentum and ground-map checks.

The VOF case is therefore not directly reproducible from the article. For
example, a reader cannot reconstruct its AMR trigger, mesh cell count,
pressure-velocity algorithm, cell-face schemes beyond two listed items,
time-step history, or exact alpha contour used to extract the Fig. 13
boundary. The source case remains useful for identifying candidate
observables and scales; it does not supply a complete benchmark package.

## VOF-to-DPM handoff and breakup model

The paper says detached liquid is converted from VOF into Lagrangian droplets
when equivalent diameter and asphericity satisfy
`d_eq <= d_thr` and `xi <= xi_c` (Eq. (16), PDF p. 5 / printed p. 4). It
states that conversion removes liquid from VOF and maps it to DPM while
preserving mass, momentum, and position (PDF p. 5 / printed p. 4, Section II
C). This is a **reported conservation claim**, not a reported residual
measurement: no handoff-plane flux, per-interval error, global exclusive
mass ledger, transfer count/weight, or direct-versus-hybrid impact comparison
is supplied.

The only numerical conversion choices shown are Fig. 11: `(d_eq, xi)` of
`(0.4 mm, 0.5)`, `(0.8 mm, 0.5)`, and `(0.4 mm, 0.1)` (PDF p. 8 / printed
p. 7). The paper says the first combination best captured ligaments and
phase conversion; this is a **qualitative sensitivity conclusion**, not a
fitted or statistically validated threshold. It does not define the
asphericity calculation, `xi_c` independently, interpolation/reconstruction
for parcel position and velocity, how many parcels represent each cut
component, or reproducible random seeds.

The enhanced-DPM breakup model reports `We = rho_g U_r^2 d_p / sigma` and a
critical breakup value of 12 (Eq. (10)); child diameters obey
`sum_i d_c,i^3 = d_p^3` (Eq. (11)). Each child gets parent velocity plus a
random normal perturbation (Eqs. (10)–(15), PDF pp. 4–5 / printed pp. 3–4).
Equation (11) and the first child-velocity relation (12) are on PDF p. 4 / printed p. 3; the perturbation relation and pseudocode continue on PDF p. 5 / printed p. 4. The stated equal-volume child diameters conserve parent liquid volume, but
the independent random velocity perturbations have no reported zero-sum
constraint. Thus they do not by themselves guarantee exact vector momentum
conservation during subsequent breakup. The paper gives no momentum residual
for the breakup operation. The transfer claim and the later stochastic
breakup rule must be evaluated as distinct operations.

The carrier-flow momentum equation contains no explicitly reported parcel
feedback/source term; the paper does not say whether the Lagrangian phase is
one-way or two-way coupled. It also does not report evaporation in the
flight calculation: the text says flight mass loss is not modeled, and the
heat model's latent-heat term is not an evaporation model (PDF p. 6 /
printed p. 5, Eqs. (17)–(19) and accompanying text).

## What the validation evidence actually covers

| Study / output | Reported evidence | What it supports and does not support |
|---|---|---|
| Enhanced-DPM front-angle experiment | A `4.0 +/- 0.02 mm` water nozzle, transverse blower flow, Phantom V711 camera at 5000 Hz and 2 us exposure are reported. The numerical particle representation uses six representative `2 mm` droplets. At `26 m/s`, the plotted breakup-DPM front-angle trend is closer to the experiment than fixed-size DPM. | **Measured apparatus description plus a separate DPM comparison**, PDF pp. 6–7 / printed pp. 5–6, Figs. 3–7. It is not VOF validation; the article shows a representative still (Fig. 6) but provides no raw image sequence/video, measurement arrays, quantitative uncertainty, or numerical error statistic. |
| VOF-enhanced-DPM transverse jet | The small VOF case is compared with Li–Soteriou numerical results in Figs. 12–13; the text claims visually matching velocity maps and a `4.5%` maximum boundary error. | **Numerical-to-published-numerical comparison**, PDF pp. 7–9 / printed pp. 6–8. Not a direct comparison with independently reported raw measurements in this article. Fig. 13's 4.5% attribution is unresolved as described above. |
| Ito scaled wind-tunnel example | Table IV gives a prototype row (15 L, `1920 x 640 mm`, 45.2/90 m/s, 30 m) and a `1/16` row (4.2 L, `120 x 40 mm`, 11.3/22.5 m/s, 1.88 m). The paper reports a predicted drop range of 4.5–9.0 m, maximum spread about 0.5 m, slight overestimate for film thicker than 3 mm, and Fig. 18 maximum boundary errors of 20% (lower-speed case) and 10.6% (22.5 m/s case). | **Reported wind-tunnel comparison as reproduced by the paper**, PDF pp. 10–12 / printed pp. 9–11, Table IV and Figs. 17–19. It is one scaled case; raw cup/field data, uncertainty and map-generation details are absent here. The lower speed for the 20% error is printed as 13.3 m/s in prose, versus 11.3 m/s in Table IV and Fig. 17. The geometry is simplified and fuselage-shape effects are neglected. **Calculated scaling check:** the reported 4.2 L is not the geometric volume scale of 15 L at 1/16 length; the paper does not explain its scaling basis. |
| AG600 volume/height/speed sweeps | Table V gives nine cases: 3,330/6,030/12,000 L, a `Time` field of 1 s, flight speeds 150–250 km/h, heights 50–125 m, and outlet areas 1.01/1.82/3.65 m2. Figure 20 shows four tank outlines and labels `1090`, `1360`, `750`, `740`, `2000`, and `140 mm`; Figs. 21–24 show water-depth maps. | **Reported model inputs and DPM numerical results**, PDF pp. 12–16 / printed pp. 11–15, Table V and Figs. 20–24; Fig. 20 is PDF p. 12 / printed p. 11. This section applies enhanced-DPM; it does not resolve AG600 discharge with VOF. Figure 20 is a schematic, not a coordinate-based mesh or outlet specification, and does not map its dimension labels to per-port outlet areas. Outlet histories, split among ports, wind, map resolution, deposition algorithm, escaped mass, and a mass/momentum ledger are not reported. These maps cannot validate L95 or useful fraction under the project definition. |
| Fire-extinguishing evaluation | The article uses empirical density contours at `0.2 L/m2` and `2 L/m2`. Its AG600 heat calculation assumes wood, 600 C initial fire-source temperature, 1 s fire duration, 20 kJ/g average wood heat of combustion, and extinction when the wood surface falls below 100 C. | **Calculated criteria and model assumptions**, PDF pp. 6, 13, 15–16 / printed pp. 5, 12, 14–15, Eqs. (17)–(19), Fig. 24. Eq. (17)'s prose gives latent heat `2.26e6 J/g`; that is a possible 1000-fold unit mismatch, but the source does not resolve whether the unit or exponent is wrong. The paper says in-flight evaporation mass loss is omitted. No fire or post-impact experiment is reported; this is not a measured suppression validation. |

If the Table V `Time=1 s` field is the discharge interval, the table permits
one arithmetic inference, which is **not an explicit inlet boundary
condition**: `volume/(outlet area * 1 s)` is approximately `3.27`,
`3.31`, and `3.29 m/s` for the 3,330/6,030/12,000 L cases (or about
`3.27 m/s` if the first case is 3,300 L). This suggests the tabulated areas
were selected to keep mean discharge speed near 3.3 m/s. It does not establish
a uniform spatial velocity, time history, or four-port split.

The main AG600 model does not report evidence comparable to a measured,
full-scale aircraft drop. The article's data-availability statement is
“available from the corresponding author upon reasonable request” (PDF p. 17
/ printed p. 16); no raw output package accompanies the local PDF.

## Discrepancy and missing-input register

These items were checked against rendered pages, not resolved by assuming an
intended value.

| Issue | Conflicting/absent source statements | Required treatment |
|---|---|---|
| VOF domain and wall coordinate | `30 x 20 x 50 mm3` is called length, width, height, but the no-slip boundary is stated at `y=50`; if `y` is the stated width it is outside the domain. Fig. 8 shows a vertical +y axis, so interpreting the stated height as y=50 mm is plausible; explicit coordinate extents and inlet geometry are still not supplied. (PDF p. 7 / printed p. 6, Section III B and Fig. 8.) | Obtain the original Li–Soteriou case geometry or author clarification before claiming exact reproduction. If proceeding provisionally, name the axis convention and make its alternatives a declared sensitivity. |
| VOF time-step schedule | Text gives `1e-8`–`1e-5 s` and Table II lists `1e-7 s` (PDF p. 8 / printed p. 7). The table value is within the range. | The case's actual time-step history and whether the range is adaptive or a sweep are missing. Do not represent `1e-7 s` as a fully recovered schedule. Use an explicitly declared project time-step/convergence study. |
| Reference for `39 um` mesh | The text calls the `38 um` three-level minimum comparable to and slightly finer than a `39 um` resolution “reported in the literature,” without identifying the cited case at that sentence. (PDF p. 8 / printed p. 7.) | Do not treat `39 um` as a source-identified resolution target until its reference and definition are recovered. |
| Penetration horizon | “Full penetration time” is approximately `2 ms`; the numerical run is reported as `0.1 s`. (PDF p. 8 / printed p. 7.) | Treat as an undefined event/horizon difference until the measured observable and start time are established. |
| Boundary-error claim | Prose attributes `4.5%` to a boundary extracted from literature; Fig. 13 labels the compared lines “Uniform Grid” and “AMR (3 Level)” and marks the gap at their top. A gray data trace is unlabeled. (PDF p. 9 / printed p. 8, Fig. 13 and text.) | Do not use `4.5%` as a validated experiment error or accepted tolerance. Recover the underlying plot/data or keep it as an unresolved author claim. |
| Ito-test velocity | Table IV and Fig. 17 use `11.3 m/s`; the Fig. 18 discussion says the maximum error at the lower speed is at `13.3 m/s`. The higher value is `22.5 m/s` throughout. (PDF pp. 10–12 / printed pp. 9–11.) | Do not silently relabel the `11.3` case. The exact lower-speed condition for the reported 20% error is unresolved. |
| AG600 volume | Table V lists `3,330 L`; text and Fig. 21/24 identify the corresponding case as `3,300 L`. (PDF pp. 12–16 / printed pp. 11–15.) | Preserve both reported values until the authors or source case records resolve them. |
| AG600 height sweep | Text and Table V give `50, 75, 100, 125 m`; Fig. 22 caption gives `50, 100, 150, 200 m`. (PDF pp. 11, 13–14 / printed pp. 10, 12–13.) | Do not digitize the Fig. 22 height axis as if the caption matched Table V. This sweep is not a frozen project reference. |
| Table I units/property | Table I prints surface-tension unit `N/s`, and air viscosity `1.86e-6 Pa s`. (PDF p. 7 / printed p. 6.) | Retain as printed in source transcription; obtain clarification before putting these into a reproducibility input file. |
| Heat-model latent-heat unit | Eq. (17)'s prose prints `Lv=2.26e6 J/g`, while `Cp` is in `J/(g degree C)`. (PDF p. 6 / printed p. 5.) | Preserve the printed value and unit as a possible 1000-fold unit error; do not silently change it to `J/kg` or adjust the exponent. The paper does not state the units used in its calculations. |
| Transfer details | `d_thr`, `xi_c`, shape definition, transfer timing, parcel weights, interface flux residual, momentum mapping, random perturbation coefficient/distribution/seed, and two-way coupling status are not numerically specified. (PDF p. 5 / printed p. 4, Eq. (16), Section II C and Algorithm 1.) | Treat threshold values as missing **production inputs**. `(d_eq,xi)=(0.4 mm,0.5)` is an inferred candidate from Fig. 11(a) and its discussion, not an independently documented production setting; label that inference if used. |
| AG600 flow/ground inputs | No port-by-port flow history, release ramp, wind, ground grid size, parcel count, evaporation loss, map integration method, or exclusive mass compartments are provided. (PDF pp. 11–16 / printed pp. 10–15, Table V and Figs. 20–24.) | A reproduction can only be an explicitly assumed exploratory DPM calculation unless those inputs/data are obtained. |

## Relevance to the current CPU OpenFOAM case

The project case named in this audit assignment is OpenFOAM v2512
`interIsoFoam`, Rouaix geometry with about 10.1 million cells, RANS
realizable-`k-epsilon`, PIMPLE with one outer iteration and three pressure
correctors, `isoAdvection`, Euler time integration, `dt=1e-4 s`, 14–56 mm
cells and no prism layers. The current diagnostics compare GAMG and PCG/DIC
pressure-correction behavior; the evolving run endpoint belongs in
[`docs/STATUS.md`](STATUS.md), not in this paper-source record.

The article is only method-adjacent to that case:

* Its detailed VOF geometry is a 0.8 mm nozzle, versus the 0.4 m Rouaix Case 1
  nozzle. It is not a same-scale or same-geometry reproduction.
* It reports SST `k–omega` and PLIC/geometric reconstruction, while the
  current case uses realizable `k-epsilon` and isoAdvector. Both are VOF
  formulations, but that does not make their alpha advection or pressure
  behavior equivalent.
* It gives no pressure-coupling or linear-solver details. It therefore
  provides no evidence about why the current GAMG corrector fails or whether
  PCG/DIC is a physical/numerical improvement.
* Its printed `1e-7 s` is three orders of magnitude below current `1e-4 s`,
  while its stated range is under-specified. The article's `38 um` minimum
  cell and AMR results do not establish accuracy for the current 14–56 mm
  field or the 0.4 m source. As scale arithmetic only, its 0.8 mm nozzle at
  38 um minimum spacing is about 21 cells across; the current 0.4 m nozzle
  at 14 mm minimum spacing is about 28.6 cells across (and about 7.1 at
  56 mm). This ratio comparison is not a resolution equivalence or accuracy
  result: the geometries, dimensionless conditions, mesh distributions, and
  solvers differ.
* The article says residuals fall below `1e-3`, but it does not identify
  equations, residual normalization, or whether these are linear/nonlinear
  residuals. That reported threshold cannot be mapped directly onto
  OpenFOAM's configured linear-solver tolerances.
* It provides no data for the current Rouaix benchmark and does not validate
  the current 10.1M-cell mesh, boundary conditions, turbulence closure, or
  observed failure mode.

The prior source review of Rouaix Case 1 remains the appropriate quantitative
reference for that large-diameter jet. Shi et al. is potentially valuable for
how a separate **VOF-nearfield / parcel-farfield** method might be qualified;
it does not justify changing the current physics, solver, or numerical
settings.

## Useful nondimensional comparison for VOF work

The small physical nozzle is not by itself a reason to discard this case as a
numerical reference. Using the paper's **nominal table timestep** (not a
recovered time history), the calculated liquid convective increment is
`U_l*dt/D = 17.7*1e-7/0.0008 = 0.0022125`. Our Rouaix reference gives
`10*1e-4/0.4 = 0.0025`. The finest reported nozzle resolution is about
`D/dx_min = 0.0008/38e-6 = 21.1` cells per diameter; our nominal 14 mm target
gives `0.4/0.014 = 28.6` (Rouaix's reported 16 mm value gives 25).
These are calculated numerical-scale comparisons, not convergence evidence.

The horizons are very different in the same units. The reported 0.1 s small-jet
run represents `t*U_l/D = 2212.5`; the reported 2 ms penetration event represents
44.25. Our 0.255 s Rouaix result represents 6.375, while a 5 s target represents
125. A constant 1e-7 s step would require one million steps for the paper's
0.1 s horizon, or 20,000 for 2 ms; these counts are conditional because the
actual reported schedule is unresolved. A small physical domain is therefore
not a reason to skip a measured runtime pilot.

The regimes still differ substantially: Yumeng reports gas Weber number 40
and momentum ratio 88.2, versus Rouaix Case 1's reported roughly 32,000 and
17.3. A small-jet replay can exercise surface tension, geometric phase
transport and adaptive refinement in a complementary regime. It cannot supply
the large-jet breakup curve or justify transferring an absolute timestep,
0.4 mm parcel threshold, or runtime directly.

The reported residual criterion `1e-3` is useful source information, but its
normalization and equation/iteration level are unspecified. It is not directly
equivalent to OpenFOAM's configured `p_rghFinal` linear residual `1e-8`.
A cost/accuracy tolerance sensitivity would require matched fields and ledgers;
the printed number alone does not justify loosening the current pressure solve.

## Proposed tests and gates for the primary agent

These are ordered from lower to higher cost. They are proposals only; no run
was launched and no scientific gate is declared passed by this audit.

1. **Use the existing matched pressure-solver diagnostic as the lowest-cost
   sensitivity.** Keep the Rouaix restart, mesh, fields, timestep, schemes,
   and PIMPLE controls identical; compare the declared GAMG/100-iteration policy with PCG/DIC/1000-iteration policy outcomes
   through the same physical-time endpoint. Do not launch a duplicate while
   this comparison is active. Record pressure iterations/residuals on all
   ranks, continuity and water-phase mass/flux ledger, endpoint fields, CPU
   time and whether `Time` advances. This is a solver-robustness diagnostic,
   not a Yumeng result or validation gate. A pass criterion must require
   equivalent conservation and finite fields as well as completion; the
   paper supplies no pressure-solver criterion.

2. **Prepare a separate provisional VOF diagnostic if useful; recover the original geometry and data before treating it as an exact Yumeng/Li–Soteriou reproduction (moderate-to-high cost).** Missing production inputs do not prevent a clearly labeled idealized smoke test. Freeze the
   reported `0.8 mm`, `17.7/54.8 m/s`, `J=88.2`, `We=40`, properties and
   domain boundaries; explicitly declare the domain-axis convention and
   Table I property notation first. A reported 38 um minimum cell size can
   anchor one mesh, with a predeclared coarser/finer pair. A fixed
   `1e-7 s`/half-step temporal pair would be a proposed test design anchored
   to the printed value, not a recovered paper schedule. Measure actual
   Courant numbers and preserve AMR or a documented static-refinement
   approximation. Compare
   documented normalized jet-boundary and midplane velocity observables
   against source data with independently stated extraction bounds. Do not
   use the paper's 4.5% as the tolerance. Require two finest mesh/time
   levels to meet a case-specific, source-uncertainty-based agreement budget
   frozen before run. Without original Li data or contour definitions, this
   remains exploratory. Start with a bounded short-horizon pilot and measure cost before attempting the paper's expensive 0.1 s horizon.

3. **Qualify transfer separately with an overlap case before using parcels
   for descent (highest architecture value/cost).** First test a saved VOF
   state converted to parcels without advancing physics: exact transferred
   mass, vector momentum, centroid and support must reconcile by interval
   and cumulatively, with released/airborne/transferred/deposited/escaped
   compartments mutually exclusive. Then compare direct-VOF and hybrid
   descent from identical plane data over a handoff-location sweep; accept
   the handoff only when map and `L95` changes stay within a predeclared
   physical/source-uncertainty budget, in addition to approved mass and
   momentum limits. The draft tolerances in `docs/VALIDATION.md` remain
   proposals requiring case-specific acceptance. The Yumeng article's
   qualitative Fig. 11 choice and conservation sentence are not gate limits.

Before Test 2 becomes formal, the minimum missing packet is: the original
Li–Soteriou source definition/arrays, the domain coordinate interpretation,
VOF contour used for Fig. 13, time-step history, and property-unit
disposition. Before Test 3, the project must define the handoff geometry,
parcel weights, velocity/position mapping, random-number handling, carrier
feedback decision, transfer interval and accepted conservation budgets.

## Extraction record

`pdfinfo`, `pdftotext -layout`, and `pdftoppm` were run read-only on the
preserved 17-page PDF. All pages were rendered at 120 dpi; relevant equation,
table, and figure pages were visually checked, including Eqs. (1)–(19),
Tables I–V, Figs. 8–13, and Figs. 17–24. The cited Li–Soteriou DOI resolves
to an AIP page, but the publisher landing page and PDF were inaccessible from
this environment (HTTP 403); no original Li–Soteriou arrays were extracted.
No files in the PDF source or historical run directories were modified.
Rendered pages and extracted text are ignored run artifacts under
`results/runs/yumeng-vof-audit-20261028/`.
