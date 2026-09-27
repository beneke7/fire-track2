# E1 gate inventory correction — primary receipt

**Disposition: correct the stale repository inventory only; the E1 gate remains
NOT READY.** Astra's exact E1 static correction review accepted the corrected
static artifacts at static-preparation scope but returned REVISE because the
gate still claimed those files did not exist. This receipt records the primary
correction; it approves no E1 comparison, mesh, characterization, solver, or
E2 advancement.

## Exact identities

The reviewed predecessor integration snapshot is
`docs/reviews/E1_STATIC_CORRECTION_INTEGRATION_20260925T1259Z.md`, SHA-256
`a71ebe32e8158843dcbc5f32c9a6dee527032aadef12cb4ddef197260663291c`. Its gate
hash was `28e66d27d63204cb275fc447afdde8217695e03963fb2ed591fe365be31c39c7`.
After Astra's review, the primary updated only stale inventory statements in
`experiments/E1_ROUAIX_CASE1_GATE_DRAFT.md`; its new SHA-256 is
`8e3efe6a3e7edb91985550ff5c285615e5b26f880e74415cb57962efdb7d9132`.

The current gate now states that the provisional static case/dictionaries
exist and passed exact static-artifact review, while no mesh or E1 run exists;
the two Figure 13 digitizations exist but no executable comparison sampler or
acceptance result is approved. This edit changes no paper interpretation,
assumption, limit, boundary condition, method, or scientific gate state. The
corrected preparation note, generator/checker/tests, generated outputs and
prior integration receipt retain their reviewed hashes.

This receipt points forward to the new gate identity; the gate does not link
back to this receipt, keeping provenance acyclic. Request an exact follow-up
only to close the stale inventory finding against this updated gate and the
unchanged reviewed static package. Keep the gate NOT READY and all later E1
stages closed until their separate prospective decisions and reviews.
