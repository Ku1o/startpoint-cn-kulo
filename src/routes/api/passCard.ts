import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify"
import { resolvePlayerIdSync } from "../../data/activeAccount"
import { getPlayerMailCountSync } from "../../data/domains/mail"
import {
    getPlayerPassCardRewardRecordsSync,
    getPlayerPassCardStateSync,
    setPlayerPassCardRewardReceivedSync,
} from "../../data/domains/pass-card"
import { getPlayerSync } from "../../data/domains/player"
import { getSession } from "../../data/domains/session"
import { MissionRewardGranter } from "../../lib/mission/grants"
import { getPassCardEventDefinition, getPassCardRewardDefinition } from "../../lib/pass-card"
import { generateDataHeaders, getServerTime, getServerDate } from "../../utils"
import { runPersistenceTransaction } from "../../lib/persistence-coordinator"
import { isPassContentAvailable } from "../../lib/content-economy-operations"
import { getDb } from "../../data/db"
import { getMissionMasterDefinitions } from "../../lib/mission/master-data"

interface PassCardBody {
    viewer_id: number
    pass_card_id: number
}

interface PassCardReceiveBody extends PassCardBody {
    all_receive?: number[]
    reward1_receive?: number[]
    reward2_receive?: number[]
}

interface RequestedTracks {
    receive1: boolean
    receive2: boolean
}

function isPassCardBody(body: unknown): body is PassCardBody {
    return typeof body === "object" && body !== null && !Array.isArray(body)
}

async function resolvePlayerId(body: PassCardBody, reply: FastifyReply, requirePassId = true): Promise<number | undefined> {
    if (!Number.isSafeInteger(body.viewer_id) || (requirePassId && !Number.isSafeInteger(body.pass_card_id))) {
        reply.status(400).send({ error: "Bad Request", message: "Invalid request body." })
        return undefined
    }
    const session = await getSession(String(body.viewer_id))
    const playerId = session ? resolvePlayerIdSync(session.accountId) : null
    if (playerId === null || playerId === undefined) {
        reply.status(400).send({ error: "Bad Request", message: "Invalid viewer id." })
        return undefined
    }
    return playerId
}

/** Read earned state only; a zero-point login baseline is not an entitlement. */
function retainedPassIds(playerId: number): Set<number> {
    const db = getDb()
    const ids = new Set((db.prepare(`
        SELECT event_id FROM players_pass_cards WHERE player_id = ? AND (point > 0 OR is_buy = 1)
    `).all(playerId) as { event_id: number }[]).map(row => row.event_id))
    const receipts = db.prepare(`SELECT event_id, reward_id FROM players_pass_card_rewards
        WHERE player_id = ? AND (is_received_1 = 1 OR is_received_2 = 1)
    `).all(playerId) as { event_id: number, reward_id: number }[]
    for (const row of receipts) {
        if (getPassCardRewardDefinition(row.reward_id)?.eventId === row.event_id) ids.add(row.event_id)
    }
    const progressed = db.prepare(`
        SELECT category, id FROM players_category_missions
            WHERE player_id = ? AND category IN (6, 7, 8) AND progress > 0
        UNION SELECT category, mission_id AS id FROM players_category_mission_stages
            WHERE player_id = ? AND category IN (6, 7, 8) AND status = 1
    `).all(playerId, playerId) as { category: number, id: number }[]
    const events = new Map<number, Map<number, number>>()
    for (const category of [6, 7, 8]) events.set(category, new Map(
        getMissionMasterDefinitions(category).flatMap(definition =>
            definition.eventId === undefined ? [] : [[definition.missionId, definition.eventId]])))
    for (const row of progressed) {
        const eventId = events.get(row.category)?.get(row.id)
        if (eventId !== undefined) ids.add(eventId)
    }
    return ids
}

function responseRecords(playerId: number, eventId: number) {
    return getPlayerPassCardRewardRecordsSync(playerId, eventId).map(record => ({
        reward_id: record.rewardId,
        is_received_1: record.isReceived1,
        is_received_2: record.isReceived2,
    }))
}

function collectRequestedTracks(body: PassCardReceiveBody): Map<number, RequestedTracks> | undefined {
    const result = new Map<number, RequestedTracks>()
    const add = (values: unknown, receive1: boolean, receive2: boolean): boolean => {
        if (!Array.isArray(values)) return false
        for (const rewardId of values) {
            if (!Number.isSafeInteger(rewardId)) return false
            const tracks = result.get(rewardId) ?? { receive1: false, receive2: false }
            tracks.receive1 ||= receive1
            tracks.receive2 ||= receive2
            result.set(rewardId, tracks)
        }
        return true
    }
    if (!add(body.all_receive ?? [], true, true)
        || !add(body.reward1_receive ?? [], true, false)
        || !add(body.reward2_receive ?? [], false, true)) return undefined
    return result
}

