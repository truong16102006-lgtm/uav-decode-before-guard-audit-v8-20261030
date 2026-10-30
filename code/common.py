"""Round-2 evidence paths, frozen input access and explicit Step-0 gate."""
from pathlib import Path
import os,json,hashlib
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import numpy as np,pandas as pd,joblib
DEV=Path(__file__).resolve().parents[1];ROOT=DEV.parent;SEED=20261030

def write(name,obj):
    p=DEV/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

def step0():
    p=DEV/'audit/step0.json'
    assert p.exists() and json.loads(p.read_text(encoding='utf-8'))['passed'],'Complete and report isolated Step 0 before any new v8 numerical experiment'

def records():return joblib.load(ROOT/'development_v4/data/benchmark_signals.joblib')
def full_records():return joblib.load(ROOT/'development_v7/data/full_episodes.joblib')
def identity(r):return {k:r[k] for k in ['dataset','flight_id','group_id']}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def dump_atomic(obj,path):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.partial')
    joblib.dump(obj,temporary,compress=3);os.replace(temporary,path)

def scope_records(scope):
    population=records() if scope=='120' else full_records();out=[]
    for r in population:
        limit=1800. if r['dataset']=='Solar' and scope!='120' else 120. if scope=='120' else float(r['t'][-1])
        use=r['t']<=limit
        out.append(dict(r,t=np.asarray(r['t'][use],dtype=np.float64),p=np.asarray(r['p'][use],dtype=np.float64)))
    return out

def balanced_mean(frame,column):
    """Equal sources, clusters within source and records within cluster."""
    return float(frame.groupby(['dataset','group_id'])[column].mean().groupby('dataset').mean().mean())
