# Rouaix coarse water field comparison

This is an exploratory matched-field comparison of two completed total-pressure
water-nozzle cases at t = 0.3000 s. Both use the same 299,520-cell coarse mesh,
8 MPI ranks, and source physics; the fixed time steps are 0.0001 s and
0.0003 s. The comparison is a temporal-sensitivity diagnostic, not a
time-convergence result or an E1 validation pass.

## Evidence

- [Field comparison receipt](field-comparison.json) contains the exact
  cell-order map, source archive hashes, cell-integrated water volumes,
  alpha-difference metrics, and threshold support extents.
- [Matched field view](water-alpha-001-matched-fields-030.png) shows cells with
  alpha.water >= 0.01 from the same orthographic +z view, in physical
  nozzle-relative coordinates. The cross marks the nozzle reference at
  (x, y) = (0, 0) m.
- [Visualization receipt](visualization-receipt.json) records the CPU-only
  render backend, view bounds, source hashes, VTK surfaces, and figure hash.
- [Source helper archive](source-helpers.tar.gz) preserves the four analysis
  scripts without duplicating them as an unpacked tree. Its member paths,
  source paths, and per-file hashes are in
  [source-helpers-manifest.json](source-helpers-manifest.json). The archive
  SHA-256 is 3a7ab9b1d4d6d925265a1d39e0b179f45ae4039175bd98c78d2aaebca11c81c4.
- [Saved ParaView state](water-alpha-threshold-comparison.pvsm) is saved
  without calling ParaView's renderer.
- The prepared fixed-step continuation is under
  results/runs/rouaix-water-view-20261028/continuation-to-09999/. It is held
  and no solver was launched.

## Field comparison

The volume-weighted integral of the absolute alpha difference is
0.19011784 m3, or 0.5014 of the 0.0001 s run's water volume. Half of that
L1 value, 0.09505892 m3, is the minimum amount that would need to be
redistributed between cells to explain the difference. It is about 25.1% of
the water volume; it does not mean that half the water mass was lost. The two
field water volumes differ by only 2.00e-7 m3, while their mass centroids
shift by 0.08742 m (mostly in x).

| Cell threshold | dt (s) | Cells | x extent (m) | y extent (m) | Cells at x >= 10 m |
|---|---:|---:|---:|---:|---:|
| alpha >= 0.01 | 0.0001 | 1,680 | -0.175 to 14.950 | -5.800 to -0.025 | 4 |
| alpha >= 0.01 | 0.0003 | 1,695 | -0.175 to 14.950 | -5.800 to -0.025 | 4 |
| alpha >= 0.1 | 0.0001 | 1,399 | -0.175 to 4.389 | -4.600 to -0.025 | 0 |
| alpha >= 0.1 | 0.0003 | 1,394 | -0.175 to 3.722 | -3.786 to -0.025 | 0 |
| alpha >= 0.9 | 0.0001 | 811 | -0.175 to 0.475 | -2.500 to -0.025 | 0 |
| alpha >= 0.9 | 0.0003 | 806 | -0.175 to 0.375 | -2.071 to -0.025 | 0 |

The far patch near x = 14.95 m consists of four cells per arm at the
0.01 threshold, with cell-support volumes 0.2043 m3 and 0.3701 m3 for the
0.0001 s and 0.0003 s arms, respectively; none of those cells reaches
alpha = 0.1. It is a dilute, coarse-grid threshold tail, not the high-alpha
jet core. The figure displays thresholded finite-volume cells and does not
interpolate them into a continuous interface.

Both global alpha fields were assembled using the exact 8-rank
cellProcAddressing produced from the same native mesh. The mapped water
volumes close to the solver ledger within 3.2e-8 relative for dt = 0.0001 s
and 5.7e-9 relative for dt = 0.0003 s. The map covers every native cell once.

## Continuation status

The prepared continuation starts from the dt = 0.0003 s checkpoint at 0.3 s
and uses fixed deltaT = 0.0003 s for 2,333 steps to t = 0.9999 s. It remains
held as a temporal-sensitivity follow-up because the matched 0.3 s fields
differ materially in spatial distribution. It is not an accuracy baseline,
and the preparation is not a launch authorization.

The source archive was created with:

    env COPYFILE_DISABLE=1 tar -czf results/summaries/rouaix_water_view_20261028/source-helpers.tar.gz -C results/runs/rouaix-water-view-20261028 compare_fields.py extract_native_mesh.py render_alpha_comparison.py prepare_continuation.py
