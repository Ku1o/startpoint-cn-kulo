import { createHash, randomUUID } from "crypto"
import { getCharacterDataSync, getConfigSync, getGachaSync } from "./assets"
import { contentDecision } from "./content-operations"
import { runPersistenceTransaction } from "./persistence-coordinator"
import { commitPlannedCharacterGachaMovies, drawGachaWithMetadataSync, planCharacterGachaMovies, rewardPlayerGachaDrawResultSync } from "./gacha"
import { CRAZY_GACHA_ID, CRAZY_GACHA_TICKET_ID, CrazyGachaCandidate, CrazyGachaState, StoredCrazyGachaState, getCrazyGachaRecoverySync, getCrazyGachaCompletionItemIdsSync, reconcileCrazyGachaCompletionSync, recordCrazyGachaCompletionSync, writeCrazyGachaStateSync } from "../data/domains/crazy_gacha"
import { getPlayerItemSync, getPlayerItemsByIdsSync, updatePlayerItemSync } from "../data/domains/item"
import { getPlayerCharactersByIdsSync } from "../data/domains/character"
import { getPlayerCharacterAwakeUnlocksByCharacterIdsSync } from "../data/domains/character_awake"
import { clientSerializeDate, serializeBondTokenStatuses } from "../data/utils"
import { getAccountFromPlayerIdSync, getPlayerSync } from "../data/domains/player"
import { getDb } from "../data/db"
import { getPlayerOperationReceiptSync, insertPlayerOperationReceiptSync } from "../data/domains/player-operation-receipt"
import { readGameplayMutationIdentitySync } from "./gameplay-request-identity"
import { getPlayerOptionSync } from "../data/domains/option"
import { getPlayerGachaInfoSync, insertPlayerGachaInfoSync, updatePlayerGachaInfoSync } from "../data/domains/gacha"
import { insertReceiveHistorySync, MailType } from "../data/domains/mail"
import { incrementActiveMissionGachaCharacterCountSync } from "../data/domains/active_mission_counters"
import { reconcileAwakeUnlockCharacterList, refreshAwakeUnlockCharacterList, settleDegreeMissionResponse } from "./mission"
import type { CharacterGacha } from "./types"

export type CrazyGachaOutcome = { ok: true; data: Record<string, any> } | { ok: false; message: string }
const rejected = (message: string): CrazyGachaOutcome => ({ ok: false, message })
export interface CrazyGachaMutationContext {
    headerToken: unknown
    body: { viewer_id?: unknown; api_count?: unknown }
    accountId: number
}
type CrazyOperation = "draw" | "save" | "select"
interface CrazyRequestReceipt {
    version: 1; operation: CrazyOperation; payloadHash: string; sessionId: string; drawCount: number
}
interface CrazyRequest {
    requestKey: string; operation: CrazyOperation; payloadHash: string; previous: CrazyRequestReceipt | null
}
const requestOperation = "crazy_gacha_request"
function readRequest(playerId: number, context: CrazyGachaMutationContext, operation: CrazyOperation, index?: number): CrazyRequest | null {
    // This runs after acquiring the business writer and its SQLite transaction:
    // a queued signup can supersede a nonce before this request actually writes.
    if (getAccountFromPlayerIdSync(playerId)?.id !== context.accountId) return null
    const identity = readGameplayMutationIdentitySync(getDb(), context.headerToken, context.body, context.accountId)
    if (!identity) return null
    const payloadHash = createHash("sha256").update(JSON.stringify(operation === "draw"
        ? { operation, gachaId: 100, paymentType: 3, type: 14, numberOfExec: 1 }
        : { operation, gachaId: 100, index })).digest("hex")
    const previous = getPlayerOperationReceiptSync<CrazyRequestReceipt>(playerId, requestOperation, identity.requestKey)?.response ?? null
    if (previous && (previous.version !== 1 || previous.operation !== operation || previous.payloadHash !== payloadHash)) return null
    if (!previous && !identity.isCurrent) return null
    return { requestKey: identity.requestKey, operation, payloadHash, previous }
}
function samePaidSession(request: CrazyRequest, current: StoredCrazyGachaState | null): boolean {
    return !!current && request.previous?.sessionId === current.state.sessionId
}
function recordRequest(playerId: number, request: CrazyRequest, state: CrazyGachaState): void {
    insertPlayerOperationReceiptSync({ playerId, operation: requestOperation, requestKey: request.requestKey,
        response: { version: 1, operation: request.operation, payloadHash: request.payloadHash,
            sessionId: state.sessionId, drawCount: state.drawCount } satisfies CrazyRequestReceipt })
}

