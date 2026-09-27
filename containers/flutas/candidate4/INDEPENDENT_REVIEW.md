# Candidate4 independent Astra Max review

Reviewer: `candidate4_exact_astra_review`, Astra Max, read-only.
Review time: 2026-09-25 09:25:26 UTC.

**Disposition:** the exact candidate4 image is eligible for a bounded
source-disabled GPU regression after the runner fixes below. Do not use the
current runner unchanged. This review does **not** approve source-boundary
execution, `dry_four`, `dry_crossflow`, or any scientific gate. No files were
edited and no tests, builds, solver runs, CFD or GPU work were launched by the
reviewer.

## Exact reviewed evidence

The source patch SHA-256 is
`2eddbe5cc406ecbc60e7ca1fe9ba3a5ff61b130283e74772b1593f1d385959ff`; the
authoritative build evidence is
[`evidence/runs/20260925T091602Z-1994261/`](evidence/runs/20260925T091602Z-1994261/).
The immutable image ID is
`sha256:3086f0312b3a74dd7d0f03102d4b8584a8dd1fe4091364615cb0e580f00283bb`;
its inherited entrypoint is `[/bin/true]`.

The reviewer independently checked candidate files, all 12 build-input hashes,
all 15 case-manifest files, patch contexts and resulting source blobs against
the pinned upstream commit. The exact review inputs included the source patch,
Dockerfile, build script, tests, case manifest, source record, runner scripts and
candidate3 review. The build log records eight host behavior/ledger modes, two
expected rejects, a flushed expected rate failure, 14 Python tests, and
`sm_120.cubin`. These are build/helper checks, not GPU or solver execution.

## Findings

### High — wrapper can report success after an abnormal solver stop

`containers/flutas/run-candidate-gpu-regression.sh` checks the container exit
and nonempty artifacts but not normal solver completion. The pinned driver can
set `kill=true` after divergence, finalize, and exit normally without printing
`*** Fim ***`. The upstream bubble checker tests means of two columns and does
not check final time or solver error output.

**Required fix:** require `*** Fim ***`, reject solver error/abort diagnostics,
and verify the last finite timestep record reaches the frozen 3 s endpoint.
Keep the upstream comparison as an additional check.

### Medium — patch provenance names candidate3 for candidate4

The reviewed `run-candidate-gpu-regression.sh` SHA-256 is
`b4d00171b5f0550682b6bdd9618b427de859b7b10721dc748cf67c0b93221824`. Its
metadata unconditionally hashes `containers/flutas/candidate3/source-boundary.patch`.

**Required fix:** verify `/tmp/source-boundary.patch` from the immutable image
against the expected candidate4 patch hash and record the verified hash/build
metadata. Do not emit a misleading candidate3 `candidate_patch_sha256` field.

### Medium — header-only resource samples pass as complete evidence

`run-candidate-gpu-regression-locked.sh` writes resource CSV/TSV headers before
sampling. The outer wrapper accepts them because they are nonempty.

**Required fix:** require at least one valid finite GPU sample and at least one
valid container CPU/memory sample before writing PASS. Preserve sampler errors;
describe maxima as sampled values, not exact peaks.

### Source-runtime blocker — analyzer and execution contract are not frozen

The host suite writes synthetic records but does not validate corrupted,
reordered, duplicate, truncated, nonfinite or incomplete solver histories,
unknown input hashes, periodic mismatches, abnormal completion or numerical
limits. Numerical/resource budgets and pressure/stability rules remain
unapproved. The analyzer must include the new rate-check and global off-mask
tables, use separate local-maximum and volume-integrated L1 divergence checks,
and handle nonfinite rate comparisons explicitly.

**Required next action:** freeze schema and execution manifest, implement
positive and negative analyzer tests, and obtain protocol review before source
execution.

### Medium — Courant equivalence is limited to the uniform fixture

The z estimate in `restas_source_record_velocity_audit` uses `wz/dzf(k)`, while
upstream `chkdt.f90:80` uses `wz*dzci(k)`. The `dzf(:)` assumed-shape dummy also
reindexes the driver's full haloed array. They agree on the hashed uniform
`gr=0` fixture up to floating-point construction, but not necessarily on a
stretched grid; validation does not reject `gr != 0`.

**Required fix before any stretched-grid equivalence claim:** pass correctly
indexed physical `dzfi`/`dzci` arrays, or explicitly enforce the uniform-grid
restriction. This does not affect the source-disabled regression.

## Confirmed candidate behavior and limits

- The three candidate2 defects remain repaired: zero-duration dry input is
  accepted; return velocity covers periodic halos; and phase/property boundary
  state is refreshed before the first VOF sweep and after generic property
  fills.
- Transport interval `k` consumes corrected velocity `U_k`; the next
  projection profile is state `k+1`. Intervals 2–11 are active, and intervals
  12–13 exercise post-pulse transport.
- The grid-aligned short-x/long-y fixture has `6×40` cells per slot, `0.15 m²`
  area and `0.05 m` gaps. Signs are consistent: top inward and bottom outward
  velocities have negative coordinate W, with outward-positive rates `−Q` and
  `+Q`.
- Geometric top liquid rate and kinematic bottom total-volume return are
  measured separately. One slot is `0.72 m³/s`, `0.72 kg` per ten active
  intervals and has prescribed impulse `(0,0,−3.456) kg·m/s`. Four slots total
  `2.88 kg`; their uniform bottom return is about `−0.342857143 m/s`. This is
  not whole-domain momentum validation.
- Empty interface semantics are explicit: count 0, defined flag 0 and numeric
  value 0 mean undefined, not measured zero. Courant is advective-only;
  fixed-step fixtures bypass the complete upstream timestep restriction.
- Divergence maximum, volume-integrated L1 and signed integral are separate;
  closure is only a bookkeeping identity. Successful ledgers have 14/56/0
  source rows for one/four/dry, 14 off-mask and rate rows, and 15 boundary,
  mass and velocity rows. Rate failure is flushed before abort.
- Production-width-one tests cover selected return/alpha/ledger paths; the
  momentum-stencil corruption test and detailed property transition checks use
  halo width two. No host mode advances the real solver driver or performs a
  projection or VOF advection.

## Bounded next GPU check

After the wrapper is fixed and independently checked, run the exact image above
through the shared GPU lock, with two CPUs, one GPU-owning job, a 600-second
timeout and cleanup. Explicitly override `/bin/true` with
`/usr/local/bin/flutas-gpu-tests`; verify the exact embedded runner hash and
absence of `source-boundary.in` in the copied upstream case before execution.
Run OpenACC, CUDA-buffer MPI and the one-rank rising-bubble test sequentially;
stop at the first failure. Require positive solver completion and valid runtime
resource samples. Any success is a source-disabled hardware/upstream
regression only.
