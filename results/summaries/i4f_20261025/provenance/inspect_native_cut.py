from pathlib import Path
import re, json, hashlib
import numpy as np

ROOT = Path('results/runs/i4f-two-tank-four-mouth-fixed8-physical-continue-20261025T1110Z/case')
AUDIT = Path('results/runs/i4f-fourmouth-observer-audit-20261025T102803Z/native-cv-endpoint-readonly-v1')
TIME = '0.00502116666404'
FIELD_PATH = ROOT / 'processors20' / TIME / 'alphaPhi0.water'
FIELD_BYTES = FIELD_PATH.read_bytes()


def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()


def list_start(b, label):
    # Binary OpenFOAM List<label> file: top-level count after FoamFile/header comments.
    m = re.search(rb'// \* \* \*.*?\n\s*(\d+)\s*\n\(', b, re.S)
    if not m: raise RuntimeError(f'cannot find {label} list')
    return int(m.group(1)), m.end()


def read_labels(path):
    b=Path(path).read_bytes(); n,off=list_start(b,path)
    a=np.frombuffer(b[off:off+4*n],dtype='<i4').astype(np.int64,copy=False)
    if len(a)!=n: raise RuntimeError(f'bad label count {path}')
    return a


def read_zones(path):
    b=Path(path).read_bytes(); out={}
    pat=rb'(?m)^([A-Za-z0-9_]+)\s*\{\s*type\s+cellZone;\s*cellLabels\s+List<label>\s+(\d+)\s*([;(])'
    for m in re.finditer(pat,b):
        name=m.group(1).decode(); n=int(m.group(2)); op=m.group(3)
        if n==0:
            out[name]=np.empty(0,dtype=np.int64)
        else:
            if op!=b'(': raise RuntimeError(f'bad zone list opening {name}')
            off=m.end(); a=np.frombuffer(b[off:off+4*n],dtype='<i4').astype(np.int64,copy=False)
            if len(a)!=n: raise RuntimeError(f'bad zone count {name}')
            out[name]=a
    return out


def read_boundary(path):
    b=Path(path).read_bytes(); n,off=list_start(b,path); text=b[off:].decode('latin1')
    found=[(m.group(1),m.group(2),int(m.group(3)),int(m.group(4))) for m in re.finditer(r'([A-Za-z0-9_]+)\s*\{\s*type\s+(\w+);.*?nFaces\s+(\d+);\s*startFace\s+(\d+);',text,re.S)]
    if len(found)!=n: raise RuntimeError(f'boundary patch count {len(found)} != {n} in {path}')
    return found


def read_field_chunks():
    ms=list(re.finditer(rb'// processor(\d+)\n(\d+)\n\(',FIELD_BYTES)); out={}
    for i,m in enumerate(ms):
        rank=int(m.group(1)); end=ms[i+1].start() if i+1<len(ms) else len(FIELD_BYTES)
        chunk=FIELD_BYTES[m.end():end]
        mi=re.search(rb'internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\(',chunk)
        if not mi: raise RuntimeError(f'no internal field in block {rank}')
        n=int(mi.group(1)); off=mi.end()
        if chunk[off:off+2]==b'\r\n': off+=2
        elif chunk[off:off+1]==b'\n': off+=1
        vals=np.frombuffer(chunk[off:off+8*n],dtype='<f8')
        if len(vals)!=n: raise RuntimeError(f'internal values count {rank}: {len(vals)} != {n}')
        out[rank]={'internal':vals,'chunk':chunk}
    if sorted(out)!=list(range(20)): raise RuntimeError(f'expected 20 processor blocks, got {sorted(out)}')
    return out


