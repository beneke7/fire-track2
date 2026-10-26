// Private, read-only diagnostics for the I4F pressure-floor defect audit.

static void i4fReportPressureResidual
(
    const word& stage,
    const word& component,
    const label pass,
    const word& timeName,
    const scalarField& residual
)
{
    scalar maxAbsLocal = 0;
    scalar sumAbsLocal = 0;
    label cellCount = residual.size();

    forAll(residual, celli)
    {
        const scalar value = mag(residual[celli]);
        maxAbsLocal = max(maxAbsLocal, value);
        sumAbsLocal += value;
    }

    reduce(maxAbsLocal, maxOp<scalar>());
    reduce(sumAbsLocal, sumOp<scalar>());
    reduce(cellCount, sumOp<label>());

    Info<< "I4F_PRESSURE_RESIDUAL"
        << " time_s=" << timeName
        << " pass=" << pass
        << " stage=" << stage
        << " component=" << component
        << " maxAbs_m3_s=" << maxAbsLocal
        << " sumAbs_unweighted_m3_s=" << sumAbsLocal
        << " cell_count=" << cellCount
        << " definition=fvMatrix_residual_raw_coupled_source_may_be_counted_twice"
        << " linearization_only_not_fully_coupled_residual=1"
        << nl << endl;
}


// Compare fvMatrix::residual() with operator&(M, p) without changing the
// pressure matrix. In parallel, fvMatrix::residual() adds the explicit
// coupled-neighbour boundary source before the ldu residual path adds it
// again. Remove one copy of that source from the raw residual, and check the
// result against the matrix operator evaluated at the same p_rgh state.
static void i4fReportOperatorPressureDefect
(
    const fvScalarMatrix& matrix,
    const volScalarField& p,
    const fvMesh& mesh,
    const word& stage,
    const word& component,
    const label pass,
    const word& timeName
)
{
    scalarField coupledNeighbourSource(mesh.nCells(), Zero);

    forAll(mesh.boundary(), patchi)
    {
        if (!mesh.boundary()[patchi].coupled())
        {
            continue;
        }

        const scalarField& coeff = matrix.boundaryCoeffs()[patchi];
        tmp<scalarField> tNeighbour
        (
            matrix.psi().boundaryField()[patchi].patchNeighbourField()
        );
        const scalarField& neighbour = tNeighbour();
        const labelUList& faceCells = mesh.boundary()[patchi].faceCells();

        forAll(faceCells, facei)
        {
            coupledNeighbourSource[faceCells[facei]] +=
                coeff[facei]*neighbour[facei];
        }
    }

    const scalarField rawResidual(matrix.residual());
    tmp<volScalarField> tApMinusB(matrix & p);
    const scalarField& apMinusBPerVolume = tApMinusB().primitiveField();

    scalar maxCorrectedLocal = 0;
    scalar sumCorrectedLocal = 0;
    scalar maxOperatorLocal = 0;
    scalar sumOperatorLocal = 0;
    scalar maxIdentityErrorLocal = 0;
    scalar sumIdentityErrorLocal = 0;
    scalar maxCoupledSourceLocal = 0;
    scalar sumCoupledSourceLocal = 0;

    forAll(rawResidual, celli)
    {
        const scalar corrected =
            rawResidual[celli] - coupledNeighbourSource[celli];
        const scalar operatorDefect =
            -apMinusBPerVolume[celli]*mesh.V()[celli];
        const scalar identityError = corrected - operatorDefect;

        maxCorrectedLocal = max(maxCorrectedLocal, mag(corrected));
        sumCorrectedLocal += mag(corrected);
        maxOperatorLocal = max(maxOperatorLocal, mag(operatorDefect));
        sumOperatorLocal += mag(operatorDefect);
        maxIdentityErrorLocal = max(maxIdentityErrorLocal, mag(identityError));
        sumIdentityErrorLocal += mag(identityError);
        maxCoupledSourceLocal = max
        (
            maxCoupledSourceLocal,
            mag(coupledNeighbourSource[celli])
        );
        sumCoupledSourceLocal += mag(coupledNeighbourSource[celli]);
    }

    reduce(maxCorrectedLocal, maxOp<scalar>());
    reduce(sumCorrectedLocal, sumOp<scalar>());
    reduce(maxOperatorLocal, maxOp<scalar>());
    reduce(sumOperatorLocal, sumOp<scalar>());
    reduce(maxIdentityErrorLocal, maxOp<scalar>());
    reduce(sumIdentityErrorLocal, sumOp<scalar>());
    reduce(maxCoupledSourceLocal, maxOp<scalar>());
    reduce(sumCoupledSourceLocal, sumOp<scalar>());

    Info<< "I4F_PRESSURE_OPERATOR_DEFECT"
        << " time_s=" << timeName
        << " pass=" << pass
        << " stage=" << stage
        << " component=" << component
        << " maxAbs_corrected_b_minus_Ap_m3_s=" << maxCorrectedLocal
        << " sumAbs_corrected_b_minus_Ap_unweighted_m3_s=" << sumCorrectedLocal
        << " maxAbs_operator_b_minus_Ap_m3_s=" << maxOperatorLocal
        << " sumAbs_operator_b_minus_Ap_unweighted_m3_s=" << sumOperatorLocal
        << " maxAbs_corrected_minus_operator_m3_s=" << maxIdentityErrorLocal
        << " sumAbs_corrected_minus_operator_unweighted_m3_s=" << sumIdentityErrorLocal
        << " maxAbs_extra_coupled_source_m3_s=" << maxCoupledSourceLocal
        << " sumAbs_extra_coupled_source_unweighted_m3_s=" << sumCoupledSourceLocal
        << " definition=raw_fvMatrix_residual_minus_one_coupled_neighbour_source"
        << " comparison=minus_operator_M_and_p_times_native_cell_volume"
        << " cached_patch_neighbour_state=used_for_both_terms_and_checked_by_identity"
        << " frozen_linearization_not_fully_coupled_reassembly=1"
        << nl << endl;
}


static scalar i4fReportBoundaryMassFlux
(
    const fvMesh& mesh,
    const word& stage,
    const word& phase,
    const surfaceScalarField& massFlux
)
{
    scalar netOutward = 0;

    forAll(mesh.boundary(), patchi)
    {
        if (mesh.boundary()[patchi].coupled())
        {
            continue;
        }

        scalar localPatchFlux = 0;
        forAll(massFlux.boundaryField()[patchi], facei)
        {
            localPatchFlux += massFlux.boundaryField()[patchi][facei];
        }

        reduce(localPatchFlux, sumOp<scalar>());
        netOutward += localPatchFlux;

        Info<< "I4F_PHASE_BOUNDARY_MASS_FLUX"
            << " stage=" << stage
            << " phase=" << phase
            << " patch=" << mesh.boundaryMesh()[patchi].name()
            << " signed_outward_kg_s=" << localPatchFlux
            << " field=alphaPhi_phase_times_interpolated_phase_rho"
            << nl;
    }

    Info<< "I4F_PHASE_BOUNDARY_MASS_FLUX_SUM"
        << " stage=" << stage
        << " phase=" << phase
        << " signed_outward_kg_s=" << netOutward
        << " excludes_coupled_processor_faces=1"
        << nl << endl;

    return netOutward;
}
