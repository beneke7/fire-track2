# Project status

Updated: 2026-09-27 UTC. Latest result and solver comparison:
[`VOF trial results`](../results/VOF_TRIALS_2026-09-27.md). The one-second
still-air OpenFOAM run completed on CPU with the declared mesh and Courant
limits; its sampled source/inventory/outflow ledger closes within 0.1%.
This remains exploratory because geometry, discharge and turbulence inputs are
provisional and there is no mesh or model sensitivity study. A repaired
CaNS-Fizzy THINC/QQ build passed the upstream rising-bubble contour criterion
on the RTX 5090 after fixing an uninitialized interface-width value. This is a
solver benchmark, not a four-slot source run. The pipe preview is
[`available here`](../results/restas-still-air-alpha65-1s-preview.mp4).
No E1–E6 validation gate changed. The detailed queue snapshot below is from
2026-09-25 and is retained as historical checkpoint context, not a live queue.

Updated: 2026-09-25 15:08 UTC. The candidate5 successor passed one
source-disabled GPU regression after exact Astra eligibility review. It
verified OpenACC, CUDA-buffer MPI and the upstream rising-bubble check through
3 s; it used no `source-boundary.in` and closes only that software-runtime
checkpoint. Exact review and immutable smoke evidence are linked below.
B1-pre/B2, source execution and scientific gates remain closed. Since the
14:25 snapshot, the candidate6 two-halo H4 regression passed and Astra Max
accepted its exact follow-up at bounded host-test scope. A separate audit
extracted and hash-checked all 29 DNS and 8 VOF records across the five
allowlisted fixture triplets. The primary has added the proposed H3 input
schema annex to v0.3. Candidate5 production-arithmetic evidence is complete
and its 403-entry checksum inventory passes; exact Astra review is now active.
The H7 code audit is complete, with implementation and lifecycle tests still
open. Warden 13 is complete and archived; its sequencing recommendations are
accepted without changing any gate. Luna's H5 raw-roster audit is active. An
additional Astra E1 packet review was refused by the agent thread limit and
will be dispatched when a reviewer slot releases. The RTX 5090 was idle at
15:08 UTC; no source GPU trial or scientific gate has been added.

The corrected E1 static artifacts and factual gate inventory are accepted at
their narrow reviewed scope. The exact follow-up is
[`E1 inventory follow-up`](reviews/E1_GATE_INVENTORY_EXACT_FOLLOWUP_20260925T1320Z.md),
SHA-256 `1351683ae2fce519f2844c59172e9c8c7d04fd9b2ee1d5e3c295f082b0538667`.
The E1 gate remains NOT READY: no mesh or solver run is approved. D-NUT-BC,
contact angle, instrumentation, mesh/initialization and characterization
approval remain open. E2 implementation review is accepted, while its protocol
and scientific release remain open.

Candidate5 analyzer M1/M2 exact review is complete at narrow scope:
[Astra exact review](reviews/FLUTAS_ANALYZER_REPAIR_EXACT_REVIEW_20260925T1331Z.md),
SHA-256 `b5606ebce5fea7e89f384a623f3e4a22ee6d236723fbca72eb9894e4eab6dd09`.
The F1 repair is closed for exact hashes after independent Astra review:
57 tests, Ruff/format, and 42 literal phase/velocity cases passed. This closes
malformed-summary evidence only, not source-input binding or production B2.
The successor build, exact review and one eligible source-disabled GPU smoke
are complete. The primary v0.1 source-release contract review returned REVISE
at
[`source-release review`](reviews/FLUTAS_SOURCE_RELEASE_CONTRACT_REVIEW_20260925T1331Z.md),
SHA-256 `058a3d83de7c326f5f51ac8af58d54f8f0f4c28db20a595343fafb9f2df3d336`.
It found concrete output-prefix, inherited-ledger/time, strict-parser, `dzf`
indexing, raw-evidence, OCI-receipt, source-locator and first-run
resource-limit blockers. Astra Max Warden 12 reviewed the exact v0.2 proposal
hash `8965b0c1d58ba53252659d53ff7fcc0bd9fb41a2f82aeec4a65ea39d49281b32` and
found remaining prefix, typed-input/raw-schema, zero-rule, provenance and
resource-monitor contradictions. Preserve v0.2 as the reviewed proposal
snapshot; the primary is preparing v0.3 before a separate exact contract review.
No measured Restás data are required for these engineering fixes.

The earlier Astra Max deblocker memo remains archived at
[`DEBLOCKER_PLAN_20260925T1229Z.md`](reviews/DEBLOCKER_PLAN_20260925T1229Z.md)
(SHA-256 `48a8aeb1f9e828577d24ee6f152490f7481ce18367751e15c6ec2055928438c8`).
The project Warden is the Astra Max `project_warden` role, configured read-only
at max reasoning. Warden 11 is archived at
[`PROJECT_WARDEN_20260925T1340Z.md`](reviews/PROJECT_WARDEN_20260925T1340Z.md),
SHA-256 `89a2e1e310f25650aaa6ec58d6960b49c6793f4b63b37c8200bba2854ee1db6c`.
Warden 12 is complete at
[`PROJECT_WARDEN_20260925T1403Z.md`](reviews/PROJECT_WARDEN_20260925T1403Z.md),
SHA-256 `6a1a4221a354e6bbc18c8ef69d56ec2e4a916ac83e97377c6b758935adef875f`.
The primary accepts its interface-correction checklist, current-queue refresh,
no-repeat smoke decision and role-rotation recommendation. It approves no
candidate, contract, launch or scientific gate. The focused Astra Max deblock
plan is
[`BLOCKER_RESOLUTION_PLAN_ASTRA_20260925T1615Z.md`](reviews/BLOCKER_RESOLUTION_PLAN_ASTRA_20260925T1615Z.md),
SHA-256 `dfc2a4012b982f498f08378032a133bd87b750150c5ced60dddc23eaec9a28cd`;
the primary accepts its ranked engineering assignments and continues to own
interfaces, integration and gate decisions.

