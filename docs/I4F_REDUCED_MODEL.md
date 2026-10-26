# I4F internal discharge reduced model

## Scope and coordinate frame

This is a single-liquid, lumped-inertia model for the initial discharge from a
partially filled, pressurized tank through an opening valve surrogate, a circular
pipe, a circular-to-rectangular transition, and a horizontal rectangular outlet.
It predicts tank inventory, gas pressure, line flow, pressure losses, and outlet
momentum flux. Integration stops when the liquid surface first reaches the upper
edge of the tank connection. Physical validity may end earlier: the reconstructed
line pressure can fall below water saturation pressure while the equations still
produce a mathematical trajectory. That portion requires a vapor/cavity or other
appropriate physical response and cannot be treated as valid liquid-only flow.
It does not predict gas entrainment, the butterfly-disk
wake, transition separation, or the spatial thickness and uniformity of the
external liquid sheet. It is exploratory, not a validated hardware model or
CFD result.

Coordinates are stationary-apparatus SI coordinates: `x` points along the
outlet, `y` is horizontal cross-stream, and `z` is vertical upward. The
baseline tank axis is horizontal along `x`; the pipe and rectangular nozzle
discharge along `+x`. The code also supports a vertical-axis cylindrical tank
whose ends are treated as flat.

## Historical single-outlet baseline inputs

This section and its numerical examples preserve the original single-outlet
assumptions. The later two-branch network and the 25 October confirmed tank
inventory have separate immutable inputs and results, summarized in
[the scientific note](I4F_SCIENTIFIC_NOTE.md). The original baseline file is
not the current hardware specification.

The input record is [`experiments/i4f_baseline.json`](../experiments/i4f_baseline.json).
Only the 1.0 m × 0.15 m outlet dimensions are the
user's nominal dimensions. Tank size, fill, absolute pressure, gas identity,
connection, pipe, transition length and loss, liquid properties, valve
coefficient and opening time are provisional. The baseline models water in the
tank and an ideal-air headspace as a hydraulic reference. The user currently
recalls mostly liquid before charging, but is uncertain whether the real tank
has gaseous oxygen above liquid retardant before later CO₂ pressurization. The
reference therefore does not establish the actual fluid or pressurization
arrangement, and it does not model the unconfirmed historical CO₂ supply.

| Quantity | Baseline | Status |
|---|---:|---|
| Tank diameter × axial length | 1.0 × 2.0 m | Assumed |
| Tank axis / center elevation | Horizontal `x` / 1.0 m | Assumed |
| Initial water fill fraction | 0.70 | Assumed |
| Tank connection center / upper edge | 0.65 / 0.775 m | Assumed; pipe diameter sets the upper edge |
| Initial gas pressure / ambient pressure | 0.900 / 0.100 MPa absolute | Assumed, not a confirmed 8 bar gauge trace |
| Gas / initial temperature / `n` | Air / 293.15 K / 1.25 | Air and `n` are modeling assumptions |
| Pipe diameter × straight length | 0.25 × 1.0 m | Assumed |
| Transition length / local `K` | 1.5 m / 0.2 | Assumed; `K` referenced to pipe velocity |
| Rectangular outlet width × height | 1.0 × 0.15 m | User nominal dimensions |
| Water density / dynamic viscosity | 998.2 kg/m³ / 0.001002 Pa·s | Assumed at 293.15 K |
| Valve effective `C_d` / opening time / minimum effective opening | 0.7 / 0.5 s / 0.02 | Provisional orifice surrogate; current baseline floor matches the CFD scalar restriction, not measured valve clearance |
| Pipe equivalent roughness | 10 μm | Assumed |

The circular tank volume is `V_T = pi D_T^2 L_T / 4 = 1.57080 m^3`.
The initial tank water and sealed gas volumes are 1.09956 and
0.471239 m³. Horizontal-tank level is inverted from the circular-segment
volume relation; at 70% fill the interface is at `z = 1.15985 m`.
The connection's upper edge at `z = 0.775 m` defines the mean-level screening
event, leaving 0.351084 m³ in the tank. It does not predict actual gas
breakthrough: CFD shows a local gas path to the intake while substantially more
water remains. The single-liquid reduced model stops before it can represent
that gas/water discharge regime.

New outputs also report section-mean absolute pressure at the pipe-side
transition entrance and a lumped station after the valve. They retain the
instantaneous ODE acceleration and downstream inertance, kinetic-head change
and losses. A first pressure at or below the approximate 20 C pure-water
saturation reference (2,339.2 Pa, IAPWS SR1-86(1992)) is recorded separately
from the geometric crown event. Integration continues for reproducibility;
neither that continuation nor a negative-pressure segment is a valid model of
vapor/cavity dynamics. The saved 18-case screen is in
`results/runs/i4f-reduced-static-pressure-screen-20261024T100659Z/`.

