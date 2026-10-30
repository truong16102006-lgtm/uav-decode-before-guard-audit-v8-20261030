"""Independent wire replay, unchanged legacy evidence and manuscript locks."""
import importlib.util,time,platform,re
from common import *
from wire import decode,PROFILES,ESCAPE
from kernels import cumulative_energy,canonical_nodes,byte_oracle
from encoders import measure_decoded

def run():
    step0();start=time.perf_counter();frozen=json.loads((DEV/'before/freeze.json').read_text(encoding='utf8'))
    assert all(sha(ROOT/p)==v for p,v in frozen['v7'].items())
    protected={p:v for p,v in frozen['protected'].items() if p.replace('\\','/').startswith('Paper_04_Drones_Integrated/')}
    assert all(sha(ROOT.parent/p)==v for p,v in protected.items())
    for name in ['kernel_validation']:
        assert json.loads((DEV/f'audit/{name}.json').read_text())['passed']
    gate_names=['main_120','main_full','baselines','drift','receiver','loss','solar','preprocessing','heatmap','timing','statistics']
    for name in gate_names:assert json.loads((DEV/f'results/{name}_gate.json').read_text())['completed']
    cases=0;segments=0;escapes=0
    for scope in ['120','full']:
        population={(r['dataset'],r['flight_id']):r for r in scope_records(scope)}
        table=pd.read_csv(DEV/f'results/main_{scope}.csv',dtype={'flight_id':str,'group_id':str});wires=joblib.load(DEV/f'data/wires_{scope}.joblib')
        assert len(table)==718*17 and table.groupby(['dataset','flight_id']).size().eq(17).all()
        assert len(wires)==int((table.status=='OK').sum())
        assert table.effective_bytes.notna().all() and (table.effective_bytes>=0).all()
        for key,blob in wires.items():
            ds,fid,method,profile=key;r=population[(ds,fid)];d=decode(blob);e=cumulative_energy(r['t'],r['p']);m=measure_decoded(r['t'],r['p'],e,d)
            assert m['passes'],(scope,key,m)
            row=table[(table.dataset==ds)&(table.flight_id==str(fid))&(table.method==method)&(table.profile==profile)].iloc[0]
            assert row.status=='OK' and row.encoded_bytes==len(blob)
            for col in ['power_max_W','energy_max_Wh','minimum_power_W','max_segment_s']:
                assert np.isclose(row[col],m[col],rtol=1e-9,atol=1e-9),(scope,key,col)
            if method!='ByteOracle':
                extra=2 if method.startswith('Horizon2') else 4 if method.startswith('Horizon4') else 0
                assert row.max_buffer<=(12 if not extra else 11+extra)
                assert row.release_s<=(5.5 if not extra else 5+.5*extra)+1e-10
            cases+=1;segments+=len(d['rows'])-1;escapes+=sum(p['kind']==ESCAPE for p in d['packets'])
        refused=table[(table.status!='OK')&(table.method!='ByteOracle')]
        assert np.allclose(refused.effective_bytes,refused.dense_bytes+refused.partial_bytes)
        # Re-solve every fixed-node medium oracle independently from the
        # serialized path size, not by assuming checkpoint count equals bytes.
        for (ds,fid),r in population.items():
            e=cumulative_energy(r['t'],r['p']);nodes,cost=canonical_nodes(r['t'],r['p'],e,.1,1e-6);path,obj=byte_oracle(r['t'],r['p'],e,nodes,cost)
            key=(ds,fid,'ByteOracle','medium')
            if len(path):
                d=decode(wires[key]);assert np.array_equal(d['rows'][:,1],r['t'][path]);assert len(wires[key])==36+int(obj)+len(d['footer']['blob'])
            else:assert key not in wires
    # The retained 21 legacy fixed refusals are diagnosed on their record and
    # precision identities; byte equality pertains to Step 0, not version-8 tags.
    old=pd.read_csv(ROOT/'development_v7/results/main_cases.csv',dtype={'flight_id':str})
    old=old[old.method.str.startswith('DBG_fixed_')];new=pd.read_csv(DEV/'results/main_120.csv',dtype={'flight_id':str})
    new=new[new.method=='Strict'];joined=old.merge(new,on=['dataset','flight_id','profile'],suffixes=('_old','_new'),validate='one_to_one')
    changes=joined[(joined.status_old=='OK')!=(joined.status_new=='OK')]
    changes.to_csv(DEV/'audit/strict_legacy_status_differences.csv',index=False)
    # Numeric changes are evidence, never silently converted into passes. They
    # must be reconciled explicitly before sealing the manuscript.
    assert len(changes)==0,'Reconcile any changed strict feasibility before final release'
    failure=joined[joined.status_old!='OK'];assert len(failure)==21 and failure.first_first.notna().all()
    failure.to_csv(DEV/'results/legacy_21_refusal_causes.csv',index=False)
    effects=pd.read_csv(DEV/'results/paired_effects_v8.csv');assert effects.wilcoxon_p_holm.between(0,1).all()
    assert (effects.wilcoxon_p_holm>=effects.wilcoxon_p-1e-14).all()
    body=(ROOT/'paper/iccies_body.tex').read_text(encoding='utf8');front=(DEV/'before/frontmatter.tex').read_text(encoding='utf8');assert body.startswith(front)
    assert '[TODO' not in body and 'C:\\' not in body and 'D:\\' not in body
    assert all(',' not in key for key in re.findall(r'\\cite\{([^}]+)\}',body))
    assert not re.search(r'\\cite\{[^}]+\}[\s~,;]*\\cite\{',body)
    assert not re.search(r'development_v\d/|research/|[CD]:\\',body)
    result=dict(passed=True,attempted_records=718,wire_replays=cases,continuous_segments_rechecked=segments,escape_segments_rechecked=escapes,
        oracle_scopes=2,oracle_records_each=718,legacy_refusals_diagnosed=21,legacy_v7_files_unchanged=len(frozen['v7']),
        Paper4_files_unchanged=len(protected),locked_abstract_introduction_related_work_unchanged=True,
        code_sha256={p.name:sha(p) for p in (DEV/'code').glob('*.py')},python=platform.python_version(),seconds=time.perf_counter()-start)
    write('results/gate.json',result);print(json.dumps({k:v for k,v in result.items() if k!='code_sha256'},indent=2))

if __name__=='__main__':run()
