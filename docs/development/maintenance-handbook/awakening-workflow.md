# 角色觉醒制作与兼容流程

本页覆盖角色觉醒主数据、服务端状态、任务、二板兼容和验证入口。[案例与故障经验](awakening-cases.md)保存历史设计及其证据边界；案例中的角色、版本、槽位和日期不能直接作为新角色的默认配置。本文补充技术资料，不改变游戏数据或验收登记，也不证明当前设备或云服已经验证。

## 基线与实现入口

先确定角色 ID/资源代码、官方设计、觉醒前后目标设计、当前启用资源链及需要修改的范围。工作区规则与[分支流程](../branch-workflow.md)决定实际源码、运行和发布入口。客户端身份从 `client-patch/android-accepted.json`、`client-patch/ios-accepted.json` 查阅，不从历史案例选择安装包。

| 职责 | 当前源码或资料入口 |
| --- | --- |
| 技能节点觉醒后的进化等级 | [character-awake-evolution.ts](../../../src/lib/character-awake-evolution.ts) |
| 扩展板映射、整板更新与增量响应延迟发布 | [character-awake-extension.ts](../../../src/lib/character-awake-extension.ts)、[角色配置](../../../assets/character_awake_extension.json) |
| 学习、觉醒、重复请求和角色响应 | [mana.ts](../../../src/routes/api/character/mana.ts) |
| 完整加载及旧局部觉醒状态修复 | [player-data.ts](../../../src/data/utils/player-data.ts) |
| 官方与扩展任务合并 | [awake-master-assets.ts](../../../src/lib/mission/awake-master-assets.ts)、[扩展定义](../../../assets/mission_char_awake_cnmod.json)、[扩展奖励](../../../assets/mission_char_awake_reward_cnmod.json) |
| 战斗任务结算与解锁 | [awake-settlement.ts](../../../src/lib/mission/awake-settlement.ts)、[awake-unlock.ts](../../../src/lib/mission/awake-unlock.ts) |
| 原生觉醒界面、消息与任务机制 | [客户端与服务端对齐说明](../../systems/character-awake-alignment.md) |

当前任务扩展文件确实参与加载。早期原型撤回时曾移除同名入口，那是历史状态，不适用于现在的源码。旧运行镜像也不作为恢复入口。

## 客户端数据闭环

常见受影响逻辑表包括：

- `master/ability/ability.orderedmap`、`master/ability/leader_ability.orderedmap`；
- `master/skill/action_skill.orderedmap` 及主动技引用的 `.action.dsl.amf3.deflate`；
- `master/mission/character_awake_event.orderedmap`、`master/character/character_awake_status.orderedmap`；
- `master/mission/character_awake_mission.orderedmap`、`master/mission/character_awake_mission_reward.orderedmap`；
- `master/mana_board/mana_node_awake.orderedmap`。

逐角色比较官方行、当前有效行、目标行和真实玛纳板。历史格式中，能力门控曾位于零基列 3/4，队长技位于 1/2；这些列号只作定位线索，必须与当前表头或解析器证据相符。结构和输入未变时复用已有解析结论；出现新布局、缺失证据或冲突时重新推导，不复制首个案例的槽位。

主动技通常保留官方进化 1/2，并在设计确需时增加进化 3。历史九角色迁移中，第三形态需要持久化 `evolution_level = 2`；只补能力表不足以生效。新角色仍应按实际主数据确定等级条件。

常用立绘资源只有基础与进化两档。没有独立觉醒立绘的设计可沿用进化图，不伪造第三档资源。

标准觉醒页固定按一板显示能力 1、2、3 和技能觉醒，不会自动列出实际变化的队长技或二板能力。因此，能力未改而页面仍出现对应标签、能力 6 已生效却没有独立展示项，都可能是界面限制。最终面板、过程页标签和战斗效果分别核对；显示文案不能反过来决定战斗设计。

## 服务端持久化与重复请求

检查 `/character/awake_mana_node` 与 `/character/learn_mana_node` 的实际调用链，至少保持以下约束：

- 觉醒节点 `awake_level` 与必要的进化等级在同一业务操作中持久化；响应与最终状态一致。
- 已达到目标的请求安全重放，不重复扣费或插入节点，同时允许修复缺失的派生状态。
- 响应保留持久化的 `mana_board_index`、完整 `bond_token_list` 和权威已学习节点，不能用公共构造器的默认值覆盖真实进度。
- 只对配置角色及扩展板施加特殊规则；不能把一个角色的槽位映射扩散到所有角色。
- 完整加载可幂等补齐旧版局部觉醒状态，但不降低已取得等级、板位、羁绊或显式角色身份例外。

### 二板与能力 4～6 的兼容门禁

这类设计属于客户端/服务端状态模型变更，不能当作只改数值的平衡补丁。以下条件必须一起成立：

