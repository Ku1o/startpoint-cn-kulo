"""Narrow, read-only helper-body/callsite inventory for dispatch repair."""
from __future__ import annotations
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse, json, sys, types
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'lens0907-0908'))
import build_swf as p
from relocate_helpers import DEFAULT_METHODS

DEFAULT = DEFAULT_METHODS

def inventory(path, method_ids):
    a = p.abcfmt.ABC(Path(path).read_bytes())
    v = p.View(types.SimpleNamespace(abc=a), p.asm)
    by_mid = {b[0]: b for b in a.bodies}
    wanted = set(method_ids)
    names = {}
    result = {'path': str(path), 'method_count': len(a.methods), 'helpers': [], 'calls': []}
    for ci, inst in enumerate(a.instances):
        for tr in inst[6]:
            if tr.kind in (1, 2, 3) and tr.data[2] in wanted:
                mid = tr.data[2]
                mn = a.multinames[tr.name]
                name = a.s(mn[2]); names[name] = mid
                b = by_mid[mid]
                ins = p.asm.decode(b[5])
                result['helpers'].append(dict(mid=mid, owner=a.mn_name(inst[0]), ci=ci,
                    trait=p.freeze(tr), namespace=a.namespaces[mn[1]],
                    signature=a.methods[mid], header=b[:5], exceptions=b[6], activation=p.freeze(b[7]),
                    instructions=[dict(index=i, op=x.name, args=x.args, name=a.mn_name(x.args[0]) if x.op in p.MULTINAME_OPS else None,
                        target=x.target, cases=x.cases, default=x.default) for i,x in enumerate(ins)]))
    for b in a.bodies:
        for i,x in enumerate(p.asm.decode(b[5])):
            if x.op in p.MULTINAME_OPS:
                mn = a.multinames[x.args[0]]
                if mn[0] in (7,13): name = a.s(mn[2])
                elif mn[0] in (9,14,15,16): name = a.s(mn[1])
                else: continue
                if name not in names: continue
                result['calls'].append(dict(caller=b[0], label=v.labels.get(b[0]), index=i,
                    op=x.name, args=x.args, multiname=mn, helper=names[name], header=b[:5], activation=p.freeze(b[7])))
            elif x.op in (0x40,0x44) and x.args[0] in wanted:
                result['calls'].append(dict(caller=b[0], label=v.labels.get(b[0]), index=i,
                    op=x.name, args=x.args, helper=x.args[0], header=b[:5], activation=p.freeze(b[7])))
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--abc', required=True, type=Path)
    ap.add_argument('--method', action='append', type=int)
    ap.add_argument('--output', required=True, type=Path)
    args=ap.parse_args(); r=inventory(args.abc, args.method or DEFAULT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(r, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(output=str(args.output), helpers=[dict(mid=h['mid'], owner=h['owner'], code_instructions=len(h['instructions']),activation_slots=len(h['activation']),exceptions=len(h['exceptions'])) for h in r['helpers']], call_count=len(r['calls']),caller_count=len({c['caller'] for c in r['calls']})), ensure_ascii=False))

if __name__ == '__main__': main()
