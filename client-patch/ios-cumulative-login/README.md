# iOS 累计登录、深渊详情与 Lens 0910（2026-09-11）

## 当前已验收成品：公网 HUD 初始化修正版 R4

2026-09-11，用户明确表示“ipa也验收了，然后提交修改内容到github”。已回读原交付 IPA、原生程序、主 SWF 和配套完整 ABC，将 R4 登记为后续修改的直接基线；见 [验收记录](../ACCEPTANCE-IOS-R4-20260911.md) 和 [当前登记](../ios-accepted.json)。用户验收单独记录，不改写下方历史构建报告，也不推断每个功能的独立真机测试结果。IPA 仍为原 unsigned 成品，没有重新打包或签名。

用户确认 R3 在深渊第四层加载至 93.38% 时触发 F1009，Android 正常。日志定位到 `HudMemberStatus.run()`；新增的三个整数语音计数字段移动了原有对象引用的内存位置，但保留的原生初始化代码仍按旧位置读取。

R4 从实际 R3 公网成品继续，将三个计数器改为尾部 Number 存储，并明确按整数读取，保留原有字段位置及语音轮换。现已获用户验收；成品为 `F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-login-abyss-hud-public-fix-r4-20260911-unsigned.ipa`，SHA-256：`560d5787411dfa1b603a9c8f0b4fba46f045e02531256e476df5b6474d822fae`。

详见 [R4 原因、修改方法与测试记录](./HUD-F1009-FIX-R4-20260911.md)。保留 R3 公网登录、R2 TrollStore 签名布局及全部累计功能；无服务器、CDN、塔配置或存档修改。构建准备器和原生校验器也已补上 HUD 字段偏移保护。下方 R2/R3 的锁定哈希用于历史复现，不能用于绕过新基线检查；新累计构建必须保留此修复并再次核验实际初始公网地址。

## 历史测试成品：公网登录地址修正版 R3

R2 已有用户截图显示能够启动并打开登录面板，但报告连接不上。核对发现：iOS 原生构造器的初始地址仍为官网 HTTPS，稍后的版本查询才将其改成公网；登录面板会提前捕获并保留初始地址，失败后重试也不重新读取它。

R3 在 R2 成品上只改一个协议常量加载指令和一个主 AOT 字符串池中的主机名，将初始地址设为 `http://175.178.160.158`（默认端口 80），与云服版本配置完全一致。保留 R2 全部累计功能、存档路径与 TrollStore 签名布局。没有使用 AIR 桌面运行器或重新编译游戏方法。

