# 竞速池四名玩家角色：第一轮削弱交接

用户已确认按调查报告的第一轮方案实施，并要求本任务完成、且“审阅更新包并制定融合方案”原任务完成后，将内容转交它制作新的增量更新。

当前状态：**本地规则、候选资源与静态验证已完成，尚未挂入发布链或同步运行镜像。**
2026-09-08 生成时源链尾为 `1.4.106`。由接收任务在其原工作完成后，将本规则应用到届时最新有效链尾再制作顺序增量，不能直接覆盖整合过程中产生的新主表。

## 已实施数值

下表均为满级百分比。角色均来自竞速池 `990002`，不涉及同名敌方 Boss。

| 角色 | 第一轮调整 |
|---|---|
| 水灵幽魂 `129998` | 能力 2 每层自身攻击/技伤各 60→40、PF 45→30；每层水队攻击/技伤各 25→15、直击 20→12；自身直击独立项每层 10→6。能力 4 主位开技回充 50→30，有怨念时直击回充 4→2。 |
| 红蝮蛇 `119993` | 能力 1 每减益攻击型/直击型各 20→15；能力 3 攻击型 25→17.5、直击型 17.5→12.5；能力 5 一般条件伤害每计数 5→3.5；队长每减益攻击型 35→25、直击型 45→30。 |
| 风暴恶魔拉比 `149994` | 能力 3 直击回充 6→3，副位风队直击 100→60；能力 4 主位开技回充 40→25；能力 6 副位风队攻击/技伤各 100→60。 |
| 机枪魔块·雷 `139996` | 能力 4 开局自身充能 100 及开技回充两行加入主位条件，回充 40→25；能力 2 雷队锁定攻击型/一般/技能型 60/20/40→40/15/25，机械锁定攻击型 40→25；队长锁定攻击型 60→40。 |

最低等级端点按原比例同步缩放，精度为原表整数单位（1 单位 = 0.001 个百分点），四舍五入。红蝮蛇队长两项最低端点分别为 `17.857%` 和 `23.333%`；满级严格为 `25%` 和 `30%`。

共 28 行、56 个单元格：普通能力表 10 个键/25 行/50 格；队长表 2 个键/3 行/6 格。进化前后共享这组能力键，主动技两形态、技能能量、PF/EX 攻击程序、状态及层数上限均沿用当前内容。技能回充仍延迟 2 秒，直击回充仍冷却 60 帧。

机枪魔块主位限制使用能力行 c6 的 `OwnerIsMain` 前置条件 `0→202`，与水灵幽魂、拉比的现有实现一致，只作用于能力 4 的第 0、2 行。未将整个能力 4 改成主位专用，因此充能速度和槽上限词条仍可副位使用；能力 1 的开局 50% 也保留。字段映射和反编译 `AbilityPreconditionMasterValueTools.as` 均确认 `202→Initial(OwnerIsMain)`、`203→Initial(OwnerIsUnison)`。

## 源文件与调用方式

- `wf_race_character_nerf.py`：精确补丁函数和候选生成 CLI。
- `race_character_nerf_v1.json`：逐行原始指纹、修改坐标、旧值/新值和资源来源。
- `tests/test_race_character_nerf.py`：8 项回归。
- `tests/fixtures/race-character-nerf-v1/`：实际原表中的稀疏测试样本，不可发布。

在源仓库根目录运行：

```powershell
python -B tools/fantasy-gauntlet-mod-tools/wf_race_character_nerf.py --server-root F:\codex\startpoint-cn-private-clean --output-dir F:\codex\work\race-character-nerf-implementation-20260908\candidate
python -B -m unittest discover -s tools/fantasy-gauntlet-mod-tools/tests -p test_race_character_nerf.py -v
python -B F:\codex\work\race-character-nerf-implementation-20260908\verify_candidate.py
```