Candidate6's Astra Max exact review is
[`FLUTAS_CANDIDATE6_H4_EXACT_REVIEW_20260925T1620Z.md`](reviews/FLUTAS_CANDIDATE6_H4_EXACT_REVIEW_20260925T1620Z.md),
SHA-256 `2341b9a361046fa6033740b0a8409fe979f197e1523578f3110d14c1b9527e13`.
It accepts the `dzf(0:)` correction for the pinned one-halo production caller
and exact patch application, but returns **REVISE** for aggregate H4 because
the two-halo harness still shifts indices and the candidate lacked permanent
positive/negative regressions. A compiled probe measured 20,064 kg with the
wrong whole-array call versus the expected 37,032 kg; explicit `dzf(0:)`
restored the checked results. The native build log records `sm_120.cubin`, but
the executable was ephemeral and no candidate6 image/receipt was retained.
No solver, source case or GPU runtime ran.

Candidate6's two-halo successor is now accepted at bounded H4 regression
scope by Astra Max:
[`two-halo exact review`](reviews/FLUTAS_CANDIDATE6_H4_TWO_HALO_EXACT_REVIEW_20260925T1445Z.md),
SHA-256 `176475954e7540739b7267f0a6d54cf6e298624dfb0141e7d5fa36616c3bf2d4`.
The retained test passes nonuniform two-halo `dzf(0:)` calls and demonstrates
the whole-array shifted-index negative control; 600 emitted CSV values were
independently recomputed. This closes aggregate H4 for the bounded helper
scope only. The historical candidate5 full validator remains unsafe to reuse
with candidate6 without adapting its whole-array calls; the failed Python
oracle snapshot was not retained. No production-flags review, source runtime,
image/receipt or GPU eligibility follows from H4 acceptance.

Astra Max accepted candidate5 schema 1.2 as an implementation interface at the
exact hash `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`;
see [the review memo](reviews/FLUTAS_CANDIDATE5_SCHEMA_REVIEW_20260925T115737Z.md).
That does not accept the producer, analyzer, B1-pre, B2, or a source run. The
candidate5 producer/build handoff and exact review are complete at bounded
implementation scope; the successor smoke passed. The inherited manifest run
skipped one schema-dependent fixture, while the external pinned-schema rerun
passed all four; the first NVHPC build failure is preserved and the retry
produced `sm_120.cubin`. The local image still lacks retained OCI provenance
and `candidate-build.json`. Analyzer M1/M2/F1 repairs have narrow exact
acceptance, but production B2 remains blocked until scan and timestep inputs
derive from staged bytes, the six inherited ledgers have an independent
auditor, raw evidence and limits are frozen, and the source supervisor passes
exact review. Candidate4 remains historical source-disabled evidence;
candidate5 source execution is also gated.
The E5 source extraction is complete: six Gu Table 4/5 conditions were
transcribed with Table 5 bias arithmetic independently checked. The source
record and CSV are
[`E5_GU_AG600_SOURCE.md`](../experiments/E5_GU_AG600_SOURCE.md) and
[`gu_ag600_table4_table5.csv`](../data/derived/gu_ag600_table4_table5.csv);
raw cup data and release traces remain unavailable, so this is source
preparation and not an E5 simulation or validation result.

The frozen 50 m/s crossflow fixtures have a known U0 timestep-guard rejection:
`dt/dtmax=0.20003689638113265` versus factor `0.2`. The primary retains
`dry_crossflow` and `crossflow_four` as negative guard fixtures. Positive
crossflow qualification requires an independently reviewed prospective
protocol amendment preserving or redeclaring pulse duration, dose and horizon;
no crossflow source run is authorized.
Scientific pipeline progress is 1 of 7 E0–E6 gates complete (about 14% by gate
count only; it is not a weighted measure of validated simulation progress).
Candidate2 compiled and passed ten static/analytic checks, but Astra Max found
three source defects: the mandatory dry case fails validation; the active
bottom return leaves periodic momentum-stencil halos inconsistent; and the
first interval after source shutoff can use stale liquid ghosts and VOF
reconstruction. Candidate2 is preserved exactly; candidate3 work is isolated.
Its 13 Python static/analytic checks and five host-only Fortran behavior modes
pass. The first `cc120` build failed on managed-attribute mismatches, and the
second successful attempt included ignored bytecode in its input hash list.
The authoritative third build is cleanly recorded with source patch SHA-256
`055758a2690fe4bb9003bdc54665cbc63f67e490f8bd1e307d71ca6d013a4319` and image
`sha256:90f1261308ab56e52ee29d129deefad86a19b352cef79b43feca08df6762e1c3`;
see [build metadata](../containers/flutas/candidate3/evidence/runs/20260925T082315Z-1955187/metadata.txt).
Astra Max's exact-hash review accepts candidate3 for a separate
source-disabled GPU regression only. That regression passed the OpenACC smoke,
CUDA-buffer MPI smoke, and upstream rising-bubble verification; it used no
`source-boundary.in` and does not test a source boundary. Evidence is in
[`candidate3 GPU regression`](../results/runs/flutas-candidate-gpu-regression-20260925T083856Z-1977448/exit-status.txt).
Its 25-second bundle did not sample runtime RAM/VRAM peaks; the limitation is
recorded in that bundle. No source-enabled GPU run or source CFD has occurred.
Candidate4 is now frozen after its two-CPU-capped CPU build. The exact patch
SHA-256 is
`2eddbe5cc406ecbc60e7ca1fe9ba3a5ff61b130283e74772b1593f1d385959ff`; image
ID is `sha256:3086f0312b3a74dd7d0f03102d4b8584a8dd1fe4091364615cb0e580f00283bb`.
Its build record shows 14 Python checks, eight host behavior/ledger modes,
unsupported-input rejection, flushed failure-rate evidence and `sm_120.cubin`;
see [candidate4 build evidence](../containers/flutas/candidate4/evidence/runs/20260925T091602Z-1994261/metadata.txt).
The exact Astra source review accepts candidate4 for a bounded source-disabled
GPU regression after runner fixes. The repaired runner passed its independent
Astra review and one candidate4 smoke passed with the immutable image and patch.
Evidence is in
[`candidate4 GPU regression`](../results/runs/flutas-candidate-gpu-regression-20260925T095317Z-2015705/exit-status.txt):
OpenACC, CUDA-buffer MPI, and upstream bubble all passed through `3.00152 s`,
`True True`; no `source-boundary.in` was present. Thirteen GPU and eleven
container CPU/memory samples parsed successfully; sampled maxima were 668 MiB
GPU memory and 326.8 MiB container memory (not hardware peaks). A shutdown-race
`docker stats` no-container message is retained after container removal; all
runtime samples were valid. This is a source-disabled regression, not source
behavior or scale evidence. The candidate review also limits Courant
equivalence to the uniform fixture and keeps all source execution closed; see
[candidate4 independent review](../containers/flutas/candidate4/INDEPENDENT_REVIEW.md)
and [runner review](reviews/CANDIDATE4_GPU_RUNNER_REVIEW_20260925T095200Z.md).
The CPU capability audit found OpenFOAM v2512 viable for an explicitly
approximate E1 comparison, with material model/geometry/turbulence gaps. The
fourth Astra Max exact-hash E1 review accepted the gate/audit pair for static
preparation only; it did not approve characterization or E1 execution. Its
alpha-stage naming recommendation is resolved in the current
[`ALPHA_CAPTURE_MAP.md`](../cases/e1_rouaix_case1_static/ALPHA_CAPTURE_MAP.md)
and the E1 decision packet: the active names are `alpha_preclip`,
`alpha_postclip`, and `alpha_solver_final`. Older gate/audit prose retains
predecessor labels and must be reconciled prospectively before instrumentation
is frozen. See [`E1 review 4`](reviews/E1_GATE_REVIEW_4_20260925T095700Z.md).
Neither E1 nor E2 is approved for execution. The initial review is archived in
[`E1_GATE_REVIEW_20260925T0806Z.md`](reviews/E1_GATE_REVIEW_20260925T0806Z.md).
The second review is archived in
[`E1_GATE_REVIEW_2_20260925T085302Z.md`](reviews/E1_GATE_REVIEW_2_20260925T085302Z.md).
The exact candidate2 findings are recorded in
[`INDEPENDENT_REVIEW.md`](../containers/flutas/evidence/source-candidate-runs/20260925T073740Z-1880163/INDEPENDENT_REVIEW.md).
The full validated aircraft-to-ground simulation objective remains open.

