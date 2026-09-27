# Remaining source-release blockers — Astra Max deblock plan

**Advisory only; inspected 2026-09-25 14:13–14:23 UTC.** The filename retains
the primary's assignment tag. This memo accepts no interface, implementation,
numerical limit, mesh, source run, GPU launch or scientific gate. Only this
file was written. No tests, builds, image exports, containers, solver or GPU
jobs were launched. Shared status, contracts, code and the failed attempts
remain their owners' files.

This is the bounded follow-up to
[`PROJECT_WARDEN_20260925T1403Z.md`](PROJECT_WARDEN_20260925T1403Z.md),
not another broad project survey. Governing inputs were `AGENTS.md`, the
blocker-planner role, experiment plan, validation/workflow contracts, current
status/blocker plan, v0.1 review, v0.2, schema v1.2, and the exact artifacts
below. **No new user or external data are needed for any action ranked here.**

## Verified changes to the working queue

Candidate6's H4 repair has completed CPU evidence. Its
[`HANDOFF.md`](../../containers/flutas/candidate6/HANDOFF.md), passing
`evidence/dzf-lower-bound-20260925T141008Z/test.log`, and
`evidence/native-build-20260925T141014Z/build.log` exist. The final native build
exited 0, contains `sm_120.cubin`, and records executable SHA-256
`80cea6c09773a24441e4c990a790d79880b71b2e20d60cc3d9f368c0ea8bce5a`.
The earlier target-delta preflight failure and hunk-count compile failure are
preserved. They are not the current build disposition. The successful command
used an ephemeral `docker run --rm`; no candidate6 executable, runtime image
receipt or OCI layout is retained in its assigned directory. This is build
evidence, not a packaged runtime candidate.

The candidate5 successor smoke already finished at 13:55:21 UTC with exit 0,
OpenACC/CUDA-buffer MPI checks, bubble completion at
`3.001520526915884 s`, and `True True`. I read its archived stage checks,
source-absence preflight and resource-validation record; Warden 12 separately
verified all 142 manifest entries. Its local image and source-disabled scope
remain fixed by
[`FLUTAS_CANDIDATE5_SUCCESSOR_EXACT_REVIEW_20260925T1345Z.md`](FLUTAS_CANDIDATE5_SUCCESSOR_EXACT_REVIEW_20260925T1345Z.md)
and the primary's 14:03 disposition. Do not repeat it to test source-only H4.
Analyzer F1 likewise has exact narrow closure; production B2 remains open.

The
[`E1_CHARACTERIZATION_DECISION_PACKET_20260925T1356Z.md`](E1_CHARACTERIZATION_DECISION_PACKET_20260925T1356Z.md)
is complete. It needs primary decisions and separate review, not another
extraction assignment. Read-only manifest verification passed candidate6's
4/4 pins, the source fixture inventory's 15/15 pins, and E1's 20/20 static
package pins. Those checks establish current bytes, not their scientific
acceptance. E0 remains the only completed E0–E6 gate.

## Ranked action sequence and exclusive owners

Ranks express critical-path priority, not a requirement to serialize
independent CPU work. Proposed new files below are assignment scopes, not
claims that artifacts already exist. The primary freezes shared interfaces;
each named implementer is one exclusive owner, with a different reviewer.

