"""Strict compiler table proof for a direct u32 selector and separate sum register."""
import re
from unittest.mock import patch
import capstone


def direct_dispatch(instructions,low,base,entries,code_size):
 def writes(ins,r):return any(ins.reg_name(w) in (f'w{r}',f'x{r}') for w in ins.regs_access()[1])
 def control(ins):return any(ins.group(g) for g in (capstone.CS_GRP_JUMP,capstone.CS_GRP_CALL,capstone.CS_GRP_RET,capstone.CS_GRP_INT,capstone.CS_GRP_IRET)) or ins.mnemonic in ('brk','hlt','udf','svc','hvc','smc','eret','drps')
 candidates=[]
 for i,load in enumerate(instructions):
  match=re.fullmatch(rf'x(\d+), \[x{base}, x(\d+), lsl #2\]',load.op_str)
  if load.address<=low or load.mnemonic!='ldrsw' or not match or i+2>=len(instructions):continue
  dest,selector=map(int,match.groups())
  sums=[]
  for ai,add in enumerate(instructions[i+1:i+9],i+1):
   am=re.fullmatch(r'x(\d+), x(\d+), x(\d+)',add.op_str)
   if add.mnemonic=='add' and am and {int(am[2]),int(am[3])}=={dest,base}:sums.append((ai,add,int(am[1])))
  if not sums:continue
  ai,add,result=sums[0]
  if any(control(x) or writes(x,dest) or writes(x,base) for x in instructions[i+1:ai]):continue
  branches=[(bi,x) for bi,x in enumerate(instructions[ai+1:ai+5],ai+1) if x.mnemonic=='br' and x.op_str==f'x{result}']
  if not branches:continue
  bi,branch=branches[0]
  if any(control(x) or writes(x,result) for x in instructions[ai+1:bi]):continue
  guards=[(n,x) for n,x in enumerate(instructions[max(0,i-8):i],max(0,i-8)) if x.mnemonic=='cmp' and re.fullmatch(rf'w{selector}, #(0x[0-9a-f]+|\d+)',x.op_str) and int(x.op_str.split('#')[1],0)==entries-1]
  if not guards:continue
  gi,guard=guards[-1]
  highs=[(n,x) for n,x in enumerate(instructions[gi+1:i],gi+1) if x.mnemonic=='b.hi']
  if len(highs)!=1:continue
  hi,high=highs[0];target=int(high.op_str.lstrip('#'),0)
  if not branch.address+4<=target<code_size:continue
  if any('nzcv' in [x.reg_name(w) for w in x.regs_access()[1]] for x in instructions[gi+1:hi]):continue
  # Every ARM64 W-register write clears the upper 32 bits. In particular,
  # SUB Wselector proves the same u32 index checked by CMP and read by LDRSW.
  definitions=[(n,x) for n,x in enumerate(instructions[max(0,gi-8):gi],max(0,gi-8)) if writes(x,selector)]
  if not definitions:continue
  di,definition=definitions[-1]
  if f'w{selector}' not in [definition.reg_name(w) for w in definition.regs_access()[1]]:continue
  if any(control(x) and x.address!=high.address for x in instructions[di+1:i]):continue
  if any(writes(x,selector) for x in instructions[gi+1:i]):continue
  if any(writes(x,base) for x in instructions if low<x.address<load.address):continue
  candidates.append(dict(load_offset=load.address,add_offset=add.address,branch_offset=branch.address,bound_compare_offset=guard.address,bound_branch_offset=high.address,bound_branch_target=target,base_register=base,selector_register=selector,result_register=result,u32_definition_offset=definition.address,proof='exact W-write/CMP-HI/LDRSW/ADD/BR direct-selector chain'))
 if len(candidates)!=1:raise ValueError('switch lacks a unique direct-u32 guarded dispatch')
 return candidates[0]


def verify_switch_tables(record,section,relocations,code_size):
 import switch_adapter
 with patch.object(switch_adapter,'bounded_dispatch',direct_dispatch):
  return switch_adapter.verify_switch_tables(record,section,relocations,code_size)
