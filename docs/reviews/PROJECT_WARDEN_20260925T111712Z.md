# Project Warden checkpoint 8 — 2026-09-25 11:17:12 UTC

**Disposition:** accept the current Luna Max implementation / Astra Max Warden
role contract and one-device GPU queue rules; refresh the operating ledger and
continue candidate5 schema resolution before producer/analyzer integration.
This is a read-only, advisory project review. It approves no code, solver run,
or scientific gate.

## Contract check

The existing project contract already requires productive use of the available
worker pool within the three-worker runtime cap and the measured shared CPU
budget. `.codex/agents/project_warden.toml` selects `gpt-6-astra`, maximum
reasoning, and read-only behavior. `AGENTS.md` and `docs/WORKFLOW.md` define
Warden checks at milestones, gate transitions, architecture changes, repeated
blockers, two completed checkpoints, and high-severity decisions. They also
require one serialized RTX 5090 queue, the smallest eligible GPU runtime trial,
and overlap with independent CPU work. Additional concurrency or more frequent
unchanged Warden audits are not needed.

The operating gap was stale status: the queue record still listed the B2
analyzer author and E1 review as active, and the E1 exact review as pending.
The E1 Astra review had already returned **REVISE**. The B2 Luna analyzer
handoff had completed with 23 synthetic offline tests and Ruff passing, but
primary acceptance and exact review were outstanding; its v1.1-targeted parser
is parked for schema v1.2 integration. That Luna worker has rotated to E1
static-package corrections. Candidate5 producer work remains active and is
holding production serialization for the shared-interface addendum.

## Critical path and steering

1. **Primary — freeze the candidate5 schema addendum.** Identify the actual
   property array at every phase stage, exact independent face/class/index
   scan sets and expected values, schedule state for phase versus velocity,
   failure-prefix membership, canonical output ordering, comparison/reduction
   rules, and timestep source pins. Acceptance evidence: exact schema hash and
   finding-by-finding disposition. CPU only; do not release source CFD.
2. **Luna candidate5 producer — continue source inspection and independent
   implementation in its disjoint files.** Keep CSV/manifest serialization
   assumptions parked until the reviewed interface is frozen. Report immutable
   candidate4 provenance, candidate5 source hashes, host behavior and scan
   counts. Ceiling: at most two CPUs and 6 GiB; no GPU or source solver.
3. **Luna E1 reviser — correct only the static package** against the archived
   exact Astra review. Update generator and generated case together, negative
   fixtures, pinned dictionary evidence and clean-output contract; provide a
   defensible Figure 3 trace or a proposed gate amendment for primary
   disposition. Ceiling: one CPU, no GPU, no mesh/solver execution.
4. **Astra Max reviewer — after v1.2 is frozen, review that exact interface
   independently.** Reuse the worker slot only for a bounded ready review or
   other independent task; do not keep it assigned to a completed Warden memo.
5. **Next Luna / primary integrator — after schema acceptance, adapt the parked
   B2 analyzer to production scan counts and failed-prefix rules, then request
   separate exact review.** Keep the analyzer scientifically
   `not_adjudicated` until limits are independently approved.

There is no currently eligible GPU trial. The next candidate5 source-disabled
GPU regression requires the completed native build, exact candidate review,
and a fresh resource check. It cannot use source inputs. Source cases additionally
require the complete B1-pre/B2 execution gate and must remain sequential.
Record CPU work and resource measurements separately; a free GPU does not
remove the schema/review dependency.

## Primary dispositions

- **Accept:** current Astra Max Warden role, model, cadence and advisory scope;
  existing Luna Max implementation role and measured concurrency/compute caps;
  one ordered GPU queue with independent CPU overlap.
- **Accept:** update the queue ledger and clarify that builds/code-object checks
  are CPU prerequisites while GPU runtime trials begin only after exact review.
- **Defer:** source CFD, E1 characterization, large GPU pilots, and B2
  production-bundle acceptance.
- **Reject:** candidate4 approval inheritance, repeated unchanged GPU smoke,
  or utilization-driven runs that bypass review.

The next Warden trigger is two primary-disposed deliverable checkpoints after
this memo, or earlier after a material architecture change or repeated
high-severity blocker. Coalesce simultaneous triggers against the same evidence
snapshot.

## Exact B2 implementation handoff (not accepted)

- `src/aerial_drop/flutas_source_analyzer.py` — SHA-256
  `42479b283fd738ac3a3de35c7fe977d4a9978d18ca9ea69b279bc3038046e443`
- `tests/test_flutas_source_analyzer.py` — SHA-256
  `7c6a1aaf75c8b6bb258279745d639a83e90e73b2dea1e229605551198921d4d4`
- `experiments/FLUTAS_SOURCE_ANALYZER_IMPLEMENTATION.md` — SHA-256
  `18dbaee2a3f9196fbb1dee7e9def7e454e10c7bd1e534493aadff87675904782`
- Reported checks: 23 focused offline tests, Ruff lint and format passed. These
  fixtures use schema v1.1 and synthetic count plans; they are not B2 acceptance.
