"""Unsigned APK packaging: final SWF, AIR UUID and optional four bundle members.

No signing, installation, or historical build entry point is invoked. The
archived binary-AXML parser is imported solely for structural readback.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import struct
import uuid
import zipfile
import zlib

from x86_port import safe_name, signature, sha, PortError

HERE = Path(__file__).resolve().parent
SWF = 'assets/worldflipper_android_release.swf'
MANIFEST_PARSER = HERE / 'support/apk_manifest.py'


def require(condition, message):
    if not condition:
        raise PortError(message)


def canonical_uuid(value):
    try:
        require(str(uuid.UUID(value)) == value and uuid.UUID(value).int != 0, 'UUID must be canonical lowercase and nonzero')
    except (ValueError, TypeError) as e:
        raise PortError('invalid UUID') from e
    return value


def manifest_module():
    spec = importlib.util.spec_from_file_location('pr43_binary_manifest', MANIFEST_PARSER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def manifest_strings(raw, parser):
    # decode_manifest validates the envelope, chunks, package and version fields.
    parser.decode_manifest(raw)
    at, pools = 8, []
    while at < len(raw):
        kind, header, size = struct.unpack_from('<HHI', raw, at)
        if kind == 1:
            pools.append(parser._string_pool(raw, at, header, size))
        at += size
    require(len(pools) == 1, 'manifest must have one string pool')
    return pools[0]


def patch_manifest(raw, old_uuid, new_uuid):
    canonical_uuid(old_uuid); canonical_uuid(new_uuid)
    require(old_uuid != new_uuid, 'new UUID must differ from base UUID')
    parser = manifest_module()
    before = parser.decode_manifest(raw)
    strings = manifest_strings(raw, parser)
    require(strings.count(old_uuid) == 1 and new_uuid not in strings, 'manifest UUID string count mismatch')
    old, new = old_uuid.encode('utf-16le'), new_uuid.encode('utf-16le')
    require(raw.count(old) == 1 and new not in raw, 'manifest requires exactly one UTF16 UUID')
    patched = raw.replace(old, new)
    require(parser.decode_manifest(patched) == before, 'package/version identity changed')
    require(manifest_strings(patched, parser) == [new_uuid if s == old_uuid else s for s in strings], 'manifest string pool changed beyond UUID')
    require(patched.replace(new, old) == raw, 'manifest changed outside UUID slot')
    return patched, before


def dex_fix_checksums(raw):
    b = bytearray(raw)
    b[12:32] = hashlib.sha1(b[32:]).digest()
    struct.pack_into('<I', b, 8, zlib.adler32(b[12:]) & 0xffffffff)
    return bytes(b)


def dex_strings(raw):
    require(len(raw) >= 112 and re.fullmatch(rb'dex\n0(?:35|37|38|39)\x00', raw[:8]), 'unsupported DEX magic/version')
    require(struct.unpack_from('<I', raw, 32)[0] == len(raw), 'DEX file_size mismatch')
    require(struct.unpack_from('<II', raw, 36) == (112, 0x12345678), 'DEX header_size/endian mismatch')
    require(raw[12:32] == hashlib.sha1(raw[32:]).digest(), 'DEX SHA1 mismatch')
    require(struct.unpack_from('<I', raw, 8)[0] == zlib.adler32(raw[12:]) & 0xffffffff, 'DEX Adler32 mismatch')
    map_off = struct.unpack_from('<I', raw, 52)[0]
    count, ids_off = struct.unpack_from('<II', raw, 56)
    data_size, data_off = struct.unpack_from('<II', raw, 104)
    require(data_off >= 112 and data_off + data_size == len(raw), 'DEX data bounds mismatch')
    require(count > 0 and ids_off >= 112 and ids_off + 4 * count <= data_off, 'DEX string_ids bounds mismatch')
    require(data_off <= map_off <= len(raw) - 4 and map_off % 4 == 0, 'DEX map offset mismatch')
    map_count = struct.unpack_from('<I', raw, map_off)[0]
    require(map_off + 4 + map_count * 12 <= len(raw), 'DEX truncated map')
    maps, map_offsets = {}, []
    for i in range(map_count):
        kind, unused, size, off = struct.unpack_from('<HHII', raw, map_off + 4 + i * 12)
        require(not unused and size > 0 and off < len(raw) and kind not in maps, 'DEX invalid/duplicate map record')
        maps[kind] = (size, off)
        map_offsets.append(off)
    require(map_offsets == sorted(set(map_offsets)), 'DEX map sections are not ordered/disjoint')
    require(maps.get(0) == (1, 0) and maps.get(1) == (count, ids_off)
            and maps.get(0x1000) == (1, map_off), 'DEX map/header inventories differ')
    rows, seen = [], set()
    for i in range(count):
        off = struct.unpack_from('<I', raw, ids_off + i * 4)[0]
        require(data_off <= off < len(raw) and off not in seen, 'DEX invalid/duplicate string_data offset')
        seen.add(off)
        pos, length, shift = off, 0, 0
        for byte in range(5):
            require(pos < len(raw), 'DEX truncated ULEB128')
            v = raw[pos]; pos += 1
            length |= (v & 127) << shift
            if not v & 128:
                break
            shift += 7
        else:
            raise PortError('DEX invalid ULEB128')
        end = raw.find(b'\0', pos)
        require(end >= pos, 'DEX unterminated string_data')
        encoded = raw[pos:end]
        try:
            text = encoded.replace(b'\xc0\x80', b'\0').decode('utf-8', 'surrogatepass')
            utf16 = text.encode('utf-16le', 'surrogatepass')
        except UnicodeError as e:
            raise PortError('DEX invalid modified UTF8') from e
        require(len(utf16) // 2 == length, 'DEX string UTF16 length mismatch')
        units = struct.unpack('<' + 'H' * length, utf16) if length else ()
        rows.append({'text': text, 'start': pos, 'end': end, 'data_offset': off, 'units': units})
    require(maps.get(0x2002) == (count, min(seen)), 'DEX string_data map mismatch')
    string_begin = maps[0x2002][1]
    string_limit = min((off for off in map_offsets if off > string_begin), default=len(raw))
    ordered_rows = sorted(rows, key=lambda r: r['data_offset'])
    require(all(string_begin <= r['data_offset'] < r['start'] <= r['end'] < string_limit for r in rows), 'DEX string_data escapes mapped section')
    require(all(ordered_rows[i]['end'] < ordered_rows[i + 1]['data_offset'] for i in range(count - 1)), 'DEX string_data overlap')
    require(all(rows[i]['units'] < rows[i + 1]['units'] for i in range(count - 1)), 'DEX string_ids order/duplicates invalid')
    return rows


def patch_dex(raw, old_uuid, new_uuid, expected_count=1):
    canonical_uuid(old_uuid); canonical_uuid(new_uuid)
    require(old_uuid != new_uuid, 'new UUID must differ from base UUID')
    rows = dex_strings(raw)
    matches = [r for r in rows if r['text'] == old_uuid]
    require(expected_count == 1 and len(matches) == expected_count, 'DEX UUID string_data count mismatch')
    old, new = old_uuid.encode('ascii'), new_uuid.encode('ascii')
    require(len(old) == len(new) == 36 and raw.count(old) == expected_count and new not in raw, 'DEX UUID extra/nonstring hit or new UUID already exists')
    r = matches[0]
    require(raw[r['start']:r['end']] == old, 'DEX UUID is not an exact ASCII string_data')
    changed = raw[:r['start']] + new + raw[r['end']:]
    patched = dex_fix_checksums(changed)
    after = dex_strings(patched)  # Also rejects UUIDs that would break string_ids ordering.
    require([r['text'] for r in after] == [new_uuid if r['text'] == old_uuid else r['text'] for r in rows], 'DEX strings changed outside UUID')
    require(patched[32:r['start']] == raw[32:r['start']] and patched[r['end']:] == raw[r['end']:], 'DEX changed outside identity/checksum fields')
    require(patched.count(new) == expected_count and old not in patched, 'DEX UUID readback count mismatch')
    return patched, {'uuidStringCount': len(matches), 'stringDataOffset': r['start'],
                     'checksumFields': ['8:12 Adler32', '12:32 SHA1'], 'outsideUUIDAndChecksumIdentical': True}


def zip_inventory(z):
    infos = z.infolist()
    names = [safe_name(i.filename) for i in infos]
    require(len(names) == len(set(names)), 'duplicate ZIP members')
    require(not any(i.flag_bits & 1 for i in infos), 'encrypted ZIP unsupported')
    return infos


def rewrite_zip(raw, replacements, *, drop_signatures=False):
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(out, 'w') as dst:
        infos = zip_inventory(src)
        require(set(replacements) <= set(src.namelist()), 'replacement ZIP member missing')
        dst.comment = src.comment
        for i in infos:
            if not drop_signatures or not signature(i.filename):
                dst.writestr(copy.copy(i), replacements.get(i.filename, src.read(i.filename)))
    result = out.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(io.BytesIO(result)) as after:
        require(after.testzip() is None, 'rewritten ZIP CRC failure')
        expected = {n for n in src.namelist() if not drop_signatures or not signature(n)}
        require(set(after.namelist()) == expected, 'rewritten ZIP inventory mismatch')
        for n in expected:
            require(after.read(n) == replacements.get(n, src.read(n)), f'ZIP byte preservation failed: {n}')
            require(all(getattr(after.getinfo(n), k) == getattr(src.getinfo(n), k) for k in ('compress_type','date_time','external_attr','comment','extra')), f'ZIP metadata changed: {n}')
    return result


def patch_bundle(raw, targets):
    resources = targets['resources']
    require(len(resources) == 4 and len({r['member'] for r in resources}) == 4, 'exactly four distinct bundle replacements required')
    edits = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        zip_inventory(z)
        for r in resources:
            n = safe_name(r['member'])
            require(n in z.namelist(), f'bundle target missing: {n}')
            donor = Path(r['donor_file']).read_bytes()
            require(len(z.read(n)) == r['before_size'] and sha(z.read(n)) == r['before_sha256'], f'bundle before hash mismatch: {n}')
            require(len(donor) == r['after_size'] and sha(donor) == r['after_sha256'], f'bundle donor hash mismatch: {n}')
            edits[n] = donor
    return rewrite_zip(raw, edits), sorted(edits)


def package(base, final_swf, bundle_targets, new_uuid, output_dir, *, base_sha256,
            swf_sha256, old_uuid, output_root, expected_dex_uuid_count=1):
    """Return a report and write game.unsigned.apk plus package-report.json.

    Calls to x86_port.port must use this exact output (and returned hash) so
    both ABIs share the final game SWF and bundle. No platform rebuild occurs.
    """
    base, final_swf = Path(base), Path(final_swf)
    bundle_targets = Path(bundle_targets) if bundle_targets is not None else None
    for candidate in (Path(output_dir).absolute(), Path(output_root).absolute()):
        require('.cdn' not in [p.lower() for p in candidate.parts], 'read-only CDN output boundary')
    output_dir, output_root = Path(output_dir).resolve(), Path(output_root).resolve()
    require('.cdn' not in [p.lower() for p in output_root.parts], 'read-only CDN output boundary')
    require(output_dir.is_relative_to(output_root) and output_dir != output_root and not output_dir.exists(), 'output must be a new child directory of task output root')
    canonical_uuid(old_uuid); canonical_uuid(new_uuid)
    require(old_uuid != new_uuid, 'new UUID must differ from base UUID')
    base_raw, swf = base.read_bytes(), final_swf.read_bytes()
    require(sha(base_raw) == base_sha256, 'base APK SHA256 mismatch')
    require(sha(swf) == swf_sha256 and swf[:3] in (b'FWS', b'CWS', b'ZWS'), 'final SWF hash/magic mismatch')
    uuid_record = output_root / '_air_uuid_registry' / (new_uuid + '.json')
    if uuid_record.exists():
        prior = json.loads(uuid_record.read_text(encoding='utf-8'))
        require(prior['swf_sha256'] == swf_sha256, 'UUID already used for a different SWF')
    with zipfile.ZipFile(io.BytesIO(base_raw)) as z:
        zip_inventory(z)
        require(sha(z.read(SWF)) != swf_sha256, 'final SWF unchanged from baseline')
        manifest, identity = patch_manifest(z.read('AndroidManifest.xml'), old_uuid, new_uuid)
        dex, dex_report = patch_dex(z.read('classes.dex'), old_uuid, new_uuid, expected_dex_uuid_count)
        bundle = z.read('assets/bundle.zip')
        marker = z.read('assets/bundle.zip.sha1')
        old_sha1 = hashlib.sha1(bundle).hexdigest().encode('ascii')
        require(marker.strip() == old_sha1 and marker.count(old_sha1) == 1, 'base bundle.zip.sha1 does not match actual bundle')
        edits = {SWF: swf, 'AndroidManifest.xml': manifest, 'classes.dex': dex}
        changed_bundle = []
        if bundle_targets is not None:
            targets = json.loads(bundle_targets.read_text(encoding='utf-8-sig'))
            new_bundle, changed_bundle = patch_bundle(bundle, targets)
            edits.update({'assets/bundle.zip': new_bundle,
                'assets/bundle.zip.sha1': marker.replace(old_sha1, hashlib.sha1(new_bundle).hexdigest().encode('ascii'))})
        preserved = {n: sha(z.read(n)) for n in z.namelist() if n not in edits and not signature(n)}
    result = rewrite_zip(base_raw, edits, drop_signatures=True)
    with zipfile.ZipFile(io.BytesIO(result)) as check:
        require(check.read('assets/bundle.zip.sha1').strip().decode('ascii') == hashlib.sha1(check.read('assets/bundle.zip')).hexdigest(), 'final bundle hash marker mismatch')
        require(check.read(SWF) == swf, 'final SWF readback mismatch')
    report = {'base_apk_sha256': base_sha256, 'apk_sha256': sha(result), 'swf_sha256': swf_sha256,
              'previous_uniqueappversionid': old_uuid, 'uniqueappversionid': new_uuid,
              'identity': identity, 'dex': dex_report, 'changed_members': sorted(edits),
              'changed_bundle_members': changed_bundle, 'preserved_members': len(preserved),
              'preserved_payload_set_sha256': sha(json.dumps(preserved, sort_keys=True).encode()),
              'manifest_parser': str(MANIFEST_PARSER), 'unsigned': True, 'aligned': False,
              'device_tested': False, 'apk': str(output_dir / 'game.unsigned.apk')}
    output_dir.mkdir(parents=True)
    (output_dir / 'game.unsigned.apk').write_bytes(result)
    require(sha((output_dir / 'game.unsigned.apk').read_bytes()) == report['apk_sha256'], 'written APK hash mismatch')
    (output_dir / 'package-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    uuid_record.parent.mkdir(parents=True, exist_ok=True)
    if not uuid_record.exists():
        with uuid_record.open('x', encoding='utf-8') as f:
            json.dump({'uuid': new_uuid, 'swf_sha256': swf_sha256}, f)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'final-swf', 'output-dir', 'output-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    bundle_mode = parser.add_mutually_exclusive_group(required=True)
    bundle_mode.add_argument('--bundle-targets', type=Path)
    bundle_mode.add_argument('--swf-only', action='store_true',
                             help='Preserve the entire bundle for a later SWF/admission-only delta')
    for name in ('base-sha256', 'swf-sha256', 'old-uuid', 'new-uuid'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    report = package(args.base, args.final_swf, args.bundle_targets, args.new_uuid,
                     args.output_dir, base_sha256=args.base_sha256,
                     swf_sha256=args.swf_sha256, old_uuid=args.old_uuid,
                     output_root=args.output_root)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
