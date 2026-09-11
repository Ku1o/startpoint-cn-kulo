"""Prepare one iOS auto-start method on the exact cumulative Lens IPA."""
from pathlib import Path
import argparse, copy, hashlib, importlib.util, json, os, struct, sys, types, zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = Path(os.environ.get('STARPOINT_IOS_ABYSS_WORK', 'F:/codex/work/ios-abyss-autostart-lens-20260909'))
LEGACY = Path('F:/codex/ios-rush-leaderboard-port-20260830')
LENS_WORK = Path('F:/codex/work/lens-ios-20260908')
sys.path.insert(0, str(REPO/'client-patch/lens0907-0908'))
from build_swf import Importer, View, SwfAbc, abcfmt, asm, freeze, check_body, activation_traits

IPA_HASH = 'de28d8134e51d22f3c596869e53e90072866c17f54ec54af99b2a3fcd78dcd02'
FULL_HASH = '932c5b21f01de3a8aae4529e651b30f3bc42ccd789306c93cb4f151b64c42ef6'
APK_HASH = 'c868534b575348dde825fcd4c88c156157174fd4444724f1141fd9aa95e32a2d'
SWF_HASH = '11c06fd77a0e3811164d196208ecce28cba5ec3a602e3d798f3c67d5d5b17e04'
LABEL = 'pinball.common.data.quest.singleQuestAutoStart::RushEventAutoStartQuestGroup/getDuplicatedCharacterIdsForEachQuest|1'
TARGET_ID = 26363
TARGET_BODY = 24810
TARGET_CLASS = 'pinball.common.data.quest.singleQuestAutoStart.RushEventAutoStartQuestGroup'
MAIN_AOT_INFO_OFFSET = 0x63B4B80

def sha(b): return hashlib.sha256(b).hexdigest()
def view(abc): return View(types.SimpleNamespace(abc=abc), asm)
def dump(path, obj): path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def source_record(*, reproduce=False):
    sys.path.insert(0, str(HERE.parent))
    from verify_ios_baseline import verify
    record_path = HERE.parent/'accepted-history/ios-lens-20260909.json' if reproduce else HERE.parent/'ios-accepted.json'
    verified = verify(record_path=record_path)
    if verified['ipa_sha256'] != IPA_HASH:
        raise ValueError('registered iOS baseline advanced; audit a new patch or explicitly reproduce this historical Lens step')
    return json.loads(record_path.read_text('utf-8'))['artifact']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reproduce-lens', action='store_true', help='explicitly reproduce from the exact archived Lens input')
    args = parser.parse_args()
    reg = source_record(reproduce=args.reproduce_lens)
    full = (LENS_WORK/'lens-full.abc').read_bytes()
    assert sha(full) == FULL_HASH
    with zipfile.ZipFile(reg['ipa']) as z:
        native = z.read(reg['native_member']); swf = z.read(reg['swf_member'])
    assert sha(native) == reg['native_sha256'] and sha(swf) == reg['swf_sha256']
    assert hashlib.sha1(full).digest() == native[MAIN_AOT_INFO_OFFSET:MAIN_AOT_INFO_OFFSET+20]
    apk = REPO/'outputs/abyss-autostart-lens-public-test-20260909/StarPoint-CN-1.8.1-abyss-autostart-lens-public-test-20260909.apk'
    assert sha(apk.read_bytes()) == APK_HASH
    with zipfile.ZipFile(apk) as z: android = z.read('assets/worldflipper_android_release.swf')
    assert sha(android) == SWF_HASH
    WORK.mkdir(parents=True, exist_ok=False)
    for name, data in [('baseline-native',native),('baseline.swf',swf),('baseline-full.abc',full),('android-autostart.swf',android)]:
        (WORK/name).write_bytes(data)
    target = view(abcfmt.ABC(full)); baseline = copy.deepcopy(target.a)
    source = View(SwfAbc(WORK/'android-autostart.swf'),asm)
    assert target.by_label[LABEL] == [TARGET_BODY] and source.by_label[LABEL] == [24599]
    old = target.a.bodies[TARGET_BODY]
    assert old[:5] == [TARGET_ID,7,20,1,2] and not old[6] and not old[7]
    importer = Importer(target,source)
    body = importer.body(24599,TARGET_ID,scope=old[3])
    assert body[:5] == [TARGET_ID,7,23,1,2] and not body[6] and not body[7]
    target.a.bodies[TARGET_BODY] = body
    assert target.normalized(TARGET_BODY) == source.normalized(24599)
    assert '700099' in repr(target.normalized(TARGET_BODY))
    # The compiler needs the class initialization body; its native implementation
    # and runtime body metadata are retained from the accepted IPA.
    lifecycle = 'script:'+LABEL.split('/')[0]+'/<init>'
    ai = target.by_label[lifecycle][0]; bi = source.by_label[lifecycle][0]
    lifecycle_id = target.a.bodies[ai][0]
    target.a.bodies[ai] = importer.body(bi,lifecycle_id,scope=target.a.bodies[ai][3])
    for attr in ('methods','metadata','instances','classes','scripts'):
        assert freeze(getattr(baseline,attr)) == freeze(getattr(target.a,attr)),attr
    pool_growth = {}
    for pool in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        oldpool = getattr(baseline,pool); newpool = getattr(target.a,pool)
        assert freeze(oldpool) == freeze(newpool[:len(oldpool)]),pool
        pool_growth[pool] = len(newpool)-len(oldpool)
    assert len(target.a.methods) == 101071 and len(target.a.bodies) == len(baseline.bodies)
    for a,b in zip(baseline.bodies,target.a.bodies):
        if a[0] not in (TARGET_ID,lifecycle_id): assert freeze(a) == freeze(b)
    parser = 'pinball.master.generated::AbilityValues$/parseAt109|1'
    parser_index = target.by_label[parser][0]
    assert freeze(target.a.bodies[parser_index]) == freeze(baseline.bodies[parser_index])
    compiled_full = target.a.serialize()
    (WORK/'compile').mkdir()
    (WORK/'compile/abyss.abc').write_bytes(compiled_full)
    (WORK/'abyss-full.abc').write_bytes(compiled_full)
    result = dict(source_ipa=reg,android_apk_sha256=APK_HASH,android_swf_sha256=SWF_HASH,
                  methods=[dict(label=LABEL,body_index=TARGET_BODY,method_id=TARGET_ID,
                                source_body_index=24599,checks=check_body(body,target.a))],
                  compiler_only_lifecycles=[dict(label=lifecycle,method_id=lifecycle_id,body_index=ai)],
                  fields={},pool_growth=pool_growth,android_ios_normalized_method_equal=True,
                  prior_lens_parser_unchanged=True,source_full_abc_sha256=FULL_HASH,
                  full_abc_sha256=sha(compiled_full),full_abc_sha1=hashlib.sha1(compiled_full).hexdigest())
    dump(WORK/'port.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
