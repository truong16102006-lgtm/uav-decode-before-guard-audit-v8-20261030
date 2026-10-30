"""Resume all round-2 experiments after an isolated legacy reproduction gate."""
import argparse,subprocess,sys,concurrent.futures,time
from common import *
import psutil

def call(script,*args,core=0):
    label=script.removesuffix('.py')+('_'+'_'.join(args) if args else '')
    path=DEV/'audit'/f'{label}_run.log'
    with path.open('w',encoding='utf8') as log:
        p=subprocess.Popen([sys.executable,'-X','utf8','-u',str(DEV/'code'/script),*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        child=psutil.Process(p.pid)
        if script!='preflight_v7.py' and core in child.cpu_affinity():child.cpu_affinity([core])
        print('START',label,'PID',p.pid,flush=True)
        result=p.wait()
    if result:raise RuntimeError(f'{label} failed; inspect {path}')
    print('DONE',label,flush=True)

def batch(jobs):
    count=3 if psutil.virtual_memory().available>2.5*2**30 else 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
        futures=[pool.submit(call,*job,core=[0,2,4][j%3]) for j,job in enumerate(jobs)]
        for future in futures:future.result()

def run():
    parser=argparse.ArgumentParser();parser.add_argument('--repeat-step0',action='store_true');args=parser.parse_args()
    if args.repeat_step0 or not (DEV/'audit/step0.json').exists():call('preflight_v7.py')
    step0();call('sources.py');call('validate_kernels.py')
    batch([('experiments.py','baselines'),('experiments.py','120'),('experiments.py','full')])
    batch([('extra_diagnostics.py','drift'),('extra_diagnostics.py','receiver'),('extra_diagnostics.py','heatmap')])
    batch([('solar_stream.py',),('preprocessing_v8.py',),('loss_v8.py',)])
    call('statistics_v8.py');call('supplemental_equivalence.py');call('extra_diagnostics.py','timings')
    call('report_v8.py');call('workflow_v8.py');call('manuscript_v8.py');call('finalize_v8.py','--references-only');call('validate_v8.py')
    config_path=ROOT/'paper_config.json'
    config=json.loads(config_path.read_text(encoding='utf8'))
    config.update(research_version=8,manuscript_revision='ICCIES2027_Methods_V8_20261030',
                  reference_count=29,contribution_extension='development_v8/PROTOCOL.md',
                  author_list_status='Draft author fields retained; Zenodo deferred by user')
    config_path.write_text(json.dumps(config,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/build.py')],cwd=ROOT,check=True)
    call('finalize_v8.py')
    print('All numerical stages and PDF render finished. Inspect the final pages before sealing the package.',flush=True)

if __name__=='__main__':run()
