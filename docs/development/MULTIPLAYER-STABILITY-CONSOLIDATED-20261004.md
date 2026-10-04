# 多人稳定性、五重决战、幻想连战与 AI 续战改进总记录

日期：2026-10-04

基线分支：`staging`

基线提交：

```text
c08dd5f9
```

本文汇总最近几轮围绕多人共斗、五重决战、幻想连战和 AI 自动续战完成的全部
排查、实现与验证。它作为本批改动的总入口；更早的日志细节与单项历史仍保留在：

- `docs/development/FIVE-BOSS-DISCONNECT-H400-FIX-20261004.md`
- `docs/development/FIVE-BOSS-STAGING-LOG-FOLLOWUP-20261004.md`
- `docs/development/MULTIPLAYER-DISCONNECT-INVESTIGATION-20261003.md`
- `docs/development/RUNTIME-LOG2-FOLLOWUP-20261003.md`

交付分支：`fix/multiplayer-stability-h400-recovery`，目标分支为 `staging`。本批改动
不会直接推送 `staging`，也未合并 `main`。

主要实现提交：`890c8874`

交付 PR：`https://github.com/Ku1o/startpoint-cn-kulo/pull/21`（开放、待评审）

## 一、涉及问题

本批连续处理了以下问题：

1. 多人房间满员时，多个 HTTP 选房请求可能同时通过，直到 TCP 入房才发生冲突。
2. 高难多人副本的等级与前置关卡要求只在部分入口生效，铃铛、好友房或房间号可能
   出现规则不一致。
3. 五重决战助力需要持票，但好友房、房间号和 TCP 最终握手也必须执行同一检查。
4. 五重决战新队友需要增加玩家 Rank 130 门槛。
5. 五重 battle TCP 因 lobby/battle 出口 IP 不一致误拒合法移动网络连接。
6. 五重玩家进入战斗后可能因 25 秒静默被服务器主动销毁 battle socket。
7. 五重 Boss 转换阶段可能一直等待，战斗计时继续增加。
8. 五重第一轮结束后所有玩家已回房，但服务器仍停留在 `RETURNING`，无法开始下一轮，
   60 秒后房间自动解散。
9. 五重合法 abort 请求可能缺少 category/quest，导致 active run 残留。
10. 五重单人有足够体力但无法连续战斗。
11. 幻想连战第 5、10、15 层共斗掉线后，房主整轮进度被清空回第 1 层。
12. 地狱关卡匹配 AI 后，自动续战开战时出现客户端错误 `U_1d93f4`。

## 二、生产日志结论

分析来源：项目外运行日志目录“`五重修复后日志`”。

包含：

```text
cn-server-20261003-233657.stdout.log
cn-server-20261003-233657.stderr.log
cn-server-20261004-145227.stdout.log
cn-server-20261004-145227.stderr.log
```

### 2.1 服务重启边界

新进程启动时间约为：

```text
2026-10-04T06:52:29Z
```

短日志中 30 条 `FIVE-BOSS-REJECT` 分布为：

| 操作与原因 | 数量 |
|---|---:|
| `finish:battle_proof_missing` | 11 |
| `start:active_quest_mismatch` | 6 |
| `abort:request_identity_mismatch` | 4 |
| `start:insufficient_ticket` | 9 |

11 个 `battle_proof_missing` 的 `started_at` 均早于新进程启动时间。它们是重启前创建、
没有 `battle_entered_at` 的旧在途局，不是新版新建局再次产生的凭证丢失。

因此：

- 上一轮“全员 SceneReady 屏障释放后持久化认证入场凭证”的方向有效；
- 不能把重启前旧局继续失败统计成新版回归；
- 新局的主要问题转向握手误拒、连接租约、回房确认和请求兼容。

### 2.2 合法 battle 握手误拒

日志中的典型链路：

```text
frozen
-> http_start
-> handshake
-> handshake_denied:frozen_identity_mismatch
-> socket_end/socket_close
-> abort:request_identity_mismatch
```

冻结身份原来同时比较：

- viewer；
- player ID；
- connection ID；
- lobby TCP 与 battle TCP 的 remote address。

移动网络、双栈和运营商 NAT 可能让同一客户端的两条 TCP 连接使用不同出口 IP。
remote address 不是稳定身份，不能作为已有 session、viewer、player 和 connection ID
之外的强身份条件。

### 2.3 五重连接被 25 秒租约销毁

结构化 transport 事件存在以下顺序：

