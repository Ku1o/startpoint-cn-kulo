package {
 import flash.filesystem.File;
 import flash.filesystem.FileMode;
 import flash.filesystem.FileStream;
 import flash.utils.getDefinitionByName;
 import pinball.common.data.ability.instant.InstantAbilityTriggerMasterValue;
 public class NativeCases {
  private static function equalValue(a:*,b:*):Boolean {
   if(a===b)return true;if(a==null || b==null)return false;
   if(a is Array || b is Array){if(!(a is Array) || !(b is Array) || a.length!=b.length)return false;for(var i:int=0;i<a.length;i++)if(!equalValue(a[i],b[i]))return false;return true;}
   if(typeof a!="object" || typeof b!="object")return false;
   var ak:Array=[],bk:Array=[];for(var k:String in a)ak.push(k);for(k in b)bk.push(k);ak.sort();bk.sort();if(ak.join("|")!=bk.join("|"))return false;for each(k in ak)if(!equalValue(a[k],b[k]))return false;return true;
  }
  public static function run(check:Function,observe:Function):void {
   var stream:FileStream=new FileStream();
   stream.open(File.applicationDirectory.resolvePath("case.json"),FileMode.READ);
   var config:Object=JSON.parse(stream.readUTFBytes(stream.bytesAvailable));stream.close();
   if(!(config.row is Array) || config.row[25]!=="9000")throw new Error("Pinned actual leader row required");
   var leader:Array=config.row;var frozenRowText:String=JSON.stringify(leader);
   // The second fixture follows the actual leader/ability schema offset. The
   // frozen leader row itself is never spliced, edited or used as scratch state.
   var ability:Array=leader.slice();ability.splice(1,0,"","");
   for each(var spec:Object in [
    {owner:"pinball.master.generated::LeaderAbilityValues",method:"parseAt25",column:25,row:leader},
    {owner:"pinball.master.generated::AbilityValues",method:"parseAt27",column:27,row:ability}
   ]) {
    var parser:Class=getDefinitionByName(spec.owner) as Class;
    var parse:Function=parser[spec.method];
    var original:String=JSON.stringify(spec.row);
    var got:Object=null,error:Error=null;
    try {got=parse(spec.row);} catch(e:Error) {error=e;}
    check(JSON.stringify(spec.row)===original,spec.method+" leaves exact9000 input row unchanged");
    observe({method:spec.method,phase:config.mode,error:error==null?null:String(error),
     nativeCode:error!=null && NativeErrorContract.isClientError(error)?NativeErrorContract.code(error):null,
     stack:error==null?null:error.getStackTrace(),result:got});
    if(config.mode==="before") {
     check(error!=null && NativeErrorContract.isClientError(error) && NativeErrorContract.code(error)===7050,
      spec.method+" before rejects9000 with actual ClientError7050");
    } else if(config.mode==="after") {
     check(error==null && got.index===9000 && got.tag==="WfxCumulativeHpLoss",spec.method+" returns actual9000 enum");
     check(got.params.length===1 && got.params[0].wfxHpScope===int(spec.row[int(spec.column)+1]),spec.method+" preserves exact scope parameter");
    } else throw new Error("Explicit before/after mode required");
    var oldRow:Array=spec.row.slice();oldRow[int(spec.column)]="25";
    var oldEncoded:String=JSON.stringify(oldRow),old:Object=parse(oldRow);
    check(old.tag==="HpLow" && JSON.stringify(oldRow)===oldEncoded,spec.method+" native25 remains HpLow and does not mutate row");
    if(config.mode==="after") {
     // Expected parameters are produced by the complete original parser path,
     // not by a reimplemented numeric model or inert enum factory.
     var actual:Object=JSON.parse(JSON.stringify(got.params[0]));
     delete actual.wfxHpScope;
     check(equalValue(actual,JSON.parse(JSON.stringify(old.params[0]))),spec.method+"9000 preserves all original HpLow parsed parameters");
    }
    for each(var legacy:String in ["0","1"]) {
     var row:Array=spec.row.slice();row[int(spec.column)]=legacy;
     var encoded:String=JSON.stringify(row),value:Object=parse(row);
     check(value.tag===(legacy==="0"?"Initial":"InstantWithoutConditionString") && JSON.stringify(row)===encoded,
      spec.method+" legacy"+legacy+" exact native enum and immutable row");
    }
    var unknown:Array=spec.row.slice();unknown[int(spec.column)]="999999";
    var unknownEncoded:String=JSON.stringify(unknown),bad:Error=null;
    try {parse(unknown);} catch(unknownError:Error) {bad=unknownError;}
    check(bad!=null && NativeErrorContract.isClientError(bad) && NativeErrorContract.code(bad)===7050 && JSON.stringify(unknown)===unknownEncoded,
     spec.method+" unknown kind retains actual7050 and immutable input");
   }
   if(config.mode==="after") {
    var actualParser:Class=getDefinitionByName("pinball.master.generated::LeaderAbilityValues") as Class;
    var master:Object=actualParser.parseAt25(leader);
    var resolved:Object=NativeAPI.resolve(master as InstantAbilityTriggerMasterValue);
    HPNativeCase.run(resolved,check,observe);
    check(JSON.stringify(leader)===frozenRowText,"all native HP/counter consumers preserve frozen input row");
   }
  }
 }
}
