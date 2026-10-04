# 四核服务器 CPU 优化实施记录

日期：2026-10-02

目标环境：4 核、8 GiB 内存、12 Mbps，CPU 为主要瓶颈

验证环境：macOS arm64、Node.js v26.4.0、隔离 SQLite 数据库

## 生产结论

- 4 核及以上自动启用多核配置；`CN_MULTICORE=0` 可整体回退。
- CPU 优先默认使用本地响应编码，`CN_RESPONSE_WORKERS=0`；吞吐或事件循环隔离优先时可试 `1`。
- 多核模式启用独立 SQLite checkpoint worker，主连接仍是唯一业务写入所有者。
- `/load` 读取/转换 worker 的原型验证失败，已从生产代码移除。
- 带宽充足且 CPU 是瓶颈时，`CN_LOAD_HTTP_COMPRESSION=off`。受限链路可单独恢复 gzip。
- SQLite 保持 `synchronous=FULL`；多核模式使用 64 MiB 页缓存和 256 MiB mmap。`NORMAL` 仅允许显式配置。
- Fastify access log、游戏明细日志、SQL 细粒度诊断和每请求阶段细分默认关闭；分钟级 CPU/ELU/路由汇总保留。

## 可行性结果

测试环境为本机 Node.js v26.4.0、隔离 SQLite 数据库、567 个角色、10 或 30 个并发真实 `/load`。数值用于相对比较，不代表云服务器容量。

| 方案 | 结果 | 决策 |
|---|---|---|
| 热 session/账号查询复用 prepared statement | 100 次热读无新增 prepare | 启用 |
| 登录 guard 合并查询 | 未绑定玩家 5.97 µs → 1.19 µs（约 -80%） | 启用 |
| 活跃存档状态内存缓存 + 单行玩家选择 | 1 万次解析 CPU 明显下降；重复样本下降 68% 到 93% | 启用 |
| Active Mission 静态事实/商店 master 缓存 | `load.reconcile` 约 7.8 ms → 1.25-1.29 ms | 启用 |
| 觉醒摘要请求快照复用 | `load.assemble` 约 2.9 ms → 约 2.0 ms | 启用 |
| SQLite 64 MiB cache + 256 MiB mmap | 30 并发重复样本显示小幅 CPU/墙钟改善 | 多核模式启用 |
| 轻量请求汇总 | 5000 次极短请求 CPU 161 ms → 147 ms（相对详细模式） | 默认启用 |
| 1 个响应 worker | 不同批次 CPU 约 +9% 到 +32%，墙钟无稳定改善 | 默认关闭 |
| 2 个响应 worker | 不同批次 CPU 约 +29% 到 +36%，墙钟无稳定改善 | 默认关闭 |
| 3 个响应 worker | CPU 增幅更高 | 不采用 |
| 1 个 `/load` 读取/转换 worker 原型 | 最新中位 CPU 约 +60%，且存在混合时点快照风险 | 移除 |
| gzip `/load` | 重复样本无稳定 CPU 优势；当前带宽不是瓶颈 | 默认关闭 |
| checkpoint worker | WAL backlog、固定读事务、busy 重试、关闭与恢复全部通过 | 多核模式启用 |

读取 worker 没有通过收益门槛的原因是当前 `/load` 仍包含较多主线程业务核对和写入，而且大型对象需要在读取线程、主线程和编码线程之间传输。后续若继续推进，应把完整的只读组装与最终 MessagePack 编码合并为单次 worker 命令，避免中间对象往返；在此之前不要扩大 worker 数量。

## 复现与清理

```bash
npm run test:multicore
npm run bench:multicore

# 结算基准与正确性哈希
PERF_ITERATIONS=500 \
  node tools/run-isolated-check.cjs tools/server-performance-benchmark.cjs
```

`tools/run-isolated-check.cjs` 将 `TMPDIR`、`DATA_DIR`、种子目录和 npm cache 指向仓库内 `tmp/cpu-check-*`，每个测试文件使用独立目录，并在成功、失败、SIGINT 或 SIGTERM 后删除。POSIX 下测试进程使用独立进程组，清理信号会覆盖其子进程；外部传入的抓包和性能输出路径会被移除。测试不读取或写入生产数据库。

## 实施背景

项目是 Fastify + `better-sqlite3` + MessagePack 的单进程 Node.js 服务。HTTP、联机 TCP、业务结算以及大部分 SQLite 访问经过主 JavaScript 线程；项目原本已经把大响应的 MessagePack 后处理、Base64 和可选压缩放入响应 worker。

联机系统持有进程内房间状态和真实 `net.Socket`，因此本轮没有直接使用 Node.js cluster 多开完整服务。实现遵循以下边界：

1. 联机、结算和业务写入继续由单个主进程拥有。
2. 只有不共享业务状态的编码和数据库维护任务使用 worker。
3. 使用可控内存换取固定 SQL、状态文件和 SQLite 页读取的 CPU。
4. 每项方案先做隔离基准；没有稳定收益的方案不作为生产默认。
5. 不改变数据库结构，不要求玩家存档迁移。

### MySQL 结论

本轮没有迁移 MySQL。当前仍为单机服务，SQLite 是进程内调用，没有 MySQL 的连接池、协议编解码和结果集跨进程序列化成本。迁移 MySQL 还需要重写大量同步领域 API 与事务边界，但不能直接解决业务计算和 MessagePack 编码占用主线程的问题。

只有在以下条件出现后才重新评估外部数据库：

- HTTP 层需要扩展为多个进程或多台服务器；
- 多个业务进程必须共享同一份可写状态；
- 指标证明 SQLite 单写者已成为主要瓶颈；
- 联机房间状态已抽成独立 Hub，不再依赖单进程内存。

## 环境准备

初始工作区没有 `node_modules`。准备过程如下：

