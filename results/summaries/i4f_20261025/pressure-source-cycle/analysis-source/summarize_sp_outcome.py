#!/usr/bin/env python3
"""Summarize the terminal warm-fork predictor-Sp diagnostic without editing CFD inputs."""
from __future__ import annotations
import csv, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path

B = Path(__file__).resolve().parents[1]
ROOT = B.parents[3]
def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()
def kv_line(line: str) -> dict[str,str]:
    return dict(re.findall(r'([A-Za-z0-9_-]+)=([^\s]+)',line))

guard=json.loads((B/'guardian-status.json').read_text())
branch=guard['branches']['fourmouth_coldstart']
manifest=json.loads((B/'launch-manifest.json').read_text())
experiment=json.loads((B/'experiment.json').read_text())
lock=json.loads((B/'provenance/run-source-lock.json').read_text())
log_path=B/'case/log.cold-coupled'
log=log_path.read_text(errors='replace')
times=[float(x) for x in re.findall(r'(?m)^Time = ([0-9.eE+-]+)$',log)]
source_rows=[]
for line in log.splitlines():
    if 'I4F_FROZEN_ALPHA_SOURCE' in line:
        d=kv_line(line)
        if 'time_s' in d and 'used_frozen_predictor_Sp' in d:
            source_rows.append(d)

def f(row,key): return float(row[key])
# This source logger observes only its two configured cells; it is not a global Sp audit.
cell_groups={}
for row in source_rows:
    key=(row.get('rank'),row.get('local_cell'))
    cell_groups.setdefault(key,[]).append(row)
sp_abs=[]; sp_rel=[]; lagged_abs=[]; fluxres_abs=[]
for row in source_rows:
    a=f(row,'frozen_predictor_Sp'); c=f(row,'recomputed_corrector_Sp')
    sp_abs.append(abs(a-c))
    sp_rel.append(abs(a-c)/max(abs(a),abs(c),1e-300))
    lagged_abs.append(abs(f(row,'lagged_divU_residual_per_s')))
    fluxres_abs.append(abs(f(row,'local_alpha_flux_residual_per_s')))
# Last 12 complete per-step health rows carry the screen trend and inventories.
with (B/'step_health.csv').open(newline='') as fobj:
    all_health=list(csv.DictReader(fobj))
last_health=all_health[-12:]
condition_runs=[]
current_run=[]
for row in all_health:
    if row.get('pressure_update_persistent_condition')=='True':
        current_run.append(row)
    elif current_run:
        condition_runs.append(current_run); current_run=[]
