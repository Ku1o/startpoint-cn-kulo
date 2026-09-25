"""Install one fully prepared local candidate; never sync runtime or deploy."""
import argparse,json,hashlib,shutil
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
def sha(b):return hashlib.sha256(b).hexdigest()
ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);args=ap.parse_args()
w=args.work.resolve();report=json.loads((w/'report.json').read_text('utf-8'))
paths=sorted(p for p in (w/'files').rglob('*') if p.is_file())
for src in paths:
    rel=src.relative_to(w/'files').as_posix();target=REPO/rel
    assert target.resolve().is_relative_to(REPO.resolve()) and '.cdn' not in target.parts
    expected=report['server_preimages'].get(rel)
    assert (sha(target.read_bytes()) if target.exists() else None)==expected, f'Preimage drift: {rel}'
for src in paths:
    rel=src.relative_to(w/'files');target=REPO/rel
    if target.exists():
        backup=w/'before'/rel;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(target,backup)
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
    assert sha(target.read_bytes())==sha(src.read_bytes())
audit=REPO/'assets/asset-patch/audit/midautumn-national-2026'
audit.mkdir(parents=True,exist_ok=True)
for info in report['asset_sources'].values():
    archive=Path(info['archive'])
    try:info['archive']=archive.relative_to(REPO).as_posix()
    except ValueError:info['archive']='.cdn/cn/'+archive.parent.name+'/'+archive.name
(audit/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Installed',len(paths),'candidate files in source only; preimages backed up under --work/before')
