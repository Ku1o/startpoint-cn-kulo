# iOS 类静态槽位移 F1009 记录（2026-10-04）

平台：iOS unsigned IPA（TrollStore 安装流程）。范围：救援铃铛批次 10 分钟 AIR 缓存清理。
本文记录 2026-10-04 公网候选进入副本 F1009 的原因、证据与修复方式，供后续 iOS 端口复用。

## 现象

- 2026-10-04 晚公网 iOS 客户端进入副本即弹「发生错误。（错误码：F1009）」。
- 服务端 stdout 崩溃记录中，35 条 iOS 记录里 34 条栈顶为
  `cn.mod::AuthorState$/getGauge()` ← `pinball.scene.battle.battle.ability::MemberAbilityTotalizerImpl/get wfGaugeRules()`
  （另 1 条同样来自 iOS，上行日志截断）；同一时间窗内 83 条 Android 崩溃记录没有该签名。
- `F1009` = `TypeError: Error #1009`（空对象引用）。

## 根因

10-04 候选把缓存清理状态 `periodicStarted:Boolean`、`periodicTimer:Timer` 作为**静态字段**追加到
`cn.mod::AuthorState`，与该类已有的 `gauge`/`damage`/`context` 同处一个类对象槽区。AIR arm64 的
类静态槽按类型排布（32 位标量在引用字段之前），新增的 Boolean 占用了第一个槽，`gauge`/`damage`
的槽偏移整体后移 8 字节：

| 方法 | 载体编译偏移 | 10-04 全 ABC 编译偏移 | 10-04 包内实际链接的旧代码 |
| --- | --- | --- | --- |
| `AuthorState.getGauge` (101323) | `0x30` | `0x38` | `0x30`（未重编译） |
| `AuthorState.setGauge` (101324) | `0x30` | `0x38` | `0x30`（未重编译） |
| `AuthorState.getDamage` (101325) | `0x38` | `0x40` | `0x38`（未重编译） |
| `AuthorState.setDamage` (101326) | `0x38` | `0x40` | `0x38`（未重编译） |
| `ensurePeriodicCacheCleanup` | — | `periodicStarted` = `0x30` | 新方法，已链接 |

10-04 链接器只追加新方法（`method_redirects` 为空），因此四个既有访问器仍是载体 AOT 代码。
进入副本构造成员能力汇总时 `get wfGaugeRules` 读取 `getGauge`，代码从类对象 `+0x30` 取
`gauge` 字典，实际取到 `periodicStarted`（类创建默认 0）；空值分支跳到运行时 helper
（`0x10b74a9f0 → 0x100a2676c`，`mov w1,#0x3f1`）抛出 `TypeError #1009`，与日志栈完全一致。

A/B 对照用同一 AIR AOT 编译器分别编译载体全 ABC 与 10-04 全 ABC 得到上表偏移；控件实验证明
偏移变化只由新增的两个静态字段引起。

## 影响范围

- `getGauge`：进入副本（首个读取）必然抛 F1009；`setGauge` 会把数组写进 `periodicStarted` 槽；
  `getDamage`/`setDamage` 读到 `gauge` 槽，damage 规则通道错位；`context` 相关路径按名字解析，
  未在本批崩溃栈中出现，但同批布局变化需一并复核。
- Android 不受影响：解释执行按名字解析槽位，没有固定的类静态槽偏移。

## 修复

- 新增独立类 `cn.mod::CacheCleanupState`（`client-patch/orochi-rescue-bell-ios/src/cn/mod/CacheCleanupState.as`），
  承载两个静态字段与 5 个静态方法；`ensurePeriodicCacheCleanupBridge` 仍保持 4 参数原生桥形状。
- `cn.mod::AuthorState` 的 class/instance trait 列表与已验收载体逐字节一致，既有 AOT 访问器继续有效；
  本次新增 8 个方法（脚本初始化、ctor、cinit 与 5 个方法），AOT 方法表从 101458 扩展到 101466。
- `prepare_port.py` 拒绝既有 class/instance/body 字节变化并单独断言 `cn.mod::AuthorState` 一致；
  `compile_port.py` 增加编译期门槛：载体与本次重编译的四个访问器槽立即数必须一致（`0x30/0x30/0x38/0x38`），
  且本批新方法不得出现 `Verify error`；`verify_port.py` 独立复核 `authorstate_untouched`、
  新类结构与 `accessor_slot_guard`。

## 成品身份（离线校验）

- IPA：`F:/codex/outputs/orochi-rescue-bell-ios-fix-20261004/StarPoint-iOS-1.8.4-orochi-rescue-bell-cache-10m-fix-20261004-unsigned.ipa`
- IPA SHA-256：`df4afd7b6f4eb113424eb82f04919862f156b3424cffb21f400dd1bdd497a45f`
- 原生可执行文件 SHA-256：`d3f3514cf893897ddaae23aba9adbe25e3704b436d3204a8e001e8f2932b1706`
- 主 SWF SHA-256：见 `ios-build-report.json`；仅 AOT 摘要 20 字节变化
- 完整 ABC：`F:/codex/work/orochi-ios-cachefix-20261004/cache-cleanup-full.abc`
  （SHA-256 `fc9a927cbb9fa9a4eaa6b27311df12d4c908617c29ed1d7539bd9a8c3c6f492f`，101,466 方法，
  SHA-1 `9e6929ee8aed9a570cef113584a5e6bb82cfc1ea`）
- 变更成员：原生可执行文件、主 SWF、内置 payload，其余成员逐字节一致
- 校验报告：`ios-verification-report.json`（`status=verified`，无失败项）

## 未验证与边界

- 未真机安装、启动或计时验证；离线结论不替代 TrollStore 实机验收。
- 未提交、未推送、未部署云服，未改 CDN active 链与准入配置。
- 2026-10-04：修复包已迁移到新公网地址并登记为当前 iOS 基线（`66b1057c…`，`accepted_offline`）；
  10-04 旧候选与它对应的公网迁移包标记为停用，见 `ios-accepted.json` 的 `lineage.superseded_artifact`
  与 `lineage.superseded_public_migration`。
- 10-04 候选产物保留在 `F:/codex/outputs/orochi-rescue-bell-ios-20261004/` 供复现，不再分发。
