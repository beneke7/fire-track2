# Pressure-driven I4F discharge: working scientific note

26 October 2026 UTC. Working scientific note with executed exploratory results;
no apparatus validation is claimed. Dimensions are distinguished as user-reported,
derived or assumed below; the CAD is not a calibrated dimensional measurement.
[The shared input](../experiments/i4f_baseline.json)
describes the earlier frozen exploratory single-outlet CFD reference; the later
two- and four-outlet cases use their own immutable run inputs and geometry records.
The later maker notes and original STEP/photo are preserved separately in
`experiments/i4f_hardware_notes_20261024.json`; their provisional two-tank,
four-mouth reconstruction must not be confused with the earlier single-outlet
CFD. Those executed references model one provisional tank and its two outlets;
the new hardware case includes both tanks and all four outlets.

## Current scientific result

**Latest outcome:** no complete credible tank-to-nozzle discharge exists yet.
The source-consistency investigation now provides a specific discrete error
mechanism, but correcting it has not cured the pressure cycle. The complete
Sp+divU warm trial stopped at .494130 s with 1261.902 Pa and 5.520 m/s final
outer updates, zero raw floor contacts, and a complete checkpoint. The Sp-only
trial stopped at .494225 s. These are effectively the same stopping window;
better intermediate water balance did not supply a stable discharge. The matched
warm upwind baseline stopped at .481894 s; caching its predictor Sp continued
to .494225 s without floor contact, then also stopped on persistent pressure
updates. At approximately .480 s, its post-EOS water-continuity volume-L1
residual fell from 1.527 to .387 kg/s and its accumulated water defect since
the common .460048 s seed fell from .01181 to .00463 kg. Actual sample times
differ by .119 microseconds; these are nearest-sample comparisons, not
identical-time fields or a proof of physical phase-mass conservation.

The predictor/corrector equations explain the targeted numerical change.
For this static Euler, single alpha-correction/subcycle configuration, let
alphaP denote the implicit predictor, alphaF the corrected fraction, d0 its
cached divU, Sp0/Su0 its cached source coefficients, and Spc the coefficient
passed to MULES. Adding the two discrete equations gives

```text
D_t alphaF + div(PhiF)
  = Su0 + Sp0*alphaF + d0*alphaP + (Spc-Sp0)*(alphaF-alphaP).
```

Here PhiF is the actual corrected phase-volume flux. In one recurrent cell
on the positive half of the observed pressure cycle, the last term times
water density predicts 22,234.13 kg/m3/s, versus a measured post-EOS local
water residual of 22,166.81 kg/m3/s (0.304% relative difference). Other cells
do not share this agreement: this is evidence for a particular local error
contribution, not a global explanation or a fitted correction. Caching Sp0
removes that term but leaves d0*(alphaP-alphaF) relative to a fully implicit
cached source. The new exploratory prototype uses C0=Sp0+d0 in MULES, with
Su=-C0*alphaP, and measures the resulting full discrete-alpha residual.
It forbids previous-correction reuse and requires global min(1/dt-C0)>0;
it does not clip coefficients. Independent equation review and a ten-step
byte-identical default-off check support testing it, not adopting it as a
validated solver. A separate uninterrupted cold upwind/cached-Sp candidate
tests whether this combination survives without the intermediate restart;
it changes both momentum transport and source handling relative to the original
cold reference and is not a one-factor causal comparison. The
[source-cycle evidence packet](../results/summaries/i4f_20261025/pressure-source-cycle/summary.json)
includes the same-cell pressure trace, local arithmetic, full distribution of
observed ratios, source patches and nearest-sample comparisons.
Current execution and evidence paths belong in [live status](STATUS.md).

Other completed discriminators narrow the next action. Sixteen rather than
eight outer iterations, nontransonic pressure linearization, and a tighter
temperature solve retained the warm pressure cycle. A 25-microsecond maximum
timestep warm restart failed after only .425 ms with a raw pressure-floor
contact; this is not a cold timestep-convergence result. A separate periodic
6,400-cell translating water/air slab completed .1 s/1000 steps with uniform
p/U/T errors of 7.20e-9 Pa / 4.27e-12 m/s / 2.01e-11 K. Its public launcher
reproduced that result. Uniform equilibrium does not excite the apparatus's
compression sources, so this limited verification does not clear the tank.

A separate [source-active sealed-channel study](../results/summaries/i4f_20261025/source-active-withdrawal/README.md)
now compares cached Sp and cached Sp+divU on 60/120/240/480 axial cells.
Each case starts with 80 mL water and 20 mL air at 1.2 MPa and 293.15 K,
and completes .4 s/1600 fixed steps. Constant-density water, laminar flow and
Pr=1e9 deliberately separate this test from the apparatus's finite-water EOS,
SST and heat transport. With the full coefficient, same-volume adiabatic
pressure errors decrease from 1.930% to 1.288% to .878% on the three finest
meshes; temperature errors are 1.914%, 1.272% and .861%. These are refinement
trends, not a demonstrated asymptotic order, GCI or apparatus validation.
The source change leaves these thermal errors almost unchanged and slightly
increases gas-mass drift, while reducing normalized water-volume balance error
from roughly 2e-5 to at most 5.32e-11 of initial water volume in this study.
Thus improved water balance does not establish a closed gas-energy model.
An additional n=120 read-only audit reproduces identical native endpoint fields
and finds corrected-minus-predictor alpha-equation residual below 9.21e-13 s^-1.
The [inspected figure](../results/summaries/i4f_20261025/source-active-withdrawal/grid-trend.png)
and SI data preserve both effects. The much larger alpha residual in the tank
motivates the next controlled predictor linear-tolerance test; its outcome
remains unknown.

The earlier finite-water cold test contacted the pressure floor:
one pass at .409998 s reached -308.269 Pa in two cells. It saved all fields at
.410223 s; final minimum pressure recovered to 85.499 kPa and the pressure
update to .160 Pa, but this does not undo the floor event. Liquid support in
the affected cells was .019267 kg, not removed water mass. The uninterrupted
standard-source constant-density cold control ended at .434532 s after eighteen
raw pressure-floor contacts. A warm upwind fork from a .400020 s state saved
.460048 s with no pressure-floor contacts, but its continuation stopped at
.481894 s with a persistent 300.719 Pa pressure update and no floor contacts.
This is evidence of sensitivity to momentum transport, not a remedy.
The smaller-timestep finite-water cold comparison also stopped, at .383069 s,
after a +677.757 Pa raw minimum below the configured 10 kPa floor. Neither
trajectory establishes a complete credible discharge.

As of 26 October, the corrected-junction constant-density cold trajectory
reached a raw pressure-floor failure at .434224 s after an operational restart
from .413689 s. Two intermediate pressure corrections alternated between
positive pressure and negative pressure down to -330.889 kPa. Reducing the
pressure correctors from two to one avoided floor contact in that short trial
but stopped at .440686 s with persistent 7.78 kPa pressure and 8.10 m/s velocity
updates. The tank-interface-refined case similarly stopped at .445301 s with
3.00 kPa pressure updates. These are unresolved numerical failures, not physical
cavitation or trustworthy discharge results.

The finite-water case uses the explicitly provisional
[finite-compressibility water packet](../experiments/i4f_physical_water_eos_reference/i4f-physical-water-eos-reference.json).
Its reference sound speed is 1482.344 m/s at 293.15 K and 0.1 MPa, evaluated
from the linked IAPWS release. The assumed pressure exponent 7.15 is not Cp/Cv;
the barotropic water law with constant heat capacity is neither full IAPWS
thermodynamics nor a validated high-pressure material description. The EOS
increases initial water mass by 1.6063 kg at the matched volume. Its first
timestep setting did not resolve the floor event. The completed smaller-timestep
run continued from its .0500106 s cold pilot, while the stock-upwind probe
was a separate warm-start sensitivity. Current execution and deadlines are in
[live status](STATUS.md); do not conflate these paths or call either a validation.

The [guard-parser repair evidence](../results/summaries/i4f_20261025/parser-merge-replay.json)
recovers an MPI-interleaved terminal record without changing the equations or
health thresholds. Its full-log replay parses all 1,644 completed steps.
One recovered step still had a 3.45 kPa outer update, so successful parsing does
not establish nonlinear convergence. Native outlet postprocessing now supports
phase-water density from either selected EOS; native water-volume flux remains
primary, while mass and momentum reconstructed from separately saved fields
retain their stage-matching qualification.

A matched **audit-output-only** pair ended at .401007658722 s after seven steps.
All fourteen native fields plus `uniform/time` and the step-health rows were
byte-identical with `i4fFullPressureAudit` on/off; the outputs are separate
files. Solver ClockTime was 51 s on and 42 s off in this one sequential pair.
That is a single short timing observation, not a general speedup or physics
result. The [exact-byte proof](../results/summaries/i4f_20261025/pressure-audit-toggle/exact-byte-proof.json)
and [captured profile](../results/summaries/i4f_20261025/pressure-audit-toggle/profile-window-result-v2.json)
retain both run identities and hashes. Future child helpers disable only this
detailed audit stream; the warm continuation used the setting. Earlier
stages remain preserved with their original controls.

The latest user confirmation changes the physical baseline: the passages
downstream of the valves initially contain air. Earlier liquid-filled-line
calculations below are conditional initial-state/numerical evidence, not the
confirmed hardware startup. A new compact case initializes downstream air at
ambient pressure, while accounting separately for tank water and the wetted
tank-to-valve passages. The effective initial valve plane remains an assumed
representation of the distributed scalar restriction. The earlier fully
wetted reduced model does not describe this line-filling transient. The new
[earlier moving-front model](../results/summaries/i4f_20261025/air-filled-moving-front-model.json)
includes liquid inertia and downstream filling. The
[updated compact-geometry comparison](../results/summaries/i4f_20261025/flush-filling-model-comparison.json)
uses the corrected junction's native tank/headspace state and direct compact
centerlines. Adiabatic air gives mouth-water arrival near .617/.625 s; an
isothermal assumption gives .585/.591 s. Their mean-level intake-crown endpoints
are 1.127/.970 s, respectively, not emptying times or established gas breakthrough.
Halving the adiabatic-model timestep changes arrivals by 25 microseconds. The
model retains .634% more wet-feed volume and 2.081% more full-line volume than
the native Tank-A zones; these differences are exposed rather than fitted away.
The [thermal sensitivity plot](../results/summaries/i4f_20261025/flush-filling-model-thermo-sensitivity.png)
shows assumed gas-law sensitivity, not measured heat transfer or CFD validation.
The single full-bore front, ambient front pressure, approximate lamella friction
and unknown dry-air minor losses remain material limitations.

The [corrected-CFD startup comparison](../results/summaries/i4f_20261025/flush-early-cfd-model-comparison.json)
uses complete native checkpoints through .250021 s. Mean tank withdrawal is
62.581 L versus 62.210 L in the adiabatic reduced model (+.597%); mean per-tank
two-valve flow is .608803 versus .604200 m3/s (+.762%). Mean local headspace
probe pressure is 946.934 kPa versus bulk model 920.654 kPa, while the isothermal
model gives 989.501 kPa. This is early consistency with distinct pressure
observables and uncalibrated closures, not validation or a rigorous thermal
envelope. Tank/line volumes and valve fluxes use exact saved scalar rows;
probe p/T uses bracket interpolation with targets within about four nanoseconds
of the upper printed sample. Model values are bracket-interpolated without
extrapolation. The [plot](../results/summaries/i4f_20261025/flush-early-cfd-model-comparison.png)
keeps each tank separate and shows the .10–.25 s window only.

The [sealed-gas tank-to-nozzle reference](../results/summaries/i4f_20261025/sealed-gas-pressure-budget/pressure-budget.json)
provides a conditional quasistatic pressure scale for the 1.0 m and 0.8 m
transition variants. With 12 bar absolute, 22.5% headspace and n=1.4, full-bore
priming leaves about 3.478/3.771 bar absolute. The ideal sealed-gas relation
then reaches the 1 bar back pressure after approximately 1.056/1.098 m3 of
nozzle-delivered water per tank. These are pressure-equalization volumes, not
maximum delivery or emptying predictions: inertia and elevation can sustain
flow, while valve/pipe losses and initial-air purge dynamics are not resolved.
At the nominal .225 headspace, the n=1 isothermal limit stays above 1 bar over
the listed liquid inventory. The
0.8 m geometry reduces initial downstream gas storage by 41.335 L per tank,
but no CFD discharge advantage has been shown. Headspace sensitivity holds
water fixed, so tank capacity also varies; pressure and gas-law inputs are
assumptions, not values inferred from a CFD probe. The
[plot](../results/summaries/i4f_20261025/sealed-gas-pressure-budget/pressure-budget.png)
shows the below-back-pressure formula extension separately from its
pressure-supported part; the [recoverable source snapshot and hashes](../results/summaries/i4f_20261025/sealed-gas-pressure-budget/provenance/publication-package.json)
record the generated reference inputs.

User clarification on 25 October establishes two tanks, two valves/outlets per
tank, .900 m tank diameter, .300 m valve diameter, and 1.350 m3 liquid per tank.
Additional gas headspace is .20–.25 times liquid volume, giving nominal vessel
capacity 1.620–1.6875 m3. Four equally spaced lamellae starting halfway through
the transition are the next first-pass description. Roughly five seconds is
reported discharge duration; valve actuation remains unspecified. The next
hydraulic reference uses 12 bar absolute with 13 bar absolute sensitivity,
because the user did not specify gauge versus absolute pressure. These are
reported/derived inputs and declared scenarios, not new measurements. They are
preserved in [the hardware record](../experiments/i4f_hardware_notes_20261024.json).
Historical one-tank calculations retain their original 9 bar, larger-headspace,
no-lamella inputs and must not be presented as this revised hardware case.

The earlier compact air-filled CFD cases have 279,536 and 299,248 cells,
with 12.5 and 6.25 mm axial spacing specifically through the .30 m valve-loss
reach. These are local source refinements, not those spacings everywhere.
All nine configured mesh-quality criteria pass. Each tank initially contains
1.350 m3 water, with another .25106/.25111 m3 in its wetted upstream feeds;
downstream air starts at 100 kPa. A scalar restriction predicts discharge
rather than prescribing an outlet history. It does not resolve the butterfly
disk wake or CO2/retardant behavior.

The static wall audit found an approximately 18.5 mm shoulder near x=3.911 m
in both older meshes. It originates in the generated pipe/transition union:
the round pipe extends into the contracting loft. The opt-in flush junction
removes this reconstruction artifact at all four branches while preserving
the CAD tank capacity and feed intersections. The summed branch-volume change
is -1.012 L downstream of the valves; under the confirmed dry startup it changes
ambient-air storage. The [matched geometry sections](../results/summaries/i4f_20261025/pipe-transition-join-comparison.png)
and [record](../results/summaries/i4f_20261025/pipe-transition-join-summary.json)
establish a geometry correction, not its role in the pressure failures or a CFD
improvement. The earlier 299,214-cell corrected-junction cold trajectory used the standard
phase-source update and subsequently failed as described above. The older
881,431-cell bend/outlet refinement retained the overlapping geometry and frozen
source; it stopped at .396175 s on the persistent-update screen. These cases
must not be interpreted as a single-factor comparison.

At matched .050021 s, the finer corrected-source case withdraws 4.59423 L
from tank A, compared with a bracket-interpolated moving-front result of
4.57287 L and 6.54699 L in the original partly wetted-source case. The
[comparison figure](../results/summaries/i4f_20261025/air-filled-drawdown-source-grid.png)
and [native axial histories](../results/summaries/i4f_20261025/air-filled-valve-band-axial-comparison.json)
support a substantial numerical contribution to the early mismatch without
fitting Cd. The unchanged 2% pointwise axial screen remains HOLD: the first
two timesteps differ by up to 5.12%, while endpoint flow differs about 1.50%.
The reduced model has .634% more initial wet-feed volume, so even close early
agreement is a consistency check rather than independent validation.

Long continuations of the corrected-source meshes target the useful
discharge interval; a complete verified discharge has not yet finished.
The finer reference saved at .443669 s when pressure corrections stopped
settling between outer iterations: the last correction was 3291 Pa and
the velocity update 4.54 m/s, despite positive pressure and no clipping.
This is a diagnostic stop, not evidence of a converged discharge. A restart
from the clean .400087 s checkpoint reproduced the condition at .443925 s;
the 24-layer source-resolution comparison stopped at .442746 s. Both saved
all restart fields with positive pressure and no clipping. The smaller-Courant
trial instead encountered a raw intermediate pressure of 2698 Pa and saved
at .410422 s; the final saved pressure does not replace that raw observation.
Disabling the transonic pressure Jacobian and relaxing the pressure-component
matrices by .5 also retained the alternating outer pressure updates, stopping
near .443765 and .443685 s respectively without pressure clipping. These
one-factor tests do not establish a remedy. A cell-localized trace places the
later cycle in mixed transition cells; source-lag observations alone do not
establish its cause. No completed-discharge or late mesh-convergence claim follows.
One non-orthogonal correction also stops at .443765 s with a persistent
3.56 kPa update. Momentum equation relaxation .5 instead reaches raw negative
pressures, as low as -127.21 kPa, and saves at .410704 s. Restoring the stock
MULES source update from the common .400087 s restart encounters a raw 6.380 kPa
cell and saves at .410533 s. These are separate failures, despite normal End
and positive final saved pressures. The stock restart inherits the frozen-source
trajectory; it does not test a stock calculation from the confirmed cold state.
The earlier air-filled original-source case saved at .392 s after a raw
pressure-floor event. A short restart passed .395 s without reproducing it;
original and diagnostic binaries produce identical short-restart results.
The cause of that earlier event remains unresolved. Current execution belongs
in [STATUS](STATUS.md), not in a completed-discharge claim.

