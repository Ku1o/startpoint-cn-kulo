import type { FastifyReply } from "fastify"
import type { Player } from "../../data/types"
import type { MultiRoom } from "../../lib/types/multi"
import type { MultiAbortBody, MultiFinishBody, MultiStartBody } from "../types"
import { getPlayerActiveQuestSync } from "../../data/domains/quest_active"
import { FiveBossGauntletRunError, backfillMissingFinalizeSync, getFiveBossRunByClientSync } from "../../data/domains/fiveBossGauntletRun"
import { getPlayerItemSync } from "../../data/domains/item"
import { getPlayerSync, updatePlayerSync } from "../../data/domains/player"
import type { RewardPlayerCharacterExpResult } from "../../lib/types/character"
import { generateDataHeaders, getServerTime, realToVirtual } from "../../utils"
import { activeQuests } from "../../routes/api/singleBattleQuest"
import { getRoom, disbandRoom } from "../room/manager"
import { sessionManager } from "../state/SessionManager"
import {
    abortFiveBossBattle,
    finishFiveBossBattle,
    FiveBossBattleRuntimeError,
    startFiveBossBattle,
    type FinishFiveBossBattleResult,
} from "../five-boss/battle-runtime"
import { FIVE_BOSS_GAUNTLET, isFiveBossGauntletQuest } from "../five-boss/contract"
import { buildFiveBossAdditionalRewardDrops } from "../five-boss/rewards"
import { abandonFiveBossSoloForMultiSync } from "../five-boss/solo-runtime"
import { getDb } from "../../data/db"
import { measureSettlementPhase, measureSettlementPhaseAsync } from "../../lib/settlement-performance"

/** Small structured evidence, without logging tokens, party data or the full request. */
export function logFiveBossRequestFailure(operation: "start" | "finish" | "abort", body: MultiStartBody | MultiFinishBody | MultiAbortBody,
    playerId: number, error: unknown): void {
    const run = getFiveBossRunByClientSync({ playerId, clientPlayId: body.play_id })
    const member = run ? getDb().prepare(`SELECT started_at, aborted_at, level_next_at, finalized_at
        FROM five_boss_gauntlet_members WHERE run_id = ? AND player_id = ?`).get(run.runId, playerId) : null
    const active = getPlayerActiveQuestSync(playerId)
    console.warn(`[FIVE-BOSS-REJECT] ${JSON.stringify({ operation, player: playerId, play: body.play_id,
        category: body.category, quest: body.quest_id, run: run?.runId, room: run?.roomNumber,
        status: run?.status, code: (error as { code?: string })?.code, message: (error as Error)?.message,
        proof: member, active: active ? { play: active.playId, multi: active.isMulti, room: active.roomNumber } : null })}`)
}


type FollowInfoBuilder = (
    viewerId: number,
    mateResults: Array<{ viewer_id?: number }>,
    fallbackMateIds?: number[],
) => Promise<unknown[]>


export function isFiveBossBattleRequestError(error: unknown): boolean {
    return error instanceof FiveBossBattleRuntimeError
        || error instanceof FiveBossGauntletRunError
}


export function shouldHandleFiveBossStart(body: MultiStartBody): boolean {
    const room = body.room_number ? getRoom(body.room_number) : undefined
    return isFiveBossGauntletQuest(body.category, body.quest_id)
        || !!room && isFiveBossGauntletQuest(room.category, room.quest_id)
}


export function shouldHandleFiveBossMemberRequest(
    body: Pick<MultiFinishBody | MultiAbortBody, "category" | "quest_id" | "play_id">,
    playerId: number,
): boolean {
    if (isFiveBossGauntletQuest(body.category, body.quest_id)) return true
    if (getFiveBossRunByClientSync({ playerId, clientPlayId: body.play_id })) return true
    const memory = activeQuests[playerId]
    if (memory && isFiveBossGauntletQuest(memory.category, memory.questId)) return true
    const persistent = getPlayerActiveQuestSync(playerId)
    return persistent !== null
        && isFiveBossGauntletQuest(persistent.category, persistent.questId)
}


function clearMatchingMemoryActive(playerId: number, playId: string): void {
    const active = activeQuests[playerId]
    if (
        active?.playId === playId
        && isFiveBossGauntletQuest(active.category, active.questId)
    ) {
        delete activeQuests[playerId]
    }
}


