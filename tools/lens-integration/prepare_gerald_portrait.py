"""Prepare Gerald's portrait subpackage; never edit a manifest or runtime store."""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ProcessPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import zlib

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/fantasy-gauntlet-mod-tools'))
import wf_mod_tool as core
import wf_assets
import wf_atf
from PIL import Image

PREFIX = 'character/unicorn_lancer_rose/ui/'
ROOTS = {'common': 'upload', 'medium': 'medium_upload', 'android': 'android_upload', 'ios': 'ios_upload'}
ROWS = {
    'master/generated/character_image.orderedmap': ['129992'],
    'master/character/full_shot_image_attribute.orderedmap': ['129992'],
    'master/generated/trimmed_image.orderedmap': [PREFIX + n + f'_{i}' for n in ('full_shot_1440_1920', 'skill_cutin') for i in (0, 1)],
}
PAIRS = ('battle_control_board', 'battle_member_status', 'cutin_skill_chain', 'full_shot_1440_1920',
         'skill_cutin', 'square', 'square_132_132', 'square_round_136_136', 'square_round_95_95',
         'thumb_level_up', 'thumb_party_main', 'thumb_party_unison')
ASSETS = {PREFIX+n+f'_{i}.png': 'medium' for n in PAIRS for i in (0, 1)}
ASSETS[PREFIX+'illustration_setting_sprite_sheet.png'] = 'medium'
ASSETS[PREFIX+'illustration_setting_sprite_sheet.atlas.amf3.deflate'] = 'common'
ASSETS.update({PREFIX+f'skill_cutin_{i}.atf.deflate': 'android' for i in (0, 1)})


def sha(data): return hashlib.sha256(data).hexdigest()
def jsonbytes(value): return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
def relative(logical):
    h = core.sha1_path(logical)
    return h[:2]+'/'+h[2:]
def member(root, logical): return 'production/'+ROOTS[root]+'/'+relative(logical)
def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, f'existing output differs: {path}'
    else:
        with path.open('xb') as f: f.write(raw)
    assert path.read_bytes() == raw
def rawmap(raw):
    om = core.read_orderedmap_raw_rows_from_bytes(raw)
    assert len(om.keys) == len(set(om.keys)) == len(om.rows)
    return dict(zip(om.keys, om.rows))
def packmap(rows):
    return core.build_orderedmap_raw_rows(core.OrderedMap('[portrait]', list(rows), list(rows.values()), Path('[memory]')))


def read_active(requested):
    manifest_path = REPO/'assets/asset-patch/manifest.json'
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    enabled = sorted((p for p in manifest['patches'] if p.get('enabled')), key=lambda p:tuple(map(int,p['version'].split('.'))))
    tail = '1.4.54'
    archives = []
    for p in enabled:
        assert p['depends_on'] == tail
        tail = p['version']
        archives.extend((p,n) for n in (p.get('chain') or [p['archive']]))
    assert tail == manifest['cdn_version'] and tail in ('1.4.104','1.4.105'), ('chain advanced',tail)
    found, evidence = {}, {}
    for patch,name in reversed(archives):
        path = REPO/'assets/asset-patch/active'/name
        with zipfile.ZipFile(path) as z:
            wanted = (set(requested)-set(found)) & set(z.namelist())
            if not wanted: continue
            receipt = next((r for r in patch.get('archive_integrity',[]) if r['name']==name), None)
            if receipt:
                assert path.stat().st_size == receipt['size'] and sha(path.read_bytes()) == receipt['sha256']
            for n in sorted(wanted):
                raw = z.read(n); found[n] = raw
                evidence[n] = {'archive':str(path),'version':patch['version'],'sha256':sha(raw),'size':len(raw)}
        if set(found)==set(requested): break
    assert set(found)==set(requested), ('missing from enabled active chain',set(requested)-set(found))
    assert manifest_path.read_bytes()==manifest_raw, 'manifest changed during sparse read'
    return found, evidence, manifest_raw, tail


