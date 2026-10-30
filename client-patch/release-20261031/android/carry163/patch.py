"""Native continuation hooks for the standalone StageCarryState ABC."""
from pathlib import Path
import hashlib
import asm,bodies
ROOT=Path(__file__).resolve().parent
TARGETS=('BattleContinuationData/bothbossNext','SquadImpl/setContinuationData')
LOCKS={TARGETS[0]:('f63dfd1b167d042500b268322029b7cdbbc5f4a432ddc524e538841a205fb864',[4,28,1,1]),TARGETS[1]:('76ea74e715e773093a93bb6ef7c30144338b0564ab8e81a44ab5162eaed5fdbb',[2,5,1,2])}

def helper_q(e):
 ns=(0x16,e.pool.string('cn.carry'))
 if ns in e.abc.namespaces:ni=e.abc.namespaces.index(ns)
 else:ni=len(e.abc.namespaces);e.abc.namespaces.append(ns)
 mn=(7,ni,e.pool.string('StageCarryState'))
 if mn in e.abc.multinames:return e.abc.multinames.index(mn)
 e.abc.multinames.append(mn);e.pool.added_multinames.append('cn.carry::StageCarryState');return len(e.abc.multinames)-1

def build(e):
 for row in e.abc.instances:
  for t in row[6]:
   if 'wfxStage' in e.abc.mn_name(t.name):raise ValueError('old PR163 already installed: rebuild without 163 before replacement')
 for ci,row in enumerate(e.abc.classes):
  if any('wfxStage' in e.abc.mn_name(t.name) for t in row[1]):raise ValueError('old PR163 storage already installed')
 h=helper_q(e);capture=e.newq('capture');apply=e.newq('apply')
 for l,(digest,header) in LOCKS.items():
  body=e.body(l)
  if hashlib.sha256(body[5]).hexdigest()!=digest or body[1:5]!=header:raise ValueError('native continuation preimage mismatch: '+l)
  ins=asm.decode(body[5]);op='returnvalue' if l==TARGETS[0] else 'returnvoid';returns=[i for i,x in enumerate(ins) if x.name==op]
  if returns!=[len(ins)-1]:raise ValueError('native return shape mismatch')
  if l==TARGETS[0]:
   if ins[-2].name!='getlocal' or ins[-2].args!=[16]:raise ValueError('native continuation return local mismatch')
   code=[('dup',),('getlex',h),('swap',),('getlocal_3',),('callpropvoid',capture,2)]
  else:code=[('getlex',h),('getlocal_0',),('getlocal_1',),('callpropvoid',apply,2)]
  e.insert(l,returns[0],code,incoming=asm.ENTER)
 return {'helper_abc_role':'android.inputs.carry_helper_abc','helper_qname':'cn.carry::StageCarryState','native_targets':TARGETS,'replacement_for_original_PR163':True,'existing_instance_layout_unchanged':True}
