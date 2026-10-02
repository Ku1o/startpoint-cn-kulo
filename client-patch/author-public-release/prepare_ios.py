"""Port accepted Android rules onto the accepted iOS SET-fix AOT unit.

Keep all old pools, methods and native field layouts. New rule arrays live in
weak side tables; the four address integers use trailing Number storage.
"""
import copy, struct, subprocess, sys, zipfile
from common import *
sys.path.insert(0,str(HERE.parent/'ios-cumulative-login'))
import prepare as p
p.asm.MNEMONICS['avm_label']=0x09; p.asm.BY_OPCODE[0x09]='avm_label'
from build_native import file_offset
from hud_state_layout import slot_offsets, COUNTERS
lan = load('author_ios_pool', HERE.parent/'r10-public-release/build_lan.py')
s=lan.s
W=WORK/'ios'
INFO=104549248
TOTALIZER='pinball.scene.battle.battle.ability::MemberAbilityTotalizerImpl'
MEMBER='pinball.scene.battle.battle.squad.member::MemberImpl'
ADDRESS='pinball.online.battle.address::InstantAbilityAddress'
FIELDS=('wfGainKind','wfGainCategory','wfGainOwner','wfGainTrigger')

def index(abc, cls):
    return next(n for n,r in enumerate(abc.instances) if abc.mn_name(r[0])==cls)

def q(abc, name):
    matches=[n for n in range(1,len(abc.multinames)) if abc.multinames[n][0]==7 and abc.mn_name(n)==name
             and abc.namespaces[abc.multinames[n][1]][0] in (0x08,0x16)]
    assert matches,name
    return matches[0]

def accessor(abc, ci, slot, static, getter, setter):
    traits=abc.classes[ci][1] if static else abc.instances[ci][6]
    output=[]
    for kind,code in ((2,getter),(3,setter)):
        mid=len(abc.methods)
        typ=slot.data[2]
        abc.methods.append([typ if kind==2 else q(abc,'void'), [] if kind==2 else [typ], 0,0,None,None])
        ins=p.asm.assemble([('getlocal_0',),('pushscope',)]+code)
        metrics=p.asm.simulate(ins,1,abc.multinames)
        body=[mid,max(1,metrics[0]),1 if kind==2 else 2,1,metrics[1],p.asm.encode(ins)[0],[],[]]
        abc.bodies.append(body)
        t=p.abcfmt.Trait();t.name=slot.name;t.kind=kind;t.attr=0;t.metadata=[];t.data=['method',0,mid]
        traits.append(t);p.check_body(body,abc)
        output.append(mid)
    return output

def integer_reads(body,abc,names):
    old=p.asm.decode(body[5]); rows=[]; mapping={}; added=[]
    for n,ins in enumerate(old):
        mapping[n]=len(rows);rows.append(copy.deepcopy(ins))
        if ins.op==0x66 and abc.mn_name(ins.args[0]) in names and (n+1==len(old) or old[n+1].op!=0x73):
            rows.append(p.asm.Instruction(0x73));added.append(n)
    mapping[len(old)]=len(rows)
    for ins in rows:
        if ins.target is not None:ins.target=mapping[ins.target]
        if ins.default is not None:ins.default=mapping[ins.default]
        if ins.cases is not None:ins.cases=[mapping[n] for n in ins.cases]
    oldoffsets=p.asm.encode(old)[1]+[len(body[5])]
    code,newoffsets=p.asm.encode(rows);newoffsets.append(len(code));at={o:n for n,o in enumerate(oldoffsets)}
    body[6]=[(newoffsets[mapping[at[a]]],newoffsets[mapping[at[b]]],newoffsets[mapping[at[c]]],d,e) for a,b,c,d,e in body[6]]
    body[5]=code
    return added

