"""Compile only the new dual-form prefix; the retained iOS stock native draws."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
import copy

def build(p,abc,imported):
    instructions=p.asm.decode(imported[5]);stop=111
    assert not imported[6] and not imported[7]
    assert instructions[stop].op==0x5e and abc.mn_name(instructions[stop].args[0])=='member'
    assert instructions[113].op==0x46 and abc.mn_name(instructions[113].args[0]).endswith('::canDisplay')
    assert [x.op for x in instructions[38:44]]==[0xd0,0xd0,0x66,0x46,0x66,0x46]
    assert abc.mn_name(instructions[43].args[0])=='wfxDualFormUid'
    prefix=copy.deepcopy(instructions[:stop])+[p.asm.Instruction(9),p.asm.Instruction(0x47)]
    for ins in prefix:
        assert ins.cases is None
        if ins.target is not None:assert 0<=ins.target<=stop
    body=copy.deepcopy(imported);body[5]=p.asm.encode(prefix)[0]
    # Each guard consumes only the newly checked null value and any receiver
    # retained underneath it by this specific call expression.
    guard_specs=[(41,2,'member'),(42,2,'member.getCharacter'),(74,1,'character'),(80,1,'asset'),
                 (83,1,'asset.getAnimation result'),(99,1,'characterLayer before removeChild'),
                 (108,1,'characterLayer before addChild')]
    guards=[]
    for at,pops,name in reversed(guard_specs):
        before=p.asm.decode(body[5])
        if at==41:assert before[at-1].op==0x66 and abc.mn_name(before[at-1].args[0])=='member'
        elif at==42:assert before[at-1].op==0x46 and abc.mn_name(before[at-1].args[0]).endswith('::getCharacter')
        elif at==83:assert before[at-2].op==0x46 and abc.mn_name(before[at-2].args[0])=='getAnimation'
        else:assert before[at-1].op==0x66 and abc.mn_name(before[at-1].args[0])==('characterLayer' if at in (99,108) else name)
        block=[p.asm.Instruction(0x2a),p.asm.Instruction(0x11,target=2+pops+1)]
        block += [p.asm.Instruction(0x29) for _ in range(pops)]+[p.asm.Instruction(0x47),p.asm.Instruction(9)]
        # The iftrue target is the physical label following the early return.
        assert block[1].target==len(block)-1
        body[5],body[6],_=p.asm.splice(body,at,block,p.asm.ENTER)
        guards.append(dict(insertion_at=at,nullable=name,popped_values=pops))
    body[1]=max(body[1],8)
    check=p.check_body(body,abc)
    return body,dict(strategy='dual_form_prefix_only_with_null_returns_then_native_stock_draw',
        source_prefix_instruction_count=stop,guards=list(reversed(guards)),checks=check,
        stock_body_not_recompiled=True,original_method_info_required=66181)
