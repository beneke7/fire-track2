# Alpha-source denominator-floor sensitivity

This packet captures one matched native timestep from the corrected 299,214-cell
finite-water I4F case. The compared dimensionless denominator floors are the
captured default `1e-4` and a single trial at `1e-5`. All other solver inputs,
source settings, EOS, seed, timestep and numerical controls were held fixed.

The default arm reproduced all 16 saved native entries byte-for-byte against
the published v3 observer endpoint. The lower-floor arm changed 15 fields,
while `uniform/time` remained byte-identical. At the final outer iteration,
the signed whole-domain water mass residual fell from `-0.02201` to
`-0.00496 kg/s`; its L1 magnitude fell from `0.09573` to `0.07862 kg/s`.
The assembly cutoff contribution changed from `-0.02142` to `-0.00426 kg/s`.
The minimum raw pressure differed by less than 1 Pa, and neither arm reported
a raw pressure-floor contact or clipped water. These are single-step
sensitivities. They do not show that changing the floor improves a later
trajectory or explains pressure-cycle behavior.

The logs report whole-domain phase inventories and physical-boundary phase
flux totals. They do not provide a tank-only inventory or a dedicated native
valve-seat flux observer. The packet does not contain a standalone case or
full solver logs; the exact local run bundle and checkpoints are identified
in `sensitivity.json`.

## Source closure and reproduction

`source/from-published-v3.patch` is applied directly to the published 75-file
v3 source closure. The verifier reconstructs the public physical-alpha and v3
source from their published parent manifests and patches, then checks every
target source-file hash. The six changed solver source files are also included
under `source/target-files/`; their hashes are checked by the same verifier.

```sh
.venv/bin/python results/summaries/i4f_20261025/source-cutoff-sensitivity/verify_source_closure.py
```

It prints JSON to stdout. Optional `--output PATH` writes a new report and
refuses to overwrite an existing path. `sensitivity.json` contains the exact
binary/image/source hashes, launch identity, native output hashes, and
comparison scope. `outer-and-mass-budget.csv` contains matched per-outer and
per-pressure-pass diagnostics extracted from the preserved attempt logs.

To render the plot from those local logs, run:

```sh
.venv/bin/python results/summaries/i4f_20261025/source-cutoff-sensitivity/plot_outer_metrics.py \
  --default-log results/runs/i4f-alpha-source-floor-sensitivity-20261027T061106Z/arms/native-step-002/logs-attempt004/default-1e-4-solver.log \
  --trial-log results/runs/i4f-alpha-source-floor-sensitivity-20261027T061106Z/arms/native-step-002/logs-attempt004/explicit-1e-5-solver.log \
  --output results/summaries/i4f_20261025/source-cutoff-sensitivity/outer-sensitivity.png
```

The plot helper writes PNG bytes to stdout if `--output` is omitted; a supplied
output path is opened exclusively and is never overwritten.

The six focused parameterization tests are in `test_floor_parameterization.py`.
They cover the default value, invalid values, positive and negative source
branches, and routing of the same runtime parameter through coefficient and
diagnostic paths. They are source-level checks, not a solver validation.
