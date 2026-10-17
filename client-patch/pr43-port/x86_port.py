"""Append the audited emulator ABI to a chosen APK, without replacing game code.

Standard library only. Produces an unsigned, unaligned intermediate APK. Both
input hashes are mandatory; use tree_hash() to identify the extracted input set.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

EXT = 'assets/META-INF/AIR/extensions/'
LIBS = frozenset(('Core SocketHelper c++_shared entryexpro execgame fakedyn '
                 'fakedyn_x86 getuiext3 secsdk sobot tracepath uptsmaddon '
                 'uptsmaddonmi wordfilter ysshared').split())
ANES = frozenset(('com.digitalstrawberry.ane.share com.distriqt.Battery '
                 'com.distriqt.Core com.gbitstools com.gibits.leitingaar '
                 'com.tuarua.frekotlin jp.cygames.GooglePlayServicesANE '
                 'pinball.ane.getbuild pinball.ane.googleId pinball.assetDownload '
                 'pinball.checkapp pinball.screen pinball.vibration').split())


class PortError(ValueError):
    """An explicit input, compatibility, or output invariant failed."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if (not name or '\\' in name or '\x00' in name or p.is_absolute()
            or any(s in ('', '.', '..') for s in name.rstrip('/').split('/'))
            or ':' in name):
        raise PortError(f'unsafe ZIP/input path: {name!r}')
    return name


def signature(name):
    # Only APK v1 signature files directly under META-INF. Nested AIR/ANE
    # metadata and similarly named ordinary resources are never discarded.
    return bool(re.fullmatch(r'META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC)|SIG-[^/]+)', name, re.I))


def input_files(root):
    root = Path(root).resolve(strict=True)
    files = {}
    # Preserve the audited WindowsPath ordering on every host OS.
    ordered = sorted(root.rglob('*'), key=lambda p: (
        tuple(part.casefold() for part in p.relative_to(root).parts),
        p.relative_to(root).as_posix()))
    for p in ordered:
        if p.is_symlink() or not p.resolve().is_relative_to(root):
            raise PortError(f'linked input is forbidden: {p}')
        if p.is_file():
            files[safe_name(p.relative_to(root).as_posix())] = p
    return files


def tree_hash(root):
    """SHA256 over path/size/digest records in the audited Windows path order."""
    h = hashlib.sha256()
    for n, p in input_files(root).items():
        b = p.read_bytes()
        h.update(f'{n}\0{len(b)}\0{sha(b)}\n'.encode('utf-8'))
    return h.hexdigest()


def elf_exports(b, machine=None):
    if len(b) < 64 or b[:6] != b'\x7fELF\x02\x01':
        raise PortError('expected little-endian ELF64')
    actual = struct.unpack_from('<H', b, 18)[0]
    if machine is not None and actual != machine:
        raise PortError(f'wrong ELF machine: {actual}, expected {machine}')
    try:
        off = struct.unpack_from('<Q', b, 40)[0]
        size, count = struct.unpack_from('<HH', b, 58)
        if size < 64 or not count or off + size * count > len(b):
            raise PortError('missing or truncated ELF section table')
        sections = [struct.unpack_from('<IIQQQQIIQQ', b, off + i * size) for i in range(count)]
        exports = set()
        for s in sections:
            if s[1] != 11:  # SHT_DYNSYM
                continue
            strings = sections[s[6]]
            tab = b[strings[4]:strings[4] + strings[5]]
            if s[9] != 24 or s[4] + s[5] > len(b) or s[5] % 24:
                raise PortError('invalid dynamic symbol table')
            for pos in range(s[4], s[4] + s[5], 24):
                index, info, other, shndx, value, length = struct.unpack_from('<IBBHQQ', b, pos)
                if shndx and index and (info >> 4) in (1, 2):
                    exports.add(tab[index:tab.index(b'\0', index)].decode('ascii'))
        if not exports:
            raise PortError('ELF has no defined dynamic exports')
        return exports
    except (struct.error, IndexError, UnicodeError, ValueError) as e:
        raise PortError(f'invalid ELF exports: {e}') from e


