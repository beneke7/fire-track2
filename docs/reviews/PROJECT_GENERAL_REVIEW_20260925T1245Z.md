# Independent contract and handoff review — 2026-09-25 12:45 UTC assignment

**Astra Max advisory disposition: revise the remaining ledger inconsistencies.**
The delegation/GPU/Warden contract is coherent. One source-order conflict was
corrected by the primary during review. This memo approves no implementation,
scientific gate, mesh, characterization, or launch. Only this memo was written;
no tests, builds, containers, solvers, or GPU jobs were launched by this reviewer.

The review followed `.codex/agents/general_reviewer.toml` and read the project
plan, validation contract, requested five documents, both advisory memos,
Warden checkpoint 9, role configuration, and relevant source-gate/launcher
declarations. Shared documents changed during inspection: the opening STATUS
read had a 12:42 header; the exact finding snapshot below has a 12:48 header
and was rehashed at **12:55:24 UTC**. I do not claim an unchanged opening/closing
STATUS hash. Closing workflow inspection at **12:56:12 UTC** confirmed the
primary's correction. Line references below use the hashed finding snapshot
unless explicitly marked closing.

1. **M1 — Source-run order conflict; resolved by closing inspection.**
   Finding-snapshot `docs/WORKFLOW.md:128–133` required dry crossflow before
   one-slot and source-enabled crossflow afterward. That contradicted
   `experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md:127–144` and
   `docs/BLOCKER_RESOLUTION_PLAN.md:110`, which retain both frozen crossflow
   cases as negative fixtures. The smallest correction was to state the
   current positive sequence `dry_four → one-slot → four-slot` and require a
   separate reviewed amendment for positive crossflow. The primary made this
   exact correction at closing `docs/WORKFLOW.md:128–136`. No source execution
   was authorized by resolving the documentation conflict.

2. **M2 — Candidate5 schema-conformance wording overstates readiness.**
   `docs/STATUS.md:25–26` contains the broken sentence “Luna is candidate5
   serialization/build metadata aligns with the accepted schema,” while
   `:512–514` and `docs/BLOCKER_RESOLUTION_PLAN.md:107` record nonconforming
   timestep formatting, phase-row order, and missing production provenance.
   The deblock memo explicitly separates these at `:102–154`. Replace the
   alignment claim with completed implementation/build evidence plus the exact
   review disposition. The newly returned candidate5 review marks only one
   local-image-pinned source-disabled regression **ELIGIBLE**; producer/B2/
   source acceptance remains **REVISE / CLOSED**. Carry both dispositions
   together; its smoke eligibility is the specialist's finding, not this memo's.

3. **M3 — Warden accounting and primary disposition are not yet auditable.**
   `docs/STATUS.md:478` attributes acceptance to checkpoint 9, although that
   memo's `:3–5,55–62` provides advisory recommendations only.
   `docs/BLOCKER_RESOLUTION_PLAN.md:359–360` says the primary disposition is
   archived in that same memo, but it contains no primary addendum. Record
   dated primary accept/defer/reject dispositions with reason and next evidence,
   as required by `AGENTS.md:66–73`, and link their actual location.
   `docs/STATUS.md:499–503` retains count **1** and omits the repeated-blocker
   trigger. The completed deblock memo now has an exact hash, prescribed
   read-only checks, and explicit primary acceptance at blocker-plan `:42–53`;
   list counted deliverables under `AGENTS.md:60–65`, or state why this handoff
   is excluded rather than silently retaining the old total. Include all
   independent triggers from `AGENTS.md:47–50`. A new Warden worker is already
   active at closing, so archive/dispose that review and reconcile the counter;
   do not start a duplicate Warden audit for the same snapshot.

