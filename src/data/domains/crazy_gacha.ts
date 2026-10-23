import { getDb } from "../db"
import { getPlayerOperationReceiptSync, insertPlayerOperationReceiptSync } from "./player-operation-receipt"
import type { GachaDrawMetadata, PlannedCharacterGachaMovie } from "../../lib/gacha"

export const CRAZY_GACHA_ID = 100
export const CRAZY_GACHA_TICKET_ID = 999012
export interface CrazyGachaDraw {
    character_id: number
    movie_id: string
    seed: number
    entry_count: number
    ex_boost_item: null
}
export interface CrazyGachaCandidate {
    draw: CrazyGachaDraw[]
    metadata: GachaDrawMetadata[]
    movies: PlannedCharacterGachaMovie[]
}
export interface CrazyGachaState {
    version: 1
    sessionId: string
    status: "pending" | "finalized"
    drawCount: number
    maxDrawCount: number
    latest: CrazyGachaCandidate
    saved: { "1"?: CrazyGachaCandidate; "2"?: CrazyGachaCandidate }
    selectedIndex?: number
}
export interface StoredCrazyGachaState { sessionNumber: number; state: CrazyGachaState }
const completionOperation = "crazy_gacha_completion"

const positiveInteger = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0
function validateCandidate(candidate: CrazyGachaCandidate): void {
    if (!candidate || !Array.isArray(candidate.draw) || candidate.draw.length !== 10
        || !Array.isArray(candidate.metadata) || candidate.metadata.length !== 10
        || !Array.isArray(candidate.movies) || candidate.movies.length !== 10) throw new Error("Invalid crazy gacha candidate")
    for (let i = 0; i < 10; i++) {
        const draw = candidate.draw[i], metadata = candidate.metadata[i], movie = candidate.movies[i]
        if (!draw || !metadata || !movie || !positiveInteger(draw.character_id)
            || draw.entry_count !== 1 || !Number.isSafeInteger(draw.seed) || draw.seed < 0
            || typeof draw.movie_id !== "string" || !draw.movie_id || draw.ex_boost_item !== null
            || metadata.id !== draw.character_id || !positiveInteger(metadata.rank) || typeof metadata.isGuarantee !== "boolean"
            || movie.characterId !== draw.character_id || movie.movieId !== draw.movie_id || movie.seed !== draw.seed
            || !positiveInteger(movie.rarity) || typeof movie.moviePlayable !== "boolean"
            || typeof movie.rarityUp !== "boolean" || typeof movie.requiresVerification !== "boolean") {
            throw new Error("Invalid crazy gacha draw identity")
        }
    }
}

/** Business state is portable; protocol retry receipts alone cannot replace it. */
export function parseCrazyGachaState(value: string): CrazyGachaState {
    const state = JSON.parse(value) as CrazyGachaState
    if (!state || state.version !== 1 || typeof state.sessionId !== "string"
        || !/^[0-9a-f-]{36}$/i.test(state.sessionId) || !["pending", "finalized"].includes(state.status)
        || !positiveInteger(state.drawCount) || !positiveInteger(state.maxDrawCount) || state.drawCount > state.maxDrawCount
        || !state.saved || typeof state.saved !== "object" || Array.isArray(state.saved)
        || Object.keys(state.saved).some(key => key !== "1" && key !== "2")) throw new Error("Invalid crazy gacha state")
    validateCandidate(state.latest)
    for (const candidate of Object.values(state.saved)) validateCandidate(candidate)
    if (state.status === "finalized" && (!Number.isSafeInteger(state.selectedIndex)
        || ![0, 1, 2].includes(state.selectedIndex!)
        || (state.selectedIndex !== 0 && !state.saved[state.selectedIndex as 1 | 2]))) throw new Error("Invalid finalized crazy gacha state")
    if (state.status === "pending" && state.selectedIndex !== undefined) throw new Error("Invalid pending crazy gacha selection")
    return state
}

