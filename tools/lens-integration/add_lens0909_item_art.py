"""Add user-supplied pixel art to the unpublished consolidated 1.4.103."""
import argparse
import copy
import io
import json
import zipfile
from pathlib import Path
from PIL import Image
import prepare_content as p
import fix_five_boss_icon_closure as closure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--images', type=Path, required=True)
    args = parser.parse_args()
    w = args.work.resolve()
    assert w.is_relative_to(Path('F:/codex/work').resolve())
    c = p.Chain()
    assert c.tail == '1.4.103'
    patch = c.manifest['patches'][-1]
    assert patch['id'] == 'lens0909-consolidated-1.4.103'
    audit_dir = p.REPO / patch['audit']['directory']
    report = p.readj(audit_dir / 'report.json')
    assert 'item_art_update' not in report, 'do not apply twice'
    archive_path = p.REPO / 'assets/asset-patch/active' / patch['archive']
    old_archive = archive_path.read_bytes()
    assert p.sha(old_archive) == patch['archive_integrity'][0]['sha256']
    with zipfile.ZipFile(io.BytesIO(old_archive)) as z:
        payloads = {n: z.read(n) for n in z.namelist()}
    resources = {r['member']: r for r in p.readj(audit_dir / 'resources.json')}
    changed = {}
    def read(n): return c.get(('common', p.hrel(n)))
    def put(n, raw):
        key = ('common', p.hrel(n))
        before = c.get(key)
        member = p.member(key)
        assert member not in changed
        changed[member] = {'root': 'common', 'logical': n, 'rel': key[1], 'member': member,
            'before_sha256': p.sha(before) if before is not None else None,
            'sha256': p.sha(raw), 'kind': 'user-item-art'}
        payloads[member] = raw
        resources[member] = changed[member]
    items_before = read(closure.ITEM)
    items = p.rawmap(items_before)
    sources = []
    thumbnails, small = {}, {}
    specs = [
        ('10000143', '新·深界连战凭证.png', 'entry_ticket_v2'),
        ('10000144', '新·终式武装图纸.png', 'deathbringer_blueprint_v2'),
        ('10000146', '新·五重决战之证.png', 'fivefold_clear_badge_v2'),
    ]
    for item_id, filename, stem in specs:
        source = (args.images / filename).resolve()
        original = source.read_bytes()
        with Image.open(io.BytesIO(original)) as im:
            im.load()
            assert im.size == (20, 20) and im.mode == 'RGBA'
            base = im.copy()
        thumbnail = 'item/materials/mod/five_boss/' + stem
        icon = 'item_icon/materials/mod/five_boss/' + stem
        assert read(thumbnail + '.png') is None and read(icon + '.png') is None
        raw20 = p.wf_assets.png_encode(original)
        raw40 = closure.codec.encode_png(base.resize((40, 40), Image.Resampling.NEAREST))
        assert p.wf_assets.png_decode_stored(raw20) == original
        im40 = closure.strict_png(raw40)
        for y in range(40):
            for x in range(40):
                assert im40.getpixel((x, y)) == base.getpixel((x // 2, y // 2))
        thumbnails[thumbnail] = raw20
        small[icon] = raw40
        put(thumbnail + '.png', raw20)
        put(icon + '.png', raw40)
        row = p.csvrows(items[item_id])[0]
        previous = row.copy()
        row[3], row[4] = thumbnail, icon
        assert [i for i in range(len(row)) if row[i] != previous[i]] == [3, 4]
        items[item_id] = p.packcsv([row])
        sources.append({'item_id': int(item_id), 'item_name': row[2], 'input_name': filename,
            'input_sha256': p.sha(original), 'thumbnail': thumbnail, 'small_icon': icon,
            'thumbnail_size': [20, 20], 'small_icon_size': [40, 40],
            'method': '原始 20px PNG 保留；40px 使用 nearest 整数倍放大，逐像素核对。'})
    new_items = p.packmap(items)
    old_rows, new_rows = p.rawmap(items_before), p.rawmap(new_items)
    assert list(old_rows) == list(new_rows)
    assert {k for k in old_rows if old_rows[k] != new_rows[k]} == {x[0] for x in specs}
    for item_id, _, _ in specs:
        a, b = p.csvrows(old_rows[item_id])[0], p.csvrows(new_rows[item_id])[0]
        assert [i for i in range(len(a)) if a[i] != b[i]] == [3, 4]
    assert p.csvrows(new_rows['10000143'])[0][5] == report['ticket_description']
    put(closure.ITEM, new_items)
    atlas_reports = {}
    final_atlases = {base: closure.codec.decode_atlas(read(base + '.atlas.amf3.deflate')) for base in closure.PRELOADED}
    for base, icons in [('item/sprite_sheet', thumbnails), ('item_icon/sprite_sheet', small)]:
        png, atlas, proof = closure.append_icons(read(base + '.png'), read(base + '.atlas.amf3.deflate'), icons)
        put(base + '.png', png)
        put(base + '.atlas.amf3.deflate', atlas)
        final_atlases[base] = closure.codec.decode_atlas(atlas)
        atlas_reports[base] = proof
    required = closure.requirements({closure.ITEM: new_items, closure.STAGE: read(closure.STAGE), closure.SHOP: read(closure.SHOP)})
    closure.validate_closure(required, final_atlases)
    # Every new thumbnail is preloaded as well as independently downloadable.
    item_names = {r['n'] for r in final_atlases['item/sprite_sheet']}
    assert set(thumbnails) <= item_names
    # Removing any required small icon must fail; standalone PNGs are insufficient.
    for name in small:
        broken = copy.deepcopy(final_atlases)
        broken['item_icon/sprite_sheet'] = [r for r in broken['item_icon/sprite_sheet'] if r['n'] != name]
        try:
            closure.validate_closure(required, broken)
        except AssertionError:
            pass
        else:
            raise AssertionError('missing-icon closure check did not fail')
    encoded = io.BytesIO()
    with zipfile.ZipFile(encoded, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for member, raw in sorted(payloads.items()):
            zi = zipfile.ZipInfo(member, (2026, 9, 9, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, raw)
    archive = encoded.getvalue()
    pngs = 0
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and z.namelist() == sorted(payloads)
        for member, raw in payloads.items():
            assert z.read(member) == raw
            if resources[member]['logical'].endswith('.png'):
                closure.strict_png(raw)
                pngs += 1
    integrity = {'name': patch['archive'], 'size': len(archive), 'sha256': p.sha(archive),
                 'members': len(payloads), 'files': sorted(payloads)}
    manifest = copy.deepcopy(c.manifest)
    updated_patch = manifest['patches'][-1]
    updated_patch.update(archive_size=len(archive), archive_integrity=[integrity], files=sorted(payloads))
    updated_patch['description'] += '采用用户重绘的连战凭证、终式武装图纸、五重决战之证图标。'
    art_report = {'source_images': sources, 'changed_resources': list(changed.values()),
        'item_columns_changed': [3, 4], 'description_preserved': True,
        'atlas_preservation': atlas_reports, 'required_small_icons': required,
        'negative_missing_icon_checks': 3, 'platforms': ['android', 'ios'],
        'scope': '用户要求替换三个道具图标并纳入同一 1.4.103；原有共享图标和全部既有图集帧、像素保持。'}
    report.update(archive=integrity, strict_pngs_decoded=pngs, item_art_update=art_report,
        final_resource_count=len(payloads), resources_equal_previous_terminal_before_item_art=report.pop('resources_equal_previous_terminal'))
    backup = w / 'icons-before'
    assert not backup.exists()
    writes = {archive_path: archive,
        p.REPO / 'assets/asset-patch/manifest.json': (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode(),
        audit_dir / 'resources.json': (json.dumps([resources[m] for m in sorted(resources)], ensure_ascii=False, indent=2) + '\n').encode(),
        audit_dir / 'report.json': (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()}
    for member in changed:
        writes[p.REPO / 'assets/asset-patch' / member] = payloads[member]
    for dest in writes:
        target = dest.resolve()
        assert target.is_relative_to(p.REPO.resolve()) and not target.is_relative_to((p.REPO / '.cdn').resolve())
        if target.exists():
            saved = backup / dest.relative_to(p.REPO)
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(dest.read_bytes())
    assert (p.REPO / 'assets/asset-patch/manifest.json').read_bytes() == c.manifest_bytes
    for dest, raw in writes.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        assert dest.read_bytes() == raw
    final = p.Chain()
    assert final.tail == '1.4.103'
    for member, row in resources.items():
        assert final.get((row['root'], row['rel'])) == payloads[member]
    p.savej(w / 'item-art-readback.json', {'status': 'passed', 'resources': len(payloads),
        'new_art_resources': len(changed), 'strict_pngs': pngs, 'archive': integrity, 'art': art_report})
    print(json.dumps({'resources': len(payloads), 'updated_resources': len(changed), 'pngs': pngs, 'archive_bytes': len(archive)}))


if __name__ == '__main__':
    main()
