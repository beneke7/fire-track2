from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "komondor_tutorial.sh"


def _python_block(pattern: str) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    match = re.search(pattern, text, re.DOTALL)
    assert match is not None, f"script block missing: {pattern}"
    return match.group(1)


def test_launcher_has_valid_bash_syntax_and_bounded_steps() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    text = SCRIPT.read_text(encoding="utf-8")

    assert "srun --kill-on-bad-exit=1" in text
    assert "#SBATCH --" not in text
    assert "interIsoFoam -parallel" in text
    assert "FOAM_IORANKS='(0)'" in text
    assert "pause_check" in text
    assert "set +e +u" in text
    assert 'trap \'record_error "$?" "$LINENO" "$BASH_COMMAND"\' ERR' in text
    assert "writeFields false;" in text
    assert 'cp -a -- "$CASE_DIR/0.orig" "$CASE_DIR/0"' in text
    assert "writeNowSignal 10; stopAtWriteNowSignal 12;" in text
    assert "--ntasks=1 --cpus-per-task=8 --cpu-bind=cores" in text
    assert "serial_setup_cpus_per_task=8" in text
    assert "mpirun" not in text
    assert "ssh " not in text


def test_flexible_rank_node_range_and_frozen_layouts() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "8|16|32|64) expected_nodes=1 ;;" in text
    assert "expected_nodes=3" in text
    assert "expected_nodes=5" in text
    assert "expected_nodes=10" in text
    assert "if [[ ${SLURM_JOB_NAME:-} == ml-io-flex ]]; then" in text
    assert "ml-io-300f" in text
    assert "ml-io-500f" in text
    assert "ml-io-1000f" in text
    assert "ml-io-1200f" in text
    assert "flexible 300-rank job must use 3 to 8 nodes" in text
    assert "flexible 500-rank job must use 5 to 12 nodes" in text
    assert "flexible 1000-rank job must use 10 to 24 nodes" in text
    assert "flexible 1200-rank job must use 10 to 32 nodes" in text
    assert "expected_nodes=1" in text
    assert "8:1|8:16|16:16|32:16|64:16|100:16|300:16|500:16|1000:16|1200:16) ;;" in text

    validator = re.search(r"(?m)^is_flex_node_count\(\) \{[^\n]+\}", text)
    wide_validator = re.search(r"(?ms)^is_wide_flex_node_count\(\) \{.*?^}", text)
    node_case = re.search(r"(?ms)^case \$\{SLURM_NTASKS:-\} in\n.*?^esac", text)
    assert validator is not None
    assert wide_validator is not None
    assert node_case is not None
    code = (
        validator.group(0)
        + "\n"
        + wide_validator.group(0)
        + "\nfail() { exit 9; }\n"
        + node_case.group(0)
        + '\n[[ ${SLURM_JOB_NUM_NODES:-} == "$expected_nodes" ]]'
    )

    def validate(ranks: str, name: str, nodes: str) -> int:
        import os

        env = os.environ.copy()
        env.update(SLURM_NTASKS=ranks, SLURM_JOB_NAME=name, SLURM_JOB_NUM_NODES=nodes)
        return subprocess.run(["bash", "-c", code], env=env, check=False).returncode

    for nodes in ("1", "2", "8"):
        assert validate("100", "ml-io-flex", nodes) == 0
    for nodes in ("", "0", "9", "01", "+1", "1.5", "nope"):
        assert validate("100", "ml-io-flex", nodes) != 0
    assert validate("100", "ml-io-100", "1") == 0
    assert validate("100", "ml-io-100", "2") != 0
    for ranks, name, low, high in (
        ("300", "ml-io-300f", 3, 8),
        ("500", "ml-io-500f", 5, 12),
        ("1000", "ml-io-1000f", 10, 24),
        ("1200", "ml-io-1200f", 10, 32),
    ):
        assert validate(ranks, name, str(low)) == 0
        assert validate(ranks, name, str(high)) == 0
        for nodes in ("", "0", str(low - 1), str(high + 1), "01", "+3", "1.5", "nope"):
            assert validate(ranks, name, nodes) != 0
    for ranks, name, nodes in (
        ("300", "ml-io-300", "3"),
        ("500", "ml-io-500", "5"),
        ("1000", "ml-io-1000", "10"),
        ("1200", "ml-io-1200", "10"),
    ):
        assert validate(ranks, name, nodes) == 0
    for ranks, name, nodes in (
        ("300", "ml-io-300F", "4"),
        ("300", "ml-io-300f-extra", "4"),
        ("300", "ml-io-301f", "4"),
        ("500", "ml-io-300f", "6"),
        ("500", "ml-io-500f-extra", "6"),
        ("1000", "ml-io-1000fx", "11"),
        ("1200", "ml-io-1200flex", "11"),
    ):
        assert validate(ranks, name, nodes) != 0
    for ranks, name, nodes in (
        ("8", "ml-io-8", "1"),
        ("16", "ml-io-16", "1"),
        ("32", "ml-io-32", "1"),
        ("64", "ml-io-64", "1"),
        ("100", "ml-io-100", "1"),
        ("500", "ml-io-500", "5"),
        ("1000", "ml-io-1000", "10"),
        ("1200", "ml-io-1200", "10"),
    ):
        assert validate(ranks, name, nodes) == 0


