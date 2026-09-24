"""Independent IPA readback, AOT/rebase checks and ARM64 guard execution."""
import copy, json, plistlib, re, struct, sys, zipfile, zlib
from common import *
sys.path[:0]=[str(HERE.parent/'ios-cumulative-login'),str(HERE.parent/'ios-shop-first-open')]
import prepare as p
p.asm.MNEMONICS['avm_label']=0x09;p.asm.BY_OPCODE[0x09]='avm_label'
import build_native as link
from macho_signing_layout import assert_signable_layout,linkedit_ranges
from test_signing_layout import replace_signature_tail,BROKEN_IPA,FIRST_FIX_IPA
from public_endpoint import require_public_endpoint,runtime_abc
from hud_state_layout import slot_offsets,COUNTERS,R3,R3_SHA
import veneers,capstone
W=WORK/'ios';INFO=104549248
u64=lambda b,at:struct.unpack_from('<Q',b,at)[0]

def execute_guard(native,row):
    sys.path.insert(0,'F:/codex/work/ios-cache-rounded-r2-20260912/test-libs')
    from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X29,UC_ARM64_REG_X30,UC_ARM64_REG_SP,UC_ARM64_REG_PC
    result=[]
    for handled in (False,True):
        uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);pages=set()
        def mapped(address,data):
            start=address&~0xfff;end=(address+len(data)+0xfff)&~0xfff
            for page in range(start,end,0x1000):
                if page not in pages:uc.mem_map(page,0x1000);pages.add(page)
            uc.mem_write(address,data)
        address=row['address'];offset=row['file_offset']
        mapped(address,native[offset:offset+row['size']])
        for stop in (row['guard'],row['fallback'],0x310000):mapped(stop,bytes.fromhex('c0035fd6'))
        uc.mem_map(0x400000,0x20000);initial_sp=0x410000
        original=[0x12340000+i*0x110 for i in range(8)]
        for i,value in enumerate(original):uc.reg_write(UC_ARM64_REG_X0+i,value)
        uc.reg_write(UC_ARM64_REG_X29,0x98760000);uc.reg_write(UC_ARM64_REG_X30,0x310000);uc.reg_write(UC_ARM64_REG_SP,initial_sp)
        seen=[];answer=0x45670000 if row['kind']=='null_function' else 133
        fallback_value=0 if row['kind']=='null_function' else 0xffffffff
        def step(engine,pc,size,data):
            if pc==row['guard']:
                assert [engine.reg_read(UC_ARM64_REG_X0+i) for i in range(8)]==original
                seen.append('guard')
                for i in range(8):engine.reg_write(UC_ARM64_REG_X0+i,0xdead0000+i)
                engine.reg_write(UC_ARM64_REG_X0,answer if handled else fallback_value)
                engine.reg_write(UC_ARM64_REG_PC,engine.reg_read(UC_ARM64_REG_X30))
            elif pc in (row['fallback'],0x310000):seen.append('fallback' if pc==row['fallback'] else 'return');engine.emu_stop()
        uc.hook_add(UC_HOOK_CODE,step)
        uc.emu_start(address,0,count=120)
        assert seen==['guard','return' if handled else 'fallback'],(row['method'],seen)
        if handled:
            assert uc.reg_read(UC_ARM64_REG_X0)==answer and uc.reg_read(UC_ARM64_REG_SP)==initial_sp
        else:
            assert [uc.reg_read(UC_ARM64_REG_X0+i) for i in range(8)]==original
            displaced=row['displaced_instruction']
            if displaced.startswith('b '):assert uc.reg_read(UC_ARM64_REG_SP)==initial_sp
            else:
                amount=re.search(r'#-(0x[0-9a-f]+|\d+)',displaced)
                assert amount and uc.reg_read(UC_ARM64_REG_SP)==initial_sp-int(amount.group(1),0)
        assert uc.reg_read(UC_ARM64_REG_X29)==0x98760000 and uc.reg_read(UC_ARM64_REG_X30)==0x310000
        result.append({'method':row['method'],'handled':handled,'registers_and_stack_preserved':True})
    return result

