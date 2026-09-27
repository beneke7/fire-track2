# Candidate5 timestep time-field decision

**Primary decision: retain schema v1.2 unchanged.** This is an implementation
interface decision; it accepts no producer/analyzer implementation, B1/B2
production bundle, source run, or scientific gate.

The exact reviewed schema is
`experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md`, SHA-256
`4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`.
Its `timestep-restriction.csv` contract defines row `k` as state `U_k` at
`time_s = t_0 + k*dt` (schema lines 142–156), and the source input captures
`time_start_s` (line 294). The exact Astra review
[`FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md`](FLUTAS_CANDIDATE5_EXACT_REVIEW_20260925T1240Z.md),
SHA-256 `b5cf3036bf7a79a2ad4b149889faf10e3d407e169191b80c311c61e9e19cfd68`,
found that producer currently writes the accumulated AB2 solver clock, which
differs at state 2 from the schema's index-multiplied diagnostic time.

Therefore `time_s` must be emitted using the frozen index-based operation
`time_start_s + real(state_index,rp)*dt`, with the declared `real_kind` and
arithmetic order. Keep the solver's accumulated clock in its existing
solver-native output/log when that clock must be inspected; do not relabel that
value as `time_s`, add a field to the frozen CSV, or add post hoc tolerance.
The producer handoff must include a multi-state compiled-output-to-independent-
analyzer fixture, including state 2 and pulse edges, to verify serialized
bytes and parser agreement. This does not claim that an actual source run has
occurred.

The primary accepts Astra Warden checkpoint 10's ranked recommendations for
producer fixes, analyzer fixes, staged-input/provenance/conservation/launch
contracts, append-only E1 receipt, and frozen crossflow expected-negative
fixtures. Owners and exact acceptance evidence are recorded in
`docs/BLOCKER_RESOLUTION_PLAN.md`. User data are not required for these
engineering deliverables.
