from pathlib import Path
import argparse,subprocess,sys,json,hashlib,shutil
p=argparse.ArgumentParser();p.add_argument('--paper-root',required=True,type=Path);a=p.parse_args();r=a.paper_root.resolve();release=Path(__file__).parent.resolve()
manifest=json.loads((release/'configuration/local_input_manifest.json').read_text())
for name,entry in manifest.items():
 f=r/name;assert f.is_file(),f;assert hashlib.file_digest(f.open('rb'),'sha256').hexdigest()==entry['sha256'],f
dev=r/'development_v8';(dev/'code').mkdir(parents=True,exist_ok=True);(dev/'audit').mkdir(exist_ok=True)
for f in (release/'code').glob('*.py'):shutil.copy2(f,dev/'code'/f.name)
shutil.copy2(release/'audit/SZ3_reference_primary.json',dev/'audit/SZ3_reference_primary.json')
for name in ['PROTOCOL.md','requirements.txt']:
 if (release/name).exists():shutil.copy2(release/name,dev/name)
subprocess.run([sys.executable,'-X','utf8',str(dev/'code/run_suite.py'),'--repeat-step0'],cwd=r,check=True)
