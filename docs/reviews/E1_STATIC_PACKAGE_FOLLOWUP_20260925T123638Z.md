**E1 exact-artifact follow-up — 2026-09-25 12:36:38 UTC**

**Disposition: REVISE for static-package readiness.** The five earlier findings are resolved in the corrected dictionaries and narrow wall amendment, subject to the remaining provenance and validation fixes below.

This is an independent Astra Max artifact review, separate from Warden checkpoint 9. I inspected files and hashes only. I did not edit, run tests, invoke the generator, launch Docker, build, mesh, execute a solver or use the GPU.

**Required corrections**

1. **M1 — Conflicting source identity is embedded in generated geometry.**  
   [prepare_case.py:735](/home/v/proj/bene/fire-track2/cases/e1_rouaix_case1_static/prepare_case.py:735) emits the wrong PDF hash into [domain.json:13](/home/v/proj/bene/fire-track2/cases/e1_rouaix_case1_static/geometry/domain.json:13). The same wrong hash appears in the [preparation note:101](/home/v/proj/bene/fire-track2/experiments/E1_ROUAIX_CASE1_STATIC_PREPARATION.md:101):

   - Incorrect: `624efe9ee2aec11b85624e9e2ac5364802b12c42657711d211e625052cf28446`
   - Correct: `624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446`

   Both local PDF copies independently hash to the correct value. The source note, checker constant, preparation-note opening and `domain.json`’s other source field already use it. Thus this is a concrete package defect; a passing file manifest preserves the conflicting provenance.

   Use one pinned source identity for both generated fields, check their agreement, and add an isolated mismatch fixture. Correct the note and regenerate the geometry/manifest. Required affected files are `prepare_case.py`, `static_preparation.py`, `geometry/domain.json`, `CASE_SHA256SUMS`, the focused test, the preparation note, and the primary wall-disposition memo because it embeds the preparation-note hash. Refresh the note’s manifest hash as well. Current identities are inventoried below.

2. **M2 — The wall-node validator accepts positive infinity as a height.**  
   [static_preparation.py:1019](/home/v/proj/bene/fire-track2/cases/e1_rouaix_case1_static/static_preparation.py:1019) bounds `x` and `z`, but checks `y` only with `float(row["y_m"]) >= 0.0`. By inspection, `+inf` satisfies that condition; arbitrary positive heights also escape the declared amplitude.

   Require finite coordinates and `0 <= y <= A` with an explicitly justified serialization allowance. Add independent nonfinite and out-of-range geometry fixtures. Exercise the geometry belonging to the fixture package: the current function reads geometry through global `PACKAGE_DIR` even when given another `case_dir` at lines 975–1015. This finding concerns validation coverage; it does not establish that the current finite wall data are invalid.

**Small follow-up corrections**

- **Isolate the nesting regression.** [tests:198](/home/v/proj/bene/fire-track2/tests/test_e1_rouaix_case1_static.py:198) moves the already invalid `plicRDF` block outside `solvers`. The resulting fixture violates both requirements, so it cannot independently demonstrate nesting rejection. Construct it from `original_solution` with valid `isoAlpha`, retaining the separate wrong-method fixture. The current checker itself does inspect the nested block.
- **Align current provenance labels and review history.** The generated wall classification at `prepare_case.py:732` / `domain.json:11` still says “inferred schematic reconstruction.” Prefer “assumed analytic wall; not source-derived geometry,” consistent with the amendment. The preparation note at lines 29–33 also says neither gate nor audit was edited; distinguish the original review-4 gate hash from the current primary-amended gate. The unchanged capability audit contains historical no-case/trace language at lines 3, 22, 59–61 and 191; identify that as predecessor evidence in the current note rather than treating it as current package status.

**Disposition of the five previous findings**

