"""Restore lexical initializers only for compiler reachability; never link them."""
from release_common import *
import copy

def add_context(full, methods):
    abc = abcfmt.ABC(full); before = copy.deepcopy(abc); target = view(abc)
    donors = [view(t[3]) for t in s.parts(PREP/'abyss-ex-android.swf')[2] if t[0]==82]
    records = []
    labels = ['script:'+owner+'/<init>' for owner in dict.fromkeys(row['label'].split('/')[0].rstrip('$') for row in methods)]
    labels.append('cn.ui::AbyssDetails$/<cinit>')
    for label in labels:
        donor, = [v for v in donors if label in v.by_label]
        si, = donor.by_label[label]; ti, = target.by_label[label]
        old = abc.bodies[ti]
        body = p.Importer(target,donor).body(si,old[0],scope=old[3])
        assert p.activation_traits(target,old)==p.activation_traits(target,body)
        abc.bodies[ti]=body
        records.append(dict(label=label,method_id=old[0],body_index=ti))
    ids={r['method_id'] for r in records}
    for old,new in zip(before.bodies,abc.bodies):
        if old[0] not in ids: assert freeze(old)==freeze(new)
    for field in ('methods','metadata','instances','classes','scripts'):
        assert freeze(getattr(before,field))==freeze(getattr(abc,field))
    return abc.serialize(),records

if __name__=='__main__':
    port=read(WORK/'port.json')
    path=WORK/port['full_abc_file'];raw=path.read_bytes()
    assert sha(raw)==port['full_abc_sha256']
    raw,_=replace_abc((PREP/'abyss-ex-ios-full.abc').read_bytes(),'ios')
    full,records=add_context(raw,port['methods'])
    path.write_bytes(full)
    port.update(full_abc_sha256=sha(full),full_abc_sha1=hashlib.sha1(full).hexdigest(),compiler_only_lifecycles=records)
    dump(WORK/'port.json',port)
    print('Restored compiler context for',len(records),'owners; runtime initializers remain unchanged.')