```text
accepted
-> scene_ready
-> 战斗期间暂无合作通道数据
-> heartbeat_timeout，约 25000 ms
-> socket_close/removed
```

五重 Boss 战期间并不保证每 25 秒发送一条合作通道数据。服务器把“战斗中静默”
等价成断线后，会主动销毁原本仍应保留到 `LevelNext` 的连接。

直接后果：

- 队友收到错误的通讯断开体验；
- 后续 `LevelNext` 无法送达；
- 第二场景 `SceneReady` 屏障无法完成；
- 客户端转换页一直等待，本地战斗计时继续增长。

### 2.4 回房状态竞态

成功结算后房间进入：

```text
BATTLE -> SETTLING -> RETURNING
```

原实现只在房主重新发送 lobby `Enter` 时完成：

```text
RETURNING -> LOBBY
```

客户端可能继续复用首轮前已经完成 `Enter` 的 lobby socket，不会再次发送服务器期待的
新 `Enter`。服务器因此误判房主未返回，下一轮 `StartBattle` 被状态机挡住，随后触发：

```text
settlement_host_return_timeout
```

### 2.5 Abort 请求字段缺失

部分 CN `QuestAbortRealRemote` 请求不带 category、quest 或 room number。原代码将空值
直接传给五重 runtime，最终得到：

```text
request_identity_mismatch
```

合法终止没有成功清理 active quest 和 run，后续开局可能继续被旧状态阻挡。

### 2.6 `U_1d93f4` 的真实含义

日志中的堆栈为：

```text
Failed to allocate packing rectangle: size exceeded
MaxRectsPacker.allocateRectangle
-> MaxRectsPacker.pack
-> AtlasBuilder.buildTextureAtlas
-> BattleStartProductionViewService.pack
```

这不是 HTTP 错误码，而是 AIR 客户端开战时动态合并三支队伍战斗资源，无法装入固定
图集容量。

当前 `1.4.130` 资源链已经包含历史上的：

- 杰拉德战斗图集裁剪；
- 赛瑞斯战斗图集裁剪；
- 赛瑞斯大特效迁移到 layer 1；
- 相关 atlas/parts/action 引用修复。

但生产日志仍有 `U_1d93f4`，其中至少一例紧跟两个 `MULTI-AI fallback` 事件。服务端
原来在每次自动续战回房后重新随机 AI 队伍，导致首局已经成功加载的房间，第二局可能
突然换入另一套高资源角色组合。

日志的 `[CRASH]` 行被服务端限制为约 2000 字符，部分样本的 viewer、quest 和完整
上下文被截断，所以目前不能从历史日志精确列出每个崩溃 AI 的角色 ID。可以确认的是
错误发生于客户端合图阶段，且“续战重新随机 AI 编队”是服务端可消除的变量。

## 三、统一多人准入

### 3.1 统一入口

所有新队友统一通过 `canJoinMultiGuestQuestSync()` 判断，包括：

- 铃铛列表 `attention/check`；
- 铃铛接受后的 `select_room(accepted_type=2)`；
- 好友/关注房列表；
- 房间号 `search_room`；
- 普通直接 `select_room`；
- HTTP 选房后的 TCP lobby handshake。

房主和已经属于该房间的续战/断线回连成员不作为“新队友”重新检查，避免玩家在战斗
完成后的返回流程中被新增门槛误踢。

### 3.2 十二个高难副本

客户端 master 中可审计的 12 个高难多人副本使用以下规则：

| 多人副本 | 最低 Rank | 前置分类 | 前置关卡 |
|---|---:|---|---:|
| `26:1001` | 120 | 7 或 8 | `200014004` |
| `26:2001` | 120 | 7 或 8 | `200017004` |
| `26:3001` | 120 | 7 或 8 | `200018004` |
| `26:1001001` | 120 | 2 | `1061004` |
| `26:1002001` | 120 | 2 | `1062004` |
| `26:1003001` | 120 | 2 | `1063004` |
| `26:1004001` | 120 | 2 | `1064004` |
| `26:1005001` | 120 | 2 | `1065004` |
| `26:1006001` | 120 | 2 | `1066004` |
| `26:100001001` | 120 | 7 或 8 | `200064004` |
| `26:100000001` | 120 | 7 或 8 | `200053004` |
| `26:100002001` | 120 | 7 或 8 | `200077004` |

规则保存在：

```text
assets/multi_guest_entry_requirements.json
```

未知或自定义副本没有可审计规则时默认放行，避免按推荐等级或 ID 形状猜测并误封。

