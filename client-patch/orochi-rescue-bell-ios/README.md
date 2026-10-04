# 救援铃铛 iOS 端口（缓存清理与超级+ 内置排版）

本目录记录救援铃铛批次 iOS 侧的受控方法：把 Android 内网已验收的对应内容补到已验收 iOS 载体
（作者装备 F1009 IPA `4ce93ffe…`）。管线只生成编译器输入、执行 AOT 编译、链接与回读校验；
成品登记见 [`../ios-accepted.json`](../ios-accepted.json) 与
[`../ACCEPTANCE-OROCHI-RESCUE-BELL-IOS-20261004.md`](../ACCEPTANCE-OROCHI-RESCUE-BELL-IOS-20261004.md)。

## 固定输入

- 来源 IPA：`F:/codex/outputs/ios-equipment-f1009-fix-20261002/ios/StarPoint-iOS-1.8.4-author-equipment-standalone-20261002-unsigned.ipa`
  （SHA-256 `4ce93ffe967331b088032fa4d3e169c7d58b2c1cef4b10cf727e28906811bf40`）
- 来源 native / SWF：`1a427b648fc62297effb0dbc9982611b7f0e6e9d0e0623d46cebdbe72872b1dc` /
  `7e7e3642f19d59b3471bd6b09f344cf83b097924bc7a4bd094780deb7b793e72`
- 完整 ABC：`F:/codex/work/f1009-fullfix/equipment-ios-full.abc`
  （SHA-256 `83149cffbef675fb0661a3072725473e4c49817c645bc069516124dc094b1097`，101,458 方法）
- 内置 payload：来源 IPA 内
  `Payload/worldflipper.app/asset/production/ios_bundle/dc/bcccb129122c0189c8eab004ecc4516a077f3e`
  （官方 466 字节 `bf37fe2f…`）

## 变更

- 超级+ 内置排版：用 [`../orochi-rescue-bell-superplus/build_embedded_layout.py`](../orochi-rescue-bell-superplus/build_embedded_layout.py)
  的 `compact_payload()` 从官方 466 字节 payload 现场推导 480 字节紧凑居中 payload
  （`f9cba755d3c5d63f334989fd0a0a21b7f169f0fbede9e77e3178f4efa5568125`），替换 IPA 内同路径成员；
  仓库不保存该二进制。
- iOS 等效 AIR 启动缓存清理：`cn.mod::AuthorState` 追加 5 个静态方法
  （`ensurePeriodicCacheCleanup`、`periodicCacheTick`、`purgePeriodicCache`、
  `writePeriodicCacheDiag`、`ensurePeriodicCacheCleanupBridge`）与 2 个静态槽；每 600,000 毫秒仅删除
  `File.cacheDirectory/app` 与 `File.cacheDirectory/.AIR`，失败容错并按周期覆盖写有界诊断。
  启动钩子为 `pinball.loading.global::GlobalLoading/applyLoad` 原生入口（VA `0x105376DF8`）的
  56 字节包装器：保存 x0–x7/x29/x30 → 调用桥（4 参数与 applyLoad 原生寄存器形状一致，桥内用
  `getlex` 载入类对象）→ 恢复 → 补执行被替换首指令 → 跳回入口+4。
- C8016 `InahoAbilityVisuals` 预载：不改。已验收 iOS helper 的 `preload` 无条件加入全部 6 个
  Layout，覆盖嵌套索引 13/14，缩小守卫会引入未验证行为。

## 管线

```powershell
$env:OROCHI_IOS_PORT_WORK='<新的空工作目录>'
$env:OROCHI_IOS_PORT_OUT='<输出目录>'
python -B client-patch/orochi-rescue-bell-ios/prepare_port.py
python -B client-patch/orochi-rescue-bell-ios/compile_port.py
python -B client-patch/orochi-rescue-bell-ios/link_port.py
python -B client-patch/orochi-rescue-bell-ios/verify_port.py
```

默认目录为 `F:/codex/work/orochi-ios-port-20261004` 与 `F:/codex/outputs/orochi-rescue-bell-ios-20261004`。
链接器拒绝覆盖已有输出，重复运行需使用新的工作目录。工具链：AIR SDK
`F:/codex/ios-rush-leaderboard-port-20260830/AIRSDK_51.2.1.5`、AOT 辅助
`F:/codex/ios-rush-navigation-port-20260907`、`F:/codex/tools/ios-re-libs`、附加 helper 映射
`F:/codex/work/lens-ios-20260908/additional-helper.json`；私有准入配对从
`F:/codex/.codex/secrets/starpoint-client-admission/releases/author-1047-public-20261001/` 读取。

## 复现结果

以本目录脚本重跑 `prepare → compile → link → verify` 得到与登记一致的 IPA
`284f725c71f3582c7eb14f4341a42b26534dcd5907233c688544b1ae1988da47`（101,463 方法，仅 3 个成员变化）。
`port.json`、`ios-build-report.json`、`ios-verification-report.json` 与完整 ABC 留在任务输出目录，
不进入 Git。

## 边界

IPA/native/SWF/ABC/编译产物/报告/签名材料与密钥不提交；未真机测试；未部署云服；CDN、准入材料与
包身份保持不变。
