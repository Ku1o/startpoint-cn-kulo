"""Standard <=4KiB compact pages, exact page-payload reuse only.

Input is the prior 422KB audit table, never the native. Every augmented row,
personality and LSDA is preserved. No compiler, linker, or native write occurs.
"""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from collections import defaultdict
import bisect
import json
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode = True
SOURCE = Path(str(fc.REPO / 'client-patch'))
sys.path.insert(0, str(SOURCE / 'equipment-ios-repair'))
import compact_unwind as u

TASK = Path(str(fc.client() / 'revision-ios-dispatch-fix-20261031'))
ROOT = TASK / 'audit'
MASK = (1 << 64) - 1
POLY = 1099511628211

def require(ok, message):
    if not ok:
        raise ValueError(message)

def make_pages(entries, windows, sentinel, lsda):
    pages, cursor = [], 0
    def ordinary(start, stop):
        while start < stop:
            end = min(stop, start + 1021)
            while entries[end - 1][0] - entries[start][0] > 0xffffff:
                end -= 1
            pages.append(dict(entries=entries[start:end], lsda=[]))
            start = end
    for begin, end in sorted(windows):
        require(cursor <= begin < end, 'Overlapping chosen windows')
        ordinary(cursor, begin)
        pages.append(dict(entries=entries[begin:end], lsda=[]))
        cursor = end
    ordinary(cursor, len(entries))
    lsda_starts = [r[0] for r in lsda]
    for i, page in enumerate(pages):
        begin = page['entries'][0][0]
        end = pages[i + 1]['entries'][0][0] if i + 1 < len(pages) else sentinel
        lo, hi = bisect.bisect_left(lsda_starts, begin), bisect.bisect_left(lsda_starts, end)
        page['lsda'] = lsda[lo:hi]
    return pages

def serialize_reusing_payloads(model):
    common, personalities, pages = (model[k] for k in ('common', 'personalities', 'pages'))
    common_index = {encoding: i for i, encoding in enumerate(common)}
    require(len(common_index) == len(common) <= 256, 'Common encoding index invalid')
    co = 28
    po = co + len(common) * 4
    io = po + len(personalities) * 4
    lsda_offset = io + (len(pages) + 1) * 12
    payload_offset = lsda_offset + sum(len(p['lsda']) * 8 for p in pages)
    cursor, indices, lsda_blobs, blobs, cache, aliases = payload_offset, [], [], [], {}, []
    for index, page in enumerate(pages):
        entries = page['entries']
        require(1 <= len(entries) <= 1021, 'Compressed entry count exceeds standard maximum')
        base = entries[0][0]
        require(entries[-1][0] - base <= 0xffffff, 'Compressed relative offset overflow')
        values = [(common_index[encoding] << 24) | (address - base) for address, encoding in entries]
        blob = struct.pack('<IHHHH', 3, 12, len(entries), 12 + 4 * len(entries), 0) + struct.pack('<' + 'I' * len(values), *values)
        require(len(blob) <= 4096, 'Standard second-level page byte limit exceeded')
        if blob in cache:
            at, original_page = cache[blob]
            aliases.append(dict(page=index, payload_of_page=original_page, bytes=len(blob)))
        else:
            at = cursor
            cache[blob] = at, index
            blobs.append(blob)
            cursor += len(blob)
        indices.append((base, at, lsda_offset))
        encoded_lsda = b''.join(struct.pack('<II', *r) for r in page['lsda'])
        lsda_blobs.append(encoded_lsda)
        lsda_offset += len(encoded_lsda)
    indices.append((model['sentinel'], 0, lsda_offset))
    packed = struct.pack('<7I', 1, co, len(common), po, len(personalities), io, len(indices))
    packed += struct.pack('<' + 'I' * len(common), *common)
    packed += struct.pack('<' + 'I' * len(personalities), *personalities)
    packed += b''.join(struct.pack('<III', *row) for row in indices)
    packed += b''.join(lsda_blobs) + b''.join(blobs)
    return packed, aliases