def test_refiner_preserves_stock_z_and_scales_only_x_y(tmp_path: Path) -> None:
    code = _python_block(
        r'python3 - "\$CASE_DIR/system/blockMeshDict" "\$REFINE" <<\'PY\'\n(.*?)\nPY'
    )
    mesh = tmp_path / "blockMeshDict"
    mesh.write_text(
        "\n".join(
            f"hex (0 1 2 3 4 5 6 7) ({x} {y} 1) simpleGrading (1 1 1)"
            for x, y in ((46, 16), (38, 16), (46, 84), (8, 84), (38, 84))
        ),
        encoding="utf-8",
    )

    for factor, expected in (
        ("1", ((46, 16, 1), (38, 16, 1), (46, 84, 1), (8, 84, 1), (38, 84, 1))),
        ("16", ((736, 256, 1), (608, 256, 1), (736, 1344, 1), (128, 1344, 1), (608, 1344, 1))),
    ):
        subprocess.run([sys.executable, "-c", code, str(mesh), factor], check=True)
        actual = tuple(
            tuple(map(int, values))
            for values in re.findall(r"hex\s+\([^)]*\)\s+\((\d+) (\d+) (\d+)\)", mesh.read_text())
        )
        assert actual == expected


def test_solver_log_gate_accepts_complete_low_courant_run(tmp_path: Path) -> None:
    code = _python_block(
        r'python3 - "\$RUN_DIR/interIsoFoam\.log" "\$STEPS" "\$expected_time" <<\'PY\'\n(.*?)\nPY'
    )
    log = tmp_path / "solver.log"
    log.write_text(
        "Time = 0.001\nCourant Number mean: 0.1 max: 0.2\n"
        "Interface Courant Number mean: 0.1 max: 0.3\n"
        "Time = 0.002\nCourant Number mean: 0.2 max: 0.4\n",
        encoding="utf-8",
    )
    subprocess.run([sys.executable, "-c", code, str(log), "2", "0.002"], check=True)

    log.write_text("Time = 0.001\nCourant Number mean: 0.1 max: 0.5001\n", encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, "-c", code, str(log), "1", "0.001"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
    assert "Courant" in failed.stderr


def test_final_alpha_bounds_gate_rejects_overshoot(tmp_path: Path) -> None:
    code = _python_block(r'python3 - "\$minmax_file" "\$expected_time" <<\'PY\'\n(.*?)\nPY')
    extrema = tmp_path / "fieldMinMax.dat"
    extrema.write_text("# Time min(alpha.water) max(alpha.water)\n0.001 0 1\n", encoding="utf-8")
    subprocess.run([sys.executable, "-c", code, str(extrema), "0.001"], check=True)

    extrema.write_text("# Time field min max\n0.001 alpha.water 0 1\n", encoding="utf-8")
    subprocess.run([sys.executable, "-c", code, str(extrema), "0.001"], check=True)

    for data in (
        "# Time field min max\n0.001 alpha.water -0.0001 1.0001\n",
        "# Time min(alpha.water) max(alpha.water)\n0.001 -0.0001 1.0001\n",
    ):
        extrema.write_text(data, encoding="utf-8")
        failed = subprocess.run(
            [sys.executable, "-c", code, str(extrema), "0.001"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert failed.returncode != 0
        assert "outside [0,1]" in failed.stderr
