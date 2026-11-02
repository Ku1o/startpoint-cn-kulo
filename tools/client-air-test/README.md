# StarPoint 客户端代码验收

固定入口：`<repo>/tools/client-air-test/run.py`。在桌面 AIR 中执行指定 SWF 的真实方法，不启动模拟器、不截图、不点击。用于本地业务修复验收；不代表手机、画面、原生扩展、真实网络或 iOS AOT 已验收。

## 每次怎么用

1. 确认本次实际源码/worktree、目标 SWF 和要验证的行为。SWF 必须是本次明确选定的输入；仅服务端修复可用已确认的目标客户端，客户端修复须用包含新补丁的 SWF。未直接给出路径时，先按当前登记或任务成品台账定位并核对，不把历史样本当默认输入，也不把 Android 结果外推 iOS。
2. 按下表选择 suite 和业务 group。已有案例直接复用；只在新增行为或发现缺口时补案例，不为每次测试另写一套工具。没有相关覆盖时明确指出缺口。
3. 指定一个尚不存在的仓外输出目录。运行后读取该目录 `result.json`、`manifest.json` 和对应 `suites/*/receipt.json`；总体 passed 还须结合实际覆盖范围解读。
4. 输入、源码、工具及有关条件未变化的有效结果可以复用；改动后只重跑受影响部分。源端改动使用新生成的真实回包。

执行本工具属于代码测试，不自动提升 accepted registry；版本采用或登记需要对应的明确指令。

| suite | 覆盖 | 选择方式 |
| --- | --- | --- |
| `queue` | 请求身份冻结、重试与终止分支 | 不需要服务端回包 |
| `common` | 通用回包解析、库存/角色/货币更新、回调顺序；另有小型非法输入案例 | `--groups tutorial,mail,equipment,crazy` 中选相关项；完整 load 明确排除 |
| `flows` | 教程、邮件、装备分解/升级专用回调、乐享及 EX 业务回调 | 同上，可加 `ex`；load 明确交给对应恢复 suite |
| `ex` | 完整 load 解析、待选 EX、重登恢复；教程与正常恢复分别断言 | 默认只生成 `ex` 组；EX 修复一般用 `flows,ex --groups ex` |
| `gacha-entry` | 乐享页面类型 5、券 999012、原生日期开关和真实运营 helper 入口条件 | 不需要服务端回包；8 个边界案例 |
| `crazy-flow` | 乐享候选事件、保存槽位、选定清理；抽取/保存/选择后的三次跨进程 load 与实际 Home 恢复路由 | `--suite common,flows,crazy-flow --groups crazy` |
| `mail-ex` | 单封领取前后差分、同一请求快照重试、批量逐封补偿分组和角色获得提示数据 | `--suite common,flows,mail-ex --groups mail`；另有真实差分算法边界案例 |
| `mvp` | 两种真实评分、MVP 选择与 `is_mvp` 载荷；客户端先执行，再用其载荷驱动当前源码双端 finish、双结算顺序与同 play 重试 | 单独运行 `--suite mvp`，默认 `--groups mvp`；`all` 保持原七套/五组，不自动包含 MVP |
| `common` 的可选 `battle` 组 | 原生拾取累计和 finish `add_mana` 序列化先执行；当前源码普通单/多人、Raid 冻结经验、五重旧结果/新局回包，再执行真实公共更新和 boost 可用判断 | 单独 `--suite common --groups battle`；`all` 仍保持原七套/五组，不自动包含 battle |
| `common` 的可选 `purchases` 组 | 当前源码真实购买、回体、注入经验、箱式扭蛋、学习/觉醒首次成功及重试回包；原生公共消费者核对货币、体力、经验池、物品与角色状态 | 单独 `--suite common --groups purchases`；不加入 `all`，不接受旧 fixtures 重放；玛纳节点场景流程和专用结果回调未覆盖 |

历史执行环境为 Python 3.13。工具依赖所选源码树已有 Node 依赖和 ABC 导入器。将 `config.example.json` 复制到仓外私人目录并填写实际 SDK、Java、Node 和后台入口路径，通过 `--config <配置文件>` 传入；默认同目录 `config.local.json` 不随源码分发。缺项直接报错，不自动下载或切换环境。

```powershell
# 将三个路径替换为本任务已确认的实际输入与新输出目录。
& '<local-tool-path>' -B <repo>/tools/client-air-test/run.py `
  --repo '<实际源码或隔离工作树>' --swf '<本次目标SWF>' `
  --suite flows,ex --groups ex --out '<仓外新任务目录>/client-air-01'
```

可加 `--swf-sha256 <已确认SHA256>` 检查输入身份。只有确需整套回归才使用 `--suite all --groups all`。

