package {
    import flash.display.Sprite;
    import flash.desktop.NativeApplication;
    import flash.filesystem.File;
    import flash.filesystem.FileMode;
    import flash.filesystem.FileStream;
    import cn.admission.AdmissionSession;
    public class SessionHarness extends Sprite {
        private var nowMs:Number=0, sent:Array=[], checks:int=0, count:int=0;
        private function check(ok:Boolean,name:String):void {checks++;if(!ok)throw new Error(name);}
        private function send(path:String,body:Object,ticket:String,session:String,done:Function):void {sent.push({path:path,body:body,ticket:ticket,session:session,done:done});}
        private function issued(token:String="ticket-A"):Object {return {ok:true,data:{token:token,expires_in_ms:1800000,renew_after_ms:1500000}};}
        private function reply(path:String,r:Object):void {check(sent.length>0,"request exists");var p:Object=sent.shift();check(p.path==path,"expected "+path);p.done(r);}
        public function SessionHarness() {
            var output:Object;
            try {run();output={passed:true,assertions:checks};}catch(e:*){output={passed:false,assertions:checks,error:String(e)};}
            var f:FileStream=new FileStream();f.open(new File(File.applicationDirectory.nativePath).resolvePath("session-results.json"),FileMode.WRITE);f.writeUTFBytes(JSON.stringify(output));f.close();
            NativeApplication.nativeApplication.exit(output.passed?0:1);
        }
        private function run():void {
            var s:AdmissionSession=new AdmissionSession(send,function():Number{return nowMs;});
            s.observe("account-A");
            s.ensure(function(r:Object):void {check(r.ok,"first waiter succeeds");count++;});
            s.ensure(function(r:Object):void {check(r.ok,"second waiter succeeds");count++;});
            check(sent.length==1 && s.busy,"concurrent demand shares handshake");
            nowMs+=400;reply("handshake",issued());
            check(sent[0].body.token=="account-A" && sent[0].ticket=="ticket-A","fresh grant binds existing account");
            reply("resume",{ok:true,data:{token:"account-A"}});
            check(count==2 && s.usable() && !s.busy,"all waiters complete after binding");
            s.ensure(function(r:Object):void {check(r.ok,"fast path");});check(sent.length==0,"no redundant handshake");
            nowMs=1501000;s.background();check(sent.length==1,"background renewal occurs before expiry");
            reply("renew",{ok:false,action:"retry",message:"network failure"});
            check(s.token=="ticket-A" && s.usable(),"transient failure preserves valid grant");
            s.background();check(sent.length==0,"background backoff");
            nowMs+=10001;s.background();reply("renew",issued());check(s.token=="ticket-A","renewal keeps ticket");
            nowMs+=1800001;s.ensure(function(r:Object):void {check(r.ok,"expired grant recovers");});
            reply("renew",{ok:false,action:"handshake"});reply("handshake",issued("ticket-B"));reply("resume",{ok:true,data:{token:"account-A"}});
            check(s.token=="ticket-B" && s.usable(),"restart performs handshake and resume");
            s.ensure(function(r:Object):void {check(!r.ok && r.action=="update","revocation reported");},true);
            reply("renew",{ok:false,action:"update",message:"get update from group"});
            check(s.token=="" && !s.usable(),"revoked ticket cleared");s.background();check(sent.length==0,"no revoked background loop");
            s.allowRetry();s.ensure(function(r:Object):void {check(r.ok,"reenabled build recovers");});
            reply("handshake",issued("ticket-C"));reply("resume",{ok:true,data:{token:"account-A"}});
            s.ensure(function(r:Object):void {check(!r.ok,"account race cannot apply stale response");},true);
            s.observe("account-B");reply("renew",issued("stale-ticket"));check(s.token!="stale-ticket","stale grant ignored");
            nowMs+=10001;s.ensure(function(r:Object):void {check(r.ok,"new login can use unbound grant");},false,false);
            check(sent.length==0,"login is not blocked by old account binding");
            var bad:AdmissionSession=new AdmissionSession(send,function():Number{return nowMs;});
            bad.ensure(function(r:Object):void {check(!r.ok,"malformed success rejected");});reply("handshake",{ok:true,data:{token:"invalid"}});
            check(!bad.usable(),"invalid lifetime is not accepted");
            nowMs+=10001;bad.ensure(function(r:Object):void {check(r.action=="retry","rate limit remains transient");});
            reply("handshake",{ok:false,action:"retry",retry_after_ms:60000});
            nowMs+=30000;bad.ensure(function(r:Object):void {check(!r.ok,"retry before deadline rejected locally");});check(sent.length==0,"server retry delay obeyed");
            nowMs+=30001;bad.ensure(function(r:Object):void {check(r.ok,"retry after deadline");},false,false);reply("handshake",issued());
            check(bad.usable(false),"unbound initial login can proceed");
        }
    }
}