export default async function passCardRoutes(fastify: FastifyInstance): Promise<void> {
    fastify.post("/get_retained_pass_cards", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body
        if (!isPassCardBody(body)) {
            return reply.status(400).send({ error: "Bad Request", message: "Invalid request body." })
        }
        const playerId = await resolvePlayerId(body, reply, false)
        if (playerId === undefined) return reply
        const now = getServerDate()
        const cards = [...retainedPassIds(playerId)].sort((left, right) => left - right).flatMap(eventId => {
            const event = getPassCardEventDefinition(eventId)
            if (!event || !isPassContentAvailable(event, "claim", now)) return []
            const state = getPlayerPassCardStateSync(playerId, eventId)
            return [{ pass_card_id: eventId, point: state.point, is_buy: state.isBuy,
                all_received_record: responseRecords(playerId, eventId) }]
        })
        reply.header("content-type", "application/x-msgpack")
        return reply.send({ data_headers: generateDataHeaders({ viewer_id: body.viewer_id }),
            data: { retained_pass_card_list: cards } })
    })

    fastify.post("/get_pass_card", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body
        if (!isPassCardBody(body)) {
            return reply.status(400).send({ error: "Bad Request", message: "Invalid request body." })
        }
        const playerId = await resolvePlayerId(body, reply)
        if (playerId === undefined) return reply
        const event = getPassCardEventDefinition(body.pass_card_id)
        const now = getServerDate()
        if (!event || (!isPassContentAvailable(event, "visible", now)
            && !(isPassContentAvailable(event, "claim", now) && retainedPassIds(playerId).has(body.pass_card_id)))) {
            return reply.status(400).send({ error: "Bad Request", message: "Unknown pass card." })
        }
        const state = getPlayerPassCardStateSync(playerId, body.pass_card_id)
        reply.header("content-type", "application/x-msgpack")
        return reply.send({
            data_headers: generateDataHeaders({ viewer_id: body.viewer_id }),
            data: {
                point: state.point,
                is_buy: state.isBuy,
                all_received_record: responseRecords(playerId, body.pass_card_id),
            },
        })
    })

    fastify.post("/receive_all", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body
        if (!isPassCardBody(body)) {
            return reply.status(400).send({ error: "Bad Request", message: "Invalid request body." })
        }
        const playerId = await resolvePlayerId(body, reply)
        if (playerId === undefined) return reply
        const event = getPassCardEventDefinition(body.pass_card_id)
        const requested = collectRequestedTracks(body as PassCardReceiveBody)
        if (!event
            || !requested || requested.size === 0) {
            return reply.status(400).send({ error: "Bad Request", message: "Invalid pass reward request." })
        }

        const pendingTracks = (records: ReturnType<typeof getPlayerPassCardRewardRecordsSync>) => {
            const received = new Map(records.map(record => [record.rewardId, record]))
            return [...requested].some(([rewardId, tracks]) =>
                (tracks.receive1 && received.get(rewardId)?.isReceived1 !== 1)
                || (tracks.receive2 && received.get(rewardId)?.isReceived2 !== 1))
        }
        if ((requested.size === 0 || pendingTracks(getPlayerPassCardRewardRecordsSync(playerId, body.pass_card_id)))
            && !isPassContentAvailable(event, "claim", new Date(getServerTime() * 1000))) {
            return reply.status(400).send({ error: "Bad Request", message: "Pass rewards are closed." })
        }

        const result = await runPersistenceTransaction({
            domain: "event", playerId, operation: "receive_pass_card",
        }, () => {
            const event = getPassCardEventDefinition(body.pass_card_id)
            if (!event) {
                return { ok: false as const, message: "Invalid pass reward request." }
            }
            const state = getPlayerPassCardStateSync(playerId, body.pass_card_id)
            if (!isPassContentAvailable(event, "enter", getServerDate())
                && !retainedPassIds(playerId).has(body.pass_card_id)) {
                return { ok: false as const, message: "No retained pass entitlement." }
            }
            const currentLevel = Math.floor(state.point / event.levelThreshold)
            const definitions = new Map<number, ReturnType<typeof getPassCardRewardDefinition>>()
            for (const [rewardId, tracks] of requested) {
                const definition = getPassCardRewardDefinition(rewardId)
                if (!definition
                    || definition.eventId !== body.pass_card_id
                    || definition.level > currentLevel
                    || (tracks.receive2 && !state.isBuy)) {
                    return { ok: false as const, message: "Pass reward is not available." }
                }
                definitions.set(rewardId, definition)
            }

            const records = getPlayerPassCardRewardRecordsSync(playerId, body.pass_card_id)
            if ((requested.size === 0 || pendingTracks(records)) && !isPassContentAvailable(event, "claim", getServerDate())) {
                return { ok: false as const, message: "Pass rewards are closed." }
            }

            const player = getPlayerSync(playerId)
            if (!player) throw new Error(`Player ${playerId} not found during pass reward settlement.`)
            const granter = new MissionRewardGranter(playerId, player)
            const received = new Map(
                records
                    .map(record => [record.rewardId, record]),
            )
            for (const [rewardId, tracks] of requested) {
                const definition = definitions.get(rewardId)!
                const current = received.get(rewardId)
                const grant1 = tracks.receive1 && current?.isReceived1 !== 1
                const grant2 = tracks.receive2 && current?.isReceived2 !== 1
                if (grant1) granter.grant([definition.reward1])
                if (grant2) granter.grant([definition.reward2])
                if (grant1 || grant2) {
                    setPlayerPassCardRewardReceivedSync(
                        playerId,
                        body.pass_card_id,
                        rewardId,
                        grant1,
                        grant2,
                    )
                }
            }
            granter.persistPlayer()
            return { ok: true as const, granter }
        })
        if (!result.ok) return reply.status(400).send({ error: "Bad Request", message: result.message })
        const granter = result.granter

        reply.header("content-type", "application/x-msgpack")
        return reply.send({
            data_headers: generateDataHeaders({ viewer_id: body.viewer_id }),
            data: {
                all_received_record: responseRecords(playerId, body.pass_card_id),
                item_list: granter.itemList,
                character_list: granter.characterList,
                equipment_list: granter.equipmentList,
                degree_list: granter.degreeList.map(degreeId => ({
                    viewer_id: body.viewer_id,
                    degree_id: degreeId,
                })),
                ...(granter.hasPlayerChanges() ? { user_info: granter.getUserInfo() } : {}),
                mail_arrived: getPlayerMailCountSync(playerId, true) > 0,
            },
        })
    })
}
