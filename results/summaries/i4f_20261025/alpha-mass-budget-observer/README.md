# I4F alpha-source mass-budget observer

This packet records one natural solver timestep from a restarted, corrected
299,214-cell I4F case. It is a discrete accounting and observer-passivity
check, not a trajectory validation or a causal explanation of the later
pressure cycle.

The native step starts from `0.490706656519181661 s` with the solver's natural
`dt = 0.0001066873942806877 s`; the saved endpoint is `0.4908133439132807 s`.
The two 10-rank restart arms use the original physical solver (`4d1b5b47…`)
and the recompiled v3 solver with its observer explicitly enabled (`3ce4de14…`).
Their prescribed fields and numerical controls match; the source change adds
the default-off diagnostic. All 15 endpoint fields plus `uniform/time` are byte
identical. The natural timestep avoids the roughly tenfold timestep reduction
used in an earlier 12-microsecond passivity probe. It is still only one restart
step: it does not establish long-run restart equivalence. The continuous-run
comparison is a scalar step-health row; no same-time continuous field snapshot
was saved.

## Reading the budget

For the native EOS accounting, the emitted signed terms satisfy

```text
Rmass = rho_new*Ralpha + rho_new*S_actual
      + alpha_old*ddt(rho)
      + [div(alphaPhi*rho_face) - rho_new*div(alphaPhi)]
```

The CSV reports signed values and L1 magnitudes in kg/s. `cutoff_at_assembly`
and `source_state_change` partition the actual cached source and are reported
separately; do not add them again to the four-term mass identity. The maximum
absolute signed closure error across the six selected passes is
`1.16e-11 kg/s`.

The selected pressure passes are 1–2 (outer iteration 1), 29–30 (outer 15),
and 31–32 (outer 16). The assembly-cutoff magnitude divided by `|Rmass|` is
about 1.68% in the first outer iteration and 94.0–97.4% in the last four
passes. The source-state-change term is also reported because the source is
cached at assembly and evaluated after the alpha state changes. These ratios
vary across outer iterations; they are not a physical-flow percentage or a
causal attribution.

The prior `80.6%` estimate came from saved `alpha.water` and `dgdt` at
`0.390717595007 s`, using constant `rho=998.2 kg/m3`. It did not capture the
cached source at assembly. The later natural-step records show why that
endpoint estimate cannot be generalized, but they do not retroactively measure
the missing source at `0.390717595007 s`.

The earlier v2 observer emitted a near-singular uncapped reference with 3,957
undefined cells and terms around `1e41 m3/s`. That is an ill-conditioned
counterfactual, not a realized source flux; it is preserved in the private run
bundle and excluded from the v3 mass budget.

## Source reconstruction and reproduction

`source-from-public-physical-alpha.patch` is a direct patch from the published
71-file physical-alpha source closure to the captured 75-file v3 observer
source. `source-manifest.json` records the base, target hashes, pinned image,
and executed binary hash. The patch reproduces all captured target source
hashes, but this packet does not claim that a fresh public-source rebuild
produces the same binary. The exact case and solver log remain in the private
run bundle recorded in `healthy-natural-step-proof.json`; this packet does not
contain the mesh, fields, or log and is not a standalone CFD case.

From the repository root, rebuild the public source closure in a temporary
directory with:

```sh
.venv/bin/python results/summaries/i4f_20261025/alpha-mass-budget-observer/verify_public_v3_source.py
```

To regenerate the selected CSV from the preserved private v3 Pout log:

```sh
.venv/bin/python results/summaries/i4f_20261025/alpha-mass-budget-observer/extract_natural_step_budget.py \
  --log results/runs/i4f-alpha-source-mass-observer-gap-20261027T044519Z/arms/native-natural-dt-attempt001-20261027T0542Z/logs/restart-observer-v3-explicit-on-solver.log
```

The extractor writes to stdout by default. `--output PATH` writes a new file
and refuses to overwrite an existing path. The four synthetic tests validate
the finite source-partition algebra at pure-phase endpoints, subnormal phase
fractions, differing predictor/corrector coefficients, and changed source
state; they do not validate the physical solver.
