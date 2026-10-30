"""Native application-option row and original object-backed persistent setting."""
import copy,hashlib
OWNER='pinball.common.data.localStore::ApplicationOptionLogic'
KIND='pinball.scene.applicationOption::ApplicationOptionSwitchButtonKind'
ITEM='pinball.scene.applicationOption.panel::SwitchConfigContainerItem'
LAYOUT='pinball.ui.display::UiDisplayObjectContainer'
KEY='cnTeammateEffectsVisible'
TAG='CnTeammateEffectsVisible'
GET='getTeammateEffectsVisible';SET='setTeammateEffectsVisible';RAW='cnTeammateEffectsVisibleFromRaw'
LOCKS={
 'ApplicationOptionScene/prepareScene':('52c4e796259b7ad0a7442ceface825010a6676c2ec1e00206867e083b9af213f',[11,23,1,2]),
 'ApplicationOptionScene/switchButtonInput':('ff27ff6d6c7deeb238c603920ec2bd365c6f881ec6070ca810bca8fa0378aaa1',[3,7,1,2]),
 'ApplicationOptionView/run':('7875521f94544eee984e790b1ee2ee0881e321db896b9871b61766939b5f3f34',[24,12,1,2]),
 'SwitchButtonConfigInnerContentView/run':('ee35ad2540a4578e5996965bb427d6991bd087230fab8b836eeb758a0f073ddd',[11,10,1,2])}
