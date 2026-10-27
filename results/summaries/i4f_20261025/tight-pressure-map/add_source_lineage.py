#!/usr/bin/env python3
"""Add and independently verify the complete published-v8-to-tight source delta."""
from __future__ import annotations
import difflib, hashlib, json, shutil, subprocess, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
BASE_REL=Path('results/summaries/i4f_20261025/restart-history/solver-source/v8')
BASE=ROOT/BASE_REL
BASE_MANIFEST=ROOT/'results/summaries/i4f_20261025/restart-history/solver-source/v8-source-files.json'
TARGET_REL=Path('results/runs/i4f-frozen-pressure-operator-tightmaps-20261026T2234Z/build/source/v8-frozen-pressure-tight-maps')
TARGET=ROOT/TARGET_REL
TARGET_MANIFEST=ROOT/'results/runs/i4f-frozen-pressure-operator-tightmaps-20261026T2234Z/provenance/source-files-release.sha256'
RUN=ROOT/'results/runs/i4f-frozen-pressure-operator-tightmaps-20261026T2234Z'
EXPECTED_CHANGED={
 'applications/solvers/multiphase/VoF/alphaEqn.H',
 'applications/solvers/multiphase/compressibleInterFoam/Make/files',
 'applications/solvers/multiphase/compressibleInterFoam/compressibleInterFoam.C',
 'applications/solvers/multiphase/compressibleInterFoam/pEqn.H',
 'applications/solvers/multiphase/compressibleInterFoam/i4fFrozenPressureProbe.H',
}
def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat()
def read_target_manifest():
 rows={}
 for line in TARGET_MANIFEST.read_text().splitlines():
  digest,rel=line.split('  ',1); rows[rel]=digest
 return rows
def read_base_manifest():
 obj=json.loads(BASE_MANIFEST.read_text())
 return {x['path']:x['sha256'] for x in obj['files']},obj

