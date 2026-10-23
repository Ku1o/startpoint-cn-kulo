"""Execute the seven actual assistant Option consumers without scene navigation.

The copied instruction ranges include the production accessor, bridge insertion,
and original Some/NoValue CFG. Harness code only supplies the original receiver
local and returns the numeric local extracted by the native switch.
"""
LABELS=[('pinball.scene.littleAssistant::LittleAssistantScene/multipleButtonHandler|1',6),
        ('pinball.scene.littleAssistant::LittleAssistantScene/goToLink|1',1)]

def prepare(stubs,includes):
 key='pinball/common/data/quest/event/common/EventLogicBase.as'
 stubs[key]=stubs[key].replace('public class EventLogicBase {','public class EventLogicBase {public namespace NativeEventLogic="pinball.common.data.quest.event.common:EventLogic";NativeEventLogic function get_playableEndTime():haxe.ds.Option{return Object(this)["get_playableEndTime"]();}')
 stubs['cn/fixture/NativeAssistantProbe.as']='package cn.fixture {public class NativeAssistantProbe {'+''.join('public function site'+str(i)+'(receiver:Object):Number{return 0;}' for i in range(7))+'}}'
 includes.append('cn.fixture.NativeAssistantProbe')

def import_comparisons(builder,target,main,receipts):
 import copy,hashlib
 source=builder.view(main);asm=builder.p.asm;site_number=0;hooked=0
 def local(ins,store=False):
  if ins.op==(0x63 if store else 0x62):return ins.args[0]
  base=0xd4 if store else 0xd0
  assert base<=ins.op<=base+3,ins
  return ins.op-base
 for label,count in LABELS:
  di,=source.by_label[label];original=main.bodies[di];decoded=asm.decode(original[5])
  sites=[i for i,ins in enumerate(decoded) if ins.op==0x46 and main.mn_name(ins.args[0]).rsplit('::',1)[-1]=='get_playableEndTime']
  assert len(sites)==count,(label,sites)
  for call_index in sites:
   has_hook=any(i.op==0x46 and main.mn_name(i.args[0]).rsplit('::',1)[-1]=='nativeComparableEnd' for i in decoded[call_index+1:call_index+4])
   if not has_hook:continue
   hooked+=1
   assert [i.op for i in decoded[call_index-3:call_index]]==[0x60,0x2b,0x2a]
   start=call_index-4;receiver_local=local(decoded[start]);stop=next(i+1 for i in range(call_index+1,call_index+45) if decoded[i].op==0x03)
   fragment=copy.deepcopy(decoded[start:stop]);prefix=[asm.Instruction(0xd0),asm.Instruction(0x30),asm.Instruction(0xd1),asm.Instruction(0x63,[receiver_local])]
   stores=[i for i in fragment if i.op==0x63 or 0xd4<=i.op<=0xd7];end_local=local(stores[-1],True)
   for ins in fragment:
    if ins.target is not None:
     assert start<=ins.target<=stop,(label,ins)
     ins.target=ins.target-start+len(prefix)
    if ins.cases is not None:
     assert all(start<=i<=stop for i in [ins.default]+ins.cases)
     ins.default=ins.default-start+len(prefix);ins.cases=[i-start+len(prefix) for i in ins.cases]
   code=prefix+fragment+[asm.Instruction(0x62,[end_local]),asm.Instruction(0x48)]
   probe='cn.fixture::NativeAssistantProbe/site'+str(site_number)+'|1';ti,=target.by_label[probe];prior=target.a.bodies[ti]
   sliced=list(original);sliced[5]=asm.encode(code)[0];sliced[6]=[]
   try:
    main.bodies[di]=sliced
    imported_source=builder.view(main);expected=imported_source.normalized(di)
    target.a.bodies[ti]=builder.p.Importer(target,imported_source).body(di,prior[0])
   finally:main.bodies[di]=original
   assert target.normalized(ti)==expected,(label,'assistant consumer instructions/CFG differ')
   builder.p.check_body(target.a.bodies[ti],target.a)
   receipts.append({'label':label,'kind':'bounded-native-option-consumer','sourceCodeSha256':hashlib.sha256(original[5]).hexdigest(),'sourceInstructionRange':[start,stop],'sourceGetterInstruction':call_index,'receiverLocal':receiver_local,'extractedValueLocal':end_local,'nativeInstructionsCfgExact':True,'nativeComparableEndIncluded':True,'wholeNavigationExecuted':False,'targetHarness':probe})
   site_number+=1
 return hooked==7

BODY=r'''
if(!nativeBaseline && !EXPECT_CAMPAIGN_DATE_REGRESSIONS){
 var assistantProbe:Object=make("cn.fixture.NativeAssistantProbe"),assistantRevision:int=400;
 for each(var assistantCase:Object in NATIVE_EVENT_CASES){
  bootClass.skip_constructor=true;var assistantEvent:Object=make(assistantCase.name);bootClass.skip_constructor=false;if("eventId" in assistantEvent)assistantEvent.eventId=91;else assistantEvent.id=91;assistantEvent.commonValues={start_time:0,playable_end_time:Option.None};
  for(var assistantSite:int=0;assistantSite<7;assistantSite++){
   var consume:Function=assistantProbe["site"+assistantSite];
   snap2(assistantRevision++,[row2(assistantCase.key+":91",{visible:action(true),enter:action(true)})]);
   check(consume(assistantEvent)==8640000000000000,"actual assistant Some consumer accepts controlled permanent sealed event: "+assistantSite+":"+assistantCase.key);
   snap2(assistantRevision++,[row2(assistantCase.key+":91",{visible:action(true),enter:action(true,61000)})]);
   check(consume(assistantEvent)==61000,"actual assistant Some consumer retains finite deadline: "+assistantSite+":"+assistantCase.key);
   snap2(assistantRevision++,[row2(assistantCase.key+":91",{visible:action(false),enter:action(false)})]);
   check(consume(assistantEvent)==0,"actual assistant Some consumer retains explicit closed deadline: "+assistantSite+":"+assistantCase.key);
   if("eventId" in assistantEvent)assistantEvent.eventId=92;else assistantEvent.id=92;
   var nativeNoValue:Boolean=false;try{consume(assistantEvent);}catch(assistantError:*){if(String(assistantError).indexOf("No Value(")<0)throw assistantError;nativeNoValue=true;}
   check(nativeNoValue,"actual assistant original NoValue branch remains for unmanaged missing end: "+assistantSite+":"+assistantCase.key);
   if("eventId" in assistantEvent)assistantEvent.eventId=91;else assistantEvent.id=91;
  }
 }
}
'''