### 3.3 五重决战新队友

五重多人新队友必须同时满足：

```text
玩家 Rank >= 130
持有深界连战凭证 10000143 >= 1
```

检查顺序：

1. 先计算正式玩家 Rank；
2. Rank 129 及以下立即拒绝，不读取票券库存；
3. Rank 130 及以上继续检查票券；
4. 只有两个条件都满足才允许作为新队友进入。

准入检查只读，不消耗队友门票。

当前费用规则：

| 模式 | 体力 | 门票 |
|---|---:|---:|
| 五重单人 | 35 | 1 |
| 五重多人房主 | 35 | 1 |
| 五重多人队友 | 0 | 只需持有 1 张，不扣除 |

Rank 130 和持票检查同时覆盖：

- 铃铛；
- 好友/关注房；
- 房间号；
- 直接选房；
- TCP 最终握手。

### 3.4 HTTP 到 TCP 的席位预约

多人选房分为 HTTP 和 TCP 两步。没有中间预约时，多名玩家可能同时看到剩余一个席位，
全部通过 HTTP，直到 TCP 阶段才冲突。

新增 `RoomAdmissionRegistry`：

- HTTP `select_room` 为 viewer 和当前 generation 预约席位；
- 区分 direct 和 rescue 来源；
- TCP handshake 使用同一 connection ID claim；
- `Enter` 完成后 commit；
- 握手失败、socket 关闭或 generation 变化时 release；
- 预约有界过期，不永久占用房间；
- 已占用 viewer 与预约 viewer 去重计数；
- 同一 viewer 重试只刷新原预约；
- 旧 generation 和过期预约不能进入新一轮房间。

这同时解决：

- 房间满员竞态；
- 铃铛多人同时抢最后席位；
- 重试偷走其他玩家 claim；
- 旧 TCP 连接释放新 TCP 连接预约；
- 选房到握手之间资格变化的最终防绕过。

## 四、五重决战连接与状态机修复

### 4.1 冻结身份不再绑定 IP

保留：

- viewer；
- player ID；
- connection ID；
- 当前连接未 superseded。

移除：

- lobby 与 battle socket 的 remote address 必须相等。

错误 player、伪造 connection ID、过期或被替换连接仍拒绝。

### 4.2 五重 active 场景不使用普通 25 秒 heartbeat

已经通过五重首轮 `BattleStart` 屏障的连接：

- 不再因 25 秒无包被销毁；
- 同场景重连后补发 `SceneReady`，也解除临时 lease；
- 在第二场景已经 `SceneReady`、等待慢队友时，不套用 25 秒普通 ready lease。

仍然保留：

- 初次加载固定 deadline；
- `LevelNext` 后下一场景固定 loading deadline；
- 缺席席位重连宽限；
- 到期转 AI 和合法 `Leave`；
- abandoned-battle watchdog；
- 普通共斗 heartbeat。

因此不是“无限保留连接”，而是把计时器所有权交给五重真实加载屏障和房间 watchdog。

### 4.3 五重连接关闭不误报普通 Leave

已经通过首轮 `BattleStart` 的五重连接关闭时：

- 不立即按普通共斗向其他玩家广播 `Leave`；
- 避免客户端正常转场或关闭 battle socket 被显示成“与队友通讯断开”；
- 第二场景真正缺席仍由 `LevelNext` 屏障宽限处理。

### 4.4 认证入场凭证

服务端在以下条件全部满足后记录 `battle_entered_at`：

- battle socket 通过认证和冻结身份校验；
- 房间仍属于对应五重 run；
- 本轮真人全部 `SceneReady`，或缺席席位经过宽限后缩编为 AI；
- SceneReady 屏障真正释放。

新局 finish 可使用 `battle_entered_at` 作为认证进入战斗的持久化证据。旧版
`level_next_at + finalized_at` 组合继续兼容，不把只用于诊断的包数或时长当作发奖依据。

### 4.5 回房与下一轮

成功结算后：

```text
BATTLE -> SETTLING -> RETURNING -> LOBBY
```

五重房间进入 `RETURNING` 时：

- 若已认证房主 lobby socket 仍在线并完成过 `Enter`，立即完成返回；
- 房主后续 `Ready` 可幂等完成返回；
- 收到下一轮 `StartBattle` 时，若房主在线，先完成返回再开局；
- 完成返回时同步存活 lobby client 的 generation；
- 只有真正没有房主返回才保留 60 秒解散保护。

