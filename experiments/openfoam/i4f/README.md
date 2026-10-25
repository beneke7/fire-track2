# I4F OpenFOAM profiles

`cold_start_transonic.json` records the matched cold-start numerical profile:
`compressibleInterFoam`, transonic pressure correction, `GAMG` with
`GaussSeidel`, `maxDeltaT=0.00025 s`, `maxCo=0.5`, `maxAlphaCo=0.25`, two
PIMPLE outer correctors, and one alpha subcycle. The profile keeps the same
air/water hydraulic-reference assumptions as the baseline case.
It is now the preparer's default when `--profile` is omitted. Each generated
case records the resolved profile file and SHA256; the explicit command below
is equivalent. This is the explored reference method, not a validated setting.

Prepare a default 2 m external-air case with:

```sh
.venv/bin/python scripts/prepare_i4f_case.py \
  --config experiments/i4f_baseline.json \
  --profile experiments/openfoam/i4f/cold_start_transonic.json \
  --ranks 4 --output results/runs/i4f-run-name
```

To reproduce the earlier non-transonic/DIC/1 ms preparation, explicitly select
`--profile experiments/openfoam/i4f/legacy_nontransonic.json`. Those settings
remain available for historical reproduction and are not the default.

Use `--external-length-m 4.0` for the longer external region. This runtime
override is recorded in `case-inputs.json`; it does not alter the shared
baseline configuration. Background bounds derive from the apparatus and the
external-region bounds with a 0.2 m margin. For the 2 m baseline, the generated
box remains exactly `(-0.2,-1.7,-0.7)` to `(6.7,1.7,2.2)` m on the original
0.1 m lattice. At 4 m external length, only the x maximum and x cell count
change.

The profile writes six sampled-plane observer histories at x=2.2 m (port) and
x=4.49 m (nozzle): alpha-weighted area-integrated `U`, area-normal-integrated
`U`, and area-averaged `alpha.water`. These are interpolated-plane estimates,
not conservative phase face fluxes. Their event contract gates out startup air
by requiring three consecutive positive-mixture port rows with at least 1%
net sampled gas fraction, then three nozzle liquid rows, then three consecutive
nozzle rows above the same 1% threshold. This is an operational marker, not a
universal physical breakthrough criterion. An external watcher must request
`stopAt writeNow` after the marker; the case itself retains the configured
end-time limit.

The reference omits confirmed CO2 composition, dissolved or dispersed gas,
foam properties, and the reported five lamellae. Valve restriction is a
time-dependent scalar loss, not a resolved butterfly disk.

The generator supports horizontal tanks along +x and vertical tanks along +z
through `tank.axis` and a matching `tank.axis_vector`; the vertical geometry supplier is
`scripts/prepare_i4f_vertical_geometry.py`. The pipe and nozzle remain along
+x in both arrangements, with +z upward. Set the vertical tank center and port
location (`tank.center_xyz_m`, matching `tank.center_z_m`, and
`connection.centerline_mouth_xyz_m`) explicitly; this changes the tank/pipe junction from an end-cap entry
to a curved-side entry. Other nozzle directions and tank axes are rejected.
Initial inventories depend on the mesh and interface initialization; use native
cell-volume audits when comparing arrangements rather than assuming equal
nominal fill fractions guarantee equal water masses.
The `gravity_m_s2` input is interpreted as a positive magnitude and emitted
along -z.

The thermophysical setup accepts `gas.kind="air"`, the valve source accepts
`valve.opening_law="smoothstep"`, and the external region requires a zero
`wind_velocity_m_s` vector. Other values are rejected because their physics
are not implemented in this case.

The scalar valve source reads `valve.minimum_effective_opening` as an area
fraction in `(0, 1]`; legacy configs without this key use the existing 0.02
floor. A zero floor is rejected because the current model has no sealed-valve
implementation.
