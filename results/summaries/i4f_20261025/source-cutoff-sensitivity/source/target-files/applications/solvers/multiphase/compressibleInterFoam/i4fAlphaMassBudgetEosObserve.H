// Read-only post-EOS identity. The alpha source snapshot was captured in the
// alpha solve at the same physical time/outer iteration and is intentionally
// not recomputed from the later dgdt field.
if
(
    i4fAlphaMassBudgetAudit
 && i4fAlphaMassBudgetSourceValid
 && i4fAlphaMassBudgetTimeIndex == runTime.timeIndex()
)
{
    tmp<volScalarField> tI4fBudgetDivAlpha(fvc::div(alphaPhi1));
    tmp<volScalarField> tI4fBudgetDivWaterFlux
    (
        fvc::div(i4fWaterAdvMassFluxAfterEos)
    );
    const volScalarField& i4fBudgetDivAlpha = tI4fBudgetDivAlpha();
    const volScalarField& i4fBudgetDivWaterFlux = tI4fBudgetDivWaterFlux();
    const scalarField& i4fBudgetAlphaOld = alpha1.oldTime().primitiveField();
    const scalarField& i4fBudgetRhoOld = rho1.oldTime().primitiveField();

    scalar i4fBudgetRalphaSignedV = 0;
    scalar i4fBudgetRalphaL1V = 0;
    scalar i4fBudgetRalphaMax = 0;
    scalar i4fBudgetRmassSignedV = 0;
    scalar i4fBudgetRmassL1V = 0;
    scalar i4fBudgetRmassMax = 0;
    scalar i4fBudgetRhoRalphaSigned = 0;
    scalar i4fBudgetRhoRalphaL1 = 0;
    scalar i4fBudgetRhoSourceSigned = 0;
    scalar i4fBudgetRhoSourceL1 = 0;
    scalar i4fBudgetAlphaOldDrhoSigned = 0;
    scalar i4fBudgetAlphaOldDrhoL1 = 0;
    scalar i4fBudgetFaceDensitySigned = 0;
    scalar i4fBudgetFaceDensityL1 = 0;
    scalar i4fBudgetGammaAssemblyMassSigned = 0;
    scalar i4fBudgetGammaActualMassSigned = 0;
    scalar i4fBudgetCutoffAtAssemblyMassSigned = 0;
    scalar i4fBudgetCutoffAtAssemblyMassL1 = 0;
    scalar i4fBudgetSourceStateMassSigned = 0;
    scalar i4fBudgetSourceStateMassL1 = 0;
    scalar i4fBudgetGammaMassSigned = 0;
    scalar i4fBudgetSourceSplitErrorSigned = 0;
    scalar i4fBudgetSourceSplitErrorL1 = 0;
    scalar i4fBudgetSourceSplitErrorMax = 0;
    scalar i4fBudgetDivUMassSigned = 0;
    scalar i4fBudgetIdentityErrorSigned = 0;
    scalar i4fBudgetIdentityErrorL1 = 0;
    scalar i4fBudgetIdentityErrorMax = 0;
    scalar i4fBudgetDivWaterFluxIntegral = 0;
    label i4fBudgetSourceDenominatorFloorCells = 0;

    forAll(alpha1, celli)
    {
        const scalar alpha = alpha1[celli];
        const scalar alphaOld = i4fBudgetAlphaOld[celli];
        const scalar rho = rho1[celli];
        const scalar rhoOld = i4fBudgetRhoOld[celli];
        const scalar su = i4fAlphaMassBudgetSu[celli];
        const scalar sp = i4fAlphaMassBudgetSp[celli];
        const scalar gamma = i4fAlphaMassBudgetGamma[celli];
        const scalar alphaSource = i4fAlphaMassBudgetAlphaSource[celli];
        // Finite algebraic partition only; not a counterfactual uncut source.
        const scalar sourceGammaAssembly = su + sp*alphaSource;
        const scalar sourceGammaActual = su + sp*alpha;
        const scalar sourceCutoffAtAssembly = sourceGammaAssembly - gamma;
        const scalar sourceStateDelta = sp*(alpha - alphaSource);
        const scalar sourceSplitError =
            sourceGammaActual
          - (gamma + sourceCutoffAtAssembly + sourceStateDelta);
        const scalar sourceDivU =
            i4fAlphaMassBudgetDivU[celli]
           *i4fAlphaMassBudgetDivUEvalAlpha[celli];
        const scalar sourceActual = sourceGammaActual + sourceDivU;
        const scalar alphaStorage =
            (alpha - alphaOld)/runTime.deltaTValue();
        const scalar rAlpha =
            alphaStorage + i4fBudgetDivAlpha[celli] - sourceActual;
        const scalar rMass = i4fWaterContinuityAfterEos[celli];
        const scalar divWaterFlux = i4fBudgetDivWaterFlux[celli];

        const scalar termRhoRalpha = rho*rAlpha;
        const scalar termRhoSource = rho*sourceActual;
        const scalar termOldAlphaDrho =
            alphaOld*(rho - rhoOld)/runTime.deltaTValue();
        const scalar termFaceDensity =
            divWaterFlux - rho*i4fBudgetDivAlpha[celli];
        const scalar reconstructedMassResidual =
            termRhoRalpha
          + termRhoSource
          + termOldAlphaDrho
          + termFaceDensity;
        const scalar identityError = rMass - reconstructedMassResidual;
        const scalar volume = mesh.V()[celli];

        if
        (
            (gamma > 0 && 1.0 - alphaSource < i4fAlphaSourceDenominatorFloor)
         || (gamma < 0 && alphaSource < i4fAlphaSourceDenominatorFloor)
        )
        {
            ++i4fBudgetSourceDenominatorFloorCells;
        }

        i4fBudgetRalphaSignedV += rAlpha*volume;
        i4fBudgetRalphaL1V += mag(rAlpha)*volume;
        i4fBudgetRalphaMax = max(i4fBudgetRalphaMax, mag(rAlpha));
        i4fBudgetRmassSignedV += rMass*volume;
        i4fBudgetRmassL1V += mag(rMass)*volume;
        i4fBudgetRmassMax = max(i4fBudgetRmassMax, mag(rMass));
        i4fBudgetRhoRalphaSigned += termRhoRalpha*volume;
        i4fBudgetRhoRalphaL1 += mag(termRhoRalpha)*volume;
        i4fBudgetRhoSourceSigned += termRhoSource*volume;
        i4fBudgetRhoSourceL1 += mag(termRhoSource)*volume;
        i4fBudgetAlphaOldDrhoSigned += termOldAlphaDrho*volume;
        i4fBudgetAlphaOldDrhoL1 += mag(termOldAlphaDrho)*volume;
        i4fBudgetFaceDensitySigned += termFaceDensity*volume;
        i4fBudgetFaceDensityL1 += mag(termFaceDensity)*volume;
        i4fBudgetGammaAssemblyMassSigned += rho*sourceGammaAssembly*volume;
        i4fBudgetGammaActualMassSigned += rho*sourceGammaActual*volume;
        i4fBudgetGammaMassSigned += rho*gamma*volume;
        i4fBudgetCutoffAtAssemblyMassSigned +=
            rho*sourceCutoffAtAssembly*volume;
        i4fBudgetCutoffAtAssemblyMassL1 +=
            mag(rho*sourceCutoffAtAssembly)*volume;
        i4fBudgetDivUMassSigned += rho*sourceDivU*volume;
        i4fBudgetSourceStateMassSigned += rho*sourceStateDelta*volume;
        i4fBudgetSourceStateMassL1 += mag(rho*sourceStateDelta)*volume;
        i4fBudgetSourceSplitErrorSigned += rho*sourceSplitError*volume;
        i4fBudgetSourceSplitErrorL1 += mag(rho*sourceSplitError)*volume;
        i4fBudgetSourceSplitErrorMax = max
        (
            i4fBudgetSourceSplitErrorMax,
            mag(rho*sourceSplitError)
        );
        i4fBudgetIdentityErrorSigned += identityError*volume;
        i4fBudgetIdentityErrorL1 += mag(identityError)*volume;
        i4fBudgetIdentityErrorMax = max
        (
            i4fBudgetIdentityErrorMax,
            mag(identityError)
        );
        i4fBudgetDivWaterFluxIntegral += divWaterFlux*volume;
    }

    reduce(i4fBudgetRalphaSignedV, sumOp<scalar>());
    reduce(i4fBudgetRalphaL1V, sumOp<scalar>());
    reduce(i4fBudgetRalphaMax, maxOp<scalar>());
    reduce(i4fBudgetRmassSignedV, sumOp<scalar>());
    reduce(i4fBudgetRmassL1V, sumOp<scalar>());
    reduce(i4fBudgetRmassMax, maxOp<scalar>());
    reduce(i4fBudgetRhoRalphaSigned, sumOp<scalar>());
    reduce(i4fBudgetRhoRalphaL1, sumOp<scalar>());
    reduce(i4fBudgetRhoSourceSigned, sumOp<scalar>());
    reduce(i4fBudgetRhoSourceL1, sumOp<scalar>());
    reduce(i4fBudgetAlphaOldDrhoSigned, sumOp<scalar>());
    reduce(i4fBudgetAlphaOldDrhoL1, sumOp<scalar>());
    reduce(i4fBudgetFaceDensitySigned, sumOp<scalar>());
    reduce(i4fBudgetFaceDensityL1, sumOp<scalar>());
    reduce(i4fBudgetGammaAssemblyMassSigned, sumOp<scalar>());
    reduce(i4fBudgetGammaActualMassSigned, sumOp<scalar>());
    reduce(i4fBudgetCutoffAtAssemblyMassSigned, sumOp<scalar>());
    reduce(i4fBudgetCutoffAtAssemblyMassL1, sumOp<scalar>());
    reduce(i4fBudgetSourceStateMassSigned, sumOp<scalar>());
    reduce(i4fBudgetSourceStateMassL1, sumOp<scalar>());
    reduce(i4fBudgetGammaMassSigned, sumOp<scalar>());
    reduce(i4fBudgetDivUMassSigned, sumOp<scalar>());
    reduce(i4fBudgetSourceSplitErrorSigned, sumOp<scalar>());
    reduce(i4fBudgetSourceSplitErrorL1, sumOp<scalar>());
    reduce(i4fBudgetSourceSplitErrorMax, maxOp<scalar>());
    reduce(i4fBudgetIdentityErrorSigned, sumOp<scalar>());
    reduce(i4fBudgetIdentityErrorL1, sumOp<scalar>());
    reduce(i4fBudgetIdentityErrorMax, maxOp<scalar>());
    reduce(i4fBudgetDivWaterFluxIntegral, sumOp<scalar>());
    reduce(i4fBudgetSourceDenominatorFloorCells, sumOp<label>());

    if (Pstream::master())
    {
        Info<< "I4F_ALPHA_MASS_BUDGET_EOS_V3"
            << " time_s=" << runTime.timeName()
            << " time_index=" << i4fAlphaMassBudgetTimeIndex
            << " source_outer_iteration=" << i4fAlphaMassBudgetOuterIteration
            << " source_call_index=" << i4fAlphaMassBudgetSourceCallIndex
            << " source_dgdt_generation=" << i4fAlphaMassBudgetDgdtGeneration
            << " pressure_pass=" << i4fPressurePass
            << " source_mode=" << i4fAlphaMassBudgetSourceMode
            << " Ralpha_signed_m3_s=" << i4fBudgetRalphaSignedV
            << " Ralpha_L1_m3_s=" << i4fBudgetRalphaL1V
            << " Ralpha_max_s-1=" << i4fBudgetRalphaMax
            << " Rmass_signed_kg_s=" << i4fBudgetRmassSignedV
            << " Rmass_L1_kg_s=" << i4fBudgetRmassL1V
            << " Rmass_max_kg_m3_s=" << i4fBudgetRmassMax
            << " rho_Ralpha_signed_kg_s=" << i4fBudgetRhoRalphaSigned
            << " rho_Ralpha_L1_kg_s=" << i4fBudgetRhoRalphaL1
            << " rho_source_signed_kg_s=" << i4fBudgetRhoSourceSigned
            << " rho_source_L1_kg_s=" << i4fBudgetRhoSourceL1
            << " alphaOld_drho_signed_kg_s=" << i4fBudgetAlphaOldDrhoSigned
            << " alphaOld_drho_L1_kg_s=" << i4fBudgetAlphaOldDrhoL1
            << " face_density_noncommutation_signed_kg_s="
            << i4fBudgetFaceDensitySigned
            << " face_density_noncommutation_L1_kg_s="
            << i4fBudgetFaceDensityL1
            << " source_gamma_dgdt_signed_kg_s=" << i4fBudgetGammaMassSigned
            << " source_gamma_at_assembly_signed_kg_s="
            << i4fBudgetGammaAssemblyMassSigned
            << " source_gamma_actual_signed_kg_s="
            << i4fBudgetGammaActualMassSigned
            << " source_cutoff_at_assembly_delta_signed_kg_s="
            << i4fBudgetCutoffAtAssemblyMassSigned
            << " source_cutoff_at_assembly_delta_L1_kg_s="
            << i4fBudgetCutoffAtAssemblyMassL1
            << " source_state_delta_signed_kg_s="
            << i4fBudgetSourceStateMassSigned
            << " source_state_delta_L1_kg_s="
            << i4fBudgetSourceStateMassL1
            << " source_split_identity_error_signed_kg_s="
            << i4fBudgetSourceSplitErrorSigned
            << " source_split_identity_error_L1_kg_s="
            << i4fBudgetSourceSplitErrorL1
            << " source_split_identity_error_max_kg_m3_s="
            << i4fBudgetSourceSplitErrorMax
            << " divU_source_signed_kg_s=" << i4fBudgetDivUMassSigned
            << " identity_error_signed_kg_s=" << i4fBudgetIdentityErrorSigned
            << " identity_error_L1_kg_s=" << i4fBudgetIdentityErrorL1
            << " identity_error_max_kg_m3_s=" << i4fBudgetIdentityErrorMax
            << " div_alphaPhi_rhoFace_integral_kg_s="
            << i4fBudgetDivWaterFluxIntegral
            << " boundary_water_flux_kg_s=" << i4fWaterBoundaryAfterEos
            << " divFlux_boundary_difference_kg_s="
            << i4fBudgetDivWaterFluxIntegral - i4fWaterBoundaryAfterEos
            << " source_denominator_floor_cells="
            << i4fBudgetSourceDenominatorFloorCells
            << " continuity_source_terms=none_in_configured_phase_mass_equations"
            << " flux_density=fvc_interpolate(rho1)_after_correctRho"
            << nl;
    }
}