def main():
    W.mkdir(parents=True,exist_ok=True)
    assert sha(IPA.read_bytes())==IPA_SHA and sha(IOS_FULL.read_bytes())==IOS_FULL_SHA
    with zipfile.ZipFile(IPA) as z:
        native=z.read('Payload/worldflipper.app/worldflipper');swf=z.read('Payload/worldflipper.app/worldflipper_ios_release.swf')
    assert sha(native)==IOS_NATIVE_SHA and sha(swf)==IOS_SWF_SHA
    (W/'baseline-native').write_bytes(native);(W/'baseline.swf').write_bytes(swf)
    with zipfile.ZipFile(APK) as z:android=z.read('assets/worldflipper_android_release.swf')
    assert sha(APK.read_bytes())==APK_SHA and sha(android)==ANDROID_SWF_SHA
    (W/'android-accepted.swf').write_bytes(android)
    previous=Path('F:/codex/outputs/set-edit-c8601-public-20260924/StarPoint-CN-1.8.1-independent-formations-set-edit-c8601-public-20260924-0fcf027e.apk')
    assert sha(previous.read_bytes())=='f24f469c1be0cb3d2d16520a739ace52b58055ce65621f5243404026beba6066'
    with zipfile.ZipFile(previous) as z:(W/'android-before.swf').write_bytes(z.read('assets/worldflipper_android_release.swf'))
    target=p.view(p.abcfmt.ABC(IOS_FULL.read_bytes()));a=target.a;before=copy.deepcopy(a)
    assert len(a.methods)==101315
    source=p.View(p.SwfAbc(W/'android-accepted.swf'),p.asm)
    original=p.View(p.SwfAbc(W/'android-before.swf'),p.asm)
    swc=W/'author-state.swc'
    command=['D:/java/bin/java.exe','-Dflexlib='+str(p.SDK/'frameworks'),'-Xmx512m','-jar',str(p.SDK/'lib/compc-cli.jar'),
             '+configname=air','-swf-version=44','-target-player=32.0','-debug=false',
             '-compiler.source-path='+str(HERE/'src'),'-include-classes=cn.mod.AuthorState','-output='+str(swc)]
    r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    (W/'compile-state.log').write_bytes(r.stdout)
    assert r.returncode==0,'State helper compiler failed; inspect compile-state.log'
    helpers=[]
    _,_,tags=s.parts(W/'android-accepted.swf')
    visual,=[t[3] for t in tags if t[0]==82 and t[2][4:-1]==b'cn.mod.InahoAbilityVisuals']
    for helper in (visual,s.helper_abc(swc)):
        start=len(a.methods);p.ClassImporter(target,p.view(helper)).merge()
        helpers.append({'class':helper.mn_name(helper.instances[0][0]),'first':start,'count':len(helper.methods)})
    # Map six new methods before importing any call sites or traits.
    imp=p.Importer(target,source); additions=[]
    for mi in range(len(original.a.methods),len(source.a.methods)):
        target_mid=len(a.methods);imp.methods[mi]=target_mid
        a.methods.append(imp.info(mi));additions.append((mi,target_mid))
    state=q(a,'cn.mod::AuthorState');added_traits=[];storage=[]
    for cls in (TOTALIZER,MEMBER,ADDRESS):
        ti=index(a,cls);si=index(source.a,cls);oi=index(original.a,cls)
        assert not any(a.mn_name(row[1])==cls for row in a.instances), 'Subclass layout requires audit'
        for static,old_traits,new_traits in ((False,original.a.instances[oi][6],source.a.instances[si][6]),
                                           (True,original.a.classes[oi][1],source.a.classes[si][1])):
            for oldtrait in new_traits[len(old_traits):]:
                trait=imp.trait(oldtrait);name=a.mn_name(trait.name)
                if name in ('wfGaugeRules','wfDamageRules'):
                    suffix='Gauge' if name=='wfGaugeRules' else 'Damage'
                    mids=accessor(a,ti,trait,False,
                        [('getlex',state),('getlocal_0',),('callproperty',q(a,'get'+suffix),1),('returnvalue',)],
                        [('getlex',state),('getlocal_0',),('getlocal_1',),('callpropvoid',q(a,'set'+suffix),2),('returnvoid',)])
                    storage.append({'class':cls,'name':name,'strategy':'weak_dictionary_accessors','methods':mids})
                elif name=='wfGaugeContext':
                    mids=accessor(a,ti,trait,True,
                        [('getlex',state),('getproperty',q(a,'context')),('returnvalue',)],
                        [('getlex',state),('getlocal_1',),('setproperty',q(a,'context')),('returnvoid',)])
                    storage.append({'class':cls,'name':name,'strategy':'external_static_accessors','methods':mids})
                else:
                    if name in FIELDS:
                        zeros=[j for j,x in enumerate(a.doubles) if j and x==0.0]
                        if not zeros:a.doubles.append(0.0);zeros=[len(a.doubles)-1]
                        trait.data=list(trait.data);trait.data[2:]=[q(a,'Number'),zeros[0],6]
                        storage.append({'class':cls,'name':name,'strategy':'trailing_number_with_integer_reads'})
                    (a.classes[ti][1] if static else a.instances[ti][6]).append(trait)
                added_traits.append({'class':cls,'static':static,'name':name})
    for source_mid,target_mid in additions:
        bi,=[n for n,b in enumerate(source.a.bodies) if b[0]==source_mid]
        body=imp.body(bi,target_mid);integer_reads(body,a,FIELDS)
        a.bodies.append(body);p.check_body(body,a)
    changed=[n for n,(x,y) in enumerate(zip(original.a.bodies,source.a.bodies)) if p.freeze(x)!=p.freeze(y)]
    assert len(changed)==31
    for name in ('InstantAbilitySource/resolvePathCollection','AbilityDamageShot/getEffect','AbilityDamageShot/finish'):
        label,=[label for label in original.by_label if label.split('::')[-1].split('|')[0]==name]
        bi,=source.by_label[label];changed.append(bi)
    records=[];redirects=[]
    hooks_class=index(a,'cn.mod::AuthorState')
    qname_module=load('author_ios_qname',HERE.parent/'independent-formations/prepare_set_edit_ios.py')
    for bi in changed:
        label=source.labels[source.a.bodies[bi][0]];ti,=target.by_label[label]
        old=before.bodies[ti]
        strategy='replace'
        guard_kind=None
        if label.startswith('pinball.common.data.ability.description::AbilityDescriptionGenerator/') or old[0]==57004:
            # These original functions own hundreds of native closures. Run
            # only the new early-return guard, then tail-call the retained
            # native function for all other abilities.
            prior=original.a.bodies[bi];current=source.a.bodies[bi]
            at=2 if old[0]==57004 else 4
            guard_kind='integer_minus_one' if old[0]==57004 else 'null_function'
            count=len(p.asm.decode(current[5]))-len(p.asm.decode(prior[5]))
            assert count>0 and p.asm.unsplice(current[5],at,count)==prior[5]
            block=copy.deepcopy(p.asm.decode(current[5])[at:at+count])
            for ins in block:
                assert ins.cases is None and ins.default is None
                if ins.target is not None:
                    assert at<=ins.target<=at+count
                    ins.target+=2-at
            fallback=[('pushbyte',255),('returnvalue',)] if old[0]==57004 else [('pushnull',),('returnvalue',)]
            rows=p.asm.assemble([('getlocal_0',),('pushscope',)])+block+p.asm.assemble(fallback)
            tmp=copy.deepcopy(current);tmp[5]=p.asm.encode(rows)[0];tmp[6]=[];tmp[7]=[]
            tmp[4]=tmp[3]+1
            source.a.bodies.append(tmp)
            try:body=imp.body(len(source.a.bodies)-1,old[0],scope=old[3])
            finally:source.a.bodies.pop()
            strategy='guard_then_original'
        else:
            body=imp.body(bi,old[0],scope=old[3])
            assert p.activation_traits(target,old)==p.activation_traits(target,body),(label,'activation layout')
        normalization=p.lower_constant_casts(body,a)
        normalization['integer_reads']=integer_reads(body,a,set(FIELDS)|set(COUNTERS))
        if old[0]==48643:
            # The original AOT constructor initializes the trait default
            # __enum__=true. A synthetic static compilation hook does not
            # receive AIR's implicit instance-default initializer.
            enum_slot,=[t for t in before.instances[index(before,ADDRESS)][6] if before.mn_name(t.name)=='__enum__']
            assert enum_slot.data[3:]==[11,11]
            insert=p.asm.assemble([('getlocal_0',),('pushtrue',),('setproperty',q(a,'__enum__'))])
            body[5],body[6],_=p.asm.splice(body,2,insert,p.asm.ENTER)
            normalization['explicit_constructor_trait_default']='__enum__=true'
        check=p.check_body(body,a)
        if strategy=='replace':a.bodies[ti]=body
        mid=len(a.methods);a.methods.append(copy.deepcopy(a.methods[old[0]]))
        if strategy=='guard_then_original':a.methods[mid][3]&=~2
        hook=copy.deepcopy(body);hook[0]=mid;a.bodies.append(hook)
        t=p.abcfmt.Trait();t.name=qname_module.qname(a,'cn.mod','authorHook'+str(old[0]));t.kind=1;t.attr=0;t.metadata=[];t.data=['method',0,mid]
        a.classes[hooks_class][1].append(t)
        records.append({'label':label,'method_id':old[0],'body_index':ti,'source_body':bi,'strategy':strategy,
                        'activation_fields':len(old[7]),'normalization':normalization,'checks':check,
                        'source_body_sha256':sha(source.a.bodies[bi][5]),'target_body_sha256':sha(body[5])})
        redirects.append({'original':old[0],'compiled':mid,'label':label,'strategy':strategy,'guard_kind':guard_kind})
    aliases=[]
    # AIR does not emit implementations appended to already-native classes.
    # Materialize the same bodies on the new helper class, then register those
    # addresses under the original new method IDs in the native AOT table.
    external_methods=[target_mid for _,target_mid in additions]
    external_methods += [mid for row in storage for mid in row.get('methods',[])]
    for original_mid in external_methods:
        mid=len(a.methods);a.methods.append(copy.deepcopy(a.methods[original_mid]))
        body=copy.deepcopy(next(b for b in a.bodies if b[0]==original_mid));body[0]=mid;a.bodies.append(body)
        t=p.abcfmt.Trait();t.name=qname_module.qname(a,'cn.mod','authorMethod'+str(original_mid));t.kind=1;t.attr=0;t.metadata=[];t.data=['method',0,mid]
        a.classes[hooks_class][1].append(t)
        aliases.append({'original':original_mid,'compiled':mid})
    # Constant rotation must include the folded HMAC message prefix.
    _,keys=pair()
    repl={OLD_IDS['ios'].encode():IDS['ios'].encode(),keys[OLD_IDS['ios']].encode():keys[IDS['ios']].encode(),
          ('SP-ADMISSION-1\n'+OLD_IDS['ios']+'\n').encode():('SP-ADMISSION-1\n'+IDS['ios']+'\n').encode()}
    string_changes=[]
    for n,value in enumerate(a.strings):
        if value in repl:a.strings[n]=repl[value];string_changes.append(n)
    assert all(old not in a.strings for old in repl)
    assert lan.constants([[82,None,None,a]])==dict(ID=IDS['ios'],KEY=keys[IDS['ios']],ORIGIN='http://175.178.160.158')
    assert [x for x in a.strings if x.startswith(b'SP-ADMISSION-1\n')]==[('SP-ADMISSION-1\n'+IDS['ios']+'\n').encode()]
    # All old method IDs, slots, trait prefixes and pool positions stay fixed.
    expected={r['body_index'] for r in records if r['strategy']=='replace'}
    assert {n for n,(x,y) in enumerate(zip(before.bodies,a.bodies)) if p.freeze(x)!=p.freeze(y)}==expected
    assert p.freeze(before.methods)==p.freeze(a.methods[:len(before.methods)])
    for field in ('metadata','scripts','ints','uints','doubles','namespaces','ns_sets','multinames'):
        old=getattr(before,field);assert p.freeze(old)==p.freeze(getattr(a,field)[:len(old)]),field
    for section in ('instances','classes'):
        for n,old in enumerate(getattr(before,section)):
            row=getattr(a,section)[n];assert p.freeze(old[:-1])==p.freeze(row[:-1])
            assert p.freeze(old[-1])==p.freeze(row[-1][:len(old[-1])]),(section,n)
            if a.mn_name(a.instances[n][0]) in (TOTALIZER,MEMBER):
                assert [p.freeze(t) for t in old[-1] if t.kind in (0,6)]==[p.freeze(t) for t in row[-1] if t.kind in (0,6)]
    assert slot_offsets(before)==slot_offsets(a)
    # The address class has int/bool then references, with no original Number
    # fields or subclasses. New Numbers are the final allocation category.
    old_address=before.instances[index(before,ADDRESS)][6]
    assert [(before.mn_name(t.name),before.mn_name(t.data[2])) for t in old_address if t.kind in (0,6)]==[
        ('tag','String'),('index','int'),('params','Array'),('__enum__','Boolean')]
    full=W/'author-full.abc';full.write_bytes(a.serialize())
    assert p.abcfmt.ABC(full.read_bytes()).serialize()==a.serialize()
    offset=file_offset(native,struct.unpack_from('<Q',native,INFO+24)[0]);length=struct.unpack_from('<Q',native,INFO+32)[0]
    equipment=native[64394848:64394848+548];(W/'abyss-ex-ios-equipment.bin').write_bytes(equipment)
    source_ipa={'ipa':str(IPA),'ipa_sha256':IPA_SHA,'native_member':'Payload/worldflipper.app/worldflipper',
                'swf_member':'Payload/worldflipper.app/worldflipper_ios_release.swf','native_sha256':IOS_NATIVE_SHA,
                'swf_sha256':IOS_SWF_SHA,'bundle_id':'com.kulo.wf','version':'1.8.4','build':'1.8.46',
                'build_id':OLD_IDS['ios'],'signing':'unsigned'}
    port={'source_ipa':source_ipa,'old_methods':len(before.methods),'total_methods':len(a.methods),
          'native_old_count':struct.unpack_from('<Q',native,INFO+56)[0],
          'full_abc_file':full.name,'full_abc_sha256':sha(full.read_bytes()),
          'baseline_runtime_abc_sha256':sha(native[offset:offset+length]),
          'methods':records,'method_redirects':redirects,'native_aliases':aliases,'helpers':helpers,'added_traits':added_traits,
          'storage':storage,'admission_string_indexes':string_changes,
          'equipment':{'offset':64394848,'old_size':548,'new_size':548,'source_sha256':sha(equipment),'sha256':sha(equipment)},
          'hud_layout_unchanged':True,'existing_field_slots_preserved':True,'save_schema_changed':False}
    dump(W/'port.json',port)
    print(json.dumps({k:port[k] for k in ('old_methods','native_old_count','total_methods','full_abc_sha256','storage')}))

if __name__=='__main__':main()
