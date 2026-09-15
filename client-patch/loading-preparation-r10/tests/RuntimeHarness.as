package {
    import cn.loading.PartyDerivedCache;
    import flash.desktop.NativeApplication;
    import flash.display.Sprite;
    import flash.events.TimerEvent;
    import flash.filesystem.File;
    import flash.filesystem.FileMode;
    import flash.filesystem.FileStream;
    import flash.utils.Timer;
    import flash.utils.Dictionary;
    import haxe.ds.IntMap;
    import haxe.ds.StringMap;

    public final class RuntimeHarness extends Sprite {
        private var assertions:int = 0;
        private var asyncTimer:Timer;
        private var asyncParty:FakeParty;
        private var ticks:int = 0;
        private function complete(report:Object):void {
            var stream:FileStream = new FileStream();
            stream.open(new File(File.applicationDirectory.nativePath).resolvePath("runtime-tests.json"),FileMode.WRITE);
            stream.writeUTFBytes(JSON.stringify(report)); stream.close();
            NativeApplication.nativeApplication.exit(report.passed ? 0 : 1);
        }
        private function check(value:Boolean, label:String):void {
            assertions++;
            if (!value) throw new Error(label);
        }
        private function group(id:int = 1003001, round:int = 0):Object {
            return new TestEnum("Multi",1,[new TestEnum("BothBoss",4,[id,
                new TestEnum("Some",0,[[{viewerId:123,questIds:[new TestEnum("Normal",0,[17]),new TestEnum("Normal",0,[18])]}]]),round])]);
        }
        public function RuntimeHarness() {
            try { synchronous(); startAsync(); }
            catch (error:*) { complete({passed:false,assertions:assertions,error:String(error)}); }
        }
        private function synchronous():void {
            var values:Object = {characters:[{id:1,level:100},{id:2,level:99},{id:3,level:98}],equipment:[{id:7,level:5}]};
            var assets:Object = {};
            var a:FakeParty = new FakeParty(values,assets);
            var b:FakeParty = new FakeParty(values,assets);
            PartyDerivedCache.begin();
            var first:Array = PartyDerivedCache.get(a,group(),[8000101],true);
            for (var i:int=0;i<12;i++) check(PartyDerivedCache.get(b,group(),[8000101],true) === first,"semantic enum cache reuse " + i);
            check(a.calls == 3 && b.calls == 0,"one calculation per occupied character");
            check(PartyDerivedCache.metrics().hits == 12,"hit metrics");
            check(PartyDerivedCache.get(b,group(1003002),[8000101],true) !== first,"quest isolation");
            check(PartyDerivedCache.get(b,group(1003001,1),[8000101],true) !== first,"round isolation");
            var nested:Object = group(); nested.params[0].params[1].params[0][0].questIds[1].params[0] = 19;
            check(PartyDerivedCache.get(b,nested,[8000101],true) !== first,"full nested quest-list isolation");
            check(PartyDerivedCache.get(b,group(),[8000102],true) !== first,"debug values isolation");
            check(PartyDerivedCache.get(b,group(),[8000101],false) !== first,"ability flag isolation");
            check(PartyDerivedCache.get(new FakeParty(values,{}),group(),[8000101],true) !== first,"asset-container isolation");
            check(PartyDerivedCache.get(new FakeParty(JSON.parse(JSON.stringify(values)),assets),group(),[8000101],true) !== first,"party source identity isolation");
            values.equipment[0].level = 6;
            check(PartyDerivedCache.get(a,group(),[8000101],true) !== first,"in-place equipment mutation invalidates");
            PartyDerivedCache.finish();
            check(PartyDerivedCache.get(a,group(),[8000101],true) !== first,"finish releases old entries");
            PartyDerivedCache.begin();
            var second:Array = PartyDerivedCache.get(a,group(),[],true);
            PartyDerivedCache.begin();
            check(PartyDerivedCache.get(a,group(),[],true) !== second,"new load never reuses prior load");
            var cycle:Object = {}; cycle.self = cycle;
            var c:FakeParty = new FakeParty(cycle,assets);
            check(PartyDerivedCache.get(c,group(),[],true) !== PartyDerivedCache.get(c,group(),[],true),"cyclic key bypasses cache");
            PartyDerivedCache.begin();
            a = new FakeParty(values,assets);
            PartyDerivedCache.enqueue(a,group(),[],true);
            PartyDerivedCache.enqueue(new FakeParty(values,assets),group(),[],true);
            check(a.calls == 0,"queue does not calculate synchronously");
            check(PartyDerivedCache.metrics().queuedParties == 1,"semantic queue deduplication");
            check(PartyDerivedCache.runOne() && a.calls == 1,"first batch calculates one character");
            check(PartyDerivedCache.runOne() && a.calls == 2,"second batch calculates one character");
            check(!PartyDerivedCache.runOne() && a.calls == 3,"third batch completes");
            var warmed:Array = PartyDerivedCache.get(a,group(),[],true);
            check(a.calls == 3,"completed warm-up is a cache hit");
            var expected:Array = PartyDerivedCache.get(new FakeParty(values,{}),group(),[],true);
            check(JSON.stringify(warmed) == JSON.stringify(expected),"cold and warm outputs identical including five callback arguments");
            PartyDerivedCache.begin();
            a = new FakeParty(values,assets); a.emptySlot = 1;
            PartyDerivedCache.enqueue(a,group(),[],true);
            while(PartyDerivedCache.runOne()) {}
            warmed = PartyDerivedCache.get(a,group(),[],true);
            check(a.calls == 2 && warmed[1].index == 1 && warmed[2].params[0].slot == 2,"empty slots and positions preserved");
            PartyDerivedCache.begin();
            a = new FakeParty(values,assets);
            PartyDerivedCache.enqueue(a,group(),[],true);
            PartyDerivedCache.runOne();
            warmed = PartyDerivedCache.get(a,group(),[],true);
            check(warmed[1].params[0] != null && warmed[2].params[0] != null,"unfinished entries never escape");
            PartyDerivedCache.reset();
            check(!PartyDerivedCache.runOne(),"cancel removes pending jobs");
            PartyDerivedCache.begin();
            for(i=0;i<45;i++) PartyDerivedCache.enqueue(new FakeParty({id:i},assets),group(),[],true);
            check(PartyDerivedCache.metrics().queuedParties == 32,"bounded entries");
            PartyDerivedCache.reset();
            PartyDerivedCache.begin();
            var mana:IntMap = new IntMap(); mana.h[1] = 6; mana.h[2] = 5;
            var names:StringMap = new StringMap(); names.h.slot = 1; names.rh = {"$toString":2};
            a = new FakeParty({abilities:mana,other:names},assets);
            first = PartyDerivedCache.get(a,group(),[],true);
            check(first === PartyDerivedCache.get(a,group(),[],true),"real Haxe map container layout hits");
            mana.h[1] = 7;
            second = PartyDerivedCache.get(a,group(),[],true);
            check(first !== second,"mana node dictionary mutation invalidates");
            names.rh["$toString"] = 3;
            check(second !== PartyDerivedCache.get(a,group(),[],true),"reserved string map keys included");
            var mapA:Dictionary = new Dictionary(), mapB:Dictionary = new Dictionary();
            mapA[1] = 11; mapA[2] = 22; mapB[2] = 22; mapB[1] = 11;
            first = PartyDerivedCache.get(a,new TestEnum("Maps",0,[mapA]),[],true);
            check(first === PartyDerivedCache.get(a,new TestEnum("Maps",0,[mapB]),[],true),"dictionary iteration order independent");
            mapB["1"] = 33;
            check(first !== PartyDerivedCache.get(a,new TestEnum("Maps",0,[mapB]),[],true),"string and numeric dictionary keys distinct");
            PartyDerivedCache.reset();
        }
        private function startAsync():void {
            PartyDerivedCache.begin();
            asyncParty = new FakeParty({characters:[1,2,3]},{});
            PartyDerivedCache.enqueue(asyncParty,group(),[],true);
            asyncTimer = new Timer(16);
            asyncTimer.addEventListener(TimerEvent.TIMER,onTick);
            asyncTimer.start();
        }
        private function onTick(event:TimerEvent):void {
            try {
                ticks++;
                var remaining:Boolean = PartyDerivedCache.runOne();
                check(asyncParty.calls == ticks,"one character per separate timer callback");
                if (remaining) return;
                asyncTimer.stop();
                check(ticks == 3,"three timer turns");
                var report:Object = {passed:true, assertions:assertions, timerTurns:ticks, metrics:PartyDerivedCache.metrics()};
                PartyDerivedCache.finish();
                trace("R10_TEST_RESULT " + JSON.stringify(report));
                complete(report);
            } catch(error:*) { complete({passed:false,assertions:assertions,error:String(error)}); }
        }
    }
}
internal final class TestEnum {
    public const __enum__:Boolean = true;
    public var tag:String;
    public var index:int;
    public var params:Array;
    public function TestEnum(tag:String,index:int,params:Array) { this.tag=tag; this.index=index; this.params=params; }
}
internal final class FakeParty {
    public var values:Object;
    public var logicAssets:Object;
    public var calls:int = 0;
    public var emptySlot:int = -1;
    public function FakeParty(values:Object,assets:Object) { this.values=values; logicAssets=assets; }
    public function _getUnitedCharactersWithQuestId(callback:Function,group:Object,debug:Array,enable:Boolean):Array {
        var result:Array = [];
        for(var i:int=0;i<3;i++) result.push(i == emptySlot ? new TestEnum("None",1,null) :
            new TestEnum("Some",0,[callback({id:10+i},i,group,debug,enable)]));
        return result;
    }
    public function _createCalculatedBattleCharacterLogic(character:Object,slot:int,group:Object,debug:Array,enable:Boolean):Object {
        calls++;
        return {character:character.id,slot:slot,quest:JSON.stringify(group),debug:debug.concat(),enabled:enable};
    }
}
