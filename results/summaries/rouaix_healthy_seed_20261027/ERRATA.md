# Receipt corrections and lifecycle update

This file supplements the frozen capsule and original local receipts; it does not edit either.

- `submission/submit-command-job-14669440.txt` preserves the original receipt but its `SUBMIT_TIME_UTC=2026-10-27T12:00:05Z` label is wrong. The Slurm `scontrol show job` timestamps printed as `2026-10-27T12:00:05` are server-local Europe/Budapest time (CET, UTC+1). The machine-readable `scontrol show job --json` `submit_time.number` converts to **2026-10-27T11:00:05Z**. Auditor 14669459's local `12:01:13` converts to **11:01:13Z**.
- Root's release receipt records its `date -u` time, **2026-10-27T11:09:56Z**. At 11:10:50Z both jobs were released and pending: parent 14669440 had `Reason=Priority`, 120 CPUs, 64G, 2h, partition `cpu`; auditor 14669459 had `Reason=Dependency`, `afterany:14669440(unfulfilled)`, 1 CPU, 1800M, 10m, scheduler partition `cpu,cpu-short`. Neither had an allocation or node at that readback. The parent scheduler start time then estimated by JSON was 12:00:01Z; this is a forecast, not an observed start.
- `checks/admission-core-v-duration-comparison-20261027.txt` is a read-only comparison. Its 120-CPU/1:59 test-only request forecast only the normal `cpu` partition and emitted no cpu-short notice. The 64-CPU/2h test-only request emitted a cpu-short notice. Its displayed numeric IDs are forecasts, not submitted jobs. Do not characterize the 120-CPU parent as cpu-short eligible. The site rule is not known from these probes.
- The admission comparison's statement that the probes did not alter jobs refers to those `--test-only` calls. Root separately released the two held jobs at the time above.
- The declaration inside the immutable capsule states the state at preparation (“prepared only”). It remains historical. Actual submission, release and current scheduler state are recorded in `submission/`.

The summary excludes the 336,471,054-byte mesh payload. Its SHA-256 is recorded as `8da7141c4fc72fe1f8903e1952d8119f5f079e523da6e80b7ab8a5d6b8a12787`; on the cluster it was hardlinked from the already qualified archive.