4. **L1 — Refresh live ownership, resource, and dependency records together.**
   `docs/STATUS.md:437,460,498–499` still lists the completed deblocker as
   active, whereas blocker-plan `:355–357` had already replaced it with this
   reviewer. `docs/BLOCKER_RESOLUTION_PLAN.md:384–386` still calls producer/
   analyzer allocations and the finished two-core build current. Finally,
   `docs/STATUS.md:536–537` awaits final provenance-test evidence despite
   `:442–444` recording the full unskipped rerun. Replace these with the new
   timestamped worker/job ledger and exact remaining review/production-receipt
   dependencies. Distinguish the completed test from the unresolved OCI/build
   receipt; do not repeat tests or builds merely to reconcile the wording.

The substantive deblock advice is otherwise integrated correctly at
`docs/BLOCKER_RESOLUTION_PLAN.md:40–59,107–112`: the primary owns staged-input
binding and the companion six-output conservation/limits/launch contract;
the three-file B2 implementation is not production acceptance; one E1 correction
owner and a separate primary disposition-memo owner avoid duplicate writes;
the wall amendment remains an assumption for static preparation, with mesh,
boundary choices, characterization and E1 execution still separately gated.
No missing user measurement is incorrectly made a present engineering blocker.

Model/slot rules match the supplied runtime: `.codex/config.toml:5–9` and
`AGENTS.md:16–29` allow three workers plus the primary, with Luna Max for
implementation/research and Astra Max for the three named advisory roles.
Live listings showed four agents total at both observations. Opening roles
were candidate5 exact review, this review, and the reused E1 worker; closing
names were this review, `astra_max_warden_current`, and `candidate5_gpu_smoke`.
Agent names do not verify effective models or running compute processes.
No overlapping write ownership was established in the inspected task tables.

The GPU-checkpoint rule is explicit at `AGENTS.md:90–120` and
`docs/WORKFLOW.md:99–108,119–145`: exact review and prerequisites first, smallest
meaningful trial promptly, one locked GPU job, separate CPU work, and no
utilization-based gate release. `scripts/run_local.py:40–59` implements a shared
per-user flock. Candidate3/4 trials are already archived; unchanged repeats and
P1 replay are unnecessary. E1/B2 preparation is CPU-only. The new candidate5
smoke assignment follows its returned limited-scope review; this memo neither
verifies that run nor infers source behavior. E0 remains the only completed
E0–E6 scientific stage in the inspected records.

Exact SHA-256 evidence follows. Source/test results are attributed to existing
handoffs and reviews; this reviewer used file/line/hash reads and live-agent
listings only. Later primary ledger edits are outside this frozen memo.

| Artifact / observation | SHA-256 |
| --- | --- |
| `AGENTS.md` | `5bfa08b723d5138d660514968f1b1c6c204c8b0f4e6d7469b80bb7285fb26575` |
| `docs/WORKFLOW.md`, finding snapshot | `b3fde0dcc739d87eb4eb1e0174d4404871038ff7e80929bf6fb2bbd875a975bf` |
| `docs/WORKFLOW.md`, corrected closing snapshot | `52cbe3df4d02b1e922bfcd4eb73e818c02da28cd73ecb2f946b4ded794acba90` |
| `docs/STATUS.md`, 12:48 header | `9002575d32b8205f277679f1c06fe96c199cd506e4a798807948dd1ac0f883ec` |
| `docs/BLOCKER_RESOLUTION_PLAN.md`, finding snapshot | `a02cb6acd4569b48746b2779fd71d0049f1dd32a72a66f67e525a9287d9452f4` |
| `DEBLOCKER_PLAN_20260925T1229Z.md` | `48a8aeb1f9e828577d24ee6f152490f7481ce18367751e15c6ec2055928438c8` |
| `E1_STATIC_PACKAGE_FOLLOWUP_20260925T123638Z.md` | `9451052a90ca338501ead2b92658d4b53f83e33fbc35300cb4cdb0f591cef847` |
| `PROJECT_WARDEN_20260925T121128Z.md` | `a75930818669f3f00af2a3bd2bd9ea99deb33712204ed273c746951bce982101` |
| Candidate5 exact review, closing scope table inspected | `b5cf3036bf7a79a2ad4b149889faf10e3d407e169191b80c311c61e9e19cfd68` |
