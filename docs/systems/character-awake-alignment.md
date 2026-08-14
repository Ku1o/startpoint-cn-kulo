# 角色觉醒功能对齐文档

## 问题发现

### 症状

- 觉醒**任务页**：4 条任务全部显示完成 ✅
- 觉醒**能力页**：tab 按钮显示"任务未全部完成" ❌
- 客户端在进入任务页后，tab 从可点击变为锁定

### 排查过程

#### 1. 最初假设：`get_mission_progress` 响应格式问题

检查了 `stage`、`progress_value`、`mail_arrived` 等字段。通过与客户端源码
`MissionGetMissionProgressRealRemote.successHandler()` 比对，确认所有字段类型对齐。

**结论**：响应格式正确，不是原因。

#### 2. 假设：`stage` 值问题

尝试 `stage=0`（模拟"未领取"）、`stage=1-4`（按 lastDigit 递增），均无效果。

**结论**：客户端不依赖 `stage` 判断完成。

#### 3. 假设：ex_boost 字段

尝试设置 `ex_boost_status_id` 为多种值（0、8、14010），均导致 C8601 客户端崩溃。

**结论**：ex_boost 属于另一个独立系统，不是原因。

#### 4. 假设：`manaBoardAwake` 字段

从调试版 APK 存档中发现客户端写入了 `manaBoardAwake: { "1": 1 }`。
尝试在 `/load` 响应的 character 对象中添加该字段（驼峰和蛇形均试过），无 crash 也无效果。

**结论**：该字段不由 `/load` 解析。

#### 5. 突破：发现反编译代码不完整

原始反编译 `wf-2.1.125-cn-decompiled` 缺少 `CharacterAwakeStatusLogic`、
`CharacterAwakeMissionLogic`、`ManaBoardAwakeRequiredCondition` 等关键类。

**解决**：从新版 APK 的 SWF 文件中用 FFDec 重新导出，获取了缺失的类。

#### 6. 源码确认：两条不同的判定路径

**任务页判定**：
```as3
// MissionStageLogicImpl.as:66
isCompleted() = targetValue ≤ progress
// 3410051: target=1, progress=5 → 5 ≥ 1 = true ✅
```
数据源：`get_mission_progress(cat=9, char_id=341005)` 实时响应

**能力页判定**：
```as3
// CharacterAwakeEventLogic.as:45-51
isCompleteMission(missionId, param2) {
    lastStage = rewardTable.keys().last()  → 1
    return param2 == lastStage
}
// 如果 param2 是 progress_value(5)，5 ≠ 1 ❌
```
数据源：`LoadedDataTools.clearedActiveMissions`（来自 `/load` 的 `all_active_mission_list`）

**关键发现**：`clearedActiveMissions` 从 `/load` 的 `all_active_mission_list` 填充，
而该列表被 `filterToActiveMissions` 过滤掉了 cat9 的觉醒任务 ——
因为 `activeMissionIdSet` 只包含 `mission_active_reward.json` 的 ID（96 个），
觉醒任务在 `mission_char_awake_reward.json` 中。

#### 7. 确认根因：两套数据源

```
任务页：get_mission_progress → 实时计算 → 正确 ✅
能力页：/load → all_active_mission_list → filterToActiveMissions 过滤 → 无 cat9 → "未完成" ❌
```

### 修复

`lib/mission/index.ts:38-43` — `filterToActiveMissions` 改为直接透传，不再过滤：

```typescript
export function filterToActiveMissions<T>(missions: Record<string, T>): Record<string, T> {
    return missions
}
```

## 角色觉醒完整流程（基于新版 SWF 反编译）

### 解锁条件（按钮可见性）

```as3
// OwnedCharacterLogic.isAwakeMissionOpened(time)
1. isAwakeEventOpened(time)     — CDN CharacterAwakeEventTable 有当前角色条目 + 时间在窗口内
2. get_level() ≥ get_baseLevelCap() — 角色满级
3. hasLearnedAllManaNodeOfManaBoard(1) — 玛纳板 1 全部节点学完
```

CDN 数据：`character_awake_event.json`（36 条），每条有 `start_time` + `end_time`。

### 数据流

```
/load 响应
  ├─ user_character_list — 角色基础属性（等级、mana_board_index、ex_boost 等）
  └─ all_active_mission_list — 全部活跃任务进度（含觉醒任务）

get_mission_progress(cat=9, char_id=341005)
  └─ mission_progress_list — 4 条觉醒任务进度（实时计算）

character_list（API 响应）
  └─ mana_board_awake — 各板觉醒等级 { "1": 1 }（由 character/awake_mana_node 等端点返回）
```

### 客户端关键类清单

