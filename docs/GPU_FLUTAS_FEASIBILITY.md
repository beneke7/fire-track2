# FluTAS GPU feasibility for the four-slot case

**Checked:** 2026-09-25. **Decision:** the pinned base FluTAS image builds and
passes its upstream rising-bubble check on the RTX 5090. Candidate2 implements
the reviewed paired z-face source/return design, compiles to `sm_120`, and
passes ten static/analytic checks. Astra Max review found three blockers: the
zero-source dry fixture fails validation, bottom-return periodic momentum
halos are inconsistent, and the first post-shutoff transport can use stale
liquid ghosts/reconstruction. Candidate2 is preserved as blocked while a
corrected candidate is prepared. Fixed-dt runtime Courant/interface telemetry
and the full execution/analyzer contract also remain absent. No source-slot
CFD or candidate GPU runtime test has run. The GPU source-boundary and pilot
gates remain closed. The SDK, MPI stack, and solver are isolated in project
containers; no host compiler, driver, or system solver was installed or
altered.

## Host and upstream revision

The local resource doctor reports 20 effective CPUs, 119.0 GiB available RAM,
262.1 GiB free disk, and a GeForce RTX 5090 with 31.8 GiB. A direct host check
reports Ubuntu 24.04.3, NVIDIA driver 580.159.03, and 32,607 MiB GPU memory;
`nvfortran`, `nvc++`, `mpif90`, and `nvcc` are absent from `PATH`. The driver
version reported by `nvidia-smi` is not a CUDA toolkit installation.

The host compiler remains absent, but the reproducible image
`track2/flutas-nvhpc:26.9` is built locally with ID
`sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8`
(25.1 GB). It installs the checksum-pinned NVIDIA HPC SDK 26.9 archive, builds
FluTAS commit `598210616bebd51f7d51f61455f196e6f3479916` with `cc120,cuda13.3`,
and confirms an `sm_120` cubin. The recipe and run evidence are documented in
[`containers/flutas/README.md`](../containers/flutas/README.md) and
[`containers/flutas/BUILD_EVIDENCE.md`](../containers/flutas/BUILD_EVIDENCE.md).

Docker exposes its `nvidia` runtime. The local image
`nvidia/cuda:12.8.0-base-ubuntu24.04` (image ID
`sha256:e1410ea223d03afe5a3479c66c3750b8ac1c1d8d7169412a872a8edf30a67749`)
passed this device-visibility check on 2026-09-25:

```sh
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
```

It reported the host RTX 5090 and driver inside the container. This verifies
GPU device passthrough and driver-library access only; it does not compile or
launch a GPU kernel and does not establish FluTAS readiness. The invocation
matches NVIDIA's [documented Docker GPU check](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html).

The stronger `make gpu-smoke` check also passed. The target pulls the
digest-pinned development image before acquiring the shared GPU lock, then
compiles [`scripts/cuda_device_smoke.cu`](../scripts/cuda_device_smoke.cu) with
native `sm_120` code in NVIDIA CUDA 12.8.0 and verifies 1,024 outputs on the RTX
5090.
The CUDA image is pinned by OCI manifest digest in the Makefile. This establishes
that a native CUDA kernel can run in Docker on this host; it says nothing about
FluTAS's Fortran/OpenACC build, solver behavior, or source-boundary support.

