# S1 64-rank terminal result — 26 October 2026

Job **14651180** completed all **500 steps to 0.05 s**, fixed deltaT=0.0001 s, on one CPU-short host with 64 CPU ranks and 64 GiB. No GPUs were allocated. The node x1001c2s3b0n0 has 64 CPUs and is GPU-capable; its hardware differs from the 128-CPU hosts used by the 120-rank case. This is an exploratory startup result, not an E1 pass.

All **4,001 linear solve records** met their configured criteria. Peak speed was **103.502606784 m/s**; bulk/interface Courant maxima were **1.121011 / 0.540217**. The 500-row ledger injected 62.5822160148817 kg and ended with 62.5822160148921 kg; final residual is about **+1.05e-11 kg**. This global water balance does not establish momentum conservation or physical accuracy.

Solver srun wall time was **3490.203 s**; whole-job elapsed **3681 s**, charging 65.44 allocated core-hours. Measured TotalCPU was 61.57 core-hours (~94.1% of the job allocation); CPU activity can include MPI polling. The earlier 120-rank T1 peak was 103.29355 m/s (difference ~0.2%); its runtime comparison is observational because placement/hardware differ. Peak agreement is one scalar, not a field-convergence test.

Endpoint turbulence maxima remain material uncertainty: k 756.61 m2/s2, epsilon 285263 m2/s3 and nut 0.33459 m2/s occur at different cells. There is no 3D field at the 0.0495 s speed-peak time; endpoint extrema cannot establish that peak's phase/location. Only 0 and 0.05 s full fields were saved.

[hpc-metrics.json](hpc-metrics.json) contains the parsed per-step performance history. [analysis.json](analysis.json) records precise timings, accounting scopes, alpha stages, ledger, commands, source hashes and limits. [solver.log.gz](solver.log.gz) is a lossless compressed copy of the matched source log; its raw identity is recorded separately. The bundled convergence result, speed CSV and ledger permit compact audit. Raw 3D fields and the 1.697 GB result archive remain on HPC, SHA-256 dfd541d13d7246030c45197f35b3557051852e994683a59621af4c7fa676d048. Remote archive SHA and 130-member listing matched the saved records; 16 compact files were independently transferred and hash-checked. The full archive was not copied locally.

The legacy experiment.md intro describes the earlier 1 ms/50-step pilot. The preserved active experiment-progression.md, immutable case record, manifest, controlDict and solver log establish this run's 0.1 ms/500 steps. No historical declaration was overwritten.
