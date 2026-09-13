package cn.shop {
    import flash.utils.Dictionary;

    /** Static master-data membership only; never caches player state or availability. */
    public final class ShopFirstOpen {
        private static const byTable:Dictionary = new Dictionary(true);

        private static function eventKey(event:Object):String {
            return String(event.index) + ":" + String(event.params[0]);
        }

        public static function productIds(table:Object, event:Object):Array {
            var index:Object = byTable[table];
            // A replaced binary map must not reuse the previous membership.
            if (index == null || index.source !== table.map) {
                var groups:Object = {};
                var ids:Array = table.keys();
                for (var i:int = 0; i < ids.length; ++i) {
                    var id:int = int(ids[i]);
                    var row:Object = table.get(id);
                    var key:String = eventKey(row.event);
                    var group:Array = groups[key] as Array;
                    if (group == null) {
                        group = [];
                        groups[key] = group;
                    }
                    group.push(id);
                }
                index = {source:table.map, groups:groups};
                byTable[table] = index;
            }
            var selected:Array = index.groups[eventKey(event)] as Array;
            return selected == null ? [] : selected;
        }

        private static function hasProductsOrBox(event:Object, shop:Object, time:Number):Boolean {
            if (shop.existsEventItemInQuestEvent(event.getEventId(), time)) return true;
            // haxe.ds.Option.Some has index 0. Preserve box-only events.
            return event.getBoxGachaId().index == 0;
        }

        public static function sideStoryExists(quest:Object, shop:Object, time:Number):Boolean {
            var ids:Array = quest.getSideStoryEventList().getAllEventIds();
            for (var i:int = 0; i < ids.length; ++i) {
                var event:Object = quest.getEvent(ids[i]);
                if (event.isWithinExchangeablePeriod(time) && hasProductsOrBox(event, shop, time)) return true;
            }
            return false;
        }

        public static function shopTopExists(global:Object):Boolean {
            var time:Number = global.getTime();
            var quest:Object = global.getQuestRepository();
            global.getBossBattleRepository();
            if (global.isGameSystemUnlocked("event")) {
                var shop:Object = global.getShopProductRepository();
                if (sideStoryExists(quest, shop, time)) return true;
                var events:Array = quest.getEventsWithinExchangeablePeriod(time);
                for (var i:int = 0; i < events.length; ++i) {
                    if (hasProductsOrBox(events[i], shop, time)) return true;
                }
            }
            return global.getCollectItemEventRepository().getExchangeAvailableCollectItemEvents(time).length > 0;
        }
    }
}
