# Candidate5 DNS/VOF fixture schema v0.1

**Primary proposal, 2026-09-25.** This annex freezes the typed interpretation
of the current five allowlisted fixture triplets for review. It does not accept
a parser or candidate, authorize source execution, or broaden fixture
eligibility. Any changed bytes or case semantics require a prospective
versioned amendment.

## Byte allowlist

All three files must match one exact tuple below. Hashes cover every byte,
including comments and the final LF. Check hashes before decoding or parsing.
The five DNS/VOF record tables, field names, types, token counts and exact
values are incorporated by reference from the independent extraction
[`DNS/VOF typed-record audit`](../docs/reviews/DNS_VOF_TYPED_SCHEMA_AUDIT_20260925T1443Z.md),
SHA-256 `e7709cc54e5ecbb623062fcba6f30f420d6c2c17048866cf9db25f756e917c47`.
Its DNS and VOF tables are normative data for this annex; the source record
anchors are FluTAS commit `598210616bebd51f7d51f61455f196e6f3479916`,
`src/apps/two_phase_inc_isot/param.f90` and `src/types.f90`.

| Fixture | `dns.in` SHA-256 | `source-boundary.in` SHA-256 | `vof.in` SHA-256 |
| --- | --- | --- | --- |
| `dry_four` | `929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0` | `f14d5e44d14928e5c3db0b4158e9ff7122aec64ac591fc8ea2fea9ce5df154e0` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |
| `quiescent_one` | `929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0` | `761dfef4cf386ae122344fc3b9b8e0fa3fb6e468ba79a7235224389c779b9b13` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |
| `quiescent_four` | `929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0` | `f4d904ae10986f6fa6ff872f76435bb6e4cdb0b8a9c7707ff5307f911410f5b7` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |
| `dry_crossflow` | `574bcfe3afa0c17284677f78a28b5bdad70e97c80a32ee0dc8af1651227da7b7` | `7bbb8cdd01a06ae6bcbfe47fb448d9cf5a61f3bb2ae82b7a83c6b688be1024db` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |
| `crossflow_four` | `574bcfe3afa0c17284677f78a28b5bdad70e97c80a32ee0dc8af1651227da7b7` | `55f485ce507b8d19fa05c4324308028696ef50ddfe3faec2bab6b1a242e201ec` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |

The fixture inventory itself is
`containers/flutas/candidate5/cases/source_boundary/SHA256SUMS`, SHA-256
`a04cbac29baf540bce1c969ad0df2c081b0dc2a3a7a31177606c34602d7978f1`; its
15-file `sha256sum -c` verification passed. The table permits two DNS byte
variants and one VOF byte variant only. Case IDs are independently checked
against this allowlist, never inferred from a directory name alone.

## Parsing rules

Decode ASCII only after the exact raw-byte hash passes. Require LF-only bytes,
one final LF, no BOM, CR, blank records or extra records. DNS has exactly 29
physical records and VOF exactly 8. Each physical record is one line; after
removing only the inline `!` comment, split on one or more ASCII spaces or
horizontal tabs and require exactly the type-count in the pinned record table.
Do not admit continuation, quoting, comma, slash, null, repetition or
list-directed extensions. Parse fields in declared order and type: default
integer, candidate-build `real(rp)`, default logical, or fixed character
identifier. The pinned candidate build flags omit `_SINGLE_PRECISION`, so its
current `real(rp)` is double precision; the parser still binds this meaning to
the exact reviewed build receipt.

Only the exact lexical tokens in the five hashed fixture files are accepted.
The observed logical vocabulary is uppercase `T`/`F`; identifiers are
lowercase `ab2`, `cen`, `zer`, `hkv`, `cfr`; boundary characters are uppercase
`P`, `D`, `N`. Real fields include integer-spelled tokens such as `0` and `-50`.
Do not claim a generalized Fortran lexical grammar, accepted physical ranges,
or conversion/underflow behavior beyond these exact bytes. The independent
parser must reject any hash mismatch before solver launch, even when the
changed file would parse to the same values.

## Cross-file semantics frozen by this allowlist

The independent validator derives fixture identity from the full hash tuple,
parses both typed files and `source-boundary.in`, then checks all of these
relations:

- DNS grid counts are `160,84,40`; lengths are `4.0,2.1,1.0 m`; all three
  derived spacings are `0.025 m`.
- DNS `constant_dt=T`, `dt_input=1.0e-4 s`, `time_scheme=ab2`,
  `space_scheme_mom=cen`, `nstep=14`, `time_max=0.0014 s`, and
  `stop_type=T F F`. Source-positive fixtures schedule `[2,12)`; dry fixtures
  schedule `[0,0)`. The derived state/interval counts are 15/14.
- `restart=F`, `late_init=F`, and fixture start time is 0 s. Retain the
  literal checkpoint fields but do not interpret them as restart permission.
- Quiet DNS gravity is `(0,0,0) m/s2`; crossflow gravity is `(0,0,-9.81)`.
  `cfl=0.2` and the source fixed-step factor is `0.2`.
- Quiet source velocity is `(0,0,-4.8) m/s` over background `(0,0,0)`;
  crossflow source velocity is `(-50,0,-4.8) m/s` over background
  `(-50,0,0)`. Source and background tangential components agree. The four
  x/y velocity boundary codes are `P`, the z codes are `D`; V, W, pressure and
  VOF values remain exactly as specified in the referenced typed tables.
- `is_forced` and `is_outflow` are all false; `bvel`, `dpdl`, and pressure/VOF
  value arrays are zero; `bulk_ftype=cfr`. Preserve and compare every boundary
  token, not only the subset currently checked by the source patch.
- VOF records are fixed for all fixtures: `rho1=1000`, `rho2=1 kg/m3`,
  `mu1=1.0e-3`, `mu2=1.8e-5 Pa s`, `inivof=zer`, `nbub=1`, the consumed
  tuple `(0,0,0.5,0)`, surface tension zero, and `late_init=F`. The tuple is
  mandatory even for the empty initial VOF field. Do not equate DNS placeholder
  `rho_sp/mu_sp` with both VOF phases; the VOF build replaces those values with
  `rho2/mu2`.

For the current input-byte allowlist, compare parsed values to the exact
fixture table, not to a generic tolerance. The producer's current cross-file
real comparisons use `1e-12_rp`; that implementation fact is recorded but is
not the independent parser's acceptance rule. Any amendment admitting new
values must prospectively define token grammar, precision, finite/range checks
and whether each duplicate-field relation is lexical, exact-converted-value,
or tolerance based. Units not supported by fixture comments or cited source
use remain unspecified: in particular, do not infer units for `gr` solely
from its declared real type.

## Validation boundary

CPU tests must cover each allowlisted tuple, all per-record token counts and
types, the Q/X DNS variants, each cross-file relation, and one-byte mutations
of every input file. Also reject a hash-correct roster with a mismatched
case_id, a changed but value-equivalent number, extra or missing record/token,
CRLF, BOM, blank line, malformed comments, comma/slash/repetition/null tokens,
and any unlisted extra input. A parser pass proves fixture eligibility only;
it does not authorize a source run or close H4, raw-output, conservation,
resource, receipt, launch or scientific gates.
