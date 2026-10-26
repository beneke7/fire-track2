# Local compute procedure

Formal compute gates follow the [experiment plan](../track2_aerial_drop_experiment_plan.md).
The user has separately authorized exploratory runs on idle local CPU/GPU
capacity, including short physical VOF, AMR, turbulence, profiling and rendering
trials, without per-run Astra/Warden approval. Keep provisional inputs and
exploratory status explicit; this does not pass a scientific gate. Check other
workloads first and use available capacity without a fixed CPU reserve or rigid
per-run cap. Avoid routine resource negotiation; workers coordinate when an
active long run materially delays assigned work or observed pressure affects
responsiveness. Serialize GPU jobs through the lock. The prior failed
`dry_four` bundle remains immutable; distinct experiments are allowed and must
write new case/run directories.

## Inspect the host

Run `make doctor` after `make setup`. The doctor uses the standard library and reports the
Python interpreter and selected package versions, logical CPUs and affinity, cgroup CPU and
memory limits, available RAM, free disk, NVIDIA device memory, and commonly needed tools.
The JSON report is written to `results/machine.json`; use
`.venv/bin/python scripts/doctor.py --json` to print JSON or
`.venv/bin/python scripts/doctor.py --output PATH` to save a report elsewhere. These values are a
snapshot, so rerun the doctor before scheduling a substantial job.

The CL415 launch doctor inspection on 2026-10-01 found a Linux x86-64 host with CPython 3.12.3, 20 CPUs in process
affinity, 121.4 GiB of available RAM, and 717.4 GiB free on the working filesystem.
The retained snapshot is `results/runs/cl415-halfsecond-priority-20261001T165200Z/machine.json`;
these are launch-time readings, not standing resource guarantees.
An RTX 5090 with 32 GB is visible through `nvidia-smi`; driver 580.159.03 reports CUDA 13.0.
The host has no `nvcc`, host OpenFOAM, FluTAS, or SU2. Docker is available and contains
`opencfd/openfoam-default:2512`, a GCC CPU image with `interIsoFoam`, `interFoam`,
`blockMesh`, `checkMesh`, `decomposePar`, `mpirun`, `reconstructPar`, and `foamToVTK`. The
image was probed on this machine, and the image ID is recorded in each run bundle. It does
not use the RTX 5090 or pass a benchmark. The driver’s reported CUDA version is not an
installed host CUDA toolkit. No finite CPU quota or cgroup memory limit was detected. A
separate digest-pinned container now builds FluTAS with NVIDIA HPC SDK 26.9 for `cc120` and
passes its OpenACC kernel, CUDA-buffer MPI, and upstream rising-bubble checks. The container
does not install a compiler on the host. The latest doctor still reports GPU VOF as not ready
because the candidate-specific source-boundary gate has not passed.

## Current CPU VOF pilot

`make restas-pilot` runs the four-slot characterization case in
[`cases/restas_four_slot/`](../cases/restas_four_slot/), as declared in
[`experiments/P0_RESTAS_CPU_VOF.md`](../experiments/P0_RESTAS_CPU_VOF.md). It creates a new
run directory under `results/runs/`, checks a 2.08-million-cell mesh, then runs up to 16 MPI
ranks inside an 18-CPU Docker cap and a 48 GiB memory limit. It writes sparse VOF interface
surfaces and a water-volume time series. The launcher applies a one-hour wall-time limit.
Three cells across the slot width, laminar flow, the short time window, and the missing
aircraft/ground mean this is a software and boundary-condition characterization only. It
cannot establish physical breakup or useful-strip performance. The earlier
one-second still-air case also discharged vertically downward; it is retained as
an exploratory software run and does not represent the horizontal outlet
orientation now specified by the user. New horizontal cases are being prepared.

The runner samples Docker memory and CPU use approximately every two seconds. Peaks between
samples may be higher; use these measurements for rough cost estimates only. The first run
used 16 ranks for 975.6 s of wall time (0.443 simulated seconds per wall hour), sampled a
5.55 GiB peak, and reached 0.12 s. Treat that throughput as a preliminary scale estimate,
not a forecast for refined physics, more cells, or different boundaries.

