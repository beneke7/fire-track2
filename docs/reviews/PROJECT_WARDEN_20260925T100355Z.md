# Project Warden checkpoint 5 — 2026-09-25 10:03:55 UTC

Read-only Astra Max audit after candidate4's GPU regression and E1 review 4.
The Warden edited no files, launched no builds or simulations, and approved no
scientific gate.

## Confirmed state

- The candidate4 source-disabled regression passed. All 142 bundle manifest
  entries matched; the copied bubble case lacked `source-boundary.in`; logs
  contain `*** Fim ***` and `True True`. Thirteen GPU samples and eleven
  container samples are valid. This is only a source-disabled regression, not
  source or scale evidence.
- E1 review 4 accepted the exact gate/audit pair for static case, dictionary,
  geometry, mesh and sampler preparation only. It released no
  characterization, E1 execution, E2 advancement or scientific result.
- Active assignments at the audit were the E2 M03 author, the Astra B1–B3
  deblocker, and this Warden. The E2 worker's task is the exact evaluator and
  identity utilities; its old agent name is stale. No worker yet owned E1
  static preparation.
- The new `make doctor` snapshot confirms 20 effective CPUs, no CPU quota,
  118.50 GiB available RAM, 260.82 GiB free disk, and one idle RTX 5090 at
  0%/16 MiB. No compute process or container was running. These are
  availability readings, not permission to bypass a gate.

## Critical path and assignments

1. **Primary assigns Luna Max E1 static preparation immediately.** Use a
   disjoint E1 case/geometry/sampler package. Resolve D-NUT-BC only as a
   provisional, sourced mapping; check complete dictionaries, geometry and
   hashes, pressure reconstruction, patch/field consistency, inlet flux,
   initial inventory, and synthetic contour/sign/zero-reference/score cases.
   No CFD. The primary independently checks the package before review.
2. **Astra B1–B3 deblocker finishes the bounded source protocol plan.** Separate
   pre-run eligibility (candidate, call order, sufficient observables, analyzer
   and frozen contract) from runtime qualification (measured results from the
   authorized ordered trials). Specify the source-grounded timestep condition,
   fixed/adaptive timestep rule, schema, uniform-grid restriction, limits,
   failure rules, and resource cap. Do not call `cfl=0.2` enforced if the
   selected constant-dt path bypasses `chkdt_tw`.
3. **Luna Max implements the B2 analyzer only after the primary freezes its
   interface.** Own disjoint implementation/test files; include positive and
   negative fixtures for interval/state joins, row counts, dry-source rows,
   nonfinite/duplicate/truncated data, boundary signs, mass/phase validity,
   distinct divergence norms and abnormal completion. The analyzer cannot
   invent or silently relax missing runtime observables.
4. **Existing Luna E2 implementer completes M03 work in its isolated module.**
   Archive reproducible arithmetic/support/integral, rounding, identity and
   dependency-mutation evidence. Method acceptance remains separate from
   scenario coverage, target uncertainty, scoring and CFD release.
5. **Astra independently reviews stable implementation snapshots.** Only after
   B1/B2's pre-run contract is accepted may the primary schedule quiescent dry
   → dry crossflow/gravity → one-slot → four-slot → source crossflow, sequentially
   and stopping at first failure. E1 characterization has its own reviewed
   contract and remains blocked.

The B2 plan must not create a circular dependency: pre-run eligibility allows
an attempt; runtime qualification is assessed from that attempt's recorded
evidence. Do not require measurements from a run as a prerequisite for making
that same run eligible.

## Compute and user dependencies

Fill the three worker slots with independent, gate-ready preparation, analysis
and review; budget shared CPU jobs against current headroom and leave two cores
for the host. A safe example at the 18-core project budget is 14 threads for
static meshing, 2 for a GPU job, and two one-thread CPU tasks. Measure actual
scaling and account for memory; a thread cap is not a reservation. Run one
eligible GPU trial through the shared lock while independent CPU work proceeds.
The single RTX 5090 cannot productively run parallel GPU trials. There is no
eligible source GPU job yet; analyzer/protocol/timestep review is the gate. Do
not repeat candidate3, candidate4 or P1 runs unchanged.

No new user input is required for the assignments above. Measured built-device
geometry, discharge/material/flight data and independent deposition or
calibrated plume evidence remain necessary for later built-system claims.
Cluster access is unestablished.

## Contract integration

The next Warden checkpoint should follow executable preparation or a material
blocker decision, not an unchanged status edit. Keep the existing milestone,
two-checkpoint, repeated-blocker and high-severity decision cadence. Distinguish
GPU-using runtime smoke from CPU compilation/code-object inspection in the
workflow contract. Keep a single ordered GPU queue and record the exact gate
when it is empty.
