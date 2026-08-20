require("ts-node/register/transpile-only")

const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")
const Fastify = require("fastify")
const { pack, unpack } = require("msgpackr")

const dataDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "player-history-profile-"))
const previousDataDirectory = process.env.DATA_DIR
process.env.DATA_DIR = dataDirectory

const { initializeDatabase } = require("../src/data")
const { getDb } = require("../src/data/db")
const { insertAccountSync } = require("../src/data/domains/account")
const { insertDefaultPlayerSync } = require("../src/data/domains/player")
const { setServerTime } = require("../src/utils")
const playerHistoryRoutes = require("../src/routes/api/playerHistory").default
const profileRoutes = require("../src/routes/api/profile").default

initializeDatabase()
setServerTime(new Date("2025-07-25T00:00:00.000Z"))
const db = getDb()

function createPlayer(suffix) {
    const account = insertAccountSync({
        appId: "wf_cn",
        idpAlias: "",
        idpCode: "test",
        idpId: `player-history-profile-${suffix}`,
        status: "normal",
    })
    const player = insertDefaultPlayerSync(account.id)
    const viewerId = 760000000 + player.id
    db.prepare(`
        INSERT INTO sessions (token, account_id, expires, type)
        VALUES (?, ?, ?, 2)
    `).run(String(viewerId), account.id, new Date("2099-12-31T23:59:59.000Z").toISOString())
    return { account, player, viewerId }
}

const owner = createPlayer("owner")
const visitor = createPlayer("visitor")

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
    await app.register(playerHistoryRoutes, { prefix: "/api/index.php/player_history" })
    await app.register(profileRoutes, { prefix: "/api/index.php/profile" })
    await app.ready()
    return app
}

