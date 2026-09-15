package cn.probe {
    import flash.display.DisplayObject;
    import flash.events.UncaughtErrorEvent;
    import flash.filesystem.File;
    import flash.filesystem.FileMode;
    import flash.filesystem.FileStream;
    import flash.utils.getDefinitionByName;
    import flash.utils.getTimer;
    import flash.utils.setTimeout;
    /** Temporary device test only; omitted from both delivered APKs. */
    public final class StartupProbe {
        private static var seen:int=0;
        public static function mark():void {write("boot constructor entered");}
        public static function install(root:DisplayObject):void {
            write("after super");
            root.loaderInfo.uncaughtErrorEvents.addEventListener(UncaughtErrorEvent.UNCAUGHT_ERROR,function(e:UncaughtErrorEvent):void {
                if(seen++>=8)return;
                var error:Error=e.error as Error;
                write("uncaught "+String(e.error)+(error?"\n"+error.getStackTrace():""));
            });
            try {
                var result:Object=getDefinitionByName("RecordHarness").run(File.applicationStorageDirectory.resolvePath("record-fixture-"+new Date().time));
                write("record tests "+JSON.stringify(result));
            } catch(error:*) {write("RECORD TEST FAILED "+error);}
            setTimeout(function():void {write("5s stage children="+root.stage.numChildren+" context="+root.stage.stage3Ds[0].context3D);},5000);
        }
        private static function write(text:String):void {
            var stream:FileStream=new FileStream();
            try {stream.open(File.applicationStorageDirectory.resolvePath("SPRecordTest.log"),FileMode.APPEND);stream.writeUTFBytes(getTimer()+" "+text+"\n");stream.close();}catch(e:*){try{stream.close();}catch(ignore:*){}}
        }
    }
}
