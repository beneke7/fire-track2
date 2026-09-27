# Project Warden checkpoint 13

**25 September 2026, 15:00:17 UTC · Astra Max / max · advisory, read-only**

This checkpoint reviewed the source-release contract proposal, H3 annex, H4
follow-up, H7 lifecycle audit, M3 arithmetic bundle, current status and blocker
plan, workflow, validation contract, and prior Warden/deblock records. It made
no repository edits and started no tests, builds, containers, solvers or GPU
jobs. It approves no candidate, contract, launch or scientific gate.

## Exact artifacts inspected

| Artifact | SHA-256 |
| --- | --- |
| `experiments/FLUTAS_CANDIDATE5_SOURCE_RELEASE_CONTRACT_v0.3.md` | `262a841846806c4f2e1eee18c2936f765b04c38a9b4591e6eb52c44ad7720051` |
| `experiments/FLUTAS_CANDIDATE5_INPUT_SCHEMA_v0.1.md` | `20afc81766fd0068bbc24732339412c5e10ca8707e40557038d68eee6c1139db` |
| Candidate6 H4 two-halo exact review | `176475954e7540739b7267f0a6d54cf6e298624dfb0141e7d5fa36616c3bf2d4` |
| H7 outer-runner audit | `c7b763c7dab463b498e851b19f10b8cc9a28d96bf31d28f1cfdb4fd3dc57f513` |
| M3 `SHA256SUMS` | `6f2c96cd0d96953670cb263c2362ba149a21edcf204b71165ec75cee43617b49` |

The independent hash checks passed for the candidate6 root, retained H4 bundle
and candidate5's 15 allowlisted input files. H4 accepts one-halo and
explicit-slice two-halo helper indexing, including its shifted-index negative
control. It does not qualify production integration, source runtime, receipt
or GPU launch. The H3 annex maps the hash-pinned 29 DNS and 8 VOF records and
fixture tuples, but strict parser acceptance is still open. M3 retains optimized
helper output and independent arithmetic/byte comparisons; phase and velocity
tables are synthetic. Ordinary subnormal tests stop at the positivity guard;
altered-MXCSR overflow evidence is supplemental. H7 confirms the outer runner
can release `flock` without verifying Docker container termination; existing
shell tests bypass the real `run_local.py` owner.

## Warden advice

1. Finish and freeze the H5 interface before requesting exact review of the
   complete v0.3 contract. H5 must define all six ledger headers and token
   types, raw roster and shapes/bounds, stop-prefix examples, zero rules,
   primitive operands and the static output-size bound. Reject any
   self-declared roster or undefined observable.
2. Assign the next exact Astra review to M3. Check flags, independent
   arithmetic, serialized bytes, retained dependencies, synthetic-table
   limits, and whether early invalid-input rejection meets the stated
   requirement. Do not add probes unless the reviewer names a specific
   unresolved condition.
3. After the interfaces pass review, split implementation into disjoint
   producer and independent-auditor work: strict staged-input reader/header
   flush/raw capture versus staged-byte binding and independent six-ledger
   reconstruction. Test corruption, truncation, all stop prefixes and retained
   compiled outputs. Do not reuse the historical whole-array validator
   unchanged.
4. Repair H7 at the outer lock owner. Fake-run tests must cover client exit
   with a surviving container, graceful and forced stop, sampler gaps, timeout
   and signals, failed termination verification, and second-job exclusion.
   Keep the GPU lock until cleanup is verified.
5. Continue bounded provenance work, but defer final OCI export until the
   receipt schema and reviewed producer are fixed. Include export/layout bytes
   in disk bounds and test small-layout corruption first.
6. Advance E1 decision work independently: dispose the completed decision
   packet, obtain exact independent review, and resolve D-NUT/contact-angle,
   capture/initialization choices and timestep/Courant compatibility before
   mesh or characterization.

These are sequencing recommendations, not acceptance decisions. No additional
user data are needed for engineering work; measured geometry, synchronized
discharge/pressure, material properties, flight/wind and calibrated field
observations remain necessary for claims about the built device and E4/E5.

## State observed at close

At 14:57:34 UTC `docker ps` was empty and the RTX 5090 reported 0% utilization,
16/32,607 MiB and 22.48 W. At 14:58:40, CPU affinity was `0-19`, available
RAM about 117.5 GiB and free disk about 260 GiB. These are point-in-time
readings, not reservations. The GPU queue was correctly empty: no reviewed
source job was eligible. E0 remained the only completed scientific gate; B1-
pre/B2 and all source execution remained closed.

At Warden close, the raw-roster audit was active and M3 evidence complete but
awaiting exact review. Remaining documentation drift included queue timestamps
and active-work labels in `STATUS.md`, Warden/cadence wording in the blocker
plan, and the need to re-check H4 wording in the exact v0.3 snapshot. Following
primary archival/disposition, the next Warden should be triggered by two newly
accepted bounded checkpoints, a material source/solver-interface change, a
gate transition, or a repeated blocker that changes the resolution. Do not
repeat an unchanged broad audit. The proposed first source sequence remains
`dry_four → quiescent_one → quiescent_four`, independently audited between
stages and stopped at the first real failure.
