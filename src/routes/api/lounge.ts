import { randomUUID } from "crypto"
import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify"
import { resolvePlayerIdSync } from "../../data/activeAccount"
import { getPlayerCharacterSync } from "../../data/domains/character"
import { getPlayerSync } from "../../data/domains/player"
import { getSession } from "../../data/domains/session"
import {
    createLounge,
    getLounge,
    getLoungeByNumber,
    listLounges,
    matchesLoungeAccess,
    prepareLounge,
    setLoungeShareTypes,
    type LoungeRoom,
} from "../../lounge/state"
import { getDisplayHost } from "../../multi/room/serializer"
import { generateDataHeaders } from "../../utils"

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
    const parsed = Number(value)
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
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
    return !!room && useCase !== null && establisherViewerId !== null
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
        mates: Math.max(1, room.members.size),
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

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/get_list", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as LoungeRequestBody
        const context = await resolveViewer(body)
        const useCase = positiveSafeInteger(body.use_case)
        if (!context || useCase === null) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body or viewer id.",
        })
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: { lounge_list: listLounges(useCase).map(loungeListEntry) },
        })
    })

    fastify.post("/create", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as LoungeRequestBody
        const context = await resolveViewer(body)
        const useCase = positiveSafeInteger(body.use_case)
        const campaignId = positiveSafeInteger(body.campaign_id)
        if (!context || useCase === null || campaignId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body or viewer id.",
        })
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
        const body = request.body as LoungeRequestBody
        const context = await resolveViewer(body)
        const loungeId = positiveSafeInteger(body.lounge_id)
        if (!context || loungeId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body or viewer id.",
        })
        const room = getLounge(loungeId)
        if (!hasAccess(room, body) || context.viewerId !== room.hostViewerId) {
            return sendLoungeNotFound(reply, context.viewerId)
        }
        prepareLounge(room)
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: {},
        })
    })

    fastify.post("/select", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as LoungeRequestBody
        const context = await resolveViewer(body)
        const loungeId = positiveSafeInteger(body.lounge_id)
        if (!context || loungeId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body or viewer id.",
        })
        const room = getLounge(loungeId)
        if (!hasAccess(room, body)) return sendLoungeNotFound(reply, context.viewerId)
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: connectionData(room),
        })
    })

    fastify.post("/search", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as LoungeRequestBody
        const context = await resolveViewer(body)
        const useCase = positiveSafeInteger(body.use_case)
        if (!context || useCase === null || typeof body.lounge_number !== "string") {
            return reply.status(400).send({ error: "Bad Request", message: "Invalid request body or viewer id." })
        }
        const room = getLoungeByNumber(body.lounge_number)
        const data = room && room.useCase === useCase && room.raisingState === 2
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
        const body = request.body as LoungeRequestBody
        const context = await resolveViewer(body)
        const loungeId = positiveSafeInteger(body.lounge_id)
        if (!context || loungeId === null) return reply.status(400).send({
            error: "Bad Request",
            message: "Invalid request body or viewer id.",
        })
        const room = getLounge(loungeId)
        if (!hasAccess(room, body)) return sendLoungeNotFound(reply, context.viewerId)
        const data = connectionData(room)
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            data_headers: generateDataHeaders({ viewer_id: context.viewerId }),
            data: { ip_address: data.ip_address, port: data.port, raising_state: data.raising_state },
        })
    })

    fastify.post("/share", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as LoungeRequestBody
        const context = await resolveViewer(body)
        const loungeId = positiveSafeInteger(body.lounge_id)
        if (!context || loungeId === null || !Array.isArray(body.share_type_list)) {
            return reply.status(400).send({ error: "Bad Request", message: "Invalid request body or viewer id." })
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
