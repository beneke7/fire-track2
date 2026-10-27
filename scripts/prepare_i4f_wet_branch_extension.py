#!/usr/bin/env python3
"""Prepare a short flat-plane outlet extension for the frozen I4F wet branch."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
PARENT = RUNS / "i4f-wet-branch-upwind-20261027T080629Z"
D_PARENT = RUNS / "i4f-wet-branch-outlet-extension-20261027T085020Z"
IMAGE = "opencfd/openfoam-default@sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319"
OUTLET_NAME = "wetOutlet"
OUTLET_PLANE_X_M = 5.10
LAYER_COUNT = 12


def load_helper():
    helper_path = ROOT / "scripts/prepare_i4f_wet_branch_reference.py"
    spec = importlib.util.spec_from_file_location("i4f_wet_branch_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load existing wet-branch helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_vtk_surface(path: Path, points: np.ndarray, faces: list[list[int]]) -> None:
    """Write indexed polygonal VTK data; OpenFOAM v2512 triangulates both twins identically."""
    with path.open("w", encoding="ascii") as stream:
        stream.write(
            "# vtk DataFile Version 2.0\nI4F wet outlet matched surface\nASCII\nDATASET POLYDATA\n"
        )
        stream.write(f"POINTS {len(points)} double\n")
        for point in points:
            stream.write(f"{point[0]:.17g} {point[1]:.17g} {point[2]:.17g}\n")
        total = sum(len(face) + 1 for face in faces)
        stream.write(f"POLYGONS {len(faces)} {total}\n")
        for face in faces:
            stream.write(str(len(face)) + " " + " ".join(str(i) for i in face) + "\n")


def patch_geometry(
    helper: Any, mesh: Path, patch_name: str
) -> tuple[np.ndarray, list[list[int]], dict[str, Any]]:
    boundary = helper._read_global_boundary(mesh / "boundary")
    found = [row for row in boundary if row[0] == patch_name]
    if len(found) != 1:
        raise ValueError(f"expected one {patch_name} patch in {mesh}")
    _, patch_type, count, start = found[0]
    offsets, labels = helper._read_global_faces(mesh / "faces")
    points = helper._read_global_points(mesh / "points")
    mesh_points: set[int] = set()
    raw_faces: list[list[int]] = []
    for face_id in range(start, start + count):
        face = list(map(int, labels[offsets[face_id] : offsets[face_id + 1]]))
        raw_faces.append(face)
        mesh_points.update(face)
    ordered = sorted(mesh_points)
    local = {point_id: i for i, point_id in enumerate(ordered)}
    local_faces = [[local[p] for p in face] for face in raw_faces]
    return (
        points[ordered],
        local_faces,
        {
            "patch_type": patch_type,
            "face_count": count,
            "global_point_ids": ordered,
            "patch_start_face": start,
        },
    )


def vtk_surface_pair(helper: Any, case: Path) -> dict[str, Any]:
    mesh = case / "constant/polyMesh"
    base_points, faces, patch_record = patch_geometry(helper, mesh, OUTLET_NAME)
    plane_points = base_points.copy()
    plane_points[:, 0] = OUTLET_PLANE_X_M
    tri_surface = case / "constant/triSurface"
    tri_surface.mkdir(parents=True, exist_ok=True)
    base_path = tri_surface / "wetOutletBase.vtk"
    plane_path = tri_surface / "wetOutletPlane.vtk"
    write_vtk_surface(base_path, base_points, faces)
    write_vtk_surface(plane_path, plane_points, faces)
    if len(faces) != 384:
        raise ValueError(f"unexpected parent outlet face count {len(faces)}")
    return {
        "base_surface": str(base_path.relative_to(case)),
        "target_surface": str(plane_path.relative_to(case)),
        "base_surface_sha256": digest(base_path),
        "target_surface_sha256": digest(plane_path),
        "base_patch_point_count": len(base_points),
        "base_patch_face_count": len(faces),
        "base_patch_x_range_m": [float(base_points[:, 0].min()), float(base_points[:, 0].max())],
        "target_plane_x_m": OUTLET_PLANE_X_M,
        "parent_patch": patch_record,
        "surface_topology_identical_by_construction": True,
    }


def extrude_mesh_dict(case: Path) -> str:
    base = "/case/constant/triSurface/wetOutletBase.vtk"
    target = "/case/constant/triSurface/wetOutletPlane.vtk"
    return f'''FoamFile
{{
    version 2.0;
    format ascii;
    class dictionary;
    object extrudeMeshDict;
}}
constructFrom mesh;
sourceCase "/case";
sourcePatches (wetOutlet);
flipNormals false;
extrudeModel offsetSurface;
nLayers {LAYER_COUNT};
expansionRatio 1.0;
offsetSurfaceCoeffs
{{
    baseSurface "{base}";
    offsetSurface "{target}";
    project false;
}}
mergeFaces false;
mergeTol 0;
'''


def mesh_script(attempt: int = 1) -> str:
    script = """#!/usr/bin/env bash
set +e
. /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1
foam_rc=$?
set -Eeuo pipefail
if [[ $foam_rc -ne 0 || -z "${WM_PROJECT_VERSION:-}" ]]; then
    echo "OpenFOAM environment init failed rc=$foam_rc" >&2
    exit 70
