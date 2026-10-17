"""Repair two material filters and convert the current dual-ABI APK to public.

Only the SWF, Manifest and DEX AIR cache identity change. The carrier already
contains the verified ARM/x86 libraries, ANEs and four overlimit bundle assets.
"""
from __future__ import annotations
import argparse
import copy
import io
import ipaddress
import json
from pathlib import Path
import re
import struct
from urllib.parse import urlsplit
import uuid
import zipfile
import zlib

import port_game
from package_android import patch_manifest, patch_dex, rewrite_zip, zip_inventory
from x86_port import sha, signature

# Historical verified carrier identity, for audit/fixture reference only. A
# rebuilt carrier has a fresh UUID/signature and must supply its own receipt.
BASE_SHA = 'c0e8f489c36719815edc4e4f6695d4efc1d437cb09b9d7c87a816aa510b99918'
SWF_SHA = 'ee871b6bdaa339afe4e4bea755bded1d26d828f2884e0fe17c481c627898c6b6'
OLD_UUID = '519ccdf8-8ee1-4ec3-a733-006c9bbed440'
SWF = 'assets/worldflipper_android_release.swf'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_carrier_identity(base_sha256, old_uuid):
    require(isinstance(base_sha256, str) and re.fullmatch(r'[0-9a-f]{64}', base_sha256),
            'base SHA256 must be an explicit lowercase 64-digit digest')
    try:
        parsed = uuid.UUID(old_uuid)
        require(str(parsed) == old_uuid and parsed.int != 0, 'old UUID must be canonical lowercase and nonzero')
    except (ValueError, TypeError, AttributeError) as e:
        raise ValueError('old UUID must be canonical lowercase and nonzero') from e


def validate_host(value):
    """Accept an explicit ASCII DNS name or IPv4 address, without URL syntax."""
    require(isinstance(value, str) and value and value == value.strip(), 'host must be explicit and have no whitespace')
    require(len(value) <= 253 and re.fullmatch(r'[A-Za-z0-9.-]+', value), 'host must be an ASCII DNS name or IPv4 address')
    if re.fullmatch(r'[0-9.]+', value):
        try:
            require(str(ipaddress.IPv4Address(value)) == value, 'IPv4 host must use canonical spelling')
        except ipaddress.AddressValueError as e:
            raise ValueError('invalid IPv4 host') from e
    else:
        require(all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
                    for label in value.split('.')), 'invalid DNS host')
    return value


def origins(lan_host, public_origin):
    """Require the exact game-server origin; never silently drop URL components."""
    lan_host = validate_host(lan_host)
    require(isinstance(public_origin, str) and public_origin == public_origin.strip(), 'public origin must be explicit and have no whitespace')
    try:
        parts = urlsplit(public_origin)
        public_host = validate_host(parts.hostname)
        require(parts.scheme == 'http' and parts.port == 8001
                and not parts.username and not parts.password
                and not parts.path and not parts.query and not parts.fragment
                and public_origin == f'http://{public_host}:8001',
                'public origin must be exactly http://HOST:8001')
    except (TypeError, ValueError) as e:
        raise ValueError('public origin must be exactly http://HOST:8001') from e
    require(lan_host.casefold() != public_host.casefold(), 'source and target hosts must differ')
    return f'http://{lan_host}:8001', public_origin


def paths(base_apk, work_dir, *, fresh):
    requested_work = Path(work_dir).absolute()
    base, work = Path(base_apk).resolve(), Path(work_dir).resolve()
    cdn = Path(__file__).resolve().parents[2] / '.cdn'
    require(not any(part.casefold() == '.cdn' for p in (requested_work, work) for part in p.parts)
            and (not cdn.exists() or not work.is_relative_to(cdn.resolve())),
            'output must not be in the read-only .cdn baseline')
    require(work != base and not base.is_relative_to(work), 'output directory must not contain or replace the input APK')
    require(base.is_file(), 'base APK must be an existing file')
    require(not work.exists() if fresh else work.is_dir(),
            'SWF stage requires a fresh output directory' if fresh else 'package stage requires the existing SWF output directory')
    return base, work