普通共斗保持既有返回语义。

### 4.6 Abort 缺字段恢复

五重 abort 先按：

```text
playerId + play_id
```

查询不可变 ledger。

- body 缺 category/quest 时恢复 canonical 五重值；
- room number 继续从精确 run 恢复；
- body 明确携带错误 category/quest 时仍拒绝；
- 不允许请求体把普通战斗伪装成五重。

### 4.7 诊断增强

`FIVE-BOSS-REJECT` 的 active quest 摘要新增：

- category；
- quest。

以后可直接区分：

- 五重单人或多人孤儿状态；
- 玩家确实仍在其他普通副本；
- play ID 错配。

不记录 token、完整队伍、session 或其他敏感内容。

## 五、五重单人连续战斗

### 5.1 核对结论

单人五重的既定收费是每轮 35 体力 + 1 张深界连战凭证；曾观察到“仍有体力但不能
继续单人战斗”的现象，核对后确认是被门票不足拦住，而不是 stale active quest 造成。
客户端凭证说明只描述多人房间由房主支付，不改变单人收费。

### 5.2 现行规则

五重单人：

- 每轮扣 35 体力和 1 张深界连战凭证；
- active quest 继续把门票写入 `entryItemId`；
- start、体力与门票扣除、solo ledger 和 active quest 仍在同一事务中；
- 同 play ID 重试不重复扣体力和门票；
- 新 play ID 开始下一轮时再次扣 35 体力和 1 张门票；
- 门票不足时返回原生 `200/4050`，不扣体力、不建立 run 或 active quest。

五重多人：

- 房主每轮扣 35 体力和 1 张票；
- 队友不扣体力、不扣票；
- 队友仍必须满足 Rank 130 和持票准入。

没有采用“发现 active quest 就批量删除”的方案。普通单人副本或仍有效的五重局不会
被五重入口擅自清理。

## 六、幻想 5/10/15 层掉线保层

### 6.1 进度来源

幻想当前层数来自：

```text
players_rush_events_played_parties
```

已完成阶段标记数量决定下一阶段。第 5、10、15 层是多人边界关卡。

### 6.2 原重置路径

共斗中断后可能进入三条路径：

1. 客户端发送失败 `/finish`；
2. 客户端发送 `/abort`；
3. 房间消失，下一次 `/cn/load` 清理 stale multiplayer active quest。

原实现会在这些路径调用 `resetMode15RunSync()`，删除本轮全部阶段标记，因此房主从
第 5、10 或 15 层直接回到第 1 层。

### 6.3 新行为

对幻想第 5、10、15 层：

- 只有成功结算才写当前层成功标记；
- 只有成功结算才发当前层边界奖励；
- 失败 finish 不推进；
- abort 不推进；
- 房间异常消失后的 `/cn/load` 只清理无法恢复的 active battle；
- 前面 1-4、1-9 或 1-14 层标记保持不变；
- 下一次仍只允许挑战原来的 5、10 或 15 层。

不能从旧客户端的失败请求可靠区分“主动放弃”和“网络掉线”，所以多人边界采用
对进度更保守的一致语义：未成功就不发成功奖励，但也不清空整轮。

保持不变：

- 单人阶段失败仍重置整轮；
- 玩家主动调用幻想整轮重置仍回到第 1 层；
- 第 15 层成功完成仍发完整奖励并开启新一轮；
- 救援玩家不推进自己的幻想 run。

## 七、地狱关卡 AI 自动续战 `U_1d93f4`

### 7.1 已证实部分

已证实：

- `U_1d93f4` 是客户端动态战斗图集打包失败；
- 错误文本为 `Failed to allocate packing rectangle: size exceeded`；
- 发生点在 `BattleStartProductionViewService.pack`；
- 当前 `.130` 已包含历史角色图集裁剪修复；
- 生产日志中仍有样本，且至少一例与 AI fallback 时间相邻；
- 服务端原实现会在每次续战重建 COM 时重新随机 AI 队伍。

未能从旧日志完整证明：

- 每个崩溃房间的完整三队角色列表；
- 哪个具体角色组合超过预算；
- 所有样本是否都只发生在第二局。

原因是 `[CRASH]` 结构化内容被日志长度上限截断，部分 viewer、quest 和队伍上下文没有
保留下来。

### 7.2 服务端风险收敛

新增房间级：

```text
npc_party_by_com_id
```

规则：

