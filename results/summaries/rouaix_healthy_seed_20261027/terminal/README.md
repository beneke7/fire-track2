# Healthy-seed terminal audit — 14669440

Captured UTC: 2026-10-27T14:20:35.546076+00:00

## Scope and provenance

The native after-any auditor classified this as `completed_horizon_converged_exploratory_only`. This is an exploratory run audit, not an E1 or field-validation decision. The parent Slurm job completed `0:0` after **1:55:13**, using 120 MPI ranks on one node with a 64 GiB request and a two-hour limit. The case reached 0.2 s in 2,000 steps at fixed `deltaT=0.0001 s`; solver exit was 0 and the log contains `End`.

The attempt archive SHA-256 is `31010755e705010771de7ed00fb5fb9990e7d2621237c3d881ee22b826cf25c9`. The compact audit bundle SHA-256 is `432d23763bdaf51ddeea2a609b6dfff7de94d98ef9be89b8690d581e2d21bd47`; its nested compact payload archive SHA-256 is `4b09132150a8a3a23ee2b25895291476984f7c77ea645b85247884511eac4074`. All 14 selected payloads (9,131,636 bytes) were extracted only after checking bundle, nested-archive, member path/type, size and per-file hashes. No full solver archive or 3D field payload was copied. Exact status, audit, selection, and scheduler receipts are alongside this note; the raw bundle, sidecar, downloaded status, scheduler receipt, and hash-verified selected files are under `results/runs/rouaix-healthy-seed-20261027/terminal/` (selected payloads in `terminal/selected/`).

The attempt manifest matches requested job `14669440`, case `HSEED-ORIG-120-01MS-020`, 120 ranks, 0.2 s horizon, and `deltaT=0.0001 s`. Audit verified 22 prepared-case files. Input mesh archive SHA-256: `8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787`; mesh contains 10,099,265 cells. The source record identifies OpenFOAM v2512 (`OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH`, DP, 32-bit labels) and installed-source hashes. Repository revision is recorded as unknown; binary reproducibility is not established.

## Diagnostics

- **Water inventory:** initial water inventory 0 kg; cumulative injected mass 250.328864060 kg; signed net escape 0.033442764 kg; final water inventory 0.250897577151 m³ (density 997.6 kg/m³). Maximum absolute cumulative closure residual was 1.67037885035e-06 kg; maximum per-step residual was 9.43282502719e-07 kg. The raw ledger uses right-rectangle integration of `alphaPhi_` over each completed interval, outward-positive patch signs, and one alpha subcycle. Its documented caveat is that later direct alpha snap/clipping can appear in the residual after conservative `limitFluxes`; this is a diagnostic, not a conservation gate.
- **Courant numbers:** bulk Co max 1.301609777, mean max 0.070408306; interface Co max 0.963842708. Configured `maxCo`/`maxAlphaCo` are both 5. These observed values are descriptive only.
- **Alpha extrema:** `alpha.water` over the log reached min -6.34966712456e-11 and max 1; final extrema were -1.62630325873e-19 to 1. The separate raw `alpha` minimum reached -0.000404728706102; no fitted acceptance threshold is applied.
- **Turbulence and speed:** the captured solver log reports global-in-time spatial extrema across 2,000 records of `k` min 0.00622922212033, max 1631.98145517; `epsilon` min 0.0106143748097, max 498332.185409; `nut` min 0, max 3.66368792275. These are raw model-field extrema without a physical threshold or interpretation. Dedicated native profiling was disabled; the auditor's current TKE-extrema parser reports “not exposed.” The raw `max|U|` peak was 116.926518384 m/s (last 111.720159608 m/s).
- **Linear solves:** the parser found 16001 records, all converged under the case's residual/relative-residual criteria; no failed record was found. Counts: Ux/Uy/Uz/k/epsilon 2,000 each, `p_rgh` 6,000, `pcorr` 1. The maximum final `p_rgh` residual was 0.000290661812029. This is solver telemetry, not validation.
- **Checkpoint:** the verified full-archive member inventory lists initial `t=0` and terminal `t=0.2` collated fields including U, alpha.water, k, epsilon and p_rgh; see `checkpoint-presence.json`. The archive member list was used for field-presence confirmation; full fields were not reread. No restart branch is evaluated here.

## Performance and gaps

Solver wall time was 6703.880 s; OpenFOAM ClockTime was 6697 s. Timing covers solver clock and launcher wall time only, not a full I/O breakdown. Profiling is disabled. The auditor's compute-node `sacct` request failed because that node's localhost accounting connection refused; a separate login-node `TZ=UTC sacct` readback is preserved in `login-TZ-UTC-sacct.txt` and records parent TotalCPU `9-05:50:09` and solver-step TotalCPU `9-05:45:11`. Memory is not aggregated: the login readback has no parent MaxRSS; the batch and solver-step rows report 9,449,176K and 1,425,472K respectively. These per-step values are not summed or presented as total-job memory.

The current audit exposes no formal ledger decision, no TKE interpretation, and no native profiling interpretation. The run is a completed, converged **0.2 s exploratory healthy-seed candidate**; mesh qualification exception, model assumptions, and short horizon still limit its scientific scope.
