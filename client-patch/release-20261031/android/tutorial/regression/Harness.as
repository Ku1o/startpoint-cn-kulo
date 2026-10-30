package {
 import flash.display.Sprite;import flash.filesystem.*;import flash.desktop.NativeApplication;import flash.utils.*;import flash.Boot;
 import cn.content.ContentOperationsState;import pinball.common.data.gacha.*;import pinball.master.generated.TutorialGachaValues;
 import pinball.scene.gacha.top.common.GachaSceneViewBase;import pinball.ui.display.UiDisplayObjectContainer;import fixture.BasePeek;
 public class Harness extends Sprite {
  private var checks:Array=[];
  private function check(v:Boolean,n:String):void{checks.push({name:n,passed:v});if(!v)throw new Error(n);}
  public function Harness(){var result:Object;try{test();result={passed:true,assertions:checks.length,checks:checks};}catch(e:Error){result={passed:false,assertions:checks.length,checks:checks,error:String(e),errorID:e.errorID,stack:e.getStackTrace()};}var f:File=new File(File.applicationDirectory.nativePath).resolvePath("result.json");var s:FileStream=new FileStream();s.open(f,FileMode.WRITE);s.writeUTFBytes(JSON.stringify(result));s.close();NativeApplication.nativeApplication.exit(result.passed?0:1);}
  private function snapshot(id:int,managed:Boolean,end:Object):void{
   ContentOperationsState.applySnapshot({schema_version:2,full_snapshot:true,catalog_digest:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",revision:id,server_time_ms:1893456000000,states:managed?[{key:"gacha:990001",instance_id:"gacha:990001:original",actions:{visible:{enabled:true,ends_at_ms:end,quest_keys:null,mission_keys:null},enter:{enabled:true,ends_at_ms:end,quest_keys:null,mission_keys:null}}}]:[]});
  }
  private function test():void{
   var fs:FileStream=new FileStream();fs.open(File.applicationDirectory.resolvePath("mode.txt"),FileMode.READ);var mode:String=fs.readUTFBytes(fs.bytesAvailable);fs.close();
   var ordinary:GachaLogic=new GachaLogic();ordinary.id=990001;ordinary.values={show_period:true,is_comeback:false,is_stars_gacha:false};
   var tutorial:TutorialGachaLogic=new TutorialGachaLogic(ordinary,new TutorialGachaValues());
   check(!Boot.skip_constructor && tutorial.baseGacha===ordinary && tutorial.featureContent.gachaId==990001,"actual tutorial constructor and feature constructor execute");
   check(!("id" in tutorial) && tutorial.get_showPeriod()===false,"native sealed tutorial has no id and hides period");
   var peek:BasePeek=new BasePeek();peek.gacha=tutorial;var view:GachaSceneViewBase=new GachaSceneViewBase();view.basePeek=peek;view.periodLayout=new UiDisplayObjectContainer();
   var asset:Object={calls:0,getUiStringWithContext:function(k:String,c:Object):String{this.calls++;return k+":"+c.start_date+":"+c.end_date;}};view.view={asset:asset};
   var err:Error=null;try{view.setupText();}catch(e:Error){err=e;}
   if(mode=="before"){
    check(err is ReferenceError && err.errorID==1069,"before setupText reproduces exact ReferenceError1069");
    check(err.getStackTrace().indexOf("gachaDateText")>=0 && err.getStackTrace().indexOf("gachaSharedDates")>=0 && err.getStackTrace().indexOf("setupText")>=0,"before error stack contains complete production chain");
   }else{
    check(err==null,"after actual setupText accepts sealed tutorial");
    check(view.periodLayout.visible===false && view.periodLayout.calls==0 && peek.startCalls==0 && peek.endCalls==0 && asset.calls==0,"tutorial complete native fallback hides period without date reads");
   }
   peek.gacha=ordinary;
   snapshot(101,true,null);view.setupText();check(view.periodLayout.visible && view.periodLayout.text.text=="常驻开放" && asset.calls==0,"managed ordinary permanent pool retains operator label");
   snapshot(102,true,1893558600000);view.setupText();check(view.periodLayout.text.text=="开放至 2030.01/02 12:30" && asset.calls==0,"managed timed pool retains exact operator deadline");
   ordinary.values.show_period=false;view.setupText();check(!view.periodLayout.visible,"ordinary no-date pool stays hidden");
   ordinary.values.show_period=true;ordinary.id=990002;snapshot(103,false,null);view.setupText();check(view.periodLayout.visible && view.periodLayout.text.text=="event_quest_dates:DATE(100):DATE(500)" && asset.calls==1 && peek.startCalls==1 && peek.endCalls==1,"unmanaged ordinary pool executes entire original native date fallback");
  }
 }
}
