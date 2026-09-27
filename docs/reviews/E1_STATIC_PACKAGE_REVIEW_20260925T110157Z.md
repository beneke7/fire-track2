# E1 static package review — 2026-09-25 11:01:57 UTC

**Disposition: REVISE for static-package readiness.** This independent Astra Max
read-only review does not approve characterization, E1 execution, E2
advancement or any scientific gate. It is separate from Warden checkpoint 7.

The following identities matched at review opening and closing:

| Artifact | SHA-256 |
|---|---|
| `cases/e1_rouaix_case1_static/static_preparation.py` | `fe4dea35db0a2fb1abe472dc87d83daaab9d1e39cb928e7b4a64f904d6bd40ff` |
| `cases/e1_rouaix_case1_static/prepare_case.py` | `f77c2283c51e7680de9025b4781faa64d03167b14c7244d5ea9948392f815418` |
| `cases/e1_rouaix_case1_static/CASE_SHA256SUMS` | `2c666af4a39b280f73919456b4df7bc92490fe92f3388a251de6a4f8af8772f9` |
| `cases/e1_rouaix_case1_static/ALPHA_CAPTURE_MAP.md` | `c0e8e1d3f51e3b0ac683039443a59a5fd07ad0f64656fcb488df469ce33abefd` |
| `tests/test_e1_rouaix_case1_static.py` | `ce176a4ad33ec30b7bac2dabf3f49c86122e0ac6def2e5c8e3195c6fb615bdeb` |
| `experiments/E1_ROUAIX_CASE1_STATIC_PREPARATION.md` | `d9177d9cecdcff5016e623aca117f32e9b82cd2908cde4284fab65ad55b9378a` |
| Accepted gate draft | `15a9b4a48df3f8b059b98961d92cd89bdc8b69ffe1f66beaa81f936167ffe3ea` |
| Accepted capability audit | `a6c655abbf58eff6bb71850fbed8612ece459c891ad9e21b4f5d3ddf7e7fcb32` |
| Review 4 | `7c01b1262d305e3c131bb40f5cb43f0c9cc276d0b851002f1ffdffdaf39fcdbb` |

All 20 case/geometry manifest entries independently passed read-only SHA-256
verification. This confirms archived bytes only; it does not establish correct
dictionaries or regeneration determinism.

## Required corrections

1. **High — density selection and numerical schemes do not implement the
   accepted baseline.** `case/constant/turbulenceProperties` omits top-level
   `density variable;`, while `case/system/fvSchemes` provides only `rhoPhi`
   convection keys under `default none`. Gate line 156 and audit lines 70–73
   pair variable-density turbulence with those keys. Archived E1 review 3
   records the pinned v2512 selector at
   `incompressibleInterPhaseTransportModel.C:43–108`: without an explicit
   choice the model defaults to uniform density and the `phi` branch. Add the
   declared density choice in both generator and dictionary. The same
   `divSchemes` block lacks the accepted viscous-divergence `Gauss linear`
   entry; obtain and pin the exact operator/key from the selected transport
   path. Add negative static checks for both omissions.

2. **High — alpha controls are outside `solvers`, and reconstruction differs
   from the accepted method.** In `case/system/fvSolution`, `solvers` closes
   before the `"alpha.*"` block; the block selects `plicRDF`, while accepted
   gate line 156 specifies `isoAlpha`. The generator repeats both issues. Put
   the alpha block inside `solvers`, retain explicit `clip true`, `snapTol 0`
   and one subcycle, and restore `reconstructionScheme isoAlpha` unless the
   primary prospectively amends the method. Archive the pinned
   `mesh.solverDict(alpha1.name())` lookup with the correction evidence. This
   review did not freshly rehash that source body; the package records
   `isoAdvection.C` SHA-256
   `c2ed42ee16632e77b8aad9ff2adc87214cfd5c0a1b94387644e51aa2835b6380`.
   Add nesting and method regression checks.

3. **High — plane sampling does not enable the specified interpolation.**
   `controlDict` declares `interpolationScheme cellPoint`, but every sampling
   plane omits `interpolate true;`. The v2512 API says the interpolation scheme
   applies only when a surface enables interpolation; the plane implementation
   distinguishes face sampling from point interpolation. Therefore the
   current dictionary does not provide the vertex-valued contour required by
   gate lines 192–199. Add `interpolate true` to every plane and assert it in
   the static checker, which currently checks only the scheme, position,
   normal and triangulation. See [v2512 sampledSurfaces
   API](https://api.openfoam.com/2512/classFoam_1_1sampledSurfaces.html) and
   [sampledPlane source](https://api.openfoam.com/2512/sampledPlane_8C_source.html).

4. **Medium — the wall is an assumed analytic surface, not the prospectively
   specified Figure 3 trace.** The generator chooses `A=0.080 m`,
   `Lx=Lz=0.800 m` for an analytic surface and the note properly identifies
   those as assumptions. Gate line 152 instead requires a Figure 3 trace,
   source image, point/scale transform and hashes, or a prospective replacement
   amendment. Supply the trace evidence or have the primary explicitly amend
   the baseline to the idealized analytic wall before freezing. Existing
   provisional-input authorization permits this work; no user permission is
   needed.

5. **Medium — nozzle-face selection is not constrained to the aircraft-wall
   boundary.** `topoSetDict` selects faces in a cylinder, and `createPatchDict`
   consumes the set as a boundary patch. Freeze an intersection with
   `aircraftWall` and the utility order, particularly relative to refinement
   and layers. The selection does not establish boundary-only membership; no
   mesh was run. The v2512 `createPatch` utility is for boundary faces; see the
   [official v2512 utility listing](https://api.openfoam.com/2512/files.html).

Update both generator and generated dictionaries. The checker does not
currently validate the turbulence/solver/scheme contract, so its pass cannot
detect findings 1–2. Add focused malformed-dictionary fixtures as well as
valid-package assertions.

## Additional limits and confirmed items

- `prepare_case.py` hashes every existing file under the case/geometry
  directories. Sorted enumeration is deterministic for a clean tree, but stale
  extra files become manifest inputs. Declare a clean-output or exact expected
  file-set contract and demonstrate clean regeneration before claiming
  reproducibility.
- Synthetic helpers lack comprehensive finite-value and positive-volume
  validation. NaN contour values can lose crossings, and a NaN score can keep
  `scored_static_fixture` status. Keep these as fixture-only claims; reject
  invalid values before using the helpers on solver outputs.
- The source note identifies the DOI, PDF hash and page/table/figure locations,
  separates reported values from assumptions, preserves the Reynolds-number
  discrepancy, and limits the package to preparation. Coordinates, nominal
  inlet integrals, material conversions and hydrostatic pressure signs are
  consistent. The uniform-zero `p_rgh` seed is distinguished from future
  `setExprFields` initialization. D-NUT-BC remains visibly unaccepted.
- The alpha map distinguishes preclip, postclip and solver-final states, keeps
  correction volumes separate from transported `alphaPhi_`, and uses the
  review-4 naming. Its interpretation remains conditional on correcting alpha
  controls. No instrumentation is claimed.

Primary-reported checks on these exact artifacts were: focused pytest **8
passed**; manifest **20 entries OK**; generator no-write check printed
`static case inputs structurally consistent`; Ruff check passed. There is no
archived output log. The reviewer did not rerun tests, invoke the generator,
build, launch Docker, mesh, execute a solver or use the GPU; review activity was
read-only inspection and hashing.

After correction, archive command results, regenerated identities, pinned
source lookup evidence and a finding-by-finding response for a separate
exact-artifact follow-up. Characterization and scientific execution remain
closed.