def main():
    report=json.loads((OUT/'ios/ios-build-report.json').read_text('utf8'))
    port=json.loads((W/'port.json').read_text('utf8'));path=Path(report['ipa'])
    assert sha(path.read_bytes())==report['ipa_sha256']
    with zipfile.ZipFile(IPA) as old,zipfile.ZipFile(path) as new:
        assert old.namelist()==new.namelist() and len(set(new.namelist()))==len(new.namelist()) and new.testzip() is None
        changed=[n for n in old.namelist() if old.read(n)!=new.read(n)]
        assert set(changed)=={'Payload/worldflipper.app/worldflipper','Payload/worldflipper.app/worldflipper_ios_release.swf'}
        before=old.read(changed[0]) if changed[0].endswith('/worldflipper') else old.read(changed[1])
        native=new.read('Payload/worldflipper.app/worldflipper')
        oldswf=old.read('Payload/worldflipper.app/worldflipper_ios_release.swf');swf=new.read('Payload/worldflipper.app/worldflipper_ios_release.swf')
        plist=plistlib.loads(new.read('Payload/worldflipper.app/Info.plist'));members=len(new.namelist())
    assert sha(before)==IOS_NATIVE_SHA and sha(native)==report['native_sha256'] and sha(swf)==report['swf_sha256']
    assert (plist['CFBundleIdentifier'],plist['CFBundleShortVersionString'],plist['CFBundleVersion'])==('com.kulo.wf','1.8.4','1.8.46')
    full=(W/'author-full.abc').read_bytes();abc=p.abcfmt.ABC(full)
    assert sha(full)==port['full_abc_sha256']==report['full_abc_sha256']
    assert native[INFO:INFO+20]==__import__('hashlib').sha1(full).digest()
    plain=lambda b:b[:8]+zlib.decompress(b[8:]) if b[:3]==b'CWS' else b
    assert plain(oldswf).count(bytes(4)+before[INFO:INFO+20])==1
    assert plain(oldswf).replace(bytes(4)+before[INFO:INFO+20],bytes(4)+native[INFO:INFO+20])==plain(swf)
    _,_,oldabc=runtime_abc(before);rt_offset,rt_size,runtime=runtime_abc(native)
    assert sha(native[rt_offset:rt_offset+rt_size])==report['runtime_abc_sha256']
    assert len(runtime.methods)==len(abc.methods)==u64(native,INFO+56)==101387
    assert slot_offsets(oldabc)==slot_offsets(runtime)
    assert [s['name'] for s in link.segments(before)]==[s['name'] for s in link.segments(native)]
    for left,right in zip(link.segments(native),link.segments(native)[1:]):assert left['vm']+left['vs']<=right['vm']
    end=link.segments(before)[-1]['off'];restored=bytearray(native[:end])
    for a,b in report['native_change_ranges']:restored[a:b]=before[a:b]
    assert restored==before[:end]
    oldtable=link.file_offset(before,u64(before,INFO+48));table=link.file_offset(native,u64(native,INFO+48))
    assert oldtable==table
    expected={r['method']:r['target'] for r in report['hooks']}
    for mid in range(report['old_native_count']):assert u64(native,table+mid*8)==expected.get(mid,u64(before,table+mid*8)),mid
    assert u64(native,table+85605*8)==u64(before,table+85605*8),'SET fix pointer changed'
    funcs={r['method']:r for r in report['functions']};aliases={int(k):v for k,v in report['native_aliases'].items()}
    old_functions={int(k):v for k,v in report['registered_prior_methods'].items()}
    for mid in range(report['old_native_count'],len(abc.methods)):
        target=funcs[aliases.get(mid,mid)]['address'] if mid>=101315 else old_functions[mid]['address']
        assert u64(native,table+mid*8)==target,mid
    activation=link.file_offset(native,u64(native,INFO+88))
    assert activation==report['activation_offset']
    assert native[activation:activation+101287*16]==before[activation:activation+101287*16]
    assert native[activation+101287*16:activation+101387*16]==bytes.fromhex('ffffffff000000000000000000000000')*100
    for row in report['functions']+list(old_functions.values()):
        at=row['file_offset'];assert sha(native[at:at+row['size']])==row['sha256']
    md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN)
    def branch(pc):
        off=link.file_offset(native,pc,4);ins,=list(md.disasm(native[off:off+4],pc));assert ins.mnemonic in ('b','bl')
        return int(ins.op_str.removeprefix('#'),16)
    bridges={r['address']:r for r in report['entry_bridges']}
    for row in report['entry_bridges']+report['veneers']:
        at=row['file_offset'];assert native[at:at+16]==veneers.encode(row['address'],row['target'])
    for row in report['hooks']:
        target=branch(row['previous']);target=bridges[target]['target'] if target in bridges else target
        assert target==row['target']
    for row in report['relocations']:
        pc,target,typ=row['pc'],row['target'],row['type'];word=struct.unpack_from('<I',native,link.file_offset(native,pc,4))[0]
        if typ==2:assert branch(pc)==row['branch_target']
        elif typ in (3,5):
            assert word&0x9f000000==0x90000000
            imm=((word>>29)&3)|(((word>>5)&0x7ffff)<<2)
            if imm&(1<<20):imm-=1<<21
            assert (pc&~0xfff)+(imm<<12)==target&~0xfff
        elif typ in (4,6):
            value=(word>>10)&0xfff
            if word&0x7f000000==0x11000000:assert value==target&0xfff
            else:assert word&0x3b000000==0x39000000 and value<<(word>>30)==target&0xfff
        else:raise AssertionError(typ)
    old_rebase=link.read_rebase(before)['entries'];new_rebase=link.read_rebase(native)['entries']
    segment=link.segments(native)[15]
    assert new_rebase==old_rebase+[(15,table+mid*8-segment['off'],1) for mid in range(101287,101387)]
    assert len(new_rebase)==len(set(new_rebase))
    for size in (0x80000,0x200000,0x400000):
        model=replace_signature_tail(native,size,use_ldid=True);assert_signable_layout(model)
        assert link.read_rebase(model)['entries']==new_rebase
        for row in linkedit_ranges(native):
            at=row['offset'];assert model[at:at+row['size']]==native[at:at+row['size']]
    negatives=0
    for path0 in (BROKEN_IPA,FIRST_FIX_IPA):
        with zipfile.ZipFile(path0) as z:bad=z.read('Payload/worldflipper.app/worldflipper')
        try:assert_signable_layout(bad)
        except AssertionError:negatives+=1
    assert negatives==2
    assert sha(R3.read_bytes())==R3_SHA
    with zipfile.ZipFile(R3) as z:_,_,badabc=runtime_abc(z.read('Payload/worldflipper.app/worldflipper'))
    assert slot_offsets(badabc)['featuresPermit']!=slot_offsets(runtime)['featuresPermit']==0x48
    assert native[0x2aca980:0x2aca984]==before[0x2aca980:0x2aca984]
    # The four new address fields are Number slots after the old int/bool and
    # pointer groups. Arrays/context use accessors, adding no existing slots.
    classes=('pinball.scene.battle.battle.ability::MemberAbilityTotalizerImpl','pinball.scene.battle.battle.squad.member::MemberImpl')
    for name in classes:
        ci=next(n for n,r in enumerate(runtime.instances) if runtime.mn_name(r[0])==name)
        for x,y in ((oldabc.instances[ci][6],runtime.instances[ci][6]),(oldabc.classes[ci][1],runtime.classes[ci][1])):
            assert p.freeze([t for t in x if t.kind in (0,6)])==p.freeze([t for t in y if t.kind in (0,6)])
    from prepare_ios import ADDRESS,FIELDS
    ci=next(n for n,r in enumerate(runtime.instances) if runtime.mn_name(r[0])==ADDRESS)
    extra=runtime.instances[ci][6][len(oldabc.instances[ci][6]):]
    assert [runtime.mn_name(t.name) for t in extra]==list(FIELDS)
    assert all(runtime.mn_name(t.data[2])=='Number' and t.data[4]==6 and runtime.doubles[t.data[3]]==0 for t in extra)
    wrapped=[]
    for row in report['guard_wrappers']:wrapped+=execute_guard(native,row)
    # Original enum constructor writes index@0x20, __enum__@0x24,
    # tag@0x28 and params@0x30. Trailing Numbers do not move these slots.
    ctor_va=u64(before,oldtable+48643*8);ctor_off=link.file_offset(before,ctor_va)
    ops={(i.mnemonic,i.op_str) for i in md.disasm(before[ctor_off:ctor_off+144],ctor_va)}
    assert {('mov','w10, #1'),('str','w10, [x24, #0x24]'),('str','w22, [x24, #0x20]'),
            ('add','x2, x24, #0x28'),('add','x2, x24, #0x30')}<=ops
    ctor=next(b for b in abc.bodies if b[0]==48643)
    code=p.asm.decode(ctor[5])
    assert [x.op for x in code[2:5]]==[0xd0,0x26,0x61] and abc.mn_name(code[4].args[0])=='__enum__'
    warnings=(W/'compile-final-defaults.log').read_text('utf8').strip().splitlines()
    assert warnings==['warning: Verify error: cumulative_284:101312:cn.mod::GenericDamage$/cn.mod::formalHook_52468']
    assert 101312 not in funcs and 52468 not in expected
    lan=load('verify_author_admission',HERE.parent/'r10-public-release/build_lan.py');_,keys=pair()
    assert lan.constants([[82,None,None,runtime]])==dict(ID=IDS['ios'],KEY=keys[IDS['ios']],ORIGIN='http://175.178.160.158')
    assert [v for v in runtime.strings if v.startswith(b'SP-ADMISSION-1\n')]==[('SP-ADMISSION-1\n'+IDS['ios']+'\n').encode()]
    result={'status':'offline_verified_public_candidate','ipa':str(path),'ipa_sha256':report['ipa_sha256'],
            'native_sha256':report['native_sha256'],'full_abc_sha256':sha(full),'zip_members_checked':members,
            'only_native_and_swf_changed':True,'set_c8601_and_other_native_code_preserved':True,
            'native_relocations_checked':len(report['relocations']),'new_aot_methods_registered':100,
            'new_field_storage_preserves_original_offsets':True,'hud_r3_negative_detected':True,
            'address_constructor_trait_default_and_native_offsets_verified':True,
            'guard_arm64_executions':wrapped,'ldid_signature_models':3,'historical_bad_signing_layouts_rejected':2,
            'new_methods_have_no_compiler_verification_errors':True,'unlinked_historical_warning':101312,
            'public_bootstrap':require_public_endpoint(native),'build_id':IDS['ios'],
            'save_schema_changed':False,'device_tested':False,'signed':False}
    dump(OUT/'ios/verification-report.json',result)
    (OUT/'ios/author-full.abc').write_bytes(full)
    (OUT/'ios'/ (path.name+'.sha256')).write_text(report['ipa_sha256']+'  '+path.name+'\n',encoding='utf8')
    print(json.dumps({k:result[k] for k in ('status','ipa_sha256','native_relocations_checked','new_aot_methods_registered','ldid_signature_models','device_tested')}))

if __name__=='__main__':main()
