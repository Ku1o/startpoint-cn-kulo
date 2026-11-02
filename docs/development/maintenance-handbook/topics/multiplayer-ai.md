# SP-MULTI-001 · 通关 AI 编队与延迟补席

适用：`startpoint-cn-private-clean` 多人普通关卡 AI 池、COM 补席与准备状态。候选出现未通关编队/幻想装备，战斗中编辑 SET，首次补席授权失败，或准备→未准备→准备时读取。

验证层级：出战快照、池选择和装备门禁有源码及隔离回归依据；ALS 回归另有真实 Node Timer 与 owner 探针；准备闪动调查有隔离帧回放及已登记客户端静态输入。均不自动代表当前运行、设备或云部署状态，批次结果见冻结历史（历史本地记录）。

## 入池必须使用开战快照

成功结算只证明战斗成功，不能证明结算时可变 SET 曾参与战斗。普通 SET 与历史通关池原本可能是独立来源，战斗中 HTTP 编辑 SET 会污染结算重读结果。

- 不从普通 SET 扫描补 AI 来源；选择装备时一起冻结实际 wireparty，并校对选中 SET 的角色、副位、装备和魂身份。
- 在 HTTP 房间队列内复制为每局结算快照，成功 finish 只录该快照；不在异步持久化后重读可变 room，也不重读 SET 补字段。
- 原验证契约为每副本仅保留最近 50 名玩家的通关编队，同玩家再次通关覆盖旧记录；录入、启动、重载均裁剪，不复活旧高战力 30 队保留策略。该容量不是当前运行身份声明，改容量另核目标和资源。
- 固定队、无法核实来源的旧局跳过入池。已有历史不足以证明全部正确；旧策略已淘汰记录不能恢复，不因此自动迁移玩家存档或整池清空。

入口：[快照契约](../../MULTI-NPC-CLEAR-SNAPSHOT-20261009.md)、[整合说明](../../MULTI-PR26-PR27-INTEGRATION-20261009.md)。源码定位：`src/multi/npc/quest-party-snapshot.ts`、`quest-party-pool-shared.ts`、`src/workers/quest-npc-party-pool-worker.ts` 与 `src/multi/tcp/lobby.ts`。

## 装备准入与空池兜底

普通关卡对含幻想专属武器或能力魂的历史候选、COM 缓存和房主编队整队拒绝，不能卸装后继续使用；幻想关卡保留完整装备。同关卡战力/属性筛选与合法 COM 续战缓存仍保留。

空历史使用合法房主 wireparty；房主违规则空席等待真实编队或真人席位变化。补席自身的延迟 ready 不递归重抽，外部 ChangeParty 仍触发补席。测试推进补席 timer 时，不能提前触发装备 idle deadline 导致合法解散后误判补席故障。

## 维护 timer 的授权寿命

HTTP room.share fallback 可能继承已释放 parent proof，TCP 延迟补席可能继承 active=false work，在 player.facts 前分别触发 `REALTIME_BUSINESS_ADMISSION_INVALID` / `TCP_BUSINESS_WORK_ENDED`。应核对实际失败阶段，不能一看到等待后失败就归因等待参数或续战真人预留。

独立 AI/NPC 维护 timer 在创建时同步隔离两份 ALS；RPC 仍走 fresh 有限受理，保留关闭、预算、旧 proof 拒绝与 instance/generation/当前 host 门禁。不能以移除普通受理检查修复维护 timer。

验收必须先结束原受理，再让真实 Node Timer 执行 callback；手工 mock callback 只证明名单/时序，不覆盖 ALS 继承。保留普通合同拒绝和停服后 `SERVER_CLOSING` 负例；源码修复、编译产物、现有服务实际加载分别确认。

证据：首次补席诊断与真实 Timer 验证（历史本地记录）。

## 准备状态反复切换与召唤幂等

已确认的历史故障链：自动补席后 legacy TCP Notify10 再次调用 `handleEnterComs`，绕过已有席位幂等检查，同连接 ID 的 COM 被重建为新对象并设未准备；旧 ready 回调仍向旧对象发送准备，新名单却携带新对象未准备，随后新 ready 再通知准备。

处理方向是统一召唤幂等入口，保留已有合法 COM 及状态，延迟 ready 复核对象仍属于当前席位；不能只调延迟掩盖重复重建。该方向在历史记录中是调查结论而非已实施保证，接手时须查实际实现。

### 时间参数能避开窗口，不能代替幂等

- `NPC_JOIN_DELAY_MS` / `NPC_READY_DELAY_MS` 改通知时刻，不检查已有席位；READY/JOIN 为零仍可能重复重建。延迟到两次召唤之后可能暂时隐藏取消，也可能增加等待；边界相等仍会交错。
- `MULTI_AI_FILL_TIMEOUT_MS` 改等待真人及 fallback 时刻。客户端等待值 `SUMMON_COM_SECONDS` 经玩家 config 的 `summon_com_seconds` 下发，不能与服务端补席时间混为一谈。
- 所审 Android 客户端：类型 3 随机招募 timer 起点早于 share_room 响应；房主仍在房、连接有效、人数不足、计时 active、状态 Idle 且超时才 `/summon`。取得 COM 后下一帧仍不足三人才 Notify10；Mates 更新人数可阻止尚未发出的召唤，本身不直接触发召唤。
- 让客户端等待晚于自动名单送达可避开正常时序窗口，不能绝对断言 ENV 无效；网络迟到、重复请求及部分补席仍依赖服务端幂等。首次 fallback 前若 `is_npc_mode=false`，`/summon` 可返回空队伍继续招募，客户端门槛不等于加入 AI 的时刻。
- 本地默认值、提供的云 `.env` 文件、云实际进程环境和云下发配置是不同证据；不能把本地窗口套到云文件，更不能把读取配置文件写成已核实云运行。具体等待数字留原任务记录。

代表证据：回放调查（历史本地记录）、客户端触发核对（历史本地记录）、提供配置核对（历史本地记录）。隔离帧/时序探针不等于设备实战，也不证明全部 ENV 组合都能或都不能绕开现象。