- COM1、COM2 第一次生成时保存对应 party；
- 同一房间自动续战复用同一 COM party；
- 已有完整快照时不读取随机池、不执行随机选择；
- 两真人一 AI 时保存剩余 COM 席位；
- 真人离开后新增另一个 AI，只为从未存在的席位选择新 party；
- 原席位以后恢复时继续复用旧 party；
- 新房间拥有独立快照，仍正常随机；
- 房间解散后内存自动释放；
- 不写玩家存档和数据库。

这一调整不改变：

- AI 数量；
- AI Ready 时序；
- AI 战斗协议；
- 玩家历史通关队伍池；
- 新房间的随机性；
- 真人加入替换 AI 的行为。

### 7.3 验收边界

该修复直接覆盖：

```text
首局能进入
-> 回房自动续战
-> 服务端重新随机出另一支高资源 AI
-> 第二局合图超限
```

它不修改 AIR 图集容量。如果新房间首局就抽到一个本身超预算的组合，仍可能复现。
上线后若仍有首局 `U_1d93f4`，下一阶段应：

1. 提升 `[CRASH]` 上下文保留，记录 room、quest 和脱敏角色 ID；
2. 建立角色战斗图集预算清单；
3. 在 AI 候选选择时按三队总资源预算过滤；
4. 或对明确高占用角色继续做客户端 atlas/layer 优化。

不应仅凭一个错误码随意禁用所有自制角色。

## 八、核心实现文件

| 文件 | 作用 |
|---|---|
| `src/multi/guest-eligibility.ts` | 新队友统一 Rank、前置关卡、Mode15、五重 Rank/票券判断 |
| `assets/multi_guest_entry_requirements.json` | 12 个高难多人副本的审计规则 |
| `src/multi/room/admission.ts` | HTTP 选房到 TCP 握手的有界席位预约 |
| `src/multi/http/lobby.ts` | 好友房、房间号和直接选房准入 |
| `src/routes/api/attention.ts` | 铃铛列表资格过滤 |
| `src/multi/tcp/handshake.ts` | TCP 最终资格复查与防绕过 |
| `src/multi/five-boss/contract.ts` | 五重 Rank 130、票券和玩法常量 |
| `src/multi/five-boss/lobby-runtime.ts` | 五重冻结身份与战斗信号 |
| `src/multi/five-boss/solo-runtime.ts` | 五重单人 35 体力 + 1 张门票（同轮重试不重复扣） |
| `src/multi/http/five-boss-battle.ts` | 五重 start/finish/abort、字段恢复与诊断 |
| `src/multi/state/SessionManager.ts` | battle lease、屏障、回房和房间回收 |
| `src/multi/tcp/lobby.ts` | 回房确认、StartBattle、AI 固定编队和续战 |
| `src/multi/room/manager.ts` | 房间初始化及 AI 快照生命周期 |
| `src/lib/types/multi.ts` | 房间运行时结构 |
| `src/lib/mode15.ts` | 幻想边界失败保层和成功结算 |
| `src/lib/mode15-active-quest-recovery.ts` | 掉线后登录清理是否重置幻想 run |
| `src/multi/http/battle.ts` | 多人失败 finish/abort 路径 |
| `src/routes/cn/load.ts` | stale active battle 登录恢复 |
| `src/routes/api/singleBattleQuest.ts` | 五重单人开局 active quest |

对应 `out/` 编译产物已同步生成。

## 九、测试矩阵

### 9.1 五重专项

`tests/five-boss-integration.test.js` 覆盖：

- 房主扣票、队友不扣票；
- 单人零票且有体力可开局；
- 单人连续两轮各扣 35 体力；
- start/finish/abort 事务回滚；
- 认证入场凭证；
- forged identity 拒绝；
- abort 缺字段恢复；
- stale run 幂等；
- 房间返回与续战；
- AI 自动续战固定 COM 编队；
- 幻想第 10 层真实 `/abort` 保层；
- 幻想第 15 层成功奖励和新一轮重置。

最终：

```text
50/50 通过
```

### 9.2 屏障与连接

`tests/multi-barrier-recovery.test.js` 覆盖：

- 初次 loading timeout；
- 缺席席位宽限；
- reconnect 与 replacement；
- 五重 active 静默不触发普通 heartbeat；
- `LevelNext` 重建 loading lease；
- 第二场景 ready 玩家等待慢队友；
- 房主原 lobby 在线时完成 `RETURNING`；
- 旧 timer 不污染新 generation；
- 结算后 retired seat 不被重新打开。

最终：

```text
24/24 通过
```

