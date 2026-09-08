"""Repair synchronous Five Boss material icons on the verified cumulative CDN.

Prepare sparse files under --work. --publish-local explicitly publishes the
reviewed resource edge to source and the local test runtime, manifest last.
No item tables, APKs, databases or pristine CDN files are changed.
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

BASE = '1.4.103'
VERSION = '1.4.104'
ITEM = 'master/item/item.orderedmap'
STAGE = 'master/quest/boss_battle_stage_node.orderedmap'
SHOP = 'master/shop/boss_coin_shop.orderedmap'
# Verified in the cumulative LAN v3 SWF: CommonUi loads item_icon; the
# post-tutorial Item group loads item + item_sec. Both pages use stage drops.
PRELOADED = ('item/sprite_sheet', 'item_sec/sprite_sheet', 'item_icon/sprite_sheet')
CHANGED = ('item/sprite_sheet', 'item_icon/sprite_sheet')
SUFFIXES = ('.png', '.atlas.amf3.deflate')


def strict_png(raw):
    decoded = p.wf_assets.png_decode_stored(raw)
    with Image.open(io.BytesIO(decoded)) as im:
        im.load()
        return im.convert('RGBA')


def requirements(tables):
    stage = p.csvrows(p.rawmap(p.rawmap(tables[STAGE])['1'])['99'])[0]
    assert stage[6] == '99', 'Five Boss stage/shop link changed'
    ids = {int(x) for x in stage[7:11] if x != '(None)'}
    assert ids == {10000144, 10000145, 10000146, 10000147}, 'review changed stage drops'
    for raw in p.rawmap(tables[SHOP]).values():
        row = p.csvrows(raw)[0]
        if row[0] == '99':
            ids.update(int(row[i]) for i in (17, 19, 21, 23) if row[i] != '(None)')
    ids.add(10000143)  # Also protect the native ticket icon used before battle.
    items = p.rawmap(tables[ITEM])
    result = []
    for item_id in sorted(ids):
        row = p.csvrows(items[str(item_id)])[0]
        assert row[4] and row[4] != '(None)', f'no small icon: {item_id}'
        result.append({'id': item_id, 'name': row[2], 'icon': row[4]})
    return result


def missing_icons(required, atlases):
    names = {row['n'] for base in PRELOADED for row in atlases[base]}
    return [row for row in required if row['icon'] not in names]


def validate_closure(required, atlases):
    missing = missing_icons(required, atlases)
    assert not missing, 'small icons not preloaded: ' + ', '.join(str(x['id']) for x in missing)


def rect(row):
    return row['x'], row['y'], row['x'] + row['w'], row['y'] + row['h']


def intersects(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def validate_pair(before_png, before_atlas, after_png, after_atlas, icons):
    old_im, im = strict_png(before_png), strict_png(after_png)
    old_rows, rows = codec.decode_atlas(before_atlas), codec.decode_atlas(after_atlas)
    assert im.width == old_im.width and im.height > old_im.height
    assert max(im.size) <= 2048, 'review platform texture dimensions'
    assert im.crop((0, 0, *old_im.size)).tobytes() == old_im.tobytes(), 'old pixels changed'
    assert rows[:len(old_rows)] == old_rows, 'old frame metadata changed'
    assert len({r['n'] for r in rows}) == len(rows), 'duplicate atlas names'
    added = rows[len(old_rows):]
    assert {r['n'] for r in added} == set(icons), 'added frame names differ'
    for index, row in enumerate(added):
        source = strict_png(icons[row['n']])
        assert (row['w'], row['h']) == source.size, 'icon resized'
        assert row['x'] >= 1 and row['y'] >= old_im.height + 1
        assert row['x'] + row['w'] < im.width and row['y'] + row['h'] < im.height
        assert not any(intersects(rect(row), rect(other)) for other in old_rows + added[:index])
        assert im.crop(rect(row)).tobytes() == source.tobytes(), 'icon pixels changed'
    return {'before_size': list(old_im.size), 'after_size': list(im.size),
            'before_frames': len(old_rows), 'after_frames': len(rows),
            'old_pixels_and_metadata_preserved': True, 'added': added}


def append_icons(before_png, before_atlas, icons):
    old = strict_png(before_png)
    images = {name: strict_png(raw) for name, raw in sorted(icons.items())}
    assert images
    assert sum(im.width + 1 for im in images.values()) + 1 <= old.width
    out = Image.new('RGBA', (old.width, old.height + max(im.height for im in images.values()) + 2))
    out.paste(old, (0, 0))
    rows = codec.decode_atlas(before_atlas)
    x = 1
    for name, im in images.items():
        out.paste(im, (x, old.height + 1))  # No alpha mask: preserve exact RGBA.
        rows.append({'n': name, 'w': im.width, 'h': im.height, 'x': x, 'y': old.height + 1})
        x += im.width + 1
    png, atlas = codec.encode_png(out), codec.encode_atlas(rows)
    report = validate_pair(before_png, before_atlas, png, atlas, icons)
    return png, atlas, report


def validate_bundle(blobs, before, required, icons_by_atlas):
    expected = {base + suffix for base in CHANGED for suffix in SUFFIXES}
    assert set(blobs) == expected, 'unexpected resource set'
    atlases, reports = {}, {}
    for base in PRELOADED:
        atlases[base] = codec.decode_atlas(blobs.get(base + SUFFIXES[1], before[base + SUFFIXES[1]]))
    validate_closure(required, atlases)
    for base in CHANGED:
        reports[base] = validate_pair(before[base + SUFFIXES[0]], before[base + SUFFIXES[1]],
                                     blobs[base + SUFFIXES[0]], blobs[base + SUFFIXES[1]],
                                     icons_by_atlas[base])
    return reports


def publish(chain, w, payloads, archive_name, archive, manifest, report):
    runtime = Path('F:/startpoint-cn-main').resolve()
    manifest_rel = 'assets/asset-patch/manifest.json'
    assert (p.REPO / manifest_rel).read_bytes() == chain.manifest_bytes
    assert (runtime / manifest_rel).read_bytes() == chain.manifest_bytes, 'runtime chain differs'
    # Explicit local test authority; preserve the existing uncommitted graft.
    delivery = {f'assets/asset-patch/{name}': raw for name, raw in payloads.items()}
    delivery[f'assets/asset-patch/active/{archive_name}'] = archive
    delivery[manifest_rel] = manifest
    backup = runtime / '.codex-backups' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-five-boss-icon-closure')
    receipt = []
    for rel, raw in delivery.items():
        for root in (p.REPO, runtime):
            dest = (root / rel).resolve()
            assert dest.is_relative_to(root.resolve()) and '.cdn' not in dest.parts
            if '/active/' in rel:
                assert not dest.exists(), f'published archive already exists: {dest}'
            assert not dest.with_name(dest.name + '.five-boss-icons-tmp').exists()
        dest = runtime / rel
        receipt.append({'path': rel, 'before_sha256': p.sha(dest.read_bytes()) if dest.exists() else None,
                        'sha256': p.sha(raw)})
    for root, saved_root in ((p.REPO, w / 'source-before'), (runtime, backup)):
        for rel, raw in delivery.items():
            dest = root / rel
            if dest.exists():
                saved = saved_root / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, saved)
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp = dest.with_name(dest.name + '.five-boss-icons-tmp')
            temp.write_bytes(raw)
            os.replace(temp, dest)
            assert dest.read_bytes() == raw
    report.update(runtime_delivered=True, backup=str(backup), delivery=receipt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--publish-local', action='store_true')
    args = ap.parse_args()
    w = args.work.resolve()
    assert not w.is_relative_to((p.REPO / '.cdn').resolve())
    w.mkdir(parents=True, exist_ok=True)
    chain = p.Chain()
    assert chain.tail == BASE, 'review changed chain before building this historical edge'
    tables = {name: chain.get(('common', p.hrel(name))) for name in (ITEM, STAGE, SHOP)}
    required = requirements(tables)
    before = {base + suffix: chain.get(('common', p.hrel(base + suffix)))
              for base in PRELOADED for suffix in SUFFIXES}
    atlases = {base: codec.decode_atlas(before[base + SUFFIXES[1]]) for base in PRELOADED}
    missing = missing_icons(required, atlases)
    assert {row['id'] for row in missing} == {10000144, 10000145, 10000146, 10000147}
    icons_by_atlas = {base: {} for base in CHANGED}
    for row in missing:
        name = row['icon']
        base = next(base for base in CHANGED if name.startswith(base.split('/')[0] + '/'))
        raw = chain.get(('common', p.hrel(name + '.png')))
        assert raw is not None, f'missing source artwork: {name}'
        strict_png(raw)
        icons_by_atlas[base][name] = raw
    blobs = {}
    for base in CHANGED:
        png, atlas, _ = append_icons(before[base + SUFFIXES[0]], before[base + SUFFIXES[1]], icons_by_atlas[base])
        blobs[base + SUFFIXES[0]], blobs[base + SUFFIXES[1]] = png, atlas
    checks = validate_bundle(blobs, before, required, icons_by_atlas)
    payloads = {p.member(('common', p.hrel(name))): raw for name, raw in blobs.items()}
    archive_name = f'pinball-{BASE}-{VERSION}-1-five-boss-icon-closure.zip'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and set(z.namelist()) == set(payloads)
        readback = {logical: z.read(p.member(('common', p.hrel(logical)))) for logical in blobs}
        assert readback == blobs
        validate_bundle(readback, before, required, icons_by_atlas)
    integrity = {'name': archive_name, 'size': len(archive), 'sha256': p.sha(archive),
                 'members': len(payloads), 'files': sorted(payloads)}
    entry = {'id': 'five-boss-icon-closure-' + VERSION, 'type': 'patch',
             'name': '五重决战材料小图标加载修复',
             'description': '补齐讨伐与兑换页四种材料的小图标预加载图集，保留全部累计图块。',
             'version': VERSION, 'depends_on': BASE, 'enabled': True,
             'archive': archive_name, 'archive_size': len(archive), 'chain': [archive_name],
             'archive_integrity': [integrity], 'files': sorted(payloads), 'created_at': '2026-09-08',
             'local_test_only': True, 'required_local_platform': 'android'}
    manifest = copy.deepcopy(chain.manifest)
    manifest['patches'].append(entry)
    manifest['cdn_version'] = VERSION
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    for dirname, data in [('before', before), ('prepared', blobs)]:
        for logical, raw in data.items():
            dest = w / dirname / p.member(('common', p.hrel(logical)))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
    for name, raw in tables.items():
        dest = w / 'before' / p.member(('common', p.hrel(name)))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    for icons in icons_by_atlas.values():
        for name, raw in icons.items():
            dest = w / 'before' / p.member(('common', p.hrel(name + '.png')))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
    (w / archive_name).write_bytes(archive)
    (w / 'manifest.before.json').write_bytes(chain.manifest_bytes)
    (w / 'manifest.after.json').write_bytes(manifest_bytes)
    report = {'version': VERSION, 'base': BASE, 'required_small_icons': required,
              'preimage_missing_icons': missing, 'checks': checks, 'archive': integrity,
              'source_reads': chain.reads, 'runtime_delivered': False, 'device_tested': False,
              'swf_changed': False, 'item_tables_changed': False, 'common_png_atlas_only': True}
    if args.publish_local:
        publish(chain, w, payloads, archive_name, archive, manifest_bytes, report)
        p.savej(p.REPO / f'assets/asset-patch/audit/five-boss-icon-closure-{VERSION}/report.json', report)
    p.savej(w / 'report.json', report)
    print(json.dumps({k: report[k] for k in ('version', 'checks', 'archive', 'runtime_delivered')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
