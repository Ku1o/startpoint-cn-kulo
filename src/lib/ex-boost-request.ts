import { createHash } from "node:crypto"
import { getDb } from "../data/db"
import { getPlayerOperationReceiptSync, insertPlayerOperationReceiptSync } from "../data/domains/player-operation-receipt"
import type { PendingExBoostDraw } from "../data/domains/ex-boost-pending"
import { readGameplayMutationIdentitySync } from "./gameplay-request-identity"

interface ExBoostReceipt { fingerprint: string; draw: PendingExBoostDraw; confirmed?: boolean }
export interface ExBoostRequest { key: string; operation: string; fingerprint: string; previous?: ExBoostReceipt }
function invalid(message: string): never { throw Object.assign(new Error(message), { statusCode: 400 }) }
export function readExBoostRequest(playerId: number, accountId: number, headerToken: unknown,
    body: { viewer_id?: unknown; api_count?: unknown }, operation: string, payload: unknown): ExBoostRequest | null {
    // Legacy callers remain compatible. api_count alone is never a durable identity.
    if (headerToken === undefined) return null
    const identity = readGameplayMutationIdentitySync(getDb(), headerToken, body, accountId)
    if (!identity) invalid("EX boost request identity is invalid.")
    const fingerprint = createHash("sha256").update(JSON.stringify(payload)).digest("hex")
    const previous = getPlayerOperationReceiptSync<ExBoostReceipt>(playerId, operation, identity.requestKey)?.response
    if (previous && previous.fingerprint !== fingerprint) invalid("EX boost request identity conflicts with its payload.")
    if (!previous && !identity.isCurrent) invalid("EX boost request identity is superseded.")
    return { key: identity.requestKey, operation, fingerprint, previous }
}
export function rememberExBoostRequest(playerId: number, request: ExBoostRequest | null,
    draw: PendingExBoostDraw, confirmed?: boolean): void {
    if (!request || request.previous) return
    insertPlayerOperationReceiptSync({ playerId, operation: request.operation, requestKey: request.key,
        response: { fingerprint: request.fingerprint, draw, ...(confirmed === undefined ? {} : { confirmed }) } })
}
