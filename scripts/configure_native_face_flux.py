#!/usr/bin/env python3
"""Copy a Dash-8 discharge case and add a sparse native alphaPhi face stream.

The coded function object writes the solver's signed, face-integrated
``alphaPhi_`` value once per main time step.  It emits one compact CSV stream
and one static geometry/ID sidecar per MPI rank.  It does not reconstruct flux
from velocity and volume fraction or change any solver/model dictionaries.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Sequence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symbolic links are not supported in a source case: {path}")
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = sha256_file(path)
    return hashes


def _matching_brace(text: str, open_index: int) -> int:
    """Find a closing brace while ignoring Foam comments and quoted strings."""
    if text[open_index] != "{":
        raise ValueError("expected an opening brace")
    depth = 0
    in_string = False
    escaped = False
    line_comment = False
    block_comment = False
    index = open_index
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 1
        elif in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == "/" and next_char == "/":
            line_comment = True
            index += 1
        elif char == "/" and next_char == "*":
            block_comment = True
            index += 1
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                break
        index += 1
    raise ValueError("unbalanced controlDict braces")


def _functions_range(text: str) -> tuple[int, int]:
    matches = list(re.finditer(r"(?m)^\s*functions\s*\{", text))
    if len(matches) != 1:
        raise ValueError("controlDict must contain exactly one functions dictionary")
    opening = text.find("{", matches[0].start(), matches[0].end())
    closing = _matching_brace(text, opening)
    return opening, closing


def _face_zone_selection_code(zone_name: str) -> str:
    return f"""
    const faceZoneMesh& zones = mesh.faceZones();
    const label zonei = zones.findZoneID("{zone_name}");
    if (zonei < 0)
    {{
        FatalErrorInFunction << "Missing faceZone {zone_name}" << exit(FatalError);
    }}
    const faceZone& zone = zones[zonei];
    forAll(zone, zoneFacei)
    {{
        const label meshFacei = zone[zoneFacei];
        const bool flip = zone.flipMap()[zoneFacei];
        label patchi = -1;
        label patchFacei = meshFacei;
        if (!mesh.isInternalFace(meshFacei))
        {{
            patchi = mesh.boundaryMesh().whichPatch(meshFacei);
            if (patchi < 0)
            {{
                FatalErrorInFunction << "Cannot locate faceZone boundary face" << exit(FatalError);
            }}
            const polyPatch& patch = mesh.boundaryMesh()[patchi];
            if
            (
                isA<coupledPolyPatch>(patch)
             && !refCast<const coupledPolyPatch>(patch).owner()
            )
            {{
                continue;  // Match surfaceFieldValue: skip duplicate neighbour-side faces.
            }}
            patchFacei = patch.whichFace(meshFacei);
        }}
        meshFaceIds.append(meshFacei);
        patchIds.append(patchi);
        patchFaceIds.append(patchFacei);
        flipSigns.append(flip ? 1 : 0);
        selectionFaceIds.append(zoneFacei);
    }}
"""


def _patch_selection_code(patch_name: str) -> str:
    return f"""
    const label patchi = mesh.boundaryMesh().findPatchID("{patch_name}");
    if (patchi < 0)
    {{
        FatalErrorInFunction << "Missing boundary patch {patch_name}" << exit(FatalError);
    }}
    const polyPatch& patch = mesh.boundaryMesh()[patchi];
    forAll(patch, patchFacei)
    {{
        meshFaceIds.append(patch.start() + patchFacei);
        patchIds.append(patchi);
        patchFaceIds.append(patchFacei);
        flipSigns.append(0);
        selectionFaceIds.append(patchFacei);
    }}
