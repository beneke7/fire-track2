// Small physical-time candidate observer and same-time joint alpha/water-flux
// blend. Source terms are the actual Sp/Su/divU used by advector. No old-time
// field is read here; the candidate remains the unrelaxed MULES result.
const scalar i4fPhysicalAlphaOmega = i4fPhysicalAlphaFluxRelaxOmega;
const scalar i4fPhysicalAlphaDt = runTime.deltaTValue();
const scalarField& i4fPhysicalVolumes = mesh.V();
const volScalarField& i4fPhysicalAlphaEntryField = i4fPhysicalAlphaEntry();
const surfaceScalarField& i4fPhysicalAlphaPhiEntryField =
    i4fPhysicalAlphaPhiEntry();
tmp<volScalarField> ti4fPhysicalCandidateDivAlphaPhi = fvc::div(alphaPhi10);
const volScalarField& i4fPhysicalCandidateDivAlphaPhi =
    ti4fPhysicalCandidateDivAlphaPhi();

scalar i4fCandidateDeltaL1V = 0;
scalar i4fCandidateDelta2V = 0;
scalar i4fCandidateDeltaMax = 0;
scalar i4fCandidateResidualL1V = 0;
scalar i4fCandidateResidual2V = 0;
scalar i4fCandidateResidualMax = 0;
scalar i4fSourceSplitErrorL1V = 0;
scalar i4fSourceSplitErrorMax = 0;
scalar i4fCellVolumeSum = 0;
scalar i4fCandidateAlphaMin = GREAT;
scalar i4fCandidateAlphaMax = -GREAT;
label i4fCandidateAlphaBelowZero = 0;
label i4fCandidateAlphaAboveOne = 0;

forAll(alpha1, celli)
{
    const scalar entry = i4fPhysicalAlphaEntryField[celli];
    const scalar sourceAlpha = i4fPhysicalMulesSourceAlpha[celli];
    const scalar candidate = alpha1[celli];
    const scalar delta = candidate - entry;
    const scalar residual =
        delta/i4fPhysicalAlphaDt
      + i4fPhysicalCandidateDivAlphaPhi[celli]
      -
        (
            Su[celli]
          + Sp[celli]*candidate
          + divU[celli]*min(candidate, scalar(1))
        );
    const scalar gamma = dgdt[celli];
    scalar sourceSp = 0;
    scalar sourceSu = 0;
    if (gamma > 0)
    {
        sourceSp -= gamma/Foam::max(1.0 - sourceAlpha, i4fAlphaSourceDenominatorFloor);
        sourceSu += gamma/Foam::max(1.0 - sourceAlpha, i4fAlphaSourceDenominatorFloor);
    }
    else if (gamma < 0)
    {
        sourceSp += gamma/Foam::max(sourceAlpha, i4fAlphaSourceDenominatorFloor);
    }
    const scalar sourceError =
        max(mag(Sp[celli] - sourceSp), mag(Su[celli] - sourceSu));
    const scalar volume = i4fPhysicalVolumes[celli];

    i4fCandidateDeltaL1V += mag(delta)*volume;
    i4fCandidateDelta2V += sqr(delta)*volume;
    i4fCandidateDeltaMax = max(i4fCandidateDeltaMax, mag(delta));
    i4fCandidateResidualL1V += mag(residual)*volume;
    i4fCandidateResidual2V += sqr(residual)*volume;
    i4fCandidateResidualMax = max(i4fCandidateResidualMax, mag(residual));
    i4fSourceSplitErrorL1V += sourceError*volume;
    i4fSourceSplitErrorMax = max(i4fSourceSplitErrorMax, sourceError);
    i4fCellVolumeSum += volume;
    i4fCandidateAlphaMin = min(i4fCandidateAlphaMin, candidate);
    i4fCandidateAlphaMax = max(i4fCandidateAlphaMax, candidate);
    i4fCandidateAlphaBelowZero += candidate < 0;
    i4fCandidateAlphaAboveOne += candidate > 1;
}

