# Rouaix fixed-step HPC progression

**Status:** exploratory progression declared 25 October 2026. The first
64-rank, 1 ms, 50-step allocation (`14647683`) failed before launching the
solver: the runner checked for `sigStopAtWriteNow.C`, while the installed
v2512 module source is
`src/OSspecific/POSIX/signals/sigStopAtWriteNow.cxx` (installed real path
`/scratch/software/packages/openfoam/v2512-20251230/OpenFOAM-v2512/src/OSspecific/POSIX/signals/sigStopAtWriteNow.cxx`,
SHA-256
`5571278a48efd49507546d9ac4aa419519010d5a2de822992d53e287761a7a03`). The
source contains `stopAtWriteNowSignal` and `Time::saWriteNow`; the native
banner independently reported signal 12. This launcher source-path defect is
not a CFD result; no physical timestep or solver-performance data were
produced. Retry `14647686` loaded the solver but stopped near `t=0.002 s`.
At `t=0.001 s`, the
actual field-function-object line was
`min/max(mag(U)) = 0 92672390.4876 m/s`; the monitor only recognized the older
single-maximum syntax, so its declared 1000 m/s operational stop did not fire.
At `t=0.002 s`, the three velocity-component solves each reached 100 iterations
(final residuals 23.98, 103.40, and 394.19), then ranks 16 and 20 raised
`SIGFPE` in `GAMGSolver::scale`. There is no completed startup horizon or
ledger-complete result. The reported missing `t=0.002` extrema was downstream
of the crash. The runner now recognizes the native min/max pair and checks its
upper value against the existing guard; this parser correction does not alter
the physics or time step. Its single-step timing is invalid as a stable
throughput sample because the flow immediately diverged. The original capsule
`042202b589d518…` remains frozen. Later N1/N2 fixed-step probes completed
their solver horizons; their unchanged raw Slurm batch states failed only in
the frozen ledger-audit parser. Separate hash-bound posthoc audits verified
the full ledgers and give derived exploratory eligibility. This record is
not an E1 decision.

## Morning outcome, 26 October

The bounded chain completed all four fixed 0.5 ms, 0.05 s rank tests, each
100 steps. Jobs 14647793/14647876/14648039/14648312 used 64/120/240/300 ranks
on 1/1/2/3 nodes. Their full solver envelopes were
896.207/414.264/181.415/142.220 s; the declared 0.010–0.049 s clock windows
were 672/310/130/99 s. Allocated costs were 17.5289/17.6333/22.2667/26.0
core-hours, totaling 83.4289. These are measured exploratory startup timings,
not a long-horizon prediction or a validated comparison of identical trajectories.

Observed queue waits were 52/5152/12073/5164 s. Submissions occurred at
different cluster times, so these waits do not establish a general queue-time
law versus rank count. The 300-rank case ended at 05:06:46 UTC; final selector
14648313 completed at 05:06:57 UTC, declining the 0.5 s stage because its
1,947 s forecast exceeded the 1,023 s cutoff-bounded allocation remaining.
No 0.5 s or 5 s run was launched. All recorded CFD and selector IDs are
terminal; exact-ID squeue returned no active rows.

All four cases passed the declared residual/convergence and ledger-completeness
checks. Peak speeds nevertheless differ materially: 555.11/261.55/904.74/
412.48 m/s. The operational viability flag is not physical acceptance; inspect
locations, Courant history and timestep/decomposition sensitivity before
using 0.5 ms for a longer reproduction. No formal E1 decision is made.

Raw morning state, plan, accounting, allocation logs and four compact result
archives are in `results/runs/rouaix-hpc-morning-20261026/root-capture-20261026/`.
The capture manifest binds 53 files by size and SHA-256, and the terminal
24-event queue hash chain was independently verified. Per-run metrics and
independent review follow under the same morning evidence root. Old handoff
and fallback receipts remain unchanged and explicitly dated.

## Armed overnight handoff, 25 October 22:15 UTC

Selector **14647791** completed and submitted **14647793** (`ml-vof`):
64 ranks on one node, 64 GiB, original momentum, fixed `deltaT=0.0005 s`,
fresh 0.05 s horizon, endpoint write, compact diagnostic retention. The measured
forecast requested 1,616 s, rounded by Slurm to a 27-minute allocation. At
handoff it is pending on Priority; there is no new completed CFD result yet.
Selector **14647794** is accepted with `afterany:14647793`, one CPU/1 GiB/3 min.
It applies the finite progression below, with one active CFD job at a time.

Plan `queue-deploy-v2-20261026/overnight-plan.json` under the common scratch
root has SHA `939e12a5aa25189f4f29d802483524c8d0a049a42e73b48647806bbd436cf915`.
The cutoff is `2026-10-26T05:30:00Z` (06:30 CET); the limits are 300 ranks
and 2,700 allocated core-hours. Full in-memory adoption of the three real
seed records passed before arming. Preflight v1 found a historical full versus
diagnostic retention mismatch before any submission; v2 fixes that metadata
expectation while preserving every raw run. The actual seven-event state chain
passed independent root verification. Receipts:
`results/runs/rouaix-native-mesh-qa-20261025/launch/overnight-deploy-20261026/queue-stage-v2/`.
A scratch-root `PAUSE` marker prevents further dispatch and requests owned-run
checkpoint/stop. W&B remains offline pending a destination.

## Revised guarded diagnostic sequence

The sequence below supersedes the earlier `RHP-1` order later in this record:
the actual original-scheme 1 ms retry was unstable at startup, so proceeding
directly to a fresh long run was not justified. These are clean-start, one-factor exploratory
diagnostics on the same 10,099,265-cell cast-only input. They retain fixed
`deltaT`, one alpha subcycle, the current pressure initialization, turbulence
model, outer correctors, and linear-solver dictionaries. Initial `p_rgh` is
the declared transform of uniform gauge-static `p0`, not a claim of stationary
hydrostatic equilibrium. They do not claim a
scheme or time step is scientifically acceptable.

| ID | Declared case | Purpose and decision |
| --- | --- | --- |
| `N1-UPWIND-64-1MS-001` | Fresh `t=0`; 64 ranks/1 node; `0.01 s`, fixed `dt=0.001 s`; change only momentum convection from `limitedLinearV 1` to `upwind`. | Isolate the startup response to the declared first-order momentum-convection diagnostic. The case record binds the parent and post-override `fvSchemes` hashes. This is not a paper-numerics match. |
| `N2-ORIGINAL-64-01MS-001` | Fresh `t=0`; 64/1; `0.01 s`, fixed `dt=0.0001 s`; original `limitedLinearV 1` dictionaries. | Independently test whether a tenfold smaller fixed step allows the unchanged schemes to complete startup. It is not an automatic fallback or a restart from N1. |
| `N3-ORIGINAL-64-05MS-001` | Fresh `t=0`; 64/1; `0.01 s`, fixed `dt=0.0005 s`; original dictionaries. | Accepted only after N2's posthoc audit verified finite full-horizon ledger coverage and active residual criteria. |

