from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "run_restas_still_air_vof.py"
SPEC = importlib.util.spec_from_file_location("restas_still_air_vof", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
still_air = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = still_air
SPEC.loader.exec_module(still_air)


def test_long_case_is_still_air_and_keeps_slot_resolution(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    inputs = still_air._prepare_case(case_dir, ranks=4)

    assert inputs["mesh_cells_expected"] == 1_640_760
    assert inputs["cells_across_slot_short_axis"] == 6
    assert inputs["cells_along_slot_long_axis"] == 40
    assert inputs["end_time_s"] == 1.0
    assert inputs["crossflow_m_s"] == [0.0, 0.0, 0.0]
    assert inputs["turbulence_model"] == "realizable k-epsilon RANS"
    assert inputs["source_turbulence_intensity"] == 0.01

    control = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    mesh = (case_dir / "system" / "blockMeshDict").read_text(encoding="utf-8")
    velocity = (case_dir / "0" / "U").read_text(encoding="utf-8")
    turbulence = (case_dir / "constant" / "turbulenceProperties").read_text(encoding="utf-8")
    schemes = (case_dir / "system" / "fvSchemes").read_text(encoding="utf-8")

    assert "endTime 1;" in control
    assert mesh.count("simpleGrading (1 1 0.25)") == 25
    assert "internalField uniform (0 0 0);" in velocity
    assert (
        "uniformValue table ((0 (0 0 -4.8)) (0.0795 (0 0 -4.8)) (0.0805 (0 0 0)) (1 (0 0 0)))"
        in velocity
    )
    assert "density variable;" in turbulence
    assert "RASModel realizableKE;" in turbulence
    assert "div(rhoPhi,k) Gauss limitedLinear 1;" in schemes
    assert "div(rhoPhi,epsilon) Gauss limitedLinear 1;" in schemes
    assert 0.038 < inputs["mesh_cell_width_m"]["vertical_top_cell_approx"] < 0.039
    assert 0.153 < inputs["mesh_cell_width_m"]["vertical_bottom_cell_approx"] < 0.155
