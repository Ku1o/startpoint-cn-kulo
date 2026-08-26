require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const { randomUUID } = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const Fastify = require("fastify")
const { pack, unpack } = require("msgpackr")

const dataDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "practice-history-finish-db-"))
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
const singleBattleRoutes = require("../src/routes/api/singleBattleQuest").default
const historyRoutes = require("../src/routes/api/history").default

function decode(response) {
    assert.match(response.headers["content-type"], /^application\/x-msgpack/)
    return unpack(Buffer.from(response.body, "base64"))
}

async function main() {
    db = initializeDatabase()
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `practice-history-finish-${randomUUID()}`,
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    const viewerId = 810000000 + player.id
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

    const start = await app.inject({
        method: "POST",
        url: "/single_battle_quest/start",
        payload: {
            viewer_id: viewerId,
            quest_id: 1,
            category: 15,
            party_id: 1,
            play_id: "practice-finish-play-1",
            use_boss_boost_point: false,
            use_boost_point: false,
            is_auto_start_mode: false,
            api_count: 1,
        },
    })
    assert.equal(start.statusCode, 200, start.body)

    const finish = await app.inject({
        method: "POST",
        url: "/single_battle_quest/finish",
        payload: {
            viewer_id: viewerId,
            quest_id: 1,
            category: 15,
            continue_count: 0,
            elapsed_time_ms: 60_000,
            score: 12_345,
            add_mana: 0,
            is_accomplished: true,
            is_restored: false,
            api_count: 2,
            statistics: {
                clear_phase: 1,
                party: {
                    characters: [{ id: 1 }, null, null],
                    unison_characters: [null, null, null],
                    equipments: [null, null, null],
                    ability_soul_ids: [null, null, null],
                },
                zones: [{
                    damage_deal_total: 321.5,
                    members: [{ origin_damage: 321.5 }, null, null],
                }],
            },
        },
    })
    assert.equal(finish.statusCode, 200, finish.body)
    assert.equal(decode(finish).data.category_id, 15)

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
    assert.equal(history[0].finish_kind, 0)
    assert.equal(history[0].clear_rank, 5)
    assert.equal(history[0].elapsed_time_ms, 60_000)
    assert.equal(history[0].score, 12_345)
    assert.equal(history[0].total_damage, 321.5)
    assert.equal(history[0].character_1_total_damage, 321.5)
    assert.equal(history[0].character_id_1, 1)

    const failedStart = await app.inject({
        method: "POST",
        url: "/single_battle_quest/start",
        payload: {
            viewer_id: viewerId,
            quest_id: 1,
            category: 15,
            party_id: 1,
            play_id: "practice-finish-play-2",
            use_boss_boost_point: false,
            use_boost_point: false,
            is_auto_start_mode: false,
            api_count: 3,
        },
    })
    assert.equal(failedStart.statusCode, 200, failedStart.body)

    const failedFinish = await app.inject({
        method: "POST",
        url: "/single_battle_quest/finish",
        payload: {
            viewer_id: viewerId,
            quest_id: 1,
            category: 15,
            continue_count: 0,
            elapsed_time_ms: 75_000,
            score: 999,
            add_mana: 0,
            is_accomplished: false,
            is_restored: false,
            api_count: 4,
            statistics: {
                clear_phase: 1,
                party: {
                    characters: [{ id: 1 }, null, null],
                    unison_characters: [null, null, null],
                    equipments: [null, null, null],
                    ability_soul_ids: [null, null, null],
                },
                zones: [{
                    damage_deal_total: 111,
                    members: [{ origin_damage: 111 }, null, null],
                }],
            },
        },
    })
    assert.equal(failedFinish.statusCode, 200, failedFinish.body)

    const failedHistoryResponse = await app.inject({
        method: "POST",
        url: "/history/practice_battle",
        payload: { viewer_id: viewerId },
    })
    assert.equal(failedHistoryResponse.statusCode, 200, failedHistoryResponse.body)
    const failedHistory = decode(failedHistoryResponse).data.history
    assert.equal(failedHistory.length, 2)
    assert.equal(failedHistory[0].finish_kind, 1)
    assert.equal(failedHistory[0].clear_rank, null)
    assert.equal(failedHistory[0].elapsed_time_ms, 75_000)
    assert.equal(failedHistory[0].total_damage, 111)

    const rollbackStart = await app.inject({
        method: "POST",
        url: "/single_battle_quest/start",
        payload: {
            viewer_id: viewerId,
            quest_id: 1,
            category: 15,
            party_id: 1,
            play_id: "practice-finish-play-rollback",
            use_boss_boost_point: false,
            use_boost_point: false,
            is_auto_start_mode: false,
            api_count: 5,
        },
    })
    assert.equal(rollbackStart.statusCode, 200, rollbackStart.body)
    db.exec(`
        CREATE TRIGGER reject_practice_character_exp
        BEFORE UPDATE ON players_characters
        WHEN OLD.player_id = ${player.id} AND OLD.id = 1
        BEGIN
            SELECT RAISE(ABORT, 'forced practice settlement failure');
        END;
    `)
    const rollbackFinish = await app.inject({
        method: "POST",
        url: "/single_battle_quest/finish",
        payload: {
            viewer_id: viewerId,
            quest_id: 1,
            category: 15,
            continue_count: 0,
            elapsed_time_ms: 80_000,
            score: 555,
            add_mana: 0,
            is_accomplished: true,
            is_restored: false,
            api_count: 6,
            statistics: {
                clear_phase: 1,
                party: {
                    characters: [{ id: 1 }, null, null],
                    unison_characters: [null, null, null],
                    equipments: [null, null, null],
                    ability_soul_ids: [null, null, null],
                },
                zones: [{
                    damage_deal_total: 222,
                    members: [{ origin_damage: 222 }, null, null],
                }],
            },
        },
    })
    assert.equal(rollbackFinish.statusCode, 500, rollbackFinish.body)
    db.exec("DROP TRIGGER reject_practice_character_exp")
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count FROM players_practice_battle_history
        WHERE player_id = ?
    `).get(player.id).count, 2)
    assert.equal(db.prepare(`
        SELECT COUNT(*) AS count FROM players_active_quests
        WHERE player_id = ? AND play_id = ?
    `).get(player.id, "practice-finish-play-rollback").count, 1)

    await app.close()
    cleanup()
    process.removeListener("exit", cleanup)
}

main().then(
    () => console.log("practice battle history finish tests passed"),
    error => {
        console.error(error)
        process.exitCode = 1
    },
)
