"""Batch-stream the original Solar campaign into independent gap-split codecs."""
import argparse,time,threading,struct
from common import *
from sources import source_path
import pyarrow.parquet as pq
import psutil
from encoders import StreamingEncoder,StreamRefusal
from wire import HEADER,decode_packet,Refusal,EOS

SOURCE=source_path('solar')

def prepared_knots(path):
    """First duplicate, finite nonnegative power, gaps >2s and .5s interpolation.

    The raw-to-prepared interpolator needs the next native bracket. The codec
    sees prepared knots only, and no raw online latency claim follows from it.
    Memory holds one parquet batch, one native bracket and scalar grid state.
    """
    previous=None;start=None;index=0;last_native=-np.inf;segment=-1
    for batch in pq.ParquetFile(path).iter_batches(batch_size=8192,columns=['time_s','power_W','valid_electrical']):
        d=batch.to_pydict()
        for ti,pi,valid in zip(d['time_s'],d['power_W'],d['valid_electrical']):
            if ti is None or pi is None:previous=None;continue
            ti=float(ti);pi=float(pi)
            if not np.isfinite(ti):previous=None;continue
            if ti<last_native:raise ValueError('RAW_SOLAR_NOT_CHRONOLOGICAL')
            if ti==last_native:continue
            last_native=ti
            if not valid or not np.isfinite(pi) or pi<0:previous=None;continue
            if previous is None or ti-previous[0]>2.:
                segment+=1;start=ti;index=1;previous=(ti,pi)
                yield segment,float(start),pi
                continue
            while start+index*.5<=ti:
                target=start+index*.5
                value=previous[1]+(pi-previous[1])*(target-previous[0])/(ti-previous[0])
                yield segment,float(target),float(value);index+=1
            previous=(ti,pi)

def run():
    step0();assert json.loads((DEV/'audit/kernel_validation.json').read_text())['passed']
    start=time.perf_counter();proc=psutil.Process();peak=[proc.memory_info().rss];stop=threading.Event()
    def monitor():
        while not stop.wait(.05):peak[0]=max(peak[0],proc.memory_info().rss)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    outdir=DEV/'data/solar_campaign';outdir.mkdir(exist_ok=True)
    modes={'Strict':dict(),'Escape':dict(escape_enabled=True),'SearchEscape':dict(search=True,escape_enabled=True)}
    active={};files={};states=[];segments=[];current=None;count=0;first=None;last=None
    def close():
        nonlocal active,files
        for name,state in active.items():
            obj=state['encoder']
            if state['status']=='OK':
                try:files[name].write(obj.finish())
                except Refusal as exc:state['status']=str(exc)
            files[name].close();row=dict(method=name,segment=current,status=state['status'],samples=state['samples'],
                start_s=state['start'],end_s=state['end'],duration_s=state['end']-state['start'],**obj.summary())
            row['wire_bytes']=(outdir/f'{current:05d}_{name}.bin').stat().st_size
            row['sequence_wraps']=(obj.seq-1)//65536
            if obj.first_failure is not None:row['first_refusal_exposure_s']=obj.first_failure['exposure_s'];row['first_refusal_guard']=obj.first_failure['first']
            assert row['wire_bytes']==row['encoded_bytes']
            states.append(row)
        active={};files={}
    try:
        for segment,ti,pi in prepared_knots(SOURCE):
            if segment!=current:
                if current is not None:close()
                current=segment
                for name,kw in modes.items():
                    active[name]=dict(encoder=StreamingEncoder(profile='medium',**kw),status='OK',samples=0,start=ti,end=ti)
                    files[name]=(outdir/f'{segment:05d}_{name}.bin').open('wb')
            first=ti if first is None else first;last=ti;count+=1
            for name,state in active.items():
                state['samples']+=1;state['end']=ti
                if state['status']!='OK':continue
                # Codec coordinates are exact half-second relative ticks.
                # Subtraction of large fractional source timestamps can differ
                # from .5 by an ULP even on this constructed uniform grid.
                relative_time=(state['samples']-1)*.5
                try:files[name].write(state['encoder'].push(relative_time,pi))
                except StreamRefusal as exc:files[name].write(exc.emitted);state['status']=str(exc)
                except Refusal as exc:state['status']=str(exc)
            if count%50000==0:print('Solar campaign',count,'knots',round(time.perf_counter()-start,1),'s',flush=True)
        if current is not None:close()
    finally:stop.set();thread.join();[f.close() for f in files.values()]
    frame=pd.DataFrame(states);frame.to_csv(DEV/'results/solar_campaign_streams.csv',index=False)
    # Re-read every complete output in bounded packet chunks to verify modulo
    # sequence across actual wraps without building a whole-stream rows array.
    wrapchecks=[]
    for row in states:
        if row['status']!='OK':continue
        path=outdir/f"{row['segment']:05d}_{row['method']}.bin"
        with path.open('rb') as stream:
            magic,origin,h,sp,se=HEADER.unpack(stream.read(36));buffer=b'';ordinal=0;previous_tick=-1;footer=False
            while True:
                new=stream.read(65536)
                if not new and not buffer:break
                buffer+=new;pos=0
                while pos<len(buffer):
                    saved=pos
                    try:item,end=decode_packet(buffer,pos,origin,h,sp,se)
                    except Refusal as exc:
                        if new and str(exc).startswith('TRUNCATED'):break
                        raise
                    pos=end
                    if item['kind']==EOS:
                        assert item['seq']==(ordinal-1)%65536 and item['tick']==previous_tick;footer=True
                    else:
                        assert not footer and item['seq']==ordinal%65536 and item['tick']>previous_tick
                        previous_tick=item['tick'];ordinal+=1
                buffer=buffer[pos:]
                if not new:
                    assert not buffer;break
            assert footer and ordinal==row['checkpoints']
            wrapchecks.append(dict(method=row['method'],segment=row['segment'],checkpoints=ordinal,wraps=(ordinal-1)//65536,passed=True))
    pd.DataFrame(wrapchecks).to_csv(DEV/'results/solar_modulo_stream_checks.csv',index=False)
    write('results/solar_gate.json',dict(completed=True,raw_source=str(SOURCE.relative_to(ROOT.parent)),source_sha256=sha(SOURCE),
        prepared_knots=count,campaign_span_hours=(last-first)/3600 if first is not None else 0.,gap_split_streams=current+1 if current is not None else 0,
        supported_hours=float(frame[frame.method=='Escape'].duration_s.sum()/3600),elapsed_s=time.perf_counter()-start,peak_process_RSS_bytes=max(peak[0],getattr(proc.memory_info(),'peak_wset',peak[0])),sampled_peak_RSS_bytes=peak[0],RSS_sampling_interval_s=.05,
        codec_owned_raw_buffer_max=int(frame.max_buffer.max()),native_interpolator_batch_rows=8192,
        time_coordinates='Exact half-second ticks relative to each gap-split stream; source offsets retained in evaluation CSV; no absolute mission-time preservation claim.',
        limits='Campaign span is not claimed to be continuous supported time; gaps/invalid electrical rows start a fresh stream, and each header/footer is charged. Whole-process RSS includes the parquet reader, Python and JIT runtime.'))

if __name__=='__main__':run()
