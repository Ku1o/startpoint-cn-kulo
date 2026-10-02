# MySQL 迁移方案

## 目标

将 MySQL 作为正式运行环境的持久化后端，同时保留 SQLite 作为当前运行和离线迁移基线，直到 MySQL 完成数据校验、结算回归和观察期验证。

迁移的重点不是更换数据库连接字符串，而是先收敛数据库所有权，使 HTTP 业务、实时房间和持久化执行之间有明确边界。实时 TCP 不直接访问 MySQL，也不等待数据库事务完成；房间状态继续由 realtime owner 管理。

## 当前规模与风险

当前服务端约有 114 个文件直接或间接依赖 SQLite，约 71 处直接准备 SQL。现有代码还依赖以下 SQLite 特性：

- `INSERT OR IGNORE`、`INSERT OR REPLACE` 和 `ON CONFLICT ... DO UPDATE`；
- `RETURNING`、`last_insert_rowid`、`AUTOINCREMENT` 和 `WITHOUT ROWID`；
- `PRAGMA`、`sqlite_master`、临时表、`rowid` 和连接级 `data_version`；
- `julianday`、SQLite 日期表达式和维护任务的批量删除；
- better-sqlite3 的同步事务、嵌套保存点和共享连接语义。

这些项目不能直接照搬到 MySQL。尤其是 SQLite 的 `INSERT OR REPLACE` 可能先删除旧行，不能机械替换为 MySQL 的 `REPLACE`，必须逐个确认外键、更新时间和奖励幂等语义。

## 实施顺序

### 1. 建立后端边界

新增统一的数据库会话和事务接口，业务领域只调用持久化命令，不再取得 better-sqlite3 连接。第一阶段仍由 SQLite 适配器实现，运行结果保持不变。

持久化上下文至少保留：

- 业务域和操作名；
- 玩家串行键；
- 请求幂等键；
- 事务提交、回滚、排队和失败状态；
- 关闭时 drain 语义。

### 2. 逐域迁移写入口

按以下顺序改造，并且每组都保持原有事务边界：

1. 账号、设备、会话和玩家基础资料；
2. 背包、角色、装备、体力和奖励；
3. 单人/多人结算、任务、活动和 Raid 账本；
4. 邮件、商城、抽卡和支付回执；
5. 排行榜、管理面板、维护任务和存档导入导出。

实时 TCP 只提交房间事件或持久化命令，不在 socket 回调内执行数据库读写。

### 3. 建立 MySQL 方言适配层

采用显式 SQL 和轻量驱动适配，不引入 ORM 重写现有领域逻辑。主要替换规则为：

| SQLite | MySQL 适配方向 |
| --- | --- |
| `INSERT OR IGNORE` | `INSERT IGNORE` 或明确的 `ON DUPLICATE KEY UPDATE` |
| `INSERT OR REPLACE` | 按业务改成显式更新/插入，禁止直接使用 `REPLACE` |
| `ON CONFLICT` | `ON DUPLICATE KEY UPDATE` |
| `RETURNING` | 使用 `LAST_INSERT_ID()` 或提交后查询 |
| `AUTOINCREMENT` | `AUTO_INCREMENT` |
| `WITHOUT ROWID` | 普通 InnoDB 表和明确主键 |
| `sqlite_master`、`PRAGMA` | `information_schema` 和后端能力接口 |
| 临时表、`data_version` | 持久化汇总表或进程内有版本号的缓存 |
| `julianday` | 明确的 `DATETIME`/UTC 边界比较 |

### 4. 数据迁移与校验

迁移工具必须在停服后执行，流程为：

1. 读取 SQLite schema 和数据字典，生成版本化 MySQL DDL；
2. 导出服务器账本、玩家数据和全局活动数据；
3. 导入 MySQL 临时库；
4. 对每张表比较行数、主键范围、玩家分组计数和关键账本摘要；
5. 随机抽取玩家验证存档、背包、任务、奖励、邮件和活动状态；
6. 通过完整回归后切换正式连接；
7. 保留原 SQLite 文件作为只读回滚基线，不进行双写。

切换到 MySQL 后产生新写入时，不能再把 SQLite 当作可自动回退的实时数据源。回滚必须在停服状态下完成，并明确以哪一个数据库为权威。

### 5. 运行部署

第一目标服务器可以使用 4 核 8GB，但需要给 MySQL 设置受控的连接池和内存上限，避免数据库吞掉 Node 的实时线程资源。迁移前必须完成压力测试；如果事件循环仍有明显长尾，优先升级到 6～8 核或将 MySQL 独立部署。

初期不固定连接池大小和缓冲池数值，以迁移库上的结算、登录、`/load`、多人房间和维护任务基准为准。凭据只放运行环境，不进入 Git、整合包或日志。

## 验收标准

- 所有正式写入口都经过统一持久化边界，没有遗漏的直接 SQLite 写入；
- 单人结算、多人结算、五重决战、奖励、任务、邮件、抽卡和支付回执在 SQLite/MySQL fixture 上结果一致；
- 重复请求、断线重连、进程重启和事务回滚不会重复发奖或丢失玩家进度；
- TCP 房间在数据库延迟升高时仍能维持心跳和广播，不在 socket 回调中同步等待数据库；
- MySQL 迁移后完成连续高负载观察，再决定是否删除 SQLite 运行依赖。

当前目标是完成第 1 阶段的后端边界和入口清单，尚未启用 MySQL、安装 MySQL 驱动或修改线上数据库。
