"""Package code and bounded research evidence, excluding runtimes and original attachments."""
from pathlib import Path
import hashlib
import json
import zipfile
from datetime import datetime, timezone


def package(root):
    root=Path(root).resolve()
    files=set()
    for folder in ('firelab','web','tests','docs','configs','cases','scripts','data/reference'):
        files.update(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files.update(p for p in root.iterdir() if p.is_file() and p.suffix in ('.md','.txt','.ps1','.cmd'))
    for pattern in ('reports/verification*.json','reports/http_verification.json','reports/tests_final.log','reports/full_design_preparation.json',
                    'reports/fields/*.json','reports/verification/*.json','reports/acoustics/*.json',
                    'runs/openfoam_v2412_taylor_green_spatial/convergence.*',
                    'runs/openfoam_v2412_taylor_green_temporal/temporal_convergence.*',
                    'runs/fds_steckler_full_ext4_omp8/run_manifest.json',
                    'data/reference_manifest.json','data/source_manifest.json'):
        files.update(root.glob(pattern))
    transport_pointer=root/'runs/latest.json'
    if transport_pointer.is_file():
        files.add(transport_pointer)
        latest=json.loads(transport_pointer.read_text(encoding='utf-8'))
        run_id=latest.get('run_id')
        if run_id and Path(run_id).name==run_id:
            files.update(p for p in (root/'runs'/run_id).rglob('*')
                         if p.is_file() and p.suffix!='.zip')
    pointer=root/'runs/campaign_latest.json'
    if pointer.is_file():
        files.add(pointer)
        cid=json.loads(pointer.read_text(encoding='utf-8'))['campaign_id']
        directory=root/'runs'/cid
        files.update(p for p in directory.iterdir() if p.is_file() and p.suffix!='.zip')
        result=json.loads((directory/'campaign.json').read_text(encoding='utf-8'))
        for case in result['cases']:
            if not case.get('native'):continue
            run=Path(case['run_directory'])
            files.update(p for p in run.iterdir() if p.is_file() and (p.suffix in ('.fds','.csv','.out','.json')))
    preparation=root/'reports/full_design_preparation.json'
    if preparation.exists():
        cid=json.loads(preparation.read_text())['campaign_id']
        files.update(p for p in (root/'runs'/cid).iterdir() if p.is_file() and p.suffix in ('.json','.csv','.md'))
    inventory=[]
    output=root/'firefield_implementation.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p in sorted(files):
            relative=p.relative_to(root).as_posix()
            data=p.read_bytes()
            archive.writestr(relative,data)
            inventory.append({'path':relative,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        archive.writestr('DELIVERY_MANIFEST.json',json.dumps({
            'created_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'code + assumed-scenario native results; not experimental validation',
            'excluded':['solver binaries','original user attachments','large native binary fields'],
            'portability':'install requirements and official FDS/OpenFOAM runtimes; original absolute provenance paths are retained',
            'files':inventory},ensure_ascii=False,indent=2))
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for item in inventory:
            assert hashlib.sha256(archive.read(item['path'])).hexdigest()==item['sha256']
    return {'path':str(output),'files':len(inventory),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__=='__main__':
    print(json.dumps(package(Path(__file__).resolve().parents[1]),ensure_ascii=False,indent=2))
