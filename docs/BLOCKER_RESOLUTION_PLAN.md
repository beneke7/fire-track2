# Blocker resolution plan

**Working plan · 25 September 2026 15:08 UTC. This is a proposed work sequence, not a
validation result, accepted experiment protocol, or permission to start CFD.**

**Current primary checkpoint · 28 September 2026 13:04 UTC.** The user has
authorized one GPU diagnostic, but no solver/GPU run has started. Candidate6's
build/static/host checkpoint is accepted narrowly by Astra Max. The primary
accepts Warden 14's dry-only scope and Warden 15's integration findings; these
are archived at [Warden 14](reviews/PROJECT_WARDEN_20260928T1127Z.md) and
[Warden 15](reviews/PROJECT_WARDEN_20260928T1300Z.md). The allowed claim is
software execution and telemetry for the zero-liquid, zero-slot `dry_four`
case; it cannot establish injection, conservation, plume behavior, or E1–E6.
The launcher now passes the candidate identity check's required OCI archive
argument, with a CPU-only test. Before exact Astra launch review, the primary
will align the staged directory with the manifest adapter, close native clock
and timestep predicates, align output-map paths with actual producers, capture
the host snapshot in-bundle, implement success/failure finalization and
inventory, and test bounded startup telemetry sampling. The GPU queue remains
idle until those checks and the exact review/disposition pass. Current machine
headroom is refreshed immediately before launch; no water case starts
automatically.

E0 is the only completed scientific gate: 1/7 (about 14% by gate count only).
The candidate5 successor passed one exact-reviewed, source-disabled GPU smoke;
it is not source qualification. Analyzer F1 closed on exact hashes after 57
tests and 42 independent literal outcomes. E1 static preparation is accepted
at narrow scope, while its gate remains NOT READY. Candidate5 source release
H4's two-halo explicit-slice regression has now passed exact Astra Max review;
the accepted scope is helper-level and does not qualify a source run. The
primary accepts the independently audited DNS/VOF extraction for H3 schema
drafting and has added a hash-pinned exact-fixture annex to the v0.3 proposal.
The remaining v0.3 interface gaps are the six-ledger/raw schema and
stop-prefix annex, M3 arithmetic disposition, source receipt/tooling, numeric
limits, and verified shutdown/lock enforcement. H5 raw-roster audit and M3
exact review are active; Warden 13 is complete and archived. No source run or
E1 solver is approved.

The user-authorized roles are Luna Max implementation/research workers and
Astra Max blocker planner, general reviewer and project Warden. The primary
owns decisions, interfaces, integration and compute scheduling, with at most
three spawned workers alongside the orchestrator. Clearly labelled provisional
inputs remain authorized for engineering preparation; they are not measurements
or gate approval. The synthetic FluTAS box does not provide E1's aircraft wall
or external inlet/outlet conditions.

## Primary disposition of Astra Max deblock advice

The primary reviewed [`DEBLOCKER_PLAN_20260925T1229Z.md`](reviews/DEBLOCKER_PLAN_20260925T1229Z.md),
SHA-256 `48a8aeb1f9e828577d24ee6f152490f7481ce18367751e15c6ec2055928438c8`,
and **accepts** its ranked engineering sequence. It is advice, not a gate
approval:

| Recommendation | Primary disposition | Owner and next evidence trigger |
| --- | --- | --- |
| Candidate5 successor exact review and smallest source-disabled GPU regression. | **Accepted and complete for this bounded smoke only.** Astra approved the exact local image/patch; primary checked current headroom and used the unchanged locked runner. | [`successor review`](reviews/FLUTAS_CANDIDATE5_SUCCESSOR_EXACT_REVIEW_20260925T1345Z.md); run evidence `results/runs/flutas-candidate-gpu-regression-20260925T135456Z-2137699/`. No source input; no repeat. |
| Candidate5 producer and analyzer repairs. | **Accepted narrowly.** Schema v1.2 remains unchanged; diagnostic `time_s` uses `time_start_s+state_index*dt`, while native AB2 time remains native. F1 is closed for exact hashes. Candidate6's one-halo production correction and nonuniform two-halo explicit-slice adapter/negative control are accepted for H4 helper scope. | F1 and candidate5 exact reviews are archived. [`Candidate6 H4 follow-up`](reviews/FLUTAS_CANDIDATE6_H4_TWO_HALO_EXACT_REVIEW_20260925T1445Z.md) is ACCEPT; it does not accept the historical full validator, source run, or candidate receipt. No source run. |
| B2 staged-input, raw-evidence, conservation and launch contract. | **Accepted as primary-owned design work, not interface acceptance.** v0.1 is historical REVISE; v0.2 is preserved as a Warden-reviewed proposal snapshot. The primary has drafted v0.3 H1-H7 corrections and exact DNS/VOF input-schema annex. | Warden 12 exact findings, the focused Astra deblock plan, and DNS/VOF audit are archived. The six-ledger/raw schema/stop-prefix annex and exact Astra contract review remain required before implementation treats interfaces as frozen. |
| E1 static corrections and inventory. | **Accepted for static-preparation scope only.** The corrected gate/inventory follow-up and source-order alpha map are accepted; the decision packet is complete but not accepted. E1 remains NOT READY; no mesh/characterization/solver is authorized. | [`E1 inventory follow-up`](reviews/E1_GATE_INVENTORY_EXACT_FOLLOWUP_20260925T1320Z.md), [`alpha capture map`](../cases/e1_rouaix_case1_static/ALPHA_CAPTURE_MAP.md), and [`decision packet`](reviews/E1_CHARACTERIZATION_DECISION_PACKET_20260925T1356Z.md); primary disposition and independent review remain next. |
| Frozen crossflow inputs stay negative guard fixtures. | **Accepted.** No silent step/factor relaxation; positive crossflow requires a prospective versioned protocol and review. | Primary opens a new amendment only if crossflow qualification is required; otherwise these fixtures remain expected guard rejections. |

