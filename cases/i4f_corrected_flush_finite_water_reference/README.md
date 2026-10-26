# Corrected flush finite-water reference capsule

This is a compact record of the corrected-flush, finite-water case inputs. It is **not a standalone or runnable OpenFOAM case**.

## What these files represent

The 18 text dictionaries under system/ and constant/ are copied byte-for-byte from the pre-GO freeze for results/runs/i4f-finite-water-eos-halfdt-stage01-20261026T131840Z. Each selected file matches its path, byte count, and SHA-256 entry in the included original freeze manifest. This is the half-dt continuation stage: its case starts from the saved native checkpoint at 0.05001058333202217 s and targets 0.46 s. The finite-water cold t=0 source case and its confirmed pilot are identified separately in the water overlay records.

The stage uses deltaT=5e-6 s, maxDeltaT=1.25e-4 s, maxCo=0.25, and maxAlphaCo=0.125; its full-field write interval remains 0.05 s. Relative to the matched stage controls, the four time/Courant values are halved. The three ambient-patch VTK field exports are disabled; scalar diagnostics, native snapshots, and the four-mouth observer remain configured. The actual dictionaries preserve the Euler time scheme, MULES phase-fraction controls, Gauss linearUpwind grad(U) for momentum, eight PIMPLE outer correctors, two pressure correctors, and SST turbulence.

The actual control metadata selects the standard phase-source update: i4fFrozenPredictorSp is false and the run record says Sp_mode is “standard source update.” The executable keeps its historical compressibleInterFoamFrozenAlphaSourceV2NoPout filename. Its recorded DCEC binary SHA-256 is dcecb2950004d7c133f1433bba00b619649468ec373072f73aed48ae390be0b5. The source reconstruction link is in the project solver snapshot README and solvers/i4f_frozen_sp/variants/dcec/variant-manifest.json.

## Physical source state

The source is a true cold t=0 state with a nominal tank pressure setting of 12 bar absolute, 1.35 m³ water per tank, 20 °C initial temperature, ideal-gas air, and finite-pressure-density water. The native initial absolute-pressure field spans 100000.0 to 1211011.7118868 Pa across the ambient and hydrostatic field; 12 bar is not a uniform field value. The downstream passages after the valves start as ambient air; tank-to-valve feeds are wetted. The matched water dictionary uses OpenFOAM adiabaticPerfectFluid with the recorded rho0=998.2 kg/m³, c0=1482.3443444561285 m/s, B=306667767.13022316 Pa, and provisional assumed exponent gamma=7.15. The source readiness record reports 3198.008370828796 kg of finite-EOS water in 3.202165993106066 m³ total water inventory, including the two tank inventories and wetted feeds. These values describe the provisional source case and EOS, not measured apparatus performance.

## Geometry and aperture qualification

The CFD mesh uses zero-thickness divider mid-surfaces as internal baffle faces. The saved mesh geometry record explicitly marks the assumed 4 mm BREP divider plates as display solids, not mesh walls; the mesh-preparation log records conversion of 8552 faces into boundary faces. The recorded native gross mouth area is 0.15 m² per outlet; the BREP geometry summary gives a nominal clear area of 0.1476 m² after subtracting the assumed divider thickness. These are different definitions. Since the CFD dividers are zero-thickness surfaces, native full-plate/open-area equivalence has not been established here. Reconcile the four outlet-plane openings and the existing native-versus-BREP volume comparison before treating the matched 0.8 m CFD geometry as equivalent. The exact source-record hashes are listed in provenance/mesh-and-source-links.json.

## Phase-temperature startup fields

The pre-GO T.air and T.water hashes identify the original parent checkpoint at 0.050010583332 s and match that immutable checkpoint. After GO, the OpenFOAM v2512 twoPhaseMixtureThermo constructor rewrote both phase-temperature fields from common T and materialized their physical-patch values. They are derived startup outputs, not independent prescribed inputs; their post-startup hashes therefore differ from the pre-GO hashes. The read-only review is included at provenance/startup-phase-temperature-review.json (SHA-256 e7059e97646db96a409d1b0cd305332555346f0ba0bb97f05cca24f9aafaed36). This capsule omits those field files and does not claim that every current live restart file matches the pre-GO freeze.

## Required files for reuse

A runnable continuation also needs the exact frozen native mesh, its cell/face zones and 10-rank addressing, the native restart checkpoint fields and uniform/time, plus the corresponding mapping/decomposition files. Those large files are deliberately absent. Their frozen hashes are recorded for transfer checks in provenance/run-source-lock.json and provenance/original-pre-go-input-freeze.json. The water t=0 readiness metadata is not a substitute for the omitted t=0 fields or the half-dt restart checkpoint.

The mesh record has multiple scopes. The active 299214-cell mesh identity is the one in the pre-GO freeze and mesh-load preflight. meshPreparationProvenance.json also retains earlier base-mesh hashes; mesh-and-source-links.json documents how those hashes relate to the saved mesh preparation history and which exact transition remains unproven. No mesh files or CAD/STL/cache are included.

The cold pilot reached an early checkpoint, and the half-dt continuation metadata records a target end time. This capsule contains no claim that the continuation completed, that the CFD is validated, or that the provisional geometry and EOS are measured physical facts.