1. 首次运行 `npx tsc` 时，由于依赖尚未安装，npx 拉取到了不相关的旧 `tsc` 包，未用于后续构建。
2. `npm ci` 最初因 npm `allowScripts` 策略以及锁文件中两条 `npmmirror` tarball URL 失败。
3. 临时将 `@types/bcryptjs` 和 `bcryptjs` 的 resolved URL 指向 npm 官方 registry，完成 278 个依赖的安装。
4. `better-sqlite3` 的 install script 被策略拦截后，由用户在本机完成原生模块准备。
5. 使用内存数据库执行 `SELECT 1`，输出 `SQLITE_OK 1`，确认原生绑定可用。
6. 使用项目本地 `./node_modules/.bin/tsc` 完成构建。
7. 任务结束前将 `package-lock.json` 的两条 URL 恢复为原 `npmmirror` 地址。
8. 删除临时锁文件备份和本次安装产生的 npm 错误日志。

最终 `package-lock.json` 没有差异；`node_modules` 位于项目内并由 `.gitignore` 忽略。

补充说明：

- 没有修改或绕过全局 `allowScripts` 安全策略；
- 曾检查 `node-gyp` 路径，但系统没有全局 `node-gyp`，因此没有把“全局手工 node-gyp 编译”作为项目方案；
- 用户执行项目目录内 `npm rebuild better-sqlite3` 后，原生绑定可用；后续只使用项目已有依赖和项目内命令；
- 测试命令卡住时，实际多数处于 TypeScript 编译、原生模块加载、checkpoint cooldown 或长测试运行阶段；此后统一使用可见 PTY 输出和有界轮询等待，不再把无输出误判为失败；
- 本轮未把 npm cache、临时数据库、基准报告或构建备份写到项目外作为长期产物。

## 本轮完整动作台账

本节按实际执行顺序记录本轮做过的分析、实验、实现、撤销、验证和清理。后面的专题章节保留实现细节与测量数据，本节用于审计“做过什么”和“最终是否保留”。

### 1. 项目分析与基线

| 动作 | 实施内容 | 结果 |
|---|---|---|
| 梳理运行模型 | 检查 CN Fastify 入口、TCP 联机服务、SQLite 数据层、每玩家写队列、MessagePack/Base64 响应链路、任务结算和现有 workers | 确认 CPU 热点主要仍在单个 JavaScript 主线程，不能直接用 cluster 复制完整进程 |
| 梳理进程内状态 | 盘点 TCP sockets、房间/休息室/招募、在线状态、结算快照、结束响应缓存、登录会话、玩家写队列和 `active_account.json` | 明确多进程迁移前必须先拆 Hub、持久化所有者和共享状态 |
| 建立正确性基线 | 运行结算基准并记录 response/state SHA-256 | 后续优化保持两个哈希不变 |
| 建立真实 `/load` 基准 | 使用 567 个角色的隔离玩家，执行 10/30 并发真实请求，记录 wall、process CPU、主线程 ELU 和 `load.* / encode.*` 阶段 | 确认主线程 ELU 接近 100%，并形成 worker/压缩方案的统一比较口径 |
| 建立微基准 | 分别测活跃存档解析、登录 guard、Fastify 日志、请求诊断和 SQLite 诊断 | 为默认开关和热点改造提供可重复证据 |
| 明确数据库边界 | 对照 SQLite 进程内调用、现有同步领域 API、事务边界和业务计算成本，评估 MySQL | 本轮不迁移；换库不能直接解决主线程业务计算与编码 CPU |

### 2. 第一阶段：低风险 CPU 优化

| 动作 | 实施内容 | 最终状态 |
|---|---|---|
| 固定 SQL 缓存 | 将 session、账号、设备绑定、玩家选择、箱池、活动、角色觉醒、卡池、邮件、选项、队伍、玩家挑战点、关卡、Rush、教程等固定查询接入现有 bounded `cachedStatement` LRU | 保留 |
| 有界动态集合查询 | 角色觉醒按 ID 查询由动态 `IN (?,...)` 改为固定 SQL + SQLite `json_each(?)` | 保留，避免集合长度改变时持续产生新 statement |
| 活跃账号状态缓存 | `active_account.json` 惰性读取一次；写操作复制 state/defaultPlayers，文件写成功后才替换内存缓存 | 保留 |
| 玩家选择单行化 | 原“读取账号全部 player ID，再在 JS 中选择”改为带优先级排序的单行 SQL | 保留 |
| 登录 guard 合并 | viewer/device 身份和 managed credential 状态分别合并为一次索引查询；未初始化 schema 时保持旧行为 | 保留 |
| `/load` 数据读取去重 | 抽出共享同步 reader，一次读取角色与 bond token、魔力节点、队伍和关卡快照；领域 API 复用相同实现 | 保留 |
| `/load` 组装分层 | 将流程拆为 `load.snapshot`、`load.reconcile`、`load.assemble`、`load.convert`、`load.serialize`；业务准备与纯客户端对象转换分离 | 保留，便于定位 CPU，协议输出保持一致 |
| 纯序列化函数 | 将 `serializePlayerSnapshot` 抽到无数据库读取的模块；旧入口仍负责体力、邮件、时间和模式配置等有副作用准备 | 保留 |
| Active Mission 静态缓存 | 缓存任务/角色/节点映射、商店 master 派生集合、角色故事映射等不可变事实 | 保留 |
| Active Mission 请求聚合 | 同一请求一次遍历聚合角色等级、进化、突破、羁绊、装备强化、魔力节点、二板完成和商店购买计数；关卡事实一次遍历同时建立列表和完成集合 | 保留 |
| Awake 快照复用 | Awake context 复用 `/load` 已读取的 player、character、quest 和 persisted mission；任务到角色及 stage 映射在模块加载时缓存 | 保留 |
| Awake 写后读取收敛 | 解锁 reconcile 复用传入 unlock map，只有实际写入后才读取权威结果 | 保留 |
| 日志降载 | Fastify 默认 `warn`；普通游戏、beacon、C3032/PLAY、箱池、关注、物品、队伍码、出售和未知路由明细通过 `gameVerboseLog` 延迟构造 | 保留；崩溃、错误和安全证据仍强制记录 |
| 请求诊断分级 | `ROUTE_PERF_DETAIL=false` 使用紧凑模式，只保留固定基数的状态、错误、总耗时和聚合指标；详细阶段 hook 改为显式开启 | 保留 |
| SQL 诊断默认关闭 | `SQLITE_DIAGNOSTICS=false`，需要排障时才启用 prepare/execute 计数和 1/64 采样 | 保留 |
| 诊断正确性修复 | 根 Fastify 实例统一建立请求状态；plugin 路由保留 outcome/custom encoding；abort/timeout 使用真实起点；同一请求最多结算一次 | 保留 |
| SQLite 诊断刷新 | 每次采集重新读取 PRAGMA，不缓存 checkpoint 所有权交接前的旧值 | 保留 |

