# 任务-关卡映射表 (Mission → Quest Map)

> 生成脚本: `scripts/gen_mission_event_quest_map.js`
> 输出文件: `assets/mission_event_quest_map.json`
> 覆盖范围: cat3 活动任务 2512 条，9 种 col[7] 类型

---

## 一、映射规则

### 通用原理

```
mission.col[7] → 选择 CDN quest 文件
mission.col[8] or col[9] → 在该文件中查找 stage_group/folder_id
CDN quest 文件的 row[0] = quest_id → 收集所有 difficulty 的 quest_id
```

### CDN 文件结构（通用模式）

```json
{
  "<stage_group或folder_id>": {
    "<difficulty_index>": [
      ["<quest_id>", "<element>", "<name>", ...]
    ]
  }
}
```

### 按 col[7] 分派

| col[7] | CDN 文件 | 映射键 | quest_category |
|:---:|------|:---:|:---:|
| 2 | `boss_battle_quest.json` | col[9]=stage_group | [2] |
| 5 | `advent_event_quest.json` | col[8]=stage_group | [7, 8] |
| 7 | `challenge_dungeon_event_quest.json` | 全部 quest | [13] |
| 8 | `ranking_event_single_quest.json` | col[8]=key | [11] |
| 10 | `world_story_event_boss_battle_quest.json` | col[8]=event_id | [19] |
| 15 | `carnival_event_quest.json` | col[8]=folder_id | [22] |
| 16 | `raid_event_quest.json` | col[8]=stage_group | [23] |
| 17 | `rush_event_quest.json` | col[8]=event_id | [24] |

### 输出格式

```json
{
  "pattern_name": {
    "questIds": [1010001, 1010002, ...],
    "categories": [2]
  }
}
```

---

## 二、各类型详细说明

### A — BOSS_BATTLE (col[7]=2, 920 条)

**col[9] = stage_group** → `boss_battle_quest.json` 中该 stage_group 下的所有 difficulty 的 quest_id。

| col[9] | boss 名称 | quest_ids |
|:---:|------|------|
| 3 | 不死王瑞西塔尔 | 1003001~1003004 |
| 5 | 废墟守卫·火 | 1005001~1005004 |
| 6 | 废墟魔像 | 1006001~1006004 |
| 10 | 寄居蟹船长 | 1010001~1010004 |
| 12 | 诅咒弧魔艾基尔 | 1012001~1012004 |
| 14 | 白虎 | 1014001~1014004 |
| 16 | Sec-5200Li | 1016001~1016004 |
| 17 | 管理者 | 1017001~1017004 |
| 19 | 妖狐 | 1019001~1019004 |
| 20 | 八岐大蛇 | 1020001~1020003 |

八岐大蛇只有 3 个难度。col[9] 为空 = 全部 boss 都算。

### B — ADVENT_EVENT (col[7]=5, 481 条)

**col[8] = stage_group** → `advent_event_quest.json`。

含 5 个子类型：常规降临 boss、荒龙/废龙系列、精灵兽系列、机兵系列、联动活动。

荒龙系列 col[8] 对照：6(灼炎复刻), 7(凶暗), 10(雷废龙), 12(水废龙), 13(歼风), 18(凶暗复刻), 3000(灼炎再复刻), 3001(光废龙复刻)。

quest_category = [7, 8]（单人+多人都查）。

### C — CHALLENGE_DUNGEON (col[7]=7, ~106 条)

全部指向 challenge_dungeon_event_quest.json folder=1 的 20+ 条 quest：

```
[1020, 1021, 1022, 1023, 1024, 1025, 1026, 1027, 1028, 1029,
 1030, 1031, 1032, 1033, 1034, 1035, 1036, 1037, 1038, 1039, 1040]
```

category = [13]。

### D — RANKING_EVENT (col[7]=8, 230 条)

**col[8] = key** → `ranking_event_single_quest.json`。

| col[8] | 试炼名 | quest_id |
|:---:|------|------|
| 1 | 云水试炼 v1 | 1001 |
| 2 | 溢光试炼 v1 | 2001 |
| 3 | 旋风试炼 v1 | 3001 |
| 4 | 奔雷试炼 v1 | 4001 |
| 5 | 闪火试炼 v1 | 5001 |
| 1000 | 云水试炼 v2 | 1000001 |
| 1001 | 溢光试炼 v2 | 1001001 |

category = [11]。实测验证 ✅。

### E — WORLD_STORY_BOSS (col[7]=10, 342 条)

**col[8] = event_id** → `world_story_event_boss_battle_quest.json`。

| col[8] | 事件名 |
|:---:|------|
| 100300 | 大海的遗产 |
| 100401 | 幻彩摩天楼 |
| 100406 | HERO:BEGINNING |
| 100409 | 百兽王冠 |
| ... | (共 24 个事件) |

category = [19]。

### F — CARNIVAL (col[7]=15, 54 条)

**col[8] = folder_id** → `carnival_event_quest.json`。

同一套 quest (4001~4009) 被不同 col[8] 值复用。

category = [22]。

### G — RAID (col[7]=16, 96 条)

**col[8] = stage_group** → `raid_event_quest.json`。

category = [23]。

### H — RUSH (col[7]=17, 110 条)

**col[8] = event_id** → `rush_event_quest.json`。

| col[8] | 事件 |
|:---:|------|
| 700001 | 第一次狂热激战 |
| 700002~700007 | 第二~七次 |

category = [24]。

---

## 三、quest_category 速查

| QuestCategory | 编号 | 说明 |
|------|:---:|------|
| BOSS_BATTLE | 2 | 领主战 |
| ADVENT_EVENT_SINGLE | 7 | 降临讨伐 单人 |
| ADVENT_EVENT_MULTI | 8 | 降临讨伐 多人 |
| RANKING_EVENT_SINGLE | 11 | 时间试炼 |
| CHALLENGE_DUNGEON_EVENT | 13 | 深渊之兽 |
| WORLD_STORY_EVENT_BOSS_BATTLE | 19 | 世界故事 BOSS 战 |
| CARNIVAL_EVENT | 22 | 土俑嘉年华 |
| RAID_EVENT | 23 | 战阵之宴 |
| RUSH_EVENT | 24 | 狂热激战 |

---

## 四、追踪层架构

```
lib/quest/finish/trackers:
  character-clear-tracker.ts   — 角色出场/队长/联机计数
  powerflip-tracker.ts         — 弹射/冲刺全局计数
  leader-powerflip-tracker.ts  — 角色弹射 per-char 计数
  party-co-clear-tracker.ts    — 同队 pairwise 计数

DB 源表:
  players_quest_progress           — 关卡通关 (finished + multi_clear_count)
  players_character_quest_clears    — 角色出场 (clear/leader/multi/powerflip)
  players.total_*                   — 全局计数器
  players_party_member_co_clears    — 同队计数
  players_periodic_snapshots        — 每日快照

计算层:
  lib/mission/computer-*.ts        — 8 个 MissionComputer
  lib/mission/registry.ts          — registry dispatch
  assets/mission_event_quest_map.json — cat3 预生成映射
```
