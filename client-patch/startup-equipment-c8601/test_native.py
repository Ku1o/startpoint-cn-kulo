"""Execute selected production bodies on sealed fixtures, including old-code negatives."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'content-operations'))
import offline_runtime_test as suite
import native_runtime_fixtures as native
import assistant_runtime_fixtures as assistant

baseline='--expect-c8601-baseline' in sys.argv
if baseline:sys.argv.remove('--expect-c8601-baseline')
original_prepare=native.prepare
owner='pinball.scene.equipmentList::EquipmentSellableStatusResolver'
native.NATIVE_METHODS[owner]=['reasonToUiString','getPartyCategoryPriority']
native.STORAGE[owner]='public var logicAsset:pinball.asset.logic.ILogicAssetContainer;'

def prepare(stubs,cases,abc,builder):
 stubs,labels,includes=original_prepare(stubs,cases,abc,builder)
 key='pinball/asset/logic/ILogicAssetContainer.as'
 stubs[key]=stubs[key].replace('function getIgnoreQuestPeriod()', 'function getUiString(k:String):String;function getUiStringWithContext(k:String,c:Object):String;function getIgnoreQuestPeriod()')
 key='pinball/asset/logic/LogicAssetContainer.as'
 stubs[key]=stubs[key].replace('{import','{import pinball.error.ClientError;import',1).replace('public var loaded:', 'public function getUiString(k:String):String{if(k==null)throw new ClientError(8601,"missing null UI key");return k;}public function getUiStringWithContext(k:String,c:Object):String{return getUiString(k);}public var loaded:')
 stubs['pinball/common/tools/ComparatorTools.as']='package pinball.common.tools {public class ComparatorTools {public static function comparing(f:Function):Function{return function(a:Object,b:Object):Number{return Number(f(a))-Number(f(b));};}}}'
 stubs['pinball/common/data/item/EquipmentNotSellableReason.as']='package pinball.common.data.item {public class EquipmentNotSellableReason {public var index:int;public var params:Array;public function EquipmentNotSellableReason(i:int,p:Array){index=i;params=p;}}}'
 stubs['pinball/common/data/tutorial/TutorialQuestLogic.as']='package pinball.common.data.tutorial {import pinball.common.data.quest.common.CommonQuestBase;import pinball.error.ClientError;public class TutorialQuestLogic extends CommonQuestBase {public var categoryReads:int=0;override public function get_category():Object{categoryReads++;throw new ClientError(8601,"missing category 9");}}}'
 stubs['pinball/scene/equipmentList/EquipmentSellableStatusResolver.as']='package pinball.scene.equipmentList {import pinball.asset.logic.ILogicAssetContainer;import pinball.common.data.item.EquipmentNotSellableReason;public class EquipmentSellableStatusResolver {public var logicAsset:ILogicAssetContainer;public function reasonToUiString(r:EquipmentNotSellableReason=null):String{return null;}public function getPartyCategoryPriority(c:int=0):int{return 0;}}}'
 includes+=['pinball.common.tools.ComparatorTools','pinball.common.data.item.EquipmentNotSellableReason','pinball.common.data.tutorial.TutorialQuestLogic']
 return stubs,labels,includes
native.prepare=prepare
# Reuse the production importer, with a deliberately scoped current-package
# oracle. The historical page/date matrix is a separate suite.
assistant.BODY=''
native.BODY=r'''
var tutorialType:Class=getDefinitionByName("pinball.common.data.tutorial::TutorialQuestLogic") as Class;
var reasonType:Class=getDefinitionByName("pinball.common.data.item::EquipmentNotSellableReason") as Class;
var resolverType:Class=getDefinitionByName("pinball.scene.equipmentList::EquipmentSellableStatusResolver") as Class;
var tutorial:Object=new tutorialType();
tutorial.period=new TimeRange(0,Option.Some(5000));
var tutorialFailures:int=0;
for each(var tutorialMethod:String in ["isWithinPeriod","isWithinViewablePeriod","isEarlierThanPeriodEnd"]) {
 try {check(tutorial[tutorialMethod](1000)===true,"native tutorial period: "+tutorialMethod);}
 catch(tutorialError:Error) {if(!EXPECT_C8601_BASELINE)throw tutorialError;check(tutorialError.errorID==8601,"old tutorial missing-table negative");tutorialFailures++;}
}
if(EXPECT_C8601_BASELINE)check(tutorialFailures==3,"all three old tutorial routes reproduce C8601");
else {
 check(tutorial.categoryReads==0,"tutorial never reads the ordinary category table");
 tutorial.period=new TimeRange(0,Option.Some(500));
 check(tutorial.isWithinPeriod(1000)===false && tutorial.isEarlierThanPeriodEnd(1000)===false,"native tutorial expiry remains authoritative");
 var restoredTutorial:Object=new tutorialType();restoredTutorial.period=new TimeRange(0,Option.Some(5000));
 check(restoredTutorial.isWithinViewablePeriod(1000)===true && restoredTutorial.categoryReads==0,"recreated tutorial follows the same native path");
}
var resolver:Object=new resolverType();resolver.logicAsset=new (getDefinitionByName("pinball.asset.logic::LogicAssetContainer") as Class)();
var equipmentFailures:int=0;
for each(var category:int in [1,2,3,4,5,6,7]) {
 var occupied:Array=[category];
 var reason:Object=new reasonType(1,[occupied]);
 var expectedKey:String=category==1?"equipment_list_not_sellable_reason_occupied":category==2?"equipment_list_not_sellable_reason_occupied_carnival_event":category==3?"equipment_list_not_sellable_reason_occupied_raid_event":"equipment_list_not_sellable_reason_occupied_rush_event";
 try {check(resolver.reasonToUiString(reason)==expectedKey,"occupied equipment category "+category);}
 catch(equipmentError:Error) {if(!EXPECT_C8601_BASELINE||category<5)throw equipmentError;check(equipmentError.errorID==8601,"old independent equipment null-key negative");equipmentFailures++;}
 check(occupied.length==1 && occupied[0]==category,"saved party category preserved: "+category);
 if(!EXPECT_C8601_BASELINE && category>=4)check(resolver.getPartyCategoryPriority(category)==0,"independent party sorting retains Rush priority: "+category);
}
if(EXPECT_C8601_BASELINE)check(equipmentFailures==3,"all three old independent categories reproduce C8601");
check(resolver.reasonToUiString(new reasonType(2,[]))=="equipment_list_not_sellable_reason_protected","equipment protection reason is preserved");
var unknownFailed:Boolean=false;try{resolver.reasonToUiString(new reasonType(1,[[8]]));}catch(unknownError:Error){unknownFailed=unknownError.errorID==8601;}
check(unknownFailed,"unknown categories still fail instead of being silently normalized");
snap(30000,[row("challenge_dungeon_event:1",true,["3:101"])]);
var ordinary:Object=new (getDefinitionByName("pinball.common.data.quest.common::CommonQuestBase") as Class)();
check(ordinary.isWithinPeriod(1000)===true,"managed ordinary quest remains open");
snap(30001,[row("challenge_dungeon_event:1",false,["3:101"])]);
check(ordinary.isWithinPeriod(1000)===false,"managed ordinary quest closure is retained");
'''.replace('EXPECT_C8601_BASELINE',str(baseline).lower())
if __name__=='__main__':suite.main()
