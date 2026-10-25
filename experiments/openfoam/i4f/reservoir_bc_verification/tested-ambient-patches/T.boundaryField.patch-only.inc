// Insert these patch dictionaries under T.boundaryField in the private replay.
// T is the custom twoPhaseMixtureThermo shared temperature field; it is not a
// separately conserved phase-specific air temperature.
ambientAnnulus
{
    type inletOutletTotalTemperature;
    U U;
    phi phi;
    psi thermo:psi;
    gamma 1.399814036969217;
    T0 uniform 293.15;
    value uniform 293.15;
}
externalSides
{
    type inletOutletTotalTemperature;
    U U;
    phi phi;
    psi thermo:psi;
    gamma 1.399814036969217;
    T0 uniform 293.15;
    value uniform 293.15;
}
farOutlet
{
    type inletOutletTotalTemperature;
    U U;
    phi phi;
    psi thermo:psi;
    gamma 1.399814036969217;
    T0 uniform 293.15;
    value uniform 293.15;
}
