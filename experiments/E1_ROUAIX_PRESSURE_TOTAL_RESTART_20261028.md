# Rouaix fine-grid p_rgh total-pressure restart sensitivity — 28 October 2026

Prepared exploratory CPU restart from the frozen 0.2 s water-injection checkpoint. This is a boundary-condition sensitivity run, not an E1 acceptance run or a paper correction. The run source, submission IDs, and outcome are recorded in results/summaries/rouaix_pressure_total_restart_20261028/.

## Question and declared change

Test whether the four open p_rgh outlet conditions contribute to the pressure-driven instability during a 120-rank continuation. Start from the immutable water-injection checkpoint at 0.2 s, produced by the original static-pressure case, and change only p_rgh on downstreamOutlet, bottomOutlet, spanwiseMinus, and spanwisePlus to OpenCFD v2512 prghTotalPressure:

- type prghTotalPressure
- p0 uniform 0
- rho rho
- U U
- phi phi
- value uniform 0

Here p0=0 Pa is gauge pressure. The treatment preserves zero static gauge pressure during outward flow and applies the reverse-flow dynamic-head term. This is a backflow-energy sensitivity, not a match to a measured total pressure or a paper boundary condition. Source review and v2512 implementation evidence are recorded in results/runs/rouaix-restart-controls-20261027/research/outlet-control-review.md.

The candidate comes from parent archive SHA-256 31010755e705010771de7ed00fb5fb9990e7d2621237c3d881ee22b826cf25c9 and parent ledger SHA-256 0baa380005d188edf6c94a0c175b790a5a8af5fa79773ff37ace5da5dda2f300. The parent water inventory at 0.2 s is 0.2508975771509 m3 at rho=997.6 kg/m3. Preserve all parent fields, mesh, decomposition, time state, and cumulative-continuity state.

## Evidence before release

The local coarse exploratory gates passed with unchanged deltaT=0.0001 s:

- The all-air total-pressure case reached 0.3000 s with End, exit 0, and no 200 m/s stop. Its peak speed was 85.0362 m/s and terminal speed 75.7689 m/s. The case retained zero water. Evidence: results/summaries/rouaix_backflow_local_20261028/air-result-summary.json.
- The water-nozzle total-pressure sibling reached 0.3000 s with End, exit 0, and no 200 m/s stop. Its peak and terminal speeds were 103.1456 and 100.2184 m/s. The endpoint water volume was 0.379166666663 m3; the signed mass-balance residual was -3.65e-10 kg. Evidence: results/summaries/rouaix_backflow_local_20261028/water-total-pressure-diagnostics.json.
- The matched static-pressure water control reached its declared 200 m/s guard at 0.1702 s and ended at 0.1703 s. Its trigger speed was 200.697 m/s and terminal speed was 210.058 m/s. Evidence: results/summaries/rouaix_backflow_local_20261028/water-static-control-diagnostics.json.
- The native early-save restart 14700599 stopped cleanly at 0.2005 s after five continuation steps, with native End, exit 0, no pause, endpoint fields, incremental ledger, and archived source. Its afterany audit 14700602 completed and captured the expected intentionally partial horizon. Evidence and archive hashes are in results/summaries/rouaix_early_save_20261028/v3/terminal/.
- The native v2512 collated changeDictionary utility passed on a private two-rank copy of the same 299,520-cell coarse mesh. It changed the four declared p_rgh patches, retained p0=0, rho/U/phi references, and zero value on each rank; the p_rgh internal-array digest, the other present fields U, alpha.water, epsilon, k, and nut, and the original static time-zero p_rgh input were unchanged. The .2 utility directory was explicitly copied from time zero to exercise the command path; it was an I/O fixture, not a physical .2 checkpoint. Evidence is in results/summaries/rouaix_pressure_total_restart_20261028/native-io/.
- A separate coarse deltaT=0.0003 s performance run completed the horizon faster, but it had roughly threefold higher bulk and interface Courant maxima. A matched field comparison found an L1 alpha-water difference of about 0.19 m3 and a water-centroid shift of 0.087 m. Those coarse results are retained as a diagnostic only; the fine continuation keeps the parent fixed deltaT=0.0001 s. The timestep and Courant records are in results/summaries/rouaix_backflow_local_20261028/water-dt0003-diagnostics.json; the field-comparison measurement is preserved in the launch manifest.

These exploratory gates establish readiness for this conditional continuation only. They do not establish that the total-pressure outlet is more physically accurate.

## Matched controls and outputs

- OpenCFD v2512 interIsoFoam, original limitedLinearV 1 momentum scheme, parent 120-rank decomposition and mesh, materials, gravity, fields, and all non-pressure boundaries unchanged.
- Fixed deltaT=0.0001 s from 0.2 to 0.3 s (1,000 continuation steps); writeInterval=0.05 s retains collated checkpoints at 0.25 and 0.30 s.
- 120 MPI ranks on three nodes, 40 ranks per node, 22 GiB/node; cpu-short, CPU-only, 90-minute Slurm limit, no requeue or GPU.
- Apply the generated dictionary with native parallel I/O using changeDictionary -parallel -fileHandler collated -case <private-case> -time 0.2 -dict system/changeDictionaryDict. The production runner first verifies the actual 120-rank donor arrays and all other checkpoint-field hashes. Any failed check prevents the solver from starting and preserves the attempt.
- The existing operational max|U|=1000 m/s guard is unchanged. No field clipping, timestep changes, or threshold changes are allowed. The native job records every-step extrema and locations, pressure and patch-flux diagnostics, solver convergence, water inventory, and the incremental mass ledger. Preserve raw residuals without inventing an acceptance threshold.

The primary observables are maximum speed and location, pressure and patch-flux traces, convergence, actual checkpoint times, endpoint fields, and whether the branch reaches 0.3 s. Interpretation remains conditional on this checkpoint and boundary intervention.

## Release and run record

The candidate was eligible after the five evidence gates above. The unique source capsule, Slurm submission and readbacks, afterany audit, and live outcome are recorded in results/summaries/rouaix_pressure_total_restart_20261028/. The run's status is separate from the predeclared inputs in this experiment record.
