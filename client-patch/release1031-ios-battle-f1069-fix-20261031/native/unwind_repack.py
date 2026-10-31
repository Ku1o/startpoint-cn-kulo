"""Retain all current unwind semantics and standard shared-page storage."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
from pathlib import Path
import common as c

ALGORITHM=c.SOURCE/'release1031-ios-dispatch-fix-20261031/audit/probe_unwind_payload_dedup.py'
ALGORITHM_SHA='09b517c4341df626d13da6f8caab405d02f0e29384f4455bdf037416861eba91'
WINDOWS=[[31587,31619],[32232,32264],[32989,33021],[33092,33124],
         [34047,34079],[34890,34922],[35765,35797],[36391,36423]]

def wrap_augment(original_augment):
    c.require(c.sha(ALGORITHM.read_bytes())==ALGORITHM_SHA,'Reviewed standard-page sharing source changed')
    algorithm=c.module('battle_unwind_standard_pages',ALGORITHM)
    baseline=c.read(c.PREVIOUS/'linked01/link-report.json')['unwind_finalization']
    def augment(original,ranges):
        c.require(c.sha(original)==baseline['final_unwind_sha256'],
                  'Current cumulative unwind bytes differ from prior finalized receipt')
        packed,receipt=original_augment(original,ranges)
        if len(packed)<=len(original):return packed,receipt
        before=algorithm.u.parse(packed)
        entries=[r for page in before['pages'] for r in page['entries']]
        lsda=[r for page in before['pages'] for r in page['lsda']]
        c.require(all(encoding in before['common'] for _,encoding in entries),
                  'New unwind encoding needs an explicitly reviewed common-table extension')
        model=dict(before,pages=algorithm.make_pages(entries,WINDOWS,before['sentinel'],lsda))
        result,aliases=algorithm.serialize_reusing_payloads(model)
        actual=algorithm.u.parse(result)
        c.require(actual==model and [r for page in actual['pages'] for r in page['entries']]==entries
            and [r for page in actual['pages'] for r in page['lsda']]==lsda,
            'Standard shared pages changed a boundary, encoding or LSDA')
        c.require(actual['common']==before['common'] and actual['personalities']==before['personalities']
            and actual['sentinel']==before['sentinel'],'Unwind common/personality/sentinel changed')
        c.require(len(result)<=len(original),'Standard shared pages exceed existing verified capacity')
        receipt.update(packed_size=len(result),new_pages=len(model['pages']),
            exact_page_payload_sharing=dict(before_bytes=len(packed),after_bytes=len(result),capacity=len(original),
                all_augmented_boundaries_and_encodings_exact=len(entries),aliases=aliases,
                selected_windows=WINDOWS,max_entries=max(len(p['entries']) for p in model['pages']),
                max_page_bytes=max(12+4*len(p['entries']) for p in model['pages']),
                algorithm_sha256=ALGORITHM_SHA,section_address_size_and_eh_unchanged=True,
                actual_ios_unwinder_executed=False))
        return result,receipt
    return augment