N1 and N2 have independent diagnostic purposes and should run sequentially to
limit temporary mesh and decomposition storage. After the diagnostics, select
only a finite, fully completed candidate with successful compact-ledger audit
and every linear solve meeting the active `fvSolution` absolute or relative
residual criterion. Iteration count alone is not a rejection: the initial
`pcorr` solve reached its configured criterion after 799 iterations. Among
viable candidates, prefer original-scheme 0.5 ms, then original-scheme 0.1 ms,
then upwind 1 ms. If upwind 1 ms is selected, declare a separate upwind 0.5 ms
temporal check before treating that profile as established. If all diagnostics
fail, stop and review their evidence; do not auto-adjust the time step or
repeat a case without a new declared diagnostic purpose.

The corrected launch attempts are now distinct from the earlier invalid
bootstrap attempts. N1 job `14647712` uses the explicit input archive exports
and is the 64-rank, fixed 1 ms upwind diagnostic. N2 job `14647714` is declared
after-any N1 and uses the unchanged original scheme at fixed 0.1 ms. Both are
clean starts from the same qualified cast-only input; neither maps a previous
field or checkpoint. Jobs `14647709` and `14647710` stopped before solver
startup because their batch environments did not provide the archive under
the versioned project root. They are preserved operational failures and are
not stability outcomes or N1/N2 seeds. The overnight controller adopts only
the corrected job IDs and their verified run-state/archive hashes.
The corrected 24-member source capsule SHA-256 is
`fa45d1cdb575a9abf230fef2f48c7a00bc85ad0721a651e6a7186498c8c058a1`.

### Measured N1/N2 outcomes

Both solver steps returned zero and reached `0.01 s` from their declared
fresh starts. The batch runner marked each attempt `solver_complete_ledger_failed`
because its frozen parser omitted the fixed-`deltaT` ledger source from its
whitelist. The primary then ran a separate auditor against the preserved
archives; these receipts bind the original run-state, archive, input, prepared
case hashes, source identity, and solver log. This posthoc audit does not alter
the batch exit or raw run state, and neither receipt makes a formal validation
decision.

| Job/profile | Solver and convergence | Allocation and stored evidence |
| --- | --- | --- |
| N1 `14647712`, upwind, 64/1, `dt=0.001 s`, 10 steps | Solver wall 113.085 s; max `|U|=86.2437 m/s`; 81/81 solve records passed. `0.01 s / solver wall` is `8.84e-5` physical s/s, but no startup-excluded timing window is available. | 64 allocated CPUs, 64 GiB, 288 s total job time (5.120 allocated core-h); shared scratch free space 21,625,634,816 B at workspace selection and 16,955,244,544 B minimum. Archive 1,596,306,804 B, SHA-256 `605cc684998d67b2e23c68766f072010b336130ba07996b928104cdfb3267861`. Receipt `56f66c6dc25f24ea543bcc900c5bb10d03d737609f3f02777277feab614a488e`: 10/10 rows, mass closure `-1.8385767575068712e-08 kg`. |
| N2 `14647714`, original schemes, 64/1, `dt=0.0001 s`, 100 steps | Solver wall 708.682 s; max `|U|=91.2442 m/s`; 801/801 solve records passed. `0.01 s / solver wall` is `1.41e-5` physical s/s, but no startup-excluded timing window is available. | 64 allocated CPUs, 64 GiB, 880 s total job time (15.644 allocated core-h); shared scratch free space 20,029,091,840 B at workspace selection and 15,324,844,032 B minimum. Archive 1,603,772,295 B, SHA-256 `ac2fd101ea8d3db460acea06ddac4a410d1c47e7c55fc9362b90d23477299bd2`. Receipt `2be15c374889651cff9415da67118a0bca5ea9aead3b25398d5c2740e0a595e9`: 100/100 rows, mass closure `-2.1316282072803006e-14 kg`. |

These short startup rates are crude estimates, not the specified 0.010–0.049 s
throughput window. The N1/N2 comparison changes both the momentum scheme and
fixed time step, so it does not isolate time-step convergence. N3 job
`14647739` was accepted as the fresh original-scheme `dt=0.0005 s`, 64/1,
0.01 s diagnostic after the N2 supplemental audit. It completed all 20 fixed
steps, all 161 solver records passed, and its corrected ledger audit exited 0
with 20/20 rows and closure `-2.6935e-10 kg`. Solver wall was 200.942 s,
max `|U|=104.1425 m/s`; `0.01 s / solver wall` is `4.98e-5` physical s/s,
still with no startup-excluded timing window. The job used 64 ranks/CPUs,
64 GiB, and 379 s total allocation (6.738 allocated core-h). Shared scratch
free space was 18,424,565,760 B at selection and 14,676,926,464 B minimum.
The CRC-verified 129-member archive is 1,597,487,335 B, SHA-256
`60001e98abd39281a8efdf333e01c601acea72547c9f100a1e2ec9dba110c60a`.
Formal validation decision remains null.

Only after a candidate is reviewed should it receive a fresh 0.05 s run. A
successful 0.05 s case may then be compared at 120/1 and 240/2 ranks (300/3
only if the remaining allocation budget supports it), preserving the same
profile and fixed time step. The initial timing window is 0.010–0.049 s, so
the endpoint write is excluded. Run one 0.5 s case only when measured time,
storage and cutoff budget permit. Use the late 0.25–0.49 s window for its
throughput forecast; a runner-up 0.5 s case is skipped so the
main 5 s run retains the remaining cutoff budget. Attempt the approximately 5 s horizon only if
measured stability, conservation, throughput, output size and the absolute
2026-10-26 05:30 UTC cutoff permit. A 5 s clean-start candidate uses 1 s
sparse field checkpoints; choose its disk floor from measured 0.5 s field and
archive costs. A managed stop may leave a partial checkpointed run, which must
be reported as partial.

For N1/N2/N3 diagnostics and later rank comparisons, diagnostic retention is
planned to keep native logs, complete compact per-step ledger and extrema,
case dictionaries, source/runtime and prepared-input provenance while omitting
3D fields and mesh copies only after the ledger audit succeeds. The manifest
must list omitted paths and byte totals and state that an offline mesh/field
re-audit is unavailable without restoring inputs. The launcher default remains
full retention so the first frozen pilot capsule is unchanged. Scientific
0.5/5 s runs retain full fields and declared checkpoints. Resource accounting
is one CFD job at a time, at most 300 ranks and 2700 allocated core-hours over
the overnight window. Free-space floors are 12 GiB for 0.01 s diagnostics,
6 GiB for 0.05 s/scaling and 0.5 s runs, and 4 GiB for a 5 s run. The 5 s
case also compares its measured transient checkpoint-write peak plus its
runtime floor against the packing peak plus 1 GiB packing headroom.

