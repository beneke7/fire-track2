# Project Warden checkpoint 10

**Astra Max advisory steering; observation window 2026-09-25 12:53–12:58 UTC.**
This memo approves no scientific gate or launch. I read the project plan,
AGENTS, workflow, compute/validation contracts, current status/blocker records,
Warden checkpoint 9, candidate5 exact review, E1 follow-up and corrected static
package. I inspected hashes and existing runtime evidence; I ran no tests,
build, mesh, solver or GPU job. This is a critical-path audit, separate from
the concurrent general contract review. The only file written is this memo.

## Confirmed state and immediate significance

Candidate5's exact review is complete and its one permitted source-disabled
GPU regression has **passed**. The attempt ran 12:55:22–12:55:48 UTC, exit 0,
in [`20260925T125522Z-2108516`](../../results/runs/flutas-candidate-gpu-regression-20260925T125522Z-2108516/).
Its preflight records absent `source-boundary.in`; its stage checks record
OpenACC, CUDA-buffer MPI, `sm_120.cubin`, normal upstream bubble completion at
`3.001520526915884 s`, and upstream `True True`. Thirteen GPU and eleven
container CPU/memory samples passed structural validation. I independently
checked every entry in the candidate evidence archive's `SHA256SUMS`, read
the exit/preflight/stage/resource records, and checked the manifest identity.
This closes this candidate's software runtime checkpoint, **not** B1-pre,
B1-runtime, B2, a source-enabled run, or E1.

The [exact candidate5 review](FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md)
already reviews the analyzer as well as the producer. Its H1–H4 and M1–M3 are
concrete CPU engineering work. Repeating a separate review of the unchanged B2
implementation would duplicate completed work; exact review of the corrected
implementation is still needed. The current producer and analyzer tests pass
while their serialized interface disagrees, so increasing the same test count
will not resolve the critical defect.

The E1 correction handoff is complete. The primary reports 23 focused tests,
Ruff/format, deterministic regeneration of 20 artifacts plus their manifest,
and 19 unchanged generated artifacts with only `domain.json` intentionally
changed. I independently hashed the six corrected files below and verified
all 20 manifest entries. The prep-note hash matches the primary's handoff.
These are corrected inputs awaiting exact scientific review; no mesh,
characterization or E1 solver result is established. D-NUT-BC, contact-angle,
instrumentation, mesh/initialization and separate characterization approval
remain real later dependencies.

E0 remains the only completed E0–E6 scientific gate: **1/7, about 14% by gate
count**, with no claim that this measures remaining effort. The GPU synthetic
periodic/paired-return box cannot supply E1's aircraft wall and external-flow
boundary conditions. Advancing the GPU source branch must not hold the
independent CPU E1 preparation branch indefinitely.

## Ranked steering and bounded next assignments

| Rank / blocker | Owner, prerequisites and concrete next action | Acceptance or stop evidence / compute eligibility |
| --- | --- | --- |
| **1 — Review/implementation boundary defects, B1-pre/B2.** Candidate5 H1–H3/M3 survive existing tests. | **Primary** first fixes the time/provenance interface choices; **Luna Max producer worker** owns only a new versioned successor candidate, its producer tests/build recipe/receipt tools. Preserve the reviewed candidate5 and all attempt bundles. Fix strict timestep serialization, schema phase ordering, declared diagnostic time, and reciprocal validation. | Test actual compiled helper output through the independent analyzer across all declared states, including pulse edges and state 2 where accumulated/index time differs. Use realistic 42-entry operands from pinned `initgrid`, exercise production arithmetic flags, and preserve finite/nonfinite failure behavior. Exact successor hashes, host behavior evidence and native build/code-object evidence precede independent review and its smallest source-disabled GPU check. Start within the established **2 CPU / 6 GiB** build ceiling; raise only from a measured profile. No source solver is eligible. |
| **2 — Independent analyzer malformed-evidence handling, M1/M2.** | **Luna Max analyzer worker** owns `src/aerial_drop/flutas_source_analyzer.py`, its focused tests and implementation note only. Parse each first-failure value independently; validate failure coordinates against its actual face/component mask; validate ranges before reciprocal arithmetic and turn overflow/domain errors into deterministic rejection reports. This can overlap producer work. | Independent fixtures must distinguish a legitimate nonfinite audit failure from malformed evidence, reject the invalid xlow location, and return structured failure for finite-intermediate overflow. Focused tests/lint and exact corrected hashes, then exact independent review. **1 CPU / 2 GiB**, CPU-only; GPU trial is not applicable. Do not claim broad production B2 acceptance from the three-file tests. |
| **3 — Shared input/provenance/conservation contract is still missing.** | **Primary** owns the interface documents and prospective decisions. Freeze the staged `source-boundary.in` grammar/hash binding so an independent reader derives schedule, geometry/masks and expected scan plan. Preserve actual captured timestep operands and bind/check their identity; do not replace actual vertical arrays with uniform reconstructed values. Add a companion matrix for all six inherited conservation/velocity artifacts, numerical limits, direct-pressure applicability, supervisor stops and launch behavior. | Source acceptance requires an independently reviewed complete quantity-to-artifact matrix, justified frozen limits, deterministic input/output identity checks, producer/analyzer join tests and a fake-executable launch/stop exercise. The three-file schema alone cannot prove mass/momentum/continuity closure. CPU preparation is ready; all source GPU stages remain blocked until this and exact candidate acceptance pass. No user data are required. |
| **4 — Repeated E1 static review and provenance chain.** | **Primary** records the corrected handoff in a new integration receipt; an **Astra Max exact E1 reviewer**, separate from implementation, reviews the six corrected identities and amended gate. Keep one next-wave slot for this bounded work so GPU support work cannot consume every slot. | Findings must be closed against the exact static package and embedded identities. Static acceptance permits only its explicitly reviewed scope; neither the assumed wall nor passing fixtures releases meshing, characterization or E1. The next characterization contract must separately resolve D-NUT-BC/contact angle, capture points, mesh/initialization checks and monitor/resource stops. Read-only review/light CPU; GPU not applicable. |
| **5 — Frozen crossflow fixtures are expected negatives.** | **Primary** preserves `dry_crossflow` and `crossflow_four` unchanged. Bring generic workflow/compute sequence text into agreement with the source gate. If positive crossflow becomes necessary, open a versioned prospective amendment with a concrete timestep/margin calculation and pulse/dose/horizon disposition. | The current positive quiescent sequence is `dry_four → one-slot → four-slot`, only after B1-pre/B2/limits/launch review. Known crossflow guard rejection is offline negative evidence, not a passed crossflow runtime case. Positive crossflow needs separate exact review; stop at the first real failed runtime stage. Never spend GPU time rediscovering the known U0 rejection. |

