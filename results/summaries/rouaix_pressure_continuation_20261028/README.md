# Superseded Rouaix total-pressure continuation dispatch

The earlier 0.3→0.5 continuation was **not submitted**. Parent job `14702499` terminated as
`failed_preserved` at 0.2496 s after 495 steps, with exit 143 and no native
`End` marker or .25/.3 checkpoint. It fails the exact clean-parent contract, so
there is no child source capsule, solver job, or continuation result. The
existing parent auditor `14702500` was left untouched.

The local dispatcher and bounded Slurm wrappers are prepared for review. The
dispatcher verifies source hashes, `PAUSE`, disk reserve, and the hash-bound
parent contract before submission; it submits child and audit held, verifies
resources/ownership/dependencies, then releases the audit before the child.
Its fail-closed parent and scheduler checks are covered by
`tests/test_rouaix_hpc_restart_dispatch.py`.

Checks run:

- `./.venv/bin/python -m pytest -q tests/test_rouaix_hpc_restart_dispatch.py` — 6 passed after integration fixes for Slurm's dependency suffix and spooled script path.
- `./.venv/bin/ruff check cases/e1_rouaix_hpc_restart/dispatch_pressure_continue.py tests/test_rouaix_hpc_restart_dispatch.py` — passed.
- `./.venv/bin/ruff format --check cases/e1_rouaix_hpc_restart/dispatch_pressure_continue.py tests/test_rouaix_hpc_restart_dispatch.py` — passed.
- `bash -n cases/e1_rouaix_hpc_restart/dispatch_pressure_continue.sbatch cases/e1_rouaix_hpc_restart/restart_pressure_continue.sbatch` — passed.
- `./.venv/bin/python -m py_compile cases/e1_rouaix_hpc_restart/dispatch_pressure_continue.py tests/test_rouaix_hpc_restart_dispatch.py` — passed.

This profile is superseded by the PCG/DIC .255→.3 candidate documented in
`results/summaries/rouaix_pressure_pcgdic_continuation_20261028/`. No source
capsule or Slurm job from the earlier profile was released.
