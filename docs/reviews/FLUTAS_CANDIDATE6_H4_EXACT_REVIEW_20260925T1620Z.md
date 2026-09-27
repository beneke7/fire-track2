# Candidate6 H4 exact implementation review

**Disposition: REVISE for aggregate H4 closure.** The three lower-bound changes
are correct for the pinned one-halo production caller. The inherited two-halo
host interface still shifts the spacing index when it passes its whole array;
candidate6 does not supply the required repaired harness and negative-control
regression. The compiled reviewer probe below confirms both facts.

Actual review snapshot: 2026-09-25 14:14–14:23 UTC. The filename is the
primary's assigned memo name. This is an independent, narrow implementation
review under `.codex/agents/general_reviewer.toml`. Candidate files, candidate5,
shared plans and upstream working files were not edited. Only this memo was
added. CPU helper execution was capped at 1 CPU / 4 GiB in a network-disabled
container without a GPU. No solver, source case, scientific run, native
rebuild or GPU runtime was performed.

| Scope | Decision |
| --- | --- |
| Exact patch's production `dzf(0:nz+1)` mapping | **ACCEPT at source/helper implementation scope.** |
| Exact patch application and corrected 1,388-line include hunk | **ACCEPT.** Independently applied to pinned upstream files. |
| H4 across production and inherited harness interfaces, with permanent discriminating tests | **REVISE.** Required harness mapping remains wrong and the candidate lacks a shifted-index negative. |
| Recorded native compilation / `sm_120.cubin` evidence | Successful build is supported by the preserved log and matching input hashes; no candidate6 executable or packaged runtime image was retained for independent reinspection. |
| Source-run eligibility, B1-pre/B1-runtime/B2, conservation/scientific approval, E1–E6 | **NOT APPROVED.** This review releases none of these gates. |

## Exact reviewed snapshot

`sha256sum -c SHA256SUMS`, run from `containers/flutas/candidate6/`,
passed all four entries. Both final evidence `inputs.sha256` files
were independently checked against current bytes; all entries matched.

| File | SHA-256 |
| --- | --- |
| `containers/flutas/candidate6/source-boundary.patch` | `3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee` |
| `containers/flutas/candidate6/source-pin.txt` | `e07ae0f21196fac176f88c5ec553b33e64c7595aa947839903d38f1c853beefb` |
| `containers/flutas/candidate6/tests/test_dzf_lower_bound_helpers.py` | `6099869d30635f1e678e92f92fff847793e59006204cddaf2d74f94836daa8b8` |
| `containers/flutas/candidate6/tests/dzf_lower_bound_driver.f90` | `89b07c6de682a75dc7a41182f4343fcffc99a1104e5690ec8b54c36d576c3cca` |
| `containers/flutas/candidate6/SHA256SUMS` | `27805fdbfbba80a3226368839e73e014a4003fc7426a9ba59da9d367119cbc61` |
| `containers/flutas/candidate6/HANDOFF.md` | `fdc991e4dc729d3c758373e3e6b741b2313be1fa2a5918b6846cac2db7836a35` |
| Preserved candidate5 patch | `aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7` |
| Final helper `test.log` | `3c2df0ec46725694ecb81960455408c867171fdf768f2708a0a91386b6f57690` |
| Final native `build.log` | `993b9e29c80128b5fdbf5404b5f29d5215fa03d39a566a6007d3de7b9f2b02f3` |

The final helper bundle is
`containers/flutas/candidate6/evidence/dzf-lower-bound-20260925T141008Z/`;
the native bundle is
`containers/flutas/candidate6/evidence/native-build-20260925T141014Z/`.
Earlier failed attempts remain alongside them and were not replaced.

The candidate5-to-candidate6 diff contains three declaration changes
(`dzf(:)` to `dzf(0:)`, patch lines 752, 870, 916), an inherited-Courant
comment clarification (962–965), and the new-file hunk count correction from
1,386 to 1,388 (204). No arithmetic statement, source call, schedule or
source-enabled branch changed.

## Bound and metric inspection

