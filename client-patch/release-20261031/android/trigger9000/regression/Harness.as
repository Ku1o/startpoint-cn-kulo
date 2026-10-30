package {
 import flash.display.Sprite;
 import flash.filesystem.File;
 import flash.filesystem.FileMode;
 import flash.filesystem.FileStream;
 import flash.desktop.NativeApplication;
 public class Harness extends Sprite {
  private var checks:Array=[];
  private var observations:Array=[];
  private function check(value:Boolean,name:String):void {
   checks.push({name:name,passed:value});
   if(!value) throw new Error(name);
  }
  private function observe(value:Object):void {observations.push(value);}
  public function Harness() {
   var result:Object;
   try {
    // NativeCases is generated only after the actual method/enum contract is read.
    // It invokes grafted production methods; it is not a parser implementation.
    NativeCases.run(check,observe);
    result={passed:true,assertions:checks.length,checks:checks,observations:observations};
   } catch(error:Error) {
    result={passed:false,assertions:checks.length,checks:checks,observations:observations,
     error:String(error),errorID:error.errorID,stack:error.getStackTrace()};
   }
   var file:File=new File(File.applicationDirectory.nativePath).resolvePath("result.json");
   var stream:FileStream=new FileStream();stream.open(file,FileMode.WRITE);
   stream.writeUTFBytes(JSON.stringify(result));stream.close();
   NativeApplication.nativeApplication.exit(result.passed?0:1);
  }
 }
}
