#!/usr/bin/env python3
"""Assemble a compact scalar packet from the immutable private tight-map run."""
from __future__ import annotations
import csv, hashlib, json, re, shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
B=ROOT/'results/runs/i4f-frozen-pressure-operator-tightmaps-20261026T2234Z'

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
 return h.hexdigest()
def utc()->str: return datetime.now(timezone.utc).isoformat()
def main()->None:
 vector=json.loads((B/'analysis/tight-map-vector-summary.json').read_text())
 log=(B/'logs/probe-solver.log').read_text(errors='replace')
 guard=json.loads((B/'guardian-status.json').read_text())
 launch=json.loads((B/'launch-manifest.json').read_text())
 freeze=json.loads((B/'provenance/probe-input-freeze-release.json').read_text())
 if guard.get('status')!='probe_diagnostic_complete_no_physical_checkpoint': raise RuntimeError('private tight-map diagnostic is not terminal/captured')
 if guard.get('docker_exit_code')!=0 or guard.get('probe_marker_valid') is not True: raise RuntimeError('private terminal record lacks valid completion')
 source_patch=B/'provenance/source.patch'
 shutil.copy2(source_patch,OUT/'source.patch')
 shutil.copy2(B/'analysis/tight-map-vector-summary.json',OUT/'vector-metrics.json')
 shutil.copy2(B/'analysis/analyze_sweeps.py',OUT/'analyze_sweeps.py')
 pattern=re.compile(r'GAMG:\s+Solving for p_rgh, Initial residual = ([^,]+), Final residual = ([^,]+), No Iterations (\d+)')
 marker='I4F_FROZEN_PRESSURE_MAP_SOLVER_CONTROLS'
 tail=log[log.index(marker):]
 solves=[(float(a),float(b),int(n)) for a,b,n in pattern.findall(tail)]
 if len(solves)!=12: raise RuntimeError(f'expected 8 baseline plus 4 centered-response p solves, got {len(solves)}')
 baseline=vector['baseline_sweeps']
 if len(baseline)!=8: raise RuntimeError('expected eight unperturbed map sweeps')
 scalar_path=OUT/'baseline-sweeps.csv'
 with scalar_path.open('w',newline='') as f:
  w=csv.writer(f); w.writerow(['map','sweep','solver','initial_residual','final_residual','iterations','max_abs_delta_p_Pa','volume_weighted_l2_delta_p_Pa_m3_sqrt','volume_weighted_rms_delta_p_Pa'])
  for i,row in enumerate(baseline):
   ini,fin,it=solves[i]
   diff=row.get('difference_from_previous_output',row.get('difference'))
   w.writerow(['unperturbed',i+1,'GAMG',format(ini,'.17g'),format(fin,'.17g'),it,format(diff['max_abs'],'.17g'),format(diff['volume_weighted_l2'],'.17g'),format(diff['volume_weighted_rms'],'.17g')])
 responses=vector['centered_response']
 response_path=OUT/'centered-responses.csv'
 with response_path.open('w',newline='') as f:
  w=csv.writer(f); w.writerow(['amplitude_Pa','sign','solver','initial_residual','final_residual','iterations','volume_weighted_L2_gain','signed_alignment_cosine','signed_projection_along_v','centered_vector_weighted_rms_per_Pa'])
  solve_i=8
  for amp in ('1','10'):
   for sign in ('plus','minus'):
    ini,fin,it=solves[solve_i]; solve_i+=1
    r=responses[amp]
    w.writerow([amp,sign,'GAMG',format(ini,'.17g'),format(fin,'.17g'),it,format(r['gain_recomputed'],'.17g'),format(r['alignment_recomputed'],'.17g'),format(r['projection_recomputed'],'.17g'),format(r['centered_vector_weighted_rms_per_Pa'],'.17g')])
 probe=B/'case/i4f_frozen_pressure_probe'
 raw=[]
 for p in sorted(probe.iterdir()):
  if p.is_file() and (p.name.endswith('.bin') or p.name.endswith('-index.csv') or p.name=='selected-pressure-rows.csv'):
   raw.append({'private_path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)})
 logpath=B/'logs/probe-solver.log'
 summary={
  'schema':'i4f-frozen-pressure-tight-map-summary/v1',
  'classification':'bounded algebraic frozen-pressure diagnostic; not a physical continuation or a global stability test',
  'run':{'bundle':str(B.relative_to(ROOT)),'docker_id':launch['container_id'],'docker_name':launch['container_name'],'started_at_utc':launch['docker_started_at'],'finished_at_utc':guard['docker_finished_at'],'exit_code':guard['docker_exit_code'],'image':launch['image'],'mpi_ranks':launch['ranks'],'cpu_quota':launch['cpu_quota_equiv'],'binary_sha256':launch['binary_sha256'],'source_patch_sha256':sha(source_patch),'solver_log_sha256':sha(logpath),'case_freeze_sha256':launch['probe_input_freeze_sha256'],'go_sha256':launch['go_sha256']},
  'state':{'canonical_seed_case':'results/runs/i4f-upwind-momentum-warm-20261026T130013Z/case/processors10/0.460047515286','time_s':0.493844492237,'time_index':2736,'deltaT_s':9.514090971421265e-5,'physical_outer_iteration':8,'physical_pressure_corrector':2,'mesh_cells':299214,'sum_cell_volume_m3':25.1417669189096,'global_cells_under_test':[31926,62270],'global_face_under_test':136938},
  'method':{'map':'Frozen pressure-only map from the same physical second p_rgh equation; only p_rgh and explicit non-orthogonal correction evolve. Processor-neighbor pressure exchange remains live.','physical_fvSolution_unchanged':True,'physical_p_rgh_tolerance':1e-10,'diagnostic_solver':'GAMG','diagnostic_tolerance':1e-14,'diagnostic_relTol':0.0,'diagnostic_maxIter':1000,'matrix_dimensions':'[0 3 -1 0 0 0 0]','matrix_residual_units':'integrated m^3/s, not per-volume units','unperturbed_maps':8,'centered_response_maps_per_sign_and_amplitude':1,'amplitudes_Pa':[1,10]},
  'results':{'baseline_solver_iterations':[x[2] for x in solves[:8]],'baseline_solver_final_residuals':[x[1] for x in solves[:8]],'note':'Baseline differences become exactly zero after the fifth solve because the later GAMG solves take zero iterations once the residual is below tolerance; those unchanged snapshots are not evidence of further operator contraction.','centered_response':responses,'relative_centered_response_1Pa_vs_10Pa_weighted_L2':vector['relative_centered_response_1Pa_vs_10Pa_weighted_L2'],'integrity':{'held_field_count':38,'local_mismatches':0,'global_mismatch_checks':0,'comp1_and_comp2_source_hashes_unchanged':True,'original_comp_matrices_unchanged':True,'fixedFluxPressure_gradient_hash_unchanged':True}},
  'interpretation_limit':'The selected perturbation direction is damped in both tested amplitudes (weighted gains about 0.032), with negative alignment. The centered 1 Pa and 10 Pa response vectors differ by 23.2% in weighted L2, so an amplitude-independent derivative is not established. This single direction/state does not establish global pressure-map stability or explain the physical pressure cycle.',
  'physical_checkpoint_written':False,'continuation_after_probe':False,'native_seed_only_checkpoint':True,
  'private_raw_vector_artifacts':raw,
  'private_source_parent':'results/runs/i4f-frozen-pressure-operator-20261026T2200Z/build/source/v8-frozen-pressure-probe; public patch is relative to this private parent and the tight-map private source tree.'
 }
 (OUT/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+'\n')
 files=[]
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='artifact-manifest.json': files.append({'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
 manifest={'schema':'i4f-frozen-pressure-tight-map-artifacts/v1','created_utc':utc(),'files':files,'private_evidence':{'launch_manifest_sha256':sha(B/'launch-manifest.json'),'guardian_status_sha256':sha(B/'guardian-status.json'),'probe_freeze_sha256':sha(B/'provenance/probe-input-freeze-release.json'),'source_files_manifest_sha256':sha(B/'provenance/source-files-release.sha256'),'raw_vector_artifact_count':len(raw),'raw_vector_artifacts_sha256_listing':'summary.json.private_raw_vector_artifacts'}}
 (OUT/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':'packet_built','public_files':[x['path'] for x in files],'raw_vector_artifact_count':len(raw),'baseline_iterations':[x[2] for x in solves[:8]],'response_gains':{a:responses[a]['gain_recomputed'] for a in responses}},indent=2))
if __name__=='__main__': main()
