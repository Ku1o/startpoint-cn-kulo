"""Map an explicitly frozen, selected Android donor to the verified iOS prefix.

Contract: {donor_swf, donor_swf_sha256, methods:[{label,action?,feature?}]}.
action defaults to apply; skip/exclude entries are retained but never mapped.
No ABC/native/package is modified. MethodInfo IDs and body indices stay separate.
"""
from __future__ import annotations
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import types
from collections import deque

SOURCE = Path(str(cfg.REPO))
sys.path.insert(0, str(SOURCE / 'client-patch/lens0907-0908'))
import build_swf as p

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(label):
    owner,sep,tail = label.partition('/')
    return owner.replace('::','.')+sep+tail

def signature(v, mid):
    ret, params, name, flags, options, names = v.a.methods[mid]
    pools = {1:'strings',3:'ints',4:'uints',6:'doubles'}
    def value(index, kind):
        if kind in pools:
            result = getattr(v.a,pools[kind])[index]
            return kind,result.hex() if isinstance(result,bytes) else result
        if kind in (5,8,22,23,24,25,26):
            return kind,v.ns(index)
        return kind,index
    return dict(return_type=v.mn(ret), parameters=[v.mn(x) for x in params],flags=flags,
                optional=[value(x,k) for x,k in options] if options is not None else None)

def index(v):
    rows = {}
    for label,indices in v.by_label.items():
        key = canonical(label)
        if key in rows or len(indices)!=1:
            raise ValueError('ambiguous normalized method label: '+key)
        rows[key] = indices[0]
    return rows

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    contract=json.loads(args.contract.read_text(encoding='utf-8-sig'))
    donor=Path(contract['donor_swf'])
    assert sha(donor.read_bytes())==contract['donor_swf_sha256'],'donor identity differs from frozen contract'
    full=Path(cfg.path('outputs_ios_r11_cumulative_compact_20261025_ios_full_equipment_r11_compact_20261025_abc')).read_bytes()
    assert sha(full)=='ff1ac16421ed0d394b70612aed23584e30c0aa9ec1de0eebe4336cc1cb396388'
    target=p.View(types.SimpleNamespace(abc=p.abcfmt.ABC(full)),p.asm)
    source=p.View(p.SwfAbc(donor),p.asm)
    ti,si=index(target),index(source)
    rows=[];pending=deque();selected=set();skipped=[]
    for item in contract['methods']:
        item={'label':item} if isinstance(item,str) else item
        if item.get('action','apply') in ('skip','exclude'):
            skipped.append(item);continue
        label=canonical(item['label'])
        assert label in si,('selected donor method missing',label)
        pending.append((label,item.get('feature'),False))
    while pending:
        label,feature,closure=pending.popleft()
        if label in selected:continue
        selected.add(label)
        sb=source.a.bodies[si[label]]; sm=sb[0]
        hit=ti.get(label)
        row=dict(label=label,feature=feature,is_closure=closure,
            donor_body_index=si[label],donor_method_id=sm,donor_code_sha256=sha(sb[5]),
            donor_signature=signature(source,sm),donor_activation_traits=p.freeze(sb[7]),
            strategy='append_method' if hit is None else 'replace_existing_body')
        if hit is not None:
            tb=target.a.bodies[hit];tm=tb[0]
            row.update(ios_body_index=hit,ios_method_id=tm,ios_code_sha256=sha(tb[5]),
                ios_signature=signature(target,tm),signature_equal=signature(target,tm)==signature(source,sm),
                ios_activation_traits=p.freeze(tb[7]),activation_shape_requires_review=bool(tb[7] or sb[7]))
        for instruction in p.asm.decode(sb[5]):
            if instruction.op not in (0x40,0x44):continue
            child=instruction.args[0]
            child_label=canonical(source.labels.get(child,f'UNMAPPED:{child}'))
            assert child_label in si,('closure/callstatic has no body mapping',label,child,child_label)
            pending.append((child_label,feature,True))
        rows.append(row)
    owners={r['label'].split('/')[0].rstrip('$') for r in rows}
    layouts=[]
    def class_slots(v):
        result={}
        for instance,cls in zip(v.a.instances,v.a.classes):
            qname=canonical(v.a.mn_name(instance[0]))
            slots=lambda traits:[dict(name=v.mn(t.name),kind=t.kind,slot=t.data[1],type=v.mn(t.data[2])) for t in traits if t.kind in (0,6)]
            result[qname]=dict(instance=slots(instance[6]),static=slots(cls[1]))
        return result
    before,after=class_slots(target),class_slots(source)
    for owner in sorted(owners):
        if owner not in after:continue
        if owner not in before:
            layouts.append(dict(owner=owner,strategy='new_class',donor=after[owner]));continue
        changed={side:dict(ios=before[owner][side],donor=after[owner][side]) for side in ('instance','static') if before[owner][side]!=after[owner][side]}
        if changed:layouts.append(dict(owner=owner,strategy='existing_class_layout_diff_requires_adapter',differences=changed))
    result=dict(status='mapping_ready_requires_import_compile_link_validation',
        contract=str(args.contract.resolve()),contract_sha256=sha(args.contract.read_bytes()),
        donor_swf=str(donor.resolve()),donor_swf_sha256=contract['donor_swf_sha256'],
        ios_full_sha256=sha(full),ios_old_methods=101598,methods=rows,excluded=skipped,
        class_layout_differences=layouts,body_index_is_not_method_id=True,
        signature_failures=[r['label'] for r in rows if r.get('signature_equal') is False],
        native_linked=False,native_executed=False,device_tested=False,registry_changed=False)
    assert not args.output.exists(),'refuse to overwrite mapping report'
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],selected=len(rows),appended=sum(r['strategy']=='append_method' for r in rows),layout_differences=len(layouts),signature_failures=len(result['signature_failures']))))

if __name__=='__main__':main()