def ios_job(job):
    logical, png, android = job
    android_plain = wf_atf.inflate(android)
    ios_plain = wf_atf.build_cutin_atf_ios(png, android_plain)
    pair = wf_atf.validate_cutin_platform_pair(android_plain, ios_plain, png)
    parsed = wf_atf.parse_atf(ios_plain)
    for level, raw in enumerate(parsed['pairs']):
        w,h=max(parsed['w']>>level,1),max(parsed['h']>>level,1)
        assert len(wf_atf.decode_etc2_rgba(raw,w,h))==w*h*4
    stored = wf_atf.deflate(ios_plain)
    assert wf_atf.inflate(stored)==ios_plain
    return logical,stored,{'pair':pair,'png_sha256':sha(png),'android_sha256':sha(android),
                           'ios_sha256':sha(stored),'all_ios_mips_decoded':True}


def prepare(pack, work):
    assert not (work/'prepared.json').exists(), 'use a fresh work directory'
    checksum_count = 0
    for line in (pack/'SHA256SUMS').read_text('utf-8-sig').splitlines():
        digest,name=line.split(maxsplit=1)
        path=(pack/name.lstrip('*')).resolve()
        assert path.is_relative_to(pack)
        assert sha(path.read_bytes())==digest
        checksum_count+=1
    m=json.loads((pack/'asset-manifest.json').read_text('utf-8-sig'))
    rows=json.loads((pack/'portrait-rows.json').read_text('utf-8-sig'))
    assert len(m['assets'])==28 and {a['logical'] for a in m['assets']}==set(ASSETS)
    assert set(rows)==set(ROWS) and all(set(rows[n])==set(ROWS[n]) for n in ROWS)
    data,logicals={},{}
    with zipfile.ZipFile(pack/'portrait-assets.zip') as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))==28
        assert set(z.namelist())=={a['member'] for a in m['assets']}
        for a in m['assets']:
            name=a['logical']; root=ASSETS[name]; n=member(root,name)
            assert a['root']==root and a['relative']==relative(name) and a['member']==n
            raw=z.read(n)
            assert len(raw)==a['size'] and sha(raw)==a['sha256']
            if name.endswith('.png'):
                plain=wf_assets.png_decode_stored(raw)
                with Image.open(io.BytesIO(plain)) as im: im.verify()
                with Image.open(io.BytesIO(plain)) as im: im.load()
            data[n]=raw; logicals[n]={'root':root,'logical':name}
    requested=dict(logicals)
    for logical in ROWS: requested[member('common',logical)]={'root':'common','logical':logical}
    for i in (0,1):
        logical=PREFIX+f'skill_cutin_{i}.atf.deflate'
        requested[member('ios',logical)]={'root':'ios','logical':logical}
    before,sources,manifest_raw,tail=read_active(requested)
    row_report=[]
    for logical,keys in ROWS.items():
        n=member('common',logical); old=rawmap(before[n]); new=dict(old)
        assert set(keys)<=set(old)
        for k in keys:
            new[k]=base64.b64decode(rows[logical][k],validate=True)
            row_report.append({'table':logical,'key':k,'before_sha256':sha(old[k]),'after_sha256':sha(new[k])})
        merged=packmap(new) if new!=old else before[n]
        check=rawmap(merged)
        assert list(check)==list(old) and check==new
        assert all(check[k]==v for k,v in old.items() if k not in keys)
        data[n]=merged; logicals[n]=requested[n]
    print('Prepared donor PNG/Android assets and isolated merges; encoding two iOS textures with max_workers=4.',flush=True)
    jobs=[]
    for i in (0,1):
        logical=PREFIX+f'skill_cutin_{i}.atf.deflate'
        png=wf_assets.png_decode_stored(data[member('medium',PREFIX+f'skill_cutin_{i}.png')])
        jobs.append((logical,png,data[member('android',logical)]))
    with ProcessPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(ios_job,jobs))
    pair_reports=[]
    for logical,stored,receipt in results:
        n=member('ios',logical);data[n]=stored;logicals[n]=requested[n]
        pair_reports.append({'logical':logical,**receipt})
    assert len(data)==33
    for n,raw in before.items():save(work/'before'/n,raw)
    for n,raw in data.items():save(work/'after'/n,raw)
    geometry=[]
    character=rawmap(data[member('common','master/generated/character_image.orderedmap')])
    for level,raw in rawmap(character['129992']).items():
        dimensions=list(map(int,zlib.decompress(raw).decode().split(',')))
        png=wf_assets.png_decode_stored(data[member('medium',PREFIX+f'full_shot_1440_1920_{level}.png')])
        with Image.open(io.BytesIO(png)) as im:
            geometry.append({'level':level,'png_size':list(im.size),'character_image':dimensions,
                             'policy':'preserve exact donor rows; inherited width/height mismatch; device acceptance pending'})
    report={'base_version':'1.4.104','version':'1.4.105','archive_sequence':2,'source_tail_at_prepare':tail,
            'source_manifest_sha256':sha(manifest_raw),'donor_manifest_sha256':sha((pack/'asset-manifest.json').read_bytes()),
            'donor_rows_sha256':sha((pack/'portrait-rows.json').read_bytes()),'checksums_verified':checksum_count,
            'files':[{'member':n,**logicals[n],'size':len(raw),'sha256':sha(raw),'before_sha256':sha(before[n])} for n,raw in sorted(data.items())],
            'table_rows':row_report,'unrelated_rows_and_order_preserved':True,'ios':pair_reports,'geometry':geometry,
            'sources':sources,'save_impact':'Only art and existing character display rows; no saved IDs, schema or progress changes.',
            'source_manifest_modified':False,'runtime_modified':False,'published':False,'device_tested':False}
    save(work/'prepared.json',jsonbytes(report))
    print(json.dumps({'prepared':str(work/'prepared.json'),'files':len(data),'ios_pairs':len(pair_reports)},ensure_ascii=False),flush=True)


