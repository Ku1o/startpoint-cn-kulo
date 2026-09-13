package {
    import cn.shop.ShopFirstOpen;
    import flash.desktop.NativeApplication;
    import flash.display.Sprite;
    import flash.filesystem.File;
    import flash.filesystem.FileMode;
    import flash.filesystem.FileStream;

    public final class RuntimeHarness extends Sprite {
        private var checks:int = 0;
        private var completed:Array = [];

        public function RuntimeHarness() {
            var report:Object;
            try {
                var input:FileStream = new FileStream();
                input.open(File.applicationDirectory.resolvePath("fixture.json"), FileMode.READ);
                var fixture:Object = JSON.parse(input.readUTFBytes(input.bytesAvailable));
                input.close();
                var counts:Object = testIndex(fixture.products);
                testAvailability();
                report = {passed:true, checks:checks, cases:completed, counts:counts,
                    runtime:"Desktop AIR, compiled candidate helper", device_tested:false};
            } catch (error:Error) {
                report = {passed:false, error:error.toString(), stack:error.getStackTrace(), checks:checks};
            }
            trace("SHOP_FIRST_OPEN_RESULT " + JSON.stringify(report));
            NativeApplication.nativeApplication.exit(report.passed ? 0 : 1);
        }

        private function check(value:Boolean, label:String):void {
            ++checks;
            if (!value) throw new Error(label);
        }

        private function same(actual:Array, expected:Array, label:String):void {
            check(JSON.stringify(actual) == JSON.stringify(expected), label);
        }

        private function testIndex(products:Array):Object {
            var table:FakeTable = new FakeTable(products);
            var events:Object = {};
            var referenceReads:int = 0;
            var row:Object;
            for each (row in products) events[key(row.event)] = row.event;
            var groupCount:int = 0;
            for each (var event:Object in events) {
                ++groupCount;
                var expected:Array = [];
                for each (row in products) {
                    ++referenceReads;
                    if (key(row.event) == key(event)) expected.push(int(row.id));
                }
                same(ShopFirstOpen.productIds(table, event), expected, "real group " + key(event));
            }
            check(table.keyReads == 1 && table.rowReads == products.length, "one full read per master");
            for each (event in events) ShopFirstOpen.productIds(table, event);
            check(table.keyReads == 1 && table.rowReads == products.length, "warm calls do not rescan");
            same(ShopFirstOpen.productIds(table, {index:7,params:[2147483647]}), [], "unknown group");
            completed.push("8,575 real products: all 157 event groups and order match full scan");

            var scoped:FakeTable = new FakeTable([
                {id:31,event:{index:0,params:[7]},price:99,stock:2},
                {id:12,event:{index:1,params:[7]},price:23,stock:0},
                {id:8,event:{index:0,params:[7]},price:51,stock:3}
            ]);
            var e:Object = {index:0,params:[7]};
            same(ShopFirstOpen.productIds(scoped,e), [31,8], "order and type partition");
            same(ShopFirstOpen.productIds(scoped,{index:1,params:[7]}), [12], "same numeric id other type");
            var selected:Array = ShopFirstOpen.productIds(scoped,e);
            scoped.get(31).stock = 0;
            scoped.get(31).price = 77;
            check(scoped.get(selected[0]).stock == 0 && scoped.get(selected[0]).price == 77,
                "index does not snapshot product state");
            scoped.replace([{id:49,event:e},{id:15,event:{index:1,params:[7]}}]);
            same(ShopFirstOpen.productIds(scoped,e), [49], "same table new binary invalidates index");
            same(ShopFirstOpen.productIds(new FakeTable([{id:17,event:e}]),e), [17], "new master isolated");
            same(ShopFirstOpen.productIds(new FakeTable([]),e), [], "empty master");
            completed.push("type collisions, master replacement, fresh state and empty groups");
            return {products:products.length, groups:groupCount,
                full_scan_reference_row_reads:referenceReads, indexed_cold_row_reads:table.rowReads,
                indexed_warm_extra_row_reads:0, counts_are_not_phone_timing:true};
        }

        private static function key(event:Object):String {
            return String(event.index) + ":" + String(event.params[0]);
        }

        private function testAvailability():void {
            for (var mask:int = 0; mask < 256; ++mask) {
                var side:FakeEvent = new FakeEvent(0,1,100,200,Boolean(mask & 8));
                var ordinary:FakeEvent = new FakeEvent(1,1,100,200,Boolean(mask & 64));
                var shop:FakeShop = new FakeShop();
                shop.offers["0:1"] = {from:100,until:200,enabled:Boolean(mask & 4)};
                shop.offers["1:1"] = {from:100,until:200,enabled:Boolean(mask & 32)};
                if (!(mask & 2)) side.from = 900;
                if (!(mask & 16)) ordinary.from = 900;
                var quest:FakeQuest = new FakeQuest([side],[ordinary]);
                var global:FakeGlobal = new FakeGlobal(quest,shop);
                global.time = 150;
                global.unlocked = Boolean(mask & 1);
                global.collect = Boolean(mask & 128);
                var expected:Boolean = originalTop(global);
                check(ShopFirstOpen.shopTopExists(global) == expected, "top truth table " + mask);
                check(ShopFirstOpen.sideStoryExists(quest,shop,150) == originalSide(quest,shop,150),
                    "side truth table " + mask);
            }
            completed.push("256 combinations: system lock, event periods, products, box-only and collection events");

            side = new FakeEvent(0,20,100,200,false);
            shop = new FakeShop();
            shop.offers["0:20"] = {from:120,until:180,enabled:true};
            quest = new FakeQuest([side],[]);
            global = new FakeGlobal(quest,shop);
            for each (var time:Number in [99,100,119,120,150,180,181,200,201,120]) {
                global.time = time;
                check(ShopFirstOpen.shopTopExists(global) == originalTop(global), "time refresh " + time);
            }
            global.time = 150;
            global.unlocked = false;
            check(!ShopFirstOpen.shopTopExists(global), "system relocked");
            global.unlocked = true;
            check(ShopFirstOpen.shopTopExists(global), "system unlocked again");
            var other:FakeGlobal = new FakeGlobal(quest,new FakeShop());
            other.time = 150;
            check(!ShopFirstOpen.shopTopExists(other), "another player's current availability");
            check(ShopFirstOpen.shopTopExists(global), "first player's result not polluted");
            shop.offers["0:20"].enabled = false;
            check(!ShopFirstOpen.shopTopExists(global), "current product availability re-read");
            side.box = true;
            check(ShopFirstOpen.shopTopExists(global), "box-only activity still available");
            completed.push("period boundaries, reentry, player switch and live availability changes");

            var many:Array = [];
            for (var i:int = 1; i <= 100; ++i) many.push(new FakeEvent(0,i,0,1000,i == 1));
            quest = new FakeQuest(many,[]);
            shop = new FakeShop();
            check(ShopFirstOpen.sideStoryExists(quest,shop,150), "early positive");
            check(quest.eventReads == 1 && shop.reads == 1, "positive stops at first matching event");
            many[0].box = false;
            quest.eventReads = 0; shop.reads = 0;
            check(!ShopFirstOpen.sideStoryExists(quest,shop,150), "all-negative remains negative");
            check(quest.eventReads == 100 && shop.reads == 100, "all negatives checked");
            completed.push("100-event positive short circuit and complete negative scan");
        }

        private static function originalSide(quest:FakeQuest, shop:FakeShop, time:Number):Boolean {
            var all:Array = [];
            for each (var id:Object in quest.getSideStoryEventList().getAllEventIds()) all.push(quest.getEvent(id));
            var selected:Array = [];
            for each (var event:FakeEvent in all) {
                if (event.isWithinExchangeablePeriod(time) &&
                    (shop.existsEventItemInQuestEvent(event.getEventId(),time) || event.getBoxGachaId().index == 0))
                    selected.push(event);
            }
            return selected.length > 0;
        }

        private static function originalTop(global:FakeGlobal):Boolean {
            var quest:FakeQuest = global.quest;
            if (global.unlocked && originalSide(quest,global.shop,global.time)) return true;
            var selected:Array = [];
            if (global.unlocked) {
                for each (var event:FakeEvent in quest.getEventsWithinExchangeablePeriod(global.time)) {
                    if (global.shop.existsEventItemInQuestEvent(event.getEventId(),global.time) ||
                        event.getBoxGachaId().index == 0) selected.push(event);
                }
            }
            return selected.length > 0 || global.collect;
        }
    }

}

    internal final class FakeTable {
        public var map:Object;
        public var keyReads:int = 0;
        public var rowReads:int = 0;
        private var ids:Array;
        private var rows:Object;
        public function FakeTable(values:Array) { replace(values); }
        public function replace(values:Array):void {
            map = {}; ids = []; rows = {};
            for each (var row:Object in values) { ids.push(int(row.id)); rows[int(row.id)] = row; }
        }
        public function keys():Array { ++keyReads; return ids; }
        public function get(id:int):Object { ++rowReads; return rows[id]; }
    }

    internal final class FakeEvent {
        public var id:Object;
        public var from:Number;
        public var until:Number;
        public var box:Boolean;
        public function FakeEvent(kind:int, number:int, start:Number, end:Number, hasBox:Boolean) {
            id = {index:kind,params:[number]}; from = start; until = end; box = hasBox;
        }
        public function getEventId():Object { return id; }
        public function isWithinExchangeablePeriod(time:Number):Boolean { return time >= from && time <= until; }
        public function getBoxGachaId():Object { return {index:box ? 0 : 1}; }
    }

    internal final class FakeQuest {
        public var eventReads:int = 0;
        private var side:Array;
        private var ordinary:Array;
        public function FakeQuest(a:Array,b:Array) { side = a; ordinary = b; }
        public function getSideStoryEventList():Object { return this; }
        public function getAllEventIds():Array {
            var ids:Array = []; for each (var event:FakeEvent in side) ids.push(event.id); return ids;
        }
        public function getEvent(id:Object):Object {
            ++eventReads;
            for each (var event:FakeEvent in side)
                if (event.id.index == id.index && event.id.params[0] == id.params[0]) return event;
            throw new Error("missing fixture event");
        }
        public function getEventsWithinExchangeablePeriod(time:Number):Array {
            var found:Array = [];
            for each (var event:FakeEvent in ordinary) if (event.isWithinExchangeablePeriod(time)) found.push(event);
            return found;
        }
    }

    internal final class FakeShop {
        public var offers:Object = {};
        public var reads:int = 0;
        public function existsEventItemInQuestEvent(id:Object,time:Number):Boolean {
            ++reads;
            var offer:Object = offers[String(id.index) + ":" + String(id.params[0])];
            return offer != null && offer.enabled && time >= offer.from && time <= offer.until;
        }
    }

    internal final class FakeGlobal {
        public var quest:FakeQuest;
        public var shop:FakeShop;
        public var time:Number = 150;
        public var unlocked:Boolean = true;
        public var collect:Boolean = false;
        public function FakeGlobal(q:FakeQuest,s:FakeShop) { quest = q; shop = s; }
        public function getTime():Number { return time; }
        public function getQuestRepository():Object { return quest; }
        public function getBossBattleRepository():Object { return {}; }
        public function getShopProductRepository():Object { return shop; }
        public function isGameSystemUnlocked(name:String):Boolean { return unlocked; }
        public function getCollectItemEventRepository():Object { return this; }
        public function getExchangeAvailableCollectItemEvents(time:Number):Array { return collect ? [{}] : []; }
    }
