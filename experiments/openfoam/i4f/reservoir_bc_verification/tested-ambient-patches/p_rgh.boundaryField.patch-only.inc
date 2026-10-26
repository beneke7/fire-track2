// Insert these patch dictionaries under p_rgh.boundaryField in the private
// replay only. They map an ideal-air reservoir p0 to isentropic static p,
// then subtract the OpenFOAM hydrostatic term to form p_rgh.
ambientAnnulus
{
    type codedFixedValue;
    name i4fCompressibleAmbientReservoirPRgh;
    value uniform 100000;
    codeInclude
    #{
        #include "fvCFD.H"
        #include "gravityMeshObject.H"
    #};
    code
    #{
        const scalar p0 = 100000.0;
        const scalar gamma = 1.399814036969217;
        const scalar gM1ByG = (gamma - 1.0)/gamma;
        const vectorField& Up = patch().lookupPatchField<volVectorField>("U");
        const scalarField& phip = patch().lookupPatchField<surfaceScalarField>("phi");
        const scalarField& psip = patch().lookupPatchField<volScalarField>("thermo:psi");
        const scalarField& rhop = patch().lookupPatchField<volScalarField>("rho");
        const uniformDimensionedVectorField& g = meshObjects::gravity::New(db().time());
        const uniformDimensionedScalarField& hRef =
            db().lookupObject<uniformDimensionedScalarField>("hRef");
        const scalar ghRef =
            mag(g.value()) > SMALL
          ? (g.value() & ((cmptMag(g.value())/mag(g.value()))*hRef.value()))
          : 0.0;
        const scalarField pStatic =
            p0/pow(1.0 + 0.5*psip*gM1ByG*neg(phip)*magSqr(Up), 1.0/gM1ByG);
        operator==(pStatic - rhop*((g.value() & patch().Cf()) - ghRef));
    #};
}
externalSides
{
    type codedFixedValue;
    name i4fCompressibleAmbientReservoirPRgh;
    value uniform 100000;
    codeInclude
    #{
        #include "fvCFD.H"
        #include "gravityMeshObject.H"
    #};
    code
    #{
        const scalar p0 = 100000.0;
        const scalar gamma = 1.399814036969217;
        const scalar gM1ByG = (gamma - 1.0)/gamma;
        const vectorField& Up = patch().lookupPatchField<volVectorField>("U");
        const scalarField& phip = patch().lookupPatchField<surfaceScalarField>("phi");
        const scalarField& psip = patch().lookupPatchField<volScalarField>("thermo:psi");
        const scalarField& rhop = patch().lookupPatchField<volScalarField>("rho");
        const uniformDimensionedVectorField& g = meshObjects::gravity::New(db().time());
        const uniformDimensionedScalarField& hRef =
            db().lookupObject<uniformDimensionedScalarField>("hRef");
        const scalar ghRef =
            mag(g.value()) > SMALL
          ? (g.value() & ((cmptMag(g.value())/mag(g.value()))*hRef.value()))
          : 0.0;
        const scalarField pStatic =
            p0/pow(1.0 + 0.5*psip*gM1ByG*neg(phip)*magSqr(Up), 1.0/gM1ByG);
        operator==(pStatic - rhop*((g.value() & patch().Cf()) - ghRef));
    #};
}
farOutlet
{
    type codedFixedValue;
    name i4fCompressibleAmbientReservoirPRgh;
    value uniform 100000;
    codeInclude
    #{
        #include "fvCFD.H"
        #include "gravityMeshObject.H"
    #};
    code
    #{
        const scalar p0 = 100000.0;
        const scalar gamma = 1.399814036969217;
        const scalar gM1ByG = (gamma - 1.0)/gamma;
        const vectorField& Up = patch().lookupPatchField<volVectorField>("U");
        const scalarField& phip = patch().lookupPatchField<surfaceScalarField>("phi");
        const scalarField& psip = patch().lookupPatchField<volScalarField>("thermo:psi");
        const scalarField& rhop = patch().lookupPatchField<volScalarField>("rho");
        const uniformDimensionedVectorField& g = meshObjects::gravity::New(db().time());
        const uniformDimensionedScalarField& hRef =
            db().lookupObject<uniformDimensionedScalarField>("hRef");
        const scalar ghRef =
            mag(g.value()) > SMALL
          ? (g.value() & ((cmptMag(g.value())/mag(g.value()))*hRef.value()))
          : 0.0;
        const scalarField pStatic =
            p0/pow(1.0 + 0.5*psip*gM1ByG*neg(phip)*magSqr(Up), 1.0/gM1ByG);
        operator==(pStatic - rhop*((g.value() & patch().Cf()) - ghRef));
    #};
}
