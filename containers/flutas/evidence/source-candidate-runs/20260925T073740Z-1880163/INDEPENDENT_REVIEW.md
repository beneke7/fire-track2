# Candidate2 independent Astra Max review

**Primary-recorded review handoff:** 2026-09-25. **Reviewer role:**
`general_reviewer_astra` (Astra Max, read-only). **Decision:** candidate2 is
blocked. This record transcribes the reviewer's handoff; the reviewer did not
edit repository files or run a solver/GPU job.

## Reviewed identity and evidence

- Patch SHA-256: `bd42ab7b17383ae90411aef2e0878c1427a3c3a5f49694eeb28c57659063af40`.
- Case `SHA256SUMS` SHA-256:
  `02d1d1c96c05f72721884b7e6765d13df9b210e2773acbbbf39018772969713b`; all
  12 case hashes independently verified.
- `Dockerfile.source-candidate` SHA-256:
  `bdb7723d086ede27bdb90d42089f546979770909345b297af32a9348b1cd9fe5`.
- Image ID:
  `sha256:6ecfa8e248fe297782becdffba41dcd5db267768cdee0f9f724895796252e7b3`.
- Build log reports ten static/analytic checks passing and native `sm_120`
  code-object presence. These are compile/static results only; no boundary
  helper was run, and no source CFD or candidate GPU run occurred.
- The immutable patch copy is
  [`source-boundary-candidate2.patch`](source-boundary-candidate2.patch).

## Blocking and high-severity findings

1. **Dry validator aborts.** The reader and validator accept zero slots and
   `[0,0)`, but a final unconditional duration assertion rejects `q1 <= q0`.
   The relevant candidate2 patch locations are around lines 194–199, 282–288,
   and 393–395. Guard positive-duration checks for active slots and execute
   the full reader/validator on all frozen fixture records.
2. **Bottom-return periodic halos are stale.** The helper changes bottom-face
   W only for interior indices after generic boundary filling. The periodic
   halo values remain zero while the active return is nonzero; pinned
   `bound.f90:503–510` fills this plane and pinned `mom.f90:73,84,116,127`
   consumes its periodic x/y ghost values in momentum stencils. Refresh or
   consistently prescribe the full plane without a later generic z fill
   erasing it, and test the actual periodic-edge stencil inputs.
3. **Source shutoff leaves stale alpha and reconstruction.** End-of-pulse
   velocity U12 is inactive, but the source alpha/property ghosts retain the
   prior liquid inflow. The next `advvof` starts with an inflow-only helper;
   zero W leaves those ghosts untouched, so the first x sweep can use the old
   liquid ghost plus stale `nor/cur/d_thinc`. At each advection entry, apply
   generic alpha fill, interval-k source-aware fill, and recompute VOF geometry
   before the first flux. Test fractional interior alpha across an on-to-off
   and inflow-to-outflow transition.

## Remaining release blockers and bounded limitations

- Fixed `dt` skips runtime Courant calculation. The documented 0.0192/0.2/0.2192
  estimates are theoretical, not measured maxima. Implement global and
  interface Courant telemetry, finite-value checks, local-divergence,
  volume-flux and pressure/velocity-solve limits, resource ceilings, and a
  fail-closed analyzer/runner before source execution.
- Candidate2 originally defined the ledger residual using source-attributed
  inward mass minus all-face outward mass. Periodic crossing would make that
  false. Control-volume closure must use all-face inward minus all-face
  outward (or explicitly pair periodic terms); keep source-attributed dose
  separate. The primary corrected the shared gate formula after this review.
- The ten tests are static/analytic, not runtime boundary tests. Candidate3
  needs full-validator, periodic-halo, transition/reconstruction, wet-outflow,
  reverse-inflow and property-ghost behavior coverage.
- `dry_four` has zero gravity and no ambient crossflow; it does not test the
  dry crossflow/gravity behavior. Add a separate dry-crossflow fixture.
- Record and flush measured/expected phase flux before any assertion aborts,
  so the failed attempt retains decisive diagnostics.
- Candidate2 build metadata omitted the build script/test hashes and repository
  revision/dirty state. A new candidate bundle must include those plus the
  complete immutable source patch and must use a unique directory/tag.
- The U/V source-momentum interpolation is valid for the current spatially
  uniform tangential fixture; it is not a general staggered interpolation for
  nonuniform velocities.

## Findings that did pass source inspection

The interval-k versus endpoint-(k+1) state sequence is present in candidate2.
The DD velocity/NN pressure pairing is compatible with the pinned correction
for this fixture. The return is derived from total volume flux; geometric
liquid phase flux is measured separately. A one-slot schedule requests
`Q=0.72 m³/s`; the bottom return is `−0.0857142857 m/s` over `8.4 m²`.
These design checks do not waive the defects or the missing source-run
contract.

Candidate3 implementation and non-solver behavioral tests may proceed. Source
cases remain closed until the corrected exact hashes, diagnostics, execution
contract, numerical limits, and independent review are complete. Then run dry
→ one-slot → four-slot → crossflow sequentially and stop at the first failure.
