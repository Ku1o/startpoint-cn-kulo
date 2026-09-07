/**
 * News / Announcement API.
 *
 * CN client response contracts are strict for list/detail payloads. The
 * forced-popup endpoint must always return the complete client news schema;
 * returning `{}` for a missing item causes the client to show its generic R1
 * parse-error screen.
 */
import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify"
import {
    hasAccountNewsReceiptSync,
    markAccountNewsReceiptSync,
    markAccountNewsReceiptsSync,
} from "../../data/domains/news"
import { getSession } from "../../data/domains/session"
import {
    getActivePopupNews,
    getPublishedNews,
    loadNewsConfig,
    NewsCategory,
    NewsItem,
} from "../../lib/news-config"
import { generateDataHeaders, getServerDate } from "../../utils"

const NEWS_PER_PAGE = 20

// A stale client-side force flag can cause one more latest_forced request after
// the popup was already acknowledged (or disabled in the admin panel). The
// legacy client has no "no item" response shape, so use a schema-valid,
// visually empty detail that lets it clear that stale flag instead of failing
// during strict response parsing. It is never persisted as an announcement.
const EMPTY_FORCED_NEWS = {
    id: 0,
    title: "",
    date: "1970-01-01 00:00:00",
    html: "<p></p>",
    label: 0,
    thumbnail: 0,
    thumbnail_path: null,
    added_time: null,
}

function toClientNews(item: NewsItem) {
    return {
        id: item.id,
        title: item.title,
        date: item.date,
        html: item.html,
        label: item.label,
        thumbnail: item.thumbnail,
        thumbnail_path: item.thumbnail_path,
        added_time: item.added_time,
    }
}

function parsePage(value: unknown): number {
    const parsed = Number(value ?? 1)
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1
}

function parseCategory(value: unknown, fallback: NewsCategory): NewsCategory {
    const parsed = Number(value)
    return Number.isSafeInteger(parsed) && parsed >= 1 && parsed <= 4
        ? parsed as NewsCategory
        : fallback
}

async function requireViewer(
    request: FastifyRequest,
    reply: FastifyReply,
): Promise<{ viewerId: number, accountId: number } | null> {
    const body = request.body as Record<string, unknown> | null
    const viewerId = Number(body?.viewer_id)
    if (!Number.isSafeInteger(viewerId) || viewerId <= 0) {
        reply.status(400).send({ error: "Bad Request", message: "Invalid request body." })
        return null
    }
    const session = await getSession(String(viewerId))
    if (!session) {
        reply.status(400).send({ error: "Bad Request", message: "Invalid viewer id." })
        return null
    }
    return { viewerId, accountId: session.accountId }
}

function sendMsgpack(reply: FastifyReply, viewerId: number, data: unknown) {
    reply.header("content-type", "application/x-msgpack")
    return reply.status(200).send({
        // Opening or browsing the panel must not schedule another startup
        // interruption. A null force_news is decoded by the client as
        // Option.None; 0 would be decoded as Some(0) and can leave stale
        // announcement state behind.
        data_headers: generateDataHeaders({ viewer_id: viewerId, force_news: null }),
        data,
    })
}

const routes = async (fastify: FastifyInstance) => {
    const sendIndex = async (
        request: FastifyRequest,
        reply: FastifyReply,
        fallbackCategory: NewsCategory,
    ) => {
        const viewer = await requireViewer(request, reply)
        if (!viewer) return
        const body = request.body as Record<string, unknown>
        const publishedNews = getPublishedNews(loadNewsConfig())
        const category = parseCategory(body.category, fallbackCategory)
        const allNews = publishedNews.filter(item => item.category === category)
        const page = parsePage(body.page_index ?? body.current_page)
        const start = (page - 1) * NEWS_PER_PAGE
        const pageItems = allNews.slice(start, start + NEWS_PER_PAGE)
        // Opening the announcement panel is the client's acknowledgement
        // point.  It initially requests only one tab, but the panel has one
        // unread badge for the whole announcement feed.  Mark every published
        // item here so returning to the main city does not reopen the panel
        // merely because another category was not selected yet.
        markAccountNewsReceiptsSync(viewer.accountId, publishedNews.map(item => item.id), "list")
        return sendMsgpack(reply, viewer.viewerId, {
            current_page: page,
            news: pageItems.map(toClientNews),
            news_count: allNews.length,
        })
    }

    const sendInfo = async (
        request: FastifyRequest,
        reply: FastifyReply,
        systemOnly: boolean,
    ) => {
        const viewer = await requireViewer(request, reply)
        if (!viewer) return
        const body = request.body as Record<string, unknown>
        const newsId = Number(body.news_id)
        const item = getPublishedNews(loadNewsConfig()).find(candidate => (
            candidate.id === newsId && (systemOnly ? candidate.category === 4 : candidate.category !== 4)
        ))
        if (!item) {
            return reply.status(400).send({
                error: "Bad Request",
                message: `News with id '${body.news_id}' not found.`,
            })
        }
        markAccountNewsReceiptSync(viewer.accountId, item.id, "list")
        return sendMsgpack(reply, viewer.viewerId, toClientNews(item))
    }

    const sendForced = async (request: FastifyRequest, reply: FastifyReply) => {
        const viewer = await requireViewer(request, reply)
        if (!viewer) return
        const config = loadNewsConfig()
        const item = getActivePopupNews(config, getServerDate())
        // The client may ask for the forced announcement again when returning
        // from another screen.  For the once-per-news policy, an already
        // acknowledged item must not be sent again; otherwise the client will
        // display the same popup on every navigation even though /load has
        // already delivered it once.
        if (
            item === null
            || (
                config.popup.mode === "once_per_news"
                && hasAccountNewsReceiptSync(viewer.accountId, item.id, "popup")
            )
        ) {
            console.warn(
                `[NEWS] latest_forced fallback: viewer=${viewer.viewerId} `
                + `reason=${item === null ? "no-active-popup" : "popup-already-read"}`,
            )
            return sendMsgpack(reply, viewer.viewerId, EMPTY_FORCED_NEWS)
        }
        markAccountNewsReceiptSync(viewer.accountId, item.id, "popup")
        return sendMsgpack(reply, viewer.viewerId, toClientNews(item))
    }

    fastify.post("/index", (request, reply) => sendIndex(request, reply, 1))
    fastify.post("/get_info", (request, reply) => sendInfo(request, reply, false))
    fastify.post("/system_index", (request, reply) => sendIndex(request, reply, 4))
    fastify.post("/get_system_info", (request, reply) => sendInfo(request, reply, true))
    fastify.post("/latest_forced", sendForced)
    // Kept for compatibility with deployments that call the system variant.
    fastify.post("/latest_forced_system", sendForced)
}

export default routes
