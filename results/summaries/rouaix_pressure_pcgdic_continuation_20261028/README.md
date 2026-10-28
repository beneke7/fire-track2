# Rouaix PCG/DIC continuation dispatch

**Dispatcher 14706859 was released on 28 October 2026 at 16:36 UTC** and is
pending `afterany:14705632`. Root independently verified all 28 recorded v2
source members, the held readback, and released dependency/resource readback.
See [submission record](submission-record.json) and
[released readback](dispatch-readback-released-14706859.txt). No child exists
until the actual parent endpoint passes the contract checks.

The continuation remains conditional on parent `14705632` reaching a clean,
verified .255 s endpoint. The parent was still running at the last scheduler
check (24:41 elapsed); its after-any auditor is `14705633`.

The pre-release readback is in [dispatch-readback-held-14706859.txt](dispatch-readback-held-14706859.txt): one task, two CPU slots, 4 GiB, 15 minutes, `cpu-short`, no requeue. Slurm allocated two slots for the 4 GiB controller request, so the corrected source explicitly requests two while keeping numerical and BLAS/OpenMP thread counts at one. Root reviewed and released it; no child or child auditor has been submitted yet.

The active frozen source is correction capsule v2 at
`results/summaries/rouaix_pressure_pcgdic_20261028/continuation-source-v2/`.
Its SHA-256 is
`ca952303498af8b83d37bc1c39a5ec1f082cc32d6a6a779bb58c94d435b0a917`; the
outer index SHA-256 is
`234f9e2d8707383c56ee430115ef2e19a3e210e5ca308b7ca8fcdbfb198fda20`.
It preserves the first capsule
(`f1ecdb5ceab3e5fa6ebb3af1c5aebf1ceb93dbf1e7cd2ad87f5d1b20ec399048`)
and records the two-slot
resource correction. The first held submission `14706710` was canceled after
its readback showed two allocated CPUs despite a one-CPU declaration. The
single `--mem-per-cpu=4G` probe `14706778` was also canceled after the same
two-slot allocation; receipts are under `attempts/`.

Local checks: `./.venv/bin/python -m pytest -q
tests/test_rouaix_hpc_restart_dispatch.py tests/test_rouaix_hpc_restart.py
tests/test_rouaix_hpc_restart_audit.py` passed 51 tests; Ruff, format, Bash
syntax, Python compilation, and capsule
member-hash checks passed. The remote v2 capsule/member hashes, Python 3.11.7,
NumPy 1.24.4, and runner contract imports also verified.

The dispatcher will refuse a guarded, incomplete, paused, or otherwise
unverified parent. It is armed; no continuation contract exists until the
actual parent endpoint is available and verified.
