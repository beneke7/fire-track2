from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.cluster.slurm_scaffold import main, render_job, validate_config


def sample_config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "allocation": {
            "cores": 1300,
            "cpu_hours_budget_min": 1_000_000,
            "cpu_hours_budget_max": 2_000_000,
        },
        "solver": {
            "name": "custom interIsoFoamTracePair with traceNormalHeadPressure",
            "openfoam_version": "OpenCFD OpenFOAM v2512",
            "binary_sha256": "a" * 64,
            "source_manifest_sha256": "b" * 64,
            "custom_components": ["interIsoFoamTracePair", "traceNormalHeadPressure"],
            "runtime_strategy": "site-wrapper",
        },
        "jobs": [
            {
                "name": "rouaix-smoke",
                "profile": "smoke",
                "nodes": 1,
                "tasks_per_node": 4,
                "cpus_per_task": 1,
                "walltime": "00:10:00",
                "signal_before_walltime_seconds": 300,
                "memory_per_node": "64G",
                "partition": "cpu",
                "account": None,
            }
        ],
    }


def test_resource_arithmetic_and_thread_policy() -> None:
    config, jobs = validate_config(sample_config())
    assert config["allocation"]["cores"] == 1300
    assert jobs[0].ranks == 4
    assert jobs[0].requested_cores == 4
    assert jobs[0].walltime_seconds == 600


def test_rejects_job_above_allocation_and_nested_threads() -> None:
    over = sample_config()
    over["jobs"][0]["nodes"] = 2
    over["jobs"][0]["tasks_per_node"] = 700
    with pytest.raises(ValueError, match="above allocation limit"):
        validate_config(over)

    nested = sample_config()
    nested["jobs"][0]["cpus_per_task"] = 2
    with pytest.raises(ValueError, match="must be 1"):
        validate_config(nested)


def test_rendered_slurm_script_is_syntax_valid_and_never_submits(tmp_path: Path) -> None:
    config, jobs = validate_config(sample_config())
    script = render_job(config, jobs[0])
    path = tmp_path / "smoke.sbatch"
    path.write_text(script, encoding="utf-8")
    subprocess.run(["bash", "-n", str(path)], check=True)
    assert "#SBATCH --nodes=1" in script
    assert "#SBATCH --ntasks=4" in script
    assert "#SBATCH --signal=B:USR1@300" in script
    assert "export OMP_NUM_THREADS=1" in script
    assert 'exec "$FIRETRACK2_CLUSTER_WRAPPER"' in script
    assert "sbatch " not in script


def test_budget_and_runtime_strategy_reject_invalid_values() -> None:
    too_expensive = sample_config()
    too_expensive["jobs"][0]["nodes"] = 1300
    too_expensive["jobs"][0]["tasks_per_node"] = 1
    too_expensive["jobs"][0]["walltime"] = "50-00:00:00"
    with pytest.raises(ValueError, match="conservative configured planning cap"):
        validate_config(too_expensive)

    invalid_runtime = sample_config()
    invalid_runtime["solver"]["runtime_strategy"] = "docker-assumed"
    with pytest.raises(ValueError, match="runtime_strategy"):
        validate_config(invalid_runtime)


def test_config_sample_is_json_object() -> None:
    # This guards test-fixture serialization without requiring a site config.
    assert json.loads(json.dumps(sample_config()))["schema_version"] == 1


def test_example_config_refuses_unconfirmed_site_values() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts/cluster/example-config.json"
    with pytest.raises(ValueError, match="SHA-256"):
        validate_config(json.loads(path.read_text(encoding="utf-8")))


def test_cli_dry_run_writes_new_scripts_and_refuses_overwrite(tmp_path: Path) -> None:
    config_path = tmp_path / "site.json"
    config_path.write_text(json.dumps(sample_config()), encoding="utf-8")
    output_dir = tmp_path / "jobs"
    assert (
        main(
            [
                "render",
                "--config",
                str(config_path),
                "--output-dir",
                str(output_dir),
                "--dry-run",
            ]
        )
        == 0
    )
    manifest = json.loads((output_dir / "scaffold-manifest.json").read_text(encoding="utf-8"))
    assert manifest["submission_performed"] is False
    assert (output_dir / "rouaix-smoke.sbatch").is_file()
    assert (
        main(
            [
                "render",
                "--config",
                str(config_path),
                "--output-dir",
                str(output_dir),
                "--dry-run",
            ]
        )
        == 2
    )


def test_pre_timeout_signal_must_arrive_before_walltime() -> None:
    config = sample_config()
    config["jobs"][0]["signal_before_walltime_seconds"] = 600
    with pytest.raises(ValueError, match="below the walltime"):
        validate_config(config)
