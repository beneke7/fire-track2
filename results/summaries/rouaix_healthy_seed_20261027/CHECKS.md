# Preparation and launch checks

- Focused local tests: `.venv/bin/python -m pytest -q tests/test_rouaix_hpc_case.py tests/test_rouaix_hpc_runner.py` — 92 passed.
- Ruff: `uv run --frozen ruff check cases/e1_rouaix_hpc/prepare_case.py cases/e1_rouaix_hpc/run_pilot.py tests/test_rouaix_hpc_case.py tests/test_rouaix_hpc_runner.py` passed; matching `ruff format --check` reported all four files formatted.
- The 0.2 s option is validated as 2,000 fixed 0.0001 s steps, exact endpoint 0.2 s, with only initial/final full-field write times; undeclared 0.3 s remains rejected.
- Qualified mesh validator accepted 18 archive members, 10,099,265 cells, SHA-256 `8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787`. Qualification retains one exact `concaveCells` exception and no prism layers.
- The frozen capsule has 25 members. Every remote member name, type, byte count and SHA-256 matched the capsule index. Capsule SHA-256 is `64f3da5646bd002918f2c407d918e1810ab943d5c119751bde1783e4d824ef6b`.
- Remote mesh archive was a same-device, same-inode hardlink to the existing qualified archive; no second full mesh copy was made.
- Before submission the project PAUSE sentinel was absent, project quota was below soft limits, and the exact staged script/input paths were readable. The root source tree, capsule and mesh were verified before the held submissions.
- Parent readback verifies one node, 120 tasks/CPUs, 64G, 2h, no requeue, `ml-vof`, normal QoS, and exact `pilot.sbatch`/work directory. Its explicit ROUAIX exports are in the preserved command receipt; Slurm JSON does not expose a job environment field, so inherited `ALL` values were not dumped.
- Auditor manifest contains only parent `14669440`; frozen auditor SHA-256 is `e49893ce488afe17a0e4536ae6b16f4dc830984fd1b8bd482d8b781fcbdd3989`. Auditor readback verifies `afterany:14669440`, 1 CPU, 1800M, 10m, no requeue. The wrapped command is preserved because Slurm reports `Command=(null)` for the inline `--wrap` job.
- At last readback (2026-10-27T11:10:50Z) the parent was released but pending for `Priority`; the auditor was released but pending for its unfulfilled dependency. No solver step or terminal audit result exists in this bundle. Completion, stability beyond 0.2 s, conservation, benchmark fidelity and physical validity remain unestablished.

The measured original-scheme 0.05 s solver runtime was 1,638.392448 s. Linear projection to 0.2 s plus setup is about 6,754 s of a 7,200 s limit, leaving about 446 s. This is a narrow, uncertain runtime margin; it is not a completion guarantee.
