# 联机战斗转发独立进程

日期：2026-10-08

基线：`main` `40ee833`（PR #26 的五重掉线修复与战斗摘要已由作者整合进 main）

开关：`MULTI_BATTLE_RELAY_PROCESS=1`（默认关闭）

## 一、为什么

### 客户端容忍度

CN 客户端联机战斗是帧同步（`pinball/scene/battle/derailleur/BattleDerailleur`）。
每名客户端开局比队友的指令晚 15 帧执行（`MULTI_BATTLE_DEFAULT_BUFFER_FRAME = 15`，60 帧/秒，约 0.25 秒）。
队友的帧没到时客户端速度降为 0，等帧到了再继续。因此 A → 服务器 → B 这条路上任何一环耽误超过约 0.25 秒，
整个房间都会一起顿住。

### 正式服数据

数据来自正式服 `cn-server-20261005-012147`，约 3.9 天、5626 个分钟采样：

- 有 42% 的分钟里，主线程至少卡过一次超过 250 ms；超过 500 ms 的占 18%，超过 1 s 的有 180 分钟，最长一次 6.2 s；
- 主线程 ELU 中位数 44%，原因是结算写库全部在主线程同步执行（`CN_WRITER_THREAD=0`，见
  `RUNTIME-LOG2-FOLLOWUP-20261003.md` 的 10-04 生产 A/B 修正）：
  - 单人结算 `single.transaction` 约每分钟 316 次、平均 44 ms；
  - 多人结算 `multi.core`、`multi.mission` 等阶段单次最长也都超过 1 s；
- 联机转发本身很轻：`multi.relay.send` 单次最长 19 ms。问题在于它和这些工作共用一个事件循环。

单写者重构（同一文档的「修订后的推进顺序」）能降低主线程负载，但工作量大，还牵涉数据一致性。
本 PR 只做联机这一侧：转发不再经过主线程，主线程卡多久都不影响队友之间的帧。

## 二、做法

```
客户端 ──TCP 8003──▶ 主进程 net.Server
                        │ 读到首帧 socklet=cooperation_battle
                        │ child.send(handle) 交出 socket
                        ▼
                     转发子进程（out/multi/tcp/battle-relay/child.js）
                        ├─ Broadcast/Send：按房间成员表直接转发给队友，并回 ack
                        ├─ Heartbeat/Measurement：直接回应答
                        ├─ LineSpeedWarning：只计数
                        └─ 其余帧（握手、SceneReady、LevelNext、Finalize…）原样转给主进程
```

主进程用 `RelayProxySocket` 顶替原 socket（实现多人代码用到的 `write`、`end`、`destroy`、`destroyed`、
`writable`、`readable` 和各类事件）。握手、屏障、租约、`BattleStart`、`Leave`、AI 接管和结算代码都不变，
写出的帧经 IPC 交给子进程，在同一个 socket 队列里按顺序发出。

- **成员表**：`SessionManager` 每次改动 `battleClients` / `cidToBattleClient` 后，把该房间当前的
  {子进程 socket id、connectionId、generation} 推给子进程；同一轮事件循环内的多次改动合成一条。
  转发规则与 `snapshotBattleRelayRecipients()` 相同：不发给自己、只发给同一 generation、跳过已关闭连接。
  未绑定（握手尚未完成）的连接，其帧全部交给主进程处理。
- **活动汇报**：子进程每 250 ms（`MULTI_BATTLE_RELAY_ACTIVITY_MS`）汇报每个连接在本地处理的帧数、
  最长入站间隔、转发出去的帧数和背压时长。主进程据此刷新 25 秒心跳租约、在线状态和 `[MULTI-BATTLE]` 摘要，
  并按原逻辑复查客户端准入，未通过则断开。
- **背压**：子进程沿用同样的上限（`MULTI_SEND_QUEUE_MAX_BYTES` 4 MiB、`MULTI_SEND_QUEUE_MAX_AGE_MS` 15 s），
  超限时断开该连接，并按 `send_queue_limit` / `send_backpressure` 上报原因。
- **子进程崩溃**：它持有的战斗连接全部按断线处理（新断线原因 `relay_exit`），房间照常走 Leave、缺席宽限和
  AI 接管；主进程自动重启子进程，每次服务进程运行期间最多重启 `MULTI_BATTLE_RELAY_MAX_RESTARTS`（5）次。
  子进程不可用时，新的战斗连接留在主进程，行为与关闭开关时相同。
- **主进程退出**：子进程收到 IPC 断开后关闭全部连接并退出。

仍经过主进程、延迟不变的是 SceneReady → BattleStart、LevelNext、Finalize 和 Leave。它们每场只有几次，
不在逐帧路径上。

## 三、验证

`tests/multi-battle-relay-process.test.cjs`：三名真实 TCP 客户端放在单独进程里，每人约每秒 30 帧，
期间把服务器主线程同步卡住 1 秒（模拟一次长结算）：

| 模式 | 全部帧 p99 | 卡顿期间发送的帧 p50 / p99 |
|---|---:|---:|
| 主进程转发（开关关闭） | 974 ms | 510 ms / 877 ms |
| 转发子进程（开关开启） | 4 ms | 0.4 ms / 4 ms |

同一测试还确认：开启后，`[MULTI-BATTLE]` 摘要里的包数、转发数和 SceneReady 计数照常；主线程卡顿照常记入
`loopLagMaxMs`。

`tests/multi-battle-sim.test.cjs` 的两项五重用例（换场截止、队友中途掉线立即 Leave）在两种模式下各跑一遍，
并新增一项：杀掉子进程后三个战斗连接都被关闭，摘要记为 `relay_exit`，子进程自动恢复，服务器可以正常关闭。

## 四、上线与回退

- 默认关闭。先在测试服设置 `MULTI_BATTLE_RELAY_PROCESS=1` 并重启，日志出现 `[BATTLE-RELAY] relay process ready`
  即生效。
- **Windows 需要实测**：socket 句柄跨进程传递依赖 Node 的 IPC 句柄传递，在 Windows 上 Node/libuv 支持 TCP
  句柄，但本 PR 只在 Linux 上跑过测试。测试服要先确认三人联机能进战斗、能正常结算。
- 观察指标：`[MULTI-BATTLE]` 的 `maxInboundGapMs`（开启后由子进程按到达时间测量，不再包含主线程卡顿）和
  `longGaps`（每名成员最长的 3 段 ≥1 秒静默：时长 `ms`、距开战 `atMs`、发生时已换场次数 `scene`）、
  `tcpDisconnects.relay_exit`（应为 0）、`[BATTLE-RELAY]` 日志。
- 回退：删除该变量或设为 0 后重启，回到原来的主进程转发。代码回退连同 `out/` 一起回退即可，无数据库变更。

## 五、改动文件

- 新增 `src/multi/tcp/battle-relay/`：`protocol.ts`（IPC 消息）、`child.ts`（子进程）、`bridge.ts`（主进程侧、
  `RelayProxySocket`）
- `src/multi/tcp/server.ts`：连接处理抽成 `attachSessionSocket()`，战斗首帧时移交子进程；代理 socket 的活动与
  关闭原因处理；启动/停止子进程
- `src/multi/tcp/battle.ts`：`handleBattleRelayActivity()`
- `src/multi/state/SessionManager.ts`：成员变化时推送成员表
- `src/multi/battle-telemetry.ts`：`relayActivity()`
- `src/multi/tcp/disconnect-diagnostics.ts`：断线原因 `relay_exit`
- `.env.example`、测试与 `tools/run-multiplayer-connectivity-check.cjs`
