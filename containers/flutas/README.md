# Pinned FluTAS `cc120` build and GPU smoke

This container recipe builds the upstream FluTAS two-phase VOF application at
the commit in [`source-pin.txt`](source-pin.txt). It applies a two-line local
GPU target patch: native `cc120`/CUDA 13.3 code generation and the container's
FFTW prefix. The NVIDIA HPC SDK installer and CUDA base image are pinned by
SHA-256/OCI digest; direct Ubuntu package versions used by the build are pinned
in the Dockerfile.

Build with a two-CPU cap:

```sh
containers/flutas/build-image.sh
```

Run the forced OpenACC kernel, a two-rank MPI all-reduce over CUDA device
buffers, and FluTAS's upstream 3D rising-bubble reference check through the
project GPU-lock launcher:

```sh
containers/flutas/run-gpu-gate.sh
```

The runner creates a new directory under `results/runs/` for every attempt. It
keeps the compiler report, device report, `sm_120` code-object list, test logs,
and upstream case output there. Set `FLUTAS_GPU_IMAGE` to build or run a
different local image tag.

The upstream bubble case is a 32 × 32 × 64, single-rank solver verification.
It is not an aerial-drop case, the 1–3 million-cell characterization pilot, or
evidence for four-slot sources, aircraft boundaries, benchmark validity,
field performance, or the 15–30 second scientific render. See
[`BUILD_EVIDENCE.md`](BUILD_EVIDENCE.md) for the executed results and remaining
gates.

An unapproved, synthetic source/return boundary patch is documented in
[`SOURCE_BOUNDARY.md`](SOURCE_BOUNDARY.md), with the separate image recipe and
build evidence in [`SOURCE_CANDIDATE_EVIDENCE.md`](SOURCE_CANDIDATE_EVIDENCE.md).
Its build and static checks do not execute the source solver or a source-slot
case.

After an independent exact-hash review accepts a source candidate, its first
GPU trial is a **source-disabled** regression only. Invoke
[`run-candidate-gpu-regression.sh`](run-candidate-gpu-regression.sh) with the
image reference, expected immutable image ID, and expected SHA-256 for the
candidate patch embedded in that image. For example:

```sh
image_ref=track2/flutas-source-boundary:reviewed
image_id="$(docker image inspect --format '{{.Id}}' "$image_ref")"
candidate_patch=/path/to/reviewed/source-boundary.patch
candidate_patch_sha256="$(sha256sum "$candidate_patch" | awk '{print $1}')"
containers/flutas/run-candidate-gpu-regression.sh \
  "$image_ref" "$image_id" "$candidate_patch_sha256"
```

The runner checks that the image reference resolves to the expected immutable
ID. Under the shared GPU lock, it verifies `/tmp/source-boundary.patch` inside
that exact image against the supplied hash and copies the verified patch into
the new evidence bundle. It explicitly invokes
`/usr/local/bin/flutas-gpu-tests` despite the candidate image's `/bin/true`
entrypoint, and checks that the copied upstream rising-bubble input contains no
`source-boundary.in`.

The attempt must include successful OpenACC and two-rank GPU-buffer MPI
markers, an `sm_120.cubin`, normal solver completion (`*** Fim ***`) without
solver error/abort/fatal output, a finite last timestep of at least 3.0 s, and
the upstream verification result `True True`. It also requires at least one
parseable finite GPU sample and one parseable finite container CPU/memory sample.
Sampler diagnostics remain in `resource-sampler-errors.log`. Resource extrema
are sampled maxima/minima at about 1 Hz, not exact hardware peaks. Each attempt,
including failures, gets a fresh directory and SHA-256 manifest under
`results/runs/`.

This remains a source-disabled upstream regression and does not qualify the
candidate source boundary. The quiescent-to-source case sequence still
requires its reviewed diagnostics, limits, analyzer, and execution contract.