| Rank / severity | Smallest deliverable and exclusive owner | Prerequisite and exact acceptance or stop evidence | CPU/GPU eligibility and gate affected |
| --- | --- | --- | --- |
| **1 / High — incomplete companion interface** | **Primary** owns a preserved v0.2 successor plus typed input, ledger/raw, receipt and resource annexes. **Astra general reviewer** owns only its subsequent exact-review memo. | Close the enumerated corrections below; retain v1.2 unchanged. Freeze exact field/type/roster/stop examples and hash the entire normative set. Exact review must distinguish accepted implementation interfaces from still-pending numeric limits. Stop on any contradictory prefix, unspecified operand/zero rule, or self-declared raw inventory. | Document/static CPU work now. Releases bounded implementation interfaces only. Source GPU remains blocked by B1-pre/B2 and launch review. |
| **2 / High — H4 needs exact closure and directed evidence** | **Astra candidate reviewer** reviews the held candidate6 patch now. A **Luna H4 follow-up owner** gets only the review's test/harness corrections in a successor scope after that freeze. | Verify every caller's lower bound, nonconstant independent integrals, harness adapter or explicit harness retirement, and compiled shifted-index negative control. Preserve passing native-build evidence and all failed attempts. Exact review determines whether any production patch change is needed. | Review now; scheduled helper checks initially 1 CPU / 4 GiB. Changed native build only if necessary, 2 CPU / 6 GiB / 900 s ceiling subject to refreshed headroom. No source GPU; no meaningful H4 source-disabled smoke. |
| **3 / High — production arithmetic and retained integration** | **Luna producer-evidence owner** owns a fresh helper/evidence scope, not the currently reviewed patch. | Use the reviewed H4 source and exact upstream initialization; execute the relevant production arithmetic flags, reciprocal corruption cases and complete producer-byte/analyzer joins. Archive every generated operand/table and external dependency hash. Stop on any binary64-contract mismatch or unclassified result. | CPU prerequisite, initially 1 CPU / 4 GiB; native compile separately scheduled. No solver/GPU needed for these host diagnostics. Contributes to B1-pre and production B2; does not close either alone. |
| **4 / High — strict producer and independent staged-byte/six-ledger path** | **Luna producer owner** alone owns a new candidate patch, reader, raw captures and compiled producer fixtures. **Separate Luna auditor owner** alone owns new staged-input binding and raw/six-ledger modules/tests. Primary integrates calls to the existing reviewed analyzer. | Rank 1's accepted typed interfaces; rank 2/3 source findings resolved before the final producer freeze. Differential reader/parser tests, raw analytic/corruption fixtures, every stop prefix, and retained actual compiled output must pass independent review. Auditor derives expectations from staged bytes and authoritative initialization, never producer summaries. | Independent CPU implementation and tests can overlap, within the shared budget. Source GPU blocked by complete B1-pre/B2. No prerequisite to wait for a large OCI export before writing these modules. |
| **5 / High — no production receipt or retained export** | **Primary provenance owner** alone owns provenance/export tools and `candidate-build.json` schema/tool integration; final candidate packaging stays coordinated with the producer owner. | Accepted exact receipt schema; tool tests can precede final source completion. Final export waits for the actual reviewed production candidate. Retain executable, source/build identities, original OCI bytes, config-to-local-image mapping, all ordered layer checks, tamper results and separate verification. | Streaming CPU/disk work, initially 1 CPU with bounded buffers and explicit temporary/retained disk budget. GPU not applicable. Closes provenance prerequisite, not source physics. |
| **6 / High — enforceable supervisor and prospective limits** | **Luna source-supervisor owner** alone owns the new source launcher, fake-run tests and any explicitly assigned local-launcher integration. **Primary** owns the limits/resource decision record; **independent scientific reviewer** assesses it. | Rank 1's monitor/state machine and raw roster. CPU fake jobs prove lifecycle, prefix, hash, failure and no-next-case behavior. Freeze justified scientific limits and static output/resource arithmetic before final exact launch review. | CPU-ready after interface freeze. First GPU source case remains ineligible until all rows and exact launch review pass. The future profiling pilot is not a prerequisite to its bootstrap limits. |
| **7 / High for E1, independent of ranks 1–6 — dispose the decision packet** | **Primary** records D-NUT/contact-angle/density/capture decisions. **Luna E1 preparer** owns only the resulting successor static inputs and instrumentation preparation; **independent E1 reviewer** owns acceptance. | Reviewed successor input hashes before meshing; then actual mesh/initial-field evidence and a separate reviewed characterization contract. Resolve the packet's timestep/Courant conflict prospectively. Do not reopen closed static corrections. | Source/code review and static preparation now, initially 1 CPU / 4 GiB. Meshing and CPU characterization wait for their own decisions/budgets. GPU not applicable; FluTAS completion is not an E1 dependency. |

