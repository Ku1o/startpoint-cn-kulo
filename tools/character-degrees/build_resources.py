"""Merge the reviewed Reborn nameplates into the enabled .107 -> .108 chain.

Only --apply writes project assets. Donor programs are never executed and the
pristine CDN is read-only. Sparse preimages and the receipt stay in --work.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile
import zlib

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/lens-integration'))
import prepare_content as assets
import wf_dsl
from PIL import Image

BASE = '1.4.107'
TARGET = '1.4.108'
PATCH_ID = 'reborn-character-degrees-1.4.108'
ARCHIVE = f'pinball-{BASE}-{TARGET}-1-reborn-character-degrees.zip'
DONOR_SHA = '9859248a2e71681f377e2bc5aa860a5035aaa4f97bde621efe6b70e144edf733'
DEGREE = 'master/degree/degree.orderedmap'
CATEGORY = 'master/degree/degree_category.orderedmap'
CIDS = (119989,119996,119997,129952,129992,129997,129999,139995,
        139997,139998,139999,149988,149989,149990,149995,149996,
        149997,149999,169989,169996,169997,169998,169999,179999)
AUDIT = f'assets/asset-patch/audit/{PATCH_ID}'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decoded_rows(raw, logical=DEGREE):
    table = assets.core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    require(len(table.keys) == len(set(table.keys)), 'duplicate master keys')
    result = {}
    for key, row in zip(table.keys, table.rows):
        records = list(csv.reader(io.StringIO(zlib.decompress(row).decode('utf-8'))))
        require(len(records) == 1, f'not a single row: {key}')
        result[key] = records[0]
    return table, result


def validate_picture(raw, image):
    require(raw[:8] == assets.wf_assets.PNG_REAL, 'donor must be a standard PNG')
    with Image.open(io.BytesIO(raw)) as picture:
        picture.load()
        require(picture.size == (320, 50) and picture.mode == 'RGBA', 'wrong picture dimensions/mode')
        low, high = picture.getchannel('A').getextrema()
        require(low < 255 and high > 0, 'picture must contain visible and transparent pixels')
    require(sha(raw) == image['sha256'], 'donor picture SHA mismatch')
    stored = assets.wf_assets.png_encode(raw)
    require(stored[:8] == assets.wf_assets.PNG_FAKE, 'wrong native PNG signature')
    require(sha(stored) == image['stored_sha256'], 'stored picture SHA mismatch')
    require(assets.wf_assets.png_decode_stored(stored) == raw, 'strict PNG round trip failed')
    return stored


def merge_degrees(before, degrees, category_ids):
    table, old = decoded_rows(before)
    incoming = {}
    for index, entry in enumerate(degrees):
        key = str(9910001 + index)
        require(entry['degree_id'] == int(key) and entry['character_id'] == CIDS[index // 2]
                and entry['state'] == index % 2, 'degree/character/state mapping mismatch')
        row = entry['row']
        require(isinstance(row, list) and len(row) == 9
                and all(isinstance(cell, str) and '\n' not in cell and '\r' not in cell for cell in row)
                and row[2].strip() and row[5] in category_ids, f'invalid native degree row {key}')
        require(row[1] == str(991001 + index) and row[5] == '2', f'wrong order/category {key}')
        require(row[0] == f"degree_mod_character_{entry['character_id']}_awake{entry['state']}", 'wrong string ID')
        require(row[6:8] == ['dynamic/degree/background', 'item/etc/degree'], 'wrong native dependencies')
        require(entry['image']['logical'] == f'dynamic/degree/{row[0]}.png'
                and row[8] + '.png' == entry['image']['logical'], 'image path mismatch')
        require(all(text in row[4] for text in ('100级', '突破至上限', '木桩')), 'missing acquisition text')
        incoming[key] = row
    require(len(degrees) == len(incoming) == 48, 'expected exactly 48 degrees')
    for column in (0, 1, 8):
        values = {row[column] for row in incoming.values()}
        require(len(values) == 48, 'duplicate incoming string/order/image')
        for key, row in old.items():
            require(len(row) == 9, f'bad existing row {key}')
            collision = (int(row[column]) in {int(v) for v in values}) if column == 1 else row[column] in values
            require(not collision or key in incoming, f'occupied string/order/image {key}')
    added = []
    old_raw = dict(zip(table.keys, table.rows))
    for key, row in incoming.items():
        if key in old:
            require(old[key] == row, f'existing degree ID differs: {key}')
        else:
            table.keys.append(key)
            table.rows.append(zlib.compress(assets.core.write_csv_lines([row]).encode('utf-8')))
            added.append(key)
    after = assets.core.build_orderedmap_raw_rows(table) if added else before
    parsed, result = decoded_rows(after)
    new_raw = dict(zip(parsed.keys, parsed.rows))
    require(all(new_raw[key] == row for key, row in old_raw.items()), 'existing compressed rows changed')
    require(all(result[key] == row for key, row in incoming.items()), 'merged rows differ')
    return after, {'existing_rows': len(old), 'added_ids': added, 'total_rows': len(result)}


def deterministic_archive(payloads):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    data = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        require(archive.testzip() is None, 'new archive CRC failure')
        require(archive.namelist() == sorted(payloads), 'unexpected archive members')
        for name, raw in payloads.items():
            require(archive.read(name) == raw, 'archive bytes differ: ' + name)
    return data


def prepare(package, work):
    require(not work.resolve().is_relative_to((REPO / '.cdn').resolve()), 'work must be outside pristine CDN')
    donor = package.read_bytes()
    require(sha(donor) == DONOR_SHA, 'unreviewed donor package')
    with zipfile.ZipFile(io.BytesIO(donor)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and archive.testzip() is None, 'invalid donor ZIP')
        for name in names:
            require(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
                    and ':' not in name and '\\' not in name, 'unsafe donor member')
        file_manifest = json.loads(archive.read('package-manifest.json'))
        for entry in file_manifest['files']:
            data = archive.read(entry['path'])
            require(len(data) == entry['bytes'] and sha(data) == entry['sha256'], 'donor file integrity mismatch')
        manifest = json.loads(archive.read('degree-manifest.json'))
        degrees = manifest['degrees']
        roster = list(csv.DictReader(io.StringIO(archive.read('24角色48铭牌清单.csv').decode('utf-8-sig'))))
        config = json.loads(archive.read('character_degree_rewards.disabled.json'))
        require([int(row['角色ID']) for row in roster] == list(CIDS), 'roster mismatch')
        expected = [{'character_id': cid, 'degree_ids': [9910001 + 2*i, 9910002 + 2*i]} for i, cid in enumerate(CIDS)]
        require(config == {'schema_version': 1, 'enabled': False, 'characters': expected}, 'activation catalog mismatch')
        pictures = {entry['image']['logical']: validate_picture(archive.read(entry['image']['file']), entry['image'])
                    for entry in degrees}
    chain = assets.Chain()
    require(chain.tail == BASE, f'expected {BASE}, got {chain.tail}')
    require(chain.manifest['cdn_version'] == BASE, 'manifest tail mismatch')
    server, cdn = {}, {}
    for name in ('character.json', 'character_rank_p5b.json'):
        server.update(json.loads((REPO / 'assets' / name).read_bytes()))
        cdn.update(json.loads((REPO / 'assets/cdndata' / name).read_bytes()))
    client = chain.get(('common', assets.hrel('master/character/character.orderedmap')))
    _, client_rows = decoded_rows(client, 'master/character/character.orderedmap')
    for row in roster:
        cid, code = row['角色ID'], row['角色code']
        require(server[cid]['rarity'] == 5 and server[cid]['name'] == row['角色名'], f'server identity differs: {cid}')
        require(cdn[cid][0][0] == code and client_rows[cid][0] == code, f'client identity differs: {cid}')
    def current(logical):
        raw = chain.get(('common', assets.hrel(logical)))
        require(raw is not None, 'missing dependency: ' + logical)
        return raw
    before = current(DEGREE)
    category = current(CATEGORY)
    category_ids = set(assets.core.read_orderedmap_raw_rows_from_bytes(category, CATEGORY).keys)
    background = current('dynamic/degree/background.png')
    sheet = current('item/sprite_sheet.png')
    atlas = current('item/sprite_sheet.atlas.amf3.deflate')
    frames = wf_dsl.parse_dsl(zlib.decompress(atlas, -15))['tree']
    matches = [frame for frame in frames if isinstance(frame, dict) and frame.get('n') == 'item/etc/degree']
    require(len(matches) == 1, 'native degree icon not preloaded in item atlas')
    width, height = assets.wf_assets.png_dims(sheet)
    frame = matches[0]
    require(0 <= frame['x'] < frame['x'] + frame['w'] <= width
            and 0 <= frame['y'] < frame['y'] + frame['h'] <= height, 'invalid degree icon frame')
    after, changes = merge_degrees(before, degrees, category_ids)
    require(len(changes['added_ids']) == 48, 'expected 48 new degree rows')
    require(merge_degrees(after, degrees, category_ids)[0] == after, 'merge is not idempotent')
    definitions = {}
    occupied = set()
    for name in ('degree.json', 'degree_rank_p5b.json', 'degree_sponsor.json'):
        occupied.update(json.loads((REPO / 'assets' / name).read_bytes()))
    for entry in degrees:
        key, row = str(entry['degree_id']), entry['row']
        require(key not in occupied, 'existing server degree ID: ' + key)
        require(chain.get(('common', assets.hrel(entry['image']['logical']))) is None, 'existing image path occupied')
        definitions[key] = {'string_id': row[0], 'name': row[2], 'kana': row[3],
                            'condition': row[4], 'category_id': int(row[5])}
    payloads = {assets.member(('common', assets.hrel(DEGREE))): after}
    payloads.update({assets.member(('common', assets.hrel(name))): raw for name, raw in pictures.items()})
    packed = deterministic_archive(payloads)
    integrity = {'name': ARCHIVE, 'size': len(packed), 'sha256': sha(packed),
                 'members': len(payloads), 'files': sorted(payloads)}
    entry = {'id': PATCH_ID, 'type': 'patch', 'name': '24名MOD角色48款专属称号与获取条件',
             'description': '每名角色满破并达100级获得两款称号；旧角色成功完成原生木桩练习补领。',
             'depends_on': BASE, 'version': TARGET, 'enabled': True, 'archive': ARCHIVE,
             'archive_size': len(packed), 'archive_integrity': [integrity], 'files': sorted(payloads),
             'changes': ['追加48条称号及获取条件，保留全部既有称号压缩行。',
                         '48张320×50透明称号图使用原生PNG存储格式，Android与iOS共用。'],
             'created_at': '2026-09-13', 'audit': {'directory': AUDIT, 'report': 'report.json'}}
    updated = copy.deepcopy(chain.manifest)
    updated['cdn_version'] = TARGET
    updated['patches'].append(entry)
    config['enabled'] = True
    skipped = sorted(str(path) for path in (REPO / '.cdn/cn').resolve().glob('archive-*-diff/*.zip')
                     if re.match(r'pinball-1\.4\.\d+-1\.4\.(\d+)-', path.name)
                     and int(re.match(r'pinball-1\.4\.\d+-1\.4\.(\d+)-', path.name)[1]) > 54)
    report = {'schema_version': 1, 'base': BASE, 'target': TARGET, 'donor_sha256': DONOR_SHA,
              'donor_source_commit': file_manifest['source_commit'], 'characters': 24, 'degrees': 48,
              'conditions': 'owned five-star; over_limit_step=4; exp>=379988; both variants together',
              'changes': changes, 'roster': roster, 'native_icon_frame': frame,
              'source_reads': chain.reads, 'ignored_custom_archives_in_pristine_cdn': skipped,
              'archive': integrity, 'manifest_before_sha256': sha(chain.manifest_bytes),
              'manifest_after_sha256': sha(json_bytes(updated)), 'platforms': ['Android', 'iOS'],
              'shared_common_resources': True, 'idempotent_merge': True,
              'device_tested': False, 'runtime_synced': False, 'cloud_deployed': False}
    outputs = {f'assets/asset-patch/active/{ARCHIVE}': packed,
               'assets/degree_character_mod.json': json_bytes(definitions),
               'assets/character_degree_rewards.json': json_bytes(config),
               f'{AUDIT}/report.json': json_bytes(report),
               f'{AUDIT}/degree-manifest.json': json_bytes(manifest),
               'assets/asset-patch/manifest.json': json_bytes(updated)}
    for name, raw in outputs.items():
        target = work / 'after' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for name, raw in [(DEGREE, before), (CATEGORY, category), ('dynamic/degree/background.png', background),
                      ('item/sprite_sheet.png', sheet), ('item/sprite_sheet.atlas.amf3.deflate', atlas)]:
        target = work / 'before' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (work / 'manifest.before.json').write_bytes(chain.manifest_bytes)
    (work / 'report.json').write_bytes(json_bytes(report))
    require((REPO / 'assets/asset-patch/manifest.json').read_bytes() == chain.manifest_bytes, 'manifest changed during preparation')
    return outputs, report


def apply(outputs, report):
    manifest = REPO / 'assets/asset-patch/manifest.json'
    require(sha(manifest.read_bytes()) == report['manifest_before_sha256'], 'manifest preimage drift')
    for name in outputs:
        target = REPO / name
        require(target.resolve().is_relative_to(REPO.resolve()) and not target.resolve().is_relative_to((REPO / '.cdn').resolve()), 'unsafe output')
        require(name == 'assets/asset-patch/manifest.json' or not target.exists(), 'output already exists: ' + name)
    for name, raw in outputs.items():
        if name == 'assets/asset-patch/manifest.json':
            continue
        target = REPO / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
        require(target.read_bytes() == raw, 'write verification failed')
    require(sha(manifest.read_bytes()) == report['manifest_before_sha256'], 'manifest changed before publication')
    temporary = manifest.with_name('manifest.reborn-degrees.tmp')
    with temporary.open('xb') as stream:
        stream.write(outputs['assets/asset-patch/manifest.json'])
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, manifest)
    require(sha(manifest.read_bytes()) == report['manifest_after_sha256'], 'manifest readback failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    outputs, report = prepare(args.package, args.work)
    if args.apply:
        apply(outputs, report)
    print(json.dumps({'applied': args.apply, 'characters': report['characters'], 'degrees': report['degrees'],
                      'master': report['changes'], 'archive': {k: report['archive'][k] for k in ('name','size','sha256','members')},
                      'report': str(args.work / 'report.json')}, ensure_ascii=False))
