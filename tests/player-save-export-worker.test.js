const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")

const temporaryDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "startpoint-save-export-"))
process.env.DATA_DIR = temporaryDataDir

const Fastify = require("fastify")
const { getDb } = require("../out/data/db")
const { insertAccountSync } = require("../out/data/domains/account")
const { insertDefaultPlayerSync } = require("../out/data/domains/player")
const { setPlayerItemSync } = require("../out/data/domains/item")
const {
    createPlayerSaveSnapshotV2Sync,
    validatePlayerSaveSnapshotV2Sync,
} = require("../out/data/snapshots/player-snapshot")
const {
    exportPlayerSaveInWorker,
    PlayerSaveExportError,
} = require("../out/lib/player-save-export")
const playerRoutes = require("../out/routes/web_api/player").default

const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "leiting",
    idpId: "",
    status: "normal",
})
const player = insertDefaultPlayerSync(account.id)
setPlayerItemSync(player.id, 2, 12345)

test("worker 导出保持完整存档内容且不阻塞主事件循环", async () => {
    let mainLoopTicked = false
    const exportPromise = exportPlayerSaveInWorker(player.id)
    const mainLoopTick = new Promise(resolve => setImmediate(() => {
        mainLoopTicked = true
        resolve()
    }))

    await mainLoopTick
    assert.equal(mainLoopTicked, true)
    const exported = await exportPromise
    const snapshot = JSON.parse(exported.payload.toString("utf8"))
    const validated = validatePlayerSaveSnapshotV2Sync(snapshot, getDb())
    const direct = createPlayerSaveSnapshotV2Sync(player.id, getDb())

    assert.equal(validated.playerId, player.id)
    assert.equal(exported.rowCount, validated.summary.rowCount)
    assert.deepEqual(validated.data.tables.players_items, direct.data.tables.players_items)
    assert.ok(validated.data.tables.players_items.rows.some(row => row.includes(12345)))
})

test("五万行存档导出期间主事件循环仍持续响应", async () => {
    const insertHistory = getDb().prepare(`
        INSERT INTO players_receive_history
            (player_id, type, type_id, number, reason_id, create_time)
        VALUES (?, 1, 2, 1, 0, ?)
    `)
    getDb().transaction(() => {
        for (let index = 0; index < 50_000; index += 1) {
            insertHistory.run(player.id, `2026-08-30 00:${String(index % 60).padStart(2, "0")}:00`)
        }
    })()

    let eventLoopTicks = 0
    const timer = setInterval(() => { eventLoopTicks += 1 }, 2)
    let exported
    try {
        exported = await exportPlayerSaveInWorker(player.id)
    } finally {
        clearInterval(timer)
    }
    const snapshot = JSON.parse(exported.payload.toString("utf8"))
    assert.equal(snapshot.data.tables.players_receive_history.rows.length, 50_000)
    assert.ok(eventLoopTicks >= 3, `导出期间事件循环只运行了 ${eventLoopTicks} 次`)
})

test("worker 导出限制并发、大小和取消", async () => {
    const firstExport = exportPlayerSaveInWorker(player.id)
    await assert.rejects(
        exportPlayerSaveInWorker(player.id),
        error => error instanceof PlayerSaveExportError && error.code === "busy",
    )
    await firstExport

    await assert.rejects(
        exportPlayerSaveInWorker(player.id, { maxBytes: 1 }),
        error => error instanceof PlayerSaveExportError && error.code === "too-large",
    )

    const controller = new AbortController()
    controller.abort()
    await assert.rejects(
        exportPlayerSaveInWorker(player.id, { signal: controller.signal }),
        error => error instanceof PlayerSaveExportError && error.code === "aborted",
    )
})

test("存档下载路由返回 worker 生成的附件", async t => {
    const app = Fastify({ logger: false })
    t.after(() => app.close())
    await app.register(playerRoutes, { prefix: "/api/player" })
    await app.ready()

    const response = await app.inject({
        method: "GET",
        url: `/api/player/save?id=${player.id}`,
    })
    assert.equal(response.statusCode, 200)
    assert.match(response.headers["content-disposition"], new RegExp(`save_${player.id}\\.json`))
    assert.equal(JSON.parse(response.body).playerId, player.id)
})

test("Fastify 不会对已销毁 socket 自动补发响应", async () => {
    const fastifyRoot = path.dirname(require.resolve("fastify"))
    const wrapThenable = require(path.join(fastifyRoot, "lib", "wrap-thenable"))
    const { kReplyHijacked, kReplyIsError } = require(path.join(fastifyRoot, "lib", "symbols"))
    let sendCount = 0
    const reply = {
        [kReplyHijacked]: false,
        [kReplyIsError]: false,
        sent: false,
        raw: { headersSent: false },
        request: {
            raw: { aborted: false },
            socket: { destroyed: true },
        },
        send() { sendCount += 1 },
    }

    wrapThenable(Promise.resolve(undefined), reply)
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(sendCount, 0)
})

test.after(() => {
    try { getDb().close() } catch {}
    const resolved = path.resolve(temporaryDataDir)
    if (resolved.startsWith(path.resolve(os.tmpdir()) + path.sep)) {
        fs.rmSync(resolved, { recursive: true, force: true })
    }
})
