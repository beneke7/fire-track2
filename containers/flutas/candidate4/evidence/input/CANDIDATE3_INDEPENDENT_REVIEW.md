# Independent candidate3 source and build review

Reviewer: Astra Max, `/root/general_reviewer_astra`.
Review snapshot: 2026-09-25 08:33:21 UTC.
Only this review record was written. No candidate source/input was edited,
no build or helper executable was run, and no GPU or CFD job was launched.

**Disposition:** the three candidate2 blocking code defects are repaired in
this exact candidate, and the frozen short-x/long-y geometry is retained.
No new blocking defect in those repairs was established by this review.
Candidate3 is suitable for a **separate source-disabled GPU regression** under
the exact conditions below. This is bounded code/build acceptance, not source
CFD readiness: runtime telemetry, executable analysis, numerical limits and
additional behavioral coverage remain open. No source-enabled fixture,
including either dry fixture, is released by this review.

## Exact evidence

The local image inspection confirms image ID
`sha256:90f1261308ab56e52ee29d129deefad86a19b352cef79b43feca08df6762e1c3`,
tag `track2/flutas-source-boundary:5982106-candidate3-20260925T082315Z-1955187`,
and entrypoint `["/bin/true"]`.

| Candidate-relative input | Independently verified SHA-256 |
| --- | --- |
| `source-boundary.patch` | `055758a2690fe4bb9003bdc54665cbc63f67e490f8bd1e307d71ca6d013a4319` |
| `Dockerfile` | `11ef5132827fe2375d68b3559a532747c59bb03bf85d9d8ab4adc21e780adfe4` |
| `build.sh` | `61de670674be3d9f1bae06ab1a8fae26cb25bbc585dd3da1a127d45c28ca0f5a` |
| `tests/test_source_boundary.py` | `9fcbd82979f1189182073b5ad66c7986510983bd10434f8a74fb4e4e3e4623b3` |
| `tests/source_boundary_validator.f90` | `14bae4b0feaf0963a1852583cd96959f14febd460ef633e553655a94370f7560` |
| `tests/run_source_validator_tests.sh` | `b88325b3955cbe84daa45166c11555379df0d88a5d45cec1a425775439f305cb` |
| `tests/source_boundary_sanity_stub.f90` | `741d89003ca07a62ddbd560b3d250f282ed917a1df77cf805453d8a8847059cf` |
| `tests/derive_candidate3_patch.py` | `e0c8bbc1288be59289acff95c4456c35e0569502fc1e7afdd77fcecc81dfa06d` |
| `cases/source_boundary/SHA256SUMS` | `529a81b0429e1f56d86bf2c1a8c691bcf8ae9037ef682d758fe1cb459fa1dc92` |
| `SOURCE_BOUNDARY.md` | `bd33539d46c030827a1795ace71afb8c2ab898604395d7555e307e184128c80f` |

All 11 input hashes recorded in the successful build metadata match current
files, including `.dockerignore` and `source-pin.txt`. All 15 case files match
the frozen manifest. Successful evidence is
`evidence/runs/20260925T082315Z-1955187/`; its `metadata.txt` SHA-256 is
`f9c769d5444fc93b93b587e8dd94cb5a7c424bee0dd485bdeba044f0df988dcc`
and its `docker-build.log` SHA-256 is
`989e9d12b779e3a73b033a5cb08b18c16330218c3f3297e1017a655dea04df68`.

An independent, memory-only application checked every patch context/hunk
against Git objects at FluTAS commit
`598210616bebd51f7d51f61455f196e6f3479916`, and checked the resulting Git blob
IDs against the patch headers. The resulting file SHA-256 values are:

| Patched source | SHA-256 |
| --- | --- |
| `src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90` | `64e305dd85106e12e746af3fb30a056fac40909ab08e3dbc7b47a69f699ff6ae` |
| `src/restas_source.inc` | `adc618df1ed2454eb1c0a8f34c4e2a696757c27acb3f62a5dd83c42b580105c0` |
| `src/vof.f90` | `efd0ad2d3210cbebdd156082b533cd69697ebbc785f42a7d7898079b22a8e6ab` |

Below, **patch** means `source-boundary.patch` line numbers; **upstream** means
the pinned Git object, not a potentially modified temporary checkout.

