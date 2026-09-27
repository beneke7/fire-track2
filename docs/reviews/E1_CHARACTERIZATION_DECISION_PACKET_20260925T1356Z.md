# E1 characterization decision packet

**Prepared:** 2026-09-25 13:56 UTC  
**Disposition:** primary decision aid only. This packet approves no mesh, characterization, solver run, E1 comparison, or scientific gate. It follows Project Warden checkpoint 11, rank 6. The current E1 gate remains NOT READY.

## Current evidence and scope

The corrected static input files passed exact review for static-artifact scope; the factual gate-inventory correction also passed exact follow-up. Those dispositions do not accept their provisional physics, approve a mesh, or close characterization. The latest status keeps D-NUT-BC, contact angle, instrumentation, mesh/initialization, and characterization approval open. There is no E1 mesh or solver run. See [STATUS.md](../STATUS.md#L10), [the static correction review](E1_STATIC_CORRECTION_EXACT_REVIEW_20260925T1305Z.md#L4), and [the inventory follow-up](E1_GATE_INVENTORY_EXACT_FOLLOWUP_20260925T1320Z.md#L4).

This is analytical planning from the accepted static package, the CPU capability audit, the current gate, Rouaix's author manuscript, and the plan. The pinned CPU solver image is OpenCFD OpenFOAM v2512, image ID <code>sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b</code>. Rouaix Case 1 is a single 0.4 m round nozzle at 10 m/s downward into 70 m/s crossflow; it is not the paper's four-nozzle aircraft comparison. The reported 16 mm resolution is the finest local mesh target, not a whole-domain cell count. The source reports five prism layers with 1.1 growth and mesh scales 70, 50, 30, and 16 mm (PDF pp. 5, 8; article pp. 4, 7; Table 3 and §3.3). Figure 13 is PDF p. 13 / article p. 12.

The source leaves the aircraft-wall coordinates, contact angle, initial fields, non-wall nut conditions, and reverse-flow conditions unspecified. It also does not state the Figure 13 time/window or exact width extraction operation. These gaps allow a clearly labelled reconstructed comparison after review; they do not support a claim of exact STAR-CCM+ reproduction. The independent audit and source record provide the broader deviation and uncertainty list ([audit](../../experiments/E1_CPU_SOLVER_CAPABILITY_AUDIT.md#L266), [source record](../../experiments/E1_ROUAIX_CASE1_SOURCE.md#L161)).

## Proposed choices for the primary to dispose

These are candidate inputs for a future reviewed characterization record. They are not paper-recovered values.

| Decision | Candidate proposal | Basis and required caveat |
| --- | --- | --- |
| D-NUT-BC at nozzle and gas inlet | <code>calculated</code>, seeded with zero in the initial field. | This matches the pinned v2512 <code>weirOverflow</code> <code>nut</code> tutorial's non-wall pattern (lines 23–33) and lets the chosen RANS model provide <code>nut</code>. The static candidate already uses this mapping on both inlet patches. |
| D-NUT-BC at the no-slip wall | <code>nutkWallFunction</code>, zero seed; retain <code>kqRWallFunction</code> and <code>epsilonWallFunction</code> with the same high-Re wall treatment. | The v2512 tutorial uses <code>nutkWallFunction</code> at its wall (lines 35–39). The wall function derives y+ from wall distance, k, viscosity, and the wall velocity gradient (pinned source <code>nutkWallFunctionFvPatchScalarField.C:243–292</code>). This is an OpenFOAM approximation; Rouaix reports realizable k-epsilon with two-layer wall treatment. v2512 documents <code>twoLayerTreatment</code> for standard <code>kEpsilon</code>, so <code>realizableKE</code> plus high-Re wall functions is an explicitly provisional pairing, not the paper's exact combination. |
| D-NUT-BC at open patches | Prefer <code>calculated</code>, seeded with zero, on downstream, bottom, and both spanwise openings. Carry the current static package's <code>inletOutlet</code> with explicit zero reverse <code>inletValue</code> as a predeclared alternate. | <code>realizableKE::correctNut</code> forms nut from its k/epsilon and strain closure, then corrects boundary conditions (<code>realizableKE.C:76–87</code>). <code>calculated</code> is the tutorial's outlet pattern. In contrast, the current static candidate prescribes zero nut on opening inflow while its k and epsilon patches prescribe assumed ambient values. The paper supplies no evidence to choose that zero as a physical backflow state. The primary should freeze one mapping before mesh preparation and treat the other as a sensitivity, never select it by Figure 13 fit. |
| Wall contact-angle model | Retain <code>constantAlphaContactAngle</code>, <code>theta0 90</code>, <code>limit gradient</code>, and <code>value uniform 0</code> as the provisional primary. | <code>theta0=90</code> is an assumed neutral-wetting baseline; neither it nor the angle-limit method is in Rouaix. In v2512 the constant model returns the same theta0 on the patch (<code>constantAlphaContactAngleFvPatchScalarField.C:48–60, 102–110</code>). Its base class supports <code>none</code>, <code>gradient</code>, <code>zeroGradient</code>, and <code>alpha</code>; <code>gradient</code> clamps the resulting alpha by adjusting the gradient, while <code>alpha</code> clamps the evaluated patch value (<code>alphaContactAngleTwoPhaseFvPatchScalarField.C:35–45, 126–151</code>). The accepted static dictionary and checker already pin <code>gradient</code>. |

The open-patch D-NUT recommendation is the one prospective input change suggested by this inspection: the current accepted static artifact encodes <code>inletOutlet</code> with zero reverse value at all four openings. If the primary keeps that mapping, the characterization record must say that zero is an assumed numerical backflow state and require post-turbulence-correction nut values to be logged beside k, epsilon, and signed patch flow. Under either mapping, log reverse flow separately at every open patch. Predeclare integrated inward open-boundary flux greater than zero as a trigger to characterize the alternate mapping on the same mesh and timestep; do not switch mappings within a run. The reviewer must freeze an observable sensitivity bound before either run. If no bound is accepted or the alternate remains unrun, later source comparison is descriptive only. Do not change boundary dictionaries after seeing any Figure 13 overlay.

For wall alpha, a <code>limit alpha</code> run at the same 90-degree angle is a numerical-boundary sensitivity. A <code>zeroGradient</code> case is useful only as a zero-contact-gradient diagnostic; it does not supply another physical contact angle. No numerical wetting-angle range or materiality bound is set here because neither the paper nor the plan supplies one. If no defensible range or accepted primary angle is available, retain 90 degrees as an assumption; until a contact-angle sensitivity bound is accepted, do not make a source pass/fail claim that depends on wall-interaction uncertainty. A flat wall and alternate turbulence pairing remain named sensitivities and cannot be chosen by best fit.

## Exact alpha capture contract

Use the reviewed source-order names in [ALPHA_CAPTURE_MAP.md](../../cases/e1_rouaix_case1_static/ALPHA_CAPTURE_MAP.md), not the older <code>alpha_preclip_presnap</code> and <code>alpha_postclip_presnap</code> labels still present in the audit/gate text. The map pins OpenFOAM v2512 and says <code>snapTol 0</code> disables snap while <code>clip true</code> enables clipping.

1. **<code>alpha_preclip</code>**: after conservative <code>limitFluxes(Sp, Su)</code> and the “After conservative bounding” state, before <code>applyBruteForceBounding()</code>. In the pinned <code>isoAdvectionTemplates.C</code>, <code>limitFluxes</code> is at line 491, the conservative-bound observation at lines 493–498, and the call into clipping/snapping at line 503. Keep its own extrema, out-of-range cell count, and out-of-range volume. A later valid field does not clear this result.
2. **<code>alpha_postclip</code>**: immediately after <code>applyBruteForceBounding()</code> returns. In <code>isoAdvection.C:625–652</code>, snap runs only for <code>snapTol &gt; 0</code>; <code>clip true</code> clamps to [0,1] and then corrects boundary conditions. Preserve the signed volume change <code>DeltaV_clip = sum_i(V_i*(alpha_postclip_i-alpha_preclip_i))</code>.
3. **<code>alpha_solver_final</code>**: after the alpha equation/subcycle completes for the outer correction. <code>interIsoFoam/alphaEqn.H:8–23</code> calls <code>advector.advect</code>, obtains <code>rhoPhi</code>, and corrects the mixture; <code>alphaEqnSubCycle.H:30–48</code> shows subcycle placement. With the candidate single outer correction and one alpha subcycle, this is the candidate end-of-step state. Remap it if outer corrections or subcycling change. Preserve <code>DeltaV_later = sum_i(V_i*(alpha_solver_final_i-alpha_postclip_i))</code>.

<code>alphaPhi_</code> is a distinct transported phase flux: the template assigns <code>alphaPhi_ = dVf_/deltaT</code> at line 514 after the brute-force bounding call. It is not the clipping correction. Capture its per-patch signed integral separately from <code>DeltaV_clip</code>, <code>DeltaV_later</code>, <code>phi</code>, and in-domain water inventory. The proposed alpha range <code>[-1e-6, 1+1e-6]</code> is an unapproved integrity limit; if accepted, a violation at any named stage invalidates the attempt and bars scoring. Never externally clip or renormalize alpha.

## Mesh, patch, and initialization checks

No mesh was created for this packet. The accepted package's utility order is: <code>blockMesh</code> creates <code>aircraftWall</code>; <code>topoSet</code> selects existing <code>aircraftWall</code> faces and intersects them with the finite 0.2 m-radius nozzle cylinder; <code>createPatch</code> creates <code>nozzle</code>; <code>snappyHexMesh -overwrite</code> refines and adds candidate wall layers; then <code>checkMesh</code> runs. The cylinder selector tests face centres, so selected face count, aperture area, and normals remain unknown until a mesh exists. See the preparation record at lines 241–255; it explicitly says no utility was invoked.

After the exact input review, retain the assumed Gaussian aircraft wall (A=0.080 m, Lx=Lz=0.800 m) only as the static primary geometry. It is not a Fig. 3 trace or recovered aircraft CAD. The current structured node layout, local refinement, and five candidate prism layers are preparation assumptions. Record the final mesh hash, actual cell count, local equivalent-size distribution, prism coverage/growth, face orientation/area, full domain and wall gap, and complete <code>checkMesh -allTopology -allGeometry</code> output. Verify nozzle area, equivalent diameter, normals, face count, and area-integrated water flux from the mesh rather than from the nominal circle. Require the nominal reference checks: area 0.125664 m2, water volume flux 1.25664 m3/s, mass flow about 1.254e3 kg/s, and downward momentum flux about 12.54 kN. Preserve all deviations from the source's polyhedral mesh and local 70/50/30/16 mm scales; do not claim a mesh match from total cell count.

The internal initial state is proposed as air only: alpha.water zero and water inventory zero; uniform crossflow U=(70,0,0) m/s; assumed air k and epsilon; and nut seed zero. The nozzle and gas-inlet velocities/phase fractions use the paper's values. The static p_rgh file is only a zero seed and must not be used as the solver initialization. After mesh creation, apply the pinned setExprFields dictionary and verify at every cell centre and open face that

<code>p_rgh = p_static - rho*(g dot (x-x_ref))</code>,

with p_static gauge zero, g=(0,-9.81,0) m/s2, x_ref=(0,0,0) at the nozzle, and local rho=alpha.water*rho_water+(1-alpha.water)*rho_air. For air-only initialization this gives p_rgh=1.18*9.81*y; at y=-10 m it is -115.758 Pa for air. Static preparation gives -97864.56 Pa for pure water there. Check the inverse reconstruction to zero gauge pressure on cells and open faces. <code>prghPressureFvPatchScalarField.C:143–161</code> reads patch-local density, gravity, hRef, and face centres to form the pressure condition.

Static acceptance should enumerate all fields, dimensions, patch names/types, inlet directions, phase values, assumed turbulence inputs, boundary pressure/backflow values, image ID, and hashes. Check both active momentum pairs (<code>water@nozzle</code>, <code>air@gasInlet</code>) and same-patch normalized absent-phase leakage without dividing by a zero reference. A static y+ estimate is not runtime y+; the characterization must report the area-weighted wall y+ distribution after the RANS wall function has run.

## Proposed bounded characterization and stops

Keep the gate draft's candidate for planning: 1–3 million cells, fixed deltaT=0.5 ms, 300 steps to 0.15 s, at most 16 MPI ranks inside an 18-CPU cap, 48 GiB RAM, 30 GiB incremental disk, and four hours wall time. This is a startup/resource pilot only. It is not Figure 13 evidence, an E1 result, or an E1 gate run. These limits are planning values, not approved resource reservations or measured costs. The CPU audit reports an old 2.0812-million-cell laminar pilot with about 5.55–5.60 GiB sampled peak RAM on 16 ranks; that is not an E1 RANS forecast.

Before a future launch, the independent contract reviewer must freeze or replace every number and stop below. A scale preflight matters: at 70 m/s and 0.5 ms, a 16 mm cell gives Co about 2.19 by aligned-grid arithmetic. Thus the proposed interface-Co stop of 1.0 could conflict with a 16 mm interface region. Compute from the exact candidate mesh before launch; change mesh/dt or obtain prospective stop approval before running, never after observing output. The proposed global Co stop 5.7 is only numerically anchored to a STAR-CCM+ report and does not establish cross-solver equivalence; interface Co 1.0 is a project candidate, not a paper limit.

| Stop / limit | Candidate for independent review | Required response |
| --- | --- | --- |
| Work cap | 300 steps / 0.15 s, whichever occurs first; 4 h wall, 18 CPUs, 16 MPI ranks, 48 GiB container memory, 30 GiB added disk, whichever resource cap occurs first. | Preserve the exact stop reason, latest complete checkpoint, and failed attempt. Use a pinned image ID and immutable run path. |
| Alpha integrity | At all three named capture stages, finite values and proposed range [-1e-6, 1+1e-6]. | Stop on any accepted-limit violation; do not use a repaired postclip value to clear an earlier failure. |
| Flow/time-step behavior | Proposed Co_global &lt;= 5.7 and Co_interface &lt;= 1.0; record both every step. | Stop at the accepted cap. No cap may be treated as accuracy evidence. |
| Conservation and boundaries | Candidate mass/phase closure 0.5%; active momentum checks 0.5% of each nonzero reference; absent-phase leakage separately normalized against the present phase on that same patch. | Candidate values require source/physical justification and independent acceptance. At t=0 report zero-source/zero-inventory absolute checks, not a relative error. Stop on invalid references, missing fields, lost boundary coverage, or accepted closure failure. |
| Solver health | Save residual and iteration histories for each equation; stop if a solver reaches maxIter without its frozen tolerance, fields become nonfinite, or pressure/continuity iteration fails the reviewed rule. | Retain the failed output and all per-step diagnostics; do not tune solver controls after seeing comparison output. |
| Runtime monitor | Docker hard CPU/memory limits and launcher wall timeout, plus a separate disk/resource monitor with sampling interval, overshoot allowance, signals, and completion markers frozen in the contract. | <code>scripts/run_local.py</code> caps common thread variables and can time out a process group; it does not monitor RAM or disk. The existing pilot samples Docker usage about every two seconds and warns that peaks can be missed. The E1 runner must prove the actual container stopped before it records a controlled stop. |

For output, freeze a compact per-step record of global/interface Co, three alpha-stage extrema/counts/volumes and correction deltas, alphaPhi_/phi patch fluxes, water inventory/closure, active/absent phase momentum, reverse flow, residuals/iterations, y+, CPU/RAM/disk, step time, pressure-solve time, and I/O time. Keep full fields sparse (candidate snapshots at 0, 0.075, and 0.15 s) and retain a checkpoint at a preregistered interval; calculate an uncompressed upper bound from the actual cell count and field list before accepting the 30 GiB output ceiling. These cadence choices are proposals for review. Do not require stationarity or Figure 13 output from this pilot.

## Fallbacks and remaining blockers

- If the primary wall/contact-angle assumption is declined, preserve any future flow result as a descriptive overlay. The paper's statement that a flat wall made no significant difference is based on unreported preliminary tests; it does not release the wall sensitivity.
- If nut backflow assumptions remain unresolved, report the measured reverse-flow and closure evidence but no source pass/fail claim. Do not change D-NUT-BC in response to a favorable plume image.
- If source timing/width semantics, exact initialization, model deviation, or the unapproved comparison limits are not accepted, report Figure 13 curves descriptively with their digitization bounds and no pass/fail label. Keep Figure 16 breakup as q-level context because Cases 1, 8, and 9 share q=17.3. Carry, do not tune, property-derived Re_j=4.4886e6 versus the Table 3 value 4.9e6.
- Characterization evidence may prospectively set the later comparison mesh and timestep only. A separate E1 execution decision still needs E0 evidence, frozen source semantics/limits, actual mesh/dictionary/sampler hashes, and a distinct independent review. E2 remains closed unless an accepted E1 disposition expressly authorizes advancement.

Concrete order: (1) primary disposes the proposed D-NUT-BC, contact-angle, density-mode, solver-deviation choices, and older capture-name mismatch; (2) preparation owner writes a successor input record and hashes it; (3) an exact independent review accepts those exact input hashes before mesh generation; (4) prepare the mesh and pressure initialization, then archive mesh, patch, field, and checkMesh evidence; (5) independently review the exact mesh/static bundle and a preregistered characterization contract, including the monitor and accepted numerical/resource stops; (6) only then run one bounded CPU characterization, adding the predeclared D-NUT alternate if the reverse-flow trigger occurs; (7) review its raw diagnostics and resource profile before separately freezing a comparison mesh/timestep and asking for E1 execution review. Each failed or stopped attempt remains immutable.

## Hash-pinned inputs and source evidence

Snapshot hashes below pin the materials consulted for this packet. The accepted package manifest hash commits its complete 20-file list; current per-file values also appear in CASE_SHA256SUMS. The author manuscript is an external copy in /tmp and its original project root PDFs were not changed.

| Artifact | SHA-256 |
| --- | --- |
| Project plan, track2_aerial_drop_experiment_plan.md | 569833febde7ddecd5f709dfb13b88d7d15a8abc77a95657ee4a29596e6f310d |
| CPU audit, experiments/E1_CPU_SOLVER_CAPABILITY_AUDIT.md | a6c655abbf58eff6bb71850fbed8612ece459c891ad9e21b4f5d3ddf7e7fcb32 |
| Accepted static preparation record | 4178ea3201c6960c250831a93320e821a20427908701fd911a747582d02a6fe1 |
| Current E1 gate draft | 8e3efe6a3e7edb91985550ff5c285615e5b26f880e74415cb57962efdb7d9132 |
| Rouaix source transcription | a95fd4c43d39d3e4ee0d81b869f61d584dd17e00d7056e32044c45f94d1559ea |
| Rouaix HAL author-manuscript PDF, Rouaix_28516.pdf | 624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446 |
| Current status | 787c80242d7690dbe8cee7b990586c5da0940aa62968903e27686d563befe9b9 |
| docs/VALIDATION.md | 1cfe09383776953eab9716e146c026e32038b1637abf4f4bcd2528713106bdfb |
| docs/REFERENCES.md | b4c434b80accdb3c932917eff9371a33a4c289b61821aac860b32b58ba85c4dd |
| docs/COMPUTE.md | 0fb3f0a76571f4fc9fb14ae8414d7a265ad41713ccd8725e545ca6ec143ea0e7 |
| scripts/run_local.py | 13e3d2fd6fcebe58ad623af339de36ed4d29f842b7588c18c59e750ae16d73db |
| Warden checkpoint 11, rank 6 | 89a2e1e310f25650aaa6ec58d6960b49c6793f4b63b37c8200bba2854ee1db6c |
| E1 static package review | f9eeb5df39f512760a95bb354dd8157b8867fad19b04a492b2d86aa01d0b7951 |
| E1 static package follow-up | 9451052a90ca338501ead2b92658d4b53f83e33fbc35300cb4cdb0f591cef847 |
| E1 gate review 4 | 7c01b1262d305e3c131bb40f5cb43f0c9cc276d0b851002f1ffdffdaf39fcdbb |
| E1 static correction exact review | 49b26e05aa794ee613e1c861d0bba996bcf44915402cdf9cd4065930f3207f94 |
| E1 static correction integration receipt | a71ebe32e8158843dcbc5f32c9a6dee527032aadef12cb4ddef197260663291c |
| E1 primary wall disposition | 181ee1644d8611fac003f22eeddc161eaaaac1bea17987c1d709202ed90a7d18 |
| E1 inventory primary correction | 0cea2c34c6e1f74997e5c0c655d3243ed74eb55caefe5f520b2414a6e3f39fba |
| E1 inventory exact follow-up | 1351683ae2fce519f2844c59172e9c8c7d04fd9b2ee1d5e3c295f082b0538667 |
| Accepted alpha capture map | c0e8e1d3f51e3b0ac683039443a59a5fd07ad0f64656fcb488df469ce33abefd |
| 20-file static package manifest | 3cbc0528bc8b2d9feb35529e85d5bd1b247c92e4f7f28345f53db1ba462cfb8e |
| Current candidate case/0/nut | c9c0b1af876a5252d23f0df5916226d7f1c64fde4f7e36f343ecdebdccdca397 |
| Current candidate case/0/alpha.water | 4e5d4735a7b55dbdfa9b9e4630df2f0c7bf53cfcf5f2a07cfd7d056bd6ead4c8 |
| Current candidate case/0/p_rgh | 990ff353a32cd9fbd69dbd5d22a8eee69e923878e0b60e95d61774220f829ddd |
| Current candidate case/0/k | d845e4719b888adbf5754042ebbdeeb373b9a8bc981ca7dfe3e8067915d31f76 |
| Current candidate case/0/epsilon | 0e7c9a81cad868c67d1534838599c220827613bc5a219a4fb865e813c51c8800 |
| Current candidate case/0/U | f02ff11e12ff1333b4941416f4aced63d9f246441ae2e475263fc59f1bc22ad8 |
| Current candidate setExprFieldsDict | 1feb5a66222198a2133b26353fd75dfeecdb9fa61e877be27d73df977ad5e891 |
| Current candidate constant/g and constant/hRef | 18f0445d263795f548dd7cbe066b74d4fa2458ede883efcd94d95f3c5a89d7d4; f2999e33aeeab37967b295381c225dcb2a0a0f8dbed45a7eb0e66e86867cca82 |
| Current candidate turbulenceProperties | c6a7d91e95eff3464545922a9baaab454a7da870fbefffc05640fb6c63d4f3ab |
| Current candidate fvSolution and controlDict | 659c430963f5516bb7efc2abc6f5dfb84c3bc2a20129ba1dbee51eac0ea8736a; 3b3459266f02120cd6b13d4043c92aa94fe2baf01622f95c3bdde9fdd4db7c1d |
| Current candidate assumed geometry files | ac4d4ec27ba588e8337d018a781d27ac7d3d33f8dd19b7ec1b6171daeadb5c8c; c0e2142b0d9a5eb2de1b6e678fe34822011df6db1311892b0d517f7549ad1248 |

The following source hashes were recomputed from the pinned v2512 image. The listed source line numbers are therefore bound to the image ID above, not to a mutable web page:

| Pinned source file and relevant lines | SHA-256 |
| --- | --- |
| src/transportModels/interfaceProperties/alphaContactAngle/alphaContactAngleTwoPhaseFvPatchScalarField.C:35–45,126–151 | a90fcfeb219518bf4f25fdc39d4a15da272de0a21452226850e80c8a86a2e781 |
| src/transportModels/twoPhaseProperties/alphaContactAngle/constantAlphaContactAngle/constantAlphaContactAngleFvPatchScalarField.C:48–60,102–120 | 49eb345b942a0952b8f63cf9b363c9f64826eb6b9d59c20d1f014c646579d812 |
| src/TurbulenceModels/turbulenceModels/RAS/realizableKE/realizableKE.C:76–87 | d278018ca7b18698d91e3beb248522e92101300304f3a41ecefdf325a62c5bcb |
| src/TurbulenceModels/turbulenceModels/derivedFvPatchFields/wallFunctions/nutWallFunctions/nutkWallFunction/nutkWallFunctionFvPatchScalarField.C:243–292 | 0dc183bec3b00091216ecbf747d45ba0dd59c5f7676135d1fab741ec340915e9 |
| tutorials/multiphase/interIsoFoam/weirOverflow/0.orig/nut:23–45 | 18a57ea1d8629b3fb53a35a6849b93cc10775cd51161ec663eb445733f509608 |
| src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvectionTemplates.C:491–515 | 1d704aec280cffa4302f75cc3e15654db25dc75c6d1cb9e230ab8a4be64f1e90 |
| src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvection.C:625–652 | c2ed42ee16632e77b8aad9ff2adc87214cfd5c0a1b94387644e51aa2835b6380 |
| applications/solvers/multiphase/interIsoFoam/alphaEqn.H:8–23 | cbb4348977388633b29f0aa1f612225249c3062e80755f548fddfb0760c7311f |
| applications/solvers/multiphase/interIsoFoam/alphaEqnSubCycle.H:1–48 | b5f9845d57cb3fc75577ef00ed338186f83d13a9261c67d4ef88e6f1ef419385 |
| src/finiteVolume/fields/fvPatchFields/derived/prghPressure/prghPressureFvPatchScalarField.C:136–161 | 672bc7535cf6fd76357ebf311ca747c44ab221f2cca36a8bea5c511404c7577a |

**Inspection record:** pinned-image source listing, hashes, and line reads ran serially through scripts/run_local.py with Docker <code>--cpus=1 --memory=4g</code>. I also read the local author manuscript pages with pdftotext and hashed the source and project artifacts. No mesh utility, solver, characterization, GPU job, or test suite ran. No shared plan, status, contract, source, or solver file was edited.
