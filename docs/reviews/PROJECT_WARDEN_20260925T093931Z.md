# Project Warden checkpoint 4 — 2026-09-25 09:39:31 UTC

**Read-only audit.** No files were edited and no builds, tests, or simulations
were launched. No scientific gate was approved.

## Overall assessment

Execution is currently limited by software and review readiness, not compute
availability. At 09:36 UTC, a read-only resource check found 20 effective CPUs,
load averages `0.04/0.13/0.24`, 118.52 GiB available RAM, and 260.89 GiB free
disk. The RTX 5090 was at 0% utilization with 16 MiB used and no compute
process; Docker had no running containers. These are availability snapshots,
not reservations or performance measurements.

The three worker slots were productively occupied by the Luna candidate4
runner implementer, Astra E1 reviewer, and this Warden. The E2 reviewer had
completed. Agent concurrency and local CPU allocations are separate.

## Confirmed state and critical path

- Candidate4's frozen build and source patch have an exact independent review.
  The image is eligible for one bounded **source-disabled** GPU regression only
  after runner repair and independent offline checks. There is no candidate4
  GPU runtime evidence.
- Candidate3's completed smoke and accepted P1 evidence remain unchanged;
  repeating either would not address a current blocker.
- E1 remains closed. Provisional case, mesh, sampler, and static preparation
  may proceed, but the reviewer found additional pinned-v2512 mismatches:
  turbulence density selection versus `rhoPhi` schemes; contact-angle
  `limit` and parameterization; missing GAMG smoother; and alpha clipping that
  could make solver-written boundedness checks tautological.
- The focused E2 Astra review accepts hash `bab679601f447193c7d103038c5703c94f36d208961c503d28c87c4af95b5c4b`
  as a method specification. Generator acceptance, coverage/scenario
  admissibility, target uncertainty, scoring, and scientific release remain
  open. E2 execution still requires accepted E1.
- The periodic FluTAS source box is a synthetic source implementation test. It
  does not supply E1's aircraft wall and external boundaries. Keep CPU E1
  preparation independent of GPU source qualification.

## Prioritized assignments

| Priority / owner | Action | Dependency and acceptance evidence |
| --- | --- | --- |
| 1 — Luna runner implementer; primary integration/check | Finish both regression wrappers and offline fake-command tests; freeze hashes. | Verify patch provenance from immutable image; explicit entrypoint and embedded runner hash; no source input in copied case; all stage results; `*** Fim ***`, finite final time at least 3 s, fatal/abort rejection even with exit zero; valid finite device and container CPU/memory rows. Preserve failures and manifests. |
| 2 — Primary scheduler | When runner checks pass, run one candidate4 source-disabled GPU regression via `run_local.py --gpu` within reviewed two-CPU/600-second envelope. | Exact image/wrapper hashes, sequential OpenACC, CUDA-buffer MPI and rising-bubble checks, stop at first failure, immutable logs and sampled resource maxima. This clears only the regression checkpoint. |
| 3 — Primary interface owner, Luna analyzer implementer, Astra reviewer | Freeze candidate4's source schema/contract, implement fail-closed analyzer in a disjoint file scope, then obtain independent review. | Interval/state joins, dry-source handling, all-face signs, rate failures, phase validity, separate divergence norms, uniform-grid restriction, justified numerical/resource limits, and positive/negative histories for missing, reordered, duplicated, truncated and nonfinite records. No source execution before review. |
| 4 — Luna E1 preparer; Astra reviewer | Convert the E1 correction packet into explicit v2512 choices and an executable synthetic sampler/static-check packet. | Resolve density/scheme, contact-angle, GAMG and preclip-alpha findings; freeze paired hashes; provide curved-primary geometry, field/patch consistency, pressure reconstruction, and synthetic contour/sign/zero-reference/score tests. Static preparation precedes separately reviewed characterization and controlled E1. |
| 5 — Luna E2 implementer; Astra follow-up reviewer | Implement and archive deterministic history generator and manifest checks from the accepted method. | Exact arithmetic/reference evaluator, query rounding, support/integral checks, history/case/execution identities, mutation tests and reproducible outputs. Does not approve scenario admissibility or scientific coverage. |

