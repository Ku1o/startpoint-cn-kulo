# 多人共斗断线排查与修复记录

日期：2026-10-03

范围：CN 多人大厅与战斗 TCP，协议为 `\0` 分隔 JSON 帧。

## 结论

本轮没有可用的生产 `cn-server.log` 或具体断线时间点，因此不能把每一次线上断线都归因到同一原因。源码审计和本地真实 TCP 复现确认了三条会造成偶发断线或污染重连状态的竞态，并已修复：

1. **异步握手与合包帧竞态**：服务端在 `handleHandshake()` 完成前就继续消费同一 TCP chunk 中的 Enter、SceneReady 或 heartbeat。缓存未命中时握手包含异步数据库读取，后续帧会因为 socket 尚未加入 `SessionManager` 而被丢弃。
2. **租约 timer 与已到达 I/O 的竞态**：Node 事件循环被同步 CPU/SQLite 工作占用后，超时 timer 可能先于已经到达内核缓冲区的 SceneReady/heartbeat 执行，旧代码会立即 `destroy()`，把服务端处理延迟误判为客户端掉线。
3. **握手期间提前关闭竞态**：peer 在异步握手完成前关闭时，close 回调可能先执行且找不到尚未索引的 client；握手随后完成又把已关闭 socket 加入房间，留下占用席位的陈旧连接并干扰重连。

项目还存在三条有意设计的服务端主动断线阈值。它们不是本轮新增，但在慢设备、弱网或 CPU 长暂停时会真实触发：

- 战斗场景加载固定上限：默认 60 秒；
- ready/active 战斗连接无入站活动：默认 25 秒；
- 发送 socket 持续背压：默认 15 秒，或后续队列超过 512 帧/4 MiB。

修复没有取消这些保护。到期判断现在先让出一次 poll/I/O 轮次再复核，只有仍然过期才断开。握手期间后续帧会留在原 buffer，握手完成后按顺序处理。

## 已确认的断开路径

| 原因 | 默认条件 | 服务端行为 | 处理 |
|---|---|---|---|
| `loading_timeout` | battle socket 接受后 60 秒内未处理 SceneReady；LevelNext 后也重新进入 loading | `socket.destroy()` | 保留阈值，增加 I/O 轮次复核 |
| `heartbeat_timeout` | ready/active 阶段 25 秒内没有被主线程处理到合法 battle 帧 | `socket.destroy()` | 保留阈值，增加 I/O 轮次复核 |
| `send_backpressure` | `socket.write()` 返回 false 后 15 秒没有 drain | 清空应用队列并断开慢连接 | 保留，新增原因统计 |
| `send_queue_limit` | 背压期间后续队列超过 512 帧或 4 MiB | 清空队列并断开慢连接 | 保留，边界测试通过 |
| `protocol` | 非法 JSON、超大帧、无终止符或错误首帧 | 立即断开 | 保留 |
| `admission` | 客户端构建准入被撤销、ticket 过期或 session 不匹配 | 拒绝或断开 | 保留 |
| `handshake_denied` | 房间不存在、阶段不允许、席位已退役或身份不匹配 | 返回 denied 后关闭 | 保留 |
| `login_replaced` | 同一 viewer 登录新账号会话、切换账号或退出 | 销毁该 viewer 的大厅/战斗连接 | 保留 |
| `superseded` | 同一 viewer/connection 建立替代 socket | 旧 socket 隔离后关闭 | 保留 |
| `room_rejected` | 席位预留失效、房间消失或满员 | 发退出消息后关闭 | 保留 |
| `room_disband` / `rescue_timeout` | 房间解散或救援等待到期 | 发退出消息并关闭 | 保留 |
| `peer_fin` / `socket_error` | 客户端主动 FIN 或操作系统报告网络错误 | 正常清理房间索引 | 由网络/客户端触发 |

TCP keepalive 的 `SESSION_TCP_KEEPALIVE_MS=10000` 只是首次探测延迟，不会在 10 秒后自动断线。真正的应用层战斗租约是上述 60/25 秒。

## 修复内容

### 握手串行化

`src/multi/tcp/server.ts` 增加单 socket 的 `handshakePending` 状态：

- 第一帧通过准入后启动异步握手；
- 握手完成前停止消费该 socket 的后续完整帧；
- 同一 chunk 或后续 `data` 事件追加的帧继续保留在有界 buffer；
- 握手成功并完成 socket 索引后继续按原顺序处理；
- 握手拒绝或异常后不再调度这些帧。
- 若 peer 在握手完成前关闭，握手落地后再次执行索引清理，不能遗留陈旧 room client。

这不会阻塞其他 socket；等待只发生在当前连接自己的帧序列中。

### 超时前 I/O 复核

`src/multi/state/SessionManager.ts` 的 loading 和 heartbeat timer 到期后使用一次 `setImmediate()`：

- poll 阶段先处理已经到达的 SceneReady/heartbeat；
- 若新活动替换了旧 timer，旧检查通过 timer identity 直接退出；
- 若一次 I/O 轮次后仍是同一租约且确实过期，才执行原有断开。

