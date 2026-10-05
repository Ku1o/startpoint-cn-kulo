# 服务器固定四小时日志

日期：2026-10-05

实现基线：`staging@3995738e`。本轮仅调整日志收集与启动入口，不修改游戏逻辑、
数据库、客户端、日志级别或已有性能摘要频率。

## 原因

- Windows `start-cn-logged.ps1` 原先按启动时间分别创建 stdout/stderr 文件；运行
  多久就写多久，没有时间轮转。
- 调试模式也按启动时间创建文件。
- Linux/macOS `start-cn.sh` 原先固定写 `.logs/cn-server.log`，下次启动会覆盖。

因此旧文件的覆盖时长取决于服务进程寿命，不是固定四小时。

## 新规则

使用真实北京时间 UTC+08:00，每天固定六个半开时段：

| 时段 | 文件示例 |
|---|---|
| 00:00 至 04:00 | `.logs/cn-server-20261005-0000.log` |
| 04:00 至 08:00 | `.logs/cn-server-20261005-0400.log` |
| 08:00 至 12:00 | `.logs/cn-server-20261005-0800.log` |
| 12:00 至 16:00 | `.logs/cn-server-20261005-1200.log` |
| 16:00 至 20:00 | `.logs/cn-server-20261005-1600.log` |
| 20:00 至次日 00:00 | `.logs/cn-server-20261005-2000.log` |

同一时段 stdout 和 stderr 合并为一个 UTF-8 文件，每行附带收集时的 ISO UTC 时间
和来源标记 `[stdout]` 或 `[stderr]`。文件名使用北京时间，行内 `Z` 时间为 UTC。
不使用游戏活动虚拟时间；两条输出管道按收集器收到的顺序合并，不声称还原跨管道的
严格发生先后。

四小时是固定日历窗口，不是每次启动后重新计时。如果 02:30 启动，首文件只覆盖
02:30 至 04:00；该时段再次重启继续追加，不覆盖已有内容。首个文件在启动时打开，
后续时段在有新日志时切换，不为停服或全程无输出的时段补造空日志。
没有按文件大小二次切分。系统真实时间回调时，日志追加到其所属窗口。

调试模式使用 `cn-server-debug-YYYYMMDD-HH00.log`，独立于生产文件；同样四小时切换。
专用 `multi-chain-*.jsonl` 等诊断文件保持原规则，不合并。

## 实现与入口

新增 `scripts/run-cn-logged.cjs`，使用当前 Node 可执行文件启动 `out/cn-server.js`，
在独立收集进程中读取两条管道、按行标注并异步批量写入文件。

- `start-cn-production.bat`：原入口不变，经 PowerShell 使用收集器，仍保留 7 天。
- `start-cn-logged.bat`：仍保留 30 天，支持 PowerShell 原有 `RetentionDays` 参数。
- `start-cn-debug.bat`：仍保留 3 天，同时把输出显示到控制台。
- `bash scripts/start-cn.sh`：构建后使用收集器后台启动，保留 30 天。
- `start-cn-console.bat`、`npm run dev:cn`、tmux 及直接执行游戏 JS 的方式不自动
  新增文件日志，需要日志时使用上述入口或下面的直接命令。

直接运行（已构建服务端）：

```bash
node --env-file=.env scripts/run-cn-logged.cjs
node --env-file=.env scripts/run-cn-logged.cjs --console --retention-days 7
node --env-file=.env scripts/run-cn-logged.cjs --debug --console --retention-days 3
```

收集器自身为 CommonJS，无新增依赖，不需要 TypeScript 编译产物。
部署启动脚本时必须一同部署 `scripts/run-cn-logged.cjs`。

## 生命周期与兼容

- 切换文件不重启游戏进程，不关闭共斗连接。
- `.logs/cn-server-current.json` 的 `pid` 仍是实际游戏 PID；新增 `loggerPid`。
- `stdout` 和 `stderr` 兼容字段都指向当前合并日志，同时增加 `log`、时段和时区。
- 维护脚本仍按游戏 PID、启动时间、进程命令和项目日志目录验证所有权。
- Windows 启动脚本只接受本次 logger PID 对应的回执，避免误读上次运行状态。
- 回执是“进程已启动”，不等价于 HTTP/TCP 就绪；就绪仍由原
  `.logs/cn-server-ready.json` 表达。
- 正常退出等待两条管道读完，再关闭文件；转发 SIGINT/SIGTERM，等待超时后终止子进程。
- 文件写入失败会报告错误并停止本次子进程，返回非零退出码，避免悄悄丢日志。
  这不是自动重启管理器；磁盘满或目录无权限需要运维处理。
- Windows 强制终止/关闭窗口、断电不保证最后的管道缓冲全部落盘。
- 不要单独强制杀收集器而留下游戏子进程；Windows 日常停服仍使用维护脚本识别的游戏 PID。

旧日志不重新切分；普通模式在启动及跨窗口写入时清理超过保留期、匹配旧/新命名的
日志文件，调试模式仅清理自己的文件。当前写入文件、其他诊断文件、目录和符号链接
不在删除范围。旧 Linux 固定 `cn-server.log` 不自动删除。

## CPU 与内存边界

- 游戏主线程不做逐行格式化、保留期扫描或文件切换。
- 同一管道数据块中的短行批量写入；不为每行独立开关文件或扫描目录。
- 管道遵守回压；缓慢磁盘不会在收集器中无限堆积日志。
- 无换行的长输出按最多 64 Ki 字符分片，保留跨块 UTF-8 和代理对字符。
- 极端磁盘拥塞仍可能让游戏 stdout 缓冲积压，不能承诺日志永远不影响性能。
- 新增一个轻量 Node 进程，不是把游戏改为多进程运行。

## 分析工具

`tools/analyze-runtime-log.cjs` 同时接受旧双文件和新合并文件；只移除本收集器的明确
前缀，不改动 JSON 内容。内存分析工具原本就支持标记前缀，不需要改实现。

```bash
node tools/analyze-runtime-log.cjs .logs/cn-server-20261005-0000.log
node tools/analyze-memory-log.cjs --json .logs/cn-server-20261005-0000.log
```

## 验证与回滚

```bash
npm run test:server-logs
npm run typecheck
bash -n scripts/start-cn.sh
git diff --check
```

专项覆盖固定时段、整点、跨天、重启追加、空闲跳段、中文跨块、stderr 合并、超长行、
批量写入、新日志分析、保留期、真实子进程 PID/退出码、尾部日志、写失败和信号退出，
以及旧收集器退出前回执已被新启动替换时保留新回执。
时间轮转通过注入时钟重现，不需要真实等待四小时。

本地结果：日志专项 12/12、已有内存日志分析回归 6/6，合计 18/18 通过；
TypeScript 类型检查、Shell 语法检查和 `git diff --check` 均通过。
测试临时目录已删除，未发现残留收集器或测试游戏进程。

所有测试只使用项目 `tmp/` 中的独立目录及无游戏依赖的子进程，退出后删除。
当前 Mac 没有 PowerShell，Windows 脚本仅做静态断言，未在 Windows 云服实跑；
Linux/macOS 启动脚本仅做语法检查，未调用会终止旧服务的真实启动命令。
上线后仍需验证 Windows 启动、维护停服以及跨 04:00/08:00 边界的实际日志。

回滚时同时恢复三个启动脚本，之后按原方式重启。已有四小时日志保留，不改写数据库，
不需要逆迁移。当前未提交、推送、创建 PR 或部署云服。