| 类 | 路径 | 用途 |
|------|------|------|
| `CharacterAwakeMissionLogic` | `pinball.common.data.mission.characterAwake` | 觉醒任务逻辑 |
| `CharacterAwakeEventLogic` | `pinball.common.data.mission.characterAwake` | 觉醒事件管理 |
| `CharacterAwakeStatusLogic` | `pinball.common.data.character` | 觉醒属性加成 |
| `ManaBoardAwakeRequiredCondition` | `pinball.common.data.ability` | 解锁条件枚举 |
| `CharacterAwakeScene` | `pinball.scene.characterAwake` | 觉醒场景（未导出） |
| `CharacterAwakeDialog` | `pinball.dialog.characterAwake` | 觉醒弹窗 |

### CDN 关键文件

| 文件 | 用途 |
|------|------|
| `mission/character_awake_event.json` | 觉醒事件时间窗口（36 条） |
| `mission/character_awake_mission.json` | 觉醒任务定义 |
| `mission/character_awake_mission_reward.json` | 觉醒任务奖励 |
| `character/character_awake_status.json` | 觉醒属性（ATK/HP 加成） |

### 提取新版 SWF 源码的方法

新版 APK 的 SWF 中包含 `wf-2.1.125-cn-decompiled` 缺失的类。
提取步骤：

```bash
# 1. 从 APK 提取 SWF
unzip apk/com.leiting.wf.apk -d /tmp/wf_apk_extract

# 2. 列出 AS3 脚本（找目标类名）
ffdec.sh -dumpAS3 /tmp/wf_apk_extract/assets/worldflipper_android_release.swf \
  | grep -i "awake"

# 3. 全量导出（可能很慢，需 2G+ Java heap）
java -Xmx2g -jar ffdec/ffdec-cli.jar \
  -export script wf-awake-source \
  /tmp/wf_apk_extract/assets/worldflipper_android_release.swf

# 4. 搜索目标文件
find wf-awake-source -name "*Awake*" -o -name "*awake*"

# 5. 如果导出卡死，用 strings 从 SWF 提取字符串参考
strings worldflipper_android_release.swf | grep -i "CharacterAwake"
```

---

## 实现参考 (2026-07-03)

### 数据流向

```
┌──────────────────────────────────────────────────────────────┐
│ /load 响应                                                   │
│ ├─ data.active_mission_list  ──→ ReceiveCommonResponse       │
│ │   └─ applyCommonResponseActiveMission: exists() 安全过滤    │
│ ├─ user_character_list[i].mana_board_awake = { "1": N }      │
│ │   └─ PlayerLogic.applyManaBoardAwake                      │
│ └─ user_character_mana_node_list[i].awake_level = N          │
│     └─ serialize-player.ts 从 DB 读取真实值                   │
└──────────────────────────────────────────────────────────────┘
```

### 端点

#### `POST /character/awake_mana_node`

```
请求:  { viewer_id, character_id, api_count, mana_node_multiplied_id_list, awake_level }
响应:  {
    user_info:   { free_mana, paid_mana },
    character_list: [{ character_id, mana_board_awake: {1:N}, evolution_level, bond_token_list, ... }],
    user_character_mana_node_list: { char_id: [{ multiplied_id, awake_level }] },
    item_list:   { ... },
    mail_arrived: false
}
```

- 已到目标等级的节点跳过（idempotent）
- `awake_level=1` 时也会轮询 `receive_bond_token` ── 但因 status=2 直接返回 200

### CDN 关键表

| 文件 | 结构 | 用途 |
|------|------|------|
| `mana_node_awake.json` | `{ rarity → slot → pedestal_size → [items, counts, mana] }` | 觉醒消耗 |
| `mana_board.json` | `{ charId → level → nodeIdx → [multiplied_id, x, y, road, pedestal_size, parent] }` | pedstal_size 查表 |
| `mana_node.json` | `{ charId → level → nodeId → { field6 } }` | field6→slot 映射 |

**slot 推导**: `field6`=1/2/3="" → ability slot 1/2/3 或 skill slot 4

### DB 变更

```sql
ALTER TABLE players_characters_mana_nodes ADD COLUMN awake_level INTEGER NOT NULL DEFAULT 0
```

### 常见问题排查

| 现象 | 根因 | 定位 |
|------|------|------|
| H400 `awake_mana_node` | CDN 成本查表失败 | 检查 `rarity`=`character.json[charId][3]`；`slot`=`field6`；`pedestal_size`=`mana_board.json[charId][level][nodeIdx][4]` |
| H400 `receive_bond_token` | status=2 已领取 | 兜底返回 200，不发重复奖励 |
| `/load` 中 `awake_level` 恒为 0 | serialize-player.ts 未读 DB | 已修复：通过 `MergedPlayerData.characterManaNodeAwakeLevels` |
| 觉醒后重进玛纳板仍显示「未觉醒」 | 同上 | 同上 |
| C8601 `active_mission_list` | ActiveMissionRepository 不认识 cat9 mission ID | 不把 cat9 放入 `all_active_mission_list`；用 `data.active_mission_list` 通道 |
```
