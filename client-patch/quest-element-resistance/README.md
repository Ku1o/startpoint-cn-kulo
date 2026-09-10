# 按关卡配置的属性耐性入口

2026-09-10 用户要求从已验收 APK 制作测试版。本目录只实现 Android 通道和测试包，
不生成新塔，不更新资源清单或正式验收登记，不包含诊断器、玩家登录等其他候选改动。

## 输入与插入方式

直接输入为 `android-accepted.json` 的深渊续战 Lens 公网累计 APK，先运行
`python -B client-patch/verify_android_baseline.py --variant public`。
APK SHA-256 为 `c868534b575348dde825fcd4c88c156157174fd4444724f1141fd9aa95e32a2d`，
SWF SHA-256 为 `11c06fd77a0e3811164d196208ecce28cba5ec3a602e3d798f3c67d5d5b17e04`。
验收基线推进后构建器停止，需重新审计，不能跳过哈希保护。

仅在 `BattleQuestBaseImpl.getInitialEnemyConditions`（原 ABC 284、方法体 21496）
最后返回前插入九条指令：原五个条件解析完毕后，调用独立的 `cn.rules.QuestElementResistance.apply`。
原方法的每条指令、分支、异常处理均可还原；其他原方法、类定义和原常量池保持。
新增模块单独编译为一个类、五个方法体，以懒加载 DoABC 放在主 ABC 前。
主 ABC 容器序号变为 285，不改变主 ABC 内部方法索引。没有重新编译游戏类。

新增 QName 必须使用非零字符串索引的真实公开命名空间，不能使用 ABC 保留索引 0。
这是此前其他测试模块在 Android 出现 F1069 的已知错误，构建器显式断言这一约束。
新增模块使用现有 AIRSDK 51.2.1.5 的编译器、SWF 44 / Player 32 目标；
APK 内 AIR 33.1.1.620、application.xml、全部原生库及其他资源逐字节保持。
编译器版本和桌面测试不能代替原 Android 运行库验证。

## 内容配置契约

当前桥接载体是既有 `sub_name`，使用可读、精确匹配的标记，不增加旧客户端无法解析的枚举：

```text
原有副标题 【属性伤害：火=0.1%;水=0.1%;雷=10%】
```

- 只识别一个 `【属性伤害：...】` 块，分号、等号、百分号使用 ASCII；风、暗采用简体。
- 六属性对应原生 `ElementTargetKind`：火 1、水 2、雷 3、风 4、光 5、暗 6。0 为全属性，不接受配置。
- 数字表示本条额外耐性对应的普通伤害剩余百分比。转换 `r=100/percent-1`，再调用原客户端
  `Decimal_Impl_.fromFloat(r)` 和 `ConditionChangeContent.ElementResistance(element, rFixed)`。
- 允许百分比 `[0.0001,100]`，拒绝零、负值、非有限值、指数格式和重复属性；100% 不追加无效果条件。
- 至多五属性的比例可以低至 1% 或以下；六属性都有弱耐性合法。还会检查原初始条件与本次配置合并后是否六封锁。
- 未配置、缺少 `sub_name`、`Option.None` 均保持原数组。正常配置使用新数组，原有条件对象保持。
  损坏配置整体不生效并保留原有条件，避免因此造成 C7050；生成器发布前必须严格验证，不能依赖这一容错。
- 入口不绑定活动 ID、不执行随机数。最低两属性补足、保留已 roll 的更多封锁和最多五属性的规则属于 MOD 工具。

`BattleQuestBaseImpl` 为多数关卡保留原 master 行，RushEvent（含深渊）可直接读取此字段。
Tutorial、SkillPreview、DailyEvent 在构造时投影了部分字段，没有保留 `sub_name`，本次不在其中启用；
其他模式仍需确认其实际行具有该字段并走同一敌人流程，不能宣称全部模式均已实战验证。

