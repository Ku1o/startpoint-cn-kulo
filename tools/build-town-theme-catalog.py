#!/usr/bin/env python3
"""Verify native town resources sparsely and register an offline catalog. Dry-run by default."""
import argparse
import hashlib
import importlib.util
import io
import json
import re
import sys
import warnings
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
MASTER = 'master/town/town_content.orderedmap'
MAX_RESOURCE = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
KEY = re.compile(r'[a-z][a-z0-9_]{0,63}\Z')
VERSION = re.compile(r'\d+\.\d+\.\d+\Z')
RESOURCE = re.compile(r'[a-zA-Z0-9_/-]+(?:\.[a-zA-Z0-9_]+)*\Z')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def safe_relative(value, archive=False):
    pattern = r'[a-zA-Z0-9_./-]+\Z' if archive else RESOURCE
    if not isinstance(value, str) or len(value) > 240 or not re.fullmatch(pattern, value):
        raise ValueError('unsafe logical resource or archive path')
    if value.startswith('/') or any(part in ('', '.', '..') for part in value.split('/')):
        raise ValueError('unsafe logical resource or archive path')
    return value


def inside(path, root):
    return path == root or root in path.parents


def text(value, limit):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', value)


def load_spec(path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict) or set(value) != {'schemaVersion', 'resourceVersion', 'themes'} or value['schemaVersion'] != 1:
        raise ValueError('spec requires schemaVersion=1, resourceVersion and themes')
    if not isinstance(value['resourceVersion'], str) or not VERSION.fullmatch(value['resourceVersion']):
        raise ValueError('invalid resourceVersion')
    rows = value['themes']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError('spec must include the complete catalog, with 1..100 themes')
    keys, native_ids = set(), set()
    for row in rows:
        if not isinstance(row, dict) or not {'id', 'name', 'description', 'nativeTownContentId'} <= set(row) or set(row) - {'id', 'name', 'description', 'nativeTownContentId', 'extraDependencies'}:
            raise ValueError('theme metadata requires id/name/description/nativeTownContentId, optional extraDependencies')
        key, ident = row['id'], row['nativeTownContentId']
        if not isinstance(key, str) or not KEY.fullmatch(key) or key in keys:
            raise ValueError('invalid/duplicate theme id')
        if type(ident) is not int or not 1 <= ident <= 2147483647 or ident in native_ids:
            raise ValueError('invalid/duplicate nativeTownContentId')
        if not text(row['name'], 80) or not text(row['description'], 500):
            raise ValueError('invalid name or description')
        extras = row.get('extraDependencies', [])
        if not isinstance(extras, list) or len(extras) > 32:
            raise ValueError('invalid extraDependencies')
        refs = set()
        for extra in extras:
            if not isinstance(extra, dict) or set(extra) != {'reference', 'resources', 'evidence'} or not text(extra['reference'], 240) or extra['reference'] in refs or not text(extra['evidence'], 500):
                raise ValueError('extra dependency needs a unique reference and explicit verification evidence')
            refs.add(extra['reference'])
            if not isinstance(extra['resources'], list) or not 1 <= len(extra['resources']) <= 8:
                raise ValueError('extra dependency needs 1..8 exact resource identities')
            for identity in extra['resources']:
                if not isinstance(identity, dict) or set(identity) != {'path', 'sha256', 'size'}:
                    raise ValueError('extra resource requires path/sha256/size')
                safe_relative(identity['path'])
                if not isinstance(identity['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', identity['sha256']) or type(identity['size']) is not int or not 1 <= identity['size'] <= MAX_RESOURCE:
                    raise ValueError('invalid extra resource identity')
        keys.add(key)
        native_ids.add(ident)
    return value


def native_period(row):
    if not isinstance(row, list) or len(row) != 20 or any(not isinstance(cell, str) or len(cell) > 240 for cell in row):
        raise ValueError('town_content must have exactly twenty string fields')
    if not text(row[0], 64) or row[1] not in ('0', '1', '2'):
        raise ValueError('unsupported native town row')
    if row[1] == '0':
        return None
    if row[1] == '1':
        dates = row[2:4]
        if any(not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', value) for value in dates):
            raise ValueError('native Event requires complete start/end timestamps')
        try:
            start, end = (datetime.strptime(value, '%Y-%m-%d %H:%M:%S') for value in dates)
        except ValueError as error:
            raise ValueError('invalid native Event calendar date') from error
        if start > end:
            raise ValueError('native Event start must not follow end')
        return {'kind': 'event', 'start': dates[0], 'end': dates[1]}
    dates = row[4:6]
    if any(not re.fullmatch(r'[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', value) for value in dates):
        raise ValueError('native Annual requires MM-DD HH:mm:ss start/end')
    try:
        # A non-leap reference year rejects 02-29, which has no date every year.
        for value in dates:
            datetime.strptime('2001-' + value, '%Y-%m-%d %H:%M:%S')
    except ValueError as error:
        raise ValueError('invalid native Annual month/day (02-29 is unsupported)') from error
    return {'kind': 'annual', 'start': dates[0], 'end': dates[1]}


def original_periods(parsed, selected_row):
    """Keep dates of every exact resource/behavior alias in this winning master."""
    result, seen = [], set()
    for key, values in parsed.items():
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], list) or len(values[0]) != 20 or any(not isinstance(cell, str) for cell in values[0]):
            raise ValueError('town_content aliases require unambiguous twenty-field rows')
        row = values[0]
        if row[6:] != selected_row[6:]:
            continue
        if not isinstance(key, str) or not re.fullmatch(r'[1-9][0-9]*', key) or not 1 <= int(key) <= 2147483647 or int(key) in seen:
            raise ValueError('invalid/duplicate native town alias id')
        ident = int(key)
        seen.add(ident)
        period = native_period(row)
        if period is not None:
            result.append({'nativeTownContentId': ident, **period})
    return sorted(result, key=lambda period: period['nativeTownContentId'])


