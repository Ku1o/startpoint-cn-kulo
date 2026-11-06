package {
  import flash.filesystem.File;
  import flash.filesystem.FileMode;
  import flash.filesystem.FileStream;
  import flash.utils.Dictionary;
  import flash.utils.getDefinitionByName;
  import flash.utils.getQualifiedClassName;

  public final class BattleBootstrap {
    private static const MASTER:String = "pinball.master.generated.";
    private static const FIXTURE_TIME:Number = 1704067200000;
    private static const GEAR_ROOT:String = "jp.sipo.gipo.core.GearHolderImpl";
    private static const LOGIC:String = "pinball.context.Logic";
    private static const LOGIC_STATUS:String = "pinball.context.reproduce.LogicStatus";
    private static const GLOBAL_LOGIC:String = "pinball.context.global.GlobalLogic";
    private static const GLOBAL_FOR_SECTION:String = "pinball.context.global.GlobalLogicForSection";
    private static const LOGIC_ASSET:String = "pinball.asset.logic.LogicAssetContainer";
    private static const DEV_CONFIG:String = "pinball.config.core.DevConfig";
    private static const FILE_READER:String = "pinball.asset.file.FileReader";
    private static const OPTION:String = "haxe.ds.Option";

    public static function prepare(output:File, result:Object):Object {
      var state:Object = {
        phase: "construct-native-context",
        fixture: "c8601-isolated-gacha-preview",
        realAccount: false,
        logicGearAttached: false,
        assetGearAttached: false,
        previewHookAttached: false,
        masterVerified: false,
        questVerified: false
      };
      result.battleBootstrap = state;

      var Root:Class = nativeClass(GEAR_ROOT);
      var Logic:Class = nativeClass(LOGIC);
      var Dev:Class = nativeClass(DEV_CONFIG);
      var Hook:Class = nativeClass("pinball.context.Hook");
      var Reproduce:Class = nativeClass("pinball.context.reproduce.AdvancedReproduce");
      var TopKeys:Object = nativeClass("pinball.context.TopDiffuseKey");
      var Option:Object = nativeClass(OPTION);
      var ComplexTime:Class = nativeClass("pinball.context.clock.ComplexTime");
      var root:Object = new Root();
      var logic:Object = new Logic(false);
      var dev:Object = new Dev();
      var hook:Object = new Hook();
      // The preview owns its replay log. Construct this host Hook dependency
      // without running the application's crash recovery or recorder setup.
      var reproduce:Object = new Reproduce(false);
      var status:Object = logic.logicStatus;
      var globalLogic:Object = logic.globalLogic;
      var asset:Object = logic.asset;
      var gear:Object = root.gearOutside().getImplement();

      // The official origin-character factory asks for a player, then uses master data.
      var IntMap:Class = nativeClass("haxe.ds.IntMap");
      var RestoreState:Object = nativeClass("pinball.common.data.save.restore.RestoreState");
      var accountFixture:Object = {
        player: {questProgress: new IntMap()},
        restoreState: RestoreState.None,
        userOption: {number_notation_symbol: false, simple_ability_description: false}
      };
      status.applyLoadedData(accountFixture);
      var MiscStore:Object = nativeClass("pinball.context.localStore._MiscLocalStore.MiscLocalStore_Impl_");
      var ApplicationStore:Object = nativeClass("pinball.context.localStore._ApplicationOptionLocalStore.ApplicationOptionLocalStore_Impl_");
      status.miscData = Option.Some(MiscStore.getDefault());
      status.applicationOption = Option.Some(ApplicationStore.getDefault(dev));
      globalLogic.devConfig = dev;
      status.currentTime = Option.Some(new ComplexTime(FIXTURE_TIME, 0));
      if (status.getLoadedData() !== accountFixture || globalLogic.getLogicAssets() !== asset) {
        throw new Error("Native Logic/LogicStatus fixture identity mismatch");
      }

      var prepared:Boolean = false;
      gear.addPreparationHandler(function(tool:Object):void {
        state.phase = "diffuse-native-context";
        tool.diffuse(logic, Logic);
        tool.diffuse(logic, nativeClass("pinball.context.LogicForHook"));
        tool.diffuse(hook, nativeClass("pinball.context.HookForDispatcher"));
        tool.diffuse(hook, nativeClass("pinball.context.HookForSection"));
        tool.diffuseWithKey(reproduce, TopKeys.ReproduceKey);
        tool.diffuse(status, nativeClass(LOGIC_STATUS));
        tool.diffuse(globalLogic, nativeClass(GLOBAL_LOGIC));
        tool.diffuse(globalLogic, nativeClass(GLOBAL_FOR_SECTION));
        tool.diffuse(asset, nativeClass(LOGIC_ASSET));
        tool.diffuse(dev, Dev);
        prepared = true;
      }, position("prepare"));
      root.gearOutside().initializeTop(Option.None);
      if (!prepared) {
        throw new Error("Native root did not execute its preparation handler");
      }

      // Preparing the Logic object as a child would require the platform/remote
      // sections. Keep that startup path unentered in this first lookup probe.
      state.phase = "native-root-ready";
      state.nativeTypes = {
        root: getQualifiedClassName(root),
        gear: getQualifiedClassName(gear),
        logic: getQualifiedClassName(logic),
        status: getQualifiedClassName(status),
        globalLogic: getQualifiedClassName(globalLogic),
        asset: getQualifiedClassName(asset),
        dev: getQualifiedClassName(dev)
      };
      var previewFixture:Object = readPreviewFixture();
      if (previewFixture != null) {
        state.selectedRole = {id: previewFixture.roleId, quest: previewFixture.questId, pool: previewFixture.poolId};
      }
      return {
        output: output,
        fixture: previewFixture,
        root: root,
        gear: gear,
        logic: logic,
        status: status,
        global: globalLogic,
        dev: dev,
        hook: hook,
        asset: asset,
        previewLoads: {},
        state: state
      };
    }

    private static function readPreviewFixture():Object {
      var file:File = File.applicationDirectory.resolvePath("preview-fixture.json");
      if (!file.exists) throw new Error("Missing native preview fixture");
      var stream:FileStream = new FileStream();
      var fixture:Object;
      stream.open(file, FileMode.READ);
      try {
        fixture = JSON.parse(stream.readUTFBytes(stream.bytesAvailable));
      } finally {
        stream.close();
      }
      if (fixture == null || fixture.previewKind !== "gacha" ||
          fixture.roleId !== int(fixture.roleId) || fixture.roleId <= 0 ||
          fixture.poolId !== int(fixture.poolId) || fixture.poolId <= 0 ||
          fixture.questId !== int(fixture.questId) || fixture.questId <= 0 ||
          fixture.gachaRow == null || fixture.replayProof == null || fixture.terrainProof == null ||
          fixture.replay == null || fixture.replay.config == null ||
          !(fixture.replay.log_parts is Array)) {
        throw new Error("Invalid isolated Gacha preview fixture");
      }
      var row:Object = fixture.gachaRow;
      if (row.quest_id !== fixture.questId || !(row.log is String) ||
          !/^gacha\/feature_battle_preview\/[a-zA-Z0-9_/-]+$/.test(row.log) ||
          row.log + ".battle.amf3.deflate" !== fixture.replayProof.logical ||
          row.clip == null || row.clip.left !== int(row.clip.left) || row.clip.top !== int(row.clip.top) ||
          !(row.enables_ability is Boolean) || !(row.enables_powerflip is Boolean)) {
        throw new Error("Invalid native Gacha row for preview character " + fixture.roleId);
      }
      return fixture;
    }

    public static function attachAssets(context:Object, reader:Object):void {
      if (context.state.assetGearAttached) {
        throw new Error("Native asset Gear already attached");
      }
      context.state.phase = "attach-native-asset-gear";
      var assetGear:Object = context.asset.gearOutside().getImplement();
      assetGear.otherDiffuse(reader, nativeClass(FILE_READER));
      context.gear.addChild(context.asset, position("attachAssets"));
      context.state.assetGearAttached = true;
      context.state.phase = "native-asset-gear-ready";
    }

    public static function loadQuestMaster(context:Object):Object {
      return loadMasters(context, ["SkillPreviewQuestTable"]);
    }

    public static function loadOfficialCommonMasters(context:Object):Object {
      return loadMasters(context, ["GachaFeatureContentTable", "GachaSkillPreviewTable"]);
    }

    public static function loadOfficialMasters(context:Object):Object {
      if (!context.state.assetGearAttached) {
        throw new Error("Native asset Gear must be attached before loading startup masters");
      }
      context.state.phase = "load-native-startup-masters";
      var GroupKind:Object = nativeClass("pinball.asset.AssetGroupKind");
      var kind:Object = GroupKind.Global(false);
      var startup:Object = startupMasterBuilder(context);
      var entries:Array = startup.buildForLeadingLogic().master;
      context.state.requestedMasterCount = entries.length;
      return context.asset.addLeadingGroupsAt(kind, startup, []);
    }

    public static function enumerateStartupMasters(context:Object, result:Object):Array {
      var state:Object = context.state;
      state.phase = "enumerate-native-startup-masters";
      var startup:Object = startupMasterBuilder(context);
      var entries:Array = startup.buildForLeadingLogic().master;
      var paths:Array = [];
      for each (var entry:Object in entries) {
        paths.push({
          path: entry.key,
          filePaths: entry.filePaths.concat(),
          className: getQualifiedClassName(entry.clazz)
        });
      }
      state.startupMasters = {
        builderType: getQualifiedClassName(startup),
        group: "Global(false)",
        count: paths.length,
        entries: paths
      };
      state.phase = "native-startup-masters-enumerated";
      result.battleBootstrap = state;
      return paths;
    }

    private static function loadMasters(context:Object, names:Array):Object {
      if (!context.state.assetGearAttached) {
        throw new Error("Native asset Gear must be attached before loading masters");
      }
      context.state.phase = "load-native-masters";
      var GroupKind:Object = nativeClass("pinball.asset.AssetGroupKind");
      var Builder:Class = nativeClass("pinball.asset.logic.AssetPathCollectionBuilder");
      var builder:Object = new Builder();
      var classes:Dictionary = new Dictionary();
      for each (var name:String in names) {
        classes[nativeClass(MASTER + name)] = name;
      }

      var paths:Array = [];
      var entries:Array = startupMasterBuilder(context).buildForLeadingLogic().master;
      for each (var entry:Object in entries) {
        if (classes[entry.clazz] == null) {
          continue;
        }
        paths.push({path: entry.key, filePaths: entry.filePaths.concat(), className: classes[entry.clazz]});
        delete classes[entry.clazz];
        builder.master.add(entry);
      }
      if (paths.length !== names.length) {
        var missing:Array = [];
        for each (var missingName:String in classes) {
          missing.push(missingName);
        }
        throw new Error("Native startup master descriptors are unavailable for " + missing.join(", "));
      }
      context.state.requestedMasters = paths;
      return context.asset.addLeadingGroupsAt(GroupKind.GachaSkillPreviewCommon, builder, []);
    }

    private static function startupMasterBuilder(context:Object):Object {
      var AssetResolver:Object = nativeClass("pinball.asset.AssetResolver");
      var GroupKind:Object = nativeClass("pinball.asset.AssetGroupKind");
      return AssetResolver.getBuilder(GroupKind.Global(false), context.global);
    }

    public static function verifyMasterAndQuest(context:Object, result:Object):Object {
      var state:Object = context.state;
      state.phase = "lookup-native-master";
      var QuestTable:Class = nativeClass("pinball.master.generated.SkillPreviewQuestTable");
      var asset:Object = context.global.getLogicAssets();
      if (asset !== context.asset) {
        throw new Error("GlobalLogic did not return the attached native asset container");
      }
      var table:Object = asset.getMasterTable(QuestTable);
      var selectedId:int = context.fixture.questId;
      var values:Object = table.get_data().get(selectedId);
      if (values == null) throw new Error("Missing native Gacha preview quest " + selectedId);
      var Option:Object = nativeClass(OPTION);
      var SingleBattleIdKind:Object = nativeClass("pinball.common.data.quest.id.SingleBattleIdKind");
      var QuestIdBattleKind:Object = nativeClass("pinball.common.data.quest.id.QuestIdBattleKind");
      var questId:Object = QuestIdBattleKind.Single(SingleBattleIdKind.GachaSkillPreview(selectedId, Option.None));
      var repository:Object = context.global.getQuestRepository();
      var quest:Object = repository.getBattleQuestByBattleKind(questId);
      if (quest == null) throw new Error("Could not resolve native Gacha preview quest " + selectedId);
      var fieldDataId:String = values.kind.params[0].battle_field_data_id;
      var fieldData:Object = asset.getMasterTable(nativeClass(MASTER + "FieldDataTable")).get_data().get(fieldDataId);
      if (fieldData == null) throw new Error("Missing native preview field " + fieldDataId);
      var terrainLogical:String = fieldData.terrain + ".amf3.deflate";
      if (terrainLogical !== context.fixture.terrainProof.logical) {
        throw new Error("Native Gacha quest " + selectedId + " resolved unexpected terrain " + terrainLogical);
      }
      state.masterVerified = true;
      state.questVerified = true;
      state.questId = selectedId;
      state.questType = getQualifiedClassName(quest);
      state.repositoryType = getQualifiedClassName(repository);
      state.selectedRole.questType = state.questType;
      state.selectedRole.fieldData = fieldDataId;
      state.selectedRole.field = fieldData.field;
      state.selectedRole.terrain = terrainLogical;
      state.selectedRole.zone = fieldData.zone;
      state.phase = "native-quest-verified";
      result.battleBootstrap = state;
      return quest;
    }

    public static function enumerateOfficialCommon(context:Object, result:Object):Object {
      return enumerateGachaCandidateCommon(context, result);
    }

    private static function enumerateGachaCandidateCommon(context:Object, result:Object):Object {
      var state:Object = context.state;
      var fixture:Object = context.fixture;
      var row:Object = fixture.gachaRow;
      var roleId:int = fixture.roleId;
      state.phase = "enumerate-native-gacha-candidate-common";
      // The candidate supplies a separate Gacha row. Build common assets with
      // the same native permit and builder as the client Gacha row resolver.
      var PermitKind:Object = nativeClass("pinball.scene.battle.battle.feature.BattleFeaturePermitKind");
      var PermitTools:Object = nativeClass("pinball.scene.battle.battle.feature.BattleFeaturePermitTools");
      var permit:Object = PermitTools.createLoadPermitData(
        PermitKind.GachaSkillPreview(row.enables_ability, row.enables_powerflip),
        PermitTools.getGachaSkillPreviewFeatureData()
      );
      var Builder:Class = nativeClass("pinball.asset.builder.BattleAssetPathCollectionBuilder");
      var builder:Object = new Builder(context.global, permit, null, false);
      builder.addCommonAssets();
      var GroupKind:Object = nativeClass("pinball.asset.AssetGroupKind");
      var common:Object = {
        row: row, builder: builder, kind: GroupKind.GachaSkillPreviewCommon,
        roleId: roleId, poolId: fixture.poolId
      };
      context.officialCommon = common;
      state.gachaCandidateBinding = {
        previewKind: fixture.previewKind, roleId: roleId, questId: row.quest_id, log: row.log,
        clipLeft: row.clip.left, clipTop: row.clip.top,
        enablesAbility: row.enables_ability, enablesPowerFlip: row.enables_powerflip
      };
      state.commonBuilderCreated = true;
      state.commonBuilderType = getQualifiedClassName(builder);
      state.initialNativeCommonRequests = snapshotRequests(builder);
      state.phase = "native-preview-common-enumerated";
      result.battleBootstrap = state;
      return common;
    }

    public static function createOfficialPreview(context:Object, result:Object):Object {
      var state:Object = context.state;
      if (!state.questVerified) {
        throw new Error("The native preview quest must resolve before creating the preview");
      }
      state.sourceCreated = false;
      state.partBuilderCreated = false;
      var common:Object = context.officialCommon;
      if (common == null) {
        common = enumerateOfficialCommon(context, result);
      }
      state.phase = "create-native-preview-source";
      var Info:Object = nativeClass("pinball.scene.gacha.featureDisplay.skillPreview.GachaFeatureSkillPreviewInfo");
      var info:Object = Info.createSkillPreviewInfo(context.global, common.row, common.roleId);
      state.phase = "verify-native-preview-source";
      var source:Object = info.battleSource;
      var values:Object = source.values;
      var party:Object = values.source.party;
      var character:Object = party.characters[0].params[0];
      if (character.id !== common.roleId || character.evolution_level !== 1 ||
          party.characters.length !== 3 || party.characters[1].index !== 1 ||
          party.characters[2].index !== 1) {
        throw new Error("Native origin-character party differs from the selected preview binding");
      }
      var QuestIdBattleKind:Object = nativeClass("pinball.common.data.quest.id.QuestIdBattleKind");
      var SingleBattleIdKindTools:Object = nativeClass("pinball.common.data.quest.id.SingleBattleIdKindTools");
      var battleKind:Object = QuestIdBattleKind.Single(values.questId);
      var previewOption:Object = SingleBattleIdKindTools.getSkillPreviewValue(values.questId);
      if (previewOption.index !== 0) {
        throw new Error("Native source did not produce skill preview values");
      }
      var preview:Object = previewOption.params[0];
      if (preview.questId !== common.row.quest_id || preview.log !== common.row.log ||
          preview.enablesAbility !== common.row.enables_ability ||
          preview.enablesPowerFlip !== common.row.enables_powerflip) {
        throw new Error("Native preview values differ from the selected preview row");
      }
      state.sourceCreated = true;
      state.phase = "read-native-preview-source-mana-map";
      var manaKeys:Object = character.mana_node_ids.keys();
      var manaNodeCount:int = 0;
      while (manaKeys.hasNext()) {
        manaKeys.next();
        manaNodeCount++;
      }
      state.phase = "record-native-preview-source";
      state.previewSource = {
        infoType: getQualifiedClassName(info),
        battleSourceType: getQualifiedClassName(source),
        valuesType: getQualifiedClassName(values),
        playId: values.playId,
        character: character.id,
        pool: common.poolId,
        quest: common.row.quest_id,
        evolution: character.evolution_level,
        experience: character.exp,
        manaNodeCount: manaNodeCount,
        log: preview.log,
        enablesAbility: preview.enablesAbility,
        enablesPowerFlip: preview.enablesPowerFlip,
        clipLeft: info.clip.left,
        clipTop: info.clip.top
      };

      var AssetResolver:Object = nativeClass("pinball.asset.AssetResolver");
      var GroupKind:Object = nativeClass("pinball.asset.AssetGroupKind");
      var parents:Array = [common.kind];
      state.phase = "enumerate-native-preview-part";
      var builder:Object = AssetResolver.getGachaSkillPreviewPartBuilder(
        values.playId, battleKind, 0, party, preview.log,
        preview.enablesAbility, preview.enablesPowerFlip, context.global
      );
      var kind:Object = GroupKind.GachaSkillPreviewPart(common.poolId);
      state.partBuilderCreated = true;
      state.partBuilderType = getQualifiedClassName(builder);
      state.initialNativeAssetRequests = snapshotRequests(builder);
      state.phase = "native-preview-part-enumerated";
      result.battleBootstrap = state;
      return {
        info: info, source: source, builder: builder, kind: kind, parents: parents,
        poolId: common.poolId, commonBuilder: common.builder, commonKind: common.kind
      };
    }

    public static function loadPreviewLeading(context:Object, preview:Object, isCommon:Boolean):Object {
      var label:String = isCommon ? "common" : "part";
      if (context.previewLoads[label] != null) {
        throw new Error("Native preview " + label + " resource group already started");
      }
      var AssetGroup:Class = nativeClass("pinball.asset.AssetGroup");
      var group:Object = isCommon
        ? new AssetGroup(preview.commonKind, preview.commonBuilder)
        : new AssetGroup(preview.kind, preview.builder);
      var parents:Array = isCommon ? [] : preview.parents;
      context.state.phase = "load-native-preview-" + label + "-leading";
      var progress:Object = context.asset.addLeadingGroupsAt(group.kind, group.builder, parents);
      context.previewLoads[label] = {group: group, parents: parents, leading: progress};
      return progress;
    }

    public static function resolvePreviewLeading(context:Object, isCommon:Boolean, result:Object):Object {
      var label:String = isCommon ? "common" : "part";
      var load:Object = context.previewLoads[label];
      if (load == null || !load.leading.get_completed() || load.following != null) {
        throw new Error("Native preview " + label + " leading group must complete once before resolution");
      }
      context.state.phase = "resolve-native-preview-" + label + "-leading";
      var AssetResolver:Object = nativeClass("pinball.asset.AssetResolver");
      AssetResolver.dispatchLeadingLogicAssetLoaded([load.group], context.asset);
      context.state[label + "RequestsAfterLeading"] = snapshotRequests(load.group.builder);
      result.battleBootstrap = context.state;
      context.state.phase = "load-native-preview-" + label + "-following";
      load.following = context.asset.addFollowingGroupsAt(load.group.kind, load.group.builder, load.parents);
      return load.following;
    }

    public static function resolvePreviewFollowing(context:Object, isCommon:Boolean, result:Object):void {
      var label:String = isCommon ? "common" : "part";
      var load:Object = context.previewLoads[label];
      if (load == null || load.following == null || !load.following.get_completed() || load.resolved === true) {
        throw new Error("Native preview " + label + " following group must complete once before resolution");
      }
      context.state.phase = "resolve-native-preview-" + label + "-following";
      var AssetResolver:Object = nativeClass("pinball.asset.AssetResolver");
      AssetResolver.dispatchFollowingLogicAssetLoaded([load.group], context.asset);
      context.state[label + "RequestsAfterFollowing"] = snapshotRequests(load.group.builder);
      if (!isCommon) {
        verifyLoadedReplay(context);
      }
      load.resolved = true;
      context.state.phase = "native-preview-" + label + "-logic-ready";
      result.battleBootstrap = context.state;
    }

    private static function verifyLoadedReplay(context:Object):void {
      var state:Object = context.state;
      state.phase = "verify-native-preview-replay";
      var logPath:String = context.officialCommon.row.log;
      var replay:Object = context.asset.getBattleReplayLog(logPath);
      var config:Object = replay.config;
      var ball:Object = config.ball;
      var frames:Array = [];
      for each (var command:Object in replay.log_parts) {
        frames.push(command.f);
      }
      if (context.fixture != null) {
        var expected:Object = context.fixture.replay;
        var expectedConfig:Object = expected.config;
        if (config.start_frame !== expectedConfig.start_frame ||
            config.end_frame !== expectedConfig.end_frame ||
            config.hp_ratio !== expectedConfig.hp_ratio ||
            config.skill_gauge_ratio !== expectedConfig.skill_gauge_ratio ||
            config.power_flip_level !== expectedConfig.power_flip_level ||
            ball.x !== expectedConfig.ball.x || ball.y !== expectedConfig.ball.y ||
            ball.vx !== expectedConfig.ball.vx || ball.vy !== expectedConfig.ball.vy ||
            frames.length !== expected.log_parts.length) {
          throw new Error("Native cached replay differs from the locked character fixture " + context.fixture.roleId);
        }
        for (var i:int = 0; i < frames.length; i++) {
          if (frames[i] !== expected.log_parts[i].f) {
            throw new Error("Native cached replay command frame differs at index " + i);
          }
        }
      }
      state.loadedNativeReplay = {
        type: getQualifiedClassName(replay), logical: logPath,
        startFrame: config.start_frame, endFrame: config.end_frame,
        ball: {x: ball.x, y: ball.y, vx: ball.vx, vy: ball.vy},
        skillGaugeRatio: config.skill_gauge_ratio, hpRatio: config.hp_ratio,
        powerFlipLevel: config.power_flip_level, commandFrames: frames
      };
    }

    public static function attachPreviewHook(context:Object):Object {
      if (!context.state.previewHookAttached) {
        context.state.phase = "attach-native-preview-hook";
        context.gear.addChild(context.hook, position("attachPreviewHook"));
        if (context.hook.dispatcher == null) {
          throw new Error("Native preview Hook did not initialize its dispatcher");
        }
        context.state.previewHookAttached = true;
        context.state.previewHookType = getQualifiedClassName(context.hook);
      }
      return context.hook;
    }

    public static function attachPreviewScene(context:Object, preview:Object, result:Object):Object {
      if (context.previewLoads.common == null || context.previewLoads.common.resolved !== true ||
          context.previewLoads.part == null || context.previewLoads.part.resolved !== true) {
        throw new Error("Both native preview logic groups must resolve before attaching the scene");
      }
      if (context.nativePreviewSound == null) {
        throw new Error("A native ProductionSoundSection must be supplied before attaching the preview scene");
      }
      attachPreviewHook(context);
      context.state.phase = "prepare-native-preview-component-holder";
      var holder:Object = createPreviewComponentHolder(context);
      var Scene:Class = nativeClass("pinball.scene.battle.SkillPreviewBattle");
      var Restore:Class = nativeClass("pinball.context.restore.Restore");
      var scene:Object = new Scene(preview.source);
      var sceneGear:Object = scene.gearOutside().getImplement();
      sceneGear.otherDiffuse(holder, nativeClass("pinball.context.scene.component.ComponentLogicHolder"));
      sceneGear.otherDiffuse(context.nativePreviewSound, nativeClass("pinball.sound.SoundSectionForLogic"));
      // BattleDebug absorbs this service while preparing the native battle.
      // The preview never enters its save/restore UI or storage lifecycle.
      var restore:Object = new Restore();
      sceneGear.otherDiffuse(restore, nativeClass("pinball.context.restore.RestoreForLogic"));
      context.state.previewRestoreType = getQualifiedClassName(restore);
      context.state.previewSoundType = getQualifiedClassName(context.nativePreviewSound);
      context.state.previewComponentHolderType = getQualifiedClassName(holder);
      context.state.phase = "attach-native-preview-scene";
      context.gear.addChild(scene, position("attachPreviewScene"));
      if (scene.myBattle == null) {
        throw new Error("Native SkillPreviewBattle did not prepare its Battle child");
      }
      context.state.previewSceneType = getQualifiedClassName(scene);
      context.state.previewBattleType = getQualifiedClassName(scene.myBattle);
      context.state.phase = "native-preview-scene-attached";
      result.battleBootstrap = context.state;
      return scene;
    }

    private static function createPreviewComponentHolder(context:Object):Object {
      // The embedded scene inherits this native UI holder from its parent page.
      // Its constructor builds the dispatcher without entering a top-level scene.
      var LogicScene:Class = nativeClass("pinball.context.scene.LogicScene");
      var Transition:Class = nativeClass("pinball.context.scene.LogicSceneTransition");
      var Parameters:Class = nativeClass("pinball.context.scene.TransitionParameters");
      var TransitionKind:Object = nativeClass("pinball.context.ViewTransitionKind");
      var SceneKind:Object = nativeClass("pinball.context.ViewSceneKind");
      var Provider:Class = nativeClass("pinball.context.input.HookDispatcherProvider");
      var transition:Object = new Transition(null, null, TransitionKind.Blank, new Parameters(1, 0, 0, 0));
      var holder:Object = new LogicScene(SceneKind.BlankScene, transition, position("createPreviewComponentHolder"));
      holder.hookDispatcherProvider = context.gear.addChild(new Provider(), position("createPreviewComponentHolder"));
      return holder;
    }

    private static function snapshotRequests(builder:Object):Object {
      return {
        leading: summarizeRequests(builder.buildForLeadingLogic(), [
          "master", "action", "actionWithoutView", "enemy", "terrain", "intermediateDownloadFileLists"
        ]),
        following: summarizeRequests(builder.buildForFollowingLogic(), [
          "ui", "movie", "timeline", "gachaConfig", "battleReplayLog", "battleBallLog"
        ]),
        view: summarizeRequests(builder.buildForView(), [
          "image", "html", "css", "bitmapFont", "spriteSheet", "animationLayout",
          "characters", "dynamicTexture", "packingImage", "packingSpriteSheet", "colorChanges"
        ]),
        sound: summarizeRequests(builder.buildForSound(), ["soundEffect", "bgm"])
      };
    }

    private static function summarizeRequests(collection:Object, fields:Array):Object {
      var summary:Object = {};
      for each (var field:String in fields) {
        var entries:Array = collection[field] as Array;
        if (entries == null) {
          var nativeValue:Object = collection[field];
          if (nativeValue != null && getQualifiedClassName(nativeValue) === "pinball.common.ds::OrderedMap") {
            summary[field] = {type: getQualifiedClassName(nativeValue), keys: nativeValue.rawKeys().concat()};
          } else {
            summary[field] = {type: getQualifiedClassName(nativeValue)};
          }
          continue;
        }
        var values:Array = [];
        for each (var entry:* in entries) {
          if (entry == null || entry is String) {
            values.push(entry);
            continue;
          }
          var value:Object = {type: getQualifiedClassName(entry)};
          for each (var property:String in ["path", "filePaths", "id", "key", "logicalPath", "stringId"]) {
            if (property in entry && (entry[property] is String || entry[property] is int)) {
              value[property] = entry[property];
            } else if (property in entry && entry[property] is Array) {
              var strings:Array = [];
              for each (var item:* in entry[property]) {
                if (item is String) {
                  strings.push(item);
                }
              }
              value[property] = strings;
            }
          }
          values.push(value);
        }
        summary[field] = values;
      }
      return summary;
    }

    private static function nativeClass(name:String):Class {
      var result:Class = getDefinitionByName(name) as Class;
      if (result == null) {
        throw new Error("Missing native class " + name);
      }
      return result;
    }

    private static function position(method:String):Object {
      return {fileName: "BattleBootstrap.as", lineNumber: 0, className: "BattleBootstrap", methodName: method};
    }
  }
}
