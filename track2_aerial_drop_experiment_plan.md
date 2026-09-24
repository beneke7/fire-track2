# Track 2 — constant-velocity release to useful ground strip

**Working plan · 24 September 2026**

## Objective and first assumption

Build a conservative, multiregion water–air simulation that predicts an aerial drop from outlet to ground. Use the **same exterior physics and scoring code** to compare a conventional release with the built Restás/i4f architecture. Deliver numerical comparisons, uncertainty ranges, and a scientifically labelled 3D animation.

The first Restás source is **four closely arranged outlets in a 2 × 2 layout**, each with a prescribed constant outlet *velocity vector* during a finite release, followed by an abrupt stop. Approximate slot dimensions discussed so far are **about 1 m × 0.10–0.15 m each**, pending measurements. These are provisional inputs, not measured specifications. For water of density \(\rho\), total released mass is \(M_0=\rho A_{\rm total}|v_n|T\); choose release duration \(T\) to match the specified payload. Vary outlet direction independently of speed. Start with water-like properties; introduce measured foam properties and time-dependent discharge in subsequent runs. This first model tests what a controlled outlet *could* achieve in flight; it does not establish that a pressurized tank maintains the prescribed velocity.

## The comparison we will report

Specify one scenario **before** optimization: released mass \(M_0\), aircraft speed and height, wind, fire-derived target width \(W\), and water-equivalent ground coverage threshold \(C_*\). The motivating Restás example uses approximately \(W=9\) m and \(C_*=2.4\) kg/m²; actual fire scenarios need separately justified thresholds. Use the deposited-mass map \(C(x,y)\), including its sampling resolution, for every design.

- For each along-track position, measure the fraction of the prescribed width with \(C(x,y)\ge C_*\). **\(L_{95}\)** is the longest continuous along-track interval for which at least **95% of that width** passes the threshold at every section. The 95% rule is an initial declared engineering tolerance; publish sensitivity to it and to map resolution.
- **Useful ground fraction:** \(f_{\rm useful}=\frac{C_*}{M_0}\int_{I_{95}}\int_{-W/2}^{W/2}\mathbf{1}[C(x,y)\ge C_*]\,dy\,dx\). This counts only threshold-satisfying cells inside the longest valid strip, caps credit at the required dose, and penalizes gaps and excess application. Also report \(L_{95}\), actual mass inside that strip, mass elsewhere on the ground, and mass crossing the outer domain boundaries. Keep Gu's *collected ground fraction* as a distinct metric.
- **Improvement claim:** \(G=L_{95,\rm Restás}/L_{95,\rm control}\) at the same \(M_0,W,C_*,H,U\), environmental forcing, and numerical resolution. Report \(G\) alongside \(f_{\rm useful}\), rather than transferring a historical ground-fraction percentage into a fourfold claim.

First run a **matched counterfactual**: conventional and shaped outlet in the same flight environment, altering only the release. Then run **operational comparisons** at each aircraft's realistic flight conditions; keep these results in a separate table. The Restás paper's ellipse-to-rectangle example gives only about **1.6×** length at its illustrated 9 m width if qualifying area is merely reshaped; a larger gain must be accounted for by changes in delivered, correctly placed, or excess mass.

## Solver architecture and conservation contract

| Region | Physics and numerical task | Data handed forward |
| --- | --- | --- |
| **A — outlet and coherent nearfield** | Three-dimensional incompressible water–air VOF. Fixed source in the aircraft frame, prescribed relative airflow, gravity, initially simplified aircraft geometry. Resolve the slots and coherent liquid sheets; include aircraft/rotor flow later where relevant. | Time-stamped liquid volume fraction, liquid velocity, momentum and flux on a downstream interface. |
| **B — expanding plume** | Refined VOF while connected liquid and large structures dominate. Test a moving refined window or local mesh refinement against a fixed-grid reference. | Connected structures stay VOF. Transfer only resolvable detached structures or a calibrated unresolved-size spectrum to parcels. |
| **C — descent** | Advect resolved VOF if affordable. Otherwise, Lagrangian parcels with drag, gravity, wind and checked breakup/dispersion; add two-way air coupling when loading requires it. Test an overlap region where both representations run on identical incoming data. | Time, position, velocity and **mass flux** through a ground-intercept plane, including mass outside the collection area. |
| **D — ground diagnostic** | Conservative flux accumulation into \(C(x,y)\), keeping the original impact locations and weights; transform from aircraft-frame positions to ground coordinates at each impact time. | Ground map, contours, strip metrics, mass ledger, and visualization files. |