成品：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-login-abyss-lens-public-fix-r3-20260911-unsigned.ipa`；SHA-256：`61a545ea867e97837fee2204c1649e362d6e3be2d98aa80abd3931111354a9af`。离线检查与公网空请求验证通过，仍需巨魔覆盖安装确认旧存档检测、绑定/登录和开始游戏；未提交、未部署服务器、未登记验收。

详见 [R3 原因、修改方法与测试记录](./PUBLIC-ENDPOINT-FIX-R3-20260911.md)。后续累计重建不能仅运行下方历史 R2 编译步骤就交付，必须继续执行 `public_endpoint.py` 和 `verify_public_endpoint.py`，或从随后明确验收登记的 R3 基线继续。

## 历史测试成品：TrollStore 启动修正版 R2

第一份 `launch-fix` 真机仍闪退，日志改为 `unknown rebase opcode 0xF0`。用户确认使用 TrollStore；其 `ldid` 会按符号字符串表结尾重新分配签名区域，第一份修正遗漏了这个裁剪边界。

当前交付为 `F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-login-abyss-lens-trollstore-fix-r2-20260911-unsigned.ipa`，SHA-256 `171f0eb1d1671c9684c1ee9829af4b7f29a9ccc7481ec42144743c51cc2e6d7c`。新增数据现放在字符串表之前，字符串表与签名的偏移同步更新；游戏代码、SWF、完整 ABC 与公网配置保持原样。

详见 [R2 修正与验证记录](./TROLLSTORE-FIX-R2-20260911.md)。八项回归通过，按 `ldid` 源码规则对前一包重现 0xF0，R2 在相同裁剪下保留全部加载数据。仍需用户使用巨魔覆盖安装进行真机复测，尚未登记验收或提交。

R2 工作目录为 `F:/codex/work/ios-cumulative-launch-fix-r2-20260911/`，侧件为 `F:/codex/ios-artifacts/login-abyss-lens-trollstore-fix-r2-20260911/`。复现入口现输出 `trollstore-fix-r2` 文件名；本次测试将 `STARPOINT_IOS_CUMULATIVE_WORK` 设置为 R2 工作目录后运行下面相同的验证及 unittest 命令。

## 首次启动修正记录（已被 R2 替代）

用户真机报告初版一启动即闪退。当前测试成品改为 `F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-login-abyss-lens-launch-fix-20260911-unsigned.ipa`，SHA-256 `77757cb88ed43593d1df3ab48b7d4fc0601476362163a013c20159f3e3832499`；原生 SHA-256 `8b9bf60a1d8d2044cb236028f270bc393b95d464d776a8a2614d3422f2452a4a`。下方初版成品哈希及记录只作历史，不能再向玩家发放初版。

这次只修正原生封装布局，游戏代码、SWF、完整 ABC、公网配置及全部累计功能与初版相同。签名块移到新增重定位流之后，补齐构建器和独立验证器的签名区域检查，以及五项回归测试。详见 [启动闪退修复记录](./LAUNCH-FIX-20260911.md)。修正版仍未签名、未真机验证，不推进 `ios-accepted.json`，未提交或部署服务器。

修复工作目录为 `F:/codex/work/ios-cumulative-launch-fix-20260911/`，交付侧件为 `F:/codex/ios-artifacts/login-abyss-lens-launch-fix-20260911/`。原有复现命令会输出带 `launch-fix` 名称的新包；执行本次回归测试时先设置 `STARPOINT_IOS_CUMULATIVE_WORK` 指向修复工作目录，再运行 `python -X utf8 -B -m unittest discover -s client-patch/ios-cumulative-login -p test_signing_layout.py -v`。

以下为累计移植范围与初版历史记录。

从 9 月 9 日登记的深渊续战 Lens IPA 接入当前 Android 累计登录版的客户端功能。成品为 **unsigned、离线验证通过、待真机测试**；没有重签、安装、云服部署或修改已验收登记。本轮源码尚未提交。

## 成品与输入

- 新 IPA：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-login-abyss-lens-20260911-unsigned.ipa`
- IPA SHA-256：`54a305686a8cf0ae9ad6f1ea3158d34009a7eb0a7221e807de334570d56ebe2a`
- 原生程序 SHA-256：`ca2fda4fa34a87ed0cdf092783c01a583255b9baf70a01e6de7d50e04bb82b52`
- 主 SWF SHA-256：`547d3436f4e558df2a3ce0a4f6660bde94da2283009172a59007c92c476a9dc3`
- 报告及后续 AOT 输入：`F:/codex/ios-artifacts/login-abyss-lens-20260911/`
- 本轮工作目录：`F:/codex/work/ios-cumulative-login-details-20260911/`

历史累计步骤的直接输入现归档在 `accepted-history/ios-abyss-autostart-20260909.json`，为 `StarPoint-iOS-1.8.4-abyss-autostart-lens-20260909-unsigned.ipa`，SHA-256 为 `8e6fb8cc4de6fe1c79efaded8e4ab1159c012645bdc3a52a22e19562e0661193`。仅使用 `--reproduce-accepted-20260909` 时核验并读取该旧输入；新任务先运行 `verify_ios_baseline.py`，从当前登记的 R4 继续。

Android 行为输入是 `outputs/player-login-cumulative-lan-test-20260910/StarPoint-CN-1.8.1-player-login-abyss-lens-lan-test.apk`，SHA-256 为 `27de717e8864ea35a329032fa3f7dc23e8d99e3f6187b411a39f321d1509a200`，其中 SWF SHA-256 为 `c667815ff871e12705e665267640db480f7c959e1c6bb4d852016f1e4923d6ed`。仅移植指定方法与三个模块，不把 Android 连接地址或存储路径带入 iOS。

## 功能范围与测试清单