function terminalRoomTransition(
    roomNumber: string,
    runId: string,
    runStatus: "active" | "settled" | "aborted",
): void {
    if (runStatus === "active") return
    const room = getRoom(roomNumber)
    if (
        !room
        || !isFiveBossGauntletQuest(room.category, room.quest_id)
        || room.five_boss_runtime?.runId !== runId
    ) {
        return
    }

    sessionManager.clearBattleExpectedCount(roomNumber)
    if (runStatus === "settled") {
        delete room.five_boss_runtime
        // 结算后不再把房间退回 raising_state=1 复用,而是直接解散:
        // V7 客户端补丁 five-boss-random-map 的选图种子 = 房间号,同一房间再战
        // 会抽到同一套变体;解散逼房主重建房间 = 新房号 = 新一轮随机。
        // 代价是结算页点「再战」会提示房间已解散,回到关卡页重建(作者接受随机性优先)。
        console.log(`[MULTI] five-boss settled: disbanding room ${roomNumber} so the next run rerolls its map seed`)
        disbandRoom(roomNumber)
        return
    }
    disbandRoom(roomNumber)
}


/**
 * CN 客户端的 multi finish / abort 请求体**不带 room_number**(官方
 * BattleQuestFinishRealRemote / QuestAbortRealRemote 都没有这个字段),原生多人路径
 * 一直是靠服务端 activeQuests 记住房号。五重 runtime 的冻结契约要求 requestRoomNumber
 * 非空,真机首战(2026-09-04)就因此在结算时连吃 6 个 H400。这里按
 * 请求体 → 内存 activeQuests → 持久化 players_active_quests 的顺序补房号;
 * 全都没有才让 runtime 用原来的 invalid_argument 拒绝。
 */
function resolveFiveBossRoomNumber(bodyRoomNumber: unknown, playerId: number, playId: string): string {
    if (typeof bodyRoomNumber === "string" && bodyRoomNumber.length > 0) return bodyRoomNumber
    const run = getFiveBossRunByClientSync({ playerId, clientPlayId: playId })
    if (run) return run.roomNumber
    const memory = activeQuests[playerId]
    if (memory && isFiveBossGauntletQuest(memory.category, memory.questId) && memory.roomNumber) {
        return memory.roomNumber
    }
    const persistent = getPlayerActiveQuestSync(playerId)
    if (
        persistent
        && isFiveBossGauntletQuest(persistent.category, persistent.questId)
        && persistent.roomNumber
    ) {
        return persistent.roomNumber
    }
    return ""
}


/**
 * 上一局没结算干净(客户端半路报错退出、房间早已解散)时,玩家身上还挂着旧的
 * 五重持久化 active quest,新一局 start 会被 runtime 以 active_quest_mismatch 拒绝,
 * 玩家从此进不了五重。开新局前把这条"房间已不存在"的旧局按 abort 收掉。
 * 按整轮身份区别同房号的新旧局；活动房间仍属于旧局时不清理。
 * 此函数与新局 start 同处一个事务，开新局失败时旧局保持原状。
 */
function abandonStaleFiveBossRun(body: MultiStartBody, playerId: number): void {
    const stale = getPlayerActiveQuestSync(playerId)
    if (
        !stale
        || !isFiveBossGauntletQuest(stale.category, stale.questId)
        || stale.playId === body.play_id
    ) {
        return
    }
    try {
        if (!stale.isMulti) {
            if (abandonFiveBossSoloForMultiSync(playerId, stale.playId)) {
                clearMatchingMemoryActive(playerId, stale.playId)
                console.log(`[MULTI] five-boss start: abandoned previous solo player=${playerId} play=${stale.playId}`)
            }
            return
        }
        const oldRun = getFiveBossRunByClientSync({ playerId, clientPlayId: stale.playId })
        const oldRoomNumber = oldRun?.roomNumber ?? stale.roomNumber
        const oldRoom = oldRoomNumber ? getRoom(oldRoomNumber) : undefined
        if (oldRoom && (!oldRun || oldRoom.five_boss_runtime?.runId === oldRun.runId)) return
        if (!oldRun || !oldRoomNumber) {
            console.warn(`[FIVE-BOSS-STALE] missing immutable run player=${playerId} play=${stale.playId}`)
            return
        }
        // Recover only a missing room field from this exact persisted player/play binding.
        if (!stale.roomNumber) {
            getDb().prepare(`UPDATE players_active_quests SET room_number = ?
                WHERE player_id = ? AND play_id = ? AND is_multi = 1 AND (room_number IS NULL OR room_number = '')`)
                .run(oldRoomNumber, playerId, stale.playId)
        }
        const aborted = abortFiveBossBattle({
            playerId,
            clientPlayId: stale.playId,
            requestRoomNumber: oldRoomNumber,
            requestCategory: stale.category,
            requestQuestId: stale.questId,
        })
        clearMatchingMemoryActive(playerId, stale.playId)
        console.log(`[MULTI] five-boss start: abandoned stale run for player ${playerId}`
            + ` room=${stale.roomNumber} play=${stale.playId}`
            + ` status=${aborted.abortStatus}/${aborted.runStatus}`)
    } catch (error) {
        console.warn(`[MULTI] five-boss start: could not abandon stale run for player ${playerId}`
            + ` room=${stale.roomNumber}: ${(error as Error).message}`)
    }
}


