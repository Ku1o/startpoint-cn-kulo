"""Read-only small-interval __TEXT unwind-capacity inventory, no free-space claim."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import json
import mmap
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode = True
TASK = Path(str(fc.client() / 'revision-ios-dispatch-fix-20261031'))
SOURCE = Path(str(fc.REPO / 'client-patch'))
sys.path[:0] = [str(SOURCE / 'pr43-ios'), str(SOURCE / 'equipment-ios-repair'),
    str(SOURCE / 'lens0907-0908'), str(fc.private('libraries'))]
import native_support as ns
import build_candidate as b

def inspect(path):
    link = ns.backend()
    with path.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as raw:
        segments = link.segments(raw)
        sections = b.sections(raw, link)
        text, = [s for s in segments if s['name'] == '__TEXT']
        uw, = [s for s in sections if (s['segment'], s['name']) == ('__TEXT', '__unwind_info')]
        end = uw['off'] + uw['size']
        limit = min([text['off'] + text['fs']] + [s['off'] for s in sections if s['off'] >= end and s['name'] != '__unwind_info'])
        assert limit >= end
        size = limit - end
        assert size < 65536, 'Unexpected large gap; refuse materialization'
        gap = raw[end:limit]
        starts_command, starts = b.function_starts(raw, link)
        gapva = text['vm'] + end - text['off']
        pointers = []
        info = ns.INFO_OFFSET
        tableva, count = struct.unpack_from('<QQ', raw, info + 48)
        tableoff = link.file_offset(raw, tableva, count * 8)
        for mid in range(count):
            value = struct.unpack_from('<Q', raw, tableoff + mid * 8)[0]
            if gapva <= value < gapva + size:
                pointers.append(dict(method=mid, pointer=hex(value)))
        return dict(path=str(path), text_segment=text, unwind_section=uw,
            following_sections=[s for s in sections if s['off'] >= end][:3],
            following_segments=[s for s in segments if s['off'] >= end][:3],
            gap=dict(offset=end, va=hex(gapva), bytes=size, all_zero=not any(gap),
                function_starts_in_gap=[hex(s + 0x100000000) for s in starts if gapva <= s + 0x100000000 < gapva + size],
                aot_pointers_in_gap=pointers),
            interpretation='Inventory only; zero bytes and absent entries alone do not authorize section growth')

def main():
    output = TASK / 'audit/unwind-section-gap.json'
    assert not output.exists()
    value = dict(current=inspect(TASK / 'linked01/worldflipper'),
        public=inspect(TASK.parent / 'revision-public-admission-20261031/ios/build01/worldflipper'))
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps(value, ensure_ascii=False))

if __name__ == '__main__':
    main()
