# Current VOF trials and solver choice

**Decision:** keep OpenFOAM CPU as the near-field reference and continue GPU
evaluation with matched benchmark cases. Do not start a custom RTX 5090 solver
yet. The current evidence establishes one exploratory four-slot CPU run and a
separate GPU solver benchmark; it does not establish GPU acceleration for the
pipe case or validated breakup physics.

## Four-slot still-air CPU run

Run `restas-still-air-20260925T161158.078698Z-b5d19c1c` completed at 1.0 s with
OpenCFD OpenFOAM 2512 `interIsoFoam`. It used 1,640,760 cells in a 10 m domain,
16 MPI ranks under an 18-CPU and 48 GiB cap, and took 18,218.6 s (about 5.06 h).
It models water and air, gravity, surface tension and realizable k-epsilon RANS.
The four 1.0 × 0.15 m slots, 0.05 m gaps, 4.8 m/s outlet speed, turbulence
inputs, and source pulse are provisional. Aircraft, rotor and ambient wind are
omitted by the chosen still-air setup. There are six cells across each slot's
short axis, so the mesh cannot establish resolved breakup.

`checkMesh` passed. The logged maximum Courant and interface Courant numbers
were 0.12974 and 0.06681 against declared maxima of 0.5 and 0.25. The maximum
cumulative continuity error was `7.82e-8`. The minimum logged water fraction
was `-1.83e-6`; the solver also bounded the RANS `k` field 7,354 times. These
numerical details warrant refinement and sensitivity checks before a physical
interpretation.

The time-sampled source dose was 230.544 kg, including the left-endpoint
sampling convention; the nominal rectangular pulse is 230.4 kg. Final water
inventory was 224.891961 kg and accumulated open-boundary outflow was
5.652042636 kg. Their ledger residual was `-3.64e-6 kg`, with maximum relative
residual `2.61e-8`; the sampled ledger and source dose meet the run's 0.1%
diagnostic tolerance. This is numerical mass accounting, not validation.

The local immutable run bundle is
`results/runs/restas-still-air-20260925T161158.078698Z-b5d19c1c/`. Its inputs,
manifest, report and ledger-summary SHA-256 values are respectively
`ae64fddb85c322fc4bd783fc399e486b9c46d9b464c2d78fa59926a9b462e007`,
`8bf2678ddfb538a1c752f730d7fb4b134de0fe3dbfb1eb3f1cda2af052e11ddb`,
`0063c4a685a5e75c0796514c22a391ed1694d969ca44050cf5013bbdbf950ea7`, and
`6846123d7e0a6eaae5e3dacaa68941c4c22c2d59fa36ca55b4b31bea1c6380cb`.
The full bundle is not in Git; keep it available locally until it is archived
with the larger research data.

The [preview video](restas-still-air-alpha65-1s-preview.mp4) shows ten saved
states from 0.1 through 1.0 s at a fixed alpha.water threshold of 0.65. Its
camera now stays fixed on the same 10 m region for every frame, and the matte
blue cells have a 0.8 px display blur; no simulation states are interpolated.
The per-frame JSON and PNG files remain in the local run bundle. The earlier
preview auto-fitted each frame separately, which made the spray appear to
change scale. The current camera fix corrects that presentation defect, but
the field itself still has isolated thresholded cell clusters: VTK reports 8,
28, and 35 connected regions at 0.1, 0.5, and 1.0 s respectively. Changing the
alpha cutoff from 0.5 to 0.8 does not remove that fragmentation. At six cells
across the slot, these are unresolved cell groups, not validated droplets or
evidence of physical breakup.

## GPU solver benchmark

CaNS-Fizzy was built for the RTX 5090 with NVIDIA HPC SDK 26.9, CUDA 13.3 and
native `sm_120` code. The run used the upstream CaNS-Fizzy commit
[`c416e481`](https://github.com/CaNS-World/CaNS-Fizzy/tree/c416e48105b19a673a3c419e31160b2091a29c54),
one GPU rank, THINC/QQ VOF, and the upstream 64 × 2 × 128 rising-bubble case.
The initial CPU-only test caught a real VOF initialization bug: the selected
VOF branch passed an uninitialized interface width to the analytic bubble
initializer. The exact, two-site correction and run input are preserved in
[`containers/cans-fizzy`](../containers/cans-fizzy/README.md).

After the correction, the initial phase field was finite and smooth; the full
6,000-step run reached 3.0 s. The unchanged upstream contour test passed
(one-way Hausdorff distance 0.00864, limit 0.1); reverse distance was 0.01166.
Across 13 saved states, phase-volume drift was `5.20e-14` relative and maximum
divergence was `9.86e-14`. These are strong benchmark checks, but this small
benchmark has no slot sources, aircraft flow, RANS closure or engineering mesh.
It provides no speedup comparison with OpenFOAM. The full build and field output
are outside the repository at `/tmp/cans-fizzy-20260927/`.

## Solver choice

FluTAS remains a credible open GPU research code: its paper describes
incompressible two-fluid VOF with MTHINC, and its published GPU results are
promising. Its current project branch has not passed a four-slot source run;
its GPU checks so far are source-disabled verification. CaNS-Fizzy now has a
working native-5090 benchmark, but is likewise not a ready four-slot
engineering setup. OpenFOAM CPU is the documented reference path for our first
source cases. If a suitable commercial license is available, Siemens STAR-CCM+
is worth a bounded evaluation because Siemens documents GPU-native VOF; Fluent's
GPU VOF is still a beta feature with documented limits.

Writing a solver tailored to the 5090 could eventually make sense if matched
tests show that available codes cannot express the required source boundary or
are too slow. Starting now would combine solver development with unresolved
choices about turbulence, interface transport, source conditions and mesh
resolution, making every result harder to validate. First establish a CPU
reference and a same-problem GPU benchmark; then decide from measured runtime
and agreement. No speedup is claimed from comparing the different bubble and
pipe cases.

Sources: [FluTAS paper](https://doi.org/10.1016/j.cpc.2022.108602),
[CaNS-Fizzy paper](https://joss.theoj.org/papers/10.21105/joss.08076.pdf),
[CaNS-Fizzy source](https://github.com/CaNS-World/CaNS-Fizzy),
[Siemens GPU VOF](https://blogs.sw.siemens.com/simcenter/multiphase-cfd-with-gpu/),
[Fluent GPU VOF beta documentation](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/fluent_beta_doc/ch34s07.html),
and the [OpenFOAM external-solver module](https://develop.openfoam.com/modules/external-solver).
