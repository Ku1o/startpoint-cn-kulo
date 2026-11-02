# SP-RELAY-001 · 实时所有者与可选战斗转发

适用：`startpoint-cn-private-clean` 多人房间、战局/场景屏障、TCP/IPC、准入续租、关闭及性能比较。出现早返等待、连接替换丢帧、租约续期失败，或需要比较转发隔离效果时读取。

验证层级：下列方法有源码、隔离进程、真实回环 TCP/IPC 和部分历史双 Android 证据；具体运行身份、开关及发布状态须另查。历史样本不代表当前服务、云服或公网验收。批次数字和完整依据见冻结历史（历史本地记录）。

## 先区分两种进程

- `MULTI_REALTIME_PROCESS` 是完整实时所有者：独立 child 持有 TCP listener、房间、战局、场景屏障、返回名单与有限租约。父进程只通过 command/projection 访问权威；玩家数据库、资格、队伍保存、支付、进度与回执留父侧，child 禁止访问玩家 DB。owner 故障应封闭处理，不回退 embedded 权威。
- `MULTI_BATTLE_RELAY_PROCESS` 是可选战斗帧转发路径。它不自动隔离握手、屏障、换场、Finalize 或混合房间的父侧转发。relay 的 native 保留/降级策略不能套用成 owner 故障后的权威回退。历史默认开关不是当前运行证据。

入口：[实时 owner 架构](../../MULTIPLAYER-PHASE2-REALTIME-OWNER-20261011.md)、[battle relay 实现](../../MULTIPLAYER-BATTLE-RELAY-PROCESS-20261010.md)。

## 房间、开局、返回与命令身份

- 房号不足以标识对象，必须绑定 instance、generation、run、scene、play 与 connection/socket。普通 Start 在持久化前预占 play，同 play 并发按引用计数释放；五王排队 Start 在副作用前复核冻结 run。
- 纯查询在 owner 的一次同步操作中取投影，不能先 lookup、排队后再授权已替换实例。Prepare/restore 只有明确未应用的 stale 才可按同 instance/gen 重查一次；unknown/busy 不能换 ID 重做。原局快照缺失仍保留合法付款，没有原 instance/run/play 绑定时不能改当前房间。
- Prepare 每次独立 pin；超时或未知不自动解 pin。FIFO 换场控制和屏障/到期回调等待 Commit/Cancel；恢复持久 play 时先新 pin，再精确对账旧 pin。持久 Commit 或终局丢 ACK，查原 ID 并重发同 ID，不能重做 SQL/支付；终局先 SETTLED/ABORTED 再解 pin。
- 房主回大厅不证明队友已结算或返回，成功 Enter 才是返回证据。Notify10/AI 扣除个人预留席位；早结算者从实际开放返回时起保留完整窗口。资格过期未知阻止新 Ready/Start，但不误解散房间；native 不可用使用其不可用响应，不能伪报房间已解散。
- HTTP 选房预留只是有限内存席位等待，不延长 TCP capability 或战斗租约。自动开战同时核对 Host.autoStart、全员 Ready 及协议席位要求；保留合法手动 Start。Notify8 仅接受当前已 Enter 的 LOBBY 连接更新本人，同值、旧代、旧 socket 和战斗阶段忽略；Host 变化重评倒数，Guest 变化不清既有 pending。

### 五王房主早返 Enter

个人已 SETTLED 而全队仍 BATTLE 时，Prepare 可回大厅，旧 Enter 门禁可能静默丢弃请求；心跳继续会令客户端无限等待。

仅在当前原房主连接暂存有界 Enter，终态按原 FIFO 复核 instance/gen/run/play/socket/deadline，先删 pending 再走原 Enter。COMPLETE_RETURN 会清 battleSession，身份检查必须在其前。过期或队列不可用应明确结束等待，不能仅清缓存继续心跳；旧 socket 清理不能清新连接。验证须走实际 Enter 链，直接设置 enterData 不覆盖该链路。

证据：[状态与 IPC 契约](../../MULTIPLAYER-PHASE1-STATE-IPC-20261011.md)、大厅契约修复（历史本地记录）、早返修复（历史本地记录）。

## ALS、准入续租与 IPC 预算

- 在已受理握手内创建的 timer 会继承 `tcpBusinessContext`，原 work 结束后 poll 可被 `TCP_BUSINESS_WORK_ENDED` 拒绝；只清 work 仍可能残留失效 admission proof。独立维护 timer 在创建点同步脱离两份 ALS，后续 poll 作为 fresh 请求通过父侧有限准入，不长期持有握手 grant。早返 pending timer 同样不得携带旧受理上下文。
- 保留普通 ended-work 拒绝、关闭封口、条目/字节预算、实际结果确认后扣耗、有限 deadline 与往返扣耗。过期、撤销、stop 后的迟到 ACK 不得重建租约。
- 验证 ALS 必须先结束原受理，再执行真实 Node Timer；可加速 interval，手调 callback 只能覆盖逻辑，不能证明上下文寿命正确。断因分类明确，失败日志只用白名单且限频，不输出 token/session/payload。
- IPC send callback 不是应用确认；条目、字节、年龄、结果和重复等待预算维持到应用 ACK，调用方超时不提前释放。旧身份拒绝后仍 ACK 以释放发送侧资源；child 故障明确断其连接并保留适用的 native 路径。TCP proof 等待实际业务结果。

