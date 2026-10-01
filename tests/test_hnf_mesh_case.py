from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cases/restas_amr_probe"))
import run_hnf_mesh_case as hnf_case  # noqa: E402


def prepare_pulsed_case(tmp_path: Path, model: str) -> Path:
    case = tmp_path / "case"
    inputs = hnf_case.prepare_case.prepare_case(case, model, 4, 0.025, 0.08)
    values = inputs["rans_boundary_values"]
    hnf_case.install_pulsed_source_turbulence(
        case,
        model=model,
        pulse_end_s=0.08,
        end_s=0.1,
        k_value=values["source_k_m2_s2"],
        epsilon_value=values["source_epsilon_m2_s3"],
    )
    return case


def test_sst_source_pulse_decays_k_and_keeps_positive_omega(tmp_path: Path) -> None:
    case = tmp_path / "case"
    inputs = hnf_case.prepare_case.prepare_case(case, "k-omega-sst", 4, 0.025, 0.08)
    omega_before = (case / "0/omega").read_text(encoding="utf-8")
    values = inputs["rans_boundary_values"]

    # SST has no epsilon field: decay k and preserve its positive omega inlet value.
    hnf_case.install_pulsed_source_turbulence(
        case,
        model="k-omega-sst",
        pulse_end_s=0.08,
        end_s=0.1,
        k_value=values["source_k_m2_s2"],
        epsilon_value=values["source_epsilon_m2_s3"],
    )
    k_text = (case / "0/k").read_text(encoding="utf-8")
    assert k_text.count("uniformValue table") == 4
    assert "(0.080001 1e-12)" in k_text
    assert (case / "0/omega").read_text(encoding="utf-8") == omega_before
    assert not (case / "0/epsilon").exists()


def test_ke_source_pulse_decays_k_and_epsilon(tmp_path: Path) -> None:
    case = prepare_pulsed_case(tmp_path, "realizable-ke")

    for field in ("k", "epsilon"):
        text = (case / "0" / field).read_text(encoding="utf-8")
        assert text.count("uniformValue table") == 4
        assert "(0.080001 1e-12)" in text


def test_sst_preparation_accepts_full_host_cpu_count(tmp_path: Path) -> None:
    case = tmp_path / "case"
    inputs = hnf_case.prepare_case.prepare_case(case, "k-omega-sst", 20, 0.025, 0.08)

    assert inputs["turbulence_model"] == "k-omega-sst"
    decomposition = (case / "system/decomposeParDict").read_text(encoding="utf-8")
    assert "numberOfSubdomains 20;" in decomposition
    assert "n (20 1 1)" in decomposition
    assert (case / "0/omega").is_file()
