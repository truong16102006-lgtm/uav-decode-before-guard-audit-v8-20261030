"""Finish the current run after the documented Solar coordinate correction."""
import subprocess,sys,time
import psutil
from common import *


def call(name,*args):
    path=DEV/'audit'/('finish_'+name.removesuffix('.py')+'.log')
    with path.open('w',encoding='utf8') as log:
        process=subprocess.Popen([sys.executable,'-X','utf8','-u',str(DEV/'code'/name),*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        child=psutil.Process(process.pid)
        if 0 in child.cpu_affinity():child.cpu_affinity([0])
        print('START',name,process.pid,flush=True)
        if process.wait():raise RuntimeError('Inspect '+str(path))
    print('DONE',name,flush=True)


def run():
    step0()
    workers={23572:'loss_v8.py',26144:'solar_stream.py'}
    while True:
        active=[]
        for pid,name in workers.items():
            try:
                process=psutil.Process(pid)
                if any(s.endswith(name) for s in process.cmdline()):active.append(pid)
            except psutil.NoSuchProcess:pass
        write('audit/finish_progress.json',dict(stage='waiting_for_loss_and_corrected_solar',active_PIDs=active))
        if not active:break
        time.sleep(2)
    for name in ['main_120_gate','main_full_gate','baselines_gate','drift_gate','receiver_gate','heatmap_gate','preprocessing_gate','solar_gate','loss_gate']:
        result=json.loads((DEV/'results'/f'{name}.json').read_text(encoding='utf8'));assert result['completed'],name
    write('audit/finish_progress.json',dict(stage='statistics_and_document'))
    for name,args in [('statistics_v8.py',()),('extra_diagnostics.py',('timings',)),('report_v8.py',()),('workflow_v8.py',()),('manuscript_v8.py',()),('finalize_v8.py',('--references-only',)),('validate_v8.py',())]:call(name,*args)
    path=ROOT/'paper_config.json';config=json.loads(path.read_text(encoding='utf8'))
    config.update(research_version=8,manuscript_revision='ICCIES2027_Methods_V8_20261030',reference_count=29,contribution_extension='development_v8/PROTOCOL.md',author_list_status='Draft author fields retained; Zenodo deferred by user')
    path.write_text(json.dumps(config,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/build.py')],cwd=ROOT,check=True)
    call('finalize_v8.py')
    write('audit/finish_progress.json',dict(stage='rendered_pending_manual_visual_review'))


if __name__=='__main__':run()