### 3. 第二阶段：四核调度与架构边界

| 动作 | 实施内容 | 最终状态 |
|---|---|---|
| 统一多核配置 | 新增 `multicoreConfig()`；4 核及以上自动启用多核模式，响应 worker 默认 0，checkpoint worker 默认开启，均可显式覆盖 | 保留 |
| SQLite 参数集中化 | 新增 `sqliteSettings()`/`applySqliteSettings()`，统一校验 `FULL/NORMAL`、cache 和 mmap 范围 | 保留 |
| 四核 SQLite 默认值 | `cache_size=-65536`、`mmap_size=256 MiB`、`synchronous=FULL`；关闭多核时回到 2 MiB/0 | 保留 |
| checkpoint worker | 独立低频线程执行 PASSIVE，并按帧数/文件大小/cooldown 尝试 TRUNCATE；busy 不阻塞业务锁 | 保留 |
| checkpoint 所有权交接 | 主连接和 persistence worker 启动时均保留 `wal_autocheckpoint=1000`；外部 worker 首次成功后才切到 0 | 保留 |
| checkpoint 故障回退 | 连续三次异常或 worker 退出后恢复两个业务连接的 1000；后续成功可重新接管 | 保留并新增状态机单测 |
| checkpoint 优雅关闭 | 先发送 close，等待 `closed`/exit，最长 5 秒后 terminate | 保留 |
| persistence worker PRAGMA | worker 不再强制 `synchronous=NORMAL`，改为继承主配置，并向诊断报告 synchronous/cache/mmap/checkpoint | 保留 |
| 持久化提交后钩子 | `runPersistenceTransaction` 增加 `afterCommit`；非持久副作用只在 COMMIT 后执行，异常只记录、不把已提交成功变成重试 | 保留 |
| 响应 worker 对照 | 实测 0/1/2/3 个 worker；当前对象在主线程 pack 后再跨线程，复制与调度增加总 CPU | 默认 0，线程池和显式开关保留 |
| `/load` 读取 worker 原型 | 曾实现只读连接、V8 快照、陈旧检测、限流、回退和基准场景 | 因 CPU 增加约 60%及混合时点风险，生产 pool、worker 入口、环境变量和编译残留全部删除 |
| `/load` HTTP 压缩 | 对比 identity/gzip/br，目标环境带宽不是瓶颈 | 默认 `off`，gzip 功能保留供受限链路使用 |
| 完整 Node cluster | 评估直接复制 CN 服务进程 | 未实施；实时状态和写入所有权尚未外置 |

### 4. 正确性与生命周期审查

| 动作 | 修复内容 | 验证 |
|---|---|---|
| TCP 启动错误传播 | `startSessionServer()` 在 listen error 时 reject，并清理半初始化 server | 忙端口回归通过 |
| readiness 顺序 | HTTP 和 TCP 都成功监听后才写 `.logs/cn-server-ready.json`；启动和关闭都删除旧文件 | lifecycle 测试及静态检查通过 |
| 强制停机边界 | 优雅关闭超时或 close 失败时调用 `process.exit(1)`，不再只设置可能无法退出的 `exitCode` | 类型检查、构建和完整回归通过 |
| 关闭顺序 | 先停 TCP，随后 seed、调度任务、持久化队列和 SQLite workers，防止新回调进入正在排空的写队列 | 完整回归通过 |
| 抽卡并发规划 | 玩家资金、票券、活动次数、campaign 和积分在每玩家队列/事务内重新读取并规划 | 双并发、资金不足、积分累计测试通过 |
| 抽卡事务原子性 | 奖励、历史、扣费、积分、Active Mission、Awake、Degree Mission 和响应组装位于同一事务 | 故障注入后存档完全回滚 |
| seed/movie 副作用 | movie 先以 `flushPrevious:false` 规划，COMMIT 后才 mark/flush | 回滚不会污染下一请求 |
| 抽卡输入边界 | `number_of_exec` 只接受 `1..10` 安全整数 | 0、负数、小数、11、非安全整数均返回 400 且不写库 |
| 高频日志旁路 | 修正普通 beacon、未知路由及多个 API 直接 `console.log` 绕过日志开关的问题 | 默认不构造热路径日志字符串 |

### 5. 验证、工具和清理

| 动作 | 实施内容 | 结果 |
|---|---|---|
| 正式验收入口 | `package.json` 新增 `test:multicore`，先 typecheck/编译，再逐文件隔离运行 13 个测试文件 | 65 项中 63 通过、2 条条件跳过、0 失败 |
| 正式基准入口 | 新增 `bench:multicore`，顺序执行真实 `/load`、活跃账号、登录 guard、日志/诊断微基准 | 三轮中位数已记录 |
| 隔离运行器 | 每个测试文件创建仓库内独立 `tmp/cpu-check-*`；覆盖 TMP/DATA/seed/npm cache；移除外部输出路径 | 正常、失败和信号退出均清理 |
| 子进程清理 | POSIX 子进程独立进程组，SIGINT/SIGTERM 终止整个组 | 不遗留测试孙进程 |
| 生产数据保护 | 所有新增测试和基准使用隔离数据库，不访问正式 `.database` | 已检查 |
| 构建产物同步 | 每轮正式验收使用 `tsc` 重新生成受影响的 `out/` JavaScript | 源码与运行产物一致 |
| 启动脚本修复 | 构建输出过滤不再用 `|| true` 吞掉真实失败；日志从 `/tmp` 移到项目 `.logs/` | `bash -n` 通过 |
| 工作区清理 | 恢复 lockfile registry，删除临时备份/日志/数据库/ready 文件，确认 `tmp/` 为空 | 无本轮垃圾残留 |
| 文档归档 | 新建本记录、加入 `docs/README.md`，并同步持久化、响应 worker、性能和诊断旧文档的默认值 | 本文为最终权威记录 |

