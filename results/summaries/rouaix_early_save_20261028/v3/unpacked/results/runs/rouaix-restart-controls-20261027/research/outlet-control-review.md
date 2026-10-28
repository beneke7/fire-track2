# Restart control research: outlet pressure vs coupling

Captured 2026-10-27 UTC. Read-only review for the 0.2→0.3 s full-grid matched restart pair. No case, code, or job was changed or launched.

## Recommendation

The repeated downstream/top/positive-spanwise corner failures in the original and upwind dry controls, and the fine-water failure with alpha near zero at the peak cell, make the open-boundary pressure treatment a direct first sensitivity. Test one restart sibling with `prghTotalPressure` on all four existing open pressure patches, leaving the other dictionaries and restart fields identical to the unchanged-static-pressure control.

Use **`p0 = 0 Pa gauge`** on the four existing open pressure patches, leaving all other restart inputs unchanged. This preserves the current outflow static-pressure gauge while switching reverse-flow faces to the `prghTotalPressure` energy relation. This is explicitly a backflow pressure-energy sensitivity, not a paper-matched ambient boundary condition. Minimal v2512 patch syntax:

```foam
 downstreamOutlet
 {
     type    prghTotalPressure;
     p0      uniform 0;
     rho     rho;
     U       U;
     phi     phi;
     value   uniform 0;
 }
```

Apply the same entry to `bottomOutlet`, `spanwiseMinus`, and `spanwisePlus`. `value` is the initial patch value; v2512 recalculates the boundary in `updateCoeffs()`. Use gauge pressure in Pa: the case solves `p_rgh` in Pa and the current `prghPressure p uniform 0` is atmospheric static gauge pressure. Do not supply 101325 Pa absolute pressure.

**Gauge clarification:** the installed v2512 relation is `p_rgh = p0 - 0.5*rho*neg(phi)*|U|^2 - rho*(g·Cf-ghRef)`. Changing `p0` by +2891 Pa adds the same constant to both flux-sign branches; it does not remove reverse-flow dynamic-head subtraction. With fixed-value pressure conditions on all four outlets, the incompressible pressure reference is inactive, so this constant is a gauge shift in this model, barring any absolute-pressure-dependent physics. At `p0=0`, reverse-flow air with `rho=1.18 kg/m3` and `|U|=70 m/s` reconstructs about −2.891 kPa static gauge pressure; nonzero normal velocity increases the dynamic term according to full `|U|^2`. Inspect patch-face static `p` alongside `phi`, `rho`, `U`, and `alpha`, especially downstreamOutlet and spanwisePlus at the known corner. Do not interpret either p0 choice as a measured or ambient-matched total pressure.

There is no uniform scalar `p0` that makes reverse-flow static pressure zero and simultaneously preserves zero outflow gauge in this branch relation. `p0=0` is preferred to preserve the existing outflow gauge and make the backflow dynamic-head subtraction explicit. `p0=2891` has the same pressure differences under the stated incompressible fixed-boundary setup; it merely shifts the common gauge.

If the experiment must preserve static zero on both directions, keep the pressure dictionaries and test `PIMPLE nOuterCorrectors 2` (with the existing `nCorrectors 3`). This is a reasonable coupling sensitivity, but not strictly a pressure-only change: installed v2512 `interIsoFoam` runs an outer PIMPLE loop, and `alphaEqnSubCycle.H` averages previous/current `phi` and `U` for alpha advection on later outer passes. It therefore changes both nonlinear coupling and interface flux treatment. The pressure arm above is the more direct boundary-localized diagnostic if its pressure shift is explicitly accepted.

## Verified current case values

- Current static outlet dictionaries are in `cases/e1_rouaix_case1_static/case/0/p_rgh:40-69`: `prghPressure`, `p uniform 0`, `rho rho` on downstream, bottom, and both spanwise exits.
- Current velocity entries are `cases/e1_rouaix_case1_static/case/0/U:39-69`: `pressureInletOutletVelocity`, `phi phi`, `tangentialVelocity uniform (70 0 0)`.
- `constant/g` is `(0 -9.81 0)` and `constant/hRef` is `0 m` in the same static case. `transportProperties` declares water density 997.6 and air density 1.18 kg/m3.
- The active HPC `fvSolution` template sets `nOuterCorrectors 1`, `nCorrectors 3`, `nNonOrthogonalCorrectors 0` (`cases/e1_rouaix_hpc/template/system/fvSolution:80-87`).
- The velocity BC projects the configured vector onto the patch tangent plane. Thus `(70,0,0)` is projected to zero on the x-normal downstream face; it remains 70 m/s tangent on y-normal bottom and z-normal spanwise faces. Its normal component is flux-derived for inflow; outflow uses zero gradient.

