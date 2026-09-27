# Project Warden checkpoint 11

**Astra Max advisory steering; observation window 2026-09-25 13:40–13:50 UTC.**
This memo approves no candidate, source run, solver/GPU launch, numeric limit,
or scientific gate. The primary requested it after two disposed checkpoints
since Warden 10. I read AGENTS, the Warden role, the experiment plan,
workflow/compute/validation contracts, status/blocker records, Warden 10, the
candidate5 exact review, successor producer handoff, analyzer exact review,
source-release draft and its newly completed exact review. I also read the
new F1 handoff and primary OCI feasibility report. I performed read-only hash,
image/process/resource inspection; no tests, build, export, solver or GPU job.
Only this memo was written.

The critical path is now **exact successor review plus a concrete source-release
contract repair**, not missing hardware or measured Restás data. The previous
candidate5 source-disabled smoke remains complete. Its acceptance does not
extend to the newly built image, and neither image has source qualification.
E0 remains the only completed E0–E6 scientific gate: 1/7 by gate count, not an
estimate of remaining effort.

The producer successor handoff at
`containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/handoff.md`
is complete. All 15 entries in its local `SHA256SUMS` pass my read-only check.
The handoff reports 19 static/input, 16 compiled observability and four full
manifest tests; the compiled 15-state producer/analyzer join distinguishes
index-based time from accumulated AB2 time. Its native build contains
`sm_120.cubin`, patch `aabff805…`, executable `99cf345a…`, and image
`sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`.
Docker read-only inspection confirms that ID, linux/amd64, `/bin/true`, 24
rootfs layers and empty `RepoDigests`. These checks verify the cited identities,
not the scientific correctness of the repaired implementation. The separate
pre-build suite supplied inputs absent from two Dockerfile-only tests; keep
that distinction in review rather than reporting the build-only skips as full
integration coverage.

At closing, the successor exact reviewer reported an additional provenance
defect: the handoff's claimed upstream `src/main.f90` path is absent at commit
`598210616bebd51f7d51f61455f196e6f3479916`, and `ef4e55d8…` identifies a dirty
worktree file from an allegedly pristine checkout. I independently hashed the
actual commit object
`src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90` with `git show`:
`1d6450b3379b9995b0d69c0d8e22d8b038c66446ebd33066cfdffdf799616e22`.
The primary should append a corrected provenance receipt and recheck affected
source-order/build claims against authoritative commit objects, not directory
names or mutable checkout files. Preserve the old handoff as historical
evidence. This blocks source/build-receipt provenance acceptance independently
of the OCI export gap. The reviewer reports that it does not alter the narrow
local-image source-disabled smoke scope; that conclusion still belongs in the
reviewer's final exact disposition, not this Warden's authority.

The original analyzer M1/M2 findings are closed only for their reviewed hash.
The new F1 implementation handoff reports 57 focused tests, Ruff/format and
compile checks under 1 CPU / 4 GiB virtual-memory limits. Source, test and
implementation-note hashes match its **final** handoff. An intermediate
note/hash mismatch observed while the worker was finishing has been resolved;
do not carry it forward as an open defect. F1 still needs independent exact
review. It concerns malformed-evidence classification, not a demonstrated
false scientific pass. The analyzer still takes masks/schedules as caller pins,
so F1 closure alone cannot close production B2.

The source-release exact review returns **REVISE** at contract hash
`09419b40…`. It independently identifies valid-empty/prefix contradictions,
incorrect inherited rate/clock descriptions, an unenforced reader grammar,
shifted vertical-spacing indexing, incomplete raw/clipping/manifest evidence,
OCI conversion requirements and a circular first-run resource prerequisite.
The accepted five input inventories and quiescent order remain useful. These
are actionable local engineering findings; broad re-examination without a
bounded correction would repeat the blocker.