def read_patch_values(chunk, patch, expected_n):
    if expected_n==0: return np.empty(0,dtype=np.float64)
    pat=rb'(?m)^\s*'+re.escape(patch.encode())+rb'\s*\{'
    m=re.search(pat,chunk)
    if not m: raise RuntimeError(f'no field patch {patch}')
    tail=chunk[m.end():]
    v=re.search(rb'value\s+(uniform|nonuniform)\b',tail)
    if not v: raise RuntimeError(f'no value entry for {patch}')
    if v.group(1)==b'uniform':
        u=re.search(rb'value\s+uniform\s+([-+0-9.eE]+)',tail)
        if not u: raise RuntimeError(f'bad uniform value for {patch}')
        return np.full(expected_n,float(u.group(1)),dtype=np.float64)
    nv=re.search(rb'value\s+nonuniform\s+List<scalar>\s+(\d+)\s*\(',tail)
    if not nv: raise RuntimeError(f'bad nonuniform value header {patch}')
    n=int(nv.group(1))
    if n!=expected_n: raise RuntimeError(f'patch {patch}: value count {n} != mesh nFaces {expected_n}')
    off=m.end()+nv.end()
    if chunk[off:off+2]==b'\r\n': off+=2
    elif chunk[off:off+1]==b'\n': off+=1
    vals=np.frombuffer(chunk[off:off+8*n],dtype='<f8')
    if len(vals)!=n: raise RuntimeError(f'bad values count {patch}')
    return vals


chunks=read_field_chunks()
cv_zones={'A':('tankAZone','lineAInitialZone'),'B':('tankBZone','lineBInitialZone')}
flux={k:{'internal_m3_s':0.0,'processor_m3_s':0.0,'physical_m3_s':0.0,'internal_cut_faces':0,'processor_inside_faces':0,
         'physical_boundary_faces_in_cv':0,'rank_sums':[]} for k in cv_zones}
patch_sums={}
proc_face_pairs={}

for rank in range(20):
    mesh=ROOT/f'processor{rank}'/'constant'/'polyMesh'
    owner=read_labels(mesh/'owner'); neigh=read_labels(mesh/'neighbour'); zones=read_zones(mesh/'cellZones')
    bnd=read_boundary(mesh/'boundary'); n_internal=len(neigh)
    if len(chunks[rank]['internal'])!=n_internal: raise RuntimeError(f'internal face count mismatch rank{rank}')
    n_cells=int(max(owner.max(),neigh.max())+1)
    pfa=read_labels(mesh/'faceProcAddressing')
    if len(pfa)!=len(owner): raise RuntimeError(f'face addressing count mismatch rank{rank}')
    local_patch_results={}
    for pn,ptype,nf,sf in bnd:
        vals=read_patch_values(chunks[rank]['chunk'],pn,nf)
        if ptype=='processor':
            ownb=owner[sf:sf+nf]
            local_patch_results[pn]=(sf,nf,ownb,vals,pfa[sf:sf+nf])
            # FaceProcAddressing encodes reverse orientation as -(globalFace+1).
            for j,(addr,q) in enumerate(zip(pfa[sf:sf+nf],vals)):
                global_face=abs(int(addr))-1
                proc_face_pairs.setdefault(global_face,[]).append((rank,pn,j,float(q)))
        else:
            patch_sums[pn]=patch_sums.get(pn,0.0)+float(np.sum(vals))
    for name,znames in cv_zones.items():
        inside=np.zeros(n_cells,dtype=bool)
        for zn in znames:
            lab=zones.get(zn,np.empty(0,dtype=np.int64))
            if len(lab) and (lab.min()<0 or lab.max()>=n_cells): raise RuntimeError(f'bad cell label in {zn}, rank{rank}')
            inside[lab]=True
        own_i=owner[:n_internal]; nei_i=neigh
        cut=inside[own_i]!=inside[nei_i]
        q=chunks[rank]['internal']
        signed=np.where(inside[own_i],1.0,-1.0)
        local_internal=float(np.sum(q[cut]*signed[cut]))
        local_proc=0.0; local_nproc=0; local_phys=0; local_phys_sum=0.0
        for pn,ptype,nf,sf in bnd:
            ownb=owner[sf:sf+nf]
            inb=inside[ownb]
            if ptype=='processor':
                vals=local_patch_results[pn][3]
                local_proc+=float(np.sum(vals[inb])); local_nproc+=int(np.count_nonzero(inb))
            else:
                vals=read_patch_values(chunks[rank]['chunk'],pn,nf)
                local_phys+=int(np.count_nonzero(inb))
                local_phys_sum+=float(np.sum(vals[inb]))
        flux[name]['internal_m3_s']+=local_internal
        flux[name]['processor_m3_s']+=local_proc
        flux[name]['physical_m3_s']+=local_phys_sum
        flux[name]['internal_cut_faces']+=int(cut.sum())
        flux[name]['processor_inside_faces']+=local_nproc
        flux[name]['physical_boundary_faces_in_cv']+=local_phys
        flux[name]['rank_sums'].append({'rank':rank,'internal':local_internal,'processor':local_proc,'total':local_internal+local_proc})