export function isCrazyGachaExecRequest(gachaId: number, paymentType: number, execType: number, numberOfExec: number): boolean {
    return gachaId === CRAZY_GACHA_ID && paymentType === 3 && execType === 14 && numberOfExec === 1
}
function definition(): CharacterGacha | null {
    const gacha = getGachaSync(CRAZY_GACHA_ID)
    return gacha?.type === 0 && gacha.pageKind === 5 ? gacha as CharacterGacha : null
}
function allowed(action: "enter" | "claim", gacha: CharacterGacha): boolean {
    const controlled = contentDecision("gacha", CRAZY_GACHA_ID, action, Date.now())
    if (controlled !== null) return controlled
    if (action === "claim" || gacha.enforceAvailabilityWindow !== true) return true
    const parse = (value: string) => Date.parse(value.replace(" ", "T") + "+08:00")
    const now = Date.now(), start = parse(gacha.startDate), end = parse(gacha.endDate)
    return Number.isFinite(start) && Number.isFinite(end) && start <= now && now <= end
}
function gachaInfo(playerId: number, drawCount: number) {
    const old = getPlayerGachaInfoSync(playerId, CRAZY_GACHA_ID)
    return { gacha_id: CRAZY_GACHA_ID, is_account_first: old?.isAccountFirst ?? true,
        is_daily_first: old?.isDailyFirst ?? true, gacha_exchange_point: old?.gachaExchangePoint ?? 0, crazy_draw_count: drawCount }
}
function common(playerId: number, drawCount: number): Record<string, any> {
    const player = getPlayerSync(playerId)
    if (!player) throw new Error("Crazy gacha player is missing")
    return { ...getCrazyGachaRecoverySync(playerId), gacha_info_list: [gachaInfo(playerId, drawCount)],
        user_info: { free_vmoney: player.freeVmoney, vmoney: player.vmoney }, character_list: [], item_list: {} }
}
function selectedAcknowledgement(playerId: number, state: CrazyGachaState): Record<string, any> {
    const selected = state.selectedIndex === 0 ? state.latest : state.saved[state.selectedIndex as 1 | 2]!
    const ids = selected.draw.map(draw => draw.character_id)
    // A lost first response must recover authoritative current inventories,
    // rather than replaying stale stack/item amounts or granting the group again.
    const characters = Object.entries(getPlayerCharactersByIdsSync(playerId, ids)).map(([id, character]) => ({
        character_id: Number(id), entry_count: character.entryCount, stack: character.stack,
        evolution_level: character.evolutionLevel, over_limit_step: character.overLimitStep,
        protection: character.protection, exp: character.exp, exp_total: character.exp,
        create_time: clientSerializeDate(character.joinTime), join_time: clientSerializeDate(character.joinTime),
        update_time: clientSerializeDate(character.updateTime), mana_board_index: character.manaBoardIndex,
        bond_token_list: serializeBondTokenStatuses(character.bondTokenList),
        ...(character.exBoost ? { ex_boost: { status_id: character.exBoost.statusId, ability_id_list: character.exBoost.abilityIdList } } : {}),
        ...(character.illustrationSettings ? { illustration_settings: character.illustrationSettings } : {}),
    }))
    return { ...common(playerId, 0), character_list: refreshAwakeUnlockCharacterList(playerId, characters,
        getPlayerCharacterAwakeUnlocksByCharacterIdsSync(playerId, ids), ids),
        item_list: getPlayerItemsByIdsSync(playerId, getCrazyGachaCompletionItemIdsSync(playerId, state.sessionId)) }
}
function candidate(playerId: number, gacha: CharacterGacha): CrazyGachaCandidate {
    const metadata = drawGachaWithMetadataSync(gacha, 10), ids = metadata.map(draw => draw.id)
    if (ids.length !== 10 || ids.some(id => getCharacterDataSync(id) === null)) throw new Error("Invalid crazy gacha character definition")
    const movies = planCharacterGachaMovies(gacha, ids, {
        skipNoRarityUpMovie: getPlayerOptionSync(playerId, "gacha_play_no_rarity_up_movie", false), flushPrevious: false,
    })
    return { metadata, movies, draw: movies.map(movie => ({ character_id: movie.characterId,
        movie_id: movie.movieId, seed: movie.seed, entry_count: 1, ex_boost_item: null })) }
}