| Rank / blocker | Responsible owner, prerequisite and bounded files/action | Acceptance or stop evidence; CPU/GPU eligibility |
| --- | --- | --- |
| **1 — Built successor lacks exact review/runtime qualification.** | **Astra Max exact candidate reviewer**, already started at the closing snapshot. Freeze patch `aabff805…`, build bundle `20260925T132844Z-2122673`, image `73b7a60d…`, current reviewed wrapper identities and the exact analyzer dependency used by the join test. Own only a new timestamped review memo. Check H1–H3/M3 closure, actual compiler/arithmetic flags, embedded patch/executable identity and source-disabled control flow; explicitly disposition the new contract-review H4 as it affects each scope. | A hash-pinned narrow review must say whether the unchanged source-disabled wrapper may exercise this image. If accepted and other smoke prerequisites pass, the **primary** promptly schedules its single smallest source-disabled regression through the shared lock, with the existing reviewed 2-CPU/600-second envelope, absent source input, completion/verification markers and sampled resources. Stop on changed identities, source presence or a real failed stage. No source case is eligible from this row. Missing OCI source receipt is not automatically a blocker to the separately reviewed local-image smoke. |
| **2 — Analyzer F1 repair needs independent closure.** | **Astra Max analyzer reviewer**, next available slot; own only a new exact review memo. Inputs are the final `FLUTAS_ANALYZER_F1_HANDOFF_20260925T1342Z.md`, three corrected files and unchanged v1.2. Keep its scope separate from the six-ledger implementation. | Independently reproduce all four literal contradictory finite-pair cases in both tables; retain exact singleton/multiple-mismatch positive controls, mixed/both-nonfinite stops and M1/M2 negatives. Require structured rejection, no escaped arithmetic exceptions, focused checks and closing hashes. Review/test budget **1 CPU / 4 GiB**, sequential launcher checks. GPU **not applicable**. Do not wait for the entire source contract to close this bounded defect. |
| **3 — Source contract cannot yet serve as an implementation interface.** | **Primary**, using `FLUTAS_SOURCE_RELEASE_CONTRACT_REVIEW_20260925T1331Z.md`, owns an explicit successor of `experiments/FLUTAS_CANDIDATE5_SOURCE_RELEASE_CONTRACT.md` and its dispositions. Freeze exact lexical/typed grammars; native-to-canonical ledger names/headers/padding; stage-specific row/prefix and clock meanings; rate/sign/reduction semantics; raw capture and companion manifest interfaces; and first-run bootstrap resources. | A new exact contract review must close H1–H3/H5–H7 at interface scope. Numeric acceptance values may remain clearly pending during CPU implementation, but formulas, units, zero rules and required operands cannot. All values, enforcement and independent rationale must be frozen before any source launch. Light CPU/document work now; GPU **blocked by B1-pre/B2 and exact launch review**. |
| **4 — H4 shifts the inherited mesh operands.** | **Luna Max producer follow-up**, in a separately named successor directory such as `containers/flutas/candidate6/`, with only its patch/helper tests/evidence. Preserve the current built successor while its exact review runs. The source review identifies three `dzf(:)` helpers whose dummy lower bound remaps halo-indexed caller cells. This repair can be isolated before broader raw-capture work; strict reader implementation additionally depends on rank 3's grammar. | Correct the bound or pass the intended slice consistently at every call. Compiled one-halo and host-harness tests with nonconstant spacings must match independent face-area, volume/inventory and divergence integrals. Distinguish inherited Courant arithmetic from v1.2's captured inverse/multiplication order. Stop if the auditor must reproduce the wrong mesh to agree. Helper checks **1 CPU / 4 GiB**; native build only when separately scheduled, initially within the proven **2 CPU / 6 GiB / 900 s** ceiling. Exact successor review precedes any GPU check; source GPU remains closed. |
| **5 — Source/OCI receipt is incomplete, but local export feasibility is concrete.** | **Primary provenance owner**; archive the native export algorithm/verification and freeze receipt/launch-binding tools under `containers/flutas/candidate5/tools/` or a separate provenance-tool scope. Do not overlap the new producer patch owner. Correct the main-driver source locator from authoritative commit bytes and audit the receipt's upstream file identities. Use the existing native OCI layout semantics, preserving raw manifest/config/layer bytes. | Independently verify commit/path/blob identities, production layout, ordered descriptors, sizes/media types, platform, local config ID/DiffIDs, executable/patch and receipt hash. Test blob/config/manifest/index substitution, missing/reordered layers, corruption and changed bytes. Source release needs retained exact layout/receipt evidence; a temporary feasibility report alone is insufficient. **CPU/disk only, GPU not applicable**; stream hashing with one CPU and bounded buffers, budget archive/temp disk explicitly, then independently review. No registry upload, host toolkit installation or schema relaxation is presently needed. |
| **6 — Keep the scientific E1 branch moving independently.** | After the narrow exact-review wave, reserve a **Luna Max preparation slot** for a timestamped E1 characterization-decision packet, reading the accepted static package and `E1_CPU_SOLVER_CAPABILITY_AUDIT.md`; primary retains the shared gate. Bound it to D-NUT-BC/contact-angle choices, exact capture stages, mesh/initialization checks and proposed monitor/resource stops. | Every choice has pinned solver/source support or an explicit provisional label; missing source certainty has a supported sensitivity/descriptive fallback. Independent review precedes meshing/characterization. **1 CPU / 4 GiB**, source/code inspection only; GPU not applicable. Do not rerun the now-closed E1 static correction review or let FluTAS tooling indefinitely block this independent preparation. |

