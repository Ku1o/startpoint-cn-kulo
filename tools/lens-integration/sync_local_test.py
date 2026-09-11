"""Apply an explicitly hashed local-test plan, backing up all overwritten files."""
import argparse
import hashlib
import json
import shutil
import socket
import sqlite3
from datetime import datetime
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
RUNTIME=Path('F:/startpoint-cn-main')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True)
    w=ap.parse_args().work.resolve();rows=json.loads((w/'local-sync-plan.json').read_text('utf-8'))
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(('127.0.0.1',8001))==0:raise RuntimeError('server is already running; stop exact instance before syncing')
    for row in rows:
        name=row['path'];source=REPO/name;target=RUNTIME/name
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert target.resolve().is_relative_to(RUNTIME.resolve())
        assert '.cdn' not in Path(name).parts and not target.resolve().is_relative_to((RUNTIME/'.cdn').resolve())
        assert name not in ('.env',) and not name.startswith('.database/')
        assert sha(source)==row['source_sha256'],name
        assert sha(target)==row['runtime_before_sha256'],name
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    backup=RUNTIME/'.codex-backups'/f'{stamp}-lens0907-0908-local-test'
    backup.mkdir(parents=True,exist_ok=False)
    database=RUNTIME/'.database/wdfp_data.db'
    db_backup=backup/'database/wdfp_data.db';db_backup.parent.mkdir()
    # SQLite backup includes any WAL content without changing the original DB.
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as source:
        with sqlite3.connect(db_backup) as dest:
            source.backup(dest)
            assert dest.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    print('Database snapshot complete',flush=True)
    original_env_sha=sha(RUNTIME/'.env')
    for row in rows:
        name=row['path'];target=RUNTIME/name
        if row['changed'] and target.exists():
            saved=backup/'files'/name;saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(target,saved);assert sha(saved)==row['runtime_before_sha256']
    (backup/'sync-plan.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf-8')
    for row in sorted(rows,key=lambda r:(r['path']=='assets/asset-patch/manifest.json',r['path'])):
        if not row['changed']:continue
        name=row['path'];target=RUNTIME/name;target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_name(target.name+'.lens-sync-tmp');assert not temp.exists()
        shutil.copyfile(REPO/name,temp);assert sha(temp)==row['source_sha256'];temp.replace(target)
    for row in rows:assert sha(RUNTIME/row['path'])==row['source_sha256']
    assert sha(RUNTIME/'.env')==original_env_sha
    result={'status':'synced','backup':str(backup),'database_backup':str(db_backup),'files':rows,
        'copied':sum(r['changed'] for r in rows),'unchanged':sum(not r['changed'] for r in rows),
        'env_unchanged':True,'database_replaced':False,'pristine_cdn_written':False,
        'authorization':'User explicitly requested local synchronization and server execution for testing; no commit or cloud deployment.'}
    (w/'local-sync-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
