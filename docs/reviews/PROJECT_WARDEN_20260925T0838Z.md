# Project Warden checkpoint — 2026-09-25 08:38 UTC

Read-only Astra Max steering memo. No files changed, builds or solver jobs
launched, GPU used, or scientific gates approved by the Warden.

## Confirmed state

Candidate3's exact review is complete and accepts the three candidate2 repairs
and retained short-x/long-y geometry for patch
`055758a2690fe4bb9003bdc54665cbc63f67e490f8bd1e307d71ca6d013a4319` and image
`sha256:90f1261308ab56e52ee29d129deefad86a19b352cef79b43feca08df6762e1c3`.
The Warden independently rechecked all 11 build-input hashes and 15 fixture
hashes against immutable evidence. The review permits a separately recorded
source-disabled hardware/upstream regression only. E0 and P1 revision 2 retain
their established analytical and source-ledger scope. No E1–E6 comparison or
ground-delivery validation has passed.

## Critical path and blockers

The FluTAS path is candidate3 source-disabled regression → a new immutable
candidate with telemetry and behavioral coverage → complete analyzer and
execution protocol → exact review → ordered source diagnostics → separately
reviewed GPU pilot. The independent CPU E1 branch proceeds in parallel:
stable corrected packet → source/physics/metric decisions → mesh and resource
qualification → frozen contract → E1 comparison. GPU source qualification
does not block E1 preparation; E1 does remain a prerequisite for E2.

Source execution remains blocked by measured per-step global/interface Courant
diagnostics, empty-interface semantics, applicable stability restrictions,
and justified numerical limits. The analyzer must check local maximum and L1
divergence independently because integrated-divergence versus boundary-flux
closure alone is a telescoping identity. It must distinguish source interval
`k`, completed inventory state `k+1`, and the next velocity profile; handle
repeated global off-mask totals, header-only dry source output, differing signs
and units, and incomplete/error-terminated records. Expected row counts are 14
source rows for one slot, 56 for four, zero for dry, and 15 initial/completed
rows in each other ledger. Add behavioral coverage for actual rho/mu refresh,
production halo width one, audit output and unsupported-input rejection. Flux
assertion failures should preserve measured and expected values before aborting.
Freeze resource/numerical limits, schema, hashes, launcher and independent
protocol approval before source execution.

The E1 draft requires inlet-specific phase weights and momentum references.
At the current snapshot, a shared `rho*alpha` definition conflicts with the
nonzero +x gas-inlet reference if `alpha` is `alpha.water`; its zero-component
set must also differ for liquid and gas. The primary has notified the author.
The scientific reviewer must assess revised formulas, proposed Courant limits,
source-time/width assumptions and the complete pass rule before freezing.

The revised E2 source-history method has changed release-time semantics. In
particular, positive shifts may imply starting the solver before absolute zero;
the relationship between figure time and elapsed time from release remains
open. Scenario admissibility, target-coordinate uncertainty and score budgets
also remain unresolved. Do not call a matrix approved before those decisions.

## Recommended next assignments

| Owner | Scope and dependency | Acceptance evidence |
| --- | --- | --- |
| Primary | Complete the candidate GPU-regression launcher and own schema, execution contract, queues and status. | Exact image/runner hashes, actual-case source-input absence, explicit test entrypoint, fresh evidence, stage exits and resource record. |
| Luna Max worker | New isolated `candidate4/` for measured telemetry and remaining behavioral checks; preserve candidate3. | Independent analytic expectations, executable helper tests, immutable build/input hashes and exact review. No worker-scheduled GPU job. |
| Existing Luna Max E1 worker | Finish corrected E1 packet, then help with analyzer implementation in separately assigned files after schema freeze. | Stable E1 hash/finding dispositions; later synthetic positive/negative parser fixtures and deterministic reports. |
| Astra Max reviewer | Reuse the reviewer for stable E1, revised E2, then the new candidate/protocol. | Separate exact-hash decisions; no implementation edits or self-approval. |

The old GPU wrapper is unsuitable for candidate3 because its `/bin/true`
entrypoint would produce a no-op success. The independent review's explicit
`/usr/local/bin/flutas-gpu-tests` override, immutable image, source-input
absence check, fresh evidence bundle and shared GPU lock are required. Record
runtime resources separately from an initial device snapshot.

The recorded machine snapshot is 20 effective CPUs, 118.7 GiB available RAM,
261.1 GiB free disk and one 31.8 GiB RTX 5090. Refresh `make doctor` before
allocation. The proposed two-CPU regression, two-CPU build, one-thread
preparation, and one-thread reviewer total six CPUs; reserve two host cores and
never exceed the measured 18-core project ceiling. Keep the 600-second
regression cap and GPU lock. Do not repeat unchanged smoke/P1 work to fill the
GPU. No new user input blocks these assignments. Actual Restás geometry,
synchronized discharge/material/flight measurements and independent deposition
or calibrated plume evidence are needed for built-device claims. Calbrix raw
inlet/geometry data and M134/AG600 measurements remain external evidence for
later reconstruction/validation limits.