function requirePlayer(playerId: number): Player {
    const player = getPlayerSync(playerId)
    if (!player) throw new Error(`five-boss player ${playerId} disappeared`)
    return player
}


function finishItemList(
    result: FinishFiveBossBattleResult,
    playerId: number,
): Record<string, number> {
    if (result.kind !== "success") return {}

    return Object.fromEntries(result.reward.grantedItems.map(item => [
        String(item.itemId),
        getPlayerItemSync(playerId, item.itemId) ?? 0,
    ]))
}


function buildFinishData(
    player: Player,
    body: MultiFinishBody,
    result: FinishFiveBossBattleResult,
    dataHeaders: ReturnType<typeof generateDataHeaders>,
    matePlayerResult: Array<{ viewer_id?: number }>,
    followInfo: unknown[],
    exp: RewardPlayerCharacterExpResult | null,
) {
    return {
        user_info: {
            free_mana: player.freeMana,
            exp_pool: player.expPool,
            exp_pooled_time: getServerTime(player.expPooledTime),
            free_vmoney: player.freeVmoney,
            rank_point: player.rankPoint,
            // getRankDegree 算出来的是玩家 **rank**(高 rank 号如 250),不是称号表 degree 的键;
            // 结算页 MVP 卡会拿 user_info.degree_id 去查 master/degree/degree,查不到就 C8601
            // 「指定的Key不存在 key=250」(真机 2026-09-04)。普通多人/关注列表都用玩家持久化的 degreeId。
            degree_id: player.degreeId || 1,
            stamina: player.stamina,
            stamina_heal_time: realToVirtual(player.staminaHealTime),
            boost_point: player.boostPoint,
            boss_boost_point: player.bossBoostPoint,
        },
        add_exp_list: exp?.add_exp_list ?? [],
        character_list: exp?.character_list ?? [],
        bond_token_status_list: exp?.bond_token_status_list ?? [],
        rewards: {
            overflow_pool_exp: 0,
            converted_pool_exp: 0,
            reward_pool_exp: 0,
            reward_mana: 0,
            field_mana: 0,
        },
        old_high_score: 0,
        joined_character_id_list: [],
        before_rank_point: player.rankPoint,
        clear_rank: result.kind === "success" ? 5 : 0,
        drop_score_reward_ids: [],
        drop_rare_reward_ids: [],
        drop_additional_reward_ids: result.kind === "success"
            ? buildFiveBossAdditionalRewardDrops(result.reward.grantedItems)
            : [],
        drop_periodic_reward_ids: [],
        equipment_list: [],
        category_id: body.category,
        start_time: dataHeaders.servertime,
        is_multi: "multi",
        quest_name: "",
        item_list: finishItemList(result, player.id),
        presigned_quest_category: [],
        mate_player_result: matePlayerResult,
        follow_info: followInfo,
        contribution_score: body.contribution_score ?? 0,
        host_finished: true,
        aborted_play_id: null,
    }
}


export function handleFiveBossStart(
    body: MultiStartBody,
    playerId: number,
    reply: FastifyReply,
) {
    const room = getRoom(body.room_number)
    if (!room) {
        return reply.status(400).send({
            error: "Bad Request",
            message: "Room doesn't exist.",
        })
    }

    // 五重决战不消耗、不结算任何强化点:客户端在"降临讨伐"页签建房时会按官方 boss 战
    // 习惯默认勾上领主强化点(use_boss_boost_point=true),真机实测直接被 runtime 的
    // boost_not_allowed 拒成 H400 进不了战斗(2026-09-04)。这里把两个开关一律当 false
    // 交给 runtime(冻结契约不变:runtime 仍只接受 false),只留一行日志说明被忽略。
    if (body.use_boost_point === true || body.use_boss_boost_point === true) {
        console.log(`[MULTI] five-boss start: ignoring client boost flags`
            + ` viewer=${body.viewer_id} room=${body.room_number}`
            + ` boost=${body.use_boost_point}/${body.use_boss_boost_point}`)
    }
    const previousMemory = activeQuests[playerId]
    let result
    try {
        result = getDb().transaction(() => {
            abandonStaleFiveBossRun(body, playerId)
            return startFiveBossBattle({
                playerId,
                clientPlayId: body.play_id,
                room,
                requestRoomNumber: body.room_number,
                requestCategory: body.category,
                requestQuestId: body.quest_id,
                useBoostPoint: false,
                useBossBoostPoint: false,
                httpIsAutoStartMode: body.is_auto_start_mode,
                matePlayerIds: body.mate_player_ids,
                mateComIds: room.mates.map(mate => mate.com_id),
            })
        }).immediate()
    } catch (error) {
        if (previousMemory) activeQuests[playerId] = previousMemory
        else delete activeQuests[playerId]
        throw error
    }
    activeQuests[playerId] = result.activeQuest
    updatePlayerSync({ id: playerId, partySlot: body.party_id })
    const player = requirePlayer(playerId)

    reply.header("content-type", "application/x-msgpack")
    return reply.status(200).send({
        data_headers: generateDataHeaders({ viewer_id: body.viewer_id }),
        data: {
            is_multi: "multi",
            play_id: body.play_id,
            user_info: { stamina: player.stamina, stamina_heal_time: realToVirtual(player.staminaHealTime) },
            item_list: { [FIVE_BOSS_GAUNTLET.ticketItemId]: getPlayerItemSync(playerId, FIVE_BOSS_GAUNTLET.ticketItemId) ?? 0 },
        },
    })
}