原 `EnemyImpl` 出生初始化读取 `battle.initialEnemyConditions`，因此该入口不依赖 General Boss 的 pre-action。
普通伤害仍使用原生耐性计算，固定、比例等特殊伤害路径可能绕过它。Boss 自带耐性和战斗中减耐性仍会参与计算。
转阶段、召唤敌人、续战需要 Android 实战验收。

### 后续塔生成的配套约束

本包没有写入任何当前关卡配置，也没有硬编码测试楼层。正式塔生成接入仍未完成：

1. 先由已有 `guarantee_element_bans` 保留原卡并补足到 2～5 个封锁属性。
2. 合并完整的本层元素耐性后生成一个配置块；保留原卡的记录、展示和其他效果。
3. 同一份元素耐性只使用本通道一次，不能同时保留工具此前生成的同效果 Boss pre-action，否则重复累计。
   不得删除 Boss 原生动作或原生耐性机制。
4. 校验能力版本、配置序列化回读、禁用数量、原条件保留，并完成不同 Boss 类型和续战的游戏验证。
5. 旧 Android 和当前未移植的 iOS 只会显示标记，不会应用本通道；配套发布前必须处理客户端版本范围。

## 构建与验证

从仓库根目录执行，使用全新的任务工作目录和交付目录：

```powershell
python -B client-patch/quest-element-resistance/build_apk.py --work <新工作目录> --out <新交付目录> --sdk F:\codex\ios-rush-leaderboard-port-20260830\AIRSDK_51.2.1.5
```

FFDec 只窄导出两个类，并通过独立 Java 解析器比较原 96,404 个方法。
桌面 AIR 宿主加载本次 SWC 内的同一份 `library.swf`，不重新编译被测 helper；
351 项检查覆盖全部 62 个合法非空封锁子集、六封锁拒绝、六弱耐性、原条件/原数组保留、
固定小数转换、异常输入和合并后第六封锁拦截。游戏条件工厂与 Decimal 工厂由宿主替身提供；
这证明 helper 运行与参数正确，不能代替真实游戏战斗。

所有外部子进程均有超时和异常/取消后的进程树清理。签名只复用受保护 DPAPI 签名脚本，
密码不进入命令行或报告。每次不同 SWF 配新 AIR UUID，并检查 v1/v2、固定证书和 ZIP 对齐。

首次测试包：`outputs/quest-element-channel-test-20260910/`。
APK SHA-256：`7b3294b494c3c8cff7846e922c65477fee662af21884966c0b8cb6957592e5a4`。
AIR UUID：`a74a957b-ce1d-49ed-ad40-4d1472230c58`。
离线检查通过；Android/MuMu 安装、启动和战斗尚未实测。本次没有更改正式验收登记。

## 配套本地测试（2026-09-10 后续授权）

用户随后要求完成配套塔并同步本地。现在 `F:/startpoint-cn-main` 已启用资源 1.4.104，
保留原普通随机塔的全部 Boss/领域/HP，30 层补足属性封锁；称号及莱特兑换合入同一资源包。
APK 仍没有固定楼层代码，属性全部由资源提供。新内网包使用同一份 helper，直接从登记的内网累计基线构建，
通过 `build_apk.py --variant lan ...` 可复现；不会从公网包替换整类或退回旧 APK。

交付目录：`outputs/quest-element-channel-lan-test-20260910/`。APK SHA-256：
`8e21b793091415be13d13ac170a1dc53e89fb92a3d688c135deb86644a71bbcb`；新 AIR UUID：
`51e09b50-f15c-431f-9359-c9a55caf209f`。正式验收登记仍不变。

`tests/TowerHarness.as` 从最终资源 ZIP 提取的 30 条副标题运行同一 APK helper，
验证逐属性固定小数、封锁数量及原条件保留，全部通过。详细构建/同步/HTTP 记录见
`assets/asset-patch/audit/abyss-element-sponsor-laite-1.4.104-test/`。
这份内网包配合本地 1.4.104 用于实际战斗测试，前面的公网通道包说明是构建时的历史状态。
