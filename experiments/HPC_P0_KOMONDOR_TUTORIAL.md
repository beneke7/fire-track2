# Komondor P0: CPU tutorial and I/O characterization

Declared 2026-10-24 before any job submission. Exploratory infrastructure and
strong-scaling exercise; no E1–E6 acceptance decision or aircraft reproduction.

## Case and inputs

Use the installed OpenCFD `OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH` module,
`interIsoFoam`, build `_87ed40d256-20251219`, and its unmodified-source
`tutorials/multiphase/interIsoFoam/damBreak` geometry, materials, gravity and
boundary conditions. Preserve a copy and hashes of the actual dictionaries.
The tutorial is a thin, two-dimensional dam break with an obstacle; it is not
an aerial release. Coordinates and SI dimensions come from its dictionaries:
`blockMeshDict` scale is 0.146 m, gravity and liquid column are supplied by the
installed tutorial. Preserve the original PDFs and existing CFD attempts.

Smoke: stock 9,072-cell mesh, eight MPI ranks, fixed 0.001 s step, 100 steps
to 0.1 s. Scaling: multiply each block's x/y cell counts by 16, keep z at one
cell, giving 2,322,432 cells. Run exactly 50 fixed 0.00002 s steps from clean
initialization to 0.001 s for every rank count. These are provisional
performance settings, not temporal or spatial convergence choices. Keep the
same pressure, transport and interface settings across scaling trials.
Disable tutorial surface exports during the timing trial; save initial and
final volume fields only, then reconstruct the final state for ParaView.

## Resources and progression

Use only Slurm CPU allocations in account `nk_meshapplied`, partition `cpu`,
QOS `normal`, one thread per rank, physical-core binding. Use short job names
`ml-io-s08`, `ml-io-100`, `ml-io-500`, `ml-io-1000`, `ml-io-1200`; these names
do not change the recorded solver. Initial hard wall budget is ten minutes
per trial. Run the smoke before scaling, and scaling trials sequentially.
Target 100/500/1000/1200 MPI ranks on 1/5/10/10 nodes, subject to scheduler
admission and measured resource use. Use 100 ranks/node for the first three
scaling points and 120 ranks/node for the final point. This keeps within the
site's 120-rank/node guidance; the largest free CPU-node fragment at discovery
had 103 cores, so a 100-rank baseline may start sooner. Record allocated/billed
CPUs separately from active ranks. The documented group limit observed at discovery is 5,000
CPUs; unrelated existing jobs remain untouched. No GPU jobs or rendering.

Advance only after the preceding run exits successfully, produces the
requested final field, and has finite diagnostics, bounded alpha to the
reported numerical precision, and no Courant maximum above 0.5. Stop on
fatal errors, failed mesh/decomposition, missing final state, exhausted wall
budget, non-finite fields, quota pressure, or a user pause. Keep every failed
attempt and its logs. Any shorter diagnostic prompted by a failure gets a
distinct directory and declared purpose; do not silently rerun it.
Poor scaling is an observed result, not grounds to change the fixed workload
mid-sweep. Larger-rank steps remain short overhead tests, not production
recommendations. An actual bounded submission mechanism must serialize jobs;
a written queue is insufficient.

Operational submission uses `afterok` dependencies with
`--kill-on-invalid-dep=yes`, a finite scheduling deadline and a shared
`PAUSE` sentinel checked before work and before the solver. A user pause also
requires cancelling this exercise's recorded active/pending IDs; the sentinel
alone does not interrupt an already running solver. Completed failed attempts
may be archived intact after integrity/ownership checks to reduce live inodes.
The initial twelve-hour scheduling deadlines were replaced with 36 hours
after Slurm's start estimate moved beyond them. Runtime limits stay at ten
minutes; the offline collector gets a 38-hour scheduling deadline and a
three-minute runtime. Slurm denied in-place deadline updates, so only pending
owned jobs are replaced, retaining their cancelled submission records.

## Additional fragment-fitting diagnostic

