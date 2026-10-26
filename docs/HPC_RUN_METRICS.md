# Rouaix HPC measurement contract

Compact published measurements, hashes and preview: [26 October evidence bundle](../results/summaries/rouaix_hpc_20261026/README.md).
Raw fields and archives referenced below remain outside Git.

Use this record with the prepared exploratory Rouaix Case 1 jobs in
[`E1_ROUAIX_HPC_PILOT.md`](../experiments/E1_ROUAIX_HPC_PILOT.md). It is an
operational measurement record, not an E1 gate or a CFD validation result. Keep
each attempt, including failures, under its Slurm job ID. Do not alter the mesh,
physics, solver dictionaries, or `deltaT` to improve a timing result.

## Measurement rules

- **Input window:** read `fixed_delta_t`, `delta_t_s`, `horizon_s`, and
  `field_write_times_s` from each preserved `manifest.json`; cross-check the
  hash-bound `case-inputs.json`, `system/controlDict`, and `run-state.json`.
  Do not carry a timestep or horizon from one run into another. The parser
  reports the interval between the first and last printed `Time` samples. A
  log beginning at `Time=deltaT` therefore spans `horizon-deltaT` between
  printed samples, even when every requested step completed. Record requested
  horizon, printed first/last times, and step count separately.
- **Per-step rate:** the parser reports physical seconds and steps per logged
  `ClockTime` second for each interval between consecutive `Time` samples.
  The first sample has no preceding interval. When printed `ClockTime` values
  repeat, the per-step rate is `null`; a zero delta is output quantization, not
  zero cost. Preserve the printed precision and observed clock increments with
  the report. Use high-resolution `solver_wall_s` for the end-to-end solver
  envelope and keep OpenFOAM `ClockTime` separate.
- **Pressure:** `pressure_solve_iterations` is the sum of the logged `No
  Iterations` values for `p` and `p_rgh`, attached to the corresponding log
  step. It is a count, never a time measurement. Keep per-field residuals and
  counts. Pressure seconds require the native profiler evidence described
  below.
- **CPU and cost:** `AllocCPUS * Elapsed / 3600` is allocated core-hours for
  the entire Slurm job. Parent-row `TotalCPU / 3600` is CPU time charged to the
  job; dividing it by allocated CPU-seconds gives a whole-job busy fraction
  that includes preparation and finalization. Keep this separate from
  solver-child `TotalCPU` and the estimate `solver_wall_s * MPI ranks / 3600`.
  The latter is allocated solver-envelope core-hours, not measured CPU
  consumption. Preserve parent, `.batch`, `.extern`, and solver-step rows;
  these rows are hierarchical and their CPU totals must not be added.
  `CPUTimeRAW` is allocated CPU-seconds, not busy CPU time.
- **Memory and placement:** record the requested `--nodes`, `--ntasks`,
  `--cpus-per-task`, memory request, `srun` binding, and file-handler settings
  next to the actual node list and tasks-per-node from Slurm. Record the exact
  accounting row for every RSS value. A `.batch` RSS is preparation/launcher
  memory; it is not solver memory. A solver-step `MaxRSS` is the Slurm
  per-task maximum, not total node RSS. An allocation limit is not an observed
  peak, and terminal `MaxRSS` is not a periodic trace.
- **Timing boundaries:** queue wait is `sacct Start - Submit` when both
  timestamps were captured; otherwise mark it missing. Runner startup is
  `run-state.started_utc` to `solver_started_utc`; `solver_wall_s` spans
  the runner's monotonic start of `srun` through reaping it. The first logged
  `ClockTime` includes OpenFOAM initialization and its first advance, so it is
  only a coarse startup-plus-first-step observation. Full-field writes are
  scheduled at that run's manifest `field_write_times_s`; scheduled times are
  not write durations. Do not infer checkpoint time from `solver_wall_s` minus
  a rounded `ClockTime`.
- **Bytes and I/O:** report final field/checkpoint bytes separately from the
  tar archive size. The stock v2512 profiler does not time the actual field
  writes in this solver path. Until external timing is added, set measured
  checkpoint-write seconds to `null` and report archived output bytes and
  scheduled write times separately.
- **Reproducibility:** preserve source revision/dirty state, solver banner and
  installed-source evidence, module list, executable/library versions, input
  archive SHA-256, mesh-file hashes, prepared-case hashes, Slurm submission and
  terminal accounting, solver log, runner state, and result-archive SHA-256.
  Keep metrics offline JSON; the W&B destination has not been specified.

## Fixed input versus printed timestep evidence

These Rouaix fixed-step runs use `adjustTimeStep no`; each run's hash-frozen
`system/controlDict` and matching `case-inputs.json` metadata prescribe its
own `deltaT` (the first three measured cases use 0.001, 0.0001, and 0.0005 s).
OpenFOAM v2512 does not print a native `deltaT = ...` line for each fixed step.
A `Time = ...` row is the solver's printed clock value; the controlDict token
is the prescribed interval source, not a measured timestep. Use the manifest
for each run's requested horizon and scheduled writes.

The ledger audit may label a row `fixed-controlDict` only when both input files
are hash-bound, `adjustTimeStep no`, `runTimeModifiable false`, clean
`startFrom startTime` at zero, fixed physical-time writes, and the stock
diagnostic function objects are verified. Case metadata must agree with the
exact positive controlDict token. It then checks every positive `Time` record,
including an unmatched final step announcement, against `n * deltaT`. The
fixed input token has zero decimal-print rounding uncertainty; the time check
allows the printed `Time` half-unit plus a small IEEE accumulation bound.
Skipped or mismatched times are rejected. The raw solver log and its byte hash
remain untouched; no `deltaT` rows are inserted. CSV `interval_deltaT_s` carries
the prescribed interval, while `native_deltaT_s` is blank for this mode.

