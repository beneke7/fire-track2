#!/usr/bin/env bash
set -o pipefail
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export OMPI_MCA_mpi_yield_when_idle=1
set +e
source /opt/openfoam13/etc/bashrc >/dev/null 2>&1
setup=$?
set -e
[[ $setup -eq 0 ]] || exit "$setup"
case_dir=${1:?case directory required}
stage=${2:?stage required}
cd "$case_dir"
stage_mpi_ranks=1
[[ $stage != cast-checkpoint ]] || stage_mpi_ranks=10
printf 'OPENFOAM_VERSION=%s STAGE_MPI_RANKS=%s HOST_CPUS=%s STAGE=%s PID=%s\n' \
    "$WM_PROJECT_VERSION" "$stage_mpi_ranks" "$(nproc)" "$stage" "$$"
run() {
    local name=$1
    shift
    [[ ! -e "$name.log" ]] || { echo "STAGE_LOG_ALREADY_EXISTS name=$name" >&2; return 1; }
    printf 'ROUAIX_STAGE_START stage=%s command=%q ' "$name" "$*"
    printf '\n'
    set +e
    /usr/bin/time -v "$@" 2>&1 | tee "$name.log"
    local code=${PIPESTATUS[0]}
    set -e
    printf 'ROUAIX_STAGE_EXIT stage=%s code=%s\n' "$name" "$code"
    return "$code"
}
global_cells() {
    local cells
    cells=$(grep -a -m1 -oE 'nCells:[[:space:]]*[0-9]+' constant/polyMesh/owner | tr -cd '0-9')
    [[ -n $cells ]] || { echo 'GLOBAL_CELL_COUNT_MISSING owner-header-note' >&2; return 1; }
    printf '%s\n' "$cells"
}
assert_global_cells() {
    local expected=$1 label=$2 actual
    actual=$(global_cells) || return
    if [[ $actual != "$expected" ]]; then
        echo "GLOBAL_CELL_COUNT_MISMATCH label=$label expected=$expected actual=$actual" >&2
        return 1
    fi
    echo "GLOBAL_CELL_COUNT_OK label=$label cells=$actual"
}
castellated_cells() {
    awk '
        /Cells per refinement level:/ { inLevels=1; sum=0; have=0; next }
        inLevels && $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ { sum += $2; have=1; next }
        inLevels { if (have) latest=sum; inLevels=0 }
        END { if (inLevels && have) latest=sum; print latest+0 }
    ' castellated.log
}
checked_cells() {
    awk '/^[[:space:]]*cells:[[:space:]]*[0-9]+/ { cells=$2 } END { print cells+0 }' final-check.log
}
set_size() {
    local log=$1 set_type=$2 set_name=$3
    awk -v prefix="$set_type $set_name now size" 'index($0, prefix) { size=$NF } END { print size+0 }' "$log"
}
wall_patch_start() {
    awk '
        /^[[:space:]]*aircraftWall[[:space:]]*$/ { inPatch=1; next }
        inPatch && /startFace[[:space:]]+[0-9]+;/ { gsub(";", "", $2); print $2; exit }
        inPatch && /^}/ { inPatch=0 }
    ' constant/polyMesh/boundary
}
wall_split() {
    local expected_cells=$1 actual_cells index=1 fraction
    assert_global_cells "$expected_cells" before-wall-split
    [[ ! -e points.beforeWallSplit ]] || {
        echo 'WALL_SPLIT_POINT_SNAPSHOT_ALREADY_EXISTS' >&2
        return 1
    }
    cp constant/polyMesh/points points.beforeWallSplit
    for fraction in \
        0.7601841083684133 \
        0.7132083602671838 \
        0.6344410876132930 \
        0.4761904761904762; do
        run "wall-split-$index" refineWallLayer '(aircraftWall)' "$fraction"
        actual_cells=$(global_cells) || return
        [[ $actual_cells -gt $expected_cells ]] || {
            echo "WALL_SPLIT_NO_CELL_GROWTH pass=$index previous=$expected_cells current=$actual_cells" >&2
            return 1
        }
        echo "WALL_SPLIT_CELL_COUNT pass=$index before=$expected_cells after=$actual_cells edgeFraction=$fraction"
        expected_cells=$actual_cells
        index=$((index + 1))
    done
    run final-check checkMesh -constant -allTopology -allGeometry -writeSets -writeSurfaces
    actual_cells=$(checked_cells)
    [[ $actual_cells -gt 0 ]] || { echo 'FINAL_CHECK_CELL_COUNT_MISSING' >&2; return 1; }
    assert_global_cells "$actual_cells" after-wall-split-check
    [[ $actual_cells == "$expected_cells" ]] || {
        echo "WALL_SPLIT_CHECK_CELL_COUNT_MISMATCH expected=$expected_cells checked=$actual_cells" >&2
        return 1
    }
    echo "FINAL_CHECK_CELL_COUNT cells=$actual_cells"
}
owner_wall_split() {
    local expected_cells=$1 actual_cells index=1 fraction selected_cells selected_faces all_wall_faces delta start_face face_fraction
    [[ -f system/wallOwnerSetDict ]] || {
        echo 'EXPERIMENTAL_WALL_SET_DICT_MISSING; rebuild with --experimental-wall-sets' >&2
        return 1
    }
    assert_global_cells "$expected_cells" before-owner-wall-split
    [[ ! -e points.beforeOwnerWallSplit ]] || {
        echo 'OWNER_WALL_SPLIT_POINT_SNAPSHOT_ALREADY_EXISTS' >&2
        return 1
    }
    cp constant/polyMesh/points points.beforeOwnerWallSplit
    for fraction in \
        0.7601841083684133 \
        0.7132083602671838 \
        0.6344410876132930 \
        0.4761904761904762; do
        run "owner-wall-set-$index" topoSet -dict system/wallOwnerSetDict -constant
        selected_cells=$(set_size "owner-wall-set-$index.log" cellSet wallOwnerCells)
        selected_faces=$(set_size "owner-wall-set-$index.log" faceSet hexWallFaces)
        all_wall_faces=$(set_size "owner-wall-set-$index.log" faceSet wallFaces)
        start_face=$(wall_patch_start)
        [[ $selected_cells -gt 0 && $selected_faces -gt 0 && $all_wall_faces -gt 0 && -n $start_face ]] || {
            echo "OWNER_WALL_SELECTION_MISSING pass=$index cells=$selected_cells faces=$selected_faces wallFaces=$all_wall_faces startFace=$start_face" >&2
            return 1
        }
        [[ $selected_faces -le $all_wall_faces ]] || {
            echo "OWNER_WALL_SELECTION_EXCEEDS_PATCH pass=$index selected=$selected_faces wallFaces=$all_wall_faces" >&2
            return 1
        }
        mkdir -p layer-selection
        cp constant/polyMesh/sets/hexWallFaces "layer-selection/pass-$index-hexWallFaces"
        printf '%s\n' "$start_face" > "layer-selection/pass-$index-startFace"
        face_fraction=$(awk -v s="$selected_faces" -v n="$all_wall_faces" 'BEGIN {printf "%.9f", s/n}')
        echo "HEX_WALL_COVERAGE pass=$index selected_cells=$selected_cells selected_wall_faces=$selected_faces total_wall_faces=$all_wall_faces face_fraction=$face_fraction startFace=$start_face"
        run "owner-wall-split-$index" refineWallLayer -inSet wallOwnerCells '(aircraftWall)' "$fraction"
        actual_cells=$(global_cells) || return
        delta=$((actual_cells - expected_cells))
        [[ $delta -eq $selected_cells ]] || {
            echo "OWNER_WALL_SPLIT_CELL_DELTA_MISMATCH pass=$index selected=$selected_cells delta=$delta previous=$expected_cells current=$actual_cells" >&2
            return 1
        }
        echo "OWNER_WALL_SPLIT_CELL_COUNT pass=$index before=$expected_cells after=$actual_cells added=$delta selectedOwners=$selected_cells edgeFraction=$fraction"
        expected_cells=$actual_cells
        index=$((index + 1))
    done
    run final-check checkMesh -constant -allTopology -allGeometry -writeSets -writeSurfaces
    actual_cells=$(checked_cells)
    [[ $actual_cells -gt 0 ]] || { echo 'FINAL_CHECK_CELL_COUNT_MISSING' >&2; return 1; }
    assert_global_cells "$actual_cells" after-owner-wall-split-check
    [[ $actual_cells == "$expected_cells" ]] || {
        echo "OWNER_WALL_SPLIT_CHECK_CELL_COUNT_MISMATCH expected=$expected_cells checked=$actual_cells" >&2
        return 1
    }
    echo "FINAL_CHECK_CELL_COUNT cells=$actual_cells"
    if grep -q '^Mesh OK\.$' final-check.log; then
        echo 'CHECKMESH_GATE=PASS_NATIVE'
    else
        echo 'CHECKMESH_GATE=REVIEW_LOG_AND_SIGNED_PLANES'
    fi
}
if [[ $stage == base ]]; then
    run blockMesh blockMesh
    run base-check checkMesh -allTopology -allGeometry
