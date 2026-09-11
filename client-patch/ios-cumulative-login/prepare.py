"""Append login/details/element classes to the accepted iOS AOT unit.

Existing method IDs and constant-pool indexes never move. The native linker
retains all unrelated original functions and runtime metadata; this file is
compiler input, not a replacement of the original game classes or IPA.
"""
from pathlib import Path
import argparse
import copy, hashlib, json, os, struct, sys, types, zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
WORK=Path(os.environ.get('STARPOINT_IOS_CUMULATIVE_WORK',r'F:\codex\work\ios-cumulative-login-details-20260911'))
LEGACY=Path(r'F:\codex\ios-rush-leaderboard-port-20260830')
SDK=LEGACY/'AIRSDK_51.2.1.5'
sys.path.insert(0,str(HERE.parent/'lens0907-0908'))
from build_swf import Importer,View,SwfAbc,abcfmt,asm,freeze,check_body,activation_traits
from swfabc import swftags

IPA_SHA='8e6fb8cc4de6fe1c79efaded8e4ab1159c012645bdc3a52a22e19562e0661193'
APK_SHA='27de717e8864ea35a329032fa3f7dc23e8d99e3f6187b411a39f321d1509a200'
SWF_SHA='c667815ff871e12705e665267640db480f7c959e1c6bb4d852016f1e4923d6ed'
OLD_COUNT=101071
INFO_OFFSET=0x63b4b80
MAIN_BODIES=[21496,71835,78350,56844,59846,58882,92450,82502,82500,29697,31405,37085,77176,7174]
HELPERS=['cn.rules.QuestElementResistance','cn.ui.AbyssDetails','cn.account.PlayerLogin']

def sha(data):return hashlib.sha256(data).hexdigest()
def view(abc):return View(types.SimpleNamespace(abc=abc),asm)
def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n','utf8')
def put(path,data):
    if path.exists():assert path.read_bytes()==data,('existing output differs',str(path))
    else:path.write_bytes(data)

def lower_constant_casts(body,abc):
    """Normalize FFDec's constant late casts to equivalent typed AVM2 casts."""
    old=asm.decode(body[5]);_,offsets=asm.encode(old);offsets.append(len(body[5]))
    rows=[];mapping={};removed=set();casts=[]
    for i,x in enumerate(old):
        if i in removed:continue
        x=copy.deepcopy(x)
        mapping[i]=len(rows)
        if x.op in (0xef,0xf0,0xf1):continue
        if x.op==0x60 and i+1<len(old) and old[i+1].op==0x87:
            rows.append(asm.Instruction(0x86,list(x.args)));removed.add(i+1);casts.append(i)
        else:rows.append(copy.deepcopy(x))
    mapping[len(old)]=len(rows)
    for x in rows:
        if x.target is not None:x.target=mapping[x.target]
        if x.default is not None:x.default=mapping[x.default]
        if x.cases is not None:x.cases=[mapping[t] for t in x.cases]
    code,new_offsets=asm.encode(rows);new_offsets.append(len(code));at={o:i for i,o in enumerate(offsets)}
    body[6]=[(new_offsets[mapping[at[a]]],new_offsets[mapping[at[b]]],new_offsets[mapping[at[c]]],d,e) for a,b,c,d,e in body[6]]
    body[5]=code
    return dict(constant_late_casts=casts,debug_operations_removed=sum(x.op in (0xef,0xf0,0xf1) for x in old))

class ClassImporter(Importer):
    def __init__(self,target,source):
        super().__init__(target,source)
        self.class_base=len(self.a.instances);self.meta_base=len(self.a.metadata)
        self.methods={i:len(self.a.methods)+i for i in range(len(self.b.methods))}

    def trait(self,old,append=False):
        t=copy.deepcopy(old);t.metadata=[]
        if t.data[0] in ('class','function'):
            t.name=self.pool('multinames',t.name)
            t.data[2]=self.class_base+t.data[2] if t.data[0]=='class' else self.methods[t.data[2]]
        else:t=super().trait(t,append=append)
        t.metadata=[self.meta_base+m for m in old.metadata]
        return t

    def merge(self):
        a,b=self.a,self.b
        a.metadata.extend([(self.pool('strings',n),[(self.pool('strings',k),self.pool('strings',v)) for k,v in rows]) for n,rows in b.metadata])
        a.methods.extend(self.info(i) for i in range(len(b.methods)))
        for n,s,f,p,interfaces,init,traits in b.instances:
            a.instances.append([self.pool('multinames',n),self.pool('multinames',s),f,
                self.pool('namespaces',p) if p is not None else None,
                [self.pool('multinames',i) for i in interfaces],self.methods[init],[self.trait(t) for t in traits]])
        a.classes.extend([[self.methods[m],[self.trait(t) for t in ts]] for m,ts in b.classes])
        a.scripts.extend([[self.methods[m],[self.trait(t) for t in ts]] for m,ts in b.scripts])
        for i,body in enumerate(b.bodies):a.bodies.append(self.body(i,self.methods[body[0]]))