That run's 2,081,200-cell mesh passed `checkMesh`. Its cumulative continuity error peaked at
2.17e-7, and the water-volume inventory plateaued at 0.231019 m³ versus the rectangular
source integral of 0.2304 m³ (+0.269%). The excess appeared at the discrete 0.08 s source
cutoff. No acceptance tolerance had been registered before launch, and the case did not save
per-patch liquid-flux histories, so this is a discrepancy to investigate rather than a
conservation pass. Logged peak Courant numbers were 0.542 global and 0.293 interface, above
the configured 0.5 and 0.25 controls. The flow completed without a fatal error, but those
limit exceedances also need resolution in a follow-on case. See the run's `pilot-report.json`;
the bundle name is recorded in
[`docs/STATUS.md`](STATUS.md).
Pressure-solver iteration counts were logged, but pressure-solve time share and filesystem
I/O/checkpoint time share were not instrumented. The wall throughput is not enough to size a
larger pilot without those cost components.
The compact evidence summary and rendered frame are in
[`results/P0_RESTAS_CPU_VOF.md`](../results/P0_RESTAS_CPU_VOF.md).

## P1 source-event and liquid-ledger diagnostic

The source/mass contract is in
[`experiments/P1_SOURCE_EVENT_LEDGER.md`](../experiments/P1_SOURCE_EVENT_LEDGER.md).
Its independent scientific review confirmed that OpenFOAM 2512 `interIsoFoam`
registers isoAdvector's in-memory `alphaPhi_` field for per-patch logging. The
case records the conservative phase-1 step flux on all four source patches and
all open box boundaries, plus the domain integral of `alpha.water`; it uses a
fixed 0.1 ms step to resolve the 1 ms source ramp. Under the approved P1
revision-2 sampling convention, `alphaPhi_` is left-endpoint sampled and its
expected dose is 230.544 kg; the `phi` volume-flux dose is right-endpoint
sampled and expected to be 230.256 kg. Both are reported separately from the
continuous analytic target of 230.4 kg. The contract also includes
cumulative-source ledger limits and hard Co stop thresholds.

`make prepare-source-ledger` creates and hashes an immutable P1 case without
launching OpenFOAM. Astra Max prospectively reviewed the complete current
Makefile target and six-file launch path, and the execution record now pins
those exact hashes. Five focused test modules passed (59 tests); the real
contract accepts its frozen limits and rejects a stale hash; regenerated case
inputs match the accepted revision-2 manifest; and the local OpenFOAM image
matches the recorded image ID. `make restas-source-ledger` is ready for an
optional replay, but the completed revision-2 evidence requires no rerun.
When used, the launcher allows 16 MPI ranks, 48 GiB and one hour; a live log
monitor stops at the first Co or interface-Co breach. P1 is a source and
mass-accounting diagnostic on the unchanged coarse P0 mesh, not a breakup or
design-validation run.

## Launch local commands

Use this interface for compute commands:

```text
.venv/bin/python scripts/run_local.py [--threads N] [--gpu] [--timeout SECONDS] -- COMMAND ARGS
```

For example, the analytical E0 command is launched by `make e0`. A direct invocation can
look like:

```bash
.venv/bin/python scripts/run_local.py --threads 1 -- .venv/bin/python -m aerial_drop.e0
```

The launcher passes the command and arguments directly to a child process without a shell.
By default it sets common OpenMP and BLAS thread variables to the full effective CPU budget
reported by affinity and cgroup limits. An explicit `--threads N` can select a smaller
starting allocation. Workers coordinate directly only when an active long run materially
slows another assigned task or observed resource pressure affects responsiveness. The
launcher changes child environment variables only; it does not alter the current shell or
system configuration, and its thread setting is not a hard CPU quota for tools that ignore
those variables.

