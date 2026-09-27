#!/usr/bin/env python3
"""Feed actual compiled timestep bytes into the frozen analyzer's offline fixture."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

root = Path(__file__).resolve().parents[1]
fixture_root = root / "analysis" / "fixture_root"
output_root = root / "analysis" / "bundle" / "analyzer-integration"
source_output = root / "outputs" / "m3-multistate-pass"
analyzer_path = fixture_root / "src" / "aerial_drop" / "flutas_source_analyzer.py"
fixture_path = fixture_root / "tests" / "test_flutas_source_analyzer.py"

sys.path.insert(0, str(fixture_root / "src"))
pytest_stub = types.ModuleType("pytest")
pytest_stub.mark = types.SimpleNamespace(
    parametrize=lambda *args, **kwargs: (lambda function: function)
)
sys.modules.setdefault("pytest", pytest_stub)

from aerial_drop import flutas_source_analyzer as analyzer  # noqa: E402

spec = importlib.util.spec_from_file_location("candidate5_pinned_fixtures", fixture_path)
if spec is None or spec.loader is None:
    raise RuntimeError("could not import pinned offline analyzer fixture")
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixtures
spec.loader.exec_module(fixtures)

actual_inputs_bytes = (source_output / "ledger_timestep-inputs.json").read_bytes()
actual_inputs = json.loads(actual_inputs_bytes)
actual_timestep = (source_output / "ledger_timestep-restriction.csv").read_bytes()
rows = list(csv.DictReader(actual_timestep.decode("utf-8").splitlines()))
if len(rows) != 15 or [row["state_index"] for row in rows] != [str(i) for i in range(15)]:
    raise AssertionError("compiled timestep CSV does not contain U0-U14 in order")

manifest, files, pins = fixtures._build_bundle(
    timestep_inputs=actual_inputs,
    raw_rate=float(rows[0]["dtic_raw_s_inv"]),
)
record = json.loads(manifest)
analyzer_hash = hashlib.sha256(analyzer_path.read_bytes()).hexdigest()
record["analyzer_sha256"] = analyzer_hash
manifest = fixtures._manifest_bytes(record)
pins = analyzer.ExpectedProvenance(
    **{
        **pins.__dict__,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "analyzer_sha256": analyzer_hash,
    }
)
files[analyzer.TIMESTEP_FILE] = actual_timestep
manifest, files, pins = fixtures._refresh_bundle(manifest, files, pins)
report = analyzer.analyze_bundle(manifest, files, pins)

output_root.mkdir(parents=True, exist_ok=True)
(output_root / "manifest.json").write_bytes(manifest)
for name, data in files.items():
    (output_root / name).write_bytes(data)
report_record = {
    "evidence_scope": "synthetic offline fixture; compiled candidate5 timestep table only",
    "synthetic_phase_and_velocity_tables": True,
    "source_solver_run": False,
    "scientific_gate_disposition": "none",
    "candidate_patch_sha256": hashlib.sha256(
        (root / "reference" / "candidate-source-boundary.patch").read_bytes()
    ).hexdigest(),
    "producer_vof_sha256": hashlib.sha256(
        (root / "reference" / "pinned-source" / "vof.f90").read_bytes()
    ).hexdigest(),
    "analyzer_sha256": analyzer_hash,
    "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
    "schema_sha256": hashlib.sha256(
        (fixture_root / "experiments" / "FLUTAS_CANDIDATE5_OBSERVABILITY_SCHEMA.md").read_bytes()
    ).hexdigest(),
    "producer_timestep_inputs_sha256": hashlib.sha256(actual_inputs_bytes).hexdigest(),
    "producer_timestep_csv_sha256": hashlib.sha256(actual_timestep).hexdigest(),
    "structural_disposition": report.structural_disposition,
    "evidence_disposition": report.evidence_disposition,
    "decision": report.decision,
    "issue_codes": list(report.issue_codes),
    "row_counts": dict(report.row_counts),
    "timestep_rows_checked": report.timestep_rows_checked,
}
(output_root / "analyzer-report.json").write_text(
    json.dumps(report_record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
if (
    report.structural_disposition != "complete"
    or report.evidence_disposition != "complete"
    or report.timestep_rows_checked != 15
):
    raise AssertionError(json.dumps(report_record, sort_keys=True))
print(json.dumps(report_record, sort_keys=True))
