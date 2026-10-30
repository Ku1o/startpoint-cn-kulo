package {
 import flash.display.Sprite;import flash.filesystem.*;import flash.desktop.NativeApplication;
 import pinball.scene.battle.battle.squad.ball.BallImpl;import pinball.scene.battle.battle.squad.member.MemberImpl;
 import pinball.scene.battle.battle._SLv.SLv_Impl_;
 public class Harness extends Sprite {
  private var checks:Array=[];private var observed:Object={};
  private function check(v:Boolean,n:String):void{checks.push({name:n,passed:v});if(!v)throw new Error(n);}
  public function Harness(){var r:Object;try{test();r={passed:true,assertions:checks.length,checks:checks,observed:observed};}catch(e:Error){r={passed:false,assertions:checks.length,checks:checks,error:String(e),errorID:e.errorID,stack:e.getStackTrace(),observed:observed};}var f:FileStream=new FileStream();f.open(new File(File.applicationDirectory.nativePath).resolvePath("result.json"),FileMode.WRITE);f.writeUTFBytes(JSON.stringify(r));f.close();NativeApplication.nativeApplication.exit(r.passed?0:1);}
  private function test():void {
   var f:FileStream=new FileStream();f.open(File.applicationDirectory.resolvePath("mode.txt"),FileMode.READ);var mode:String=f.readUTFBytes(f.bytesAvailable);f.close();
   var m:MemberImpl=new MemberImpl();m.address=NativeInput.address();m.originMemberIndex=2;m.source={clv:37,element:3,characterTags:["fixture"]};
   var ports:Ports=new Ports(m),ball:BallImpl=new BallImpl();ball.squad=ports;ball.zoneManager=ports;ball.body=ports;ball.escapePoint=ports;ball.x=120;ball.y=240;BallImpl.wfxDashPending=null;
   var error:Error=null,value:Boolean=false;try{value=ball.wfxTryDashReplacement(NativeInput.state());}catch(e:Error){error=e;}
   observed={mode:mode,error:error==null?null:String(error),errorID:error==null?null:error.errorID,stack:error==null?null:error.getStackTrace(),applyCalls:m.calls};
   if(mode=="before") {
    check(error is ReferenceError && error.errorID==1069,"sealed old Member missing helper produces exact1069");
    check(error.getStackTrace().indexOf("wfxTryDashReplacement")>=0 && String(error).indexOf("wfxRunDashAction")>=0,"1069 comes from actual original TryDash call site");
    check(m.calls==0 && ports.statsCalls==0,"old missing method executes no skill sink or dash success stats");return;
   }
   check(error==null && value,"actual TryDash caller and new helper return successfully");
   check(m.calls==1,"actual helper reaches applyInstantAbility sink exactly once");
   var args:Array=m.received;observed.args=args;
   check(args.length==10 && args[0]===null,"actual helper retains10 arguments and null target");
   check(args[1].tag=="Instant" && args[1].index==1 && args[1].params[1]===m.address && args[1].params[2]===false,"actual Instant address factory retains member address and flag");
   check(args[1].params[0]==-9001,"native signed pushshort address id is -9001");
   check(args[2].tag=="InvokeSkill" && args[2].index==19 && args[2].params[0]=="" && args[2].params[1]=="fixture_skill" && args[2].params[3]==0,"actual InvokeSkill factory preserves skill and parameters");
   var power:Object=args[2].params[2];check(power.calculateMethod.tag=="LevelScale" && power.calculateMethod.params[0]==1 && power.calculateMethod.params[1]==SLv_Impl_.MAX_SLV,"actual fromSlv/toInt/LevelScale/ctor propagate level1 and MAX_SLV sentinel");
   check(args[3]===false && args[4]===false && args[5]===false && args[6]===1 && args[7]==131072 && args[8]==37 && args[9]==m.getElement(),"actual helper forwards all flags scale origin index CLv and native element");
   check(ports.statsCalls==1 && ports.lastStat==18 && ports.lastDelta==1 && ports.escapeCalls==1,"actual TryDash tail records success and escape gauge reset");
   check(ball.changed.tag=="Escaping" && ports.vx==0 && ports.vy==0 && BallImpl.wfxDashPending[ball][0]===m,"actual TryDash stores pending state and enters escaping with zero velocity ports");
  }
 }
}
