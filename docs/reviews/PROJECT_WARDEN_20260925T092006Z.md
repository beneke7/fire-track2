# Project Warden checkpoint 3

Reviewer: Astra Max, `project_warden`, read-only.
Snapshot: 2026-09-25 09:20 UTC. No files, builds, tests, CFD or GPU jobs were
changed or launched by the Warden. No scientific gate was approved.

## Confirmed state and stale claims

- Candidate3's source-disabled GPU regression passed. Its runtime RAM/VRAM
  peaks remain unknown. Preserve the bundle and do not repeat the unchanged
  regression.
- Candidate4 implementation and CPU build are complete. The final evidence is
  `containers/flutas/candidate4/evidence/runs/20260925T091602Z-1994261/`;
  patch SHA-256 is
  `2eddbe5cc406ecbc60e7ca1fe9ba3a5ff61b130283e74772b1593f1d385959ff`, and
  image ID is
  `sha256:3086f0312b3a74dd7d0f03102d4b8584a8dd1fe4091364615cb0e580f00283bb`.
  The build log records 14 Python tests, host behavior/ledger checks and
  `sm_120.cubin`; the Warden reconciled all 12 build-input and 15 fixture
  hashes. Exact independent review and runtime GPU evidence remain pending.
- E1's second exact-hash review returned **REVISE** with seven findings. The
  correction is still changing. Previously reviewed hashes
  `3e5fb064…` and `083746f0…` identify historical reviewed files, not the
  current draft. Freeze paired final hashes before the next review.
- E2's current method hash independently matches
  `867403defd73046a8faf358b97e3828c38eb973bc7961d7d986d936df1265520`.
  Its arithmetic checks are author-reported and not archived as a reproducible
  script/output. It still needs exact review, a generator and manifest, target
  uncertainty and score/budget decisions. No E1–E6 comparison has passed.
- No source-enabled GPU diagnostic or E1 characterization run is eligible.
  Existing provisional-input authorization is sufficient for current work;
  no new user input is needed now.

## Critical path and steering

The immediate route is candidate4 exact-hash review, then one bounded
source-disabled GPU regression if the review and runner provenance clear. The
GPU runtime wrapper currently records the candidate3 patch hash even when
invoked for candidate4 (`containers/flutas/run-candidate-gpu-regression.sh`,
lines 52–53). Make that provenance candidate-aware and verify the exact image,
entrypoint, actual-case absence of `source-boundary.in`, resource sampler and
positive stage evidence before launching candidate4. Candidate4's Docker image
has an inherited `/bin/true` entrypoint, so the trial must explicitly invoke
the test executable.

Source execution is a separate chain: reviewed candidate4 semantics → frozen
schema and justified limits → fail-closed analyzer and execution contract →
independent protocol review → quiescent dry → dry crossflow/gravity → one-slot
→ four-slot → source crossflow. Stop on the first failed stage. Candidate4's
advective Co telemetry is diagnostic; it does not impose or validate the full
fixed-step stability restriction. The analyzer must include new rate-check
and non-summable off-mask tables, divergence measures, phase boundedness,
residuals and required pressure diagnostics.

The E1 CPU preparation route remains independent. Finish the seven review
corrections and freeze the packet. Clearly labelled draft geometry, dictionaries
and synthetic samplers may be prepared under existing user authorization before
scientific approval. Keep that separate from a preregistered, bounded
characterization run, mesh/time-step freezing, and later controlled E1 approval.
Accepted E1 remains upstream of E2 execution. Eighteen E2 histories do not prove
uncertainty coverage.

## Next assignments and resource use

| Owner | Work and dependency | Acceptance evidence |
| --- | --- | --- |
| Astra Max reviewer | Review exact candidate4 patch/build and regression launcher. | Hash-bound findings and explicit source-disabled runtime disposition; no source gate approval. |
| Primary | Fix candidate-aware provenance and reconcile STATUS / blocker plan. | Exact wrapper hash, image ID, entrypoint, case-input check and sampler behavior. |
| Luna implementer | After primary freezes the analyzer interface, implement it in separately owned files. | Synthetic valid and invalid histories for row counts/order, interval/state joins, empty interfaces, nonfinite values, dry rows, incomplete runs and all numerical gates. |
| E1 Luna author | Finish the seven corrections and freeze gate/audit hashes. | Finding-by-finding response and synthetic contour, sign, aggregate score, zero-reference and sampling checks. |
| Astra Max reviewer | Review frozen E1; use a separate pass for E2 hash `867403de…`. | Exact-hash method decisions; keep E2 method approval separate from generator/CFD authorization. |

At the Warden snapshot, the candidate4 worker had completed; E1 and the Warden
were active. Reassign the completed worker promptly when a slot is free. The
doctor snapshot reported 20 effective CPUs, about 118.6 GiB available RAM,
261.0 GiB disk and one 31.8 GiB RTX 5090. Refresh it before the next allocation.
The candidate4 build used two CPU cores and no GPU. The next source-disabled
trial, once eligible, fits the established two-CPU/600-second envelope and
should overlap independent one-CPU analyzer, E1-preparation and review tasks;
reserve two host cores and capture runtime resources.

The GPU is not eligible at this snapshot because the exact review and
candidate-aware runner provenance are unresolved. Repeating candidate3 or P1
would add no evidence. Later measured Restás geometry/discharge/material/flight
inputs and independent deposition or calibrated-plume evidence are needed for
built-system claims; they do not block today's software/protocol preparation.

## Project-document corrections

- Update `docs/STATUS.md` with candidate4's completed build and current review
  state, and archive this memo.
- Reconcile E1 preparation wording in `docs/BLOCKER_RESOLUTION_PLAN.md` so it
  allows authorized draft inputs and synthetic samplers before approval.
- Clarify in `docs/VALIDATION.md` that the upstream base lacks separate pulsed
  slots; patched candidates add an unqualified implementation and do not pass
  the source gate.
