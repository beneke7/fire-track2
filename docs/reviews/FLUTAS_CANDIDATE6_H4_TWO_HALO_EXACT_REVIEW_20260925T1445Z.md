# Candidate6 H4 two-halo successor: independent exact review

**Disposition: ACCEPT at the bounded H4 implementation/regression scope.**
The exact candidate6 patch remains unchanged. Its retained one-halo test and
new two-halo driver now demonstrate the correct physical-index mapping for
all three affected helpers. The two-halo driver passes `dzf(0:)`; its
whole-array negative control produces the independently expected one-index
shift. No revision of this exact helper successor is required.

This accepts the missing permanent two-halo positive/negative evidence from
the [previous exact review](FLUTAS_CANDIDATE6_H4_EXACT_REVIEW_20260925T1620Z.md),
combined with that review's accepted production mapping and patch application.
It does **not** certify the preserved candidate5 full host validator as
repaired, approve a source run, or close B1-pre, B1-runtime, B2, production
arithmetic/provenance work, E1–E6, or any scientific gate.

Review snapshot: **2026-09-25 14:45 UTC**. Role: independent Astra Max exact
review under `docs/WORKFLOW.md` and `.codex/agents/general_reviewer.toml`.
The reviewer read the experiment plan, current status, H4 proposal text, prior
review, exact tests, generated sources and both evidence bundles. Actions
were limited to reading, hashing and lightweight in-memory Python arithmetic;
no Fortran compilation, retained executable execution, container, solver,
GPU job or source case was launched. Only this memo was added. The primary
owns status integration and launch decisions.

## Exact identities and evidence checks

Paths below are relative to `containers/flutas/candidate6/`, unless stated
otherwise. Both attempts remain separate:

- Passing retry: `evidence/dzf-two-halo-20260925T143734Z/` (`P` below).
- Preserved oracle failure: `evidence/dzf-two-halo-20260925T143646Z/`
  (`F` below).

| Artifact | SHA-256 |
| --- | --- |
| `source-boundary.patch` | `3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee` |
| `source-pin.txt` | `e07ae0f21196fac176f88c5ec553b33e64c7595aa947839903d38f1c853beefb` |
| `tests/test_dzf_lower_bound_helpers.py` | `72b73c01202019bc24ad6748af078ba2ae1dc3d5edf7e6f1cce6256d72d1a6c8` |
| `tests/dzf_lower_bound_driver.f90` | `89b07c6de682a75dc7a41182f4343fcffc99a1104e5690ec8b54c36d576c3cca` |
| `tests/test_dzf_two_halo_helpers.py` | `9be553db8dae43bffae29704174f1fe60088615b25c149c5b4700c8da7fe8ef4` |
| `tests/dzf_two_halo_driver.f90` | `b8964d942f66aeb7ad09f8c0b1d9d2850d16545467a949647e4f9790ae1ec3f6` |
| `HANDOFF.md` | `96d83bd5e2e5453a61c1b686054babc32b856b110aae1254a20367aa47c94ace` |
| `SHA256SUMS` | `907f76c837f0679713f86d3286771693aa2618e4b9d71c30d8c2b53a1b376f25` |
| `P/SHA256SUMS` | `f0352d9664bf6d3497316d96ba782332073016e3d81602ec070e2da9797eb0a6` |
| `F/SHA256SUMS` | `18d472a2e34dfe62ad670d1c8dc675888d2acbb7def4dd967983aed12696cff6` |
| `P/two-halo/inputs.sha256` | `f6f57ef8afd70b3303cbec0e7ee6df086c01c011cd59f7d3abf5b7db699cd569` |
| `P/test.log` | `e356812c7cd36a1c2c89c98071f255c1d79466f0295b9ba85ef8e98775e2681f` |
| `F/test.log` | `5ffe9b52f02f37b1c5e6f760c92ab5a2983a6b2f631d8a3843106f80cbe0769f` |
| `P/two-halo/comparison.txt` | `fef0a9580b82936568b25a852521b819fc0e4ce953284b42cb0437c6427ff08d` |
| Generated `candidate6_production_helpers.f90`, all four copies | `a6b62334f2ab5b2fec35170a9252cb45908933081f1c688a314286744322cab8` |
| `P/one-halo/dzf_lower_bound_driver` CPU helper executable | `0fa23987bd5d9bd334bacdd0eda83dd529749e79e22e03af858e6fafd9e28426` |
| `P/two-halo/dzf_two_halo_driver` CPU helper executable | `d64a4fb8e49666f78090cd8407da094a9750633d8d1f32973f866b362ecceee1` |
| Preserved candidate5 `source-boundary.patch` | `aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7` |
| Preserved candidate5 `tests/source_boundary_validator.f90` | `c44d1ba0f1b15877c2eaa518e54c6bd338e0d7b6ebb0729d813cce9edb2fe467` |
| Previous exact review, repository-relative path linked above | `2341b9a361046fa6033740b0a8409fe979f197e1523578f3110d14c1b9527e13` |