No new user data are required for these engineering fixes. Measured built-
Restas geometry/discharge/pressure and E4/E5 raw collection evidence remain
valuable at their later scientific stages. Astra Warden checkpoint 10 is
archived at
[`PROJECT_WARDEN_20260925T1300Z.md`](reviews/PROJECT_WARDEN_20260925T1300Z.md),
SHA-256 `ad597e6e658f150cd8a264356f7c579b9bde22ba07aa2761413ecb137733164d`.
The primary accepts its ranked recommendations and freezes the time-field
choice in
[`FLUTAS_CANDIDATE5_TIME_INTERFACE_PRIMARY_DECISION_20260925T1302Z.md`](reviews/FLUTAS_CANDIDATE5_TIME_INTERFACE_PRIMARY_DECISION_20260925T1302Z.md).
Its other advice is integrated into the rows above and queue below. Astra
Warden checkpoint 11 is archived at
[`PROJECT_WARDEN_20260925T1340Z.md`](reviews/PROJECT_WARDEN_20260925T1340Z.md),
SHA-256 `89a2e1e310f25650aaa6ec58d6960b49c6793f4b63b37c8200bba2854ee1db6c`.
Since Warden 11, the primary accepted F1 closure, ran the single reviewed
successor smoke, corrected source provenance and drafted v0.2. Warden 12's
exact-snapshot memo is archived at
[`PROJECT_WARDEN_20260925T1403Z.md`](reviews/PROJECT_WARDEN_20260925T1403Z.md),
SHA-256 `6a1a4221a354e6bbc18c8ef69d56ec2e4a916ac83e97377c6b758935adef875f`.
The focused Astra deblock plan is
[`BLOCKER_RESOLUTION_PLAN_ASTRA_20260925T1615Z.md`](reviews/BLOCKER_RESOLUTION_PLAN_ASTRA_20260925T1615Z.md),
SHA-256 `dfc2a4012b982f498f08378032a133bd87b750150c5ced60dddc23eaec9a28cd`.
The primary accepts their concrete interface/queue corrections and ranked
engineering tasks; neither memo accepts a candidate, contract or gate. The
candidate6 exact review is archived at
[`FLUTAS_CANDIDATE6_H4_EXACT_REVIEW_20260925T1620Z.md`](reviews/FLUTAS_CANDIDATE6_H4_EXACT_REVIEW_20260925T1620Z.md),
SHA-256 `2341b9a361046fa6033740b0a8409fe979f197e1523578f3110d14c1b9527e13`;
it accepts only the one-halo production mapping and requires further H4 test
evidence. No source case is authorized.

The later H4 successor review is
[`FLUTAS_CANDIDATE6_H4_TWO_HALO_EXACT_REVIEW_20260925T1445Z.md`](reviews/FLUTAS_CANDIDATE6_H4_TWO_HALO_EXACT_REVIEW_20260925T1445Z.md),
SHA-256 `176475954e7540739b7267f0a6d54cf6e298624dfb0141e7d5fa36616c3bf2d4`.
It accepts the retained one-halo and explicit-slice two-halo helper regressions
at narrow H4 scope. It does not make the legacy whole-array full-validator
calls safe, accept a source run, or supply candidate6 build/OCI provenance.
The independent DNS/VOF record extraction is
[`DNS_VOF_TYPED_SCHEMA_AUDIT_20260925T1443Z.md`](reviews/DNS_VOF_TYPED_SCHEMA_AUDIT_20260925T1443Z.md),
SHA-256 `e7709cc54e5ecbb623062fcba6f30f420d6c2c17048866cf9db25f756e917c47`;
the primary accepts it as evidence for H3 proposal drafting only.

## Evidence at this handoff

The source of truth is the [experiment plan](../track2_aerial_drop_experiment_plan.md),
[AGENTS.md](../AGENTS.md), [validation contract](VALIDATION.md), and accepted
run/review records linked from [STATUS.md](STATUS.md).

| Evidence class | Current evidence | What remains open |
| --- | --- | --- |
| Analytical verification | E0 passed its independent review and seven analytical report checks. | Keep affected analytical checks passing as interfaces change. E0 does not validate CFD. |
| CPU implementation diagnostic | P1 revision 2 passed its source-event and box-ledger gates, including an independent raw-output audit. The retained revision-1 run remains failed under its original protocol. | P1 has no E1/E2/E3 benchmark, breakup, descent or field-validation result. |
| GPU build/runtime foundation | The pinned upstream FluTAS Blackwell image compiled and passed OpenACC, CUDA-buffer MPI and its rising-bubble check. Candidate2 compiled a patched `sm_120` executable. | Source injection, aircraft boundaries and performance at the planned pilot size remain unqualified. |
| Source patch status | Candidate1 is withdrawn and candidate2 is preserved as blocked; Astra Max found that mandatory `dry_four` fails its zero-duration validation, periodic return halos are inconsistent, and source shutoff can use stale liquid ghosts/reconstruction. Candidate2 image: `sha256:6ecfa8e248fe297782becdffba41dcd5db267768cdee0f9f724895796252e7b3`; patch SHA: `bd42ab7b17383ae90411aef2e0878c1427a3c3a5f49694eeb28c57659063af40`; evidence: `containers/flutas/evidence/source-candidate-runs/20260925T073740Z-1880163/`. Candidate3's isolated patch SHA is `055758a2690fe4bb9003bdc54665cbc63f67e490f8bd1e307d71ca6d013a4319`; image ID is `sha256:90f1261308ab56e52ee29d129deefad86a19b352cef79b43feca08df6762e1c3`; immutable build evidence is `containers/flutas/candidate3/evidence/runs/20260925T082315Z-1955187/`. Astra Max exact review is [`candidate3/INDEPENDENT_REVIEW.md`](../containers/flutas/candidate3/INDEPENDENT_REVIEW.md); the bounded source-disabled GPU regression passed in [`results/runs/flutas-candidate-gpu-regression-20260925T083856Z-1977448/`](../results/runs/flutas-candidate-gpu-regression-20260925T083856Z-1977448/). Candidate4 is frozen, built, exact-reviewed and has passed one bounded source-disabled regression. Its patch, image, build, runner-review and run evidence are linked in `docs/STATUS.md`. | Candidate3 passes 13 Python static/analytic checks, five host-only Fortran behavior modes, the `cc120` compile and one source-disabled OpenACC/MPI/upstream-bubble GPU regression. Its test bundle did not sample runtime peak RAM/VRAM, so it supports no performance or scale claim. No source boundary input was present; no source-enabled GPU runtime or source CFD exists. Candidate4 adds measured Co/interface-Co, clarified ledgers, complete failure records and host behavior tests; its bounded GPU regression confirms only the source-disabled upstream runtime. B1 source-on projection/state behavior and B2 analyzer/schema/limits/protocol review remain unqualified. Candidate2 evidence is not inherited. |

| Numerical reference preparation | E1 has two Figure 13 reads; E2 has separate Fig. 4 input reads and Figs. 6–9 target reads; E3 has paired Fig. 4 and Fig. 11 reads. | Reproducible figure reading is not a solver comparison. Source semantics, geometry and case-specific protocols still matter. |
| Ground evidence preparation | E4's M134 Fig. 9 plotted-marker extraction is audited. E5's six Gu Table 4/5 rows and collection method are transcribed in the new source record and checked CSV. | No E4/E5 validation result exists. Raw E5 cup data and release traces are unavailable; matched-case reconstruction, registration and acceptance rules remain open. |