## Rank 1: finish the interface in one bounded amendment

Use Warden 12's exact finding table as the amendment checklist. The current
v0.2 hash is `8965b0c1…281b32`; do not silently reinterpret it while workers
implement different contracts.

1. **H1/H2 prefix and clocks:** an `initial_u0` failure keeps the complete
   12-row failing v1.2 velocity group `(state=0, interval=-1)`. Only phase and
   timestep tables, plus the six inherited tables, have zero data rows.
   Replace `0..row_count-1` for multi-slot rows with lexicographic
   `(interval,slot)`: row r is `(r//S,1+r%S)` for S>0; S=0 has no slot rows.
   Require explicit header flushes before the first possible stop. Positive
   fixtures use `[2,12)`; dry uses `[0,0)`. Both inherited mass and velocity
   `time_s` fields use the accumulated solver clock. Freeze the separate
   final-state, partial-endpoint, diagnostic-time and native-time predicates.
   Preserve the rate-pair abort as unclassified failure with its own exact
   retained prefix, not a new v1.2 stop reason.
2. **H3 typed fixtures:** supply the actual 29-record DNS and 8-record VOF
   field/type tables, logical/identifier vocabulary, numeric conversion and
   duplicated-field equalities. A comment-stripping rule and exact file
   hashes alone do not define the independent typed parser. Retain the precise
   source-file lexical grammar and exact five-case allowlist.
3. **H5 ledger/raw annex:** pin the six exact headers to an immutable source
   identity and declare integer, boolean and padded-real token grammars.
   Specify the companion manifest version, exact keys/types, byte order and
   storage order, composite artifact key, role-specific shape/index/halo
   rules, capture point, and complete expected roster for every normal/stop
   prefix. Separate requiredness from `captured`/`not_reached`; define missing
   path/size/hash fields for the latter. Include one complete normal example
   and examples for all stop classes. Bind the full auditor dependency set.
   Freeze observable formulas, momentum interpolation/reduction, denominators
   and zero behavior now; numerical acceptance values can remain pending
   until launch review. Remove the contradictory claim that these zero rules
   are already frozen.
4. **H6 receipt:** declare exact field names/types, canonical path rules,
   platform/manifest selection and source-object distinctions. Git blob IDs,
   SHA-256 of their contents, patched source and build-generated `main.f90`
   are distinct identities. Keep native OCI JSON bytes unchanged.
5. **H7 monitor:** correct the doctor timestamp to **13:54 UTC**. Define
   separate sampling, liveness/detection, stop-signal, forced-kill and verified
   termination deadlines. An allowed 5-second sample gap plus 10-second grace
   and up to 30-second cleanup cannot promise a 2-second hard-cap overshoot.
   Define measurable VRAM/disk triggers without an unspecified growth
   predictor. Distinguish hard CPU/cgroup enforcement from sampled stops,
   and declare startup/shutdown validity and resource accounting.

This is not a request to determine every later CFD tolerance before coding.
It is the minimum common interface needed for independent producer, auditor,
provenance and supervisor implementations to agree for the current fixtures.

## Ranks 2–3: close the discriminating CPU evidence first

Candidate6 changes exactly three `dzf(:)` dummies to `dzf(0:)`, plus a
Courant explanation and corrected new-file hunk count. Production passes
`dzf(0:nz+1)`; the new one-halo compiled fixture correctly makes halo and
interior spacings different. Its independent Python expectations cover areas,
inventory, divergence and inherited Courant. This is useful new evidence.

Two specific checks remain absent from that handoff. The test compiles once
at `-O0` and contains no compiled shifted-dummy negative variant. Also, the
inherited `candidate5/tests/source_boundary_validator.f90:19–23` allocates
`dzf(-1:nz+2)` and its ledger calls pass the whole array. Passing that array
unchanged to a `dzf(0:)` dummy still remaps its indices. The smallest follow-up
is a nonconstant two-halo caller test with an explicit intended slice/adapter,
or an explicit retirement/replacement of that harness; the primary and
reviewer choose one. Do not change production to imitate the old wrong mesh.
Compile the deliberately shifted variant and require the independent
area/inventory check to fail. Retain the generated helper, compiler command,
raw CSVs and expected values in a fresh evidence bundle; the current helper
test deletes its temporary compiled output.

