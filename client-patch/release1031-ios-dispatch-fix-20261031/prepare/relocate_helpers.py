"""Move reviewed instance helpers into one append-only static helper class.

This is ABC preparation only. It does not compile, link, alter admission data,
update accepted registries, or make a device-execution claim. Unreviewed lexical,
private/protected, activation, reflection and function-value uses fail closed.
"""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse, copy, hashlib, json, sys, types
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lens0907-0908'))
import build_swf as p

DEFAULT_METHODS = (101732,101820,101821,101665,101666,101667,101668,101669,
    101670,101685,101686,101687,101688,101689,101690,101691,101692,101697,
    101698,101702,101725,101729,101730,101812,101711)
HELPER_OWNER = 'cn.release::DispatchHelpers20261031'
POOLS = ('ints', 'uints', 'doubles', 'strings', 'namespaces', 'ns_sets', 'multinames')
PUBLIC_NAMESPACES = (0x08, 0x16)
LOCAL_OPERANDS = (0x08, 0x62, 0x63, 0x92, 0x94, 0xc2, 0xc3)
UNSUPPORTED_MOVED_OPS = (0x04,0x05,0x43,0x45,0x49,0x4e,0x58,0x67)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def view(a): return p.View(types.SimpleNamespace(abc=a), p.asm)
def save(path, data): path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def instruction_token(x):
    return [x.op, x.args, x.target, x.default, x.cases]

def local_transform(x, delta):
    """Shift every explicit local register, including compact local opcodes."""
    y=copy.deepcopy(x)
    if 0xd0 <= y.op <= 0xd3:
        index=y.op-0xd0+delta
        y.op, y.args=(0xd0+index, []) if index<4 else (0x62, [index])
    elif 0xd4 <= y.op <= 0xd7:
        index=y.op-0xd4+delta
        y.op, y.args=(0xd4+index, []) if index<4 else (0x63, [index])
    elif y.op in LOCAL_OPERANDS:
        y.args[0]+=delta
        if y.op in (0x62,0x63) and y.args[0]<4:
            y.op=(0xd0 if y.op==0x62 else 0xd4)+y.args[0];y.args=[]
    elif y.op==0x32:
        y.args=[i+delta for i in y.args]
    elif y.op==0xef and y.args[0]==1:
        y.args[2]+=delta
    return y

def normalize_locals(x):
    """Normalize compact register instructions only for inverse comparison."""
    y=copy.deepcopy(x)
    if 0xd0 <= y.op <= 0xd3:y.op,y.args=0x62,[y.op-0xd0]
    elif 0xd4 <= y.op <= 0xd7:y.op,y.args=0x63,[y.op-0xd4]
    return instruction_token(y)

def relocate_exceptions(old_code, new_rows, exceptions, mapping=None):
    old_rows=p.asm.decode(old_code)
    _,old_offsets=p.asm.encode(old_rows);old_offsets.append(len(old_code))
    new_code,new_offsets=p.asm.encode(new_rows);new_offsets.append(len(new_code))
    index={at:i for i,at in enumerate(old_offsets)}
    if mapping is None:mapping={i:i for i in range(len(old_offsets))}
    return new_code, [(new_offsets[mapping[index[a]]],new_offsets[mapping[index[b]]],
                      new_offsets[mapping[index[c]]],d,e) for a,b,c,d,e in exceptions]

def multiname_namespaces(a, mi):
    row=a.multinames[mi]
    if row[0] in (7,13):return [row[1]]
    if row[0] in (9,14):return a.ns_sets[row[2]]
    if row[0] in (27,28):return a.ns_sets[row[1]]
    if row[0]==29:return multiname_namespaces(a,row[1])+[ns for x in row[2] for ns in multiname_namespaces(a,x)]
    raise ValueError(('runtime-resolved namespace needs explicit review',mi,row))

def short_name(a, mi):
    row=a.multinames[mi]
    if row[0] in (7,13):return a.s(row[2])
    if row[0] in (9,14,15,16):return a.s(row[1])
    return None

