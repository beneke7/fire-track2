# I4F internal-discharge physics review

## Scope and present hardware record

This note covers the pressurized internal discharge apparatus only. The aerial
campaign remains separate. Literature and calculations here do not pass an
I4F validation gate; the geometry and the operating history are still
provisional.

The earlier verbal description from the user was: the vessel is mainly
liquid before charging; an initial gas space may contain oxygen, but the user
is unsure; CO2 is then charged to roughly 8–10 bar and the vessel waits sealed
before discharge. The pressure convention, charge cutoff pressure, pressure
after the sealed wait, initial headspace composition, initial dissolved CO2,
and any dispersed gas in the liquid are unmeasured. A pre-existing foam or
microbubble fraction is **not confirmed**. The current water/air case is a
hydraulic reference, not a prediction of retardant, CO2, or foam behavior.

The 25 October confirmations supersede the older dimensional assumptions:
two tanks, two valve/outlet branches per tank, .900 m tank diameter, .300 m
valve diameter, 1.350 m3 liquid per tank, and additional gas headspace equal to
20–25% of liquid volume. The latest first-pass divider count is four per outlet,
starting roughly halfway through the transition; the earlier count of five is
historical. Pressure is reported as 12 bar with unknown gauge/absolute
convention. The chosen next-case pressures are 12/13 bar absolute. Consult
[the hardware record](../experiments/i4f_hardware_notes_20261024.json) for
provenance and remaining unknowns.

The numerical scale screens below preserve their original 23 October geometry
and inputs. They establish how the cited closures were used, not updated
predictions for the confirmed inventory. The revised network-model results and
CFD preparation are described in [the scientific note](I4F_SCIENTIFIC_NOTE.md).

The calculation bundle is
[`results/runs/i4f-literature-20261023/`](../results/runs/i4f-literature-20261023/).
It preserves the original valve and CO2 papers, inspection images, the
machine-readable valve digitization, and a script/output pair for the
provisional scale screen. It records a hash of
[`experiments/i4f_baseline.json`](../experiments/i4f_baseline.json) at screen
time; preserve that historical bundle and write any rerun with changed inputs
to a new bundle.

## Pressure and discharge closures

The assumed 1.0 m diameter × 2.0 m horizontal cylinder contains 1.571 m³.
At the assumed 70% water fill, water and headspace volumes are 1.100 and
0.471 m³. In the stationary SI frame, `x` is the tank axis and discharge
direction, `z` points upward, and the assumed 0.25 m pipe center is at
`z = 0.65 m`. The 70% level is `z = 1.160 m`, 0.510 m above the pipe center.
The provisional pressure is 9 bar absolute, equivalent to 8 bar gauge only
if ambient is 1 bar. If the user’s 8–10 bar means gauge, the possible initial
absolute range is instead 9–11 bar.

For a sealed gas inventory with no interphase mass transfer, a reduced
first-pass closure is

\[
  p_g V_g^n = p_{g0}V_{g0}^n, \qquad
  T_g/T_{g0}=(V_{g0}/V_g)^{n-1}.
\]

The isothermal limit is `n = 1`; an ideal-gas adiabatic limit uses the gas
heat-capacity ratio. These are sensitivity closures, not fitted I4F values.
At the geometric event where the surface reaches the pipe crown (`z = 0.775 m`),
the single-liquid geometry leaves 0.351 m³, or 31.9% of the initial water, in
the tank. For 9 bara, the fixed-mass gas-law screen gives 3.48 bara at `n=1`,
2.74 bara at `n=1.25`, and 2.64 bara at `n=1.29`. This is not the physical
gas-breakthrough time: free-surface drawdown, vortices, gas ingestion, and
two-phase flow can begin before the crown is exposed.

The fixed-mass law does not apply while CO2 dissolves or exsolves. If pressure
is regulated during the wait or discharge, a mass/energy supply boundary is
needed; maintained pressure is a separate experiment from the user-described
sealed operation. For the CO2 case, the required balances are gas species
moles, dissolved CO2 in liquid, phase-interface transfer, and energy, coupled
to a real-gas mixture EOS. A polytropic law may remain a reduced limit, but it
cannot simultaneously represent a fixed headspace mass and CO2 uptake.