Completed P1 run: `results/runs/restas-source-ledger-20260925T015720.514566Z-8e93eda1`
(`make restas-source-ledger`, 16 MPI ranks, 48 GiB memory cap, 3,600 s solver
wall limit). It reached 0.12 s in 2,200.9 s; all stage and runner exits were 0.
The automated report and independent raw flux/inventory audit pass every P1
gate. Keep this bundle and the revision-1 run immutable.

## Established

- The eight supplied PDFs remain unchanged. The plan now distinguishes E2's
  quantitative dilute-envelope curves from descriptive core morphology and
  records E4's cross-track-sum definition for `Vx`. The plan, paper inventory
  and validation contracts are documented in
  [`REFERENCES.md`](REFERENCES.md), [`VALIDATION.md`](VALIDATION.md), and
  `track2_aerial_drop_experiment_plan.md`.
- The repository has an orchestrator-led Luna Max workflow, immutable run
  directories, shared compute budgeting, a local launcher, resource doctor,
  experiment templates and scientific-review handoffs in
  [`WORKFLOW.md`](WORKFLOW.md) and `AGENTS.md`.
- The E0 analytical foundation passed an independent scientific review. The
  initial seven report checks passed; see
  [`results/E0_INITIAL.md`](../results/E0_INITIAL.md). During this continuation,
  `make check` passed Ruff, formatting and all 118 tests; a fresh `make e0` run
  passed all seven analytical checks. The latest doctor snapshot reports 20
  effective CPUs, 118.5 GiB available RAM, 260.9 GiB free disk, and an RTX 5090
  with 31.8 GiB. Host `nvcc` remains absent. A separate digest-pinned NVIDIA
  HPC SDK 26.9 container built FluTAS for `cc120,cuda13.3` and passed the
  OpenACC, CUDA-buffer MPI and upstream rising-bubble checks. The GPU pilot
  remains closed pending the project slot-source diagnostics.
- Denner (2026) isolated-water-drop momentum and breakup relations (PDF p. 3,
  Eqs. 1–11) now have a fixed-step RK4 component with event termination at
  predicted breakup or ground impact. Eleven focused tests verify the printed
  correlations, direct drag acceleration, an independent terminal speed, the
  ballistic limit, event handling and input validation. These are equation/numerical checks,
  not validation against Denner's coupled evaporation results or measurements;
  the fixed-radius component does not represent the dense Restás plume. See
  [`Region C isolated-drop foundation`](../experiments/REGION_C_DENNER_ISOLATED_DROP.md).
- A provisional four-slot OpenFOAM `interIsoFoam` case now runs in the local CPU
  container. It completed 0.12 simulated seconds on the recorded 2,081,200-cell
  mesh, and `checkMesh` reported `Mesh OK`. This is not the GPU pilot and is not
  a paper benchmark or design prediction.
- The run bundle
  `restas-cpu-vof-20260924T222240.919816Z-49f65225` has the logs, fields and
  machine-readable report in the ignored local `results/runs/` tree. Its
  tracked summary and render are in
  [`results/P0_RESTAS_CPU_VOF.md`](../results/P0_RESTAS_CPU_VOF.md) and
  [`the 0.080 s frame`](../results/P0_RESTAS_CPU_VOF_0p08s.png).
  It used 16 MPI ranks, 975.6 s wall time, sampled a 5.55 GiB memory peak, and
  advanced at 0.443 simulated seconds per wall hour. The report recomputes
  hashes for the 16 retained case-input files because this first run's manifest
  left that field empty; the runner has been fixed.
