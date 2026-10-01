# Generic four-slot downward-release AMR probe

This isolated generic downward-release case family compares a coarse uniform
reference, a fixed one-level refinement box, and `dynamicRefineFvMesh`
refining `alpha.water`. Water enters vertically downward from a horizontal
plane at z=4 m while air crosses in -x. This is a mesh-method/cost probe, not
the corrected horizontal Restás four-slot near-field case. The separate
horizontal configuration places four outlets in the vertical x=0 plane and
injects water in +x; its actual geometry and conditions are analyzed in a
second AMR bundle under `results/runs/`. The horizontal comparison and
rendered frames are in
[`restas-hnf-amr-comparison-20260928T154239Z-b42a1d`](../../results/runs/restas-hnf-amr-comparison-20260928T154239Z-b42a1d/comparison.md),
using the untouched uniform fine reference
`restas-hnf-laminar-20260928T145501Z-4fe554`.

All generic-case variants use the same 15.95 m × 6.05 m × 4 m box, four
provisional 1.0 m × 0.15 m slots, 50 m/s opposing crossflow, water-like
properties, laminar closure, fixed 0.1 ms time step, and 0.02 s source/run
horizon. The common starting mesh has 455,392 hexahedral cells. The local
finest spacing is 0.025 × 0.025 × 0.0625 m; both refinement approaches reach
that spacing.

The slots and source are assumptions from the project plan and the prior P0
characterization, not measured hardware data. The 4.8 m/s source is borrowed
from the Calbrix Dash-8 peak and is used as a constant provisional inlet. This
probe measures CPU/mesh cost and short-time plume behavior only. It does not
validate breakup, Restás hardware, full descent, or ground delivery. The
laminar model is held constant to isolate the mesh comparison, despite the
high Reynolds number; turbulence-model implications are discussed in the
comparison handoff.

The frame is aircraft-relative: +x is the streamwise axis, air enters at the
high-x boundary with `U=(-50, 0, 0) m/s` and exits at low x; +z points upward,
the slot plane is at z=4 m, and water enters with `U=(0, 0, -4.8) m/s` under
`g=(0, 0, -9.81) m/s²`. The four 0.15 m × 1.0 m rectangular source patches
are arranged 2 × 2 in x and y. The chosen 0.05 m gaps are explicit assumptions.

The 50 m/s crossflow is the value reported for Calbrix et al.'s Dash-8 water
case (PDF p. 4 / journal p. 1518); its plotted Dash-8 speed peaks at about
4.8 m/s near 0.5 s (PDF p. 5 / journal p. 1519). This run uses that peak as a
constant source for 20 ms; it is not the paper's digitized time history, and
the paper's outlet area/profile are not published. See
[`experiments/E2_CALBRIX_SOURCE.md`](../../experiments/E2_CALBRIX_SOURCE.md)
for evidence classes and gaps. The slot dimensions use the plan's provisional
range and choose its 0.15 m upper end; fluid properties, gravity and 0.05 m
slot gaps remain assumed inputs.

Run with the repository CPU launcher:

```bash
.venv/bin/python scripts/run_local.py --threads 8 --timeout 3600 -- \
  .venv/bin/python cases/restas_amr_probe/run_probe.py
```

Each attempt creates unique ignored bundles under `results/runs/`. The runner
preserves generated case inputs, image/code/input hashes, OpenFOAM output,
sampled Docker resources, pressure iteration counts, time histories, and an
exploratory liquid ledger. `analyze_probe.py` reads reconstructed fields for
cell-level, volume, and shape diagnostics; `render_probe.py` saves a correctly
labelled alpha-water PNG. It makes no scientific validation claim.

The localized static mesh uses a conformal, structured transition, so its
whole-domain cell count exceeds the base mesh even outside the finest box.
The actual cell-volume ratios are reported alongside the nominal fixed-box
level histogram. For AMR, saved `cellLevel` is the authoritative level count.
OpenFOAM's step clock includes mesh-update work but does not time
`dynamicRefineFvMesh.update()` separately; refinement event counts are an
overhead diagnostic, not a mesh-update duration.

## Turbulence-model economics

The present comparison uses laminar closure for all three grids so the mesh
costs remain matched. With 0.15 m characteristic slot width and the stated
properties, the inlet-water and crossflow Reynolds numbers are approximately
7.2×10⁵ and 5.1×10⁵. Laminar therefore serves as a cheap solver/mesh baseline;
it does not model turbulent mixing or eddy stresses. A two-equation realizable
`k-epsilon` RANS model or `k-omega` SST adds transport solves and turbulence
boundary conditions but models mean eddy stresses instead of resolving
instantaneous eddies. Realizable `k-epsilon` is a practical first low-cost
sensitivity; SST has more value if an aircraft body, near-wall shear, or
separation is included, with appropriate wall treatment. OpenFOAM provides
both RANS families in the local v2512 installation. Calbrix et al. report
standard (not realizable) `k-epsilon` for their much larger Dash-8 nearfield
calculation.

Three-dimensional transient LES resolves large eddies and models subgrid
scales, so it can better expose unsteady shear-layer structure. It needs a
finer mesh, small time steps, and credible turbulent inflow or precursor
initialization; it costs substantially more and still does not resolve tiny
droplets on this mesh. It is a later focused physics check, not the economical
default for broad design sweeps. See the official OpenFOAM
[realizable `k-epsilon` documentation](https://doc.openfoam.com/2212/tools/processing/models/turbulence/ras/linear-evm/rtm/realizableKEpsilon/),
[v2512 `k-omega` SST API](https://api.openfoam.com/2512/classFoam_1_1RASModels_1_1kOmegaSST.html), and
[LES guidance](https://doc.openfoam.com/2312/tools/processing/models/turbulence/les/).
