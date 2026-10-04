package cn.mod {
    import flash.events.TimerEvent;
    import flash.filesystem.File;
    import flash.filesystem.FileMode;
    import flash.filesystem.FileStream;
    import flash.utils.Timer;

    /**
     * iOS periodic AIR startup-cache cleanup (Android StartupCache parity).
     *
     * The state lives in this dedicated class on purpose.  AIR arm64 lays
     * class-object static slots out by type: 32-bit scalars are placed before
     * reference slots.  Adding a Boolean static to an existing class therefore
     * moves its reference-typed statics, while AOT code linked earlier keeps
     * reading the old offsets.  The 2026-10-04 candidate added the two fields
     * below to cn.mod.AuthorState and every iOS client raised TypeError #1009
     * from cn.mod::AuthorState$/getGauge() on entering a battle.  Importing a
     * whole new class leaves every existing class trait list, and therefore
     * every existing baked slot offset, unchanged.
     *
     * The two state fields intentionally have no explicit initializers: the
     * class-creation defaults (false / null) are the linked initial state.
     */
    public final class CacheCleanupState {
        private static var periodicStarted:Boolean;
        private static var periodicTimer:Timer;

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
            cn.mod.CacheCleanupState.ensurePeriodicCacheCleanup();
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
