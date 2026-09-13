# 练习关崩溃后放弃恢复导致 H400

2026-09-13：用户最终要求先修复 H400，G1008 留待本地复现。本轮只交付服务端退出修复。

## 已确认根因

用户提供的 `cn-server-20260913-121913.stderr.log` 第 237–255 行中共有 12 次相同记录：

```text
[PRACTICE-HISTORY] invalid abort history payload: player=19 quest=1101 error=Cannot read properties of undefined (reading 'party')
```

对应 stdout 第 12791、13225 行分别在 13:17:28、13:18:45 上报
`single_battle_quest/abort` 的 HTTP 400，客户端显示 H400。

已登记 Android 公网 SWF 的 `QuestAbortRealRemote` 只在 `playStatistics=Some` 时发送
`statistics`；崩溃后从登录恢复流程放弃关卡时可以没有该字段。服务端原先却在记录练习历史时
无条件读取 `body.statistics.party`，捕获异常后立即返回 400，未执行随后删除未完成关卡的事务。
因此下一次登录继续返回同一 `unfinished_quest_list`，形成无法放弃关卡的循环。

这项缺陷覆盖所有练习关，并非只有新增 1101/1102。隔离测试已用原版 97 复现完全相同的异常。

## 最终修复

- `AbortBody.statistics` 与实际客户端协议一致，允许省略或 null。
- 身份匹配的练习退出没有统计时跳过历史写入，正常完成取消与未完成关卡清理。
- 提供了统计但数据无效时仍执行严格历史校验，跳过无效记录后允许退出；不伪造队伍、伤害或零分记录。
- 保留原类别、关卡和 play ID 一致性校验；不允许旧请求清除当前另一场练习。
- 保留正常退出记录、结束结算及事务。删除失败时不丢失未完成关卡，重试仍可完成。

运行文件仅为：

```text
src/routes/api/singleBattleQuest.ts
out/routes/api/singleBattleQuest.js
```

回归文件为 `tools/practice_abort_recovery.test.cjs`。本文件和待交付记录不需要部署到服务器。

## 验证

- 修改前复现：缺少 statistics 的退出返回 400，异常为读取 undefined.party。
- 新回归分别对 TypeScript 源码与构建后的 JS 执行：原版 97/87、新关 1101/1102，合计 16 种无统计或坏统计恢复场景，每轮另有 48 次错误身份请求保护检查。
- 真实 `/cn/load` 路由在取消前返回未完成关卡，取消后返回空列表；重复退出成功，不伪造历史，不改关卡完成进度。
- 人工制造数据库删除失败，验证 500 时事务回滚、内存及数据库保留当前关卡，解除失败后可重试退出。
- 既有 `practice_battle_history_abort`、`practice_battle_history_finish`、`practice_battle_history_route` 回归通过。
- `practice_high_hp.test.cjs` 通过：新旧关卡结算、10 分钟评价/大伤害记录、7 分钟退出、旧/新 V1/V2 HTTP 存档导入导出、导入前备份、无效输入不改写目标。
- 在独立构建目录执行 `npm run build` 成功；当前 `out/routes/api/singleBattleQuest.js` 与该构建字节一致。独立目录避免其他会话尚未提交的生成文件被覆盖。

存档影响：只在玩家主动退出且身份匹配时清理已有 `players_active_quests` 临时战斗状态。
没有新增表、列、存储 ID、奖励、账户变化或 V2 schemaFingerprint 变化；该表原本已按 reset 分类。
既有 V1/V2 兼容，无迁移、批量清档或真实玩家存档导入。

证据目录：`F:/codex/work/practice-g1008-h400-20260913/`，包括构建核对、源码/JS 回归日志和存档兼容报告。

## 交付状态与 G1008 边界

用户随后明确要求“提交，并给我云服整合包”，授权提交到 `staging`、推送、同步上述两个运行文件并制作云服包。
用户进一步确认“`.107` 已经覆盖了，别再加进来了”。云服包只含本次 H400 两个运行文件，
现有 `.107` 部署作为前置基础，不重复纳入此前 39 个文件。其他任务未提交的抽卡优化及其他本地修改保持原状。
本次没有授权云端部署或服务重启；修复需要覆盖文件并重启服务后生效，不把文件同步等同于运行中的进程已更新。
最终提交、运行镜像备份、文件哈希、整合包和 CI 状态记录于
`F:/codex/outputs/server-overlays/` 中本次 `practice-h400-107` 包旁的交付记录。

G1008 的截图时间已对上客户端状态效果调用栈，校园碧安卡延迟小龙引用是待复现线索，
尚未确认用户阵容的实际触发时序。本轮未修改任何有效客户端资源、CDN manifest、APK/IPA 或验收注册表。
未启用的资源候选和分析代码留在排查目录；用户要求的本地复现完成前不将其登记为已修复或交付。