test.after(() => {
    setServerTime(null)
    if (db.open) db.close()
    fs.rmSync(dataDirectory, { recursive: true, force: true })
    if (previousDataDirectory === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDirectory
})

test("player history exposes all required topic values and persists edits", async () => {
    const app = await createApp()
    try {
        db.prepare(`
            UPDATE players
            SET total_login_days = 30, bond_token = 12
            WHERE id = ?
        `).run(owner.player.id)
        db.prepare(`
            UPDATE players_characters
            SET exp = 342410
            WHERE player_id = ? AND id = 1
        `).run(owner.player.id)
        db.prepare(`
            UPDATE players_characters_bond_tokens
            SET status = 2
            WHERE player_id = ? AND character_id = 1 AND mana_board_index = 2
        `).run(owner.player.id)
        const mainQuests = require("../assets/main_quest.json")
        const insertQuest = db.prepare(`
            INSERT INTO players_quest_progress
                (section, quest_id, finished, host_finished, unlocked, player_id)
            VALUES (1, ?, 1, 0, 1, ?)
        `)
        for (const questId of Object.keys(mainQuests).map(Number)) {
            if (Math.floor(questId / 1000000) === 1) insertQuest.run(questId, owner.player.id)
        }

        const indexResponse = await app.inject({
            method: "POST",
            url: "/api/index.php/player_history/index",
            payload: { viewer_id: owner.viewerId },
        })
        assert.equal(indexResponse.statusCode, 200, indexResponse.body)
        const initial = decode(indexResponse).data
        assert.equal(initial.player_history_id, 1)
        assert.equal(initial.background_card_id, 1001)
        assert.deepEqual(initial.favorite_character, {
            character_ids: [1, null, null],
            unison_character_ids: [null, null, null],
        })
        assert.deepEqual(Object.keys(initial.player_history_topic_list), Array.from(
            { length: 27 },
            (_unused, index) => String(index + 1),
        ))
        assert.match(
            initial.player_history_topic_list[1].value_list.date_values[0],
            /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/,
        )
        assert.deepEqual(initial.player_history_topic_list[2].value_list.int_values, [30])
        assert.match(
            initial.player_history_topic_list[3].value_list.date_values[0],
            /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/,
        )
        assert.deepEqual(
            initial.player_history_topic_list[3].value_list.date_values.slice(1),
            [null, null, null, null, null],
        )
        assert.match(
            initial.player_history_topic_list[5].value_list.date_values[0],
            /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/,
        )
        assert.deepEqual(initial.player_history_topic_list[5].value_list.character_id_values, [1])
        assert.deepEqual(initial.player_history_topic_list[6].value_list.int_values, [1])
        assert.deepEqual(initial.player_history_topic_list[7].value_list.int_values, [12])
        assert.equal(initial.player_history_topic_list[6].is_visible, true)
        assert.equal(initial.player_history_topic_list[7].is_visible, false)
        assert.deepEqual(initial.player_history_topic_list[18].value_list.boss_id_values, [null])
        assert.deepEqual(initial.player_history_topic_list[19].value_list.character_id_values, [
            null, null, null, null, null, null, null,
        ])

        const edits = [
            {
                party_info: {
                    character_ids: [1, null, null],
                    unison_character_ids: [null, 1, null],
                },
                degree_id: null,
                background_card_id: null,
                player_history_topic_visible: null,
            },
            {
                party_info: null,
                degree_id: null,
                background_card_id: 1002,
                player_history_topic_visible: null,
            },
            {
                party_info: null,
                degree_id: null,
                background_card_id: null,
                player_history_topic_visible: { "1": false },
            },
        ]
        for (const edit of edits) {
            const response = await app.inject({
                method: "POST",
                url: "/api/index.php/player_history/edit",
                payload: { viewer_id: owner.viewerId, ...edit },
            })
            assert.equal(response.statusCode, 200, response.body)
            assert.deepEqual(decode(response).data, {})
        }

        const reloaded = decode(await app.inject({
            method: "POST",
            url: "/api/index.php/player_history/index",
            payload: { viewer_id: owner.viewerId },
        })).data
        assert.equal(reloaded.background_card_id, 1002)
        assert.deepEqual(reloaded.favorite_character.unison_character_ids, [null, 1, null])
        assert.equal(reloaded.player_history_topic_list[1].is_visible, false)

        const invalid = await app.inject({
            method: "POST",
            url: "/api/index.php/player_history/edit",
            payload: { viewer_id: owner.viewerId, background_card_id: 999999 },
        })
        assert.equal(invalid.statusCode, 400)
    } finally {
        await app.close()
    }
})

test("profile statistics and visibility settings are real and persistent", async () => {
    const app = await createApp()
    try {
        db.prepare(`
            UPDATE players_characters_bond_tokens
            SET status = 1
            WHERE player_id = ? AND character_id = 1 AND mana_board_index = 2
        `).run(owner.player.id)

        const mine = decode(await app.inject({
            method: "POST",
            url: "/api/index.php/profile/get_my_profile",
            payload: { viewer_id: owner.viewerId },
        })).data
        assert.equal(mine.profile_info.owned_character_count, 1)
        assert.equal(mine.profile_info.opened_mana_board_second_count, 1)
        assert.equal(mine.profile_info.owned_degree_count, 1)
        assert.equal(mine.profile_info.max_owned_character_count, 515)
        assert.equal(mine.profile_info.max_opened_mana_board_second_count, 484)
        assert.equal(mine.profile_info.max_owned_degree_count, 1485)
        assert.deepEqual(mine.profile_settings, {
            show_opened_mana_board_second_count: false,
            show_owned_character_count: true,
            show_owned_degree_count: true,
        })

        const updatedResponse = await app.inject({
            method: "POST",
            url: "/api/index.php/profile/update_profile_settings",
            payload: {
                viewer_id: owner.viewerId,
                profile_settings: {
                    show_opened_mana_board_second_count: false,
                    show_owned_character_count: false,
                    show_owned_degree_count: false,
                },
            },
        })
        assert.equal(updatedResponse.statusCode, 200, updatedResponse.body)

        const reloaded = decode(await app.inject({
            method: "POST",
            url: "/api/index.php/profile/get_my_profile",
            payload: { viewer_id: owner.viewerId },
        })).data
        assert.equal(reloaded.profile_settings.show_owned_character_count, false)

        const publicProfile = decode(await app.inject({
            method: "POST",
            url: "/api/index.php/profile/get_profile",
            payload: {
                viewer_id: visitor.viewerId,
                target_viewer_id: owner.viewerId,
            },
        })).data.target_user_info
        assert.equal(publicProfile.owned_character_count, null)
        assert.equal(publicProfile.max_owned_character_count, null)
        assert.equal(publicProfile.opened_mana_board_second_count, null)
        assert.equal(publicProfile.owned_degree_count, null)

        const clientOptions = require("../src/data/domains/option").getPlayerOptionsSync(owner.player.id)
        assert.equal(Object.keys(clientOptions).some(key => key.startsWith("profile.")), false)
    } finally {
        await app.close()
    }
})

test("player history returns the official period result code outside its window", async () => {
    const app = await createApp()
    try {
        setServerTime(new Date("2025-08-15T00:00:00.000Z"))
        const response = await app.inject({
            method: "POST",
            url: "/api/index.php/player_history/index",
            payload: { viewer_id: owner.viewerId },
        })
        assert.equal(response.statusCode, 200, response.body)
        assert.equal(decode(response).data_headers.result_code, 11101)
    } finally {
        setServerTime(new Date("2025-07-25T00:00:00.000Z"))
        await app.close()
    }
})
