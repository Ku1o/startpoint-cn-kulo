# StarPoint CN 时间口径策略

日期：2026-10-03
适用范围：本仓库全部服务端代码（HTTP、联机 TCP、写线程、管理端、定时任务）
用途：把"虚拟时间 / 真实时间 / 每玩家偏移"的口径固化成可对照的规则，供每批
写线程迁移和涉及时间字段的功能改动前逐条核对。

本文只描述现状与规则。任何**口径调整**都必须单独提出、单独验证，不和一致性
修复混在同一批改动里（见第 8 节"待定项"）。

## 1. 时钟模型

| 组成 | 位置 | 说明 |
| --- | --- | --- |
| 全局偏移 `timeOffset` | `src/utils.ts`（毫秒，`null` = 系统时间） | 主线程唯一权威副本；`getServerTime()` 等 API 都读它 |
| 启动恢复 | `src/data/activeAccount.ts` → `restoreTimeOffset()` | 从 `.database/active_account.json` 读回；未设置时默认 `2024-08-14T12:00:00Z` |
| 管理端改钟 | `src/routes/web_api/server.ts` 的 `/time`、`/resetTime` | 调 `setServerTime()` / `setServerTimeOffset()` 并落盘 |
| 每玩家偏移 | `players.time_offset` + `getServerTimeForPlayer()` | 记录该行写入时的全局偏移，用于存档时间重基；写线程可直接从数据库读到 |
| 写线程偏移 | `src/lib/persistence/writer-client.ts` / `src/workers/sqlite-writer-worker.ts` | 写线程 ready 后立即推送 `set_time_offset`，之后每次偏移变化再推送；协议版本 `WRITER_PROTOCOL_VERSION = 2` |

写线程是独立线程，拥有自己的一份 `src/utils.ts` 模块。**任何主线程初始化、
写线程不会自动拥有的模块级状态都必须显式同步**；时间偏移是本批已同步的一项。

## 2. 时间 API 语义（代码事实）

| API | 语义 | 用途 |
| --- | --- | --- |
| `getServerTime()` | 虚拟 epoch（秒）= 真实 + 偏移 | 内容窗口、客户端可见时钟 |
| `getServerTime(date)` | 把给定 `Date` **原样**序列化为 epoch 秒，不加偏移 | 序列化已经是虚拟坐标的字段 |
| `getServerDate()` | 虚拟时间 `Date` | 写入虚拟坐标的列 |
| `realToVirtual(date)` | 真实 `Date` → 虚拟 epoch 秒 | 库内真实、出口转虚拟 |
| `getServerTimeForPlayer(playerId)` | 每玩家偏移优先，否则回落全局偏移 | 玩家存档相关的游戏时钟 |
| `clientSerializeDate(date)` | 取 UTC 字段格式化 `YYYY-MM-DD HH:mm:ss`，**不做偏移换算** | 客户端文本时间 |
| `deserializeClientDate(text)` | `YYYY-MM-DD HH:mm:ss` → UTC `Date` | 反向解析 |
| `getDateFromServerTime(epoch)` | epoch 秒 → `Date`，不做换算 | 反向解析 |
| `serializeRealTimeForVirtualClient(text)` | 库内真实时间字符串 → 虚拟 UTC+8 字符串 | 邮件、收件历史等"库内真实、出口虚拟" |

## 3. 口径规则

- **R1 游戏时钟 = 虚拟时间**：活动/卡池/每日复位/任务窗口/客户端的 `servertime`
  全部走虚拟时间。
- **R2 运维与安全 = 真实时间**：会话过期、登录票据、验证码、审计、管理端、
  维护租约、幂等收据、排行榜结算期限走 `Date.now()`，与虚拟钟解耦。
- **R3 客户端可见的时刻必须是虚拟坐标**：写入时用 `getServerDate()`，或读出时用
  `realToVirtual()` / `serializeRealTimeForVirtualClient()` 转换。两者必居其一。
- **R4 同名不同表可以不同坐标**（如 `created_at`），以第 4 节登记表为准，
  禁止按名字猜语义。
- **R5 虚拟坐标字段在全局偏移变化后要重基**：`players.time_offset` 记录写入时的
  偏移，`src/data/domains/player.ts` 的经验池重基逻辑据此保持真实经过时间；
  真实坐标字段（体力恢复、邮件、审计）不需要重基。
- **R6 写线程必须与主线程共用同一全局偏移**（协议同步）；每玩家偏移由写线程
  自行查库，不需要同步。
- **R7 时长不是时间点**：`*_elapsed_time_ms`、`endless_battle_max_round_time`
  是战斗耗时，禁止与时间戳互相加减。
