const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-news-test-"))
const newsConfigPath = path.join(temporaryDataDir, "news.json")
process.env.DATA_DIR = temporaryDataDir
process.env.NEWS_CONFIG_PATH = newsConfigPath

fs.writeFileSync(newsConfigPath, `${JSON.stringify({
    version: 1,
    popup: {
        enabled: true,
        news_id: 101,
        mode: "once_per_news",
        start_time: null,
        end_time: null,
    },
    news: [
        {
            id: 101,
            title: "登录公告",
            date: "2026-08-31 12:00:00",
            category: 1,
            label: 1,
            thumbnail: 1,
            thumbnail_path: null,
            added_time: "2026-08-31 12:00:00",
            html: "<html><body><h1>登录公告</h1></body></html>",
            published: true,
        },
        {
            id: 102,
            title: "活动公告",
            date: "2026-08-30 12:00:00",
            category: 2,
            label: 2,
            thumbnail: 1,
            thumbnail_path: null,
            added_time: null,
            html: "<html><body><p>活动内容</p></body></html>",
            published: true,
        },
        {
            id: 103,
            title: "系统公告",
            date: "2026-08-29 12:00:00",
            category: 4,
            label: 4,
            thumbnail: 1,
            thumbnail_path: null,
            added_time: null,
            html: "<html><body><p>系统内容</p></body></html>",
            published: true,
        },
    ],
}, null, 4)}\n`, "utf-8")

let gameApp = null
let adminApp = null

