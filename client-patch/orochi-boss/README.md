# 八岐大蛇高难客户端构建方法

本目录记录八岐大蛇高难 V2 客户端的可复用构建入口。APK 和 IPA 成品、SWF/ABC 中间文件、签名材料、准入密钥及本地构建报告不进入仓库；构建脚本从本机已验收输入读取它们，并在输出目录生成结果。

## Android

`build_public_android.py` 接收已验收的 Boss 内网 APK/SWF，使用现有 Android packager 完成内网地址到公网地址的字符串池替换、AIR `uniqueappversionid` 更新、zipalign、签名和 APK 成员回读。Boss ActionScript 不在公网转换阶段重新编译，输入 LAN APK 中的 Boss SWF 是功能载荷。默认输入和输出对应 2026-09-26 交付；可用 `STARPOINT_BOSS_LAN_HOST` 传入已验收的内网地址，并用 `STARPOINT_BOSS_LAN_APK`、`STARPOINT_BOSS_LAN_SWF`、`STARPOINT_BOSS_ANDROID_WORK` 和 `STARPOINT_BOSS_ANDROID_OUT` 覆盖路径。

## iOS

按以下顺序运行：

1. `prepare_ios.py` 从 Android Boss SWF 提取 Boss 方法，合并 `cn.boss::BossMechanicsRuntime`，把阶段、血量、弱点、同步字段和方法写入已验收 iOS 完整 ABC。带闭包激活帧的 `applySynchronizeKind` 保留原生入口并追加 AOT hook，避免改变旧 activation 布局。
2. `compile_ios.py` 调用 AIR arm64 headless compiler，生成 iOS AOT 对象。
3. `link_ios.py` 将新方法、方法表、激活信息、重定位和 SWF 摘要写入已验收 iOS 可执行文件；扩展既有 `__CNRECIO`/`__CNADTAB`，不新增 Mach-O 段。
4. `verify_ios.py` 回读 IPA、完整 ABC、运行时 ABC、准入常量、SWF 摘要、包身份、ZIP 成员和 TrollStore 签名布局。

准入配对从本机受限目录读取，只输出准入号和密钥哈希；脚本不会把密钥写入源码或报告。iOS 当前输出为 unsigned TrollStore 包，真机测试需另行完成。

## 当前离线验收基线

- Android APK：`85dbc5728e3dd74fee0989638c77b4f10641ced6e3da3be856db3e5409afb4fc`
- iOS corrected IPA：`f7c43c3b6ced56ba2cade636ac818cd7d7dc944aefe50573a05ec942ae6ffe4a`
- iOS 完整 ABC/AOT 方法数：`101433`
- iOS 新增/重定向 AOT 入口：`46`
- iOS 公网地址：`http://175.178.160.158`

这些数值用于构建回读和验收登记，不代表已完成真机战斗测试或云服部署。
