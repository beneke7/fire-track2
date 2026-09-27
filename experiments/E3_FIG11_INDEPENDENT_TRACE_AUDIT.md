# Independent read of Calbrix Fig. 11(a)

**Decision:** the second read supports figure-reading reproducibility at a few
counts, but Fig. 11 remains descriptive only. It does not establish an
equivalent quantitative benchmark observable because the authors' structure
reconstruction method is unpublished and the paper does not report the plotted
sampling cadence.

## Source and observable

The requested `papers/Calbrix_2012.pdf` path is absent. The sole local match is
[`Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf`](../Numerical%20simulation%20of%20aerial%20liquid%20drops%20of%20Canadair%20CL-415%20and%20Dash-8%20airtankers.pdf), SHA-256
`128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4`, which
matches the hash in [`E3_CALBRIX_CL415_SOURCE.md`](E3_CALBRIX_CL415_SOURCE.md).
The figure is PDF p. 10 / journal p. 1524, Fig. 11(a); the explanation of the
Matlab reconstruction is PDF p. 8 / journal p. 1522. The red trace is the
number of identified liquid structures with `0.001 <= alpha_L <= 1`; blue is
`0.9 <= alpha_L <= 1`. The paper says the lower threshold includes additional
small, sub-grid fragments. These are **identified liquid structures, not
parcels**. Both thresholds come from the same simulation and reconstruction.

The article reports neither the plotted sampling times nor the MATLAB
structure-identification algorithm. The 0.1 s reads in the CSV are this
digitizer's chosen sample grid, not reported solver output times. A matching
curve therefore cannot show that a new solver used the same connectedness,
filtering, or structure-count definitions.

## Independent extraction method

[`digitize_calbrix_e3_fig11_independent.py`](../scripts/digitize_calbrix_e3_fig11_independent.py)
renders the full page at 300 dpi (2481 x 3249 pixels). It does not reuse the
first trace's crop or pixel coordinates. The x calibration regresses all seven
vector-text tick-label centers from 0 to 3 s; the y calibration regresses all
nine 0-to-400 labels after locating their horizontal tick marks in the fresh
raster. Maximum calibration residuals are 1.25 px horizontally and 0.94 px
vertically. Red and blue pixels are separated by RGB dominance masks, the
legend rectangle is excluded, and a local Theil-Sen fit through per-column
pixel medians estimates each trace center at the target time. Counts are
rounded to the nearest integer. The red value at 1.1 s is 420, above the
highest labeled y tick; it is a linear-axis extrapolation, not interpolation
between labeled count ticks.

The CSV uses heuristic figure-read allowances of +/-5 counts and +/-0.025 s.
They are not reported by Calbrix et al. and are not confidence intervals. The
time and count reads are correlated along each trace; on the steep red rise,
horizontal read uncertainty can move the corresponding ordinate by many
counts. The existing first trace assigns +/-5 counts and +/-0.01 s. These
bounds describe raster reading only, not source-method, timestep, grid, or
simulation uncertainty.

## Comparison with the first extraction

Both CSVs contain 30 reads per trace at nominal times 0.1 to 3.0 s. Differences
below are independent-read minus first-read counts:

| Trace | Mean signed difference | MAE | RMSE | Largest absolute difference |
| --- | ---: | ---: | ---: | ---: |
| Red, `0.001 <= alpha_L <= 1` | +0.50 | 1.37 | 1.85 | 4 at 0.9 s (258 vs 262) |
| Blue, `0.9 <= alpha_L <= 1` | +0.27 | 0.33 | 0.73 | 2 at 0.4 s (2 vs 4) |

At matched nominal times every difference is inside the two vertical read
allowances combined (10 counts). This is a check on reading the same printed
raster, not independent experimental evidence or a pass/fail result; the
correlated horizontal uncertainty must be retained when comparing steep parts
of the curves. Do not score a CFD run against this trace as a quantitative E3
gate until the source's structure-detection definition and comparison-time
selection are recovered or independently shown equivalent.

## Reproduction and checks

The source identity/page were checked with:

```sh
sha256sum "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
pdfinfo "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf"
pdftotext -f 8 -l 10 -layout "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf" -
mkdir -p /tmp/calbrx_independent
pdftoppm -f 10 -l 10 -r 300 -singlefile "Numerical simulation of aerial liquid drops of Canadair CL-415 and Dash-8 airtankers.pdf" /tmp/calbrx_independent/page10
```

The independent output is reproduced with:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/digitize_calbrix_e3_fig11_independent.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/digitize_calbrix_e3_fig11_independent.py --output /tmp/calbrx_independent/reproduction.csv
cmp -s data/derived/calbrix_cl415_fig11_structure_counts_independent.csv /tmp/calbrx_independent/reproduction.csv
.venv/bin/ruff check scripts/digitize_calbrix_e3_fig11_independent.py
.venv/bin/ruff format --check scripts/digitize_calbrix_e3_fig11_independent.py
.venv/bin/python -m py_compile scripts/digitize_calbrix_e3_fig11_independent.py
```

The reproduction CSV was byte-identical. The script writes 60 rows and embeds
the source PDF hash in each row. It reads the first CSV only for the printed
comparison; no first-trace pixel coordinates or values enter the extraction.

## Artifact hashes

- Source PDF: `128eeb1ea3ad30f5a2ecf9194e2b784be37e837982dec3bdcb7b9db48aa4e7e4`
- Independent script: `a3fdd7190436c4f2d86616925c8eb3e0c1eb3a5f26e3e9f9e1ee76c66e863dfa`
- Independent CSV: `23cd37c8da9fddc578797f7eb10ec2e8355f8c84e4e6ea693d78b592d34da5dd`
- First-trace CSV used only for the comparison: `cb60d88ab7105725f23917f223b07999d8c0cd1e61bf13d5a49012ea14bc43de`
