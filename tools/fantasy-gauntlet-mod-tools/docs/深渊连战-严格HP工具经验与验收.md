# 深渊连战严格 HP 工具：经验与验收边界

本文记录 `wf_rogue_build.py` 严格目标 HP 模式已经落实的工程约束，供后续维护、重 Roll、审计和发布复核使用。它不是某一座塔的发布记录，也不表示整塔已经通过真机实战。

## 1. 严格模式的契约

启用 `--strict-target-hp` 后，每个 Boss 关都必须同时满足：

- 按实际出现次数和胜利条件组件统计 HP；多 Boss、多阶段不能按 Boss code 去重。
- 每个计入胜利条件的组件都有绝对 HP 证据；不允许用等级、DPS 或同族经验值冒充绝对回读。
- `target_exempt=0`、最终 `proxy=0`、未归一关数为 0。
- 写入后按客户端公式重新读取基础总 HP 和诅咒后最终总 HP，并在明确的浮点容差内命中目标。
- 专用 Boss 的身份引用、阶段/波次、子单位和胜利条件闭包全部通过；无法证明时重抽，不带病保留。

严格模式采用 fail-closed：安全适配能力不足时排除或重抽该 Boss，不通过降低证据标准扩大入选范围。

## 2. HP 目标与落表通道

工具把“诅咒前基础目标”和“诅咒后最终目标”分开保存和验收：

1. 先按楼层曲线确定基础总 HP。
2. 多 Boss/多阶段按实际胜利组件和原生占比分配基础目标。
3. 只在基础目标之后应用本层 HP 诅咒倍率。
4. 构建结束从最终表按客户端公式独立回读两组总 HP，防止倍率重复应用。

已建立的主要适配通道包括：

- General Hit：克隆 `boss_level` 等级键并调整 Hit 通道。
- General Fix：根据 `boss_level.c5 × c6` 的绝对值语义写入和回读。
- Standard Boss：解析并克隆 Enemy DSL 的 T1 Health form。
- 多 Boss/混合族：逐出现次数建立组件，不按 code 合并。
- identity-locked：连同 `general_funnel.c32`、watch、BossAlive 等代号引用闭包一起处理。
- 专用 bundle：Orochi、Orochi EX、Conductor、CEO 和五类 Sphere 使用各自的阶段/子体适配与回读。

每层审计应列出 Boss、来源族、阶段组件、证据类型、原生 HP、基础目标/回读、最终目标/回读、落表通道、误差和诅咒。

## 3. Sphere 的真机教训

雷 Sphere 曾在第二阶段清空可见小怪后长期不再出现。离线引用链和 HP 总量均通过，说明“结构闭包”不能替代“运行时阶段行为”。根因风险来自阶段切换依赖的子单位伤害预算与浮点边界；HP 倍率会把原生阶段比例推到边界之外。

因此当前策略适用于 fire/water/thunder/wind/holy 全部五类 Sphere：

- 保留原生父体、阶段子单位、damage conduit 和胜利条件的完整关系。
- 对每个阶段预算做来源、目标、数量和比例回读。
- 禁止获得任何改变 HP 的诅咒，包括增加和降低 HP；不是只禁止“血肉高墙”。
- 严格模式缺少阶段行为闭包时直接重抽。

这些门禁能降低已知风险，但仍不能把 Sphere 标记为已真机通过；新版本至少要抽测一次完整退场、清怪、再入场和结算流程。

## 4. 诅咒随机策略

随机性必须服从 Boss 的安全能力：

- 能安全承受属性免疫/抗性诅咒的 Boss，优先扩大这类候选的实际出现机会。
- “火/水/雷/风/暗伤害降至 0.1%，只留光”已经覆盖五个元素时，不再叠加其他单元素诅咒。
- 单层最多选择一张元素类诅咒卡，避免重复或互相包含的描述。
- “血肉高墙”不得连续出现，最后六个 Boss 关最多出现两次。
- 无安全属性硬通道的专用 Boss 使用已证明不会破坏阶段/身份闭包的其他候选。
- Sphere 一律从候选中剔除全部 HP 诅咒，即使强制计划请求也应拒绝或替换。

## 5. 自动验收与真机边界

严格审计至少检查：

- Boss 关 absolute 覆盖数与预期一致。
- 未归一、最终 proxy、`target_exempt` 和解析链失败均为 0。
- 每个适配回执可从序列化审计数据独立重算。
- 基础目标/回读和诅咒后最终目标/回读分别在容差内。
- identity-locked、Orochi/Orochi EX、Sphere 等高风险族的引用和阶段闭包通过。
- 每个 Boss 关的 `quest c5` 封面都能回溯到实际 Boss 来源场地的官方任务大图，
  图片资源存在；混搭层不得误用地形 donor 的封面，也不得沿用模板旧图。
- 审计文件明确保存 `verification_scope=static_dry_run` 与 `gameplay_verified=false`。

`29/29 absolute` 只证明本次内存构建的 HP 与静态闭包满足契约；封面门禁也只证明
`Boss 来源场地 → 官方 quest 大图 → 客户端可见 PNG` 的数据链闭合。两者都不能证明
Boss AI、阶段时序、真机界面渲染或整塔结算已经通过。没有真机条件时必须一直保留
“未真机验证”标记。

封面历史事故包括：把 `floor.c2` 的 31×31 层内图标当成 240×188 任务大图、专用族
查不到来源时静默保留 Combat Diver 模板图、混搭层用地形 donor 而非 Boss donor 的图。
当前三类均纳入构建失败门禁；真机确认列表界面逐关一致前，报告只能写“封面静态来源
闭合、未真机验证”，不能写成玩法/界面绝对验证。

## 6. 推荐的安全工作流

仅调查或准备候选时使用内存 dry-run 和隔离输出目录，不写数据库、不更新正式版本链、不同步运行镜像、不执行发布脚本：

```powershell
python -X utf8 tools\fantasy-gauntlet-mod-tools\wf_rogue_build.py `
  --rounds 30 --seed <new-seed> --difficulty hell --enemy-level ramp `
  --strict-target-hp `
  --audit-json <isolated-work-dir>\hp-audit.json `
  --audit-report <isolated-work-dir>\hp-report.md

python -X utf8 tools\fantasy-gauntlet-mod-tools\wf_rogue_build.py `
  --verify-audit-json <isolated-work-dir>\hp-audit.json
```

发布前另做多种子 dry-run、相关单元/集成回归和至少一轮真机金丝雀。真机金丝雀应覆盖普通 Hit/Fix、Standard DSL、多阶段专用 Boss、Sphere 和最终结算；通过后才能把对应范围的 `gameplay_verified` 结论写入发布审计。

## 7. Git 与发布纪律

- Git 源真相是 `F:\codex\startpoint-cn-private-clean`；`F:\startpoint-cn-main` 只是运行镜像。
- 工具里程碑只提交工具、测试和本文档，不夹带生成塔、审计输出、补丁 ZIP、角色资源、manifest/changelog 或服务端状态。
- 共享脏工作树必须逐文件暂存，禁止 `git add .` 或 `git add -A`。
- 工具提交不等于发布；版本链、打包、部署与数据库写入必须由单独明确授权的流程执行。
