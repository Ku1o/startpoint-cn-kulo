# iOS 新号 CDN 启动下载修复验收

日期：2026-09-30。当前登记为 `accepted_offline`，覆盖 IPA、完整 ABC、AOT、主 SWF、准入身份和静态路由模型；未进行真机或 TrollStore 重签运行验收。

## 当前成品

- IPA：`F:\codex\outputs\ios-startup-download-20260927-r2\ios\StarPoint-iOS-1.8.4-author-1047-startup-download-fix-20260927-r2-unsigned.ipa`
- SHA-256：`123fdafd38caff60b64bebf4bd2d7dc8f73a48de2e08ba5f99f8d9a79a20d769`
- 包身份：`com.kulo.wf` / `1.8.4` / `1.8.46`
- 准入号：`ios-184-author-1047-20260925`
- 完整 ABC：`F:\codex\work\ios-startup-download-20260927-r2\startup-download-full.abc`
- 完整 ABC SHA-256：`e100ae2f0d6b77ed278f91fda753df3402d7aa12a1b1867600c61f63e4b07f39`
- 完整 ABC 方法数：`101436`

## 修复范围

修复 `GlobalLoading.applyLoad`（方法 `41998`）的 CDN 资源加载门控。`isDownloaded(version)` 仍决定正常下载选择路径，`isAssetComplete()` 仍决定恢复路径；只丢弃该入口的 `needsDownloadAsset()` 阻断结果，使新安装或本地 CDN 状态缺失/不完整时可以进入既有下载与恢复流程。非 CDN 读取、完整包处理、下载选择、恢复回调、准入数据和既有 Boss AOT 方法保持不变。

## 静态验收

- IPA 成员列表与基线一致，仅 `worldflipper` 和主 SWF 改变。
- 原生改动为两个 ARM64 条件分支替换为 NOP，加上 20 字节 AOT 完整 ABC 身份，共 28 字节变更。
- 完整 ABC、主 SWF 身份、AOT 方法表和运行时 ABC 关系校验通过。
- `applyLoad` 路由模型覆盖 30 个场景，非 CDN 和已完成资源路径保持原行为，缺失/不完整 CDN 路径进入下载/恢复。
- IPA 的 LINKEDIT、签名尾部和 ldid 不同签名大小替换模型校验通过。

## 验收边界

本次登记为 `accepted_offline`。IPA 未签名，未进行物理 iOS 设备或 TrollStore 重签运行测试，未声明云服部署。静态报告位于 `F:\codex\outputs\ios-startup-download-20260927-r2\ios\ios-startup-download-static-verification.json`。
