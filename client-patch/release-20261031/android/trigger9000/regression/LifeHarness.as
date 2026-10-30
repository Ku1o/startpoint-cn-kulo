package {
 import flash.display.Sprite;import flash.filesystem.*;import flash.desktop.NativeApplication;
 import pinball.master.generated.LeaderAbilityValues;
 public class Harness extends Sprite {
  private var checks:Array=[];private var observations:Array=[];
  private function check(v:Boolean,n:String):void{checks.push({name:n,passed:v});if(!v)throw new Error(n);}
  private function observe(v:Object):void{observations.push(v);}
  public function Harness(){try{var f:FileStream=new FileStream();f.open(File.applicationDirectory.resolvePath("case.json"),FileMode.READ);var c:Object=JSON.parse(f.readUTFBytes(f.bytesAvailable));f.close();var resolved:Object=NativeAPI.resolve(LeaderAbilityValues.parseAt25(c.row));LifecycleCase.start(resolved,check,observe,finish);}catch(e:Error){finish(e);}}
  private function finish(e:Error=null):void{var r:Object={passed:e==null,assertions:checks.length,checks:checks,observations:observations,error:e==null?null:String(e),errorID:e==null?null:e.errorID,stack:e==null?null:e.getStackTrace()};var f:FileStream=new FileStream();f.open(new File(File.applicationDirectory.nativePath).resolvePath("result.json"),FileMode.WRITE);f.writeUTFBytes(JSON.stringify(r));f.close();NativeApplication.nativeApplication.exit(e==null?0:1);}
 }
}
