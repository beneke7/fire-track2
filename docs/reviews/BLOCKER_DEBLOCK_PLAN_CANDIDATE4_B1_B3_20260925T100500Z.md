# Astra Max blocker deblock plan — candidate4 B1–B3

**Completed:** 2026-09-25 10:05 UTC  
**Role:** independent blocker planner; read-only  
**Status:** recommendations for the primary to integrate. This plan does not
approve an execution protocol or source CFD.

## Dependency graph

```text
B0 candidate4 source-disabled GPU regression                         DONE
  │
  ├─ B1-pre: exact candidate/input restrictions, call-order/helper evidence,
  │          sufficient producer observables, no unresolved preflight defect
  │        ├─ freeze final source schema and numerical/resource rules
  │        │        ├─ implement deterministic analyzer + offline fixtures
  │        │        └─ implement source launcher + failure/cleanup fixtures
  │        └─ Astra Max exact review of candidate, protocol and tools
  │
  └─ primary records pre-run eligibility
           │
           └─ dry_four → dry_crossflow → quiescent_one → quiescent_four
              → crossflow_four; one immutable attempt at a time, stop first fail
                        │
                        └─ B1-runtime/B3 diagnostic qualification
                             └─ separately reviewed 1–3 million-cell pilot
```

Keep **B1-pre** separate from **B1-runtime**. B1-pre establishes that the exact
candidate is eligible to attempt a source diagnostic: supported inputs,
reviewed call order, helper and transition evidence, adequate serialized or
asserted observables, and a complete accepted protocol. B1-runtime consists of
the measured source/projection/flux evidence from the authorized ordered trials.
It cannot be required before launching those trials without creating a
circular blocker.

## Decisions required before B2 freeze

### Fixed timestep

The pinned source audit identifies `src/chkdt.f90:92–112` and
`src/apps/two_phase_inc_isot/param.f90:272–280` as the AB2 timestep restriction
and constants (`cfl_c=1`, `cfl_d=1/6`). Candidate4 records the advective
Courant quantity, but its `constant_dt=T` path bypasses `chkdt_tw`; the hashed
`dns.in` also contains `cfl=0.2`. Therefore the existing file cannot claim
that the 0.2 factor is enforced. This does not prove the fixed step unstable.

For the current uniform grid/material fixture, the reviewer estimated
`dt/dtmax ≈ 0.200036896` at initial dry crossflow; adaptive `cfl=0.2` would
give `dt ≈ 9.9981555e-5 s`. During active crossflow the top-boundary advective
Courant lower bound is about `0.2192`, implying `dt/dtmax ≥ 0.219235179`.
Before protocol freeze, independently reproduce the complete pinned bound,
including advective, viscous, gravity and capillary terms and the zero-advection
fallback. Then select and review an explicit fixed-step safety factor, enforce
the exact `gr=0` input hash, or prospectively amend the timestep/schedule and
candidate. Do not select a limit after viewing source-run outcomes.

### Producer observables and pressure path

Candidate4's six current CSV schemas cover flux/momentum, rate, inventory and
aggregate corrected-state velocity/divergence. The reviewed gate also calls
for stage alpha/rho/mu ghost-state evidence and a requested/applied boundary
velocity check. The source audit found `restas_source_assert_velocity` checks
slot W and bottom W but does not serialize the check; no per-cell request/apply
audit or stage-indexed ghost history was identified in the CSVs. A bounded
source-readiness audit must map every gate observable to an existing artifact
or an accepted executable assertion. Do not let the parser fabricate missing
data or relax the gate. If material observables are absent, preserve candidate4
and add only compact stage-indexed mismatch counts, maximum errors and
nonfinite counts in a separately reviewed candidate5. Any changed candidate
needs host checks, native build/code-object evidence, exact review, and its
smallest eligible source-disabled GPU smoke before source execution.

The pinned pressure path is a direct FFT/tridiagonal solve, not an iterative
pressure solver. The protocol should declare iterative residual/iteration
budgets **not applicable** with source evidence and instead freeze justified
projection/continuity checks. The reviewer proposed the upstream
`divmax <= small` check (binary64 `small ≈ 7.02166694e-9 s^-1`), plus a
separately checked L1 bound and signed closure identity. These remain proposals
for independent review; the existing 0.1% mass and inherited Courant budgets
are not approved limits.

## Suggested bounded assignments

