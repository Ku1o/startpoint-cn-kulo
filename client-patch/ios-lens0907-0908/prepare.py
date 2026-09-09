"""Hash-locked cumulative iOS Lens port; never rebuild from a historical IPA."""
from pathlib import Path
import copy, hashlib, json, os, sys, types, zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = Path(os.environ.get('STARPOINT_IOS_LENS_WORK', r'F:\codex\work\lens-ios-20260908'))
LEGACY = Path(r'F:\codex\ios-rush-leaderboard-port-20260830')
sys.path.insert(0, str(REPO / 'client-patch/lens0907-0908'))
from build_swf import Importer, View, SwfAbc, abcfmt, asm, freeze, check_body, activation_traits

IPA_HASH = '09eca214d1e73559bbc7af98d642f9056b0eeee4a44f3e09dd25f2a1e9091a43'
FULL_HASH = 'b374e739c7da1541182f0608f6f52c2e597efafc5133f2ecad97da819f842c4c'
APK_HASH = '8e5999e2689788159362acc81cd4bcd89182966fce9af7800d085ff89dccb41b'
SWF_HASH = 'ff96d39ae9dd30b7341958da0dbb19db38f557f5eb37ec9ed5284fd15f238a71'

def sha(b): return hashlib.sha256(b).hexdigest()
def view(abc): return View(types.SimpleNamespace(abc=abc), asm)
def dump(path, obj): path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def inputs():
    WORK.mkdir(parents=True, exist_ok=True)
    reg=json.loads((REPO/'client-patch/ios-accepted.json').read_text(encoding='utf-8'))['artifact']
    ipa=Path(reg['ipa']); assert sha(ipa.read_bytes())==reg['ipa_sha256']==IPA_HASH
    with zipfile.ZipFile(ipa) as z:
        native=z.read(reg['native_member']); swf=z.read(reg['swf_member'])
    assert sha(native)==reg['native_sha256'] and sha(swf)==reg['swf_sha256']
    full=Path(r'F:\codex\ios-profile-follow-port-20260908\profile-full.abc').read_bytes()
    assert sha(full)==FULL_HASH and hashlib.sha1(full).digest()==native[0x63b4b80:0x63b4b94]
    apk=REPO/'outputs/lens0907-0908-android-20260908/public-v3-final/StarPoint-CN-1.8.1-lens0907-0908-public-v3-20260908.apk'
    assert sha(apk.read_bytes())==APK_HASH
    with zipfile.ZipFile(apk) as z: android=z.read('assets/worldflipper_android_release.swf')
    assert sha(android)==SWF_HASH
    for name,data in [('baseline-native',native),('baseline.swf',swf),('baseline-full.abc',full),('android-v3.swf',android)]:
        p=WORK/name
        if p.exists(): assert p.read_bytes()==data
        else: p.write_bytes(data)
    return reg, view(abcfmt.ABC(full)), View(SwfAbc(WORK/'android-v3.swf'),asm)

def local_read(i): return asm.Instruction(0x62,[i])
def local_write(i): return asm.Instruction(0x63,[i])

