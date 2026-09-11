# 深渊详情与奖励预览测试客户端

2026-09-10，用户同意试做“顶部短摘要 + 关卡详情弹窗”。这是本地测试候选，未提升 Android 验收登记。

## 行为

- 700099 深渊关卡的列表与编队页显示封锁属性和额外 PF 调整。
- 编队页“不可续战”右侧新增“关卡详情”。使用现有 ButtonGroup 与 RichTextDialog，按属性伤害、敌人与血量、诅咒、额外领域分段显示，沿用原生滚动和关闭逻辑。
- 只转换展示文本，不修改 `QuestValues.sub_name` 或战斗条件。完整属性伤害配置仍由原有 `cn.rules.QuestElementResistance` 读取。
- 资源 1.4.109 修正通关固定奖励预览：梦境纹章 1000、深渊代币 100、★4 破星结晶 2、★4 星铁钢 2。实际发奖及随机追加奖励不变。
- `wf_rogue_build.build_deep_abyss_folder_leaf` 接收服务端固定奖励列表，取消旧硬编码；生成器读取同一份服务端配置。
- `wf_rogue_build.py` 会从当前有效塔的详情标记自动沿用详情功能，普通重 roll 不再需要重复加参数；`--details-ui` 只用于首次开启。每层说明从本次最终 HP 审计重新生成，不复制旧敌人或旧血量。其他后处理若改变敌人或 HP，须在其完成后通过 `wf_abyss_quest_details.with_details` 更新说明，避免旧血量残留。纯展示数据更新不需要再次修改 APK。

## 累计输入和方法范围

输入是已验收深渊续战 Lens 内网基线的属性封锁通道后继包：
`outputs/quest-element-channel-lan-test-20260910/StarPoint-CN-1.8.1-quest-element-channel-lan-test-20260910.apk`。

- 输入 APK SHA-256：`8e21b793091415be13d13ac170a1dc53e89fb92a3d688c135deb86644a71bbcb`
- 输入 SWF SHA-256：`70ae68d0b5ca59650e3a41468b81fd00d6ce1d2861eebb5fb66d90b61b0da653`
- 输入 AIR UUID：`51e09b50-f15c-431f-9359-c9a55caf209f`
- 仅在主 ABC 的 71835（QuestTranslator.translateFormattedQuestNumber）和 78350（PartySelectTopPanelView.baseRun）插入展示调用。
- 新增独立 `cn.ui.AbyssDetails` ABC（13 个方法体），原主 ABC 从 285 移到 286。原属性封锁 helper ABC 保持逐字节一致。
- 两个目标方法均通过插入逆变换恢复全部原指令和分支；其余 96407 个既有方法体不变。独立 FFDec 再比较全部 96409 个输入方法体。

## 复现与校验

工作目录：`F:/codex/work/abyss-detail-ui-20260910`。构建器从源码编译独立 helper，不重编译游戏原生类；FFDec 只导出三个目标类，所有子进程均有超时及进程树清理。普通重 roll 只运行 Python 数据生成与校验，不启动桌面 AIR。

默认构建只做静态校验，或复用输入哈希完全一致的既有 AIR 回执，不启动图形程序。只有显式加 `--run-air-tests` 才运行桌面 AIR；它可能显示 HARMAN 启动画面，隐藏测试主窗口不能保证隐藏运行器自己的启动画面。调用前应说明这一点，集中运行必要检查。

```powershell
python -X utf8 -B client-patch/abyss-detail-ui/build.py --work F:/codex/work/abyss-detail-ui-20260910 --fixtures F:/codex/work/abyss-detail-ui-20260910/resources/floor-fixtures.json
# 只有需要新增桌面运行验证时才显式运行：
python -X utf8 -B client-patch/abyss-detail-ui/build.py --work F:/codex/work/abyss-detail-ui-20260910 --fixtures F:/codex/work/abyss-detail-ui-20260910/resources/floor-fixtures.json --run-air-tests
python -X utf8 -B client-patch/abyss-detail-ui/package_apk.py --work F:/codex/work/abyss-detail-ui-20260910 --out outputs/abyss-detail-ui-lan-test-20260910
```

回执绑定最终 SWF、helper 源码、测试代码、描述文件、关卡样本和测试驱动的 SHA-256。输入变化、失败重跑或结果被改动都会使旧回执失效。跳过的检查会明确记录 `not_run`，不会当作运行验证通过；打包器要求匹配回执。此前已交付成品的验证报告保持历史记录，不为补回执重新运行或重签。