The upstream source was read with `git show` at commit
`598210616bebd51f7d51f61455f196e6f3479916`, rather than trusting the modified
`/tmp/candidate5-upstream` working tree. Pinned
`src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90:220–250` sets
`nh_u=nh_p=nh_v=1`, hence `nh_d=1`, and allocates `dzf(0:nz+1)`.
The main and `advvof` calls pass that whole array. Explicit dummy lower bound
zero therefore makes helper `dzf(k)` refer to physical cell k; the candidate5
default lower bound one instead referred to caller k−1.

All direct spacing uses in the source include were checked:

| Helper / candidate6 patch locations | Finding |
| --- | --- |
| Boundary accumulation, 749–791 | Interior k is `1:n(3)`. x-face area is `dl(2)*dzf(k)` and y-face area is `dl(1)*dzf(k)`; z area is `dl(1)*dl(2)`. Low faces negate the directional signed geometric flux, high faces retain it. Incoming and outgoing volumes are disjoint. |
| Inventory, 866–910 | The same physical interior spacing weights `rho1*alpha*dx*dy*dzf(k)`. State zero stores initial mass; later calls add interval boundary masses once. Residual is cumulative inward minus outward minus inventory change. It does not count cumulative flux as stored liquid. |
| Velocity audit, 912–998 | x/y boundary rates use the corresponding face areas; z rates use `dx*dy`. Cell volume and staggered divergence use the same `dzf(k)`, so summing divergence times cell volume telescopes to signed external face flux, up to rounding. All `i±1`, `j±1`, `k±1` stencil accesses fit the one-halo velocity arrays. |
| VOF refresh, 628–660 | Its `dzf(1-nh_d:)` already tracks the incoming halo parameter and passes it consistently to `boundp`/`update_vof`; no direct erroneous reindexing was found there. |
| Timestep-input capture, 1154–1196 | Its existing `dzf(0:)` retains the production 42 entries; positivity/finiteness/reciprocal checks and sequential JSON serialization do not introduce another cell-index shift. This capture is itself specific to the frozen one-halo, 40-cell vertical layout. |
| Timestep restriction, 1450–1540 | Existing `dzfi(1-nh_d:)` and `dzci(1-nh_d:)` match upstream `chkdt_tw`. The full-array minimum includes the same halo entries as pinned upstream. Candidate6 does not modify this path. |

Pinned `initgrid.f90:50–62` defines `dzf(k)=zf(k)-zf(k-1)` and
`dzc(k)=0.5*(dzf(k)+dzf(k+1))`. Thus volume/face/divergence expressions above
have the correct geometric meaning even for the deliberately nonuniform
helper fixture. This does **not** qualify a nonuniform VOF solver: pinned
`advvof` and reconstruction contain scalar `dli(3)` operations, and the
diagnostic fixture is not an approved stretched-grid CFD case.

The velocity audit intentionally retains division by `dzf(k)` for all three
directional estimates. The v1.2 timestep path instead multiplies x/y terms by
captured `dzfi(k)` and z terms by `dzci(k)`, in upstream source order
(`chkdt.f90:67–80`). They differ on a nonuniform mesh and may differ in last
bits even where reciprocals describe the same nominal spacing. Candidate6's
comment correctly stops claiming equality. The inherited CSV name
`global_chkdt_advective_courant_max` is not evidence of such equality; the
source-release interface still must preserve their distinct meanings.

The interface audit tests `0 < alpha < 1` and reports the maximum of the same
cellwise legacy Courant over that subset. The supplied fixture makes all
12 interior cells interfacial, so its global and interface maxima agree by
construction. It exercises nonuniform spacing and one-halo stencil limits;
it does not separately test pure-cell exclusion or the no-interface branch.

## Finding H4-R1: the two-halo caller remains incompatible

**High for complete H4 closure.** Candidate5's preserved
`tests/source_boundary_validator.f90:19–23` declares `nh_d=2` and
`dzf(-1:nz+2)`. Its inventory/velocity calls (326–327, 371–374) and boundary
calls (366–368) pass the whole spacing array. A `dzf(0:)` dummy remaps actual
index −1 to dummy zero, so helper k denotes actual k−1. The harness assigns
constant spacings at line 61, concealing this error numerically.

Candidate6's new driver only declares `dzf(0:nz+1)` (line 8). The candidate has
no repaired two-halo harness or compiled shifted-index negative control.
The earlier source-contract review, successor exact review, and v0.2 H4
proposal (152–171) require both production and harness mapping plus a
deliberate shifted-index negative. Warden 12 repeats that evidence boundary.
Those conditions are not satisfied by the one-halo pass message.

