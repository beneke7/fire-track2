# Candidate5 crossflow startup guard arithmetic — primary check, 2026-09-25 12:19 UTC

**Result: expected guard rejection at U0 for both frozen crossflow fixtures.**
This is a primary binary64 reconstruction from the accepted schema's pinned
source equations and exact case inputs. It is not a solver run or runtime
observation. The two cases remain negative guard fixtures; do not launch either
as source CFD with these hashes.

The exact accepted interface is schema v1.2, SHA-256
`4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`. Its
pinned arithmetic uses FluTAS `src/chkdt.f90` SHA-256
`68e9f9592220b6f7a80366e60ccceb0595685d7324977c3710656aab15b0e661` and
`src/apps/two_phase_inc_isot/param.f90` SHA-256
`153519b5efb1be6b454a57a7bb6a96d7803511effe5d376e4b993df8cd8e4507`.
Both inputs declare `dt=1e-4 s`, factor `0.2`, 50 m/s background crossflow,
gravity magnitude `9.81 m/s²`, and a 25 mm minimum grid spacing. The shared
DNS and VOF files are identical; the source-boundary inputs differ only in the
source activity/mask case.

| Case input | SHA-256 |
|---|---|
| `candidate5/cases/source_boundary/dry_crossflow/dns.in` | `574bcfe3afa0c17284677f78a28b5bdad70e97c80a32ee0dc8af1651227da7b7` |
| `candidate5/cases/source_boundary/dry_crossflow/source-boundary.in` | `7bbb8cdd01a06ae6bcbfe47fb448d9cf5a61f3bb2ae82b7a83c6b688be1024db` |
| `candidate5/cases/source_boundary/dry_crossflow/vof.in` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |
| `candidate5/cases/source_boundary/crossflow_four/dns.in` | `574bcfe3afa0c17284677f78a28b5bdad70e97c80a32ee0dc8af1651227da7b7` |
| `candidate5/cases/source_boundary/crossflow_four/source-boundary.in` | `55f485ce507b8d19fa05c4324308028696ef50ddfe3faec2bab6b1a242e201ec` |
| `candidate5/cases/source_boundary/crossflow_four/vof.in` | `2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54` |

Using the declared uniform startup profile `U_0=(-50,0,0) m/s`, the source
rate estimate is `dtic_raw=50/0.025=2000 s^-1`. With `nu_max=1.8e-5 m²/s`,
`dtiv=0.1728 s^-1`, `dtig=sqrt(9.81/0.025)=19.809088823063014 s^-1`, and
`dtik=small=7.021666937153402e-9 s^-1` from the pinned binary64 definition,
the schema's source-order AB2 restriction gives:

| Quantity | Value |
|---|---:|
| `dtmax` | `0.00049990777606081648 s` |
| `factor * dtmax` at `factor=0.2` | `0.000099981555212163303 s` |
| frozen `dt` | `0.0001 s` |
| `dt / dtmax` | `0.20003689638113265` |
| guard result | `false` |

The frozen step exceeds the guard limit by `1.8444787836701315e-8 s`
(`0.0184447878%` of the step). The minimum factor for this static U0 estimate
is `0.20003689638113265`. The accepted candidate helper's existing
`test_provisional_gamma_fails_frozen_crossflow_arithmetic` independently
asserts the same failure; the producer must still capture actual runtime
operands and fail closed in the reviewed build.

## Primary disposition

Keep both frozen crossflow cases and factor `0.2` unchanged as explicitly
expected-negative startup-guard fixtures. Do not consume U0, run dry-crossflow
or source-crossflow CFD, or report crossflow qualification for these inputs.
Quiescent `dry_four`, one-slot and four-slot checks remain separate potential
stages after their gates pass. Positive crossflow qualification requires a
prospective versioned case/gate amendment and exact independent review before
execution. Any changed factor, step or pulse indexing must preserve or
explicitly redeclare the pulse duration, source dose and observation horizon;
there is no silent tolerance relaxation here.

This disposition implements the Warden's safe option to retain negative
fixtures. It does not accept the B1/B2 contract or authorize any CFD/GPU source
run. No solver or GPU process was launched for this calculation.
