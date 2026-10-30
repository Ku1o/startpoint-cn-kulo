"""Add the one omitted donor action method; preserve every existing method."""
from pathlib import Path
import copy,json,sys
HERE=Path(__file__).resolve().parent;CLIENT=HERE.parent
import bootstrap
from input_config import input_path,input_sha,work_path,capability_module
p=capability_module()
LABEL='MemberImpl/wfxRunDashAction'
def main():
 source=input_path('trigger9000_swf')
 expected='d06b1431c13d7d50765f81ed4a747be00e01500c5288702d816398e4fcc666f2'
 assert p.digest(source.read_bytes())==expected
 out=work_path('dash/build01');assert not out.exists()
 e=p.R11Editor(source);before=copy.deepcopy(e.abc)
 assert LABEL not in p.bodies.label_map(e.abc).values()
 imported=p.graft_donor(e,[LABEL])
 assert len(e.new_methods)==1 and not e.report and not e.added_state
 assert len(e.abc.methods)==len(before.methods)+1 and len(e.abc.bodies)==len(before.bodies)+1
 assert e.abc.methods[:-1]==before.methods
 assert all(p.body_bytes(a)==p.body_bytes(b) for a,b in zip(before.bodies,e.abc.bodies))
 traitbytes=lambda traits:p.body_bytes([0,0,0,0,0,b'',[],traits])
 changed=[]
 for i,row in enumerate(before.instances):
  new=e.abc.instances[i]
  assert new[:6]==row[:6] and traitbytes(new[6][:len(row[6])])==traitbytes(row[6])
  if len(new[6])!=len(row[6]):
   assert e.abc.mn_name(row[0])=='pinball.scene.battle.battle.squad.member::MemberImpl'
   trait,=new[6][len(row[6]):];assert trait.kind==1 and e.abc.mn_name(trait.name)=='wfxRunDashAction'
   mn=e.abc.multinames[trait.name];assert mn[0]==7 and e.abc.namespaces[mn[1]][0]==22 and e.abc.ns_name(mn[1])==''
   changed.append(i)
 assert len(changed)==1 and len(e.abc.classes)==len(before.classes)
 for old,new in zip(before.classes,e.abc.classes):assert old[0]==new[0] and traitbytes(old[1])==traitbytes(new[1])
 reverse=copy.deepcopy(e.abc);reverse.methods.pop();reverse.bodies.pop();reverse.instances[changed[0]][6].pop()
 for name in ('strings','ints','uints','doubles','namespaces','ns_sets','multinames'):
  setattr(reverse,name,getattr(reverse,name)[:len(getattr(before,name))])
 assert reverse.serialize()==before.serialize()
 out.mkdir(parents=True);swf=out/'production1031-dash-action-r1.swf';swf.write_bytes(p.compose(e));after=p.SwfAbc(swf)
 assert after.abc.serialize()==e.abc.serialize()
 envelope=p.envelope(e.swf,after,{'boot_ffc6'})
 row=e.new_methods[0];bi=p.bodies.resolve(after.abc,LABEL);body=after.abc.bodies[bi]
 report={'status':'single_missing_method_static_verified_runtime_pending','input':str(source),'inputSha256':expected,
  'output':str(swf),'outputSha256':p.digest(swf.read_bytes()),'donor':imported,'newMethods':e.new_methods,
  'actualMethodInfo':body[0],'actualBodyIndex':bi,'codeSha256':p.digest(body[5]),'methodSignature':after.abc.methods[body[0]],
  'methodPublicQName':True,'newStaticSlots':0,'newInstanceFields':0,'existingBodiesChanged':0,'methodsAdded':1,
  'allOldMethodInfoAndBodiesExact':True,'oldInstanceAndStaticLayoutsExact':True,'reverseDeltaRestoresInputAbc':True,
  'envelope':envelope,'existingTrigger9000AndTutorialFixesPreserved':True,'bundleAndAdmissionUnchanged':True,
  'totalMethods':len(after.abc.methods),'deviceTested':False}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
 print(json.dumps({k:report[k] for k in ('status','output','outputSha256','actualMethodInfo','actualBodyIndex','codeSha256','existingBodiesChanged','methodsAdded')}))
if __name__=='__main__':main()
