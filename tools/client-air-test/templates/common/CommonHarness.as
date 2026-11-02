package fixture {
import haxe.IMap;
import haxe.ds.IntMap;
import haxe.ds.Option;
import flash.utils.Dictionary;
import pinball.common.data.player.PlayerLogic;
import pinball.common.data.item.repository.OwnedItemRepository;
import pinball.context.remote.real.RealRemoteService;
import pinball.remote.common.ResponseData;
import pinball.context.HookForSection;
import pinball.context.remote.NewsInterruptFlagSender;
public class CommonHarness {
 public static var events:Array=[];
 public static function clone(v:*):* {return JSON.parse(JSON.stringify(v));}
 public static function map(v:Object):IntMap {var m:IntMap=new IntMap();if(v)for(var key:String in v)m.h[int(key)]=clone(v[key]);return m;}
 public static function objectMap(v:IMap):Object {var o:Object={};for(var key:* in Object(v).h)o[String(key)]=Object(v).h[key];return o;}
 public static function createPlayer(before:Object):PlayerLogic {
  var player:PlayerLogic=new PlayerLogic();
  var data:Object={items:map(before.items),equipments:map(before.equipments),characters:new IntMap(),crazyGachaResultList:map(before.crazyGachaResultList),userInfo:before.userInfo?clone(before.userInfo):{},fundReceiveList:[],lastCrazyGachaDrawResult:[]};
  if(before.characters)for(var key:String in before.characters){var c:Object=clone(before.characters[key]);data.characters.h[int(key)]={id:int(c.characterId===undefined?key:c.characterId),entry_count:0,mana_node_ids:new IntMap(),evolution_level:int(c.evolutionLevel),join_date:0,use_date:0,exp:int(c.exp),stack:int(c.stack),over_limit_step:int(c.overLimitStep),protection:c.protection===true,bond_token_list:[],mana_board_index:1,illustration_settings:Option.None,ex_boost:c.exBoost?Option.Some({status_id:c.exBoost.statusId,ability_id_list:c.exBoost.abilityIdList}):Option.None,mana_board_awake:new IntMap()};}
  player.saveData=data;player.itemRepository=new OwnedItemRepository();player.itemRepository.player=player;return player;
 }
 public static function consume(raw:Object,player:PlayerLogic):ResponseData {
  var response:ResponseData=new ResponseData(raw,true);
  var service:RealRemoteService=new RealRemoteService();
  var hook:HookForSection=new HookForSection();var dispatcher:RecordingDispatcher=new RecordingDispatcher();dispatcher.player=player;hook.dispatcher=dispatcher;service.hook=hook;service.newsInterruptFlagSender=new NewsInterruptFlagSender();
  var callbacks:int=0;service.earlySuccessHandler(function(v:ResponseData):void {if(v!==response)throw new Error("response identity changed");callbacks++;events.push({kind:"callback"});},response);
  if(callbacks!==1)throw new Error("expected one early callback, got "+callbacks);
  return response;
 }
 public static function snapshot(player:PlayerLogic):Object {
  var data:Object=player.saveData;var chars:Object={};
  for(var key:* in data.characters.h){var c:Object=data.characters.h[key];var ex:Object=null;if(c.ex_boost && c.ex_boost.index==0){var x:Object=c.ex_boost.params[0];ex={statusId:x.status_id,abilityIdList:x.ability_id_list};}chars[String(key)]={characterId:int(c.id),exp:int(c.exp),stack:int(c.stack),overLimitStep:int(c.over_limit_step),evolutionLevel:int(c.evolution_level),protection:c.protection===true,exBoost:ex};}
  return clone({items:objectMap(data.items),equipments:objectMap(data.equipments),userInfo:data.userInfo,characters:chars,crazyGachaResultList:objectMap(data.crazyGachaResultList)});
 }
 public static function same(a:*,b:*):Boolean {
  if(a===b)return true;if(typeof a!=typeof b || a===null || b===null)return false;if(typeof a!="object")return false;
  if((a is Array)!=(b is Array))return false;if(a is Array && a.length!==b.length)return false;
  var ak:Array=[],bk:Array=[];var key:String;for(key in a)if(a.hasOwnProperty(key))ak.push(key);for(key in b)if(b.hasOwnProperty(key))bk.push(key);ak.sort();bk.sort();if(ak.length!==bk.length)return false;
  for(var i:int=0;i<ak.length;i++)if(ak[i]!==bk[i] || !same(a[ak[i]],b[bk[i]]))return false;return true;
 }
 public static function installHaxeArrayContract():void {
  Array.prototype.iterator=function():Object {var values:Array=this as Array;var at:int=0;return {hasNext:function():Boolean{return at<values.length;},next:function():*{return values[at++];}};};
  Array.prototype.copy=function():Array{return (this as Array).concat();};
  Array.prototype.setPropertyIsEnumerable("iterator",false);Array.prototype.setPropertyIsEnumerable("copy",false);
 }
}}
