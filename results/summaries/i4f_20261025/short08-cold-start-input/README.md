# Shorter 0.8 m outlet: cold-start input preparation

This packet records an **input-only** preparation for the provisional SHORT2 layout: no post-rise straight, 0.8 m transition-and-mouth train, transition inlet x=3.8 m, mouth x=4.6 m. These lengths follow the user-directed geometry option; they are not measured from the photo. Tanks, upstream ports/valves and the rise bend are held fixed.

The staged startup dictionaries retain the baseline settings: `deltaT=10 µs`, `maxDeltaT=250 µs`, `maxCo=0.5`, `maxAlphaCo=0.25`, eight PIMPLE outer iterations, two correctors, `transonic yes`, `i4fFrozenPredictorSp false`, and kOmegaSST. These are prepared inputs, not a solver result.

Runtime controls are still legacy preparation values, including `i4fFrozenPredictorSp false`; this input case must be bound to the selected solver/source settings before launch. The [integration disposition](integration-disposition.json) records this hold and the inventory comparison.

The case has 317,814 cells. The generic/configured mesh check passes (all nine configured rows zero; max skewness 3.9133). The separate optional all-geometry check reports 7,141 concave cells/869 faces and remains a qualification. Every valve band has 5,376 fully wet cells and 48 axial layers.

Each tank starts with 1.350 m³ water at 293.15 K and 1.2 MPa absolute, with a wetted tank-to-valve feed. The native CAD tank capacity gives a 22.11% headspace-to-water ratio, versus the 22.5% nominal assumption. Downstream lines and mouths start air-filled at 100 kPa. The assumed 2% minimum valve opening is a numerical model assumption. The provisional pressure-only water EOS gives 3.202166 m³ total water and 3,198.008 kg initial water mass; that is 1.6063 kg above constant-998.2 kg/m³ mass because of the pressure-dependent density, mainly in the pressurized feeds/tanks.

All 14 time-zero field lists and six constant geometry fields were checked against the actual mesh count. Ten-way decomposition is bijective; the nine physical fields round-trip bit-exactly by global cell addressing, and cell-zone labels match. `p_rgh` was recomputed from the mixture EOS and gravity. The case has no solver binary or `dynamicCode` cache, and **no flow solver was launched**.

This mesh has a different cell count and extra local refinement from the 1.0 m train; this is not an accuracy-matched geometry comparison. The compact packet points to the private run bundle for the case and its preparation scripts; it does not contain the full mesh or constitute a standalone Git rebuild recipe. See `manifest.json` for exact source paths and hashes.

## Figures

- [Provisional four-outlet assembly](figures/provisional-assembly.png)
- [Horizontal tank connection section](figures/tank-connection-section.png)
- [Flush-at-inlet join sections](figures/flush-at-inlet-join-sections.png)
- [Transition cross sections](figures/transition-cross-sections.png)
- [Local divider mesh before the targeted repair](figures/mesh-before-local-repair.png)
- [Local divider mesh after the targeted repair](figures/mesh-after-local-repair.png)

The assembly/cross-section figures show provisional 4 mm CAD divider solids; CFD currently uses zero-thickness paired baffle walls. Root inspected the connection, cross sections and repaired local-mesh views. Native headspace differences between candidates are at most about 1.5e-8 relative, so bitwise mismatch alone is not an operational blocker; mesh and ambient-boundary sensitivities remain required.
