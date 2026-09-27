# E1 gate inventory exact follow-up

**Review completed:** 2026-09-25 13:17 UTC  
**Disposition: PASS — F1 closed.** The primary corrected the stale case inventory. The E1 gate remains **NOT READY**; this review approves no mesh, characterization, solver run, E1 comparison or E2 advancement.

## Finding closure and gate scope

The current gate now accurately distinguishes the provisional static inputs from a validated or executable E1 case:

- The case/dictionary package exists and has exact review only for static-preparation artifact scope. The gate says it is not meshed or run and does not pass E1.
- The two Figure 13 digitizations are present. The gate says no source-grounded acceptance sampler or comparison result is approved. This is accurate: the configured planes and static helper do not constitute an accepted field-to-observable comparison procedure.
- No mesh or E1 solver run exists. The claimed inventory now distinguishes this from the static case files and dictionaries that do exist.

The correction did not relax the gate. Its status remains **NOT READY** at the heading and in its acceptance conditions; it remains a proposal rather than an accepted experiment record. The correction adds no new mesh or run authorization. The existing gate retains the prior user-authorized allowance for provisional case/mesh preparation and static checks, and explicitly says that this does not authorize a solver run. No preparation or execution was performed in this review.

## Exact opening and closing identities

Opening hashes matched the requested identities. Closing hashes rechecked at 13:16 UTC are identical:

| Artifact | Opening SHA-256 | Closing SHA-256 |
|---|---|---|
| Current gate `experiments/E1_ROUAIX_CASE1_GATE_DRAFT.md` | `8e3efe6a3e7edb91985550ff5c285615e5b26f880e74415cb57962efdb7d9132` | `8e3efe6a3e7edb91985550ff5c285615e5b26f880e74415cb57962efdb7d9132` |
| Primary correction `docs/reviews/E1_GATE_INVENTORY_PRIMARY_CORRECTION_20260925T1313Z.md` | `0cea2c34c6e1f74997e5c0c655d3243ed74eb55caefe5f520b2414a6e3f39fba` | `0cea2c34c6e1f74997e5c0c655d3243ed74eb55caefe5f520b2414a6e3f39fba` |
| Prior integration receipt `docs/reviews/E1_STATIC_CORRECTION_INTEGRATION_20260925T1259Z.md` | `a71ebe32e8158843dcbc5f32c9a6dee527032aadef12cb4ddef197260663291c` | `a71ebe32e8158843dcbc5f32c9a6dee527032aadef12cb4ddef197260663291c` |
| Prior exact review `docs/reviews/E1_STATIC_CORRECTION_EXACT_REVIEW_20260925T1305Z.md` | `49b26e05aa794ee613e1c861d0bba996bcf44915402cdf9cd4065930f3207f94` | `49b26e05aa794ee613e1c861d0bba996bcf44915402cdf9cd4065930f3207f94` |
| Corrected preparation note | `4178ea3201c6960c250831a93320e821a20427908701fd911a747582d02a6fe1` | `4178ea3201c6960c250831a93320e821a20427908701fd911a747582d02a6fe1` |
| `prepare_case.py` | `dd72cec1ace9d75bf109c06afefd056bc4b12fc92f33f3d51d1aa013f6ebf901` | `dd72cec1ace9d75bf109c06afefd056bc4b12fc92f33f3d51d1aa013f6ebf901` |
| `static_preparation.py` | `762583cbaa0b2622b527faa622a9922c053b008dffdbc8104dbac64a293e7507` | `762583cbaa0b2622b527faa622a9922c053b008dffdbc8104dbac64a293e7507` |
| `geometry/domain.json` | `ac4d4ec27ba588e8337d018a781d27ac7d3d33f8dd19b7ec1b6171daeadb5c8c` | `ac4d4ec27ba588e8337d018a781d27ac7d3d33f8dd19b7ec1b6171daeadb5c8c` |
| `CASE_SHA256SUMS` | `3cbc0528bc8b2d9feb35529e85d5bd1b247c92e4f7f28345f53db1ba462cfb8e` | `3cbc0528bc8b2d9feb35529e85d5bd1b247c92e4f7f28345f53db1ba462cfb8e` |
| Focused E1 static tests | `cc20a96961e94015fa04fe1e0e8cfb0b2330bcde7fab65ddde8ae5ee1bb1ffa1` | `cc20a96961e94015fa04fe1e0e8cfb0b2330bcde7fab65ddde8ae5ee1bb1ffa1` |
| 12:07 primary wall disposition | `181ee1644d8611fac003f22eeddc161eaaaac1bea17987c1d709202ed90a7d18` | `181ee1644d8611fac003f22eeddc161eaaaac1bea17987c1d709202ed90a7d18` |
| Earlier E1 static follow-up | `9451052a90ca338501ead2b92658d4b53f83e33fbc35300cb4cdb0f591cef847` | `9451052a90ca338501ead2b92658d4b53f83e33fbc35300cb4cdb0f591cef847` |

The 12:59 integration receipt intentionally preserves the **historical** gate hash `28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7`. The primary correction records that prior identity and the new current gate hash `8e3efe6a3e7edb91985550ff5c285615e5b26f880e74415cb57962efdb7d9132`; its own SHA-256 is unchanged above. The six non-gate artifacts in the integration receipt still match their pinned hashes. The 12:07 memo remains unchanged and records the superseded preparation-note hash `ac47a5fabb9431b26b285647fd26f7715f318a58959d3fe9c1551e622e6618f4`; the corrected note pins that memo, and the integration receipt pins the corrected note and six companion artifacts. The primary correction points to the integration receipt and current gate, while neither the gate nor preparation note points back to the correction receipt. The provenance remains acyclic.

The generated-file manifest was rechecked from `cases/e1_rouaix_case1_static/`; all 20 listed outputs returned `OK`. No tests, builds, mesh tools, solver, characterization or GPU work was run.

## Residual scientific decisions

The gate remains NOT READY because key inputs and acceptance rules remain provisional or unresolved. D-NUT-BC and contact-angle selection still require decisions before characterization. The analytic wall and parameter values remain assumptions; the package has no mesh, mesh-quality or actual nozzle-face evidence, and its zero `p_rgh` field is only a seed that must be initialized after meshing. The reported-versus-recomputed `Re_j` discrepancy, turbulence/model and initial-condition mappings, Figure 13 timing and width semantics, acceptance limits, and mesh/time-refinement rules remain for prospective review. No source-grounded pass/fail E1 comparison or E2 advancement is established.
