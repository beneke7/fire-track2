# E1 CPU solver capability audit: Rouaix Case 1

**Status: CPU route is available for a proposed approximate numerical comparison. Provisional case/geometry/dictionary/mesh preparation and static checks are already authorized; no E1 case, mesh, or run exists. A bounded solver-characterization run is not approved until its separate purpose/resource/stop contract is independently reviewed; E1 execution remains separately gated.** This is an implementation-capability audit, not a solver run, source approval, or E1 result. The OpenFOAM choices, pressure/backflow mapping, scoring conventions and candidate limits in the linked gate remain unapproved. E2 execution requires an accepted E1 disposition that explicitly authorizes advancement.

## Scope and installed route

The candidate is the local CPU-only Docker image `opencfd/openfoam-default:2512`, image ID `sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`. Read-only image inspection confirmed `WM_PROJECT_VERSION=v2512`, `interIsoFoam`, `blockMesh`, `checkMesh`, `snappyHexMesh`, `surfaceFeatureExtract`, `createPatch`, `decomposePar`, `mpirun`, `reconstructPar`, `foamToVTK`, and `foamToEnsight`. No case was launched and no solver executable was run for this audit. The image is CPU-only for this project; host GPU visibility does not change that.

The repository has run `interIsoFoam` on the P0/P1 four-slot characterization box. Those cases show that the image and basic VOF path work, and that the conservative `alphaPhi_` phase flux can be sampled. They use a flat plate, four rectangular outlets, 50 m/s crossflow, symmetry side planes, and laminar flow. They do **not** qualify Rouaix geometry, a round nozzle, RANS turbulence, E1 boundary conditions, or breakup. Relevant local evidence is [the compute record](../docs/COMPUTE.md#current-cpu-vof-pilot), [the P1 ledger protocol](P1_SOURCE_EVENT_LEDGER.md), and [the current four-slot case description](../cases/restas_four_slot/README.md).

## Capability by source requirement

Here, **supported** means the installed solver exposes a suitable field/model capability; it does not mean an E1 case has exercised it. **Approximated** means an OpenFOAM choice differs from a reported source method or requires a reconstruction assumption. **Missing** means the necessary source value, E1 case, or project tooling is absent.

| Rouaix requirement | Classification for installed `interIsoFoam` path | Evidence, limit, and measurable check |
| --- | --- | --- |
| 3-D incompressible water-air VOF with gravity and surface tension | **Supported in principle and used in P0/P1.** `interIsoFoam` solves two incompressible, isothermal immiscible fluids and uses isoAdvector. Its constant phase `rho`, `nu`, and `sigma` inputs and uniform `g` field fit the reported constant-property setup. | OpenFOAM's [v2512 solver inventory](https://www.openfoam.com/documentation/user-guide/a-reference/a.1-standard-solvers) describes this solver and its isoAdvector approach; its [dam-break tutorial](https://www.openfoam.com/documentation/tutorial-guide/4-multiphase-flow/4.1-breaking-of-a-dam) documents phase `nu`/`rho`, `sigma`, and `g`. Before E1, record loaded values and derived dimensionless groups. The linked gate provisionally pins `clip true; snapTol 0;` and requires per-step `alpha_preclip_presnap`, `alpha_postclip_presnap`, and `alpha_solver_final` extrema, out-of-range counts/volume, and separate correction amounts, alongside water inventory and per-patch conservative `alphaPhi_`. The bound and controls remain unapproved; any accepted-bound violation at any named stage invalidates that attempt and bars source scoring. P1's independent review confirms `alphaPhi_` meaning in this installed version. |
| Published interface-capturing scheme | **Approximated.** Rouaix used STAR-CCM+ HRIC. `interIsoFoam` uses isoAdvector's geometrical interface advection; it is not an HRIC switch and should not be described as HRIC. | The interIsoFoam difference is documented by the official [solver description](https://www.openfoam.com/documentation/user-guide/a-reference/a.1-standard-solvers). Preserve this as a solver-form difference. Measure mesh and time-step drift in the Figure 13 observables; compare `chi=0.1` cloud and `chi=0.9` core using the same post-processing definition at each resolution. |
| Round nozzle and steady uniform liquid source | **Supported as a boundary-condition concept; geometry is missing from the repository.** A dedicated circular inlet patch can prescribe uniform `U=(0,-10,0)` and `alpha.water=1`, with a water-free crossflow inlet. The inlet patch must have the reported 0.4 m diameter and the actual mesh must resolve its circumference and near field in all three directions. | The E1 source describes one 0.4 m nozzle, not the separate four-port B747 setup ([source record, Table 3 and §“Source model versus aircraft context”](E1_ROUAIX_CASE1_SOURCE.md#source-model-versus-aircraft-context)). The P0 generator has only four rectangular slots and symmetry planes ([`run_restas_pilot.py`, field setup](../scripts/run_restas_pilot.py)); it is not an E1 case. The nozzle active check is `water@nozzle`; the crossflow active check is `air@gas_inlet`. The complementary absent-phase combinations are separately status-coded leakage diagnostics normalized by the present-phase reference on that same patch. Mesh a circular patch using a curved-edge multi-block or a surface-based mesh, then measure its area, equivalent diameter, normal, cell count across diameter, and integrated phase flux. The source spacings imply about 5.7, 8.0, 13.3, and 25 cells across `d_j` for 70, 50, 30, and 16 mm local sizes. For the 0.4 m diameter and 10 m/s speed, verify inlet `Q=1.25664 m^3/s`, `m_dot≈1.254e3 kg/s`, and downward momentum-flux magnitude `≈12.54 kN`. Use the reported continuous 10 m/s source for the five-second simulation; five seconds is run duration, not a finite release or payload. |
| Uniform 70 m/s crossflow, atmospheric exits, and backflow | **Supported by standard patch fields, absent from the current E1 case.** Proposed inlet is uniform `+x`, `alpha.water=0`; outlet backflow values are proposed explicitly in the gate matrix. Do not borrow the P0 `-x`, 50 m/s setting. | Rouaix PDF p. 4 / article p. 3, Fig. 1, and PDF p. 7 / article p. 6, §3.2/Fig. 3; see [local transcription](E1_ROUAIX_CASE1_SOURCE.md). The proposed reference convention is `p_gauge=0` for atmospheric static pressure, `p_rgh=p_gauge-rho*(g_vec dot (x-x_ref))`, `g_vec=(0,-9.81,0) m/s^2`, `x_ref=(0,0,0)` at the nozzle exit, and `rho=alpha.water*rho_water+(1-alpha.water)*rho_air`. Thus an elevation-varying open patch must not be assigned flat zero `p_rgh`; for air-only fluid, the 10 m elevation change is 115.758 Pa in `p_rgh` under this gauge convention. Proposed fields are `prghPressure` with `rho`, `U=pressureInletOutletVelocity` and +x tangential reverse-flow velocity `(70,0,0) m/s`, `alpha.water=inletOutlet` with reverse `0`, and `k`/`epsilon=inletOutlet` with the assumed air values. Verify reconstructed static pressure face-by-face and log each outlet's velocity/phase/turbulence backflow and integrated `phi`/`alphaPhi_`. All mappings remain provisional until independently approved. Stop comparison if cloud reaches an open outlet before the last scored `x/d_j`. |
| Initial fields and all remaining pressure/backflow conditions | **Expressible as provisional fields; entirely absent as source data.** Candidate initial internal fields are uniform air `U=(70,0,0) m/s`, `alpha.water=0`, `k=k_g=0.735`, `epsilon=epsilon_g=3.6979`, `nut=0`, and `p_gauge=0` with `p_rgh=-rho_air*(g_vec dot (x-x_ref))`. Candidate nozzle patches are fixed `U=(0,-10,0)`, `alpha.water=1`, `k_j=0.015`, `epsilon_j=0.01078`; gas inlet is fixed `U=(70,0,0)`, `alpha.water=0`, `k=k_g`, `epsilon=epsilon_g`. Use `p_rgh=fixedFluxPressure` at both velocity inlets and the no-slip wall; wall uses `nutkWallFunction`, `kqRWallFunction`, `epsilonWallFunction`, and provisional `constantAlphaContactAngle` entries `theta0 90; limit gradient; value uniform 0;`. The constant-angle `limit gradient` is a project choice; `alpha`, `zeroGradient`, and `none` are alternatives to review, and `thetaA`, `thetaR`, `uTheta` do not belong to this parameterization. At all open pressure patches use `prghPressure` with static `p_gauge=0`, local mixture `rho`, +x tangential reverse U, reverse `alpha.water=0`, `k=k_g`, `epsilon=epsilon_g`. **Named pre-characterization decision D-NUT-BC (owner: E1 case-preparation owner):** choose `nut` patch types, seed values, and reverse-flow values on nozzle, gas inlet, and every open patch. Provisional options are `calculated` or `zeroGradient` at velocity inlets and `zeroGradient` or `inletOutlet` at openings with an explicit `inletValue`; these are assumptions, not reported facts. | The paper gives no initial velocity/liquid/pressure state, inlet or wall pressure dictionary, contact-angle limit, non-wall `nut` conditions, or reverse-flow values. The owner must freeze D-NUT-BC and the selected contact-angle `limit` before characterization. Static checks must enumerate every patch/field/type and dimensions, check initial zero liquid inventory, and reconstruct static pressure from local `p_rgh`, `rho`, gravity and reference on cells/faces. During characterization/E1, record each outlet's reverse-flow state and `phi`/`alphaPhi_`. |
| Full trapezoidal, unbounded spanwise domain and aircraft underside | **Domain proportions are reconstructible; exact curved body geometry is not.** The source gives approximately 20 m streamwise length, 10 m height, top span 7 m, bottom span 16 m, 25° opening, and a crossflow inlet 2.5 m upstream of the nozzle center. The image has `snappyHexMesh`/surface utilities, so a static 3-D body and nonuniform mesh are technically possible. | Rouaix PDF p. 7 / article p. 6, §3.2/Fig. 3 ([source record](E1_ROUAIX_CASE1_SOURCE.md)). The paper does not give coordinates or a dimensioned profile for the curved underside; a surface traced from the schematic is an **assumption**. It also does not report a wall contact-angle value. Preserve full 3-D with no symmetry plane because the crossflow breaks axisymmetry. **Freeze the curved Fig. 3 trace as the prospective primary wall before viewing results.** Flat-wall, contact-angle, and turbulence alternatives are named sensitivities only; never select the best Figure 13 fit as the primary. Preserve trace/STL, scale transform and hashes; measure boundary extents, opening angle, nozzle center, wall gap and wall contact, then log cloud distance to each open boundary. |
| Realizable `k-epsilon`, two-layer wall treatment, inlet turbulence, and coupling/numerics | **Partly supported, with a material combination and method gap.** Prospective primary is `realizableKE` with smooth no-slip and high-Re `nutkWallFunction`, `kqRWallFunction`, `epsilonWallFunction`; this approximates the source pairing. v2512 documents `twoLayerTreatment` for standard `kEpsilon`, not `realizableKE`; standard `kEpsilon` plus two-layer is a named sensitivity, never a post-Figure-13 primary selection. | Official [v2512 RAS model list](https://api.openfoam.com/2512/group__grpRASTurbulence.html), [v2512 `kEpsilon` API](https://api.openfoam.com/2512/classFoam_1_1RASModels_1_1kEpsilon.html), and [v2512 two-layer release note](https://www.openfoam.com/news/main-news/openfoam-v2512/solvers-and-physics). The paper reports `I_j=0.01` but no `k`, `epsilon`, or turbulence length scale; air-inlet turbulence is unspecified (PDF p. 5, Table 3; PDF p. 6, §3.1). Proposed conversions are `k_j=0.015`, `L_j=0.028 m`, `epsilon_j=0.01078`, and assumed air `I_g=1%`, `L_g=0.028 m`, `k_g=0.735`, `epsilon_g=3.6979` in SI units. **Provisional turbulence density mode is `density variable`**, aligned with `rhoPhi` for `U`, `k`, and `epsilon`; selecting `density uniform` would require `phi` convection for `k`/`epsilon` and a prospective amendment. This density choice is not paper-recovered; verify exact v2512 equations and dictionary lookups before freezing. The paper reports SIMPLE, second-order convection for momentum and turbulence, and first-order implicit integration (PDF p. 6 / article p. 5, §3.1); the gate's proposed transient PIMPLE (1 outer, 3 pressure correctors) plus `linearUpwind` for U/k/epsilon and Euler is an explicit deviation. Candidate `fvSolution`: `p_rgh` GAMG with `smoother DICGaussSeidel` (`tolerance 1e-8`, `relTol 0.01`, `maxIter 100`); U/k/epsilon smoothSolver/GaussSeidel (`tolerance 1e-8`, `relTol 0.1`, `maxIter 100`, `nSweeps 2`); Final solvers use `tolerance 1e-8`, `relTol 0`, `maxIter 100`, with no PIMPLE residualControl. Record residual/iteration histories and flag equations that hit maxIter without meeting tolerance. These unapproved settings are not paper-recovered. Freeze/hash exact `fvSchemes`/`fvSolution`, record residuals/iterations and first-cell y+; only `I_j` is reported, all other turbulence values are assumed/derived. |
| Constant dimensionless fluid properties | **Supported as constant inputs, with one source-table discrepancy to resolve.** OpenFOAM expects kinematic viscosity and density; converting the reported dynamic viscosities gives `nu_water=8.91139e-7 m^2/s` and `nu_air=1.57627e-5 m^2/s`. Use reported `rho_water=997.6`, `rho_air=1.18 kg/m^3`, `sigma=0.072 N/m`, and `g=(0,-9.81,0) m/s^2`. | From Table 2 and Case 1 Table 3 (Rouaix PDF p. 5 / article p. 4; [source transcription](E1_ROUAIX_CASE1_SOURCE.md)). Recalculation yields `q=17.254`, `We_g=3.212e4`, `We_j=5.542e5`, `Re_g=1.776e6`, and `Re_j=4.489e6`. These reproduce the printed `q`, Weber numbers, and gas Reynolds number to the shown precision, but not Table 3's printed `Re_j=4.9e6` (about 9% higher). Do not tune viscosity to the printed Reynolds number; request source/reviewer disposition or retain the properties and flag the discrepancy before the controlled comparison. `T=300 K` and `p=101325 Pa` are source conditions, but `interIsoFoam` is isothermal/incompressible and uses a pressure field relative to a reference; it cannot reproduce temperature-dependent properties, density/compressibility response, or absolute thermodynamic pressure. |
| Time, mesh, and Courant definitions | **Nominal settings are expressible; source discretization and local mesh are approximations.** Candidate comparison `dt` values are 1.0/0.5 ms; candidate nearfield scales are 70/50/30/16 mm. `interIsoFoam` uses isoAdvector, not source HRIC. | Rouaix PDF p. 6 / article p. 5, §3.1 and PDF p. 8 / article p. 7, §3.3/Figs. 4–6 ([source record](E1_ROUAIX_CASE1_SOURCE.md)). Pinned v2512 paths `applications/solvers/multiphase/interIsoFoam/porousCourantNo.H` and `porousAlphaCourantNo.H` define, for porosity disabled, `Co_global=0.5*dt*max_i(sum_f(abs(phi_f))/V_i)` and `Co_interface=0.5*dt*max_i(nearInterface_i*sum_f(abs(phi_f))/V_i)`. For aligned cubic cells with 70 m/s along a grid axis, `Co≈U*dt/h`: at `h=70/30/16 mm`, `dt=1 ms` gives `1.00/2.33/4.38` (half at 0.5 ms). At 16 mm, the conditional interface estimate is 4.38/2.19, so the unapproved proposed cap 1.0 would imply `dt<=0.228571 ms` if that interface-cell velocity applies. This is scale arithmetic only, not a case measurement or accuracy result. The unapproved proposed global cap 5.7 is numerically anchored only to STAR-CCM+'s printed global range 3.2–5.7, with no cross-solver equivalence; interface cap 1.0 is a project stop proposal absent from the paper. Record actual maxima during reviewed characterization and every later run; use those measurements to freeze the comparison mesh/dt pair. Staying below a stop cap does not establish accuracy. See the [official v2512 source archive](https://dl.openfoam.com/source/v2512/) and [API file listing](https://api.openfoam.com/2512/files.html). |
| Figure 13 observables and scoring | **Fields are available; sampler and E1 outputs are missing.** `alpha.water` can supply `chi=0.1` cloud and `chi=0.9` core contours; no E1 sampler exists. | Fig. 13 is PDF p. 13 / article p. 12; inputs are [source record](E1_ROUAIX_CASE1_SOURCE.md#figure-13-digitizations-cross-check-and-uncertainty), [`rouaix_e1_case1_fig13.csv`](../data/derived/rouaix_e1_case1_fig13.csv), and [`rouaix_e1_case1_fig13_raster.csv`](../data/derived/rouaix_e1_case1_fig13_raster.csv). Use physical `+y` upward, `U_j=(0,-10,0)`, `U_g=(70,0,0)`, plotted `Y=(y0-y_min)/d_j` positive downward, and exclude calibration `(0,0)`. Freeze 20 penetration rows `0.25,0.50,...,4.50,4.75,4.875`, 10 width rows `0.25..2.50`, `R_Y=5.225`, `R_Z=3.257`. Proposed sampler cuts exact x-planes, uses `interpolationCellPoint` at cut vertices and linear `alpha.water=0.1` edge crossings; includes disconnected/detached crossings, no extrapolation, missing station => no pass/fail. Freeze/hash and test synthetic contours/signs/aggregation before run. The candidate `[4.50,5.00] s` window retains 51 inclusive states each 0.01 s; it bounds only those sampled states, not the gaps. Compute one aggregate NRMSE over all stations for the mean and each sampled profile; the 10% candidate is only that curve bound. The separate 5% candidate is the per-station range across the 51 samples. Neither sampler nor time/full-span convention is author-recovered; see [gate draft](E1_ROUAIX_CASE1_GATE_DRAFT.md). |

## Smallest defensible E1 preparation and comparison convention

1. **Keep E1 independent from P0/P1 and the synthetic FluTAS box.** Prepare an
   immutable single-round-nozzle case using the full 3-D trapezoid; do not copy
   four-slot patches, symmetry boundaries, or 50 m/s settings. Existing user
   authorization permits provisional geometry, dictionary, mesh preparation,
   and static checks. These activities do not need fresh solver approval and do
   not provide flow evidence. No E1 case, mesh, sampler, or run exists yet.
2. **Use the current explicitly provisional, incomplete field/deviation matrix.** Exact hashed dictionaries and named preparation-owner choices are still required before characterization.
   Candidate initial internal fields are uniform air `U=(70,0,0) m/s`,
   `alpha.water=0`, `k=k_g=0.735 m^2/s^2`, `epsilon=epsilon_g=3.6979 m^2/s^3`,
   `nut=0`, and `p_gauge=0` represented as
   `p_rgh=-rho_air*(g_vec dot (x-x_ref))`. Candidate nozzle BCs are fixed
   `U=(0,-10,0)`, `alpha.water=1`, `k_j=0.015`, `epsilon_j=0.01078`; gas inlet
   BCs are fixed `U=(70,0,0)`, `alpha.water=0`, `k_g`, `epsilon_g`. Use
   `p_rgh=fixedFluxPressure` at velocity inlets and curved no-slip wall;
   `prghPressure` at open boundaries with static gauge pressure 0 and local
   mixture density; `pressureInletOutletVelocity` with +x tangential reverse
   flow, `alpha.water=inletOutlet` reverse value 0, and `k`/`epsilon=inletOutlet`
   reverse values `k_g`/`epsilon_g`. Wall alpha is the proposed 90°
   `constantAlphaContactAngle` (`theta0 90; limit gradient; value uniform 0;`),
   with `nutkWallFunction`, `kqRWallFunction`, `epsilonWallFunction`. Freeze the
   `constantAlphaContactAngle` `limit`
   (`gradient` is the candidate; `alpha`, `zeroGradient`, or `none` are alternatives).
   The E1 case-preparation owner must also choose and freeze all non-wall `nut`
   patch types, seed values, and reverse-flow values before characterization;
   candidate choices are `calculated`/`zeroGradient` at inlets and
   `zeroGradient`/`inletOutlet` at open patches with explicit `inletValue`.
   Static-check every patch/field/dimension and
   facewise-reconstruct static pressure. The paper does not report these initial
   or pressure/backflow conditions.
3. **Freeze the curved wall and disclose numerical mismatches before any
   comparison.** The smooth curved underside traced/scaled from Fig. 3 is the
   prospective primary; coordinates and contact angle are not paper-recovered.
   Flat wall and alternate wetting are named sensitivities only; neither may be
   selected by Figure 13 fit. `realizableKE` with high-Re wall functions is the
   prospective approximation; v2512's `twoLayerTreatment` is for standard
   `kEpsilon`, which is a separate turbulence sensitivity. Keep reported
   `I_j=0.01`; `L_j=0.028 m`, liquid `epsilon`, and all air turbulence are
   derived/assumed. Rouaix reports SIMPLE, second-order convection for U/k/eps,
   and Euler time integration. The proposed transient PIMPLE (1 outer, 3
   pressure correctors), isoAdvector vs HRIC, and `linearUpwind` U/k/epsilon
   schemes are explicit deviations. Provisionally select turbulence `density
   variable`, aligned with `rhoPhi` convection for U/k/epsilon; if `density
   uniform` is selected, use the applicable `phi` convection keys for k/epsilon
   and amend prospectively. This density treatment is not paper-recovered;
   verify the installed v2512 equations and dictionary lookups before freeze.
   Candidate linear solvers are `p_rgh` GAMG with `smoother DICGaussSeidel`
   (`tolerance=1e-8`, `relTol=0.01`, `maxIter=100`) and U/k/epsilon
   smoothSolver/GaussSeidel (`tolerance=1e-8`, `relTol=0.1`, `maxIter=100`,
   `nSweeps=2`); Final solvers use `relTol=0`, with no PIMPLE residualControl.
   These are unapproved proposals. Pin/hash `fvSchemes`, `fvSolution`, model,
   field dictionaries, and isoAdvector controls `clip true; snapTol 0;`;
   require per-step preclip, postclip, and solver-final alpha extrema/corrections.
   Record final residuals/iterations and equation-level convergence outcomes.
4. **Prepare and statically verify first; characterize before freezing the
   production mesh/dt.** Under existing authorization prepare the provisional
   full-domain case/mesh and check geometry, patch signs/areas, inlet flux,
   field dimensions/names, initial zero water, pressure-reference formula and
   mesh quality. Then, before any solver characterization, independently review
   a preregistered purpose/resource/stop contract. Proposed bounded pilot:
   curved primary, 1–3 million-cell candidate mesh, `dt=0.5 ms`, 300 steps
   (`endTime=0.15 s`), up to 16 MPI ranks/18 CPUs, 48 GiB RAM, 30 GiB incremental
   disk and 4 h wall. The monitor must log y+, global/interface Co, mass/phase
   closure, raw alpha extrema/corrections, solver costs, memory and I/O, and
   enforce the reviewed stops. No Figure 13 score or stable-flow output is
   required before preparing inputs. Review actual pilot evidence to freeze the
   comparison mesh and dt pair prospectively; this does not authorize E1.
5. **Keep pressure and property arithmetic explicit.** Use
   `p_rgh=p_gauge-rho*(g_vec dot (x-x_ref))`, `g_vec=(0,-9.81,0)`,
   `x_ref=(0,0,0)` at the nozzle exit and
   `rho=alpha.water*rho_water+(1-alpha.water)*rho_air`. A constant atmospheric
   static pressure maps to spatially varying `p_rgh`; do not set zero on an
   elevation-varying open patch. Recalculated properties give
   `Re_j=4.4886e6` while Table 3 prints `4.9e6`; preserve the discrepancy or
   obtain clarification, never tune viscosity. Check dimensionless groups from
   the pinned properties before comparison.
6. **Freeze the source observables and the finite sample limitation.** Use
   physical `+y` upward, plotted `Y=(y0-y_min)/d_j` positive downward, and
   exclude the contextual/digitizer `(0,0)` anchor. Candidate scored rows are 20
   penetration stations `0.25,0.50,...,4.50,4.75,4.875` and 10 width stations
   `0.25..2.50`, with `R_Y=5.225`, `R_Z=3.257`. Freeze a mesh cut at each exact
   station plane, `interpolationCellPoint` values at vertices, and linear
   `alpha.water=0.1` edge crossings including disconnected/detached structures;
   pin and synthetic-test the sampler, coordinate signs, missing-station and
   aggregate behavior. The proposed final window `[4.50,5.00] s` contains 51
   inclusive 0.01 s states only; it does not bound unsampled time. Compute
   mean-of-observables plus each sampled profile. For each, calculate one
   aggregate NRMSE over all stations; proposed 10% bound applies only to that
   curve score. The separate proposed 5% temporal-range rule is per scored
   station across those 51 samples. No pointwise 10% accuracy claim follows.
7. **Make phase checks defined for active and absent phases.** Use
   `M_in,q,p=-integral_p(rho_q*alpha_q*U*(U dot n_out))dA`, with
   `alpha_water=alpha.water` and `alpha_air=1-alpha.water`. Check exactly two
   active pairs: `water@nozzle`, reference `(0,-rho_w*A_j*10^2,0)=(0,-12536.2,0)
   N`; and `air@gas_inlet`, reference `(rho_air*A_g*70^2,0,0) N`. Candidate
   active vector tolerance is 0.5% of its own nonzero reference; zero components
   are water x/z and air y/z, bounded by 0.5% of that active reference norm.
   For absent air at the water nozzle and absent water at the gas inlet, never
   calculate a reference-relative error against their zero vector. Emit
   `status=absent_reference`, absent phase/patch, expected `(0,0,0)`, designated
   present reference phase and same patch, positive reference norm, leakage
   vector, component residuals and
   `norm(M_leak)/norm(M_ref,present,same_patch)`. Candidate leakage and
   component bounds are each 0.5% of that same-patch reference; a missing or
   nonfinite present-phase reference is `invalid_present_reference`, a stop,
   not division. These limits are all unapproved proposals.
8. **Separate hard invalidation from accuracy and descriptive decisions.** Candidate
   source-mass relative checks apply only at `t>0`; at `t=0` emit
   `not_applicable_zero_reference` and verify zero source and zero initialized
   water mass in absolute units. Candidate mass closure 0.5%, alpha bound
   `[-1e-6,1+1e-6]`, Co stops 5.7/1.0, mesh drift 5%, timestep drift 2%, and
   curve bound 10% remain unapproved unless separately accepted. Explicitly pin
   the provisional isoAdvector controls `clip true; snapTol 0;`. Preserve
   `alpha_preclip_presnap`, `alpha_postclip_presnap`, and `alpha_solver_final`
   extrema, out-of-range counts/volume, `DeltaV_clip`, later correction amounts,
   and `alphaPhi_` separately; do not externally clip/renormalize. A violation
   of the accepted alpha bound at any named stage invalidates the attempt and
   bars source scoring; retain all stages and corrections. Hard failures also
   include a missing station, conservation failure, accepted Co/resource stop,
   or lost boundary coverage. Sampled stationarity (candidate range 5%) is
   evaluated only in the descriptive decision stage, not as hard validity. If
   it is unresolved or unmet, or mesh/time accuracy is unresolved, report the
   window descriptive/no-pass-fail. Otherwise apply source bounds to aggregate
   curves (pass if all upper bounds are <=10%, disagreement only if all lower
   bounds are >10%, otherwise inconclusive). Keep failed attempts. E2 execution
   remains closed until an independent reviewer accepts E1 and expressly
   authorizes advancement.

## CPU and memory budget

The latest repository snapshot records 20 effective CPU cores, 119.0 GiB
available host RAM, 262.1 GiB free disk, and no detected finite cgroup quota
([`docs/COMPUTE.md`](../docs/COMPUTE.md), lines 20–28). Preserve two cores for
responsiveness: at most 18 CPUs and 16 MPI ranks for one job, with a proposed
48 GiB Docker memory ceiling. The measured P0/P1 2.0812-million-cell laminar
box used about 5.55–5.60 GiB sampled peak RAM on 16 ranks; two-second sampling
may miss peaks. P0 measured 0.443 simulated seconds per wall hour; P1 took about
2,201 s for 1,200 steps at fixed 0.1 ms. These are rough anchors only: E1 adds
RANS, a larger high-aspect-ratio domain and local refinement.

The nominal trapezoidal box volume is approximately
`20 m × 10 m × ((7+16)/2 m) = 2,300 m^3`. Uniform cubic spacing would be about
6.7 million cells at 70 mm, 18.4 million at 50 mm, 85 million at 30 mm, and
562 million at 16 mm. These are not estimates of the nested-refinement source
mesh. The prospective 16 mm target stays local. Based on old laminar anchors,
a 5 s / 5,000-step run at candidate `dt=1 ms` could cost a few to roughly
11 wall hours if size and step cost stay near 2.08M cells; refined turbulent
runs may cost substantially more. Any accepted smaller `dt` increases steps and
requires a new prospective budget. No defensible fine-grid time/RAM projection
exists before measured characterization and a coarse E1 profile. Do not advance
to 5–10 million cells without measured evidence; no cluster allocation is
assumed.

Proposed preparation ceiling is 18 CPUs, 48 GiB and 1 hour for coarse full-
domain mesh/static checks; proposed characterization ceiling is 18 CPUs, 16
MPI ranks, 48 GiB, 30 GiB incremental disk and 4 hours for a 1–3M-cell,
300-step (`dt=0.5 ms`) pilot. These are planning values, not measured capacity,
reservations, or approved stops. An independent reviewer must freeze or replace
them in the pilot contract, and the future monitor must enforce accepted caps.

## Future staged commands (not executed)

There is no E1 case directory, mesh, sampler, runner, or `make` target yet. The
commands below are templates and were not executed; they must use new immutable
paths and must not target P0/P1. Stage 1 provisional case/mesh prep and static
checks are already authorized. Stage 2 characterization requires independent
review of a separate preregistered purpose/resource/stop contract. Stage 3 E1
execution requires its own later approval after reviewing characterization
measurements, E0 and the complete frozen E1 record. All use the pinned image ID
rather than its mutable tag.

```bash
# Stage 1: existing-authorized provisional preparation/static checks only.
.venv/bin/python scripts/run_local.py --threads 18 --timeout 3600 -- \
  docker run --rm --cpus=18 --memory=48g \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -v "$PWD/results/runs/<new-e1-prep>/case:/case" -w /case \
  sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b /bin/bash -lc \
  'source /usr/lib/openfoam/openfoam2512/etc/bashrc && blockMesh && surfaceFeatureExtract && snappyHexMesh -overwrite && checkMesh -allTopology -allGeometry'
```

Save `checkMesh`, patch/field consistency, patch extents/normals/areas,
nozzle-flux and static-pressure reconstruction, ROI spacing/layers and all
deviations. This stage supplies no flow-dependent y+, evolving Co, closure or
runtime.

Before Stage 2, preregister and independently review the proposed bounded
characterization contract: provisional curved-primary inputs and model; 1–3M
cell candidate mesh; fixed `deltaT=0.0005 s`, `endTime=0.15 s` (300 steps); at
most 16 MPI ranks/18 CPUs; 48 GiB RAM, 30 GiB incremental disk, 4 h wall; compact
output plan; per-step alpha/raw-correction, mass/phase, residual/iteration and
global/interface Co logging; wall-y+ and RAM/CPU/step/pressure/I/O cost
measurement; monitor/checkpoint behavior; and explicit solver, alpha, Co and
resource stops. Numeric stops are still unapproved until accepted in that
contract. The command assumes the future immutable `controlDict` fixes the
listed step size and end time; the monitored runner, not this shell template,
must enforce the accepted dynamic stops.

```bash
# Stage 2: characterization only after its independently reviewed contract.
.venv/bin/python scripts/run_local.py --threads 18 --timeout 14400 -- \
  docker run --rm --cpus=18 --memory=48g \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -v "$PWD/results/runs/<new-e1-characterization>/case:/case" -w /case \
  sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b /bin/bash -lc \
  'source /usr/lib/openfoam/openfoam2512/etc/bashrc && decomposePar -force && mpirun -np 16 interIsoFoam -parallel && reconstructPar'
```

Review measured y+, actual global/interface Co, alpha and mass/phase closure,
solver residuals and costs, memory/disk peaks, and resource projection. Use that
evidence to freeze the later comparison mesh/dt pair prospectively. Then a
separate E1 execution decision must record E0, accepted source/property/input
choices, exact mesh/dictionary/sampler hashes, outputs, stops, and measured
budget. Only then may the full-domain coarse comparison run toward the proposed
5 s final source regime; it is not a 0.4 s breakup-only run.

```bash
# Stage 3: coarse E1 comparison only after the separate E1 execution decision.
.venv/bin/python scripts/run_local.py --threads 18 --timeout 86400 -- \
  docker run --rm --cpus=18 --memory=48g \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -v "$PWD/results/runs/<new-e1-coarse>/case:/case" -w /case \
  sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b /bin/bash -lc \
  'source /usr/lib/openfoam/openfoam2512/etc/bashrc && decomposePar -force && mpirun -np 16 interIsoFoam -parallel && reconstructPar && foamToVTK'
```

The future runner must record image ID, exit codes and failed attempts; enforce
every accepted stop; checkpoint before limits; and write compact per-step
`alphaPhi_`/`phi`, active/absent-phase momentum, source/inventory, raw alpha
min/max/correction, Co, boundary and resource diagnostics. Keep all 51 sampled
final-window `alpha.water`, `U`, `p_rgh`, `k`, `epsilon`, `nut` fields and
extracted observables in the controlled E1 run (`purgeWrite=0`). Keep a new path
for each mesh/dt variant. Stop sequentially on any failed prerequisite; do not
advance to 30/16 mm or timestep refinement until approved coarse diagnostics and
cost are reviewed. E2 remains closed until an independent E1 disposition
expressly authorizes advancement.

## Independent decisions and exact open source gaps

The linked [gate draft](E1_ROUAIX_CASE1_GATE_DRAFT.md) remains **NOT READY for
pass/fail**. Existing authorization permits provisional input/geometry/
dictionary/mesh preparation and static checks; no solver run is approved here.
The reviewer sequence is: review static inputs/evidence before characterization;
independently approve or replace the bounded characterization contract before
that pilot; review its measured y+, Co, closure, alpha and cost evidence and
freeze the production mesh/dt prospectively; then separately authorize the E1
comparison after E0 and all input/scoring/limit decisions are frozen. Every
proposed numerical/resource value remains unapproved until accepted in the
appropriate record.

The reviewer still needs to resolve or explicitly accept these provisional
items before a controlled E1 comparison:

- initial `U`, `alpha.water`, gauge pressure/`p_rgh`, `k`, `epsilon`, `nut`;
  every nozzle, crossflow, wall and open-patch condition, especially
  `fixedFluxPressure`/`prghPressure`, reverse-flow `U`/alpha/turbulence and
  static-pressure reconstruction using local mixture density;
- prospective primary curved Fig. 3 wall trace, contact angle and mesh family;
  the flat-wall and alternate turbulence/wetting cases remain sensitivities and
  may not be selected by Figure 13 agreement;
- `realizableKE`/high-Re wall-function approximation vs source realizable
  `k-epsilon`/two-layer pairing, liquid/air turbulence conversions, paper SIMPLE
  vs proposed PIMPLE, isoAdvector vs HRIC, k/epsilon convection and pinned
  linear-solver tolerances;
- property-derived `Re_j=4.4886e6` versus printed `4.9e6`, pressure reference,
  coordinate/patch orientation, Figure 13 station rows/origin signs, source
  read bounds, sampler and 51-state-only temporal convention;
- active momentum candidates for exactly `water@nozzle` and `air@gas_inlet`,
  absent-phase same-patch leakage/status records, source/mass denominator status
  at `t=0`, raw-alpha bound and correction policy, mass closure, curve aggregate
  NRMSE vs separate temporal-range rule, and all Co/mesh/time stop/accuracy
  candidates;
- preregistered characterization purpose, exact candidate mesh/dt/300 steps,
  18-CPU/16-rank/48-GiB/30-GiB/4-hour proposal, output and monitoring plan,
  y+/Co/cost evidence, and stop contract; then actual comparison mesh/dt and
  resource freeze from measured results;
- E0 completion and separate E1 execution authorization. E2 execution stays
  closed until an independent reviewer accepts an E1 disposition that expressly
  authorizes advancement; failed, inconclusive or descriptive-only E1 requires
  a prospective scope amendment before E2.

The paper/source record does **not** recover these exact author inputs or
observables: the curved underside coordinates and wetting/contact-angle model;
initial velocity/liquid/pressure fields; inlet, wall and reverse-flow pressure
and turbulence dictionaries; air turbulence and liquid dissipation length
scale; exact realizable/two-layer implementation, linear solvers or STAR-CCM+
control deck; full mesh family/refinement and cell count; and Figure 13's sample
time/window, contour interpolation/threshold-crossing algorithm, treatment of
detached structures, and width operation. Original STAR-CCM+ case files or
specific author clarification/history would be needed to claim exact recovery;
they are not required to proceed with clearly labelled assumptions after
independent review. The `Re_j` discrepancy likewise remains a source-table
conflict unless the authors clarify it. The reported `p=101325 Pa` is represented
only as an incompressible gauge reference, not compressible thermodynamic
pressure.

No E1 mesh, sampler, characterization, solver run, build, or GPU trial was
performed for this audit. Any future result remains a conditional OpenFOAM
numerical comparison, not exact STAR-CCM+ reproduction, field validation, or
proof of E2–E6 readiness. Preserve source provenance and failed attempts; never
advance to E2 before accepted E1 disposition.