## 源码与工具落点

下表按职责列出本轮主要落点。`out/` 中对应 JavaScript 均由 TypeScript 构建生成，不作为独立设计实现重复说明。

| 范围 | 主要文件 | 内容 |
|---|---|---|
| 配置与入口 | `.env.example`、`src/cn-server.ts`、`src/lib/multicore-config.ts`、`src/lib/sqlite-settings.ts`、`scripts/start-cn.sh` | 四核默认值、日志/诊断默认值、监听就绪、关闭顺序、项目内日志 |
| SQLite 生命周期 | `src/data/index.ts`、`src/lib/sqlite-checkpoint-worker.ts`、`src/workers/sqlite-checkpoint-worker.ts`、`src/lib/sqlite-diagnostics.ts` | PRAGMA、checkpoint 维护、所有权和动态诊断 |
| 持久化边界 | `src/lib/persistence-coordinator.ts`、`src/lib/sqlite-persistence-worker.ts`、`src/workers/sqlite-persistence-worker.ts` | 命令执行、事务指标、PRAGMA 继承、`afterCommit` |
| 高频账号/登录 | `src/data/activeAccount.ts`、`src/data/domains/account.ts`、`src/data/domains/session.ts`、`src/lib/player-login.ts`、`src/routes/cn/playerLogin.ts` | 内存状态、单行玩家选择、statement cache、组合 guard 查询 |
| `/load` 读取与转换 | `src/data/readers/load-snapshot.ts`、`src/data/utils/player-data.ts`、`src/data/utils/serialize-player.ts`、`src/data/utils/client-player-snapshot.ts`、`src/routes/cn/load.ts` | 共享读取器、预加载复用、纯转换、阶段计时 |
| 固定 SQL 热路径 | `src/data/domains/{boxGacha,campaign,character_awake,gacha,mail,option,player,rushEvent,tutorial}.ts` 等 | 固定查询复用 bounded statement cache |
| Active Mission/Awake | `src/lib/mission/active-reconciliation.ts`、`compute-awake-summary.ts`、`computer-awake.ts` | 静态 master 缓存、请求事实聚合、快照复用、写后读取收敛 |
| 响应与监控 | `src/lib/cn-response-worker-pool.ts`、`request-diagnostics.ts`、`route-performance.ts`、`memory-diagnostics.ts`、`server-work-performance.ts` | worker 默认值、紧凑/详细诊断、固定基数统计和新增阶段 |
| 抽卡一致性 | `src/routes/api/gacha.ts`、`src/lib/gacha.ts`、`src/lib/persistence-coordinator.ts` | 队列内规划、原子事务、提交后 seed/movie、副作用边界 |
| TCP 生命周期 | `src/multi/tcp/server.ts`、`src/cn-server.ts` | listen 失败传播、ready 文件和优雅关闭 |
| 正式测试 | `tests/multicore-snapshot.test.cjs`、`sqlite-checkpoint-worker.test.cjs`、`sqlite-persistence-worker.test.cjs`、`tcp-server-lifecycle.test.cjs`、`request-diagnostics.test.cjs`、`gacha-exec-preservation.test.js` 等 | 配置、缓存、workers、诊断、任务、抽卡和登录回归 |
| 基准与隔离 | `tools/run-isolated-check.cjs`、`multicore-load-benchmark.cjs`、`active-account-benchmark.cjs`、`runtime-overhead-benchmark.cjs` | 可重复基准、项目内临时目录和自动清理 |

### 新增文件

- `src/data/readers/load-snapshot.ts`
- `src/data/utils/client-player-snapshot.ts`
- `src/lib/multicore-config.ts`
- `src/lib/sqlite-settings.ts`
- `tests/multicore-snapshot.test.cjs`
- `tests/tcp-server-lifecycle.test.cjs`
- `tools/active-account-benchmark.cjs`
- `tools/multicore-load-benchmark.cjs`
- `tools/run-isolated-check.cjs`
- `tools/runtime-overhead-benchmark.cjs`
- `docs/development/MULTICORE-CPU-OPTIMIZATION-20261002.md`

### 修改文件范围

本轮修改可按以下组审计：

- 配置/脚本：`.env.example`、`package.json`、`scripts/start-cn.sh`；
- 服务入口/运行时：`src/cn-server.ts`、`src/multi/tcp/server.ts`；
- 数据入口：`src/data/activeAccount.ts`、`src/data/index.ts`；
- 数据领域：`account.ts`、`boxGacha.ts`、`campaign.ts`、`character.ts`、`character_awake.ts`、`gacha.ts`、`mail.ts`、`option.ts`、`party.ts`、`player.ts`、`quest.ts`、`rushEvent.ts`、`session.ts`、`tutorial.ts`；
- 数据读取/转换：`src/data/readers/load-snapshot.ts`、`src/data/utils/player-data.ts`、`serialize-player.ts`、`client-player-snapshot.ts`；
- CPU/诊断/持久化：`cn-response-worker-pool.ts`、`game-logging.ts`、`memory-diagnostics.ts`、`request-diagnostics.ts`、`route-performance.ts`、`server-work-performance.ts`、`sqlite-checkpoint-worker.ts`、`sqlite-diagnostics.ts`、`sqlite-persistence-worker.ts`、`persistence-coordinator.ts`；
- 任务：`mission/active-reconciliation.ts`、`compute-awake-summary.ts`、`computer-awake.ts`；
- 登录/抽卡/API：`player-login.ts`、`gacha.ts` 及相关箱池、关注、物品、队伍、出售和 CN 登录路由；
- worker：`src/workers/sqlite-persistence-worker.ts`；
- 测试/基准：`tests/` 和 `tools/` 中本节列出的正式用例与工具；
- 文档：`docs/README.md` 及性能、响应 worker、持久化、诊断、内存专题文档；
- 构建产物：上述 TypeScript 对应的 `out/` 文件由 `tsc` 更新。

