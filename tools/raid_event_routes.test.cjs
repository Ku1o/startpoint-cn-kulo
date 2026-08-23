require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")
const Fastify = require("fastify")
const { pack, unpack } = require("msgpackr")

const dataDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "raid-event-routes-"))
const previousDataDirectory = process.env.DATA_DIR
const previousDatabaseDirectory = process.env.WDFP_DATABASE_DIR
process.env.DATA_DIR = dataDirectory
delete process.env.WDFP_DATABASE_DIR

const { initializeDatabase } = require("../src/data")
const { getDb } = require("../src/data/db")
const { insertAccountSync } = require("../src/data/domains/account")
const { insertDefaultPlayerSync } = require("../src/data/domains/player")
const { activeQuests } = require("../src/routes/api/singleBattleQuest")
const raidEventRoutes = require("../src/routes/api/raidEvent").default

initializeDatabase()
const db = getDb()
const account = insertAccountSync({
    appId: "wf_cn",
    idpAlias: "",
    idpCode: "test",
    idpId: "raid-event-routes",
    status: "normal",
})
const player = insertDefaultPlayerSync(account.id)
const viewerId = 780000000 + player.id
db.prepare(`
    INSERT INTO sessions (token, account_id, expires, type)
    VALUES (?, ?, ?, 2)
`).run(String(viewerId), account.id, new Date("2099-12-31T23:59:59.000Z").toISOString())

function decode(response) {
    assert.match(response.headers["content-type"], /^application\/x-msgpack/)
    return unpack(Buffer.from(response.body, "base64"))
}

async function createApp() {
    const app = Fastify()
    app.addHook("onSend", (_request, reply, payload, done) => {
        if (reply.getHeader("content-type") === "application/x-msgpack") {
            done(null, pack(payload).toString("base64"))
            return
        }
        done(null, payload)
    })
    await app.register(raidEventRoutes, { prefix: "/api/index.php/event/raid" })
    await app.ready()
    return app
}

test.after(() => {
    delete activeQuests[player.id]
    if (db.open) db.close()
    fs.rmSync(dataDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
    if (previousDatabaseDirectory === undefined) delete process.env.WDFP_DATABASE_DIR
    else process.env.WDFP_DATABASE_DIR = previousDatabaseDirectory
})

test("Raid endpoints reject unsupported events and unauthenticated boss requests", async () => {
    const app = await createApp()
    try {
        const unsupported = await app.inject({
            method: "POST",
            url: "/api/index.php/event/raid/summary",
            payload: { viewer_id: viewerId, event_id: 6 },
        })
        assert.equal(unsupported.statusCode, 400)
        assert.equal(
            db.prepare(`SELECT COUNT(*) AS count FROM raid_event_global_state`).get().count,
            0,
        )

        const unauthenticated = await app.inject({
            method: "POST",
            url: "/api/index.php/event/raid/get_boss",
            payload: { viewer_id: viewerId + 999, event_id: 7 },
        })
        assert.equal(unauthenticated.statusCode, 400)

        const authenticated = await app.inject({
            method: "POST",
            url: "/api/index.php/event/raid/get_boss",
            payload: { viewer_id: viewerId, event_id: 7 },
        })
        assert.equal(authenticated.statusCode, 200, authenticated.body)
        assert.deepEqual(decode(authenticated).data.raid_boss, {
            hp_percentage: 100,
            total_kill_count: 0,
        })
    } finally {
        await app.close()
    }
})

test("Raid battle start binds only an official event/quest pair", async () => {
    const app = await createApp()
    const basePayload = {
        viewer_id: viewerId,
        quest_id: 7002,
        party_group_id: 1,
        play_id: "raid-route-play",
        use_auto_start_point: false,
        is_auto_start_mode: false,
    }
    try {
        const unknownQuest = await app.inject({
            method: "POST",
            url: "/api/index.php/event/raid/battle/start",
            payload: { ...basePayload, quest_id: 7999 },
        })
        assert.equal(unknownQuest.statusCode, 400)
        assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_active_quests`).get().count, 0)

        const mismatchedEvent = await app.inject({
            method: "POST",
            url: "/api/index.php/event/raid/battle/start",
            payload: { ...basePayload, event_id: 6 },
        })
        assert.equal(mismatchedEvent.statusCode, 400)
        assert.equal(db.prepare(`SELECT COUNT(*) AS count FROM players_active_quests`).get().count, 0)

        const valid = await app.inject({
            method: "POST",
            url: "/api/index.php/event/raid/battle/start",
            payload: basePayload,
        })
        assert.equal(valid.statusCode, 200, valid.body)
        assert.deepEqual(decode(valid).data, {})
        assert.deepEqual(
            db.prepare(`
                SELECT quest_id, category, event_id, play_id
                FROM players_active_quests
                WHERE player_id = ?
            `).get(player.id),
            {
                quest_id: 7002,
                category: 23,
                event_id: 7,
                play_id: "raid-route-play",
            },
        )
    } finally {
        await app.close()
    }
})
