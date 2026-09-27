# Project Warden checkpoint 6 — 2026-09-25 10:29 UTC

**Reviewer:** Astra Max, read-only project Warden.  
**Disposition:** Steering memo only. No files were edited by the Warden, no tests/builds/solvers were run, and no scientific or execution gate was approved.

## Confirmed state and stale claims

- E0 is the only completed E0–E6 gate. P1 Rev 2 is an accepted implementation diagnostic; candidate4 B0 is a source-disabled GPU regression. The raw B0 records confirm exit 0, absent `source-boundary.in`, final time `3.001520526915884 s`, upstream `True True`, and 13 GPU/11 container samples. No source-on or scale claim follows.
- E1 review 4 accepts static preparation only. The current gate/audit hashes still match `15a9b4a48df3f8b059b98961d92cd89bdc8b69ffe1f66beaa81f936167ffe3ea` and `a6c655abbf58eff6bb71850fbed8612ece459c891ad9e21b4f5d3ddf7e7fcb32`. The E1 preparation worker is active, and `cases/e1_rouaix_case1_static` contains work in progress; no completed case or run is asserted.
- E2 author work and primary integration are complete, with 11 passing tests recorded; exact independent implementation review remains outstanding. Current source/test/note hashes are `23aa2ead5647c11ae97e6a86980b59b29e85f9caaefea2052562c02263be8de5` / `6ca763f72b31d64333c5f99e4eb98ee969338c5b25ee7443c911e7b0728ccd65` / `fb122e1d72c78529112b3ee7a8447d9f4e4d3dc81ed518167d1efc7defbd5816`. The accepted method hash remains `bab679601f447193c7d103038c5703c94f36d208961c503d28c87c4af95b5c4b`.
- Candidate4 source-readiness audit is archived at hash `2dd15861bd5f1a066546c62026f3bad006ef347f12e57bcd8f972ce6ba6da2be`, and the B1–B3 planner memo is complete. The old status and blocker records still described completed E2/audit/review work as active; refresh them and qualify any statement that no case is being prepared.

## Critical path and concrete steering

1. The path to the next numerical benchmark is E1 static package → separate reviewed bounded characterization → measured numerical/resource qualification → controlled E1 comparison. GPU source qualification is a separate enabling track; the periodic paired-return box cannot establish E1 aircraft-wall or external-flow boundary conditions. Keep E1 moving independently.
2. Candidate4 cannot currently clear B1-pre. The audit identifies missing full-stage alpha/rho/mu ghost evidence and incomplete requested/applied boundary-vector observability. Its fixed-step path also bypasses the complete AB2 timestep restriction. Primary should dispose the audit and freeze a compact stage/schema interface, then implement a narrowly scoped candidate5 while preserving candidate4.
3. Candidate5 should add full relevant ghost/vector scans with stage/interval/state identifiers, nonfinite counts, mismatch counts/maxima and failing-location evidence, plus the full timestep terms and an explicit prospective fixed-step margin. The independent scientific reviewer decides whether those summaries are sufficient and reviews the margin, dt/schedule, maximum/L1-divergence limits, and direct-pressure-solver applicability. The nominal `0.219235179` `dt/dtmax` estimate is a reason to resolve the 0.2-factor claim, not evidence of instability or an approved substitute threshold.
4. After schema freeze, implement the deterministic B2 analyzer and launcher in disjoint scopes; exact candidate/schema/limits/analyzer/launcher/input review precedes release. B1-pre permits an attempt; measured B1-runtime is its outcome. Then run `dry_four` → `dry_crossflow` → `quiescent_one` → `quiescent_four` → `crossflow_four`, one immutable attempt and independent assessment at a time, stopping on first failure. A separate pilot contract follows qualification.
5. Close the ready E2 implementation review. Reuse this Astra thread under a separate review assignment; the Warden memo does not satisfy that review. Keep real startup/boundary identities, matrix coverage, target-coordinate uncertainty, scoring and E2 scientific release open.

## Worker and compute recommendation

Immediate wave: existing Luna E1 static preparer (up to 2 CPU/4 GiB, no mesh/CFD); reuse the completed Luna implementation thread for candidate5 after primary interface freeze (initially up to 2 CPU/4 GiB, no self-scheduled build/GPU); reuse this Astra thread for the exact E2 code review (one CPU/2 GiB, read-only). When E2 review finishes, primary can use that slot for candidate5 design/exact review or a bounded B2 implementation assignment as dependencies permit. After the E1 handoff, reassign its slot to analyzer or launcher work rather than leave a worker waiting on another interface. Do not allocate more than three worker slots in total.

The latest recorded doctor snapshot is 20 effective CPUs, roughly 118.5 GiB available RAM, 260.8 GiB free disk, and one 31.8 GiB GPU; it is historical availability, not a reservation. Primary reruns doctor and inspects active jobs before scheduling builds or simulations. Shared local jobs stay at or below 18 cores with two reserved for responsiveness. CPU preparation/review is ready. No source CFD or new meaningful GPU trial is currently eligible. Candidate4's unchanged B0 and P1 should not be rerun. A changed candidate5 gets CPU host/build/code-object checks, exact review, then its smallest source-disabled GPU regression through the shared lock; source runs still await B1-pre/B2. Spare CPU/GPU capacity is justified while those gates are closed.

No new user input is required for these local tasks. Measured device geometry, discharge/material/flight data, calibrated plume/deposition evidence, paper-author details for exact replay, and cluster access are future external dependencies; their absence does not block authorized provisional preparation.

## Contract assessment and exact additions

The existing cadence, Astra model/effort, read-only authority, separate scientific review, queue balancing, prompt minimal GPU checks, and first-failure rule are sufficiently concrete. Add this operational rule to `AGENTS.md` and mirror it in `docs/WORKFLOW.md`:

> Count a completed checkpoint when a bounded deliverable, its prescribed checks, exact evidence references and the primary's handoff disposition are recorded. Status edits, repeated discussion and unchanged reruns are not checkpoints. Record the last Warden memo, completed checkpoints since it and the next trigger in `docs/STATUS.md`. Coalesce simultaneous triggers into one memo for the same evidence snapshot.
>
> Each Warden recommendation names the blocker, responsible owner, prerequisite, next action, acceptance or stop evidence, and CPU/GPU eligibility. For a repeated blocker, identify the attempted resolution and the evidence that remains missing, then recommend a bounded discriminating check, implementation change or supported fallback. The primary records each recommendation as accepted, deferred or rejected, with a reason and next evidence trigger, in the existing status/blocker records. Warden advice never substitutes for exact independent review or the primary's launch decision.

Append this to the `project_warden` role instructions:

> Read `docs/BLOCKER_RESOLUTION_PLAN.md` and the previous Warden memo's dispositions. Anchor current-state claims to exact artifacts or timestamps; identify stale active-worker, review and run claims explicitly. Separate implementation eligibility, measured runtime qualification and scientific validation. For each ready assignment include owner/file scope, dependencies, resource ceiling and acceptance evidence; for each idle queue name the exact blocker. State the next Warden trigger and avoid repeating an unchanged audit without new evidence or a required cadence trigger.

## Next trigger

Run the next Warden check at the candidate5/source-observability architecture decision, after two completed deliverable checkpoints if that comes first, or immediately for a high-severity cross-discipline finding that redirects E1 or the GPU route. Primary archives this memo and integrates confirmed decisions only.
