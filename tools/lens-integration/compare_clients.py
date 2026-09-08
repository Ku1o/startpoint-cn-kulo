"""Compare named AVM2 methods after resolving pools and anonymous method references.

Read-only analysis; --parser points to the reviewed donor's pure ABC parsers.
No donor patch/build/install entry point is run.
"""
import argparse
import hashlib
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

MULTINAME_OPS = {0x04,0x05,0x45,0x46,0x4a,0x4c,0x4e,0x4f,0x59,0x5b,0x5c,0x5d,0x5e,0x5f,0x60,0x61,0x66,0x68,0x6a,0x80,0x86,0xb2}

def labels(abc, opwalk):
    names = {}
    def traits(rows, owner):
        for t in rows:
            if t.data[0] in ('method','function'):
                name = f'{owner}/{abc.mn_name(t.name)}|{t.kind}'
                names[t.data[2]] = name
    for i, instance in enumerate(abc.instances):
        owner = abc.mn_name(instance[0])
        names[instance[5]] = owner + '/<ctor>'
        names[abc.classes[i][0]] = owner + '$/<cinit>'
        traits(instance[6], owner)
        traits(abc.classes[i][1], owner + '$')
    for i, script in enumerate(abc.scripts):
        owner = 'script:' + ','.join(abc.mn_name(t.name) for t in script[1])
        names.setdefault(script[0], owner + '/<init>')
        traits(script[1], owner)
    body_of = {b[0]: b for b in abc.bodies}
    queue = deque(names)
    visited = set()
    while queue:
        method = queue.popleft()
        if method in visited: continue
        visited.add(method)
        body = body_of.get(method)
        if body is None: continue
        ordinal = 0
        for op, args in opwalk.walk(body[5]):
            if op not in (0x40,0x44): continue
            child = args[0]
            if child not in names:
                names[child] = names[method] + f'/closure:{ordinal}'
                queue.append(child)
            ordinal += 1
        traits(body[7], names[method] + '/activation')
    return names

class View:
    def __init__(self, swf, asm):
        self.swf, self.a, self.asm = swf, swf.abc, asm
        self.labels = labels(self.a, asm.opwalk)
        self.by_label = defaultdict(list)
        for i,b in enumerate(self.a.bodies): self.by_label[self.labels.get(b[0], f'UNMAPPED:{b[0]}')].append(i)
        self.ns_cache = {}; self.mn_cache = {}
    def ns(self, i):
        if i not in self.ns_cache:
            k,s = self.a.namespaces[i]
            self.ns_cache[i] = (k,self.a.strings[s].decode('utf8','replace'))
        return self.ns_cache[i]
    def mn(self, i):
        if i in self.mn_cache: return self.mn_cache[i]
        m = self.a.multinames[i]; k = m[0]
        if k == 0: v = ('any',)
        elif k in (7,13): v = (k,self.ns(m[1]),self.a.strings[m[2]].decode('utf8','replace'))
        elif k in (9,14): v = (k,self.a.strings[m[1]].decode('utf8','replace'),tuple(self.ns(n) for n in self.a.ns_sets[m[2]]))
        elif k in (15,16): v = (k,self.a.strings[m[1]].decode('utf8','replace'))
        elif k in (17,18): v = (k,)
        elif k in (27,28): v = (k,tuple(self.ns(n) for n in self.a.ns_sets[m[1]]))
        elif k == 29: v = (k,self.mn(m[1]),tuple(self.mn(n) for n in m[2]))
        else: raise ValueError(m)
        self.mn_cache[i]=v
        return v
    def normalized(self, i):
        b = self.a.bodies[i]
        instructions = self.asm.decode(b[5])
        encoded, offsets = self.asm.encode(instructions)
        assert encoded == b[5], 'noncanonical instruction encoding'
        end = len(b[5])
        idx = {off:n for n,off in enumerate(offsets)};idx[end]=len(instructions)
        result = []
        for ins in instructions:
            args = list(ins.args);op=ins.op
            if op in MULTINAME_OPS: args[0]=self.mn(args[0])
            elif op in (0x2c,0x06,0xf1): args[0]=('string',self.a.strings[args[0]].decode('utf8','replace'))
            elif op in (0x2d,0x2e,0x2f): args[0]=(op,getattr(self.a,{0x2d:'ints',0x2e:'uints',0x2f:'doubles'}[op])[args[0]])
            elif op == 0x31: args[0]=self.ns(args[0])
            elif op in (0x40,0x44): args[0]=self.labels.get(args[0],f'UNMAPPED:{args[0]}')
            elif op == 0x58: args[0]=self.mn(self.a.instances[args[0]][0])
            elif op == 0xef: args[1]=self.a.strings[args[1]].decode('utf8','replace')
            result.append((op,args,ins.target,ins.default,ins.cases))
        exceptions=[(idx[e[0]],idx[e[1]],idx[e[2]],self.mn(e[3]),self.mn(e[4])) for e in b[6]]
        return result,exceptions

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--parser',type=Path,required=True);ap.add_argument('--accepted',type=Path,required=True);ap.add_argument('--donor',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    sys.path.insert(0,str(args.parser/'abcasm'))
    import asm
    from swfabc import SwfAbc
    av,bv=[View(SwfAbc(p),asm) for p in (args.accepted,args.donor)]
    changed=[];errors=[];new=[]
    for label, bi in bv.by_label.items():
        ai=av.by_label.get(label,[])
        if not ai: new.append({'label':label,'body':bi});continue
        if len(ai)!=1 or len(bi)!=1: errors.append({'label':label,'ambiguous':[ai,bi]});continue
        a,b=ai[0],bi[0]
        try:
            if av.normalized(a) == bv.normalized(b): continue
            changed.append({'label':label,'accepted_body':a,'donor_body':b,'accepted_method':av.a.bodies[a][0],'donor_method':bv.a.bodies[b][0],
                'accepted_bytes':len(av.a.bodies[a][5]),'donor_bytes':len(bv.a.bodies[b][5])})
        except Exception as e:errors.append({'label':label,'error':str(e)})
    report={'accepted_sha256':hashlib.sha256(args.accepted.read_bytes()).hexdigest(),'donor_sha256':hashlib.sha256(args.donor.read_bytes()).hexdigest(),
        'semantic_differences':changed,'new_methods':new,'errors':errors}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps({'semantic_differences':len(changed),'new_methods':len(new),'errors':len(errors)}))
    for row in changed:print(row['label'],row['accepted_bytes'],row['donor_bytes'])

if __name__=='__main__':main()
