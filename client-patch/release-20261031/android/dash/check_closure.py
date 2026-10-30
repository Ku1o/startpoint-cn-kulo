"""Assert the one action helper's exact current native dependency traits."""
from pathlib import Path
import json,sys,zipfile
HERE=Path(__file__).resolve().parent;CLIENT=HERE.parent
import bootstrap
from input_config import input_path,repo_path,work_path
sys.dont_write_bytecode=True;sys.path.insert(0,str(repo_path('client-patch/pr43-port/support')))
import common
raw=input_path('trigger9000_swf').read_bytes()
assert common.sha(raw)=='d06b1431c13d7d50765f81ed4a747be00e01500c5288702d816398e4fcc666f2'
abc,_=common.main_abc(raw)
classes={abc.mn_name(row[0]).split('::')[-1]:(ci,row) for ci,row in enumerate(abc.instances)}
checks=[]
def trait(owner,name,static=False,public=False):
 ci,row=classes[owner];items=abc.classes[ci][1] if static else row[6]
 matches=[t for t in items if abc.mn_name(t.name).split('::')[-1]==name]
 if public:matches=[t for t in matches if abc.multinames[t.name][0]==7 and abc.namespaces[abc.multinames[t.name][1]][0]==22 and abc.ns_name(abc.multinames[t.name][1])=='']
 assert matches,(owner,name,static,public)
 t=matches[0];mn=abc.multinames[t.name];ns=abc.namespaces[mn[1]]
 rec={'owner':abc.mn_name(row[0]),'name':name,'static':static,'kind':t.kind,'namespaceKind':ns[0],'namespaceUri':abc.ns_name(mn[1]),'data':t.data}
 if t.data[0]=='method':rec['signature']=abc.methods[t.data[2]]
 if t.data[0]=='slot':rec['type']=abc.mn_name(t.data[2]) if t.data[2] else '*'
 checks.append(rec);return t
for name in ('address','originMemberIndex','source'):trait('MemberImpl',name,public=True)
trait('SquadMemberSource','clv',public=True)
for name in ('getElement','applyInstantAbility'):trait('MemberImpl',name,public=True)
for owner,name in [('AbilityPowerValue','fromSlv'),('AbilityPowerValueCalculateMethod','LevelScale'),('SLv_Impl_','toInt'),('SLv_Impl_','MAX_SLV'),('InstantAbilityAddress','Instant'),('InstantAbilityInstantCharacterContent','InvokeSkill')]:trait(owner,name,True,True)
logic=trait('MemberImpl','logicAssets');type_name=abc.mn_name(logic.data[2]).split('::')[-1]
trait(type_name,'getActionDsl',public=True)
trait('ZoneManager','executeAction')
trait('ZoneManagerImpl','executeAction',public=True)
result={'status':'all_selected_dash_native_dependency_traits_present','inputSha256':common.sha(raw),'checks':checks,
 'helperPublicQName':{'kind':22,'uri':''},'dynamicObjects':'InvokeSkill parameters and executeAction context are created by existing native code, not missing sealed fields',
 'nativeBehaviourUnchanged':True,'runtimeExecuted':False}
out=work_path('dash/inspections/direct-transitive-trait-proof.json');out.parent.mkdir(parents=True,exist_ok=True);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n','utf-8')
print(json.dumps({'status':result['status'],'checks':len(checks)}))
