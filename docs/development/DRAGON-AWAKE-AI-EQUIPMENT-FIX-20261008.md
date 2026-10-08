# 光暗龙觉醒能力刷新与共斗 AI 幻想装备过滤

日期：2026-10-08。

状态：两项根因已定位并完成本地实现及自动验证。资源更新和服务端代码均未部署，
未进行 Android/iOS 真机下载或线上共斗验收。

## 问题一：光暗龙能力 4/5/6 偶发显示旧版

涉及角色：

- `151159` 拉夫马诺，称号“延续爱之龙”；
- `261089` 阿鲁玛德乌斯，称号“传承心愿的冥龙”。

### 根因

能力主表 `master/ability/ability.orderedmap` 是整表资源。`1.4.94` 的觉醒迁移已经为
两名角色能力 4、5、6 同时写入：

- `awake_kind=1, awake_level=0` 的未觉醒旧版行；
- `awake_kind=1, awake_level=1` 的觉醒新版替换行。

当前终态中六个键仍与 `1.4.94` 已批准行逐字节一致：

| 角色 | 能力键 | 未觉醒行 | 觉醒替换行 |
| --- | --- | ---: | ---: |
| 拉夫马诺 | `1511594` | 1 | 1 |
| 拉夫马诺 | `1511595` | 1 | 1 |
| 拉夫马诺 | `1511596` | 1 | 2 |
| 阿鲁玛德乌斯 | `2610894` | 1 | 1 |
| 阿鲁玛德乌斯 | `2610895` | 1 | 1 |
| 阿鲁玛德乌斯 | `2610896` | 1 | 2 |

因此不是玩家存档的觉醒等级写错，也不是后续资源把这六项回退。部分客户端在同一资源
版本已经上报完成后仍持有旧整表；同版本内替换或增加包不会让这些客户端自动补拉。
玩家手工重新获取资源能恢复，正是因为重新下载覆盖了旧能力表，但不应长期要求玩家
自行清缓存。

### 修复

新增确定性生成器：

`tools/fantasy-gauntlet-mod-tools/publish_dragon_awake_ability_refresh_1_4_135.py`

生成新的资源版本边：

```text
1.4.134 -> 1.4.135
pinball-1.4.134-1.4.135-1-dragon-awake-ability-refresh-20261008.zip
```

包内只有当前终态的一个成员：

```text
production/upload/1e/664c1cc8d80f4f9a69aae2c49ae8c01d1c4001
```

对应 `ability.orderedmap` 原始载荷 SHA-256：

```text
413129be259ad4c3686489649ed6c4bbc143c722f595e126b9cbccec9dcfca74
```

ZIP SHA-256：

```text
05c76f648e4f7f5e4e09f5b58f113e60015e143b0d1b9443a80499baf214abf8
```

该包不修改能力数值，只通过新版本号让 `.134` 客户端自动重新下载当前整表。
Android 与 iOS 共用这张 common 主表。`.135` 客户端返回无更新。

详细回读证据：

- `assets/asset-patch/audit/dragon-awake-ability-refresh-1.4.135/report.json`
- `assets/asset-patch/audit/dragon-awake-ability-refresh-1.4.135/manifest-entry.json`

同步最新 `staging` 后，资源链已由凉月与活动收尾推进到 `.134`，且凉月 `.131` 包内
包含更新后的整张能力表。旧方案若继续在 `.130 -> .131` 以序号 2 重发较早整表，
会覆盖凉月等新角色能力。因此刷新包重锚到链尾 `.134 -> .135`，并直接复用凉月之后
的最新能力整表；`.131-.134` 的资源内容不会被回退。

## 问题二：普通共斗 AI 携带幻想装备

### 根因

当前 `staging` 的 AI 队伍可能来自：

1. 固定 `NPC_TEMPLATES`；
2. 某关历史通关队伍快照；
3. 普通 SET 的 TTL 缓存池；
4. 随机池为空时复制房主当前队伍；
5. 同一房间自动续战保存的 `npc_party_by_com_id`。

旧流程会把这些来源的武器、魂珠原样发布到大厅。真人队伍已有开战边界检查，但
AI 是服务端生成状态，不经过真人准备检查，因此 `100013..100023` 可以出现在非幻想
共斗房。

PR #24 分支中曾实现过 AI 发布前卸下违规装备，但该 PR 尚未进入 `staging`，当前基线
没有这项保护。本次按“违规 AI 不应进入房间”的规则改为整队准入过滤，不依赖 PR #24
的整套准备/超时逻辑。

### 修复

新增 `src/multi/npc/equipment-policy.ts`，在以下边界统一执行整队准入判断：