| 功能 | 本次接入及测试重点 |
| --- | --- |
| 登录 | 注册、账号密码登录、旧存档绑定、UID 继承与管理员绑定码、找回密码重置码、记住登录最长 30 天、本地多账号及移除账号。测试有旧存档与空设备两种入口、错误提示、键盘与滚动、新设备登录后的旧会话处理。 |
| 标题流程 | 登录确认后“继续游戏”关闭弹窗、停留原标题，再点开始；原继承入口按累计登录方案调整。确认返回标题与反复打开/关闭不会卡住或重复提交。 |
| 深渊界面 | 顶部简短摘要、“关卡详情”入口、诅咒/领域/属性封锁/血量分段滚动。重点看 1、26、27、30 层与长描述。 |
| 属性伤害通道 | 读取关卡属性伤害配置，具备通用关卡支持；实际至少 ban 两属性、排除雷及 PF 调整由现有塔配置决定。测试被 ban 属性近零、雷属性正常及跨层切换。 |
| Lens 0910 | 灼晒 1499901 的敌方能力伤害耐性处理（每层 -15000，最多 3 层）；夏白 Fever 语音、两组就绪轮播及杰拉尔四段轮播，缺资源回退；额外预加载夏白两条、杰拉尔三条路径。测试普通/Fever 状态、多人/单人及重复就绪。 |
| 旧功能保留 | MOD 五合一、幻想连战、角色轮播、Rush 排行榜及资料导航、真实关注按钮与本人资料路由、深渊装备门控、700099 续战队伍跨层复用、Lens 724 Fever 与 422 冲刺、稻穗 PF 连击、基诺维冲刺、五重地图及手动 Auto 锁、5900101 铁钢限制。iOS 原有 CNtips_b 行为保留。 |

本包保留 bundle ID `com.kulo.wf`、版本 `1.8.4`、build `1.8.46` 以及原 iOS 服务地址和存储位置。没有新增自助修改密码入口或游戏内账号按钮；星导石客户端上限修改已由用户取消，不在本次范围内。

需要配套已交付的登录服务端及 **1.4.104** CDN。塔配置、奖励预览数据、称号、兑换、角色美术与物品图标在此前服务端/CDN 整合内容里；不能只安装 IPA 就视为这些资源已经更新。本次没有重制 CDN 或云服包。

存档影响：客户端接入已完成的账号协议，不新增存档物品/角色 ID、数据库表或迁移。保留 iOS 原存储路径，使用已有服务端的绑定及导入导出兼容修复。本轮未对真实存档执行导入；此前服务器测试不能替代本次 iOS 旧存档绑定和账号切换真机测试。

## 原生移植方法

`prepare.py` 追加常量池、类及方法，不重排原有 ID。三个模块分别为 `cn.rules.QuestElementResistance`（5 方法）、`cn.ui.AbyssDetails`（13 方法）、`cn.account.PlayerLogin`（93 方法），主单元方法数从 101071 增至 101182。HUD 初版的三个 int 状态槽已按 R4 修为尾部 Number 槽和整数读取，并检查原字段偏移、无子类布局冲突及原有 activation 布局一致。

现有原生入口更新如下；表内是方法 ID，不能当作 ABC body 索引：

| iOS 方法 ID | 入口 |
| --- | --- |
| 22984 | BattleQuestBaseImpl.getInitialEnemyConditions |
| 78941 | QuestTranslator.translateFormattedQuestNumber |
| 86421 | PartySelectTopPanelView.baseRun |
| 61694 | ConditionSlot.getOneSideTotalAbilityDamageResistance |
| 65161 | SquadManagerImpl.invokeActionSkill |
| 63979 | HudMemberStatus.update |
| 18394 | BattleCharacterLogic.resolveFollowingPathCollection：追加预加载后执行原函数 |
| 91141 / 91139 | TitleScene.afterTransition / disposeTitleScene |
| 32429 | RequestQueue.startRequest |
| 34260 | SockletConnection.socket_connected |
| 40659 | TitleMenuDialogContentView.setupContents |
| 85036 | MenuTopScene.createMenuListData |
| 7607 | ChannelSDKDummy.startLoginServer |

AIR 51.2.1.5 的无窗口 arm64 编译器仅编译增量。编译输入中无关旧方法使用返回占位体；**交付原生程序保留它们的原有机器码和运行时元数据**，不会把占位体替换到游戏中。编译所需的旧类脚本初始化声明也只存在于编译输入，原有原生初始化函数保持原样。

