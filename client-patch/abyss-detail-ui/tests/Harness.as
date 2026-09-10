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
        public function Harness() {
            setTimeout(load, 1);
        }
        private function load():void {
            try {
                var f:FileStream = new FileStream();
                f.open(File.applicationDirectory.resolvePath("api-test.swf"),FileMode.READ);
                var bytes:ByteArray = new ByteArray(); f.readBytes(bytes); f.close();
                loader = new Loader(); loader.contentLoaderInfo.addEventListener(Event.COMPLETE, loaded);
                var context:LoaderContext = new LoaderContext(false,ApplicationDomain.currentDomain);
                context.allowCodeImport = true; loader.loadBytes(bytes,context);
            } catch (e:*) { finish(e); }
        }
        private function check(ok:Boolean, name:String):void {
            if (!ok) throw new Error(name); checks.push(name);
        }
        private function loaded(event:Event):void {
            try {
                Q = ApplicationDomain.currentDomain.getDefinition("cn.ui.AbyssDetails") as Class;
                var Parser:Class = ApplicationDomain.currentDomain.getDefinition("pinball.ui.richText.parser.RichTextLayoutParser") as Class;
                var parser:Object = new Parser();
                var input:FileStream = new FileStream();
                input.open(File.applicationDirectory.resolvePath("floor-fixtures.json"), FileMode.READ);
                var fixtures:Array = JSON.parse(input.readUTFBytes(input.bytesAvailable)) as Array; input.close();
                for each (var floor:Object in fixtures) {
                    var quest:Object = {id:700099000 + floor.r, values:{sub_name:{index:0,params:[floor.raw]}}};
                    var before:String = JSON.stringify(quest);
                    var summary:String = Q.summaryForQuest(floor.raw,quest);
                    check(summary.indexOf("封锁：") == 0 && summary.length <= 32, "short summary " + floor.r);
                    var html:String = Q.detailsHtml(floor.raw);
                    var layout:Object = parser.getLayoutData(html);
                    check(layout.html.node.length >= 6, "native rich text parser " + floor.r);
                    check(html.indexOf("属性伤害：") < 0 && html.indexOf("「属性封锁保底」") < 0, "duplicate removal " + floor.r);
                    check(html.indexOf("敌人与血量") >= 0 && html.indexOf("额外领域") >= 0, "detail sections " + floor.r);
                    check(Q.rawSubtitle(quest) == floor.raw && JSON.stringify(quest) == before, "source gameplay data immutable " + floor.r);
                    check(Q.summaryForQuest(floor.raw,{id:700007001}) == floor.raw, "other events unchanged " + floor.r);
                    var Channel:Class = ApplicationDomain.currentDomain.getDefinition("cn.rules.QuestElementResistance") as Class;
                    check(JSON.stringify(Channel.parse(floor.raw)) == JSON.stringify(Channel.parse(
                        floor.raw.replace(/\s*【关卡资料：[^】]*】/g,""))), "original element channel accepts metadata " + floor.r);
                }
                var five:String="【属性伤害：火=0.1%;水=0.1%;风=0.1%;光=0.1%;暗=0.1%】 「PF调校」PF抗性额外-15个百分点";
                check(Q.summaryForQuest(five,{id:700099001}) == "封锁：火·水·风·光·暗　PF -15%", "maximum ban summary");
                var escaped:Object = parser.getLayoutData(Q.detailsHtml("「测试」<tag>&内容"));
                check(escaped.html.node.length > 0, "native parser escaped prose");
                check(Q.detailsHtml("【关卡资料：bad】").indexOf("暂不可用") >= 0, "malformed optional metadata fallback");
                check(Q.summaryForQuest("unchanged", {}) == "unchanged", "quest without public id unchanged");
                testButton(fixtures[0]);
                finish(null);
            } catch (e:*) { finish(e); }
        }
        private function testButton(floor:Object):void {
            var StarlingClass:Class=ApplicationDomain.currentDomain.getDefinition("starling.core.Starling") as Class;
            var SpriteClass:Class=ApplicationDomain.currentDomain.getDefinition("starling.display.Sprite") as Class;
            var testStage:Object=new StarlingClass(SpriteClass,stage);
            // The test library deliberately omits application startup. Initialize
            // only the Gear pools normally initialized by the document class.
            var Gear:Object=ApplicationDomain.currentDomain.getDefinition("jp.sipo.gipo.core.Gear");
            var ListClass:Class=ApplicationDomain.currentDomain.getDefinition("haxe.ds.List") as Class;
            var MapClass:Class=ApplicationDomain.currentDomain.getDefinition("haxe.ds.StringMap") as Class;
            Gear.taskPool=new ListClass();Gear.absorbTargetCache=new MapClass();
            var Log:Object=ApplicationDomain.currentDomain.getDefinition("haxe.Log");
            Log.trace=function(value:Object,pos:Object=null):void {};
            var UiText:Object=ApplicationDomain.currentDomain.getDefinition("pinball.ui.display.text.UiText");
            var texts:Object={};
            for each (var name:String in ["questTitle","questNumber","continue_count"]) {
                texts[name]=UiText.create(480,50,"",null,null);
                var format:Object=texts[name].get_format().clone();format.size=40;
                texts[name].set_format(format);texts[name].x=337;
            }
            texts.questTitle.y=100;texts.questNumber.y=50;texts.continue_count.y=240;
            var children:Array=[],registered:Array=[],handlers:Array=[],opened:Array=[];
            var scene:Object={targetQuest:{id:700099001,values:{sub_name:floor.raw}},
                openDialog:function(dialog:Object):void {opened.push(dialog);}};
            var group:Object={append:function(id:int):void {registered.push(id);},
                addClickHandler:function(handler:Function):void {handlers.push(handler);}};
            var panel:Object={peek:scene,topPanel:{getText:function(id:String,pos:Object):Object {return texts[id];},
                addChild:function(child:Object):void {children.push(child);}},buttonGroupView:{peek:group,
                exists:function(id:int):Boolean {return registered.indexOf(id)>=0;},
                registerDisplayObjectAsButton:function(id:int,display:Object,behavior:Object):void {
                    check(id==Q.BUTTON && display===children[0] && behavior!=null,"native button registration");}}};
            Q.attach(panel);
            check(children.length==1 && children[0].getChildAt(1).get_text()=="关卡详情","native Sprite/Quad/UiText button created");
            check(texts.questNumber.get_autoScale()==false && texts.questNumber.get_format().size==28,"summary fixed readable font");
            check(children[0].x==617 && children[0].y==230,"button in continuation row");
            Q.attach(panel);check(children.length==1 && handlers.length==1,"repeated attach does not duplicate button");
            handlers[0](1);check(opened.length==0,"unrelated clicks unchanged");
            handlers[0](Q.BUTTON);
            check(opened.length==1 && opened[0].titleName=="关卡详情" && opened[0].assetKind.index==1,"native scroll dialog constructed");
            check(opened[0].assetKind.params[0].indexOf("属性封锁")>=0,"dialog receives complete detail text");
            scene.targetQuest.values.sub_name="「最新关卡」新说明";
            handlers[0](Q.BUTTON);check(opened[1].assetKind.params[0].indexOf("最新关卡")>=0,"button reads current floor on each click");
        }
        private function finish(error:*):void {
            var root:File=new File(File.applicationDirectory.nativePath).parent;
            var f:FileStream=new FileStream();f.open(root.resolvePath("harness-result.json"),FileMode.WRITE);
            f.writeUTFBytes(JSON.stringify({passed:error==null,checks:checks,error:error==null?null:String(error),stack:error is Error ? error.getStackTrace() : null})); f.close();
            NativeApplication.nativeApplication.exit(error==null?0:1);
        }
    }
}
