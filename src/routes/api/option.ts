import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { getSession } from "../../data/domains/session"
import { updatePlayerOptionsInTransactionSync } from "../../data/domains/option"
import { resolvePlayerIdSync } from "../../data/activeAccount";
import { generateDataHeaders } from "../../utils";
import { markFiveBossSoloAutoUsedSync } from "../../multi/five-boss/solo-runtime";
import { runPersistenceTransaction } from "../../lib/persistence-coordinator";

interface UpdateBody {
    viewer_id: number
    api_count: number
    option_params: Record<string, boolean>
}

const updateRoute = async (request: FastifyRequest, reply: FastifyReply) => {
    const body = request.body as UpdateBody

    const viewerId = body.viewer_id
    if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
        "error": "Bad Request",
        "message": "Invalid request body."
    })

    const viewerIdSession = await getSession(viewerId.toString())
    if (!viewerIdSession) return reply.status(400).send({
        "error": "Bad Request",
        "message": "Invalid viewer id."
    })

    // get player
    const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!

    if (playerId === null) return reply.status(500).send({
        "error": "Internal Server Error",
        "message": "No player bound to account."
    })

    // update options
    const updatedOptions = body.option_params
    await runPersistenceTransaction({
        domain: "player", playerId, operation: "update_options",
    }, () => {
        updatePlayerOptionsInTransactionSync(playerId, updatedOptions)
        // Match the option store's boolean coercion for values received on the wire.
        if (updatedOptions.auto_play) markFiveBossSoloAutoUsedSync(playerId)
    })
    
    reply.header("content-type", "application/x-msgpack")
    return reply.status(200).send({
        "data_headers": generateDataHeaders({
            viewer_id: viewerId
        }),
        "data": {
            "user_option": updatedOptions
        }
    })
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/update", updateRoute)

    fastify.post("/update_in_battle", updateRoute)
}

export default routes;