def rewrite_calls(body, helpers, abc, trail=()):
    """Inline small leaf helpers without extending the native method table."""
    old=asm.decode(body[5]); old_code,offsets=asm.encode(old)
    assert old_code==body[5]
    offsets.append(len(old_code)); old_at={off:i for i,off in enumerate(offsets)}
    output=[]; positions={}; fixups=[]; inlined=[]
    for at,ins in enumerate(old):
        positions[at]=len(output)
        name=abc.mn_name(ins.args[0]) if ins.op in (0x46,0x4f) else None
        if name not in helpers:
            out=copy.deepcopy(ins); output.append(out);fixups.append(out);continue
        assert name not in trail,'recursive inline helper'
        helper,param_types,return_type=helpers[name]
        helper=copy.deepcopy(helper)
        nested=rewrite_calls(helper,helpers,abc,trail+(name,))
        assert not helper[6] and not helper[7]
        code=asm.decode(helper[5]); assert [(i.op,i.args) for i in code[:2]]==[(0xd0,[]),(0x30,[])]
        assert not any(i.op in (0x30,0x1c,0x1d,0x65,0x67,0x40,0x57,0x1b) for i in code[2:]),name
        argc=ins.args[1]; assert argc==len(param_types)
        base=body[2]; body[2]+=helper[2]+1; result=base+helper[2]
        # Runtime calls coerce arguments before entering their method frame.
        for n in range(argc,0,-1):
            if param_types[n-1]:output.append(asm.Instruction(0x80,[param_types[n-1]]))
            output.append(local_write(base+n))
        output.append(local_write(base))
        for n in range(argc+1,helper[2]):output.extend([asm.Instruction(0x21),local_write(base+n)])
        hp={0:len(output),1:len(output)}; hj=[]; exits=[]
        for hi,h in enumerate(code[2:],2):
            hp[hi]=len(output); h=copy.deepcopy(h)
            if h.op in (0xef,0xf0,0xf1):continue
            if h.op==0x48:
                if return_type:output.append(asm.Instruction(0x80,[return_type]))
                output.append(local_write(result));j=asm.Instruction(0x10,target=0);output.append(j);exits.append(j);continue
            assert h.op!=0x47,'void helper not supported'
            if 0xd0<=h.op<=0xd3:h=local_read(base+h.op-0xd0)
            elif 0xd4<=h.op<=0xd7:h=local_write(base+h.op-0xd4)
            elif h.op in (0x08,0x62,0x63,0x92,0x94,0xc2,0xc3):h.args[0]+=base
            elif h.op==0x32:h.args=[i+base for i in h.args]
            output.append(h);hj.append(h)
        hp[len(code)]=len(output)
        for j in exits:j.target=len(output)
        for h in hj:
            if h.target is not None:h.target=hp[h.target]
        if ins.op==0x46:output.append(local_read(result))
        inlined.append(dict(name=name,nested=nested,locals=helper[2],caller_index=at))
    positions[len(old)]=len(output)
    for ins in fixups:
        if ins.target is not None:ins.target=positions[ins.target]
        if ins.default is not None:ins.default=positions[ins.default]
        if ins.cases is not None:ins.cases=[positions[i] for i in ins.cases]
    code,new_offsets=asm.encode(output);new_offsets.append(len(code))
    body[6]=[(new_offsets[positions[old_at[a]]],new_offsets[positions[old_at[b]]],new_offsets[positions[old_at[c]]],d,e) for a,b,c,d,e in body[6]]
    body[5]=code
    at2={o:i for i,o in enumerate(new_offsets)}
    stack,scope,_=asm.simulate(output,body[3],abc.multinames,exception_targets=[at2[e[2]] for e in body[6]])
    body[1]=max(body[1],stack);body[4]=max(body[4],scope)
    return inlined