Verified scheduler and archive measurements are in
[`pilot-run-metrics.json`](../results/runs/rouaix-native-mesh-qa-20261025/pilot-run-metrics.json).
Job timestamps below are site-local. The 1 ms step metrics are recorded for
diagnosis, not as a throughput baseline.

| Job | Queue / batch elapsed | CPU, memory, storage, archive | Solver result |
| --- | --- | --- | --- |
| `14647683` | Submit 21:12:43; start 21:13:10; queue 27 s; elapsed 57 s. | 64 CPUs; 53.356 CPU-s (0.936 mean cores); 6.278 GiB batch max RSS; 1.013 allocated core-h; archive 350,371,917 B, 51 members. | Source guard failed before solver. |
| `14647686` | Submit 21:19:40; start 21:20:02; queue 22 s; elapsed 232 s. | 4,751 total CPU-s (20.478 mean cores); 9.038 GiB batch max RSS, 0.600 GiB solver-step max RSS; 4.124 allocated and 1.320 consumed core-h. Shared Lustre fallback: free space 22,752,849,920 B at start, 19,005,546,496 B minimum; maximum write delta 3,747,303,424 B. Archive 789,892,367 B, 108 members. | Solver began 103.301 s after batch start; first step `ExecutionTime=48.3 s`, `ClockTime=52 s`. It reached `t=0.001 s`, then at `t=0.002 s` raised SIGFPE after the velocity solves failed to converge. The 52 s step is startup-affected and immediately divergent, so it is not a useful throughput sample. |

At `t=0.001 s`, the measured `maxCo` was 5,964,502.69592 and `maxAlphaCo`
was 5.12935081617. Ux/Uy/Uz each reached 100 iterations, with final
residuals 1.37235, 0.0169510, and 0.0184053. The `pcorr` solve took 799
iterations; `p_rgh` took 3, 3, and 25. At `t=0.002 s`, the velocity final
residuals grew to 23.9818, 103.399, and 394.188 before the `GAMGSolver::scale`
FPE on ranks 16 and 20. The batch ran on shared Lustre because no local block
filesystem qualified. The preserved archive and raw log paths are listed in
the metrics file; no valid completed ledger audit was produced.

## Question and fixed inputs

Measure how the current native OpenFOAM v2512 case advances at practical
fixed-step horizons, how solver cost scales with supported Slurm placements,
and whether a separately declared 0.5 ms time-step candidate changes stability
or observables. Preserve clean-start trials. Do not continue from a checkpoint
for the comparisons below.

The mesh is the 10,099,265-cell cast-only transfer, with zero added wall
layers. Its raw v2512 `checkMesh` output reports one `concaveCells` finding;
the primary's narrowly hash-bound exact-set exception qualifies exploratory
import only. It does not create `Mesh OK.` and does not match Rouaix's five
prism layers. Keep this mesh distinct from the earlier 35,190,080-cell fine
mesh record and the older 2,733,120-cell workstation instability case.

Use the unchanged Case 1 source and dictionaries: D=0.4 m; water velocity
`(0,-10,0) m/s`; air `(70,0,0) m/s`; gravity `(0,-9.81,0) m/s²`; water and air
properties and sigma from Table 2; realizable k-epsilon; v2512 `interIsoFoam`
with isoAdvector; `nAlphaSubCycles=1`; fixed `deltaT`; no automatic reduction.
The selected schemes and linear solvers remain the explicitly recorded
diagnostic assumptions in `E1_ROUAIX_HPC_PILOT.md`, not the paper's HRIC and
second-order-upwind numerics. Keep the fresh air-filled `t=0` fields and
declared transform-of-uniform-gauge-static-`p0` `p_rgh`; do not map old fields.

Source details are in [`E1_ROUAIX_CASE1_SOURCE.md`](E1_ROUAIX_CASE1_SOURCE.md),
Rouaix et al. (2023), DOI
[10.1016/j.ijmultiphaseflow.2023.104419](https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419):
Table 2–3, PDF p. 5; numerics §3.1, PDF p. 6; geometry and boundaries §3.2,
PDF p. 7; mesh and approximate 5 s run §3.3, PDF p. 8. The paper's 16 mm mesh
has five prism layers; the transferred mesh's local spacing and zero-layer
wall treatment are not a reproduction of that mesh.

## Declared queue progression

Each attempt is a fresh `t=0` case using the same 10,099,265-cell cast-only
mesh, air-filled initial fields, source, gravity, boundary conditions,
turbulence model, pressure setup, and native v2512 solver. The only diagnostic
scheme change is N1's declared momentum convection override; delta-T variants
remain fixed for the full run. There is no restart, adaptive step, automatic
retry, or change to pressure initialization or correction counts.

| Order | Case | Condition and purpose |
| --- | --- | --- |
| 1–2 | N1 upwind, 1 ms; then N2 original, 0.1 ms; each 0.01 s at 64/1 | Sequential clean-start diagnostics. N2 follows N1 regardless of N1 outcome. |
| 3 | N3 original, 0.5 ms; 0.01 s at 64/1 | Completed: 20 fixed steps; corrected ledger audit passed 20/20 rows; solver residual gate passed. Exploratory only. |
| 4 | Candidate selection | Prefer viable original 0.5 ms, then original 0.1 ms, then upwind 1 ms. If only upwind 1 ms is viable, first run a separate fixed 0.5 ms upwind temporal check. If no candidate passes, stop. |
| 5 | Fresh 0.05 s validation at 64/1 | Run the selected fixed-step profile from `t=0`, then measure 120/1, 240/2, and 300/3 only after each predecessor passes and the remaining cutoff/core/disk budgets fit. |
| 6 | One fresh 0.5 s at the measured best placement | Measure the startup-excluded 0.25–0.49 s window. Skip a runner-up 0.5 s case to preserve the main 5 s run window. No field mapping. |
| 7 | Fresh approximately 5 s at a measured placement | Only after stability, ledger closure, throughput, memory, and output costs justify it. Use declared sparse checkpoints; preserve partial runs. |

