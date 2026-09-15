package cn.admission {
    import flash.display.DisplayObject;
    import flash.display.Sprite;
    import flash.display.Stage;
    import flash.events.Event;
    import flash.events.MouseEvent;
    import flash.events.TouchEvent;
    import flash.events.IOErrorEvent;
    import flash.events.SecurityErrorEvent;
    import flash.events.TimerEvent;
    import flash.net.URLLoader;
    import flash.net.URLRequest;
    import flash.net.URLRequestHeader;
    import flash.text.TextField;
    import flash.text.TextFormat;
    import flash.utils.ByteArray;
    import flash.utils.Dictionary;
    import flash.utils.Timer;
    import flash.utils.getDefinitionByName;

    /** Lightweight build admission, not hardware attestation. BuildConfig is generated locally. */
    public final class ClientAdmission {
        private static var ticket:String="", expires:Number=0, session:String="";
        private static var pending:Array=[], busy:Boolean=false;
        private static var queues:Dictionary=new Dictionary(true);
        private static var panel:Sprite, stageRef:Stage, retryAction:Function;
        private static const FALLBACK:String="当前客户端版本已停止支持，请到群聊下载新版安装包。";

        public static function beforeQueue(queue:Object, setting:Object, retry:int, started:int):Boolean {
            if(String(setting.basePath).replace(/\/$/, "") != BuildConfig.ORIGIN+"/api/index.php") return true;
            if(queues[queue]) return false;
            if(ticket && expires>new Date().time+60000) { attach(setting);return true; }
            queues[queue]=true;
            ensure(function(ok:Boolean,text:String):void {
                delete queues[queue];
                if(ok)queue.startRequest(setting,retry,started);
                else {queue.clearQueue();show(text,function():void {queue.startRequest(setting,0,0);});}
            });
            return false;
        }
        private static function attach(setting:Object):void {
            var h:Array=setting.headers as Array;if(!h)h=[];
            for(var i:int=h.length-1;i>=0;i--) {
                var name:String=String(h[i].name).toLowerCase();
                if(name=="x-sp-admission")h.splice(i,1);
                else if(name=="x-sp-session")session=String(h[i].value);
            }
            h.push(new URLRequestHeader("X-SP-ADMISSION",ticket));setting.headers=h;
        }
        public static function socket(connection:Object):void {
            if(connection && connection.handshakeCommand)connection.handshakeCommand.sp_admission=ticket;
        }
        public static function inspect(queue:Object,setting:Object,raw:Object):Boolean {
            var result:Object=raw && raw.data_headers?raw.data_headers.client_admission:null;
            if(!result || result.ok!==false)return true;
            ticket="";expires=0;queue.clearQueue();
            show(String(result.message || FALLBACK),function():void {queue.startRequest(setting,0,0);});
            return false;
        }
        /** RemoteUtil normally handles non-success codes before RequestQueue sees the payload. */
        public static function forwardAdmission(raw:Object,success:Function):Boolean {
            var result:Object=raw && raw.data_headers?raw.data_headers.client_admission:null;
            if(!result || result.ok!==false)return true;
            success(raw);return false;
        }
        /** The original login helper owns its loader, callbacks and timeout. */
        public static function load(loader:URLLoader,req:URLRequest):void {
            if(req.url.indexOf(BuildConfig.ORIGIN+"/player-auth/")!==0){loader.load(req);return;}
            ensure(function(ok:Boolean,text:String):void {
                if(!ok){loader.data=JSON.stringify({ok:false,code:"CLIENT_NOT_ALLOWED",message:text});loader.dispatchEvent(new Event(Event.COMPLETE));return;}
                var headers:Array=req.requestHeaders || [];
                headers.push(new URLRequestHeader("X-SP-ADMISSION",ticket));req.requestHeaders=headers;
                var captured:Function=function(e:Event):void {
                    loader.removeEventListener(Event.COMPLETE,captured);
                    try {var data:Object=JSON.parse(String(loader.data));if(data.ok && data.data && data.data.token)session=String(data.data.token);}catch(error:*){}
                };
                loader.addEventListener(Event.COMPLETE,captured,false,1000);
                try {loader.load(req);}catch(error:*){loader.dispatchEvent(new IOErrorEvent(IOErrorEvent.IO_ERROR));}
            });
        }
        private static function ensure(done:Function):void {
            if(ticket && expires>new Date().time+60000){done(true,"");return;}
            if(pending.length>=32){done(false,"连接请求较多，请稍后重试。");return;}
            pending.push(done);if(busy)return;busy=true;
            if(ticket) {
                send("renew",{},function(r:Object):void {
                    if(r.ok){finish(r);return;}
                    // Reconnect by a fresh challenge; account binding follows a successful resume.
                    ticket="";expires=0;handshake();
                });
            } else handshake();
        }
        private static function handshake():void {
            send("challenge",{protocol:1,build:BuildConfig.ID},function(r:Object):void {
                if(!r.ok){finish(r);return;}
                try {
                    var c:Object=r.data;
                    var proof:String=hmac(BuildConfig.KEY,"SP-ADMISSION-1\n"+BuildConfig.ID+"\n"+c.challenge+"\n"+c.nonce);
                    send("prove",{challenge:c.challenge,proof:proof},function(p:Object):void {
                        if(!p.ok || !session){finish(p);return;}
                        // A restarted server has lost admission memory. Rebind through the existing
                        // session-resume API, preserving the account and its save.
                        ticket=String(p.data.token);expires=Number(p.data.expires_at);
                        sendAbsolute(BuildConfig.ORIGIN+"/player-auth/resume",{token:session},function(a:Object):void {
                            if(a.ok && a.data && a.data.token){session=String(a.data.token);finish(p);}
                            else {session="";finish({ok:false,message:a.message || "登录状态已过期，请退出游戏后重新登录。"});}
                        });
                    });
                }catch(error:*){finish({ok:false,message:"客户端校验失败，请退出游戏后重试。"});}
            });
        }
        private static function finish(r:Object):void {
            busy=false;
            if(r.ok){ticket=String(r.data.token);expires=Number(r.data.expires_at);}
            else {ticket="";expires=0;}
            var waiting:Array=pending;pending=[];
            for each(var callback:Function in waiting)callback(r.ok===true,String(r.message || FALLBACK));
        }
        private static function send(path:String,body:Object,done:Function):void {
            sendAbsolute(BuildConfig.ORIGIN+"/client-admission/"+path,body,done);
        }
        private static function sendAbsolute(url:String,body:Object,done:Function):void {
            var req:URLRequest=new URLRequest(url);req.method="POST";req.contentType="application/json";req.data=JSON.stringify(body);
            var headers:Array=[];
            if(ticket)headers.push(new URLRequestHeader("X-SP-ADMISSION",ticket));
            if(session)headers.push(new URLRequestHeader("X-SP-SESSION",session));req.requestHeaders=headers;
            var loader:URLLoader=new URLLoader(), timer:Timer=new Timer(10000,1), complete:Boolean=false;
            function finishRequest(r:Object):void {if(complete)return;complete=true;timer.stop();try{loader.close();}catch(error:*){}done(r);}
            function failure(e:Event):void {finishRequest({ok:false,message:"暂时无法校验客户端，请检查网络后重试。"});}
            loader.addEventListener(Event.COMPLETE,function(e:Event):void {
                try {var r:Object=JSON.parse(String(loader.data));}catch(error:*){failure(e);return;}
                finishRequest(r);
            });
            loader.addEventListener(IOErrorEvent.IO_ERROR,failure);loader.addEventListener(SecurityErrorEvent.SECURITY_ERROR,failure);
            timer.addEventListener(TimerEvent.TIMER_COMPLETE,failure);timer.start();
            try{loader.load(req);}catch(error:*){failure(null);}
        }
        public static function hmac(keyHex:String,message:String):String {
            var inner:ByteArray=new ByteArray(),outer:ByteArray=new ByteArray(),key:ByteArray=new ByteArray();
            for(var i:int=0;i<keyHex.length;i+=2)key.writeByte(parseInt(keyHex.substr(i,2),16));
            for(i=0;i<64;i++){var b:int=i<key.length?key[i]:0;inner.writeByte(b^0x36);outer.writeByte(b^0x5c);}
            inner.writeUTFBytes(message);outer.writeBytes(sha(inner));
            var result:ByteArray=sha(outer),hex:String="";
            for(i=0;i<result.length;i++)hex+=("0"+uint(result[i]).toString(16)).substr(-2);
            return hex;
        }
        private static function sha(bytes:ByteArray):ByteArray {
            var hash:Object=getDefinitionByName("haxe.crypto.Sha256"),type:Object=getDefinitionByName("haxe.io.Bytes");
            bytes.position=0;return hash.make(type.ofData(bytes)).b as ByteArray;
        }
        private static function show(text:String,retry:Function):void {
            try {
                var lib:Object=getDefinitionByName("flash.Lib");stageRef=(lib.current as DisplayObject).stage;
                if(panel && panel.parent)panel.parent.removeChild(panel);
                panel=new Sprite();retryAction=retry;
                panel.graphics.beginFill(0x132C29,0.92);panel.graphics.drawRect(0,0,stageRef.stageWidth,stageRef.stageHeight);panel.graphics.endFill();
                var width:Number=580,left:Number=0,top:Number=0,card:Sprite=new Sprite();
                var scale:Number=Math.min(stageRef.stageWidth*0.90/width,stageRef.stageHeight*0.80/280);
                card.scaleX=card.scaleY=scale;card.x=(stageRef.stageWidth-width*scale)/2;card.y=(stageRef.stageHeight-280*scale)/2;
                card.graphics.beginFill(0xF5FAF8);card.graphics.drawRoundRect(0,0,width,280,24,24);card.graphics.endFill();panel.addChild(card);
                var field:TextField=new TextField();field.embedFonts=true;field.defaultTextFormat=new TextFormat("SY",22,0x294943,false,null,null,null,null,"center");
                field.x=left+24;field.y=top+30;field.width=width-48;field.height=155;field.multiline=true;field.wordWrap=true;field.selectable=false;
                field.text="客户端接入提示\n\n"+text;card.addChild(field);
                var button:Sprite=new Sprite();button.graphics.beginFill(0x20B9AA);button.graphics.drawRoundRect(0,0,width-80,52,12,12);button.graphics.endFill();
                button.x=left+40;button.y=top+205;button.buttonMode=true;
                var label:TextField=new TextField();label.embedFonts=true;label.defaultTextFormat=new TextFormat("SY",21,0xFFFFFF,false,null,null,null,null,"center");label.width=width-80;label.height=42;label.y=10;label.text="重试";label.mouseEnabled=false;button.addChild(label);card.addChild(button);
                button.addEventListener(MouseEvent.CLICK,function(e:MouseEvent):void {e.stopImmediatePropagation();var next:Function=retryAction;stageRef.removeEventListener(Event.ENTER_FRAME,raise);if(panel && panel.parent)panel.parent.removeChild(panel);panel=null;if(next!=null)next();});
                panel.addEventListener(MouseEvent.CLICK,block);panel.addEventListener(MouseEvent.MOUSE_DOWN,block);panel.addEventListener(MouseEvent.MOUSE_UP,block);
                panel.addEventListener(TouchEvent.TOUCH_BEGIN,block);panel.addEventListener(TouchEvent.TOUCH_END,block);
                stageRef.addChild(panel);stageRef.addEventListener(Event.ENTER_FRAME,raise);
            }catch(error:*){}
        }
        private static function block(e:Event):void {e.stopPropagation();}
        private static function raise(e:Event):void {if(panel && panel.parent && stageRef.getChildIndex(panel)!=stageRef.numChildren-1)stageRef.setChildIndex(panel,stageRef.numChildren-1);}
    }
}