Declared 24 October before submission, after the user requested use of the
316 unallocated CPU slots visible across 29 nodes. The largest free CPU-node
fragment was 79, so the one-node 100-rank request could not fit that snapshot.
Try one 64-rank, one-node pilot with the **same** 2,322,432-cell mesh, 50 fixed
0.00002 s steps, physics, diagnostics and operational limits as the scaling
cases. Request 32000M, one CPU/thread per rank, ten minutes maximum runtime,
no GPU resources and a four-hour scheduling deadline. Choose an eligible
128-core CPU-partition host from a fresh resource snapshot, without exclusive
node allocation. Use a distinct `ml-io-64` job and immutable run path. This
additional performance diagnostic does not replace the queued 100/500/1000/
1200 trials. Verify the actual CPU/node model before any scaling comparison.
If the scheduler's test-only estimate is over one hour away, report that limit
before adding another long-waiting diagnostic. The aggregate free-core count
does not override priority, reservations, memory or per-node fit constraints.

## Flexible multinode diagnostic

Declared before submission following the user's request for wiser distribution
across available nodes. Keep the same 100 ranks, refine-16 mesh, 50 steps and
0.00002 s step. Let Slurm select 1–8 nodes, omit a fixed tasks-per-node count,
and use block/pack task distribution, one CPU per task, a minimum eight CPUs
per node and 1500M per CPU. The minimum gives at least 12000M on the first
node for serial meshing/decomposition, while staying below the CPU partition's
2000M-per-CPU ceiling. Measure the actual peak; the refined preparation peak
has not yet been observed. Use CPU hosts, no GPU resources or exclusive-node
allocation, ten minutes maximum runtime, a four-hour scheduling deadline,
no requeue and a distinct `ml-io-flex` run path. Existing queued scaling jobs
remain unchanged. Record actual rank distribution, hardware and contention;
this diagnostic is not interchangeable with a packed one-node timing without
reporting its layout. A scheduler estimate beyond its deadline is a forecast
and may lead to expiry; do not label an accepted pending job as running.

## Everyday core-count sweep

User direction: prioritize the fastest practical normal allocation, then
consider long larger jobs on demand. Run matched 8/16/32/64/100-rank refine-16
cases, each with the same 50 steps, 0.00002 s timestep, initialization and
physics above. Use one node and 16000M per node for 8–64 ranks; use the flexible
1–8-node layout above for 100 ranks. Each serial preparation step requests
eight CPUs with one software thread. This fixes the observed flexible-job OOM:
Slurm limited its previous one-CPU preparation step to 1500M even though the
node allocation had more memory. No solver evolution occurred in that failed
attempt; preserve it. The new per-node/step memory allowance remains to be
measured on the refined mesh.

Arm an actual sequential afterok chain with six-hour scheduling deadlines,
ten-minute runtime limits, no requeue, sparse outputs and automatic invalid-
dependency cancellation. Keep the existing larger short characterization
requests, but gate them behind the normal sweep if an owned pending dependency
update is permitted. Record actual background load, node layout and hardware.
Compare solver-step wall time, preparation and output overhead, measured peak
RAM and allocated core-hours; report the speed/cost trade-off rather than
declare a maximum-rank winner. A 300-rank, 3–4-node burst is a candidate after
these measurements, not a long-run launch authorization. Tutorial timing is
only a provisional allocation guide until checked on the actual nearfield case.

## Wide-rank follow-up, 25 October 2026

The user explicitly requested 300–1200-rank tests after reviewing the completed
8/16/32/64/100-rank sweep. Run 300, 500, 1000 and 1200 MPI ranks sequentially
on 3, 5, 10 and 10 CPU nodes respectively. Use 100 ranks/node for 300–1000
and 120 ranks/node for 1200, one physical CPU/thread per rank, no GPU or
exclusive-node request, and 16000M per node. All serial setup/reconstruction
steps retain eight allocated CPUs with one software thread; the prior refined
checkMesh MaxRSS sample was about 5.5 GiB. Preserve the same refine-16 mesh,
2,322,432 cells, 50 fixed 0.00002 s steps to 0.001 s, physics, diagnostics,
reconstruction and archive policy. This is a strong-scaling/communication
probe with only about 1,935 cells/rank at 1200, not a production rank choice.

