#!/usr/bin/env python3
"""Supplemental live Courant guard for the maxCo stability pilot."""
import hashlib, importlib.util, json, os, re, signal, subprocess, sys, time
from datetime import UTC, datetime
from pathlib import Path

def now(): return datetime.now(UTC).isoformat()
def write_json(path, data):
 path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name('.'+path.name+'.tmp'); tmp.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n'); os.replace(tmp,path)
def main(run):
 run=Path(run).resolve(); cfg=json.loads((run/'ram-run.json').read_text()); scratch=Path(cfg['scratch_dir']); log=scratch/'flow.log'; name=cfg['container_name']
 hp=run/'solver_process_helper.py'; spec=importlib.util.spec_from_file_location('co_guard_process_helper',hp); helper=importlib.util.module_from_spec(spec); sys.modules[spec.name]=helper; spec.loader.exec_module(helper)
 helper_hash=hashlib.sha256(hp.read_bytes()).hexdigest()
 started=now(); offset=log.stat().st_size if log.exists() else 0; carry=''; co_count=0; ico_count=0; co=None; ico=None; start_mono=time.monotonic(); fired=False
 record={'run_id':run.name,'status':'watching_new_bytes_only','started_utc':started,'initial_log_offset_bytes':offset,'coverage_note':'Started after supervisor parser defect was found; does not rescan prior output; the primary dt/epsilon/alpha/time guard remains active.','solver_process_helper_sha256':helper_hash,'co_threshold':4.0,'interface_co_threshold':4.0,'consecutive_records':3}
 write_json(run/'co-guard-start.json',record)
 with (run/'co-guard-events.jsonl').open('a',encoding='utf-8') as events:
  events.write(json.dumps(record,sort_keys=True)+'\n')
 while True:
  state=helper.inspect_container(name)
  if not state or not state['running'] or state['paused']:
   write_json(run/'pilot-co-guard-state.json',{'utc':now(),'status':'container_not_running','container':state,'maxCo':co,'interfaceCo':ico,'co_high_count':co_count,'interface_high_count':ico_count,'offset_bytes':offset}); return 0
  try:
   with log.open('rb') as f:
    f.seek(offset); chunk=f.read(); offset=f.tell()
  except OSError: chunk=b''
  if chunk:
   parts=(carry+chunk.decode('utf-8',errors='replace')).split('\n'); carry=parts.pop()
   for line in parts:
    pattern=None; which=None
    if line.startswith('Courant Number mean:'): pattern=r'max:\s*([^\s]+)'; which='co'
    elif line.startswith('Interface Courant Number mean:'): pattern=r'max:\s*([^\s]+)'; which='interface'
    if not pattern: continue
    match=re.search(pattern,line)
    try: val=float(match.group(1)) if match else float('nan')
    except ValueError: val=float('nan')
    if which=='co':
     co=val; co_count=co_count+1 if not (val!=val or abs(val)==float('inf')) and val>4.0 else 0
    else:
     ico=val; ico_count=ico_count+1 if not (val!=val or abs(val)==float('inf')) and val>4.0 else 0
    if val!=val or abs(val)==float('inf'):
     reason=f'nonfinite_{which}_courant'
    elif co_count>=3 or ico_count>=3:
     reason='repeated_courant_above_4'
    else: reason=None
    if reason and not fired:
     ev=helper.handler_evidence(name); pids=sorted(int(x['pid']) for x in ev.get('solver_ranks',[]))
     sent=[]; errors=[]
     if len(pids)==20 and ev.get('all_rank_handlers_verified'):
      for pid in pids:
       try: os.kill(pid,signal.SIGUSR2); sent.append(pid)
       except (ProcessLookupError,PermissionError) as error: errors.append({'pid':pid,'error':str(error)})
     event={'utc':now(),'status':'co_guard_safe_stop','reason':reason,'line':line,'maxCo':co,'interfaceCo':ico,'co_high_count':co_count,'interface_co_high_count':ico_count,'handler_evidence':ev,'signal':12,'delivered_pids':sent,'signal_errors':errors}
     with (run/'co-guard-events.jsonl').open('a',encoding='utf-8') as out: out.write(json.dumps(event,sort_keys=True,allow_nan=False)+'\n')
     write_json(run/'pilot-co-guard-state.json',event); fired=True
  if int(time.monotonic()-start_mono)%15<2:
   write_json(run/'pilot-co-guard-state.json',{'utc':now(),'status':'watching' if not fired else 'stop_sent','maxCo':co,'interfaceCo':ico,'co_high_count':co_count,'interface_high_count':ico_count,'offset_bytes':offset,'stop_sent':fired})
  time.sleep(1)
if __name__=='__main__':
 if len(sys.argv)!=2: raise SystemExit('usage: co_guard.py RUN_DIR')
 raise SystemExit(main(sys.argv[1]))