`out/data/domains/carnivalEvent.js` 和 `out/data/domains/session.js` 中 `git diff --check` 报告的三处行尾空格在任务开始前已经存在，本轮按“不覆盖用户既有改动”的约束保留。

### 实验后删除的生产内容

- `/load` worker pool 模块；
- `/load` worker 线程入口；
- `CN_LOAD_WORKERS` 配置；
- worker 专属集成用例和 benchmark 场景；
- 对应的陈旧 `out/` 编译文件。

保留的 `load-snapshot` reader 和 `client-player-snapshot` serializer 都由当前同步生产路径使用，不会创建线程。

## 基线记录

### 初始结算基准

使用 `tools/server-performance-benchmark.cjs` 执行 150 次合成结算：

| 指标 | 基线 |
|---|---:|
| Wall time | 470.37 ms |
| Process CPU | 611.55 ms |
| Characters | 567 |
| Quest rows | 1000 |
| Response SHA-256 | `cb94654b08db8e859460e26b968cf82bebb0ab94b45c297ee4ea3cd9a86b8cbc` |
| State SHA-256 | `e8af0184e103d6044252e2ce162eb147f1b3efd859d0c2d13d60045791b24c90` |

该工具用于检查结算正确性和相对变化，不代表线上容量。后续相同基准保持响应与状态哈希一致。

### 热路径检查

源码审查确认：

- `getSession` 在游戏请求中有大量调用；
- `resolvePlayerIdSync` 在路由和领域代码中有超过 100 个调用点；
- `resolvePlayerIdSync` 原本每次都同步读取并解析 `active_account.json`；
- 固定 SQL 中仍有部分路径重复调用 `prepare()`；
- 真实 `/load` 在 10 或 30 个并发请求时主线程 ELU 接近 100%。

## 已落地优化

### 高频 SQL 语句缓存

将每请求或每登录会执行的固定 SQL 接入已有的 `cachedStatement` LRU：

- viewer session 查询；
- viewer ID 查询；
-账号 session 查询；
-设备绑定查询；
-账号玩家列表；
-玩家 `time_offset`；
-首选存档解析。

验证：首轮预热后连续执行 100 次 session 和账号玩家读取，SQLite `prepare` 计数不再增长。

主要文件：

- `src/data/domains/session.ts`
- `src/data/domains/account.ts`
- `src/data/activeAccount.ts`

动态 SQL、迁移 SQL和只在启动期间执行的语句没有机械替换。

### 活跃存档状态内存缓存

`active_account.json` 改为惰性进程内缓存：

-首次使用时读取和解析文件；
-同一服务进程内复用 `WebState`；
-所有写入口先复制状态；
-文件写成功后才替换缓存；
-文件写失败不会污染内存状态；
-删除账号、默认存档切换和服务器时间仍同步写入文件；
-玩家选择从“读取全部 ID 并创建数组”改为一条缓存 SQL，直接返回首选或最小 ID。

一万次玩家解析的重复样本：

| 路径 | Process CPU | Wall time |
|---|---:|---:|
| 每次读文件 + 全量 ID | 150-154 ms | 143 ms |
| 内存状态 + 单行 SQL | 10-49 ms | 9-12 ms |

CPU 下降范围约 68%-93%，墙钟下降约 92%-94%。

运维边界：运行期间手工编辑 `active_account.json` 不会自动热加载。管理后台 API 写入会立即更新缓存和文件；外部手工修改后应重启服务。

### 登录 guard 合并查询

未绑定玩家原本在每个游戏请求进入 `installPlayerLoginGuard` 时依次查询 viewer 所属账号和账号是否已绑定，具体业务路由随后还会读取游戏 session。现在新增组合读取：

- `readPlayerLoginViewerAccess`：一次主键查询返回 `accountId` 和 `managed`；
- `readPlayerLoginDeviceAccess`：工具注册路径一次查询返回设备所属账号和绑定状态；
- TCP 登录检查复用组合读取；
-账号登录 session 的校验仍保持单条关联查询，不引入跨请求授权缓存。

2 万个隔离账号、每轮 3 万次查询、5 轮交错基准：

| 路径 | 旧实现 | 新实现 | 下降 |
|---|---:|---:|---:|
| 未绑定玩家 HTTP guard | 5.97 µs | 1.19 µs | 80.1% |
| 已绑定玩家鉴权 | 20.17 µs | 2.50 µs | 87.6% |

已绑定路径的旧/新对照包含项目先前已经完成的四查询合并；本轮新增收益主要是未绑定玩家的一次查询替代两次查询。

### SQLite 参数

新增 `src/lib/sqlite-settings.ts`：

| 模式 | `cache_size` | `mmap_size` | `synchronous` |
|---|---:|---:|---|
| 单核/回退 | 2 MiB | 0 | `FULL` |
| 4 核多核 | 64 MiB | 256 MiB | `FULL` |

说明：

- mmap 是地址空间窗口，不等于立即增加相同大小的 RSS；
- `FULL` 保留断电持久性；
-仅显式设置 `SQLITE_SYNCHRONOUS=NORMAL` 才降低同步级别；
-可通过 `SQLITE_CACHE_KIB` 和 `SQLITE_MMAP_MIB` 覆盖。

30 个并发真实 `/load` 的精确旧参数对照：

| 场景 | Wall 样本中位数 | CPU 样本中位数 |
|---|---:|---:|
| 旧参数：2 MiB cache / mmap 0 | 511 ms | 770 ms |
| 新参数：64 MiB cache / mmap 256 MiB | 505 ms | 762 ms |

样本显示小幅改善，没有出现退化。

### 四核线程预算

新增 `src/lib/multicore-config.ts`。4 核及以上自动进入多核配置：

- 0 个响应编码 worker；
- 0 个 `/load` 读取 worker；
- 1 个低频 SQLite checkpoint worker；
-主线程保留给 HTTP、TCP 联机、业务结算和业务写入。