For rank 3, the valid-empty distinction is substantive. Normal dry completion
has zero `source-flux.csv` data rows because there are no slots; an initial
velocity-audit stop legitimately has only headers in all six inherited
ledgers. Missing files or truncated required rows remain structural failures.
Freeze the review's event-prefix matrix, not a single count based only on
`completed_interval_count`: pre-momentum and endpoint failures occur on
different sides of flux/inventory/velocity writes. An inherited rate-check
abort is currently an unclassified failed attempt, not one of v1.2's three
controlled-stop reasons. Flush initialized headers and test every prefix plus
each one-row truncation with fake executables.

The stored top rate is configured-mask inward liquid flow, not all top liquid
flow; the bottom rate is signed total-volume flow, including air. Off-mask
inflow, reverse flow and net quantities must remain distinct. Native mass and
velocity clocks still use the accumulated solver clock; v1.2 timestep time is
the separately frozen index coordinate. Declare joins without retrospective
time tolerances. Raw directional flux must be captured before shared arrays
are reused, and pre/post-clipping alpha is required to support a raw-bounds or
clip-mass claim. Three-table v1.2 objects cannot silently gain six extra ledger
keys: freeze a separately versioned, hash-bound conservation/raw manifest.

The first 537,600-cell, 14-interval diagnostic needs a **prospective** resource
envelope from current headroom, static memory/output bounds and conservative
wall allowance. Its measured usage can size subsequent diagnostics. The
1–3-million-cell pilot comes later and cannot be a prerequisite for the
diagnostic that releases it. A source-disabled smoke is not a source-resource
profile. Resource monitoring must specify gaps/overshoot and prove that the
actual child/container has stopped before the GPU lock is released. Scientific
limits remain separately justified and reviewed; neither utilization nor a
convenient inherited abort tolerance releases a source gate.

The OCI feasibility report at
`results/runs/candidate5-oci-layout-proof-20260925T1345Z/verification.json`
is primary-generated evidence, not an independent acceptance. It records
Docker 29.1.3 emitting OCI layout 1.0.0, one image manifest
`sha256:5d3d0117271bf8e7e987d316a863d4f3397a77049eb9cd1f3122c44d03b7bda3`,
config digest equal to image `73b7a60d…`, and 24 verified uncompressed raw
layer blobs whose hashes match the ordered DiffIDs. I verified the report's
identity and read its claims; I did **not** rehash the 25,230,840,320-byte tar.
For these uncompressed layers blob digest and DiffID coincide; that equality
must not be generalized to compressed layers. The native export already has
the required structure, so inventing a new converter is unnecessary unless a
later image/export proves otherwise. Preserve exact JSON bytes; do not
reserialize them to manufacture an identity. Empty `RepoDigests` is compatible
with this local route. The subsequently archived
`FLUTAS_OFFLINE_OCI_PRIMARY_PROBE_20260925T1345Z.md` explicitly limits the
result to feasibility. Its past-tense temporary-tar removal statement is
prospective at this closing snapshot: the primary's last message says cleanup
is still pending. Reconcile that inventory statement when cleanup occurs; it
does not change the review boundary. A retained, freshly verified production
layout remains necessary before receipt acceptance; deterministic re-export
and corruption checks remain open. Deterministic identity of exported bytes is
distinct from reproducibility of a fresh native build.

