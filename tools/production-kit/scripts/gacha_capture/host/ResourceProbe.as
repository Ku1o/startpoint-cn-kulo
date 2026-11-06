package {
  import flash.desktop.NativeApplication;
  import flash.filesystem.File;
  import flash.filesystem.FileMode;
  import flash.filesystem.FileStream;
  import flash.utils.ByteArray;
  import flash.utils.getDefinitionByName;
  import flash.utils.getQualifiedClassName;

  public final class ResourceProbe {
    private static const BUNDLE_ROOT:String = "asset/bundle/production/";
    private static const FILELIST_HASH:String = "0b/b0ad84cf78469d021ce6896dfa931ed434af54";

    public static function run(output:File, result:Object, fixture:Object):Object {
      requirePrivateHost(output);
      result.resourceProbe = {
        passed: false, phase: "stage-bundle", nativeFileReader: true,
        masterParserStubbed: false, readMode: 1,
        unusedExternalInterfaces: ["GlobalLogicForSection", "DownloadedCacheForSection",
          "AssetDownloaderForSection", "HookForSection"]
      };
      var source:File = File.applicationDirectory.resolvePath("resource-probe/bundle");
      var storage:File = File.applicationStorageDirectory;
      var preparedList:File = source.resolvePath("files.json");
      if (!preparedList.exists) throw new Error("Missing private bundle manifest");
      var manifest:ByteArray = readBytes(preparedList);
      var paths:Array = JSON.parse(manifest.readUTFBytes(manifest.length)) as Array;
      if (!paths || paths.indexOf("bundle/" + FILELIST_HASH) < 0) {
        throw new Error("Sparse bundle lacks the native file list");
      }
      for each (var path:String in paths) {
        if (!/^(?:bundle|medium_bundle|android_bundle)\/[0-9a-f]{2}\/[0-9a-f]{38}$/.test(path)) {
          throw new Error("Invalid sparse bundle member path: " + path);
        }
        var sourcePath:String = path;
        copyExact(source.resolvePath(sourcePath), storage.resolvePath(BUNDLE_ROOT + path));
      }
      result.resourceProbe.stagedBundleMembers = paths.length;

      result.resourceProbe.phase = "initialize-file-reader";
      var Config:Class = getDefinitionByName("pinball.config.core.DevConfig") as Class;
      var Reader:Class = getDefinitionByName("pinball.asset.file.FileReader") as Class;
      var config:Object = new Config();
      config.assetReadKind = 1;
      config.assetDirectories = ["production"];
      var scale:Object = getDefinitionByName("pinball.context.screenSize.ImageScale").Medium;
      var reader:Object = new Reader(config, null, null, null, null, scale);
      reader.initialize();
      var replay:Object = reader.readDataFileSync(fixture.gachaRow.log, ".battle");
      if (replay == null || replay.config.start_frame !== fixture.replay.config.start_frame ||
          replay.config.end_frame !== fixture.replay.config.end_frame ||
          replay.log_parts.length !== fixture.replay.log_parts.length) {
        throw new Error("Native private reader returned a different replay");
      }
      for (var i:int = 0; i < replay.log_parts.length; i++) {
        var actual:Object = replay.log_parts[i];
        var expected:Object = fixture.replay.log_parts[i];
        if (actual.f !== expected.f || JSON.stringify(actual.c) !== JSON.stringify(expected.c)) {
          throw new Error("Native private reader returned a different command");
        }
      }
      result.resourceProbe.replay = replay;
      result.resourceProbe.phase = "complete";
      result.resourceProbe.passed = true;
      return reader;
    }

    private static function requirePrivateHost(output:File):void {
      var id:String = NativeApplication.nativeApplication.applicationID;
      if (!/^local\.starpoint\.offlinenative(?:\.[A-Za-z0-9.-]+)?$/.test(id)) {
        throw new Error("Resource probe requires an independent offline AIR application ID");
      }
      if (!output || !output.isDirectory) throw new Error("Resource probe requires a run results directory");
    }

    private static function copyExact(source:File, destination:File):void {
      var expected:ByteArray = readBytes(source);
      if (!destination.exists) {
        destination.parent.createDirectory();
        source.copyTo(destination, false);
      }
      var actual:ByteArray = readBytes(destination);
      if (actual.length !== expected.length) throw new Error("Private cache collision: " + destination.nativePath);
      actual.position = 0;
      expected.position = 0;
      while (actual.bytesAvailable >= 4) {
        if (actual.readUnsignedInt() !== expected.readUnsignedInt()) {
          throw new Error("Private cache collision: " + destination.nativePath);
        }
      }
      while (actual.bytesAvailable > 0) {
        if (actual.readUnsignedByte() !== expected.readUnsignedByte()) {
          throw new Error("Private cache collision: " + destination.nativePath);
        }
      }
    }

    private static function readBytes(file:File):ByteArray {
      if (!file.exists || file.isDirectory) throw new Error("Missing prepared resource: " + file.nativePath);
      var bytes:ByteArray = new ByteArray();
      var stream:FileStream = new FileStream();
      stream.open(file, FileMode.READ);
      try {
        stream.readBytes(bytes);
      } finally {
        stream.close();
      }
      return bytes;
    }
  }
}
