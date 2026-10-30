"""Matched-path drift, receiver checks, two-budget grids and compiled timings."""
import argparse,struct,time,os,platform,threading
from common import *
from experiments import require_kernels,MODES
from kernels import cumulative_energy,segment_stats,guard,power_extrema,energy_extrema,shape_minimum
from wire import *
from encoders import encode,measure_decoded,metrics_dict

def delta_wire(t,p,e,indices,feedback=False):
    sp,se=PROFILES['medium'];parts=[HEADER.pack(b'DFB8' if feedback else b'DNV8',float(t[0]),.5,sp,se)]
    previous=0.;previous_raw=0.
    for j,i in enumerate(indices):
        increment=float(e[i])-previous if feedback else float(e[i])-previous_raw
        count=max(0,round(increment/se));pc=round(float(p[i])/sp)
        blob=normal(j,tick(float(t[i]),float(t[0]),.5),pc,count)
        item,pos=decode_packet(blob,0,float(t[0]),.5,sp,se);assert pos==len(blob)
        previous+=item['energy'];previous_raw=float(e[i]);parts.append(blob)
    parts.append(footer(len(indices)-1,tick(float(t[indices[-1]]),float(t[0]),.5)))
    return b''.join(parts)

def decode_delta(blob):
    magic,origin,h,sp,se=HEADER.unpack_from(blob);assert magic in (b'DNV8',b'DFB8')
    pos=36;energy=0.;rows=[];packets=[];endmark=None
    while pos<len(blob):
        item,pos=decode_packet(blob,pos,origin,h,sp,se)
        if item['kind']==EOS:endmark=item;break
        assert item['kind']==NORMAL and item['seq']==len(rows)%65536
        energy+=item['energy'];item['energy']=energy
        packets.append(item);rows.append((len(rows),item['time'],item['power'],energy))
    assert pos==len(blob) and endmark is not None
    assert endmark['tick']==packets[-1]['tick'] and endmark['seq']==packets[-1]['seq']
    return dict(rows=np.asarray(rows),packets=packets,footer=endmark)

def drift():
    require_kernels();wires=joblib.load(DEV/'data/wires_full.joblib');rows=[]
    for r in scope_records('full'):
        t,p=r['t'],r['p'];e=cumulative_energy(t,p);key=(r['dataset'],r['flight_id'],'Strict','medium')
        if key not in wires:
            for method in ['DeltaNaiveSamePath','DeltaFeedbackSamePath','LinearSamePath']:
                rows.append(identity(r)|dict(method=method,status='MATCHED_STRICT_PATH_REFUSED'))
            continue
        reference=decode(wires[key]);indices=np.searchsorted(t,reference['rows'][:,1])
        for method,feedback in [('DeltaNaiveSamePath',False),('DeltaFeedbackSamePath',True)]:
            actual=delta_wire(t,p,e,indices,feedback);decoded=decode_delta(actual);m=measure_decoded(t,p,e,decoded)
            rows.append(identity(r)|dict(method=method,status='OK',duration_s=float(t[-1]-t[0]),encoded_bytes=len(actual),
                same_absolute_guarded_path=True,sender_guard_uses='absolute endpoints of the reference path; delta decoding is a post-hoc matched-path ablation',
                terminal_energy_error_Wh=float(decoded['rows'][-1,3]-e[-1]),**m))
        top=[0.,0.,np.inf,0.];jumps=0.
        for a,b,aa,bb in zip(indices[:-1],indices[1:],reference['rows'][:-1],reference['rows'][1:]):
            m=segment_stats(t,p,e,int(a),int(b),aa[2],bb[2],aa[3],bb[3],True)
            top=[max(top[0],m[0]),max(top[1],m[1]),min(top[2],m[2]),max(top[3],m[3])]
            jumps=max(jumps,abs(aa[3]+(bb[1]-aa[1])*(aa[2]+bb[2])/7200-bb[3]))
        rows.append(identity(r)|dict(method='LinearSamePath',status='OK',duration_s=float(t[-1]-t[0]),encoded_bytes=len(wires[key]),
            same_absolute_guarded_path=True,energy_reset_jump_Wh=jumps,passes=bool(guard(tuple(top))),**metrics_dict(top)))
    pd.DataFrame(rows).to_csv(DEV/'results/matched_path_drift.csv',index=False)
    write('results/drift_gate.json',dict(completed=True,inputs=len(scope_records('full')),rows=len(rows),
        note='Delta feedback is an adverse control: absolute fields are not uniquely necessary for low lossless drift; they support independent resynchronization.'))

