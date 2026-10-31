"""Re-encode a pinned unwind model without removing any boundary or interval."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from pathlib import Path
import common as c

def wrap_augment(original_augment):
    plan_path=Path(__file__).with_name('unwind_plan.json')
    plan=c.read(plan_path)
    source=Path(__file__).resolve().parents[1]/'audit/probe_unwind_payload_dedup.py'
    c.require(c.sha(source.read_bytes())==plan['algorithm_source_sha256'],
              'Reviewed unwind page-payload sharing algorithm changed')
    algorithm=c.module('dispatch_unwind_exact_payload_algorithm',source)
    def augment(original,ranges):
        packed,receipt=original_augment(original,ranges)
        if len(packed)<=len(original):return packed,receipt
        c.require(len(original)==plan['capacity'] and len(packed)==plan['input_bytes'] and
                  c.sha(packed)==plan['input_augmented_sha256'],
                  'Unwind sharing plan is for another exact augmented model')
        u=algorithm.u;before=u.parse(packed)
        entries=[r for page in before['pages'] for r in page['entries']]
        lsda=[r for page in before['pages'] for r in page['lsda']]
        c.require(len(entries)==plan['augmented_rows'],'Unexpected augmented unwind row count')
        c.require(all(encoding in before['common'] for _,encoding in entries),
                  'Pinned all-common representation contract changed')
        pages=algorithm.make_pages(entries,plan['selected_windows'],before['sentinel'],lsda)
        model=dict(before,pages=pages)
        result,aliases=algorithm.serialize_reusing_payloads(model)
        actual=u.parse(result)
        c.require(actual==model and
                  [r for page in actual['pages'] for r in page['entries']]==entries and
                  [r for page in actual['pages'] for r in page['lsda']]==lsda,
                  'Unwind page-payload sharing changed decoded semantics')
        c.require(actual['common']==before['common'] and actual['personalities']==before['personalities'] and
                  actual['sentinel']==before['sentinel'],'Unwind encoding/personality/sentinel changed')
        c.require(len(result)==plan['output_bytes'] and len(result)<=len(original) and
                  c.sha(result)==plan['output_sha256'],'Pinned unwind sharing result differs')
        receipt.update(packed_size=len(result),new_pages=len(pages),
            exact_page_payload_sharing=dict(strategy='standard compressed pages with exact shared payloads',
                before_bytes=len(packed),after_bytes=len(result),capacity=len(original),
                all_augmented_boundaries_and_encodings_exact=len(entries),
                common_personality_lsda_and_sentinel_exact=True,
                selected_windows=plan['selected_windows'],aliases=aliases,
                max_entries=max(len(p['entries']) for p in pages),
                max_page_bytes=max(12+4*len(p['entries']) for p in pages),
                plan_sha256=c.sha(plan_path.read_bytes()),
                probe=str(c.TASK/plan['probe']),probe_sha256=c.sha((c.TASK/plan['probe']).read_bytes()),
                section_address_size_and_eh_unchanged=True,actual_ios_unwinder_executed=False))
        return result,receipt
    return augment
