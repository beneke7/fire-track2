# E1 Rouaix Case 1 gate draft

**Gate recommendation: NOT READY to freeze a source-grounded pass/fail E1 comparison.**
An independent inspection of the exact HAL author-manuscript PDF confirms the
Case 1 conditions, the Figure 13 digitizations, and the source limitations
recorded below. It also supports an inference that `z` is a full transverse
span: Section 4.3 says `z approximately d_j` close to the nozzle, where the
round exit diameter is `d_j`; the primary Figure 13 digitization reads
`z/d_j=1.071` at `x/d_j=0.25`. That is stronger evidence than treating half-
and full-width as equally likely, but the paper does not state the exact
extraction operation. More decisively, Figure 13 has no sample time or averaging window.
The source's approximately 5 s stabilized-run statement and separate 4.5 s
snapshots make a final-window comparison a reasonable **proposed assumption**,
not a source-defined target. Figure 16 is a `q`-level landmark and cannot be
uniquely assigned to Case 1 because Cases 1, 8, and 9 share `q=17.3`.

This is a proposed correction packet responding to the seven findings in
[`docs/reviews/E1_GATE_REVIEW_2_20260925T085302Z.md`](../docs/reviews/E1_GATE_REVIEW_2_20260925T085302Z.md),
not a reviewer-ready experiment record or an accepted contract. Every added
setting and limit marked **provisional** remains for independent decision; no
paper input has been recovered by these proposals. The gate stays **NOT READY**
until the reviewer accepts or replaces the input/deviation matrix, scoring
conventions, limits, and mesh/execution split below. Provisional case/mesh
preparation and static checks are already authorized; this does not authorize
a solver run. A separately preregistered and independently reviewed bounded
solver characterization remains distinct from E1. If source-semantic
reconstruction is not accepted, report a descriptive overlay without a
pass/fail label, as allowed by
[`docs/VALIDATION.md`](../docs/VALIDATION.md#published-case-comparison-gates).

E2 execution remains closed until the independent reviewer records an
**accepted E1 disposition that explicitly authorizes advancement**. A failed,
inconclusive, or descriptive-only E1 disposition does not release E2 execution;
only a separately reviewed prospective scope amendment can do so. Independent
E2 method preparation may continue without a case run.

This draft is a source and gate assessment, not an accepted experiment record,
tolerance, solver result, or validation claim. It covers Rouaix Case 1 only: one
round nozzle, not the separate four-nozzle B747 comparison. The CPU route is
now identified precisely: the installed `opencfd/openfoam-default:2512`
container has `interIsoFoam`. A provisional static Rouaix case and dictionaries
now exist in [`cases/e1_rouaix_case1_static`](../cases/e1_rouaix_case1_static/)
and passed exact review for static-preparation artifact scope only. They are
not meshed or run and do not pass this E1 gate. Existing P0/P1 runs establish
only a different four-slot laminar box and do not qualify this benchmark.

## Evidence classification

| Item | Classification and value | Source / extraction | Gate use and limit |
| --- | --- | --- | --- |
| Installed CPU solver route | **Available:** OpenFOAM v2512 `interIsoFoam` in CPU image `opencfd/openfoam-default:2512` (image ID `sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`); the image also has `blockMesh`, `checkMesh`, `snappyHexMesh`, `surfaceFeatureExtract`, MPI and VTK tools. | Read-only image inspection; P0/P1 evidence in [`docs/COMPUTE.md`](../docs/COMPUTE.md#current-cpu-vof-pilot) and [`P1_SOURCE_EVENT_LEDGER.md`](P1_SOURCE_EVENT_LEDGER.md). | `interIsoFoam` provides two-fluid incompressible/isothermal VOF with isoAdvector, gravity, constant phase properties and surface tension. A provisional static Rouaix case/dictionary package exists and passed exact static-artifact review only; there is no mesh or E1 run. P0/P1 use a flat plate, four rectangular slots, 50 m/s crossflow, symmetry side planes and laminar flow. |
| Case 1 nozzle and flow conditions | **Reported:** one round nozzle, `d_j=0.40 m`, `v_j=10 m/s` downward, `u_g=70 m/s` in crossflow, `q=17.3`, `We_g=3.2e4`, `We_j=5.54e5`, `I_j=0.01`; realizable `k-epsilon`; listed mesh `Delta x=16 mm`. | Rouaix et al., HAL author manuscript, PDF p. 5 / article p. 4, Tables 2–3; transcribed in [`E1_ROUAIX_CASE1_SOURCE.md`](E1_ROUAIX_CASE1_SOURCE.md). | Sufficient to identify the single-nozzle reference row and core operating point. Preserve reported coordinates: `+x` crossflow, `-y` liquid velocity and gravity, `z` spanwise (PDF p. 4 / article p. 3, Fig. 1). |
| Fluid properties and dimensionless check | **Reported:** water `rho_j=997.6 kg/m^3`, `mu_j=8.89e-4 Pa s`; air `rho_g=1.18 kg/m^3`, `mu_g=1.86e-5 Pa s`; `sigma=0.072 N/m`, `g=9.81 m/s^2`, `p=101325 Pa`, `T=300 K`. OpenFOAM's phase input uses kinematic viscosity: `nu_j=8.91139e-7 m^2/s`, `nu_g=1.57627e-5 m^2/s`. | PDF p. 5 / article p. 4, Table 2; source record above. | Recalculation gives `q=17.254`, `We_g=3.212e4`, `We_j=5.542e5`, `Re_g=1.776e6`, and `Re_j=4.489e6`. The first four agree with the printed values to shown precision; the last differs from Table 3's `Re_j=4.9e6` by about 9%. Do not tune a reported property to force agreement. The source gives no statistical uncertainty for these properties; independent reviewer must resolve the `Re_j` discrepancy or explicitly carry it as a source inconsistency. `interIsoFoam` is isothermal/incompressible: `T` informs the reported properties, while absolute `p=101325 Pa` is a reference offset, not a compressible thermodynamic input. |
| Inlet area and flux | **Derived:** circular area `pi*d_j^2/4 = 0.125664 m^2`; volume flux `1.25664 m^3/s`; mass flow approximately `1.254e3 kg/s`; downward momentum-flux magnitude approximately `12.54 kN`. | Arithmetic from the reported Case 1 diameter, velocity, and water density; arithmetic is recorded in `E1_ROUAIX_CASE1_SOURCE.md`. | Audit values only. They do not establish a finite release time, payload, or transient source history. No Case 1 duration or total mass is reported. |
| Numerical method | **Reported:** transient, incompressible 3-D finite-volume VOF with CSF surface tension; realizable `k-epsilon` RANS and two-layer wall treatment; HRIC interface scheme, second-order upwind convection, first-order implicit time integration; `dt=1e-3 s`, reported CFL 3.2–5.7. `chi=0.1` is the dilute cloud surface used for the Figure 13 observables; `chi=0.9` defines the liquid core used for breakup. | PDF p. 6 / article p. 5, Section 3.1 and equations (3)–(7); source record. The installed [OpenFOAM v2512 solver inventory](https://www.openfoam.com/documentation/user-guide/a-reference/a.1-standard-solvers) describes `interIsoFoam` as an incompressible, isothermal two-fluid VOF solver using isoAdvector. | **Approximation:** `interIsoFoam` uses isoAdvector, not STAR-CCM+ HRIC; its interface advection cannot be relabelled HRIC. OpenFOAM v2512 includes `realizableKE`, but the documented [`twoLayerTreatment`](https://api.openfoam.com/2512/classFoam_1_1RASModels_1_1kEpsilon.html) belongs to standard `kEpsilon`, not the realizable model ([v2512 release note](https://www.openfoam.com/news/main-news/openfoam-v2512/solvers-and-physics)). The candidate must therefore choose, disclose and review either realizable `k-epsilon` with ordinary wall functions or standard `kEpsilon` with its two-layer option; neither is the reported exact pairing. Disclose all other scheme differences and do not infer equivalence from matching nominal `dt`/mesh. |
| Domain and boundaries | **Reported:** curved no-slip top wall; trapezoidal domain about `25 d_j` high, top `50 d_j x 17.5 d_j`, bottom `50 d_j x 40 d_j`, opening angle `25 degrees`; uniform air inlet starts `2.5 m` upstream of nozzle center; uniform-velocity nozzle inlet; remaining boundaries are pressure outlets at atmospheric pressure. | PDF p. 7 / article p. 6, Section 3.2 and Fig. 3. Dimensions in SI are about 20 m streamwise by 7 m spanwise at the top, 20 m by 16 m at the bottom, and 10 m high. | Standard patch fields and the installed surface-meshing tools can represent the reported boundary types and full 3-D domain. Exact curved aircraft-wall coordinates are not published; a schematic reconstruction is provisional. The source does not state wall contact angle. Preserve full 3-D with no symmetry plane; freeze the wall shape and alpha/contact-angle treatment, and include a flat-wall comparison only as a sensitivity because the paper's flat-wall statement is unquantified. A smaller box or symmetry restriction is a changed case unless justified against these observables. |
| Grid and elapsed simulation | **Reported:** locally refined unstructured polyhedral meshes with five prism layers and growth ratio 1.1; mesh sizes 70, 50, 30 and 16 mm; the authors selected 16 mm for reported study curves. They state each case ran about 5 s until penetration and transverse expansion were established/stabilized. The mesh study says the finest grid costs eight times the coarsest and lateral width is harder to converge than penetration. | PDF p. 8 / article p. 7, Section 3.3 and Figs. 4–6. Fig. 5 has a 4.5 s snapshot; Figure 13 itself has no time or averaging annotation. | The stabilization statement makes a steady-regime comparison plausible but does not identify which instant/window generated Figure 13. There is no cell count or runtime in the manuscript extraction to cost a full replica from specifications alone. |
| Figure 13 penetration and expansion | **Digitized:** plotted `y/d_j` and `z/d_j` versus their separate `x/d_j` samples for the green-plus Case 1 (`q=17.3`); both axes retain the source's normalization. Primary vector-path trace: [`data/derived/rouaix_e1_case1_fig13.csv`](../data/derived/rouaix_e1_case1_fig13.csv). Independent raster trace: [`data/derived/rouaix_e1_case1_fig13_raster.csv`](../data/derived/rouaix_e1_case1_fig13_raster.csv). | HAL PDF p. 13 / article p. 12, Fig. 13; trace procedure and calibration are documented in `E1_ROUAIX_CASE1_SOURCE.md`. The author-manuscript PDF used for those traces has SHA-256 `624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446`. | Use the plotted points as the direct descriptive target; do not treat the two observable x-grids as matched. The raster trace is at the primary trace's x coordinates, so it is an independent extraction method, not a separate sampling design. |
| Figure 13 extraction bounds | **Digitization bounds, not standard deviations:** primary ordinate bounds are `0.07` for `y/d_j` and `0.04` for `z/d_j`; primary x bounds are `0.02` and `0.01`, respectively. Raster bounds are local-trace heuristics; at `z/d_j`'s `x/d_j=0.25` point the traces overlap and the raster method uses one-sided extrapolation (`0.082` bound). | CSV columns `sigma_value_over_dj`, `sigma_x_over_dj` and `sigma_raster_bound`; detailed methods in `E1_ROUAIX_CASE1_SOURCE.md`. | These do not include source-model uncertainty or temporal variability. Cross-method RMSE is 0.019 for penetration and 0.028 for width; maximum differences are 0.051 and 0.088, both within the documented combined extraction bounds. Do not convert bounds to Gaussian errors or combine by root-sum-square without a statistical model. |
| Figure 13 time and width semantics | **Time unstated; full-span interpretation inferred, exact operation unstated:** Section 3.3 says about 5 s is run to establish stabilized penetration/expansion; Figs. 1, 5, and 8 show separate 4.5 s morphology snapshots. Fig. 13 caption and Section 4.3 use `z` for transverse expansion of the `chi=0.1` cloud. Section 4.3's `z approximately d_j` close to a circular `d_j` exit supports reading `z` as full span, but the source does not explicitly prescribe `max(z)-min(z)`, treatment of detached `chi>=0.1` structures, or a sample/averaging interval. | HAL PDF pp. 4, 8, 13, 15 / article pp. 3, 7, 12, 14; Figs. 1, 5, 8, and 13, Section 4.3. | Proposed width observable: full span of the `chi=0.1` cloud at fixed streamwise `x`, using the outermost threshold crossings. This is an inference requiring review. Do not assign Figure 13 to 4.5 s or 5 s without declaring the final-window assumption; preserve the unresolved time limitation. |
| Section 4.3 fitted relations | **Reported:** `y/d_j = 1.15 q^0.379 (x/d_j)^0.54`; `z/d_j = 2.1 q^0.171 (x/d_j)^0.49` for `z >= 0.25 d_j`; near the nozzle `z approximately d_j`. The paper reports coefficients from Fig. 14 slopes and prefactors plotted against `q`, and says Fig. 15 curves collapse after scaling. | HAL PDF p. 15 / article p. 14, Section 4.3, Eqs. (8)–(11), Fig. 15. At `q=17.3`, printed rounded coefficients yield `y/d_j=3.388 (x/d_j)^0.54` and `z/d_j=3.419 (x/d_j)^0.49`. | These are cross-case empirical fits, not a replacement for the direct Case 1 points or a pointwise acceptance target. Digitized Fig. 13 versus the fits has RMSE 0.552 for `y/d_j` and 0.693 for `z/d_j`; e.g. at `x/d_j=2.5`, Fig. 13 `z/d_j=4.328` versus fit `5.357`. The residual is larger than the trace-digitization bound, but fit scatter/coefficient uncertainty is unreported; retain this only as a secondary consistency check, not a source contradiction or pass/fail criterion. |
| Breakup landmark | **Digitized q-level marker, not Case-1-specific:** Fig. 16's time-mean locations of the `chi=0.9` core breakup give approximately `(x_BU/d_j,y_BU/d_j)=(8.91,10.04)` near `q=17.3`, with about `0.25` normalized-coordinate trace uncertainty. Cases 1, 8 and 9 share `q=17.3`. | HAL PDF p. 14 / article p. 13, Fig. 16 and Section 4.4; digitization is documented in `E1_ROUAIX_CASE1_SOURCE.md`. | Report as contextual q-level evidence only; do not label an apparent match as Case-1-specific. Section 4.4 defines breakup as a time mean but does not give the averaging window. |

## Source audit conclusion and smallest remaining decisions

The author PDF was fetched from the cited HAL file URL and its SHA-256 was
`624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446`, matching
the exact file identity recorded for the two digitizations. Direct text and
figure inspection confirms that Figure 13 names Case 1 (`+`, `q=17.3`) and
uses the `chi=0.1` cloud surface; the primary vector-path and independent raster
traces agree within their documented extraction bounds. No additional Figure
13 timing or post-processing statement appears in the cited manuscript.

The remaining source/decision blockers are specific:

1. **Figure 13 temporal target:** the manuscript says each case runs about 5 s
   until penetration/expansion is established (PDF p. 8 / article p. 7), and
   gives 4.5 s morphology images (PDF pp. 4, 8 / article pp. 3, 7), but Figure
   13 (PDF p. 13 / article p. 12) gives no snapshot or averaging time. The
   smallest source that resolves this is the authors' Figure 13 sampling
   timestamp/window or original time-resolved post-processing data. Without
   it, a 4.5–5.0 s comparison can only be a reviewer-approved stabilized-regime
   assumption, not a reproduction of a uniquely identified source instant.
2. **Figure 13 width operation:** `z approximately d_j` near a circular nozzle
   strongly supports a full-span reading; it does not specify whether detached
   `chi>=0.1` liquid is included when finding the outer limits. The smallest
   source is the author's definition/algorithm or the per-time contour used to
   make Figure 13. Pending that, propose full span between the outermost
   `chi=0.1` crossings and label it inferred. This avoids a silent factor-of-two
   change but does not erase the extraction uncertainty.
3. **Figure 16 breakup landmark:** Section 4.4 (PDF p. 15 / article p. 14)
   defines breakup positions as time means of `chi=0.9` core breakup, but Fig.
   16 (PDF p. 14 / article p. 13) identifies points only by `q`; Cases 1, 8,
   and 9 share `q=17.3`. The smallest source is a Case-1-specific marker/value
   and averaging window. Pending that, the plan's breakup comparison can be
   reported as contextual `q`-level evidence, with no breakup pass/fail test.
4. **Run-specific turbulence and initialization:** the paper does not report
   an initial velocity field, an air-inlet turbulence specification, or a
   complete conversion from liquid `I_j=0.01` to `k`/`epsilon` inputs. An
   isotropic intensity conversion gives the candidate `k=1.5(I_j v_j)^2 =
   0.015 m^2/s^2`; `epsilon` still depends on a turbulence length-scale
   assumption. The exact STAR-CCM+ input deck or an independent reviewer
   decision accepting declared mappings and their sensitivity as reconstruction
   assumptions is needed. Mark them assumed; do not describe them as measured
   or exact source inputs.
5. **CPU mesh and wall reconstruction:** the installed OpenFOAM route has
   standard meshing tools, but the manuscript does not publish coordinates for
   the aircraft underside. A provisional static E1 case and boundary
   dictionaries now exist and passed exact review at static-preparation scope;
   no mesh or E1 run exists. Two independent Figure 13 digitizations are
   recorded, but no source-grounded acceptance sampler or comparison result is
   approved. The curved wall is an explicit analytic assumption, not a source
   trace. Wall alpha/contact-angle choice, mesh family and local refinement
   map still require prospective decision and review. A flat wall is a
   sensitivity case, not recovered geometry.

Thus the PDF plus current project rules do **not** by themselves freeze a
source-grounded pass/fail E1. They do support the following candidate contract
for root/reviewer decision. Accepting its assumptions would freeze a
reconstructed numerical comparison, not recover the authors' undisclosed
Figure 13 extraction history. If those assumptions are not accepted, preserve
an overlay and report “no pass/fail label.” E2 execution remains closed until
an independent reviewer accepts an E1 disposition that explicitly authorizes
advancement. A failed, inconclusive, or descriptive-only E1 does not release
E2 execution unless a separate prospective scope amendment is independently
reviewed and accepted. Independent E2 method preparation may continue.

## Proposed E1 execution contract — review required

### Primary amendment: idealized wall for static preparation (2026-09-25)

The primary adopts the provisional analytic surface
`y=A*(1-exp(-((x/Lx)^2+(z/Lz)^2)))`, with `A=0.080 m` and
`Lx=Lz=0.800 m`, represented by the declared bilinear node grid, for static
case preparation only. These values and the function are project assumptions;
they are neither a Figure 3 trace nor recovered aircraft geometry. The source
figure is a perspective schematic without profile coordinates or a scale
transform, so it does not support a defensible quantitative trace. This
amendment replaces only the prospective Figure 3 trace requirement for static
preparation. Keep the flat-wall and declared geometry sensitivities. This does
not accept the case package, approve a mesh, close D-NUT-BC or contact-angle
decisions, authorize characterization or E1 execution, or permit Figure 13
comparison. Those steps require separate exact review and authorization.

Every value below is proposed for review, not accepted. Tolerance candidates
are taken from the draft values in
[`docs/VALIDATION.md`](../docs/VALIDATION.md#draft-cfd-budgets-for-case-specific-review)
and must be explicitly accepted and frozen before the controlled comparison.

### Case and numerical setup

The matrix below is a provisional, currently incomplete input/deviation
proposal for independent review, not a complete or frozen run record. Named
preparation-owner decisions and exact hashed dictionaries remain prerequisites
to characterization. Case preparation can proceed under the existing
authorization, but all resulting dictionaries and static checks must be
recorded and reviewed. `Reported` means recoverable from the paper; `derived` means
arithmetic from reported values; `provisional` means an explicit reconstruction
that the paper does not provide. The OpenFOAM v2512 route is pinned to image ID
`sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`.
Record that exact ID with all dictionaries and run inputs. Do not substitute
the image tag for the ID in the accepted run manifest.

| Topic | Proposed primary input or limit | Status, deviation, and measurable acceptance evidence |
| --- | --- | --- |
| Case, coordinates, and source | One circular water inlet, `d_j=0.400 m`, `U_j=(0,-10,0) m/s`; gas inlet `U_g=(70,0,0) m/s`; `z` spanwise. Set nozzle-exit center `x_ref=(0,0,0)`; `+x` follows crossflow, `+y` is upward, and `+z` is spanwise. Gravity is `(0,-9.81,0) m/s^2`. Start the continuous source at `t=0` and run at least to `5.0 s`; this is run duration, not a finite payload. | Flow values/axes: Rouaix PDF pp. 4–5 / article pp. 3–4, Figs. 1 and Table 3. Origin placement follows the source coordinate sketch but is an implementation convention. Verify inlet area `0.125664 m^2`, volume flux `1.25664 m^3/s`, water mass flux about `1.254e3 kg/s`, downward momentum-flux magnitude about `12.54 kN`, and area-mean velocity vectors. |
| Fluids and forces | Water `rho=997.6 kg/m^3`, `mu=8.89e-4 Pa s`, `nu=8.91139e-7 m^2/s`; air `rho=1.18 kg/m^3`, `mu=1.86e-5 Pa s`, `nu=1.57627e-5 m^2/s`; `sigma=0.072 N/m`; `T=300 K` recorded but no energy equation; incompressible VOF with CSF. | Table 2, PDF p. 5 / article p. 4; kinematic viscosities are derived. Recalculation gives `q=17.2535`, `We_g=3.2122e4`, `We_j=5.5422e5`, `Re_g=1.7763e6`, and `Re_j=4.4886e6`. The printed `Re_j=4.9e6` is 9.16% higher. Preserve both; do not tune properties to Figure 13. Before execution, the reviewer must accept the property-based result or record an author clarification. |
| Primary RANS and wall treatment | Prospectively nominate `realizableKE` with smooth no-slip walls and high-Re wall functions: `nutkWallFunction`, `kqRWallFunction`, `epsilonWallFunction`. Target `30 <= y+ <= 300` on at least 90% of the curved aircraft-wall area. Record area-weighted y+ distribution, map, and exceptions. | Rouaix reports realizable `k-epsilon` with a two-layer treatment (PDF p. 6 / article p. 5, §3.1). v2512 documents `twoLayerTreatment` for standard `kEpsilon`, so the nominated primary is an approximation. Select it before any Figure 13 result is available; do not choose the alternative by curve agreement. A separately reported sensitivity uses standard `kEpsilon` plus v2512 `twoLayerTreatment` on the same coarse characterization mesh. Neither pairing is claimed to reproduce the paper's exact combination. High-Re y+ target is a provisional wall-function criterion, not a paper value. |
| Liquid inlet/initial turbulence | Reported `I_j=0.01`. Primary isotropic conversion: `k_j=1.5*(I_j*10 m/s)^2=0.015 m^2/s^2`; provisional `L_j=0.07d_j=0.028 m`; `epsilon_j=C_mu^(3/4) k_j^(3/2)/L_j=0.01078 m^2/s^3`, using provisional `C_mu=0.09`. Fixed values on water inlet; initialize non-nozzle domain with the selected air values. | `I_j` is reported in Table 3; `k` is derived, while `L_j`, `epsilon_j`, and `C_mu` mapping are assumptions. The paper provides no inlet dissipation or length scale. Record exact patch/internal values. Candidate length-scale sensitivity: `L_j=0.014` and `0.056 m`; no value is measured. |
| Air inlet/initial turbulence | **Assumption:** `I_g=1%`, `L_g=0.028 m`, `k_g=0.735 m^2/s^2`, `epsilon_g=3.6979 m^2/s^3` from the same isotropic formula and `C_mu=0.09`; fixed values at the uniform `+x` crossflow inlet. | Air turbulence is unreported. Sensitivity candidates are `I_g=0.1%` and `5%` at the primary length scale, plus `L_g=0.014` and `0.056 m` at the primary intensity. Record resulting `k`, `epsilon`, model coefficients, and `nut`; do not describe the primary or sensitivity values as measured. |
| Initial fields | **Provisional:** initialize `U=(70,0,0) m/s` and `alpha.water=0` uniformly in the domain at `t=0`; this is air-only startup with zero initialized water inventory. Initialize `k=k_g=0.735 m^2/s^2`, `epsilon=epsilon_g=3.6979 m^2/s^3`, and `nut=0` before the first realizableKE correction. Initialize static gauge pressure as `p_gauge=0 Pa` everywhere and set `p_rgh=-rho*(g_vec dot (x-x_ref))`, with local initial air density `rho=rho_air`. | The paper does not report initial velocity, water distribution, or pressure. These are assumptions, not recovered initial conditions. Check initial field extrema and water mass (`M_water(0)=0`), reconstruct `p_gauge=p_rgh+rho*g_vec dot (x-x_ref)` at cell centers and boundary faces, and verify inlet/outlet fields against the initialized air state. The inlet boundary values below replace these internal values on their patches at `t=0`. |
| Domain, curved wall, and wetting | Full 3-D trapezoid without symmetry: approximately 20 m streamwise, 10 m high, 7 m top span and 16 m bottom span, 25° opening; gas inlet 2.5 m upstream of nozzle center. For static preparation, use the primary-amended idealized assumed wall `y=A*(1-exp(-((x/Lx)^2+(z/Lz)^2)))`, `A=0.080 m`, `Lx=Lz=0.800 m`, represented by the declared bilinear node grid. This is not a trace from Fig. 3 or recovered aircraft geometry. Use no-slip `U`. Provisional `constantAlphaContactAngle` entry: `theta0 90; limit gradient; value uniform 0;`. The `limit gradient` selection is a project assumption, not a paper value; it still requires exact review before characterization. Alternate valid `limit` entries to assess are `alpha`, `zeroGradient`, and `none`. Contact-angle sensitivity candidates are `theta0=60` and `120 degrees`, with the accepted `limit` unchanged. | Dimensions: PDF p. 7 / article p. 6, §3.2/Fig. 3. The figure is only a perspective domain schematic; curved coordinates, wall roughness, contact angle, and contact-angle limit are not reported. The analytic wall and its parameters are explicit project assumptions for static preparation. The v2512 condition reads `theta0` and requires `limit`; `thetaA`, `thetaR`, and `uTheta` are not this constant-angle parameterization. See [v2512 contact-angle source](https://api.openfoam.com/2512/constantAlphaContactAngleFvPatchScalarField_8C_source.html) and [base-class limit handling](https://api.openfoam.com/2512/alphaContactAngleTwoPhaseFvPatchScalarField_8C_source.html). Keep the flat-wall and declared geometry sensitivities; do not select a wall by Figure 13 agreement. No characterization or Figure 13 comparison is permitted under this static-preparation amendment. Verify dimensioned patch bounds, opening angle, nozzle center, wall gap and wall contact in the mesh record. |
| Inlet and wall fields, including pressure and `nut` | At the circular nozzle prescribe `U=(0,-10,0)`, `alpha.water=1`, fixed `k=k_j=0.015` and `epsilon=epsilon_j=0.01078`; use `p_rgh=fixedFluxPressure`. At the gas inlet prescribe `U=(70,0,0)`, `alpha.water=0`, fixed `k=k_g` and `epsilon=epsilon_g`; use `p_rgh=fixedFluxPressure`. On the curved solid wall use `U=noSlip`, the provisional `alpha.water=constantAlphaContactAngle` entries above, `nut=nutkWallFunction`, `k=kqRWallFunction`, `epsilon=epsilonWallFunction`, and `p_rgh=fixedFluxPressure`. Initialize internal `nut=0`; the turbulence model updates it. **Named pre-characterization decision D-NUT-BC (owner: E1 case-preparation owner):** set `nut` patch types and seed/reverse-flow values for the nozzle, gas inlet, and every open patch. Candidate options to review are `calculated` or `zeroGradient` on velocity inlets, and `zeroGradient` or `inletOutlet` on open patches with an explicit reverse-flow `inletValue`; these are not paper values or approved defaults. | The paper does not specify dictionary-level pressure behavior, contact-angle treatment, or `nut` boundary conditions. The `limit` option and every non-wall `nut` patch entry must be accepted or replaced and statically checked before characterization. Record every patch/field entry, including required seed `value` entries; check field types, dimensions, patch names, and reverse-flow values. On each prescribed inlet, fixed values define the state if local flow reverses. All mappings remain provisional assumptions. |
| Atmospheric open boundaries and reverse flow | On every non-inlet, non-wall open patch use `prghPressure` with static pressure `p_gauge=0 Pa` (equivalent to `p_abs=101325 Pa` only as this incompressible reference convention), density field `rho`, `U=pressureInletOutletVelocity` with `tangentialVelocity=(70,0,0) m/s`, `alpha.water=inletOutlet` with reverse-flow `inletValue=0`, and `k`/`epsilon=inletOutlet` with reverse values `k_g`/`epsilon_g`. | OpenFOAM defines `p_rgh = p_static - rho*(g_vec dot (x-x_ref))`; use `g_vec=(0,-9.81,0)` and `x_ref=(0,0,0)` at nozzle center, with mixture `rho=alpha.water*rho_water+(1-alpha.water)*rho_air`. Thus constant atmospheric static pressure gives elevation-varying `p_rgh` (air-only change is 115.758 Pa over 10 m), not uniform zero `p_rgh`. Verify facewise reconstructed static pressure on every open patch. `pressureInletOutletVelocity` supplies the flux-based normal reverse velocity and +x tangential value; `alpha.water`, `k`, and `epsilon` reverse to zero liquid and the assumed air fields. Log reverse-flow area/time and patchwise `phi`/`alphaPhi_`. Cite [prghPressure](https://doc.openfoam.com/2306/tools/processing/boundary-conditions/rtm/derived/general/prghPressure/), [v2512 pressureInletOutletVelocity](https://api.openfoam.com/2512/pressureInletOutletVelocityFvPatchVectorField_8H_source.html), and [inletOutlet](https://doc.openfoam.com/2312/tools/processing/boundary-conditions/rtm/derived/inletOutlet/inletOutlet/). |
| Mesh family and acceptance | Primary candidate is locally refined `snappyHexMesh` hex-dominant mesh, not the source's unstructured polyhedra. Candidate levels: 70 mm resource/coarse, then 30 and 16 mm comparison; full domain. Candidate five prism layers, expansion 1.1; record first-layer height, actual layer count/coverage and ratio. Nozzle spans nominally 5.7/13.3/25 cells at 70/30/16 mm. | Source mesh: PDF pp. 5, 8 / article pp. 4, 7, Tables 2–3 and §3.3/Figs. 4–6. No cell count or refinement map is published. Static acceptance evidence includes mesh/image hashes, family, total cells, domain and every patch extent/area/normal, nozzle area/equivalent diameter/face count, refinement-box coordinates, ROI `h_eq=(cell volume)^(1/3)` percentiles, layer coverage/growth, first-cell height, and complete `checkMesh -allTopology -allGeometry` output (zero topology/geometry errors and no non-positive volumes). Candidate static ROI target: at least 95% of cells at or below each ROI's declared spacing. The primary's proposed `30<=y+<=300` on 90% wall area is flow-dependent: record actual area-weighted y+ during the reviewed characterization, then use it to freeze/refine the comparison mesh prospectively. Do not require measured y+ before preparation or the characterization run. Review static cell-family/layer/spacing/quality deviations before characterization and flow-dependent y+ deviations after it; none of these candidates is an accepted criterion here. Do not infer the source mesh from nominal spacing. |
| Spatial/time discretization, coupling, and linear solvers | `interIsoFoam` geometric isoAdvector for `alpha.water` (`reconstructionScheme isoAlpha`, `cAlpha=1`, one alpha subcycle); explicitly set provisional isoAdvector controls `clip true; snapTol 0;` (snapping disabled), plus `ddt Euler`; gradients `Gauss linear`; viscous divergence `Gauss linear`; Laplacian `Gauss linear corrected`; interpolation `linear`; `snGrad corrected`. Provisional convection with **density `variable`**: `div(rhoPhi,U) Gauss linearUpwind grad(U)`, `div(rhoPhi,k) Gauss linearUpwind grad(k)`, and `div(rhoPhi,epsilon) Gauss linearUpwind grad(epsilon)`. The density mode and aligned `rhoPhi` schemes are project-provisional settings, not source values; verify exact v2512 dictionary lookups and equations before freezing. If `density uniform` is selected instead, use the applicable `phi` convection keys for the turbulence equations and record that prospective change. Provisional PIMPLE: 1 outer corrector, 3 pressure correctors, 0 non-orthogonal correctors, `momentumPredictor yes`. Provisional `fvSolution`: `p_rgh` uses GAMG with nominated `smoother DICGaussSeidel` (`tolerance 1e-8`, `relTol 0.01`, `maxIter 100`); `U`, `k`, and `epsilon` use smoothSolver/GaussSeidel (`tolerance 1e-8`, `relTol 0.1`, `maxIter 100`, `nSweeps 2`); corresponding `Final` solvers use `tolerance 1e-8`, `relTol 0`, `maxIter 100`. Do not set PIMPLE residualControl; record every equation residual/iteration count and stop if an accepted convergence rule is missed. | The paper reports SIMPLE, second-order convection for momentum and turbulence, and first-order implicit integration (PDF p. 6 / article p. 5, §3.1). This proposed transient PIMPLE setup is a declared coupling-method deviation from paper SIMPLE. isoAdvector is not HRIC; `linearUpwind` is a declared approximation. Density `variable`, the `rhoPhi` turbulence schemes, `DICGaussSeidel`, solver tolerances, and iteration controls are not paper-recovered. The v2512 realizableKE source documents the density-weighted `rhoPhi` path; see [official source](https://api.openfoam.com/2512/realizableKE_8C_source.html). Pin and hash `fvSchemes`, `fvSolution`, `turbulenceProperties`, isoAdvector controls, and all field dictionaries; record final residuals and iteration counts. These choices remain provisional and require pre-characterization review; do not imply method equivalence from nominal grid or `dt`. |
| Time step and Courant stops | Candidate fixed `deltaT=0.001 s` and `0.0005 s` are comparison inputs, not accepted defaults; do not adapt `dt` silently. **Unapproved proposed stop caps:** `Co_global<=5.7` and `Co_interface<=1.0`, computed every step using the pinned solver's flux-based definitions. | `1 ms` and reported STAR-CCM+ CFL range 3.2–5.7 are source values (PDF p. 6 / article p. 5). v2512 `interIsoFoam` evaluates `Co_global=0.5*dt*max_i(sum_f(abs(phi_f))/V_i)` and `Co_interface=0.5*dt*max_i(nearInterface_i*sum_f(abs(phi_f))/V_i)` in its `porousCourantNo.H` and `porousAlphaCourantNo.H` paths (porosity disabled for this proposed case); see the [official v2512 source archive](https://dl.openfoam.com/source/v2512/) and [solver-source/API listing](https://api.openfoam.com/2512/files.html). For an aligned cubic cell with 70 m/s streamwise velocity, these definitions give scale estimates `Co≈U*dt/h`: at local `h=70, 30, 16 mm`, respectively, `Co≈1.00, 2.33, 4.38` for `dt=1 ms` and half those values at `0.5 ms`. These estimates are not a mesh or field evaluation: actual `phi`, cell-face geometry, local velocity and interface mask determine maxima. The `5.7` cap is only anchored to the reported STAR-CCM+ range; no cross-solver equivalence or accuracy follows. `Co_interface=1.0` is an unapproved conservative project guard, absent from the paper. Measure both from every accepted mesh and candidate `dt` before freezing the timestep pair; if a cap requires smaller `dt`, prospectively revise the pair and cost budget. A cap exceedance is a hard stop for that attempt; staying below either cap does not establish accuracy, which is checked separately by mesh/time refinement and observable drift. |
| Figure 13 window, aggregation, and retention | Primary candidate window `[4.50,5.00] s`, endpoints inclusive, samples every `0.01 s` (51 sampled solver states). At every time and fixed station, compute the observable first, then take the unweighted arithmetic mean of the 51 values; also retain the temporal minimum/maximum. This is a mean of observables, not a contour of mean `alpha`. Keep all 51 sampled `alpha.water`, `U`, `p_rgh`, `k`, `epsilon`, `nut` states and extracted values; `purgeWrite=0`. | Figure 13 has no sampling time. The source's ~5 s stabilization and separate 4.5 s images only motivate this inferred convention. The timing set consists only of the 51 sampled states; no bound is claimed for unsampled times between them. Candidate stationarity bound: for each observable, `max_i(max_t F_i(t)-min_t F_i(t))/R_F <= 0.05` over those 51 samples. A cadence-refinement study needs a separate prospective rule; it is not included here. If the sampled criterion is not met, no pass/fail comparison; do not move the window after inspecting results. |

The existing user authorization permits provisional case/dictionary/geometry
and mesh preparation plus static analytical checks under the primary's bounded
resource schedule. No additional scientific-run approval is required for those
preparatory activities. They produce immutable inputs and evidence only; static
checks cannot supply y+, evolving Courant numbers, solver closure, or runtime.
Before any solver characterization, independently review its preregistered
purpose, candidate inputs, resources, step cap, outputs, and stop contract.
Characterization evidence then informs the prospective comparison mesh and
timestep pair. A separate E1 execution decision still requires review of the
complete hashed inputs, mesh deviations, scoring/validity rules, E0 status,
resource profile, and stops. This draft itself authorizes no solver execution.

### Observables and source/read uncertainty

Use the nozzle-exit center `(x0,y0,z0)` as coordinate origin and `d_j=0.4 m`.
For each instantaneous `chi=0.1` field compute
`X=(x-x0)/d_j`, `Y=(y0-y_min)/d_j` (positive downward although physical `+y`
is upward), and `Z=(z_max-z_min)/d_j` (nonnegative full span). `y_min` is the
lowest vertical coordinate among all threshold crossings at that station;
`z_min,z_max` are the outermost spanwise crossings, including detached
thresholded structures. These extraction operations are inferred, not stated
by the author; a reviewer may require descriptive-only status if they are not
accepted. Report the `chi=0.9` core breakup separately and contextually.

The chart-origin `(0,0)` row is a **digitizer/calibration anchor**, not an
independent physical observation: the raster method inserts it where plotted
symbols overlap. Retain it in source files and figures as contextual evidence,
but exclude it from scored rows. Freeze all remaining rows from the primary
vector-path CSV: penetration `X={0.25,0.50,...,4.50,4.75,4.875}` (20 points;
0.25 increments through 4.75 plus the 4.875 terminal point), width
`X={0.25,0.50,...,2.50}` (10 points at 0.25 increments). These are separate grids, and the raster
CSV is a cross-check at the same locations, not an independent sampling plan.
For each scored station, freeze the sampler before any solver run: cut the
unstructured mesh at the exact plane `x=x0+X_i*d_j`, evaluate `alpha.water` at
plane vertices with OpenFOAM `interpolationCellPoint`, and linearly locate every
`alpha.water=0.1` edge crossing on the cut polygons. Include every connected
component and every detached thresholded structure; define `y_min` as the
lowest crossing and `z_min/z_max` as the outermost crossings. Do not extrapolate
outside the cut support; a station with no crossing is missing and prevents
pass/fail. Pin the sampler version/hash and test known synthetic contours,
coordinate signs, missing stations, and aggregate-score arithmetic before it is
used. This proposed interpolation/crossing operation is not author-recovered.
Freeze equal point weights and normalization ranges from the selected primary
rows: `R_Y=6.725-1.500=5.225`, `R_Z=4.328-1.071=3.257`. A missing computed
observable at any frozen station/time or a domain that does not cover every
frozen station makes pass/fail unavailable; interpolate only within the
computed support and never extrapolate.

The digitization fields `sigma_value`/`sigma_x` are conservative read bounds,
not standard deviations. Across every scored segment, use its piecewise-linear
slope; at an interior knot use the larger absolute slope of the adjacent
segments, and at either scored endpoint use the one-sided adjoining slope.
Then `delta_i=sigma_value_i+abs(slope_i)*sigma_x_i`. Keep the normalization
ranges fixed above. Form lower/upper residuals as
`max(0,abs(F_sim-F_ref)-delta_i)` and `abs(F_sim-F_ref)+delta_i`, then compute
lower/upper NRMSE with the same frozen stations and weights. The timing-
uncertainty set is only the 51 sampled instantaneous profiles: compare each
profile across all scored stations at the same sampled time, so a time shift is
common to the whole curve. The samples do not bound intervening times or
contour changes. Report per-station sampled minimum/maximum as a range
diagnostic, but do not combine independently selected station extrema into an
artificial profile. Do not assign the finite temporal set a probability
distribution or RSS-combine it with source-read bounds. A denser cadence test
would be a separate prospective check. Preserve the raster-primary difference
check using the same recorded bounds and stop for source review if it fails.

For breakup, report `x_BU/d_j` and `y_BU/d_j` separately. The Fig. 16 values
near `q=17.3` (about `8.91` and `10.04`, each with about `0.25` ordinate read
bound) are contextual only. Do not assign them to Case 1 or use the project's
draft 15% landmark tolerance as a pass/fail test unless Case-1 applicability
and averaging are confirmed.

### Proposed decision metrics and candidate tolerances

These are concrete candidates for reviewer approval, not project defaults:

| Gate | Proposed metric / candidate threshold | Decision rule and limitation |
| --- | --- | --- |
| Figure 13 penetration | `NRMSE_Y = sqrt(mean_i((Y_sim(X_i)-Y_ref(X_i))^2))/R_Y`, one aggregate score over all 20 primary stations `X=0.25,0.50,...,4.50,4.75,4.875` (0.25 increments through 4.75 plus terminal 4.875), equal weights and fixed `R_Y=5.225`. Candidate aggregate bound `NRMSE_Y <= 0.10`. | For the mean-of-observables curve and each of the 51 sampled profiles, compute one lower/upper aggregate NRMSE over the entire frozen station set with the source-read bounds above. Pass this observable only if the maximum upper bound across those 52 profiles is `<=0.10`. This is not a per-station error limit. If the minimum lower bound across all 52 profiles is `>0.10`, it is curve disagreement; otherwise source-bound overlap is inconclusive. No station may be dropped. |
| Figure 13 full-span expansion | Same aggregate NRMSE formula over the frozen 10 primary stations `0.25..2.50` in 0.25 steps, equal weights, fixed `R_Z=3.257`, and candidate bound `NRMSE_Z <= 0.10`. | Apply the same 52-profile upper/lower decision separately for `Z`. No joint score and no pointwise limit is implied. The `(0,0)` chart anchor is excluded from both denominators and scored rows. |
| Mesh sensitivity | Compare 30 and 16 mm on the fixed station sets using the same range-normalized aggregate NRMSE; provisional drift candidate `<=5%` for each observable and each of the mean plus 51 sampled profiles. | The 5% candidate is a project numerical-resolution budget, not a paper tolerance; all point coverage and ROI-spacing requirements still apply. Any missing station, ROI-spacing acceptance failure, or missed limit leaves numerical accuracy unresolved; do not relax after viewing Figure 13 agreement. |
| Time-step sensitivity | Candidate pair at 16 mm: fixed `dt=1.0 ms` and `dt=0.5 ms`, same end time, 51 retained sampled states and frozen stations; provisional range-normalized aggregate drift candidate `<=2%` for each observable and each of the mean plus 51 profiles. Both `dt` values remain provisional and are usable only if accepted operational Courant caps permit them. | The 2% candidate is a project numerical-resolution budget, not a paper tolerance. If an accepted cap requires a smaller `dt`, prospectively freeze a revised timestep pair and cost budget before comparison. If the cap or drift limit fails, retain the attempt and report numerical accuracy unresolved; each changed `dt` needs its own immutable input/run record. |
| Courant guardrails | **Unapproved proposed hard-stop caps:** `Co_global<=5.7` and `Co_interface<=1.0` each step, using pinned v2512 flux-based definitions and measured `phi`/near-interface mask. | The STAR-CCM+ global-CFL report (3.2–5.7) does not establish an OpenFOAM cap or accuracy criterion; the paper gives no interface-Courant limit. Co caps only stop runs and cannot satisfy mesh/time accuracy checks. Any accepted cap exceedance invalidates that attempt. |
| Sampled temporal stationarity (descriptive decision only) | **Unapproved proposed decision threshold:** at each scored station, `(max_t(F_i)-min_t(F_i))/R_F <=5%` over only the 51 sampled outputs, for both observables. | Evaluate after hard validity and mesh/time accuracy. If the accepted sampled-stationarity rule is unmet or unresolved, report the window as descriptive/no-pass-fail; it does not invalidate the underlying attempt and is not part of the hard-validity conjunction. The source defines no stationarity limit. |
| Source trace cross-check | Each raster-primary point difference within the sum of the primary ordinate bound, slope-propagated `X` bound, and raster heuristic bound. | This is an extraction integrity check, not CFD accuracy or a confidence interval. Resolve any violation before using a threshold. |
| Inlet and domain mass | Integrated source mass is compared with `M_source(t)=rho_water*A_j*v_j*t` only for `t>0`; candidate relative error `<=0.1%`. Checkpoint water inventory plus cumulative open-boundary liquid outflow closes against cumulative source within candidate `0.5%` of released mass, also only for `t>0`. At `t=0`, return structured status `not_applicable_zero_reference` for every source-normalized ratio, verify exactly zero prescribed source integral and zero initialized water inventory in absolute units, and never compute `0/0`. Record escaped/open-boundary flux separately. | Both limits are unapproved project-budget proposals. No parcel-transfer budget applies to E1. A failed closure stops interpretation until corrected; do not delete the failed run. |
| Active inlet/phase momentum flux | Use inward convective momentum-flux rate `M_in,q,p = -integral_p(rho_q*alpha_q*U*(U dot n_out)) dA` (N), with `alpha_water=alpha.water`, `alpha_air=1-alpha.water`, and constant phase density. Enumerate exactly two active references: (1) `water@nozzle`, `M_ref=(0,-rho_water*A_j*10^2,0)=(0,-12536.2,0) N`; (2) `air@gas_inlet`, `M_ref=(rho_air*A_g*70^2,0,0) N`, where `A_g` is the accepted crossflow patch area. Candidate active-pair vector error is `norm(M_meas-M_ref)/norm(M_ref)<=0.5%`; candidate zero components are water x/z and gas y/z, each absolute component `<=0.5%*norm(M_ref)` for its own active pair. | These are the only pairs with nonzero phase-specific references. The outward-normal sign makes prescribed incoming flux negative in `U dot n_out`; the leading minus sign therefore yields the inward vector signs shown. Record active references, integrated vectors, areas/normals, phase weighting, and units every time step. The 0.5% values are unapproved integrity candidates, not source tolerances. |
| Absent-phase inlet leakage | For absent phase `q_abs` on each inlet patch `p`, report `L_q_abs,p=norm(M_in,q_abs,p)/norm(M_ref,q_present,p)` using only the designated nonzero present-phase reference on the **same patch**: air leakage at the water nozzle normalized by `norm(M_ref,water,nozzle)`; water leakage at the gas inlet normalized by `norm(M_ref,air,gas_inlet)`. All three absent-phase components are expected zero and each candidate absolute component bound is `0.5%` of that same-patch present-phase norm; candidate leakage-ratio bound is also `<=0.5%`. | Emit structured status for each pair: `status=absent_reference`, absent `phase`, `patch`, `expected_vector_N=(0,0,0)`, `reference_status=present_phase_same_patch`, reference `phase` and `patch`, positive `reference_norm_N`, measured `leakage_vector_N`, component residuals, and ratio. Never form `M_ref` or relative error for the absent phase. If the designated present-phase norm is zero/non-finite, report `invalid_present_reference`, stop the attempt, and do not divide. These leakage limits are unapproved proposals. |
| Raw phase boundedness and isoAdvector corrections | Explicitly pin provisional isoAdvector controls `clip true; snapTol 0;` in the hashed `fvSolution` (snapping disabled); these project choices reflect pinned v2512 defaults, not paper settings. At every step preserve `alpha_preclip_presnap` immediately after conservative isoAdvector flux bounding and before clipping/snapping, `alpha_postclip_presnap` immediately after clipping and before snapping, and `alpha_solver_final` after the remaining solver corrections. Record extrema and out-of-range cell count/volume for each stage; record clipping correction `DeltaV_clip=sum_i(V_i*(alpha_postclip_presnap-alpha_preclip_presnap))` and any later correction `DeltaV_later=sum_i(V_i*(alpha_solver_final-alpha_postclip_presnap))`, in m^3. Retain `alphaPhi_` separately as the conservative transported phase flux. Candidate bound: `-1e-6 <= alpha.water <= 1+1e-6` at every named stage. | The bound and control values are unapproved and have no paper basis. Pinned v2512 source reports an intermediate alpha after flux bounding and corrected alpha later; see [isoAdvection source](https://api.openfoam.com/2512/isoAdvectionTemplates_8C_source.html) and [interIsoFoam alpha equation](https://api.openfoam.com/2512/alphaEqn_8H_source.html). Capture preclip, postclip, and solver-final values without external clipping/renormalization; preserve preclip extrema and each correction amount. Any violation of the accepted bound at any named stage invalidates the attempt and bars source scoring; retain all fields and diagnostics, including built-in corrections. If future instrumentation cannot expose these stages, characterization remains blocked until a reviewed alternative monitor is specified. |
| Breakup location | Report both normalized coordinates and uncertainty, plus distance from the generic Fig. 16 `q=17.3` marker. | Context only until the case-specific source ambiguity is resolved. The project draft 15% landmark value is not adopted. |

The source/read bounds account only for reading the plotted image. The 51-state
sampled envelope is a separate operational bound, not source uncertainty or a
statistical confidence interval; it says nothing about unsampled times and
neither source nor temporal bounds cover algorithm-definition or model-form
error. The gate uses the mean-of-observables result and all 51 sampled profiles;
no unsampled Figure 13 time is claimed to be covered. If the source does not
support the provisional window/full-span semantics, keep a descriptive overlay
rather than a pass/fail label.

The candidate decision has separate validity, accuracy and operational layers.
For a valid comparison, E0 must be complete; the reviewer must accept the
provisional input/deviation and scoring rules; prepared mesh/dictionaries must
meet accepted static checks or have accepted deviations; every scored station
and all 51 sampled outputs/provenance must be intact; raw alpha must meet its
accepted bound; and source mass, inventory/outflow closure, both active
momentum pairs, both absent-phase leakage records, and boundary influence must
meet their separately frozen definitions. Sampled stationarity is evaluated
later as a descriptive/no-pass-fail decision check, not as hard validity.
Source-normalized checks at `t=0` are `not_applicable_zero_reference`, accompanied by
absolute zero source and inventory checks. Numerical-accuracy candidates are
the accepted 30/16 mm mesh-drift limit and time-step-drift limit for a reviewer-
accepted pair. For each Figure 13 observable, the curve score is one aggregate
NRMSE over the full frozen station set; compute its source-read lower/upper
bounds for the mean and each of the 51 sampled profiles. No pointwise 10%
criterion is implied. Unapproved Courant caps are operational stop guards only:
if accepted, exceeding either invalidates that attempt, while staying below
them is not accuracy evidence. Apply decision precedence: (1) a hard/validity
failure invalidates the attempt; (2) unresolved mesh/time accuracy or a failed
sampled-stationarity decision leaves the comparison descriptive/no-pass-fail;
(3) source-bound overlap is inconclusive; (4) pass only if every upper-bound aggregate NRMSE for
both observables across the mean plus 51 profiles is `<=10%`, or curve
disagreement only if every corresponding lower-bound aggregate NRMSE is `>10%`.
Every other combination, including a source-bound profile that overlaps 10% or sampled profiles split across the 10% boundary, is inconclusive.

Hard failures are separate from numerical comparison tolerances: solver/non-
finite failure; failed mesh topology/geometry; unreviewed inputs/deviations; a
missing scored station/output; raw alpha outside the accepted bound; a reached
outlet before the last scored station; failed accepted conservation or active/
absent-phase inlet checks; an accepted Courant cap exceeded; or breached frozen
CPU/RAM/disk/time limits stops or invalidates the attempt and bars pass/fail
classification. Retain the attempt and classify it as failed, inconclusive, or
descriptive-only without changing limits after results. Passing resource or
stability guards does not imply accuracy. Even an accepted pass is a conditional
OpenFOAM comparison, not exact STAR-CCM+ recovery or field validation.

### Stop and escalation rules

- Provisional input, geometry, case-dictionary, mesh preparation, and static
  checks may proceed under the existing user authorization and primary's
  bounded resource schedule. Keep each artifact immutable and record source,
  assumptions, deviations, hashes, and static results. This permission does not
  cover any solver run.
- Before the bounded solver-characterization run, freeze and independently
  review its purpose, initial/patch fields, primary curved-wall model,
  provisional mesh and timestep, step cap, output/diagnostic list, CPU/RAM/disk/
  wall-time ceilings, and stop conditions. The pilot measures wall y+, global
  and interface Co, closure/alpha behavior, and runtime/cost; it is not E1 and
  need not produce stable flow or Figure 13 observables. Use those measurements
  to freeze the later comparison mesh and timestep pair prospectively. A
  separate E1 execution approval is required after that evidence and all other
  E1 inputs/limits are reviewed. No solver execution is authorized here.
- At static preflight, verify the full 3-D domain without symmetry, the circular
  0.4 m water inlet, +70 m/s gas crossflow, gravity, surface tension, curved
  no-slip primary wall, all open boundaries and every pressure/backflow/turbulence
  field. Reconstruct static pressure facewise from the provisional
  `p_rgh`/mixture-density rule. If a required field, boundary, force, or patch
  is missing, correct the preparation record before proposing any solver run;
  do not substitute the FluTAS box, four-slot case, parcels, or a reduced domain.
- On every solver run, including characterization, coarse profile, mesh
  refinement, and timestep refinement, monitor accepted global/interface Co,
  resource/time limits, solver residual/failure, raw alpha minima/maxima,
  source/inventory closure, active inlet momentum, absent-phase leakage, and
  boundary influence. Any accepted hard stop invalidates that attempt; preserve
  its inputs and diagnostics. A cloud reaching an open outlet before the last
  scored `X` also bars the controlled comparison.
- At `t=0`, do not calculate a relative source or mass-closure ratio because its
  reference is zero. Record `not_applicable_zero_reference`; verify absolute
  zero source integral and zero initialized water mass. Evaluate source-relative
  checks only at `t>0` with a positive reference.
- If mesh/time drift is unresolved, report no source-comparison pass/fail.
  Evaluate the 51-sample stationarity criterion in the descriptive decision
  stage; if it fails, the target window is descriptive/no-pass-fail without
  invalidating the attempt. A
  finer nearfield grid, smaller `dt`, or cadence study requires a prospective
  amendment and new resource estimate; do not change limits after seeing Figure
  13. The `[4.50,5.00] s` observations are 51 samples only. Do not shift or
  shorten the window after inspecting computed curves.

## Inputs and preregistration items

Before a controlled run, record the following in a machine-readable experiment
record and freeze it under review:

1. **Case/source:** DOI `10.1016/j.ijmultiphaseflow.2023.104419`; exact source
   PDF identity/hash; Case 1 Tables 2–3; Fig. 13 and Fig. 16 extraction
   versions; units, coordinate frame, `chi` surfaces, sampling time/window,
   and author/source clarification if obtained. Complete the E0 analytical
   gates before a controlled E1 run.
2. **Single-nozzle inputs/deviations:** `d_j=0.4 m`, `U_j=(0,-10,0) m/s`,
   `U_g=(70,0,0) m/s`, origin at the nozzle exit center, physical `+y` upward,
   reported fluids and `I_j=0.01`; full 3-D trapezoid and prospectively fixed
   provisional curved wall; gravity and surface tension. Record internal
   initial `U`, `alpha.water`, gauge pressure/`p_rgh`, `k`, `epsilon`, `nut`,
   and initial water inventory; all nozzle, gas-inlet, curved-wall, and open-
   boundary conditions for `U`, alpha, pressure, and turbulence; and reverse-
   flow values. Freeze the primary `realizableKE` plus high-Re wall functions,
   derived liquid `k/epsilon`, assumed air intensity/length scale, contact
   angle, and sensitivity set. Pin `fvSchemes`/`fvSolution`, explicitly record
   paper SIMPLE versus proposed PIMPLE, k/epsilon convection schemes, linear
   solvers/tolerances, and all deviations from STAR-CCM+. Do not label a
   provisional value as reported.
3. **Preparation, characterization, and resolution/time:** retain static
   geometry/field checks and their hashes; domain and patch extents, mesh family
   and deviations; cell counts and local `h_eq` distributions; prism
   count/growth/coverage and `checkMesh`; characterization y+ histogram, actual
   global/interface Co histories, closure, and measured costs. Before that
   pilot, preregister and independently review purpose, provisional mesh/dt and
   field/model inputs, fixed step cap, diagnostics, CPU/RAM/disk/wall-time
   ceilings, and stops. Use its evidence to freeze the later comparison mesh
   and dt pair. For E1 record exact final mesh/dictionary hashes, timestep,
   accepted Co stops, output cadence, and all 51 sampled final-window states.
   The source `dt=1 ms` and roughly 5 s are not proof that OpenFOAM has the same
   temporal error.
4. **Comparisons:** exclude the contextual `(0,0)` anchor; freeze the 20
   penetration rows `0.25,0.50,...,4.50,4.75,4.875` (20 points), 10 width
   rows `0.25..2.50` at 0.25 increments, `R_Y=5.225`,
   `R_Z=3.257`, equal point weights, the pinned plane interpolation and
   threshold-crossing sampler, piecewise-linear x-bound treatment, no
   extrapolation, and a timing set limited to the 51 sampled profiles. Define
   one aggregate NRMSE per observable/profile over all stations, with the 10%
   candidate curve bound; define sampled per-station temporal range separately
   with the 5% candidate stationarity bound in the descriptive decision stage.
   Review the unapproved mass,
   active/absent phase-momentum, alpha-bound, Co, mesh/time sensitivity, and
   stationarity limits;
   q-level breakup evidence remains contextual. Any declined limit means
   descriptive-only status until an alternative is prospectively approved.
5. **Provenance and conservation:** revision and dirty state, code/input hashes,
   container and solver versions, processor allocation, peak RAM/VRAM,
   wall/step time, checkpoints, time-resolved inlet liquid mass, water and air
   active-pair vector momentum-flux histories, same-patch present-phase-
   normalized absent-phase leakage/status records, raw alpha extrema and
   correction diagnostics, open-boundary phase-weighted liquid fluxes, and checkpoint
   in-domain inventory closure against integrated source minus outflow. Keep
   mass and momentum residuals, raw `chi=0.1` and `chi=0.9` observables, and
   the gate decision. Retain failed attempts and do not overwrite a run.

## Local compute plan and stop rules

The latest `make doctor` snapshot in `docs/COMPUTE.md` reports 20 effective CPU
cores, 119.0 GiB available host RAM, 262.1 GiB free disk, and a visible RTX
5090. The CPU image is `opencfd/openfoam-default:2512` (v2512, image ID
`sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`);
read-only inspection found `interIsoFoam`, `blockMesh`, `checkMesh`,
`snappyHexMesh`, `surfaceFeatureExtract`, `createPatch`, MPI, and VTK tools.
This establishes an available CPU route for two-fluid incompressible VOF with
constant phase properties, gravity and surface tension, plus standard patch
boundary conditions. A provisional static Rouaix case/dictionary package
exists, but no mesh, executable comparison sampler, or E1 run exists in the
repository. P0/P1 are smaller four-slot,
flat-wall, 50 m/s, symmetry-side, laminar characterization cases.

The remaining CPU limitations are specific rather than an unknown solver
support claim: isoAdvector differs from HRIC; v2512's two-layer option is
documented for standard `kEpsilon`, while Rouaix reports realizable
`k-epsilon` with two-layer wall treatment; the source gives no curved-wall
coordinates or contact angle, air-inlet turbulence, initial velocity field,
or liquid `epsilon` length scale. Standard patch fields can express the round
water inlet, 70 m/s air inlet and atmospheric outlets, but those E1 fields and
mesh have not been prepared. Incompressible `p_rgh` represents pressure
relative to a reference, not a compressible absolute `101325 Pa` condition.
Keep FluTAS GPU readiness separate: GPU device visibility does not make the
CPU OpenFOAM case a GPU solver or qualify the FluTAS source boundaries.

Use a serialized CPU-first budget with 2 cores reserved for responsiveness
(18 threads at most for one CFD process; no nested process/MPI/BLAS
oversubscription):

| Stage | Proposed local allocation | Advance/stop condition |
| --- | --- | --- |
| Source review | No CFD allocation. Resolve Figure 13 time/width questions from source evidence, or explicitly retain them as reconstruction assumptions. Keep the q-level breakup marker contextual. | If the reviewer declines reconstructed semantics, retain descriptive-only status; this does not block authorized preparation or a solver-characterization pilot. |
| Provisional case/mesh preparation and static checks | Already authorized under the user's provisional-preparation instruction; primary schedules within the shared CPU budget. Proposed ceiling for the full-domain coarse mesh construction/static checks: 18 CPUs, 48 GiB RAM, 1 hour wall time. Produce immutable dictionaries, geometry and mesh, `checkMesh`, patch/area/normal and inlet-flux checks, initial `p_rgh` reconstruction, field/dimension/patch consistency, and mesh ROI/y+ geometry records. No solver executable. | Static checks establish geometry and input consistency only; they cannot provide evolving y+, Co, closure, or runtime. Save all warnings/deviations and review the static evidence before a characterization contract is approved. |
| Preregistered solver characterization | Before launch, submit a separate purpose/resource/stop record for independent review. Candidate pilot: provisional curved primary wall, primary `realizableKE`/wall functions, full-domain 1–3 million-cell mesh, fixed `dt=0.5 ms`, at most 300 steps (0.15 s), 16 MPI ranks within 18 CPUs, 48 GiB RAM, 30 GiB incremental disk, and 4 hours wall time. Save per-step global/interface Co, residual/iteration and phase-ledger/alpha diagnostics; compute wall y+ distribution and sampled RAM, CPU, step-time, pressure-solve and I/O costs. It is a startup/resource characterization only, not a Figure 13 comparison. | The independent pre-run contract must freeze candidate alpha/Co stop rules, resource monitor and stops, checkpoint/output plan, and response to early instability. Every accepted stop applies during the pilot. Preserve early termination/failure; do not require stationarity or Figure 13 flow outputs before preparing the case. |
| Freeze comparison mesh and dt | Use measured pilot wall y+, global/interface Co, closure, alpha behavior, memory/disk and throughput to choose and hash the later mesh family/refinement and timestep pair prospectively. Keep the curved wall as primary; flat and turbulence alternatives are sensitivities only. | If wall treatment/ROI spacing, Co, accuracy-proxy, or resource evidence is inadequate, revise mesh/dt prospectively and, if needed, propose another bounded characterization. Do not select variants by Figure 13 fit. A separate E1 execution approval is still required after the comparison record and E0 evidence are reviewed. |
| Coarse E1 comparison | Only after separate E1 execution approval records E0 completion, accepted source/assumption decisions, frozen fields/limits, final mesh and dictionaries, reviewed characterization evidence, actual Co values at the selected dt, and resource projection, run the full Rouaix domain with source-like coarse local refinement toward the proposed 5 s regime. `5,000` steps applies only if fixed 1 ms is later accepted by characterization/review; otherwise freeze the revised timestep and step count prospectively. | Monitor stops on every run. Checkpoint and assess stability, boundary influence, mass/phase behavior, accepted Co guards, alpha bounds, and measured cost. Do not shrink the domain or stop at 400 steps while calling it a Figure 13 comparison. E2 remains closed until an accepted E1 disposition expressly authorizes advancement. |
| Resolution/time pair | Proceed sequentially to at least two nearfield meshes, including the reported 16 mm local target, with the same source case/window; compare 30 and 16 mm first, and include coarse 70/50 mm evidence for resource scaling. Test the reviewer-accepted timestep pair at the chosen comparison resolution. | Every run has the same frozen hard stops and its own immutable record. Use measured costs; if sensitivity misses its accepted limit, refine prospectively or report numerical accuracy unresolved. Do not relabel a coarser result as the 16 mm benchmark. |

The 16 mm target is a locally refined mesh, not a published cell count. Do not
estimate or promise its feasibility by pretending the entire trapezoidal
domain is uniformly meshed at 16 mm; the paper describes a coarse background
and nested refinement but does not publish total cell counts. Conversely, do
not extrapolate the measured eightfold coarse-to-fine CPU-cost statement to a
different solver without a pilot. The local plan's 1–3 million-cell pilot and
5–10 million-cell scaling gate apply; 5–10 million cells should be attempted
only after profiling. The cluster is not included in this budget and must not
be assumed available.

### Conditional future commands — preparation, characterization, and E1 execution

The provisional static E1 case, dictionaries, and two Figure 13 digitizations
exist and have exact static-artifact review; there is no mesh, executable
comparison sampler, runner, or `make` target. The commands are unexecuted
templates, use a new immutable path, and must not target P0/P1. Stage 1
case/mesh preparation and static checks are within the existing user
authorization and do not require a new scientific-run approval. Stage 2
solver characterization may be considered only after independent review of a
separate preregistration that freezes purpose, candidate fields/model, exact
mesh/dt/step cap, resource limits, diagnostics, monitor, checkpoint plan, and
stop conditions. Stage 3 requires a separate E1 execution approval after
characterization evidence and the full E1 record are reviewed. Every stage uses
the pinned image ID, not its mutable tag; all proposed resource/tolerance values
remain unapproved until those decisions are recorded.

```bash
# Stage 1: authorized provisional case/mesh construction and static checks only.
.venv/bin/python scripts/run_local.py --threads 18 --timeout 3600 -- \
  docker run --rm --cpus=18 --memory=48g \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -v "$PWD/results/runs/<new-e1-run>/case:/case" -w /case \
  sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b /bin/bash -lc \
  'source /usr/lib/openfoam/openfoam2512/etc/bashrc && blockMesh && surfaceFeatureExtract && snappyHexMesh -overwrite && checkMesh -allTopology -allGeometry'
```

Save the full `checkMesh` report, field/dictionary dimension and patch checks,
patch extents/normals/areas, prescribed inlet fluxes, static-pressure
reconstruction, mesh ROI spacing/layer/y+ geometry and all deviations. These are
preparation evidence only. No flow-dependent y+, evolving Co, closure, or cost
is required before preparing the case.

Before Stage 2, independently review a preregistration with the proposed
characterization contract: provisional primary curved-wall case and model;
1–3 million cells; fixed `deltaT=0.0005 s`, `endTime=0.15 s` (300 steps);
maximum 16 MPI ranks/18 CPUs, 48 GiB RAM, 30 GiB incremental disk and 4 wall
hours; compact output plan; per-step global/interface Co, alpha extrema,
conservation and residual/iteration logging; wall-y+ and resource/cost
measurement; monitor/checkpoint behavior; and explicit failure, Co/alpha and
resource stops. The reviewer must accept or replace each proposed stop before
launch. This pilot is a solver/resource characterization, not E1 and not a
Figure 13 comparison.

```bash
# Stage 2: bounded characterization; use only after its separate contract is reviewed.
# Its prepared controlDict must fix deltaT=0.0005 and endTime=0.15; the future
# monitored runner must enforce the reviewed Co/alpha/resource stops.
.venv/bin/python scripts/run_local.py --threads 18 --timeout 14400 -- \
  docker run --rm --cpus=18 --memory=48g \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -v "$PWD/results/runs/<new-e1-characterization>/case:/case" -w /case \
  sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b /bin/bash -lc \
  'source /usr/lib/openfoam/openfoam2512/etc/bashrc && decomposePar -force && mpirun -np 16 interIsoFoam -parallel && reconstructPar'
```

After the pilot, review measured y+, actual global/interface Co, alpha and mass
closure, solver cost and resource peaks. Freeze the comparison mesh and dt pair
prospectively from that evidence. Then obtain a separate **E1 execution approval**
that records E0 completion, accepted source/reconstruction semantics, property
disposition, final fields/limits, exact mesh/dictionary/sampler hashes, output
plan, actual Co values at selected timesteps, resource projection and stops.
Only then may the full-domain coarse comparison run proceed toward the proposed
5 s source regime (5,000 steps only if `dt=1 ms` is prospectively accepted).

```bash
# Stage 3: first coarse E1 comparison, only after the separate E1 approval.
.venv/bin/python scripts/run_local.py --threads 18 --timeout 86400 -- \
  docker run --rm --cpus=18 --memory=48g \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -v "$PWD/results/runs/<new-e1-coarse>/case:/case" -w /case \
  sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b /bin/bash -lc \
  'source /usr/lib/openfoam/openfoam2512/etc/bashrc && decomposePar -force && mpirun -np 16 interIsoFoam -parallel && reconstructPar && foamToVTK'
```

The future runner must verify and record the image ID, all exit codes and failed
attempts; enforce every accepted runtime/resource/numerical stop; checkpoint
before limits; and write compact per-step `alphaPhi_`/`phi`, mass, active and
absent-phase momentum, raw alpha extrema/corrections, global/interface Co,
boundary influence, and resource diagnostics. The controlled E1 comparison
must retain all 51 sampled final-window `alpha.water`, `U`, `p_rgh`, `k`,
`epsilon`, `nut` states (`purgeWrite=0`) and their extracted profiles. Keep each
mesh/timestep variant in a new immutable path and stop sequentially on any
failed prerequisite. Do not advance to 30/16 mm or timestep refinement until
the coarse profile's approved diagnostics and cost are reviewed. Do not execute
E2 until an independent reviewer accepts an E1 disposition that explicitly
authorizes advancement.

## Review checklist / acceptance record

Provisional case/geometry/dictionary/mesh preparation and static checks remain
authorized; this draft does not require a fresh mesh-preparation approval and
does not grant any solver execution. Keep the gates in order: static evidence,
independent review of a bounded characterization contract, review of measured
characterization evidence and prospective comparison mesh/dt freeze, then a
separate E1 execution decision. No result-dependent input or sensitivity choice
is permitted.

### Before bounded solver characterization

1. Accept, replace, or reject the full provisional input/deviation matrix:
   initial `U`, `alpha.water`, `p_rgh`, `k`, `epsilon`, and `nut`; nozzle, gas
   inlet, curved wall, and open-boundary field/pressure/backflow conditions;
   `p_rgh` gravity/reference/mixture-density mapping; primary `realizableKE`/
   high-Re wall-function pairing; liquid/air turbulence values and sensitivities;
   curved wall and contact-angle reconstruction; isoAdvector vs HRIC; and paper
   SIMPLE vs proposed PIMPLE. Explicitly review k/epsilon convection and linear
   solver choices/tolerances. Keep the curved wall primary prospectively fixed;
   flat-wall and turbulence variants are named sensitivities and cannot be
   selected by Figure 13 fit.
2. Review the static geometry/field evidence: full-domain bounds, patch areas,
   normals and orientations, water-inlet area/diameter/flux, image ID
   `sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`,
   nominal grid targets, cell-family deviations, prism/y+ geometry, exact
   `checkMesh` results, field dimensions/patch names, initial `p_rgh` to static
   pressure reconstruction, and field/dictionary hashes. Static checks do not
   stand in for flow-dependent y+, Co, closure, or cost.
3. Resolve or explicitly carry `Re_j=4.4886e6` from listed properties versus
   Table 3's `4.9e6`; do not tune viscosity. Review the atmospheric pressure
   convention `p_abs=101325 Pa` as `p_gauge=0`, `g=(0,-9.81,0)`, nozzle-exit
   `x_ref=(0,0,0)`, local mixture density, facewise `p_rgh` mapping, and all
   reverse-flow `U`, `alpha.water`, `k`, and `epsilon` entries.
4. Independently preregister and review the characterization purpose, case/model
   and provisional primary wall, exact mesh/dt and 300-step cap, output and
   diagnostic plan, monitor/checkpoint method, proposed CPU/RAM/disk/wall-time
   ceilings (18 CPUs, 16 MPI ranks, 48 GiB, 30 GiB incremental disk, 4 hours),
   and alpha/Co/solver/resource stop rules. Each numeric stop remains unapproved
   until explicitly accepted. The pilot collects y+, global/interface Co,
   closure/alpha behavior, and cost only; it is not Figure 13 evidence.

### Before E1 execution

5. Review characterization results, including actual area-weighted wall y+,
   global/interface Co histories, mass/phase closure, alpha extrema and any
   solver correction, peak memory/disk, per-step and pressure-solver costs, and
   projected resource use. Freeze the prospective comparison mesh/refinement
   and timestep pair from these measurements before any Figure 13 comparison.
   If a wall/y+ or stop criterion requires a change, retain the pilot and make a
   prospective amendment; do not choose a geometry/turbulence variant by fit.
6. Accept or replace the Figure 13 reconstruction: physical `+y` upward and
   plotted `Y=(y0-y_min)/d_j` positive downward; exclude `(0,0)` as the
   digitizer/calibration anchor; freeze 20 penetration rows (0.25 increments
   through 4.75 plus 4.875) and 10 width rows (0.25 through 2.50),
   `R_Y=5.225`, `R_Z=3.257`, interpolation/contour crossing and endpoints,
   complete station coverage, and source-read bounds. The proposed
   `[4.50,5.00] s` window consists of 51 sampled profiles only; it does not
   claim to bound unsampled times. Freeze mean-of-observables plus each sampled
   profile and separate sampled per-station temporal range; these are not
   recovered author processing.
7. Accept or replace every comparison/integrity candidate without viewing
   Figure 13 results: aggregate curve upper-bound NRMSE 10% over all scored
   stations for each mean/profile; 30/16 mm mesh drift 5%; time-pair drift 2%;
   source-mass error 0.1% only at `t>0`; checkpoint mass closure 0.5% only at `t>0`; the two
   active momentum checks (`water@nozzle` and `air@gas_inlet`) with their
   own nonzero references and candidate 0.5% vector/zero-component bounds; the
   two absent-phase leak checks normalized only by the present phase's
   same-patch reference, with structured `absent_reference` status and all
   components expected zero; raw `alpha.water` bound `[-1e-6,1+1e-6]`; and
   sampled-stationarity range 5%. At `t=0`, source-normalized metrics must be
   `not_applicable_zero_reference`, never `0/0`. Decide whether the unapproved
   operational stops `Co_global=5.7` and `Co_interface=1.0` are accepted and
   whether measured characterization requires a smaller dt pair. Keep hard
   invalidation/resource stops separate from numerical comparison tolerances
   and score one aggregate NRMSE per observable/profile, not pointwise errors.
8. Record E0 completion and issue a distinct E1 execution authorization or keep
   the gate closed. Each solver run must have exact immutable input/sampler
   hashes, stop monitor, resource budget, raw alpha/flux/Co/conservation outputs
   and failed-attempt retention. After the controlled comparison, preserve
   failed, inconclusive and descriptive-only dispositions. E2 execution remains
   closed until an independent reviewer accepts an E1 disposition explicitly
   authorizing advancement; a failed, inconclusive or descriptive-only E1
   requires a prospectively reviewed scope amendment before E2 can execute.

Until the required approvals and evidence are recorded, E1 remains **NOT READY
for pass/fail**. Even an accepted reconstructed result is a conditional
OpenFOAM numerical comparison, not a uniquely identified Figure 13 time
history, exact STAR-CCM+ reproduction, or field validation.