The selector is a short one-CPU dependency job. It adopts corrected N1/N2 and
the optional N3 seed, records measured completion and hashes, and dispatches at
most one next case plus one dependent selector. Seed paths may be direct
children or explicitly pinned, single-level versioned roots under the shared
project root; the sibling N1/N2 and N3 roots retain their own immutable code
capsules while binding the same input archive hash. It uses separate Slurm requests for
64/1, 120/1, 240/2, and 300/3; one CFD case runs at a time. Every sbatch case
request explicitly exports the versioned input archive path and SHA-256 plus
all declared profile variables. The selector refuses input or source paths
outside the shared project root and approved versioned seed paths. A finite queue-state hash chain
records decisions; ambiguous sbatch acceptance is a stop condition and never
causes an automatic resubmission. The N1/N2 raw batch states remain FAILED;
their independently hash-bound posthoc receipts supply derived exploratory
eligibility without rewriting the raw attempts or asserting formal validation.

Diagnostic cases and rank comparisons retain logs, source/runtime provenance,
case dictionaries, and the full compact per-step ledger/extrema. After a
successful ledger audit, diagnostic retention may omit 3D fields and mesh
copies while recording omitted paths and bytes; that archive cannot support an
offline field or mesh re-audit without restoring the common input. The 0.5 s
and 5 s scientific runs retain full fields and declared checkpoints. The
short diagnostic disk floor is 12 GiB; 0.05 s/scaling and 0.5 s floors are
6 GiB; the 5 s floor is 4 GiB plus measured write/packing bounds. The 5 s
bound uses measured 0.5 s field and archive costs and current quota, not
inferred filesystem free space. Allocations remain capped at 300 ranks and the reviewed 2700
allocated core-hour limit; actual accounting, memory, storage, queue wait, and
physical-time throughput are recorded for every attempt.

## Measurements and comparison windows

For every attempt, preserve the immutable per-run source capsule and record its
hash, mesh receipt hashes, prepared-case hashes, code revision/dirty state,
module/build/executable evidence, actual Slurm job ID, node list, node count,
tasks per node, memory, wall limit, queue wait, run wall time, and stop reason.
Report requested allocation separately from observed usage.

Use native per-step log data and the compact water ledger. Report `maxCo`,
interface Courant number, alpha and velocity extrema, each pressure/momentum
solver's iteration count and residuals, and per-step source/open-boundary/wall
fluxes. Iteration count is a convergence diagnostic, not a timing measure.
Measure timing independently from `ExecutionTime`, `ClockTime`, the runner's
monotonic solver wall time, and Slurm CPU accounting. Do not present
periodically sampled memory as a guaranteed peak. Capture actual `MaxRSS`,
CPU-time totals, sampled maxima, available disk, and per-node values when
Slurm exposes them.

Exclude startup from throughput summaries. For the 0.05 s validation/scaling
cases, report the explicit `0.010..0.049 s` window separately from the full
50-step run. For the 0.5 s runs, report `0.05..0.10`, `0.10..0.25`, and
`0.25..0.49 s`; also report the full run including startup. For a 5 s run, report `0.05..0.5`,
`0.5..1`, `1..2`, `2..3.0`, `3.0..3.2`, and `3.2..5.0 s` windows so any cost
or stability change near the historical 3.094 s stall is visible. Compute
physical-time throughput as `delta physical seconds / delta monotonic wall
seconds`; keep startup, setup/decomposition, solver, final output, and archive
time separate.

Full fields are written only at `t=0` and the declared final time. Compact
flux/extrema diagnostics remain per-step. A PAUSE, deadline, or operational
guard may request the configured write-and-stop signal on the verified Slurm
step; record checkpoint signal time, completion latency, written time, bytes,
and disk space. Endpoint-only fields are the current policy for the 0.05 s and
0.5 s clean-start runs; confirm their actual bytes and packing cost from the
pilot. A 5 s attempt needs sparse durable checkpoints (a 1 s interval is a
candidate) so an OOM or allocation stop does not discard the entire long run.
Choose that interval and its storage budget from measured pilot write bytes,
packing time, and available project quota before declaring the 5 s attempt; do
not add a checkpoint framework in this progression change. Free-space floors
are 12 GiB for short startup diagnostics, 6 GiB for 0.05 s/0.5 s runs, and
4 GiB for a 5 s run plus measured checkpoint-write and packing bounds.
Project scratch accounting currently reports about 22 GiB to the soft byte
quota and 124 GiB to the hard quota with active grace. These are quota
headrooms, not generic filesystem-free measurements; recheck and report both
for each run. Never restart a failed attempt automatically. Any later restart
must be declared as a separate experiment with its parent checkpoint, exact
time, hashes, and ledger offsets; the progression above uses clean starts.

## Historical evidence and limits

The 35,190,080-cell fine-mesh attempt stopped during startup before CFD and has
no solver time, solver RAM, or CFD result. The older 2,733,120-cell
workstation case stalled near `3.0942804546046 s`; a separate `maxCo=1`
checkpoint reached `3.0851454757947256 s` and was stopped before crossing that
region. It did not establish a fix. These records motivate explicit progress
checks but are not transferable performance or stability results for the new
10,099,265-cell cast-only mesh.

The progression is exploratory. It cannot establish E1 acceptance, mesh
convergence, or field validity. No claim that the 10.1M-cell cast-only mesh
matches the paper's five-layer 16 mm mesh is made.


## G1 velocity-gradient limiter comparison, declared 26 October

User steering prioritizes a gradient-limiter test before reducing timestep.
Case ID **G1-ULIM-300-05MS-005** is an exploratory, one-factor comparison
against 300-rank baseline **14648312**. Use the same qualified 10,099,265-cell
input archive, native v2512 binary/properties/boundaries and fresh initial
fields; 300 ranks on three compact nodes (100 each), one thread per rank,
64 GiB/node, fixed deltaT=0.0005 s, horizon 0.05 s (100 steps),
nOuterCorrectors=1, nCorrectors=3, one alpha subcycle and the existing
limitedLinearV 1 momentum convection.

The sole solver-dictionary change is `grad(U) Gauss linear` to
`grad(U) cellLimited Gauss linear 1`. Default, pressure, alpha and turbulence
gradient entries remain as in the baseline. This stock bounded-gradient
(minmod) diagnostic is not an exact implementation of the paper's hybrid-Gauss
LSQ/Venkatakrishnan treatment. It limits reconstructed slopes; it does not cap
stored velocity. Declare variant `u_gradient_limited`, parent/post-override
fvSchemes hashes and exact one-entry diff in the new source capsule.

Budget: one CFD job, 1,800 s requested wall (at most 150 allocated core-hours),
6 GiB minimum free scratch during compute; inspect actual availability/quota
before submission. Preserve full endpoint fields and the entire per-step
extrema/location/Courant/residual/alpha/flux ledger. Endpoint fields do not
identify the phase at an earlier transient peak; record that limitation rather
than inventing event snapshots. Keep the existing >1000 m/s/nonfinite/no-progress,
PAUSE and deadline guards, with a new bounded run deadline rather than the
expired overnight cutoff. Do not autoqueue a long run based only on exit zero.

