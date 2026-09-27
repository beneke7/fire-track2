#!/usr/bin/env python3
"""Offline contract tests for the candidate GPU regression launcher.

The tests execute both shell launchers with fake git/Docker/GPU commands in an
isolated temporary repository. They validate bundle and failure behavior; they
do not invoke a real container, GPU, solver, or CUDA runtime.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


FLUTAS_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = FLUTAS_ROOT / "run-candidate-gpu-regression.sh"
LOCKED_RUNNER = FLUTAS_ROOT / "run-candidate-gpu-regression-locked.sh"
EXPECTED_IMAGE_ID = "sha256:" + "a" * 64
PATCH_BYTES = b"candidate4 offline patch fixture\n"
PATCH_SHA256 = hashlib.sha256(PATCH_BYTES).hexdigest()
RUNNER_SHA256 = re.search(
    r'^expected_runner_sha256="([0-9a-f]{64})"$',
    LAUNCHER.read_text(),
    re.MULTILINE,
).group(1)


FAKE_DOCKER = r'''#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" == image && "$2" == inspect ]]; then
  if [[ "$4" == *".Config.Entrypoint"* ]]; then
    printf '["/bin/true"]\n'
  else
    printf '%s\n' "$FAKE_EXPECTED_IMAGE_ID"
  fi
  exit 0
fi

if [[ "$1" == stats ]]; then
  case "$FAKE_SCENARIO" in
    header-only-resources)
      echo 'fake docker stats sampling failed' >&2
      exit 1
      ;;
    malformed-resources)
      printf 'NaN|unparseable|inf|not-a-pid\n'
      exit 0
      ;;
    *)
      printf '12.5%%|512MiB / 2GiB|25.0%%|4\n'
      exit 0
      ;;
  esac
fi

if [[ "$1" == rm ]]; then
  exit 0
fi

if [[ "$1" != run ]]; then
  echo "unexpected fake docker command: $*" >&2
  exit 90
fi
shift
args=("$@")
volume=''
entrypoint=''
script_index=-1
for ((i = 0; i < ${#args[@]}; i++)); do
  if [[ "${args[$i]}" == --volume ]]; then
    volume="${args[$((i + 1))]}"
  elif [[ "${args[$i]}" == --entrypoint ]]; then
    entrypoint="${args[$((i + 1))]}"
  elif [[ "${args[$i]}" == -ceu ]]; then
    script_index=$((i + 1))
  fi
done
evidence_dir="${volume%:/evidence}"

if [[ "$entrypoint" == /bin/bash ]]; then
  script="${args[$script_index]}"
  expected_runner="${args[$((${#args[@]} - 2))]}"
  expected_patch="${args[$((${#args[@]} - 1))]}"
  if [[ "$script" != *'sha256sum "$patch"'* || \
        "$script" != *'cp "$patch" /evidence/embedded-source-boundary.patch'* || \
        "$script" != *'test ! -e "$bubble/source-boundary.in"'* || \
        "$script" != *'test ! -L "$bubble/source-boundary.in"'* ]]; then
    echo 'preflight command did not verify/copy patch and source-free case' >&2
    exit 91
  fi
  if [[ "$expected_runner" != "$FAKE_RUNNER_SHA256" ]]; then
    echo 'wrong expected upstream runner hash passed to image preflight' >&2
    exit 92
  fi
  actual_patch="$(sha256sum "$FAKE_EMBEDDED_PATCH" | awk '{print $1}')"
  if [[ "$actual_patch" != "$expected_patch" ]]; then
    printf 'embedded candidate patch hash mismatch: expected %s, got %s\n' \
      "$expected_patch" "$actual_patch" >&2
    exit 93
  fi
  mkdir -p "$evidence_dir/rising_bubble_3d"
  cp "$FAKE_EMBEDDED_PATCH" "$evidence_dir/embedded-source-boundary.patch"
  printf 'expected_patch_sha256=%s\nactual_patch_sha256=%s\n' \
    "$expected_patch" "$actual_patch" > "$evidence_dir/embedded-patch-check.txt"
  printf 'pre_solver_source_boundary_input=absent\nrunner_sha256=%s\npatch_sha256=%s\n' \
    "$expected_runner" "$actual_patch" > "$evidence_dir/source-disabled-preflight.txt"
  exit 0
fi

if [[ "$entrypoint" != /usr/local/bin/flutas-gpu-tests ]]; then
  echo "GPU regression did not explicitly select the test entrypoint: $entrypoint" >&2
  exit 94
fi
if [[ " ${args[*]} " != *" --gpus all "* ]]; then
  echo 'GPU stage did not request its GPU device' >&2
  exit 95
fi

mkdir -p "$evidence_dir/rising_bubble_3d"
printf 'NVIDIA Compilers and Tools\n' > "$evidence_dir/compiler.txt"
printf 'NVIDIA-SMI fake device report\n' > "$evidence_dir/nvidia-smi.txt"
printf 'Device Number: 0\nDevice Name: NVIDIA Offline Test GPU\n' \
  > "$evidence_dir/nvaccelinfo.txt"
printf 'ELF file 1: test.sm_120.cubin\n' > "$evidence_dir/flutas-cubins.txt"
if [[ "$FAKE_SCENARIO" == missing-openacc-marker ]]; then
  printf 'OpenACC kernel ran but has no success marker\n' > "$evidence_dir/openacc-smoke.txt"
else
  printf 'OpenACC GPU kernel PASS; output_count=1024\n' > "$evidence_dir/openacc-smoke.txt"
fi
if [[ "$FAKE_SCENARIO" == missing-mpi-marker ]]; then
  printf 'rank 0 GPU-buffer MPI_Allreduce result=3\n' > "$evidence_dir/mpi-gpu-buffer-smoke.txt"
else
  printf 'rank 0 GPU-buffer MPI_Allreduce result=3\nrank 1 GPU-buffer MPI_Allreduce result=3\n' \
    > "$evidence_dir/mpi-gpu-buffer-smoke.txt"
fi

final_time=3.001520526915884
if [[ "$FAKE_SCENARIO" == short-final-time ]]; then
  final_time=2.99
fi
printf ' Timestep #            1 Time = 1.0000000000000000E-003\n' \
  > "$evidence_dir/rising_bubble_3d/solver.log"
printf ' Timestep #         1680 Time = %s\n' "$final_time" \
  >> "$evidence_dir/rising_bubble_3d/solver.log"
if [[ "$FAKE_SCENARIO" != abnormal-exit-zero-solver ]]; then
  printf ' *** Fim ***\n' >> "$evidence_dir/rising_bubble_3d/solver.log"
fi
if [[ "$FAKE_SCENARIO" == solver-error-marker ]]; then
  printf 'FATAL solver failure despite exit status zero\n' >> "$evidence_dir/rising_bubble_3d/solver.log"
fi
if [[ "$FAKE_SCENARIO" == missing-upstream-verification ]]; then
  printf 'False False\n' > "$evidence_dir/rising_bubble_3d/verification.txt"
else
  printf 'True True\n' > "$evidence_dir/rising_bubble_3d/verification.txt"
fi
printf 'fake explicit GPU test entrypoint completed\n'
/bin/sleep 0.15
exit 0
'''


FAKE_NVIDIA_SMI = r'''#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == --query-gpu=index,utilization.gpu,memory.used,power.draw ]]; then
  case "$FAKE_SCENARIO" in
    header-only-resources)
      echo 'fake nvidia-smi sampling failed' >&2
      exit 1
      ;;
    malformed-resources)
      printf 'GPU0, NaN, unknown, N/A\n'
      exit 0
      ;;
    *)
      printf '0, 45 %%, 2048 MiB, 115.2 W\n'
      exit 0
      ;;
  esac
fi
printf 'NVIDIA-SMI fake device report\n'
'''


FAKE_GIT = r'''#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  *"rev-parse HEAD"*) printf 'offline-test-revision\n' ;;
  *"status --short"*) : ;;
  *) echo "unexpected fake git command: $*" >&2; exit 90 ;;
esac
'''


FAKE_SLEEP = r'''#!/usr/bin/env bash
set -euo pipefail
/bin/sleep 0.01
'''


FAKE_PYTHON = r'''#!/usr/bin/env bash
set -euo pipefail
while [[ $# -gt 0 && "$1" != -- ]]; do shift; done
if [[ $# -lt 2 ]]; then
  echo 'fake run_local shim did not receive the launcher command' >&2
  exit 90
fi
shift
locked_runner="$1"
shift
exec "$locked_runner" "$@"
'''


def executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


class CandidateGpuRegressionOfflineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="flutas-gpu-launcher-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "fake-repo"
        self.flutas = self.root / "containers/flutas"
        self.bin = Path(self.temp.name) / "fake-bin"
        self.evidence_root = self.root / "results/runs"
        (self.flutas / "tests").mkdir(parents=True)
        (self.root / ".venv/bin").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        (self.root / "results").mkdir()
        self.bin.mkdir()
        shutil.copy2(LAUNCHER, self.flutas / LAUNCHER.name)
        shutil.copy2(LOCKED_RUNNER, self.flutas / LOCKED_RUNNER.name)
        (self.root / "scripts/run_local.py").write_text("# never executed by offline shim\n")
        (self.root / "results/machine.json").write_text('{"offline_test": true}\n')
        executable(self.root / ".venv/bin/python", FAKE_PYTHON)
        executable(self.bin / "docker", FAKE_DOCKER)
        executable(self.bin / "nvidia-smi", FAKE_NVIDIA_SMI)
        executable(self.bin / "git", FAKE_GIT)
        executable(self.bin / "sleep", FAKE_SLEEP)
        self.patch_file = Path(self.temp.name) / "fake-image-source-boundary.patch"
        self.patch_file.write_bytes(PATCH_BYTES)

    def run_launcher(self, scenario: str = "pass", expected_patch: str = PATCH_SHA256):
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin}:{environment.get('PATH', '')}",
                "FAKE_SCENARIO": scenario,
                "FAKE_EXPECTED_IMAGE_ID": EXPECTED_IMAGE_ID,
                "FAKE_EMBEDDED_PATCH": str(self.patch_file),
                "FAKE_RUNNER_SHA256": RUNNER_SHA256,
            }
        )
        result = subprocess.run(
            [
                str(self.flutas / LAUNCHER.name),
                "offline:test-image",
                EXPECTED_IMAGE_ID,
                expected_patch,
            ],
            cwd=self.root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        bundles = sorted(self.evidence_root.glob("flutas-candidate-gpu-regression-*"))
        self.assertEqual(len(bundles), 1, result.stdout)
        return result, bundles[0]

    def assert_manifest_matches_bundle(self, bundle: Path) -> None:
        manifest = bundle / "SHA256SUMS"
        self.assertTrue(manifest.is_file())
        declared: set[str] = set()
        for line in manifest.read_text().splitlines():
            digest, relative = line.split(maxsplit=1)
            relative = relative.lstrip("*")
            path = bundle / relative.removeprefix("./")
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, relative)
            declared.add(path.relative_to(bundle).as_posix())
        actual = {
            path.relative_to(bundle).as_posix()
            for path in bundle.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS"
        }
        self.assertEqual(declared, actual)

    def test_success_bundle_has_verified_patch_positive_stages_and_finite_samples(self) -> None:
        result, bundle = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("result=PASS", (bundle / "exit-status.txt").read_text())
        self.assertEqual((bundle / "embedded-source-boundary.patch").read_bytes(), PATCH_BYTES)
        self.assertIn(f"actual_patch_sha256={PATCH_SHA256}", (bundle / "embedded-patch-check.txt").read_text())
        self.assertIn(
            f"verified_embedded_candidate_patch_sha256={PATCH_SHA256}",
            (bundle / "metadata.txt").read_text(),
        )
        self.assertIn("pre_solver_source_boundary_input=absent", (bundle / "source-disabled-preflight.txt").read_text())
        self.assertIn("compiler=PASS", (bundle / "stage-checks.txt").read_text())
        self.assertIn("nvidia_smi=PASS", (bundle / "stage-checks.txt").read_text())
        self.assertIn("nvaccelinfo=PASS", (bundle / "stage-checks.txt").read_text())
        self.assertIn("openacc_smoke=PASS", (bundle / "stage-checks.txt").read_text())
        self.assertIn("mpi_gpu_buffer_smoke=PASS", (bundle / "stage-checks.txt").read_text())
        self.assertIn("solver_completion=PASS", (bundle / "stage-checks.txt").read_text())
        self.assertIn("upstream_verification=PASS (True True)", (bundle / "stage-checks.txt").read_text())
        self.assertIn("not exact hardware peaks", (bundle / "resource-use.txt").read_text())
        self.assert_manifest_matches_bundle(bundle)

    def test_wrong_embedded_patch_hash_fails_and_manifest_keeps_attempt(self) -> None:
        wrong_hash = hashlib.sha256(b"different patch\n").hexdigest()
        result, bundle = self.run_launcher(expected_patch=wrong_hash)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("embedded candidate patch hash mismatch", (bundle / "launcher.log").read_text())
        self.assertIn("result=FAIL", (bundle / "exit-status.txt").read_text())
        self.assertFalse((bundle / "embedded-source-boundary.patch").exists())
        self.assert_manifest_matches_bundle(bundle)

    def test_exit_zero_without_normal_solver_completion_fails(self) -> None:
        result, bundle = self.run_launcher("abnormal-exit-zero-solver")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("lacks normal completion marker", (bundle / "launcher.log").read_text())
        self.assertIn("result=FAIL", (bundle / "exit-status.txt").read_text())
        self.assert_manifest_matches_bundle(bundle)

    def test_solver_final_time_below_three_seconds_fails(self) -> None:
        result, bundle = self.run_launcher("short-final-time")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("is not finite and >= 3.0 s", (bundle / "launcher.log").read_text())
        self.assert_manifest_matches_bundle(bundle)

    def test_solver_error_marker_fails_even_with_fim_and_long_time(self) -> None:
        result, bundle = self.run_launcher("solver-error-marker")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("contains an ERROR, abort, or fatal marker", (bundle / "launcher.log").read_text())
        self.assert_manifest_matches_bundle(bundle)

    def test_upstream_verification_must_report_true_true(self) -> None:
        result, bundle = self.run_launcher("missing-upstream-verification")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("did not report True True", (bundle / "launcher.log").read_text())
        self.assert_manifest_matches_bundle(bundle)

    def test_header_only_resource_files_fail_and_sampler_errors_are_preserved(self) -> None:
        result, bundle = self.run_launcher("header-only-resources")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        errors = (bundle / "resource-sampler-errors.log").read_text()
        self.assertIn("fake nvidia-smi sampling failed", errors)
        self.assertIn("fake docker stats sampling failed", errors)
        self.assertIn("no parseable finite sample", (bundle / "launcher.log").read_text())
        self.assertEqual(len((bundle / "gpu-resource-samples.csv").read_text().splitlines()), 1)
        self.assertEqual(len((bundle / "container-resource-samples.tsv").read_text().splitlines()), 1)
        self.assert_manifest_matches_bundle(bundle)

    def test_malformed_resource_rows_fail_closed(self) -> None:
        result, bundle = self.run_launcher("malformed-resources")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        log = (bundle / "launcher.log").read_text()
        self.assertIn("no parseable finite sample", log)
        self.assertIn("no parseable finite CPU+memory sample", log)
        self.assert_manifest_matches_bundle(bundle)

    def test_nonempty_openacc_log_without_positive_marker_fails(self) -> None:
        result, bundle = self.run_launcher("missing-openacc-marker")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("lacks its successful kernel marker", (bundle / "launcher.log").read_text())
        self.assert_manifest_matches_bundle(bundle)

    def test_missing_mpi_rank_marker_fails(self) -> None:
        result, bundle = self.run_launcher("missing-mpi-marker")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("lacks successful rank 1 result", (bundle / "launcher.log").read_text())
        self.assert_manifest_matches_bundle(bundle)

    def test_missing_patch_sha_argument_is_rejected(self) -> None:
        environment = os.environ.copy()
        environment["PATH"] = f"{self.bin}:{environment.get('PATH', '')}"
        result = subprocess.run(
            [str(self.flutas / LAUNCHER.name), "offline:test-image", EXPECTED_IMAGE_ID],
            cwd=self.root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("EXPECTED_CANDIDATE_PATCH_SHA256", result.stdout)
        self.assertFalse(self.evidence_root.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
