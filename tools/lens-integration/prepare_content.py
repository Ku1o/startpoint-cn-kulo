"""Prepare the approved lens0907 + lens0908 graft against the effective CN chain.

Only writes to --work. It never invokes donor scripts or touches the pristine CDN.
Prepared files are applied by a separate preimage-checked step after validation.
"""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/fantasy-gauntlet-mod-tools'))
import wf_mod_tool as core
import wf_assets
import wf_atf
from PIL import Image

ROOTS = {'common': 'upload', 'medium': 'medium_upload', 'android': 'android_upload', 'ios': 'ios_upload'}
REVERSE_ROOTS = {v: k for k, v in ROOTS.items()}
NEW_IDS = (129992, 139995)
EXCHANGE_UP = (129952, 169980, 169994, 169995, 179981)
ODDS_TABLE = 'master/gacha_odds/cnmod_abyss_limited_gacha_character_5.orderedmap'
NOTE = 'rich_text/cnmod_abyss_limited_gacha_note.html.deflate'


def sha(b): return hashlib.sha256(b).hexdigest()
def readj(p): return json.loads(p.read_text('utf-8-sig'))
def savej(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', 'utf-8')
def hrel(logical):
    h = core.sha1_path(logical)
    return h[:2] + '/' + h[2:]
def member(key): return f'production/{ROOTS[key[0]]}/{key[1]}'
def rawmap(b):
    if b is None: return {}
    obj = core.read_orderedmap_raw_rows_from_bytes(b)
    return dict(zip(obj.keys, obj.rows))
def packmap(rows):
    return core.build_orderedmap_raw_rows(core.OrderedMap('[lens]', list(rows), list(rows.values()), Path('[memory]')))
def csvrows(b): return list(csv.reader(io.StringIO(zlib.decompress(b).decode('utf-8'))))
def packcsv(rows):
    out = io.StringIO(newline='')
    csv.writer(out, lineterminator='\n').writerows(rows)
    return zlib.compress(out.getvalue().encode('utf-8'))


class Chain:
    def __init__(self):
        self.manifest_bytes = (REPO / 'assets/asset-patch/manifest.json').read_bytes()
        self.manifest = json.loads(self.manifest_bytes)
        self.index = {}
        archives = []
        for d in (REPO / '.cdn/cn').resolve().glob('archive-*'):
            for p in d.glob('*.zip'):
                if '-full' in d.name:
                    archives.append((0, p.name, p))
                else:
                    m = re.match(r'pinball-1\.4\.\d+-1\.4\.(\d+)-(\d+)-', p.name)
                    if m and int(m[1]) <= 54:
                        archives.append((int(m[1]), p.name, p))
        ordered = [p for _, _, p in sorted(archives)]
        tail = '1.4.54'
        for patch in sorted((p for p in self.manifest['patches'] if p.get('enabled')), key=lambda p: tuple(map(int, p['version'].split('.')))):
            assert patch['depends_on'] == tail, 'non-contiguous baseline'
            tail = patch['version']
            for n in patch.get('chain') or [patch['archive']]:
                p = REPO / 'assets/asset-patch/active' / n
                receipt = next((x for x in patch.get('archive_integrity', []) if x['name'] == n), None)
                if receipt:
                    assert sha(p.read_bytes()) == receipt['sha256'], f'active archive drift: {n}'
                ordered.append(p)
        assert tail == self.manifest['cdn_version']
        self.tail = tail
        for p in ordered:
            with zipfile.ZipFile(p) as z:
                for n in z.namelist():
                    parts = n.split('/')
                    if len(parts) == 4 and parts[0] == 'production' and parts[1] in REVERSE_ROOTS:
                        self.index[(REVERSE_ROOTS[parts[1]], '/'.join(parts[2:]))] = (p, n)
        self.reads = {}

    def get(self, key):
        loc = self.index.get(key)
        if loc is None: return None
        p, n = loc
        with zipfile.ZipFile(p) as z: b = z.read(n)
        self.reads['|'.join(key)] = {'archive': str(p), 'member': n, 'sha256': sha(b)}
        return b


def merge_node(old, payload, path, changes):
    if isinstance(payload, dict):
        new_rows = payload['__n__']
    else:
        new = base64.b64decode(payload, validate=True)
        try:
            new_rows = {k: base64.b64encode(v).decode() for k, v in rawmap(new).items()}
        except Exception:
            if old == new: return old
            if old is not None:
                try:
                    if csvrows(old) == csvrows(new): return old
                except Exception: pass
            changes.append({'path': path, 'before': sha(old) if old else None, 'after': sha(new)})
            return new
    rows = rawmap(old)
    before = dict(rows)
    for k, v in new_rows.items(): rows[k] = merge_node(rows.get(k), v, path + [k], changes)
    if rows == before: return old
    packed = packmap(rows)
    assert rawmap(packed) == rows
    assert all(rows[k] == v for k, v in before.items() if k not in new_rows)
    return packed


def ios_job(job):
    logical, png, android, output = job
    atf = wf_atf.inflate(android)
    generated = wf_atf.build_cutin_atf_ios(png, atf)
    receipt = wf_atf.validate_cutin_platform_pair(atf, generated, png)
    out = Path(output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(wf_atf.deflate(generated))
    return {'logical': logical, 'path': str(out), 'sha256': sha(out.read_bytes()), 'png_sha256': sha(png), 'pair': receipt}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--donor07', type=Path, required=True)
    ap.add_argument('--donor08', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--decisions', type=Path, required=True)
    args = ap.parse_args()
    work = args.work.resolve()
    assert not work.is_relative_to((REPO / '.cdn').resolve())
    work.mkdir(parents=True, exist_ok=True)
    chain = Chain()
    print(f'Effective chain {chain.tail}, indexed {len(chain.index)} resource locations', flush=True)
    assets, logicals, source_receipts, server, before_server, table_payloads = {}, {}, [], {}, {}, []
    changes = []

    def get_server(rel):
        if rel not in server:
            p = REPO / 'assets' / rel
            b = p.read_bytes() if p.exists() else None
            before_server[rel] = b
            server[rel] = json.loads(b) if b else {}
        return server[rel]

    for donor in [args.donor07, args.donor08]:
        for line in (donor / '_work/asset_inventory.txt').read_text('utf-8-sig').splitlines():
            root, size, logical = line.split(None, 2)
            if not logical.startswith('(未反查)'): logicals[(root, hrel(logical))] = logical
        for p in sorted(donor.glob('archive-*/*.zip')):
            source_receipts.append({'path': str(p), 'sha256': sha(p.read_bytes())})
            with zipfile.ZipFile(p) as z:
                assert z.testzip() is None
                for n in z.namelist():
                    parts = n.split('/')
                    assert len(parts) == 4 and parts[0] == 'production'
                    assert re.fullmatch('[a-f0-9]{2}', parts[2]) and re.fullmatch('[a-f0-9]{38}', parts[3])
                    assets[(REVERSE_ROOTS[parts[1]], '/'.join(parts[2:]))] = z.read(n)
        table_payloads.append(readj(donor / 'client-tables/client_tables_payload.json'))
        for p in sorted((donor / 'server-data').glob('*_rows.json')):
            if 'gacha' in p.name: continue
            obj = readj(p)
            for rel, rows in obj.get('objects', obj).items():
                dest = get_server(rel)
                assert isinstance(dest, dict) and isinstance(rows, dict)
                dest.update(copy.deepcopy(rows))
            for rel, rows in obj.get('lists', {}).items():
                # This donor-only list has no reader in our server. Soul IDs
                # belong to the existing runtime item registry instead.
                if rel == 'soul_item_ids.json': rel = 'item_ids.json'
                dest = get_server(rel)
                if before_server[rel] is None and dest == {}:
                    dest = server[rel] = []
                assert isinstance(dest, list), f'expected list: {rel}'
                for value in rows:
                    if value not in dest: dest.append(value)

    # All server extension rows that currently win must agree with the new targets.
    for base, ext in [('character.json', 'character_rank_p5b.json'), ('cdndata/character.json', 'cdndata/character_rank_p5b.json'), ('cdndata/character_text.json', 'cdndata/character_text_rank_p5b.json'), ('mana_node.json', 'mana_node_cnmod.json'), ('mana_node.json', 'mana_node_rank_p5b.json')]:
        target_ids = set()
        for donor in [args.donor07, args.donor08]:
            obj = readj(next((donor/'server-data').glob('*_character_rows.json')))
            target_ids.update(obj.get('objects', obj).get(base, {}))
        extended = get_server(ext)
        for k in target_ids:
            if k in extended: extended[k] = copy.deepcopy(get_server(base)[k])

    # Rebuild only the approved pool from our existing membership and policies.
    decisions = readj(args.decisions)
    pool = copy.deepcopy(get_server('gacha_cnmod.json')['990001'])
    old_pool = copy.deepcopy(pool)
    rows = pool['pool']['1']
    assert len(rows) == 253 and all(x['rank'] == 5 for x in rows), 'unexpected current pool'
    approved_ids = set(decisions['approved']['preserve_existing_exchangeable_ids']) | set(EXCHANGE_UP)
    donor_pool = readj(next((args.donor07/'server-data').glob('*_gacha_rows.json')))['gacha.json']['990001']['pool']['1']
    new_rows = [copy.deepcopy(next(x for x in donor_pool if x['id'] == id)) for id in NEW_IDS]
    for x in rows:
        if x['id'] in EXCHANGE_UP: x['odds'] = 10000
        x['isExchangeable'] = x['id'] in approved_ids
    ordinary = [x for x in rows if not x['isRateUp']]
    original_total = sum(x['odds'] for x in ordinary)
    target_total = 1204000
    allocations = [divmod(x['odds'] * target_total, original_total) for x in ordinary]
    remaining = target_total - sum(q for q, _ in allocations)
    extras = set(sorted(range(len(ordinary)), key=lambda i: (-allocations[i][1], i))[:remaining])
    for i, x in enumerate(ordinary): x['odds'] = allocations[i][0] + (i in extras)
    rows[:] = new_rows + rows
    for x in rows:
        if x['id'] in NEW_IDS: x.update(odds=38000, isExchangeable=False)
        x['rarity'] = round(x['odds'] * 1000 / 1500000, 6)
    assert sum(x['odds'] for x in rows) == 1500000
    assert len(rows) == 255 and len({x['id'] for x in rows}) == 255
    all_rows = [x for r in pool['pool'].values() for x in r]
    assert {x['id'] for x in all_rows if x.get('isExchangeable')} == approved_ids
    assert not set(decisions['approved']['excluded_removed_ids']) & {x['id'] for x in all_rows}
    assert {k:v for k,v in old_pool.items() if k!='pool'} == {k:v for k,v in pool.items() if k!='pool'}
    for k in old_pool['pool']:
        if k!='1': assert old_pool['pool'][k] == pool['pool'][k]
    for rel in ['gacha.json', 'gacha_cnmod.json', 'gacha_rank_p5b.json']:
        obj = get_server(rel)
        if rel != 'gacha_rank_p5b.json' or '990001' in obj: obj['990001'] = copy.deepcopy(pool)

    # Merge shared tables by individual stored leaves; retain unrelated keys/bytes.
    for payload in table_payloads:
        for logical, rows_payload in payload.items():
            if logical == ODDS_TABLE: continue
            key = ('common', hrel(logical)); logicals[key] = logical
            old = assets.get(key)
            if old is None: old = chain.get(key)
            assert old is not None, f'missing existing table: {logical}'
            assets[key] = merge_node(old, {'__n__': rows_payload}, [logical], changes)
    key = ('common', hrel(ODDS_TABLE)); logicals[key] = ODDS_TABLE
    before = chain.get(key); outer = rawmap(before)
    table_id = 'cnmod_abyss_limited_gacha_character_5'
    assert list(outer) == [table_id]
    def boolean(x): return 'true' if x else 'false'
    inner = {str(i): packcsv([[str(x['id']), '5', str(x['odds']), boolean(x['isRateUp']), boolean(x['isLimited']), boolean(x['isExchangeable']), boolean(x['trialReadingForced'])]]) for i,x in enumerate(rows)}
    assets[key] = packmap({table_id: packmap(inner)})
    assert len(rawmap(rawmap(assets[key])[table_id])) == 255

    note_key = ('common', hrel(NOTE)); logicals[note_key] = NOTE
    note = wf_atf.inflate(chain.get(note_key)).decode('utf-8')
    replacements = {
        '5名首领角色各自UP，出现概率各为0.300%，合计1.5%。': '杰拉尔、稻穗两名新角色各自UP，出现概率各为0.380%，合计0.760%。</p><br/>\n    <p>・5名首领角色各自UP，出现概率各为0.100%，合计0.5%。',
        '其余231名★5角色的总出现概率为11.8%': '其余231名★5角色的总出现概率为12.04%',
        '除水魔女、深渊之兽、白虎、魔王、歼灭者外，其余UP角色及池内联动角色可兑换，每名需250点；其余角色不可兑换。': '杰拉尔、稻穗暂不可兑换；原有22名UP角色及池内联动角色可兑换，共37名★5、7名★4，每名需250点；其余角色不可兑换。',
    }
    for old,new in replacements.items():
        assert note.count(old) == 1, f'gacha note preimage mismatch: {old}'
        note = note.replace(old,new)
    assets[note_key] = wf_atf.deflate(note.encode('utf-8'))

    # Validate all stored PNGs, and build actual iOS slot-3 textures with four workers.
    png_count = 0
    for key,b in assets.items():
        if b[1:4] in (b'png', b'PNG'):
            decoded = wf_assets.png_decode_stored(b)
            image = Image.open(io.BytesIO(decoded)); image.load(); png_count += 1
    jobs = []
    for key,b in sorted(assets.items()):
        if key[0] != 'android': continue
        logical = logicals[key]
        assert logical.endswith('.atf.deflate'), logical
        png_logical = logical.removesuffix('.atf.deflate') + '.png'
        png_key = ('medium',hrel(png_logical))
        png = assets.get(png_key)
        if png is None: png = chain.get(png_key)
        assert png is not None, f'missing iOS source PNG: {png_logical}'
        decoded = wf_assets.png_decode_stored(png)
        ios_key = ('ios',key[1]); logicals[ios_key] = logical
        jobs.append((logical,decoded,b,str(work/'ios'/key[1])))
    savej(work/'source-receipts.json', source_receipts)
    savej(work/'shared-table-changes.json', changes)
    print(f'Prepared {len(assets)} resources, {len(changes)} shared leaves, {len(jobs)} iOS cut-ins',flush=True)
    ios_receipts=[]
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(ios_job,j): j[0] for j in jobs}
        for future in as_completed(futures):
            result = future.result();ios_receipts.append(result)
            print(f'iOS complete: {result["logical"]}',flush=True)
    for receipt in ios_receipts:
        assets[('ios',hrel(receipt['logical']))] = Path(receipt['path']).read_bytes()
    savej(work/'ios-pairs.json', sorted(ios_receipts,key=lambda x:x['logical']))

    inventory=[]
    for key,b in sorted(assets.items()):
        old = chain.get(key)
        if old == b: continue
        out = work/'resources'/ROOTS[key[0]]/key[1]
        out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b)
        if old is not None:
            pre = work/'before/resources'/ROOTS[key[0]]/key[1]
            pre.parent.mkdir(parents=True,exist_ok=True);pre.write_bytes(old)
        inventory.append({'root':key[0],'rel':key[1],'member':member(key),'logical':logicals.get(key),'bytes':len(b),'sha256':sha(b),'before_sha256':sha(old) if old else None})
    server_inventory=[]
    for rel,obj in sorted(server.items()):
        old = before_server[rel]
        if old is not None and json.loads(old)==obj: continue
        output = work/'server/assets'/rel;savej(output,obj)
        if old is not None:
            pre=work/'before/server/assets'/rel;pre.parent.mkdir(parents=True,exist_ok=True);pre.write_bytes(old)
        server_inventory.append({'path':'assets/'+rel,'before_sha256':sha(old) if old else None,'sha256':sha(output.read_bytes())})
    savej(work/'resources.json',inventory)
    savej(work/'server-files.json',server_inventory)
    savej(work/'current-resource-sources.json',chain.reads)
    savej(work/'approved-gacha.json',pool)
    savej(work/'prepare-report.json',{'status':'prepared_pending_runtime_and_reference_validation','baseline_version':chain.tail,'baseline_manifest_sha256':sha(chain.manifest_bytes),'resources':len(inventory),'server_files':len(server_inventory),'pngs_validated':png_count,'ios_pairs':len(ios_receipts),'unresolved_logical_paths':[x for x in inventory if not x['logical']],'exchangeable_ids':sorted(approved_ids),'five_star_odds':sum(x['odds'] for x in rows),'ordinary_five_star_odds':sum(x['odds'] for x in ordinary)})
    print(f'Prepared {len(inventory)} changed resource payloads and {len(server_inventory)} server files',flush=True)


if __name__ == '__main__': main()
