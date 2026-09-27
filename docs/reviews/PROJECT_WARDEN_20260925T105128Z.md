# Project Warden checkpoint 7 — 2026-09-25 10:51:28 UTC

Authority: independent Astra Max steering audit, read-only and advisory. This
memo approves no candidate, scientific gate, characterization or execution. The
separately assigned E1 exact-package review is still in progress and has its
own disposition.

Trigger and evidence: the primary froze the candidate5 producer
architecture/schema while producer and B2 analyzer workers became active.
Inspected interface:
`experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md`, SHA-256
`d0bc6d997d92a59df677fb1d79e280c5f37c56da848bc846d0af087bb9ba8169`. The
previous Warden memo is
[`PROJECT_WARDEN_20260925T102908Z.md`](PROJECT_WARDEN_20260925T102908Z.md),
SHA-256 `184a7a3c3114e9a4f81625416882400dfe82ab50c938a91c5cbc4abfa9c62724`.
Current STATUS, blocker plan, workflow, compute record, review-4 inputs,
candidate5 work-in-progress documents and E1 package were inspected.

## Confirmed state and stale claims

- E0 remains the only completed E0–E6 gate. Candidate4 B0 is a completed
  source-disabled regression; B1-pre/B2/source CFD remain closed. Candidate5 is
  under implementation, not reviewed or built evidence.
- E2's exact post-fix implementation was independently accepted at 10:38:49
  UTC. Its protocol and scientific release remain open.
- E1 author preparation is complete and under a separate independent
  exact-package review. STATUS's opening, active-worker paragraph and next-work
  item still call it active preparation; the blocker-plan worker table also
  needs to replace E1 authoring with Warden/E1 review.
- The live worker roster contains candidate5 producer, B2 analyzer and this
  Astra Warden/reviewer; old thread names do not describe current assignments.
- STATUS still says Warden 7 is queued and E2 findings await focused follow-up.
  The “zero completed checkpoints since checkpoint 6” statement should be
  reconciled with the accepted E2 implementation handoff; only count a
  deliverable once its prescribed checks and primary disposition are
  recorded. E1 author completion alone is not scientific acceptance.
- Candidate5's working `INDEPENDENT_REVIEW.md` and `SOURCE_BOUNDARY.md` still
  contain copied candidate4 identities and claims. Treat them as inherited
  placeholders; before candidate5 handoff, the owner must remove ambiguity and
  ensure no candidate4 acceptance is presented as candidate5 approval.
  Preserve candidate4's originals.
- STATUS's latest-doctor label is 09:59 UTC, whereas the blocker plan records
  10:30 UTC. Synchronize the timestamp and evidence reference; neither snapshot
  reserves resources.

## Critical path and bounded steering

1. Continue the two independent CPU tracks: candidate5's producer and B2's
   structural analyzer. Candidate5 must emit full relevant scan summaries,
   deterministic failure evidence and the complete timestep restriction; the
   analyzer must independently enforce schema/completeness and recompute
   quantities. Without accepted numerical limits its decision remains
   `not_adjudicated`.
2. Primary resolves schema details before producer/analyzer integration. The
   current join paragraph says all three tables have an interval key, but the
   timestep header lacks it. A state-only timestep key is appropriate:
   enumerate U_0..U_N, bind time=t0+k*dt and join explicitly on
   `state_index`. State whether the final unconsumed endpoint's guard is itself
   an acceptance requirement. Define phase `state_index` as the source-boundary
   schedule state so `pre_momentum`'s endpoint liquid field is not confused
   with the still-applied interval-k boundary state.
3. Freeze expected keys/counts and failure sentinels. Derive complete stage /
   face / class / property or component membership independently from case
   geometry and the pinned call-stage map. Include declared empty-class rows
   with zero scanned cells rather than silently omitting them. For the
   restricted paired-return fixtures, phase x/y faces are periodic; zhigh
   partitions into `active_slot`/`inactive_slot`/`top_offmask`; zlow is
   `bottom_return`. Velocity membership covers the three zhigh classes and
   zlow return for u/v/w, including explicit staggered/halo ranges. Other
   labels require a prospective extension. Freeze zero-failure rows as zero
   counts/max error and `not_applicable` first-failure indices/value fields.
   Preserve nonfinite failure values through explicitly allowed categorical
   tokens or a kind field; reconcile that rule with the current blanket “finite
   decimal” rule. The analyzer must reject a failed scan while retaining
   complete failure evidence.
4. The provisional 0.2 timestep guard is expected to reject current crossflow
   inputs. Preserve that CPU guard test. Primary and independent reviewer must
   settle the margin or prospectively version dt/schedule before a source
   execution packet is eligible; do not discover this known policy mismatch
   through an expensive source run.
5. E1 remains an independent route to the next numerical benchmark:
   static-package review/fixes → separately reviewed bounded characterization
   → numerical/resource qualification → controlled E1. The synthetic GPU
   periodic box does not supply E1 aircraft-wall/external-flow qualification.
   Continue that route while GPU infrastructure matures.

## Queues and owners

Current wave: Luna candidate5 producer owns `containers/flutas/candidate5/**`,
at most 2 CPU / 6 GiB; Luna B2 analyzer owns its module/test/note scope, at most
1 CPU / 2 GiB; Astra owns no files and performs the Warden/E1 reviews at one
CPU / 2 GiB. Primary owns shared schema, numerical decisions, integration and
scheduling. Reassign a completed slot to the launcher or required E1
corrections once its prerequisite interface/review is available; do not leave
workers waiting on an unresolved shared interface.

The recorded host is 20 effective CPUs, about 118.4 GiB available RAM, 260.8
GiB disk and one 31.8 GiB RTX 5090. Primary refreshes doctor and active-job
evidence before build/compute allocation. Keep aggregate jobs <=18 cores,
reserve two host cores and serialize GPU work through `run_local.py`'s lock.
Small preparation tasks do not justify filling unused cores with gated
solvers.

GPU queue: no job is eligible now. A stable candidate5 may receive CPU
host/build/code-object checks, exact independent review and then its smallest
source-disabled regression. Source diagnostics additionally require B1-pre/B2,
numerical limits and launcher review. Do not repeat unchanged candidate4 or P1
runs. Later source stages remain ordered and stop at the first failure.

## Primary disposition record

Accepted prior steering: preserve candidate4; keep E1 independent; implement
candidate5 only after shared interface freeze; resolve and independently
review E2 code findings. These are now evidenced, with E2 code review complete.

Recommend **ACCEPT**: finish the two current implementation scopes; clarify
schema keys/membership/sentinels before integration; replace stale
worker/review labels; keep the E1 exact review separate.

Recommend **DEFER**: source CFD, E1 characterization, and all larger GPU pilots
until their exact reviewed prerequisites exist.

Recommend **REJECT**: inheriting candidate4 approval in candidate5 or launching
unchanged/regression/known-ineligible cases merely to increase utilization.

No new user input is required for these tasks. Measured built-device data and
external source clarifications remain necessary for stronger later claims,
not for the authorized provisional preparation. Cluster access remains
unestablished.

Next Warden trigger: two completed, primary-disposed deliverable checkpoints
after this memo, or earlier if producer/analyzer integration changes the
frozen architecture, a blocker repeats, or a high-severity finding redirects
the E1/GPU critical path. Do not count status edits or repeated unchanged
reviews.
