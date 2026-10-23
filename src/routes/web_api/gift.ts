import type { FastifyInstance } from "fastify"
import { hasManagementSession } from "../../lib/management-auth"
import { runPersistenceTransaction } from "../../lib/persistence-coordinator"
import { createGiftCodeSync, GiftInputError, giftRewardIds, listGiftCodesSync, setGiftCodeEnabledSync } from "../../lib/gift-codes"

export default async function routes(fastify: FastifyInstance) {
    fastify.addHook("preHandler", async (request, reply) => {
        if (!hasManagementSession(request)) return reply.code(401).send({ error: "需要管理登录" })
    })
    fastify.get("/", async () => ({ gifts: listGiftCodesSync(), rewardIds: giftRewardIds() }))
    fastify.post("/", async (request, reply) => {
        try {
            return await runPersistenceTransaction({ domain: "player", operation: "admin_gift_create" }, () => createGiftCodeSync(request.body))
        } catch (error) {
            if (error instanceof GiftInputError) return reply.code(400).send({ error: error.message })
            throw error
        }
    })
    fastify.patch<{ Params: { id: string } }>("/:id", async (request, reply) => {
        const body = request.body as { revision: number; enabled: boolean } | null
        try {
            if (!body) throw new GiftInputError("缺少状态参数")
            const updated = await runPersistenceTransaction({ domain: "player", operation: "admin_gift_status" },
                () => setGiftCodeEnabledSync(Number(request.params.id), body.revision, body.enabled))
            return updated ? { ok: true } : reply.code(409).send({ error: "礼包码已更新，请刷新后重试" })
        } catch (error) {
            if (error instanceof GiftInputError) return reply.code(400).send({ error: error.message })
            throw error
        }
    })
}