打包必须使用新输出目录，每次 SWF 构建使用新的 AIR UUID；签名调用现有 DPAPI 保护的签名流程。验证包名、版本、签名、对齐、嵌入 SWF 和所有其他 APK 成员。

桌面 AIR 测试只移除测试 SWF 的根文档绑定，避免启动游戏或访问玩家账户；原生类与 helper 仍来自最终 SWF。测试环境单独初始化 Starling 和正常启动时创建的 Gear 池，实际交付 SWF 不含这些测试改动。

已通过 223 项桌面 AIR 检查：全塔 30 层原生富文本解析、战斗配置不变、其他活动不变、最多五属性的摘要、原生 Sprite/Quad/UiText 按钮、原生详情对话框、重复注册和点击后读取当前关卡。场景对象与按钮组分发在该测试中使用替身；这不代表已经跑通手机上的场景生命周期、触控滚动或 GPU 渲染。

最终 APK：`outputs/abyss-detail-ui-lan-test-20260910/StarPoint-CN-1.8.1-abyss-details-lan-test-20260910.apk`。
APK SHA-256：`eb1edaaae48027362970fb94b3a71da8fa3282ec47f6196a49490b56d9a4c61c`。
SWF SHA-256：`355d4b5e1ff41f874c7f32f9ec45542a7cce8469c740497949c1dc0b3c6faa55`。
AIR UUID：`2bf1476e-2fe3-43b0-bba3-b199415c0128`。

## 本地资源同步

资源审计：`assets/asset-patch/audit/abyss-details-rewards-1.4.109-test/`。
只向 `F:/startpoint-cn-main` 同步以下 4 个路径，备份后最后原子替换 manifest：

- `assets/asset-patch/active/pinball-1.4.108-1.4.109-1-abyss-details-rewards-test.zip`
- `assets/asset-patch/production/upload/b6/595dedd9cfa79b7e6eccab25dd9a2a81b066a2`
- `assets/asset-patch/production/upload/e6/e407d1adb48131eaefdf5ec32208f3d4f46910`
- `assets/asset-patch/manifest.json`

备份：`F:/startpoint-cn-main/.codex-backups/20260910-174153-abyss-details-rewards`。
补丁 SHA-256：`f35bfe5851da534929420d5110d7907a0d1fee7eb70d1c2980ff85d16e7dfe78`。

5 项 Python 回归、31 项事件链检查、303 项有效资源、301 个本地散文件覆盖、6 种更新请求与 ZIP/两张表的实际 HTTP 下载均通过。服务端公共奖励 accessor 与客户端预览一致；没有改发奖配置或玩家数据。26/30 换层、不出额外雷抗、15 层 PF 调整、缺失资源及机兵修复、称号和莱特兑换均保持。

当前分支 `staging`，HEAD `8f6252bb31c7f18a8cb61f11fa699282e68ebc4b`，记录的上游相同。本次为授权的未提交本地测试增量，未提交、未推送、未合并 main；未制作云端覆盖整合包或部署云端。源仓库暂缓资源链、已有其他修改和 IPA 均保留。

## 后续工具修正：自动沿用详情，减少 AIR 启动

用户反馈应防止下一次重 roll 再次回退，并询问反复出现的 HARMAN 启动画面。

已修正生成器自动沿用详情功能，保留从服务端配置生成奖励预览的规则；每次重 roll 重新填写新敌人和最终 HP。桌面 AIR 测试改为显式 `--run-air-tests`，默认只做静态检查或复用严格匹配的回执，失败或失效的旧回执不能用于打包。

13 项 Python 回归及当前有效 1.4.109 的 30 层说明回放通过；奖励预览重新序列化后与当前表完全一致。本轮没有启动 AIR、重 roll、重新打包或改动服务端文件，已交付 APK 和资源版本保持。工具流程检查不代表新增手机验证。

检查记录：`F:/codex/work/abyss-tool-air-workflow-20260910/verification.json`，修改前源码快照位于同目录 `before/`。仍为 `staging@8f6252bb31c7f18a8cb61f11fa699282e68ebc4b`，未提交或推送；没有新运行目录备份或云端覆盖包，因为本轮只修改本地开发工具。其他用户修改保持。
