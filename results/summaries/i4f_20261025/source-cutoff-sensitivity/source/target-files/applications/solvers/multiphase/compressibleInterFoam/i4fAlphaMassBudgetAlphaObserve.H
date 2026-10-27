// Default-off, read-only alpha budget. This header is included after the
// optional alpha/alphaPhi relaxation, while the source coefficients assembled
// for this MULES update and the matching source-alpha state are still in scope.
const word i4fAlphaMassBudgetAlphaDdtKey
(
    "ddt(" + alpha1.name() + ')'
);
const word i4fAlphaMassBudgetAlphaRhoDdtKey
(
    "ddt(" + alpha1.name() + ',' + rho1.name() + ')'
);
const word i4fAlphaMassBudgetAlphaDdtScheme
(
    mesh.ddtScheme(i4fAlphaMassBudgetAlphaDdtKey)
);
const word i4fAlphaMassBudgetAlphaRhoDdtScheme
(
    mesh.ddtScheme(i4fAlphaMassBudgetAlphaRhoDdtKey)
);
const bool i4fAlphaMassBudgetSupported =
    !LTS
 && !mesh.moving()
 && nAlphaSubCycles == 1
 && nAlphaCorr == 1
 && MULESCorr
 && !alphaApplyPrevCorr
 && i4fFrozenPredictorSp
 && i4fFrozenPredictorFullSource
 && i4fAlphaMassBudgetAlphaDdtScheme
    == fv::EulerDdtScheme<scalar>::typeName
 && i4fAlphaMassBudgetAlphaRhoDdtScheme
    == fv::EulerDdtScheme<scalar>::typeName;