1. **整板状态一致。** 客户端用整板 `mana_board_awake` 选择节点展示模式，战斗能力又从各节点 `awake_level` 聚合。扩展板未点满时保持普通状态；角色已觉醒且该板点满后，整板节点在事务内统一提升。不能只提升实际修改的能力槽，否则会出现重新学习或强化等级反向显示。
2. **查询表完整。** 终端 `mana_node_awake` 必须包含目标稀有度、能力槽和底座状态需要的查询键。能力 5、6 不因官方表缺行而豁免。缺键可能在 `GeneralManaNodeLogic/get_awakeValues()` 触发 `C8601`；服务端 JSON 与 Android/iOS 终端表应同源。
3. **按真实响应解析能力发布标志。** 已定位的 1.8.1 增量公共响应会应用 `character_list.mana_board_awake`，但忽略额外返回的 `user_character_mana_node_list`。当前兼容方案立即保存数据库整板节点，同时由 `deferLinkedManaBoardAwakeLevels` 从学习、觉醒及幂等增量响应中隐藏扩展板标志，直到下一次完整 `/load` 同时加载角色与节点状态。
4. **不暴露中间矛盾状态。** “板已觉醒、客户端节点仍为普通等级”会触发后续错误。1.8.1 的 `ManaBoardAwakeBulkResolver` 只为四个槽建立容器，二板能力 5/6 在这种状态下可能触发 `F1009`。补齐查询键只能处理 `C8601`，不能替代响应时序修正。
5. **完整加载收敛。** `/load` 必须返回相互一致的整板等级和标志，并修复旧版只提升部分槽位的存档。修复保持节点数量、等级、羁绊和角色身份；重复执行不再改变状态。
6. **覆盖重登前后。** 使用延迟发布方案时，交付说明应明确完整退出并重新登录后扩展板最终显示生效。设备验证要覆盖重登前无错误重学/报错、重登后无倒退，不能只检查最终角色面板。

更换客户端后重新检查公共响应和批量解析器，不把 1.8.1 的内部结构当作永久协议。同一会话立即显示扩展板，需要明确修改并验证对应客户端解析路径，不能仅取消服务端延迟标志。

## 任务、时间与资源版本

客户端任务表不代表服务端会正确计算进度。核对任务定义、奖励、关卡/队伍条件、战斗结算、解锁和重复结算；`awake-master-assets.ts` 合并扩展时拒绝与基础任务重复的 ID。历史案例的“编入目标角色通关任意关卡 1/3/5 次”只是一种已实现的条件，不能用客户端文字证明新的高难任务条件也受支持。

日期按实际运行语义检查：系统时间、历史账号时间和活动窗口可能不同。存在时间偏移的环境应核对 `getServerDate()`、`getServerTimeForPlayer()` 或对应日志，再对照客户端活动与服务端任务窗口。实时运营方案以[时间与内容](topics/content-time.md)为准，不因复用旧案例重新引入已退役的偏移机制。

资源发布遵循以下规则：

- 有效版本由只读 CDN 基线和启用链解析，不只看 manifest 中遗留的顶层版本字段。
- 新增量从当前实际终点接出；已被客户端下载的缺陷包用更高版本修正，不原地替换旧 ZIP。
- 小范围修改使用稀疏增量，回读成员、CRC、目标行与无关行保留情况，并核对受影响平台终点。
- 本地链可能领先云服；真正交付前核对云端基线，不照搬历史本机版本号。
- 撤回本地试验要同时处理启用清单和试验包，并重新解析终点。服务端降低终点不会自动降级已缓存高版本的客户端；资源恢复另按客户端流程处理。

## 验证与回退

先恢复仓库锁定的依赖及测试需要的编译产物，再按改动选择检查。下表是后续实现的入口，不是本次资料补充的测试通过记录。

| 变化 | 验证内容与入口 |
| --- | --- |
| 技能进化状态 | [character-awake-evolution.test.js](../../../tests/character-awake-evolution.test.js)：首次持久化、旧状态补写、幂等重放 |
| 二板/学习/角色响应 | [character-awake-extension.test.js](../../../tests/character-awake-extension.test.js)：未满板、满板、板位/羁绊、完整加载修复、延迟标志、零重复扣费 |
| 任务扩展与结算 | [character-awake-custom-content.test.js](../../../tests/character-awake-custom-content.test.js)、[character-awake-custom-settlement.test.js](../../../tests/character-awake-custom-settlement.test.js)：定义/奖励、目标角色条件、进度与重复结算 |
| 查询范围与并发学习 | [character-awake-query-scope.test.js](../../../tests/character-awake-query-scope.test.js)、[mana-learn-concurrency.test.cjs](../../../tests/mana-learn-concurrency.test.cjs) |
| 主数据、DSL、查询键 | 回放真实终端表，核对未觉醒/觉醒选择、进化形态、能力 5/6 键、序列化和无关行不变 |
| 客户端实际表现 | 资源更新、入口、任务、四项展示、重登前后、战斗技能与伤害；API/离线通过不替代设备结果 |

对新的兼容故障优先构造最小、隔离的合成存档与请求，不用真实玩家数据库做破坏性验证。代码变化按影响编译；纯资料和数据变化不因此重建安装包、开服或部署。

已授权的运行变更前，保存受影响文件、角色状态及明确的恢复入口。数据库回退使用事务并在合成 SQLite 数据上验证；备份范围与实际影响相称。资源清单与 ZIP 应按既有发布流程一致切换，不能留下半更新状态。恢复或交付分别报告源代码、资源、存档、离线结果、设备验收与云服状态。

## 复用案例的条件

新增角色按自身官方结构推导槽位、进化等级、立绘和任务；历史版本、角色 ID、日期及资源摘要只保留在对应案例。已有结构/输入未变时复用有效证据；新布局、失败模式或结论冲突时更新匹配案例并收窄适用范围。可靠的多角色或官方参照才能支撑通用结论。