响应 worker 能隔离部分编码工作，但当前 workload 下对象先在主线程 MessagePack 打包，再跨线程做整数修正和 Base64，复制与调度成本高于 CPU 收益。因此 CPU 优先默认关闭。需要对比时显式设置：

```env
CN_RESPONSE_WORKERS=1
```

### SQLite checkpoint 所有权交接

4 核模式自动启用 checkpoint worker，并增加故障安全交接：

1. 数据库初始化和离线工具始终先保留 `wal_autocheckpoint=1000`。
2. checkpoint worker 首次成功执行后，主连接才切换为 `wal_autocheckpoint=0`。
3. persistence worker 继承主服务的 `synchronous/cache_size/mmap_size`，启动时也保留 `wal_autocheckpoint=1000`。
4. 外部 worker 接管后，主连接和 persistence worker 才同时切换为 `wal_autocheckpoint=0`。
5. worker 连续三次 checkpoint 异常或退出后，两个业务连接都恢复 `wal_autocheckpoint=1000`；后续成功可重新接管。
6. worker 遇到 busy 时不等待业务写锁，由下一周期重试。
7. Fastify shutdown 时先等待 worker 确认关闭，最多等待 5 秒，再终止线程。

测试覆盖现有 WAL backlog、固定读事务、busy、cooldown、truncate、数据完整性、启动失败恢复、连续异常回退、成功后重新接管、ready/stopped 回调与重复关闭。

### `/load` 压缩默认关闭

由于目标服务器带宽充足、CPU 才是瓶颈，`.env.example` 改为：

```env
CN_LOAD_HTTP_COMPRESSION="off"
```

gzip 功能没有删除。带宽受限部署仍可显式设置 `gzip`，建议保持 level 1。

### 生产日志与诊断默认值

使用 5000 个 Fastify 内存注入请求和 25 万次 SQLite 查询做三轮独立进程中位数：

| 场景 | CPU 中位数 | 相对成本 |
|---|---:|---:|
| Fastify bare | 138.9 ms | 基线 |
| 轻量请求汇总 | 148.2 ms | 约 +6.7% |
| 完整阶段诊断 | 165.2 ms | 约 +18.9% |
| Fastify warn | 145.2 ms | 接近 bare |
| Fastify info | 154.5 ms | 高于 warn |
| SQLite 诊断关闭 | 28.4 ms | 基线 |
| SQLite 诊断开启 | 31.3 ms | 约 +10.4% |

最终复测仍得到相同方向：5000 次请求下轻量/完整阶段诊断为 153.2/159.7 ms CPU，`warn/info` 为 147.6/173.2 ms；25 万次查询下 SQL 诊断关闭/开启为 31.1/33.8 ms。

因此生产默认调整为：

- `LOG_LEVEL=warn`，不输出逐请求 access log；
- `GAME_VERBOSE_LOGS=false`，不生成热路径明细字符串；
- `GACHA_VERBOSE_LOGS=false`；
- `SQLITE_DIAGNOSTICS=false`，需要排查 SQL 时临时开启；
- `ROUTE_PERF_SUMMARY=true` 保留 CPU、ELU、路由、错误和总耗时；
- `ROUTE_PERF_DETAIL=false` 默认使用轻量汇总，需要定位 receive/application/serialize 时临时开启。

Linux/macOS 的 `scripts/start-cn.sh` 将日志写到项目 `.logs/cn-server.log`；日志默认值由服务代码和 `.env` 控制。

紧凑监控的最终回归还覆盖了 Fastify plugin 子实例路由、自定义编码耗时、延迟 abort 和 timeout。根实例统一建立请求状态，避免 plugin 路由丢失 outcome/encoding 指标；abort 保留真实开始时间，不再把耗时记为 0。

### Active Mission 与觉醒热路径

`/load` 阶段计时确认 SQLite 快照读取约 1 ms，主要 CPU 原本在 Active Mission 核对与觉醒存档组装。已完成：

- 按角色缓存不可变的魔力板节点 ID 和能力槽索引；
- 按 content repository 缓存 `treasure_shop`、`boss_coin_shop_item_category_map` 和约 1.1 MiB 的 `boss_coin_shop` 派生集合；
- 将同一 pattern 的角色等级、突破、羁绊、装备、魔力节点和二板完成事实每请求聚合一次；
- 将关卡进度的两次全量 `flatMap` 合并成一次遍历；
- 觉醒摘要缓存任务到角色和任务到 stage 的静态映射；
- 觉醒计算复用 `/load` 已读取的 player、角色和关卡快照；
- 觉醒解锁修复复用已读取的 unlock map，只有发生写入时才重新读取权威结果。

同一 30 并发测试中，`load.reconcile` 从约 7.7-7.8 ms 降至约 1.25-1.29 ms；`load.assemble` 从约 2.9 ms 降至约 2.0 ms。纯客户端对象转换约 0.2-0.3 ms，不值得继续拆分到 worker。

### 抽卡并发一致性

固定 SQL 缓存回归暴露了一个既有的同玩家并发问题：两个请求可能都在写队列外读到“尚无卡池状态”，随后第二个事务插入相同主键；票券、免费/付费石和活动次数也可能基于旧值规划。

修复后：

- 事务外只做静态合法性预检、确定抽取数量并生成随机结果；
- 玩家资金、票券、活动次数和卡池积分在玩家写队列内重新读取和规划；
- 扣费、奖励、领取历史、积分和任务计数仍处于同一事务；
- 觉醒修复、Degree Mission 结算和最终响应组装也在同一事务中，避免“数据库已提交但后处理抛错后返回 500”；
- 抽卡 seed/movie 的内存副作用只在 SQLite COMMIT 成功后的 `afterCommit` 执行，回滚不会污染下一次请求；
- `number_of_exec` 只接受 `1..10` 的安全整数，拒绝小数、负数、超限值和非安全整数；
- 并发请求资金不足时返回 400，不会推进存档；
- 同玩家两次合法并发十连可正确累计 20 积分，不再触发卡池状态主键冲突。

抽卡并发、失败回滚、兑换资格和旧 MOD 池测试均通过。

### 启停与就绪状态

