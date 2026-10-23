import { getPlayerOperationReceiptSync, insertPlayerOperationReceiptSync } from "../../data/domains/player-operation-receipt"

const OPERATION = "mission.rescue_battle"

interface RescueBattleIdentity {
    playerId: number
    playId: string
    category: number
    questId: number
    roomNumber: string
}

interface AcceptedRescueStart extends RescueBattleIdentity {
    viewerId: number
    roomInstanceId: string
    battleSessionId: string
    isHost: boolean
    isRescueGuest: boolean
    isRescueFragmentEligible: boolean
}

interface RescueBattleRegistration extends RescueBattleIdentity {
    schemaVersion: 1
    viewerId: number
    roomInstanceId: string
    battleSessionId: string
}

const text = (value: unknown): value is string => typeof value === "string" && value.length > 0
const integer = (value: number): boolean => Number.isSafeInteger(value) && value > 0

/** Only the owner's accepted random-rescue projection may call this at durable start. */
export function registerAcceptedRescueBattleSync(start: AcceptedRescueStart): void {
    if (start.isHost || !start.isRescueGuest || !start.isRescueFragmentEligible) return
    if (![start.playerId, start.viewerId, start.category, start.questId].every(integer)
        || ![start.playId, start.roomNumber, start.roomInstanceId, start.battleSessionId].every(text)) {
        throw new TypeError("Invalid accepted rescue battle identity.")
    }
    const registration: RescueBattleRegistration = {
        schemaVersion: 1, playerId: start.playerId, viewerId: start.viewerId,
        playId: start.playId, category: start.category, questId: start.questId,
        roomNumber: start.roomNumber, roomInstanceId: start.roomInstanceId, battleSessionId: start.battleSessionId,
    }
    const existing = getPlayerOperationReceiptSync<RescueBattleRegistration>(start.playerId, OPERATION, start.playId)
    if (existing) {
        if (JSON.stringify(existing.response) !== JSON.stringify(registration)) throw new Error("Accepted rescue battle identity changed.")
        return
    }
    insertPlayerOperationReceiptSync({ playerId: start.playerId, operation: OPERATION, requestKey: start.playId, response: registration })
}

/** Retained start identity survives owner/snapshot loss; finish still owns replay prevention. */
export function isRegisteredRescueBattleSync(identity: RescueBattleIdentity): boolean {
    const registration = getPlayerOperationReceiptSync<RescueBattleRegistration>(identity.playerId, OPERATION, identity.playId)?.response
    return registration?.schemaVersion === 1
        && registration.playerId === identity.playerId && registration.playId === identity.playId
        && registration.category === identity.category && registration.questId === identity.questId
        && registration.roomNumber === identity.roomNumber
        && integer(registration.viewerId) && text(registration.roomInstanceId) && text(registration.battleSessionId)
}