- **R8 迁移到写线程的命令不得调用 `setServerTime*`**：那只会改一侧。改时间只能
  走主线程管理端。

## 4. B 层：数据库时间列归属

来源：`src/data/initializers/*`、`src/data/updaters/*` 与各领域模块内的
`CREATE TABLE`（含 `ALTER TABLE`/`ensureSchemaColumn` 追加列）。共 75 个时间/时长列。

### 4.1 虚拟坐标（写入即虚拟，出口原样或文本）

| 列 | 写入 | 读出解释 | 发客户端 | 客户端比较对象 |
| --- | --- | --- | --- | --- |
| `players.exp_pooled_time` | `getServerDate()`（默认行/登录维护） | 原样 epoch（`getServerTime(date)`） | 是 | 与 `servertime` 比较算经验池进度 |
| `players.last_login_time` | 登录维护 `getServerDate()` | `clientSerializeDate` 文本 | 是（资料页/登录信息） | 展示文本 |
| `players_active_quests.started_at_ms` | `getServerTime() * 1000` | 虚拟 ms，内部耗时计算 | 否 | — |
| `abyss_floor_records.recorded_at_ms` | `getServerTime() * 1000` | 虚拟 ms | 否（内部最好成绩） | — |
| `players_follows.created_at` | `getServerTime()`（秒） | 原样 epoch | 是（`follow_time`） | 与 `servertime` 比 |
| `players_start_dash_exchange_campaigns.period_start_time` / `period_end_time` | 活动主数据 | 原样 epoch（`getServerTime(date)`） | 是 | 与 `servertime` 比活动窗口 |
| `players.time_offset` | 写行时的全局偏移 | 偏移本身（非时间点） | 否 | — |

### 4.2 真实坐标 + 出口转换（库内真实、发客户端前转虚拟）

| 列 | 写入 | 读出解释 | 发客户端 | 客户端比较对象 |
| --- | --- | --- | --- | --- |
| `players.stamina_heal_time` | `new Date()`（真实） | `realToVirtual` | 是 | 与 `servertime` 比体力恢复 |
| `accounts.first_login_time` / `reg_time` / `last_login_time` | `new Date().toISOString()` | `new Date(...)`；资料页 `realToVirtual` | 是（登录/资料） | 与 `servertime` 比 |
| `players_mails.receive_time` / `create_time` / `reward_limit_time` | 真实 `YYYY-MM-DD HH:mm:ss` | `serializeRealTimeForVirtualClient` | 是 | 展示/期限 |
| `players_receive_history.create_time` | 真实文本 | `serializeRealTimeForVirtualClient` | 是（收件历史） | 展示 |
| `players_practice_battle_history.create_time` | `new Date()`（真实） | 历史接口 `serializeRealTimeForVirtualClient` | 是 | 展示 |
| `players_degrees.acquired_at` | `Date.now()`（真实 ms） | `formatAchievementDate(..., offsetMs)` 转虚拟 JST 文本 | 是（履历） | 展示文本 |
| `players_characters.join_time` / `update_time` | `new Date()`（真实） | 出口为 `getServerTime(date)` **原样 epoch，无转换** | 是 | 与 `servertime` 比（见 P1） |

### 4.3 真实坐标（服务器内部，不发客户端）

| 列 | 用途 |
| --- | --- |
| `sessions.expires`、`player_login_sessions.expires_at`、`player_login_codes.expires_at` / `consumed_at`、`player_login_claims.expires_at`、`player_login_credentials.created_at`、`player_login_audit.occurred_at` | 登录/会话/验证码/审计 |
| `account_transfer_audit.transferred_at`、`device_bindings.last_seen` | 账号接管与设备绑定 |
| `account_news_receipts.seen_at`、`player_payment_receipts.created_at`、`player_operation_receipts.created_at` | 幂等收据/审计 |
| `five_boss_gauntlet_runs.created_at` / `updated_at`、`five_boss_gauntlet_members.started_at` / `aborted_at` / `level_next_at` / `finalized_at`、`five_boss_gauntlet_receipts.settled_at` | 五重决战运行账本（真实 ISO） |
| `raid_event_global_state.updated_at`、`raid_event_global_kill_ledger.created_at`、`players_raid_event_overall_rewards.updated_at` | 讨伐战全局账本 |
| `players_carnival_event_reward_claims.claimed_at` | 嘉年华档位领取（真实 ms，用于补发时间） |
| `players_mission_counters.updated_at`、`players_mission_counter_values.updated_at`、`players_mission_counter_snapshots.updated_at` | 任务计数缓存时间（真实 ISO/`datetime('now')`） |
| `players_periodic_snapshots.updated_at` | 周期快照（真实） |
| `published_parties.created_at` | 发布队伍保留最近 50 条 |
| `quest_npc_party_pool.cleared_at` | NPC 队伍池新鲜度排序（真实 ms） |
| `carnival_event_folder_migrations.migrated_at`、`players_repair_versions.applied_at` | 幂等迁移/修复标记 |
| `daily_vmoney_mail_config.updated_at_ms`、`daily_vmoney_mail_runs.scheduled_at_ms` / `executed_at_ms`、`daily_vmoney_mail_grants.created_at_ms` | 每日 vmoney 邮件调度 |
| `leaderboard_seasons.started_at_ms`、`leaderboard_runs.started_at_ms` / `finished_at_ms` / `pending_started_at_ms`、`leaderboard_run_rounds.started_at_ms` / `finished_at_ms`、`leaderboard_settlement_configs.settle_at_ms` / `updated_at_ms`、`leaderboard_availability.updated_at_ms`、`leaderboard_settlements.settled_at_ms` | 排行榜赛季/轮次/结算（真实 ms；截止时间按北京时间填写，界面文本由服务端渲染） |
| `server_maintenance_jobs.lease_until` / `last_started_at` / `last_completed_at`、`server_storage_migrations.completed_at` | 维护租约与存储迁移 |

