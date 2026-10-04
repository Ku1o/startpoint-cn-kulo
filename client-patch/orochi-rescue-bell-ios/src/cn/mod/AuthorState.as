package cn.mod {
    import flash.events.TimerEvent;
    import flash.filesystem.File;
    import flash.filesystem.FileMode;
    import flash.filesystem.FileStream;
    import flash.utils.Dictionary;
    import flash.utils.Timer;

    /** Storage outside existing native objects preserves their field offsets. */
    public final class AuthorState {
        private static const gauge:Dictionary = new Dictionary(true);
        private static const damage:Dictionary = new Dictionary(true);
        public static var context:Object;

        // iOS periodic AIR startup-cache cleanup (Android StartupCache parity).
        // The two state fields below intentionally have no explicit
        // initializers: only this class body is linked into the accepted iOS
        // carrier, so the class-creation defaults (false / null) are the
        // linked initial state.
        private static var periodicStarted:Boolean;
        private static var periodicTimer:Timer;

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

        public static function ensurePeriodicCacheCleanup():void {
            if (periodicStarted == true) return;
            periodicStarted = true;
            writePeriodicCacheDiag("stage=scheduled\nperiod_ms=600000\n");
            var timer:Timer = new Timer(600000, 0);
            timer.addEventListener(TimerEvent.TIMER, periodicCacheTick);
            timer.start();
            periodicTimer = timer;
        }

        // Native entry bridge: the register shape mirrors the original
        // GlobalLoading.applyLoad signature so the AOT environment register
        // stays aligned; only the cleanup start runs here.
        public static function ensurePeriodicCacheCleanupBridge(a:Object, b:Object,
                                                                c:Object, d:Object):void {
            cn.mod.AuthorState.ensurePeriodicCacheCleanup();
        }

        private static function periodicCacheTick(event:TimerEvent):void {
            purgePeriodicCache();
        }

        private static function purgePeriodicCache():void {
            var root:File = File.cacheDirectory;
            if (root == null) {
                writePeriodicCacheDiag("stage=error\nphase=cache-directory\n");
                return;
            }
            var app:File = root.resolvePath("app");
            var air:File = root.resolvePath(".AIR");
            var appBefore:Boolean = app.exists;
            var airBefore:Boolean = air.exists;
            var appDone:Boolean = true;
            var airDone:Boolean = true;
            try {
                if (appBefore) app.deleteDirectory(true);
            } catch (appError:Error) {
                appDone = false;
            }
            try {
                if (airBefore) air.deleteDirectory(true);
            } catch (airError:Error) {
                airDone = false;
            }
            writePeriodicCacheDiag("stage=complete\nperiod_ms=600000\n"
                + "dataDir=" + root.nativePath + "\nappPath=" + app.nativePath
                + "\nappExistsBefore=" + appBefore + "\nappDelete=" + appDone
                + "\n.AIRPath=" + air.nativePath + "\n.AIRExistsBefore=" + airBefore
                + "\n.AIRDelete=" + airDone + "\n");
        }

        private static function writePeriodicCacheDiag(record:String):void {
            try {
                var root:File = File.cacheDirectory;
                if (root == null) return;
                var file:File = root.resolvePath("sp-cache-periodic.diag");
                var stream:FileStream = new FileStream();
                stream.open(file, FileMode.WRITE);
                stream.writeUTFBytes(record.length > 4096 ? record.substr(0, 4096) : record);
                stream.close();
            } catch (error:Error) {
            }
        }
    }
}
