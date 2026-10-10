import { randomUUID } from "crypto"
import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify"
import { resolvePlayerIdSync } from "../../data/activeAccount"
import { getPlayerCharacterSync } from "../../data/domains/character"
import { getPlayerSync } from "../../data/domains/player"
import { getSession } from "../../data/domains/session"
import { getMultiSpecialExchangeCampaignDefinition } from "../../lib/multi-special-exchange"
import { canParticipateInLounge as canParticipate } from "../../lounge/eligibility"
import {
    createLounge,
    canAttachLoungeViewer,
    getLounge,
    getLoungeByNumber,
    getLoungeOccupancy,
    listLounges,
    matchesLoungeAccess,
    prepareLounge,
    setLoungeShareTypes,
    type LoungeRoom,
} from "../../lounge/state"
import { getDisplayHost } from "../../multi/room/serializer"
import { generateDataHeaders } from "../../utils"
import { buildLoungeDisbandedConnectionData } from "../../lounge/protocol"

interface LoungeRequestBody {
    viewer_id?: number
    use_case?: number
    campaign_id?: number
    lounge_id?: number
    lounge_number?: string
    advice?: string
    establisher_viewer_id?: number
    accepted_type?: number
    share_type_list?: number[]
}

function positiveSafeInteger(value: unknown): number | null {
    if (typeof value !== "number" && (typeof value !== "string" || !/^\d+$/.test(value))) return null
    const parsed = Number(value)
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}

function requestBody(value: unknown): LoungeRequestBody {
    return value !== null && typeof value === "object" && !Array.isArray(value) ? value : {}
}

async function resolveViewer(body: LoungeRequestBody): Promise<{
    viewerId: number
    playerId: number
    player: NonNullable<ReturnType<typeof getPlayerSync>>
} | null> {
    const viewerId = positiveSafeInteger(body.viewer_id)
    if (viewerId === null) return null
    const session = await getSession(String(viewerId))
    if (!session) return null
    const playerId = resolvePlayerIdSync(session.accountId)
    if (playerId === null) return null
    const player = getPlayerSync(playerId)
    return player ? { viewerId, playerId, player } : null
}

function hasAccess(room: LoungeRoom | undefined, body: LoungeRequestBody): room is LoungeRoom {
    const useCase = positiveSafeInteger(body.use_case)
    const establisherViewerId = positiveSafeInteger(body.establisher_viewer_id)
    return !!room && useCase === 1 && !!getMultiSpecialExchangeCampaignDefinition(room.campaignId) && establisherViewerId !== null
        && typeof body.advice === "string"
        && matchesLoungeAccess(room, {
            useCase,
            advice: body.advice,
            establisherViewerId,
        })
}

function connectionData(room: LoungeRoom) {
    return {
        application_update_url: "",
        ip_address: getDisplayHost(),
        lounge_number: room.number,
        port: Number.parseInt(process.env.SESSION_PORT || "8003", 10),
        raising_state: room.raisingState,
    }
}

function loungeListEntry(room: LoungeRoom) {
    return {
        advice: room.advice,
        establisher_character: room.hostProfile.characterId,
        establisher_character_evolution_img_level: room.hostProfile.characterEvolutionLevel,
        establisher_follow: 0,
        establisher_name: room.hostProfile.name,
        establisher_viewer_id: room.hostViewerId,
        lounge_id: room.id,
        mates: Math.max(1, getLoungeOccupancy(room)),
        raising_state: room.raisingState,
        use_case: room.useCase,
    }
}

function sendLoungeNotFound(reply: FastifyReply, viewerId: number) {
    reply.header("content-type", "application/x-msgpack")
    return reply.status(200).send({
        data_headers: generateDataHeaders({ viewer_id: viewerId, result_code: 4511 }),
        data: {},
    })
}

