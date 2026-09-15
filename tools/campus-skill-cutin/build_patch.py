"""Build the approved campus skill portraits as .109 part 3.

Only the explicit --apply phase writes the active archive and manifest. The
pristine CDN is read-only; previous archives are checked and never rewritten.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import io
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/lens-integration'))
import prepare_content as p
from PIL import Image

VERSION = '1.4.109'
BASE = '1.4.108'
PART = 'pinball-1.4.108-1.4.109-3-campus-skill-cutin.zip'
AUDIT = 'assets/asset-patch/audit/campus-skill-cutin-1.4.109'
CODES = ('lady_summoner_campus', 'wind_spgirl_campus', 'ruin_girl_campus')


def savej(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def member(root, logical):
    return p.member((root, p.hrel(logical)))


def png_image(raw):
    image = Image.open(io.BytesIO(raw))
    image.load()
    assert image.mode == 'RGBA' and image.size == (1024, 512)
    return image


def decode_android(payload, width, height):
    half = len(payload) // 2
    rgb = p.wf_atf.decode_etc1(payload[:half], width, height)
    alpha = p.wf_atf.decode_etc1(payload[half:], width, height)
    rgba = bytearray(width * height * 4)
    for i in range(width * height):
        rgba[i*4:i*4+3] = rgb[i*3:i*3+3]
        rgba[i*4+3] = alpha[i*3]
    return bytes(rgba)


def decode_all_mips(android, ios):
    images = {}
    for platform, raw in [('android', android), ('ios', ios)]:
        atf = p.wf_atf.parse_atf(raw)
        for level, payload in enumerate(atf['pairs']):
            width, height = max(atf['w'] >> level, 1), max(atf['h'] >> level, 1)
            decoded = (decode_android(payload, width, height) if platform == 'android'
                       else bytes(p.wf_atf.decode_etc2_rgba(payload, width, height)))
            assert len(decoded) == width * height * 4
            if level == 0:
                images[platform] = Image.frombytes('RGBA', (width, height), decoded)
    return images


def quality(source, decoded):
    # Opaque-subject RGB and full-image alpha separately measure codec loss.
    pairs = list(zip(source.getdata(), decoded.getdata()))
    visible = [(a, b) for a, b in pairs if a[3] >= 128]
    rgb = sum(abs(a[c] - b[c]) for a, b in visible for c in range(3)) / (len(visible) * 3)
    alpha = sum(abs(a[3] - b[3]) for a, b in pairs) / len(pairs)
    assert rgb < 15 and alpha < 8, (rgb, alpha)
    return {'opaque_rgb_mean_absolute_error': rgb, 'alpha_mean_absolute_error': alpha}


def encode_job(job):
    code, form, png_path, android_path, ios_path, output = job
    png = Path(png_path).read_bytes()
    source = png_image(png)
    refs = [p.wf_atf.inflate(Path(path).read_bytes()) for path in (android_path, ios_path)]
    android, ios = p.wf_atf.build_cutin_platform_pair(png, *refs)
    pair = p.wf_atf.validate_cutin_platform_pair(android, ios, png)
    decoded = decode_all_mips(android, ios)
    metrics = {}
    for platform, raw in [('android', android), ('ios', ios)]:
        stored = p.wf_atf.deflate(raw)
        assert p.wf_atf.inflate(stored) == raw
        write(Path(output) / platform / code / f'skill_cutin_{form}.atf.deflate', stored)
        metrics[platform] = quality(source, decoded[platform])
        dest = Path(output) / 'decoded' / platform / code / f'skill_cutin_{form}.png'
        dest.parent.mkdir(parents=True, exist_ok=True)
        decoded[platform].save(dest)
    return {'code': code, 'form': form, 'png_sha256': p.sha(png), 'pair': pair,
            'all_mips_decoded': True, 'codec_error': metrics}


def prepare(preview, work):
    assert not (work / 'prepared.json').exists(), 'use a new work directory'
    assert not work.is_relative_to((REPO / '.cdn').resolve())
    work.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((preview / 'crop-receipt.json').read_text('utf-8-sig'))
    assert {(r['code'], r['form']) for r in receipt['images']} == {(c, i) for c in CODES for i in (0, 1)}
    assert len(receipt['images']) == 6
    chain = p.Chain()
    assert chain.tail == VERSION
    manifest = chain.manifest
    patch = next(x for x in manifest['patches'] if x.get('enabled') and x['version'] == VERSION)
    assert patch['depends_on'] == BASE
    assert PART not in (patch.get('chain') or [patch['archive']])
    assert not (REPO / 'assets/asset-patch/active' / PART).exists()
    write(work / 'manifest-before.json', chain.manifest_bytes)
    archive_hashes = {}
    for x in manifest['patches']:
        if x.get('enabled'):
            for name in x.get('chain') or [x['archive']]:
                archive_hashes[name] = p.sha((REPO / 'assets/asset-patch/active' / name).read_bytes())
    trim_logical = 'master/generated/trimmed_image.orderedmap'
    trimmed = p.rawmap(chain.get(('common', p.hrel(trim_logical))))
    assets, jobs, trim_rows = [], [], {}
    for row in receipt['images']:
        code, form = row['code'], row['form']
        base = f'character/{code}/ui/skill_cutin_{form}'
        png = (preview / 'png' / code / f'skill_cutin_{form}.png').read_bytes()
        assert p.sha(png) == row['output_sha256']
        png_image(png)
        full = chain.get(('medium', p.hrel(f'character/{code}/ui/full_shot_1440_1920_{form}.png')))
        assert p.sha(full) == row['source_stored_sha256'], 'full illustration changed since approved preview'
        trim_rows[base] = p.csvrows(trimmed[base])
        assert trim_rows[base] == [['0', '0', '1024', '512']]
        refs = []
        for root, extension in [('medium', '.png'), ('android', '.atf.deflate'), ('ios', '.atf.deflate')]:
            logical = base + extension
            old = chain.get((root, p.hrel(logical)))
            assert old is not None
            before = work / 'before' / member(root, logical)
            write(before, old)
            assets.append({'root': root, 'logical': logical, 'member': member(root, logical),
                           'before_sha256': p.sha(old), 'code': code, 'form': form})
            if root != 'medium': refs.append(str(before))
        png_path = work / 'approved-png' / code / f'skill_cutin_{form}.png'
        write(png_path, png)
        jobs.append((code, form, str(png_path), *refs, str(work / 'encoded')))
    print('Encoding six Android/iOS pairs with 4 worker processes.', flush=True)
    pairs = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        for row in pool.map(encode_job, jobs):
            pairs.append(row)
            print(f'Validated {row["code"]} form {row["form"]}: {row["pair"]}', flush=True)
    for row in assets:
        code, form = row['code'], row['form']
        if row['root'] == 'medium':
            png = (work / 'approved-png' / code / f'skill_cutin_{form}.png').read_bytes()
            raw = p.wf_assets.png_encode(png)
            assert raw.startswith(p.wf_assets.PNG_FAKE)
            assert p.wf_assets.png_decode_stored(raw) == png
        else:
            raw = (work / 'encoded' / row['root'] / code / f'skill_cutin_{form}.atf.deflate').read_bytes()
        assert p.sha(raw) != row['before_sha256']
        write(work / 'after' / row['member'], raw)
        row.update(size=len(raw), sha256=p.sha(raw))
    savej(work / 'prepared.json', {'assets': assets, 'pairs': pairs, 'approved_crop': receipt,
          'manifest_before_sha256': p.sha(chain.manifest_bytes), 'previous_archives': archive_hashes,
          'trim_rows_unchanged': trim_rows, 'sources': chain.reads})
    print('Prepared 18 resources.', flush=True)


def apply(work):
    prepared = json.loads((work / 'prepared.json').read_text('utf-8'))
    manifest_path = REPO / 'assets/asset-patch/manifest.json'
    before = manifest_path.read_bytes()
    assert p.sha(before) == prepared['manifest_before_sha256'], 'manifest changed during encoding'
    original = json.loads(before)
    manifest = copy.deepcopy(original)
    patch = next(x for x in manifest['patches'] if x.get('enabled') and x['version'] == VERSION)
    assert manifest['cdn_version'] == VERSION and patch['depends_on'] == BASE
    destination = REPO / 'assets/asset-patch/active' / PART
    assert not destination.exists()
    for name, digest in prepared['previous_archives'].items():
        assert p.sha(destination.with_name(name).read_bytes()) == digest
    # Final archives are created directly in the repository active directory only
    # after all resource outputs are complete. The manifest is activated last.
    payloads = {}
    for row in prepared['assets']:
        assert re.fullmatch(r'production/(medium_upload|android_upload|ios_upload)/[0-9a-f]{2}/[0-9a-f]{38}', row['member'])
        raw = (work / 'after' / row['member']).read_bytes()
        assert p.sha(raw) == row['sha256'] and len(raw) == row['size']
        payloads[row['member']] = raw
    assert len(payloads) == 18
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, raw)
    archive = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.testzip() is None and len(set(z.namelist())) == len(z.namelist()) == 18
        assert {n: z.read(n) for n in z.namelist()} == payloads
        for code in CODES:
            for form in (0, 1):
                base = f'character/{code}/ui/skill_cutin_{form}'
                png = p.wf_assets.png_decode_stored(z.read(member('medium', base + '.png')))
                assert png == (work / 'approved-png' / code / f'skill_cutin_{form}.png').read_bytes()
                png_image(png)
                android, ios = [p.wf_atf.inflate(z.read(member(platform, base + '.atf.deflate'))) for platform in ('android', 'ios')]
                p.wf_atf.validate_cutin_platform_pair(android, ios, png)
    names = sorted(payloads)
    integrity = {'name': PART, 'size': len(archive), 'sha256': p.sha(archive), 'members': 18, 'files': names}
    patch['chain'] = list(patch.get('chain') or [patch['archive']]) + [PART]
    patch.setdefault('archive_integrity', []).append(integrity)
    patch['archive_size'] = sum(x['size'] for x in patch['archive_integrity'])
    patch['files'] = sorted(set(patch['files']) | set(names))
    patch.setdefault('changes', []).append('第3分包：校碧安卡、校希尔媞、校奈芙提姆进化前后6张技能展示图扩大取景范围，保留上半身和动作；配套Android ETC1与iOS ETC2纹理。')
    patch.setdefault('audit', {})['campus_skill_cutin_directory'] = AUDIT
    for left, right in zip(original['patches'], manifest['patches']):
        if right is not patch: assert left == right
    assert all(original[k] == manifest[k] for k in original if k != 'patches')
    audit = REPO / AUDIT
    assert not audit.exists()
    audit.mkdir(parents=True)
    for name in ('prepared.json', 'manifest-before.json'):
        shutil.copyfile(work / name, audit / name)
    shutil.copytree(work / 'approved-png', audit / 'approved-png')
    after = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    assert manifest_path.read_bytes() == before
    with destination.open('xb') as f: f.write(archive)
    assert destination.read_bytes() == archive
    manifest_path.write_bytes(after)
    chain = p.Chain()
    assert chain.tail == VERSION
    for row in prepared['assets']:
        assert p.sha(chain.get((row['root'], p.hrel(row['logical'])))) == row['sha256']
    for name, digest in prepared['previous_archives'].items():
        assert p.sha(destination.with_name(name).read_bytes()) == digest
    report = {'status': 'packaged_source_only', 'version': VERSION, 'depends_on': BASE, 'part': 3,
        'archive': integrity, 'manifest_before_sha256': p.sha(before), 'manifest_after_sha256': p.sha(after),
        'all_18_effective_assets_verified': True, 'old_archives_unchanged': True,
        'strict_png_roundtrip': True, 'android_ios_pair_count': 6, 'all_mips_decoded': True,
        'approved_pngs_preserved_exactly': True, 'trim_rows_unchanged': prepared['trim_rows_unchanged'],
        'save_impact': 'Art only; no saved identifiers, schema, data tables or balance changes.',
        'runtime_synced': False, 'cloud_deployed': False, 'commit_created': False, 'device_tested': False,
        'part2_note': 'Part 2 was previously allocated to the C2265 repair; this art package uses part 3.',
        'same_version_note': 'Clients already reporting 1.4.109 will not automatically request a new version delta.'}
    savej(audit / 'report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('archive', 'trim_rows_unchanged')} | {'archive': {k: v for k, v in integrity.items() if k != 'files'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', type=Path)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply:
        apply(args.work.resolve())
    else:
        assert args.preview is not None
        prepare(args.preview.resolve(), args.work.resolve())