if current_run: condition_runs.append(current_run)
first_condition=next((row for row in all_health if row.get('pressure_update_persistent_condition')=='True'),None)
first_three=next((run for run in condition_runs if len(run)>=3),None)
# Hash the exact saved endpoint fields and clock.
cp=Path(branch['latest_native10_checkpoint']['path'])
fields=('alpha.water','alphaPhi0.water','alphat','k','nut','omega','p','p_rgh','phi','rho','T','T.air','T.water','U')
checkpoint_hashes={name:sha(cp/name) for name in fields}
checkpoint_hashes['uniform/time']=sha(cp/'uniform/time')
endpoint=branch['last_step_health']
terminal={
 'status':branch['status'], 'normal_End':branch['terminal_log']['normal_End'],
 'exit_code':branch['docker_final_state']['ExitCode'], 'OOMKilled':branch['docker_final_state']['OOMKilled'],
 'requested_end_time_s':0.5, 'actual_native_endpoint_time_s':branch['latest_native10_checkpoint']['time_s'],
 'endpoint_shortfall_s':0.5-float(branch['latest_native10_checkpoint']['time_s']),
 'stop_reason':branch.get('write_now_reason'), 'writeNow_requested_utc':branch.get('write_now_requested_utc'),
 'wall_elapsed_s':branch.get('wall_elapsed_s'), 'completed_steps':branch.get('completed_steps'),
}
summary={
 'schema':'i4f-frozen-predictor-sp-outcome/v1',
 'created_utc':datetime.now(timezone.utc).isoformat(),
 'classification':'exploratory warm-fork algorithm diagnostic; stopped by the unchanged persistent pressure-update guard before .50 s; not a validation result',
 'experiment':{
  'bundle':str(B.relative_to(ROOT)), 'container_id':manifest['container_id'], 'docker_started_at':manifest['docker_started_at'],
  'docker_finished_at':branch['docker_final_state']['FinishedAt'], 'guard_unit':manifest.get('guard_unit','i4f-frozen-predictor-sp-diagnostic-20261026t173557z-guard'),
  'mpi_ranks':manifest['ranks'], 'cpu_quota_equiv':manifest['cpu_quota_equiv'], 'binary_sha256':manifest['binary_sha256'],
  'i4fFrozenPredictorSp':True, 'i4fFullPressureAudit':False, 'momentum_div_rhoPhi_U':'Gauss upwind',
  'source_change':'none; unchanged binary reads the existing controlDict switch',
  'restart_parent_bundle':experiment['parent']['bundle'], 'restart_parent_container_id':experiment['parent']['container_id'],
  'restart_checkpoint_time_s':experiment['parent']['checkpoint_time_s'],
  'model_change':'i4fFrozenPredictorSp false -> true after the shared .460047515286 warm checkpoint',
  'comparison_limit':'No false-flag sibling was restarted from the same .460047515286 checkpoint; this one fork cannot isolate a post-seed causal difference.'
 },
 'terminal':terminal,
 'guard':{
  'raw_pressure_contact_count':branch['raw_pressure_contact_count'],
  'persistent_final_floor_steps':branch['persistent_final_floor_steps'],
  'sustained_outer_pressure_update_steps':branch['sustained_outer_pressure_update_steps'],
  'pressure_update_threshold_Pa':100.0, 'pressure_update_ratio_threshold':0.9,
  'pressure_update_stop_after_steps':3,
  'first_single_condition_time_s':float(first_condition['time_s']) if first_condition else None,
  'first_three_consecutive_condition_time_s':float(first_three[2]['time_s']) if first_three else None,
  'consecutive_condition_run_lengths_and_ranges':[{ 'rows':len(run), 'start_time_s':float(run[0]['time_s']), 'end_time_s':float(run[-1]['time_s']) } for run in condition_runs],
  'last_final_dp_Pa':endpoint['final_outer_max_abs_dp_Pa'],
  'last_penultimate_dp_Pa':endpoint['penultimate_outer_max_abs_dp_Pa'],
  'last_final_to_penultimate_ratio':endpoint['pressure_update_final_to_penultimate_ratio'],
  'last_max_abs_dU_m_s':endpoint['final_outer_max_abs_dU_m_s'],
  'last_max_abs_dalpha':endpoint['final_outer_max_abs_dalpha1'],
  'last_max_abs_dphi_m3_s':endpoint['final_outer_max_abs_dphi_m3_s'],
  'raw_corrector_min_pressure_Pa_at_terminal':endpoint['raw_corrector_min_pressure_Pa_this_step'],
  'final_field_min_pressure_Pa':endpoint['final_field_min_p_Pa'],
  'final_field_min_pressure_cell_coordinate_m':endpoint['final_min_p_location'],
  'final_field_min_temperature_K':endpoint['final_field_min_T_K'],
  'final_field_min_density_kg_m3':endpoint['final_field_min_rho_kg_m3'],
  'clipped_liquid_mass_kg':endpoint['raw_clipped_liquid_mass_peak_single_pass_kg'],
  'diagnostic_errors':branch['diagnostic_errors'], 'parser_errors':branch['parser_errors'],
 },
 'phase_inventory_at_terminal':{
  'water_kg':endpoint['water_inventory_kg'], 'gas_kg':endpoint['gas_inventory_kg'],
  'water_cumulative_defect_kg':endpoint['water_cumulative_defect_kg'],
  'water_cumulative_defect_fraction_initial':endpoint['water_cumulative_defect_fraction_initial'],
  'gas_cumulative_defect_kg':endpoint['gas_cumulative_defect_kg'],
  'gas_cumulative_defect_fraction_initial':endpoint['gas_cumulative_defect_fraction_initial'],
  'water_boundary_flux_kg_s':endpoint['water_boundary_flux_kg_s'], 'gas_boundary_flux_kg_s':endpoint['gas_boundary_flux_kg_s'],
 },
 'frozen_predictor_trace':{
  'record_tag':'I4F_FROZEN_ALPHA_SOURCE', 'rows':len(source_rows),
  'used_frozen_predictor_Sp_true_rows':sum(r.get('used_frozen_predictor_Sp')=='true' for r in source_rows),
  'observed_rank_local_cells':sorted([{'rank':int(k[0]),'local_cell':int(k[1]),'rows':len(v)} for k,v in cell_groups.items()],key=lambda x:(x['rank'],x['local_cell'])),
  'time_range_s':[min(float(r['time_s']) for r in source_rows),max(float(r['time_s']) for r in source_rows)] if source_rows else None,
  'maximum_abs_predictor_vs_corrector_Sp_difference_s-1':max(sp_abs,default=None),
  'maximum_relative_predictor_vs_corrector_Sp_difference_at_these_cells':max(sp_rel,default=None),
  'maximum_abs_logged_lagged_divU_residual_s-1':max(lagged_abs,default=None),
  'maximum_abs_logged_local_alpha_flux_residual_s-1':max(fluxres_abs,default=None),
  'qualification':'Trace covers only the two configured diagnostic cells on rank 2, not a mesh-wide maximum. Equality there does not establish equality of Sp over all cells or explain global pressure updates.'
 },
 'time_history_tail':[{k:r[k] for k in ['time_s','deltaT_logged_s','outer_iteration','phase_mass_pass','water_inventory_kg','gas_inventory_kg','final_field_min_p_Pa','raw_corrector_min_pressure_Pa_this_step','final_outer_max_abs_dp_Pa','penultimate_outer_max_abs_dp_Pa','pressure_update_final_to_penultimate_ratio','pressure_update_consecutive_steps','final_outer_max_abs_dU_m_s','final_outer_max_abs_dalpha1','final_outer_max_abs_dphi_m3_s']} for r in last_health],
 'checkpoint':{'path':str(cp.relative_to(ROOT)),'complete':True,'field_hashes':checkpoint_hashes},
 'provenance_hashes':{
  'experiment_json_at_GO_sha256':manifest['experiment_record_sha256'],
  'run_input_freeze_sha256':manifest['input_freeze_sha256'],
  'run_source_lock_sha256':sha(B/'provenance/run-source-lock.json'),
  'binary_sha256':sha(B/'bin/compressibleInterFoamFrozenAlphaSourceV2NoPout'),
  'controlDict_sha256_at_GO':json.loads((B/'input-freeze.json').read_text())['files'][[x['path'] for x in json.loads((B/'input-freeze.json').read_text())['files']].index('case/system/controlDict')]['sha256'],
  'controlDict_before_guard_writeNow_sha256':sha(B/'controlDict.before-guard-writeNow.bak'),
  'log_sha256':sha(log_path), 'step_health_csv_sha256':sha(B/'step_health.csv'),
  'guard_sha256':sha(B/'guard.py'), 'launcher_sha256':manifest['launcher_sha256'],
  'alphaEqn_source_sha256':'f2f10939f37b7765f8e4a1c032daab3140c5605533ac2bf955245925a425df7e',
  'compressibleInterFoam_C_source_sha256':'fa5f33ba89ed73c1615dfcdb1b0d8ac3e6577fe6414332af7085c72e1faf7078'
 },
 'limitations':[
  'The true-flag run was not paired with a fresh false-flag continuation from the same seed.',
  'It stopped at .494224620516 s, short of the declared .5 s target, because the existing persistent pressure-update guard fired; do not treat normal End from writeNow as target attainment.',
  'Zero raw pressure-floor contacts does not imply converged pressure updates or a healthy/validated flow solution.',
  'The local alpha-source trace samples two cells only and does not establish global Sp differences or causality.',
  'No automatic restart or physical-method adoption follows from this diagnostic.'
 ]
}
out=B/'analysis/terminal-diagnostic-v1.json'
out.write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(json.dumps({'output':str(out.relative_to(ROOT)),'sha256':sha(out),'source_rows':len(source_rows),'trace_cell_groups':len(cell_groups),'max_abs_dSp':max(sp_abs,default=None),'max_rel_dSp':max(sp_rel,default=None),'first_single_condition_time_s':summary['guard']['first_single_condition_time_s'],'first_three_consecutive_condition_time_s':summary['guard']['first_three_consecutive_condition_time_s']},indent=2))