### 9.3 统一准入

`tests/multi-guest-eligibility.test.js` 覆盖：

- 未知副本默认放行；
- 五重 Rank 129 拒绝；
- 五重 Rank 130 进入持票检查；
- 队友票券只读不扣；
- 12 个高难副本 Rank 120；
- 精确前置关卡；
- 联动副本分类兼容。

`tools/multi_room_identity.test.cjs` 使用真实 HTTP/TCP 流程覆盖：

- 铃铛；
- 好友/关注房；
- 房间号；
- 直接选房；
- TCP 握手；
- 选房后资格变化；
- Rank 129/130 边界；
- 无票/有票；
- 库存不消耗。

### 9.4 幻想保层

`tools/mode15_persistent_completion.test.cjs` 覆盖：

- 第 5 层失败保持 5；
- 第 10 层失败保持 10；
- 第 15 层失败保持 15；
- 不写当前层成功记录；
- 不发幻想边界 token；
- 房主与救援 stale multiplayer active quest 均不 reset；
- 单人第 6 层失败仍回第 1 层；
- 主动 reset 仍清理本轮状态并保留永久历史。

`tests/mode15-disconnect-load-recovery.test.cjs` 使用真实 `/cn/load` 覆盖：

- 第 10 层房间已消失；
- 房主仍有 persisted multiplayer active quest；
- 登录后 active quest 被清理；
- unfinished multi 列表清空；
- 当前层仍为 10；
- 第 10 层允许重新挑战；
- 第 5 层不允许回退；
- 奖励库存不变化。

### 9.5 完整套件

执行：

```bash
npm run typecheck
./node_modules/.bin/tsc
node tools/run-isolated-check.cjs --test \
  tests/five-boss-integration.test.js \
  tests/multi-barrier-recovery.test.js \
  tools/mode15_persistent_completion.test.cjs \
  tests/mode15-disconnect-load-recovery.test.cjs \
  tests/multi-guest-eligibility.test.js \
  tools/multi_room_identity.test.cjs
npm run test:multiplayer-connectivity
npm run test:multicore
npm run check:out -- --worktree
git diff --check
```

已完成结果：

- TypeScript 类型检查通过；
- TypeScript 完整编译通过；
- 五重及多人专项 `51/51`；
- 屏障与重连 `24/24`；
- 幻想持久化 `5/5`；
- 真实幻想 `/cn/load` 掉线恢复 `1/1`；
- 统一准入规则 `7/7`；
- 完整多人连接套件通过；
- 四核默认、响应 worker、checkpoint、persistence worker、writer thread、单人结算
  writer 一致性套件通过；
- `out/` 与源码对应检查通过；
- `git diff --check` 通过。

## 十、测试隔离与清理

所有本批测试遵循：

- 隔离数据写入项目 `tmp/`；
- 不读取或修改生产玩家数据库；
- 每项测试使用独立临时目录；
- 测试退出显示 `temporary state removed`；
- 结束后检查 `tmp/` 内容数量为 0；
- 无残留 `cn-server`、`run-isolated-check` 或多人测试进程；
- 没有把日志副本、数据库、缓存或 npm 临时目录写进仓库。

`out/lib/mode15-active-quest-recovery.js` 是对应源码的新增编译产物，已用 intent-to-add
纳入工作区检查，但尚未创建 commit。

## 十一、行为边界

### 保持不变

- 普通多人 heartbeat；
- 普通共斗失败结算；
- 五重房主费用；
- 五重队友助力不扣票；
- 五重发奖 receipt 幂等；
- 五重 initial/LevelNext loading deadline；
- 幻想单人层失败清整轮；
- 幻想第 15 层成功完成后开启新一轮；
- 新房间 AI 仍从玩家历史队伍池选择；
- 真人可以替换 AI；
- AI 数量与 Ready 时序。

### 有意改变

- 五重新队友必须 Rank 130 且持票；
- 五重单人维持 35 体力 + 1 张门票，同一整轮内重试不重复扣；
- 五重 active/next-scene-ready 不再被 25 秒普通 heartbeat 误杀；
- 五重回房可识别仍在线的原 lobby host；
- 幻想 5/10/15 未成功不再清整轮；
- 同一房间 AI 自动续战不再随机换队。
- 续战中缺席的铃铛助力成员可被房主显式 AI 补位替换，不再阻塞下一战。

### 未实现

