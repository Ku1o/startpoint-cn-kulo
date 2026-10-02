import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify"
import { configureRealtimeDiagnostics, getRealtimeDiagnostics } from "../../lib/realtime-diagnostics"

/** Management-only runtime controls for bounded multiplayer diagnostics. */
const routes = async (fastify: FastifyInstance) => {
    fastify.get("/realtime", async (_request: FastifyRequest, reply: FastifyReply) => {
        return reply.status(200).send(getRealtimeDiagnostics())
    })

    fastify.post("/realtime", async (request: FastifyRequest, reply: FastifyReply) => {
        try {
            return reply.status(200).send(configureRealtimeDiagnostics((request.body ?? {}) as {
                mode?: unknown; roomNumber?: unknown; ttlMs?: unknown; maxEvents?: unknown
            }))
        } catch (error) {
            return reply.status(400).send({ error: error instanceof Error ? error.message : String(error) })
        }
    })
}

export default routes
