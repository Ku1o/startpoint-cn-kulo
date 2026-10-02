from __future__ import annotations
import argparse
import importlib.util,json,sys,traceback,hashlib
from pathlib import Path
parser=argparse.ArgumentParser(description='Apply the seven equipment client layers to an already prepared L1 SWF.')
parser.add_argument('--work-dir', type=Path, required=True, help='directory containing public-l1.swf; outputs are written here')
base=parser.parse_args().work_dir.resolve()
root=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(root/'battle-rules'))
spec=importlib.util.spec_from_file_location('core',root/'battle-rules'/'core.py');core=importlib.util.module_from_spec(spec);sys.modules['core']=core;spec.loader.exec_module(core)
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def rebase(mod,swf):
 cls=next(v for n,v in vars(mod).items() if isinstance(v,type) and n.endswith('Editor') and issubclass(v,core.Editor));locks=json.loads((Path(mod.HERE)/'baseline.json').read_text())
 def init(self,s):
  core.Editor.__init__(self,s);self.locks={}
  for label in locks:
   b=s.abc.bodies[core.bodies.resolve(s.abc,label)];self.locks[label]={'sha':hashlib.sha256(b[5]).hexdigest(),'header':list(b[1:5])}
 cls.__init__=init

def save_layer(mod,cur,name):
 swf=core.SwfAbc(cur);rebase(mod,swf);e,rep=mod.patch_editor(swf);abc=swf.abc.serialize();out=base/f'{name}.swf';swf.save(out);assert core.SwfAbc(out).abc.serialize()==abc
 (base/f'{name}-report.json').write_text(json.dumps({'status':'static_candidate_runtime_pending','patch':name,'source':str(cur),'source_sha256':hashlib.sha256(cur.read_bytes()).hexdigest(),'output':str(out),'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'output_abc_sha256':hashlib.sha256(abc).hexdigest(),'report':rep},ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8')
 print(name,'OK',hashlib.sha256(out.read_bytes()).hexdigest(),hashlib.sha256(abc).hexdigest())
 return out

try:
 cur=base/'public-l1.swf'
 for lid,dirname in [('l2','equipment-description-override'),('l3','equipment-enhanced-look')]:
  mod=load('pub_'+lid,root/dirname/'overlay.py');cur=save_layer(mod,cur,lid)
 # L4 only updateEnhancedEffectAnimation; preserve equivalent setItemImage behavior already present.
 mod=load('pub_l4',root/'equipment-enhanced-party-frame'/'overlay.py');swf=core.SwfAbc(cur);rebase(mod,swf);orig=mod.rules.find_anchor
 def update_anchor(e,asm,bodies,label=mod.rules.LABEL):
  if label!=mod.rules.LABEL:return orig(e,asm,bodies,label)
  abc=e.abc;b=abc.bodies[bodies.resolve(abc,label)];ins=asm.decode(b[5]);at=3
  if [x.name for x in ins[:2]]!=['getlocal_0','pushscope'] or ins[2].name!='op_ef':raise asm.AsmError('public update prologue changed')
  if ins[3].name!='getlex' or abc.mn_name(ins[3].args[0])!='isEnableEnhancedEffect':raise asm.AsmError('public update anchor changed')
  if b[6] or b[7]:raise asm.AsmError('public update gained exception/traits')
  if any(x.target==at or (x.cases and at in [x.default,*x.cases]) for x in ins):raise asm.AsmError('public update anchor branch target')
  if any(x.name=='pushstring' and abc.strings[x.args[0]]==mod.rules.PREFIX.encode() for x in ins):raise asm.AsmError('already patched')
  return at
 mod.rules.find_anchor=update_anchor;mod.rules.LOCALS={k:v+1 for k,v in mod.rules.LOCALS.items()}
 e=mod.EquipmentEnhancedPartyFrameEditor(swf);anchors={mod.rules.LABEL:update_anchor(e,mod.asm,mod.bodies)};e.insert(mod.rules.LABEL,anchors[mod.rules.LABEL],mod.rules.insertion(e),mod.asm.FORBID);methods=e.apply();assert set(methods)=={mod.rules.LABEL};assert not e.new_methods and not e.traits
 rep={'anchors':anchors,'methods':methods,'headers':{label:list(e.abc.bodies[mod.bodies.resolve(e.abc,label)][1:5]) for label in methods},'inserted_counts':{label:change['insertions'][0][1] for label,change in methods.items()},'unchanged_method_bodies':mod.battle_rules_verify.verify_editor(e,methods),'pool':e.pool.report(),'skipped_equivalent_target':'PartyItemThumbnailView/setItemImage'}
 abc=swf.abc.serialize();cur=base/'l4-nodup.swf';swf.save(cur);assert core.SwfAbc(cur).abc.serialize()==abc;(base/'l4-nodup-report.json').write_text(json.dumps({'status':'static_candidate_runtime_pending','patch':'equipment-enhanced-party-frame','source':str(base/'l3.swf'),'source_sha256':hashlib.sha256((base/'l3.swf').read_bytes()).hexdigest(),'output':str(cur),'output_sha256':hashlib.sha256(cur.read_bytes()).hexdigest(),'output_abc_sha256':hashlib.sha256(abc).hexdigest(),'report':rep},ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8');print('l4 OK',hashlib.sha256(cur.read_bytes()).hexdigest(),hashlib.sha256(abc).hexdigest())
 # L5 custom anchor
 mod=load('pub_l5',root/'equipment-awakening-material'/'overlay.py');swf=core.SwfAbc(cur);rebase(mod,swf)
 def find(e,asm,bodies,label=mod.rules.LABEL):
  abc=e.abc;b=abc.bodies[bodies.resolve(abc,label)];ins=asm.decode(b[5]);at=19
  if [x.name for x in ins[:2]]!=['getlocal_0','pushscope']:raise asm.AsmError('public awaken prologue')
  if abc.methods[b[0]][3]&mod.rules.NEED_ACTIVATION or b[6] or b[7]:raise asm.AsmError('public awaken activation')
  inc=[i for i,x in enumerate(ins) if x.target==at or (x.cases and at in [x.default,*x.cases])]
  if inc!=[15]:raise asm.AsmError(f'public awaken incoming {inc}')
  if ins[15].name!='iffalse' or ins[13].name!='callproperty' or abc.mn_name(ins[13].args[0])!='hasStack':raise asm.AsmError('public awaken guard')
  if b[2]!=min(mod.rules.LOCALS.values()) or core.asm.block_locals(ins)>b[2]:raise asm.AsmError('public awaken locals')
  def nm(x):return abc.mn_name(x.args[0]) if x.args else None
  for off,(n,o) in zip((-1,0,1),[('returnvalue',None),('getlocal_1',None),('findproperty','get_rarity')]):
   x=ins[at+off]
   if x.name!=n or (o and nm(x)!=o):raise asm.AsmError('public awaken native')
  if ins[at+4].name!='callproperty' or nm(ins[at+4])!='getEquipmentAwakingCrystal':raise asm.AsmError('public awaken pick')
  return at
 mod.rules.find_anchor=find;swf=core.SwfAbc(cur);e,rep=mod.patch_editor(swf);abc=swf.abc.serialize();cur=base/'l5-nodup.swf';swf.save(cur);assert core.SwfAbc(cur).abc.serialize()==abc;(base/'l5-nodup-report.json').write_text(json.dumps({'status':'static_candidate_runtime_pending','patch':'equipment-awakening-material','source':str(base/'l4-nodup.swf'),'source_sha256':hashlib.sha256((base/'l4-nodup.swf').read_bytes()).hexdigest(),'output':str(cur),'output_sha256':hashlib.sha256(cur.read_bytes()).hexdigest(),'output_abc_sha256':hashlib.sha256(abc).hexdigest(),'report':rep},ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8');print('l5 OK',hashlib.sha256(cur.read_bytes()).hexdigest(),hashlib.sha256(abc).hexdigest())
 for lid,dirname in [('l6','equipment-sort-pin'),('l7','item-rarity-frame-override')]:
  mod=load('pub_'+lid,root/dirname/'overlay.py');cur=save_layer(mod,cur,lid)
 print(json.dumps({'status':'ok','output':str(cur),'sha256':hashlib.sha256(cur.read_bytes()).hexdigest()},ensure_ascii=False))
except Exception as ex:
 print(json.dumps({'status':'error','type':type(ex).__name__,'error':str(ex),'trace':traceback.format_exc()},ensure_ascii=False));raise
