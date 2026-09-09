# 五重决战结算连接诊断

用于排查 `finish` 返回 `battle_proof_missing`，但现有日志无法判断本人转场、结束消息为何缺失的情况。观察记录不参与鉴权、奖励或结算证据判定。

## 输出位置与阅读方法

正常战斗只更新内存。第一次请求拒绝的 `[FIVE-BOSS-REJECT]` 增加 `transport`，与原有 `proof`、`active` 一起输出到 stderr；原有重复合并仍生效。报错之后首次出现的新连接事件输出 `[FIVE-BOSS-TRANSPORT]`，用来补充迟到消息、连接关闭和重连信息，也受共享的限频与容量限制。

- `run`、`room`、`player` 关联同一对局及玩家；不要用房间级屏障消息代替本人证据。
- `createdAt`、`capturedAt`、事件 `at`、`firstAt`、`lastAt` 为 Unix 毫秒。可用 `new Date(value).toISOString()` 转成时间。
- `socket` 是本进程内递增的诊断连接编号。重连产生新编号；不记录原始连接 ID、IP、令牌或完整请求。
- `connections` 保留最近三个连接的消息总数、最近收包时间和失去索引后的消息数。`packets` 包含战斗通道的合法数组消息，不表示业务信号已写入。
- `events` 保留最近 16 个关键事件；`counts` 保留各类事件总数及首次、末次时间。`droppedEvents` 明确指出已从最近事件窗口移出的数量。

| 事件 | 含义 |
| --- | --- |
| frozen / http_start | 已冻结成员；HTTP 开始已成功登记 |
| handshake / accepted / handshake_denied | 可关联到冻结连接的握手尝试、接受或拒绝 |
| scene_ready / level_next / finalize | 服务端解析到该通知，detail 标明当时是否仍能查到连接 |
| level_next_recorded / finalize_recorded | 业务证据已成功写入；detail 区分 TCP 和 HTTP 兼容补记 |
| signal_rejected | 通知到达，但冻结身份或账本写入检查拒绝 |
| socket_end / socket_error / socket_close | 对端 FIN、套接字错误码及关闭结果；仅 close 本身不足以断言原因 |
| protocol_close | 服务端因协议或大小限制主动关闭，只记录原因类别 |
| loading_timeout / heartbeat_timeout | 服务端因加载时限或活动租约主动断开 |
| replaced / removed | 连接被替换或从业务索引移除，removed 区分当前与旧连接 |
| packet_unindexed | 曾关联的战斗套接字仍来消息，但已无法查到有效战斗客户端 |
| seat_expired | 该玩家的等待席位超时退出当前屏障 |
| room_disband | 房间被清理及清理原因，记录不会随房间删除立即丢失 |
| http_finish / finish_rejected | 结算请求到达及第一次拒绝 |

读取时比较“通知已到”和“证据已写入”。例如，`level_next` 有记录而 `level_next_recorded` 没有，应继续看 `signal_rejected` 或 `packet_unindexed`；若转场前已经出现关闭或超时，说明服务端在该连接上无法继续收到后续通知。服务器侧记录仍不能单独证明客户端是否曾尝试发送一个未到达服务器的数据包。

## 容量与性能

- 最多保留 512 个五重对局，每局最多三名真实玩家；满额淘汰最早登记的对局。
- 保存期限为登记后 60 分钟，查询或登记新局时清理过期记录；不新增清理定时器。
- 最近事件和连接数量均有硬上限，事件 detail 最多 80 字符。普通多人消息只做一次弱引用查找；已关联五重连接更新计数与时间，不复制消息正文或查询数据库。
- 拒绝与后续日志共用现有 `CoalescedDiagnostics`，每 60 秒最多保留 128 个不同日志键，重复项及超额项输出计数。
- 重启、超过保存期限或容量淘汰后，`transport.available=false`、`reason=not_retained`。这表示记录不可用，不能解释成“没有连接过”。完全无法关联到冻结成员的握手不会创建新玩家记录。

## 使用与验证

部署相应编译产物并重启后，沿原操作复现，保留该次启动的 stdout/stderr。无需开启全量 TCP 消息日志，也无需更新客户端或 CDN 资源。

验证覆盖内存与事件上限、过期及房号重用、普通消息无时间读取、日志写入异常隔离，以及真实本地 TCP 的握手、转场前关闭、HTTP 拒绝、重连后转场与结束消息到达、成功结算和重复结算。另覆盖加载超时、席位淘汰及心跳超时的玩家归属。

诊断本身不是结算前 H400 的业务修复。应根据部署后取得的连接记录定位并修复消息缺失原因，保留现有身份、本人证据及幂等奖励规则。