async function main() {
    const Fastify = require("fastify")
    const gameNewsRoutes = require("../out/routes/api/news").default
    const adminNewsRoutes = require("../out/routes/web_api/news").default
    const { insertAccountSync } = require("../out/data/domains/account")
    const { insertSessionWithToken } = require("../out/data/domains/session")
    const { getDb } = require("../out/data/db")
    const { getNewsDeliveryState, getNewsInterruptFlag } = require("../out/lib/news-delivery")
    const { generateDataHeaders } = require("../out/utils")

    // MessagePack encodes JavaScript undefined as an extension value.  The
    // client expects no pending news interrupt to be an actual nil value.
    assert.equal(generateDataHeaders().force_news, null)

    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "leiting",
        idpId: "",
        status: "normal",
    })
    const viewerId = 712345678
    await insertSessionWithToken({
        token: String(viewerId),
        accountId: account.id,
        type: 2,
        expires: new Date(Date.now() + 86_400_000),
    })
    gameApp = Fastify({ logger: false })
    gameApp.addHook("onSend", (_request, reply, payload, done) => {
        const contentType = String(reply.getHeader("content-type") ?? "")
        done(null, contentType.startsWith("application/x-msgpack") && typeof payload === "object"
            ? JSON.stringify(payload)
            : payload)
    })
    await gameApp.register(gameNewsRoutes, { prefix: "/news" })
    await gameApp.ready()

    adminApp = Fastify({ logger: false })
    await adminApp.register(adminNewsRoutes, { prefix: "/api/news" })
    await adminApp.ready()

    const postGame = async (url, payload = {}) => {
        const response = await gameApp.inject({
            method: "POST",
            url: `/news/${url}`,
            headers: { "content-type": "application/json" },
            payload: { viewer_id: viewerId, ...payload },
        })
        assert.equal(response.statusCode, 200, response.payload)
        return JSON.parse(response.payload)
    }

    assert.equal(getNewsDeliveryState(account.id).forceNews, true)
    assert.equal(getNewsDeliveryState(account.id).hasUnreadNews, true)
    assert.equal(getNewsInterruptFlag(getNewsDeliveryState(account.id)), 1)

    const forced = await postGame("latest_forced")
    assert.equal(forced.data.id, 101)
    for (const field of ["id", "title", "date", "html", "label", "thumbnail", "thumbnail_path", "added_time"]) {
        assert.ok(Object.hasOwn(forced.data, field), `forced announcement misses ${field}`)
    }
    assert.equal(forced.data_headers.force_news, null)
    assert.equal(getNewsDeliveryState(account.id).forceNews, false)

    // Re-entering a screen can cause the legacy client to ask for the forced
    // endpoint again. Once the receipt exists, return a schema-valid empty
    // detail so strict client parsing does not turn this into R1.
    const forcedAgain = await postGame("latest_forced")
    assert.equal(forcedAgain.data.id, 0)
    for (const field of ["id", "title", "date", "html", "label", "thumbnail", "thumbnail_path", "added_time"]) {
        assert.ok(Object.hasOwn(forcedAgain.data, field), `fallback announcement misses ${field}`)
    }
    assert.equal(forcedAgain.data_headers.force_news, null)

    const activity = await postGame("index", { category: 2, page_index: 1 })
    assert.equal(activity.data.news_count, 1)
    assert.equal(activity.data_headers.force_news, null)
    assert.deepEqual(activity.data.news.map(item => item.id), [102])
    assert.equal(getNewsDeliveryState(account.id).hasUnreadNews, false)
    assert.equal(getNewsInterruptFlag(getNewsDeliveryState(account.id)), null)

    await postGame("index", { category: 1, page_index: 1 })
    const system = await postGame("system_index", { category: 4, page_index: 1 })
    assert.deepEqual(system.data.news.map(item => item.id), [103])
    assert.equal(getNewsDeliveryState(account.id).hasUnreadNews, false)

    let response = await adminApp.inject({ method: "GET", url: "/api/news/" })
    assert.equal(response.statusCode, 200, response.payload)
    assert.equal(JSON.parse(response.payload).active_popup_id, 101)

    response = await adminApp.inject({
        method: "POST",
        url: "/api/news/popup/reset",
        payload: { news_id: 101 },
    })
    assert.equal(response.statusCode, 200, response.payload)
    assert.equal(JSON.parse(response.payload).deleted, 1)
    assert.equal(getNewsDeliveryState(account.id).forceNews, true)

    response = await adminApp.inject({
        method: "POST",
        url: "/api/news/items",
        payload: {
            id: 104,
            title: "草稿公告",
            date: "2026-08-31 13:00:00",
            category: 3,
            label: 3,
            thumbnail: 1,
            thumbnail_path: null,
            added_time: null,
            html: "<p>尚未发布</p>",
            published: false,
        },
    })
    assert.equal(response.statusCode, 200, response.payload)

    response = await adminApp.inject({
        method: "POST",
        url: "/api/news/items",
        payload: {
            id: 105,
            title: "非法缩略图",
            date: "2026-08-31 14:00:00",
            category: 1,
            label: 1,
            thumbnail: 14,
            thumbnail_path: null,
            added_time: null,
            html: "<p>不应保存</p>",
            published: true,
        },
    })
    assert.equal(response.statusCode, 400, response.payload)
    assert.match(JSON.parse(response.payload).error, /thumbnail.*1–13/)

    response = await adminApp.inject({
        method: "POST",
        url: "/api/news/items",
        payload: {
            id: 106,
            title: "自定义缩略图",
            date: "2026-08-31 14:00:00",
            category: 1,
            label: 1,
            thumbnail: 1,
            thumbnail_path: "dynamic/feature_announcement/example.png",
            added_time: null,
            html: "<p>不应保存</p>",
            published: true,
        },
    })
    assert.equal(response.statusCode, 400, response.payload)
    assert.match(JSON.parse(response.payload).error, /thumbnail_path.*不支持/)

    response = await adminApp.inject({
        method: "PUT",
        url: "/api/news/popup",
        payload: { enabled: true, news_id: 104 },
    })
    assert.equal(response.statusCode, 400, response.payload)
    assert.match(JSON.parse(response.payload).error, /已发布公告/)

    response = await adminApp.inject({
        method: "PATCH",
        url: "/api/news/items/104",
        payload: { published: true },
    })
    assert.equal(response.statusCode, 200, response.payload)

    response = await adminApp.inject({
        method: "PUT",
        url: "/api/news/popup",
        payload: { enabled: true, news_id: 104, mode: "every_login" },
    })
    assert.equal(response.statusCode, 200, response.payload)
    const overview = JSON.parse(response.payload)
    assert.equal(overview.popup.news_id, 104)
    assert.equal(overview.active_popup_id, 104)
    assert.equal(getNewsDeliveryState(account.id).forceNews, true)

    response = await adminApp.inject({
        method: "PUT",
        url: "/api/news/popup",
        payload: { enabled: false, news_id: null },
    })
    assert.equal(response.statusCode, 200, response.payload)
    const noForced = await postGame("latest_forced")
    assert.equal(noForced.data.id, 0)
    assert.equal(noForced.data_headers.force_news, null)

    assert.equal(getDb().prepare(`SELECT COUNT(*) AS count FROM account_news_receipts`).get().count >= 3, true)
    console.log("news announcement integration tests passed")
}

main()
    .finally(async () => {
        try { await gameApp?.close() } catch {}
        try { await adminApp?.close() } catch {}
        try { require("../out/data/db").getDb().close() } catch {}
        const resolved = path.resolve(temporaryDataDir)
        if (resolved.startsWith(path.resolve(os.tmpdir()) + path.sep)) {
            fs.rmSync(resolved, { recursive: true, force: true })
        }
    })
    .catch(error => {
        console.error(error)
        process.exitCode = 1
    })
