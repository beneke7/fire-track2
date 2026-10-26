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

Use `--tank-axis horizontal` (the default) or `--tank-axis vertical` to select
the vessel orientation. The horizontal option retains the current +X tank axis
and fixed two-column branch layout. The vertical option keeps every branch
spine, valve and outlet in place, gives each tank the same derived length and
capacity, and uses this explicit provisional placement: the tank bottom is at
`TANK_Z - tank_radius`, and its +Z axis passes through the existing pipe-start
coordinate `x=0.250 m` and the tank-center `y`. This is a construction
convention for a geometry comparison; it is not a measured rotated
installation. Because the branch spines stay fixed, the branch-to-vessel wall
intersections change between orientations.

For each branch, generation checks that the circular pipe start fits entirely
inside its own vessel, computes a positive BREP overlap with that vessel, finds
no volume intersection with the other vessel, and verifies a positive
pipe/transition overlap in legacy mode or a shared circular interface in flush
mode. Each joined branch must be one valid solid. The geometry record
contains the per-branch clearances and exact overlap volumes. Assembly render
bounds come from the generated envelope so the vertical tanks remain fully in
frame. `figures/tank_connection_section_<orientation>.png` is a slice through
the vessel cross-sections and the four pipe starts; `figures/two_tank_four_outlet_assembly.png`
shows the full assembly, and `figures/transition_cross_sections.png` shows the
transition and lamella sections. Both orientations use the same default tank
diameter, water/headspace volumes, branch geometry, and outlet geometry unless
other CLI options are explicitly changed. The comparison describes geometry
only and makes no orientation-performance claim.

The downstream geometry options are:

- `--post-rise-straight-m`: distance after the fixed rise-bend endpoint at
  x=3.800 m to the transition inlet. Default: 0 m; zero is allowed.
- `--transition-and-mouth-length-m`: distance from transition inlet to mouth.
  This scales the existing divider-start, intermediate, transition-end, and
  mouth offsets together. Default: 1.000 m.
- `--pipe-transition-join`: `legacy-overlap` (default) preserves the old pipe
  extension, scaled from 0.200 m to 0.1111 m for the compact train. Its union
  with the contracting loft creates an exposed shoulder. `flush-at-inlet`
  ends the round pipe at the loft's circular inlet and removes that shoulder.
  This is an opt-in reconstruction correction; its CFD effect is untested.

The candidate record [i4f_shortened_downstream_candidate.json](../../experiments/i4f_shortened_downstream_candidate.json)
defines SHORT1 (user-directed provisional primary, zero straight and a 1.0 m
train), SHORT2 (zero straight and a 0.8 m train), and the legacy 0.2 m / 1.8 m
reference. The reference photograph is used only for visual proportions; it has
no scale and supplies no measured length. The generated comparison reports exact BREP line-volume changes
because shortening the line changes its storage and liquid-front transit. The
current baseline starts with air downstream of the valves; the older
fully primed comparison instead changes initial line-water inventory.
It does not change or validate a CFD pressure history.

For example, generate the current default primary into a new ignored path:

```sh
uv run --project scripts/i4f_four_outlet_geometry --frozen python scripts/i4f_four_outlet_geometry/generate.py \
  --output-dir results/runs/NEW_IGNORED_PATH
```

Add `--pipe-transition-join flush-at-inlet` for the corrected junction. The
generated joined-branch STEP and longitudinal section figures expose all four
connections; inspect them before preparing a new CFD mesh.

To regenerate the legacy reference, pass its explicit lengths:

```sh
uv run --project scripts/i4f_four_outlet_geometry --frozen python scripts/i4f_four_outlet_geometry/generate.py \
  --post-rise-straight-m 0.2 --transition-and-mouth-length-m 1.8 \
  --output-dir results/runs/NEW_IGNORED_PATH
```

Generate the vertical-axis geometry into a separate fresh path with:

```sh
uv run --project scripts/i4f_four_outlet_geometry --frozen python scripts/i4f_four_outlet_geometry/generate.py \
  --tank-axis vertical --output-dir results/runs/NEW_VERTICAL_ORIENTATION_PATH
```