"""


def _native_flux_function_object(name: str, selection: str, selection_code: str) -> str:
    selection_path = re.sub(r"[^A-Za-z0-9_-]+", "_", selection)
    return f"""
    {name}
    {{
        type coded;
        libs (utilityFunctionObjects);
        name {name};
        codeInclude
        #{{
            #include "fvCFD.H"
            #include "coupledPolyPatch.H"
            #include "OSspecific.H"
            #include <fstream>
            #include <iomanip>
            #include <sstream>
            #include <string>
        #}};
        codeWrite
        #{{
            const fvMesh& mesh = this->mesh();
            const Time& runTime = mesh.time();
            const surfaceScalarField& alphaPhi =
                mesh.lookupObject<surfaceScalarField>("alphaPhi_");
            DynamicList<label> meshFaceIds;
            DynamicList<label> patchIds;
            DynamicList<label> patchFaceIds;
            DynamicList<label> flipSigns;
            DynamicList<label> selectionFaceIds;
{selection_code}
            const fileName outputDir = runTime.path()
                / "postProcessing/nativeAlphaPhi/{selection_path}";
            mkDir(outputDir);
            std::ostringstream rankStream;
            rankStream << "rank-" << std::setfill('0') << std::setw(4)
                       << Pstream::myProcNo();
            const fileName rankDir = outputDir / rankStream.str();
            mkDir(rankDir);
            const fileName geometryPath = rankDir / "face-map.csv";
            const fileName ratesPath = rankDir / "rates.csv";

            if (!isFile(geometryPath))
            {{
                std::ofstream geometry(geometryPath.c_str(), std::ios::out);
                if (!geometry.good())
                {{
                    FatalErrorInFunction << "Cannot write native face map "
                        << geometryPath << exit(FatalError);
                }}
                geometry << "rank,stream_order,selection_face_id,mesh_face_id,patch_name,"
                    "patch_face_id,flip_map,center_x_m,center_y_m,center_z_m,"
                    "area_vector_x_m2,area_vector_y_m2,area_vector_z_m2,area_m2,"
                    "oriented_normal_x,oriented_normal_y,oriented_normal_z,"
                    "min_x_m,min_y_m,min_z_m,max_x_m,max_y_m,max_z_m\\n";
                geometry << std::setprecision(17);
                forAll(meshFaceIds, outputFacei)
                {{
                    const label meshFacei = meshFaceIds[outputFacei];
                    const label patchi = patchIds[outputFacei];
                    const label patchFacei = patchFaceIds[outputFacei];
                    vector areaVector;
                    vector centre;
                    if (patchi < 0)
                    {{
                        areaVector = mesh.Sf()[meshFacei];
                        centre = mesh.Cf()[meshFacei];
                    }}
                    else
                    {{
                        areaVector = mesh.Sf().boundaryField()[patchi][patchFacei];
                        centre = mesh.Cf().boundaryField()[patchi][patchFacei];
                    }}
                    if (flipSigns[outputFacei]) areaVector = -areaVector;
                    const scalar area = mag(areaVector);
                    if (area <= VSMALL)
                    {{
                        FatalErrorInFunction << "Zero native face area" << exit(FatalError);
                    }}
                    const vector normal = areaVector/area;
                    const face& facePoints = mesh.faces()[meshFacei];
                    if (facePoints.empty())
                    {{
                        FatalErrorInFunction << "Native face has no points" << exit(FatalError);
                    }}
                    vector lower(GREAT, GREAT, GREAT);
                    vector upper(-GREAT, -GREAT, -GREAT);
                    forAll(facePoints, pointi)
                    {{
                        const point& pointValue = mesh.points()[facePoints[pointi]];
                        for (direction component = 0; component < 3; ++component)
                        {{
                            lower[component] = min(lower[component], pointValue[component]);
                            upper[component] = max(upper[component], pointValue[component]);
                        }}
                    }}
                    const word patchName = patchi < 0
                        ? word("internal") : mesh.boundaryMesh()[patchi].name();
                    geometry << Pstream::myProcNo() << ',' << outputFacei << ','
                        << selectionFaceIds[outputFacei] << ',' << meshFacei << ','
                        << patchName << ',' << patchFacei << ',' << flipSigns[outputFacei]
                        << ',' << centre.x() << ',' << centre.y() << ',' << centre.z()
                        << ',' << areaVector.x() << ',' << areaVector.y() << ','
                        << areaVector.z() << ',' << area << ',' << normal.x() << ','
                        << normal.y() << ',' << normal.z() << ',' << lower.x() << ','
                        << lower.y() << ',' << lower.z() << ',' << upper.x() << ','
                        << upper.y() << ',' << upper.z() << '\\n';
                }}
            }}

            std::ofstream rates(ratesPath.c_str(), std::ios::out | std::ios::app);
            if (!rates.good())
            {{
                FatalErrorInFunction << "Cannot append native alphaPhi stream "
                    << ratesPath << exit(FatalError);
            }}
            rates << std::setprecision(17);
            if (!isFile(ratesPath) || rates.tellp() == std::streampos(0))
            {{
                rates << "time_index,time_s,deltaT_s,face_count";
                forAll(meshFaceIds, outputFacei) rates << ",alphaPhi_" << outputFacei;
                rates << '\\n';
            }}
            rates << runTime.timeIndex() << ',' << runTime.value() << ','
                << runTime.deltaTValue() << ',' << meshFaceIds.size();
            forAll(meshFaceIds, outputFacei)
            {{
                const label meshFacei = meshFaceIds[outputFacei];
                const label patchi = patchIds[outputFacei];
                const label patchFacei = patchFaceIds[outputFacei];
                scalar faceRate = patchi < 0
                    ? alphaPhi[meshFacei]
                    : alphaPhi.boundaryField()[patchi][patchFacei];
                if (alphaPhi.is_oriented() && flipSigns[outputFacei]) faceRate = -faceRate;
                rates << ',' << faceRate;
            }}
            rates << '\\n';
            rates.flush();
            if (!rates.good())
            {{
                FatalErrorInFunction << "Failed writing native alphaPhi stream "
                    << ratesPath << exit(FatalError);
            }}
        #}};
        executeControl timeStep;
        executeInterval 1;
        writeControl timeStep;
        writeInterval 1;
    }}
