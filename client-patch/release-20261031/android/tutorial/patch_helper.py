"""Reorder the two existing date guards; preserve every other ABC record."""
from pathlib import Path
import argparse, copy, json, struct, sys, zlib
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
import bootstrap
from input_config import repo_path,work_path
sys.path.insert(0,str(repo_path('client-patch/content-operations')))
import build_bridge as bridge
LABEL='cn.content::ContentOperationsState$/gachaDateText|1'
OLD_CODE_SHA='ca6dcbc09ef373c00e59b27ac72455e87ee07d98dfc4e8170ad059ccc4164f80'

def patch_abc(raw):
    abc=bridge.p.abcfmt.ABC(raw)
    assert bridge.sc.serialize(abc,raw)==raw, 'ABC must roundtrip exactly'
    view=bridge.view(abc); bi,=view.by_label[LABEL]; old=copy.deepcopy(abc.bodies[bi])
    assert bridge.sha(old[5])==OLD_CODE_SHA, 'pinned gachaDateText body changed'
    assert not old[6], 'no exception records may be reordered'
    instructions=bridge.p.asm.decode(old[5]); rows=view.normalized(bi)[0]
    assert len(instructions)==len(rows)
    assert [x.op for x in instructions[7:20]]==[0x5d,0xd2,0x46,0x11,0x27,0x48,0x09,0xd2,0x46,0x11,0x27,0x48,0x09]
    assert 'gachaSharedDates' in str(rows[7]) and 'gachaSharedDates' in str(rows[9])
    assert 'get_showPeriod' in str(rows[15]) and instructions[10].target==13 and instructions[16].target==19
    order=list(range(7))+list(range(14,20))+list(range(7,14))+list(range(20,len(instructions)))
    remap={old_index:new_index for new_index,old_index in enumerate(order)}
    result=[copy.deepcopy(instructions[i]) for i in order]
    for instruction in result:
        if instruction.target is not None: instruction.target=remap[instruction.target]
        assert instruction.cases is None, 'unexpected switch'
    abc.bodies[bi][5]=bridge.p.asm.encode(result)[0]
    bridge.p.check_body(abc.bodies[bi],abc)
    # Reverse the exact instruction permutation and branches, independently.
    reversed_rows=[copy.deepcopy(result[remap[i]]) for i in range(len(order))]
    inverse={v:k for k,v in remap.items()}
    for instruction in reversed_rows:
        if instruction.target is not None: instruction.target=inverse[instruction.target]
    assert bridge.p.asm.encode(reversed_rows)[0]==old[5]
    output=bridge.sc.serialize(abc,raw)
    final=bridge.p.abcfmt.ABC(output)
    after=copy.deepcopy(final.bodies[bi]); final.bodies[bi]=old
    assert bridge.sc.serialize(final,raw)==raw, 'only target method body may change'
    return output,{'label':LABEL,'bodyIndex':bi,'methodInfo':old[0],
        'beforeCodeSha256':bridge.sha(old[5]),'afterCodeSha256':bridge.sha(after[5]),
        'beforeAbcSha256':bridge.sha(raw),'afterAbcSha256':bridge.sha(output),
        'headerUnchanged':old[:5]==after[:5], 'reversibleGuardPermutation':True,
        'onlyTargetBodyChanged':True,'poolsTraitsSignaturesOtherBodiesExact':True}

def patch_swf(source,dest):
    assert not dest.exists() and dest.is_relative_to(work_path()), 'fresh task-local destination required'
    assert bridge.sha(source.read_bytes())=='3c56f08c8b30ae75ae71908a699e703764dcfca0bc64d1fb91d866e2c61bfaef'
    _,version,_,raw=bridge.swftags.load_swf(str(source))
    changes=[]; replacements=[]
    for code,at,header,size in bridge.swftags.iter_tags(raw):
        if code!=82: continue
        data=raw[at+header:at+header+size]; end=data.index(b'\0',4)+1
        if data[4:end-1]!=b'content_operations':continue
        replacement,proof=patch_abc(data[end:]); payload=data[:end]+replacement
        replacements.append((at,at+header+size,struct.pack('<HI',(82<<6)|63,len(payload))+payload))
        changes.append(proof)
    assert len(replacements)==1
    at,end,replacement=replacements[0]
    payload=raw[:at]+replacement+raw[end:]
    result=b'CWS'+bytes([version])+struct.pack('<I',len(payload)+8)+zlib.compress(payload)
    dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(result)
    _,_,_,read=bridge.swftags.load_swf(str(dest))
    assert read==payload and read[:at]==raw[:at] and read[at+len(replacement):]==raw[end:]
    proof={'input':str(source),'inputSha256':bridge.sha(source.read_bytes()),'output':str(dest),
        'outputSha256':bridge.sha(result),'changes':changes,'allOtherSwfBytesExact':True,
        'gameMainAbcUnchanged':True,'admissionUnchanged':True,'bundleUnchanged':True,
        'saveSchemaAndIdentifiersUnchanged':True,'runtimeVerified':False}
    dest.with_suffix('.json').write_text(json.dumps(proof,indent=2)+'\n','utf-8')
    return proof

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(patch_swf(a.input.resolve(),a.output.resolve())))
