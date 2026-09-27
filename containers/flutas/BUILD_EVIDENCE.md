# FluTAS `cc120` build-gate evidence

Checked 2026-09-25 on the project's RTX 5090 host. This records compiler and
small solver-verification evidence only; it does not open the aerial-drop GPU
pilot gate.

The isolated build used the digest-pinned CUDA 12.8 Ubuntu 24.04 development
image and NVIDIA HPC SDK 26.9's official CUDA 13.3 installer. The installer
checksum and FluTAS source revision are in [`source-pin.txt`](source-pin.txt).
The NVIDIA SDK release notes list Blackwell support, CUDA 13.3, Ubuntu 24.04,
and a minimum CUDA 13.x driver of 580.65.06; the host driver was 580.159.03.
The SDK installed `nvfortran 26.9-0`, the matching OpenMPI/HPC-X wrappers,
cuFFT, and cuRAND without modifying host packages or drivers.

The pinned upstream `two_phase_inc_isot` app compiled with `make -j2
ARCH=generic-gpu APP=two_phase_inc_isot`. The only source change was the
two-line target patch: replace the author-specific FFTW prefix with `/usr` and
replace `-gpu=cc70,cuda11.0` with `-gpu=cc120,cuda13.3`. Compilation completed
successfully. `cuobjdump --list-elf` reported
`pgcudafat0XjCb6Q8fUx.sm_120.cubin` in the final recipe-built FluTAS
executable. The project-owned Dockerfile then rebuilt the image from the
pinned base, installer checksum, source commit, and target patch with a
two-CPU CFS quota. The built image is available locally as
`track2/flutas-nvhpc:26.9`; its image ID is
`sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8`
(25.1 GB).

GPU execution used `python3 scripts/run_local.py --gpu` with `--threads 1` for
the device smoke and `--threads 2` for MPI and solver attempts, so each kernel
or solver attempt held the documented shared GPU lock. `nvaccelinfo`
reported an NVIDIA GeForce RTX 5090 with device revision 12.0. The forced
OpenACC smoke produced 1,024 correct outputs. Two MPI ranks each allocated
CUDA device buffers and `MPI_Allreduce` returned 3 on both ranks from inputs 1
and 2; both ranks shared this single physical GPU.

The upstream 3D rising-bubble example ran on one GPU rank with its checked-in
32 × 32 × 64 grid. It completed 1,680 steps to 3.0015205269 s in 16.07 s wall
time in the standalone probe (11.208 s reported by the final recipe image for
its step loop; the full packaged gate completed in 21.0 s). The upstream
`test_bub.test_answer()` passed (`True True`); the loaded z-centroid and
z-velocity arrays had zero maximum difference from the checked-in reference.
The final reported maximum velocity divergence was about 3.33e-15. The run
printed 697,827,328 bytes as used solver memory; this is not a sampled peak
VRAM measurement. Full final run output is retained under
[`results/runs/flutas-gpu-gate-20260925T054056Z-C3DL0J/`](../../results/runs/flutas-gpu-gate-20260925T054056Z-C3DL0J/).

The first MPI launch failed before the solver started because the base image
lacked `libnl-route-3.so.200`. The exact launcher error is retained in
[`evidence/first-launch-failure.log`](evidence/first-launch-failure.log).
Installing Ubuntu package `libnl-route-3-200` in the container fixed launch;
that dependency is included in the recipe. An initial attempt to invoke the new
host runner also returned `Permission denied` before starting Docker because
its executable bit was not set. The build and runner scripts were marked
executable before the packaged test run; neither failed attempt is counted as
a solver pass. The runner invocation is recorded in
[`evidence/runner-mode-failure.txt`](evidence/runner-mode-failure.txt).

This establishes a native `sm_120` FluTAS build, one-GPU VOF execution, and a
small same-device CUDA-buffer MPI collective. It does not establish scaling to
multiple GPUs, the published bubble's numerical accuracy beyond the upstream
check, aircraft/source support, four-slot conservation, turbulent physics,
E1–E3 agreement, E4–E5 ground evidence, an affordable 1–3 million-cell pilot,
or any Restás ground-strip result. Do not advance the planned pilot until the
separate case and boundary requirements in [`docs/GPU_FLUTAS_FEASIBILITY.md`](../../docs/GPU_FLUTAS_FEASIBILITY.md)
are reviewed.

The supporting current NVIDIA primary sources are the [26.9 release notes](https://docs.nvidia.com/hpc-sdk/archive/26.9/release-notes/index.html),
[26.9 download page](https://developer.nvidia.com/hpc-sdk/releases/26.9),
[Linux installation guide](https://docs.nvidia.com/hpc-sdk/installation-guide/index.html),
[26.9 container guide](https://docs.nvidia.com/hpc-sdk/archive/26.9/container-guide/index.html),
and [26.9 NGC catalog](https://catalog.ngc.nvidia.com/orgs/nvidia/-/containers/nvhpc). The official catalog currently exposes a 26.5 devel image; the tested 26.9 devel tag was absent, which is why this recipe installs the official 26.9 archive into the pinned CUDA base.
