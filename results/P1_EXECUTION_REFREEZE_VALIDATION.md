# P1 execution-path re-freeze validation

**Date:** 2026-09-25. **Purpose:** restore optional P1 replay readiness after
the `Makefile` hash changed, without rerunning the accepted revision-2 solver
case. **Outcome:** exact current execution review recorded; all listed
non-solver checks passed. The accepted Rev 2 run remains unchanged.

## Independent review

`general_reviewer_astra` (Astra Max, read-only) prospectively reviewed the full
current `Makefile` P1 target and the six-file local execution path. The target
has no hidden includes, evaluation hooks, or prerequisites; it invokes the
previously reviewed local launcher with 16 threads and a 3,660 s outer timeout.
The runner retains the frozen 3,600 s inner limit and 48 GiB cap. This review
does not claim to recover the unavailable historical Makefile diff. The
reviewer did not launch tests, containers, or solvers. Its dated approval and
complete history are recorded in
[`P1_SOURCE_EVENT_LEDGER.execution.json`](../experiments/P1_SOURCE_EVENT_LEDGER.execution.json).

| Execution-path file | SHA-256 |
| --- | --- |
| `Makefile` | `f6dfe1e67c443186c7ca14f1bedd0b7e3beebc17114311921baa8ffe0a682182` |
| `scripts/analyze_restas_pilot.py` | `d7e88a2460df77ab4d9de781910569e9fb8b52f5a34a9fb0ba6a81a197a533cf` |
| `scripts/run_restas_pilot.py` | `46a79400ba532825cf0940ff803a452b838404a90df030ccbdeecdfdca721a38` |
| `scripts/analyze_restas_ledger.py` | `6e59408ebaac5b5904fbff3c6d385773eb7bc527688e7f68b2d7a0c902904ce0` |
| `scripts/doctor.py` | `e9e1f76a1c1ce5b39331a20353d7923ebd588a2e9a29954f6d6ecba53023bf03` |
| `scripts/run_local.py` | `13e3d2fd6fcebe58ad623af339de36ed4d29f842b7588c18c59e750ae16d73db` |

The approved amendment document still hashes to
`98002c2252a7f6ded3b98758248cf5e194739fcedc2050e95a4caee8e4fd9829`.
Protocol revision 2, scientific approval, tolerances and accepted run evidence
were not changed.

## Non-solver validation

The Make dry-run printed the expected command and did not execute it:

```text
$ make -n --no-print-directory PYTHON=.venv/bin/python restas-source-ledger
.venv/bin/python scripts/run_local.py --threads 16 --timeout 3660 -- .venv/bin/python scripts/run_restas_pilot.py --source-event-ledger
```

The focused existing test set passed 59 tests in 6.40 s. Its captured output is
[`P1_EXECUTION_REFREEZE_TESTS.txt`](P1_EXECUTION_REFREEZE_TESTS.txt):

```bash
.venv/bin/python -m pytest -q \
  tests/test_pilot_execution_gates.py \
  tests/test_pilot_launcher_stop.py \
  tests/test_pilot_case.py \
  tests/test_pilot_ledger.py \
  tests/test_compute.py
```

The separate live-contract check imported the actual runner and checked the
real execution JSON, a deliberately wrong Makefile hash, regenerated P1 case
files, and the accepted run's input hash. It printed
`PASS real contract readiness, stale-hash rejection, historical input equivalence`:

```bash
PYTHONPATH=scripts .venv/bin/python -B - <<'PY'
import copy
import hashlib
import json
import tempfile
from pathlib import Path

from run_restas_pilot import _hash, _validate_p1_execution_contract, _write_case

contract = json.loads(Path("experiments/P1_SOURCE_EVENT_LEDGER.execution.json").read_text())
assert _validate_p1_execution_contract(contract, ranks=16, memory_gib=48) == 3600

bad = copy.deepcopy(contract)
bad["reviewed_code_sha256"]["Makefile"] = "0" * 64
try:
    _validate_p1_execution_contract(bad, ranks=16, memory_gib=48)
except ValueError as error:
    assert "reviewed code hash no longer matches Makefile" in str(error)
else:
    raise AssertionError("A mismatched Makefile hash was accepted")

accepted = Path("results/runs/restas-source-ledger-20260925T015720.514566Z-8e93eda1")
manifest = json.loads((accepted / "manifest.json").read_text())
with tempfile.TemporaryDirectory() as temporary:
    case = Path(temporary) / "case"
    inputs = _write_case(case, 16, source_event_ledger=True)
    generated_hashes = {
        str(path.relative_to(case)): _hash(path)
        for path in sorted(case.rglob("*")) if path.is_file()
    }
    assert generated_hashes == manifest["prepared_case_file_hashes"]
    input_bytes = (json.dumps(inputs, indent=2, sort_keys=True) + "\n").encode()
    assert hashlib.sha256(input_bytes).hexdigest() == manifest["inputs_sha256"]
print("PASS real contract readiness, stale-hash rejection, historical input equivalence")
PY
```

The local image identity matched the accepted manifest:

```text
$ docker image inspect --format '{{.Id}}' opencfd/openfoam-default:2512
sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b
```

**No P1 solver, CFD case, or GPU job was launched for this recovery.** The
completed Rev 2 bundle remains the evidence of the P1 scientific diagnostic;
this record establishes only that the current replay path is reviewed and its
prelaunch checks pass. A new solver run is optional and not needed to retain
the accepted Rev 2 result.
