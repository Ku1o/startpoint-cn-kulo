# Android AIR 缓存十分钟定时清理

这是覆盖安装启动清理之后的运行期补充。它只清理应用私有的 `cache/app` 和 `cache/.AIR`，不清理 CDN 下载目录、APK 内置 `assets/bundle.zip`、Local Store、SharedObject、账号文件、设置或存档。

## 行为边界

- Android 原生 `StartupCache.run` 成功后只启动一个 daemon 线程；同一进程不会重复启动。
- 线程每 `600000` 毫秒（10 分钟）运行一次，先将 `dataDir` 规范化，再通过 allowlist 定位 `<DATA>/cache/app` 和 `<DATA>/cache/.AIR`。
- 删除失败不会杀死游戏进程；线程继续等待下一个周期。
- 每次调度、完成或异常都会覆盖写入 `<DATA>/sp-cache-periodic.diag`，记录实际 `dataDir`、目标路径、删除前是否存在、删除结果、阶段和异常信息；记录限制为 4096 字节。

实现位于 [`native/cn/startpoint/StartupCache.java`](./native/cn/startpoint/StartupCache.java)，测试夹具位于 [`tests/StartupCacheTest.java`](./tests/StartupCacheTest.java)。启动清理与定时清理共用 `inside`、`remove` 和符号链接边界检查。

## 从 C8016 v3 APK 构建

构建器要求输入已经包含 C8016 v3 helper 和启动缓存入口的 APK，默认锁定输入 SHA-256 `5505e73fbe770ca3c81e638e6e97b103b9bb997c95b6bc63d2b277323d8e6884`、SWF SHA-256 `9418137820c007b52a11ad0d7955c102795d8dd903213670577bf3407ed709f7` 和 AIR UUID `5a18e114-3549-4e26-bf34-e9616562d08a`。它只替换 `StartupCache`、`StartupCache$Periodic`、`BuildIdentity`、`classes.dex` 和 Manifest 中的 AIR UUID；SWF 与其他 APK 成员保持不变。

```powershell
python -X utf8 -B client-patch/startup-cache/build_periodic_apk.py `
  --input-apk=<C8016_V3_APK> `
  --work=<WORK>/periodic-cache `
  --output-apk=<OUTPUT>/c8016-cache-10m-lan.apk `
  --java=<JAVA> `
  --d8-jar=<D8_JAR> `
  --baksmali-jar=<BAKSMALI_JAR> `
  --smali-jar=<SMALI_JAR> `
  --zipalign=<ZIPALIGN> `
  --sign-script=<SIGN_APK_PS1> `
  --apksigner=<APKSIGNER_JAR>
```

构建器先从源码编译原生 helper，再回读完整 DEX 的类清单，确认非目标类逐字节回读一致，检查 `0x927c0` 睡眠常量、`periodicPurge` 和 `startPeriodic`，最后校验 ZIP、AIR UUID、SWF 哈希、对齐和签名。签名密码只由现有签名脚本读取，不进入脚本参数、报告或 Git。

## 当前组合血统

本次组合顺序固定为：

1. “超级+”内置紧凑排版 APK；
2. C8016 v3 helper SWF（仅 helper tag 359 改变）；
3. 10 分钟 AIR 缓存清理；
4. 新的 AIR `uniqueappversionid`、ZIP 对齐和签名。

最终内网 APK 的 SHA-256 为 `4f62b899a89b0648f79d0dbaf20d8aab9b64ad91959d91706dc71af02cb6c335`，SWF SHA-256 仍为 `9418137820c007b52a11ad0d7955c102795d8dd903213670577bf3407ed709f7`，AIR UUID 为 `4728fb03-7242-4fcc-9bc4-e8b4fc073a43`。该成品报告标记为未由 Codex 设备连接实测、未部署云服；用户实机测试记录按验收登记保存。

APK、SWF、DEX、诊断文件和临时构建目录只留在任务输出目录，不提交 Git。该功能没有 CDN 增量，也不需要服务端改动或公网 APK/IPA。
