"""Actual application datagram erasures, recovery and duration-weighted metrics."""
import hashlib,time
from common import *
from kernels import cumulative_energy,segment_stats
from wire import decode,packet_fields
from transport import pack_stream,recover,ge_mask,analytic_bernoulli,unpack_data

def run():
    step0();assert (DEV/'results/main_120_gate.json').exists()
    wires=joblib.load(DEV/'data/wires_120.joblib');base=DEV/'data/loss_checkpoints';base.mkdir(exist_ok=True)
    stamp=hashlib.sha256(b''.join((DEV/'code'/name).read_bytes() for name in ['loss_v8.py','wire.py','transport.py','kernels.py'])+sha(DEV/'data/wires_120.joblib').encode()).hexdigest()
    output=[];start=time.perf_counter()
    for n,r in enumerate(records()):
        tag=hashlib.sha256((r['dataset']+'|'+str(r['flight_id'])).encode()).hexdigest()[:20];path=base/(tag+'.parquet')
        if path.exists():
            previous=pd.read_parquet(path);assert previous.code_signature.eq(stamp).all(),'Changed transport code/input wire: archive loss checkpoints before replay'
            output.append(path);continue
        key=(r['dataset'],r['flight_id'],'Escape','medium');duration=float(r['t'][-1]-r['t'][0]);local=[]
        if key not in wires:
            # Unsupported records stay in every denominator and contribute no
            # certified duration. A dense restart is outside this coded loss
            # channel experiment and is reported separately as fallback cost.
            for m in [1,4,16]:
                for protection in ['none','repeat','xor']:
                    for channel in ['Bernoulli','GilbertElliott']:
                        for rate in [.01,.05,.1,.2]:
                            for rep in range(30):local.append(identity(r)|dict(m=m,protection=protection,channel=channel,rate=rate,repeat=rep,status='SOURCE_REFUSED',attempt_duration_s=duration,certified_duration_s=0.,anchor_available_duration_s=0.,transmitted_bytes=0,bridge_duration_s=0.,bridge_power_max_W=0.,bridge_energy_max_Wh=0.,terminal_erased=False,terminal_detected=False,footer_delivered=False))
            frame=pd.DataFrame(local);frame['code_signature']=stamp;temporary=path.with_suffix('.partial');frame.to_parquet(temporary,index=False);os.replace(temporary,path);output.append(path);continue
        blob=wires[key];decoded=decode(blob);rows=decoded['rows'];dur=np.diff(rows[:,1]);ticks=np.array([p['tick'] for p in decoded['packets']])
        originals={int(ti):i for i,ti in enumerate(ticks)};e=cumulative_energy(r['t'],r['p']);bridge_cache={}
        for m in [1,4,16]:
            for protection in ['none','repeat','xor']:
                transport=pack_stream(decoded,m,protection);count=len(transport['datagrams'])
                # A no-loss recovery fixture checks actual bytes for each
                # record/configuration, in addition to parsing every replicate.
                zero=recover(transport,np.zeros(count,dtype=bool),blob[:36],verify_original=True)
                assert len(zero['packets'])==len(rows) and zero['terminal']=='complete'
                # Parsing cache entries depend on complete actual received
                # bytes, not hidden packet IDs or the missing-data pattern.
                packet_fields.cache_clear();unpack_data.cache_clear()
                for channel in ['Bernoulli','GilbertElliott']:
                    for rate in [.01,.05,.1,.2]:
                        theoretical=analytic_bernoulli(decoded,transport,rate) if protection=='none' and channel=='Bernoulli' else (np.nan,np.nan)
                        salt=int.from_bytes(hashlib.sha256(f'{SEED}|{tag}|{m}|{protection}|{channel}|{rate}'.encode()).digest()[:8],'little')
                        rng=np.random.default_rng(salt)
                        for rep in range(30):
                            erased=rng.random(count)<rate if channel=='Bernoulli' else ge_mask(count,rate,rng)
                            received=recover(transport,erased,blob[:36],verify_original=True)
                            ids=np.array([originals[v['tick']] for v in received['packets']],dtype=int)
                            present=np.zeros(len(rows),dtype=bool);present[ids]=True
                            cert=present[:-1]&present[1:];cert_s=float(dur[cert].sum());level_s=float(dur[present[:-1]].sum())
                            bridge_s=0.;bridge_p=0.;bridge_e=0.;bridge_count=0
                            for aa,bb in zip(ids[:-1],ids[1:]):
                                if bb==aa+1:continue
                                pair=(int(aa),int(bb))
                                if pair not in bridge_cache:
                                    a=int(np.searchsorted(r['t'],rows[aa,1]));b=int(np.searchsorted(r['t'],rows[bb,1]))
                                    bridge_cache[pair]=segment_stats(r['t'],r['p'],e,a,b,rows[aa,2],rows[bb,2],rows[aa,3],rows[bb,3])
                                values=bridge_cache[pair];bridge_s+=rows[bb,1]-rows[aa,1];bridge_p=max(bridge_p,values[0]);bridge_e=max(bridge_e,values[1]);bridge_count+=1
                            terminal_erased=not present[-1];detected=received['terminal']=='erased'
                            assert not detected or terminal_erased
                            local.append(identity(r)|dict(m=m,protection=protection,channel=channel,rate=rate,repeat=rep,status='OK',
                                attempt_duration_s=duration,certified_duration_s=cert_s,anchor_available_duration_s=level_s,
                                certified_fraction=cert_s/duration,anchor_available_fraction=level_s/duration,
                                transmitted_bytes=transport['transmitted_bytes'],base_stream_bytes=len(blob),parity_bytes=transport['parity_bytes'],
                                footer_bytes=transport['footer_bytes'],lost_datagrams=int(erased.sum()),sent_datagrams=count,
                                recovered_data_frames=received['recovered_data_frames'],bridge_duration_s=bridge_s,bridge_segments=bridge_count,
                                bridge_power_max_W=bridge_p,bridge_energy_max_Wh=bridge_e,
                                terminal_erased=terminal_erased,terminal_detected=detected,footer_delivered=received['footer_delivered'],
                                theoretical_certified_fraction=theoretical[0],theoretical_anchor_available_fraction=theoretical[1],
                                encoded_packet_buffer_bound=transport['max_encoded_buffer_checkpoints'],additional_packing_delay_bound_s=(m-1)*5.,
                                ambiguous_modulo_gaps=received['ambiguous_gaps']))
        frame=pd.DataFrame(local);frame['code_signature']=stamp;temporary=path.with_suffix('.partial');frame.to_parquet(temporary,index=False);os.replace(temporary,path);output.append(path)
        if (n+1)%25==0:print('loss',n+1,'of 718 seconds',round(time.perf_counter()-start,1),flush=True)
    # Consolidate one record at a time rather than holding 1.55 million rows
    # and a second concatenated copy in RAM on the research desktop.
    from loss_aggregate import consolidate
    reps,raw_rows=consolidate(output);reps.to_csv(DEV/'results/loss_replicates.csv',index=False)
    keys=['dataset','m','protection','channel','rate','repeat']
    metrics=[c for c in reps.columns if c not in keys]
    summary=reps.groupby(keys[:-1])[metrics].agg(['mean','std','min','max']);summary.to_csv(DEV/'results/loss_summary.csv')
    missing=reps.groupby(keys[:-1]).missing_hours.agg(['sum','mean','std']);missing.columns=['Missing_h_sum_30','Missing_h_per_repeat_mean','Missing_h_per_repeat_SD'];missing.to_csv(DEV/'results/loss_missing_hours.csv')
    write('results/loss_gate.json',dict(completed=True,inputs=718,repetitions=30,record_replicate_rows=raw_rows,seed=SEED,
        channels=['Bernoulli','stationary Gilbert-Elliott mean bad run 3 datagrams'],packing=[1,4,16],protection=['none','repeat previous endpoint','one-erasure XOR blocks of four'],
        bytes='actual application header, data framing, repeats, parity and EOS; no UDP/IP/radio overhead',
        absolute_energy_metric='left absolute-anchor availability weighted by the following original segment duration; this is not certified interpolation through a gap',
        bridge='uncertified quadratic between surviving nonadjacent endpoints; no leading/trailing extrapolation',
        FEC_delay='retrospective recovery; parity arrival latency is not measured as a live guarantee',seconds=time.perf_counter()-start))

if __name__=='__main__':run()
