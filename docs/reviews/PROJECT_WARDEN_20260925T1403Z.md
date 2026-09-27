# Project Warden checkpoint 12

**Astra Max / max, advisory; observation window 2026-09-25 14:08–14:14 UTC.**
The filename retains the primary's assigned checkpoint timestamp. This memo
approves no contract, candidate, numerical limit, source case, launch or
scientific gate. I read the project instructions and Warden role, experiment
plan, workflow/compute/validation contracts, current status/blocker records,
Warden 11, the v0.1 contract review and v0.2 proposal, successor exact review,
smoke/F1 primary disposition, provenance erratum, and new candidate6/E1
handoffs. Inspection was read-only except for this memo: no tests, builds,
image exports, container starts, solvers or GPU jobs were launched.

The changed steering is concrete: **v0.2 repairs much of v0.1 but still cannot
serve as a complete, nonconflicting implementation interface.** Correct the
small prefix/clock statements and finish the typed raw/ledger/resource
interfaces before its exact acceptance review. Candidate6's bounded repair
now has successful CPU helper/build evidence and needs independent review;
the E1 decision packet is complete and needs primary disposition. These are
local engineering dependencies, not missing hardware or user measurements.
The successfully completed successor smoke and F1 repair should leave the
active queue. E0 remains the only completed E0–E6 scientific gate.

## Verified snapshot and narrow evidence boundaries

| Artifact | Observed SHA-256 |
| --- | --- |
| v0.2 proposal, opening and closing identical | `8965b0c1d58ba53252659d53ff7fcc0bd9fb41a2f82aeec4a65ea39d49281b32` |
| Unchanged parent schema v1.2 | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
| Candidate5 successor exact review | `9615e07d93e9c3d4e0bcd1b4a2373650419a56ba7f220ca3a90f96b2074c108c` |
| Primary smoke/F1 disposition | `d5c03c122274c37cd1335ddf14a7b6fdbc67df19a7e075788b57c649a75e613b` |
| Primary provenance erratum | `b67929bb1f52648eee1770f962277b5663a7fffacb1dd23ad195f5baf3ae5e2a` |
| E1 decision packet | `c1d57536656b4253d6a43813fe957b8fcf7017a8b3d6b80cbe8c5d1379212939` |
| Candidate6 handoff at closing | `fdc991e4dc729d3c758373e3e6b741b2313be1fa2a5918b6846cac2db7836a35` |

All **142** entries in
`results/runs/flutas-candidate-gpu-regression-20260925T135456Z-2137699/SHA256SUMS`
match actual bytes: 49,305,117 bytes hashed, no mismatch. The list itself
matches `4e1852edfb1f772665c23c45040c5ab83225184017b821a4f694feb34620d142`.
The bundle records 13:54:56–13:55:21 UTC, exit 0, OpenACC and two-rank
CUDA-buffer MPI checks, `sm_120.cubin`, normal bubble completion at step 1680 /
`3.001520526915884 s`, and `True True`. The staged case contains no
`source-boundary.in`; the archived preflight independently records its absence.
Thirteen GPU and eleven container samples parsed; maxima reported are sampled
extrema, not hardware peaks. The retained no-container sampler diagnostic
occurs at cleanup and is not missing in-run evidence under the reviewed smoke
runner. Do not erase it or reclassify this smoke by future source-monitor rules.

Read-only Docker inspection confirms the same local image ID
`sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`,
`linux/amd64`, empty `RepoDigests`, and `/bin/true` default entrypoint. This is
one successful **source-disabled runtime smoke of this exact image**, after
its separate exact review. It does not establish source/build-receipt
provenance, production arithmetic, H4 closure, B1-pre/B1-runtime/B2, source
resource use, a pilot or an E1–E6 pass. The erratum corrects the authoritative
main-driver locator and reports three embedded-source matches; this Warden
did not repeat image extraction. Neither that erratum nor the earlier
temporary OCI feasibility probe supplies the missing production receipt and
retained verified layout.

## Remaining exact-interface defects in v0.2

Line references below are to the frozen v0.2 hash above. These are bounded
amendment requests for the primary, not a substitute exact contract review.

