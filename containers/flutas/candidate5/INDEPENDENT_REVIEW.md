# Candidate5 independent review record

**Status: pending.** This file is a review checklist, not an approval. No
independent review of the exact candidate5 patch, manifest, analyzer, or build
evidence has been completed. Candidate4's review and disposition do not apply
to candidate5.

Candidate5 adds runtime observability for phase/property ghost states, the
requested/applied boundary velocity, and the pinned non-heat AB2 timestep
restriction. The current primary-frozen observability schema is revision 1.2,
SHA-256 `4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492`.
That schema is frozen for implementation. No independent source, serializer,
analyzer, build, B1 pre-run, or runtime review is recorded here, and no gate is
cleared by this implementation note.

The independent review should verify the pinned source delta and all case and
analyzer hashes; every scan range, key, order, and count; first-failure and
non-finite behavior; exact property and velocity comparison semantics; stage
and state joins; the complete AB2 bound and configurable factor; the preserved
crossflow guard failure; the direct FFT/tridiagonal pressure path's proposed
residual treatment; and positive and negative analyzer tests.

The local code-object build evidence is separate from a solver run and cannot
substitute for the candidate-build receipt and run manifest required by the
frozen schema.

Candidate5 review must independently verify the exact source and input hashes,
stage arrays, every full scan and first-failure case, exact AB2 operation order,
the preserved crossflow guard failure, strict output parsing and stop prefixes,
and the proposed direct-pressure residual `not_applicable` disposition.

Host helper checks and a successful code-object build establish instrumentation
and compilation behavior only. They do not establish a source-run pass, B1
pre-run eligibility, runtime source-on qualification, pressure residual
acceptance, solver stability, or scientific validity. Candidate4's review and
disposition do not apply to candidate5. Any source runtime requires a separate
primary launch decision after exact candidate, inputs, analyzer, numerical
limits, and independent review are complete.
