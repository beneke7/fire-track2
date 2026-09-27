# Rendering computed pilot surfaces

The P0 renderer reads OpenFOAM's computed `.vtp` interface output, verifies that
the surface contains cells and velocity field `U`, derives its magnitude, and
saves a 3D PNG plus a JSON provenance record. It does not generate or smooth
the simulated geometry. The frame color range is its own minimum and maximum;
do not use it to compare magnitudes across times or designs.

Install the optional, locked PyVista environment and render a frame from an
existing immutable run bundle:

```bash
uv sync --frozen --extra visualization
make render-pilot RUN=results/runs/<run-id> TIME=0.08
```

Omit `TIME` to render the latest available surface. The command writes
`figures/interface-<time>s.png` and a JSON record alongside it. It runs with
VTK off-screen rendering; on a headless host without EGL, wrap it in
`xvfb-run -a`. PyVista documents the off-screen renderer and screenshot flow in
the [installation guide](https://docs.pyvista.org/getting-started/installation)
and [screenshot guide](https://docs.pyvista.org/examples/02-plot/screenshot).

P0 images show only the solver's geometric VOF interface, colored by the
cell-centered velocity magnitude. They are not droplet-size-resolved fields,
validated breakup, full flight-to-ground trajectories, or evidence about foam
or fire suppression. Later design comparisons need one fixed camera, time map,
coordinate frame, and scalar range, with render settings recorded before
comparison. Do conservation and scoring on original solver fields, not on
rendered or converted surfaces.

## Time-resolved animation

`scripts/render_aerial_animation.py` creates a fixed-camera animation from the
actual timestamped VTP surface files. It verifies the source run manifest's
frame hashes, the `U` and `alpha.water` fields, each surface's `TimeValue`, and
the declared time sequence. Each output frame corresponds to one stored solver
time; it does not interpolate or fabricate simulation states. Case comparisons
share one camera and velocity scale. Validated comparisons also require
identical target rectangles and coverage thresholds, so displayed L95 values
use the same scoring basis. The render manifest records input/output hashes,
time span, camera/scalar settings, software versions and the active EGL/OpenGL
renderer. Multisampling is disabled to make output stable on a fixed backend.

Diagnostic mode is for exploratory, incomplete cases and puts the scope warning
into the render. For example, with the local P0 run:

```bash
.venv/bin/python scripts/render_aerial_animation.py \
  --mode diagnostic \
  --case 'P0=results/runs/restas-cpu-vof-20260924T222240.919816Z-49f65225' \
  --output-dir results/runs/p0-short-animation \
  --fps 5 --size 1280 720
```

The current local P0 render uses six stored surfaces from 0.02 to 0.12 s,
covering only 0.10 simulated seconds (1.2 s playback at 5 fps). Its ignored
local artifact is
results/runs/render-p0-short-diagnostic-msaa0-20260925/animation.mp4, with
SHA-256
287d4f758bb2c4c7a83624863d4b30a3994bbbf1cc6146e85de4cfaa722c4161.
Three renders with multisampling disabled produced the same MP4 hash on this
machine. The manifest records VTK's vtkEGLRenderWindow, NVIDIA EGL, RTX 5090
OpenGL renderer and driver version 580.159.03. Byte identity is not guaranteed
across other drivers or rendering backends. The animation is a short
provisional nearfield diagnostic, not a full aircraft-to-ground experiment or
design result. The MP4 and manifest are ignored run artifacts; regenerate them
with the documented command.

The Make wrapper supports one diagnostic case. For validated single-case or
multi-case animations, invoke scripts/render_aerial_animation.py directly;
provide one each of --ground-map, --ground-map-record, --protocol-record and
--validation-record for every named case, plus shared --camera-bounds,
--speed-scale and --map-scale values (and --map-camera-bounds). Run --help to
see the exact argument format. Validated multi-case renders must also use the
same target rectangle and coverage threshold in every ground-map record.

Validated mode accepts a case only with an accepted E4/E5/E6 ground-map
protocol, a matching passed-gate record, and a conservative ground-map artifact
plus provenance. The pass record must bind the exact run-manifest hash,
ground-map record and NPZ hashes, protocol hash, and accepted mass-ledger
tolerance. The renderer independently rebins impact locations/masses, closes
the mutually exclusive mass ledger, and recomputes L95 from the map using the
E0 scoring implementation before display. It also requires predeclared shared
time, camera and scalar ranges, and for comparisons requires identical target
rectangles and coverage thresholds. These render-time checks do not create a
scientific gate pass; the supplied protocol and pass records must point to an
independently reviewed experiment contract. See the script docstring and
`tests/test_aerial_animation.py` for the machine-readable sidecar contracts.

The planned final deliverable remains a fixed-scale 15–30 s scientific render
from a validated full simulation. Do not smooth or decorate a short diagnostic
to imply longer descent or missing breakup/deposition physics.