export async function executeCrazyGacha(playerId: number, context: CrazyGachaMutationContext): Promise<CrazyGachaOutcome> {
    let committedMovies: CrazyGachaCandidate["movies"] | undefined
    return runPersistenceTransaction({ domain: "gacha", playerId, operation: "crazy_draw" }, () => {
        const request = readRequest(playerId, context, "draw")
        if (!request) return rejected("Crazy gacha request identity is invalid or superseded.")
        const gacha = definition()
        if (!gacha) return rejected("Crazy gacha definition is unavailable.")
        const old = reconcileCrazyGachaCompletionSync(playerId), pending = old?.state.status === "pending"
        if (request.previous) {
            if (!samePaidSession(request, old) || !pending || request.previous.drawCount !== old.state.drawCount) {
                return rejected("Crazy gacha request belongs to an earlier candidate or paid session.")
            }
            return { ok: true as const, data: { ...common(playerId, old.state.drawCount), draw: old.state.latest.draw,
                item_list: { [CRAZY_GACHA_TICKET_ID]: getPlayerItemSync(playerId, CRAZY_GACHA_TICKET_ID) ?? 0 } } }
        }
        if (!allowed(pending ? "claim" : "enter", gacha)) return rejected("Crazy gacha is not available.")
        const ticketCount = getPlayerItemSync(playerId, CRAZY_GACHA_TICKET_ID) ?? 0
        if (!pending && ticketCount < 1) return rejected("A Crazy Gacha ticket is required.")
        if (pending && old.state.drawCount >= old.state.maxDrawCount) return rejected("Crazy gacha candidate limit reached.")
        const max = pending ? old.state.maxDrawCount : getConfigSync().gacha_crazy_ten_max_count
        if (!Number.isSafeInteger(max) || max < 1) return rejected("Crazy gacha limit is unavailable.")
        const next = candidate(playerId, gacha)
        const state: CrazyGachaState = pending ? { ...old.state, drawCount: old.state.drawCount + 1, latest: next } : {
            version: 1, sessionId: randomUUID(), status: "pending", drawCount: 1, maxDrawCount: max, latest: next, saved: {},
        }
        if (!pending) updatePlayerItemSync(playerId, CRAZY_GACHA_TICKET_ID, ticketCount - 1)
        writeCrazyGachaStateSync(playerId, pending ? old.sessionNumber : (old?.sessionNumber ?? 0) + 1, state)
        recordRequest(playerId, request, state)
        committedMovies = next.movies
        return { ok: true as const, data: { ...common(playerId, state.drawCount), draw: next.draw,
            item_list: pending ? {} : { [CRAZY_GACHA_TICKET_ID]: ticketCount - 1 } } }
    }, { afterCommit: result => { if (result.ok && committedMovies) commitPlannedCharacterGachaMovies(committedMovies) } })
}

