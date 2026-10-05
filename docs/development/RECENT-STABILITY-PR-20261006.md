# 近期运行稳定性改进交付汇总

日期：2026-10-06。基线：`staging@3995738e`。

本次按用户要求，将最近几轮“日志可观测性与共斗准备稳定性”工作整理为一个 PR。
此前已进入 staging 的五重掉线、准入等级、幻想进度保留等修复不重复计为新增。
本次只提交和发起评审，不合并 main/staging，不部署或重启真实游戏服务。

## 范围与完成状态

| 项目 | 本次交付 | 状态 |
| --- | --- | --- |
| 固定四小时日志 | 独立收集器、启动入口适配、分析工具兼容及回归测试 | 已实现，本地验证通过 |
| 幻想装备准备保护 | 房内准备检查、超时移出/解散、倒计时及 HTTP/TCP 竞态保护、AI 配装过滤 | 已实现，本地验证通过，待真机验收 |
| 深渊逐层队伍自行变化 | 分析 SET 引用、本机选择记忆和本轮续战计划的差异 | 仅排查，未新增同步或修复 |
| 瞬时技能充能卡死 | 定位白梅斩铁与天穹无坠之翼的双向反馈，提供只读词条检查工具 | 仅排查，未改词条或客户端，未认定卡死已修复 |

## 已完成改进

### 日志轮转

- 按真实北京时间 00/04/08/12/16/20 点划分固定四小时窗口，合并 stdout/stderr。
- 同时段重启追加，跨窗口不重启游戏进程，旧日志不重新切分。
- 独立 Node 收集器异步批量写入，长行有界分片，保持 UTF-8，遵守回压。
- 保持生产 7 天、普通日志 30 天、调试 3 天的保留策略。
- 回执区分实际游戏 PID 和收集器 PID，避免旧进程退出覆盖新回执。
- Windows PowerShell 和 Shell 启动入口接入；分析工具兼容旧双文件与新合并文件。

详细行为、命令及维护边界见
[四小时日志说明](SERVER-FOUR-HOUR-LOGS-20261005.md)。

### 共斗准备与倒计时

- 不因装备拒绝入房，允许玩家在房内更换编队；只检查当前选中队伍。
- 非幻想副本携带幻想武器或魂珠时，手动/自动/强制准备均回退为未准备，
  不弹装备提示，不立即解散整房。
- 同时校验数据库 SET 与大厅上传配装，覆盖房主自动准备、倒计时、TCP/HTTP 开战、
  编队保存及自动续战换队。
- 违规队友被拦截后连续 30 秒无有效改动，仅移出该队友；违规房主同样超时则解散
  整房。房主合法而被队友阻挡时，不启动房主装备解散计时。
- 实际主动修改当前队伍可刷新期限，合法修正取消期限；心跳、重复准备/开战、
  相同内容、其他 SET 修改和自动换队不会刷期限。
- 已发出的倒计时不能越过再次校验；本轮已批准的选队在开战后冻结，回房重新检查。
- 计时器受房间实例、代次和连接身份约束，旧连接/旧房间回调不能处理新一轮。
- 非幻想房间发布 AI 队伍前移除 AI 自身的幻想装备引用，不改玩家库存或保存编队。
- 正常队伍没有准备操作不触发新增 30 秒装备超时；幻想共斗 5/10/15 层
  `300098001/300098002/300098003` 继续允许幻想装备与魂珠。

详细实现和测试见
[幻想装备共斗准备保护](MULTI-EQUIPMENT-READY-GATE-20261005.md)。

## 尚未实施的内容

- 深渊逐层队伍预设没有新增持久化或跨设备同步。当前本地选择记录与共享 SET 引用
  可能解释部分变化，但缺少反馈玩家的具体复现。
  见[深渊续战队伍排查](ABYSS-AUTOSTART-PARTY-INVESTIGATION-20261006.md)。
- 白梅斩铁主位、满足六光编成时“充能转连击”，与浮游时天穹“每 30 连击全队充能”
  存在无配置冷却的反馈关系。已经回读本地资源，但还没有当前累计客户端真机复现；
  不把数据规则检查说成卡死修复。未新增冷却、充能上限、组合禁用或丢包处理。
  见[技能充能卡死排查](SKILL-GAUGE-FREEZE-INVESTIGATION-20261006.md)。
- 客户端约 60 秒强制准备计时没有被服务端暂停或重置；旧客户端强制准备后的
  换队按钮可能仍受本地状态限制。
