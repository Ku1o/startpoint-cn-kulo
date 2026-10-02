# 作者机制 1.4.1047 双端客户端验收

日期：2026-09-25。Android 公网 APK 与 iOS unsigned IPA 的当前成品均已确认可验收，登记状态为 `accepted_offline`。本记录确认交付物身份与离线检查结果，不声称完成本轮新增真机战斗测试。

## 成品

| 平台 | 文件 | SHA-256 | 准入号 |
| --- | --- | --- | --- |
| Android 1.8.1 | `F:\codex\outputs\starpoint-cn-merge-20260925\android\StarPoint-CN-1.8.1-author-1047-gauge-public-20260925-final.apk` | `81651b9d1990171487197ed4d65f2e609a2eb5d804ec1e1b6b61ea3a388b75ec` | `android-181-author-1043-20260924` |
| iOS 1.8.4 / 1.8.46 unsigned | `F:\codex\outputs\starpoint-cn-merge-20260925\ios\StarPoint-iOS-1.8.4-author-1047-gauge-public-20260925-unsigned.ipa` | `e884eed2a859b2de0dfae40365c3aa7497ebf847f7d513db9a9545daf7f50a95` | `ios-184-author-1043-20260924` |

两端继续使用公网地址 `http://175.178.160.158`；包身份、版本号、签名证书/unsigned TrollStore 布局和既有准入配对保持。

## 本次客户端改动

- Android：`MemberImpl/applyInstantAbility` 与 `MemberAbilityTotalizerImpl/wfBlocksGauge` 加入回槽特效性能拦截和来源筛选；非目标 APK 成员保持，ZIP 对齐与 v1/v2 签名通过。
- iOS：在已有 AOT 编译 hook 上实现同一两处逻辑；原生目标方法本体保持字节一致，完整 ABC/AOT 方法表为 `101387`，重定位检查 `18168` 处通过。
- 资源：服务器已登记并融合 1.4.1047 风巨蜥增量包，资源链版本为 1.4.119。

## 检查范围

Android 构建报告为 `F:\codex\outputs\starpoint-cn-merge-20260925\android\StarPoint-CN-1.8.1-author-1047-gauge-public-20260925-final.build-report.json`。iOS 通过 `F:\codex\outputs\starpoint-cn-merge-20260925\ios\verification-report.json`、10 项规则测试、15 项环境分支、4 项构造场景、3 种 ldid 签名模型及 2 个历史错误布局检查。两端本轮未新增真机或多人战斗测试。