Pass `--gpu` for any command that uses the local GPU. The launcher takes a Linux `flock`
under `/tmp`, keyed by user ID, so local GPU jobs launched from separate worktrees by that
user wait for one another. The lock is active regardless of the selected CPU thread count.
This coordinates the project’s local invocations; it does not reserve GPU memory or
coordinate other users and schedulers. The option only serializes launchers; it does not
enable GPU support in a solver.

`--timeout SECONDS` applies to the command process group; on expiry, the launcher sends a
termination signal, then kills remaining group members if necessary, and returns status
124. Ctrl-C and SIGTERM also stop the command process group before releasing the GPU lock;
the launcher returns 130 for Ctrl-C and 143 for SIGTERM. Otherwise, it forwards the
command’s exit status. No timeout is set unless requested.

## Advance through compute gates

1. **CPU characterization:** review P0's mesh report, source-volume discrepancy, time-step
   history, solver residuals, interface output, and resource samples. P1 adds reviewed
   source-event and conservative phase-ledger diagnostics; it must pass those criteria
   before any mesh refinement. Neither P0 nor P1 establishes breakup accuracy.
2. **GPU source-boundary qualification:** the pinned base FluTAS image passed its
   OpenACC, CUDA-buffer MPI, and upstream rising-bubble checks on the RTX 5090.
   Candidate2's paired z-face implementation compiled and passed ten
   static/analytic checks, but Astra Max found three blockers: dry input
   validation aborts, the return-plane periodic momentum halos are inconsistent,
   and the first post-shutoff transport can use stale phase ghosts/reconstruction.
   Candidate2 is preserved as blocked. Candidate3 repairs those code defects;
   Astra Max reviewed its exact hashes and permitted only a separate
   source-disabled GPU regression. That regression passed on the immutable
   candidate3 image in
   [`candidate3 evidence`](../results/runs/flutas-candidate-gpu-regression-20260925T083856Z-1977448/).
   The run did not sample runtime peak RAM/VRAM and makes no resource-scaling
   claim. No source CFD has occurred. Candidate4 is frozen, built and
   exact-reviewed for one bounded source-disabled GPU regression only. That
   regression passed through `3.001520526915884 s` on the immutable image;
   evidence is in
   [`candidate4 evidence`](../results/runs/flutas-candidate-gpu-regression-20260925T095317Z-2015705/).
   Candidate4 adds measured Courant/interface diagnostics, clarified audit rows
   and host behavior tests; the smoke does not qualify source-on behavior. The
   exact disposition is in
   [`candidate4 review`](../containers/flutas/candidate4/INDEPENDENT_REVIEW.md).
   Keep source CFD gated by a reviewed analyzer, frozen limits, input identity
   and launch contracts. The current frozen positive sequence is quiescent
   `dry_four` → one-slot → four-slot. The unchanged `dry_crossflow` and
   `crossflow_four` fixtures fail the frozen U0 timestep guard and are expected
   negative checks, not executable runtime stages. Positive crossflow requires
   a prospective reviewed protocol amendment; do not rerun the known guard
   rejection on the GPU.
   See the [FluTAS feasibility record](GPU_FLUTAS_FEASIBILITY.md)
   and [`FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md`](../experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md).
3. **GPU pilot:** on a compatible implementation, run an idealized 1–3 million-cell box
   for a few hundred steps. Record peak VRAM and RAM, time per step, time-step limit,
   interface and mass error, pressure-solver share, and output cost. Check the inlet and
   crossflow behavior before extrapolating. Follow the plan’s E1–E3 requirements before
   treating nearfield outputs as benchmarked.
4. **Extrapolation:** estimate wall time to one physical second, memory, and checkpoint
   size from measured pilot data. Attempt 5–10 million cells only if the measured cost and
   boundary behavior support it. Compare at least two nearfield resolutions and add a
   third when penetration, transfer flux, or `L95` remains sensitive.
