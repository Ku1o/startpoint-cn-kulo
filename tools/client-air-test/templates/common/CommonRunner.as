package {
import flash.display.Sprite;
import flash.desktop.NativeApplication;
import flash.events.InvokeEvent;
import flash.filesystem.File;
import flash.filesystem.FileStream;
import flash.filesystem.FileMode;
import fixture.CommonHarness;
import pinball.common.data.player.PlayerLogic;

public class CommonRunner extends Sprite {
 private var builtInCases:Array=JSON.parse(__SYNTHETIC_CASES_JSON__) as Array;
 public function CommonRunner(){CommonHarness.installHaxeArrayContract();NativeApplication.nativeApplication.addEventListener(InvokeEvent.INVOKE,start);}
 private function describe(error:*):Object {
  return {code:error!==null && error!==undefined && Object(error).hasOwnProperty("code")?error.code:(error is Error?Error(error).errorID:0),message:String(error),stack:error is Error?Error(error).getStackTrace():null};
 }
 private function compareState(actual:Object,expected:Object,checks:Array,prefix:String,economicSubset:Boolean=false):void {
  if(expected===null)throw new Error(prefix+" expectedAfter is required");
  var fields:int=0;
  for(var key:String in expected){fields++;if(key=="userInfo" && economicSubset){for(var field:String in expected[key])checks.push({name:prefix+"/userInfo/"+field,pass:CommonHarness.same(actual[key][field],expected[key][field])});}else{checks.push({name:prefix+"/"+key,pass:CommonHarness.same(actual[key],expected[key])});}}
  if(fields==0)throw new Error(prefix+" has no declared state fields");
 }
 private function allPassed(checks:Array):Boolean {for each(var c:Object in checks)if(c.pass!==true)return false;return true;}
 private function runCase(spec:Object):Object {
  var rows:Array=[],checks:Array=[],fatal:Object=null,player:PlayerLogic=null;
  CommonHarness.events=[];
  try {
   if(!(spec.steps is Array) || spec.steps.length==0)throw new Error("Case must declare nonempty steps: "+spec.id);
   if(spec.before===null || spec.before===undefined)throw new Error("Case before state is required: "+spec.id);
   player=CommonHarness.createPlayer(spec.before);
   var stepIds:Object={};
   for each(var step:Object in spec.steps){
    if(!step.id || stepIds.hasOwnProperty(step.id))throw new Error("Missing or duplicate step ID in "+spec.id);
    stepIds[step.id]=true;
    if(!step.hasOwnProperty("response"))throw new Error("Complete step.response is required: "+step.id);
    var observedError:Object=null;var start:int=CommonHarness.events.length;var stepChecks:Array=[];
    try {CommonHarness.consume(step.response,player);}
    catch(error:*){observedError=describe(error);}
    var after:Object=CommonHarness.snapshot(player);var events:Array=CommonHarness.events.slice(start);
    var callbacks:int=0,starts:int=0,ends:int=0,lastStart:int=-1,lastEnd:int=-1,lastCallback:int=-1;
    for(var i:int=0;i<events.length;i++){
     if(events[i].kind=="callback"){callbacks++;lastCallback=i;}
     if(events[i].kind=="common-before"){starts++;lastStart=i;}
     if(events[i].kind=="common-after"){ends++;lastEnd=i;}
    }
    if(step.hasOwnProperty("expectedErrorId")){
     stepChecks.push({name:"expected_error",pass:observedError!==null && observedError.code===step.expectedErrorId});
     stepChecks.push({name:"no_success_dispatch",pass:callbacks==0 && starts==0 && ends==0});
    } else {
     stepChecks.push({name:"no_error",pass:observedError===null});
     stepChecks.push({name:"callback_after_common_update",pass:callbacks==1 && starts==1 && ends==1 && lastStart<lastEnd && lastEnd<lastCallback});
    }
    compareState(after,step.expectedAfter,stepChecks,"state",spec.group=="purchases");
    __BATTLE_NATIVE_RESPONSE__
    rows.push(CommonHarness.clone({id:step.id,status:allPassed(stepChecks)?"passed":"failed",checks:stepChecks,after:after,error:observedError,events:events}));
   }
   checks.push({name:"declared_step_count",pass:rows.length===spec.steps.length});
   compareState(CommonHarness.snapshot(player),spec.expectedAfter,checks,"final",spec.group=="purchases");
  }catch(problem:*){fatal=describe(problem);checks.push({name:"case_contract",pass:false});}
  var pass:Boolean=allPassed(checks) && fatal===null;
  for each(var row:Object in rows)if(row.status!="passed")pass=false;
  return {id:spec.id,group:spec.group,status:pass?"passed":"failed",steps:rows,checks:checks,error:fatal,after:player?CommonHarness.snapshot(player):null,uncoveredFields:spec.group=="purchases" && spec.operation.indexOf("mana.")==0?["user_character_mana_node_list"]:[]};
 }
 private function start(event:InvokeEvent):void {
  var rows:Array=[],excluded:Array=[],excludedSteps:Array=[],failed:int=0,fatal:Object=null,declaredSteps:int=0;
  try {
   var stream:FileStream=new FileStream();stream.open(new File(String(event.arguments[0])),FileMode.READ);
   var inputData:Object=JSON.parse(stream.readUTFBytes(stream.bytesAvailable));stream.close();
   if(inputData.schemaVersion!==2 || !(inputData.cases is Array))throw new Error("Expected schemaVersion 2 and cases[]");
   var cases:Array=inputData.cases.concat(builtInCases);var ids:Object={};
   __BATTLE_NATIVE_RUN__
   var groups:Array=["tutorial","mail","equipment","gacha","crazy","synthetic","battle","purchases"];
   for each(var spec:Object in cases){
    if(!spec.id || ids.hasOwnProperty(spec.id))throw new Error("Missing or duplicate case ID");ids[spec.id]=true;
    if(spec.group=="ex"){excluded.push({id:spec.id,reason:"EX full load/restore requires the ex suite"});continue;}
    if(groups.indexOf(spec.group)<0)throw new Error("Unsupported common case group: "+spec.group);
    var incremental:Array=[];for each(var sourceStep:Object in spec.steps){if(sourceStep.route=="/api/index.php/load"){excludedSteps.push({id:sourceStep.id,reason:"Complete load uses the full-load carrier"});}else{incremental.push(sourceStep);}}
    spec.steps=incremental;
    var row:Object=runCase(spec);rows.push(row);declaredSteps+=spec.steps is Array?spec.steps.length:0;
    if(row.status!="passed")failed++;
   }
  }catch(error:*){fatal=describe(error);failed++;}
  var actualSteps:int=0;for each(var resultRow:Object in rows)actualSteps+=resultRow.steps.length;
  if(actualSteps!=declaredSteps && fatal===null){fatal={message:"Declared and observed step counts differ"};failed++;}
  var result:Object={schemaVersion:2,suite:"common",status:failed?"failed":"passed",failed:failed,caseCount:rows.length,stepCount:actualSteps,declaredStepCount:declaredSteps,cases:rows,excludedCases:excluded,excludedSteps:excludedSteps,fatal:fatal,stage_is_null:stage===null,limits:["Complete application response after MessagePack decoding; Flash HTTP/MessagePack transport is not executed.","Only proof-listed methods are production bytecode; captureResponse, construction/storage/time/ANE and dispatch boundaries remain explicit typed fixtures.","Imported method count is not execution coverage. Complete load and downstream scene persistence are separate suites." __BATTLE_NATIVE_LIMIT__ __PURCHASE_NATIVE_LIMIT__]};
  var output:FileStream=new FileStream();output.open(new File(String(event.arguments[1])),FileMode.WRITE);output.writeUTFBytes(JSON.stringify(result));output.close();NativeApplication.nativeApplication.exit(failed?1:0);
 }
}
}
