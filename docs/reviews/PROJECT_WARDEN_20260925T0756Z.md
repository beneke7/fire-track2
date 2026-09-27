# Project Warden checkpoint

**Recorded:** 2026-09-25 07:56 UTC. **Role:** project-scoped `project_warden`,
`gpt-6-astra` with max reasoning. **Scope:** read-only project state,
scientific sequencing, compute queues and blockers. The Warden did not edit,
run tests, build images, launch jobs, or approve scientific gates. This file is
the primary's durable record of its steering memo.

## Verified state

- **P1:** historical revision 2 remains accepted. The current six-file
  execution path has prospective exact-hash review; 59 focused tests, real
  contract validation, stale-hash rejection, input equivalence and CPU image
  identity checks passed. Optional replay is ready but adds no necessary
  evidence. See
  [`P1_EXECUTION_REFREEZE_VALIDATION.md`](../../results/P1_EXECUTION_REFREEZE_VALIDATION.md).
- **FluTAS:** candidate2 compiled to `sm_120` and passed ten static/analytic
  checks, but is blocked by the dry validator, bottom-return periodic halos,
  and stale source ghosts/reconstruction on shutoff. The exact patch copy and
  independent review are preserved. No candidate3 image exists yet and no
  source CFD has run.
- **E1:** the CPU capability audit says OpenFOAM v2512 can support an explicitly
  approximate comparison. HRIC versus isoAdvector, realizable-closure versus
  two-layer treatment, curved geometry, turbulence mapping, Figure 13
  semantics, and the printed `Re_j` discrepancy remain decisions. No E1 case
  or solver result exists.

## Warden steering

1. Complete candidate3's dry/active validator, periodic-stencil halo and
   shutoff/reconstruction behavior tests; add dry crossflow/gravity coverage.
2. Freeze candidate3 hashes and build metadata, then obtain exact-candidate
   Astra review. Keep compiler/code-object evidence separate from solver
   runtime evidence.
3. Add fixed-step global/interface Courant telemetry, finite-value checks,
   diagnostics flushed before failures, the fail-closed analyzer/runner, and
   independently reviewed limits and execution contract before source CFD.
4. Run quiescent dry → dry crossflow/gravity → one-slot → four-slot →
   source-enabled crossflow sequentially, stopping at the first failure.
   E1 case prep proceeds independently; E2 execution remains downstream of an
   accepted E1 gate.

A candidate GPU regression can be considered after exact-candidate review if
it is bounded, has an immutable source-disabled input/expected-output record,
and does not exercise the source feature. It is a runtime regression check,
not the dry source gate. The single RTX 5090 uses the shared launcher lock;
parallel GPU processes would compete for the same device.

During the review no containers or CFD jobs were active and GPU utilization
was zero. Keep CPU work to a two-core build, one-thread independent review and
one-thread E1 preparation, reserve two cores for the host, and keep the
aggregate within the 18-core limit. Count any later GPU regression's CPU use
separately. Refresh `make doctor` before scheduling a resource-intensive case.

No new user input is needed to correct candidate2 or prepare E1. Continue the
already authorized clearly labelled provisional inputs. Measured Restás slot
geometry, synchronized discharge/pressure/flight records and material
properties are needed for built-device claims; missing paper geometry and
inlet/post-processing detail may remain explicit E1 reconstruction
assumptions. No user data substitutes for independent review.

## Primary integration

The primary corrected the stale blocker/status claims, added an all-face
inward-minus-outward mass residual distinct from source-dose attribution, and
archived the candidate2 review. The current worker queue and candidate release
conditions are tracked in [`STATUS.md`](../STATUS.md) and
[`BLOCKER_RESOLUTION_PLAN.md`](../BLOCKER_RESOLUTION_PLAN.md).
