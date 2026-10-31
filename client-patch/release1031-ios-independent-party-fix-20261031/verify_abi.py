"""Verify only the inspected ARM64 call ABI; reuse the actual-IPA readback."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import struct
import common as c

def main():
    guard=c.bounded_job();proof=c.read(c.TASK/'verify-review/final02-party-proof.json')
    c.require(proof['result']['status']=='independent_actual_stage_package_readback_passed','Missing actual-IPA proof')
    rows={r['method']:r for r in proof['proof']['actual_native_entries']}
    # These words are read independently from the loose native that was compared
    # byte for byte with the IPA; do not trust the instruction receipt alone.
    linked=c.read(c.TASK/'linked01/link-report.json')
    from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
    md=Cs(CS_ARCH_ARM64,CS_MODE_ARM);buffers={}
    with open(linked['native_file'],'rb') as f:
        for row in linked['functions']:
            f.seek(row['file_offset']);raw=f.read(row['size']);c.require(c.sha(raw)==row['sha256'],'Native function identity drift')
            buffers[row['method']]=raw
    expected={
        22164:{0x10:('mov','x19, x1'),0x60:('ldr','x0, [x8, #0x20]'),0x6c:('ldr','x1, [x8, #0xb8]'),
               0x70:('ldr','x8, [x1, #0x10]'),0x74:('ldr','x8, [x8, #0x50]'),0x78:('blr','x8'),0x90:('ret','')},
        42394:{0x20:('mov','x19, x2'),0x28:('mov','x21, x0'),0x4c:('ldr','w8, [x1, #0x20]'),
               0x2f4:('ldr','x22, [x21, #0x40]'),0x318:('ldr','x0, [x8, #0x20]'),0x324:('ldr','w1, [x21, #0x38]'),
               0x328:('ldr','x2, [x8, #0xa8]'),0x334:('blr','x8'),0x350:('mov','x2, x22'),
               0x378:('mov','x0, x22'),0x37c:('mov','x1, x23'),0x380:('mov','x2, x20'),0x388:('blr','x8')},
        52468:{0x1c:('mov','x20, x3'),0x28:('mov','x23, x2'),0x2c:('mov','x24, x1'),0x38:('mov','x21, x0'),
               0x84:('mov','x0, x21'),0x88:('mov','x1, x24'),0x94:('ldr','x2, [x8, #0x10]'),0xa0:('blr','x8'),
               0xa8:('add','x2, x21, #0x58'),0xb0:('mov','x3, x23'),
               0x11c:('ldr','x1, [x8, #0xb0]'),0x128:('blr','x8'),0x12c:('mov','w1, w0'),
               0x1c4:('mov','x2, x0'),0x1c8:('mov','x0, x21'),0x1cc:('mov','x1, x23'),
               0x1d4:('mov','x3, x22'),0x1d8:('mov','x4, x20'),0x1dc:('blr','x8')},
    }
    for mid,checks in expected.items():
        row=next(r for r in linked['functions'] if r['method']==mid)
        actual={i.address-row['address']:(i.mnemonic,i.op_str) for i in md.disasm(buffers[mid],row['address'])}
        c.require(all(actual.get(at)==op for at,op in checks.items()),'Actual receiver/MethodEnv/argument ABI mismatch: '+str(mid))
    p=c.framework();a=p.abcfmt.ABC(c.ABC.read_bytes())
    ci,=[i for i,inst in enumerate(a.instances) if a.mn_name(inst[0])=='cn.mod::IndependentRushParty']
    methods=[(a.mn_name(t.name),t.data[2]) for t in a.classes[ci][1] if t.kind==1]
    c.require(methods[:3]==[('setEventId',101300),('getEventId',101301),('category',101302)],
        'Actual static helper binding prefix changed: '+repr(methods))
    builtin=p.abcfmt.ABC((c.SDK/'lib/aot/lib/builtin.abc').read_bytes());bindings=[]
    for name in ('Object','Class'):
        inst,=[x for x in builtin.instances if builtin.mn_name(x[0])==name]
        bindings.extend((name,builtin.mn_name(t.name),t.kind) for t in inst[6] if t.kind in (1,2,3))
    c.require(bindings==[('Object','isPrototypeOf',1),('Object','hasOwnProperty',1),('Object','propertyIsEnumerable',1),('Class','prototype',2)],
        'Builtin Class method slot model changed')
    c.require(0x80+(3+2)*8==0xa8,'Static helper first slot differs')
    def cache(raw,at):
        x,y=struct.unpack_from('<II',raw,at)
        c.require(x&0x7f80001f==0x52800009 and y&0x7f80001f==0x72800009,'Finddef cache immediate format changed')
        first=((x>>5)&65535)<<(((x>>21)&3)*16);shift=((y>>21)&3)*16
        return (first&~(65535<<shift))|(((y>>5)&65535)<<shift)
    offsets=[cache(buffers[22164],0x38),cache(buffers[42394],0x2ec),cache(buffers[52468],0xd8)]
    c.require(len(set(offsets))==1 and (offsets[0]-0x18)%8==0,'Helper class cache routes differ')
    mn=(offsets[0]-0x18)//8
    c.require(a.mn_name(mn)=='cn.mod::IndependentRushParty','Actual finddef cache selects wrong helper')
    c.dump(c.TASK/'verify-review/abi01.json',dict(status='actual_arm64_three_entry_call_abi_passed',
        actual_ipa_readback='final02.json',native_sha256=linked['native_sha256'],checks=expected,
        helper_bindings=methods,helper_static_offsets=[0xa8,0xb0,0xb8],finddef_multiname=mn,finddef_byte_offset=offsets[0],
        arguments={42394:['x0 receiver','x1 EventRushSummaryRemoteInput','x2 MethodEnv'],
                   52468:['x0 receiver','x1 nullable RealRemote','x2 nullable HookEntrance','x3 MethodEnv'],
                   22164:['x0 receiver','x1 MethodEnv','w0 int return']},
        source_sha256=c.sha(__import__('pathlib').Path(__file__).read_bytes()),bounded_job=guard,
        native_executed=False,device_tested=False))
    print('ARM64 ABI passed for',sorted(expected),'helper class multiname',mn)
if __name__=='__main__':main()
