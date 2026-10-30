"""Independent v7 comparison and wire fixtures, gated after isolated Step 0."""
import importlib.util,time,struct
import numpy as np
from common import *
from kernels import *
from wire import *
from encoders import encode,measure_decoded

def run():
    step0();start=time.perf_counter();rng=np.random.default_rng(SEED)
    spec=importlib.util.spec_from_file_location('retained_v7_core',ROOT/'development_v7/code/core.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    population=records();maximum=np.zeros(3);matches=0
    for case in range(1200):
        r=population[int(rng.integers(len(population)))];t,p=r['t'],r['p'];e=cumulative_energy(t,p)
        assert np.allclose(e,old.energy(t,p),atol=1e-12,rtol=1e-13)
        a=int(rng.integers(len(t)-1));b=min(len(t)-1,a+int(rng.integers(1,11)))
        profile=list(PROFILES)[case%3];sp,se=PROFILES[profile]
        pa=round(p[a]/sp)*sp;pb=round(p[b]/sp)*sp;ea=round(e[a]/se)*se;eb=round(e[b]/se)*se
        current=segment_stats(t,p,e,a,b,pa,pb,ea,eb)
        separate=(power_extrema(t,p,a,b,pa,pb,ea,eb),energy_extrema(t,p,e,a,b,pa,pb,ea,eb),shape_minimum(pa,pb,ea,eb,t[b]-t[a]))
        assert np.allclose(current[:3],separate,atol=2e-8,rtol=1e-10)
        previous=old.extrema(t[a:b+1],p[a:b+1],e[a:b+1],(0,t[a],pa,ea),(1,t[b],pb,eb))
        values=np.array([previous['power_max_W'],previous['energy_max_Wh'],previous['minimum_power_W']])
        maximum=np.maximum(maximum,abs(np.asarray(current[:3])-values))
        assert np.allclose(current[:3],values,atol=2e-8,rtol=1e-10)
        assert bool(guard(current))==old.passes(previous);matches+=1
    malformed=0
    for blob in [b'\x80\x00',b'\x81'*10+b'\x00',b'\xff'*9+b'\x02',b'\x80',b'']:
        try:read_uleb(blob,0)
        except Refusal:malformed+=1
        else:raise AssertionError('Malformed ULEB accepted')
    for n in [0,127,128,2**32,2**63,2**64-1]:
        buf=uleb(n);value,pos=read_uleb(buf,0);assert value==n and pos==len(buf)
    assert decode_audit_sample(audit_sample(120,0.25))==(120,0.25) and len(audit_sample(120,0.25))==17
    # This constructed coarse pair really activates the failure/escape/search
    # branches: nearest rounded endpoints create a negative quadratic interior.
    tt=np.array([0.,.5]);pp=np.array([0.,.51]);ee=cumulative_energy(tt,pp)
    strict=encode(tt,pp,profile='coarse');assert strict['status']!='OK'
    assert strict['first_failure']['first']=='nonnegativity'
    rescued=encode(tt,pp,profile='coarse',escape_enabled=True);assert rescued['status']=='OK' and rescued['escape_segments']==1
    assert measure_decoded(tt,pp,ee,rescued['decoded'])['passes']
    searched=encode(tt,pp,profile='coarse',search=True);assert searched['status']=='OK' and searched['rounding_altered_segments']>0
    tt=np.arange(0.,2.5,.5);pp=np.array([0.,.51,3.,2.,1.]);continued=encode(tt,pp,profile='coarse',escape_enabled=True)
    assert continued['status']=='OK' and continued['escape_segments']>=1
    assert measure_decoded(tt,pp,cumulative_energy(tt,pp),continued['decoded'])['passes']
    escape_fixture=dict(strict_status=strict['status'],escape_segments=rescued['escape_segments'],search_changed=searched['rounding_altered_segments'],continued_segments=continued['segments'],constructed_not_observed=True)
    # Decode/recode controls must reproduce the exact float bits and preserve
    # method-specific segment boundaries, including disjoint linear spans.
    from baselines_v8 import neutral_area_wire
    fixture=neutral_area_wire(np.arange(3)*.5,np.arange(3),[100.,100.05,0.],[0.,.01,.02],[0,0,1])
    assert fixture[:4]==b'UMX8'
    # Explicit transport fixtures wrap sequence independently of greedy segment count.
    chunks=[header(0.,.5,.1,1e-6)]
    for j in range(65540):chunks.append(normal(j,j,1000,round(100*j*.5/3600/1e-6)))
    chunks.append(footer(65539,65539));wire=b''.join(chunks);decoded=decode(wire)
    assert len(decoded['rows'])==65540 and decoded['packets'][65536]['seq']==0
    for a,b in [(65534,65535),(65535,65536),(65536,65537)]:assert unwrap_steps(decoded['packets'][a],decoded['packets'][b])==(1,'unique')
    kept=[decoded['packets'][j]['blob'] for j in [0,1,65535,65536,65539]]
    result=receive(wire[:36],kept,decoded['footer']['blob']);assert result['terminal']=='complete'
    result=receive(wire[:36],kept[:-1],decoded['footer']['blob']);assert result['terminal']=='erased'
    assert receive(wire[:36],kept,None)['terminal']=='unknown'
    assert receive(wire[:36],kept,decoded['footer']['blob'],memoized=True)==receive(wire[:36],kept,decoded['footer']['blob'],memoized=False)
    # A sufficiently wide erasure admits multiple modulo-compatible edge counts.
    aa=dict(tick=0,seq=0);bb=dict(tick=10*65536*2,seq=0)
    assert unwrap_steps(aa,bb)[1]=='ambiguous'
    # Constructed inputs are explicitly numerical fixtures, not observed flight results.
    t=np.arange(0.,21.,.5);p=100+20*np.sin(t);e=cumulative_energy(t,p);modes=[]
    for horizon in [0,2,4]:
        for search in ([False,True] if horizon==0 else [False]):
            for esc in [False,True]:
                out=encode(t,p,horizon=horizon,search=search,escape_enabled=esc,crc=32)
                assert out['status']=='OK';measured=measure_decoded(t,p,e,out['decoded']);assert measured['passes']
                assert out['max_buffer']<=12+(horizon-1 if horizon else 0)
                assert out['release_s']<=(5.5 if not horizon else 5+horizon*.5)+1e-10
                modes.append(dict(horizon=horizon,search=search,escape=esc,bytes=out['encoded_bytes']))
    example=encode(np.arange(0.,2.5,.5),np.linspace(100.,120.,5),profile='medium')
    assert example['status']=='OK'
    ex=example['decoded'];D=ex['rows'][-1,1]-ex['rows'][0,1]
    c=3600*(ex['rows'][-1,3]-ex['rows'][0,3])/D-(ex['rows'][0,2]+ex['rows'][-1,2])/2
    write('results/worked_wire_example.json',dict(fixture=True,observed_flight=False,power_start_W=100.,power_end_W=120.,duration_s=2.,
        decoded_endpoint_energy_Wh=float(ex['rows'][-1,3]),correction_W=float(c),midpoint_power_W=float(110+1.5*c),
        encoded_bytes=len(example['wire']),footer_bytes=len(ex['footer']['blob']),wire_hex=example['wire'].hex(),
        **measure_decoded(np.arange(0.,2.5,.5),np.linspace(100.,120.,5),cumulative_energy(np.arange(0.,2.5,.5),np.linspace(100.,120.,5)),ex)))
    from transport import pack_stream,recover
    transport_checks=[]
    for packing in [1,4,16]:
        for protection in ['none','repeat','xor']:
            stream=pack_stream(ex,packing,protection)
            from transport import unpack_data
            for data_blob in stream['data']:assert unpack_data(data_blob,example['wire'][:36])==unpack_data.__wrapped__(data_blob,example['wire'][:36])
            result=recover(stream,np.zeros(len(stream['datagrams']),bool),example['wire'][:36],verify_original=True)
            assert len(result['packets'])==len(ex['packets']) and result['terminal']=='complete'
            if protection=='xor':
                lost=np.zeros(len(stream['datagrams']),bool);lost[0]=True
                result=recover(stream,lost,example['wire'][:36],verify_original=True)
                assert len(result['packets'])==len(ex['packets']) and result['recovered_data_frames']==1
            transport_checks.append(dict(m=packing,protection=protection,bytes=stream['transmitted_bytes']))
    write('audit/kernel_validation.json',dict(passed=True,continuous_cases=matches,max_abs_differences=maximum.tolist(),malformed_ULEB_rejections=malformed,sequence_wrap_checkpoints=65540,wire_fixtures=modes,forced_escape_fixture=escape_fixture,transport_fixtures=transport_checks,seconds=time.perf_counter()-start,seed=SEED))
    print('Compiled continuous guards and new-wire fixtures passed',flush=True)

if __name__=='__main__':run()
