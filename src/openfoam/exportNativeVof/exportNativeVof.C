/*---------------------------------------------------------------------------*\
  Native-cell VOF exporter for OpenFOAM v2512.

  Exports only internal fields and native finite-volume connectivity. It does
  not correct boundary conditions, advance a solver, or write to the case.
\*---------------------------------------------------------------------------*/

#include "fvCFD.H"
#include "syncTools.H"
#include "processorPolyPatch.H"
#include "labelIOList.H"
#include "fieldDictionary.H"

#include <cstdint>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

using namespace Foam;

template<class T>
static bool writeRaw(const fileName& path, const std::vector<T>& values)
{
    std::ofstream stream(path.c_str(), std::ios::binary | std::ios::out);
    if (!stream.good()) return false;
    if (!values.empty())
    {
        stream.write
        (
            reinterpret_cast<const char*>(values.data()),
            static_cast<std::streamsize>(values.size()*sizeof(T))
        );
    }
    return stream.good();
}


static std::vector<std::int64_t> toI64(const labelUList& values)
{
    std::vector<std::int64_t> out(values.size());
    forAll(values, i) out[i] = static_cast<std::int64_t>(values[i]);
    return out;
}


int main(int argc, char *argv[])
{
    argList::addOption("outputDir", "directory", "export directory");
    argList::addOption("sourcePatch", "name", "source boundary patch name");
    argList::addOption("snapshotName", "time-directory", "exact saved time-directory name");

    #include "setRootCase.H"
    #include "createTime.H"

    if (!args.found("outputDir") || !args.found("sourcePatch") || !args.found("snapshotName"))
    {
        FatalErrorInFunction
            << "-outputDir, -sourcePatch, and -snapshotName are required"
            << exit(FatalError);
    }

    const word snapshotName(args.get<word>("snapshotName"));
    runTime.setTime(instant(snapshotName), 0);
    #include "createMesh.H"

    const fileName outputDir(args.get<fileName>("outputDir"));
    const word sourcePatchName(args.get<word>("sourcePatch"));
    const label patchi = mesh.boundaryMesh().findPatchID(sourcePatchName);
    if (patchi < 0)
    {
        FatalErrorInFunction
            << "Cannot find source patch " << sourcePatchName
            << exit(FatalError);
    }

    // Read field dictionaries and extract internalField directly. Constructing
    // volFields would instantiate patch-field classes (including coded
    // conditions) and can trigger dynamicCode compilation/cache writes.
    IOobject alphaObject
    (
        "alpha.water", runTime.timeName(), mesh,
        IOobject::MUST_READ, IOobject::NO_WRITE, IOobject::NO_REGISTER
    );
    IOobject velocityObject
    (
        "U", runTime.timeName(), mesh,
        IOobject::MUST_READ, IOobject::NO_WRITE, IOobject::NO_REGISTER
    );
    if
    (
        !alphaObject.typeHeaderOk<labelIOList>(false)
     || !alphaObject.isHeaderClass("volScalarField")
    )
    {
        FatalErrorInFunction
            << "alpha.water must be a volScalarField at " << runTime.timeName()
            << exit(FatalError);
    }
    if
    (
        !velocityObject.typeHeaderOk<labelIOList>(false)
     || !velocityObject.isHeaderClass("volVectorField")
    )
    {
        FatalErrorInFunction
            << "U must be a volVectorField at " << runTime.timeName()
            << exit(FatalError);
    }
    const fieldDictionary alphaDictionary(alphaObject, alphaObject.headerClassName());
    const fieldDictionary velocityDictionary(velocityObject, velocityObject.headerClassName());
    const scalarField alphaInternal("internalField", alphaDictionary, mesh.nCells());
    const vectorField velocityInternal("internalField", velocityDictionary, mesh.nCells());

    labelList globalCellIds(mesh.nCells());
    if (Pstream::parRun())
    {
        labelIOList cellProcAddressing
        (
            IOobject
            (
                "cellProcAddressing",
                mesh.facesInstance(),
                polyMesh::meshSubDir,
                mesh,
                IOobject::MUST_READ,
                IOobject::NO_WRITE,
                IOobject::NO_REGISTER
            )
        );
        if (cellProcAddressing.size() != mesh.nCells())
        {
            FatalErrorInFunction
                << "cellProcAddressing has " << cellProcAddressing.size()
                << " entries for " << mesh.nCells() << " local cells"
                << exit(FatalError);
        }
        globalCellIds = cellProcAddressing;
    }
    else
    {
        forAll(globalCellIds, celli) globalCellIds[celli] = celli;
    }

    std::vector<double> volumes(mesh.nCells());
    std::vector<double> alpha(mesh.nCells());
    std::vector<double> velocityXYZ(3*mesh.nCells());
    std::vector<double> centresXYZ(3*mesh.nCells());
    std::vector<double> boundsMinMaxXYZ(6*mesh.nCells());
    const scalarField& meshVolumes = mesh.V();
    const vectorField& cellCentres = mesh.C().primitiveField();
    forAll(meshVolumes, celli)
    {
        volumes[celli] = static_cast<double>(meshVolumes[celli]);
        alpha[celli] = static_cast<double>(alphaInternal[celli]);
        velocityXYZ[3*celli] = static_cast<double>(velocityInternal[celli].x());
        velocityXYZ[3*celli + 1] = static_cast<double>(velocityInternal[celli].y());
        velocityXYZ[3*celli + 2] = static_cast<double>(velocityInternal[celli].z());
        centresXYZ[3*celli] = static_cast<double>(cellCentres[celli].x());
        centresXYZ[3*celli + 1] = static_cast<double>(cellCentres[celli].y());
        centresXYZ[3*celli + 2] = static_cast<double>(cellCentres[celli].z());

        scalar minX = GREAT;
        scalar minY = GREAT;
        scalar minZ = GREAT;
        scalar maxX = -GREAT;
        scalar maxY = -GREAT;
        scalar maxZ = -GREAT;
        const cell& cellFaces = mesh.cells()[celli];
        forAll(cellFaces, cellFacei)
        {
            const face& meshFace = mesh.faces()[cellFaces[cellFacei]];
            forAll(meshFace, facePointi)
            {
                const point& meshPoint = mesh.points()[meshFace[facePointi]];
                minX = min(minX, meshPoint.x());
                minY = min(minY, meshPoint.y());
                minZ = min(minZ, meshPoint.z());
                maxX = max(maxX, meshPoint.x());
                maxY = max(maxY, meshPoint.y());
                maxZ = max(maxZ, meshPoint.z());
            }
        }
        boundsMinMaxXYZ[6*celli] = static_cast<double>(minX);
        boundsMinMaxXYZ[6*celli + 1] = static_cast<double>(minY);
        boundsMinMaxXYZ[6*celli + 2] = static_cast<double>(minZ);
        boundsMinMaxXYZ[6*celli + 3] = static_cast<double>(maxX);
        boundsMinMaxXYZ[6*celli + 4] = static_cast<double>(maxY);
        boundsMinMaxXYZ[6*celli + 5] = static_cast<double>(maxZ);
    }

    std::vector<std::int64_t> internalEdges(2*mesh.nInternalFaces());
    const labelUList& faceOwner = mesh.faceOwner();
    const labelUList& faceNeighbour = mesh.faceNeighbour();
    for (label facei = 0; facei < mesh.nInternalFaces(); ++facei)
    {
        internalEdges[2*facei] = globalCellIds[faceOwner[facei]];
        internalEdges[2*facei + 1] = globalCellIds[faceNeighbour[facei]];
    }

    const List<label> neighbourGlobalCell =
        syncTools::swapBoundaryCellList(mesh, globalCellIds);
    std::vector<std::int64_t> processorEdges;
    forAll(mesh.boundaryMesh(), boundaryi)
    {
        const polyPatch& boundaryPatch = mesh.boundaryMesh()[boundaryi];
        if (!isA<processorPolyPatch>(boundaryPatch)) continue;
        const label boundaryFaceOffset =
            boundaryPatch.start() - mesh.nInternalFaces();
        const labelList& faceCells = boundaryPatch.faceCells();
        forAll(faceCells, patchFacei)
        {
            const label neighbourGlobal =
                neighbourGlobalCell[boundaryFaceOffset + patchFacei];
            if (neighbourGlobal < 0)
            {
                FatalErrorInFunction
                    << "Missing neighbour global cell on processor patch "
                    << boundaryPatch.name() << " face " << patchFacei
                    << exit(FatalError);
            }
            processorEdges.push_back(globalCellIds[faceCells[patchFacei]]);
            processorEdges.push_back(neighbourGlobal);
        }
    }

    const polyPatch& sourcePatch = mesh.boundaryMesh()[patchi];
    std::vector<std::int64_t> sourceOwners(sourcePatch.faceCells().size());
    std::vector<std::int64_t> sourceLocalFaces(sourcePatch.faceCells().size());
    std::vector<double> sourceCentresXYZ(3*sourcePatch.faceCells().size());
    std::vector<double> sourceAreaVectorsXYZ(3*sourcePatch.faceCells().size());
    const vectorField& sourceCentres = mesh.Cf().boundaryField()[patchi];
    const vectorField& sourceAreaVectors = mesh.Sf().boundaryField()[patchi];
    forAll(sourcePatch.faceCells(), sourceFacei)
    {
        sourceOwners[sourceFacei] =
            globalCellIds[sourcePatch.faceCells()[sourceFacei]];
        sourceLocalFaces[sourceFacei] = sourcePatch.start() + sourceFacei;
        sourceCentresXYZ[3*sourceFacei] = sourceCentres[sourceFacei].x();
        sourceCentresXYZ[3*sourceFacei + 1] = sourceCentres[sourceFacei].y();
        sourceCentresXYZ[3*sourceFacei + 2] = sourceCentres[sourceFacei].z();
        sourceAreaVectorsXYZ[3*sourceFacei] = sourceAreaVectors[sourceFacei].x();
        sourceAreaVectorsXYZ[3*sourceFacei + 1] = sourceAreaVectors[sourceFacei].y();
        sourceAreaVectorsXYZ[3*sourceFacei + 2] = sourceAreaVectors[sourceFacei].z();
    }

    const label rank = Pstream::myProcNo();
    const label nProcs = Pstream::nProcs();
    const std::uint16_t endianProbe = 1;
    if (*reinterpret_cast<const unsigned char*>(&endianProbe) != 1)
    {
        FatalErrorInFunction
            << "Only little-endian hosts are supported by the declared raw export format"
            << exit(FatalError);
    }
    char rankName[32];
    std::snprintf(rankName, sizeof(rankName), "rank-%04d", int(rank));
    const fileName rankDir = outputDir/rankName;
    mkDir(rankDir);

    const bool written =
        writeRaw(rankDir/"cell_global_ids.i64", toI64(globalCellIds))
     && writeRaw(rankDir/"cell_volumes_m3.f64", volumes)
     && writeRaw(rankDir/"alpha_water.f64", alpha)
     && writeRaw(rankDir/"velocity_xyz_m_s.f64", velocityXYZ)
     && writeRaw(rankDir/"cell_centres_xyz_m.f64", centresXYZ)
     && writeRaw(rankDir/"cell_bounds_minmax_xyz_m.f64", boundsMinMaxXYZ)
     && writeRaw(rankDir/"internal_edges_global.i64", internalEdges)
     && writeRaw(rankDir/"processor_edges_global.i64", processorEdges)
     && writeRaw(rankDir/"source_owner_global.i64", sourceOwners)
     && writeRaw(rankDir/"source_face_local_ids.i64", sourceLocalFaces)
     && writeRaw(rankDir/"source_face_centres_xyz_m.f64", sourceCentresXYZ)
     && writeRaw(rankDir/"source_face_area_vectors_xyz_m2.f64", sourceAreaVectorsXYZ);
    if (!written)
    {
        FatalErrorInFunction
            << "Failed writing one or more native export arrays under " << rankDir
            << exit(FatalError);
    }

    OFstream metadata(rankDir/"metadata.json");
    metadata
        << "{\n"
        << "  \"format\": \"fire-track2-native-vof-v1\",\n"
        << "  \"rank\": " << rank << ",\n"
        << "  \"rank_count\": " << nProcs << ",\n"
        << "  \"time_name\": \"" << runTime.timeName() << "\",\n"
        << "  \"time_value_s\": " << runTime.value() << ",\n"
        << "  \"local_cell_count\": " << mesh.nCells() << ",\n"
        << "  \"internal_face_count\": " << mesh.nInternalFaces() << ",\n"
        << "  \"processor_edge_occurrences\": "
        << processorEdges.size()/2 << ",\n"
        << "  \"source_patch\": \"" << sourcePatchName << "\",\n"
        << "  \"source_face_count_local\": " << sourceOwners.size() << ",\n"
        << "  \"source_face_order\": \"native mesh face labels in boundary patch order\",\n"
        << "  \"parallel_global_id_source\": \""
        << (Pstream::parRun() ? "constant/polyMesh/cellProcAddressing" : "serial identity")
        << "\",\n"
        << "  \"label_bytes_input\": " << sizeof(label) << ",\n"
        << "  \"scalar_bytes_input\": " << sizeof(scalar) << ",\n"
        << "  \"export_integer_bytes\": 8,\n"
        << "  \"export_float_bytes\": 8,\n"
        << "  \"export_byte_order\": \"little-endian\",\n"
        << "  \"fields_read_internal_only\": [\"alpha.water\", \"U\"],\n"
        << "  \"cell_centres\": \"OpenFOAM fvMesh C() in native local cell order\",\n"
        << "  \"cell_bounds\": \"axis-aligned min/max over all native polyMesh face vertices of each cell\",\n"
        << "  \"boundary_conditions_corrected\": false\n"
        << "}\n";

    Info<< "Native VOF export: rank " << rank << '/' << nProcs
        << " cells=" << mesh.nCells()
        << " internalFaces=" << mesh.nInternalFaces()
        << " processorEdges=" << processorEdges.size()/2
        << " sourceFaces=" << sourceOwners.size()
        << " output=" << rankDir << nl << endl;

    return 0;
}