| Finding | What improved, remaining defect, and required correction |
| --- | --- |
| **H1: contradictory initial-stop and slot-key wording** | The inherited event-prefix matrix and unclassified rate-abort treatment are useful. But lines 31–32 call the inherited **and v1.2 tables** header-only after an `initial_u0` failure. Schema v1.2:326–340,396–423 requires the complete failing **12-row velocity group**, with `state_index=0`, `transport_interval_index=-1`, `stage_id=initial_u0`; only its phase and timestep tables are header-only. The six inherited tables have zero data rows. Later v0.2 lines 63–69 do not cure the conflicting earlier sentence. Also line 37's interval keys `0..row_count-1` are wrong for the multi-slot source ledger: for S=4, 56 rows have intervals 0..13 repeated four times, not intervals 0..55. Freeze lexicographic `(interval,slot)` keys: row r has `(r//S, 1+r%S)` for S>0; S=0 has no rows. Require explicit header flushes before the first possible stop, as requested by v0.1 review H1; the inspected candidate5 header writer does not explicitly flush them. |
| **H2: meanings mostly repaired; two scope qualifications remain** | Masked inward phase rate, signed total bottom flow, interval inventory and distinct diagnostic/native clocks now match the inherited source. However line 101 applies `[2,12)` to all source rows while retained v0.1:61–62 makes dry `[0,0)`. Qualify `[2,12)` as the positive source fixtures. Explicitly assign native accumulated solver `time_s` to **both** mass and velocity ledgers; the table currently states it only for mass. Freeze final-state/native-time predicates for normal and partial endpoints, rather than leaving an implementer to infer them from the source. |
| **H3: source lexer specified; DNS/VOF typed interface still implicit** | The source-file regex, physical-record, integer-range and underflow rules are substantial progress. Lines 130–144 refer to DNS/VOF “declared typed records” without actually declaring their record types/counts or a hash-pinned normative record schema. The allowlisted fixtures have 29 DNS records and 8 VOF records; their comments are not a typed parser interface. Freeze each record's field names/types, logical/identifier vocabulary, numeric conversion and expected cross-file equalities, or reference an exact separately versioned schema containing them. Exact fixture hashes remain necessary but do not replace the differential reader/parser interface requested by H3. |
| **H4: explicitly open, with new bounded implementation evidence** | v0.2 correctly refuses to treat the smoke as spacing-index closure and requires nonconstant-spacing compiled evidence. Candidate6 now supplies a proposed repair, helper output and native compile. Only its assigned exact reviewer can close the implementation finding. No contract text or Warden disposition closes H4. |
| **H5: capture intent improved; executable raw/ledger schema still missing** | Paths, byte-preserving copies, separate manifest, directional capture and pre/post-clipping intent are now stated. But lines 181–200 do not pin the six headers to a specific immutable producer identity, exact numeric/boolean/integer token grammar, manifest version value/top-level keys/types, expected raw-artifact roster, file encoding/storage order, role-specific shapes/halos, or stop-stage presence matrix. A list of metadata each artifact must self-declare cannot independently establish what artifacts should exist. “Reject duplicate roles” is ambiguous when the same role legitimately recurs at different states/stages; define the composite identity. Separate a required-artifact flag from `captured`/`not_reached` status and define whether size/hash/path are present or absent in each state. Bind the full auditor dependency set, not an unspecified analyzer path. Freeze these interfaces, with a small complete example and each-stop examples, before separate producer/auditor implementation. |
| **H5 / limits: zero rules are not yet frozen** | Lines 209–210 explicitly leave absent-phase cells, stages and zero rules pending, while lines 298–299 claim formulas, primitive operands and zero rules are frozen. Retained v0.1:161–166 still asks for normalization denominators, zero-mass behavior and momentum interpolation/reduction definitions. H2 does not supply them. Numeric acceptance values can remain pending during implementation; observable definitions, required operands, units, denominators and zero behavior cannot. Distinguish those two kinds of pending work and remove the false “frozen” statement until the interface annex exists. |
| **H6: identity route repaired at design scope, production acceptance open** | Preserving native OCI bytes, separating config/manifest identities, ordered DiffID verification and authoritative Git provenance address the previous direction error. No new registry or converter search is needed. Receipt field names/types/path conventions and the selected manifest/platform rule still need an exact schema or pinned tool interface for independent implementation. The retained layout, authoritative full build receipt, tamper tests and independent verification remain deliverables; the successful local-image smoke cannot substitute. Record Git blob object IDs separately from SHA-256 of blob contents. |
| **H7: bootstrap cycle removed, stop timing still conflicts** | The first-diagnostic prospective envelope correctly precedes the larger pilot. Line 270's **15:54 UTC** snapshot is actually the **13:54 UTC** pre-smoke snapshot; primary confirmed local `nvidia-smi` time was mislabeled. More materially, ≤2 s threshold overshoot at lines 286–287 is not compatible as written with allowed sample gaps of 5 s and subsequent 10 s grace plus up to 30 s termination. No predictor or bounded growth rate makes “predicted hard-cap crossing” testable. Freeze separate sample/liveness, detection, stop-signal, forced-kill and verified-termination deadlines; distinguish hard-enforced memory/CPU limits from sampled VRAM/disk stops. Specify cgroup-memory accounting, per-device/process VRAM attribution, disk roots/inclusions and startup/shutdown sample validity. Preserve the lock until termination is verified. These are interface defects, not objections to the proposal's numeric capacity values. |

