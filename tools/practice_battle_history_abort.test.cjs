require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { randomUUID } = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const Fastify = require("fastify")
const { pack, unpack } = require("msgpackr")

const dataDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "practice-history-abort-db-"))
const previousDataDirectory = process.env.DATA_DIR
process.env.DATA_DIR = dataDirectory
let db

function cleanup() {
    if (db?.open) db.close()
    fs.rmSync(dataDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
}

process.once("exit", cleanup)

const { initializeDatabase } = require("../src/data")
const { insertAccountSync } = require("../src/data/domains/account")
const { insertDefaultPlayerSync } = require("../src/data/domains/player")
const singleBattleModule = require("../src/routes/api/singleBattleQuest")
const singleBattleRoutes = singleBattleModule.default
const historyRoutes = require("../src/routes/api/history").default

function decode(response) {
    assert.match(response.headers["content-type"], /^application\/x-msgpack/)
    return unpack(Buffer.from(response.body, "base64"))
}

function startPayload(viewerId, playId, apiCount) {
    return {
        viewer_id: viewerId,
        quest_id: 1,
        category: 15,
        party_id: 1,
        play_id: playId,
        use_boss_boost_point: false,
        use_boost_point: false,
        is_auto_start_mode: false,
        api_count: apiCount,
    }
}

function abortPayload(viewerId, playId, apiCount, damage) {
    return {
        viewer_id: viewerId,
        quest_id: 1,
        category: 15,
        play_id: playId,
        finish_kind: 1,
        api_count: apiCount,
        statistics: {
            clear_phase: 1,
            party: {
                characters: [{ id: 1 }, null, null],
                unison_characters: [null, null, null],
                equipments: [null, null, null],
                ability_soul_ids: [null, null, null],
            },
            zones: [{
                damage_deal_total: damage,
                members: [{ origin_damage: damage }, null, null],
            }],
        },
    }
}

async function main() {
    db = initializeDatabase()
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `practice-history-abort-${randomUUID()}`,
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    const viewerId = 820000000 + player.id
    db.prepare(`
        INSERT INTO sessions (token, account_id, expires, type)
        VALUES (?, ?, ?, 2)
    `).run(String(viewerId), account.id, new Date("2099-01-01T00:00:00.000Z").toISOString())

    const app = Fastify()
    app.addHook("onSend", (_request, reply, payload, done) => {
        if (reply.getHeader("content-type") === "application/x-msgpack") {
            done(null, pack(payload).toString("base64"))
            return
        }
        done(null, payload)
    })
    await app.register(singleBattleRoutes, { prefix: "/single_battle_quest" })
    await app.register(historyRoutes, { prefix: "/history" })
    await app.ready()

    const playId = "practice-abort-play-1"
    const start = await app.inject({
        method: "POST",
        url: "/single_battle_quest/start",
        payload: startPayload(viewerId, playId, 1),
    })
    assert.equal(start.statusCode, 200, start.body)
    const activeRow = db.prepare(`
        SELECT started_at_ms FROM players_active_quests
        WHERE player_id = ? AND play_id = ?
    `).get(player.id, playId)
    assert.equal(Number.isSafeInteger(activeRow.started_at_ms), true)

    const forcedStartedAtMs = activeRow.started_at_ms - 45_000
    db.prepare(`
        UPDATE players_active_quests SET started_at_ms = ? WHERE player_id = ?
    `).run(forcedStartedAtMs, player.id)
    // Exercise recovery from SQLite as it happens after a server restart.
    delete singleBattleModule.activeQuests[player.id]

    const mismatchedAbort = await app.inject({
        method: "POST",
        url: "/single_battle_quest/abort",
        payload: abortPayload(viewerId, "wrong-practice-play", 2, 456.5),
    })
    assert.equal(mismatchedAbort.statusCode, 400, mismatchedAbort.body)
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count FROM players_active_quests
        WHERE player_id = ? AND play_id = ?
    `).get(player.id, playId).count, 1)

    const abort = await app.inject({
        method: "POST",
        url: "/single_battle_quest/abort",
        payload: abortPayload(viewerId, playId, 3, 456.5),
    })
    assert.equal(abort.statusCode, 200, abort.body)
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count FROM players_active_quests WHERE player_id = ?
    `).get(player.id).count, 0)

    const historyResponse = await app.inject({
        method: "POST",
        url: "/history/practice_battle",
        payload: { viewer_id: viewerId },
    })
    assert.equal(historyResponse.statusCode, 200, historyResponse.body)
    const history = decode(historyResponse).data.history
    assert.equal(history.length, 1)
    assert.equal(Object.keys(history[0]).length, 29)
    assert.equal(history[0].quest_id, 1)
    assert.equal(history[0].finish_kind, 1)
    assert.equal(history[0].clear_rank, null)
    assert.equal(history[0].score, null)
    assert.equal(history[0].elapsed_time_ms, 45_000)
    assert.equal(history[0].total_damage, 456.5)
    assert.equal(history[0].character_1_total_damage, 456.5)
    assert.equal(history[0].character_id_1, 1)

    const rollbackPlayId = "practice-abort-play-rollback"
    const rollbackStart = await app.inject({
        method: "POST",
        url: "/single_battle_quest/start",
        payload: startPayload(viewerId, rollbackPlayId, 4),
    })
    assert.equal(rollbackStart.statusCode, 200, rollbackStart.body)
    db.exec(`
        CREATE TRIGGER reject_practice_active_delete
        BEFORE DELETE ON players_active_quests
        WHEN OLD.player_id = ${player.id} AND OLD.play_id = '${rollbackPlayId}'
        BEGIN
            SELECT RAISE(ABORT, 'forced practice abort failure');
        END;
    `)
    const rollbackAbort = await app.inject({
        method: "POST",
        url: "/single_battle_quest/abort",
        payload: abortPayload(viewerId, rollbackPlayId, 5, 789),
    })
    assert.equal(rollbackAbort.statusCode, 500, rollbackAbort.body)
    db.exec("DROP TRIGGER reject_practice_active_delete")
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count FROM players_practice_battle_history
        WHERE player_id = ?
    `).get(player.id).count, 1)
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count FROM players_active_quests
        WHERE player_id = ? AND play_id = ?
    `).get(player.id, rollbackPlayId).count, 1)
    assert.equal(singleBattleModule.activeQuests[player.id].playId, rollbackPlayId)

    await app.close()
    cleanup()
    process.removeListener("exit", cleanup)
}

main().then(
    () => console.log("practice battle history abort tests passed"),
    error => {
        console.error(error)
        process.exitCode = 1
    },
)
