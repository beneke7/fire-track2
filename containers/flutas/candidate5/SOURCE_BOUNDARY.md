# Candidate5 source/runtime observability draft

Candidate5 is an implementation draft for the pinned FluTAS source at the
revision recorded in [`source-pin.txt`](source-pin.txt). It carries forward the
synthetic paired-return setup and adds three compact runtime ledgers required
by [`FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md`](../../../experiments/FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md):
phase/property ghost scans, requested/applied boundary-vector scans, and
per-state timestep-restriction records. The source patch and these notes are
not an accepted contract or gate approval.

The implementation targets primary-frozen schema revision 1.2
(SHA-256 `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`).
Its phase contract is alpha-only at `pre_vof_x`, `pre_vof_y`, and `pre_vof_z`,
with alpha/rho/mu scanned only at `pre_momentum`. The schema hash is frozen for
candidate5 implementation, but this does not imply analyzer, source-runtime,
or scientific approval.

The source profile, return calculation, mesh, boundary conditions, fixed
`dt=1e-4 s`, and 14-step schedule remain the inherited diagnostic inputs. Each
case now also supplies an explicit provisional `fixed_step_factor=0.2`. This
factor is a candidate input only; it is not an established stability margin.
The crossflow case is expected to fail the new guard at U0, before its first
advance. Preserve that result and do not change the source profile, step, or
schedule to make it pass.

The three added tables summarize complete scans, retaining
counts, exact mismatch/non-finite counts, maximum absolute error, and the first
failure location and values. Successful arrays are not dumped. An independent
review must determine whether that evidence and the boundary-value comparison
predicate are sufficient. Output order, exact scan sets, and controlled-stop
prefixes are pinned in schema 1.2. The timestep row preserves both source
`dlmin` and `dlmini`, the complete non-heat AB2 bound, and the provisional
factor guard. Before the initial U0 scan, the source also writes the actual
runtime timestep-input snapshot, including all 42 vertical spacing and inverse
operands. `tools/write_run_manifest.py` binds that capture to the exact build,
schema, analyzer, case inputs, three CSV hashes/counts, stop tuple, resources,
and direct-pressure disposition. It assembles identity and counts; the separate
analyzer determines row conformance. This checkpoint produced no runtime
bundle or run manifest.

If independent review finds these summaries insufficient, the next engineering
change is a deterministic per-cell boundary ledger keyed by state, interval,
stage, face/class, component or property, and `(i,j,k)`, carrying requested and
applied values for every scanned cell. That change would add observability only
and would require a prospective schema revision before implementation.

The pinned pressure route uses a direct FFT and tridiagonal solve, not an
iterative residual-controlled solver. The proposed residual treatment is
therefore `not_applicable`; it remains a review decision. No residual limit,
divergence limit, fixed-step margin, or source-runtime acceptance is approved
here.

B1 pre-run eligibility is a review of the exact candidate, inputs, schema,
analyzer, limits, and launcher before execution. Runtime source-on qualification
requires a separate reviewed source run and its complete logs and observables.
Neither gate is passed by this draft.

The candidate has not run the FluTAS solver or CFD. A CPU helper test or build
does not establish B1 pre-run eligibility or runtime source-on qualification.
Candidate4 evidence and review are not inherited as candidate5 approval or
eligibility.
