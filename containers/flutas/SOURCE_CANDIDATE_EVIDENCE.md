# Source-boundary candidate2 build evidence

Candidate2 is a compile-and-static-check artifact for independent review. It
does not establish that the source case runs correctly, and it has not run any
source-slot solver case.

| Item | Evidence |
|---|---|
| Pinned FluTAS commit | `598210616bebd51f7d51f61455f196e6f3479916` |
| Base image | `track2/flutas-nvhpc:26.9`, `sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8` |
| Candidate image | `track2/flutas-source-boundary:5982106-candidate2` |
| Candidate image ID | `sha256:6ecfa8e248fe297782becdffba41dcd5db267768cdee0f9f724895796252e7b3` |
| Applyable source patch SHA-256 | `bd42ab7b17383ae90411aef2e0878c1427a3c3a5f49694eeb28c57659063af40` |
| Frozen case hash manifest SHA-256 | `02d1d1c96c05f72721884b7e6765d13df9b210e2773acbbbf39018772969713b` |
| Build/run metadata | [`evidence/source-candidate-runs/20260925T073740Z-1880163/metadata.txt`](evidence/source-candidate-runs/20260925T073740Z-1880163/metadata.txt) |
| Full build log | [`evidence/source-candidate-runs/20260925T073740Z-1880163/docker-build.log`](evidence/source-candidate-runs/20260925T073740Z-1880163/docker-build.log) |

The reproducible project command is:

```sh
containers/flutas/build-source-candidate.sh
```

The script verifies the local base image ID, pins the source commit, applies
[`source-boundary.patch`](source-boundary.patch), runs the Python static and
analytic suite, cleans and recompiles FluTAS with
`make -j2 ARCH=generic-gpu APP=two_phase_inc_isot`, and checks that
`cuobjdump --list-elf` reports `sm_120.cubin`. Docker was limited to two CPUs
(`--cpu-period=100000 --cpu-quota=200000`); no GPU device was requested. The
candidate image overrides the base GPU-test entrypoint with `/bin/true` to
avoid accidentally running a solver when the image is started.

Build result: exit status 0, ten static/analytic tests passed, executable linked,
and native `sm_120` code object found. The build log records the exact compiler
commands. The tests inspect source order and calculate fixture totals; they do
not execute the Fortran helper or boundary conditions. No GPU kernel, upstream
case, source-slot case, or CFD was run in this build.

The fixture has 537,600 cells. Source VOF intervals are `[2,12)` within a
14-step window; intervals 12 and 13 are post-pulse checks. A zero-slot dry case
uses `[0,0)`. Requested total-volume return is based on the exact synthetic
mask areas and source speed; actual geometric liquid flux is measured and
checked separately, without changing the projected velocity state mid-step.
Slot inputs are provisional and are not built-device dimensions. The x/y
periodic boundaries and paired z-normal DD/NN faces are diagnostic limits; this
is not an ambient open-boundary case.

Numerical acceptance thresholds are proposed in
[`SOURCE_BOUNDARY.md`](SOURCE_BOUNDARY.md), not accepted or passed. The source
boundary implementation still needs a fresh independent code/protocol review.
Only after that review and the separately frozen run protocol may a source case
be launched. No 1–3 million-cell pilot or four-slot CFD run is included here.

The earlier `candidate1` image was withdrawn after review found that it changed
the interval boundary before VOF and retuned the bottom return during VOF. Its
image and log are preserved as historical evidence under
[`evidence/source-candidate-runs/candidate1-withdrawn`](evidence/source-candidate-runs/candidate1-withdrawn).
