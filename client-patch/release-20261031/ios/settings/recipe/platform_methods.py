"""Keep current iOS equipment typed dispatch and constant-cast lowering."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
import copy,importlib.util
from pathlib import Path

def constant_casts(body,abc,p):
    source=Path(cfg.repo('client-patch/ios-cumulative-login/prepare.py'))
    spec=importlib.util.spec_from_file_location('release_ios_cast_lowering',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.lower_constant_casts(body,abc)

def adapt(body,abc,p):
    result=copy.deepcopy(body);original=result[5];rules=[]
    def q(name):
        hits=[i for i,m in enumerate(abc.multinames) if m[0]==7 and abc.mn_name(i)==name]
        assert hits,('platform rule QName missing',name)
        assert len({p.freeze(abc.multinames[i]) for i in hits})==1
        return hits[0]
    instructions=p.asm.decode(result[5])
    calls=[i for i,x in enumerate(instructions) if x.op==0x46 and abc.mn_name(x.args[0])=='wfEquipmentRule']
    for index in reversed(calls):
        instructions=p.asm.decode(result[5]);call=instructions[index];assert call.args[1]==3
        needed=4;start=None
        for at in range(index-1,-1,-1):
            ins=instructions[at]
            assert ins.target is None and ins.cases is None and ins.op not in (0x2a,0x2b),'equipment receiver expression needs explicit control-flow adapter'
            pop,push=p.asm._effect(ins,abc.multinames);needed+=pop-push
            if needed==0:start=at;break
        assert start is not None and instructions[start].op==0xd0,'equipment hook must pass its original receiver explicitly'
        before=result[5];old_args=list(call.args)
        block=p.asm.assemble([('getlex',q('cn.mod::AuthorState'))])
        code,exceptions,ins=p.asm.splice(result,start,block,p.asm.ENTER)
        ins[index+1].args=[q('cn.mod::authorEquipmentRule'),4]
        result[5]=p.asm.encode(ins)[0];result[6]=exceptions;result[1]+=1
        # Reverse both edits independently to retain the complete input body.
        ins[index+1].args=old_args
        assert p.asm.unsplice(p.asm.encode(ins)[0],start,1)==before
        rules.append(dict(call_index=index,receiver_start=start,strategy='existing iOS AuthorState.authorEquipmentRule with explicit receiver and four arguments',reversible=True))
    cast_proof=constant_casts(result,abc,p)
    return result,dict(equipment_dispatch=rules,constant_casts=cast_proof,changed=result[5]!=original)
