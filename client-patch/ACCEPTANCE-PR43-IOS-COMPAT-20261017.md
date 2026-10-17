# iOS PR43 兼容新准入基线登记（2026-10-17）

本批 iOS 公网成品登记为 `accepted_offline`，作为后续 iOS 开发的直接输入。包为 ARM64 未签名 IPA，设备运行、重签安装及公网游戏运行未验收。当前没有同功能内网变体；内网需求从本公网基线转换，不回落旧包。

## 成品身份

| 项目 | 登记值 |
| --- | --- |
| IPA | `F:/codex/outputs/client-pr-port-20261017/StarPoint-iOS-1.8.4-pr43-compat-admission-public-20261017-unsigned.ipa` |
| IPA SHA-256 | `a7fbe01dca579602fda1ad622ff508c92a92824a954c025ca09f36478111f14d` |
| 字节数 | 169083144 |
| 原生程序 SHA-256 | `5b935dbdfdee81f0ea36f8172fc294a10a2f221fd95d7ce8ea558ebcac910167` |
| 游戏 SWF SHA-256 | `ddc513811d86dd0352b1cb69584bafc3c6d7f7ef1622ff00a6634b548eb98281` |
| 完整 ABC SHA-256 | `1c3bd2b748f7c1b12e983e9395e175eb7a106e29edd2c709bef58f068dbb3a8d` |
| Bundle / 版本 / Build | `com.kulo.wf` / `1.8.4` / `1.8.46` |
| 架构 / 方法数 | ARM64 / 101496 |
| 公网 origin | `http://124.222.203.221` |
| iOS 准入 ID | `ios-184-pr43-compat-public-20261017` |

完整 ABC 与 IPA 位于同一输出目录，文件名为 `ios-full-pr43-compat-admission-20261017.abc`。准入密钥和完整配对配置单独私有维护，不进入源码提交或玩家材料。新准入允许状态需由服务器应用既有配对配置后生效。

## 功能与历史保留

从 10 月 4 日 iOS 公网静态槽修复基线接续，移植 37 个通用方法、12 个超限方法、1 个商店辅助方法及 30 个新增方法；同步四项内置成长/台座资源。普通角色继续使用旧材料；具备超限资格且完成普通突破后才切换超限材料，缺少材料定义时只回退显示并禁用确认。

保留既有 HUD Number 字段布局、静态槽修复、缓存清理、Inaho 预载、标题与平台专属编队行为。R4 加载实现、离屏生命周期 guard 和 Android x86 补丁不进入 iOS。原完整登记保存在 `ios-accepted.json` 的 `lineage.previous_ios_baseline_registration`，不继承旧包的设备验收结论。

## 离线证据

- 原生编译实际覆盖 80 个目标函数；50 个旧入口、3 个共享别名、30 个新增表项、3802 处 ARM64 重定位及旧 flags/activation 前缀通过既有独立检查。
- 完整 ABC、运行时 SWF、AOT 摘要和方法数匹配；公网构造器地址、六种签名尾部及 TrollStore ldid 裁剪布局检查通过。
- 相对原输入仅 native、SWF 和四项 bundle 成员变化；准入轮换阶段仅 native/SWF 变化，其余 3566 个成员保留，80 个兼容功能函数及原生 ABI、AOT 数组和布局不变。
- 旧服兼容使用旧材料 master 和实际 AIR 窗口执行验证；1918 个断言、184 个窗口场景通过。该执行证据不替代 iOS 原生运行。

构建及方法证据在 `F:/codex/work/client-pr-port-20261017/ios/`、`compat-public/` 和 `admission-release/`；登记身份检查使用 [iOS 基线检查器](verify_ios_baseline.py)，源码流程见 [PR43 iOS 配方](pr43-ios/README.md)。

本登记不改变服务器、CDN、运行准入配置、签名或设备数据。功能支持随对应服务端数据与资源开放生效。