| Owner | Scope | Resource and acceptance |
| --- | --- | --- |
| Primary | Own the B1-pre/B1-runtime wording, output-schema freeze, proposed `experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.execution.json`, and release decision. | Record exact artifact hashes and why source GPU work is eligible or blocked. No blank limits; keep producer limitations explicit. |
| Luna Max source-readiness auditor | New `docs/reviews/CANDIDATE4_SOURCE_RUNTIME_READINESS_DRAFT.md`; source-line table, full timestep derivation and observable-to-producer mapping. | One thread, 2 GiB, no GPU. If producer gaps require candidate5, separately assign all files under `containers/flutas/candidate5/`; preserve candidate4. |
| Luna Max analyzer implementer | Proposed `src/aerial_drop/flutas_source_gate.py`, `scripts/analyze_flutas_source_gate.py`, `tests/test_flutas_source_gate.py`, and fixtures. | Two CPUs, 2 GiB, no GPU. Start after the primary freezes schema. Require deterministic JSON and nonzero exit on every non-pass. |
| Luna Max launcher implementer | Proposed `containers/flutas/run-source-boundary-gate.sh`, locked wrapper and offline launcher tests. | One CPU, 1 GiB, no GPU. Must not dispatch after failed preflight or a failed stage; preserve immutable attempts, timeout, cleanup, provenance and resource behavior. |
| Astra Max independent reviewer | Exact candidate/schema/parser/launcher/manifest and limits review. | One CPU, 2 GiB, no GPU. Independently derive expectations and challenge negative fixtures; accept exact hashes, not author summaries. |

These are sequential staffing waves within the three-worker pool, not five
simultaneous agents. Keep all local processes within the measured 18-core
budget and preserve two host cores.

## Analyzer acceptance evidence

- Pin image, patch, case, launcher, analyzer and contract identities; reject
  changed or unknown hashes.
- Parse exact schemas and finite numbers; reject malformed integer keys,
  nonmonotonic, duplicate, missing, extra or truncated rows. Expected rows:
  source `14/56/0` for one-slot/four-slot/dry; off-mask and rate `14` each;
  boundary, mass and velocity states `0–14`, `15` each. An empty dry source
  flux table is permitted only where declared; header-only required histories
  fail.
- Join source/off-mask/rate interval `k` to state `k+1` for the corresponding
  post-step ledger while preserving the velocity state `k` actually applied
  during that interval. State `k+1` supplies the next transport interval.
  Count global off-mask fields once.
- Independently recompute geometric mass, each momentum component, per-slot
  attribution, six-face inventory, residuals, periodic-pair cancellation, net
  volume flux, maximum/L1 divergence and complete timestep bound. Do not trust
  producer residual columns without recomputation.
- Expected dose is `0.072 kg` per active interval per slot and `0.72 kg` per
  pulse. Four-slot total is `2.88 kg`. Quiescent per-slot impulse is
  `(0,0,-3.456) kg·m/s`; crossflow is `(-36,0,-3.456)`. Active intervals are
  2–11; no new source input is permitted in 12–13. Compare four-slot scaling
  with the separately accepted one-slot bundle.
- Require normal completion, steps 1–14 ending `0.0014 s`, complete
  `time.out`, `vof_info.out`, performance and resource histories, and no
  fatal/abort markers even with exit zero. Preserve partial rate-failure data.
- Test valid dry/one/four/crossflow fixtures plus NaN/Inf, zero-safe
  normalization, empty-interface semantics, shifted pulse, reordered,
  duplicate and truncated rows, off-mask double counting, wrong signs/units,
  periodic mismatch, corrupted momentum, post-shutoff source, hidden local
  divergence, breached limits, false solver success, missing samples and hash
  drift.

## GPU release recommendation

No source GPU run is eligible now. After exact protocol approval, consider one
rank, two CPU cores, one OpenMP/BLAS thread, an 8 GiB container RAM ceiling, a
sampled 24 GiB VRAM stop ceiling and 600 seconds per stage through
`scripts/run_local.py --gpu`. The primary and independent reviewer must freeze
those proposed ceilings first; the bubble run does not profile source cases.
Sample actual resource use during solver execution and retain failed runs. Run
source stages sequentially and stop after the first failure.

No measured device geometry, external source history or cluster access is
needed to resolve these synthetic implementation blockers. Those remain
necessary for later built-system scientific claims.