export async function saveCrazyGacha(playerId: number, index: number, context: CrazyGachaMutationContext): Promise<CrazyGachaOutcome> {
    if (index !== 1 && index !== 2) return rejected("Invalid crazy gacha backup index.")
    return runPersistenceTransaction({ domain: "gacha", playerId, operation: "crazy_save" }, () => {
        const request = readRequest(playerId, context, "save", index)
        if (!request) return rejected("Crazy gacha request identity is invalid or superseded.")
        const gacha = definition(), current = reconcileCrazyGachaCompletionSync(playerId)
        if (request.previous) return samePaidSession(request, current)
            ? { ok: true as const, data: common(playerId, current!.state.status === "pending" ? current!.state.drawCount : 0) }
            : rejected("Crazy gacha request belongs to an earlier paid session.")
        if (!gacha || !current || current.state.status !== "pending") return rejected("No unfinished crazy gacha session.")
        if (!allowed("claim", gacha)) return rejected("Crazy gacha selection is not available.")
        if (current.state.saved[index as 1 | 2]) return rejected("Crazy gacha backup cannot be replaced.")
        current.state.saved[index as 1 | 2] = current.state.latest
        writeCrazyGachaStateSync(playerId, current.sessionNumber, current.state)
        recordRequest(playerId, request, current.state)
        return { ok: true as const, data: common(playerId, current.state.drawCount) }
    })
}

export async function selectCrazyGacha(playerId: number, viewerId: number, index: number, context: CrazyGachaMutationContext): Promise<CrazyGachaOutcome> {
    if (!Number.isSafeInteger(index) || ![0, 1, 2].includes(index)) return rejected("Invalid crazy gacha selection index.")
    return runPersistenceTransaction({ domain: "gacha", playerId, operation: "crazy_select" }, () => {
        const request = readRequest(playerId, context, "select", index)
        if (!request) return rejected("Crazy gacha request identity is invalid or superseded.")
        const gacha = definition(), current = reconcileCrazyGachaCompletionSync(playerId)
        if (!gacha || !current) return rejected("No unfinished crazy gacha session.")
        if (request.previous && (!samePaidSession(request, current)
            || request.previous.drawCount !== current.state.drawCount || current.state.status !== "finalized")) {
            return rejected("Crazy gacha request belongs to an earlier paid session.")
        }
        // Finalized business state also survives archives; a replay never re-grants its group.
        if (current.state.status === "finalized") {
            if (current.state.selectedIndex !== index) return rejected("Crazy gacha selection has already been finalized.")
            if (!request.previous) recordRequest(playerId, request, current.state)
            return { ok: true as const, data: selectedAcknowledgement(playerId, current.state) }
        }
        if (!allowed("claim", gacha)) return rejected("Crazy gacha selection is not available.")
        const selected = index === 0 ? current.state.latest : current.state.saved[index as 1 | 2]
        if (!selected) return rejected("Crazy gacha selection slot is empty.")
        const ids = selected.draw.map(draw => draw.character_id)
        if (ids.length !== 10 || ids.some(id => getCharacterDataSync(id) === null)) throw new Error("Crazy gacha selected character is unavailable")
        const reward = rewardPlayerGachaDrawResultSync(playerId, gacha, ids, selected.metadata, selected.movies, false)
        if (reward.draw.length !== 10) throw new Error("Crazy gacha selected group was not fully granted")
        for (const id of ids) insertReceiveHistorySync(playerId, { type: MailType.CHARACTER, type_id: id, number: 1 })
        const oldInfo = getPlayerGachaInfoSync(playerId, CRAZY_GACHA_ID)
        const newInfo = { gachaId: CRAZY_GACHA_ID, isAccountFirst: false, isDailyFirst: false, gachaExchangePoint: (oldInfo?.gachaExchangePoint ?? 0) + 10 }
        if (oldInfo) updatePlayerGachaInfoSync(playerId, newInfo)
        else insertPlayerGachaInfoSync(playerId, newInfo)
        incrementActiveMissionGachaCharacterCountSync(playerId, 10)
        current.state.status = "finalized"
        current.state.selectedIndex = index
        writeCrazyGachaStateSync(playerId, current.sessionNumber, current.state)
        recordCrazyGachaCompletionSync(playerId, current.state, Object.keys(reward.items).map(Number))
        recordRequest(playerId, request, current.state)
        const data = { ...common(playerId, 0), character_list: reconcileAwakeUnlockCharacterList(playerId, reward.characters as Record<string, unknown>[]), item_list: reward.items }
        settleDegreeMissionResponse(playerId, viewerId, data, undefined, [4])
        return { ok: true as const, data }
    })
}
