# I4F four-outlet geometry source

From the repository root, replace `NEW_IGNORED_PATH` with a fresh path under
ignored `results/runs/` to generate the provisional two-tank/four-outlet
fluid-envelope BREP and separate divider-solid and zero-thickness
divider-surface candidates:

```sh
uv run --project scripts/i4f_four_outlet_geometry --frozen python scripts/i4f_four_outlet_geometry/generate.py --output-dir NEW_IGNORED_PATH
```

The local UV project pins OpenCascade through `cadquery-ocp==8.0.1.1.0`,
NumPy 2.5.4, Matplotlib 3.11.2, PyVista 0.49.1, and VTK 9.6.2. It writes STEP,
STL, JSON, CSV, and PNG artifacts. The default geometry assumes 0.900 m tank
ID, 1.350 m water per tank, headspace equal to 22.5% of liquid volume, 0.300 m
pipe ID, 1.000 by 0.150 m mouths, a 0.500 m intermediate transition width, and
four assumed 4 mm dividers per mouth. The current default is the user-directed
provisional layout with no post-rise straight and a 1.000 m transition-and-mouth
train; its mouth is at x=4.800 m. Divider thickness and reconstructed branch
routing are not measured hardware dimensions. The envelope is not a CFD mesh.
Pass `--post-rise-straight-m 0.2 --transition-and-mouth-length-m 1.8` to
reproduce the reviewed aligned-ruled-v4 reference stations (mouth x=5.800 m).

Two geometry-only shortening parameters are available:

- `--post-rise-straight-m`: distance after the fixed rise-bend endpoint at
  x=3.800 m to the transition inlet. Default: 0 m; zero is allowed.
- `--transition-and-mouth-length-m`: distance from transition inlet to mouth.
  This scales the existing divider-start, intermediate, transition-end, and
  mouth offsets together; the 0.200 m pipe overlap into the transition scales
  with it as a BREP construction overlap, not extra exposed straight. Default:
  1.000 m.

The candidate record [i4f_shortened_downstream_candidate.json](../../experiments/i4f_shortened_downstream_candidate.json)
defines SHORT1 (user-directed provisional primary, zero straight and a 1.0 m
train), SHORT2 (zero straight and a 0.8 m train), and the legacy 0.2 m / 1.8 m
reference. The reference photograph is used only for visual proportions; it has
no scale and supplies no measured length. The generated comparison reports exact BREP line-volume changes
because shortening the line also changes the initially primed-water inventory.
It does not change or validate a CFD pressure history.

For example, generate the current default primary into a new ignored path:

```sh
uv run --project scripts/i4f_four_outlet_geometry --frozen python scripts/i4f_four_outlet_geometry/generate.py \
  --output-dir results/runs/NEW_IGNORED_PATH
```

To regenerate the legacy reference, pass its explicit lengths:

```sh
uv run --project scripts/i4f_four_outlet_geometry --frozen python scripts/i4f_four_outlet_geometry/generate.py \
  --post-rise-straight-m 0.2 --transition-and-mouth-length-m 1.8 \
  --output-dir results/runs/NEW_IGNORED_PATH
```

The current CLI implements only horizontal tanks on the fixed +X axis with the
fixed two-column/lower-and-upper branch layout; a vertical four-outlet layout
is not implemented.
