package cn.diagnostics {
    import flash.display.DisplayObject;
    import flash.display.Sprite;
    import flash.events.MouseEvent;
    import flash.events.TimerEvent;
    import flash.filesystem.File;
    import flash.filesystem.FileMode;
    import flash.filesystem.FileStream;
    import flash.net.URLRequest;
    import flash.net.navigateToURL;
    import flash.system.Capabilities;
    import flash.system.System;
    import flash.text.TextField;
    import flash.text.TextFormat;
    import flash.utils.Dictionary;
    import flash.utils.Timer;
    import flash.utils.getTimer;

    /** Bounded loading checkpoints only; no packet, account or save serialization. */
    public final class LoadingTrace {
        public static const BUILD:String = "CN-LOAD-20260913-r6";
        private static var directory:File;
        private static var current:File;
        private static var active:Boolean = false;
        private static var recording:Boolean = false;
        private static var session:String = "";
        private static var serial:uint = 0;
        private static var seq:uint = 0;
        private static var estimatedBytes:uint = 0;
        private static var dropped:uint = 0;
        private static var ioTotal:int = 0;
        private static var ioMax:int = 0;
        private static var memoryCost:int = 0;
        private static var serializeCost:int = 0;
        private static var fileCost:int = 0;
        private static var memoryAt:int = 0;
        private static var sampledAir:Number = 0;
        private static var sampledPrivate:Number = 0;
        private static var lastSample:int = 0;
        private static var timer:Timer;
        private static var ids:Dictionary;
        private static var nextId:uint = 0;
        private static var button:Sprite;

        private static function getv(o:Object, name:String):* {
            try { return o == null ? null : o[name]; } catch (e:*) { return null; }
        }
        private static function scalar(v:*):* {
            return v is Number || v is Boolean ? v : null;
        }
        private static function enumInfo(v:Object):Object {
            if (v == null) return null;
            var result:Object = {index:scalar(getv(v,"index")), ids:[]};
            var args:Array = getv(v,"params") as Array;
            if (args != null) for (var i:int=0; i<Math.min(3,args.length); i++) result.ids.push(scalar(args[i]));
            return result;
        }
        private static function count(v:*):* { return v is Array ? v.length : null; }
        private static function init():void {
            if (directory != null) return;
            var folder:File=File.applicationStorageDirectory.resolvePath("cn-loading-diagnostics");
            folder.createDirectory();directory=folder;
            current = directory.resolvePath("latest.jsonl");
            var probe:FileStream=new FileStream();
            try {
                probe.open(directory.resolvePath("runtime.json"),FileMode.WRITE);
                probe.writeUTFBytes(JSON.stringify({build:BUILD,os:Capabilities.os,runtime:Capabilities.version,epochMs:new Date().time}));
            } catch(ignored:*) {} finally {try{probe.close();}catch(ignoredClose:*){}}
        }
        private static function read(f:File):String {
            var stream:FileStream = new FileStream();
            try {
                if (!f.exists || f.size > 160000) return "";
                stream.open(f,FileMode.READ);
                return stream.readUTFBytes(stream.bytesAvailable);
            } finally { try { stream.close(); } catch(e:*) {} }
            return "";
        }
        private static function replaceCopy(source:File, target:File):void {
            var next:File = target.parent.resolvePath(target.name+".tmp");
            source.copyTo(next,true);
            next.moveTo(target,true);
        }
        public static function begin(task:Object):void {
            try {
                init();
                if (timer != null) timer.stop();
                // Preserve an unfinished attempt before truncating the latest file.
                // Missing completion is evidence of interruption, not proof of a crash.
                var old:String = read(current);
                if (old.length > 0) {
                    replaceCopy(current,directory.resolvePath("previous.jsonl"));
                    if (old.indexOf('"phase":"session.complete"') < 0 && old.indexOf('"phase":"session.cancel"') < 0)
                        replaceCopy(current,directory.resolvePath("last-unfinished.jsonl"));
                }
                var stream:FileStream = new FileStream();
                try { stream.open(current,FileMode.WRITE); } finally { try { stream.close(); } catch(ignored:*) {} }
                session = String(new Date().time)+"-"+(++serial);
                seq=0;estimatedBytes=0;dropped=0;ioTotal=0;ioMax=0;nextId=0;
                memoryCost=0;serializeCost=0;fileCost=0;memoryAt=0;
                ids=new Dictionary(true);active=true;
                if(button!=null)button.visible=false;
                var config:Object=getv(task,"config");
                emit("session.begin","point",{build:BUILD,os:Capabilities.os,runtime:Capabilities.version,
                    quest:enumInfo(getv(config,"questId")),mates:count(getv(task,"mates")),
                    selectedPartyId:scalar(getv(task,"selectedPartyId"))},true);
                if(timer==null) {timer=new Timer(2000);timer.addEventListener(TimerEvent.TIMER,sample);}
                lastSample=getTimer();timer.start();
            } catch(e:*) {active=false;if(timer!=null)timer.stop();}
        }
        private static function sample(e:TimerEvent):void {
            if(!active)return;
            var now:int=getTimer();
            emit("sample","point",{callbackGapMs:now-lastSample},false);lastSample=now;
        }
        public static function mark(phase:String,edge:String,subject:Object=null,detail:Object=null):void {
            if(!active || recording)return;
            try {
                var data:Object={};
                if(subject!=null) {
                    if(ids[subject]==null)ids[subject]=++nextId;
                    data.objectId=ids[subject];
                }
                if(phase=="rect.pack") {
                    data.pending=count(getv(subject,"pendingRectangles"));
                    data.free=count(getv(subject,"freeRectangles"));
                    data.maxWidth=scalar(getv(subject,"maxWidth"));data.maxHeight=scalar(getv(subject,"maxHeight"));
                } else if(phase=="atlas.draw" || phase=="atlas.allocate") {
                    var texture:Object=getv(subject,"renderTexture");
                    data.width=scalar(getv(texture,"width"));data.height=scalar(getv(texture,"height"));
                } else if(phase=="atlas.layer") {
                    // Layer labels are generated by the client, never player names.
                    if(detail is String && /^layer[01]_[A-Za-z0-9_\-]+$/.test(String(detail)))data.layer=String(detail).substr(0,96);
                } else if(phase=="local.child")data.child=scalar(detail);
                emit(phase,edge,data,false);
            } catch(e:*) {}
        }
        private static function emit(phase:String,edge:String,data:Object,force:Boolean):void {
            if(!active || recording)return;
            if(!force && (seq>=400 || estimatedBytes>=120000)) {dropped++;return;}
            recording=true;
            var started:int=getTimer();
            var stream:FileStream=new FileStream();
            var memoryBefore:int=memoryCost;
            var serializeBefore:int=serializeCost;
            var fileBefore:int=fileCost;
            var fileStarted:int=-1;
            try {
                // Private-memory queries can be expensive. Keep timestamps on reused samples;
                // every phase checkpoint is still appended immediately for interruption analysis.
                if(force || started-memoryAt>=2000) {
                    var memoryStarted:int=getTimer();
                    sampledAir=System.totalMemoryNumber;sampledPrivate=System.privateMemory;
                    memoryAt=started;memoryCost+=getTimer()-memoryStarted;
                }
                var row:Object={session:session,seq:seq++,epochMs:new Date().time,ms:started,
                    phase:phase,edge:edge,airBytes:sampledAir,privateBytes:sampledPrivate,
                    memorySampleMs:memoryAt,memorySampleAgeMs:started-memoryAt,
                    memoryTotalBeforeMs:memoryBefore,serializeTotalBeforeMs:serializeBefore,fileTotalBeforeMs:fileBefore,
                    ioTotalBeforeMs:ioTotal,ioMaxBeforeMs:ioMax,dropped:dropped,data:data};
                var serializeStarted:int=getTimer();
                var line:String=JSON.stringify(row)+"\n";
                serializeCost+=getTimer()-serializeStarted;
                fileStarted=getTimer();
                stream.open(current,FileMode.APPEND);stream.writeUTFBytes(line);
                estimatedBytes=stream.position;
            } catch(e:*) {dropped++;}
            finally {
                try{stream.close();}catch(ignored:*){}
                if(fileStarted>=0)fileCost+=getTimer()-fileStarted;
                var cost:int=getTimer()-started;ioTotal+=cost;ioMax=Math.max(ioMax,cost);recording=false;
            }
        }
        public static function collectGarbage():void {
            mark("gc","begin");
            try {System.gc();} finally {mark("gc","end");}
        }
        public static function firstFrame():void {
            if(!active)return;
            emit("session.complete","point",{reached:"first_playing_update_returned"},true);
            active=false;if(timer!=null)timer.stop();ids=null;
        }
        public static function cancel():void {
            if(!active)return;
            emit("session.cancel","point",{reason:"battle_scene_left_before_first_update"},true);
            active=false;if(timer!=null)timer.stop();ids=null;
        }
        public static function hideEntry():void {if(button!=null)button.visible=false;}
        public static function install(root:DisplayObject):void {
            try {
                init();
                if(root==null || root.stage==null)return;
                if(button==null) {
                    button=new Sprite();button.name="cn-loading-diagnostic-button";
                    button.graphics.beginFill(0x235e75,0.95);button.graphics.drawRoundRect(0,0,132,40,10);button.graphics.endFill();
                    var label:TextField=new TextField();label.defaultTextFormat=new TextFormat("SY",18,0xffffff,true);
                    label.embedFonts=true;label.text="诊断日志";label.width=132;label.height=34;label.y=5;
                    label.mouseEnabled=false;button.addChild(label);button.buttonMode=true;
                    button.addEventListener(MouseEvent.CLICK,openReport);
                }
                if(button.parent!=root.stage)root.stage.addChild(button);
                var scale:Number=Math.max(0.6,root.stage.stageWidth/540);
                button.scaleX=button.scaleY=scale;
                button.x=root.stage.stageWidth-140*scale;button.y=96*scale;button.visible=true;
            } catch(e:*) {}
        }
        private static function openReport(e:MouseEvent):void {
            e.stopImmediatePropagation();
            try {navigateToURL(new URLRequest("sp-loading-diag://report"),"_self");}catch(ignored:*){}
        }
    }
}
