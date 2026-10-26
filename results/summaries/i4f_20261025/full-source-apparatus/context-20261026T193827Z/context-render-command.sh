#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 CASE_DIR TIME_SECONDS FRESH_OUTPUT_DIR" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
BUNDLE="$REPO_ROOT/results/runs/i4f-full-source-context-render-20261026T193827Z"
HELPER="$BUNDLE/analysis/render_native_cutaway_v2.py"
CASE_DIR="$1"
TIME_SECONDS="$2"
OUTPUT_DIR="$3"

if [[ ! -f "$HELPER" ]]; then
  echo "private renderer helper is missing: $HELPER" >&2
  exit 1
fi
if [[ -e "$OUTPUT_DIR" ]]; then
  echo "output path already exists; choose a fresh directory: $OUTPUT_DIR" >&2
  exit 1
fi

cd "$REPO_ROOT"
exec nice -n 19 "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/run_local.py" \
  --threads 1 --timeout 900 -- \
  xvfb-run -a env \
    PYVISTA_OFF_SCREEN=false \
    LIBGL_ALWAYS_SOFTWARE=1 \
    MESA_LOADER_DRIVER_OVERRIDE=llvmpipe \
    __GLX_VENDOR_LIBRARY_NAME=mesa \
    LP_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 CUDA_VISIBLE_DEVICES=-1 \
    "$REPO_ROOT/.venv/bin/python" "$HELPER" \
    --case-dir "$CASE_DIR" --time "$TIME_SECONDS" \
    --out-dir "$OUTPUT_DIR" --stability-seconds 2
