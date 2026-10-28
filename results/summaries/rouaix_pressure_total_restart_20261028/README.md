# Rouaix fine-grid total-pressure restart

This exploratory native continuation tests one boundary sensitivity from the
immutable 0.2 s water-injection checkpoint. It is not an E1 acceptance run or a
paper boundary-condition correction. Only `p_rgh` on `downstreamOutlet`,
`bottomOutlet`, `spanwiseMinus`, and `spanwisePlus` changes to
`prghTotalPressure` with `p0 uniform 0`, `rho rho`, `U U`, `phi phi`, and
`value uniform 0`. Fixed `deltaT=0.0001 s`, 120 ranks on three nodes (40 per
node), and the existing 1000 m/s guard are retained. The requested horizon is
0.2 to 0.3 s with writes at 0.25 and 0.30 s.

## Frozen source and prelaunch checks

- Revision: `4918df20a5c3e8eae4ecbac577f481072dbc179a` (dirty source captured).
- Source capsule: `pressure-total-source-20261028.tar.gz`, SHA-256
  `6397c52e5f097d80644d63ae0a6d93a825e0b9eaa7f9a7b98e8b2bf90a1aa235`.
  The archive contains 20 files; Komondor verified every file against
  `source-sha256sum.txt` before submission.
- Focused tests: `./.venv/bin/python -m pytest -q
  tests/test_rouaix_hpc_restart.py` — 22 passed.
- Actual v2512 two-rank collated I/O utility passed: all four patches changed;
  the parsed `p_rgh` internal array and the other present fields remained
  unchanged across 299,520 cells. This utility used a private static-case copy
  whose time-zero fields were aliased to 0.2 solely to test the command path;
  it was not a physical restart checkpoint. Receipt:
  `native-io/native-utility-receipt.json`.
- The released 120-rank job independently repeated the integrity check against
  the real parent before starting the solver. Its receipt says
  `native_boundary_change_verified_internal_arrays_and_other_fields_unchanged`.
  The parent archive SHA-256 is
  `31010755e705010771de7ed00fb5fb9990e7d2621237c3d881ee22b826cf25c9`; its
  ledger SHA-256 is
  `0baa380005d188edf6c94a0c175b790a5a8af5fa79773ff37ace5da5dda2f300`.
  The measured parent water inventory is 0.2508975771509 m3 at 997.6 kg/m3.

## Slurm and current status

- Solver: job `14702499`, released on `cpu-short`; 3 nodes, 120 tasks,
  22 GiB/node, 90 minutes, CPU only, no requeue. Its actual run directory is
  `/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-total-restart-20261028/rouaix-restart-pressure-total-p0-zero-14702499`.
- After-any audit: job `14702500`, released with dependency
  `afterany:14702499`; it runs the existing frozen HPC finished-run auditor.
- Solver **FAILED 1:0**, ending at 2026-10-28 15:51:46 UTC after 28m46s.
  It completed 495 steps through 0.2495 s, then failed during the attempted
  0.2496 s U solve. At 0.2494 s max speed was 107.34 m/s; during 0.2495 s
  pressure GAMG correctors diverged to 3.45e19 and 8.65e22 residuals before
  the catastrophic velocity growth. No 0.25/0.30 s field, End or new ledger
  was written. The guard signal was acknowledged but the FPE preempted saving.
- Auditor **14702500 COMPLETED 0:0**, with verified compact failure capture.
  The 110-member full attempt archive remains on Komondor (1,739,238,047 bytes),
  SHA-256 `959e129d854689f0a7e5ce90fad7999bcc9f7536f3439024ce045aa8b6173029`.
- [Failure inspection and raw logs](live-14702499/failure-20261028T155146Z/)
  distinguish completed 0.2495 s diagnostics from the attempted 0.2496 s step.
  This parent cannot qualify for the unsubmitted 0.30→0.50 s continuation.
  The next matched diagnostic changes the pressure linear solver to PCG/DIC;
  it is recorded separately and does not overwrite this attempt.
- Held/released Slurm readbacks and the captured pending/start status are in
  this directory. `gate-manifest.json` preserves the declared input and
  eligibility evidence; `submission-record.json` captures the released jobs.

This failed exploratory sensitivity does not establish fine-grid stability or
that total pressure is more physically accurate.
