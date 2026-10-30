"""Post-result diagnostics for the three separately scoped UAV articles.

Declared before calculation: seed 20261031; P1 primary-minus-fixed-default
30 s group MSE, 100000 sign flips, 10000 group bootstrap draws and Holm over
three collections; P2 pooled terminal events at Bernoulli .1, m=1, uncoded,
mean/sample SD over 30 repetitions; P3 observed date-balanced coverage >=.9
and acceptance >=.1 on the retained radius-scale grid, without calibration.
No fitted model, label, split, primary comparison family or radius is changed.
"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

SEED=20261031

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def paper1(dev):
    rng=np.random.default_rng(SEED);rows=[];inputs={}
    for ds,expected in [('IDF',38),('CMU',18),('AMOVFLY',21)]:
        path=dev/f'results/{ds}_groups.csv';inputs[str(path.relative_to(dev))]=sha(path)
        f=pd.read_csv(path);f=f.query('horizon_s==30 and method in ["Primary","FixedDefault"]')
        assert f.seed.nunique()==10
        grouped=f.groupby(['group_id','method']).mse.mean().unstack();assert len(grouped)==expected and grouped.notna().all().all()
        a=grouped.Primary.to_numpy();b=grouped.FixedDefault.to_numpy();delta=a-b;n=len(a)
        signs=rng.choice([-1,1],(100000,n));p=(1+np.count_nonzero(np.abs((signs*delta).mean(1))>=abs(delta.mean())-1e-15))/100001
        ids=rng.integers(0,n,(10000,n));boot=np.sqrt(a[ids].mean(1))-np.sqrt(b[ids].mean(1));lo,hi=np.quantile(boot,[.025,.975])
        rows.append(dict(dataset=ds,groups=n,delta_RMSE_Wh=float(np.sqrt(a.mean())-np.sqrt(b.mean())),low95=float(lo),high95=float(hi),p_signflip=float(p)))
    order=np.argsort([r['p_signflip'] for r in rows]);previous=0.
    for rank,index in enumerate(order):
        previous=min(1.,max(previous,rows[index]['p_signflip']*(3-rank)));rows[index]['p_holm']=previous
    return dict(comparisons=rows,inputs=inputs,family=3,bootstrap_replicates=10000,sign_flips=100000,assumptions='Conditional on fitted outer models, acquisition-group resampling and sign symmetry; seed losses averaged within each group.')

def paper2(dev):
    path=dev/'results/loss_record_replicates.parquet'
    f=pd.read_parquet(path,filters=[('dataset','!=','Solar'),('m','==',1),('protection','==','none'),('channel','==','Bernoulli'),('rate','==',.1)],columns=['repeat','terminal_erased','terminal_detected','footer_delivered'])
    assert len(f)==706*30 and not (f.terminal_detected&~f.terminal_erased).any()
    rows=[]
    for rep,g in f.groupby('repeat'):
        conditional=g.terminal_erased&g.footer_delivered
        assert conditional.sum()>0 and g.terminal_erased.sum()>0
        assert (g.terminal_detected==conditional).all()
        rows.append(dict(repeat=int(rep),terminal_erased=int(g.terminal_erased.sum()),conditional_events=int(conditional.sum()),detected=int(g.terminal_detected.sum()),conditional_rate=float(g.terminal_detected.sum()/conditional.sum()),unconditional_rate=float(g.terminal_detected.sum()/g.terminal_erased.sum())))
    z=pd.DataFrame(rows);assert len(z)==30
    return dict(inputs={str(path.relative_to(dev)):sha(path)},configuration='Non-Solar, Bernoulli p=.1, one checkpoint/datagram, no protection; pooled terminal events within each repeat',replicates=rows,conditional_mean=float(z.conditional_rate.mean()),conditional_SD=float(z.conditional_rate.std(ddof=1)),unconditional_mean=float(z.unconditional_rate.mean()),unconditional_SD=float(z.unconditional_rate.std(ddof=1)))

def paper3(dev):
    path=dev/'results/selective_summary.csv';f=pd.read_csv(path);f=f.query('scope=="date_excluded" and method=="RadiusScale"');rows=[]
    for ds,g in f.groupby('dataset'):
        assert g.alpha.is_unique and g.coverage.between(0,1).all() and g.acceptance.between(0,1).all()
        eligible=g[g.coverage>=.9];joint=g[(g.coverage>=.9)&(g.acceptance>=.1)]
        rows.append(dict(dataset=ds,grid_points=len(g),joint_points=len(joint),maximum_acceptance_at_coverage90=float(eligible.acceptance.max()),coverage_threshold=.9,acceptance_threshold=.1,scale_min=float(g.alpha.min()),scale_max=float(g.alpha.max())))
    assert len(rows)==2
    return dict(inputs={str(path.relative_to(dev)):sha(path)},collections=rows,interpretation='Post-result descriptive feasibility audit on the evaluated scale grid and date-balanced metrics, not threshold tuning or an independent coverage guarantee.')

def run():
    dev=Path(__file__).resolve().parents[1];root=dev.parent
    number=json.loads((root/'paper_config.json').read_text(encoding='utf8'))['paper_number']
    result={1:paper1,2:paper2,3:paper3}[number](dev)
    assert all(sha(dev/name)==digest for name,digest in result['inputs'].items())
    result.update(passed=True,paper=number,analysis_seed=SEED if number==1 else None,status='exploratory post-result supplement; original results unchanged')
    if number==2:result['source_simulation_seed']=json.loads((dev/'results/loss_gate.json').read_text())['seed']
    (dev/'results/followup_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf8')
    return result

if __name__=='__main__':print(json.dumps(run(),indent=2))
