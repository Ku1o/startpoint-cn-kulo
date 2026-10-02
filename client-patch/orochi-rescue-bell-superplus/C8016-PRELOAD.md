# 救援铃铛 C8016 v3 SWF helper 预载

这一步接在已验收的“超级+”紧凑排版 APK 后面。它修复的是 C8016 预载判断，不改伤害归属、数值、服务端接口或 CDN 链。

## 根因与源码

SWF 中已有的 `cn.mod::InahoAbilityVisuals` helper 原来只对 `InvokeSkill`（嵌套类型 `19`）且路径含 `cnmod_inaho_midautumn` 的内容预载稻穗特效。`AllEnemyDamage` 和 `GeneralEnemyDamage` 会直接创建 `AbilityDamageShot`，对应嵌套类型 `13`、`14`，没有 `InvokeSkill` 路径标记，因此会漏掉预载。

源码位于 [`author-unified-damage/src/cn/mod/InahoAbilityVisuals.as`](../author-unified-damage/src/cn/mod/InahoAbilityVisuals.as)。预载判断保持以下边界：

- 根内容索引必须是 `4`；
- 嵌套索引 `13`、`14` 直接允许预载；
- 嵌套索引 `19` 仍必须检查 `cnmod_inaho_midautumn` 标记；
- 其他索引和异常对象返回 `false`。

## 生成 helper SWF

先用 AIR SDK 编译现有源码 helper，再只替换 SWF 中现有的 helper ABC：

```powershell
<JAVA> -Dflexlib=<AIR_SDK>/frameworks -Xmx512m `
  -jar <AIR_SDK>/lib/compc-cli.jar `
  +configname=air -swf-version=44 -target-player=32.0 -debug=false `
  -compiler.source-path=client-patch/author-unified-damage/src `
  -include-classes=cn.mod.InahoAbilityVisuals `
  -output=<WORK>/inaho-visuals-v3.swc

python -X utf8 -B client-patch/orochi-rescue-bell-superplus/build_c8016_helper.py `
  --source=<SUPERPLUS_LAYOUT_SWF> `
  --helper-swc=<WORK>/inaho-visuals-v3.swc `
  --output=<WORK>/c8016-v3.swf `
  --report=<WORK>/c8016-v3.json
```

`build_c8016_helper.py` 要求 SWF 中恰好一个 `cn.mod::InahoAbilityVisuals` ABC，保留其原 tag 位置和前缀，只允许该 tag 改变，并逐 tag 检查其他内容字节一致。当前 v3 回读结果为 helper tag `359`、旧 helper 7 个方法体、新 helper 8 个方法体；输出 SWF SHA-256 为 `9418137820c007b52a11ad0d7955c102795d8dd903213670577bf3407ed709f7`。

## 封装 Android 内网 APK

从紧凑排版 APK `8ab2533469bb88d1292db9c2406b7ff696cb1d1064c027bd83b4985f5e19dcc1` 接续，替换 SWF、更新 AIR `uniqueappversionid`，再执行 ZIP 对齐和固定证书签名：

```powershell
python -X utf8 -B client-patch/orochi-rescue-bell-superplus/package_c8016_apk.py `
  --input-apk=<SUPERPLUS_LAYOUT_APK> `
  --swf=<WORK>/c8016-v3.swf `
  --work=<WORK>/package `
  --output-apk=<OUTPUT>/c8016-v3-lan.apk `
  --java=<JAVA> `
  --baksmali-jar=<BAKSMALI_JAR> `
  --smali-jar=<SMALI_JAR> `
  --zipalign=<ZIPALIGN> `
  --sign-script=<SIGN_APK_PS1> `
  --apksigner=<APKSIGNER_JAR>
```

封装器只更新 `AndroidManifest.xml`、`classes.dex` 中的 AIR 身份和目标 SWF，保留准入配对、包名、版本号、签名证书及其他 APK 成员。当前 v3 内网 APK SHA-256 为 `5505e73fbe770ca3c81e638e6e97b103b9bb997c95b6bc63d2b277323d8e6884`，AIR UUID 为 `5a18e114-3549-4e26-bf34-e9616562d08a`。它没有使用 CDN 增量，也没有制作 IPA。

完成 C8016 v3 后，若要叠加 10 分钟 AIR 缓存清理，继续使用 [`startup-cache/PERIODIC-10M.md`](../startup-cache/PERIODIC-10M.md) 和 `build_periodic_apk.py`，不要回退到紧凑排版旧 APK。
