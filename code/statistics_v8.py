"""All-attempt byte comparisons, matched profiles and cluster sensitivity."""
from common import *
from sources import source_path
from scipy.stats import wilcoxon,t as student_t,gamma
import zipfile

CONTROLS=['Swing','SlideCore','DPvertical','SwingIso','SlideCoreIso','DPverticalIso','ZFP','ZFPIso','zstd','SZ3','Native32','SwingEnergy','SlideEnergy','LinearResetGuarded']

def collectors():
    path=source_path('amov')
    with zipfile.ZipFile(path) as archive:
        member=next(n for n in archive.namelist() if n.endswith('/Flight_info.csv'));f=pd.read_csv(archive.open(member))
    f['collector']=f['Pick Man'].astype('string').str.strip().replace({'mj':'lmj'})
    f['key']=f['Data Dir'].str.strip()+'|'+f.FlightName.str.strip()+'|'+pd.to_datetime(f['Date time']).dt.strftime('%Y-%m-%d')
    groups=f.groupby('key').collector.agg(lambda x:sorted(set(x.dropna().astype(str))))
    write('results/collector_provenance.json',dict(source_sha256=sha(path),member=member,alias_map={'mj':'lmj'},
        identity='original dataset collector metadata; not verified pilot identity',alias_source='original AMOVFLY README identifies mj/lmj as the same collector'))
    return {k:v[0] for k,v in groups.items() if len(v)==1}

def holm(rows,key,out):
    order=sorted(range(len(rows)),key=lambda j:rows[j][key]);previous=0.
    for rank,j in enumerate(order):rows[j][out]=min(1.,max(previous,rows[j][key]*(len(rows)-rank)));previous=rows[j][out]

def effects(delta,rng,B=10000):
    delta=np.asarray(delta,dtype=float);n=len(delta);mean=delta.mean();sd=delta.std(ddof=1);se=sd/np.sqrt(n)
    tri=np.triu_indices(n);hl=float(np.median((delta[:,None]+delta[None,:])[tri]/2))
    means=[];hls=[];wild=[];center=delta-mean
    for start in range(0,B,200):
        size=min(200,B-start);sample=delta[rng.integers(0,n,(size,n))];means.extend(sample.mean(1))
        hls.extend(np.median((sample[:,:,None]+sample[:,None,:])[:,tri[0],tri[1]]/2,axis=1))
        w=center*rng.choice([-1,1],(size,n));s=w.std(axis=1,ddof=1)/np.sqrt(n)
        wild.extend(np.divide(w.mean(1),s,out=np.zeros(size),where=s>0))
    means=np.asarray(means);wild=np.asarray(wild);obs=abs(mean/se) if se>0 else (np.inf if mean else 0.)
    p=(1+np.sum(abs(wild)>=obs-1e-15))/(B+1)
    low,high=np.quantile(means,[.025,.975]);hlow,hhigh=np.quantile(hls,[.025,.975]);ql,qh=np.quantile(wild,[.025,.975])
    # TOST on the mean difference in Dense-byte ratio, with a margin fixed
    # before this code is run. Two one-sided Student t tests and a 90% CI.
    margin=.01
    if se>0:
        p_lower=float(student_t.sf((mean+margin)/se,n-1));p_upper=float(student_t.cdf((mean-margin)/se,n-1))
        half=float(student_t.ppf(.95,n-1)*se)
    else:p_lower=0. if mean>-margin else 1.;p_upper=0. if mean<margin else 1.;half=0.
    return dict(clusters=n,mean_delta=float(mean),median_cluster_delta=float(np.median(delta)),HL=float(hl),
        mean_low95=float(low),mean_high95=float(high),HL_low95=float(hlow),HL_high95=float(hhigh),
        standardized_paired=float(mean/sd) if sd else np.nan,wild_studentized_p=p,
        wild_studentized_low95=float(mean-qh*se),wild_studentized_high95=float(mean-ql*se),
        wilcoxon_p=1. if np.all(delta==0) else float(wilcoxon(delta).pvalue),
        LOCO_mean_min=float(min((delta.sum()-v)/(n-1) for v in delta)),
        LOCO_mean_max=float(max((delta.sum()-v)/(n-1) for v in delta)),
        tost_margin=margin,tost_p_lower=p_lower,tost_p_upper=p_upper,tost_p_max=max(p_lower,p_upper),
        mean_low90=float(mean-half),mean_high90=float(mean+half),TOST_equivalent=bool(p_lower<.05 and p_upper<.05))