For rank 1, retaining v1.2 requires emitting its declared index-based
diagnostic time without relabelling the accumulated solver clock as that same
quantity. Preserve the actual clock separately under an explicit companion
contract, or prospectively amend and re-review the schema. The primary should
decide this before the implementation owner changes the interface. Do not
introduce a post-run tolerance to erase the mismatch.

For rank 3, choose one explicit identity route: a genuine local OCI manifest
and immutable receipt, or a prospectively reviewed contract that calls the
local Docker image ID exactly what it is. A registry upload is unnecessary.
Do not place a configuration/image ID into a field described as an OCI
manifest digest. This choice does not invalidate the already reviewed
local-image-only smoke.

The inherited outputs needing companion coverage are `source-flux.csv`,
`source-offmask.csv`, `rate-check.csv`, `boundary-ledger.csv`, `mass-ledger.csv`
and `velocity-audit.csv`. Independent arithmetic must cover their real phase,
volume, momentum, inventory and continuity semantics. B1-runtime evidence
must be measured after a reviewed attempt is eligible; requiring it before
that same attempt would create a circular gate.

## Avoid two repeated-work traps

**The E1 hash chain must be acyclic.** The corrected prep note pins the
12:07 primary wall-disposition memo at `181ee164…`, while that memo pins the
historical prep note `ac47a5fa…`. Updating the old memo in place to pin the new
prep note `4178ea32…` would invalidate the current note's parent identity;
updating the note back would start a reciprocal hash loop. Preserve the
timestamped old memo as historical evidence. Append a new primary integration
receipt that pins both the old decision and the six new artifacts, and let
the next independent review pin that receipt. The historical memo need not
be rewritten to accept a package it never accepted. This is an actionable
provenance correction, not a reason to restart E1 implementation.

**Use the producer/analyzer boundary as the next discriminating check.**
Earlier producer tests accepted padded numbers and repeated the producer's
incorrect row order; analyzer unit fixtures did not consume those bytes.
One compiled-output-to-independent-parser fixture spanning the schedule and
real operand variation resolves more uncertainty than another unchanged
review or GPU smoke. It remains a helper/integration check, not source CFD.
Frozen predecessors and retained failed attempts are justified evidence;
rerunning them unchanged would duplicate work.

## Queues, resources and non-blockers

At the 12:56:28 UTC read-only snapshot, `docker ps` was empty and the RTX 5090
reported **0% utilization, 16/32,607 MiB and 20.98 W**, after the smoke had
finished. This is a snapshot, not a utilization average or runtime peak.
`results/machine.json` reports 20 effective CPUs, the shared 18-CPU default,
about 118 GiB available RAM and about 261 GiB free disk. The primary must
refresh resource headroom before the next compute allocation.

