# 双端深渊 EX 准入修正版验收

2026-09-18，Android 公网 APK 与 iOS unsigned IPA 登记为 `accepted_offline`，作为后续双端公网修改的精确累计输入。验收范围为成品身份、累计载荷、准入签名前缀与公网挑战/证明协议；没有新增手机安装或战斗验收。EX 第 20 关 Boss 血量异常仍在独立排查，不属于客户端准入修复的通过范围。

| 平台 | SHA-256 | 准入号 |
| --- | --- | --- |
| Android | `86bfa97f6f8479ddeda7084e08fc9144e10caaf2aaa2cbe01ad5a27fbbdd3a71` | `android-181-abyss-ex-20260917` |
| iOS | `068bd0cc82cd4c5c38380fe72b8c29e6807a8481e2c27613030c6f07769c67c2` | `ios-184-abyss-ex-20260917` |

成品位于 `F:/codex/outputs/abyss-ex-admission-fix-20260918/`。精确路径、SWF/DEX/原生程序/完整 ABC 摘要见两端 accepted registry。Android 内网登记保持原 R10 本地记录恢复版，不将公网 EX 包标为内网成品。

Android 保留 R10 性能、账号记录恢复及既有累计功能，并保留 EX 活动、续战和装备限制。准入修复只替换一个编译器折叠字符串；相对原 EX 包，方法体和其余 SWF 标签不变。AIR UUID 更新为 `0a43203d-f28f-4d2a-89fc-5f365a00b273`，DEX 缓存身份配套更新；原固定证书、v1/v2 签名及 ZIP 对齐通过。

iOS 保留幻想连战返回修复、累计 EX AOT 方法及原包身份，完整 AOT 101,287 个方法。修复运行 ABC 与完整 ABC 中的签名前缀，同步原生 AOT 和 SWF 摘要，保留原生指令、方法表、重定位及签名布局；三个 TrollStore/ldid 签名尾部模型通过。成品仍为 unsigned IPA，未进行真机测试。

从双端实际原包和修正版读取准入常量进行公网协议正反例验证：原 EX 包证明失败，修正版证明成功。只调用准入挑战/证明，没有登录玩家账号或修改玩家数据。构建入口增加折叠前缀检查；历史构建器使用 `abyss-ex/source-artifacts.json` 固定原始输入，避免登记推进后重复应用补丁。

本次不推进准入号、不轮换密钥，不修改服务器允许策略或旧版期限；不改变数据库、存档格式、账号归属和持久化 ID。私有服务器配置与二进制成品不进入 Git。服务器配置交付及实际部署状态独立管理。

执行 `verify_android_baseline.py --variant public` 和 `verify_ios_baseline.py` 可回读当前登记；`abyss-ex/verify_admission_prefix.py` 提供实际包准入正反例检查。历史构建回执保留生成时状态。
