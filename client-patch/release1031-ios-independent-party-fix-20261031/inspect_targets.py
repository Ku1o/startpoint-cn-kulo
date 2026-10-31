"""Read the bounded method subset needed to construct the real-body fixture."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import json,types
import common as c
def main():
    c.bounded_job();p=c.framework();raw=c.ABC.read_bytes();c.require(c.sha(raw)==c.ABC_SHA,'Full ABC input changed')
    a=p.abcfmt.ABC(raw);v=p.View(types.SimpleNamespace(abc=a),p.asm);result=[]
    wanted=set(c.TARGETS)|{101300,101301,101302}
    for i,body in enumerate(a.bodies):
        if body[0] not in wanted:continue
        owners=[]
        for ci,(inst,cls) in enumerate(zip(a.instances,a.classes)):
            if inst[5]==body[0] or any(t.kind in (1,2,3) and t.data[2]==body[0] for t in inst[6]+cls[1]):
                owners.append(dict(class_index=ci,name=a.mn_name(inst[0]),base=a.mn_name(inst[1]),
                    fields=[(a.mn_name(t.name),a.mn_name(t.data[2])) for t in inst[6] if t.kind in (0,6)]))
        result.append(dict(method=body[0],owners=owners,signature=str(a.methods[body[0]]),normalized=v.normalized(i)))
    c.dump(c.TASK/'inspection01.json',result);print(json.dumps(result,default=str,ensure_ascii=False))
if __name__=='__main__':main()
