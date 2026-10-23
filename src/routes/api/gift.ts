import type { FastifyInstance } from "fastify"
import { getSession } from "../../data/domains/session"
import { SessionType } from "../../data/types"
import { resolvePlayerIdSync } from "../../data/activeAccount"
import { runPersistenceTransaction } from "../../lib/persistence-coordinator"
import { GiftInputError, redeemGiftCodeWithinTransactionSync } from "../../lib/gift-codes"
import { generateDataHeaders } from "../../utils"

export default async function routes(fastify: FastifyInstance) {
    fastify.post("/receive", async (request, reply) => {
        const body = request.body as { viewer_id?: number; key?: unknown } | null
        if (!body || !Number.isSafeInteger(body.viewer_id) || Number(body.viewer_id) < 1 || typeof body.key !== "string")
            return reply.code(400).send({ error: "Invalid gift request" })
        const session = await getSession(String(body.viewer_id))
        if (!session || session.type !== SessionType.VIEWER) return reply.code(400).send({ error: "Invalid viewer id" })
        const playerId = resolvePlayerIdSync(session.accountId)
        if (playerId === null) return reply.code(400).send({ error: "No active player" })
        try {
            const data = await runPersistenceTransaction({ domain: "player", playerId, operation: "gift_code_redemption" },
                () => redeemGiftCodeWithinTransactionSync(playerId, body.key))
            return reply.header("content-type", "application/x-msgpack").send({ data_headers: generateDataHeaders({ viewer_id: body.viewer_id }), data })
        } catch (error) {
            if (error instanceof GiftInputError) return reply.code(400).send({ error: error.message })
            throw error
        }
    })
}