def compact_sha(value):
    return sha(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf8'))


def required_resources(row):
    native_period(row)
    wanted = []
    for index in (6, 7, 8):
        if index == 8 and row[index] == '(None)':
            continue
        logical = safe_relative(row[index])
        if not logical.startswith('town/background/'):
            raise ValueError('town background must use the native town/background namespace')
        wanted.append(logical + '.png')
    if row[9] != '(None)':
        particle = safe_relative(row[9])
        if not particle.startswith('town/particle/'):
            raise ValueError('particle must use the native town/particle namespace')
        wanted += [particle + '.parts.amf3.deflate', particle + '.timeline.amf3.deflate']
        sheet = particle.rsplit('/', 1)[0] + '/sprite_sheet'
        wanted += [sheet + '.png', sheet + '.atlas.amf3.deflate']
    bgm = safe_relative(row[19])
    if not bgm.startswith('bgm/'):
        raise ValueError('music must use the native bgm namespace')
    wanted.append(bgm + '.mp3')
    return list(dict.fromkeys(wanted))


def verify_identity(root, logical, raw, identity, exporter):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RESOURCE:
        raise ValueError('missing/oversize resource: ' + logical)
    if not isinstance(identity, dict) or identity.get('sha256') != sha(raw):
        raise ValueError('resource digest mismatch: ' + logical)
    archive = safe_relative(identity.get('archive'), archive=True)
    archive_path = (root / archive).resolve(strict=True)
    if not inside(archive_path, root) or not archive_path.is_file():
        raise ValueError('archive escapes the read-only resource root')
    member = exporter.member(logical)
    safe_relative(member)
    if identity.get('member', member) != member:
        raise ValueError('member does not match native logical hash: ' + logical)
    with zipfile.ZipFile(archive_path) as source:
        members = [info for info in source.infolist() if info.filename == member]
        if len(members) != 1 or members[0].is_dir() or members[0].file_size != len(raw):
            raise ValueError('missing/ambiguous archive member: ' + logical)
        if source.read(members[0]) != raw:
            raise ValueError('archive member bytes changed: ' + logical)
    return {'path': logical, 'sha256': sha(raw), 'size': len(raw), 'archive': archive, 'member': member}


def png_image(raw, logical):
    from PIL import Image
    signature = raw[:8]
    if signature not in (b'\x89PNG\r\n\x1a\n', b'\x89png\r\n\x1a\n'):
        raise ValueError('invalid PNG signature: ' + logical)
    # Game resources may lowercase the PNG magic; only this decode copy is normalized.
    normalized = b'\x89PNG\r\n\x1a\n' + raw[8:]
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(normalized)) as image:
            if image.format != 'PNG' or image.width < 1 or image.height < 1 or image.width * image.height > 32_000_000:
                raise ValueError('invalid/oversize PNG dimensions: ' + logical)
            image.verify()
        with Image.open(io.BytesIO(normalized)) as image:
            image.load()
            return image.convert('RGBA')