export function getLatestCrazyGachaStateSync(playerId: number): StoredCrazyGachaState | null {
    const row = getDb().prepare(`SELECT session_number,state_json FROM players_crazy_gacha
        WHERE player_id=? AND gacha_id=? ORDER BY session_number DESC LIMIT 1`).get(playerId, CRAZY_GACHA_ID) as
        { session_number: number; state_json: string } | undefined
    return row ? { sessionNumber: row.session_number, state: parseCrazyGachaState(row.state_json) } : null
}

export function writeCrazyGachaStateSync(playerId: number, sessionNumber: number, state: CrazyGachaState): void {
    const serialized = JSON.stringify(state)
    parseCrazyGachaState(serialized)
    const result = getDb().prepare(`INSERT INTO players_crazy_gacha(player_id,gacha_id,session_number,state_json) VALUES(?,?,?,?)
        ON CONFLICT(player_id,gacha_id,session_number) DO UPDATE SET state_json=excluded.state_json
        WHERE json_extract(players_crazy_gacha.state_json,'$.status')='pending'`)
        .run(playerId, CRAZY_GACHA_ID, sessionNumber, serialized)
    if (result.changes !== 1) throw new Error("Finalized crazy gacha business state is immutable")
}

/** Call only inside the caller's persistence transaction. Older imported pending
 * state cannot undo a completed paid UUID already recorded on this server. */
export function reconcileCrazyGachaCompletionSync(playerId: number): StoredCrazyGachaState | null {
    const current = getLatestCrazyGachaStateSync(playerId)
    if (!current || current.state.status !== "pending") return current
    const receipt = getPlayerOperationReceiptSync<{ version: number; state: CrazyGachaState }>(
        playerId, completionOperation, current.state.sessionId,
    )
    if (!receipt) return current
    const state = parseCrazyGachaState(JSON.stringify(receipt.response.state))
    if (receipt.response.version !== 1 || state.status !== "finalized" || state.sessionId !== current.state.sessionId) {
        throw new Error("Invalid crazy gacha completion receipt")
    }
    writeCrazyGachaStateSync(playerId, current.sessionNumber, state)
    return { sessionNumber: current.sessionNumber, state }
}

export function recordCrazyGachaCompletionSync(playerId: number, state: CrazyGachaState, itemIds: number[] = []): void {
    if (state.status !== "finalized") throw new Error("Crazy gacha completion requires finalized state")
    insertPlayerOperationReceiptSync({ playerId, operation: completionOperation, requestKey: state.sessionId,
        response: { version: 1, state, itemIds: [...new Set(itemIds)] } })
}

export function getCrazyGachaCompletionItemIdsSync(playerId: number, sessionId: string): number[] {
    const receipt = getPlayerOperationReceiptSync<{ itemIds?: number[] }>(playerId, completionOperation, sessionId)
    const ids = receipt?.response.itemIds ?? []
    if (!Array.isArray(ids) || ids.some(id => !positiveInteger(id))) throw new Error("Invalid crazy gacha completion items")
    return ids
}

export function crazyGachaDrawCount(playerId: number): number {
    const current = getLatestCrazyGachaStateSync(playerId)
    return current?.state.status === "pending" ? current.state.drawCount : 0
}

export function getCrazyGachaRecoverySync(playerId: number): {
    crazy_gacha_result_list: Record<string, number[]>; last_crazy_gacha_draw_result: CrazyGachaDraw[]
} {
    const current = getLatestCrazyGachaStateSync(playerId)
    const slots: Record<string, number[]> = { "0": [], "1": [], "2": [] }
    if (!current || current.state.status !== "pending") return { crazy_gacha_result_list: slots, last_crazy_gacha_draw_result: [] }
    slots["0"] = current.state.latest.draw.map(draw => draw.character_id)
    for (const index of ["1", "2"] as const) slots[index] = current.state.saved[index]?.draw.map(draw => draw.character_id) ?? []
    return { crazy_gacha_result_list: slots, last_crazy_gacha_draw_result: current.state.latest.draw }
}
