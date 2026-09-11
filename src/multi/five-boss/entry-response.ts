import type { FastifyReply } from "fastify"
import { generateDataHeaders } from "../../utils"
import { FiveBossGauntletRunError } from "../../data/domains/fiveBossGauntletRun"

/** Native QuestStartRealRemote handles 4050 by closing loading and returning to the quest UI.
 * Other result codes and HTTP 400 use the fatal title-return handler. The CDN
 * entry-condition message covers item shortage as well as existing 4050 uses.
 */
export function isFiveBossTicketShortage(error: unknown): boolean {
    return error instanceof FiveBossGauntletRunError && error.code === "insufficient_ticket"
}

export function sendFiveBossTicketShortage(reply: FastifyReply, viewerId: number) {
    reply.header("content-type", "application/x-msgpack")
    return reply.status(200).send({
        data_headers: generateDataHeaders({ viewer_id: viewerId, result_code: 4050 }),
        data: {},
    })
}