- The pilot recorded a water-volume discrepancy: 0.231019355 m³ at 0.119177 s
  versus the intended 0.2304 m³ rectangular source integral (+0.269%). It first
  appeared at the adaptive step crossing the nominal 0.08 s source cutoff. The
  case did not save per-slot liquid boundary-flux histories; no acceptance
  tolerance was preregistered. The discrepancy is not a passed conservation
  gate. See [`P0_RESTAS_CPU_VOF.md`](../experiments/P0_RESTAS_CPU_VOF.md).
- The solver's logged global and interface Courant maxima were 0.5417 and
  0.2926, above the configured 0.5 and 0.25 limits. It reached its end time
  without a fatal error, but stability/configured-limit compliance was not
  established.
- P1 revision 1 completed a 0.12 s source-event and box-ledger run, but its
  preregistered per-slot source-dose gate did not pass. The retained run
  `restas-source-ledger-20260925T003321.108356Z-1927f2fd` contains 1,200 aligned
  rows for all seven patch fluxes and water inventory, reaches the 2,081,200-cell
  mesh final time, and remains a provisional diagnostic. `alphaPhi_` integrates
  to 57.636 kg/slot (230.544 kg total), 0.125078% above revision 1's frozen
  right-endpoint target of 57.564 kg/slot (230.256 kg total). `phi` matches that
  right-endpoint dose; `alphaPhi_` reflects the left endpoint of each completed
  time step through shutoff. Independent audits support a prospective protocol
  amendment with a 57.636/230.544 kg left-step target, but the old run
  stays failed under revision 1; the 0.1% tolerance is unchanged and the
  continuous 57.6/230.4 kg target remains a separate check. The box residual is
  about `7.2e-12 kg`; global/interface Courant maxima are 0.23044/0.14367. The
  run used 16 MPI ranks, 2,199.1 s wall time and a sampled memory peak near
  5.6 GiB under the 48 GiB cap. Its original report could not locate OpenFOAM's
  `0.000000` output directories and the legacy manifest did not preserve raw
  `interIsoFoam` status. The analyzer now finds one numeric time directory
  fail-closed; the launcher records each case-stage status and overall command
  separately, and the old bundle cannot become eligible for revision 2. The
  independent protocol review approved amendment 1 with revisions and approved
  the exact current launcher/analyzer hashes. A fresh revision-2 confirmation
  used clearly labelled provisional inputs, reached 0.12 s, and passes every
  automated P1 report check: `alphaPhi_` delivered 57.636 kg/slot (230.544 kg
  total), `phi` delivered 57.564 kg/slot (230.256 kg total), the maximum box
  residual was about `7.2e-12 kg`, and global/interface Co maxima were
  0.23044/0.14367. All five recorded case stages exited 0; runtime was 2,200.9 s
  and sampled memory peaked at 5.598 GiB under the 48 GiB cap. The independent
  raw-output audit confirmed the analyzer and all gates. The P1 result remains
  only a source/ledger diagnostic. See
  [`P1 protocol amendment 1`](../experiments/P1_SOURCE_EVENT_LEDGER_AMENDMENT_1.md),
  [`revision-2 result`](../results/P1_SOURCE_EVENT_LEDGER_REV2.md), and
  [`first-run audit`](../results/P1_SOURCE_EVENT_LEDGER_FIRST_RUN.md).
- The completed revision-2 P1 result remains unchanged. Astra Max prospectively
  reviewed the current Makefile and exact six-file local execution path; the
  active hash map now matches. The five focused test modules pass (59 tests),
  the real contract validator accepts the frozen limits and rejects a stale
  hash, regenerated inputs are byte-identical to the accepted bundle, and the
  local OpenFOAM image ID matches. P1 replay is ready but optional; no new
  solver run was launched for this recovery.
- Rouaix Case 1 Figure 13 now has two documented extractions: an SVG vector-path
  trace and a separate 600 dpi raster centerline trace. They reproduce within
  the combined extraction bounds. The paper's Section 4.3 relations are
  cross-case empirical fits, separate from Case 1 Figure 13; their residual
  scatter is not reported, so the residuals are a secondary consistency check
  rather than a demonstrated source contradiction. Figure 13's unstated
  sampling time, ambiguous width definition, q-level-only breakup marker and
  case-specific acceptance limits remain open. The independent E1 gate-draft
  review identified pressure-mapping, coordinate/origin, momentum-gate and
  E2-release defects; its findings are archived in
  [`E1_GATE_REVIEW_20260925T0806Z.md`](reviews/E1_GATE_REVIEW_20260925T0806Z.md).
  These defects and source ambiguities block a formal pass/fail comparison.