elif [[ $stage == cast-checkpoint ]]; then
    assert_global_cells 1433790 before-initial-decompose
    run decompose decomposePar -force -noFields
    run castellated mpirun --bind-to core -np 10 snappyHexMesh -parallel -overwrite
    cast_cells=$(castellated_cells)
    [[ $cast_cells -gt 0 ]] || { echo 'CASTELLATED_CELL_COUNT_MISSING' >&2; exit 1; }
    printf '%s\n' "$cast_cells" > castellatedCells.txt
    echo "CASTELLATED_CELL_COUNT cells=$cast_cells"
    run serial-reconstruct reconstructPar -constant -noFields -noSets
    assert_global_cells "$cast_cells" after-castellation-reconstruct
    run nozzle-set topoSet -constant
    run nozzle-patch createPatch -overwrite
    assert_global_cells "$cast_cells" before-prelayer-check
    rm -f constant/polyMesh/sets/nozzleFaces
    run prelayer-check checkMesh -constant -allTopology -allGeometry -writeSets -writeSurfaces
    assert_global_cells "$cast_cells" after-prelayer-check
elif [[ $stage == wall-split ]]; then
    cast_cells=$(cat castellatedCells.txt)
    [[ $cast_cells =~ ^[0-9]+$ ]] && [[ $cast_cells -gt 0 ]] || {
        echo 'CASTELLATED_CELL_COUNT_MISSING' >&2
        exit 1
    }
    wall_split "$cast_cells"
