import { getMissionBattleCountersSync } from "../../data/domains/mission_battle_facts"
import { getPlayerCollectedItemTotalsSync } from "../../data/domains/item"
import { getPlayerSync } from "../../data/domains/player"
import { countFinishedPlayerQuestsSync, getPlayerQuestProgressSync } from "../../data/domains/quest"
import type { Player, PlayerQuestProgress } from "../../data/types"
import {
    getMissionCounterValuesSync,
    makeMissionCounterKey,
    type MissionCounterQuery,
} from "./counters"
import { getSnapshot, type SnapshotData } from "./snapshot"

/**
 * Request-scoped authoritative reads shared by all mission category computers.
 * The cache deliberately lives for one settlement only; it must never be kept
 * across a reward boundary or reused by another request.
 */
export class MissionEvaluationReadContext {
    private playerValue: Player | null | undefined
    private battleCountersValue: ReturnType<typeof getMissionBattleCountersSync> | undefined
    private totalQuestClearsValue: number | undefined
    private collectedItemTotalsValue: Record<string, number> | undefined
    private questProgressValue: Record<string, PlayerQuestProgress[]> | undefined
    private readonly snapshots = new Map<string, SnapshotData | null>()
    private readonly missionCounterValues = new Map<string, number>()

    constructor(readonly playerId: number) {}

    get player(): Player {
        if (this.playerValue === undefined) this.playerValue = getPlayerSync(this.playerId)
        if (!this.playerValue) {
            throw new Error(`Player ${this.playerId} not found during mission settlement.`)
        }
        return this.playerValue
    }

    get battleCounters(): ReturnType<typeof getMissionBattleCountersSync> {
        if (this.battleCountersValue === undefined) {
            this.battleCountersValue = getMissionBattleCountersSync(this.playerId)
        }
        return this.battleCountersValue
    }

    get totalQuestClears(): number {
        if (this.totalQuestClearsValue === undefined) {
            this.totalQuestClearsValue = countFinishedPlayerQuestsSync(this.playerId)
        }
        return this.totalQuestClearsValue
    }

    get collectedItemTotals(): Record<string, number> {
        if (this.collectedItemTotalsValue === undefined) {
            this.collectedItemTotalsValue = getPlayerCollectedItemTotalsSync(this.playerId)
        }
        return this.collectedItemTotalsValue
    }

    get questProgress(): Record<string, PlayerQuestProgress[]> {
        if (this.questProgressValue === undefined) {
            this.questProgressValue = getPlayerQuestProgressSync(this.playerId)
        }
        return this.questProgressValue
    }

    snapshot(periodType: string): SnapshotData | null {
        if (!this.snapshots.has(periodType)) {
            this.snapshots.set(periodType, getSnapshot(this.playerId, periodType))
        }
        return this.snapshots.get(periodType) ?? null
    }

    setSnapshot(periodType: string, snapshot: SnapshotData): void {
        this.snapshots.set(periodType, snapshot)
    }

    missionCounters(queries: readonly MissionCounterQuery[]): ReadonlyMap<string, number> {
        const missing = queries.filter(query => !this.missionCounterValues.has(makeMissionCounterKey(query)))
        if (missing.length > 0) {
            const loaded = getMissionCounterValuesSync(this.playerId, missing)
            for (const query of missing) {
                const key = makeMissionCounterKey(query)
                this.missionCounterValues.set(key, loaded.get(key) ?? 0)
            }
        }
        return this.missionCounterValues
    }
}
