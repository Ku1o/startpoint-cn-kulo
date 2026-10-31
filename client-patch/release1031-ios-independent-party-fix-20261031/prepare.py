"""Select three existing real-owner bodies without changing the complete ABC."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse, hashlib, json, struct, types
from pathlib import Path
import common as c

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(); guard = c.bounded_job(); out = c.fresh(args.output)
    p = c.framework(); raw = c.ABC.read_bytes(); c.require(c.sha(raw) == c.ABC_SHA, 'Full ABC identity changed')
    a = p.abcfmt.ABC(raw); v = p.View(types.SimpleNamespace(abc=a), p.asm)
    c.require(len(a.methods) == c.METHODS, 'Wrong cumulative method count')
    previous = c.read(c.PREVIOUS/'linked01/link-report.json')
    package_path = c.PREVIOUS/'StarPoint-iOS-1.8.4-release1031-battle-f1069-fix-r1-unsigned.json'
    package = c.read(package_path)
    c.require(package['ipa_sha256'] == c.IPA_SHA and previous['native_sha256'] == c.NATIVE_SHA, 'Wrong previous cumulative input')
    source = c.read(str(fc.private('followup_party_input_record')))['artifact']
    c.require(source['ipa_sha256'] == c.IPA_SHA and source['full_abc_sha256'] == c.ABC_SHA, 'Registered iOS input changed')
    changes = []
    for mid, label in c.TARGETS.items():
        bi, = v.by_label[label]; body = a.bodies[bi]
        c.require(body[0] == mid and len(body[5]) > 1 and not body[6] and not body[7], 'Real target body/owner contract differs')
        changes.append(dict(method_id=mid, label=label, strategy='replace',
                            before_code_sha256=c.sha(body[5]), after_code_sha256=c.sha(body[5]), body_bytes=len(body[5]),
                            validation=p.check_body(body,a), real_owner_recompile=True))
    helper_class, = [i for i,row in enumerate(a.instances) if a.mn_name(row[0])=='cn.mod::IndependentRushParty']
    helpers = {a.mn_name(t.name):t.data[2] for t in a.classes[helper_class][1]
               if t.kind==1 and a.mn_name(t.name) in ('setEventId','getEventId','category')}
    c.require(helpers == dict(setEventId=101300,getEventId=101301,category=101302), 'Existing helper identities differ')
    out.mkdir(parents=True)
    port = dict(status='prepared_real_owner_native_rebind', source_ipa=source,
                full_abc_file=str(c.ABC), full_abc_sha256=c.ABC_SHA,
                full_abc_sha1=hashlib.sha1(raw).hexdigest(), base_full_abc_sha256=c.ABC_SHA,
                old_methods=c.METHODS,total_methods=c.METHODS,methods=changes,
                compiled_helpers=[],new_method_ids=[],
                unchanged_helpers=helpers, full_abc_bytes_unchanged=True,
                admission_materials_unchanged=True,parent_bounded_job=guard,
                compiler_only_owner_context_required=True, device_tested=False)
    c.dump(out/'port.json',port)
    print(json.dumps(dict(status=port['status'],targets=sorted(c.TARGETS),full_abc_unchanged=True)))
if __name__ == '__main__': main()