**Current successor addendum (15:08 UTC):** Candidate5's exact-reviewed
successor passed one source-disabled GPU smoke; it did not contain a source
input. Candidate6 H4 is accepted only for retained one-halo and explicit-slice
two-halo helper tests with a shifted-index negative control. Candidate6 has no
retained production executable/image/receipt, and the historical full validator
is unsafe to reuse unchanged. The M3 arithmetic bundle is complete and its
Astra exact review is active. None of these updates qualifies source execution.

Links to existing artifacts below are evidence locations. New filenames named
as deliverables are proposed artifacts and are not assertions that those files
or results already exist.

An earlier specialist review identified candidate1 integration/test-path gaps
and withdrew that image after finding source-interval and return-velocity
timing defects. Its exact image metadata and build log are retained under
[`candidate1-withdrawn`](../containers/flutas/evidence/source-candidate-runs/candidate1-withdrawn/).
Candidate2 subsequently applied the patch through the visible Docker recipe
and passed ten static/analytic checks plus a native build. These checks do not
execute the Fortran boundary helper or a source-slot solver case. Preserve the
historical checks as candidate-specific evidence; check counts are not runtime
qualification. Candidate2 remains blocked by the independently found
dry-validator, periodic-return-halo, and source-shutoff state issues. Its exact review is recorded in
[`INDEPENDENT_REVIEW.md`](../containers/flutas/evidence/source-candidate-runs/20260925T073740Z-1880163/INDEPENDENT_REVIEW.md).
Candidate1 and candidate2 pass records cannot be inherited by a corrected
candidate.

## Executive blocker table

“Primary” means the orchestrator. “Implementer” and “source preparer” are
`gpt-6-luna` / `max`; the independent general reviewer is `gpt-6-astra` /
`max`, following the user's latest instruction. The Astra Max blocker planner
and project warden assess dependencies and project claims. The reviewer must
not approve their own physics or conservation implementation. Each acceptance
below requires the primary's recorded decision on the cited artifacts.

