# Experimental compressible reservoir boundary

These exact field templates compiled and ran in the small gas-only inflow and
flow-reversal verification using OpenCFD OpenFOAM v2512. They are not a complete
case. The example reservoir is **110 kPa absolute and 300 K**; the ongoing I4F
paired replay instead uses 100 kPa and 293.15 K. Do not silently substitute one
for the other.

The pressure code applies compressible stagnation-to-static conversion using
the registered `thermo:psi`, then subtracts the actual hydrostatic contribution
for `p_rgh`. `inletOutletTotalTemperature` preserves extrapolated outflow.
Runtime compilation uses the case owner's non-root UID. The full-apparatus
reference dictionaries retain the static-ambient control: the reservoir
alternative is still under controlled comparison, not promoted or validated.