When the solver prints paired `deltaT` and `Time` rows, the audit keeps the
`native-paired` mode and its existing accumulated native-token rounding bound.
Adaptive timestep results require those native pairs. Never describe either
mode's iteration count as pressure-solve time.

## Reusable post-run command

Run this for an attempt that reached solver launch, on the local checkout after
the verified result archive and `run-state.json` are present. Set `RUN_DIR` to
that attempt's local preserved-output directory. For a bootstrap failure with
no `solver.log`, skip log parsing and record its solver metrics as missing. The
new `metrics/` directory makes these commands fail instead of overwriting an
earlier analysis.

```sh
run_dir="${RUN_DIR:?set RUN_DIR to the local preserved attempt directory}"
job_id="${JOB_ID:?set JOB_ID to the Slurm job ID}"
run_label="${RUN_LABEL:?set RUN_LABEL to a short attempt label}"
ranks="${MPI_RANKS:?set MPI_RANKS to the allocated MPI rank count}"
mkdir "$run_dir/metrics"
tar -xzf "$run_dir/result.tar.gz" -C "$run_dir/metrics" \
  attempt/solver.log attempt/manifest.json attempt/native-source-evidence.json \
  attempt/case/case-inputs.json attempt/case/system/controlDict
sacct --parsable2 -j "$job_id" \
  --format=JobID,JobName,Elapsed,TotalCPU,CPUTimeRAW,AllocCPUS,MaxRSS,AveRSS,State,ExitCode,NodeList,Submit,Start,End \
  > "$run_dir/metrics/sacct.sacct"
.venv/bin/python scripts/hpc_metrics.py \
  --run "$run_label=$run_dir/metrics/attempt/solver.log" \
  --ranks "$run_label=$ranks" \
  --launcher "$run_label=$run_dir/run-state.json" \
  --sacct "$run_label=$run_dir/metrics/sacct.sacct" \
  --output "$run_dir/metrics/hpc-metrics.json"
```

The parser emits scalar and per-step solver-log metrics plus parent-job Slurm
accounting. It does not read the case manifest: preserve the prescribed
`deltaT`, requested horizon, and write schedule alongside its parsed output.
For fixed-time cases, the helper's log-derived `delta_t_s` is empty when no
native `deltaT` records exist; do not fill those log rows synthetically.
`solver_wall_s` and `solver_exit_code` are read directly from the runner JSON;
if absent, they remain `null`. Retain raw Slurm parent, batch, extern, and
solver-child rows for separate CPU and RSS accounting. The parser intentionally
does not promote child-step RSS to whole-job RSS or `CPUTimeRAW` to measured
CPU. On bootstrap failure, a missing solver log is recorded as missing rather
than fabricating an empty successful run; capture terminal accounting and
report the bootstrap outcome directly.

## Per-experiment record

Create one JSON record for each job ID. Use `null` and a reason when a quantity
was not collected. Store source file paths beside every derived value.

```json
{
  "schema_version": 1,
  "attempt_id": "rouaix-e1-hpc-pilot-<job-id>",
  "status": "completed | failed | incomplete",
  "purpose": "why this measurement is needed",
  "hypothesis": "expected runtime or resource bottleneck",
  "changed_factors": [],
  "constants": {
    "case_id": null,
    "numerical_variant": null,
    "solver": "interIsoFoam / OpenCFD v2512",
    "mesh_cells": 10099265,
    "start_time_s": 0.0,
    "end_time_s_from_manifest": null,
    "delta_t_s_from_manifest": null,
    "fixed_steps_from_manifest": null,
    "field_write_times_s_from_manifest": [],
    "mpi_ranks": null,
    "alpha_subcycles": null
  },
  "identity": {
    "revision": null,
    "dirty": null,
    "input_archive_sha256": null,
    "mesh_file_sha256": {},
    "prepared_case_sha256": {},
    "solver_executable_sha256": null,
    "modules": null,
    "libraries": null
  },
  "placement": {
    "requested": {"nodes": null, "tasks": null, "cpus_per_task": null, "memory": null, "cpu_bind": null, "mem_bind": null, "file_handler": null},
    "actual": {"node_list": null, "tasks_per_node": null}
  },
  "measurement_window": {
    "first_printed_time_s": null,
    "last_printed_time_s": null,
    "requested_horizon_s": null,
    "logged_steps": null,
    "native_delta_t_log_rows": null,
    "clock_time_print_resolution_s": null,
    "minimum_positive_observed_clock_increment_s": null,
    "first_to_last_printed_time_interval_s": null
  },
  "timing_s": {
    "submit_to_start_queue_wait": null,
    "runner_start_to_solver_launch": null,
    "solver_wall_srun_envelope": null,
    "first_logged_clock_time_includes_startup_and_first_step": null,
    "last_logged_clock_time": null,
    "checkpoint_write": null,
    "archive_pack_and_finalize": null
  },
  "cpu": {
    "allocated_cpu_hours_job": null,
    "measured_total_cpu_hours_job": null,
    "measured_solver_child_cpu_hours": null,
    "whole_job_busy_fraction": null,
    "solver_child_busy_fraction_over_srun_envelope": null,
    "solver_wall_times_ranks_core_hours_estimate": null,
    "raw_accounting_rows_parent_batch_extern_solver_child": []
  },
  "memory": {
    "allocation_limit_bytes": null,
    "max_rss_by_slurm_row": {},
    "runner_periodic_rss_available": false
  },
  "solver_metrics": {
    "prescribed_delta_t_s_from_manifest": null,
    "physical_seconds_per_clock_second_per_step": [],
    "pressure_solve_iterations_count_per_step": [],
    "pressure_time_per_rank_s": null,
    "courant": null,
    "alpha_extrema": null,
    "velocity_max_m_s": null,
    "mass_ledger": null
  },
  "io": {
    "scheduled_field_writes_s_from_manifest": [],
    "checkpoint_bytes": null,
    "result_archive_bytes": null,
    "measured_full_field_write_seconds": null,
    "profile_scope_coverage": null
  },
  "sources": {
    "run_state": null,
    "manifest": null,
    "solver_log": null,
    "terminal_sacct": null,
    "native_profile_summary": null,
    "archive_sha256": null
  },
  "assumptions_and_missing": []
}
```

