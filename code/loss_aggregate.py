"""Bounded-memory consolidation of record/replicate parquet evidence."""
from common import *
import pyarrow as pa,pyarrow.parquet as pq

def consolidate(paths):
    keys=['m','protection','channel','rate','repeat']
    index=pd.MultiIndex.from_product([[1,4,16],['none','repeat','xor'],['Bernoulli','GilbertElliott'],[.01,.05,.1,.2],range(30)],names=keys)
    sources=['IDF','CMU','AMOVFLY','Solar'];N=len(index)
    sums=['attempt_duration_s','certified_duration_s','anchor_available_duration_s','transmitted_bytes','base_stream_bytes','parity_bytes','footer_bytes',
        'lost_datagrams','sent_datagrams','recovered_data_frames','bridge_duration_s','bridge_segments','terminal_erased','terminal_detected','footer_delivered','ambiguous_modulo_gaps']
    maxima=['bridge_power_max_W','bridge_energy_max_Wh','encoded_packet_buffer_bound','additional_packing_delay_bound_s']
    total={ds:np.zeros((N,len(sums)+3)) for ds in sources};maximum={ds:np.zeros((N,len(maxima))) for ds in sources};records={ds:0 for ds in sources}
    writer=None;rows=0;out=DEV/'results/loss_record_replicates.parquet';temporary=out.with_suffix('.partial')
    strings=['dataset','flight_id','group_id','protection','channel','status','code_signature'];booleans=['terminal_erased','terminal_detected','footer_delivered']
    integers=['m','repeat','transmitted_bytes','base_stream_bytes','parity_bytes','footer_bytes','lost_datagrams','sent_datagrams','recovered_data_frames','bridge_segments','encoded_packet_buffer_bound','ambiguous_modulo_gaps']
    floats=['rate','attempt_duration_s','certified_duration_s','anchor_available_duration_s','certified_fraction','anchor_available_fraction','bridge_duration_s','bridge_power_max_W','bridge_energy_max_Wh','theoretical_certified_fraction','theoretical_anchor_available_fraction','additional_packing_delay_bound_s']
    schema=pa.schema([(c,pa.string()) for c in strings]+[(c,pa.bool_()) for c in booleans]+[(c,pa.int64()) for c in integers]+[(c,pa.float64()) for c in floats])
    try:
        writer=pq.ParquetWriter(temporary,schema,compression='zstd')
        for path in paths:
            f=pd.read_parquet(path);ds=str(f.dataset.iloc[0]);assert f.dataset.eq(ds).all()
            for c in strings:
                if c not in f:f[c]=''
                f[c]=f[c].fillna('').astype(str)
            for c in integers:
                if c not in f:f[c]=0
                f[c]=f[c].fillna(0).astype('int64')
            for c in booleans:
                if c not in f:f[c]=False
                f[c]=f[c].fillna(False).astype(bool)
            for c in floats:
                if c not in f:f[c]=np.nan if c.startswith('theoretical_') else 0.
                f[c]=f[c].astype(float)
            writer.write_table(pa.Table.from_pandas(f[schema.names],schema=schema,preserve_index=False));rows+=len(f)
            f=f.set_index(keys).reindex(index);assert len(f)==N and f.attempt_duration_s.notna().all()
            values=f[sums].to_numpy(dtype=float)
            conditional=(f.terminal_erased&f.footer_delivered).to_numpy(dtype=float)
            theoretical=(f.attempt_duration_s*f.theoretical_certified_fraction.fillna(0)).to_numpy()
            valid=f.theoretical_certified_fraction.notna().to_numpy(dtype=float)
            total[ds]+=np.c_[values,conditional,theoretical,valid]
            maximum[ds]=np.maximum(maximum[ds],f[maxima].to_numpy(dtype=float));records[ds]+=1
    finally:
        if writer is not None:writer.close()
    os.replace(temporary,out)
    aggregates=[]
    for ds in sources:
        for i,key in enumerate(index):
            z=dict(zip(sums,total[ds][i,:len(sums)]));den=z['attempt_duration_s'];cert=z['certified_duration_s'];level=z['anchor_available_duration_s']
            row=dict(dataset=ds,**dict(zip(keys,key)),records=records[ds],duration_s=den,certified_fraction=cert/den,anchor_available_fraction=level/den,
                missing_hours=(den-cert)/3600,transmitted_bytes=z['transmitted_bytes'],bridge_duration_s=z['bridge_duration_s'],
                terminal_erased=int(z['terminal_erased']),terminal_detected=int(z['terminal_detected']),footer_delivered=int(z['footer_delivered']),
                detection_conditional=z['terminal_detected']/max(1,total[ds][i,len(sums)]),
                detection_unconditional=z['terminal_detected']/max(1,z['terminal_erased']),
                application_byte_multiplier=z['transmitted_bytes']/z['base_stream_bytes'] if z['base_stream_bytes'] else np.nan,
                theoretical_certified_fraction=total[ds][i,len(sums)+1]/den if total[ds][i,len(sums)+2] else np.nan)
            row.update({c:float(maximum[ds][i,j]) for j,c in enumerate(maxima)})
            row.update({c:z[c] for c in ['parity_bytes','footer_bytes','lost_datagrams','sent_datagrams','recovered_data_frames','bridge_segments','ambiguous_modulo_gaps']})
            aggregates.append(row)
    return pd.DataFrame(aggregates),rows
