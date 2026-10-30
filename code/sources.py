"""Private local source snapshots, never included in the public code release."""
import hashlib
import shutil
from common import DEV,ROOT,write

SOURCES={
    'pixhawk':'Paper_01_Robust_Energy/research/03_Full240/data/processed/pixhawk.parquet',
    'speedy':'Paper_01_Robust_Energy/research/03_Full240/data/processed/speedy.parquet',
    'cmu':'Paper_03_Measurement_Clocks/development_v2/data/flights.zip',
    'amov':'Paper_04_Drones_Integrated/data/external_amovfly/AMOVFLY_pinned.zip',
    'solar':'Paper_04_Drones_Integrated/data/external_solar/native_power.parquet',
}


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def source_path(key):
    original=ROOT.parent/SOURCES[key]
    local=DEV/'data/source_inputs'/key/original.name
    return local if local.exists() else original


def freeze_sources():
    rows={}
    for key,relative in SOURCES.items():
        original=ROOT.parent/relative
        local=DEV/'data/source_inputs'/key/original.name
        if not local.exists():
            local.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(original,local)
        if original.exists():assert digest(original)==digest(local),('Source snapshot mismatch',key)
        rows[key]=dict(path=local.relative_to(ROOT).as_posix(),bytes=local.stat().st_size,sha256=digest(local),original_workspace_path=relative)
    write('audit/local_source_inputs.json',dict(inputs=rows,scope='Private local reproducibility snapshots; raw archives excluded from public release; source terms retained.'))


if __name__=='__main__':freeze_sources()
