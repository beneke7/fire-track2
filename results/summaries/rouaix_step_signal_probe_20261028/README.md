# Rouaix Slurm signal helper probe — 28 October 2026

The public signal_owned_step implementation was exercised against a live,
owned one-task Slurm step under the same OpenFOAM v2512 module environment used
by the restart jobs. No CFD solver was launched.

- Slurm job: 14700561, one task on one CPU, 2 GiB, five-minute bound.
- Helper source SHA-256: 2cb1284e09f184c1c67670f30c198d70d7befe9c5a47c6232ac80dd105a5ea88.
- Step identity: 14700561 0 1 0.
- The specific and job-wide scontrol show step queries returned explicit
  not-found responses. The helper then verified the live job record:
  JobId=14700561, JobName=ml-sigprobe3, JobState=RUNNING, NumTasks=1,
  UserId=nk_memj(16018), matching the running process UID.
- The helper called scancel --signal=12 14700561.0; return code was 0.
  The helper returned acknowledged=true before the controller waited for srun.
  The child recorded signal 12, then srun exited 0.
- The module environment kept scontrol and scancel at /usr/bin; scontrol used
  the compute node's cached SLURM_CONF. SLURM_CONF_SERVER was unset.

The full bounded receipt is in probe-14700561/controller-result.json;
the separate acknowledgement and child signal receipt are saved beside it.
