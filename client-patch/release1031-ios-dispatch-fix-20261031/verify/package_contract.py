"""Bounded actual-IPA readback and exact non-target member preservation."""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()

import hashlib
import json
from pathlib import Path
import plistlib
import struct
import zipfile

from dispatch_contract import require

CHUNK = 1024 * 1024
MEMBER_NATIVE = 'Payload/worldflipper.app/worldflipper'
MEMBER_SWF = 'Payload/worldflipper.app/worldflipper_ios_release.swf'
MAX_NATIVE = 512 * CHUNK
MAX_SWF = 32 * CHUNK


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while raw := stream.read(CHUNK):
            h.update(raw)
    return h.hexdigest()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def equal_file(raw, path):
    path = Path(path)
    require(path.stat().st_size == len(raw), 'Loose/IPA payload size differs: ' + path.name)
    with path.open('rb') as stream:
        for at in range(0, len(raw), CHUNK):
            require(stream.read(CHUNK) == raw[at:at + CHUNK], 'Loose/IPA payload bytes differ: ' + path.name)


def member_payload(zipper, info):
    zipper.fp.seek(info.header_offset)
    header = zipper.fp.read(30)
    require(header[:4] == b'PK\x03\x04', 'Invalid ZIP local header')
    name_len, extra_len = struct.unpack_from('<HH', header, 26)
    tail = zipper.fp.read(name_len + extra_len)
    return header + tail, zipper.fp.tell()


def same_compressed(old, a, new, b):
    old_header, old_at = member_payload(old, a)
    new_header, new_at = member_payload(new, b)
    if a.compress_size != b.compress_size:
        return False, old_header, new_header
    old.fp.seek(old_at)
    new.fp.seek(new_at)
    remaining = a.compress_size
    same = True
    while remaining:
        size = min(CHUNK, remaining)
        left, right = old.fp.read(size), new.fp.read(size)
        require(len(left) == len(right) == size, 'Truncated compressed ZIP member')
        same &= left == right
        remaining -= size
    return same, old_header, new_header


