    fvVectorMatrix UEqn
    (
        fvm::ddt(rho, U) + fvm::div(rhoPhi, U)
      - fvm::Sp(contErr, U)
      + MRF.DDt(rho, U)
      + turbulence.divDevRhoReff(U)
     ==
        fvOptions(rho, U)
    );

    UEqn.relax();

    fvOptions.constrain(UEqn);

    // Construct A() on every rank because it corrects a volField boundary.
    // Restrict only the file output to the selected rank/cell.
    const tmp<volScalarField> tI4fUEqnA(UEqn.A());
    {
        const label i4fValveLocalCell = 2684;
        if (Pstream::myProcNo() == 2 && i4fValveLocalCell < mesh.nCells())
        {
            const scalar i4fA =
                tI4fUEqnA().primitiveField()[i4fValveLocalCell];
            std::ofstream i4fUEqnLog("valve-ueqn-rank2.log", std::ios::app);
            i4fUEqnLog << std::setprecision(17)
                << "I4F_VALVE_UEQN_DIAG"
                << " time_s=" << runTime.timeName()
                << " time_index=" << runTime.timeIndex()
                << " outer_iteration=" << i4fOuterLoop
                << " rank=" << Pstream::myProcNo()
                << " local_cell=" << i4fValveLocalCell
                << " Ux_before_predictor_m_s=" << U[i4fValveLocalCell].x()
                << " Uy_before_predictor_m_s=" << U[i4fValveLocalCell].y()
                << " Uz_before_predictor_m_s=" << U[i4fValveLocalCell].z()
                << " rho_kg_m3=" << rho[i4fValveLocalCell]
                << " alpha_water=" << alpha1[i4fValveLocalCell]
                << " diag_per_volume_kg_m3_s=" << i4fA
                << " rAU_m3_s_kg=" << 1.0/i4fA
                << " diag_integrated_kg_s="
                << UEqn.diag()[i4fValveLocalCell]
                << std::endl;
        }
    }

    if (pimple.momentumPredictor())
    {
        solve
        (
            UEqn
         ==
            fvc::reconstruct
            (
                (
                    mixture.surfaceTensionForce()
                  - ghf*fvc::snGrad(rho)
                  - fvc::snGrad(p_rgh)
                ) * mesh.magSf()
            )
        );

        fvOptions.correct(U);

        K = 0.5*magSqr(U);
    }