def replace_abc_tags(source, edits, common):
    raw = common.swf_data(source)
    pieces, cursor = [], 0
    for name, at, length, prefix, abc in common.abc_tags(source):
        if at not in edits:
            continue
        payload = prefix + edits[at]
        pieces.extend((raw[cursor:at], struct.pack('<HI', (82 << 6) | 63, len(payload)), payload))
        cursor = at + length
    pieces.append(raw[cursor:])
    output = b''.join(pieces)
    return source[:4] + struct.pack('<I', len(output) + 8) + (zlib.compress(output) if source[:3] == b'CWS' else output)


def serialize_abc(abc, original, common):
    # Reuse the lossless zero-count-pool normalization from the established
    # independent-formations/package_set_edit_public_android.py serializer.
    def counts(data):
        reader = common.abcfmt.R(data)
        reader.p = 4
        rows = []
        for read in (reader.s32, reader.u32, reader.d64):
            at = reader.p
            count = reader.u30()
            rows.append((at, count))
            for _ in range(max(0, count - 1)):
                read()
        return rows
    result = bytearray(abc.serialize())
    for (_, old), (at, fresh) in zip(counts(original), counts(result)):
        if old == 0 and fresh == 1:
            result[at] = 0
    return bytes(result)


def build_swf(source, *, lan_host, public_origin):
    before_origin, after_origin = origins(lan_host, public_origin)
    lan, source_origin, target_origin = lan_host.encode('ascii'), before_origin.encode('ascii'), after_origin.encode('ascii')
    source_authority, target_authority = source_origin[len(b'http://'):], target_origin[len(b'http://'):]
    require(sha(source) == SWF_SHA, 'base SWF SHA256 mismatch')
    common, core = port_game.dependencies()
    import old_server_compat
    original_tags = common.abc_tags(source)
    main, main_tag = common.main_abc(source)
    require(main.serialize() == main_tag[4], 'main ABC must roundtrip')
    before = copy.deepcopy(main)
    changes = [old_server_compat.apply(d, main, core.Pool(main, False), core)
               for d in old_server_compat.PATCHES]
    changed = [i for i, (a, b) in enumerate(zip(before.bodies, main.bodies)) if common.freeze(a) != common.freeze(b)]
    wanted = {core.bodies.resolve(main, d['label']) for d in old_server_compat.PATCHES}
    require(set(changed) == wanted and len(changed) == 2, 'exactly the two selected compatibility methods must change')
    for field in ('methods', 'instances', 'classes', 'scripts', 'metadata', 'ints', 'uints', 'doubles', 'strings', 'namespaces', 'ns_sets', 'multinames'):
        require(common.freeze(getattr(before, field)) == common.freeze(getattr(main, field)), f'unexpected main ABC change: {field}')
    checks = [port_game.validate_body(main, main.bodies[i], common, core) for i in changed]
    edits, endpoints = {}, []
    for name, at, length, prefix, raw in original_tags:
        if at != main_tag[1] and lan not in raw:
            continue
        abc = main if at == main_tag[1] else common.ABC(raw)
        unchanged_encoding = serialize_abc(abc, raw, common)
        if at != main_tag[1]:
            require(unchanged_encoding == raw, f'target ABC must roundtrip: {name!r}')
        saved_strings = {}
        for index, value in enumerate(abc.strings):
            if isinstance(value, bytes) and lan in value:
                # The main game stores two bare authorities; the admission
                # helpers store full origins and route URLs.
                bare_authority = value == source_authority
                route = value == source_origin or value.startswith(source_origin + b'/')
                require((bare_authority or route) and value.count(lan) == 1 and target_origin not in value,
                        f'LAN host occurs outside the selected endpoint: {name!r} string {index}')
                saved_strings[index] = value
                abc.strings[index] = target_authority if bare_authority else value.replace(source_origin, target_origin)
                endpoints.append(dict(tag=name.decode(), index=index, before=value.decode(), after=abc.strings[index].decode()))
        payload = serialize_abc(abc, raw, common)
        if at == main_tag[1] or saved_strings:
            edits[at] = payload
        for index, value in saved_strings.items():
            abc.strings[index] = value
        require(serialize_abc(abc, raw, common) == unchanged_encoding, f'endpoint inverse changed ABC: {name!r}')
    require(len(endpoints) == 9, f'exactly nine endpoint strings required; found {len(endpoints)}')
    output = replace_abc_tags(source, edits, common)
    # Tag order and all unrelated raw tags must remain byte-identical.
    old_raw, new_raw = common.swf_data(source), common.swf_data(output)
    old_rows, new_rows = list(common.swftags.iter_tags(old_raw)), list(common.swftags.iter_tags(new_raw))
    require(len(old_rows) == len(new_rows), 'SWF tag count changed')
    original_at = {row[1]: row for row in original_tags}
    for a, b in zip(old_rows, new_rows):
        ak, ao, ah, an = a; bk, bo, bh, bn = b
        require(ak == bk, 'SWF tag order changed')
        if ao not in edits:
            require(old_raw[ao:ao + ah + an] == new_raw[bo:bo + bh + bn], 'unrelated SWF tag changed')
        else:
            prefix = original_at[ao][3]
            require(new_raw[bo + bh:bo + bh + bn] == prefix + edits[ao], 'edited SWF tag readback mismatch')
    back, _ = common.main_abc(output)
    require(all(not isinstance(v, bytes) or lan not in v for tag in common.abc_tags(output) for v in common.ABC(tag[4]).strings), 'LAN host remains in an ABC string pool')
    require(len(back.bodies) == len(before.bodies), 'method body count changed')
    require([i for i, (a, b) in enumerate(zip(before.bodies, back.bodies)) if common.freeze(a) != common.freeze(b)] == changed,
            'method differences changed after SWF serialization')
    return output, dict(passed=True, input_swf_sha256=sha(source), output_swf_sha256=sha(output),
                        compatibility_changes=changes, changed_main_bodies=changed,
                        unchanged_main_bodies=len(before.bodies) - len(changed), validations=checks,
                        endpoint_before=before_origin, endpoint_after=after_origin, endpoints=endpoints,
                        unrelated_tags_preserved=True)


