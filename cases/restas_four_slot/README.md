# Four-slot OpenFOAM characterization case

This is a **CPU VOF solver characterization pilot**, not E1–E6 validation and
not a prediction for the built I4F/Restás system. It runs in the local
`opencfd/openfoam-default:2512` Docker image, using OpenFOAM `interIsoFoam`.
The host RTX 5090 is not used by this solver.

The generated mesh has 2,081,200 cells in a 15.95 m × 6.05 m × 4 m domain.
It places four separate slot patches in a 2 × 2 arrangement on a flat plate.
The provisional slots are 1.0 m × 0.15 m, with 0.05 m gaps in both array
directions. Those dimensions and gaps come from the project plan and pilot
choices; no local paper or measured device record supplies the built geometry.
The short slot axis is along-track, the long axis is cross-track. The mesh has
three cells across each 0.15 m slot and is only a cost/boundary-condition pilot.

The pilot prescribes water at 4.8 m/s normal to the outlet for 0.08 s, then
stops it. The speed is borrowed from the Calbrix Dash-8 nearfield case as an
explicit provisional source value, not a measured Restás discharge. The
aircraft-frame crossflow is 50 m/s from Calbrix. Room-temperature water/air
properties and gravity are listed in the generated run manifest. This short
case injects 230.4 kg of water. It has no aircraft, wake, ground, parcel
handoff, foam, or fire model and cannot determine `L95`, useful fraction, or a
design gain.

Run with `make restas-pilot`. Each execution creates a new directory under
`results/runs/`, records code/input/image hashes and resource limits, checks the
mesh, runs the transient VOF case, and writes liquid-interface VTP surfaces at
declared times. Do not interpret the unrefined three-cell slot width or short
physical-time window as resolved breakup evidence.