## Confirmed source behavior and repairs

- **Geometry:** patch 271–295, 328–344 and the hashed fixtures impose
  `160x84x40`, `dx=dy=dz=0.025 m`, and four `6x40` face masks: short x is
  `0.15 m`, long y is `1.0 m`. The centered x intervals are
  `[-0.175,-0.025]` and `[0.025,0.175] m`; y intervals are
  `[-1.025,-0.025]` and `[0.025,1.025] m`. Both gaps are `0.05 m`.
  This matches `docs/BLOCKER_RESOLUTION_PLAN.md:171–174` and
  `SOURCE_BOUNDARY.md:27–33`. The rejected long-x proposal is only a provenance
  artifact under `evidence/orientation-review/`; it is excluded from the build
  context. No archived Astra finding justifies adopting that rotation.
- **Dry duration:** both duration checks now require `slot_count>0`
  (patch 320 and 395); zero-slot `[0,0)` is accepted at 282–288.
  The built host harness reports success for both dry inputs. This establishes
  validator behavior, not dry CFD stability or zero transported liquid.
- **Return halos:** patch 446–451 and 479–485 set and assert the uniform bottom
  return on all x/y halo indices. This repairs the actual momentum accesses to
  `w(ip,j,km)` and `w(i,jp,km)` at the periodic edges (upstream `mom.f90:73,116`).
  The harness deliberately corrupts each relevant halo and checks the expected
  change in the actual CPU momentum routine (harness 186–209).
- **Phase transition:** patch 571–592 performs generic alpha boundary fill,
  interval-specific inflow replacement, then reconstruction before the first
  flux sweep (940–948). Further fills/reconstructions occur between sweeps
  (955–980, 993–996). Post-advection rho/mu fills are followed by source-aware
  property fills before momentum (117–123). The host harness tests an active
  liquid ghost, shutoff to a fractional interior value, changed normal, and
  synthetic outward flow (153–184). Thus the previous stale first-sweep state
  defect is repaired at the inspected call sites.
- **Pressure/velocity pairing:** PP in x/y and DD-normal/NN-pressure in z with
  all `is_outflow=false` is enforced at patch 375–392. The top correction has
  zero pressure gradient and the bottom `k=0` face is outside `correc`'s update
  loop (upstream `correc.f90:49–69`). The source override is present before
  projection and after correction. This supports the boundary design; it does
  not prove a runtime local-divergence result.

The state sequence is explicit in patched driver lines 460, 619–634, 688 and
737–738 (patch 84, 108–123, 132, 141–142): initialize `U0` with interval 0;
at solver step `k+1`, assert and advect with corrected `Uk` and interval `k`;
set interval `k+1` before projection; correct and reapply that same endpoint
profile to establish `U(k+1)`. Intervals 2–11 inject, and intervals 12–13 test
shutoff. The first injected inventory is completed state 3. Completed state
12 contains the last interval's injected mass while velocity state `U12`
already has the source off. This distinction must survive analysis.

**Flux and momentum:** upstream `vof.f90:1274–1276,1452` returns a signed
swept-liquid length, so multiplying by physical face area gives volume, and
division by `dt` gives a rate. Patch 505–528 correctly distinguishes measured
top liquid Q from bottom kinematic total-volume Q. For this fixed pure-liquid
inflow, predeclaring return Q from the exact mask/speed is consistent with the
projection; the measured phase flux is checked, not used to mutate W mid-sweep.
Top outward flux is `-Q`; bottom outward flux is `+Q`, with coordinate W
negative on both faces. Patch 648–669 uses the proper low/high outward signs.
The liquid ledger includes initial inventory and all inward/outward phase
fluxes (749–790); periodic transfer is not an escaped-mass compartment.

Per slot, `Q=0.72 m^3/s`, ten active `1e-4 s` intervals give `0.00072 m^3`
and `0.72 kg`; four slots give `2.88 kg`. The return W is
`-0.085714285714... m/s` per active slot. Source momentum is time-integrated
`dm*U` in `kg m/s`, not a momentum rate: per-slot quiescent impulse is
`(0,0,-3.456)`, and crossflow impulse is `(-36,0,-3.456) kg m/s`.
The z-average of staggered U/V in patch 730–736 recovers the prescribed
constant tangential face values under these DD conditions. A general spatially
varying inlet would additionally need collocation in x/y; that is outside this
frozen fixture. This source audit is not whole-domain momentum validation.