| ID / blocker | Exact next action and owner | Required evidence / artifact | Dependency and condition to unblock; stop condition |
| --- | --- | --- | --- |
| **B0 — candidate4 source-disabled runtime smoke (resolved)** | Candidate4's frozen patch/build and wrapper passed exact Astra review; primary ran the single bounded smoke with the immutable reviewed image. Do not repeat the unchanged attempt. | [`candidate4 regression evidence`](../results/runs/flutas-candidate-gpu-regression-20260925T095317Z-2015705/); runner hashes `282bfce5…` / `9c885143…`; offline fake-test hash `3e409efd…`. Smoke reached `3.001520526915884 s`, recorded `*** Fim ***`, passed OpenACC/CUDA-buffer MPI/upstream rising bubble, and had no source input. Thirteen GPU and eleven container CPU/memory samples parsed. | B0 clears only the source-disabled runtime checkpoint. The retained post-removal `docker stats` race is nonfatal because all in-run samples are valid. B1/B2 remain closed; no source-on run is released. |
| **B0-R — P1 replay hash drift (resolved)** | Completed: Astra Max reviewed the full current Makefile target and six-file local launch path; primary re-froze exact hashes and ran non-solver contract/input/image checks. | Dated review is in `experiments/P1_SOURCE_EVENT_LEDGER.execution.json`; validation details and test output are in [`P1_EXECUTION_REFREEZE_VALIDATION.md`](../results/P1_EXECUTION_REFREEZE_VALIDATION.md). Five focused modules passed (59 tests); real validator accepts the contract/rejects a stale hash; regenerated case inputs and CPU image match accepted Rev 2. | Resolved without CFD or a repeat run. Historical Rev 2 remains accepted; optional replay is ready, not required. Do not edit the protocol or accepted bundle. |
| **B1-pre — source diagnostic eligibility (blocked)** | Candidate5 successor has exact narrow review and one source-disabled GPU smoke. Its 19 source-boundary, 16 observability and 4 manifest checks, native build and smoke cover only their stated scopes. Candidate6 H4 is now accepted for explicit-slice one/two-halo helper regressions; the historical full validator's whole-array calls remain unsafe to reuse unchanged. | [`successor exact review`](../docs/reviews/FLUTAS_CANDIDATE5_SUCCESSOR_EXACT_REVIEW_20260925T1345Z.md); [`candidate6 H4 follow-up`](../docs/reviews/FLUTAS_CANDIDATE6_H4_TWO_HALO_EXACT_REVIEW_20260925T1445Z.md); [`source-disabled smoke`](../results/runs/flutas-candidate-gpu-regression-20260925T135456Z-2137699/). | **B1-pre is not accepted.** No source case is eligible. Candidate5 lacks an immutable build receipt/OCI identity and retained compiled integration bytes; candidate6 has only ephemeral build evidence. Source input binding, raw capture/audit, scientific limits, and supervisor/termination enforcement also remain open. |
| **B1-runtime — source/projection qualification (produced by staged runs)** | After B1-pre and B2 acceptance, measure source/projection/flux behavior from the ordered source cases; do not require those future measurements as a precondition to starting the same cases. | Applied-state/interval joins; actual geometric source flux and six-face ledgers; phase/velocity validity; projection, continuity, global/L1 divergence and Courant evidence; exact hashes and valid runtime resource histories. | This is an outcome of B3 runs, not a pre-run dependency. Failures stop the queue and remain immutable evidence. Candidate4 source-disabled smoke does not satisfy this row. |
| **B2 — staged-input, analyzer, and source-release contract (open)** | Analyzer M1/M2/F1 defects are closed at narrow exact hashes; F1 independently passed 57 tests and 42 literal cases. Frozen v1.2 retains exactly three observability tables. V0.2 is Warden-reviewed but has contradictions. V0.3 now has corrected H1/H2, typed DNS/VOF input schema, exact receipt fields and revised H7 lifecycle proposal; six-ledger/raw schema remains unwritten. | Exact staged-byte parser/binding; all six inherited ledger headers/token types/prefixes; required raw roster and stop matrix; independent conservation auditor; immutable OCI receipt/export; numerical limits; verified source supervisor and CPU fake-run lifecycle evidence. | B2 remains closed pending exact Astra contract review and primary disposition, implementation/tests against frozen interfaces, authoritative provenance receipt, independently justified limits, and launch review. Candidate6 H4 has narrow acceptance; production-arithmetic disposition and the other interface/evidence gaps remain open. A `not_applicable` iterative residual does not waive continuity/divergence evidence. No source GPU/solver case. |
| **B3 — source diagnostic and GPU scale are unproved** | After B1-pre/B2 and launch review, primary may schedule quiescent `dry_four` → one-slot → four-slot sequentially, stopping at first failed check. The frozen `dry_crossflow` and `crossflow_four` cases are expected-negative U0 guard fixtures and are not source-runtime attempts. Positive crossflow needs a versioned step/factor protocol amendment and exact review before any run. See [`FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md`](../experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md). Each accepted attempt is analyzed and independently audited before the next. After diagnostic qualification, prepare a separately reviewed 1–3 million-cell pilot contract. | Immutable bundle per attempt/stage, applied boundary states, all-face fluxes, per-slot mass/momentum, continuity and Courant records, full timestep status, image/input hashes, sampled RAM/VRAM/timing, independent report and decision. Later pilot: pressure/I/O share, throughput and checkpoint-cost projection. | Primary arithmetic gives `dt/dtmax=0.20003689638113265` versus factor `0.2`; see [crossflow arithmetic check](reviews/FLUTAS_CROSSFLOW_GUARD_ARITHMETIC_PRIMARY_20260925T121916Z.md). Current crossflow inputs fail before U0 and cannot establish crossflow behavior. Any factor/step change must preserve or explicitly redeclare the pulse duration, dose and horizon and receive independent review. A source pass clears only implementation qualification. Do not begin later stages after a real failed check; no 5–10 million-cell run until a separate pilot demonstrates affordable cost and compatible physics. |
| **B4 — E1 time/width semantics and numerical contract (accepted only for static prep)** | Astra accepted the corrected gate inventory and static artifacts at narrow static-preparation scope. Current gate SHA-256 is `8e3efe6a3e7edb91985550ff5c285615e5b26f880e74415cb57962efdb7d9132`; see [`E1 inventory follow-up`](../docs/reviews/E1_GATE_INVENTORY_EXACT_FOLLOWUP_20260925T1320Z.md). The separate decision packet is complete and awaiting primary disposition. | The paper-derived window/width reconstruction, two figure traces, uncertainty treatment, explicit `phi`/`rhoPhi` density, stationarity as descriptive only, D-NUT/contact-angle proposals, mesh/initialization, instrumentation and resource choices still need primary and independent review. | Static package and inventory correction are closed at narrow scope. E1 remains NOT READY; no mesh, characterization, E1 execution, Figure 13 acceptance or E2 advancement. D-NUT-BC/contact angle and characterization acceptance/resource rules remain open. |
| **B5 — E1 characterization and solver validation remain open** | The corrected static package and source-order `alpha_preclip` / `alpha_postclip` / `alpha_solver_final` capture map passed exact review for static-preparation scope. The OpenFOAM route remains an approximation to STAR-CCM+. The separate Luna decision packet is complete and awaits primary disposition plus independent review. | Freeze D-NUT-BC/contact-angle choices, instrumentation and correction ledger, mesh and initial-field evidence, uncertainty/acceptance rules, and prospective resource/stopping limits; exact review before mesh/characterization. | No mesh or solver is approved. Missing built geometry and boundary measurements remain clearly provisional; accepted static artifacts are preparation only. Older gate/audit stage names need prospective reconciliation. E1 may remain descriptive/inconclusive if model/source mapping or uncertainty is inadequate; E2 stays downstream of accepted E1. |
| **B6 — E2 M03 evaluator code review accepted; scientific release open** | Astra's first exact-hash implementation review returned **REVISE** for path aliases and unchecked fixture schema/status; primary fixed both and addressed the two low-priority expectation issues. Astra accepted the exact post-fix source/test/note hashes in [`E2 implementation follow-up`](../docs/reviews/E2_IMPLEMENTATION_FOLLOWUP_20260925T103849Z.md). The accepted M03 method hash is `bab679601f447193c7d103038c5703c94f36d208961c503d28c87c4af95b5c4b`. | Source `5579d1d1e3327d281223e7e0e24cf2443f0b4d3ceb18beecf91d5b745b23841a`; tests `2d202996de4d8d0b70f5768308bce6459a86a6b9cdd99d371c81f09c37ddb68d`; implementation note `3a32f835d142bcebe342fdc810a93262f6c0ff81660983f7d48aab0be4002d9d`. Initial review at [`E2 initial exact review`](../docs/reviews/E2_IMPLEMENTATION_REVIEW_20260925T103306Z.md) was against the earlier code hashes; current focused checks: 11 passed, Ruff lint and format passed. | Code-review findings are closed. No startup/boundary identities, approved score/target-coordinate contract, scenario coverage proof, production matrix or CFD release exists. E1 proposal acceptance does not advance the E2 method: E1 execution/acceptance and a separately reviewed E2 protocol remain prerequisites. The nominal full-run source-history integral is `1.881265 m`; `1.87096 m` covers only `[0,0.5] s`. Inferred `1.332 m²` remains a hypothesis. No user input is needed for this CPU code review; exact source timing or physical uncertainty claims need better source evidence. |
| **B7 — E3 four-exit mapping and terminal history are missing** | Source preparer reconstructs reviewed patch polygons/normals/groups from the paper or recovered files, retains both CL-415 histories and defines supported observation/source windows. Reviewer checks all inferred mappings and timing conflicts. | E3 geometry/source packet, two trace reads, explicit red/top-green/bottom primary convention and any swapped-label sensitivity, two independent reads of quantitative target curves, frozen limited-window or terminal-tail protocol. | Preparation can proceed now; E3 solver comparison follows accepted E2. Two curves cannot silently become four equal port histories. No supported grouping means no E3 replay; no supported shutoff means no complete-drop or `3 s` post-release claim. Fig. 11 remains descriptive without equivalent structure detection. |
| **B8 — regions B/C/D are not yet a conservative full-drop pipeline** | After the primary freezes shared interfaces, implementer builds a minimal detached-structure handoff and ground accumulator; reviewer derives synthetic mass/momentum/frame expectations independently. Prepare a direct-VOF descent attempt and assess loading before selecting one-way/two-way coupling. | Time-stamped phase-weighted transfer records, parcel masses/velocities, exclusive inventory/sink ledger, raw impact positions/times/weights, independent tests; then direct-VOF attempt, overlap and handoff-location sensitivities in maps and `L95`. | Interface/test preparation may overlap nearfield work. Production use needs qualified A/B physics, reviewed transfer/transport budgets and measured resource feasibility. Stop on unclosed transfer momentum/mass, unsupported unresolved-size models or ignored high loading. A failed/limited direct-VOF attempt is retained as evidence, not a descent validation. |
| **B9 — E4 M134 measured comparison is source-limited** | Source preparer independently reads/reviews Fig. 4 contours and Fig. 9 uncertainty; primary freezes registration, source reconstruction and observable definitions before any model overlay. Seek cup-level data and trial metadata through the user when available. | E4 source/uncertainty record, retained independent figure reads or raw cups with units/binning, source/track/wind packet, one preregistered translation rule if needed, contour length/area and `Vx` comparisons kept separate. | Evidence preparation can proceed now; controlled transport comparison follows the preceding stages and B8. Current plotted figures support descriptive work. Missing raw measurement uncertainty, matching source conditions or defensible limits prevents a field-validation pass; never infer collected mass by integrating plotted `Vx dx`. |
| **B10 — E5 collection convention and six matched cases are not reconstructed** | Source extraction is complete in `experiments/E5_GU_AG600_SOURCE.md` and `data/derived/gu_ag600_table4_table5.csv`; Luna checked the six source rows and Table 5 bias arithmetic against the local PDF. Astra/primary still need an exact source-record review. | DOI/PDF/page/table locators, six-row CSV separating measured and reconstructed fractions, cup/collection/method audit, missing-data list and hashes are present. Independent review should check denominators, collection area, interpolation, ±3σ integration and rounding. | Paper transcription is prepared, but no E5 case/run exists. Raw cup coordinates/masses, release traces and exact metered Q are unavailable. Controlled E5 follows E4 and matched-case reconstruction. All six groups must be reported. The paper's 10% relative-bias criterion needs local justification before use. Fractions alone cannot reconstruct a ground map or validate `f_useful`. |
| **B11 — E6 and built-system claims are not supported** | Primary freezes a matched conventional/Restás scenario only after preceding scientific gates; implementer uses common physics/scoring and preserves an unadjusted pair; reviewer audits ledger, continuous-strip scoring and all sensitivities. | Matched inputs, maps/raw impacts, `L95`, `f_useful`, actual strip and collected mass, escaped/airborne mass, map/threshold/width and physical/numerical sensitivities; separate operational comparison. Built-system claim additionally needs the measured packet below and an independent comparison. | E0–E5 and B8 are prerequisites for a validated ground-delivery comparison. Idealized preparation is allowed now; no present E6 validation or fourfold claim exists. Zero control `L95` makes gain undefined. Water-only results cannot establish foam, device discharge, suppression or post-impact behavior. |