## Balances and closures

Let `V_w` be tank water volume, `Q >= 0` be line volume flow, `p_g` be
headspace absolute pressure, `z_s` be free-surface elevation, `z_o` be
outlet center elevation, and `A_p`, `A_n` be pipe and nozzle areas. The tank
inventory balance and sealed-gas law are

\[
\frac{dV_w}{dt}=-Q,\qquad V_g=V_T-V_w,\qquad p_g V_g^n=p_{g0}V_{g0}^n.
\]

The ideal-gas sealed-air mass is fixed at

\[
m_g=\frac{p_{g0}V_{g0}}{R_{air}T_0},\qquad
T_g=T_0\left(\frac{V_{g0}}{V_g}\right)^{n-1}.
\]

The code distinguishes a `maintained_pressure` mode, where pressure is held
constant by an unspecified external supply. It does not infer that supply's
mass or energy flow, and that mode must not be read as sealed blowdown. The
declared sensitivity uses n=1.0, 1.25, and 1.4: isothermal, a provisional
intermediate exponent, and an ideal-air adiabatic reference. The n=1.25 case is
not fitted to I4F data. Near room temperature, the NIST dry-air ideal-gas heat
capacity formulation gives Cp/Cv close to 1.4; this is calculated from Eqs.
(14)/(18), §4.4 and Table 12 on pp. 345–346 of Lemmon et al., *J. Phys. Chem.
Ref. Data* 29(3), 331–385 (2000), DOI
[10.1063/1.1285884](https://doi.org/10.1063/1.1285884). This makes n=1.4 a
useful comparison if CFD uses ideal air, adiabatic walls, and uniform headspace
thermodynamics. Interfacial heat transfer to liquid could make the actual
effective exponent lower; n is a lumped gas-energy closure, not a solved first
law for the gas, liquid, wall, or foam. Heat transfer, wall thermal mass,
humidity, possible gas within the liquid, CO₂ properties, and real-gas
corrections are omitted. The actual liquid composition or gas inventory is
unconfirmed.

The pressure/inertia balance is

\[
 p_g-p_a+\rho g(z_s-z_o)+\frac{\rho}{2}\left(\frac{Q}{A_s}\right)^2
 = I_Q\frac{dQ}{dt}+
 \Delta p_{pipe}+\Delta p_{entrance}+\Delta p_{valve}+\Delta p_{transition}
 +\frac{\rho}{2}\left(\frac{Q}{A_n}\right)^2,
\]

where the upstream surface-velocity term is retained as a Bernoulli correction.
For this large tank, it is small compared with the pipe velocity head. Only the
water-filled pipe and transition contribute to line inertance:

\[
I_Q=\rho\left[\frac{L_p}{A_p}+\int_0^{L_t}\frac{dl}{A(l)}\right],
\quad
A(l)=A_p+\frac{l}{L_t}(A_n-A_p),
\]

so the transition integral is

\[
\int_0^{L_t}\frac{dl}{A(l)}=
L_t\frac{\ln(A_n/A_p)}{A_n-A_p}.
\]

The reduced transition uses the linear-area polar loft also used by the
parameterized CFD apparatus. It gives a pipe-plus-transition water prefill of
0.198403 m³ (198.046 kg at the assumed density). The prefilled line stays in
the internal liquid inventory. Under this constant-area-flow incompressible
line model, its inventory is constant and outlet volume equals tank drawdown;
the initial prefill is therefore not added again to cumulative released mass.
For the same line, the integrated axial momentum is
\(P_{line}=\int\rho A u\,dl=\rho Q(L_p+L_t)\), because
\(u(l)=Q/A(l)\). It must not be estimated by multiplying all prefilled line
mass by the pipe velocity when the transition area varies.

Pipe friction uses Darcy-Weisbach:

\[
\Delta p_{pipe}=f_D\frac{L_p}{D_p}\frac{\rho}{2}
\left(\frac{Q}{A_p}\right)^2,
\qquad
Re=\frac{\rho |Q|D_p}{\mu A_p}.
\]

For `Re <= 2300`, `f_D = 64/Re`, implemented in its Hagen-Poiseuille linear
flow limit at `Q -> 0`. For `Re >= 4000`, the turbulent Darcy factor uses
the Haaland explicit approximation

\[
\frac{1}{\sqrt{f_D}}=-1.8\log_{10}\left[
\left(\frac{\epsilon/D_p}{3.7}\right)^{1.11}+\frac{6.9}{Re}\right].
\]

Between 2300 and 4000 the code linearly blends the laminar value and Haaland
value for a continuous, numerically defined transitional closure. Haaland's
correlation was proposed for turbulent pipe flow and is used in its stated
turbulent range here; the transitional interpolation is an implementation
choice. Source: S. E. Haaland, “Simple and Explicit Formulas for the Friction
Factor in Turbulent Pipe Flow,” *Journal of Fluids Engineering* 105(1), 89–90
(1983), DOI [10.1115/1.3240948](https://doi.org/10.1115/1.3240948), pp. 89–90.
The laminar limit follows the circular-pipe Hagen-Poiseuille relation.

The sharp-edge tank-to-pipe entrance is assigned a separate
\(\Delta p_{entrance}=\rho K_e(Q/A_p)^2/2\), with baseline \(K_e=0.5\)
referenced to pipe mean velocity. This is an approximate analogy to a square-
edged reservoir entrance: Table 2 reports \(K_e=0.50\pm0.06\) for a physical
square-edge, 375 mm culvert entrance. That study is not I4F hardware; its stated
uncertainty is used as a rough \(0.3\)–\(0.7\) sensitivity interval, not as an
I4F measurement. Source: “Effects of Bottom-Up Blockage on Entrance Loss
Coefficients and Head-Discharge Relationships for Pipe Culvert Inlets,”
*Journal of Irrigation and Drainage Engineering* 150(2) (2024), DOI
[10.1061/JIDEDH.IRENG-10219](https://doi.org/10.1061/JIDEDH.IRENG-10219), Table 2.

The valve is represented only as an equivalent time-dependent orifice:

\[
\Delta p_{valve}=\frac{\rho}{2}
\left(\frac{Q}{C_d A_p a_{\mathrm{eff}}(t)}\right)^2,
\quad
a(t)=3s^2-2s^3,\quad s=\operatorname{clip}(t/t_v,0,1).
\]

The commanded stroke \(a(t)\) is distinct from the effective hydraulic opening
fraction used by the loss law. A configurable minimum effective opening
\(a_{\min}\) is applied as a floor, matching the current CFD momentum sink:
\[
a_{\mathrm{eff}}(t)=\max(a_{\min},a(t)).
\]
If a config omits the value, \(a_{\min}=0\) preserves the original zero-flow
startup. The current shared baseline explicitly sets 0.02. An optional 0
versus 0.02 comparison matches the numerical minimum-open fraction used in
the current CFD apparatus case; it is an explicit hydraulic surrogate input,
not a measured I4F valve clearance. The command stroke is
written separately as valve_command_fraction; opening_fraction records the
effective area fraction used in the loss law.

Thus its equivalent loss coefficient on pipe velocity is
\(K_v=[C_da_{\mathrm{eff}}(t)]^{-2}\), and the baseline full-open value is 2.04. This is a
provisional effective-area mapping, not a butterfly disk-angle law, not a
measured `C_v`, and not a source-grounded `K(theta)` curve. It cannot
predict disk wake or asymmetric downstream flow. The separate transition term
is `delta_p_t = rho K_t (Q/A_p)^2 / 2`, with provisional `K_t=0.2`; no
resolved local separation loss has yet been obtained.

The current shared baseline explicitly declares the 0.02 minimum opening.
Earlier reduced runs with no floor field in their captured input use the
original zero-floor behavior; those inputs and results remain unchanged. Run the
matched hydraulic-floor sensitivity with
--compare-minimum-openings; it retains all three n values and all three
stroke durations at a_min in {0, 0.02}. For one explicit floor, use
--minimum-effective-opening 0.02. Neither setting alters the shared baseline
configuration or the preserved earlier bundles; the explicit comparison
overrides the configured value for each reported run.

The output kinetic term is \(\rho(Q/A_n)^2/2\). The model omits a finite
nozzle length, liquid compressibility, valve/structure inertance, tank-side
contraction losses beyond the entrance and scalar valve terms, and reverse
flow. The calculation stops before gas breakthrough can be carried into the
line.

## Numerics and reproducibility

`src/aerial_drop/i4f_reduced.py` uses NumPy and a fixed-step implicit midpoint
update for the liquid-column equation. A scalar positive-root solve handles
time-dependent quadratic valve/entrance/transition losses without unstable startup
steps at zero flow. Water volume advances with the midpoint flow and the final
step is shortened to land on the gas-breakthrough event. The default step is
0.0001 s. No random process is used. The output includes per-step CSV, a JSON
summary, source-config and code hashes, revision/dirty state, package versions,
and PNG plots. HDF5 is optional and was not written because `h5py` is
unavailable.

The entrance-corrected run's parsed configuration and the exact model/runner files were
also preserved in
[`results/runs/i4f-reduced-source-authoritative-20261023T210629.191907Z`](../results/runs/i4f-reduced-source-authoritative-20261023T210629.191907Z).
During that run the raw config path changed to add lamellae metadata; the
startup snapshot and end-state config have the same numerical model inputs.
The summary therefore hashes the end-state file, while `config_source.json`
records the parsed startup config. The runner now captures raw and parsed
inputs and code snapshots before starting a calculation.

The tank/line/external-water ledger follows from the same \(dV_w/dt=-Q\)
inventory update, and the \(p_gV_g^n\) residual checks the selected gas law;
neither is independent physical validation. Independent limiting checks
compare low-Re pipe loss with Hagen-Poiseuille flow and compare constant-head
startup with the exact inertial-orifice solution. For
\(I\,dQ/dt=\Delta p-bQ^2\), \(Q(0)=0\), the exact result is
\(Q(t)=Q_\infty\tanh(t/\tau)\), with
\(Q_\infty=\sqrt{\Delta p/b}\), \(\tau=I/\sqrt{\Delta p b}\), and
\(V(t)=Q_\infty\tau\ln\cosh(t/\tau)\). These tests verify the numerical
equation limit, not the adequacy of the assumed system closures.

## Exploratory result

The corrected baseline and \(n\in\{1.0,1.25,1.4\}\),
\(t_v\in\{0.1,0.5,1.0\}\,\mathrm s\) sensitivity bundle are preserved in
[`results/runs/i4f-reduced-20261023T205747.576470Z`](../results/runs/i4f-reduced-20261023T205747.576470Z)
(ignored run data). The earlier
[`results/runs/i4f-reduced-20261023T205141.710444Z`](../results/runs/i4f-reduced-20261023T205141.710444Z)
bundle omitted the now-added sharp-edge entrance loss and is preserved as a
superseded exploratory run. The corrected bundle summary includes the config
and code hashes, software versions, resource use and numerical refinement
check. Main derived
observables are volume flow, mass flow, gas pressure, tank water/gas inventory,
pipe and outlet mean speeds, individual pressure losses, and outlet momentum
flux \(\rho Q^2/A_n\). The momentum flux is a force-like flux in newtons, not
the momentum stored in the line.

For the original zero-floor case with \(n=1.25\), a 0.5 s opening and entrance \(K_e=0.5\), the model
reaches the event in 1.22763 s, draining 0.748473 m³ (747.126 kg) from the
tank. Peak flow is 0.86662 m³/s, peak nozzle mean speed is 5.777 m/s, and
outlet momentum flux peaks at 4.998 kN. Sealed-air pressure falls from 0.900
to 0.274 MPa absolute. Near peak flow, the modeled pressure drive is 455.81
kPa; the approximate entrance, valve, transition, exit kinetic, and straight-
pipe losses are 77.78, 323.60, 31.11, 16.66, and 6.75 kPa, respectively.
These component drops are algebraic model outputs, not CFD pressure taps.
The discharged mass is the same in all nine cases because the tank geometry
and gas-breakthrough level are fixed. For the 0.5 s opening, stop time rises
from 1.13990 s at \(n=1\) to 1.22763 s at \(n=1.25\) and 1.28878 s at
\(n=1.4\); corresponding peak flow falls from 0.9105 to 0.8666 to
0.8426 m³/s. At \(n=1.25\), increasing the opening time from 0.1 to 1.0 s
lengthens the stop time from 1.04145 to 1.46554 s and reduces peak flow from
1.0196 to 0.7348 m³/s. Final gas pressure varies with \(n\) but is independent
of valve opening time at this fixed event volume, as required by the sealed
polytropic law.

### Minimum-opening sensitivity

The exact max-floor comparison is preserved at
results/runs/i4f-reduced-20261023T230314.651620Z (ignored result data). It uses
the same provisional inputs and \(n\in\{1,1.25,1.4\}\),
\(t_v\in\{0.1,0.5,1.0\}\), with floors 0 and 0.02. An earlier bundle at
results/runs/i4f-reduced-20261023T224707.490442Z used the affine mapping
\(a_{\min}+(1-a_{\min})a(t)\); it is preserved as an exploratory run but is
superseded for CFD matching because CFD uses \(\max(a_{\min},a(t))\). The
following table holds \(t_v=0.5\) s:

| \(n\) | Floor | Stop time (s) | Peak \(Q\) (m³/s) | Discharged mass (kg) | Final \(p_g\) absolute (MPa) |
|---:|---:|---:|---:|---:|---:|
| 1.00 | 0 | 1.13990 | 0.91047 | 747.126 | 0.347717 |
| 1.00 | 0.02 | 1.13929 | 0.90999 | 747.126 | 0.347717 |
| 1.25 | 0 | 1.22763 | 0.86662 | 747.126 | 0.274140 |
| 1.25 | 0.02 | 1.22703 | 0.86606 | 747.126 | 0.274140 |
| 1.40 | 0 | 1.28878 | 0.84258 | 747.126 | 0.237695 |
| 1.40 | 0.02 | 1.28818 | 0.84197 | 747.126 | 0.237695 |

For \(n=1.25\), floors 0 / 0.02 give stop times and peak \(Q\) of
1.04145 / 1.04134 s and 1.01956 / 1.01937 m³/s at \(t_v=0.1\) s;
1.22763 / 1.22703 s and 0.86662 / 0.86606 m³/s at 0.5 s; and
1.46554 / 1.46430 s and 0.73484 / 0.73410 m³/s at 1.0 s. Across these
declared cases, the 0.02 area floor advances breakthrough by 0.01–0.08%
and lowers peak flow by 0.02–0.10%. Event discharge and final polytropic
pressure are unchanged because the stopping inventory is fixed. These are
hydraulic floor sensitivities, not a measured butterfly characteristic; the
model does not resolve the disk or its wake.

The ideal-gas polytropic temperature law predicts 231.12 K at breakthrough for
\(n=1.25\) and 200.39 K for \(n=1.4\), from the assumed initial 293.15 K.
The latter is the reference to compare with an ideal-air, adiabatic-wall CFD
case. This strong cooling is a consequence of the sealed-gas closure; it is not
a prediction of the actual pressurizing gas or the liquid retardant.

Halving the integration step from 0.0001 to 0.00005 s changed baseline event
time by \(1.01\times10^{-10}\) relative, peak flow by
\(-1.34\times10^{-8}\), momentum impulse by \(-8.40\times10^{-9}\), and final
gas pressure by zero at reported precision. The tank-plus-line-plus-external
water ledger closes to the stored precision, and maximum drift in
\(p_gV_g^{1.25}\) is below \(5\times10^{-16}\). These checks establish
time-step consistency of this reduced equation set; they do not bound the
dominant valve, actual gas/fluid composition, and transition-model uncertainties.

### Early-time CFD comparison

The exploratory overlay is in
`results/runs/i4f-reduced-cfd-overlay-20261023T225942Z/analysis/reduced-cfd-overlay-matched-floor-v2/`.
It compares the 0.5 s opening and 0.02 minimum-opening law against the
146,354-cell CFD case at saved times 0.1, 0.2, and 0.3 s. For the n=1.4
reduced case, headspace pressure is 885.6, 820.0, and 709.0 kPa absolute,
compared with reconstructed CFD headspace means of 883.7, 818.4, and 714.4
kPa. Reduced whole-column flow is 10.8%, 5.7%, and 3.5% below the approximate
CFD internal-nozzle-plane flow at those times. The reduced analytic tank
inventory and CFD cell-volume inventory have different initial values; the
comparison therefore uses drawdown from each model's own initial state.

These are early exploratory comparisons, not a fit or a validation result.
CFD nozzle flow is reconstructed from sampled \(\alpha U\), not the native
conservative phase flux. Startup external air appears at the nozzle at 0.1 s,
then clears by 0.2 s, so that early gas fraction is not evidence of tank-gas
arrival. Pressure-section values are spatially reconstructed means; their
differences do not isolate local loss coefficients. The figure and CSVs are
in the same bundle. Its first-law diagnostic uses
\(Q_{app}=\Delta U+\int p\,dV\); the zero-heat prediction is
\(U_0-\int p\,dV\). The coarse 0.1 s quadrature gives \(Q_{app}=19.7\) kJ by
0.3 s. This apparent subsystem residual is not attributed to physical heat
transfer and omits gas kinetic/potential energy and any gas crossing the tank
boundary. The corrected v2 figure clips reduced curves to the plotted 0–0.3 s
window and uses the zero-heat sign above.

The output is a hydraulic-history estimate under the stated assumptions. It
does not establish outlet sheet uniformity, actual I4F discharge timing,
butterfly-valve behavior, the disputed pressurization supply, or nearfield CFD
accuracy. These require measured pressure/flow/valve traces and the resolved
water-air apparatus comparison.
