# 作者机制公网 APK / IPA 验收

2026-09-25 对下列原始成品补做验收，登记为 `accepted_offline`。Android 另完成模拟器安装、首次启动与冷启动至登录面板；未登录玩家账号、未重测实战。iOS 未真机测试。原成品和 2026-09-24 构建报告保持不变。

| 平台 | 成品 SHA-256 | 正式准入号 |
| --- | --- | --- |
| Android 1.8.1 | `aeb1c87859b15642a5093140842d0f3b687dff0c06e8d253d3c1a3ecfb8a1596` | `android-181-author-1043-20260924` |
| iOS 1.8.4 / 1.8.46 unsigned | `310aa3665b6ea0bc621186c76550bd3bd36aeb122bf6670e32de511539488ecd` | `ios-184-author-1043-20260924` |

精确路径、SWF/DEX/原生/完整 ABC 身份见 [Android registry](./android-accepted.json) 与 [iOS registry](./ios-accepted.json)。方法见 [作者机制公网移植](./author-public-release/README.md)。旧 SET 公网包及作者机制内网包保留，内网 `user_accepted` 登记不变。

## 已完成检查

- Android 与已验收内网 APK 逐成员比较：4,172 个成员保持，SWF 仅 14 处端点或准入字符串变化；逆向恢复后全部 ABC 字节一致，96,654 个方法体及 trait 保留。DEX 六类回读仅两处缓存身份变化，AIR UUID 为 `68bc1d3a-0d57-4ead-bb53-e9876fbcad27`。固定证书、v1/v2 签名与 ZIP 对齐通过，37 项伤害、回槽来源与语音用例通过。
- Android 在独立测试用户中安装指定 APK，安装后的文件哈希与交付包一致；首次及冷启动均显示登录面板，未观察到崩溃。测试后恢复启动测试前备份的实际 APK，删除测试用户，原账号数据隔离。
- iOS 与 SET C8601 基线比较，仅主可执行文件和 SWF 变化，3,568 个 ZIP 成员完整。完整 ABC 与运行 ABC、AOT 摘要一致，方法表 101,387 项；18,131 处原生重定位及 100 个补注册方法通过，原 SET 入口及其余非目标字节保持。
- iOS 原字段偏移、枚举默认值、八个 ARM64 包装器执行场景、10 项规则字节码测试、15 个分类分支和四个构造场景通过。三种 ldid 签名大小模型通过，两个历史错误签名布局及 HUD 错位负例均被识别。此项验证签名布局，不代表 TrollStore 实际安装或真机启动。
- 26 项隔离准入协议检查通过，包括错平台/密钥拒绝、旧号并存、单端撤销和模拟时钟续期。两端实际公网地址的新旧四个版本号均完成 challenge/prove，HTTP 200 且平台匹配；未登录玩家账号、未修改服务器配置。

本轮没有生成安装包、推进准入号、更换密钥或修改角色/CDN。新旧版本仍获准入；不涉及存档结构或迁移。长时间联机、多人战斗和 iOS 真机未覆盖。

本地证据：`F:/codex/outputs/author-public-acceptance-20260925/`。身份检查器可继续直接运行 `verify_android_baseline.py --variant public`、`--variant lan` 与 `verify_ios_baseline.py`。