- 玩家已被装备规则拦截后，只浏览编队编辑界面但未产生服务端可观察改动，
  30 秒仍继续计算。“编辑宽限”仅讨论，未实现。

## 2026-10-06 提交前复验

实际执行顺序为先类型检查和编译，再分别运行项目既有隔离运行器。
下列命令对应本次执行；多核文件列表与 `package.json` 的 `test:multicore` 一致。

```bash
node node_modules/typescript/bin/tsc --noEmit
node node_modules/typescript/bin/tsc
node tools/run-multiplayer-connectivity-check.cjs
node tools/run-isolated-check.cjs --test tests/multicore-snapshot.test.cjs tests/server-response-workers.test.cjs tests/cn-load-worker-integration.test.cjs tests/sqlite-checkpoint-worker.test.cjs tests/sqlite-persistence-worker.test.cjs tests/sqlite-writer-thread.test.cjs tests/sqlite-writer-inprocess.test.cjs tests/single-finish-writer-thread.test.cjs tests/tcp-server-lifecycle.test.cjs tests/server-diagnostics-modes.test.cjs tests/request-diagnostics.test.cjs tests/mission-performance-safety.test.cjs tests/character-awake-query-scope.test.js tests/gacha-exec-preservation.test.js tests/gacha-exchange-consistency.test.cjs tests/player-login-integration.test.js
node tools/run-isolated-check.cjs --test tests/server-log-rotation.test.cjs tests/memory-log-analysis.test.cjs tests/hygiene-license.test.cjs
env PYTHONPATH=tools/fantasy-gauntlet-mod-tools python3 -B -m unittest discover -s tools/fantasy-gauntlet-mod-tools/tests -p test_combo_gauge_feedback_audit.py -v
bash -n scripts/start-cn.sh
```

结果：

- 类型检查及 TypeScript 编译通过，本次未重建无改动的管理页面 CSS。
- 完整多人套件通过；其中准备与超时 28/28、HTTP/SQLite 3/3、编队保存 4/4、
  五重集成 53/53、屏障与重连 24/24。
- 完整多核套件通过；两项既有条件跳过：未提供旧编码器对照源、非 Windows 原生
  内存探针环境。未新增多核架构改造，不用这些结果宣称本轮有 CPU 百分比收益。
- 四小时日志 12/12、内存日志分析 6/6、许可证卫生检查回归通过。
- 只读反馈词条检查 5/5，Shell 语法通过。
- 隔离运行器结束时删除各自测试目录；没有写入真实玩家数据库。
- `node tools/check-out-artifacts.cjs` 暂存检查通过，相关运行产物均已纳入。
- `bash scripts/check-hygiene.sh --all` 全树卫生扫描及
  `git diff --cached --check` 通过。
- 检查了 7 份改动文档中的 60 个相对链接，全部存在；项目 `tmp/` 已移除，
  未发现隔离测试运行器、收集器或测试子进程残留。

没有执行 Windows 云服真实启动/维护停服、真实四小时运行、客户端编队/强制准备
真机验收、深渊变化复现或技能充能卡死真机验收。时间边界和 30 秒超时使用模拟时钟；
Python 检查使用 `-B`，不生成字节码缓存。旧记录中的“未提交/未创建 PR”
描述各自记录时点，本汇总及实际 PR 承接后续交付状态。

## 兼容性与回退

- 无数据库结构、存档格式、库存、奖励来源、五重门票或玩家等级门槛变更；
  不迁移数据库，不清理玩家 SET。
- 无 CDN ZIP/manifest、准入号或 APK/IPA/SWF 变更；幻想原白名单保持。
- 服务端源码与受版本控制的 `out` 一起交付，新增准备模块及 coordinator 产物
  必须纳入，不能只更新 TypeScript。
- 经评审批准部署时，在维护窗口更新完整服务端并重启，使房间内存状态一致；
  四小时日志入口须同时携带新收集脚本。
- 回退使用上一完整服务端版本与配套启动脚本，在维护窗口重启；已有日志保留，
  不需要数据库逆迁移。回退也会恢复旧版本装备开战检查行为。
- 日志目录不可写或磁盘满时，收集器会停止其游戏子进程并报错；
  仍需部署后的磁盘监控与进程管理，不能把日志轮转当作自动重启机制。

## PR 交付

- GitHub 发起身份及 Git 提交身份：`reeee3ky`，Git 使用对应 GitHub 隐私邮箱。
- 工作分支：`fix/four-hour-server-logs`；目标分支：`staging`。
- 只推送该临时分支并请求评审，不启用自动合并，不合并或直接推送长期分支。