def main():
    reg,target,source=inputs()
    assert target.a.serialize()==(WORK/'baseline-full.abc').read_bytes()
    plan=json.loads((REPO/'client-patch/lens0907-0908/method-plan.json').read_text(encoding='utf-8'))
    labels=[r['label'] for k in ('insert_only_methods','replace_methods') for r in plan[k]]
    labels += ['pinball.scene.battle::BattleScene/preparation|1',
               'pinball.scene.battle::BattleScene/changeAutoplayMode|1',
               'pinball.dialog.battlePauseMenu::BattlePauseMenu/prepare|1',
               'pinball.common.data.item::OwnedEquipmentLogic/getUseableAwakingCrystal|1']
    helper_labels=[r['label'] for r in plan['new_methods']]
    importer=Importer(target,source)
    # iOS stores anonymous method infos but no AVM2 bodies.  Match the contiguous
    # interval between named methods, including every type and activation slot.
    named_source={m:l for m,l in source.labels.items() if '/closure:' not in l and '/activation/' not in l}
    named_target={m:l for m,l in target.labels.items() if '/closure:' not in l and '/activation/' not in l}
    signature=lambda v,m:(v.mn(v.a.methods[m][0]),tuple(v.mn(x) for x in v.a.methods[m][1]),v.a.methods[m][3])
    child_map=[]
    for label in labels:
        si=source.a.bodies[source.by_label[label][0]][0]; ti=target.a.bodies[target.by_label[label][0]][0]
        se=min((m for m in named_source if m>si),default=len(source.a.methods))
        te=min((m for m in named_target if m>ti),default=len(target.a.methods))
        assert se-si==te-ti,(label,'anonymous interval differs',se-si,te-ti)
        for delta in range(1,se-si):
            assert signature(source,si+delta)==signature(target,ti+delta),(label,delta,'signature')
            importer.methods[si+delta]=ti+delta
            child_map.append((si+delta,ti+delta))
    baseline=copy.deepcopy(target.a)
    field_names={'pinball.scene.battle::BattleScene':['fiveBossManualAutoLock'],
                 'pinball.scene.battle.battle.squad.ball::BallImpl':['kyubiPowerFlipInitialCombo'],
                 'pinball.scene.battle.battle.ability::BattleAbilityTotalizerImpl':['duringDashParameters']}
    for owner,names in field_names.items():
        assert not any(target.a.mn_name(i[1])==owner for i in target.a.instances),'field owner has subclasses'
        ai=next(i for i,r in enumerate(target.a.instances) if target.a.mn_name(r[0])==owner)
        bi=next(i for i,r in enumerate(source.a.instances) if source.a.mn_name(r[0])==owner)
        for name in names:
            src=next(t for t in source.a.instances[bi][6] if source.a.mn_name(t.name)==name)
            assert not any(target.a.mn_name(t.name)==name for t in target.a.instances[ai][6])
            target.a.instances[ai][6].append(importer.trait(src))
    # Helpers are compiled inline, keeping all 101071 original AOT method IDs
    # and the existing rebased method table. No spare/unused method is hijacked.
    helpers={}
    for label in helper_labels:
        bi=source.by_label[label][0]; body=source.a.bodies[bi]
        info=importer.info(body[0])
        helpers[label.split('/')[-1].split('|')[0]]=(importer.body(bi,body[0],scope=1),info[1],info[0])
    results=[]
    for label in labels:
        bi=source.by_label[label][0]; ai=target.by_label[label][0]
        old=target.a.bodies[ai]; body=importer.body(bi,old[0],scope=old[3])
        assert activation_traits(target,old)==activation_traits(target,body),(label,'activation layout')
        inlined=rewrite_calls(body,helpers,target.a)
        target.a.bodies[ai]=body
        if label in [r['label'] for r in plan['replace_methods']]:
            target.a.methods[old[0]]=importer.info(source.a.bodies[bi][0])
        results.append(dict(label=label,body_index=ai,method_id=old[0],source_method_id=source.a.bodies[bi][0],inlined=inlined,checks=check_body(body,target.a)))
    lifecycles=[]
    for owner in sorted(set(l.split('/')[0].rstrip('$') for l in labels)):
        label='script:'+owner+'/<init>'
        ai=target.by_label[label][0];bi=source.by_label[label][0];old=target.a.bodies[ai]
        body=importer.body(bi,old[0],scope=old[3]); target.a.bodies[ai]=body
        lifecycles.append(dict(label=label,method_id=old[0],body_index=ai))
    changed={r['method_id'] for r in results+lifecycles}
    for pool in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        assert freeze(getattr(baseline,pool))==freeze(getattr(target.a,pool)[:len(getattr(baseline,pool))]),pool
    assert len(baseline.methods)==len(target.a.methods)==101071
    for old,new in zip(baseline.bodies,target.a.bodies):
        if old[0] not in changed:assert freeze(old)==freeze(new),old[0]
    dump(WORK/'port.json',dict(methods=results,anonymous_mapping=child_map,fields=field_names,compiler_only_lifecycles=lifecycles,source_ipa=reg))
    (WORK/'compile').mkdir(exist_ok=True)
    full=target.a.serialize(); (WORK/'compile/lens.abc').write_bytes(full)
    (WORK/'lens-full.abc').write_bytes(full)
    print('Imported',len(results),'methods; mapped',len(child_map),'anonymous method infos')

if __name__=='__main__':main()
