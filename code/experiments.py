"""New-wire support/rounding/escape and complete-horizon byte-oracle experiments."""
import argparse,hashlib,time
import numpy as np,pandas as pd,joblib
from common import *
from kernels import cumulative_energy,canonical_nodes,byte_oracle,guard
from encoders import encode,measure_decoded,path_wire
from wire import PROFILES,decode,HEADER
from baselines_v8 import neutral_area_wire

MODES={'Strict':dict(search=False,escape_enabled=False),'Search':dict(search=True,escape_enabled=False),
       'Escape':dict(search=False,escape_enabled=True),'SearchEscape':dict(search=True,escape_enabled=True)}

def signature():
    names=['common.py','kernels.py','wire.py','encoders.py','baselines_v8.py','experiments.py']
    return hashlib.sha256(b''.join((DEV/'code'/name).read_bytes() for name in names)).hexdigest()

def require_kernels():
    step0();p=DEV/'audit/kernel_validation.json'
    assert p.exists() and json.loads(p.read_text())['passed'],'Validate compiled continuous guards and wire fixtures first'

def row_result(r,t,p,e,result,scope,profile,method,elapsed):
    dense=36+16*len(t);okay=result['status']=='OK'
    row=identity(r)|dict(scope=scope,profile=profile,method=method,status=result['status'],samples=len(t),duration_s=float(t[-1]-t[0]),dense_bytes=dense,
        encoded_bytes=result['encoded_bytes'] if okay else np.nan,partial_bytes=0 if okay else result['partial_emitted_bytes'],
        effective_bytes=result['encoded_bytes'] if okay else result['partial_emitted_bytes']+dense,
        dense_fallback_bytes=0 if okay else dense,checkpoints=result['checkpoints'],segments=result['segments'],
        escape_segments=result['escape_segments'],record_uses_escape=result['escape_segments']>0,max_buffer=result['max_buffer'],release_s=result['release_s'],
        guard_calls=result['guard_calls'],rounding_altered_segments=result['rounding_altered_segments'],elapsed_s=elapsed)
    failure=result['encoder'].first_failure
    if failure is not None:
        for k,v in failure.items():row['first_'+k]=json.dumps(v) if isinstance(v,list) else v
    elif not okay:
        reason=str(result['status'])
        row['first_first']='clock' if any(s in reason for s in ['CLOCK','TIME']) else 'overflow' if any(s in reason for s in ['OVERFLOW','COUNT','INTEGER']) else 'power' if 'INITIAL_POWER' in reason else 'unclassified'
        row['first_all']=json.dumps([reason])
    if okay:
        m=measure_decoded(t,p,e,result['decoded']);assert m['passes'],(identity(r),method,m)
        row.update(m);row['byte_ratio']=len(result['wire'])/dense;row['effective_byte_ratio']=len(result['wire'])/dense
        row['header_fraction']=36/len(result['wire']);row['footer_bytes']=len(result['decoded']['footer']['blob'])
        rows=result['decoded']['rows'];idx=np.searchsorted(t,rows[:,1])
        kinds=[v['kind'] for v in result['decoded']['packets']] if result['escape_segments'] else None
        neutral=neutral_area_wire(t,idx,rows[:,2],rows[:,3],kinds)
        row['neutral_bytes']=len(neutral);row['neutral_effective_bytes']=len(neutral);row['neutral_effective_byte_ratio']=len(neutral)/dense
    else:
        row['effective_byte_ratio']=row['effective_bytes']/dense
        from wire import decode_packet,EOS
        blob=result['wire'];pos=36;points=[]
        if len(blob)>=36:
            _,origin,h,sp,se=HEADER.unpack_from(blob)
            while pos<len(blob):
                item,pos=decode_packet(blob,pos,origin,h,sp,se)
                if item['kind']==EOS:break
                points.append(item)
        if points:
            ids=np.array([int(round((q['time']-t[0])/.5)) for q in points]);kinds=[q['kind'] for q in points] if any(q['kind']==1 for q in points) else None
            partial_neutral=len(neutral_area_wire(t,ids,[q['power'] for q in points],[q['energy'] for q in points],kinds))
        else:partial_neutral=0
        row['neutral_effective_bytes']=partial_neutral+dense;row['neutral_effective_byte_ratio']=(partial_neutral+dense)/dense
    return row

