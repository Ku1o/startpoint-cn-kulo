# Android / iOS C8601 累计修复基线（2026-11-01）

当前 Android 公网 APK 与 iOS ARM64 公网未签名 IPA 均登记为 `accepted_offline`，作为后续开发的直接输入。离线登记不代表重签安装、手机游戏或 iOS 原生执行通过。平台登记分别见 [Android](android-accepted.json)、[iOS](ios-accepted.json)，配方见 [startup-equipment-c8601](startup-equipment-c8601/README.md)。

## 登记成品

| 平台 | 成品 SHA-256 | 载荷身份 |
| --- | --- | --- |
| Android 1.8.1 | `abab751cee7b3584fb5600a1a7a057bbe8b4d5f44b33232801983790ba74fd87` | SWF `1d9dbd353c429570833ccad106ab93b76794226e66087a9fc5c3fff80fd2ae10`；AIR UUID `95dfe546-7124-4e0f-a728-3e16e14d0b27` |
| iOS 1.8.4 / build 1.8.46 | `5af60564dcf4468a118b7e4d8dfc53f9b8d601bcfbaaaa88d18698367618997d` | native `20ec1f3f53c9f40d12f0a4d8dd31ccbd06b7907d24b1222c73bb89ecf1f6ceb6`；SWF `6574b07537498ae7ad7f66f26764a70dbd92a3f6342e3ce413c1571f09544310` |

具体成品路径、DEX、完整 ABC/AOT 摘要和各平台配对编号以登记 JSON 为准。沿用包名、版本、地址及既有准入配对；本次登记不生成密钥，不更改服务端名单，不重新打包。Android 保留的旧 R11 LAN 变体不变，尚无本批同功能 LAN 成品。

## 行为与累计保全

教程未完整下载普通关卡表时，运营状态判断先识别真实 `TutorialQuestLogic` 并交回原有教程时间规则，不再提前读取可能为空的分类表。普通关卡仍按原控制读取。

装备占用说明和排序只将独立编队类别 5/6/7 的显示值归一到已有 Rush 类别；真实保存类别、编队内容、装备保护及分解资格不变，未知类别仍保留错误。共修改三个方法体；Android 与 iOS 分别在自身累计输入上接续，保留此前 release1031、主城、战斗 F1069、独立编队等已采用内容。

历史输入为 Android `ca180d7d...` 与 iOS `1990178a...`，完整旧登记保留在各自 lineage。旧构建器用于复现历史步骤，不能再次应用到当前修复包；Android 配方通过 `--record` 显式选择冻结的输入登记，同时固定 APK/SWF 摘要。

## 验证范围

- Android：比较 97013 个方法体及全部非目标声明/布局，只改三个目标体；6125 个非目标 APK 成员保持。最终 APK 的 Manifest/DEX AIR 身份、v1/v2 固定签名及对齐通过。实际生产方法导入受控 AIR 的 28 条定向断言通过，旧输入教程三入口和三类独立编队的负例已复现。
- iOS：三个真实 owner 方法重编译，完整 ABC 仍为 101873 方法，签名及类布局不变；移植方法的归一指令/控制流与 Android 对照一致。实际 IPA 独立回读只变 native/SWF，其他 3566 个压缩成员保持；三个原生入口、五处表项、150 处重定位、949 个此前编译函数、825638 个旧 rebase、89128 条旧展开边界及 EH/加载信息通过。六种签名布局模型通过；三张实际跳表及十五个破坏负例、三个入口参数 ABI 核对通过。
- 登记后运行 `verify_android_baseline.py --variant public` 与 `verify_ios_baseline.py`，确认登记能定位上述实际成品及完整 ABC。iOS 阶段使用 1536 MiB / 180 秒受限 Windows Job；已有成品验证结果复用，不重复 AOT 或封包。

本地证据位于 `F:/codex/work/new-player-c8601-20261101/` 的 `fix/`、`ios/` 与 `registration/`；交付目录为 `F:/codex/outputs/client-startup-equipment-fix-20261101/`。冻结构建回执仍保留生成时的候选/未登记状态，由本记录和新登记单独描述后续基线。

尚未执行重签安装、手机教学/装备页面、iOS native、公网游戏登录或真实账号翻页验收。此前设备记录不自动成为本包验收。漫画不在修复范围；本次源码与登记同步不改变云端业务、资源或玩家数据。
