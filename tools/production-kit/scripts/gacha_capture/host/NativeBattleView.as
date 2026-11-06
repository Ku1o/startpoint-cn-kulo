package {
  import flash.display.BitmapData;
  import flash.display.Sprite;
  import flash.geom.Point;
  import flash.geom.Rectangle;
  import flash.utils.getDefinitionByName;
  import flash.utils.getQualifiedClassName;
  import flash.utils.setTimeout;

  public final class NativeBattleView {
    private static const WIDTH:int = 1080;
    private static const HEIGHT:int = 1920;
    private static const CONTENT_WIDTH:int = 1440;
    private static const CONTENT_TOP:int = 60;
    private static const CONTENT_HEIGHT:int = 1560;
    private static const SIDE_MARGIN:int = (CONTENT_WIDTH - WIDTH) / 2;
    private static const FILE_READER:String = "pinball.asset.file.FileReader";

    public static function prepare(ctx:Object, reader:Object, host:Sprite, starling:Object):Object {
      if (ctx == null || reader == null || host == null || starling == null || starling.root == null ||
          starling.context == null || starling.stage.stageWidth !== WIDTH || starling.stage.stageHeight !== HEIGHT) {
        throw new Error("Native battle view requires the ready 1080×1920 Starling host and local FileReader");
      }

      var hook:Object = ctx.hook;
      if (hook == null) {
        var Hook:Class = nativeClass("pinball.context.Hook");
        hook = new Hook();
      }
      var Screen:Class = nativeClass("pinball.context.screenSize.ScreenSizeSection");
      var Type:Object = nativeClass("Type");
      // Native ScreenSizeSection's Android constructor unconditionally calls ScreenAne.
      // The real typed object supplies the standard non-cutout desktop fields instead.
      var screen:Object = Type.createEmptyInstance(Screen);
      screen.screenWidth = WIDTH;
      screen.screenHeight = HEIGHT;
      screen.screenOffsetX = 0;
      screen.screenOffsetY = 0;
      screen.orientX = 0;
      screen.orientY = 0;
      screen.scale = 1;
      screen.safeAreaTopMargin = 0;
      screen.safeAreaBottomMargin = 0;
      screen.canShowPlatformStatusBar = false;
      var Option:Object = nativeClass("haxe.ds.Option");
      screen.forceCutoutInsets = Option.Some({left: 0, top: 0, right: 0, bottom: 0});
      ctx.status.screenHorizontalMargin = 0;
      ctx.status.screenVerticalMargin = 0;
      ctx.status.safeAreaTopMargin = 0;
      ctx.status.safeAreaBottomMargin = 0;

      var GearHolder:Class = nativeClass("jp.sipo.gipo.core.GearHolderImpl");
      var localOwner:Object = new GearHolder();
      var localGear:Object = getGear(localOwner);
      localGear.otherDiffuse(reader, nativeClass(FILE_READER));
      ctx.gear.addChild(localOwner, position("prepare"));
      var Sound:Class = nativeClass("pinball.sound.production.ProductionSoundSection");
      var sound:Object = localGear.addChild(new Sound(), position("prepare"));
      sound.changeGlobalVolume(0, 0, 0);
      ctx.nativePreviewSound = sound;

      var Production:Class = nativeClass("pinball.productionView.ProductionView");
      var production:Object = new Production(false);
      var viewGear:Object = getGear(production);
      // Use the scene's installed Hook when present. In a view-only probe, the
      // typed local Hook need not enter the tree because no input is dispatched.
      if (ctx.hook == null) {
        viewGear.otherDiffuse(hook, nativeClass("pinball.context.HookForSection"));
      }
      viewGear.otherDiffuse(screen, nativeClass("pinball.context.screenSize.ScreenSizeForSection"));
      viewGear.otherDiffuse(sound, nativeClass("pinball.sound.SoundSectionForView"));
      production.setContext(host);
      localGear.addChild(production, position("prepare"));
      if (getQualifiedClassName(production.asset) !== "pinball.asset.view::ViewAssetContainer") {
        throw new Error("ProductionView failed to prepare its native view asset container");
      }

      // The original rootCreated handler registers blend modes and attaches the
      // production layers to Starling.stage. The host already owns the GPU context.
      var blendModes:Object = nativeClass("flatomo.animation.parts.BlendModeTools");
      blendModes.registerCustomBlendMode();
      production.starlingManager.myStarling = starling;
      production.starlingManager.setupDisplayList();
      return {
        production: production, gear: viewGear, starling: starling, owner: localOwner,
        sound: sound, hook: hook, dev: ctx.dev, global: ctx.global,
        scratch: new BitmapData(WIDTH, HEIGHT, false, 0), packed: false,
        phases: []
      };
    }

    public static function loadGroup(view:Object, preview:Object, isCommon:Boolean):Object {
      var kind:Object = isCommon ? preview.commonKind : preview.kind;
      var builder:Object = isCommon ? preview.commonBuilder : preview.builder;
      var parents:Array = isCommon ? [] : preview.parents;
      if (isCommon ? view.commonLoad != null : view.commonLoad == null || !view.commonLoad.get_completed() || view.partLoad != null) {
        throw new Error("Native view asset groups must load once in common/part order");
      }
      var textures:Object = view.production.addAssetToGroup(kind, builder, parents);
      var sounds:Object = view.sound.addAssetToGroup(kind, builder, parents);
      var progress:Object = {
        textures: textures, sounds: sounds,
        get_completed: function():Boolean {
          return textures.get_completed() && sounds.get_completed();
        }
      };
      if (isCommon) {
        view.commonLoad = progress;
      } else {
        view.partLoad = progress;
      }
      return progress;
    }

    public static function pack(view:Object, gachaId:int, onDone:Function):void {
      if (view.partLoad == null || !view.partLoad.get_completed() || view.packing || view.dev.disableTexturePacking) {
        throw new Error("Native texture packing requires completed view groups and enabled texture packing");
      }
      var RootDispatcher:Class = nativeClass("pinball.context.input.RootHookDispatcherImpl");
      var sink:Object = new RootDispatcher(view.hook);
      sink.stop();
      var ChildEntrance:Class = nativeClass("pinball.context.input.HookEntranceChild");
      var Input:Object = nativeClass("pinball.loading.battle.BattleStartViewInput");
      var Command:Object = nativeClass("pinball.context.SectionCommand");
      var entrance:Object = new ChildEntrance(sink, function(input:Object):Object {
        if (input !== Input.Complete || view.packed) {
          throw new Error("Unexpected native battle texture packing notification");
        }
        view.packed = true;
        view.phases.push("BattleStartViewInput.Complete");
        setTimeout(onDone, 0);
        // The genuine stopped root dispatcher consumes this without Hook/Logic dispatch.
        return Command.BattleStartView(input);
      });
      view.packing = true;
      view.production.startBattleTexturePacking(entrance, gachaId);
    }

    public static function attach(view:Object, preview:Object, scene:Object):Object {
      if (!view.packed || view.scene != null ||
          getQualifiedClassName(scene) !== "pinball.scene.battle::SkillPreviewBattle") {
        throw new Error("Native preview view requires one prepared battle scene after texture packing");
      }
      var safe:Rectangle = view.global.getSafeArea() as Rectangle;
      if (safe.x !== 0 || safe.y !== 0 || safe.width !== WIDTH || safe.height !== HEIGHT) {
        throw new Error("Unexpected safe area for the standard native capture");
      }
      var NativeView:Class = nativeClass("pinball.scene.battle.view.SkillPreviewBattleView");
      var binding:Object = preview.info.clip;
      var clip:Rectangle = new Rectangle(binding.left - SIDE_MARGIN, binding.top, CONTENT_WIDTH, CONTENT_HEIGHT);
      var nativeView:Object = view.gear.addChild(new NativeView(scene, clip, new Point(SIDE_MARGIN, 0)), position("attach"));
      scene.setViewOrder(nativeView);

      var Layer:Class = nativeClass("starling.display.Sprite");
      var Quad:Class = nativeClass("starling.display.Quad");
      var viewport:Object = new Layer();
      viewport.y = CONTENT_TOP;
      viewport.touchable = false;
      var content:Object = new Layer();
      content.x = -SIDE_MARGIN;
      var fade:Object = new Quad(CONTENT_WIDTH, CONTENT_HEIGHT, 0xe2e2e2);
      fade.alpha = 1;
      var mask:Object = new Quad(WIDTH, CONTENT_HEIGHT, 0xffffff);
      content.addChild(nativeView.starlingLayer);
      content.addChild(fade);
      viewport.addChild(content);
      viewport.addChild(mask);
      viewport.mask = mask;
      view.production.starlingSceneLayer.addChild(viewport);
      nativeView.activateView();
      view.scene = scene;
      view.nativeView = nativeView;
      view.viewport = viewport;
      view.fade = fade;
      view.phases.push("SkillPreviewBattleView.activateView");
      return nativeView;
    }

    public static function draw(view:Object, tick:int, previousState:Object):void {
      if (view.nativeView == null || previousState == null) {
        throw new Error("Native view draw requires the pre-update SkillPreviewState");
      }
      // GachaFeatureDisplayLogic.updateSkillPreviewMovie uses state before the
      // simulation step. The native Holder then applies 1 - imageFadeRate.
      var fade:Number = 1;
      if (previousState.index === 1) {
        var params:Array = previousState.params;
        var current:int = params[0];
        var start:int = params[1];
        var end:int = params[2];
        if (current - 8 < start) {
          fade = 1 - (current - start) / 8;
        } else if (current + 6 > end) {
          fade = 1 - (end - current) / 6;
        } else {
          fade = 0;
        }
      }
      view.fade.alpha = fade;
      view.nativeView.skillPreviewDraw(tick);
    }

    public static function capture(view:Object):BitmapData {
      if (view.nativeView == null) {
        throw new Error("The native battle view must be active before capture");
      }
      // Production layers are children of Starling.stage, outside the host root.
      var full:BitmapData = view.starling.stage.drawToBitmapData(view.scratch) as BitmapData;
      if (full == null || full.width !== WIDTH || full.height !== HEIGHT) {
        throw new Error("Native final compositor did not return a standard-size frame");
      }
      var cropped:BitmapData = new BitmapData(WIDTH, CONTENT_HEIGHT, false, 0);
      cropped.copyPixels(full, new Rectangle(0, CONTENT_TOP, WIDTH, CONTENT_HEIGHT), new Point());
      return cropped;
    }

    private static function getGear(holder:Object):Object {
      return holder.gearOutside().getImplement();
    }

    private static function nativeClass(name:String):Class {
      return getDefinitionByName(name) as Class;
    }

    private static function position(method:String):Object {
      return {fileName: "NativeBattleView.as", lineNumber: 0, className: "NativeBattleView", methodName: method};
    }
  }
}