Intended diagnostic: compare max-U time history and locations, bulk/interface
Courant excursions, intermediate alpha undershoot, post-step alpha extrema,
clip/ledger residual and residual/iteration counts with the frozen baseline.
Report solver wall, placement, queue wait, CPU accounting, per-task RSS and
archive bytes. This is hypothesis testing, without a formal E1 tolerance or
post hoc success threshold. If the limiter changes little, a dt-only case
and then a separate outer-coupling comparison remain useful next tests.

Preparation owner: rouaix_hpc_prep. Native staging/launch owner: overnight_hpc.
Root owns source interpretation, combined review and integration. A fresh
versioned root/capsule preserves the terminated night chain and earlier runs.


G1 execution receipt: **14648417** was accepted once, then exact readback
showed PENDING/Priority, with no allocation or start estimate. Slurm confirms
300 CPUs/tasks, three nodes with 100 tasks per node, 64 GiB per node (192 GiB
total), 30-minute cap, no dependency and no requeue. Source staging under
`rouaix-ulim-source-v1-20261026` passed every member SHA, Bash syntax and
Python AST checks; capsule SHA is
`19281933b6de48c5eb3cbcd1a00e610a74472b1b0e5a98d261604356241ff8b3`.
The immutable qualified input is a hardlink with matching device/inode and SHA.
Receipts are in `results/runs/rouaix-ulim-g1-20261026/`.
Local 80-test case/runner/queue suite and Ruff passed. Native preparation,
actual FV dictionary hash/diff and solver outcome remain to be reviewed after
allocation. This is one changed input scheme setting, but grad(U) feeds
convection limiter weights, stress and turbulence terms, so the experiment does
not isolate which of those numerical pathways is responsible for any response.


## G1 outcome and T1 fixed-timestep diagnostic, 26 October

G1 **14648417** is a failed exploratory stability diagnostic, not a full
0.05 s result. A frozen native-case comparison confirmed exactly the intended
one-entry fvSchemes change and identical fvSolution, controlDict and properties
against baseline 14648312. At t=0.0445 s, its recorded maximum speed reached
6975.24790046 m/s at (0.0488827, -0.5688394, 0.1930174) m, processor 141,
local cell 21892. Neighbouring maxima were 114.46 m/s at 0.0440 s and
173.12 m/s at 0.0450 s, indicating a severe local one-step excursion. The
monitor's existing >1000 m/s guard requested signal 12; the solver wrote and
ended at 0.0455 s (91 steps). Exit 0 and End reflect orderly stopping, not
horizon completion. The final kFinal solve also hit 100 iterations with
residual 1.375e-6 versus tolerance 1e-8. Preserve the full attempt and failures.

The previously reviewed timestep diagnostic is now the next bounded case:
**T1-ORIG-300-01MS-005**, compared against original-gradient baseline
**14648312**, not against G1. Revert the gradient-limiter variant to `original`;
use the same qualified 10,099,265-cell mesh, native solver, properties,
initialization, boundaries, original Gauss-linear gradients/limitedLinearV 1,
nOuter=1/nCorrectors=3 and one alpha subcycle. The sole intended numerical
change relative to that baseline is fixed deltaT **0.0001 s**, with the same
0.05 s horizon (500 steps). This tests timestep sensitivity, not a claim that
0.1 ms is the required production setting or that the paper's 1 ms is invalid.

Resources: 300 ranks, three nodes with 100 each, one thread per rank,
64 GiB/node, 1,800 s wall cap (at most 150 allocated core-hours), no GPU,
no requeue/dependency, no adaptive stepping. Full endpoint fields and per-step
location/extrema/Courant/residual/alpha/flux data are retained. Endpoint fields
still cannot identify the phase of an earlier transient maximum. The original
>1000 m/s/nonfinite/no-progress/PAUSE/deadline guards remain in force.

Launch only after G1's required terminal archive/checkpoint capture is complete
and fresh project-ID quota/active-job checks show room for one case. Account for
both workspace and archive packing with the 6 GiB runtime floor; do not rely on
global filesystem free space. Use a fresh versioned root and unchanged frozen
G1 code capsule with variant=original, so prior attempts remain immutable.
Execution owner is overnight_hpc; metrics owner hpc_measurements; root integrates
and independently reviews the interpretation. No follow-up long run is armed.


T1 submission receipt: **14648472** accepted once, PENDING/Priority at
08:13:46 UTC, start unknown, no allocation. The exact request matches the
300/3×100/64 GiB per node/30-minute declaration and variant=original,
deltaT=0.0001 s, end/write=0.05 s, full retention. G1's terminal archive was
verified before staging T1; the fresh scratch headroom was approximately
14.09 GiB, PAUSE absent and no prior owned CFD job active. T1 uses the same
frozen code capsule under `rouaix-dt01-source-v1-20261026` and a separately
hash-bound declaration, preserving G1. Receipts:
`results/runs/rouaix-dt01-t1-20261026/`. Actual native preparation and solver
outcome remain pending allocation.


## T1 one-node alternative, declared 26 October

User requests a one-node trial while the 300-rank T1 remains queued. Case
**T1-ORIG-120-01MS-005** uses the existing tested 120-rank / one-node placement,
not a new 128-rank tooling profile. Its direct temporal comparator is original
120-rank baseline **14647876** (fixed 0.5 ms through 0.05 s); its placement
comparator is **14648472**, the queued 300-rank T1 at the same fixed 0.1 ms.
Rank/decomposition effects must not be called a timestep effect when comparing
120 with 300 ranks.

Use the unchanged frozen G1/T1 code capsule and qualified 10,099,265-cell mesh,
fresh t=0, variant=original, native OpenCFD v2512 interIsoFoam, fixed deltaT
0.0001 s, horizon/write interval 0.05 s, 500 steps, one alpha subcycle,
nOuterCorrectors=1 and nCorrectors=3. Preserve original gradients, momentum
convection, material properties, source, turbulence, initial and boundary
conditions. No adaptive stepping, fitted coefficients or velocity clipping.

Resource request: one CPU node, 120 MPI ranks, one thread per rank, 64 GiB
node memory and 2,700 s (45 min) wall cap, at most 90 allocated core-hours.
The earlier 120-rank / 100-step solver envelope was 414.264 s; a simple
fivefold step-count estimate is 2,071 s before preparation and capture. This
motivates the 45-minute cap rather than an unsupported 30-minute assumption;
the estimate is not a throughput promise. The same-mesh 120-rank baseline
completed within a 64 GiB allocation; fresh sacct has no MaxRSS, so peak
physical memory remains unmeasured (MaxVMSize is not RSS). Inspect accounting,
fresh project-ID byte/inode quota, node fit, active owned jobs and PAUSE before
submission. Keep the existing 6 GiB runtime disk floor and all nonfinite,
>1000 m/s, no-progress, pause, signal and deadline guards. Full endpoint
fields plus per-step extrema/locations, residuals, Courant and alpha/flux
ledger are retained; no exact earlier peak-field capture is promised.