The next numerical comparisons separate two mechanisms. Repeated pressure
solutions update the explicit non-orthogonal Laplacian correction, as described
in the [OpenFOAM tutorial](https://www.openfoam.com/documentation/tutorial-guide/2-incompressible-flow/2.2-flow-around-a-cylinder).
Momentum equation relaxation changes the iteration matrix and source; its
effect must vanish at a converged fixed point before interpreting an unchanged
governing equation. The [current OpenCFD explanation](https://doc.openfoam.com/2606/tools/processing/numerics/solvers/under-relaxation/)
also distinguishes an absent relaxation entry from factor one, which can enforce
diagonal equality. The installed v2512 source, rather than documentation for a
different release, remains the execution authority. A separate finer-tank
calculation retains the original numerical settings to isolate mesh sensitivity.
The current [phase-source fork](../solvers/i4f_frozen_sp/applications/solvers/multiphase/VoF/alphaEqn.H)
retains the stock predictor but uses its captured `Sp` in the MULES correction
instead of recomputing that coefficient. Its earlier comparison used a primed
one-tank case. The current flag-off restart above adds a matched-state source
sensitivity; a separate true-cold standard-source trajectory now supplies the
[comparison through .4 s](../results/summaries/i4f_20261025/stock-frozen-source-comparison.json).
Nearest scalar rows differ by 3.0 and 34.5 microseconds at the .35/.4 s targets.
Valve-seat water fluxes differ by at most .00531%/.00236%, and headspace probe
pressure by about 131/164 Pa. Initial fields and mesh match; diagnostic binaries
differ. No interpolation or exact-common-time error claim is made.

That true-cold case also stops numerically: at .41005436428 s, two intermediate
pressure solves reach -9.095 and -80.959 kPa in nearly pure-water cells around
x=3.436904 m. The [contact review](../results/summaries/i4f_20261025/stock-cold-pressure-contact-review.json)
reconciles all fourteen affected-cell records. Its saved .410269 s endpoint is
complete, but the .46 s target is unachieved; the later positive pressure does
not erase those contacts. Changing the source update alone has not removed the
problem. The corrected 299,214-cell flush-junction case has completed clean
.05 s startup and is continuing toward .46/1.3 s, while the older bend-refinement
case remains active. Neither supplies a complete verified discharge yet.
No new production phase-source equation correction is adopted.

The [corrected raw-contact analysis](../results/summaries/i4f_20261025/pressure-contact-review.json)
recovers the actual rank-prefixed cell records already present in the logs;
the earlier parser had missed them. Momentum relaxation's worst raw minimum
is rank 0/cell 7902 at (3.436916, .736759, .964727) m with alpha_water=.999706.
The stock-restart event is nearby cell 7966 with alpha_water=.9999999986.
All affected-cell records reconcile with the global minima and printed counts;
none were omitted. These are intermediate pressure solves, not evidence of
physical cavitation. Their liquid-support mass is not mass removed by clipping.
The CSV publication corrects the legacy psi column labels: OpenFOAM psi is
d(rho)/dp in kg m^-3 Pa^-1; the storage coefficient alpha*psi/rho is in Pa^-1.
Logged gas density and psi precede the EOS update and must not be recomputed
from the raw negative pressure when interpreting that matrix.

Small bulk liquid-density change alone cannot dismiss liquid compressibility
in nearly pure-water cells. At the stock raw minimum, logged gas storage is
5.30e-15 Pa^-1; an illustrative water sound speed of 1500 m/s would add
4.45e-10 Pa^-1. That conditional model could affect the nearly pure-water
event, while contributing very little to the later alpha_water~.69 cycle.
The retained earlier Tait-type restart delayed but did not remove clipping;
this is a hypothesis, not a demonstrated correction. A physical cavitation
claim would require settled native pressure and acceleration/curvature evidence,
rather than an alternating pressure-iteration minimum.

The saved .350114 and .400087 s corrected-source fields locate the coldest
cells in tank gas, at 255.02 and 245.66 K. The lowest pressures instead occur
in the lines, at 96.84 and 92.58 kPa absolute and approximately 293 K. At
.400087 s, whole-tank gas-mass-weighted temperature is about 261.21 K, while
global water-mass-weighted temperature is 293.121 K. Water in cells with
alpha >= .99 remains above 292.799 K; only .0592 g of water is assigned
T < 273.15 K, entirely outside that water-rich group. This locates the
cooling in the computed gas inventory without establishing its heat-transfer
mechanism or full energy closure. The solver has one shared temperature;
T.air and T.water agree with it to roundoff. The
[native thermal audit](../results/summaries/i4f_20261025/corrected-source-temperature-audit.json)
and [phase-mass distribution](../results/summaries/i4f_20261025/corrected-source-temperature-distributions.png)
record the EOS and native-volume checks. These saved fields do not locate
extrema reported later by the live guard.

Cooling alone does not establish an adiabatic trajectory. At .400087 s,
tank A gas volume is 1.63454 times its initial value. The constant-mass
adiabatic comparison evaluated at that same volume,
`p_ad = p0 (Vg0/Vg)^1.399814`, gives 6.032 bar absolute and 240.86 K,
whereas CFD gives about 6.541 bar and a gas-mass-weighted 261.21 K. Tank
gas mass changes by only .00389%. This same-volume comparison separates
the thermal-trajectory difference from differences in drainage timing;
it is not a fitted polytropic closure or an identified heat-transfer rate.
Its inputs are the whole-tank rows of the
[regional thermal data](../results/summaries/i4f_20261025/corrected-source-temperature-zones.csv)
and the initial native gas volume in the audit record.

Adiabatic solid walls do not imply adiabatic gas evolution in this model:
SST also supplies turbulent thermal transport inside the fluid. At .40 s,
the gas-rich headspace's median eddy-to-molecular diffusivity ratio is about
234, with the installed default turbulent Prandtl number equal to one. The
[native transport audit](../results/summaries/i4f_20261025/corrected-source-temperature-diffusion-v2.json)
and [coefficient table](../results/summaries/i4f_20261025/corrected-source-temperature-diffusion-v2.csv)
distinguish base enthalpy coefficients from the sensible-internal-energy
temperature coefficient, which includes Cp/Cv in pure gas. They explicitly
qualify the gas-rich selection's mixed cells. Equivalent-cell diffusion
times of several seconds are local scale estimates, not interfacial heat
fluxes or an explanation of the pressure difference. The historical
[OpenFOAM design note](https://openfoam.org/release/2-2-0/thermophysical-multiphase-energy/)
describes the mixture-temperature formulation's boundedness motivation;
that motivation does not validate its thermal accuracy for this apparatus.

A targeted [sealed water–air withdrawal study](../results/summaries/i4f_20261025/gas-layer-grid-sensitivity.json)
now demonstrates a numerical contribution in a controlled limit. A 1 m
channel starts with 80 mL water and 20 mL air at 12 bar absolute; water-only
withdrawal expands the gas by approximately 1.6345 over .4 s. Gravity and
turbulence are disabled, and Pr=1e9 suppresses physical thermal diffusion.
Uniform axial meshes with 3/6/12/24 cells initially across the gas layer give
pressure errors against the adiabatic reference at native gas volume of
6.66/4.45/2.92/1.92%. Gas-mass-weighted temperature errors follow the same
trend. Gas-mass drift remains about .01%, while the gas energy/work remainder
decreases from 3.58 to 1.04 J. Thus small inventory error alone does not rule
out a substantial apparent thermal offset. The
[figure](../results/summaries/i4f_20261025/gas-layer-grid-sensitivity.png)
also shows the finest case's native temperature and phase-fraction profile.
Both phases are refined together; this is not an isolated gas-only refinement.
The study uses 2 outer iterations and 2 pressure corrections, versus 8 and 2
in the apparatus, and its solver identity is recorded separately. It does
not establish the cause or correction size in the turbulent apparatus.

The apparatus's [first tank-interface refinement comparison](../results/summaries/i4f_20261025/tank-interface-startup-comparison.json)
uses exact native states at .050021166664 s, with about 25 rather than 50 mm
local tank spacing. The 299,248- and 456,954-cell cases retain identical
physics and solution dictionaries; the latter uses the previously checked
lean audit build. In both tanks, gas-mass-weighted temperature decreases
from 291.886 to 291.797 K. Gas volume in cells with .01 < alpha_water < .99
falls from 15.57% to 12.56% of total tank gas volume. Tank withdrawal differs
by about .18 mL and native seat water flux by .014%; these are observed early
differences, not established accuracy bounds. Initial tank water matches,
but remeshing increases gas capacity by .883% and reduces total line water
by 7.1 mL. The [figure](../results/summaries/i4f_20261025/tank-interface-startup-comparison.png)
therefore normalizes pressure and gas volume to each mesh's own initial state.
At those distinct observed expansion ratios, pressure exceeds the adiabatic
reference by .179% and .143%, respectively. This single startup snapshot
does not establish a convergence order, thermal mechanism or later behavior;
the same-settings refined continuation now supplies the near-.4 s comparison below.
The [extended exact-time comparison](../results/summaries/i4f_20261025/tank-interface-time-series.png)
now includes .100021166664 s. Gas-mass-weighted temperature is 290.796 versus
290.527 K, and pressure departure from each observed-volume adiabat is .446%
versus .342%. Tank withdrawal differs by 1.18 mL and native seat flow by .0374%.
The [raw data](../results/summaries/i4f_20261025/tank-interface-time-series.json)
retain phase-fraction excursions: minimum alpha is about -1.08e-5, while the
integrated equivalent negative-water mass is below .13 mg in each mesh.
No alpha clipping is applied to those reductions. These two startup checkpoints
do not isolate a thermal mechanism or establish convergence.

The [terminal tank-refinement comparison](../results/summaries/i4f_20261025/tank-interface-terminal-comparison.json)
now compares the coarse clean .400086712911 s state with the refined normal-End
.399995294759 s checkpoint. The exact time offset is -91.4 microseconds; neither
fields nor scalar histories are interpolated. For tank A, gas-mass-weighted
temperature changes from 261.207 to 254.920 K and gas-volume-weighted pressure
from 654.125 to 642.040 kPa (-1.85%). Tank withdrawal is 189.407 versus
188.300 L (-.584%), and the sum of two native valve-seat water fluxes is
1.047557 versus 1.036627 m3/s (-1.04%). The small time offset is retained in
these differences; they are not exact-common-time error estimates. Each mesh
starts with its own gas volume, differing by .883%, so geometry and discretization
effects are not fully isolated. Against the adiabat at each observed gas-volume
ratio, pressure departures are 8.44% and 5.60%; the adiabat is a diagnostic
reference, not an established exact solution for this turbulent apparatus.

The [native plot](../results/summaries/i4f_20261025/tank-interface-terminal-comparison.png)
shows stronger thermal sensitivity than early hydraulic sensitivity. Gas volume
in cells with .01 < alpha_water < .99 falls from 19.80% to 9.69%. The temperature
mean in the fixed headspace zone changes by 1.19 K, versus 6.29 K over all tank
gas. These observations make diffuse-interface thermal transport worth examining,
but neither identify a physical heat flux nor prove numerical diffusion is the
sole cause. The refined endpoint has no raw pressure contacts or persistent
pressure-update stop; its final outer pressure update is 2.415 Pa. Boundary-flux
balanced cumulative water/gas defects are +.045687/+.000151 kg, respectively.
This result precedes the reference's later .41–.44 s failures and therefore does
not establish their remedy. Keep the independent bend-refinement and stock-source
cold-start comparisons as the next discriminating experiments.

The [native gas storage/work analysis](../results/summaries/i4f_20261025/headspace-pv-energy-proxy.json)
checks `U_g* = sum(alpha_g p V)/(gamma-1)` against `sum(m_g Cv T)` and integrates
gas-volume-weighted pressure against the saved gas volumes. For both tanks
together through .400087 s, storage changes by -195.307 kJ while the
trapezoidal pressure–volume work proxy is +332.626 kJ, leaving +137.319 kJ.
The configured sensible-energy reference changes that remainder by only
.099 kJ; coarsening the saved-state quadrature changes work by .844 kJ per tank.
The positive-gas-volume p05–p95 pressure spread at the endpoint is about 124 Pa.
These checks make the calculation traceable, but do not turn the remainder
into measured heat transfer or identify a numerical energy defect. Interface transport,
thermal terms and other budget terms remain unresolved. The
[figure](../results/summaries/i4f_20261025/headspace-pv-energy-proxy.png)
also includes the refined trajectory through .284932 s; its different endpoint
must not be interpreted as a paired mesh-error reduction. Domain gas inventory
loss reflects an open, venting control volume and is distinct from a
boundary-flux-balanced conservation residual.
The new terminal refinement analysis extends that case to .399995 s: both
tanks together have delta(U*)=-235.708 kJ and integral(pbar dV)=327.933 kJ,
leaving +92.225 kJ. The sensible-energy reference changes this by -.044 kJ;
every-other-snapshot quadrature changes work by .763 kJ per tank. The reduced
proxy remainder is observed at nearly matched times with different initial
capacities and saved-point sets. It is not a 32.8% reduction in a proven
numerical energy error. Root independently checked EOS/work/reference arithmetic
for all 38 tank-states, the CSV row count, output hashes and all 15 terminal
native-file hashes, and inspected the plotted curves.

The [forward-model comparison through .400087 s](../results/summaries/i4f_20261025/corrected-source-model-comparison.png)
also shows how the initial agreement evolves. At that same time, CFD tank-A
water is 2.480 L below the reduced model, while its pressure is 654.125 versus
607.529 kPa absolute, a 7.67% difference. The model starts with 1.592 L more
water in its equivalent upstream feed; that initial geometry difference is
kept separate from the tank comparison. Native valve-flow sample means
exceed the model by about 2.25% in the final .35–.40 s bin, with instantaneous
endpoint differences of 5.20–6.06% across the valves. These are consistency
comparisons, not calibrated error estimates. Connected liquid fronts extend
farther than the model's full-bore front, with substantial dependence on the
phase-fraction threshold; that is not a demonstrated outlet-water arrival.
Exact common-time 24/48-layer scalars through .20 s differ by at most
1.554 kPa in pressure, .421 L in tank volume and 1.57% in valve flow. This
prefix evidence does not replace the original startup HOLD or establish
convergence through the later failure. The
[analysis record](../results/summaries/i4f_20261025/corrected-source-model-comparison.json)
preserves masks, connected-front definition, temperature weighting and inputs.

The parameterized CAD now supports horizontal and vertical tank axes with
inspected connection sections. This is geometry capability; there is no
current vertical-arrangement CFD performance result. The published air-filled
movie through .200021 s still depicts the earlier original-source run, not
the corrected-source long continuations. Its filename is retained for link
stability. The [new corrected-source preview at .350114 s](../results/summaries/i4f_20261025/corrected-source-preview-0p350.png)
shows all four branches in the outlet view, with no resolved exterior water
at alpha >= .5 at that time. Its native mapping and CPU/Mesa backend are
recorded alongside it. The later .8 s movie milestone was not reached.
The [10x cutaway movie through the saved .443669 s diagnostic endpoint](../results/summaries/i4f_20261025/corrected-source-cutaway-through-0p443-10x.mp4)
and [all-four-branches view](../results/summaries/i4f_20261025/corrected-source-outlets-through-0p443-10x.mp4)
retain actual native states and label the incomplete discharge explicitly.

### Earlier primed-line four-mouth context

An earlier 12-bar, two-tank/four-outlet run used a 303,108-cell mesh with two
recorded face-tet quality failures. It completed .05 s and was saved/stopped at
.516777 s after the initial-fill correction; this remains exploratory.
A matched .05 s halved-timestep trial changes
probe pressure by 103 Pa, sampled flow by about .2% and maximum speed by 4.1%,
at about twice the wall cost. The separate 1,779,258-cell reservoir-boundary case
completed .050021 s with a full restart and no pressure clipping. Compared at
the same time, its headspace probe pressure differs by 403 Pa (0.034%), tank
drawdown by -2.44%, and sampled mouth-plane mean water fraction is .944 versus
.970 coarse. Native headspace capacities differ by about 1%; this is startup
sensitivity, not formal convergence or a late-time sheet comparison. See the
[matched metrics](../results/summaries/i4f_20261025/current-startup-grid-comparison.json).
At .2 s on the coarse run,
native gas mass remains nearly constant, while mass-weighted gas temperature is
284.905 K versus 281.357 K at the gas probe; mixed cells contain 26.5% of the
tank-zone gas volume. This is an interface-resolution and thermal-model
question, not evidence of foam. See the [current results and diagnostic images](../results/summaries/i4f_20261025/README.md).
The [portable geometry generator](../scripts/i4f_four_outlet_geometry/README.md)
reproduces the approved horizontal layout in an isolated locked CAD environment.
The user-directed compact revision removes the post-rise straight and uses a
1 m transition/outlet assembly. Its separate 269,680-cell primed-line pilot
completed .050021 s normally; configured mesh-quality checks pass. Fully primed compact lines contain another
1.363 m3 of water across the apparatus, in addition to the 2.700 m3 tank load.
Thus the compact/long comparison matches tank states but not total initial
water inventory; no matched-payload performance gain follows from it.

The corrected two-tank, four-mouth geometry has a 1,779,258-cell mesh. Its
zero-thickness divider-wall variant passes all configured mesh-quality rows,
with maximum nonorthogonality 58.020 degrees; its no-wall control does not pass
the unchanged 65-degree limit and remains held. This is mesh evidence, not CFD
validation. During initialization, closed-surface cell selection was found to
exclude wall-cut pipe cells, undercounting line volume by about 17%. Including
those cells brings the internal native volume within 0.21% of the exact CAD
envelope. The corrected tank/line/exterior partition assigns every cell once;
mouth-plane classification and field checks precede the short startup pilot.
Fully water-filled historical lines add about .88 m3 per tank beyond the
reported tank payload. The user has now rejected that downstream initial-fill
hypothesis; the new air-filled case supersedes it as the physical baseline.
The earlier 1,779,258-cell revised-hardware case completed startup through
0.005021166664 s without a pressure-floor contact, but this is not a useful
release interval or completed discharge. Its native tank-plus-line water
inventory loss and native face flux agree at about .08714 m3/s per tank, while
the sampled-mouth plane reports about .068 m3/s; that gap remains unresolved.
A divider comparison must report outlet quality alongside this discrepancy
before it can support a hardware interpretation.

A three-step, 20-rank startup comparison now has complete restart fields through
4.368e-5 s. Eight and sixteen outer iterations pass the declared tank-pressure,
inventory, velocity and four-mouth flow screens on the same partition. Each
mouth's sampled area is .15000003 m2; summing its profile quadrature recovers
the plane-integral flow to within 5e-12 m3/s. These checks establish that the
outlet diagnostics work and support an exploratory eight-loop continuation;
43.68 microseconds do not establish a useful release interval, post-ingestion
convergence or engineering uniformity. The absolute residual-control trial
still used all sixteen loops. Eight-loop cold wall time was longer; two later
step increments were about 20% cheaper, insufficient to establish a whole-run
speedup. Profile evidence is in
`results/runs/i4f-fourmouth-observer-audit-20261025T102803Z/`.

The [3D tank cutaway video](../results/summaries/i4f_20261025/tank-cutaway-10x.mp4)
shows the older one-tank/two-outlet 9-bar reference from zero through .560717 s,
at tenfold slow playback. Its shell matches that reference mesh, with the near
half removed for visibility; water is derived from saved volume fractions.
Thirteen computed snapshots are held in proportion to their actual time gaps,
and the combined-run seam is disclosed. This is partial exploratory discharge,
not a full emptying or visualization of the new two-tank apparatus. Root checked
the first, middle and final frames and decoded the MP4's final frame.

## Historical one-tank numerical evidence

**A reliable mixed-phase discharge history has not yet been obtained.**
The fine-mesh and targeted source-correction runs were interrupted by workstation
shutdown at 2026-10-25 00:03 UTC. The Docker journal records a daemon termination
signal before both exits; neither container reports an out-of-memory kill.
Their complete restart states at the interruption were .100021 s (fine) and
.460771 s (source trial), respectively. After recovery, fine was saved normally
at .251771 s without floor contact; the longer source trial was saved at
.589759 s after floor intervention, as detailed below. Unsaved log-tail steps
are not restart checkpoints. This interruption
does not answer either numerical comparison; new continuations must preserve
those inputs and distinguish stage ledgers from whole-trajectory conservation.
After recovery, the frozen-predictor-source trial passed .493498 s with no
raw pressure-floor contact and a final pressure update of 2.12e-6 Pa, beyond
both matched stock restart endpoints (.4865/.4901 s). This is evidence that
the numerical change merits continuation, not a completed accuracy comparison.
The completed common-window comparison uses nearest-time native observations,
without interpolation across restart seams. Against stock outer16, fourteen
gas-pressure samples through .484273 s differ by at most 134.3 Pa (.0227%),
with RMS 107.6 Pa. In 147 matched steps through .486505 s, nozzle water flow
differs by at most .00630% and tank-water volume by at most 0.92 mL. Global gas
inventory differs by 1.50 g at the endpoint; the candidate's cumulative gas
ledger defect fraction is about 8.97e-5 versus 2.77e-5 for stock, so closer
pressure convergence does not mean uniformly improved conservation. Both
stock iteration counts and the candidate are retained in the
[source-hashed comparison](../results/runs/i4f-frozen-sp-common-interval-20261025T0802Z/comparison.json).
These small differences support continuing the targeted trial, but do not
establish accuracy after the stock trajectories end or validate the apparatus.
The longer source trial subsequently stopped at .589758560843 s on the
pressure-update rule, after 68 raw-below-floor corrector passes beginning at
.589138142355 s. Later positive pressure and small outer updates do not
establish independence from the 10 kPa bound, which is applied before velocity,
flux and density correction. Matched 10/5 kPa replays now use the same complete
pre-contact .560717 s checkpoint and recorded timestep schedule. The old
zero-contact continuation remains held. Initial replay attempts stopped on an
inherited relative-velocity admission screen before contact and are preserved
as non-discriminating. The new diagnostic records that admission screen as
advisory while retaining physical/ledger/pressure-update stop rules.

Both matched replays subsequently completed the exact .589617581493 s endpoint
on the same 555-step schedule. Changing 10 to 5 kPa changes the intermediate
pressure traces, but endpoint tank mean pressure differs by only 2.2e-5 Pa and
outlet volume flow by 1.18e-8 m3/s. This supports endpoint bulk insensitivity
within this short interval, not general floor independence. Root inspected
the [matched endpoint comparison](../results/runs/i4f-pmin-replay-pair-20261025T095211Z/analysis/matched-endpoint/matched-endpoint-summary.json)
and its plot.

That agreement does not clear the late fields. An
[endpoint audit](../results/runs/i4f-pmin-replay-pair-20261025T095211Z/analysis/extreme-field-audit/endpoint-extreme-field-audit.json)
finds gas-dominant velocities near 1490 m/s (local Mach 4.49), with a separate
gas-temperature maximum of 652 K. The fastest cell also sets the Courant limit.
Direct binary boundary inspection in the independent source review finds an
ambientAnnulus face admitting 1489.93 m/s flow at imposed static 100 kPa and
293.15 K, with native inward phi .314569 m3/s. The patch-wide EOS-density
estimate of incoming kinetic-energy flux is 1.214 MW; this is an instantaneous
boundary diagnostic, not a closed solver-energy residual. Speed exceeds
1000 m/s before the first pressure-floor contact, excluding that later contact
as the initiator of the preceding growth. The ambient formulation/placement
and numerical amplification must be isolated before interpreting the late
outlet flow as physical.

For an ambient reservoir, static pressure/temperature and stagnation conditions
are different boundary specifications when inflow accelerates. A controlled
pre-onset replay will test a compressible reservoir conversion followed by
the correct hydrostatic subtraction, with inlet-only total temperature. Exact
v2512 source inspection shows that `prghTotalPressure` contains only the
incompressible dynamic-pressure subtraction, while compressible `totalPressure`
does not itself supply the hydrostatic conversion required for `p_rgh`.
Blindly substituting either is inadequate. The compressible mode is documented
in [OpenCFD's totalPressure reference](https://doc.openfoam.com/2306/tools/processing/boundary-conditions/rtm/derived/inletOutlet/totalPressure/).
The case-local implementation requires analytical gas-only and flow-reversal
checks before the paired replay; successful suppression would establish
boundary sensitivity, not hardware validation.

A revised, complete one-tank/two-outlet water/air calculation has completed
0.489232241974 s with no pressure-floor contact and a complete checkpoint.
Its original startup controller stopped on an overly small face-flux-update
allowance; that operational decision remains preserved. The separately declared
continuation targeted 1.20 s with the face-flux update advisory and a sustained
pressure-update stop. The latter stopped this run after three >100 Pa updates
that did not sufficiently contract. At the saved endpoint, the final update
had returned to 3.757 Pa and raw minimum pressure was 54.0 kPa. This is a
numerical diagnostic interruption, not a physical discharge endpoint or proof
that the intervening nonlinear iterations were adequate. The three trigger
updates were 135.6, 209.8 and 279.7 Pa at .488361/.488581/.488800 s; a further
completed step reached 389.8 Pa before the final contraction. No pressure
floor was involved. The raw pressure-matrix residual alone is not the corrected
operator defect: the known coupled-source subtraction gives 5.18e-7 m3/s at
the endpoint, with identity error below 9e-15. This does not establish outer-loop
convergence. These are operational monitors, not validation criteria.
This pilot's binary
cell-center initialization gives 1.333126 m3 of tank water, rather than the
intended 1.380494 m3. Native total water is 2202.033 kg and effective tank fill
about .67845. The difference is an initial-state discretization error, not
lost water during discharge. A separate fractional-cell initialization now
matches the nominal tank-water volume, but has not been run; it does not alter
this trajectory. A volume-matched reduced-model comparison through .30 s gives
useful early pressure/inventory consistency, as detailed below, without yet
establishing the complete discharge or outlet-uniformity accuracy.

At the .489232 checkpoint a headspace-connected gas tongue reaches the upper
intake throat, while the lower throat and both nozzle mouths remain water-filled.
The first 0.20 m of upper throat contains 1.85/1.61/1.11 L of connected gas
at gas-fraction thresholds .1/.5/.9; the component does not connect to the
far-exterior seed. Neither throat has qualifying gas at .450021 s, giving an
onset bracket rather than an exact time. Tank water is still 1.05932 m3,
79.46% of its initial inventory. Its volume-equivalent flat level is .266 m
above the upper-opening crown, so that flat level is not a sufficient ingestion
criterion. This is a computed gas-position/connectivity result, not proof of
a vortex, sustained gas delivery or real-device behavior. Its time/grid/coupling
sensitivity remains to be established. Evidence:
`results/runs/i4f-headspace-intake-connectivity-20261024T2325Z/analysis/headspace-intake-connectivity-refined.json`.
Root inspected the [matched native gas slices](../results/runs/i4f-headspace-intake-connectivity-20261024T2325Z/analysis/figures/headspace-gas-upper-intake-connectivity.png);
the displayed blue quantity is gas fraction, not water fraction.

The revised apparatus also has a pre-ingestion headspace-energy diagnostic,
using eleven field snapshots and dense native tank-volume history through
.450021 s. Gas volume grows from .63184 to .86047 m3 while EOS-derived air
mass changes by .0055%. Mass-weighted gas temperature falls to 270.54 K and
gas-volume-weighted pressure to 609.91 kPa. At that same measured volume, the
fixed-mass reversible adiabatic reference gives 259.10 K and 584.09 kPa;
isothermal expansion gives 293.15 K and 660.85 kPa. These are reference
processes, not fitted curves or experimental bounds.

With the case's constant ideal-air Cv, the gas sensible internal-energy change
is -109.6 kJ. Estimated pressure work is +168.5 kJ, leaving +58.9 kJ in
`delta Eg + integral(pg dVg)`. This is 4.14% of initial gas internal energy
and 34.9% of pressure work. Dense-volume integration with interpolated
snapshot pressure and snapshot trapezoidal work differ by .176 kJ; this
comparison is not a full quadrature-error bound. The shared-temperature solver,
adiabatic solid-wall temperature condition, modeled thermal transport,
mechanical-energy terms and discrete interface coupling must be distinguished
before assigning that remainder to heat or numerical error. The aggregate
ideal-gas identity is algebraic, not an independent EOS validation. Root
inspected the [energy plot](../results/runs/i4f-headspace-energy-audit-20261025T075514Z/analysis/headspace_energy_audit.png)
and [native-field audit](../results/runs/i4f-headspace-energy-audit-20261025T075514Z/analysis/summary.json).
Thermal-model and grid sensitivity remain material uncertainties.
An [extension with the valid native gas probe](../results/runs/i4f-headspace-energy-audit-20261025T075514Z/analysis/energy_mechanical_transport_extension.json)
uses 181 pressure samples (2.5 ms median spacing), giving work 168.591 kJ
and remainder 58.956 kJ. Probe water fraction stays below 3.1e-17; this is a
different observer from the invalid dedicated gas probe reported in the first
audit. Mean-flow and modeled turbulent kinetic-energy storage together change
by only 4.85 J, so omitted stored kinetic energy does not explain the remainder;
this is not a bound on dissipative or interfacial energy transfer. At .45 s,
pure-air-core modeled temperature diffusivity is about .00133 m2/s, much
larger than molecular diffusion. Whole-gas averages include mixed cells and
cannot be treated as a measured interphase heat-transfer coefficient. Root
inspected the extension plot and checked the shared-temperature equation.

At the old apparatus's saved .560717 s field, minimum liquid-core pressure is
35.42 kPa at 293.25 K and 11.17 m/s near the transition. Gas pressure is about
ambient or higher; maximum gas-reference Mach is .151. Native-flux Courant
reconstruction matches the solver, with its maximum in a fast gas cell larger
than the median cell. These observations do not classify later raw contact
cells or explain the full subsequent timestep collapse. A pressure pass's
reported affected-cell water mass is support inside that cell, not mass added
or removed; repeated passes must not be summed as cumulative mass loss.

The completed old coarse/fine prefix comparison spans .100271–.200021 s.
Endpoint fine/coarse gas pressure is 844.741/844.753 kPa and sampled total
nozzle water flow .36872/.36551 m3/s; at .149521 s flow differs by about 4.2%.
Endpoint tank depletion differs by .308 L. Fine initial headspace is .34%
larger and line water 2.083 L larger; source-length normalization preserves
the intended integrated valve K. This is descriptive numerical sensitivity,
not a convergence order or post-ingestion robustness claim. Root inspected
the [prefix analysis](../results/runs/i4f-coarse-fine-hydraulic-prefix-20261025T094025Z/coarse-fine-prefix.json).

The longer coarse 10/5 kPa tests retain pressure clipping through every final
correction near 0.319 s, with a substantial unresolved pressure-operator defect.
The velocity-convection limiter does not remove it. The earlier gas-marker,
mesh and valve-comparison values below remain computed statistics from
pressure-affected trajectories; they do not establish physical late-discharge
performance. The corrected fine continuation is now terminal, and a full-log
audit also disqualifies its late checkpoint as a healthy continuation source.

The fine continuation ended on its six-hour wall limit, with the latest complete
checkpoint at 0.385393470561 s. Its controller failed to recognize the aligned
`stopAt          endTime;` dictionary entry, so the intended health stop was not
applied. Inspecting raw pressure before the numerical floor, rather than only
saved bounded fields, finds the first negative absolute-pressure iterate at
0.31973360344 s. Over 0.35 s to the last completed step, final-correction raw
pressure reaches -2.487 MPa, the largest final outer pressure update is
11.77 MPa and the corrected post-floor operator defect reaches 0.773 m3/s.
These are numerical failures, not physical negative-pressure predictions.
Some earliest strictly-below-floor records are roundoff, which is distinct
from this later failure. Preserve the late fields for diagnosis; do not resume
them as a valid discharge. Evidence:
`results/runs/i4f-fine-full-discharge-20261024T1002Z/analysis/pressure-validity-audit-20261024T2040Z.json`.

The matched cold fast-opening run with stronger coupling from startup also
stopped, saving 0.31654077 s after three consecutive completed steps at the
10 kPa numerical floor. Its last step's raw minimum is positive 6.747 kPa,
above the approximate water saturation pressure, and its final outer pressure
update is only 0.00887 Pa. This separate event establishes floor intervention,
not cavitation or a failure to contract the outer loop. Stronger startup
coupling alone has therefore not removed the floor contact.

The reduced model also exposes a physical consistency warning: the assumed
0.25 m feed pipe and 0.15 m2 exit can demand sub-saturation static pressure
before most tank water is discharged. The n=1.25, 0.5 s, 2%-minimum-opening
case crosses the approximate 20 C water saturation pressure at 0.4326 s,
with 82.5% of its initial tank water remaining. This does not prove cavitation
or explain the much deeper numerical undershoot, but makes feed-pipe geometry
and omitted vapor response consequential rather than incidental inputs. This
warning occurs after the CFD first admits gas into the pipe: it is a conditional
fully-liquid-line screen beyond that model's applicability, not a prediction of
the actual mixed-phase pressure or proof of a reachable initial steady state.

An updated early comparison avoids the pressure-clipped late endpoints. At
the fast-opening anchor 0.31500928 s, native face-adjacency connects gas in the
pipe at x=2.2 m to the tank headspace at gas-fraction thresholds 0.1, 0.5 and
0.9; those cells do not connect to the far-field external-air seed. A slow-opening
field at 0.46908678 s has about 2.96 L less tank water than that fast anchor,
yet no threshold-qualified gas in the pipe mouth or at x=2.2 m. The mean tank
surface still lies above the pipe crown in both fields. This supports a local
drawdown mechanism, not a resolved vortex or molecular-origin tracer.

At exactly matched native tank inventory (0.984405803 m3), scalar interpolation
places the slow case at 0.46340734 s: headspace probe pressures are 700.3 versus
697.8 kPa, while approximate sampled-plane nozzle water flows are 0.520 versus
0.751 m3/s. The slower schedule delays the compared drawdown and reduces flow;
neither outcome establishes improved useful discharge. The fast history used
two outer corrections through 0.300 s, then sixteen and eight, whereas the slow
case uses eight from startup. Earlier history remains a confound even though
the fast 0.310–0.315 s anchor continuation has no floor contact. A matched
cold-start fast case has since run and stopped at floor intervention as described
above. Evidence and threshold/observer
definitions: `results/runs/i4f-valid-early-valve-comparison-20261024T115835Z/`.

In the earlier provisional, initially water-filled water/air fields, local tank
surface drawdown allows gas into the pipe while substantial tank water and
pressure remain. The single-liquid model's average-level criterion therefore
overpredicts the liquid-only interval. Both examined meshes show early port
gas ingestion; this is a resolved drawdown observation, not proof of a vortex.

The earlier horizontal trajectory reaches its declared nozzle-gas marker at 0.411 s
after 253.6 L of net upstream water-storage depletion D, not a direct nozzle
flux integral or escaped volume. Doubling valve-opening time
delays that marker by 50.6% but increases depletion at the marker by only
3.0%. The vertical arrangement later fails numerically; its saved fields first
reach the imposed 10 kPa pressure floor between 0.30 and 0.35 s. The later
matched-depletion comparison is therefore withdrawn. Intake submergence and
arrangement remain useful hypotheses to test alongside opening time;
they do not establish hardware efficiency or an optimized valve schedule.

The new cold-start slow case also exposes a distinct coupling limitation without
pressure clipping. At 0.5122158 s, all eight outer updates remain near 28–30 kPa
rather than contracting; the surrounding transient peaks near 46.8 kPa. A line
probe at x=2.60 m rises from about 93.5 to 201.9 kPa between 0.5080 and 0.5122 s,
with sampled water fraction one at both ends. At the concerning final pressure
solve the corrected linearized operator defect is small (maximum 1.72e-6 m3/s,
identity agreement about 1e-14 m3/s), pressure remains above the floor and
cumulative water error is about 0.027 kg. Those checks do not prove convergence
of the nonlinear outer loop. A short native-checkpoint eight-versus-sixteen
comparison has completed: sixteen updates retain the alternating pressure
cycle rather than removing it. The long slow-case continuation remains held.
Agreement between two even iteration counts is not treated as convergence.
Numerical source:
`results/runs/i4f-slowvalve-cold-coupled-20261024T1104Z-attempt4/analysis/outer-pressure-transient-diagnostic.json`.
The original plot used probe columns shifted by one; its numerical pulse
description was correct. Use the [corrected, header-checked plot](../results/runs/i4f-slow-pulse-outer-pair-20261024T123127Z/analysis/prior-transient-probe-index-corrected.png)
for the spatial labels. The original artifact is retained as superseded.

A subsequent four-step pulse logs the actual coded resistance coefficient and
assembled momentum diagonal without changing the equations. All fourteen saved
fields plus uniform/time and function-object state match the uninstrumented
one-step control byte-for-byte. With eight outer and two pressure corrections,
the valve coefficient varies only .539% and contributes 2.04–2.38% of the local
momentum diagonal; dt*K*|U|/L is .0426–.0500. Pressure updates nevertheless
alternate by tens of kPa. This makes an obviously stiff, independently cycling
drag coefficient an unlikely sole explanation. The same cell's gas fraction
ranges from 5.71e-5 to 1.51e-4 at the logged momentum stage. A subsequent
passive alphaSuSp diagnostic resolves an important distinction: its branch-
specific 1e-4 denominator floor is inactive in all 128 sampled source rows.
The momentum-stage crossing therefore does not support the proposed cutoff
mechanism. The dgdt sign alternates with the cycle; positive-source dt*Su and
dt*Sp reach approximately +1.01/-1.01, while the actual net fraction increment
is much smaller. This identifies substantial implicit phase-source coupling,
not its proven causal role. A matched transonic yes/no pressure-
linearization comparison retains the cycle in both arms (approximately
plus/minus 47 kPa at the endpoint), while nozzle flow differs only .0016%.
Thus disabling this linearization is not a cure either. A matched fixed-40/20-us
pair reduces maximum |dt*Sp| from .813 to .376 but retains large final outer
pressure updates of approximately 48/54 kPa, with no pressure-floor contact.
Unlike the original adaptive pulse, its phase-source denominator floor is
active in 32/128 and 64/256 rows. The fixed-step logger lacks signed target-cell
pressure histories, so these results establish noncontraction, not independently
verified signed cycles. Root inspected the
[source/pressure pulse plot](../results/runs/i4f-valve-cycle-mechanism-20261024T2051Z/analysis/valve-cycle-mechanism.png).

A single targeted independent numerical review identifies a more specific
correction-path discrepancy. The implicit upwind alpha predictor and its MULES
correction use different phase-source coefficients after recomputation at the
predicted fraction. In the inspected floor-inactive positive-dgdt example,
the coefficient changes from -13692 to -562 per second as predicted gas fraction
increases, and the stage discrepancy is approximately 47 per second. This is
not the small source evaluated at the pre-predictor fraction. The discrete
equations and source locations are in the private diagnostic source; the
review does not establish a production fix.

The resulting nAlphaCorr=0 diagnostic removes the correction loop while keeping
the implicit predictor. Its last-step outer pressure update decreases from
4.69 kPa to 25.7 Pa, compared with a roughly 48 kPa stock plateau. However,
valve-cell gas fraction rises to .0194 instead of about .000053: increased
diffusion is a major confound. It is not promoted to the apparatus method.
A stock compressibleInterIsoFoam restart also encounters the 10 kPa pressure
floor; that failed restart does not establish a general method limitation.
A private, disabled-by-default frozen-predictor-Sp experiment isolates
coefficient recomputation while retaining the correction flux. Over the same
four 40-us steps, the stock final outer pressure update remains about 48 kPa;
freezing the predictor coefficient reduces the last-step update to 44.1 Pa
with eight outers and 23.5 Pa with sixteen. The alternating update pattern
persists, so this is not evidence of full nonlinear convergence. Adding the
lagged divergence contribution to the frozen coefficient changes the latter
value negligibly. The patched formulation is not the revised apparatus
baseline. Evidence and phase-source identities:
`results/runs/i4f-frozen-alpha-effective-sp-20261024T221631Z/analysis/frozen-sp-source-comparison.json`.

The bounds-checked diagnostic binary also completes the idealized sealed-air
channel with sixteen outers. After 5 ms, interface RMS error is .214 mm,
outlet-speed RMS relative error .434%, and mean gas-pressure RMS relative error
1.12% against the moving-control-volume ODE. Native water-volume residual is
.0436% of initial water; gas inventory drifts -.101% despite negligible gas
boundary flux. The .03009 s stop is a 1e-6 trace-gas marker in the valve, not
bulk gas breakthrough. An earlier channel crash came from apparatus-specific
observers indexing cells outside that channel partition; bounds guards leave
all ten written fields byte-identical to stock in a flag-off one-step check.
These results support only a bounded diagnostic candidate, not promotion to
production or an apparatus validation. Evidence:
`results/runs/i4f-headspace-frozen-sp16-20261024T222233Z/analysis/frozen_sp_channel_comparison.json`.

Doubling exterior length changes the compared flow and momentum by less than
1% through the reference event. The completed mesh comparison changes nozzle
flow by 3.7% at 0.2 s and 1.09% at 0.4 s, but the outlet velocity CV changes
from 0.190 to 0.145 at 0.4 s. Bulk-flow agreement therefore does not establish
outlet-uniformity accuracy. Initial inventories also differ. Halving
the timestep/Courant controls shifts the gas marker by 0.22% and changes
0.4 s nozzle flow by 1.68%.
Before gas ingestion, the
valve dominates the pressure budget; downstream pressure recovery and absence
of strong sampled reverse flow give no evidence that major resolved transition
recirculation controls this unvaned baseline.

The actual initial pipe fill, five lamellae and CO2-retardant state remain
consequential unknowns. A gravity-drained startup attempt has exposed a
localized numerical pressure/temperature failure and is not a valid physical
comparison yet. The conclusions below apply to the declared hydraulic
reference, with explicit uncertainty, rather than to the built device.

Computed evidence: [pressure/inventory/flow histories](../results/runs/i4f-reduced-cfd-overlay-20261023T225942Z/analysis/reduced-cfd-overlay-matched-floor-v2/reduced_cfd_overlay.png),
[valve-opening comparison](../results/runs/i4f-slowvalve-20261023T222641Z/analysis/pair-endpoint-v4/native-D-matched-observers.png),
[exterior-domain check](../results/runs/i4f-external-L2vL4-endpoint-analysis-20261024T003650Z/l2_l4_endpoint_comparison.png),
[mesh comparison](../results/runs/i4f-fine-endpoint-comparison-20261024T032115Z/plots/fine_l2_history.png),
[timestep/Courant comparison](../results/runs/i4f-matched-dt-halved-pair-retry4-20261024T023228Z/matched_timestep_comparison.png),
[adiabatic gas check](../results/runs/i4f-adiabatic-gas-expansion-check-20261024T012520Z/attempt4-adiabatic-expansion.png),
[startup-failure diagnosis](../results/runs/i4f-partial-drained-failure-taper-diagnostics-20261024T012725Z/partial_drained_failure_taper_diagnostics.png),
and the [fine-grid 10x slow reference movie](../results/runs/i4f-fine-reference-visual-20261024T034004Z/i4f-discharge.mp4).

The fine movie contains seven exact states from 0 to 0.41277429 s, held for
their physical intervals at 10x slow motion (4.17 s at 24 fps). It shows the
tank, scalar valve zone, pipe, transition, external sheet and pressure/history
panels with fixed scales. No intermediate fluid motion, subgrid bubbles or foam
is synthesized. Source fields, native histories, geometry metadata, renderer
hashes and video metadata are in the movie bundle's `render-provenance.json`.

## Question and apparatus

How do gas expansion, tank drainage, valve opening and the circular-to-rectangular
transition control discharge history and the emerging sheet? The first model
includes these components and a short exterior air region in one connected
apparatus. The tank is horizontal, with its axis in x; z is upward, and the
nozzle points in +x. Gravity is in −z. The pipe entrance is near the bottom of
the downstream tank end. Tank orientation is a parameter, not an inferred
hardware fact. Original CAD, if supplied, must remain unchanged.

The user also reports five lamellae starting approximately halfway through
the transition. Their orientation, thickness and exit termination remain
unconfirmed. The initial no-vane reference omits them; it cannot establish
actual nozzle uniformity. After clarifying their arrangement, include explicit
plates and compare with the no-vane reference under matched conditions.

The provisional tank is 1 m in diameter and 2 m long, initially 70% water by
volume. Its axis is 1 m above the coordinate origin. The 0.25 m pipe is centered
at z = 0.65 m. A 1.5 m transition changes the circular section into a horizontal
1 × 0.15 m rectangle. The intended initial condition has water in the pipe and
transition; initial downstream inventory must therefore be reported separately
from tank water. The CFD initialization must document how the closed valve
supports the pressure difference before opening.

The user describes CO2 charging to roughly 8–10 bar and sealed waiting before
discharge, like a soda can. They currently think the uncharged fill is mainly
liquid with a gas headspace, but are uncertain; dispersed initial bubbles are
not confirmed. Initial headspace composition (provisionally air), the pressure
convention, bubble fraction and dissolved CO2 content remain unknown.
Compressed bubbles and dissolved gas are
distinct inventories and can change discharge, aeration and apparent rheology.
The first water/air calculation below is therefore a **hydraulic reference**,
not a model of the actual foam formulation.

The reference gas is air, sealed after an assumed charge of 9 bar absolute against
1 bar ambient. This interprets the historical “8 bar” as gauge pressure and is
not a measurement. Air permits a two-phase gas/water model with exterior air.
It does not establish CO2 thermodynamics, dissolution, aeration or gas mixing.
A maintained-pressure supply changes the mass and energy balance and must be
identified as a separate experiment.

## Connected models and interpretation

### Initially air-filled downstream passages

The new moving-front model distinguishes tank withdrawal, water stored in each
growing wetted pipe column, and water released from a mouth. For branch j,
`dVtank/dt = -sum(Qj)` and `dVwet,j/dt = Qj` before mouth arrival; outlet water
flow is zero until that arrival. Thereafter line storage is fixed and its branch
flow enters the external-water compartment. Branch and global ledgers are both
checked, including different branches crossing their mouths in the same step.

Integrating one-dimensional Euler flow over the wetted path gives

`pg - pfront + rho*g*(zlevel-zfront) = Iwet*dQ/dt + rho*(Q/Afront)^2/2 + losses`,

with `Iwet = rho*integral_wet(ds/A)`. The front velocity head follows from the
convective term and reservoir inlet condition; entrance and valve losses are
additional terms, each counted once. This is the variable-area counterpart of
the lengthening-column balance in [Tijsseling, Hou and Bozkus (2019),
Eq. (2)](https://doi.org/10.1115/1.4043321). It assumes a full-bore liquid front;
ambient front pressure is an approximation, with air Mach, pressure-loss and
front Froude diagnostics. It does not solve stratified filling or trapped air.

The current representative-tank calculation matches the native compact case's
1.350 m3 tank water, .298497 m3 headspace, 12 bar absolute and 293.15 K, using
the ideal-air adiabatic exponent 1.399814. Its equivalent wet feed is .252648 m3
(.634% above the native feed), and full line volume .693420 m3 (1.016% above
the CAD envelope). No volume or valve coefficient was fitted to CFD.

The 50/25 microsecond model steps bracket first lower-mouth water at
.611600–.611650/.611625–.611650 s and upper-mouth water at
.619800–.619850/.619825–.619850 s. The intake-crown stop is about 1.12688 s,
with .295950 m3 in the tank, .693420 m3 in its two branches and .613278 m3
released from this **one-tank** network. This is not emptying. Its adiabatic
gas temperature reaches about 160 K, emphasizing the importance of the thermal
assumption; no measured thermal history is implied. Numerical repeatability
does not validate the piston front: the air approximation remains incomplete,
and its diagnostic flags passage through the transition. Earlier .72 s results
used the older long route and different tank state, and are not current compact
predictions. Immutable input tables and histories identify each calculation.

The portable command is
`.venv/bin/python scripts/run_i4f_filling_network.py --max-time 1.3`;
it writes a fresh ignored run with source snapshots. The small frozen inputs in
`experiments/i4f_filling_reference/` remove any dependency on private historical
run directories. Eleven focused checks cover Euler flow, branch/global water
accounting, arrival, crown stopping and analytical air diagnostics; eight
existing network checks also pass. Independent review confirms those numerical
claims while retaining the physical applicability limits above.

Holding only the gas polytropic exponent at the isothermal limit n=1 gives
first-positive outlet samples at .58005/.58690 s and crown exposure at
.97013 s, versus .61165/.61985 s and 1.12688 s for n=gamma. At .5 s, gas
pressure is .578 versus .456 MPa and total two-branch flow 1.350 versus
1.177 m3/s. Both stop at the same geometric inventory condition, so equal
terminal released volume is expected; it does not validate either thermal
assumption. The [thermal sensitivity record](../results/summaries/i4f_20261025/air-filled-model-thermal-sensitivity.json)
preserves the inputs and numerical scope.

Early CFD/model disagreement has a specific candidate mechanism. The .30 m
distributed valve-loss source initially spans a half-water/half-air region,
while the reduced model places the full liquid loss at the assumed seat.
The native source's wet coverage grows from .500 to .656 by .05 s; its
density-weighted water coefficient therefore changes during filling. At .05 s,
native tank withdrawal and line gain are about 6.55 L versus 4.57 L in the
moving-front model. The [source audit](../results/summaries/i4f_20261025/air-filled-valve-zone-audit.json)
and [plot](../results/summaries/i4f_20261025/air-filled-valve-zone-audit.png)
support this as a plausible mechanism. The momentum source is resistive under
the actual `UEqn == fvOptions(rho,U)` assembly. A separate matched source-band
trial moves resistance wholly upstream while preserving its fully wet integral;
its .05 s pilot completed without pressure clipping. In the exact-time
[paired comparison](../results/summaries/i4f_20261025/air-filled-valve-source-comparison.json),
tank drawdown falls from 6.547 to 5.756 L, a 12.1% reduction, and headspace
pressure rises by 3.88 kPa. This isolates a source-placement effect but leaves
a gap against the 4.573 L reduced-model prediction. The matched continuation
to .3 s tests persistence after wetting; a small fully water-filled duct test
will verify the imposed pressure/flow resistance independently of front motion.

The reduced model predicts liquid inventory and gas volume, pressure from a
declared thermodynamic approximation, hydrostatic head, valve and pipe losses,
liquid inertia, discharge and the first approach of gas to the pipe entrance.
Every modeled resistance needs an identified velocity reference and a source
or explicit uncertainty range. A polytropic exponent is a thermal sensitivity
parameter until heat-transfer evidence supports it. The first scalar valve
restriction approximates opening hydraulics; it cannot predict butterfly-disk
wakes or their asymmetric influence on the nozzle.

The complete CFD model must evolve the gas pressure, density and interface.
An ordinary incompressible gas headspace with imposed outlet speed does not
answer this question. Record the actual gas and liquid equations of state,
energy treatment, turbulence closure, wall treatment and loss implementation
from the solver used. Agreement between CFD and a reduced model sharing losses
and gas assumptions is a consistency check, not experimental validation.

For the executed reference, the equations of state are
`rho_water = 998.2 kg/m³`, `rho_air = p/(R_air T)`, and
`rho = alpha_water rho_water + (1-alpha_water) rho_air`. Pressure is absolute;
the pressure-correction variable removes the hydrostatic contribution.
There is one mixture velocity and one temperature field, with no interphase
mass transfer. Thus this is compressible-gas/incompressible-liquid VOF, not
an incompressible treatment of the headspace and not a model of dissolved CO2.
MULES transports the phase fraction with interface compression and
compressibility source terms; the mixture momentum equation includes pressure,
gravity, surface tension, modeled viscous/turbulent stresses and valve drag.
SST is a provisional closure for the high-Reynolds-number internal flow and
adverse pressure gradients; no measured turbulence or wall-resolution evidence
yet establishes its quantitative accuracy for this apparatus.

The installed v2512 `TEqn.H` solves a temperature equation rather than an
independently logged total-energy balance. With
`D_rho(q) = d(rho q)/dt + div(rho U q) - q contErr`,
`contErr = d(rho)/dt + div(rho U)` in this source-free-mass case, and
`K = |U|²/2`, its continuum-like structure is

`D_rho(T) - div(alpha_eff grad(T))`
`+ (alpha_water/Cv_water + alpha_air/Cv_air) [div(p U) + D_rho(K)] = S_T`.

This records the implemented pressure-work and kinetic-energy coupling;
face fluxes and finite-volume operators, not this shorthand, define the actual
discrete equation. Both phases share T, transport coefficients are blended,
and walls are adiabatic. A gas inventory diagnostic `sum(m_air Cv_air T)` is
therefore not a proof of a conservative total energy balance through mixed
cells, valve drag, heat diffusion and open boundaries. It remains necessary
to distinguish thermal accounting from mass closure and linear-solver residuals.
Source evidence is the pinned image recorded with every case, under
`applications/solvers/multiphase/compressibleInterFoam/`
(`UEqn.H`, `TEqn.H`, `compressibleAlphaEqnSubCycle.H`) and shared
`applications/solvers/multiphase/VoF/alphaEqn.H`. These files were inspected
directly in the installed v2512 image; an unavailable online API page was not
used as evidence for this version.

As a provisional liquid-compressibility screen, taking water sound speed as
1500 m/s gives a bulk modulus `rho*c²` of about 2.25 GPa. An 0.8 MPa pressure
change then implies a relative density change around 0.036%, and acoustic
transit through the 2.5 m line takes about 1.7 ms, far below the 0.5–1.0 s
opening times. These order-of-magnitude values support constant-density water
for bulk startup. They do not verify water-hammer transients, the initial
finite-bleed pressure jump, or a liquid containing compressed bubbles; that
mixture can have substantially different compressibility.

## Observables and comparison conventions

Use the same physical nozzle plane and section definitions on every mesh.
With its unit normal **n** directed outward, define outward liquid volume flux
as `Q+ = integral(alpha_water max(U·n,0) dA)` and report inward flux separately.
For mass conservation use the actual signed, conservative solver phase mass
flux, including inward boundary flow. Report tank inventory, downstream stored
water, external stored water and escaped water without counting nozzle flux
again as stored or escaped water. A pressure-dependent water density requires
mass integration rather than a constant-density volume conversion.

At the nozzle report liquid area `A_L = integral(alpha_water dA)`, net liquid
flux, area-weighted mean normal velocity and its RMS spatial variation divided
by the magnitude of that mean. Declare low-flow intervals undefined rather
than dividing by nearly zero. Also report the outward-water-flux-weighted
mean local angular departure from the nozzle normal, and separately the angle
of the net forward-water momentum vector. Opposite lateral directions cancel
in the latter but not in the former; a local fan angle is not a net downward
jet deflection. Retain
reverse-flow fraction, gas area/flux fractions and liquid momentum flux
`integral(rho_water alpha_water U max(U·n,0) dA)`. A single uniformity number
cannot distinguish an aerated patchy outlet from a fully wetted one, so retain
spatial maps and wet area with it.

Compare area- or phase-weighted section pressure with the weighting stated;
separate static pressure differences from total mechanical-energy changes.
Measure valve, pipe and transition losses at fixed sections, recognizing that
an unsteady pressure difference also accelerates the liquid column. A loss
coefficient inferred during startup cannot be interpreted as steady dissipation
without the inertia term. Record recirculation and separation in the transition.

Track sheet thickness only where there are enough cells through it; otherwise
report liquid volume or flux and the resolution limitation. A smoothed display
does not supply missing physical sheet thickness or breakup scales.

## Initial dimensional sanity check

Direct cylinder geometry gives 1.570796 m³ tank volume, 1.099557 m³ initial
tank water and a free surface at z ≈ 1.159846 m. Pipe area is 0.049087 m²,
versus the nominal 0.15 m² nozzle area: an area expansion of 3.0558.
Gas first reaching the top of the entrance at z = 0.775 m corresponds to
about 0.351084 m³ remaining tank water. This is a geometric screening event;
actual entrainment can begin earlier through vortices or surface deformation.
It permits about 0.748473 m³ tank drawdown before that screening event.

For a sealed exponent of 1.25, the corresponding gas pressure would still be
about 2.7414 bar absolute. The apparatus may therefore entrain gas while a
substantial pressure and water inventory remain. These values follow from
assumed geometry and thermodynamics and are not experimental observations.
The reduced model and CFD must determine the associated time histories.

## Verification and first engineering comparison

First obtain startup, a useful discharge interval and a defined termination
event in the complete apparatus. Inspect liquid conservation, gas mass and
energy accounting, pressure/velocity plausibility, convergence and interface
transport. Check actual mesh resolution through the pipe, valve representation,
contracting dimension and emerging sheet. A completed run or bounded alpha
does not establish accuracy.

Select one focused mesh refinement and one timestep refinement for pressure,
flow, cumulative mass, breakthrough time and outlet quality. Test the external
boundary if pressure or liquid approaches it. Distinguish numerical corrections
from engineering changes; preserve failed cases. Do not assign a formal pass
until the declared observables and uncertainty support it.

Choose the first physical comparison from the baseline: transition separation
suggests a transition-length comparison; opening-dominated oscillations suggest
opening-time comparison; early gas ingestion suggests tank orientation and
entrance placement. Match initial water mass, initial gas state and pressure,
and report discharge and uniformity tradeoffs together.

## Measurements needed for the real hardware

- Tank inner diameter, axial length, end-cap shape, installed orientation,
  outlet connection location, and initial water mass or fill level.
- Actual gas species, temperature, absolute/gauge pressure convention, initial
  pressure trace, and supply plumbing: isolated vessel, regulator, or finite
  connected reservoir. Include regulator capacity and line restrictions.
- Pipe inner diameter, lengths, bends, fittings, elevations and roughness;
  valve diameter, disk/shaft geometry, installed angle and opening-angle versus
  time, plus flow/loss data if available.
- Transition inner surfaces, length and cross-sections, actual final opening,
  lip thickness and any internal guides. Preserve original CAD and identify
  uncertain dimensions instead of silently repairing them.
- For the four dividers in the latest user description: plate orientation,
  thickness, spacing and
  angles, leading-edge locations relative to the transition, termination at
  or before the exit, and wall/tip clearances. Confirm whether they divide the
  1 m span or the 0.15 m height; these make different hydraulic passages.
- Confirm the initial liquid interface at each valve seat, upstream wetted-pipe
  inventory and any trapped liquid pockets. The user confirms initially
  air-filled downstream passages. The older primed compact sensitivity adds
  1.363 m3 of line water across both tanks; that does not describe the confirmed
  startup. Keep all line inventories separate from the reported 2.700 m3 tank
  payload.
- Synchronized tank pressure, liquid inventory or discharged mass versus time,
  valve position, and pressure taps before/after the valve and transition.
- Outlet velocity/flow-direction maps or calibrated high-speed images with
  length and time references; gas-breakthrough timing and visible aeration.
- Water temperature/properties, additives, dissolved-gas state and evidence
  for CO2 dissolution, cavitation or foaming if present.
- Charging route (headspace injection or bubbling through the liquid), gas
  composition before charging, charging duration and waiting time, and
  temperature/absolute pressure immediately before opening. A dissolved-CO2
  measurement and an image showing whether pre-existing bubbles remain would
  distinguish a pressurized liquid from an initially expanded foam.

## Executed reduced-model results

The corrected hydraulic-reference bundle is
`results/runs/i4f-reduced-20261023T205747.576470Z/`. It preserves CSV histories,
input and source hashes, summary and plots. The previous bundle without an
entrance loss remains intact. The model uses the explicitly assumed effective
orifice `K_valve = 1/(Cd a(t))²`, with Cd = 0.7 and a smoothstep effective-area
opening. This is not a measured butterfly-angle curve. The transition loss is
an assumed K = 0.2 and the sharp tank-to-pipe entrance uses K = 0.5, both on
pipe velocity. [Sellevold et al., Table 2](https://doi.org/10.1061/JIDEDH.IRENG-10219)
provides a square-edged reservoir-entry analogue for the latter; its geometry
and steady tests do not constitute I4F calibration.

| Thermal exponent | Opening time (s) | Pipe-crown event (s) | Peak flow (m³/s) |
| --- | --- | --- | --- |
| 1.00 | 0.50 | 1.14 | 0.910 |
| 1.25 | 0.10 | 1.04 | 1.020 |
| 1.25 | 0.50 | 1.23 | 0.867 |
| 1.25 | 1.00 | 1.47 | 0.735 |
| 1.40 | 0.50 | 1.29 | 0.843 |

For the illustrative n = 1.25, 0.5 s case, peak nominal nozzle speed is
5.78 m/s and peak liquid momentum flux is approximately 5.00 kN. About
747 kg has discharged when the geometrical entrance event is reached; this
quantity is fixed by tank geometry and the selected termination condition,
not independently predicted gas entrainment. The model ends with 0.351 m³
tank water and the initially full 0.1984 m³ line still present. It does not
model the subsequent gas/liquid discharge.

At peak flow the modeled pressure contributions are approximately 324 kPa
valve, 78 kPa entrance, 31 kPa transition, 17 kPa outlet kinetic head and
7 kPa straight-pipe friction. These are algebraic closure predictions, not CFD
pressure taps. They suggest that opening history and valve/entrance treatment
deserve more attention than tuning pipe roughness. The loss assumptions still
need the complete CFD comparison; they must not be fitted to force agreement.

Halving the reduced-model step from 0.1 to 0.05 ms changed the selected event
time by about 1e-10 relatively and peak flow by about 1e-8. This establishes
insensitivity at these small steps for this model; it says nothing about CFD
resolution or physical closure accuracy. Seven focused tests pass, including
the independent constant-head solution
`Q = sqrt(dp/b) tanh(t sqrt(dp b)/I)` and its integrated volume, the variable-area
line momentum integral and a laminar pipe-flow limit. Inventory and polytropic
identities also close, but are substantially built into the state definition.

Primary butterfly measurements from
[Ishikawa and Yamashita, Figs. 6 and 9](https://doi.org/10.5988/jime1966.20.20)
show that real K(angle) depends on disk geometry and is not established by this
effective-area law. The available 200 mm valve curves cover 30–90° and do not
justify near-closed extrapolation. They are retained as source evidence, with
the I4F disk and actuation history still unknown. A scalar valve model will
remain limited even after using a better bulk loss curve.

An identified startup mismatch must be retained in comparisons: the original
reduced runs start at zero effective valve opening, whereas CFD imposes a
minimum 2% area fraction to regularize the resistance. That is a finite bleed,
not an actually sealed valve, and lasts until the smoothstep exceeds 2%.
Matching the algebraic K law alone therefore does not match startup. The
corrected reduced campaign now uses the same clipped 2% floor in
`results/runs/i4f-reduced-20261023T230314.651620Z/`. The shared input explicitly
declares this floor for future runs. At n=1.25 and a 0.5 s stroke, the model's
crown-event time changes from 1.227635 s (closed start) to 1.227029 s (clipped
floor), about 0.049%; this does not establish three-dimensional insensitivity.
The first override bundle,
`results/runs/i4f-reduced-20261023T224707.490442Z/`, instead used an affine
opening `0.02 + 0.98*command`. That is a different actuation law and must not
be labeled matched to CFD's `max(command,0.02)`. Its raw results remain
preserved, but its event-time comparison is superseded. Neither law establishes
the real valve leakage.

The coarse CFD trajectories now reach a sampled nozzle-gas endpoint, as
described below. An exact-state animation of the original non-transonic
trajectory is available at
`results/runs/i4f-visual-baseline-10x-corrected-20261023T224002Z/i4f-discharge.mp4`.
It holds ten saved fields through 0.41112674 s for their physical intervals
at 10x-slow playback; it does not interpolate evolving fluid states.
The timestep/Courant, valve-opening and exterior-boundary comparisons are now
reported below, together with the completed full-event refined-mesh audit.

## CFD formulation and focused numerical comparisons

The executed complete-apparatus cases use OpenCFD v2512
`compressibleInterFoam`: non-isothermal ideal-gas air, constant-density water,
SST RANS with wall functions and a coded implicit valve-loss zone. There is
no imposed liquid inlet. Wall layers and a resolved butterfly disk are absent;
wall-function suitability and near-wall resolution remain limitations.

The corrected 146,354-cell geometry has measured near-exit passage areas
within 0.047% of the intended area. The preceding 13% loft pinch was a geometry
error, not a physical contraction; its failed attempts remain preserved.
The corrected coarse mesh retains 1,435 concave cells. The 642,480-cell mesh
retains 643, with maximum nonorthogonality reduced from about 65 to 51 degrees.
Neither mesh is declared adequate from quality statistics alone.

The refined cold-start prefix completed to 0.35 s and its continuation reached
the sampled nozzle-gas stop at 0.41277429 s. Its three-stage ledger audit is
complete with coverage limits stated below. Both numerical
references use transonic pressure coupling, GAMG/GaussSeidel pressure solves,
Euler time integration, two outer/two pressure corrections, one alpha cycle,
maximum timestep 0.25 ms and Courant/interface limits of 0.5/0.25. This promotes
the tested pressure and temperature solver corrections into a common method;
it is not a comparison with the earlier non-transonic trajectory at otherwise
identical numerical settings.

Both grids use the same geometric box-based initial fill. Their native tank
water inventories are 1.082598 versus 1.087701 m³ (fine versus coarse), a
0.469% difference from discretizing the interface; total stored water differs
by 0.340%. No renormalization or field mapping was applied. Compare normalized
drawdown as well as absolute quantities, and disclose this initial-condition
confound before attributing a change solely to resolution.

Native water-balance measurements use one alpha cycle and the right-endpoint
Euler integral of the conservative boundary phase flux. Earlier two-subcycle
logging captured the last subcycle rather than its full-step average and
cannot establish that ledger. Outlet sampled-plane velocity integrals are
useful flow diagnostics, but are not the conservative solver face flux.

## Early hydraulic cross-check and current sensitivity evidence

The corrected reduced/CFD comparison uses the same clipped valve law without
fitting any resistance coefficient. At 0.3 s, before gas enters the pipe, the
adiabatic n=1.4 reduced case gives 709.0 kPa headspace pressure and
0.6736 m³/s whole-column flow, compared with 714.4 kPa and an approximately
0.6982 m³/s nozzle flow from CFD. Tank drawdown is 87.54 versus 93.55 L.
The original analytical initial tank inventory is 1.099557 m³ versus
1.087701 m³ on the coarse CFD grid; these differences must accompany the
comparison. The single-liquid model also cannot represent the initially
prefilled line's temporary partial wetting and ambient-air intrusion.

The inspected figure and data are in
`results/runs/i4f-reduced-cfd-overlay-20261023T225942Z/analysis/reduced-cfd-overlay-matched-floor-v2/`.
It includes n=1, 1.25 and 1.4 rather than choosing an exponent by fitting CFD.
At 0.3 s the CFD headspace is about 5.15 K warmer than the constant-mass
adiabatic prediction based on its own initial inventory and changing volume.
The approximate closed-headspace first-law diagnostic gives
`delta U + integral(p dV) = 19.70 kJ`, using four saved states and a sparse
trapezoidal work integral. This is apparent subsystem heat/work accounting,
not a measurement of physical interfacial heat transfer or a global energy
closure. Sparse valve-drag integration gives about 49 kJ of removed resolved
mechanical work on the same interval; its thermal partition cannot simply be
assigned to the upstream gas.

At the common 0.2 s field, the fine mesh gives nozzle flow 0.4234 versus
0.4397 m³/s on the coarse mesh, a 3.70% reduction, while headspace pressure
is 822.6 versus 818.4 kPa. Each run's tank-gas mass drift remains below 0.01%
through this early interval. Initial fine gas mass is approximately 1.59%
higher and tank water about 5.10 L lower than coarse because of geometry and
interface discretization; this is not an inventory-matched convergence study.
The completed refined prefix also reaches the port-gas marker at
0.31773099 s versus 0.31477096 s coarse. Root inspected its actual 0.35 s
mid-plane alpha slice: gas extends from the tank headspace into the upper
pipe while the nozzle remains liquid-filled. The same early-ingestion
mechanism is therefore present on both meshes; quantitative endpoint
sensitivity is reported below. A single slice does not establish a swirling
vortex or a three-dimensional topological classification.
The full solver logs show 812 steps through 0.2 s in each case, with initial
step about 12 microseconds and median/maximum step 0.25 ms. First-law apparent
heat at 0.2 s changes from 6.90 kJ coarse to 4.61 kJ fine, so even this early
thermal diagnostic is resolution-sensitive.

The slower 1.0 s valve case has a startup tradeoff already visible before its
event: at 0.1 s the nozzle's area-weighted liquid fraction is about 0.684,
versus 0.941 for the 0.5 s stroke. By 0.3 s it is nearly fully wet, with
approximately 0.297 m³/s nozzle flow versus 0.698 m³/s for the faster opening.
These early air fractions come from the exterior, with the pipe still liquid;
they are not tank-gas breakthrough. Compare eventual delivery and uniformity
at matched upstream depletion, as well as clock time, before favoring either
stroke. The completed longer-exterior comparison now extends through the
nozzle-gas endpoint, as reported below.

## Where the pressure goes before gas ingestion

The pressure comparison uses adjacent area-weighted static-pressure taps:
x=2.2–2.6 m brackets the valve; x=2.6–4.49 m covers the remaining straight
pipe and transition. These intervals do not overlap. A static pressure
difference includes acceleration and changes in velocity head, so it is not
alone a dissipative loss. For the reduced-model tap mapping, use
`delta p_static = delta p_loss + I_segment dQ/dt`
`+ rho(U_right²−U_left²)/2`, with the segment lengths stated explicitly.

| Time (s) | CFD valve-bracket drop (kPa) | Reduced mapped drop (kPa) | CFD post-valve-to-lip drop (kPa) | Reduced mapped drop (kPa) |
| --- | ---: | ---: | ---: | ---: |
| 0.1 | 703.7 | 719.1 | 59.4 | 56.0 |
| 0.2 | 587.7 | 610.5 | 37.4 | 48.5 |
| 0.3 | 424.0 | 475.3 | −33.0 | −12.1 |

The negative downstream difference at 0.3 s is pressure recovery, not negative
dissipation. CFD recovers about 45.5 kPa from the near-pipe-end tap at x=2.9 m
to the lip. The expanding area decelerates the liquid, while the accelerating
column also consumes pressure; the reduced full-column inertia contributions
are 87.6, 108.6 and 76.9 kPa at these times. Valve restriction dominates the
early pressure budget under the assumed opening law. Quantitative downstream
differences, especially near startup or low pressure recovery, remain material;
no coefficient was fitted to force agreement.

At these saved states the transition contains approximately 148.8 L water.
Its native-volume-weighted fraction with axial speed below −0.1 m/s is
effectively zero, as are reverse-flux fractions on the selected transition
cuts. Root inspected the actual 0.2 s wetted mid-plane, whose minimum axial
speed is 2.10 m/s. Strong resolved reverse flow in the unvaned transition is
therefore not supported by these samples. This does not exclude weaker or
unresolved near-wall separation, and does not represent the five actual plates.
The computed slice, separate pressure terms, tap mapping and provenance are in
`results/runs/i4f-hydraulic-component-recirculation-20261024T005301Z/`.

## Completed mesh sensitivity through the gas marker

The 642,480-cell calculation ended normally at 0.41277429 s after the same
origin-gated, three-record nozzle-gas criterion as the 146,354-cell reference.
Its last-below/first-above bracket is 0.41268970–0.41273975 s, versus
0.41099234–0.41104607 s coarse. Confirmation shifts by 1.6924 ms, or 0.412%.
Both meshes retain the early local gas-ingestion mechanism while substantial
water remains; neither the sampled threshold nor its confirmation is a
universal physical end of useful discharge.

At exact common saved times, the numerical differences are:

| Observable | Coarse | Fine | Interpretation |
| --- | ---: | ---: | --- |
| Nozzle water flow at 0.2 s, m³/s | 0.43969 | 0.42340 | −3.70% |
| Nozzle water flow at 0.4 s, m³/s | 2.60203 | 2.57373 | −1.09% |
| Wet-area velocity CV at 0.4 s | 0.18997 | 0.14454 | −23.9%; spatial quality is still mesh-sensitive |
| Forward normal water momentum at 0.4 s, kN | 46.892 | 45.205 | −3.60% |
| Maximum water-ledger residual, % initial water | 0.02912 | 0.02496 | Coverage is from the first recorded endpoint |

This is sensitivity evidence, not formal grid convergence: total initial
water differs by 0.3404% and headspace gas mass by 1.59%. The fine run also
changes from six to twelve ranks at 0.40616514 s after an exact cell-field and
native-inventory restart check. All three stages are explicitly stitched;
21 overlap checks have no mismatches, and all 5,671 logged solver steps have
consistent time increments. Water accounting integrates 5,670 intervals from
the first logged endpoint at 11.99904 μs. Its unintegrated startup inventory
change is 3.84e-8 m³. The fine gas ledger begins at the first saved state with
complete subsequent mass-flux coverage, 0.1 s, and has maximum residual
0.662 g; the excluded 0–0.1 s gas-storage change is −6.667 g. It is not a
startup-to-end gas balance.

Neither the coarse nor fine inspected states reach the 10 kPa pressure floor
or nonpositive temperature. At the fine endpoint, water-core minimum pressure
is 86.45 kPa and minimum temperature 291.12 K; air-core minimum temperature is
240.65 K and maximum speed 291.83 m/s. Gas Mach number reaches about 0.95 near
0.4 s. This near-sonic interval remains a demanding exploratory result.
The corrected EOS diagnostic compares solver mixture density against
`alpha*rho_water + (1-alpha)*p/(R_air*T)`, using raw alpha and exact case
constants; gas-core median and 95th-percentile discrepancies are about 1 ppm.
Comparing mixture density directly with pure-air density would confound EOS
error with the small water fraction and was corrected in the archived audit.

The [computed mesh-comparison plot](../results/runs/i4f-fine-endpoint-comparison-20261024T032115Z/plots/fine_l2_history.png),
raw stages, source hashes, comparison CSV/JSON, coverage and corrected EOS
diagnostics are in `results/runs/i4f-fine-endpoint-comparison-20261024T032115Z/`.
The primary implication is that bulk discharge and marker timing are more
robust than the predicted spatial uniformity; no actual lamella performance
or experimentally verified sheet quality follows from this comparison.

An independent audit of the full coarse log and all three raw fine-stage
logs finds 22,676/22,684 pressure solves, respectively. Every logged final
pressure residual is below the configured absolute tolerance 1e-7; maximum
iteration counts are two/three. Velocity components also finish below 1e-7,
with at most two iterations. No warning/fatal/nonconvergence records or U/T
200-iteration cap hits appear in these completed trajectories. The fine
stitched `Time`/`deltaT` log contains no solve residuals; the audit uses the
manifest-listed raw logs rather than inferring convergence from that file.
Temperature has tolerance 1e-8 **or** relative reduction to 1% of its initial
normalized residual, including `TFinal`. Many T solves stop by the relative
criterion: the largest fine final residual is 8.565e-4 from initial 0.9967,
about 0.086% of that initial value. It is incorrect to say all T solves meet
absolute 1e-8. These are normalized algebraic residuals; they establish neither
convergence of the two fixed PIMPLE outer iterations nor physical or total
energy accuracy.

## Completed timestep/Courant sensitivity

The cold-start comparison halves maxDeltaT from 250 to 125 μs, maxCo from
0.5 to 0.25, and maxAlphaCo from 0.25 to 0.125. Mesh, initial fields,
thermodynamics, valve law and numerical schemes are unchanged. It therefore
tests joint timestep controls rather than an isolated fixed-step change.
Through t=0.4 s the logged step count rises from 5,061 to 10,081; median
deltaT falls from 23.35 to 11.62 μs. These actual histories confirm that
Courant limits, not only the maximum-step setting, control the late trajectory.

| Observable | Halved-control change at exact t=0.4 s |
| --- | ---: |
| Native upstream water depletion | −2.023 L (−0.916%) |
| Sampled nozzle water flow | −1.685% |
| Mass-weighted headspace pressure | +0.254% |
| Wet normal-velocity CV | −1.60% |
| Forward normal water momentum flux | −3.45% |

The gas-marker confirmation/checkpoint shifts from 0.41108189 to
0.41198123 s (+0.89934 ms, +0.219%). Native depletion at those distinct
endpoints is 253.60065 versus 254.11817 L (+0.204%); sampled endpoint water
flow differs by +1.14%. Thus the timing and delivered-amount conclusions are
insensitive to this tested change relative to the much larger valve/orientation
effects. This is not proof of temporal convergence for every local quantity:
the near-pipe-end absolute-pressure cut changes by +12.76% at t=0.4 s,
whereas other selected pressure cuts change by approximately 0.2–3.6%.

Both native water ledgers cover every required step; maximum residual decreases
from 0.0291% to 0.0167% of initial water. The reference gas-flux record has
184 unmatched phase-water startup rows because rhoPhi logging starts at
0.043252806 s; exact timestamp joins and the 0.05 s gas-storage reference
are retained. No missing gas prefix is zero-filled or interpolated. Endpoint
field comparisons retain their actual unequal times. Frozen comparison tables,
actual timestep distributions, source references and inspected plot are in
`results/runs/i4f-matched-dt-halved-pair-retry4-20261024T023228Z/`.

## Completed external-boundary sensitivity

Extending the exterior from 2 to 4 m changes the mesh from 146,354 to 176,247
cells while retaining the apparatus, initial-state prescription, gas state,
valve law and numerical profile. The first native solver-sample water
inventories differ by 21.39 mL; this small difference is disclosed rather than
removed by fitting. At the exact common saved field t=0.4 s:

| Observable | Change with the 4 m exterior |
| --- | ---: |
| Native upstream water depletion | +0.174 L (+0.079%) |
| Headspace mean pressure | +0.280 kPa (+0.046%) |
| Sampled nozzle water flow | +0.0127 m³/s (+0.486%) |
| Wet normal-velocity CV | −0.000258 |
| Forward normal water momentum flux | +0.965% |

The operational gas-marker confirmation shifts from 0.41108189 to
0.41122637 s (+0.0351%). The longer-domain saved endpoint is 0.41124423 s,
one 17.86 μs step after its marker; endpoint field comparisons retain those
actual unequal times. No water crosses the far exterior boundaries at the
compared snapshots. This supports small boundary sensitivity for these
observables through this event, not independence for arbitrary later descent.

The native water ledgers cover every logged post-reference step, with maximum
residuals 0.3743 L (2 m) and 0.3668 L (4 m), or 0.0291% and 0.0285% of
initial water. Both water references are the first common solver sample at
1.199904e−5 s, excluding the initial unsampled interval. The 2 m gas ledger
starts at the exact saved field 0.05 s because native mixture boundary flux
logging began later than startup; its maximum subsequent residual is 1.265 g.
The 4 m gas ledger starts at t=0 and has maximum residual 0.3205 g. Different
references and the additional exterior air prevent comparing their absolute
domain gas inventories as equal initial quantities. Earlier unavailable
coverage reports were preserved after a justified correction for printed-time
rounding; missing or nonfinite flux records remain rejected.

Frozen fields, commands, provenance, tabulated comparisons and the inspected
plot are in
`results/runs/i4f-external-L2vL4-endpoint-analysis-20261024T003650Z/`.

## Completed valve-opening comparison

The cold-start 0.5 s opening reference and 1.0 s opening case both ended
normally after the origin-gated nozzle-gas marker. Their written endpoint
times are 0.41108189 and 0.61891382 s. Mesh, initial fields, pressure,
temperature, nominal payload and numerical controls were matched; only the
opening time changed. Both use the same clipped 2% minimum effective area.

At the horizontal reference endpoint, tank water falls from 1.08770064 to
0.935250101 m³, while line water falls from 0.197696957 to 0.0965468481 m³.
The line's net inventory decrease is therefore 101.15 L, approximately 39.9%
of the total 253.60 L upstream-depletion budget, while about 86% of initial
tank water remains. This is a storage-balance contribution, not a tracer-based
statement about the material origin of individual discharged parcels. It
shows why the initially primed passage and separate tank/line inventories
matter to the apparent liquid-only delivery interval.

Native upstream water depletion, `D(t) = V_tank(ref)+V_line(ref)`
`-V_tank(t)-V_line(t)`, is 0.25360065 versus 0.26114604 m³ at those endpoint
checkpoints, or approximately 253.14 versus 260.68 kg. Its reference is the
first common native-volume sample at 1.199904e-5 s. This is delivery across the
mesh partition near x=4.5 m, including initially stored line water; it is not
water escaping the far box boundary or an exact x=4.49 m face-flux integral.
Slower opening increases the time to the marker by about 50.6%, but endpoint
depletion by only 2.98%. That modest delivery change still needs the grid/time
checks, while the longer startup with partial nozzle wetting is already visible.
No claim of increased total discharge efficiency follows: substantial water
remains in both tanks, and this first calculation stops at an operational
gas-fraction marker, not at emptying or a demonstrated end of useful foam flow.

The complete raw-observer comparison is in
`results/runs/i4f-slowvalve-20261023T222641Z/analysis/pair-endpoint-v4/`.
At the reference endpoint's native D, the nearest slow-case raw sample is
only 22.9 mL above the same delivery target. Its nozzle water flow is
2.339 versus 3.479 m³/s. Dense per-step observers show the slow nozzle still
essentially all water there; interpolating sparse cut statistics across the
abrupt gas front had given a misleading gas fraction and is superseded.
Velocity CV and momentum comparisons therefore use only actual saved fields,
with no claimed matched-D CV ranking at an unsaved slow-case time.

The inspected current reference movie is
`results/runs/i4f-slowvalve-20261023T222641Z/render-reference-10x-slow-motion/i4f-discharge.mp4`:
ten distinct saved states, 124 frames at 30 fps, 4.1333 s encoded duration
for 0.41108 s of physics (10.055x slow motion). States are held between
outputs rather than synthesized. Incomplete early postprocessing and two
mistaken fast-playback exports remain preserved and explicitly superseded.

## Vertical comparison, failed continuation and initial-state limitation

The vertical CFD geometry was executed as an additional exploratory
arrangement. It later failed numerically near 0.867 s, without a valid
nozzle-gas endpoint. The saved earlier interval is being audited separately.
Saved minimum pressure falls from 14.344 kPa at 0.30 s to exactly the imposed
10 kPa floor at 0.35 s; this brackets first saved activation, not its exact
onset. Later snapshots cannot support physical outlet-quality or delivery
comparisons, even while temperature, density and EOS consistency remain
apparently healthy. Neither a final payload improvement nor full-discharge
stability is established. The [0.4 s arrangement image](../results/runs/i4f-orientation-historyfix-20261024T0304Z/orientation-pair-t-0.4s-native-volume.png)
is retained as a diagnostic of the computed states: its vertical panel is
already pressure-clamped and must not illustrate a validated physical benefit.

Through the last saved state above the floor, 0.30 s, vertical tank/line
depletion is 93.838 L versus 93.554 L horizontal (+0.30%), and sampled nozzle
water flow is 0.70130 versus 0.69820 m³/s (+0.44%). Exact saved-field pressure,
nozzle flow, wet fraction, CV and momentum angle at 0.20 s differ by less than
about 0.5%. The vertical water ledger covers all 1,471 intervals through
0.30 s, with maximum residual 33.4 mL (0.00260% of initial stored water).
The minimum-pressure cells at 0.30/0.35 s are pure liquid, near 293.3 K,
with consistent density; gas EOS consistency does not clear this liquid
pressure clipping. The floor's activation is not evidence of cavitation.
The run ultimately fails at 0.86702446 s with a negative temperature; its
last saved 0.85 s state is excluded. The [pre-floor comparison plot](../results/runs/i4f-vertical-matched-flow-prefix-analysis-20261024T032500Z/pre-floor-comparison/pre-floor-comparison.png),
health fields, native histories and coverage records are preserved in
`results/runs/i4f-vertical-matched-flow-prefix-analysis-20261024T032500Z/`.
Its cylinder occupies z=0.5–2.5 m, with the same
diameter/length and outlet bottom clearance as the horizontal reference.
The pipe/nozzle remain horizontal; their connection enters the curved tank
side rather than the original end cap. Thus this compares idealized complete
arrangements, not a gravity-only rotation of an otherwise unchanged junction.

Native initial total water is matched to the horizontal 1.28539771485 m³
within 3.2e-8 m³ using a geometric cut-cell plane at z=1.88795853 m.
Pressure and temperature remain 900 kPa absolute and 293.15 K; the remaining
0.0923% headspace-volume difference is disclosed rather than removed by changing
those inputs. The reference used box-based initialization, so the change in
interface representation is also a comparison limitation. Root inspected the
actual mesh, alpha and pressure images before launch. The nominal 70%-fill
preparation and failed startup attempts remain preserved separately.

A raw comparison at matched upstream depletion was initially reported before
the terminal failure audit. It is **withdrawn as physical evidence** because
the pressure floor is already active by 0.35 s. For traceability, the raw row
at t=0.49483455 s gives
D=0.253601360 m³, within 0.712 mL of the horizontal reference endpoint's
D=0.253600648 m³. The vertical port remains fully water-filled by the sampled
area observer, versus the horizontal case's established tank-gas discharge.
Its nozzle water flow is 0.8891 m³/s versus 3.4787 m³/s at that horizontal
row; the same depletion takes approximately 20.4% longer. These are numerical
outputs from a pressure-clamped trajectory, not demonstrated delayed gas
ingestion or a physical throughput/time tradeoff. Vertical nozzle
area-mean alpha is 0.997415; its signed sampled `Q_mix−Q_water` is negative
(−0.0003215 m³/s), which may reflect counterflow and/or separate interpolation
and must not be presented as an outward gas fraction. No CV or saved-field
shape was interpolated to this raw matched-D time. Exact rows, hashes and
failed-prefix analysis are in
`results/runs/i4f-vertical-matched-flow-comparison-20261024T010013Z/`.

All current references start with a water-filled pipe/transition. This is a
declared primed-line transient, not a prediction that an open downstream pipe
would remain full during a long charging wait. Its inventory materially affects
startup and the later water-flow surge. Whether the real post-valve passage
drains, retains pockets, or has a closure is unconfirmed and has been asked of
the user. A different initial downstream inventory needs its own case; these
results must not be transferred unchanged to a dry-start device.

A geometry-only hydrostatic screen quantifies that uncertainty. With an ideally
closed valve at x=2.4 m and an open, vented nozzle, the lowest exit lip is
z=0.575 m. The modeled post-valve passage holds 178.78 L when full; only
16.32 L lies below that drainage level, leaving 162.46 L potentially drainable.
This is a static water/air geometry calculation, not a prediction of the actual
charging sequence or drain time. It excludes lamellae, capillary retention,
retardant rheology, foam, unknown closures and valve leakage. Its frozen-STL
reconstruction and independent integration checks are preserved in
`results/runs/i4f-initial-retained-water-screen-20261024T002835Z/`.
The surface-integrated whole-line volume is 198.419 L versus 197.697 L in
the native CFD line zone; that 0.722 L representation difference is disclosed.
The refined mesh's independently recorded initial line inventory is 198.424 L,
within 0.0051 L of the surface integral, consistent with a coarse geometric
representation error. This comparison does not establish dynamic convergence.
The existing 2% minimum-opening CFD cannot represent a long, ideally sealed
pre-discharge wait.

A conditional drained-start CFD attempt then kept the original tank/upstream
fields and mesh, with a geometric liquid plane at z=0.575 m downstream of
the valve and ambient-pressure gas above it. Native downstream water was
16.10 L; tank water remained 1.08770063 m³. Initial exterior phase-boundary
values were restored to the air-only reference after image inspection.
This attempt failed at t=0.018856141 s because the solved temperature became
negative (−0.00243 K), before any positive-time field checkpoint. Its output
is not a usable physical discharge result. The failure is preserved in
`results/runs/i4f-partial-drained-cutplane-20261024T004933Z/`; a same-input,
short instrumented reproduction failed similarly at 0.019507837 s and located
the collapse in a downstream gas-rich cell, while water remained near 293 K.
An early valid state has a local characteristic acoustic crossing ratio
`c deltaT / V^(1/3)` around 6 despite small advective Courant number. This is
an accuracy/stability diagnostic, not proof of an acoustic-Courant requirement
for this implicit solver.

An isolated initialization comparison then preserved the original valve-zone
pressure taper through x=2.45 m instead of allowing later downstream masks to
overwrite its right half. The corrected p_rgh was recomputed consistently;
alpha, temperature, velocity, mesh, valve and solver controls were unchanged.
The changed initial pressure adds approximately 4.99 g of ideal air locally,
which is disclosed. This probe ended normally at 0.029986769 s: gas-rich
temperatures 255.5–296.2 K, no pressure-floor cells, gas Mach maximum 0.406,
and mixture-density/EOS relative discrepancy about 1e−6. The native water
ledger residual was −10.79 mL, or −0.000960% of initial water. This supports
the overlapping pressure initialization as a contributor to the earlier
failure; it does not prove long-run stability or a uniquely physical valve
initial state. The successful probe and its endpoint audit are preserved in
`results/runs/i4f-partial-drained-valve-taper-sensitivity-20261024T010920Z/`.
Its continuation subsequently failed at 0.061140301 s with negative
temperature. Before termination, monitors report approximately 1407 m/s,
12.45 MPa and a gross native water-balance residual of 1.955 m³ against
1.123 m³ initially. That segment is invalid even though alpha remains nearly
bounded. It never arms the tank-gas marker, and no full fields were saved
after the 0.029986769 s prefix. Evidence is preserved in
`results/runs/i4f-partial-drained-taper-cont-terminal-analysis-20261024T025953Z/`.

Separately, the original abrupt-pressure initialization with a 10 μs timestep
cap remained healthy through 0.02943 s (budget stop): minimum temperature
approximately 292.85 K, with the original initial p/p_rgh/T/U/alpha/V hashes.
It uses two rather than four ranks, so this is not a perfectly isolated
timestep experiment. It nevertheless shows that pressure smoothing is not
the only route through the early failure interval, and cannot establish that
the original pressure state was physically invalid. The focused blocker
review therefore selected a fresh four-rank replay changing only maxDeltaT
to 10 μs, with a 0.08 s target, dense diagnostic field capture and a
90-minute budget. This replay passed the old failure interval with positive
temperature and density, but its guard detected pressure-floor activation
at an observed 0.03354 s and captured a normal-End checkpoint at 0.03356 s. It did not
reach the 0.08 s target. The last guard observation has temperature
292.75–293.55 K, fixed headspace gas-probe EOS error below 1e-6 and water
residual −19.54 mL. A full per-step audit places the first raw pressure-floor
sample earlier, at 0.03329 s, with six intermittent hits before the guard
action. Thus a small step addresses the early temperature collapse but does
not yet establish a usable drained-start run.
Momentum, energy, EOS and physical inputs remain unchanged. No temperature
floor or unverified valve sign change was applied.
The current conclusions therefore remain conditional
on the primed-line reference until this alternative is resolved or bounded.

A paired restart comparison from the same launch-hashed 0.030 s native
checkpoint then changed only momentum convection to first-order upwind, with
an unchanged-scheme restart as control. Both reach the pressure floor: first
raw samples are 0.03312 s upwind and 0.03342 s control, at
`(2.4875, 0.0845778349, 0.565447861) m`. One original-run record instead
selects the approximately mirrored negative-y cell. Upwind does not remove the
issue. Comparing either restart with the uninterrupted parent also includes
runtime initialization/cache effects; these timings do not establish a
simple order-of-accuracy benefit.

In that paired comparison, no full field was saved at the trigger instants.
At the common 0.032 s
snapshot, the nearest cell is pure water at about 100.7 kPa and 293.151 K;
later terminal snapshots have recovered local pressure and no local floor
cells. The trigger's phase, temperature, density, velocity and spatial extent
were therefore unknown. It would be incorrect to assign the recovered state's phase
to the unsaved trigger or call this evidence of cavitation. Exact
0.030–0.032 s restart-relative ledgers cover 200 steps: water residuals are
−2.37 to −2.50 mL and EOS gas residuals +0.235 to +0.242 g. The
[pressure/phase neighborhood diagnostic](../results/runs/i4f-transport-order-final-comparison-20261024T035856Z/pressure-alpha-valve-neighborhood.png)
and exact raw event records are in
`results/runs/i4f-transport-order-final-comparison-20261024T035856Z/`.
A subsequent repeat saved every timestep and captured the actual event at
0.03342 s. Exactly two of 146,354 cells reach the floor, at the mirrored
locations: each has native volume about 5.406e-6 m³, alpha_water=1,
T=293.151 K, rho=998.2 kg/m³ and speed 0.334–0.336 m/s. Their pressure is
188.6/218.8 kPa one 10 μs step earlier and 122.2/100.7 kPa one step later.
The phase-weighted EOS discrepancy at the floor cells is about 1.2e-8. This
captures a transient pressure excursion in liquid, rather than cold-gas EOS
collapse; it does not establish its physical or numerical cause.

Native checkMesh quality does not identify an obvious bad-cell explanation
there: neither trigger cell nor any incident internal face is concave;
maximum incident internal nonorthogonality is 28.9° and absolute skewness
0.167. The one pipeWall boundary face per cell has an uninformative calculated
zero sentinel, so its corresponding face-quality metrics remain unmeasured.
The [joint pressure/phase image](../results/runs/i4f-pmin-trigger-field-capture-20261024T0416Z/analysis/trigger-diagnostics-v3/trigger_pressure_alpha_slice.png),
co-located cell table, native volumes and mesh-quality outputs are in
`results/runs/i4f-pmin-trigger-field-capture-20261024T0416Z/`.

## Post-breakthrough continuation and duration limitation

A same-physics coarse continuation attempted to advance from the accepted
0.41108189 s checkpoint to 0.50 s. A 4→16→4 preflight reproduces the cell
fields and phi bitwise; alphaPhi0.water is verified only by matching the three
open-boundary integrals within 2e-15 m³/s, not by a full face-value comparison.
The pilot stops at 0.41201293 s after 52 steps when the guard detects pressure
floor hits at 0.41194124 and 0.41195916 s in the transition. A subsequent
extremum reaches 2.0345 MPa at 0.41197708 s; this is not the final field's
maximum. The final global pressure range has recovered to 71.94–599.04 kPa.
The scalar trigger records do not supply joint phase information at those
transition cells.

Through the stopped interval, native water residual is +1.46 mL and gas
residual +4.98e-5 kg relative to the actual checkpoint inventories. Final
sampled nozzle water/mixture flows are 3.3409/3.6891 m³/s, after the clipping
events; these are diagnostic outputs, not a validated tail-discharge history.
The run takes 8.20 s wall at 16 MPI, with about 708 MiB peak container memory.
Small mass residuals and normal solver End do not clear the pressure issue.
Raw events, hashes, restart references and the complete checkpoint are in
`results/runs/i4f-post-marker-tail-20261024T0418Z/`.

Those focused continuations are now complete. Two versus four PIMPLE outer
iterations first reach the final-field 10 kPa floor at 0.41194198 and
0.41195990 s respectively. The half-timestep/Courant trajectory also reaches
the floor, at 0.41203465 s. Changing only momentum convection to upwind in
the post-ingress restart reaches it earlier, at 0.41130064 s. These controls
do not establish a cure. Their small bulk-flow differences before the event
also do not justify ignoring its large local pressure effect.

The fine reference continues through 0.41499626 s with no final-step floor
hit, but its next extension captures one at 0.42001293 s. The affected cell
has alpha_water=0.99996495, temperature 292.796 K and density 998.165 kg/m³.
Its native volume is 1.802e-6 m³. The simultaneous global temperature minimum
of 219.289 K occurs in gas-rich fluid, with alpha_water about 4e-6; water-core
temperatures remain above 291 K. This is not computed freezing of the water.
Refinement delays the event but has not removed it. Exact field diagnostics:
`results/runs/i4f-fine-pfloor-cell-thermal-20261024T0510Z/`.

### What the pressure floor hides

A trace from the original native four-rank t=0 inputs now establishes the
first floor contact on that trajectory. At 0.30541472 s, two fully liquid
cells near the pipe-to-transition junction have raw pressures 9.390 and
9.719 kPa at about 293.28 K. These are **positive absolute pressures**, above
the water vapor-pressure estimate at this temperature. The limiter raises
them to its arbitrary 10 kPa threshold. The later saved endpoint has a minimum
of 11.330 kPa; that later recovery does not establish convergence of the event
step. Its second and fourth pressure correctors keep the clipped state with
zero GAMG iterations because their normalized initial residual already meets
the configured 1e-7 tolerance. Twenty-four field/checkpoint hashes at 0.1,
0.2 and 0.3 s match the canonical reference byte-for-byte.

Thus first inner-floor contact is a diagnostic trigger, not automatically the
end of physical validity. A temporary safeguarded iterate may be acceptable
if the coupled solve converges to an admissible state satisfying the original
equations with an inactive constraint. Neither a later positive field nor a
small global mass balance proves that. Persistent bound activity instead
requires quantified equation defects and floor/convergence sensitivity before
claiming a physical history. This qualifies the earlier conservative stopping
rule without approving the unverified mixed-phase tail.

The original fine-mesh cold trace encounters a different event much earlier:
at 0.033256964 s, one fully liquid cell near the nozzle has raw pressure
−3.738 kPa in the first of four correctors. The next three correctors have
minima at 10 kPa; a later saved endpoint has 88.924 kPa. A negative intermediate
iterate has been demonstrated, not a converged negative state or physical
cavitation. The fine and coarse events occur at different locations, so their
times do not form a same-location convergence result. Neither trigger cell
belongs to the mesh's concave-cell sets; local nonorthogonality is about 17.8°
coarse and 41.8° fine. Those observations establish no mesh cause.
Data and exact event states:
`results/runs/i4f-cold-original-pressure-trace-20261024T0646Z/postrun-analysis/`
and `results/runs/i4f-fine-cold-pressure-trace-20261024T0712Z/`.

The coarse trace now has a mass ledger beginning at the actual native t=0
fields, rather than its first function-object sample. Native serial and
four-rank initial water inventories agree to 2.3e-13 kg at 1,283.084 kg.
All 1,324 Euler steps use their logged deltaT and right-endpoint flux on the
three physical open boundaries, including the first step; no t=0 flux is
invented. At the final 0.30563784 s checkpoint the residual is +0.06914 kg
water (0.00539% initial water), -0.000503 kg gas, and +0.06864 kg mixture.
Initial gas is EOS-derived because no t=0 mixture-rho field exists; its
22.943 kg covers the whole domain, including exterior air, while the tank
headspace contains 5.126 kg. Thus this is global accounting through the first
floor event, not an isolated headspace check or validation of clipped physics.
Reproducible native-field calculation and inspected plot:
`results/runs/i4f-full-start-ledger-20261024T091221Z/`.

The coarse event reproduces from its unchanged native 0.3 s checkpoint within
0.55 microseconds, at the same cells. The next focused comparison uses 10 and
5 kPa numerical floors with tighter pressure solves and up to 16 outer
corrections, recording full pressure-equation defects and successive outer
state changes. Five kPa is an admissibility sensitivity above vapor pressure
here, not a cavitation model.

Both coarse branches have now reached 0.310 s with tighter pressure solves
and 16 outer corrections per step. At 0.30543444 s, the 10 kPa branch clips
two liquid cells containing 14.9 mL, while the 5 kPa branch does not. The next
pressure pass rises to 10.289 kPa without clipping. Both endpoint fields have
minimum pressure 33.753 kPa and reported nozzle flow about 0.723839 m³/s;
late outer pressure changes fall to approximately 1e-4 Pa. This supports a
transient safeguard interpretation for this short early interval, rather than
an established persistent sub-floor state. It does not settle the later
gas-front problem or demonstrate full emptying. Eight-digit inventory output
limits small per-step mass comparisons; exact field and flux interpretations
remain qualified in the
`results/runs/i4f-floor-defect-pair-attempt3-20261024T073345Z/analysis/` bundle.

The added global matrix-residual measurement also required correction. In
the pinned parallel implementation, `fvMatrix::residual()` includes an extra
coupled-neighbor source contribution relative to the assembled operator.
The very large raw global max/L1 norms therefore are not the true pressure
defect. The corrected diagnostic removes only that extra coupled-patch term,
retains physical boundary sources/diagonals, and checks cellwise agreement
against `-V*(M & p_rgh)`. A short runtime check gives corrected and operator
maxima about 3.14e-7 m³/s, agreeing to 8.9e-15 m³/s, where the uncorrected
maximum was 9.87 m³/s. This fixes a diagnostic metric; neither the stock
pressure solve nor its original `dgdt` operator is changed. Original raw
results remain preserved. The corrected source and passivity checks are in
`results/runs/i4f-fine-floor-pair-prep-20261024T075705Z/`.

The corrected diagnostic solver has also been compared directly with the
pinned stock `compressibleInterFoam` executable over the coarse 0.300–0.310 s
interval. All 14 endpoint fields are byte-identical, including the floor
crossing. Observed wall time is 629.02 versus 591.40 s (+6.36%); the diagnostic
log is 22.76 times larger. The runs overlapped other work, so this is an
observed cost comparison rather than isolated scaling evidence. This supports
passivity over the tested segment, not general physical validity. Evidence:
`results/runs/i4f-stock-passivity-profile-20261024T081608Z/analysis/`.

The fine 10/5 kPa comparison supplies a useful but incomplete result. Both
branches complete 36 steps through 0.039258211 s with **no floor contact**;
minimum raw pressure is 79.644 kPa. Their logged nozzle/port/inventory
histories are identical. Thus tighter pressure solves and 16 outer corrections
remove the earlier fine-case pressure-floor event over this observed window.
Corrected operator/reference agreement is within 1.12e-14 m³/s; the final
solved max and unweighted L1 defects are 5.75e-7 and 1.92e-5 m³/s. This is
stronger evidence than merely obtaining bounded alpha or solver End.

However, an immutable 900 s in-container timeout terminates both runs during
the next step, despite extending the external guard. The 0.040 s target is
not reached, and no new full 3D endpoint is saved after the initial 0.030258211
checkpoint. Only complete-step logs are used; partial-step data are excluded.
Neither momentum/CV fields nor a later physical tail can be inferred from
these logs. Source and full qualifications:
`results/runs/i4f-fine-pair-timeout-analysis-20261024T0854Z/`.
The accuracy/cost pilot has now completed with eight and sixteen outer
corrections, matching checkpoint schedules, an explicit end writer and
consistent internal/external wall limits. Both arms end normally at
0.040008211 s, with ten exact common saved states from 0.030258211 s and no
pressure-floor contacts. All predeclared observable budgets pass: maximum
relative differences are 5.07e-6 for nozzle flow, 5.85e-6 for advective normal
momentum, 4.85e-7 for tank drawdown and 3.49e-10 for gas-volume-weighted
headspace pressure; wet-area velocity CV differs by at most 4.91e-6 absolute.
The internal-plane measures use interpolated computed fields, not conservative
boundary fluxes, and the smallest reported differences approach postprocessor
precision. Docker start-to-finish time is 607.2 versus 1,099.8 s, an observed
1.81x speedup under overlapping workloads rather than isolated scaling.
This supports eight corrections for the next exploratory fine segment;
it does not establish adequate coupling through later gas ingestion.
The stricter global field-change targets remain diagnostics, not retuned
acceptance criteria. Exact checkpoint comparison and inspected plot:
`results/runs/i4f-fine-outer8-vs16-20261024T0901Z/analysis/`.

The longer coarse continuation establishes a separate, persistent failure.
Both 16-outer branches stop on their declared clipped-water-support limit:
10 kPa at 0.31899862 s and 5 kPa at 0.31931753 s. Every one of the final
step's 32 pressure passes retains about 1.4–1.5 kg of clipped liquid. Raw
pressure minima remain about -650 kPa; the saved positive floor is therefore
not a converged admissible solution. The corrected maximum pressure-operator
defect is about 1.8e-7 m3/s before clipping and 1.4e-3 m3/s afterward, while
the unweighted sum of absolute defects is about 0.019–0.021 m3/s afterward.
Outer changes contract without clearing that constraint. Both runs save full
endpoints, but their planned extension is withheld. Evidence:
`results/runs/i4f-coarse-coupled-discharge-20261024T0856Z/stage1/clip-stop-audit/`.

An eight/sixteen-outer comparison before this failure agrees in exact common
scalar histories through 0.31489183 s. The nearest 3D fields are 118.48 us
apart, so their apparent 0.142% momentum difference cannot be treated as a
coupling error: the neighboring-time trend accounts for approximately all of
it. At the eight-outer 0.31500928 s endpoint, minimum water pressure is
31.47 kPa near the transition entrance, with local speed 15.34 m/s. An
approximate x=2.9–4.49 m section budget has +86.1 kPa liquid-inertia pressure,
-105.4 kPa bulk kinetic-head change and +6.6 kPa inferred residual, consistent
with the observed +12.8 kPa static recovery. This is not a steady loss
measurement. Later raw -650 kPa values occur at roughly the same liquid
speed, so the bulk kinetic-head estimate alone does not explain them or
establish physical cavitation. Local mesh checks find no obvious concavity
or large nonorthogonality at the identified cells. The next discriminating
test changes only the velocity gradient used by momentum convection, starting
both arms at the same last saved pre-floor checkpoint, 0.31593593 s.
Budget and inspected comparison plot:
`results/runs/i4f-coarse-outer8-pilot-20261024T0914Z/analysis/coarse8-vs-stage1-16/analysis/`.

That matched reconstruction test is now complete. The original control
reproduces its support-limit stop at 0.31899880 s; limiting only the convective
velocity gradient stops at 0.31902437 s. First raw floor contact shifts by
0.112 ms, but both retain roughly -650 kPa raw minima and 1.4–1.5e-3 m3/s
post-clamp operator defects. The limiter therefore does not remove the problem.
The vertical 16-outer diagnostic also develops persistent clipping while its
port has no detected gas flow, so headspace-gas ingestion is not necessary for
this numerical failure. A clean-start water-EOS/timestep comparison and the
corrected fine trajectory are the next discriminators. Pair evidence:
`results/runs/i4f-convection-gradient-pair-20261024T094505Z/analysis/`.

A private diagnostic build preserves the stock equations and records pressure
immediately before and after the actual solver operation
`p=max(p_rgh+(alpha1*rho1+alpha2*rho2)*gh,pMin)` inside each pressure corrector.
Pre-event hashes match the stock restart byte-for-byte for 658 field/time
pairs. This trace starts at 0.41108189 s; it does not certify that every
earlier corrector in the cold-start baseline avoided clipping. At
0.41194198 s the first unclipped minimum in this trace is −25.947 kPa absolute
in one almost-liquid cell; another corrector at the same time reaches
−2.825 MPa. The displayed 10 kPa minimum therefore conceals an inadmissible
pressure iterate, rather than measuring a physical saturation pressure.

Clipping also changes the incompressible-part pressure-equation face flux:
at the latter corrector, its maximum change is 0.002349 m³/s and its summed
absolute face change is 0.010993 m³/s. These are local algebraic diagnostics,
not a boundary mass ledger. `fvMatrix::residual()` here has integrated units
of m³/s, with the coupled-interface qualification just described; an earlier
additional cell-volume-weighted sum has units m⁶/s and is excluded from
physical interpretation. The scope is only
`p_rghEqnIncomp`, not the full compressible equation or its normalized linear
solver residual. The corrected summary and preserved source diff are in
`results/runs/i4f-pressure-clamp-trace-native4-20261024T0512Z/`.

One explicitly invalid stress continuation then retained the unchanged floor
and allowed clipping to continue, testing whether its support stayed isolated.
It did not: at 0.41916951 s, 88 cells contain 1.355 L of bounded liquid in a
single clipped corrector, exceeding the predeclared 1.286 L diagnostic stop
limit. The supervisor requested an endpoint write and the solver ended
normally at 0.41922322 s. This is a **guard-stopped numerical stress result**,
not a successful physical tail or emptying calculation. Corrector volumes
must not be summed as physical exposure. The full postrun join contains all
454 solver steps and 1,816 corrector records; 105 steps have some clipping.
The most negative raw iterate is −6.469 MPa. Final water and gas ledger
residuals are +0.1767 L and −0.7163 g respectively (0.01374% of restart water
and −0.003164% of restart gas). Good global closure therefore does not clear
the local pressure failure. The primary inspected the
[clipping/ledger plot](../results/runs/i4f-pressure-clamp-stress-native4-20261024T0549Z/postrun-analysis/clipping_and_ledgers.png).
Bundle:
`results/runs/i4f-pressure-clamp-stress-native4-20261024T0549Z/`.

A matched MULES/stock-IsoAdvector restart from 0.4 s likewise reaches the floor
in both branches: MULES at 0.40396296 s and IsoAdvector at its first step,
0.40001887 s. Switching interface representation on an existing MULES state
introduces a startup qualification; this does not establish intrinsic
inferiority of IsoAdvector. The pair does rule out declaring that switch a
demonstrated remedy. A separate periodic moving-contact check is inconclusive
because momentum linear solves hit iteration caps; it supplies no validated
formulation verdict. Both failed/inconclusive experiments remain preserved.

The next hypothesis is finite water compressibility, currently absent
(`rhoConst`, psi_water=0). A dedicated acoustic-pulse test and a source-based
initialization/phase-mass audit precede any apparatus EOS change. This is a
physical-model sensitivity, not an already established explanation or fix.

### Finite-compressibility water diagnostic

The pinned solver has now run a pure-water pressure pulse on 200 and 400 axial
cells (2×2 symmetric transverse cells), to 0.5 ms at acoustic Courant 0.25.
An imposed 1 m/s boundary velocity drives a wave into initially stationary
water at 1 bar and 293.15 K. The pressure-only `adiabaticPerfectFluid` law is
`rho=rho0*((p+B)/(p0+B))^(1/7.15)`, with rho0=998.2 kg/m³ and declared
c0=1500 m/s; B=rho0*c0²/7.15−p0. These are a provisional water EOS choice,
not measured apparatus properties. Its simple-wave pressure rise is
1.499334 MPa (the linear acoustic estimate is 1.497300 MPa).

| Observable | 200 axial cells | 400 axial cells |
| --- | ---: | ---: |
| 50% wave arrival at 0.25 m | 0.166667 ms | 0.166250 ms |
| 50% wave arrival at 0.50 m | 0.332500 ms | 0.332500 ms |
| Plateau pressure-rise error at 0.50 m, relative to Tait simple wave | −0.0392% | −0.0353% |
| Maximum mass residual, relative to injected mass | 0.0783% | 0.00000825% |
| Phase-fraction solve iteration-cap calls | 1,198/1,200 | 2,398/2,400 |
| Temperature solve iteration-cap calls | 184/1,200 | 314/2,400 |

Expected arrival times are 0.166667 and 0.333333 ms. Plateau medians use the
predeclared interval beginning at expected arrival plus ten cell-transit
times; the 0.75 m probe has no complete plateau before the endpoint. Pressure
and momentum solves meet their configured tolerances without hitting caps,
but phase and temperature caps prevent calling this a clean solver-convergence
pass. Alpha remains within 1.2e-13 of unity and temperature changes less than
0.00026 K; those small field changes do not prove the capped solves converged.
Early inlet-adjacent pressure peaks exceed the simple-wave plateau by 18.2%
and 16.4%, respectively. Thus the close later plateau agreement does not
establish accuracy of every startup pressure peak or validate real-water
thermodynamics. The primary inspected the
[grid comparison](../results/runs/i4f-water-pressure-pulse-20261024T055904Z/analysis/grid-pressure-probes.png);
inputs, actual solver logs, source references and full diagnostics remain in
`results/runs/i4f-water-pressure-pulse-20261024T055904Z/`.

This evidence supports a bounded apparatus sensitivity trial. Initialization
must preserve p/T/alpha/U while recomputing density and hydrostatic pressure
consistently; doing so changes initial liquid mass by +0.21928 kg (+0.01709%)
at the chosen 0.4 s restart. A matched constant-density control uses the same
smaller timestep. Liquid mass is evaluated with its phase EOS, not constant
density times volume; the recorded equation-stage advective flux is compared
with storage while retaining any finite-corrector coupling residual. The
candidate and source audit are in
`results/runs/i4f-weak-water-eos-preparation-20261024T055818Z/`.

The matched apparatus probe has now executed with eight MPI ranks per branch,
the same 4 microsecond maximum step and common EOS-consistent initialization
of density and p_rgh. It stops on the first **inner** raw-pressure event:
rhoConst at 0.400012 s (3 steps, minimum −337.136 kPa, 3 cells), and finite-
compressibility water at 0.400368 s (92 steps, minimum −28.652 kPa, 1 cell).
Both save an endpoint and exit normally before their 0.425 s target. Thus the
water EOS delays the event by 0.356 ms in this restart test but does not remove
it. Final corrected minima are slightly above 10 kPa in both branches, again
showing why a final-field floor detector can miss an inner-corrector event.
This is a warm restart with common startup reconstruction and decomposition;
it is not a comparison of full cold-start discharge histories. The original
cold-start reference must be traced separately with the already compiled
passive binary to establish its first clipping time. Executed cases, preserved
startup failure, corrected preflights and exact-container stop evidence:
`results/runs/i4f-water-eos-pair-20261024T062507Z/attempt2/`.

## Earlier solver-development evidence and gas-ingestion diagnostics

This section retains earlier numerical-development evidence and its exact
states. Its non-transonic and restarted trajectories are not the current
matched cold-start reference used in the completed comparisons above.

The strongest current physical lead is **local headspace-gas drawdown into
the pipe before the mean liquid level exposes the pipe crown**. At the saved
coarse field t = 0.34232644 s, gas-core cells connect the headspace to the upper
pipe mouth. The center point in the pipe remains water-filled and would miss
this ingress. The evidence is the
[computed connection diagnostic](../results/runs/i4f-visual-20261023T215734Z/frames/connection-gas-ingress-00000-t-0.34232644s.png)
and native-volume analysis in
`results/runs/i4f-analysis-20261023T215736.231913Z/`. This is not an
experimentally validated result; the current two-grid assessment is reported
separately above. The nearly symmetric funnel
does not, by itself, establish a swirling vortex.

At that time, native liquid volumes are 0.97000 m³ in the tank, 0.18805 m³ in
the line and 0.12754 m³ in the external region. Approximately 89% of the
initial tank water is still present. The liquid remains stored in the domain;
zero water flux at the far boundary does not mean zero nozzle discharge.
The global water-balance residual is about 0.200 L, or 0.0155% of initial
stored water and 0.170% of tank drawdown at this time.

The nozzle plane is still fully liquid at that checkpoint. Its interpolated
water flux is approximately 1.00 m³/s, velocity CV 0.153 and flux-weighted
flow angle 10.0°. The native sampled-plane observer agrees closely with this
cut-surface estimate. Near t = 0.392 s it reports approximately 2.24 m³/s at
the still-liquid nozzle, while water crossing the upstream pipe plane is only
about 0.52 m³/s. This is consistent with expanding gas displacing water
initially stored in the line; it is not evidence of additional water creation.
The full mechanical-energy budget and grid sensitivity are still pending.

The reduced model's full-liquid line and flat-level crown stop cannot predict
that regime. Retain its pre-entrainment balances and comparisons; do not fit
an arbitrary new flow multiplier or move its termination criterion to force
agreement.

Both trajectories were checkpoint-stopped after the operational nozzle-gas
marker: port gas confirmed, followed by three common-time sampled records
with positive net nozzle flow and at least 1% net sampled gas fraction.
The baseline crosses this marker at about 0.411 s and stops at 0.41112674 s.
The smaller-maximum-step case's observer starts only at 0.41774819 s, already
showing about 82% gas flow. Its true onset is therefore **censored between the
last all-liquid 0.400 s field and the first 0.41774819 s observation**;
0.41778246 s is persistence-confirmation time, not a microsecond-resolved
onset. It stops at 0.42317001 s. Different gas strengths at these different
post-onset times cannot establish timestep sensitivity by themselves.

Startup must be separated from this event: at 0.1 s, external air enters part
of the initially wet nozzle while the upstream pipe is still liquid. A
nozzle-only gas threshold would falsely identify that startup air as tank-gas
breakthrough. By 0.2 s the nozzle is fully wet again.

The measured cost increase is associated with compressed gas entering the
pipe. At 0.342 s a gas cell reaches 117 m/s (Mach about 0.35); at 0.4 s the
smaller-step branch reaches Mach about 0.8 downstream of the valve. Its
post-marker checkpoint reaches Mach about 1.1. The default non-transonic
pressure correction retains explicit mass advection but lacks the optional
implicit pressure-convection correction. The transonic continuation has now
completed normally at 0.41070136 s, with three above-threshold nozzle-gas
records beginning at 0.41062984 s. At the common 0.35 s checkpoint its nozzle
flow differs by about 0.13% from the non-transonic smaller-maximum-step branch;
this precedes the most demanding gas-front interval. At the stopped transonic
checkpoint the native water-ledger residual is 0.308 L (0.0240% of stored
water at the ledger reference), measured only from the first continuation
sample at 0.30017301 s. It excludes the parent's startup error; maximum
interval residual is 0.313 L. The reconstructed water inventory increased
by about 0.436 L between the archived t=0 and endpoint fields, which is a
storage diagnostic rather than a merged startup-to-end flux ledger.
The maximum gas Mach number is about 0.965 downstream of
the valve. The endpoint nozzle cut estimates 3.51 m³/s of water and a velocity
CV of 0.203; these near-sonic transient magnitudes remain unvalidated.
Domain-wide gas closure and mesh sensitivity are still required. A small water
residual alone cannot establish that the pressure-to-kinetic-energy transfer is
accurate.
The transonic branch also uses the asymmetric-compatible GaussSeidel pressure
smoother, so the comparison does not isolate pressure coupling alone. The scalar
valve-loss law is also not a validated choked-gas valve model. No sustained
gas-blowdown or actual foam-throughput claim follows from these runs.

Phase-conditioned checks help separate gas cooling from liquid behavior.
At the transonic endpoint, cells with alpha_water >= 0.99 have absolute
pressure 95.84–600.33 kPa, water temperature 291.35–293.32 K, and maximum
speed 31.35 m/s. Gas-core cells have temperature as low as 239.03 K and
maximum speed 299.81 m/s. These phase-specific reconstructed temperature
fields confirm that the reported cold-gas minimum is not a bulk-water
freezing result. No cell reaches the configured 10 kPa pressure floor.
Exact masks, field hashes and extrema locations are in
`phase-conditioned-plausibility.json` inside the transonic endpoint analysis.

For scale, the 273–303 K Antoine coefficients compiled by
[NIST from Bridgeman and Aldrich (1964)](https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185&Mask=4#Thermo-Phase)
give water saturation pressure about 2.34 kPa at 293.15 K, and below 2.37 kPa
over the observed liquid-core range. The resolved liquid pressure is therefore
well above vapor saturation at these inspected states. This supports omitting
vapor cavitation in the present scalar-loss reference; it cannot exclude low
pressures at an unresolved butterfly disk or establish anything about dissolved
CO2 exsolution. Sparse saved states also do not bound every intermediate
pressure excursion.

## Direct adiabatic gas-expansion check

A separate small CFD limit tests the same compiled solver and air/water
thermodynamics without apparatus geometry or valve losses. A 1 m channel of
1 cm² cross-section initially contains 80 mL water and 20 mL sealed air at
9 bar absolute and 293.15 K. Withdrawing only water at 2.5 mL/s for 2 s
expands the gas by 25%. Gravity and turbulence are disabled and Pr=1e9
suppresses thermal diffusion for this deliberate adiabatic limit. Neither
pressure nor gas inflow is imposed at the extraction boundary.

For the configured gamma=1.399814, compare
`p=p0(Vg0/Vg)^gamma` and `T=T0(Vg0/Vg)^(gamma−1)` using the measured native
gas volume. The frozen declaration sets 2% pressure/temperature and energy
targets, 0.5% gas-mass/withdrawal-volume/flux-closure targets, and 2% grid
change, before seeing results. In the converged repeat:

| Metric | 500 axial cells | 1,000 axial cells |
| --- | ---: | ---: |
| Pressure error at 2 s | +0.310% | +0.209% |
| Volume-weighted gas-temperature error at 2 s | +0.328% | +0.222% |
| Maximum gas-mass drift | 0.00478% | 0.00400% |
| Water inventory/flux residual, relative to 5 mL withdrawal | 0.0229% | 0.0195% |
| Maximum final pressure linear residual | 9.65e−11 | 2.29e−10 |

Both cases reached t=2 s with normal End and complete endpoint fields; every
pressure solve converged in one iteration. The final pressure/temperature
grid changes are below 0.11%. GAMG had stagnated on the quasi-one-dimensional
mesh in an earlier preserved attempt, so this repeat changes only its pressure
linear solver to PBiCGStab/DILU at the same tolerance. It tests the gas-energy
formulation, not the apparatus pressure solver or hardware validity. The
coarse adaptive step briefly reaches 5.0203 ms versus a requested 5 ms cap;
actual steps are recorded rather than asserted identical to the request.

Energy accounting uses the exact constant-Cv ideal-gas phase integral
`Ug = integral(alpha_air p dV)/(gamma−1)`, not total gas mass times a
volume-weighted temperature proxy. The dense-state diagnostic
`delta Ug + integral(p_g dVg)` is +0.1327 / +0.0896 J: 0.295% / 0.199% of
initial gas energy, or 3.45% / 2.33% of expansion work. It decreases with
refinement but is nonzero even in this high-Pr limit. Consequently, apparent
subsystem heat in the apparatus must not automatically be interpreted as
physical interfacial heat transfer. This diagnostic is not a total-energy
conservation proof for the apparatus.

The predeclaration, immutable cases, failed setup attempts, native time series,
converged-repeat CSV/plot and exact-energy diagnostic are in
`results/runs/i4f-adiabatic-gas-expansion-check-20261024T012520Z/`.
Use its `attempt4-analysis.json`, `attempt4-endpoint-ledger.csv` and
`attempt4-adiabatic-expansion.png`; earlier GAMG artifacts remain separate.

## Earlier startup numerical diagnostics

At 0.2 s, using OpenFOAM's native cell volumes and the actual ideal-air EOS:

| Maximum step | Tank pressure, pure-gas volume mean (bar absolute) | Tank gas-mass drift | Global water residual (L) |
| --- | --- | --- | --- |
| 1.0 ms | 8.1577 | −0.207% | 0.10184 |
| 0.5 ms | 8.1766 | −0.00155% | 0.07968 |

The larger-step gas error occurs by 0.1 s and then remains nearly constant
through 0.2 s, while gas is confined to the tank. This is an identified startup
time/coupling sensitivity, not a validated loss mechanism. Source fields,
hashes, definitions and native flux residuals are preserved in
`checkpoint-0.2-comparison.json` inside the corrected coarse run bundle.
A four-outer-corrector startup diagnostic completed to 0.2 s. Gas drift was
−0.0342% and the water residual about 0.0345 L. Printed Courant/interface
numbers reached 2.38/1.28, but the solver prints these **before** `setDeltaT`
adjusts the upcoming step. Those printed maxima alone do not establish that
the applied advection step violated the requested 0.5/0.25 limits. Its different
adaptive-step history prevents accepting it as an isolated coupling fix.
The new cold-start numerical references retain two outer correctors and a
smaller maximum step. No conservation pass is declared.

Post-processing also required a correction: VTK's geometric cell-size
calculation produced incorrect signed volumes for some cells. Quantitative
integrals now use the solver-written positive `V` field and are reconciled
against native cell-zone sums. Taking absolute VTK volumes is not a validated
replacement. After gas exits the tank, tank-only gas inventory is no longer a
closed-system conservation check; use the relevant storage and flux
compartments.

The matched 1.0 s versus 0.5 s opening comparison has now been executed and
is reported above. Its modest extra depletion relative to the much longer
elapsed time illustrates why delayed gas arrival alone is not an improvement.

## CO2 inventory comparison and thermal qualification

A second executed calculation isolates interphase transfer under **matched
initial inventory**. Both cases start with the same assumed 1 bar air plus
8 bar CO2 partial pressure, water initially saturated with CO2, and 293.15 K.
Initial total CO2 is approximately 21.7 kg in the assumed tank, of which about
6.8 kg is gaseous and 14.9 kg dissolved. These are pure-water model inventories,
not inferred measurements of the device. The Henry coefficient is transferred
from [Moreno Soto et al., Eq. (2.1) and experimental conditions](https://doi.org/10.1017/jfm.2017.623);
its pressure convention and transfer to retardant remain uncertainties.

One limit prohibits interphase exchange during drainage, while dissolved CO2
still leaves with the liquid. The other maintains instantaneous Henry
equilibrium and includes the same advective loss. Both use ideal gas and fixed
temperature. At the same geometric entrance event, calculated total pressure
is 3.48 bar absolute without exchange and 5.29 bar with equilibrium exchange.
The latter keeps more gas in the headspace through exsolution. Gas, remaining
dissolved inventory and advected CO2 close the initial mass to within
1.8e-7 kg on 1,001 inventory samples. Root independently checked the governing
balance and inspected the pressure/inventory plot.

The evidence is in `results/runs/i4f-co2-inventory-limits-20261023/`. The
independent variable is liquid volume released, **not time**; these curves do
not predict a dissolution rate or a CFD discharge history. They show why
charging state and mass transfer could materially change pressure retention.
Actual finite-rate flow need not attain the equilibrium limit, and temperature,
air composition and agent chemistry can change both scenarios.

The illustrative polytropic exponent also carries an energy assumption. For
constant ideal-air heat capacities, `U_g = pV/(gamma−1)` and heat required by a
polytropic history is `Q_heat = delta(U_g) + integral(p dV)`. With gamma = 1.4,
the n = 1.25 reference requires about 135 kJ of net heat into the gas before
the entrance event. That heat has not been justified by a heat-transfer
calculation. The n = 1.4 ideal adiabatic limit requires zero heat by definition.
Thus n = 1.25 remains an illustrative sensitivity, not an established thermal
model. Compare the actual CFD gas temperature and energy treatment rather than
assuming it realizes that exponent.

## External stationary water-discharge comparison

A component comparison now also uses Iguchi and Ohmi's measured air flow
through a sudden pipe expansion, DOI 10.1299/kikaib.52.3252, case No. 5.
At diameter ratio squared approximately .2852 and inlet Reynolds number
53,187, digitized experimental markers give K=.5317 and .4864, with approximate
pixel-reading bounds .0092 and .0084. Their spread is not a reported statistical
confidence interval. The unfit Borda–Carnot relation gives .51094. Our coarse
30,600-cell and fine 122,400-cell SST calculations at iteration 6000 give
.50764 and .50152. Pressure is extrapolated from developed pipe sections to
remove straight-pipe friction; static-pressure recovery alone is not the loss.
Fine K changes .00106% from iteration 5000 to 6000. Its only remaining
residual-control component, Uz, is a symmetry-zero wedge velocity with maximum
4.51e-14 m/s; its relative residual does not represent a meaningful transverse
flow error. Coarse pressure and pressure-fit-window checks still fail.
Fine mean wall y+ is approximately 8–13 on the reported patches, so the wall
approximation and unspecified experimental inlet conditions remain limitations.
This is a useful experimental component comparison, not apparatus validation
or a measured coefficient for the smooth I4F transition. Root inspected the
[comparison plot and pressure extrapolations](../results/runs/i4f-iguchi-iteration-continuation-20261024T202607Z/analysis/attempt5b-experimental-comparison-fine6000.png).

The Watanabe, Tomita and Takemae (2003) fixed water-rocket experiment supplies
actual pressure, camera-derived water inventory and load-cell thrust curves
([DOI 10.2322/jjsass.51.314](https://doi.org/10.2322/jjsass.51.314)). The source
uses a nominal 1.5 L bottle, 500 mL water and 5 atm gauge compressed air; the
ordinary-nozzle reference is 7.5 mm. Figures 4, 6 and 11 are digitized separately,
with pixel calibration and trace overlays. The authors explicitly describe
simultaneous pressure/thrust acquisition in their abstract; synchronization of
the camera-derived inventory with these particular plotted records has not
been established. The model retains the
approximately 1.3% difference between the stated pressure and the graph's
roughly 500 kPa starting value. Source and executed comparison:
`results/runs/i4f-watanabe-reduced-benchmark-20261024T2008Z/`.

Using measured water inventory as input to gas volume, fixed polytropic
exponents 1, 1.25 and 1.4 produce pressure RMSE of 30.9, 15.7 and 14.2 kPa
over 0–0.25 s. No exponent is fitted. This is a conditional p(V) closure
comparison, not a forward prediction of discharge. The plotted envelopes are
deterministic mass/pixel sensitivities, not statistical confidence intervals;
pressure-sensor uncertainty and inventory/pressure alignment are unspecified. The
independent forward water/gas model with the source-literal flow coefficient
has about 0.039 kg mean absolute water-inventory error in that interval, about
7.8% of initial water mass. It is not an exact reproduction or a validation pass.

Source Eqs. (2)/(6) put the assumed coefficient alpha=.8 in discharged mass,
while Eq. (7) omits it from thrust. Printed Eqs. (8)/(16) also omit the nozzle
area required for force units. Primary and independent Luna source inspection
confirmed these printed inconsistencies. The analysis separates the paper's
digitized semi-empirical line, an area-restored Eq. (7) convention and a
mass-flux-consistent momentum calculation. It does not silently repair the
formulas and claim their conventions are uniquely recovered.

The camera inventory is measured only through about .35 s; the paper estimates
the mixed tail to an empty time near .40 s. At .35 s the digitized remaining
mass is .116 kg. Completing it in .05 s would require about 2.33 kg/s, exceeding
the source-literal initial maximum of about 1.124 kg/s. This is a conflict with
an extrapolated tail and assumed coefficient, not a contradiction of a measured
empty-time observation. The reconstructed forward models empty at .510–.542 s,
but their liquid-only applicability ends earlier and those values are not
validated gas/water termination predictions.

The most useful figure is the explicitly conditional
[pressure–volume comparison](../results/runs/i4f-watanabe-reduced-benchmark-20261024T2008Z/figures/conditional_pv_pressure_closure.png).
These external data now constrain a liquid-discharge model without requiring
escaping gas as the primary target. Exact CFD reproduction still needs a
documented internal bottle contour and release-opening history.

A separate sealed-headspace channel check now tests the numerical formulation
while essentially only water leaves. The 1 m slip-wall channel contains ideal
air initially occupying 0.2 m, water downstream and a fixed scalar valve loss;
air thermal diffusivity is suppressed to approach the adiabatic reference.
Against a moving-liquid-control-volume ODE, the 5,120-cell run has RMS errors
of 0.286 mm in gas-volume-equivalent interface position, 0.435% in outlet speed
and 1.129% in headspace pressure after the first 5 ms. It stops at 0.03009 s
on a numerical gas-tail marker in the valve, with essentially no outlet gas;
the 1,280-cell run stops earlier at 0.0252 s. These different stopping times
are not physical breakthrough times or a formal convergence study. The test
supports the basic gas-expansion/liquid-inertia coupling in a simple geometry,
while omitting the apparatus transition, wall friction, lamellae and CO2.
Computed comparison:
[channel pressure, flow and inventory](../results/runs/i4f-headspace-channel-piston-pair-20261024T2029Z/analysis/headspace-ode-comparison.png).

## Revised two-outlet reduced reference

The revised geometry's scales are recomputed from native inventories and the
.400021 s outlet fields, rather than transferred from the earlier .25 m pipe
case. Each .30 m pipe feeds a 1.0 by .15 m mouth (area ratio 2.122; mouth
hydraulic diameter .26087 m). Initial tank gas/tank liquid volume is .474 and
absolute pressure/ambient pressure is 9.0. At that snapshot, pipe Reynolds numbers are
2.18/2.17 million and mouth Reynolds numbers .894/.891 million using hydraulic
diameter. Lower-branch liquid Froude numbers are 4.26 in the pipe and 2.15 at
the mouth; liquid Weber numbers are 2.19e5 and 4.24e4 respectively. These use
water density, section mean speed and the stated characteristic length;
they are not aerodynamic droplet Weber numbers or evidence of resolved breakup.

At .40 s, current headspace-volume/total-flow is .782 s and primed-line-volume/
total-flow .847 s. Neither is a gas-front arrival prediction. Branch length
scales are 5.38/5.44 m, with integral(ds/A) 69.31/70.27 m^-1. An illustrative
ideal-air path acoustic time is about .016 s, versus the assumed one-second
valve stroke and about .74 s for sqrt(path length/g). The air acoustic estimate
uses its initial 293.15 K state and a hypothetical all-gas path, not a mixed-line
wave speed. A 5.4 m/1500 m/s water-acoustic estimate is .0036 s; that assumed
sound speed is absent from rhoConst-water CFD. Slow actuation supports this
liquid approximation for bulk flow, while fast water-hammer claims remain
outside it. Molecular diffusion across tank or pipe dimensions is much slower
than release; this does not exclude thin interfacial thermal layers or modeled
eddy transport. Formulas, units, input provenance and 125 scale entries are
preserved in the [revised scale calculation](../results/runs/i4f-revised-two-branch-scales-20261025T0805Z/scales.json).

The new `src/aerial_drop/i4f_reduced_network.py` represents independent liquid
branches sharing one sealed headspace. Each branch obeys
`Ij*dQj/dt = pg - pamb + rho*g*(h-zout,j) - lossesj`, with
`Ij=rho*integral(ds/A)`, while `dVtank/dt=-sum(Qj)`. Initially full line
inventories remain separate from tank water and discharged water. The model
stops at the highest intake crown or before reverse flow; it does not calculate
mixed discharge or full emptying. Eight focused checks plus the existing
twelve reduced-model checks pass together; no physical validation is implied.

A frozen two-branch comparator uses the provisional .9 m by 3.1 m cylinder,
.70 tank fill, 9 bar absolute ideal air, n=1.4, .30 m pipes, two 1 by .15 m
mouths, and the declared one-second scalar valve opening. At .05/.10/.20/.30 s,
predicted total flows are .07915/.10527/.36651/.69372 m3/s; gas pressures are
892.0/883.4/838.7/748.3 kPa absolute. The mean-level upper-crown event occurs
at 1.017544 s after 1.026443 m3 of tank drawdown. The lines still contain
.881092 m3 and tank water remains .354052 m3; this is not an empty system.
Halving the numerical step changes event time by less than 1e-7 s. The
backward unsteady-Bernoulli transition-entry screen has a minimum section-mean
pressure of 65.9 kPa, not a bound on local CFD pressure or a cavitation verdict.
Root inspected the [captioned prediction plot](../results/runs/i4f-parallel-branch-adiabatic-comparator-20261024T212300Z/figures/two-branch-adiabatic-comparator-captioned.png).
These predictions preceded the revised CFD result and must be compared using
the actual initialized inventories; the present pilot does not achieve the
nominal .70 fill. Source snapshots, timestep comparisons and the corrected
timestamp erratum are retained in that comparator bundle.

An additional comparison fixes the reduced model's initial tank-water and gas
volumes to the native CFD values, without fitting the gas exponent. This uses
an equivalent cylinder length of 3.08873 m to represent the meshed tank volume;
it is an observer-volume match, not a revised hardware measurement. The model
line inventory remains 8.21 L larger than CFD and is reported separately.
At .30 s, CFD tank depletion is 86.29 L and sampled total nozzle flow .7092
m3/s; fixed n=1.25 gives 84.08 L and .7045 m3/s. At the last gas-probe time
.29952117 s, that model's pressure exceeds the CFD probe's 765.25 kPa by
5.08 kPa. Fixed n=1.4 gives a pressure 8.55 kPa below the same probe.
These are shared-assumption consistency checks, not thermal-model calibration
or independent validation. Integrating sampled alpha*Ux at the nozzle gives
85.42 L at the endpoint, versus 86.31 L gained in external water storage;
the sampled surface is not a conservative finite-volume flux. The signed
open-boundary phase flux is tracked separately. Root inspected the
[pressure, inventory, flow and storage comparison](../results/runs/i4f-cfd-vs-volume-matched-reduced-20261024T221505Z/figures/cfd-vs-reduced.png).

Saved-field mouth quadrature at .400021 s gives lower/upper water flow
.51618/.51429 m3/s, water-area-weighted mean axial speeds 3.441/3.429 m/s,
and axial-velocity coefficients of variation .09323/.09326. Both sampled
mouths are fully water-covered. The directions of the area-mean velocity
vectors are 4.26/4.21 degrees from +x; these are not averages of local angles.
Their mean lateral velocities have opposite signs (+.236/-.233 m/s), so a
combined-vector average would hide this branch difference. Approximate water
axial momentum fluxes are 1788/1775 N, excluding pressure/stress forces.
These remain sampled estimates 1 cm upstream of the lip, with provisional
geometry and no lamellae. Root inspected the contact sheet and endpoint frame.
The [10x slow prefix movie](../results/runs/i4f-twooutlet-mouth-quality-20261024T2248Z/figures/movie_10x_slow.mp4)
shows actual saved times from 0 to .400021 s; its 4.5 s duration includes the
held endpoint frame. It does not represent a complete discharge.

At that endpoint the mean local velocity-angle magnitudes are 4.55/4.50 degrees,
with 95th percentiles 7.32/7.23 degrees; these differ from the directions of
the averaged vectors. Three transition cuts at x=4.0/4.8/5.5 m show no sampled
negative water velocity along the generated centerline tangent, at thresholds
0 and -.01 m/s. They do not exclude separation between cuts or at later times.
Static-pressure differences across valve-bracketing x=2.0–2.5 m sections are
442/439 kPa, versus 6.04/4.72 kPa across x=4.0–5.5 m. These unsteady section
differences are not dissipative-loss measurements. Root inspected the
[outlet maps](../results/runs/i4f-twooutlet-mouth-quality-20261024T2248Z/quality-extension/figures/mouth-ux-and-transverse-vectors.png)
and [pressure/velocity allocation](../results/runs/i4f-twooutlet-mouth-quality-20261024T2248Z/quality-extension/figures/section-pressure-velocity.png).

The matched .300021–.400021 s restart comparison halves maximum timestep from
.25 to .125 ms with byte-identical initial fourteen fields and uniform/time.
Endpoint sampled Q changes -.182%, gas-probe pressure +.024%, and mouth CV
by -.000176/-.000153 absolute. Minimum local pressure changes -1.74 kPa
(-2.43%), a larger local sensitivity than bulk pressure. Neither branch clips
pressure. The concurrent window costs 564 versus 2118 solver ClockTime seconds;
this is not an isolated scaling benchmark. It is a short-window sensitivity,
not temporal validation through the later ingestion event. Root inspected
[the timestep comparison](../results/runs/i4f-halfdt-analysis-20261024T232445Z/analysis/halfdt_comparison.png).

The external-flux audit finds only 2.03 mL cumulative outward native water
phase flux by .300021 s, with no meaningful negative inflow. The visible
negative curve is line storage: it loses 2.296 L by .123271 s and refills by
about .25 s. Thus the early redistribution is not evidence of water entering
through an exterior boundary. The .893 L sampled-plane/storage discrepancy
remains a diagnostic limitation; a 9 mm offset between the sample and line-zone
edge alone does not explain its endpoint value. In a separate, otherwise fixed
reduced-model pair, reducing minimum effective valve opening from .02 to .002
changes .05 s discharge from 3.780 to .612 L. At .40 s the difference is
3.45 L and instantaneous flow differs by .37%. The finite minimum opening
therefore matters strongly to startup, even when later bulk flow is similar;
it is a numerical/physical input sensitivity, not a measured hardware leak.
Source-frozen calculation and audit:
`results/runs/i4f-openpatch-line-storage-audit-20261024T2240Z/`.

A native solver-based wall audit at .400021 s gives area-weighted wall y+
percentiles 242/817/1903 (5th/median/95th); the transition median is 1272.
The SST baseline uses `nutkWallFunction`, whose y+ estimates friction velocity
from local k ([v2512 implementation](https://api.openfoam.com/2512/nutkWallFunctionFvPatchScalarField_8C_source.html)).
This is a wall-function computation, not viscous-sublayer resolution; a y+=300
screen is descriptive, not a universal failure threshold at high Reynolds
number. Losses/separation still require sensitivity evidence. A global nGrow
layer repair removes three determinant failures but leaves only 25.9% of wall
faces layered, so it is not promoted. A localized exclusion is being tested
to retain coverage elsewhere. The audit uses a private complete checkpoint;
the zero field from standalone postProcess without a registered turbulence
model is retained as a failed attempt. Evidence:
`results/runs/i4f-relative-layer-local-repair-20261025T004000Z/yplus-check/`.

The earlier one-versus-two-branch reduced comparison matches total initial
water and pressure by changing tank fill. Its headspace volume and gas mass
therefore differ. The approximately doubled early flow is an operational
comparison under changed gas charge, not a controlled design-efficiency gain.

A separate matched opening-time comparison changes only the assumed scalar
opening from 1 to 5 s, with the same native-volume-matched tank, gas charge,
two primed lines, n=1.25 and minimum opening .02. The flat-level crown stops
occur at .947060 and 2.332364 s, peak Q at 1.62617 and .79705 m3/s. Both
withdraw .98036 m3 and leave .352765 m3 in the tank: this equality follows
from the shared geometric stop, not proof of equal usable real discharge.
Halving model step to .5 ms changes the 5 s event time by 2.1e-7 s.
The maker's '5 s' meaning remains unconfirmed, and these are reduced-model
scenarios, not evidence of improved CFD sheet quality. Evidence:
`results/runs/i4f-opening-time-1v5s-20261024T230813Z/`.

## Interpretation and next engineering decision

The newly confirmed inventory has now been evaluated with the existing
liquid-only two-branch model. The central scenario uses 1.350 m3 tank water,
.30375 m3 gas, 12 bar absolute, a volume-derived 2.59953 m horizontal cylinder,
dry-air n=1.4 and the assumed one-second opening. Peak two-mouth flow is
1.306 m3/s per tank. At 1.120 s the mean surface reaches the upper intake crown,
after 1.053 m3 withdrawal, leaving .2969 m3 tank water and .8811 m3 in the
assumed primed lines. This is not emptying or a prediction of total discharge
duration; neither local early drawdown nor mixed gas/water release is resolved.

At the same 12-bar/n=1.4 assumptions, 20/25% gas headspace gives peaks
1.240/1.366 m3/s and crown times 1.178/1.075 s. Central 13-bar pressure gives
1.352 m3/s and 1.084 s. Isothermal and n=1.25 references give peaks
1.625/1.409 m3/s and times .972/1.056 s, with no exponent fit. Halving the
central integration step from .002 to .001 s changes crown time by 4.45e-7 s
and peak flow by 7.95e-7 m3/s; this establishes integration precision for this
model, not input or physical accuracy. Root inspected the
[confirmed-inventory model plot](../results/runs/i4f-confirmed-inventory-reduced-network-20261025T084122Z/figures/confirmed-inventory-reduced-model.png)
and [source/result record](../results/runs/i4f-confirmed-inventory-reduced-network-20261025T084122Z/data/results-summary.json).
Branch geometry/losses and initial line fill remain provisional; the model
does not yet include the new dividers. System totals may be doubled only for
two identical independent tanks with simultaneous identical valve actuation.

For the current two-outlet apparatus, the useful early evidence is a nearly
water-filled, moderately nonuniform mouth flow (axial CV about .093 at .40 s),
a valve-bracketing pressure drop around 440 kPa, and local upper-intake gas
entry while about 79.5% of initial tank water remains. The source correction
has continued beyond the stock stop window while preserving the compared
early pressure/flow histories closely. Completing that trajectory, establishing
fine-grid sensitivity and explaining the gas-energy remainder are the current
numerical priorities. They precede an engineering ranking. Given the clarified
hardware, the next physical comparison is the same corrected envelope with
and without the four inferred dividers per mouth, reporting discharge and
outlet quality together. The prior one-/five-second opening scenarios remain
hypothetical sensitivities: the user has clarified five seconds as total
discharge duration, not actuation. The revised-mesh pilot has only completed
0.005021166664 s of startup, so no useful release interval is yet available.

For the earlier single-outlet primed water/air reference, the opening valve controls the
early restriction, gas expansion reduces tank pressure, and line inertia
contributes substantially to the transient pressure budget. The transition
recovers static pressure as velocity falls with increasing area; a static
pressure rise is not negative dissipation. Later, local surface drawdown
admits gas while roughly 86% of the initial tank water remains. Expanding gas
then displaces the downstream water inventory and produces a nozzle-flow
surge. The single-liquid reduced model is useful before this phase change in
the flow pattern, but its flat-interface stopping criterion misses the early
local ingestion.

The earlier broad-history and operational-marker comparisons are pressure
affected and cannot establish robust late performance. The newer early
matched-inventory evidence supports investigating local drawdown and opening
rate, subject to its inherited numerical-history difference. Delaying gas
arrival alone is insufficient as an engineering objective: flow, delivered
liquid inventory and sheet quality must accompany timing. The vertical
comparison cannot rank late performance because pressure clipping begins
before the interesting ingestion interval.

The highest-value physical input is the downstream passage's initial state.
In the reference, about 40% of the endpoint upstream storage-loss budget is
the **net decrease of line inventory**; this is not a tracer attribution of
which original water crossed the nozzle. An open passage could retain much
less liquid during the charging wait. Confirm that state, the real valve
opening trace, intake submergence, and the four-lamella cross-section before
interpreting a no-divider simulation as a design prediction. Earlier
drained-passage trials had a localized startup pressure problem; their smaller
step and first-order momentum experiments did not remove clipping. That is
a distinct unresolved initial-state scenario, not the current primed-run queue.

The reported durations end at explicitly defined ingestion/operational
criteria. **Total emptying time is not established**: the reduced model loses
its liquid-only validity, and CFD deliberately stops near the first confirmed
outlet gas marker with substantial water remaining. A full mixed gas/water
blowdown, any unreleased residual and actual CO2/retardant discharge require
the next physical model and measured initial conditions. Extrapolating the
present histories to a complete emptying time would not be defensible.

## Current evidence update — 25–26 October 2026

The user's initial-state clarification now fixes the current reference:
passages downstream of the valves initially contain air. The compact baseline
has 1.350 m3 water per tank plus .25106/.25111 m3 in wetted tank-to-valve feeds,
and ambient gas downstream of the assumed x=2.25 m seat planes. Earlier
primed-line results below remain historical initial-state sensitivities.
The [current movie](../results/summaries/i4f_20261025/current-air-filled-cutaway-10x.mp4)
shows filling through .200021 s, without a resolved exterior sheet. The
[portable moving-front model](../results/summaries/i4f_20261025/air-filled-moving-front-model.json)
conditionally predicts first mouth water near .612/.620 s and a geometric
intake-crown proxy near 1.127 s for one tank/two branches. A full-bore front, polytropic
gas and incomplete downstream-air/transition treatment limit those predictions;
they do not determine actual emptying time. Isothermal gas changes the crown
event by about 14%. No complete corrected CFD discharge has yet finished.

A [targeted all-water pressure-loss benchmark](../results/summaries/i4f_20261025/valve-resistance-duct-results.json)
uses the executed scalar source, fixed static pressures of 1.2 and .1 MPa,
gravity zero, equal-area end sections and slip sidewalls. With water density
998.2 kg/m3, Cd=.7 and opening fraction .02, K=1/(Cd f)^2=5102.04 and
the steady reference is Q=A sqrt(2 delta-p/(rho K))=.0464583 m3/s.
All four cases end normally. The native flow error is +6.34% for a .30 m
source on 25 mm axial cells, and +1.38% on 6.25 mm cells; the .10 m source
gives +27.66% and +5.02%. Inlet/outlet flux closure is below 3e-11 relative
and source-integrated force per area recovers the imposed pressure drop.
Thus conservation and the correct integrated force do not establish that the
discrete source delivers the intended pressure–flow relation. These errors
must not be used as fitted correction factors for the multiphase apparatus.

The [source-placement history](../results/summaries/i4f_20261025/air-filled-source-history-comparison.png)
also prevents adopting a narrower upstream source as a simple fix. Its
tank-A drawdown difference reverses from -.79 L at .050021 s to +3.08 L
at .200021 s. At the latter checkpoint it has 11.85 kPa lower gas pressure
and a roughly .15 m farther liquid front, even though the original source
has already become fully wetted. Both fronts are upstream of the transition.
Thus the initially mixed source and its discrete pressure–flow behavior must
be separated; an early improvement alone does not identify the right closure.

The [native gas-state diagnostic](../results/summaries/i4f_20261025/air-filled-gas-apparent-exponent.json)
finds an apparent exponent -log(p/p0)/log(Vg/Vg0) decreasing from about
1.283 at .05 s to 1.242 at .20 s in both source arms, compared with dry-air
gamma=1.399814. EOS tank-gas mass changes by at most .00235%, and pressure
standard deviation is at most .0111% of the mean over these samples. This
quantifies a gas-trajectory difference from the adiabatic reduced model;
it does not identify physical heat transfer, close energy fluxes, or justify
fitting the reduced model to CFD. The common-temperature equation and its
interface transport still require appropriate energy accounting.

The headspace range also affects the late pressure margin. In the simple
sealed polytropic limit, replacing the tank's liquid volume entirely by gas
gives p_final = p_initial [r/(1+r)]^n, where r is initial gas volume divided
by tank liquid volume. With n=1.399814 and 12 bar absolute, r=.20/.225/.25
gives .977/1.119/1.261 bar absolute. At 13 bar, the values are
1.058/1.213/1.366 bar. The gas-only pressure margin against a 1 bar atmosphere
vanishes at r=.2040 for 12 bar, within the reported range. This is a
hypothetical tank-volume replacement scale: intake exposure, hydrostatic head,
line losses, heat transfer and CO2 behavior affect the actual termination.
It prioritizes measured headspace and pressure/temperature histories without
turning the idealized calculation into an emptying prediction.

The resulting numerical action is a .30 m initially wetted source upstream
of the seat, with local axial refinement and explicitly normalized weights.
Prepared 279,536- and 299,248-cell meshes pass all nine configured quality
criteria, preserving mapped initial phase inventories and all fourteen zones.
Their matched cold starts both completed .050021 s normally. The
[native flux comparison](../results/summaries/i4f_20261025/air-filled-valve-band-axial-comparison.json)
retains **HOLD** under the unchanged 2% pointwise target: only the first two
rows, at 12 and 26.4 microseconds, fail, with maximum difference 5.12%.
At the endpoint, per-branch flow differs about 1.50%; tank-A drawdown is
4.66391 L on 12.5 mm axial cells and 4.59423 L on 6.25 mm cells, compared
with approximately 4.57 L in the reduced model and 6.547 L in the original
mixed-source case. The 69.7 mL tank-inventory difference agrees closely with
the integrated native seat-flux difference. This supports a substantial
numerical origin for the early mismatch without fitting Cd. It is a shared-
assumption consistency result, not validation of the valve or thermal model.
The [source/grid comparison figure](../results/summaries/i4f_20261025/air-filled-drawdown-source-grid.png)
shows all four matched-time CFD inventories against the bracket-interpolated
model reference, including the .634% difference in initial wet-feed volume.
The separately labeled exploratory long fine run proceeds with this known
sensitivity; the failed screen remains failed. These cases do not resolve
the butterfly-disk wake. A prospective 2% source-flow target against
the analytical duct and a 2% apparatus mesh-sensitivity target have different
meanings. Neither is experimental validation. Horizontal and vertical vessel
CAD now exist with inspected connection sections, but the provisional vertical
placement has no computed discharge-performance result yet.

The remaining paragraphs in this update describe earlier reference cases.

A matched boundary-condition replay of the older one-tank reference advanced
373 physical steps from the shared 0.560717355465 s checkpoint to 0.588704120044 s.
The compressible-reservoir arm reduced global maximum speed from 1162 to 67 m/s
and maximum temperature from 495.5 to 293.3 K, while tank pressure, mouth flow
and phase ledgers remained close. Its 22.35× Courant-based timestep headroom is
an estimate, not measured throughput or speedup; this replay does not validate
ambient coupling or the revised hardware. See the [pair evidence](../results/summaries/i4f_20261025/ambient-reservoir-pair-r2-evidence.json)
and [plot](../results/summaries/i4f_20261025/ambient-reservoir-pair-r2.png).

The separate pre-ingestion water-storage audit finds −292.545 kJ tank-water
thermal excess against the prior +58.956 kJ gas-energy/work remainder through
0.450021 s. The fields use one shared mixture temperature; this phase-weighted
storage change does not measure heat transfer to gas or close the budget without
boundary and transport fluxes. See the [reproducible private audit](../results/runs/i4f-headspace-energy-audit-20261025T075514Z/analysis/water-storage-extension-20261025T123001Z/water_thermal_storage.json),
[plot](../results/runs/i4f-headspace-energy-audit-20261025T075514Z/analysis/water-storage-extension-20261025T123001Z/water_storage_vs_gas_remainder.png),
and [analysis script](../results/runs/i4f-headspace-energy-audit-20261025T075514Z/analysis/water-storage-extension-20261025T123001Z/analyze_water_storage.py).

The subsequent [thermo-source audit](../results/runs/i4f-headspace-energy-audit-20261025T075514Z/analysis/water-thermo-pressure-extension-20261025T130002Z/water_internal_energy_terms.json)
clarifies that the configured water sensible internal energy is
`e_s = 4182 (T - 298.15 K) - p/998.2`, with absolute thermodynamic pressure.
Thus the temperature-excess diagnostic is only one storage term. In that
historical one-tank prefix, the pressure contribution `-sum(alpha_water p V)`
changes by +527.721 kJ. Energy-reference terms also change as water leaves the
open tank control volume; their corresponding transported energy must use the
same reference. These storage results do not establish gas heating or a closed
energy balance. No thermal closure or hardware result is inferred from them.
