import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { SessionType } from "../../data/types";
import { generateViewerIdSessionSync, getAccountSessionsOfTypeSync, getSession } from "../../data/domains/session"
import { getPlayerFromAccountIdSync, insertDefaultPlayerSync } from "../../data/domains/player"
import { generateDataHeaders } from "../../utils";
import { runPersistenceTransaction } from "../../lib/persistence-coordinator";

interface GetHeaderResponseBody {
    viewer_id: number
}

interface SignupBody {
    app_secret: string
    access_token: string
    storage_directory_path: string
    app_admin: string
    kakao_pid: string,
    device_id: number,
    idp_code: string
}

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/get_header_response", (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as GetHeaderResponseBody

        reply.header("content-type", "application/x-msgpack")

        reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: body.viewer_id
            }),
            "data": []
        })
    })

    fastify.post("/signup", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as SignupBody
        
        const zat = body.access_token
        if (!zat) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const udid = request.headers['udid']
        if (!udid) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid headers."
        })

        const session = await getSession(zat)
        if (session === null || session.type !== SessionType.ZAT) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid zat provided."
        })

        const accountId = session.accountId

        const viewerId = await runPersistenceTransaction({
            domain: "account", operation: "legacy_tool_signup",
        }, () => {
            // Create the player data if it doesn't exist, then ensure the
            // account has exactly one viewer session under the same owner.
            const accountPlayer = getPlayerFromAccountIdSync(accountId)
            if (accountPlayer === null) insertDefaultPlayerSync(accountId)
            const viewerIds = getAccountSessionsOfTypeSync(accountId, SessionType.VIEWER)
            return viewerIds[0] ?? generateViewerIdSessionSync(accountId)
        })

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: Number.parseInt(viewerId.token),
                udid: String(udid)
            }, ['short_udid', 'viewer_id', 'udid', 'servertime', 'result_code']),
            "data": []
        })
    })
}

export default routes;