Use short names `ml-io-300`, `ml-io-500`, `ml-io-1000`, `ml-io-1200`, unique
run paths and a uniquely staged, hash-verified launcher. Submit an actual
300 -> 500 -> 1000 -> 1200 afterok chain, invalid-dependency cancellation,
no requeue, ten-minute runtime per job and a 36-hour scheduling deadline.
The nominal rank-runtime budget across all four jobs is 500 core-hours;
actual allocated cost must include any per-node CPU/memory rounding;
queued jobs consume no cores until admitted, and only one solver allocation
in this chain can run at a time. Scheduling deadlines are finite waiting
bounds, not promised start times. Do not cancel or modify unrelated jobs.
A user pause applies to active and queued work as described above.

The pre-submission snapshot at 08:56 UTC found 809 account CPUs allocated
against the shared 5,000-CPU cap, 1,563 idle CPU-partition cores spread across
mixed nodes, and no fully idle CPU nodes. Group project storage was 1.1 TB
of 4 TB and 840,928 of one million soft-limit entries. Packed requests still
need the scheduler to find sufficient per-node cores and memory; aggregate
idle counts do not guarantee admission. Scratch remains above its inode soft
limit, so continue using project storage.

Keep every failed attempt and abort dependent trials on operational failure.
Poor scaling alone is a result, not a reason to change the fixed workload.
Collect high-resolution solver-step wall time, whole-job elapsed/actual CPU
accounting, per-stage timings, layout, alpha/Co checks, input/mesh hashes,
archive integrity and live entry counts. Reuse the offline metrics CLI and
compare with the earlier sweep only after checking matched inputs and horizon.
The collector must preserve usable solver-only evidence when SlurmDBD is
unreachable from compute nodes; recover accounting through the authenticated
login session later rather than inventing missing values. No W&B upload.

### Fragment-fitting layout amendment, before submission

The packed 300-rank test-only forecast on 25 October was October 29, beyond
the 36-hour deadline; only two nodes had at least 100 idle cores. No packed
chain was submitted. Try the requested rank counts with flexible node ranges:
300 on 3–8 nodes, 500 on 5–12, 1000 on 10–24, and 1200 on 10–32. Use names
`ml-io-300f`, `ml-io-500f`, `ml-io-1000f`, `ml-io-1200f`, no fixed tasks
per node, a minimum eight allocated CPUs per node, block/pack distribution,
and 16000M per node. Keep one CPU/thread per rank, the same mesh/horizon and
all operational checks. Do not queue duplicate packed and flexible trials.
Serial preparation still requests eight CPUs. Record allocated CPU rounding
separately from the exact requested active MPI ranks.

Submit the real flexible afterok chain with the same ten-minute runtime,
36-hour scheduling deadline and invalid-dependency cancellation, then arm the
finite afterany collector. A test-only forecast is neither an allocation nor
a reason to label an accepted pending job running. Flexible placement does
not guarantee earlier admission. Compare rank counts together with actual
node count, task distribution and contention; this arm does not isolate the
performance of a packed three-node or ten-node allocation. Memory reservations
are per node and total requested memory grows with node count. No physics,
convergence tolerances or storage formats change.

The first accepted flexible requests interpreted `--ntasks-per-node=120`
as `MinCPUsNode=120` despite `--mincpus=8`. Their pending resource records
therefore did not match the intended fragment-fitting layout. Replace only
those owned pending, zero-allocation requests and their pending collector;
preserve cancellation records. Omit `--ntasks-per-node` entirely in the
replacement, as in the successful earlier 100-rank flexible run. Verify the
first accepted job's `MinCPUsNode=8`, `ReqTRES cpu=N`, tasks=N, memory, node
range and afterok chain before proceeding. Each host has 128 physical CPUs;
let Slurm place one CPU per MPI rank without oversubscription and record the
actual per-node count. The earlier 120-rank packed guidance is not an enforced
cap in this flexible arm. Replacement attempts use distinct `flex2` run paths.

