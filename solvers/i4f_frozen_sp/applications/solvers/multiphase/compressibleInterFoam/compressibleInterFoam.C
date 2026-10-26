/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | www.openfoam.com
     \\/     M anipulation  |
-------------------------------------------------------------------------------
    Copyright (C) 2011-2017 OpenFOAM Foundation
    Copyright (C) OpenCFD OpenCFD Ltd.
-------------------------------------------------------------------------------
License
    This file is part of OpenFOAM.

    OpenFOAM is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    OpenFOAM is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
    for more details.

    You should have received a copy of the GNU General Public License
    along with OpenFOAM.  If not, see <http://www.gnu.org/licenses/>.

Application
    compressibleInterFoam

Group
    grpMultiphaseSolvers

Description
    Solver for two compressible, non-isothermal immiscible fluids using a VOF
    (volume of fluid) phase-fraction based interface capturing approach.

    The momentum and other fluid properties are of the "mixture" and a single
    momentum equation is solved.

    Either mixture or two-phase transport modelling may be selected.  In the
    mixture approach a single laminar, RAS or LES model is selected to model the
    momentum stress.  In the Euler-Euler two-phase approach separate laminar,
    RAS or LES selected models are selected for each of the phases.

\*---------------------------------------------------------------------------*/

#include "fvCFD.H"
#include "CMULES.H"
#include "EulerDdtScheme.H"
#include "localEulerDdtScheme.H"
#include "CrankNicolsonDdtScheme.H"
#include "subCycle.H"
#include "compressibleInterPhaseTransportModel.H"
#include "pimpleControl.H"
#include "fvOptions.H"
#include "fvcSmooth.H"
#include "i4fDefectAudit.H"
#include <fstream>
#include <iomanip>

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