def emit(work,output):
    report=json.loads((work/'prepared.json').read_text('utf-8'))
    assert output.name=='pinball-1.4.104-1.4.105-2-gerald-portrait.zip'
    assert output.parent==(REPO/'assets/asset-patch/active').resolve()
    assert not output.exists(), 'never replace an existing archive'
    data={x['member']:(work/'after'/x['member']).read_bytes() for x in report['files']}
    for x in report['files']:assert len(data[x['member']])==x['size'] and sha(data[x['member']])==x['sha256']
    before,_,_,_=read_active(data)
    assert all(sha(before[x['member']])==x['before_sha256'] for x in report['files']), 'target preimage changed'
    for path in output.parent.glob('pinball-1.4.104-1.4.105-*.zip'):
        with zipfile.ZipFile(path) as z:assert not (set(z.namelist()) & set(data)), ('sibling resource collision',path)
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,raw in sorted(data.items()):
            info=zipfile.ZipInfo(n,(2026,9,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    archive=buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and len(z.namelist())==33 and set(z.namelist())==set(data)
        assert all(z.read(n)==raw for n,raw in data.items())
        for i in (0,1):
            logical=PREFIX+f'skill_cutin_{i}.atf.deflate'
            wf_atf.validate_cutin_platform_pair(wf_atf.inflate(z.read(member('android',logical))),wf_atf.inflate(z.read(member('ios',logical))),
                wf_assets.png_decode_stored(z.read(member('medium',PREFIX+f'skill_cutin_{i}.png'))))
    save(output,archive)
    report['archive']={'name':output.name,'size':len(archive),'sha256':sha(archive),'members':33,'files':sorted(data)}
    audit=REPO/'assets/asset-patch/audit/gerald-portrait-1.4.105'
    save(audit/'report.json',jsonbytes(report))
    save(audit/'archive-integrity.json',jsonbytes(report['archive']))
    print(json.dumps({'archive':str(output),'audit':str(audit),**report['archive']},ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--emit-archive',type=Path)
    args=p.parse_args();work=args.work.resolve();cdn=(REPO/'.cdn').resolve()
    assert work.is_relative_to(Path('F:/codex/work').resolve()) and not work.is_relative_to(cdn)
    if args.emit_archive:emit(work,args.emit_archive.resolve())
    else:
        assert args.package is not None
        prepare(args.package.resolve(),work)


if __name__=='__main__':main()