旧编译器无法稳定编译 Android 重建的完整语音收集函数。最终做法是编译原 Android 方法中新增的 48 条预加载指令及相同的音效/主角色/就绪语音条件，再通过 arm64 包装器先调用这段增量、恢复 x0–x5、fp/lr/sp、执行原入口第一条指令并跳回原函数余部。原语音收集函数和元数据保留，不交付取消语音的诊断版本。

`build_native.py` 添加 RX `__CNUPDATE` 与 RW `__CNACCT`，保留旧 `__LENS`、`__ABYAUTO`，更新主 AOTInfo、方法表、activation 表与 dyld rebases。三个模块与 14 个入口共 125 个编译函数，另有语音包装器；不添加 RWX 段。主 SWF 只更新与新 AOT 单元对应的 20 字节标识。

`map_runtime.py` 用 SDK 对象代码与基线程序的唯一匹配证明新增 AIR helper 地址，并从已匹配访问器解码真正的 `_builtin_traits_any` 槽地址。不能用推测地址或空常量替代。SDK AOTInfo 通过其 ABC SHA-1 定位。

历史 R2 编译输入 `cumulative-full-r8.abc` 的 SHA-256 为 `b3d4c1e7aea35df9f50bf080d201f7f84de1a0ecd0943359de25d399b7dbef40`，SHA-1 为 `3fef244c36ef09eefb2d120cee4359dcfc3e9bcf`。当前后续修改使用登记的 `login-abyss-hud-public-fix-r4-20260911/cumulative-full-r4.abc`，SHA-256 为 `7151e3d2ffb4e03e2204e5630011d98e5e8a7c0d3f29c073c7bafbe71b6547e8`；不能把历史输入或 stripped runtime ABC 误当当前完整编译输入。

## 本机复现

依赖 Python、本仓库 `lens0907-0908` 的 ABC 工具、`F:/codex/ios-rush-leaderboard-port-20260830` 的 AIR SDK/284 份依赖 ABC/原生链接工具、`F:/codex/ios-rush-navigation-port-20260907` 的旧段保护定义及 ZIP 元数据工具、`F:/codex/tools/ios-re-libs` 的 LIEF/Capstone、先前 Lens helper 地址证明。还需要 9 月 9 日完整 AOT 输入 `F:/codex/work/ios-abyss-autostart-lens-20260909/abyss-full.abc`。缺失依赖必须补齐，不跳过哈希断言。

在源仓库 PowerShell 中，选一个新的任务工作目录后依次执行（默认目录已有成品时，构建器拒绝覆盖）：

```powershell
$env:STARPOINT_IOS_CUMULATIVE_WORK = 'F:/codex/work/ios-cumulative-login-reproduce'
python -X utf8 -B client-patch/verify_ios_baseline.py
python -X utf8 -B client-patch/ios-cumulative-login/prepare.py --reproduce-accepted-20260909
python -X utf8 -B client-patch/ios-cumulative-login/map_runtime.py
python -X utf8 -B client-patch/ios-cumulative-login/compile_native.py --attempt compile-r8
python -X utf8 -B client-patch/ios-cumulative-login/build_native.py
python -X utf8 -B client-patch/ios-cumulative-login/verify_native.py
Remove-Item Env:STARPOINT_IOS_CUMULATIVE_WORK
```

使用的是 `compile-abc-64.exe`，没有启动桌面 AIR/ADL 运行器。编译子进程超时会清理进程树。最终 r8 共 7 个对象；先前失败编译目录和大体积 IR 是可清理的诊断临时文件，不是交付输入。

## 已完成验证及边界

- 回读 IPA 3568 个成员，只有原生程序和主 SWF 不同，包身份与其他成员保持原样。
- 原有 101071 个方法 ID 保留；新增 111 个方法与 Android 模块指令及 activation 布局一致，14 个现有入口逐项检查。
- 独立反汇编核对 3532 个原生重定位、入口跳转、语音包装器寄存器/栈保存，以及 92709 项新增 dyld rebases。
- 检查 Mach-O 文件边界、段权限与对齐；原代码允许修改范围外的字节、旧 Lens/续战段、旧 LINKEDIT 载荷保持原样。
- 完整编译输入、运行时 ABC 与 SWF AOT 标识一致；端点、存储路径和 iOS CNtips_b 相关旧代码保持。

这些是离线检查，尚未完成 iOS 签名安装、键盘、联网登录或实战验收。成功交付并不自动推进 `ios-accepted.json`；后续需用户明确验收，再按实际证据登记。