For a scaling or timestep comparison, list every changed factor and keep all
other constants/hash-bound inputs visible. A failed, resource-stopped, or
partial attempt remains in this ledger and is not replaced by a retry.

## Offline measurements: N1–N3

The compact, hash-bound per-step data are in
[`n1-n3-offline-summary.json`](../results/runs/rouaix-hpc-metrics-20261025/n1-n3-offline-summary.json).
They were parsed locally from the preserved solver logs with
[`hpc_metrics.py`](../scripts/hpc_metrics.py); no large result archive was
extracted for this summary. All three runs used 64 ranks on one node and the
same 10,099,265-cell input mesh and 0.01 s requested horizon. Their timestep
and, for N1, scheme differ, so these timings do not form a controlled
timestep/scheme comparison.

| Run | Scheme / prescribed Δt | Logged steps | First–last printed Time interval | Solver srun wall | OpenFOAM ClockTime | p_rgh iterations (count) | max Co | U max (m/s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| N1 / 14647712 | upwind / 0.001 s | 10 | 0.009 s | 113.09 s | 109 s | 250 | 8.44 | 86.24 |
| N2 / 14647714 | original / 0.0001 s | 100 | 0.0099 s | 708.68 s | 705 s | 1,855 | 0.957 | 91.24 |
| N3 / 14647739 | original / 0.0005 s | 20 | 0.0095 s | 200.94 s | 197 s | 413 | 4.90 | 104.14 |

`Time` covers the configured horizon in every row; the printed first-to-last
interval is shorter by one completed timestep. Native logs contain no `deltaT`
rows, so the prescribed timestep comes from the hash-bound controlDict and
manifest. The values labelled “p_rgh iterations” and the per-step pressure
entries in the JSON are iteration counts only. ClockTime prints whole seconds;
the interval throughput ratios are coarse.

Runner start-to-solver launch was 88.215 s (N1), 74.152 s (N2), and 81.723 s
(N3). The terminal readbacks did not retain the Slurm `Submit` timestamp, so
queue wait is `null` for these attempts; archive-pack/finalization duration is
also unknown.

The solver child exited successfully for all three runs. N1 and N2 retain their
original Slurm parent state `FAILED` because the original ledger command exited
2 when its parser required printed `deltaT` lines. New local supplementary
audits using the fixed-controlDict source returned 0 and covered all 10 and
100 steps respectively. N3's original ledger command exited 0 and covered all
20 steps. Each ledger remains an exploratory accounting result, not an E1
validation decision. N1–N3 archived solver outputs preserve these outcomes;
the raw run-state and accounting files remain unmodified.

The terminal solver-child CPU and memory observations are:

| Run | Job elapsed / parent CPU | Solver-child elapsed / CPU | Solver-child CPU / (run-state `solver_wall_s` × 64) | `.batch` MaxRSS | Solver-child MaxRSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| N1 | 288 s / 7,194 s | 113 s / 7,022 s | 97.0% | 9,498,164K | 1,499,552K |
| N2 | 880 s / 45,029 s | 709 s / 44,855 s | 98.9% | 9,138,160K | 1,561,684K |
| N3 | 379 s / 12,759 s | 201 s / 12,584 s | 97.9% | 9,135,668K | 1,519,284K |

The CPU fractions in this table use the solver-child `TotalCPU` divided by the
high-resolution run-state `solver_wall_s × 64`; they estimate busy time within
the measured solver envelope. They do not use the rounded Slurm child `Elapsed`
value shown beside them. The parent-row whole-job CPU fractions are lower because the job
includes setup, audit, and finalization. `.batch` memory reflects launcher and
preparation; solver-child `MaxRSS` is a per-task Slurm maximum. There are no
periodic memory samples. Pressure wall time and full-field write duration were
not measured; archive size is not checkpoint size.

Verified result archives were 1,596,306,804 bytes (N1), 1,603,772,295 bytes
(N2), and 1,597,487,335 bytes (N3). Those archives include retained case,
decomposed data, diagnostics, logs, and metadata; checkpoint bytes and actual
write time remain `null` in the JSON. All three runs scheduled field writes at
0 and 0.01 s according to their manifests.

## First HPC attempt: job 14647683

**Outcome:** failed before `decomposePar` and before `interIsoFoam`; zero CFD
steps and no `solver.log`. This is a bootstrap resource measurement only.

| Item | Recorded value |
| --- | --- |
| Purpose | Verify the immutable mesh import, native source checks, and 64-rank startup path before using the fixed-step pilot as a runtime baseline. |
| Intended case | Rouaix Case 1, 10,099,265-cell cast-only mesh; 64 ranks on one node; `deltaT=0.001 s`; 50 steps to `0.05 s`; v2512 `interIsoFoam`, isoAdvector. |
| Actual placement | Node `x1000c7s2b1n1`; 64 tasks, 1 CPU/task, 64 GiB requested; `FOAM_FILEHANDLER=collated`, `FOAM_IORANKS=(0)`. |
| Failure | `PilotError: installed native write-and-stop source is missing` while checking the site source path. Case preparation and `setExprFields` completed; the runner stopped before decomposition/solver launch. |
| Slurm job | `FAILED`, exit `1:0`, elapsed 57 s, 64 allocated CPUs, `TotalCPU=53.356 s`; allocated 1.013333 core-hours and measured job CPU 0.014821 core-hours (about 1.46% busy). |
| RSS | Parent `MaxRSS` is blank. `.batch MaxRSS=6582488K` (about 6.28 GiB) is bootstrap memory, not a solver peak. The attempted `sstat` readback reports an invalid requested field and is missing. |
| Throughput / pressure / checkpoint | Not measured: no solver step, pressure solve, CFD field write, or solver timing exists. `CPUTimeRAW=3648` is 64 CPUs × 57 s of allocation, not busy CPU. |
| Archive | 51 members, 350,371,917 bytes; CRC, hash, and exact member list verified. This size includes the mesh and preparation evidence, not a CFD checkpoint. |
| Raw evidence | [`run-state.json`](../results/runs/rouaix-native-mesh-qa-20261025/outputs/failed-14647683/run-state.json), [`allocation.txt`](../results/runs/rouaix-native-mesh-qa-20261025/outputs/failed-14647683/allocation.txt), [`terminal accounting readback`](../results/runs/rouaix-native-mesh-qa-20261025/launch/pilot-20261025T2008Z-64r-1ms/job-14647683-terminal-accounting-readback.txt), [`archive verification`](../results/runs/rouaix-native-mesh-qa-20261025/outputs/failed-14647683/archive-verification.json). |

The retry must use a new job ID and preserve this failed attempt unchanged. The
startup experiment itself remains exploratory: the transferred mesh has zero
added wall layers while the paper reports five, and this pilot uses isoAdvector
with the current case schemes rather than the paper's HRIC numerics. The mesh
was admitted under the exact-coplanar flagged-cell exception for exploratory
import only. No CFD result or E1 comparison follows from job 14647683.

## Native v2512 profiling evidence and proposed pair

Read-only SSH used the supplied multiplexed connection, loaded
`openfoam` and `OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH`, sourced `$FOAM_BASH`, and
queried installed source/help. The runtime banner was OpenCFD OpenFOAM v2512,
build `_87ed40d256-20251219`; `interIsoFoam -help-full` showed no `-profiling`
option. The installed profiler is enabled from `system/controlDict` without a
solver patch:

```foam
profiling
{
    active  true;
    cpuInfo false;
    memInfo false;
    sysInfo false;
}
```

`Time::setMonitoring()` constructs `uniform/profiling` as a registered
`AUTO_WRITE` object. Verify the retained rank coverage in each actual output:
P0 job 14652548 retained one collated-path object labeled `caseprocessor0`,
so only rank-zero timings are established by that archive.
`profilingSummary -latestTime`
reads processor-local profile entries and writes max/average/min values under
`postProcessing/profiling/<time>/profiling`. With the pilot's
`FOAM_FILEHANDLER=collated`, processor output appears under `processors<N>/`.
In the completed P0 archive the profiling object is an ordinary `dictionary`
under that path, with rank-zero content only. The generated `controlDict` sets
`maxThreadFileBufferSize 0`, so the collated writer uses the unthreaded,
synchronous path. The observed P0 output is one profiling file at the final
write time. A collated pathname alone does not prove all-rank content; the
completed P0 archive contains no max/average/min summary.

The `lduMatrix::solver.<field>` scope measures wall-clock time and calls for
each pressure linear solver on each rank; `profilingSummary` retains the
maximum, average, and minimum rank values (or a single value if ranks match).
Use the maximum as the slowest-rank wall-time evidence and preserve the average
and minimum. Compare `totalTime` (inclusive) and `childTime` (nested work)
without summing scopes. `cpuInfo` is not a per-scope CPU timer, so per-rank
busy CPU must still come from Slurm accounting.

**I/O limit:** the scope named `objectRegistry::writeObject` is placed in
`Time::writeTimeDict()` and times only the small `uniform/time` dictionary
write. `Time::writeObject()` then calls `objectRegistry::writeObject()` to
write fields outside that scope. Therefore this built-in profile cannot
measure full checkpoint/field-write duration or total I/O share without
additional instrumentation. A paired unprofiled/profiled run can measure
profiler overhead and pressure timing only; it cannot fill that I/O field.
Create a fresh hash-bound case with only this dictionary added, matching the
selected baseline's exact manifest values for mesh, numerical settings,
`deltaT`, horizon, field-write schedule, rank count, and resource request.
Record the actual node for both jobs. Compare `solver_wall_s` and whole-job
Slurm metrics, and report `(profiled_wall / baseline_wall) - 1` as observed
profiler overhead. Do not use a profile timing result as a longer-run accuracy
decision.

The exact remote source paths and SHA-256 values are preserved in
[`native-profile-inspection.json`](../results/runs/rouaix-hpc-metrics-20261025/native-profile-inspection.json).
No profiling trial was launched during that source inspection. The subsequent
[P0 profiling trial](../results/summaries/rouaix_p0_profile_20261026/README.md)
completed 100 fixed 0.1 ms steps through 0.01 s. Its rank-zero pressure scope
was 850.222 s/300 calls. Solver wall was 2221.959 s versus baseline 2191.417 s
on another node; the +1.394% difference does not isolate profiler overhead.

### Compute-node accounting limitation

Native audit smoke 14654156 failed in two seconds because compute-node
`sacct` could not reach configured `localhost:6819`; login-node accounting
worked. The repaired auditor uses retained `scontrol` state when available,
or preserves hash-verified solver/ledger diagnostics with scheduler state
`UNKNOWN` and CPU accounting unavailable. It does not infer zero CPU. Fetch
actual parent/step CPU and RSS through the login node separately.
[Repaired native smoke](../results/summaries/rouaix_audit_repair_20261026/README.md)
14656128 passed in 36 s with 156136 KiB batch MaxRSS and 34.733 CPU-seconds.

## Matched rank measurements: 64–300 ranks

These four completed exploratory jobs measured whether the qualified 10,099,265-cell
Rouaix mesh could advance a 50 ms fixed-step window fast enough to justify
longer work. The working hypothesis was that more MPI ranks would reduce the
solver wall time. All runs used `interIsoFoam` v2512, the `original` scheme,
`deltaT=0.0005 s`, 100 steps, a 0.05 s requested horizon, the same mesh input
archive (`8da7141c…a12787`), executable, `controlDict`, `fvSchemes`,
`fvSolution`, and physical field inputs. Each run's 22 prepared input hashes
were verified by its ledger audit. The run-specific `case-inputs.json`,
`system/decomposeParDict`, and generated `setExprFields.log` hashes differ;
the case metadata and decomposition follow the requested rank/node count.

The rank count and actual node allocation changed together. The jobs ran
sequentially at different times, so queue delay and placement are measured
context, not controlled solver factors. The common comparison window is the
79 printed samples from `Time=0.010` through `0.049 s`, or 78 intervals over
0.039 physical seconds. It excludes initialization and the final endpoint.
OpenFOAM `ClockTime` prints whole seconds; the matched-window intervals and
per-step clock rates are therefore coarse. The high-resolution solver wall is
the runner's `solver_wall_s` around `srun`.

| Job / ranks | Actual placement | Queue wait | Solver `srun` wall | `.010–.049` ClockTime | Wall speedup vs 64 |
| --- | --- | ---: | ---: | ---: | ---: |
| 14647793 / 64 | 1 node, `x1000c2s3b1n0` | 52 s | 896.207 s | 672 s | 1.000× |
| 14647876 / 120 | 1 node, `x1000c6s4b0n0` | 5,152 s | 414.264 s | 310 s | 2.163× |
| 14648039 / 240 | 2 nodes, `x1000c5s2b0n1,x1000c5s4b0n1` | 12,073 s | 181.415 s | 130 s | 4.940× |
| 14648312 / 300 | 3 nodes, `x1000c5s2b0n1,x1000c5s4b0n1,x1000c5s5b0n1` | 5,164 s | 142.220 s | 99 s | 6.302× |

The measured 300-rank run was fastest. From 240 to 300 ranks, solver wall fell
21.6% for 25% more ranks, while allocated job core-hours rose from 22.267 to
26.000. Relative to the 64-rank baseline, the wall-time ratios imply apparent
parallel efficiencies of 115%, 132%, and 134% at 120, 240, and 300 ranks.
These are short-run measured ratios, not a scaling law. Rank count, node count,
placement, and partitioning changed together; the cause of the greater-than-
linear ratios is not isolated.

The per-step diagnostics also show an unresolved rank-dependent observable.
The global maximum `|U|` reached 555.110 m/s at 64 ranks, 261.546 m/s at 120,
904.736 m/s at 240, and 412.477 m/s at 300. The 240-rank peak occurred at
`t=0.038 s` near `(0.0489, -0.288, -0.317) m`; the other peak locations and
processor IDs are in the per-step report. These are global field maxima, not
rank averages. Inspect the late-time field and peak locations before treating
the timing ratios as representative of a longer run.

Over the matched window, maximum bulk Courant numbers were 16.42, 6.51, 23.85,
and 9.36 for 64, 120, 240, and 300 ranks; maximum interface Courant numbers
were 7.14, 4.37, 9.13, and 4.48. Mean bulk Courant was about 0.34435 in each
run. The solver's `Phase-1 volume fraction` line reported `Min(alpha.water)`
down to roughly `−5.4e−6`, with a maximum of 1. The separate `fieldMinMax
alphaExtrema` record stayed near 0–1, while the intermediate `isoAdvection`
`min(alpha)` record reached about −0.31 to −0.45. These are different solver
stages and remain separate in the per-step JSON.

The summed `No Iterations` counts for `p` and `p_rgh` over the matched window
were 1,472, 1,452, 1,450, and 1,470. All four convergence summaries recorded
801 solver records with no failed record. Iterations are counts only: no
pressure seconds or pressure share was measured because profiling was not
enabled. Ledger audits covered all 100 steps; final closure residuals were
0.02144, 0.01636, 0.01760, and 0.01731 kg, respectively (0.0343%, 0.0261%,
0.0281%, and 0.0277% of injected mass). These exploratory ledgers are not an
E1 conservation gate.

| Ranks | Allocated job core-hours | Parent CPU hours / busy fraction | Solver-child CPU hours / busy fraction | `.batch` MaxRSS | Solver-child MaxRSS per task |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 17.529 | 15.790 / 90.1% | 15.764 / 98.9% | 9,205,028 K | 1,585,032 K |
| 120 | 17.633 | 13.590 / 77.1% | 13.558 / 98.2% | 9,456,904 K | 1,374,040 K |
| 240 | 22.267 | 11.566 / 51.9% | 11.523 / 95.3% | 9,463,220 K | 1,378,508 K |
| 300 | 26.000 | 11.217 / 43.1% | 11.171 / 94.3% | 9,433,712 K | 1,338,948 K |

Whole-job allocated core-hours use parent `AllocCPUS × Elapsed`; parent CPU
hours include setup and finalization. Solver-child busy fraction divides its
`TotalCPU` by `MPI ranks × high-resolution solver wall`. `.batch` memory is
launcher/preparation RSS; solver-child `MaxRSS` is Slurm's maximum for one
task, not aggregate node memory. No periodic RSS trace was collected. Jobs
requested 64 GiB per node (64, 64, 128, and 192 GiB total). Runner-to-solver
launch gaps were 81.6, 106.2, 142.6, and 160.6 s; queue waits varied from 52 s
to 12,073 s. Do not include either in the `srun` solver wall ratio.

Full-field writes were scheduled at 0 and 0.05 s, but neither write duration
nor retained full-field checkpoint bytes are available from these archives.
The compressed result archives are compact evidence bundles, not checkpoint
sizes. Finalization/archive-pack time is not isolated. The parser used only
the parent SACCT row for its scalar summary; the verified capture retains the
parent, `.batch`, `.extern`, solver-step, and selector rows separately, and the
summary joins those rows without adding hierarchical CPU totals.

The declared forecast for 0.5 s exceeded the remaining wall cutoff, so no 0.5
or 5 s continuation ran. The 50 ms measurements do not establish a stabilized
plume runtime or E1 result. The run-state source revision is `unknown`; the
solver binary, modules, mesh, case files, ledger, logs, and archives remain
hash-bound. The imported mesh still uses its exact-concave-set exploratory
exception and has zero added wall layers, compared with five reported in the
paper.

The compact, hash-bound measurements and all 100 per-step rows per run are in
[`matched-rank-scaling.json`](../results/runs/rouaix-hpc-morning-20261026/analysis/matched-rank-scaling.json).
The capture manifest SHA-256 is
`d940c6abd6721e0817234c4e2b1e021446be346bb321ff15101c69371aa85050`; the
archive verification receipt SHA-256 is
`7309dc4c9275d6d7690e83b03ec3fb34070421c61591d24502f2e751254d5ad4`.


## Velocity-spike interpretation and primary documentation, 26 October

Treat the observed high speeds as unexplained, physically suspect local extrema,
not proof of a particular surface-tension defect. High interface Courant numbers,
large intermediate alpha excursions, pressure/density coupling, mass–momentum
transport and curvature/force balance are diagnostic candidates. The mean
Courant number hides local peaks. Retained peak locations lie close to the nozzle
and early jet; co-located phase at the peak is not available from the compact
scaling archives. Passing residual criteria and a mass ledger does not close
momentum or establish physical accuracy.

Do not clip U to make the result look stable: such an intervention changes
momentum and kinetic energy without a declared physical mechanism. Scalar alpha
bounding is different: stock v2512 isoAdvection has an optional final [0,1]
clamp (enabled by default) after conservative transport/bounding, followed by
boundary-condition correction. A near-bounded final internal alpha field does
not show that the transport step was accurate. Keep intermediate and final
alpha diagnostics separate and retain the mass-error record.

Primary documentation consulted:

- Roenby, Bredmose and Jasak (2016), [A computational method for sharp interface
  advection](https://doi.org/10.1098/rsos.160405), §3.5 and conclusion: conservative
  redistribution and optional clipping; interface motion across many cells per
  step is outside the regime in which the authors expect good performance.
  The paper's interface-normal Courant definition need not be identical to the
  solver's reported interface Co, so it is guidance rather than a universal
  acceptance threshold for this coupled case.
- [OpenCFD v2512 isoAdvection source](https://api.openfoam.com/2512/isoAdvection_8C_source.html),
  applyBruteForceBounding, lines 625–651: default clip=true, clamp_range(zero_one),
  then correctBoundaryConditions. This documents scalar bounding, not a remedy
  for velocity spikes.
- [Popinet's VOF course notes](https://gerris.dalembert.upmc.fr/papers/course.pdf),
  §3.1: pressure/surface-tension imbalance can create spurious currents. This
  is one candidate mechanism, not an established diagnosis of this case.
- [A novel consistent and well-balanced algorithm for simulations of multiphase
  flows on unstructured grids](https://www.sciencedirect.com/science/article/abs/pii/S0021999117306289)
  (2017): force imbalance and inconsistent mass/momentum convection are distinct
  sources of spurious currents, with convection consistency particularly relevant
  to high-density-ratio flows. This does not establish that stock interIsoFoam's
  rhoPhi is inconsistent; its actual discretization must be checked.
- [OpenCFD v2512 PIMPLE control source](https://api.openfoam.com/2512/pimpleControl_8C_source.html):
  nOuterCorrectors and nCorrectors are separate controls. The first diagnostic
  changes only fixed deltaT; coupling changes belong in a separate comparison.

Independent review recommends a clean 300-rank, fixed 0.0001 s run through
0.05 s, keeping the existing scheme and nOuter=1/nCorrectors=3. Retain sparse
fields near the first anomaly and 0.038–0.043 s, plus endpoint fields, within a
measured disk budget. If the spikes persist, test coupling separately, then
use matched old/new-mesh cases to isolate mesh effects. This is a proposed
exploratory diagnostic; no new job was launched in the morning inspection.


## G1 velocity-gradient limiter comparison, job 14648417

The declared purpose was to test whether bounding only the `grad(U)` reconstruction changes the max-speed history, bulk/interface Courant, intermediate and post-step alpha, ledger, solver residuals/iterations and cost. It was a one-factor exploratory comparison to original-gradient baseline **14648312**. The declaration specified no directional success criterion or post hoc pass threshold.

Both jobs used the same 10,099,265-cell mesh archive (`8da7141c…b8a12787`), fixed `deltaT=0.0005 s`, 0.05 s requested horizon, fresh initial fields, one alpha subcycle, PIMPLE `nOuterCorrectors=1` / `nCorrectors=3`, `limitedLinearV 1`, and matching `controlDict`, `fvSolution`, properties, mesh and initial-field hashes. The only physical solver dictionary entry changed in G1 was `grad(U) Gauss linear;` → `grad(U) cellLimited Gauss linear 1;` (`fvSchemes` SHA `6435e4d6…e2412a`; baseline SHA `fe51e9c9…a2db13`). This limiter bounds reconstructed slopes; it does not cap stored velocity and is not the paper's hybrid Gauss-LSQ/Venkatakrishnan scheme. The baseline used diagnostic retention; G1 used full retention and kept a stop checkpoint at 0.0455 s.

The native ledger audit verified all 22 prepared-case file hashes. The source capsule index binds the unchanged initial fields and solver code; the compact comparison JSON records the hashes for the case metadata, mesh, dictionaries and run artifacts.

The source capsule SHA is `19281933…ff8b3`, frozen at revision `e5d81158…7643678` with dirty source paths captured in the capsule. Komondor loaded OpenFOAM v2512 (`OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH`), GCC native 13.2, Cray MPICH 8.1.31, LibSci 24.11.0, FFTW 3.3.10.9, and Python 3.11.7. Requested placement was 300 ranks over three nodes, 100 ranks/node, one CPU/task, 64 GiB/node, CPU binding `cores`, memory binding `local`, collated file handler. Slurm granted the same counts on `x1000c0s1b1n1,x1000c7s2b1n1,x1000c7s3b1n0`; baseline ran on a different three-node set, so placement was not controlled or replicated.

The preserved attempt reached 91/100 steps and `Time=0.0455 s`, then its `max|U| > 1000 m/s` monitor requested stop signal 12. The solver child exited 0 and wrote `End`; the runner marked `stopped_with_preserved_evidence`, and the parent Slurm job is `FAILED` with exit 1:0. Treat this as a partial result, not a completed 0.05 s run. One final `kFinal` record failed its residual criterion: 100 iterations, residual `1.37534453342e-6` versus `1e-8`; all other recorded fields passed.

At 0.0445 s, `max|U|` reached **6975.24790046 m/s** at cell 21892, processor 141, `(0.0488827, -0.5688394, 0.1930174) m`. Adjacent maxima were 114.46 m/s at 0.0440 s and 173.12 m/s at 0.0450 s. The following pre-step report, computed from the peak-producing state, gave bulk/interface Co 195.063/18.513; these are not proof that high Co initiated the peak. Baseline's full-run peak was 412.477 m/s at 0.0425 s; at the same 0.0445 s timestamp it was 129.748 m/s. The G1 spike is 16.9 times the baseline full-run maximum and 53.8 times its same-time maximum. The final 0.0455 s field checkpoint does not capture the earlier peak, so its phase and mechanism remain unknown.

Keep alpha records distinct: the intermediate isoAdvection minimum reached `-0.18568`; the Phase-1 console minimum for `alpha.water` reached `-4.28e-6`; post-step `alphaExtrema` remained within `[-4.96e-14, 1]`. The partial ledger injected 56.9498 kg, reported 56.9566 kg in the native inventory, and had a 0.0067561 kg cumulative residual (0.01186% of injected mass), with maximum absolute per-step residual 0.0008423 kg and zero net escape. At the matched 0.0455 s endpoint the baseline ledger residual was 0.0109592 kg. These exploratory ledger values do not validate momentum or physical accuracy.

For the common **0.0100–0.0455 s** window (72 samples, 71 intervals, 0.0355 physical seconds), G1's printed `ExecutionTime` rose from 29.51 to 124.07 s, a 94.56 s interval. Baseline rose from 28.44 to 117.43 s, an 88.99 s interval. G1 therefore took about 6.3% longer in this matched log interval and had about 5.9% lower physical throughput from those printed `ExecutionTime` deltas. The corresponding coarse `ClockTime` deltas were 96 s and 90 s. `ExecutionTime` is printed to 0.01 s; `ClockTime` is quantized to whole seconds. Different node sets and retention policies, with only one attempt per variant, limit runtime attribution. Whole-run `srun` wall was 140.644 s for G1 versus 142.220 s for baseline, but G1 is incomplete and must not be called faster.

The G1 parent allocation lasted 397 s and charged 10:40:36 CPU (10.677 core-hours) from 33.083 allocated core-hours, about 32.3% whole-job busy CPU. The solver child used 10:36:23 CPU (10.606 core-hours), about 90.5% busy over the high-resolution 140.644 s × 300-rank `srun` envelope. That envelope corresponds to an estimated 11.720 core-hours of allocated solver time, not consumed CPU. Queue wait was 694 s; runner start to solver launch was 162.575 s. `.batch` MaxRSS was 9,454,128K; solver-step MaxRSS was 1,327,696K **per task**. No periodic RSS trace or parent-row peak was retained.

The stop checkpoint contains 1,070,503,845 uncompressed bytes across its eight field files (1,070,511,403 bytes including small metadata). The verified result archive is 1,688,102,352 compressed bytes (3,746,027,520 uncompressed bytes); gzip CRC passed and all 129 archive members match the saved inventory. Full-field writes were scheduled at 0 and 0.05 s; the early stop forced the 0.0455 s checkpoint. Neither checkpoint-write time nor archive-pack/finalization time is measured. The derived ~84 s from the solver `srun` envelope end to Slurm allocation end includes teardown and cannot be assigned to I/O.

Pressure iterations are counts, not seconds: the parser reports 1,732 `p_rgh` iterations over G1's 91 steps and 1,896 over baseline's 100 steps. No native profiler was enabled, so pressure-solve seconds and I/O share are unknown. The runner's `max_u_seen_m_s=155.0807` also conflicts with `solver_max_u_m_s=6975.2479` and the hash-matched per-step CSV/log. Use `solver_max_u_m_s`, `max-speed.csv` and `fieldMinMax` as the authoritative extrema; retain the discrepancy as a telemetry defect.

The reusable parser output has all 91 per-step rows, with physical-throughput indicators, iteration counts, residuals, Courant and alpha fields. Its `completed` label only sees the log `End` marker and child exit code; operational completion must come from run-state and terminal Slurm records. The exact parser invocation was:

```sh
.venv/bin/python scripts/hpc_metrics.py \
  --run g1=results/runs/rouaix-ulim-g1-20261026/live-20261026T075957Z/solver.log \
  --ranks g1=300 \
  --launcher g1=results/runs/rouaix-ulim-g1-20261026/live-20261026T075957Z/run-state.json \
  --output results/runs/rouaix-ulim-g1-20261026/analysis/parsed-openfoam.json
```

The compact matched summary, source hashes and measurement limits are in [`g1-vs-baseline-summary.json`](../results/runs/rouaix-ulim-g1-20261026/analysis/g1-vs-baseline-summary.json); the per-step series remain in [`parsed-openfoam.json`](../results/runs/rouaix-ulim-g1-20261026/analysis/parsed-openfoam.json). The final result archive SHA is `e0ef0963…f1297e`, with verification receipt `d863ec85…0489b34`. The terminal run-state, archive, accounting table, raw log, max-speed CSV, ledger and case hashes are bound in the summary.

This is not CFD validation or E1 acceptance. The mesh uses an exact coplanar/concave-set qualification exception affecting 114,008 cells and has zero added wall layers versus five reported in the paper; this case also uses isoAdvector and the inherited momentum scheme rather than the paper's HRIC/second-order-upwind numerics.

## T1 one-node fixed 0.1 ms, job 14649329

Purpose: compare fixed timestep against the same 120-rank, 0.05 s original
baseline 14647876. Both use the same 10,099,265-cell mesh, source, material
properties, original gradient/momentum schemes, turbulence and coupling.
T1 used 500 steps at 0.1 ms versus baseline's 100 steps at 0.5 ms. This is a
timestep comparison, not a strong-scaling test; the existing metrics tool
correctly rejects strong-scaling eligibility for different step counts.

Job 14649329 completed on x1000c7s4b1n1 with 120 ranks, one thread/rank,
64 GiB/node and a 45-minute limit. Submission to start was about 523 s;
Slurm backfilled the job at 10:01:24 UTC, despite an earlier much later
forecast. The job lasted 1,817 s; its srun solver envelope was 1,617.744 s,
OpenFOAM ClockTime 1,611 s, and runner-reported solver supervision elapsed
1,595.439 s. These are distinct timing boundaries. TotalCPU was 192,434 s
(53.4539 core-hours), versus 60.5667 allocated core-hours: 88.26% whole-job
CPU utilization. No pressure-solve or checkpoint/packing time profiler was
enabled, so do not infer those shares from iteration counts or the job gap.

All 500 steps reached 0.05 s and all 4,001 printed linear solves met their
declared tolerances. Exact peak speed was 103.293547802 m/s at 0.0497 s,
cell 38626, processor 66, location (0.57960894, -0.06325629, 0.40675186) m.
The solver log, global maximum of max-speed.csv and authoritative
solver_max_u_m_s agree; the final CSV row is lower and the old max_u_seen
alias remains slightly stale. Full-log bulk/interface Co maxima were
1.121541/0.560173. Post-step alpha.water was within [-1.65e-20, 1], and the
generic alpha minimum was -6.44e-14. No significant alpha excursion was found
in this short prefix. Peak-time phase is not established by the .05 s field.

The existing full ledger auditor exited 0 with 500 rows: 62.58221601488 kg
injected, 62.58221601489 kg in the domain at the final time and 1.05e-11 kg
cumulative closure residual, with no meaningful net escape. This does not
audit local momentum consistency or establish a physically validated plume.
The 0.5 ms baseline had peak speed 261.54586 m/s, bulk/interface Co
6.50730/4.36959 and a +0.0163593 kg cumulative mass residual. The smaller
timestep is promising at this horizon; neither run establishes 5 s stability.

The full binary-state archive is 1,719,302,994 bytes, 129 members/91 files;
SHA-256 f710b5a78cfaf818a7def4c516110a8dc4f375f91c8ff61197a151d2dbdcd2e0.
Native and independent local gzip CRC, SHA, member list and per-file size
verification passed before owned workspace cleanup. Final analysis and raw
evidence bindings are in
`results/runs/rouaix-one-node-t1-20261026/analysis-terminal-20261026T102840Z/terminal-analysis.json`.
The first metrics parse failed on a JobIDRaw-header/step-row handling defect;
the preserved rerun used the documented JobID header and succeeded. No
parser behavior or source physics was changed for this measurement.

## P0 per-core measurement setup, 26 October

The submitted v2 pair is **14652546 baseline -> 14652548 native profile**:
24 single-threaded ranks on one node, 46 GiB, fixed 0.1 ms through 0.01 s
(100 steps), 60 min caps and unchanged original numerical settings. The only
profiled-case dictionary change is the native monitoring block documented
above. At the 15:12 UTC root capture both remained pending, with no runtime
or speedup result. Case/source/command hashes, the failed admission and
independent readbacks are in the [compact P0 proof](../results/summaries/rouaix_percore_p0_20261026/README.md).

The first held 48 GiB request, 14652491, became 48 CPUs for 24 tasks with
CPUs/Task=2; it was cancelled before allocation. At the partition's 2000 MiB
per-core threshold, 48 GiB/24 is 2048 MiB whereas 46 GiB/24 is 1962.67 MiB.
The revised held jobs read back as 24 CPUs/CPT1. Test-only admission had
reported 24 processors for the original request, so it cannot replace actual
held-job validation. Slurm documents memory-related CPU/task adjustment in
its [sbatch memory rules](https://slurm.schedmd.com/sbatch.html#OPT_mem-per-cpu).

Historical solver-step totals sum each task's RSS high-water mark, not a
simultaneous node peak; MaxRSS is one task's maximum. N2 at 64 ranks summed
to about 31.23 GiB and T1 at 120 to 33.62 GiB; T1's separate batch maximum
was 9.03 GiB. These phases must not be blindly added. The 46 GiB budget is
informed by those sums with margin, not a measured 24-rank qualification.
See the upstream [accounting definitions](https://slurm.schedmd.com/sacct.html).
P0 captures optional cgroup-v2 job memory peak/current data; absence is null,
and the accounting fallback retains its different measurement scope.

Both jobs capture CPU model/topology and rank-zero affinity while retaining
core binding, local memory binding and one thread per rank. Native scopes
can identify linear-solver timing and rank imbalance. Interpret an observed
profile/baseline wall-time ratio with actual placement and co-tenancy, and
retain inclusive/child times separately. Full field-write timing remains
unmeasured by the built-in uniform/time scope. Only use complete, converged,
ledger-audited samples for performance comparisons. The 0.0020--0.0099 s
window contains 80 samples but 79 endpoint intervals (0.0079 s); no long-time
optimum or E1 acceptance is inferred from this startup pair.
