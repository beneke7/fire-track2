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
