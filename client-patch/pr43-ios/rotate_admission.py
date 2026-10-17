"""Rotate equal-length iOS admission constants without recompiling game code.

Private pairing values stay in process memory and final authorized carriers.
Receipts contain identifiers, hashes and structural evidence, never key values.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

from native_support import (INFO_OFFSET, backend, current_origin, dump, read64,
                            sha, verify_signing_models)

INPUT_IPA_SHA = 'a4418388ff005313b2e1f2b3380dd7c99d411ac29afb4543e84fae4e505baa7d'
INPUT_FULL_SHA = '51d8155dc38d04d6c590a978f61de4206a6ac403799209b4979fef29456ce3c9'
INPUT_NATIVE_SHA = '641a97fd555bcaca9d54c95bd264cd55ae2194cbb09f3e816964108dd3d09e2a'
OLD_ID = 'ios-184-author-1047-public-20261001'
NATIVE_MEMBER = 'Payload/worldflipper.app/worldflipper'
SWF_MEMBER = 'Payload/worldflipper.app/worldflipper_ios_release.swf'
METHOD_COUNT = 101496
STRING_HELPER = 0x100a26130
CONSUMERS = {101244: {'ID': 1}, 101245: {'KEY': 2, 'HMAC_PREFIX': 1},
             101281: {'ID': 1, 'KEY': 1}}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def replacement_contract(old_id, new_id, old_key, new_key):
    old_id, new_id = old_id.encode('ascii'), new_id.encode('ascii')
    require(len(old_id) == len(new_id) and old_id != new_id, 'Admission ID must change without changing length')
    require(re.fullmatch(rb'[A-Za-z0-9-]+', new_id) is not None, 'Invalid admission identifier')
    require(len(old_key) == len(new_key) == 64 and old_key != new_key, 'Admission key must change and retain its encoded length')
    require(re.fullmatch(rb'[0-9a-fA-F]{64}', new_key) is not None, 'Admission key must be a 64-byte hexadecimal string')
    return [(old_id, new_id), (old_key, new_key)]


def replace_exact(data, replacements, expected):
    require(len(replacements) == len(expected), 'Replacement count contract mismatch')
    result = data
    for (old, new), count in zip(replacements, expected):
        require(len(old) == len(new), 'Replacement changes encoded length')
        require(result.count(old) == count and result.count(new) == 0, 'Admission value occurrence contract mismatch')
        result = result.replace(old, new)
    reverse = result
    for old, new in reversed(replacements):
        reverse = reverse.replace(new, old)
    require(reverse == data, 'Admission replacement inverse mismatch')
    return result


def build_fields(abc):
    ci, = [i for i, row in enumerate(abc.instances) if abc.mn_name(row[0]) == 'cn.admission::BuildConfig']
    result = {}
    for trait in abc.classes[ci][1]:
        name = abc.mn_name(trait.name).split('::')[-1]
        if name in ('ID', 'KEY', 'ORIGIN'):
            require(trait.kind == 6 and trait.data[4] == 1, 'BuildConfig constant trait drift')
            result[name] = (trait.data[3], abc.strings[trait.data[3]])
    require(set(result) == {'ID', 'KEY', 'ORIGIN'}, 'BuildConfig constants missing')
    return ci, result


def string_veneer(native, target):
    link = backend()
    if target == STRING_HELPER:
        return target
    off = link.file_offset(native, target, 12)
    adrp, add, branch = struct.unpack_from('<III', native, off)
    require(adrp & 0x9f00001f == 0x90000010 and add & 0xffc003ff == 0x91000210
            and branch == 0xd61f0200, 'Unexpected native string-loader veneer')
    immediate = ((adrp >> 29) & 3) | (((adrp >> 5) & 0x7ffff) << 2)
    if immediate & (1 << 20):
        immediate -= 1 << 21
    return (target & ~0xfff) + (immediate << 12) + ((add >> 10) & 0xfff)


def native_string_consumers(native, indexes):
    """Prove actual string loads in transport, HMAC closure and BuildConfig."""
    link = backend()
    import capstone
    table = link.file_offset(native, read64(native, INFO_OFFSET + 48), METHOD_COUNT * 8)
    addresses = struct.unpack_from('<' + 'Q' * METHOD_COUNT, native, table)
    starts = sorted(set(addresses))
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    result = []
    for mid, expected in CONSUMERS.items():
        address = addresses[mid]
        end = next(x for x in starts if x > address)
        require(end - address < 0x10000, 'Native admission function extent drift')
        offset = link.file_offset(native, address, end - address)
        value, found = None, {}
        for ins in md.disasm(native[offset:offset + end - address], address):
            mov = re.fullmatch(r'w1, #(0x[0-9a-f]+|\d+)', ins.op_str)
            movk = re.fullmatch(r'w1, #(0x[0-9a-f]+|\d+)(?:, lsl #(16))?', ins.op_str)
            if ins.mnemonic == 'mov' and mov:
                value = int(mov.group(1), 0)
            elif ins.mnemonic == 'movk' and movk and value is not None:
                shift = int(movk.group(2) or 0)
                value = (value & ~(0xffff << shift)) | (int(movk.group(1), 0) << shift)
            elif ins.mnemonic == 'bl':
                if value in indexes:
                    target = int(ins.op_str.removeprefix('#'), 0)
                    require(string_veneer(native, target) == STRING_HELPER, 'Admission literal is not loaded through llGetString')
                    role = indexes[value]
                    found[role] = found.get(role, 0) + 1
                    result.append(dict(method_id=mid, entry=address, call_site=ins.address,
                                       string_index=value, role=role, veneer=target,
                                       string_helper=STRING_HELPER))
                value = None
            elif ins.op_str.startswith(('w1,', 'x1,')) and ins.mnemonic not in ('cmp', 'tst'):
                value = None
        require(found == expected, 'Native admission literal consumer contract drift')
    return result


def patch_carrier(native, swf, full, new_id, new_key, old_pair_key):
    link = backend()
    from macho_signing_layout import assert_signable_layout
    require(sha(native) == INPUT_NATIVE_SHA and sha(full) == INPUT_FULL_SHA, 'Pinned iOS input identity mismatch')
    require(native[INFO_OFFSET:INFO_OFFSET + 20] == hashlib.sha1(full).digest(), 'Input full ABC/AOT mismatch')
    require(read64(native, INFO_OFFSET + 56) == METHOD_COUNT, 'Input method count drift')
    current_origin(native)
    assert_signable_layout(native)
    old_full = link.abcfmt.ABC(full)
    ci, fields = build_fields(old_full)
    require(ci == 9913 and old_full.classes[ci][0] == 101281, 'BuildConfig class identity drift')
    require(fields['ID'] == (93452, OLD_ID.encode()), 'BuildConfig ID identity drift')
    require(fields['KEY'][0] == 93443 and fields['KEY'][1] == old_pair_key, 'Previous private pair does not match embedded key')
    require(fields['ORIGIN'] == (93454, b'http://124.222.203.221'), 'BuildConfig origin drift')
    prefix = b'SP-ADMISSION-1\n' + OLD_ID.encode() + b'\n'
    require(old_full.strings[93444] == prefix, 'Admission HMAC-prefix identity drift')
    indexes = {93452: 'ID', 93443: 'KEY', 93444: 'HMAC_PREFIX'}
    before_consumers = native_string_consumers(native, indexes)
    changes = replacement_contract(OLD_ID, new_id, fields['KEY'][1], new_key)
    new_full = replace_exact(full, changes, [2, 1])
    new_native = bytearray(replace_exact(native, changes, [6, 3]))
    digest = hashlib.sha1(new_full).digest()
    new_native[INFO_OFFSET:INFO_OFFSET + 20] = digest
    new_swf = link.aot.replace_main_swf_hash(swf, hashlib.sha1(full).digest(), digest)
    fresh = link.abcfmt.ABC(new_full)
    expected_strings = {93452: new_id.encode(), 93443: new_key,
                        93444: b'SP-ADMISSION-1\n' + new_id.encode() + b'\n'}
    require(all(fresh.strings[i] == expected_strings.get(i, value)
                for i, value in enumerate(old_full.strings)), 'Unexpected full ABC string change')
    for field in ('methods', 'metadata', 'instances', 'classes', 'scripts', 'bodies',
                  'ints', 'uints', 'doubles', 'namespaces', 'ns_sets', 'multinames'):
        require(link.freeze(getattr(fresh, field)) == link.freeze(getattr(old_full, field)), 'Non-string full ABC change: ' + field)
    runtime_offset = link.file_offset(native, read64(native, INFO_OFFSET + 24))
    runtime_size = read64(native, INFO_OFFSET + 32)
    old_runtime = link.abcfmt.ABC(native[runtime_offset:runtime_offset + runtime_size])
    runtime_raw = bytes(new_native[runtime_offset:runtime_offset + runtime_size])
    runtime = link.abcfmt.ABC(runtime_raw)
    require(all(runtime.strings[i] == expected_strings.get(i, value)
                for i, value in enumerate(old_runtime.strings)), 'Unexpected runtime ABC string change')
    restored = copy.deepcopy(runtime)
    for i in expected_strings:
        restored.strings[i] = old_runtime.strings[i]
    require(restored.serialize() == old_runtime.serialize(), 'Non-string runtime ABC change')
    require(native_string_consumers(new_native, indexes) == before_consumers, 'Native admission consumer instructions changed')
    require(current_origin(new_native) == current_origin(native), 'Public origin changed')
    assert_signable_layout(new_native)
    signing = verify_signing_models(new_native)
    proof = dict(buildconfig_class=ci, buildconfig_cinit=101281,
                 string_indexes={role: index for index, role in indexes.items()},
                 native_string_consumers=before_consumers,
                 runtime_abc_offset=runtime_offset, runtime_abc_size=runtime_size,
                 runtime_abc_sha256=sha(runtime_raw), all_method_bodies_and_traits_unchanged=True,
                 all_non_admission_bytes_reversible=True, native_id_occurrences=6,
                 native_key_occurrences=3, full_id_occurrences=2, full_key_occurrences=1,
                 signing_models=signing, public_origin=current_origin(new_native))
    return bytes(new_native), new_swf, new_full, proof


def load_private_pair(pair_dir, new_id):
    pair_dir = Path(pair_dir)
    policy = json.loads((pair_dir / 'config/client-admission.json').read_text('utf-8-sig'))
    rows = [r for r in policy['builds'] if r['id'] == new_id]
    require(len(rows) == 1 and rows[0]['platform'] == 'ios', 'New iOS policy entry missing or ambiguous')
    keys = json.loads((pair_dir / 'config/client-admission.keys.json').read_text('utf-8-sig'))
    before = json.loads((pair_dir / 'before/config/client-admission.keys.json').read_text('utf-8-sig'))
    require(new_id in keys and OLD_ID in before, 'Private iOS pair incomplete')
    new_key, old_key = keys[new_id].encode('ascii'), before[OLD_ID].encode('ascii')
    require(keys.get(OLD_ID) == before[OLD_ID], 'Previous allowed iOS pair changed')
    del keys, before
    return old_key, new_key


def run(input_ipa, full_abc, pair_dir, new_id, carrier_report, output_ipa, output_full, work):
    input_ipa, full_abc = Path(input_ipa), Path(full_abc)
    output_ipa, output_full, work = Path(output_ipa), Path(output_full), Path(work)
    require(not output_ipa.exists() and not output_full.exists() and not work.exists(), 'Fresh rotation outputs required')
    require(sha(input_ipa.read_bytes()) == INPUT_IPA_SHA and sha(full_abc.read_bytes()) == INPUT_FULL_SHA,
            'Pinned compatibility candidate mismatch')
    old_key, new_key = load_private_pair(pair_dir, new_id)
    with zipfile.ZipFile(input_ipa) as archive:
        native, swf = archive.read(NATIVE_MEMBER), archive.read(SWF_MEMBER)
    current = json.loads(Path(carrier_report).read_text('utf8'))
    require(current['native_sha256'] == sha(native) and len(current['functions']) == 80, 'Compatibility function receipt mismatch')
    patched, new_swf, new_full, proof = patch_carrier(native, swf, full_abc.read_bytes(), new_id, new_key, old_key)
    for function in current['functions']:
        start, size = function['file_offset'], function['size']
        require(native[start:start + size] == patched[start:start + size]
                and sha(patched[start:start + size]) == function['sha256'], 'Compatibility native function changed')
    del old_key, new_key
    output_ipa.parent.mkdir(parents=True, exist_ok=True)
    output_full.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_ipa) as source, zipfile.ZipFile(output_ipa, 'w', allowZip64=True) as target:
        target.comment = source.comment
        for item in source.infolist():
            data = patched if item.filename == NATIVE_MEMBER else new_swf if item.filename == SWF_MEMBER else source.read(item)
            target.writestr(copy.copy(item), data)
    output_full.write_bytes(new_full)
    with zipfile.ZipFile(input_ipa) as source, zipfile.ZipFile(output_ipa) as target:
        require(source.namelist() == target.namelist() and source.comment == target.comment, 'Package metadata/order changed')
        require(target.testzip() is None, 'Output IPA CRC failure')
        changed = []
        for a, b in zip(source.infolist(), target.infolist()):
            require(all(getattr(a, key) == getattr(b, key) for key in
                        ('filename', 'date_time', 'compress_type', 'comment', 'extra', 'create_system', 'external_attr')),
                    'Package member metadata changed')
            if source.read(a) != target.read(b):
                changed.append(a.filename)
        require(set(changed) == {NATIVE_MEMBER, SWF_MEMBER}, 'Unexpected IPA payload change')
        require(sha(target.read(NATIVE_MEMBER)) == sha(patched) and sha(target.read(SWF_MEMBER)) == sha(new_swf),
                'Packaged admission carrier mismatch')
    work.mkdir(parents=True)
    report = dict(status='unsigned_admission_rotated_offline', input_ipa_sha256=INPUT_IPA_SHA,
                  input_full_abc_sha256=INPUT_FULL_SHA, old_admission_id=OLD_ID, new_admission_id=new_id,
                  platform='ios', private_pair_verified=True, ipa=str(output_ipa), ipa_sha256=sha(output_ipa.read_bytes()),
                  full_abc=str(output_full), full_abc_sha256=sha(new_full), full_abc_sha1=hashlib.sha1(new_full).hexdigest(),
                  native_sha256=sha(patched), swf_sha256=sha(new_swf), changed_members=changed,
                  compatibility_functions_byte_identical=80, aot_method_count=METHOD_COUNT,
                  native_recompiled=False, native_executed=False, device_tested=False,
                  accepted_registry_changed=False, server_config_changed=False, **proof)
    dump(work / 'rotation-report.json', report)
    print(json.dumps({key: report[key] for key in ('status', 'new_admission_id', 'ipa_sha256', 'full_abc_sha256')}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input-ipa', 'full-abc', 'pair-dir', 'carrier-report', 'output-ipa', 'output-full', 'work'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--new-id', required=True)
    args = parser.parse_args()
    run(args.input_ipa, args.full_abc, args.pair_dir, args.new_id, args.carrier_report,
        args.output_ipa, args.output_full, args.work)


if __name__ == '__main__':
    main()
