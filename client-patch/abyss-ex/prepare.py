"""Prepare cumulative EX SWF/full-ABC payloads; no APK/IPA or registry changes."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('ex_swf_parts', HERE.parent/'startup-cache/build_swf.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
m = b.m
sys.path.insert(0, str(HERE.parent))

ANDROID_HASH = '7b67801fc938b8f77b9919b3ca1ddd77bb57da47befbb2eec6eb208897f88a72'
IOS_HASH = '507109bf13ff1b665b521d135057e42f76f924d1f14960b8264ae4f2362ef96c'
OLD_PATTERN = '^7000990[0-9]{2}$'
NEW_PATTERN = '^(?:7000990[0-9]{2}|7001000(?:0[1-9]|[12][0-9]|30))$'


def classify(label):
    if label.endswith('BattleCharacterLogic/getAvailableAbilities|1'):
        return 'equipment'
    if label.endswith('RushEventAutoStartQuestGroup/getDuplicatedCharacterIdsForEachQuest|1'):
        return 'autostart'
    if label == 'cn.ui::AbyssDetails$/isAbyss|1':
        return 'details'
    if label == 'cn.ui::AbyssRecordDetails$/open|1':
        return 'records'
    return None


def patch_abc(abc):
    before = copy.deepcopy(abc)
    view = m.View(SimpleNamespace(abc=abc), m.asm)
    receipts = []
    def integer(value):
        if value not in abc.ints:
            abc.ints.append(value)
        return abc.ints.index(value)
    for label, indices in view.by_label.items():
        kind = classify(label)
        if kind is None:
            continue
        index, = indices
        body = abc.bodies[index]
        original = copy.deepcopy(body)
        rows = m.asm.decode(body[5])
        if kind == 'details':
            old = abc.strings.index(OLD_PATTERN.encode())
            matches = [i for i,row in enumerate(rows) if row.op == 0x2c and row.args == [old]]
            if len(matches) != 1:
                raise ValueError('unexpected details predicate')
            new = len(abc.strings)
            abc.strings.append(NEW_PATTERN.encode())
            rows[matches[0]].args = [new]
            body[5] = m.asm.encode(rows)[0]
        else:
            values = {700099} if kind in ('equipment','autostart') else {700099001,700099098}
            matches = [i for i,row in enumerate(rows) if row.op == 0x2d and abc.ints[row.args[0]] in values]
            if len(matches) != len(values):
                raise ValueError(f'{kind}: predicate inventory changed')
            blocks = []
            for i in matches:
                if kind in ('equipment','autostart'):
                    if rows[i+1].op != 0x14:
                        raise ValueError('expected legacy ifne predicate')
                    # Normalize only the stack value used by this predicate.
                    # event.id, quest.id and all persisted identifiers stay EX.
                    source = f'dup\npushint {integer(700100)}\nifne done\npop\npushint {integer(700099)}\ndone:\nnop'
                else:
                    source = (f'dup\npushint {integer(700100001)}\niflt done\n'
                              f'dup\npushint {integer(700100030)}\nifgt done\n'
                              f'pop\npushint {integer(700099001)}\ndone:\nnop')
                entries = [('label',line[:-1]) if line.endswith(':') else
                           tuple(int(word) if word.isdigit() else word for word in line.split())
                           for line in source.splitlines()]
                blocks.append((i, m.asm.assemble(entries), m.asm.ENTER))
            body[5], body[6], _, placed = m.asm.splice_many(body, blocks)
            if m.asm.unsplice_many(body[5], placed) != original[5]:
                raise ValueError('non-inserted gameplay instructions changed')
            body[1] = original[1]+2
        checks = m.check_body(body, abc)
        receipts.append({'kind':kind, 'label':label, 'body_index':index, 'method_id':body[0],
                         'before_code_sha256':b.sha(original[5]), 'after_code_sha256':b.sha(body[5]),
                         'checks':checks})
    changed = {r['body_index'] for r in receipts}
    for i,(old,new) in enumerate(zip(before.bodies,abc.bodies)):
        if i not in changed and m.freeze(old) != m.freeze(new):
            raise ValueError('unrelated method changed')
    for attr in ('methods','metadata','instances','classes','scripts'):
        if m.freeze(getattr(before,attr)) != m.freeze(getattr(abc,attr)):
            raise ValueError(f'unrelated ABC metadata changed: {attr}')
    for attr in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        old = getattr(before,attr)
        if m.freeze(old) != m.freeze(getattr(abc,attr)[:len(old)]):
            raise ValueError(f'existing pool changed: {attr}')
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    from verify_android_baseline import verify as verify_android
    from verify_ios_baseline import verify as verify_ios
    android = verify_android('public')
    ios = verify_ios()
    registry = json.loads((HERE.parent/'ios-accepted.json').read_text('utf-8'))['artifact']
    if android['swf_sha256'] != ANDROID_HASH or registry['full_abc_sha256'] != IOS_HASH:
        raise ValueError('accepted lineage advanced; review EX integration against the new baseline')
    args.out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(android['apk']) as archive:
        raw = archive.read('assets/worldflipper_android_release.swf')
    source = args.out/'accepted-android.swf'
    source.write_bytes(raw)
    version,header,tags = b.parts(source)
    receipts = []
    changed_tags = []
    for tag_index,tag in enumerate(tags):
        if tag[0] != 82:
            continue
        names = [tag[3].mn_name(i[0]) for i in tag[3].instances]
        if not (len(tag[3].bodies)>90000 or 'cn.ui::AbyssDetails' in names or 'cn.ui::AbyssRecordDetails' in names):
            continue
        changes = patch_abc(tag[3])
        if changes:
            receipts.extend(changes)
            payload = tag[2]+b.serialize(tag[3],tag[4])
            tag[1] = struct.pack('<HI',(82<<6)|63,len(payload))+payload
            changed_tags.append(tag_index)
    if sorted(r['kind'] for r in receipts) != ['autostart','details','equipment','records']:
        raise ValueError('Android must change exactly the four EX predicates')
    final = header+b''.join(t[1] for t in tags)
    output = args.out/'abyss-ex-android.swf'
    output.write_bytes(b'CWS'+bytes([version])+struct.pack('<I',len(final)+8)+zlib.compress(final))
    readback = b.parts(output)[2]
    original_tags = b.parts(source)[2]
    if [i for i,(a,c) in enumerate(zip(original_tags,readback)) if a[1]!=c[1]] != changed_tags:
        raise ValueError('unexpected SWF tag changes')
    full = (ROOT/registry['full_abc']).read_bytes()
    if b.sha(full) != IOS_HASH:
        raise ValueError('iOS full ABC source mismatch')
    abc = m.abcfmt.ABC(full)
    ios_before = copy.deepcopy(abc)
    target = m.View(SimpleNamespace(abc=abc), m.asm)
    historical = json.loads((HERE.parent/'accepted-history/ios-record-holder-20260912.json').read_text('utf-8'))['artifact']
    symbols = Path(historical['full_abc']).read_bytes()
    if b.sha(symbols) != historical['full_abc_sha256']:
        raise ValueError('historical closure-symbol evidence mismatch')
    symbol_abc = m.abcfmt.ABC(symbols)
    if m.freeze(symbol_abc.methods) != m.freeze(abc.methods[:len(symbol_abc.methods)]):
        raise ValueError('historical closure method IDs no longer match current AOT metadata')
    symbol_view = m.View(SimpleNamespace(abc=symbol_abc),m.asm)
    for mid,label in symbol_view.labels.items():
        if '/closure:' in label:
            target.labels[mid] = label
    # Current iOS ABC is compiler metadata with return stubs. Restore only the
    # three reviewed methods from Android; the equipment gate is native ARM64.
    ios_changes = []
    for tag in tags:
        if tag[0] != 82:
            continue
        if not (len(tag[3].bodies)>90000 or any(tag[3].mn_name(i[0]) in
                ('cn.ui::AbyssDetails','cn.ui::AbyssRecordDetails') for i in tag[3].instances)):
            continue
        donor = m.View(SimpleNamespace(abc=tag[3]),m.asm)
        for label,indices in donor.by_label.items():
            kind = classify(label)
            if kind not in ('autostart','details','records'):
                continue
            si, = indices
            ti, = target.by_label[label]
            original = abc.bodies[ti]
            imported = m.Importer(target,donor).body(si,original[0])
            if m.activation_traits(target,original) != m.activation_traits(target,imported):
                raise ValueError(f'iOS activation ABI mismatch: {label}')
            abc.bodies[ti] = imported
            ios_changes.append({'kind':kind,'label':label,'body_index':ti,'method_id':original[0],
                                'checks':m.check_body(imported,abc)})
    if sorted(r['kind'] for r in ios_changes) != ['autostart','details','records']:
        raise ValueError('iOS must prepare exactly three AOT predicates')
    changed_ios = {r['body_index'] for r in ios_changes}
    if len(abc.bodies) != len(ios_before.bodies):
        raise ValueError('iOS body inventory changed')
    for i,(old,new) in enumerate(zip(ios_before.bodies,abc.bodies)):
        if i not in changed_ios and m.freeze(old) != m.freeze(new):
            raise ValueError(f'unrelated iOS body changed: {i}')
    for attr in ('methods','metadata','instances','classes','scripts'):
        if m.freeze(getattr(ios_before,attr)) != m.freeze(getattr(abc,attr)):
            raise ValueError(f'iOS ABI metadata changed: {attr}')
    for attr in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        old = getattr(ios_before,attr)
        if m.freeze(old) != m.freeze(getattr(abc,attr)[:len(old)]):
            raise ValueError(f'existing iOS pool changed: {attr}')
    patched_full = abc.serialize()
    (args.out/'abyss-ex-ios-full.abc').write_bytes(patched_full)
    gate_spec = importlib.util.spec_from_file_location('ios_old_gate',HERE.parent/'ios-abyss-equipment/build_ios_abyss_multibothboss_level120.py')
    gate = importlib.util.module_from_spec(gate_spec)
    gate_spec.loader.exec_module(gate)
    assembler,_,_ = gate.load_assembler(None)
    source_asm = gate.build_gate_helper()
    needle = 'mov w9, #0xaec3\nmovk w9, #0xa, lsl #16\ncmp w0, w9\nb.eq allow_deep'
    if source_asm.count(needle) != 1:
        raise ValueError('native equipment predicate changed')
    # Same four instructions and original helper size: two immediate subtracts
    # compute the unsigned distance from 700099 without touching its tail.
    new_asm = source_asm.replace(needle,'sub w9, w0, #0xaa, lsl #12\nsub w9, w9, #0xec3\ncmp w9, #1\nb.ls allow_deep')
    old_code = bytes(assembler.asm(source_asm,addr=gate.IMAGE_BASE+gate.HELPER_OFFSET)[0])
    new_code = bytes(assembler.asm(new_asm,addr=gate.IMAGE_BASE+gate.HELPER_OFFSET)[0])
    with zipfile.ZipFile(ROOT/registry['ipa']) as archive:
        native = archive.read(registry['native_member'])
    if native[gate.HELPER_OFFSET:gate.HELPER_OFFSET+len(old_code)] != old_code:
        raise ValueError('current iOS native equipment helper differs from reviewed source')
    if len(new_code) > gate.HELPER_CAPACITY_END-gate.HELPER_OFFSET:
        raise ValueError('native equipment helper exceeds its reserved range')
    (args.out/'abyss-ex-ios-equipment.bin').write_bytes(new_code)
    report = {'schema':1,'status':'prepared_for_next_client_build',
              'android':{'base_swf_sha256':ANDROID_HASH,'swf_sha256':b.sha(output.read_bytes()),'methods':receipts},
              'ios':{'base_ipa_sha256':ios['ipa_sha256'],'base_full_abc_sha256':IOS_HASH,
                     'full_abc_sha256':b.sha(patched_full),'methods':ios_changes,
                     'equipment_helper':{'offset':gate.HELPER_OFFSET,'old_size':len(old_code),
                                         'new_size':len(new_code),'source_sha256':b.sha(old_code),
                                         'sha256':b.sha(new_code)}},
              'release_requirements':['Android fresh AIR UUID and signed APK',
                                      'iOS AOT compile/link and runtime pointer validation',
                                      'New Android/iOS admission IDs and complete private server pairing',
                                      'Previous platform build allowUntil = formal activation + 86400 seconds'],
              'release_policy':json.loads((HERE/'release-policy.json').read_text('utf-8')),
              'apk_or_ipa_created':False,'device_tested':False}
    (args.out/'preparation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'status':report['status'],'android_methods':len(receipts),'ios_methods':len(ios_changes)}))


if __name__ == '__main__':
    main()
