# E1 static correction exact review

**Review completed:** 2026-09-25 13:09 UTC  
**Overall disposition: REVISE the integrated package record for one stale gate-inventory statement.** The corrected static-preparation artifacts themselves pass this bounded exact review. No source/solver gate or scientific E1 gate is approved.

## Scope and dispositions

I compared all seven artifact hashes in the 12:59 correction integration receipt with the working tree, read the corrected generator, checker, fixtures, current gate draft and preparation note, and checked the prior E1 static review. Every receipt identity matched at opening and closing. I made no changes to those artifacts and ran no mesh utility, solver, characterization case or GPU task.

| Scope | Disposition |
|---|---|
| Corrected E1 static package and the prior M1/M2/nesting/assumption-history corrections | **ACCEPT for static-preparation artifact scope.** The identified defects are corrected and independently reproduced below. |
| Current E1 gate draft's inventory/history | **REVISE.** It still says the repository contains no E1 case, boundary dictionaries or Figure 13 sampler, although the provisional static package now contains them. Correct this dated inventory before the next gate/status disposition. |
| E1 source-grounded comparison, characterization, meshing, solver execution, Figure 13 acceptance, E2 advancement | **CLOSED / NOT APPROVED.** The gate itself remains NOT READY; this review grants none of these approvals. |

## Exact identity and recomputed evidence

The opening hashes from the integration receipt and the closing hashes rechecked at 13:09 UTC are identical:

| Artifact | Opening SHA-256 | Closing SHA-256 |
|---|---|---|
| `experiments/E1_ROUAIX_CASE1_GATE_DRAFT.md` | `28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7` | `28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7` |
| `experiments/E1_ROUAIX_CASE1_STATIC_PREPARATION.md` | `4178ea3201c6960c250831a93320e821a20427908701fd911a747582d02a6fe1` | `4178ea3201c6960c250831a93320e821a20427908701fd911a747582d02a6fe1` |
| `cases/e1_rouaix_case1_static/prepare_case.py` | `dd72cec1ace9d75bf109c06afefd056bc4b12fc92f33f3d51d1aa013f6ebf901` | `dd72cec1ace9d75bf109c06afefd056bc4b12fc92f33f3d51d1aa013f6ebf901` |
| `cases/e1_rouaix_case1_static/static_preparation.py` | `762583cbaa0b2622b527faa622a9922c053b008dffdbc8104dbac64a293e7507` | `762583cbaa0b2622b527faa622a9922c053b008dffdbc8104dbac64a293e7507` |
| `cases/e1_rouaix_case1_static/geometry/domain.json` | `ac4d4ec27ba588e8337d018a781d27ac7d3d33f8dd19b7ec1b6171daeadb5c8c` | `ac4d4ec27ba588e8337d018a781d27ac7d3d33f8dd19b7ec1b6171daeadb5c8c` |
| `cases/e1_rouaix_case1_static/CASE_SHA256SUMS` | `3cbc0528bc8b2d9feb35529e85d5bd1b247c92e4f7f28345f53db1ba462cfb8e` | `3cbc0528bc8b2d9feb35529e85d5bd1b247c92e4f7f28345f53db1ba462cfb8e` |
| `tests/test_e1_rouaix_case1_static.py` | `cc20a96961e94015fa04fe1e0e8cfb0b2330bcde7fab65ddde8ae5ee1bb1ffa1` | `cc20a96961e94015fa04fe1e0e8cfb0b2330bcde7fab65ddde8ae5ee1bb1ffa1` |

The unchanged primary wall-disposition memo is `181ee1644d8611fac003f22eeddc161eaaaac1bea17987c1d709202ed90a7d18`; the preceding E1 follow-up is `9451052a90ca338501ead2b92658d4b53f83e33fbc35300cb4cdb0f591cef847`; the integration receipt is `a71ebe32e8158843dcbc5f32c9a6dee527032aadef12cb4ddef197260663291c`. All three hashes also matched on the closing check. The two local Rouaix PDFs, `/tmp/Rouaix_28516_e1_static.pdf` and `/tmp/Rouaix_28516.pdf`, both hash to canonical SHA-256 `624efe9ee2aec11b85624e9c2ac5364802b12c42657711d211e625052cf28446`.

