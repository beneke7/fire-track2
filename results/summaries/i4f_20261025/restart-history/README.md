# Euler restart-history probe

This packet reproduces the captured 60-cell sealed gas/water channel diagnostic
with three arms: A runs continuously from the cold start; C restarts from A's
0.1 s checkpoint with the saved `dgdt`; D restarts from the same checkpoint
with a one-step grouped `oldTime()` preallocation. It is a numerical restart
test, not apparatus validation or a production restart policy.

## Observed result

All arms used Euler time integration with `deltaT = 2.5e-4 s`. A ran from
`t=0` to `0.10025000000000008 s`; C and D restarted from the exact 15-file A
checkpoint at `0.10000000000000007 s` and advanced one step. Each captured
Docker run exited 0 with a normal `End` and the requested native endpoint.
The original container IDs, `StartedAt`, exact field hashes, source and case
freezes, and build provenance are preserved under `cases/{A,C,D}/provenance/`
and `evidence/`.

| Comparison | Observed endpoint difference / diagnostic |
|---|---|
| C vs A | max `|p|` difference 127.824 Pa; max `|T|` 0.01154 K; max `|U|` 0.005999 m/s; max `|alpha.water|` 5.58e-6. C's saved `dgdt` reproduces A's outer-1 full-source summary, but not A's endpoint state. |
| Gas continuity L1, A vs C | `4.7048e-8` vs `3.7638e-4 kg/s` (C/A = 7,999.86). The water inventory step remains close to its prescribed withdrawal in both. |
| D vs A | Max differences: `p` 7.92e-9 Pa, `T` 1.02e-12 K, `U` 5.55e-13 m/s, `alpha.water` 3.61e-16, and `rho` 3.41e-13 kg/m3. These values are near roundoff but are not bitwise equal. |
| Gas continuity L1, A vs D | `4.7048138541e-8` vs `4.7048137036e-8 kg/s` (D/A = 0.999999968). D's water continuity L1 is 1.04098 times A's, with both absolute values about `2e-14 kg/s`; do not read this as exact equality of every diagnostic. |

The compiled solver includes the native `ddtCorr(U, phi)` pressure-velocity
correction. The captured `compressibleInterFoam.C` advances `runTime` and then
enters the PIMPLE loop; it snapshots `alpha1` for diagnostics but does not
reset `alpha1` at each outer iteration. The D-only patch adds calls to
`oldTime()` twice for ten fields immediately after `++runTime` and before the
first alpha/EOS/momentum/energy/pressure updates:
`alpha1`, `alpha2`, `rho1`, `rho2`, `rho`, `U`, `T`, `K`, `p_rgh`, and `phi`.
`dgdt` is a separate saved pressure-derived field, not one of those ten.
Equation terms and coefficients are unchanged by this patch. D's grouped
intervention reproduces this short reference step closely; it does not identify
which individual field was necessary.

The source audit records the OpenFOAM-2512 lazy old-time behavior and source
hashes in `evidence/provenance/preallocation-restart-comparison.json`. For a
step from checkpoint `t_n` to `t_(n+1)`, Euler uses the checkpoint state as
the old state. Here, “missing Euler history” means that the field's `oldTime`
object was not reliably bound to that checkpoint before updates; it does not
mean this one-step test required a separate full-field directory at
`t=0.09975 s`. D ensures the current `t_n` checkpoint becomes the new step's
old-time state before fields are mutated. The observed C result shows that
saving `dgdt` alone is not sufficient in this fixture. Calls to `oldTime()` can
allocate and update field history, so diagnostics that call it are not assumed
to be passive.

## Frozen inputs and source

`cases/A`, `cases/C`, and `cases/D` contain the exact 23 static case files and
the saved 0.1 s split and 0.10025 s endpoints. Binary field data are included
for those small 60-cell states. The split and endpoint files are native solver
outputs, not regenerated. No full solver logs or compiled binaries are copied;
their original hashes and run identities remain in the included provenance
JSON, and the original private run bundle is
`results/runs/i4f-dgdt-restart-serialization-20261026T185614Z/`.