## Severity-ranked remaining findings

### B1 — Source-runtime blocker: telemetry and numerical limits remain incomplete

`SOURCE_BOUNDARY.md:160–169` correctly acknowledges that fixed dt bypasses
`chkdt_tw`; upstream driver 754–760 substitutes `dt_input`. The inherited
checker computes a combined advective/viscous/gravity/capillary stability limit
(`chkdt.f90:67–107`), not an interface-Courant diagnostic. The new CSV header
and audit (patch 618–622, 795–849) contain no measured global/interface Co.
The theoretical `0.0192`, `0.2`, and `0.2192` values are not maxima measured
from the evolved velocity field or a validated stability budget.

Local maximum and volume-integrated absolute divergence are now logged, which
is useful. However `integrated_divergence-net_boundary` is a telescoping
identity even for a divergent field: zero closure is not incompressibility.
The analyzer must judge local maximum and L1 divergence separately. Upstream
`chkdiv`/abort behavior is not a substitute for frozen source-gate limits.

**Smallest fix:** instrument per-step measured global and explicitly defined
interface diagnostics, declare how an empty interface is represented, retain
the relevant timestep/stability restrictions, and freeze justified divergence,
mass, momentum and solve/residual limits before any source-enabled run. For
the direct FFT/pressure solve, declare iteration count inapplicable where
appropriate and supply an actual residual/continuity diagnostic rather than
inventing iteration telemetry. The CPU limits `0.5/0.25` remain proposed.

### H1 — High: source-output schema and fail-closed analyzer are not complete

The header/write counts are internally consistent: source CSV 15 columns,
boundary 13, mass 20, velocity 16. But several semantic rules must be explicit
before those files can drive a gate:

- Source rows use interval `k`; boundary and mass rows use completed state
  `k+1`; velocity state `k+1` reports the next source profile. Joining these
  rows as though their schedule indices matched would shift pulse accounting.
- `offmask_in_m3/offmask_out_m3` are global top-face totals calculated once
  and repeated in **every slot row** (patch 703–744). Summing those columns
  over four slots multiplies them by four. Move them to a per-interval table
  or declare repeated values and require their equality without summing.
- Zero-slot dry fixtures generate no source rows, only its header. This is
  not evidence of zero all-face liquid flux. Require the complete boundary,
  mass and velocity histories and their zero-liquid assertions.
- `net_boundary_liquid_m3` is step-integrated inward-minus-outward liquid
  volume; `net_boundary_m3_s` is outward-positive instantaneous total-volume
  rate. They have different signs, units and meanings. `source_interval_index`
  is emitted as a real-valued scientific-notation field (845–847), despite
  being semantically integral.
- Before early `error stop` on a geometric rate mismatch (519–528), that
  interval has not yet been written to the flux/mass ledgers (984–986).
  Record the failing interval, measured/expected values and residual first.

**Smallest fix:** freeze and test a schema/analyzer with expected counts:
14 source rows for one slot or 56 for four, source intervals 0–13; zero source
rows for dry; and 15 initial/completed records indexed 0–14 in each other
ledger. Reject nonfinite fields, missing/duplicate/truncated/reordered records,
unknown hashes, premature termination and solver-error logs. Enforce all
required gates, including periodic pairing, source-off and off-mask checks,
rather than accepting exit zero or finite-volume closure alone. Use synthetic
CSV fixtures with deliberately failing records before solver execution.

### H2 — High for GPU execution: the existing wrapper would report a no-op success

`Dockerfile:24` deliberately changes the inherited entrypoint to `/bin/true`;
the inspected image agrees. `containers/flutas/run-gpu-gate.sh:15–16` supplies
only the image and `/evidence`, without overriding that entrypoint. Setting
only `FLUTAS_GPU_IMAGE` to candidate3 therefore does not run a kernel or the
bubble test; it runs `/bin/true /evidence` and can exit successfully.

**Smallest fix:** use a separate reviewed invocation with explicit
`--entrypoint /usr/local/bin/flutas-gpu-tests`, the immutable image ID and
positive evidence checks. Do not interpret the unmodified wrapper's success
as candidate regression evidence. See the permitted scope below.

