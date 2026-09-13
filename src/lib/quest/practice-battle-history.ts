import type { PracticeBattleHistoryInsert } from "../../data/domains/practice-battle-history"
import { clientSerializeDate } from "../../data/utils"
import {
    buildBattleHistoryProtocolRecord,
    type BuildBattleHistoryInput,
} from "./battle-history"

export interface BuildPracticeBattleHistoryInput extends BuildBattleHistoryInput {
    /** Actual completion/abandonment instant, without the event time offset. */
    readonly createdAt: Date
    readonly playerId: number
    readonly playId: string
}

export function buildPracticeBattleHistoryRecord(
    input: BuildPracticeBattleHistoryInput,
): PracticeBattleHistoryInsert {
    if (!Number.isSafeInteger(input.playerId) || input.playerId <= 0
        || typeof input.playId !== "string" || input.playId.length === 0) {
        throw new Error("Practice battle history identity is invalid")
    }
    return {
        playerId: input.playerId,
        playId: input.playId,
        ...buildBattleHistoryProtocolRecord(input, 15, "Practice battle history"),
        // The CN list displays this timezone-less value verbatim and sorts by
        // it again. Real Beijing time keeps the archive's dates independent
        // from event-clock changes, including backward jumps.
        create_time: clientSerializeDate(new Date(input.createdAt.getTime() + 8 * 60 * 60 * 1000)),
    }
}
