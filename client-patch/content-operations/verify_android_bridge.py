"""Read back the Android candidate and prove bounded method/layout/branch changes."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("content_bridge_model",HERE/"build_bridge.py")
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--work",type=Path,required=True);p.add_argument("--runtime-work",type=Path);p.add_argument("--native-work",type=Path);a=p.parse_args();w=a.work
 r=json.loads((w/"android-bridge-report.json").read_text(encoding="utf-8"))
 old=(w/"baseline-android.swf").read_bytes();new=(w/"content-operations-android.swf").read_bytes()
 assert sha(old)==r["inputSha256"] and sha(new)==r["outputSha256"]
 before=b.sc.parts(w/"baseline-android.swf")[2];after=b.sc.parts(w/"content-operations-android.swf")[2]
 helper=[t for t in after if t[3] and any(t[3].mn_name(i[0])=="cn.content::ContentOperationsState" for i in t[3].instances)]
 assert len(helper)==1
 helper_abc=helper[0][3]
 forbidden_symbols=["attachHomeHistory","attachPassSelector","initHistoricalPass","historicalPassButtonGate","historicalBoxList","pendingPassId","retainedPasses","retainedBoxes","retainedExchanges","requestRetainedPasses","requestRetainedBoxes","requestRetainedExchanges","replaceExchangeList","resumeRefresh","refreshSuccess","refreshError","refreshCancelled","RequestSetting","PlayerIdMode","requestQueue","BlackOut","changeSceneSimply","SceneKind","starling.display","starling.text"]
 helper_strings={value.decode("utf8","replace") for value in helper_abc.strings}
 assert not helper_strings.intersection(forbidden_symbols),sorted(helper_strings.intersection(forbidden_symbols))
 forbidden_hooks=["pinball.scene.home::HomeView/draw|1","pinball.scene.passCard::PassCardScene/initPassCard|1","pinball.scene.passCard::PassCardScene/buttonClicked|1","pinball.common.data.boxGacha::BoxGachaLogic/getBoxesWithinPeriod|1","pinball.context.scene::LogicScene/activityInput|1"]
 assert not set(forbidden_hooks).intersection(row["label"] for row in r["edits"]),"player selection or remote refresh hook remains"
 retained=[t for t in after if t is not helper[0]];assert len(retained)==len(before)
 mainpair=[]
 for left,right in zip(before,retained):
  if left[1]!=right[1]:mainpair.append((left,right))
 assert len(mainpair)==1
 left,right=mainpair[0];original=left[3];actual=right[3]
 assert any(actual.mn_name(i[0])=="pinball.context.global::GlobalLogic" for i in actual.instances)
 changed={row["body"] for row in r["edits"]};assert len(changed)==len(r["edits"])
 for field in ["methods","instances","classes","scripts","metadata"]:assert b.p.freeze(getattr(original,field))==b.p.freeze(getattr(actual,field)),field
 for field in ["ints","uints","doubles","strings","namespaces","ns_sets","multinames"]:
  assert b.p.freeze(getattr(original,field))==b.p.freeze(getattr(actual,field)[:len(getattr(original,field))]),field
 assert all(kind!=22 or uri!=0 for kind,uri in actual.namespaces[len(original.namespaces):]),"new public namespace URI must be a real string"
 assert len(original.bodies)==len(actual.bodies)
 for i,body in enumerate(original.bodies):
  if i not in changed:assert b.p.freeze(body)==b.p.freeze(actual.bodies[i]),i
 original_view=b.view(original);actual_view=b.view(actual)
 grafted={row["label"] for row in r["edits"]}
 for owner,method,bridge,action,kind in b.ADDITIONAL_TARGETS:
  assert owner+"/"+method+"|1" in grafted,(owner,method,"missing native hook")
 classes={actual.mn_name(instance[0]):instance for instance in actual.instances}
 def native_traits(owner):
  result={};current=owner
  while current in classes:
   instance=classes[current]
   for trait in instance[6]:
    result.setdefault(actual.mn_name(trait.name),(current,trait))
   current=actual.mn_name(instance[1])
  return result
 receiver_contracts={
  "pinball.common.data.gacha::GachaLogic":["period","get_onceTicketItemId","get_tenTimesTicketItemId","get_ticketExpiryTime"],
  "pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic":["get_hasCampaignData","startDashExchangeCampaignData"],
  "pinball.common.data.collectItem::CollectItemEventLogic":["id","get_kind"],
  "pinball.common.data.quest.event.scoreAttack::ScoreAttackEventLogic":["eventId","getQuests"],
  "pinball.common.data.quest.event.ranking::RankingEventLogic":["id","getEventId","isWithinPeriod"],
  "pinball.common.data.mission.activeMission::ActiveMissionEventLogic":["id","getPlayablePeriod"],
  "pinball.scene.campaign.specialExchange::SpecialExchangeCampaignScene":["campaignLogic"],
  "pinball.scene.campaign.startDashExchange::StartDashExchangeCampaignView":["view"],
  "pinball.scene.gacha.top.common::GachaSceneViewBase":["basePeek","periodLayout","view"],
  "pinball.ui.component.template::QuestLikeSceneTemplateView":["config"],
 }
 for owner,method,bridge,action,kind in b.ADDITIONAL_TARGETS:
  if bridge=="eventDate":
   traits=native_traits(owner);field="eventPeek" if "eventPeek" in traits else "event"
   receiver_contracts[owner]=[field]
  elif bridge=="rankingPeriodInfo":receiver_contracts[owner]=["event"]
 receiver_abis=[]
 for owner,names in receiver_contracts.items():
  assert owner in classes and classes[owner][2]&1,(owner,"receiver must remain sealed")
  traits=native_traits(owner)
  for name in names:
   assert name in traits,(owner,name,"missing native slot/method")
   declaring,trait=traits[name];mn=actual.multinames[trait.name];namespace=actual.namespaces[mn[1]]
   assert mn[0] in (7,13) and namespace[0]==22 and actual.s(namespace[1])=="",(owner,name,"not a public native trait")
   receiver_abis.append({"class":owner,"member":name,"declaringClass":declaring,"kind":trait.kind})
 template_ctor="pinball.ui.component.template::QuestLikeSceneTemplateView/<ctor>"
 assert template_ctor in grafted
 template_bi,=actual_view.by_label[template_ctor]
 template_method=actual.methods[actual.bodies[template_bi][0]]
 assert [actual.mn_name(t) for t in template_method[1]]==["starling.display::Sprite","Object"],"date config constructor ABI changed"
 helper_view=b.view(helper_abc)
 event_ids=next(label for label in helper_view.by_label if label.endswith("/eventIds|1"))
 event_ids_instructions=helper_view.normalized(helper_view.by_label[event_ids][0])[0]
 assert not any("getDefinitionByName" in str(row) or "catalog" in str(row) for row in event_ids_instructions),"catalog must not manufacture native EventList entries"
 assert 8640000000000000 in helper_abc.doubles,"native concrete-end contract is missing"
 for label,span in [
   ("pinball.scene.campaign.startDashExchange::StartDashExchangeCampaignView/refresh|1",(88,133)),
   ("pinball.scene.campaign.multiSpecialExchange.exchange::MultiSpecialExchangeCampaignExchangeView/refresh|1",(85,106))]:
  edit=next(row for row in r["edits"] if row["label"]==label)
  assert edit["nativeExpressionBypass"]=={"from":span[0],"resume":span[1],"nullPreservesOriginalExpression":True}
  assert "set_text" in str(original_view.normalized(edit["body"])[0][span[1]]),label
 for method,count in [("multipleButtonHandler",6),("goToLink",1)]:
  label="pinball.scene.littleAssistant::LittleAssistantScene/"+method+"|1"
  edit=next(row for row in r["edits"] if row["label"]==label)
  assert edit["nativeComparableEndSites"]==count and len(edit["originalInsertionSpans"])==count*2,label
 native_reload=next(row for row in r["edits"] if row["label"]=="pinball.context::Logic/remoteCommonInput|1")
 assert native_reload["insertion"]==20,"reload hook must follow original crash/attention notifications"
 protected_methods=["pinball.context::Logic/openDateChangedDialog|1","pinball.context::Logic/timeInput|1","pinball.context.scene::LogicScene/gotoTitleScene|1","pinball.context.remote::RemoteUtil$/requestCompleteHandler|1","pinball.context.remote::RequestQueue/requestSuccessHandler|1"]
 for label in protected_methods:
  oi,=original_view.by_label[label];ai,=actual_view.by_label[label]
  assert b.p.freeze(original.bodies[oi])==b.p.freeze(actual.bodies[ai]),label
 for label,indices in original_view.by_label.items():
  if label.startswith("pinball.context.remote::RequestQueue/") or label.startswith("pinball.context.clock::Clock/"):
   oi,=indices;ai,=actual_view.by_label[label]
   assert b.p.freeze(original.bodies[oi])==b.p.freeze(actual.bodies[ai]),label
 assert "活动与卡池配置已更新，请重新登录。" in helper_strings,"reserved server/client reload message differs"
 branches=0;backward=0
 for abc,indices in [(actual,sorted(changed)),(helper[0][3],range(len(helper[0][3].bodies)))]:
  for bi in indices:
   body=abc.bodies[bi];b.p.check_body(body,abc);ins=b.p.asm.decode(body[5]);assert b.p.asm.encode(ins)[0]==body[5]
   for ii,item in enumerate(ins):
    for target in ([item.target] if item.target is not None else [])+([item.default]+item.cases if item.cases is not None else []):
     assert 0<=target<len(ins) and ins[target].op==0x09,(bi,ii,target)
     branches+=1;backward+=target<=ii
 runtime_work=a.runtime_work or w;native_work=a.native_work or w
 runtime=json.loads((runtime_work/"air-runtime-result.json").read_text(encoding="utf-8"));imports=json.loads((runtime_work/"production-runtime-import.json").read_text(encoding="utf-8"))
 assert runtime["passed"] and runtime["sourceSha256"]==r["sourceSha256"] and imports["sourceSwfSha256"]==sha(new)
 assert imports["actualHelperBodies"]==len(helper[0][3].bodies)
 native=json.loads((native_work/"air-native-result.json").read_text(encoding="utf-8"))
 native_imports=json.loads((native_work/"production-native-import.json").read_text(encoding="utf-8"))
 assert native["passed"] and not native["nativeRegressionBaseline"] and native["sourceSha256"]==r["sourceSha256"]
 assert native["sourceSwfSha256"]==sha(new) and native_imports["sourceSwfSha256"]==sha(new)
 native_imported={row["label"] for row in native_imports["methods"]}
 for label in ["pinball.common.data.quest.event.ranking::RankingEventLogic/<ctor>",
               "pinball.common.data.quest.event.advent::AdventEventQuestLogic/isViewable|1",
               "pinball.common.data.quest.common::CommonQuestBase/isEarlierThanPeriodEnd|1",
               "pinball.common.data.collectItem::CollectItemEventLogic/isExchangingAvailable|1",
               "pinball.common.data.collectItem::CollectItemEventLogic/get_startTime|1",
               "pinball.common.data.collectItem::CollectItemEventLogic/get_endTime|1",
               "pinball.common.data.mission.activeMission::ActiveMissionEventLogic/getLotteryPeriod|1",
               "pinball.common.data.quest.event.scoreAttack::ScoreAttackEventLogic/getRemainingTimeUntilNextEvent|1",
               "pinball.scene.event.base::EventQuestSelectBaseScene/getDate|1",
               "pinball.scene.event.ranking.questSelect::RankingEventQuestSelectScene/getEventPeriodInfo|1",
               "pinball.scene.campaign.specialExchange::SpecialExchangeCampaignScene/getDateText|1",
               "pinball.scene.campaign.startDashExchange::StartDashExchangeCampaignView/refresh|1",
               "pinball.scene.campaign.multiSpecialExchange.exchange::MultiSpecialExchangeCampaignExchangeView/refresh|1",
               "pinball.common.data.campaign.startDashExchange::StartDashExchangeCampaignLogic/get_buyEndTime|1",
               "pinball.scene.gacha.top.common::GachaSceneViewBase/setupText|1",
               "pinball.scene.littleAssistant::LittleAssistantScene/multipleButtonHandler|1",
               "pinball.scene.littleAssistant::LittleAssistantScene/goToLink|1",
               "pinball.ui.component.template::QuestLikeSceneTemplateView/<ctor>"]:
  assert label in native_imported,(label,"required native regression body not exercised")
 cases=b.load("content_native_event_cases",HERE/"offline_runtime_test.py").EVENT_CASES
 event_abis=[];classes={actual.mn_name(instance[0]):instance for instance in actual.instances}
 imported={row["label"] for row in imports["methods"]}
 for package,kind,key,field,fixed in cases:
  owner="pinball.common.data.quest.event."+package+"::"+kind+"Logic";instance=classes[owner]
  slots={actual.mn_name(t.name):t for t in instance[6] if t.data[0]=="slot"}
  assert instance[2]&1 and field in slots and actual.mn_name(slots[field].data[2])=="int",owner
  if field=="eventId":assert "id" not in slots,owner
  label=owner+"/getEventId|1";bi,=actual_view.by_label[label];mi=actual.bodies[bi][0]
  assert actual.methods[mi][1]==[] and actual.mn_name(actual.methods[mi][0])=="pinball.common.data.quest.event::EventIdKind",label
  instructions=b.p.asm.decode(actual.bodies[bi][5]);assert instructions[4].op==0x66 and actual.mn_name(instructions[4].args[0])==field,label
  assert label in imported and "pinball.common.data.quest.event::EventIdKind$/"+kind+"|1" in imported,label
  event_abis.append({"class":owner,"key":key,"nativeIdSlot":field,"getterBody":bi,"getterMethod":mi})
 assert "pinball.common.data.quest.event.common::EventLogicBase/isWithinPeriod|1" in imported
 (w/"native-event-accessor-abi.json").write_text(json.dumps(event_abis,indent=2),encoding="utf-8")
 (w/"native-receiver-abi.json").write_text(json.dumps(receiver_abis,indent=2),encoding="utf-8")
 result={"passed":True,"swfSha256":sha(new),"originalMethodBodies":sum(len(t[3].bodies) for t in before if t[3]),"changedOriginalBodies":len(changed),"newHelperBodies":len(helper[0][3].bodies),"physicalBranchTargets":branches,"backwardTargets":backward,"originalClassLayoutsAndUnrelatedBytesPreserved":True,"noPlayerSelectionNetworkOrSceneTransitionSymbols":True,"originalHomeAndManualPassRoutesUnchanged":True,"nativeReloadHookAfterErrorNotifications":True,"nativeDateDialogClockQueueAndTitleBodiesUnchanged":True,"nativeEventAccessorFamilies":len(event_abis),"nativeReceiverMembers":len(receiver_abis),"catalogDoesNotManufactureNativeEntries":True,"nativeContractAssertions":native["assertions"],"nativeImportedBodies":len(native_imported),"airAssertions":runtime["assertions"],"actualProductionImportedBodies":len(imports["methods"]),"packaged":False,"deviceTested":False}
 (w/"android-bridge-verified.json").write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result))
if __name__=="__main__":main()