- The second exact-hash E1 review (see
  [`E1_GATE_REVIEW_2_20260925T085302Z.md`](reviews/E1_GATE_REVIEW_2_20260925T085302Z.md))
  also requires zero-safe absent-phase leakage rules, complete provisional
  initial/numerical conditions, a prospectively frozen curved-wall primary,
  a reviewed bounded-characterization sequence, sampled-state-only timing
  claims or output-cadence refinement, one aggregate score and status
  precedence, and raw alpha boundedness validity. Review 3 returned **REVISE**
  on density/convection pairing, missing contact-angle and solver controls,
  clipping-stage alpha checks, and stationarity precedence. The corrected
  proposal is frozen at gate SHA-256
  `15a9b4a48df3f8b059b98961d92cd89bdc8b69ffe1f66beaa81f936167ffe3ea` and
  audit SHA-256
  `a6c655abbf58eff6bb71850fbed8612ece459c891ad9e21b4f5d3ddf7e7fcb32`; Astra
  review 4 accepted this exact pair for static preparation only. It is the
  reviewed predecessor, not the current gate hash. Reviews 1–3
  remain archived, and the exact disposition is in
  [`E1_GATE_REVIEW_4_20260925T095700Z.md`](reviews/E1_GATE_REVIEW_4_20260925T095700Z.md).
  The correction labels density mode and boundary values provisional, adds
  `theta0`/`limit`, a GAMG smoother, explicit pre/post alpha stages and correction
  amounts, and keeps stationarity in descriptive/no-pass-fail status. Astra
  Max review 4 accepted this exact proposal as a baseline for static case,
  dictionary, geometry, mesh and sampler preparation only. It does not approve
  characterization, E1 execution, E2 advancement, or a scientific pass.
  Non-wall `nut` values remain a named preparation-owner decision due before
  characterization. The primary's wall amendment changes only static
  preparation. The amended gate and corrected inventory were exact-reviewed
  and accepted for static-preparation scope only; the current gate hash is
  `8e3efe6a3e7edb91985550ff5c285615e5b26f880e74415cb57962efdb7d9132`. Its scope is archived in
  [`E1_WALL_AMENDMENT_PRIMARY_DISPOSITION_20260925T120700Z.md`](reviews/E1_WALL_AMENDMENT_PRIMARY_DISPOSITION_20260925T120700Z.md).
  The corrected generated static case and sampler now exist; no mesh,
  characterization or solver run exists. The accepted current capture map
  uses `alpha_preclip`, `alpha_postclip` and `alpha_solver_final`; predecessor
  audit/gate prose still has older names and must be reconciled before
  instrumentation is frozen. No user-only data are needed for this provisional
  preparation. The exact disposition and archival Re wording erratum are in
  [`E1_GATE_REVIEW_4_20260925T095700Z.md`](reviews/E1_GATE_REVIEW_4_20260925T095700Z.md).
- The CPU route audit is complete at
  [`E1_CPU_SOLVER_CAPABILITY_AUDIT.md`](../experiments/E1_CPU_SOLVER_CAPABILITY_AUDIT.md).
  It confirms `interIsoFoam`, mesh and post-processing tools are available.
  The corrected generated E1 static case and sampler passed exact inventory
  follow-up for static-preparation scope only; no mesh, characterization or
  solver has run. The route is an approximation: isoAdvector
  differs from HRIC; the documented two-layer wall option does not combine
  with `realizableKE`; curved-wall/contact-angle and turbulence inputs need
  declared reconstruction; and recalculated `Re_j=4.489e6` differs by about
  9% from the paper's printed `4.9e6`. No E1 CFD has run.
- The supplied Calbrix paper has a source handoff for the Dash-8 water case and
  a primary plus separately implemented second 0.1 s Fig. 4 raster read; both
  share the stated axis calibration and carry the same declared read bounds.
  The primary trace peaks at 4.693 m/s at 0.4 s,
  near the paper's approximate 4.8 m/s at 0.5 s; the two figure reads agree
  within their combined ordinate bounds at shared nominal times. Neither trace
  is the paper's unpublished discharge or spatial inlet data, and correlated
  timing uncertainty remains material. Figs. 6–9 also have primary and
  independently calibrated Dash-8 `alpha_L=0.001` cloud-envelope reads. Their
  directed point-to-nearest-trace audit falls within summed read bounds for
  94–100% of samples, depending on series; this is figure-read reproducibility,
  not a solver comparison. The Fig. 8 body/caption time conflict remains open,
  Figs. 7 and 9 remain dimensionless because the outlet area is unreported, and
  reviewed near-origin Fig. 9 fragments remain separate uncertain reads. The
  E2-DIG-0.5 preregistration now separates both source-history reads
  and both Fig. 6(b) target reads, with an explicit but unverified
  `4.44 m × 0.30 m = 1.332 m²` geometry hypothesis and a release-blocking
  correlated source-uncertainty sensitivity. It labels standard sea-level air
  and standard gravity as provisional assumptions and disables surface tension
  as reported by the paper. It remains a draft pending independent approval;
  no E2 run or validation pass exists. See
  [`E2_CALBRIX_SOURCE.md`](../experiments/E2_CALBRIX_SOURCE.md) and the E2
  digitizations in [`data/README.md`](../data/README.md). Astra Max reviewed
  the separate source-uncertainty method and found its proposed six-knot
  reinterpolation did not implement the stated whole-history shift, coverage
  was unproven, target-coordinate uncertainty/pass rules were incomplete, and
  shared calibration was mislabeled as independent. The Luna revision now
  evaluates the continuous shifted history and corrects provenance. Astra
  Max's second exact-hash review says revise before freeze. The current revised
  draft fixes an absolute observation time of `0.5 s`, a common provisional
  gas-start convention, and source ages of `0.47/0.50/0.53 s`; it labels this
  a combined timing/startup assumption and specifies status precedence,
  binary64/root and case-ID/manifest rules. The third review returned
  **REVISE** on the history/case identity conflict and requested explicit
  query-time rounding. The bounded revision now separates history, case and
  execution IDs and fixes ties-to-even query projection; its SHA-256 is
  `bab679601f447193c7d103038c5703c94f36d208961c503d28c87c4af95b5c4b`.
  Astra Max's focused third-review follow-up accepts this exact method
  specification for freezing, with one low-priority identity-wording note.
  The acceptance does not approve a generator, case matrix, CFD execution or
  scientific gate.
  The separate acceptance is archived in
  [`E2_SOURCE_UNCERTAINTY_FOLLOWUP_4_20260925T093255Z.md`](reviews/E2_SOURCE_UNCERTAINTY_FOLLOWUP_4_20260925T093255Z.md);
  the earlier review-3 **REVISE** record remains unchanged.
  Earlier synthetic-check claims remain unarchived. The CPU exact-rational
  evaluator and identity utilities are now implemented in
  [`e2_source_uncertainty.py`](../src/aerial_drop/e2_source_uncertainty.py),
  with a focused test module and implementation record. Primary integration
  tightened stale-upstream and orphan/extra manifest rejection. Astra's exact
  implementation review returned **REVISE** for path aliases and unchecked
  fixture schema/status; the primary added canonical-path and exact
  schema/status checks plus stronger rational expectations. Astra's focused
  follow-up accepted the post-fix implementation. The post-fix 11 focused
  tests, Ruff lint and format checks pass. Current source/test/note hashes are
  `5579d1d1…b23841a`, `2d202996…ddb68d`, and `3a32f835…002d9d`.
  Initial and follow-up reviews are archived at [`E2 initial code review`](reviews/E2_IMPLEMENTATION_REVIEW_20260925T103306Z.md)
  and [`E2 implementation follow-up`](reviews/E2_IMPLEMENTATION_FOLLOWUP_20260925T103849Z.md).
  Provisional startup/boundary hashes are absent, so no real case matrix is
  emitted.
  Coverage, target-coordinate uncertainty, score and release decisions remain
  open. See
  [`third E2 method review`](reviews/E2_SOURCE_UNCERTAINTY_REVIEW_3_20260925T092416Z.md).
  The independent arithmetic found
  `1.881265 m` for the full primary advanced nominal history; `1.87096 m`
  covers only `[0,0.5] s`. This remains unapproved and unrun. Reviews:
  [`initial E2 method review`](reviews/E2_SOURCE_UNCERTAINTY_REVIEW_20260925T081638Z.md)
  and [`second E2 method review`](reviews/E2_SOURCE_UNCERTAINTY_REVIEW_2_20260925T084013Z.md).
