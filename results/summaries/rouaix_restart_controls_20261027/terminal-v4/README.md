# Rouaix restart terminal evidence — 28 October 2026

Read-only collection from remote run root `/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-restart-controls-20261027`, captured 2026-10-28 11:22 UTC. No solver was launched. The collection contains short logs, CSV traces, run states, two audit bundles and scheduler accounting; it excludes full result archives and 3D fields.

## Terminal states

| Job | Slurm parent | Solver step | Recorded endpoint | Summary |
| --- | --- | --- | --- | --- |
| 14689395 smoke | COMPLETED `0:0`, 243 s | COMPLETED `0:0`, 39 s | 0.201 s, 10 steps | Maximum speed 111.975271939 m/s. Post-hoc audit reports 81/81 linear solves met configured criteria. Incremental ledger closure residual is −6.33214551×10⁻¹⁰ kg (maximum absolute per-step residual 1.27960537×10⁻¹⁰ kg). |
| 14689396 control | FAILED `1:0`, 2,147 s | CANCELLED `0:15`, 1,956 s | 658 speed rows through 0.2658 s; next printed `Time = 0.2659` did not complete | First recorded maximum above 1,000 m/s is 1,033.79161166 m/s at 0.2625 s. The run later develops extreme residuals and a rank-12 floating-point exception in `GAMGSolver::scale`; no `End` marker or terminal fields/ledger endpoint. |

For the control, maximum-speed progression is 120.280 m/s at 0.2511 s, 151.141 at 0.2542 s, 201.800 at 0.2568 s, 510.918 at 0.2610 s, 975.782 at 0.2624 s, and 1,033.792 at 0.2625 s. The threshold record reports a maximum at `(17.4441340782, −0.0561797752809, 3.52528089888) m`, processor 10. Its native `failureLocations` line labels the location `cell 83525`; that label does not establish whether the coordinate is a volume-cell center or boundary-face-associated. The last recorded speed sample is 22,532,440,324.1 m/s at 0.2658 s, with the reported location `(15.0977653631, −0.730460731862, 0.212705962741) m`, processor 10. The log then prints `Time = 0.2659`, reports alpha bounds far outside [0,1], and shows final U-solve residuals of 6,005,021 (Ux), 39,031.8 (Uy), and 12,843.5 (Uz), each at 100 iterations, before the rank-12 FPE. The post-hoc convergence audit counts 11 failed solve records (Ux 2, Uy 2, Uz 2, epsilon 3, k 2; p_rgh and pcorr 0). These are audit-parser results, not a convergence field in the control run-state.

## Comparison and limits

The prior original run 14650641 recorded its 1,045.533448471 m/s guard sample at 0.2625 s at `(17.44413407821, −0.05617977528090, 3.525280898876) m`, processor 10. The new control's first >1,000 m/s reported maximum matches that guard-point coordinate to printed precision. The old run's final 0.2628 s maximum was elsewhere, at `(17.44413407821, −0.05631406956444, 3.486170872067) m`; the new control's terminal recorded maximum is elsewhere again. This supports a recurring high-speed event near the downstream/top corner, not a proven common cell or cause.

Run-state records `stop_signals: ["12"]` and confirms the signal-12 runtime banner. It also records `stop_requested_utc` as 2026-10-28 09:52:08.783273 UTC. In `cases/e1_rouaix_hpc/run_pilot.py`, `stop_solver_step(...)` blocks on its wait before line 1211 writes that timestamp. Therefore this field is not the signal-send time; the preserved log does not establish whether the requested write-and-stop preceded the FPE or completed successfully. The control run-state reports a missing .2659 collated endpoint and the audit has no terminal ledger. Do not infer a successful checkpoint, bitwise restart, or identical numerical cause.

The after-any audit metadata for the failed control records `slurm_failed` / `captured`. Its embedded Slurm accounting attempt reports a connection-refused error. The fresh direct `sacct` read saved here succeeded and records all four jobs; see [sacct output](sacct-14689395-98.txt). Scheduler parent and `.0` solver-step wall/CPU values are separate accounting scopes; `AveRSS` in the raw readback is retained as supplied, not interpreted as aggregate node memory.

## Preserved evidence

- [Smoke run-state, solver log and speed trace](run-14689395/)
- [Control run-state, solver log and speed trace](run-14689396/)
- [Smoke audit bundle, hash sidecar, status and event](audit-14689395/)
- [Control audit bundle, hash sidecar, status and event](audit-14689396/)
- [Remote SHA-256 readback](remote-sha256.txt), [scheduler accounting](sacct-14689395-98.txt), and [local SHA-256 manifest](files.sha256)

The audit bundles' SHA-256 sidecars matched locally. Both outer tarballs and nested compact tarballs passed full member reads/CRC checks; each nested compact archive matched its audit JSON hash. The run-state log and CSV hashes matched for both trials, and the collected files matched the remote SHA-256 readback. The successful direct `sacct` read also preserves accounting that the asynchronous audit could not retrieve at capture time.

Collection commands used read-only SSH/rsync. Accounting: `ssh -S /tmp/fire-track2-komondor-%C -o BatchMode=yes nk_memj@komondor.hpc.kifu.hu 'sacct -j 14689395,14689396,14689397,14689398 --format=JobID,JobName%28,State,ExitCode,Elapsed,TotalCPU,MaxRSS,AveRSS,Start,End -P'`. Artifact copies used `rsync -av -e 'ssh -S /tmp/fire-track2-komondor-%C -o BatchMode=yes'` on the named solver log, `max-speed.csv`, run-state, and audit metadata paths. An assert-based Python check validated row counts, first threshold crossing, source/run-state hashes, sidecar hashes, nested archive hashes and CRCs, and post-hoc failed-solve count.
