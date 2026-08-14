# 狂热激战(Rush Event)
> 状态: 已实现   关键文件: src/data/domains/rushEvent.ts   相关端点: /event/rush/*

本文档描述狂热激战(Rush Event)活动系统的实现:14 个事件、API 端点、关卡流程、converter 修复、复刻事件回退逻辑及关键 bug 修复。

14 events — 7 primary (700001-700007) + 7 reruns (700011-700017). Reruns share primary's quests/quest folders/shop data.

## API endpoints (`/event/rush/*`)

| Endpoint | Purpose | Client response key quirks |
|----------|---------|---------------------------|
| `/summary` | Event state + played parties + my ranking | `endless_battle_max_round`, `endless_battle_played_max_round` |
| `/select_folder` | Lock into a difficulty | Rejects if `activeRushBattleFolderId !== null` |
| `/party` | Get EVENT (category=4) party groups | Same flow as RaidEvent |
| `/battle/start` | Start a quest, inserts active quest | Uses regular `/single_battle_quest/finish` for completion |
| `/finish` (via single_battle_quest) | Clear reward + endless record + folder clear | `rush_event` field in response |
| `/endless_battle` | Get endless mode state | Reads `PlayerRushEvent` from DB |
| `/ranking` | Leaderboard | Returns `ranking_data` (NOT `ranking_list`) |
| `/ranking/played_party` | View other player's party | Returns `rush_ranking_party` |
| `/reset` | Reset folder or endless progress | `quest_type`: 1=FOLDER, 2=ENDLESS |
| `/reward` | Claim ranking rewards after aggregation | Matches CDN rank tiers |

## Quest flow
1. `/summary` → get state
2. `/select_folder {folderId}` → lock folder
3. `/battle/start {questId}` → inserts active quest
4. Client battles → `/single_battle_quest/finish` → handle reward/record
5. Folder clears when `rushEventRound >= rushEventFolderMaxRounds[folderId]`
6. Folder clear reward from `getRushEventFolderClearRewards()`

## Key converter fixes
- `convert_rush_event_quest_folder`: added `folder = folder[0]` to extract inner array from CDN's 3-layer nested structure
- `convert_rush_event_ranking_reward`: new converter for ranking rewards (14 events × 3 tiers)
- `convert_event_item_shop`: added `item = item[0]` for shop items

## Rerun event fallback
Events 700011-700017 have no standalone rewards/shop data in CDN. Server maps to primary (ID - 10):
- `getEventShopItemsSync()`: type 11 → try exact, fallback ID-10
- `getRushEventFolderClearRewards()`: try exact, if empty array/null → fallback ID-10

## Critical bug fixes
- **folder clear crash**: `rushEventRound=0` (endless) tricked `>= (maxRounds[4] ?? 0)` → added FOLDER type guard
- **folder clear residue**: delete all parties then unconditionally re-insert last round → restructured to only insert non-final rounds
- **shop empty**: date filter re-enabled via `getServerDate()` for GENERAL shop; event_item_shop.json regenerated
- **shop purchase broken**: `general_shop.json` had ALL 290 reward types as `1`(EXP) instead of correct `0`(ITEM)/`2`(MANA)/`4`(EQUIPMENT) — items never given to players; regenerated from `wf-assets-cn/orderedmap/shop/general_shop.json` with correct types
- **shop buy response**: cleaned up `user_info` to only changed fields; removed `joined_character_id_list` (client `earlySuccessHandler` doesn't parse it); fixed `free_vmoney` missing reward vmone

## No per-quest drops
Rush event quests have NO `scoreRewardGroupId` in CDN. Drops come ONLY from folder clear rewards and ranking rewards. `[BATTLE] scoreReward groupId=undefined` is expected.