elif [[ $stage == aperture-fixture ]]; then
    run fixture-blockMesh blockMesh
    assert_global_cells 128 after-fixture-blockMesh
    run fixture-nozzle-set topoSet -constant
    run fixture-nozzle-patch createPatch -overwrite
    fixture_cells=$(global_cells)
    printf '%s\n' "$fixture_cells" > castellatedCells.txt
    run fixture-base-check checkMesh -constant -allTopology -allGeometry -writeSets -writeSurfaces
    [[ ! -e pre-owner-split/polyMesh ]] || {
        echo 'FIXTURE_PRE_SPLIT_MESH_ALREADY_EXISTS' >&2
        exit 1
    }
    mkdir -p pre-owner-split
    cp -R constant/polyMesh pre-owner-split/polyMesh
    owner_wall_split "$fixture_cells"
elif [[ $stage == owner-wall-split ]]; then
    cast_cells=$(cat castellatedCells.txt)
    [[ $cast_cells =~ ^[0-9]+$ ]] && [[ $cast_cells -gt 0 ]] || {
        echo 'CASTELLATED_CELL_COUNT_MISSING' >&2
        exit 1
    }
    owner_wall_split "$cast_cells"
elif [[ $stage == global-audit ]]; then
    mesh_cells=$(global_cells)
    echo "GLOBAL_CELL_COUNT_OK label=before-global-audit cells=$mesh_cells"
    run global-check checkMesh -constant -allTopology -allGeometry -writeSets -writeSurfaces
else
    echo "unknown stage: $stage" >&2
    exit 2
fi
