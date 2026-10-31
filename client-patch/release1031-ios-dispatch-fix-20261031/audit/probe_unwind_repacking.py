"""Read-only mmap/object probe of compact-unwind representation savings."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from collections import Counter
import bisect
import importlib.util
import json
import mmap
from pathlib import Path
import struct
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
TASK = Path(str(fc.client() / 'revision-ios-dispatch-fix-20261031'))
SOURCE = Path(str(fc.REPO / 'client-patch'))
sys.path[:0] = [str(SOURCE / 'equipment-ios-repair'), str(SOURCE / 'pr43-ios'),
    str(SOURCE / 'lens0907-0908'), str(SOURCE / 'ios-r11-port'),
    str(fc.tool('settings/recipe')), str(TASK.parent / 'ios'), str(fc.private('libraries'))]
import finalize_delta as f
import compact_unwind as u
import native_support as ns

def require(ok, message):
    if not ok:
        raise ValueError(message)

def paginate(ordered, lsda, sentinel, common):
    common_set = set(common)
    pages, cursor = [], 0
    lsda_starts = [r[0] for r in lsda]
    while cursor < len(ordered):
        end = cursor + 1
        local = {ordered[cursor][1]} - common_set
        while end < len(ordered):
            new_local = local | ({ordered[end][1]} - common_set)
            if (ordered[end][0] - ordered[cursor][0] > 0xffffff or
                    12 + 4 * (end - cursor + 1 + len(new_local)) > 4096 or
                    len(common) + len(new_local) > 256):
                break
            local = new_local
            end += 1
        next_start = ordered[end][0] if end < len(ordered) else sentinel
        lo = bisect.bisect_left(lsda_starts, ordered[cursor][0])
        hi = bisect.bisect_left(lsda_starts, next_start)
        pages.append(dict(entries=ordered[cursor:end], lsda=lsda[lo:hi]))
        cursor = end
    return pages

def main():
    out = TASK / 'audit/unwind-repacking-probe01'
    require(not out.exists(), 'Fresh probe output required')
    report = json.loads((TASK / 'linked01/link-report.json').read_text('utf8'))
    spec = importlib.util.spec_from_file_location('dispatch_probe_strict_switch', fc.tool('settings/recipe/finalize_final.py'))
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    link = ns.backend()
    with patch.object(f, 'verify_switch_tables', previous.strict_switch):
        functions = f._compile_functions(Path(report['compiled_report']), report['functions'], report['generated_initializers'], ns, link)
    records = list(functions)
    for kind, rows in (('entry_bridge', report['entry_bridges']), ('veneer', report['veneers'])):
        records += [dict(r, kind=kind, encoding=0) for r in rows]
    records.sort(key=lambda r: r['address'])
    with Path(report['native_file']).open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as raw:
        sections = f.b.sections(raw, link)
        uw, = [r for r in sections if (r['segment'], r['name']) == ('__TEXT', '__unwind_info')]
        eh, = [r for r in sections if (r['segment'], r['name']) == ('__TEXT', '__eh_frame')]
        original = bytes(raw[uw['off']:uw['off'] + uw['size']])
        ranges, padding = [], []
        for index, row in enumerate(records):
            size = row['size']
            if index + 1 < len(records):
                gap = records[index + 1]['address'] - row['address'] - size
                if 0 < gap <= 12:
                    at = link.file_offset(raw, row['address'] + size, gap)
                    if not any(raw[at:at + gap]):
                        padding.append(dict(start=row['address'] + size, size=gap))
                        size += gap
            start = row['address'] - 0x100000000
            if row.get('data_tail'):
                ranges += [(start, row['unwind_size'], row['encoding']),
                    (start + row['unwind_size'], size - row['unwind_size'], 0)]
            else:
                ranges.append((start, size, row['encoding']))
        packed, receipt = f._augment_model(original, ranges)
        initial = u.parse(original)
        augmented = u.parse(packed)
        old_entries = [r for page in initial['pages'] for r in page['entries']]
        ordered = [r for page in augmented['pages'] for r in page['entries']]
        lsda = [r for page in augmented['pages'] for r in page['lsda']]
        # Preserve every existing row, including original zero boundaries.
        om = dict(ordered)
        require(all(om.get(start) == encoding for start, encoding in old_entries), 'Existing boundary lost by original augmentation; refuse compression-only recommendation')
        incidence = Counter()
        for page in augmented['pages']:
            incidence.update({r[1] for r in page['entries']})
        frequency = Counter(r[1] for r in ordered)
        rank = sorted(incidence, key=lambda encoding: (-incidence[encoding], -frequency[encoding], encoding))
        candidates = [('unchanged_common', initial['common'])]
        for count in sorted({len(initial['common']), 32, 64, 96, 128, 160, 192, 224, 240, 248, 255, 256}):
            if count <= len(rank):
                candidates.append(('incidence_top_' + str(count), rank[:count]))
        if len(rank) <= 256:
            candidates.append(('all_unique_' + str(len(rank)), rank))
        rows, best = [], None
        for label, common in candidates:
            pages = paginate(ordered, lsda, augmented['sentinel'], common)
            model = dict(common=common, personalities=initial['personalities'], pages=pages, sentinel=augmented['sentinel'])
            blob = u.serialize(model)
            decoded = u.parse(blob)
            require(decoded == model, 'Candidate model roundtrip differs: ' + label)
            flattened = [r for page in decoded['pages'] for r in page['entries']]
            actual_lsda = [r for page in decoded['pages'] for r in page['lsda']]
            require(flattened == ordered and actual_lsda == lsda, 'Candidate semantic row drift: ' + label)
            require(decoded['personalities'] == initial['personalities'], 'Candidate personality drift')
            row = dict(candidate=label, bytes=len(blob), capacity=uw['size'], fits=len(blob) <= uw['size'],
                spare=uw['size'] - len(blob), common_count=len(common), pages=len(pages),
                local_encoding_words=sum(len({r[1] for r in page['entries']} - set(common)) for page in pages))
            rows.append(row)
            if best is None or len(blob) < len(best[1]):
                best = row, blob, model
        chosen, blob, model = best
        out.mkdir()
        (out / 'best-unwind-info.bin').write_bytes(blob)
        value = dict(status='read_only_unwind_representation_probe_complete', native=report['native_file'],
            mmap_only_native_read=True, full_native_copied=False, original_section=uw, eh_section=eh,
            original_entry_count=len(old_entries), all_original_boundaries_including_zero_preserved=True,
            augmented_entry_count=len(ordered), original_common_count=len(initial['common']),
            distinct_encodings=len(rank), initial_augment_bytes=len(packed), original_capacity=uw['size'],
            original_augment_receipt=receipt, candidate_results=rows, best=chosen,
            best_common_encodings=model['common'], best_binary=str(out / 'best-unwind-info.bin'),
            all_augmented_effective_rows_exact=True, personalities_exact=True, lsda_rows_exact=True,
            no_native_code_eh_fde_lsda_personality_section_or_linkedit_modified=True,
            new_functions=len(functions), ranges=ranges,
            recommended_strategy='Replace only compact-unwind representation in existing section if best.fits; pad remainder with zero and retain all section addresses/sizes/signing metadata',
            limitation='Probe writes no native and does not execute or sign iOS code; parent must integrate and independently read back final payload')
        (out / 'RESULT.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
        print(json.dumps(dict(original_capacity=uw['size'], original_packed=len(packed), distinct_encodings=len(rank),
            original_common=len(initial['common']), original_entries=len(old_entries), augmented_entries=len(ordered),
            best=chosen, output=str(out / 'RESULT.json')), ensure_ascii=False))

if __name__ == '__main__':
    main()