fi
cd /case
set +e
surfaceCheck constant/triSurface/wetOutletBase.vtk > /bundle/logs/surfaceCheck-base-attempt@@ATTEMPT@@.log 2>&1
base_rc=$?
surfaceCheck constant/triSurface/wetOutletPlane.vtk > /bundle/logs/surfaceCheck-plane-attempt@@ATTEMPT@@.log 2>&1
plane_rc=$?
set -e
printf 'BASE_SURFACE_CHECK_EXIT=%s\\nPLANE_SURFACE_CHECK_EXIT=%s\\n' "$base_rc" "$plane_rc" > /bundle/logs/surfaceCheck-status-attempt@@ATTEMPT@@.txt
extrudeMesh -case /case > /bundle/logs/extrudeMesh-attempt@@ATTEMPT@@.log 2>&1
"""
    return script.replace("@@ATTEMPT@@", f"{attempt:03d}")


def parse_patch_faces(
    helper: Any, mesh: Path, patch_name: str
) -> tuple[np.ndarray, np.ndarray, float, dict[str, Any]]:
    sys.path.insert(0, str(ROOT / "src"))
    from aerial_drop.i4f_native_mouth_flux import _polygon_measure

    boundary = helper._read_global_boundary(mesh / "boundary")
    found = [row for row in boundary if row[0] == patch_name]
    if len(found) != 1:
        raise ValueError(f"expected exactly one {patch_name} patch after extrusion")
    _, patch_type, count, start = found[0]
    offsets, labels = helper._read_global_faces(mesh / "faces")
    points = helper._read_global_points(mesh / "points")
    centers, vectors, areas, fan_areas = [], [], [], []
    for face_id in range(start, start + count):
        face_points = points[labels[offsets[face_id] : offsets[face_id + 1]]]
        sf, center, area, fan_area = _polygon_measure(face_points)
        centers.append(center)
        vectors.append(sf)
        areas.append(area)
        fan_areas.append(fan_area)
    return (
        np.asarray(centers),
        np.asarray(vectors),
        float(np.sum(areas)),
        {
            "patch_type": patch_type,
            "count": count,
            "start": start,
            "absolute_first_vertex_fan_area_m2": float(np.sum(fan_areas)),
        },
    )


def replace_patch_scalar_values(text: str, patch_name: str, values: np.ndarray) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(patch_name)}\s*\{{", text)
    if not match:
        raise ValueError(f"field dictionary lacks patch {patch_name}")
    brace = text.find("{", match.start())
    depth = 0
    end = None
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError(f"unclosed dictionary block for {patch_name}")
    block = text[brace:end]
    value = re.search(r"value\s+nonuniform\s+List<scalar>\s+\d+\s*\(", block)
    if not value:
        raise ValueError(f"{patch_name} pressure value is not a nonuniform scalar list")
    open_paren = block.find("(", value.start())
    depth = 0
    close = None
    for index in range(open_paren, len(block)):
        if block[index] == "(":
            depth += 1
        elif block[index] == ")":
            depth -= 1
            if depth == 0:
                close = index + 1
                break
    if close is None:
        raise ValueError(f"unclosed scalar list in {patch_name}")
    new_list = f"value nonuniform List<scalar> {len(values)}\n    (\n"
    new_list += "".join(f"        {v:.17g}\n" for v in values)
    new_list += "    )"
    new_block = block[: value.start()] + new_list + block[close:]
    return text[:brace] + new_block + text[end:]


def read_ascii_patch_scalar_values(text: str, patch_name: str, count: int) -> np.ndarray:
    """Read an ASCII nonuniform patch list without relying on header spacing."""
    match = re.search(rf"(?m)^\s*{re.escape(patch_name)}\s*\{{", text)
    if match is None:
        raise ValueError(f"field dictionary lacks patch {patch_name}")
    brace = text.find("{", match.start())
    depth = 0
    end = None
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError(f"unclosed dictionary block for {patch_name}")
    block = text[brace:end]
    values_match = re.search(r"value\s+nonuniform\s+List<scalar>\s+(\d+)\s*\(", block)
    if values_match is None or int(values_match.group(1)) != count:
        raise ValueError(f"{patch_name} scalar count mismatch")
    start = values_match.end()
    close = block.find(")", start)
    if close < 0:
        raise ValueError(f"unclosed scalar list on {patch_name}")
    values = np.fromstring(block[start:close], sep=" ", dtype=np.float64)
    if values.size != count or not np.isfinite(values).all():
        raise ValueError(f"invalid scalar list on {patch_name}")
    return values


def prepare(bundle: Path) -> None:
    helper = load_helper()
    bundle = bundle.resolve()
    if (bundle / "case").exists():
        raise FileExistsError(f"case already exists: {bundle / 'case'}")
    helper.verify_freeze(PARENT)
    parent_freeze = json.loads((PARENT / "input-freeze.json").read_text())
    (bundle / "case").mkdir()
    for name in ("logs", "scripts", "analysis", "figures", "source", "geometry"):
        (bundle / name).mkdir(exist_ok=True)
    copied = [
        helper.copy_independent(PARENT / "case" / row["path"], bundle / "case" / row["path"])
        for row in parent_freeze["files"]
    ]
    case = bundle / "case"
    surfaces = vtk_surface_pair(helper, case)
    dict_path = case / "system/extrudeMeshDict"
    dict_path.write_text(extrude_mesh_dict(case), encoding="utf-8")
    mesh_script_path = bundle / "scripts/mesh_extension.sh"
    mesh_script_path.write_text(mesh_script(1), encoding="utf-8")
    mesh_script_path.chmod(0o755)
    shutil.copy2(PARENT / "scripts/run_solver.sh", bundle / "scripts/run_solver.sh")
    (bundle / "scripts/run_solver.sh").chmod(0o755)
    shutil.copy2(
        ROOT / "scripts/prepare_i4f_wet_branch_reference.py",
        bundle / "source/prepare_i4f_wet_branch_reference.py",
    )
    shutil.copy2(Path(__file__).resolve(), bundle / "source/prepare_i4f_wet_branch_extension.py")
    parent_prep = json.loads((PARENT / "preparation.json").read_text())
    parent_terminal = json.loads((PARENT / "terminal.json").read_text())
    metadata = {
        "schema": "i4f-wet-branch-outlet-extension-preparation/v1",
        "created_utc": now_utc(),
        "parent_bundle": str(PARENT),
        "parent_terminal_container_id": parent_terminal["container_id"],
        "parent_input_freeze_sha256": helper.sha256_file(PARENT / "input-freeze.json"),
        "parent_case_input_files": len(parent_freeze["files"]),
        "copied_input_files": copied,
        "only_geometry_change": "append a 0.30 m numerical outlet extension, mapping the existing warped outlet section to a flat x=5.10 m plane",
        "pressure_boundary_law": "pSolver=-g dot (Cf-xref), preserving ambient pAbs at the new plane",
        "extension": {
            "tool": "OpenCFD v2512 extrudeMesh",
            "model": "offsetSurface",
            "source_patch": OUTLET_NAME,
            "layers": LAYER_COUNT,
            "target_x_m": OUTLET_PLANE_X_M,
            "mergeTol": 0,
            "project_intermediate_layers": False,
            "divider_continuation": False,
            "side_wall_patch": "apparatusWall",
            "side_wall_bc": "inherited noSlip",
        },
        "surface_inputs": surfaces,
        "parent_physics": parent_prep["physics_and_solver"],
        "parent_flow_setup": parent_prep["flow_setup"],
        "solver_settings": {
            "solver": "stock serial simpleFoam",
            "div_phi_U": "bounded Gauss upwind",
            "SIMPLE.consistent": "yes",
            "runaway_guard_max_mag_U_m_s": 200.0,
        },
        "source_image": IMAGE,
        "source_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip(),
        "preparation_script_sha256": digest(Path(__file__).resolve()),
        "runaway_control_identical_to_upwind_parent": True,
        "geometry_validation_pending": True,
        "not_a_hardware_modification": True,
    }
    helper.atomic_json(bundle / "preparation.json", metadata)
    print(
        json.dumps(
            {
                "bundle": str(bundle),
                "files": len(copied),
                "surfaces": surfaces,
                "extrudeMeshDict_sha256": digest(dict_path),
            },
            indent=2,
        )
    )


def prepare_parent_cf_control(bundle: Path) -> dict[str, Any]:
    """Clone the immutable B parent and correct only its outlet p list to v2512 Cf."""
    helper = load_helper()
    bundle = bundle.resolve()
    if bundle.exists():
        raise FileExistsError(f"control bundle already exists: {bundle}")
    helper.verify_freeze(PARENT)
    parent_freeze = json.loads((PARENT / "input-freeze.json").read_text(encoding="utf-8"))
    parent_prep = json.loads((PARENT / "preparation.json").read_text(encoding="utf-8"))
    parent_terminal = json.loads((PARENT / "terminal.json").read_text(encoding="utf-8"))
    case = bundle / "case"
    for name in ("case", "logs", "analysis", "figures", "source", "scripts"):
        (bundle / name).mkdir(parents=True, exist_ok=True)
    copied = [
        helper.copy_independent(PARENT / "case" / row["path"], case / row["path"])
        for row in parent_freeze["files"]
    ]
    mesh = case / "constant/polyMesh"
    centers, sf, area, patch = parse_patch_faces(helper, mesh, OUTLET_NAME)
    if patch["count"] != 384:
        raise ValueError(f"parent outlet has {patch['count']} faces, expected 384")
    xref = np.asarray(parent_prep["flow_setup"]["pressure_reference_xyz_m"], dtype=float)
    physics = parent_prep["physics_and_solver"]
    gravity = np.asarray(physics["gravity_xyz_m_s2"], dtype=float)
    rho = float(physics["water_density_kg_m3"])
    updated = -np.einsum("i,ji->j", gravity, centers - xref)
    p_path = case / "0/p"
    original = p_path.read_text(encoding="latin1")
    original_values = read_ascii_patch_scalar_values(original, OUTLET_NAME, patch["count"])
    residual_pa = (original_values - updated) * rho
    p_path.write_text(
        replace_patch_scalar_values(original, OUTLET_NAME, updated), encoding="latin1"
    )
    shutil.copy2(PARENT / "scripts/run_solver.sh", bundle / "scripts/run_solver.sh")
    shutil.copy2(Path(__file__).resolve(), bundle / "source/prepare_i4f_wet_branch_extension.py")
    metadata = {
        "schema": "i4f-wet-branch-v2512-outlet-pressure-profile-control/v1",
        "created_utc": now_utc(),
        "purpose": "Same native B mesh, upwind/SIMPLE-consistent solver inputs and initial fields, with only the B outlet fixedValue list re-evaluated using pinned v2512 face::centre geometry.",
        "parent_bundle": str(PARENT),
        "parent_container_id": parent_terminal["container_id"],
        "parent_input_freeze_sha256": helper.sha256_file(PARENT / "input-freeze.json"),
        "source_image": IMAGE,
        "solver_settings": {
            "solver": "stock serial simpleFoam",
            "div_phi_U": "bounded Gauss upwind",
            "SIMPLE.consistent": "yes",
            "runaway_guard_max_mag_U_m_s": 200.0,
        },
        "flow_setup": parent_prep["flow_setup"],
        "physics_and_solver": physics,
        "mesh_and_geometry": parent_prep["mesh_and_geometry"],
        "only_changed_case_file": "0/p",
        "outlet_pressure_update": {
            "law": "same pSolver=-g dot (Cf-xref) ambient-pressure law; Cf from pinned v2512 area-magnitude-weighted face centre",
            "outlet_face_count": patch["count"],
            "v2512_native_area_m2": area,
            "signed_projected_x_area_m2": float(sf[:, 0].sum()),
            "parent_legacy_profile_max_abs_error_pa": float(np.max(np.abs(residual_pa))),
            "parent_legacy_profile_rms_error_pa": float(np.sqrt(np.mean(residual_pa**2))),
            "updated_profile_residual_max_abs_pa": 0.0,
            "updated_profile_residual_rms_pa": 0.0,
            "original_parent_p_sha256": hashlib.sha256(original.encode("latin1")).hexdigest(),
            "new_p_sha256": digest(p_path),
        },
        "geometry_unchanged_from_B": True,
        "not_a_hardware_modification": True,
        "preparation_script_sha256": digest(Path(__file__).resolve()),
        "copied_input_files": copied,
    }
    helper.atomic_json(bundle / "preparation.json", metadata)
    (bundle / "scripts/run_solver.sh").chmod(0o755)
    freeze = helper.freeze_inputs(bundle)
    metadata["input_freeze_sha256"] = helper.sha256_file(bundle / "input-freeze.json")
    metadata["input_file_count"] = len(freeze["files"])
    helper.atomic_json(bundle / "preparation.json", metadata)
    helper.verify_freeze(bundle)
    result = {
        "bundle": str(bundle),
        "input_freeze_sha256": metadata["input_freeze_sha256"],
        "input_file_count": len(freeze["files"]),
        "p_parent_error_max_abs_pa": metadata["outlet_pressure_update"][
            "parent_legacy_profile_max_abs_error_pa"
        ],
        "p_parent_error_rms_pa": metadata["outlet_pressure_update"][
            "parent_legacy_profile_rms_error_pa"
        ],
        "v2512_area_m2": area,
        "signed_projected_x_area_m2": float(sf[:, 0].sum()),
        "only_changed_case_file": "0/p",
    }
    helper.atomic_json(bundle / "logs/preparation-result.json", result)
    return result


def finalize_parent_cf_control(bundle: Path) -> dict[str, Any]:
    """Complete a preserved pre-GO clone after the earlier chmod typo, without recopying it."""
    helper = load_helper()
    bundle = bundle.resolve(strict=True)
    case = bundle / "case"
    freeze_path = bundle / "input-freeze.json"
    if freeze_path.exists():
        raise FileExistsError("control bundle is already frozen")
    parent_freeze = json.loads((PARENT / "input-freeze.json").read_text(encoding="utf-8"))
    parent_prep = json.loads((PARENT / "preparation.json").read_text(encoding="utf-8"))
    prep_path = bundle / "preparation.json"
    metadata = json.loads(prep_path.read_text(encoding="utf-8"))
    if metadata["parent_input_freeze_sha256"] != helper.sha256_file(PARENT / "input-freeze.json"):
        raise RuntimeError("immutable B parent input freeze changed")

    expected = {row["path"]: row for row in parent_freeze["files"]}
    changed = []
    for name, row in expected.items():
        source = PARENT / "case" / name
        target = case / name
        if (
            not target.is_file()
            or target.stat().st_ino == source.stat().st_ino
            or (name != "0/p" and digest(target) != digest(source))
        ):
            changed.append(name)
    if changed:
        raise RuntimeError(
            "copied B inputs are missing, changed, or not inode-independent: " + ", ".join(changed)
        )

    mesh = case / "constant/polyMesh"
    centers, sf, area, patch = parse_patch_faces(helper, mesh, OUTLET_NAME)
    xref = np.asarray(parent_prep["flow_setup"]["pressure_reference_xyz_m"], dtype=float)
    gravity = np.asarray(parent_prep["physics_and_solver"]["gravity_xyz_m_s2"], dtype=float)
    rho = float(parent_prep["physics_and_solver"]["water_density_kg_m3"])
    expected_values = -np.einsum("i,ji->j", gravity, centers - xref)
    original_values = read_ascii_patch_scalar_values(
        (PARENT / "case/0/p").read_text(encoding="latin1"), OUTLET_NAME, patch["count"]
    )
    current_values = read_ascii_patch_scalar_values(
        (case / "0/p").read_text(encoding="latin1"), OUTLET_NAME, patch["count"]
    )
    if not np.array_equal(current_values, expected_values):
        raise RuntimeError("prepared outlet list is not the exact pinned-v2512 Cf profile")
    delta_pa = (original_values - expected_values) * rho
    changed_inputs = [
        name
        for name, row in expected.items()
        if digest(PARENT / "case" / name) != digest(case / name)
    ]
    if changed_inputs != ["0/p"]:
        raise RuntimeError(f"control changed case inputs outside 0/p: {changed_inputs}")

    attempt_record = {
        "schema": "i4f-wet-branch-cf-control-preparation-attempt/v1",
        "attempt": 1,
        "created_utc": now_utc(),
        "command": ".venv/bin/python scripts/run_local.py --threads 1 --timeout 300 -- nice -n 19 .venv/bin/python scripts/prepare_i4f_wet_branch_extension.py prepare-cf-control --bundle results/runs/i4f-wet-branch-v2512-cf-control-20261027T0917Z",
        "returncode": 1,
        "error": "AttributeError: 'str' object has no attribute 'chmod' at the post-copy run_solver.sh chmod step; all 104 frozen parent inputs were copied independently and only 0/p had been replaced before the error.",
        "recovery": "Preserved case was validated in place and finalized without recopying it.",
    }
    helper.atomic_json(bundle / "logs/preparation-attempt001-error.json", attempt_record)
    helper.atomic_json(
        bundle / "logs/preparation-attempt002-error.json",
        {
            "schema": "i4f-wet-branch-cf-control-preparation-attempt/v1",
            "attempt": 2,
            "created_utc": now_utc(),
            "command": ".venv/bin/python scripts/run_local.py --threads 1 --timeout 300 -- nice -n 19 .venv/bin/python scripts/prepare_i4f_wet_branch_extension.py finalize-cf-control --bundle results/runs/i4f-wet-branch-v2512-cf-control-20261027T0917Z",
            "returncode": 1,
            "error": "Validation predicate compared the intentionally modified 0/p to the parent before checking the declared single-file diff.",
            "recovery": "Predicate corrected to allow only 0/p to differ while requiring independent inode and exact parent bytes for every other frozen file.",
        },
    )
    shutil.copy2(
        Path(__file__).resolve(), bundle / "source/prepare_i4f_wet_branch_extension-attempt003.py"
    )
    (bundle / "scripts/run_solver.sh").chmod(0o755)

    metadata["outlet_pressure_update"].update(
        {
            "parent_legacy_profile_max_abs_error_pa": float(np.max(np.abs(delta_pa))),
            "parent_legacy_profile_rms_error_pa": float(np.sqrt(np.mean(delta_pa**2))),
            "original_parent_p_sha256": digest(PARENT / "case/0/p"),
            "new_p_sha256": digest(case / "0/p"),
            "native_cf_method": "OpenCFD v2512 face::centre area-magnitude-weighted polygon triangulation",
            "pressure_profile_parser": "ASCII scalar list parsed by numeric text; the first attempt's imported parser assumed a different ascii header spacing and was discarded before GO",
        }
    )
    metadata["case_input_diff"] = {
        "changed_paths": changed_inputs,
        "all_other_parent_input_hashes_match": True,
        "independent_inode_copy_verified": True,
    }
    metadata["preparation_attempts"] = [
        "attempt001: case copy and pressure update completed, then halted at chmod typo before freeze/GO",
        "attempt002: validation predicate rejected the intended 0/p difference; case remained pre-GO and unchanged",
        "attempt003: corrected the single-file-diff validation and finalized the same pre-GO case without recopying inputs",
    ]
    metadata["preparation_script_sha256"] = digest(Path(__file__).resolve())
    helper.atomic_json(prep_path, metadata)
    freeze = helper.freeze_inputs(bundle)
    metadata["input_freeze_sha256"] = helper.sha256_file(freeze_path)
    metadata["input_file_count"] = len(freeze["files"])
    metadata["finalized_utc"] = now_utc()
    helper.atomic_json(prep_path, metadata)
    helper.verify_freeze(bundle)
    result = {
        "bundle": str(bundle),
        "input_freeze_sha256": metadata["input_freeze_sha256"],
        "input_file_count": len(freeze["files"]),
        "changed_case_paths": changed_inputs,
        "parent_profile_error_max_abs_pa": metadata["outlet_pressure_update"][
            "parent_legacy_profile_max_abs_error_pa"
        ],
        "parent_profile_error_rms_pa": metadata["outlet_pressure_update"][
            "parent_legacy_profile_rms_error_pa"
        ],
        "pressure_law_residual_pa": 0.0,
    }
    helper.atomic_json(bundle / "logs/preparation-result-final.json", result)
    return result


def prepare_d_continuation(bundle: Path, end_iteration: int = 9000) -> dict[str, Any]:
    """Clone D's captured native endpoint and extend only the SIMPLE iteration limit."""
    helper = load_helper()
    bundle = bundle.resolve()
    if bundle.exists():
        allowed = {"logs"}
        if (bundle / "case").exists() or any(path.name not in allowed for path in bundle.iterdir()):
            raise FileExistsError(
                f"continuation bundle already contains preparation data: {bundle}"
            )
    helper.verify_freeze(D_PARENT)
    parent_terminal_path = D_PARENT / "terminal.json"
    terminal = json.loads(parent_terminal_path.read_text(encoding="utf-8"))
    parent_prep = json.loads((D_PARENT / "preparation.json").read_text(encoding="utf-8"))
    if terminal.get("exit_code") != 0 or not terminal.get("normal_solver_End"):
        raise RuntimeError("D is not a captured normal-End checkpoint")
    latest = str(max((int(t) for t in terminal["latest_native_times"] if t.isdigit())))
    if latest != "3000":
        raise RuntimeError(f"expected D endpoint iteration 3000, found {latest}")
    required = {"p", "U", "phi", "k", "omega"}
    checkpoint = D_PARENT / "case" / latest
    if not checkpoint.is_dir() or not required.issubset(
        {p.name for p in checkpoint.iterdir() if p.is_file()}
    ):
        raise RuntimeError("D iteration-3000 checkpoint lacks required simpleFoam fields")

    case = bundle / "case"
    for name in ("logs", "analysis", "figures", "source", "scripts", "lineage"):
        (bundle / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree(D_PARENT / "case", case, copy_function=shutil.copy2)
    control = case / "system/controlDict"
    original_control = control.read_text(encoding="utf-8")
    changed, count_start = re.subn(
        r"(?m)^startFrom\s+\S+\s*;", "startFrom latestTime;", original_control
    )
    changed, count_end = re.subn(r"(?m)^endTime\s+\S+\s*;", f"endTime {end_iteration};", changed)
    if count_start != 1 or count_end != 1:
        raise RuntimeError(f"expected one startFrom/endTime entry, found {count_start}/{count_end}")
    control.write_text(changed, encoding="utf-8")
    if re.sub(r"(?m)^startFrom\s+\S+\s*;", "startFrom startTime;", changed) != re.sub(
        r"(?m)^endTime\s+\S+\s*;", f"endTime {end_iteration};", original_control
    ):
        raise RuntimeError(
            "controlDict contains unexpected changes beyond the declared continuation settings"
        )
    shutil.copy2(D_PARENT / "scripts/run_solver.sh", bundle / "scripts/run_solver.sh")
    (bundle / "scripts/run_solver.sh").chmod(0o755)
    shutil.copy2(Path(__file__).resolve(), bundle / "source/prepare_i4f_wet_branch_extension.py")
    for name, source in (
        ("preparation.json", D_PARENT / "preparation.json"),
        ("terminal.json", parent_terminal_path),
        ("endpoint-analysis.json", D_PARENT / "analysis/steady-endpoint-analysis.json"),
        ("input-freeze.json", D_PARENT / "input-freeze.json"),
    ):
        shutil.copy2(source, bundle / "lineage" / name)

    checkpoint_manifest = []
    for source in sorted(checkpoint.iterdir()):
        if not source.is_file():
            continue
        target = case / latest / source.name
        source_hash = digest(source)
        target_hash = digest(target)
        if source_hash != target_hash or source.stat().st_ino == target.stat().st_ino:
            raise RuntimeError(f"restart field copy mismatch or shared inode: {source.name}")
        checkpoint_manifest.append(
            {
                "field": source.name,
                "bytes": source.stat().st_size,
                "sha256": source_hash,
                "parent_inode": source.stat().st_ino,
                "continuation_inode": target.stat().st_ino,
            }
        )
    if not required.issubset({row["field"] for row in checkpoint_manifest}):
        raise RuntimeError("restart manifest omitted one or more required fields")

    parent_freeze = json.loads((D_PARENT / "input-freeze.json").read_text(encoding="utf-8"))
    changed_inputs = []
    for row in parent_freeze["files"]:
        name = row["path"]
        if digest(D_PARENT / "case" / name) != digest(case / name):
            changed_inputs.append(name)
    if changed_inputs != ["system/controlDict"]:
        raise RuntimeError(
            f"continuation differs from frozen D inputs beyond controlDict: {changed_inputs}"
        )

    metadata = {
        "schema": "i4f-wet-branch-outlet-extension-continuation/v1",
        "created_utc": now_utc(),
        "purpose": "Continue the bounded D steady hydraulic diagnostic from its captured iteration-3000 endpoint to iteration 9000 without changing geometry, fields, equations, residual controls, or boundary conditions.",
        "parent_bundle": str(D_PARENT),
        "parent_container_id": terminal["container_id"],
        "parent_started_at": terminal["started_at"],
        "parent_terminal_sha256": digest(parent_terminal_path),
        "parent_input_freeze_sha256": digest(D_PARENT / "input-freeze.json"),
        "flow_setup": parent_prep["flow_setup"],
        "physics_and_solver": parent_prep["parent_physics"],
        "mesh_and_geometry": parent_prep["geometry_change"],
        "restart": {
            "mode": "OpenFOAM startFrom latestTime",
            "parent_latest_time_label": latest,
            "interpretation": "simpleFoam iteration index; not physical seconds",
            "required_fields": sorted(required),
            "checkpoint_files": checkpoint_manifest,
            "full_checkpoint_directory_copied": True,
            "checkpoint_inodes_independent": True,
        },
        "declared_control_changes": {
            "startFrom": ["startTime", "latestTime"],
            "endTime_iteration": [3000, end_iteration],
            "all_other_controlDict_content_unchanged": True,
        },
        "changed_frozen_parent_inputs": changed_inputs,
        "same_geometry_fields_physics_numerics_residual_controls": True,
        "resource_budget": {
            "cpu_quota": 0.75,
            "memory_bytes": 4 * 1024**3,
            "hard_wall_seconds": 1800,
            "graceful_write_seconds": 1500,
        },
        "success_interpretation": "Continue only to assess residual settlement; bounded endpoint alone does not mean convergence or an accepted hydraulic reference.",
        "source_image": IMAGE,
        "preparation_script_sha256": digest(Path(__file__).resolve()),
    }
    helper.atomic_json(bundle / "preparation.json", metadata)
    freeze = helper.freeze_inputs(bundle)
    metadata["input_freeze_sha256"] = digest(bundle / "input-freeze.json")
    metadata["input_file_count"] = len(freeze["files"])
    metadata["case_log_parent_sha256"] = digest(D_PARENT / "case/log.simpleFoam")
    helper.atomic_json(bundle / "preparation.json", metadata)
    helper.verify_freeze(bundle)
    helper.atomic_json(
        bundle / "restart-checkpoint.json",
        {
            "schema": "i4f-wet-branch-simplefoam-restart-checkpoint/v1",
            "captured_from_parent_at_utc": terminal["captured_utc"],
            "parent_terminal_sha256": digest(parent_terminal_path),
            "time_label": latest,
            "interpretation": "steady iteration index, not physical seconds",
            "files": checkpoint_manifest,
        },
    )
    return {
        "bundle": str(bundle),
        "input_freeze_sha256": metadata["input_freeze_sha256"],
        "changed_frozen_parent_inputs": changed_inputs,
        "restart_time_label": latest,
        "checkpoint_files": len(checkpoint_manifest),
        "target_iteration": end_iteration,
        "checkpoint_fields": sorted(required),
    }


def run_mesh(bundle: Path) -> None:
    helper = load_helper()
    bundle = bundle.resolve(strict=True)
    case = bundle / "case"
    if not case.is_dir() or not (case / "system/extrudeMeshDict").is_file():
        raise FileNotFoundError("prepared case or extrudeMeshDict missing")
    prior = sorted(bundle.glob("logs/mesh-utility-run-attempt*.json"))
    attempt = len(prior) + 1 + int((bundle / "logs/mesh-utility-run.json").exists())
    mesh_script_path = bundle / "scripts/mesh_extension.sh"
    mesh_script_path.write_text(mesh_script(attempt), encoding="utf-8")
    mesh_script_path.chmod(0o755)
    dict_path = case / "system/extrudeMeshDict"
    dict_before = None
    if dict_path.is_file():
        dict_before = digest(dict_path)
        shutil.copy2(dict_path, bundle / f"logs/extrudeMeshDict-before-attempt{attempt:03d}")
    dict_path.write_text(extrude_mesh_dict(case), encoding="utf-8")
    source_snapshot = (
        bundle / "source" / f"prepare_i4f_wet_branch_extension-attempt{attempt:03d}.py"
    )
    shutil.copy2(Path(__file__).resolve(), source_snapshot)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--cpus=0.75",
        "--memory=4g",
        "--log-driver=none",
        "-v",
        f"{case}:/case",
        "-v",
        f"{bundle}:/bundle",
        "-w",
        "/case",
        IMAGE,
        "bash",
        "/bundle/scripts/mesh_extension.sh",
    ]
    run = [
        sys.executable,
        str(ROOT / "scripts/run_local.py"),
        "--threads",
        "1",
        "--timeout",
        "600",
        "--",
        "nice",
        "-n",
        "19",
        *cmd,
    ]
    result = subprocess.run(run, cwd=ROOT, capture_output=True, text=True, check=False, timeout=660)
    helper.atomic_json(
        bundle / f"logs/mesh-utility-run-attempt{attempt:03d}.json",
        {
            "schema": "i4f-wet-branch-extension-mesh-run/v1",
            "attempt": attempt,
            "created_utc": now_utc(),
            "command": run,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "script_sha256": digest(Path(__file__).resolve()),
            "previous_extrudeMeshDict_sha256": dict_before,
            "extrudeMeshDict_sha256": digest(dict_path),
        },
    )
    if result.returncode:
        raise RuntimeError(
            f"extrudeMesh utility failed with exit {result.returncode}; see logs/mesh-utility-run-attempt{attempt:03d}.json"
        )