## CO2 capacity and release kinetics

Moreno Soto et al. report Henry form `c(T,P) = k_H(T) P` in Eq. (2.1),
Sec. 2, and saturated ultra-pure degassed water at 20.7 °C containing
15.5 kg/m³ CO2 at a reported 914 kPa. Lowering pressure to 810 kPa produced
about 2 kg/m³ excess dissolved gas (supersaturation 0.14). Each bubble grew
quasi-statically from a deliberately prepared hydrophobic silicon pit; the
paper says growth/detachment takes many minutes. These are direct measurements
and model conditions in [Moreno Soto et al., JFM 831 (2017), 474–490,
doi:10.1017/jfm.2017.623](https://doi.org/10.1017/jfm.2017.623), printed
pp. 475–476, Eq. (2.1), Sec. 2. The article does not clearly label its 914 kPa
as gauge or absolute in that passage; using it as CO2 partial pressure for a
direct Henry comparison is an explicit assumption here.

Using the measured concentration only as a water-like equilibrium-capacity
illustration, the assumed 1.100 m³ liquid could hold about 17.0 kg CO2 at the
reported 914 kPa. The 0.471 m³ headspace at 9 bara would contain about 7.7 kg
CO2 if ideal, or 8.1 kg in the preliminary Peng–Robinson screen. Thus the
measured water capacity near the relevant pressure is larger than the
provisional headspace inventory. This comparison assumes pure CO2, sufficiently
water-like agent, matching CO2 partial pressure, and eventual equilibrium; it
does not say that the I4F solution actually reaches saturation.

For clarity, the evidence bundle also calculates one deliberately conditional
closed-wait case: if 9 bara pure CO2 were isolated in the assumed headspace,
the liquid initially had no dissolved CO2, volumes and temperature stayed
fixed, and the water followed the measured Henry relation, equilibrium falls
to about 2.96 bara. This is an illustration of inventory coupling only. It
does not apply if 9 bara is measured after the sealed wait, if the gas is mixed
with air/O2, if the fluid is retardant with different solubility, if it already
contains CO2, or if charging continues during the wait. A pressure trace from
charge cutoff to discharge and the charged CO2 mass are the minimum data needed
to choose among these states.

Cui et al. directly measured CO2-saturated tap-water degassing at 20 °C. Their
pressures from 0.1 to 2.0 MPa are explicitly **gauge**. Section 2.2 describes
CO2 bubbling into pure water until pH stabilized. Under a rapid full-open
depressurization they observed an initial interval with near-zero void
fraction, so bubbles did not appear instantly. For a controlled slow pressure
drop, Fig. 5 and Eq. (1), printed p. 120, give a required supersaturation drop
of about 0.27 MPa at 1 MPa gauge, asymptoting near 0.35 MPa above 1.5 MPa. Once
that pressure-drop threshold was reached, their Fig. 6 / Eq. (2), printed
pp. 120–121, reports a bubble-formation delay around 10–20 s over 0.1–2.0 MPa
gauge; the exponential delay fit has adjusted `R²=0.5760` (Appendix B, Table 2).
These data show finite nucleation/exsolution delay in their vessel and tap
water. They are not a transferable delay law for a high-shear nozzle: existing
gas nuclei, agent surfactants, roughness, pressure gradients, and mixing may
change it substantially. See [Cui et al., C. R. Géoscience 352 (2020),
115–126, doi:10.5802/crgeos.13](https://doi.org/10.5802/crgeos.13).

The capacity evidence says instantaneous equilibrium is a useful upper
capacity scenario; the degassing evidence says it should not be silently
equated with sub-second release kinetics. The next CO2 model should compare
no-transfer and instantaneous-equilibrium limits, then add finite transfer
only when the real agent, gas fraction, interface area, and a pressure-vs-time
or discharge measurement can constrain it. Unknown retardant rheology and
surface tension prevent treating water properties as foam properties.

For 9–11 bara and 293.15 K, Peng–Robinson gives a screening compressibility
factor of about 0.935–0.947; ideal-gas density is low by roughly 5.6–7.0% in
this screen. This is not a final property package. Use the reference Helmholtz
EOS of [Span & Wagner (1996), doi:10.1063/1.555991](https://doi.org/10.1063/1.555991)
or the newer [NISTIR 8608 (2026)](https://doi.org/10.6028/NIST.IR.8608) for
CO2 density and energy in any quantitative CO2 calculation. For water-only
reference runs, use the IAPWS-95 thermodynamic formulation, R12-08 viscosity,
and R1-76(2014) surface-tension release. The current water inputs describe a
293.15 K hydraulic reference only.

### Matched-inventory CO2 drainage limits

I evaluated two ideal-gas, isothermal limits over the same provisional tank
drawdown, with the same initial CO2 inventory. The source input is Moreno
Soto et al.'s Henry-form Eq. (2.1), Sec. 2, printed pp. 475–476:
`H = 15.5 kg m⁻³ / 914 kPa = 1.6958×10⁻⁵ kg m⁻³ Pa⁻¹`. The cited paragraph
does not make clear whether 914 kPa is gauge or absolute; this screen treats it
as CO2 partial pressure. The source used ultra-pure water at 20.7 °C; transfer
to retardant and 293.15 K is unverified.

The declared starting mixture is 8 bar CO2 partial pressure plus 1 bar air
partial pressure, giving 9 bara total at 293.15 K. The 1 bar air component is a
placeholder for an unknown non-CO2 headspace gas, not a measurement of air or
oxygen. It has constant moles and does not dissolve. The initial liquid is
assumed saturated at the 8 bar CO2 partial pressure, so `c₀=H pCO2,0=13.57
kg m⁻³`. In the same 1.100 m³ water volume and 0.471 m³ headspace, the ideal
CO2 gas mass is 6.807 kg, initial dissolved CO2 is 14.917 kg, and total CO2
inventory is 21.724 kg. Both limits start with exactly these inventories.

For **no transfer**, the headspace gas CO2 mass stays fixed while the initially
saturated dissolved CO2 advects with the liquid at fixed concentration:

\[
p_{CO2}=p_{CO2,0}\frac{V_{g0}}{V_g},\qquad
c_d=c_0,\qquad
M_{escaped}=c_0(V_{l0}-V_l).
\]

For **instant equilibrium**, the remaining liquid concentration follows
`c_d=H pCO2`, and the CO2 inventory inside the tank is
`M=pCO2[Vg/(RCO2 T)+H Vl]`. Using `dM/dt=-c_d Q` and `dVl/dt=-Q`, so the
dissolved CO2 is advected out with the discharged liquid, gives
`dM/dVl=H pCO2` and therefore

\[
\frac{dp_{CO2}}{dV_l}=
\frac{p_{CO2}}{V_g+H R_{CO2}T V_l},\qquad
p_{CO2}(V_l)=p_{CO2,0}
\left(\frac{V_t+(\alpha-1)V_l}
{V_t+(\alpha-1)V_{l0}}\right)^{1/(\alpha-1)},
\quad \alpha=H R_{CO2}T.
\]

Here `RCO2=188.924 J kg⁻¹ K⁻¹`, `T=293.15 K`, and `alpha=0.93921`.
The escaped mass is the volume integral `∫[Vl,Vl0] H pCO2(v) dv`, evaluated
with trapezoidal quadrature over 1,001 samples. Air pressure in both cases is
`p_air=p_air,0 Vg0/Vg`; total pressure is `pCO2+p_air`.

At the single-liquid geometric stop when the free surface reaches the pipe
crown (`Vl=0.35108 m³`, `Vg=1.21971 m³`, 0.74847 m³ released), the matched
screens give:

| Limit | Tank pressure (bara) | CO2 gas (kg) | Dissolved CO2 remaining (kg) | CO2 advected out (kg) | Inventory residual (kg) |
|---|---:|---:|---:|---:|---:|
| No transfer | 3.477 | 6.807 | 4.763 | 10.154 | < 4×10⁻¹⁵ |
| Instant equilibrium | 5.286 | 10.790 | 2.917 | 8.017 | 1.8×10⁻⁷ |

Both have the same starting inventory; the different pressure is due to
equilibrium redistribution plus advective removal, not different charging.
The no-transfer total pressure equals the earlier 9 bara fixed-mass isothermal
headspace result because both gas partial pressures scale inversely with
headspace volume. Instant equilibrium lets CO2 exsolve as pressure falls, while
the lower equilibrium concentration is carried out with the liquid. This is
an inventory bound, not a mass-transfer rate or sub-second discharge forecast.
It assumes a single well-mixed liquid, Henry equilibrium at all times in one
limit, no CO2 transfer in the other, constant temperature, ideal CO2 gas, fixed
tank volume, no external exchange, and the crown event as a comparison stop.
It does not model the actual gas-breakthrough time, bubble nucleation, agent
chemistry, foam, or the uncertain sealed charging history.

The reproducible script and sampled balances are in
[`results/runs/i4f-co2-inventory-limits-20261023/`](../results/runs/i4f-co2-inventory-limits-20261023/):
[`inventory_limits.py`](../results/runs/i4f-co2-inventory-limits-20261023/inventory_limits.py),
[`inventory-limits-summary.json`](../results/runs/i4f-co2-inventory-limits-20261023/inventory-limits-summary.json),
and [`inventory-limits-timeseries.csv`](../results/runs/i4f-co2-inventory-limits-20261023/inventory-limits-timeseries.csv).
The plot is [`co2-inventory-limits.png`](../results/runs/i4f-co2-inventory-limits-20261023/co2-inventory-limits.png).

## Valve, entry, pipe, transition, and lamellae

### Butterfly valve

Ishikawa and Yamashita measured 200 mm butterfly valves. Their Eq. (2), PDF
p. 2 / printed p. 21, defines `K = Δh_v 2g/u_v²` using valve-inlet mean
velocity. The V3–V6 wafer valves have 197.1 mm seats; V3 disc thickness is
47 mm and V6 is 80 mm (Table 1, PDF p. 3 / printed p. 22). Figs. 6 and 9,
PDF p. 4 / printed p. 23, give angle-averaged K values over the measured
Reynolds range. The angle-wise data from those figures are in
[`butterfly-k-theta-v3-v6.json`](../results/runs/i4f-literature-20261023/butterfly-k-theta-v3-v6.json);
the original page and enlarged Fig. 9 / Fig. 10 crops are alongside it.

Digitized values, in the paper’s disc-opening convention where 90° is full
open, are:

| Opening angle | V3 K | V6 K |
|---:|---:|---:|
| 30° | 62 | 44 |
| 40° | 17.5 | 13.7 |
| 45° | 10.3 | 8.3 |
| 50° | 7.2 | 5.3 |
| 60° | 2.63 | 2.74 |
| 70° | 1.12 | 2.02 |
| 80° | 0.71 | 2.37 |
| 90° | 0.67 | 2.71 |

The 30–60° labels are clear; V6's 60–90° labels overlap and are medium
confidence chart reads. The authors shifted V6 data except full-open by +3° in
composite Fig. 10 to account for estimated backlash. The JSON retains both
Fig. 9 source angle and Fig. 10 corrected angle. V3 and V6 cross, so they are
separate geometry scenarios, not universal low/high bounds. The tested body is
200 mm, and expected I4F Reynolds numbers are several million versus roughly
`2e5–8e5` in the paper. Their coefficients are useful sensitivity evidence,
not an I4F valve measurement. Full-open values in those tests are V3 ≈0.67 and
V6 ≈2.71; the scan does **not** support V6=2.02 as its full-open value.

There are no data below 30°. Do not invent a finite `K(theta)` there or
extrapolate the curves to closure. A smooth area/orifice function may be run
as a clearly named surrogate; for the current `Cd=0.7` convention,
`Kopen=1/Cd²=2.04`. That surrogate happens to lie between the tested V3/V6
full-open coefficients but is not an I4F measurement and its time-law is not a
measured butterfly angle curve. If using the published data in a reduced model,
interpolate `log(K)` in opening angle only over 30–90° and state that this is a
numerical interpolation choice. The source provides no actuator
angle-versus-time, minimum gap, or near-closed pressure-loss data.

The occasional `Kopen=0.2` expectation is lower than even the V3 full-open
coefficient and is not supported by these valve geometries. It may still be
possible for a different, more streamlined I4F disk, but remains an unverified
assumption. When the CFD resolves the valve or tank opening geometry, omit the
corresponding scalar loss to avoid double counting.

### Tank entrance, line friction, and transition

Sellevold et al. measured a square-edged inlet in a 375 mm pipe-culvert model.
Their Eq. (1) defines entry loss on barrel velocity; Table 2 gives
`Kentry = 0.50 ± 0.06` for the square edge (`J. Irrigation & Drainage Eng.`
150(2), doi:10.1061/JIDEDH.IRENG-10219). This supports `Kentry≈0.5` as a
provisional analogue for a sharp flush tank opening. It is not the I4F
measurement: their steady culvert setup and 375 mm inlet differ from the
assumed 250 mm tank port. A wider 0.3–0.7 sweep is a chosen stress test, not a
published confidence interval. The CFD geometry should resolve the entrance.

Use Darcy–Weisbach for the straight pipe and the Colebrook turbulent friction
relation ([Colebrook 1939, doi:10.1680/ijoti.1939.13150](https://doi.org/10.1680/ijoti.1939.13150)).
At the initial K-based flows in the bundle, the assumed 10 μm roughness gives
`Re ≈ 5.3–8.1×10⁶` and Darcy `f≈0.0106–0.0108`; the 1 m straight-pipe
coefficient is only about `Kpipe=0.042–0.043`. Roughness and actual length
remain unmeasured.

For the assumed 0.25 m pipe and 0.15 m² outlet, area ratio is 3.056. The
Borda–Carnot abrupt-expansion relation gives `K=(1−Ap/An)²≈0.453` on pipe
velocity; [Iguchi & Omi (1986), doi:10.1299/kikaib.52.3252](https://doi.org/10.1299/kikaib.52.3252)
give it as Eq. (7), printed p. 3254, and report sudden-expansion measurements
within about 7% over their stated area-ratio/Re range (abstract and Sec. 4.2).
This is only an abrupt circular expansion
comparator, not a coefficient or upper bound for the 1.5 m circular-to-
rectangular transition that expands horizontally and contracts vertically.
The current `Ktransition=0.2` is an assumption with no source match; do not
call it measured or validated. The five reported lamellae change the
cross-section and pressure loss. Resolve them when orientation, thickness,
spacing, and outlet reach are known; no-vane and vane cases should be compared
with pressure taps and outlet velocity statistics.

### Plausibility and timescales

The provisional initial driving pressure including hydrostatic head is about
805 kPa. The nozzle area is 3.06 times the pipe area, so the pipe/valve/entry/
transition govern initial flow; prescribing a nozzle-only velocity would
violate the series restriction. With `Kentry=0.5`, the assumed `Ktransition=0.2`,
Colebrook pipe friction, and nozzle exit kinetic energy, the zero-opening-time
full-open screen gives:

| Valve representation | Valve K | Initial Q (m³/s) | Pipe speed (m/s) | Nozzle mean speed (m/s) |
|---|---:|---:|---:|---:|
| V3 full-open analogue | 0.67 | 1.60 | 32.6 | 10.7 |
| current Cd=0.7 surrogate | 2.04 | 1.16 | 23.6 | 7.73 |
| V6 full-open analogue | 2.71 | 1.04 | 21.3 | 6.97 |

These are steady initial-state calculations, not predicted histories. The
source V6 analogue gives about 35% lower flow than V3 at this state; the current
Cd=0.7 surrogate gives about 28% lower flow than V3. Under a fixed open valve and polytropic
headspace with no line inertia, the calculated time to the geometric crown
event is about 0.66–1.13 s across V3/V6 and `n=1–1.29`. This is a diagnostic
lower-complexity screen; the assumed 0.5 s opening time is material. The line
inertial startup time constant is about 0.048–0.073 s for the same cases, while
pipe and transition transit estimates total about 0.12–0.19 s. Actual start and
gas breakthrough need the valve transient and resolved free surface.

At the port, pipe-diameter Froude numbers are about 14–21 and water Weber
numbers are very large. These bulk scales imply inertia dominates gravity and
surface tension inside the line, but they do not predict the gas-ingestion
threshold. The VOF solution should report free-surface depression, gas fraction
at the port and outlet, and time/mass at first sustained gas passage; compare
that event with the reduced model’s crown stop.

## Solver suitability and advancement criteria

The official OpenFOAM source description for
[`compressibleInterFoam`](https://api.openfoam.com/2312/compressibleInterFoam_8C.html)
is a two-compressible-fluid, non-isothermal VOF formulation. This is a
reasonable candidate for the **water/air hydraulic reference** if its gas
thermo and energy closure are checked in the installed version. `interFoam`
is documented as incompressible and is not an adequate headspace blowdown
model by itself.

CO2 and exterior air are miscible gases. A water-versus-single-gas VOF solver
with fixed gas properties cannot model changing CO2/air composition, CO2
dissolved in liquid, or finite dissolution/exsolution just by declaring an
extra gas VOF phase. A CO2 case needs a gas-mixture species equation/EOS,
liquid dissolved-gas inventory, interfacial transfer/nucleation closure, and
energy accounting; dispersed pre-existing bubbles would require a resolved
microbubble mesh or a separate validated population/Euler–Euler closure. Until
the installed solver supports and verifies these terms, keep air-headspace
CFD clearly labelled as hydraulic reference and do not interpret it as actual
CO2-retardant prediction.

Before a quantitative actual-discharge claim, obtain: pressure absolute/gauge
and time trace through charge cutoff, sealed wait and release; charged CO2 mass
and whether a regulator stays connected; liquid/retardant composition,
density, rheology, surface tension, dissolved CO2 and gas fraction; valve
geometry plus angle/time or a pressure-flow trace through startup and near
closure; tank fill/orientation and pipe entry dimensions; full transition,
lamella and outlet geometry; and a synchronized discharge mass/flow or pressure
record. In the meantime, preserve separate water/air hydraulic, sealed fixed-
gas, no-transfer CO2, and equilibrium-Henry sensitivity cases. Advance a CO2
model only after its species/mass-transfer balances and real-gas limit are
verified against the primary dissolution/degassing evidence above.

## Source index

- Ishikawa, T. & Yamashita, T. (1985), valve Eq. (2), PDF p. 2 / printed p. 21;
  Table 1, PDF p. 3 / printed p. 22; Figs. 6, 9–10, PDF p. 4 / printed
  p. 23. DOI: [10.5988/jime1966.20.20](https://doi.org/10.5988/jime1966.20.20).
- Moreno Soto, A. et al. (2017), Henry law Eq. (2.1), Sec. 2, printed
  pp. 475–476. DOI: [10.1017/jfm.2017.623](https://doi.org/10.1017/jfm.2017.623).
- Cui, Z. et al. (2020), experiment Sec. 2.2; supersaturation Fig. 5/Eq. (1),
  time delay Fig. 6/Eq. (2), printed pp. 119–121; fit uncertainty Appendix B,
  Table 2. DOI: [10.5802/crgeos.13](https://doi.org/10.5802/crgeos.13).
- Sellevold, J. et al. (2024), inlet energy-loss Eq. (1), Table 2 and
  experimental setup. DOI:
  [10.1061/JIDEDH.IRENG-10219](https://doi.org/10.1061/JIDEDH.IRENG-10219).
- Iguchi, M. & Omi, M. (1986), Eq. (7) abrupt-expansion Borda–Carnot relation
  and measurements, printed p. 3254, Sec. 4.2. DOI:
  [10.1299/kikaib.52.3252](https://doi.org/10.1299/kikaib.52.3252).
- Colebrook, C. F. (1939), turbulent pipe friction relation and smooth/rough
  transition, pp. 139–141. DOI:
  [10.1680/ijoti.1939.13150](https://doi.org/10.1680/ijoti.1939.13150).
- Span, R. & Wagner, W. (1996), CO2 reference Helmholtz EOS. DOI:
  [10.1063/1.555991](https://doi.org/10.1063/1.555991).
- IAPWS R6-95(2018) thermodynamics, [R12-08 viscosity](https://www.iapws.org/relguide/viscosity.html),
  and [R1-76(2014) water surface tension](https://iapws.org/technical-guidance/release/Surf-H2O).
  R1-76 Table 1 gives 72.74 ± 0.36 mN/m at 20 °C; R12-08 p. 4 states the
  formulation reproduces the 20 °C viscosity reference within 0.17%.
- Official OpenFOAM 2312 API description:
  [`compressibleInterFoam`](https://api.openfoam.com/2312/compressibleInterFoam_8C.html)
  and [standard solver capabilities](https://www.openfoam.com/documentation/user-guide/a-reference/a.1-standard-solvers).

## Early headspace-gas connection in the saved pilot

The exact saved frame at `t = 0.34232644 s` shows a headspace-connected gas
core descending as a nearly symmetric V-shaped surface funnel to the upper lip
of the horizontal pipe (`z = 0.775 m`). The native mesh connectivity diagnostic
finds one connected component at `alpha.water <= 0.01` from the headspace seed
to the pipe-mouth seed. At the same time, the sampled tank free-surface level
at `x = 1.5 m` is `z = 1.05752 m`, still 0.28252 m (`1.13D`) above the pipe
crown and 0.40752 m (`1.63D`) above the pipe center. The tank-zone liquid
volume fell from 1.08770064 to 0.97000227 m³. The frame therefore records a
0.11770 m³ drawdown, about 16% of the current flat-level reduced reference's
0.748 m³ drawdown to crown (reported stop time about 1.23 s). This local path
appears well before the flat-level crown stop; it does not establish a physical
gas-breakthrough prediction. The image shows a center-plane and cross sections,
with thresholded native-cell classification and interpolated contours: [saved connection diagnostic](../results/runs/i4f-visual-20261023T215734Z/frames/connection-gas-ingress-00000-t-0.34232644s.png).

The interface has a symmetric drawdown shape in this view. No angular velocity
or sign-coherent circulation has been demonstrated, so call it a **connected
headspace-gas funnel** or **local free-surface drawdown** for now, not a vortex.
A center-plane image cannot rule out three-dimensional circulation. Compute a
3D velocity/circulation measure around the core before assigning a vortex
mechanism. The gas connectivity is a single `alpha.water <= 0.01` threshold
diagnostic on the 146,354-cell mesh; 1,435 concave cells remain, and the
642,480-cell mesh and time-step sensitivity have not yet established event
robustness. The reported 117 m/s point is at `alpha.water ≈ 10⁻⁴`, around
6 bar and 280 K; it is a local low-water-fraction velocity, not a bulk gas flow
measurement.

Horizontal-intake experiments offer useful geometric context. [Taştan's 2020
horizontal-pipe study](https://doi.org/10.1016/j.asej.2020.02.010) says air
enters a horizontal intake at the crown and
defines center submergence as the crown distance plus `0.5D` (Fig. 1, Sec. 1,
printed p. 933). Its Eq. (1), p. 933, is the generic empirical relation
`Sc/D = m + n F^a`; the coefficients depend on the conditions of each
experiment. Its Sec. 2, pp. 934–936, treats a horizontal pipe at a dead-end
wall and compiles studies without imposed approach circulation; it also
explains that boundary friction changes the critical-sink flow and can make a
naive potential-flow estimate overpredict submergence. Göğüş and Köken's
2016 experiment directly studied horizontal reservoir-wall pipes with no
approach-flow-induced circulation, varying pipe diameter, discharge and side
wall clearances (publisher abstract, *Journal of Hydrodynamics* 28(1),
102–113, [doi:10.1016/S1001-6058(16)60612-1](https://doi.org/10.1016/S1001-6058(16)60612-1)). Anwar et al.'s horizontal-intake tests report that a bellmouth did not improve performance while flush mounting at the boundary did
(*Journal of Hydraulic Research* 16(2), 95–105,
[doi:10.1080/00221687809499623](https://doi.org/10.1080/00221687809499623)).

The horizontal pipe and flush tank-wall geometry make these sources useful
comparators. Their correlations are **not** a closure for this event: they
define incipient air ingestion from a free-surface vortex in an open reservoir
under controlled or quasi-steady intake flow. Here the gas is the pressurized
headspace, the free surface is moving rapidly, the valve and liquid column are
transient, and the 3D swirl state is unknown. The geometric ratios and intake
Froude number can be reported as diagnostics, but do not use a published
`Sc(F)` fit to predict this breakthrough or tune a numerical threshold to it.

For the saved interval, tank drawdown gives `Q̄ = 0.34383 m³/s`, hence
equivalent full-bore `Ūpipe = 7.004 m/s`, `Re_D = 1.744×10⁶`,
`Fr_D = 4.473`, and water `We_D = 1.682×10⁵`. These use the
interval-averaged flow derived from the saved tank-zone volume and the
provisional 0.25 m port. They are not
instantaneous intake values for an unsteady vortex correlation. A dry-air
ideal sound-speed estimate at 280 K gives `a ≈ 335.4 m/s`, so the reported
local gas speed has `Ma ≈ 0.349`. Acoustic travel takes about 0.0030 s across
1 m and 0.0060 s along the 2 m tank. In contrast, `sqrt(D/g) = 0.160 s`,
`sqrt(Dtank/g) = 0.319 s`, and the mean-level-to-crown gravity time
`sqrt(0.2825/g) = 0.170 s`. The configured 0.5 s valve stroke is about
3.5 pipe transit times (`1 m/Ū = 0.143 s`) and 1.15 estimated transition
transit times (`0.434 s` for linearly varying area at `Q̄`). This ordering
allows quick acoustic pressure communication but leaves gravity-driven
interface response and liquid-line inertia on the valve-opening timescale; a
quasi-steady water-flow assumption is not supported by these ratios.

For thermal scaling, Prusa's dry-gas water-rocket model uses a thermal
diffusivity near `10⁻⁵ m²/s` and an adiabatic law when heat diffusion is slow
(Eq. (2.8), printed p. 722, [doi:10.1137/S0036144598348223](https://doi.org/10.1137/S0036144598348223)). Gommes gives `δh² ≈ χt` and
`χ = 0.014 cm²/s = 1.4×10⁻⁶ m²/s` (Sec. II.A, Eq. (1), printed p. 237).
These cited air diffusivities differ by about a factor of seven; I retain both
source values rather than reconcile them without property conditions. At
0.342 s they yield only about 1.85 mm and 0.69 mm of conduction depth. Over a
0.5 m gas scale, their conduction times are about
25,000 s and 179,000 s. Bulk headspace conduction is therefore slow on this
event timescale, but wall/water convection and phase change are not captured
by that estimate. Gommes shows that humid-air condensation changes the
adiabatic pressure-volume path; the dry `γ = 1.4` law is a limit, not a
universal headspace closure. The rocket paper's moving-frame acceleration
terms and quasi-steady nozzle relation do not apply to the stationary I4F
tank. The full source PDFs, extracted equations, locations and direct URLs are
recorded in [`results/runs/i4f-free-surface-sources-20261023/SOURCES.md`](../results/runs/i4f-free-surface-sources-20261023/SOURCES.md).

The clean next hypothesis comparison is a matched pair with fixed geometry and
initial inventories: 0.5 s and 1.0 s smoothstep strokes on the same
642,480-cell mesh and time controls, after the current numerical robustness
checks. Define onset as the first sustained, headspace-connected gas mass flux
across a plane at the pipe mouth; set its noise floor and persistence using
the numerical robustness runs, rather than a chosen `alpha.water` threshold.
Record the onset clock time **and remaining tank-water volume**, sampled and
local free-surface height, headspace pressure/temperature, pipe-mouth
connected-gas volume/flux, and 3D circulation around the core. If the slower
stroke reduces gas flux and delays connection at the same remaining water
volume, local flow-induced drawdown contributes materially; if onset follows
nearly the same local crown-interface contact in both runs,
geometry-dominated interface reach is a stronger explanation. Cell
connectivity alone remains a numerical diagnostic until mesh, time-step and
alpha-threshold sensitivity are checked.