- The Calbrix CL-415/E3 source record now covers the four exits, tank/domain
  drawings, source history, nearfield observables, solver/mesh facts, and missing
  outlet and boundary data. Fig. 4's legend and adjacent prose conflict on the
  top/bottom trace colors; Fig. 8 also has a 0.5/1 s timing conflict. The source
  record has an independent review approved with revisions; the omitted sketch
  label, `L_c` definition, legend/prose difference, and surface-tension
  qualification are now explicit. Independent CL-415 Fig. 4 red/top and
  green/bottom scalar maximum-velocity reads agree at shared sample times
  within combined figure and timing-read bounds, but visible positive tails end
  at different times. They do not establish exact shutoff or map two curves to
  four outlets. Two independent Fig. 11(a) reads of identified-liquid-structure
  counts agree within figure-read bounds, but they are not parcel counts.
  The 421-count first red peak is a linear-axis extrapolation above the last
  labeled y tick. The paper's Matlab structure-detection method is unpublished,
  so matching traces only establish figure-reading reproducibility, not an
  equivalent quantitative benchmark. Keep Fig. 11 descriptive. No E3 CFD run,
  comparison gate, or pass exists. See
  [`E3_CALBRIX_CL415_SOURCE.md`](../experiments/E3_CALBRIX_CL415_SOURCE.md).
- The Amorim M134 E4 source record now separates the measured and ADM Fig. 9
  vector markers into a reproducible plotted-profile digitization. The source
  defines `Vx = sum_y V(y)` at each along-track position; it is not a running
  cumulative sum along x. The aircraft's absolute pattern position is unknown,
  and the local PDF lacks cup-level data, so this is descriptive source
  preparation rather than a field-validation result. Independent audit
  confirmed the ADM plotted peak is 2.25% higher than the measured peak, at a
  different x location. The paper describes a general underestimation tendency
  for Marana drops but does not state this per-drop exception explicitly; the
  M134 difference is recorded without calling it a contradiction or gate.
  See [`E4_AMORIM_M134_SOURCE.md`](../experiments/E4_AMORIM_M134_SOURCE.md) and
  [`amorim_m134_fig9.csv`](../data/derived/amorim_m134_fig9.csv). Regenerate
  the plotted-marker CSV with `make digitize-e4`.
- Six actual geometric VOF surfaces were written at 0.02 s intervals. The
  locked optional PyVista renderer can create a provenance-recorded 3D frame
  from the solver's `alpha.water`/`U` surface. Rendering details and limits are
  in [`RENDERING.md`](RENDERING.md). This is not the planned 15–30 s animation.
- A stricter two-mode animation pipeline now reads every declared, hashed VTP
  field frame and checks `U`, `alpha.water`, `TimeValue`, timeline and common
  scales. Its diagnostic output is the
  ignored local artifact is
  results/runs/render-p0-short-diagnostic-msaa0-20260925/animation.mp4
  (SHA-256 287d4f758bb2c4c7a83624863d4b30a3994bbbf1cc6146e85de4cfaa722c4161).
  It uses the six real P0 surfaces at 0.02–0.12 s; its render manifest records
  hashes, fields, scales, software and claim limits. Three renders with
  multisampling disabled matched byte-for-byte on the recorded NVIDIA EGL/
  OpenGL backend. In validated mode, case comparisons also require
  common targets and coverage thresholds; the renderer requires matching pass
  records and rechecks conservative impact rebinning, mass closure and E0
  ground scoring. This P0 animation remains a 0.10 s provisional diagnostic; it
  does not show descent, breakup, deposition, or the requested full experiment.

## Not established

- Exact built Restás slot dimensions, spacing, discharge histories, pressure,
  foam properties and device geometry remain unavailable. Inputs in the P0 case
  are labelled provisional and must not be presented as measurements.
- The full 22-page Rouaix author manuscript is now identified at HAL. Case 1's
  single-nozzle conditions and both Figure 13 digitizations are recorded in
  [`E1_ROUAIX_CASE1_SOURCE.md`](../experiments/E1_ROUAIX_CASE1_SOURCE.md),
  [`rouaix_e1_case1_fig13.csv`](../data/derived/rouaix_e1_case1_fig13.csv), and
  [`rouaix_e1_case1_fig13_raster.csv`](../data/derived/rouaix_e1_case1_fig13_raster.csv).
  No E1 run or comparison gate has passed. Figure 13 gives no sample-time
  window; its `q=17.3` breakup marker is shared by Cases 1, 8, and 9; and the
  transverse-width definition is ambiguous. The empirical-fit residual is not
  treated as a source contradiction because fit scatter is unreported. Source
  review, accepted comparison tolerances, turbulence-input mapping,
  conservation diagnostics and solver/resource qualification remain open.