int main(int argc, char *argv[])
{
    argList::addNote
    (
        "Solver for two compressible, non-isothermal immiscible fluids"
        " using VOF phase-fraction based interface capturing."
    );

    #include "postProcess.H"

    #include "addCheckCaseOptions.H"
    #include "setRootCaseLists.H"
    #include "createTime.H"
    #include "createMesh.H"
    #include "createControl.H"
    #include "createTimeControls.H"
    #include "createFields.H"

    // Private experiment control. Missing entry defaults OFF, preserving the
    // stock v7 source path in the disabled passivity arm.
    const Switch i4fFrozenPredictorSp
    (
        runTime.controlDict().lookupOrDefault<Switch>
        (
            "i4fFrozenPredictorSp",
            false
        )
    );

    // Increase diagnostic stream precision only; solver state and equations
    // are unchanged.
    Info.stream().precision(16);
    Pout.precision(16);

    volScalarField& p = mixture.p();
    volScalarField& T = mixture.T();
    const volScalarField& psi1 = mixture.thermo1().psi();
    const volScalarField& psi2 = mixture.thermo2().psi();

    scalar i4fInitialWaterMassLocal = 0;
    scalar i4fInitialGasMassLocal = 0;
    forAll(alpha1, celli)
    {
        i4fInitialWaterMassLocal += alpha1[celli]*rho1[celli]*mesh.V()[celli];
        i4fInitialGasMassLocal += alpha2[celli]*rho2[celli]*mesh.V()[celli];
    }
    reduce(i4fInitialWaterMassLocal, sumOp<scalar>());
    reduce(i4fInitialGasMassLocal, sumOp<scalar>());

    Info<< "I4F_INITIAL_PHASE_MASS"
        << " time_s=" << runTime.timeName()
        << " water_inventory_kg=" << i4fInitialWaterMassLocal
        << " gas_inventory_kg=" << i4fInitialGasMassLocal
        << " definition=sum(alpha_phase*rho_phase*native_cellV)"
        << nl << endl;

    if (!LTS)
    {
        #include "readTimeControls.H"
        #include "CourantNo.H"
        #include "setInitialDeltaT.H"
    }

    // * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

    Info<< "\nStarting time loop\n" << endl;

    while (runTime.run())
    {
        #include "readTimeControls.H"

        if (LTS)
        {
            #include "setRDeltaT.H"
        }
        else
        {
            #include "CourantNo.H"
            #include "alphaCourantNo.H"
            #include "setDeltaT.H"
        }

        ++runTime;

        Info<< "Time = " << runTime.timeName() << nl << endl;

        // --- Pressure-velocity PIMPLE corrector loop
        static label i4fOuterLoop = 0;
        static label i4fAlphaSuSpCallIndex = 0;
        while (pimple.loop())
        {
            ++i4fOuterLoop;

            // Internal-cell snapshots at the start of this outer iteration.
            // The first row compares with the previous time-step state; later
            // rows compare successive outer iterations at this physical time.
            const scalarField i4fPOuterStart(p.primitiveField());
            const vectorField i4fUOuterStart(U.primitiveField());
            const scalarField i4fPhiOuterStart(phi.primitiveField());
            const scalarField i4fAlphaOuterStart(alpha1.primitiveField());
            const scalarField i4fTOuterStart(T.primitiveField());
            const scalarField i4fRho1OuterStart(rho1.primitiveField());
            const scalarField i4fRho2OuterStart(rho2.primitiveField());

            #include "alphaControls.H"
            #include "compressibleAlphaEqnSubCycle.H"

            turbulence.correctPhasePhi();

            #include "UEqn.H"
            volScalarField divUp("divUp", fvc::div(fvc::absolute(phi, U), p));
            #include "TEqn.H"

            // --- Pressure corrector loop
            while (pimple.correct())
            {
                #include "pEqn.H"
            }

            if (pimple.turbCorr())
            {
                turbulence.correct();
            }

            scalar i4fDpMax = 0;
            scalar i4fDpRelMax = 0;
            scalar i4fDUmax = 0;
            scalar i4fDPhiMax = 0;
            scalar i4fDAlphaMax = 0;
            scalar i4fDTMax = 0;
            scalar i4fDRho1Max = 0;
            scalar i4fDRho2Max = 0;
            scalar i4fDpLocalMax = -1;
            label i4fDpLocalCell = -1;
            scalar i4fDAlphaLocalMax = -1;
            label i4fDAlphaLocalCell = -1;

            forAll(p.primitiveField(), celli)
            {
                const scalar dp = mag(p[celli] - i4fPOuterStart[celli]);
                i4fDpMax = max(i4fDpMax, dp);
                if (dp > i4fDpLocalMax)
                {
                    i4fDpLocalMax = dp;
                    i4fDpLocalCell = celli;
                }
                i4fDpRelMax = max
                (
                    i4fDpRelMax,
                    dp/max(mag(i4fPOuterStart[celli]), scalar(1))
                );
                i4fDUmax = max
                (
                    i4fDUmax,
                    mag(U[celli] - i4fUOuterStart[celli])
                );
                i4fDAlphaMax = max
                (
                    i4fDAlphaMax,
                    mag(alpha1[celli] - i4fAlphaOuterStart[celli])
                );
                const scalar dAlpha =
                    mag(alpha1[celli] - i4fAlphaOuterStart[celli]);
                if (dAlpha > i4fDAlphaLocalMax)
                {
                    i4fDAlphaLocalMax = dAlpha;
                    i4fDAlphaLocalCell = celli;
                }
                i4fDTMax = max
                (
                    i4fDTMax,
                    mag(T[celli] - i4fTOuterStart[celli])
                );
                i4fDRho1Max = max
                (
                    i4fDRho1Max,
                    mag(rho1[celli] - i4fRho1OuterStart[celli])
                );
                i4fDRho2Max = max
                (
                    i4fDRho2Max,
                    mag(rho2[celli] - i4fRho2OuterStart[celli])
                );
            }

            forAll(phi.primitiveField(), facei)
            {
                i4fDPhiMax = max
                (
                    i4fDPhiMax,
                    mag(phi[facei] - i4fPhiOuterStart[facei])
                );
            }

            reduce(i4fDpMax, maxOp<scalar>());
            reduce(i4fDpRelMax, maxOp<scalar>());
            reduce(i4fDUmax, maxOp<scalar>());
            reduce(i4fDPhiMax, maxOp<scalar>());
            reduce(i4fDAlphaMax, maxOp<scalar>());
            reduce(i4fDTMax, maxOp<scalar>());
            reduce(i4fDRho1Max, maxOp<scalar>());
            reduce(i4fDRho2Max, maxOp<scalar>());

            // Read-only localization of the global outer-update maxima.
            // Each rank prints only if its local controlling cell attains the
            // already-computed global maximum; these are diagnostics only.
            const scalar i4fDpTieTolerance =
                64*SMALL*max(i4fDpMax, scalar(1));
            const scalar i4fDAlphaTieTolerance =
                64*SMALL*max(i4fDAlphaMax, scalar(1));

            const bool i4fDpCellIsGlobal =
                i4fDpLocalCell >= 0
             && mag(i4fDpLocalMax - i4fDpMax) <= i4fDpTieTolerance;
            const label i4fValveZoneId =
                mesh.cellZones().findZoneID("valveZone");

            auto i4fWriteOuterCell =
            [&]
            (const char* rowName, const label celli, const scalar globalMax)
            {
                bool inValveZone = false;
                if (i4fValveZoneId >= 0)
                {
                    const cellZone& zone = mesh.cellZones()[i4fValveZoneId];
                    forAll(zone, zoneCelli)
                    {
                        if (zone[zoneCelli] == celli)
                        {
                            inValveZone = true;
                            break;
                        }
                    }
                }

                Pout<< "I4F_OUTER_" << rowName
                    << " time_s=" << runTime.timeName()
                    << " time_index=" << runTime.timeIndex()
                    << " outer_iteration=" << i4fOuterLoop
                    << " rank=" << Pstream::myProcNo()
                    << " local_cell=" << celli
                    << " global_max_update=" << globalMax
                    << " C_m=" << mesh.C().primitiveField()[celli]
                    << " nativeV_m3=" << mesh.V()[celli]
                    << " in_valve_zone=" << inValveZone
                    << " p_before_Pa=" << i4fPOuterStart[celli]
                    << " p_after_Pa=" << p[celli]
                    << " signed_delta_p_Pa="
                    << p[celli] - i4fPOuterStart[celli]
                    << " alpha_before=" << i4fAlphaOuterStart[celli]
                    << " alpha_after=" << alpha1[celli]
                    << " signed_delta_alpha="
                    << alpha1[celli] - i4fAlphaOuterStart[celli]
                    << " U_before_m_s=" << i4fUOuterStart[celli]
                    << " U_after_m_s=" << U[celli]
                    << " T_before_K=" << i4fTOuterStart[celli]
                    << " T_after_K=" << T[celli]
                    << " rho1_before_kg_m3=" << i4fRho1OuterStart[celli]
                    << " rho1_after_kg_m3=" << rho1[celli]
                    << " rho2_before_kg_m3=" << i4fRho2OuterStart[celli]
                    << " rho2_after_kg_m3=" << rho2[celli]
                    << " native_faces=[";

                const cell& cellFaces = mesh.cells()[celli];
                forAll(cellFaces, faceLocali)
                {
                    const label facei = cellFaces[faceLocali];
                    Pout<< facei << ":owner=" << mesh.owner()[facei];
                    if (facei < mesh.nInternalFaces())
                    {
                        Pout<< ":neighbour=" << mesh.neighbour()[facei]
                            << ":patch=internal";
                    }
                    else
                    {
                        const label patchi =
                            mesh.boundaryMesh().whichPatch(facei);
                        Pout<< ":neighbour=-1:patch="
                            << mesh.boundaryMesh()[patchi].name();
                    }
                    if (faceLocali + 1 < cellFaces.size()) Pout<< ";";
                }
                Pout<< "]" << nl;
            };

            if (false && i4fDpMax > 1000 && i4fDpCellIsGlobal)
            {
                i4fWriteOuterCell("DP_CELL", i4fDpLocalCell, i4fDpMax);
            }

            const bool i4fDAlphaCellIsGlobal =
                i4fDAlphaLocalCell >= 0
             && mag(i4fDAlphaLocalMax - i4fDAlphaMax)
                <= i4fDAlphaTieTolerance;
            if
            (
                i4fDAlphaMax > 0
             && false
             && i4fDAlphaCellIsGlobal
             && !(i4fDpCellIsGlobal
               && i4fDAlphaLocalCell == i4fDpLocalCell)
            )
            {
                i4fWriteOuterCell
                (
                    "ALPHA_CELL", i4fDAlphaLocalCell, i4fDAlphaMax
                );
            }

            Info<< "I4F_OUTER_STATE_DELTA"
                << " time_s=" << runTime.timeName()
                << " outer_iteration=" << i4fOuterLoop
                << " reference=start_of_this_outer_iteration"
                << " first_outer_reference=previous_time_step_state"
                << " max_abs_dp_Pa=" << i4fDpMax
                << " max_rel_dp=" << i4fDpRelMax
                << " max_abs_dU_m_s=" << i4fDUmax
                << " max_abs_dphi_m3_s=" << i4fDPhiMax
                << " max_abs_dalpha1=" << i4fDAlphaMax
                << " max_abs_dT_K=" << i4fDTMax
                << " max_abs_drho1_kg_m3=" << i4fDRho1Max
                << " max_abs_drho2_kg_m3=" << i4fDRho2Max
                << " scope=internal_cells_and_internal_faces"
                << nl << endl;
        }

        runTime.write();

        runTime.printExecutionTime(Info);
    }

    Info<< "End\n" << endl;

    return 0;
}


// ************************************************************************* //