def update_pressure_boundary(bundle: Path) -> dict[str, Any]:
    helper = load_helper()
    bundle = bundle.resolve(strict=True)
    case = bundle / "case"
    mesh = case / "constant/polyMesh"
    centers, sf, area, patch = parse_patch_faces(helper, mesh, OUTLET_NAME)
    if patch["count"] != 384:
        raise ValueError(f"new wetOutlet has {patch['count']} faces, expected 384")
    xspan = np.ptp(centers[:, 0])
    if float(xspan) > 1e-8 or abs(float(np.mean(centers[:, 0])) - OUTLET_PLANE_X_M) > 1e-8:
        raise ValueError(
            f"new wetOutlet is not the declared flat x={OUTLET_PLANE_X_M} plane: {centers[:, 0].min()}..{centers[:, 0].max()}"
        )
    prep = json.loads((bundle / "preparation.json").read_text())
    xref = np.asarray(prep["parent_flow_setup"]["pressure_reference_xyz_m"], dtype=float)
    gravity = np.asarray(prep["parent_physics"]["gravity_xyz_m_s2"], dtype=float)
    values = -np.einsum("i,ji->j", gravity, centers - xref)
    pfile = case / "0/p"
    before = pfile.read_text(encoding="utf-8")
    after = replace_patch_scalar_values(before, OUTLET_NAME, values)
    pfile.write_text(after, encoding="utf-8")
    result = {
        "new_outlet_patch": patch,
        "v2512_fv_area_m2": area,
        "absolute_first_vertex_fan_area_m2": patch["absolute_first_vertex_fan_area_m2"],
        "signed_projected_x_area_m2": float(sf[:, 0].sum()),
        "center_x_range_m": [float(centers[:, 0].min()), float(centers[:, 0].max())],
        "pressure_boundary_value_count": len(values),
        "pressure_formula": "pSolver=-g dot (Cf-xref), where Cf uses OpenFOAM v2512 face::centre area-magnitude weighting",
        "pressure_values_sha256": hashlib.sha256(
            np.asarray(values, dtype="<f8").tobytes()
        ).hexdigest(),
        "p_file_before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "p_file_after_sha256": digest(pfile),
    }
    helper.atomic_json(bundle / "logs/new-outlet-boundary.json", result)
    return result


