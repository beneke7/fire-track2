# CaNS-Fizzy RTX 5090 benchmark

This is a compact record of a GPU solver benchmark, not a ready four-slot
simulation. It pins the upstream source, preserves the local source correction,
build settings and case input, and records the measured reference checks.

## Reproduction inputs

- CaNS-Fizzy: `c416e48105b19a673a3c419e31160b2091a29c54`
- `2decomp-fft` submodule: `dc4ce5c261adbeb131c894099434ae2518b86689`
- `cuDecomp` submodule: `eabe338cb706f68f1afe19248af001227bac538e`
- Compiler/toolkit: NVIDIA HPC SDK 26.9, CUDA 13.3, `sm_120`
- Source correction and GPU flags: [`vof-init-sm120.patch`](vof-init-sm120.patch)
- Run-specific compiler configuration: [`gpu-build.conf`](gpu-build.conf)
- Rising-bubble namelist: [`rising-bubble-input.nml`](rising-bubble-input.nml)

Apply the patch to the pinned checkout, copy `gpu-build.conf` to the upstream
root as `build.conf`, and build with `make -j8`. The local build also rebuilt
cuDecomp for compute capability 12.0 because the upstream architecture list did
not include the RTX 5090. The corrected case used one MPI rank and the upstream
THINC/QQ rising-bubble test input. The upstream test's plotting dependency was
run with Matplotlib 3.9.4 because Matplotlib 3.10 removed an API used by the
unchanged test.

## Correction and result

In the upstream THINC/QQ branch, `seps` was used by the analytic bubble
initializer but its only assignment was compiled out. The patch imports
`acdi_set_epsilon` in the VOF build and calls it before initialization. This
sets the shared grid-scaled interface width; it does not enable ACDI transport.
For this uniform-grid case, the documented input factor 0.51 gives
`seps = 0.00796875`.

The corrected build completed 6,000 steps to 3.000000000000169 s on the RTX
5090. The upstream one-way contour Hausdorff test passed at 0.00863784 against
its 0.1 limit; reverse direction was 0.01166139. The initial field contained
fractional cells and matched the declared smooth profile. Over 13 saved states,
relative phase-volume drift was `5.20e-14`; maximum divergence was
`9.86e-14`.

This check does not test an injected source, four openings, turbulence closure,
aircraft flow, a large 3D engineering case, or agreement with OpenFOAM. Its
approximately 0.44 ms per-step compute timing is not a speedup claim. The full
build log SHA-256 is
`154cd0aac1997547daf84f3599efe16164365a25df9d07db4a57ba6fab66f18d`; the log,
solver executable and 17 MB field bundle are local at
`/tmp/cans-fizzy-20260927/` and are not tracked here.