The separate M3 finding is not closed by those tests. The successor review's
`M3` and integration-evidence sections explain that its host helpers omit
`-fast/-cuda/-acc`, while the native build uses them. Native build success
does not execute optimized reciprocal checks or nonfinite handling. The
H4 helper's `-O0` check also cannot establish the production arithmetic.

The next arithmetic bundle should exercise exact initialization/capture and
restriction helper bodies under the relevant production flags without a
source solver. Include all 42 vertical operands, both halo ends, individual
one-ULP reciprocal corruptions, nonpositive/nonfinite operands, zero-advection
fallback, finite guard pass/equality/rejection, both pulse edges, and U0–U14
index time against independently accumulated native time. Preserve compiler
version, complete flags, source/object/executable hashes and raw outputs.
Pin the external analyzer and fixture files before the run and retain them or
their reproducible inputs. Distinguish compiled phase/velocity output from
synthetic supplemental tables; a timestep-only join cannot be labeled a
three-table production integration.

If optimized operations violate schema v1.2's exact arithmetic, the bounded
fallback is to identify the first differing operation and prospectively pin
compiler-supported strict arithmetic for that path, then rebuild and review
the affected candidate. A genuine interface change needs a reviewed schema
successor. Do not add a post-result epsilon or loosen the reciprocal check.
GPU execution is unnecessary for the current host-side diagnostics; eventual
source runtime behavior still needs the combined release gate.

## Ranks 4–5: independent production, audit and provenance

Keep one producer patch owner. The strict reader and header flushes can share
that owner with directional/raw captures; a second worker must not edit the
same include concurrently. Freeze the binder's public output as an immutable
typed case plus actual byte hashes, masks, schedule and independently derived
scan plan. Derive initialized spacing/inverse expectations from pinned
initialization and compiler identity; compare them to captured runtime
operands instead of treating the capture as its own reference.

The existing `ExpectedProvenance` and `analyze_bundle` in
`src/aerial_drop/flutas_source_analyzer.py:228–239,1853–1878` still accept
caller pins and exactly three files. Build an outer production binder/auditor
around that narrow reviewed component. The new six-ledger/raw report should
separate structural validity, numerical evidence and scientific adjudication;
it cannot emit a scientific pass while limits are pending.

Capture directional phase flux before array reuse, the exact source momentum
operands, inventory alpha, divergence/Courant U/V/W states, and pre/post alpha
at each clipping site. Recompute slot/offmask and all-face transport, requested
and applied vector momentum, inventory change, signs/areas, periodic
cancellation and state/interval joins independently. Required tests include
analytic nonuniform geometry, sign/halo/stagger/mask perturbations, reverse
flow, absent-phase/dry zeros, clipping changes, reduction-order differences,
hash/shape/truncation failures and every H1 prefix. Neither summaries agreeing
with each other nor the same helper used twice is independent conservation
evidence.

For provenance, the local OCI route already has feasibility evidence in
`results/runs/candidate5-oci-layout-proof-20260925T1345Z/verification.json`.
The temporary 25,230,840,320-byte archive was not retained. Do not repeat a
large export of obsolete candidate5 merely to occupy the queue. Implement
and test the verifier first with small authentic-format synthetic layouts;
export the final packaged candidate once it exists. Preserve its original
manifest/config/layer bytes, ordered descriptors and uncompressed DiffIDs,
and verify the config digest against the local Docker ID. Bind the actual
executable, applied source, target-file delta, toolchain and command. Include
all Warden H6 corruption/substitution tests and authoritative commit-object
provenance from the append-only erratum. No registry, external account or
host toolchain installation is needed.

Budget exporter temporary storage and retained per-run layouts explicitly.
The known export alone occupies about 23.5 GiB before raw fields, logs or
copies. A proposed 40-GiB run cap must state whether those bytes are included;
neither undocumented deduplication nor replacing the required layout with a
digest-only reference satisfies the current contract.