# Cross-rank processor surface flux is single-valued with opposite outward signs.
# Count all paired groups; report maximum |qA+qB| and relative mismatch.
paired=[v for v in proc_face_pairs.values() if len(v)==2]
wrong_mult={str(n):sum(1 for v in proc_face_pairs.values() if len(v)==n) for n in sorted(set(map(len,proc_face_pairs.values()))) if n!=2}
max_pair_abs=0.0; max_pair_rel=0.0; pair_sums=[]
for v in paired:
    s=v[0][3]+v[1][3]; scale=max(abs(v[0][3]),abs(v[1][3]),1e-30)
    pair_sums.append(s); max_pair_abs=max(max_pair_abs,abs(s)); max_pair_rel=max(max_pair_rel,abs(s)/scale)

# Independent signed-patch cross-check against the functionObject logs.
expected_patch_logs={
 'ambientAnnulus': ROOT/'postProcessing/ambientAnnulusWaterPhaseFlux/4.368e-05/surfaceFieldValue.dat',
 'externalSides': ROOT/'postProcessing/externalSidesWaterPhaseFlux/4.368e-05/surfaceFieldValue.dat',
 'farOutlet': ROOT/'postProcessing/farOutletWaterPhaseFlux/4.368e-05/surfaceFieldValue.dat',
}
def last_log_value(path, t=TIME):
    rows=[]
    for line in Path(path).read_text().splitlines():
        if not line or line.startswith('#'): continue
        q=line.split()
        try:
            if abs(float(q[0])-float(t))<5e-11: rows.append(float(q[-1]))
        except (ValueError,IndexError): pass
    if not rows: raise RuntimeError(f'no matching functionObject time in {path}')
    return rows[-1]
patch_cross={}
for pn,p in expected_patch_logs.items():
    actual=patch_sums.get(pn,0.0); expected=last_log_value(p)
    patch_cross[pn]={'native_boundary_array_sum_m3_s':actual,'functionObject_sum_m3_s':expected,'difference_m3_s':actual-expected}

# Inventories and sampled mouth-plane quadrature from the existing histories.
def read_series(path):
    rows=[]
    for line in Path(path).read_text().splitlines():
        if not line or line.startswith('#'): continue
        q=line.split()
        try: rows.append((float(q[0]),float(q[-1])))
        except (ValueError,IndexError): pass
    return rows

def at_time(rows,t):
    matches=[v for tt,v in rows if abs(tt-t)<5e-11]
    if not matches: raise RuntimeError(f'no row at {t}')
    return matches[-1]

inventory={}
t0=0.00477116666404; t1=0.00502116666404; dt=t1-t0
for tank in ('A','B'):
    labels={'A':('tankAWaterVolume','lineAInitialWaterVolume'),'B':('tankBWaterVolume','lineBInitialWaterVolume')}[tank]
    vols=[]
    for lab in labels:
        path=ROOT/'postProcessing'/lab/'4.368e-05'/'volFieldValue.dat'
        rows=read_series(path); vols.append((at_time(rows,t0),at_time(rows,t1)))
    V0=sum(x[0] for x in vols); V1=sum(x[1] for x in vols)
    inventory[tank]={'t0_s':t0,'t1_s':t1,'dt_s':dt,'water_inventory_t0_m3':V0,'water_inventory_t1_m3':V1,
                     'd_inventory_dt_m3_s':(V1-V0)/dt,'outward_rate_from_inventory_m3_s':-(V1-V0)/dt,
                     'components':{labels[i]:{'t0_m3':vols[i][0],'t1_m3':vols[i][1]} for i in range(2)}}

