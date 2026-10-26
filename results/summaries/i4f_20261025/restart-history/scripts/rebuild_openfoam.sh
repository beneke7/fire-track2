#!/usr/bin/env bash
# Build one captured solver variant inside the pinned OpenFOAM 2512 image.
# Usage in the container: /packet/scripts/rebuild_openfoam.sh v7 /work/v7
set +u
. /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1
setup=$?
set -euo pipefail
if [ "$setup" -ne 0 ]; then
    echo "OpenFOAM environment setup failed: $setup" >&2
    exit "$setup"
fi

if [ "$#" -ne 2 ]; then
    echo "usage: $0 {v7|v8} /work/new-output-path" >&2
    exit 2
fi
variant=$1
output=$2
case "$variant" in
    v7) source_root=/packet/solver-source/v7 ;;
    v8) source_root=/packet/solver-source/v8 ;;
    *) echo "variant must be v7 or v8" >&2; exit 2 ;;
esac
if [ -e "$output" ]; then
    echo "refusing to overwrite output: $output" >&2
    exit 2
fi
mkdir -p "$output/bin"
cp -a "$source_root" "$output/source"
export FOAM_USER_APPBIN="$output/bin"
export OMP_NUM_THREADS=1
export OMP_THREAD_LIMIT=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

for source_dir in \
    "$output/source/applications/solvers/multiphase/compressibleInterFoam/twoPhaseMixtureThermo" \
    "$output/source/applications/solvers/multiphase/compressibleInterFoam/VoFphaseCompressibleTurbulenceModels"
do
    rm -rf "$source_dir/lnInclude"
    nice -n 19 wmakeLnInclude "$source_dir"
done

cd "$output/source/applications/solvers/multiphase/compressibleInterFoam"
nice -n 19 wclean
nice -n 19 wmake
sha256sum "$FOAM_USER_APPBIN"/*