## First release: finish the source diagnostic without changing its meaning

Use [the source gate](../experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md) as
the acceptance contract. The details below identify what must be reviewed;
they do not independently approve its proposed thresholds.

1. **Historical candidate1 projection/state defect.** Candidate1 set
   `source_interval=istep-1`, applies that interval before `advvof`, and uses
   the same index before and after `correc`. At a pulse transition this
   overwrites normal boundary velocities immediately before VOF without
   projecting the changed field. At an initially quiescent top cell,
   changing `W` from 0 to `-4.8 m/s` changes its divergence contribution by
   `-4.8/0.025 = -192 s^-1`; matching the bottom's *global* volume flux does
   not remove that local defect. A post-projection audit alone misses the
   velocity consumed by VOF. Candidate2 corrected the `k` versus `k+1`
   sequence, and Astra Max found it consistent in source inspection; its
   remaining transition issue is stale phase ghosts/reconstruction at the
   first sweep after shutoff (see the candidate2 review). Keep the agreed
   contract: transport interval `k` with already corrected
   `U_k`; impose state `k+1` for its next projection and preserve it after
   correction. Check any cached geometric return flux against its state
   index, especially at start/shutoff. If geometric return matching changes
   the velocity inside VOF, demonstrate compatible local continuity and
   transport fluxes before accepting that formulation. Candidate1 derives
   return from liquid-phase flux during VOF; this does not by itself prove
   total face-volume/projection compatibility. Match and audit total volume
   separately from liquid-phase attribution. A different algorithm
   requires a prospective protocol change and independent review.
2. **Freeze the actual candidate.** Preserve the passing upstream image.
   Deliver a reproducible separate source image and its base/upstream/patch
   identities. Test the final patch rather than a temporary predecessor.
   The source suite is outside `make check`'s normal `src/scripts/tests`
   lint scope and must be invoked explicitly against the patched source tree:
   `.venv/bin/python containers/flutas/tests/test_source_boundary.py <patched-source-root>`.
   Record the final count and output; source-string matching and fixture
   arithmetic do not execute the Fortran boundary logic. Add bounded
   executable validator/helper behavior checks, then use separately reviewed
   dry/source diagnostics for solver evidence. Candidate2 includes a
   quiescent zero-source fixture, but its validator defect and static-only
   coverage remain; add a distinct dry crossflow/gravity fixture as well as
   the liquid-pulse fixtures. Retain the recipe's actual test invocation and
   correct main-driver path in the final-image evidence.
3. **Freeze schedule and geometry.** Current draft: `4.0 × 2.1 × 1.0 m`,
   uniform `0.025 m` cells, `160 × 84 × 40 = 537,600` cells, one MPI rank,
   `dt=1e-4 s`, 14 completed steps through `0.0014 s`. Intervals `k=2..11`
   inject; `k=0,1` and `k=12,13` do not. The earlier 12-step setting would
   provide no completed post-shutoff transport intervals; check all fixture,
   test and contract copies agree on 14. One slot is `1.0 × 0.15 m`, four
   masks are disjoint and grid aligned, and their edge gaps are `0.05 m`.
4. **Freeze the six-face contract and forces.** Candidate x/y pairs are
   periodic; both z normal velocities are Dirichlet, pressure is Neumann,
   and every `is_outflow` is false. Record tangential velocity BCs, alpha and
   density/viscosity ghost handling separately, including after generic
   property fills. With outward normal signs, z+ source has `W<0`,
   `F_z+=-Q`; uniform z− return also has `W=-Q/A_return<0`, `F_z-=+Q`.
   Derive `Q` from the actual applied source each step and verify measured
   face-flux cancellation and cell divergence after correction. The
   crossflow fixture prescribes liquid `(-50,0,-4.8) m/s`, background
   `(-50,0,0) m/s`, gravity `(0,0,-9.81) m/s²`; quiescent liquid is
   `(0,0,-4.8) m/s` with zero background/gravity. These are this diagnostic's
   signed Cartesian coordinates, not the papers' coordinate conventions.
   The crossflow `dns.in` still says `inivel=zer`; z-face tangential values
   alone cannot initialize interior `U=-50 m/s`. Verify that the new helper
   fills the complete staggered interior, that halo/device states receive
   that field, and that actual initial-field diagnostics show the intended
   uniform velocity. A matching string in the source is insufficient.
