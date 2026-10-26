#!/usr/bin/env bash
set +e +u
. /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1
foam_setup=$?
set -euo pipefail
if [[ "$foam_setup" -ne 0 ]]; then
  echo "OpenFOAM v2512 bashrc setup failed: $foam_setup" >&2
  exit "$foam_setup"
fi

if [[ $# -ne 2 || "$1" != /case || ( "$2" != run && "$2" != --prepare-only ) ]]; then
  echo "usage: run_in_container.sh /case run|--prepare-only" >&2
  exit 2
fi
case_dir=$1
mode=$2
repo=/repo
set -euo pipefail
mkdir -p "$case_dir/logs" "$case_dir/bin"

# The host controller has already verified the JSON input manifest and built
# the exact DCEC tree with the locked host Python. The pinned OpenFOAM image has
# no Python, so verify its portable checksum list with the supplied coreutils.
cd "$case_dir"
sha256sum --check --strict input-files.sha256 > logs/input-verification.log

app_dir="$case_dir/build/dcec-source/applications/solvers/multiphase/compressibleInterFoam"
export FOAM_USER_APPBIN="$case_dir/bin"
mkdir -p "$FOAM_USER_APPBIN"
cd "$app_dir"
{
  wmakeLnInclude VoFphaseCompressibleTurbulenceModels
  wmake
} 2>&1 | tee "$case_dir/logs/solver-build.log"
solver="$case_dir/bin/compressibleInterFoamFrozenAlphaSourceV2NoPout"
if [[ ! -x "$solver" ]]; then
  echo "DCEC build did not create expected executable: $solver" >&2
  exit 1
fi
"$solver" -help > "$case_dir/logs/solver-help.log" 2>&1

cd "$case_dir"
blockMesh 2>&1 | tee logs/blockMesh.log
setFields 2>&1 | tee logs/setFields.log
checkMesh -allTopology -allGeometry 2>&1 | tee logs/checkMesh.log
if ! grep -q 'Mesh OK' logs/checkMesh.log; then
  echo "checkMesh did not report Mesh OK" >&2
  exit 1
fi

manifest_sha256=$(sha256sum input-manifest.json | awk '{print $1}')
checksums_sha256=$(sha256sum input-files.sha256 | awk '{print $1}')
source_prepare_sha256=$(sha256sum logs/source-prepare.json | awk '{print $1}')
solver_sha256=$(sha256sum bin/compressibleInterFoamFrozenAlphaSourceV2NoPout | awk '{print $1}')
{
  printf 'schema=i4f-pressure-equilibrium-case-preparation/v1\n'
  printf 'status=prepared_mesh_ok_waiting_for_GO\n'
  printf 'input_manifest_sha256=%s\n' "$manifest_sha256"
  printf 'input_checksums_sha256=%s\n' "$checksums_sha256"
  printf 'source_prepare_sha256=%s\n' "$source_prepare_sha256"
  printf 'solver_binary_sha256=%s\n' "$solver_sha256"
  printf 'mesh_check=Mesh_OK\n'
} > logs/preparation-ready.env.tmp
mv logs/preparation-ready.env.tmp logs/preparation-ready.env

if [[ "$mode" == --prepare-only ]]; then
  echo "PREPARE_ONLY_COMPLETE=1"
  exit 0
fi

# The host controller writes a matching manifest and GO record only after it
# has verified the exact Docker ID/StartedAt and the preparation hashes above.
while [[ ! -s "$case_dir/GO" ]]; do sleep 0.2; done
if ! cmp -s "$case_dir/GO" "$case_dir/launch-identity.txt"; then
  echo 'GO identity does not match the host-verified launch record' >&2
  exit 1
fi
printf 'RUN_RELEASED_UTC=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > logs/container-release.txt

set +e
timeout --signal=TERM --kill-after=20s 650s "$solver" 2>&1 | tee log.cold-coupled
solver_status=${PIPESTATUS[0]}
set -e
printf '{"exit_code":%s,"exited_utc":"%s"}\n' \
  "$solver_status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > logs/solver-exit.json
exit "$solver_status"