The upstream repository was inspected at commit
[`598210616bebd51f7d51f61455f196e6f3479916`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/commit/598210616bebd51f7d51f61455f196e6f3479916).
Pin this commit or a later reviewed commit for any build; do not build from a
floating `main` branch. Relevant upstream files are the
[`generic-gpu` target](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/targets/target.generic-gpu),
[`INFO_INPUT.md`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/getting_started/INFO_INPUT.md),
and [`REQ.md`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/getting_started/REQ.md).
The method and published verification cases are described in the
[FluTAS paper](https://doi.org/10.1016/j.cpc.2022.108602).

## Evidence and limits

FluTAS implements incompressible two-fluid VOF with MTHINC, surface tension,
gravity, and a pressure-correction solver on a fixed, uniform Cartesian grid.
Its published verification includes Zalesak's disk, a three-dimensional
rising bubble, and a differentially heated cavity. These establish a useful
starting solver, not the high-Reynolds-number jet-in-crossflow or aircraft
configuration required here.

The upstream input documentation exposes velocity, pressure, VOF and outflow
settings per domain face. It does not document four independent rectangular
inlet patches or a time-dependent per-slot schedule. The Restás case requires
four simultaneously interacting, finite-duration water sources. That needs a
code-level source mask/time law or a demonstrated equivalent, plus per-slot
mass and vector-momentum flux accounting. Its stability with the chosen
pressure/outflow boundaries must be tested. The fixed Cartesian grid also
does not establish support for a curved aircraft body or local refinement.

Read-only inspection of the pinned [`bound.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/bound.f90)
confirms `bounduvw` applies its velocity conditions to whole physical domain
faces through `set_bc`; it does not define internal patch masks. The two-phase
driver calls [`advvof`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/vof.f90)
with the velocity fields, which are used to compute phase fluxes. **Inference
from that source structure:** an internal source cannot be qualified by merely
overwriting four velocity regions. Any extension needs review across the
pressure/momentum update and VOF phase transport, including source attribution
at shutoff. The cc120 build changes only the target flags and FFTW path; the
source extension remains a separate, unpassed gate.

The proposed post-correction source hook is incompatible with the inspected
open-outflow boundary path: it sets the top normal velocity after `outflow`
has computed a divergence-compatible value. A source-level review found a
different compatible pairing. In the pinned
[`main__two_phase_inc_isot.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/main__two_phase_inc_isot.f90#L695-L696),
`bounduvw` runs after velocity correction. With `is_outflow=true`, the
validation requires pressure D in
[`sanity.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/sanity.f90#L273-L283);
`bounduvw` then calls the outflow handler, which computes the top-face normal
velocity from tangential divergence in
[`bound.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/bound.f90#L709-L723).
Overwriting those slot values changes the top-cell divergence by
`dzfi(nz) * (w_source - w_outflow)`. The solver checks that same quantity in
[`chkdiv.f90`](https://github.com/Multiphysics-Flow-Solvers/FluTAS/blob/598210616bebd51f7d51f61455f196e6f3479916/src/chkdiv.f90#L50-L52)
and aborts when it exceeds its limit. However, an independent boundary audit
identified a supported paired-return box: both z faces use Dirichlet normal
velocity and Neumann pressure (`DD` velocity / `NN` pressure), with
`is_outflow=false`; x and y are periodic. Put masked inflow on z+ and a
stepwise volume-matched return on z−. With zero-normal-gradient pressure, the
pressure correction does not change the prescribed z-normal boundary values;
disabling the outflow flag prevents the whole-face outflow helper from
overwriting them. The return velocity must balance the discrete slot volume
flux at every step. This is a synthetic source-implementation box, not an
aircraft external-flow boundary condition.

The audit also corrected the reading of `sanity.f90:273–284`: executable
validation requires pressure D when `is_outflow=true`, but it does not require
that flag on every D-pressure face. The source/return mapping avoids D-pressure
faces. These findings are source-level, not CFD results. The implementation
still needs independent review of the exact call sites, geometric flux area,
per-slot phase/momentum flux, and per-step global/local divergence. Mixed
boundary-projector support or a justified conservative volume source remain
untested alternatives if the paired-return formulation fails.

The upstream GPU target named `-gpu=cc70,cuda11.0`, enables CUDA and OpenACC,
defines `_GPU_MPI`, and hard-codes an author-specific FFTW path. The tested
container patch changes the target to `cc120,cuda13.3` and the FFTW prefix to
`/usr`; it links the same cuFFT/cuRAND libraries. NVIDIA lists the RTX 5090 as
compute capability 12.0. Its HPC SDK 26.9 release notes document Blackwell
`cc120`, CUDA 12.9/13.3 toolchains, Ubuntu 24.04 support, and minimum CUDA 13.x
driver 580.65.06. The local OS and driver meet those platform thresholds.
See NVIDIA's [GPU capability table](https://developer.nvidia.com/cuda/gpus)
and [HPC SDK 26.9 release notes](https://docs.nvidia.com/hpc-sdk/archive/26.9/release-notes/index.html).

FluTAS is a direct-simulation-oriented implementation; its paper's turbulent
applications are not evidence of a RANS closure. The existing P0 case's
provisional source and crossflow Reynolds numbers are approximately
`7.2e5` and `5.1e5`, and its laminar setup is only a characterization. A
successful port or short run would not resolve the turbulence-model and
resolution question.

## Qualification sequence and remaining gate

1. **Passed, build gate:** the pinned `cc120,cuda13.3` image contains native
   `sm_120` FluTAS code, ran a forced OpenACC kernel and a two-rank
   CUDA-buffer MPI all-reduce on this one GPU, and passed the upstream 3D
   rising-bubble reference. The checked bubble z-centroid and z-velocity arrays
   have zero maximum difference from the checked-in reference. Evidence and
   exact commands are in [`BUILD_EVIDENCE.md`](../containers/flutas/BUILD_EVIDENCE.md).
2. **Candidate source implementation:** candidate3 implements and compiles the
   paired z-face design: normal velocity `DD`, pressure `NN`, and
   `is_outflow=false` at source and return, with x/y periodic `PP` boundaries.
   Astra Max exact-hash review accepts its repairs for the three candidate2
   defects and permits only a separate source-disabled regression. Candidate3
   passed OpenACC, CUDA-buffer MPI, and the upstream rising-bubble reference
   with no source input; this does not exercise source-boundary code. The
   run bundle lacks runtime peak RAM/VRAM samples. Candidate4 telemetry and
   behavior work plus a fail-closed analyzer/protocol remain required before
   any source execution.
   The ordinary one-sided velocity-inlet/pressure-outlet `ND`/`DN` pairing is
   unavailable on this GPU transform. Preserve alpha and material-property
   ghosts through every VOF and momentum update, instrument actual geometric
   phase flux by slot, and balance the return path each step. The source audit
   and future acceptance contract are recorded in
   [`FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md`](../experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md).
3. **Required diagnostics after telemetry and the full execution contract are
   reviewed:** run the
   quiescent dry fixture, a separate dry crossflow/gravity case, a grid-aligned
   one-slot square pulse, four symmetric slots with the same schedule, then the
   source-enabled crossflow/gravity case. The project plan's 1.0 m × 0.15 m
   slots and 0.05 m gaps may be used only as
   clearly labelled synthetic geometry until measurements are supplied.
   Independently check exact mask areas, boundary velocity, no off-slot liquid
   inflow, each slot's geometric phase-mass and vector-momentum flux, domain
   inventory, divergence, and boundary reflection/contamination during ramp,
   shutoff and post-release. Freeze tolerances before each CFD run. A reviewer
   proposed 0.1% cumulative liquid-ledger closure for the crossflow case; this
   is a candidate budget to accept or revise before execution, not an approved
   criterion or a passed result. Any unexplained residual, unstable boundary,
   or missing per-slot attribution closes the gate.

4. Only after those checks, run the planned 1–3 million-cell, few-hundred-step
   characterization pilot. Measure peak VRAM and RAM, time per step, timestep
   limit, solver time share, output cost, source fluxes, phase mass and
   divergence. Review a cost projection before attempting 5–10 million cells.

The proposed pre-run contract is in
[`FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md`](../experiments/FLUTAS_SLOT_SOURCE_BOUNDARY_GATE.md).
It remains a future acceptance contract until the candidate4 diagnostics,
exact call order, six-face boundary map, time-step fixture, residual limits,
analyzer and acceptance budgets are independently reviewed. No slot-source CFD
has run.

Any first run is solver and boundary characterization until turbulence,
resolution and E1–E3 source comparisons are separately qualified. The CPU
OpenFOAM pilot does not establish GPU readiness. Current machine evidence and
the shared compute gates are in [`COMPUTE.md`](COMPUTE.md) and
[`VALIDATION.md`](VALIDATION.md).
