"""Prepare/publish the user-authorized second .106 art part; preserve part 1.

Input is a 20px PNG produced by tools/soul-icon-converter from the effective
Deathbringer equipment icon. No CDN baseline, saved IDs or exchange rules change.
"""
import argparse
import copy
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import zipfile

from PIL import Image
import prepare_content as p
import wf_battle_atlas_repack as codec

SOUL = 'item/generated/ability_soul/mod/five_boss/deathbringer_final'
DONOR = 'item/equipment/mod/five_boss/deathbringer_final_lv0.png'
CORE = 'item/materials/mod/abyss/abyss_core'
TRIM = 'master/generated/trimmed_image.orderedmap'
SHOP = 'master/shop/event_item_shop.orderedmap'
PART1 = 'pinball-1.4.105-1.4.106-1-mech-item-sources.zip'
PART1_SHA = 'f25bccc0027d54b980462d78b792d86d015efabb568a76c207e6ba7debd3d9b2'
PART2 = 'pinball-1.4.105-1.4.106-2-deathbringer-core-icons.zip'
AUDIT = 'assets/asset-patch/audit/deathbringer-core-icons-1.4.106'
MANIFEST = 'assets/asset-patch/manifest.json'


def image(raw):
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        return im.convert('RGBA')


def validate(before, blobs, donor):
    assert set(blobs) == {SOUL + '.png', TRIM, SHOP}
    icon = image(p.wf_assets.png_decode_stored(blobs[SOUL + '.png']))
    assert icon.size == donor.size == (20, 20)
    assert icon.getchannel('A').tobytes() == donor.getchannel('A').tobytes()
    assert icon.tobytes() != donor.tobytes()
    old, new = p.rawmap(before[TRIM]), p.rawmap(blobs[TRIM])
    assert set(new) == set(old) | {SOUL}
    assert all(new[k] == v for k, v in old.items())
    assert p.csvrows(new[SOUL]) == [['0', '0', '20', '20']]
    old, new = p.rawmap(before[SHOP]), p.rawmap(blobs[SHOP])
    assert list(old) == list(new)
    assert all(new[k] == v for k, v in old.items() if k != '9700199')
    a, b = p.csvrows(old['9700199']), p.csvrows(new['9700199'])
    assert len(a) == len(b) == 1 and len(a[0]) == len(b[0])
    assert [i for i, (x, y) in enumerate(zip(a[0], b[0])) if x != y] == [13]
    assert b[0][13] == CORE
    assert [b[0][i] for i in (18, 19, 29, 33, 34)] == ['2370099', '500', '5', '2370100', '1']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True, type=Path)
    ap.add_argument('--publish-local', action='store_true')
    args = ap.parse_args()
    w = args.work.resolve()
    assert not w.is_relative_to((p.REPO / '.cdn').resolve())
    chain = p.Chain()
    assert chain.tail == '1.4.106'
    assert chain.manifest_bytes == (w / 'manifest.before.json').read_bytes(), 'review changed manifest'
    entry = next(e for e in chain.manifest['patches'] if e.get('enabled') and e['version'] == '1.4.106')
    assert entry['chain'] == [PART1]
    assert p.sha((p.REPO / 'assets/asset-patch/active' / PART1).read_bytes()) == PART1_SHA
    names = [SOUL + '.png', DONOR, CORE + '.png', TRIM, SHOP,
             'item/sprite_sheet.png', 'item/sprite_sheet.atlas.amf3.deflate']
    before = {n: chain.get(('common', p.hrel(n))) for n in names}
    assert all(before.values())
    donor = image(p.wf_assets.png_decode_stored(before[DONOR]))
    assert donor.tobytes() == image((w / 'deathbringer_final_lv0.png').read_bytes()).tobytes()
    soul = (w / 'deathbringer_final_soul_new.png').read_bytes()
    encoded = p.wf_assets.png_encode(soul)
    assert p.wf_assets.png_decode_stored(encoded) == soul
    # The actual core is already in the synchronously preloaded item atlas.
    atlas = image(p.wf_assets.png_decode_stored(before['item/sprite_sheet.png']))
    frames = codec.decode_atlas(before['item/sprite_sheet.atlas.amf3.deflate'])
    f = next(r for r in frames if r['n'] == CORE)
    assert atlas.crop((f['x'], f['y'], f['x'] + f['w'], f['y'] + f['h'])).tobytes() == image(p.wf_assets.png_decode_stored(before[CORE + '.png'])).tobytes()
    trim = p.rawmap(before[TRIM])
    assert SOUL not in trim
    trim[SOUL] = p.packcsv([['0', '0', '20', '20']])
    shop = p.rawmap(before[SHOP])
    row = p.csvrows(shop['9700199'])
    assert row[0][13] == 'item/materials/equipment_enhancement_materials/steam_robot_material_none_r5'
    row[0][13] = CORE
    shop['9700199'] = p.packcsv(row)
    blobs = {SOUL + '.png': encoded, TRIM: p.packmap(trim), SHOP: p.packmap(shop)}
    validate(before, blobs, donor)
    payloads = {p.member(('common', p.hrel(n))): raw for n, raw in blobs.items()}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and set(z.namelist()) == set(payloads)
        readback = {n: z.read(p.member(('common', p.hrel(n)))) for n in blobs}
        assert readback == blobs
        validate(before, readback, donor)
    receipt = {'name': PART2, 'size': len(archive), 'sha256': p.sha(archive),
               'members': len(payloads), 'files': sorted(payloads)}
    manifest = copy.deepcopy(chain.manifest)
    new_entry = next(e for e in manifest['patches'] if e.get('enabled') and e['version'] == '1.4.106')
    new_entry['chain'].append(PART2)
    new_entry['archive_integrity'].append(receipt)
    new_entry['archive_size'] = sum(r['size'] for r in new_entry['archive_integrity'])
    new_entry['files'] = sorted(set(new_entry['files']) | set(payloads))
    new_entry['audit']['icons_directory'] = AUDIT
    new_entry['description'] += '；第二分包更新死亡使者魂珠与深渊觉醒核商品预览。'
    assert new_entry['quest_time_revisions'] == entry['quest_time_revisions']
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    for n, raw in blobs.items():
        path = w / 'prepared' / n
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (w / PART2).write_bytes(archive)
    (w / 'manifest.after.json').write_bytes(manifest_bytes)
    report = {'version': '1.4.106', 'archive': receipt, 'part1_sha256_unchanged': PART1_SHA,
              'reads': chain.reads, 'converter': 'tools/soul-icon-converter/dist/魂珠图标一键转换工具.exe',
              'converter_sha256': p.sha((p.REPO / 'tools/soul-icon-converter/dist/魂珠图标一键转换工具.exe').read_bytes()),
              'converted_png_sha256': p.sha(soul), 'size': [20, 20], 'alpha_preserved': True,
              'trim': [0, 0, 20, 20], 'shop_changed_product': '9700199', 'shop_changed_column': 13,
              'core_existing_atlas_frame': f, 'unrelated_rows_preserved': True,
              'quest_time_revisions_preserved': new_entry['quest_time_revisions'],
              'save_impact': 'None: artwork and one thumbnail path only; IDs, costs, rewards and progress unchanged.',
              'device_acceptance': False, 'runtime_delivered': False,
              'resources': [{'logical': n, 'member': p.member(('common', p.hrel(n))),
                             'before_sha256': p.sha(before[n]), 'sha256': p.sha(raw)} for n, raw in blobs.items()]}
    if args.publish_local:
        runtime = Path('F:/startpoint-cn-main').resolve()
        assert (runtime / MANIFEST).read_bytes() == chain.manifest_bytes
        assert (p.REPO / MANIFEST).read_bytes() == chain.manifest_bytes
        delivery = {f'assets/asset-patch/{n}': raw for n, raw in payloads.items()}
        delivery[f'assets/asset-patch/active/{PART2}'] = archive
        delivery[MANIFEST] = manifest_bytes  # Publish only after every resource exists.
        backup = runtime / '.codex-backups' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-deathbringer-core-icons')
        saved = []
        for root in (p.REPO, runtime):
            for rel, raw in delivery.items():
                dest = (root / rel).resolve()
                assert dest.is_relative_to(root.resolve()) and '.cdn' not in dest.parts
                assert not dest.with_name(dest.name + '.icons-tmp').exists()
                if '/active/' in rel:
                    assert not dest.exists()
                saved.append({'root': str(root), 'path': rel, 'before_sha256': p.sha(dest.read_bytes()) if dest.exists() else None, 'sha256': p.sha(raw)})
        for root, saved_root in ((p.REPO, w / 'source-before'), (runtime, backup)):
            for rel, raw in delivery.items():
                dest = root / rel
                if dest.exists():
                    target = saved_root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest, target)
                dest.parent.mkdir(parents=True, exist_ok=True)
                temp = dest.with_name(dest.name + '.icons-tmp')
                temp.write_bytes(raw)
                os.replace(temp, dest)
                assert dest.read_bytes() == raw
        after = p.Chain()
        assert all(after.get(('common', p.hrel(n))) == raw for n, raw in blobs.items())
        assert p.sha((runtime / 'assets/asset-patch/active' / PART1).read_bytes()) == PART1_SHA
        report.update(runtime_delivered=True, backup=str(backup), delivery=saved)
        p.savej(backup / 'files.json', saved)
        p.savej(p.REPO / AUDIT / 'report.json', report)
        for name in ('converter-preview.png', 'deathbringer_final_soul_new.png', 'abyss_core.png'):
            shutil.copy2(w / name, p.REPO / AUDIT / name)
    p.savej(w / 'report.json', report)
    print(json.dumps({'archive': receipt, 'runtime_delivered': report['runtime_delivered']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
