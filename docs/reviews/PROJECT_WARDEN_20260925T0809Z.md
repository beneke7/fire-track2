# Project Warden checkpoint — 2026-09-25 08:09 UTC

Read-only advisory review by the configured Astra Max project Warden. No files
were edited by the Warden; no builds, solver jobs, GPU work, or gate approvals
occurred.

## Confirmed project state

- E0 remains accepted for analytical verification only. Historical P1
  revision 2 remains accepted for its source-event and box-ledger scope; P1
  replay recovery is complete and no replay is needed.
- FluTAS candidate2 remains blocked by three independent defects: the dry
  validator rejects a zero-duration fixture, the bottom return leaves periodic
  momentum-stencil halos inconsistent, and source shutoff may use stale liquid
  ghosts/VOF reconstruction. Its archived patch still matches
  `bd42ab7b17383ae90411aef2e0878c1427a3c3a5f49694eeb28c57659063af40`.
- Candidate3 implementation and behavior-test drafts are isolated but did not
  yet have completed test/build evidence at review time. Three repairs alone
  will not release source CFD.
- The E1 CPU route is explicitly approximate. The Astra E1 audit identified
  unresolved pressure mapping, coordinate/origin scoring, momentum limits,
  pass conjunction, uncertainty operations and E2-release wording. Its
  reviewed draft remains closed to execution.
- The Luna E2 correlated-source method is a proposal only. It does not replace
  source/geometry review or authorize E2 execution before an accepted E1.
- E1 and FluTAS source qualification are independent branches. Neither
  currently needs new user measurements to make provisional, clearly labelled
  progress.

## Critical path and next assignments

1. **Luna FluTAS implementer:** finish candidate3 in its isolated directory;
   complete executable validator, periodic-edge and source-transition tests,
   including dry crossflow; regenerate and preserve exact patch/build hashes.
   A successful behavioral suite, exact build evidence, and exact-hash Astra
   review are required before even a source-disabled candidate GPU regression.
   No source CFD is authorized by candidate compilation.
2. **Luna E1 preparer:** correct the seven E1 review findings with explicit
   provisional assumptions, deterministic scores, zero-component momentum
   normalization, a complete pass rule and accepted-E1-only E2 release
   wording. Keep source reads intact, avoid fitting Figure 13, and return a
   revised decision packet for independent review.
3. **Primary orchestrator:** prepare the source diagnostic schema, telemetry,
   execution contract, fail-closed analyzer and negative checks alongside the
   candidate fixes. Define fixed-step global/interface Courant metrics, finite
   checks, failure-state evidence, all-face mass balance, and enforceable
   resource/stop ceilings; coordinate interfaces with the sole source-patch
   owner.
4. **Astra Max reviewer:** independently review the completed E2 uncertainty
   method while candidate3 and E1 corrections are in progress; later review
   stable exact hashes for candidate3 and the revised E1 packet.

Candidate source progression stays **quiescent dry → dry crossflow/gravity →
one-slot → four-slot → source-enabled crossflow**, with one GPU job at a time
and stop-at-first-failure. The larger GPU pilot is a separate later gate.
Controlled E1 comparison waits for its accepted contract and resource
qualification. A failed or inconclusive E1 does not release E2.

## Compute and external evidence

The three-worker limit is fully occupied alongside the primary, by two Luna
workers and one Astra role. At 08:07 UTC the read-only resource snapshot showed
20 affinity CPUs, about 118.7 GiB available RAM, 261.29 GiB free disk and one
RTX 5090 at 0% utilization with 16 MiB occupied. No solver/container job was
running. The GPU is idle for a specific gate reason: candidate3 lacks completed
tests/build and exact-candidate independent review. The single ordered GPU
queue matches the one-device hardware limit; duplicate jobs would add
contention, not throughput.

Refresh `make doctor` before each compute allocation. Keep the sum of all local
jobs within the measured 18-core ceiling and reserve two host cores. A two-core
candidate build plus one-thread E1 preparation/review leaves room for bounded
analyzer tests, subject to fresh headroom checks. Keep CPU preparation moving
while an eligible GPU checkpoint runs. Do not repeat unchanged P1 or upstream
checks merely to raise utilization.

No new user data is needed for current provisional implementation and review.
Later claims about the built Restás system need measured outlet geometry,
synchronized discharge/pressure/valve traces, and device-specific material and
flight information. Calbrix geometry/source history and raw M134/AG600 ground
measurements would improve later benchmark claims but are not blockers for the
current drafts.

At the Warden's last inspection, `docs/STATUS.md` still claimed the E1 review
had found no high-impact protocol issue, and the blocker plan linked a missing
candidate1 build-log path while ambiguously describing the historical check
count. The primary corrected the status summary and linked the preserved
candidate1 evidence directory; candidate2's ten static/analytic checks are now
clearly distinguished from solver qualification.
