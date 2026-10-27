#!/usr/bin/env python3
"""Losslessly archive and restore the three explicitly selected closed I4F logs."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/v/proj/bene/fire-track2')
BUNDLE = ROOT / 'results/runs/i4f-recent-closed-log-recovery-20261027T021433Z'
MANIFEST = BUNDLE / 'recovery-manifest.json'
TARGETS = [
    {
        'path': 'results/runs/i4f-cold-nouter16-advisory-20261026T2320Z/case/log.cold-coupled.retry006',
        'container_id': 'd0adc7e1e8e026b805876347f27edde59d39c1c15e9fb1ff3be269f003713032',
        'container_name': 'i4f-cold-nouter16-advisory-20261026T2320Z-retry006',
        'started_at': '2026-10-26T23:44:32.173495091Z', 'expected_bytes': 260325562,
    },
    {
        'path': 'results/runs/i4f-cold-pressure-advisory-continuation-20261026T2227Z/case/log.cold-coupled',
        'container_id': '87c69f24d16d1eb3ae3a79271c4c88516386fec2c130f98625e2bebc868c761c',
        'container_name': 'i4f-cold-pressure-advisory-continuation-20261026T2227Z-a003',
        'started_at': '2026-10-26T22:34:41.550545949Z', 'expected_bytes': 133519876,
    },
    {
        'path': 'results/runs/i4f-pressure-floor5k-20261027T005941Z/case/log.cold-coupled',
        'container_id': '71d34a2df7df1ade47e18ed17d431464a1b59c27f0364c46fcf5c7715ef4f793',
        'container_name': 'i4f-pressure-floor5k-20261027t005941z-a001',
        'started_at': '2026-10-27T01:15:56.671914021Z', 'expected_bytes': 150093315,
    },
    {
        'path': 'results/runs/i4f-cold-finite-water-eos-upwind-frozenSp-target050-20261026T181955Z/case/log.cold-coupled',
        'container_id': '0f8517608ad477044db5ab0b10dde34dabcbd81fad7accdfa7eb9965414f4fb9',
        'container_name': 'i4f-cold-upwind-frozen-sp-target050-20261026T181955Z',
        'started_at': '2026-10-26T18:26:13.097379609Z', 'expected_bytes': 317602945,
    },
    {
        'path': 'results/runs/i4f-cold-momentum-predictor-off-continuation-20261026T2048Z/case/log.cold-coupled',
        'container_id': 'f960b72b804919d8216462a2f4049a85f7abc3ab75a014067e93624b31c1af48',
        'container_name': 'i4f-cold-momentum-predictor-off-continuation-20261026T2048Z',
        'started_at': '2026-10-26T20:50:36.466720222Z', 'expected_bytes': 275491545,
    },
    {
        'path': 'results/runs/i4f-cold-momentum-predictor-off-20261026T2022Z/case/log.cold-coupled',
        'container_id': '8b086b299aee6b71b8a4826ab110db0989d8e92ca10ca142ee7acede0da551d5',
        'container_name': 'i4f-cold-momentum-predictor-off-20261026T2022Z',
        'started_at': '2026-10-26T20:24:41.025680559Z', 'expected_bytes': 275491545,
    },
    {
        'path': 'results/runs/i4f-upwind-momentum-warm-20261026T130013Z/case/log.cold-coupled',
        'container_id': '400939f169cc9bfd90f8f24461905255e6644871fec51abb0282a5ae04994f87',
        'container_name': 'i4f-upwind-momentum-warm-20261026T130013Z',
        'started_at': '2026-10-26T14:44:50.083120753Z', 'expected_bytes': 163247455,
    },
    {
        'path': 'results/runs/i4f-stock-cold-299248-stage01-20261026T023352Z/case/log.cold-coupled',
        'container_id': 'de0e6503a0f3e567fca1185ef45e8395b2cd925f212ca1e9f2807dbc561f2e0e',
        'container_name': 'i4f-stock-cold-299248-stage01-20261026T023352Z',
        'started_at': '2026-10-26T02:33:56.411557366Z', 'expected_bytes': 114677302,
    },
    {
        'path': 'results/runs/i4f-finite-water-eos-halfdt-conditional-20261026T122804Z/case/log.cold-coupled',
        'container_id': '13324c8bdc8489ffe9c9fa8e058bb8a9105507a253b3a2b375aa1ed081656057',
        'container_name': 'i4f-finite-water-eos-halfdt-conditional-20261026T122804Z-pilot',
        'started_at': '2026-10-26T12:37:58.261453121Z', 'expected_bytes': 97579047,
    },
    {
        'path': 'results/runs/i4f-stock-cold-299248-stage03-20261026T054311Z/case/log.cold-coupled',
        'container_id': '7a4508c7f1fea53336140ed3c763ac79d7ddff01d27fda62934ea7e3f986c249',
        'container_name': 'i4f-stock-cold-299248-stage03-20261026T054311Z',
        'started_at': '2026-10-26T05:43:15.899063019Z', 'expected_bytes': 95546642,
    },
]
CHUNK = 1 << 20

def utc(): return datetime.now(timezone.utc).isoformat()
def sha_stream(stream):
    h = hashlib.sha256(); n = 0
    while True:
        b = stream.read(CHUNK)
        if not b: break
        h.update(b); n += len(b)
    return h.hexdigest(), n
def sha_file(path):
    with path.open('rb') as f: return sha_stream(f)
def identity(path):
    s = path.stat()
    return {'device': s.st_dev, 'inode': s.st_ino, 'size_bytes': s.st_size, 'mtime_ns': s.st_mtime_ns, 'mode': s.st_mode}
def docker_state(t):
    raw = subprocess.run(['docker','inspect','--type','container',t['container_id']], check=True, capture_output=True, text=True, timeout=30)
    rows = json.loads(raw.stdout)
    if len(rows) != 1: raise RuntimeError('Docker identity not unique')
    row = rows[0]; st = row['State']
    actual = (row['Id'], row['Name'].lstrip('/'), st.get('StartedAt'))
    expected = (t['container_id'], t['container_name'], t['started_at'])
    if actual != expected or st.get('Status') not in {'exited','dead'} or st.get('Running') or st.get('Paused') or st.get('ExitCode') != 0:
        raise RuntimeError(f'container not exact successful terminal identity: {actual!r}, {st.get("Status")}, exit={st.get("ExitCode")}')
    return {'id': row['Id'], 'name': row['Name'].lstrip('/'), 'started_at': st['StartedAt'], 'finished_at': st.get('FinishedAt'), 'status': st.get('Status'), 'exit_code': st.get('ExitCode'), 'oom_killed': st.get('OOMKilled')}
def check_no_active_mount(path):
    ids = set()
    for status in ('running','paused'):
        out = subprocess.run(['docker','ps','-aq','--filter',f'status={status}'], check=True, capture_output=True, text=True, timeout=30).stdout
        ids.update(out.split())
    for cid in sorted(ids):
        row = json.loads(subprocess.run(['docker','inspect',cid], check=True, capture_output=True, text=True, timeout=30).stdout)[0]
        for m in row.get('Mounts', []):
            if not m.get('RW') or not m.get('Source'): continue
            source = Path(m['Source']).resolve()
            target = path.resolve()
            if target == source or target.is_relative_to(source) or source.is_relative_to(target):
                raise RuntimeError(f'active RW Docker mount overlaps source: {cid[:12]} {source}')
def check_no_open_fd(path):
    p = subprocess.run(['lsof','-nP','-t','--',str(path)], capture_output=True, text=True, timeout=30)
    if p.returncode not in (0,1): raise RuntimeError(f'lsof uncertain rc={p.returncode}: {p.stderr.strip()}')
    if p.stdout.strip(): raise RuntimeError(f'open file descriptors on source: {p.stdout.strip()}')
def referenced_by_existing_archive(rel):
    needles = (rel, str((ROOT / rel).resolve()))
    paths = [ROOT / 'results/archives/index.json']
    paths.extend((ROOT / 'results/archives/manifests').rglob('*'))
    for p in paths:
        if not p.is_file() or p == MANIFEST or p.suffix.lower() not in {'.json','.jsonl','.txt'}: continue
        try: body = p.read_text(errors='replace')
        except OSError: continue
        if any(needle in body for needle in needles): return str(p)
    return None
def durable_manifest(data):
    tmp = MANIFEST.with_suffix('.json.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, sort_keys=True, indent=2, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, MANIFEST)
    fd = os.open(MANIFEST.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)
def decompressed_digest(archive):
    proc = subprocess.Popen(['zstd','-q','-d','-c','-T1',str(archive)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    h = hashlib.sha256(); n = 0
    while True:
        block = proc.stdout.read(CHUNK)
        if not block: break
        h.update(block); n += len(block)
    err = proc.stderr.read() if proc.stderr else b''
    rc = proc.wait(timeout=300)
    if rc: raise RuntimeError(f'zstd decompression/verification failed rc={rc}: {err[:300]!r}')
    return h.hexdigest(), n
def archive_one(i, data):
    t = TARGETS[i]; source = ROOT / t['path']
    prior = referenced_by_existing_archive(t['path'])
    if prior: raise RuntimeError(f'source already referenced by existing restore record: {prior}')
    if not source.is_file(): raise RuntimeError(f'missing exact source: {t["path"]}')
    before = identity(source)
    if before['size_bytes'] != t['expected_bytes']: raise RuntimeError(f'wrong source size {before["size_bytes"]}')
    terminal = docker_state(t); check_no_active_mount(source); check_no_open_fd(source)
    source_hash, source_size = sha_file(source)
    after_hash_id = identity(source)
    if before != after_hash_id or source_size != t['expected_bytes']: raise RuntimeError('source changed during initial checksum')
    dest_rel = f'archive/{i+1:02d}-{Path(t["path"]).name}.zst'
    archive = BUNDLE / dest_rel; tmp = archive.with_suffix(archive.suffix + '.partial')
    cp = subprocess.run(['zstd','-q','-1','-T1','--no-progress','-f','-o',str(tmp),str(source)], capture_output=True, text=True, timeout=600)
    if cp.returncode: raise RuntimeError(f'zstd compression failed rc={cp.returncode}: {cp.stderr[-300:]}')
    with tmp.open('rb') as f: os.fsync(f.fileno())
    os.replace(tmp, archive)
    dfd = os.open(archive.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(dfd)
    finally: os.close(dfd)
    archive_sha, archive_size = sha_file(archive)
    restored_sha, restored_size = decompressed_digest(archive)
    if (restored_sha, restored_size) != (source_hash, source_size): raise RuntimeError('full decompression SHA256/size mismatch; source preserved')
    record = {
      'source_path': t['path'], 'source_absolute_path': str(source), 'source_metadata': before,
      'source_sha256': source_hash, 'source_bytes': source_size,
      'container': terminal, 'archive_path': dest_rel, 'archive_bytes': archive_size,
      'archive_sha256': archive_sha, 'decompressed_sha256': restored_sha,
      'decompressed_bytes': restored_size, 'verified_utc': utc(), 'source_removed': False,
    }
    data['records'].append(record); durable_manifest(data)
    # Last-moment deletion gate: exact successful terminal container, unchanged bytes/identity, no reader or active writer mount.
    if docker_state(t) != terminal: raise RuntimeError('container identity/state changed after durable manifest; source preserved')
    check_no_active_mount(source); check_no_open_fd(source)
    if identity(source) != before or sha_file(source) != (source_hash, source_size): raise RuntimeError('source changed after durable manifest; source preserved')
    source.unlink()
    pfd = os.open(source.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(pfd)
    finally: os.close(pfd)
    record['source_removed'] = True; record['removed_utc'] = utc(); durable_manifest(data)
    return record

def restore_all():
    data = json.loads(MANIFEST.read_text())
    for r in data['records']:
        destination = ROOT / r['source_path']
        if destination.exists(): raise RuntimeError(f'refusing to overwrite existing destination: {r["source_path"]}')
        archive = BUNDLE / r['archive_path']
        sha, size = decompressed_digest(archive)
        if (sha,size) != (r['source_sha256'],r['source_bytes']): raise RuntimeError('archive verification failed during restore')
        tmp = destination.with_name(destination.name + '.restore.tmp')
        tmp.parent.mkdir(parents=True,exist_ok=True)
        p = subprocess.run(['zstd','-q','-d','-c','-T1',str(archive)], stdout=tmp.open('wb'), stderr=subprocess.PIPE, timeout=600)
        if p.returncode: tmp.unlink(missing_ok=True); raise RuntimeError(f'restore decompression failed: {p.stderr[-300:]!r}')
        with tmp.open('rb') as f: os.fsync(f.fileno())
        if sha_file(tmp) != (r['source_sha256'],r['source_bytes']): tmp.unlink(missing_ok=True); raise RuntimeError('restored output mismatch')
        os.replace(tmp,destination)
        fd=os.open(destination.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
        try: os.fsync(fd)
        finally: os.close(fd)
        print(json.dumps({'restored':r['source_path'],'bytes':r['source_bytes']}))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--only',type=int,help='zero-based target index'); ap.add_argument('--restore-all',action='store_true'); a=ap.parse_args()
    if a.restore_all: restore_all(); return
    if MANIFEST.exists(): data=json.loads(MANIFEST.read_text())
    else: data={'schema':'i4f-recent-closed-log-recovery/v1','created_utc':utc(),'scope':'Lossless zstd-1 archives of explicitly selected terminal raw I4F solver logs.','bundle':str(BUNDLE.relative_to(ROOT)),'restore_command':f'python3 {BUNDLE.relative_to(ROOT)}/recover_logs.py --restore-all','records':[]}
    done={r['source_path'] for r in data['records']}
    indexes=[a.only] if a.only is not None else range(len(TARGETS))
    for i in indexes:
        if not 0 <= i < len(TARGETS): raise RuntimeError('target index out of range')
        if TARGETS[i]['path'] in done: continue
        r=archive_one(i,data)
        print(json.dumps({'archived':r['source_path'],'source_bytes':r['source_bytes'],'archive_bytes':r['archive_bytes'],'sha256':r['source_sha256'],'free_bytes':os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize},separators=(',',':')),flush=True)
if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(f'RECOVERY STOPPED: {type(exc).__name__}: {exc}',file=sys.stderr); raise
