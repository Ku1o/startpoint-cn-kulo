# 作者机制公网 Android 验收记录（2026-10-01）

本记录登记已确认的作者机制公网 Android APK，作为后续 Android 任务的精确公网基线。成品由已验收内网 Android 1047 载体转换而来，保留既有 SWF/DEX 内容，并切换公网地址与新的准入身份。

## 成品身份

- APK：`F:/codex/outputs/author-public-merge-20261001/StarPoint-CN-1.8.1-author-merge-public-20261001-public-7c47c340.apk`
- APK SHA-256：`955d1fef6844285f06f37ab9fa997b33721ca2a67caa6a547874ba662a2a40cf`
- 内嵌 SWF SHA-256：`b0b44b37d4f5d6492ff17f58158823515ea8e2875291974a3c29a0aff10246f6`
- `classes.dex` SHA-256：`280e64891f48b1b50b8bab85aa4daa5196e3d69d9669c6a6eb6d570273adb318`
- AIR `uniqueappversionid`：`7c47c340-fe66-4755-ab66-599a33aa18a2`
- 公网地址：`http://175.178.160.158:8001`
- 新 Android 准入号：`android-181-author-1047-public-20261001`
- 旧 Android 准入号未嵌入新 APK；服务端配对仍保留旧安卓和旧 iOS 校验项。

## 验收结论

登记状态为 `accepted_offline`，用户已确认使用该成品；Codex 未进行实体设备测试。APK 通过 ZIP 成员、SWF/Dex 身份、AIR 缓存 UUID、公网地址、v1/v2 签名、ZIP 对齐和固定签名证书检查，保留 4,172 个非目标成员。

验收报告：`F:/codex/outputs/author-public-merge-20261001/acceptance-report.json`

本次没有改变存档结构、服务端资源或 CDN；APK 和准入密钥配对不提交 Git。