def elf_needed(b):
    """Read actual DT_NEEDED entries, rather than guessing dependencies by name."""
    try:
        off = struct.unpack_from('<Q', b, 40)[0]
        size, count = struct.unpack_from('<HH', b, 58)
        sections = [struct.unpack_from('<IIQQQQIIQQ', b, off + i * size) for i in range(count)]
        needed = []
        for s in sections:
            if s[1] != 6:
                continue
            strings = sections[s[6]]
            tab = b[strings[4]:strings[4] + strings[5]]
            if s[9] != 16 or s[4] + s[5] > len(b) or s[5] % 16:
                raise PortError('invalid dynamic dependency table')
            for pos in range(s[4], s[4] + s[5], 16):
                tag, value = struct.unpack_from('<QQ', b, pos)
                if tag == 1:
                    needed.append(tab[value:tab.index(b'\0', value)].decode('ascii'))
        return sorted(set(needed))
    except (struct.error, IndexError, UnicodeError, ValueError) as e:
        raise PortError(f'invalid ELF dependencies: {e}') from e


def xml_root(b):
    if b'<!DOCTYPE' in b.upper() or b'<!ENTITY' in b.upper():
        raise PortError('XML entities/DTD are forbidden')
    try:
        return ET.fromstring(b)
    except ET.ParseError as e:
        raise PortError(f'invalid ANE XML: {e}') from e


def shape(el):
    return (el.tag, tuple(sorted(el.attrib.items())), (el.text or '').strip(), tuple(shape(c) for c in el))


def platform(root, name):
    found = [e for e in root.iter() if e.tag.rsplit('}', 1)[-1] == 'platform' and e.get('name') == name]
    if len(found) > 1:
        raise PortError(f'duplicate ANE platform {name}')
    return found[0] if found else None


def patched_xml(base, supplied):
    root, donor = xml_root(base), xml_root(supplied)
    arm, x64 = platform(root, 'Android-ARM64'), platform(donor, 'Android-x64')
    if arm is None or x64 is None:
        raise PortError('ANE lacks ARM64 base or x64 donor platform')
    clone = copy.deepcopy(arm)
    clone.set('name', 'Android-x64')
    if shape(clone) != shape(x64):
        raise PortError('ANE native initializer/finalizer platform API differs')
    existing = platform(root, 'Android-x64')
    if existing is not None:
        if shape(existing) != shape(clone):
            raise PortError('conflicting existing ANE x64 platform')
        return base
    # Preserve all original descriptor bytes; inject only the matching platform.
    text = base.decode('utf-8')
    matches = list(re.finditer(r'<platform\s+name="Android-ARM64"\s*>.*?</platform>', text, re.S))
    if len(matches) != 1:
        raise PortError('unsupported ARM64 descriptor serialization')
    m = matches[0]
    result = (text[:m.end()] + '\n' + m[0].replace('name="Android-ARM64"', 'name="Android-x64"', 1) + text[m.end():]).encode('utf-8')
    if shape(platform(xml_root(result), 'Android-x64')) != shape(clone):
        raise PortError('injected descriptor failed round-trip')
    return result


