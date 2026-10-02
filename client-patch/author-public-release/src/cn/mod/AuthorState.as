package cn.mod {
    import flash.utils.Dictionary;

    /** Storage outside existing native objects preserves their field offsets. */
    public final class AuthorState {
        private static const gauge:Dictionary = new Dictionary(true);
        private static const damage:Dictionary = new Dictionary(true);
        public static var context:Object;

        public static function getGauge(owner:Object):Array {
            return gauge[owner] as Array;
        }
        public static function setGauge(owner:Object, value:Array):void {
            gauge[owner] = value;
        }
        public static function getDamage(owner:Object):Array {
            return damage[owner] as Array;
        }
        public static function setDamage(owner:Object, value:Array):void {
            damage[owner] = value;
        }
    }
}