if (i4fAlphaMassBudgetAudit && !i4fAlphaMassBudgetSupported)
{
    i4fAlphaMassBudgetSourceValid = false;
    if (Pstream::master())
    {
        Info<< "I4F_ALPHA_MASS_BUDGET status=unsupported"
            << " time_s=" << runTime.timeName()
            << " requires=static_Euler_full_predictor_source_MULESCorr"
               "_nAlphaCorr1_nSubCycles1"
            << " alpha_ddt_key=" << i4fAlphaMassBudgetAlphaDdtKey
            << " alpha_ddt_scheme=" << i4fAlphaMassBudgetAlphaDdtScheme
            << " alpha_rho_ddt_key=" << i4fAlphaMassBudgetAlphaRhoDdtKey
            << " alpha_rho_ddt_scheme="
            << i4fAlphaMassBudgetAlphaRhoDdtScheme
            << nl;
    }
}
else if (i4fAlphaMassBudgetAudit)
{
    const bool i4fAlphaBudgetUsePredictor =
        i4fFrozenPredictorFullSource || i4fFrozenPredictorSp;
    const word i4fAlphaBudgetMode =
        i4fFrozenPredictorFullSource
      ? word("frozen_predictor_full_source")
      : i4fFrozenPredictorSp
      ? word("frozen_predictor_Sp_lagged_divU")
      : word("standard_MULES_corrector_source");

    const surfaceScalarField& i4fAlphaBudgetCandidateFlux =
        i4fPhysicalAlphaFluxRelaxActive
      ? i4fAlphaMassBudgetCandidatePhi()
      : alphaPhi10;
    tmp<volScalarField> tI4fAlphaBudgetCandidateDiv
    (
        fvc::div(i4fAlphaBudgetCandidateFlux)
    );
    tmp<volScalarField> tI4fAlphaBudgetAppliedDiv(fvc::div(alphaPhi10));
    const volScalarField& i4fAlphaBudgetCandidateDiv =
        tI4fAlphaBudgetCandidateDiv();
    const volScalarField& i4fAlphaBudgetAppliedDiv =
        tI4fAlphaBudgetAppliedDiv();
    const scalarField& i4fAlphaBudgetOld = alpha1.oldTime().primitiveField();

    scalar i4fAlphaBudgetCandidateSignedV = 0;
    scalar i4fAlphaBudgetCandidateL1V = 0;
    scalar i4fAlphaBudgetCandidateMax = 0;
    scalar i4fAlphaBudgetAppliedSignedV = 0;
    scalar i4fAlphaBudgetAppliedL1V = 0;
    scalar i4fAlphaBudgetAppliedMax = 0;
    scalar i4fAlphaBudgetGammaAssemblyAppliedSignedV = 0;
    scalar i4fAlphaBudgetGammaAppliedSignedV = 0;
    scalar i4fAlphaBudgetGammaCutAppliedSignedV = 0;
    scalar i4fAlphaBudgetGammaCutAppliedL1V = 0;
    scalar i4fAlphaBudgetGammaStateAppliedSignedV = 0;
    scalar i4fAlphaBudgetGammaStateAppliedL1V = 0;
    scalar i4fAlphaBudgetDivUAppliedSignedV = 0;
    scalar i4fAlphaBudgetSplitErrorMax = 0;
    scalar i4fAlphaBudgetAlphaSourceMin = GREAT;
    scalar i4fAlphaBudgetAlphaSourceMax = -GREAT;
    scalar i4fAlphaBudgetGammaMin = GREAT;
    scalar i4fAlphaBudgetGammaMax = -GREAT;
    scalar i4fAlphaBudgetSuMin = GREAT;
    scalar i4fAlphaBudgetSuMax = -GREAT;
    scalar i4fAlphaBudgetSpMin = GREAT;
    scalar i4fAlphaBudgetSpMax = -GREAT;
    label i4fAlphaBudgetSourceDenominatorFloorCells = 0;

    const label i4fAlphaBudgetSourceCall =
        i4fAlphaBudgetUsePredictor
      ? i4fAlphaMassBudgetPredictorSourceCallIndex
      : i4fAlphaSuSpCallIndex;

    forAll(alpha1, celli)
    {
        scalar alphaSource = 0;
        scalar gamma = 0;
        scalar sourceSu = 0;
        scalar sourceSp = 0;
        scalar sourceDivU = 0;
        scalar divUEvalAlpha = 0;

        if (i4fAlphaBudgetUsePredictor)
        {
            alphaSource = i4fAlphaBeforePredictor[celli];
            gamma = i4fDgdtPredictor[celli];
            sourceSu = i4fSuPredictor[celli];
            sourceSp = i4fSpPredictor[celli];
            sourceDivU = i4fDivUPredictor[celli];
            divUEvalAlpha = i4fFrozenPredictorFullSource
              ? alpha1[celli]
              : i4fAlphaPredictor[celli];
        }
        else
        {
            alphaSource = i4fAlphaMassBudgetMulesSourceAlpha[celli];
            gamma = dgdt[celli];
            sourceSu = Su[celli];
            sourceSp = Sp[celli];
            sourceDivU = divU[celli];
            divUEvalAlpha = min(alpha1[celli], scalar(1));
        }

        if
        (
            (gamma > 0 && 1.0 - alphaSource < i4fAlphaSourceDenominatorFloor)
         || (gamma < 0 && alphaSource < i4fAlphaSourceDenominatorFloor)
        )
        {
            ++i4fAlphaBudgetSourceDenominatorFloorCells;
        }

        i4fAlphaMassBudgetAlphaSource[celli] = alphaSource;
        i4fAlphaMassBudgetGamma[celli] = gamma;
        i4fAlphaMassBudgetSu[celli] = sourceSu;
        i4fAlphaMassBudgetSp[celli] = sourceSp;
        i4fAlphaMassBudgetDivU[celli] = sourceDivU;
        i4fAlphaMassBudgetDivUEvalAlpha[celli] = divUEvalAlpha;
        i4fAlphaBudgetAlphaSourceMin = min
        (
            i4fAlphaBudgetAlphaSourceMin,
            alphaSource
        );
        i4fAlphaBudgetAlphaSourceMax = max
        (
            i4fAlphaBudgetAlphaSourceMax,
            alphaSource
        );
        i4fAlphaBudgetGammaMin = min(i4fAlphaBudgetGammaMin, gamma);
        i4fAlphaBudgetGammaMax = max(i4fAlphaBudgetGammaMax, gamma);
        i4fAlphaBudgetSuMin = min(i4fAlphaBudgetSuMin, sourceSu);
        i4fAlphaBudgetSuMax = max(i4fAlphaBudgetSuMax, sourceSu);
        i4fAlphaBudgetSpMin = min(i4fAlphaBudgetSpMin, sourceSp);
        i4fAlphaBudgetSpMax = max(i4fAlphaBudgetSpMax, sourceSp);

        struct I4fAlphaBudgetSourceTerms
        {
            scalar effective;
            scalar gammaActual;
            scalar gammaAssembly;
            scalar gammaCut;
            scalar gammaState;
            scalar splitError;
        };
        auto i4fSourceTerms =
        [gamma, alphaSource, sourceSu, sourceSp, sourceDivU]
        (const scalar alphaEval, const scalar divUEval)
         -> I4fAlphaBudgetSourceTerms
        {
            // Finite algebraic partition of the assembled Su/Sp source.
            // gammaCut is not an uncut-source estimate or causal attribution.
            const scalar gammaAssembly = sourceSu + sourceSp*alphaSource;
            const scalar gammaActual = sourceSu + sourceSp*alphaEval;
            const scalar gammaCut = gammaAssembly - gamma;
            const scalar gammaState = sourceSp*(alphaEval - alphaSource);
            const scalar splitError =
                gammaActual - (gamma + gammaCut + gammaState);
            const scalar divUSource = sourceDivU*divUEval;
            return I4fAlphaBudgetSourceTerms
            {
                gammaActual + divUSource,
                gammaActual,
                gammaAssembly,
                gammaCut,
                gammaState,
                splitError
            };
        };

        const scalar alphaCandidate = i4fAlphaMassBudgetCandidateAlpha[celli];
        const auto candidateTerms = i4fSourceTerms
        (
            alphaCandidate,
            i4fFrozenPredictorSp && !i4fFrozenPredictorFullSource
              ? i4fAlphaPredictor[celli]
              : i4fFrozenPredictorFullSource
              ? alphaCandidate
              : min(alphaCandidate, scalar(1))
        );
        const scalar candidateResidual =
            (alphaCandidate - i4fAlphaBudgetOld[celli])
           /runTime.deltaTValue()
          + i4fAlphaBudgetCandidateDiv[celli]
          - candidateTerms.effective;
        const scalar appliedAlpha = alpha1[celli];
        const auto appliedTerms = i4fSourceTerms
        (
            appliedAlpha,
            i4fAlphaMassBudgetDivUEvalAlpha[celli]
        );
        const scalar appliedResidual =
            (appliedAlpha - i4fAlphaBudgetOld[celli])
           /runTime.deltaTValue()
          + i4fAlphaBudgetAppliedDiv[celli]
          - appliedTerms.effective;
        const scalar volume = mesh.V()[celli];

        i4fAlphaBudgetCandidateSignedV += candidateResidual*volume;
        i4fAlphaBudgetCandidateL1V += mag(candidateResidual)*volume;
        i4fAlphaBudgetCandidateMax =
            max(i4fAlphaBudgetCandidateMax, mag(candidateResidual));
        i4fAlphaBudgetAppliedSignedV += appliedResidual*volume;
        i4fAlphaBudgetAppliedL1V += mag(appliedResidual)*volume;
        i4fAlphaBudgetAppliedMax =
            max(i4fAlphaBudgetAppliedMax, mag(appliedResidual));
        i4fAlphaBudgetGammaAssemblyAppliedSignedV +=
            appliedTerms.gammaAssembly*volume;
        i4fAlphaBudgetGammaAppliedSignedV +=
            appliedTerms.gammaActual*volume;
        i4fAlphaBudgetGammaCutAppliedSignedV +=
            appliedTerms.gammaCut*volume;
        i4fAlphaBudgetGammaCutAppliedL1V +=
            mag(appliedTerms.gammaCut)*volume;
        i4fAlphaBudgetGammaStateAppliedSignedV +=
            appliedTerms.gammaState*volume;
        i4fAlphaBudgetGammaStateAppliedL1V +=
            mag(appliedTerms.gammaState)*volume;
        i4fAlphaBudgetDivUAppliedSignedV +=
            (appliedTerms.effective
           - appliedTerms.gammaActual)*volume;
        i4fAlphaBudgetSplitErrorMax =
            max(i4fAlphaBudgetSplitErrorMax, mag(appliedTerms.splitError));
    }

    reduce(i4fAlphaBudgetCandidateSignedV, sumOp<scalar>());
    reduce(i4fAlphaBudgetCandidateL1V, sumOp<scalar>());
    reduce(i4fAlphaBudgetCandidateMax, maxOp<scalar>());
    reduce(i4fAlphaBudgetAppliedSignedV, sumOp<scalar>());
    reduce(i4fAlphaBudgetAppliedL1V, sumOp<scalar>());
    reduce(i4fAlphaBudgetAppliedMax, maxOp<scalar>());
    reduce(i4fAlphaBudgetGammaAssemblyAppliedSignedV, sumOp<scalar>());
    reduce(i4fAlphaBudgetGammaAppliedSignedV, sumOp<scalar>());
    reduce(i4fAlphaBudgetGammaCutAppliedSignedV, sumOp<scalar>());
    reduce(i4fAlphaBudgetGammaCutAppliedL1V, sumOp<scalar>());
    reduce(i4fAlphaBudgetGammaStateAppliedSignedV, sumOp<scalar>());
    reduce(i4fAlphaBudgetGammaStateAppliedL1V, sumOp<scalar>());
    reduce(i4fAlphaBudgetDivUAppliedSignedV, sumOp<scalar>());
    reduce(i4fAlphaBudgetSplitErrorMax, maxOp<scalar>());
    reduce(i4fAlphaBudgetAlphaSourceMin, minOp<scalar>());
    reduce(i4fAlphaBudgetAlphaSourceMax, maxOp<scalar>());
    reduce(i4fAlphaBudgetGammaMin, minOp<scalar>());
    reduce(i4fAlphaBudgetGammaMax, maxOp<scalar>());
    reduce(i4fAlphaBudgetSuMin, minOp<scalar>());
    reduce(i4fAlphaBudgetSuMax, maxOp<scalar>());
    reduce(i4fAlphaBudgetSpMin, minOp<scalar>());
    reduce(i4fAlphaBudgetSpMax, maxOp<scalar>());
    reduce(i4fAlphaBudgetSourceDenominatorFloorCells, sumOp<label>());

    i4fAlphaMassBudgetSourceValid = true;
    i4fAlphaMassBudgetTimeIndex = runTime.timeIndex();
    i4fAlphaMassBudgetOuterIteration = i4fOuterLoop;
    i4fAlphaMassBudgetSourceCallIndex = i4fAlphaBudgetSourceCall;
    i4fAlphaMassBudgetDgdtGeneration = i4fDgdtGeneration;
    i4fAlphaMassBudgetSourceMode = i4fAlphaBudgetMode;

    if (Pstream::master())
    {
        Info<< "I4F_ALPHA_MASS_BUDGET_ALPHA_V3"
            << " time_s=" << runTime.timeName()
            << " time_index=" << runTime.timeIndex()
            << " outer_iteration=" << i4fOuterLoop
            << " source_mode=" << i4fAlphaBudgetMode
            << " source_call_index=" << i4fAlphaBudgetSourceCall
            << " alpha_ddt_scheme=" << mesh.ddtScheme("ddt(alpha)")
            << " alpha_rho_ddt_scheme="
            << mesh.ddtScheme("ddt(alpha1,rho1)")
            << " dgdt_generation=" << i4fDgdtGeneration
            << " alpha_relax_active=" << i4fPhysicalAlphaFluxRelaxActive
            << " alpha_relax_omega=" << i4fPhysicalAlphaFluxRelaxOmega
            << " source_assembly_alpha_min=" << i4fAlphaBudgetAlphaSourceMin
            << " source_assembly_alpha_max=" << i4fAlphaBudgetAlphaSourceMax
            << " source_assembly_gamma_min_s-1=" << i4fAlphaBudgetGammaMin
            << " source_assembly_gamma_max_s-1=" << i4fAlphaBudgetGammaMax
            << " source_assembly_Su_min_s-1=" << i4fAlphaBudgetSuMin
            << " source_assembly_Su_max_s-1=" << i4fAlphaBudgetSuMax
            << " source_assembly_Sp_min_s-1=" << i4fAlphaBudgetSpMin
            << " source_assembly_Sp_max_s-1=" << i4fAlphaBudgetSpMax
            << " candidate_Ralpha_signed_m3_s="
            << i4fAlphaBudgetCandidateSignedV
            << " candidate_Ralpha_L1_m3_s=" << i4fAlphaBudgetCandidateL1V
            << " candidate_Ralpha_max_s-1=" << i4fAlphaBudgetCandidateMax
            << " applied_Ralpha_signed_m3_s="
            << i4fAlphaBudgetAppliedSignedV
            << " applied_Ralpha_L1_m3_s=" << i4fAlphaBudgetAppliedL1V
            << " applied_Ralpha_max_s-1=" << i4fAlphaBudgetAppliedMax
            << " applied_gamma_assembly_signed_m3_s="
            << i4fAlphaBudgetGammaAssemblyAppliedSignedV
            << " applied_gamma_actual_signed_m3_s="
            << i4fAlphaBudgetGammaAppliedSignedV
            << " applied_cutoff_at_assembly_signed_m3_s="
            << i4fAlphaBudgetGammaCutAppliedSignedV
            << " applied_cutoff_at_assembly_L1_m3_s="
            << i4fAlphaBudgetGammaCutAppliedL1V
            << " applied_source_state_delta_signed_m3_s="
            << i4fAlphaBudgetGammaStateAppliedSignedV
            << " applied_source_state_delta_L1_m3_s="
            << i4fAlphaBudgetGammaStateAppliedL1V
            << " applied_divU_source_signed_m3_s="
            << i4fAlphaBudgetDivUAppliedSignedV
            << " source_split_identity_error_max_s-1="
            << i4fAlphaBudgetSplitErrorMax
            << " source_denominator_floor_cells="
            << i4fAlphaBudgetSourceDenominatorFloorCells
            << " source_effective=Su+Sp*alpha+divU_mode_specific"
            << " residual=ddtEuler_alpha+div(alphaPhi)-source"
            << nl;
    }
}