def port(base, inputs, output, *, base_sha256, inputs_sha256, output_root):
    base, inputs, output = Path(base), Path(inputs), Path(output)
    if any('.cdn' in [part.lower() for part in p.absolute().parts] for p in (output, Path(output_root))):
        raise PortError('read-only CDN output boundary')
    output_root = Path(output_root).resolve()
    if '.cdn' in [part.lower() for part in output_root.parts]:
        raise PortError('read-only CDN output boundary')
    if output.resolve() == output_root or output.resolve().is_relative_to(inputs.resolve()):
        raise PortError('output must be separate from the input tree')
    if not output.resolve().is_relative_to(output_root) or output.exists():
        raise PortError('output must be a new file inside the permitted output root')
    if not re.fullmatch('[0-9a-f]{64}', base_sha256) or sha(base.read_bytes()) != base_sha256:
        raise PortError('base SHA256 mismatch')
    if not re.fullmatch('[0-9a-f]{64}', inputs_sha256) or tree_hash(inputs) != inputs_sha256:
        raise PortError('input tree SHA256 mismatch')
    files = input_files(inputs)
    libs = {f'lib/x86_64/lib{n}.so' for n in LIBS}
    if {n for n in files if n.startswith('lib/')} != libs:
        raise PortError('input must contain exactly the audited 15 native libraries')
    edits, adds, consumed, evidence, dependencies = {}, {}, set(libs), {}, {}
    with zipfile.ZipFile(base) as src:
        infos = src.infolist()
        names = [safe_name(i.filename) for i in infos]
        if len(names) != len(set(names)):
            raise PortError('duplicate ZIP members')
        if any(i.flag_bits & 1 for i in infos):
            raise PortError('encrypted ZIP members unsupported')
        names = set(names)
        arm_names = {n.rsplit('/', 1)[-1] for n in names if n.startswith('lib/arm64-v8a/') and n.endswith('.so')}
        if arm_names != {Path(n).name for n in libs}:
            raise PortError('base ARM64 native library roster differs')
        arm_core = src.read('lib/arm64-v8a/libCore.so')
        if b'33.1.1.620' not in arm_core or b'Android-ARM64' not in arm_core:
            raise PortError('base AIR must be 33.1.1.620 / Android-ARM64')
        for n in sorted(libs):
            b = files[n].read_bytes()
            exports = elf_exports(b, 62)
            if not n.endswith('/libc++_shared.so') and 'JNI_OnLoad' not in exports:
                raise PortError(f'native JNI_OnLoad missing: {n}')
            needed = elf_needed(b)
            android_system = {'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libz.so',
                              'libGLESv2.so', 'libEGL.so', 'libjnigraphics.so'}
            unresolved = set(needed) - android_system - arm_names
            if unresolved:
                raise PortError(f'unresolved x64 native dependencies: {n}: {sorted(unresolved)}')
            dependencies[Path(n).name] = needed
            if n.endswith('/libCore.so') and (b'33.1.1.620' not in b or b'Android-x64' not in b):
                raise PortError('x64 AIR version/platform mismatch')
            if Path(n).name in ('libCore.so', 'libSocketHelper.so', 'libentryexpro.so'):
                arm_exports = elf_exports(src.read('lib/arm64-v8a/' + Path(n).name), 183)
                aj = {s for s in arm_exports if s.startswith('Java_')}
                xj = {s for s in exports if s.startswith('Java_')}
                if not aj or aj != xj:
                    raise PortError(f'JNI API mismatch: {n}; missing={sorted(aj-xj)}; extra={sorted(xj-aj)}')
                evidence[Path(n).name] = {'matchingJavaExports': len(aj)}
            if n in names:
                if src.read(n) != b:
                    raise PortError(f'conflicting existing native: {n}')
            else:
                adds[n] = (b, src.getinfo('lib/arm64-v8a/' + Path(n).name))
        descriptors = {n for n in names if n.startswith(EXT) and n.endswith('/META-INF/ANE/extension.xml')}
        if descriptors != {EXT + a + '/META-INF/ANE/extension.xml' for a in ANES}:
            raise PortError('base must contain exactly the audited 13 ANEs')
        resource_count = 0
        for desc in sorted(descriptors):
            if desc not in files:
                raise PortError(f'missing input descriptor: {desc}')
            edits[desc] = patched_xml(src.read(desc), files[desc].read_bytes())
            consumed.add(desc)
            arm_prefix = desc.rsplit('/', 1)[0] + '/Android-ARM64/'
            resource_names = {n for n in names if n.startswith(arm_prefix) and not n.endswith('/')}
            if not resource_names:
                raise PortError(f'empty ANE ARM64 resource set: {desc}')
            for arm_name in sorted(resource_names):
                target = arm_name.replace('/Android-ARM64/', '/Android-x64/', 1)
                if target not in files:
                    raise PortError(f'missing input ANE resource: {target}')
                b = files[target].read_bytes()
                if b.startswith(b'\x7fELF'):
                    raise PortError(f'cannot clone ABI-dependent ANE ELF resource: {target}')
                if src.read(arm_name) != b:
                    raise PortError(f'ANE ARM64 resource/API differs from audited x64 input: {target}')
                if target in names and src.read(target) != b:
                    raise PortError(f'conflicting existing ANE resource: {target}')
                if target not in names:
                    adds[target] = (b, src.getinfo(arm_name))
                consumed.add(target)
                resource_count += 1
        if set(files) != consumed:
            raise PortError(f'unexpected input files: {sorted(set(files)-consumed)}')
        allowed_existing_x64 = libs | {n for n in consumed if '/Android-x64/' in n}
        if any((n.startswith('lib/x86_64/') or '/Android-x64/' in n) and not n.endswith('/') and n not in allowed_existing_x64 for n in names):
            raise PortError('unexpected existing x64 library/resource')
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: never overwrite another task artifact. On write or
        # post-write verification failure, retain the candidate for diagnosis.
        with zipfile.ZipFile(output, 'x') as dst:
            dst.comment = src.comment
            for info in infos:
                if not signature(info.filename):
                    dst.writestr(copy.copy(info), edits.get(info.filename, src.read(info.filename)))
            for n, (b, template) in sorted(adds.items()):
                info = copy.copy(template)
                info.filename, info.orig_filename = n, n
                dst.writestr(info, b)
        with zipfile.ZipFile(output) as check:
            expected_names = (names - {n for n in names if signature(n)}) | set(adds)
            if set(check.namelist()) != expected_names or check.testzip() is not None:
                raise PortError('output member set/CRC verification failed')
            for n, (data, template) in adds.items():
                if check.read(n) != data:
                    raise PortError(f'added member readback differs: {n}')
            preserved, critical = 0, {}
            for info in infos:
                n = info.filename
                if signature(n):
                    continue
                if check.read(n) != edits.get(n, src.read(n)):
                    raise PortError(f'output bytes differ: {n}')
                current = check.getinfo(n)
                if any(getattr(current, k) != getattr(info, k) for k in ('compress_type', 'date_time', 'external_attr', 'comment', 'extra')):
                    raise PortError(f'output metadata differs: {n}')
                if n not in edits:
                    preserved += 1
                    if (n == 'AndroidManifest.xml' or re.fullmatch(r'classes\d*\.dex', n)
                            or n.startswith('lib/arm64-v8a/')
                            or (n.startswith('assets/') and n.count('/') == 1 and n.endswith('.swf'))
                            or n == 'META-INF/AIR/application.xml'):
                        critical[n] = sha(check.read(n))
    return {'baseSha256': base_sha256, 'inputsTreeSha256': inputs_sha256,
            'output': str(output.resolve()), 'outputSha256': sha(output.read_bytes()),
            'nativeCount': len(libs), 'aneCount': len(descriptors),
            'aneResourcesComparedByteForByte': resource_count,
            'jniAPI': evidence, 'nativeDependencies': dependencies, 'preservedMembers': preserved,
            'preservedCriticalMemberSha256': critical,
            'addedMembers': len(adds), 'descriptorMembers': len(edits),
            'unsigned': True, 'aligned': False, 'deviceTested': False,
            'limitations': 'SDK stubs are partial; export/resource equivalence does not prove native semantics or emulator/phone compatibility.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', required=True, type=Path)
    ap.add_argument('--base-sha256', required=True)
    ap.add_argument('--inputs', required=True, type=Path)
    ap.add_argument('--inputs-sha256', required=True)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--output-root', required=True, type=Path)
    args = ap.parse_args()
    print(json.dumps(port(args.base, args.inputs, args.output,
                         base_sha256=args.base_sha256, inputs_sha256=args.inputs_sha256,
                         output_root=args.output_root), indent=2))


if __name__ == '__main__':
    main()