`purchases` 使用 `fixtures/purchases.cjs` 从本轮指定源码生成六个 case、十二个 success/retry 步骤；空组、缺案例、缺步骤、错误路由和缺经济字段期望都会失败。源码相关文件起止哈希与本轮冻结 SWF 身份写入 manifest，不用历史回包代替当前源码运行。公共消费者通过后也只代表公共更新范围：`user_character_mana_node_list` 由原客户端的 `CharacterLearnManaNodeProcessingFlow.run` / `CharacterAwakeManaNodeProcessingFlow.run` 场景流程处理，本组没有运行这两条流程，结果及 receipt 必须保留 `uncovered_fields`。服务端对节点持久状态的断言不能当作 AIR 节点消费通过；商店、回体、经验、箱式扭蛋和玛纳的专用 remote callback、结果 UI、网络及设备仍未覆盖。

该组的 `userInfo` 按显式列出的六个经济字段分别比较，允许原生消费者同步保留真实回包中的恢复时间等额外字段；物品和角色仍完整比较。每个 case 只初始化一次客户端 before，首次成功后在同一状态上消费重试回包，不在重试前重置余额或节点。其他组的现有比较规则不变。

`run.py` 已从最外层自动调用既有 `client-background/run_background.py`，并在后台桌面完成构建及 ADL；正常使用不需重复包裹。内部参数 `--_run` 仅供包装器调用，不是另一条用户入口。调试其他会启动 AIR 的脚本仍须从最外层包裹；失败后不得裸跑 ADL。

显式 `--fixtures <schema2 fixtures.json>` 是客户端重放模式，结果标记 `explicit-replay`，不能证明当前服务端修复。普通验收省略它，工具使用所选源码、隔离数据库和真实响应编码器生成新回包；不监听端口，不使用真实账号、8001 服务或真实数据库。

MVP 使用 `fixtures/mvp.cjs` 的专用适配器：先在 `client-payload/` 执行选定 SWF 的真实评分及统计方法，之后以该输出中的统计和贡献值调用所选源码的真实 start/finish 与回包编码器。最终 AIR 再次执行相同客户端方法并对账回包、任务事实和三个称号进度。治疗者伤害 0/治疗 10000 必须生成 `is_mvp=false`，任务保持 99；伤害者伤害 1000/治疗 0 必须生成 `true`，任务变为 100。两种结算顺序、双方真实 start、双方同 play 重试均为必需合同。另测平分、弱点、连锁、单人不含 MVP 字段与 RTT；单人字段缺失只证明客户端该分支，不冒充多人旧协议验收。MVP 权重从本轮 SWF 的 `BattleConstants` 脚本初始化直接核对，完整常量初始化及战斗构造器不执行。战斗输入、类型壳与枚举壳为显式替身；回包使用 JSON 载入，未执行生产 finish remote 回调或页面渲染。`--fixtures` 可明确重放；空 schema2 仅运行七个客户端案例，不能证明当前服务端。

## 普通战斗经济与回包

显式 `--fixtures` 重放选择 `--groups battle` 时，必须包含全部三个业务案例、十个必需步骤及经济断言。空输入、只有其他组或缺案例会在 CLI 校验时失败，不启动 AIR、不退回仅 synthetic 通过；worker 读取后再次校验。显式重放仍只证明客户端回归，不声称执行当前服务端。

`--suite common --groups battle` 复用 common 的构建、ABC 导入、类型壳及公共回包消费者，不是另一套运行平台。`client-battle-payload/` 先执行选定 SWF 的九个新增方法：拾取管理器构造、addChild、count、sumUp，finish createRequest，以及普通/boss boost getter 和两个 canUse 方法。原生 count 只计 kind=0；固定样本从首场 1200、第二场累计 71200，到续存同一拾取数组后累计 19071200。三种 boost 余额 1、0、-1 分别核对 getter 和可用判断。

count 的结果由测试手工赋给 BattleClearParameter.obtainedMana，再执行真实 createRequest；不宣称执行 Battle.getClearParameter、BattleClearParameter 构造或完整恢复流程。QuestLogic/BattleQuestPeek 的接口壳保持当前 SWF namespace，拾取来源、continuation、评分、关卡 ID 转换、日志、rank 主表及未走的装备/队友分支是显式替身。记录在 proof 的导入方法数只证明绑定，实际执行看两个必需 native 案例及逐项断言。

