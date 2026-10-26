{
    word alphaScheme("div(phi,alpha)");
    word alpharScheme("div(phirb,alpha)");

    // Set the off-centering coefficient according to ddt scheme
    scalar ocCoeff = 0;
    {
        tmp<fv::ddtScheme<scalar>> tddtAlpha
        (
            fv::ddtScheme<scalar>::New
            (
                mesh,
                mesh.ddtScheme("ddt(alpha)")
            )
        );
        const fv::ddtScheme<scalar>& ddtAlpha = tddtAlpha();

        if
        (
            isType<fv::EulerDdtScheme<scalar>>(ddtAlpha)
         || isType<fv::localEulerDdtScheme<scalar>>(ddtAlpha)
        )
        {
            ocCoeff = 0;
        }
        else if (isType<fv::CrankNicolsonDdtScheme<scalar>>(ddtAlpha))
        {
            if (nAlphaSubCycles > 1)
            {
                FatalErrorInFunction
                    << "Sub-cycling is not supported "
                       "with the CrankNicolson ddt scheme"
                    << exit(FatalError);
            }

            if
            (
                alphaRestart
             || mesh.time().timeIndex() > mesh.time().startTimeIndex() + 1
            )
            {
                ocCoeff =
                    refCast<const fv::CrankNicolsonDdtScheme<scalar>>(ddtAlpha)
                   .ocCoeff();
            }
        }
        else
        {
            FatalErrorInFunction
                << "Only Euler and CrankNicolson ddt schemes are supported"
                << exit(FatalError);
        }
    }

    // Set the time blending factor, 1 for Euler
    scalar cnCoeff = 1.0/(1.0 + ocCoeff);

    if (i4fFrozenPredictorFullSource)
    {
        tmp<fv::ddtScheme<scalar>> tFullSourceAlphaDdt
        (
            fv::ddtScheme<scalar>::New
            (
                mesh,
                mesh.ddtScheme("ddt(alpha)")
            )
        );
        const bool i4fStaticEulerDdt =
            isType<fv::EulerDdtScheme<scalar>>(tFullSourceAlphaDdt());

        if (!i4fFrozenPredictorSp)
        {
            FatalErrorInFunction
                << "i4fFrozenPredictorFullSource requires "
                   "i4fFrozenPredictorSp=true"
                << exit(FatalError);
        }

        if
        (
            LTS
         || !i4fStaticEulerDdt
         || nAlphaSubCycles != 1
         || nAlphaCorr != 1
         || !MULESCorr
         || alphaApplyPrevCorr
        )
        {
            FatalErrorInFunction
                << "i4fFrozenPredictorFullSource only supports static "
                   "Euler, MULESCorr=true, nAlphaCorr=1, "
                   "nAlphaSubCycles=1 and alphaApplyPrevCorr=false; got "
                << "LTS=" << LTS
                << " Euler=" << i4fStaticEulerDdt
                << " MULESCorr=" << MULESCorr
                << " nAlphaCorr=" << nAlphaCorr
                << " nAlphaSubCycles=" << nAlphaSubCycles
                << " alphaApplyPrevCorr=" << alphaApplyPrevCorr
                << exit(FatalError);
        }
    }

    // Read-only snapshots of the predictor source. These are local internal
    // fields (not registered or written) and are refreshed every PIMPLE outer
    // iteration immediately before the implicit alpha predictor.
    volScalarField::Internal i4fSpPredictor
    (
        IOobject
        (
            "i4fSpPredictor",
            runTime.timeName(),
            mesh,
            IOobject::NO_READ,
            IOobject::NO_WRITE,
            false
        ),
        mesh,
        dimensionedScalar(dgdt.dimensions(), Zero)
    );
    volScalarField::Internal i4fSuPredictor
    (
        IOobject
        (
            "i4fSuPredictor",
            runTime.timeName(),
            mesh,
            IOobject::NO_READ,
            IOobject::NO_WRITE,
            false
        ),
        mesh,
        dimensionedScalar(dgdt.dimensions(), Zero)
    );
    volScalarField::Internal i4fDivUPredictor
    (
        IOobject
        (
            "i4fDivUPredictor",
            runTime.timeName(),
            mesh,
            IOobject::NO_READ,
            IOobject::NO_WRITE,
            false
        ),
        mesh,
        dimensionedScalar(dgdt.dimensions(), Zero)
    );
    volScalarField::Internal i4fDgdtPredictor
    (
        IOobject
        (
            "i4fDgdtPredictor",
            runTime.timeName(),
            mesh,
            IOobject::NO_READ,
            IOobject::NO_WRITE,
            false
        ),
        mesh,
        dimensionedScalar(dgdt.dimensions(), Zero)
    );
    scalarField i4fAlphaBeforePredictor(alpha1.primitiveField());
    scalarField i4fAlphaPredictor(alpha1.primitiveField());

    // Standard face-flux compression coefficient
    surfaceScalarField phic(mixture.cAlpha()*mag(phi/mesh.magSf()));

    // Add the optional isotropic compression contribution
    if (icAlpha > 0)
    {
        phic *= (1.0 - icAlpha);
        phic += (mixture.cAlpha()*icAlpha)*fvc::interpolate(mag(U));
    }

    // Add the optional shear compression contribution
    if (scAlpha > 0)
    {
        phic +=
            scAlpha*mag(mesh.delta() & fvc::interpolate(symm(fvc::grad(U))));
    }


    surfaceScalarField::Boundary& phicBf =
        phic.boundaryFieldRef();

    // Do not compress interface at non-coupled boundary faces
    // (inlets, outlets etc.)
    forAll(phic.boundaryField(), patchi)
    {
        fvsPatchScalarField& phicp = phicBf[patchi];

        if (!phicp.coupled())
        {
            phicp == 0;
        }
    }

    tmp<surfaceScalarField> phiCN(phi);

    // Calculate the Crank-Nicolson off-centred volumetric flux
    if (ocCoeff > 0)
    {
        phiCN = cnCoeff*phi + (1.0 - cnCoeff)*phi.oldTime();
    }

    if (MULESCorr)
    {
        #include "alphaSuSp.H"

        i4fSpPredictor = Sp;
        i4fSuPredictor = Su;
        i4fDivUPredictor = divU;
        i4fDgdtPredictor = dgdt.internalField();
        i4fAlphaBeforePredictor = alpha1.primitiveField();

        fvScalarMatrix alpha1Eqn
        (
            (
                LTS
              ? fv::localEulerDdtScheme<scalar>(mesh).fvmDdt(alpha1)
              : fv::EulerDdtScheme<scalar>(mesh).fvmDdt(alpha1)
            )
          + fv::gaussConvectionScheme<scalar>
            (
                mesh,
                phiCN,
                upwind<scalar>(mesh, phiCN)
            ).fvmDiv(phiCN, alpha1)
       // - fvm::Sp(fvc::ddt(dimensionedScalar("1", dimless, 1), mesh)
       //           + fvc::div(phiCN), alpha1)
         ==
            Su + fvm::Sp(Sp + divU, alpha1)
        );

        alpha1Eqn.solve();

        Info<< "Phase-1 volume fraction = "
            << alpha1.weightedAverage(mesh.Vsc()).value()
            << "  Min(" << alpha1.name() << ") = " << min(alpha1).value()
            << "  Max(" << alpha1.name() << ") = " << max(alpha1).value()
            << endl;

        tmp<surfaceScalarField> talphaPhi1UD(alpha1Eqn.flux());
        alphaPhi10 = talphaPhi1UD();

        if (alphaApplyPrevCorr && talphaPhi1Corr0.valid())
        {
            Info<< "Applying the previous iteration compression flux" << endl;
            MULES::correct
            (
                geometricOneField(),
                alpha1,
                alphaPhi10,
                talphaPhi1Corr0.ref(),
                oneField(),
                zeroField()
            );

            alphaPhi10 += talphaPhi1Corr0();
        }

        i4fAlphaPredictor = alpha1.primitiveField();

        // Cache the upwind-flux
        talphaPhi1Corr0 = talphaPhi1UD;

        alpha2 = 1.0 - alpha1;

        mixture.correct();
    }


    for (int aCorr=0; aCorr<nAlphaCorr; aCorr++)
    {
        #include "alphaSuSp.H"

        surfaceScalarField phir(phic*mixture.nHatf());

        alphaPhiUn =
            fvc::flux
            (
                phi,
                alpha1,
                alphaScheme
            )
          + fvc::flux
            (
               -fvc::flux(-phir, alpha2, alpharScheme),
                alpha1,
                alpharScheme
            );

        if (MULESCorr)
        {
            tmp<surfaceScalarField> talphaPhi1Corr(alphaPhiUn - alphaPhi10);
            volScalarField alpha10("alpha10", alpha1);

            const scalar alphaPredMin = min(alpha1).value();
            const scalar alphaPredMax = max(alpha1).value();
            if (i4fFrozenPredictorFullSource)
            {
                volScalarField::Internal i4fFullSourceCoefficient
                (
                    IOobject
                    (
                        "i4fFullSourceCoefficient",
                        runTime.timeName(),
                        mesh,
                        IOobject::NO_READ,
                        IOobject::NO_WRITE,
                        false
                    ),
                    mesh,
                    dimensionedScalar(i4fSpPredictor.dimensions(), Zero)
                );
                i4fFullSourceCoefficient =
                    i4fSpPredictor + i4fDivUPredictor;

                const scalar rDeltaT = 1.0/runTime.deltaTValue();
                scalar minFullSourceMargin = GREAT;
                forAll(i4fFullSourceCoefficient, celli)
                {
                    minFullSourceMargin = min
                    (
                        minFullSourceMargin,
                        rDeltaT - i4fFullSourceCoefficient[celli]
                    );
                }
                reduce(minFullSourceMargin, minOp<scalar>());

                if (!(minFullSourceMargin > 0))
                {
                    FatalErrorInFunction
                        << "Unsafe full predictor source for bounded MULES: "
                           "global min(rDeltaT - C)="
                        << minFullSourceMargin << " s^-1; no coefficient "
                           "clipping or alpha correction was applied"
                        << exit(FatalError);
                }

                MULES::correct
                (
                    geometricOneField(),
                    alpha1,
                    alphaPhiUn,
                    talphaPhi1Corr.ref(),
                    i4fFullSourceCoefficient,
                    (-i4fFullSourceCoefficient*alpha1)(),
                    oneField(),
                    zeroField()
                );

                surfaceScalarField i4fFullCorrectedAlphaFlux
                (
                    "i4fFullCorrectedAlphaFlux",
                    alphaPhi10 + talphaPhi1Corr()
                );
                tmp<volScalarField> ti4fFullCorrectedAlphaFluxDiv
                (
                    fvc::div(i4fFullCorrectedAlphaFlux)
                );
                const volScalarField& i4fFullCorrectedAlphaFluxDiv =
                    ti4fFullCorrectedAlphaFluxDiv();

                scalar fullResidualMax = 0;
                scalar fullResidualL1Volume = 0;
                scalar fullResidualSignedVolume = 0;
                scalar spOnlyLagMax = 0;
                scalar spOnlyLagL1Volume = 0;
                scalar spOnlyLagSignedVolume = 0;
                forAll(i4fFullSourceCoefficient, celli)
                {
                    const scalar alphaFinal = alpha1[celli];
                    const scalar alphaStorage =
                        (alphaFinal - alpha1.oldTime()[celli])
                       /runTime.deltaTValue();
                    const scalar fullSource =
                        i4fSuPredictor[celli]
                      + i4fFullSourceCoefficient[celli]*alphaFinal;
                    const scalar fullResidual =
                        alphaStorage
                      + i4fFullCorrectedAlphaFluxDiv[celli]
                      - fullSource;
                    const scalar spOnlyLag =
                        i4fDivUPredictor[celli]
                       *(i4fAlphaPredictor[celli] - alphaFinal);
                    const scalar cellVolume = mesh.V()[celli];

                    fullResidualMax = max
                    (
                        fullResidualMax,
                        mag(fullResidual)
                    );
                    fullResidualL1Volume += cellVolume*mag(fullResidual);
                    fullResidualSignedVolume += cellVolume*fullResidual;
                    spOnlyLagMax = max(spOnlyLagMax, mag(spOnlyLag));
                    spOnlyLagL1Volume += cellVolume*mag(spOnlyLag);
                    spOnlyLagSignedVolume += cellVolume*spOnlyLag;
                }
                reduce(fullResidualMax, maxOp<scalar>());
                reduce(fullResidualL1Volume, sumOp<scalar>());
                reduce(fullResidualSignedVolume, sumOp<scalar>());
                reduce(spOnlyLagMax, maxOp<scalar>());
                reduce(spOnlyLagL1Volume, sumOp<scalar>());
                reduce(spOnlyLagSignedVolume, sumOp<scalar>());

                Info<< "I4F_FULL_PREDICTOR_SOURCE_SUMMARY"
                    << " time_s=" << runTime.timeName()
                    << " outer_iteration=" << i4fOuterLoop
                    << " alpha_corrector=" << aCorr + 1
                    << " min_rDeltaT_minus_C_s-1="
                    << minFullSourceMargin
                    << " full_R_max_s-1=" << fullResidualMax
                    << " full_R_volume_L1_m3_s=" << fullResidualL1Volume
                    << " full_R_signed_volume_integral_m3_s="
                    << fullResidualSignedVolume
                    << " predicted_Sp_only_lag_max_s-1=" << spOnlyLagMax
                    << " predicted_Sp_only_lag_volume_L1_m3_s="
                    << spOnlyLagL1Volume
                    << " predicted_Sp_only_lag_signed_volume_integral_m3_s="
                    << spOnlyLagSignedVolume
                    << " alpha_residual_claim=discrete_local_equation_only"
                    << nl;

                const label i4fTargetCells[] = {2684, 2752};
                if (Pstream::myProcNo() == 2)
                {
                    for (const label i4fCell : i4fTargetCells)
                    {
                        const scalar alphaFinal = alpha1[i4fCell];
                        const scalar alphaStorage =
                            (alphaFinal - alpha1.oldTime()[i4fCell])
                           /runTime.deltaTValue();
                        const scalar fullResidual =
                            alphaStorage
                          + i4fFullCorrectedAlphaFluxDiv[i4fCell]
                          - i4fSuPredictor[i4fCell]
                          - i4fFullSourceCoefficient[i4fCell]*alphaFinal;
                        Pout<< "I4F_FULL_PREDICTOR_SOURCE_CELL"
                            << " time_s=" << runTime.timeName()
                            << " outer_iteration=" << i4fOuterLoop
                            << " alpha_corrector=" << aCorr + 1
                            << " rank=" << Pstream::myProcNo()
                            << " local_cell=" << i4fCell
                            << " predictor_Sp_s-1="
                            << i4fSpPredictor[i4fCell]
                            << " predictor_divU_s-1="
                            << i4fDivUPredictor[i4fCell]
                            << " full_C_s-1="
                            << i4fFullSourceCoefficient[i4fCell]
                            << " alphaP=" << i4fAlphaPredictor[i4fCell]
                            << " alphaF=" << alphaFinal
                            << " full_R_s-1=" << fullResidual
                            << " predicted_Sp_only_lag_s-1="
                            << i4fDivUPredictor[i4fCell]
                               *(i4fAlphaPredictor[i4fCell] - alphaFinal)
                            << " continuity_claim=none"
                            << nl;
                    }
                }
            }
            else if (i4fFrozenPredictorSp)
            {
                MULES::correct
                (
                    geometricOneField(),
                    alpha1,
                    alphaPhiUn,
                    talphaPhi1Corr.ref(),
                    i4fSpPredictor,
                    (-i4fSpPredictor*alpha1)(),
                    oneField(),
                    zeroField()
                );
            }
            else
            {
                MULES::correct
                (
                    geometricOneField(),
                    alpha1,
                    alphaPhiUn,
                    talphaPhi1Corr.ref(),
                    Sp,
                    (-Sp*alpha1)(),
                    oneField(),
                    zeroField()
                );
            }

            // Under-relax the correction for all but the 1st corrector
            if (aCorr == 0)
            {
                alphaPhi10 += talphaPhi1Corr();
            }
            else
            {
                alpha1 = 0.5*alpha1 + 0.5*alpha10;
                alphaPhi10 += 0.5*talphaPhi1Corr();
            }

            if (i4fFrozenPredictorSp)
            {
                // The corrected alpha flux is the actual face flux from the
                // MULES update. Keep this identity diagnostic distinct from
                // a mass-conservation claim: it exposes the lagged divU term.
                tmp<volScalarField> tI4fAlphaFluxDiv(fvc::div(alphaPhi10));
                const volScalarField& i4fAlphaFluxDiv = tI4fAlphaFluxDiv();

                scalar correctionDiagMin = GREAT;
                const scalar rDeltaT = 1.0/runTime.deltaTValue();
                forAll(i4fSpPredictor, celli)
                {
                    correctionDiagMin = min
                    (
                        correctionDiagMin,
                        rDeltaT - i4fSpPredictor[celli]
                    );
                }
                reduce(correctionDiagMin, minOp<scalar>());

                const scalar alphaFinalMin = min(alpha1).value();
                const scalar alphaFinalMax = max(alpha1).value();
                const label i4fTargetCells[] = {2684, 2752};
                if (Pstream::myProcNo() == 2)
                {
                    for (const label i4fCell : i4fTargetCells)
                    {
                        const scalar alphaBefore =
                            i4fAlphaBeforePredictor[i4fCell];
                        const scalar alphaPred = i4fAlphaPredictor[i4fCell];
                        const scalar alphaFinal = alpha1[i4fCell];
                        const scalar dgdtPred = i4fDgdtPredictor[i4fCell];
                        const scalar dgdtCorr = dgdt[i4fCell];
                        const bool predictorFloorActive =
                            dgdtPred > 0
                          ? (1.0 - alphaBefore < 1e-4)
                          : (dgdtPred < 0 && alphaBefore < 1e-4);
                        const bool correctionFloorActive =
                            dgdtCorr > 0
                          ? (1.0 - alphaPred < 1e-4)
                          : (dgdtCorr < 0 && alphaPred < 1e-4);
                        const scalar frozenSource =
                            i4fSuPredictor[i4fCell]
                          + i4fSpPredictor[i4fCell]*alphaFinal
                          + i4fDivUPredictor[i4fCell]*alphaPred;
                        const scalar divULagResidual =
                            -i4fDivUPredictor[i4fCell]
                            *(alphaFinal - alphaPred);
                        const scalar alphaStorage =
                            (alphaFinal - alpha1.oldTime()[i4fCell])
                           /runTime.deltaTValue();
                        const scalar alphaFluxDivergence =
                            i4fAlphaFluxDiv[i4fCell];
                        const scalar localAlphaResidual =
                            alphaStorage + alphaFluxDivergence - frozenSource;

                        Pout<< "I4F_FROZEN_ALPHA_SOURCE"
                            << " time_s=" << runTime.timeName()
                            << " outer_iteration=" << i4fOuterLoop
                            << " alpha_corrector=" << aCorr + 1
                            << " rank=" << Pstream::myProcNo()
                            << " local_cell=" << i4fCell
                            << " frozen_predictor_Sp="
                            << i4fSpPredictor[i4fCell]
                            << " recomputed_corrector_Sp=" << Sp[i4fCell]
                            << " predictor_Su=" << i4fSuPredictor[i4fCell]
                            << " predictor_divU="
                            << i4fDivUPredictor[i4fCell]
                            << " corrector_divU=" << divU[i4fCell]
                            << " predictor_dgdt="
                            << i4fDgdtPredictor[i4fCell]
                            << " corrector_dgdt=" << dgdtCorr
                            << " alpha_before_predictor=" << alphaBefore
                            << " alpha_pred_before_MULES_correct=" << alphaPred
                            << " alpha_final_after_MULES_correct=" << alphaFinal
                            << " predictor_denominator_floor_active="
                            << predictorFloorActive
                            << " corrector_denominator_floor_active="
                            << correctionFloorActive
                            << " alpha_pred_bounds_before_MULES_correct=["
                            << alphaPredMin << "," << alphaPredMax << "]"
                            << " alpha_final_bounds_after_MULES_correct=["
                            << alphaFinalMin << "," << alphaFinalMax << "]"
                            << " correction_diag_min_s-1="
                            << correctionDiagMin
                            << " used_frozen_predictor_Sp="
                            << i4fFrozenPredictorSp
                            << " predictor_source_combination_per_s="
                            << frozenSource
                            << " lagged_divU_residual_per_s="
                            << divULagResidual
                            << " alpha_storage_rate_per_s=" << alphaStorage
                            << " native_alphaPhi0_divergence_per_s="
                            << alphaFluxDivergence
                            << " local_alpha_flux_residual_per_s="
                            << localAlphaResidual
                            << " continuity_claim=none_local_discrete_diagnostic"
                            << nl;
                    }
                }
            }
        }
        else
        {
            alphaPhi10 = alphaPhiUn;

            MULES::explicitSolve
            (
                geometricOneField(),
                alpha1,
                phiCN,
                alphaPhi10,
                Sp,
                (Su + divU*min(alpha1(), scalar(1)))(),
                oneField(),
                zeroField()
            );
        }

        alpha2 = 1.0 - alpha1;

        mixture.correct();
    }

    if (alphaApplyPrevCorr && MULESCorr)
    {
        talphaPhi1Corr0 = alphaPhi10 - talphaPhi1Corr0;
        talphaPhi1Corr0.ref().rename("alphaPhi1Corr0");
    }
    else
    {
        talphaPhi1Corr0.clear();
    }

    #include "rhofs.H"

    if
    (
        word(mesh.ddtScheme("ddt(rho,U)"))
     == fv::EulerDdtScheme<vector>::typeName
     || word(mesh.ddtScheme("ddt(rho,U)"))
     == fv::localEulerDdtScheme<vector>::typeName
    )
    {
        rhoPhi = alphaPhi10*(rho1f - rho2f) + phiCN*rho2f;
    }
    else
    {
        if (ocCoeff > 0)
        {
            // Calculate the end-of-time-step alpha flux
            alphaPhi10 =
                (alphaPhi10 - (1.0 - cnCoeff)*alphaPhi10.oldTime())/cnCoeff;
        }

        // Calculate the end-of-time-step mass flux
        rhoPhi = alphaPhi10*(rho1f - rho2f) + phi*rho2f;
    }

    Info<< "Phase-1 volume fraction = "
        << alpha1.weightedAverage(mesh.Vsc()).value()
        << "  Min(" << alpha1.name() << ") = " << min(alpha1).value()
        << "  Max(" << alpha1.name() << ") = " << max(alpha1).value()
        << endl;
}
