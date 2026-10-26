# Executed I4F solver source snapshot

This is the source snapshot of the exploratory OpenCFD OpenFOAM **v2512**
`compressibleInterFoamFrozenAlphaSourceV2NoPout` used for the I4F water/air runs.
It includes the frozen predictor-source option and numerical diagnostics.
Original OpenFOAM copyright notices and GPL licensing are preserved; see
[COPYING](COPYING). [The manifest](source-manifest.json) identifies each source
file and the workstation reference executable hash. Compiled objects and
executables are deliberately excluded.

The snapshot also retains sibling OpenFOAM variant sources for provenance.
The executed application is only:

```text
applications/solvers/multiphase/compressibleInterFoam
```

## Captured DCEC diagnostic variant

The source snapshot above remains the historical `d3daff...` reference. The
later captured DCEC diagnostic build is represented additively under
[`variants/dcec`](variants/dcec/variant-manifest.json); its manifest locks the
two source overrides and all 68 output-file hashes. Reconstruct a clean source
tree without changing this base snapshot with:

```bash
python scripts/prepare_i4f_dcec_source.py --output-dir /tmp/i4f-dcec-source
```

The preparer verifies the base manifest and each source hash, refuses an
existing output directory, and copies only the manifest-listed source files.
The captured build used OpenCFD OpenFOAM v2512 image
`sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319`;
the recorded DCEC executable SHA256 is in the variant manifest. A rebuild on
another compiler, library set, or build path is not promised to be bitwise
identical.

This variant enables the existing `DP_CELL` diagnostic writer; it does not
change the pressure or phase equations. `i4fFullPressureAudit` defaults to
`true`. Setting it explicitly to `false` suppresses the expensive pressure
residual/operator diagnostics while retaining the pressure solve and raw-floor
health records; use that case setting only after a matched audit-on/off check
for the intended inputs. The existing base snapshot and its reference binary
remain unchanged.

After loading a compatible site OpenFOAM v2512 and its MPI environment, build
that application with its matching installed libraries:

```bash
cd applications/solvers/multiphase/compressibleInterFoam
wmakeLnInclude VoFphaseCompressibleTurbulenceModels
wmake
```

Its `Make/files` writes the executable to `FOAM_USER_APPBIN`. Reference cases
enable `i4fFrozenPredictorSp true` in `controlDict`. Do not build the sibling
variants or overwrite system solvers as part of this handoff. The
snapshot is not proof of ABI compatibility or a successful build on another
site; record the site-built binary and verify a small MPI restart before use.

Cases separately require the valve `fvOptions`, numerical controls and their
initial/boundary dictionaries. The compressible ambient-reservoir condition is
a separate, ongoing case-local experiment; it is not silently included in this
reference solver. Git contains selected results, not the large native mesh and
restart payload. Transfer the intended immutable case separately and verify
its hashes. The older Slurm solver packager is specific to the Rouaix
`interIsoFoamTracePair` and must not be treated as an I4F package.
