#!/usr/bin/env bash
set +e +u
. /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1
foam_setup=$?
set -euo pipefail
if [[ "$foam_setup" -ne 0 ]]; then echo "OpenFOAM setup failed: $foam_setup" >&2; exit "$foam_setup"; fi
export FOAM_USER_APPBIN=/pair/bin
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
source_root=/pair/build/source/v8-frozen-pressure-tight-maps
for source_dir in "$source_root/applications/solvers/multiphase/compressibleInterFoam/twoPhaseMixtureThermo" "$source_root/applications/solvers/multiphase/compressibleInterFoam/VoFphaseCompressibleTurbulenceModels"; do
  rm -rf "$source_dir/lnInclude"
  nice -n 19 wmakeLnInclude "$source_dir"
done
cd "$source_root/applications/solvers/multiphase/compressibleInterFoam"
nice -n 19 wclean
nice -n 19 wmake
sha256sum /pair/bin/compressibleInterFoamI4FFrozenPressureTightMap