def receiver():
    require_kernels();wires=joblib.load(DEV/'data/wires_120.joblib');rows=[];corruptions=[]
    for r in records():
        t,p=r['t'],r['p'];e=cumulative_energy(t,p);out=encode(t,p,profile='medium',escape_enabled=True)
        row=identity(r)|dict(status=out['status'])
        if out['status']!='OK':rows.append(row);continue
        d=out['decoded'];top=[0.,0.,np.inf,0.];audits=[];auditbytes=0
        for j,(aa,bb) in enumerate(zip(d['rows'][:-1],d['rows'][1:])):
            D=bb[1]-aa[1];c=3600*(bb[3]-aa[3])/D-(aa[2]+bb[2])/2
            linear=d['packets'][j+1]['kind']==ESCAPE
            c1=(bb[2]-aa[2]+(0 if linear else 6*c))/D;c2=0 if linear else -6*c/D**2
            candidates=[0.,D]
            if c2 and 0<-c1/(2*c2)<D:candidates.append(-c1/(2*c2))
            minimum=min(aa[2]+c1*x+c2*x*x for x in candidates)
            assert minimum>=-1e-8 and 0<D<=5+1e-10 and bb[3]>=aa[3]-1e-12
            top[2]=min(top[2],minimum);top[3]=max(top[3],D)
            if j%16==0:
                # A fixed midpoint raw knot, not the largest residual selected
                # after seeing the source. A separate optional audit datagram
                # has a real kind byte, uint64 tick and binary64 reference P.
                a=int(np.searchsorted(t,aa[1]));b=int(np.searchsorted(t,bb[1]));i=(a+b)//2
                packet=audit_sample(tick(float(t[i]),float(t[0]),.5),float(p[i]))
                ti,raw=decode_audit_sample(packet);x=ti*.5+t[0]-aa[1]
                audits.append(abs(aa[2]+c1*x+c2*x*x-raw));auditbytes+=len(packet)
        true=measure_decoded(t,p,e,d)['power_max_W'];lower=max(audits,default=0.)
        assert lower<=true+1e-7
        row.update(receiver_shape_checks=True,audit_samples=len(audits),audit_bytes=auditbytes,
            audit_lower_bound_W=lower,true_continuous_error_W=true,
            lower_to_true=lower/true if true>0 else 1.,minimum_power_W=top[2],maximum_duration_s=top[3])
        for bits in [16,32]:
            checked=encode(t,p,profile='medium',escape_enabled=True,crc=bits);assert checked['status']=='OK'
            # The different magic is included in the checksum. Payload fields
            # and footer are unchanged, so the measured overhead is exact.
            assert checked['wire'][36:-bits//8]==out['wire'][36:]
            row[f'crc{bits}_extra_bytes']=len(checked['wire'])-len(out['wire'])
            damaged=bytearray(checked['wire']);damaged[40]^=1
            try:decode(bytes(damaged));detected=False
            except Refusal as exc:detected=str(exc)=='CRC_MISMATCH'
            assert detected;corruptions.append(dict(dataset=r['dataset'],flight_id=r['flight_id'],bits=bits,detected=detected))
        rows.append(row)
    pd.DataFrame(rows).to_csv(DEV/'results/receiver_audit.csv',index=False)
    pd.DataFrame(corruptions).to_csv(DEV/'results/crc_single_bit_checks.csv',index=False)
    write('results/receiver_gate.json',dict(completed=True,inputs=len(rows),corruptions_checked=len(corruptions),
        local_checks='syntax/order/time/modulo/nonnegativity/duration/nondecreasing energy',
        sender_assertions='continuous P/E error relative to the prepared reference; sparse audit lower bounds do not certify the maximum',
        checksum='CRC detects accidental errors and does not authenticate a sender'))

def heatmap():
    require_kernels();rows=[]
    for n,r in enumerate(records()):
        for power in [12.5,25.,50.]:
            for area in [.0005,.001,.002]:
                for method,kw in [('Strict',dict()),('Escape',dict(escape_enabled=True))]:
                    start=time.perf_counter();out=encode(r['t'],r['p'],profile='medium',power=power,area=area,**kw)
                    dense=36+16*len(r['t']);okay=out['status']=='OK'
                    if okay:
                        # measure_decoded's default 25 W/1mWh flag is not a
                        # claim at another budget; compare its numeric maxima.
                        m=measure_decoded(r['t'],r['p'],cumulative_energy(r['t'],r['p']),out['decoded'])
                        assert m['power_max_W']<=power+1e-8 and m['energy_max_Wh']<=area+1e-12
                    rows.append(identity(r)|dict(method=method,power_budget_W=power,energy_budget_Wh=area,duration_s=float(r['t'][-1]-r['t'][0]),
                        status=out['status'],encoded_bytes=out['encoded_bytes'] if okay else np.nan,
                        effective_bytes=out['encoded_bytes'] if okay else dense+out['partial_emitted_bytes'],dense_bytes=dense,
                        elapsed_s=time.perf_counter()-start))
        if (n+1)%100==0:print('heatmap',n+1,flush=True)
    pd.DataFrame(rows).to_csv(DEV/'results/two_budget_heatmap.csv',index=False)
    write('results/heatmap_gate.json',dict(completed=True,inputs=718,cells=len(rows)))

def timings():
    require_kernels();import psutil,subprocess
    process=psutil.Process();allowed=process.cpu_affinity();process.cpu_affinity([allowed[0]])
    rows=[];data=records();sample=[data[i] for i in np.linspace(0,len(data)-1,24,dtype=int)]
    for r in sample:
        t,p=r['t'],r['p'];e=cumulative_energy(t,p);a=0;b=min(10,len(t)-1)
        args=(t,p,e,a,b,p[a],p[b],e[a],e[b])
        segment_stats(*args) # exclude JIT compilation explicitly
        components=[('power_guard',power_extrema,(t,p,a,b,p[a],p[b],e[a],e[b])),
            ('energy_guard',energy_extrema,args),('shape_guard',shape_minimum,(p[a],p[b],e[a],e[b],t[b]-t[a]))]
        for label,fn,par in components:
            fn(*par)
            for rep in range(7):
                start=time.perf_counter_ns()
                for _ in range(2000):fn(*par)
                rows.append(identity(r)|dict(component=label,repeat=rep,ns_per_call=(time.perf_counter_ns()-start)/2000))
        for linear in [False,True]:
            for rep in range(7):
                start=time.perf_counter_ns()
                for _ in range(2000):segment_stats(*args,linear)
                rows.append(identity(r)|dict(component='compiled_exact_linear' if linear else 'compiled_exact_quadratic',repeat=rep,ns_per_call=(time.perf_counter_ns()-start)/2000))
        for method,kw in MODES.items():
            encode(t,p,profile='medium',**kw)
            for rep in range(5):
                start=time.perf_counter_ns();out=encode(t,p,profile='medium',**kw)
                elapsed=time.perf_counter_ns()-start
                processed=int(np.searchsorted(t,out['encoder'].previous[0],side='right')) if out['encoder'].previous is not None else 0
                rows.append(identity(r)|dict(component='full_'+method,repeat=rep,ns_per_processed_sample=elapsed/max(1,processed),processed_samples=processed,attempted_samples=len(t),encoder_ns=elapsed,status=out['status']))
    pd.DataFrame(rows).to_csv(DEV/'results/compiled_timings.csv',index=False)
    hardware=platform.processor()
    if platform.system()=='Windows':
        info=subprocess.run(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name'],capture_output=True,text=True,check=True);hardware=info.stdout.strip()
    write('results/timing_gate.json',dict(completed=True,records=len(sample),warmup_excluded=True,cpu_affinity=process.cpu_affinity(),library_threads=1,
        hardware=hardware,platform=platform.platform(),rss_bytes=process.memory_info().rss,MCU='not measured; no verified Cortex-M emulator configured',
        complexity='B=floor(L/h); greedy at most 9 rounding candidates times O(B) guard work per sample; byte oracle O(N B^2) work and O(N) state, streaming horizon O(B^3) with bounded B+k+1 state'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['drift','receiver','heatmap','timings']);args=parser.parse_args()
    globals()[args.command]()
