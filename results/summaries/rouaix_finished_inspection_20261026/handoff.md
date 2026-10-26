# Finished HPC run inventory follow-up

Updated 2026-10-26 18:52 UTC. Scope is read-only job evidence recovery and updates to this inventory directory. The raw batch `sacct` capture remains byte-identical (SHA-256 `26301b29f8a48d724051dd349be27a2aa0869fd9f136d272096376ad16eaa6a2`). Curator-enriched `baseline-analysis.json` metadata now has the current hash: reduced-pressure units are clarified as Pa, the final wall-time value replaces the stale `solver_elapsed` field, and CPU accounting scopes are explicit. The raw solver log bytes are unchanged (SHA-256 `5703f0690f59f5e6767177b5cbb12313b5b86723e6c2baa7986995579d3db406`).

## Inventory coverage

- 64 project attempts: 18 `COMPLETED`, 19 `FAILED`, 15 `CANCELLED`, 7 `CANCELLED by 16018`, and 5 `PENDING` in the captured accounting sample. They group as 26 Komondor tutorial, 12 wide tutorial, 22 Rouaix E1, and 4 native mesh QA attempts.
- 19 control/support attempts: 14 `COMPLETED`, 1 `FAILED`, 3 `CANCELLED by 16018`, and 1 `CANCELLED while PENDING`.
- Exact current pending candidate IDs remain `14650641`, `14651174`, `14651178`, `14651185`, and `14652548`. No scientific gate pass is asserted.
- `audit-gaps.json` has 12 tracked findings. All 36 file references in that file now resolve and have SHA-256 values; the prior incorrect 14643873 `checkMesh.log` path was corrected to `outputs/failed-14643873/extracted/checkMesh.log`.

## Resolved and classified evidence

- **14652546, P0 Rouaix baseline:** exact HPC runroot is `/project/nk_meshapplied/bene/fire-track2-hpc/rouaix-percore-p0-source-v2-20261026/rouaix-e1hpc-14652546.jy6p_bzq/attempt/case`. The hash-bound terminal analysis is [baseline-analysis.json](../../rouaix-p0-terminal-inspection-20261026/baseline-analysis.json), SHA-256 `fc2a4d42a9f24664b3d969b244217515126c5cc297d78c228693f0c12a0bad6a`. It records 100 steps through 0.01 s, 801 linear solve records within their configured residual criteria, and a 100-row mass ledger: injected `12.516443202976454 kg`, final inventory `12.516443202976433 kg`, closure `-2.1316282072803006e-14 kg`. The missing terminal-audit gap is resolved. Momentum closure, physical interpretation of extreme fields, and formal E1 acceptance remain unestablished.
- **14641244, Komondor tutorial parser failure:** current `scripts/hpc_metrics.py` reparsed the stored log to 100 steps from 0.001 to the declared 0.1 s endpoint. Reparse output SHA-256 `20113c23fb3832d06f5e1921ba02a2a6cfcf2231b1fbd35b94013bac3251daff`; parser source SHA-256 `9fa244d633bd37932da253e275acfb7a8d4b182a817bb56bf060195abef89d7b`. It finds no parsed fatal/divergence marker, `alpha.water` bounds `[0, 1]`, max bulk Co `0.438229`, and max interface Co `0.427342`. The wrapper failed because it expected an old `fieldMinMax.dat` column layout. The only water-volume sample is the endpoint (`6.191778e-4 m3` in a `4.962599e-3 m3` domain); no initial phase inventory or phase flux is stored, so mass and momentum budgets are unavailable.
- **14641346, 100-rank tutorial scale attempt:** read-only recovery of declared batch stdout yielded `ERROR: RUN_DIR must be directly beneath /project/nk_meshapplied/bene/fire-track2-hpc`. Local capture SHA-256 `1b2804415cd021c3e6357153ed77c05be22a7254958f8421bbf9b21fea6f891e`. This identifies a wrapper preflight refusal before solver startup. The interpolated `RUN_DIR`, exact reason its parent check failed, and runroot remain unknown; no timestep ran.
- **14643854 and 14643873, native mesh QA:** both inputs have the same five `polyMesh` core hashes as the qualified 10,099,265-cell final cast-only mesh (manifest SHA-256 `4347c663a52b3dda878f0b32d60b4ff485a767417b784e89145c6adc0298d670`). Job 14643873 captured the native set and matched the Foundation reference exactly: 114,008 IDs, symmetric difference 0 (comparison SHA-256 `920b2d5005ede69691de1ada659129a96ef1485540933753e5e33656c9c8ac91`). The existing binary-plane screen (SHA-256 `b8194ee0f417483c54a284d29efc40d33e272fd64c04db179ead20bb712b1ca1`) explicitly identifies `final-cast-only`, the same 10M mesh, and examines only flagged cells. Both native reports still show one concavity failure/no `Mesh OK`; this is not an E1 pass. The 14643854 archive itself did not retain a per-cell set, so its ID identity is linked through exact core-mesh hashes and the later capture. No hash match to a separate historical ~35M geometry was established.

## Remaining unknowns

- 14641346 exact failed `RUN_DIR` value and exact HPC runroot.
- No mass/momentum budget for 14641244; only its endpoint water-volume output survives.
- No independent momentum budget or physical field interpretation for P0 14652546.
- No evidence here that links the 10M final cast-only mesh audit to any separate ~35M mesh. Native checkMesh failures remain recorded for both jobs.
- The five pending job states are a scheduler snapshot only; they have no terminal numerical result in this inventory.

## Updated artifacts

- `inventory.json` SHA-256: `4c2a9024ebb3c070fdb510c11606b7f1a8908fc9a2116e072d3da06ae6340d58`
- `audit-gaps.json` SHA-256: `dd6768adebc04aeba90e78c008f068107ca41cb8dc55ccf45931c85ff32f3e3a`
- `sacct-batch-exact-jobids.parsable` SHA-256 unchanged: `26301b29f8a48d724051dd349be27a2aa0869fd9f136d272096376ad16eaa6a2`

## Criteria for root review

- Keep scheduler state, wrapper exit, solver termination, and numerical verdict as separate fields. A parser-only classification needs evidence that the solver reached its declared horizon and the later wrapper/parser stage caused the job failure; it does not make the run a conservation or validation pass.
- Treat a CFD attempt as fully audited only when its declared horizon, raw solver completion, convergence series, and applicable mass/momentum accounting are backed by retained outputs. P0 14652546 has a mass ledger but no independent momentum balance; 14641244 lacks inputs for either budget.
- Keep the existing mesh exception scoped to the exact 10M core mesh hashes and exact flagged-ID set. A changed mesh hash, including any separate ~35M geometry, needs its own evidence. Preserve the native checkMesh failure; do not relabel it as a native pass or E1 acceptance.
- Apply the experiment's existing predeclared E1 observables, tolerances, refinement requirements, and independent review. This inventory proposes no new numerical tolerance or gate threshold.