证据：续租真实 Timer 与双机边界（历史本地记录）、完整 owner 受控验证（历史本地记录）。

## battle relay 成员、移交与帧顺序

- 完整成员表以 `sid:null` 表示 native/parent-owned socket。仅当源连接同代、全成员可写且都由 child 持有时，child 才本地 Broadcast/Send；其余将原帧交父侧统一 fan-out/ACK，防止双发和静默漏发。mixed 仍受父线程阻塞影响。
- 控制帧同 chunk 的后续帧保持父侧处理顺序。替换连接须隔离旧身份，不能假定立即关闭；同步移交 catch 也销毁原 socket。真实 spawn 可能只发 error/close 而无 exit，start/stop 都必须释放等待。
- `StringDecoder.lastNeed` 非零时保留 native，避免丢掉 UTF-8 尾字节。停止/重启达到上限时核对 native 生存与降级、generation、ACK 和控制顺序。
- 接收 socket 身份只在已确认成员快照且下一次替换前完成数据 ACK 的窗口内断言；跨变化窗口按座位检查恰好一次、无丢失/重复。客户端 write 时刻不是服务器路由点。
- members 没有正式协议 ACK；同 bridge/socket outbound 见证、Measurement 和处理见证只是测试的顺序/排空依据，不能称为新增正式确认或瞬时原子切换。generic ACK 无序号时只能核对每连接精确总数，不能声称逐帧 ACK 身份。
- 验证旧 superseded 源实际到达后不 ACK/投递、跨 generation 隔离、同接收块控制后紧随数据。握手未携带 generation 的事实与转发按代隔离分开判断；人为改变 generation 的探针不直接证明生产事故。Finalize ACK 仅确认信号，不等于 HTTP 奖励结算或立即停流。原验证 timer 契约为普通 ready/active 25 秒、loading 60 秒、LevelNext 90 秒；这是历史验证条件，当前值须查对应实现，重复 LevelNext 不应刷新原 deadline。

代表证据：早期修复（历史本地记录）、连接替换/成员 churn（历史本地记录）。

## 关闭和恢复

关闭保持 sticky 封新准入 → child FIFO cutoff ACK → 已受理尾部及业务结果排空 → 最终停止；停止后清 lazy 引用而未封口，持久事件 timer 可能再次 fork 同 ID owner。

父命令与 TCP token 绑定 owner/commandId；grant 登记不阻塞本地屏障，不逐帧登记 heartbeat/Measurement/数据。roomqueue 后延迟队伍写仅 retain 实际 tail；pin 控制关闭 discard 并阻止晚 unpin。Windows fork 同 console 的 CTRL_BREAK 可提前杀 child，child 应由 parent IPC 统一关闭；同步 fork 异常释放 startup ingress scope。数据库 writer/checkpoint 与后台任务关闭还须按[安全专题](security.md)处理。

子进程退出会断其连接，依赖原房间恢复；未 ACK 帧跨崩溃无损、无确认时刻的瞬时线性化、无感热迁移和实际 APP/WiFi 重启恢复不能由回环证据推出。

## 性能与验收方法

- ready、`maxInboundGapMs`、服务器控制处理耗时及 owner IPC 应用 ACK 都不是网络 RTT。网络延迟用匹配 Measurement ID 的真实 TCP 往返，与本进程耗时分列；p99 必须一起报告超时、故障和样本量。
- OFF/ON 对照需匹配实际运行字节身份、工作负载、成员全 child/mixed、网络、客户端时钟与测量窗口。正式关卡读取/分组/JSON 序列化的实际阻塞与额外哈希核验分开计时，负载门槛不能靠哈希凑足。多个场次/时间窗的 p99 范围不是总体 p99。
- 人工阻塞要落在 histogram 采样轮转可见窗口，失败时修正时序依据，不能删性能断言或反复运行直到通过。同步阻塞改善仅说明受控条件，不证明当前生产瓶颈。
- 数据验证同时检查 room/source/seq/payload/target、真实发送时间和两目标确认；有界释放在线记录，明确哪些是全量在线检查、哪些只落盘抽样、直方图是否量化。计划重连成功不等于真实客户端画面恢复/自动续局。
- 覆盖真实工作块内握手、SceneReady 屏障、LevelNext、Leave、重连与旧身份拒绝；独立 heartbeat/Measurement 通畅不等于父侧控制也不等待。多房长时回环、同机 CPU/RSS/GC 观测不能外推云服容量、无限期无泄漏或手机帧率。
- 收尾核对进程、连接/proxy、房间、timer、监听和数据库退出。复跑用新批次名拒绝覆盖旧证据，记录实际运行 dispatcher/out 字节身份，不能只按 HEAD 标识未提交实现。

代表证据：工作负载对照（历史本地记录）、控制及持续负载（历史本地记录）。公网/云端容量、iOS、Android ON 画面、五王完整多层/终奖、负载中完整 HTTP 房间/结算链、慢消费者/backpressure、静默完整到期与超长阻塞、真实 SCM/外层期限及断线/崩溃恢复均需对应证据；历史列表不是当前全部待办的确认。