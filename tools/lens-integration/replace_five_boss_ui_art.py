"""Replace three Five Boss UI images; isolate the shared boss menu background.

Preparation writes sparse snapshots only. --apply-source updates the source
asset chain and its loose download files; it never writes the runtime or CDN.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import os
from pathlib import Path
import re
import zipfile

from PIL import Image
import prepare_content as p

STAGE = 'master/quest/boss_battle_stage_node.orderedmap'
SHOP = 'master/shop/boss_coin_shop_category.orderedmap'
OLD_BACKGROUND = 'quest/boss_battle/background/boss_battle_owl'
BACKGROUND = 'quest/boss_battle/background/mod_five_boss'
ART = (
    ('五重关卡预览图.png', 'quest/thumbnail/multi_battle/mod_five_boss.png', (240, 188)),
    ('五重决战交换所横幅.png', 'quest/boss_battle/banner/mod_five_boss_exchange.png', (1000, 184)),
    ('五重关卡-讨伐页.png', BACKGROUND + '.png', (1440, 556)),
)
ART_DIR = 'assets/asset-patch/artwork/five-boss/ui-20260911'


def jsonbytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    assert path.read_bytes() == raw


def png_check(raw, donor, size):
    assert raw[:8] == p.wf_assets.PNG_FAKE
    decoded = p.wf_assets.png_decode_stored(raw)
    assert decoded == donor, 'donor bytes changed beyond the PNG signature'
    with Image.open(io.BytesIO(decoded)) as im:
        im.load()
        assert im.size == size
        return {'size': list(im.size), 'mode': im.mode, 'original_png_sha256': p.sha(decoded)}


def patch_tables(before):
    stage_root = p.rawmap(before[STAGE])
    group = p.rawmap(stage_root['1'])
    old_stage = p.csvrows(group['99'])
    stage = copy.deepcopy(old_stage)
    assert len(stage) == 1 and len(stage[0]) == 14
    assert stage[0][6] == '99' and stage[0][12] == OLD_BACKGROUND
    stage[0][12] = BACKGROUND
    group['99'] = p.packcsv(stage)
    stage_root['1'] = p.packmap(group)
    categories = p.rawmap(before[SHOP])
    old_shop = p.csvrows(categories['99'])
    shop = copy.deepcopy(old_shop)
    assert len(shop) == 1 and len(shop[0]) == 13
    assert shop[0][7] == '1099001' and shop[0][10] == OLD_BACKGROUND
    shop[0][10] = BACKGROUND
    categories['99'] = p.packcsv(shop)
    result = {STAGE: p.packmap(stage_root), SHOP: p.packmap(categories)}
    validate_tables(before, result)
    return result


def validate_tables(before, after):
    old_root, new_root = p.rawmap(before[STAGE]), p.rawmap(after[STAGE])
    assert old_root.keys() == new_root.keys()
    for group_id in old_root:
        if group_id != '1':
            assert old_root[group_id] == new_root[group_id]
            continue
        old_rows, new_rows = p.rawmap(old_root[group_id]), p.rawmap(new_root[group_id])
        assert old_rows.keys() == new_rows.keys()
        for key, raw in old_rows.items():
            if key == '99':
                expected = p.csvrows(raw)
                expected[0][12] = BACKGROUND
                assert p.csvrows(new_rows[key]) == expected
            else:
                assert raw == new_rows[key], ('unrelated stage changed', key)
    old_rows, new_rows = p.rawmap(before[SHOP]), p.rawmap(after[SHOP])
    assert old_rows.keys() == new_rows.keys()
    for key, raw in old_rows.items():
        if key == '99':
            expected = p.csvrows(raw)
            expected[0][10] = BACKGROUND
            assert p.csvrows(new_rows[key]) == expected
        else:
            assert raw == new_rows[key], ('unrelated shop category changed', key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--images', type=Path, default=p.REPO / ART_DIR)
    parser.add_argument('--base-version', required=True)
    parser.add_argument('--apply-source', action='store_true')
    args = parser.parse_args()
    work = args.work.resolve()
    assert work.is_relative_to(Path('F:/codex/work').resolve())
    cdn = (p.REPO / '.cdn').resolve()
    assert not work.is_relative_to(cdn)
    assert not (work / 'report.json').exists(), 'use a fresh task work directory'
    chain = p.Chain()
    assert chain.tail == args.base_version, 'resource chain advanced; re-review inputs'
    version_parts = [int(x) for x in chain.tail.split('.')]
    version_parts[-1] += 1
    version = '.'.join(map(str, version_parts))
    patch_id = f'five-boss-ui-art-{version}'
    archive_name = f'pinball-{chain.tail}-{version}-1-five-boss-ui-art.zip'
    audit_rel = f'assets/asset-patch/audit/{patch_id}'
    before = {}

    def read(logical):
        raw = chain.get(('common', p.hrel(logical)))
        before[logical] = raw
        if raw is not None:
            save(work / 'before' / logical, raw)
        return raw

    for logical in (STAGE, SHOP, OLD_BACKGROUND + '.png'):
        assert read(logical) is not None
    resources = patch_tables(before)
    originals, images = {}, []
    for filename, logical, size in ART:
        source = args.images / filename
        raw = source.read_bytes()
        assert raw[:8] == p.wf_assets.PNG_REAL
        encoded = p.wf_assets.png_encode(raw)
        details = png_check(encoded, raw, size)
        previous = read(logical)
        if logical == BACKGROUND + '.png':
            assert previous is None, 'dedicated background already exists; re-review'
        else:
            assert previous is not None and p.wf_assets.png_dims(previous) == size
        assert encoded != previous, 'image already matches'
        resources[logical] = encoded
        originals[filename] = raw
        images.append(dict(file=filename, logical=logical, stored_sha256=p.sha(encoded), **details))

    # Existing full-size menu images have no trim row; the new one follows the
    # same untrimmed reader contract. Leave the unrelated trim table untouched.
    trims = p.rawmap(read('master/generated/trimmed_image.orderedmap'))
    assert OLD_BACKGROUND not in trims and BACKGROUND not in trims
    members = {p.member(('common', p.hrel(name))): raw for name, raw in resources.items()}
    assert len(members) == 5
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for member, raw in sorted(members.items()):
            info = zipfile.ZipInfo(member, (2026, 9, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and z.namelist() == sorted(members)
        serialized = {logical: z.read(p.member(('common', p.hrel(logical)))) for logical in resources}
        assert serialized == resources
        validate_tables(before, serialized)
        for filename, logical, size in ART:
            png_check(serialized[logical], originals[filename], size)

    integrity = dict(name=archive_name, size=len(archive), sha256=p.sha(archive), members=5, files=sorted(members))
    manifest = copy.deepcopy(chain.manifest)
    manifest['cdn_version'] = version
    manifest['patches'].append(dict(id=patch_id, type='patch', name='五重决战预览、交换所横幅与专用背景',
        description='使用用户提供的三张原尺寸图片；讨伐页与交换所改用独立五重背景，保留官方共用背景。',
        version=version, depends_on=chain.tail, enabled=True, archive=archive_name,
        archive_size=len(archive), chain=[archive_name], archive_integrity=[integrity],
        files=sorted(members), created_at='2026-09-11', local_test_only=False,
        audit=dict(directory=audit_rel, report='report.json')))
    report = dict(version=version, base_version=chain.tail, images=images, archive=integrity,
        resources=[dict(logical=n, member=p.member(('common', p.hrel(n))), sha256=p.sha(raw)) for n, raw in resources.items()],
        table_changes=[dict(logical=STAGE, row='1/99', column=12, before=OLD_BACKGROUND, after=BACKGROUND),
                       dict(logical=SHOP, row='99', column=10, before=OLD_BACKGROUND, after=BACKGROUND)],
        all_other_table_rows_and_cells_preserved=True, donor_png_roundtrip_exact=True,
        official_shared_background_preserved=True, both_platforms_use_common_png=True,
        save_impact='仅图片与图片路径变化；不改变持久化数据、存档ID或导入导出兼容性。',
        source_manifest_before_sha256=p.sha(chain.manifest_bytes), source_reads=chain.reads,
        source_applied=False, runtime_synced=False, device_tested=False,
        excluded_cdn_archives=[str(f) for f in (cdn/'cn').glob('archive-*/*.zip')
            if '-full' not in f.parent.name and
            (not (match := re.match(r'pinball-1\.4\.\d+-1\.4\.(\d+)-(\d+)-', f.name)) or int(match[1]) > 54)])
    save(work / 'manifest.before.json', chain.manifest_bytes)
    save(work / 'manifest.after.json', jsonbytes(manifest))
    for logical, raw in resources.items():
        save(work / 'after' / logical, raw)
    delivery = {f'assets/asset-patch/{member}': raw for member, raw in members.items()}
    delivery.update({f'{ART_DIR}/{name}': raw for name, raw in originals.items()})
    delivery[f'assets/asset-patch/active/{archive_name}'] = archive
    if args.apply_source:
        assert (p.REPO / 'assets/asset-patch/manifest.json').read_bytes() == chain.manifest_bytes
        protected = {}
        for rel in list(delivery) + ['assets/asset-patch/manifest.json', f'{audit_rel}/report.json']:
            dest = (p.REPO / rel).resolve()
            assert dest.is_relative_to(p.REPO.resolve()) and not dest.is_relative_to(cdn)
            assert '.cdn' not in dest.parts
            if '/active/' in rel or '/audit/' in rel:
                assert not dest.exists(), ('already published path', rel)
            protected[rel] = dest.read_bytes() if dest.exists() else None
            if protected[rel] is not None:
                save(work / 'source-before' / rel, protected[rel])
        for logical, raw in resources.items():
            rel = f'assets/asset-patch/{p.member(("common", p.hrel(logical)))}'
            assert protected[rel] == before[logical], ('loose preimage differs', logical)
        for rel, raw in delivery.items():
            dest = p.REPO / rel
            assert (dest.read_bytes() if dest.exists() else None) == protected[rel]
            save(dest, raw)
        report['source_applied'] = True
        report['source_paths'] = sorted(delivery) + [f'{audit_rel}/report.json', 'assets/asset-patch/manifest.json']
        report['source_backup'] = str(work / 'source-before')
        save(p.REPO / audit_rel / 'report.json', jsonbytes(report))
        manifest_path = p.REPO / 'assets/asset-patch/manifest.json'
        assert manifest_path.read_bytes() == chain.manifest_bytes
        temp = manifest_path.with_suffix('.five-boss-ui.tmp')
        assert not temp.exists()
        save(temp, jsonbytes(manifest))
        os.replace(temp, manifest_path)
        final = p.Chain()
        assert final.tail == version
        for logical, raw in before.items():
            assert final.get(('common', p.hrel(logical))) == resources.get(logical, raw)
        for logical, raw in resources.items():
            assert final.get(('common', p.hrel(logical))) == raw
    save(work / 'report.json', jsonbytes(report))
    print(json.dumps({k: report[k] for k in ('version', 'images', 'source_applied', 'runtime_synced')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
