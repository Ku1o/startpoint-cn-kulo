import type { MultiRoom, MultiMate, CompanionInfo } from "../types"
import type { IRoomMateProvider, RecruitResult } from "../types"
import type { NpcMateTemplate } from "../../lib/types"
import { NPC_TEMPLATES } from "./types"
import { buildNpcMates } from "./builder"

type RecruitedMate = RecruitResult["recruitedMates"][number]

export function selectStableNpcSlots(
    recruitedMates: readonly RecruitedMate[],
    count: number,
): RecruitedMate[] {
    const desiredCount = Math.max(0, Math.min(2, Math.floor(count)))
    if (desiredCount === 0) return []

    // Real players replace COM seats from the front (COM1, then COM2). Keep
    // the remaining tail seats when the lobby is rebuilt so a 2R1B rematch
    // does not silently change the surviving bot from COM2 back to COM1.
    return [...recruitedMates]
        .sort((left, right) => left.com_id - right.com_id)
        .slice(-desiredCount)
}

export class NpcMateProvider implements IRoomMateProvider {
    getMates(roomNumber: string): MultiMate[] {
        const { mate1, mate2 } = buildNpcMates()
        return [mate1, mate2].filter((m): m is MultiMate => m !== null)
    }

    async onRecruit(roomNumber: string, hostViewerId: string): Promise<RecruitResult> {
        return {
            recruitedMates: [
                { viewer_id: 900000001, com_id: 1 },
                { viewer_id: 900000002, com_id: 2 },
            ],
        }
    }

    isRoomFull(roomNumber: string): boolean {
        return true
    }

    getAvailableCompanions(hostViewerId: string): CompanionInfo[] {
        return []
    }
}