服务只在 Fastify HTTP 和联机 TCP 两个监听器都成功绑定后写入 `.logs/cn-server-ready.json`。启动和关闭都会移除旧 ready 文件；TCP 端口占用会拒绝启动且不会发布伪就绪状态。

SIGINT/SIGTERM/SIGBREAK 仍按顺序停止联机入口、seed validator、后台调度、持久化队列和 SQLite workers。超过 `GRACEFUL_SHUTDOWN_TIMEOUT_MS` 或关闭过程失败时会以退出码 1 强制退出，确保服务管理器的停机上限真实有效。

## 阶段 2 实验结论

为验证 SQLite 读取和客户端数据转换能否铺到多核，曾实现只读连接、V8 快照传输、陈旧检测、限流与回退原型。审查和基准确认：

- 大型对象跨线程序列化、反序列化和回退显著增加总 CPU；
- 全库 `data_version` 会因无关玩家写入导致当前快照失效；
- worker 等待期间继续读取 active quest 等状态会产生混合时点响应；
- 队列饱和时会同时支付快照和本地回退成本。

因此 `CN_LOAD_WORKERS`、worker pool 和 worker 入口已从生产代码移除。保留的 `load-snapshot` reader 与纯 serializer 只用于同步路径去重，不启动线程。

## 未采用方案

主要决策数据来自 30 个并发真实 `/load`、每种场景三轮中位数，测试玩家拥有 567 个角色。

| 场景 | Wall 中位数 | CPU 中位数 | 相对默认 CPU | 决策 |
|---|---:|---:|---:|---|
| 验证默认：0 response / 0 load / identity | 248 ms | 330 ms | 基准 | 启用 |
| 1 个响应 worker | 248 ms | 360 ms | +9.1% | 默认关闭 |
| 2 个响应 worker | 250 ms | 448 ms | +36.0% | 不采用 |
| 3 个响应 worker | 248 ms | 426 ms | +29.3% | 不采用 |
| 1 个 `/load` 读取/转换 worker 原型 | 304 ms | 528 ms | +60.2% | 已移除 |
| gzip，本地编码 | 252 ms | 378 ms | +14.7% | 默认关闭 |

与第一轮改造完成时的同类 30 并发样本（约 488 ms wall / 698 ms CPU）相比，第二轮源码热路径优化后的样本约为 248 ms wall / 330 ms CPU，分别下降约 49% 和 53%。该数据用于相对决策，不是云服容量承诺。

审查修复后的最终三轮复测如下。运行时背景负载令绝对值高于上表，但同批次相对结论一致：

| 场景 | Wall 中位数 | CPU 中位数 | 相对默认 CPU |
|---|---:|---:|---:|
| 验证默认：0 response / identity | 272 ms | 384 ms | 基准 |
| 1 个响应 worker | 317 ms | 505 ms | +31.6% |
| 2 个响应 worker | 308 ms | 494 ms | +28.8% |
| 3 个响应 worker | 307 ms | 544 ms | +41.7% |
| gzip，本地编码 | 311 ms | 449 ms | +17.1% |

同次微基准中，活跃账号内存解析相对逐次磁盘解析减少约 88.8% CPU；登录守卫的未绑定/已绑定路径分别减少约 78.2%/87.8% CPU。

### `/load` worker 未通过收益门槛的原因

- `/load` 仍包含任务核对、永久修复、活动初始化和房间恢复等主线程工作；
-大型中间对象要在读取 worker、主线程和响应 worker 之间传输；
- V8 快照与对象恢复本身消耗 CPU；
-一个读取 worker 未显著降低主线程 ELU，反而增加总 CPU。

继续推进阶段 2 的前提是把完整只读组装与最终 MessagePack 编码合并成一次 worker 命令，避免大型对象多次跨线程。

## 测试记录

### 正式多核验收

```bash
npm run test:multicore
```

最终结果：

- 65 项相关测试；
- 63 项通过；
- 0 项失败；
- 2 项条件性跳过：旧版源码字节对照，以及非 Windows 平台原生内存探测；
-真实 `/load` 的 off、gzip、br、禁用 worker、延迟 hook 全部通过；
- 10 个并发请求均无重复响应；
- worker failure、timeout、queue saturation 和 shutdown 均正确回退；
- TCP 忙端口不会发布 ready，checkpoint 连续异常会恢复自动 checkpoint；
- persistence worker PRAGMA、事务回滚、抽卡提交后副作用和输入边界全部通过；
- 无 retained bytes、pending job 或响应写入残留。

### 扩展回归

额外覆盖：

-玩家登录与本地迁移；
-后台未备注账号清理；
-存档导出 worker；
-深渊时间修复；
-角色觉醒查询；
-队伍当前槽位；
- Rush 多回战；
-响应生命周期；
-任务性能和 statement cache。

一次扩展集合中 52 项里 51 项通过。唯一未直接执行成功的是：

```text
tests/player-save-portable.test.cjs
```

它要求命令行传入“已解压 Windows 便携包目录”，不是无参数测试，也与本轮服务端改造无关。正确调用方式：

```bash
node tests/player-save-portable.test.cjs <已解压的便携目录>
```

随后单独执行的玩家登录与后台清理回归为 2/2 通过。

### 正确性哈希

结算基准在优化前后保持一致：

```text
responseSha256 = cb94654b08db8e859460e26b968cf82bebb0ab94b45c297ee4ea3cd9a86b8cbc
stateSha256    = e8af0184e103d6044252e2ce162eb147f1b3efd859d0c2d13d60045791b24c90
```

## 可复现命令

```bash
# 类型、构建、多核/响应/checkpoint 正式验收
npm run test:multicore

# 多核场景中位数 + 活跃存档微基准
npm run bench:multicore

# 结算基准与正确性哈希
PERF_ITERATIONS=500 \
  node tools/run-isolated-check.cjs tools/server-performance-benchmark.cjs
```

## 测试隔离与清理

新增 `tools/run-isolated-check.cjs`。它将以下路径指向仓库内 `tmp/cpu-check-*`：

- `TMPDIR`、`TMP`、`TEMP`；
- `DATA_DIR`；
- `GACHA_SEED_DIR`；
- npm cache。