## Primary sources and exact installed-source receipts

Installed Komondor v2512 sources were read-only inspected under `/scratch/software/packages/openfoam/v2512-20251230/OpenFOAM-v2512/`:

| Source | Relevant lines | SHA-256 |
| --- | --- | --- |
| `src/finiteVolume/fields/fvPatchFields/derived/prghTotalPressure/prghTotalPressureFvPatchScalarField.C` | 142-178 (`neg(phi)`, local `rho`, `g`, `hRef`, `Cf`, dynamic term) | `59a5dd36e6c0fe75590a2d0ae07bf905e08e9a611bf33362b7a17388db803b72` |
| `src/finiteVolume/fields/fvPatchFields/derived/prghPressure/prghPressureFvPatchScalarField.C` | 136-161 (`p - rho*(g.Cf-ghRef)`) | `672bc7535cf6fd76357ebf311ca747c44ab221f2cca36a8bea5c511404c7577a` |
| `src/finiteVolume/fields/fvPatchFields/derived/pressureInletOutletVelocity/pressureInletOutletVelocityFvPatchVectorField.C` | 130-136 tangential projection; 170-184 flux sign | `b01263caab11b2c10139b18e5907f1a77bc04ef79f254377fa0483a926a0158b` |
| `src/finiteVolume/fields/fvPatchFields/derived/totalPressure/totalPressureFvPatchScalarField.C` | 163-175; dimensions and sign-conditioned dynamic correction, but no `gh` conversion | `9aa6d85e8e8ca958847c5a5b5793aeb85541c1fa213c79c2fd0218bffebb63dd` |
| `applications/solvers/multiphase/interIsoFoam/interIsoFoam.C` | 112-115, PIMPLE outer loop | `60419acc76a1df4d81238a272f599f498ecbb584c0dcb45e5677748a4ae72379` |
| `applications/solvers/multiphase/interIsoFoam/alphaEqnSubCycle.H` | 1-27, later outer-pass alpha flux/velocity averaging | `b5f9845d57cb3fc75577ef00ed338186f83d13a9261c67d4ef88e6f1ef419385` |

OpenCFD primary docs: [v2512 prghTotalPressure header/API](https://api.openfoam.com/2512/prghTotalPressureFvPatchScalarField_8H_source.html) (definition and `p0` usage, lines 32-71), [v2512 prghTotalPressure implementation](https://api.openfoam.com/2512/prghTotalPressureFvPatchScalarField_8C_source.html) (flux-conditioned correction, lines 142-178), [v2512 prghPressure implementation](https://api.openfoam.com/2512/prghPressureFvPatchScalarField_8C_source.html) (static pressure/gravity/reference, lines 136-161), and [v2512 pressureInletOutletVelocity implementation](https://api.openfoam.com/2512/pressureInletOutletVelocityFvPatchVectorField_8C_source.html) (tangent projection and flux direction, lines 130-184). The versioned [OpenCFD prghPressure documentation](https://doc.openfoam.com/2306/tools/processing/boundary-conditions/rtm/derived/general/prghPressure/) describes its hydrostatic/static-pressure mapping; [OpenCFD totalPressure documentation](https://doc.openfoam.com/2306/tools/processing/boundary-conditions/rtm/derived/inletOutlet/totalPressure/) describes total/static pressure modes. The installed v2512 implementation controls the exact version-specific behavior above.

## Applying the dictionary to an isolated restart branch

The loaded Komondor v2512 `changeDictionary -help` exposes `-parallel` and `-fileHandler`. Its installed source `applications/utilities/parallelProcessing/changeDictionary/changeDictionary.C` (SHA-256 `49fa8466d04568e339c421c2a032fa16ee7fc8ad6f64c2ad4f20cf59acb7e920`) reads and writes field dictionaries through normal per-processor I/O. The intended command shape is `srun -n 120 changeDictionary -parallel -fileHandler collated -case <new-branch> -time 0.2 -dict system/changeDictionaryDict`, under the branch runner's loaded OpenFOAM environment. In that dictionary's `boundaryField`, repeat the shown entry for each of the four open pressure patches. Apply it only to an independent branch copy, never to the donor checkpoint or a hard-linked writable tree; capture source and resulting dictionary hashes. This describes supported native parallel I/O; no remote field mutation was performed during this review.
