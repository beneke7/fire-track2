"""Native cell-centre cut reader for the compact four-mouth I4F mesh.

This is a deliberately narrow reader for ten-rank collated OpenFOAM cases. It
selects native internal faces crossing a requested cell-centre x cut (4.8 m by
default), assigns them to the four fixed mouth windows, recovers signed native
surface fluxes, and reconstructs cell U/alpha at those faces. It is not a
general OpenFOAM reader.

The binary parsing, processor-pair sign check, face-centre interpolation, and
cut orientation were extracted from these audited private readers (not imported
at runtime):

* ``results/runs/i4f-native-mouth-flux-density-v2-20261025T190753Z/analyze_native_mouth_flux_density_v2.py``
  SHA256 ``5cd05385c7620c895a5bf7fffa9b410d41ba2498a71307fa9d24748155cc134e``
* ``results/runs/i4f-native-mouth-face-primed-validation-20261025T185911Z/analyze_native_mouth_plane.py``
  SHA256 ``3fd8b0e719e6f383c58b0e6fd9695f6a829c48984fc53fd0a4730f4862a93fc0``
* ``results/runs/i4f-fourmouth-observer-audit-20261025T102803Z/native-mouth-gap-20261025T124045Z/analyze_native_mouth_gap.py``
  SHA256 ``ea9ac46f78b0bccec4bc0969e9d46a8f294da71f116c7f935c48dcf5dcd82e08``

The historical paths above document provenance only; all parsing needed at
runtime is contained in this module.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

NPROCS = 10
TARGET_X_M = 4.8
READER_EXTRACTION_PROVENANCE = (
    {
        "source": "results/runs/i4f-native-mouth-flux-density-v2-20261025T190753Z/analyze_native_mouth_flux_density_v2.py",
        "sha256": "5cd05385c7620c895a5bf7fffa9b410d41ba2498a71307fa9d24748155cc134e",
        "routines": "global cut selection, local/processor face addressing, native flux orientation and processor duplicate checks",
    },
    {
        "source": "results/runs/i4f-native-mouth-face-primed-validation-20261025T185911Z/analyze_native_mouth_plane.py",
        "sha256": "3fd8b0e719e6f383c58b0e6fd9695f6a829c48984fc53fd0a4730f4862a93fc0",
        "routines": "global mesh labels/faces/points/C parsing and cell-map field reconstruction",
    },
    {
        "source": "results/runs/i4f-fourmouth-observer-audit-20261025T102803Z/native-mouth-gap-20261025T124045Z/analyze_native_mouth_gap.py",
        "sha256": "ea9ac46f78b0bccec4bc0969e9d46a8f294da71f116c7f935c48dcf5dcd82e08",
        "routines": "collated binary list parsing, scalar/vector field decoding, face geometry and OpenCFD linear face weight",
    },
)
MOUTH_WINDOWS = {
    "A_lower": {"y_min": -1.05, "y_max": -0.05, "z_min": 0.575, "z_max": 0.725},
    "A_upper": {"y_min": -1.05, "y_max": -0.05, "z_min": 0.825, "z_max": 0.975},
    "B_lower": {"y_min": 0.05, "y_max": 1.05, "z_min": 0.575, "z_max": 0.725},
    "B_upper": {"y_min": 0.05, "y_max": 1.05, "z_min": 0.825, "z_max": 0.975},
}
NATIVE_FIELDS = (
    "alpha.water",
    "alphaPhi0.water",
    "alphat",
    "k",
    "nut",
    "omega",
    "p",
    "p_rgh",
    "phi",
    "rho",
    "T",
    "T.air",
    "T.water",
    "U",
)
_COLLATED_FIELD_RE = re.compile(rb"// processor(\d+)\s*\n\s*(\d+)\s*\n\s*\(")
_LIST_HEADER_RE = re.compile(rb"// \* \* \*.*?\n\s*(\d+)\s*\n\s*\(", re.S)


@dataclass(frozen=True)
class NativeMouthFace:
    mouth: str
    global_face_id: int
    centroid_xyz_m: tuple[float, float, float]
    outward_projected_area_m2: float
    native_polygon_area_m2: float
    native_phi_m3_s: float
    native_alpha_phi_water_m3_s: float
    reconstructed_velocity_xyz_m_s: tuple[float, float, float]
    reconstructed_alpha_water_raw: float
    reconstructed_water_density_kg_m3: float
    interpolation_weight: float
    face_map_sign: int
    record_kind: str


@dataclass(frozen=True)
class NativeMouthSnapshot:
    case_path: Path
    time_name: str
    time_value_s: float
    nprocs: int
    face_count: int
    processor_pair_summary: dict[str, Any]
    mouth_faces: dict[str, tuple[NativeMouthFace, ...]]
    input_paths: tuple[Path, ...]
    selection_metadata: dict[str, Any]
    water_density_metadata: dict[str, Any]


def _parse_list_header(raw: bytes, path: Path) -> tuple[int, int]:
    match = _LIST_HEADER_RE.search(raw)
    if match is None:
        raise ValueError(f"cannot locate OpenFOAM list header in {path}")
    return int(match.group(1)), match.end()


def _ascii_list_body(raw: bytes, start: int, path: Path) -> bytes:
    end = re.search(rb"\n\s*\)", raw[start:])
    if end is None:
        raise ValueError(f"cannot locate ASCII list end in {path}")
    return raw[start : start + end.start()]


def _read_global_labels(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    count, start = _parse_list_header(raw, path)
    if b"format      ascii" in raw[:1024]:
        values = np.fromstring(
            _ascii_list_body(raw, start, path).decode("ascii"), sep=" ", dtype=np.int64
        )
    else:
        values = np.frombuffer(raw[start : start + 4 * count], dtype="<i4").astype(np.int64)
    if len(values) != count:
        raise ValueError(f"global label count mismatch in {path}: {len(values)} != {count}")
    return values


def _read_global_points(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    count, start = _parse_list_header(raw, path)
    if b"format      ascii" in raw[:1024]:
        body = (
            _ascii_list_body(raw, start, path).decode("ascii").replace("(", " ").replace(")", " ")
        )
        values = np.fromstring(body, sep=" ", dtype=np.float64)
    else:
        values = np.frombuffer(raw[start : start + 24 * count], dtype="<f8").copy()
    if values.size != 3 * count:
        raise ValueError(f"global point count mismatch in {path}")
    points = values.reshape((-1, 3))
    if not np.isfinite(points).all():
        raise ValueError(f"non-finite point coordinates in {path}")
    return points


def _read_global_cell_centers(path: Path) -> np.ndarray:
    return _parse_internal(path.read_bytes(), "vector", components=3)


def _read_global_faces(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    if b"format      ascii" not in raw[:1024]:
        n_offsets, start = _parse_list_header(raw, path)
        offsets = np.frombuffer(raw[start : start + 4 * n_offsets], dtype="<i4").astype(np.int64)
        after_offsets = start + 4 * n_offsets
        trailer = re.match(rb"\)\s*(\d+)\s*\(", raw[after_offsets:])
        if trailer is None:
            raise ValueError(f"cannot parse compact binary face list in {path}")
        n_labels = int(trailer.group(1))
        label_start = after_offsets + trailer.end()
        labels = np.frombuffer(raw[label_start : label_start + 4 * n_labels], dtype="<i4").astype(
            np.int64
        )
        if (
            len(offsets) != n_offsets
            or len(labels) != n_labels
            or offsets[0] != 0
            or offsets[-1] != n_labels
        ):
            raise ValueError(f"invalid compact binary face connectivity in {path}")
        return offsets, labels

    count, start = _parse_list_header(raw, path)
    body = _ascii_list_body(raw, start, path).decode("ascii")
    offsets = [0]
    labels: list[int] = []
    for match in re.finditer(r"(\d+)\s*\(([^()]*)\)", body):
        n_vertices = int(match.group(1))
        face_labels = np.fromstring(match.group(2), sep=" ", dtype=np.int64)
        if len(face_labels) != n_vertices:
            raise ValueError(f"ASCII face vertex count mismatch in {path}")
        labels.extend(int(value) for value in face_labels)
        offsets.append(len(labels))
    if len(offsets) != count + 1:
        raise ValueError(f"ASCII face count mismatch in {path}: {len(offsets) - 1} != {count}")
    return np.asarray(offsets, dtype=np.int64), np.asarray(labels, dtype=np.int64)


def _read_global_boundary(path: Path) -> list[tuple[str, str, int, int]]:
    raw = path.read_bytes()
    count, start = _parse_list_header(raw, path)
    entries = _parse_boundary_entries(raw[start:].decode("latin1"))
    if len(entries) != count:
        raise ValueError(f"global patch count mismatch in {path}: {len(entries)} != {count}")
    return entries


def _parse_boundary_entries(text: str) -> list[tuple[str, str, int, int]]:
    return [
        (match.group(1), match.group(2), int(match.group(3)), int(match.group(4)))
        for match in re.finditer(
            r"([A-Za-z0-9_]+)\s*\{\s*type\s+(\w+);.*?nFaces\s+(\d+);\s*startFace\s+(\d+);",
            text,
            re.S,
        )
    ]


def _collated_block(path: Path, rank: int) -> bytes:
    raw = path.read_bytes()
    matches = list(_COLLATED_FIELD_RE.finditer(raw))
    for index, match in enumerate(matches):
        if int(match.group(1)) == rank:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
            return raw[match.end() : end]
    raise ValueError(f"collated file {path} has no processor{rank} block")


def _block_list_start(block: bytes, path: Path) -> tuple[int, int]:
    match = re.search(rb"object\s+\w+;\s*}\s*(\d+)\s*\n\s*\(", block, re.S)
    if match is None:
        match = re.match(rb"\s*(\d+)\s*\n\s*\(", block)
    if match is None:
        raise ValueError(f"cannot locate list in collated mesh block from {path}")
    return int(match.group(1)), match.end()


def _read_block_labels(path: Path, rank: int) -> np.ndarray:
    block = _collated_block(path, rank)
    count, start = _block_list_start(block, path)
    if b"format      ascii" in block[:512]:
        values = np.fromstring(
            _ascii_list_body(block, start, path).decode("ascii"), sep=" ", dtype=np.int64
        )
    else:
        values = np.frombuffer(block[start : start + 4 * count], dtype="<i4").astype(np.int64)
    if len(values) != count:
        raise ValueError(f"collated label count mismatch in {path}, rank {rank}")
    return values


def _read_block_boundary(path: Path, rank: int) -> list[tuple[str, str, int, int]]:
    block = _collated_block(path, rank)
    count, start = _block_list_start(block, path)
    entries = _parse_boundary_entries(block[start:].decode("latin1"))
    if len(entries) != count:
        raise ValueError(f"collated boundary patch count mismatch in {path}, rank {rank}")
    return entries


def _field_chunks(path: Path, nprocs: int) -> dict[int, bytes]:
    raw = path.read_bytes()
    matches = list(_COLLATED_FIELD_RE.finditer(raw))
    chunks: dict[int, bytes] = {}
    for index, match in enumerate(matches):
        rank = int(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        if rank in chunks:
            raise ValueError(f"duplicate processor{rank} field block in {path}")
        chunks[rank] = raw[match.end() : end]
    if sorted(chunks) != list(range(nprocs)):
        raise ValueError(
            f"expected processor blocks 0..{nprocs - 1} in {path}; got {sorted(chunks)}"
        )
    return chunks


def _parse_internal(chunk: bytes, value_type: str, components: int = 1) -> np.ndarray:
    match = re.search(
        rb"internalField\s+nonuniform\s+List<" + value_type.encode() + rb">\s*(\d+)\s*\(",
        chunk,
    )
    if match is None:
        raise ValueError(f"no nonuniform List<{value_type}> internalField")
    count = int(match.group(1))
    start = match.end()
    raw_count = count * components
    if b"format      ascii" in chunk[: match.start()]:
        end = re.search(rb"\n\s*\)\s*;", chunk[start:])
        if end is None:
            raise ValueError("cannot find ASCII internalField list end")
        values = np.fromstring(
            chunk[start : start + end.start()].decode("ascii").replace("(", " ").replace(")", " "),
            sep=" ",
            dtype=np.float64,
        )
    else:
        values = np.frombuffer(chunk[start : start + 8 * raw_count], dtype="<f8").copy()
    if values.size != raw_count or not np.isfinite(values).all():
        raise ValueError("native internalField count/non-finite check failed")
    return values.reshape((count, components)) if components > 1 else values


def _parse_patch_scalar_values(chunk: bytes, patch: str, count: int) -> np.ndarray:
    if count == 0:
        return np.empty(0, dtype=np.float64)
    match = re.search(rb"(?m)^\s*" + re.escape(patch.encode()) + rb"\s*\{", chunk)
    if match is None:
        raise ValueError(f"missing processor patch {patch}")
    tail = chunk[match.end() :]
    first = re.search(rb"value\s+(uniform|nonuniform)\b", tail)
    if first is None:
        raise ValueError(f"missing value field on processor patch {patch}")
    if first.group(1) == b"uniform":
        scalar = re.search(rb"value\s+uniform\s+([-+0-9.eE]+)", tail)
        if scalar is None:
            raise ValueError(f"bad uniform scalar on processor patch {patch}")
        return np.full(count, float(scalar.group(1)), dtype=np.float64)
    values_match = re.search(rb"value\s+nonuniform\s+List<scalar>\s+(\d+)\s*\(", tail)
    if values_match is None or int(values_match.group(1)) != count:
        raise ValueError(f"processor patch {patch} scalar count mismatch")
    start = match.end() + values_match.end()
    if b"format      ascii" in chunk[: match.start()]:
        end = re.search(rb"\n\s*\)\s*;", chunk[start:])
        if end is None:
            raise ValueError(f"cannot find ASCII scalar end on processor patch {patch}")
        values = np.fromstring(chunk[start : start + end.start()].decode("ascii"), sep=" ")
    else:
        values = np.frombuffer(chunk[start : start + 8 * count], dtype="<f8").copy()
    if len(values) != count or not np.isfinite(values).all():
        raise ValueError(f"processor patch {patch} scalar values invalid")
    return values


def _face_geometry(
    face: int,
    offsets: np.ndarray,
    labels: np.ndarray,
    points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    polygon = points[labels[int(offsets[face]) : int(offsets[face + 1])]]
    if len(polygon) < 3:
        raise ValueError(f"degenerate global face {face}")
    p0 = polygon[0]
    sf = np.zeros(3, dtype=np.float64)
    weighted_center = np.zeros(3, dtype=np.float64)
    area_sum = 0.0
    for index in range(1, len(polygon) - 1):
        triangle_vector = 0.5 * np.cross(polygon[index] - p0, polygon[index + 1] - p0)
        triangle_area = float(np.linalg.norm(triangle_vector))
        sf += triangle_vector
        weighted_center += triangle_area * (p0 + polygon[index] + polygon[index + 1]) / 3.0
        area_sum += triangle_area
    if area_sum <= 0.0:
        raise ValueError(f"zero-area global face {face}")
    return sf, weighted_center / area_sum, area_sum


def _openfoam_linear_weight(
    sf: np.ndarray, cf: np.ndarray, co: np.ndarray, cn: np.ndarray
) -> float:
    """Return OpenFOAM's owner interpolation weight for an internal face.

    The distance to the neighbour is the owner weight: for a face closer to
    the owner, the neighbour distance is larger and the owner contribution
    must therefore be larger.
    """
    own_distance = abs(float(np.dot(sf, cf - co)))
    neighbour_distance = abs(float(np.dot(sf, cn - cf)))
    total = own_distance + neighbour_distance
    return neighbour_distance / total if total > 1e-30 else 0.5


def _interpolate_owner_weighted(
    owner_value: np.ndarray | float,
    neighbour_value: np.ndarray | float,
    owner_weight: float,
) -> np.ndarray | float:
    """Apply OpenFOAM linear interpolation using an owner-weighted factor."""
    return owner_weight * owner_value + (1.0 - owner_weight) * neighbour_value


def _orient_local_internal_flux(
    local_flux: float, face_map_sign: int, global_owner_is_inside: bool
) -> float:
    """Orient local owner-to-neighbour flux across the global outward cut.

    ``faceProcAddressing`` stores signed one-based global face labels. Its sign
    maps local face orientation to the global face orientation; the second
    sign maps global owner-to-neighbour orientation to inside-to-outside.
    """
    if face_map_sign not in (-1, 1):
        raise ValueError(f"invalid signed faceProcAddressing orientation: {face_map_sign}")
    global_cut_sign = 1 if global_owner_is_inside else -1
    return float(local_flux) * face_map_sign * global_cut_sign


def _local_face_cells_in_global_cut_order(
    local_owner_global: int,
    local_neighbour_global: int,
    face_map_sign: int,
    global_owner_is_inside: bool,
) -> tuple[int, int]:
    """Return inside/outside cell ids from a local internal face record.

    A negative signed face label means local owner/neighbour order is reversed
    relative to the global face. Resolve that mapping before selecting the
    control-volume inside and outside cells.
    """
    if face_map_sign not in (-1, 1):
        raise ValueError(f"invalid signed faceProcAddressing orientation: {face_map_sign}")
    if face_map_sign > 0:
        global_owner, global_neighbour = local_owner_global, local_neighbour_global
    else:
        global_owner, global_neighbour = local_neighbour_global, local_owner_global
    if global_owner_is_inside:
        return global_owner, global_neighbour
    return global_neighbour, global_owner


def _parse_uniform_time(path: Path) -> tuple[float, str]:
    raw = path.read_text()
    value_match = re.search(r"(?m)^\s*value\s+([-+0-9.eE]+)\s*;", raw)
    name_match = re.search(r'(?m)^\s*name\s+"([^"]+)"\s*;', raw)
    if value_match is None or name_match is None:
        raise ValueError(f"uniform/time lacks value/name: {path}")
    value = float(value_match.group(1))
    if not math.isfinite(value):
        raise ValueError(f"uniform/time is non-finite: {path}")
    return value, name_match.group(1)


def _mouth_for_center(center: np.ndarray) -> str | None:
    matches = [
        name
        for name, bounds in MOUTH_WINDOWS.items()
        if bounds["y_min"] <= float(center[1]) <= bounds["y_max"]
        and bounds["z_min"] <= float(center[2]) <= bounds["z_max"]
    ]
    if len(matches) > 1:
        raise ValueError(f"mouth windows overlap at face centroid {center.tolist()}")
    return matches[0] if matches else None


def _validated_mouth_x(mouth_x_m: float) -> float:
    try:
        target = float(mouth_x_m)
    except (TypeError, ValueError) as exc:
        raise ValueError("mouth_x_m must be a finite number") from exc
    if not math.isfinite(target):
        raise ValueError("mouth_x_m must be a finite number")
    return target


def _select_native_mouth_cut(
    centers: np.ndarray,
    owner: np.ndarray,
    neighbour: np.ndarray,
    offsets: np.ndarray,
    labels: np.ndarray,
    points: np.ndarray,
    mouth_x_m: float,
) -> tuple[np.ndarray, dict[int, dict[str, Any]]]:
    """Select the native global faces that straddle a requested x control cut."""
    target_x = _validated_mouth_x(mouth_x_m)
    inside = centers[:, 0] <= target_x
    crossing = np.flatnonzero(inside[owner[: len(neighbour)]] != inside[neighbour])
    if crossing.size == 0:
        raise ValueError(f"no native internal faces straddle the requested mouth x={target_x:g} m")

    geometry: dict[int, dict[str, Any]] = {}
    for gid_raw in crossing:
        gid = int(gid_raw)
        sf, centroid, polygon_area = _face_geometry(gid, offsets, labels, points)
        mouth = _mouth_for_center(centroid)
        if mouth is not None:
            geometry[gid] = {
                "mouth": mouth,
                "centroid": centroid,
                "sf": sf,
                "polygon_area": polygon_area,
            }
    if not geometry:
        raise ValueError(
            f"native faces straddle x={target_x:g} m, but none fall within the four fixed mouth windows"
        )
    expected_mouths = set(MOUTH_WINDOWS)
    seen_mouths = {item["mouth"] for item in geometry.values()}
    if seen_mouths != expected_mouths:
        missing = sorted(expected_mouths - seen_mouths)
        raise ValueError(
            f"native cut at x={target_x:g} m did not cover all four fixed mouths; "
            f"missing {missing} (selected {sorted(seen_mouths)})"
        )
    return inside, geometry


def _load_global_cell_field(
    field: str,
    time_dir: Path,
    cell_maps: list[np.ndarray],
    global_cell_count: int,
    components: int,
    nprocs: int,
) -> np.ndarray:
    chunks = _field_chunks(time_dir / field, nprocs)
    shape = (global_cell_count, components) if components > 1 else (global_cell_count,)
    output = np.full(shape, np.nan, dtype=np.float64)
    value_type = "vector" if components > 1 else "scalar"
    for rank in range(nprocs):
        values = _parse_internal(chunks[rank], value_type, components)
        mapping = cell_maps[rank]
        if len(values) != len(mapping):
            raise ValueError(f"{field} internal count does not match rank {rank} cell map")
        output[mapping] = values
    if not np.isfinite(output).all():
        raise ValueError(f"{field} did not map to every global cell")
    return output


def _read_water_density_model(path: Path) -> dict[str, Any]:
    """Read the supported water EOS and lock its exact case dictionary bytes."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"(?m)//.*$", " ", text)
    thermo_type = re.search(r"\bthermoType\s*\{([^{}]*)\}", text, flags=re.S)
    if thermo_type is None:
        raise ValueError(f"water dictionary has no simple thermoType block: {path}")
    eos_match = re.search(r"\bequationOfState\s+([A-Za-z][A-Za-z0-9_]*)\s*;", thermo_type.group(1))
    if eos_match is None:
        raise ValueError(f"water dictionary has no equationOfState selector: {path}")
    eos_name = eos_match.group(1)
    eos_block = re.search(r"\bequationOfState\s*\{([^{}]*)\}", text, flags=re.S)
    if eos_block is None:
        raise ValueError(f"water dictionary has no equationOfState parameter block: {path}")

    def parameter(name: str) -> float:
        match = re.search(
            rf"(?m)^\s*{re.escape(name)}\s+([-+0-9.eE]+)\s*;",
            eos_block.group(1),
        )
        if match is None:
            raise ValueError(f"water EOS {eos_name} is missing scalar {name}: {path}")
        value = float(match.group(1))
        if not math.isfinite(value):
            raise ValueError(f"water EOS parameter {name} is non-finite: {path}")
        return value

    if eos_name == "rhoConst":
        parameters = {"rho_kg_m3": parameter("rho")}
        if parameters["rho_kg_m3"] <= 0.0:
            raise ValueError(f"rhoConst density must be positive: {path}")
        equation = "rho_water(p,T)=rho"
    elif eos_name == "adiabaticPerfectFluid":
        parameters = {name: parameter(name) for name in ("p0", "rho0", "gamma", "B")}
        if (
            parameters["p0"] + parameters["B"] <= 0.0
            or parameters["rho0"] <= 0.0
            or parameters["gamma"] <= 0.0
        ):
            raise ValueError(f"invalid adiabaticPerfectFluid parameters: {path}")
        equation = "rho0*((p+B)/(p0+B))**(1/gamma); p is absolute pressure"
    else:
        raise ValueError(f"unsupported water equationOfState {eos_name!r}: {path}")

    return {
        "model": eos_name,
        "parameters": parameters,
        "density_equation": equation,
        "source_path": "constant/thermophysicalProperties.water",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _water_density_from_pressure(pressure_pa: np.ndarray, model: dict[str, Any]) -> np.ndarray:
    """Evaluate liquid density cellwise from absolute pressure and a supported EOS."""
    pressure = np.asarray(pressure_pa, dtype=np.float64)
    if not np.all(np.isfinite(pressure)):
        raise ValueError("cell absolute pressure contains non-finite values")
    eos_name = model["model"]
    parameters = model["parameters"]
    if eos_name == "rhoConst":
        density = np.full(pressure.shape, float(parameters["rho_kg_m3"]), dtype=np.float64)
    elif eos_name == "adiabaticPerfectFluid":
        p0 = float(parameters["p0"])
        rho0 = float(parameters["rho0"])
        gamma = float(parameters["gamma"])
        bulk_parameter = float(parameters["B"])
        ratio = (pressure + bulk_parameter) / (p0 + bulk_parameter)
        if not np.all(np.isfinite(ratio)) or np.any(ratio <= 0.0):
            raise ValueError(
                "absolute pressure is outside the adiabaticPerfectFluid density domain"
            )
        density = rho0 * np.power(ratio, 1.0 / gamma)
    else:
        raise ValueError(f"unsupported water equationOfState {eos_name!r}")
    if not np.all(np.isfinite(density)) or np.any(density <= 0.0):
        raise ValueError("water EOS produced non-finite or nonpositive density")
    return density


def _build_case_mesh(case: Path, nprocs: int, mouth_x_m: float) -> dict[str, Any]:
    target_x = _validated_mouth_x(mouth_x_m)
    mesh = case / "constant/polyMesh"
    points = _read_global_points(mesh / "points")
    offsets, labels = _read_global_faces(mesh / "faces")
    owner = _read_global_labels(mesh / "owner")
    neighbour = _read_global_labels(mesh / "neighbour")
    centers = _read_global_cell_centers(case / "constant/C")
    if len(owner) != len(offsets) - 1 or len(neighbour) > len(owner):
        raise ValueError("global owner/neighbour/faces counts disagree")
    if len(centers) != max(int(owner.max()), int(neighbour.max())) + 1:
        raise ValueError("global C count does not agree with owner/neighbour cell labels")
    if (
        np.any(owner < 0)
        or np.any(owner >= len(centers))
        or np.any(neighbour < 0)
        or np.any(neighbour >= len(centers))
    ):
        raise ValueError("global owner/neighbour contains an out-of-range cell label")
    inside, geometry = _select_native_mouth_cut(
        centers, owner, neighbour, offsets, labels, points, target_x
    )

    proc_mesh = case / f"processors{nprocs}/constant/polyMesh"
    cell_maps: list[np.ndarray] = []
    internal_map: dict[int, dict[str, int]] = {}
    processor_map: dict[int, list[dict[str, Any]]] = {}
    rank_data: list[dict[str, Any]] = []
    global_cell_seen = np.zeros(len(centers), dtype=bool)
    candidate = set(geometry)
    selected_internal_signs: list[int] = []
    selected_processor_signs: dict[int, list[int]] = {}
    for rank in range(nprocs):
        cell_map = _read_block_labels(proc_mesh / "cellProcAddressing", rank)
        local_owner = _read_block_labels(proc_mesh / "owner", rank)
        local_neighbour = _read_block_labels(proc_mesh / "neighbour", rank)
        face_map = _read_block_labels(proc_mesh / "faceProcAddressing", rank)
        boundary = _read_block_boundary(proc_mesh / "boundary", rank)
        if len(local_owner) != len(face_map) or len(local_neighbour) > len(local_owner):
            raise ValueError(f"rank {rank} local face addressing sizes disagree")
        if (
            np.any(cell_map < 0)
            or np.any(cell_map >= len(centers))
            or global_cell_seen[cell_map].any()
        ):
            raise ValueError(f"rank {rank} cellProcAddressing is out of bounds or duplicated")
        global_cell_seen[cell_map] = True
        cell_maps.append(cell_map)
        for local_face in range(len(local_neighbour)):
            gid = abs(int(face_map[local_face])) - 1
            if gid not in candidate:
                continue
            if gid in internal_map:
                raise ValueError(f"candidate global internal face {gid} is represented twice")
            internal_map[gid] = {
                "rank": rank,
                "local_face": local_face,
                "owner_global": int(cell_map[local_owner[local_face]]),
                "neighbour_global": int(cell_map[local_neighbour[local_face]]),
                "face_map_sign": 1 if int(face_map[local_face]) > 0 else -1,
            }
            selected_internal_signs.append(1 if int(face_map[local_face]) > 0 else -1)
        processor_patch_names: set[str] = set()
        for patch, patch_type, nfaces, start_face in boundary:
            if patch_type != "processor":
                continue
            for patch_offset in range(nfaces):
                local_face = start_face + patch_offset
                gid = abs(int(face_map[local_face])) - 1
                if gid not in candidate:
                    continue
                processor_patch_names.add(patch)
                processor_map.setdefault(gid, []).append(
                    {
                        "rank": rank,
                        "local_face": local_face,
                        "patch": patch,
                        "patch_offset": patch_offset,
                        "owner_global": int(cell_map[local_owner[local_face]]),
                        "face_map_sign": 1 if int(face_map[local_face]) > 0 else -1,
                    }
                )
                selected_processor_signs.setdefault(gid, []).append(
                    1 if int(face_map[local_face]) > 0 else -1
                )
        rank_data.append(
            {
                "owner": local_owner,
                "neighbour": local_neighbour,
                "boundary": boundary,
                "processor_patch_names": processor_patch_names,
            }
        )
    if not global_cell_seen.all():
        raise ValueError(
            f"cellProcAddressing misses {int(np.count_nonzero(~global_cell_seen))} global cells"
        )
    for gid in candidate:
        n_internal = int(gid in internal_map)
        n_processor = len(processor_map.get(gid, []))
        if (n_internal, n_processor) not in ((1, 0), (0, 2)):
            raise ValueError(
                f"face {gid} has invalid local/processor representation {(n_internal, n_processor)}"
            )
        if n_processor == 2 and set(selected_processor_signs.get(gid, ())) != {-1, 1}:
            raise ValueError(
                f"processor representations of face {gid} do not have opposite signed mappings: "
                f"{selected_processor_signs.get(gid)}"
            )
    return {
        "mesh_path": mesh,
        "processor_mesh_path": proc_mesh,
        "points": points,
        "face_offsets": offsets,
        "face_labels": labels,
        "global_owner": owner,
        "global_neighbour": neighbour,
        "global_cell_centers": centers,
        "inside_mask": inside,
        "geometry": geometry,
        "cell_maps": cell_maps,
        "internal_map": internal_map,
        "processor_map": processor_map,
        "rank_data": rank_data,
        "selected_internal_face_map_sign_counts": {
            "positive": selected_internal_signs.count(1),
            "negative": selected_internal_signs.count(-1),
        },
        "selected_processor_face_map_sign_counts": {
            "positive": sum(
                sign == 1 for signs in selected_processor_signs.values() for sign in signs
            ),
            "negative": sum(
                sign == -1 for signs in selected_processor_signs.values() for sign in signs
            ),
        },
    }


def _read_time_fields(
    case: Path,
    time_name: str,
    mesh_data: dict[str, Any],
    nprocs: int,
) -> tuple[
    dict[int, dict[str, Any]],
    np.ndarray,
    np.ndarray,
    float,
    list[Path],
    dict[str, Any],
    dict[str, Any],
]:
    time_dir = case / f"processors{nprocs}/{time_name}"
    if not time_dir.is_dir():
        raise FileNotFoundError(f"native checkpoint directory does not exist: {time_dir}")
    native_paths = [time_dir / field for field in NATIVE_FIELDS]
    native_paths.append(time_dir / "uniform/time")
    for path in native_paths:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"incomplete selected native checkpoint: {path}")
    time_value, time_label = _parse_uniform_time(time_dir / "uniform/time")
    if time_label != time_name or not math.isclose(
        time_value, float(time_name), rel_tol=0.0, abs_tol=1e-9
    ):
        raise ValueError(
            f"uniform/time {time_label}/{time_value} does not match requested {time_name}"
        )

    chunks: dict[str, dict[int, bytes]] = {}
    for field in ("phi", "alphaPhi0.water", "alpha.water", "U"):
        chunks[field] = _field_chunks(time_dir / field, nprocs)
    local_surface: dict[int, dict[str, Any]] = {}
    for rank in range(nprocs):
        rank_info = mesh_data["rank_data"][rank]
        phi_chunk = chunks["phi"][rank]
        alpha_phi_chunk = chunks["alphaPhi0.water"][rank]
        phi_internal = _parse_internal(phi_chunk, "scalar")
        alpha_phi_internal = _parse_internal(alpha_phi_chunk, "scalar")
        expected_internal_faces = len(rank_info["neighbour"])
        if (
            len(phi_internal) != expected_internal_faces
            or len(alpha_phi_internal) != expected_internal_faces
        ):
            raise ValueError(f"rank {rank} internal surface field count differs from its mesh")
        phi_patches: dict[str, np.ndarray] = {}
        alpha_patches: dict[str, np.ndarray] = {}
        patch_by_name = {item[0]: item for item in rank_info["boundary"]}
        for patch in rank_info["processor_patch_names"]:
            _name, _kind, patch_count, _start = patch_by_name[patch]
            phi_patches[patch] = _parse_patch_scalar_values(phi_chunk, patch, patch_count)
            alpha_patches[patch] = _parse_patch_scalar_values(alpha_phi_chunk, patch, patch_count)
        local_surface[rank] = {
            "phi_internal": phi_internal,
            "alpha_phi_internal": alpha_phi_internal,
            "phi_patches": phi_patches,
            "alpha_patches": alpha_patches,
        }
    centers = mesh_data["global_cell_centers"]
    alpha_global = _load_global_cell_field(
        "alpha.water", time_dir, mesh_data["cell_maps"], len(centers), 1, nprocs
    )
    velocity_global = _load_global_cell_field(
        "U", time_dir, mesh_data["cell_maps"], len(centers), 3, nprocs
    )
    pressure_global = _load_global_cell_field(
        "p", time_dir, mesh_data["cell_maps"], len(centers), 1, nprocs
    )
    water_density_model = _read_water_density_model(
        case / "constant/thermophysicalProperties.water"
    )
    water_density_global = _water_density_from_pressure(pressure_global, water_density_model)
    face_fluxes: dict[int, dict[str, Any]] = {}
    pair_errors: list[tuple[float, float, float, float]] = []
    inside = mesh_data["inside_mask"]
    for gid, geom in mesh_data["geometry"].items():
        if gid in mesh_data["internal_map"]:
            item = mesh_data["internal_map"][gid]
            rank = item["rank"]
            local_face = item["local_face"]
            global_owner_inside = bool(inside[mesh_data["global_owner"][gid]])
            q_phi = _orient_local_internal_flux(
                float(local_surface[rank]["phi_internal"][local_face]),
                item["face_map_sign"],
                global_owner_inside,
            )
            q_alpha = _orient_local_internal_flux(
                float(local_surface[rank]["alpha_phi_internal"][local_face]),
                item["face_map_sign"],
                global_owner_inside,
            )
            owner_inside, neighbour_outside = _local_face_cells_in_global_cut_order(
                item["owner_global"],
                item["neighbour_global"],
                item["face_map_sign"],
                global_owner_inside,
            )
            global_owner = int(mesh_data["global_owner"][gid])
            global_neighbour = int(mesh_data["global_neighbour"][gid])
            if item["face_map_sign"] > 0:
                mapped_owner, mapped_neighbour = item["owner_global"], item["neighbour_global"]
            else:
                mapped_owner, mapped_neighbour = item["neighbour_global"], item["owner_global"]
            if (mapped_owner, mapped_neighbour) != (global_owner, global_neighbour):
                raise ValueError(
                    f"faceProcAddressing cell orientation disagrees with global face {gid}: "
                    f"mapped={(mapped_owner, mapped_neighbour)} global={(global_owner, global_neighbour)}"
                )
            face_map_sign = item["face_map_sign"]
            record_kind = "local_internal_face"
        else:
            pair = mesh_data["processor_map"][gid]
            first_inside = bool(inside[int(pair[0]["owner_global"])])
            upstream, downstream = pair if first_inside else pair[::-1]
            if not inside[int(upstream["owner_global"])] or inside[int(downstream["owner_global"])]:
                raise ValueError(f"processor face {gid} does not bridge inside and outside cells")
            up = local_surface[int(upstream["rank"])]
            down = local_surface[int(downstream["rank"])]
            q_phi = float(up["phi_patches"][upstream["patch"]][upstream["patch_offset"]])
            q_alpha = float(up["alpha_patches"][upstream["patch"]][upstream["patch_offset"]])
            downstream_phi = -float(
                down["phi_patches"][downstream["patch"]][downstream["patch_offset"]]
            )
            downstream_alpha = -float(
                down["alpha_patches"][downstream["patch"]][downstream["patch_offset"]]
            )
            phi_abs = abs(q_phi - downstream_phi)
            alpha_abs = abs(q_alpha - downstream_alpha)
            phi_rel = phi_abs / max(abs(q_phi), abs(downstream_phi), 1e-300)
            alpha_rel = alpha_abs / max(abs(q_alpha), abs(downstream_alpha), 1e-300)
            pair_errors.append((phi_rel, alpha_rel, phi_abs, alpha_abs))
            owner_inside = int(upstream["owner_global"])
            neighbour_outside = int(downstream["owner_global"])
            face_map_sign = int(upstream["face_map_sign"])
            record_kind = "processor_face_upstream_side"
        if not (0 <= owner_inside < len(centers) and 0 <= neighbour_outside < len(centers)):
            raise ValueError(f"face {gid} has invalid reconstructed-neighbor cells")
        sf_out = np.asarray(geom["sf"], dtype=np.float64)
        if geom["mouth"] not in MOUTH_WINDOWS:
            raise ValueError(f"face {gid} assigned to unknown mouth {geom['mouth']}")
        # The global face area vector is owner-to-neighbour. Orient it outward
        # from the selected x-cut control region, independent of rank signs.
        if not inside[int(mesh_data["global_owner"][gid])]:
            sf_out = -sf_out
        projected_area = float(sf_out[0])
        if not math.isfinite(projected_area) or projected_area <= 0.0:
            raise ValueError(f"face {gid} has nonpositive outward projected area {projected_area}")
        face_center = np.asarray(geom["centroid"], dtype=np.float64)
        weight = _openfoam_linear_weight(
            sf_out,
            face_center,
            centers[owner_inside],
            centers[neighbour_outside],
        )
        u_face = _interpolate_owner_weighted(
            velocity_global[owner_inside], velocity_global[neighbour_outside], weight
        )
        alpha_face = _interpolate_owner_weighted(
            alpha_global[owner_inside], alpha_global[neighbour_outside], weight
        )
        water_density_face = _interpolate_owner_weighted(
            water_density_global[owner_inside], water_density_global[neighbour_outside], weight
        )
        face_fluxes[gid] = {
            "phi": q_phi,
            "alpha_phi_water": q_alpha,
            "face_map_sign": face_map_sign,
            "record_kind": record_kind,
            "owner_inside": owner_inside,
            "neighbour_outside": neighbour_outside,
            "sf_out": sf_out,
            "projected_area": projected_area,
            "u_face": u_face,
            "alpha_face": float(alpha_face),
            "water_density_face": float(water_density_face),
            "interpolation_weight": weight,
        }
    if set(face_fluxes) != set(mesh_data["geometry"]):
        raise ValueError("native flux reconstruction did not produce every selected mouth face")
    pair_summary = {
        "paired_processor_face_count": len(pair_errors),
        "max_phi_relative_pair_error": max((item[0] for item in pair_errors), default=0.0),
        "max_alphaPhi_relative_pair_error": max((item[1] for item in pair_errors), default=0.0),
        "max_phi_absolute_pair_error_m3_s": max((item[2] for item in pair_errors), default=0.0),
        "max_alphaPhi_absolute_pair_error_m3_s": max(
            (item[3] for item in pair_errors), default=0.0
        ),
    }
    if (
        pair_summary["max_phi_relative_pair_error"] > 1e-8
        or pair_summary["max_alphaPhi_relative_pair_error"] > 1e-8
    ):
        raise ValueError(f"processor duplicate flux check failed: {pair_summary}")
    return (
        face_fluxes,
        alpha_global,
        velocity_global,
        time_value,
        native_paths,
        pair_summary,
        water_density_model,
    )