保护阈值、AI 接管、Leave 顺序和房间屏障语义均未改变。

### 固定基数断线统计

新增 `src/multi/tcp/disconnect-diagnostics.ts`：

- 每个 socket 只保留第一个明确原因；
- `close` 时累计到固定枚举计数；
- 不记录 IP、viewer、room、token 或消息正文；
- 通过现有 `[MEM]` 的 `counters.tcpDisconnects` 输出；
- 没有每包日志和高基数 Map。

重点字段：

```text
counters.tcpDisconnects.total
counters.tcpDisconnects.loading_timeout
counters.tcpDisconnects.heartbeat_timeout
counters.tcpDisconnects.send_backpressure
counters.tcpDisconnects.send_queue_limit
counters.tcpDisconnects.protocol
counters.tcpDisconnects.admission
counters.tcpDisconnects.login_replaced
counters.tcpDisconnects.peer_fin
counters.tcpDisconnects.socket_error
counters.tcpDisconnects.unknown_close
```

计数是进程启动以来累计值。比较相邻 `[MEM]` 样本的增量即可判断某时间窗的主要断线来源。

## 验证

一键运行：

```bash
npm run test:multiplayer-connectivity
```

`tools/run-multiplayer-connectivity-check.cjs` 将每个测试放在项目内独立的
`tmp/multiplayer-check-*`，并在成功、失败或信号退出后清理。该入口不依赖其他
性能优化分支，可以单独在当前 `main` 基线上复现。

最终正式结果：20 个隔离测试文件，共 94 项通过、0 失败、0 跳过；真实 TCP 准入场景内部另完成 38 个协议检查。交叉执行 `npm run test:multicore` 仍为 63 项通过、2 项条件性跳过、0 失败。

重点新增回归：

- 真实 loopback TCP 将握手和首个业务帧写入同一个 chunk；
- 异步握手完成前业务帧不被消费，完成后按序到达 handler；
- peer 在异步握手期间关闭后不会留下已索引的陈旧 client；
- loading timer 已触发但 SceneReady 在 I/O 复核前到达时不掉线；
- heartbeat timer 已触发但活动帧在 I/O 复核前到达时不掉线；
- 真正超过租约时仍会断开；
- 断线统计保留第一个原因且字段数量固定；
- `write(false)` 的首帧不重复，后续帧在 drain 后按序发送；
- 发送队列第 513 个后续帧触发 512 帧硬上限并归因 `send_queue_limit`。

本轮还复跑了房间准入、房间解散、连接 generation、host 回连、身份边界、场景屏障、relay 快照、结算生命周期、TCP guardrails、客户端准入和五重真实 TCP 断开/重连集成。

## 上线排查

部署并重启后先保持默认阈值，通过 `[MEM]` 观察 30-60 分钟：

1. `loading_timeout` 上升：检查慢设备/资源加载、第二场景 LevelNext；确认 I/O 复核修复已部署后，再考虑把 `BATTLE_LOADING_LEASE_MS` 临时提高到 `90000`。
2. `heartbeat_timeout` 上升：同时看主线程 event-loop delay、CPU 和 `[WORK-PERF]`。若伴随长暂停，优先继续降低主线程同步 CPU；可临时将 `BATTLE_HEARTBEAT_LEASE_MS` 调到 `45000` 验证。
3. `send_backpressure` 或 `send_queue_limit` 上升：检查客户端下行、服务器出口和代理 TCP 缓冲，不要只增大队列；更大的队列会增加内存并延迟过期数据。
4. `peer_fin` 上升且服务端超时为零：更像客户端主动关闭、移动网络切换或 NAT/代理问题。
5. `socket_error` 上升：保留同时间段 warning 中的 errno，例如 `ECONNRESET`、`EPIPE`、`ETIMEDOUT`。
6. `login_replaced` 上升：检查客户端是否在共斗期间重复执行 `/player-auth/login`、账号切换或 logout。
7. `admission` 上升：检查客户端准入策略是否在战斗期间热更新、build 是否被禁用，以及 ticket/session 是否匹配。
8. `protocol` 上升：检查代理是否改写 TCP 数据、客户端版本是否一致，并查看 protocol violation 的有界原因。

建议一次只调整一个阈值并保留前后计数。不要同时关闭 heartbeat 和背压保护；真正失联的 socket 必须最终回收，否则房间屏障、AI 接管和内存都会被陈旧连接拖住。

## 仍需生产证据

本地没有该部署实例的日志和断线时刻，因此以下内容仍需上线数据确认：

- 各断线原因的实际占比；
- 是否集中在加载阶段、LevelNext、战斗中或结算返回；
- 是否只发生在特定客户端版本、运营商或代理；
- 断线窗口是否伴随主线程 event-loop delay/CPU 峰值；
- 是否存在 `ECONNRESET/EPIPE/ETIMEDOUT` 等明确网络错误。

拿到一轮 `tcpDisconnects` 增量后即可判断下一步应调租约、查网络、查登录重入，还是继续优化主线程。
