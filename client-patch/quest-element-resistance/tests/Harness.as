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

    public class Harness extends Sprite {
        private var Q:Class;
        private var checks:Array = [];
        private var loader:Loader;
        private var names:String = "火水雷风光暗";
        private var content:Object = {ElementResistance:function(e:int, s:Number):Object {
            return {index:7, params:[e,s]};
        }};
        private var decimal:Object = {fromFloat:function(n:Number):Number { return Math.round(n*100000); }};
        public function Harness() {
            setTimeout(load, 1);
        }
        private function load():void {
            try {
                var f:FileStream = new FileStream();
                f.open(File.applicationDirectory.resolvePath("helper-library.swf"),FileMode.READ);
                var bytes:ByteArray = new ByteArray(); f.readBytes(bytes); f.close();
                loader = new Loader(); loader.contentLoaderInfo.addEventListener(Event.COMPLETE, loaded);
                var context:LoaderContext = new LoaderContext(false,ApplicationDomain.currentDomain);
                context.allowCodeImport = true; loader.loadBytes(bytes,context);
            } catch (e:*) { finish(e); }
        }
        private function check(ok:Boolean, name:String):void {
            if (!ok) throw new Error(name); checks.push(name);
        }
        private function quest(text:String):Object { return {sub_name:{index:0,params:[text]}}; }
        private function block(tokens:Array):String { return "【属性伤害："+tokens.join(";")+"】"; }
        private function rejects(text:String):Boolean {
            try { Q.parse(text); } catch (e:*) { return true; } return false;
        }
        private function loaded(event:Event):void {
            try {
                Q = ApplicationDomain.currentDomain.getDefinition("cn.rules.QuestElementResistance") as Class;
                var original:Array = [{index:1,params:[250000]}];
                check(Q.apply({}, original, content, decimal) === original, "unconfigured special mode unchanged");
                check(Q.apply(quest("普通关卡"), original, content, decimal) === original, "unconfigured quest unchanged");
                check(Q.apply({sub_name:{index:1,params:[]}}, original, content, decimal) === original, "Option.None unchanged");
                var count:int = 0;
                for (var mask:int=1; mask<64; mask++) {
                    var tokens:Array=[]; var ids:Array=[];
                    for (var i:int=0; i<6; i++) if (mask & (1<<i)) {tokens.push(names.charAt(i)+"=0.1%");ids.push(i+1);}
                    if (mask == 63) {check(rejects(block(tokens)), "six banned elements rejected");continue;}
                    var result:Array=Q.apply(quest("测试关卡 "+block(tokens)), original, content, decimal);
                    check(result !== original && result.length == ids.length+1 && result[0] === original[0], "original conditions preserved mask "+mask);
                    for (i=0; i<ids.length; i++) check(result[i+1].params[0] == ids[i] && result[i+1].params[1] == 99900000,
                        "native element and fixed decimal mapping "+mask+":"+ids[i]);
                    check(original.length==1,"source array unchanged "+mask);
                    count++;
                }
                check(count==62,"all legal nonempty ban subsets exercised");
                var weak:String=block(["火=50%","水=10%","雷=50%","风=10%","光=50%","暗=10%"]);
                check(Q.parse(weak).length==6,"six weak resistances allowed");
                result=Q.apply(quest(weak),[],content,decimal);
                check(result[0].params[1]==100000 && result[1].params[1]==900000,"weak resistance conversion");
                check(Q.parse(block(["火=1%"]))[0].strength==99,"one percent ban threshold");
                check(Q.apply(quest(block(["火=100%"])),[],content,decimal).length==0,"zero resistance omitted");
                var invalid:Array=[block([]),block(["火=0%"]),block(["火=-1%"]),block(["火=101%"]),
                    block(["火=NaN%"]),block(["火=Infinity%"]),block(["火=0.00001%"]),block(["火=0.1%","火=0.1%"]),
                    block(["全=0.1%"]),block(["火=1e-1%"]),"【属性伤害：火=0.1%",block(["火=0.1%"])+block(["水=0.1%"]),
                    block(["火=0.1%","水=0.1%","雷=0.1%","风=0.1%","光=0.1%","暗=0.1%"]),block(["火=0.1%;"] )];
                for each(var bad:String in invalid) {
                    check(rejects(bad),"strict parser rejects "+bad);
                    check(Q.apply(quest(bad),original,content,decimal)===original,"malformed content preserves base conditions");
                }
                var five:String=block(["火=0.1%","水=0.1%","雷=0.1%","风=0.1%","光=0.1%"]);
                var dark:Array=[{index:7,params:[6,9900000]}];
                check(Q.apply(quest(five),dark,content,decimal)===dark,"combined sixth ban rejected atomically");
                var allWeak:Array=[{index:7,params:[0,100000]}];
                check(Q.apply(quest(five),allWeak,content,decimal).length==6,"all-element weak native condition retained");
                result=Q.apply({sub_name:block(["火=0.1%","水=0.1%"])},original,content,decimal);
                check(result.length==3,"plain string subtitle opt-in");
                check(Q.apply(quest(five), original, content, {fromFloat:function(n:Number):Number {throw new Error("factory failure");}})===original,
                    "factory failure cannot leak partial conditions");
                finish(null);
            } catch (e:*) { finish(e); }
        }
        private function finish(error:*):void {
            var root:File=new File(File.applicationDirectory.nativePath).parent;
            var f:FileStream=new FileStream();f.open(root.resolvePath("harness-result.json"),FileMode.WRITE);
            f.writeUTFBytes(JSON.stringify({passed:error==null,checks:checks,error:error==null?null:String(error)})); f.close();
            NativeApplication.nativeApplication.exit(error==null?0:1);
        }
    }
}