- 没有迁移数据库；
- 没有修改客户端 4096 图集容量；
- 没有制作新的 APK/IPA 或 CDN 增量；
- 没有按猜测批量禁用自制角色；
- 没有自动合并到 `main`；
- 通过独立修复分支按 PR 流程交付，不直接推送 `staging` 或 `main`。

## 十二、上线观察

部署后至少观察一个 30-60 分钟高峰窗口。

### 五重

- 新建局 `battle_proof_missing` 应接近 0；
- 不应再出现合法连接因 remote address 变化被拒；
- `scene_ready -> heartbeat_timeout` 应降为 0；
- `settlement_host_return_timeout` 应显著下降；
- 下一场景应继续看到 `level_next/scene_ready`；
- 新队友 Rank 129 应被 `player_rank` 拒绝；
- Rank 130 无票应被 `five_boss_ticket` 拒绝；
- Rank 130 有票进入后库存不减少。

### 幻想

- 第 5、10、15 层掉线后重新登录仍显示当前边界层；
- stale active quest 应被清理；
- 当前层未成功时不增加幻想 token；
- 成功重打后才推进；
- 单人层失败仍回到第 1 层；
- 第 15 层成功仍正常开启新一轮。

### AI 自动续战

- 同一房间各轮 COM1/COM2 的角色 ID 应保持一致；
- 自动续战不应重新查询随机 AI 池；
- `U_1d93f4` 数量应明显下降；
- 若仍出现，区分首局与续战；
- 若首局仍出现，补充 room/quest/脱敏角色 ID 后做资源预算过滤；
- 同时观察 `C8113` 等具体资源缺失错误，它与图集容量错误不是同一根因。

## 十三、上线与回滚建议

推荐按以下顺序上线：

1. 先部署服务端，不需要数据库 migration；
2. 重启 Node 进程，让新 room runtime 结构生效；
3. 使用新房间验证 AI 自动续战，旧进程内房间不会保留新字段；
4. 验证五重 Rank 130 + 持票准入；
5. 验证五重完整两 Boss 流程；
6. 验证幻想第 5、10、15 层断线后重打；
7. 观察一小时结构化日志与客户端 crash 统计。

若需要回滚：

- 服务端代码和对应 `out/` 一起回滚；
- 无数据库 schema 需要逆迁移；
- 房间级 AI 快照只存在内存，重启即清除；
- 已有玩家永久进度不会因回滚脚本被批量改写；
- 不需要删除客户端资源或玩家物品。

## 十四、当前工作区说明

本次 PR 文件集包含同批次的统一准入、五重修复和用户原有
`out/multi/five-boss/rewards.js` 注释变化。交付时必须：

- 保留用户已有改动；
- 同时纳入源码、测试、文档和对应 `out/`；
- 不把测试数据库、日志目录或系统临时文件加入；
- 提交前再次执行 `npm run check:out -- --worktree`；
- 未经明确要求不得合并到 `main`。

## 十五、铃铛成员离房后 AI 补位无法续战

### 15.1 现象与根因

首战使用“房主 + 铃铛助力玩家 + COM”阵容。战斗结束后，助力玩家离开或只关闭
回房 TCP，房主侧随后能看到 AI 补满房间，但再次开始战斗没有反应。

续战保护通过 `expected_real_viewer_ids` 保存上一战的真人名单，避免真人短暂断线时
过早被 COM 抢位。这项保护同时存在于自动准备检查和最终 `StartBattle` 边界。旧实现
在助力玩家离开后可能只更新实时 roster，却没有同步释放该成员在以下结构中的记录：

- `member_viewer_ids`；
- `member_player_ids`；
- `expected_real_viewer_ids`；
- `room.mates`。

因此 UI 中虽然已经是“房主 + 两名 COM”，开战边界仍等待旧助力 viewer ID，
持续拒绝开始下一战。这不是 AI Ready 失败，也不是五重发奖账本问题，而是续战
真人席位保护与 AI 接管之间缺少明确的所有权转换。

### 15.2 修复

`removeRoomMember()` 现在原子释放成员登记、玩家映射、续战期待名单和持久 room
roster。正式 `Bye`、助力重连宽限到期和房主 AI 接管都收敛到同一清理规则。

房主在续战代次显式发送 `EnterComs` 时，服务端执行以下检查：

1. 仅允许房主触发该替换语义；
2. 仅处理 `lobby_generation > 0` 的续战大厅；
3. 只释放当前没有可读写 lobby socket 的非房主成员；
4. 在线真人保持原席位，不会被 AI 踢出；
5. 铃铛成员同时清理 rescue/reconnect 状态并阻止旧房间恢复；
6. 取消旧的 rematch roster 清理定时器，再由当前房间命令串行补入 COM；
7. AI Ready 后重新计算房主 Ready，最终冻结名单只包含实际真人。

