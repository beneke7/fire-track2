# E1 Rouaix Case 1 static preparation

**Disposition: static inputs prepared; no mesh or solver execution.** This
package is a deterministic provisional reconstruction for Rouaix Case 1, the
single circular nozzle benchmark. It is not the paper's four-nozzle aircraft
comparison, an E1 characterization contract, an E1 run, a scientific pass, or
an acceptance of the candidate limits. Gate review 4 applies only to its then-
reviewed gate snapshot; the current gate draft and primary wall disposition do
not accept this corrected package. The primary disposition adopts the assumed
analytic wall for static preparation only. Characterization and E1 execution
remain closed.

## Source, version, and provenance

The reference is Rouaix et al. (2023), DOI
[10.1016/j.ijmultiphaseflow.2023.104419](https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419).
The external author PDF is
[HAL manuscript](https://hal.science/hal-04098260v1/file/Rouaix_28516.pdf),
SHA-256 `624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446`.
The source locations and extraction notes are in
[`E1_ROUAIX_CASE1_SOURCE.md`](E1_ROUAIX_CASE1_SOURCE.md): Fig. 1 (PDF p. 4 /
article p. 3) supplies axes/signs; Table 2 (PDF p. 5 / article p. 4) supplies
fluid properties; Table 3 on that page supplies Case 1 conditions; §3.1 (PDF
p. 6 / article p. 5) describes solver/model choices; §3.2 and Fig. 3 (PDF p.
7 / article p. 6) describe the domain; §3.3 (PDF p. 8 / article p. 7) gives
mesh family/resolution; Fig. 13 (PDF p. 13 / article p. 12) supplies sampled
reference ordinates.

The pinned implementation is OpenCFD OpenFOAM v2512 image
`sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`.
Static source inspection used this image only. Gate review 4's historical
gate snapshot was SHA-256
`15a9b4a48df3f8b059b98961d92cd89bdc8b69ffe1f66beaa81f936167ffe3ea`; that
disposition does not extend to the primary-amended current gate draft
(`28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7`). The
primary wall-disposition memo (`181ee1644d8611fac003f22eeddc161eaaaac1bea17987c1d709202ed90a7d18`)
adopts the analytic wall for static preparation only and leaves this package
for exact independent review. Neither shared file was edited for this
follow-up. The unchanged CPU capability audit
(`a6c655abbf58eff6bb71850fbed8612ece459c891ad9e21b4f5d3ddf7e7fcb32`) is
predecessor evidence: its earlier no-case/trace statements do not describe the
current static package and are not a capability review of these artifacts.

| Pinned v2512 source/tutorial input | SHA-256 | Use |
| --- | --- | --- |
| `src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvectionTemplates.C` | `1d704aec280cffa4302f75cc3e15654db25dc75c6d1cb9e230ab8a4be64f1e90` | Conservative limiter, alpha capture order, `alphaPhi_` separation |
| `src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvection.C` | `c2ed42ee16632e77b8aad9ff2adc87214cfd5c0a1b94387644e51aa2835b6380` | Optional snap/clip order and clipping behavior |
| `applications/solvers/multiphase/interIsoFoam/alphaEqn.H` | `cbb4348977388633b29f0aa1f612225249c3062e80755f548fddfb0760c7311f` | Solver alpha equation and final capture stage |
| `applications/solvers/multiphase/interIsoFoam/alphaEqnSubCycle.H` | `b5f9845d57cb3fc75577ef00ed338186f83d13a9261c67d4ef88e6f1ef419385` | Alpha subcycle placement |
| `src/finiteVolume/fields/fvPatchFields/derived/prghPressure/prghPressureFvPatchScalarField.C` | `672bc7535cf6fd76357ebf311ca747c44ab221f2cca36a8bea5c511404c7577a` | Static-pressure reconstruction convention and density patch use |
| `src/transportModels/twoPhaseProperties/alphaContactAngle/constantAlphaContactAngle/constantAlphaContactAngleFvPatchScalarField.C` | `49eb345b942a0952b8f63cf9b363c9f64826eb6b9d59c20d1f014c646579d812` | `constantAlphaContactAngle` patch-type implementation; `theta0`/`limit` selection |
| `src/finiteVolume/fields/fvPatchFields/derived/fixedFluxPressure/fixedFluxPressureFvPatchScalarField.C` | `397adeba8ad56cbda72b9bcbedaa1ea807bb1dd2967f1957ffd4f0773d7038d7` | Velocity-boundary pressure patch implementation |
| `src/TurbulenceModels/turbulenceModels/derivedFvPatchFields/wallFunctions/nutWallFunctions/nutkWallFunction/nutkWallFunctionFvPatchScalarField.C` | `0dc183bec3b00091216ecbf747d45ba0dd59c5f7676135d1fab741ec340915e9` | `nutkWallFunction` type used on the no-slip wall |
| `tutorials/multiphase/interIsoFoam/weirOverflow/0.orig/nut` | `18a57ea1d8629b3fb53a35a6849b93cc10775cd51161ec663eb445733f509608` | v2512 example for wall and non-wall `nut` field type conventions |
| `src/finiteVolume/fields/fvPatchFields/derived/pressureInletOutletVelocity/pressureInletOutletVelocityFvPatchVectorField.C` | `b01263caab11b2c10139b18e5907f1a77bc04ef79f254377fa0483a926a0158b` | Open-boundary velocity behavior |
| `src/phaseSystemModels/twoPhaseInter/incompressibleInterPhaseTransportModel/incompressibleInterPhaseTransportModel.C` | `2b9a817a0300bdc00deed7af5422dc53455f82922eb7f0b6e10487c8313ac93f` | Lines 43–108: density defaults to `uniform`; `density variable` selects `rhoPhi` |
| `src/TurbulenceModels/phaseIncompressible/PhaseIncompressibleTurbulenceModel/PhaseIncompressibleTurbulenceModel.C` | `5d8831e421d14148ca8cabad168d6ef63f1faaa69d52c60195f358c4fd52ea40` | Lines 44–62: variable-density phase model uses `geometricOneField`, `rho`, and `alphaRhoPhi` |
| `src/TurbulenceModels/turbulenceModels/linearViscousStress/linearViscousStress.C` | `f28f4a6bb9a5d4448226fa6407f505808fb2c2840b224a435d36fa898d30ea5f` | Lines 122–132: variable-density viscous term is `div((rho*nuEff)*dev2(T(grad(U))))` with a matching Laplacian |
| `tutorials/multiphase/interIsoFoam/damBreak/system/fvSchemes` | `393cdcc3e0a61482f76c88d2be3ccdcad3e228663e38405aad148f9de717af11` | Line 31 carries the exact `div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;` dictionary key |
| `applications/solvers/multiphase/interIsoFoam/alphaControls.H` | `a66ad72324f526c0194f99fa7f64712da966e1bd7118c357217993069c763004` | Line 1: alpha controls are read through `mesh.solverDict(alpha1.name())` |
| `src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvection.C` | `c2ed42ee16632e77b8aad9ff2adc87214cfd5c0a1b94387644e51aa2835b6380` | Line 63: isoAdvector uses the same alpha-named solver dictionary |
| `applications/utilities/mesh/manipulation/topoSet/topoSet.C` | `d52f0faa425e81c73e597035fae27135fed1dab109526e8316cd8f5df08e801b` | Lines 344–375: `subset` forms a work set, then intersects it with the existing face set |
| `src/meshTools/topoSet/faceSources/patchToFace/patchToFace.C` | `a6a13ea9d8f81494156d0f1bda7fe24aeef892c751ff460cf16e6c294a68069d` | Selects all faces in the named existing boundary patch |
| `src/meshTools/topoSet/faceSources/cylinderToFace/cylinderToFace.C` | `6ce2a20b1fcee2781acdb58743be744c36ea9a07771b4e9a38f0b0c2f2ab256a` | Lines 63–94: cylinder selection tests face centres inside the finite cylinder |
| `applications/utilities/mesh/manipulation/createPatch/createPatch.C` | `68bc731d6f5f6b5368d00cf7caf730b45c8b5f04b5b70a495a34ea85170a6c08` | Pinned utility source for the set-to-patch conversion |

The corresponding official source pages are the [v2512 density selector](https://api.openfoam.com/2512/incompressibleInterPhaseTransportModel_8C_source.html), [linear viscous stress implementation](https://api.openfoam.com/2512/linearViscousStress_8C_source.html), [isoAdvector source](https://api.openfoam.com/2512/isoAdvection_8C_source.html), and [topoSet source listing](https://api.openfoam.com/2512/files.html). Hashes above were computed from the pinned image filesystem, not from mutable web pages.

The full deterministic file list and per-file SHA-256 digests are in
[`cases/e1_rouaix_case1_static/CASE_SHA256SUMS`](../cases/e1_rouaix_case1_static/CASE_SHA256SUMS).
The regenerated `CASE_SHA256SUMS` manifest SHA-256 is
`3cbc0528bc8b2d9feb35529e85d5bd1b247c92e4f7f28345f53db1ba462cfb8e`.
The pure-Python generator and checker are in
[`prepare_case.py`](../cases/e1_rouaix_case1_static/prepare_case.py) and
[`static_preparation.py`](../cases/e1_rouaix_case1_static/static_preparation.py).
No source PDF or rendered page was added to the repository.

## Reported values, derivations, and assumptions

The case is the single round water jet with `d_j=0.400 m`,
`U_j=(0,-10,0) m/s`, uniform gas crossflow `U_g=(70,0,0) m/s`,
`rho_water=997.6 kg/m^3`, `mu_water=8.89e-4 Pa s`,
`rho_air=1.18 kg/m^3`, `mu_air=1.86e-5 Pa s`, and
`sigma=0.072 N/m`. The coordinate frame is `+x` crossflow, `+y` upward, `+z`
spanwise; gravity is `(0,-9.81,0) m/s^2`; nozzle center/reference is
`(0,0,0) m`. These are the paper's reported Case 1/frame values except for
the origin convention. Kinematic viscosities are derived as `mu/rho` and
classified that way in the generated dictionary source.

For the reported diameter and speed, the circular area is
`0.1256637061 m^2`, liquid volume flux `1.2566370614 m^3/s`, mass flux
`1253.6211 kg/s`, and inward momentum flux `(0,-12536.2113,0) N`. These are
arithmetic consequences of reported steady boundary values, not measured
payload or finite-duration release. The source's printed Case 1
`Re_j=4.9e6` is retained as reported; the property-based calculation
`4.4886389e6` is not tuned to match it.

The domain dictionary uses the paper's approximate 20 m streamwise length,
10 m height, 7 m top span, 16 m bottom span, 25 degree nominal opening, and
gas inlet 2.5 m upstream. This yields nominal trapezoid volume `2300 m^3`
and a dimension-derived side angle about `24.23 degrees`; the difference from
25 degrees is retained as rounded source geometry. The top wall is only
schematically curved in the source. A quantitative Figure 3 trace is not
defensible: the view is an isometric domain schematic with perspective, no
profile coordinate axes, no wall ordinates, and no scale transform for the
curved underside. Its dimension labels establish approximate domain extents
but cannot identify a unique wall curve; pixel-to-world and perspective
uncertainty therefore cannot be bounded from this figure. For auditability,
the source PDF SHA-256
is `624efe9ee2aec11b85624e9e2ac5364802b12c42657711d211e625052cf28446`;
the 180-dpi rendering of PDF page 7 (zero-based page index 6) is
`/tmp/rouaix_figure3_page7.png`, SHA-256
`12cd10ef2d1cb06b397dcc2fa81e83067a83bf8f7be5eca64a2d302fa2291726`.
No point trace or pixel-to-world transform is claimed; a fit would be an
invented geometry rather than a source extraction. **Primary disposition,
2026-09-25:** the gate now adopts the explicitly assumed analytic surface
`y=A*(1-exp(-((x/Lx)^2+(z/Lz)^2)))`, with `A=0.080 m` and
`Lx=Lz=0.800 m`, represented by the declared bilinear node grid, for static
preparation only. It is not a Figure 3 trace or recovered aircraft geometry.
Keep the flat-wall and declared geometry sensitivities. This does not accept
the case package or authorize characterization, E1 execution, or Figure 13
comparison; those require separate exact review and authorization. The current
deterministic reconstruction
`y=A*(1-exp(-((x/Lx)^2+(z/Lz)^2)))` uses explicitly assumed
`A=0.080 m`, `Lx=Lz=0.800 m`, nozzle center at `y=0`, and piecewise bilinear
faces through `geometry/top_wall_nodes.csv`. It is neither a measured surface
nor aircraft CAD. Its generated classification is “assumed analytic wall; not
source-derived geometry.” The static checker requires finite node coordinates,
the declared x/z footprint, and `0 <= y <= A` with a `5e-11 m` upper allowance.
That allowance is the maximum half-step from the generator's nine-significant-
digit `.9g` y serialization at `A=0.08 m`, not a physical geometry tolerance.
The 26-by-23 node layout, structured blocks, local
refinement level 2, and five candidate prism layers with expansion 1.1 are
preparation choices. Layer thickness parameters are assumed. No meshing
utility was run; there is no mesh, `checkMesh` report, measured nozzle area,
cell count, or mesh-confirmed patch-face selection.

`constant/transportProperties` records the reported densities, derived
kinematic viscosities, and surface tension. The case explicitly sets
`density variable;` in `turbulenceProperties`, provisionally selecting the
pinned v2512 `rhoPhi` turbulence path; without the entry, that selector
defaults to `uniform`/`phi`. `fvSchemes` supplies the three provisional
`rhoPhi` convection entries and the exact selected variable-path viscous key
`div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;`. This aligns the input
scheme key with the declared equation path; it is not a frozen or validated
scheme. `realizableKE`, turbulence values, initial air-only state,
inlet/outlet pressure treatment, contact angle, PIMPLE settings, discretization,
and mesh details follow the bounded gate proposal; they remain provisional.
The water inlet turbulence intensity
`I_j=0.01` is reported, while `k_j=0.015 m^2/s^2` is derived using isotropic
conversion. Its length scale, `epsilon`, and all air turbulence values are
assumptions, not paper measurements.

### Provisional D-NUT-BC mapping

The dictionaries instantiate a clearly labelled candidate: `calculated` with
zero seed on nozzle and gas-inlet `nut`, `inletOutlet` with explicit zero
reverse-flow `inletValue` on open boundaries, and `nutkWallFunction` with zero
seed on the no-slip wall. The paper specifies no `nut` patch fields. The
pinned v2512 `weirOverflow` tutorial demonstrates the wall function and
non-wall calculated-field pattern; `inletOutlet` at open patches is an
explicit project assumption to carry a safe zero reverse-flow state. This
mapping is neither measured nor independently accepted as a frozen boundary
condition. Its static type/seed consistency is checked. D-NUT-BC, including
the interaction with turbulence correction and reverse flow, remains an open
review decision before characterization.

### Pressure, fields, and inlet consistency

The pinned v2512 convention is
`p_rgh = p_static - rho*(g dot (x-x_ref))`, with `x_ref=(0,0,0) m` and
mixture density from `alpha.water`. `prghPressure` uses `p=0 Pa` gauge and
`rho=rho` on each opening. The `p_rgh` file is deliberately only a uniform
zero seed so static field files are complete; this is **not** hydrostatic
initialization. Before any future solver launch, the mesh must exist and the
hashed `setExprFieldsDict` must replace it with the provisional air field
`p_rgh=1.18*9.81*y` (Pa), then checks must reconstruct zero static gauge
pressure at cell centers and open faces. At `y=-10 m`, this gives
`p_rgh=-115.758 Pa` for air and `-97864.56 Pa` for water at zero static gauge
pressure. The pure-Python static test exercises both signs and the inverse
reconstruction. This preparation did not run `setExprFields`.

The field checker compares all six field dimensions, required seven patch
names, and every patch-field type with the candidate mapping. Additional
checks connect transport properties, gravity/reference height, inlet velocity
and phase fraction, air-only zero initial `alpha.water`, domain extents, block
count, and assumed wall nodes. The nominal inlet integral is checked
analytically; only a future mesh integration can verify actual selected nozzle
area and flux.

## Sampler and static diagnostic semantics

The candidate `controlDict` declares `interIsoFoam`, `dt=0.001 s`, end time
`5 s`, write interval `0.01 s`, and sampler start `4.50 s`. Those times follow
the proposal, not a Figure 13 sample time: the paper gives no averaging window.
They are not accepted execution settings. Planes have normal `+x` and each
sets `interpolate true;` with `cellPoint` interpolation
(`interpolationCellPoint` in the v2512 scheme terminology). The checker
asserts interpolation on all 30 planes; declaring a control-level scheme
alone does not enable interpolation for an individual plane. Penetration
samples are `X={0.25,0.50,...,4.75,4.875}`;
reported width samples are the separate `X={0.25,0.50,...,2.50}` grid. The
CSV column names are preserved as `penetration_y` and `width_z`. The
digitizer's `(0,0)` calibration anchor stays in the source CSV but is excluded
from score stations.

The draft observable interpretation is recorded without claiming author
extraction code: threshold `alpha.water=0.1`,
`Y=(y0-y_min)/d_j` (positive downward though `+y` is upward), and
`Z=(z_max-z_min)/d_j` (outer full span, with no factor-of-two conversion).
All crossings, including disconnected components, determine extrema; a
missing station is not silently dropped and makes the static score unavailable.
Synthetic fixtures check the contour crossing, signs, disconnected extrema,
zero-reference behavior, missing stations, station grids, and source-bound
NRMSE semantics. The source-bound score helper only evaluates test fixtures;
it is not an E1 result or accepted pass threshold. Candidate normalization
ranges are `R_Y=5.225` and `R_Z=3.257`. Source extraction uncertainty is a
digitization bound, not a statistical interval or CFD tolerance.

The stage contract in
[`ALPHA_CAPTURE_MAP.md`](../cases/e1_rouaix_case1_static/ALPHA_CAPTURE_MAP.md)
uses `alpha_preclip` after the pinned conservative limiter and before clipping,
`alpha_postclip` after brute-force correction, and `alpha_solver_final` after
the alpha equation. `snapTol=0` disables snap for this proposal. Preclip
validity is preserved even where clipping makes postclip alpha valid;
`alphaPhi_`, clipping correction, and later corrections remain separate.
The proposed alpha bound is unapproved. No instrumentation or solver source
was edited.

The alpha entry in `fvSolution` is nested inside `solvers`, matching the pinned
`mesh.solverDict(alpha1.name())` lookup in `alphaControls.H` and
`isoAdvection.C`. The provisional controls retain `clip true`, `snapTol 0`,
one subcycle, and `reconstructionScheme isoAlpha`. The `p_rgh` GAMG entry
explicitly nominates the provisional `DICGaussSeidel` smoother. The wall
contact-angle checker inspects the `aircraftWall` block for
`constantAlphaContactAngle`, `theta0 90;`, the required `limit gradient;`,
and the initialization value; it rejects the unrelated `thetaA`, `thetaR`,
and `uTheta` parameterization. None of those numerical choices is a measured
or characterization-approved result.

### Boundary-only nozzle-set construction

The static dictionaries encode this utility order: `blockMesh` creates the
`aircraftWall` boundary; `topoSet` creates `nozzleFaces` from `patchToFace`
with `patch aircraftWall`, then applies `action subset` using the finite
`cylinderToFace` selector from `(0,-0.1,0)` to `(0,0.1,0)` with radius
`0.2 m`; `createPatch` converts the intersected set to patch `nozzle`; then
`snappyHexMesh -overwrite` refines and adds candidate layers to the remaining
`aircraftWall`. In pinned v2512, `topoSet` constructs a work set for the
second action and intersects it with the current set. `cylinderToFace` tests
face centres, not full-face containment. The static contract therefore
restricts candidates to existing aircraft-wall boundary faces, but selected
face count, area, and normals remain unknown until a future mesh check. The
order is stored in `geometry/domain.json` and checked statically. No utility
was invoked.

### Exact output tree and regeneration behavior

The generator declares exactly 20 case/geometry files: six under `case/0`,
four under `case/constant`, eight under `case/system`, and two under
`geometry`. `CASE_SHA256SUMS` lists exactly those paths in the declared order.
Before writing, the generator refuses unexpected files, directories,
symlinks, hard-linked outputs, and non-file paths under the output trees; it
does not delete or overwrite unknown content. A clean temporary package was generated twice,
with all 20 file bytes and the manifest bytes compared exactly. The same
offline test confirms that an unknown sentinel survives a refused generation.
The checked-in manifest is frozen only after all owned generator and
dictionary edits are stable.

## Verification and open decisions

The static checks and synthetic tests are listed in the task handoff. They
only inspect files and exercise pure-Python fixtures. No CFD, meshing
execution, characterization, E1 solver execution, or GPU job was launched.
The next acceptance evidence is a separate independent review of the exact
case and manifest hashes, explicit disposition of D-NUT-BC/contact-angle and
other assumed boundaries, validated geometry/mesh and actual nozzle patch
area, source-consistent pressure/field initialization, and a separately
reviewed bounded characterization contract. E1 remains closed until all
scientific inputs, mesh, observables, limits, diagnostics, resource/stops,
and independent review are accepted. The current package cannot support an
E1 pass, E2 advancement, field validity, or performance claim.
