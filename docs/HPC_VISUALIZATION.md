# ParaView view for an OpenFOAM VOF tutorial

Compact published measurements, hashes and preview: [26 October evidence bundle](../results/summaries/rouaix_hpc_20261026/README.md).
Raw fields and archives referenced below remain outside Git.

## Current Rouaix case: simple alpha display

The user-preferred view is
[`rouaix-alpha001.pvsm`](../results/runs/rouaix-one-node-paraview-20261026/paraview/rouaix-alpha001.pvsm):
the computed 0.05 s field, with one cell threshold `alpha.water >= 0.01` and
solid surface display. It retains 34,800 cells. No slice, smoothing, invented
droplets or field modification is applied. The full raw reader remains in
the pipeline. Only t=0 and t=0.05 s are stored; there is no intermediate
3D animation history. The stepped surface is the underlying cell geometry.

Open using the installed app's CLI, without accessibility button automation:

```sh
/Applications/ParaView-6.1.1.app/Contents/MacOS/paraview --state=/Users/bene/fire-track2/results/runs/rouaix-one-node-paraview-20261026/paraview/rouaix-alpha001.pvsm
```

The full source archive from job 14649329 is SHA-verified locally and in
project storage. This build's reader cannot read its collated `processors120`
layout directly. The run-specific `demux_collated_blocks.py` copies exact
byte-counted rank payloads, adding only the shared FoamFile header to later
blocks; its fixtures reject truncation and noncontiguous ranks. The ordinary
decomposed display case reads 10,099,265 cells at both times with U and alpha.
ParaView integration gives water volume 0.06273277442454941 m3, versus native
ledger 0.06273277465918203 m3 (relative difference -3.74e-9). This is a readback
cross-check, not a new conservation or physics gate. The extra decomposed
files are local; the HPC run remains collated and archived.

The detailed interface/slice state `rouaix-nearfield.pvsm` is preserved as an
optional earlier view. The final simple CLI startup, render proof and failed
attempt records are in the same `paraview/` directory. Native accessibility
interactions crashed this app in macOS AX/objc_release; CLI startup rendered
successfully. The redundant native conversion job 14650644 was cancelled
before allocation once the local view was verified. No GPU CFD or HPC GPU
batch-render job was started.

The display's alpha=.01 threshold does not change the later Rouaix benchmark
definitions: alpha=.1 cloud and alpha=.9 connected core. Current fields are
startup only; the queued 5 s target has no result yet.

`scripts/paraview_hpc.py` opens a reconstructed OpenFOAM case and creates one
ParaView state at its latest available time. The view contains the computed
`alpha.water = 0.5` interface colored by `|U|` in m/s, a center-plane
`alpha.water` slice on a fixed 0–1 scale, a domain outline, and a scope label.
The state opens at the latest time and uses a dynamic time annotation during
playback. Both color ranges stay fixed across time steps.
The default slice is the mid-z x-y plane, matching the stock 2D damBreak
tutorial; use `--slice-axis x` or `y` for a different cross-section. The camera
looks along z with y up and fits the domain.
The field conversion to point data is for display interpolation only.

## Prepare the HPC output

Use a reconstructed case root with `constant/polyMesh` and time directories
containing `alpha.water` and `U`. ParaView's [OpenFOAM reader](https://docs.paraview.org/en/latest/ReferenceManual/parallelDataVisualization.html)
reads OpenFOAM datasets as multiblock data. For decomposed output, reconstruct
the needed fields first from the case directory:

```bash
reconstructPar -latestTime -fields '(alpha.water U)'
touch case.foam
```

The empty `case.foam` marker belongs in the case root. For a time history,
reconstruct the needed fields at the required times instead of only the latest
time. This helper requires that marker or a case directory containing exactly
one `.foam` marker; it does not assume ParaView can read a collated layout
directly. Copy or mount the reconstructed case where ParaView can read it.

## Create the state

Use the ParaView app's bundled `pvpython` (this workstation has ParaView 6.1.1):

```bash
PV=/Applications/ParaView-6.1.1.app/Contents/bin/pvpython
"$PV" scripts/paraview_hpc.py /path/to/reconstructed/case.foam \
  --state /path/to/output/tutorial.pvsm --slice-axis z
```

The state path must be new. Open the `.pvsm` in ParaView on a machine that can
still access the input case. The default speed scale fits that case's data;
for comparisons, pass the same explicit `--speed-range MIN MAX` in m/s to both
views. The scope annotation says the fields are exploratory tutorial output;
this view does not create inferred droplets or a validation result.

## Actual interIsoFoam smoke state

The preferred state is the CPU smoke run from 24 October 2026, with an explicit
0–2 m/s speed scale for the time slider:
[`tutorial-speed-0-2.pvsm`](../results/runs/komondor-discovery-20261024T203716Z/smoke-14641254/extracted/ml-io-s08-r3-minmax-20261024T205116Z/paraview/tutorial-speed-0-2.pvsm).
Its reload checks are in
[`verification-speed-0-2.json`](../results/runs/komondor-discovery-20261024T203716Z/smoke-14641254/extracted/ml-io-s08-r3-minmax-20261024T205116Z/paraview/verification-speed-0-2.json).
The earlier state whose speed scale follows the final-time field range is
preserved as
[`tutorial.pvsm`](../results/runs/komondor-discovery-20261024T203716Z/smoke-14641254/extracted/ml-io-s08-r3-minmax-20261024T205116Z/paraview/tutorial.pvsm).
The run used OpenFOAM v2512 `interIsoFoam`, eight MPI ranks, 9,072 cells,
100 steps at 0.001 s, and stopped at 0.1 s. The command was:

```bash
/Applications/ParaView-6.1.1.app/Contents/bin/pvpython scripts/paraview_hpc.py \
  results/runs/komondor-discovery-20261024T203716Z/smoke-14641254/extracted/ml-io-s08-r3-minmax-20261024T205116Z/damBreak/damBreak.foam \
  --state results/runs/komondor-discovery-20261024T203716Z/smoke-14641254/extracted/ml-io-s08-r3-minmax-20261024T205116Z/paraview/tutorial-speed-0-2.pvsm \
  --slice-axis z --speed-range 0 2
```

ParaView 6.1.1 reloaded that state with 9,072 mesh cells and both required cell
fields. At 0.1 s, the interface has 174 cells and the computed speed field
ranges from 0.666376 to 1.707196 m/s; the fixed speed LUT is 0–2 m/s, so zero
velocity stays at the low end of the scale at every time step. The z-normal
slice and y-up camera are unchanged from the previous state. The water-fraction
LUT is 0–1 and both LUTs disable automatic rescaling. Reload checks updated the
dynamic time annotation at 0.0 and 0.1 s and verified the saved 0.1 s scene
time, source path, filters, and camera. They did not call `Render()` or save a
screenshot. The bundled runtime printed an optional OpenVKL CPU-device
initialization warning, but state generation and reload checks completed.

As a CPU diagnostic, `IntegrateVariables` on the raw cell-centered
`alpha.water` field gave 6.191778092e-4 m³ at 0 s and 6.191778678e-4 m³ at
0.1 s. The final function-object value is 6.191778336e-4 m³; the difference
from ParaView integration is 3.42e-11 m³. This is a readback cross-check, not
a mass-conservation gate.

An earlier state from job 14641244 is retained as a diagnostic, with its
provenance in [metadata.json](../results/runs/komondor-discovery-20261024T203716Z/r2-smoke-14641244/extracted/ml-io-s08-r2-volfix-20261024T205200Z/paraview/metadata.json).
That job's solver reached 0.1 s and its final fields were reconstructed, but
the batch job failed in a fixed post-processing parser that expected a
different `alpha.water` extrema-row layout. The preferred state uses successful
job 14641254.

## Optional CPU-rendered PNG

The optional `--screenshot PATH` refuses to render unless ParaView created an
OSMesa render window. On a ParaView build with OSMesa, use:

```bash
"$PV" --force-offscreen-rendering --opengl-window-backend OSMesa \
  scripts/paraview_hpc.py /path/to/reconstructed/case.foam \
  --state /path/to/output/tutorial.pvsm \
  --screenshot /path/to/output/tutorial.png
```

The installed Mac app accepts the OSMesa option but creates a `vtkCocoaRenderWindow`,
so this script correctly refuses a screenshot there; saving a `.pvsm` state does
not render. A CPU screenshot needs a ParaView build/runtime that actually
provides OSMesa. No GPU rendering is required for the state file.

## Where HDF5 fits

ParaView 6.1.1 on this workstation exposes both `OpenFOAMReader` and
`VTKHDFReader`. The latter reads the **VTKHDF** schema: VTK datasets stored in
HDF5, with a `/VTKHDF` group and VTK type/version metadata ([VTKHDF format
specification](https://docs.vtk.org/en/v9.7.0/vtk_file_formats/vtkhdf_file_format/index.html)).
HDF5 is a container, not enough information to identify a mesh and field
layout. An OpenFOAM HDF5 file-handler output is not thereby a VTKHDF file, and
this helper does not read HDF5 directly. Use reconstructed OpenFOAM output with
`OpenFOAMReader`, or explicitly export a supported VTKHDF dataset before using
`VTKHDFReader`.

A CPU-only synthetic round trip with this installed writer/reader narrowed that
last option: `VTKHDFWriter` rejected `vtkImageData`, so the successful probe
used a `vtkPolyData` surface extracted from a 3×3×3 point grid. The round trip
preserved 26 points, 24 cells, the `U` component ranges, and the `alpha.water`
range 0–1, but VTKHDF rewrote the field name to `alpha_water`. It is therefore
not a lossless export path for this OpenFOAM VOF field. No conversion step was
added.

Reproduce the successful check with the bundled runtime:

```bash
/Applications/ParaView-6.1.1.app/Contents/bin/pvpython \
  results/runs/paraview-vtkhdf-roundtrip-20261024/roundtrip.py
```

The output is
[`result.json`](../results/runs/paraview-vtkhdf-roundtrip-20261024/result.json)
and `synthetic.vtkhdf` (2,253,432 bytes; SHA-256
`6421861132a9d44c67fcf2be49f8dde804c2a7c65db9be0c3d3afc19752711ab`). The
run produced eight ignored files across the successful run and two preserved
failed attempts (4,515,330 bytes total). The [initial image-data writer
failure](../results/runs/paraview-vtkhdf-smoke-20261024/failure.log) and
[exact-name mismatch](../results/runs/paraview-vtkhdf-polydata-20261024/failure.log)
are recorded with their commands. This is format behavior evidence only; the
reconstructed interIsoFoam case is read through `OpenFOAMReader`, with no
VTKHDF conversion.
