"""Round-2 gate: fresh v7 replay in an extracted workspace, leaving v7 frozen."""
from pathlib import Path
import concurrent.futures,datetime,hashlib,importlib.metadata,json,os,platform,shutil,subprocess,sys,time,zipfile
import joblib,numpy as np,pandas as pd,psutil

DEV=Path(__file__).resolve().parents[1];ROOT=DEV.parent
REPLAY=ROOT.parent/'tmp/Paper02_V8_Stage0_20261030'/ROOT.name

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def freeze():
    for d in ('audit','audit/stage0_logs','before','code','data','results','figures','tables','public_release'):(DEV/d).mkdir(parents=True,exist_ok=True)
    path=DEV/'before/freeze.json'
    if not path.exists():
        shutil.copytree(ROOT/'paper',DEV/'before/paper',dirs_exist_ok=True)
        shutil.copytree(ROOT/'tools',DEV/'before/tools',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('MANIFEST.json','paper_config.json'):shutil.copy2(ROOT/name,DEV/'before'/name)
        shutil.copy2(ROOT/'output/pdf/UAV_Energy_Conserving_Compression.pdf',DEV/'before/before.pdf')
        body=(ROOT/'paper/iccies_body.tex').read_text(encoding='utf-8')
        front=body.split('\\input{v7_numbers.tex}')[0]
        (DEV/'before/frontmatter.tex').write_text(front,encoding='utf-8')
        legacy={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'development_v7').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        protected=json.loads((ROOT/'development_v7/before/freeze.json').read_text())['protected']
        write(path,dict(v7=legacy,protected=protected,opening_sha256=sha(DEV/'before/frontmatter.tex'),created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    versions={p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy','joblib','matplotlib','psutil','zfpy','zstandard','numba','PyMuPDF','requests','pysz')}
    write(DEV/'audit/environment.json',dict(python=sys.version,platform=platform.platform(),libraries=versions,seed=20261030,initial_available_ram_bytes=psutil.virtual_memory().available))

def extract():
    archive=DEV/'before/v7_source_evidence.zip'
    if not archive.exists():shutil.copy2(ROOT/'output/Paper_02_ICCIES2027_Source_and_Evidence.zip',archive)
    REPLAY.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for m in z.infolist():assert (REPLAY.parent/m.filename).resolve().is_relative_to(REPLAY.parent.resolve())
        z.extractall(REPLAY.parent)
    return archive

def call(script,*extra):
    label=Path(script).stem+('_'+'_'.join(extra) if extra else '')
    cmd=[sys.executable,'-X','utf8','-u',str(REPLAY/'development_v7/code'/script),*extra]
    env=os.environ.copy()
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
    print('START',label,flush=True)
    with (DEV/'audit/stage0_logs'/(label+'.txt')).open('w',encoding='utf-8') as log:
        proc=subprocess.Popen(cmd,cwd=REPLAY,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        for line in proc.stdout:
            log.write(line);log.flush()
            if line.strip():print(label+': '+line.rstrip(),flush=True)
        if proc.wait():raise RuntimeError(label+' failed')
    print('DONE',label,flush=True)

def batch(tasks):
    workers=3 if psutil.virtual_memory().available>2*2**30 else 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results=[pool.submit(call,script,*extra) for script,extra in tasks]
        for result in results:result.result()

def compare():
    before=ROOT/'development_v7';after=REPLAY/'development_v7';tables=[];csvs=[]
    for name in ('profiles','baselines','distributions','ablation','lookahead','long','loss'):
        a=(before/'tables'/(name+'.tex')).read_text(encoding='utf-8');b=(after/'tables'/(name+'.tex')).read_text(encoding='utf-8')
        assert a==b,('Table mismatch',name)
        tables.append(dict(table=name,identical=True))
    for name in ('main_cases','frozen_path_widths','independent_segments','ablation_cases','sensitivity_cases','lookahead_cases','long_cases','loss_cases','cluster_intervals','distributions','support_and_violations','paired_wilcoxon_holm','lookahead_headroom','sensitivity_summary'):
        a=pd.read_csv(before/'results'/(name+'.csv'),dtype={'flight_id':str,'group_id':str},low_memory=False)
        b=pd.read_csv(after/'results'/(name+'.csv'),dtype={'flight_id':str,'group_id':str},low_memory=False)
        pd.testing.assert_frame_equal(a,b,check_dtype=False,atol=1e-10,rtol=1e-10)
        csvs.append(dict(file=name,rows=len(a),match=True))
    a=joblib.load(before/'data/main_wires.joblib');b=joblib.load(after/'data/main_wires.joblib')
    assert a.keys()==b.keys() and all(a[k]==b[k] for k in a)
    f=pd.read_csv(after/'results/main_cases.csv');ab=pd.read_csv(after/'results/ablation_cases.csv');h=pd.read_csv(after/'results/lookahead_cases.csv');o=pd.read_csv(REPLAY/'development_v6/results/oracle.csv')
    strict=f[f.method=='DBG_fixed_medium'];outside=strict[strict.dataset!='Solar']
    assert len(strict)==718 and int((outside.status=='OK').sum())==702
    assert int(ab[ab.variant=='CheckBeforeRounding'].energy_violation.sum())==36
    assert int((o.greedy_status=='OK').sum())==715
    assert all(int((z.status=='OK').sum())==718 for _,z in h.groupby('extra_steps'))
    fixed=f[f.method.str.startswith('DBG_fixed_')];assert int((fixed.status=='OK').sum())==2133 and int((fixed.status!='OK').sum())==21
    return dict(passed=True,inputs=718,fixed_wires_byte_identical=2133,fixed_refusals=21,all_main_wires_byte_identical=len(a),medium_non_solar_complete='702/706',check_before_rounding_energy_violations=36,greedy_30s_complete=715,lookahead_30s_complete=718,tables_2_8=tables,numerical_files=csvs)

def main():
    start=time.perf_counter();freeze();archive=extract()
    proc=psutil.Process();allowed=proc.cpu_affinity();chosen=[x for x in (0,2,4) if x in allowed]
    if chosen:proc.cpu_affinity(chosen)
    write(DEV/'audit/stage0_progress.json',dict(status='running',start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),archive_sha256=sha(archive),replay_root=str(REPLAY)))
    batch([('preflight.py',()),('experiments.py',()),('extended.py',('ablation',))])
    batch([('extended.py',('delta_ablation',)),('extended.py',('lookahead',)),('extended.py',('sensitivity',)),('long_and_loss.py',('long',)),('long_and_loss.py',('loss',)),('validate.py',()),('statistical_analysis.py',())])
    call('profile_cpu.py');call('report.py');call('quality.py','metrics')
    result=compare();result['elapsed_s']=time.perf_counter()-start
    write(DEV/'audit/step0.json',result);write(DEV/'audit/stage0_progress.json',dict(status='passed',elapsed_s=result['elapsed_s']))
    (DEV/'audit/STEP0_VI.md').write_text('# Tái lập vòng 2\n\nĐã chạy lại v7 trong gói giải nén tách biệt và giữ nguyên bản v7.\n\n- 718 đầu vào, 2.133 wire fixed giống từng byte và 21 refusal.\n- 702/706 medium ngoài Solar, 36 energy violations của check-before-rounding.\n- 715 greedy so với 718 lookahead trên prefix 30 s.\n- Tables 2–8 và 14 file kết quả số khớp, toàn bộ 9.989 wire chính giống từng byte.\n- Không có sai khác số cần chỉnh hoặc giấu. CPU được chạy lại nhưng không dùng để đòi byte-identical về thời gian.\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('tables_2_8','numerical_files')},indent=2),flush=True)

if __name__=='__main__':main()
