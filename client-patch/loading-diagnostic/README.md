# Android 共斗加载诊断候选

2026-09-13，按用户“从已验收版本做出来试试看”制作。当前源码候选为 `CN-LOAD-20260913-r6`，连接已登记的公网环境；r5 是本次 MuMu 1 实测版本。
本次只增加加载观测和手机本地导出，尚未把图集合成分帧、资源复用或 GC 调整带入成品，也不声称已修复 93.38% 附近的无响应。

## 输入与范围

直接输入为 `android-accepted.json` 登记的商店优化公网 APK，SHA-256：

`35e0e7c777798594d68c9bcd74c507c6f0b7d065453e0425c301258c6bc38ac6`

输入 SWF：`e60cc4a82e3b305257040dedc54d180794234e2c2d4d3cef68a105b9f8405927`。
保留当前商店、觉醒页刷新、昵称、账号登录、缓存、切队及全部累计修复。只替换 APK 的 SWF、DEX 和二进制 manifest；其他载荷逐项按字节比较。
原来 96,543 个方法体中 22 个增加观测或入口调用，其余 96,521 个保持不变；新增 20 个 AS3 辅助方法。
原有类字段、方法签名、异常表数量及原生 6 个类的逻辑保持。去除插桩后能还原原方法代码，GC 原回调位置及实际调用次数保持。

原方法体索引（基线主 ABC 291，候选主 ABC 292；r6 额外加入四个细分阶段）：

`4336, 4373, 4374, 5209, 5259, 5263, 5264, 5322, 15140, 20565, 28920, 28956, 28963, 28971, 30852, 38042, 38045, 38046, 38073, 38074, 38076, 38428, 38430, 38431, 38432, 50845, 51007, 51008, 58883, 60835, 63233, 63250, 76162, 76168, 76169, 82500, 82509, 92540`。

本次没有服务端、CDN、iOS、存档结构、进度 ID、导入导出或账号归属变更，因此不运行无关的存档迁移测试。
没有提交、推送、同步运行目录或修改已验收注册表。本候选不成为后续开发基线，须等待用户验收。

## 记录内容和成本

共斗任务开始后记录连接响应、队伍资源整理、图集收集/排布/分配/绘制、原 GC、场景及 HUD 初始化、首次战斗更新返回等阶段。
每条包含阶段起止、时间、AIR 内存/进程私有内存样本及少量资源数量、尺寸和关卡数字标识。记录自身累计/最大写入耗时，供判断诊断开销。
不序列化网络包、账号、密码、昵称、UID、房号或存档；系统 ANR 线程信息仅在系统提供时附加。

`begin/end` 表示函数的同步进入/返回，异步工作需结合后续 `ready/complete` 阶段判断。嵌套调用的时间不能简单相加；最后一个 begin 也不单独证明该函数就是崩溃原因。

加载期间每 2 秒补一次样本；阻塞时回调也会延迟，因此它不是实时 CPU/GPU 探针，内存样本不是精确峰值。
普通记录最多 400 条或约 120 KB，另留一个结束标记；每条写完关闭流，没有逐帧写盘或强制 fsync。
首次战斗更新结束后停止采样；后续战斗帧只有一次布尔短路调用。诊断存在额外开销，暂未做真实手机加载耗时对照。

AIR 使用 `File.applicationStorageDirectory/cn-loading-diagnostics`。当前包实际位于应用私有目录下
`com.leiting.wf/Local Store/cn-loading-diagnostics`，原生读取同时支持有限的旧目录候选。
仅允许读取 `runtime.json`、`latest.jsonl`、`previous.jsonl`、`last-unfinished.jsonl`，单文件最大 160 KB。
开始下一次加载前将最新记录轮换；没有完成或取消标记的记录另行保留。启动游戏和导出都不清空上次加载。
“未完成”只能说明中断，主动结束应用、系统回收等也可能产生该状态。强杀或断电仍可能丢失最后一条正在写的记录。