### 4.4 时长/计数器（不是时间点）

| 列 | 含义 |
| --- | --- |
| `players_quest_progress.best_elapsed_time_ms` | 最好通关耗时 |
| `players_practice_battle_history.elapsed_time_ms` | 练习战耗时 |
| `abyss_floor_records.elapsed_time_ms` | 深渊层耗时 |
| `players_rush_events.endless_battle_max_round_time` | 无尽最高层达成耗时（并列排序用） |
| `players.total_login_days`、`players_periodic_snapshots.login_days`、`players_box_gacha.reset_times` | 计数（登录天数/重置次数） |
| `players.birth` | 生日（`19900101` 形式，不是时间戳） |

## 5. A 层：写线程写路径的时间调用清单

### 5.1 已迁移

| 命令 | 时间调用点 | 口径 |
| --- | --- | --- |
| `single.settle_finish` | `missionEvaluationTime = new Date(getServerTime() * 1000)` | 虚拟（任务结算评估时间） |
| | `recordAbyssFloorFinishSync({ nowMs: getServerTime() * 1000 })` | 虚拟 ms |
| | `generateDataHeaders()` → `data_headers.servertime` | 虚拟 |
| | `"exp_pooled_time": getServerTime(playerData.expPooledTime)` | 虚拟坐标原样 |
| | `"stamina_heal_time": realToVirtual(playerData.staminaHealTime)` | 真实 → 虚拟 |
| | `finishLeaderboardQuestSync` → `finishedAtMs = Date.now()` | 真实 ms（排行榜域） |
| | `insertPlayerPracticeBattleHistorySync`（`create_time`） | 真实，出口转换 |
| | 嘉年华 `claimed_at`、称号 `acquired_at` | 真实 ms |
| `single.refresh_quest_progress` | 无时间列写入（只刷新深渊最好成绩 revision 标识） | — |
| `multi.cleanup_active_quest` | 无 | — |
| `multi.record_battle_facts` | `missionEvaluationTime`（由调用方传入） | 虚拟 |
| `mission.settle_categories` | `evaluationTime`（由调用方传入） | 虚拟 |

### 5.2 计划迁移（迁移前按第 4 节逐列核对）

| 路径 | 已知时间调用点 | 口径 |
| --- | --- | --- |
| 多人结算剩余（`src/multi/http/battle.ts` 514+） | `missionEvaluationTime = new Date(getServerTime() * 1000)` | 虚拟 |
| | `staminaHealTime: new Date()` | 真实（出口 `realToVirtual`） |
| | `exp_pooled_time` / `stamina_heal_time` 响应字段 | 虚拟坐标原样 / 真实转虚拟 |
| | 五重账本 `created_at`/`settled_at` 等 | 真实 ISO |
| | `players_active_quests.started_at_ms`（房间/开战写入） | 虚拟 ms |
| 抽卡 | 写路径当前无时间列（`reset_times` 是计数器）；活动窗口判定用虚拟时间 | 只读虚拟 |
| 邮件 | `players_mails.*` 真实字符串；`daily_vmoney_mail_*` 真实 ms | 真实 + 出口转换 |
| 排行榜 | `Date.now()` 全域（赛季/轮次/结算期限） | 真实 ms |
| 登录 | `player_login_*`、`sessions.expires`、`accounts.*_time` 真实；`players.last_login_time` 虚拟 | 两域并存，按列登记 |