def swf_only(base_apk, work_dir, *, base_sha256, old_uuid, lan_host, public_origin):
    origins(lan_host, public_origin)
    validate_carrier_identity(base_sha256, old_uuid)
    base, work = paths(base_apk, work_dir, fresh=True)
    output = work / 'android-game.swf'
    # Pin the currently selected candidate before any payload extraction.
    carrier = base.read_bytes()
    require(sha(carrier) == base_sha256, 'base APK SHA256 mismatch')
    with zipfile.ZipFile(io.BytesIO(carrier)) as z:
        zip_inventory(z)
        source = z.read(SWF)
    fixed, report = build_swf(source, lan_host=lan_host, public_origin=public_origin)
    report.update(schema_version=1, base_apk=str(base), base_apk_sha256=base_sha256,
                  base_air_uuid=old_uuid, swf=str(output))
    work.mkdir(parents=True, exist_ok=False)
    with output.open('xb') as f:
        f.write(fixed)
    with (work / 'android-game-report.json').open('x', encoding='utf8') as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def package(base_apk, work_dir, *, base_sha256, old_uuid, lan_host, public_origin):
    before_origin, after_origin = origins(lan_host, public_origin)
    validate_carrier_identity(base_sha256, old_uuid)
    base, work = paths(base_apk, work_dir, fresh=False)
    output, output_report = work / 'android.unsigned.apk', work / 'unsigned-build.json'
    require(not output.exists() and not output_report.exists(), 'package output already exists')
    report = json.loads((work / 'android-game-report.json').read_text('utf8'))
    require(report.get('schema_version') == 1 and report.get('passed') is True
            and report.get('base_apk') == str(base) and report.get('base_apk_sha256') == base_sha256
            and report.get('base_air_uuid') == old_uuid
            and report.get('input_swf_sha256') == SWF_SHA
            and report.get('swf') == str(work / 'android-game.swf')
            and report.get('endpoint_before') == before_origin and report.get('endpoint_after') == after_origin,
            'SWF stage report does not match the selected inputs and endpoints')
    require(len(report.get('changed_main_bodies', [])) == 2 and len(report.get('endpoints', [])) == 9
            and report.get('unrelated_tags_preserved') is True, 'SWF stage protection proof is incomplete')
    swf_path = work / 'android-game.swf'
    require(swf_path.resolve().parent == work, 'SWF stage output must remain in its work directory')
    swf = swf_path.read_bytes()
    require(sha(swf) == report['output_swf_sha256'], 'SWF stage output hash mismatch')
    source = base.read_bytes()
    require(sha(source) == base_sha256, 'base APK SHA256 mismatch')
    new_uuid = str(uuid.uuid4())
    while not new_uuid[0].isdigit():
        new_uuid = str(uuid.uuid4())
    with zipfile.ZipFile(io.BytesIO(source)) as z:
        zip_inventory(z)
        require(sha(z.read(SWF)) == SWF_SHA, 'base SWF SHA256 mismatch')
        manifest, identity = patch_manifest(z.read('AndroidManifest.xml'), old_uuid, new_uuid)
        dex, dex_proof = patch_dex(z.read('classes.dex'), old_uuid, new_uuid, 1)
        preserved = {n: sha(z.read(n)) for n in z.namelist() if n not in (SWF, 'AndroidManifest.xml', 'classes.dex') and not signature(n)}
    result = rewrite_zip(source, {SWF: swf, 'AndroidManifest.xml': manifest, 'classes.dex': dex}, drop_signatures=True)
    with zipfile.ZipFile(io.BytesIO(result)) as z:
        require(z.testzip() is None, 'unsigned APK CRC failure')
        require(sha(z.read(SWF)) == report['output_swf_sha256'], 'unsigned APK SWF readback mismatch')
        require(all(sha(z.read(n)) == digest for n, digest in preserved.items()), 'unsigned APK changed an unrelated payload member')
    data = dict(status='unsigned_public_candidate', apk=str(output), apk_sha256=sha(result), base_apk=str(base),
                base_apk_sha256=base_sha256, swf_sha256=sha(swf), air_uuid=new_uuid, previous_air_uuid=old_uuid,
                identity=identity, dex=dex_proof, preserved_payload_members=len(preserved),
                changed_payload_members=[SWF, 'AndroidManifest.xml', 'classes.dex'],
                all_native_ane_bundle_members_preserved=True, endpoint=after_origin,
                admission_pair_unchanged=True, device_tested=False)
    with output.open('xb') as f:
        f.write(result)
    with output_report.open('x', encoding='utf8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return data


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['swf', 'package'])
    parser.add_argument('--base-apk', required=True, type=Path, help='exact pinned dual-ABI LAN carrier APK')
    parser.add_argument('--base-sha256', required=True, help='trusted SHA256 from the selected carrier receipt')
    parser.add_argument('--old-uuid', required=True, help='AIR UUID from that same carrier receipt')
    parser.add_argument('--work-dir', required=True, type=Path, help='fresh directory for swf; the same directory for package')
    parser.add_argument('--lan-host', required=True, help='literal source DNS/IPv4 host, without scheme or port')
    parser.add_argument('--public-origin', required=True, help='exact target origin: http://HOST:8001')
    return parser


if __name__ == '__main__':
    parser = argument_parser()
    args = parser.parse_args()
    try:
        result = (swf_only if args.stage == 'swf' else package)(args.base_apk, args.work_dir,
                    base_sha256=args.base_sha256, old_uuid=args.old_uuid,
                    lan_host=args.lan_host, public_origin=args.public_origin)
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        parser.exit(1, f'build refused: {e}\n')
    keys = ('swf', 'output_swf_sha256', 'changed_main_bodies') if args.stage == 'swf' else ('apk', 'apk_sha256', 'air_uuid')
    print(json.dumps({k: result[k] for k in keys}))
