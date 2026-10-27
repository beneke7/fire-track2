{
    volScalarField rAU("rAU", 1.0/UEqn.A());
    surfaceScalarField rAUf("rAUf", fvc::interpolate(rAU));
    volVectorField HbyA(constrainHbyA(rAU*UEqn.H(), U, p_rgh));
    surfaceScalarField phiHbyA
    (
        "phiHbyA",
        fvc::flux(HbyA)
      + MRF.zeroFilter(fvc::interpolate(rho*rAU)*fvc::ddtCorr(U, phi))
    );
    MRF.makeRelative(phiHbyA);

    surfaceScalarField phig
    (
        (
            mixture.surfaceTensionForce()
          - ghf*fvc::snGrad(rho)
        )*rAUf*mesh.magSf()
    );

    phiHbyA += phig;

    // Update the pressure BCs to ensure flux consistency
    constrainPressure(p_rgh, U, phiHbyA, rAUf, MRF);

    tmp<fvScalarMatrix> p_rghEqnComp1;
    tmp<fvScalarMatrix> p_rghEqnComp2;

    if (pimple.transonic())
    {
        #include "rhofs.H"

        surfaceScalarField phid1("phid1", fvc::interpolate(psi1)*phi);
        surfaceScalarField phid2("phid2", fvc::interpolate(psi2)*phi);

        p_rghEqnComp1 =
            pos(alpha1)
           *(
                (
                    fvc::ddt(alpha1, rho1) + fvc::div(alphaPhi1*rho1f)
                  - (fvOptions(alpha1, mixture.thermo1().rho())&rho1)
                )/rho1
              - fvc::ddt(alpha1) - fvc::div(alphaPhi1)
              + (alpha1/rho1)
               *correction
                (
                    psi1*fvm::ddt(p_rgh)
                  + fvm::div(phid1, p_rgh) - fvm::Sp(fvc::div(phid1), p_rgh)
                )
            );
        p_rghEqnComp1.ref().relax();

        p_rghEqnComp2 =
            pos(alpha2)
           *(
               (
                   fvc::ddt(alpha2, rho2) + fvc::div(alphaPhi2*rho2f)
                 - (fvOptions(alpha2, mixture.thermo2().rho())&rho2)
               )/rho2
             - fvc::ddt(alpha2) - fvc::div(alphaPhi2)
             + (alpha2/rho2)
              *correction
               (
                   psi2*fvm::ddt(p_rgh)
                 + fvm::div(phid2, p_rgh) - fvm::Sp(fvc::div(phid2), p_rgh)
               )
           );
        p_rghEqnComp2.ref().relax();
    }
    else
    {
        #include "rhofs.H"

        p_rghEqnComp1 =
            pos(alpha1)
           *(
                (
                    fvc::ddt(alpha1, rho1) + fvc::div(alphaPhi1*rho1f)
                  - (fvOptions(alpha1, mixture.thermo1().rho())&rho1)
                )/rho1
              - fvc::ddt(alpha1) - fvc::div(alphaPhi1)
              + (alpha1*psi1/rho1)*correction(fvm::ddt(p_rgh))
            );

        p_rghEqnComp2 =
            pos(alpha2)
           *(
               (
                   fvc::ddt(alpha2, rho2) + fvc::div(alphaPhi2*rho2f)
                 - (fvOptions(alpha2, mixture.thermo2().rho())&rho2)
               )/rho2
             - fvc::ddt(alpha2) - fvc::div(alphaPhi2)
             + (alpha2*psi2/rho2)*correction(fvm::ddt(p_rgh))
            );
    }

    // Cache p_rgh prior to solve for density update
    volScalarField p_rgh_0(p_rgh);

    static label i4fPressurePass = 0;
    ++i4fPressurePass;
    const Switch i4fFullPressureAudit = runTime.controlDict().lookupOrDefault<Switch>("i4fFullPressureAudit", true);

    while (pimple.correctNonOrthogonal())
    {
        fvScalarMatrix p_rghEqnIncomp
        (
            fvc::div(phiHbyA)
          - fvm::laplacian(rAUf, p_rgh)
        );

        if (i4fFullPressureAudit)
        {
            // Residual of the freshly assembled, current outer-iteration
            // linearization before its pressure solve. This is not a nonlinear
            // reassembly after the solve or after the EOS density correction.
            tmp<fvScalarMatrix> tI4fPressureBeforeSolve
            (
                p_rghEqnComp1() + p_rghEqnComp2() + p_rghEqnIncomp
            );
            scalarField i4fComp1BeforeSolve(p_rghEqnComp1().residual());
            scalarField i4fComp2BeforeSolve(p_rghEqnComp2().residual());
            scalarField i4fIncompBeforeSolve(p_rghEqnIncomp.residual());
            scalarField i4fFullBeforeSolve
            (
                tI4fPressureBeforeSolve().residual()
            );

            i4fReportPressureResidual
            (
                "assembled_before_solve", "comp1", i4fPressurePass,
                runTime.timeName(), i4fComp1BeforeSolve
            );
            i4fReportPressureResidual
            (
                "assembled_before_solve", "comp2", i4fPressurePass,
                runTime.timeName(), i4fComp2BeforeSolve
            );
            i4fReportPressureResidual
            (
                "assembled_before_solve", "incompressible", i4fPressurePass,
                runTime.timeName(), i4fIncompBeforeSolve
            );
            i4fReportPressureResidual
            (
                "assembled_before_solve", "full_comp1_plus_comp2_plus_incomp",
                i4fPressurePass, runTime.timeName(), i4fFullBeforeSolve
            );
            i4fReportOperatorPressureDefect
            (
                tI4fPressureBeforeSolve(), p_rgh, mesh,
                "assembled_before_solve", "full_comp1_plus_comp2_plus_incomp",
                i4fPressurePass, runTime.timeName()
            );
        }



        solve
        (
            p_rghEqnComp1() + p_rghEqnComp2() + p_rghEqnIncomp,
            p_rgh.select(pimple.finalInnerIter())
        );

        if (pimple.finalNonOrthogonalIter())
        {
            // Read-only diagnostic: inspect absolute pressure immediately before
            // the stock floor and preserve all original equations below.
            static label pressureClampTracePass = 0;
            ++pressureClampTracePass;

            tmp<volScalarField> tPressureClampRaw
            (
                p_rgh + (alpha1*rho1 + alpha2*rho2)*gh
            );
            const volScalarField& pressureClampRaw = tPressureClampRaw();
            const scalar pressureClampFloor = pMin.value();

            scalar pressureClampRawMin = GREAT;
            scalar pressureClampRawMax = -GREAT;
            label pressureClampLocalBelow = 0;
            scalar pressureClampLocalWaterVolumeBelow = 0;
            scalar pressureClampLocalWaterMassBelow = 0;

            forAll(pressureClampRaw, celli)
            {
                const scalar rawP = pressureClampRaw[celli];
                pressureClampRawMin = min(pressureClampRawMin, rawP);
                pressureClampRawMax = max(pressureClampRawMax, rawP);
                if (rawP < pressureClampFloor)
                {
                    ++pressureClampLocalBelow;
                    pressureClampLocalWaterVolumeBelow += alpha1[celli]*mesh.V()[celli];
                    pressureClampLocalWaterMassBelow +=
                        alpha1[celli]*rho1[celli]*mesh.V()[celli];
                }
            }

            scalar pressureClampGlobalMin = pressureClampRawMin;
            scalar pressureClampGlobalMax = pressureClampRawMax;
            label pressureClampGlobalBelow = pressureClampLocalBelow;
            scalar pressureClampGlobalWaterVolumeBelow =
                pressureClampLocalWaterVolumeBelow;
            scalar pressureClampGlobalWaterMassBelow =
                pressureClampLocalWaterMassBelow;
            reduce(pressureClampGlobalMin, minOp<scalar>());
            reduce(pressureClampGlobalMax, maxOp<scalar>());
            reduce(pressureClampGlobalBelow, sumOp<label>());
            reduce(pressureClampGlobalWaterVolumeBelow, sumOp<scalar>());
            reduce(pressureClampGlobalWaterMassBelow, sumOp<scalar>());

            Info<< "CLAMP_TRACE_RAW"
                << " time_s=" << runTime.timeName()
                << " outer=" << i4fOuterLoop
                << " pass=" << pressureClampTracePass
                << " pMin_Pa=" << pressureClampFloor
                << " raw_cell_p_min_Pa=" << pressureClampGlobalMin
                << " raw_cell_p_max_Pa=" << pressureClampGlobalMax
                << " cells_strictly_below_pMin=" << pressureClampGlobalBelow
                << " clipped_water_volume_m3=" << pressureClampGlobalWaterVolumeBelow
                << " clipped_water_mass_kg=" << pressureClampGlobalWaterMassBelow
                << " local_cells_below_pMin=" << pressureClampLocalBelow
                << nl << endl;

            label pressureClampPrintedCells = 0;
            forAll(pressureClampRaw, celli)
            {
                if
                (
                    pressureClampRaw[celli] < pressureClampFloor
                 && pressureClampPrintedCells < 8
                )
                {
                    Pout<< "CLAMP_TRACE_CELL"
                        << " time_s=" << runTime.timeName()
                        << " outer=" << i4fOuterLoop
                        << " pass=" << pressureClampTracePass
                        << " rank=" << Pstream::myProcNo()
                        << " cell=" << celli
                        << " p_raw_Pa=" << pressureClampRaw[celli]
                        << " p_rgh_Pa=" << p_rgh[celli]
                        << " pMin_Pa=" << pressureClampFloor
                        << " C_m=" << mesh.C().primitiveField()[celli]
                        << " nativeV_m3=" << mesh.V()[celli]
                        << " alpha1_water=" << alpha1[celli]
                        << " alpha2_air=" << alpha2[celli]
                        << " T_K=" << T[celli]
                        << " rho_mix_kg_m3=" << rho[celli]
                        << " rho1_kg_m3=" << rho1[celli]
                        << " rho2_kg_m3=" << rho2[celli]
                        << " U_m_s=" << U[celli]
                        << " psi1_PaInv=" << psi1[celli]
                        << " psi2_PaInv=" << psi2[celli]
                        << nl;
                    ++pressureClampPrintedCells;
                }
            }

            if (pressureClampGlobalBelow > 0)
            {
                label pressureClampGlobalPrinted = pressureClampPrintedCells;
                reduce(pressureClampGlobalPrinted, sumOp<label>());

                Info<< "CLAMP_TRACE_CELL_SUMMARY"
                    << " time_s=" << runTime.timeName()
                    << " outer=" << i4fOuterLoop
                    << " pass=" << pressureClampTracePass
                    << " global_below_pMin=" << pressureClampGlobalBelow
                    << " global_printed=" << pressureClampGlobalPrinted
                    << " global_omitted="
                    << pressureClampGlobalBelow - pressureClampGlobalPrinted
                    << " per_rank_cap=8"
                    << nl << endl;

                Pout<< "CLAMP_TRACE_CELL_RANK_SUMMARY"
                    << " time_s=" << runTime.timeName()
                    << " outer=" << i4fOuterLoop
                    << " pass=" << pressureClampTracePass
                    << " rank=" << Pstream::myProcNo()
                    << " local_below_pMin=" << pressureClampLocalBelow
                    << " local_printed=" << pressureClampPrintedCells
                    << " local_omitted="
                    << pressureClampLocalBelow - pressureClampPrintedCells
                    << " per_rank_cap=8"
                    << nl;
            }

            tmp<scalarField> tPressureClampResidualBefore;
            tmp<surfaceScalarField> tPressureClampFluxBefore;
            scalar pressureClampResidualBeforeMax = 0;
            scalar pressureClampResidualBeforeL1V = 0;
            scalar pressureClampFluxBeforeMax = 0;
            scalar pressureClampFluxBeforeL1 = 0;

            if (i4fFullPressureAudit)
            {
                // Full pressure-equation defects with p_rgh at its solved value,
                // immediately before the stock absolute-pressure floor.
                scalarField i4fComp1BeforeFloor(p_rghEqnComp1().residual());
                scalarField i4fComp2BeforeFloor(p_rghEqnComp2().residual());
                scalarField i4fIncompBeforeFloor(p_rghEqnIncomp.residual());
                tmp<fvScalarMatrix> tI4fFullBeforeFloor
                (
                    p_rghEqnComp1() + p_rghEqnComp2() + p_rghEqnIncomp
                );
                scalarField i4fFullBeforeFloor
                (
                    tI4fFullBeforeFloor().residual()
                );

                i4fReportPressureResidual
                (
                    "solved_before_stock_floor", "comp1", i4fPressurePass,
                    runTime.timeName(), i4fComp1BeforeFloor
                );
                i4fReportPressureResidual
                (
                    "solved_before_stock_floor", "comp2", i4fPressurePass,
                    runTime.timeName(), i4fComp2BeforeFloor
                );
                i4fReportPressureResidual
                (
                    "solved_before_stock_floor", "incompressible", i4fPressurePass,
                    runTime.timeName(), i4fIncompBeforeFloor
                );
                i4fReportPressureResidual
                (
                    "solved_before_stock_floor", "full_comp1_plus_comp2_plus_incomp",
                    i4fPressurePass, runTime.timeName(), i4fFullBeforeFloor
                );
                i4fReportOperatorPressureDefect
                (
                    tI4fFullBeforeFloor(), p_rgh, mesh,
                    "solved_before_stock_floor", "full_comp1_plus_comp2_plus_incomp",
                    i4fPressurePass, runTime.timeName()
                );

                label i4fFloorCellsPrinted = 0;
                const labelListList& i4fCellNeighbors = mesh.cellCells();
                forAll(pressureClampRaw, celli)
                {
                    if
                    (
                        false
                     && pressureClampRaw[celli] < pressureClampFloor
                     && i4fFloorCellsPrinted < 8
                    )
                    {
                        Pout<< "I4F_FLOOR_DEFECT_CELL"
                            << " time_s=" << runTime.timeName()
                            << " pass=" << i4fPressurePass
                            << " rank=" << Pstream::myProcNo()
                            << " cell=" << celli
                            << " p_raw_Pa=" << pressureClampRaw[celli]
                            << " p_rgh_Pa=" << p_rgh[celli]
                            << " pMin_Pa=" << pressureClampFloor
                            << " C_m=" << mesh.C().primitiveField()[celli]
                            << " nativeV_m3=" << mesh.V()[celli]
                            << " alpha1=" << alpha1[celli]
                            << " alpha2=" << alpha2[celli]
                            << " T_K=" << T[celli]
                            << " rho_mix_kg_m3=" << rho[celli]
                            << " rho1_kg_m3=" << rho1[celli]
                            << " rho2_kg_m3=" << rho2[celli]
                            << " U_m_s=" << U[celli]
                            << " r_comp1_m3_s=" << i4fComp1BeforeFloor[celli]
                            << " r_comp2_m3_s=" << i4fComp2BeforeFloor[celli]
                            << " r_incomp_m3_s=" << i4fIncompBeforeFloor[celli]
                            << " r_full_m3_s=" << i4fFullBeforeFloor[celli]
                            << nl;

                        const labelList& neighbors = i4fCellNeighbors[celli];
                        forAll(neighbors, neighbori)
                        {
                            const label nei = neighbors[neighbori];
                            Pout<< "I4F_FLOOR_DEFECT_NEIGHBOR"
                                << " time_s=" << runTime.timeName()
                                << " pass=" << i4fPressurePass
                                << " rank=" << Pstream::myProcNo()
                                << " trigger_cell=" << celli
                                << " cell=" << nei
                                << " p_raw_Pa=" << pressureClampRaw[nei]
                                << " p_rgh_Pa=" << p_rgh[nei]
                                << " C_m=" << mesh.C().primitiveField()[nei]
                                << " alpha1=" << alpha1[nei]
                                << " T_K=" << T[nei]
                                << " rho1_kg_m3=" << rho1[nei]
                                << " rho2_kg_m3=" << rho2[nei]
                                << " r_comp1_m3_s=" << i4fComp1BeforeFloor[nei]
                                << " r_comp2_m3_s=" << i4fComp2BeforeFloor[nei]
                                << " r_incomp_m3_s=" << i4fIncompBeforeFloor[nei]
                                << " r_full_m3_s=" << i4fFullBeforeFloor[nei]
                                << nl;
                        }
                        ++i4fFloorCellsPrinted;
                    }
                }

                // Snapshot the same pressure-matrix diagnostics before the stock
                // p/p_rgh floor. The fvMatrix equation itself is not modified.
                tPressureClampResidualBefore = p_rghEqnIncomp.residual();
                tPressureClampFluxBefore = p_rghEqnIncomp.flux();
                const scalarField& pressureClampResidualBefore = tPressureClampResidualBefore();
                const surfaceScalarField& pressureClampFluxBefore = tPressureClampFluxBefore();

                pressureClampResidualBeforeMax = 0;
                pressureClampResidualBeforeL1V = 0;
                forAll(pressureClampResidualBefore, celli)
                {
                    const scalar residualMagnitude = mag(pressureClampResidualBefore[celli]);
                    pressureClampResidualBeforeMax = max
                    (
                        pressureClampResidualBeforeMax,
                        residualMagnitude
                    );
                    pressureClampResidualBeforeL1V += residualMagnitude*mesh.V()[celli];
                }
                reduce(pressureClampResidualBeforeMax, maxOp<scalar>());
                reduce(pressureClampResidualBeforeL1V, sumOp<scalar>());

                pressureClampFluxBeforeMax = 0;
                pressureClampFluxBeforeL1 = 0;
                forAll(pressureClampFluxBefore.primitiveField(), facei)
                {
                    const scalar fluxMagnitude = mag
                    (
                        pressureClampFluxBefore.primitiveField()[facei]
                    );
                    pressureClampFluxBeforeMax = max
                    (
                        pressureClampFluxBeforeMax,
                        fluxMagnitude
                    );
                    pressureClampFluxBeforeL1 += fluxMagnitude;
                }
                forAll(mesh.boundary(), patchi)
                {
                    const scalar patchWeight = mesh.boundary()[patchi].coupled() ? 0.5 : 1.0;
                    forAll(pressureClampFluxBefore.boundaryField()[patchi], facei)
                    {
                        const scalar fluxMagnitude = mag
                        (
                            pressureClampFluxBefore.boundaryField()[patchi][facei]
                        );
                        pressureClampFluxBeforeMax = max
                        (
                            pressureClampFluxBeforeMax,
                            fluxMagnitude
                        );
                        pressureClampFluxBeforeL1 += patchWeight*fluxMagnitude;
                    }
                }
                reduce(pressureClampFluxBeforeMax, maxOp<scalar>());
                reduce(pressureClampFluxBeforeL1, sumOp<scalar>());
            }



            // Original solver clamp and hydrostatic reconstruction, unchanged.
            p = max(p_rgh + (alpha1*rho1 + alpha2*rho2)*gh, pMin);
            p_rgh = p - (alpha1*rho1 + alpha2*rho2)*gh;

            if (i4fFullPressureAudit)
            {
                // Re-evaluate each component and the assembled equation at the
                // same p_rgh after the stock floor, without changing the equation.
                const scalarField& pressureClampResidualBefore = tPressureClampResidualBefore();
                const surfaceScalarField& pressureClampFluxBefore = tPressureClampFluxBefore();
                scalarField i4fComp1AfterFloor(p_rghEqnComp1().residual());
                scalarField i4fComp2AfterFloor(p_rghEqnComp2().residual());
                scalarField i4fIncompAfterFloor(p_rghEqnIncomp.residual());
                tmp<fvScalarMatrix> tI4fFullAfterFloor
                (
                    p_rghEqnComp1() + p_rghEqnComp2() + p_rghEqnIncomp
                );
                scalarField i4fFullAfterFloor
                (
                    tI4fFullAfterFloor().residual()
                );

                i4fReportPressureResidual
                (
                    "after_stock_floor", "comp1", i4fPressurePass,
                    runTime.timeName(), i4fComp1AfterFloor
                );
                i4fReportPressureResidual
                (
                    "after_stock_floor", "comp2", i4fPressurePass,
                    runTime.timeName(), i4fComp2AfterFloor
                );
                i4fReportPressureResidual
                (
                    "after_stock_floor", "incompressible", i4fPressurePass,
                    runTime.timeName(), i4fIncompAfterFloor
                );
                i4fReportPressureResidual
                (
                    "after_stock_floor", "full_comp1_plus_comp2_plus_incomp",
                    i4fPressurePass, runTime.timeName(), i4fFullAfterFloor
                );
                i4fReportOperatorPressureDefect
                (
                    tI4fFullAfterFloor(), p_rgh, mesh,
                    "after_stock_floor", "full_comp1_plus_comp2_plus_incomp",
                    i4fPressurePass, runTime.timeName()
                );

                forAll(pressureClampRaw, celli)
                {
                    if (false && pressureClampRaw[celli] < pressureClampFloor)
                    {
                        Pout<< "I4F_FLOOR_DEFECT_POST_CELL"
                            << " time_s=" << runTime.timeName()
                            << " pass=" << i4fPressurePass
                            << " rank=" << Pstream::myProcNo()
                            << " cell=" << celli
                            << " p_raw_Pa=" << pressureClampRaw[celli]
                            << " p_clamped_Pa=" << p[celli]
                            << " p_rgh_clamped_Pa=" << p_rgh[celli]
                            << " r_comp1_m3_s=" << i4fComp1AfterFloor[celli]
                            << " r_comp2_m3_s=" << i4fComp2AfterFloor[celli]
                            << " r_incomp_m3_s=" << i4fIncompAfterFloor[celli]
                            << " r_full_m3_s=" << i4fFullAfterFloor[celli]
                            << nl;
                    }
                }

                // Evaluate the exact same retained matrix after only the p_rgh
                // mutation caused by the stock clamp. These are clamp diagnostics,
                // not a water-mass or continuity ledger.
                scalarField pressureClampResidualAfter
                (
                    p_rghEqnIncomp.residual()
                );
                tmp<surfaceScalarField> tPressureClampFluxAfter
                (
                    p_rghEqnIncomp.flux()
                );
                surfaceScalarField pressureClampFluxAfter
                (
                    tPressureClampFluxAfter()
                );

                scalar pressureClampResidualAfterMax = 0;
                scalar pressureClampResidualAfterL1V = 0;
                scalar pressureClampResidualDeltaMax = 0;
                scalar pressureClampResidualDeltaL1V = 0;
                forAll(pressureClampResidualAfter, celli)
                {
                    const scalar afterMagnitude = mag(pressureClampResidualAfter[celli]);
                    const scalar deltaMagnitude = mag
                    (
                        pressureClampResidualAfter[celli]
                      - pressureClampResidualBefore[celli]
                    );
                    pressureClampResidualAfterMax = max
                    (
                        pressureClampResidualAfterMax,
                        afterMagnitude
                    );
                    pressureClampResidualAfterL1V += afterMagnitude*mesh.V()[celli];
                    pressureClampResidualDeltaMax = max
                    (
                        pressureClampResidualDeltaMax,
                        deltaMagnitude
                    );
                    pressureClampResidualDeltaL1V += deltaMagnitude*mesh.V()[celli];
                }
                reduce(pressureClampResidualAfterMax, maxOp<scalar>());
                reduce(pressureClampResidualAfterL1V, sumOp<scalar>());
                reduce(pressureClampResidualDeltaMax, maxOp<scalar>());
                reduce(pressureClampResidualDeltaL1V, sumOp<scalar>());

                scalar pressureClampFluxAfterMax = 0;
                scalar pressureClampFluxAfterL1 = 0;
                scalar pressureClampFluxDeltaMax = 0;
                scalar pressureClampFluxDeltaL1 = 0;
                forAll(pressureClampFluxAfter.primitiveField(), facei)
                {
                    const scalar afterValue = pressureClampFluxAfter.primitiveField()[facei];
                    const scalar deltaMagnitude = mag
                    (
                        afterValue - pressureClampFluxBefore.primitiveField()[facei]
                    );
                    pressureClampFluxAfterMax = max
                    (
                        pressureClampFluxAfterMax,
                        mag(afterValue)
                    );
                    pressureClampFluxAfterL1 += mag(afterValue);
                    pressureClampFluxDeltaMax = max
                    (
                        pressureClampFluxDeltaMax,
                        deltaMagnitude
                    );
                    pressureClampFluxDeltaL1 += deltaMagnitude;
                }
                forAll(mesh.boundary(), patchi)
                {
                    const scalar patchWeight = mesh.boundary()[patchi].coupled() ? 0.5 : 1.0;
                    forAll(pressureClampFluxAfter.boundaryField()[patchi], facei)
                    {
                        const scalar afterValue = pressureClampFluxAfter.boundaryField()[patchi][facei];
                        const scalar beforeValue = pressureClampFluxBefore.boundaryField()[patchi][facei];
                        const scalar deltaMagnitude = mag(afterValue - beforeValue);
                        pressureClampFluxAfterMax = max
                        (
                            pressureClampFluxAfterMax,
                            mag(afterValue)
                        );
                        pressureClampFluxAfterL1 += patchWeight*mag(afterValue);
                        pressureClampFluxDeltaMax = max
                        (
                            pressureClampFluxDeltaMax,
                            deltaMagnitude
                        );
                        pressureClampFluxDeltaL1 += patchWeight*deltaMagnitude;
                    }
                }
                reduce(pressureClampFluxAfterMax, maxOp<scalar>());
                reduce(pressureClampFluxAfterL1, sumOp<scalar>());
                reduce(pressureClampFluxDeltaMax, maxOp<scalar>());
                reduce(pressureClampFluxDeltaL1, sumOp<scalar>());

                Info<< "CLAMP_TRACE_MATRIX"
                    << " time_s=" << runTime.timeName()
                    << " pass=" << pressureClampTracePass
                    << " residual_before_max=" << pressureClampResidualBeforeMax
                    << " residual_after_max=" << pressureClampResidualAfterMax
                    << " residual_delta_max=" << pressureClampResidualDeltaMax
                    << " residual_before_L1_nativeV=" << pressureClampResidualBeforeL1V
                    << " residual_after_L1_nativeV=" << pressureClampResidualAfterL1V
                    << " residual_delta_L1_nativeV=" << pressureClampResidualDeltaL1V
                    << " flux_before_max=" << pressureClampFluxBeforeMax
                    << " flux_after_max=" << pressureClampFluxAfterMax
                    << " flux_delta_max=" << pressureClampFluxDeltaMax
                    << " flux_before_L1=" << pressureClampFluxBeforeL1
                    << " flux_after_L1=" << pressureClampFluxAfterL1
                    << " flux_delta_L1=" << pressureClampFluxDeltaL1
                    << " flux_dimensions=" << pressureClampFluxAfter.dimensions()
                    << " flux_L1_rule=internal_plus_all_boundary_faces_coupled_patches_half_weighted"
                    << " residual_scope=p_rghEqnIncomp_only"
                    << nl << endl;
            }



            dgdt =
            (
                alpha1*(p_rghEqnComp2 & p_rgh)
              - alpha2*(p_rghEqnComp1 & p_rgh)
            );

            phi = phiHbyA + p_rghEqnIncomp.flux();

            U = HbyA
              + rAU*fvc::reconstruct((phig + p_rghEqnIncomp.flux())/rAUf);
            U.correctBoundaryConditions();
            fvOptions.correct(U);
        }
    }

    scalar i4fWaterMassBeforeEosLocal = 0;
    scalar i4fGasMassBeforeEosLocal = 0;
    forAll(alpha1, celli)
    {
        i4fWaterMassBeforeEosLocal += alpha1[celli]*rho1[celli]*mesh.V()[celli];
        i4fGasMassBeforeEosLocal += alpha2[celli]*rho2[celli]*mesh.V()[celli];
    }
    reduce(i4fWaterMassBeforeEosLocal, sumOp<scalar>());
    reduce(i4fGasMassBeforeEosLocal, sumOp<scalar>());

    surfaceScalarField i4fRho1fBeforeEos
    (
        "i4fRho1fBeforeEos", fvc::interpolate(rho1)
    );
    surfaceScalarField i4fRho2fBeforeEos
    (
        "i4fRho2fBeforeEos", fvc::interpolate(rho2)
    );
    surfaceScalarField i4fWaterAdvMassFluxBeforeEos
    (
        "i4fWaterAdvMassFluxBeforeEos",
        alphaPhi1*i4fRho1fBeforeEos
    );
    surfaceScalarField i4fGasAdvMassFluxBeforeEos
    (
        "i4fGasAdvMassFluxBeforeEos",
        alphaPhi2*i4fRho2fBeforeEos
    );
    const scalar i4fWaterBoundaryBeforeEos = i4fReportBoundaryMassFlux
    (
        mesh, "pEqn_phase_flux_pre_EOS_update", "water",
        i4fWaterAdvMassFluxBeforeEos
    );
    const scalar i4fGasBoundaryBeforeEos = i4fReportBoundaryMassFlux
    (
        mesh, "pEqn_phase_flux_pre_EOS_update", "gas",
        i4fGasAdvMassFluxBeforeEos
    );

    Info<< "I4F_PHASE_MASS_STATE"
        << " time_s=" << runTime.timeName()
        << " pass=" << i4fPressurePass
        << " stage=before_correctRho"
        << " water_inventory_kg=" << i4fWaterMassBeforeEosLocal
        << " gas_inventory_kg=" << i4fGasMassBeforeEosLocal
        << " water_signed_boundary_flux_kg_s=" << i4fWaterBoundaryBeforeEos
        << " gas_signed_boundary_flux_kg_s=" << i4fGasBoundaryBeforeEos
        << " alphaFluxField=alphaPhi1_and_alphaPhi2"
        << " phaseDensityField=EOS_rho1_and_rho2_at_pEqn_assembly"
        << " nAlphaSubCycles=" << nAlphaSubCycles
        << nl << endl;

    // Update densities from change in p_rgh
    mixture.thermo1().correctRho(psi1*(p_rgh - p_rgh_0));
    mixture.thermo2().correctRho(psi2*(p_rgh - p_rgh_0));

    rho = alpha1*rho1 + alpha2*rho2;

    // Correct p_rgh for consistency with p and the updated densities
    p_rgh = p - rho*gh;
    p_rgh.correctBoundaryConditions();

    scalar i4fWaterMassAfterEosLocal = 0;
    scalar i4fGasMassAfterEosLocal = 0;
    forAll(alpha1, celli)
    {
        i4fWaterMassAfterEosLocal += alpha1[celli]*rho1[celli]*mesh.V()[celli];
        i4fGasMassAfterEosLocal += alpha2[celli]*rho2[celli]*mesh.V()[celli];
    }
    reduce(i4fWaterMassAfterEosLocal, sumOp<scalar>());
    reduce(i4fGasMassAfterEosLocal, sumOp<scalar>());

    surfaceScalarField i4fRho1fAfterEos
    (
        "i4fRho1fAfterEos", fvc::interpolate(rho1)
    );
    surfaceScalarField i4fRho2fAfterEos
    (
        "i4fRho2fAfterEos", fvc::interpolate(rho2)
    );
    surfaceScalarField i4fWaterAdvMassFluxAfterEos
    (
        "i4fWaterAdvMassFluxAfterEos",
        alphaPhi1*i4fRho1fAfterEos
    );
    surfaceScalarField i4fGasAdvMassFluxAfterEos
    (
        "i4fGasAdvMassFluxAfterEos",
        alphaPhi2*i4fRho2fAfterEos
    );
    const scalar i4fWaterBoundaryAfterEos = i4fReportBoundaryMassFlux
    (
        mesh, "pEqn_phase_flux_post_EOS_update", "water",
        i4fWaterAdvMassFluxAfterEos
    );
    const scalar i4fGasBoundaryAfterEos = i4fReportBoundaryMassFlux
    (
        mesh, "pEqn_phase_flux_post_EOS_update", "gas",
        i4fGasAdvMassFluxAfterEos
    );

    tmp<volScalarField> tI4fWaterContinuityAfterEos
    (
        fvc::ddt(alpha1, rho1) + fvc::div(i4fWaterAdvMassFluxAfterEos)
    );
    tmp<volScalarField> tI4fGasContinuityAfterEos
    (
        fvc::ddt(alpha2, rho2) + fvc::div(i4fGasAdvMassFluxAfterEos)
    );
    const volScalarField& i4fWaterContinuityAfterEos
    (
        tI4fWaterContinuityAfterEos()
    );
    const volScalarField& i4fGasContinuityAfterEos
    (
        tI4fGasContinuityAfterEos()
    );

    scalar i4fWaterContinuityMaxLocal = 0;
    scalar i4fWaterContinuityL1Local = 0;
    scalar i4fWaterContinuitySignedLocal = 0;
    scalar i4fGasContinuityMaxLocal = 0;
    scalar i4fGasContinuityL1Local = 0;
    scalar i4fGasContinuitySignedLocal = 0;
    forAll(alpha1, celli)
    {
        const scalar waterResidual = i4fWaterContinuityAfterEos[celli];
        const scalar gasResidual = i4fGasContinuityAfterEos[celli];
        i4fWaterContinuityMaxLocal = max
        (
            i4fWaterContinuityMaxLocal,
            mag(waterResidual)
        );
        i4fWaterContinuityL1Local += mag(waterResidual)*mesh.V()[celli];
        i4fWaterContinuitySignedLocal += waterResidual*mesh.V()[celli];
        i4fGasContinuityMaxLocal = max
        (
            i4fGasContinuityMaxLocal,
            mag(gasResidual)
        );
        i4fGasContinuityL1Local += mag(gasResidual)*mesh.V()[celli];
        i4fGasContinuitySignedLocal += gasResidual*mesh.V()[celli];
    }
    reduce(i4fWaterContinuityMaxLocal, maxOp<scalar>());
    reduce(i4fWaterContinuityL1Local, sumOp<scalar>());
    reduce(i4fWaterContinuitySignedLocal, sumOp<scalar>());
    reduce(i4fGasContinuityMaxLocal, maxOp<scalar>());
    reduce(i4fGasContinuityL1Local, sumOp<scalar>());
    reduce(i4fGasContinuitySignedLocal, sumOp<scalar>());

    // Localized post-EOS phase continuity values from the same native
    // alphaPhi*rhoFace fields used by the global residual above.
    if (false && i4fFrozenPredictorSp && Pstream::myProcNo() == 2)
    {
        const label i4fPhaseCells[] = {2684, 2752};
        for (const label i4fCell : i4fPhaseCells)
        {
            Pout<< "I4F_EOS_PHASE_CONTINUITY_TARGET"
                << " time_s=" << runTime.timeName()
                << " outer_iteration=" << i4fOuterLoop
                << " pressure_pass=" << i4fPressurePass
                << " rank=" << Pstream::myProcNo()
                << " local_cell=" << i4fCell
                << " alpha_water=" << alpha1[i4fCell]
                << " rho_water_kg_m3=" << rho1[i4fCell]
                << " water_residual_kg_m3_s="
                << i4fWaterContinuityAfterEos[i4fCell]
                << " alpha_gas=" << alpha2[i4fCell]
                << " rho_gas_kg_m3=" << rho2[i4fCell]
                << " gas_residual_kg_m3_s="
                << i4fGasContinuityAfterEos[i4fCell]
                << " flux=alphaPhi_phase_times_interpolated_EOS_rho"
                << nl;
        }
    }

    Info<< "I4F_PHASE_MASS_STATE"
        << " time_s=" << runTime.timeName()
        << " pass=" << i4fPressurePass
        << " stage=after_correctRho"
        << " water_inventory_kg=" << i4fWaterMassAfterEosLocal
        << " gas_inventory_kg=" << i4fGasMassAfterEosLocal
        << " water_signed_boundary_flux_kg_s=" << i4fWaterBoundaryAfterEos
        << " gas_signed_boundary_flux_kg_s=" << i4fGasBoundaryAfterEos
        << " alphaFluxField=alphaPhi1_and_alphaPhi2"
        << " phaseDensityField=EOS_rho1_and_rho2_after_correctRho"
        << " nAlphaSubCycles=" << nAlphaSubCycles
        << " source_terms=none_in_configured_phase_mass_equations"
        << " continuity_definition=ddt(alpha*rho)+div(alphaPhi*rhoFace)"
        << " water_cont_max_kg_m3_s=" << i4fWaterContinuityMaxLocal
        << " water_cont_L1_nativeV_kg_s=" << i4fWaterContinuityL1Local
        << " water_cont_signed_nativeV_kg_s=" << i4fWaterContinuitySignedLocal
        << " gas_cont_max_kg_m3_s=" << i4fGasContinuityMaxLocal
        << " gas_cont_L1_nativeV_kg_s=" << i4fGasContinuityL1Local
        << " gas_cont_signed_nativeV_kg_s=" << i4fGasContinuitySignedLocal
        << nl << endl;

    K = 0.5*magSqr(U);
}