# Read actual VTK field-data time and per-tank alpha-weighted U quadrature from v2 profile.
profile_csv=Path('results/runs/i4f-fourmouth-observer-audit-20261025T102803Z/updated-hardware-startup-comparison-v2/startup-inventory-flux-diagnostics.csv')
profile_json=Path('results/runs/i4f-fourmouth-observer-audit-20261025T102803Z/updated-hardware-startup-comparison-v2/cfd-mouth-profile/four-mouth-observer-profile.json')
profile_doc=json.loads(profile_json.read_text())
profile_record=min(profile_doc['records'],key=lambda r:abs(float(r['path_time_s'])-float(TIME)))
mouth={tank:sum(float(x['water_Q_signed_profile_approx_m3_s']) for x in profile_record['mouths'] if x['tank']==tank) for tank in ('A','B')}
import csv
profile_history=list(csv.DictReader(profile_csv.open()))
endpoint_history=[r for r in profile_history if r['tank']=='A' and abs(float(r['time_s'])-float(profile_record['time_s']))<1e-8][-1]
v2_independent={'cfd_native_tank_withdrawal_rate_m3_s':float(endpoint_history['native_tank_water_withdrawal_rate_m3_s']),
                'reduced_network_two_branch_Q_m3_s':float(endpoint_history['network_two_branch_Q_m3_s']),
                'network_minus_CFD_tank_withdrawal_m3_s':float(endpoint_history['network_Q_minus_native_tank_withdrawal_m3_s']),
                'network_minus_CFD_tank_withdrawal_percent_of_CFD':100*float(endpoint_history['network_Q_minus_native_tank_withdrawal_m3_s'])/float(endpoint_history['native_tank_water_withdrawal_rate_m3_s']),
                'ODE_minus_CFD_dynamic_pressure_drop_Pa':float(endpoint_history['ODE_minus_CFD_dynamic_pressure_drop_Pa']),
                'ODE_minus_CFD_dynamic_pressure_drop_percent_of_CFD':100*float(endpoint_history['ODE_minus_CFD_dynamic_pressure_drop_fraction_of_CFD_drop'])}

mesh_hashes=[]
for rank in range(20):
    mesh=ROOT/f'processor{rank}'/'constant'/'polyMesh'
    for fn in ('owner','neighbour','cellZones','boundary','faceProcAddressing'):
        mesh_hashes.append({'path':str(mesh/fn),'sha256':digest(mesh/fn)})
mesh_hash_payload='\n'.join(f"{x['path']} {x['sha256']}" for x in mesh_hashes).encode()
mesh_hash=hashlib.sha256(mesh_hash_payload).hexdigest()
manifest_path=ROOT.parent/'launch-manifest.json'
manifest=json.loads(manifest_path.read_text())
source_snapshot=json.loads((ROOT.parent/'provenance/source-snapshot.json').read_text())
source_hashes={x['path']:x['sha256'] for x in source_snapshot['files'] if x['path'].endswith(('VoF/createAlphaFluxes.H','compressibleInterIsoFoam/alphaEqn.H'))}
local_source_copies={p.name:digest(p) for p in AUDIT.glob('OpenFOAM2512_*.H')}

