# Water transport and pressure feedback

These are eight repeated equation updates at a fixed physical time, 0.493844492237 s, reached from the same original warm seed and 299,214-cell apparatus. They are not eight new physical timesteps or discharge checkpoints.

Holding water transport fixed gives pressure updates 16.47 → 1.92 → approximately 0.42–0.48 Pa. Allowing the stock water-transport update gives 827.30 → 1063.72 Pa, with velocity updates 3.94 → 5.08 m/s. Both hold shared temperature, transported turbulence and old-time histories fixed. Every declared held-field check passed. The rederived phase temperatures use the predeclared 128-epsilon floating-point invariant; their numeric test records remain in the local raw bundle.

This isolates a sufficient water/mechanical feedback path at one state. It does not distinguish limiter switching, coefficient lag, flux inconsistency or a geometric trigger. Maxima can move between cells, so these tables do not prove a signed two-cycle. A small total inventory change is not proof of local equation convergence.

Each arm contains its original experiment and launch record, raw summary CSV, source manifest and a new direct patch from the published exact immediate-parent source. Root applied each patch to a separate clean copy of that public base and verified every declared source hash. The base can contain additional build products: matching declared files does not mean an identical directory tree. No fresh binary rebuild or long-trajectory identity test is claimed. The launch records identify the executed binaries and pinned image. Full native seeds, mesh and remaining raw logs are still local requirements for rerunning the apparatus.

Use `patch --batch --forward -p1 -i <absolute-arm-patch-path>` in a fresh copy of `../immediate-parent-source/build/source/v8-restart-cold`, then `sha256sum -c <absolute-arm-source-tree.sha256>`. Apply each arm independently to the base, not sequentially.
