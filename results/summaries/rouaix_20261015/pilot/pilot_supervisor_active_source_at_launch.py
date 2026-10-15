#!/usr/bin/env python3
"""Bounded CPU-only Rouaix stability pilot with incremental log guard."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import signal
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
WALL_S = 3600
SCRATCH_LIMIT = 16 * 1024**3
MEM_FLOOR = 24 * 1024**3
DISK_FLOOR = 2 * 1024**3
TARGET_TIME = 3.12
GUARD = {
    "dt_below_s": 1e-9,
    "dt_low_steps": 3,
    "epsilon_abs_bound_above": 1e10,
    "epsilon_high_steps": 2,
    "co_max_above": 4.0,
    "co_high_steps": 3,
    "interface_co_max_above": 4.0,
    "interface_co_high_steps": 3,
    "post_bounded_alpha_violation": 1e-3,
    "alpha_violation_steps": 2,
    "dt_below_ulp_steps": 3,
    "no_time_line_progress_s": 180,
}

def utc() -> str:
    return datetime.now(UTC).isoformat()

def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(tmp, path)

def append_event(run: Path, scratch: Path, event: dict[str, Any]) -> None:
    event = {"utc": utc(), **event}
    line = json.dumps(event, sort_keys=True, allow_nan=False) + "\n"
    with (scratch / "pilot-events.jsonl").open("a", encoding="utf-8") as f:
        f.write(line)
    if disk_free() >= DISK_FLOOR and metadata_bytes(run) < 50 * 1024**2:
        with (run / "pilot-events.jsonl").open("a", encoding="utf-8") as f:
            f.write(line)

def disk_free() -> int:
    return os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize

def mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return 0

def tree_bytes(path: Path) -> int:
    total = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        for name in files:
            p = Path(base) / name
            if not p.is_symlink():
                try:
                    total += p.stat().st_size
                except FileNotFoundError:
                    pass
    return total

def metadata_bytes(path: Path) -> int:
    total = 0
    for p in path.iterdir():
        if p.name == "durable-checkpoints" or p.is_symlink():
            continue
        total += tree_bytes(p) if p.is_dir() else p.stat().st_size
    return total

def load_helper(run: Path):
    path = run / "solver_process_helper.py"
    cfg = json.loads((run / "ram-run.json").read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != cfg["signal_process_helper_sha256"]:
        raise RuntimeError("solver process helper hash changed after declaration")
    spec = importlib.util.spec_from_file_location("rouaix_pilot_process_helper", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import process helper")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

def docker_cmd(run: Path, cfg: dict[str, Any]) -> list[str]:
    case = Path(cfg["case"])
    name = cfg["container_name"]
    flow = (
        "set +e +u; source /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1; setup=$?; "
        "set -euo pipefail; printf 'ROUAIX_SETUP_EXIT code=%s\\n' \"$setup\"; "
        'if [ "$setup" -ne 0 ]; then exit "$setup"; fi; '
        'run_stage() { stage=$1; shift; set +e; "$@"; code=$?; set -e; '
        'printf \'ROUAIX_STAGE_EXIT stage=%s code=%s\\n\' "$stage" "$code"; '
        'if [ "$code" -ne 0 ]; then exit "$code"; fi; }; '
        "run_stage dictionary-app foamDictionary system/controlDict -entry application -value; "
        "run_stage dictionary-start foamDictionary system/controlDict -entry startFrom -value; "
        "run_stage dictionary-end foamDictionary system/controlDict -entry endTime -value; "
        "run_stage dictionary-maxCo foamDictionary system/controlDict -entry maxCo -value; "
        "run_stage dictionary-ranks foamDictionary system/decomposeParDict -entry numberOfSubdomains -value; "
        "run_stage solver timeout --signal=TERM --kill-after=60s 3600s mpirun --bind-to none -mca mpi_yield_when_idle 1 -np 20 interIsoFoam -parallel; "
        "run_stage reconstruct reconstructPar -latestTime -fields '(alpha.water U p_rgh k epsilon nut)'"
    )
    return [
        "docker", "run", f"--name={name}", f"--cidfile={run / 'flow.cid'}",
        f"--cpus={cfg['cpu_quota_initial']}", f"--cpu-shares={cfg['cpu_shares']}",
        f"--memory={cfg['memory_gib']}g", "--memory-swap", f"{cfg['memory_gib']}g",
        "--log-driver=local", "--log-opt=max-size=10m", "--log-opt=max-file=2",
        "--env", "OMP_NUM_THREADS=1", "--env", "OMP_THREAD_LIMIT=1",
        "--env", "OPENBLAS_NUM_THREADS=1", "--env", "MKL_NUM_THREADS=1",
        "--env", "BLIS_NUM_THREADS=1", "--env", "NUMEXPR_NUM_THREADS=1",
        "--user", f"{os.getuid()}:{os.getgid()}", "--mount",
        f"type=bind,src={case},dst=/case", "--workdir", "/case", "--entrypoint", "/bin/bash",
        cfg["image"], "-c", flow,
    ]

def send_rank_signal(helper: Any, name: str, sig: int) -> dict[str, Any]:
    evidence = helper.handler_evidence(name)
    pids = sorted(int(row["pid"]) for row in evidence["solver_ranks"])
    if not evidence.get("all_rank_handlers_verified") or len(pids) != 20:
        return {"status": "refused_rank_identity_or_handler_check", "signal": sig, "evidence": evidence}
    sent, failed = [], []
    for pid in pids:
        try:
            os.kill(pid, sig)
            sent.append(pid)
        except (ProcessLookupError, PermissionError) as error:
            failed.append({"pid": pid, "error": str(error)})
    return {"status": "sent" if len(sent) == 20 and not failed else "partial", "signal": sig,
            "signal_name": "SIGUSR1/writeNow" if sig == signal.SIGUSR1 else "SIGUSR2/stopAtWriteNow",
            "pids": pids, "delivered_pids": sent, "errors": failed}

def save_tail(run: Path, scratch: Path, flow: Path, seq: int) -> None:
    if not flow.exists() or disk_free() < DISK_FLOOR or metadata_bytes(run) + 70_000 >= 50 * 1024**2:
        return
    with flow.open("rb") as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(max(0, size - 64 * 1024))
        data = f.read()
    path = run / "durable-log-tails" / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%fZ')}-{seq}.log-tail"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

def update_line(line: str, m: dict[str, Any], counters: dict[str, int]) -> str | None:
    def value(pattern: str):
        match = re.search(pattern, line)
        return float(match.group(1)) if match else None
    if any(word in line.lower() for word in ("nan", " inf", "infinity")) and any(
        label in line for label in ("deltaT", "Time =", "Courant Number", "Interface Courant", "bounding epsilon", "Phase-1 volume")
    ):
        return "nonfinite_solver_diagnostic"
    if line.startswith("deltaT ="):
        v = value(r"deltaT\s*=\s*([^\s]+)")
        m["delta_t_s"] = v
        counters["small_dt"] = counters["small_dt"] + 1 if v is not None and v < GUARD["dt_below_s"] else 0
        if v is None or v <= 0 or not math.isfinite(v): return "invalid_delta_t"
        if counters["small_dt"] >= GUARD["dt_low_steps"]: return "persistent_delta_t_collapse"
    elif line.startswith("Time ="):
        v = value(r"Time\s*=\s*([^\s]+)")
        if v is None or not math.isfinite(v): return "nonfinite_solver_time"
        prev = m.get("solver_time_s")
        m["solver_time_s"] = v
        if prev is None or v > prev:
            m["last_time_advance_monotonic"] = time.monotonic()
            m["same_time_lines"] = 0
        elif v == prev:
            m["same_time_lines"] = int(m.get("same_time_lines", 0)) + 1
        if v >= TARGET_TIME - 0.001 and not m.get("target_write_now_sent"):
            m["target_write_now_sent"] = True
            return "request_target_write_now"
    elif line.startswith("Courant Number mean:"):
        v = value(r"max\s+([^\s]+)")
        m["co_max"] = v
        counters["high_co"] = counters["high_co"] + 1 if v is not None and v > GUARD["co_max_above"] else 0
        if counters["high_co"] >= GUARD["co_high_steps"]: return "co_explosion"
    elif line.startswith("Interface Courant Number mean:"):
        v = value(r"max\s+([^\s]+)")
        m["interface_co_max"] = v
        counters["high_interface_co"] = counters["high_interface_co"] + 1 if v is not None and v > GUARD["interface_co_max_above"] else 0
        if counters["high_interface_co"] >= GUARD["interface_co_high_steps"]: return "interface_co_explosion"
    elif line.startswith("bounding epsilon,"):
        vals = re.findall(r"(?:min|max|average):\s*([^\s]+)", line)
        try: peak = max(abs(float(v)) for v in vals)
        except (ValueError, TypeError): return "nonfinite_epsilon_bound"
        m["epsilon_bound_abs_max"] = peak
        counters["epsilon_high"] = counters["epsilon_high"] + 1 if peak > GUARD["epsilon_abs_bound_above"] else 0
        if counters["epsilon_high"] >= GUARD["epsilon_high_steps"]: return "epsilon_bound_runaway"
    elif line.startswith("Phase-1 volume fraction"):
        lo = value(r"Min\(alpha\.water\)\s*=\s*([^\s]+)")
        hi = value(r"Max\(alpha\.water\)\s*=\s*([^\s]+)")
        m["post_bounded_alpha_min"] = lo; m["post_bounded_alpha_max"] = hi
        bad = lo is None or hi is None or lo < -GUARD["post_bounded_alpha_violation"] or hi > 1 + GUARD["post_bounded_alpha_violation"]
        counters["alpha_violation"] = counters["alpha_violation"] + 1 if bad else 0
        if counters["alpha_violation"] >= GUARD["alpha_violation_steps"]: return "gross_post_bounded_alpha_violation"
    return None

def run(run_dir: Path) -> int:
    cfg=json.loads((run_dir/'ram-run.json').read_text()); scratch=Path(cfg['scratch_dir']); case=Path(cfg['case'])
    name=cfg['container_name']; flow=scratch/'flow.log'; helper=load_helper(run_dir)
    monitor_log=(scratch/'checkpoint-monitor.log').open('ab',buffering=0)
    monitor=subprocess.Popen([sys.executable,str(run_dir/'ram_resume_supervisor.py'),'--run-dir',str(run_dir),'--monitor'],stdin=subprocess.DEVNULL,stdout=monitor_log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True); monitor_log.close()
    capture_log=(scratch/'native-ledger-capture.log').open('ab',buffering=0)
    capture=subprocess.Popen([sys.executable,str(run_dir/'capture_ram_ledgers.py'),'--run-dir',str(run_dir)],stdin=subprocess.DEVNULL,stdout=capture_log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True); capture_log.close()
    command=docker_cmd(run_dir,cfg)
    (run_dir/'docker-command.json').write_text(json.dumps({'command':command,'created_utc':utc(),'cpu_quota':cfg['cpu_quota_initial'],'mpi_ranks':20,'timeout_s':WALL_S},indent=2,sort_keys=True)+'\n')
    start=time.monotonic(); wall_deadline=start+WALL_S
    with flow.open('ab',buffering=0) as log:
        client=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
    write_json(run_dir/'worker-state.json',{'status':'docker_starting','run_id':run_dir.name,'manager_pid':os.getpid(),'docker_client_pid':client.pid,'monitor_pid':monitor.pid,'capture_pid':capture.pid,'cpu_quota':cfg['cpu_quota_initial'],'mpi_ranks':20,'started_utc':utc()})
    deadline=time.monotonic()+240
    evidence=None
    while time.monotonic()<deadline:
        if client.poll() is not None: break
        try:
            evidence=helper.handler_evidence(name)
            if evidence['all_rank_handlers_verified'] and evidence['solver_process_count']==20: break
        except Exception: pass
        time.sleep(2)
    if not evidence or not evidence.get('all_rank_handlers_verified'):
        write_json(run_dir/'signal-handler-failure.json',evidence or {'status':'no_container_process_evidence'})
        subprocess.run(['docker','stop','--time','60',name],capture_output=True,timeout=90,check=False)
        return 2
    write_json(run_dir/'signal-handler-verification.json',evidence)
    append_event(run_dir,scratch,{'status':'solver_startup_pass','mpi_ranks':20,'cpu_quota':cfg['cpu_quota_initial'],'solver_pids':[x['pid'] for x in evidence['solver_ranks']],'all_handlers_verified':True})
    offset=0; carry=''; metrics={'solver_time_s':None,'delta_t_s':None,'co_max':None,'interface_co_max':None,'epsilon_bound_abs_max':None,'post_bounded_alpha_min':None,'post_bounded_alpha_max':None,'same_time_lines':0,'target_write_now_sent':False}
    counters={'small_dt':0,'high_co':0,'high_interface_co':0,'epsilon_high':0,'alpha_violation':0}
    last_state=time.monotonic(); last_tail=time.monotonic(); last_heartbeat=time.monotonic(); stop_reason=None; stop_sent=False; stop_sent_at=None; target_sent=False
    while client.poll() is None:
        if monitor.poll() not in (None,0):
            stop_reason=f'checkpoint_monitor_exit_{monitor.returncode}'
        if capture.poll() not in (None,0):
            append_event(run_dir,scratch,{'status':'capture_watcher_exit','exit_code':capture.returncode})
        try:
            with flow.open('rb') as f:
                f.seek(offset); chunk=f.read(); offset=f.tell()
        except OSError: chunk=b''
        if chunk:
            parts=(carry+chunk.decode('utf-8',errors='replace')).split('\n'); carry=parts.pop()
            for line in parts:
                reason=update_line(line,metrics,counters)
                if reason=='request_target_write_now' and not target_sent:
                    sig=send_rank_signal(helper,name,signal.SIGUSR1); target_sent=True
                    append_event(run_dir,scratch,{'status':'target_write_now_request','threshold_time_s':TARGET_TIME,'observed_time_s':metrics['solver_time_s'],**sig})
                elif reason:
                    stop_reason=reason; metrics['trigger_line']=line[-400:]; break
                if metrics.get('solver_time_s') is not None and metrics.get('delta_t_s') is not None:
                    t=metrics['solver_time_s']; dt=metrics['delta_t_s']
                    if dt < 1e-9 and counters['small_dt'] >= 1:
                        # Values below one time ULP are the clear clock-stall signature.
                        if dt < math.ulp(t): counters['dt_below_ulp']=counters.get('dt_below_ulp',0)+1
                        else: counters['dt_below_ulp']=0
                    else: counters['dt_below_ulp']=0
                    if counters.get('dt_below_ulp',0)>=GUARD['dt_below_ulp_steps']:
                        stop_reason='delta_t_below_time_ulp'; break
        now=time.monotonic()
        if metrics.get('solver_time_s') is not None and now-metrics.get('last_time_advance_monotonic',start)>GUARD['no_time_line_progress_s']:
            stop_reason='solver_time_line_stalled_180s'
        usage=tree_bytes(scratch); available=mem_available(); disk=disk_free()
        if usage>=SCRATCH_LIMIT: stop_reason='scratch_budget'
        elif available<MEM_FLOOR: stop_reason='host_memavailable_floor'
        elif disk<DISK_FLOOR: stop_reason='root_disk_durability_floor'
        if now>=wall_deadline: stop_reason='wall_budget_3600s'
        if stop_reason and not stop_sent:
            sig=send_rank_signal(helper,name,signal.SIGUSR2)
            stop_sent=True; stop_sent_at=now
            append_event(run_dir,scratch,{'status':'safe_stop_signal_sent','reason':stop_reason,'latest_metrics':metrics,'counters':counters,'scratch_bytes':usage,'memavailable_bytes':available,'disk_free_bytes':disk,**sig})
        if stop_sent and stop_sent_at is not None and now-stop_sent_at>180 and client.poll() is None:
            append_event(run_dir,scratch,{'status':'graceful_stop_timeout_escalation','reason':stop_reason,'elapsed_after_sigusr2_s':now-stop_sent_at})
            subprocess.run(['docker','stop','--time','60',name],capture_output=True,timeout=90,check=False)
            stop_sent_at=now+1e9
        if now-last_state>=15:
            state=helper.inspect_container(name)
            write_json(run_dir/'pilot-live-state.json',{'utc':utc(),'status':'stopping' if stop_sent else 'running','container':state,'latest_solver_metrics':metrics,'threshold_counters':counters,'scratch_bytes':usage,'scratch_limit_bytes':SCRATCH_LIMIT,'host_memavailable_bytes':available,'root_disk_free_bytes':disk,'wall_elapsed_s':round(now-start,1),'stop_reason':stop_reason})
            last_state=now
        if now-last_tail>=300:
            save_tail(run_dir,scratch,flow,int(now-start)); last_tail=now
        if now-last_heartbeat>=300:
            append_event(run_dir,scratch,{'status':'resource_sample','container':helper.inspect_container(name),'solver_time_s':metrics['solver_time_s'],'delta_t_s':metrics['delta_t_s'],'epsilon_bound_abs_max':metrics['epsilon_bound_abs_max'],'scratch_bytes':usage,'host_memavailable_bytes':available,'disk_free_bytes':disk,'wall_elapsed_s':round(now-start,1)})
            last_heartbeat=now
        time.sleep(3)
    client_code=client.wait()
    write_json(run_dir/'pilot-live-state.json',{'utc':utc(),'status':'solver_client_exited','docker_client_exit_code':client_code,'container':helper.inspect_container(name),'latest_solver_metrics':metrics,'threshold_counters':counters,'scratch_bytes':tree_bytes(scratch),'host_memavailable_bytes':mem_available(),'root_disk_free_bytes':disk_free(),'wall_elapsed_s':round(time.monotonic()-start,1),'stop_reason':stop_reason})
    try: monitor_code=monitor.wait(timeout=1200)
    except subprocess.TimeoutExpired:
        monitor.terminate(); monitor_code=monitor.wait(timeout=30)
    try: capture_code=capture.wait(timeout=1200)
    except subprocess.TimeoutExpired:
        capture.terminate(); capture_code=capture.wait(timeout=30)
    append_event(run_dir,scratch,{'status':'pilot_finished','docker_exit_code':client_code,'monitor_exit_code':monitor_code,'capture_exit_code':capture_code,'stop_reason':stop_reason,'latest_metrics':metrics,'container':helper.inspect_container(name),'scratch_bytes':tree_bytes(scratch),'disk_free_bytes':disk_free()})
    return 0 if client_code==0 and monitor_code==0 else 1

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--run-dir',type=Path,required=True); args=parser.parse_args()
    return run(args.run_dir.resolve())

if __name__=='__main__':
    raise SystemExit(main())