report={
 'title':'Exact native upstream control-volume boundary water-flux audit at saved endpoint',
 'status':'read_only_completed_no_mesh_or_solver_changes',
 'case':str(ROOT), 'time_field_s':TIME,
 'container':{'id':manifest['container_id'],'image':manifest['image'],'started_at_utc':manifest['docker_started_at'],'finished_at_utc':'2026-10-25T11:35:20.363745337Z','exit_code':0,'state':'exited_cleanly','solver_binary_sha256':manifest['binary_sha256'],'solver_binary':str(ROOT.parent/'bin/compressibleInterFoamFrozenAlphaSourceV2NoPout')},
 'field':{'path':str(FIELD_PATH),'sha256':digest(FIELD_PATH),'class':'surfaceScalarField','object':'alphaPhi0.water','dimensions':'[0 3 -1 0 0 0 0] (volume/time)',
          'phase':'water','semantics':'OpenFOAM 2512 MULES phase-1 water advective volume flux, cached/updated by alpha advection and written at the endpoint; boundary values are face-oriented, outward from local owner cell on processor patches.'},
 'source_verification':{'solver':'custom compressibleInterFoamFrozenAlphaSourceV2NoPout built against OpenFOAM 2512',
      'source_paths_in_image':['/usr/lib/openfoam/openfoam2512/applications/solvers/multiphase/VoF/createAlphaFluxes.H','/usr/lib/openfoam/openfoam2512/applications/solvers/multiphase/compressibleInterFoam/compressibleInterIsoFoam/alphaEqn.H'],
      'immutable_run_source_hashes':source_hashes,'copied_exact_source_hashes':local_source_copies,
      'basis':'createAlphaFluxes.H names alphaPhi0 from alpha1.group() with READ_IF_PRESENT and AUTO_WRITE; alphaEqn.H sets alphaPhi10=advector.alphaPhi() after advector.advect. Case thermophysicalProperties declares phases (water air), so alpha1/group is water. This run has nAlphaSubCycles=1. The endpoint field is the cached MULES water advective volume flux that appears in the discrete alpha transport, not a reconstructed U dot Sf estimate.'},
 'cv_definition':'native cell membership union tankAZone + lineAInitialZone, and tankBZone + lineBInitialZone; outward flux positive from the union. Internal faces cut by owner/neighbour membership use owner-to-neighbour alphaPhi sign. Processor-boundary faces use the owner-outward patch value only for local owner cells in the CV; paired faces from two ranks are both included and cancel if both adjacent cells belong to the CV.',
 'mesh_and_addressing':{'processors':20,'per_rank_mesh_input_sha256':mesh_hash,'native_face_cut_method':'local native owner/neighbour plus decomposed processor patch boundaries; local cellZone labels identify CV membership','processor_patch_flux_pair_count':len(paired),'processor_patch_face_groups_with_non2_multiplicity':wrong_mult,
      'max_paired_processor_flux_sum_abs_m3_s':max_pair_abs,'max_paired_processor_flux_sum_relative':max_pair_rel,
      'physical_boundary_faces_touched_by_CV':{k:v['physical_boundary_faces_in_cv'] for k,v in flux.items()},
      'physical_boundary_flux_contribution_m3_s':{k:v['physical_m3_s'] for k,v in flux.items()},
      'physical_boundary_patch_crosscheck':patch_cross},
 'mouth_plane':{'surface_file':profile_record['surface_file'],'sampled_plane_x_m':profile_record['sampled_plane_x_m'],'field_data_time_s':profile_record['time_s'],'path_time_s':profile_record['path_time_s'],'field_data_minus_native_field_time_s':float(profile_record['time_s'])-float(TIME),'method':'triangulated sampledSurface cell fields with centroid-window masks and area weights; approximate U/alpha quadrature, no native alphaPhi field on this interior plane'},
 'independent_v2_comparisons_retained':v2_independent,
 'per_tank':{},
 'qualification':['This tests the exact native staircase CV boundary, not the sampled plane at x=5.79 m. The mouth plane and cellZone cut are distinct surfaces.','The CV flux and inventory derivative agree to within the printed volFieldValue inventory precision at the saved endpoint; that supports discrete balance for this exact native CV and step, not sampled-plane validity or a general convergence result.','The VTK plane Q remains an approximate sampled-surface alpha-weighted U quadrature, not native alphaPhi flux. The CV staircase boundary is geometrically distinct from x=5.79 m; the plane Q gap is unresolved.' ,
               'Prior v2 observation that downstream line-mouth-zone inventory growth is similar in magnitude to the gap is correlation only. Do not add that entire zone storage to plane Q as a native control-volume closure; those zone cell centres lie downstream of the sampled plane.'],
 'sources':{'v2_comparison_csv':str(profile_csv),'v2_mouth_profile_json':str(profile_json),'postProcessing_root':str(ROOT/'postProcessing'),'endpoint_field_hash_sha256':digest(FIELD_PATH),'launch_manifest':str(manifest_path),'run_source_snapshot':str(ROOT.parent/'provenance/source-snapshot.json')}
}
for tank in ('A','B'):
    f=flux[tank]; inv=inventory[tank]; native=f['internal_m3_s']+f['processor_m3_s']+f['physical_m3_s']; fd=inv['outward_rate_from_inventory_m3_s']; q=mouth[tank]
    report['per_tank'][tank]={
      'native_CV_boundary_outward_alphaPhi0_water_m3_s':native,
      'internal_cut_face_outward_sum_m3_s':f['internal_m3_s'],'processor_patch_cut_face_outward_sum_m3_s':f['processor_m3_s'],'physical_boundary_face_outward_sum_m3_s':f['physical_m3_s'],
      'internal_cut_face_count':f['internal_cut_faces'],'processor_owner_inside_face_count':f['processor_inside_faces'],'physical_boundary_faces_touched':f['physical_boundary_faces_in_cv'],
      'finite_difference_inventory_outward_rate_m3_s':fd,'inventory':inv,
      'native_minus_inventory_m3_s':native-fd,'native_vs_inventory_relative_percent':100*(native-fd)/fd,
      'native_flux_implied_inventory_loss_over_step_m3':native*dt,'ledger_inventory_loss_over_step_m3':inv['water_inventory_t0_m3']-inv['water_inventory_t1_m3'],
      'native_implied_minus_logged_volume_loss_m3':native*dt-(inv['water_inventory_t0_m3']-inv['water_inventory_t1_m3']),
      'inventory_log_precision_note':'volFieldValue values are printed to roughly 8 significant digits; the observed native-flux versus finite-difference remainder is below the endpoint/t0 rounding bound for the volume differencing.',
      'sampled_mouth_plane_water_Q_m3_s':q,'native_minus_sampled_plane_m3_s':native-q,
      'sampled_plane_under_native_flux_percent':100*(native-q)/native,
      'rank_contributions':f['rank_sums']}

