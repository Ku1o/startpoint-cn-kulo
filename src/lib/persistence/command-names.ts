import type { MissionSettlementScope } from "../mission/settlement"
import type { PlayerQuestProgress } from "../../data/types"
import type { FinishContext } from "../../lib/quest/finish/types"

/**
 * Stable command names and their argument shapes.
 *
 * Commands are named here instead of inside the domain modules so callers, the
 * registry and the writer worker can share one literal without importing each
 * other. The domain type import is type-only, so this module stays free of
 * runtime dependencies and cannot create an import cycle.
 */

export const MISSION_SETTLE_CATEGORIES = "mission.settle_categories"

export interface MissionSettleCategoriesArgs {
    playerId: number
    categories: Array<number | MissionSettlementScope>
    evaluationTimeMs: number
}

/**
 * 单人副本结算前的关卡进度刷新。原实现用 runPersistenceTransaction 包裹，
 * 因为深渊最好成绩的刷新是"读+写"；把整段搬进写线程后主线程不再承担它。
 */
export const SINGLE_REFRESH_QUEST_PROGRESS = "single.refresh_quest_progress"

export interface SingleRefreshQuestProgressArgs {
    playerId: number
    section: number | string
    questId: number | string
}

export type SingleRefreshQuestProgressResult = PlayerQuestProgress | null

/** 多人结算后清理本场战斗的进行中关卡记录（单条 DELETE）。 */
export const MULTI_CLEANUP_ACTIVE_QUEST = "multi.cleanup_active_quest"

export interface MultiCleanupActiveQuestArgs {
    playerId: number
}

/**
 * 多人结算的"战斗事实"事务：任务战斗事实、推荐队伍、蒸气机器人挑战与角色经验。
 * finishCtx 全部由请求体与数据库行组成，是普通数据，可安全跨线程传递。
 */
export const MULTI_RECORD_BATTLE_FACTS = "multi.record_battle_facts"

export interface MultiRecordBattleFactsArgs {
    finishCtx: FinishContext
    partyCharacterIdsArray: number[]
    characterExpReward: number
    fixedParty: boolean
    evaluationTimeMs: number
}

export interface MultiRecordBattleFactsResult {
    missionBattleFacts: unknown
    steamRobotMissionId: number | null
    rewardCharacterExpResult: unknown
}