def looks_like_stub(body):
    rows=p.asm.decode(body[5])
    allowed={0x02,0x09,0x20,0x21,0x24,0x25,0x26,0x27,0x28,0x30,0x47,0x48,
             0x70,0x73,0x74,0x75,0x76,0x77,0x80,0x82,0x85,0xd0}
    return len(rows)<=8 and all(x.op in allowed for x in rows)

class PoolAppender:
    def __init__(self,a):self.a=a
    def put(self,pool,value):
        rows=getattr(self.a,pool)
        for i,row in enumerate(rows[1:],1):
            if row==value:return i
        rows.append(value);return len(rows)-1
    def string(self,text):return self.put('strings',text.encode('utf-8'))
    def qname(self,package,name):
        ns=self.put('namespaces',(0x16,self.string(package)))
        return self.put('multinames',(7,ns,self.string(name)))

def trait(name,kind,data):
    t=p.abcfmt.Trait();t.name=name;t.kind=kind;t.attr=0;t.data=data;t.metadata=[];return t

def append_function(a, returns, params, body_code, *, init_scope=0, max_scope=1, locals_=1, max_stack=2):
    mid=len(a.methods);a.methods.append([returns,params,0,0,None,None])
    raw=p.asm.encode(p.asm.assemble(body_code))[0]
    b=[mid,max_stack,locals_,init_scope,max_scope,raw,[],[]]
    p.check_body(b,a);a.bodies.append(b);return mid

def append_helper_class(a,pool):
    assert not any(a.mn_name(r[0])==HELPER_OWNER for r in a.instances),'helper already installed'
    owner=pool.qname('cn.release','DispatchHelpers20261031')
    obj=pool.qname('','Object');void=pool.qname('','void')
    ci=len(a.instances)
    cinit=append_function(a,void,[],[('returnvoid',)],max_scope=0,max_stack=0)
    iinit=append_function(a,void,[],[('getlocal_0',),('pushscope',),('getlocal_0',),('constructsuper',0),('returnvoid',)],max_stack=1)
    a.instances.append([owner,obj,3,None,[],iinit,[]])
    a.classes.append([cinit,[]])
    sinit=append_function(a,void,[],[('getlocal_0',),('pushscope',),('getscopeobject',0),
        ('getlex',obj),('dup',),('pushscope',),('newclass',ci),('popscope',),
        ('initproperty',owner),('returnvoid',)],max_scope=2,max_stack=3)
    a.scripts.append([sinit,[trait(owner,4,['class',0,ci])]])
    return ci,owner,[cinit,iinit,sinit]

def review_helper(a, mid, bodies):
    matches=[(ci,t) for ci,r in enumerate(a.instances) for t in r[6]
             if t.kind in (1,2,3) and t.data[2]==mid]
    assert len(matches)==1,('expected one instance helper declaration',mid,matches)
    ci,t=matches[0]
    assert t.kind==1 and not t.attr and not t.metadata and t.data[1]==0,('plain nonoverride method required',mid)
    assert a.methods[mid][3] & 5 == 0,('arguments/rest flags require dedicated relocation',mid)
    b=bodies[mid];assert not looks_like_stub(b),('helper body is an AOT return stub',mid)
    assert bool(b[7]) == bool(a.methods[mid][3]&2),('activation flag/traits mismatch',mid)
    ns=[]
    for x in p.asm.decode(b[5]):
        assert x.op not in UNSUPPORTED_MOVED_OPS,('owner/lexical-sensitive opcode',mid,x.name)
        if x.op in p.MULTINAME_OPS:
            for ni in multiname_namespaces(a,x.args[0]):
                ns.append(dict(index=ni,kind=a.namespaces[ni][0],uri=a.ns_name(ni)))
    return dict(old_mid=mid,ci=ci,owner=a.mn_name(a.instances[ci][0]),owner_multiname=a.instances[ci][0],
                receiver_type=a.mn_name(a.instances[ci][0]),old_qname=t.name,name=short_name(a,t.name),
                namespaces=list({r['index']:r for r in ns}.values()))