The earlier preparation-note hash `ac47a5fabb9431b26b285647fd26f7715f318a58959d3fe9c1551e622e6618f4` remains a historical predecessor value embedded in the unchanged 12:07 memo and the integration receipt. The corrected note pins that unchanged memo hash; the new receipt pins the corrected note and its six companion artifacts. The corrected note does not point back to the receipt, so this identity chain is acyclic. The superseded note bytes are not present for a fresh rehash; I verified the historical hash reference, not the replaced bytes.

Recomputed checks:

- `sha256sum --check cases/e1_rouaix_case1_static/CASE_SHA256SUMS`: all 20 generated artifacts pass.
- `.venv/bin/python -m pytest -q tests/test_e1_rouaix_case1_static.py`: **23 passed**.
- Ruff lint and format checks on the generator, checker and focused tests: passed; all three files already formatted.
- Independently generated a fresh package in a temporary directory and byte-compared all 20 outputs plus `CASE_SHA256SUMS` against the reviewed package: **zero mismatches**. Recomputed `domain.json` SHA-256 `ac4d4ec27ba588e8337d018a781d27ac7d3d33f8dd19b7ec1b6171daeadb5c8c` and manifest SHA-256 `3cbc0528bc8b2d9feb35529e85d5bd1b247c92e4f7f28345f53db1ba462cfb8e`.

## Finding

**F1 — Medium, stale current-gate inventory.** The pinned current gate says at lines 41–42 that the repository has “no Rouaix E1 case,” and repeats at lines 106–108 that it has no E1 case, boundary dictionaries or Figure 13 sampler. The reviewed package now contains a provisional static OpenFOAM input case and dictionaries, generated geometry, and a candidate Figure 13 sampler. It still has no mesh or E1 solver run. This is an inventory statement that became stale after case preparation, not a reason to treat the provisional inputs as accepted. Update the gate language to say the static candidate exists but is not yet reviewed/frozen, meshed or run; preserve the existing NOT READY and no-authorization boundary. The primary owns that shared-gate edit.

## Correction-by-correction review

- **PDF identity — resolved.** `prepare_case.py` imports the single pinned `SOURCE_PDF_SHA256` and uses it for both `source.pdf_sha256` and `curved_aircraft_wall.figure3_source_pdf_sha256`. The checker requires both values to equal the canonical constant and each other. The generated `domain.json` contains that one correct hash in both fields. The tests corrupt each field separately and show the identity check rejects each isolated mismatch. Both available local PDF copies match the constant.
- **Fixture-relative geometry — resolved.** The material/geometry checker opens `case_dir.parent / "geometry"` rather than using the package-global geometry path for `domain.json` or `top_wall_nodes.csv`. The temporary-package fixtures mutate copied geometry and assert on the copied case, exercising the intended path.
- **Finite wall coordinates and bounds — resolved.** The checker requires all parsed x/z/y values to be finite, checks x/z against the declared footprint, and checks `0 <= y <= A + allowance`. The helper documents the `.9g` nine-significant-digit rounding half-step. At `A=0.08 m`, the computed allowance is `5e-11 m`; fixtures accept the bound and reject an additional `1e-12 m`, positive overflow above A, negative y, and non-finite coordinates.
- **Isolated `isoAlpha` nesting fixture — resolved.** The separate wrong-method fixture preserves a nested block but changes `isoAlpha` to `plicRDF`. The nesting fixture starts with valid `isoAlpha`, moves that block outside `solvers`, and checks the nesting rule alone. It no longer relies on an already-invalid method block.
- **Assumptions and history — resolved in the preparation note and generated metadata.** The wall is labelled “assumed analytic wall; not source-derived geometry”; its amplitude and length parameters are explicitly assumptions. The note distinguishes gate review 4's historical snapshot from the current amended gate, labels the old capability audit as predecessor evidence, and keeps D-NUT-BC/contact-angle and characterization decisions open. The one residual stale statement is F1 in the current gate draft above.

## Remaining boundaries

The static package records assumptions; it does not establish aircraft geometry, mesh quality, actual nozzle face area, or physical validity. D-NUT-BC and contact-angle selection remain open before characterization. The zero `p_rgh` file remains only a seed and must be replaced after meshing using the declared initialization procedure. Figure 13 timing/width semantics, model and initialization choices, comparison limits, mesh/time refinement, and the characterization contract still require separate prospective decisions and review. Gate draft remains NOT READY for a source-grounded pass/fail comparison. No meshing, solver, characterization, GPU, E1 acceptance, or E2 advancement is approved here.