普通 socket 闪断本身仍保留原有 25/60 秒重连宽限。只有明确 `Bye`、宽限到期或
房主主动选择 AI 接管时才释放席位，所以本修复不会把正常网络抖动直接变成永久离房。

### 15.3 诊断与验证

生产日志命中修复分支时会出现：

```text
[LOBBY] host AI replacement released absent rematch members: room=... viewers=...
```

新增集成场景完整执行：

```text
首战真人名单包含房主和铃铛成员
-> 铃铛成员只断开 socket，名单仍保留
-> 房主发送 EnterComs
-> 释放缺席铃铛成员
-> 两名 COM 补位并 Ready
-> 房主自动 Ready
-> StartBattle
-> 生命周期进入 BATTLE
-> 新五重冻结名单只包含房主
```

验证结果：

- TypeScript 类型检查和完整编译通过；
- 五重集成 `51/51`；
- 屏障与重连 `24/24`；
- 完整 `npm run test:multiplayer-connectivity` 通过；
- 房间身份、准入预约、可靠发送和生命周期专项通过；
- 测试数据仅写入项目 `tmp/`，结束后清理。

### 15.4 上线观察

部署后复现一次“铃铛真人首战后离房，AI 接替并开始第二战”。应看到上述
`host AI replacement` 日志，随后该房间进入新 battle generation。若 AI 已显示但仍
不能开战，保留同一房号附近的 `StartBattle deferred`、`expected_changed` 和
`MULTI-BARRIER` 日志，以判断是成员 Ready、五重冻结编队校验还是客户端没有发送
`StartBattle`，不要再把三类情况统一归因为 AI 补位。

## 十六、多人房间 H400 与登录任务恢复循环

本轮进一步排查了“创建或进入共斗房间时 H400，回到登录页后无法读取正在进行任务，
两个错误循环”的问题。完整日志计数、实现边界和验证记录见：

```text
docs/development/MULTIPLAYER-H400-LOGIN-LOOP-FIX-20261004.md
```

故障由两部分叠加：

1. 房间消失、旧请求、重复结算和成员状态变化等正常竞态被返回为 HTTP 400，旧客户端
   将其当作致命 H400 并退出登录态；
2. `/load` 又把缺少房号、房间已消失、关卡不一致、viewer 已不在真人战斗名单或席位
   已转交 AI 的 active quest 发布为 `unfinished_multi_quest_list`，客户端每次登录
   都重新尝试恢复或退出同一坏任务。

修复后只有“房间仍处于 `BATTLE`、关卡完全一致、真实 viewer 仍持有未退休席位”的
多人任务可以恢复。其他孤儿任务按 `player_id + play_id` 条件清理；上一局的延迟
finish、abort、continue 和 writer cleanup 不能删除或修改下一局。

已认证玩家遇到的正常生命周期竞态改为协议内 200：

- 不存在或已过期关卡创建房间使用 `result_code=4507`；
- select/prepare/summon/share_room 在房间消失时返回不可用终态；
- start 在房间消失、状态变化、费用不足或旧 run 结束时使用业务结果；
- 五重外层校验后、事务开始前房间又被解散的二次竞态使用 `200/4050`，不扣体力、
  门票，不建立 run 或 active quest；
- 普通多人旧 finish 返回 `clear_rank=0` 的完整零奖励结果；
- 延迟 abort/continue 幂等确认但不修改当前新局；
- 五重缺失 proof 或 run 已结束时返回零奖励终态，不伪造成功结算。

无效 session、畸形 viewer、陌生玩家越权、viewer/player 映射冲突、显式伪造
category/quest/room 和五重 `request_identity_mismatch` 仍保持硬拒绝。

最终验证：

- TypeScript 类型检查与完整编译通过；
- 五重专项增至 `53/53`；
- 多人恢复判定 `2/2`；
- active quest 条件删除 `1/1`；
- 连续两次 `/load` 不再发布同一孤儿任务 `2/2`；
- 完整多人连接回归通过；
- 完整多核、响应 worker、SQLite checkpoint/persistence/writer thread 回归通过；
- 测试状态位于项目 `tmp/` 并在结束后清理；
- 使用独立修复分支向 `staging` 提交 PR，没有直接推送或合并 `main`。
