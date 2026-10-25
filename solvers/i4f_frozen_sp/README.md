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