def run():
    step0();main=pd.read_csv(DEV/'results/main_120.csv',dtype={'flight_id':str,'group_id':str})
    base=pd.read_csv(DEV/'results/baselines.csv',dtype={'flight_id':str,'group_id':str});rng=np.random.default_rng(SEED)
    key=['dataset','flight_id','group_id'];primary=main.query("method=='Escape' and profile=='medium'").copy()
    assert len(primary)==718
    results=[];alternate=[];collector_map=collectors()
    for control in CONTROLS:
        ref=base[base.method==control]
        joined=primary.merge(ref,on=key,suffixes=('_dbg','_ref'),validate='one_to_one')
        assert len(joined)==718
        if (joined.status_ref=='NOT_RUN_LIBRARY_UNAVAILABLE').any():continue
        for ds,part in joined[joined.dataset!='Solar'].groupby('dataset'):
            # Failed streaming DBG includes its actually emitted prefix plus
            # a full Dense restart. Offline baseline admission uses Dense only.
            delta=(part.neutral_effective_byte_ratio_dbg-part.neutral_effective_byte_ratio_ref)
            d=pd.DataFrame(dict(group=part.group_id,delta=delta)).groupby('group').delta.mean().to_numpy()
            native=part.effective_byte_ratio_dbg-part.effective_byte_ratio_ref
            result=dict(dataset=ds,control=control,metric='effective_lossless_common_ULEB_byte_ratio',records=len(part),native_mean_record_delta=float(native.mean()),**effects(d,rng));results.append(result)
            # Alternative aircraft/platform clusters are descriptive when only
            # 1-3 units exist, with no fabricated bootstrap precision.
            labels=part.flight_id.str.split('_').str[0] if ds=='IDF' else part.flight_id.str.extract(r'Uav([GRY])',expand=False) if ds=='AMOVFLY' else pd.Series('single_M100',index=part.index)
            assert labels.notna().all()
            alt=pd.DataFrame(dict(group=labels,delta=delta)).groupby('group').delta.mean()
            alternate.append(dict(dataset=ds,control=control,kind='platform' if ds=='IDF' else 'aircraft',clusters=len(alt),
                mean_delta=float(alt.mean()),minimum_cluster_delta=float(alt.min()),maximum_cluster_delta=float(alt.max()),
                inferential_status='DESCRIPTIVE_TOO_FEW_AIRCRAFT_CLUSTERS'))
            if ds=='AMOVFLY':
                keys=part.flight_id.str.split('/').str[0]+'|'+part.flight_id.str.split('/').str[-1]+'|'+part.group_id
                lab=keys.map(collector_map);known=lab.notna()
                alt=pd.DataFrame(dict(group=lab[known],delta=delta[known])).groupby('group').delta.mean()
                alternate.append(dict(dataset=ds,control=control,kind='collector_not_verified_pilot',clusters=len(alt),mapped_records=int(known.sum()),
                    mean_delta=float(alt.mean()),minimum_cluster_delta=float(alt.min()),maximum_cluster_delta=float(alt.max()),
                    inferential_status='DESCRIPTIVE_FEW_COLLECTORS'))
    holm(results,'wilcoxon_p','wilcoxon_p_holm');holm(results,'wild_studentized_p','wild_studentized_p_holm')
    pd.DataFrame(results).to_csv(DEV/'results/paired_effects_v8.csv',index=False)
    pd.DataFrame(alternate).to_csv(DEV/'results/alternative_aircraft_clusters.csv',index=False)
    # Equivalence is specifically the new guarded energy-aware Swing control.
    # Legacy 36 Holm comparisons are retained in full rather than substituted.
    tost=[dict(row) for row in results if row['control']=='SwingEnergy']
    holm(tost,'tost_p_max','tost_p_holm')
    for row in tost:row['TOST_equivalent_after_Holm']=row['tost_p_holm']<.05
    pd.DataFrame(tost).to_csv(DEV/'results/tost_dbg_swing.csv',index=False)
    legacy=pd.read_csv(ROOT/'development_v7/results/paired_wilcoxon_holm.csv');assert len(legacy)==36
    legacy.to_csv(DEV/'results/legacy_36_Holm.csv',index=False)
    matched=[]
    for scope in ['120','full']:
        f=pd.read_csv(DEV/f'results/main_{scope}.csv',dtype={'flight_id':str,'group_id':str})
        for ds,part in f.query("method=='Strict'").groupby('dataset'):
            pivot=part.pivot(index='flight_id',columns='profile',values='status');support=pivot.index[(pivot=='OK').all(axis=1)]
            for profile,pop in part.groupby('profile'):
                common=pop[pop.flight_id.isin(support)];success=pop[pop.status=='OK']
                matched.append(dict(dataset=ds,scope=scope,profile=profile,all_records=len(pop),completed=len(success),common_completed=len(common),
                    completed_only_mean_byte_ratio=float(success.byte_ratio.mean()),matched_mean_byte_ratio=float(common.byte_ratio.mean()),
                    all_attempt_effective_mean_byte_ratio=float(pop.effective_byte_ratio.mean()),
                    matched_sum_bytes=float(common.encoded_bytes.sum()),matched_sum_dense=float(common.dense_bytes.sum())))
    pd.DataFrame(matched).to_csv(DEV/'results/matched_profile_support.csv',index=False)
    # A refusal hazard is a descriptive event/exposure rate, not a validated
    # constant-hazard forecast of how many future hour-long flights survive.
    full=pd.read_csv(DEV/'results/main_full.csv');hazards=[]
    for (ds,profile),part in full.query("method=='Strict'").groupby(['dataset','profile']):
        fail=part.status!='OK';events=int(fail.sum());exposure=np.where(fail,part.first_exposure_s,part.duration_s).sum()/3600
        lo=0. if events==0 else float(gamma.ppf(.025,events)/exposure)
        hi=float(gamma.ppf(.975,events+1)/exposure)
        hazards.append(dict(dataset=ds,profile=profile,records=len(part),events=events,exposure_hours=float(exposure),
            events_per_hour=float(events/exposure),poisson_low95=lo,poisson_high95=hi,
            caution='descriptive Poisson interval ignores episode clustering and does not establish a stationary future hazard'))
    pd.DataFrame(hazards).to_csv(DEV/'results/strict_refusal_hazard.csv',index=False)
    write('results/statistics_gate.json',dict(completed=True,contrasts=len(results),legacy_Holm_family=36,new_Holm_family=len(results),
        TOST_family=len(tost),bootstrap_replicates=10000,seed=SEED,Solar='descriptive; excluded from p-value families'))

if __name__=='__main__':run()