At the live-agent inspection the three occupied slots were the general
contract reviewer, this Warden, and the bounded candidate5 smoke worker.
Those task names are not evidence of three running compute jobs. Capture the
finished smoke and review handoffs, then promptly rotate into the two Luna
correction assignments and Astra E1 exact follow-up above. The primary can
draft the shared companion contracts concurrently. Respect the actual
three-worker ceiling, shared CPU budget and one GPU lock. A Warden should not
hold a permanent idle worker slot.

The **GPU queue is now empty for a valid dependency reason**: candidate5's
eligible smoke is complete; a successor needs native build and exact review;
source execution needs B1-pre/B2/limits/launch approval. Candidate3/4 repeats
and a P1 replay add no current evidence. CPU capacity can advance the
corrections and shared interfaces immediately. The throughput target is
maximum useful approved work within measured headroom; full utilization
cannot be promised when the critical path is a review/interface dependency.

No user input blocks these engineering tasks. Measured Restás geometry and
synchronized discharge/pressure/valve traces remain needed for a built-device
claim; E4/E5 raw cups and matching release/flight metadata remain needed for
stronger field comparisons. These are later scientific limitations, not
grounds to halt authorized provisional water preparation. Host `nvcc`, a
second GPU, cluster access and a new source-free replay are not prerequisites
for the present corrections.

The 12:48 status/plan snapshot still described the candidate5 exact review and
E1 implementation as active and B2 as unreviewed. Those statements now need
the completed review, corrected handoff and passed smoke. The general
reviewer owns the comprehensive consistency audit. The sequencing conflict
affecting scientific planning is specifically `WORKFLOW.md` and `COMPUTE.md`
still listing the known-negative dry crossflow as a positive runtime stage;
the accepted primary crossflow disposition/source gate takes precedence.

## Cadence and primary dispositions

Recommended recurring contract text: **Invoke the Astra Max Warden after two
completed, primary-disposed deliverable checkpoints; immediately at a major
gate transition, source/solver architecture change, repeated blocker, or
high-severity decision that redirects the critical path. Coalesce simultaneous
triggers over one evidence snapshot. Archive advice and record each item as
accepted, deferred or rejected with owner and next evidence trigger.**
Existing AGENTS/workflow/role instructions already express this cadence and
are coherent about independence. The Warden is advisory; the assigned
scientific reviewer and primary retain gate/launch responsibility.

This memo covers the newly completed candidate5 exact review, E1 corrected
handoff and candidate5 software smoke. After the primary records their
dispositions and integrates this memo, reset the since-Warden counter to zero;
do not count the Warden's own administrative integration as a new deliverable
that recursively triggers another audit. The next expected trigger is **two
newly disposed correction/review deliverables**, or an earlier material
input/time/provenance architecture decision or source-run eligibility change.
Do not delay ready implementation while waiting for that checkpoint.

Recommended primary dispositions: accept ranks 1–5 and the append-only E1
receipt; acknowledge the passed smoke without rerunning it; defer source CFD,
E1 characterization and larger pilots until their named gates; reject
unchanged duplicate review/run work and utilization-driven gate bypass.

## Exact evidence anchors

| Artifact | SHA-256 observed |
| --- | --- |
| Candidate5 exact review | `b5cf3036bf7a79a2ad4b149889faf10e3d407e169191b80c311c61e9e19cfd68` |
| Candidate5 GPU attempt `SHA256SUMS` | `99fce2d33c9d47b8b5de14aec697870b2c61423eb37c543a79c6b61b1fbf50fc` |
| E1 prior exact follow-up | `9451052a90ca338501ead2b92658d4b53f83e33fbc35300cb4cdb0f591cef847` |
| `cases/e1_rouaix_case1_static/prepare_case.py` | `dd72cec1ace9d75bf109c06afefd056bc4b12fc92f33f3d51d1aa013f6ebf901` |
| `cases/e1_rouaix_case1_static/static_preparation.py` | `762583cbaa0b2622b527faa622a9922c053b008dffdbc8104dbac64a293e7507` |
| `cases/e1_rouaix_case1_static/geometry/domain.json` | `ac4d4ec27ba588e8337d018a781d27ac7d3d33f8dd19b7ec1b6171daeadb5c8c` |
| `cases/e1_rouaix_case1_static/CASE_SHA256SUMS` | `3cbc0528bc8b2d9feb35529e85d5bd1b247c92e4f7f28345f53db1ba462cfb8e` |
| `tests/test_e1_rouaix_case1_static.py` | `cc20a96961e94015fa04fe1e0e8cfb0b2330bcde7fab65ddde8ae5ee1bb1ffa1` |
| `experiments/E1_ROUAIX_CASE1_STATIC_PREPARATION.md` | `4178ea3201c6960c250831a93320e821a20427908701fd911a747582d02a6fe1` |

Hashes record this observed snapshot and do not accept the artifacts. If a
producer or shared contract changes afterward, its author must identify the
successor explicitly; this memo does not silently extend its findings to it.
