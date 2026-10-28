# Fine Rouaix pressure-correction PCG/DIC sensitivity — 28 October 2026

This is a CPU-only exploratory continuation of the immutable water-injection
checkpoint at 0.2 s. It repeats the four-patch `prghTotalPressure`, `p0=0`
case used by job 14702499 and changes the `p_rgh` linear solver policy to test
the pressure-corrector divergence seen there. It is not an E1 acceptance run,
paper boundary-condition correction, or physical validation.

## Question and declared numerical change

In job 14702499, at the completed 0.2495 s solve, the first `p_rgh` correction
converged to a 0.00331 residual in two iterations, while the following two
corrections ended at 3.45e19 and 8.65e22 after 100 iterations. The attempted
0.2496 s step then hit SIGFPE in the vector `U` PBiCGStab solve. The maximum
bulk Courant number before the failed iteration was about 1.222. This sequence
does not establish whether the outlet treatment caused the instability.

Keep the original 0.2 s donor, its fields, mesh, decomposition, physics,
`deltaT`, pressure-total boundary treatment, and all solver settings except
the `p_rgh` solver entry. Change:

- `p_rgh`: GAMG with `DICGaussSeidel`, `maxIter 100` → PCG with DIC,
  `maxIter 1000`.
- Keep `tolerance 1e-8` and `relTol 0.01` for `p_rgh`.
- Keep `p_rghFinal` inheriting `p_rgh` and its existing `relTol 0`; it therefore
  uses the same PCG/DIC solver and the same absolute tolerance.
- Keep the four open `p_rgh` patches on `prghTotalPressure`, `p0 uniform 0`,
  `rho rho`, `U U`, `phi phi`, `value uniform 0`.

The increased iteration cap is part of this solver-policy sensitivity. Report
whether any pressure corrector needed more than 100 iterations and whether any
hit the 1000-iteration cap; do not attribute a change to PCG alone if the cap
was material. Retain raw residuals and iteration counts without introducing a
new acceptance threshold.

## Horizon, writes, and resources

- Start at 0.2000 s and target 0.2550 s with fixed `deltaT=0.0001 s` (550
  continuation steps). This crosses the previous 0.2495–0.2496 failure window.
- Write collated fields every 0.005 s and set `purgeWrite 2`, retaining the two
  most recent field checkpoints. This is an I/O retention change intended to
  preserve a recent restart state if pressure divergence recurs.
- OpenCFD v2512 `interIsoFoam`; 120 MPI ranks on 3 nodes, 40 ranks per node,
  22 GiB/node, `cpu-short`, CPU-only, 2-hour Slurm limit, no requeue.
- Preserve the existing `max|U|=1000 m/s` stop guard. Do not clip fields or
  change time step, boundary physics, mesh, or turbulence model.
- Capture per-step `U`, `p_rgh`, `k`, `epsilon`, `nut`, alpha, Courant,
  continuity and linear-solver diagnostics. Profile the first 20 steps from
  the solver log and step-accounting data, including pressure-solve iteration
  counts and wall cost.

The main observables are pressure-corrector residual/iteration histories,
whether the run crosses 0.2495 s and reaches 0.255 s, peak `U` and location,
Courant numbers, alpha bounds, pressure/RANS extrema, checkpoint times, and
the incremental native water ledger if a clean endpoint is reached. A guarded
or numerically failed run remains a preserved diagnostic outcome and is not
counted as reaching the requested horizon.

## Inputs and provenance

Use the frozen original water-injection parent archive and ledger recorded in
`results/summaries/rouaix_pressure_total_restart_20261028/gate-manifest.json`.
The parent is the 120-rank 0.2 s water-injection checkpoint; its 0.2 s water
inventory is 0.2508975771509 m3 at rho=997.6 kg/m3. Never modify the parent
archive or overwrite job 14702499. The new run has a unique source capsule and
run root under `results/summaries/rouaix_pressure_pcgdic_20261028/` and
`/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-pressure-pcgdic-restart-20261028/`.

Use the native convergence inspector against the modified `fvSolution`, and
preserve the solver log, run-state, source hashes, afterany audit, archive
hash/member receipt, and any failed preparation attempt. The result remains a
numerical-solver sensitivity for this frozen donor and conditional outlet
setting; it cannot establish hardware fidelity or field validation.
