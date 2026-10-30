"""Revision3 selective 195. UI raw getter must be installed first. No whole-body replacement."""
import hashlib,json
import bootstrap
import asm,bodies
import selected_patch as old
APP='pinball.common.data.localStore::ApplicationOptionLogic'
BATTLE='pinball.scene.battle.battle::Battle'
GLOBAL='pinball.context.global::GlobalLogic'
RAW='cnTeammateEffectsVisibleFromRaw'
READER='cnTeammateEffectsVisibleFromBattle'
TARGETS=(old.P1_LABEL,old.P3_LABEL,old.P4_LABEL,old.P5_LABEL)
def public_method(abc,owner,name,static=False):
 hits=[(i,row) for i,row in enumerate(abc.instances) if abc.mn_name(row[0])==owner]
 if len(hits)!=1:raise ValueError(('owner',owner))
 i,row=hits[0];traits=abc.classes[i][1] if static else row[6]
 ts=[t for t in traits if t.data[0]=='method' and abc.mn_name(t.name)==name]
 if len(ts)!=1:raise ValueError(('required exact method',owner,name,len(ts)))
 t=ts[0];mn=abc.multinames[t.name];ns=abc.namespaces[mn[1]]
 if mn[0]!=7 or ns[0]!=0x16 or abc.s(ns[1])!='':raise ValueError(('not empty-package public QName',owner,name,mn,ns))
 return t.name,abc.methods[t.data[2]]
def verify(abc):
 raw,info=public_method(abc,APP,RAW,True)
 if abc.mn_name(info[0])!='Boolean' or [abc.mn_name(t) for t in info[1]]!=['Object'] or info[3]!=0:raise ValueError('raw API signature')
 global_get,info=public_method(abc,GLOBAL,'_getApplicationOption')
 if abc.mn_name(info[0])!='Object' or info[1] or info[3]!=0:raise ValueError('native Global getter signature')
 for label,digest in {'GlobalLogic/_getApplicationOption':'15b1af691e367811ac9095edc541b161e33037cacb3d5dc24305f7415a0460c7','Gear/absorb':'c96dedf963872f30428d74653d4f3968fb66e29441e0380451f1ed46644928a5'}.items():
  if hashlib.sha256(abc.bodies[bodies.resolve(abc,label)][5]).hexdigest()!=digest:raise ValueError('native dependency body differs '+label)
 anchors={old.P1_LABEL:old._verify_p1(abc),old.P3_LABEL:old._verify_p3(abc),old.P4_LABEL:old._verify_p4(abc),old.P5_LABEL:old._verify_p5(abc)}
 body=abc.bodies[bodies.resolve(abc,old.P3_LABEL)];xs=asm.decode(body[5]);reader=[i for i,x in enumerate(xs) if x.name=='getproperty' and abc.mn_name(x.args[0]).split('::')[-1]=='showOthersMultiball']
 if len(reader)!=1:raise ValueError('unique native multiball reader required')
 at=reader[0]+1
 if xs[at].name!='iffalse':raise ValueError('multiball reader must directly feed native iffalse')
 anchors['P2-reader']={'insert_at':at,'native_read_at':at-1,'multiball_mn':xs[at-1].args[0],'original_iffalse_target':xs[at].target}
 return anchors,raw,global_get

def build(e):
 anchors,raw,global_get=verify(e.abc)
 for label in TARGETS:
  body=e.body(label);e.locks[label]={'sha':hashlib.sha256(body[5]).hexdigest(),'header':list(body[1:5])}
 q=e.q
 # Keep original native failures. This resolves one existing Object, creates no option wrapper.
 reader=e.add_method(APP,READER,'Boolean',[BATTLE],[('getlocal_0',),('pushscope',),('getlex',q(APP)),('getlocal_1',),('getproperty',q('gear')),('getlex',q(GLOBAL)),('pushnull',),('callproperty',q('absorb'),2),('coerce',q(GLOBAL)),('callproperty',global_get,0),('callproperty',raw,1),('returnvalue',)],2,static=True)
 def visible(kind):
  load=[('getlocal_0',)]
  if kind=='view':load+=[('getproperty',q('settings'))]
  return [('getlex',q(APP))]+load+[('getproperty',q('battle')),('callproperty',reader,1)]
 a=anchors[old.P1_LABEL]
 e.insert(old.P1_LABEL,a['insert_at'],visible('settings')+[('iftrue','KEEP'),('pushfalse',),('returnvalue',),('label','KEEP')],incoming=a['incoming'])
 # The original reader Boolean stays on stack. Visible keeps it; hidden feeds false to native fallback.
 a=anchors['P2-reader']
 e.insert(old.P3_LABEL,a['insert_at'],visible('view')+[('iftrue','KEEP'),('pop',),('pushfalse',),('label','KEEP')],incoming=asm.FORBID)
 a=anchors[old.P3_LABEL]
 e.insert(old.P3_LABEL,a['case43_insert_at'],visible('view')+[('iftrue','KEEP'),('getlocal_2',),('getproperty',a['params_mn']),('pushbyte',0),('getproperty',a['rt_mn']),('coerce',a['ball_peek_mn']),('callproperty',a['ball_is_primary_mn'],0),('convert_b',),('iftrue','KEEP'),('getlocal',a['return_local']),('returnvalue',),('label','KEEP')],incoming=a['case43_incoming'])
 e.insert(old.P3_LABEL,a['insert_at'],visible('view')+[('iftrue','KEEP'),('getlocal',a['return_local']),('returnvalue',),('label','KEEP')],incoming=a['incoming'])
 a=anchors[old.P4_LABEL]
 e.insert(old.P4_LABEL,a['insert_at'],visible('effect')+[('iftrue','KEEP'),('pushfalse',),('returnvalue',),('label','KEEP')],incoming=a['incoming'])
 a=anchors[old.P5_LABEL]
 e.insert(old.P5_LABEL,a['insert_at'],[('getlocal_0',),('getproperty',a['battle_mn']),('getproperty',a['lightweight_mode_level_mn']),('pushbyte',1),('iflt','OLD'),('getlocal_2',),('getproperty',a['params_mn']),('pushbyte',1),('getproperty',a['rt_mn']),('convert_b',),('iffalse','OUT'),('getlocal_0',),('callproperty',a['get_random_rotation_mn'],0),('pop',),('label','OUT'),('returnvoid',),('label','OLD')],incoming=a['incoming'])
 return {'anchors':anchors,'reader':APP+'$/'+READER,'native_global_getter_namespace_kind':22,'native_global_getter_namespace_uri':'','preparation_unchanged':True,'four_existing_bodies':list(TARGETS),'six_sites':['P1','P2-reader','P2b','P3','P4','P5'],'P5_independent':True}