For H1, the candidate5 patch's source-row writer at lines 831–863 directly
confirms the repeated interval key and slot order. The inherited velocity
writer at lines 991–994 confirms its native clock. The accepted v1.2
three-table schema must remain unchanged unless a prospective amendment is
separately reviewed. A corrected companion must not silently add six ledger
keys to that manifest or convert an unclassified rate abort into a controlled
stop. Preserve the current v0.2 draft and its findings when freezing its
successor; avoid another broad review of unchanged evidence.

## New handoffs and immediate owner assignments

Candidate6's final patch hashes to
`3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee`.
I read its passing helper log in
`containers/flutas/candidate6/evidence/dzf-lower-bound-20260925T141008Z/`
and native build in `evidence/native-build-20260925T141014Z/`: exit 0,
`sm_120.cubin`, executable hash
`80cea6c09773a24441e4c990a790d79880b71b2e20d60cc3d9f368c0ea8bce5a`.
The build log hashes to
`993b9e29c80128b5fdbf5404b5f29d5215fa03d39a566a6007d3de7b9f2b02f3`.
The preceding 14:06:11 build failed on Fortran statement ordering; the worker
reports that a new-file patch hunk undercount dropped the final include lines.
The successful retry and new hunk-count assertion follow that preserved
failure. This was compilation in an ephemeral container, **not a newly
packaged immutable runtime image or source runtime evidence**. The handoff
describes a one-halo driver; the exact reviewer should explicitly check the
requested harness-call compatibility and shifted-index negative control,
without assuming they are covered by the pass message.

| Next bounded action | Responsible owner / dependency / exclusive scope | Acceptance or stop evidence; resources and GPU status |
| --- | --- | --- |
| Finish the companion interface | **Primary**, using the table above; own a successor contract plus referenced typed schema/annex. The broad critical path is already known. | Concrete DNS/VOF and ledger/raw/receipt schemas, exact prefix examples and consistent monitor state machine; then **Astra exact contract reviewer** pins the final bytes. Document work now; GPU blocked by B1-pre/B2 and exact launch gate. |
| Review candidate6's exact H4 repair | **Astra general/exact reviewer**, after primary receives the final handoff; own a new review memo, no implementation files. | Verify exact patch application, all caller layouts, nonconstant independent integrals and shifted-index negative; distinguish helper compiler flags, native build and packaged image. Any missing evidence becomes a bounded Luna follow-up. Source runtime stays blocked. Initial review read-only; any authorized helper rerun 1 CPU / 4 GiB. |
| Close the separate production-arithmetic/evidence gap | **Luna producer-evidence owner**, after current candidate6 handoff/review fixes are scoped; use a fresh CPU evidence directory. This is newly explicit in the successor exact review, not closed by H4 or the smoke. | Exercise the relevant production arithmetic flags, corrupted individual reciprocal operands and exact operation order; retain generated helper, commands/tool versions, external analyzer/fixture hashes, raw emitted timestep bytes, supplemental tables and analyzer report. Source-disabled smoke does not test these routines. Primary budgets 1 CPU / 4 GiB initially; any native compile uses its separately reviewed ceiling. No solver/GPU. |
| Turn E1 packet into decisions | **Primary**, then **independent E1 reviewer**; packet `E1_CHARACTERIZATION_DECISION_PACKET_20260925T1356Z.md` is complete. Keep future implementation ownership separate. | Dispose the D-NUT/contact-angle/capture/initialization proposals and prospective successor input hashes. The packet identifies a timestep/Courant compatibility check for the proposed finest cells; resolve prospectively against actual mesh before characterization. This memo does not deep-review or accept its physics. Source/code review 1 CPU / 4 GiB; no mesh/solver/GPU until its own approvals. |
| Implement independent engineering branches after interface freeze | **Primary provenance owner** plus disjoint **Luna parser**, **raw producer**, **independent auditor**, and **supervisor** tasks, rotated within available slots. These are separate prerequisites and need not wait serially for an OCI export to finish. | Frozen interfaces and exact compiled/differential, raw-corruption, receipt-tamper and fake-stop evidence. Schedule one bounded CPU task per owner; export is streaming CPU/disk work with an explicit temporary/retained disk budget. Source GPU remains blocked until the combined release review. |