def freeze_case(bundle: Path) -> dict[str, Any]:
    """Freeze the final remeshed case only after all geometry and BC edits."""
    helper = load_helper()
    bundle = bundle.resolve(strict=True)
    prep_path = bundle / "preparation.json"
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    if not (bundle / "logs/new-outlet-boundary.json").is_file():
        raise RuntimeError("run update-pressure after extrusion before freezing the case")
    validation = bundle / "analysis/geometry-validation.json"
    if not validation.is_file():
        raise RuntimeError("run the native geometry validation before freezing inputs")
    freeze = helper.freeze_inputs(bundle)
    prep["geometry_validation_pending"] = False
    prep["geometry_validation"] = {
        "path": str(validation.relative_to(bundle)),
        "sha256": digest(validation),
    }
    prep["processors10_qualification"] = (
        "Copied from the immutable parent for lineage only; mesh was extended in the undecomposed serial case and these decomposition files are not valid for this geometry or usable by the declared serial solver."
    )
    prep["preparation_script_sha256"] = digest(Path(__file__).resolve())
    prep["final_preparation_script_snapshot"] = {
        "path": "source/prepare_i4f_wet_branch_extension-final.py",
        "sha256": digest(Path(__file__).resolve()),
    }
    prep["final_mesh_sha256"] = {
        name: digest(bundle / "case/constant/polyMesh" / name)
        for name in ("points", "faces", "owner", "neighbour", "boundary")
    }
    prep["input_freeze_sha256"] = helper.sha256_file(bundle / "input-freeze.json")
    prep["frozen_input_file_count"] = len(freeze["files"])
    helper.atomic_json(prep_path, prep)
    final_source = bundle / "source/prepare_i4f_wet_branch_extension-final.py"
    shutil.copy2(Path(__file__).resolve(), final_source)
    helper.verify_freeze(bundle)
    return {"input_freeze_sha256": prep["input_freeze_sha256"], "files": len(freeze["files"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--bundle", type=Path, required=True)
    c = sub.add_parser("prepare-cf-control")
    c.add_argument("--bundle", type=Path, required=True)
    cf = sub.add_parser("finalize-cf-control")
    cf.add_argument("--bundle", type=Path, required=True)
    e = sub.add_parser("prepare-continuation")
    e.add_argument("--bundle", type=Path, required=True)
    e.add_argument("--end-iteration", type=int, default=9000)
    m = sub.add_parser("mesh")
    m.add_argument("--bundle", type=Path, required=True)
    u = sub.add_parser("update-pressure")
    u.add_argument("--bundle", type=Path, required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--bundle", type=Path, required=True)
    launch_parser = sub.add_parser("launch")
    launch_parser.add_argument("--bundle", type=Path, required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.bundle)
    elif args.command == "prepare-cf-control":
        print(json.dumps(prepare_parent_cf_control(args.bundle), indent=2, sort_keys=True))
    elif args.command == "finalize-cf-control":
        print(json.dumps(finalize_parent_cf_control(args.bundle), indent=2, sort_keys=True))
    elif args.command == "prepare-continuation":
        print(
            json.dumps(
                prepare_d_continuation(args.bundle, args.end_iteration), indent=2, sort_keys=True
            )
        )
    elif args.command == "mesh":
        run_mesh(args.bundle)
    elif args.command == "update-pressure":
        print(json.dumps(update_pressure_boundary(args.bundle), indent=2))
    elif args.command == "freeze":
        print(json.dumps(freeze_case(args.bundle), indent=2))
    elif args.command == "launch":
        print(load_helper().launch_guarded(args.bundle))
    elif args.command == "analyze":
        print(
            json.dumps(
                load_helper().analyze_endpoint(args.bundle, "analysis.json"),
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
