# 五重决战共斗掉线与 H400 修复

日期：2026-10-04

范围：五重决战多人战斗 TCP 生命周期、结算资格账本和 `multi_battle_quest/finish`。

## 问题表现

玩家进入五重决战多人战斗后，可能先看到“与队友通信断开”，完成战斗后再出现：

```text
发生意想不到的错误
No.H400
```

这不是单纯的 HTTP 结算耗时问题。日志中的完整链路为：

```text
五重 start 成功并绑定冻结 run
-> battle TCP 握手成功
-> SceneReady 成功
-> 持续交换大量战斗帧
-> 客户端 FIN，或 ECONNRESET / ECONNABORTED
-> LevelNext / Finalize 未到达服务端
-> 客户端仍提交成功 finish
-> 服务端以 battle_proof_missing 拒绝
-> 客户端显示 No.H400
```

## 日志证据

两批生产日志中的五重拒绝：

| 指标 | 日志 1 | 日志 2 |
|---|---:|---:|
| `FIVE-BOSS-REJECT` 总数 | 15 | 115 |
| `battle_proof_missing` | 12 | 95 |
| 涉及 run | 11 | 69 |
| 同一 run 多名成员失败 | 1 | 22 |
| 有完整连接诊断 | 8 | 84 |
| 客户端 FIN | 7 | 66 |
| socket error | 1 | 17 |

日志 2 中，有完整连接诊断的 84 个 `battle_proof_missing` 样本里，绝大部分已经：

- 通过 battle TCP 握手；
- 完成第一次 `SceneReady`；
- 交换几十到数千个战斗帧；
- 没有触发服务端 `loading_timeout`、`heartbeat_timeout` 或发送背压；
- 随后由客户端 FIN，或出现 `ECONNRESET` / `ECONNABORTED`；
- 数分钟后仍提交成功 `/finish`。

同一房间内多名成员经常在很短间隔内关闭 battle socket，说明五重客户端转场/结束路径会主动结束合作通道。原服务端把容易丢失的 `LevelNext + Finalize` 当作结算硬门槛，因此把已经真实进入战斗的完成请求误判成伪造请求。

## 根因

原有结算资格包含两部分：

1. 服务端在 `/start` 建立并扣费的冻结 run：
   - 固定 run ID、房号和真人 roster；
   - 绑定认证玩家与 `play_id`；
   - 房主门票和体力只扣一次；
   - 持久化 active quest；
   - receipt 保证 finish 重试不重复发奖。
2. 客户端通过 battle TCP 上报的 `LevelNext` 和 `Finalize`。

第二部分不是服务端独立计算的战斗结果，它仍是客户端通知，并且当前五重客户端会在通知到达前关闭 battle socket。它不能提供比认证 `/finish` 更强的防伪能力，却会把真实完成局拒绝成 H400。

## 修复方案

### 认证战斗进入证据

`five_boss_gauntlet_members` 新增可空字段：

```text
battle_entered_at
```

只有满足以下条件时才写入：

1. battle socket 已通过现有 session、房间、玩家和冻结 connection identity 校验；
2. 当前房间仍是对应的五重 run；
3. 本轮真人全部完成 `SceneReady`，或缺席席位经过原有宽限后被服务端缩编为 AI；
4. 服务端 SceneReady barrier 真正释放并准备发送 BattleStart。

单个客户端独自发送 `SceneReady` 不会获得结算资格。旧数据库通过幂等 `ALTER TABLE` 增加字段，已有行保持 `NULL`。

凭证写入与同一玩家的 `/finish` 共用持久化写队列。即使客户端在 BattleStart
后立即提交结算，finish 事务也必须等待先入队的 `battle_entered_at` 事务完成，
不会因异步落库先后顺序偶发误报 H400。

### 结算判定

新版本允许以下任一证据：

- `battle_entered_at` 已记录；或
- 旧版本完整记录了 `level_next_at + finalized_at`。

以下边界继续保持：

- run 必须由服务端建立且已完成入场扣费；
- 玩家必须属于冻结真人 roster；
- `player_id + play_id` 必须匹配；
- room、category、quest 和 ticket identity 必须匹配；
- persistent active quest 必须仍属于该 run；
- 已 abort 的成员不能结算；
- receipt 保证重复 finish 不重复发放奖励；
- 未完成全员 SceneReady 的请求继续返回 `battle_proof_missing`。

`LevelNext` 和 `Finalize` 仍继续记录，用于诊断客户端转场行为和兼容旧在途 run，但不再是新对局唯一的硬结算门槛。三种信号本质上都来自客户端；本次改动解决的是合法客户端尾部通知丢失造成的误拒绝，不把它描述成独立的反作弊系统。服务端仍依靠冻结 run、全员屏障、身份绑定、入场扣费、active quest 和幂等 receipt 约束结算。

### 五重连接关闭语义

普通共斗中，battle socket 关闭后会立即向剩余玩家广播 `Leave`。五重客户端的转场关闭会因此直接弹出“与队友通信断开”，并可能引发同房成员连锁退出。

修复后，已经通过五重首轮 BattleStart barrier 的连接：