The successor review's production-flag and lost integration-byte findings
must be tracked explicitly. The old log proves a compiled timestep join ran;
it does not recover its historical external analyzer hash or deleted bytes.
A new retained CPU bundle resolves this without rerunning any GPU smoke.

## Standing Astra roles, queues and cadence

The requested standing `blocker_planner` and `general_reviewer` role files
already exist and pin **gpt-6-astra / max**. Project config retains Luna Max
defaults and the three-worker ceiling; it does not itself document maintained
role ownership or an assignment cadence. Current AGENTS/WORKFLOW describe
bounded invocation and rotation. The primary should record the new standing
role policy locally, name reusable role owners in the queue, and continue
explicit model/effort task packets. Do not infer role occupancy or model choice
from the default alone, or change global Codex settings.

At the opening live roster, candidate6, E1 preparation and this Warden occupied
all three worker slots. By the closing roster, E1 had completed and its slot
was already reassigned to **`astra_blocker_plan_20260925`**; candidate6 was
finishing its handoff, and this Warden remained active. This is productive
rebalance. Release this Warden promptly for the standing **Astra general
reviewer**, initially assigned candidate6 exact review and then the corrected
contract. Give the standing **Astra blocker planner** a bounded updated
dependency/ownership plan for the remaining interface and production-arithmetic
findings, not a repeat survey of the broad critical path. Require ranked next
actions and acceptance evidence in its own timestamped memo. After the
candidate6 handoff, the third slot can handle the highest ready Luna
implementation/evidence task. The occasional Warden replaces one of those
three slots; two standing Astra workers, a Luna worker and a Warden cannot all
run alongside the primary under the current limit. Standing roles should
yield when their bounded handoffs finish rather than manufacture repeated
unchanged audits.

At **14:10:32 UTC**, `docker ps` was empty; the process snapshot showed no
project solver/export/build, and the GPU was **0%, 16/32,607 MiB, 20.42 W**.
The `nvidia-smi` displayed clock was 16:10:32 local, not UTC. The adjacent
**14:11:32 UTC** snapshot found 20 CPUs in affinity, **117.53 GiB** available
RAM and **236.67 GiB** free disk. The one-second whole-host CPU sample was
**10.51% nonidle**; it is not a project allocation or longer-term utilization
claim. An initial root-only cgroup read found no root `cpu.max`; inspection
of the actual process cgroup and its ancestors then confirmed `cpu.max=max`
and `memory.max=max`, with cpuset `0-19`. These are observations, not reserved
capacity. Retain two responsive CPUs and the shared 18-core ceiling; refresh
the resource doctor before the primary assigns new compute. Native build
caps were 2 CPU / 6 GiB / 900 s; E1 inspection cap was 1 CPU / 4 GiB.

The GPU queue is legitimately empty: the exact candidate5 successor smoke is
finished and should not repeat; candidate6 has no independently reviewed
packaged runtime candidate, and a source-disabled replay cannot exercise its
H4 repair. Source-mode diagnostics remain blocked by B1-pre/B2, raw evidence,
limits, provenance, supervisor/resource enforcement and exact launch review.
No approved ready source GPU job is being idled. Keep independent CPU work
moving; do not fill hardware by replaying unchanged or irrelevant trials.

Refresh the current queue/status entries from these handoffs. The observed
14:03 ledger still calls E1 preparation active and candidate6 preflight repair
pending; both have advanced. `BLOCKER_RESOLUTION_PLAN.md:17–31` duplicates its
role/authority introduction. `STATUS.md:119–124,273–279` retains older E1
capture-rename instructions alongside accepted corrected static artifacts;
distinguish the corrected static map from predecessor audit wording. The
`Evidence at this handoff` source-patch row in the blocker plan still ends at
candidate4, while the executive table correctly describes candidate5: label
that row historical or replace it with current evidence. Preserve historical
review files rather than accumulating competing executive summaries. Also
track the production-arithmetic finding explicitly instead of burying it under
“incomplete integration evidence.”

After primary disposition of this memo, record it as the last Warden check,
reset the completed-checkpoint count, and list the next trigger: two accepted
bounded deliverables with checks/evidence/disposition, a material
source/solver-interface change or gate transition, or a repeated critical-path
blocker. Candidate6 and E1 handoffs do not become accepted checkpoints merely
because a worker completed them. No new user-only dependency is required for
the next engineering actions. Measured built-system inputs and E4/E5 raw data
remain later scientific dependencies; all source and scientific gates retain
their existing closed dispositions.