def build(e):
 q=e.q;asm=__import__('asm')
 before={}
 for label,(digest,header) in LOCKS.items():
  b=e.body(label);assert hashlib.sha256(b[5]).hexdigest()==digest and b[1:5]==header,('UI baseline differs',label)
  before[label]=copy.deepcopy(b);e.locks[label]={'sha':digest,'header':header}
 # The Boolean is read from the original raw Object. No cache, IO, version
 # mutation, new old-owner slot, or alternative settings file is introduced.
 raw=e.add_method(OWNER,RAW,'Boolean',['Object'],[
  ('getlocal_0',),('pushscope',),('getlocal_1',),('getproperty',e.newq(KEY)),('setlocal_2',),
  ('getlocal_2',),('istype',q('Boolean')),('iffalse','DEFAULT'),('getlocal_2',),('convert_b',),('returnvalue',),
  ('label','DEFAULT'),('pushtrue',),('returnvalue',)],3,static=True)
 getter=e.add_method(OWNER,GET,'Boolean',[],[
  ('getlocal_0',),('pushscope',),('getlex',q(OWNER)),('getlocal_0',),('getproperty',q('applicationOption')),('callproperty',raw,1),('returnvalue',)],1)
 setter=e.add_method(OWNER,SET,'void',['Boolean'],[
  ('getlocal_0',),('pushscope',),('getlocal_0',),('getproperty',q('applicationOption')),('getlocal_1',),('setproperty',q(KEY)),
  ('getlocal_0',),('callpropvoid',q('store'),0),('returnvoid',)],2)
 enumgetter=e.add_method(KIND,TAG,KIND,[],[
  ('getlocal_0',),('pushscope',),('getlex',q(KIND)),e.string(TAG),('pushbyte',18),('pushnull',),('construct',3),('returnvalue',)],1,static=True)
 kindindex,kindrow=e.instance(KIND)
 gt=next(t for t in e.abc.classes[kindindex][1] if t.name==enumgetter);gt.kind=2
 e.new_methods[-1]['label']+='|get'
 __import__('bodies')._CACHE.pop(id(e.abc),None)
 makekind=e.add_method(OWNER,'cnTeammateEffectsKind',KIND,[],[
  ('getlocal_0',),('pushscope',),('getlex',q(KIND)),('getproperty',enumgetter),('returnvalue',)],1,static=True)
 addmap=e.add_method(OWNER,'cnTeammateEffectsInitialMap','void',['haxe.ds::EnumValueMap',OWNER],[
  ('getlocal_0',),('pushscope',),('getlocal_1',),('getlex',q(OWNER)),('callproperty',makekind,0),
  ('getlocal_2',),('callproperty',getter,0),('callpropvoid',q('set'),2),('returnvoid',)],3,static=True)
 addrow=e.add_method(OWNER,'cnTeammateEffectsAddRow','Array',['Array'],[
  ('getlocal_0',),('pushscope',),('getlocal_1',),('pushbyte',6),('pushbyte',0),
  ('getlex',q(ITEM)),e.string('kind'),('getlex',q(OWNER)),('callproperty',makekind,0),
  e.string('title'),e.string('application_option_cooperation_saving_mode_title'),
  e.string('titleContext'),('getlex',q('haxe.ds::Option')),('getproperty',q('None')),
  e.string('description'),e.string('application_option_cooperation_saving_mode_description'),
  e.string('descriptionContext'),('getlex',q('haxe.ds::Option')),('getproperty',q('None')),
  ('newobject',5),('callproperty',q('SwitchButton'),1),('callpropvoid',q('http://adobe.com/AS3/2006/builtin::splice'),3),
  ('getlocal_1',),('returnvalue',)],2,static=True)
 labels=e.add_method(OWNER,'cnTeammateEffectsLabel','void',[KIND,LAYOUT],[
  ('getlocal_0',),('pushscope',),('getlocal_1',),('getproperty',q('index')),('pushbyte',18),('ifne','DONE'),
  ('getlocal_1',),('getproperty',q('tag')),e.string(TAG),('ifne','DONE'),
  ('getlocal_2',),e.string('title'),('pushnull',),('callproperty',q('getText'),2),e.string('队友特效'),('callpropvoid',q('set_text'),1),
  ('getlocal_2',),e.string('description'),('pushnull',),('callproperty',q('getText'),2),e.string('关闭后隐藏队友演出和特效。'),('callpropvoid',q('set_text'),1),
  ('label','DONE'),('returnvoid',)],3,static=True)
 # Original instruction anchors are from exact R11/coreddde methods. Each
 # insertion retains the complete old branch and is reversibly recorded.
 code=asm.decode(before['ApplicationOptionScene/prepareScene'][5]);assert code[240].op==0x5e and code[246].name=='constructprop'
 e.insert('ApplicationOptionScene/prepareScene',240,[('getlex',q(OWNER)),('getlocal',9),('getlocal_0',),('getproperty',q('applicationOption')),('callpropvoid',addmap,2)])
 e.insert('ApplicationOptionScene/switchButtonInput',2,[
  ('getlocal_1',),('getproperty',q('index')),('pushbyte',18),('ifne','OLD'),
  ('getlocal_1',),('getproperty',q('tag')),e.string(TAG),('ifne','OLD'),
  ('getlocal_0',),('getproperty',q('applicationOption')),('getlocal_2',),('callpropvoid',setter,1),('returnvoid',),('label','OLD')])
 code=asm.decode(before['ApplicationOptionView/run'][5]);assert code[348].name=='newarray' and code[348].args==[14] and code[351].name=='constructprop'
 e.insert('ApplicationOptionView/run',349,[('getlex',q(OWNER)),('swap',),('callproperty',addrow,1)])
 code=asm.decode(before['SwitchButtonConfigInnerContentView/run'][5]);assert code[174].name=='callpropvoid' and code[175].name=='returnvoid'
 e.insert('SwitchButtonConfigInnerContentView/run',175,[('getlex',q(OWNER)),('getlocal_0',),('getproperty',q('kind')),('getlocal_0',),('getproperty',q('layout')),('callpropvoid',labels,2)])
 e.apply()
 # Haxe static values are initialized by the class-owning SCRIPT, not this
 # enum's empty cinit. Preserve its entire original initializer, append one
 # constructor-name string at the exact array expression and retain its ID.
 scriptindex,script=next((i,s) for i,s in enumerate(e.abc.scripts) if any(t.kind==4 and t.data[2]==kindindex for t in s[1]))
 bodyindex,init=next((i,b) for i,b in enumerate(e.abc.bodies) if b[0]==script[0]);oldinit=copy.deepcopy(init)
 assert hashlib.sha256(init[5]).hexdigest()=='e024cb737a256f7081458d13aa5cdf70082f2b7606e8228295e0b09a340416d1' and init[1:5]==[19,1,1,3]
 ins=asm.decode(init[5]);assert ins[154].name=='newarray' and ins[154].args==[18] and ins[155].name=='initproperty' and e.abc.mn_name(ins[155].args[0])=='__constructs__'
 ins[154].args=[19];ins[154:154]=asm.assemble([e.string(TAG)]);init[5]=asm.encode(ins)[0];init[1]=20
 check=__import__('static_check').check_body(e.abc,init)
 restore=asm.decode(init[5]);del restore[154];restore[154].args=[18];assert asm.encode(restore)[0]==oldinit[5]
 initialization={'class':KIND,'script_index':scriptindex,'method_info':init[0],'body':bodyindex,'before_sha256':hashlib.sha256(oldinit[5]).hexdigest(),'after_sha256':hashlib.sha256(init[5]).hexdigest(),'before_header':oldinit[1:5],'after_header':init[1:5],'original_newarray_instruction':154,'old_array_size':18,'new_array_size':19,'new_name':TAG,'script_record_unchanged':True,'reversible_exact':True,'static_check':check}
 return {'setting_key':KEY,'visible_default':True,'no_new_old_slots':True,'no_mutable_static_state':True,'new_kind_index':18,'new_kind_tag':TAG,'original_native_switches_unchanged':True,'new_methods':e.new_methods[-8:],'script_initializer_changes':[initialization],'touched':list(LOCKS)}
