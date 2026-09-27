# E1 alpha capture map for pinned OpenFOAM v2512

This is a source-order map for a future reviewed instrumented build. It does
not modify OpenFOAM, run a solver, or authorize characterization. In the
candidate dictionary, `snapTol 0` disables the optional snap branch and `clip
true` enables clipping. Keep each stage's own extrema and out-of-range volume;
a valid postclip value does not clear a preclip violation.

| Capture name | Pinned source location and operation | Meaning |
| --- | --- | --- |
| `alpha_preclip` | `src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvectionTemplates.C`, after `limitFluxes(Sp, Su)` and the “After conservative bounding” state, before `applyBruteForceBounding()`; source SHA-256 `1d704aec280cffa4302f75cc3e15654db25dc75c6d1cb9e230ab8a4be64f1e90`. | Reconstructed alpha after conservative flux limiting and before snap/clip correction. Preserve its validity result even if the next stage repairs it. |
| `alpha_postclip` | `src/transportModels/geometricVoF/advectionSchemes/isoAdvection/isoAdvection.C`, immediately after `isoAdvection::applyBruteForceBounding()` returns. With `snapTol 0`, the source's snap branch is disabled; its clip branch clamps to `[0,1]` and corrects boundary conditions. Source SHA-256 `c2ed42ee16632e77b8aad9ff2adc87214cfd5c0a1b94387644e51aa2835b6380`. | Post-correction alpha. Name follows the review-4 note; do not label this as raw/conservative alpha. |
| `alpha_solver_final` | `applications/solvers/multiphase/interIsoFoam/alphaEqn.H`, after `advector.advect()` and the alpha subcycle/equation has completed for the outer correction. Source SHA-256 `cbb4348977388633b29f0aa1f612225249c3062e80755f548fddfb0760c7311f`; subcycle path `alphaEqnSubCycle.H` SHA-256 `b5f9845d57cb3fc75577ef00ed338186f83d13a9261c67d4ef88e6f1ef419385`. | Completed alpha state for that outer correction. With the current `nOuterCorrectors 1`, it is the candidate end-of-step state; any future coupling change requires remapping this capture. |

The conservative `alphaPhi_` transported flux is a separate output. In the
pinned advection template it is formed from face swept-volume flux divided by
`dt` after bounding; it is not the clipping correction. For each cell volume
`V_i`, retain the candidate corrections

```text
DeltaV_clip  = sum_i V_i * (alpha_postclip_i - alpha_preclip_i)
DeltaV_later = sum_i V_i * (alpha_solver_final_i - alpha_postclip_i)
```

in m^3, and report extrema, out-of-range cell count, and out-of-range volume
for all three named stages. The proposal's `[-1e-6, 1+1e-6]` bound is a
candidate integrity limit, not a paper tolerance or accepted gate. Any stage
violation remains visible and invalidates a future attempt if that candidate
limit is accepted. Never externally clip, renormalize, or discard
`alpha_preclip` before reporting it.

Pinned source version is the OpenCFD OpenFOAM v2512 image
`sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b`.
Source references: [isoAdvection template](https://api.openfoam.com/2512/isoAdvectionTemplates_8C_source.html),
[isoAdvection implementation](https://api.openfoam.com/2512/isoAdvection_8C_source.html),
[interIsoFoam alpha equation](https://api.openfoam.com/2512/alphaEqn_8H_source.html), and
[alpha subcycle](https://api.openfoam.com/2512/alphaEqnSubCycle_8H_source.html).