scalar i4fCandidateFluxDeltaMax = 0;
forAll(alphaPhi10.primitiveField(), facei)
{
    i4fCandidateFluxDeltaMax = max
    (
        i4fCandidateFluxDeltaMax,
        mag
        (
            alphaPhi10.primitiveField()[facei]
          - i4fPhysicalAlphaPhiEntryField.primitiveField()[facei]
        )
    );
}
forAll(alphaPhi10.boundaryField(), patchi)
{
    forAll(alphaPhi10.boundaryField()[patchi], facei)
    {
        i4fCandidateFluxDeltaMax = max
        (
            i4fCandidateFluxDeltaMax,
            mag
            (
                alphaPhi10.boundaryField()[patchi][facei]
              - i4fPhysicalAlphaPhiEntryField.boundaryField()[patchi][facei]
            )
        );
    }
}

reduce(i4fCandidateDeltaL1V, sumOp<scalar>());
reduce(i4fCandidateDelta2V, sumOp<scalar>());
reduce(i4fCandidateDeltaMax, maxOp<scalar>());
reduce(i4fCandidateResidualL1V, sumOp<scalar>());
reduce(i4fCandidateResidual2V, sumOp<scalar>());
reduce(i4fCandidateResidualMax, maxOp<scalar>());
reduce(i4fSourceSplitErrorL1V, sumOp<scalar>());
reduce(i4fSourceSplitErrorMax, maxOp<scalar>());
reduce(i4fCellVolumeSum, sumOp<scalar>());
reduce(i4fCandidateAlphaMin, minOp<scalar>());
reduce(i4fCandidateAlphaMax, maxOp<scalar>());
reduce(i4fCandidateAlphaBelowZero, sumOp<label>());
reduce(i4fCandidateAlphaAboveOne, sumOp<label>());
reduce(i4fCandidateFluxDeltaMax, maxOp<scalar>());

// The joint alpha/flux blend placement follows the reviewed full-trigger
// attempt-06 map identity. alphaPhi10 is assigned directly: with one subcycle,
// talphaPhi1 is a borrowed const alias and must never be mutated via ref().
alpha1 =
    (1.0 - i4fPhysicalAlphaOmega)*i4fPhysicalAlphaEntryField
  + i4fPhysicalAlphaOmega*alpha1;
alphaPhi10 =
    (1.0 - i4fPhysicalAlphaOmega)*i4fPhysicalAlphaPhiEntryField
  + i4fPhysicalAlphaOmega*alphaPhi10;
// Stock rhofs.H runs immediately after this alphaEqn.H include and rebuilds
// rhoPhi from the blended alphaPhi10 for the configured Euler/static path.

// Record source-form consistency and post-blend local finite-volume residual.
tmp<volScalarField> ti4fPhysicalAppliedDivAlphaPhi = fvc::div(alphaPhi10);
const volScalarField& i4fPhysicalAppliedDivAlphaPhi =
    ti4fPhysicalAppliedDivAlphaPhi();
scalar i4fAppliedResidualL1V = 0;
scalar i4fAppliedResidual2V = 0;
scalar i4fAppliedResidualMax = 0;
scalar i4fAppliedAlphaMin = GREAT;
scalar i4fAppliedAlphaMax = -GREAT;
label i4fAppliedAlphaBelowZero = 0;
label i4fAppliedAlphaAboveOne = 0;
forAll(alpha1, celli)
{
    const scalar applied = alpha1[celli];
    const scalar residual =
        (applied - i4fPhysicalAlphaEntryField[celli])/i4fPhysicalAlphaDt
      + i4fPhysicalAppliedDivAlphaPhi[celli]
      -
        (
            Su[celli]
          + Sp[celli]*applied
          + divU[celli]*min(applied, scalar(1))
        );
    const scalar volume = i4fPhysicalVolumes[celli];
    i4fAppliedResidualL1V += mag(residual)*volume;
    i4fAppliedResidual2V += sqr(residual)*volume;
    i4fAppliedResidualMax = max(i4fAppliedResidualMax, mag(residual));
    i4fAppliedAlphaMin = min(i4fAppliedAlphaMin, applied);
    i4fAppliedAlphaMax = max(i4fAppliedAlphaMax, applied);
    i4fAppliedAlphaBelowZero += applied < 0;
    i4fAppliedAlphaAboveOne += applied > 1;
}
scalar i4fAppliedFluxDeltaMax = 0;
forAll(alphaPhi10.primitiveField(), facei)
{
    i4fAppliedFluxDeltaMax = max
    (
        i4fAppliedFluxDeltaMax,
        mag
        (
            alphaPhi10.primitiveField()[facei]
          - i4fPhysicalAlphaPhiEntryField.primitiveField()[facei]
        )
    );
}
forAll(alphaPhi10.boundaryField(), patchi)
{
    forAll(alphaPhi10.boundaryField()[patchi], facei)
    {
        i4fAppliedFluxDeltaMax = max
        (
            i4fAppliedFluxDeltaMax,
            mag
            (
                alphaPhi10.boundaryField()[patchi][facei]
              - i4fPhysicalAlphaPhiEntryField.boundaryField()[patchi][facei]
            )
        );
    }
}
reduce(i4fAppliedResidualL1V, sumOp<scalar>());
reduce(i4fAppliedResidual2V, sumOp<scalar>());
reduce(i4fAppliedResidualMax, maxOp<scalar>());
reduce(i4fAppliedAlphaMin, minOp<scalar>());
reduce(i4fAppliedAlphaMax, maxOp<scalar>());
reduce(i4fAppliedAlphaBelowZero, sumOp<label>());
reduce(i4fAppliedAlphaAboveOne, sumOp<label>());
reduce(i4fAppliedFluxDeltaMax, maxOp<scalar>());