def decode_amf(raw, logical, exporter):
    plain = None
    # Native .amf3.deflate is raw DEFLATE; wrapped zlib is also accepted for verified new exports.
    for window in (-15, 15):
        try:
            decoder = zlib.decompressobj(window)
            unpacked = decoder.decompress(raw, 16 * 1024 * 1024 + 1)
            if unpacked and len(unpacked) <= 16 * 1024 * 1024 and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail:
                plain = unpacked
                break
        except zlib.error:
            continue
    reader_type = getattr(getattr(exporter, 'core', None), 'AMF3Reader', None)
    if plain is None or not callable(reader_type):
        raise ValueError('particle needs bounded DEFLATE and trusted core.AMF3Reader: ' + logical)
    reader = reader_type(plain)
    value = reader.read_value()
    if reader.pos != len(plain):
        raise ValueError('trailing/unsupported particle AMF: ' + logical)
    return value


def validate_resource(raw, logical, exporter):
    if logical.endswith('.png'):
        png_image(raw, logical)
    elif logical.endswith('.amf3.deflate'):
        return decode_amf(raw, logical, exporter)
    elif logical.endswith('.mp3'):
        # The native CDN also obfuscates frame sync 0xff as 0x7f; hashes bind stored bytes.
        if len(raw) < 4 or not (raw.startswith(b'ID3') or (raw[0] in (0xff, 0x7f) and raw[1] & 0xe0 == 0xe0)):
            raise ValueError('unrecognized MP3 header: ' + logical)
    else:
        raise ValueError('unsupported required resource: ' + logical)


def verify_particle(row, resources, decoded, extras):
    if row[9] == '(None)':
        return
    particle = row[9]
    sheet = particle.rsplit('/', 1)[0] + '/sprite_sheet'
    atlas = decoded[sheet + '.atlas.amf3.deflate']
    parts = decoded[particle + '.parts.amf3.deflate']
    if not isinstance(atlas, list) or not atlas or not isinstance(parts, dict) or not isinstance(parts.get('i'), list):
        raise ValueError('unsupported native particle atlas/parts schema; audit mechanism before registration')
    width, height = png_image(resources[sheet + '.png'][0], sheet + '.png').size
    names = set()
    for item in atlas:
        if not isinstance(item, dict) or not text(item.get('n'), 240) or item['n'] in names:
            raise ValueError('invalid/duplicate native atlas image name')
        if any(type(item.get(key)) is not int for key in ('x', 'y', 'w', 'h')) or item['x'] < 0 or item['y'] < 0 or item['w'] < 1 or item['h'] < 1 or item['x'] + item['w'] > width or item['y'] + item['h'] > height:
            raise ValueError('native atlas rectangle escapes spritesheet')
        names.add(item['n'])
    known = set(names)
    for item in parts['i']:
        if not isinstance(item, dict) or not isinstance(item.get('s'), bool) or not text(item.get('p'), 240):
            raise ValueError('unsupported native particle image reference schema')
        reference = item['p']
        if item['s'] or reference not in names:
            if reference not in extras:
                raise ValueError('unresolved particle image reference needs verified extraDependencies: ' + reference)
        known.add(reference)
    # Path-like references outside known native atlas names may describe nested parts, sounds or images.
    # Explicit declarations bind those to audited resource bytes rather than guessing a suffix.
    def walk(value):
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str) and '/' in value and value not in known and value not in extras:
            raise ValueError('unresolved particle path needs verified extraDependencies: ' + value)
    for logical, value in decoded.items():
        if logical.startswith(particle + '.') or logical.startswith(sheet + '.') or any(logical == identity['path'] for extra in extras.values() for identity in extra['resources']):
            walk(value)


def verify_snapshot(source, manifest, version, resource_root):
    if not isinstance(source, dict) or source.get('manifestSha256') != sha(manifest) or source.get('assetVersion') != version:
        raise ValueError('exporter version/manifest does not match the requested snapshot')
    archives = source.get('actualChain')
    if not isinstance(archives, list) or not archives:
        raise ValueError('exporter must provide the actual ordered archive chain')
    seen = set()
    for identity in archives:
        relative = safe_relative(identity.get('archive'), archive=True)
        if relative in seen:
            raise ValueError('duplicate archive in source chain')
        seen.add(relative)
        path = (resource_root / relative).resolve(strict=True)
        if not inside(path, resource_root):
            raise ValueError('source archive escapes resource root')
        state = path.stat()
        if state.st_size != identity.get('size') or str(state.st_mtime_ns) != str(identity.get('mtimeNs')):
            raise ValueError('source archive changed during capture')
    return seen


