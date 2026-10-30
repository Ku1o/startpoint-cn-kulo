"""Exact reusable owning-script and receiver-load readers from adopted settings probes."""
import re
KIND='pinball.scene.applicationOption::ApplicationOptionSwitchButtonKind'
def owning_script(v,owner):
 ci,=[i for i,r in enumerate(v.a.instances) if v.a.mn_name(r[0])==owner]
 script,=[r for r in v.a.scripts if any(t.kind==4 and t.data[2]==ci for t in r[1])]
 bi,=[i for i,b in enumerate(v.a.bodies) if b[0]==script[0]]
 return ci,script[0],bi

def receiver_loads(md,raw,start=0):
 aliases={'x0'};found=[]
 for x in md.disasm(raw,start):
  load=re.fullmatch(r'x(\d+), \[(x\d+), #0x30\]',x.op_str)
  if x.mnemonic=='ldr' and load and load.group(2) in aliases:found.append(dict(pc=hex(x.address),instruction=x.mnemonic+' '+x.op_str))
  move=re.fullmatch(r'(x\d+), (x\d+)',x.op_str);add_alias=bool(x.mnemonic=='mov' and move and move.group(2) in aliases)
  aliases.difference_update(x.reg_name(r) for r in x.regs_access()[1])
  if x.mnemonic in ('bl','blr'):aliases.difference_update('x'+str(i) for i in range(19))
  if add_alias:aliases.add(move.group(1))
 return found
