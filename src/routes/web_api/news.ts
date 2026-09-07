import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify"
import {
    deleteAllPopupNewsReceiptsSync,
    deleteNewsReceiptsSync,
} from "../../data/domains/news"
import {
    getActivePopupNews,
    NewsConfig,
    readNewsConfigState,
    saveNewsConfig,
} from "../../lib/news-config"
import { getServerDate } from "../../utils"

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value)
}

function fail(reply: FastifyReply, error: unknown, statusCode = 400) {
    const message = error instanceof Error ? error.message : String(error)
    return reply.status(statusCode).send({ error: message })
}

function requireEditableConfig(reply: FastifyReply): NewsConfig | null {
    const state = readNewsConfigState()
    if (state.error !== null) {
        fail(reply, `公告配置当前无效，请先修复 assets/news.json：${state.error}`, 409)
        return null
    }
    return state.config
}

function sendOverview(reply: FastifyReply) {
    const state = readNewsConfigState()
    const activePopup = getActivePopupNews(state.config, getServerDate())
    return reply.send({
        ...state.config,
        load_error: state.error,
        source_path: state.path,
        active_popup_id: activePopup?.id ?? null,
    })
}

const routes = async (fastify: FastifyInstance) => {
    fastify.get("/", async (_request, reply) => sendOverview(reply))

    fastify.post("/items", async (request: FastifyRequest, reply: FastifyReply) => {
        const config = requireEditableConfig(reply)
        if (!config) return
        if (!isRecord(request.body)) return fail(reply, "请求正文必须是公告对象")
        const body = request.body
        const requestedId = body.id
        const id = requestedId === undefined || requestedId === null || requestedId === ""
            ? config.news.reduce((maximum, item) => Math.max(maximum, item.id), 0) + 1
            : Number(requestedId)
        if (config.news.some(item => item.id === id)) return fail(reply, `公告 ID ${id} 已存在`, 409)
        try {
            saveNewsConfig({ ...config, news: [...config.news, { ...body, id }] })
            return sendOverview(reply)
        } catch (error) {
            return fail(reply, error)
        }
    })

    fastify.patch("/items/:id", async (request: FastifyRequest, reply: FastifyReply) => {
        const config = requireEditableConfig(reply)
        if (!config) return
        if (!isRecord(request.body)) return fail(reply, "请求正文必须是公告对象")
        const id = Number((request.params as { id: string }).id)
        const index = config.news.findIndex(item => item.id === id)
        if (index < 0) return fail(reply, `公告 ID ${id} 不存在`, 404)
        const nextNews = [...config.news]
        nextNews[index] = { ...nextNews[index], ...request.body, id }
        try {
            saveNewsConfig({ ...config, news: nextNews })
            return sendOverview(reply)
        } catch (error) {
            return fail(reply, error)
        }
    })

    fastify.delete("/items/:id", async (request: FastifyRequest, reply: FastifyReply) => {
        const config = requireEditableConfig(reply)
        if (!config) return
        const id = Number((request.params as { id: string }).id)
        if (!config.news.some(item => item.id === id)) return fail(reply, `公告 ID ${id} 不存在`, 404)
        const popup = config.popup.news_id === id
            ? { ...config.popup, enabled: false, news_id: null }
            : config.popup
        try {
            saveNewsConfig({ ...config, popup, news: config.news.filter(item => item.id !== id) })
            deleteNewsReceiptsSync(id)
            return sendOverview(reply)
        } catch (error) {
            return fail(reply, error)
        }
    })

    fastify.put("/popup", async (request: FastifyRequest, reply: FastifyReply) => {
        const config = requireEditableConfig(reply)
        if (!config) return
        if (!isRecord(request.body)) return fail(reply, "请求正文必须是弹窗配置对象")
        try {
            saveNewsConfig({ ...config, popup: { ...config.popup, ...request.body } })
            return sendOverview(reply)
        } catch (error) {
            return fail(reply, error)
        }
    })

    fastify.post("/popup/reset", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = isRecord(request.body) ? request.body : {}
        const requestedId = body.news_id
        if (requestedId !== undefined && requestedId !== null && requestedId !== "") {
            const newsId = Number(requestedId)
            if (!Number.isSafeInteger(newsId) || newsId <= 0) return fail(reply, "公告 ID 无效")
            const deleted = deleteNewsReceiptsSync(newsId, "popup")
            return reply.send({ ok: true, deleted, news_id: newsId })
        }
        const deleted = deleteAllPopupNewsReceiptsSync()
        return reply.send({ ok: true, deleted, news_id: null })
    })
}

export default routes
