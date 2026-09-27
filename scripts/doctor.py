#!/usr/bin/env python3
"""Inspect local compute resources and tools using only the standard library."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PACKAGE_NAMES = (
    "fire-track2",
    "pip",
    "numpy",
    "scipy",
    "pytest",
    "ruff",
    "matplotlib",
    "pyvista",
    "vtk",
    "torch",
    "cupy",
    "mpi4py",
)

TOOL_NAMES = {
    "git": ("git",),
    "uv": ("uv",),
    "nvidia-smi": ("nvidia-smi",),
    "CUDA compiler (nvcc)": ("nvcc",),
    "MPI launcher": ("mpirun", "mpiexec"),
    "OpenFOAM version tool": ("foamVersion",),
    "OpenFOAM VOF solver": (
        "interFoam",
        "interIsoFoam",
        "multiphaseInterFoam",
        "compressibleInterFoam",
    ),
    "FluTAS candidate": ("flutas", "FluTAS"),
    "SU2 solver": ("SU2_CFD",),
    "ParaView": ("paraview",),
    "FFmpeg": ("ffmpeg",),
    "Docker": ("docker",),
}

SOLVER_KEYS = (
    "OpenFOAM VOF solver",
    "FluTAS candidate",
    "OpenFOAM VOF container",
)
OPENFOAM_CONTAINER_IMAGE = "opencfd/openfoam-default:2512"


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    except (OSError, UnicodeError):
        return None


def _cgroup_memberships() -> list[tuple[str, str]]:
    content = _read_text(Path("/proc/self/cgroup"))
    if not content:
        return []
    memberships: list[tuple[str, str]] = []
    for line in content.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            memberships.append((parts[1], parts[2].lstrip("/")))
    return memberships


def _cgroup_candidates(filename: str, controller: str | None = None) -> list[Path]:
    """Return leaf-to-root cgroup files so parent limits are included."""
    root = Path("/sys/fs/cgroup")
    candidates: list[Path] = []
    for controllers, relative in _cgroup_memberships():
        if not controllers:
            mount_roots = [root]
        elif controller and controller in controllers.split(","):
            mount_names = [controller]
            if controller == "cpu":
                mount_names.append("cpu,cpuacct")
            mount_roots = [root / name for name in mount_names]
        else:
            continue

        pieces = [piece for piece in relative.split("/") if piece]
        for mount_root in mount_roots:
            for depth in range(len(pieces), -1, -1):
                candidates.append(mount_root.joinpath(*pieces[:depth], filename))

    if controller:
        mount_names = [controller]
        if controller == "cpu":
            mount_names.append("cpu,cpuacct")
        candidates.extend(root / name / filename for name in mount_names)
    candidates.append(root / filename)
    return list(dict.fromkeys(candidates))


def _first_text(paths: list[Path]) -> tuple[str | None, str | None]:
    for path in paths:
        value = _read_text(path)
        if value is not None:
            return value, str(path)
    return None, None


def _all_text(paths: list[Path]) -> list[tuple[str, Path]]:
    values: list[tuple[str, Path]] = []
    for path in paths:
        value = _read_text(path)
        if value is not None:
            values.append((value, path))
    return values


def _parse_cpu_list(value: str | None) -> int | None:
    if not value:
        return None
    count = 0
    try:
        for item in value.split(","):
            bounds = item.strip().split("-", 1)
            start = int(bounds[0])
            end = int(bounds[-1])
            if start < 0 or end < start:
                return None
            count += end - start + 1
        return count or None
    except ValueError:
        return None


def _system_memory() -> tuple[int | None, int | None]:
    meminfo = _read_text(Path("/proc/meminfo"))
    if meminfo:
        values: dict[str, int] = {}
        for line in meminfo.splitlines():
            match = re.match(r"^(MemTotal|MemAvailable):\s+(\d+)\s+kB", line)
            if match:
                values[match.group(1)] = int(match.group(2)) * 1024
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        if total is not None:
            return total, available

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        total = os.sysconf("SC_PHYS_PAGES") * page_size
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        return total, available_pages * page_size
    except (AttributeError, OSError, ValueError):
        return None, None


def _memory_cgroup() -> tuple[int | None, int | None, dict[str, str | None]]:
    pairs = (
        ("memory.max", "memory.current"),
        ("memory.limit_in_bytes", "memory.usage_in_bytes"),
    )
    candidates: list[tuple[int, int | None, Path, Path | None, int]] = []
    for limit_name, current_name in pairs:
        controller = "memory" if limit_name.endswith("in_bytes") else None
        limit_files = _cgroup_candidates(limit_name, controller)
        for limit_text, limit_path in _all_text(limit_files):
            if limit_text == "max":
                continue
            try:
                limit = int(limit_text)
            except ValueError:
                continue
            # Some cgroup v1 kernels use a near-int64 maximum to mean unlimited.
            if limit < 0 or limit >= (1 << 60):
                continue
            current_path = limit_path.with_name(current_name)
            current_text = _read_text(current_path)
            try:
                current = int(current_text) if current_text is not None else None
            except ValueError:
                current = None
            remaining = max(0, limit - current) if current is not None else limit
            candidates.append((remaining, current, limit_path, current_path, limit))

    if not candidates:
        current_text, current_path = _first_text(
            _cgroup_candidates("memory.current")
            + _cgroup_candidates("memory.usage_in_bytes", "memory")
        )
        try:
            current = int(current_text) if current_text is not None else None
        except ValueError:
            current = None
        return None, current, {"limit_path": None, "current_path": current_path}

    _, current, limit_path, current_path, limit = min(candidates, key=lambda item: item[0])
    return (
        limit,
        current,
        {
            "limit_path": str(limit_path),
            "current_path": str(current_path) if current_path else None,
        },
    )


def _cpu_limits() -> dict[str, Any]:
    logical = os.cpu_count()
    affinity: list[int] | None = None
    if hasattr(os, "sched_getaffinity"):
        try:
            affinity = sorted(os.sched_getaffinity(0))
        except OSError:
            pass

    cpuset_text, cpuset_path = _first_text(
        _cgroup_candidates("cpuset.cpus.effective", "cpuset")
        + _cgroup_candidates("cpuset.cpus", "cpuset")
    )
    cpuset_count = _parse_cpu_list(cpuset_text)

    quota_limits: list[tuple[float, str, str | None]] = []
    for quota_text, quota_path in _all_text(_cgroup_candidates("cpu.max")):
        fields = quota_text.split()
        try:
            if len(fields) == 2 and fields[0] != "max":
                quota, period = int(fields[0]), int(fields[1])
                if quota > 0 and period > 0:
                    quota_limits.append((quota / period, str(quota_path), None))
        except ValueError:
            pass

    for quota_text, quota_path in _all_text(_cgroup_candidates("cpu.cfs_quota_us", "cpu")):
        period_path = quota_path.with_name("cpu.cfs_period_us")
        period_text = _read_text(period_path)
        try:
            quota = int(quota_text)
            period = int(period_text) if period_text is not None else 0
            if quota > 0 and period > 0:
                quota_limits.append((quota / period, str(quota_path), str(period_path)))
        except ValueError:
            pass

    quota_cores = min((item[0] for item in quota_limits), default=None)
    quota_path = next((item[1] for item in quota_limits if item[0] == quota_cores), None)
    period_path = next((item[2] for item in quota_limits if item[0] == quota_cores), None)

    bounds: list[int] = []
    if logical and logical > 0:
        bounds.append(logical)
    if affinity is not None:
        bounds.append(max(1, len(affinity)))
    if cpuset_count is not None:
        bounds.append(cpuset_count)
    if quota_cores is not None:
        bounds.append(max(1, int(quota_cores)))
    effective = min(bounds) if bounds else 1

    return {
        "logical": logical,
        "affinity_cpus": affinity,
        "affinity_count": len(affinity) if affinity is not None else None,
        "cgroup_cpuset": cpuset_text,
        "cgroup_cpuset_count": cpuset_count,
        "cgroup_cpuset_path": cpuset_path,
        "cgroup_quota_cores": quota_cores,
        "cgroup_quota_path": quota_path,
        "cgroup_period_path": period_path,
        "effective": effective,
        "default_threads": max(1, effective - 2),
    }


def effective_cpu_count() -> int:
    """Return a conservative integer CPU budget respecting affinity and cgroups."""
    return int(_cpu_limits()["effective"])


def _tool_info(candidates: tuple[str, ...]) -> dict[str, Any]:
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return {"available": True, "command": candidate, "path": path}
    return {"available": False, "command": None, "path": None, "searched": list(candidates)}


def _openfoam_container_info(docker: dict[str, Any]) -> dict[str, Any]:
    """Check for a local CPU OpenFOAM image and its VOF solver executable."""
    result: dict[str, Any] = {
        "available": False,
        "command": None,
        "path": None,
        "image": OPENFOAM_CONTAINER_IMAGE,
        "image_id": None,
        "solver": "interIsoFoam",
        "solver_path": None,
        "solver_support_verified": False,
        "backend": "CPU",
    }
    if not docker["available"]:
        return result

    try:
        image = subprocess.run(
            [docker["path"], "image", "inspect", OPENFOAM_CONTAINER_IMAGE, "--format", "{{.Id}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if image.returncode != 0:
            return result
        result["image_id"] = image.stdout.strip()
        probe = subprocess.run(
            [
                docker["path"],
                "run",
                "--rm",
                "--entrypoint",
                "/bin/bash",
                OPENFOAM_CONTAINER_IMAGE,
                "-c",
                "source /usr/lib/openfoam/openfoam2512/etc/bashrc; command -v interIsoFoam",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        result["probe_error"] = str(error)
        return result

    if probe.returncode == 0 and probe.stdout.strip():
        result.update(
            {
                "available": True,
                "command": "interIsoFoam",
                "path": f"docker image {OPENFOAM_CONTAINER_IMAGE}",
                "solver_path": probe.stdout.strip(),
            }
        )
    else:
        result["probe_error"] = probe.stderr.strip() or f"solver probe exited {probe.returncode}"
    return result


def _package_info(name: str) -> dict[str, Any]:
    try:
        return {"installed": True, "version": importlib.metadata.version(name)}
    except importlib.metadata.PackageNotFoundError:
        return {"installed": False, "version": None}
    except Exception as error:
        return {"installed": None, "version": None, "error": str(error)}


def _gpu_info(tools: dict[str, dict[str, Any]]) -> dict[str, Any]:
    smi = tools["nvidia-smi"]
    nvcc = tools["CUDA compiler (nvcc)"]
    result: dict[str, Any] = {
        "detected": False,
        "devices": [],
        "nvidia_smi_available": smi["available"],
        "cuda_toolkit_available": nvcc["available"],
        "cuda_toolkit_path": nvcc["path"],
        "driver_cuda_version": None,
        "solver_support_verified": False,
    }
    if not smi["available"]:
        return result

    try:
        completed = subprocess.run(
            [
                smi["path"],
                "--query-gpu=name,memory.total,memory.used,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        result["query_error"] = str(error)
        return result

    if completed.returncode != 0:
        result["query_error"] = (
            completed.stderr.strip() or f"nvidia-smi exited {completed.returncode}"
        )
        return result

    devices = []
    for line in completed.stdout.splitlines():
        fields = [field.strip() for field in line.split(",", 3)]
        if len(fields) < 4:
            continue

        def mebibytes(text: str) -> int | None:
            try:
                return int(float(text) * 1024 * 1024)
            except ValueError:
                return None

        devices.append(
            {
                "name": fields[0],
                "memory_total_bytes": mebibytes(fields[1]),
                "memory_used_bytes": mebibytes(fields[2]),
                "driver_version": fields[3],
            }
        )
    result["devices"] = devices
    result["detected"] = bool(devices)
    try:
        version = subprocess.run(
            [smi["path"]], check=False, capture_output=True, text=True, timeout=3
        ).stdout
        match = re.search(r"CUDA Version:\s*([\w.]+)", version)
        if match:
            result["driver_cuda_version"] = match.group(1)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result


def collect_report(location: Path | None = None) -> dict[str, Any]:
    location = (location or Path.cwd()).resolve()
    cpu = _cpu_limits()
    memory_total, memory_available = _system_memory()
    memory_limit, memory_current, memory_paths = _memory_cgroup()
    effective_memory_available = memory_available
    if memory_limit is not None:
        cgroup_remaining = (
            max(0, memory_limit - memory_current) if memory_current is not None else memory_limit
        )
        effective_memory_available = (
            min(memory_available, cgroup_remaining)
            if memory_available is not None
            else cgroup_remaining
        )

    try:
        disk_usage = shutil.disk_usage(location)
        disk = {
            "path": str(location),
            "total_bytes": disk_usage.total,
            "used_bytes": disk_usage.used,
            "free_bytes": disk_usage.free,
        }
    except OSError as error:
        disk = {
            "path": str(location),
            "total_bytes": None,
            "used_bytes": None,
            "free_bytes": None,
            "error": str(error),
        }

    tools = {label: _tool_info(candidates) for label, candidates in TOOL_NAMES.items()}
    tools["OpenFOAM VOF container"] = _openfoam_container_info(tools["Docker"])
    packages = {name: _package_info(name) for name in PACKAGE_NAMES}
    gpu = _gpu_info(tools)
    cpu_solver_found = any(
        tools[key]["available"] for key in SOLVER_KEYS if key != "FluTAS candidate"
    )
    gpu_solver_candidate_found = tools["FluTAS candidate"]["available"]
    reasons = []
    if not cpu_solver_found and not gpu_solver_candidate_found:
        reasons.append("No host or local-container VOF solver candidate was found.")
    if not gpu["cuda_toolkit_available"]:
        reasons.append("CUDA toolkit compiler nvcc was not found on PATH.")
    if tools["OpenFOAM VOF container"]["available"]:
        reasons.append(
            "A CPU OpenFOAM VOF solver is available in a local Docker image; this is not GPU readiness or benchmark validation."
        )

    return {
        "schema_version": 1,
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "hostname": platform.node(),
        },
        "interpreter": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable": sys.executable,
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
        },
        "resources": {
            "cpu": cpu,
            "memory": {
                "total_bytes": memory_total,
                "available_bytes": memory_available,
                "effective_available_bytes": effective_memory_available,
                "cgroup_limit_bytes": memory_limit,
                "cgroup_current_bytes": memory_current,
                **memory_paths,
            },
            "disk": disk,
        },
        "gpu": gpu,
        "packages": packages,
        "tools": tools,
        "readiness": {
            "cpu_vof_case": "candidate_found" if cpu_solver_found else "not_ready",
            "gpu_vof_pilot": (
                "support_check_required"
                if gpu_solver_candidate_found and gpu["cuda_toolkit_available"]
                else "not_ready"
            ),
            "gpu_solver_support_verified": False,
            "notes": reasons
            + [
                "GPU visibility and driver CUDA version do not confirm solver or VOF support.",
                "An executable candidate does not confirm inlet, crossflow, or GPU VOF capability.",
            ],
        },
    }


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} TiB"


def human_summary(report: dict[str, Any]) -> str:
    resources = report["resources"]
    cpu = resources["cpu"]
    memory = resources["memory"]
    disk = resources["disk"]
    gpu = report["gpu"]
    solver_tools = [report["tools"][key] for key in SOLVER_KEYS]
    solver = next((item for item in solver_tools if item["available"]), None)
    interpreter = report["interpreter"]
    packages = report["packages"]
    key_packages = ("numpy", "scipy", "pytest", "pyvista")
    lines = [
        f"Compute doctor — {report['host']['system']} {report['host']['machine']}",
        f"Python: {interpreter['implementation']} {interpreter['version']} ({interpreter['executable']})",
        "Packages: "
        + ", ".join(f"{name} {packages[name]['version'] or 'missing'}" for name in key_packages),
        f"CPU: {cpu['effective']} effective of {cpu['logical'] or 'unknown'} logical; default {cpu['default_threads']} threads",
        f"Memory: {_format_bytes(memory['effective_available_bytes'])} available to this process",
        f"Disk: {_format_bytes(disk['free_bytes'])} free at {disk['path']}",
    ]
    if gpu["detected"]:
        descriptions = []
        for device in gpu["devices"]:
            descriptions.append(f"{device['name']} ({_format_bytes(device['memory_total_bytes'])})")
        lines.append(
            "GPU: "
            + ", ".join(descriptions)
            + (
                f"; driver reports CUDA {gpu['driver_cuda_version']}"
                if gpu["driver_cuda_version"]
                else ""
            )
        )
    else:
        lines.append("GPU: no NVIDIA GPU detected through nvidia-smi")

    lines.append(
        f"VOF solver: {solver['command']} at {solver['path']}"
        if solver
        else "VOF solver: none of the checked candidates found"
    )
    lines.append(
        "CUDA toolkit: nvcc found at " + report["tools"]["CUDA compiler (nvcc)"]["path"]
        if gpu["cuda_toolkit_available"]
        else "CUDA toolkit: nvcc missing"
    )
    lines.append(
        "Readiness: CPU VOF "
        + report["readiness"]["cpu_vof_case"]
        + "; GPU VOF pilot "
        + report["readiness"]["gpu_vof_pilot"]
        + " (solver support unverified)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="print the machine-readable JSON report"
    )
    parser.add_argument(
        "--output", type=Path, help="also write the machine-readable report to this path"
    )
    args = parser.parse_args(argv)

    report = collect_report()
    rendered_json = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        try:
            args.output.write_text(rendered_json, encoding="utf-8")
        except OSError as error:
            parser.error(f"cannot write report to {args.output}: {error}")

    if args.json:
        sys.stdout.write(rendered_json)
    else:
        print(human_summary(report))
        if args.output:
            print(f"JSON report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
