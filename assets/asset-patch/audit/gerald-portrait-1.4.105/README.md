# 杰拉尔立绘：1.4.105 第 2 分包

资源边为 `1.4.104 → 1.4.105`，本包序号为 `2`。五重美术任务统一登记共享 manifest；本任务只制作本分包与审计，不修改第 1 包或共享清单。

- ZIP：`assets/asset-patch/active/pinball-1.4.104-1.4.105-2-gerald-portrait.zip`
- 大小：5,876,402 字节。
- SHA-256：`57f0734e524faac79899f10624044b52bd4c2ede0c846ca3bf4e744e9d3536ec`。
- 共 33 个成员：common 4、medium 25、Android 2、iOS 2。

保留供方补包的 28 件图片/图集/Android 资源原始字节，并从该包对应 PNG 独立生成两件 iOS ETC2 RGBA 槽 3 纹理。两平台尺寸、11 个 mip 层及源 PNG 配对验证通过；iOS 每层完成解码验证。未使用 Android 字节改名代替 iOS。

三张共享表取本地已启用链的最新前像，仅合入下列 6 条原始记录；其他角色的行字节和顺序完全保留：

| 表 | 本次合入的键 |
|---|---|
| `master/generated/character_image.orderedmap` | `129992` |
| `master/character/full_shot_image_attribute.orderedmap` | `129992` |
| `master/generated/trimmed_image.orderedmap` | `character/unicorn_lancer_rose/ui/full_shot_1440_1920_0`、`full_shot_1440_1920_1`、`skill_cutin_0`、`skill_cutin_1`（后三项同前缀） |

原补包的尺寸差异保留并记录于 `report.json` 的 `geometry`：基础 PNG 为 1031×1513，表为 1039×1514；觉醒 PNG 为 1050×1423，表为 1039×1513。本次是原样补送立绘，不宣称完成布局修正或真机显示验收。

打包时重新核对全部 33 个成员对应的当前前像；与已有同边第 1 包逐路径检查，无交集。内层 ZIP 的 CRC、成员集合、逐件哈希、Android/iOS 配对及最终写盘字节全部检查通过。没有通过随包不兼容的 `publish_received.py` 运行发布，而是使用本项目独立的 `tools/lens-integration/prepare_gerald_portrait.py` 生成正确资源根和哈希路径。

`archive-integrity.json` 可供统一登记任务读取；`report.json` 包含每个成员的逻辑名、前后哈希、来源归档，以及每条表记录的前后哈希。稀疏前后副本位于 `F:/codex/work/gerald-portrait-1.4.105-20260911/`。

仅涉及现有角色的美术与显示定位，不改变持久化数据、存档 ID 或存档导入导出兼容性。未修改技能、数值、语音、像素、服务端代码、APK/IPA。无需因这份资源补包重新构建 APK/IPA。

本任务未提交、推送、同步运行目录、启动服务或向客户端发布，也未制作云服务器覆盖包。后续统一登记与版本交付由“五重决战入口与资源替换”任务负责。分包准备时 `staging` HEAD 为 `f440d283f84b84671d7cd2cfebdbe66d2d775448`；其他任务已有修改保留。
