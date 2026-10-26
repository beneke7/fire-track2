volScalarField::Internal Sp
(
    IOobject
    (
        "Sp",
        runTime.timeName(),
        mesh
    ),
    mesh,
    dimensionedScalar(dgdt.dimensions(), Zero)
);

volScalarField::Internal Su
(
    IOobject
    (
        "Su",
        runTime.timeName(),
        mesh
    ),
    mesh,
    dimensionedScalar(dgdt.dimensions(), Zero)
);

forAll(dgdt, celli)
{
    if (dgdt[celli] > 0.0)
    {
        Sp[celli] -= dgdt[celli]/Foam::max(1.0 - alpha1[celli], 1e-4);
        Su[celli] += dgdt[celli]/Foam::max(1.0 - alpha1[celli], 1e-4);
    }
    else if (dgdt[celli] < 0.0)
    {
        Sp[celli] += dgdt[celli]/Foam::max(alpha1[celli], 1e-4);
    }
}

// Read-only local diagnostics: record the dgdt source actually assembled for
// the phase-fraction equation at the two valve control volumes. This adds no
// reductions, field corrections, or equation terms.
++i4fAlphaSuSpCallIndex;
if (Pstream::myProcNo() == 2)
{
    const label i4fAlphaDiagCells[] = {2684, 2752};
    for (const label i4fCell : i4fAlphaDiagCells)
    {
        if (i4fCell >= mesh.nCells()) continue;
        const scalar i4fAlpha = alpha1[i4fCell];
        const scalar i4fDgdt = dgdt[i4fCell];
        const scalar i4fDenom =
            i4fDgdt > 0
          ? Foam::max(1.0 - i4fAlpha, scalar(1e-4))
          : Foam::max(i4fAlpha, scalar(1e-4));
        const bool i4fDenomFloorActive =
            i4fDgdt > 0 ? (1.0 - i4fAlpha < 1e-4) : (i4fAlpha < 1e-4);
        std::ofstream i4fAlphaSourceLog("alpha-su-sp-rank2.log", std::ios::app);
        i4fAlphaSourceLog << std::setprecision(17)
            << "I4F_ALPHA_SUP_SP"
            << " time_s=" << runTime.timeName()
            << " time_index=" << runTime.timeIndex()
            << " outer_iteration=" << i4fOuterLoop
            << " alpha_source_call_index=" << i4fAlphaSuSpCallIndex
            << " rank=" << Pstream::myProcNo()
            << " local_cell=" << i4fCell
            << " alpha_water_before_update=" << i4fAlpha
            << " alpha_gas_before_update=" << 1.0 - i4fAlpha
            << " dgdt_branch="
            << (i4fDgdt > 0 ? "positive" : (i4fDgdt < 0 ? "negative" : "zero"))
            << " dgdt_per_s=" << i4fDgdt
            << " Su_per_s=" << Su[i4fCell]
            << " Sp_per_s=" << Sp[i4fCell]
            << " Su_plus_Sp_alpha_per_s="
            << Su[i4fCell] + Sp[i4fCell]*i4fAlpha
            << " dt_s=" << runTime.deltaTValue()
            << " dt_Su=" << runTime.deltaTValue()*Su[i4fCell]
            << " dt_Sp=" << runTime.deltaTValue()*Sp[i4fCell]
            << " dt_source_net="
            << runTime.deltaTValue()*(Su[i4fCell] + Sp[i4fCell]*i4fAlpha)
            << " denominator_used=" << i4fDenom
            << " denominator_floor_active=" << i4fDenomFloorActive
            << std::endl;
    }
}

volScalarField::Internal divU
(
    mesh.moving()
  ? fvc::div(phiCN() + mesh.phi())
  : fvc::div(phiCN())
);
