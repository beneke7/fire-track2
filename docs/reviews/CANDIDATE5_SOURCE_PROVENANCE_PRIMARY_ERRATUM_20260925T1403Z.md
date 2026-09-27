# Candidate5 source provenance primary erratum

**Primary provenance correction, 2026-09-25 14:03 UTC.** This append-only
erratum corrects the source locator in the candidate5 producer handoff and the
exact-review memo. It preserves both historical records and does not create a
`candidate-build.json`, OCI receipt, B1/B2 acceptance, or source-run approval.

The pinned upstream commit is
`598210616bebd51f7d51f61455f196e6f3479916`. The exact application driver at
that Git commit is
`src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90`, Git blob
`e0e1b4c232da1e261026e73c95118a4cb36cdd6e`, SHA-256
`1d6450b3379b9995b0d69c0d8e22d8b038c66446ebd33066cfdffdf799616e22`. The
path `src/main.f90` does not exist in that commit. The cited SHA
`ef4e55d8d5d6de489bb6e6c986a5fcc15f44e16170e4cf4add7b9e2559175a03` hashes
the modified application driver in a mutable checkout; it is not an upstream
Git-object identity. Its dirty status and applied patch were confirmed in the
checkout at `/tmp/flutas-pristine-5982106`.

The candidate5 Docker build checks that `/opt/FluTAS` is at the pinned commit,
applies patch `aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7`,
and builds the `two_phase_inc_isot` application. Read-only extraction from the
resulting local image
`sha256:73b7a60de5be7da33fd8af0802a6b70e32a6486d22452b449454eaaafa7d9e43`
matched the exact-patch application independently reconstructed from the
upstream Git objects in Astra's successor review:

| Applied source in candidate image | SHA-256 |
| --- | --- |
| `src/apps/two_phase_inc_isot/main__two_phase_inc_isot.f90` | `206c99e2a0695fa3533bf76877a887fb25e3438b6a13a8eb939fd7e54ee54d6d` |
| `src/restas_source.inc` | `775695dc665e42851bb70e5de6945b775a612509a9fdf3095e7983afa2145732` |
| `src/vof.f90` | `657e4d7e4c7ec0739b506ae806c9bd5e80df7aaa238e248cb9fab4ee43fcea61` |

This corrects the source-file locator and confirms the embedded source snapshot
for those three files. It does not replace a full immutable build receipt,
independent verification of every build input, or a retained OCI layout.
The local image still has no `RepoDigest` and no `candidate-build.json`; source
bundle provenance and release remain blocked. The inaccurate locator does not
alter the separately reviewed source-disabled smoke identity.

Commands used for the correction were read-only Git-object queries and
`docker create`/`docker cp`/`docker rm` on the exact local image. The temporary
container was never started and has been removed. No source solver or GPU job
was run for this correction.