The `solver-source/v7` tree is the exact 70-file source snapshot used to build
A and C. `solver-source/v8` is the exact 70-file D source snapshot. Their
per-file hashes are in the adjacent `*-source-files.json` files. The captured
OpenFOAM source-copy record and source manifests are preserved in
`evidence/provenance/`. The v8 tree differs from v7 in the two recorded paths
`Make/files` and `compressibleInterFoam.C`; the exact v7-to-v8 diagnostic patch
is `evidence/provenance/restart-oldtime-preallocation-final.patch`. The
recorded image was
`opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319`
(OpenFOAM-2512). The packet includes the source inputs and recipe for rebuilding in this image.
The new public rebuild recipe has not been executed as part of this package
check; the original builds are documented separately. The historical binary
hash is not promised across compiler or path changes.

The A input's `T.air` and `T.water` are the frozen pre-GO source values,
verified against `evidence/provenance/source-case-input-manifest.json`.
OpenFOAM rewrote phase-temperature fields during startup in some captured case
copies; those post-GO derived files are not used as inputs by this packet.

The toy case uses 80 mL water and 20 mL ideal gas at 1.2 MPa absolute, a
prescribed water withdrawal of `3.172675e-5 m3/s`, rho-constant water at
998.2 kg/m3, ideal-gas air (`Cp=1005 J/(kg K)`, `MW=28.96546 kg/kmol`), common
temperature transport with `Pr=1e9` in both phases, laminar flow, zero gravity,
and one 60-cell axial block. These are diagnostic inputs from the recorded
case, not the confirmed apparatus state.

## Verify, build, and reproduce

From the repository root, verify the packet and all included case/source
hashes:

```sh
python3 results/summaries/i4f_20261025/restart-history/scripts/verify_packet.py
```

To rebuild the A/C or D executable, mount this packet read-only at `/packet`
and a new empty output directory at `/work` in the pinned OpenFOAM image, then
run the bundled script. For example, on the host:

```sh
mkdir -p results/runs/i4f-restart-history-rebuild-unique
docker run --rm --cpus=1 --log-driver=none \
  -v "$PWD/results/summaries/i4f_20261025/restart-history:/packet:ro" \
  -v "$PWD/results/runs/i4f-restart-history-rebuild-unique:/work" \
  opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319 \
  bash --noprofile --norc /packet/scripts/rebuild_openfoam.sh v7 /work/v7
```

Use `v8 /work/v8` for D. `rebuild_openfoam.sh` copies the frozen source to a
new work path, creates the two required `lnInclude` directories, runs `wclean`
and `wmake`, and prints the built binary hashes. It refuses an existing output
path. The original build records in `evidence/provenance/` report the captured
v7 and v8 binary hashes and build status.

Stage a fresh arm input on the host (the output path must be new):

```sh
python3 results/summaries/i4f_20261025/restart-history/scripts/stage_case.py A /path/to/new/A-case
python3 results/summaries/i4f_20261025/restart-history/scripts/stage_case.py C /path/to/new/C-case
python3 results/summaries/i4f_20261025/restart-history/scripts/stage_case.py D /path/to/new/D-case
```

A starts from `0`; C and D include only the 0.1 s checkpoint as their
`latestTime`. The saved `.10025` endpoint is deliberately not copied into a
staged reproduction. Run the staged cases under the project's exact-container
ID/`StartedAt` manifest, GO sentinel, guard, and terminal-capture workflow.
The guarded container should mount the staged case at `/case` and the built
binary directory read-only at `/solver`. Inside it, source the OpenFOAM
environment before enabling strict shell options, then wait for the exact
container's GO sentinel before entering the case and invoking the solver:

```sh
source /usr/lib/openfoam/openfoam2512/etc/bashrc
set -euo pipefail
while [[ ! -s /case/.GO ]]; do sleep 0.05; done
cd /case
nice -n 19 /solver/compressibleInterFoamFrozenAlphaDgdtRestartProbe > /case/log.compressibleInterFoam 2>&1
```

Use `/solver/compressibleInterFoamFrozenAlphaOldTimePreallocationProbe` for D.
The recipe describes the in-container solver command only; it does not bypass
the exact-ID GO/guard requirements for a new run. For a non-destructive
comparison, copy each staged case into a separate run directory and keep all
outputs there. The included analysis sources are the exact analysis scripts
used for the reported JSON/CSV; their dependencies are Python 3 and NumPy.
They were run against the captured case bundle, not rerun on this packet.

## Scope limits

This is one small grid and one post-checkpoint Euler step. It is not a formal
continuation guarantee, a validation pass, or evidence that the same grouped
preallocation is sufficient for all meshes, schemes, startup paths, or
OpenFOAM versions. The packet preserves the exact comparison and code needed
to reproduce this diagnostic; it does not claim a general production restart
policy.