`fixtures/battle.cjs` 用先行 AIR 产出的 add_mana 调用所选源码的真实 Fastify 路由及响应编码器，固定三个 case、十个 finish/重试步骤：普通两局单人和一局多人；Raid 三队冻结后修改 SET、乱序副统计的主队经验归属；五重 load 分离旧结果、新 solo 开局、旧 finish 和重试保留新 active。最终 common 原生 earlySuccessHandler/applyCommonResponse 核对实际钱包、角色 EXP、0 点 boost 及 canUse。每份 finish 的 field_mana/reward_mana 独立核对非负 int32，不把普通两字段合计限制为 int32。

Raid 冻结与五重新旧 active 关系由 source 断言核对，AIR 只执行公共回包更新，不执行专用 finish parser、结果 UI 或完整 load 初始化。Mode15 的字段合成边界由相关 source 测试及静态 native parser 契约单独验证，不借 common 钱包通过声称已执行专用显示。手机、渲染、真实网络和 iOS 不在该组验收范围。

## 通过与失败

- 每次只冻结一份输入 SWF；真实回包只保存在 `cases[].steps[].response`，所有 suite 共用。清单记录输入、夹具、工具、导入器及相关服务端源码身份。
- 按必需类 QName 唯一定位 ABC，再导入真实方法及闭包。找不到、重复或签名不匹配即失败；保存后重新解析，校验代码、异常、参数 flags/defaults、栈及 activation traits。导入方法数不等于执行覆盖。
- ADL 退出 0 不足以通过：必须产出本轮新结果、明确 passed、无失败断言、案例和步骤完整、命中目标恢复分支。结果目录不能复用；不读取历史结果替本轮通过。每项输出及失败日志留在本轮目录。
- suite 的外部依赖使用明确的类型替身/记录器，边界写在 proof/result 中。gacha-entry 的运营 helper 使用目标 SWF 的完整原始 ABC，不用恒真替身替代入口规则。
- 执行失败或超时就停止，保留原因和对应产物；修正具体问题后换新目录运行。不自动降级、换客户端版本、绕过断言或改业务代码求绿。

完整 load 的归属按实际执行的步骤 ID 核对：`ex` 只负责 EX，`crazy-flow` 负责乐享。公共更新或其他 suite 通过不能抵消未执行的恢复步骤；最终查看 `uncovered_load_steps`。

乐享 fresh draw 直接传递候选事件，重登 load 才重建 lastCrazy；不虚构原方法没有的字段写入。邮件单封重试复用原请求领取前快照；批量明细按每封邮件的实际新增补偿记录，普通道具邮件不混入。当前重复角色补偿规范与已核客户端主表一致：三星、四星每份 1 个，五星每份 3 个。夹具从附件数量或重复份数独立计算期望，再核实际到账；不从 grant 返回值反推期望。`mail-ex` 的稀疏主表保留实际客户端来源，原生道具 ID 和补偿数量均是必须通过的断言，不能修改主表或回包来求绿；实际差分 1 小于主表数量 3 的算法边界仍保留。

目前仍不覆盖：装备批量升级 `bulk_upgrade` 专用回调、完整主表到 UI 的入口流程、手机/GPU/ANE/真实网络/iOS AOT。场景切换、图像资源和平台存储外部边界使用记录器，不等于真实页面渲染或手机文件落盘。乐享入口没有额外虚构的个人资格开关；本 suite 验证实际代码的持券、日期、visible/enter 条件。

## 加案例与空间管理

通用构建层在 `lib/abc_tools.py`，业务 suite 在 `suites/`，类型壳及断言在 `templates/`；真实服务端回包生成器在 `fixtures/generate.cjs`。新增案例写清必需分支、最终状态与失败条件，并把必需案例/步骤接入 `lib/run_contract.py` 的合同。缺少目标分支时不能用另一分支的成功替代。

共享 SDK 复用一次，不复制进每轮。成功后保留本轮 manifest/result、输入 SWF、唯一回包、最终 Harness.swf、proof、合同、编译/执行记录及必要日志；生成的 AS 源目录、template.swf、编译 API SWC 和隔离临时数据库经核实无复现/回退职责后可按工作区清理规则删除。失败轮先保留最小诊断证据，问题确认解决后再退役可重建产物；不自动清理别的任务或历史输入。

空间与运行耗时以每轮实际记录为准；完整回包通常比测试代码本身大。不要每次复制 SDK、APK、资源包或所有历史回包。

运行证据：首轮入口落地（历史本地记录）、第二批业务验收与邮件修复（历史本地记录）、五星补偿数量对齐（历史本地记录）。这些记录保留各轮当时的输入和已验证范围，不固定为后续新任务的输入；旧服务端五星每份 1 个与客户端主表 3 个的差异是历史状态，当前规则及修改后结果以最近适用证据为准，不代表已发布或部署。