function sendLoungeDisbanded(reply: FastifyReply, viewerId: number, loungeId: number, operation: string) {
    // This is a recoverable client state, not an account/login failure. The
    // client recognizes raising_state=99 and removes lounge_restore_data.
    console.warn(`[LOUNGE] stale ${operation}: viewer=${viewerId} lounge=${loungeId}; returning disbanded state`)
    reply.header("content-type", "application/x-msgpack")
    return reply.status(200).send({
        data_headers: generateDataHeaders({ viewer_id: viewerId }),
        data: buildLoungeDisbandedConnectionData(),
    })
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/get_list", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = requestBody(request.body)
        const context = await resolveViewer(body)
        const useCase = positiveSafeInteger(body.use_case)
        if (!context || useCase !== 1) return sendLoungeNotFound(reply, context?.viewerId ?? 0)
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: { lounge_list: listLounges(useCase).filter(room => canParticipate(context.playerId, room.campaignId)).map(loungeListEntry) },
        })
    })

    fastify.post("/create", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = requestBody(request.body)
        const context = await resolveViewer(body)
        const useCase = positiveSafeInteger(body.use_case)
        const campaignId = positiveSafeInteger(body.campaign_id)
        if (!context || useCase !== 1 || campaignId === null
            || !getMultiSpecialExchangeCampaignDefinition(campaignId)
            || !canParticipate(context.playerId, campaignId)) {
            return sendLoungeNotFound(reply, context?.viewerId ?? 0)
        }
        const characterId = Number(context.player.leaderCharacterId) || 1
        const character = getPlayerCharacterSync(context.playerId, characterId)
        const room = createLounge({
            advice: randomUUID(),
            useCase,
            campaignId,
            hostViewerId: context.viewerId,
            hostPlayerId: context.playerId,
            hostProfile: {
                name: context.player.name || `Player${context.viewerId}`,
                characterId,
                characterEvolutionLevel: character?.evolutionLevel ?? 0,
            },
        })
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: { advice: room.advice, lounge_id: room.id },
        })
    })

    fastify.post("/prepare", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = requestBody(request.body)
        const context = await resolveViewer(body)
        const loungeId = positiveSafeInteger(body.lounge_id)
        if (!context || loungeId === null) return sendLoungeNotFound(reply, context?.viewerId ?? 0)
        const room = getLounge(loungeId)
        if (!hasAccess(room, body) || context.viewerId !== room.hostViewerId) {
            return sendLoungeDisbanded(reply, context.viewerId, loungeId, "prepare")
        }
        prepareLounge(room)
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: {},
        })
    })

    fastify.post("/select", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = requestBody(request.body)
        const context = await resolveViewer(body)
        const loungeId = positiveSafeInteger(body.lounge_id)
        if (!context || loungeId === null) return sendLoungeNotFound(reply, context?.viewerId ?? 0)
        const room = getLounge(loungeId)
        if (!hasAccess(room, body)) return sendLoungeDisbanded(reply, context.viewerId, loungeId, "select")
        if (!canParticipate(context.playerId, room.campaignId) || !canAttachLoungeViewer(room, context.viewerId)) {
            return sendLoungeNotFound(reply, context.viewerId)
        }
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: connectionData(room),
        })
    })

    fastify.post("/search", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = requestBody(request.body)
        const context = await resolveViewer(body)
        const useCase = positiveSafeInteger(body.use_case)
        if (!context || useCase !== 1 || typeof body.lounge_number !== "string") {
            return sendLoungeNotFound(reply, context?.viewerId ?? 0)
        }
        const room = getLoungeByNumber(body.lounge_number)
        const data = room && room.useCase === useCase && room.raisingState === 2
            && !!getMultiSpecialExchangeCampaignDefinition(room.campaignId)
            && canParticipate(context.playerId, room.campaignId)
            && canAttachLoungeViewer(room, context.viewerId)
            ? {
                lounge_exists: true,
                advice: room.advice,
                establisher_follow: 0,
                establisher_viewer_id: room.hostViewerId,
                lounge_id: room.id,
            }
            : { lounge_exists: false }
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data,
        })
    })

    fastify.post("/restore", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = requestBody(request.body)
        const context = await resolveViewer(body)
        const loungeId = positiveSafeInteger(body.lounge_id)
        if (!context || loungeId === null) return sendLoungeNotFound(reply, context?.viewerId ?? 0)
        const room = getLounge(loungeId)
        if (!hasAccess(room, body) || (room.raisingState === 2 && !canParticipate(context.playerId, room.campaignId))) {
            return sendLoungeDisbanded(reply, context.viewerId, loungeId, "restore")
        }
        const data = connectionData(room)
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: { ip_address: data.ip_address, port: data.port, raising_state: data.raising_state },
        })
    })

    fastify.post("/share", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = requestBody(request.body)
        const context = await resolveViewer(body)
        const loungeId = positiveSafeInteger(body.lounge_id)
        if (!context || loungeId === null || !Array.isArray(body.share_type_list)) {
            return sendLoungeNotFound(reply, context?.viewerId ?? 0)
        }
        const room = getLounge(loungeId)
        if (!hasAccess(room, body) || context.viewerId !== room.hostViewerId) {
            return sendLoungeNotFound(reply, context.viewerId)
        }
        setLoungeShareTypes(room, body.share_type_list.map(Number).filter(Number.isSafeInteger))
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: {},
        })
    })
}

export default routes
