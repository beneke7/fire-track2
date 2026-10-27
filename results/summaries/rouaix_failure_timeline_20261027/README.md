# Rouaix 14650641 failure timeline

The figure plots the recorded domain maximum speed and bulk/interface maximum
Courant numbers through the early stop at **0.2628 s**, against the requested
**5.0 s** horizon. The speed panel uses a logarithmic y-axis. Its vertical
markers identify the **0.0500 s trial end**, **0.2341 s isolated interior
spike**, **0.2511 s sustained corner-growth onset**, **0.2625 s operational
guard sample**, and **0.2628 s final checkpoint**. The configured 1,000 m/s
operational guard and Co = 1 reference are labeled; Co = 1 is contextual, not
a validation gate.

Courant series values come from scripts/hpc_metrics.py. The timeline pairs
each pending bulk/interface sample with the next printed Time line and keeps
the last repeated startup sample for that time, matching the recorded
postmortem alignment. The 2,628 speed samples and 2,628 paired Courant samples
were checked against the hash-bound summary: max U **1260.0377 m/s** at
0.2628 s, max bulk Co **1.821026** at 0.2628 s, and max interface Co
**1.369215** at 0.2342 s.

This is a descriptive plot of one partial exploratory run. It does not
establish the cause of the local speed surge or solver validity.

## Reproduction and provenance

From the repository root, run:

    .venv/bin/python scripts/run_local.py --threads 1 --timeout 60 --
      /Applications/ParaView-6.1.1.app/Contents/bin/pvpython
      results/summaries/rouaix_failure_timeline_20261027/plot_failure_timeline.py

The plot script reads the existing compressed inputs in
results/summaries/rouaix_long_stop_20261027/ without copying them:

- max-speed.csv.xz — 16,004 bytes; SHA-256
  a1d17f524bcfad1b5dff7e064b9ce954233aa812bee005c84cc9e72e2854e3d6
- solver.log.xz — 1,047,512 bytes; SHA-256
  9672db8e88af0075fa5e35f65bd9c3c58ec3273ef2bbf4783fff2515aceb86e8
- postmortem-analysis.json — 24,399 bytes; SHA-256
  470a086984d031137312e16ae133a625037eda7ed067cfbf4bc940a9efab0afe

analysis.json records these source identities, the parser hash, recomputed
extrema, event values, plotting settings, and output hash. A temporary
uncompressed solver log is created under ignored
results/runs/rouaix-fast-local-20261027/timeline/ for the existing parser,
then deleted. The original compressed source payloads remain untouched.