| Previous finding | Follow-up disposition and evidence |
|---|---|
| Density selection and schemes | **Resolved at static scope.** `turbulenceProperties:18` sets top-level `density variable`; `fvSchemes:27–30` supplies the three `rhoPhi` convection entries and exact `div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;` key. Generator and omission fixtures are aligned. |
| Alpha nesting and reconstruction | **Resolved by inspection.** `fvSolution:38–48` places `"alpha.*"` inside `solvers`, selects `isoAlpha`, and retains clipping, disabled snapping and one subcycle. Improve the isolated nesting fixture as noted above. |
| Plane interpolation | **Resolved.** All 30 declared station planes in `controlDict` enable `interpolate true` and triangulation, with `cellPoint` interpolation. The checker examines each plane and the negative fixture removes an individual entry. This matches the point-interpolation distinction in the [v2512 sampledPlane API](https://api.openfoam.com/2512/classFoam_1_1sampledPlane.html). |
| Assumed wall versus Figure 3 trace | **Amendment acceptable for static assumptions only.** Gate lines 125–138 and the primary memo explicitly adopt the Gaussian surface and all three parameters as assumptions. The inspected Figure 3 render supports domain dimensions, not a recoverable quantitative wall profile. Correct the conflicting provenance above. |
| Boundary-only nozzle selection/order | **Resolved at dictionary scope.** `topoSetDict:19–32` first selects `aircraftWall`, then intersects with the finite cylinder. `createPatchDict:20–23` consumes that set. The declared order is `blockMesh → topoSet → createPatch → snappyHexMesh -overwrite`. Actual face count, projected aperture, area and normals remain future mesh evidence. |

**Other reviewed evidence and limits**

The 20-file output declaration, fixed manifest order and refusal of unknown paths replace the earlier open-ended manifest generation. The test source compares two generations’ file and manifest bytes and checks preservation of unknown content. I independently read the current file inventory and rehashed all 20 artifacts; their identities match the manifest and remained unchanged. I did **not** independently regenerate the package. The reported 13 focused tests, Ruff and write/no-write checks remain author/primary evidence.

The numeric helpers now reject the earlier nonfinite contour/score inputs and nonpositive volumes; pressure reconstruction, alpha summaries and correction totals have finite-result checks. These remain static fixtures, not a reviewed runtime monitor. The geometry exception above remains.

Material conversions, coordinate signs, nominal inlet integrals, initial air-only fields and hydrostatic pressure formula are consistent across the reviewed declarations. The uniform-zero `p_rgh` remains explicitly a seed requiring later mesh-based initialization. Nominal circular area is not a measurement of the selected faceted nozzle.

The alpha map preserves preclip, postclip and solver-final states, keeps clipping and later corrections separate from transported `alphaPhi_`, and does not claim instrumentation exists. Capability statements rely on the archived audit and its pinned image:

`sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`

The preparation note records upstream source paths and hashes, but a separately archived source-excerpt bundle was not available for fresh verification. I did not launch the image or independently rehash its source bodies. That limits source-verification claims without blocking this bounded static review.

**The amended wall does not release meshing, characterization, E1 execution or Figure 13 comparison.** The primary memo at lines 17–22 explicitly preserves those boundaries. D-NUT-BC, contact-angle selection, mesh/initialization evidence, instrumentation, the characterization contract and scientific acceptance decisions remain separate. This review provides no E2 advancement or other scientific-gate approval.

**Exact reviewed identities**

For every entry below, **opening SHA-256 = closing SHA-256**. Closing observation was **2026-09-25 12:36:38 UTC**. Paths are repository-relative unless absolute.

| Control/source artifact | Opening and closing SHA-256 |
|---|---|
| `cases/e1_rouaix_case1_static/prepare_case.py` | `2f31be31789c97a0ba4446aa6378640b024c870f5429eb010915bc4969cf523a` |
| `cases/e1_rouaix_case1_static/static_preparation.py` | `cac2e57e6b199ef961f312a115657849b25ded9d0a9fd0653b4a3531c8625acb` |
| `cases/e1_rouaix_case1_static/CASE_SHA256SUMS` | `291c9c48733c3500954a75ed3e172a3185e0be4fe4dbe20ed2ba27d790cedbcd` |
| `cases/e1_rouaix_case1_static/ALPHA_CAPTURE_MAP.md` | `c0e8e1d3f51e3b0ac683039443a59a5fd07ad0f64656fcb488df469ce33abefd` |
| `tests/test_e1_rouaix_case1_static.py` | `342d68113dfdc439d77069a85e5e411fc588f8af6e9b5070d84eb9b2f0e0305e` |
| `experiments/E1_ROUAIX_CASE1_STATIC_PREPARATION.md` | `ac47a5fabb9431b26b285647fd26f7715f318a58959d3fe9c1551e622e6618f4` |
| `experiments/E1_ROUAIX_CASE1_GATE_DRAFT.md` | `28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7` |
| `experiments/E1_ROUAIX_CASE1_SOURCE.md` | `a95fd4c43d39d3e4ee0d81b869f61d584dd17e00d7056e32044c45f94d1559ea` |
| `experiments/E1_CPU_SOLVER_CAPABILITY_AUDIT.md` | `a6c655abbf58eff6bb71850fbed8612ece459c891ad9e21b4f5d3ddf7e7fcb32` |
| `docs/reviews/E1_WALL_AMENDMENT_PRIMARY_DISPOSITION_20260925T120700Z.md` | `181ee1644d8611fac003f22eeddc161eaaaac1bea17987c1d709202ed90a7d18` |
| `docs/reviews/E1_GATE_REVIEW_4_20260925T095700Z.md` | `7c01b1262d305e3c131bb40f5cb43f0c9cc276d0b851002f1ffdffdaf39fcdbb` |
| `docs/reviews/E1_STATIC_PACKAGE_REVIEW_20260925T110157Z.md` | `f9eeb5df39f512760a95bb354dd8157b8867fad19b04a492b2d86aa01d0b7951` |
| `data/derived/rouaix_e1_case1_fig13.csv` | `c55b7985adf584d1f8815d22d01c21cca6660f4c637da220009d9f44b5b719f7` |
| `/tmp/Rouaix_28516_e1_static.pdf` | `624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446` |
| `/tmp/Rouaix_28516.pdf` | `624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446` |
| `/tmp/rouaix_figure3_page7.png` | `12cd10ef2d1cb06b397dcc2fa81e83067a83bf8f7be5eca64a2d302fa2291726` |

All paths in the following table are relative to `cases/e1_rouaix_case1_static/`.

| Manifest-listed artifact | Opening and closing SHA-256 |
|---|---|
| `case/0/U` | `f02ff11e12ff1333b4941414f6aced63d9f246441ae2e475263fc59f1bc22ad8` |
| `case/0/alpha.water` | `4e5d4735a7b55dbdfa9b9e4630df2f0c7bf53cfcf5f2a07cfd7d056bd6ead4c8` |
| `case/0/epsilon` | `0e7c9a81cad868c67d1534838599c220827613bc5a219a4fb865e813c51c8800` |
| `case/0/k` | `d845e4719b888adbf5754042ebbdeeb373b9a8bc981ca7dfe3e8067915d31f76` |
| `case/0/nut` | `c9c0b1af876a5252d23f0df5916226d7f1c64fde4f7e36f343ecdebdccdca397` |
| `case/0/p_rgh` | `990ff353a32cd9fbd69dbd5d22a8eee69e923878e0b60e95d61774220f829ddd` |
| `case/constant/g` | `18f0445d263795f548dd7cbe066b74d4fa2458ede883efcd94d95f3c5a89d7d4` |
| `case/constant/hRef` | `f2999e33aeeab37967b295381c225dcb2a0a0f8dbed45a7eb0e66e86867cca82` |
| `case/constant/transportProperties` | `be3f42f6560eb19392aca767168a97e38223646dcb301b3d3b6b71e8565dd24f` |
| `case/constant/turbulenceProperties` | `c6a7d91e95eff3464545922a9baaab454a7da870fbefffc05640fb6c63d4f3ab` |
| `case/system/blockMeshDict` | `862fbddb36b2039c0a706df895ab5dd185c0a6a9f7500ccc03c6a2f1fcf9d0a2` |
| `case/system/controlDict` | `3b3459266f02120cd6b13d4043c92aa94fe2baf01622f95c3bdde9fdd4db7c1d` |
| `case/system/createPatchDict` | `470351b42265a2e3e0a759deedf988229661838600530444067c676deb118de9` |
| `case/system/fvSchemes` | `bd6c0ae56cc2582376268256f71c7d77500f3918cdfec98bf205fffac58a6287` |
| `case/system/fvSolution` | `659c430963f5516bb7efc2abc6f5dfb84c3bc2a20129ba1dbee51eac0ea8736a` |
| `case/system/setExprFieldsDict` | `1feb5a66222198a2133b26353fd75dfeecdb9fa61e877be27d73df977ad5e891` |
| `case/system/snappyHexMeshDict` | `696b0c3f1bff22ad58b6511e6ea14e8d56a0b15b7325b595a1d38c6b823fea97` |
| `case/system/topoSetDict` | `b6a53014f1f2ebb3740a77c581a55321cf33f2bfda06697bed5f1652dccd133b` |
| `geometry/domain.json` | `b15391274f9796266a2a15b4b2707d74d0febef4657d148fb07ad69bd6a0f7fa` |
| `geometry/top_wall_nodes.csv` | `c0e2142b0d9a5eb2de1b6e678fe34822011df6db1311892b0d517f7549ad1248` |

After correction, provide regenerated identities, focused negative-fixture results, the updated embedded hashes and a finding-by-finding response for a bounded exact-hash follow-up.