At the opening live-agent inspection, three workers were running: this Warden,
source-contract reviewer and Luna F1 repair. The producer had completed and
was absent from that list. By the 13:45 inspection, the source-contract
review was complete and its slot had already become the **Astra successor
exact review**; the Luna F1 worker was completed. Thus the two running workers
were Warden and successor reviewer, not three compute jobs. Capture/release
the completed Luna handoff; use the available slot for rank 2, and release
this Warden slot for rank 4 once its disjoint scope is assigned. The primary
can amend the shared contract and prepare provenance concurrently. When a
review ends, rebalance toward E1 preparation or approved independent parser,
raw-capture, auditor and supervisor tasks; do not leave a finished agent idle
while ready work exists.

At 13:40, a one-thread project analyzer pytest process was active under
`run_local.py`; it was gone by the 13:43 snapshot. At 13:43 `docker ps` was
empty and no project build, solver, export or GPU job appeared in the process
filter. An unrelated one-thread CPU workload was visible and must be included
in refreshed headroom rather than counted as project progress. GPU snapshot:
**0%, 16/32,607 MiB, 23.31 W**. Available RAM was about **117.4 GiB** and
filesystem free space **236.9 GiB**, lower than the older 260.4-GiB status
snapshot while the approximately 23.5-GiB export existed. These are samples,
not allocations or peaks. Retain two responsive CPUs and the shared 18-core
ceiling; refresh `make doctor` before the primary schedules new compute.
The ready tasks are principally interface/review work with small helper
checks, so 18 useful active compute cores cannot yet be assumed. One accepted
smoke can overlap independent CPU review/implementation through the sole GPU
lock; no artificial replay is needed to fill idle capacity.

The GPU queue has exact dependencies: the predecessor candidate5 smoke is
**finished** and must not repeat; the built successor smoke is **blocked by
its own exact candidate review**, currently running; all source diagnostics
are **blocked by B1-pre/B2, the repaired contract/candidate, independently
audited conservation evidence, frozen limits and exact launch review**. Later
source cases also depend on the previous case's accepted result. Frozen
crossflow inputs remain known-negative host/parser fixtures. The positive
source diagnostic sequence remains `dry_four → quiescent_one → quiescent_four`
with first-failure stop. The one/four-slot stages are not “source-free.”

The primary should refresh specific stale claims in the observed 13:37
documents, rather than appending another contradictory status paragraph:

- `STATUS.md:26,463–466,503,541–545` still treats producer/F1 work or handoff as
  active/pending; its Warden-due text omits this active check. Update from the
  closing handoffs and exact review state, preserving review-pending labels.
- `STATUS.md:273,285` still says E1 static artifacts await exact review, while
  the opening summary and inventory follow-up record narrow acceptance.
  Keep E1 execution closed, but retire the already-closed static correction.
- `STATUS.md:512` calls the positive source diagnostic sequence “source-free.”
  `WORKFLOW.md` and `COMPUTE.md` now have the correct quiescent order, so the
  old crossflow-sequence inconsistency need not be reworked.
- `BLOCKER_RESOLUTION_PLAN.md:50,120,122,124–125` retains obsolete E1 active
  correction/review, producer old-test counts and analyzer 29-test/awaiting-review
  states. Keep those as history only where explicitly dated; use the current
  successor/F1/contract findings for active blocker rows.
- Its active-worker table at lines 368–370 and one-checkpoint assertion at
  378–379 disagree with live slots and STATUS's two-checkpoint counter. The
  OCI gap is now **accepted production receipt/layout evidence absent**, not
  lack of a feasible local manifest route. Preserve older handoffs unchanged.