**Smallest next action, bounded Luna owner:** preserve this snapshot and add
a successor harness/test package that passes the intended zero-origin slice
from two-halo storage, or prospectively adopts an explicit halo-aware helper
interface at every caller. The reviewer probe demonstrates that explicit
`dzf(0:)` call slices suffice for these helpers without changing their
production arithmetic. Repair actual harness calls, not only expected values.
Use nonconstant spacings; permanently retain positive one-halo and two-halo
tests and a deliberately shifted negative. Archive their generated source,
compile command and raw CSV outputs, then exact-review the changed package.
Initial envelope: CPU only, 1 CPU / 4 GiB; no GPU or solver is needed.

## Independent compiled discrimination

The reviewer reran the exact candidate helper test successfully, using:

```sh
.venv/bin/python scripts/run_local.py --threads 1 --timeout 120 -- \
  docker run --rm --network none --cpus=1 --memory=4g --memory-swap=4g \
  --mount type=bind,src=/home/v/proj/bene/fire-track2/containers/flutas/candidate6,dst=/candidate6,readonly \
  --entrypoint bash \
  sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8 \
  -lc 'PYTHONDONTWRITEBYTECODE=1 python3 /candidate6/tests/test_dzf_lower_bound_helpers.py /candidate6'
```

Exit 0: all three reported checks passed. The extracted helper compilation
uses `nvfortran -O0 -g -Mbounds -Mextend`, not production optimization or GPU
execution flags. The third PASS line combines preserved source expressions
and Python expected values; it does not execute the separate full v1.2
timestep-restriction routine.

A second CPU-only command used the same image, mount and limits, with
`--entrypoint python3 ... -` and a Python driver supplied on stdin. It imported
the pinned test via `runpy.run_path`, called its exact `added_source()` and
`generated_module()`, and separately compiled each of these temporary variants
with the same bounds-check flags:

1. Unmodified exact module and exact one-halo driver.
2. Only the extracted module's three `dzf(0:)` declarations replaced with
   `dzf(:)`; the exact one-halo driver was unchanged.
3. Exact module; driver storage changed to `dzf(-1:nz+2)`, with values
   `(9.9,0.4,1.1,2.3,3.7,5.2,8.8)` in array order; whole-array calls retained.
4. Variant 3 with only the helper call operands changed to `dzf(0:)`.

No production or candidate file was modified. Every variant compiled and
executed without a bounds error: this is an in-bounds semantic indexing
defect, not an out-of-bounds defect. Numeric comparisons used the existing
`2e-12` absolute/relative helper threshold and explicitly required variants
2/3 to disagree while variants 1/4 agreed. The probe exited 0.

| Observable | Exact one halo / explicit two-halo slice | Shifted dummy / whole two-halo array |
| --- | ---: | ---: |
| Initial synthetic inventory, kg | 37032 | 20064 |
| Updated synthetic inventory, kg | 42144 | 22800 |
| y-low inward geometric volume, m³ | 4.814 | 2.7520000000000002 |
| Maximum absolute divergence, s⁻¹ | 1.0019166666666666 | 2.751916666666667 |
| Global and interface legacy Courant | 0.12532708333333334 | 0.3440770833333333 |

Independent arithmetic confirms the geometry: total interior volume is
`4*2*3*(1.1+2.3+3.7)=170.4 m³`; summed alpha per z-layer is
`0.68+0.08*k`, giving `1000*6*(1.1*0.76+2.3*0.84+3.7*0.92)=37032 kg`.
Adding alpha 0.03 adds 5,112 kg. The velocity divergence is
`0.0025/2 + 0.002/3 + 1.1/dzf(k)`, giving the stated maximum at k=1.
The independent divergence integral is `79.5266 m³/s`, equal to summed signed
external velocity flux. The intentionally imposed alpha increment is not a
conservative transport update; its nonzero mass residual is a test value,
not a solver conservation result.

Generated source identities for reproduction:

| Probe artifact | SHA-256 |
| --- | --- |
| Exact extracted helper module | `a6b62334f2ab5b2fec35170a9252cb45908933081f1c688a314286744322cab8` |
| Shifted-dummy negative module | `5daf5bc94f97c55dce65c996eb10a438806822613c9fb17f8f96d1fbf8dd35a7` |
| Whole two-halo probe driver | `0dfc3a1d7d7c4533cec9cecc8656fd49a62452ca0a73235195fe044506af5c26` |
| Explicit-slice two-halo probe driver | `0bb376a570331bb8f4775f280a4915cda7a9d8b4dc4b7d14ef6e4d2b36eae420` |

These reviewer variants ran in temporary directories; this memo retains the
construction, hashes and observed values. They establish the discriminating
finding but do not supply a permanent candidate regression/evidence bundle.

## Call order and package/build evidence

Main's inventory/velocity calls remain after initialization and boundary
preparation (patch 108–118). Each source interval resets boundary volumes
before `advvof` (131–149); each directional boundary accumulator follows its
geometric flux calculation before that flux storage is reused (1731–1732,
1760–1761, 1787–1793). Updated inventory follows completed VOF/property
refresh (150–160). The endpoint velocity audit follows pressure correction,
ordinary velocity boundary conditions and the source override (175–188).
These calls pass the whole correct one-halo production spacing array.
Candidate6 neither changes nor independently requalifies the inherited
AB2 clock, split-advection/clipping residuals, return-flow/projection design
or stage-observability contract.

The reviewer wrote exact pinned upstream file contents into a temporary
directory and ran `git apply --check` followed by `git apply` on the candidate6
patch: both passed. The include has exactly 1,388 lines and ends with the
complete `end subroutine restas_source_close_log`. Applied file hashes are:

| Applied file | SHA-256 |
| --- | --- |
| `src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90` | `206c99e2a0695fa3533bf76877a887fb25e3438b6a13a8eb939fd7e54ee54d6d` |
| `src/restas_source.inc` | `7f5be52cea92d2a06f2d3fee4cdbebc782357399684776a4552643a5cb850cfd` |
| `src/vof.f90` | `657e4d7e4c7ec0739b506ae806c9bd5e80df7aaa238e248cb9fab4ee43fcea61` |

Pinned upstream hashes checked independently were main
`1d6450b3379b9995b0d69c0d8e22d8b038c66446ebd33066cfdffdf799616e22`,
VOF `034fb87f481e1fb2da5c2075f36aa39baaf4e2639c9532bc36307ae245ab59dc`,
initgrid `87010cb1b014355eb70b299264d5b6cd274ab3248c309906a39ac4a66ab8ca28`,
and chkdt `68e9f9592220b6f7a80366e60ccceb0595685d7324977c3710656aab15b0e661`.

The preserved native command reverses candidate5 from local image
`sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`,
checks the pinned Git commit and that only the inherited GPU target delta
remains, applies candidate6, cleans and builds with `make -j2
ARCH=generic-gpu APP=two_phase_inc_isot`. The inherited target hash
`d694b6db322a2f9391ef09bb697bade0cb32ec3ab3f11bd6dfe9dba814a43759`
differs as declared from original upstream
`ca815f1b4f2839459703e634d1b8ab11d3bca3cff01cec37876217af967bbf6f`.
The log shows `-fast -cuda -acc -gpu=cc120,cuda13.3`, successful linkage,
`sm_120.cubin`, and executable hash
`80cea6c09773a24441e4c990a790d79880b71b2e20d60cc3d9f368c0ea8bce5a`.
Its recorded allocation was 2 CPU / 6 GiB / 900 s with no GPU or network;
that historical build was not repeated during review.

**Build-evidence limit:** the command used an ephemeral `docker run --rm`
without copying out or packaging the new executable. Candidate6 contains the
log, not that executable or a new candidate6 image/OCI receipt. The reviewer
could inspect current compiler/base image IDs and the recorded build, but
could not independently rehash or rerun `cuobjdump` on the removed candidate6
binary. Do not attach its hash to the unchanged candidate5 image or treat the
log as an immutable runtime package. Retaining and reviewing a runtime
artifact remains a separate source-release prerequisite.

Remaining work is bounded CPU engineering: repair and prove harness mapping,
retain the negative regression/raw outputs, and complete the separate
production-arithmetic/provenance/source-release work. This review establishes
no mass-conservation pass, source-run approval, validated CFD or field result.