## 6. C 层：全服读路径概览

- **虚拟读（主流）**：`generateDataHeaders()` 的 `servertime`、`/load` 系列、
  活动/商店/任务/卡池可用性判定、`getServerTimeForPlayer()`（玩家履历）。
- **真实读**：管理端面板、维护任务、排行榜截止判定、每日邮件调度。
- **转换读**：`realToVirtual()`（体力恢复、资料页登录时间）、
  `serializeRealTimeForVirtualClient()`（邮件、收件历史、练习战历史）。
- **未转换读（待评估）**：`players_characters.join_time` / `update_time`
  经 `clientSerializeDate`/`getServerTime(date)` 直接出口，见 P1。

## 7. 迁移前检查清单

- [ ] 命令读写的每个时间列都已在本文件第 4 节登记；新列先补登记再迁移。
- [ ] 写入坐标与登记一致；客户端可见字段存在出口转换（写入虚拟或读出转换）。
- [ ] 命令内没有 `setServerTime*`；改时间只走主线程管理端。
- [ ] `Date.now()` 与 `getServerTime()` 没有在同一事务里混算同一个逻辑时间。
- [ ] 时长字段没有和时间戳互相加减。
- [ ] 跨线程传递的 `Date` 仍是 `Date`（结构化克隆保留类型）。
- [ ] 主线程初始化、写线程不会自动拥有的模块状态已确认（当前：全局时间偏移已同步；
      资源热重载尚未广播，见 P4）。
- [ ] 回归测试：主线程 `setServerTimeOffset(非空值)` 后再启动写线程，跑一条读取
      `getServerTime()` 的命令并断言两线程一致。
- [ ] 真机验证：带非空偏移启动 8001，跑该路径，核对响应 `servertime` 与相邻时间字段
      的差值与预期一致，并抽查落库的时间列取值。
- [ ] 服务进程之外的脚本（建号、导档、修复工具）修改玩家行前，必须先恢复全局偏移
      （`restoreTimeOffset()` 或手工设置），否则会把真实时间写进虚拟坐标列。
      本次审计实测到：脚本建号未恢复偏移时，新玩家的 `exp_pooled_time` 比
      `servertime` 大一个偏移量（本地约 421 天）。

## 8. 待定项（口径调整，需单独提出与验证，未实施）

- **P1 `players_characters.join_time` / `update_time` 真实坐标直接出口**：写入用
  `new Date()`，出口 `getServerTime(date)` / `clientSerializeDate` 不做转换，客户端
  按自己的虚拟时钟解释，会看到偏移量大小的日期跳变（本地当前偏移约 −421 天）。
  需单独决定：改存虚拟坐标，还是出口 `realToVirtual`。改动会影响所有已写入的历史行，
  必须先定迁移方案再实施。
- **P2 同名 `created_at` 跨表坐标/单位不一致**：`players_follows.created_at` 是虚拟
  秒，`published_parties.created_at`、`players_degrees.acquired_at` 是真实毫秒，
  `five_boss_gauntlet_*` 是真实 ISO 文本。当前各自自洽，但按名猜语义会出错；
  如后续统一命名或单位，属独立改动。
- **P3 排行榜期限使用真实时间**：`settle_at_ms` 按北京时间真实时刻填写，服务端渲染
  为文本标签，因此客户端不做比较；若以后要做客户端倒计时，需要单独设计口径转换。
- **P4 写线程资源热重载未广播**：管理端 `/reload_assets` 只刷新主线程，
  rogue_event 配置在写线程内要重启服务才生效（非时间口径，但同属"主线程状态"类）。
- **P5 历史错误数据**：本批修复前，写线程内结算过的记录时间戳带真实时间；
  云服未部署写线程，本地 `.database/` 属测试数据，未做修正。
- **P6 外部工具建号口径**：审计期间实测到脱离服务进程的脚本建号会把真实时间写进
  `players.exp_pooled_time` / `last_login_time` 等虚拟坐标列。当前只作为流程要求写入
  第 7 节检查清单，未改代码。

## 9. 覆盖与验证状态

- 时间列清单来自全部 `CREATE TABLE`/`ALTER TABLE`/`ensureSchemaColumn` 来源，
  共 75 列；未逐列做运行时验证，属静态审计 + 抽样实测。
- 本批一致性修复的验证：`tests/sqlite-writer-thread.test.cjs`（偏移启动/变更/重置
  三种情形）、`tests/single-finish-writer-thread.test.cjs`（非空偏移下两种执行路径
  的响应时钟一致）、以及一次带偏移的真实 8001 单人结算（`servertime` 与虚拟时间
  差值为 0）。
