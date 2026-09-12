import type { FastifyInstance } from "fastify"
import { getAbyssFloorRecordDetailsSync } from "../../data/domains/abyss-records"
import { getAbyssTimeRevision, getAbyssTimeRevisionAtVersion, isAbyssFiniteQuest } from "../../lib/abyss-time-revision"
import { getQuestFromCategorySync } from "../../lib/assets"

/** Public record and game nickname only; no identifiers or write operation. */
export default async function abyssRecordsRoutes(app: FastifyInstance): Promise<void> {
    app.get<{ Params: { questId: string }; Querystring: { res_ver?: string } }>(
        "/abyss-records/:questId", async (request, reply) => {
            reply.header("Cache-Control", "no-store")
            const questId = Number(request.params.questId)
            if (!/^7000990\d{2}$/.test(request.params.questId) || !isAbyssFiniteQuest(24, questId)
                || !getQuestFromCategorySync(24, questId)) return reply.code(404).send({ status: "not_found" })
            const revision = getAbyssTimeRevision()
            if (!revision || getAbyssTimeRevisionAtVersion(request.query.res_ver) !== revision)
                return { status: "update_required", quest_id: questId, best_time_ms: null }
            const record = getAbyssFloorRecordDetailsSync(revision, questId)
            return { status: "ok", quest_id: questId, revision,
                best_time_ms: record?.bestTimeMs ?? null, holder_name: record?.holderName ?? null }
        })
}
