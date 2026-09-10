package {
    import flash.desktop.NativeApplication;
    import flash.display.Sprite;
    import flash.display.Loader;
    import flash.events.Event;
    import flash.filesystem.File;
    import flash.filesystem.FileMode;
    import flash.filesystem.FileStream;
    import flash.system.ApplicationDomain;
    import flash.system.LoaderContext;
    import flash.utils.ByteArray;
    import flash.utils.setTimeout;

    /** Load actual released quest subtitles into the exact APK helper module. */
    public class TowerHarness extends Sprite {
        private var loader:Loader;
        private var results:Array=[];
        public function TowerHarness() { setTimeout(load,1); }
        private function read(name:String):ByteArray {
            var f:FileStream=new FileStream();f.open(File.applicationDirectory.resolvePath(name),FileMode.READ);
            var b:ByteArray=new ByteArray();f.readBytes(b);f.close();return b;
        }
        private function load():void {
            try {
                loader=new Loader();loader.contentLoaderInfo.addEventListener(Event.COMPLETE,loaded);
                var c:LoaderContext=new LoaderContext(false,ApplicationDomain.currentDomain);c.allowCodeImport=true;
                loader.loadBytes(read("helper-library.swf"),c);
            } catch(e:*) {finish(e);}
        }
        private function loaded(e:Event):void {
            try {
                var Q:Class=ApplicationDomain.currentDomain.getDefinition("cn.rules.QuestElementResistance") as Class;
                var rows:Array=JSON.parse(read("tower-fixtures.json").toString()) as Array;
                if(rows.length!=30)throw new Error("Expected all 30 tower rows");
                var content:Object={ElementResistance:function(e:int,s:Number):Object{return {index:7,params:[e,s]};}};
                var decimal:Object={fromFloat:function(n:Number):Number{return Math.round(n*100000);}};
                for each(var row:Object in rows) {
                    var sentinel:Object={index:4,params:[40000]};var original:Array=[sentinel];
                    var actual:Array=Q.apply({sub_name:{index:0,params:[row.subtitle]}},original,content,decimal);
                    if(actual===original || original.length!=1 || actual[0]!==sentinel)
                        throw new Error("Original conditions changed or configuration rejected at "+row.id);
                    var got:Object={};var bans:int=0;
                    for(var i:int=1;i<actual.length;i++) {
                        var x:Object=actual[i];if(x.index!==7)throw new Error("Wrong condition kind");
                        if(got[x.params[0]]!==undefined)throw new Error("Duplicate element");
                        got[x.params[0]]=x.params[1];if(x.params[1]>=9900000)bans++;
                    }
                    var count:int=0;
                    for(var key:String in row.totals) {
                        count++;
                        if(got[key]!==Math.round(Number(row.totals[key])*100000))
                            throw new Error("Resistance value mismatch at "+row.id+":"+key);
                    }
                    if(actual.length!=count+1 || bans<2 || bans>5)throw new Error("Invalid ban count at "+row.id);
                    results.push({id:row.id,bans:bans,conditions:got,original_preserved:true});
                }
                finish(null);
            } catch(err:*) {finish(err);}
        }
        private function finish(error:*):void {
            var root:File=new File(File.applicationDirectory.nativePath).parent;
            var f:FileStream=new FileStream();f.open(root.resolvePath("tower-harness-result.json"),FileMode.WRITE);
            f.writeUTFBytes(JSON.stringify({passed:error==null,error:error==null?null:String(error),rows:results}));f.close();
            NativeApplication.nativeApplication.exit(error==null?0:1);
        }
    }
}