Android 11 及以上附带本应用最近最多 6 次系统退出原因及系统最后的 PSS/RSS 样本。
最多包含 2 份 ANR 线程文本，每份截断到 256 KB；不附加 native tombstone 内存转储。
旧 Android 或系统没有保留 ANR 时，仍可导出阶段记录，不能保证所有退出都有系统堆栈。

## 手机导出

应用列表增加“星点诊断日志”入口，无需通过游戏登录。标题页另有“诊断日志”按钮，离开标题时隐藏；若登录弹窗挡住按钮，使用应用列表入口。
分享通过不对外公开的只读 ContentProvider，临时授权接收应用读取所选 ZIP。不会自动上传，也不会替用户选择收件人。
Android 10 及以上可保存至“下载/StarPoint”；较旧版本使用系统文件选择器。另提供复制摘要，但分析时应优先取得完整 ZIP。
导出压缩与保存使用后台线程，内部仅保留最近约 6 个导出 ZIP。用户另存到下载目录的文件由用户管理。
不新增存储权限，也不要求玩家打开 USB 调试或 root。

## 构建和验证

先运行仓库的已验收基线检查器。构建脚本使用 headless `compc` 编译独立辅助类，只提取其 ABC；不替换整个反编译游戏类。
Android platform-30 的类库来自官方 SDK `platform-30_r03.zip`，归档 SHA-1 为
`e7c6280901dcfa511af098d67dd88c4dfcbc6ea2`，`android.jar` SHA-256 为
`96ccfdc84d15fad4e22d76cbb8ef38b150a4b56327957067875ca7e18113a424`。
每次原生编译/DEX 合并使用 UUID 独立输出目录，避免增量目录遗留旧匿名类。每个候选使用新的 AIR 与原生启动缓存 UUID。

在仓库根目录执行：

```powershell
python -B -X utf8 client-patch/verify_android_baseline.py --variant public
python -B -X utf8 client-patch/loading-diagnostic/build.py
python -B -X utf8 client-patch/loading-diagnostic/verify.py
```

`build.py` 不覆盖已存在的候选 APK；再次制作不同载荷时须更新 `common.py` 和 AS3 中的构建标识并保留旧报告。
签名只通过既有 DPAPI 签名入口，证书固定为 `569D19A3578D4CBA16E3D6E7AD8CCAB4FA667EFC758DEEF6C9BE3ADB99919894`。
单独保存每个候选的构建、逆向核验、签名及设备回执；APK/SWF、工具和本地 QA 日志不入 Git。

JVM 文件测试覆盖允许列表、大小限制、路径拒绝、ZIP 回读、未完成记录与导出保留，共 17 项。
`tests/PhoneReceiver.java` 和 `PhoneProbe.java` 仅用于独立本机 QA APK，不打进游戏包。
PhoneProbe 仅操作本任务新增的诊断目录，在写入模拟记录前备份并在测试后恢复；测试应用随后卸载。
它验证中断记录持久保存和导出路径，不等于实际共斗的 ANR 复现。

用户指定只用 MuMu **1** 测试，当前连接 `127.0.0.1:16416`；每次安装前用 MuMuManager 核对设备索引。
0 号仅曾启动随后关闭，没有安装本次候选或操作游戏数据。设备回执详见产物目录。
实际幻想/五重共斗、Android 9 及以下的文件选择器、各厂商真机及 QQ/微信发送仍须玩家测试。

制作期间的 r1/r2 因目录匹配和文件选择器写入授权问题未交付；r3 完成导出测试后，r4 用隔离编译目录去除一个无引用的旧匿名类；r5 降低内存查询频率并加入资源／战斗阶段；r6 再加入能力汇总、队伍角色计算和地形解析阶段。实际 MuMu 1 共斗数据来自 r5，r6 仅完成静态校验和 LAN 转换，未计入性能样本。

参考：[AIR 文件位置](https://airsdk.dev/docs/development/files-and-data/working-with-the-file-system/using-the-air-file-system-api/working-with-file-objects-in-air)、
[Android 文档选择器](https://developer.android.com/training/data-storage/shared/documents-files)、
[Android 下载文件访问](https://developer.android.com/training/data-storage/shared/media)。
