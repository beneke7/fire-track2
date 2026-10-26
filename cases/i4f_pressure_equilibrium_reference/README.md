# Periodic pressure-equilibrium reference case

This small case checks preservation of a uniformly translating water-air
material contact. It is not an apparatus model or a formal validation gate.
The box is 1.0 × 0.08 × 0.08 m with 100 × 8 × 8 cells. A water slab occupies
`0.25 ≤ x ≤ 0.75 m`, with initial `U=(10,0,0) m/s`, `p=p_rgh=100000 Pa`, and
`T=293.15 K`. All six boundaries are translational cyclic. The contact makes
one full periodic traverse at `t=0.1 s`; that is the exact solution for phase
translation, while the exact uniform fields are constant `p`, `U`, and `T`.

The reproduced 1 bar run used DCEC source variant `dcec`, finite-compressibility
water, ideal-gas air, SST, zero gravity/surface tension, no momentum source,
vanLeer/MULES phase transport, linear-upwind momentum, eight outer correctors,
two pressure correctors, fixed `dt=1e-4 s`, and `maxIter=25` for `p_rgh` and
`U` (with unchanged equation tolerances). Those reduced iteration caps were
used only for this spatially uniform equilibrium check; they are not proposed
for the apparatus solver. The solver's `i4fFullPressureAudit` was explicitly
false, with the raw pressure-floor trace still enabled. The water `gamma=7.15`
here is a barotropic EOS exponent, not `Cp/Cv`.

## Rebuild and run

From the repository root, create a fresh output directory. The wrapper refuses
to overwrite an existing path and checks the copied inputs against
`input-manifest.json`. A durable user-systemd controller creates the exact
Docker container, records its ID and `StartedAt`, waits for source build, mesh,
`setFields`, and `checkMesh` hashes, then writes the launch manifest and GO
record before the solver can start. The container remains available after its
terminal checkpoint for inspection; output logs and fields are on the mounted
output path. The controller requests `writeNow` at 510 seconds and has a
650-second container-anchored hard limit (780-second systemd bound).

The host controller reconstructs and verifies the 68-file DCEC source tree
with the public source builder and writes an in-container checksum list for the
frozen case inputs. The pinned container verifies that list, builds the named
executable, generates the mesh and initial phase field, runs `checkMesh`, and
waits at the GO barrier. Only then does the host controller verify the exact
container identity and release the solver:

```bash
run_dir="results/runs/i4f-pressure-equilibrium-repro-$(date -u +%Y%m%dT%H%M%SZ)"
nice -n 19 .venv/bin/python scripts/run_local.py --threads 1 --timeout 840 -- \
  bash cases/i4f_pressure_equilibrium_reference/Allrun "$run_dir"
```

The synchronous command returns after native terminal-field verification.
`Allrun NEW_OUTPUT_DIR --detach` returns once the exact ID/StartedAt, manifest,
and GO release are verified; read `run-status.json` for later progress and
terminal capture. `Allrun NEW_OUTPUT_DIR --prepare-only` uses a one-shot
non-solver container to rebuild the executable and run `blockMesh`, `setFields`,
and `checkMesh` without starting the solver. Full runtime source provenance is
written under the fresh output directory. Before GO, the current host controller
copies and hashes its 19-file execution closure (case launcher/controller,
container runner, native-field verifier and input manifest, local runner/resource
reader, Python dependency locks, DCEC source builder, and its source
manifests/overrides) under `provenance/execution-closure/`. The snapshot record
also captures the Git revision, dirty-path list, and UTC capture time; the
controller rechecks the saved and live closure bytes before releasing GO. A
later unrelated Git commit does not invalidate the snapshot when those execution
bytes still match. See
[`input-manifest.json`](input-manifest.json) for the exact copied input hashes
and [the published DCEC variant](../../solvers/i4f_frozen_sp/variants/dcec/variant-manifest.json)
for its 68 source hashes and captured executable identity.

The recorded 1 bar run at
`results/runs/i4f-pressure-equilibrium-1bar-periodic-20261026T172125Z/` predates
this execution-closure snapshot addition. Its original input/source hashes and
output remain the evidence for that run; it does not contain the new
pre-GO closure copy, and the updated controller is not claimed as the version
that executed that smoke.

The separate reproduction run at
`results/runs/i4f-pressure-equilibrium-repro-20261026T181252Z/` has a source
snapshot captured at `2026-10-26T18:19:29Z`, after its recorded solver exit at
`18:17:09Z`. That 11-file record is useful post-run provenance, but it is not a
pre-GO execution snapshot. Future runs use the 19-file pre-GO closure described
above; neither historical run is backdated to claim that protection.

## Result and limits

The captured 1 bar case completed 0.1 s normally in 220.27 solver seconds
(1000 steps). Native maximum errors were `7.20e-9 Pa` in pressure,
`2.01e-11 K` in temperature, and `4.27e-12 m/s` in velocity. There were
16,000 raw pressure-floor trace records and no cell below the configured
10 kPa floor. The water volume differed from its initial value by
`-2.55e-17 m³` at the endpoint; at 0.02 s a temporary `-3.01e-10 m³` phase
volume deviation was observed and is preserved in the data bundle.

The matching 1.2 MPa case reached only 0.0111 s before a bounded wall save,
short of its 0.02 s target; its native errors and terminal status are retained
in `results/summaries/i4f_20261025/pressure-equilibrium/`. Neither test
establishes acoustic-wave accuracy, apparatus-model suitability, or a formal
solver validation result. In particular, the tested uniform state does not
excite the frozen predictor-source term.
