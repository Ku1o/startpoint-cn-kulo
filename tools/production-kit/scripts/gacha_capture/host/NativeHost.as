package {
  import flash.display.MovieClip;
  import flash.display.BitmapData;
  import flash.display.PNGEncoderOptions;
  import flash.geom.Rectangle;
  import flash.utils.ByteArray;
  import flash.utils.setTimeout;
  import flash.events.Event;
  import flash.events.InvokeEvent;
  import flash.events.UncaughtErrorEvent;
  import flash.filesystem.File;
  import flash.filesystem.FileMode;
  import flash.filesystem.FileStream;
  import flash.desktop.NativeApplication;
  import flash.utils.getDefinitionByName;
  import flash.utils.describeType;
  public class NativeHost extends MovieClip {
    private var result:Object={stage:'native-graphics',classes:[],nativeMainCalled:false,battleStarted:false};
    private var output:File;
    private var starling:Object;
    public function NativeHost(){
      trace('NativeHost constructor');
      loaderInfo.uncaughtErrorEvents.addEventListener(UncaughtErrorEvent.UNCAUGHT_ERROR,function(e:UncaughtErrorEvent):void{
        e.preventDefault();result.passed=false;result.error=String(e.error);if(e.error is Error)result.stack=Error(e.error).getStackTrace();finish(2);
      });
      NativeApplication.nativeApplication.addEventListener(InvokeEvent.INVOKE,function(e:InvokeEvent):void{output=new File(String(e.arguments[0]));result.stage='native-battle';run()});
    }
    private function run():void{
      try{
        checkpoint('invoked');
        var names:Array=['flash.Boot','flash.Lib','haxe.ds.Option','starling.core.Starling','jp.sipo.gipo.core.GearHolderImpl','pinball.context.Logic','pinball.config.core.DevConfig','pinball.asset.file.FileReader'];
        for each(var name:String in names){
          checkpoint('loading '+name);
          var c:Object=getDefinitionByName(name);
          result.classes.push({name:name,loaded:true,type:describeType(c).toXMLString()});
        }
        var Lib:Object=getDefinitionByName('flash.Lib');Lib.current=this;
        var Boot:Class=getDefinitionByName('boot_ffc6') as Class;
        checkpoint('native static init');var boot:Object=new Boot();
        result.optionNoneAvailable=getDefinitionByName('haxe.ds.Option').None!==null;
        checkpoint('native static init complete');
        var ctx:Object=BattleBootstrap.prepare(output,result);
        var reader:Object=ResourceProbe.run(output,result,ctx.fixture);
        ctx.reader=reader;
        BattleBootstrap.attachAssets(ctx,reader);
        waitForMaster(ctx,BattleBootstrap.loadOfficialMasters(ctx),0);
      }catch(e:Error){result.passed=false;result.error=e.toString();result.stack=e.getStackTrace();finish(1);}
    }
    private function waitForMaster(ctx:Object,progress:Object,count:int):void{
      try{
        if(!progress.get_completed()){
          if(count>=200)throw new Error('Native leading master did not complete');
          setTimeout(function():void{waitForMaster(ctx,progress,count+1)},25);return;
        }
        BattleBootstrap.verifyMasterAndQuest(ctx,result);
        var preview:Object=BattleBootstrap.createOfficialPreview(ctx,result);
        startNativeGraphics(function():void{loadLogic(ctx,preview,true)});
      }catch(e:Error){result.passed=false;result.error=e.toString();result.stack=e.getStackTrace();finish(1);}
    }
    private function loadLogic(ctx:Object,preview:Object,isCommon:Boolean):void{
      awaitProgress(BattleBootstrap.loadPreviewLeading(ctx,preview,isCommon),function():void{
        var following:Object=BattleBootstrap.resolvePreviewLeading(ctx,isCommon,result);
        awaitProgress(following,function():void{
          BattleBootstrap.resolvePreviewFollowing(ctx,isCommon,result);
          if(isCommon){loadLogic(ctx,preview,false);return;}
          loadView(ctx,preview);
        });
      });
    }
    private function loadView(ctx:Object,preview:Object):void{
      BattleBootstrap.attachPreviewHook(ctx);
      result.viewPhase='prepare';
      var view:Object=NativeBattleView.prepare(ctx,ctx.reader,this,starling);
      view.maxCaptureUpdates=int(ctx.state.loadedNativeReplay.endFrame)-int(ctx.state.loadedNativeReplay.startFrame)+120;
      if(view.maxCaptureUpdates<120||view.maxCaptureUpdates>1800)throw new Error('Unexpected native replay recording window');
      result.viewPhase='common-assets';
      awaitProgress(NativeBattleView.loadGroup(view,preview,true),function():void{
        result.viewPhase='part-assets';
        awaitProgress(NativeBattleView.loadGroup(view,preview,false),function():void{
          result.viewPhase='texture-packing';
          NativeBattleView.pack(view,preview.poolId,function():void{
            try{
              result.viewPhase='attach-battle-view';
              var scene:Object=BattleBootstrap.attachPreviewScene(ctx,preview,result);
              NativeBattleView.attach(view,preview,scene);
              result.battlePrepared=true;
              result.nativeFrames=[];
              scene.startPreview();result.battleStarted=true;
              result.viewPhase='record-native-battle';
              recordFrame(view,scene,0);
            }catch(e:Error){result.passed=false;result.error=e.toString();result.stack=e.getStackTrace();finish(1);}
          });
        });
      });
    }
    private function recordFrame(view:Object,scene:Object,tick:int):void{
      try{
        var previous:Object=scene.skillPreviewState;
        scene.update();
        NativeBattleView.draw(view,tick,previous);
        result.nativeFrames.push(NativeFrameTrace.sample(scene,tick));
        var bitmap:BitmapData=NativeBattleView.capture(view);
        var bytes:ByteArray=bitmap.encode(bitmap.rect,new PNGEncoderOptions());
        var frameDir:File=output.resolvePath('frames');if(!frameDir.exists)frameDir.createDirectory();
        var s:FileStream=new FileStream();s.open(frameDir.resolvePath(('0000'+tick).substr(-4)+'.png'),FileMode.WRITE);s.writeBytes(bytes);s.close();bitmap.dispose();
        if(scene.skillPreviewState.tag==='Finish'){result.viewPhase='native-finished';result.passed=true;finish(0);return;}
        if(tick>=view.maxCaptureUpdates)throw new Error('Native preview did not finish within its declared recording window');
        setTimeout(function():void{recordFrame(view,scene,tick+1)},0);
      }catch(e:Error){result.passed=false;result.error=e.toString();result.stack=e.getStackTrace();finish(1);}
    }
    private function startNativeGraphics(next:Function):void{
      var St:Class=getDefinitionByName('starling.core.Starling') as Class;
      var Root:Class=getDefinitionByName('starling.display.Sprite') as Class;
      starling=new St(Root,stage,new Rectangle(0,0,1080,1920),null,'auto','baselineExtended');
      starling.addEventListener('rootCreated',function(e:Object):void{
        try{
          result.driver=starling.context.driverInfo;
          result.nativeGraphicsReady=true;
          next();
        }catch(ex:Error){result.passed=false;result.error=ex.toString();result.stack=ex.getStackTrace();finish(1);}
      });
      starling.start();
    }
    private function awaitProgress(progress:Object,next:Function,count:int=0):void{
      try{
        if(!progress.get_completed()){
          if(count>=400)throw new Error('Native resource progress did not complete: '+result.battleBootstrap.phase);
          setTimeout(function():void{awaitProgress(progress,next,count+1)},25);return;
        }
        next();
      }catch(e:Error){result.passed=false;result.error=e.toString();result.stack=e.getStackTrace();finish(1);}
    }
    private function checkpoint(value:String):void{
      var s:FileStream=new FileStream();s.open(output.resolvePath('host-progress.txt'),FileMode.APPEND);s.writeUTFBytes(value+'\n');s.close();
    }
    private function finish(code:int):void{
      var f:File=output.resolvePath('host-result.json');
      var s:FileStream=new FileStream();s.open(f,FileMode.WRITE);s.writeUTFBytes(JSON.stringify(result,null,2));s.close();
      NativeApplication.nativeApplication.exit(code);
    }
  }
}