The reviewer ran `sha256sum -c SHA256SUMS` separately in the candidate root,
`P`, and `F`: **9/9, 37/37, and 35/35 entries passed**, respectively. From the
candidate root, `sha256sum -c
evidence/dzf-two-halo-20260925T143734Z/two-halo/inputs.sha256` passed **6/6**
input identities. A separate directory enumeration verified that each attempt
manifest covers every currently present regular file except the manifest
itself; there were no extra unlisted evidence files.

An independent parser isolated the `src/restas_source.inc` new-file hunk,
counted exactly **1,388** added lines, and compared each of the four retained
helper bodies against its exact patch text. All matched. The generated helper
module is also byte-identical between one-halo/two-halo and failed/passing
attempts; it matches the module hash in the earlier review. Copied drivers
match their current pinned source files.

The source patch hash is identical to the previously reviewed hash. A direct
candidate5/candidate6 patch diff still contains only the three `dzf(:)` →
`dzf(0:)` declaration changes, the inherited-Courant comment clarification,
and the corrected include hunk count. This follow-up does not change source
arithmetic, call order, source scheduling, timestep logic or physics. The
previous patch-application review remains applicable to those exact bytes;
patch application and native build were not repeated here.

## Mapping and permanent regression

`tests/dzf_two_halo_driver.f90:5–33` declares two-halo spacing storage
`dzf(-1:nz+2)` and velocity storage with `nh_u=2`. Its actual spacing values
in array order are `(9.9, 0.4, 1.1, 2.3, 3.7, 5.2, 8.8)`. Physical interior
indices `1:3` therefore contain `(1.1, 2.3, 3.7)`.

The positive branch passes `dzf(0:)` to every affected helper, including the
unit-flux area probe (56–58), the mixed-sign boundary-flux probe (75–77), both
inventory states (100, 112), and the velocity audit (128). A section's first
element is actual index zero; the helper's explicit dummy lower bound zero
makes dummy index `k` refer to physical actual index `k`. The final extra
halo remains harmless. Velocity dummy lower bounds derive from `nh_u`, so
the enlarged velocity storage also maps to the intended physical indices.

The negative branches change only the spacing call operands to the whole
array (60–62, 80–82, 102, 114, 130). Actual index −1 then maps to dummy zero,
so the helpers consume `(0.4, 1.1, 2.3)` for interior `k=1:3`. This remains
in bounds: the intended negative is a successful compiled execution with
wrong physical results, not a compiler or bounds-check failure.

`test_dzf_two_halo_helpers.py:40–109` checks the correct and shifted paths
against their separate expected face areas, all boundary volumes, inventories,
mass residual and full velocity audit. Lines 205–216 additionally require
the paths to disagree for both inventories, y-low inward volume, maximum
divergence and legacy Courant. The negative therefore cannot silently become
an accepted physical path. The geometric areas are also separately checked
against distinct expected values.

The preserved one-halo driver still declares `dzf(0:nz+1)` and passes it whole.
Its boundary, inventory and velocity CSVs are byte-identical to the positive
two-halo CSVs. These are permanent compiled caller tests of the actual
production helper bodies, rather than expected-value adjustments to hide
the index shift.