## Rank 6: make resource stops and the source launch review executable

The v0.2 proposal is one rank, one application thread, at most two total CPUs,
16 GiB cgroup memory, 24 GiB VRAM, 40 GiB disk and 1,800 s. These are
**unapproved prospective ceilings**, not measured source demand or accepted
limits. Recompute static raw/output sizes from the frozen roster, include
receipt/layout/storage overhead, refresh `make doctor`, and independently
review the first-diagnostic envelope. Do not wait for the later 1–3M-cell
pilot; do not use the source-disabled smoke as a source profile.

There is a concrete launcher integration blocker:
`scripts/run_local.py:112–140,164–179` kills the command process group after
about one second on timeout and its `gpu_lock` context unconditionally unlocks
on exit. It does not verify Docker container state. Simply nesting a source
supervisor inside the old timeout path cannot implement H7's ten-second grace,
thirty-second verified cleanup and retained lock on unverified termination.
The exclusive supervisor owner must propose one source-specific lifecycle
integration in which the lock holder supervises cleanup through completion;
outer watchdog/interrupt behavior must use the same proof. If a durable
quarantine is proposed for lock-holder death, freeze and review its semantics
and checks in every GPU admission path rather than silently calling it a held
lock. Unknown cleanup status is a hard stop and primary escalation.

Acceptance is a retained CPU fake-executable/container matrix: normal/dry
completion; every legal controlled prefix; unclassified rate abort; truncation;
zero exit with fatal text; wrong endpoint/clock; changed staged bytes or
receipt; dead/NaN/missing/gapped sampler; resource trigger; timeout; Docker
client exit with surviving container; ignored graceful signal; and failed
termination verification. An invocation counter must show zero subsequent
case launches after any failure. Declare memory/RSS/cgroup meanings, VRAM
attribution, disk roots and sampling coverage; retain configured versus
observed values separately.

In parallel, the primary and independent scientific reviewer can freeze dose,
componentwise momentum, mass closure, offmask/return, divergence, raw alpha/
leakage, timestep margin and uncertainty/decision limits from analytical
expectations and numerical rationale. Inventory the producer's existing abort
thresholds separately; they are not automatically scientific tolerances.
The direct FFT/tridiagonal pressure route needs an exact `not_applicable`
iterative-residual decision plus finite/projection/continuity evidence.

Only a combined exact input/candidate/receipt/producer/binder/auditor/limits/
supervisor review may make the first source case eligible. The primary then
queues **dry_four → quiescent_one → quiescent_four**, one RTX 5090 job through
the shared lock, auditing and independently disposing each before the next.
B1-runtime is the outcome of these diagnostics, not their circular precondition.
Frozen 50 m/s crossflow cases remain CPU expected-negative fixtures; positive
crossflow needs its own prospective amendment of step/margin, dose, duration
and horizon. No later pilot or scientific advancement is implied.

## Rank 7: E1 can advance independently to a reviewable decision

The packet supplies specific provisional choices: calculated inlet `nut`,
high-Re wall functions, calculated open-patch `nut` with the existing zero
`inletOutlet` condition as an alternate, and a 90-degree `limit gradient`
contact-angle baseline. The primary should accept, revise or reject each
explicitly, with source/model-deviation labels and a predeclared sensitivity
trigger. A numerical boundary-limit alternative is not measured wetting-angle
uncertainty. No Figure 13 fit may select the choices.

Retain the accepted capture map's `alpha_preclip`, `alpha_postclip` and
`alpha_solver_final` stages, separate transported phase flux from clipping
mass, and remove stale predecessor stage names from the active successor
record. Before characterization, verify actual nozzle area/normals/layers,
mesh hash and `checkMesh`, zero-water initialization, and reconstructed static
pressure from `p_rgh`, density, gravity and reference position. The packet
identifies `70*0.0005/0.016 = 2.1875` as a prospective Courant conflict with
the proposed interface limit 1; settle mesh/timestep/stop compatibility before
launch. Its 1–3M cells, 300 steps, 0.15 s, 16 MPI ranks, 48 GiB, 30 GiB and
four-hour envelope remains planning only.