### MPI-startup diagnostic after the 1000-rank failure

The 1000-rank job failed before any CFD timestep at MPI initialization:
`cxil_map: write error` and OFI endpoint enable returning `Cannot allocate
memory` on x1000c0s5b1n1. The observed maximum was 90 ranks/node, so 128
ranks/node or CFD field-memory overflow is not established. Its 1200-rank
successor cancelled without allocation. Preserve both outcomes.

Before repeating expensive CFD setup, run a tiny native-MPI startup/allreduce/
barrier/finalize probe at 1000 ranks on 10–24 CPU nodes, one CPU/thread per
rank, minimum eight CPUs/node, 16000M per node, no fixed tasks/node, no GPU
or exclusive allocation. Use one three-minute Slurm job, no requeue and a
36-hour scheduling deadline, unique source/build/log paths and PAUSE checks.
Within that allocation, test the recorded module/default receive-matching
mode and then `FI_CXI_RX_MATCH_MODE=software`, with separate synchronous srun
steps bounded to one minute each and failure propagation/cleanup. Record each
exit independently: an intentionally captured baseline transport failure may
be followed by the software test, but must not be relabelled successful.

Use the same loaded cray-mpich/libfabric stack as OpenFOAM. Record compiler,
linked libraries, program/source hashes, MPI version/thread level, actual
world/node counts, exact allreduce result, selected network environment,
job/step accounting and relevant nonsecret resource limits. Never run MPI on
the login node or change shared NIC/system settings. Do not guess a VNI or
increase memory without evidence. A passing probe qualifies only this MPI
startup path; CFD must still be rerun as a distinct attempt.