## Independent numerical check

The reviewer used `.venv/bin/python -B -` with only standard-library CSV,
`fractions.Fraction`, math, hashing and path operations. The calculation did
**not** import either candidate Python oracle or execute candidate code.
Exact rational expectations were compared to every scalar in the retained
CSV files with the candidate's unchanged `2e-12` relative/absolute threshold.
All **600 scalar checks passed**: 106 per two-halo mode plus 88 one-halo
values, for each of the two attempts. This includes mass-table fields that
the candidate test checks only selectively.

For `nx=ny=2`, `nz=3`, `dx=2 m`, `dy=3 m`, `rho=1000 kg/m³` and `dt=1/8 s`,
the independent calculation used the following geometry:

- Total volume is `4*6*sum(dzf(1:3))`; x/y external face areas are
  `6*sum(dzf(1:3))` and `4*sum(dzf(1:3))`.
- Summed alpha in layer `k` is `0.68+0.08*k`. Initial mass is therefore
  `1000*6*sum((0.68+0.08*k)*dzf(k))`; the imposed alpha increment adds
  `1000*0.03*volume`.
- Signed geometric boundary displacement is
  `0.13*i-0.17*j+0.09*k-0.24`, integrated over external faces with outward
  orientation. Inward and outward contributions are partitioned before
  summation. The area probe sets displacement to one metre, so its volume
  values numerically equal face areas after division by that unit displacement.
- The affine velocities are `u=0.0025*i-0.001*j+0.0005*k`,
  `v=-0.0015*i+0.002*j-0.0004*k`, and `w=1.1*k`. Their cell divergence is
  `0.0025/2+0.002/3+1.1/dzf(k)`. Its volume integral is
  `(0.0025/2+0.002/3)*volume+79.2`, independently equal to total outward
  velocity flux.
- Affine fields make the four-point velocity interpolations equal to
  evaluation at their staggered midpoint. The reviewer used those midpoint
  expressions, rather than copying the implementation's stencil summation.
  Both legacy Courant maxima occur at physical cell `(i,j,k)=(2,1,1)`.

| Observable | Physical one-halo / explicit two-halo | Whole-array negative |
| --- | ---: | ---: |
| Total synthetic volume, m³ | 170.4 | 91.2 |
| x-low / x-high geometric area, m² | 42.6 | 22.8 |
| y-low / y-high geometric area, m² | 28.4 | 15.2 |
| z-low / z-high geometric area, m² | 24 | 24 |
| Initial inventory, kg | 37032 | 20064 |
| Updated inventory, kg | 42144 | 22800 |
| y-low inward geometric volume, m³ | 4.814 | 2.752 |
| Total inward / outward mass, kg | 13618 / 21518 | 7779 / 15019 |
| Net inward geometric volume, m³ | −7.9 | −7.24 |
| Synthetic mass residual, kg | −13012 | −9976 |
| Maximum absolute divergence, s⁻¹ | `12023/12000` = 1.0019166666666667 | `33023/12000` = 2.7519166666666667 |
| Divergence integral / total outward velocity flux, m³/s | 79.5266 | 79.3748 |
| Global and interface legacy Courant | `60157/480000` = 0.1253270833333333 | `165157/480000` = 0.3440770833333333 |

The negative path's retained divergence closure is about `1.42e-14 m³/s`,
consistent with rounding. Thus divergence closure alone would not detect
using the wrong geometry: absolute physical expectations and the explicit
negative are necessary. The nonzero mass residual is intentional because
the imposed alpha increment is not a conservative transport step. It is
not a solver conservation pass or failure.

The separate inverse-spacing timestep expression remains distinct. Evaluated
on these synthetic fields with `dzfi(k)=1/dzf(k)` and
`dzci(k)=2/(dzf(k)+dzf(k+1))`, its analytical maxima are
`414757/4440000 ≈ 0.09341373873873873` for physical spacings and
`90221/480000 ≈ 0.18796041666666666` for shifted spacings. These differ from
the division-based legacy audit. The candidate checks preservation of source
expressions and this distinction; neither its retained helper executables
nor this review execute the complete v1.2 timestep restriction or qualify
production floating-point operation order.