- 固定 AI 模板构建；
- 历史通关快照和普通 SET 候选池选择；
- 大厅最终选择 AI 队伍并写入房间缓存之前；
- 自动续战复用旧房间缓存之前。

支持以下队伍字段和编码：

- `equipments`、`equipmentIds`、`equipment_ids`；
- `abilitySoulIds`、`ability_soul_ids`；
- TCP Option `[0, value]` / `[1]`；
- 普通对象及纯 ID 数组。

非幻想房命中 `100013..100023` 时，整支 AI 队伍淘汰，不通过卸下装备后继续使用：

- 候选池继续寻找下一支完整合法队伍；
- 随机池无合法队伍时，合法房主队伍仍可作为兼容兜底；违规房主队伍不会复制，
  改用合法固定模板；
- 固定模板自身违规时也整队拒绝；
- 所有候选均不合法时宁可少补一个 AI，也不让违规 AI 进入房间；
- 不修改来源玩家 SET、库存、存档或任何候选队伍内容；
- 已缓存的违规 AI 在自动续战回房时作废并重新选择；
- 幻想 5/10/15 层 `300098001/2/3` 保持幻想装备，不做清理；
- Mode15 可选模块缺失时仍使用固定 ID 范围兜底，不因配置差异失效。

## 验证

资源生成与内容检查：

```bash
python3 -B tools/fantasy-gauntlet-mod-tools/publish_dragon_awake_ability_refresh_1_4_135.py
env PYTHONPATH=tools/fantasy-gauntlet-mod-tools python3 -B -m unittest \
  tools/fantasy-gauntlet-mod-tools/tests/test_dragon_awake_ability_refresh.py -v
```

结果：生成器 dry-run 通过，Python 精确检查 4/4 通过。验证 ZIP 确定性、终态整表
SHA-256、六个目标能力行、与 `1.4.94` 觉醒版本一致，以及数值未变化。

资源下载路由：

```bash
node tools/run-isolated-check.cjs --test \
  tests/dragon-awake-ability-refresh.test.cjs \
  tests/asset-manifest-publication.test.cjs
```

结果：资源专项 4/4、manifest 发布边界 2/2。Android/iOS `.134` 均只取得已登记的
`.135` 刷新包，下载字节和 SHA-256 匹配；`.135` 不重复下载；未登记同边 ZIP 不发布。

AI 与多人：

```bash
node tools/run-isolated-check.cjs --test \
  tests/npc-fantasy-equipment-filter.test.cjs \
  tests/five-boss-integration.test.js
```

最终严格准入版本结果：AI 编码/白名单专项 8/8，五重及多人集成 55/55。覆盖固定模板
整队拒绝、历史池过滤、房主违规兜底不复制、旧续战缓存作废重选、候选来源不变和
幻想三节点放行。另用真实 SQLite 普通 SET 候选池验证：普通房拒绝违规整队、幻想房
允许同一整队、有合法备选时普通房只返回合法整队。

测试只在项目隔离目录运行并自动删除。没有启动真实游戏服务，没有修改玩家数据库，
没有生成 APK/IPA/SWF，也没有操作玩家设备缓存。

候选池真实数据库测试首次断言 3/3 通过后进程未退出，定位为导入链加载的房间清理
`setInterval` 未调用 `unref()`。已将该后台清理计时器设为非进程所有者：服务运行时
仍会正常触发，独立测试和工具在无其他句柄时可正常退出。随后重新编译并重跑验证。

首次资源测试因引用仓库未安装的 `jszip` 失败；随后改用项目已有 `unzipper` 并重跑
通过。这是测试依赖错误，不是资源包内容错误，未新增依赖。

## 部署与回退

部署需要同时更新：

- `assets/asset-patch/manifest.json`；
- `.135` 资源 ZIP；
- AI 过滤相关 `src` 与受版本控制的 `out`；
- 新增 AI 运行模块 `out/multi/npc/equipment-policy.js`。

更新后需要重启服务端，使新代码和 manifest 生效。玩家无需重新安装客户端；
从 `.134` 进入时会下载约 191 KiB 的能力表刷新包。已是错误同版本 `.135` 的测试设备
仍不会重复拉取，需要先确认其资源版本来源后单独处理，不能通过同版本换包解决。

回退服务端代码需恢复上一完整版本并重启。资源版本一旦正式投放，不应仅删除 `.135`
包或把 manifest 静默退回 `.134`，否则已上报 `.135` 的客户端会形成断链；应发布新的
前向修复版本。

当前随独立修复 PR 提交评审，尚未部署或真机验收；PR 目标为 `staging`，
不启用自动合并，不直接合并到 `main`。