def main(scope):
    require_kernels();population=scope_records(scope);base=DEV/f'data/checkpoints_{scope}';base.mkdir(parents=True,exist_ok=True)
    rows=[];wires={};start=time.perf_counter();stamp=signature()
    for n,r in enumerate(population):
        name=hashlib.sha256((r['dataset']+'|'+str(r['flight_id'])).encode()).hexdigest()[:20];path=base/(name+'.joblib')
        if path.exists():
            saved=joblib.load(path);assert saved['signature']==stamp,'Changed numerical code: archive affected checkpoint scope before replay'
            rows.extend(saved['rows']);wires.update(saved['wires']);continue
        t,p=r['t'],r['p'];e=cumulative_energy(t,p);local=[];stored={}
        for profile in PROFILES:
            for method,kw in MODES.items():
                tick=time.perf_counter();out=encode(t,p,profile=profile,**kw)
                row=row_result(r,t,p,e,out,scope,profile,method,time.perf_counter()-tick);local.append(row)
                if out['status']=='OK':stored[(r['dataset'],r['flight_id'],method,profile)]=out['wire']
        for horizon in [2,4]:
            for esc in [False,True]:
                method=f'Horizon{horizon}'+('Escape' if esc else '')
                tick=time.perf_counter();out=encode(t,p,profile='medium',horizon=horizon,escape_enabled=esc)
                row=row_result(r,t,p,e,out,scope,'medium',method,time.perf_counter()-tick);local.append(row)
                if out['status']=='OK':stored[(r['dataset'],r['flight_id'],method,'medium')]=out['wire']
        nodes,cost=canonical_nodes(t,p,e,.1,1e-6)
        tick=time.perf_counter();indices,objective=byte_oracle(t,p,e,nodes,cost)
        row=identity(r)|dict(scope=scope,profile='medium',method='ByteOracle',status='NO_FIXED_NODE_PATH',samples=len(t),duration_s=float(t[-1]-t[0]),dense_bytes=36+16*len(t),elapsed_s=time.perf_counter()-tick)
        if len(indices):
            wire=path_wire(t,p,e,indices);decoded=decode(wire);m=measure_decoded(t,p,e,decoded)
            assert m['passes'];assert len(wire)==36+int(objective)+len(decoded['footer']['blob'])
            row.update(status='OK',encoded_bytes=len(wire),effective_bytes=len(wire),partial_bytes=0,byte_ratio=len(wire)/row['dense_bytes'],effective_byte_ratio=len(wire)/row['dense_bytes'],checkpoints=len(indices),**m)
            stored[(r['dataset'],r['flight_id'],'ByteOracle','medium')]=wire
        else:row.update(effective_bytes=row['dense_bytes'],effective_byte_ratio=1.,partial_bytes=0)
        local.append(row);dump_atomic(dict(rows=local,wires=stored,signature=stamp),path);rows.extend(local);wires.update(stored)
        if (n+1)%50==0:print(scope,n+1,'of',len(population),'seconds',round(time.perf_counter()-start,1),flush=True)
    pd.DataFrame(rows).to_csv(DEV/f'results/main_{scope}.csv',index=False);joblib.dump(wires,DEV/f'data/wires_{scope}.joblib',compress=3)
    write(f'results/main_{scope}_gate.json',dict(completed=True,inputs=len(population),attempts=len(rows),actual_wires=len(wires),seconds=time.perf_counter()-start))

def baselines():
    require_kernels()
    from baselines_v8 import linear_control,zfp_control,zstd_control,sz3_control,native_area,energy_aware
    population=records();rows=[];wires={};start=time.perf_counter();base=DEV/'data/baseline_checkpoints';base.mkdir(exist_ok=True);stamp=signature()
    for n,r in enumerate(population):
        name=hashlib.sha256((r['dataset']+'|'+str(r['flight_id'])).encode()).hexdigest()[:20];path=base/(name+'.joblib')
        if path.exists():
            saved=joblib.load(path);assert saved['signature']==stamp,'Changed numerical code: archive baseline checkpoints before replay'
            rows.extend(saved['rows']);wires.update(saved['wires']);continue
        t,p=r['t'],r['p'];e=cumulative_energy(t,p);local=[];stored={}
        methods={}
        for label in ['Swing','SlideCore','DPvertical']:
            methods[label]=lambda label=label:linear_control(t,p,e,label,False)
            methods[label+'Iso']=lambda label=label:linear_control(t,p,e,label,True)
        methods.update(ZFP=lambda:zfp_control(t,p,e,False),ZFPIso=lambda:zfp_control(t,p,e,True),zstd=lambda:zstd_control(t,p,e),
            SZ3=lambda:sz3_control(t,p,e),Native32=lambda:native_area(t,p,e),
            SwingEnergy=lambda:energy_aware(t,p,e,'swing'),SlideEnergy=lambda:energy_aware(t,p,e,'slide'),LinearResetGuarded=lambda:energy_aware(t,p,e,'raw',True))
        for method,fn in methods.items():
            tick=time.perf_counter()
            try:out=fn()
            except ImportError as error:out=dict(status='NOT_RUN_LIBRARY_UNAVAILABLE',reason=str(error))
            row=identity(r)|dict(method=method,scope='120',samples=len(t),duration_s=float(t[-1]-t[0]),dense_bytes=36+16*len(t),elapsed_s=time.perf_counter()-tick)
            for key,value in out.items():
                if key in ['wire','neutral_wire','spans','indices','rows','failed_metrics']:continue
                row[key]=value
            good=out['status']=='OK' and out['passes']
            row['guard_complete']=good
            row['effective_bytes']=out['encoded_bytes'] if good else row['dense_bytes']
            row['effective_byte_ratio']=row['effective_bytes']/row['dense_bytes']
            row['neutral_effective_bytes']=out['neutral_bytes'] if good else row['dense_bytes']
            row['neutral_effective_byte_ratio']=row['neutral_effective_bytes']/row['dense_bytes']
            if out['status']=='OK':
                row['byte_ratio']=out['encoded_bytes']/row['dense_bytes'];stored[(r['dataset'],r['flight_id'],method)]=out['wire']
            local.append(row)
        dump_atomic(dict(rows=local,wires=stored,signature=stamp),path);rows.extend(local);wires.update(stored)
        if (n+1)%25==0:print('baselines',n+1,'of',len(population),'seconds',round(time.perf_counter()-start,1),flush=True)
    pd.DataFrame(rows).to_csv(DEV/'results/baselines.csv',index=False);joblib.dump(wires,DEV/'data/baseline_wires.joblib',compress=3)
    write('results/baselines_gate.json',dict(completed=True,inputs=len(population),attempts=len(rows),actual_wires=len(wires),seconds=time.perf_counter()-start,iso_scope='718 original 120s benchmark records; finite operational parameter catalogues, not arbitrary real tolerances'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('experiment',choices=['120','full','baselines']);args=p.parse_args()
    baselines() if args.experiment=='baselines' else main(args.experiment)
