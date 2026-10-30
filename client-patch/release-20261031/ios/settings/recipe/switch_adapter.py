"""Strict AIR signed32-switch proof for spilled selectors and a separate sum register."""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
import hashlib
import re
import struct
import capstone

def require(value,message):
    if not value:raise ValueError(message)

def reg(text):
    return 'x'+text[1:] if re.fullmatch('[wx][0-9]+',text) else text

def memory(operand,addresses):
    match=re.fullmatch(r'\[(x\d+|sp)(?:, #(-?0x[0-9a-f]+|-?\d+))?\]',operand)
    if not match:return None
    base,offset=match.groups();offset=int(offset or '0',0)
    origin=addresses.get(base)
    return (origin[0],origin[1]+offset) if origin else None

def bounded_dispatch(instructions,low,base,entries,code_size):
    """Forward local value provenance proves guard and loaded selector are identical."""
    def is_control(ins):
        return any(ins.group(group) for group in (capstone.CS_GRP_JUMP,capstone.CS_GRP_CALL,capstone.CS_GRP_RET,capstone.CS_GRP_INT,capstone.CS_GRP_IRET,capstone.CS_GRP_PRIVILEGE)) or ins.mnemonic in ('brk','hlt','udf','svc','hvc','smc','eret','drps')
    candidates=[]
    for index,load in enumerate(instructions):
        if load.address<=low or load.mnemonic!='ldrsw':continue
        match=re.fullmatch(rf'x(\d+), \[x{base}, x(\d+), lsl #2\]',load.op_str)
        if not match:continue
        dest,selector=map(int,match.groups())
        # Compiler scheduling may insert unrelated FP loads/moves between
        # LDRSW, integer ADD and BR. Only a short straight line that does not
        # overwrite either input/result is accepted.
        def writes_any(ins,registers):
            return any(reg(ins.reg_name(r)) in registers for r in ins.regs_access()[1])
        adds=[]
        for j,ins in enumerate(instructions[index+1:index+9],index+1):
            match=re.fullmatch(r'x(\d+), x(\d+), x(\d+)',ins.op_str)
            if ins.mnemonic=='add' and match and {int(match.group(2)),int(match.group(3))}=={dest,base}:adds.append((j,ins,int(match.group(1))))
        if not adds:continue
        add_index,add,result=adds[0]
        if any(writes_any(x,{f'x{dest}',f'x{base}'}) or is_control(x) for x in instructions[index+1:add_index]):continue
        branches=[(j,x) for j,x in enumerate(instructions[add_index+1:add_index+5],add_index+1) if x.mnemonic=='br' and x.op_str==f'x{result}']
        if not branches:continue
        branch_index,branch=branches[0]
        if any(writes_any(x,{f'x{result}'}) or is_control(x) for x in instructions[add_index+1:branch_index]):continue
        highs=[(i,x) for i,x in enumerate(instructions[max(0,index-16):index],max(0,index-16)) if x.mnemonic=='b.hi']
        if not highs:continue
        high_index,high=highs[-1]
        high_target=int(high.op_str.lstrip('#'),0)
        if not (branch.address+4<=high_target<code_size):continue
        guards=[]
        for i,x in enumerate(instructions[max(0,high_index-24):high_index],max(0,high_index-24)):
            match=re.fullmatch(r'w(\d+), w(\d+), #(0x[0-9a-f]+|\d+)',x.op_str)
            if x.mnemonic=='subs' and match and int(match.group(3),0)==entries-1:guards.append((i,x,int(match.group(2))))
            cmp=re.fullmatch(r'w(\d+), #(0x[0-9a-f]+|\d+)',x.op_str)
            if x.mnemonic=='cmp' and cmp and int(cmp.group(2),0)==entries-1:guards.append((i,x,int(cmp.group(1))))
        if not guards:continue
        guard_index,guard,guard_register=guards[-1]
        if any('nzcv' in [x.reg_name(r) for r in x.regs_access()[1]] for x in instructions[guard_index+1:branch_index]):continue
        if any(is_control(x) and x.address!=high.address for x in instructions[guard_index+1:index]):continue
        values={};slots={};addresses={'sp':('sp',0),'x29':('fp',0)};guard_value=None;selector_value=None
        start=max(0,guard_index-12)
        def value(r):
            key=reg(r)
            v=values.setdefault(key,(('initial',key),False))
            return (v[0],True) if r.startswith('w') else v
        for n in range(start,index+1):
            x=instructions[n];parts=x.op_str.split(', ',1)
            if n==guard_index:guard_value=value('w'+str(guard_register))
            if n==index:selector_value=value('x'+str(selector));break
            write={reg(x.reg_name(r)) for r in x.regs_access()[1]}
            if x.mnemonic in ('bl','blr'):
                write.update(f'x{r}' for r in range(19));slots.clear()
            assigned=None;address=None
            mov=re.fullmatch(r'([wx]\d+), ([wx]\d+)',x.op_str)
            mem=re.fullmatch(r'([wx]\d+), (\[.*\])',x.op_str)
            addr=re.fullmatch(r'(x\d+), (sp|x\d+), #(0x[0-9a-f]+|\d+)(?:, lsl #(12))?',x.op_str)
            if x.mnemonic=='mov' and mov:
                assigned=(reg(mov.group(1)),value(mov.group(2)))
                address=addresses.get(reg(mov.group(2)))
            elif x.mnemonic in ('ldr','ldur') and mem:
                key=memory(mem.group(2),addresses)
                v=slots.get(key,(('load',x.address),mem.group(1).startswith('w')))
                assigned=(reg(mem.group(1)),(v[0],True) if mem.group(1).startswith('w') else v)
            elif x.mnemonic in ('str','stur') and mem:
                key=memory(mem.group(2),addresses)
                if key is None:slots.clear()
                else:slots[key]=value(mem.group(1))
            elif x.mnemonic=='add' and addr and addr.group(2) in addresses:
                a=addresses[addr.group(2)];address=(a[0],a[1]+(int(addr.group(3),0) << int(addr.group(4) or '0')))
            elif x.mnemonic.startswith(('stp','stnp')):
                slots.clear()
            for r in write:
                values[r]=(('write',x.address,r),False);addresses.pop(r,None)
            if assigned:values[assigned[0]]=assigned[1]
            if address and parts[0].startswith('x'):addresses[parts[0]]=address
        if not guard_value or guard_value!=selector_value or not selector_value[1]:continue
        # The materialized table base must reach the load without writes.
        if any(any(x.reg_name(r) in (f'x{base}',f'w{base}') for r in x.regs_access()[1]) for x in instructions if low<x.address<load.address):continue
        candidates.append(dict(load_offset=load.address,add_offset=add.address,branch_offset=branch.address,
            bound_compare_offset=guard.address,bound_branch_offset=high.address,bound_branch_target=high_target,
            base_register=base,selector_register=selector,result_register=result,
            proof='u32 selector has identical local register/spill provenance as unsigned CMP-or-SUBS/HI bound'))
    require(len(candidates)==1,'switch lacks unique exact guarded spilled-selector dispatch')
    return candidates[0]