def readback(package, linked, previous_package, baseline_receipt, image_type):
    """Compatible with verify_stages.package_readback, without whole-IPA copies.

    The fixed input IPA's already-confirmed digest is reused explicitly. Its
    actual native/SWF are read and hashed here; every other local header and
    compressed member is compared directly with the final IPA once.
    """
    source = linked['source_ipa']
    path, baseline = Path(package['ipa']), Path(source['ipa'])
    receipt = json.loads(Path(baseline_receipt).read_text('utf-8-sig'))
    require(Path(receipt['ipa']).resolve() == baseline.resolve(), 'Reused baseline receipt points elsewhere')
    require(receipt['ipa_sha256'] == source['ipa_sha256'] == previous_package['ipa_sha256'],
            'Reused baseline IPA identity mismatch')
    require((source['native_member'], source['swf_member']) == (MEMBER_NATIVE, MEMBER_SWF),
            'Unexpected replacement member names')
    require(file_sha(path) == package['ipa_sha256'], 'Final IPA streamed digest mismatch')
    changed = []
    with zipfile.ZipFile(baseline) as old, zipfile.ZipFile(path) as new:
        require(old.namelist() == new.namelist()
                and len(set(new.namelist())) == len(new.namelist()), 'ZIP order/members/duplicates changed')
        require(old.comment == new.comment, 'ZIP archive comment changed')
        for a, b in zip(old.infolist(), new.infolist()):
            require(all(getattr(a, key) == getattr(b, key) for key in
                        ('filename', 'date_time', 'compress_type', 'comment', 'extra',
                         'create_system', 'create_version', 'extract_version', 'flag_bits',
                         'internal_attr', 'external_attr')), 'ZIP member metadata changed: ' + a.filename)
            same, old_header, new_header = same_compressed(old, a, new, b)
            if not same:
                changed.append(a.filename)
                require(a.filename in (MEMBER_NATIVE, MEMBER_SWF), 'Unexpected changed member: ' + a.filename)
            else:
                require((a.CRC, a.file_size, a.compress_size) == (b.CRC, b.file_size, b.compress_size),
                        'Unchanged member CRC/size changed')
                require(old_header == new_header, 'Unchanged ZIP local header changed: ' + a.filename)
        require(set(changed) == {MEMBER_NATIVE, MEMBER_SWF}, 'Native/SWF replacement set differs')
        for archive in (old, new):
            require(archive.getinfo(MEMBER_NATIVE).file_size <= MAX_NATIVE, 'Native readback size bound')
            require(archive.getinfo(MEMBER_SWF).file_size <= MAX_SWF, 'SWF readback size bound')
        # zipfile verifies both changed payload CRCs during these reads.
        previous_native, native = old.read(MEMBER_NATIVE), new.read(MEMBER_NATIVE)
        previous_swf, swf = old.read(MEMBER_SWF), new.read(MEMBER_SWF)
        old_plist = plistlib.loads(old.read('Payload/worldflipper.app/Info.plist'))
        plist = plistlib.loads(new.read('Payload/worldflipper.app/Info.plist'))
        require(old_plist == plist, 'Bundle Info.plist changed')
        identity = tuple(plist[x] for x in ('CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion'))
        require(identity == ('com.kulo.wf', '1.8.4', '1.8.46'), 'Bundle identity changed')
        unchanged = len(new.infolist()) - 2
    require(sha(native) == package['native_sha256'] == linked['native_sha256'], 'Final native/report identity mismatch')
    require(sha(swf) == package['swf_sha256'] == linked['swf_sha256'], 'Final SWF/report identity mismatch')
    require(sha(previous_native) == source['native_sha256'] == receipt['native_sha256'], 'Actual input native differs')
    require(sha(previous_swf) == source['swf_sha256'] == receipt['swf_sha256'], 'Actual input SWF differs')
    equal_file(native, linked['native_file'])
    equal_file(swf, linked['swf_file'])
    return image_type(previous_native), image_type(native), previous_swf, swf, dict(
        changed_members=changed, unchanged_compressed_members_exact=unchanged,
        unchanged_local_headers_exact=True, replacement_payload_crc_verified=True,
        package_identity=list(identity), baseline_ipa_digest_reused_from=str(Path(baseline_receipt).resolve()),
        final_ipa_digest_streamed=True, compressed_comparison_chunk_bytes=CHUNK)


def chunked_prefix(old, new, allowed, chunk_bytes=CHUNK):
    end = old.segments[-1]['off']
    ranges = []
    for lo, hi in allowed:
        require(0 <= lo <= hi, 'Reversed allowed native range')
        if lo < end and hi > 0:
            ranges.append((max(0, lo), min(end, hi)))
    count = 0
    for at in range(0, end, chunk_bytes):
        stop = min(end, at + chunk_bytes)
        before, after = old.raw[at:stop], bytearray(new.raw[at:stop])
        for lo, hi in ranges:
            left, right = max(at, lo), min(stop, hi)
            if left < right:
                after[left-at:right-at] = before[left-at:right-at]
        require(after == before, 'Unexpected existing native bytes changed at chunk ' + hex(at))
        count += 1
    return dict(bytes_compared=end, chunks=count, chunk_bytes=chunk_bytes)


def prefix_selftest():
    from types import SimpleNamespace as NS
    original = bytes(range(256)) * 4
    old = NS(raw=original, segments=[{'off': len(original)}])
    changed = bytearray(original)
    changed[126:130] = b'ABCD'
    chunked_prefix(old, NS(raw=changed), [(126, 130)], 127)
    rejected = []
    for where in (125, 130, 700):
        bad = bytearray(changed)
        bad[where] ^= 1
        try:
            chunked_prefix(old, NS(raw=bad), [(126, 130)], 127)
        except ValueError:
            rejected.append(where)
        else:
            raise ValueError('Native-prefix corruption escaped independent check')
    return dict(passed=4, rejected_offsets=rejected, scope='1KiB in-memory positive/negative controls')