def audit_scope_namespaces(a, selected_bodies):
    """Retain identity tokens and prove each local/activation scope access."""
    activations={t.name:t for b in selected_bodies for t in b[7]}
    activation_ns={a.multinames[t.name][1] for t in activations.values()}
    used_nonpublic=set();scope_records=[]
    for b in selected_bodies:
        rows=p.asm.decode(b[5]);scope_ops=[(i,x.args[0]) for i,x in enumerate(rows) if x.op==0x65]
        if scope_ops:
            assert b[0]==101665 and all(index==1 for _,index in scope_ops),('unreviewed local scope indexing',b[0])
            assert [x.op for x in rows[:2]]==[0xd0,0x30]
            assert [x.op for x in rows[9:13]]==[0x57,0x2a,0x63,0x30]
            scope_records.append(dict(method=b[0],getscopeobject_count=len(scope_ops),old_indices=[1],new_indices=[2],
                old_local_scope=['original_receiver','original_18_slot_activation'],
                new_local_scope=['static_helper_class','original_receiver','original_18_slot_activation'],outer_scope_reads=0))
        for x in rows:
            assert x.op!=0x67,('outer lexical scope needs dedicated adapter',b[0])
            if x.op not in p.MULTINAME_OPS:continue
            mn=a.multinames[x.args[0]]
            for ni in multiname_namespaces(a,x.args[0]):
                if a.namespaces[ni][0] in PUBLIC_NAMESPACES:continue
                used_nonpublic.add(ni)
                if mn[0] in (7,13):
                    assert x.args[0] in activations,('nonpublic direct QName is not preserved activation',b[0],x.args[0])
                    assert ni in activation_ns
    forbidden=[]
    for inst,cls in zip(a.instances,a.classes):
        for t in inst[6]+cls[1]:
            mn=a.multinames[t.name]
            if mn[0] in (7,13) and mn[1] in used_nonpublic:
                forbidden.append((a.mn_name(inst[0]),t.name))
    assert not forbidden,('actual nonpublic class bindings require dedicated adapter',forbidden)
    return dict(local_scope_evidence=scope_records,namespace_indices_preserved=True,
        nonpublic_namespace_indices=sorted(used_nonpublic),nonpublic_class_bindings=0,
        activation_namespace_indices=sorted(activation_ns),
        new_scope_header=dict(init_scope_depth=0,max_scope_depth='old_max_scope_minus_old_init_scope_plus_1',
            declaring_static_class_scope_pushed_first=True,original_local_scope_index_delta=1,
            closure_max_scope='old_max_scope_minus_old_init_scope'),
        avm_primary_source='https://raw.githubusercontent.com/adobe/avmplus/master/core/Verifier.cpp#L1989-L2013',
        compiler_shell='scope-shell/scope-metadata.json',
        verifier_probe='scope-verifier-probe01/report.json',negative_verifier_error_id=1058)