- battle socket 关闭不再向其余玩家发送普通共斗的 `Leave`；
- 不再因为客户端按既有行为关闭 battle socket而弹出错误的队友掉线提示；
- 房间仍保持 `BATTLE`，等待各成员提交 `/finish` 或 `/abort`；
- 客户端在同一场战斗中重建 battle socket 时，继承本 run 已完成 BattleStart 的状态；
- 第二场景 `LevelNext` 已经建立的 loading barrier 继续使用原有 8 秒缺席处理，不改变转 AI和屏障收缩逻辑；
- 所有 battle socket 都关闭时，现有 15 分钟 abandoned-battle watchdog 仍负责回收永远没有 finish/abort 的房间；
- 普通共斗、握手拒绝、加载超时、heartbeat 超时和发送背压策略不变。

最后一名成员完成结算或房主放弃时，房间不再由 HTTP handler 在响应发送前直接转换或删除：

- 成功结算先完成 `/finish` 响应，再进入 `RETURNING`，保留原房号供房主与队友执行再战回连；
- `RETURNING` 转换失败或成员 `/abort` 时，再通过 `SessionManager.commitRoomDisband()`
  发送合法的大厅 `Disbanded` 通知并统一清理 lobby/battle socket、房间索引和计时器；
- 再战 generation 的房主回连宽限不短于队友的回连窗口，避免房主短暂掉线提前删除房间。

这既避免响应尚未送达时房间先消失，也保留最新 `staging` 已建立的五重续战流程。

## 未采用方案

曾验证过“收到一定数量战斗包并持续一定时间后，断线即可补齐 LevelNext/Finalize”的实验方案。它可以消除 H400，但包数和持续时间可以被客户端主动制造，并且会把只用于诊断的内存轨迹变成授权依据，因此已经完全移除。

最终实现：

- 不按包数或墙钟时间发奖；
- 不使用有界诊断缓存作为结算授权；
- 不伪造 `LevelNext/Finalize`；
- 不新增第二套奖励逻辑；
- 继续使用原有原子事务和幂等 receipt。

## 验证

定向回归覆盖：

- 未完成认证 BattleStart barrier 时，finish 仍返回 H400；
- 单人 SceneReady 不能让两人房获得结算资格；
- 两名真人全部 SceneReady 后，两人同时获得 `battle_entered_at`；
- 缺席席位宽限结束并转 AI 后，已就绪的幸存玩家获得 `battle_entered_at`；
- SceneReady 后 battle socket 主动关闭，缺少 LevelNext/Finalize 的 finish 仍成功；
- 错误 quest、错误 play ID、错误 run、已 abort 请求继续拒绝；
- finish 重试返回同一 receipt，不重复发奖；
- 五重首轮 BattleStart 后关闭 battle socket不发送普通 Leave；
- 五重重建 battle socket 后仍保持已进入战斗状态；
- 第二场景 loading barrier 的缺席处理保持原行为；
- 成功结算先发送 HTTP 响应，再进入 `RETURNING` 并允许队友搜索、选中和恢复原房间；
- abort 或续战转换失败时，通过标准房间协议清理连接；
- 再战 generation 的房主回连宽限覆盖队友回连窗口；
- 旧数据库迁移重复执行不改写旧行；
- 存档导入导出保留服务端五重账本。

验证命令：

```bash
npm run test:multiplayer-connectivity
npm run test:multicore
node tools/run-isolated-check.cjs --test \
  tests/five-boss-connection-diagnostic.test.js \
  tests/five-boss-integration.test.js \
  tests/multi-barrier-recovery.test.js \
  tests/admin-save-transfer-integration.test.js
```

所有测试使用仓库内 `tmp/` 隔离数据库并自动清理。

2026-10-04 最终验证结果：

- `npm run typecheck` 与完整 `tsc` 编译通过；
- `npm run test:multiplayer-connectivity` 通过，其中五重集成 42/42、屏障与重连 22/22；
- `npm run test:multicore` 通过，覆盖四核默认配置、响应 worker、SQLite checkpoint、
  persistence worker、writer thread、事务回滚及热点查询；
- 补充验证了保留首场五重入场标记时，第二场景掉线仍执行原有 8 秒缺席宽限、
  AI 缩编和合法 `Leave`；
- `npm run check:out -- --worktree` 通过，源码与受版本控制的编译产物一致；
- 测试结束后 `tmp/` 已删除，未留下测试服务、Node 进程或隔离数据库。

## 上线观察

部署后观察至少一个 30-60 分钟高峰窗口：

- `FIVE-BOSS-REJECT` 中 `battle_proof_missing` 应接近 0；
- `battle_entry_recorded` 应在五重 BattleStart 前后出现；
- `tcpDisconnects.peer_fin/socket_error` 可能仍存在，但不应再对应 No.H400；
- `loading_timeout/heartbeat_timeout/send_backpressure/send_queue_limit` 不应异常增长；
- finish receipt 重试不得增加重复奖励。

若仍出现 No.H400，应以新的 `battle_entered_at`、`battle_entry_recorded` 和 transport 事件判断是：

- 未完成首轮全员 SceneReady；
- battle entry 持久化失败；
- 请求身份或 active quest 不匹配；
- run 已被其他成员终结/放弃；
- 其他非 `battle_proof_missing` 错误。

## SET 7 说明

本轮没有修改 SET 7。`U_af660f` 的调用栈位于客户端
`PartyTranslator.createStatus -> PartyCarousel.getPartyData`，需要当前正式 APK 方法体和受影响玩家的脱敏编队快照继续复现。此前用于验证缺页假设的服务端自动补页实验已撤出，避免未经证据批量改写玩家编队。
