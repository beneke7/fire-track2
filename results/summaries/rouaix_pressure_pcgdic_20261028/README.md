# Rouaix fine-grid pressure PCG/DIC sensitivity

This is a CPU-only exploratory continuation from the immutable water-injection
checkpoint at 0.2 s. It repeats the four-patch `prghTotalPressure` `p0=0`
boundary intervention from job 14702499 and changes only the `p_rgh` linear
solver policy. It is not an E1 acceptance run, a paper boundary-condition
correction, or physical validation.

## Diagnostic basis

Job 14702499 stopped at .2496 s after the completed .2495 s solve produced a
maximum speed of 3.846e51 m/s. At .2495 s, `p_rgh` corrector 1 fell from a
0.3587 residual to 0.00331 in two iterations. Correctors 2 and 3 then ended at
3.45e19 and 8.65e22 after the original 100-iteration cap. The attempted .2496
step subsequently encountered an FPE in vector `U` PBiCGStab after alpha
extrema left [0, 1]. The captured after-any audit for job 14702500 completed
successfully and classified 14702499 as `slurm_failed`; both audit and result
archive receipts are recorded in `gate-manifest.json`.

This variant retains the same .2 s donor, mesh, physics, fixed 0.0001 s step,
four `p_rgh` total-pressure patches, and 1000 m/s guard. It changes
`p_rgh` from GAMG/DICGaussSeidel to PCG/DIC, preserves `tolerance 1e-8` and
`relTol 0.01`, and raises `maxIter` from 100 to 1000. Since both the solver and
the iteration cap change, report whether any pressure solve exceeds 100
iterations and whether the 1000-iteration cap is reached. Keep all residuals
and iteration counts; no new convergence threshold is introduced.

## Declared run

- Start .2000 s; target .2550 s (550 fixed steps).
- Collated field writes every .005 s with `purgeWrite 2`, retaining the two
  newest checkpoints in this run directory.
- 120 MPI ranks on three nodes (40 per node), 22 GiB per node, CPU-only,
  `cpu-short`, 2-hour limit, no requeue.
- Existing native failure, nonfinite-value, PAUSE, wall-clock, disk and
  `max|U|=1000 m/s` protections remain active.
- First 20 steps are profiled from native logs/step accounting for pressure
  iteration counts and wall cost. Any incomplete or guarded result remains a
  preserved diagnostic outcome.

The prelaunch source capsule and member hashes are in
`source-capsule-index.json`; the exact inputs and failed-parent evidence are in
`gate-manifest.json`. The source capsule was verified on Komondor (22 member SHA-256 checks). Solver
job 14705632 and afterany audit 14705633 were both submitted HELD and read back
against the declared resources; the audit depends on `afterany:14705632`. The
audit was released first and the solver second at 2026-10-28 16:09 UTC. The
last readback showed the solver pending scheduler start and the audit pending on
the dependency. See `submission-record.json` and the saved Slurm readbacks for
the immutable launch receipt.
