#!/usr/bin/env python3
"""Audit native finite-volume divergence for periodic interface-wave runs.

The audit uses OpenFOAM's saved surfaceScalarField ``phi`` and mesh owner /
neighbour addressing.  It computes each cell's net outward face flux and
divides by its volume; it does not infer divergence from cell-centred U.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

COUPLED_PATCH_TYPES = frozenset(
    {
        "cyclic",
        "cyclicAMI",
        "cyclicACMI",
        "processor",
        "processorCyclic",
        "regionCoupled",
    }
)
EXPECTED_PHI_DIMENSIONS = (0, 3, -1, 0, 0, 0, 0)
EXPECTED_DIV_PHI_DIMENSIONS = (0, 0, -1, 0, 0, 0, 0)
EXPECTED_ALPHA_DIMENSIONS = (0, 0, 0, 0, 0, 0, 0)


class AuditError(ValueError):
    """Raised when a case cannot be audited without ambiguous assumptions."""


@dataclass(frozen=True)
class Patch:
    name: str
    patch_type: str
    start_face: int
    n_faces: int
    neighbour_patch: str | None = None

    @property
    def coupled(self) -> bool:
        return self.patch_type in COUPLED_PATCH_TYPES


@dataclass(frozen=True)
class MeshAddressing:
    owner: np.ndarray
    neighbour: np.ndarray
    patches: tuple[Patch, ...]
    n_cells: int


@dataclass(frozen=True)
class FoamField:
    name: str
    field_class: str
    dimensions: tuple[int, ...]
    internal: np.ndarray
    boundary: dict[str, np.ndarray]


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def _balanced_end(text: str, start: int, opening: str, closing: str) -> int:
    if start >= len(text) or text[start] != opening:
        raise AuditError(f"expected {opening!r} at character {start}")
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    raise AuditError(f"unclosed {opening!r} block")


def _named_blocks(body: str) -> dict[str, str]:
    """Parse top-level ``name { ... }`` entries from a Foam dictionary body."""
    blocks: dict[str, str] = {}
    index = 0
    while index < len(body):
        while index < len(body) and (body[index].isspace() or body[index] in ";()"):
            index += 1
        if index >= len(body):
            break
        match = re.match(r"[A-Za-z_][A-Za-z0-9_.-]*", body[index:])
        if match is None:
            index += 1
            continue
        name = match.group(0)
        index += len(name)
        while index < len(body) and body[index].isspace():
            index += 1
        if index >= len(body) or body[index] != "{":
            index = body.find(";", index)
            if index < 0:
                break
            index += 1
            continue
        end = _balanced_end(body, index, "{", "}")
        if name in blocks:
            raise AuditError(f"duplicate Foam dictionary entry {name}")
        blocks[name] = body[index + 1 : end]
        index = end + 1
    return blocks


def _block_after(text: str, key: str) -> str:
    match = re.search(rf"\b{re.escape(key)}\s*\{{", text)
    if match is None:
        raise AuditError(f"missing {key} dictionary")
    start = text.find("{", match.start())
    end = _balanced_end(text, start, "{", "}")
    return text[start + 1 : end]


def _list_after_header(path: Path) -> tuple[int, str]:
    text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    match = re.search(r"\}\s*(\d+)\s*\(", text)
    if match is None:
        raise AuditError(f"cannot find Foam list after header in {path}")
    count = int(match.group(1))
    opening = text.find("(", match.start())
    end = _balanced_end(text, opening, "(", ")")
    return count, text[opening + 1 : end]


def read_label_list(path: Path) -> np.ndarray:
    count, body = _list_after_header(path)
    values = np.fromstring(body, sep=" ", dtype=np.int64)
    if values.size != count:
        raise AuditError(f"{path}: expected {count} labels, parsed {values.size}")
    return values


def read_mesh_addressing(case_dir: Path) -> MeshAddressing:
    mesh_dir = case_dir / "constant" / "polyMesh"
    owner = read_label_list(mesh_dir / "owner")
    neighbour = read_label_list(mesh_dir / "neighbour")
    raw_boundary = _strip_comments((mesh_dir / "boundary").read_text(encoding="utf-8"))
    list_match = re.search(r"\}\s*\d+\s*\(", raw_boundary)
    if list_match is None:
        raise AuditError(f"cannot find patch list in {mesh_dir / 'boundary'}")
    opening = raw_boundary.find("(", list_match.start())
    list_end = _balanced_end(raw_boundary, opening, "(", ")")
    patch_blocks = _named_blocks(raw_boundary[opening + 1 : list_end])
    patches = []
    for name, body in patch_blocks.items():
        patch_type = _required_word(body, "type", mesh_dir / "boundary" / name)
        start_face = _required_int(body, "startFace", mesh_dir / "boundary" / name)
        n_faces = _required_int(body, "nFaces", mesh_dir / "boundary" / name)
        neighbour_match = re.search(r"\bneighbourPatch\s+([^;\s]+)\s*;", body)
        patches.append(
            Patch(
                name=name,
                patch_type=patch_type,
                start_face=start_face,
                n_faces=n_faces,
                neighbour_patch=neighbour_match.group(1) if neighbour_match else None,
            )
        )
    patches.sort(key=lambda patch: patch.start_face)
    n_internal_faces = neighbour.size
    if owner.size <= n_internal_faces:
        raise AuditError("mesh has no boundary faces; expected explicit patch addressing")
    expected = np.arange(n_internal_faces, owner.size, dtype=np.int64)
    covered = (
        np.concatenate(
            [
                np.arange(patch.start_face, patch.start_face + patch.n_faces, dtype=np.int64)
                for patch in patches
            ]
        )
        if patches
        else np.array([], dtype=np.int64)
    )
    if not np.array_equal(np.sort(covered), expected):
        raise AuditError("boundary patches do not cover each boundary face exactly once")
    if np.any(owner < 0) or np.any(neighbour < 0):
        raise AuditError("negative owner/neighbour labels are unsupported")
    if np.any(neighbour >= owner.size):
        raise AuditError("invalid neighbour cell labels")
    n_cells = int(max(owner.max(initial=-1), neighbour.max(initial=-1)) + 1)
    if n_cells <= 0:
        raise AuditError("mesh addressing is empty")
    if np.any(owner >= n_cells) or np.any(neighbour >= n_cells):
        raise AuditError("invalid cell labels")
    return MeshAddressing(owner=owner, neighbour=neighbour, patches=tuple(patches), n_cells=n_cells)


def _required_word(body: str, key: str, location: Path) -> str:
    match = re.search(rf"\b{re.escape(key)}\s+([^;\s]+)\s*;", body)
    if match is None:
        raise AuditError(f"{location}: missing {key}")
    return match.group(1)


def _required_int(body: str, key: str, location: Path) -> int:
    value = _required_word(body, key, location)
    try:
        return int(value)
    except ValueError as error:
        raise AuditError(f"{location}: {key} must be an integer") from error


_FLOAT = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def _parse_scalar_list(text: str, expression: str, location: Path, expected: int) -> np.ndarray:
    match = re.search(expression, text, flags=re.DOTALL)
    if match is None:
        raise AuditError(f"{location}: missing scalar list")
    count = int(match.group(1))
    values = np.fromstring(match.group(2), sep=" ", dtype=np.float64)
    if count != expected or values.size != count:
        raise AuditError(
            f"{location}: expected {expected} scalar values; list declares {count}, parsed {values.size}"
        )
    return values


def _field_header(text: str, path: Path) -> tuple[str, str, tuple[int, ...]]:
    header = text[: text.find("internalField")]
    class_match = re.search(r"\bclass\s+([^;\s]+)\s*;", header)
    object_match = re.search(r"\bobject\s+([^;\s]+)\s*;", header)
    dimension_match = re.search(r"\bdimensions\s*\[([^\]]+)\]\s*;", text)
    if class_match is None or object_match is None or dimension_match is None:
        raise AuditError(f"{path}: missing class, object, or dimensions")
    try:
        dimensions = tuple(int(value) for value in dimension_match.group(1).split())
    except ValueError as error:
        raise AuditError(f"{path}: invalid dimensions") from error
    if len(dimensions) != 7:
        raise AuditError(f"{path}: expected seven OpenFOAM base dimensions")
    return object_match.group(1), class_match.group(1), dimensions


def _read_internal_scalar(text: str, path: Path, expected: int) -> np.ndarray:
    pattern = r"\binternalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;"
    match = re.search(pattern, text, flags=re.DOTALL)
    if match:
        return _parse_scalar_list(text, pattern, path, expected)
    uniform = re.search(rf"\binternalField\s+uniform\s+({_FLOAT})\s*;", text)
    if uniform:
        if expected <= 0:
            raise AuditError(f"{path}: invalid uniform-field size")
        return np.full(expected, float(uniform.group(1)), dtype=np.float64)
    raise AuditError(f"{path}: unsupported internalField format")


def read_volume_scalar_field(
    path: Path, expected_cells: int, expected_dimensions: tuple[int, ...]
) -> FoamField:
    text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    name, field_class, dimensions = _field_header(text, path)
    if field_class != "volScalarField":
        raise AuditError(f"{path}: expected volScalarField, found {field_class}")
    if dimensions != expected_dimensions:
        raise AuditError(f"{path}: dimensions {dimensions} != {expected_dimensions}")
    internal = _read_internal_scalar(text, path, expected_cells)
    boundary = {}
    boundary_body = _block_after(text, "boundaryField")
    for patch_name, body in _named_blocks(boundary_body).items():
        value_match = re.search(
            r"\bvalue\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;",
            body,
            flags=re.DOTALL,
        )
        if value_match:
            count = int(value_match.group(1))
            values = np.fromstring(value_match.group(2), sep=" ", dtype=np.float64)
            if values.size != count:
                raise AuditError(f"{path}: bad boundary scalar list for {patch_name}")
            boundary[patch_name] = values
        else:
            uniform = re.search(rf"\bvalue\s+uniform\s+({_FLOAT})\s*;", body)
            if uniform:
                boundary[patch_name] = np.array([float(uniform.group(1))], dtype=np.float64)
            else:
                boundary[patch_name] = np.array([], dtype=np.float64)
    return FoamField(name, field_class, dimensions, internal, boundary)


def read_volume_vector_internal(path: Path, expected_cells: int) -> np.ndarray:
    """Read the internal values of an ASCII ``volVectorField``."""
    text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    name, field_class, dimensions = _field_header(text, path)
    if field_class != "volVectorField":
        raise AuditError(f"{path}: expected volVectorField, found {field_class}")
    if dimensions != (0, 1, -1, 0, 0, 0, 0):
        raise AuditError(f"{path}: expected velocity dimensions, found {dimensions}")
    pattern = r"\binternalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;"
    match = re.search(pattern, text, flags=re.DOTALL)
    if match:
        count = int(match.group(1))
        tokens = re.findall(_FLOAT, match.group(2))
        if count != expected_cells or len(tokens) != 3 * count:
            raise AuditError(
                f"{path}: malformed vector list ({count} values, {len(tokens)} components)"
            )
        return np.asarray(tokens, dtype=np.float64).reshape((count, 3))
    uniform = re.search(
        rf"\binternalField\s+uniform\s*\(\s*({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})\s*\)\s*;",
        text,
    )
    if uniform:
        return np.broadcast_to(
            np.asarray([float(uniform.group(i)) for i in range(1, 4)]),
            (expected_cells, 3),
        ).copy()
    raise AuditError(f"{path}: unsupported vector internalField format")


def read_surface_scalar_field(path: Path, mesh: MeshAddressing) -> FoamField:
    text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    name, field_class, dimensions = _field_header(text, path)
    if field_class != "surfaceScalarField":
        raise AuditError(f"{path}: expected surfaceScalarField, found {field_class}")
    if dimensions != EXPECTED_PHI_DIMENSIONS:
        raise AuditError(f"{path}: phi dimensions {dimensions} != {EXPECTED_PHI_DIMENSIONS}")
    internal = _read_internal_scalar(text, path, mesh.neighbour.size)
    boundary_body = _block_after(text, "boundaryField")
    boundary_blocks = _named_blocks(boundary_body)
    all_faces = np.full(mesh.owner.size, np.nan, dtype=np.float64)
    all_faces[: mesh.neighbour.size] = internal
    boundary_values = {}
    for patch in mesh.patches:
        if patch.name not in boundary_blocks:
            raise AuditError(f"{path}: missing patch field {patch.name}")
        body = boundary_blocks[patch.name]
        match = re.search(
            r"\bvalue\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;",
            body,
            flags=re.DOTALL,
        )
        if match:
            count = int(match.group(1))
            values = np.fromstring(match.group(2), sep=" ", dtype=np.float64)
            if count != patch.n_faces or values.size != count:
                raise AuditError(f"{path}: boundary list length mismatch for {patch.name}")
        else:
            uniform = re.search(rf"\bvalue\s+uniform\s+({_FLOAT})\s*;", body)
            if uniform is None:
                raise AuditError(f"{path}: {patch.name} has no explicit face values")
            values = np.full(patch.n_faces, float(uniform.group(1)), dtype=np.float64)
        if np.any(np.isfinite(all_faces[patch.start_face : patch.start_face + patch.n_faces])):
            raise AuditError(f"{path}: overlapping boundary face assignments for {patch.name}")
        all_faces[patch.start_face : patch.start_face + patch.n_faces] = values
        boundary_values[patch.name] = values
    if not np.all(np.isfinite(all_faces)):
        raise AuditError(f"{path}: one or more face fluxes are missing or non-finite")
    return FoamField(name, field_class, dimensions, all_faces, boundary_values)


def uniform_cell_volumes(case_dir: Path, n_cells: int) -> tuple[np.ndarray, dict[str, Any]]:
    metadata_path = case_dir / "case-inputs.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        cell_size = tuple(float(x) for x in metadata["cell_size_m"])
        mesh_shape = tuple(int(x) for x in metadata["mesh"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot read structured cell sizes from {metadata_path}") from error
    if len(cell_size) != 3 or len(mesh_shape) != 3:
        raise AuditError("expected 3-D cell_size_m and mesh metadata")
    if math.prod(mesh_shape) != n_cells:
        raise AuditError(
            f"mesh metadata cell count {math.prod(mesh_shape)} != field count {n_cells}"
        )
    volume = math.prod(cell_size)
    if not math.isfinite(volume) or volume <= 0:
        raise AuditError("invalid cell volume")
    return np.full(n_cells, volume, dtype=np.float64), {
        "cell_size_m": list(cell_size),
        "mesh_shape_xyz": list(mesh_shape),
        "uniform_cell_volume_m3": volume,
        "domain_volume_m3": volume * n_cells,
        "volume_source": "declared structured uniform cell_size_m in case-inputs.json",
    }


def structured_periodic_gauss_divergence(
    velocity_m_s: np.ndarray,
    mesh_shape_xyz: tuple[int, int, int],
    cell_size_m: tuple[float, float, float],
) -> np.ndarray:
    """Reconstruct linear periodic face fluxes on the declared uniform box.

    For each coordinate direction, face-normal velocity is the arithmetic
    average of the two adjacent cell-centred values (including the periodic
    pair); oriented face fluxes are differenced and divided by cell volume.
    This is an initial-field check, not a substitute for saved solver ``phi``.
    """
    nx, ny, nz = mesh_shape_xyz
    dx, dy, dz = cell_size_m
    values = np.asarray(velocity_m_s, dtype=np.float64)
    if values.shape != (nx * ny * nz, 3):
        raise AuditError("initial velocity size does not match structured mesh dimensions")
    if not np.all(np.isfinite(values)):
        raise AuditError("initial velocity contains non-finite values")
    grid = values.reshape((nz, ny, nx, 3))
    divergence = np.zeros((nz, ny, nx), dtype=np.float64)
    for component, axis, spacing in ((0, 2, dx), (1, 1, dy), (2, 0, dz)):
        normal_velocity = grid[..., component]
        plus_face = 0.5 * (normal_velocity + np.roll(normal_velocity, -1, axis=axis))
        minus_face = np.roll(plus_face, 1, axis=axis)
        divergence += (plus_face - minus_face) / spacing
    return divergence.reshape(-1)


def phi_ascii_quantization_bound(
    mesh: MeshAddressing,
    face_flux_m3_s: np.ndarray,
    cell_volume_m3: np.ndarray,
    significant_digits: int,
) -> np.ndarray:
    """Per-cell worst-case div(phi) error from rounded ASCII face values.

    OpenFOAM's ``writePrecision`` is significant digits for these ASCII fields.
    Each face contributes half a decimal ULP to the owner cell; internal faces
    also contribute the same bound to the neighbour cell.
    """
    phi = np.asarray(face_flux_m3_s, dtype=np.float64)
    volume = np.asarray(cell_volume_m3, dtype=np.float64)
    if significant_digits <= 0:
        raise AuditError("writePrecision must be positive")
    if phi.shape != mesh.owner.shape or volume.shape != (mesh.n_cells,):
        raise AuditError("flux/volume arrays do not match mesh addressing")
    ulp = np.zeros_like(phi)
    nonzero = phi != 0.0
    ulp[nonzero] = 10.0 ** (np.floor(np.log10(np.abs(phi[nonzero]))) - significant_digits + 1)
    half_ulp = 0.5 * ulp
    net_bound = np.bincount(mesh.owner, weights=half_ulp, minlength=mesh.n_cells)
    net_bound += np.bincount(
        mesh.neighbour,
        weights=half_ulp[: mesh.neighbour.size],
        minlength=mesh.n_cells,
    )
    return net_bound / volume


def _write_precision(case_dir: Path) -> int | None:
    path = case_dir / "system" / "controlDict"
    if not path.is_file():
        return None
    match = re.search(r"\bwritePrecision\s+(\d+)\s*;", _strip_comments(path.read_text()))
    return int(match.group(1)) if match else None


def finite_volume_divergence(
    owner: np.ndarray,
    neighbour: np.ndarray,
    face_flux_m3_s: np.ndarray,
    cell_volume_m3: np.ndarray,
) -> np.ndarray:
    """Compute native Gauss finite-volume divergence from owner-oriented fluxes.

    Internal-face flux is outward from its owner and inward to its neighbour.
    Boundary-face flux contributes once to the owner cell. Coupled cyclic patch
    faces are each real boundary face of one cell; their paired global fluxes
    cancel and are never added as an extra ghost-face contribution.
    """
    owner = np.asarray(owner, dtype=np.int64)
    neighbour = np.asarray(neighbour, dtype=np.int64)
    phi = np.asarray(face_flux_m3_s, dtype=np.float64)
    volume = np.asarray(cell_volume_m3, dtype=np.float64)
    if owner.ndim != 1 or neighbour.ndim != 1 or phi.ndim != 1 or volume.ndim != 1:
        raise AuditError("owner, neighbour, flux and cell volume inputs must be vectors")
    if owner.size != phi.size or neighbour.size > owner.size:
        raise AuditError("face addressing and flux lengths do not agree")
    if owner.size == 0 or volume.size == 0:
        raise AuditError("empty mesh inputs")
    if np.any(owner < 0) or np.any(owner >= volume.size):
        raise AuditError("owner label is outside the cell-volume array")
    if np.any(neighbour < 0) or np.any(neighbour >= volume.size):
        raise AuditError("neighbour label is outside the cell-volume array")
    if not np.all(np.isfinite(phi)) or not np.all(np.isfinite(volume)) or np.any(volume <= 0):
        raise AuditError("fluxes must be finite and cell volumes finite and positive")
    net = np.bincount(owner, weights=phi, minlength=volume.size).astype(np.float64)
    net -= np.bincount(neighbour, weights=phi[: neighbour.size], minlength=volume.size)
    return net / volume


def _patch_flux_summaries(mesh: MeshAddressing, phi: np.ndarray) -> dict[str, Any]:
    patch_totals = {
        patch.name: float(phi[patch.start_face : patch.start_face + patch.n_faces].sum())
        for patch in mesh.patches
    }
    physical = [patch for patch in mesh.patches if not patch.coupled]
    coupled = [patch for patch in mesh.patches if patch.coupled]
    pairs = []
    visited: set[str] = set()
    by_name = {patch.name: patch for patch in mesh.patches}
    for patch in coupled:
        peer = patch.neighbour_patch
        if peer is None or patch.name in visited:
            continue
        peer_patch = by_name.get(peer)
        if peer_patch is None or not peer_patch.coupled:
            continue
        pairs.append(
            {
                "patches": [patch.name, peer],
                "signed_flux_sum_m3_s": patch_totals[patch.name] + patch_totals[peer],
            }
        )
        visited.add(patch.name)
        visited.add(peer)
    return {
        "patch_signed_flux_m3_s": patch_totals,
        "physical_boundary_flux_m3_s": float(sum(patch_totals[p.name] for p in physical)),
        "coupled_patch_flux_sum_m3_s": float(sum(patch_totals[p.name] for p in coupled)),
        "coupled_patch_names_excluded_from_physical_boundary_total": [p.name for p in coupled],
        "coupled_patch_pair_sums_m3_s": pairs,
    }


def _fourier_amplitude(values: np.ndarray, mode_number: int) -> tuple[float, float]:
    coefficient = 2.0 * np.fft.rfft(values)[mode_number] / values.size
    return float(abs(coefficient)), float(np.angle(coefficient))


def volume_interface_mode(
    alpha: np.ndarray,
    mesh_shape_xyz: tuple[int, int, int],
    cell_size_m: tuple[float, float, float],
    *,
    lower_z_m: float = 0.03,
    upper_z_m: float = 0.09,
    mode_number: int = 1,
) -> dict[str, Any]:
    """Estimate interface displacement Fourier modes from vertical alpha volume.

    This mass-column observer is distinct from linear reconstruction of the
    alpha=0.5 contour, allowing a discretization cross-check.
    """
    nx, ny, nz = mesh_shape_xyz
    dx, _dy, dz = cell_size_m
    if alpha.size != nx * ny * nz:
        raise AuditError("alpha field size does not match structured mesh dimensions")
    if not np.all(np.isfinite(alpha)):
        raise AuditError("alpha field contains non-finite values")
    if mode_number < 0 or mode_number > nx // 2:
        raise AuditError("Fourier mode is outside the x-grid Nyquist range")
    grid = np.asarray(alpha, dtype=np.float64).reshape((nz, ny, nx))
    xz = grid.mean(axis=1)
    zlo = np.arange(nz, dtype=np.float64) * dz
    zhi = zlo + dz
    zc = 0.5 * (zlo + zhi)
    lower_ref = np.clip((zhi - lower_z_m) / dz, 0.0, 1.0)[:, None]
    upper_ref = np.clip((upper_z_m - zlo) / dz, 0.0, 1.0)[:, None]
    lower_mask = np.abs(zc - lower_z_m) <= 0.018
    upper_mask = np.abs(zc - upper_z_m) <= 0.018
    lower_eta = -dz * np.sum(xz[lower_mask] - lower_ref[lower_mask], axis=0)
    upper_eta = dz * np.sum(xz[upper_mask] - upper_ref[upper_mask], axis=0)
    lower_eta -= lower_eta.mean()
    upper_eta -= upper_eta.mean()
    symmetric = 0.5 * (lower_eta + upper_eta)
    antisymmetric = 0.5 * (lower_eta - upper_eta)
    lower_amp, lower_phase = _fourier_amplitude(lower_eta, mode_number)
    upper_amp, upper_phase = _fourier_amplitude(upper_eta, mode_number)
    sym_amp, sym_phase = _fourier_amplitude(symmetric, mode_number)
    anti_amp, anti_phase = _fourier_amplitude(antisymmetric, mode_number)
    return {
        "method": "volume-column displacement relative to flat alpha reference",
        "interface_reference_z_m": {"lower": lower_z_m, "upper": upper_z_m},
        "mode_number_x": mode_number,
        "wavelength_x_m": nx * dx / mode_number if mode_number else None,
        "lower_interface_amplitude_m": lower_amp,
        "upper_interface_amplitude_m": upper_amp,
        "symmetric_amplitude_m": sym_amp,
        "antisymmetric_amplitude_m": anti_amp,
        "lower_phase_rad": lower_phase,
        "upper_phase_rad": upper_phase,
        "symmetric_phase_rad": sym_phase,
        "antisymmetric_phase_rad": anti_phase,
    }


def alpha_half_crossing_mode(
    alpha: np.ndarray,
    mesh_shape_xyz: tuple[int, int, int],
    cell_size_m: tuple[float, float, float],
    *,
    lower_z_m: float = 0.03,
    upper_z_m: float = 0.09,
    mode_number: int = 1,
) -> dict[str, Any]:
    """Cell-to-vertex reconstruct alpha, track directed 0.5 contours, project modes."""
    nx, ny, nz = mesh_shape_xyz
    dx, _dy, dz = cell_size_m
    if alpha.size != nx * ny * nz:
        raise AuditError("alpha field size does not match structured mesh dimensions")
    if mode_number < 0 or mode_number > nx // 2:
        raise AuditError("Fourier mode is outside the x-grid Nyquist range")
    grid = np.asarray(alpha, dtype=np.float64).reshape((nz, ny, nx))
    if not np.all(np.isfinite(grid)):
        raise AuditError("alpha field contains non-finite values")
    # Periodic arithmetic averaging of the eight cell-centre neighbours gives
    # the standard linear cell-to-vertex reconstruction for an orthogonal box.
    point_alpha = np.zeros_like(grid)
    for z_shift in (0, 1):
        for y_shift in (0, 1):
            for x_shift in (0, 1):
                point_alpha += np.roll(grid, (z_shift, y_shift, x_shift), axis=(0, 1, 2)) / 8.0
    z_vertices = np.arange(nz, dtype=np.float64) * dz
    displacements = {"lower": [], "upper": []}
    crossing_counts = {"lower": [], "upper": []}
    coverage = {"lower": [], "upper": []}
    for name, reference, rising in (
        ("lower", lower_z_m, True),
        ("upper", upper_z_m, False),
    ):
        if rising:
            crossing_mask = (point_alpha[:-1] < 0.5) & (point_alpha[1:] >= 0.5)
        else:
            crossing_mask = (point_alpha[:-1] >= 0.5) & (point_alpha[1:] < 0.5)
        band_center = 0.5 * (z_vertices[:-1] + z_vertices[1:])
        band = np.abs(band_center - reference) <= 0.018
        candidates = crossing_mask & band[:, None, None]
        distances = np.where(
            candidates,
            np.abs(band_center - reference)[:, None, None],
            np.inf,
        )
        index = np.argmin(distances, axis=0)
        valid = np.isfinite(np.min(distances, axis=0))
        if not np.any(valid):
            raise AuditError(f"no directed alpha=0.5 {name} interface crossings")
        a0 = np.take_along_axis(point_alpha[:-1], index[None, :, :], axis=0)[0]
        a1 = np.take_along_axis(point_alpha[1:], index[None, :, :], axis=0)[0]
        z0 = z_vertices[index]
        fraction = (0.5 - a0) / np.where(np.abs(a1 - a0) > 1e-15, a1 - a0, 1.0)
        z_cross = z0 + fraction * dz
        eta_yx = np.where(valid, z_cross - reference, np.nan)
        with np.errstate(invalid="ignore"):
            eta_x = np.nanmean(eta_yx, axis=0)
        if not np.all(np.isfinite(eta_x)):
            missing = np.flatnonzero(~np.isfinite(eta_x))
            raise AuditError(f"{name} contour missing from x-columns {missing[:8].tolist()}")
        displacements[name] = eta_x.tolist()
        crossing_counts[name] = np.count_nonzero(candidates, axis=(0, 1)).tolist()
        coverage[name] = valid.mean(axis=0).tolist()
    lower_eta = np.asarray(displacements["lower"], dtype=np.float64)
    upper_eta = np.asarray(displacements["upper"], dtype=np.float64)
    lower_eta -= lower_eta.mean()
    upper_eta -= upper_eta.mean()
    symmetric = 0.5 * (lower_eta + upper_eta)
    antisymmetric = 0.5 * (lower_eta - upper_eta)
    lower_amp, lower_phase = _fourier_amplitude(lower_eta, mode_number)
    upper_amp, upper_phase = _fourier_amplitude(upper_eta, mode_number)
    sym_amp, sym_phase = _fourier_amplitude(symmetric, mode_number)
    anti_amp, anti_phase = _fourier_amplitude(antisymmetric, mode_number)
    return {
        "method": "cell-to-vertex linear reconstruction of periodic alpha, directed alpha=0.5 crossings, transverse average",
        "interface_reference_z_m": {"lower": lower_z_m, "upper": upper_z_m},
        "mode_number_x": mode_number,
        "wavelength_x_m": nx * dx / mode_number if mode_number else None,
        "lower_interface_amplitude_m": lower_amp,
        "upper_interface_amplitude_m": upper_amp,
        "symmetric_amplitude_m": sym_amp,
        "antisymmetric_amplitude_m": anti_amp,
        "lower_phase_rad": lower_phase,
        "upper_phase_rad": upper_phase,
        "symmetric_phase_rad": sym_phase,
        "antisymmetric_phase_rad": anti_phase,
        "crossings_per_x_column": {
            name: {
                "minimum": int(min(counts)),
                "maximum": int(max(counts)),
                "total": int(sum(counts)),
            }
            for name, counts in crossing_counts.items()
        },
        "transverse_coverage_fraction": {
            name: float(np.mean(values)) for name, values in coverage.items()
        },
    }


def compare_writer_row(writer_row: dict[str, str], recomputed: dict[str, Any]) -> dict[str, Any]:
    comparisons = {}
    scalar_fields: dict[str, tuple[str, ...]] = {
        "sum_V_div_phi_m3_s": ("sum_V_div_phi_m3_s",),
        "sum_V_abs_div_phi_m3_s": ("sum_V_abs_div_phi_m3_s",),
        "max_abs_div_phi_s_inv": ("max_abs_div_phi_s_inv",),
        "sum_V_alpha_div_phi_m3_s": ("sum_V_alpha_div_phi_m3_s_diagnostic_only",),
        "native_water_volume_m3": ("water_volume_m3",),
        "water_volume_m3": ("water_volume_m3",),
        "cell_count": ("cell_count",),
        "cell_volume_m3": ("uniform_cell_volume_m3",),
        "alpha_mode_amplitude_m": (
            "alpha_volume_fourier_observer",
            "symmetric_amplitude_m",
        ),
        "alpha05_mode_amplitude_m": (
            "alpha_half_fourier_observer",
            "symmetric_amplitude_m",
        ),
    }
    for source_key, audit_path in scalar_fields.items():
        raw = writer_row.get(source_key, "")
        if raw is None or not raw.strip():
            continue
        value_from_audit: Any = recomputed
        for key in audit_path:
            if not isinstance(value_from_audit, dict) or key not in value_from_audit:
                value_from_audit = None
                break
            value_from_audit = value_from_audit[key]
        if value_from_audit is None:
            continue
        try:
            value = float(raw)
        except ValueError:
            comparisons[source_key] = {"writer_value": raw, "status": "not_numeric"}
            continue
        recomputed_value = float(value_from_audit)
        comparisons[source_key] = {
            "writer_value": value,
            "audit_value": recomputed_value,
            "difference_audit_minus_writer": recomputed_value - value,
        }
    other = {
        key: value
        for key, value in writer_row.items()
        if key not in scalar_fields and value is not None and value != ""
    }
    return {"scalar_comparisons": comparisons, "other_writer_columns": other}


def _load_writer_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise AuditError(f"writer summary is empty: {path}")
    return rows


def _native_times(case_dir: Path) -> list[tuple[float, Path]]:
    if any(case_dir.glob("processor[0-9]*")):
        # A reconstructed serial case has both global fields and mesh at the
        # root; local processor boundaries would need coupled-face exchange.
        if not any((path / "phi").is_file() for path in case_dir.iterdir() if path.is_dir()):
            raise AuditError(f"{case_dir}: decomposed-only fields cannot be audited as serial")
    times = []
    for path in case_dir.iterdir():
        if (
            not path.is_dir()
            or path.name in {"0", "constant", "system"}
            or path.name.startswith("processor")
        ):
            continue
        try:
            value = float(path.name)
        except ValueError:
            continue
        if (path / "phi").is_file() and (path / "alpha.water").is_file():
            times.append((value, path))
    return sorted(times, key=lambda item: item[0])


def audit_time(
    case_dir: Path,
    time_s: float,
    time_dir: Path,
    *,
    writer_row: dict[str, str] | None = None,
    rho_water_kg_m3: float = 1000.0,
) -> dict[str, Any]:
    mesh = read_mesh_addressing(case_dir)
    volumes, volume_metadata = uniform_cell_volumes(case_dir, mesh.n_cells)
    phi_field = read_surface_scalar_field(time_dir / "phi", mesh)
    alpha_field = read_volume_scalar_field(
        time_dir / "alpha.water", mesh.n_cells, EXPECTED_ALPHA_DIMENSIONS
    )
    div_path = time_dir / "divPhi"
    saved_div_field = (
        read_volume_scalar_field(div_path, mesh.n_cells, EXPECTED_DIV_PHI_DIMENSIONS)
        if div_path.is_file()
        else None
    )
    phi = phi_field.internal
    alpha = alpha_field.internal
    reconstructed_div_phi = finite_volume_divergence(mesh.owner, mesh.neighbour, phi, volumes)
    div_phi = saved_div_field.internal if saved_div_field is not None else reconstructed_div_phi
    patch_summary = _patch_flux_summaries(mesh, phi)
    signed_integral = float(np.dot(volumes, div_phi))
    reconstructed_signed_integral = float(np.dot(volumes, reconstructed_div_phi))
    boundary_total = float(
        sum(
            phi[patch.start_face : patch.start_face + patch.n_faces].sum() for patch in mesh.patches
        )
    )
    water_volume = float(np.dot(alpha, volumes))
    metrics: dict[str, Any] = {
        "time_s": time_s,
        "cell_count": mesh.n_cells,
        **volume_metadata,
        "phi_dimensions": list(phi_field.dimensions),
        "div_phi_dimensions": list(EXPECTED_DIV_PHI_DIMENSIONS),
        "alpha_dimensions": list(alpha_field.dimensions),
        "divergence_source": "saved OpenFOAM divPhi"
        if saved_div_field is not None
        else "independent phi reconstruction",
        "sum_V_div_phi_m3_s": signed_integral,
        "sum_V_abs_div_phi_m3_s": float(np.dot(volumes, np.abs(div_phi))),
        "max_abs_div_phi_s_inv": float(np.max(np.abs(div_phi))),
        "rms_div_phi_s_inv_volume_weighted": float(
            math.sqrt(float(np.dot(volumes, div_phi**2) / volumes.sum()))
        ),
        "boundary_flux_sum_m3_s": boundary_total,
        "boundary_vs_volume_integral_difference_m3_s": reconstructed_signed_integral
        - boundary_total,
        "water_volume_m3": water_volume,
        "water_mass_kg": rho_water_kg_m3 * water_volume,
        "alpha_min": float(alpha.min()),
        "alpha_max": float(alpha.max()),
        "sum_V_alpha_div_phi_m3_s_diagnostic_only": float(np.dot(volumes, alpha * div_phi)),
        "phi_reconstructed_divergence": {
            "sum_V_div_phi_m3_s": reconstructed_signed_integral,
            "sum_V_abs_div_phi_m3_s": float(np.dot(volumes, np.abs(reconstructed_div_phi))),
            "max_abs_div_phi_s_inv": float(np.max(np.abs(reconstructed_div_phi))),
            "rms_div_phi_s_inv_volume_weighted": float(
                math.sqrt(float(np.dot(volumes, reconstructed_div_phi**2) / volumes.sum()))
            ),
        },
        **patch_summary,
    }
    if saved_div_field is not None:
        difference = reconstructed_div_phi - saved_div_field.internal
        precision = _write_precision(case_dir)
        quantization_bound = (
            phi_ascii_quantization_bound(mesh, phi, volumes, precision)
            if precision is not None
            else None
        )
        exceeds_bound_count = None
        max_bound = None
        max_difference_index = int(np.argmax(np.abs(difference)))
        if quantization_bound is not None:
            # The native volScalarField is also rounded on output. Its decimal
            # half-ULP is tiny relative to divPhi in this run, but include it
            # so the comparison remains conservative for near-zero fields.
            saved_roundoff = np.zeros_like(saved_div_field.internal)
            nonzero_saved = saved_div_field.internal != 0.0
            saved_roundoff[nonzero_saved] = 0.5 * 10.0 ** (
                np.floor(np.log10(np.abs(saved_div_field.internal[nonzero_saved]))) - precision + 1
            )
            total_bound = quantization_bound + saved_roundoff
            exceeds_bound_count = int(np.count_nonzero(np.abs(difference) > total_bound))
            max_bound = float(np.max(quantization_bound))
        metrics["saved_divPhi_check"] = {
            "field": str(div_path.relative_to(case_dir)),
            "max_abs_difference_s_inv": float(np.max(np.abs(difference))),
            "max_abs_difference_cell": max_difference_index,
            "rms_difference_s_inv": float(math.sqrt(float(np.mean(difference**2)))),
            "l1_volume_difference_m3_s": float(np.dot(volumes, np.abs(difference))),
            "saved_sum_V_divPhi_m3_s": float(np.dot(volumes, saved_div_field.internal)),
            "saved_sum_V_abs_divPhi_m3_s": float(np.dot(volumes, np.abs(saved_div_field.internal))),
            "saved_max_abs_divPhi_s_inv": float(np.max(np.abs(saved_div_field.internal))),
            "saved_rms_divPhi_s_inv_volume_weighted": float(
                math.sqrt(float(np.dot(volumes, saved_div_field.internal**2) / volumes.sum()))
            ),
            "phi_ascii_write_precision_significant_digits": precision,
            "maximum_phi_text_quantization_bound_s_inv": max_bound,
            "cells_exceeding_phi_rounding_bound": exceeds_bound_count,
            "cellwise_phi_rounding_bound_check": (
                "saved-vs-recomputed difference should be interpreted against this bound; "
                "subtracting large rounded face fluxes can dominate near-zero divergence"
            ),
        }
    geometry = json.loads((case_dir / "case-inputs.json").read_text(encoding="utf-8"))
    mesh_shape = tuple(int(value) for value in geometry["mesh"])
    cell_size = tuple(float(value) for value in geometry["cell_size_m"])
    volume_mode = volume_interface_mode(alpha, mesh_shape, cell_size)
    contour_mode = alpha_half_crossing_mode(alpha, mesh_shape, cell_size)
    metrics["alpha_volume_fourier_observer"] = volume_mode
    metrics["alpha_half_fourier_observer"] = contour_mode
    metrics["alpha_half_minus_volume_symmetric_amplitude_m"] = (
        contour_mode["symmetric_amplitude_m"] - volume_mode["symmetric_amplitude_m"]
    )
    metrics["alpha_half_vs_volume_amplitude_relative_difference"] = metrics[
        "alpha_half_minus_volume_symmetric_amplitude_m"
    ] / max(volume_mode["symmetric_amplitude_m"], 1e-30)
    if writer_row is not None:
        metrics["writer_summary_comparison"] = compare_writer_row(writer_row, metrics)
    return metrics


def _case_dirs(run_or_case_dir: Path) -> list[Path]:
    if (run_or_case_dir / "case-inputs.json").is_file():
        return [run_or_case_dir]
    cases_dir = run_or_case_dir / "cases"
    if not cases_dir.is_dir():
        raise AuditError(f"expected case-inputs.json or cases/ under {run_or_case_dir}")
    case_dirs = sorted(
        path for path in cases_dir.iterdir() if (path / "case-inputs.json").is_file()
    )
    if not case_dirs:
        raise AuditError(f"no case-inputs.json files under {cases_dir}")
    return case_dirs


def audit_run(run_or_case_dir: Path, writer_csv: Path | None = None) -> dict[str, Any]:
    writer_rows = _load_writer_rows(writer_csv)
    groups: dict[str, list[dict[str, Any]]] = {}
    initial_checks: dict[str, dict[str, Any]] = {}
    for case_dir in _case_dirs(run_or_case_dir):
        case_metadata = json.loads((case_dir / "case-inputs.json").read_text())
        case_id = case_metadata.get("case_id", case_dir.name)
        initial_u_path = case_dir / "0" / "U"
        if initial_u_path.is_file():
            mesh = read_mesh_addressing(case_dir)
            volumes, volume_metadata = uniform_cell_volumes(case_dir, mesh.n_cells)
            velocity = read_volume_vector_internal(initial_u_path, mesh.n_cells)
            mesh_shape = tuple(int(value) for value in case_metadata["mesh"])
            cell_size = tuple(float(value) for value in case_metadata["cell_size_m"])
            initial_divergence = structured_periodic_gauss_divergence(
                velocity, mesh_shape, cell_size
            )
            initial_checks[case_id] = {
                "source_field": str(initial_u_path.relative_to(case_dir)),
                "native_t0_phi_available": (case_dir / "0" / "phi").is_file(),
                "finite_thickness_eigenmode_declared": bool(
                    case_metadata.get("finite_thickness_eigenmode", False)
                ),
                "method": "periodic Gauss-linear face interpolation of cell U on declared uniform orthogonal mesh",
                "initial_discrete_divergence_max_abs_s_inv": float(
                    np.max(np.abs(initial_divergence))
                ),
                "initial_discrete_divergence_rms_s_inv": float(
                    math.sqrt(float(np.dot(volumes, initial_divergence**2) / volumes.sum()))
                ),
                "initial_discrete_divergence_sum_V_abs_m3_s": float(
                    np.dot(volumes, np.abs(initial_divergence))
                ),
                "initial_discrete_divergence_sum_V_signed_m3_s": float(
                    np.dot(volumes, initial_divergence)
                ),
                "cell_volume_m3": volume_metadata["uniform_cell_volume_m3"],
                "interpretation": (
                    "reconstructed from initial cell-centred U because native t=0 phi is absent; "
                    "the result tests discrete linear periodic face interpolation, not solver startup"
                ),
            }
        else:
            initial_checks[case_id] = {
                "status": "initial 0/U field absent; no t=0 discrete divergence estimate",
                "native_t0_phi_available": (case_dir / "0" / "phi").is_file(),
            }
        case_rows = [
            row for row in writer_rows if not row.get("case_id") or row.get("case_id") == case_id
        ]
        results = []
        for time_s, time_dir in _native_times(case_dir):
            matching = [
                row
                for row in case_rows
                if "time_s" in row
                and math.isclose(float(row["time_s"]), time_s, rel_tol=0.0, abs_tol=5e-10)
            ]
            if len(matching) > 1:
                raise AuditError(f"{case_id} t={time_s:g}: duplicate writer rows")
            results.append(
                audit_time(case_dir, time_s, time_dir, writer_row=matching[0] if matching else None)
            )
        groups[case_id] = results
    return {
        "schema": "interface-wave-native-fv-flux-audit-v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "classification": "exploratory finite-volume flux/divergence audit; no acceptance gate",
        "input_path": str(run_or_case_dir.resolve()),
        "writer_summary_path": str(writer_csv.resolve()) if writer_csv else None,
        "divergence_method": "cell owner-oriented face flux sum / cell volume; not cell-centred U difference",
        "boundary_orientation": "OpenFOAM surface phi is outward-positive relative to each owner cell; internal face phi adds to owner and subtracts from neighbour",
        "coupled_patch_policy": "cyclic face flux enters the adjacent boundary cell once; cyclic patches are excluded from physical/open-boundary totals and paired patch sums are reported",
        "initial_discrete_incompressibility": {
            "status": "evaluated separately from the first saved native solver flux",
            "method": "periodic Gauss-linear interpolation of declared cell-centred U to oriented faces, then net face-flux balance per cell; not a solver-written t=0 phi",
            "cases": initial_checks,
        },
        "cases": groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-or-case-dir", type=Path, required=True)
    parser.add_argument("--writer-csv", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    result = audit_run(args.run_or_case_dir, args.writer_csv)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output_json),
                "case_count": len(result["cases"]),
                "time_rows": sum(map(len, result["cases"].values())),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
