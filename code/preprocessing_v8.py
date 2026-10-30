"""Exact PL discrepancy between matched retained native samples and .5s references."""
import zipfile,io
from common import *
from sources import source_path
from kernels import cumulative_energy

def first_episode(t,p,state):
    values=np.column_stack([t,p,state]);good=np.isfinite(values).all(1)&(np.asarray(p)>=0);a=values[good]
    if len(a)<2:return None
    a=a[np.argsort(a[:,0],kind='stable')];a=a[np.r_[True,np.diff(a[:,0])>0]]
    cuts=np.r_[0,np.flatnonzero(np.diff(a[:,0])>2)+1,len(a)]
    for lo,hi in zip(cuts[:-1],cuts[1:]):
        b=a[lo:hi]
        if len(b)>=2 and b[-1,0]-b[0,0]>=2:return b[:,0]-b[0,0],b[:,1]
    return None

def qstate(f,cols):
    q=f[cols].to_numpy();q=q/np.maximum(np.linalg.norm(q,axis=1)[:,None],1e-12);x,y,z,w=q.T
    roll=np.arctan2(2*(w*x+y*z),1-2*(x*x+y*y));pitch=np.arcsin(np.clip(2*(w*y-z*x),-1,1))
    return np.c_[np.sin(roll),np.cos(roll),np.sin(pitch),np.cos(pitch)]

def discrepancy(native,reference):
    tn,pn=native;t,p=reference['t'],reference['p'];limit=t[-1]
    interp=np.interp(t,tn,pn)
    alignment=float(np.max(abs(interp-p)))
    if alignment>1e-7:return dict(status='NATIVE_PREPARED_ALIGNMENT_NOT_VERIFIED',interpolation_max_difference_W=alignment)
    knots=np.unique(np.r_[t,tn[(tn>=t[0])&(tn<=limit)]])
    delta=np.interp(knots,tn,pn)-np.interp(knots,t,p);d=np.diff(knots)
    energy=np.r_[0.,np.cumsum((delta[:-1]+delta[1:])*d/7200)]
    maximum=float(np.max(abs(energy)))
    for j,(a,b) in enumerate(zip(delta[:-1],delta[1:])):
        if a*b<0:
            x=-a*d[j]/(b-a);v=energy[j]+(a*x+.5*(b-a)/d[j]*x*x)/3600
            maximum=max(maximum,abs(float(v)))
    return dict(status='OK',interpolation_max_difference_W=alignment,native_samples=int(((tn>=0)&(tn<=limit)).sum()),prepared_samples=len(t),
        duration_s=float(limit),native_max_gap_s=float(np.diff(tn).max()),
        preprocessing_power_max_W=float(np.max(abs(delta))),preprocessing_energy_max_Wh=maximum,
        preprocessing_terminal_energy_Wh=float(energy[-1]))

def run():
    step0();wanted={(r['dataset'],str(r['flight_id'])):r for r in records()};rows=[];seen=set();provenance=[]
    def record(ds,fid,native,source):
        key=(ds,str(fid))
        if key not in wanted:return
        seen.add(key);r=wanted[key]
        row=identity(r)|dict(source=source)
        row.update(discrepancy(native,r) if native is not None else dict(status='NO_MATCHED_NATIVE_EPISODE'))
        rows.append(row)
    # IDF uses the same retained native state-aligned adapter input as the
    # prepared benchmark; it is not described as an untouched autopilot log.
    for platform in ['pixhawk','speedy']:
        path=source_path(platform)
        f=pd.read_parquet(path);provenance.append(dict(dataset='IDF',path=str(path.relative_to(ROOT.parent)),sha256=sha(path),scope='retained state-aligned source samples'))
        for fid,z in f.groupby('flight_id',sort=True):
            state=np.c_[np.hypot(z.vn,z.ve),z.climb,np.sin(z.roll),np.cos(z.roll),np.sin(z.pitch),np.cos(z.pitch)]
            record('IDF',str(fid),first_episode(z.time_s.to_numpy(),z.power_w.to_numpy(),state),str(path.relative_to(ROOT.parent)))
        del f
    path=source_path('cmu');provenance.append(dict(dataset='CMU',path=str(path.relative_to(ROOT.parent)),sha256=sha(path)))
    with zipfile.ZipFile(path) as archive:
        for ds,fid in wanted:
            if ds!='CMU':continue
            f=pd.read_csv(archive.open(f'flights/{fid}.csv'))
            state=np.c_[np.hypot(f.velocity_x,f.velocity_y),f.velocity_z,qstate(f,['orientation_x','orientation_y','orientation_z','orientation_w'])]
            record(ds,fid,first_episode(f.time.to_numpy(),(f.battery_voltage*f.battery_current).to_numpy(),state),f'flights/{fid}.csv')
    path=source_path('amov');provenance.append(dict(dataset='AMOVFLY',path=str(path.relative_to(ROOT.parent)),sha256=sha(path)))
    with zipfile.ZipFile(path) as archive:
        prefix=archive.namelist()[0].split('/')[0]+'/'
        for ds,fid in wanted:
            if ds!='AMOVFLY':continue
            f=pd.read_csv(archive.open(prefix+fid+'.csv'));f=f.sort_values('time',kind='stable').drop_duplicates('time',keep='first')
            state=np.c_[np.hypot(f.v_x,f.v_y),f.v_z,qstate(f,['o_x','o_y','o_z','o_w'])]
            record(ds,fid,first_episode(f.time.to_numpy(),(f.battery_voltage*f.battery_current).to_numpy(),state),fid+'.csv')
    path=source_path('solar');f=pd.read_parquet(path,columns=['time_s','power_W'])
    provenance.append(dict(dataset='Solar',path=str(path.relative_to(ROOT.parent)),sha256=sha(path)))
    for ds,fid in wanted:
        if ds!='Solar':continue
        k=int(fid.split('_')[-1]);base=2449.+k*21600
        # Match the original benchmark's right bracket. Its last prepared knot
        # may precede 120s because that older adapter stopped at base+120.
        use=(f.time_s>=base)&(f.time_s<=base+120)&np.isfinite(f.power_W)&(f.power_W>=0)
        z=f[use];tn=z.time_s.to_numpy();pn=z.power_W.to_numpy()
        record(ds,fid,(tn-tn[0],pn),f'Solar window {k}')
    for key,r in wanted.items():
        if key not in seen:rows.append(identity(r)|dict(status='NO_VERIFIED_SOURCE_MAPPING'))
    result=pd.DataFrame(rows);assert len(result)==718
    # Triangle bounds concern two explicit PL references, not physical sensor
    # error or continuous raw reality between the source's own timestamps.
    result['codec_to_native_power_upper_W']=25+result.get('preprocessing_power_max_W',np.nan)
    result['codec_to_native_energy_upper_Wh']=.001+result.get('preprocessing_energy_max_Wh',np.nan)
    result.to_csv(DEV/'results/native_preprocessing_discrepancy.csv',index=False)
    write('results/preprocessing_gate.json',dict(completed=True,inputs=718,matched=int((result.status=='OK').sum()),statuses=result.status.value_counts().to_dict(),
        source_provenance=provenance,interpretation='Exact PL-to-PL discrepancy over matched prepared support; triangle bounds do not calibrate physical sensor error.'))

if __name__=='__main__':run()