def lookup_like_primary_reader(blob, address):
    _, co, nc, _, _, io, ni = struct.unpack_from('<7I', blob)
    indices = [struct.unpack_from('<III', blob, io + i * 12) for i in range(ni)]
    level = bisect.bisect_right([r[0] for r in indices], address) - 1
    require(0 <= level < ni - 1, 'PC outside index sentinel')
    base, at, _ = indices[level]
    kind, eo, count, enc_off, enc_count = struct.unpack_from('<IHHHH', blob, at)
    require(kind == 3 and 1 <= count <= 1021 and 12 + count * 4 + enc_count * 4 <= 4096, 'Nonstandard compressed page')
    require(at + eo + count * 4 <= len(blob), 'Entry bytes outside section')
    target, low, high = address - base, 0, count
    while low < high:
        mid = (low + high) // 2
        value = struct.unpack_from('<I', blob, at + eo + mid * 4)[0]
        offset = value & 0xffffff
        if offset <= target:
            if mid == count - 1 or (struct.unpack_from('<I', blob, at + eo + (mid + 1) * 4)[0] & 0xffffff) > target:
                low = mid
                break
            low = mid + 1
        else:
            high = mid
    value = struct.unpack_from('<I', blob, at + eo + low * 4)[0]
    encindex = value >> 24
    require(encindex < nc, 'This bounded all-common probe does not accept local encodings')
    encoding = struct.unpack_from('<I', blob, co + encindex * 4)[0]
    start = base + (value & 0xffffff)
    end = (base + (struct.unpack_from('<I', blob, at + eo + (low + 1) * 4)[0] & 0xffffff)) if low + 1 < count else indices[level + 1][0]
    require(start <= address < end, 'Primary-shaped range lookup missed PC')
    return start, end, encoding