No current engineering assignment requires new user data, author contact,
cluster access, a second GPU, host `nvcc` or another permission request.
Measured built-device geometry and synchronized discharge/pressure/valve and
foam data remain necessary for built-system claims; E4/E5 raw cups and matched
release metadata remain later field-validation dependencies. Neither those
missing measurements nor the periodic FluTAS source box should block authorized
provisional E1 contract preparation. No present evidence establishes breakup,
descent, ground-map validity, the complete multiregion pipeline or fourfold gain.

Recommended primary dispositions: **accept** ranks 1–6 with their dependencies;
accept the concrete source-contract findings for bounded repair; **defer** all
source execution, E1 characterization and larger pilots behind their exact
gates; **reject** unchanged smoke/review repeats, premature scientific claims
and the pilot-dependent bootstrap. The current deblocker and the new detailed
source review already supply discriminating checks, so another broad blocker
planner pass is unnecessary now. Reinvoke it if an attempted strict-reader,
spacing or raw-evidence repair repeats the same blocker without resolution.

After primary dispositions integrate this evidence snapshot, reset the
since-Warden counter to zero. Do not count this memo's administrative integration
or redispose its already-covered handoffs as new checkpoints. **Next Warden
trigger: the earlier of two new primary-disposed bounded deliverables
(expected next: producer-successor exact review and analyzer-F1 exact review),
a material accepted source/raw/provenance architecture amendment, a repeated
repair blocker, or any source-run eligibility/gate change.** A smoke completion
is counted separately only when its prescribed evidence and primary disposition
are complete; coalesce simultaneous triggers over one snapshot. No ready
bounded implementation should wait merely for that future Warden.

| Exact artifact observed | SHA-256 |
| --- | --- |
| Warden 10 | `ad597e6e658f150cd8a264356f7c579b9bde22ba07aa2761413ecb137733164d` |
| Candidate5 prior exact review | `b5cf3036bf7a79a2ad4b149889faf10e3d407e169191b80c311c61e9e19cfd68` |
| Successor producer handoff | `a000cf9f444afca0c02010080ba74b96bff5405c5a4e60d1d15574535e015cbc` |
| Successor build `SHA256SUMS` | `ee104db1f5f328ab9e5822fefaeb075116cdefcc9439cd865a10e2894f207e1d` |
| Successor patch | `aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7` |
| Analyzer M1/M2 exact review | `b5606ebce5fea7e89f384a623f3e4a22ee6d236723fbca72eb9894e4eab6dd09` |
| Final F1 implementation handoff | `ac4898a9a4035da45fc41fedb0c698de6da41da02375c11aacc9e570e418fa40` |
| Final F1 analyzer | `9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37` |
| Final F1 tests | `b9ca3c50274a41454b8e9b2b9c587b3240ff0b94d82ce352eda7c0a08890ed20` |
| Final F1 implementation note | `e6a4d2776859e62f53c60fb0662c5264bf748ab5bf6b8a4169b66d26a6f64171` |
| Source-release v0.1 draft | `09419b40c4cfd4f6262f45a2ed184d303efb68adcfa86dfd451de52f0f397112` |
| Source-release exact review | `058a3d83de7c326f5f51ac8af58d54f8f0f4c28db20a595343fafb9f2df3d336` |
| Primary OCI feasibility memo | `9ee6860f44ec47a6f61f1048c26ad9da8fd8f36871f5709f263359d245211212` |
| Primary OCI feasibility `verification.json` | `25f146f4a47d2720e74531df97c10f5e4d736b951ff59e0038f0100e326eca92` |
| Observed 13:37 `STATUS.md` | `427762778040228db00f7f55ef11840cf29803b60a0971c20f57640e053e607e` |
| Observed 13:37 blocker plan | `5aa494a42677d11fefc97778428ff3fc91bcebf977d12a47063e20d230113207` |

Artifact hashes fix this audit's evidence snapshot. They are not approval of
later edits, the source implementation or any scientific outcome.
