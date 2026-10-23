import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify"
import fastifyStatic from "@fastify/static"
import { existsSync, readFileSync } from "fs"
import path from "path"

export function installAdminSpaStatic(fastify: FastifyInstance, directory: string): boolean {
    if (!existsSync(path.join(directory, "index.html"))) return false
    fastify.register(fastifyStatic, {
        root: directory, prefix: "/admin/", decorateReply: false,
        preCompressed: true, cacheControl: false,
        setHeaders(response, filename) {
            const relative = path.relative(directory, filename).replace(/\\/g, "/").replace(/\.(br|gz)$/, "")
            const hashed = /^assets\/[^/]+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$/.test(relative)
            response.setHeader("cache-control", hashed ? "private, max-age=31536000, immutable" : "no-cache")
            response.setHeader("vary", "Accept-Encoding")
        },
    })
    fastify.get("/admin", (_request, reply) => reply.redirect("/admin/"))
    return true
}

/** Resource misses must remain 404 instead of returning HTML as JavaScript. */
export function sendAdminSpaFallback(request: FastifyRequest, reply: FastifyReply, directory: string): boolean {
    if (request.method !== "GET" && request.method !== "HEAD") return false
    let pathname: string
    try { pathname = decodeURIComponent(request.url.split("?", 1)[0]) } catch { return false }
    if (!/^\/admin\/(?:|time|content(?:\/history)?|town-themes|maintenance|accounts|mail|gifts|news|seeds|leaderboards|players\/[^/.]+)\/?$/.test(pathname)) return false
    reply.header("content-type", "text/html; charset=utf-8").header("cache-control", "no-cache")
        .send(readFileSync(path.join(directory, "index.html")))
    return true
}
