"""ABI-safe storage adapter for new static mutable slots.

Storage lives only in a new class. Existing classes receive getter/setter method
traits with the original QName. The old instance/static slot lists stay exact.
This module is a preparation component, not an AOT/runtime acceptance result.
"""
from __future__ import annotations
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
import copy, importlib.util, json, re
from pathlib import Path

STATE = 'cn.release::ReleaseState20261031'

def definitions(base, donor):
    old={base.a.mn_name(r[0]):(r,c) for r,c in zip(base.a.instances,base.a.classes)}
    rows=[]
    for inst,cls in zip(donor.a.instances,donor.a.classes):
        owner=donor.a.mn_name(inst[0])
        if owner not in old:
            continue
        bi,bc=old[owner]
        for static,traits,original in ((False,inst[6],bi[6]),(True,cls[1],bc[1])):
            original_names={(base.mn(t.name),t.kind) for t in original}
            for trait in traits:
                if trait.kind not in (0,6) or (donor.mn(trait.name),trait.kind) in original_names:
                    continue
                if not static:
                    raise ValueError('new instance storage needs a separate adapter: '+owner+'/'+donor.mn(trait.name))
                if trait.kind!=0 or trait.attr or trait.metadata:
                    raise ValueError('only plain mutable static slots are supported')
                if trait.data[3]!=0 or trait.data[4] is not None:
                    raise ValueError('explicit constant default requires a reviewed initializer adapter')
                mn=donor.a.multinames[trait.name]
                if mn[0]!=7 or donor.a.namespaces[mn[1]][0] not in (0x16,0x08):
                    raise ValueError('non-public slot namespace requires identity mapping')
                name=donor.a.s(mn[2])
                rows.append(dict(owner=owner,name=name,qname=donor.a.mn_name(trait.name),
                                 namespace_semantics=donor.mn(trait.name),
                                 source_multiname=trait.name,type=donor.a.mn_name(trait.data[2]),
                                 source_type=trait.data[2],static=True,default='AVM2 type default'))
    rows.sort(key=lambda r:(r['owner'],r['qname']))
    for index,row in enumerate(rows):row['sidecar_field']=f's{index:04d}'
    return rows

def audit_accesses(p, donor, rows, method_ids):
    by_mn={r['source_multiname']:r for r in rows}
    names={r['name'] for r in rows}
    found=[]
    for body in donor.a.bodies:
        if body[0] not in method_ids:continue
        label=donor.labels.get(body[0],f'method:{body[0]}')
        for at,ins in enumerate(p.asm.decode(body[5])):
            if ins.op in (0x66,0x61) and ins.args[0] in by_mn:
                found.append(dict(method=body[0],label=label,instruction=at,
                                  operation=ins.name,slot=by_mn[ins.args[0]]['qname']))
            elif ins.op in (0x68,0x6a,0x04,0x05) and ins.args[0] in by_mn:
                raise ValueError(f'{label}: initializer/delete/super access to new storage needs separate review')
            elif ins.op==0x2c and donor.a.s(ins.args[0]) in names:
                raise ValueError(f'{label}: dynamic/reflection string references a new storage name')
    return found

def source_text(rows):
    fields=[]
    imports=set()
    short_types={}
    for row in rows:
        t=row['type'].replace('::','.')
        if not re.fullmatch(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*|\*',t):
            raise ValueError('unsupported AS3 storage type: '+t)
        short=t.rsplit('.',1)[-1]
        if short in short_types and short_types[short]!=t:
            raise ValueError('colliding imported storage type names require separate sidecars')
        short_types[short]=t
        if '.' in t:imports.add(t)
        fields.append(f'        public static var {row["sidecar_field"]}:{short};')
    return ('package cn.release {\n'+''.join(f'    import {t};\n' for t in sorted(imports))+
            '    public final class ReleaseState20261031 {\n'+
            '\n'.join(fields)+'\n    }\n}\n')

def import_sidecar(p,target,helper,source_root):
    path=Path(source_root)/'client-patch/ios-cumulative-login/prepare.py'
    spec=importlib.util.spec_from_file_location('release31_class_importer',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    start=len(target.a.methods)
    merger=module.ClassImporter(target,helper)
    merger.merge()
    return list(range(start,len(target.a.methods)))

def install_accessors(p,target,donor,importer,rows):
    a=target.a
    owners={a.mn_name(r[0]):i for i,r in enumerate(a.instances)}
    state_indices=[i for i,r in enumerate(a.instances) if a.mn_name(r[0])==STATE]
    if len(state_indices)!=1:raise ValueError('exactly one imported storage class required')
    sci=state_indices[0]
    state_mn=a.instances[sci][0]
    sidecar={a.mn_name(t.name):t for t in a.classes[sci][1] if t.kind==0}
    voids=[i for i in range(1,len(a.multinames)) if a.mn_name(i)=='void' and a.multinames[i][0]==7]
    if len(voids)!=1:raise ValueError('ambiguous void type')
    records=[]
    for row in rows:
        ci=owners[row['owner']]
        trait_name=importer.pool('multinames',row['source_multiname'])
        if any(t.name==trait_name for t in a.classes[ci][1]):
            raise ValueError('existing static property conflicts with storage proxy')
        field=sidecar[row['sidecar_field']]
        field_type=importer.pool('multinames',row['source_type'])
        if field.data[2]!=field_type:raise ValueError('sidecar slot type mismatch')
        pair=[]
        for kind,returns,params,code,locals_ in [
            (2,field_type,[],[('getlocal_0',),('pushscope',),('getlex',state_mn),('getproperty',field.name),('returnvalue',)],1),
            (3,voids[0],[field_type],[('getlocal_0',),('pushscope',),('getlex',state_mn),('getlocal_1',),('setproperty',field.name),('returnvoid',)],2)
        ]:
            mid=len(a.methods)
            a.methods.append([returns,params,0,0,None,None])
            raw,_=p.asm.encode(p.asm.assemble(code))
            body=[mid,2,locals_,1,2,raw,[],[]]
            proof=p.check_body(body,a)
            a.bodies.append(body)
            trait=p.abcfmt.Trait();trait.name=trait_name;trait.kind=kind;trait.attr=0
            trait.data=['method',0,mid];trait.metadata=[]
            a.classes[ci][1].append(trait)
            pair.append(dict(method_id=mid,kind='getter' if kind==2 else 'setter',checks=proof))
        records.append(dict(**row,accessors=pair,sidecar_owner=STATE))
    return records