- Calbrix E2 cannot yet be an exact replay: the paper omits numerical exit area,
  exact flow history, pointwise outlet profile, several air/fluid properties,
  and detailed external boundary conditions. It calls the same plotted `U_L`
  both mean and maximum velocity. Source review and a frozen provisional-input
  reconstruction protocol remain open; no E2 run or gate has passed.
- A pinned Blackwell FluTAS candidate is built as `track2/flutas-nvhpc:26.9`
  (image ID `sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8`).
  It compiled with `cc120,cuda13.3`, ran a forced OpenACC kernel and a two-rank
  CUDA-buffer MPI collective, and passed the upstream 32 × 32 × 64 rising-bubble
  test with zero difference in its checked z-centroid and z-velocity arrays.
  The two ranks shared one GPU; multi-GPU scaling is not established. No
  project source-slot CFD or 1–3 million-cell pilot has run. FluTAS does not
  natively provide masked finite-duration sources, and its GPU pressure solver
  lacks the usual one-sided `ND`/`DN` pressure pair. Independent source review
  found a candidate paired z-source/return and periodic x/y mapping; its code
  implementation and diagnostics still need review. The GPU Restas pilot gate
  stays closed. See
  [`GPU_FLUTAS_FEASIBILITY.md`](GPU_FLUTAS_FEASIBILITY.md).
- No mesh/time-step convergence, validated breakup, aircraft-body wake,
  flight-height descent, parcel handoff, VOF-to-parcel mass and momentum
  conservation, coupled full-drop comparison, E4/E5 field-map validation,
  operational scoring, or E6 validation has passed.
- No Denner coupled heat/mass-transfer result has been reproduced, and no
  independent measured isolated-drop trajectory is yet used as a Region C
  validation target.
- The 9 m target and 2.4 kg/m² threshold in Restás support an illustrative
  arithmetic target, not a validated water footprint or fourfold performance
  gain. Water-only inputs do not establish foam or fire-suppression behavior.

## Compute and worker queues

- **Machine snapshot (2026-09-25 14:46 UTC):** `make doctor` reports 20
  effective CPUs (18 shared, two reserved), 117.6 GiB available RAM,
  260.0 GiB free disk, and one RTX 5090 with 31.8 GiB VRAM. The GPU sample at
  14:46 UTC was 0%, 16 MiB used and 21.32 W; no project solver or source
  container was running. A 24 GiB temporary OCI tar and three extracted
  source files were removed after their hashes/descriptor evidence were
  recorded; the archive report remains. These are point-in-time readings, not
  reservations. The doctor finds a CPU OpenFOAM candidate but marks its GPU
  pilot not ready because solver GPU support is unverified.
- **Worker queue (15:08 UTC):** Luna Max's H5 raw-roster/call-order audit
  (1 CPU / 4 GiB) and Astra Max's exact M3 arithmetic review (read-only,
  1 CPU / 4 GiB) are active.
  The M3 arithmetic bundle is sealed; its ordinary production-flags cases
  match 168 independently reconstructed spacing/reciprocal values and 15
  timestep rows, while the production-state subnormal-overflow branch was not
  reached. No H2 disposition is inferred pending Astra exact review. An E1
  packet review dispatch hit the collaboration thread limit and is queued for
  a freed reviewer slot. The DNS/VOF audit is accepted for H3
  schema drafting, not parser acceptance. The H7 runner audit is complete and
  confirms outer-lock cleanup lacks container verification. Candidate6 H4 is
  accepted at bounded host-test scope. Warden 13 completed and was archived
  at [`PROJECT_WARDEN_20260925T1500Z.md`](reviews/PROJECT_WARDEN_20260925T1500Z.md),
  SHA-256 `cafbbb755cfd1ff7dd2156919b159a27a0ecdbcfb66dbb310d904c26d30397cd`.
  The current planned worker caps total 2 CPU cores against the 18-core shared
  limit; caps are not reservations.
- **Candidate5 GPU checkpoints:** the 12:55 predecessor smoke and 13:54
  successor smoke used different frozen patches and local image IDs; these are
  distinct checkpoints, not a duplicate run. The successor's exact Astra
  review is
  [`FLUTAS_CANDIDATE5_SUCCESSOR_EXACT_REVIEW_20260925T1345Z.md`](reviews/FLUTAS_CANDIDATE5_SUCCESSOR_EXACT_REVIEW_20260925T1345Z.md),
  SHA-256 `9615e07d93e9c3d4e0bcd1b4a2373650419a56ba7f220ca3a90f96b2074c108c`.
  The one allowed run passed with exact image
  `sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`
  and patch `aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7`.
  Evidence is
  [`the successor smoke bundle`](../results/runs/flutas-candidate-gpu-regression-20260925T135456Z-2137699/);
  its SHA256SUMS file hashes to
  `4e1852edfb1f772665c23c45040c5ab83225184017b821a4f694feb34620d142`.
  It completed OpenACC, CUDA-buffer MPI and the upstream bubble test through
  3 s (`True True`) with no source input. Thirteen GPU and eleven container
  samples parsed; sampled maxima were 100% GPU utilization, 668 MiB VRAM,
  147.62 W, 330.4 MiB container memory and 193.96% container CPU. Those are
  sampled extrema, not hardware peaks. Do not repeat this smoke.
  The primary disposition and source boundary are in
  [`smoke/F1 disposition`](reviews/CANDIDATE5_SUCCESSOR_AND_F1_PRIMARY_DISPOSITION_20260925T1403Z.md).
- **Source producer and provenance:** the successor handoff passed 19
  source-boundary tests, 16 observability tests and four manifest tests, then
  built `sm_120.cubin`. Candidate6's two-halo exact follow-up now accepts H4
  narrowly; the historical candidate5 validator still needs its whole-array
  calls adapted before reuse with candidate6. The candidate6 build log has no
  retained executable, image or receipt. Production arithmetic, integration
  bytes, OCI receipt/export and six-ledger audit remain open. The wrong
  upstream-main locator is corrected by the primary
  [provenance erratum](reviews/CANDIDATE5_SOURCE_PROVENANCE_PRIMARY_ERRATUM_20260925T1403Z.md).
  The exact upstream path is `src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90`;
  local image identity is not an OCI manifest digest. An offline OCI feasibility
  probe exists, but production receipt/export and corruption checks remain
  open.
