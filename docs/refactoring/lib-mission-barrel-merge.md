# lib/mission 双 barrel 清理 (已完成)

## 执行日期

2026-07-02

## 背景

`lib/mission` 存在双 barrel 结构:
```
lib/mission.ts               ← 4 个消费者 import 从这里进口 (legacy barrel)
  └─ re-export → ./mission/index

lib/mission/index.ts          ← 真正的模块组织
  ├─ re-exports from 8 子模块
  └─ 内联逻辑: isActiveMissionId / filterToActiveMissions (11 行)
```

## 已完成的步骤

### Step 1: 消除双 barrel

| 操作 | 文件 | 状态 |
|------|------|:----:|
| 删除 | `src/lib/mission.ts` | ✅ |
| 新建 | `src/lib/mission/filter.ts` | ✅ |
| 修改 | `src/lib/mission/index.ts` | ✅ |
| 修改 | `src/routes/cn/load.ts` | ✅ |
| 修改 | `src/routes/api/mission.ts` | ✅ |
| 修改 | `src/routes/api/activeMission.ts` | ✅ |
| 修改 | `src/data/utils/player-data.ts` | ✅ |

`lib/mission/filter.ts` 从 `index.ts` 的内联逻辑中提取了 `isActiveMissionId` 和 `filterToActiveMissions`，使 barrel 变成纯 re-export。

### Step 2: 统一类型导入

| 操作 | 文件 | 状态 |
|------|------|:----:|
| 修改 | `src/lib/mission/index.ts` 追加 `export type { CategoryContext }` | ✅ |
| 修改 | `src/routes/api/mission.ts:9` 类型导入路径改为 barrel | ✅ |

### Step 3: 消除 `as any` 类型旁路

| 操作 | 文件 | 状态 |
|------|------|:----:|
| 修改 | `src/data/utils/serialize-player.ts` 增加 `SerializePlayerDataOptions` 的两个可选字段 | ✅ |
| 修改 | `src/data/utils/player-data.ts` 调用 `computeAwakeSummary` 传递觉醒数据 | ✅ |
| 修改 | `src/routes/cn/load.ts` 移除 `as any`、`computeAwakeSummary`、`businessCodeToKId` | ✅ |

`mana_board_awake` 现在在 `serialize-player.ts` 中通过 `options?.manaBoardAwakeMap?.get(characterId)` 注入，完全类型安全。
`active_mission_list` 同样通过 `options?.activeMissionList` 在序列化层追加。

## 结果

```
# 改动统计
M  src/data/utils/player-data.ts      # +import computeAwakeSummary, 传选项
M  src/data/utils/serialize-player.ts # +SerializePlayerDataOptions 两个字段
D  src/lib/mission.ts                 # 删除 legacy barrel
M  src/lib/mission/index.ts           # 纯 barrel，无内联逻辑
A  src/lib/mission/filter.ts          # 提取的过滤逻辑 (15 行)
M  src/routes/api/activeMission.ts    # /index 路径
M  src/routes/api/mission.ts          # /index 路径 + CategoryContext 类型统一
M  src/routes/cn/load.ts             # 移除 awake 注入代码 (净减 14 行)
```

## 后续

### 已完成: 拆分 `wdfpData` barrel (2026-07-02)

`src/data/wdfpData.ts` (mega-barrel, 52 行) 已被删除。64 个消费者文件现在直接从 domain 模块导入。

改动统计: 65 files changed, 270 insertions(+), 130 deletions(-)

导入模式:
```
改前: import { fps, gcs, gpls, ...27 names } from "../wdfpData"
改后: import { fps, gpls } from "../domains/player"
      import { gcs } from "../domains/character"
```

清理:
- 16 条 dead import（导入后从未使用）
- 重复的 getDb()（data/db.ts 才是官方定义）
- expPoolMax 常量（无消费者引用）

### 可选: 替换 `import type` + 垂直格式化

5 个文件在 `data/utils/` 下同时 import 59 个命名（32 类型 + 27 函数），可改用 `import type` + 垂直格式。