Serialize the two owned full-output trials to protect scratch headroom. If
300-rank T1 is still PENDING, submit the new one-node job held, verify its
identity/resources, attach only job 14648472's afterany dependency on the new
job, then release the one-node job. If 14648472 has started first, leave it
untouched and place the one-node job after it. Verify the final dependency
graph and ensure the new job is not left held. No unrelated autoresearch job
may be modified. No auto-requeue or additional long-run chain is armed.

Diagnostics: fixed-step completion and all residual/ledger guards; velocity
and turbulence extrema with event locations, preclip/final alpha, Co histories,
queue wait, solver and whole-job wall times, actual CPU accounting, RSS and
archive/inode cost. A guarded stop is a preserved failed/partial diagnostic,
not E1 acceptance. Preparation/execution owner: single_node_trial; root owns
declaration, integration and interpretation. Use a fresh versioned remote root
and local receipts under `results/runs/rouaix-one-node-t1-20261026/`.

Submission receipt: **14649329**, initially held for exact identity/resource
verification, then released. Root independently read back at **09:54:17 UTC**:
PENDING/Priority, no dependency/allocation, 120 tasks on one node, 64 GiB,
45-minute cap, Requeue=0 and the declared unique source root. While original
T1 14648472 was still pending, only its dependency was changed to
`afterany:14649329`; readback confirms PENDING/Dependency. The one-node job's
15:26 CET start forecast is an estimate, not an allocation. Local independent
receipt: `results/runs/rouaix-one-node-t1-20261026/root-submission-readback.json`.
The frozen 24-member source capsule and qualified mesh hashes were verified;
no numerical code changed, no unrelated job was modified, and neither owned
job was running at this capture.


## L1 one-node 5 s target, declared 26 October

User explicitly requests a one-node run aiming for 5 simulated seconds after
viewing the successful short timestep diagnostic. **L1-ORIG-120-01MS-5S** is
an exploratory development/stability run, not an E1 gate. Start fresh at t=0
on the same 10,099,265-cell mesh with the unchanged native OpenCFD v2512
interIsoFoam binary, original Gauss-linear velocity gradients, limitedLinearV 1
momentum convection, realizable k–epsilon inputs/wall functions, material
properties, source, initialization and boundaries. Keep one alpha subcycle,
PIMPLE nOuterCorrectors=1/nCorrectors=3 and fixed deltaT=0.0001 s. Target
5.0 s / 50,000 steps; no adaptive stepping, turbulence tuning or new scheme.

The supporting short run 14649329 completed all 500 steps through 0.05 s.
Its archive passed independent SHA/gzip CRC/member-list/size checks, all 4,001
printed linear solves met their declared convergence conditions, and its
500-row native ledger closed to 1.05e-11 kg. Peak speed was 103.29355 m/s;
bulk/interface Co maxima were 1.12154/0.56017. These are short-horizon
operational results; they do not establish long-horizon stability or physical
accuracy. The prior coarse-mesh adaptive failure near 3.094 s remains relevant
history, with no claim that its cause or threshold transfers to this case.

Resources: **120 MPI ranks on one CPU node, one thread/rank, 64 GiB memory,
72 h wall cap (259,200 s, at most 8,640 allocated core-hours)**. The short
case's srun solver envelope was 1,617.744 s for 500 steps; a linear 100-fold
step-count estimate is 44.94 solver-hours. This is a starting estimate, not
a promise: pressure work, interface population and I/O can change. The
normal QoS shows no additional MaxWall and the cpu partition allows seven
days at preflight, so the request fits the visible limits. A long wall request
may be harder to backfill than the successful 45-minute diagnostic.

Use full-retention mode with a 1 s field-write interval and the existing
purgeWrite=2 policy: retain the last two positive 3D checkpoint times plus
initial fields, with a possible third snapshot transiently during a write.
Earlier purged 3D fields will not be recoverable; retain every-step compact
extrema/locations, solver residuals, Courant, inventory and boundary-flux
streams throughout the run. Preserve any guarded-stop fields and diagnostics.
Do not invent an earlier peak-time 3D snapshot. No requeue or automatic
restart is armed; a wall/resource/physics guard stop is a preserved partial
attempt, and any continuation needs a separately declared parent/checkpoint.