- **Analyzer:** F1 is closed narrowly for the exact reviewed implementation
  hash. Astra's
  [F1 review](reviews/FLUTAS_ANALYZER_F1_EXACT_REVIEW_20260925T1348Z.md)
  independently ran 57 tests and 42 literal phase/velocity outcomes. It does
  not bind staged input bytes or close six-ledger conservation/B2.
- **Source contract:** v0.1 remains preserved as a historical REVISE and v0.2
  remains an immutable design snapshot reviewed by Warden 12, not by the exact
  contract reviewer. The primary drafted v0.3 H1-H7 corrections, an exact H3
  input-schema proposal, explicit OCI receipt fields and a testable resource
  termination/lock contract. The independent
  [`DNS/VOF typed-record audit`](reviews/DNS_VOF_TYPED_SCHEMA_AUDIT_20260925T1443Z.md)
  is SHA-256 `e7709cc54e5ecbb623062fcba6f30f420d6c2c17048866cf9db25f756e917c47`;
  the new input annex is pinned inside v0.3. The six-ledger/raw schema and
  stop-prefix annex, numerical thresholds, arithmetic disposition, receipt
  tooling, lifecycle tests and exact Astra contract review remain open. The
  read-only [`H7 code audit`](reviews/RUN_LOCAL_H7_CODE_AUDIT_20260925T145043Z.md),
  SHA-256 `c7b763c7dab463b498e851b19f10b8cc9a28d96bf31d28f1cfdb4fd3dc57f513`,
  confirms outer-runner lock release is not termination-verified. No source
  case is eligible; B1-pre/B2 and launch review remain closed.
- **E1:** the corrected static package, factual inventory, and source-order
  [`ALPHA_CAPTURE_MAP.md`](../cases/e1_rouaix_case1_static/ALPHA_CAPTURE_MAP.md)
  are accepted only for static-preparation scope. The E1 decision packet is
  complete (SHA-256
  `c1d57536656b4253d6a43813fe957b8fcf7017a8b3d6b80cbe8c5d1379212939`) and
  awaits primary decisions plus independent review. D-NUT-BC, contact angle,
  initialization/mesh, instrumentation and characterization remain open; no
  mesh or solver is approved. Older gate/audit prose still carries predecessor
  alpha-stage names and must be reconciled before instrumentation is frozen.
- **Warden and cadence:** Astra Max Warden 13 is complete and archived at
  [`PROJECT_WARDEN_20260925T1500Z.md`](reviews/PROJECT_WARDEN_20260925T1500Z.md).
  The primary accepts its sequence: complete H5, review M3 and the full
  contract at the right interface boundary, then implement producer/auditor
  and H7 work in disjoint branches; advance E1 decisions independently. This
  changes no gate or launch status. The next Warden trigger is two newly
  accepted bounded checkpoints after this disposition, a material
  source/solver-interface change, a gate transition, or a repeated blocker
  that changes its resolution. H7's read-only audit and M3 bundle completion
  are not accepted scientific checkpoints.
- **GPU queue:** no GPU job is currently eligible. The exact-reviewed 13:54
  successor smoke is complete and must not be repeated. Candidate6 H4 helper
  tests are CPU-only and now accepted; source-mode diagnostics remain blocked
  by B1-pre/B2, raw audit, provenance, limits, launcher enforcement and exact
  launch review. The single RTX 5090 is serialized by
  `scripts/run_local.py --gpu`; keep CPU work moving while the GPU queue waits.
- **Pipeline progress:** E0 remains the only completed scientific gate:
  1/7, about 14% by gate count only. The new smoke and software checks do not
  change that count. Source simulation, E1 characterization, later E2–E6
  validation and the full aircraft-to-ground objective remain incomplete.

## Next work, in order

1. Complete the active exact Astra review of the sealed M3 arithmetic bundle
   and record the primary's narrow disposition. No GPU trial applies.
2. Complete the active H5 raw-roster audit; finish the six-ledger/raw schema,
   stop-prefix examples, primitive operands, zero rules and byte bound without
   changing v1.2 or v0.2. Then exact-review the full v0.3 interface before
   implementation treats it as frozen.
3. After contract review, implement the H7 supervisor change and fake-runner
   tests from the completed code audit: hard-limit enforcement, termination
   proof and GPU-lock retention must all pass. No real GPU run until then.
4. Obtain Astra Max independent review of the completed E1 decision packet
   when a reviewer slot releases; primary disposition follows. Keep E1 NOT
   READY; do not mesh or characterize before those reviews and the
   timestep/Courant compatibility check.
5. After interface acceptance, split strict staged-input parsing/raw capture,
   independent six-ledger auditing, receipt/OCI tooling, and the verified
   source supervisor into disjoint CPU assignments. Reconcile E1 predecessor
   capture names before instrumentation. Do not treat the CPU OpenFOAM route as
   a validated GPU solver.
6. Freeze limits, output-size arithmetic and launcher termination behavior;
   exact-review the complete source release and launch gate. Only then schedule
   `dry_four` → `quiescent_one` → `quiescent_four` sequentially, auditing each
   before the next. Positive crossflow needs its own prospective protocol
   amendment and review.
7. Keep E2, E3, E4/E5, VOF-to-parcel transfer and E6 on their separate gates.
   E5 paper extraction is complete, but matched release/cup data remain
   unavailable for field validation.

The user authorized clearly labelled provisional inputs on 2026-09-24. Preserve
those labels and uncertainty; measured inputs remain necessary before claiming
behavior of the built Restás system. Scientific progress is still **1 of 7
E0–E6 gates (about 14% by gate count only)**. Candidate5's smoke and all
workflow/build work are not scientific gate passes.
