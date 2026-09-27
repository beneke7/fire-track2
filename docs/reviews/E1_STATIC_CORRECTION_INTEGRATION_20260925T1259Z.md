# E1 static correction integration receipt

**Primary disposition: implementation handoff integrated; exact independent
review required.** This receipt records the corrected static-preparation
package after Astra's exact follow-up returned REVISE. It does not pass the E1
static gate, authorize meshing, characterization, solver execution, or Figure
13 comparison.

## Provenance chain

The 2026-09-25 12:07 primary wall-amendment disposition is preserved without
modification at
`docs/reviews/E1_WALL_AMENDMENT_PRIMARY_DISPOSITION_20260925T120700Z.md`,
SHA-256 `181ee1644d8611fac003f22eeddc161eaaaac1bea17987c1d709202ed90a7d18`.
It records the then-current preparation-note hash
`ac47a5fabb9431b26b285647fd26f7715f318a58959d3fe9c1551e622e6618f4`.
The corrected preparation note retains that memo as historical predecessor
evidence and pins its unchanged hash. This receipt adds the corrected package
identity without editing the memo or creating a circular parent/hash update.

## Exact corrected identity

| Artifact | SHA-256 |
| --- | --- |
| `experiments/E1_ROUAIX_CASE1_GATE_DRAFT.md` | `28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7` |
| `experiments/E1_ROUAIX_CASE1_STATIC_PREPARATION.md` | `4178ea3201c6960c250831a93320e821a20427908701fd911a747582d02a6fe1` |
| `cases/e1_rouaix_case1_static/prepare_case.py` | `dd72cec1ace9d75bf109c06afefd056bc4b12fc92f33f3d51d1aa013f6ebf901` |
| `cases/e1_rouaix_case1_static/static_preparation.py` | `762583cbaa0b2622b527faa622a9922c053b008dffdbc8104dbac64a293e7507` |
| `cases/e1_rouaix_case1_static/geometry/domain.json` | `ac4d4ec27ba588e8337d018a781d27ac7d3d33f8dd19b7ec1b6171daeadb5c8c` |
| `cases/e1_rouaix_case1_static/CASE_SHA256SUMS` | `3cbc0528bc8b2d9feb35529e85d5bd1b247c92e4f7f28345f53db1ba462cfb8e` |
| `tests/test_e1_rouaix_case1_static.py` | `cc20a96961e94015fa04fe1e0e8cfb0b2330bcde7fab65ddde8ae5ee1bb1ffa1` |

The primary independently recomputed the listed hashes and ran
`sha256sum --check` on all 20 generated artifacts in `CASE_SHA256SUMS`; all
passed. The implementer reports 23 focused tests, Ruff and format checks, and
deterministic write/no-write/repeat-generation comparisons across all 21
outputs as passing. Nineteen generated artifacts remained byte-identical; the
intended `geometry/domain.json` identity correction was the only generated
change. The full implementation handoff is in the corrected preparation note.

The fix addresses the reviewed conflicting source-PDF identity, fixture-path
resolution, finite coordinates and declared wall bounds, isolated valid-alpha
nesting test, and stale assumption/provenance wording. The analytic wall stays
an explicitly assumed static input. D-NUT-BC, contact-angle selection,
characterization requirements, E1 execution, and Figure 13 acceptance remain
open. Request a new Astra exact review against this receipt and the hashes
above before any next E1 static gate disposition.
