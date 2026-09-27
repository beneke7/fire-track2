#!/usr/bin/env bash
# Runs only while run_local.py holds the shared project GPU lock.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 EVIDENCE_DIR IMMUTABLE_IMAGE_ID EXPECTED_RUNNER_SHA256 EXPECTED_CANDIDATE_PATCH_SHA256" >&2
  exit 2
fi
evidence_dir="$1"
image_id="$2"
expected_runner_sha256="$3"
expected_candidate_patch_sha256="$4"
if [[ ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "IMMUTABLE_IMAGE_ID must be sha256:<64 lowercase hex digits>" >&2
  exit 2
fi
if [[ ! "$expected_runner_sha256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "EXPECTED_RUNNER_SHA256 must be 64 lowercase hex digits" >&2
  exit 2
fi
if [[ ! "$expected_candidate_patch_sha256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "EXPECTED_CANDIDATE_PATCH_SHA256 must be 64 lowercase hex digits" >&2
  exit 2
fi
test -d "$evidence_dir"
container_name="fire-track2-candidate-gpu-$(basename "$evidence_dir")"

# Copy and verify the exact upstream case and the candidate patch embedded in
# the immutable image before any GPU stage or solver process starts.
docker run --rm --cpus=1 --volume "$evidence_dir:/evidence" \
  --entrypoint /bin/bash "$image_id" -ceu '
    template=/opt/FluTAS/examples/two_phase_inc_isot/rising_bubble_3d
    bubble=/evidence/rising_bubble_3d
    test ! -e "$template/source-boundary.in"
    test ! -L "$template/source-boundary.in"
    mkdir -p "$bubble"
    cp -a "$template/." "$bubble/"
    test ! -e "$bubble/source-boundary.in"
    test ! -L "$bubble/source-boundary.in"

    runner_sha=$(sha256sum /usr/local/bin/flutas-gpu-tests | cut -d " " -f1)
    test "$runner_sha" = "$1"
    patch=/tmp/source-boundary.patch
    patch_sha=$(sha256sum "$patch" | cut -d " " -f1)
    if [[ "$patch_sha" != "$2" ]]; then
      printf "embedded candidate patch hash mismatch: expected %s, got %s\\n" "$2" "$patch_sha" >&2
      exit 1
    fi
    cp "$patch" /evidence/embedded-source-boundary.patch
    printf "expected_patch_sha256=%s\\nactual_patch_sha256=%s\\n" "$2" "$patch_sha" \
      > /evidence/embedded-patch-check.txt
    printf "pre_solver_source_boundary_input=absent\\nrunner_sha256=%s\\npatch_sha256=%s\\n" \
      "$runner_sha" "$patch_sha" > /evidence/source-disabled-preflight.txt
  ' _ "$expected_runner_sha256" "$expected_candidate_patch_sha256"

printf 'sampled_utc,index,utilization.gpu,memory.used,power.draw,host_mem_available_kib\n' \
  > "$evidence_dir/gpu-resource-samples.csv"
printf 'sampled_utc\tcpu_pct|memory_usage|memory_pct|pids\n' \
  > "$evidence_dir/container-resource-samples.tsv"
printf 'Sampler command diagnostics follow; an empty diagnostic section means no errors were reported.\n' \
  > "$evidence_dir/resource-sampler-errors.log"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# Run the explicit inherited GPU regression while sampling device, host, and
# container resource use at approximately one-second intervals.
docker run --rm --name "$container_name" --gpus all --cpus=2 \
  --entrypoint /usr/local/bin/flutas-gpu-tests \
  --volume "$evidence_dir:/evidence" "$image_id" /evidence \
  2>&1 | tee "$evidence_dir/docker-run.log" &
run_pid=$!
while kill -0 "$run_pid" 2>/dev/null; do
  sampled_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  gpu_row="$(nvidia-smi --query-gpu=index,utilization.gpu,memory.used,power.draw \
    --format=csv,noheader 2>>"$evidence_dir/resource-sampler-errors.log" || true)"
  host_available_kib="$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo)"
  if [[ -n "$gpu_row" ]]; then
    printf '%s,%s,%s\n' "$sampled_utc" "$gpu_row" "$host_available_kib" \
      >> "$evidence_dir/gpu-resource-samples.csv"
  fi
  stats_row="$(docker stats --no-stream --format '{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.PIDs}}' "$container_name" \
    2>>"$evidence_dir/resource-sampler-errors.log" || true)"
  if [[ -n "$stats_row" ]]; then
    printf '%s\t%s\n' "$sampled_utc" "$stats_row" \
      >> "$evidence_dir/container-resource-samples.tsv"
  fi
  sleep 1
done

set +e
wait "$run_pid"
run_status=$?
set -e
if [[ $run_status -ne 0 ]]; then
  exit "$run_status"
fi

for required_file in \
  compiler.txt nvidia-smi.txt nvaccelinfo.txt flutas-cubins.txt \
  openacc-smoke.txt mpi-gpu-buffer-smoke.txt \
  rising_bubble_3d/solver.log rising_bubble_3d/verification.txt; do
  if [[ ! -s "$evidence_dir/$required_file" ]]; then
    printf 'missing or empty GPU regression output: %s\n' "$required_file" >&2
    exit 1
  fi
done

if ! grep -Fq 'NVIDIA Compilers and Tools' "$evidence_dir/compiler.txt"; then
  echo 'compiler report lacks the NVIDIA toolchain marker' >&2
  exit 1
fi
if ! grep -Fq 'NVIDIA-SMI' "$evidence_dir/nvidia-smi.txt"; then
  echo 'nvidia-smi report lacks its device-report marker' >&2
  exit 1
fi
if ! grep -Fq 'Device Number:' "$evidence_dir/nvaccelinfo.txt" || \
   ! grep -Fq 'Device Name:' "$evidence_dir/nvaccelinfo.txt"; then
  echo 'nvaccelinfo report lacks a device marker' >&2
  exit 1
fi
if ! grep -Eq '(^|[^[:alpha:]])OpenACC GPU kernel PASS; output_count=1024([^[:alpha:]]|$)' \
  "$evidence_dir/openacc-smoke.txt"; then
  echo 'OpenACC smoke output lacks its successful kernel marker' >&2
  exit 1
fi
for rank in 0 1; do
  if ! grep -Eq "(^|[[:space:]])rank[[:space:]]+$rank[[:space:]]+GPU-buffer MPI_Allreduce result=3([[:space:]]|$)" \
    "$evidence_dir/mpi-gpu-buffer-smoke.txt"; then
    printf 'GPU-buffer MPI smoke output lacks successful rank %s result\n' "$rank" >&2
    exit 1
  fi
done
if ! grep -Fq 'sm_120.cubin' "$evidence_dir/flutas-cubins.txt"; then
  echo 'FluTAS code-object report lacks sm_120.cubin' >&2
  exit 1
fi

python3 - "$evidence_dir" <<'PY'
import csv
import datetime as dt
import math
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
stage_lines = [
    "compiler=PASS (NVIDIA Compilers and Tools)",
    "nvidia_smi=PASS (device report present)",
    "nvaccelinfo=PASS (device number and name present)",
    "openacc_smoke=PASS (OpenACC GPU kernel PASS; output_count=1024)",
    "mpi_gpu_buffer_smoke=PASS (ranks 0 and 1 reported result=3)",
    "flutas_code_object=PASS (sm_120.cubin)",
]

solver_text = (root / "rising_bubble_3d/solver.log").read_text(errors="replace")
if "*** Fim ***" not in solver_text:
    raise SystemExit("solver log lacks normal completion marker *** Fim ***")
if re.search(r"\b(?:ERROR|ABORT(?:ING|ED)?|FATAL)\b", solver_text, re.IGNORECASE):
    raise SystemExit("solver log contains an ERROR, abort, or fatal marker")

# Parse each timestep record in order. The last record itself must be finite
# and reach the upstream rising-bubble contract endpoint (3.0 s).
time_pattern = re.compile(r"^\s*Timestep\s*#\s*(\d+)\s+Time\s*=\s*(\S+)", re.IGNORECASE)
records: list[tuple[int, float]] = []
for line in solver_text.splitlines():
    match = time_pattern.search(line)
    if not match:
        continue
    token = match.group(2).rstrip(",;")
    try:
        value = float(token)
    except ValueError as exc:
        raise SystemExit(f"invalid final timestep time token {token!r}") from exc
    records.append((int(match.group(1)), value))
if not records:
    raise SystemExit("solver log contains no Timestep # ... Time = ... records")
final_step, final_time = records[-1]
if not math.isfinite(final_time) or final_time < 3.0:
    raise SystemExit(
        f"last timestep record is not finite and >= 3.0 s: step {final_step}, time {final_time!r}"
    )
stage_lines.append(f"solver_completion=PASS (*** Fim ***; final step {final_step}, time {final_time:.17g} s)")

verification = (root / "rising_bubble_3d/verification.txt").read_text(errors="replace")
if not re.search(r"(?m)^\s*True\s+True\s*$", verification):
    raise SystemExit("upstream rising-bubble verification did not report True True")
stage_lines.append("upstream_verification=PASS (True True)")

def finite_number(text: str, suffix: str = "") -> float:
    cleaned = text.strip()
    if suffix:
        if not cleaned.endswith(suffix):
            raise ValueError(f"missing {suffix!r} suffix in {text!r}")
        cleaned = cleaned[: -len(suffix)].strip()
    value = float(cleaned)
    if not math.isfinite(value):
        raise ValueError(f"non-finite number {text!r}")
    return value


BYTE_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(B|KiB|MiB|GiB|TiB|kB|MB|GB|TB)\s*$",
    re.IGNORECASE,
)


def bytes_value(text: str) -> float:
    match = BYTE_RE.fullmatch(text)
    if not match:
        raise ValueError(f"unparseable byte quantity {text!r}")
    value = float(match.group(1))
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"invalid byte quantity {text!r}")
    unit = match.group(2)
    binary = {"B": 0, "KiB": 1, "MiB": 2, "GiB": 3, "TiB": 4}
    decimal = {"kB": 1, "MB": 2, "GB": 3, "TB": 4}
    if unit in binary:
        return value * 1024**binary[unit]
    key = next((known for known in decimal if known.lower() == unit.lower()), None)
    if key is None:
        raise ValueError(f"unknown byte unit {unit!r}")
    return value * 1000**decimal[key]


def sampled_time(text: str) -> None:
    dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))


gpu_util: list[float] = []
gpu_memory: list[float] = []
gpu_power: list[float] = []
host_available: list[float] = []
gpu_parse_errors: list[str] = []
gpu_path = root / "gpu-resource-samples.csv"
with gpu_path.open(newline="") as stream:
    reader = csv.DictReader(stream)
    expected_gpu_columns = [
        "sampled_utc", "index", "utilization.gpu", "memory.used", "power.draw",
        "host_mem_available_kib",
    ]
    if reader.fieldnames != expected_gpu_columns:
        raise SystemExit("GPU resource sample header does not match the declared schema")
    for row_index, row in enumerate(reader, start=2):
        try:
            sampled_time(row["sampled_utc"])
            device_index = int(row["index"].strip())
            if device_index < 0:
                raise ValueError("negative GPU index")
            utilization = finite_number(row["utilization.gpu"], "%")
            if not 0.0 <= utilization <= 100.0:
                raise ValueError("GPU utilization outside [0,100]")
            memory = bytes_value(row["memory.used"])
            power_text = row["power.draw"].strip()
            if not power_text.endswith("W"):
                raise ValueError(f"unparseable GPU power {power_text!r}")
            power = finite_number(power_text, "W")
            host_kib = finite_number(row["host_mem_available_kib"])
            if memory < 0.0 or power < 0.0 or host_kib < 0.0:
                raise ValueError("negative sampled GPU or host resource value")
            gpu_util.append(utilization)
            gpu_memory.append(memory)
            gpu_power.append(power)
            host_available.append(host_kib)
        except (ValueError, TypeError, KeyError) as exc:
            gpu_parse_errors.append(f"line {row_index}: {exc}")

container_cpu: list[float] = []
container_memory: list[float] = []
container_parse_errors: list[str] = []
container_path = root / "container-resource-samples.tsv"
with container_path.open() as stream:
    header = stream.readline().rstrip("\n")
    if header != "sampled_utc\tcpu_pct|memory_usage|memory_pct|pids":
        raise SystemExit("container resource sample header does not match the declared schema")
    for row_index, line in enumerate(stream, start=2):
        try:
            sampled, raw_stats = line.rstrip("\n").split("\t", 1)
            sampled_time(sampled)
            fields = raw_stats.split("|")
            if len(fields) != 4:
                raise ValueError("expected CPU, memory usage, memory percent and PID columns")
            cpu = finite_number(fields[0], "%")
            memory_pair = fields[1].split("/")
            if len(memory_pair) != 2:
                raise ValueError("memory usage must contain used / limit")
            used_memory = bytes_value(memory_pair[0])
            _limit_memory = bytes_value(memory_pair[1])
            memory_pct = finite_number(fields[2], "%")
            pids = int(fields[3].strip())
            if cpu < 0.0 or used_memory < 0.0 or memory_pct < 0.0 or pids < 0:
                raise ValueError("negative container resource value")
            container_cpu.append(cpu)
            container_memory.append(used_memory)
        except (ValueError, TypeError) as exc:
            container_parse_errors.append(f"line {row_index}: {exc}")

resource_failures = []
if not gpu_util:
    resource_failures.append("GPU resource samples contain no parseable finite sample")
if not container_cpu or not container_memory:
    resource_failures.append("container resource samples contain no parseable finite CPU+memory sample")
if resource_failures:
    raise SystemExit("; ".join(resource_failures))

validation_lines = [
    "resource_validation=PASS",
    f"valid_gpu_samples={len(gpu_util)}",
    f"valid_container_cpu_memory_samples={len(container_cpu)}",
    f"malformed_gpu_rows={len(gpu_parse_errors)}",
    f"malformed_container_rows={len(container_parse_errors)}",
]
(root / "resource-validation.txt").write_text("\n".join(validation_lines) + "\n")

resource_lines = [
    "Runtime resources sampled at approximately 1 Hz; reported extrema are sampled maxima/minima, not exact hardware peaks.",
    f"Valid GPU samples: {len(gpu_util)}; valid container CPU+memory samples: {len(container_cpu)}.",
    f"Maximum sampled GPU utilization: {max(gpu_util):g}%.",
    f"Maximum sampled GPU memory used: {max(gpu_memory) / 1024**2:.1f} MiB.",
    f"Maximum sampled GPU power draw: {max(gpu_power):g} W.",
    f"Maximum sampled container memory: {max(container_memory) / 1024**2:.1f} MiB.",
    f"Maximum sampled container CPU: {max(container_cpu):g}%.",
    f"Minimum sampled host MemAvailable: {min(host_available) / 1024**2:.1f} GiB.",
]
(root / "resource-use.txt").write_text("\n".join(resource_lines) + "\n")
(root / "stage-checks.txt").write_text("\n".join(stage_lines + ["resources=PASS (finite GPU and container CPU+memory samples)"]) + "\n")
PY
