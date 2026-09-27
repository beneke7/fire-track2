# Candidate4 GPU regression runner review

**Disposition: ELIGIBLE for one bounded candidate4 source-disabled GPU
regression.** No blocking findings remain for that check. This does not approve
source-boundary execution, another build, or a scientific gate.

Reviewed 2026-09-25 09:52 UTC by Astra Max. All assigned hashes matched and
remained unchanged:

| Artifact | SHA-256 |
| --- | --- |
| `containers/flutas/run-candidate-gpu-regression.sh` | `282bfce5c5f2f86682318e26e7f9a6473e3277090a362fe3eb28232698c83d36` |
| `containers/flutas/run-candidate-gpu-regression-locked.sh` | `9c88514318ed24ce30b607f3fdd2f9b3b20bcf3e9227a5cc9aa24817a7b24492` |
| `containers/flutas/README.md` | `44f36703d052d0be0449aaa684bb5e0dc505a23d0b4d145d24b87a34bc5f3c01` |
| `containers/flutas/tests/test_gpu_regression_launcher_offline.py` | `3e409efdff919ef57aecb5b1e1c2c8ab035b21d975c230e381d46deb3bdae107` |

Eligible identities:

- Candidate4 image:
  `sha256:3086f0312b3a74dd7d0f03102d4b8584a8dd1fe4091364615cb0e580f00283bb`.
- Embedded candidate patch:
  `2eddbe5cc406ecbc60e7ca1fe9ba3a5ff61b130283e74772b1593f1d385959ff`.
- Embedded upstream runner:
  `e90285710e1ce77724d85bcf331c2fe993fdd6367cf3ccec159f81c70c88757c`.

The wrapper checks embedded patch and runner provenance before execution,
copies the verified patch to evidence, and rejects a `source-boundary.in` in
the template or copied case. It uses the immutable image ID and explicit test
entrypoint. PASS requires `*** Fim ***`, no solver error/abort/fatal marker, a
finite final timestep at or above 3 s, and `True True` verification. Archived
candidate3 output has 1,680 time records and ends at `3.001520526915884 s`, so
it satisfies the parser predicates. This confirms parser compatibility only;
candidate4 runtime success remains to be tested.

Header-only or fully malformed telemetry cannot pass. At least one finite GPU
sample and one finite container CPU/memory sample are required; sampler errors
and malformed-row counts are preserved, and reported extrema are labelled as
sampled. The outer launcher holds the shared GPU lock through preflight,
execution, sampling and cleanup. Sequential OpenACC, MPI and bubble stages
stop at the first executable failure. The reviewed envelope is two CPUs and a
600-second timeout; each attempt gets a new evidence directory and exit-time
SHA-256 manifest. Failed attempts are retained.

The primary independently reran `bash -n` and all 11 offline fake-command
tests; they pass. The fakes do not exercise the real Docker daemon, GPU lock,
timeout cleanup or hardware. The Astra reviewer did not launch Docker or
independently reinspect the image; the wrapper verifies exact image contents
before execution.

**Low, non-blocking README note:** the example derives the expected image ID
from a mutable tag. That demonstrates self-consistency, not identity with a
previously reviewed image. Use the independently recorded candidate4 image ID
as the expected value for this attempt.