5. **Make hidden physics choices explicit.** The current synthetic inputs
   use `rho_L=1000`, `rho_G=1 kg/m³`, `mu_L=1e-3`, `mu_G=1.8e-5 Pa s`
   and `sigma=0`. These are diagnostic constants, distinct from the E2
   provisional atmospheric state. Record that all body/bulk forcing switches
   are off except the declared gravity; review the `cfr` setting with
   `is_forced=false` against executable code. Freeze solver/pressure limits,
   continuity norms and exact Courant definitions; the CPU limits of 0.5
   and 0.25 and proposed 0.1% box residual remain unapproved until reviewed.
   Review found that fixed `dt` skips upstream `chkdt_tw`; the current
   candidate therefore does not supply the proposed Co/interface telemetry
   merely by choosing a small timestep. Add explicit per-step measurements
   on the velocity/phase states actually used for transport, with reviewed
   formulas and enforceable stop checks.
6. **Give the reviewer independent expectations.** Ten active intervals
   give `0.72 kg` per slot and `2.88 kg` for four slots, calculated as
   `1000 × 0.15 × 4.8 × 10 × 1e-4`. The return face has `8.4 m²` area;
   candidate active return speeds are `-0.0857142857 m/s` for one slot and
   `-0.3428571429 m/s` for four. Uniform-fixture integrated vector momentum
   equals each dose times the prescribed liquid velocity. Verify these from
   actual geometric phase flux at its evaluation time and staggered velocity
   interpolation, not requested boundary values or post-step samples alone.
   Check schedule state `k` versus endpoint state `k+1` at every consuming
   solver stage, signs/area units, deterministic reduction and inactive-mask
   outflow alpha extrapolation. Retain signed histories for every face;
   periodic pairs must cancel and must not be misclassified as escaped mass.
   Candidate2 corrected candidate1's pulse-volume units (`0.00072 m³` per
   slot; `0.00288 m³` total) and axis orientation (short axis x, long axis y).
   Recheck those values from actual case hashes in every new candidate; do not
   inherit candidate2's static checks as runtime evidence.
7. **Release only a reviewed executable contract.** Define the dry, one,
   four and crossflow pass/fail rules, memory/VRAM/wall limits, image/input
   checks, failure exits and expected output schema before the first solver
   call. Primary schedules stages in order and stops on the first failure.
   Any correction after a failed attempt gets a prospective versioned
   amendment, reviewer decision and new run; failed bundles stay unchanged.

The independent transition tests and later runtime diagnostics must implement
this state table. `U_0` is initialized with the inactive state; alpha/property
fills for transport use interval `k`, while velocity setters that prepare and
preserve the next projection use state `k+1`.

| Solver step `istep` | Transport interval `k` | Corrected velocity consumed by VOF | Source alpha/phase state during transport | Next corrected endpoint state |
| ---: | ---: | --- | --- | --- |
| 1 | 0 | `U_0`, source off | Off | `U_1`, off |
| 2 | 1 | `U_1`, source off | Off | `U_2`, on; source/return imposed before its projection |
| 3 | 2 | `U_2`, source on | On | `U_3`, on |
| 12 | 11 | `U_11`, source on | On | `U_12`, off; source/return shut off before its projection |
| 13 | 12 | `U_12`, source off | Off; retain interior liquid | `U_13`, off |
| 14 | 13 | `U_13`, source off | Off; retain interior liquid | `U_14`, off |

A successful `0.0014 s` synthetic box can demonstrate that pulse/return
implementation and its ledger behave as declared. It cannot establish
long-duration stability, air entrainment, breakup, external-flow accuracy,
resource scaling or aerial delivery. The subsequent 1–3 million-cell pilot
is a separate experiment with a separate review and budget.

## E1 first, with E2 preparation in parallel

The [E1 source record](../experiments/E1_ROUAIX_CASE1_SOURCE.md) identifies
Rouaix Case 1: one `0.4 m` round nozzle, `10 m/s` water, `70 m/s` crossflow,
realizable `k-epsilon`, water/air properties and surface tension from Tables
2–3 (PDF p. 5), and the wall/domain/outlets from Section 3.2 (PDF p. 7).
The GPU source fixture is not this case. The CPU candidate's P1 pass proves
neither the required turbulence/wall setup nor the Case-1 field observables.

Do not wait indefinitely for the authors before making the next decision.
The E1 draft already offers a concrete reconstructed comparison: source-like
five-second run, `4.5–5.0 s` observation window, full transverse cloud span
at `chi=0.1`, explicit initialization and turbulence mapping. A separate
reviewer must decide whether those assumptions and their sensitivities are
acceptable. Fig. 13 has no published sampling window; the near-nozzle
`z≈d_j` statement supports, but does not prove, full-width extraction.
Fig. 16's `q=17.3` marker is shared by Cases 1, 8 and 9 and remains contextual.
The cross-case empirical fits are secondary checks, not replacement targets.

The primary must record either an accepted reconstructed E1 contract or a
descriptive-only decision. An accepted contract still needs a solver feature
audit, measured resource profile, full-domain boundary check, source and
inventory conservation, two nearfield resolutions and a time-step check.
The nominal 30/16 mm local refinements and 1/0.5 ms steps in the draft are
subject to that review. Do not assume uniform full-domain cell counts or
promise a five-second cost from P1. An early roughly `0.4 s` breakup-time
diagnostic is not the final Figure 13 observation window. A descriptive or
inconclusive E1 result does not advance the E2 scientific gate; any proposed
change to stage order must be an explicit plan decision, never a renamed run.

Meanwhile, make the [E2 draft](../experiments/E2_E3_PROVISIONAL_REPLAY_DRAFT.md)
reviewable using the [E2 source record](../experiments/E2_CALBRIX_SOURCE.md):

- Keep both Fig. 4 input histories as separate `0.5 s` runs, each scored
  against both Fig. 6(b) target reads. Keep all four comparisons visible;
  do not average inputs, targets or outcomes. Freeze profile extraction,
  support coverage, interpolation, normalization, landmark rules and limits.
- Keep `4.44 × 0.30 m = 1.332 m²` as the sole proposed nominal geometry,
  explicitly inferred. The `0.666/2.664 m²` cases are non-gating project
  sensitivities, not source uncertainty bounds or alternative fits.
- Retain the declared provisional `rho_G=1.225 kg/m³`,
  `mu_G=1.7894e-5 Pa s` and `g=9.80665 m/s²`, and the paper's omission of
  surface tension. Freeze signed frames, body/domain placement, boundaries,
  turbulence and initial conditions. A uniform scalar source remains an
  approximation because `U_L` is called both mean and maximum in the paper.
- Convert the correlated timing/ordinate read allowances into a reviewed,
  coherent perturbation model and named sensitivity cases. A proposed method
  can use shared calibration/time shifts and coupled ordinate changes tied
  to the digitization method; review support at `t=0` and `0.5 s` explicitly.
  Do not extrapolate a trace beyond its support, independently jitter knots,
  or construct a pointwise envelope that no physical history follows.
  Two nominal history runs alone do not propagate this uncertainty.