5. **CPU and cluster work:** run CPU references and post-processing against the actual
   shared load; do not hold a fixed workstation reserve or renegotiate allocations routinely.
   Workers coordinate if a long-running job materially slows assigned work, and adjust for
   actual responsiveness, memory, disk, or solver-stability issues. Use one thread within
   process-parallel sweeps to prevent nested oversubscription. Before relying on the later
   CPU cluster, profile a short partition, memory per rank, and MPI scaling. Cluster
   availability is not implied by the plan.

For every scientific run, use the project experiment record and preserve inputs, revision,
mesh, time-step settings, resources, conservation errors, checkpoints, and the advance or
stop decision. Keep full 3D fields sparse; routinely save compact flux and ground-map
products. Follow the validation and stop conditions in the experiment plan before making
any design or field-performance claim.

## Komondor access verified 24 October 2026

The later 10,099,265-cell Komondor case uses stock native interIsoFoam v2512.
Its measured 64/120/240/300-rank comparisons and one-node fixed-0.1 ms trial
are in [HPC_RUN_METRICS.md](HPC_RUN_METRICS.md); the 35.19M sizing bracket
below is earlier guidance, not the selected mesh or a measured optimum.
Compact published measurements are in the
[26 October evidence bundle](../results/summaries/rouaix_hpc_20261026/README.md).

Archive-failure limit: if final packing/verification fails on node-local
storage, the runner retains its workspace but has no durable fallback copy.
That path can disappear at allocation teardown. All reported result archives
were verified; future node-local runs need a durable failure-recovery path.

SSH as `nk_memj@komondor.hpc.kifu.hu` is working. The CPU partition and native
`OpenFOAM/v2512-DP32-Gcc-CRAY-MPICH` module were inspected; the latter supplies
`interIsoFoam` build `_87ed40d256-20251219` and stock tutorials. Load
`openfoam` then the versioned module and follow the site's `source $FOAM_BASH`
command (the variable contains source arguments). Use the native Cray MPICH
environment and Slurm `srun`, not the workstation Docker launcher.

The first bounded tutorial/scaling protocol is
[`HPC_P0_KOMONDOR_TUTORIAL.md`](../experiments/HPC_P0_KOMONDOR_TUTORIAL.md).
Recheck `squota`, `sbalance`, `squeue`, and association limits before launching.
On 25 October the project inode quota blocked new files; the bounded native
mesh check therefore uses explicitly checked scratch capacity. Neither
filesystem is assumed to have quota headroom. Distinguish active MPI ranks from allocated/billed CPUs and
leave unrelated account jobs untouched. Authentication may require interactive
EduID acknowledgement; use a short-lived SSH control master for repeated
inspection and `rsync`. Do not alter global SSH settings or copy credentials.

Performance analysis uses `scripts/hpc_metrics.py --run LABEL=solver.log
--ranks LABEL=N --launcher LABEL=launcher.log --sacct LABEL=job.sacct
--output new-report.json`. Repeat the inputs for each run and add
`--baseline n100` for the matched scaling sweep. The parser separates the
high-resolution Slurm solver-step envelope, OpenFOAM's rounded `ClockTime`,
full-job elapsed time, measured CPU time and allocated CPU-hours. Pressure
iteration counts are not pressure timing. Per-step histories and scalar
summaries can be sent to W&B with explicit `--wandb-project` and optional
`--wandb-entity` after a destination and credentials exist; otherwise JSON
generation is offline and requires no W&B dependency. The HPC default Python
is 3.6.8; this parser requires Python 3.11, available via
`module load cray-python/3.11.7`.