if (Pstream::master())
{
    Info<< "I4F_PHYSICAL_ALPHA_FLUX_RELAX"
        << " time_s=" << runTime.timeName()
        << " omega=" << i4fPhysicalAlphaOmega
        << " candidate_alpha_delta_L1="
        << i4fCandidateDeltaL1V/i4fCellVolumeSum
        << " candidate_alpha_delta_rms="
        << Foam::sqrt(i4fCandidateDelta2V/i4fCellVolumeSum)
        << " candidate_alpha_delta_max=" << i4fCandidateDeltaMax
        << " candidate_alpha_min=" << i4fCandidateAlphaMin
        << " candidate_alpha_max=" << i4fCandidateAlphaMax
        << " candidate_alpha_below_zero_cells=" << i4fCandidateAlphaBelowZero
        << " candidate_alpha_above_one_cells=" << i4fCandidateAlphaAboveOne
        << " candidate_alphaPhi_delta_max_m3_s=" << i4fCandidateFluxDeltaMax
        << " source_split_consistency_L1_s-1="
        << i4fSourceSplitErrorL1V/i4fCellVolumeSum
        << " source_split_consistency_max_s-1=" << i4fSourceSplitErrorMax
        << " candidate_local_source_residual_L1_s-1="
        << i4fCandidateResidualL1V/i4fCellVolumeSum
        << " candidate_local_source_residual_rms_s-1="
        << Foam::sqrt(i4fCandidateResidual2V/i4fCellVolumeSum)
        << " candidate_local_source_residual_max_s-1="
        << i4fCandidateResidualMax
        << " applied_local_source_residual_L1_s-1="
        << i4fAppliedResidualL1V/i4fCellVolumeSum
        << " applied_local_source_residual_rms_s-1="
        << Foam::sqrt(i4fAppliedResidual2V/i4fCellVolumeSum)
        << " applied_local_source_residual_max_s-1="
        << i4fAppliedResidualMax
        << " applied_alpha_min=" << i4fAppliedAlphaMin
        << " applied_alpha_max=" << i4fAppliedAlphaMax
        << " applied_alpha_below_zero_cells=" << i4fAppliedAlphaBelowZero
        << " applied_alpha_above_one_cells=" << i4fAppliedAlphaAboveOne
        << " applied_alphaPhi_delta_max_m3_s=" << i4fAppliedFluxDeltaMax
        << " source_form=Su+Sp*alpha+divU*min(alpha,1)"
        << " source_reference=alpha_before_last_MULES_corrector_source_split"
        << " candidate=unrelaxed_stock_MULES"
        << " flux=actual_water_alphaPhi10"
        << " residual=ddt_euler_alpha+div(alphaPhi10)-source"
        << " entry_snapshot=same_time_pre_MULES_no_oldTime"
        << nl << endl;
}