def main():
 base_hash,base_obj=read_base_manifest(); target_hash=read_target_manifest()
 if len(base_hash)!=70 or len(target_hash)!=69: raise RuntimeError('unexpected published source file count')
 for rel,digest in base_hash.items():
  p=BASE/rel
  if not p.is_file() or sha(p)!=digest: raise RuntimeError(f'published-v8 source mismatch: {rel}')
 for rel,digest in target_hash.items():
  p=TARGET/rel
  if not p.is_file() or sha(p)!=digest: raise RuntimeError(f'tight-map target source mismatch: {rel}')
 changed={p for p,h in target_hash.items() if base_hash.get(p)!=h}
 if changed!=EXPECTED_CHANGED: raise RuntimeError(f'changed path set differs from the reviewed source delta: {sorted(changed)}')
 pieces=[]
 for rel in sorted(changed):
  old=BASE/rel; new=TARGET/rel
  a=old.read_text(encoding='utf-8').splitlines(keepends=True) if old.exists() else []
  b=new.read_text(encoding='utf-8').splitlines(keepends=True)
  fromfile=f'a/{rel}' if old.exists() else '/dev/null'
  tofile=f'b/{rel}'
  pieces.extend(difflib.unified_diff(a,b,fromfile=fromfile,tofile=tofile,n=3))
  if pieces and pieces[-1] and not pieces[-1].endswith('\n'): pieces.append('\n')
 patch=OUT/'v8-published-to-tight-map.patch'; patch.write_text(''.join(pieces),encoding='utf-8')
 shutil.copy2(TARGET_MANIFEST,OUT/'tight-source-manifest.sha256')
 build_src=RUN/'scripts/build_solver.sh'; shutil.copy2(build_src,OUT/'build_solver.sh')
 # Verify the portable patch in a separate temporary copy of the published v8 package.
 with tempfile.TemporaryDirectory(prefix='i4f-tight-source-lineage-') as td:
  work=Path(td)/'v8'; shutil.copytree(BASE,work,symlinks=True)
  applied=subprocess.run(['patch','--batch','--forward','-p1','-i',str(patch)],cwd=work,capture_output=True,text=True,check=False)
  if applied.returncode: raise RuntimeError(f'patch application failed: {applied.stdout}\n{applied.stderr}')
  reproduced=[]
  for rel,digest in target_hash.items():
   p=work/rel
   if not p.is_file() or sha(p)!=digest: raise RuntimeError(f'patched source hash mismatch: {rel}')
   reproduced.append(rel)
  verification={'command':['patch','--batch','--forward','-p1','-i',str(patch)],'patch_exit_code':applied.returncode,'patch_stdout':applied.stdout,'patch_stderr':applied.stderr,'verified_target_manifest_entries':len(reproduced),'target_manifest_sha256':sha(TARGET_MANIFEST),'all_declared_target_hashes_match':True,'temporary_copy_removed_after_verification':True}
 (OUT/'source-lineage-verification.json').write_text(json.dumps(verification,indent=2,sort_keys=True)+'\n')
 launch=json.loads((RUN/'launch-manifest.json').read_text())
 source_data={
  'schema':'i4f-tight-pressure-map-source-lineage/v1',
  'created_utc':utc(),
  'classification':'Portable source delta and exact source-manifest verification; case inputs and restart fields remain in the ignored run bundle.',
  'base':{'package_path':str(BASE_REL),'source_file_manifest_path':'results/summaries/i4f_20261025/restart-history/solver-source/v8-source-files.json','source_file_manifest_sha256':sha(BASE_MANIFEST),'source_manifest_entries':len(base_hash),'published_immediate_parent_binary_sha256':'12d8ed3e808deffa56a8d21e8e23227af65c27c76e57122a48986e732089da3a'},
  'delta':{'patch_path':'v8-published-to-tight-map.patch','patch_sha256':sha(patch),'changed_source_paths':sorted(changed),'patch_scope':'Four modified source/build-definition files and one added pressure-probe header; no generated lnInclude, object, dependency, binary or build-cache files.', 'verification_path':'source-lineage-verification.json','verification_sha256':sha(OUT/'source-lineage-verification.json')},
  'output':{'private_source_tree_path':str(TARGET_REL),'source_manifest_path':'tight-source-manifest.sha256','source_manifest_sha256':sha(OUT/'tight-source-manifest.sha256'),'declared_output_source_entries':len(target_hash),'build_script_path':'build_solver.sh','build_script_sha256':sha(OUT/'build_solver.sh'),'solver_binary_name':'compressibleInterFoamI4FFrozenPressureTightMap','binary_sha256':launch['binary_sha256'],'binary_bytes':(RUN/'bin/compressibleInterFoamI4FFrozenPressureTightMap').stat().st_size,'pinned_image':launch['image'],'pinned_image_id':'sha256:f5080db350a74a6130f248e2fd4d4fd1a8bd9309054b49ca160afe45a4d0c45b','build_log_sha256':sha(RUN/'logs/build.log')},
  'historical_delta_artifact':{'path':'source.patch','sha256':sha(OUT/'source.patch'),'lineage':'This earlier diff is only the tight-map change relative to a private frozen-pressure-probe source tree; it is preserved as history and is not sufficient to reconstruct tight source from published v8 by itself.'},
  'qualification':'The base is the restart-history channel-D published v8 source package, not the separate apparatus v8-restart-cold source overlay associated with the 12d8 apparatus binary. The published v8 package has two unchanged helper scripts (Allwclean/Allwmake) not included in the tight run’s 69-entry source manifest. Applying this delta to the published v8 tree reproduces every declared tight source hash. It does not recreate the mesh, case dictionaries, restart fields, dynamicCode cache or exact build environment beyond the pinned image/build script.'
 }
 lineage_path=OUT/'source-lineage.json'
 lineage_path.write_text(json.dumps(source_data,indent=2,sort_keys=True)+'\n')
 summary_path=OUT/'summary.json'; summary=json.loads(summary_path.read_text())
 summary['source_lineage']={'complete_patch':'v8-published-to-tight-map.patch','complete_patch_sha256':source_data['delta']['patch_sha256'],'base_package_path':str(BASE_REL),'base_source_manifest_sha256':source_data['base']['source_file_manifest_sha256'],'output_source_manifest_sha256':source_data['output']['source_manifest_sha256'],'verified_declared_output_source_hashes':len(target_hash),'build_script_sha256':source_data['output']['build_script_sha256'],'pinned_image':source_data['output']['pinned_image'],'binary_sha256':source_data['output']['binary_sha256'],'historical_source.patch_role':source_data['historical_delta_artifact']['lineage'],'qualification':source_data['qualification']}
 summary_path.write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+'\n')
 public_files=[]
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='artifact-manifest.json': public_files.append({'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
 packet_manifest={'schema':'i4f-frozen-pressure-tight-map-artifacts/v2','created_utc':utc(),'files':public_files,'source_lineage_verification':{'source_lineage_path':'source-lineage.json','source_lineage_sha256':sha(lineage_path),'portable_patch_sha256':source_data['delta']['patch_sha256'],'published_v8_manifest_sha256':source_data['base']['source_file_manifest_sha256'],'tight_manifest_sha256':source_data['output']['source_manifest_sha256'],'patched_target_source_hashes_verified':len(target_hash),'private_raw_vector_artifact_count':len(json.loads(summary_path.read_text())['private_raw_vector_artifacts'])},'private_evidence':{'launch_manifest_sha256':sha(RUN/'launch-manifest.json'),'guardian_status_sha256':sha(RUN/'guardian-status.json'),'probe_freeze_sha256':sha(RUN/'provenance/probe-input-freeze-release.json'),'private_source_manifest_sha256':sha(TARGET_MANIFEST)}}
 (OUT/'artifact-manifest.json').write_text(json.dumps(packet_manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':'portable_patch_verified_and_packet_manifest_updated','changed_paths':sorted(changed),'patch_sha256':source_data['delta']['patch_sha256'],'target_manifest_sha256':source_data['output']['source_manifest_sha256'],'verified_target_entries':len(target_hash),'binary_sha256':launch['binary_sha256'],'public_files':[p['path'] for p in public_files]},indent=2))
if __name__=='__main__':main()