def voice_extension(importer,source_index,original):
    """Only the new guarded preloads; native wrapper retains the old function."""
    a=importer.a
    def q(ns,name):
        found=[i for i,m in enumerate(a.multinames) if m[0]==7 and a.s(m[2])==name and a.namespaces[m[1]][0]==22 and a.ns_name(m[1])==ns]
        assert found,(ns,name)
        return found[0]
    old=copy.deepcopy(importer.b.bodies[source_index]);block=asm.decode(old[5])[112:160]
    assert len(block)==48
    for x in block:
        if x.target is not None:assert 112<=x.target<=160;x.target-=112
        assert x.default is None and x.cases is None
    old[5]=asm.encode(block)[0];old[6]=[];old[7]=[]
    importer.b.bodies.append(old)
    try:block=asm.decode(importer.body(len(importer.b.bodies)-1,original[0])[5])
    finally:importer.b.bodies.pop()
    rows=asm.assemble([('getlocal_0',),('pushscope',),('getlocal_3',),('getproperty',q('','playsSoundEffect'))])
    exits=[]
    def branch(op):
        x=asm.Instruction(op,target=0);rows.append(x);exits.append(x)
    branch(0x12)
    rows+=asm.assemble([('getlocal_2',),('getproperty',q('','index')),('pushbyte',0)])
    branch(0x14)
    rows+=asm.assemble([('getlocal_3',),('getproperty',q('','playsSkillReady'))])
    branch(0x12)
    rows+=asm.assemble([('getlocal_0',),('callproperty',q('','getShortVoice'),0),
        ('coerce',q('pinball.common.data.character','CharacterShortVoiceLogic')),('setlocal',5)])
    start=len(rows)
    for x in block:
        if x.target is not None:x.target+=start
    rows+=block
    for x in exits:x.target=len(rows)
    rows.append(asm.Instruction(0x47))
    code,_=asm.encode(rows)
    body=copy.deepcopy(original);body[5]=code;body[6]=[];body[7]=[]
    return body

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reproduce-accepted-20260909',action='store_true',
                        help='Use the archived Sep 9 input only for historical reproduction')
    args=parser.parse_args()
    registry=HERE.parent/('accepted-history/ios-abyss-autostart-20260909.json' if args.reproduce_accepted_20260909 else 'ios-accepted.json')
    sys.path.insert(0,str(HERE.parent))
    from verify_ios_baseline import verify
    verify(record_path=registry)
    reg=json.loads(registry.read_text('utf8'))['artifact']
    assert reg['ipa_sha256']==IPA_SHA,('This is a historical step; new work starts from ios-accepted.json. '
        'Use --reproduce-accepted-20260909 only to reproduce its archived input.')
    WORK.mkdir(parents=True,exist_ok=True)
    ipa=Path(reg['ipa']);assert sha(ipa.read_bytes())==reg['ipa_sha256']==IPA_SHA
    with zipfile.ZipFile(ipa) as z:native=z.read(reg['native_member']);swf=z.read(reg['swf_member'])
    assert sha(native)==reg['native_sha256'] and sha(swf)==reg['swf_sha256']
    full=Path(r'F:\codex\work\ios-abyss-autostart-lens-20260909\abyss-full.abc').read_bytes()
    assert hashlib.sha1(full).digest()==native[INFO_OFFSET:INFO_OFFSET+20]
    apk=REPO/'outputs/player-login-cumulative-lan-test-20260910/StarPoint-CN-1.8.1-player-login-abyss-lens-lan-test.apk'
    assert sha(apk.read_bytes())==APK_SHA
    with zipfile.ZipFile(apk) as z:android=z.read('assets/worldflipper_android_release.swf')
    assert sha(android)==SWF_SHA
    for name,data in [('baseline-native',native),('baseline.swf',swf),('baseline-full.abc',full),('android-target.swf',android)]:put(WORK/name,data)
    target=view(abcfmt.ABC(full));old=copy.deepcopy(target.a)
    source=View(SwfAbc(WORK/'android-target.swf'),asm)
    assert len(old.methods)==OLD_COUNT
    helper_records=[]
    _,_,_,raw=swftags.load_swf(str(WORK/'android-target.swf'))
    for code,o,h,n in swftags.iter_tags(raw):
        if code!=82:continue
        data=raw[o+h:o+h+n];nul=data.index(b'\0',4);name=data[4:nul].decode()
        if name not in HELPERS:continue
        abc=data[nul+1:];hv=view(abcfmt.ABC(abc));start=len(target.a.methods)
        put(WORK/(name+'.abc'),abc)
        ClassImporter(target,hv).merge()
        helper_records.append(dict(name=name,sha256=sha(abc),first_method=start,methods=len(hv.a.methods),scripts=len(hv.a.scripts)))
    assert [r['name'] for r in helper_records]==HELPERS
    assert len(target.a.methods)==OLD_COUNT+111
    importer=Importer(target,source)
    owner='pinball.scene.battle.battle.hud::HudMemberStatus'
    assert not any(target.a.mn_name(i[1])==owner for i in target.a.instances),'HUD subclasses require layout audit'
    ti,=[i for i,r in enumerate(target.a.instances) if target.a.mn_name(r[0])==owner]
    si,=[i for i,r in enumerate(source.a.instances) if source.a.mn_name(r[0])==owner]
    slots=['wtsReadyNormalNext','wtsReadyFeverNext','geraldReadyNext']
    for name in slots:
        assert not any(target.a.mn_name(t.name)==name for t in target.a.instances[ti][6])
        trait,=[t for t in source.a.instances[si][6] if source.a.mn_name(t.name)==name]
        assert source.a.mn_name(trait.data[2])=='int' and trait.kind==0
        target.a.instances[ti][6].append(importer.trait(trait))
    result=[]
    sig=lambda v,m:(v.mn(v.a.methods[m][0]),tuple(v.mn(x) for x in v.a.methods[m][1]),v.a.methods[m][3])
    for bi in MAIN_BODIES:
        sb=source.a.bodies[bi];label=source.labels[sb[0]];ai,=target.by_label[label]
        original=old.bodies[ai]
        assert sig(target,original[0])==sig(source,sb[0]),(label,'native method signature differs')
        if original[0]==18394:
            body=voice_extension(importer,bi,original)
            lowered=dict(native_strategy='preload_extension_then_original_native',source_span=[112,160],sound_main_ready_guards=True)
        else:
            body=importer.body(bi,original[0],scope=original[3])
            lowered=lower_constant_casts(body,target.a)
        assert activation_traits(target,original)==activation_traits(target,body),(label,'activation ABI differs')
        assert not any(i.op in (0x40,0x65,0x67) for i in asm.decode(body[5])),(label,'lexical capture requires separate audit')
        target.a.bodies[ai]=body
        result.append(dict(label=label,method_id=original[0],body_index=ai,android_body=bi,normalization=lowered,checks=check_body(body,target.a)))
    # R4: trailing int traits still precede all pointer slots in AIR's arm64
    # layout. Keep the retained native HUD constructor/run/accessors valid.
    from hud_state_layout import correct_traits,correct_body,slot_offsets
    correct_traits(target.a)
    hud_reads=correct_body(target.a)
    old_hud_offsets=slot_offsets(old);new_hud_offsets=slot_offsets(target.a)
    assert all(new_hud_offsets[n]==offset for n,offset in old_hud_offsets.items())
    hud_record=next(r for r in result if r['method_id']==63979)
    hud_record['normalization']['integer_counter_reads']=hud_reads
    hud_record['checks']=check_body(target.a.bodies[hud_record['body_index']],target.a)
    lifecycles=[]
    for owner in sorted(set(r['label'].split('/')[0].rstrip('$') for r in result)):
        label='script:'+owner+'/<init>';ai,=target.by_label[label];bi,=source.by_label[label]
        original=old.bodies[ai]
        target.a.bodies[ai]=importer.body(bi,original[0],scope=original[3])
        if target.a.bodies[ai][4]!=original[4]:
            # FFDec rebuilt this Android owner with an expanded superclass
            # scope chain. The iOS Haxe class uses its original one-parent
            # lexical chain. Restore that compiler-only declaration shape;
            # the actual iOS script initializer remains native and unchanged.
            assert owner=='pinball.common.data.character::BattleCharacterLogic'
            ci,=[i for i,r in enumerate(target.a.instances) if target.a.mn_name(r[0])==owner]
            name,superclass=target.a.instances[ci][:2]
            ins=asm.assemble([('getlocal_0',),('pushscope',),('getglobalscope',),('getlex',superclass),('pushscope',),
                ('getlex',superclass),('newclass',ci),('popscope',),('initproperty',name),('returnvoid',)])
            code,_=asm.encode(ins)
            target.a.bodies[ai]=[original[0],2,1,original[3],original[4],code,[],[]]
        lifecycles.append(dict(label=label,method_id=original[0],body_index=ai))
    changes={r['method_id'] for r in result+lifecycles}
    for a,b in zip(old.bodies,target.a.bodies):
        if a[0] not in changes:assert freeze(a)==freeze(b),('unrelated body',a[0])
    for pool in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
        assert freeze(getattr(old,pool))==freeze(getattr(target.a,pool)[:len(getattr(old,pool))]),pool
    assert freeze(old.methods)==freeze(target.a.methods[:OLD_COUNT])
    for name in ('metadata','classes','scripts'):
        rows=getattr(old,name);assert freeze(rows)==freeze(getattr(target.a,name)[:len(rows)]),name
    for i,(a,b) in enumerate(zip(old.instances,target.a.instances)):
        assert freeze(a[:6])==freeze(b[:6])
        assert freeze(a[6])==freeze(b[6][:len(a[6])]) and len(b[6])-len(a[6])==(3 if i==ti else 0)
    checks=[]
    for b in target.a.bodies[len(old.bodies):]:checks.append(dict(method=b[0],checks=check_body(b,target.a)))
    # Only compile this delta. Earlier full compiler inputs retain several huge
    # already-linked Lens bodies; recompiling them serves no purpose and can
    # crash the legacy compiler. Their actual native code and runtime metadata
    # are preserved by the native linker, independently of this compiler input.
    abc_va,abc_len=struct.unpack_from('<QQ',native,INFO_OFFSET+24)
    pos=32;matches=[]
    for _ in range(struct.unpack_from('<I',native,16)[0]):
        command,size=struct.unpack_from('<II',native,pos)
        if command==0x19:
            vm,_,off,fs=struct.unpack_from('<QQQQ',native,pos+24)
            if vm<=abc_va and abc_va+abc_len<=vm+fs:matches.append(off+abc_va-vm)
        pos+=size
    assert len(matches)==1
    runtime_raw=native[matches[0]:matches[0]+abc_len]
    runtime=abcfmt.ABC(runtime_raw);by_mid={b[0]:b for b in runtime.bodies}
    sys.path.insert(0,str(LEGACY))
    from fill_ios_aot_stub_bodies import return_stub
    for i,b in enumerate(target.a.bodies):
        if b[0]<OLD_COUNT and b[0] not in changes:
            stub=copy.deepcopy(by_mid[b[0]])
            stub[5]=return_stub(target.a.mn_name(target.a.methods[b[0]][0]));stub[6]=[]
            target.a.bodies[i]=stub
    compiled=target.a.serialize();assert abcfmt.ABC(compiled).serialize()==compiled
    put(WORK/'cumulative-full-r8.abc',compiled)
    report=dict(status='compiler_input_prepared_native_link_pending',source_ipa=reg,source_full_sha256=sha(full),
        android_apk_sha256=APK_SHA,android_swf_sha256=SWF_SHA,methods=result,helpers=helper_records,
        compiler_only_lifecycles=lifecycles,added_hud_slots=slots,hud_slot_offsets=new_hud_offsets,helper_body_checks=checks,
        old_methods=OLD_COUNT,total_methods=len(target.a.methods),old_scripts=len(old.scripts),total_scripts=len(target.a.scripts),
        full_abc_file='cumulative-full-r8.abc',full_abc_sha256=sha(compiled),full_abc_sha1=hashlib.sha1(compiled).hexdigest(),
        baseline_runtime_abc_sha256=sha(runtime_raw),compiler_delta_only=True,
        endpoint_storage_and_title_cntips_unchanged=True,desktop_air_run=False)
    dump(WORK/'port.json',report)
    print(json.dumps({k:report[k] for k in ('status','old_methods','total_methods','old_scripts','total_scripts','full_abc_sha256')}))

if __name__=='__main__':main()