def verify_switch_tables(record,section,relocations,code_size):
    require(0<code_size<record.size and (record.size-code_size)%4==0,'invalid inline switch extent')
    start=record.source_start-section.virtual_address
    raw=bytes(section.content)[start:start+record.size]
    require(len(raw)==record.size,'truncated compiler function')
    require(all(r['offset']<code_size for r in relocations),'relocation inside switch data')
    addends={r['offset']:((r['raw']&0xffffff)-(1<<24) if r['raw']&0x800000 else r['raw']&0xffffff) for r in relocations if r['type']==10}
    table_relocs=[r for r in relocations if r['type'] in (3,4) and r['symbol']==record.symbol and code_size<=addends.get(r['offset'],-1)<record.size]
    offsets=sorted({addends[r['offset']] for r in table_relocs})
    require(offsets and offsets[0]==code_size and all(v%4==0 for v in offsets),'missing exact compiler table ownership')
    md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_LITTLE_ENDIAN);md.detail=True
    instructions=list(md.disasm(raw[:code_size],0));boundaries={x.address for x in instructions}
    require(sum(x.size for x in instructions)==code_size,'code prefix does not fully decode')
    tables=[]
    for number,offset in enumerate(offsets):
        end=offsets[number+1] if number+1<len(offsets) else record.size
        values=list(struct.unpack_from('<'+'i'*((end-offset)//4),raw,offset));targets=[offset+v for v in values]
        require(all(v in boundaries for v in targets),'switch target leaves code boundary')
        pages=[r for r in table_relocs if addends[r['offset']]==offset and r['type']==3]
        lows=[r for r in table_relocs if addends[r['offset']]==offset and r['type']==4]
        require(len(pages)==len(lows)==1,'ambiguous table address pair')
        page,low=pages[0]['offset'],lows[0]['offset'];pw,lw=struct.unpack_from('<I',raw,page)[0],struct.unpack_from('<I',raw,low)[0];base=pw&31
        require(pw&0x9f000000==0x90000000 and lw&0xffc00000==0x91000000 and lw&31==base and (lw>>5)&31==base and page<low,'bad table PAGE/ADD pair')
        require(all(not any(x.reg_name(r) in (f'x{base}',f'w{base}') for r in x.regs_access()[1]) for x in instructions if page<x.address<low),'table base overwritten before ADD')
        dispatch=bounded_dispatch(instructions,low,base,len(values),code_size)
        tables.append(dict(offset=offset,size=end-offset,entries=len(values),signed_offsets=values,targets=targets,
            page_relocation_offset=page,pageoff_relocation_offset=low,symbol=record.symbol,addend=offset,
            dispatch=dispatch,sha256=hashlib.sha256(raw[offset:end]).hexdigest()))
    return dict(offset=code_size,size=record.size-code_size,sha256=hashlib.sha256(raw[code_size:]).hexdigest(),
        role='compiler signed32 switch tables; explicit no-unwind data',tables=tables)