- Keep Fig. 8's `0.5/1.0 s` conflict outside this finite-window Fig. 6(b)
  gate; Fig. 9 remains secondary. The nonzero late tail of the longer E2-HIST
  trace does not establish complete payload or shutoff.

E3 preparation follows its [source record](../experiments/E3_CALBRIX_CL415_SOURCE.md).
Independent traces are already available; the next work is geometry/group
mapping and a supported source window, not another nominally independent
copy of the same curves. Retain four distinct patches and the Fig. 4
legend/prose conflict. Fig. 11 counts liquid structures detected by an
unpublished Matlab procedure; reproducing its trace is not equivalent to
reproducing its object detector or a parcel population.

## Work agents can do now, and data valuable from the user

No new user input is required for candidate5 producer/analyzer preparation,
E1 static preparation, or the reviewed E2 implementation. The following data would
remove later scientific limitations. Request only
specific missing items when their absence changes the next stage; do not ask
the user to reauthorize provisional modeling. No messages to authors or
other third parties are part of this plan without explicit authorization.

| Data packet / needed from user if available | What agents can do with current sources | What the packet would unblock |
| --- | --- | --- |
| Rouaix Case-1 setup/post-processing files or author clarification of Fig. 13 timing/width, Case-1 breakup and inlet turbulence quantities. | Prepare and review the expressly conditional reconstruction already in the E1 draft. | A more source-resolved numerical comparison and removal of specific reconstruction assumptions; not field validation. |
| Calbrix outlet CAD/polygons, active areas, four-port grouping, spatial velocity/flow histories, source end times and detailed BCs. | Preserve all published reads and build audited geometry/source hypotheses and sensitivities, without tuning. | Exact source mapping for E2/E3; supported total release mass and terminal histories. The paper says flow-rate measurements are confidential, so availability cannot be assumed. |
| M134 cup locations/volumes/uncertainties, collection interpolation, outlet history/geometry, actual track/attitude and wind convention. | Prepare descriptive Fig. 4 contour and Fig. 9 profile comparisons with independently reviewed extraction and preregistered registration. | A matched E4 measured-map test with justified uncertainty. The currently adjusted figure origin cannot supply an absolute trajectory. |
| AG600 six-group raw cups, release amounts/history, collection footprint/method and corresponding flight/wind metadata. | Transcribe Gu Tables 4–5, audit the collected-fraction denominator and keep measured values separate from the authors' reconstructions. | Matched E5 collection comparisons and, with cups, independent map reconstruction. Six scalar fractions alone cannot determine strip usefulness. |
| Built Restás outlet dimensions/spacing/normals; synchronized flow, pressure and valve traces; payload, flight path/attitude/height, wind, and timestamped calibrated footage. For foam: measured density, rheology, surface behavior and aeration state. | Prepare the authorized ideal four-slot constant-velocity water cases with plan dimensions and explicit sensitivities. | A claim about the actual device and an independent deposition/plume comparison. Water inputs do not validate foam or constant-pressure delivery. |
| A physically justified operational target width/coverage threshold and a specific matched payload/flight scenario, when selecting the eventual E6 comparison. | Retain `9 m` and `2.4 kg/m²` as the plan's illustrative scenario; prepare the shared score and sensitivity protocol. | A scenario-specific operational interpretation. It does not itself establish suppression effectiveness. |

The E4 reference is [Amorim M134](../experiments/E4_AMORIM_M134_SOURCE.md),
DOI `10.1071/WF09123`: Table 2 on PDF p. 3, Fig. 4 on p. 6 and Fig. 9 on
p. 11. `Vx` is a cross-track column-volume sum, not a running cumulative
curve. Keep profile, contour and threshold-strip metrics separate.

The current E5 source handoff is the Gu entry in [REFERENCES.md](REFERENCES.md)
and [VALIDATION.md](VALIDATION.md), DOI `10.1071/WF22055`, local
`Study on the ground fraction of air tankers.pdf`: six conditions in Table 4,
PDF p. 8, and measured/reconstructed fractions in Table 5, p. 9. The measured
values are `42.20, 43.22, 41.35, 42.52, 44.31, 42.08%`; the paper's
post-processing estimates are `46.21, 45.40, 44.95, 44.08, 47.99, 45.07%`.
These are source results, not local E5 outputs. Preserve all source PDFs and
their names unchanged.

## Parallel assignments and shared compute budget

Use at most three concurrent workers **in total**, plus the primary, regardless
of model. Implementation/research assignments use `gpt-6-luna` with `max`
reasoning. The user specifically assigns blocker planning, general review
and project-warden work to `gpt-6-astra` with `max` reasoning. Use a fresh or
limited context (`fork_turns=none` is suitable), explicit model/effort and the
task's source/context packet. If a requested configuration is unavailable,
report it and continue useful primary work; do not silently substitute a
worker model. Rotate or reuse roles as slots become free: three Astra roles
cannot run concurrently with extra Luna workers. Worker-slot concurrency is
independent of CPU processes, MPI ranks and GPU jobs, which still require the
shared compute budget below. Workers do not recursively delegate or schedule
simulations.

| Wave / worker | Objective, sources and exclusive ownership | Interface, resource allocation and required handoff |
| --- | --- | --- |
| **Completed — candidate6 H4 successor** | The explicit-slice two-halo positive and shifted whole-array negative tests passed; Astra Max exact follow-up accepted the bounded H4 scope. | Evidence is under `containers/flutas/candidate6/evidence/dzf-two-halo-20260925T143734Z/`; no build, source solver or GPU run. |
| **Completed — DNS/VOF input audit** | Luna read-only extraction verified all 15 fixture hashes and mapped the 29 DNS/8 VOF typed records and cross-file relations. Primary accepts the memo for H3 proposal drafting, not parser acceptance. | [`DNS/VOF audit`](reviews/DNS_VOF_TYPED_SCHEMA_AUDIT_20260925T1443Z.md), SHA-256 `e7709cc54e5ecbb623062fcba6f30f420d6c2c17048866cf9db25f756e917c47`; annex draft is pinned in v0.3. |
| **Completed — Luna Max candidate5 M3 arithmetic evidence** | Bundle compiles the exact helper under production flags and independently checks normal reciprocals, corruptions/nonfinites, serialized bytes, 15 timestep rows and offline analyzer integration. It does not disposition H2. | `containers/flutas/candidate5/evidence/producer-arithmetic-20260925T1421Z/`; 403/403 inventory entries verify; inventory SHA-256 `6f2c96cd0d96953670cb263c2362ba149a21edcf204b71165ec75cee43617b49`. Ordinary runtime rejected the subnormal probe at the positivity guard; the reciprocal-overflow branch appears only in altered-MXCSR diagnostics. Astra exact review is queued. |
| **Active 1 — Luna Max candidate5 raw-roster audit** | Read-only mapping of ledger call order, raw-array capture sites, shapes/halos, stage/stop prefixes and static output size for the H5 annex. | 1 CPU / 4 GiB; no code/tests/build/solver/GPU. New memo distinguishes existing runtime bytes from proposed instrumentation. |
| **Active 2 — Astra Max Warden 13** | Periodic read-only big-picture audit after two accepted bounded handoffs (candidate6 H4 and DNS/VOF schema extraction). | One of three worker slots; no compute or GPU. Primary archives memo and dispositions. |
| **Completed — H7 outer-runner lifecycle audit** | Luna's read-only code audit confirmed `run_local.py` releases `flock` after killing only the client process group, with no Docker `State.Running` or child verification. Primary accepts it as implementation detail, not a fix. | [`H7 code audit`](reviews/RUN_LOCAL_H7_CODE_AUDIT_20260925T145043Z.md), SHA-256 `c7b763c7dab463b498e851b19f10b8cc9a28d96bf31d28f1cfdb4fd3dc57f513`; code/tests remain pending. |

