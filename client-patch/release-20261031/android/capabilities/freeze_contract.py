"""Freeze actual final method/trait/closure and unchanged R11 ABI contracts."""
from pathlib import Path
import json
import port_capabilities as p

def trait_bytes(traits):
    w=p.framework.FMT.W()
    for t in traits:p.framework.FMT.write_trait(w,t)
    return w.out()

def sig(abc,method):
    ret,args,name,flags,options,names=abc.methods[method]
    return {'returns':abc.mn_name(ret) if ret else '*',
            'parameters':[abc.mn_name(t) if t else '*' for t in args],
            'flags':flags,'parameter_names':[abc.s(x) for x in names] if names else None}

def main():
    receipt=json.loads((p.ROOT/'build/partial-report.json').read_text('utf-8'))
    source=Path(receipt['latest_partial_swf'])
    successes=[g for g in receipt['groups'] if g.get('status')=='built_partial']
    assert p.digest(source.read_bytes())==successes[-1]['output_sha256']
    old=p.SwfAbc(p.BASE);new=p.SwfAbc(source)
    assert len(old.abc.instances)==len(new.abc.instances)
    states=[];traits=[]
    for i,(a,b) in enumerate(zip(old.abc.instances,new.abc.instances)):
        assert a[:6]==b[:6],('existing class layout header changed',i)
        assert trait_bytes(a[6])==trait_bytes(b[6][:len(a[6])]),('instance trait prefix changed',i)
        assert old.abc.classes[i][0]==new.abc.classes[i][0]
        at,bt=old.abc.classes[i][1],new.abc.classes[i][1]
        assert trait_bytes(at)==trait_bytes(bt[:len(at)]),('static trait prefix changed',i)
        for static,extra in [(False,b[6][len(a[6]):]),(True,bt[len(at):])]:
            for t in extra:
                row={'class':new.abc.mn_name(b[0]),'name':new.abc.mn_name(t.name),'static':static,'kind':t.kind,'data_kind':t.data[0]}
                if t.data[0]=='slot':
                    assert static,'unreviewed new instance state'
                    row['type']=new.abc.mn_name(t.data[2]) if t.data[2] else '*'
                    row['default_index']=t.data[3];row['default_kind']=t.data[4]
                    states.append(row)
                else:
                    row['method']=t.data[2]
                traits.append(row)
    for pool in ['ints','uints','doubles','strings','namespaces','ns_sets','multinames']:
        # float NaN sentinel needs byte-aware treatment.
        a,b=getattr(old.abc,pool),getattr(new.abc,pool)
        if pool=='doubles':
            import struct
            assert [struct.pack('<d',v) for v in a]==[struct.pack('<d',v) for v in b[:len(a)]]
        else:assert a==b[:len(a)],('old constant pool prefix changed',pool)
    labels=p.bodies.label_map(new.abc)
    methods=[]
    for bi,body in enumerate(new.abc.bodies):
        added=bi>=len(old.abc.bodies)
        if not added and p.body_bytes(body)==p.body_bytes(old.abc.bodies[bi]):continue
        label=labels.get(bi,'anonymous/closure:'+str(body[0]))
        calls=[]
        for op in p.asm.decode(body[5]):
            if op.name in ('callproperty','callpropvoid','getproperty','setproperty','getlex'):
                name=new.abc.mn_name(op.args[0])
                if 'wfx' in name or 'Riven' in name:calls.append({'opcode':op.name,'name':name})
        methods.append({'label':label,'body':bi,'method':body[0],'added':added,'code_sha256':p.digest(body[5]),
            'header':body[1:5],'signature':sig(new.abc,body[0]),'helpers_or_state':calls,
            'static_check':p.check_body(new.abc,body)})
    assert not any('wfxStage' in row['label'] for row in methods),'old163 helper survived fresh build'
    assert not any('riven' in row['label'].lower() for row in methods),'excluded riven method'
    changed_tags={'boot_ffc6'}
    if any(g.get('aux') for g in successes):changed_tags.add('cn.mod.InahoAbilityVisuals')
    envelope=p.envelope(old,new,changed_tags)
    report={'status':'partial_offline_candidate_pending_native_and_content_acceptance',
            'swf':str(source),'sha256':successes[-1]['output_sha256'],'baseline':str(p.BASE),'baseline_sha256':p.BASE_SHA,
            'methods':methods,'traits':traits,'new_static_states':states,
            'existing_instance_layout_prefix_preserved':True,'old_constant_pool_prefixes_preserved':True,
            'envelope':envelope,'old_163_absent':True,'device_tested':False,
            'not_implemented':['147 mirror debug counters (outside selected required gameplay set)'],
            'latest_group_status':{g['name']:g['status'] for g in receipt['groups']},
            'external_pending':['163 corrected cn.carry helper by independent owner','195P1-P5 root composition'],
            'native_validation':'193/194 interpreter check; separate AIR fixture status must be inspected'}
    out=p.ROOT/'build/ios-method-contract.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'contract':str(out),'swf':str(source),'sha256':report['sha256'],
                      'methods':len(methods),'added_methods':sum(m['added'] for m in methods),
                      'static_states':len(states),'old163_absent':True},ensure_ascii=False))

if __name__=='__main__':main()