Missing exact Rouaix timing/width/wetting/model data supports a reviewed
reconstructed or descriptive comparison, not an automatic user block and not
an E1 pass. A short CPU characterization precedes the separate comparison
decision; it does not supply the later Figure 13 window or advance E2.

## Scheduler handoff and evidence boundaries

Immediately dispose candidate6 and E1 handoffs, Warden 12 and this memo in
the primary-owned queue. Record each recommendation as accepted, deferred or
rejected with its next evidence trigger. Use the available slots for candidate6
exact review, the next bounded Luna evidence task and an independent review/
implementation task whose interface is ready. Standing Astra roles need not
hold idle slots after a bounded handoff; rotate within three workers, with
Luna Max for implementation and Astra Max for independent review. No worker
recursively delegates or schedules compute.

Retain two responsive CPUs and at most 18 shared CPUs across actual jobs.
Native builds, helper tests and streaming exports have different measured
headroom needs; an occupied agent slot is not a CPU reservation. Refresh the
doctor before scheduling and retain per-task caps until evidence supports a
change. The GPU queue is correctly blocked by source-release dependencies;
there is no currently eligible H4-relevant GPU job being idled. Overlap the
first eligible source diagnostic with independent CPU work when its exact gate
eventually opens. Do not inflate utilization with unchanged smoke replays.

Measured slot geometry/spacing, synchronized valve/flow/pressure histories,
payload/flight/wind data, water/foam/aeration properties and calibrated footage
are required for later **built-device** claims, together with independent
deposition or calibrated plume evidence. E4/E5 raw cups and matched-release
metadata are later field-validation dependencies. They do not block any
engineering action above or authorized provisional preparation. No current
evidence validates the complete multiregion pipeline, ground performance,
foam, fire suppression or a fourfold gain.

## Exact artifact snapshot and inspection limits

| Artifact | SHA-256 recomputed during this inspection |
| --- | --- |
| Warden 12 | `6a1a4221a354e6bbc18c8ef69d56ec2e4a916ac83e97377c6b758935adef875f` |
| Companion contract v0.2 | `8965b0c1d58ba53252659d53ff7fcc0bd9fb41a2f82aeec4a65ea39d49281b32` |
| Parent schema v1.2 | `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492` |
| Candidate6 handoff | `fdc991e4dc729d3c758373e3e6b741b2313be1fa2a5918b6846cac2db7836a35` |
| Candidate6 patch | `3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee` |
| Candidate6 final native-build log | `993b9e29c80128b5fdbf5404b5f29d5215fa03d39a566a6007d3de7b9f2b02f3` |
| Candidate6 final helper-test log | `3c2df0ec46725694ecb81960455408c867171fdf768f2708a0a91386b6f57690` |
| Candidate5 successor exact review | `9615e07d93e9c3d4e0bcd1b4a2373650419a56ba7f220ca3a90f96b2074c108c` |
| Current narrow F1 analyzer | `9be9de9d6cf5f1a63196cd706ad657a48ea4344b7d720a07280ae1dfb46f8e37` |
| E1 decision packet | `c1d57536656b4253d6a43813fe957b8fcf7017a8b3d6b80cbe8c5d1379212939` |
| Local launcher | `13e3d2fd6fcebe58ad623af339de36ed4d29f842b7588c18c59e750ae16d73db` |

Checks were read-only `rg`, file reads/diff, SHA-256/manifest verification and
artifact inventory. The candidate5 smoke hash list itself matched
`4e1852edfb1f772665c23c45040c5ab83225184017b821a4f694feb34620d142`;
the full smoke rehash is attributed to Warden 12, not repeated here. Archived
test/build outcomes are cited as existing evidence; no new execution result
is claimed. The worktree remains broadly dirty/untracked. This artifact-specific
plan is not an exact scientific approval or a repository-cleanliness claim.