### M1 — Medium: host helper coverage is useful but narrower than a boundary gate

The harness calls the real source reader/validator, return helper, `boundp`,
VOF reconstruction and CPU momentum stencil. It does not parse `dns.in` through
the real driver, call `advvof`, project velocity, write/test ledgers, or test
optional rho/mu boundary handling. Its rho/mu arrays are used for the momentum
stencil; the refresh helper accepts only alpha. The Python property checks
are source-string assertions (Python tests 265–284). The crossflow/gravity
harness modes validate declarations and return values; they never advance
crossflow or gravity. The harness also uses `nh_u=nh_d=2` (line 12), while the
production driver fixes both to 1 (upstream 220–224).

**Smallest fix:** add behavioral checks for actual rho/mu updates after generic
fills, active/off-mask inflow and outward/reversed flow, production halo width
1, and the CSV audit routines with nonzero independent synthetic expectations.
Preserve the halo-width-2 stress test separately. Add dry/active rejection tests
for unsupported inputs. Continue labelling the current five successes as
helper-level checks, never dry/crossflow solver passes.

### M2 — Medium: documentation and build evidence need precise scope labels

`SOURCE_BOUNDARY.md:115–117` still says endpoint checks do not execute Fortran,
although the new host harness exercises active/off transitions. Lines 129–131
say the exact momentum operations are checked by the unit suite, but the source
ledger's flux-times-velocity operation is only inspected as text; the actual
momentum routine test is a separate halo-consumption check. State these
distinctions explicitly. Build metadata freezes inputs and an image, but does
not constitute GPU execution evidence.

The successful build log records 13 Python tests (lines 26–43), five host
helper cases (45–49), clean/recompile (50–57), native `sm_120` code object and
successful image creation (1275–1289). The earlier failed managed-attribute
build at `20260925T081906Z-1947098` is preserved, as is the separate successful
`20260925T082047Z-1950779` build. The reviewed image is only the final
`082315Z-1955187` artifact; do not merge their identities or test results.

## Separate source-disabled GPU regression recommendation

**Yes: recommend scheduling the existing bounded hardware/upstream regression
on this exact image, independently of the closed source gate.** The optional
source reader returns without enabling hooks when `source-boundary.in` is
absent (patch 165–166, 214–217). In that state the driver selects the original
no-source `advvof` call and the added helper branches are inactive (109–115).
The upstream rising-bubble directory contains no such input. This review finds
no source-path prerequisite that needs to be bypassed to exercise that branch.

Conditions for the primary's separate launch record:

1. Pin the exact image ID above and explicitly override the entrypoint to
   `/usr/local/bin/flutas-gpu-tests`. The repository script reviewed here has
   SHA-256 `e90285710e1ce77724d85bcf331c2fe993fdd6367cf3ccec159f81c70c88757c`;
   verify the executed image copy or record its exact bytes/hash too.
2. Use a fresh immutable evidence directory. Assert absence of
   `source-boundary.in` in the actual copied rising-bubble working directory
   before the solver starts; checking an unrelated shell working directory
   is insufficient. No candidate source fixture is copied or mounted there.
3. Use `scripts/run_local.py`'s shared GPU lock, one GPU-owning job, the
   existing two-CPU cap/thread controls and bounded 600-second outer timeout,
   after a current resource check by the primary. Preserve every attempt.
4. Require actual OpenACC-smoke, CUDA-aware-MPI-smoke, solver and upstream
   verification artifacts, successful process exits, and expected completion;
   reject empty logs or missing outputs. The inherited test script runs those
   stages in order and stops on failure (`run-gpu-tests.sh:20–37`). Record
   revision/dirty state, input/runner/image hashes, GPU/driver and resource use.
5. Label any success **source-disabled hardware/upstream regression only**.
   It does not pass `dry_four`, `dry_crossflow`, the slot-source gate or E1–E6.

Source CFD remains closed pending B1/H1 and the approved complete execution
contract. Then the separate source sequence is quiescent dry, dry crossflow,
one slot, four slots, and sourced crossflow/gravity, stopping at the first
failure. No larger pilot or paper comparison follows from this review alone.

Assessment complete. Hash verification, patch reconstruction, code/file reads
and image inspection were read-only; only this review record was added.
