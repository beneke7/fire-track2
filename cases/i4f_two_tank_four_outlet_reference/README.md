# Two-tank/four-outlet I4F reference dictionaries

These are the exact small dictionaries from the completed 1,779,258-cell,
20-rank startup stage ending at **0.00502116666404 s**. The source is recorded
in [dictionary-manifest.json](dictionary-manifest.json). They accompany the
[executed solver source](../../solvers/i4f_frozen_sp/README.md).

**Later input correction:** the user confirms that passages downstream of the
valves start with air. This archived primed-line/static-ambient case is not the
current physical baseline. The compact air-filled run and tested reservoir
boundaries are identified in [current status](../../docs/STATUS.md); native
initial fields and restart inputs must accompany any transfer.

This is **not a standalone case**: the native mesh, nonuniform initial fields,
14-field restart and collated addressing remain in the local run bundle and
must be transferred separately. Do not replace them with uniform fields or a
prescribed outlet flow. `decomposeParDict` records the workstation partition,
not a chosen HPC allocation. A site launch requires its own compatible binary,
MPI setup, decomposition, paths and verified restart.

The case is a provisional water/ideal-air reference with 12 bar absolute initial
headspaces, 1.350 m3 tank water each, four zero-thickness divider walls per
outlet, assumed primed lines and scalar valve losses. Additional water in the
lines is reported separately. The 1 s smoothstep and 2% minimum opening are
assumptions; the maker's approximate 5 s refers to discharge duration.

These dictionaries retain the **static ambient pressure/temperature control**.
The alternative compressible reservoir boundary remains a separate controlled
experiment; it is not promoted here. Five milliseconds do not establish a full
discharge, post-ingestion robustness or hardware validity. See the
[published results](../../results/summaries/i4f_20261025/README.md).