清理行为：

-正常结束、测试失败、SIGINT 或 SIGTERM 后删除临时目录；
- 每个测试文件使用独立临时目录；
- POSIX 下终止整个测试进程组，不遗留孙进程；
- 清除继承的 `CN_LOAD_CAPTURE_PATH` 和 `PERF_STATE_OUTPUT`，不允许测试向外部路径落盘；
-删除空的项目 `tmp/` 父目录；
-测试不访问生产 `.database`；
-不在项目外保存基准报告或数据库。

任务结束时还完成了以下清理：

-恢复 `package-lock.json` 的原始 registry URL；
-删除 `/tmp/package-lock.backup.json`；
-删除本次产生的 npm 错误日志；
-确认项目 `tmp/` 为空；
-保留任务开始前已存在的三处 `out/` 差异，没有覆盖用户改动。

全仓 `git diff --check` 仍会报告上述既有 `out/` 文件中的三处行尾空格；本轮新增源码和文档没有新增同类问题。

## 部署配置

4 核、8 GiB、带宽充足、CPU 优先的建议配置：

```env
CN_MULTICORE=1
CN_RESPONSE_WORKERS=0

SQLITE_CHECKPOINT_WORKER=1
SQLITE_CACHE_KIB=65536
SQLITE_MMAP_MIB=256
SQLITE_SYNCHRONOUS=FULL

CN_LOAD_HTTP_COMPRESSION=off
LOG_LEVEL=warn
GAME_VERBOSE_LOGS=false
SQLITE_DIAGNOSTICS=false
ROUTE_PERF_SUMMARY=true
ROUTE_PERF_DETAIL=false
```

修改 `.env` 后需要重启服务。此次没有 schema 迁移，也不需要转换现有存档。

### 上线观察指标

- `[ROUTE-PERF]` 的 `/load` 和结算 p95/p99；
- `[WORK-PERF] encode.*`；
- `responseWorkers.fallback/failed/timeouts/pending`；
- `sqliteCheckpoint.errors/busy/lastWalBytes`；
- `sqlite.main.prepareCalls/executeCalls/busyErrors`；
-主线程 event-loop delay 和整体 CPU。

## 回退

关闭本轮新增多核默认值：

```env
CN_MULTICORE=0
SQLITE_CHECKPOINT_WORKER=0
SQLITE_CACHE_KIB=2048
SQLITE_MMAP_MIB=0
SQLITE_SYNCHRONOUS=FULL
```

吞吐或事件循环隔离优先时试开一个响应 worker：

```env
CN_RESPONSE_WORKERS=1
```

恢复带宽优先：

```env
CN_LOAD_HTTP_COMPRESSION=gzip
CN_LOAD_HTTP_GZIP_LEVEL=1
```

代码回退不涉及数据库迁移：

-没有新增持久化表、列或索引；
-关闭 worker 不改变客户端协议；
-状态缓存沿用原 `active_account.json` 格式；
- checkpoint worker 停止后主连接恢复 `wal_autocheckpoint=1000`。

## 后续方向

当前合成 `/load` 并发下主线程 ELU 仍接近 100%，但热点已经发生变化：`load.reconcile` 从约 7.8 ms 降到约 1.3 ms，纯客户端转换只有约 0.2-0.3 ms，剩余成本分散在必要存档组装、小查询和主线程 MessagePack pack。

`active_account.json` 的进程内缓存只适用于当前单业务进程。多个 Node.js 进程会各自持有旧快照并可能相互覆盖，因此在启动 HTTP cluster 前必须把该状态迁入 SQLite，或增加跨进程锁和版本校验；不能直接复制现有进程。

### 下一批 CPU 优化

1. 在真实 4 核云服用 `node --cpu-prof` 采集短时 profile，并与 `[WORK-PERF] load.* / encode.*` 对照；合成吞吐不能代替生产采样。
2. 评估 Active Mission 事件驱动脏标记：角色、任务、商店、战斗事实变化时只标记受影响 pattern，登录时不再全量核对。必须保留旧存档首次全量修复与版本号。
3. 继续审计固定 SQL，但只缓存经过测试的固定 `get/all/run`；动态 SQL、事务内 monkeypatch 测试和会切换 statement 模式的调用不机械替换。
4. 若要把 MessagePack `pack()` 移到 worker，应将最终对象直接结构化克隆一次并在同一 worker 完成 pack、AIR 整数修正与 Base64；当前“主线程先 pack 再传 worker”不会降低总 CPU。
5. 高频任务结算可以继续复用 `MissionEvaluationReadContext`，减少同一请求内重复读取 player、角色、关卡和任务事实。

### 真正多进程迁移顺序

简单启动多个 `cn-server` 进程并不可行。以下状态都在进程内：TCP sockets、多人房间、休息室、招募、在线状态、结算快照、结束响应去重、玩家写队列和部分登录/管理会话。

推荐顺序：

1. **独立实时 Hub**：将 `multi/`、`lounge/`、招募和在线状态归一个进程所有；现有 `EmbeddedMultiCoordinator` 的可序列化命令边界可作为远程适配入口。
2. **独立持久化所有者**：继续把直接 `better-sqlite3` 写入命令化，使一个 writer 进程拥有业务写事务和每玩家队列。当前 persistence worker 只覆盖少量命令，尚不能作为完整单写者。
3. **HTTP worker 池**：HTTP 进程只做协议、只读事实和纯业务计算，通过 IPC 调用 Hub 与 writer。请求需按 viewer/player 保持一致性，不能只依赖随机负载均衡。
4. **共享认证/幂等状态**：玩家登录 session、finish response cache、操作 receipt 与管理 session 需要外置或由固定所有者提供。
5. **最后评估 MySQL**：只有 HTTP 已多进程、SQLite 单写者经指标证明确实限制吞吐时，再比较 MySQL/PostgreSQL。换库不是拆分实时状态的替代品。

在完成前两步之前，4 核机器最合理的生产模型仍是：一个业务主进程、一个低频 checkpoint worker、响应与 `/load` worker 默认关闭。