export async function handleFiveBossFinish(
    body: MultiFinishBody,
    playerId: number,
    reply: FastifyReply,
    buildFollowInfo: FollowInfoBuilder,
) {
    const memoryBeforeFinish = activeQuests[playerId]
    const roomNumber = resolveFiveBossRoomNumber(body.room_number, playerId, body.play_id)
    const party = body.statistics?.party ?? body.quest_statistics?.party
    const boundRun = getFiveBossRunByClientSync({ playerId, clientPlayId: body.play_id })
    if (body.is_accomplished === true && isFiveBossGauntletQuest(body.category, body.quest_id)
        && boundRun?.roomNumber === roomNumber) {
        const backfill = backfillMissingFinalizeSync({ playerId, clientPlayId: body.play_id })
        if (backfill.backfilled) {
            console.warn(`[MULTI] five-boss finish: finalize signal never reached the battle channel;`
                + ` backfilled from HTTP finish player=${playerId} run=${backfill.runId} room=${backfill.roomNumber}`)
        }
    }
    const result = measureSettlementPhase("multi", "five_boss_settlement", () => finishFiveBossBattle({
        playerId,
        clientPlayId: body.play_id,
        requestRoomNumber: roomNumber,
        requestCategory: body.category,
        requestQuestId: body.quest_id,
        accomplished: body.is_accomplished as boolean,
        elapsedTimeMs: body.elapsed_time_ms ?? body.battle_time ?? 0,
        highScore: body.score ?? 0,
        leaderCharacterId: party?.characters?.[0]?.id ?? null,
    }))
    clearMatchingMemoryActive(playerId, body.play_id)
    terminalRoomTransition(roomNumber, result.runId, result.runStatus)

    const matePlayerResult = body.mate_player_result ?? []
    const followInfo = await measureSettlementPhaseAsync("multi", "five_boss_follow", () => buildFollowInfo(
        body.viewer_id,
        matePlayerResult,
        memoryBeforeFinish?.matePlayerIds ?? body.mate_player_ids ?? [],
    ))
    const dataHeaders = generateDataHeaders({ viewer_id: body.viewer_id })
    const exp = result.kind === "success" ? result.reward.characterExp : null
    const player = requirePlayer(playerId)
    reply.header("content-type", "application/x-msgpack")
    return reply.status(200).send({
        data_headers: dataHeaders,
        data: buildFinishData(
            player,
            body,
            result,
            dataHeaders,
            matePlayerResult,
            followInfo,
            exp,
        ),
    })
}


export function handleFiveBossAbort(
    body: MultiAbortBody,
    playerId: number,
    reply: FastifyReply,
) {
    const roomNumber = resolveFiveBossRoomNumber(body.room_number, playerId, body.play_id)
    const result = abortFiveBossBattle({
        playerId,
        clientPlayId: body.play_id,
        requestRoomNumber: roomNumber,
        requestCategory: body.category,
        requestQuestId: body.quest_id,
    })
    clearMatchingMemoryActive(playerId, body.play_id)
    terminalRoomTransition(roomNumber, result.runId, result.runStatus)

    const headers = generateDataHeaders({ viewer_id: body.viewer_id })
    reply.header("content-type", "application/x-msgpack")
    return reply.status(200).send({
        data_headers: headers,
        data: {
            user_info: {},
            category_id: body.category,
            is_multi: "multi",
            start_time: headers.servertime,
            quest_name: "",
            aborted_play_id: null,
            unfinished_play_id: null,
            drawn_quest: null,
            party_info: null,
            presigned_url: null,
        },
    })
}
