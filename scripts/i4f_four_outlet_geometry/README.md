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
pipe ID, 1.000 by 0.150 m mouths, a 0.500 m transition station, and four
assumed 4 mm dividers per mouth. Divider thickness and reconstructed branch
routing are not measured hardware dimensions. The envelope is not a CFD mesh.
The current CLI implements only horizontal tanks on the fixed +X axis with the
fixed two-column/lower-and-upper branch layout; a vertical four-outlet layout
is not implemented.