VOF-to-parcel conversion must conserve released **mass and momentum** across the transfer plane; record mass that remains in VOF, enters parcels, deposits, or exits the domain without deposition. Run one **direct VOF descent attempt** for the coherent Restás plume before deciding its handoff location. Choose that location by stability of the **ground map and \(L_{95}\)**, not by how smooth a rendered plume looks. Unresolved mist is an uncertainty and cannot be silently painted into the animation as computed droplets.

## Experiments, in execution order

| ID | Experiment | Recorded result and decision |
| --- | --- | --- |
| **E0** | Analytical and grid checks: constant inlet flux, a ballistic no-wind trajectory, ground-frame coordinate mapping, mass conservation, and Restás's ellipse/rectangle arithmetic. | Correct mass ledger and scoring code before CFD. |
| **E1** | **Constant-velocity round water jet in crossflow**, following one accessible case from Rouaix et al. (large-diameter 0.2–0.6 m VOF study). | Compare penetration, lateral expansion and breakup location with the published numerical curves. Solver implementation check, **not field validation**. Obtain full paper for exact initial and boundary conditions. |
| **E2** | **Calbrix Dash-8 nearfield water case**: 50 m/s relative airflow; begin with constant outlet speed around the reported 4.8 m/s peak. Extract core (\(\alpha\ge0.9\)), dilute-envelope (\(\alpha\ge0.001\)), penetration and lateral-width curves corresponding to Figs. 5–9. | Compare morphology and trends; the paper uses \(v(t)\), so the constant-source snapshots are not exact reproductions. Subsequently replay the paper's discharge history to check its timed figures. Fig. 8's text and caption specify different times: record the choice. |
| **E3** | **Conventional geometric control:** add Calbrix CL-415's four-release geometry and its published outlet histories, first for nearfield behavior. | Check the reported relative width and penetration against the Dash-8 under its specified conditions. Preserve one case without fit adjustments. |
| **E4** | **Ground transport check:** Amorim's measured **M134 water** pattern (4.64 m³, mean flow 2.04 m³/s, 60.66 m height, 67.90 m/s aircraft speed, 2.68 m/s wind). Compare Fig. 4 coverage-contour shapes, lengths/areas and Fig. 9 cumulative along-track volume. | Field-based check of the descent/ground stage. Digitized curves and uncertain aperture/discharge imply a stated approximation until raw trial data are obtained. Use the published 5.5 and 7.5 gpc contours to bracket the illustrative 2.4 kg/m² water target. |
| **E5** | Check the ground-map integration and collection convention against **Gu's six AG600 measured ground fractions (roughly 41–44%)** when their matching release conditions can be reconstructed. | Sanity check on collected fraction; distinguish measured fractions from the paper's reconstructed estimates and from our useful-strip fraction. |
| **E6** | **Restás versus conventional matched comparison:** equal payload, water properties, flight speed, height, wind, and ground scoring; run ideal four-slot constant outlet versus conventional source, then vary velocity vector, release duration, height and crosswind. | \(L_{95}\), \(f_{\rm useful}\), maps, ground mass ledger, sensitivity intervals. Repeat decisive cases with measured foam properties and outlet traces when available. |

E1–E3 establish the nearfield solver. E4–E5 constrain the route to a measured ground map. A close match to E1–E3 alone is insufficient evidence for a fourfold **ground** result; E6 is the actual design test.

