package {import flash.display.*;import flash.events.*;import flash.net.URLRequest;import flash.filesystem.*;import flash.utils.setTimeout;import flash.desktop.NativeApplication;public class Launcher extends Sprite {
 private function save(name:String,value:Object):void{var s:FileStream=new FileStream();s.open(new File(File.applicationDirectory.nativePath).resolvePath(name),FileMode.WRITE);s.writeUTFBytes(JSON.stringify(value));s.close();}
 public function Launcher(){save("launcher-start.json",{started:true});var l:Loader=new Loader();
 l.uncaughtErrorEvents.addEventListener(UncaughtErrorEvent.UNCAUGHT_ERROR,function(e:UncaughtErrorEvent):void{e.preventDefault();save("result.json",{passed:false,launcher:true,error:String(e.error),stack:e.error is Error?Error(e.error).getStackTrace():null});NativeApplication.nativeApplication.exit(1);});
 l.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR,function(e:IOErrorEvent):void{save("result.json",{passed:false,ioerror:e.text});NativeApplication.nativeApplication.exit(1);});
 setTimeout(function():void{save("result.json",{passed:false,timeout:true});NativeApplication.nativeApplication.exit(1);},5000);
 addChild(l);l.load(new URLRequest(File.applicationDirectory.resolvePath("Harness.swf").url));}}
}