def main():
    out = ROOT / 'unwind-payload-dedup-probe01'
    require(not out.exists(), 'Fresh probe output required')
    model = u.parse((ROOT / 'unwind-repacking-probe01/best-unwind-info.bin').read_bytes())
    source = json.loads((ROOT / 'unwind-repacking-probe01/RESULT.json').read_text('utf8'))
    capacity = source['original_capacity']
    entries = [r for p in model['pages'] for r in p['entries']]
    lsda = [r for p in model['pages'] for r in p['lsda']]
    common_set = set(model['common'])
    require(all(r[1] in common_set for r in entries), 'Probe requires all encodings in common table')
    tokens = [((entries[i][1] * 0x9e3779b185ebca87) ^ (entries[i + 1][0] - entries[i][0])) & MASK for i in range(len(entries) - 1)]
    prefix = [0]
    for value in tokens:
        prefix.append((prefix[-1] * POLY + value) & MASK)
    candidates = []
    for count in (64, 32, 16, 8):
        length, power = count - 1, pow(POLY, count - 1, 1 << 64)
        hashed = defaultdict(list)
        for begin in range(len(entries) - count + 1):
            end = begin + count
            if entries[end - 1][0] - entries[begin][0] > 0xffffff:
                continue
            h = (prefix[begin + length] - prefix[begin] * power) & MASK
            hashed[(h, entries[end - 1][1])].append(begin)
        for indexes in hashed.values():
            if len(indexes) < 2:
                continue
            # Do not trust rolling-hash equality; group exact normalized bytes.
            groups = defaultdict(list)
            for begin in indexes:
                base = entries[begin][0]
                signature = tuple((address - base, encoding) for address, encoding in entries[begin:begin + count])
                groups[signature].append(begin)
            for indexes in groups.values():
                chosen, last = [], -1
                for begin in indexes:
                    if begin >= last:
                        chosen.append((begin, begin + count))
                        last = begin + count
                estimated_gain = (len(chosen) - 1) * (12 + count * 4) - len(chosen) * 48
                if estimated_gain > 0:
                    candidates.append(dict(count=count, windows=chosen, estimated_gain=estimated_gain))
    candidates.sort(key=lambda r: -r['estimated_gain'])
    baseline_blob, baseline_aliases = serialize_reusing_payloads(model)
    best = dict(bytes=len(baseline_blob), windows=[], packed=baseline_blob, model=model, aliases=baseline_aliases)
    attempted = []
    selected = []
    for candidate in candidates[:80]:
        windows = []
        for begin, end in candidate['windows']:
            if not any(begin < z and a < end for a, z in selected):
                windows.append((begin, end))
        if len(windows) < 2:
            continue
        proposed = sorted(selected + windows)
        pages = make_pages(entries, proposed, model['sentinel'], lsda)
        candidate_model = dict(common=model['common'], personalities=model['personalities'], pages=pages, sentinel=model['sentinel'])
        packed, aliases = serialize_reusing_payloads(candidate_model)
        row = dict(window_entries=candidate['count'], occurrences=len(windows), pages=len(pages),
            aliases=len(aliases), bytes=len(packed), gain_from_previous=best['bytes'] - len(packed))
        attempted.append(row)
        if len(packed) < best['bytes']:
            selected = proposed
            best = dict(bytes=len(packed), windows=selected, packed=packed, model=candidate_model, aliases=aliases)
            if len(packed) <= capacity:
                break
    parsed = u.parse(best['packed'])
    require(parsed == best['model'], 'Deduplicated binary parse differs from intended pages')
    require([r for page in parsed['pages'] for r in page['entries']] == entries, 'Any augmented boundary or encoding changed')
    require([r for page in parsed['pages'] for r in page['lsda']] == lsda, 'LSDA rows changed')
    require(parsed['personalities'] == model['personalities'], 'Personality rows changed')
    # Sample all starts plus the last instruction before each range end. This
    # reader follows Apple's binary-search/first-level-base algorithm directly.
    checks = 0
    for index, (start, encoding) in enumerate(entries):
        end = entries[index + 1][0] if index + 1 < len(entries) else model['sentinel']
        for address in (start, end - 1):
            actual = lookup_like_primary_reader(best['packed'], address)
            require(actual == (start, end, encoding), 'Primary-shaped lookup semantic drift')
            checks += 1
    negatives = []
    def rejects(label, blob):
        try:
            changed = u.parse(blob)
            equal = [r for page in changed['pages'] for r in page['entries']] == entries
            require(equal, 'Negative changed semantics')
        except (ValueError, struct.error):
            negatives.append(label)
            return
        raise ValueError('Negative control escaped: ' + label)
    io = struct.unpack_from('<I', best['packed'], 20)[0]
    first_at = struct.unpack_from('<I', best['packed'], io + 4)[0]
    damaged = bytearray(best['packed'])
    damaged[first_at + 12] ^= 4
    rejects('corrupt_shared_entry', damaged)
    oversized = bytearray(best['packed'])
    struct.pack_into('<H', oversized, first_at + 6, 1022)
    try:
        lookup_like_primary_reader(oversized, entries[0][0])
    except ValueError:
        negatives.append('reject_nonstandard_1022_entry_page')
    else:
        raise ValueError('Oversized standard-page guard escaped')
    out.mkdir()
    (out / 'best-unwind-info.bin').write_bytes(best['packed'])
    result = dict(status='standard_page_payload_reuse_probe_complete', original_capacity=capacity,
        initial_bytes=len(baseline_blob), final_bytes=best['bytes'], fits=best['bytes'] <= capacity,
        spare=capacity - best['bytes'], original_rows=source['original_entry_count'], augmented_rows=len(entries),
        all_augmented_rows_exact=True, old_zero_boundaries_preserved=True, personalities_exact=True, lsda_exact=True,
        compressed_pages=len(parsed['pages']), max_compressed_entries=max(len(p['entries']) for p in parsed['pages']),
        max_payload_bytes=max(12 + 4 * len(p['entries']) for p in parsed['pages']),
        repeated_window_candidates=len(candidates), attempts=attempted, selected_windows=best['windows'],
        exact_payload_aliases=best['aliases'], binary_search_queries=checks, negative_controls=negatives,
        source_reader='https://github.com/apple-oss-distributions/libunwind/blob/main/libunwind/src/UnwindCursor.hpp#L1605-L1669',
        source_format='https://github.com/apple-oss-distributions/libunwind/blob/main/libunwind/include/mach-o/compact_unwind_encoding.h#L375-L439',
        no_native_read_or_write=True, best_binary=str(out / 'best-unwind-info.bin'),
        limitation='Independent Python port of primary lookup algorithm; no actual iOS loader/unwinder execution')
    (out / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps({k: result[k] for k in ('status','original_capacity','initial_bytes','final_bytes','fits','spare','augmented_rows','compressed_pages','repeated_window_candidates','binary_search_queries','negative_controls','best_binary')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
