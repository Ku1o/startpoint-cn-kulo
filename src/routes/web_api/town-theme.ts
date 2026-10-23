import type { FastifyInstance } from "fastify"
import { hasManagementSession } from "../../lib/management-auth"
import { townThemeCatalog, townThemeStore } from "../../lib/town-theme"
import { TownThemeError, TownThemeConflict, validateTownThemeUpdate, type TownThemeStore } from "../../lib/town-theme-store"

interface TownThemeRouteDependencies {
    store: () => TownThemeStore
    transaction: <T>(operation: () => T) => Promise<T>
}
const dependencies: TownThemeRouteDependencies = {
    store: townThemeStore,
    transaction: operation => (require("../../lib/persistence-coordinator") as typeof import("../../lib/persistence-coordinator"))
        .runPersistenceTransaction({ domain: "admin", operation: "apply_town_theme" }, operation),
}
export function createTownThemeRoutes(deps: TownThemeRouteDependencies) {
    return async (fastify: FastifyInstance): Promise<void> => {
        // Legacy servers do not necessarily install the outer /api guard.
        fastify.addHook("onRequest", async (request, reply) => {
            reply.header("Cache-Control", "no-store")
            if (!hasManagementSession(request)) return reply.status(401).send({ error: "unauthorized" })
        })
        fastify.get("/", async (_request, reply) => reply.send(deps.store().status()))
        fastify.post("/", { bodyLimit: 32768 }, async (request, reply) => {
            try {
                const body = validateTownThemeUpdate(request.body)
                // Resolve and recheck catalog/state only after admission/BEGIN.
                return reply.send(await deps.transaction(() => deps.store().update(body)))
            } catch (error) {
                if (error instanceof TownThemeConflict) return reply.status(409).send({ error: error.message, current: error.current })
                if (error instanceof TownThemeError) return reply.status(error.statusCode).send({ error: error.message })
                request.log.error({ err: error }, "town_theme_update_failed")
                return reply.status(503).send({ error: "主城外观保存结果未知，请先刷新读取当前状态，勿自动重试。" })
            }
        })
        fastify.get<{ Params: { file: string } }>("/thumbnails/:file", async (request, reply) => {
            const match = /^([a-f0-9]{64})\.webp$/.exec(request.params.file)
            const bytes = match ? deps.store().catalog.thumbnail(match[1]) : undefined
            if (!match || !bytes) return reply.status(404).send({ error: "not_found" })
            const tag = `"${match[1]}"`
            reply.header("Cache-Control", "private, max-age=86400, immutable").header("ETag", tag)
                .header("X-Content-Type-Options", "nosniff").type("image/webp")
            const conditional = request.headers["if-none-match"]
            if (conditional && conditional.split(",").some(value => value.trim() === "*" || value.trim().replace(/^W\//, "") === tag)) return reply.status(304).send()
            return reply.send(bytes)
        })
    }
}
export default async function routes(fastify: FastifyInstance): Promise<void> {
    townThemeCatalog()
    return createTownThemeRoutes(dependencies)(fastify)
}
