package {
import flash.display.Sprite;import flash.desktop.NativeApplication;import flash.events.InvokeEvent;
import flash.filesystem.File;import flash.filesystem.FileStream;import flash.filesystem.FileMode;
import fixture.CommonHarness;import haxe.ds.Option;
import pinball.common.data.player.PlayerLogic;import pinball.common.data.gacha.GachaLogic;
import pinball.common.data.gacha.GachaPageKind;import pinball.common.time.TimeRange;
import cn.content.ContentOperationsState;
public class GachaEntryHarness extends Sprite {
 private var assertions:int=0;
 private function check(row:Object,id:String,actual:*,expected:*):void {assertions++;row.checks.push({id:id,actual:actual,expected:expected,pass:actual===expected});if(actual!==expected)throw new Error(id+" "+actual+" != "+expected);}
 public function GachaEntryHarness(){NativeApplication.nativeApplication.addEventListener(InvokeEvent.INVOKE,start);}
 private function snapshot(revision:int,visible:Boolean,enter:Object,expired:Boolean=false):Object {
  var actions:Object={visible:{enabled:visible,ends_at_ms:null}};
  if(enter!==null)actions.enter={enabled:Boolean(enter),ends_at_ms:expired?999999:null};
  var defaults:Object={};for each(var name:String in ["visible","enter","claim","exchange"])defaults[name]={closed_keys:[],qualified_rights_keys:[],legacy_keys:[]};
  return {schema_version:2,full_snapshot:true,revision:revision,catalog_digest:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",server_time_ms:1000000,states:[{key:"gacha:100",instance_id:"gacha:100:original",actions:actions}],catalog:[],default_policy:{version:1,explicit_actions_override_defaults:true,actions:defaults}};
 }
 private function start(event:InvokeEvent):void {
  CommonHarness.installHaxeArrayContract();var specs:Array=[
   {id:"gacha100-native-window-ticket",managed:false,ticket:1,now:500,expected:true,expectedPermission:-1,expectedVisible:true},
   {id:"gacha100-native-expired-ticket",managed:false,ticket:1,now:2000,expected:false,expectedPermission:-1,expectedVisible:false},
   {id:"gacha100-managed-open-ticket",managed:true,ticket:1,now:2000,visible:true,enter:true,expected:true,expectedPermission:1,expectedVisible:true},
   {id:"gacha100-managed-open-no-ticket",managed:true,ticket:0,now:2000,visible:true,enter:true,expected:false,expectedPermission:1,expectedVisible:true},
   {id:"gacha100-enter-closed",managed:true,ticket:1,now:500,visible:true,enter:false,expected:false,expectedPermission:0,expectedVisible:true},
   {id:"gacha100-enter-not-qualified-by-default",managed:true,ticket:1,now:500,visible:true,enter:null,expected:false,expectedPermission:0,expectedVisible:true},
   {id:"gacha100-hidden",managed:true,ticket:1,now:500,visible:false,enter:true,expected:false,expectedPermission:1,expectedVisible:false},
   {id:"gacha100-enter-expired",managed:true,ticket:1,now:500,visible:true,enter:true,expired:true,expected:false,expectedPermission:0,expectedVisible:true}
  ];var rows:Array=[];var failed:int=0;var revision:int=0;
  for each(var spec:Object in specs){var row:Object={id:spec.id,checks:[],steps:[],input:spec,expected:spec.expected,input_source:"synthetic boundary inputs; native page-kind 5 and ticket 999012 contract; actual registered SWF executes all availability and operations algorithms"};try {
   if(spec.managed)ContentOperationsState.applySnapshot(snapshot(++revision,Boolean(spec.visible),spec.enter,spec.expired===true));
   var stock:Object={};if(spec.ticket)stock[999012]=int(spec.ticket);
   var player:PlayerLogic=CommonHarness.createPlayer({items:stock,equipments:{},characters:{},userInfo:{},crazyGachaResultList:{}});
   var logic:GachaLogic=new GachaLogic();logic.id=100;
   logic.period=new TimeRange(0,Option.Some(1000));logic.comebackGachaPeriod=Option.None;logic.starsGachaPeriod=Option.None;
   logic.values={is_comeback:false,is_stars_gacha:false,page_kind:new GachaPageKind("CrazyTenTimesTicketOnly",5,null),crazy_ten_times_ticket_item_id:Option.Some(999012),once_ticket_item_id:Option.None,ten_times_ticket_item_id:Option.None,ticket_expiry_time:Option.None};
   row.permission=ContentOperationsState.gachaEnterGate(logic,player,Number(spec.now),false);
   row.visible=logic.isWithinPeriod(player,Number(spec.now),false);
   row.actual=logic.isAvailable(player,Number(spec.now),false);row.ticket_quantity=player.getItemNumber(999012);
   check(row,"actual-enter-permission",int(row.permission),int(spec.expectedPermission));check(row,"actual-visible-period",row.visible,spec.expectedVisible);check(row,"actual-availability",row.actual,spec.expected);
   row.status="passed";
  }catch(error:*){failed++;row.status="failed";row.error=String(error);row.stack=error is Error?error.getStackTrace():null;}rows.push(row);}
  var fs:FileStream=new FileStream();fs.open(new File(String(event.arguments[1])),FileMode.WRITE);fs.writeUTFBytes(JSON.stringify({status:failed?"failed":"passed",failed:failed,assertions:assertions,stage_is_null:stage===null,cases:rows,limits:"Actual GachaLogic methods plus entire unmodified current ContentOperationsState ABC. Master values and operations snapshots are explicit synthetic inputs; no full table parser, screen flow or draw network request."}));fs.close();NativeApplication.nativeApplication.exit(failed?1:0);
 }
}
}
