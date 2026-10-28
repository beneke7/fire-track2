# Fine Rouaix water field: last saved checkpoint before failure

The requested t = 0.25 s checkpoint was never written. Job 14702499 failed at
t = 0.2496 s after the first catastrophic max-speed row at 0.2495 s. The run
owner verified that the only closed field checkpoint is the unchanged parent
state at t = 0.2000 s. This summary therefore shows that pre-failure initial
state; it does not show the failed continuation or claim a t = 0.25 result.

## Artifacts

- [Wide CPU native-cell surface view at t = 0.2000 s](fine-water-t0200.png)
- [Plume zoom with the same threshold panels](fine-water-t0200-zoom.png)
- [Quantitative metrics and provenance](fine-water-t0200-metrics.json)
- [Static geometry for three reported failure hotspot cells](hotspot-cell-geometry.json)
- [ParaView state with a fitted parallel camera](fine-water-t0200.pvsm)
- Threshold surface files: [α ≥ 0.01](surfaces-t0200/alpha-ge-0.01-t0.2000.vtp), [α ≥ 0.1](surfaces-t0200/alpha-ge-0.1-t0.2000.vtp)
- [Run record and exact commands](../../runs/rouaix-fine-water-view-20261028/README.md)
- [Source helper archive](source-helpers.tar.gz) and [member hashes](source-helpers-manifest.json)
- [Coarse 299,520-cell comparison view at t = 0.3 s](../rouaix_water_view_20261028/water-alpha-001-matched-fields-030.png)

The plotted geometry is the exterior surface of native mesh cells selected by
`alpha.water >= 0.01` and `alpha.water >= 0.1`. Both images use the same nozzle
marker, coordinate axes, and +z projection. The wide image uses the same bounds
as the earlier coarse image at t = 0.3 s. This is qualitative visual context
across different times and grids, not a convergence comparison.

The wide PNG preserves the coarse comparison bounds. The zoom PNG uses
x=[-0.4, 3.6] m and y=[-3.0, 0.35] m with equal aspect; all selected cell
centres are within those limits. The PVSM shows the α ≥ 0.01 surface by default
and keeps the α ≥ 0.1 source available in the pipeline. Its reader paths are
relative to the state file under `surfaces-t0200/`; relocation was verified
with `LoadState(..., data_directory='.', restrict_to_data_directory=True)`.
The state contains a camera and display but no Render or screenshot was
invoked during creation.
The state loaded both threshold readers from the summary directory and a
relocated copy: 52,893 cells at α ≥ 0.01 and 49,026 at α ≥ 0.1. ParaView
printed a nonfatal OpenVKL CPU-device initialization warning while creating
the view proxy; state loading succeeded, and no rendering call was made.

From the repository root, load it with:

```python
from paraview.simple import LoadState

LoadState(
    "results/summaries/rouaix_fine_water_view_20261028/fine-water-t0200.pvsm",
    data_directory="results/summaries/rouaix_fine_water_view_20261028",
    restrict_to_data_directory=True,
)
```

At the t = 0.2 s parent checkpoint, raw alpha spans [0, 1]. Its global
cell-volume integral is 0.250897576446 m³ and centroid is
(0.133797, -1.052436, 0.000252) m. The `alpha >= 0.01` region has 124,708
cells and 0.307307 m³ support-cell volume; the `alpha >= 0.1` region has
117,912 cells and 0.285242 m³ support-cell volume. Their cell-centre bounds
are x=[-0.189, 3.080] m, y=[-2.591, -0.007] m. No selected cell centre falls
outside the displayed bounds.

The field hash is identical to the alpha field in the t = 0.2 parent restart
receipt. Its integrated volume differs from the parent ledger inventory by
-7.05e-10 m³ (-2.81e-9 relative). The failed continuation produced no ledger
summary of its own.

The mapped alpha values follow the 120-rank `cellProcAddressing` map, whose
IDs form an exact cover of all 10,099,265 native cells. ParaView's fine mesh
reader matched the cached global cell order exactly for centres and volumes.
One rank uses OpenFOAM's `internalField uniform 0` encoding; the mapper
expanded it using that rank's exact map length. No alpha values were clipped.

## Static failure-hotspot geometry

Using the same exact mesh and the reported rank-local indices, the cells map to
global IDs 4,998,818 (`max_U`), 4,478,241 (first `p_rgh` extremum), and
4,478,226 (second `p_rgh` extremum). The velocity cell is a six-face
`vtkHexahedron`; the pressure cells are six-face and fifteen-face
`vtkPolyhedron` cells. The logged max-U coordinate and static cell centre differ
by 1.47e-6 m. No pressure-location coordinate was present in the captured
failure receipt.

The second pressure cell is included in the historical `concaveCells` set;
the other two are not. That exact set has 114,008 members. The mesh's independent
signed-plane audit classifies those flags as planar subdivisions and reports no
genuine concavity. Set membership alone does not identify a geometric defect
or explain the solver failure. This check reads static mesh geometry only; it
does not read failed-time pressure, velocity, or phase fields.

This diagnostic does not attribute the later blow-up to the changed pressure
boundary condition. It says nothing about the missing .25 s state or numerical
convergence. The original solver run and its failure evidence remain under
`results/summaries/rouaix_pressure_total_restart_20261028/`.