Use the unchanged 24-member G1/T1 capsule with SHA-256
19281933b6de48c5eb3cbcd1a00e610a74472b1b0e5a98d261604356241ff8b3,
runner cf8205ea2e15a0eaf9072516fe06d91f3f3f8f8da0467ec5fb4b2698366b60ac,
and input 8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787.
Stage a new versioned root under **/project/nk_meshapplied/bene/fire-track2-hpc/**,
where fresh preflight shows approximately 3 TiB free and ample project byte/
inode quota. Reserve at least 16 GiB for expanded live fields, transient
checkpoint writing and final packing; keep the existing 6 GiB runtime floor,
PAUSE, nonfinite, >1000 m/s, no-progress and deadline/checkpoint-stop guards.
Actual node-local versus shared workspace selection must be recorded, not
assumed. Scratch's small remaining project-quota headroom does not qualify it
as the new long-run workspace merely because global filesystem space is large.

Submit this one job independently of pending 300-rank diagnostic 14648472,
with no dependency and no auto-requeue. Distinct /project storage removes the
reason to serialize its workspace with the scratch-based short case; Slurm
must allocate every requested CPU and memory resource. No unrelated jobs are
modified and no node is allocated to remain idle. Root separately authorizes
verified relocation of completed owned result archives from scratch to project
storage, preserving all bytes and old-path aliases, to restore short-case
scratch headroom. This is archival storage maintenance, not discarded evidence.

Execution owner: hpc_long_horizon; root owns the declaration and interpretation.
Receipts: `results/runs/rouaix-one-node-5s-20261026/`. Record queue wait,
actual placement/storage, complete/partial horizon, all source/input hashes,
convergence and mass errors, solver and job wall times, CPU accounting,
checkpoint/packing bytes and retained times. At end compare developed-plume
observables only with explicitly matched definitions/times; no new tolerance
or acceptance decision is set by this exploratory launch.

## Later source comparison requested, 26 October

User requests comparison with Rouaix after the longer run develops. Preserve
the current run's numerical inputs. Use the existing Figure 13 Case 1 vector
and independent raster digitizations, downward h=-y, nozzle x-origin zero
and D=0.4 m. Compare cloud alpha=.1 penetration and signed spanwise extents
against x/D; report both unresolved full-/half-width readings explicitly.
Connected alpha=.9 core breakup is a separate morphology measure. Figure
16's q=17.3 marker cannot uniquely identify Case 1. The user-preferred
ParaView alpha=.01 display is not a change to these source observables.

Admit complete-run final 4/5 s fields only with final solver/convergence/ledger
evidence; report guard-stop fields as partial. The paper does not specify the
Figure 13 sampling window, so two saved snapshots are not a matched time mean
or confidence interval. Reference hashes, station conventions, uncertainties
and required native-format adapter/resource work are in
`results/runs/rouaix-5s-comparison-prep-20261026/comparison-manifest.json`.
Eight existing reference/profile tests passed. No comparison has been run on
future fields, no automatic postprocess dispatcher is armed, and no formal
E1 tolerance or acceptance decision is declared by this preparation.

## S1 one-node small-step scaling and matched upwind, declared 26 October

User replaces the queued three-node diagnostic 14648472 with one-node starter
scaling tests and a matched momentum-advection trial. That cancelled pending
job already used 0.1 ms; the numerically compromised historical 0.5 ms scaling
results are retained, not overwritten. Existing independent 5 s job 14650641
keeps its declaration, frozen source and scheduler configuration.

Declare four fresh-from-zero exploratory cases, in this sequential order:

- **S1-ORIG-120-01MS-005:** original momentum scheme, 120 ranks, 45 min cap.
- **S1-UPWIND-120-01MS-005:** momentum upwind, 120 ranks, 45 min cap.
- **S1-ORIG-64-01MS-005:** original momentum scheme, 64 ranks, 75 min cap.
- **S1-ORIG-96-01MS-005:** original momentum scheme, 96 ranks, 60 min cap.

Every case requests one CPU node, one thread per MPI rank and 64 GiB, fixed
deltaT=0.0001 s, endTime=0.05 s (500 steps), no adaptive stepping and full
endpoint retention. The input is the same qualified 10,099,265-cell mesh
archive, SHA-256
8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787.
Native OpenCFD v2512 interIsoFoam, Cray MPI, Euler time integration, original
Gauss-linear gradients, realizable k-epsilon, source/initialization, material
properties, boundaries, alpha subcycles and PIMPLE settings remain unchanged.
The upwind case changes only `div(rhoPhi,U) Gauss limitedLinearV 1;` to
`div(rhoPhi,U) Gauss upwind;`. Case dictionaries and difference must be
hash-verified before release; do not combine gradient limiting with upwind.
The per-case S1 record and this progression document are the active declaration;
each attempt must preserve both or their hash-bound immutable source copies.
The generic pilot experiment.md is retained as historical background and does
not override the S1 timestep, horizon or numerical variant.
The new 120-rank original supplies a current-source matched control; job
14649329 remains an independent historical repeat, not the sole comparator.

This campaign does not establish an optimum for developed flow. Compare the
three original-scheme runs over the identical 0.0100--0.0499 s startup window,
reporting the actual printed-clock interval and its rounding uncertainty.
The 400 inclusive samples contain 399 endpoint intervals (0.0399 s); use
that span with the first/last ClockTime difference, not 0.0400 s.
Separate solver srun envelope, setup/decomposition, whole-job wall time,
queue wait, measured TotalCPU, allocated core-hours, per-task RSS, node/task
placement and I/O/packing bytes. Do not call pressure iteration counts time.
Full 3D output is identical and sparse (initial/final); collect every-step
extrema/locations, alpha bounds, Courant values, linear-solve criteria,
turbulence records, water inventory and boundary-flux ledger. A faster case
with failed diagnostics is not a qualified performance choice.

Compare upwind with its 120-rank original at the same times and horizon using
those diagnostics and the retained final fields. The transport-consistency
research motivates this single-factor trial; a lower peak speed or bounded
alpha cannot prove momentum conservation or correct breakup. Upwind numerical
diffusion can change penetration, width and interface structure. Quantitative
field/momentum observers require separately verified postprocessing; no
unimplemented observer or formal E1 tolerance is claimed here.

Submit four real Slurm jobs with an afterany dependency chain so at most one
short campaign job can allocate at once. A failed case must remain preserved
and is not automatically retried; the next distinct declared diagnostic may
run. Do not create dependencies on the independent 5 s target. The sum of
requested rank-times-wall caps is at most **356 allocated core-hours** if
AllocCPUS equals requested ranks; record actual AllocTRES/billing if different.
No idle reservations, automatic requeue or unrelated-job changes are allowed.

Use a new immutable source root on /project and force the short-case expanded
workspace onto that shared filesystem with
`ROUAIX_REQUIRE_SHARED_WORKSPACE=1`; this avoids relying on ephemeral node
storage if final packing fails. Reserve at least 24 GiB campaign headroom
for four ~1.7 GiB result archives, the single active expanded case and packing;
use the existing 12 GiB runtime free-space floor and inspect actual project
quota as well as filesystem availability. Keep collated I/O and packed
archives, verify CRC/hash/membership before removing only owned workspaces,
and preserve all failed attempts. Existing nonfinite, speed>1000 m/s,
no-progress, PAUSE, signal escalation and deadline/checkpoint guards remain.

Execution owner: Luna one_node_queue; source support: Luna one_node_support;
root owns declaration, staging review and interpretation. Per-case immutable
records, source capsule, scheduler submission/cancellation/estimate receipts
and later terminal evidence live under
`results/runs/rouaix-one-node-campaign-20261026/`. These are exploratory
operational tests, not an E1 gate or field-validation result.

## P0 small-allocation native profiling pair, declared 26 October

User requests per-core HPC optimization while the five S1/L1 jobs wait.
Do not change those submitted jobs or their frozen source roots. Prepare
two fresh-from-zero diagnostic jobs in a separate immutable source root:
**P0-BASE-24-01MS-001** and **P0-PROFILE-24-01MS-001**, in that order with
an afterany dependency. Both request one CPU node, 24 single-threaded MPI
ranks, **48 GiB** memory, fixed deltaT=0.0001 s through 0.01 s/100 steps,
60 min wall cap, initial/final full fields and every-step compact diagnostics.
They use the same qualified 10,099,265-cell mesh/input SHA
8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787,
original limitedLinearV 1 momentum convection, original Gauss-linear gradients,
Euler time integration, realizable k-epsilon, source, fields, boundaries and
material properties. No adaptive stepping, clipping, solver tolerance change,
new pressure algorithm, mesh change or boundary tuning is allowed in this pair.

Memory is an operating budget informed by the completed T1 accounting, not a
proved 24-rank peak: the sum of T1's per-task RSS high-water marks derived from
120 * AveRSS is about 33.62 GiB; the separate batch-step maximum is 9.03 GiB.
These are not simultaneous node-wide samples and shared pages can be counted
more than once. 32 GiB is not qualified by this evidence; 48 GiB gives about
43 percent headroom over the summed solver marks. Fewer ranks may reduce MPI
overhead but can increase per-rank working sets. Record actual cgroup/Slurm
peak data when available, and retain any OOM/guard failure rather than silently
retrying with changed memory. Keep the shared /project workspace so partially
written fields remain durable if a rank or packaging step fails.

Before submission, check the cpu partition's actual MaxMemPerCPU and use
Slurm test-only admission for 24 tasks/48 GiB. If the site allocates an extra
CPU to satisfy its memory-per-CPU rule, record 24 active ranks versus actual
AllocCPUS/billing; the maximum pair budget is 48 core-hours at 24 CPUs or
50 at 25. Do not silently increase resources beyond 25 CPUs per job. If the
request is rejected, preserve the rejection and resolve the concrete limit
before submitting. Free cores and memory must fit on one node; currently
observed fragments are not reserved or a start guarantee.

The profiled case differs only by this native controlDict monitoring block:

```foam
profiling
{
    active true;
    cpuInfo false;
    memInfo false;
    sysInfo false;
}
```

Record the exact baseline/profile dictionary difference and source hashes.
This is stock OpenCFD v2512 monitoring, not a patched solver. Preserve raw
collated per-rank profiling objects in the result archive. Use the verified
installed profilingSummary path only after checking its collated-reader/CLI
requirements; otherwise analyze the preserved raw data later with an audited
reader. A missing summary is not proof that CFD failed.

Compare solver wall time and matched native ClockTime samples from 0.0020
through 0.0099 s: 80 samples, 79 endpoint intervals/0.0079 s. Record rounding
uncertainty. Keep startup, decomposition, output/packing, whole-job time, queue
wait, measured CPU time, allocated CPU-hours, node/CPU model/NUMA topology and
actual affinity separate. Report profile-overhead ratio only for numerically
complete, converged runs with the same timestep/horizon and diagnostic checks.
Different placements, co-tenants or hardware make that ratio observational.
The historical 64-rank N2 0.1 ms/0.01 s diagnostic may be contextual evidence
only until its full physical dictionaries/mesh/observables are matched.

The native lduMatrix::solver.<field> profile scopes give linear-solver wall
time/calls and per-rank imbalance. Inclusive parent and child times overlap;
do not add them together. The objectRegistry::writeObject scope in this build
only surrounds uniform/time output and cannot establish full field-I/O time.
Do not infer pressure timing from iteration counts, total MPI wait from
pressure scopes, or a complete I/O fraction from the native monitor. No new
speedup, optimum rank count, momentum consistency or E1 accuracy is established
by enabling instrumentation. Use measured bottlenecks to declare subsequent
performance changes one factor at a time.

P0 is independent of the S1 chain and L1 long target so a small allocation can
make progress while those larger requests wait. At most one P0 job runs at a
time; together the declared families can occupy at most three productive
nodes, with no idle reservation or automatic requeue. Existing PAUSE,
nonfinite, speed>1000 m/s, no-progress and deadline/checkpoint guards remain.
Use collated I/O, one source capsule, a hardlink to the verified input archive,
packed results, CRC/member/hash verification before owned-workspace cleanup,
at least 16 GiB project-quota staging margin and the 12 GiB runtime disk floor.

Execution owner: Luna one_node_queue; implementation: Luna hpc_perf_support;
performance evidence: Luna hpc_perf_evidence. Root owns declaration and
interpretation. Case records, source snapshot, test-only and real submission
receipts, source/API inspection and later analysis are preserved under
`results/runs/rouaix-percore-p0-20261026/`. The pair is exploratory, not an E1
validation or a long-horizon performance qualification.

### A1 scheduler-order amendment to S1, 26 October

An observed 64-core free block at 14:40 UTC could not admit S1's 64-rank case
because it depended on the still-pending 120-rank control/upwind pair. While
all four S1 jobs remain pending, reorder only their scheduler dependencies
to **64 -> 96 -> original 120 -> upwind 120**: clear 14651180's dependency
and set 14651174 afterany 14651185; the other two links are unchanged.
Verify exact job/user/workdir identity, briefly hold the 120-rank control
during the update and release it after the new chain is verified. If a job
has started, stop this amendment and preserve its existing scheduling state.
Numerical inputs, immutable source and pre-submit records remain unchanged;
the scheduler amendment receipt records the changed order without overwriting
those historical declarations. The one-at-a-time S1 limit and independent
5 s job remain. This improves admission opportunity, not priority or assured
start time. Receipt: `results/runs/rouaix-one-node-campaign-20261026/scheduler-order-amendment.json`.

### A2 P0 memory/admission amendment, 26 October

The first real held P0 submission **14652491** requested 24 tasks/48 GiB,
but Slurm reported 24 tasks, NumCPUs=48 and CPUs/Task=2. The cpu partition's
MaxMemPerCPU is 2000 MiB; 48 GiB/24 = 2048 MiB per requested core exceeds it.
Test-only admission had forecast 24 processors and did not expose this change.
The worker cancelled 14652491 while held, with no allocation or CFD start;
retain its complete v1 source/records and cancellation evidence. It is an
admission failure, not a failed flow solution or performance sample.

Supersede the P0 memory request with **46 GiB** for 24 single-threaded ranks:
47104 MiB/24 = 1962.67 MiB per core, below 2000 MiB. This is about 37 percent
above the prior 33.62 GiB summed solver-task peaks. It remains an informed
operating budget, not a measured 24-rank peak or evidence of site enforcement.
Use new case IDs **P0-BASE-24-46G-01MS-001** and
**P0-PROFILE-24-46G-01MS-001**, a new immutable v2 source root, and refreshed
source/declaration/case hashes. Keep all numerical inputs, profile-only
difference, fixed 0.1 ms/0.01 s/100 steps, 60 min caps, full retention, guards
and the baseline -> profile afterany relationship from P0 unchanged.

Require actual held-job readback **NumTasks=24, NumCPUs=24, CPUs/Task=1,
MinMemoryNode=46G, one node** before releasing either job. If Slurm again
increases CPUs or changes the shape, cancel while pending and investigate;
do not run an undeclared shape or weaken the runner's one-CPU/task check.
The pair's maximum allocated CPU budget remains 48 core-hours. Source v1
remains preserved; no original case or record is overwritten.