The proposed environment comparison is supported by the site's
[OpenFOAM multi-node guidance](https://docs.hpc.dkf.hu/software/openfoam.html)
and [libfabric CXI provider documentation](https://ofiwg.github.io/libfabric/main/man/fi_cxi.7.html).
Software matching is a diagnostic hypothesis, not an established fix for
this observed endpoint failure. Keep failed and successful timings separate.

### Conditional software-matching CFD arm

If the 1000-rank software-mode startup diagnostic exits zero with the exact
world size, successful reduction/barrier/finalize and adequate MPI thread
support, permit distinct 1000- and 1200-rank tutorial attempts with
`FI_CXI_RX_MATCH_MODE=software`. Capture the default-mode outcome too; if both
pass, do not claim that software matching caused the recovery. If software
startup fails, do not repeat the large CFD preparation.

Use the same case, physics, 50 steps and diagnostics as the wide arm, new
`software` run paths, 1000 on 10–24 nodes then 1200 on 10–32 nodes, one CPU/
thread per rank, minimum eight CPUs/node, no fixed tasks/node, 16000M/node,
ten-minute job limit, no requeue and 36-hour waiting deadline. Run sequentially
with afterok and invalid-dependency cancellation. Maximum nominal additional
CFD budget is 366.7 core-hours; the prior standalone MPI diagnostic is at most
50 core-hours. Let Slurm admit the requests without changing other jobs.

In each new allocation, run the tiny MPI probe first with the actual requested
rank count and software matching, bounded to one minute, before any meshing
or decomposition. Save a separate job-ID-specific startup log; preserve a
failed preflight without entering CFD. Compile/source/library and input hashes,
network environment, exact allocation and all prior failure records remain
part of the evidence. Arm a finite afterany collector for these attempts.

These are a separate transport-configuration arm: software-mode performance
must be labelled beside the default-mode 8–500-rank results. An MPI startup
pass is not a CFD accuracy result or proof that the earlier failure was
ordinary host-RAM exhaustion. Do not alter the solver's numerical settings.

### One bounded 1200-rank placement diagnostic

Software-mode 1000-rank CFD completed, but the first software 1200-rank
allocation failed its startup probe before mesh setup. Its primary endpoint
allocation errors came from x1000c0s4b1n1 (Slurm tasks 292/294 and others);
other recorded nodes reported secondary PMI/allgather resets. Permit one
new 1200-rank attempt excluding only that host, with the same software mode,
verified wrapper/probe/launcher and all physics, horizon and resource limits.
Use a distinct `ml-io-1200f-wide-software-ex1-20261025` path, no fixed
tasks/node, 10–32 CPU nodes, minimum eight CPUs/node, 16000M/node, ten-minute
runtime, no requeue and 36-hour waiting deadline. A one-minute exact-rank MPI
probe still precedes all mesh work, and an afterany collector preserves results.

The hypothesis is that endpoint resources are allocation-dependent; this does
not establish a faulty host, another user's responsibility, or ordinary RAM
exhaustion. Exclusion changes placement, so report the actual hosts alongside
performance and preserve every prior failure. Stop this diagnostic sequence
if its preflight fails; do not automatically blacklist more nodes or alter
additional transport controls. Maximum nominal extra runtime budget is
200 core-hours. Pending scheduler delay is not a running allocation.

## Storage, cleanup and observables

Use a new run directory beneath
`/project/nk_meshapplied/bene/fire-track2-hpc/`. Scratch discovery found 997.3
GB used against a 1 TB soft quota and 308,793 inodes against a 300,000 soft
limit, so this exercise does not add to scratch. Project group storage had
653.4 GB used against 4 TB and 419,905 inodes against one million.
Use synchronous collated I/O with a single I/O group, binary fields and sparse
writes. Count files **and directories** before and after; aim below 100 live
entries for the exercise. Archive completed runs before the next trial if
needed, verify archives before removing only their own generated contents,
and preserve failures. Transfer selected archives/logs with `rsync`, not a
recursive per-rank field download. Collated output is not HDF5.

All mesh generation, decomposition, CFD and reconstruction run inside bounded
Slurm steps. No solver, background MPI launcher or polling daemon runs on a
login node. Slurm job/step cgroups own processes; use failure propagation and
verify terminal job/step states. Never cancel other jobs under this login.

Record module list/build, git revision/dirty state, input and executable
hashes, Slurm job/step IDs, layout, mesh checks, phase fraction, timestep and
Courant history, residual/pressure iteration history, solver/step/job wall
times, simulated seconds per wall hour, sampled/accounted memory and I/O,
requested and allocated core-hours, inode counts and output bytes. Compare
strong-scaling speedup and rank efficiency only over identical completed
steps/horizons; report 100-rank-relative efficiency and the separate allocated
CPU cost. Solver `ExecutionTime` is not aggregate MPI CPU time, iteration
counts are not pressure timing, and accounting samples can miss memory peaks.
No measured mass-conservation pass is inferred from a bounded alpha field.

W&B export is optional and local/offline until the user supplies a destination;
do not place credentials on compute nodes or upload full CFD fields.
ParaView gets a reconstructed `.foam` case, a saved state with alpha=0.5
interface and an alpha center slice. HDF5/VTKHDF is a possible compact derived
format, requiring an actual writer/reader round trip before adoption.

## Primary sources

- [Komondor OpenFOAM modules, collated I/O, MPI and CPU layout](https://docs.hpc.dkf.hu/software/openfoam.html).
- [Slurm submission](https://docs.hpc.dkf.hu/tasks/sbatch.html) and
  [file management](https://docs.hpc.dkf.hu/tasks/filemgmt.html).
- [SSH authentication and rsync](https://docs.hpc.dkf.hu/first-steps/ssh-key.html).
- Actual installed tutorial dictionaries and build banner, copied into each
  run, are the source for this exploratory case's physical inputs.
