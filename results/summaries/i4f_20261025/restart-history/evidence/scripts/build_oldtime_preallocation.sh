#!/usr/bin/env bash
set +e +u
. /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1
setup=$?
set -euo pipefail
if [ "$setup" -ne 0 ]; then
    echo "I4F_SETUP_EXIT code=$setup" >&2
    exit "$setup"
fi

export FOAM_USER_APPBIN=/pair/bin
export OMP_NUM_THREADS=1
export OMP_THREAD_LIMIT=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

source_root=/pair/build/source/v8-restart-startstep-oldtime
for source_dir in \
    "$source_root/applications/solvers/multiphase/compressibleInterFoam/twoPhaseMixtureThermo" \
    "$source_root/applications/solvers/multiphase/compressibleInterFoam/VoFphaseCompressibleTurbulenceModels"
do
    rm -rf "$source_dir/lnInclude"
    nice -n 19 wmakeLnInclude "$source_dir"
done

cd "$source_root/applications/solvers/multiphase/compressibleInterFoam"
nice -n 19 wclean
nice -n 19 wmake
sha256sum /pair/bin/compressibleInterFoamFrozenAlphaOldTimePreallocationProbe
