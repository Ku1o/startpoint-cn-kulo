import type { FastifyReply, FastifyRequest } from "fastify"

export function canWriteReply(request: FastifyRequest, reply: FastifyReply): boolean {
    return !reply.sent
        && !reply.raw.headersSent
        && !reply.raw.destroyed
        && !request.raw.aborted
        && !!request.socket
        && !request.socket.destroyed
}

export function hijackUnavailableReply(request: FastifyRequest, reply: FastifyReply): boolean {
    if (canWriteReply(request, reply)) return false
    if (!reply.sent) reply.hijack()
    return true
}
