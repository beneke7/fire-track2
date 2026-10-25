# Experimental compressible reservoir boundary

These exact field templates compiled and ran in the small gas-only inflow and
flow-reversal verification using OpenCFD OpenFOAM v2512. They are not a complete
case. The example reservoir is **110 kPa absolute and 300 K**; the completed
I4F paired replay used **100 kPa absolute and 293.15 K**. Keep the two input
sets distinct.

The pressure code applies compressible stagnation-to-static conversion using
the registered `thermo:psi`, then subtracts the actual hydrostatic contribution
for `p_rgh`. `inletOutletTotalTemperature` preserves extrapolated outflow.
Runtime compilation uses the case owner's non-root UID. The completed paired
comparison applies the tested reservoir treatment only to its three open
external patches in the older one-tank/two-outlet reference. Its exact
patch-only dictionaries and run provenance are in
[`tested-ambient-patches/`](tested-ambient-patches/manifest.json). Do not use
these fragments to replace an entire field or infer validation of the updated
two-tank/four-outlet hardware; the full-apparatus reference remains a
static-ambient control.