def read_native_mouth_snapshot(
    case_path: Path,
    time_name: str,
    *,
    nprocs: int = NPROCS,
    mouth_x_m: float = TARGET_X_M,
) -> NativeMouthSnapshot:
    """Read a collated checkpoint at the requested x cut and four fixed mouths."""
    case = case_path.resolve()
    target_x = _validated_mouth_x(mouth_x_m)
    if nprocs != NPROCS:
        raise ValueError(f"this reader is scoped to {NPROCS}-rank collated cases, got {nprocs}")
    if not time_name or Path(time_name).name != time_name:
        raise ValueError("time must be one exact processors10 directory name")
    try:
        float(time_name)
    except ValueError as exc:
        raise ValueError(f"time directory name is not numeric: {time_name}") from exc
    if not case.is_dir():
        raise FileNotFoundError(f"case directory does not exist: {case}")
    mesh_data = _build_case_mesh(case, nprocs, target_x)
    (
        face_fluxes,
        _alpha,
        _u,
        time_value,
        native_paths,
        pair_summary,
        water_density_model,
    ) = _read_time_fields(case, time_name, mesh_data, nprocs)
    by_mouth: dict[str, list[NativeMouthFace]] = {name: [] for name in MOUTH_WINDOWS}
    for gid, geom in mesh_data["geometry"].items():
        flux = face_fluxes[gid]
        by_mouth[geom["mouth"]].append(
            NativeMouthFace(
                mouth=geom["mouth"],
                global_face_id=gid,
                centroid_xyz_m=tuple(float(value) for value in geom["centroid"]),
                outward_projected_area_m2=float(flux["projected_area"]),
                native_polygon_area_m2=float(geom["polygon_area"]),
                native_phi_m3_s=float(flux["phi"]),
                native_alpha_phi_water_m3_s=float(flux["alpha_phi_water"]),
                reconstructed_velocity_xyz_m_s=tuple(float(value) for value in flux["u_face"]),
                reconstructed_alpha_water_raw=float(flux["alpha_face"]),
                reconstructed_water_density_kg_m3=float(flux["water_density_face"]),
                interpolation_weight=float(flux["interpolation_weight"]),
                face_map_sign=int(flux["face_map_sign"]),
                record_kind=str(flux["record_kind"]),
            )
        )
    if any(not faces for faces in by_mouth.values()):
        raise ValueError("one or more fixed mouths have no selected native cut faces")
    for faces in by_mouth.values():
        faces.sort(key=lambda face: face.global_face_id)

    mesh = mesh_data["mesh_path"]
    processor_mesh = mesh_data["processor_mesh_path"]
    input_paths = (
        case / "constant/C",
        mesh / "points",
        mesh / "faces",
        mesh / "owner",
        mesh / "neighbour",
        mesh / "boundary",
        processor_mesh / "cellProcAddressing",
        processor_mesh / "faceProcAddressing",
        processor_mesh / "owner",
        processor_mesh / "neighbour",
        processor_mesh / "boundary",
        case / "constant/thermophysicalProperties.water",
        *native_paths,
    )
    area_by_mouth = {
        mouth: float(sum(face.outward_projected_area_m2 for face in faces))
        for mouth, faces in by_mouth.items()
    }
    return NativeMouthSnapshot(
        case_path=case,
        time_name=time_name,
        time_value_s=time_value,
        nprocs=nprocs,
        face_count=sum(len(faces) for faces in by_mouth.values()),
        processor_pair_summary=pair_summary,
        mouth_faces={mouth: tuple(faces) for mouth, faces in by_mouth.items()},
        input_paths=tuple(input_paths),
        selection_metadata={
            "target_x_cell_center_m": target_x,
            "mouth_windows_m": MOUTH_WINDOWS,
            "mouth_projected_area_m2": area_by_mouth,
            "orientation": (
                f"global face area vector oriented from x<={target_x:g} m cell to "
                f"x>{target_x:g} m cell; outward projected Sf.x must be positive"
            ),
            "selection": (
                "native global internal faces whose owner/neighbour cell centres straddle "
                f"x<={target_x:g} m, assigned by actual triangulation-weighted face centroid "
                "to one fixed y/z mouth window"
            ),
            "selected_faceProcAddressing_sign_counts": {
                "local_internal_faces": mesh_data["selected_internal_face_map_sign_counts"],
                "processor_patch_representations": mesh_data[
                    "selected_processor_face_map_sign_counts"
                ],
                "processor_pair_rule": "the two processor representations of each selected global face must have opposite signed faceProcAddressing entries; processor-patch flux is read from the inside-side owner and is already oriented outward from that rank",
            },
            "local_internal_flux_orientation": (
                "local owner-to-neighbour phi is multiplied by signed faceProcAddressing "
                "orientation, then by the global owner inside/outside sign to orient across "
                f"the x<={target_x:g} control-surface cut"
            ),
            "linear_face_reconstruction": "OpenFOAM owner weight = distance from face to neighbour divided by owner-to-face plus face-to-neighbour distances; reconstructed value = w*owner + (1-w)*neighbour",
            "water_density_reconstruction": {
                "model": water_density_model["model"],
                "density_equation": water_density_model["density_equation"],
                "source_path": water_density_model["source_path"],
                "source_sha256": water_density_model["source_sha256"],
                "pressure_field": f"processors{nprocs}/{time_name}/p",
                "pressure_field_semantics": "mapped native cell-centre absolute p; evaluate rho_water(p_cell) in each cell, then linearly interpolate the two cell densities with the same owner weight used for U and alpha; do not evaluate EOS at interpolated p",
                "native_pressure_field_is_in_input_hashes": True,
                "qualification": "reconstructed water density combined with saved alphaPhi0.water is secondary and may not be the same-stage native rho1*alphaPhi mass flux",
            },
        },
        water_density_metadata=water_density_model,
    )