## Failed oracle and execution provenance

The historical command in each attempt runs the one-halo test followed by
the two-halo test through `scripts/run_local.py --threads 1 --timeout 120`
and Docker `--network none --cpus=1 --memory=4g --memory-swap=4g`, without
`--gpus`. The recorded image ID is
`sha256:78cd4fe3764e5010e09eaf77d792ee5e2cbdc35d2131497f906f7004c0f94ee8`.
The retained compiler version is NVFORTRAN 26.9-0, x86-64; both compile
commands use `-O0 -g -Mbounds -Mextend`. Compiler logs name the corresponding
generated source and driver. The passing command exits **0**. Both retained
helper executables are x86-64 ELF files, and their hashes above match the
manifest. They are CPU helper binaries, not a candidate6 solver executable
or a GPU runtime package. Compilation/execution evidence is historical;
the reviewer did not rerun it.

The failed attempt exits **1** after compiling/running both two-halo modes.
Its traceback identifies the first rejected area field: face 1 outward area
was `0`, while the oracle demanded `42.599999999999994`. A positive coordinate
flux crosses a low face inward and a high face outward, so demanding both
directions on each individual face was wrong. The current oracle at
`test_dzf_two_halo_helpers.py:57–61` applies these opposite orientations.
This is a justified correction of the expected sign partition, not a change
to numerical tolerances or a fit to a solver result.

All raw CSVs and all retained Fortran source bytes are byte-identical between
the failed attempt and retry. The independently recomputed expectations
accept both sets. This directly supports the reported oracle-only failure;
the accepted numeric path is not dependent on trusting the corrected PASS
message.

**Non-blocking reproducibility limit:** the failed directory contains neither
its old Python oracle snapshot nor an `inputs.sha256`. The current runner
writes input hashes only after comparisons succeed (230–238). Consequently,
the exact failed Python script cannot be reconstructed from that bundle
alone, and the precise Python edit is not independently diffable. Retained
Fortran/CSV/log bytes establish the failed assertion and unchanged computed
results, but do not establish the full prior Python-file identity. Preserve
this failed directory as it is. Future runner work should copy/hash both
Python oracles and all inputs before compilation/comparison, into a new
attempt directory; do not relabel current oracle bytes as the failed script.
No unchanged helper rerun is needed to decide this H4 successor.

## Acceptance boundary and next action

1. **H4 helper repair and retained discriminating tests: ACCEPT.** The primary
   can record the bounded implementation checkpoint with these exact hashes,
   previous patch-application review and this disposition. GPU eligibility is
   **not applicable** to the added CPU caller tests; repeating a
   source-disabled smoke would not test these helpers.
2. **Historical full host validator: unchanged and unqualified for candidate6
   reuse.** Candidate5 `source_boundary_validator.f90:19–23` retains two-halo
   spacing storage; lines 326–327, 366–368 and 371–374 still pass it whole.
   This memo accepts the new explicit-slice successor driver, not those old
   operands. Preserve candidate5 as historical evidence. If the full validator
   is reused against candidate6 or a later patch, its new successor must port
   these calls to physical-index slices and receive the applicable integration
   checks; a constant-spacing pass cannot establish that mapping.
3. **Source-release and scientific work: remains blocked by its separate
   prerequisites.** Continue the already scoped production-arithmetic,
   immutable solver/package provenance, raw capture/audit, protocol, limits
   and launcher work. The earlier candidate6 native build's ephemeral solver
   artifact remains a limitation; retaining these two CPU helper executables
   does not resolve it. Exact package and launch review are still required
   before any source runtime.

These fixtures exercise nonuniform diagnostic operands, not a qualified
stretched-grid VOF solver. All twelve velocity-audit cells are interfacial,
so pure-cell exclusion/no-interface branches are not separately tested here.
No MPI reduction, transport evolution, interface reconstruction, direct VOF
descent, ground map, field comparison or built-device performance is
established by this acceptance.