def move_body(a, old_body, old_info, record, new_mid, closure_map):
    rows=p.asm.decode(old_body[5]);shifted=[local_transform(x,1) for x in rows]
    assert [normalize_locals(local_transform(x,-1)) for x in shifted]==[normalize_locals(x) for x in rows]
    # Static method verification constrains the first local scope to its class.
    # Keep that required class scope, then every original receiver/activation
    # scope. getscopeobject addresses method-local scopes and shifts by one.
    for x in shifted:
        if x.op==0x40:x.args[0]=closure_map[x.args[0]]
        if x.op==0x65:x.args[0]+=1
        if x.target is not None:x.target+=2
        if x.default is not None:x.default+=2
        if x.cases is not None:x.cases=[t+2 for t in x.cases]
    prefix=p.asm.assemble([('getlocal_0',),('pushscope',)])
    all_rows=prefix+shifted
    code,ex=relocate_exceptions(old_body[5],all_rows,old_body[6],{i:i+2 for i in range(len(rows)+1)})
    restored=copy.deepcopy(shifted);inverse_closures={new:old for old,new in closure_map.items()}
    for x in restored:
        if x.op==0x40:x.args[0]=inverse_closures[x.args[0]]
        if x.op==0x65:x.args[0]-=1
        if x.target is not None:x.target-=2
        if x.default is not None:x.default-=2
        if x.cases is not None:x.cases=[t-2 for t in x.cases]
    assert [normalize_locals(local_transform(x,-1)) for x in restored]==[normalize_locals(x) for x in rows]
    body=copy.deepcopy(old_body);body[0]=new_mid;body[2]+=1;body[5]=code;body[6]=ex
    body[3]=0;body[4]=old_body[4]-old_body[3]+1
    ret,params,name,flags,options,param_names=copy.deepcopy(old_info)
    info=[ret,[record['owner_multiname'],*params],name,flags,options,
          [0,*param_names] if param_names is not None else None]
    assert not flags&5
    return info,body,dict(registers_shifted_by=1,old_receiver_local=0,new_receiver_local=1,
        old_instruction_count=len(rows),new_instruction_count=len(all_rows),
        required_static_class_prologue_instructions=2,old_local_scope_index_delta=1,
        inverse_register_scope_closure_and_cfg_proof=True,exception_regions_preserved=len(ex),
        branches=sum(x.target is not None for x in rows),switches=sum(x.cases is not None for x in rows))

def rewrite_calls(a, body, replacements, helper_owner):
    old=p.asm.decode(body[5]);hits={}
    for i,x in enumerate(old):
        if x.op in p.MULTINAME_OPS and x.args[0] in replacements:
            assert x.op in (0x46,0x4f),('helper used as value/super/lexical property',body[0],i,x.name)
            rec=replacements[x.args[0]]
            assert x.args[1]==len(a.methods[rec['old_mid']][1]),('unexpected helper argc',body[0],i)
            hits[i]=rec
    if not hits:return body,[]
    temp=body[2];max_args=max(old[i].args[1] for i in hits)
    new=[];mapping={};blocks=[]
    for i,x in enumerate(old):
        mapping[i]=len(new)
        if i not in hits:new.append(copy.deepcopy(x));continue
        rec=hits[i];argc=x.args[1]
        # Preserve every value below the receiver and preserve argument order.
        src=[('setlocal',temp+j) for j in range(argc,-1,-1)]
        # Instance dispatch throws for a null receiver before invoking a body.
        # convert_o retains that failure rather than allowing a static helper
        # with a null receiver to take an early-return branch.
        src += [('getlocal',temp),('convert_o',),('setlocal',temp),
                ('getlex',helper_owner)]+[('getlocal',temp+j) for j in range(argc+1)]
        src += [(x.name,rec['new_qname'],argc+1)]
        block=p.asm.assemble(src);start=len(new);new+=block
        blocks.append(dict(old_index=i,new_start=start,new_count=len(block),old_mid=rec['old_mid'],
                           new_mid=rec['new_mid'],argc=argc,temporary_base=temp))
    mapping[len(old)]=len(new)
    for x in new:
        if x.target is not None:x.target=mapping[x.target]
        if x.default is not None:x.default=mapping[x.default]
        if x.cases is not None:x.cases=[mapping[i] for i in x.cases]
    code,ex=relocate_exceptions(body[5],new,body[6],mapping)
    after=copy.deepcopy(body);after[2]+=max_args+1;after[5]=code;after[6]=ex;after[1]+=1
    # Independently collapse each replacement to its original call and remap
    # every original edge. This includes branch/switch targets at a callsite.
    inverse={v:k for k,v in mapping.items()};collapsed=[]
    for i,x in enumerate(old):
        if i in hits:collapsed.append(copy.deepcopy(x));continue
        y=copy.deepcopy(new[mapping[i]])
        if y.target is not None:y.target=inverse[y.target]
        if y.default is not None:y.default=inverse[y.default]
        if y.cases is not None:y.cases=[inverse[j] for j in y.cases]
        collapsed.append(y)
    assert [instruction_token(x) for x in collapsed]==[instruction_token(x) for x in old]
    assert p.asm.encode(collapsed)[0]==body[5]
    p.check_body(after,a)
    return after,blocks