The current v2512 case uses synchronous native collated files, with one writer
group to minimize inodes. Installed v2512 binaries/source did not demonstrate
HDF5 solver I/O; a system HDF5 library alone does not supply a compatible
OpenFOAM file handler. More collated writer groups may reduce I/O gathering
cost but increase file counts, so measure before changing the sparse-write
test. [Upstream OpenCFD v2606 adds VTK-HDF export tools](https://www.openfoam.com/news/main-news/openfoam-v2606/plugins); they were not adopted
for these v2512 runs. The local ParaView exporter was tested separately and
has data-type and field-name limits documented in
[`HPC_VISUALIZATION.md`](HPC_VISUALIZATION.md).

Keep persistent HPC files packed: one input archive and one result archive per
attempt, plus the batch script and scheduler log. Prefer verified node-local
temporary storage for unpacked work; use a bounded scratch workspace only
when local storage is unavailable or insufficient. Verify archive membership,
gzip integrity and SHA-256 before deleting only the attempt's owned workspace.
Keep failed attempts as compact archives. Count directories as well as files;
aim below 100 persistent entries for this experiment. A running OpenFOAM case
requires multiple files, so do not add a custom filesystem or solver format
to force one inode. For longer runs, retain sparse collated checkpoints on
durable storage because node-local data is lost with the allocation.
On 25 October, closed historical metadata was reduced from 123 loose entries
to one archive plus an index, with a verified local backup before removal.
Project EDQUOT prevented even an archive inode, so this 713 kB archive and
79 kB index remain in a dedicated HPC HOME backup directory. This tiny metadata
exception does not place simulation fields in HOME. Total current owned HPC
entries are 73 across project, scratch and that backup; see
`results/runs/komondor-inode-pack-20261025/` for the exact inventory.

## Choosing ranks for long VOF runs

Choose ranks from representative post-startup physical-time throughput on the
actual case. The 25 October 2.322M-cell, 50-step tutorial makes this distinction
important: 64 ranks finished the entire job fastest, but steps 11–49 at 300
ranks advanced about twice as fast as at 64. These rounded-clock, early-flow
windows do not predict the 35.19M-cell Rouaix case. The raw window calculation
and quantization bounds are in
`results/runs/komondor-long-horizon-sizing-20261025/throughput-sizing.json`.

For each rank count P, measure v(P) = physical seconds advanced / wall seconds
in a matched, representative window. Estimate runtime as setup/startup +
remaining physical horizon/v(P) + measured checkpoint/output costs + final
processing. Add queue time separately for time-to-result; queue time is not
billed as allocated compute. CPU cost is actual AllocCPUs times allocated job
wall seconds / 3600, which can differ from active MPI ranks on full nodes.
Use phase-specific rates when interface complexity, AMR, timestep or pressure
iterations change. Keep numerical tolerances, timestep policy, transport mode,
outputs, mesh and sampled physical windows matched; validate stability and
source/ledger observables rather than optimizing a compromised solution.

For the actual 35.19M mesh, 300–600 active ranks is a starting pilot bracket,
not a selected optimum. Include the three-node 300/360-rank target and nearby
node-aligned points; Komondor suggests 120 active ranks per full 128-core CPU
node. Verify AllocTRES and memory before cost comparisons. The external
[Pawsey heuristic](https://pawsey.atlassian.net/wiki/spaces/US/pages/51925980)
of about 60k cells/rank is a starting estimate from another system, not a
universal VOF rule. A one-node lower-rank memory qualification may precede
the larger pilots. No new CFD jobs are armed by this sizing guidance.

## Historical CPU-cluster scaffold, 20 October 2026


This pre-access scaffold records the 20 October assumptions. Verified Komondor
configuration and the later stock-solver experiments are described above.
At that time the cluster was reported to use Slurm and have OpenFOAM preinstalled. Its
OpenFOAM release, compiler, MPI implementation/Slurm plugin, node layout,
memory limits, scratch policy, wrapper conventions and checkpoint signal
behavior are not confirmed. The expected allocation is about 1,300 CPU cores
and 1–2 million CPU-hours. No cluster access, job submission, native MPI launch
or case run has been tested. `scripts/run_local.py` is a workstation thread
limiter, not a Slurm backend.

The 20 October workstation Rouaix water diagnostic used a **custom** `interIsoFoamTracePair`
solver derived from OpenFOAM's interIsoFoam and a custom
`traceNormalHeadPressure` boundary condition. It is not interchangeable with
stock `interIsoFoam` or `prghTotalPressure`. The locally captured overlay is
staged by `scripts/cluster/package_solver.py`; its manifest records the custom
source files, local reference-binary hash, local OpenFOAM image identity and
build/launch evidence. The local binary is provenance only; do not assume its
ABI or MPI compatibility on the cluster. Build against a confirmed compatible
site OpenFOAM API and MPI, then record the cluster-built binary hash in the job
config. Stop if the site version requires code changes until those changes
are diffed, hashed and tested; do not silently substitute a stock solver.

The staged review bundle at
`results/runs/cluster-solver-stage-20261020-provenance/` captured 49 source and
Make input files. Its package-defined digest is
`6f3e4d51333ff7cd0bec983f6f6f9aef90d74d0f09a3241ea5c01dd9368309ca`; the
reference binary SHA-256 is
`939c48415e54f222501a9c44abd23094d5e1e083ac93f5ed9870cdda61f2f739`, built in
local image `sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`.
The manifest hashes each captured file and computes SHA-256 over sorted
relative POSIX paths encoded as a 4-byte big-endian length plus UTF-8 path plus
the raw 32-byte file SHA-256. It is the digest of this staged inventory, not a
claim that every previous run used the same manifest algorithm or file set.

Use the parameterized scaffolder only after replacing every site placeholder:

```bash
.venv/bin/python scripts/cluster/package_solver.py \
  --source-root /path/to/diagnostic-source \
  --binary /path/to/diagnostic-source/bin-replay/interIsoFoamTracePair \
  --evidence-root /path/to/replay-run \
  --local-image-id sha256:local-build-image-id \
  --output /path/to/new/solver-stage
.venv/bin/python scripts/cluster/slurm_scaffold.py validate \
  --config /path/to/site-config.json
.venv/bin/python scripts/cluster/slurm_scaffold.py render \
  --config /path/to/site-config.json \
  --output-dir /path/to/new/generated-jobs --dry-run
```

Copy `scripts/cluster/example-config.json` to a new site config and replace its
placeholders. The example intentionally fails validation until a site version,
partition, memory request and **site-built executable hash** are supplied.
The generator writes reviewable `smoke`, `scaling` or `production` Slurm
scripts and a resource-arithmetic manifest; it never calls `sbatch`. It
requires one CPU per MPI task and checks ranks × nodes against the configured
core allocation. It caps the sum of configured job CPU-hours at the conservative
1-million-hour budget bound until the final allocation is confirmed.
`site_wrapper_example.sh` documents the wrapper interface and
checks the actual solver binary SHA-256, `foamVersion`, and every staged source
file against the manifest before launch. The example's `srun --mpi` choice and
checkpoint-stop adapter are site responsibilities, not verified defaults.

For a configured smoke script, export its paths explicitly when submitting,
for example:

```bash
sbatch --export=ALL,FIRETRACK2_CASE=/scratch/project/new-case,\
FIRETRACK2_CLUSTER_WRAPPER=/scratch/project/site-wrapper,\
FIRETRACK2_SOLVER_BIN=/scratch/project/solver/bin/interIsoFoamTracePair,\
FIRETRACK2_STAGING_MANIFEST=/scratch/project/solver/staging-manifest.json,\
FIRETRACK2_SLURM_MPI_TYPE=site-verified-plugin,\
FIRETRACK2_CHECKPOINT_STOP_ADAPTER=/scratch/project/write-stop-adapter \
/path/to/generated-jobs/rouaix-smoke.sbatch
```

Those names and the plugin token are interface examples, not site configuration.
First check the site's `foamVersion`, compiler and MPI. Then run a one-rank
startup and a small multi-rank smoke with the site's documented native MPI
integration. Slurm `srun` and OpenFOAM MPI must agree on PMI/PMIx; Apptainer's
MPI modes also require matching host/container MPI support ([Apptainer MPI
guide](https://apptainer.org/docs/user/main/mpi.html)). The example wrapper
requires a site-owned pre-timeout adapter. It must be tested to checkpoint all
solver ranks and stop cleanly when the generated `USR1` warning arrives; the
scaffold does not assume a portable OpenFOAM signal handler. Set each segment's
end time at a known saved checkpoint, retain native OpenFOAM restart fields,
and resume from the verified latest time in a new immutable case copy. Do not
let an unhandled scheduler timeout be the checkpoint plan.

After startup succeeds, measure same-checkpoint strong scaling at site-feasible
rank counts, for example 20/40/80/160, recording simulated-time throughput,
CPU time, `MaxRSS`, checkpoint and I/O cost. The present 2,733,120-cell mesh
would average only about 2,100 cells per rank at 1,300 ranks, so full-allocation
scaling is unknown and should not be assumed. Request memory per node from a
smoke measurement, not a guessed workstation ratio. Use Slurm accounting when
available:

```bash
sacct -j "$JOB_ID" --parsable2 --noheader \
  --format=JobIDRaw,JobName,State,ExitCode,ElapsedRaw,AllocCPUS,TotalCPU,MaxRSS,ReqMem,AllocTRES
```

For the job row, allocated CPU-hours are `ElapsedRaw × AllocCPUS / 3600`; use
`TotalCPU` separately as measured CPU consumption and `AllocTRES`/site billing
fields when the scheduler exposes them. Do not sum the parent job and all
step rows together. Preserve the selected native mesh, dictionaries, field
prefix, exact source ledger offset and per-file hashes. Use `rsync` to a fresh
incoming directory (no `--delete`), verify a relative-path SHA-256 inventory
at both ends, and only then rename that directory to its immutable run name.
Never transfer workstation `/dev/shm` paths as durable state.

For example, from the workstation, build the checksum list relative to the
bundle root and transfer only into a new cluster incoming path:

```bash
BUNDLE=/path/to/solver-and-case-bundle
HOST=user@cluster
INCOMING=/scratch/project/.incoming/rouaix-smoke-001
FINAL=/scratch/project/runs/rouaix-smoke-001
(cd "$BUNDLE" && find . -type f ! -name TRANSFER.sha256 ! -name TRANSFER.sha256.sha256 \
  -print0 | sort -z | xargs -0 sha256sum > TRANSFER.sha256 && \
  sha256sum TRANSFER.sha256 > TRANSFER.sha256.sha256)
ssh "$HOST" "mkdir -p '$INCOMING' && test ! -e '$FINAL'"
rsync -a --partial --info=progress2 "$BUNDLE/" "$HOST:$INCOMING/"
ssh "$HOST" "cd '$INCOMING' && sha256sum -c TRANSFER.sha256.sha256 && \
  sha256sum -c TRANSFER.sha256 && test ! -e '$FINAL' && mv '$INCOMING' '$FINAL'"
```

If interrupted, resume only into the same `.incoming` path; never sync over a
completed run or use deletion flags. Regenerate and compare checksums after any
intentional bundle edit.

Native OpenFOAM decomposed fields and restart dictionaries remain authoritative.
HDF5 is a heavy optional analytics/export format here; this scaffold neither
installs HDF5 nor assumes OpenFOAM reads/writes it. Keep any HDF5 products
derived, separately versioned and checked against native fields. W&B is not a
dependency and no upload is performed; once the cluster project is configured,
an optional offline tracker may store scalar metrics and pointers/hashes to
large files rather than field payloads.

Begin with a bounded stability smoke and the exact solver/source checks, then
scale from the same checkpoint. A larger allocation is useful only after
solver, restart, conservation and resource behavior are demonstrated; none of
these exploratory cluster jobs is an E1 validation pass or field-performance
claim. Slurm resource syntax is site-dependent; see the upstream
[sbatch](https://slurm.schedmd.com/sbatch.html) and
[sacct](https://slurm.schedmd.com/sacct.html) references.
