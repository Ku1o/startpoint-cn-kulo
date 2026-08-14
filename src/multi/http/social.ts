import { FastifyInstance, FastifyRequest, FastifyReply } from "fastify"
import { VerifyAccessTokenBody, MicroCommunityBody } from "../types"
import { generateDataHeaders } from "../../utils"

export function registerSocialRoutes(fastify: FastifyInstance): void {

    fastify.post("/verify_access_token", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as VerifyAccessTokenBody
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({ viewer_id: body.viewer_id }),
            "data": { "is_valid": true }
        })
    })

    fastify.post("/micro_community", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as MicroCommunityBody
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({ viewer_id: body.viewer_id }),
            "data": {}
        })
    })

    fastify.post("/publish_room", async (_request: FastifyRequest, reply: FastifyReply) => {
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({}),
            "data": {}
        })
    })
}