The next stable three-worker arrangement should retain two bounded
implementation/preparation tracks and one independent Astra reviewer. Prioritize
source-analyzer and executable E1 preparation; E2 generator work is useful but
should not leave E1 preparation without an owner. Reassign at every handoff
without exceeding the configured concurrency.

Two GPU-job CPUs plus separately budgeted one-thread preparation/check jobs
fit under the shared 18-core ceiling. An E1 template asking for all 18 CPUs
would consume the whole budget; reduce that allocation or schedule local jobs
separately. `run_local.py` caps threads per job but does not reserve aggregate
CPU capacity or VRAM against unrelated processes.

## Contract and documentation corrections

1. B2 had an incorrect general row count. Expected successful output is 14
   source-flux rows for one slot, 56 for four, zero for dry; 14 interval rows
   each for off-mask and rate checks; and 15 state-indexed boundary, mass, and
   velocity rows. This correction has been applied to the blocker plan.
2. Archive the distinct E2 follow-up ACCEPT; retain review 3's earlier REVISE
   record intact.
3. Update `docs/COMPUTE.md` and the source-gate record: candidate4 build/exact
   review are complete, bounded regression awaits runner repair, source
   execution remains closed.
4. Keep the corrected live worker/status state; the E2 reviewer has completed.
5. Most project files are untracked. The tracked plan diff does not represent
   the full review scope. Use full file inventories and hash manifests; no
   commit is required.

After analyzer and protocol acceptance, source cases run only in order:
quiescent dry → dry crossflow/gravity → one-slot → four-slot → source crossflow,
stopping at first failure. A 1–3 million-cell pilot has a separate review and
profile. Neither utilization pressure nor a source-disabled smoke releases
those stages.

## Exact identities recorded at audit

Repository HEAD was `5bee7e762775e2ada7b129cb83faf0a3f96feacd`, with a dirty
worktree containing substantial untracked project content. Candidate4 image:
`sha256:3086f0312b3a74dd7d0f03102d4b8584a8dd1fe4091364615cb0e580f00283bb`;
authoritative build:
`containers/flutas/candidate4/evidence/runs/20260925T091602Z-1994261/`.

| Artifact | SHA-256 |
| --- | --- |
| Candidate4 source patch | `2eddbe5cc406ecbc60e7ca1fe9ba3a5ff61b130283e74772b1593f1d385959ff` |
| Candidate4 independent review | `eb23bce970500f2adf8728ff0bbd9c8d800e84d57c4adf0737e527ce61fbc910` |
| E1 gate draft | `fdf41a7a2a6f29cca40b05eb2cd93c14cb5391f65d890be61aec8033a9989889` |
| E1 capability audit | `b78a4f104699196f9bf58a67139df395b0cef14f8eef5ff6b9f0a2cec20b1a4c` |
| E2 method specification | `bab679601f447193c7d103038c5703c94f36d208961c503d28c87c4af95b5c4b` |
| Source-boundary gate draft | `41f6c5fb7cc1d1687686d68a9ea606052a6f9fb91e590b6bfa2934d84406b969` |
| `scripts/run_local.py` | `13e3d2fd6fcebe58ad623af339de36ed4d29f842b7588c18c59e750ae16d73db` |
| AGENTS / WORKFLOW | `c1f195f99042ffc83a34d0200caaffe34014bc7bb2ea60e94a2c12bce069cd28` / `97f8dfafdd9357461eaef367da0a603236c1b2ffdb38ebfb442fba9adbfd5e9a` |

Runner files were actively changing and are not a frozen Warden review target.
No new user data are needed for current assignments. Built-system geometry,
material/discharge, flight, and independent deposition evidence remain later
dependencies for claims about the built system.