## Compute gates: 5090, 20-core workstation, later CPU cluster

1. **Pilot on the RTX 5090 (32 GB):** run a GPU-capable VOF implementation on an idealized box with roughly **1–3 million cells** and a few hundred steps. Measure peak device memory, time per step, time-step limit, interface/mass error, pressure-solver share, and file-output cost. FluTAS is a candidate for a simple box; support for the prescribed four-slot inlet, crossflow and aircraft boundaries needs confirmation. Do not assume a CPU OpenFOAM VOF case runs on GPU unchanged.
2. **Extrapolate before large runs:** estimate wall time to one physical second, projected peak memory and checkpoint size; attempt **5–10 million cells** only if the pilot and boundary conditions permit. Run two nearfield resolutions; a third is warranted where penetration, transfer flux, or \(L_{95}\) still changes substantially. The 20-core Ultra 7 265K can run small independent CPU reference cases and process outputs.
3. **Use the ~1300 CPU cores for decisions that require them:** complex aircraft geometry, local refinement, direct-VOF-to-ground trials, and selected converged control/design comparisons. Profile a short CPU partition, memory per rank and scaling first. A full 60 m descent resolved everywhere at centimetre scale is outside the 5090 budget: a uniform 10 × 10 × 30 m domain at 1 cm already contains **3 billion cells**.
4. **Keep cost observable:** checkpoint short runs, write compact ground maps and transfer-plane records routinely, and save full 3D fields only at chosen render times. Every run logs input geometry/physics, code revision, grid, seeds, wall time, memory, conservation error, and reason to advance or stop.

## Validation, inputs, and final visual

**Minimum measured input packet:** actual four-slot geometry and spacing; water/foam density, rheology and surface behavior; valve opening and flow/pressure-versus-time traces; release payload, attitude, aircraft speed and altitude; wind; test videos with camera geometry and timestamps. Foam and CO₂ aeration may require an effective-property or additional-phase model: quantify sensitivity instead of treating water-only results as foam validation. No flame or ground-after-impact dynamics is claimed in this version.

**Deliverables:** (1) a reproducible multiregion solver and case definitions, (2) paper-benchmark overlays with numerical errors and a mass ledger, (3) side-by-side conventional/Restás ground maps and continuous-strip performance across wind, height and coverage thresholds, and (4) a **15–30 s 3D animation**. Build the scientific animation in ParaView from time-stamped VOF surfaces, large resolved structures, mass-weighted parcels and the accumulated ground map; use Blender only for optional presentation. Lock the camera, flight conditions, scale, colour mapping and playback time across the two designs. Overlay the prescribed target rectangle and the measured \(L_{95}\). Label simulated droplets, inferred subgrid mist, and actual test footage separately; the picture illustrates the computed mechanism, while the ground map carries the quantitative claim.

**Interpretation rule:** the first paper-ready statement is “Under specified constant-source assumptions, this pipeline predicts \(G\) with these numerical and source uncertainties.” Stronger statements about the **built** system require its measured outflow/foam properties and at least one independent deposition or calibrated plume comparison.

### References for the benchmark cases

- [Restás (2023), footprint geometry and firebreak requirement](https://doi.org/10.3390/fire6090351).
- [Legendre et al. (2014), air tanker drop patterns](https://doi.org/10.1071/WF13029).
- [Rouaix et al. (2023), large-diameter constant-inlet jets](https://doi.org/10.1016/j.ijmultiphaseflow.2023.104419).
- [Calbrix et al. (2023), CL-415 and Dash-8 VOF](https://doi.org/10.1071/WF22147).
- [Amorim (2011), Part II measured ground-map validation](https://doi.org/10.1071/WF09123).
- [Gu et al. (2023), collected ground fraction](https://doi.org/10.1071/WF22055).
- [FluTAS GPU VOF implementation](https://github.com/Multiphysics-Flow-Solvers/FluTAS).