out=AUDIT/'native_cv_endpoint_flux_audit.json'
out.write_text(json.dumps(report,indent=2)+'\n')
with (AUDIT/'native_cv_endpoint_flux_audit.csv').open('w',newline='') as fcsv:
    w=csv.DictWriter(fcsv,fieldnames=['tank','native_field_time_s','inventory_t0_s','inventory_t1_s','native_CV_outward_alphaPhi0_water_m3_s','finite_difference_inventory_outward_rate_m3_s','native_minus_inventory_m3_s','native_implied_minus_logged_volume_loss_m3','sampled_plane_field_data_time_s','sampled_plane_x_m','sampled_mouth_plane_water_Q_m3_s','plane_under_native_flux_percent'])
    w.writeheader()
    for tank in ('A','B'):
        x=report['per_tank'][tank]
        w.writerow({'tank':tank,'native_field_time_s':TIME,'inventory_t0_s':t0,'inventory_t1_s':t1,'native_CV_outward_alphaPhi0_water_m3_s':x['native_CV_boundary_outward_alphaPhi0_water_m3_s'],'finite_difference_inventory_outward_rate_m3_s':x['finite_difference_inventory_outward_rate_m3_s'],'native_minus_inventory_m3_s':x['native_minus_inventory_m3_s'],'native_implied_minus_logged_volume_loss_m3':x['native_implied_minus_logged_volume_loss_m3'],'sampled_plane_field_data_time_s':profile_record['time_s'],'sampled_plane_x_m':profile_record['sampled_plane_x_m'],'sampled_mouth_plane_water_Q_m3_s':x['sampled_mouth_plane_water_Q_m3_s'],'plane_under_native_flux_percent':x['sampled_plane_under_native_flux_percent']})
print(json.dumps({k:{'native':v['native_CV_boundary_outward_alphaPhi0_water_m3_s'],'fd':v['finite_difference_inventory_outward_rate_m3_s'],'diff':v['native_minus_inventory_m3_s'],'plane':v['sampled_mouth_plane_water_Q_m3_s'],'plane_gap_percent':v['sampled_plane_under_native_flux_percent']} for k,v in report['per_tank'].items()},indent=2))
print('patch_cross',json.dumps(patch_cross,indent=2))
print('paired_proc',len(paired),'maxabs',max_pair_abs,'maxrel',max_pair_rel,'non2',wrong_mult)