The candidate5 exact review
[`FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md`](reviews/FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md)
and general contract review
[`PROJECT_GENERAL_REVIEW_20260925T1245Z.md`](reviews/PROJECT_GENERAL_REVIEW_20260925T1245Z.md)
are complete. Warden 10 and 11 are archived at
[`PROJECT_WARDEN_20260925T1300Z.md`](reviews/PROJECT_WARDEN_20260925T1300Z.md)
and [`PROJECT_WARDEN_20260925T1340Z.md`](reviews/PROJECT_WARDEN_20260925T1340Z.md).
Warden 11 and 12 are archived above; Warden 12 completed at 14:14 UTC, and its
recommendations have been disposed in the current queue. Since Warden 12, the
candidate6 H4 follow-up and H3 typed-record extraction have both been accepted
at their stated bounded scopes; the scheduled Astra Max Warden 13 checkpoint
will assess the refreshed critical path. The Astra Max blocker plan and exact
candidate6 follow-up review are complete. The E1 packet is a completed handoff,
not an active worker. Once the Warden slot is released and the v0.3 annex set
is complete, assign Astra Max general review of the exact contract snapshot;
then rotate that role to a repository-wide consistency review if the next
evidence snapshot warrants it. The primary owns
shared status, interfaces, gate decisions, CPU/GPU queues and launches. Workers
own only their assigned files and do not alter the Git index or another task's
deliverables.

The primary owns `docs/STATUS.md`, this plan, `docs/VALIDATION.md`, shared
interfaces, gate adjudications and launch decisions. Each actual task packet
must include objective, input locations, owned files, public interface,
dependencies, CPU/RAM/GPU/wall allocation, tests and handoff evidence. No
worker concurrently changes the Git index or reverts another worker's work.

Before assigning compute, rerun `make doctor` and inspect active jobs. The
25 September 14:46 UTC `make doctor` snapshot is 20 effective CPUs, 117.6 GiB
available RAM, 260.0 GiB free disk, and one RTX 5090 with 31.8 GiB VRAM.
`nvidia-smi` at 14:46 UTC reports 0% utilization, 16 MiB used and 21.32 W;
the GPU queue is ineligible, not waiting on compute. These are point-in-time
values, not reserved capacity. Keep two CPUs for responsiveness; on this
20-CPU host, at most 18 are available across all jobs. The H5 raw-roster audit
is the active Luna task; Astra Warden 13 is read-only. The M3 arithmetic bundle
is complete and awaits exact Astra review; the current collaboration runtime
refused a new reviewer dispatch at its thread limit. Worker caps are not
reservations.
More CPU saturation is not a reason to bypass review or start gated solvers.
Primary
must set RAM and wall ceilings from current headroom before a build/profile.

Launch local jobs with `scripts/run_local.py`; all GPU work uses `--gpu` and
its lock. Start source solver checks with one MPI rank on one GPU. At most
one GPU job runs, with only separately budgeted light CPU work overlapping.
The lock does not reserve VRAM against external processes. In MPI or process
sweeps, keep BLAS/OpenMP threads at one and count every rank/process against
the shared budget. Do not combine an 18-rank run with three unaccounted worker
jobs. Host `nvcc` is absent; use the pinned container instead of modifying
drivers, system solvers or global settings. Cluster access is not established.

For a later 1–3 million-cell pilot, freeze a few-hundred-step budget, sparse
3D snapshots, compact diagnostics and checkpoints. Measure peak RAM/VRAM,
step-time distribution, pressure and I/O shares, actual physical-time
throughput, mass/interface error, checkpoint size and restart cost. Only then
project one physical second or propose 5–10 million cells. An unaffordable
projection is a useful stop result; more cell count is not a validation gate.

## Reporting completion and scientific progress

**Repository/workflow readiness** can advance now: reproducible candidate,
reviewed protocols, source packets, immutable provenance, reliable diagnostics
and correctly staged launchers. Close those tasks when their actual artifacts
and checks pass; do not leave them waiting for unrelated built-device data.

**Scientific progress** requires the next accepted experiment: E0 is passed;
E1 comes before E2, followed by E3 and the ground-evidence E4/E5 stages, then
E6. Preparatory code, source review, a build, a short pulse diagnostic and a
render do not pass those stages. B8's conservative descent/handoff work is a
dependency of ground prediction, with direct VOF and coupling decisions
supported by evidence. A conditional numerical E1/E2/E3 comparison retains
its assumptions; it does not become field validation through workflow maturity.

For each handoff the primary reviews the combined diff, runs affected checks
and `make check` when integrating code, resolves independent findings, and
updates STATUS with the exact active gate, run process/path if any, immutable
evidence and remaining blockers. Retain code/input hashes, revision and dirty
state, dependency/solver/image versions, seeds, mesh/time settings, resources,
raw observables, mass/momentum residuals and pass/fail/inconclusive/not-run
decisions. Never overwrite failed attempts or grant retrospective tolerance
changes. Keep all changes local unless publication is requested.

For later ground comparisons, use one scoring implementation for both designs:
longest continuous qualifying `L95`, partial-cell area weights, capped useful
dose only inside that interval, deterministic ties, and explicit undefined
gain when the control length is zero. Keep deposited inside/outside-map,
airborne VOF/parcels, escaped and modeled evaporation mutually exclusive;
cumulative handoff flux is not stored mass. Preserve absolute impact times,
coordinate transforms, positions and weights. The current project has no
validated E4/E5/E6 ground result, built-device result, foam validation or
fourfold gain.
