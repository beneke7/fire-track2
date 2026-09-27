# E4 Amorim M134 source and Fig. 9 digitization

**Status:** the local source record and a reproducible vector-figure trace are
ready. E4 is **not ready for a controlled pass/fail comparison**. The paper
does not provide the M134 cup-level map, and its plotted along-track origin was
adjusted for best fit. No E4 simulation or field-validation pass is reported.

## Source and reported trial inputs

The source is J. H. Amorim, “Numerical modelling of the aerial drop of
firefighting agents by fixed-wing aircraft. Part II: model validation,”
*International Journal of Wildland Fire* 20 (2011), 394–406,
[doi:10.1071/WF09123](https://doi.org/10.1071/WF09123). The local source is
[`WF09123.pdf`](../WF09123.pdf), SHA-256
`89e50599fec1bcb872cc99270113d2cc12dbd377a56c9415b3470a64236d15da`.

| M134 item | Reported value | Source and use |
| --- | ---: | --- |
| Product | Water | PDF p. 3, Table 2; the paper reports density as 1,000 kg/m³. |
| Released volume | 4.64 m³ | PDF p. 3, Table 2; 4,640 L by unit conversion. |
| Average flow rate | 2.04 m³/s | PDF p. 3, Table 2; not a time-resolved discharge history. |
| Drop height | 60.66 m | PDF p. 3, Table 2. |
| Drop speed | 67.90 m/s | PDF p. 3, Table 2; airspeed versus ground speed is not identified. |
| Wind | 2.68 m/s, relative direction 135° | PDF p. 3, Table 2. Preserve the paper's convention; the flight-frame vector cannot be reconstructed from the table alone. |
| Ground grid | 613 m by 105 m; maximum central resolution 4.6 m by 4.6 m | PDF p. 3, measurement-method text. The ground map was produced from cup-and-grid measurements followed by interpolation. |

The table values identify a useful water trial, but they do not specify the
release-time history, exact outlet geometry, aircraft ground track, or the
original cup values. Do not treat this trial as a four-slot device test or as
validation of the built Restás system.

## Figure observables

**Fig. 4, PDF p. 6 (journal p. 399):** the M134 measured concentration pattern
is shown in the top panel and the ADM pattern in the bottom panel. The figure
compares contour shapes at the Marana coverage levels 0.25, 0.75, 1.5, 2.5,
3.5, 5.5, 7.5 and 9.5 gpc. Its caption explicitly says the pattern positions
in the grid are not comparable. The PDF contains a plotted contour image, not
the cup-level measurements needed to reconstruct a measured concentration
map. One gpc is approximately 0.4 L/m²; thus 5.5 and 7.5 gpc are approximately
2.2 and 3.0 kg/m² for water at the reported density, bracketing the
illustrative 2.4 kg/m² target. These conversions are approximate.

**Fig. 9, PDF p. 11 (journal p. 404):** M134 shows measured triangle markers
and ADM circle markers over a plotted `x` range of 0–600 m and `Vx` range of
0–30 L. The body text (PDF p. 9, journal p. 402) defines the profile as
`Vx = sum_y V(y)`: at each along-track position `x`, it sums cell volumes
across the cross-track `y` direction. Despite the paper's phrase “cumulative
volume deposited along the x axis,” this is **not a running cumulative sum
along x**; a running cumulative curve would not rise and then return to zero.
The plotted values are a cross-track-summed volume profile, not a scalar
released-volume total. Integrating the drawn `Vx` curve as `Vx dx` would have
units L·m. Recovering collected mass requires the original x-bin definition
and column volumes, which are not supplied by the plot.

The paper also states that the curves' x positions were adjusted to give the
best fit because aircraft position during the experiments was unknown (PDF
p. 9). Keep the x coordinates as plotted, but do not interpret the plot origin
as the aircraft or release origin. Any new model comparison that permits a
horizontal shift must preregister one translation and its fitting rule; do not
stretch the x axis or rescale `Vx`.

The PDF reports aggregate measured-versus-ADM contour statistics, not raw
contour data. For M134, Table 5 (PDF p. 6) reports line-length NMSE 0.024,
correlation 0.990, mean bias 12.375 m, geometric mean bias 1.79 m,
geometric variance 3.25 m², fractional bias 0.102 and FAC2 0.800. Table 7
(PDF p. 7) reports area NMSE 0.006, correlation 0.999, mean bias 169.72 m²,
geometric mean bias 1.91 m², geometric variance 2.53 m⁴, fractional bias
0.067 and FAC2 0.600. Those are the paper's ADM results, not scores from this
project; they do not replace a local E4 comparison.

## Reproducible Fig. 9 trace

[`data/derived/amorim_m134_fig9.csv`](../data/derived/amorim_m134_fig9.csv)
contains 442 measured-marker centers and 273 ADM-marker centers extracted
from the local PDF's vector paths. It keeps both the source page coordinates
and calibrated axes. The legend marker for each series is excluded. The
reproduction command is:

```sh
make digitize-e4
```

The target runs `.venv/bin/python scripts/digitize_amorim_m134_fig9.py` by
default; set `PYTHON` to another project-compatible interpreter if needed.

The script uses `pdftocairo` to render PDF page 11 as SVG, classifies the
triangle and circle marker outlines in the M134 panel, computes each marker's
geometric center, and calibrates from the printed axis ticks. In the emitted
PDF-page coordinate system, the calibration points are `x=0 m` at 92.995894
pt, `x=600 m` at 276.181097 pt, `Vx=0 L` at 228.345248 pt and `Vx=30 L` at
95.854389 pt. The input PDF SHA-256 and expected marker counts are checked so
that a source or extraction change cannot silently rewrite the trace.

This CSV is a **figure digitization**, not raw cup data. It records the plotted
marker centers; it does not add a probability model or claim an experimental
measurement uncertainty. The source does not publish a digitization error
bound. The plotted curve position was already adjusted by the paper, and no
absolute track position can be inferred. Do not integrate the trace to claim
ground recovery or released-mass closure.

The measured profile's highest marker is 24.674 L at `x=284.101 m`; the ADM
profile's highest marker is 25.229 L at `x=362.814 m`. The ADM peak is 0.555 L
(2.25% of the measured peak) higher, and the two peaks are 78.7 m apart, so
this is a comparison of separate profile maxima, not values at the same x.
The nearby Marana discussion (PDF p. 10, journal p. 403) says there is “some
tendency” to underestimate `Vx` maxima, giving 4% for M114, 18% for M110 and a
12% average; it does not state that every Marana case except M114 is
underestimated. M134's plotted peak runs opposite that general tendency, but
the prose does not quantify the M134-specific error. Preserve this as a
figure-level per-case difference, not a categorical contradiction, and do not
change the trace or use the summary prose as a local pass/fail threshold.

## E4 gate and next evidence

The current gate is **source-limited descriptive comparison only**. Before a
controlled E4 claim, obtain the M134 cup-level ground map or independently
digitize and review the figures with a source-justified uncertainty interval;
freeze the trial's discharge reconstruction, aircraft and wind frames, grid
binning, horizontal registration, observables and acceptance limits; and
review the physics used from ground-intercept plane to map accumulation. Keep
Fig. 4 shape, contour lengths/areas, and Fig. 9 `Vx` as separate observables.
If source uncertainty exceeds a proposed tolerance, report the outcome as
inconclusive rather than widening the tolerance after the comparison.

The paper's published maps and ADM metrics are valuable field-derived
evidence, but they cannot supply the missing raw measurements or validate an
independently implemented descent model by themselves. See
[`docs/VALIDATION.md`](../docs/VALIDATION.md) for the shared acceptance rules.
