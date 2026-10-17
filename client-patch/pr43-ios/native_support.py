"""Shared, non-executing helpers for prepared arm64 AOT deltas.

Historical modules are imported only for their parsing and relocation APIs;
their fixed-input command line entry points are never invoked.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUPPORT = Path(__file__).resolve().parent / 'support'
INFO_OFFSET = 104549248


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n', 'utf8')


def backend():
    sys.path[:0] = [str(SUPPORT), str(REPO / 'client-patch/ios-cumulative-login'),
                    str(REPO / 'client-patch/ios-shop-first-open'),
                    str(REPO / 'client-patch/lens0907-0908')]
    import pr43_backend
    return pr43_backend


def read_report(path):
    path = Path(path).resolve()
    port = json.loads(path.read_text('utf-8-sig'))
    assert int(port['old_methods']) <= int(port['total_methods'])
    return path, port


def input_path(report, name):
    value = Path(name)
    return value if value.is_absolute() else Path(report).parent / value


def wanted_methods(port):
    """All functions needed by the new table, plus explicit replacements."""
    wanted = set(range(int(port['old_methods']), int(port['total_methods'])))
    wanted.update(int(x) for x in port.get('compiled_helpers', []))
    wanted.update(int(x) for x in port.get('new_method_ids', []))
    for row in port.get('methods', []):
        if row.get('strategy', 'replace') == 'replace':
            value = row.get('compiled')
            wanted.add(int(row['method_id'] if value is None else value))
    wanted.update(int(x['compiled']) for x in port.get('method_redirects', []))
    assert wanted and min(wanted) >= 0 and max(wanted) < port['total_methods']
    return wanted


def verify_warnings(path, tracked):
    warnings = [x for x in Path(path).read_text('utf8', errors='replace').splitlines()
                if 'Verify error:' in x]
    rejected = []
    for line in warnings:
        match = re.search(r'Verify error:\s*[^:]+:(\d+):', line)
        # An unparseable warning cannot be silently attributed to the baseline.
        if not match or int(match.group(1)) in tracked:
            rejected.append(line)
    assert not rejected, ('target method verifier failure', rejected, str(path))
    return warnings


def read64(data, at):
    return struct.unpack_from('<Q', data, at)[0]


def write64(data, at, value):
    struct.pack_into('<Q', data, at, value)


def check_definitions(old, fresh, prepared):
    """Old pools and layouts keep their IDs; adding old-class slots is refused."""
    link = backend()
    for field in ('methods', 'metadata', 'scripts', 'ints', 'uints', 'doubles',
                  'strings', 'namespaces', 'ns_sets', 'multinames'):
        rows = getattr(old, field)
        assert link.freeze(rows) == link.freeze(getattr(fresh, field)[:len(rows)]), field
    for section in ('instances', 'classes'):
        assert link.freeze(getattr(fresh, section)) == link.freeze(getattr(prepared, section)), section
        for previous, current in zip(getattr(old, section), getattr(fresh, section)):
            assert link.freeze(previous[:-1]) == link.freeze(current[:-1]), section
            before, after = previous[-1], current[-1]
            assert link.freeze(before) == link.freeze(after[:len(before)]), section
            assert not any(t.kind in (0, 6) for t in after[len(before):]), \
                ('new slot on existing class requires explicit ABI validation', section)


def source_inputs(report, port):
    native = input_path(report, port.get('baseline_native_file', 'baseline-native')).read_bytes()
    swf = input_path(report, port.get('baseline_swf_file', 'baseline.swf')).read_bytes()
    full = input_path(report, port['full_abc_file']).read_bytes()
    reg = port['source_ipa']
    assert sha(native) == reg['native_sha256']
    assert sha(swf) == reg['swf_sha256']
    assert sha(full) == port['full_abc_sha256']
    assert read64(native, INFO_OFFSET + 56) == port['old_methods']
    return native, swf, full


def verify_entry_aliases(native, port, wanted):
    """Entry hooks affect every native table alias, not just the written ID."""
    link = backend()
    count = int(port['old_methods'])
    offset = link.file_offset(native, read64(native, INFO_OFFSET + 48), count * 8)
    addresses = struct.unpack_from('<' + 'Q' * count, native, offset)
    reverse = {}
    for method, address in enumerate(addresses):
        reverse.setdefault(address, []).append(method)
    permitted = {int(k): set(map(int, v)) for k, v in
                 port.get('permitted_native_entry_aliases', {}).items()}
    result = {}
    targets = set(wanted) & set(range(count))
    targets.update(int(r['original']) for r in port.get('method_redirects', []))
    for method in targets:
        aliases = set(reverse[addresses[method]]) - {method}
        assert not aliases & targets, ('multiple replacements share a native entry', method, sorted(aliases & targets))
        assert aliases <= permitted.get(method, set()), \
            ('unreviewed native entry aliases', method, sorted(aliases), hex(addresses[method]))
        if aliases:
            result[str(method)] = dict(address=addresses[method], aliases=sorted(aliases))
    return result


def current_origin(native):
    # Constructor instruction decoding is reused; the historical module's
    # PUBLIC_HOST constant deliberately does not define this port's endpoint.
    backend()
    from public_endpoint import constructor_origin
    result = constructor_origin(native)
    origin = result['origin'] if isinstance(result, dict) else result
    assert origin == 'http://124.222.203.221', ('unexpected initial endpoint', origin)
    return result


def dependency_info(native, name, dependencies):
    """Bind an SDK/library AOT unit by its exact original ABC identity."""
    link = backend()
    match = re.fullmatch(r'_(\d+-.+)_(\d+)_aotInfo', name)
    assert match and int(match.group(1).split('-')[0]) == int(match.group(2)), name
    path = Path(dependencies) / (match.group(1) + '.abc')
    from fixed_inputs import fixed_json
    assert path.name in fixed_json('dependency-hashes.json'), 'Unregistered dependency ABC'
    source = path.read_bytes()
    assert sha(source) == fixed_json('dependency-hashes.json')[path.name], 'Dependency ABC hash mismatch'
    digest = hashlib.sha1(source).digest()
    offset = native.find(digest)
    assert offset >= 0 and native.find(digest, offset + 1) < 0, ('dependency identity not unique', name)
    address = link.aot.IMAGE_BASE + offset
    assert link.file_offset(native, address, 168) == offset and offset % 8 == 0
    abc = link.abcfmt.ABC(source)
    assert read64(native, offset + 56) == len(abc.methods), ('dependency method count', name)
    size = read64(native, offset + 32)
    start = link.file_offset(native, read64(native, offset + 24), size)
    runtime = link.abcfmt.ABC(native[start:start + size])
    for field in ('methods', 'metadata', 'instances', 'classes', 'scripts', 'ints',
                  'uints', 'doubles', 'strings', 'namespaces', 'ns_sets', 'multinames'):
        assert link.freeze(getattr(runtime, field)) == link.freeze(getattr(abc, field)), (name, field)
    return dict(address=address, file_offset=offset, abc_file=str(path), abc_sha256=sha(source),
                abc_sha1=digest.hex(), method_count=len(abc.methods),
                runtime_abc_sha256=sha(native[start:start + size]),
                metadata_identical=True, native_bytes=native[offset:offset + 32].hex())


def symbol_record(obj, path, name, identifier):
    """Slice a defined text symbol, including generated activation handlers."""
    link = backend()
    symbols = list(obj.symbols)
    symbol = next(s for s in symbols if link.aot.text(s.name) == name and s.numberof_sections)
    section = link.aot.find_section(obj, symbol)
    assert section.name == '__text', ('not an executable symbol', name, section.name)
    boundaries = [s.value for s in symbols if s.numberof_sections == symbol.numberof_sections
                  and s.value > symbol.value
                  and not link.aot.text(s.name).startswith(('ltmp', 'lCPI'))]
    end = min(boundaries, default=section.virtual_address + section.size)
    record = link.aot.FunctionRecord(identifier, name, symbol.value, end)
    return record, path, section, symbols, link.aot.parse_relocations(path, section, symbols, record)


def activation_tail(obj, name, old_count, count):
    """Return new descriptors and their unsigned pointer relocations."""
    link = backend()
    symbol = next(s for s in obj.symbols if link.aot.text(s.name) == name and s.numberof_sections)
    section = link.aot.find_section(obj, symbol)
    tail = bytearray(link.aot.extract_symbol_bytes(obj, name, count * 16)[old_count * 16:])
    for offset in range(0, len(tail), 16):
        init_id = struct.unpack_from('<i', tail, offset)[0]
        assert init_id == -1 or 0 <= init_id < count, ('activation initializer ID', init_id)
    return tail, section, symbol.value - section.virtual_address + old_count * 16


def activation_relocations(path, obj, section, start, size):
    raw = Path(path).read_bytes()
    symbols = list(obj.symbols)
    result = []
    for index in range(section.numberof_relocations):
        at, word = struct.unpack_from('<iI', raw, section.relocation_offset + index * 8)
        if not start <= at < start + size:
            continue
        assert word >> 28 == 0 and ((word >> 25) & 3) == 3 and (word >> 27) & 1, \
            ('activation pointer relocation', at, hex(word))
        offset = at - start
        assert offset % 16 == 8, ('activation relocation outside initHandler', offset)
        result.append(dict(offset=offset, symbol=backend().aot.text(symbols[word & 0xffffff].name)))
    return result


def verify_signing_models(native):
    """Model both signature-tail replacement and TrollStore's actual trim."""
    link = backend()
    from macho_signing_layout import (assert_signable_layout, ldid_code_limit,
                                     linkedit_ranges, signature_range)
    assert_signable_layout(native)
    command, signature, _ = signature_range(native)
    ranges = linkedit_ranges(native)
    expected = link.read_rebase(native)['entries']
    checked = []
    for mode, limit in (('signature', signature), ('ldid', ldid_code_limit(native))):
        for size in (0x80000, 0x200000, 0x400000):
            result = bytearray(native[:limit])
            result.extend(struct.pack('>III', 0xfade0cc0, size, 0) + b'\xa5' * (size - 12))
            struct.pack_into('<II', result, command + 8, limit, size)
            tail = link.segments(result)[-1]
            length = len(result) - tail['off']
            struct.pack_into('<Q', result, tail['command'] + 48, length)
            struct.pack_into('<Q', result, tail['command'] + 32, link.aot.align(length, 0x4000))
            assert_signable_layout(result)
            assert link.read_rebase(result)['entries'] == expected
            for row in ranges:
                at, end = row['offset'], row['offset'] + row['size']
                assert result[at:end] == native[at:end], (mode, size, row['name'])
            checked.append(dict(mode=mode, signature_size=size, loader_metadata_preserved=True))
    return checked