def output_path(repo, resource_root, relative):
    candidate = repo / relative
    resolved = candidate.resolve()
    if not inside(resolved, repo) or inside(resolved, resource_root) or any(part.lower() == '.cdn' for part in resolved.parts):
        raise ValueError('output escapes target or reaches the read-only source/CDN')
    return candidate


def build(args):
    from PIL import Image
    repo, resource_root = Path(args.repo).resolve(strict=True), Path(args.resource_root).resolve(strict=True)
    if repo == resource_root or inside(repo, resource_root) or any(part.lower() == '.cdn' for part in repo.parts):
        raise ValueError('target checkout must be separate from the read-only source/CDN')
    spec = load_spec(Path(args.spec))
    manifest_path = Path('assets/asset-patch/manifest.json')
    manifest = (resource_root / manifest_path).read_bytes()
    if (repo / manifest_path).read_bytes() != manifest:
        raise ValueError('target and resource-root manifests differ')
    importer = importlib.util.spec_from_file_location('town_theme_native_exporter', Path(args.exporter).resolve(strict=True))
    exporter = importlib.util.module_from_spec(importer)
    importer.loader.exec_module(exporter)
    for method in ('resolve', 'parse_rows', 'member'):
        if not callable(getattr(exporter, method, None)):
            raise ValueError('exporter missing ' + method)
    masters, master_source = exporter.resolve(resource_root, [MASTER])
    if MASTER not in masters:
        raise ValueError('authoritative town_content master is missing')
    chain_archives = verify_snapshot(master_source, manifest, spec['resourceVersion'], resource_root)
    master_raw, master_identity = masters[MASTER]
    master_receipt = verify_identity(resource_root, MASTER, master_raw, master_identity, exporter)
    if master_receipt['archive'] not in chain_archives:
        raise ValueError('master identity is outside the effective archive chain')
    parsed = exporter.parse_rows(master_raw, MASTER)
    rows, periods, wanted = {}, {}, set()
    for theme in spec['themes']:
        matching = parsed.get(str(theme['nativeTownContentId']))
        if not isinstance(matching, list) or len(matching) != 1:
            raise ValueError('missing/ambiguous native town row: ' + str(theme['nativeTownContentId']))
        row = matching[0]
        rows[theme['id']] = row
        wanted.update(required_resources(row))
        periods[theme['id']] = original_periods(parsed, row)
        for extra in theme.get('extraDependencies', []):
            wanted.update(identity['path'] for identity in extra['resources'])
    resources, resource_source = exporter.resolve(resource_root, sorted(wanted))
    resource_archives = verify_snapshot(resource_source, manifest, spec['resourceVersion'], resource_root)
    if resource_source['actualChain'] != master_source['actualChain']:
        raise ValueError('resource chain changed between master and resource reads')
    if set(resources) != wanted:
        raise ValueError('missing/unexpected resources: ' + ', '.join(sorted(wanted.symmetric_difference(resources))))
    identities, decoded, total = {}, {}, len(master_raw)
    for logical, (raw, identity) in resources.items():
        total += len(raw)
        if total > MAX_TOTAL:
            raise ValueError('sparse resource read exceeds 512 MiB budget')
        identities[logical] = verify_identity(resource_root, logical, raw, identity, exporter)
        if identities[logical]['archive'] not in resource_archives:
            raise ValueError('resource identity is outside effective chain')
        value = validate_resource(raw, logical, exporter)
        if logical.endswith('.amf3.deflate'):
            decoded[logical] = value
    for theme in spec['themes']:
        extras = {item['reference']: item for item in theme.get('extraDependencies', [])}
        for extra in extras.values():
            for identity in extra['resources']:
                actual = identities[identity['path']]
                if actual['sha256'] != identity['sha256'] or actual['size'] != identity['size']:
                    raise ValueError('explicit extra dependency differs from verified bytes')
        verify_particle(rows[theme['id']], resources, decoded, extras)
    receipt = {'schemaVersion': 1, 'manifestSha256': sha(manifest), 'resourceVersion': spec['resourceVersion'],
               'master': master_receipt, 'themes': []}
    images, thumbnails = {}, {}
    for theme in spec['themes']:
        row = rows[theme['id']]
        native_hash = sha(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf8'))
        theme_resources = list(dict.fromkeys(required_resources(row) + [identity['path'] for extra in theme.get('extraDependencies', []) for identity in extra['resources']]))
        if len(theme_resources) > 100:
            raise ValueError('theme exceeds server resource count limit')
        receipt['themes'].append({'id': theme['id'], 'verified': True, 'nativeTownContentId': theme['nativeTownContentId'],
                                  'nativeRowSha256': native_hash, 'resourceVersion': spec['resourceVersion'],
                                  'originalPeriodsSha256': compact_sha(periods[theme['id']]),
                                  'resources': [identities[logical] for logical in theme_resources],
                                  'extraDependencyEvidence': theme.get('extraDependencies', [])})
        image = png_image(resources[row[6] + '.png'][0], row[6] + '.png')
        image.thumbnail((420, 540), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format='WEBP', quality=90, method=6)
        raw = buffer.getvalue()
        if len(raw) > 512 * 1024:
            raise ValueError('thumbnail exceeds server size limit')
        with Image.open(io.BytesIO(raw)) as check:
            check.load()
            if check.size != image.size or check.format != 'WEBP':
                raise ValueError('thumbnail readback differs')
        digest = sha(raw)
        images[digest + '.webp'] = raw
        thumbnails[theme['id']] = {'file': digest + '.webp', 'sha256': digest, 'width': image.width, 'height': image.height}
    receipt_raw = encoded(receipt)
    catalog = {'schemaVersion': 1, 'themes': [dict({key: value for key, value in theme.items() if key != 'extraDependencies'}, nativeRow=rows[theme['id']], resourceVersion=spec['resourceVersion'],
        originalPeriods=periods[theme['id']], thumbnail=thumbnails[theme['id']], resourceEvidence={'schemaVersion': 1,
            'receiptFile': 'town_theme_resource_receipt.json', 'receiptSha256': sha(receipt_raw)}) for theme in spec['themes']]}
    outputs = {f'assets/town_theme_thumbnails/{name}': raw for name, raw in images.items()}
    outputs['assets/town_theme_resource_receipt.json'] = receipt_raw
    outputs['assets/town_themes.json'] = encoded(catalog)
    targets = {relative: output_path(repo, resource_root, relative) for relative in outputs}
    current = targets['assets/town_themes.json']
    if current.exists():
        previous = json.loads(current.read_text(encoding='utf8'))
        previous_ids = {theme['id'] for theme in previous['themes']}
        if not previous_ids.issubset({theme['id'] for theme in spec['themes']}):
            raise ValueError('spec would remove registered themes; include the complete existing catalog')
    verify_snapshot(resource_source, manifest, spec['resourceVersion'], resource_root)
    if (repo / manifest_path).read_bytes() != manifest or (resource_root / manifest_path).read_bytes() != manifest:
        raise ValueError('manifest changed before output')
    if args.write:
        # Validate every final and temporary physical path before the first write.
        for relative in outputs:
            temporary = output_path(repo, resource_root, relative + '.tmp')
            if temporary.exists():
                raise ValueError('unresolved temporary output already exists: ' + str(temporary))
        for relative, raw in outputs.items():
            target = targets[relative]
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.tmp')
            with temporary.open('xb') as stream:
                stream.write(raw)
            temporary.replace(target)
        for relative, raw in outputs.items():
            if targets[relative].read_bytes() != raw:
                raise ValueError('output readback differs: ' + relative)
    return {'mode': 'write' if args.write else 'dry-run', 'themes': len(spec['themes']), 'resources': len(resources),
            'resourceBytes': total, 'resourceVersion': spec['resourceVersion'], 'manifestSha256': sha(manifest),
            'catalogSha256': sha(outputs['assets/town_themes.json']), 'outputs': list(outputs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, help='Separate target checkout; receives assets only with --write')
    parser.add_argument('--resource-root', required=True, help='Read-only authoritative resource checkout')
    parser.add_argument('--exporter', required=True, help='Trusted sparse native exporter with resolve/parse_rows/member')
    parser.add_argument('--spec', required=True, help='Complete theme metadata JSON, not predeclared native rows')
    parser.add_argument('--write', action='store_true', help='Explicitly write verified catalog, receipt and thumbnails')
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), ensure_ascii=False))
    except Exception as error:
        parser.exit(1, f'town-theme registration failed: {error}\n')


if __name__ == '__main__':
    main()