def prepare(a, method_ids=DEFAULT_METHODS, additional_recompile_ids=(), reviewed_tiny_ids=()):
    """Mutate parsed ABC; return a complete preparation and compile-selection receipt."""
    old=copy.deepcopy(a);old_view=view(old);bodies={b[0]:b for b in a.bodies}
    method_ids=tuple(dict.fromkeys(method_ids));assert method_ids
    records=[review_helper(a,mid,bodies) for mid in method_ids]
    closure_ids=set();pending=list(method_ids)
    while pending:
        mid=pending.pop()
        for x in p.asm.decode(bodies[mid][5]):
            if x.op==0x40 and x.args[0] not in closure_ids:
                assert x.args[0] not in method_ids,'nested closure is also a named helper'
                closure_ids.add(x.args[0]);pending.append(x.args[0])
    assert closure_ids in (set(),{101832}),('unreviewed closure graph',closure_ids)
    orphan_ids=set(method_ids)|closure_ids
    scope_evidence=audit_scope_namespaces(a,[bodies[mid] for mid in sorted(orphan_ids)])
    names={r['name'] for r in records};old_mids=set(method_ids)
    old_qnames={r['old_qname'] for r in records}
    # Exact QName references are required. Alternate MN aliases, reflection,
    # or direct function references must be reviewed instead of guessed.
    for b in a.bodies:
        for i,x in enumerate(p.asm.decode(b[5])):
            if x.op in (0x40,0x44) and x.args[0] in old_mids:
                raise ValueError(('direct helper method reference requires adapter',b[0],i,x.name))
            if x.op==0x40 and x.args[0] in closure_ids:
                assert b[0] in orphan_ids,('closure referenced outside relocated graph',b[0],x.args[0])
            if x.op in p.MULTINAME_OPS and short_name(a,x.args[0]) in names:
                assert x.args[0] in old_qnames,('alternate helper QName alias',b[0],i,x.args)
                assert x.op in (0x46,0x4f),('noncall helper reference',b[0],i,x.name)
            if x.op==0x2c and a.s(x.args[0]) in names:
                raise ValueError(('reflection/string helper reference requires review',b[0],i))
    pool=PoolAppender(a);helper_ci,helper_owner,lifecycle=append_helper_class(a,pool)
    closure_map={old_mid:len(a.methods)+i for i,old_mid in enumerate(sorted(closure_ids))}
    closure_records=[]
    for old_mid,new_mid in closure_map.items():
        original=bodies[old_mid];b=copy.deepcopy(original);b[0]=new_mid
        b[3]=0;b[4]=original[4]-original[3]
        rows=p.asm.decode(b[5])
        for x in rows:
            if x.op==0x40:x.args[0]=closure_map[x.args[0]]
        b[5]=p.asm.encode(rows)[0]
        a.methods.append(copy.deepcopy(a.methods[old_mid]));a.bodies.append(b)
        closure_records.append(dict(old_mid=old_mid,new_mid=new_mid,locals_shifted=False,
            old_header=original[:5],new_header=b[:5],activation_preserved=True,
            captured_activation_slots=dict(paths=15,characterOwner=16,featuresPermit=17,_gthis=18),
            before_code_sha256=sha(original[5]),after_code_sha256=sha(b[5]),checks=p.check_body(b,a)))
    for rec in records:
        rec['new_mid']=len(a.methods)
        rec['new_qname']=pool.qname('',f"m{rec['old_mid']}_{rec['name']}")
        info,b,proof=move_body(a,bodies[rec['old_mid']],a.methods[rec['old_mid']],rec,rec['new_mid'],closure_map)
        a.methods.append(info);a.bodies.append(b)
        a.classes[helper_ci][1].append(trait(rec['new_qname'],1,['method',0,rec['new_mid']]))
        rec['proof']=proof;rec['register_shift_checks']=p.check_body(b,a)
        rec['before_code_sha256']=sha(bodies[rec['old_mid']][5]);rec['register_shifted_code_sha256']=sha(b[5])
        a.instances[rec['ci']][6]=[t for t in a.instances[rec['ci']][6]
            if not (t.kind in (1,2,3) and t.data[2]==rec['old_mid'])]
    replacements={r['old_qname']:r for r in records}
    callers=[];changed=set();all_rewritten=set()
    for bi,b in enumerate(a.bodies):
        if b[0] in orphan_ids:continue
        after,hits=rewrite_calls(a,b,replacements,helper_owner)
        if hits:
            a.bodies[bi]=after;all_rewritten.add(b[0])
            if b[0]<len(old.methods):changed.add(b[0])
            callers.append(dict(method_id=b[0],label=old_view.labels.get(b[0]),is_existing=b[0]<len(old.methods),
                before_code_sha256=sha(b[5]),after_code_sha256=sha(after[5]),calls=hits,
                original_operations_and_cfg_inverse_proven=True,activation_traits_preserved=p.freeze(b[7])==p.freeze(after[7]),
                original_local_prefix_preserved=b[2],checks=p.check_body(after,a)))
    extras=sorted(set(additional_recompile_ids)-orphan_ids-changed)
    final_bodies={b[0]:b for b in a.bodies}
    for rec in records:
        rec['after_code_sha256']=sha(final_bodies[rec['new_mid']][5])
        rec['checks']=p.check_body(final_bodies[rec['new_mid']],a)
    for mid in extras:
        assert mid in bodies,('missing additional compilation body',mid)
        assert not looks_like_stub(bodies[mid]) or mid in reviewed_tiny_ids,('additional recompile body is possible AOT return stub; restore actual body first',mid)
        p.check_body(bodies[mid],a)
    # Freeze every original MethodInfo, constant-pool entry, static declaration,
    # metadata row, script, field, activation and unrelated existing body.
    assert p.freeze(a.methods[:len(old.methods)])==p.freeze(old.methods)
    for key in POOLS:
        assert p.freeze(getattr(a,key)[:len(getattr(old,key))])==p.freeze(getattr(old,key)),key
    for key in ('classes','metadata','scripts'):
        assert p.freeze(getattr(a,key)[:len(getattr(old,key))])==p.freeze(getattr(old,key)),key
    for ci,(before,after) in enumerate(zip(old.instances,a.instances)):
        assert p.freeze(before[:6])==p.freeze(after[:6]),ci
        expected=[t for t in before[6] if not (t.kind in (1,2,3) and t.data[2] in old_mids)]
        assert p.freeze(expected)==p.freeze(after[6]),ci
    for before,after in zip(old.bodies,a.bodies):
        if before[0] not in changed:assert p.freeze(before)==p.freeze(after),('unrelated body changed',before[0])
        else:assert p.freeze(before[7])==p.freeze(after[7]),('activation changed',before[0])
    for b in a.bodies:
        if b[0] in orphan_ids:continue
        for x in p.asm.decode(b[5]):
            assert not (x.op in p.MULTINAME_OPS and x.args[0] in old_qnames),('old helper QName remains',b[0])
            assert not (x.op in (0x40,0x44) and x.args[0] in old_mids),('old helper MID remains',b[0])
    selected=sorted(changed|set(extras)|set(lifecycle)|{r['new_mid'] for r in records}|set(closure_map.values()))
    newids=list(range(len(old.methods),len(a.methods)))
    fresh_view=view(a)
    compile_rows=[dict(method_id=mid,strategy='replace',label=fresh_view.labels.get(mid,f'method:{mid}'),
        body_changed=mid in all_rewritten or mid in newids) for mid in selected]
    return dict(status='prepared_requires_aot_compile_link_and_device_validation',helper_class=HELPER_OWNER,
        old_method_count=len(old.methods),total_method_count=len(a.methods),helper_class_index=helper_ci,
        helper_class_multiname=helper_owner,lifecycle_methods=lifecycle,helpers=records,closures=closure_records,
        scope_evidence=scope_evidence,orphan_method_ids=sorted(orphan_ids),
        callers=callers,additional_recompile_ids=extras,
        compile_method_ids=selected,changed_existing_method_ids=sorted(changed),
        old_methods=len(old.methods),total_methods=len(a.methods),methods=compile_rows,
        new_method_ids=newids,compiled_helpers=newids,permitted_native_entry_aliases={},
        removed_instance_trait_method_ids=sorted(old_mids),old_method_info_and_pool_prefix_preserved=True,
        old_fields_static_traits_activation_scripts_preserved=True,remaining_live_old_helper_references=0,
        native_compiled=False,native_linked=False,device_tested=False)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,required=True)
    ap.add_argument('--expect-sha256',required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--method',type=int,action='append')
    ap.add_argument('--additional-recompile-ids',type=Path,
        help='JSON integer list; caller closure selected by independent dispatch audit')
    ap.add_argument('--body-availability-report',type=Path,
        help='Independent prior-compiler body audit; exact tiny_code admits reviewed constant/cinit bodies')
    args=ap.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
    import common
    job=common.bounded_job(180)
    raw=args.input.read_bytes();assert sha(raw)==args.expect_sha256,'input identity mismatch'
    assert not args.output.exists(),'fresh output directory required'
    a=p.abcfmt.ABC(raw);assert a.serialize()==raw,'input parser roundtrip differs'
    extras=json.loads(args.additional_recompile_ids.read_text('utf-8-sig')) if args.additional_recompile_ids else []
    assert isinstance(extras,list) and all(isinstance(n,int) for n in extras),'expected JSON integer list'
    reviewed=[];body_review=None
    if args.body_availability_report:
        receipt_raw=args.body_availability_report.read_bytes()
        receipt=json.loads(receipt_raw.decode('utf-8-sig'))
        assert not receipt['missing'] and not receipt['code_differences_from_exact_previous_compiler_inputs']
        by_mid={b[0]:b for b in a.bodies}
        for row in receipt['tiny_bodies']:
            assert row['current_code_exact_previous_compiler_input'] and row['compiler_source_body_available']
            assert bytes.fromhex(row['tiny_code'])==by_mid[row['method']][5],('reviewed tiny code drift',row['method'])
            reviewed.append(row['method'])
        body_review=dict(path=str(args.body_availability_report.resolve()),sha256=sha(receipt_raw),
            admitted_tiny_method_ids=sorted(reviewed))
    report=prepare(a,args.method or DEFAULT_METHODS,extras,reviewed)
    result=a.serialize();assert p.abcfmt.ABC(result).serialize()==result,'result parser roundtrip differs'
    args.output.mkdir(parents=True);(args.output/'full.abc').write_bytes(result)
    report.update(input=str(args.input.resolve()),input_sha256=sha(raw),full_abc_file='full.abc',
        base_full_abc_sha256=sha(raw),full_abc_sha256=sha(result),full_abc_sha1=hashlib.sha1(result).hexdigest(),
        baseline_native_file=str(args.input.with_name('worldflipper').resolve()),
        baseline_swf_file=str(args.input.with_name('main.swf').resolve()),
        relocation_manifest='relocation.json',body_availability_review=body_review,bounded_job=job)
    save(args.output/'relocation.json',report);save(args.output/'port.json',report)
    save(args.output/'compile-methods.json',report['compile_method_ids'])
    print(json.dumps(dict(status=report['status'],output=str(args.output),moved_helpers=len(report['helpers']),
        caller_methods=len(report['callers']),calls=sum(len(r['calls']) for r in report['callers']),
        compile_methods=len(report['compile_method_ids']),total_methods=report['total_method_count'])))

if __name__=='__main__':main()