"""


def _injected_functions(face_zone: str, target_patch: str | None) -> str:
    blocks = [
        _native_flux_function_object(
            "nativeAlphaPhiOutlet",
            f"faceZone:{face_zone}",
            _face_zone_selection_code(face_zone),
        )
    ]
    if target_patch is not None:
        blocks.append(
            _native_flux_function_object(
                "nativeAlphaPhiTargetPatch",
                f"patch:{target_patch}",
                _patch_selection_code(target_patch),
            )
        )
    return "\n".join(blocks)


def configure_case(
    input_case: Path,
    output_case: Path,
    *,
    face_zone: str = "outletPlane",
    target_patch: str | None = None,
) -> dict[str, Any]:
    source = input_case.resolve(strict=True)
    destination = output_case.resolve(strict=False)
    if not source.is_dir():
        raise ValueError(f"input case is not a directory: {source}")
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing output case: {destination}")
    for value, label in ((face_zone, "face zone"), (target_patch, "target patch")):
        if value is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
            raise ValueError(f"{label} must be an OpenFOAM identifier")
    inventory_before = tree_hashes(source)
    metadata_path = source / "case-inputs.json"
    control_path = source / "system/controlDict"
    if not metadata_path.is_file() or not control_path.is_file():
        raise ValueError("source case requires case-inputs.json and system/controlDict")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (
        metadata.get("openfoam_image_id")
        != "sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b"
    ):
        raise ValueError("source case is not pinned to OpenFOAM v2512 image")
    if metadata.get("solver") != "interIsoFoam":
        raise ValueError("source case solver is not interIsoFoam")
    control = control_path.read_text(encoding="utf-8")
    opening, closing = _functions_range(control)
    if "nativeAlphaPhiOutlet" in control or "nativeAlphaPhiTargetPatch" in control:
        raise ValueError("source controlDict already contains a native alphaPhi sidecar")
    if "apertureFlux" not in control:
        raise ValueError("source controlDict lacks the per-step aggregate apertureFlux comparator")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    output_control = destination / "system/controlDict"
    control = (
        control[:closing]
        + "\n"
        + _injected_functions(face_zone, target_patch)
        + "\n"
        + control[closing:]
    )
    output_control.write_text(control, encoding="utf-8")

    out_metadata_path = destination / "case-inputs.json"
    output_metadata = json.loads(out_metadata_path.read_text(encoding="utf-8"))
    output_metadata.setdefault("diagnostics", {})["native_face_alphaPhi"] = {
        "status": "instrumented_case_not_yet_run",
        "field": "alphaPhi_",
        "source_selection": {"type": "faceZone", "name": face_zone},
        "optional_target_selection": (
            {"type": "patch", "name": target_patch} if target_patch is not None else None
        ),
        "sampling": "every completed main solver time step via coded functionObject writeControl timeStep/writeInterval 1",
        "rate_convention": "isoAdvection dVf_ divided by main Time::deltaT; row time is completed end-of-step time",
        "sign_convention": "alphaPhi_ oriented with face area vector; source faceZone rates and normals both apply flipMap; target patch uses outward patch Sf",
        "records": "per-rank CSV with one header then timeIndex,time_s,deltaT_s,face_count,per-face signed m3/s rates; static Float64 round-trip ASCII sidecar stores matching output order, processor rank/local mesh face IDs, centers, oriented area vectors, areas, unit normals, exact face-coordinate bounds and faceZone flipMap",
        "duplicate_processor_faces": "faceZone boundary duplicates skip coupled non-owner faces, matching pinned-v2512 surfaceFieldValue setFaceZoneFaces",
        "existing_profile_proxy": "apertureProfile alpha.water/U VTK remains unchanged and is not substituted for native alphaPhi_",
    }
    out_metadata_path.write_text(
        json.dumps(output_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    inventory_after = tree_hashes(source)
    if inventory_after != inventory_before:
        raise RuntimeError("configuration changed the source case")
    expected_changed = {"system/controlDict", "case-inputs.json"}
    output_hashes = tree_hashes(destination)
    changed = sorted(
        relative
        for relative, digest in inventory_before.items()
        if output_hashes.get(relative) != digest
    )
    added = sorted(set(output_hashes) - set(inventory_before))
    if set(changed) != expected_changed or added:
        raise RuntimeError(f"unexpected copied-case changes: changed={changed}, added={added}")
    return {
        "schema": "dash8-native-face-alphaPhi-configuration-v1",
        "status": "configured",
        "source_case": str(source),
        "output_case": str(destination),
        "source_file_count": len(inventory_before),
        "source_inventory_sha256": hashlib.sha256(
            json.dumps(inventory_before, sort_keys=True).encode()
        ).hexdigest(),
        "source_inputs_sha256": sha256_file(metadata_path),
        "configured_controlDict_sha256": sha256_file(output_control),
        "configured_case_inputs_sha256": sha256_file(out_metadata_path),
        "changed_case_files": changed,
        "added_case_files": added,
        "face_zone": face_zone,
        "target_patch": target_patch,
        "openfoam_image_id": metadata["openfoam_image_id"],
        "created_utc": dt.datetime.now(dt.UTC).isoformat(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-case", type=Path, required=True)
    parser.add_argument("--output-case", type=Path, required=True)
    parser.add_argument("--face-zone", default="outletPlane")
    parser.add_argument("--target-patch", help="also instrument a boundary patch, if present")
    parser.add_argument("--record-json", type=Path)
    args = parser.parse_args(argv)
    record = configure_case(
        args.input_case,
        args.output_case,
        face_zone=args.face_zone,
        target_patch=args.target_patch,
    )
    if args.record_json:
        record_path = args.record_json.resolve(strict=False)
        if record_path.exists():
            raise FileExistsError(f"refusing to overwrite preparation record: {record_path}")
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