CLI 先读取最新有效主表，校验全部目标行，补丁后重新解析、二次执行验证幂等，并确认读取期间链尾和输入没有变化，然后才输出候选。曾实际拦截整合任务从 `.105` 变为 `.106` 期间的过时生成，随后在 `.106` 成功重跑。

整合发布器也可直接调用：

```python
from wf_race_character_nerf import patch_table
patched_bytes, report = patch_table(logical_path, latest_effective_bytes)
```

只接受完整审核前/后的目标行；数值、条件、触发、对象、冷却等出现未知漂移即拒绝。允许非目标键以及同一键中的非目标行包含后来新增的整合改动，并原样保留。非目标键的压缩字节保持不变。已经削弱的输入二次调用保持整个资源字节不变。

## 候选资源与证据

工作目录：`F:\codex\work\race-character-nerf-implementation-20260908\`。

| 逻辑资源 | 候选中的成员 | 输出 SHA-256 |
|---|---|---|
| `master/ability/ability.orderedmap` | `production/upload/1e/664c1cc8d80f4f9a69aae2c49ae8c01d1c4001` | `622d42377fc7973552f1f8b98356788948ec263887dcc893a66a4dc204a62ea5` |
| `master/ability/leader_ability.orderedmap` | `production/upload/ff/84353774cb95e8d7dc90c679f96a5bca7f42e5` | `e3becef39f2c3f95eb144e751f7c4d66c2b6588f6195c90a3a60cf900ada6101` |

两个资源均属于 `common`，Android/iOS 共用，无需 ATF、PNG、APK、IPA 或 SWF 修改。目标词条由能力数据生成描述；自定义描述表命中的条目为追加技能名称，不含本轮改动数值。

- `candidate/receipt.json`：56 格明细、源包、链尾、哈希、幂等与回读记录。
- `candidate/descriptions.json`：修改前后完整能力描述。描述器“协力”指 Unison 副位。
- `candidate/before/`：两张完整有效原表，只供核对，不放入补丁。
- `validation.json`：24 项有效资源源/运行镜像对照，以及双方实际 `out/lib/content-master.js` 导出对象验证。
- `verify_candidate.py`：重跑当前源/运行镜像与候选校验。发布后原表本应变化，该脚本的原表相等断言不再适合作为发布后门禁；发布后应改验末端资源等于 `patch_table` 终态。
- 原调查：`F:\codex\work\race-character-nerf-audit-20260908\调查与削弱建议.md`。

验证结果：8/8 回归通过；两张完整表共 3362/561 个键的回读通过；只有约定行列变化；56 格精确匹配；重复执行字节不变；未知/部分修改拒绝；非目标新改动保留。24 项源/镜像资源与调查时的角色相关内容哈希一致。双方实际公共导出中四名角色均有 6 个能力，能力键正确，竞速池权重各 `33333`。未进行游戏或设备实测，不能据此承诺实战伤害降幅。

## 接收任务制作新增量时

1. 完成其原工作后再接入本规则，重读最新有效链尾。若输入仍与上述 `.106` 两表哈希一致，可复用候选；否则优先在新输入上重跑规则，遇未知目标行漂移应人工核对，不能绕过守卫。
2. 从新链尾追加顺序版本边，仅将两份最终主表作为此次削弱的资源成员；新 ZIP 放 `assets/asset-patch/active/`，manifest 与审计记录一起更新。不要复制 `candidate/before/`、测试样本或整个过时主表包，也不要向 `.cdn/` 写入。
3. 回读最终 ZIP 和最终有效解析链，逐项确认是削弱终态，检查其他整合改动仍在。两种平台读取共用主表即可。
4. 按用户对整合任务已有的打包范围制作新的增量更新；本次交接本身不增加 Git 提交/推送或云端部署权限。原调查中第二轮 PF/EX、主动技削弱未实施。

本任务工作位于 `staging`，未提交、未推送、未同步运行镜像；没有修改现有共享 manifest 或他人整合文件。最终游戏生效需要上述接入步骤。
